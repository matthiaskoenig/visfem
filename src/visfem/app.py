"""Trame web application for FEM mesh visualization."""
import asyncio
import base64
import importlib.resources
import math
from pathlib import Path
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
from visfem.mesh import get_metadata, load_mesh
from visfem.models import MeshMetadata
from visfem.ui.layout import build_ui

logger = get_logger(__name__)

_TARGET_FRAMES: int = 30    # max rendered frames for autoplay
_FRAME_SLEEP: float = 0.2   # seconds between frames


class VisfemApp(TrameApp):
    """Main Trame application for VisFEM."""

    def __init__(self, server: object = None) -> None:
        super().__init__(server)
        self._fiber_actor: vtkActor | None = None
        self._initial_camera: object = None
        self._autoplay_task: asyncio.Task | None = None
        self._preload_task: asyncio.Task | None = None
        self._warmup_task: asyncio.Task | None = None
        self._warmup_gen: int = 0
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
            on_toggle_autoplay=self.toggle_autoplay,
            on_toggle_theme=self.toggle_theme,
            on_reset_camera=self.reset_camera,
            on_toggle_xr=self.toggle_xr,
            on_enter_xr=self._on_enter_xr,
            on_exit_xr=self._on_exit_xr,
            on_toggle_left_panel=self.toggle_left_panel,
            on_toggle_right_panel=self.toggle_right_panel,
            on_toggle_render_mode=self.toggle_render_mode,
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

    def reset_camera(self) -> None:
        """Restore the camera to the initial pose captured at dataset load."""
        if self._initial_camera is None:
            return
        self.plotter.camera_position = self._initial_camera
        self.ctrl.view_push_camera()
        self.ctrl.view_update()

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

    def toggle_render_mode(self) -> None:
        """Switch between local (browser WebGL) and remote (server JPEG stream) rendering."""
        self.state.render_mode = "remote" if self.state.render_mode == "local" else "local"
        self.ctrl.view_update()

    def toggle_xr(self) -> None:
        """Toggle WebXR session on/off."""
        if self.state.xr_active:
            self.ctrl.stop_xr()
        else:
            self.ctrl.start_xr(VtkWebXRHelper.XrSessionTypes.HmdVR)

    # ---- Step pre-loading ----

    def _cancel_preload(self) -> None:
        if self._preload_task is not None and not self._preload_task.done():
            self._preload_task.cancel()
        self._preload_task = None

    async def _preload_steps(self, path: Path, steps: list[int]) -> None:
        loop = asyncio.get_running_loop()
        for step in steps:
            try:
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                return
            try:
                await loop.run_in_executor(None, load_mesh, path, step)
            except Exception:
                pass

    def _cancel_warmup(self) -> None:
        self._warmup_gen += 1
        if self._warmup_task is not None and not self._warmup_task.done():
            self._warmup_task.cancel()
        self._warmup_task = None
        self.state.loading = False

    def _start_vtkjs_warmup(self) -> None:
        n_steps = int(self.state.n_steps)
        if n_steps <= 1:
            with self.state:
                self.state.step_inc = 1
                self.state.loading = False
            return
        inc = math.ceil(n_steps / _TARGET_FRAMES)
        self.state.step_inc = inc
        gen = self._warmup_gen
        self._warmup_task = asyncio.ensure_future(self._vtkjs_warmup(gen))

    async def _vtkjs_warmup(self, gen: int) -> None:
        n_steps = int(self.state.n_steps)
        if n_steps <= 1:
            return
        inc = math.ceil(n_steps / _TARGET_FRAMES)
        steps = list(range(0, n_steps, inc))
        try:
            for step in steps:
                await asyncio.sleep(0)
                select_step(self.plotter, self.ctrl, self.state,
                            self._project_metadata, self._xdmf_meta, step)
                with self.state:
                    self.state.active_step = 0  # keep slider pinned at 0 during warmup
                await asyncio.sleep(0.04)
            if int(self.state.active_step) != 0:
                select_step(self.plotter, self.ctrl, self.state,
                            self._project_metadata, self._xdmf_meta, 0)
                with self.state:
                    pass
        finally:
            if self._warmup_gen == gen:
                with self.state:
                    self.state.loading = False

    def _start_preload_from_state(self) -> None:
        n_steps = int(self.state.n_steps)
        if n_steps <= 1:
            return
        key: str | None = self.state.active_dataset
        if not key or key not in self._project_metadata:
            return
        meta = self._project_metadata[key]
        if meta.mesh_format == "PVD":
            path = pvd_file_path(meta)
        else:
            stem: str | None = self.state.active_xdmf
            xdmf_files = discover_xdmf(dataset_dir(meta))
            path = xdmf_files.get(stem) if stem else next(iter(xdmf_files.values()), None)
        if path is None:
            return
        inc = math.ceil(n_steps / _TARGET_FRAMES)
        steps = list(range(inc, n_steps, inc))  # step 0 already loaded by initial render
        if not steps:
            return
        self._cancel_preload()
        self._preload_task = asyncio.ensure_future(self._preload_steps(path, steps))

    # ---- Reactive callbacks ----

    @change("ctrl_opacity")
    def _on_opacity_change(self, ctrl_opacity: float, **_: object) -> None:
        """Apply opacity to all actors when slider changes."""
        if self.state.active_dataset is None:
            return
        apply_opacity(self.plotter, float(ctrl_opacity))
        self.ctrl.view_update()

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
        self.state.flush()
        await asyncio.sleep(0.05)
        self._fiber_actor = select_dataset(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta, key,
        )
        self._initial_camera = self.plotter.camera_position
        self._start_preload_from_state()
        self._start_vtkjs_warmup()

    async def select_xdmf(self, key: str, stem: str) -> None:
        """Load and render a specific XDMF file within a multi-file dataset."""
        self.state.autoplay = False
        self._cancel_warmup()
        self._cancel_preload()
        self.state.loading = True
        self.state.flush()
        await asyncio.sleep(0.05)
        select_xdmf(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, self._xdmf_meta, key, stem,
        )
        self._initial_camera = self.plotter.camera_position
        self._start_preload_from_state()
        self._start_vtkjs_warmup()

    async def select_patient(self, dataset_key: str, patient: int) -> None:
        """Load and render a specific patient from a multi-patient dataset."""
        self.state.autoplay = False
        self._cancel_warmup()
        self._cancel_preload()
        self.state.loading = True
        self.state.flush()
        await asyncio.sleep(0.05)
        select_patient(
            self.plotter, self.ctrl, self.state,
            self._project_metadata, dataset_key, patient,
        )
        self._initial_camera = self.plotter.camera_position
        self._start_vtkjs_warmup()

    def select_scalar_field(self, field: str) -> None:
        """Re-render the current dataset with the given scalar field."""
        self.state.autoplay = False
        self._cancel_warmup()
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
        self._cancel_warmup()
        if self.state.autoplay:
            self.state.autoplay = False
        else:
            # Guard against double-start while previous task winds down.
            if self._autoplay_task is not None and not self._autoplay_task.done():
                return
            self.state.autoplay = True
            self._autoplay_task = asyncio.ensure_future(self._autoplay_loop())

    async def _autoplay_loop(self) -> None:
        """Advance one step at a time until stopped or end."""
        try:
            while self.state.autoplay:
                step = int(self.state.active_step)
                n = int(self.state.n_steps)
                inc = int(self.state.step_inc)
                next_step = 0 if step + inc >= n else step + inc
                select_step(
                    self.plotter, self.ctrl, self.state,
                    self._project_metadata, self._xdmf_meta, next_step,
                )
                with self.state:
                    pass
                await asyncio.sleep(_FRAME_SLEEP)
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