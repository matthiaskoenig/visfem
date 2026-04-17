"""Shared plotting utilities for FEM visualization exploration."""

from pathlib import Path

import pyvista as pv

from visfem.mesh import get_metadata, load_mesh


def _get_field_and_range(mesh: pv.DataSet, field: str) -> tuple[object, list[float]] | tuple[None, None]:
    """Return (field_array, [min, max]) from point or cell data, or (None, None) if missing."""
    arr = mesh.point_data.get(field) or mesh.cell_data.get(field)
    if arr is None:
        return None, None
    return arr, [float(arr.min()), float(arr.max())]


def animate_field(path: Path, field: str, output_path: Path, every_nth: int = 1) -> None:
    """Export a GIF animation of a field over all time steps."""
    meta = get_metadata(path)
    steps = list(range(0, meta.n_steps, every_nth))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    first_mesh = load_mesh(path, step=0)
    _, color_range = _get_field_and_range(first_mesh, field)
    if color_range is None:
        print(f"Field '{field}' not found. Available: "
              f"{list(first_mesh.point_data.keys()) + list(first_mesh.cell_data.keys())}")
        return

    plotter = pv.Plotter(off_screen=True)
    plotter.open_gif(str(output_path))

    for step in steps:
        step_mesh = load_mesh(path, step=step)
        timestamp = meta.times[step]
        plotter.clear()
        plotter.add_mesh(step_mesh, scalars=field, clim=color_range, show_edges=False)
        plotter.add_title(f"{path.stem}  {field}  t={timestamp:.4g}", font_size=9)
        plotter.write_frame()
        print(f"  step {step}/{meta.n_steps - 1}  t={timestamp:.4g}")

    plotter.close()
    print(f"Saved: {output_path}")


def preview_field_animation(path: Path, field: str, every_nth: int = 1) -> None:
    """Preview a field animation interactively in the PyVista window."""
    meta = get_metadata(path)
    steps = list(range(0, meta.n_steps, every_nth))

    first_mesh = load_mesh(path, step=0)
    _, color_range = _get_field_and_range(first_mesh, field)
    if color_range is None:
        print(f"Field '{field}' not found.")
        return

    # auto_close=False keeps window alive; interactive_update=True enables non-blocking refresh
    plotter = pv.Plotter()
    step_mesh = load_mesh(path, step=steps[0])
    plotter.add_mesh(step_mesh, scalars=field, clim=color_range, show_edges=False)
    plotter.show(auto_close=False, interactive_update=True)

    for step in steps:
        step_mesh = load_mesh(path, step=step)
        timestamp = meta.times[step]
        plotter.clear()
        plotter.add_mesh(step_mesh, scalars=field, clim=color_range, show_edges=False)
        plotter.add_title(f"{path.stem}  {field}  t={timestamp:.4g}", font_size=9)
        plotter.update()
        print(f"  step {step}  t={timestamp:.4g}")

    plotter.show()
