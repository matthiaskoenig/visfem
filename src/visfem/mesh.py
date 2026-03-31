"""Mesh loading utilities for FEM simulation data."""

import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import cast, TypedDict

import h5py
import meshio
import meshio.xdmf.common as _xdmf_common
import numpy as np
import pyvista as pv

from visfem.log import get_logger


class FieldInfo(TypedDict):
    center: str
    shape: list[int]


class MeshMetadata(TypedDict):
    format: str
    n_steps: int
    times: list[float]
    n_points: int
    n_cells: int
    cell_types: list[str]
    fields: dict[str, FieldInfo]


logger: logging.Logger = get_logger(__name__)


# File extensions that PyVista can read natively
_PYVISTA_NATIVE: frozenset[str] = frozenset(
    {".vtk", ".vtu", ".vtp", ".vts", ".vtr", ".vti", ".pvd", ".pvtu", ".pvtp"}
)

# File extensions that may contain time-series data
_XDMF_TIMESERIES: frozenset[str] = frozenset({".xdmf", ".xmf"})

# Patch meshio XDMF type map to include PolyLine (missing by default)
if "PolyLine" not in _xdmf_common.xdmf_to_meshio_type:
    _xdmf_common.xdmf_to_meshio_type["PolyLine"] = "line"
    _xdmf_common.meshio_to_xdmf_type["line"] = ("PolyLine",)

# Geometric dimension per meshio cell type
_CELL_DIM: dict[str, int] = {
    "vertex": 0,
    "line": 1, "line3": 1, "line4": 1,
    "triangle": 2, "triangle6": 2, "triangle10": 2,
    "quad": 2, "quad8": 2, "quad9": 2,
    "tetra": 3, "tetra10": 3, "tetra20": 3,
    "hexahedron": 3, "hexahedron20": 3, "hexahedron27": 3,
    "wedge": 3, "wedge15": 3, "wedge18": 3,
    "pyramid": 3, "pyramid13": 3, "pyramid14": 3,
}

# XDMF topology type names mapped to meshio cell type names
_XDMF_TO_MESHIO_CELLTYPE: dict[str, str] = {
    "polyline": "line",
    "triangle": "triangle",
    "quadrilateral": "quad",
    "tetrahedron": "tetra",
    "hexahedron": "hexahedron",
    "wedge": "wedge",
    "pyramid": "pyramid",
}


def _filter_to_max_dim_cells(cells: list) -> list:
    """Return only the cell blocks with the highest geometric dimension.

    Drops lower-dimensional boundary marker cells (e.g. PolyLine)
    that would otherwise cause pv.from_meshio() to crash.
    """
    if not cells:
        return cells
    max_dim = max(_CELL_DIM.get(block.type, 0) for block in cells)
    filtered = [block for block in cells if _CELL_DIM.get(block.type, 0) == max_dim]
    dropped = [b.type for b in cells if _CELL_DIM.get(b.type, 0) < max_dim]
    if dropped:
        logger.debug(f"Filtered out lower-dimensional cell blocks: {dropped}")
    return filtered


def _detect_format(path: Path) -> str:
    """Return a format string for the given mesh file.

    Possible values: fenics_xdmf, timeseries_xdmf, pyvista_native, meshio_fallback.
    """
    suffix = path.suffix.lower()
    if suffix in _PYVISTA_NATIVE:
        return "pyvista_native"
    if suffix in _XDMF_TIMESERIES:
        # Need to peek inside the XML to distinguish the two XDMF subtypes
        return _detect_xdmf_subtype(path)
    return "meshio_fallback"


def _detect_xdmf_subtype(path: Path) -> str:
    """Distinguish FEniCS XDMF from meshio time-series XDMF by counting Temporal Collections.

    FEniCS writes one Temporal Collection per field.
    Meshio writes one Temporal Collection containing all fields per timestep.
    """
    tree = ET.parse(path)
    domain = tree.getroot().find("Domain")
    if domain is None:
        raise ValueError(f"No Domain element found in {path.name}")

    temporal_collections = [
        grid for grid in domain.findall("Grid")
        if grid.get("CollectionType") == "Temporal"
    ]

    if len(temporal_collections) > 1:
        return "fenics_xdmf"
    elif len(temporal_collections) == 1:
        return "timeseries_xdmf"
    else:
        # No temporal collections, assume static FEniCS mesh
        return "fenics_xdmf"


def get_metadata(path: Path) -> MeshMetadata:
    """Return a metadata descriptor for any supported mesh file.

    Result is cached as a .meta.json sidecar next to the source file.
    Delete the sidecar to force regeneration.
    """
    sidecar = path.with_suffix(".meta.json")
    if sidecar.exists():
        logger.debug(f"Loading cached metadata from '{sidecar.name}'")
        return cast(MeshMetadata, json.loads(sidecar.read_text()))

    logger.debug(f"Computing metadata for '{path.name}'")
    fmt = _detect_format(path)

    # Route to the format-specific metadata extractor
    if fmt == "fenics_xdmf":
        meta = _metadata_fenics_xdmf(path, fmt)
    elif fmt == "timeseries_xdmf":
        meta = _metadata_timeseries_xdmf(path, fmt)
    else:
        meta = _metadata_static(path, fmt)

    sidecar.write_text(json.dumps(meta, indent=2))
    logger.debug(f"Cached metadata to '{sidecar.name}'")
    return meta


def _metadata_timeseries_xdmf(path: Path, fmt: str) -> MeshMetadata:
    """Extract metadata from a meshio-style XDMF time series."""
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        points, cells = reader.read_points_cells()
        num_steps = reader.num_steps
        times: list[float] = []
        fields: dict[str, FieldInfo] = {}

        for step in range(num_steps):
            t, point_data, cell_data = reader.read_data(step)
            times.append(float(t))
            # Collect field names and shapes from the first step only
            if not fields:
                for name, arr in point_data.items():
                    fields[name] = {"center": "point", "shape": list(arr.shape[1:] or [1])}
                for name, blocks in cell_data.items():
                    fields[name] = {"center": "cell", "shape": list(blocks[0].shape[1:] or [1])}

    return {
        "format": fmt,
        "n_steps": num_steps,
        "times": times,
        "n_points": len(points) if points is not None else 0,
        "n_cells": sum(len(block.data) for block in cells) if cells else 0,
        "cell_types": list({block.type for block in cells}) if cells else [],
        "fields": fields,
    }


def _metadata_fenics_xdmf(path: Path, fmt: str) -> MeshMetadata:
    """Extract metadata from a FEniCS-style XDMF file via h5py."""
    tree = ET.parse(path)
    domain = tree.getroot().find("Domain")
    if domain is None:
        raise ValueError(f"No Domain element found in {path.name}")

    # Geometry and topology dimensions live in the first Uniform grid
    uniform = next(g for g in domain.findall("Grid") if g.get("GridType") == "Uniform")
    geo_item = uniform.find("Geometry").find("DataItem")
    topo_item = uniform.find("Topology").find("DataItem")
    n_points = int(geo_item.get("Dimensions").split()[0])
    n_cells = int(topo_item.get("Dimensions").split()[0])
    cell_type = uniform.find("Topology").get("TopologyType", "unknown").lower()

    fields: dict[str, FieldInfo] = {}
    times: list[float] = []
    temporal_grids = [g for g in domain.findall("Grid") if g.get("CollectionType") == "Temporal"]

    with h5py.File(str(path.parent / path.stem) + ".h5", "r") as f:
        for collection in temporal_grids:
            field_name = collection.get("Name")
            if field_name is None:
                continue
            # Collect time values from the first field collection only
            if not times:
                for child in collection.findall("Grid"):
                    t_elem = child.find("Time")
                    if t_elem is not None:
                        value = t_elem.get("Value")
                        if value is not None:
                            times.append(float(value))
            # Read center and shape from the first timestep of this field
            first_child = collection.find("Grid")
            if first_child is not None:
                attr = first_child.find("Attribute")
                if attr is not None:
                    center = attr.get("Center", "Node").lower()
                    center = "point" if center == "node" else "cell"
                    data_item = attr.find("DataItem")
                    if data_item is not None:
                        hdf5_key = data_item.text.strip().split(":/")[1]
                        try:
                            shape = list(f[hdf5_key].shape[1:] or [1])
                        except KeyError:
                            shape = [1]
                        fields[field_name] = {"center": center, "shape": shape}

    return {
        "format": fmt,
        "n_steps": len(times),
        "times": times,
        "n_points": n_points,
        "n_cells": n_cells,
        "cell_types": [cell_type],
        "fields": fields,
    }


def _metadata_static(path: Path, fmt: str) -> MeshMetadata:
    """Extract metadata from a static mesh file."""
    mesh = (
        pv.read(str(path))
        if path.suffix.lower() in _PYVISTA_NATIVE
        else pv.from_meshio(meshio.read(str(path)))
    )
    return {
        "format": fmt,
        "n_steps": 1,
        "times": [],
        "n_points": mesh.n_points,
        "n_cells": mesh.n_cells,
        "cell_types": [str(ct.name).lower() for ct in mesh.distinct_cell_types],
        "fields": {
            **{name: {"center": "point", "shape": [1]} for name in mesh.point_data.keys()},
            **{name: {"center": "cell", "shape": [1]} for name in mesh.cell_data.keys()},
        },
    }


def _load_fenics_xdmf(path: Path, step: int = 0) -> pv.UnstructuredGrid:
    """Load one time step from a FEniCS XDMF file.

    Reads geometry from HDF5 once, then attaches all fields at the given step.
    """
    tree = ET.parse(path)
    domain = tree.getroot().find("Domain")

    # Parse geometry and topology from the base Uniform grid
    uniform = next(g for g in domain.findall("Grid") if g.get("GridType") == "Uniform")
    geo_item = uniform.find("Geometry").find("DataItem")
    topo_item = uniform.find("Topology").find("DataItem")
    topo_type_raw = uniform.find("Topology").get("TopologyType", "").lower()
    topo_type = _XDMF_TO_MESHIO_CELLTYPE.get(topo_type_raw, topo_type_raw)

    h5_file = path.parent / (path.stem + ".h5")

    with h5py.File(str(h5_file), "r") as f:
        points_2d = f[geo_item.text.strip().split(":/")[1]][:]
        connectivity = f[topo_item.text.strip().split(":/")[1]][:]

        # FEniCS often writes 2D coordinates only; pad z column with zeros
        if points_2d.shape[1] == 2:
            points = np.column_stack([points_2d, np.zeros(len(points_2d))])
        else:
            points = points_2d

        # Build the base mesh without any field data first
        cells = [meshio.CellBlock(topo_type, connectivity)]
        cells = _filter_to_max_dim_cells(cells)
        pvmesh = pv.from_meshio(meshio.Mesh(points=points, cells=cells))

        # Each Temporal Collection is one field; attach all at the requested step
        temporal_grids = [
            g for g in domain.findall("Grid")
            if g.get("CollectionType") == "Temporal"
        ]

        for collection in temporal_grids:
            field_name = collection.get("Name")
            if field_name is None:
                continue
            children = collection.findall("Grid")
            if step >= len(children):
                logger.warning(
                    f"Step {step} out of range for field '{field_name}' "
                    f"({len(children)} steps available), skipping."
                )
                continue

            attr = children[step].find("Attribute")
            if attr is None:
                continue
            data_item = attr.find("DataItem")
            if data_item is None:
                continue

            center = attr.get("Center", "Node").lower()
            hdf5_key = data_item.text.strip().split(":/")[1]
            try:
                arr = f[hdf5_key][:]
                # Squeeze trailing size-1 dim so scalar fields have shape (n,) not (n, 1)
                if arr.ndim > 1 and arr.shape[-1] == 1:
                    arr = arr.squeeze(-1)
                if center == "node":
                    pvmesh.point_data[field_name] = arr
                else:
                    pvmesh.cell_data[field_name] = arr
            except KeyError:
                logger.warning(f"HDF5 key '{hdf5_key}' not found, skipping field '{field_name}'.")

    logger.debug(
        f"Loaded '{path.name}' step {step}: "
        f"{pvmesh.n_points} points, {pvmesh.n_cells} cells, "
        f"fields: {list(pvmesh.point_data.keys()) + list(pvmesh.cell_data.keys())}"
    )
    return pvmesh


def _load_timeseries_xdmf(path: Path, step: int = 0) -> pv.UnstructuredGrid:
    """Load one time step from a meshio XDMF time series."""
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        logger.debug(f"Loading '{path.name}' ({reader.num_steps} steps)")
        points, cells = reader.read_points_cells()
        t, point_data, cell_data = reader.read_data(step)
        cells = _filter_to_max_dim_cells(cells)
        mesh = meshio.Mesh(
            points=points,
            cells=cells,
            point_data=point_data,
            cell_data=cell_data,
        )
    return pv.from_meshio(mesh)


def _load_static(path: Path) -> pv.DataSet:
    """Load a static mesh file via PyVista or meshio fallback."""
    if path.suffix.lower() in _PYVISTA_NATIVE:
        logger.debug(f"[pyvista] loading '{path.name}'")
        return cast(pv.DataSet, pv.read(str(path)))
    logger.debug(f"[meshio] loading '{path.name}'")
    return pv.from_meshio(meshio.read(str(path)))


def load_mesh(path: Path, step: int = 0) -> pv.DataSet:
    """Load any supported mesh file and return a PyVista dataset.

    All fields at the given step are attached to the returned mesh.
    """
    fmt = _detect_format(path)
    logger.debug(f"Loading '{path.name}' as '{fmt}' step {step}")
    if fmt == "fenics_xdmf":
        return _load_fenics_xdmf(path, step)
    if fmt == "timeseries_xdmf":
        return _load_timeseries_xdmf(path, step)
    return _load_static(path)


if __name__ == "__main__":
    # convergence_sixth (XDMF time-series, 3D wedge mesh)
    DATA_DIR = Path(__file__).parents[3] / "visfem_data" / "convergence_sixth" / "xdmf"
    OUTPUT_DIR = Path(__file__).parents[3] / "visfem_results"
    OUTPUT_DIR.mkdir(exist_ok=True)

    MESH_FILES = [
        DATA_DIR / "lobule_sixth_00005.xdmf",
        DATA_DIR / "lobule_sixth_000025.xdmf",
        DATA_DIR / "lobule_sixth_0000125.xdmf",
        DATA_DIR / "lobule_sixth_00000625.xdmf",
    ]
    STEP = 150
    FIELD = None

    # get_metadata(MESH_FILES[1])
    # load_mesh(MESH_FILES[1], step=STEP)

    # 3D-IRCADb-01 (static VTK surface meshes)
    IRCADB_DIR = Path(__file__).parents[3] / "visfem_data" / "3Dircadb1"
    PATIENT_NR = 2
    ORGAN = "liver"

    # get_metadata(IRCADB_DIR / f"3Dircadb1.{PATIENT_NR}" / "MESHES_VTK" / f"{ORGAN}.vtk")
    # load_mesh(IRCADB_DIR / f"3Dircadb1.{PATIENT_NR}" / "MESHES_VTK" / f"{ORGAN}.vtk")

    # 08_SPP_FEMVis (FEniCS XDMF, 2D meshes)
    SPP_DIR = Path(__file__).parents[3] / "visfem_data" / "08_SPP_FEMVis"

    # get_metadata(SPP_DIR / "deformation" / "deformation.xdmf")
    # get_metadata(SPP_DIR / "lobule" / "lobule_spt_p1.xdmf")
    # get_metadata(SPP_DIR / "lobule" / "lobule_spt_p6.xdmf")
    # get_metadata(SPP_DIR / "scan" / "scan_64_p1.xdmf")
    # load_mesh(SPP_DIR / "lobule" / "lobule_spt_p1.xdmf", step=0)