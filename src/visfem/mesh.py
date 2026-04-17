"""Mesh loading utilities for FEM simulation data.

load_mesh(path, step)  -> pv.DataSet
get_metadata(path)     -> MeshMetadata
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import cast

import h5py
import meshio
import meshio.xdmf.common as _xdmf_common
import numpy as np
import pyvista as pv

from visfem.log import get_logger
from visfem.models import MESH_METADATA_HASH, MeshMetadata


logger = get_logger(__name__)


# Constants

# File extensions that PyVista can read natively
_PYVISTA_NATIVE: frozenset[str] = frozenset(
    {".vtk", ".vtu", ".vtp", ".vts", ".vtr", ".vti", ".pvtu", ".pvtp"}
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

# Patch: meshio XDMF type map is missing PolyLine
if "PolyLine" not in _xdmf_common.xdmf_to_meshio_type:
    _xdmf_common.xdmf_to_meshio_type["PolyLine"] = "line"
    _xdmf_common.meshio_to_xdmf_type["line"] = ("PolyLine",)


# Internal utilities

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


# Format detection

def _detect_format(path: Path) -> str:
    """Return a format string for the given file path.

    Returns one of: pvd_timeseries, fenics_xdmf, timeseries_xdmf,
    pyvista_native, meshio_fallback.
    """
    suffix = path.suffix.lower()
    if suffix == ".pvd":
        return "pvd_timeseries"
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


# PVD helpers

def _parse_pvd(path: Path) -> list[tuple[float, Path]]:
    """Parse a PVD file and return (timestep, abs_vtu_path) pairs sorted by time."""
    tree = ET.parse(path)
    collection = tree.getroot().find("Collection")
    if collection is None:
        raise ValueError(f"No Collection element in {path.name}")
    entries = [
        (float(ds.get("timestep", "0")), path.parent / (ds.get("file") or ""))
        for ds in collection.findall("DataSet")
        if ds.get("file")
    ]
    return sorted(entries, key=lambda x: x[0])


# Metadata extraction

def get_metadata(path: Path) -> MeshMetadata:
    """Return a format-agnostic metadata descriptor for any supported mesh file.

    Caches the result as a .meta.json sidecar next to the source file.
    The sidecar is automatically regenerated if the MeshMetadata schema
    has changed since it was written (detected via schema_hash).
    """
    sidecar = path.with_suffix(".meta.json")

    if sidecar.exists():
        try:
            cached = MeshMetadata.model_validate_json(sidecar.read_text())
            if cached.schema_hash == MESH_METADATA_HASH:
                logger.debug(f"Cache hit: '{sidecar.name}'")
                return cached
            logger.debug(f"Schema changed, regenerating '{sidecar.name}'")
        except (ValueError, KeyError):
            logger.debug(f"Invalid sidecar, regenerating '{sidecar.name}'")

    logger.debug(f"Computing metadata for '{path.name}'")
    fmt = _detect_format(path)
    if fmt == "pvd_timeseries":
        raw = _metadata_pvd(path, fmt)
    elif fmt == "fenics_xdmf":
        raw = _metadata_fenics_xdmf(path, fmt)
    elif fmt == "timeseries_xdmf":
        raw = _metadata_timeseries_xdmf(path, fmt)
    else:
        raw = _metadata_static(path, fmt)

    raw["scalar_bounds"] = _compute_scalar_bounds(path, fmt, raw["fields"], raw["n_steps"])
    meta = MeshMetadata.model_validate({**raw, "schema_hash": MESH_METADATA_HASH})
    sidecar.write_text(meta.model_dump_json(indent=2))
    logger.debug(f"Cached metadata to '{sidecar.name}'")
    return meta


def _metadata_timeseries_xdmf(path: Path, fmt: str) -> dict:
    """Extract metadata from a meshio-style XDMF time series.

    Reads all steps to collect timestamps; field shapes are taken from step 0.
    """
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        points, cells = reader.read_points_cells()
        num_steps = reader.num_steps
        times: list[float] = []
        fields: dict[str, dict] = {}
        for step in range(num_steps):
            timestamp, point_data, cell_data = reader.read_data(step)
            times.append(float(timestamp))
            # Collect field shapes from the first step only
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


def _metadata_pvd(path: Path, fmt: str) -> dict:
    """Extract metadata from a PVD timeseries.

    Parses the PVD XML for timestep list; reads step 0 VTU for field shapes.
    """
    entries = _parse_pvd(path)
    times = [t for t, _ in entries]
    mesh = cast(pv.DataSet, pv.read(str(entries[0][1]))) if entries else pv.UnstructuredGrid()

    def _field_shape(arr: np.ndarray) -> list[int]:
        return list(arr.shape[1:]) if arr.ndim > 1 else [1]

    return {
        "format": fmt,
        "n_steps": len(entries),
        "times": times,
        "n_points": mesh.n_points,
        "n_cells": mesh.n_cells,
        "cell_types": [str(ct.name).lower() for ct in mesh.distinct_cell_types],
        "fields": {
            **{name: {"center": "point", "shape": _field_shape(arr)}
               for name, arr in mesh.point_data.items()},
            **{name: {"center": "cell", "shape": _field_shape(arr)}
               for name, arr in mesh.cell_data.items()},
        },
    }


def _metadata_fenics_xdmf(path: Path, fmt: str) -> dict:
    """Extract metadata from a FEniCS-style XDMF file via h5py.

    Reads the base Uniform grid for geometry dimensions, then iterates
    Temporal Collections to collect timestamps and per-field shapes.
    """
    domain, topology_elem, topo_item, geo_item = _parse_xdmf_base_grid(path)

    # Dimensions attribute is "n_rows n_cols"; first token is the count
    n_points  = int((geo_item.get("Dimensions") or "").split()[0])
    n_cells   = int((topo_item.get("Dimensions") or "").split()[0])
    cell_type = topology_elem.get("TopologyType", "unknown").lower()

    fields: dict[str, dict] = {}
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


def _metadata_static(path: Path, fmt: str) -> dict:
    """Extract metadata from a static (non-time-series) mesh file."""
    mesh = cast(
        pv.DataSet,
        pv.read(str(path))
        if path.suffix.lower() in _PYVISTA_NATIVE
        else pv.from_meshio(meshio.read(str(path))),
    )

    def _field_shape(arr: np.ndarray) -> list[int]:
        return list(arr.shape[1:]) if arr.ndim > 1 else [1]

    return {
        "format": fmt,
        "n_steps": 1,
        "times": [],
        "n_points": mesh.n_points,
        "n_cells": mesh.n_cells,
        "cell_types": [str(ct.name).lower() for ct in mesh.distinct_cell_types],
        "fields": {
            **{name: {"center": "point", "shape": _field_shape(arr)}
               for name, arr in mesh.point_data.items()},
            **{name: {"center": "cell", "shape": _field_shape(arr)}
               for name, arr in mesh.cell_data.items()},
        },
    }


# Global scalar bounds

def _compute_scalar_bounds(
    path: Path,
    fmt: str,
    fields: dict,
    n_steps: int,
) -> dict[str, list[float]]:
    """Return {field: [global_min, global_max]} for every scalar field across all timesteps.

    Called once during metadata extraction; result is persisted in the .meta.json sidecar.
    Only scalar fields (shape [1]) are scanned - vector/tensor fields are skipped.
    """
    scalar_fields = [name for name, info in fields.items() if info.get("shape") == [1]]
    if not scalar_fields:
        return {}

    logger.info(f"Computing global scalar bounds for '{path.name}' ({n_steps} step(s))…")

    bounds: dict[str, list[float]] = {
        name: [float("inf"), float("-inf")] for name in scalar_fields
    }

    def _update(name: str, arr: np.ndarray) -> None:
        bounds[name][0] = min(bounds[name][0], float(arr.min()))
        bounds[name][1] = max(bounds[name][1], float(arr.max()))

    if fmt == "timeseries_xdmf":
        with meshio.xdmf.TimeSeriesReader(path) as reader:
            reader.read_points_cells()  # required initialisation before read_data()
            for step in range(n_steps):
                try:
                    _, point_data, cell_data = reader.read_data(step)
                except Exception:
                    continue
                for name in scalar_fields:
                    data = point_data.get(name)
                    if data is None:
                        blocks = cell_data.get(name)
                        data = blocks[0] if blocks else None
                    if data is not None:
                        _update(name, data)

    elif fmt == "fenics_xdmf":
        domain, _, _, _ = _parse_xdmf_base_grid(path)
        temporal_grids = [
            g for g in domain.findall("Grid")
            if g.get("CollectionType") == "Temporal"
        ]
        h5_file = path.parent / (path.stem + ".h5")
        with h5py.File(str(h5_file), "r") as hdf5:
            for collection in temporal_grids:
                field_name = collection.get("Name")
                if field_name not in bounds:
                    continue
                for child in collection.findall("Grid"):
                    attr = child.find("Attribute")
                    if attr is None:
                        continue
                    data_item = attr.find("DataItem")
                    if data_item is None:
                        continue
                    hdf5_key = (data_item.text or "").strip().split(":/")[1]
                    try:
                        _update(field_name, hdf5[hdf5_key][:])
                    except KeyError:
                        pass

    elif fmt == "pvd_timeseries":
        for _, vtu_path in _parse_pvd(path):
            try:
                mesh = cast(pv.DataSet, pv.read(str(vtu_path)))
                for name in scalar_fields:
                    try:
                        lo, hi = mesh.get_data_range(name)
                        bounds[name][0] = min(bounds[name][0], float(lo))
                        bounds[name][1] = max(bounds[name][1], float(hi))
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Skipping '{vtu_path.name}' during bounds scan: {e}")

    else:
        # Static / single-step - load once
        try:
            mesh = _load_static(path)
            for name in scalar_fields:
                try:
                    lo, hi = mesh.get_data_range(name)
                    bounds[name][0] = float(lo)
                    bounds[name][1] = float(hi)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to load '{path.name}' for bounds scan: {e}")

    # Drop any field whose bounds could not be determined
    return {
        name: b for name, b in bounds.items()
        if b[0] != float("inf") and b[1] != float("-inf")
    }


# Mesh loaders

def _load_pvd(path: Path, step: int = 0) -> pv.DataSet:
    """Load one VTU from a PVD timeseries by step index."""
    entries = _parse_pvd(path)
    if not entries:
        raise ValueError(f"PVD file has no DataSet entries: {path.name}")
    if step >= len(entries):
        logger.warning(f"Step {step} out of range ({len(entries)} steps), using last.")
        step = len(entries) - 1
    _, vtu_path = entries[step]
    logger.debug(f"[pvd] loading step {step}: '{vtu_path.name}'")
    return cast(pv.DataSet, pv.read(str(vtu_path)))


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


def load_mesh(path: Path, step: int = 0) -> pv.DataSet:
    """Load any supported mesh file and return a PyVista dataset.

    Dispatches to the correct private loader based on detected format.
    All fields at the given timestep are attached to the returned mesh.
    """
    fmt = _detect_format(path)
    logger.debug(f"Loading '{path.name}' as '{fmt}' step {step}")
    if fmt == "pvd_timeseries":
        return _load_pvd(path, step)
    if fmt == "fenics_xdmf":
        return _load_fenics_xdmf(path, step)
    if fmt == "timeseries_xdmf":
        return _load_timeseries_xdmf(path, step)
    return _load_static(path)

def parse_labels_file(path: Path) -> dict[str, dict[int, list[str]]]:
    """Parse a LabelIDs.txt file into per-mesh material ID → name mappings.

    Returns dict keyed by mesh filename (e.g. 'M.vtu'), each value
    is a dict of MaterialID -> list of anatomical names (multiple structures
    can share one MaterialID).
    """
    import re

    # Accumulate all names per material ID before joining
    raw: dict[str, dict[int, list[str]]] = {}
    current_mesh: str | None = None

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "Array explanation" in line:
            current_mesh = line.split()[0]
            raw[current_mesh] = {}
            continue
        if "Anatomical Structure" in line or current_mesh is None:
            continue

        parts = re.split(r"\t+", line)
        if len(parts) < 3:
            continue

        name = parts[0].strip()
        for mid_str in parts[2].strip().split(","):
            mid_str = mid_str.strip()
            if mid_str.isdigit():
                mid = int(mid_str)
                raw[current_mesh].setdefault(mid, [])
                if name not in raw[current_mesh][mid]:
                    raw[current_mesh][mid].append(name)

    return {
        mesh: dict(ids)
        for mesh, ids in raw.items()
    }