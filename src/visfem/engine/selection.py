"""Dataset selection handlers for VisFEM.

Every handler resolves the active dataset's render config
(``visfem.engine.renderers.resolve_render_config``) and dispatches through the
renderer registry — there is no per-dataset-name branching. In-place fast-paths
(``update_xdmf_step``, ``update_scalar_field_view``, ``update_actor_palette``) are
kept for latency on step/field/palette changes, falling back to a registry
re-render.
"""
from pathlib import Path

import pyvista as pv
from typing import Any
from vtkmodules.vtkRenderingCore import vtkActor

from visfem.engine.colors import region_colors
from visfem.engine.palettes import CATEGORICAL_PALETTES
from visfem.engine.scene import (
    TrameCtrl, clear_scene, field_label,
    get_active_actor, update_actor_palette, update_scalar_field_view, update_xdmf_step,
)
from visfem.log import get_logger
from visfem.models import MeshMetadata, ProjectMetadata, RenderConfig, RendererName
from visfem.engine.discovery import (
    dataset_dir, discover_xdmf, meta_to_state, pvd_file_path,
    grasp_phase_pvd, grasp_phase_count,
)
from visfem.engine.renderers import (
    TIMESERIES_RENDERERS, RenderContext,
    apply_result_to_state, dispatch_render, is_patient_renderer,
    populate_timeseries_state, resolve_render_config,
)

logger = get_logger(__name__)

# Renderers whose active actor carries a categorical LUT, so a palette change can
# be applied as a fast in-place recolor instead of a full re-render. (scalar_field
# is excluded: it has its own dedicated fast-path, update_scalar_field_view.)
_RECOLORABLE: frozenset[RendererName] = frozenset({
    RendererName.REGION_ID,
    RendererName.MULTI_PART,
    RendererName.PATIENT_ORGANS,
})


def _resolve_palette(state: Any) -> list[str]:
    """Return the active categorical palette colors from state."""
    name: str = str(state.active_categorical_palette)
    colors = CATEGORICAL_PALETTES.get(name, CATEGORICAL_PALETTES["paired"])
    return list(reversed(colors)) if getattr(state, "color_reversed", False) else colors


def _timeseries_path(
    meta: ProjectMetadata,
    state: Any,
    xdmf_files: dict[str, Path],
) -> Path | None:
    """Return the active timeseries file path for PVD or XDMF datasets."""
    if meta.mesh_format == "PVD":
        return pvd_file_path(meta)
    stem: str | None = state.active_xdmf
    return xdmf_files.get(stem) if stem else next(iter(xdmf_files.values()), None)


def _resolve_cmap(state: Any) -> str:
    """Return the active continuous colormap name from state."""
    cmap = str(state.active_continuous_cmap)
    return cmap + "_r" if getattr(state, "color_reversed", False) else cmap


def _reset_selection_state(state: Any) -> None:
    """Reset per-dataset selection state before loading a new dataset."""
    state.available_scalar_fields = []
    state.active_scalar_field = None
    state.active_xdmf = None
    state.n_steps = 1
    state.active_step = 0
    state.step_times = []
    state.clim_override = None
    state.has_fibers = False  # set True after render when a fibre actor is produced


def _build_context(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    state: Any,
    meta: ProjectMetadata,
    cfg: RenderConfig,
    ddir: Path,
    xdmf_meta: dict[str, MeshMetadata],
    *,
    field: str | None = None,
    step: int = 0,
    reset_camera: bool = True,
) -> RenderContext:
    """Assemble a RenderContext with palette/cmap resolved from current state."""
    return RenderContext(
        plotter=plotter, ctrl=ctrl, state=state, ddir=ddir, meta=meta, cfg=cfg,
        xdmf_meta=xdmf_meta, opacity=float(state.ctrl_opacity),
        palette=_resolve_palette(state), cmap=_resolve_cmap(state),
        field=field, step=step, reset_camera=reset_camera,
    )


def _scalar_field_view_args(meta: ProjectMetadata, cfg: RenderConfig, state: Any) -> dict:
    """Shared kwargs for the scalar_field in-place fast-path (update_scalar_field_view)."""
    return dict(
        mesh_file=cfg.mesh_file,
        categorical_fields=frozenset(cfg.categorical_fields),
        zone_labels=cfg.region_labels,
        palette=_resolve_palette(state),
        cmap=_resolve_cmap(state),
        percentile=cfg.percentile_clamp if cfg.percentile_clamp is not None else 95,
    )


def select_dataset(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    key: str,
) -> vtkActor | None:
    """Render a dataset via its resolved render config (JSON-driven dispatch)."""
    state.active_dataset = key
    state.active_patient = None
    state.show_fibers = False
    _reset_selection_state(state)

    meta = project_metadata[key]
    ddir = dataset_dir(meta)
    cfg = resolve_render_config(meta, ddir)

    # Colour-scheme defaults come from the dataset's render config.
    state.active_categorical_palette = cfg.categorical_palette
    state.active_continuous_cmap = cfg.continuous_cmap

    state.trame__busy = True
    fiber_actor: vtkActor | None = None
    try:
        # Patient-driven datasets clear the scene now; rendering happens on patient select.
        if is_patient_renderer(cfg):
            clear_scene(plotter, state.dark_mode)
            state.legend_items = []
            state.mesh_stats = None
            state.scalar_bar = None
            state.active_meta = meta_to_state(meta)
            return None

        ctx = _build_context(plotter, ctrl, state, meta, cfg, ddir, xdmf_meta)

        # Timeseries datasets populate the field/step UI and render the default field.
        if cfg.renderer in TIMESERIES_RENDERERS:
            ctx.field = populate_timeseries_state(state, ctx)
        elif cfg.renderer == RendererName.SCALAR_FIELD:  # static mesh + explicit field list
            state.available_scalar_fields = [
                {"name": f.name, "label": f.label or field_label(f.name)} for f in cfg.fields
            ]
            state.active_scalar_field = cfg.default_field or (cfg.fields[0].name if cfg.fields else None)
            ctx.field = state.active_scalar_field

        result = dispatch_render(ctx)
        apply_result_to_state(state, result)
        fiber_actor = result.fiber_actor
        state.has_fibers = fiber_actor is not None
        state.active_meta = meta_to_state(meta)
    finally:
        state.trame__busy = False
    return fiber_actor


def select_xdmf(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    key: str,
    stem: str,
) -> None:
    """Load and render a specific XDMF file within a multi-file dataset."""
    state.active_dataset = key
    state.active_patient = None
    _reset_selection_state(state)
    state.active_xdmf = stem
    state.trame__busy = True
    try:
        meta = project_metadata[key]
        cfg = resolve_render_config(meta, dataset_dir(meta))
        if discover_xdmf(dataset_dir(meta)).get(stem) is None:
            logger.error(f"XDMF file not found: {stem} in {key}")
            return
        # _timeseries_path reads state.active_xdmf to pick this stem.
        ctx = _build_context(plotter, ctrl, state, meta, cfg, dataset_dir(meta), xdmf_meta)
        ctx.field = populate_timeseries_state(state, ctx)
        result = dispatch_render(ctx)
        apply_result_to_state(state, result)
        state.active_meta = meta_to_state(meta)
    finally:
        state.trame__busy = False


def select_scalar_field(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    field: str,
) -> None:
    """Re-render the current dataset with a different scalar field."""
    state.active_scalar_field = field
    state.trame__busy = True
    try:
        meta = project_metadata[state.active_dataset]
        cfg = resolve_render_config(meta, dataset_dir(meta))

        if cfg.renderer == RendererName.SCALAR_FIELD:
            # Fast-path: swap the active scalar array in place when an actor exists.
            if get_active_actor() is not None:
                legend, scalar_bar = update_scalar_field_view(
                    plotter, ctrl, dataset_dir(meta), field=field,
                    **_scalar_field_view_args(meta, cfg, state),
                )
                state.legend_items = legend
                state.scalar_bar = scalar_bar
                return
            ctx = _build_context(plotter, ctrl, state, meta, cfg, dataset_dir(meta),
                                 xdmf_meta, field=field, reset_camera=False)
            result = dispatch_render(ctx)
            apply_result_to_state(state, result)
        else:
            # XDMF / PVD time series: full redraw at the current step with the new field.
            ctx = _build_context(plotter, ctrl, state, meta, cfg, dataset_dir(meta),
                                 xdmf_meta, field=field, step=int(state.active_step),
                                 reset_camera=False)
            result = dispatch_render(ctx)
            apply_result_to_state(state, result)
    finally:
        state.trame__busy = False


def select_step(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    step: int,
) -> None:
    """Navigate the current time-series dataset to a different timestep."""
    state.active_step = step
    state.trame__busy = True
    try:
        meta = project_metadata[state.active_dataset]
        ddir = dataset_dir(meta)
        cfg = resolve_render_config(meta, ddir)

        # GRASP phase series: each patient's phases are region-coloured PVD steps with
        # independent topology — full redraw via the patient dir, no scalar field.
        if cfg.renderer == RendererName.PVD_PHASE_SERIES:
            if state.active_patient is None:
                return
            patient_dir = ddir / f"patient_{int(state.active_patient):02d}"
            ctx = _build_context(plotter, ctrl, state, meta, cfg, patient_dir,
                                 xdmf_meta, step=step, reset_camera=False)
            result = dispatch_render(ctx)
            apply_result_to_state(state, result)
            return

        field: str | None = state.active_scalar_field

        # Flat VTK series or LS-DYNA d3plot: each step is a distinct whole mesh —
        # render it via the registry (no manifest path / in-place fast-path).
        if cfg.series or cfg.database:
            ctx = _build_context(plotter, ctrl, state, meta, cfg, ddir,
                                 xdmf_meta, field=field, step=step, reset_camera=False)
            result = dispatch_render(ctx)
            state.mesh_stats = result.mesh_stats
            if result.scalar_bar_info is not None:
                state.scalar_bar = result.scalar_bar_info
            return

        # XDMF / PVD scalar series: try the in-place step fast-path, else full redraw.
        path = _timeseries_path(meta, state, discover_xdmf(ddir))
        if path is None:
            logger.error(f"No timeseries file found for dataset '{state.active_dataset}'")
            return
        cmap = _resolve_cmap(state)
        success, stats, scalar_bar = update_xdmf_step(
            plotter, ctrl, path, xdmf_meta, step=step, field=field, cmap=cmap,
        )
        if not success:
            ctx = _build_context(plotter, ctrl, state, meta, cfg, ddir,
                                 xdmf_meta, field=field, step=step, reset_camera=False)
            result = dispatch_render(ctx)
            stats = result.mesh_stats
            scalar_bar = result.scalar_bar_info
        state.mesh_stats = stats
        if scalar_bar is not None:
            state.scalar_bar = scalar_bar
    finally:
        state.trame__busy = False


def select_patient(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    dataset_key: str,
    patient: int,
) -> None:
    """Load and render a specific patient from a multi-patient dataset."""
    state.active_dataset = dataset_key
    state.active_patient = patient
    state.scalar_bar = None
    _reset_selection_state(state)
    state.trame__busy = True
    try:
        meta = project_metadata[dataset_key]
        patient_dir = dataset_dir(meta) / f"patient_{patient:02d}"
        cfg = resolve_render_config(meta, dataset_dir(meta))

        # All patient renderers (organs, phase series, single surface) render from
        # the patient dir via the registry. ddir is overridden to the patient dir.
        ctx = _build_context(plotter, ctrl, state, meta, cfg, patient_dir,
                             {}, step=0, reset_camera=True)
        if cfg.renderer == RendererName.PVD_PHASE_SERIES:
            pvd = grasp_phase_pvd(patient_dir)
            if pvd is not None:
                state.n_steps = grasp_phase_count(pvd)
                state.active_step = 0
                state.step_times = []  # phase indices; UI shows "k / n"
        result = dispatch_render(ctx)
        state.legend_items = result.legend_items
        state.mesh_stats = result.mesh_stats
        state.active_meta = meta_to_state(meta)
    finally:
        state.trame__busy = False


def _recolor_active_actor(plotter: pv.Plotter, ctrl: TrameCtrl, state: Any) -> bool:
    """Fast-path recolor of the active actor's categorical LUT + legend; False if no actor (caller does a full redraw)."""
    if get_active_actor() is None:
        return False
    n = len(state.legend_items)
    colors = region_colors(n, _resolve_palette(state))
    update_actor_palette(plotter, ctrl, colors, n)
    state.legend_items = [
        {**item, "color": colors[i]} for i, item in enumerate(state.legend_items)
    ]
    return True


def select_color_scheme(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
) -> None:
    """Re-render the current scene after a palette or colormap change."""
    key: str | None = state.active_dataset
    if key is None:
        return

    meta = project_metadata[key]
    cfg = resolve_render_config(meta, dataset_dir(meta))
    # Patient renderers re-render from the patient dir; everything else from the
    # dataset dir. Timeseries keep the active field/step.
    ddir = dataset_dir(meta)
    if state.active_patient is not None:
        ddir = ddir / f"patient_{int(state.active_patient):02d}"

    state.trame__busy = True
    try:
        # scalar_field: fast in-place LUT/field swap when an actor exists.
        if cfg.renderer == RendererName.SCALAR_FIELD and get_active_actor() is not None:
            legend, scalar_bar = update_scalar_field_view(
                plotter, ctrl, dataset_dir(meta), field=state.active_scalar_field,
                **_scalar_field_view_args(meta, cfg, state),
            )
            state.legend_items = legend
            state.scalar_bar = scalar_bar
            return

        # Categorical renderers: fast-path swap the LUT on the active actor.
        if cfg.renderer in _RECOLORABLE and _recolor_active_actor(plotter, ctrl, state):
            return

        # Otherwise full re-render at the current field/step, keeping the camera.
        ctx = _build_context(
            plotter, ctrl, state, meta, cfg, ddir, xdmf_meta,
            field=state.active_scalar_field, step=int(state.active_step),
            reset_camera=False,
        )
        result = dispatch_render(ctx)
        apply_result_to_state(state, result)
    finally:
        state.trame__busy = False
