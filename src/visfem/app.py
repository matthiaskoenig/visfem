"""Trame web application for FEM mesh visualization."""
import asyncio
import base64
import importlib.resources
import math
import pyvista as pv
from trame.app import TrameApp
from trame.decorators import change
from trame.widgets.vtk import VtkWebXRHelper
from vtkmodules.vtkRenderingCore import vtkActor

from visfem.engine.colors import BG_DARK_BOTTOM, BG_DARK_TOP, BG_LIGHT_BOTTOM, BG_LIGHT_TOP
from visfem.engine.discovery import dataset_dir, discover_xdmf, group_by_organ_system, load_project_metadata, pvd_file_path
from visfem.engine.scene import apply_opacity
from visfem.engine.palettes import CATEGORICAL_META, CONTINUOUS_META
from visfem.engine.selection import (
    select_color_scheme, select_dataset, select_patient,
    select_scalar_field, select_step, select_xdmf,
)
from visfem.log import get_logger
from visfem.mesh import get_metadata
from visfem.models import MeshMetadata
from visfem.ui.layout import build_ui

logger = get_logger(__name__)


class VisfemApp(TrameApp):
    """Main Trame application for VisFEM."""

    def __init__(self, server: object = None) -> None:
        super().__init__(server)
        self._fiber_actor: vtkActor | None = None
        self._autoplay_task: asyncio.Task | None = None
        self._project_metadata = load_project_metadata()
        self._organ_groups = group_by_organ_system(self._project_metadata)
        self._xdmf_meta: dict[str, MeshMetadata] = {}
        for meta in self._project_metadata.values():
            for name, path in discover_xdmf(dataset_dir(meta)).items():
                self._xdmf_meta[name] = get_metadata(path)
        for meta in self._project_metadata.values():
            p = pvd_file_path(meta)
            if p and p.exists():
                self._xdmf_meta[p.stem] = get_metadata(p)
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
            on_select_scalar_field=self.select_scalar_field,
            on_select_step=self.select_step,
            on_select_color_scheme=self.select_color_scheme,
            on_toggle_autoplay=self.toggle_autoplay,
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

    @staticmethod
    def _favicon_data_uri() -> str:
        data = importlib.resources.files("visfem.assets").joinpath("favicon.png").read_bytes()
        return f"data:image/png;base64,{base64.b64encode(data).decode()}"

    def _setup_state(self) -> None:
        """Initialize all Trame state variables."""
        self.state.update({
            "trame__title": "VisFEM",
            "trame__favicon": self._favicon_data_uri(),
            "dark_mode": True,
            "xr_active": False,
            "active_dataset": None,
            "active_patient": None,
            "active_xdmf": None,
            "panel_datasets_open": True,
            "legend_items": [],
            "ctrl_opacity": 0.9,
            "active_meta": None,
            "mesh_stats": None,
            "panel_info_open": True,
            "show_fibers": False,
            "scalar_bar": None,
            "available_scalar_fields": [],
            "active_scalar_field": None,
            "n_steps": 1,
            "active_step": 0,
            "step_times": [],
            "autoplay": False,
            "active_categorical_palette": "paired",
            "active_continuous_cmap": "viridis",
            "categorical_palette_meta": CATEGORICAL_META,
            "continuous_cmap_meta": CONTINUOUS_META,
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

    @change("show_fibers")
    def _on_show_fibers_change(self, show_fibers: bool, **_: object) -> None:
        """Toggle fiber glyph actor visibility."""
        if self._fiber_actor is None:
            return
        self._fiber_actor.SetVisibility(bool(show_fibers))
        self.ctrl.view_update()

    # ---- Dataset selection ----

    def select_dataset(self, key: str) -> None:
        """Route to the correct redraw based on dataset key."""
        self.state.autoplay = False  # stop any running autoplay before switching
        self._fiber_actor = select_dataset(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta, key,
        )

    def select_xdmf(self, key: str, stem: str) -> None:
        """Load and render a specific XDMF file within a multi-file dataset."""
        self.state.autoplay = False  # stop any running autoplay before switching
        select_xdmf(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta, key, stem,
        )

    def select_patient(self, patient: int) -> None:
        """Load and render a specific IRCADb patient."""
        self.state.autoplay = False  # stop any running autoplay before switching
        select_patient(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, patient,
        )

    def select_scalar_field(self, field: str) -> None:
        """Re-render the current dataset with the given scalar field."""
        self.state.autoplay = False  # stop autoplay and reset slider on field change
        self.state.active_step = 0
        select_scalar_field(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta, field,
        )

    def select_step(self, step: int) -> None:
        """Navigate the current XDMF dataset to a different timestep."""
        select_step(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta, int(step),
        )

    def select_color_scheme(self, name: str) -> None:
        """Update the active palette/colormap and re-render the current scene."""
        if self.state.active_dataset is None:
            return
        if self.state.scalar_bar is not None:
            self.state.active_continuous_cmap = name
        else:
            self.state.active_categorical_palette = name
        select_color_scheme(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta,
        )

    # ---- Autoplay ----

    def toggle_autoplay(self) -> None:
        """Start or stop automatic step playback."""
        if self.state.autoplay:
            self.state.autoplay = False
            # The running task checks autoplay on each iteration and will exit.
        else:
            # Guard against creating a second task while one is still winding down.
            if self._autoplay_task is not None and not self._autoplay_task.done():
                return
            self.state.autoplay = True
            self._autoplay_task = asyncio.ensure_future(self._autoplay_loop())

    async def _autoplay_loop(self) -> None:
        """Async task: advance one step at a time until stopped or end.

        Running inside Trame's aiohttp event loop means ctrl.view_update() and
        state writes are in the correct context.  However, state changes made
        inside the task are NOT automatically pushed to the client the way they
        are after a normal RPC callback — we must use `with self.state:` to
        explicitly flush dirty variables (active_step, scalar_bar, trame__busy,
        …) so the slider and time label update in real time.
        """
        try:
            while self.state.autoplay:
                step = int(self.state.active_step)
                n = int(self.state.n_steps)
                # Target ~100 rendered frames; increment >1 for large datasets.
                inc = math.ceil(n / 100)
                next_step = 0 if step + inc >= n else step + inc
                select_step(
                    self.plotter, self.ctrl, self.state,
                    self._project_metadata, self._xdmf_meta, next_step,
                )
                # Flush all dirty state variables to connected clients.
                # Without this, active_step / trame__busy etc. accumulate and
                # are only pushed when the next WebSocket message arrives
                # (e.g. the user clicks Stop), making the slider appear frozen.
                with self.state:
                    pass
                # Push the updated VTK scene after flushing state — the two
                # channels are independent and must both be triggered explicitly
                # inside an async task.
                self.ctrl.view_update()
                # Yield to the event loop so Trame can send the queued messages
                # (VTK scene + state) to the browser before the next render.
                await asyncio.sleep(0.15)
        finally:
            self.state.autoplay = False

    def sync_camera(self, camera: dict) -> None:
        """Sync client camera state to server plotter."""
        cam = self.plotter.camera
        cam.SetPosition(*camera["position"])
        cam.SetFocalPoint(*camera["focalPoint"])
        cam.SetViewUp(*camera["viewUp"])
        cam.SetParallelProjection(camera["parallelProjection"])
        cam.SetParallelScale(camera["parallelScale"])
        cam.SetViewAngle(camera["viewAngle"])
        self.plotter.renderer.ResetCameraClippingRange()

    def _on_camera_sync(self, **kwargs: object) -> None:
        """Keep server camera in sync with client on every interaction."""
        self.plotter.camera.position = kwargs["position"]
        self.plotter.camera.focal_point = kwargs["focalPoint"]
        self.plotter.camera.up = kwargs["viewUp"]
        self.plotter.renderer.ResetCameraClippingRange()


def main() -> None:
    """Entry point."""
    app = VisfemApp()
    app.server.start()


if __name__ == "__main__":
    main()