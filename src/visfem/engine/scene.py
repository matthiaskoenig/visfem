"""Scene management and mesh rendering helpers."""
from pathlib import Path

import numpy as np
import pyvista as pv
from vtkmodules.vtkRenderingCore import vtkActor

from visfem.engine.colors import (
    BG_DARK_BOTTOM, BG_DARK_TOP, BG_LIGHT_BOTTOM, BG_LIGHT_TOP,
    COLORS_PAIRED, region_colors,
)
from visfem.engine.discovery import ircadb_organ_names, format_organ_name
from visfem.log import get_logger
from visfem.mesh import load_mesh, parse_labels_file
from visfem.models import MeshMetadata, ProjectMetadata

logger = get_logger(__name__)


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


def push_scene(plotter: pv.Plotter, ctrl: object) -> None:
    """Flush VTK pipeline and push the complete scene to vtk.js."""
    plotter.render()
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
) -> tuple[list[dict[str, str]], dict[str, int] | None]:
    """Load and render the first step of an XDMF mesh.

    Returns legend_items (empty for XDMF datasets).
    """
    clear_scene(plotter, dark_mode)
    try:
        mesh = load_mesh(path, step=0)
    except Exception as e:
        logger.error(f"Failed to load '{path.name}': {e}")
        return [], None

    mesh_meta = xdmf_meta.get(path.stem)
    field = next(iter(mesh_meta.fields), None) if mesh_meta else None

    plotter.add_mesh(
        mesh,
        scalars=field,
        show_edges=True,
        edge_color="#000000",
        copy_mesh=True,
        show_scalar_bar=False,
        opacity=opacity,
    )
    apply_opacity(plotter, opacity)
    push_scene(plotter, ctrl)
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return [], stats


def redraw_ircadb(
    plotter: pv.Plotter,
    ctrl: object,
    patient_dir: Path,
    dark_mode: bool,
    opacity: float,
) -> tuple[list[dict[str, str]], dict[str, int] | None]:
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
    colors = region_colors(n, COLORS_PAIRED)
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
        {"name": format_organ_name(organ), "color": colors[i]}
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
) -> tuple[list[dict[str, str]], dict[str, int] | None]:
    """Render the heart mesh colored by material region.

    Returns legend_items for the material regions.
    """
    mesh_path = dataset_dir / "M.vtu"
    if not mesh_path.exists():
        logger.error(f"Heart mesh not found: {mesh_path}")
        return [], None

    label_map: dict[int, str] = {}
    if meta.labels_file:
        labels_path = dataset_dir / meta.labels_file
        if labels_path.exists():
            label_map = parse_labels_file(labels_path).get("M.vtu", {})

    try:
        mesh = load_mesh(mesh_path)
    except Exception as e:
        logger.error(f"Failed to load heart mesh: {e}")
        return [], None

    material_ids = mesh.cell_data["Material"].astype(int)
    unique_ids: list[int] = sorted(int(v) for v in np.unique(material_ids))
    mesh.cell_data["region_id"] = np.array(
        [{mid: i for i, mid in enumerate(unique_ids)}[mid] for mid in material_ids],
        dtype=np.int32,
    )
    colors = region_colors(len(unique_ids), COLORS_PAIRED)

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
        {"name": label_map.get(mid, f"Region {mid}"), "color": colors[i]}
        for i, mid in enumerate(unique_ids)
    ]
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return legend, stats


def redraw_heart_ep(
    plotter: pv.Plotter,
    ctrl: object,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
) -> tuple[list[dict[str, str]], dict[str, int] | None]:
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
    colors = region_colors(len(unique_ids), COLORS_PAIRED)

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
        {"name": ep_label_map.get(mid, f"Region {mid}"), "color": colors[i]}
        for i, mid in enumerate(unique_ids)
    ]
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return legend, stats