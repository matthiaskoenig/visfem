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

logger = get_logger(__name__)  # module-level logger

# Default data directory; override via VISFEM_DATA_DIR env var
DATA_DIR = Path(
    os.environ.get(
        "VISFEM_DATA_DIR",
        Path(__file__).parents[3] / "visfem_data" / "convergence_sixth" / "xdmf",
    )
)

# Available mesh resolutions mapped to their XDMF files
MESH_FILES = {
    "Coarse (00005)":         DATA_DIR / "lobule_sixth_00005.xdmf",
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

    # --- Setup ---

    def _setup_mesh(self) -> None:
        """Load initial mesh, read field names, and cache step counts per file."""
        # Pre-cache step counts to avoid reopening files on every mesh switch
        self._step_counts: dict[str, int] = {
            name: _num_steps(path) for name, path in MESH_FILES.items()
        }

        mesh_names = list(MESH_FILES.keys())
        initial_name = mesh_names[0]
        initial_path = MESH_FILES[initial_name]

        self.plotter = pv.Plotter(off_screen=True)
        self.pvmesh = load_mesh_from_timeseries(initial_path, step=1)

        scalar_fields = get_field_names(initial_path, step=1)
        initial_field = scalar_fields[0] if scalar_fields else None

        self.plotter.add_mesh(
            self.pvmesh,
            scalars=initial_field,
            show_edges=True,
            copy_mesh=False,  # avoid redundant copy; mesh is owned here
        )
        self.plotter.reset_camera()

        self.state.update({
            "mesh_name": initial_name,
            "scalar_fields": scalar_fields,
            "scalar_field": initial_field,
            "step": 1,
            "num_steps": self._step_counts[initial_name],
        })

    # --- Redraw ---

    def _redraw(self, mesh_name: str, field: str | None, step: int) -> None:
        """Clear and redraw the plotter with updated mesh/field/step."""
        mesh_path = MESH_FILES.get(mesh_name)
        if mesh_path is None or not mesh_path.exists():
            logger.error(f"Mesh file not found: {mesh_path}")
            return

        # Clamp step to valid range
        num_steps = self._step_counts[mesh_name]
        step = max(1, min(step, num_steps - 1))

        try:
            new_mesh = load_mesh_from_timeseries(mesh_path, step=step)
        except Exception as e:
            logger.error(f"Failed to load '{mesh_path.name}' at step {step}: {e}")
            return

        self.plotter.clear()
        self.pvmesh = new_mesh
        self.plotter.add_mesh(
            self.pvmesh,
            scalars=field,
            show_edges=True,
            copy_mesh=False,
        )
        self.ctrl.view_update()

    # --- State callbacks ---

    @change("scalar_field", "step")
    def _on_field_or_step_change(self, **_) -> None:
        """Redraw when the active field or timestep changes."""
        self._redraw(
            mesh_name=self.state.mesh_name,
            field=self.state.scalar_field,
            step=int(self.state.step),
        )

    @change("mesh_name")
    def _on_mesh_change(self, **_) -> None:
        """Update slider max, field list, and redraw when mesh changes."""
        mesh_name = self.state.mesh_name
        mesh_path = MESH_FILES.get(mesh_name)
        if mesh_path is None or not mesh_path.exists():
            return

        num_steps = self._step_counts[mesh_name]
        self.state.num_steps = num_steps
        step = max(1, min(int(self.state.step), num_steps - 1))
        self.state.step = step

        scalar_fields = get_field_names(mesh_path, step=1)
        self.state.scalar_fields = scalar_fields

        # Keep current field if it exists in the new mesh, else fall back to first
        current_field = self.state.scalar_field
        new_field = (
            current_field if current_field in scalar_fields
            else (scalar_fields[0] if scalar_fields else None)
        )
        self.state.scalar_field = new_field

        self._redraw(mesh_name=mesh_name, field=new_field, step=step)

    # --- Camera ---

    def reset_camera(self) -> None:
        """Reset camera to default position."""
        self.plotter.reset_camera()
        self.ctrl.view_push_camera()
        self.ctrl.reset_camera()

    # --- UI ---

    def _build_ui(self) -> None:
        """Build the user interface."""
        mesh_names = list(MESH_FILES.keys())

        with SinglePageWithDrawerLayout(self.server) as self.ui:
            self.ui.title.set_text("VisFEM")

            # Sidebar: mesh resolution selector
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

            # Toolbar: field selector + step slider + camera reset
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

            # Main viewport
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