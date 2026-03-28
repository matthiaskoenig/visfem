"""Shared plotting utilities for FEM visualization scripts.

Works with any dataset supported by visfem.mesh.load_mesh() and get_metadata().
"""

from pathlib import Path

import pyvista as pv

from visfem.mesh import get_metadata, load_mesh


def animate_field(path: Path, field: str, output_path: Path, every_nth: int = 1) -> None:
    """Export a GIF animation of a field over all time steps."""
    meta = get_metadata(path)
    steps = list(range(0, meta["n_steps"], every_nth))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Fix colormap range from step 0 so colors stay consistent across frames
    first_mesh = load_mesh(path, step=0)
    arr = first_mesh.point_data.get(field)
    if arr is None:
        arr = first_mesh.cell_data.get(field)
    if arr is None:
        print(f"Field '{field}' not found. Available: "
              f"{list(first_mesh.point_data.keys()) + list(first_mesh.cell_data.keys())}")
        return
    clim = [float(arr.min()), float(arr.max())]

    plotter = pv.Plotter(off_screen=True)
    plotter.open_gif(str(output_path))

    for step in steps:
        pvmesh = load_mesh(path, step=step)
        t = meta["times"][step]
        plotter.clear()
        plotter.add_mesh(pvmesh, scalars=field, clim=clim, show_edges=False)
        plotter.add_title(f"{path.stem}  {field}  t={t:.4g}", font_size=9)
        plotter.write_frame()
        print(f"  step {step}/{meta['n_steps'] - 1}  t={t:.4g}")

    plotter.close()
    print(f"Saved: {output_path}")


def preview_field_animation(path: Path, field: str, every_nth: int = 1) -> None:
    """Preview a field animation interactively in the PyVista window."""
    meta = get_metadata(path)
    steps = list(range(0, meta["n_steps"], every_nth))

    # Fix colormap range from step 0 so colors stay consistent across frames
    first_mesh = load_mesh(path, step=0)
    arr = first_mesh.point_data.get(field)
    if arr is None:
        arr = first_mesh.cell_data.get(field)
    if arr is None:
        print(f"Field '{field}' not found.")
        return
    clim = [float(arr.min()), float(arr.max())]

    # Open the window with the first frame, then update in place
    plotter = pv.Plotter()
    pvmesh = load_mesh(path, step=steps[0])
    plotter.add_mesh(pvmesh, scalars=field, clim=clim, show_edges=False)
    plotter.show(auto_close=False, interactive_update=True)

    for step in steps:
        pvmesh = load_mesh(path, step=step)
        t = meta["times"][step]
        plotter.clear()
        plotter.add_mesh(pvmesh, scalars=field, clim=clim, show_edges=False)
        plotter.add_title(f"{path.stem}  {field}  t={t:.4g}", font_size=9)
        plotter.update()
        print(f"  step {step}  t={t:.4g}")

    plotter.show()