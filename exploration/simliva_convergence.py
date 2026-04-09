"""Exploratory script for the convergence_sixth dataset.

3D wedge mesh, timeseries_xdmf format, 4 mesh resolutions.
Fields include scalars, vectors (shape [3]) and tensors (shape [3,3]).
"""

import math
from pathlib import Path
from typing import Literal

import pyvista as pv

from plot_utils import animate_field, preview_field_animation  # noqa: F401
from visfem.mesh import get_metadata, load_mesh


# ---- Paths ----

_DATA_BASE      = Path(__file__).parents[1] / "data" / "fem_data"
CONVERGENCE_DIR = _DATA_BASE / "simliva" / "lobule_convergence"
OUTPUT_DIR      = Path(__file__).parents[1] / "data" / "results"

# Discover all XDMF files that have a matching .h5 — orphan files are silently skipped
MESH_FILES: dict[str, Path] = {
    p.stem: p
    for p in sorted(CONVERGENCE_DIR.glob("*.xdmf"))
    if p.with_suffix(".h5").exists()
}


def _grid_shape(n: int) -> tuple[int, int]:
    """Return a tight (nrows, ncols) grid shape for n subplots, max 4 columns."""
    sqrt = int(math.isqrt(n))
    if sqrt * sqrt == n:
        return sqrt, sqrt
    ncols = min(n, 4)
    nrows = -(-n // ncols)
    return nrows, ncols


# ---- Inspection ----

def print_metadata_all() -> None:
    """Print metadata summary for all discovered resolution files."""
    for stem, path in MESH_FILES.items():
        meta = get_metadata(path)
        print(f"\n{stem}  ({path.name})")
        print(f"  format     : {meta['format']}")
        print(f"  n_steps    : {meta['n_steps']}")
        print(f"  n_points   : {meta['n_points']}")
        print(f"  n_cells    : {meta['n_cells']}")
        print(f"  cell_types : {meta['cell_types']}")
        print(f"  time range : {meta['times'][0]:.4g} to {meta['times'][-1]:.4g}")
        print(f"  fields ({len(meta['fields'])}):")
        for name, info in meta["fields"].items():
            print(f"    {name:<35} center={info['center']}  shape={info['shape']}")


def print_mesh_at_step(stem: str, step: int = 0) -> None:
    """Load one step and print mesh and field summary."""
    path = MESH_FILES[stem]
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
    timestamp = meta["times"][step]
    print(f"\n{stem} step {step} (t={timestamp:.4g})")
    print(f"  n_points : {mesh.n_points}")
    print(f"  n_cells  : {mesh.n_cells}")
    print(f"  point fields: {list(mesh.point_data.keys())}")
    print(f"  cell fields:  {list(mesh.cell_data.keys())}")


# ---- Visualization ----

def plot_field_at_step(stem: str, field: str, step: int = 0) -> None:
    """Plot a single field at a given step."""
    path = MESH_FILES[stem]
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
    timestamp = meta["times"][step]
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, scalars=field, show_edges=True)
    plotter.add_title(f"{stem}  {field}  t={timestamp:.4g}", font_size=9)
    plotter.show()


def plot_all_scalar_fields(stem: str, step: int = 0) -> None:
    """Plot all scalar fields at a given step in a grid layout."""
    path = MESH_FILES[stem]
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
    timestamp = meta["times"][step]

    scalar_fields = [
        name for name, info in meta["fields"].items()
        if info["shape"] == [1]
    ]
    if not scalar_fields:
        print(f"No scalar fields found in {stem} at step {step}.")
        return

    nrows, ncols = _grid_shape(len(scalar_fields))
    plotter = pv.Plotter(shape=(nrows, ncols))

    for i, field in enumerate(scalar_fields):
        row, col = i // ncols, i % ncols
        plotter.subplot(row, col)
        # mesh.copy() needed so each subplot can set a different active scalar independently
        plotter.add_mesh(mesh.copy(), scalars=field, show_edges=False)
        plotter.add_title(field, font_size=7)

    for j in range(len(scalar_fields), nrows * ncols):
        plotter.subplot(j // ncols, j % ncols)
        plotter.add_text("-", font_size=10, color="gray")

    plotter.link_views()
    plotter.add_title(f"{stem}  all scalar fields  t={timestamp:.4g}", font_size=8)
    plotter.show()


def plot_all_resolutions(field: str, step: int = 0) -> None:
    """Plot all discovered resolutions side by side with linked cameras."""
    stems = list(MESH_FILES.keys())
    nrows, ncols = _grid_shape(len(stems))
    plotter = pv.Plotter(shape=(nrows, ncols))

    for i, stem in enumerate(stems):
        path = MESH_FILES[stem]
        meta = get_metadata(path)
        actual_step = min(step, meta["n_steps"] - 1)
        step_mesh = load_mesh(path, step=actual_step)
        timestamp = meta["times"][actual_step]
        row, col = i // ncols, i % ncols
        plotter.subplot(row, col)
        plotter.add_mesh(step_mesh, scalars=field, show_edges=True)
        plotter.add_title(f"{stem}  t={timestamp:.4g}", font_size=7)
        print(f"  {stem}: {step_mesh.n_points} pts, {step_mesh.n_cells} cells")

    plotter.link_views()
    plotter.show()


def plot_slice(
    stem: str,
    field: str,
    step: int = 0,
    normal: Literal["x", "y", "z", "-x", "-y", "-z"] = "z",
) -> None:
    """Plot a cross-section through the 3D mesh with the ghost mesh for context."""
    path = MESH_FILES[stem]
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
    timestamp = meta["times"][step]
    sliced = mesh.slice(normal=normal)
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, opacity=0.15, color="lightgray")  # ghost mesh for context
    plotter.add_mesh(sliced, scalars=field, show_edges=False)
    plotter.add_title(f"{stem}  {field}  slice {normal}  t={timestamp:.4g}", font_size=9)
    plotter.show()


def plot_field_time_evolution(stem: str, field: str, steps: list[int]) -> None:
    """Plot the same field at multiple time steps side by side."""
    path = MESH_FILES[stem]
    meta = get_metadata(path)

    first_mesh = load_mesh(path, step=0)
    field_array = first_mesh.point_data.get(field) or first_mesh.cell_data.get(field)
    color_range = [float(field_array.min()), float(field_array.max())] if field_array is not None else None

    nrows, ncols = _grid_shape(len(steps))
    plotter = pv.Plotter(shape=(nrows, ncols))

    for i, step in enumerate(steps):
        actual_step = min(step, meta["n_steps"] - 1)
        step_mesh = load_mesh(path, step=actual_step)
        timestamp = meta["times"][actual_step]
        row, col = i // ncols, i % ncols
        plotter.subplot(row, col)
        plotter.add_mesh(step_mesh, scalars=field, show_edges=False, clim=color_range)
        plotter.add_title(f"t={timestamp:.4g}", font_size=8)

    plotter.link_views()
    plotter.show()


if __name__ == "__main__":
    STEP = 150
    FIELD = "pressure"
    STEPS = [0, 100, 200, 400, 500, 600, 700, 800]

    print(f"Discovered files: {list(MESH_FILES.keys())}")

    # Inspection
    print_metadata_all()
    # print_mesh_at_step("lobule_sixth_000025", step=STEP)
    # print_mesh_at_step("lobule_sixth_00000625", step=STEP)

    # Single field
    # plot_field_at_step("lobule_sixth_000025", field=FIELD, step=STEP)

    # All scalar fields for one resolution
    # plot_all_scalar_fields("lobule_sixth_000025", step=STEP)

    # All resolutions side by side
    # plot_all_resolutions(field=FIELD, step=STEP)

    # 3D cross-section slice
    # plot_slice("lobule_sixth_000025", field=FIELD, step=STEP, normal="z")

    # Time evolution across selected steps
    # plot_field_time_evolution("lobule_sixth_000025", field=FIELD, steps=STEPS)

    # GIF animation
    # animate_field(MESH_FILES["lobule_sixth_000025"], field=FIELD, output_path=OUTPUT_DIR / "convergence_pressure.gif", every_nth=10)
    # preview_field_animation(MESH_FILES["lobule_sixth_000025"], field=FIELD, every_nth=50)