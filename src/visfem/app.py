"""Trame web application for FEM mesh visualization."""

import logging
import os
from pathlib import Path

import meshio
import pyvista as pv
from trame.app import TrameApp
from trame.decorators import change
from trame.ui.vuetify3 import SinglePageWithDrawerLayout
from trame.widgets import vuetify3 as v3
from trame.widgets.vtk import VtkLocalView

from visfem.log import get_logger
from visfem.mesh import get_field_names, load_mesh_from_timeseries

logger: logging.Logger = get_logger(__name__)

DATA_DIR = Path(os.environ.get("VISFEM_DATA_DIR", Path(__file__).parents[3] / "visfem_data" / "convergence_sixth" / "xdmf"))

MESH_FILES = {
    "Coarse (00005)":        DATA_DIR / "lobule_sixth_00005.xdmf",
    "Medium-coarse (000025)": DATA_DIR / "lobule_sixth_000025.xdmf",
    "Medium-fine (0000125)":  DATA_DIR / "lobule_sixth_0000125.xdmf",
    "Fine (00000625)":        DATA_DIR / "lobule_sixth_00000625.xdmf",
}


def _num_steps(path: Path) -> int:
    """Return the number of time steps in an XDMF time series file."""
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        return reader.num_steps


class VisfemApp(TrameApp):
    def __init__(self, server=None):
        super().__init__(server)
        self._setup_mesh()
        self._build_ui()

    def _setup_mesh(self) -> None:
        """Load initial mesh, read field names, and cache step counts per file."""
        # Cache num_steps for each mesh file so the slider max can update dynamically
        self._step_counts = {name: _num_steps(path) for name, path in MESH_FILES.items()}

        mesh_names = list(MESH_FILES.keys())
        initial_path = MESH_FILES[mesh_names[0]]

        self.plotter = pv.Plotter(off_screen=True)
        self.pvmesh = load_mesh_from_timeseries(initial_path, step=1)

        # Read field names dynamically from the file
        scalar_fields = get_field_names(initial_path, step=1)

        self.plotter.add_mesh(
            self.pvmesh,
            scalars=scalar_fields[0] if scalar_fields else None,
            show_edges=True,
            copy_mesh=False,
        )
        self.plotter.reset_camera()

        # Initialise state
        self.state.update({
            "mesh_name": mesh_names[0],
            "scalar_fields": scalar_fields,
            "scalar_field": scalar_fields[0] if scalar_fields else None,
            "step": 1,
            "num_steps": self._step_counts[mesh_names[0]],
        })

    @change("scalar_field", "step", "mesh_name")
    def _on_change(self, **_) -> None:
        """Reload and redisplay mesh when step, scalar field, or mesh changes."""
        mesh_path = MESH_FILES.get(self.state.mesh_name)
        if mesh_path is None or not mesh_path.exists():
            logger.error(f"Mesh file not found: {mesh_path}")
            return

        step = int(self.state.step)
        num_steps = self._step_counts[self.state.mesh_name]
        if not (1 <= step <= num_steps - 1):
            logger.warning(f"Step {step} out of range [1, {num_steps - 1}], clamping.")
            step = max(1, min(step, num_steps - 1))

        try:
            new_mesh = load_mesh_from_timeseries(mesh_path, step=step)
        except Exception as e:
            logger.error(f"Failed to load mesh '{mesh_path.name}' at step {step}: {e}")
            return

        # Clear and re-add: the only reliable way to update the VTK pipeline
        self.plotter.clear()
        self.pvmesh = new_mesh
        self.plotter.add_mesh(self.pvmesh, scalars=self.state.scalar_field, show_edges=True, copy_mesh=False)
        self.ctrl.view_update()

    @change("mesh_name")
    def _on_mesh_change(self, **_) -> None:
        """Update slider max and field list when the mesh selection changes."""
        mesh_path = MESH_FILES.get(self.state.mesh_name)
        if mesh_path is None or not mesh_path.exists():
            return

        # Update step slider max for the newly selected mesh
        self.state.num_steps = self._step_counts[self.state.mesh_name]

        # Update available scalar fields for the newly selected mesh
        scalar_fields = get_field_names(mesh_path, step=1)
        current_field = self.state.scalar_field
        self.state.scalar_fields = scalar_fields
        # Keep current field selection if it exists in the new mesh, else reset
        if current_field not in scalar_fields:
            self.state.scalar_field = scalar_fields[0] if scalar_fields else None

    def reset_camera(self) -> None:
        """Reset camera to default position."""
        self.plotter.reset_camera()
        self.ctrl.view_push_camera()
        self.ctrl.reset_camera()

    def _build_ui(self) -> None:
        """Build the user interface."""
        mesh_names = list(MESH_FILES.keys())

        with SinglePageWithDrawerLayout(self.server) as self.ui:
            self.ui.title.set_text("VisFEM")

            # sidebar
            with self.ui.drawer as drawer:
                drawer.width = 250
                with v3.VContainer(classes="pa-4"):
                    v3.VListSubheader("Liver Lobule Mesh Resolution")
                    v3.VSelect(
                        v_model=("mesh_name",),
                        items=("mesh_names", mesh_names),
                        density="compact",
                        hide_details=True,
                    )

            # toolbar
            with self.ui.toolbar:
                v3.VSpacer()

                v3.VSelect(
                    v_model=("scalar_field",),
                    items=("scalar_fields",),
                    label="Field",
                    density="compact",
                    hide_details=True,
                    style="max-width: 200px;",
                )

                v3.VSlider(
                    v_model=("step",),
                    min=1,
                    max=("num_steps - 1",),
                    step=1,
                    label="Step",
                    thumb_label=True,
                    density="compact",
                    hide_details=True,
                    style="max-width: 300px; margin-top: 20px;",
                )

                v3.VBtn(icon="mdi-crop-free", click=self.reset_camera)

            # content
            with self.ui.content:
                with v3.VContainer(fluid=True, classes="pa-0 fill-height"):
                    view = VtkLocalView(self.plotter.render_window)
                    self.ctrl.reset_camera = view.reset_camera
                    self.ctrl.view_push_camera = view.push_camera
                    self.ctrl.view_update = view.update


def main() -> None:
    app = VisfemApp()
    app.server.start()


if __name__ == "__main__":
    main()