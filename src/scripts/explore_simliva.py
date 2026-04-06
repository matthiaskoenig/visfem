"""Exploratory script for the 08_SPP_FEMVis dataset.

Four FEniCS XDMF files across deformation, lobule, and scan subfolders.
Files: deformation (2D quad, 10 steps), lobule p1/p6 (2D triangle, 86 steps), scan (2D triangle, 86 steps).
Run sections by uncommenting the relevant call at the bottom.
"""

import math
from pathlib import Path

import pyvista as pv

from plot_utils import animate_field, preview_field_animation  # noqa: F401
from visfem.mesh import get_metadata, load_mesh


# ---- Paths ----

SPP_DIR = Path.home() / "Projects" / "VisFEM_project" / "visfem_data" / "08_SPP_FEMVis"

DEFORMATION = SPP_DIR / "deformation" / "deformation.xdmf"
LOBULE_P1   = SPP_DIR / "lobule" / "lobule_spt_p1.xdmf"
LOBULE_P6   = SPP_DIR / "lobule" / "lobule_spt_p6.xdmf"
SCAN        = SPP_DIR / "scan" / "scan_64_p1.xdmf"

ALL_FILES = [DEFORMATION, LOBULE_P1, LOBULE_P6, SCAN]


def _grid_shape(n: int) -> tuple[int, int]:
    """Return a tight (nrows, ncols) grid shape for n subplots, max 4 columns."""
    sqrt = int(math.isqrt(n))
    if sqrt * sqrt == n:
        return sqrt, sqrt
    ncols = min(n, 4)
    # Ceiling division: ensures enough rows for all subplots without a math import
    nrows = -(-n // ncols)
    return nrows, ncols


# ---- Inspection ----

def print_metadata_all() -> None:
    """Print metadata summary for all 4 SPP files."""
    for path in ALL_FILES:
        meta = get_metadata(path)
        print(f"\n{path.name}")
        print(f"  format     : {meta['format']}")
        print(f"  n_steps    : {meta['n_steps']}")
        print(f"  n_points   : {meta['n_points']}")
        print(f"  n_cells    : {meta['n_cells']}")
        print(f"  cell_types : {meta['cell_types']}")
        print(f"  time range : {meta['times'][0]:.4g} to {meta['times'][-1]:.4g}")
        print(f"  fields ({len(meta['fields'])}):")
        for name, info in meta["fields"].items():
            print(f"    {name:<25} center={info['center']}  shape={info['shape']}")


def print_mesh_at_step(path: Path, step: int = 0) -> None:
    """Load one step and print mesh and field summary."""
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
    timestamp = meta["times"][step]
    print(f"\n{path.name} step {step} (t={timestamp:.4g})")
    print(f"  n_points : {mesh.n_points}")
    print(f"  n_cells  : {mesh.n_cells}")
    print(f"  point fields: {list(mesh.point_data.keys())}")
    print(f"  cell fields:  {list(mesh.cell_data.keys())}")


# ---- Visualization ----

def plot_field_at_step(path: Path, field: str, step: int = 0) -> None:
    """Plot a single field at a given step."""
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
    timestamp = meta["times"][step]
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, scalars=field, show_edges=True)
    plotter.add_title(f"{path.stem}  {field}  t={timestamp:.4g}", font_size=9)
    plotter.show()


def plot_all_fields_at_step(path: Path, step: int = 0) -> None:
    """Plot all scalar fields at a given step in a grid layout."""
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
    timestamp = meta["times"][step]

    # Only scalar fields (shape == [1]); vectors and tensors are excluded
    scalar_fields = [
        name for name, info in meta["fields"].items()
        if info["shape"] == [1]
    ]
    if not scalar_fields:
        print(f"No scalar fields found in {path.name} at step {step}.")
        return

    nrows, ncols = _grid_shape(len(scalar_fields))
    plotter = pv.Plotter(shape=(nrows, ncols))

    for i, field in enumerate(scalar_fields):
        row, col = i // ncols, i % ncols
        plotter.subplot(row, col)
        # mesh.copy() needed so each subplot can set a different active scalar independently
        plotter.add_mesh(mesh.copy(), scalars=field, show_edges=True)
        plotter.add_title(field, font_size=8)

    # Fill any leftover empty subplots
    for j in range(len(scalar_fields), nrows * ncols):
        plotter.subplot(j // ncols, j % ncols)
        plotter.add_text("-", font_size=10, color="gray")

    plotter.link_views()
    plotter.add_title(f"{path.stem}  all scalar fields  t={timestamp:.4g}", font_size=8)
    plotter.show()


def plot_field_time_evolution(path: Path, field: str, steps: list[int]) -> None:
    """Plot the same field at multiple time steps side by side."""
    meta = get_metadata(path)

    # Fix colormap range from step 0 so all panels are comparable
    first_mesh = load_mesh(path, step=0)
    field_array = first_mesh.point_data.get(field)
    if field_array is None:
        field_array = first_mesh.cell_data.get(field)
    color_range = [float(field_array.min()), float(field_array.max())] if field_array is not None else None

    nrows, ncols = _grid_shape(len(steps))
    plotter = pv.Plotter(shape=(nrows, ncols))

    for i, step in enumerate(steps):
        step_mesh = load_mesh(path, step=step)
        timestamp = meta["times"][step]
        row, col = i // ncols, i % ncols
        plotter.subplot(row, col)
        plotter.add_mesh(step_mesh, scalars=field, show_edges=False, clim=color_range)
        plotter.add_title(f"t={timestamp:.4g}", font_size=8)

    plotter.link_views()
    plotter.show()


def plot_p1_vs_p6(field: str, step: int = 0) -> None:
    """Plot lobule p1 and p6 side by side for the same field and step."""
    meta_p1 = get_metadata(LOBULE_P1)
    meta_p6 = get_metadata(LOBULE_P6)
    mesh_p1 = load_mesh(LOBULE_P1, step=step)
    mesh_p6 = load_mesh(LOBULE_P6, step=step)

    plotter = pv.Plotter(shape=(1, 2))
    plotter.subplot(0, 0)
    plotter.add_mesh(mesh_p1, scalars=field, show_edges=True)
    plotter.add_title(f"p1  {field}  t={meta_p1['times'][step]:.4g}", font_size=8)
    plotter.subplot(0, 1)
    plotter.add_mesh(mesh_p6, scalars=field, show_edges=True)
    plotter.add_title(f"p6  {field}  t={meta_p6['times'][step]:.4g}", font_size=8)
    plotter.link_views()
    plotter.show()


def plot_deformation_vectors(field: str = "u", step: int = 0) -> None:
    """Plot the deformation mesh with a vector field shown as arrow glyphs."""
    meta = get_metadata(DEFORMATION)
    mesh = load_mesh(DEFORMATION, step=step)
    timestamp = meta["times"][step]

    if field not in mesh.point_data:
        print(f"Field '{field}' not found in point data. Available: {list(mesh.point_data.keys())}")
        return

    plotter = pv.Plotter()
    plotter.add_mesh(mesh, show_edges=True, opacity=0.5, color="lightgray")
    # factor=0.01 scales glyph size to match deformation units (displacements are small)
    glyphs = mesh.glyph(orient=field, scale=field, factor=0.01)
    plotter.add_mesh(glyphs, color="red")
    plotter.add_title(f"deformation  {field} glyphs  t={timestamp:.4g}", font_size=9)
    plotter.show()


if __name__ == "__main__":
    STEP = 0
    FIELD = "pressure"           # valid for lobule and scan files
    STEPS = [0, 20, 40, 60, 85]  # for time evolution plots
    OUTPUT_DIR = Path.home() / "Projects" / "VisFEM_project" / "visfem_results"

    # Inspection
    # print_metadata_all()
    # print_mesh_at_step(LOBULE_P1, step=STEP)
    # print_mesh_at_step(DEFORMATION, step=STEP)
    # print_mesh_at_step(SCAN, step=STEP)

    # Single field
    # plot_field_at_step(LOBULE_P1, field=FIELD, step=STEP)
    # plot_field_at_step(DEFORMATION, field="n_f", step=STEP)
    # plot_field_at_step(SCAN, field="active_state", step=STEP)

    # All scalar fields at one step
    # plot_all_fields_at_step(LOBULE_P1, step=STEP)
    # plot_all_fields_at_step(DEFORMATION, step=STEP)

    # Time evolution across selected steps
    # plot_field_time_evolution(LOBULE_P1, field=FIELD, steps=STEPS)
    # plot_field_time_evolution(SCAN, field="active_state", steps=STEPS)

    # Parameter comparison: p1 vs p6
    # plot_p1_vs_p6(field=FIELD, step=STEP)

    # Vector field glyphs (deformation only, fields: u, ws)
    # plot_deformation_vectors(field="u", step=STEP)

    # GIF animation (every_nth controls frame density)
    # animate_field(LOBULE_P1, field="necrosis", output_path=OUTPUT_DIR / "lobule_p1_necrosis.gif", every_nth=5)
    # preview_field_animation(LOBULE_P1, field="necrosis", every_nth=2)