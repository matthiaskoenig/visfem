"""Trame web application for FEM mesh visualization.

Usage: visfem, or python -m visfem.app. VISFEM_PRELOAD=1 preloads every mesh;
VISFEM_LOG_LEVEL sets the log level (default WARNING).
"""

import asyncio
import base64
import contextlib
import importlib.resources
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pyvista as pv
from trame.app import TrameApp
from trame.decorators import change
from vtkmodules.vtkRenderingCore import vtkActor

from visfem.engine.colors import (
    BG_DARK_BOTTOM,
    BG_DARK_TOP,
    BG_LIGHT_BOTTOM,
    BG_LIGHT_TOP,
    clear_overrides,
    set_override,
)
from visfem.engine.discovery import (
    active_timeseries_path,
    dataset_dir,
    discover_xdmf,
    grasp_phase_pvd,
    group_by_organ_system,
    load_project_metadata,
    patient_numbers,
    patient_subdir,
    pvd_file_path,
)
from visfem.engine.palettes import CATEGORICAL_META, CONTINUOUS_META
from visfem.engine.playback import (
    autoplay_loop,
    clear_overlay,
    keyframe_increment,
    vtkjs_warmup,
)
from visfem.engine.scene import (
    Scene,
    TrameCtrl,
    apply_opacity,
    push_scene,
    update_scalar_range,
)
from visfem.engine.selection import (
    recolor_categories,
    resolve_cmap,
    select_color_scheme,
    select_dataset,
    select_patient,
    select_scalar_field,
    select_step,
    select_xdmf,
)
from visfem.engine.xr_manager import XRManager
from visfem.log import get_logger
from visfem.mesh import get_metadata, preload_all_meshes, vtk_series_steps
from visfem.models import MeshMetadata, ProjectMetadata
from visfem.ui.layout import UICallbacks, build_ui

logger = get_logger(__name__)

_FRAME_SLEEP: float = 0.2  # seconds between frames of a scalar-field timeseries
# A GRASP phase is a full redraw; the slower cadence keeps the contrast wash-in watchable.
_PHASE_FRAME_SLEEP: float = 0.7  # seconds per phase
# Overlay hold after a geometry push; the timer is the server's only end-of-paint signal.
_RENDER_SETTLE_MIN: float = 2.0  # seconds, smallest meshes
_RENDER_SETTLE_MAX: float = 7.0  # seconds, cap for the largest
_RENDER_SETTLE_PER_MCELL: float = 1.4  # extra seconds per million cells


class VisfemApp(TrameApp):
    """Main Trame application for VisFEM."""

    def __init__(self, server: object = None) -> None:
        """Load project metadata, build plotter and state, assemble the UI on *server*."""
        super().__init__(server)
        self._fiber_actor = None
        self._initial_camera: pv.CameraPosition | None = None
        self._autoplay_task: asyncio.Task | None = None
        self._warmup_task: asyncio.Task | None = None
        self._url_select_task: asyncio.Task | None = None
        self._warmup_gen: int = 0
        self._opacity_task: asyncio.Task | None = None
        self._project_metadata = load_project_metadata()
        self._organ_groups = group_by_organ_system(self._project_metadata)
        self._xdmf_meta: dict[str, MeshMetadata] = {}
        for key, meta in self._project_metadata.items():
            series = list(discover_xdmf(dataset_dir(meta)).items())
            pvd = pvd_file_path(meta)
            if pvd and pvd.exists():
                series.append((pvd.stem, pvd))
            for name, path in series:
                try:
                    self._xdmf_meta[name] = get_metadata(path)
                except Exception as e:  # noqa: BLE001 - skip the corrupt file and keep serving
                    logger.warning(
                        "Dataset '%s': skipping '%s', metadata read failed: %s",
                        key,
                        path.name,
                        e,
                    )
        self._patients_by_dataset: dict[str, list[int]] = {}
        for key, meta in self._project_metadata.items():
            patients = patient_numbers(dataset_dir(meta))
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
            callbacks=UICallbacks(
                on_select_dataset=self.select_dataset,
                on_select_xdmf=self.select_xdmf,
                on_select_patient=self.select_patient,
                on_select_scalar_field=self.select_scalar_field,
                on_select_step=self.select_step,
                on_select_color_scheme=self.select_color_scheme,
                on_toggle_color_reversed=self.toggle_color_reversed,
                on_set_category_color=self.set_category_color,
                on_reset_category_colors=self.reset_category_colors,
                on_apply_clim=self.apply_clim_override,
                on_toggle_autoplay=self.toggle_autoplay,
                on_toggle_theme=self.toggle_theme,
                on_toggle_left_panel=self.toggle_left_panel,
                on_toggle_right_panel=self.toggle_right_panel,
                on_take_screenshot=self.take_screenshot,
                on_reset_camera=self.reset_camera,
                on_toggle_xr=self.xr.toggle_xr,
                on_enter_xr=self.xr.on_enter_xr,
                on_exit_xr=self.xr.on_exit_xr,
            ),
        )
        self.ctrl.on_client_connected.add(lambda **_: self.xr.reset_on_reconnect())

    def _setup_plotter(self) -> None:
        """Initialize an empty off-screen plotter."""
        self.plotter = pv.Plotter(off_screen=True, theme=pv.themes.DarkTheme())
        # typeshed types the functools.wraps wrappers of Plotter as unbound methods,
        # the renderers are called directly where possible.
        self.plotter.enable_depth_peeling(number_of_peels=4)  # ty: ignore[missing-argument]
        self.plotter.renderers.set_background(BG_DARK_BOTTOM, top=BG_DARK_TOP)
        self.scene = Scene(self.plotter)
        # Physical scale stays default: SetPhysicalScale is server-only; the JS selectstart handler scales XR metres by 1000 to VTK mm.

    @staticmethod
    def _favicon_data_uri() -> str:
        """Return the favicon as a base64 data URI for the browser tab."""
        data = (
            importlib.resources.files("visfem.assets")
            .joinpath("favicon.png")
            .read_bytes()
        )
        return f"data:image/png;base64,{base64.b64encode(data).decode()}"

    def _setup_state(self) -> None:
        """Initialize all Trame state variables."""
        self.state.update(
            {
                "trame__title": "VisFEM",
                "trame__favicon": self._favicon_data_uri(),
                "dark_mode": True,
                "url_model": "",
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
                # Session-scoped overrides, "<dataset>:<patient>" -> {category: hex}, kept across palette and dataset switches.
                "category_colors": {},
                # Overrides for the categories on screen now; the map the UI reads.
                "category_colors_active": {},
                "ctrl_opacity": 0.9,
                "active_meta": None,
                "mesh_stats": None,
                "show_fibers": False,
                "has_fibers": False,
                "scalar_bar": None,
                "available_scalar_fields": [],
                "active_scalar_field": None,
                "n_steps": 1,
                "active_step": 0,
                "step_inc": 1,
                "step_times": [],
                "autoplay": False,
                "playback_speed": 1.0,  # multiplier on the base frame rate; cycled in the UI
                "active_categorical_palette": "paired",
                "active_continuous_cmap": "viridis",
                "categorical_palette_meta": CATEGORICAL_META,
                "continuous_cmap_meta": CONTINUOUS_META,
                "fullscreen": False,
                "loading": False,
                "busy": False,
                # Set by _show_error; shown by the snackbar in layout.py.
                "error_message": "",
                "error_open": False,
                # Set by the client probe in layout.py when WebGL2 is blocked (Brave shields, Firefox RFP, Safari ATP); the viewport stays blank.
                "webgl_blocked": False,
                "camera_resetting": False,
                "color_reversed": False,
                "exit_btn_pos": [0.0, 0.0, 0.0],
                "xr_exit_triggered": False,
                "clim_input_min": "",
                "clim_input_max": "",
                "clim_override": None,
                "opacity_adjusting": False,
            }
        )

    @change("url_model")
    def _on_url_model_change(self, url_model: str = "", **_: object) -> None:
        """Select the ?model= URL dataset *url_model* once, then clear url_model."""
        key: str = (url_model or "").strip()
        # The reset below re-enters this handler with an empty key.
        if not key:
            return
        # One-shot: trame replays the address-bar param on every client reconnect.
        self.state.url_model = ""
        if key in self._project_metadata:
            self._url_select_task = asyncio.ensure_future(self.select_dataset(key))

    def toggle_left_panel(self) -> None:
        """Toggle the left dataset panel open/closed."""
        self.state.left_panel_open = not self.state.left_panel_open

    def toggle_right_panel(self) -> None:
        """Toggle the right view-controls panel open/closed."""
        self.state.right_panel_open = not self.state.right_panel_open

    def toggle_theme(self) -> None:
        """Toggle between dark and light mode."""
        self.state.dark_mode = not self.state.dark_mode
        if self.state.dark_mode:
            self.plotter.renderers.set_background(BG_DARK_BOTTOM, top=BG_DARK_TOP)
        else:
            self.plotter.renderers.set_background(BG_LIGHT_BOTTOM, top=BG_LIGHT_TOP)
        push_scene(self.scene, self.ctrl, reset_camera=False)

    async def reset_camera(self) -> None:
        """Restore the camera to the initial pose captured at dataset load."""
        if self._initial_camera is None:
            return
        with self._claim_busy("reset the camera") as claimed:
            if not claimed:
                return
            self.state.camera_resetting = True
            try:
                self.state.flush()
                await asyncio.sleep(0.05)
                self.plotter.camera_position = self._initial_camera
                self.ctrl.view_push_camera()
                push_scene(self.scene, self.ctrl, reset_camera=False)
                # Fixed hold: the server learns the end of the client's re-render only through this timer.
                await asyncio.sleep(0.4)
            finally:
                self.state.camera_resetting = False

    def take_screenshot(self) -> None:
        """Trigger vtk.js canvas capture and browser PNG download."""
        self.ctrl.capture_screenshot()

    @change("xr_exit_triggered")
    def _on_xr_exit_triggered(self, xr_exit_triggered: bool, **_: object) -> None:
        """Forward the *xr_exit_triggered* change to the XR manager."""
        self.xr.on_exit_triggered(xr_exit_triggered)

    @change("xr_session_ended")
    def _on_xr_session_ended(self, xr_session_ended: bool, **_: object) -> None:
        """Forward the *xr_session_ended* change to the XR manager."""
        self.xr.on_session_ended(xr_session_ended)

    @change("scalar_bar")
    def _on_scalar_bar_change(self, scalar_bar: dict | None, **_: object) -> None:
        """Sync the clim text inputs to *scalar_bar* unless a manual override is set."""
        if scalar_bar:
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
        cmap = resolve_cmap(self.state)
        scalar_bar = update_scalar_range(self.scene, self.ctrl, field, [lo, hi], cmap)
        if scalar_bar:
            self.state.clim_override = [lo, hi]
            self.state.scalar_bar = scalar_bar

    def _cancel_warmup(self) -> None:
        """Cancel any running vtk.js warmup task and clear the loading and busy flags."""
        self._warmup_gen += 1
        if self._warmup_task is not None and not self._warmup_task.done():
            self._warmup_task.cancel()
        self._warmup_task = None
        self.state.loading = False
        self.state.busy = False

    def _render_settle(self) -> float:
        """Return the overlay hold in seconds for the active mesh, scaled by cell count."""
        stats = self.state.mesh_stats or {}
        cells = 0
        if isinstance(stats, dict):
            try:
                cells = int(stats.get("n_cells") or 0)
            except (TypeError, ValueError):
                cells = 0
        settle = _RENDER_SETTLE_MIN + _RENDER_SETTLE_PER_MCELL * (cells / 1_000_000)
        return min(settle, _RENDER_SETTLE_MAX)

    def _show_error(self, context: str, exc: Exception) -> None:
        """Log the traceback of *exc* and show "*context*: *exc*" to the user."""
        # logger.exception attaches the exception being handled.
        logger.exception(context)
        with self.state:
            self.state.error_message = f"{context}: {exc}"
            self.state.error_open = True

    @contextlib.contextmanager
    def _claim_busy(self, what: str) -> Generator[bool]:
        """Claim the busy flag and yield True, or yield False while held; an exception in the block is shown as "Failed to *what*" and swallowed."""
        # The claim precedes every await; a second fast click sees the flag.
        if self.state.busy:
            yield False
            return
        self.state.busy = True
        try:
            yield True
        except Exception as e:  # noqa: BLE001 - UI boundary: report and release the view
            self._show_error(f"Failed to {what}", e)
        finally:
            self.state.busy = False

    async def _busy_render(
        self,
        what: str,
        render: Callable[..., object],
        *args: object,
        prepare: Callable[[], None] | None = None,
        needs_dataset: bool = True,
    ) -> None:
        """Run *render* with the scene, ctrl, state, both metadata maps and *args* under the busy claim; *prepare* applies state first, *what* names the action in the error, *needs_dataset* requires an active dataset."""
        if needs_dataset and self.state.active_dataset is None:
            return
        with self._claim_busy(what) as claimed:
            if not claimed:
                return
            if prepare is not None:
                prepare()
            # Push the busy flag and the prepared state before the render blocks the loop.
            self.state.flush()
            await asyncio.sleep(0.05)
            render(
                self.scene,
                self.ctrl,
                self.state,
                self._project_metadata,
                self._xdmf_meta,
                *args,
            )

    async def _switch(self, what: str, render: Callable[[], vtkActor | None]) -> None:
        """Overlay on, run *render* (the synchronous selection, returns the fibre actor or None), warm up; *what* names the target in the error message."""
        self.state.autoplay = False
        self._cancel_warmup()
        self.state.loading = True
        self.state.busy = True
        self.state.flush()
        await asyncio.sleep(0.05)
        try:
            self._fiber_actor = render()
            apply_opacity(self.scene, float(self.state.ctrl_opacity))
            self._initial_camera = self.plotter.camera_position
            await self._start_vtkjs_warmup()
        except Exception as e:  # noqa: BLE001 - UI boundary: report and release the view
            self._show_error(f"Failed to load {what}", e)
            clear_overlay(self.state)

    def _resolve_active_path(self) -> Path | None:
        """Return the load_mesh path of the active dataset (d3plot directory, series step file, PVD or XDMF), or None."""
        key: str | None = self.state.active_dataset
        if not key or key not in self._project_metadata:
            return None
        meta = self._project_metadata[key]
        # LS-DYNA d3plot: the database directory is the load_mesh path; warmup passes the step.
        if meta.render is not None and meta.render.database:
            return dataset_dir(meta)
        # Flat VTK series: the active path is the per-step file at active_step.
        if meta.render is not None and meta.render.series:
            steps = vtk_series_steps(dataset_dir(meta), meta.render.series)
            if steps:
                idx = max(0, min(int(self.state.active_step), len(steps) - 1))
                return steps[idx][1]
        # GRASP phase series: the patient's PVD; warmup passes the phase as the step.
        patient = self.state.active_patient
        if patient is not None:
            pvd = grasp_phase_pvd(patient_subdir(dataset_dir(meta), patient))
            if pvd is not None:
                return pvd
        return active_timeseries_path(meta, self.state, dataset_dir(meta))

    async def _start_vtkjs_warmup(self) -> None:
        """Hold the overlay while the client paints, then warm the step cache for a series."""
        n_steps = int(self.state.n_steps)
        if n_steps <= 1:
            self.state.step_inc = 1
            # The client paints push_scene's single push (disable_auto_switch); the sleep covers it.
            await asyncio.sleep(self._render_settle())
            clear_overlay(self.state)
            return
        self.state.step_inc = keyframe_increment(n_steps)
        path = self._resolve_active_path()
        if path is None:
            clear_overlay(self.state)
            return
        gen = self._warmup_gen
        self._warmup_task = asyncio.ensure_future(
            vtkjs_warmup(gen, lambda: self._warmup_gen, self.state, path)
        )

    @change("ctrl_opacity")
    def _on_opacity_change(self, ctrl_opacity: float, **_: object) -> None:
        """Flag the slider as adjusting and debounce the render of *ctrl_opacity*."""
        if self.state.active_dataset is None:
            return
        if self._opacity_task is not None and not self._opacity_task.done():
            self._opacity_task.cancel()
        self.state.opacity_adjusting = True
        self._opacity_task = asyncio.ensure_future(
            self._apply_opacity_debounced(float(ctrl_opacity))
        )

    async def _apply_opacity_debounced(self, opacity: float) -> None:
        """Apply *opacity* after the debounce delay, then clear the adjusting flag."""
        try:
            await asyncio.sleep(0.15)
        except asyncio.CancelledError:
            return
        try:
            apply_opacity(self.scene, opacity)
            push_scene(self.scene, self.ctrl, reset_camera=False)
        finally:
            self.state.opacity_adjusting = False
            self.state.flush()

    @change("active_organ_group_open")
    def _on_organ_group_change(
        self, active_organ_group_open: list, **_: object
    ) -> None:
        """Keep only the last opened organ system group of *active_organ_group_open* open."""
        top_level = set(self._organ_groups.keys())
        open_top = [v for v in active_organ_group_open if v in top_level]
        if len(open_top) > 1:
            keep = open_top[-1]
            self.state.active_organ_group_open = [
                v for v in active_organ_group_open if v not in top_level or v == keep
            ]

    @change("show_fibers")
    def _on_show_fibers_change(self, show_fibers: bool, **_: object) -> None:
        """Set the fibre glyph actor visibility to *show_fibers*."""
        if self._fiber_actor is None:
            return
        self._fiber_actor.SetVisibility(bool(show_fibers))
        push_scene(self.scene, self.ctrl, reset_camera=False)

    async def select_dataset(self, key: str) -> None:
        """Switch to dataset *key*."""
        await self._switch(
            f"dataset '{key}'",
            lambda: select_dataset(
                self.scene,
                self.ctrl,
                self.state,
                self._project_metadata,
                self._xdmf_meta,
                key,
            ),
        )

    async def select_xdmf(self, key: str, stem: str) -> None:
        """Switch to XDMF file *stem* of dataset *key*."""

        def render() -> None:
            """Render XDMF file *stem* of dataset *key*."""
            select_xdmf(
                self.scene,
                self.ctrl,
                self.state,
                self._project_metadata,
                self._xdmf_meta,
                key,
                stem,
            )

        await self._switch(f"'{stem}' of dataset '{key}'", render)

    async def select_patient(self, dataset_key: str, patient: int) -> None:
        """Switch to patient *patient* of dataset *dataset_key*."""

        def render() -> None:
            """Render patient *patient* of dataset *dataset_key*."""
            select_patient(
                self.scene,
                self.ctrl,
                self.state,
                self._project_metadata,
                dataset_key,
                patient,
            )

        await self._switch(f"patient {patient} of dataset '{dataset_key}'", render)

    async def select_scalar_field(self, field: str) -> None:
        """Re-render the active dataset with scalar field *field*."""

        def prepare() -> None:
            """Stop playback and warmup, rewind to step 0 and drop the range override."""
            self.state.autoplay = False
            self._cancel_warmup()
            self.state.active_step = 0
            self.state.clim_override = None

        await self._busy_render(
            "switch the field",
            select_scalar_field,
            field,
            prepare=prepare,
            needs_dataset=False,
        )

    async def select_step(self, step: int) -> None:
        """Show time step *step* of the active dataset."""

        def render(
            scene: Scene,
            ctrl: TrameCtrl,
            state: Any,
            project_metadata: dict[str, ProjectMetadata],
            xdmf_meta: dict[str, MeshMetadata],
        ) -> None:
            """Call select_step with the coerced *step* on *scene*, *ctrl*, *state*, *project_metadata* and *xdmf_meta*."""
            select_step(scene, ctrl, state, project_metadata, xdmf_meta, int(step))

        await self._busy_render("change the time step", render, needs_dataset=False)

    async def toggle_color_reversed(self) -> None:
        """Flip the color order of the active palette or colormap and re-render."""

        def prepare() -> None:
            """Flip the colour order and drop the range override."""
            self.state.color_reversed = not self.state.color_reversed
            self.state.clim_override = None

        await self._busy_render(
            "reverse the colours", select_color_scheme, prepare=prepare
        )

    async def select_color_scheme(self, name: str) -> None:
        """Set *name* as the active palette or colormap and re-render the scene."""

        def prepare() -> None:
            """Store *name* as the colormap of a scalar scene or the palette of a categorical one and drop the range override."""
            if self.state.scalar_bar is not None:
                self.state.active_continuous_cmap = name
            else:
                self.state.active_categorical_palette = name
            self.state.clim_override = None

        await self._busy_render(
            "change the colour scheme", select_color_scheme, prepare=prepare
        )

    async def set_category_color(self, name: str, color: str) -> None:
        """Override category *name* with *color* and recolour the scene in place."""
        if not name:
            return
        await self._busy_render(
            "change the category colour",
            recolor_categories,
            prepare=lambda: set_override(self.state, name, color),
        )

    async def reset_category_colors(self, name: str | None = None) -> None:
        """Clear the override of category *name*, or every override in scope when None, and recolour."""

        def prepare() -> None:
            """Clear the override of *name*, or every override in scope when None."""
            if name:
                set_override(self.state, name, None)
            else:
                clear_overrides(self.state)

        await self._busy_render(
            "reset the category colours", recolor_categories, prepare=prepare
        )

    def toggle_autoplay(self) -> None:
        """Start or stop automatic step playback."""
        self._cancel_warmup()
        if self.state.autoplay:
            self.state.autoplay = False
        else:
            # A previous autoplay task still winding down blocks the restart.
            if self._autoplay_task is not None and not self._autoplay_task.done():
                return
            self.state.autoplay = True
            # GRASP phase series (patient-indexed) plays slower than scalar timeseries.
            frame_sleep = (
                _PHASE_FRAME_SLEEP
                if self.state.active_patient is not None
                else _FRAME_SLEEP
            )
            self._autoplay_task = asyncio.ensure_future(
                autoplay_loop(
                    self.state,
                    self.scene,
                    self.ctrl,
                    self._project_metadata,
                    self._xdmf_meta,
                    frame_sleep,
                )
            )


def main() -> None:
    """Build the app, preload every mesh when VISFEM_PRELOAD=1, and start the server."""
    import os

    app = VisfemApp()
    # Unset in the per-session deployment: each session lazy-loads its one model and the idle container stays light.
    if os.environ.get("VISFEM_PRELOAD", "0") == "1":
        preload_all_meshes(app._project_metadata)
    app.server.start()


if __name__ == "__main__":
    main()
