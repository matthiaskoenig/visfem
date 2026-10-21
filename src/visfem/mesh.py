"""Mesh loading and metadata extraction for FEM simulation data."""

import contextlib
import re
import threading
import warnings
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from vtkmodules.vtkIOLSDyna import vtkLSDynaReader

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
    "line": 1,
    "line3": 1,
    "line4": 1,
    "triangle": 2,
    "triangle6": 2,
    "triangle10": 2,
    "quad": 2,
    "quad8": 2,
    "quad9": 2,
    "tetra": 3,
    "tetra10": 3,
    "tetra20": 3,
    "hexahedron": 3,
    "hexahedron20": 3,
    "hexahedron27": 3,
    "wedge": 3,
    "wedge15": 3,
    "wedge18": 3,
    "pyramid": 3,
    "pyramid13": 3,
    "pyramid14": 3,
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

# Add PolyLine to meshio's XDMF type map
if "PolyLine" not in _xdmf_common.xdmf_to_meshio_type:
    _xdmf_common.xdmf_to_meshio_type["PolyLine"] = "line"
    _xdmf_common.meshio_to_xdmf_type["line"] = ("PolyLine",)


# Mesh caches: static meshes and time-series steps are kept for the life of the process
_static_cache: dict[Path, pv.DataSet] = {}
_step_cache: dict[tuple[Path, int], pv.DataSet] = {}
_step_cache_lock: threading.Lock = threading.Lock()


# Internal utilities


def _require(element: ET.Element | None, tag: str, context: str) -> ET.Element:
    """Return *element*, or raise ValueError naming *tag* and *context* when it is None."""
    if element is None:
        raise ValueError(f"Missing required XML element <{tag}> in {context}")
    return element


def _hdf5_key(item: ET.Element) -> str:
    """Return the HDF5 dataset path of an XDMF DataItem *item* whose text reads "file.h5:/path/to/dataset"."""
    return (item.text or "").strip().split(":/", 1)[-1]


_path_locks: dict[Path, threading.Lock] = {}
_path_locks_lock = threading.Lock()


def _path_lock(key: Path) -> threading.Lock:
    """Return the lock registered for *key* (a d3plot directory or an XDMF file), creating it on first use."""
    with _path_locks_lock:
        return _path_locks.setdefault(key, threading.Lock())


def _filter_to_max_dim_cells(cells: list) -> list:
    """Return the highest-dimensional cell blocks of *cells*."""
    if not cells:
        return cells
    # Lower-dimensional boundary marker blocks crash pv.from_meshio()
    max_dim = max(_CELL_DIM.get(block.type, 0) for block in cells)
    filtered = [block for block in cells if _CELL_DIM.get(block.type, 0) == max_dim]
    dropped = [block.type for block in cells if _CELL_DIM.get(block.type, 0) < max_dim]
    if dropped:
        logger.debug(f"Filtered out lower-dimensional cell blocks: {dropped}")
    return filtered


def _parse_xdmf_base_grid(
    path: Path,
) -> tuple[ET.Element, ET.Element, ET.Element, ET.Element]:
    """Return (domain, topology, topology DataItem, geometry DataItem) from the base Uniform grid of the XDMF file at *path*."""
    tree = ET.parse(path)
    domain = _require(tree.getroot().find("Domain"), "Domain", path.name)
    uniform = next(g for g in domain.findall("Grid") if g.get("GridType") == "Uniform")
    topology_elem = _require(uniform.find("Topology"), "Topology", path.name)
    topo_item = _require(topology_elem.find("DataItem"), "DataItem", path.name)
    geo_item = _require(
        _require(uniform.find("Geometry"), "Geometry", path.name).find("DataItem"),
        "DataItem",
        path.name,
    )
    return domain, topology_elem, topo_item, geo_item


def _temporal_grids(domain: ET.Element) -> list[ET.Element]:
    """Return the Temporal Collection grids of the XDMF *domain* element."""
    return [g for g in domain.findall("Grid") if g.get("CollectionType") == "Temporal"]


# Format detection

_format_cache: dict[Path, str] = {}


def _detect_format(path: Path) -> str:
    """Return the format string of *path*, memoised per path for the life of the process."""
    # Sniffing parses the whole XDMF manifest (~0.15 s for a 6.6 MB series); load_mesh sniffs on every call
    fmt = _format_cache.get(path)
    if fmt is None:
        fmt = _format_cache[path] = _sniff_format(path)
    return fmt


def _sniff_format(path: Path) -> str:
    """Return the format of *path*: a directory holding a ``d3plot`` master file is an LS-DYNA d3plot database, every other format follows the suffix."""
    if path.is_dir() and (path / _LSDYNA_MASTER).exists():
        return "lsdyna_d3plot"
    suffix = path.suffix.lower()
    if suffix == ".pvd":
        return "pvd_timeseries"
    if suffix in _PYVISTA_NATIVE:
        return "pyvista_native"
    if suffix in _XDMF_EXTENSIONS:
        return _detect_xdmf_subtype(path)
    return "meshio_fallback"


def _detect_xdmf_subtype(path: Path) -> str:
    """Return "fenics_xdmf" (one Temporal Collection per field, or none) or "timeseries_xdmf" (one collection for all fields) for the XDMF file at *path*."""
    tree = ET.parse(path)
    domain = _require(tree.getroot().find("Domain"), "Domain", path.name)
    temporal_collections = _temporal_grids(domain)
    if len(temporal_collections) > 1:
        return "fenics_xdmf"
    if len(temporal_collections) == 1:
        return "timeseries_xdmf"
    # Zero temporal collections: a static FEniCS geometry file
    return "fenics_xdmf"


# PVD helpers


def pvd_steps(path: Path) -> list[tuple[float, Path]]:
    """Return the (timestep, absolute vtu_path) pairs of the PVD file at *path*, sorted by time."""
    tree = ET.parse(path)
    collection = _require(tree.getroot().find("Collection"), "Collection", path.name)
    entries = [
        (float(ds.get("timestep", "0")), path.parent / (ds.get("file") or ""))
        for ds in collection.findall("DataSet")
        if ds.get("file")
    ]
    return sorted(entries, key=lambda x: x[0])


# Flat VTK series helpers


def _natural_key(name: str) -> list:
    """Return a sort key for *name* that orders embedded numbers numerically (stimulus_2 < stimulus_10)."""
    return [int(tok) if tok.isdigit() else tok for tok in re.split(r"(\d+)", name)]


def vtk_series_steps(ddir: Path, pattern: str) -> list[tuple[float, Path]]:
    """Return (step_index, path) pairs for the files matching *pattern* under *ddir*, in natural sort order."""
    files = sorted(ddir.glob(pattern), key=lambda p: _natural_key(p.name))
    # The step index is the timeline value; filenames may encode several axes
    return [(float(i), p) for i, p in enumerate(files)]


# LS-DYNA d3plot helpers

# The master file; the database directory holds it plus sequential parts
_LSDYNA_MASTER = "d3plot"
# One reader per directory: vtkLSDynaReader streams one timestep at a time and is costly to instantiate
_lsdyna_readers: dict[Path, "vtkLSDynaReader"] = {}
# Step times per directory, memoised at reader creation; a frame read under the non-reentrant lock reads them directly
_lsdyna_times: dict[Path, list[float]] = {}


def _lsdyna_reader(ddir: Path) -> "vtkLSDynaReader":
    """Return the vtkLSDynaReader for *ddir*, created with its step times memoised on first use; call under _path_lock(ddir)."""
    reader = _lsdyna_readers.get(ddir)
    if reader is None:
        from vtkmodules.vtkCommonExecutionModel import (
            vtkStreamingDemandDrivenPipeline as _SDDP,
        )
        from vtkmodules.vtkIOLSDyna import vtkLSDynaReader

        reader = vtkLSDynaReader()
        reader.SetDatabaseDirectory(str(ddir))
        reader.UpdateInformation()
        info = reader.GetOutputInformation(0)
        n = info.Length(_SDDP.TIME_STEPS())
        _lsdyna_times[ddir] = [float(info.Get(_SDDP.TIME_STEPS(), i)) for i in range(n)]
        _lsdyna_readers[ddir] = reader
    return reader


def lsdyna_steps(ddir: Path) -> list[float]:
    """Return the timestep values of the d3plot database at *ddir*."""
    with _path_lock(ddir):
        _lsdyna_reader(ddir)  # memoises the step times
        return list(_lsdyna_times[ddir])


def _load_d3plot_frame(ddir: Path, step: int = 0) -> pv.DataSet:
    """Return timestep *step* of the d3plot database at *ddir* as one combined UnstructuredGrid."""
    from vtkmodules.vtkCommonExecutionModel import (
        vtkStreamingDemandDrivenPipeline as _SDDP,
    )

    # UPDATE_TIME_STEP + Update mutates the reader's shared output; one frame read at a time
    with _path_lock(ddir):
        reader = _lsdyna_reader(ddir)
        times = _lsdyna_times[ddir]
        step = max(0, min(step, len(times) - 1))
        info = reader.GetOutputInformation(0)
        info.Set(_SDDP.UPDATE_TIME_STEP(), times[step])
        reader.Update()
        combined = pv.wrap(reader.GetOutput()).combine()  # MultiBlock -> one grid
    return cast(pv.DataSet, combined)


# Metadata extraction


def _sidecar_cached(sidecar: Path, build: Callable[[], dict]) -> MeshMetadata:
    """Return the MeshMetadata stored in *sidecar* when its schema hash is current, else validate the raw dict *build* returns, write it to *sidecar* and return it."""
    if sidecar.exists():
        try:
            cached = MeshMetadata.model_validate_json(
                sidecar.read_text(encoding="utf-8")
            )
            if cached.schema_hash == MESH_METADATA_HASH:
                logger.debug(f"Cache hit: '{sidecar.name}'")
                return cached
            logger.debug(f"Schema changed, regenerating '{sidecar.name}'")
        except (ValueError, KeyError):
            logger.debug(f"Invalid sidecar, regenerating '{sidecar.name}'")

    meta = MeshMetadata.model_validate({**build(), "schema_hash": MESH_METADATA_HASH})
    try:
        sidecar.write_text(meta.model_dump_json(indent=2))
        logger.debug(f"Cached metadata to '{sidecar.name}'")
    except OSError as e:
        # A read-only data mount fails the write; the sidecar is rebuilt on the next start
        logger.warning(f"Sidecar write failed for '{sidecar.name}': {e}")
    return meta


def get_metadata(path: Path) -> MeshMetadata:
    """Return the MeshMetadata of the mesh at *path*, cached as a .meta.json sidecar keyed on the schema hash."""
    return _sidecar_cached(path.with_suffix(".meta.json"), lambda: _raw_metadata(path))


def _raw_metadata(path: Path) -> dict:
    """Return the raw metadata dict of *path*: the format-specific summary completed with global scalar bounds."""
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

    raw["scalar_bounds"] = _compute_scalar_bounds(
        path, fmt, raw["fields"], raw["n_steps"]
    )
    return raw


def _field_shape(shape: tuple[int, ...]) -> list[int]:
    """Return the per-row component shape of an array of *shape*: the axes after the leading row axis, or [1] for a flat array."""
    return list(shape[1:]) or [1]


def _mesh_summary(mesh: pv.DataSet) -> dict:
    """Return the n_points, n_cells, cell_types and fields ({name: {center, shape}}) metadata entries of *mesh*."""
    return {
        "n_points": mesh.n_points,
        "n_cells": mesh.n_cells,
        "cell_types": [str(ct.name).lower() for ct in mesh.distinct_cell_types],
        "fields": {
            **{
                name: {"center": "point", "shape": _field_shape(arr.shape)}
                for name, arr in mesh.point_data.items()
            },
            **{
                name: {"center": "cell", "shape": _field_shape(arr.shape)}
                for name, arr in mesh.cell_data.items()
            },
        },
    }


def _metadata_timeseries_xdmf(path: Path, fmt: str) -> dict:
    """Return the raw metadata dict of the meshio-style XDMF time series at *path* with format *fmt*."""
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        points, cells = reader.read_points_cells()
        num_steps = reader.num_steps
        times: list[float] = []
        fields: dict[str, dict] = {}
        for step in range(num_steps):
            timestamp, point_data, cell_data = reader.read_data(step)
            times.append(float(timestamp))
            # Field shapes come from the first step
            if not fields:
                for name, arr in point_data.items():
                    fields[name] = {
                        "center": "point",
                        "shape": _field_shape(arr.shape),
                    }
                for name, blocks in cell_data.items():
                    fields[name] = {
                        "center": "cell",
                        "shape": _field_shape(blocks[0].shape),
                    }
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
    """Return the raw metadata dict of the PVD series at *path* with format *fmt*: timesteps from the PVD XML, geometry and fields from the step-0 VTU."""
    entries = pvd_steps(path)
    times = [t for t, _ in entries]
    mesh = (
        cast(pv.DataSet, pv.read(str(entries[0][1])))
        if entries
        else pv.UnstructuredGrid()
    )
    return {
        "format": fmt,
        "n_steps": len(entries),
        "times": times,
        **_mesh_summary(mesh),
    }


def _metadata_fenics_xdmf(path: Path, fmt: str) -> dict:
    """Return the raw metadata dict of the FEniCS-style XDMF file at *path* with format *fmt*: geometry from the base grid, timestamps and field shapes from the HDF5 companion."""
    domain, topology_elem, topo_item, geo_item = _parse_xdmf_base_grid(path)

    # Dimensions attribute is "n_rows n_cols"; first token is the count
    n_points = int((geo_item.get("Dimensions") or "").split()[0])
    n_cells = int((topo_item.get("Dimensions") or "").split()[0])
    cell_type = topology_elem.get("TopologyType", "unknown").lower()

    fields: dict[str, dict] = {}
    times: list[float] = []

    with h5py.File(str(path.with_suffix(".h5")), "r") as hdf5:
        for collection in _temporal_grids(domain):
            field_name = collection.get("Name")
            if field_name is None:
                continue
            # Timestamps are identical across fields; the first collection supplies them
            if not times:
                for child in collection.findall("Grid"):
                    t_elem = child.find("Time")
                    if t_elem is not None:
                        value = t_elem.get("Value")
                        if value is not None:
                            times.append(float(value))
            # Center and array shape come from step 0 of this field
            first_child = collection.find("Grid")
            if first_child is not None:
                attr = first_child.find("Attribute")
                if attr is not None:
                    center = attr.get("Center", "Node").lower()
                    center = "point" if center == "node" else "cell"
                    data_item = attr.find("DataItem")
                    if data_item is not None:
                        try:
                            shape = _field_shape(hdf5[_hdf5_key(data_item)].shape)
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
    """Return the raw metadata dict of the single-step mesh file at *path* with format *fmt*."""
    mesh = cast(
        pv.DataSet,
        pv.read(str(path))
        if path.suffix.lower() in _PYVISTA_NATIVE
        else pv.from_meshio(meshio.read(str(path))),
    )
    return {"format": fmt, "n_steps": 1, "times": [], **_mesh_summary(mesh)}


def metadata_for_series(paths: list[Path]) -> MeshMetadata:
    """Return MeshMetadata for the flat VTK series *paths*, the ordered list of per-step files, computed in memory."""
    if not paths:
        raise ValueError("metadata_for_series needs at least one file")

    base = _metadata_static(paths[0], "vtk_series")
    base["n_steps"] = len(paths)
    base["times"] = [float(i) for i in range(len(paths))]

    fields = _boundable_fields(base["fields"])
    if fields:
        logger.info(
            f"Computing global field bounds for VTK series ({len(paths)} frames)…"
        )
        frames = (cast(pv.DataSet, pv.read(str(p))) for p in paths)
        base["scalar_bounds"] = _accumulate_bounds(
            fields, _mesh_samples(frames, fields)
        )

    # A sidecar anchors to one file; the metadata of a many-file series stays in memory
    return MeshMetadata(schema_hash=MESH_METADATA_HASH, **base)


def metadata_for_d3plot(ddir: Path) -> MeshMetadata:
    """Return MeshMetadata for the LS-DYNA d3plot database at *ddir*, cached as ``<ddir>/d3plot.meta.json`` keyed on the schema hash."""
    return _sidecar_cached(
        ddir / "d3plot.meta.json", lambda: _raw_d3plot_metadata(ddir)
    )


def _raw_d3plot_metadata(ddir: Path) -> dict:
    """Return the raw metadata dict of the d3plot database at *ddir*: frame-0 geometry and fields, reader timesteps and global bounds over every frame."""
    times = lsdyna_steps(ddir)
    frame0 = _load_d3plot_frame(ddir, 0)
    base: dict = {
        "format": "lsdyna_d3plot",
        "n_steps": len(times),
        "times": times,
        **_mesh_summary(frame0),
    }

    fields = _boundable_fields(base["fields"])
    if fields:
        logger.info(f"Computing global field bounds for d3plot ({len(times)} frames)…")
        # The scan reads every frame (~0.3 s each)
        frames = (_load_d3plot_frame(ddir, k) for k in range(len(times)))
        base["scalar_bounds"] = _accumulate_bounds(
            fields, _mesh_samples(frames, fields)
        )
    return base


# Global scalar bounds


# Bounds cover scalar fields (shape [1]) and the magnitude |v| of vector fields (shape [3]); the colour ramp holds while scrubbing


def _boundable_fields(fields: dict) -> list[str]:
    """Return the scalar (shape [1]) and 3-vector (shape [3]) field names of *fields*."""
    return [n for n, info in fields.items() if info.get("shape") in ([1], [3])]


def _array_minmax(arr: np.ndarray) -> tuple[float, float]:
    """Return (min, max) of *arr*, of its per-row magnitude for a 3-vector array."""
    if arr.ndim == 2 and arr.shape[1] == 3:
        mag = np.linalg.norm(arr, axis=1)
        return float(mag.min()), float(mag.max())
    return float(arr.min()), float(arr.max())


def _mesh_array(mesh: pv.DataSet, name: str) -> "np.ndarray | None":
    """Return the point or cell array *name* of *mesh*, or None."""
    arr = mesh.point_data.get(name)
    if arr is None:
        arr = mesh.cell_data.get(name)
    return arr


# One bounds sample: a field name with the min and max of one frame of it
_Sample = tuple[str, float, float]


def _mesh_samples(meshes: Iterable[pv.DataSet], names: list[str]) -> Iterator[_Sample]:
    """Yield (name, lo, hi) for every field of *names* found as point or cell data on each mesh of *meshes*."""
    for mesh in meshes:
        for name in names:
            arr = _mesh_array(mesh, name)
            if arr is not None:
                lo, hi = _array_minmax(arr)
                yield name, lo, hi


def _accumulate_bounds(
    names: list[str], samples: Iterable[_Sample]
) -> dict[str, list[float]]:
    """Fold (name, lo, hi) *samples* into {name: [global_min, global_max]} over *names*, keeping only names that received a finite sample."""
    bounds = {n: [float("inf"), float("-inf")] for n in names}
    for name, lo, hi in samples:
        bounds[name][0] = min(bounds[name][0], lo)
        bounds[name][1] = max(bounds[name][1], hi)
    return {
        n: b
        for n, b in bounds.items()
        if b[0] != float("inf") and b[1] != float("-inf")
    }


def _timeseries_xdmf_samples(
    path: Path, names: list[str], n_steps: int
) -> Iterator[_Sample]:
    """Yield (name, lo, hi) for the fields of *names* at every readable step of the meshio-style XDMF series *path*."""
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        reader.read_points_cells()  # initialises the reader for read_data()
        for step in range(n_steps):
            try:
                _, point_data, cell_data = reader.read_data(step)
            except Exception:  # noqa: BLE001 - an unreadable step is skipped and the bounds scan continues
                continue
            for name in names:
                data = point_data.get(name)
                if data is None:
                    blocks = cell_data.get(name)
                    data = blocks[0] if blocks else None
                if data is not None:
                    lo, hi = _array_minmax(data)
                    yield name, lo, hi


def _fenics_xdmf_samples(path: Path, names: list[str]) -> Iterator[_Sample]:
    """Yield (name, lo, hi) for the fields of *names* at every step of the FEniCS-style XDMF file *path*, read from its HDF5 companion."""
    domain, _, _, _ = _parse_xdmf_base_grid(path)
    wanted = set(names)
    with h5py.File(str(path.with_suffix(".h5")), "r") as hdf5:
        for collection in _temporal_grids(domain):
            field_name = collection.get("Name")
            if field_name not in wanted:
                continue
            for child in collection.findall("Grid"):
                attr = child.find("Attribute")
                if attr is None:
                    continue
                data_item = attr.find("DataItem")
                if data_item is None:
                    continue
                with contextlib.suppress(KeyError):  # field absent at this step
                    lo, hi = _array_minmax(hdf5[_hdf5_key(data_item)][:])
                    yield field_name, lo, hi


def _pvd_samples(path: Path, names: list[str]) -> Iterator[_Sample]:
    """Yield (name, lo, hi) for the fields of *names* on every VTU of the PVD series *path*, logging and skipping a file that fails."""
    for _, vtu_path in pvd_steps(path):
        try:
            mesh = cast(pv.DataSet, pv.read(str(vtu_path)))
            yield from _mesh_samples([mesh], names)
        except Exception as e:  # noqa: BLE001 - an unreadable file is logged and the bounds scan continues
            logger.warning(f"Skipping '{vtu_path.name}' during bounds scan: {e}")


def _static_samples(path: Path, names: list[str]) -> Iterator[_Sample]:
    """Yield (name, lo, hi) for the fields of *names* on the static mesh *path*, logging a warning when it fails to load."""
    try:
        mesh = _load_static(path)
        yield from _mesh_samples([mesh], names)
    except Exception as e:  # noqa: BLE001 - bounds are optional; the mesh may still render
        logger.warning(f"Failed to load '{path.name}' for bounds scan: {e}")


def _compute_scalar_bounds(
    path: Path,
    fmt: str,
    fields: dict,
    n_steps: int,
) -> dict[str, list[float]]:
    """Return {field: [global_min, global_max]} over the *n_steps* timesteps of the *fmt* mesh at *path* for the scalar and vector fields in *fields*."""
    boundable = _boundable_fields(fields)
    if not boundable:
        return {}

    logger.info(f"Computing global field bounds for '{path.name}' ({n_steps} step(s))…")

    if fmt == "timeseries_xdmf":
        samples = _timeseries_xdmf_samples(path, boundable, n_steps)
    elif fmt == "fenics_xdmf":
        samples = _fenics_xdmf_samples(path, boundable)
    elif fmt == "pvd_timeseries":
        samples = _pvd_samples(path, boundable)
    else:
        samples = _static_samples(path, boundable)
    return _accumulate_bounds(boundable, samples)


# Mesh loaders


def _load_pvd(path: Path, step: int = 0) -> pv.DataSet:
    """Return the VTU at index *step* of the PVD series at *path*."""
    entries = pvd_steps(path)
    if not entries:
        raise ValueError(f"PVD file lists zero DataSet entries: {path.name}")
    if step >= len(entries):
        logger.warning(f"Step {step} out of range ({len(entries)} steps), using last.")
        step = len(entries) - 1
    _, vtu_path = entries[step]
    logger.debug(f"[pvd] loading step {step}: '{vtu_path.name}'")
    return cast(pv.DataSet, pv.read(str(vtu_path)))


def _load_fenics_xdmf(path: Path, step: int = 0) -> pv.UnstructuredGrid:
    """Return timestep *step* of the FEniCS-style XDMF file at *path*: the HDF5 geometry with every field's array at *step* attached."""
    domain, topology_elem, topo_item, geo_item = _parse_xdmf_base_grid(path)

    topo_type_raw = topology_elem.get("TopologyType", "").lower()
    topo_type = _XDMF_TO_MESHIO_CELLTYPE.get(topo_type_raw, topo_type_raw)

    with h5py.File(str(path.with_suffix(".h5")), "r") as hdf5:
        points_2d = hdf5[_hdf5_key(geo_item)][:]
        connectivity = hdf5[_hdf5_key(topo_item)][:]

        # FEniCS 2D meshes store two columns; PyVista needs a zero z column
        if points_2d.shape[1] == 2:
            points = np.column_stack([points_2d, np.zeros(len(points_2d))])
        else:
            points = points_2d

        # Build the base mesh from the geometry
        cells = _filter_to_max_dim_cells([meshio.CellBlock(topo_type, connectivity)])
        pvmesh = pv.from_meshio(meshio.Mesh(points=points, cells=cells))

        # Each Temporal Collection is one field; attach each at *step*
        for collection in _temporal_grids(domain):
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
            hdf5_key = _hdf5_key(data_item)
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
                logger.warning(
                    f"HDF5 key '{hdf5_key}' missing, skipping field '{field_name}'."
                )

    logger.debug(
        f"Loaded '{path.name}' step {step}: "
        f"{pvmesh.n_points} points, {pvmesh.n_cells} cells, "
        f"fields: {list(pvmesh.point_data.keys()) + list(pvmesh.cell_data.keys())}"
    )
    return pvmesh


# meshio-style XDMF time series readers

# One reader per file for the life of the process: construction parses the whole XML manifest and read_points_cells re-reads the geometry, ~0.3 s against ~0.01 s for a frame's arrays
_XdmfEntry = tuple["meshio.xdmf.TimeSeriesReader", np.ndarray, list]
_xdmf_readers: dict[Path, _XdmfEntry] = {}


def _xdmf_reader(path: Path) -> _XdmfEntry:
    """Return the cached (reader, points, cells) for *path* (call under _path_lock(path))."""
    entry = _xdmf_readers.get(path)
    if entry is None:
        reader = meshio.xdmf.TimeSeriesReader(path)
        logger.debug(f"Opening '{path.name}' ({reader.num_steps} steps)")
        points, cells = reader.read_points_cells()
        entry = _xdmf_readers[path] = (reader, points, _filter_to_max_dim_cells(cells))
    return entry


def _load_timeseries_xdmf(path: Path, step: int = 0) -> pv.UnstructuredGrid:
    """Return timestep *step* of the meshio-style XDMF time series at *path*."""
    with _path_lock(path):  # the reader's h5py handle serves one thread at a time
        reader, points, cells = _xdmf_reader(path)
        _timestamp, point_data, cell_data = reader.read_data(step)
    mesh = meshio.Mesh(
        points=points,
        cells=cells,
        point_data=point_data,
        cell_data=cell_data,
    )
    return pv.from_meshio(mesh)


def _load_static(path: Path) -> pv.DataSet:
    """Return the static mesh at *path*, read by PyVista for native formats and by meshio for the rest."""
    if path.suffix.lower() in _PYVISTA_NATIVE:
        logger.debug(f"[pyvista] loading '{path.name}'")
        return cast(pv.DataSet, pv.read(str(path)))
    logger.debug(f"[meshio] loading '{path.name}'")
    # meshio's STL probe computes 84 + num_triangles * 50 in a fixed-width int; large STLs overflow it with a benign RuntimeWarning
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="overflow encountered in scalar multiply",
            category=RuntimeWarning,
        )
        return pv.from_meshio(meshio.read(str(path)))


def _detached_copy(cached: pv.DataSet) -> pv.DataSet:
    """Return a deep copy of *cached* that owns all of its buffers."""
    return cached.copy(deep=True)


def load_mesh(path: Path, step: int = 0) -> pv.DataSet:
    """Return timestep *step* of the mesh at *path* (a file or a d3plot database directory) as a detached PyVista dataset."""
    fmt = _detect_format(path)
    logger.debug(f"Loading '{path.name}' as '{fmt}' step {step}")

    if fmt in ("pyvista_native", "meshio_fallback"):
        if path not in _static_cache:
            logger.info(f"[mesh cache miss] loading '{path.name}' from disk")
            _static_cache[path] = _load_static(path)
        else:
            logger.info(f"[mesh cache hit] '{path.name}' served from memory")
        return _detached_copy(_static_cache[path])

    key = (path, step)
    with _step_cache_lock:
        if key in _step_cache:
            logger.info(
                f"[mesh cache hit] '{path.name}' step {step} served from memory"
            )
            return _detached_copy(_step_cache[key])

    logger.info(f"[mesh cache miss] loading '{path.name}' step {step} from disk")
    if fmt == "pvd_timeseries":
        mesh = _load_pvd(path, step)
    elif fmt == "fenics_xdmf":
        mesh = _load_fenics_xdmf(path, step)
    elif fmt == "lsdyna_d3plot":
        mesh = _load_d3plot_frame(path, step)
    else:
        mesh = _load_timeseries_xdmf(path, step)
    with _step_cache_lock:
        _step_cache[key] = mesh
    return _detached_copy(mesh)


# Skins: the PolyData the mapper gets for a volume mesh

# trame-vtk runs vtkDataSetSurfaceFilter over every mapper input other than PolyData on every push to the browser (~2.5 s per push for an 800k-cell quadratic tibia volume, several pushes per click); a cached skin makes a push cost milliseconds
Skin = tuple[pv.PolyData, np.ndarray | None, np.ndarray | None]
_skin_cache: dict[Path, Skin] = {}  # one skin per file


def as_surface(mesh: pv.DataSet) -> pv.PolyData:
    """Return *mesh* as PolyData: a surface passes through, a volume is skinned with its point and cell arrays."""
    if isinstance(mesh, pv.PolyData):
        return mesh
    # Point and cell arrays carry over; the mapper fast paths read them
    return mesh.extract_surface(
        pass_pointid=False, pass_cellid=False, algorithm="dataset_surface"
    )


def skin_with_ids(mesh: pv.DataSet) -> Skin:
    """Return (skin, volume point ids, volume cell ids) for *mesh*, the ids mapping per-volume arrays (a new time step, a region remap) onto the skin; both id arrays are None when *mesh* already is a surface."""
    if isinstance(mesh, pv.PolyData):
        return mesh, None, None
    surface = mesh.extract_surface(
        pass_pointid=True, pass_cellid=True, algorithm="dataset_surface"
    )
    point_ids = np.asarray(surface.point_data.pop("vtkOriginalPointIds"))
    cell_ids = np.asarray(surface.cell_data.pop("vtkOriginalCellIds"))
    return surface, point_ids, cell_ids


def load_skin(path: Path) -> Skin:
    """Return the skin of the static mesh file at *path* with its volume ids, cached per path."""
    if path not in _skin_cache:
        _skin_cache[path] = skin_with_ids(load_mesh(path))
    surface, point_ids, cell_ids = _skin_cache[path]
    # The shallow copy shares the cached buffers and owns its attribute lists; arrays added to it stay out of the cache
    return surface.copy(deep=False), point_ids, cell_ids


def preload_all_meshes(project_metadata: dict) -> None:
    """Fill the mesh cache from every dataset in *project_metadata* at server startup."""
    from visfem.engine.discovery import dataset_dir, discover_xdmf, pvd_file_path

    logger.warning("Preloading meshes into cache...")
    for meta in project_metadata.values():
        ddir = dataset_dir(meta)

        # Static files (VTK, VTU, STL) in the dataset dir and its patient subdirs; per-phase VTUs (phase_NN.vtu) load through their PVD into the step cache
        for ext in (".vtk", ".vtu", ".stl"):
            for path in sorted(ddir.rglob(f"*{ext}")):
                if path.name.startswith("phase_") and path.suffix == ".vtu":
                    continue
                try:
                    load_mesh(path, 0)
                    logger.warning(f"  cached {path.name}")
                except Exception as e:  # noqa: BLE001 - preload is best effort
                    logger.warning(f"  failed {path.name}: {e}")

        # Per-patient PVD phase series (GRASP MRI): step 0 of each
        for phase_pvd in sorted(ddir.rglob("*.pvd")):
            try:
                load_mesh(phase_pvd, 0)
                logger.warning(
                    f"  cached {phase_pvd.parent.name}/{phase_pvd.name} step 0"
                )
            except Exception as e:  # noqa: BLE001 - preload is best effort
                logger.warning(f"  failed {phase_pvd.name}: {e}")

        # XDMF time-series: step 0 only
        for stem, path in discover_xdmf(ddir).items():
            try:
                load_mesh(path, 0)
                logger.warning(f"  cached {stem} step 0")
            except Exception as e:  # noqa: BLE001 - preload is best effort
                logger.warning(f"  failed {stem}: {e}")

        # PVD time-series: step 0 only
        pvd = pvd_file_path(meta)
        if pvd and pvd.exists():
            try:
                load_mesh(pvd, 0)
                logger.warning(f"  cached {pvd.stem} step 0")
            except Exception as e:  # noqa: BLE001 - preload is best effort
                logger.warning(f"  failed {pvd.stem}: {e}")

    logger.warning("Preload complete.")


def parse_labels_file(path: Path) -> dict[str, dict[int, list[str]]]:
    """Return {mesh: {material_id: [names]}} parsed from the LabelIDs.txt file at *path*."""
    # Names per material ID per mesh
    raw: dict[str, dict[int, list[str]]] = {}
    current_mesh: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
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

    return {mesh: dict(ids) for mesh, ids in raw.items()}
