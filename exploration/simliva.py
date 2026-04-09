"""Exploratory script for the SPP SimLivA dataset.

FEniCS XDMF files: deformation (lobule_deformation/) and perfusion
(lobule_perfusion/: lobule_spt_p1, lobule_spt_p6, scan_64_p1).
Run sections by uncommenting the relevant call at the bottom.
"""

import math
from pathlib import Path

import pyvista as pv

from plot_utils import animate_field, preview_field_animation  # noqa: F401
from visfem.mesh import get_metadata, load_mesh


# ---- Paths ----

_DATA_BASE      = Path(__file__).parents[1] / "data" / "fem_data"
PERFUSION_DIR   = _DATA_BASE / "simliva" / "lobule_perfusion"
DEFORMATION_DIR = _DATA_BASE / "simliva" / "lobule_deformation"
OUTPUT_DIR      = Path(__file__).parents[1] / "data" / "results"

# Discover all XDMF files that have a matching .h5 — no filenames hardcoded
ALL_FILES: dict[str, Path] = {
    p.stem: p
    for directory in (DEFORMATION_DIR, PERFUSION_DIR)
    for p in sorted(directory.glob("*.xdmf"))
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
    """Print metadata summary for all discovered SPP files."""
    for stem, path in ALL_FILES.items():
        meta = get_metadata(path)
        print(f"\n{stem}  ({path.parent.name}/{path.name})")
        print(f"  format     : {meta['format']}")
        print(f"  n_steps    : {meta['n_steps']}")
        print(f"  n_points   : {meta['n_points']}")
        print(f"  n_cells    : {meta['n_cells']}")
        print(f"  cell_types : {meta['cell_types']}")
        print(f"  time range : {meta['times'][0]:.4g} to {meta['times'][-1]:.4g}")
        print(f"  fields ({len(meta['fields'])}):")
        for name, info in meta["fields"].items():
            print(f"    {name:<25} center={info['center']}  shape={info['shape']}")


def print_mesh_at_step(stem: str, step: int = 0) -> None:
    """Load one step and print mesh and field summary."""
    path = ALL_FILES[stem]
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
    path = ALL_FILES[stem]
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
    timestamp = meta["times"][step]
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, scalars=field, show_edges=True)
    plotter.add_title(f"{stem}  {field}  t={timestamp:.4g}", font_size=9)
    plotter.show()


def plot_all_fields_at_step(stem: str, step: int = 0) -> None:
    """Plot all scalar fields at a given step in a grid layout."""
    path = ALL_FILES[stem]
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
        plotter.add_mesh(mesh.copy(), scalars=field, show_edges=True)
        plotter.add_title(field, font_size=8)

    for j in range(len(scalar_fields), nrows * ncols):
        plotter.subplot(j // ncols, j % ncols)
        plotter.add_text("-", font_size=10, color="gray")

    plotter.link_views()
    plotter.add_title(f"{stem}  all scalar fields  t={timestamp:.4g}", font_size=8)
    plotter.show()


def plot_field_time_evolution(stem: str, field: str, steps: list[int]) -> None:
    """Plot the same field at multiple time steps side by side."""
    path = ALL_FILES[stem]
    meta = get_metadata(path)

    first_mesh = load_mesh(path, step=0)
    field_array = first_mesh.point_data.get(field) or first_mesh.cell_data.get(field)
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


def plot_deformation_vectors(field: str = "u", step: int = 0) -> None:
    """Plot the deformation mesh with a vector field shown as arrow glyphs."""
    stem = "deformation"
    if stem not in ALL_FILES:
        print(f"'{stem}' not found in discovered files: {list(ALL_FILES.keys())}")
        return
    path = ALL_FILES[stem]
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
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

    print(f"Discovered files: {list(ALL_FILES.keys())}")

    # Inspection
    print_metadata_all()
    # print_mesh_at_step("lobule_spt_p1", step=STEP)
    # print_mesh_at_step("deformation", step=STEP)

    # Single field
    # plot_field_at_step("lobule_spt_p1", field=FIELD, step=STEP)
    # plot_field_at_step("deformation", field="n_f", step=STEP)
    # plot_field_at_step("scan_64_p1", field="active_state", step=STEP)

    # All scalar fields at one step
    # plot_all_fields_at_step("lobule_spt_p1", step=STEP)
    # plot_all_fields_at_step("deformation", step=STEP)

    # Time evolution across selected steps
    # plot_field_time_evolution("lobule_spt_p1", field=FIELD, steps=STEPS)
    # plot_field_time_evolution("scan_64_p1", field="active_state", steps=STEPS)

    # Vector field glyphs (deformation only)
    # plot_deformation_vectors(field="u", step=STEP)

    # GIF animation
    # animate_field(ALL_FILES["lobule_spt_p1"], field="necrosis", output_path=OUTPUT_DIR / "lobule_p1_necrosis.gif", every_nth=5)
    # preview_field_animation(ALL_FILES["lobule_spt_p1"], field="necrosis", every_nth=2)