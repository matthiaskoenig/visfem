"""Exploration utilities for SPP SimLivA liver lobule datasets (perfusion, deformation, convergence)."""

import math
from pathlib import Path
from typing import Literal

import pyvista as pv

import sys
sys.path.insert(0, str(Path(__file__).parent))
from plot_utils import animate_field, preview_field_animation  # noqa: F401
from visfem.mesh import get_metadata, load_mesh
from visfem.models import MeshMetadata


# Paths

_DATA_BASE      = Path(__file__).parents[1] / "data" / "datasets"
PERFUSION_DIR   = _DATA_BASE / "lobule_perfusion"
DEFORMATION_DIR = _DATA_BASE / "lobule_deformation"
CONVERGENCE_DIR = _DATA_BASE / "lobule_convergence"
OUTPUT_DIR      = Path(__file__).parents[1] / "data" / "results"

# Perfusion + deformation XDMF files
SPP_FILES: dict[str, Path] = {
    p.stem: p
    for directory in (DEFORMATION_DIR, PERFUSION_DIR)
    for p in sorted(directory.glob("*.xdmf"))
    if p.with_suffix(".h5").exists()
}

# Convergence XDMF files (6 mesh resolutions)
CONV_FILES: dict[str, Path] = {
    p.stem: p
    for p in sorted(CONVERGENCE_DIR.glob("*.xdmf"))
    if p.with_suffix(".h5").exists()
}


def _get_scalar_fields(meta: MeshMetadata) -> list[str]:
    """Return names of scalar (shape==[1]) fields from metadata."""
    return [name for name, info in meta.fields.items() if info.shape == [1]]


def _grid_shape(n: int) -> tuple[int, int]:
    """Return a tight (nrows, ncols) grid for n subplots, max 4 columns."""
    sqrt = int(math.isqrt(n))
    if sqrt * sqrt == n:
        return sqrt, sqrt
    ncols = min(n, 4)
    return math.ceil(n / ncols), ncols


def print_metadata_all(files: dict[str, Path] = SPP_FILES) -> None:
    """Print metadata summary for all files in the given dict."""
    for stem, path in files.items():
        meta = get_metadata(path)
        print(f"\n{stem}  ({path.parent.name}/{path.name})")
        print(f"  format     : {meta.format}")
        print(f"  n_steps    : {meta.n_steps}")
        print(f"  n_points   : {meta.n_points}")
        print(f"  n_cells    : {meta.n_cells}")
        print(f"  cell_types : {meta.cell_types}")
        print(f"  time range : {meta.times[0]:.4g} to {meta.times[-1]:.4g}")
        print(f"  fields ({len(meta.fields)}):")
        for name, info in meta.fields.items():
            print(f"    {name:<35} center={info.center}  shape={info.shape}")


def print_mesh_at_step(stem: str, step: int = 0, files: dict[str, Path] = SPP_FILES) -> None:
    """Load one step and print mesh and field summary."""
    path = files[stem]
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
    timestamp = meta.times[step]
    print(f"\n{stem} step {step} (t={timestamp:.4g})")
    print(f"  n_points : {mesh.n_points}")
    print(f"  n_cells  : {mesh.n_cells}")
    print(f"  point fields: {list(mesh.point_data.keys())}")
    print(f"  cell fields:  {list(mesh.cell_data.keys())}")


def plot_field_at_step(stem: str, field: str, step: int = 0, files: dict[str, Path] = SPP_FILES) -> None:
    """Plot a single field at a given step."""
    path = files[stem]
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
    timestamp = meta.times[step]
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, scalars=field, show_edges=True)
    plotter.add_title(f"{stem}  {field}  t={timestamp:.4g}", font_size=9)
    plotter.show()


def plot_all_scalar_fields(stem: str, step: int = 0, files: dict[str, Path] = SPP_FILES) -> None:
    """Plot all scalar fields at a given step in a grid layout."""
    path = files[stem]
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
    timestamp = meta.times[step]

    scalar_fields = _get_scalar_fields(meta)
    if not scalar_fields:
        print(f"No scalar fields found in {stem} at step {step}.")
        return

    nrows, ncols = _grid_shape(len(scalar_fields))
    plotter = pv.Plotter(shape=(nrows, ncols))
    for i, field in enumerate(scalar_fields):
        row, col = i // ncols, i % ncols
        plotter.subplot(row, col)
        plotter.add_mesh(mesh.copy(), scalars=field, show_edges=True)
        plotter.add_title(field, font_size=8)
    for j in range(len(scalar_fields), nrows * ncols):
        plotter.subplot(j // ncols, j % ncols)
        plotter.add_text("-", font_size=10, color="gray")
    plotter.link_views()
    plotter.add_title(f"{stem}  all scalar fields  t={timestamp:.4g}", font_size=8)
    plotter.show()


def plot_field_time_evolution(stem: str, field: str, steps: list[int], files: dict[str, Path] = SPP_FILES) -> None:
    """Plot the same field at multiple time steps side by side."""
    path = files[stem]
    meta = get_metadata(path)

    first_mesh = load_mesh(path, step=0)
    field_array = first_mesh.point_data.get(field) or first_mesh.cell_data.get(field)
    color_range = [float(field_array.min()), float(field_array.max())] if field_array is not None else None

    nrows, ncols = _grid_shape(len(steps))
    plotter = pv.Plotter(shape=(nrows, ncols))
    for i, step in enumerate(steps):
        actual_step = min(step, meta.n_steps - 1)
        mesh = load_mesh(path, step=actual_step)
        timestamp = meta.times[actual_step]
        row, col = i // ncols, i % ncols
        plotter.subplot(row, col)
        plotter.add_mesh(mesh, scalars=field, show_edges=False, clim=color_range)
        plotter.add_title(f"t={timestamp:.4g}", font_size=8)
    plotter.link_views()
    plotter.show()


def plot_deformation_vectors(field: str = "u", step: int = 0) -> None:
    """Plot the deformation mesh with a vector field shown as arrow glyphs."""
    stem = "deformation"
    if stem not in SPP_FILES:
        print(f"'{stem}' not found in: {list(SPP_FILES.keys())}")
        return
    path = SPP_FILES[stem]
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
    timestamp = meta.times[step]
    if field not in mesh.point_data:
        print(f"Field '{field}' not in point data. Available: {list(mesh.point_data.keys())}")
        return
    glyphs = mesh.glyph(orient=field, scale=field, factor=0.01)
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, show_edges=True, opacity=0.5, color="lightgray")
    plotter.add_mesh(glyphs, color="red")
    plotter.add_title(f"deformation  {field} glyphs  t={timestamp:.4g}", font_size=9)
    plotter.show()


def plot_all_resolutions(field: str, step: int = 0) -> None:
    """Plot all convergence resolutions side by side with linked cameras."""
    stems = list(CONV_FILES.keys())
    nrows, ncols = _grid_shape(len(stems))
    plotter = pv.Plotter(shape=(nrows, ncols))
    for i, stem in enumerate(stems):
        path = CONV_FILES[stem]
        meta = get_metadata(path)
        actual_step = min(step, meta.n_steps - 1)
        mesh = load_mesh(path, step=actual_step)
        timestamp = meta.times[actual_step]
        row, col = i // ncols, i % ncols
        plotter.subplot(row, col)
        plotter.add_mesh(mesh, scalars=field, show_edges=True)
        plotter.add_title(f"{stem}  t={timestamp:.4g}", font_size=7)
        print(f"  {stem}: {mesh.n_points} pts, {mesh.n_cells} cells")
    plotter.link_views()
    plotter.show()


def plot_slice(
    stem: str,
    field: str,
    step: int = 0,
    normal: Literal["x", "y", "z", "-x", "-y", "-z"] = "z",
) -> None:
    """Plot a cross-section through a convergence mesh with ghost context."""
    path = CONV_FILES[stem]
    meta = get_metadata(path)
    mesh = load_mesh(path, step=step)
    timestamp = meta.times[step]
    sliced = mesh.slice(normal=normal)
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, opacity=0.15, color="lightgray")
    plotter.add_mesh(sliced, scalars=field, show_edges=False)
    plotter.add_title(f"{stem}  {field}  slice {normal}  t={timestamp:.4g}", font_size=9)
    plotter.show()



if __name__ == "__main__":
    SPP_STEP   = 0
    SPP_FIELD  = "pressure"
    SPP_STEPS  = [0, 20, 40, 60, 85]

    CONV_STEP  = 150
    CONV_FIELD = "pressure"
    CONV_STEPS = [0, 100, 200, 400, 500, 600, 700, 800]

    # Inspection - SPP (perfusion / deformation)
    # print_metadata_all(SPP_FILES)
    # print_mesh_at_step("lobule_spt_p1", step=SPP_STEP)
    # print_mesh_at_step("deformation",   step=SPP_STEP)

    # Inspection - convergence
    # print_metadata_all(CONV_FILES)
    # print_mesh_at_step("lobule_sixth_000025", step=CONV_STEP, files=CONV_FILES)

    # Visualization - SPP
    # plot_field_at_step("lobule_spt_p1",  field=SPP_FIELD,       step=SPP_STEP)
    # plot_field_at_step("deformation",    field="n_f",            step=SPP_STEP)
    # plot_field_at_step("scan_64_p1",     field="active_state",   step=SPP_STEP)
    # plot_all_scalar_fields("lobule_spt_p1",  step=SPP_STEP)
    # plot_all_scalar_fields("deformation",    step=SPP_STEP)
    # plot_field_time_evolution("lobule_spt_p1",  field=SPP_FIELD,       steps=SPP_STEPS)
    # plot_field_time_evolution("scan_64_p1",     field="active_state",  steps=SPP_STEPS)
    # plot_deformation_vectors(field="u", step=SPP_STEP)

    # Visualization - convergence
    # plot_field_at_step("lobule_sixth_000025", field=CONV_FIELD, step=CONV_STEP, files=CONV_FILES)
    # plot_all_scalar_fields("lobule_sixth_000025", step=CONV_STEP, files=CONV_FILES)
    # plot_all_resolutions(field=CONV_FIELD, step=CONV_STEP)
    # plot_slice("lobule_sixth_000025", field=CONV_FIELD, step=CONV_STEP, normal="z")
    # plot_field_time_evolution("lobule_sixth_000025", field=CONV_FIELD, steps=CONV_STEPS, files=CONV_FILES)

    # GIF animation
    # animate_field(SPP_FILES["lobule_spt_p1"],      field="necrosis",    output_path=OUTPUT_DIR / "lobule_p1_necrosis.gif",      every_nth=5)
    # animate_field(CONV_FILES["lobule_sixth_000025"], field=CONV_FIELD,  output_path=OUTPUT_DIR / "convergence_pressure.gif",    every_nth=10)
    # preview_field_animation(SPP_FILES["lobule_spt_p1"],       field="necrosis",   every_nth=2)
    # preview_field_animation(CONV_FILES["lobule_sixth_000025"], field=CONV_FIELD,   every_nth=50)
