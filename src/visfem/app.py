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
from visfem.mesh import get_field_names, get_organ_names, load_mesh, load_mesh_from_timeseries

logger = get_logger(__name__)

# FEM lobule data
DATA_DIR = Path(
    os.environ.get(
        "VISFEM_DATA_DIR",
        Path(__file__).parents[3] / "visfem_data" / "convergence_sixth" / "xdmf",
    )
)
MESH_FILES = {
    "Coarse (00005)":         DATA_DIR / "lobule_sixth_00005.xdmf",
    "Medium-coarse (000025)": DATA_DIR / "lobule_sixth_000025.xdmf",
    "Medium-fine (0000125)":  DATA_DIR / "lobule_sixth_0000125.xdmf",
    "Fine (00000625)":        DATA_DIR / "lobule_sixth_00000625.xdmf",
}

# IRCADb data
IRCADB_DIR = Path(
    os.environ.get(
        "VISFEM_IRCADB_DIR",
        Path(__file__).parents[3] / "visfem_data" / "3Dircadb1",
    )
)
IRCADB_PATIENTS: list[int] = sorted(
    int(d.name.split(".")[-1])
    for d in IRCADB_DIR.glob("3Dircadb1.*")
    if d.is_dir()
)

# Helpers
def _num_steps(path: Path) -> int:
    with meshio.xdmf.TimeSeriesReader(path) as reader:
        return reader.num_steps

def _ircadb_vtk_path(patient: int, organ: str) -> Path:
    return IRCADB_DIR / f"3Dircadb1.{patient}" / "MESHES_VTK" / f"{organ}.vtk"


# App
class VisfemApp(TrameApp):
    def __init__(self, server=None):
        super().__init__(server)
        self._setup_state()
        self._build_ui()

    # Initial state
    def _setup_state(self) -> None:
        self._step_counts: dict[str, int] = {
            name: _num_steps(path) for name, path in MESH_FILES.items()
        }

        fem_names = list(MESH_FILES.keys())
        initial_fem_name = fem_names[0]
        initial_fem_path = MESH_FILES[initial_fem_name]

        self.plotter = pv.Plotter(off_screen=True, theme=pv.themes.DarkTheme())
        self.pvmesh = load_mesh_from_timeseries(initial_fem_path, step=1)

        scalar_fields = get_field_names(initial_fem_path, step=1)
        initial_field = scalar_fields[0] if scalar_fields else None

        self.plotter.add_mesh(self.pvmesh, scalars=initial_field, show_edges=True, copy_mesh=False)
        self.plotter.reset_camera()

        initial_patient = IRCADB_PATIENTS[0] if IRCADB_PATIENTS else None
        initial_organs = get_organ_names(IRCADB_DIR, initial_patient) if initial_patient else []
        initial_organ = initial_organs[0] if initial_organs else None

        self.state.update({
            "mode": "fem",
            # FEM
            "fem_names": fem_names,
            "fem_name": initial_fem_name,
            "scalar_fields": scalar_fields,
            "scalar_field": initial_field,
            "step": 1,
            "num_steps": self._step_counts[initial_fem_name],
            # IRCADb
            "patient_names": [f"Patient {p}" for p in IRCADB_PATIENTS],
            "patient_name": f"Patient {initial_patient}" if initial_patient else "",
            "organ_names": initial_organs,
            "organ_name": initial_organ,
        })

    # Redraw helpers
    def _redraw_fem(self, mesh_name: str, field: str | None, step: int) -> None:
        mesh_path = MESH_FILES.get(mesh_name)
        if mesh_path is None or not mesh_path.exists():
            logger.error(f"Mesh file not found: {mesh_path}")
            return
        num_steps = self._step_counts[mesh_name]
        step = max(1, min(step, num_steps - 1))
        try:
            new_mesh = load_mesh_from_timeseries(mesh_path, step=step)
        except Exception as e:
            logger.error(f"Failed to load '{mesh_path.name}' at step {step}: {e}")
            return
        self.plotter.clear()
        self.pvmesh = new_mesh
        self.plotter.add_mesh(self.pvmesh, scalars=field, show_edges=True, copy_mesh=False)
        self.plotter.reset_camera()
        self.ctrl.view_push_camera()
        self.ctrl.view_update()

    def _redraw_ircadb(self, patient_name: str, organ: str | None) -> None:
        if not patient_name or not organ:
            return
        try:
            patient = int(patient_name.split()[-1])
        except ValueError:
            logger.error(f"Cannot parse patient number from '{patient_name}'")
            return
        vtk_path = _ircadb_vtk_path(patient, organ)
        if not vtk_path.exists():
            logger.error(f"Organ file not found: {vtk_path}")
            return
        try:
            new_mesh = load_mesh(vtk_path)
        except Exception as e:
            logger.error(f"Failed to load '{vtk_path.name}': {e}")
            return
        self.plotter.clear()
        self.pvmesh = new_mesh
        self.plotter.add_mesh(self.pvmesh, show_edges=True, copy_mesh=False)
        self.plotter.reset_camera()
        self.ctrl.view_push_camera()
        self.ctrl.view_update()

    # Button handlers — always redraw the current selection unconditionally

    def activate_fem(self) -> None:
        """Load button clicked — always redraws current FEM selection."""
        self.state.mode = "fem"
        mesh_name = self.state.fem_name
        mesh_path = MESH_FILES.get(mesh_name)
        if mesh_path is None or not mesh_path.exists():
            return
        num_steps = self._step_counts[mesh_name]
        self.state.num_steps = num_steps
        step = max(1, min(int(self.state.step), num_steps - 1))
        self.state.step = step
        scalar_fields = get_field_names(mesh_path, step=1)
        self.state.scalar_fields = scalar_fields
        current_field = self.state.scalar_field
        new_field = (
            current_field if current_field in scalar_fields
            else (scalar_fields[0] if scalar_fields else None)
        )
        self.state.scalar_field = new_field
        self._redraw_fem(mesh_name=mesh_name, field=new_field, step=step)

    def activate_ircadb(self) -> None:
        """Load button clicked — always redraws current IRCADb selection."""
        self.state.mode = "ircadb"
        patient_name = self.state.patient_name
        try:
            patient = int(patient_name.split()[-1])
        except ValueError:
            return
        organs = get_organ_names(IRCADB_DIR, patient)
        self.state.organ_names = organs
        current_organ = self.state.organ_name
        new_organ = current_organ if current_organ in organs else (organs[0] if organs else None)
        self.state.organ_name = new_organ
        self._redraw_ircadb(patient_name, new_organ)

    # @change callbacks — handle dropdown changes within the active mode
    @change("fem_name")
    def _on_fem_name_change(self, **_) -> None:
        if self.state.mode != "fem":
            return
        mesh_name = self.state.fem_name
        mesh_path = MESH_FILES.get(mesh_name)
        if mesh_path is None or not mesh_path.exists():
            return
        num_steps = self._step_counts[mesh_name]
        self.state.num_steps = num_steps
        step = max(1, min(int(self.state.step), num_steps - 1))
        self.state.step = step
        scalar_fields = get_field_names(mesh_path, step=1)
        self.state.scalar_fields = scalar_fields
        current_field = self.state.scalar_field
        new_field = (
            current_field if current_field in scalar_fields
            else (scalar_fields[0] if scalar_fields else None)
        )
        self.state.scalar_field = new_field
        self._redraw_fem(mesh_name=mesh_name, field=new_field, step=step)

    @change("scalar_field", "step")
    def _on_field_or_step_change(self, **_) -> None:
        if self.state.mode != "fem":
            return
        self._redraw_fem(
            mesh_name=self.state.fem_name,
            field=self.state.scalar_field,
            step=int(self.state.step),
        )

    @change("patient_name")
    def _on_patient_change(self, **_) -> None:
        if self.state.mode != "ircadb":
            return
        patient_name = self.state.patient_name
        try:
            patient = int(patient_name.split()[-1])
        except ValueError:
            return
        organs = get_organ_names(IRCADB_DIR, patient)
        self.state.organ_names = organs
        current_organ = self.state.organ_name
        new_organ = current_organ if current_organ in organs else (organs[0] if organs else None)
        self.state.organ_name = new_organ
        self._redraw_ircadb(patient_name, new_organ)

    @change("organ_name")
    def _on_organ_change(self, **_) -> None:
        if self.state.mode != "ircadb":
            return
        self._redraw_ircadb(self.state.patient_name, self.state.organ_name)

    # Camera
    def reset_camera(self) -> None:
        self.plotter.reset_camera()
        self.ctrl.view_push_camera()
        self.ctrl.reset_camera()

    # UI
    def _build_ui(self) -> None:
        with SinglePageWithDrawerLayout(self.server, theme="dark") as self.ui:
            self.ui.title.set_text("VisFEM")

            with self.ui.drawer as drawer:
                drawer.width = 260
                with v3.VContainer(classes="pa-4"):

                    # --- Liver Lobule section ---
                    v3.VListSubheader("Liver Lobule")
                    v3.VSelect(
                        v_model=("fem_name",),
                        items=("fem_names",),
                        density="compact",
                        hide_details=True,
                    )
                    v3.VSelect(
                        v_show=("mode === 'fem'",),
                        v_model=("scalar_field",),
                        items=("scalar_fields",),
                        label="Field",
                        density="compact",
                        hide_details=True,
                        classes="mt-2",
                    )
                    v3.VSlider(
                        v_show=("mode === 'fem'",),
                        v_model=("step",),
                        min=1,
                        max=("num_steps - 1",),
                        step=1,
                        label="Step",
                        thumb_label=True,
                        density="compact",
                        hide_details=True,
                        classes="mt-2",
                    )
                    # Load button
                    v3.VBtn(
                        "Load",
                        block=True,
                        color="primary",
                        density="compact",
                        classes="mt-3",
                        click=self.activate_fem,
                    )

                    v3.VDivider(classes="my-4")

                    # --- IRCADb section ---
                    v3.VListSubheader("3D-IRCADb-01")
                    v3.VSelect(
                        v_model=("patient_name",),
                        items=("patient_names",),
                        density="compact",
                        hide_details=True,
                    )
                    v3.VSelect(
                        v_show=("mode === 'ircadb'",),
                        v_model=("organ_name",),
                        items=("organ_names",),
                        label="Organ",
                        density="compact",
                        hide_details=True,
                        classes="mt-2",
                    )
                    # Load button
                    v3.VBtn(
                        "Load",
                        block=True,
                        color="primary",
                        density="compact",
                        classes="mt-3",
                        click=self.activate_ircadb,
                    )

            with self.ui.toolbar:
                v3.VSpacer()
                v3.VCheckbox(
                    v_model="$vuetify.theme.current.dark",
                    true_icon="mdi-weather-night",
                    false_icon="mdi-weather-sunny",
                    hide_details=True,
                    density="compact",
                )
                v3.VBtn(icon="mdi-crop-free", click=self.reset_camera)

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