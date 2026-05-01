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
from visfem.models import MeshMetadata, ProjectMetadata

logger = get_logger(__name__)


@dataclass
class RenderResult:
    legend_items: list[dict[str, Any]] = field(default_factory=list)
    mesh_stats: dict[str, Any] | None = None
    scalar_bar_info: dict[str, Any] | None = None
    fiber_actor: vtkActor | None = None


_FIBER_SUBSAMPLE: int = 5
_GLYPH_SCALE: float = 1.5
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

# Ordered list of selectable scalar fields for the tibia simulation dataset
TIBIA_SIM_FIELDS: list[dict[str, str]] = [
    {"name": "vonMises_stress",           "label": _FIELD_LABELS["vonMises_stress"]},
    {"name": "vonMises_equivalent_strain","label": _FIELD_LABELS["vonMises_equivalent_strain"]},
    {"name": "octahedral_shear_strain",   "label": _FIELD_LABELS["octahedral_shear_strain"]},
    {"name": "hydrostatic_strain",        "label": _FIELD_LABELS["hydrostatic_strain"]},
    {"name": "volumetric_strain",         "label": _FIELD_LABELS["volumetric_strain"]},
    {"name": "Claes_window",              "label": _FIELD_LABELS["Claes_window"]},
]


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

def clear_scene(plotter: pv.Plotter, dark_mode: bool) -> None:
    """Remove all actors and reset renderer state before each render."""
    global _active_actor, _xdmf_mesh, _xdmf_actor
    _active_actor = None
    _xdmf_mesh = None
    _xdmf_actor = None
    plotter.clear()
    if dark_mode:
        plotter.set_background(BG_DARK_BOTTOM, top=BG_DARK_TOP)
    else:
        plotter.set_background(BG_LIGHT_BOTTOM, top=BG_LIGHT_TOP)


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
    """Swap the categorical LUT on the active actor — no scene rebuild needed.

    Does nothing if no actor is currently tracked (falls back gracefully).
    Callers are responsible for updating state.legend_items colors.
    """
    if _active_actor is None:
        return
    mapper = _active_actor.GetMapper()
    mapper.SetLookupTable(_build_categorical_lut(colors, n))
    mapper.SetScalarRange(0, max(n - 1, 1))
    mapper.Modified()
    plotter.render()
    ctrl.view_update()


def update_tibia_sim_field(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    ddir: Path,
    field: str,
    palette: list[str],
    cmap: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Fast-path field/color update for tibia_simulation."""
    if _active_actor is None:
        return [], None

    mapper = _active_actor.GetMapper()
    mesh = load_mesh(ddir / "Tibia_Simulation.vtk")  # instant from cache

    if field == "Claes_window":
        zones = mesh.cell_data["Claes_window"].astype(int)
        zone_ids: list[int] = sorted(int(z) for z in np.unique(zones))
        n = len(zone_ids)
        colors = region_colors(n, palette)
        mapper.SelectColorArray("_zone_id")
        mapper.SetScalarModeToUseCellFieldData()
        mapper.SetInterpolateScalarsBeforeMapping(False)
        mapper.SetLookupTable(_build_categorical_lut(colors, n))
        mapper.SetScalarRange(0, max(n - 1, 1))
        mapper.Modified()
        plotter.render()
        ctrl.view_update()
        legend = [
            {"names": [_CLAES_LABELS.get(z, f"Zone {z}")], "color": colors[i]}
            for i, z in enumerate(zone_ids)
        ]
        return legend, None
    else:
        data = mesh.cell_data[field]
        clim = [float(data.min()), float(np.percentile(data, _PERCENTILE_CLAMP))]
        mapper.SelectColorArray(field)
        mapper.SetScalarModeToUseCellFieldData()
        mapper.SetInterpolateScalarsBeforeMapping(True)
        mapper.SetLookupTable(_build_continuous_lut(cmap, clim[0], clim[1]))
        mapper.SetScalarRange(*clim)
        mapper.Modified()
        plotter.render()
        ctrl.view_update()
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
    plotter.render()
    ctrl.view_update()
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
) -> RenderResult:
    """Load and render one step of an XDMF mesh."""
    global _xdmf_mesh, _xdmf_actor
    clear_scene(plotter, dark_mode)
    try:
        mesh = load_mesh(path, step=step)
    except Exception as e:
        logger.error(f"Failed to load '{path.name}' step {step}: {e}")
        return RenderResult()

    _xdmf_mesh = mesh
    mesh_meta = xdmf_meta.get(path.stem)
    if field is None:
        field = next(iter(mesh_meta.fields), None) if mesh_meta else None

    # Use precomputed global bounds so the colormap scale is stable across all timesteps
    # Fall back to the current step's range if bounds were not cached yet
    clim: list[float] | None = None
    if field and mesh_meta and field in mesh_meta.scalar_bounds:
        clim = mesh_meta.scalar_bounds[field]

    _xdmf_actor = plotter.add_mesh(
        mesh,
        scalars=field,
        cmap=cmap,
        clim=clim,
        show_edges=False,
        copy_mesh=False,
        show_scalar_bar=False,
        opacity=opacity,
        render=False,
    )
    push_scene(plotter, ctrl, reset_camera=reset_camera)
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}

    scalar_bar: dict | None = None
    if field:
        if clim is None:
            try:
                lo, hi = mesh.get_data_range(field)
                clim = [float(lo), float(hi)]
            except Exception:
                pass
        if clim is not None:
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
        _xdmf_mesh[name] = new_mesh[name]
    _xdmf_mesh.points = new_mesh.points

    _xdmf_actor.GetMapper().Modified()
    plotter.render()
    ctrl.view_update()

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


def redraw_heart(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    meta: ProjectMetadata,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None = None,
    reset_camera: bool = True,
) -> RenderResult:
    """Render the heart mesh colored by material region."""
    mesh_path = dataset_dir / "M.vtu"
    if not mesh_path.exists():
        logger.error(f"Heart mesh not found: {mesh_path}")
        return RenderResult()

    label_map: dict[int, list[str]] = {}
    if meta.labels_file:
        labels_path = dataset_dir / meta.labels_file
        if labels_path.exists():
            label_map = parse_labels_file(labels_path).get("M.vtu", {})

    try:
        mesh = load_mesh(mesh_path)
    except Exception as e:
        logger.error(f"Failed to load heart mesh: {e}")
        return RenderResult()

    material_ids = mesh.cell_data["Material"].astype(int)
    unique_ids: list[int] = sorted(int(v) for v in np.unique(material_ids))
    mesh.cell_data["region_id"] = np.array(
        [{mid: i for i, mid in enumerate(unique_ids)}[mid] for mid in material_ids],
        dtype=np.int32,
    )
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

    # Build fiber glyph overlay; hidden by default, toggled via show_fibers state.
    fiber_actor: vtkActor | None = None
    if "Fiber" in mesh.cell_data.keys():
        cell_idx = np.arange(0, mesh.n_cells, _FIBER_SUBSAMPLE)
        centers = mesh.extract_cells(cell_idx).cell_centers()
        centers["Fiber"] = mesh.cell_data["Fiber"][cell_idx]
        glyphs = centers.glyph(orient="Fiber", scale=False, factor=_GLYPH_SCALE)
        fiber_actor = plotter.add_mesh(
            glyphs,
            color="black",
            show_scalar_bar=False,
            copy_mesh=True,
            render=False,
        )
        fiber_actor.SetVisibility(False)

    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl, reset_camera=reset_camera)
    legend = [
        {"names": label_map.get(mid, [f"Region {mid}"]), "color": colors[i]}
        for i, mid in enumerate(unique_ids)
    ]
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return RenderResult(legend_items=legend, mesh_stats=stats, fiber_actor=fiber_actor)


def redraw_heart_ep(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None = None,
    reset_camera: bool = True,
) -> RenderResult:
    """Render the EP heart surface colored by EP material region."""
    ep_path = dataset_dir / "surfaces" / "ep_surface.vtp"
    if not ep_path.exists():
        logger.error(f"EP surface not found: {ep_path}")
        return RenderResult()

    # EP MaterialID -> name
    ep_label_map: dict[int, str] = {
        1:  "Ventricle endocardium",
        2:  "Ventricle myocardium",
        3:  "Ventricle epicardium",
        32: "Right atrial bulk tissue",
        33: "Left atrial bulk tissue",
        72: "Crista terminalis",
        73: "Sinus node",
        74: "Pectinate muscles",
        75: "Bachmann bundle",
        76: "Middle posterior bridge",
        77: "Lower posterior bridge",
        78: "Coronary sinus bridge",
        79: "L/R atrial appendage",
        80: "Inferior isthmus",
    }

    try:
        mesh = load_mesh(ep_path)
    except Exception as e:
        logger.error(f"Failed to load EP surface: {e}")
        return RenderResult()

    material_ids = mesh.cell_data["Material"].astype(int)
    unique_ids: list[int] = sorted(int(v) for v in np.unique(material_ids))
    mesh.cell_data["region_id"] = np.array(
        [{mid: i for i, mid in enumerate(unique_ids)}[mid] for mid in material_ids],
        dtype=np.int32,
    )
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
    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl, reset_camera=reset_camera)

    legend = [
        {"names": [ep_label_map.get(mid, f"Region {mid}")], "color": colors[i]}
        for i, mid in enumerate(unique_ids)
    ]
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return RenderResult(legend_items=legend, mesh_stats=stats)



def redraw_tibia_mesh(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None = None,
    reset_camera: bool = True,
) -> RenderResult:
    """Render Tibia_Mesh.vtk colored by PartId region."""
    mesh_path = dataset_dir / "Tibia_Mesh.vtk"
    if not mesh_path.exists():
        logger.error(f"Tibia mesh not found: {mesh_path}")
        return RenderResult()

    part_names: dict[int, str] = {
        1: "Bone",
        2: "Fracture / Callus",
        3: "Implant screws",
    }

    try:
        mesh = load_mesh(mesh_path)
    except Exception as e:
        logger.error(f"Failed to load tibia mesh: {e}")
        return RenderResult()

    part_ids = mesh.cell_data["PartId"].astype(int)
    unique_ids: list[int] = sorted(int(v) for v in np.unique(part_ids))
    mesh.cell_data["region_id"] = np.array(
        [{pid: i for i, pid in enumerate(unique_ids)}[pid] for pid in part_ids],
        dtype=np.int32,
    )
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
    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl, reset_camera=reset_camera)

    legend = [
        {"names": [part_names.get(pid, f"Part {pid}")], "color": colors[i]}
        for i, pid in enumerate(unique_ids)
    ]
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return RenderResult(legend_items=legend, mesh_stats=stats)


def redraw_aneurysm(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None = None,
    reset_camera: bool = True,
) -> RenderResult:
    """Render Aneurysm_small_Full geometry as a single surface mesh."""
    mesh_path = dataset_dir / "Aneurysm_small_Full.stl"
    if not mesh_path.exists():
        mesh_path = dataset_dir / "Aneurysm_small_Full.obj"
    if not mesh_path.exists():
        logger.error(f"Aneurysm mesh not found in {dataset_dir}")
        return RenderResult()

    try:
        mesh = load_mesh(mesh_path)
    except Exception as e:
        logger.error(f"Failed to load aneurysm mesh: {e}")
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


_COIL_PARTS: list[tuple[str, str]] = [
    ("FramingCoil", "Framing Coil"),
    ("FillingCoil",  "Filling Coil"),
]


def redraw_aneurysm_coils(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None = None,
    reset_camera: bool = True,
) -> RenderResult:
    """Render FramingCoil and FillingCoil as two categorically colored parts."""
    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]
    colors = region_colors(len(_COIL_PARTS), _palette)

    parts: list[pv.DataSet] = []
    for i, (stem, _) in enumerate(_COIL_PARTS):
        path = dataset_dir / f"{stem}.stl"
        if not path.exists():
            path = dataset_dir / f"{stem}.obj"
        if not path.exists():
            logger.error(f"Coil mesh not found: {path}")
            return RenderResult()
        try:
            part = load_mesh(path).copy()
        except Exception as e:
            logger.error(f"Failed to load coil mesh {path}: {e}")
            return RenderResult()
        part.cell_data["region_id"] = np.full(part.n_cells, i, dtype=np.int32)
        parts.append(part)

    mesh = parts[0].merge(parts[1])
    total_cells = sum(p.n_cells for p in parts)
    total_points = sum(p.n_points for p in parts)

    global _active_actor
    clear_scene(plotter, dark_mode)
    _active_actor = plotter.add_mesh(
        mesh,
        scalars="region_id",
        cmap=colors,
        clim=[0, len(_COIL_PARTS) - 1],
        n_colors=len(_COIL_PARTS),
        opacity=opacity,
        show_edges=False,
        show_scalar_bar=False,
        copy_mesh=True,
        interpolate_before_map=False,
        render=False,
    )
    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl, reset_camera=reset_camera)

    legend = [
        {"names": [label], "color": colors[i]}
        for i, (_, label) in enumerate(_COIL_PARTS)
    ]
    stats = {"n_cells": total_cells, "n_points": total_points}
    return RenderResult(legend_items=legend, mesh_stats=stats)


# Claes healing window zone labels
_CLAES_LABELS: dict[int, str] = {
    1: "Too much movement",
    2: "Transition (excess)",
    3: "Perfect healing window",
    4: "Transition (lazy)",
    5: "Bone resorption",
}


def redraw_tibia_simulation(
    plotter: pv.Plotter,
    ctrl: TrameCtrl,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
    field: str = "vonMises_stress",
    palette: list[str] | None = None,
    cmap: str = "turbo",
    reset_camera: bool = True,
) -> RenderResult:
    """Render Tibia_Simulation.vtk with the given scalar field."""
    sim_path = dataset_dir / "Tibia_Simulation.vtk"
    if not sim_path.exists():
        logger.error(f"Tibia simulation not found: {sim_path}")
        return RenderResult()

    try:
        mesh = load_mesh(sim_path)
    except Exception as e:
        logger.error(f"Failed to load tibia simulation: {e}")
        return RenderResult()

    # Always compute _zone_id so the actor's frozen dataset has it regardless of
    # the initially rendered field — enables fast-path switching to Claes_window later.
    _palette = palette if palette is not None else CATEGORICAL_PALETTES["clinical"]
    zones = mesh.cell_data["Claes_window"].astype(int)
    zone_ids: list[int] = sorted(int(z) for z in np.unique(zones))
    zone_map = {z: i for i, z in enumerate(zone_ids)}
    mesh.cell_data["_zone_id"] = np.array(
        [zone_map[int(z)] for z in zones], dtype=np.int32
    )

    global _active_actor
    clear_scene(plotter, dark_mode)
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}

    if field == "Claes_window":
        colors = region_colors(len(zone_ids), _palette)
        n = len(zone_ids)
        _active_actor = plotter.add_mesh(
            mesh,
            scalars="_zone_id",
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
        apply_opacity(plotter, opacity)
        push_scene(plotter, ctrl, reset_camera=reset_camera)
        legend = [
            {"names": [_CLAES_LABELS.get(z, f"Zone {z}")], "color": colors[i]}
            for i, z in enumerate(zone_ids)
        ]
        return RenderResult(legend_items=legend, mesh_stats=stats)
    else:
        # Continuous: clamp to nth percentile to avoid outlier washout.
        data = mesh.cell_data[field]
        clim = [float(data.min()), float(np.percentile(data, _PERCENTILE_CLAMP))]
        _active_actor = plotter.add_mesh(
            mesh,
            scalars=field,
            cmap=cmap,
            clim=clim,
            opacity=opacity,
            show_edges=False,
            show_scalar_bar=False,
            copy_mesh=True,
            render=False,
        )
        apply_opacity(plotter, opacity)
        push_scene(plotter, ctrl, reset_camera=reset_camera)
        scalar_bar = _scalar_bar_dict(field, clim, cmap)
        return RenderResult(mesh_stats=stats, scalar_bar_info=scalar_bar)