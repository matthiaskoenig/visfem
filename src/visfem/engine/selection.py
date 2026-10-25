"""Dataset selection handlers that dispatch through the renderer registry."""

import contextlib
from collections.abc import Generator
from pathlib import Path
from typing import Any

from vtkmodules.vtkRenderingCore import vtkActor

from visfem.engine.colors import apply_overrides_to_state, region_colors
from visfem.engine.discovery import (
    active_timeseries_path,
    dataset_dir,
    discover_xdmf,
    grasp_phase_count,
    grasp_phase_pvd,
    meta_to_state,
    patient_subdir,
)
from visfem.engine.palettes import CATEGORICAL_PALETTES
from visfem.engine.renderers import (
    TIMESERIES_RENDERERS,
    RenderContext,
    apply_result_to_state,
    dispatch_render,
    is_patient_renderer,
    populate_timeseries_state,
    resolve_render_config,
)
from visfem.engine.scene import (
    RenderResult,
    Scene,
    TrameCtrl,
    clear_scene,
    field_label,
    push_scene,
    update_actor_palette,
    update_scalar_field_view,
    update_xdmf_step,
)
from visfem.log import get_logger
from visfem.models import MeshMetadata, ProjectMetadata, RenderConfig, RendererName

logger = get_logger(__name__)

# Renderers whose active actor carries a categorical LUT for in-place palette swaps;
# scalar_field recolors through update_scalar_field_view.
_RECOLORABLE: frozenset[RendererName] = frozenset(
    {
        RendererName.REGION_ID,
        RendererName.MULTI_PART,
        RendererName.PATIENT_ORGANS,
    }
)


def _resolve_palette(state: Any) -> list[str]:
    """Return the active categorical palette colors from state."""
    name: str = str(state.active_categorical_palette)
    colors = CATEGORICAL_PALETTES.get(name, CATEGORICAL_PALETTES["paired"])
    return list(reversed(colors)) if getattr(state, "color_reversed", False) else colors


def resolve_cmap(state: Any) -> str:
    """Return the active continuous colormap name from state."""
    cmap = str(state.active_continuous_cmap)
    return cmap + "_r" if getattr(state, "color_reversed", False) else cmap


@contextlib.contextmanager
def _trame_busy(state: Any) -> Generator[None]:
    """Set ``trame__busy`` on *state* for the block and clear it on exit."""
    state.trame__busy = True
    try:
        yield
    finally:
        state.trame__busy = False


def _reset_selection_state(state: Any) -> None:
    """Reset per-dataset selection state before loading a new dataset."""
    state.available_scalar_fields = []
    state.active_scalar_field = None
    state.active_xdmf = None
    state.n_steps = 1
    state.active_step = 0
    state.step_times = []
    state.clim_override = None
    state.has_fibers = False


def _build_context(
    scene: Scene,
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
    """Return a RenderContext with palette and cmap resolved from *state*."""
    return RenderContext(
        scene=scene,
        ctrl=ctrl,
        state=state,
        ddir=ddir,
        meta=meta,
        cfg=cfg,
        xdmf_meta=xdmf_meta,
        opacity=float(state.ctrl_opacity),
        palette=_resolve_palette(state),
        cmap=resolve_cmap(state),
        field=field,
        step=step,
        reset_camera=reset_camera,
    )


def _scalar_field_view_args(
    meta: ProjectMetadata, cfg: RenderConfig, state: Any
) -> dict:
    """Return the update_scalar_field_view kwargs for *cfg* and *state*."""
    return {
        "mesh_file": cfg.mesh_file,
        "categorical_fields": frozenset(cfg.categorical_fields),
        "zone_labels": cfg.region_labels,
        "palette": _resolve_palette(state),
        "cmap": resolve_cmap(state),
        "percentile": cfg.percentile_clamp,
    }


def _apply_scalar_field_legend(
    scene: Scene,
    ctrl: TrameCtrl,
    state: Any,
    legend: list[dict[str, Any]],
    scalar_bar: dict[str, Any] | None,
) -> None:
    """Store legend and scalar bar on state; re-push the LUT when overrides differ."""
    colors = apply_overrides_to_state(state, legend)
    state.scalar_bar = scalar_bar
    original = [item.get("color") for item in legend]
    # update_scalar_field_view builds its LUT from the plain palette.
    if colors != original:
        update_actor_palette(scene, ctrl, colors, len(colors))


def _try_scalar_field_fast_path(
    scene: Scene,
    ctrl: TrameCtrl,
    state: Any,
    meta: ProjectMetadata,
    cfg: RenderConfig,
) -> bool:
    """Swap field and LUT in place on a scalar_field actor; True when one exists."""
    if cfg.renderer != RendererName.SCALAR_FIELD or scene.active_actor is None:
        return False
    legend, scalar_bar = update_scalar_field_view(
        scene,
        ctrl,
        dataset_dir(meta),
        field=state.active_scalar_field,
        **_scalar_field_view_args(meta, cfg, state),
    )
    _apply_scalar_field_legend(scene, ctrl, state, legend, scalar_bar)
    return True


def _redraw(
    scene: Scene,
    ctrl: TrameCtrl,
    state: Any,
    meta: ProjectMetadata,
    cfg: RenderConfig,
    ddir: Path,
    xdmf_meta: dict[str, MeshMetadata],
    *,
    field: str | None = None,
    step: int = 0,
) -> RenderResult:
    """Return a RenderResult from the registry at *field* and *step*, camera kept."""
    ctx = _build_context(
        scene,
        ctrl,
        state,
        meta,
        cfg,
        ddir,
        xdmf_meta,
        field=field,
        step=step,
        reset_camera=False,
    )
    return dispatch_render(ctx)


def select_dataset(
    scene: Scene,
    ctrl: TrameCtrl,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    key: str,
) -> vtkActor | None:
    """Render dataset *key* via its render config; return the fibre actor or None."""
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

    fiber_actor: vtkActor | None = None
    with _trame_busy(state):
        # Patient renderers clear the scene; select_patient renders.
        if is_patient_renderer(cfg):
            clear_scene(scene, state.dark_mode)
            push_scene(scene, ctrl)
            state.legend_items = []
            state.mesh_stats = None
            state.scalar_bar = None
            state.active_meta = meta_to_state(meta)
            return None

        ctx = _build_context(scene, ctrl, state, meta, cfg, ddir, xdmf_meta)

        # Timeseries datasets populate the field/step UI and pick the default field.
        if cfg.renderer in TIMESERIES_RENDERERS:
            ctx.field = populate_timeseries_state(state, ctx)
        # A static mesh takes its field list from the render config.
        elif cfg.renderer == RendererName.SCALAR_FIELD:
            state.available_scalar_fields = [
                {"name": f.name, "label": f.label or field_label(f.name)}
                for f in cfg.fields
            ]
            state.active_scalar_field = cfg.default_field or (
                cfg.fields[0].name if cfg.fields else None
            )
            ctx.field = state.active_scalar_field

        result = dispatch_render(ctx)
        apply_result_to_state(state, result)
        fiber_actor = result.fiber_actor
        state.has_fibers = fiber_actor is not None
        state.active_meta = meta_to_state(meta)
    return fiber_actor


def select_xdmf(
    scene: Scene,
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
    with _trame_busy(state):
        meta = project_metadata[key]
        cfg = resolve_render_config(meta, dataset_dir(meta))
        if discover_xdmf(dataset_dir(meta)).get(stem) is None:
            logger.error("XDMF file not found: %s in %s", stem, key)
            return
        # renderers._timeseries_path reads state.active_xdmf to pick this stem.
        ctx = _build_context(
            scene, ctrl, state, meta, cfg, dataset_dir(meta), xdmf_meta
        )
        ctx.field = populate_timeseries_state(state, ctx)
        result = dispatch_render(ctx)
        apply_result_to_state(state, result)
        state.active_meta = meta_to_state(meta)


def select_scalar_field(
    scene: Scene,
    ctrl: TrameCtrl,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    field: str,
) -> None:
    """Re-render the current dataset with a different scalar field."""
    state.active_scalar_field = field
    with _trame_busy(state):
        meta = project_metadata[state.active_dataset]
        cfg = resolve_render_config(meta, dataset_dir(meta))
        if _try_scalar_field_fast_path(scene, ctrl, state, meta, cfg):
            return
        # A static mesh redraws at step 0; a time series at the current step.
        step = (
            0 if cfg.renderer == RendererName.SCALAR_FIELD else int(state.active_step)
        )
        result = _redraw(
            scene,
            ctrl,
            state,
            meta,
            cfg,
            dataset_dir(meta),
            xdmf_meta,
            field=field,
            step=step,
        )
        apply_result_to_state(state, result)


def select_step(
    scene: Scene,
    ctrl: TrameCtrl,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    step: int,
) -> None:
    """Navigate the current time-series dataset to a different timestep."""
    state.active_step = step
    with _trame_busy(state):
        meta = project_metadata[state.active_dataset]
        ddir = dataset_dir(meta)
        cfg = resolve_render_config(meta, ddir)

        # GRASP phase steps have independent topology; redraw from the patient dir.
        if cfg.renderer == RendererName.PVD_PHASE_SERIES:
            if state.active_patient is None:
                return
            patient_dir = patient_subdir(ddir, state.active_patient)
            result = _redraw(
                scene, ctrl, state, meta, cfg, patient_dir, xdmf_meta, step=step
            )
            apply_result_to_state(state, result)
            return

        field: str | None = state.active_scalar_field

        # VTK series and d3plot steps are distinct meshes; render via the registry.
        if cfg.series or cfg.database:
            result = _redraw(
                scene, ctrl, state, meta, cfg, ddir, xdmf_meta, field=field, step=step
            )
            state.mesh_stats = result.mesh_stats
            if result.scalar_bar_info is not None:
                state.scalar_bar = result.scalar_bar_info
            return

        # XDMF / PVD scalar series swap the step in place; a failed swap redraws.
        path = active_timeseries_path(meta, state, ddir)
        if path is None:
            logger.error(
                "No timeseries file found for dataset '%s'", state.active_dataset
            )
            return
        cmap = resolve_cmap(state)
        success, stats, scalar_bar = update_xdmf_step(
            scene,
            ctrl,
            path,
            xdmf_meta,
            step=step,
            field=field,
            cmap=cmap,
        )
        if not success:
            result = _redraw(
                scene, ctrl, state, meta, cfg, ddir, xdmf_meta, field=field, step=step
            )
            stats = result.mesh_stats
            scalar_bar = result.scalar_bar_info
        state.mesh_stats = stats
        if scalar_bar is not None:
            state.scalar_bar = scalar_bar


def select_patient(
    scene: Scene,
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
    with _trame_busy(state):
        meta = project_metadata[dataset_key]
        patient_dir = patient_subdir(dataset_dir(meta), patient)
        cfg = resolve_render_config(meta, dataset_dir(meta))

        # Patient renderers render from the patient dir via the registry.
        ctx = _build_context(
            scene, ctrl, state, meta, cfg, patient_dir, {}, step=0, reset_camera=True
        )
        if cfg.renderer == RendererName.PVD_PHASE_SERIES:
            pvd = grasp_phase_pvd(patient_dir)
            if pvd is not None:
                state.n_steps = grasp_phase_count(pvd)
                state.active_step = 0
                state.step_times = []  # the UI shows phases as "k / n"
        result = dispatch_render(ctx)
        apply_overrides_to_state(state, result.legend_items)
        state.mesh_stats = result.mesh_stats
        state.active_meta = meta_to_state(meta)


def _recolor_active_actor(scene: Scene, ctrl: TrameCtrl, state: Any) -> bool:
    """Recolor the active actor's LUT and legend in place; True when one exists."""
    if scene.active_actor is None:
        return False
    n = len(state.legend_items)
    palette_colors = region_colors(n, _resolve_palette(state))
    # Overrides win over the palette colours.
    base = [
        {**item, "color": palette_colors[i]}
        for i, item in enumerate(state.legend_items)
    ]
    colors = apply_overrides_to_state(state, base)
    update_actor_palette(scene, ctrl, colors, n)
    return True


def recolor_categories(
    scene: Scene,
    ctrl: TrameCtrl,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
) -> None:
    """Re-apply category colour overrides in place, or via select_color_scheme."""
    if state.active_dataset is None:
        return
    if state.legend_items and _recolor_active_actor(scene, ctrl, state):
        return
    select_color_scheme(scene, ctrl, state, project_metadata, xdmf_meta)


def select_color_scheme(
    scene: Scene,
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
    # Patient renderers re-render from the patient dir.
    ddir = dataset_dir(meta)
    if state.active_patient is not None:
        ddir = patient_subdir(ddir, state.active_patient)

    with _trame_busy(state):
        if _try_scalar_field_fast_path(scene, ctrl, state, meta, cfg):
            return

        # Categorical renderers swap the LUT on the active actor in place.
        if cfg.renderer in _RECOLORABLE and _recolor_active_actor(scene, ctrl, state):
            return

        # Full re-render at the current field/step, keeping the camera.
        result = _redraw(
            scene,
            ctrl,
            state,
            meta,
            cfg,
            ddir,
            xdmf_meta,
            field=state.active_scalar_field,
            step=int(state.active_step),
        )
        apply_result_to_state(state, result)
