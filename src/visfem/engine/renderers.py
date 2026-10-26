"""Renderer registry and render-config resolution for a dataset's JSON ``render`` block (``visfem.models.RenderConfig``)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from visfem.engine.colors import apply_overrides_to_state, region_colors
from visfem.engine.discovery import (
    active_timeseries_path,
    discover_xdmf,
    grasp_phase_pvd,
)
from visfem.engine.scene import (
    RenderResult,
    Scene,
    TrameCtrl,
    _load_multi_part_vtk,
    _render_labeled_parts,
    _render_region_array_mesh,
    clear_scene,
    redraw_ircadb,
    redraw_region_surface_step,
    redraw_scalar_field,
    redraw_stl_surface,
    redraw_xdmf,
)
from visfem.log import get_logger
from visfem.mesh import metadata_for_d3plot, metadata_for_series, vtk_series_steps
from visfem.models import MeshMetadata, ProjectMetadata, RenderConfig, RendererName

logger = get_logger(__name__)

_SURFACE_EXTS = (".stl", ".vtu", ".obj", ".vtp", ".vtk", ".ply")


# ---- Render-config resolution / inference ----


def _has_patient_dirs(ddir: Path) -> bool:
    """Return True when ddir holds a patient_* directory."""
    return any(d.is_dir() for d in ddir.glob("patient_*"))


def _first_patient_dir(ddir: Path) -> Path | None:
    """Return the first patient_* directory in ddir by name, or None."""
    dirs = sorted(d for d in ddir.glob("patient_*") if d.is_dir())
    return dirs[0] if dirs else None


def _infer_renderer(meta: ProjectMetadata, ddir: Path) -> RendererName:
    """Return the renderer inferred from meta.mesh_format and the layout of ddir."""
    if meta.is_pvd:
        return RendererName.TIMESERIES
    if "XDMF" in meta.mesh_format.upper() or discover_xdmf(ddir):
        return RendererName.TIMESERIES
    if _has_patient_dirs(ddir):
        pdir = _first_patient_dir(ddir)
        if pdir is not None:
            if grasp_phase_pvd(pdir) is not None:
                return RendererName.PVD_PHASE_SERIES
            if len(list(pdir.glob("*.vtk"))) > 1:
                return RendererName.PATIENT_ORGANS
        return RendererName.SURFACE
    return RendererName.SURFACE


def _infer_mesh_file(ddir: Path) -> str | None:
    """Return the sole surface mesh filename in the flat dir ddir, or None when zero or several exist."""
    candidates = [
        p
        for p in sorted(ddir.iterdir())
        if p.is_file() and p.suffix.lower() in _SURFACE_EXTS
    ]
    return candidates[0].name if len(candidates) == 1 else None


def resolve_render_config(
    meta: ProjectMetadata,
    ddir: Path,
) -> RenderConfig:
    """Return a copy of meta.render whose renderer, and whose surface mesh_file, are inferred from ddir when unset."""
    cfg = (
        meta.render.model_copy(deep=True) if meta.render is not None else RenderConfig()
    )
    if cfg.renderer is None:
        # A declared flat VTK series or LS-DYNA database is a time series and overrides mesh_format.
        cfg.renderer = (
            RendererName.TIMESERIES
            if (cfg.series or cfg.database)
            else _infer_renderer(meta, ddir)
        )
    if (
        cfg.renderer == RendererName.SURFACE
        and cfg.mesh_file is None
        and not cfg.mesh_candidates
        and not _has_patient_dirs(ddir)
    ):
        cfg.mesh_file = _infer_mesh_file(ddir)
    return cfg


def resolve_mesh_file(ddir: Path, cfg: RenderConfig) -> str | None:
    """Return the surface filename in ddir that cfg selects, or None."""
    if cfg.mesh_file:
        return cfg.mesh_file
    for name in cfg.mesh_candidates:
        if (ddir / name).exists():
            return name
    return None


# ---- Renderer context + registry ----


@dataclass
class RenderContext:
    """Inputs for one renderer call, built per draw by the dispatch layer."""

    scene: Scene
    ctrl: TrameCtrl
    state: Any  # Trame state (dark_mode, palette/cmap selection, ...)
    ddir: Path  # dataset dir (or patient dir for patient renderers)
    meta: ProjectMetadata
    cfg: RenderConfig  # resolved (explicit plus inferred) render config
    xdmf_meta: dict[Path, MeshMetadata]
    opacity: float
    palette: list[str]  # resolved by selection._resolve_palette
    cmap: str  # resolved by selection.resolve_cmap
    field: str | None = None
    step: int = 0
    reset_camera: bool = True


Renderer = Callable[[RenderContext], RenderResult]  # adapter over visfem.engine.scene


def _common(ctx: RenderContext) -> dict:
    """Return the keyword arguments from ctx that the palette renderers share."""
    return {
        "dark_mode": ctx.state.dark_mode,
        "opacity": ctx.opacity,
        "palette": ctx.palette,
        "reset_camera": ctx.reset_camera,
    }


def render_surface(ctx: RenderContext) -> RenderResult:
    """Render ctx's single solid-colour surface mesh and return the RenderResult."""
    filename = resolve_mesh_file(ctx.ddir, ctx.cfg)
    if filename is None:
        logger.error(
            "surface renderer requires mesh_file or an existing mesh candidate in %s",
            ctx.ddir,
        )
        return RenderResult()
    return redraw_stl_surface(
        ctx.scene, ctx.ctrl, ctx.ddir, filename=filename, **_common(ctx)
    )


def render_region_id(ctx: RenderContext) -> RenderResult:
    """Render ctx's mesh coloured by the integer cell array cfg.region_array, with a per-region legend and the optional cfg.fiber overlay; return the RenderResult."""
    cfg = ctx.cfg
    if not cfg.mesh_file or not cfg.region_array:
        logger.error("region_id renderer requires mesh_file and region_array")
        return RenderResult()
    return _render_region_array_mesh(
        ctx.scene,
        ctx.ctrl,
        ctx.ddir / cfg.mesh_file,
        cfg.region_array,
        cfg.region_labels,
        **_common(ctx),
        meta=ctx.meta,
        labels_mesh_key=cfg.labels_mesh_key,
        fiber=cfg.fiber,
    )


def render_multi_part(ctx: RenderContext) -> RenderResult:
    """Render cfg.parts merged, categorically coloured and tubed per cfg.tube; return the RenderResult."""
    cfg = ctx.cfg
    parts = [(p.stem, p.label) for p in cfg.parts]
    meshes = _load_multi_part_vtk(ctx.ddir, parts, cfg.part_extensions)
    colors = region_colors(len(parts), ctx.palette)
    labels = [label for _, label in parts]
    clear_scene(ctx.scene, ctx.state.dark_mode)
    tube = cfg.tube
    return _render_labeled_parts(
        ctx.scene,
        ctx.ctrl,
        meshes,
        labels,
        colors,
        ctx.opacity,
        reset_camera=ctx.reset_camera,
        tubify=tube.enabled if tube else True,
        n_tube_sides=tube.n_sides if tube else 8,
        tube_stride=tube.stride if tube else 1,
    )


def render_timeseries(ctx: RenderContext) -> RenderResult:
    """Render ctx's scalar-field time series at ctx.step from a flat VTK series (cfg.series, one file per step), an LS-DYNA database (cfg.database) or a PVD/XDMF manifest; return the RenderResult."""
    if ctx.cfg.database:
        # LS-DYNA d3plot: the database dir is the mesh path and load_mesh streams one frame per step.
        return redraw_xdmf(
            ctx.scene,
            ctx.ctrl,
            ctx.ddir,
            ctx.xdmf_meta,
            dark_mode=ctx.state.dark_mode,
            opacity=ctx.opacity,
            field=ctx.field,
            step=ctx.step,
            reset_camera=ctx.reset_camera,
            cmap=ctx.cmap,
            mesh_meta=_d3plot_metadata(ctx.ddir),
        )
    if ctx.cfg.series:
        files = _series_paths(ctx.ddir, ctx.cfg.series)
        if not files:
            logger.error(
                "timeseries renderer requires at least one file matching series '%s' in %s",
                ctx.cfg.series,
                ctx.ddir,
            )
            return RenderResult()
        step = max(0, min(ctx.step, len(files) - 1))
        return redraw_xdmf(
            ctx.scene,
            ctx.ctrl,
            files[step],
            ctx.xdmf_meta,
            dark_mode=ctx.state.dark_mode,
            opacity=ctx.opacity,
            field=ctx.field,
            step=0,
            reset_camera=ctx.reset_camera,
            cmap=ctx.cmap,
            mesh_meta=_series_metadata(ctx.ddir, ctx.cfg.series),
        )
    path = active_timeseries_path(ctx.meta, ctx.state, ctx.ddir)
    if path is None:
        logger.error("timeseries renderer requires a PVD or XDMF file in %s", ctx.ddir)
        return RenderResult()
    return redraw_xdmf(
        ctx.scene,
        ctx.ctrl,
        path,
        ctx.xdmf_meta,
        dark_mode=ctx.state.dark_mode,
        opacity=ctx.opacity,
        field=ctx.field,
        step=ctx.step,
        reset_camera=ctx.reset_camera,
        cmap=ctx.cmap,
    )


def render_pvd_phase_series(ctx: RenderContext) -> RenderResult:
    """Render the region-coloured GRASP MRI phase surface at ctx.step for the patient dir ctx.ddir; return the RenderResult."""
    pvd = grasp_phase_pvd(ctx.ddir)
    if pvd is None:
        logger.error(
            "pvd_phase_series renderer requires a phase-series PVD in %s", ctx.ddir
        )
        return RenderResult()
    return redraw_region_surface_step(
        ctx.scene,
        ctx.ctrl,
        pvd,
        dark_mode=ctx.state.dark_mode,
        opacity=ctx.opacity,
        step=ctx.step,
        palette=ctx.palette,
        reset_camera=ctx.reset_camera,
        solid=ctx.cfg.solid,
    )


def render_patient_organs(ctx: RenderContext) -> RenderResult:
    """Render the per-organ .vtk files (ircadb family) in the patient dir ctx.ddir; return the RenderResult."""
    return redraw_ircadb(ctx.scene, ctx.ctrl, ctx.ddir, **_common(ctx))


def render_scalar_field(ctx: RenderContext) -> RenderResult:
    """Render ctx's static mesh coloured by its field as a percentile-clamped ramp, or as discrete zones for cfg.categorical_fields; return the RenderResult."""
    cfg = ctx.cfg
    if not cfg.mesh_file:
        logger.error("scalar_field renderer requires mesh_file")
        return RenderResult()
    field = (
        ctx.field or cfg.default_field or (cfg.fields[0].name if cfg.fields else None)
    )
    if field is None:
        logger.error(
            "scalar_field renderer requires a field (cfg.fields / default_field)"
        )
        return RenderResult()
    return redraw_scalar_field(
        ctx.scene,
        ctx.ctrl,
        ctx.ddir,
        dark_mode=ctx.state.dark_mode,
        opacity=ctx.opacity,
        mesh_file=cfg.mesh_file,
        field=field,
        categorical_fields=frozenset(cfg.categorical_fields),
        zone_labels=cfg.region_labels,
        palette=ctx.palette,
        cmap=ctx.cmap,
        percentile=cfg.percentile_clamp,
        reset_camera=ctx.reset_camera,
    )


# Per-(dir, pattern) caches for a flat VTK series' ordered files and global metadata.
_series_paths_cache: dict[tuple[Path, str], list[Path]] = {}
_series_meta_cache: dict[tuple[Path, str], MeshMetadata] = {}


def _series_paths(ddir: Path, pattern: str) -> list[Path]:
    """Return the natural-sorted per-step files of the flat VTK series pattern in ddir."""
    key = (ddir, pattern)
    if key not in _series_paths_cache:
        _series_paths_cache[key] = [p for _, p in vtk_series_steps(ddir, pattern)]
    return _series_paths_cache[key]


def _series_metadata(ddir: Path, pattern: str) -> MeshMetadata | None:
    """Return the MeshMetadata (n_steps, fields, global scalar bounds) of the flat VTK series pattern in ddir, or None when it has zero files."""
    key = (ddir, pattern)
    if key not in _series_meta_cache:
        files = _series_paths(ddir, pattern)
        if not files:
            return None
        _series_meta_cache[key] = metadata_for_series(files)
    return _series_meta_cache[key]


# Per-database-dir cache; the first lookup runs the global-bounds scan or sidecar read.
_d3plot_meta_cache: dict[Path, MeshMetadata] = {}


def _d3plot_metadata(ddir: Path) -> MeshMetadata | None:
    """Return the sidecar-backed MeshMetadata of the LS-DYNA d3plot database in ddir."""
    if ddir not in _d3plot_meta_cache:
        _d3plot_meta_cache[ddir] = metadata_for_d3plot(ddir)
    return _d3plot_meta_cache[ddir]


RENDERER_REGISTRY: dict[RendererName, Renderer] = {
    RendererName.SURFACE: render_surface,
    RendererName.MULTI_PART: render_multi_part,
    RendererName.REGION_ID: render_region_id,
    RendererName.SCALAR_FIELD: render_scalar_field,
    RendererName.TIMESERIES: render_timeseries,
    RendererName.PVD_PHASE_SERIES: render_pvd_phase_series,
    RendererName.PATIENT_ORGANS: render_patient_organs,
}

# Renderers that draw on patient selection; the dataset click clears the scene.
PATIENT_RENDERERS: frozenset[RendererName] = frozenset(
    {
        RendererName.PATIENT_ORGANS,
        RendererName.PVD_PHASE_SERIES,
    }
)

# Renderers that expose a scalar-field time series with steps.
TIMESERIES_RENDERERS: frozenset[RendererName] = frozenset(
    {
        RendererName.TIMESERIES,
    }
)


def dispatch_render(ctx: RenderContext) -> RenderResult:
    """Render ctx with the registry entry for cfg.renderer and return the RenderResult."""
    renderer = ctx.cfg.renderer
    assert renderer is not None, (
        "dispatch_render needs a config from resolve_render_config"
    )
    return RENDERER_REGISTRY[renderer](ctx)


def is_patient_renderer(cfg: RenderConfig) -> bool:
    """Return True when cfg.renderer draws on patient selection."""
    return cfg.renderer in PATIENT_RENDERERS


def _scalar_fields(
    mesh_meta: MeshMetadata | None, cfg: RenderConfig
) -> list[dict[str, str]]:
    """Return the selectable {name,label} fields: cfg.fields, else the scalar and vector (magnitude) fields of mesh_meta."""
    from visfem.engine.scene import field_label

    if cfg.fields:
        return [
            {"name": f.name, "label": f.label or field_label(f.name)}
            for f in cfg.fields
        ]
    if mesh_meta is None:
        return []
    deny = set(cfg.exclude_fields)
    out: list[dict[str, str]] = []
    for fname, finfo in mesh_meta.fields.items():
        if fname in deny:
            continue
        if finfo.shape == [1]:
            out.append({"name": fname, "label": field_label(fname)})
        elif finfo.shape == [3]:
            out.append({"name": fname, "label": f"{field_label(fname)} (magnitude)"})
    return sorted(out, key=lambda f: f["label"].lower())


def _timeseries_mesh_meta(ctx: RenderContext) -> MeshMetadata | None:
    """Return the MeshMetadata of ctx's active timeseries source, or None."""
    if ctx.cfg.database:
        return _d3plot_metadata(ctx.ddir)
    if ctx.cfg.series:
        return _series_metadata(ctx.ddir, ctx.cfg.series)
    path = active_timeseries_path(ctx.meta, ctx.state, ctx.ddir)
    return ctx.xdmf_meta.get(path) if path is not None else None


def apply_result_to_state(state: Any, result: RenderResult) -> None:
    """Write result's legend, mesh stats and scalar bar to Trame state."""
    # Renderers emit plain palette colours; apply_overrides_to_state reapplies the per-category overrides.
    apply_overrides_to_state(state, result.legend_items)
    state.mesh_stats = result.mesh_stats
    state.scalar_bar = result.scalar_bar_info


def populate_timeseries_state(state: Any, ctx: RenderContext) -> str | None:
    """Populate the timeseries field and step state from ctx and return the default field."""
    mesh_meta = _timeseries_mesh_meta(ctx)
    fields = _scalar_fields(mesh_meta, ctx.cfg)
    default = ctx.cfg.default_field or (fields[0]["name"] if fields else None)
    state.available_scalar_fields = fields
    state.active_scalar_field = default
    state.n_steps = mesh_meta.n_steps if mesh_meta else 1
    state.step_times = list(mesh_meta.times) if mesh_meta else []
    return default
