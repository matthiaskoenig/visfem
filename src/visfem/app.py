"""Trame web application for FEM mesh visualization."""
import pyvista as pv
from trame.app import TrameApp
from trame.decorators import change
from trame.widgets.vtk import VtkWebXRHelper

from visfem.engine.colors import BG_DARK_BOTTOM, BG_DARK_TOP, BG_LIGHT_BOTTOM, BG_LIGHT_TOP
from visfem.engine.discovery import dataset_dir, discover_xdmf, group_by_organ_system, load_project_metadata
from visfem.engine.scene import apply_opacity
from visfem.engine.selection import select_dataset, select_patient, select_xdmf
from visfem.log import get_logger
from visfem.mesh import get_metadata
from visfem.models import MeshMetadata
from visfem.ui.layout import build_ui

logger = get_logger(__name__)


class VisfemApp(TrameApp):
    """Main Trame application for VisFEM."""

    def __init__(self, server: object = None) -> None:
        super().__init__(server)
        self._project_metadata = load_project_metadata()
        self._organ_groups = group_by_organ_system(self._project_metadata)
        self._xdmf_meta: dict[str, MeshMetadata] = {}
        for meta in self._project_metadata.values():
            for name, path in discover_xdmf(dataset_dir(meta)).items():
                self._xdmf_meta[name] = get_metadata(path)
        ircadb_meta = self._project_metadata.get("ircadb")
        ircadb_dir = dataset_dir(ircadb_meta) if ircadb_meta else None
        self._ircadb_patients: list[int] = sorted(
            int(d.name.split("_")[-1])
            for d in (ircadb_dir.glob("patient_*") if ircadb_dir else [])
            if d.is_dir()
        )
        self._setup_plotter()
        self._setup_state()
        self.ui = build_ui(
            server=self.server,
            plotter=self.plotter,
            ctrl=self.ctrl,
            organ_groups=self._organ_groups,
            ircadb_patients=self._ircadb_patients,
            on_select_dataset=self.select_dataset,
            on_select_xdmf=self.select_xdmf,
            on_select_patient=self.select_patient,
            on_toggle_theme=self.toggle_theme,
            on_reset_camera=self.reset_camera,
            on_toggle_xr=self.toggle_xr,
            on_enter_xr=self._on_enter_xr,
            on_exit_xr=self._on_exit_xr,
        )
        self.ctrl.on_client_connected.add(self._reset_xr_state)

    def _setup_plotter(self) -> None:
        """Initialize an empty off-screen plotter."""
        self.plotter = pv.Plotter(off_screen=True, theme=pv.themes.DarkTheme())
        self.plotter.enable_depth_peeling(number_of_peels=4)
        self.plotter.set_background(BG_DARK_BOTTOM, top=BG_DARK_TOP)

    def _setup_state(self) -> None:
        """Initialize all Trame state variables."""
        self.state.update({
            "dark_mode": True,
            "xr_active": False,
            "active_dataset": None,
            "active_patient": None,
            "active_xdmf": None,
            "panel_datasets_open": True,
            "panel_controls_open": True,
            "legend_items": [],
            "ctrl_opacity": 0.8,
            "active_meta": None,
            "mesh_stats": None,
            "panel_info_open": True,
        })

    # ---- Theme ----

    def toggle_theme(self) -> None:
        """Toggle between dark and light mode."""
        self.state.dark_mode = not self.state.dark_mode
        if self.state.dark_mode:
            self.plotter.set_background(BG_DARK_BOTTOM, top=BG_DARK_TOP)
        else:
            self.plotter.set_background(BG_LIGHT_BOTTOM, top=BG_LIGHT_TOP)
        self.ctrl.view_update()

    # ---- Camera ----

    def reset_camera(self) -> None:
        """Reset camera to fit current scene."""
        self.plotter.reset_camera()
        self.ctrl.view_push_camera()
        self.ctrl.reset_camera()

    # ---- XR ----

    def _reset_xr_state(self, **_kwargs: object) -> None:
        """Reset XR state on client reconnect."""
        self.state.xr_active = False

    def _on_enter_xr(self) -> None:
        """Called when XR session starts."""
        self.state.xr_active = True

    def _on_exit_xr(self) -> None:
        """Called when XR session ends."""
        self.state.xr_active = False
        self.ctrl.view_update()

    def toggle_xr(self) -> None:
        """Toggle WebXR session on/off."""
        if self.state.xr_active:
            self.ctrl.stop_xr()
        else:
            self.ctrl.start_xr(VtkWebXRHelper.XrSessionTypes.HmdVR)

    # ---- Reactive callbacks ----

    @change("ctrl_opacity")
    def _on_opacity_change(self, ctrl_opacity: float, **_: object) -> None:
        """Apply opacity to all actors when slider changes."""
        if self.state.active_dataset is None:
            return
        apply_opacity(self.plotter, float(ctrl_opacity))
        self.ctrl.view_update()

    # ---- Dataset selection ----

    def select_dataset(self, key: str) -> None:
        """Route to the correct redraw based on dataset key."""
        select_dataset(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta, key,
        )

    def select_xdmf(self, key: str, stem: str) -> None:
        """Load and render a specific XDMF file within a multi-file dataset."""
        select_xdmf(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta, key, stem,
        )

    def select_patient(self, patient: int) -> None:
        """Load and render a specific IRCADb patient."""
        select_patient(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, patient,
        )


def main() -> None:
    """Entry point."""
    app = VisfemApp()
    app.server.start()


if __name__ == "__main__":
    main()