"""Trame web application for FEM mesh visualization."""
import asyncio
import base64
import importlib.resources
import math
from pathlib import Path
import pyvista as pv
from trame.app import TrameApp
from trame.decorators import change

from visfem.engine.colors import BG_DARK_BOTTOM, BG_DARK_TOP, BG_LIGHT_BOTTOM, BG_LIGHT_TOP
from visfem.engine.discovery import dataset_dir, discover_xdmf, group_by_organ_system, load_project_metadata, pvd_file_path
from visfem.engine.playback import autoplay_loop, preload_steps, vtkjs_warmup
from visfem.engine.scene import apply_opacity, update_scalar_range
from visfem.engine.xr_manager import XRManager
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

_TARGET_FRAMES: int = 30    # max rendered frames for autoplay
_FRAME_SLEEP: float = 0.2   # seconds between frames


class VisfemApp(TrameApp):
    """Main Trame application for VisFEM."""

    def __init__(self, server: object = None) -> None:
        """Load project metadata, build plotter and state, assemble UI."""
        super().__init__(server)
        self._fiber_actor = None
        self._initial_camera: object = None
        self._autoplay_task: asyncio.Task | None = None
        self._preload_task: asyncio.Task | None = None
        self._warmup_task: asyncio.Task | None = None
        self._warmup_gen: int = 0
        self._opacity_task: asyncio.Task | None = None
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
        self._patients_by_dataset: dict[str, list[int]] = {}
        for key, meta in self._project_metadata.items():
            ddir = dataset_dir(meta)
            patients = sorted(
                int(d.name.split("_")[-1])
                for d in ddir.glob("patient_*")
                if d.is_dir()
            )
            if patients:
                self._patients_by_dataset[key] = patients
        self._setup_plotter()
        self._setup_state()
        self.xr = XRManager(self.plotter, self.state, self.ctrl)
        self.ui = build_ui(
            server=self.server,
            plotter=self.plotter,
            ctrl=self.ctrl,
            organ_groups=self._organ_groups,
            patients_by_dataset=self._patients_by_dataset,
            on_select_dataset=self.select_dataset,
            on_select_xdmf=self.select_xdmf,
            on_select_patient=self.select_patient,
            on_select_scalar_field=self.select_scalar_field,
            on_select_step=self.select_step,
            on_select_color_scheme=self.select_color_scheme,
            on_toggle_color_reversed=self.toggle_color_reversed,
            on_toggle_autoplay=self.toggle_autoplay,
            on_toggle_theme=self.toggle_theme,
            on_reset_camera=self.reset_camera,
            on_toggle_xr=self.xr.toggle_xr,
            on_enter_xr=self.xr.on_enter_xr,
            on_exit_xr=self.xr.on_exit_xr,
            on_toggle_left_panel=self.toggle_left_panel,
            on_toggle_right_panel=self.toggle_right_panel,
            on_toggle_render_mode=self.toggle_render_mode,
            on_take_screenshot=self.take_screenshot,
            on_apply_clim=self.apply_clim_override,
        )
        self.ctrl.on_client_connected.add(lambda **_: self.xr.reset_on_reconnect())

    def _setup_plotter(self) -> None:
        """Initialize an empty off-screen plotter."""
        self.plotter = pv.Plotter(off_screen=True, theme=pv.themes.DarkTheme())
        self.plotter.enable_depth_peeling(number_of_peels=4)
        self.plotter.set_background(BG_DARK_BOTTOM, top=BG_DARK_TOP)
        # Physical scale is NOT set here: Python SetPhysicalScale does not propagate to the
        # vtk.js client via the trame-vtk sync protocol. The JS selectstart handler already
        # multiplies XR metres by 1000 to match VTK world mm, which is the correct transform.

    @staticmethod
    def _favicon_data_uri() -> str:
        """Return the favicon as a base64 data URI for the browser tab."""
        data = importlib.resources.files("visfem.assets").joinpath("favicon.png").read_bytes()
        return f"data:image/png;base64,{base64.b64encode(data).decode()}"

    def _setup_state(self) -> None:
        """Initialize all Trame state variables."""
        self.state.update({
            "trame__title": "VisFEM",
            "trame__favicon": self._favicon_data_uri(),
            "dark_mode": True,
            "xr_active": False,
            "xr_session_ended": False,
            "active_dataset": None,
            "active_patient": None,
            "active_xdmf": None,
            "left_panel_open": True,
            "right_panel_open": True,
            "active_organ_group_open": [],
            "left_datasets_section_open": True,
            "left_info_section_open": True,
            "right_view_open": True,
            "right_fibers_open": True,
            "right_scalar_field_open": True,
            "right_color_open": True,
            "right_playback_open": True,
            "right_scalar_bar_open": True,
            "right_regions_open": True,
            "legend_items": [],
            "ctrl_opacity": 0.9,
            "active_meta": None,
            "mesh_stats": None,
            "show_fibers": False,
            "scalar_bar": None,
            "available_scalar_fields": [],
            "active_scalar_field": None,
            "n_steps": 1,
            "active_step": 0,
            "step_inc": 1,
            "step_times": [],
            "autoplay": False,
            "active_categorical_palette": "paired",
            "active_continuous_cmap": "viridis",
            "categorical_palette_meta": CATEGORICAL_META,
            "continuous_cmap_meta": CONTINUOUS_META,
            "render_mode": "local",
            "fullscreen": False,
            "loading": False,
            "busy": False,
            "camera_resetting": False,
            "color_reversed": False,
            "exit_btn_pos": [0.0, 0.0, 0.0],
            "xr_exit_triggered": False,
            "clim_input_min": "",
            "clim_input_max": "",
            "clim_override": None,
            "opacity_adjusting": False,
        })

    # ---- Panel toggles ----

    def toggle_left_panel(self) -> None:
        """Toggle the left dataset panel open/closed."""
        self.state.left_panel_open = not self.state.left_panel_open

    def toggle_right_panel(self) -> None:
        """Toggle the right view-controls panel open/closed."""
        self.state.right_panel_open = not self.state.right_panel_open

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

    async def reset_camera(self) -> None:
        """Restore the camera to the initial pose captured at dataset load."""
        if self._initial_camera is None:
            return
        if self.state.busy:
            return
        self.state.busy = True
        self.state.camera_resetting = True
        self.state.flush()
        await asyncio.sleep(0.05)
        self.plotter.camera_position = self._initial_camera
        self.ctrl.view_push_camera()
        self.ctrl.view_update()
        # Hold the spinner for a fixed window; the server has no callback for when the client finishes the WebGL re-render on the new camera pose.
        await asyncio.sleep(0.4)
        self.state.camera_resetting = False
        self.state.busy = False

    def take_screenshot(self) -> None:
        """Trigger vtk.js canvas capture and browser PNG download."""
        self.ctrl.capture_screenshot()

    # ---- XR (delegated to XRManager) ----

    @change("xr_exit_triggered")
    def _on_xr_exit_triggered(self, xr_exit_triggered: bool, **_: object) -> None:
        self.xr.on_exit_triggered(xr_exit_triggered)

    @change("xr_session_ended")
    def _on_xr_session_ended(self, xr_session_ended: bool, **_: object) -> None:
        self.xr.on_session_ended(xr_session_ended)

    @change("scalar_bar")
    def _on_scalar_bar_change(self, scalar_bar: dict | None, **_: object) -> None:
        """Keep clim text inputs in sync whenever scalar_bar is updated anywhere."""
        if scalar_bar:
            # If the user has set a manual override, preserve their input values.
            if getattr(self.state, "clim_override", None) is None:
                self.state.clim_input_min = scalar_bar.get("min_label", "")
                self.state.clim_input_max = scalar_bar.get("max_label", "")
        else:
            self.state.clim_input_min = ""
            self.state.clim_input_max = ""
            self.state.clim_override = None

    def apply_clim_override(self) -> None:
        """Apply user-entered scalar range to the active continuous field."""
        if self.state.scalar_bar is None:
            return
        try:
            lo = float(self.state.clim_input_min)
            hi = float(self.state.clim_input_max)
        except ValueError:
            return
        if lo >= hi:
            return
        field = self.state.active_scalar_field
        if not field:
            return
        cmap = str(self.state.active_continuous_cmap)
        if self.state.color_reversed:
            cmap += "_r"
        scalar_bar = update_scalar_range(self.plotter, self.ctrl, field, [lo, hi], cmap)
        if scalar_bar:
            self.state.clim_override = [lo, hi]
            self.state.scalar_bar = scalar_bar

    def toggle_render_mode(self) -> None:
        """Switch between local (browser WebGL) and remote (server JPEG stream) rendering."""
        self.state.render_mode = "remote" if self.state.render_mode == "local" else "local"
        self.ctrl.view_update()

    # ---- Step pre-loading ----

    def _cancel_preload(self) -> None:
        """Cancel any running background step-preload task."""
        if self._preload_task is not None and not self._preload_task.done():
            self._preload_task.cancel()
        self._preload_task = None

    def _cancel_warmup(self) -> None:
        """Cancel any running vtk.js warmup task and clear the loading flag."""
        self._warmup_gen += 1
        if self._warmup_task is not None and not self._warmup_task.done():
            self._warmup_task.cancel()
        self._warmup_task = None
        self.state.loading = False
        self.state.busy = False

    def _resolve_active_path(self) -> Path | None:
        """Return the XDMF/PVD file path for the currently active dataset."""
        key: str | None = self.state.active_dataset
        if not key or key not in self._project_metadata:
            return None
        meta = self._project_metadata[key]
        if meta.mesh_format == "PVD":
            return pvd_file_path(meta)
        stem: str | None = self.state.active_xdmf
        xdmf_files = discover_xdmf(dataset_dir(meta))
        return xdmf_files.get(stem) if stem else next(iter(xdmf_files.values()), None)

    def _start_vtkjs_warmup(self) -> None:
        """Start the mesh-cache warmup task, or clear loading immediately for static datasets."""
        n_steps = int(self.state.n_steps)
        if n_steps <= 1:
            with self.state:
                self.state.step_inc = 1
                self.state.loading = False
                self.state.busy = False
            return
        inc = math.ceil(n_steps / _TARGET_FRAMES)
        self.state.step_inc = inc
        path = self._resolve_active_path()
        if path is None:
            with self.state:
                self.state.loading = False
                self.state.busy = False
            return
        gen = self._warmup_gen
        self._warmup_task = asyncio.ensure_future(
            vtkjs_warmup(gen, lambda: self._warmup_gen, self.state, path, _TARGET_FRAMES)
        )

    def _start_preload_from_state(self) -> None:
        """Kick off background preloading for all keyframes of the currently active dataset."""
        n_steps = int(self.state.n_steps)
        if n_steps <= 1:
            return
        path = self._resolve_active_path()
        if path is None:
            return
        inc = math.ceil(n_steps / _TARGET_FRAMES)
        steps = list(range(inc, n_steps, inc))  # step 0 already loaded by initial render
        if not steps:
            return
        self._cancel_preload()
        self._preload_task = asyncio.ensure_future(preload_steps(path, steps))

    # ---- Reactive callbacks ----

    @change("ctrl_opacity")
    def _on_opacity_change(self, ctrl_opacity: float, **_: object) -> None:
        """Show feedback immediately; debounce the actual render for heavy meshes."""
        if self.state.active_dataset is None:
            return
        if self._opacity_task is not None and not self._opacity_task.done():
            self._opacity_task.cancel()
        self.state.opacity_adjusting = True
        self._opacity_task = asyncio.ensure_future(
            self._apply_opacity_debounced(float(ctrl_opacity))
        )

    async def _apply_opacity_debounced(self, opacity: float) -> None:
        """Apply opacity 150 ms after the last slider movement."""
        try:
            await asyncio.sleep(0.15)
        except asyncio.CancelledError:
            return  # Still debouncing; new task is already queued — leave spinner up
        try:
            apply_opacity(self.plotter, opacity)
            # Geometry-only push: skips server-side VTK render (depth peeling × 4 passes).
            # In local mode the browser re-renders with the new opacity value itself.
            if self.state.render_mode == "local":
                self.ctrl.view_update_geometry()
            else:
                self.ctrl.view_update()
        finally:
            self.state.opacity_adjusting = False
            self.state.flush()

    @change("active_organ_group_open")
    def _on_organ_group_change(self, active_organ_group_open: list, **_: object) -> None:
        """Accordion: keep only the most-recently-opened organ system group open."""
        top_level = set(self._organ_groups.keys())
        open_top = [v for v in active_organ_group_open if v in top_level]
        if len(open_top) > 1:
            keep = open_top[-1]
            self.state.active_organ_group_open = [
                v for v in active_organ_group_open if v not in top_level or v == keep
            ]

    @change("show_fibers")
    def _on_show_fibers_change(self, show_fibers: bool, **_: object) -> None:
        """Toggle fiber glyph actor visibility."""
        if self._fiber_actor is None:
            return
        self._fiber_actor.SetVisibility(bool(show_fibers))
        self.ctrl.view_update()

    # ---- Dataset selection ----

    async def select_dataset(self, key: str) -> None:
        """Route to the correct redraw based on dataset key."""
        self.state.autoplay = False
        self._cancel_warmup()
        self._cancel_preload()
        self.state.loading = True
        self.state.busy = True
        self.state.flush()
        await asyncio.sleep(0.05)
        self._fiber_actor = select_dataset(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta, key,
        )
        apply_opacity(self.plotter, float(self.state.ctrl_opacity))
        self._initial_camera = self.plotter.camera_position
        self._start_vtkjs_warmup()

    async def select_xdmf(self, key: str, stem: str) -> None:
        """Load and render a specific XDMF file within a multi-file dataset."""
        self.state.autoplay = False
        self._cancel_warmup()
        self._cancel_preload()
        self.state.loading = True
        self.state.busy = True
        self.state.flush()
        await asyncio.sleep(0.05)
        select_xdmf(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta, key, stem,
        )
        apply_opacity(self.plotter, float(self.state.ctrl_opacity))
        self._initial_camera = self.plotter.camera_position
        self._start_vtkjs_warmup()

    async def select_patient(self, dataset_key: str, patient: int) -> None:
        """Load and render a specific patient from a multi-patient dataset."""
        self.state.autoplay = False
        self._cancel_warmup()
        self._cancel_preload()
        self.state.loading = True
        self.state.busy = True
        self.state.flush()
        await asyncio.sleep(0.05)
        select_patient(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, dataset_key, patient,
        )
        apply_opacity(self.plotter, float(self.state.ctrl_opacity))
        self._initial_camera = self.plotter.camera_position
        self._start_vtkjs_warmup()

    async def select_scalar_field(self, field: str) -> None:
        """Re-render the current dataset with the given scalar field."""
        if self.state.busy:
            return
        self.state.autoplay = False
        self._cancel_warmup()
        self.state.active_step = 0
        self.state.clim_override = None
        self.state.busy = True
        self.state.flush()
        await asyncio.sleep(0.05)
        select_scalar_field(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta, field,
        )
        self.state.busy = False

    async def select_step(self, step: int) -> None:
        """Navigate the current XDMF dataset to a different timestep."""
        if self.state.busy:
            return
        self.state.busy = True
        self.state.flush()
        await asyncio.sleep(0)
        select_step(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta, int(step),
        )
        self.state.busy = False

    async def toggle_color_reversed(self) -> None:
        """Flip the color order of the active palette or colormap and re-render."""
        if self.state.active_dataset is None:
            return
        if self.state.busy:
            return
        self.state.color_reversed = not self.state.color_reversed
        self.state.clim_override = None
        self.state.busy = True
        self.state.flush()
        await asyncio.sleep(0.05)
        select_color_scheme(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta,
        )
        self.state.busy = False

    async def select_color_scheme(self, name: str) -> None:
        """Update the active palette/colormap and re-render the current scene."""
        if self.state.active_dataset is None:
            return
        if self.state.busy:
            return
        if self.state.scalar_bar is not None:
            self.state.active_continuous_cmap = name
        else:
            self.state.active_categorical_palette = name
        self.state.clim_override = None
        self.state.busy = True
        self.state.flush()
        await asyncio.sleep(0.05)
        select_color_scheme(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta,
        )
        self.state.busy = False

    # ---- Autoplay ----

    def toggle_autoplay(self) -> None:
        """Start or stop automatic step playback."""
        self._cancel_warmup()
        if self.state.autoplay:
            self.state.autoplay = False
        else:
            # Guard against double-start while previous task winds down.
            if self._autoplay_task is not None and not self._autoplay_task.done():
                return
            self.state.autoplay = True
            self._autoplay_task = asyncio.ensure_future(
                autoplay_loop(
                    self.state, self.plotter, self.ctrl,
                    self._project_metadata, self._xdmf_meta,
                    _FRAME_SLEEP,
                )
            )

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