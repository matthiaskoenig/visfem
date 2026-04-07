"""Mesh loading utilities for FEM simulation data.

load_mesh(path, step)  -> pv.DataSet
get_metadata(path)     -> MeshMetadata
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import cast, TypedDict

import h5py
import meshio
import meshio.xdmf.common as _xdmf_common
import numpy as np
import pyvista as pv

from visfem.log import get_logger


# ---- Types ----

class FieldInfo(TypedDict):
    center: str       # "point" or "cell"
    shape: list[int]  # [1] for scalar, [3] for vector, [3, 3] for tensor


class MeshMetadata(TypedDict):
    format: str             # one of: fenics_xdmf, timeseries_xdmf, pyvista_native, meshio_fallback
    n_steps: int            # 1 for static datasets
    times: list[float]      # simulation timestamps; empty for static datasets
    n_points: int
    n_cells: int
    cell_types: list[str]   # e.g. ["triangle"] or ["tetra"]
    fields: dict[str, FieldInfo]


logger = get_logger(__name__)


# ---- Constants ----

# File extensions that PyVista can read natively
_PYVISTA_NATIVE: frozenset[str] = frozenset(
    {".vtk", ".vtu", ".vtp", ".vts", ".vtr", ".vti", ".pvd", ".pvtu", ".pvtp"}
)

# File extensions that may contain time-series data
_XDMF_EXTENSIONS: frozenset[str] = frozenset({".xdmf", ".xmf"})

# Geometric dimension per meshio cell type; used to drop boundary marker cells
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

# XDMF TopologyType names -> meshio cell type names
_XDMF_TO_MESHIO_CELLTYPE: dict[str, str] = {
    "polyline": "line",
    "triangle": "triangle",
    "quadrilateral": "quad",
    "tetrahedron": "tetra",
    "hexahedron": "hexahedron",
    "wedge": "wedge",
    "pyramid": "pyramid",
}

# Patch: meshio XDMF type map is missing PolyLine (present in convergence_sixth files)
if "PolyLine" not in _xdmf_common.xdmf_to_meshio_type:
    _xdmf_common.xdmf_to_meshio_type["PolyLine"] = "line"
    _xdmf_common.meshio_to_xdmf_type["line"] = ("PolyLine",)


# ---- Internal utilities ----

def _require(element: ET.Element | None, tag: str, context: str) -> ET.Element:
    """Return element or raise ValueError if None."""
    if element is None:
        raise ValueError(f"Missing required XML element <{tag}> in {context}")
    return element


def _filter_to_max_dim_cells(cells: list) -> list:
    """Return only the highest-dimensional cell blocks from a mixed-topology list.

    Drops lower-dimensional boundary markers (e.g. PolyLine alongside tetra)
    that would otherwise crash pv.from_meshio().
    """
    if not cells:
        return cells
    max_dim = max(_CELL_DIM.get(block.type, 0) for block in cells)
    filtered = [block for block in cells if _CELL_DIM.get(block.type, 0) == max_dim]
    dropped = [block.type for block in cells if _CELL_DIM.get(block.type, 0) < max_dim]
    if dropped:
        logger.debug(f"Filtered out lower-dimensional cell blocks: {dropped}")
    return filtered


def _parse_xdmf_base_grid(
    path: Path,
) -> tuple[ET.Element, ET.Element, ET.Element, ET.Element]:
    """Parse geometry and topology elements from the base Uniform grid of an XDMF file.

    Returns (domain, topology_elem, topo_item, geo_item).
    """
    tree = ET.parse(path)
    domain        = _require(tree.getroot().find("Domain"), "Domain", path.name)
    uniform       = next(g for g in domain.findall("Grid") if g.get("GridType") == "Uniform")
    topology_elem = _require(uniform.find("Topology"), "Topology", path.name)
    topo_item     = _require(topology_elem.find("DataItem"), "DataItem", path.name)
    geo_item      = _require(
        _require(uniform.find("Geometry"), "Geometry", path.name).find("DataItem"),
        "DataItem", path.name,
    )
    return domain, topology_elem, topo_item, geo_item


# ---- Format detection ----

def _detect_format(path: Path) -> str:
    """Return a format string for the given file path.

    Returns one of: fenics_xdmf, timeseries_xdmf, pyvista_native, meshio_fallback.
    """
    suffix = path.suffix.lower()
    if suffix in _PYVISTA_NATIVE:
        return "pyvista_native"
    if suffix in _XDMF_EXTENSIONS:
        return _detect_xdmf_subtype(path)
    return "meshio_fallback"


def _detect_xdmf_subtype(path: Path) -> str:
    """Distinguish FEniCS-style from meshio-style XDMF by counting Temporal Collections.

    FEniCS writes one Temporal Collection per field (N collections).
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
    if len(temporal_collections) == 1:
        return "timeseries_xdmf"
    # No temporal collections: static FEniCS geometry-only file
    return "fenics_xdmf"


# ---- Metadata extraction ----

def get_metadata(path: Path) -> MeshMetadata:
    """Return a format-agnostic metadata descriptor for any supported mesh file.

    Caches the result as a .meta.json sidecar next to the source file.
    Delete the sidecar to force regeneration.
    """
    sidecar = path.with_suffix(".meta.json")
    if sidecar.exists():
        logger.debug(f"Loading cached metadata from '{sidecar.name}'")
        return cast(MeshMetadata, json.loads(sidecar.read_text()))
    logger.debug(f"Computing metadata for '{path.name}'")
    fmt = _detect_format(path)
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
    """Extract metadata from a meshio-style XDMF time series.

    Reads all steps to collect timestamps; field shapes are taken from step 0.
    """
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        points, cells = reader.read_points_cells()
        num_steps = reader.num_steps
        times: list[float] = []
        fields: dict[str, FieldInfo] = {}
        for step in range(num_steps):
            timestamp, point_data, cell_data = reader.read_data(step)
            times.append(float(timestamp))
            # Collect field shapes from the first step only
            if not fields:
                for name, field_array in point_data.items():
                    fields[name] = {"center": "point", "shape": list(field_array.shape[1:] or [1])}
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
    """Extract metadata from a FEniCS-style XDMF file via h5py.

    Reads the base Uniform grid for geometry dimensions, then iterates
    Temporal Collections to collect timestamps and per-field shapes.
    """
    domain, topology_elem, topo_item, geo_item = _parse_xdmf_base_grid(path)

    # Dimensions attribute is "n_rows n_cols"; first token is the count
    n_points  = int((geo_item.get("Dimensions") or "").split()[0])
    n_cells   = int((topo_item.get("Dimensions") or "").split()[0])
    cell_type = topology_elem.get("TopologyType", "unknown").lower()

    fields: dict[str, FieldInfo] = {}
    times: list[float] = []
    temporal_grids = [g for g in domain.findall("Grid") if g.get("CollectionType") == "Temporal"]

    with h5py.File(str(path.parent / path.stem) + ".h5", "r") as hdf5:
        for collection in temporal_grids:
            field_name = collection.get("Name")
            if field_name is None:
                continue
            # Timestamps are identical across all fields; read from the first collection only
            if not times:
                for child in collection.findall("Grid"):
                    t_elem = child.find("Time")
                    if t_elem is not None:
                        value = t_elem.get("Value")
                        if value is not None:
                            times.append(float(value))
            # Read center and array shape from step 0 of this field
            first_child = collection.find("Grid")
            if first_child is not None:
                attr = first_child.find("Attribute")
                if attr is not None:
                    center = attr.get("Center", "Node").lower()
                    center = "point" if center == "node" else "cell"
                    data_item = attr.find("DataItem")
                    if data_item is not None:
                        # DataItem text is "filename.h5:/path/to/dataset"; take the dataset path
                        hdf5_key = (data_item.text or "").strip().split(":/")[1]
                        try:
                            shape = list(hdf5[hdf5_key].shape[1:] or [1])
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
    """Extract metadata from a static (non-time-series) mesh file."""
    # cast needed because pv.read() return type is not narrowed by PyVista's stubs
    mesh = cast(
        pv.DataSet,
        pv.read(str(path))
        if path.suffix.lower() in _PYVISTA_NATIVE
        else pv.from_meshio(meshio.read(str(path))),
    )

    def _field_shape(field_array: np.ndarray) -> list[int]:
        """Return [1] for scalar arrays, [n] for vector/tensor arrays."""
        return list(field_array.shape[1:]) if field_array.ndim > 1 else [1]

    return {
        "format": fmt,
        "n_steps": 1,
        "times": [],
        "n_points": mesh.n_points,
        "n_cells": mesh.n_cells,
        "cell_types": [str(cell_type.name).lower() for cell_type in mesh.distinct_cell_types],
        "fields": {
            **{name: {"center": "point", "shape": _field_shape(field_array)}
               for name, field_array in mesh.point_data.items()},
            **{name: {"center": "cell", "shape": _field_shape(field_array)}
               for name, field_array in mesh.cell_data.items()},
        },
    }


# ---- Mesh loaders ----

def _load_fenics_xdmf(path: Path, step: int = 0) -> pv.UnstructuredGrid:
    """Load one timestep from a FEniCS-style XDMF file.

    Reads geometry from HDF5, builds the base mesh, then attaches all
    field arrays at the requested step.
    """
    domain, topology_elem, topo_item, geo_item = _parse_xdmf_base_grid(path)

    topo_type_raw = topology_elem.get("TopologyType", "").lower()
    topo_type     = _XDMF_TO_MESHIO_CELLTYPE.get(topo_type_raw, topo_type_raw)
    h5_file       = path.parent / (path.stem + ".h5")

    with h5py.File(str(h5_file), "r") as hdf5:
        # DataItem text is "filename.h5:/path/to/dataset"; take the dataset path
        points_2d    = hdf5[(geo_item.text  or "").strip().split(":/")[1]][:]
        connectivity = hdf5[(topo_item.text or "").strip().split(":/")[1]][:]

        # FEniCS 2D meshes have no z column; pad with zeros for PyVista
        if points_2d.shape[1] == 2:
            points = np.column_stack([points_2d, np.zeros(len(points_2d))])
        else:
            points = points_2d

        # Build the base mesh (geometry only, no fields yet)
        cells  = _filter_to_max_dim_cells([meshio.CellBlock(topo_type, connectivity)])
        pvmesh = pv.from_meshio(meshio.Mesh(points=points, cells=cells))

        # Each Temporal Collection is one field; attach all fields at the requested step
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
            center   = attr.get("Center", "Node").lower()
            # DataItem text is "filename.h5:/path/to/dataset"; take the dataset path
            hdf5_key = (data_item.text or "").strip().split(":/")[1]
            try:
                field_array = hdf5[hdf5_key][:]
                # Squeeze trailing size-1 dim: (n, 1) -> (n,) for scalars
                if field_array.ndim > 1 and field_array.shape[-1] == 1:
                    field_array = field_array.squeeze(-1)
                # XDMF uses "Node" for point-centered data, "Cell" for cell-centered
                if center == "node":
                    pvmesh.point_data[field_name] = field_array
                else:
                    pvmesh.cell_data[field_name] = field_array
            except KeyError:
                logger.warning(f"HDF5 key '{hdf5_key}' not found, skipping field '{field_name}'.")

    logger.debug(
        f"Loaded '{path.name}' step {step}: "
        f"{pvmesh.n_points} points, {pvmesh.n_cells} cells, "
        f"fields: {list(pvmesh.point_data.keys()) + list(pvmesh.cell_data.keys())}"
    )
    return pvmesh


def _load_timeseries_xdmf(path: Path, step: int = 0) -> pv.UnstructuredGrid:
    """Load one timestep from a meshio-style XDMF time series."""
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        logger.debug(f"Loading '{path.name}' ({reader.num_steps} steps)")
        points, cells = reader.read_points_cells()
        _timestamp, point_data, cell_data = reader.read_data(step)
        cells = _filter_to_max_dim_cells(cells)
        mesh  = meshio.Mesh(
            points=points,
            cells=cells,
            point_data=point_data,
            cell_data=cell_data,
        )
    return pv.from_meshio(mesh)


def _load_static(path: Path) -> pv.DataSet:
    """Load a static mesh via PyVista (native formats) or meshio (fallback)."""
    if path.suffix.lower() in _PYVISTA_NATIVE:
        logger.debug(f"[pyvista] loading '{path.name}'")
        return cast(pv.DataSet, pv.read(str(path)))
    logger.debug(f"[meshio] loading '{path.name}'")
    return pv.from_meshio(meshio.read(str(path)))


# --------

def load_mesh(path: Path, step: int = 0) -> pv.DataSet:
    """Load any supported mesh file and return a PyVista dataset.

    Dispatches to the correct private loader based on detected format.
    All fields at the given timestep are attached to the returned mesh.
    """
    fmt = _detect_format(path)
    logger.debug(f"Loading '{path.name}' as '{fmt}' step {step}")
    if fmt == "fenics_xdmf":
        return _load_fenics_xdmf(path, step)
    if fmt == "timeseries_xdmf":
        return _load_timeseries_xdmf(path, step)
    return _load_static(path)