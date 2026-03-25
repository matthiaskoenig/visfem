"""Exploratory mesh loading and visualization using meshio and PyVista."""

from pathlib import Path

import meshio
import pyvista as pv


def load_mesh_from_timeseries(path: Path, step: int = 0) -> pv.UnstructuredGrid:
    """Load a single time step from an XDMF time series and convert to PyVista."""
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        print(f"Number of time steps: {reader.num_steps}")
        points, cells = reader.read_points_cells()
        t, point_data, cell_data = reader.read_data(step)
        mesh = meshio.Mesh(
            points=points,
            cells=cells,
            point_data=point_data,
            cell_data=cell_data,
        )
    return pv.utilities.from_meshio(mesh)


def plot_mesh(path: Path, step: int = 0) -> None:
    """Load and display a single mesh file."""
    pvmesh = load_mesh_from_timeseries(path, step)
    print(f"Mesh: {path.name} (step {step})")
    print(f"  Points: {pvmesh.n_points}")
    print(f"  Cells:  {pvmesh.n_cells}")
    pvmesh.plot(show_edges=True)


def animate_mesh(path: Path, every_nth: int = 10) -> None:
    """Animate all time steps of a mesh file."""
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        points, cells = reader.read_points_cells()

        plotter = pv.Plotter()
        plotter.open_gif(OUTPUT_DIR / "mesh_animation.gif")

        for step in range(0, reader.num_steps, every_nth):
            t, point_data, cell_data = reader.read_data(step)
            mesh = meshio.Mesh(
                points=points,
                cells=cells,
                point_data=point_data,
                cell_data=cell_data,
            )
            pvmesh = pv.utilities.from_meshio(mesh)
            plotter.clear()
            plotter.add_mesh(pvmesh, show_edges=True)
            plotter.add_text(f"t = {t:.2f}", font_size=12)
            plotter.write_frame()

        plotter.close()


def plot_all_resolutions(mesh_files: list[Path], step: int = 0) -> None:
    """Plot all available mesh resolutions in a 2x2 grid with linked cameras."""
    plotter = pv.Plotter(shape=(2, 2))

    for i, mesh_path in enumerate(mesh_files):
        row = i // 2
        col = i % 2
        plotter.subplot(row, col)
        pvmesh = load_mesh_from_timeseries(mesh_path, step=step)
        plotter.add_mesh(pvmesh, show_edges=True)
        plotter.add_title(mesh_path.stem, font_size=8)
        print(f"{mesh_path.stem}: {pvmesh.n_points} points, {pvmesh.n_cells} cells")

    plotter.link_views()
    plotter.show()


def print_fields(path: Path, step: int = 0) -> None:
    """Print all available data fields in the mesh."""
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        points, cells = reader.read_points_cells()
        t, point_data, cell_data = reader.read_data(step)

        print("\n--- Point data (on nodes) ---")
        for name, data in point_data.items():
            print(f"  {name}: shape {data.shape}")

        print("\n--- Cell data (on cells) ---")
        for name, data in cell_data.items():
            print(f"  {name}: shape {data[0].shape}")


def plot_scalar_fields(path: Path, step: int = 0) -> None:
    """Plot selected scalar fields side by side in a grid."""
    pvmesh = load_mesh_from_timeseries(path, step)

    scalar_fields = [
        "pressure",
        "rr_necrosis",
        "rr_zonation_pattern",
        "cell_type",
        "rr_(S)",
        "rr_(P)",
    ]

    ncols = 3
    nrows = 2
    plotter = pv.Plotter(shape=(nrows, ncols))

    for i, field in enumerate(scalar_fields):
        row = i // ncols
        col = i % ncols
        plotter.subplot(row, col)
        plotter.add_mesh(pvmesh, scalars=field, show_edges=True)
        plotter.add_title(field, font_size=8)

    plotter.link_views()
    plotter.show()

if __name__ == "__main__":
    # configuration
    DATA_DIR = Path(__file__).parents[3] / "visfem_data" / "convergence_sixth" / "xdmf"
    OUTPUT_DIR = Path(__file__).parents[3] / "visfem_results"
    OUTPUT_DIR.mkdir(exist_ok=True)

    STEP = 150
    ANIMATE_EVERY_NTH = 10

    MESH_FILES = [
        DATA_DIR / "lobule_sixth_00005.xdmf",
        DATA_DIR / "lobule_sixth_000025.xdmf",
        DATA_DIR / "lobule_sixth_0000125.xdmf",
        DATA_DIR / "lobule_sixth_00000625.xdmf",
    ]

    # run
    # plot_mesh(MESH_FILES[0], step=STEP)
    # animate_mesh(MESH_FILES[0], every_nth=ANIMATE_EVERY_NTH)
    # plot_all_resolutions(MESH_FILES, step=STEP)
    # print_fields(MESH_FILES[0], step=STEP)
    plot_scalar_fields(MESH_FILES[3], step=STEP)