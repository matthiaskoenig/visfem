"""Minimal Trame web application for FEM mesh visualization."""

from pathlib import Path

import pyvista as pv
from trame.app import TrameApp
from trame.decorators import change
from trame.ui.vuetify3 import SinglePageWithDrawerLayout
from trame.widgets import vuetify3 as v3
from trame.widgets.vtk import VtkLocalView

from visfem.mesh import load_mesh_from_timeseries

DATA_DIR = Path(__file__).parents[3] / "visfem_data" / "convergence_sixth" / "xdmf"

MESH_FILES = {
    "Coarse (00005)": DATA_DIR / "lobule_sixth_00005.xdmf",
    "Medium-coarse (000025)": DATA_DIR / "lobule_sixth_000025.xdmf",
    "Medium-fine (0000125)": DATA_DIR / "lobule_sixth_0000125.xdmf",
    "Fine (00000625)": DATA_DIR / "lobule_sixth_00000625.xdmf",
}

SCALAR_FIELDS = [
    "pressure",
    "rr_necrosis",
    "rr_zonation_pattern",
    "cell_type",
    "rr_(S)",
    "rr_(P)",
]


class VisfemApp(TrameApp):
    def __init__(self, server=None):
        super().__init__(server)
        self._setup_mesh()
        self._build_ui()

    def _setup_mesh(self) -> None:
        """Load mesh and set up PyVista plotter."""
        self.plotter = pv.Plotter(off_screen=True)
        mesh_path = list(MESH_FILES.values())[0]
        self.pvmesh = load_mesh_from_timeseries(mesh_path, step=1)
        self.plotter.add_mesh(self.pvmesh, scalars=SCALAR_FIELDS[0], show_edges=True, copy_mesh=False)
        self.plotter.reset_camera()

    @change("scalar_field", "step", "mesh_name")
    def _on_change(self, **_) -> None:
        """Update mesh when step, scalar field or mesh selection changes."""
        mesh_path = MESH_FILES[self.state.mesh_name]
        new_mesh = load_mesh_from_timeseries(mesh_path, step=self.state.step)
        self.pvmesh.copy_from(new_mesh, deep=True)
        self.pvmesh.set_active_scalars(self.state.scalar_field)
        self.ctrl.view_update()

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
                        v_model=("mesh_name", mesh_names[0]),
                        items=("mesh_names", mesh_names),
                        density="compact",
                        hide_details=True,
                    )

            # toolbar
            with self.ui.toolbar:
                v3.VSpacer()

                v3.VSelect(
                    v_model=("scalar_field", SCALAR_FIELDS[0]),
                    items=("scalar_fields", SCALAR_FIELDS),
                    label="Field",
                    density="compact",
                    hide_details=True,
                    style="max-width: 200px;",
                )

                v3.VSlider(
                    v_model=("step", 1),
                    min=1,
                    max=865,
                    step=1,
                    label="Step",
                    density="compact",
                    hide_details=True,
                    style="max-width: 300px;",
                )

                v3.VBtn(icon="mdi-crop-free", click=self.reset_camera)

            # content
            with self.ui.content:
                with v3.VContainer(fluid=True, classes="pa-0 fill-height"):
                    view = VtkLocalView(self.plotter.render_window)
                    self.ctrl.reset_camera = view.reset_camera
                    self.ctrl.view_push_camera = view.push_camera
                    self.ctrl.view_update = view.update

            # initialise mesh_name state
            self.state.mesh_name = mesh_names[0]


def main() -> None:
    app = VisfemApp()
    app.server.start()


if __name__ == "__main__":
    main()