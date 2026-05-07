"""Dataset selection handlers for VisFEM."""
from pathlib import Path

import pyvista as pv
from typing import Any, Callable
from vtkmodules.vtkRenderingCore import vtkActor

from visfem.engine.colors import region_colors
from visfem.engine.palettes import CATEGORICAL_PALETTES
from visfem.engine.scene import (
    TIBIA_SIM_FIELDS, RenderResult, TrameCtrl,
    clear_scene, field_label, redraw_aneurysm, redraw_aneurysm_coils, redraw_heart, redraw_heart_ep,
    redraw_ircadb, redraw_tibia_mesh, redraw_tibia_simulation, redraw_xdmf,
    redraw_rectangle_one_tree, redraw_rectangle_two_trees, redraw_rectangle_quad,
    redraw_liver_vessels,
    get_active_actor, update_actor_palette, update_tibia_sim_field, update_xdmf_step,
    store_static_actor, restore_static_actor,
)
from visfem.log import get_logger
from visfem.models import MeshMetadata, ProjectMetadata
from visfem.engine.discovery import dataset_dir, discover_xdmf, meta_to_state, pvd_file_path

logger = get_logger(__name__)


def _scalar_fields_from_meta(mesh_meta: MeshMetadata | None) -> list[dict[str, str]]:
    """Return {name, label} entries for scalar (shape==[1]) fields in *mesh_meta*, sorted alphabetically."""
    if mesh_meta is None:
        return []
    return sorted(
        [
            {"name": fname, "label": field_label(fname)}
            for fname, finfo in mesh_meta.fields.items()
            if finfo.shape == [1]
        ],
        key=lambda f: f["label"].lower(),
    )


def _resolve_palette(state: Any) -> list[str]:
    """Return the active categorical palette colors from state."""
    name: str = str(state.active_categorical_palette)
    colors = CATEGORICAL_PALETTES.get(name, CATEGORICAL_PALETTES["paired"])
    return list(reversed(colors)) if getattr(state, "color_reversed", False) else colors


# Fields present in heart_iv VTUs that are not meaningful for display
_HEART_IV_EXCLUDED: frozenset[str] = frozenset(
    {"Fixation", "PointID", "Material", "CellID", "f", "n", "s"}
)


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


_STATIC_DATASETS: frozenset[str] = frozenset({
    "heart", "tibia_mesh", "aneurysm", "aneurysm_coils", "heart_ep",
    "rectangle_one_tree", "rectangle_two_trees",
    "rectangle_quad_500", "rectangle_quad_2000", "rectangle_quad_3000",
    "liver_vessels",
})

_STATIC_REDRAW: dict[str, Callable[..., RenderResult]] = {
    "heart":               redraw_heart,
    "tibia_mesh":          redraw_tibia_mesh,
    "aneurysm":            redraw_aneurysm,
    "aneurysm_coils":      redraw_aneurysm_coils,
    "heart_ep":            redraw_heart_ep,
    "rectangle_one_tree":  redraw_rectangle_one_tree,
    "rectangle_two_trees": redraw_rectangle_two_trees,
    "rectangle_quad_500":  redraw_rectangle_quad,
    "rectangle_quad_2000": redraw_rectangle_quad,
    "rectangle_quad_3000": redraw_rectangle_quad,
    "liver_vessels":       redraw_liver_vessels,
}


def _redraw_static(
    key: str,
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    meta: ProjectMetadata,
    ddir: Path,
    state: Any,
    opacity: float,
) -> RenderResult:
    entry = restore_static_actor(key, plotter, ctrl, state.dark_mode)
    if entry is not None:
        colors = _resolve_palette(state)
        update_actor_palette(plotter, ctrl, colors, len(entry.legend_items))
        legend = [{**item, "color": colors[i]} for i, item in enumerate(entry.legend_items)]
        return RenderResult(legend_items=legend, mesh_stats=entry.mesh_stats, fiber_actor=entry.fiber_actor)

    fn = _STATIC_REDRAW[key]
    common = dict(dark_mode=state.dark_mode, opacity=opacity, palette=_resolve_palette(state))
    result = fn(plotter, ctrl, meta, ddir, **common) if key == "heart" else fn(plotter, ctrl, ddir, **common)
    store_static_actor(key, get_active_actor(), result.fiber_actor, result.legend_items, result.mesh_stats)
    return result


def select_dataset(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    key: str,
) -> vtkActor | None:
    """Route to the correct redraw based on dataset key."""
    state.active_dataset = key
    state.active_patient = None
    state.show_fibers = False
    _reset_selection_state(state)

    # Default color scheme per dataset type
    if key in ("tibia_simulation", "tibia_mesh"):
        state.active_categorical_palette = "clinical"
    else:
        state.active_categorical_palette = "paired"
    state.active_continuous_cmap = "viridis"

    opacity = float(state.ctrl_opacity)
    state.trame__busy = True
    fiber_actor: vtkActor | None = None
    try:
        meta = project_metadata[key]
        ddir = dataset_dir(meta)
        xdmf_files = discover_xdmf(ddir)
        if key in _STATIC_DATASETS:
            result = _redraw_static(key, plotter, ctrl, meta, ddir, state, opacity)
            state.legend_items = result.legend_items
            state.mesh_stats = result.mesh_stats
            state.scalar_bar = None
            if key == "heart":
                fiber_actor = result.fiber_actor
        elif key == "ircadb":
            state.legend_items = []
            state.mesh_stats = None
            state.scalar_bar = None
            clear_scene(plotter, state.dark_mode)
        elif key == "tibia_simulation":
            default_field: str | None = TIBIA_SIM_FIELDS[0]["name"]
            assert default_field is not None
            result = redraw_tibia_simulation(
                plotter, ctrl, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                field=default_field,
                palette=_resolve_palette(state),
                cmap=_resolve_cmap(state),
            )
            state.legend_items = result.legend_items
            state.mesh_stats = result.mesh_stats
            state.scalar_bar = result.scalar_bar_info
            state.available_scalar_fields = TIBIA_SIM_FIELDS
            state.active_scalar_field = default_field
        elif key == "heart_iv":
            pvd_p = pvd_file_path(meta)
            if pvd_p is None or not pvd_p.exists():
                logger.error(f"PVD file not found for '{key}'")
            else:
                pvd_meta = xdmf_meta.get(pvd_p.stem)
                scalar_fields = [
                    f for f in _scalar_fields_from_meta(pvd_meta)
                    if f["name"] not in _HEART_IV_EXCLUDED
                ]
                default_field = scalar_fields[0]["name"] if scalar_fields else None
                result = redraw_xdmf(
                    plotter, ctrl, pvd_p, xdmf_meta,
                    dark_mode=state.dark_mode,
                    opacity=opacity,
                    field=default_field,
                    step=0,
                    cmap=_resolve_cmap(state),
                )
                state.legend_items = result.legend_items
                state.mesh_stats = result.mesh_stats
                state.scalar_bar = result.scalar_bar_info
                state.available_scalar_fields = scalar_fields
                state.active_scalar_field = default_field
                state.n_steps = pvd_meta.n_steps if pvd_meta else 1
                state.step_times = list(pvd_meta.times) if pvd_meta else []
        elif xdmf_files:
            first_stem, first_path = next(iter(xdmf_files.items()))
            first_meta = xdmf_meta.get(first_stem)
            scalar_fields = _scalar_fields_from_meta(first_meta)
            default_field = scalar_fields[0]["name"] if scalar_fields else None
            result = redraw_xdmf(
                plotter, ctrl, first_path, xdmf_meta,
                dark_mode=state.dark_mode,
                opacity=opacity,
                field=default_field,
                step=0,
                cmap=_resolve_cmap(state),
            )
            state.legend_items = result.legend_items
            state.mesh_stats = result.mesh_stats
            state.scalar_bar = result.scalar_bar_info
            state.available_scalar_fields = scalar_fields
            state.active_scalar_field = default_field
            state.n_steps = first_meta.n_steps if first_meta else 1
            state.step_times = list(first_meta.times) if first_meta else []
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
    opacity = float(state.ctrl_opacity)
    state.trame__busy = True
    try:
        meta = project_metadata[key]
        path = discover_xdmf(dataset_dir(meta)).get(stem)
        if path is None:
            logger.error(f"XDMF file not found: {stem} in {key}")
            return
        stem_meta = xdmf_meta.get(stem)
        scalar_fields = _scalar_fields_from_meta(stem_meta)
        default_field = scalar_fields[0]["name"] if scalar_fields else None
        result = redraw_xdmf(
            plotter, ctrl, path, xdmf_meta,
            dark_mode=state.dark_mode,
            opacity=opacity,
            field=default_field,
            step=0,
            cmap=_resolve_cmap(state),
        )
        state.legend_items = result.legend_items
        state.mesh_stats = result.mesh_stats
        state.scalar_bar = result.scalar_bar_info
        state.available_scalar_fields = scalar_fields
        state.active_scalar_field = default_field
        state.n_steps = stem_meta.n_steps if stem_meta else 1
        state.step_times = list(stem_meta.times) if stem_meta else []
        state.active_meta = meta_to_state(project_metadata[key])
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
    opacity = float(state.ctrl_opacity)
    state.trame__busy = True
    try:
        active_dataset: str = state.active_dataset
        if active_dataset == "tibia_simulation":
            if get_active_actor() is not None:
                meta = project_metadata["tibia_simulation"]
                legend, scalar_bar = update_tibia_sim_field(
                    plotter, ctrl, dataset_dir(meta),
                    field=field,
                    palette=_resolve_palette(state),
                    cmap=_resolve_cmap(state),
                )
                state.legend_items = legend
                state.scalar_bar = scalar_bar
                return
            meta = project_metadata["tibia_simulation"]
            result = redraw_tibia_simulation(
                plotter, ctrl, dataset_dir(meta),
                dark_mode=state.dark_mode,
                opacity=opacity,
                field=field,
                palette=_resolve_palette(state),
                cmap=_resolve_cmap(state),
                reset_camera=False,
            )
            state.legend_items = result.legend_items
            state.mesh_stats = result.mesh_stats
            state.scalar_bar = result.scalar_bar_info
        else:
            # XDMF or PVD dataset - resolve the active timeseries file path.
            meta = project_metadata[active_dataset]
            xdmf_files = discover_xdmf(dataset_dir(meta))
            path = _timeseries_path(meta, state, xdmf_files)
            if path is None:
                logger.error(f"No timeseries file found for dataset '{active_dataset}'")
                return
            current_step: int = int(state.active_step)
            result = redraw_xdmf(
                plotter, ctrl, path, xdmf_meta,
                dark_mode=state.dark_mode,
                opacity=opacity,
                field=field,
                step=current_step,
                reset_camera=False,
                cmap=_resolve_cmap(state),
            )
            state.legend_items = result.legend_items
            state.mesh_stats = result.mesh_stats
            state.scalar_bar = result.scalar_bar_info
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
    """Navigate the current XDMF dataset to a different timestep."""
    state.active_step = step
    opacity = float(state.ctrl_opacity)
    state.trame__busy = True
    try:
        active_dataset: str = state.active_dataset
        meta = project_metadata[active_dataset]
        xdmf_files = discover_xdmf(dataset_dir(meta))
        path = _timeseries_path(meta, state, xdmf_files)
        if path is None:
            logger.error(f"No timeseries file found for dataset '{active_dataset}'")
            return
        field: str | None = state.active_scalar_field
        cmap = _resolve_cmap(state)
        success, stats, scalar_bar = update_xdmf_step(
            plotter, ctrl, path, xdmf_meta,
            step=step, field=field, cmap=cmap,
        )
        if not success:
            result = redraw_xdmf(
                plotter, ctrl, path, xdmf_meta,
                dark_mode=state.dark_mode,
                opacity=opacity,
                field=field,
                step=step,
                reset_camera=False,
                cmap=cmap,
            )
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
    opacity = float(state.ctrl_opacity)
    state.trame__busy = True
    try:
        meta = project_metadata[dataset_key]
        patient_dir = dataset_dir(meta) / f"patient_{patient:02d}"
        result = redraw_ircadb(
            plotter, ctrl, patient_dir,
            dark_mode=state.dark_mode,
            opacity=opacity,
            palette=_resolve_palette(state),
        )
        state.legend_items = result.legend_items
        state.mesh_stats = result.mesh_stats
        state.active_meta = meta_to_state(meta)
    finally:
        state.trame__busy = False


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

    opacity = float(state.ctrl_opacity)
    state.trame__busy = True
    try:
        if state.active_patient is not None:
            if get_active_actor() is not None:
                n = len(state.legend_items)
                colors = region_colors(n, _resolve_palette(state))
                update_actor_palette(plotter, ctrl, colors, n)
                state.legend_items = [
                    {**item, "color": colors[i]}
                    for i, item in enumerate(state.legend_items)
                ]
                return
            patient: int = state.active_patient
            meta = project_metadata[key]
            patient_dir = dataset_dir(meta) / f"patient_{patient:02d}"
            result = redraw_ircadb(
                plotter, ctrl, patient_dir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
                reset_camera=False,
            )
            state.legend_items = result.legend_items
            state.mesh_stats = result.mesh_stats
        elif key == "heart":
            if get_active_actor() is not None:
                n = len(state.legend_items)
                colors = region_colors(n, _resolve_palette(state))
                update_actor_palette(plotter, ctrl, colors, n)
                state.legend_items = [
                    {**item, "color": colors[i]}
                    for i, item in enumerate(state.legend_items)
                ]
                return
            meta = project_metadata["heart"]
            ddir = dataset_dir(meta)
            result = redraw_heart(
                plotter, ctrl, meta, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
                reset_camera=False,
            )
            state.legend_items = result.legend_items
            state.mesh_stats = result.mesh_stats
        elif key == "heart_ep":
            if get_active_actor() is not None:
                n = len(state.legend_items)
                colors = region_colors(n, _resolve_palette(state))
                update_actor_palette(plotter, ctrl, colors, n)
                state.legend_items = [
                    {**item, "color": colors[i]}
                    for i, item in enumerate(state.legend_items)
                ]
                return
            meta = project_metadata["heart_ep"]
            ddir = dataset_dir(meta)
            result = redraw_heart_ep(
                plotter, ctrl, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
                reset_camera=False,
            )
            state.legend_items = result.legend_items
            state.mesh_stats = result.mesh_stats
        elif key == "tibia_mesh":
            if get_active_actor() is not None:
                n = len(state.legend_items)
                colors = region_colors(n, _resolve_palette(state))
                update_actor_palette(plotter, ctrl, colors, n)
                state.legend_items = [
                    {**item, "color": colors[i]}
                    for i, item in enumerate(state.legend_items)
                ]
                return
            meta = project_metadata["tibia_mesh"]
            ddir = dataset_dir(meta)
            result = redraw_tibia_mesh(
                plotter, ctrl, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
                reset_camera=False,
            )
            state.legend_items = result.legend_items
            state.mesh_stats = result.mesh_stats
        elif key in ("rectangle_one_tree", "rectangle_two_trees",
                     "rectangle_quad_500", "rectangle_quad_2000", "rectangle_quad_3000",
                     "liver_vessels"):
            redraw_fn = _STATIC_REDRAW[key]
            meta = project_metadata[key]
            ddir = dataset_dir(meta)
            result = redraw_fn(
                plotter, ctrl, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
                reset_camera=False,
            )
            state.legend_items = result.legend_items
            state.mesh_stats = result.mesh_stats
        elif key == "aneurysm":
            meta = project_metadata["aneurysm"]
            ddir = dataset_dir(meta)
            result = redraw_aneurysm(
                plotter, ctrl, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
                reset_camera=False,
            )
            state.legend_items = result.legend_items
            state.mesh_stats = result.mesh_stats
        elif key == "aneurysm_coils":
            if get_active_actor() is not None:
                n = len(state.legend_items)
                colors = region_colors(n, _resolve_palette(state))
                update_actor_palette(plotter, ctrl, colors, n)
                state.legend_items = [
                    {**item, "color": colors[i]}
                    for i, item in enumerate(state.legend_items)
                ]
                return
            meta = project_metadata["aneurysm_coils"]
            ddir = dataset_dir(meta)
            result = redraw_aneurysm_coils(
                plotter, ctrl, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
                reset_camera=False,
            )
            state.legend_items = result.legend_items
            state.mesh_stats = result.mesh_stats
        elif key == "tibia_simulation":
            if get_active_actor() is not None:
                meta = project_metadata["tibia_simulation"]
                legend, scalar_bar = update_tibia_sim_field(
                    plotter, ctrl, dataset_dir(meta),
                    field=state.active_scalar_field,
                    palette=_resolve_palette(state),
                    cmap=_resolve_cmap(state),
                )
                state.legend_items = legend
                state.scalar_bar = scalar_bar
                return
            meta = project_metadata["tibia_simulation"]
            field: str = state.active_scalar_field
            result = redraw_tibia_simulation(
                plotter, ctrl, dataset_dir(meta),
                dark_mode=state.dark_mode,
                opacity=opacity,
                field=field,
                palette=_resolve_palette(state),
                cmap=_resolve_cmap(state),
                reset_camera=False,
            )
            state.legend_items = result.legend_items
            state.mesh_stats = result.mesh_stats
            state.scalar_bar = result.scalar_bar_info
        else:
            # XDMF or PVD dataset
            meta = project_metadata[key]
            xdmf_files = discover_xdmf(dataset_dir(meta))
            path = _timeseries_path(meta, state, xdmf_files)
            if path is None:
                logger.error(f"No timeseries file found for dataset '{key}'")
                return
            field = state.active_scalar_field
            step: int = int(state.active_step)
            result = redraw_xdmf(
                plotter, ctrl, path, xdmf_meta,
                dark_mode=state.dark_mode,
                opacity=opacity,
                field=field,
                step=step,
                reset_camera=False,
                cmap=_resolve_cmap(state),
            )
            state.mesh_stats = result.mesh_stats
            state.scalar_bar = result.scalar_bar_info
    finally:
        state.trame__busy = False
