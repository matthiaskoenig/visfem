"""Renderer registry and render-config resolution.

A dataset's rendering behaviour is declared in its JSON ``render`` block
(``visfem.models.RenderConfig``). This module turns that declarative config — or,
when absent, an inferred one — into a call to one of a small set of built-in
renderers. The point is that adding a dataset is data-only: no Python edits, even
for a pip-installed user pointing ``DATA_DIR`` at their own data folder.

``resolve_render_config`` fills in an unset ``renderer`` (and a few unset paths)
by inspecting ``mesh_format`` and the files on disk, so the simplest datasets need
little or no ``render`` block. The renderers themselves are thin adapters over the
generic helpers in ``visfem.engine.scene`` — the VTK code is reused, not rewritten.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pyvista as pv

from visfem.engine.colors import region_colors
from visfem.engine.discovery import discover_xdmf, grasp_phase_pvd, pvd_file_path
from visfem.mesh import metadata_for_series, vtk_series_steps
from visfem.engine.scene import (
    RenderResult, TrameCtrl,
    _load_multi_part_vtk, _render_labeled_parts, _render_region_array_mesh,
    clear_scene, redraw_ircadb, redraw_region_surface_step,
    redraw_scalar_field, redraw_stl_surface, redraw_xdmf,
)
from visfem.log import get_logger
from visfem.models import MeshMetadata, ProjectMetadata, RenderConfig, RendererName

logger = get_logger(__name__)

_SURFACE_EXTS = (".stl", ".vtu", ".obj", ".vtp", ".vtk", ".ply")


# ---- Render-config resolution / inference ----

def _has_patient_dirs(ddir: Path) -> bool:
    return any(d.is_dir() for d in ddir.glob("patient_*"))


def _first_patient_dir(ddir: Path) -> Path | None:
    dirs = sorted(d for d in ddir.glob("patient_*") if d.is_dir())
    return dirs[0] if dirs else None


def _infer_renderer(meta: ProjectMetadata, ddir: Path) -> RendererName:
    """Infer a renderer from mesh_format + on-disk layout.

    Precedence mirrors the previous hardcoded fallthrough in select_dataset:
    PVD/XDMF time series first, then patient-folder shapes, then a plain surface.
    """
    fmt = meta.mesh_format.upper()
    if fmt == "PVD":
        return RendererName.TIMESERIES
    if "XDMF" in fmt or discover_xdmf(ddir):
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
    """Return the single surface mesh filename in a flat dataset dir, if unambiguous."""
    candidates = [
        p for p in sorted(ddir.iterdir())
        if p.is_file() and p.suffix.lower() in _SURFACE_EXTS
    ]
    return candidates[0].name if len(candidates) == 1 else None


def resolve_render_config(
    meta: ProjectMetadata,
    ddir: Path,
) -> RenderConfig:
    """Return a RenderConfig with a concrete ``renderer`` (explicit or inferred).

    Starts from ``meta.render`` if present, else an empty config, then fills an
    unset ``renderer`` via inference and an unset single ``mesh_file`` for the
    surface renderer where it can be determined unambiguously.
    """
    cfg = meta.render.model_copy(deep=True) if meta.render is not None else RenderConfig()
    if cfg.renderer is None:
        # A declared flat VTK series is a time series regardless of mesh_format (VTK).
        cfg.renderer = RendererName.TIMESERIES if cfg.series else _infer_renderer(meta, ddir)
    if (
        cfg.renderer == RendererName.SURFACE
        and cfg.mesh_file is None
        and not cfg.mesh_candidates
        and not _has_patient_dirs(ddir)
    ):
        cfg.mesh_file = _infer_mesh_file(ddir)
    return cfg


def resolve_mesh_file(ddir: Path, cfg: RenderConfig) -> str | None:
    """Return the surface filename to load: mesh_file, else first existing candidate."""
    if cfg.mesh_file:
        return cfg.mesh_file
    for name in cfg.mesh_candidates:
        if (ddir / name).exists():
            return name
    return None


# ---- Renderer context + registry ----

@dataclass
class RenderContext:
    """Everything a renderer needs. Built once per (re)draw by the dispatch layer."""
    plotter: pv.Plotter
    ctrl: TrameCtrl
    state: Any                       # Trame state (dark_mode, palette/cmap selection, ...)
    ddir: Path                       # dataset dir (or patient dir for patient renderers)
    meta: ProjectMetadata
    cfg: RenderConfig                # resolved (explicit ∪ inferred) render config
    xdmf_meta: dict[str, MeshMetadata]
    opacity: float
    palette: list[str]               # already resolved (see selection._resolve_palette)
    cmap: str                        # already resolved (see selection._resolve_cmap)
    field: str | None = None
    step: int = 0
    reset_camera: bool = True


Renderer = Callable[[RenderContext], RenderResult]


def _common(ctx: RenderContext) -> dict:
    """Shared kwargs for renderers that take dark_mode/opacity/palette."""
    return dict(
        dark_mode=ctx.state.dark_mode,
        opacity=ctx.opacity,
        palette=ctx.palette,
        reset_camera=ctx.reset_camera,
    )


def render_surface(ctx: RenderContext) -> RenderResult:
    """One solid-colour surface mesh (STL/VTU/OBJ)."""
    filename = resolve_mesh_file(ctx.ddir, ctx.cfg)
    if filename is None:
        logger.error(f"No surface mesh resolved in {ctx.ddir}")
        return RenderResult()
    return redraw_stl_surface(ctx.plotter, ctx.ctrl, ctx.ddir, filename=filename, **_common(ctx))


def render_region_id(ctx: RenderContext) -> RenderResult:
    """One mesh coloured by an integer cell array, with a per-region legend and
    (when cfg.fiber is set) an optional fibre glyph overlay."""
    cfg = ctx.cfg
    if not cfg.mesh_file or not cfg.region_array:
        logger.error("region_id renderer requires mesh_file and region_array")
        return RenderResult()
    return _render_region_array_mesh(
        ctx.plotter, ctx.ctrl, ctx.ddir / cfg.mesh_file,
        cfg.region_array, cfg.region_labels, **_common(ctx),
        meta=ctx.meta, labels_mesh_key=cfg.labels_mesh_key, fiber=cfg.fiber,
    )


def render_multi_part(ctx: RenderContext) -> RenderResult:
    """N labelled part files, merged and categorically coloured (optionally tubed)."""
    cfg = ctx.cfg
    parts = [(p.stem, p.label) for p in cfg.parts]
    meshes = _load_multi_part_vtk(ctx.ddir, parts, cfg.part_extensions)
    if meshes is None:
        return RenderResult()
    colors = region_colors(len(parts), ctx.palette)
    labels = [label for _, label in parts]
    clear_scene(ctx.plotter, ctx.state.dark_mode)
    tube = cfg.tube
    return _render_labeled_parts(
        ctx.plotter, ctx.ctrl, meshes, labels, colors, ctx.opacity,
        reset_camera=ctx.reset_camera,
        tubify=tube.enabled if tube else True,
        n_tube_sides=tube.n_sides if tube else 8,
        tube_stride=tube.stride if tube else 1,
    )


def render_timeseries(ctx: RenderContext) -> RenderResult:
    """Scalar-field time series from XDMF, PVD, or a flat VTK series.

    Flat series (cfg.series set): the per-step file is a complete mesh, rendered
    whole with the series' global scalar bounds. Manifest series (XDMF/PVD):
    rendered by indexing the manifest at the step.
    """
    if ctx.cfg.series:
        files = _series_paths(ctx.ddir, ctx.cfg.series)
        if not files:
            logger.error(f"No files match series '{ctx.cfg.series}' in {ctx.ddir}")
            return RenderResult()
        step = max(0, min(ctx.step, len(files) - 1))
        return redraw_xdmf(
            ctx.plotter, ctx.ctrl, files[step], ctx.xdmf_meta,
            dark_mode=ctx.state.dark_mode, opacity=ctx.opacity,
            field=ctx.field, step=0, reset_camera=ctx.reset_camera, cmap=ctx.cmap,
            mesh_meta=_series_metadata(ctx.ddir, ctx.cfg.series),
        )
    path = _timeseries_path(ctx)
    if path is None:
        logger.error(f"No timeseries file for dataset in {ctx.ddir}")
        return RenderResult()
    return redraw_xdmf(
        ctx.plotter, ctx.ctrl, path, ctx.xdmf_meta,
        dark_mode=ctx.state.dark_mode, opacity=ctx.opacity,
        field=ctx.field, step=ctx.step, reset_camera=ctx.reset_camera, cmap=ctx.cmap,
    )


def render_pvd_phase_series(ctx: RenderContext) -> RenderResult:
    """Per-patient region-coloured phase surfaces (GRASP MRI). ddir is the patient dir."""
    pvd = grasp_phase_pvd(ctx.ddir)
    if pvd is None:
        logger.error(f"No phase-series PVD in {ctx.ddir}")
        return RenderResult()
    return redraw_region_surface_step(
        ctx.plotter, ctx.ctrl, pvd,
        dark_mode=ctx.state.dark_mode, opacity=ctx.opacity, step=ctx.step,
        palette=ctx.palette, reset_camera=ctx.reset_camera, solid=ctx.cfg.solid,
    )


def render_patient_organs(ctx: RenderContext) -> RenderResult:
    """Per-patient per-organ .vtk glob (ircadb family). ddir is the patient dir."""
    return redraw_ircadb(ctx.plotter, ctx.ctrl, ctx.ddir, **_common(ctx))


def render_scalar_field(ctx: RenderContext) -> RenderResult:
    """Static single-mesh dataset coloured by a selectable scalar field.

    Continuous fields use a percentile-clamped colour ramp; fields named in
    cfg.categorical_fields render as discrete zones with a region legend.
    """
    cfg = ctx.cfg
    if not cfg.mesh_file:
        logger.error("scalar_field renderer requires mesh_file")
        return RenderResult()
    field = ctx.field or cfg.default_field or (cfg.fields[0].name if cfg.fields else None)
    if field is None:
        logger.error("scalar_field renderer requires a field (cfg.fields / default_field)")
        return RenderResult()
    return redraw_scalar_field(
        ctx.plotter, ctx.ctrl, ctx.ddir,
        dark_mode=ctx.state.dark_mode, opacity=ctx.opacity,
        mesh_file=cfg.mesh_file, field=field,
        categorical_fields=frozenset(cfg.categorical_fields),
        zone_labels=cfg.region_labels,
        palette=ctx.palette, cmap=ctx.cmap,
        percentile=cfg.percentile_clamp if cfg.percentile_clamp is not None else 95,
        reset_camera=ctx.reset_camera,
    )


def _timeseries_path(ctx: RenderContext):
    """Resolve the active timeseries file: PVD, the active XDMF, or the first found."""
    if ctx.meta.mesh_format.upper() == "PVD":
        return pvd_file_path(ctx.meta)
    xdmf_files = discover_xdmf(ctx.ddir)
    stem = getattr(ctx.state, "active_xdmf", None)
    if stem and stem in xdmf_files:
        return xdmf_files[stem]
    return next(iter(xdmf_files.values()), None)


# Flat VTK series: resolve the ordered file list and global metadata once per
# (dir, pattern), since scrubbing re-renders repeatedly and the glob/bounds scan
# is the same every time.
_series_paths_cache: dict[tuple[Path, str], list[Path]] = {}
_series_meta_cache: dict[tuple[Path, str], MeshMetadata] = {}


def _series_paths(ddir: Path, pattern: str) -> list[Path]:
    """Natural-sorted per-step files for a flat VTK series (memoised)."""
    key = (ddir, pattern)
    if key not in _series_paths_cache:
        _series_paths_cache[key] = [p for _, p in vtk_series_steps(ddir, pattern)]
    return _series_paths_cache[key]


def _series_metadata(ddir: Path, pattern: str) -> MeshMetadata | None:
    """MeshMetadata (n_steps, fields, global scalar bounds) for a flat series (memoised)."""
    key = (ddir, pattern)
    if key not in _series_meta_cache:
        files = _series_paths(ddir, pattern)
        if not files:
            return None
        _series_meta_cache[key] = metadata_for_series(files)
    return _series_meta_cache[key]


RENDERER_REGISTRY: dict[RendererName, Renderer] = {
    RendererName.SURFACE:          render_surface,
    RendererName.MULTI_PART:       render_multi_part,
    RendererName.REGION_ID:        render_region_id,
    RendererName.SCALAR_FIELD:     render_scalar_field,
    RendererName.TIMESERIES:       render_timeseries,
    RendererName.PVD_PHASE_SERIES: render_pvd_phase_series,
    RendererName.PATIENT_ORGANS:   render_patient_organs,
}

# Renderers whose datasets are selected per-patient: the top-level dataset click
# clears the scene and the render happens on patient selection.
PATIENT_RENDERERS: frozenset[RendererName] = frozenset({
    RendererName.PATIENT_ORGANS,
    RendererName.PVD_PHASE_SERIES,
})

# Renderers that expose a scalar-field / step time series.
TIMESERIES_RENDERERS: frozenset[RendererName] = frozenset({
    RendererName.TIMESERIES,
})


def dispatch_render(ctx: RenderContext) -> RenderResult:
    """Render *ctx* via the registry entry for its resolved renderer.

    ``ctx.cfg`` must come from ``resolve_render_config`` (which always sets a
    concrete renderer); the assert both documents that and narrows the type.
    """
    renderer = ctx.cfg.renderer
    assert renderer is not None, "render config has no resolved renderer"
    return RENDERER_REGISTRY[renderer](ctx)


def is_patient_renderer(cfg: RenderConfig) -> bool:
    """True if the dataset is patient-driven (rendered on patient select)."""
    return cfg.renderer in PATIENT_RENDERERS


def _scalar_fields(mesh_meta: MeshMetadata | None, cfg: RenderConfig) -> list[dict[str, str]]:
    """Selectable {name,label} fields: explicit cfg list, else discovered minus deny-list."""
    from visfem.engine.scene import field_label
    if cfg.fields:
        return [{"name": f.name, "label": f.label or field_label(f.name)} for f in cfg.fields]
    if mesh_meta is None:
        return []
    deny = set(cfg.exclude_fields)
    return sorted(
        [
            {"name": fname, "label": field_label(fname)}
            for fname, finfo in mesh_meta.fields.items()
            if finfo.shape == [1] and fname not in deny
        ],
        key=lambda f: f["label"].lower(),
    )


def _timeseries_mesh_meta(ctx: RenderContext) -> MeshMetadata | None:
    """MeshMetadata for the active timeseries (for field/step UI population)."""
    if ctx.cfg.series:
        return _series_metadata(ctx.ddir, ctx.cfg.series)
    path = _timeseries_path(ctx)
    return ctx.xdmf_meta.get(path.stem) if path is not None else None


def apply_result_to_state(state: Any, result: RenderResult) -> None:
    """Write the common render outputs (legend/stats/scalar bar) to Trame state."""
    state.legend_items = result.legend_items
    state.mesh_stats = result.mesh_stats
    state.scalar_bar = result.scalar_bar_info


def populate_timeseries_state(state: Any, ctx: RenderContext) -> str | None:
    """Set available_scalar_fields/n_steps/step_times for a timeseries dataset.

    Returns the chosen default field (so the caller can pass it to the renderer).
    """
    mesh_meta = _timeseries_mesh_meta(ctx)
    fields = _scalar_fields(mesh_meta, ctx.cfg)
    default = ctx.cfg.default_field or (fields[0]["name"] if fields else None)
    state.available_scalar_fields = fields
    state.active_scalar_field = default
    state.n_steps = mesh_meta.n_steps if mesh_meta else 1
    state.step_times = list(mesh_meta.times) if mesh_meta else []
    return default
