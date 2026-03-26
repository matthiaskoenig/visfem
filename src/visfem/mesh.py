"""Mesh loading and visualization using meshio and PyVista."""

import logging
import math
from pathlib import Path

import meshio
import pyvista as pv

from visfem.log import get_logger

logger: logging.Logger = get_logger(__name__)


# Formats that PyVista can read natively
_PYVISTA_NATIVE: frozenset[str] = frozenset(
    {".vtk", ".vtu", ".vtp", ".vts", ".vtr", ".vti", ".pvd", ".pvtu", ".pvtp"}
)

# Formats that carry time-series data (need the TimeSeriesReader path)
_XDMF_TIMESERIES: frozenset[str] = frozenset({".xdmf", ".xmf"})


def load_mesh(path: Path, step: int = 0) -> pv.DataSet:
    """Load *any* supported mesh file and return a PyVista dataset."""
    suffix = path.suffix.lower()

    if suffix in _XDMF_TIMESERIES:
        logger.debug(f"[xdmf-timeseries] loading '{path.name}' step {step}")
        return load_mesh_from_timeseries(path, step)

    if suffix in _PYVISTA_NATIVE:
        logger.debug(f"[pyvista-native] loading '{path.name}'")
        return pv.read(str(path))

    # Fallback: let meshio handle anything else (.msh, .med, .stl, .ply, …)
    logger.debug(f"[meshio-fallback] loading '{path.name}'")
    return pv.from_meshio(meshio.read(str(path)))


def get_mesh_info(path: Path, step: int = 0) -> dict:
    """Return a summary dict with basic mesh metadata."""
    mesh = load_mesh(path, step=step)
    return {
        "path": str(path),
        "n_points": mesh.n_points,
        "n_cells": mesh.n_cells,
        "bounds": mesh.bounds,
        "point_fields": list(mesh.point_data.keys()),
        "cell_fields": list(mesh.cell_data.keys()),
        "format": path.suffix.lower(),
    }


def get_field_names(path: Path, step: int = 0) -> list[str]:
    """Read all available scalar field names from an XDMF time series file."""
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        reader.read_points_cells()
        _, point_data, cell_data = reader.read_data(step)
    return list(point_data.keys()) + list(cell_data.keys())


def load_mesh_from_timeseries(path: Path, step: int = 0) -> pv.UnstructuredGrid:
    """Load a single time step from an XDMF time series and convert to PyVista."""
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        logger.debug(f"Loading '{path.name}' — {reader.num_steps} time steps available")
        points, cells = reader.read_points_cells()
        t, point_data, cell_data = reader.read_data(step)
        mesh = meshio.Mesh(
            points=points,
            cells=cells,
            point_data=point_data,
            cell_data=cell_data,
        )
    return pv.from_meshio(mesh)


def plot_mesh(path: Path, step: int = 0, field: str | None = None) -> None:
    """Load and display a single mesh file."""
    pvmesh = load_mesh_from_timeseries(path, step)
    logger.info(f"Mesh: {path.name} (step {step})")
    logger.info(f"  Points: {pvmesh.n_points}")
    logger.info(f"  Cells:  {pvmesh.n_cells}")
    pvmesh.plot(scalars=field, show_edges=True)


def animate_mesh(
    path: Path,
    output_dir: Path,
    every_nth: int = 10,
    field: str | None = None,
) -> None:
    """Animate all time steps of a mesh file and save as GIF."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        points, cells = reader.read_points_cells()

        plotter = pv.Plotter()
        plotter.open_gif(output_dir / "mesh_animation.gif")

        for step in range(0, reader.num_steps, every_nth):
            t, point_data, cell_data = reader.read_data(step)
            mesh = meshio.Mesh(
                points=points,
                cells=cells,
                point_data=point_data,
                cell_data=cell_data,
            )
            pvmesh = pv.from_meshio(mesh)
            plotter.clear()
            plotter.add_mesh(pvmesh, scalars=field, show_edges=True)
            plotter.add_text(f"t = {t:.2f}", font_size=12)
            plotter.write_frame()

        plotter.close()


def _grid_shape(n: int) -> tuple[int, int]:
    """Compute the tightest (nrows, ncols) grid for n subplots, max 4 columns."""
    sqrt = int(math.isqrt(n))
    if sqrt * sqrt == n:
        return sqrt, sqrt
    ncols = min(n, 4)
    nrows = -(-n // ncols)  # ceiling division
    return nrows, ncols


def plot_all_resolutions(
    mesh_files: list[Path],
    step: int = 0,
    field: str | None = None,
) -> None:
    """Plot mesh resolutions in a dynamically sized grid with linked cameras."""
    n = len(mesh_files)
    if n == 0:
        logger.warning("No mesh files provided.")
        return

    nrows, ncols = _grid_shape(n)
    plotter = pv.Plotter(shape=(nrows, ncols))

    for i, mesh_path in enumerate(mesh_files):
        row = i // ncols
        col = i % ncols
        plotter.subplot(row, col)
        pvmesh = load_mesh_from_timeseries(mesh_path, step=step)
        plotter.add_mesh(pvmesh, scalars=field, show_edges=True)
        plotter.add_title(mesh_path.stem, font_size=8)
        logger.info(f"{mesh_path.stem}: {pvmesh.n_points} points, {pvmesh.n_cells} cells")

    # Fill any leftover empty subplots with a placeholder
    for j in range(n, nrows * ncols):
        plotter.subplot(j // ncols, j % ncols)
        plotter.add_text("-", font_size=10, color="gray")

    plotter.link_views()
    plotter.show()


def print_fields(path: Path, step: int = 0) -> None:
    """Print all available data fields in the mesh."""
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        reader.read_points_cells()
        _, point_data, cell_data = reader.read_data(step)
    logger.info("--- Point data (on nodes) ---")
    for name, data in point_data.items():
        logger.info(f"  {name}: shape {data.shape}")
    logger.info("--- Cell data (on cells) ---")
    for name, data in cell_data.items():
        logger.info(f"  {name}: shape {data[0].shape}")


def plot_scalar_fields(path: Path, step: int = 0) -> None:
    """Plot all scalar fields side by side in a dynamically sized grid."""
    pvmesh = load_mesh_from_timeseries(path, step)
    scalar_fields = get_field_names(path, step)
    nrows, ncols = _grid_shape(len(scalar_fields))
    plotter = pv.Plotter(shape=(nrows, ncols))
    for i, field in enumerate(scalar_fields):
        row = i // ncols
        col = i % ncols
        plotter.subplot(row, col)
        plotter.add_mesh(pvmesh, scalars=field, show_edges=True)
        plotter.add_title(field, font_size=8)
    plotter.link_views()
    plotter.show()


# 3D-IRCADb data functions

def _ircadb_vtk_dir(ircadb_dir: Path, patient: int) -> Path:
    """Resolve the MESHES_VTK directory for a given patient number (1–20)."""
    return ircadb_dir / f"3Dircadb1.{patient}" / "MESHES_VTK"


def print_ircadb_organs(ircadb_dir: Path, patient: int) -> None:
    """Print all available organ meshes for a patient."""
    vtk_dir = _ircadb_vtk_dir(ircadb_dir, patient)
    organs = sorted(f.stem for f in vtk_dir.glob("*.vtk"))
    logger.info(f"--- Patient {patient} — organs available ({len(organs)}) ---")
    for organ in organs:
        logger.info(f"  {organ}")


def plot_ircadb_organ(ircadb_dir: Path, patient: int, organ: str) -> None:
    """Load and display a single organ mesh for one patient."""
    path = _ircadb_vtk_dir(ircadb_dir, patient) / f"{organ}.vtk"
    pvmesh = load_mesh(path)
    logger.info(f"Patient {patient} — {organ}")
    logger.info(f"  Points: {pvmesh.n_points}")
    logger.info(f"  Cells:  {pvmesh.n_cells}")
    pvmesh.plot(show_edges=True)


def plot_ircadb_patient(
    ircadb_dir: Path,
    patient: int,
    organs: list[str] | None = None,
) -> None:
    """Plot all (or a subset of) organ meshes for one patient in a grid."""
    vtk_dir = _ircadb_vtk_dir(ircadb_dir, patient)

    if organs is None:
        vtk_files = sorted(vtk_dir.glob("*.vtk"))
    else:
        vtk_files = [vtk_dir / f"{organ}.vtk" for organ in organs]

    n = len(vtk_files)
    if n == 0:
        logger.warning(f"No organ meshes found for patient {patient}.")
        return

    nrows, ncols = _grid_shape(n)
    plotter = pv.Plotter(shape=(nrows, ncols))

    for i, f in enumerate(vtk_files):
        row = i // ncols
        col = i % ncols
        plotter.subplot(row, col)
        pvmesh = load_mesh(f)
        plotter.add_mesh(pvmesh, show_edges=True)
        plotter.add_title(f.stem, font_size=8)
        logger.info(f"{f.stem}: {pvmesh.n_points} points, {pvmesh.n_cells} cells")

    # Fill leftover empty subplots
    for j in range(n, nrows * ncols):
        plotter.subplot(j // ncols, j % ncols)
        plotter.add_text("-", font_size=10, color="gray")

    plotter.link_views()
    plotter.show()


if __name__ == "__main__":
    # ------ convergence_sixth (XDMF time-series) ------
    DATA_DIR = Path(__file__).parents[3] / "visfem_data" / "convergence_sixth" / "xdmf"
    OUTPUT_DIR = Path(__file__).parents[3] / "visfem_results"
    OUTPUT_DIR.mkdir(exist_ok=True)

    STEP = 150
    ANIMATE_EVERY_NTH = 10
    FIELD = None  # PyVista picks default; run print_fields() to see available ones
    # FIELD = "pressure"  # uncomment to select a specific field

    MESH_FILES = [
        DATA_DIR / "lobule_sixth_00005.xdmf",
        DATA_DIR / "lobule_sixth_000025.xdmf",
        DATA_DIR / "lobule_sixth_0000125.xdmf",
        DATA_DIR / "lobule_sixth_00000625.xdmf",
    ]

    # plot_mesh(MESH_FILES[1], step=STEP, field=FIELD)
    # animate_mesh(MESH_FILES[1], output_dir=OUTPUT_DIR, every_nth=ANIMATE_EVERY_NTH, field=FIELD)
    # plot_all_resolutions(MESH_FILES, step=STEP, field=FIELD)
    # print_fields(MESH_FILES[1], step=STEP)
    # plot_scalar_fields(MESH_FILES[1], step=STEP)

    # ------ 3D-IRCADb-01 (static VTK surface meshes) ------
    IRCADB_DIR = Path(__file__).parents[3] / "visfem_data" / "3Dircadb1"
    PATIENT_NR = 2   # change to any patient 1–20
    ORGAN = "liver"  # run print_ircadb_organs() first to see what's available

    print_ircadb_organs(IRCADB_DIR, PATIENT_NR)
    # plot_ircadb_organ(IRCADB_DIR, PATIENT_NR, organ=ORGAN)
    # plot_ircadb_patient(IRCADB_DIR, PATIENT_NR)
    plot_ircadb_patient(IRCADB_DIR, PATIENT_NR, organs=["liver", "livertumor"])