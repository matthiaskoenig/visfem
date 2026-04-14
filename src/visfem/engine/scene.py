"""Scene management and mesh rendering helpers."""
from pathlib import Path
from typing import Any

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

# Ordered list of selectable scalar fields for the tibia simulation dataset.
# Each entry is {name, label} as consumed by the UI field selector.
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
    return {
        "field_label": _FIELD_LABELS.get(field, field.replace("_", " ")),
        "min_label": _fmt_value(clim[0]),
        "max_label": _fmt_value(clim[1]),
        "gradient": CONTINUOUS_CMAPS.get(cmap, "linear-gradient(to right, #222, #fff)"),
    }


# ---- Scene state ----

def clear_scene(plotter: pv.Plotter, dark_mode: bool) -> None:
    """Remove all actors and reset renderer state before each render.

    plotter.clear() resets the full renderer including LUT/colormap state,
    preventing stale color accumulation across dataset switches.
    """
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


def push_scene(plotter: pv.Plotter, ctrl: object, reset_camera: bool = True) -> None:
    """Flush VTK pipeline and push the complete scene to vtk.js.

    Pass reset_camera=False when navigating timesteps so the user's current
    view is preserved between steps.
    """
    plotter.render()
    if reset_camera:
        plotter.reset_camera()
        ctrl.view_push_camera()  # type: ignore[attr-defined]
    ctrl.view_update()  # type: ignore[attr-defined]


# ---- Renderers ----

def redraw_xdmf(
    plotter: pv.Plotter,
    ctrl: object,
    path: Path,
    xdmf_meta: dict[str, MeshMetadata],
    dark_mode: bool,
    opacity: float,
    field: str | None = None,
    step: int = 0,
    reset_camera: bool = True,
    cmap: str = "viridis",
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, Any] | None]:
    """Load and render one step of an XDMF mesh.

    If *field* is None the first scalar field from metadata is used.
    Pass reset_camera=False when navigating timesteps to preserve the
    user's current view.
    Returns (legend_items, mesh_stats, scalar_bar_info).
    """
    clear_scene(plotter, dark_mode)
    try:
        mesh = load_mesh(path, step=step)
    except Exception as e:
        logger.error(f"Failed to load '{path.name}' step {step}: {e}")
        return [], None, None

    mesh_meta = xdmf_meta.get(path.stem)
    if field is None:
        field = next(iter(mesh_meta.fields), None) if mesh_meta else None

    plotter.add_mesh(
        mesh,
        scalars=field,
        cmap=cmap,
        show_edges=False,
        copy_mesh=True,
        show_scalar_bar=False,
        opacity=opacity,
    )
    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl, reset_camera=reset_camera)
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}

    scalar_bar: dict | None = None
    if field:
        try:
            lo, hi = mesh.get_data_range(field)
            scalar_bar = _scalar_bar_dict(field, [float(lo), float(hi)], cmap)
        except Exception:
            pass

    return [], stats, scalar_bar


def redraw_ircadb(
    plotter: pv.Plotter,
    ctrl: object,
    patient_dir: Path,
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Load all organ meshes for a patient and render as one merged actor.

    Returns legend_items for the loaded organs.
    """
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
            mesh = load_mesh(vtk_path)
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
        merged = pv.merge(parts)
        plotter.add_mesh(
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
        )
        stats = {"n_cells": merged.n_cells, "n_points": merged.n_points}
    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl)
    legend = [
        {"names": [format_organ_name(organ)], "color": colors[i]}
        for i, organ in enumerate(loaded_organs)
    ]
    return legend, stats


def redraw_heart(
    plotter: pv.Plotter,
    ctrl: object,
    meta: ProjectMetadata,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, vtkActor | None]:
    """Render the heart mesh colored by material region.

    Returns (legend_items, mesh_stats, fiber_actor).  fiber_actor is the
    glyph overlay added hidden; call SetVisibility(True) to show it.
    """
    mesh_path = dataset_dir / "M.vtu"
    if not mesh_path.exists():
        logger.error(f"Heart mesh not found: {mesh_path}")
        return [], None, None

    label_map: dict[int, list[str]] = {}
    if meta.labels_file:
        labels_path = dataset_dir / meta.labels_file
        if labels_path.exists():
            label_map = parse_labels_file(labels_path).get("M.vtu", {})

    try:
        mesh = load_mesh(mesh_path)
    except Exception as e:
        logger.error(f"Failed to load heart mesh: {e}")
        return [], None, None

    material_ids = mesh.cell_data["Material"].astype(int)
    unique_ids: list[int] = sorted(int(v) for v in np.unique(material_ids))
    mesh.cell_data["region_id"] = np.array(
        [{mid: i for i, mid in enumerate(unique_ids)}[mid] for mid in material_ids],
        dtype=np.int32,
    )
    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]
    colors = region_colors(len(unique_ids), _palette)

    clear_scene(plotter, dark_mode)
    plotter.add_mesh(
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
    )

    # Build fiber glyph overlay — hidden by default, toggled via show_fibers state.
    fiber_actor: vtkActor | None = None
    if "Fiber" in mesh.cell_data.keys():
        subsample = 5
        cell_idx = np.arange(0, mesh.n_cells, subsample)
        centers = mesh.extract_cells(cell_idx).cell_centers()
        centers["Fiber"] = mesh.cell_data["Fiber"][cell_idx]
        glyphs = centers.glyph(orient="Fiber", scale=False, factor=1.5)
        fiber_actor = plotter.add_mesh(
            glyphs,
            color="#484848",
            show_scalar_bar=False,
            copy_mesh=True,
        )
        fiber_actor.SetVisibility(False)

    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl)
    legend = [
        {"names": label_map.get(mid, [f"Region {mid}"]), "color": colors[i]}
        for i, mid in enumerate(unique_ids)
    ]
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return legend, stats, fiber_actor


def redraw_heart_ep(
    plotter: pv.Plotter,
    ctrl: object,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Render the EP heart surface colored by EP material region."""
    ep_path = dataset_dir / "surfaces" / "ep_surface.vtp"
    if not ep_path.exists():
        logger.error(f"EP surface not found: {ep_path}")
        return [], None

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
        return [], None

    material_ids = mesh.cell_data["Material"].astype(int)
    unique_ids: list[int] = sorted(int(v) for v in np.unique(material_ids))
    mesh.cell_data["region_id"] = np.array(
        [{mid: i for i, mid in enumerate(unique_ids)}[mid] for mid in material_ids],
        dtype=np.int32,
    )
    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]
    colors = region_colors(len(unique_ids), _palette)

    clear_scene(plotter, dark_mode)
    plotter.add_mesh(
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
    )
    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl)

    legend = [
        {"names": [ep_label_map.get(mid, f"Region {mid}")], "color": colors[i]}
        for i, mid in enumerate(unique_ids)
    ]
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return legend, stats



def redraw_tibia_mesh(
    plotter: pv.Plotter,
    ctrl: object,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Render Tibia_Mesh.vtk colored by PartId region."""
    mesh_path = dataset_dir / "Tibia_Mesh.vtk"
    if not mesh_path.exists():
        logger.error(f"Tibia mesh not found: {mesh_path}")
        return [], None

    part_names: dict[int, str] = {
        1: "Bone",
        2: "Fracture / Callus",
        3: "Implant screws",
    }

    try:
        mesh = load_mesh(mesh_path)
    except Exception as e:
        logger.error(f"Failed to load tibia mesh: {e}")
        return [], None

    part_ids = mesh.cell_data["PartId"].astype(int)
    unique_ids: list[int] = sorted(int(v) for v in np.unique(part_ids))
    mesh.cell_data["region_id"] = np.array(
        [{pid: i for i, pid in enumerate(unique_ids)}[pid] for pid in part_ids],
        dtype=np.int32,
    )
    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]
    colors = region_colors(len(unique_ids), _palette)

    clear_scene(plotter, dark_mode)
    plotter.add_mesh(
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
    )
    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl)

    legend = [
        {"names": [part_names.get(pid, f"Part {pid}")], "color": colors[i]}
        for i, pid in enumerate(unique_ids)
    ]
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return legend, stats


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
    ctrl: object,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
    field: str = "vonMises_stress",
    palette: list[str] | None = None,
    cmap: str = "turbo",
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, Any] | None]:
    """Render Tibia_Simulation.vtk with the given scalar field.

    Claes_window is rendered as a discrete categorical colormap with a legend.
    All other fields use a continuous turbo colormap with a scalar bar.
    Returns (legend_items, mesh_stats, scalar_bar_info).
    """
    sim_path = dataset_dir / "Tibia_Simulation.vtk"
    if not sim_path.exists():
        logger.error(f"Tibia simulation not found: {sim_path}")
        return [], None, None

    try:
        mesh = load_mesh(sim_path)
    except Exception as e:
        logger.error(f"Failed to load tibia simulation: {e}")
        return [], None, None

    clear_scene(plotter, dark_mode)
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}

    if field == "Claes_window":
        # Categorical: map integer zone values to a discrete colormap with a legend.
        _palette = palette if palette is not None else CATEGORICAL_PALETTES["clinical"]
        zones = mesh.cell_data["Claes_window"].astype(int)
        zone_ids: list[int] = sorted(int(z) for z in np.unique(zones))
        zone_map = {z: i for i, z in enumerate(zone_ids)}
        mesh.cell_data["_zone_id"] = np.array(
            [zone_map[int(z)] for z in zones], dtype=np.int32
        )
        colors = region_colors(len(zone_ids), _palette)
        n = len(zone_ids)
        plotter.add_mesh(
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
        )
        apply_opacity(plotter, opacity)
        push_scene(plotter, ctrl)
        legend = [
            {"names": [_CLAES_LABELS.get(z, f"Zone {z}")], "color": colors[i]}
            for i, z in enumerate(zone_ids)
        ]
        return legend, stats, None
    else:
        # Continuous: clamp colormap to 95th percentile to avoid outlier washout.
        data = mesh.cell_data[field]
        clim = [float(data.min()), float(np.percentile(data, 95))]
        plotter.add_mesh(
            mesh,
            scalars=field,
            cmap=cmap,
            clim=clim,
            opacity=opacity,
            show_edges=False,
            show_scalar_bar=False,
            copy_mesh=True,
        )
        apply_opacity(plotter, opacity)
        push_scene(plotter, ctrl)
        scalar_bar = _scalar_bar_dict(field, clim, cmap)
        return [], stats, scalar_bar