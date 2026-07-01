"""Scene management and mesh rendering helpers."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pyvista as pv
from vtkmodules.vtkRenderingCore import vtkActor

from visfem.engine.colors import (
    BG_DARK_BOTTOM, BG_DARK_TOP, BG_LIGHT_BOTTOM, BG_LIGHT_TOP,
    region_colors,
)
from visfem.engine.palettes import CATEGORICAL_PALETTES, CONTINUOUS_CMAPS
from visfem.engine.discovery import ircadb_organ_names, format_organ_name
from visfem.log import get_logger
from visfem.mesh import load_mesh, parse_labels_file
from visfem.models import FiberOptions, MeshMetadata, ProjectMetadata

logger = get_logger(__name__)


@dataclass
class RenderResult:
    legend_items: list[dict[str, Any]] = field(default_factory=list)
    mesh_stats: dict[str, Any] | None = None
    scalar_bar_info: dict[str, Any] | None = None
    fiber_actor: vtkActor | None = None


_PERCENTILE_CLAMP: int = 95

_active_actor: vtkActor | None = None
_xdmf_mesh: pv.DataSet | None = None
_xdmf_actor: vtkActor | None = None


def get_active_actor() -> vtkActor | None:
    """Return the currently tracked main mesh actor, or None if no dataset is loaded."""
    return _active_actor


class TrameCtrl(Protocol):
    def view_push_camera(self) -> None: ...
    def view_update(self) -> None: ...
    def view_push_full(self) -> None: ...



# Human-readable labels for known field names
_FIELD_LABELS: dict[str, str] = {
    "vonMises_stress": "von Mises stress",
    "vonMises_equivalent_strain": "von Mises eq. strain",
    "octahedral_shear_strain": "octahedral shear strain",
    "hydrostatic_strain": "hydrostatic strain",
    "volumetric_strain": "volumetric strain",
    "Claes_window": "healing window (Claes)",
    "pressure": "pressure",
    "strain": "strain",
    "Potential":    "transmembrane potential (mV)",
    "Calcium":      "intracellular calcium [Ca\u00b2\u207a]",
    "ActiveStress": "active stress (Pa)",
}


def field_label(name: str) -> str:
    """Return a human-readable label for a scalar field name."""
    return _FIELD_LABELS.get(name, name.replace("_", " "))


def _fmt_value(v: float) -> str:
    """Format a scalar value compactly for the scalar bar."""
    a = abs(v)
    if a == 0.0:
        return "0"
    elif a >= 1000:
        return f"{v:.0f}"
    elif a >= 100:
        return f"{v:.1f}"
    elif a >= 1:
        return f"{v:.2f}"
    elif a >= 0.01:
        return f"{v:.3f}"
    else:
        return f"{v:.2e}"


def _scalar_bar_dict(field: str, clim: list[float], cmap: str) -> dict:
    """Build the scalar_bar state dict for a continuous field."""
    reversed_cmap = cmap.endswith("_r")
    base_cmap = cmap[:-2] if reversed_cmap else cmap
    gradient = CONTINUOUS_CMAPS.get(base_cmap, "linear-gradient(to right, #222, #fff)")
    if reversed_cmap:
        gradient = gradient.replace("to right", "to left")
    return {
        "field_label": _FIELD_LABELS.get(field, field.replace("_", " ")),
        "min_label": _fmt_value(clim[0]),
        "max_label": _fmt_value(clim[1]),
        "min_val": clim[0],
        "max_val": clim[1],
        "gradient": gradient,
    }


# Scene state

def _set_background(plotter: pv.Plotter, dark_mode: bool) -> None:
    if dark_mode:
        plotter.set_background(BG_DARK_BOTTOM, top=BG_DARK_TOP)
    else:
        plotter.set_background(BG_LIGHT_BOTTOM, top=BG_LIGHT_TOP)


def clear_scene(plotter: pv.Plotter, dark_mode: bool) -> None:
    """Remove all actors and reset scene state (removed, not hidden, so the local-mode client drops the geometry)."""
    global _active_actor, _xdmf_mesh, _xdmf_actor
    _active_actor = None
    _xdmf_mesh = None
    _xdmf_actor = None
    for actor in list(plotter.renderer.actors.values()):
        plotter.renderer.RemoveActor(actor)
    _set_background(plotter, dark_mode)


def apply_opacity(plotter: pv.Plotter, opacity: float) -> None:
    """Push opacity value to every vtkActor in the renderer."""
    for actor in plotter.renderer.actors.values():
        if isinstance(actor, vtkActor):
            actor.GetProperty().SetOpacity(opacity)


def push_scene(plotter: pv.Plotter, ctrl: TrameCtrl, reset_camera: bool = True) -> None:
    """Flush VTK pipeline and push the complete scene to vtk.js."""
    plotter.render()
    if reset_camera:
        plotter.reset_camera()
        ctrl.view_push_camera()
    ctrl.view_update()


def push_scene_full(plotter: pv.Plotter, ctrl: TrameCtrl, reset_camera: bool = True) -> None:
    """Force a full (non-delta) scene resend to the vtk.js client.

    ``view_push_full`` republishes every array fresh so the client rebuilds its
    scene graph; a local-mode delta can reference a stale content-hash after a
    dataset switch and paint old geometry or colors. Falls back to a plain delta
    push when no view is bound (e.g. headless tests).
    """
    plotter.render()
    if reset_camera:
        plotter.reset_camera()
        ctrl.view_push_camera()
    push_full = getattr(ctrl, "view_push_full", None)
    if push_full is not None:
        push_full()
    else:
        ctrl.view_update()


# Mapper fast-path helpers — update color/field without rebuilding the scene

def _build_categorical_lut(colors: list[str], n: int) -> pv.LookupTable:
    """Build a fixed discrete LUT from n hex color strings."""
    lut = pv.LookupTable(cmap=colors[:n], n_values=n)
    lut.scalar_range = (0, max(n - 1, 1))
    return lut


def _build_continuous_lut(cmap: str, lo: float, hi: float) -> pv.LookupTable:
    """Build a 256-entry continuous LUT from a named colormap."""
    lut = pv.LookupTable(cmap=cmap, n_values=256)
    lut.scalar_range = (lo, hi)
    return lut


def update_actor_palette(
    plotter: pv.Plotter, ctrl: TrameCtrl, colors: list[str], n: int
) -> None:
    """Swap the categorical LUT on the active actor in place (no-op if none tracked; caller updates legend colors)."""
    if _active_actor is None:
        return
    mapper = _active_actor.GetMapper()
    mapper.SetLookupTable(_build_categorical_lut(colors, n))
    mapper.SetScalarRange(0, max(n - 1, 1))
    mapper.Modified()
    # Full resend so the recolored LUT reaches the client. See push_scene_full.
    push_scene_full(plotter, ctrl, reset_camera=False)


def update_scalar_field_view(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    ddir: Path,
    mesh_file: str,
    field: str,
    categorical_fields: frozenset[str],
    zone_labels: dict[int, list[str]],
    palette: list[str],
    cmap: str,
    percentile: int = _PERCENTILE_CLAMP,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """In-place field/colour update for a scalar_field dataset.

    Switches the active actor's mapper to *field* without rebuilding the scene.
    Categorical fields reuse the ``_zone_id`` array frozen on the actor at first
    render; continuous fields clamp to the *percentile*-th value.
    """
    if _active_actor is None:
        return [], None

    mapper = _active_actor.GetMapper()
    mesh = load_mesh(ddir / mesh_file)  # instant from cache

    if field in categorical_fields:
        zones = mesh.cell_data[field].astype(int)
        zone_ids: list[int] = sorted(int(z) for z in np.unique(zones))
        n = len(zone_ids)
        colors = region_colors(n, palette)
        mapper.SelectColorArray("_zone_id")
        mapper.SetScalarModeToUseCellFieldData()
        mapper.SetInterpolateScalarsBeforeMapping(False)
        mapper.SetLookupTable(_build_categorical_lut(colors, n))
        mapper.SetScalarRange(0, max(n - 1, 1))
        mapper.Modified()
        push_scene_full(plotter, ctrl, reset_camera=False)
        legend = [
            {"names": zone_labels.get(z, [f"Zone {z}"]), "color": colors[i]}
            for i, z in enumerate(zone_ids)
        ]
        return legend, None

    data = mesh.cell_data[field]
    clim = [float(data.min()), float(np.percentile(data, percentile))]
    mapper.SelectColorArray(field)
    mapper.SetScalarModeToUseCellFieldData()
    mapper.SetInterpolateScalarsBeforeMapping(True)
    mapper.SetLookupTable(_build_continuous_lut(cmap, clim[0], clim[1]))
    mapper.SetScalarRange(*clim)
    mapper.Modified()
    push_scene_full(plotter, ctrl, reset_camera=False)
    return [], _scalar_bar_dict(field, clim, cmap)


def update_scalar_range(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    field: str,
    clim: list[float],
    cmap: str,
) -> "dict | None":
    """Update active actor's scalar range without rebuilding the scene."""
    actor = _xdmf_actor if _xdmf_actor is not None else _active_actor
    if actor is None:
        return None
    mapper = actor.GetMapper()
    lut = mapper.GetLookupTable()
    if lut is not None:
        lut.SetTableRange(clim[0], clim[1])
    mapper.SetScalarRange(clim[0], clim[1])
    mapper.Modified()
    push_scene_full(plotter, ctrl, reset_camera=False)
    return _scalar_bar_dict(field, clim, cmap)


# Renderers

def redraw_xdmf(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    path: Path,
    xdmf_meta: dict[str, MeshMetadata],
    dark_mode: bool,
    opacity: float,
    field: str | None = None,
    step: int = 0,
    reset_camera: bool = True,
    cmap: str = "viridis",
    mesh_meta: "MeshMetadata | None" = None,
) -> RenderResult:
    """Load and render one step of a time-series mesh.

    *path* is an XDMF/PVD manifest (indexed by *step*) or a single flat-series
    file. Pass *mesh_meta* for a flat series; else it is looked up by path.stem.
    """
    global _xdmf_mesh, _xdmf_actor
    clear_scene(plotter, dark_mode)
    try:
        mesh = load_mesh(path, step=step)
    except Exception as e:
        logger.error(f"Failed to load '{path.name}' step {step}: {e}")
        return RenderResult()

    _xdmf_mesh = mesh
    if mesh_meta is None:
        mesh_meta = xdmf_meta.get(path.stem)
    if field is None:
        field = next(iter(mesh_meta.fields), None) if mesh_meta else None

    # Vector fields are coloured by magnitude: compute |v| into a temp scalar on
    # the (already-detached) frame and colour by that.
    colour_by = field
    is_vector = bool(field) and field in mesh.array_names and getattr(mesh[field], "ndim", 1) == 2 and mesh[field].shape[1] == 3
    if is_vector:
        colour_by = f"{field}__mag"
        mesh[colour_by] = np.linalg.norm(mesh[field], axis=1)

    # Use precomputed global bounds (scalar fields and vector magnitudes are both
    # keyed by field name) so the colormap scale is stable across all timesteps.
    # Fall back to the current step's range if bounds were not cached yet.
    clim: list[float] | None = None
    if field and mesh_meta and field in mesh_meta.scalar_bounds:
        clim = mesh_meta.scalar_bounds[field]

    _xdmf_actor = plotter.add_mesh(
        mesh,
        scalars=colour_by,
        cmap=cmap,
        clim=clim,
        show_edges=False,
        copy_mesh=False,
        show_scalar_bar=False,
        opacity=opacity,
        render=False,
    )
    # Full resend so the new field/step reaches the client. See push_scene_full.
    push_scene_full(plotter, ctrl, reset_camera=reset_camera)
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}

    scalar_bar: dict | None = None
    if field:
        if clim is None:
            try:
                lo, hi = mesh.get_data_range(colour_by)
                clim = [float(lo), float(hi)]
            except Exception:
                pass
        if clim is not None:
            # Bar label shows the field name (magnitude is implied by the selector).
            scalar_bar = _scalar_bar_dict(field, clim, cmap)

    return RenderResult(mesh_stats=stats, scalar_bar_info=scalar_bar)


def update_xdmf_step(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    path: Path,
    xdmf_meta: dict[str, MeshMetadata],
    step: int,
    field: str | None,
    cmap: str,
) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None]:
    """In-place step update: swap scalars without recreating the actor."""
    if _xdmf_mesh is None or _xdmf_actor is None:
        return False, None, None

    try:
        new_mesh = load_mesh(path, step=step)
    except Exception as e:
        logger.error(f"Failed to load '{path.name}' step {step}: {e}")
        return False, None, None

    if new_mesh.n_points != _xdmf_mesh.n_points or new_mesh.n_cells != _xdmf_mesh.n_cells:
        return False, None, None

    for name in new_mesh.array_names:
        _xdmf_mesh[name] = np.array(new_mesh[name], copy=True)
    _xdmf_mesh.points = np.array(new_mesh.points, copy=True)

    _xdmf_mesh.Modified()
    _xdmf_actor.GetMapper().Modified()
    push_scene_full(plotter, ctrl, reset_camera=False)

    stats = {"n_cells": new_mesh.n_cells, "n_points": new_mesh.n_points}
    scalar_bar: dict | None = None
    if field:
        mesh_meta = xdmf_meta.get(path.stem)
        clim: list[float] | None = None
        if mesh_meta and field in mesh_meta.scalar_bounds:
            clim = mesh_meta.scalar_bounds[field]
        if clim is None:
            try:
                lo, hi = new_mesh.get_data_range(field)
                clim = [float(lo), float(hi)]
            except Exception:
                pass
        if clim is not None:
            scalar_bar = _scalar_bar_dict(field, clim, cmap)

    return True, stats, scalar_bar


def redraw_ircadb(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    patient_dir: Path,
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None = None,
    reset_camera: bool = True,
) -> RenderResult:
    """Load all organ meshes for a patient and render as one merged actor."""
    organs = ircadb_organ_names(patient_dir)
    clear_scene(plotter, dark_mode)

    parts: list[pv.DataSet] = []
    loaded_organs: list[str] = []
    for organ in organs:
        vtk_path = patient_dir / f"{organ}.vtk"
        if not vtk_path.exists():
            logger.warning(f"Organ file not found: {vtk_path}, skipping.")
            continue
        try:
            mesh = load_mesh(vtk_path).triangulate()
            mesh.clear_data()
            mesh.cell_data["region_id"] = np.full(mesh.n_cells, len(parts), dtype=np.int32)
            parts.append(mesh)
            loaded_organs.append(organ)
        except Exception as e:
            logger.error(f"Failed to load '{vtk_path.name}': {e}")

    n = len(parts)
    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]
    colors = region_colors(n, _palette)
    stats: dict[str, int] | None = None
    if parts:
        global _active_actor
        merged = pv.merge(parts)
        _active_actor = plotter.add_mesh(
            merged,
            scalars="region_id",
            cmap=colors,
            clim=[0, max(n - 1, 1)],
            n_colors=n,
            opacity=opacity,
            show_edges=False,
            show_scalar_bar=False,
            copy_mesh=True,
            interpolate_before_map=False,
            render=False,
        )
        stats = {"n_cells": merged.n_cells, "n_points": merged.n_points}
    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl, reset_camera=reset_camera)
    legend = [
        {"names": [format_organ_name(organ)], "color": colors[i]}
        for i, organ in enumerate(loaded_organs)
    ]
    return RenderResult(legend_items=legend, mesh_stats=stats)


def _render_region_array_mesh(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    mesh_path: Path,
    region_array: str,
    region_labels: dict[int, list[str]],
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None = None,
    reset_camera: bool = True,
    *,
    meta: ProjectMetadata | None = None,
    labels_mesh_key: str | None = None,
    fiber: FiberOptions | None = None,
) -> RenderResult:
    """Render one mesh colored by an integer cell array, with a per-region legend.

    The integer ids in *region_array* are remapped to a dense 0..N-1
    ``region_id`` cell array, categorically colored, and labelled from
    *region_labels* (id -> name(s)). When *region_labels* is empty and the
    dataset declares a ``labels_file``, region names fall back to that file
    (keyed by *labels_mesh_key*, else the mesh filename). When *fiber* is set and
    the mesh carries that vector cell array, an oriented glyph overlay is built
    (hidden by default, toggled via the UI) and returned as ``fiber_actor``.
    """
    if not mesh_path.exists():
        logger.error(f"Region mesh not found: {mesh_path}")
        return RenderResult()
    try:
        mesh = load_mesh(mesh_path)
    except Exception as e:
        logger.error(f"Failed to load region mesh {mesh_path}: {e}")
        return RenderResult()

    # Region names: inline region_labels win; else fall back to a labels file.
    label_map: dict[int, list[str]] = dict(region_labels) if region_labels else {}
    if not label_map and meta is not None and meta.labels_file:
        labels_path = mesh_path.parent / meta.labels_file
        if labels_path.exists():
            label_map = parse_labels_file(labels_path).get(labels_mesh_key or mesh_path.name, {})

    ids = mesh.cell_data[region_array].astype(int)
    unique_ids: list[int] = sorted(int(v) for v in np.unique(ids))
    remap = {rid: i for i, rid in enumerate(unique_ids)}
    mesh.cell_data["region_id"] = np.array([remap[r] for r in ids], dtype=np.int32)
    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]
    colors = region_colors(len(unique_ids), _palette)

    global _active_actor
    clear_scene(plotter, dark_mode)
    _active_actor = plotter.add_mesh(
        mesh,
        scalars="region_id",
        cmap=colors,
        clim=[0, len(unique_ids) - 1],
        n_colors=len(unique_ids),
        opacity=opacity,
        show_edges=False,
        show_scalar_bar=False,
        copy_mesh=True,
        interpolate_before_map=False,
        render=False,
    )

    # Optional fibre glyph overlay; hidden by default, toggled via show_fibers.
    fiber_actor: vtkActor | None = None
    if fiber is not None and fiber.array in mesh.cell_data.keys():
        cell_idx = np.arange(0, mesh.n_cells, fiber.stride)
        centers = mesh.extract_cells(cell_idx).cell_centers()
        centers[fiber.array] = mesh.cell_data[fiber.array][cell_idx]
        glyphs = centers.glyph(orient=fiber.array, scale=False, factor=fiber.scale)
        fiber_actor = plotter.add_mesh(
            glyphs, color="black", show_scalar_bar=False, copy_mesh=True, render=False,
        )
        fiber_actor.SetVisibility(False)

    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl, reset_camera=reset_camera)

    legend = [
        {"names": label_map.get(rid, [f"Region {rid}"]), "color": colors[i]}
        for i, rid in enumerate(unique_ids)
    ]
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return RenderResult(legend_items=legend, mesh_stats=stats, fiber_actor=fiber_actor)


def redraw_stl_surface(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
    filename: str,
    palette: list[str] | None = None,
    reset_camera: bool = True,
) -> RenderResult:
    """Render a single named STL/OBJ surface mesh in one solid colour (a closed mesh with no scalar fields)."""
    mesh_path = dataset_dir / filename
    if not mesh_path.exists():
        logger.error(f"Surface mesh not found: {mesh_path}")
        return RenderResult()

    try:
        mesh = load_mesh(mesh_path)
    except Exception as e:
        logger.error(f"Failed to load surface mesh {mesh_path.name}: {e}")
        return RenderResult()

    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]
    color = _palette[0] if _palette else "#d62728"

    global _active_actor
    clear_scene(plotter, dark_mode)
    _active_actor = plotter.add_mesh(
        mesh,
        color=color,
        opacity=opacity,
        show_edges=False,
        show_scalar_bar=False,
        copy_mesh=True,
        render=False,
    )
    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl, reset_camera=reset_camera)

    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return RenderResult(mesh_stats=stats)


def _render_region_mesh(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    mesh: pv.DataSet,
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None,
    reset_camera: bool,
    solid: bool = False,
) -> RenderResult:
    """Clear the scene and render *mesh* coloured by its per-cell ``region_id``.

    Each connected body gets a distinct categorical colour; falls back to a single
    solid colour if the array is absent. Sets the global ``_active_actor``.

    With *solid* True the whole surface is one colour regardless of region_id — used
    for the GRASP phase animation, where per-phase connected-component counts differ
    so categorical colours would flicker distractingly between frames.
    """
    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]

    global _active_actor
    clear_scene(plotter, dark_mode)

    if not solid and "region_id" in mesh.cell_data:
        region_ids = mesh.cell_data["region_id"].astype(int)
        n = int(region_ids.max()) + 1
        colors = region_colors(n, _palette)
        _active_actor = plotter.add_mesh(
            mesh,
            scalars="region_id",
            cmap=colors,
            clim=[0, max(n - 1, 1)],
            n_colors=n,
            opacity=opacity,
            show_edges=False,
            show_scalar_bar=False,
            copy_mesh=True,
            interpolate_before_map=False,
            render=False,
        )
        legend = [{"names": [f"Region {i + 1}"], "color": colors[i]} for i in range(n)]
    else:
        _active_actor = plotter.add_mesh(
            mesh, color=_palette[0], opacity=opacity,
            show_edges=False, show_scalar_bar=False, copy_mesh=True, render=False,
        )
        legend = []

    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl, reset_camera=reset_camera)
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return RenderResult(legend_items=legend, mesh_stats=stats)


def redraw_region_surface_step(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    pvd_path: Path,
    dark_mode: bool,
    opacity: float,
    step: int,
    palette: list[str] | None = None,
    reset_camera: bool = True,
    solid: bool = True,
) -> RenderResult:
    """Render one phase of a region-coloured PVD surface series (GRASP MRI).

    Each phase has independent topology, so this always does a full redraw.
    *solid* defaults on to avoid colour-flicker as the region count changes.
    """
    try:
        mesh = load_mesh(pvd_path, step=step)
    except Exception as e:
        logger.error(f"Failed to load '{pvd_path.name}' step {step}: {e}")
        return RenderResult()
    return _render_region_mesh(plotter, ctrl, mesh, dark_mode, opacity, palette,
                               reset_camera, solid=solid)


def redraw_scalar_field(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
    mesh_file: str,
    field: str,
    categorical_fields: frozenset[str],
    zone_labels: dict[int, list[str]],
    palette: list[str] | None = None,
    cmap: str = "viridis",
    percentile: int = _PERCENTILE_CLAMP,
    reset_camera: bool = True,
) -> RenderResult:
    """Render a static mesh coloured by *field*.

    *categorical_fields* are drawn as discrete zones (a dense ``_zone_id`` array +
    legend); others use a ramp clamped to *percentile* against outlier washout.
    ``_zone_id`` is precomputed so update_scalar_field_view can switch in place.
    """
    sim_path = dataset_dir / mesh_file
    if not sim_path.exists():
        logger.error(f"Scalar-field mesh not found: {sim_path}")
        return RenderResult()
    try:
        mesh = load_mesh(sim_path)
    except Exception as e:
        logger.error(f"Failed to load scalar-field mesh {sim_path}: {e}")
        return RenderResult()

    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]
    is_categorical = field in categorical_fields

    # Precompute _zone_id for the active categorical field so the fast-path can
    # switch to it without a full reload.
    if is_categorical:
        zones = mesh.cell_data[field].astype(int)
        zone_ids: list[int] = sorted(int(z) for z in np.unique(zones))
        zone_map = {z: i for i, z in enumerate(zone_ids)}
        mesh.cell_data["_zone_id"] = np.array([zone_map[int(z)] for z in zones], dtype=np.int32)

    global _active_actor
    clear_scene(plotter, dark_mode)
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}

    if is_categorical:
        n = len(zone_ids)
        colors = region_colors(n, _palette)
        _active_actor = plotter.add_mesh(
            mesh, scalars="_zone_id", cmap=colors, clim=[0, max(n - 1, 1)],
            n_colors=n, opacity=opacity, show_edges=False, show_scalar_bar=False,
            copy_mesh=True, interpolate_before_map=False, render=False,
        )
        apply_opacity(plotter, opacity)
        push_scene(plotter, ctrl, reset_camera=reset_camera)
        legend = [
            {"names": zone_labels.get(z, [f"Zone {z}"]), "color": colors[i]}
            for i, z in enumerate(zone_ids)
        ]
        return RenderResult(legend_items=legend, mesh_stats=stats)

    data = mesh.cell_data[field]
    clim = [float(data.min()), float(np.percentile(data, percentile))]
    _active_actor = plotter.add_mesh(
        mesh, scalars=field, cmap=cmap, clim=clim, opacity=opacity,
        show_edges=False, show_scalar_bar=False, copy_mesh=True, render=False,
    )
    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl, reset_camera=reset_camera)
    return RenderResult(mesh_stats=stats, scalar_bar_info=_scalar_bar_dict(field, clim, cmap))


# Vessel-tree dataset definitions
def _load_multi_part_vtk(
    ddir: Path,
    parts: list[tuple[str, str]],
    extensions: list[str],
) -> list[pv.DataSet] | None:
    """Load meshes for each part stem, trying each extension in order; None if any part is missing."""
    meshes: list[pv.DataSet] = []
    for stem, _ in parts:
        path: Path | None = None
        for ext in extensions:
            candidate = ddir / f"{stem}{ext}"
            if candidate.exists():
                path = candidate
                break
        if path is None:
            logger.error(f"Mesh not found for '{stem}' in {ddir}")
            return None
        try:
            meshes.append(load_mesh(path).copy())
        except Exception as e:
            logger.error(f"Failed to load {path}: {e}")
            return None
    return meshes


def _subsample_lines(mesh: pv.PolyData, stride: int) -> pv.PolyData:
    """Keep every *stride*-th line cell, returning a lighter PolyData of lines.

    The liver vessel trees are ~200k disjoint 2-point segments per tree; tubing
    them all yields tens of millions of points (browser-breaking). Slicing the
    line connectivity directly preserves PolyData (so .tube still works) and the
    radius array, unlike extract_cells which would return an UnstructuredGrid.
    """
    if stride <= 1 or mesh.n_lines == 0:
        return mesh
    lines = mesh.lines.reshape(-1, 3)[::stride]          # rows of [2, i0, i1]
    sub = pv.PolyData(mesh.points, lines=lines.ravel())
    if "radius" in mesh.point_data:
        sub.point_data["radius"] = mesh.point_data["radius"]
    return sub


def _render_labeled_parts(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    meshes: list[pv.DataSet],
    labels: list[str],
    colors: list[str],
    opacity: float,
    reset_camera: bool,
    n_tube_sides: int = 8,
    tubify: bool = True,
    tube_stride: int = 1,
) -> RenderResult:
    """Merge labeled parts into one actor and push to scene.

    Meshes with a 'radius' array are tubed when tubify=True; tube_stride > 1
    subsamples dense line meshes first to keep the geometry browser-safe.
    """
    global _active_actor
    total_cells = 0
    total_points = 0
    processed: list[pv.DataSet] = []
    for i, mesh in enumerate(meshes):
        if tubify and "radius" in mesh.point_data:
            if tube_stride > 1 and isinstance(mesh, pv.PolyData):
                mesh = _subsample_lines(mesh, tube_stride)
            # pv.tube() emits triangle *strips*. In trame local mode a strip's
            # connectivity is order-dependent, so a single stale index in a delta
            # unzips the whole strip into spikes across the viewport (only fixable
            # by F5). Triangulate to plain polys, which the vtk.js client syncs
            # reliably — same geometry, one isolated bad triangle at worst.
            mesh = mesh.tube(scalars="radius", absolute=True, n_sides=n_tube_sides).triangulate()
        mesh.cell_data["region_id"] = np.full(mesh.n_cells, i, dtype=np.int32)
        total_cells += mesh.n_cells
        total_points += mesh.n_points
        processed.append(mesh)
    meshes = processed
    n = len(meshes)

    merged = meshes[0]
    for m in meshes[1:]:
        merged = merged.merge(m)

    _active_actor = plotter.add_mesh(
        merged,
        scalars="region_id",
        cmap=colors,
        clim=[0, n - 1],
        n_colors=n,
        opacity=opacity,
        show_edges=False,
        show_scalar_bar=False,
        copy_mesh=True,
        interpolate_before_map=False,
        render=False,
    )
    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl, reset_camera=reset_camera)

    legend = [{"names": [label], "color": colors[i]} for i, label in enumerate(labels)]
    stats = {"n_cells": total_cells, "n_points": total_points}
    return RenderResult(legend_items=legend, mesh_stats=stats)


