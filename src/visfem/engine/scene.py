"""Scene management and mesh rendering helpers."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

import numpy as np
import pyvista as pv
from vtkmodules.vtkRenderingCore import vtkActor

from visfem.engine.colors import (
    BG_DARK_BOTTOM,
    BG_DARK_TOP,
    BG_LIGHT_BOTTOM,
    BG_LIGHT_TOP,
    region_colors,
)
from visfem.engine.discovery import format_organ_name, ircadb_organ_names
from visfem.engine.palettes import CATEGORICAL_PALETTES, CONTINUOUS_CMAPS
from visfem.log import get_logger
from visfem.mesh import (
    as_surface,
    load_mesh,
    load_skin,
    parse_labels_file,
    skin_with_ids,
)
from visfem.models import FiberOptions, MeshMetadata, ProjectMetadata

if TYPE_CHECKING:
    from pyvista.plotting._typing import ColormapOptions

logger = get_logger(__name__)


@dataclass
class RenderResult:
    """Result of one render pass."""

    legend_items: list[dict[str, Any]] = field(default_factory=list)
    mesh_stats: dict[str, Any] | None = None
    scalar_bar_info: dict[str, Any] | None = None
    fiber_actor: vtkActor | None = None


@dataclass
class Scene:
    """One plotter and the actors its in-place updates act on."""

    plotter: pv.Plotter
    active_actor: vtkActor | None = None  # main mesh actor of the current dataset
    xdmf_mesh: pv.DataSet | None = None  # full frame of the live time series
    xdmf_actor: vtkActor | None = None
    # Skin shown by xdmf_actor and its volume point/cell ids (None for a surface frame).
    xdmf_surface: pv.PolyData | None = None
    xdmf_point_ids: np.ndarray | None = None
    xdmf_cell_ids: np.ndarray | None = None

    def forget_actors(self) -> None:
        """Drop every tracked actor and mesh."""
        self.active_actor = None
        self.xdmf_mesh = None
        self.xdmf_actor = None
        self.xdmf_surface = None
        self.xdmf_point_ids = None
        self.xdmf_cell_ids = None


_PERCENTILE_CLAMP: int = 95  # upper colour limit percentile for continuous fields


_MAG_SUFFIX = "__mag"


def _set_magnitude(mesh: pv.DataSet, field: str) -> str:
    """Store |*field*| as a scalar array on the vector's association and return its name."""
    name = f"{field}{_MAG_SUFFIX}"
    data = mesh.point_data if field in mesh.point_data else mesh.cell_data
    data[name] = np.linalg.norm(data[field], axis=1)
    return name


def _refresh_magnitudes(mesh: pv.DataSet) -> None:
    """Recompute every ``<field>__mag`` array on *mesh* from its vector array."""
    for name in list(mesh.array_names):
        if name.endswith(_MAG_SUFFIX):
            field = name[: -len(_MAG_SUFFIX)]
            if field in mesh.array_names:
                _set_magnitude(mesh, field)


class TrameCtrl(Protocol):
    """Trame controller hooks the scene pushes through."""

    def view_push_camera(self) -> None:
        """Push the server camera to the client."""
        ...

    def view_update(self) -> None:
        """Send a delta view update to the client."""
        ...

    def view_push_scene(self) -> None:
        """Send the full scene state to the client."""
        ...


# Display labels for known field names
_FIELD_LABELS: dict[str, str] = {
    "vonMises_stress": "von Mises stress",
    "vonMises_equivalent_strain": "von Mises eq. strain",
    "octahedral_shear_strain": "octahedral shear strain",
    "hydrostatic_strain": "hydrostatic strain",
    "volumetric_strain": "volumetric strain",
    "Claes_window": "healing window (Claes)",
    "pressure": "pressure",
    "strain": "strain",
    "Potential": "transmembrane potential (mV)",
    "Calcium": "intracellular calcium [Ca\u00b2\u207a]",
    "ActiveStress": "active stress (Pa)",
}


def field_label(name: str) -> str:
    """Return the display label for the scalar field *name*."""
    return _FIELD_LABELS.get(name, name.replace("_", " "))


def _fmt_value(v: float) -> str:
    """Format the scalar bar value *v* compactly."""
    a = abs(v)
    if a == 0.0:
        return "0"
    if a >= 1000:
        return f"{v:.0f}"
    if a >= 100:
        return f"{v:.1f}"
    if a >= 1:
        return f"{v:.2f}"
    if a >= 0.01:
        return f"{v:.3f}"
    return f"{v:.2e}"


def _scalar_bar_dict(field: str, clim: list[float], cmap: str) -> dict:
    """Build the scalar_bar state dict for *field* with limits *clim* and colormap *cmap*."""
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


def _set_background(scene: Scene, dark_mode: bool) -> None:
    """Set the gradient background of *scene* for *dark_mode*."""
    if dark_mode:
        scene.plotter.renderers.set_background(BG_DARK_BOTTOM, top=BG_DARK_TOP)
    else:
        scene.plotter.renderers.set_background(BG_LIGHT_BOTTOM, top=BG_LIGHT_TOP)


def clear_scene(scene: Scene, dark_mode: bool) -> None:
    """Remove every actor from *scene*, drop its tracked actors and set the background for *dark_mode*."""
    scene.forget_actors()
    # Removing an actor makes the local-mode client drop its geometry.
    for actor in list(scene.plotter.renderer.actors.values()):
        scene.plotter.renderer.RemoveActor(actor)
    _set_background(scene, dark_mode)


def apply_opacity(scene: Scene, opacity: float) -> None:
    """Set *opacity* on every vtkActor in the renderer."""
    for actor in scene.plotter.renderer.actors.values():
        if isinstance(actor, vtkActor):
            actor.GetProperty().SetOpacity(opacity)


def push_scene(scene: Scene, ctrl: TrameCtrl, reset_camera: bool = True) -> None:
    """Render *scene*, reset the camera when *reset_camera* and push the scene to the client."""
    # Each renderer and in-place update calls this once, at its end.
    scene.plotter.render()
    if reset_camera:
        scene.plotter.renderer.reset_camera()
        ctrl.view_push_camera()
    # Full push (ui.layout._make_push_scene): after a dataset switch a local-mode delta can hit a stale content-hash.
    push = getattr(ctrl, "view_push_scene", None)
    if push is not None:
        push()
    else:
        ctrl.view_update()  # delta update when no full push is bound (headless tests)


# Mapper fast-path helpers


def _build_categorical_lut(colors: list[str], n: int) -> pv.LookupTable:
    """Build a discrete LUT from the first *n* of *colors*."""
    lut = pv.LookupTable(cmap=colors[:n], n_values=n)
    lut.scalar_range = (0, max(n - 1, 1))
    return lut


def _build_continuous_lut(cmap: str, lo: float, hi: float) -> pv.LookupTable:
    """Build a continuous LUT from the named colormap *cmap* over *lo* to *hi*."""
    lut = pv.LookupTable(cmap=cmap, n_values=256)
    lut.scalar_range = (lo, hi)
    return lut


def update_actor_palette(
    scene: Scene, ctrl: TrameCtrl, colors: list[str], n: int
) -> None:
    """Swap the active actor's categorical LUT to the first *n* of *colors* in place and push the scene."""
    if scene.active_actor is None:
        return
    mapper = scene.active_actor.GetMapper()
    mapper.SetLookupTable(_build_categorical_lut(colors, n))
    mapper.SetScalarRange(0, max(n - 1, 1))
    mapper.Modified()
    push_scene(scene, ctrl, reset_camera=False)


def update_scalar_field_view(
    scene: Scene,
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
    """Switch the active actor's mapper to *field* in place and return (legend, scalar bar)."""
    if scene.active_actor is None:
        return [], None

    mapper = scene.active_actor.GetMapper()
    mesh = load_mesh(ddir / mesh_file)  # served from the load_mesh cache

    if field in categorical_fields:
        zones = mesh.cell_data[field].astype(int)
        zone_ids: list[int] = sorted(int(z) for z in np.unique(zones))
        n = len(zone_ids)
        colors = region_colors(n, palette)
        # _zone_id is the dense zone index redraw_scalar_field freezes on the skin.
        mapper.SelectColorArray("_zone_id")
        mapper.SetScalarModeToUseCellFieldData()
        mapper.SetInterpolateScalarsBeforeMapping(False)
        mapper.SetLookupTable(_build_categorical_lut(colors, n))
        mapper.SetScalarRange(0, max(n - 1, 1))
        mapper.Modified()
        push_scene(scene, ctrl, reset_camera=False)
        legend = [
            {"names": zone_labels.get(z, [f"Zone {z}"]), "color": colors[i]}
            for i, z in enumerate(zone_ids)
        ]
        return legend, None

    data = mesh.cell_data[field]
    # The upper limit at the percentile keeps outliers from washing out the ramp.
    clim = [float(data.min()), float(np.percentile(data, percentile))]
    mapper.SelectColorArray(field)
    mapper.SetScalarModeToUseCellFieldData()
    mapper.SetInterpolateScalarsBeforeMapping(True)
    mapper.SetLookupTable(_build_continuous_lut(cmap, clim[0], clim[1]))
    mapper.SetScalarRange(*clim)
    mapper.Modified()
    push_scene(scene, ctrl, reset_camera=False)
    return [], _scalar_bar_dict(field, clim, cmap)


def update_scalar_range(
    scene: Scene,
    ctrl: TrameCtrl,
    field: str,
    clim: list[float],
    cmap: str,
) -> "dict | None":
    """Set the active actor's scalar range to *clim* in place and return the scalar bar dict."""
    actor = scene.xdmf_actor if scene.xdmf_actor is not None else scene.active_actor
    if actor is None:
        return None
    mapper = actor.GetMapper()
    lut = mapper.GetLookupTable()
    if lut is not None:
        lut.SetTableRange(clim[0], clim[1])
    mapper.SetScalarRange(clim[0], clim[1])
    mapper.Modified()
    push_scene(scene, ctrl, reset_camera=False)
    return _scalar_bar_dict(field, clim, cmap)


# Renderers


def redraw_xdmf(
    scene: Scene,
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
    """Render step *step* of the time series at *path* and return the RenderResult."""
    clear_scene(scene, dark_mode)
    mesh = load_mesh(path, step=step)

    scene.xdmf_mesh = mesh
    # A flat-series file passes mesh_meta; an XDMF/PVD manifest is keyed by stem.
    if mesh_meta is None:
        mesh_meta = xdmf_meta.get(path.stem)
    if field is None:
        field = next(iter(mesh_meta.fields), None) if mesh_meta else None

    # Vector fields colour by magnitude, stored as a scalar on the detached frame.
    colour_by = field
    is_vector = (
        bool(field)
        and field in mesh.array_names
        and getattr(mesh[field], "ndim", 1) == 2
        and mesh[field].shape[1] == 3
    )
    if is_vector:
        assert field is not None  # narrows field for mypy
        colour_by = _set_magnitude(mesh, field)

    # Global bounds, keyed by field name for scalars and magnitudes alike, keep the colour scale stable across timesteps.
    clim: list[float] | None = None
    if field and mesh_meta and field in mesh_meta.scalar_bounds:
        clim = mesh_meta.scalar_bounds[field]

    # The actor shows the skin; xdmf_mesh keeps the full frame that update_xdmf_step size-checks each next frame against.
    scene.xdmf_surface, scene.xdmf_point_ids, scene.xdmf_cell_ids = skin_with_ids(mesh)
    scene.xdmf_actor = scene.plotter.add_mesh(
        scene.xdmf_surface,
        scalars=colour_by,
        # cmap is a colormap name; PyVista types it as a Literal of known names.
        cmap=cast("ColormapOptions", cmap),
        clim=clim,
        show_edges=False,
        copy_mesh=False,
        show_scalar_bar=False,
        opacity=opacity,
        render=False,
    )
    push_scene(scene, ctrl, reset_camera=reset_camera)
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}

    scalar_bar: dict | None = None
    if field:
        if clim is None:  # current step's range when no bounds are cached
            try:
                lo, hi = mesh.get_data_range(colour_by)
                clim = [float(lo), float(hi)]
            except (KeyError, ValueError):  # array absent in this frame: bar hidden
                pass
        if clim is not None:
            # The bar label is the plain field name; the vector selector conveys the magnitude.
            scalar_bar = _scalar_bar_dict(field, clim, cmap)

    return RenderResult(mesh_stats=stats, scalar_bar_info=scalar_bar)


def update_xdmf_step(
    scene: Scene,
    ctrl: TrameCtrl,
    path: Path,
    xdmf_meta: dict[str, MeshMetadata],
    step: int,
    field: str | None,
    cmap: str,
) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None]:
    """Copy step *step* onto the live frame and its skin in place and return (updated, stats, scalar bar)."""
    if scene.xdmf_mesh is None or scene.xdmf_actor is None:
        return False, None, None

    new_mesh = load_mesh(path, step=step)

    if (
        new_mesh.n_points != scene.xdmf_mesh.n_points
        or new_mesh.n_cells != scene.xdmf_mesh.n_cells
    ):
        return False, None, None

    for name in new_mesh.array_names:
        scene.xdmf_mesh[name] = np.array(new_mesh[name], copy=True)
    scene.xdmf_mesh.points = np.array(new_mesh.points, copy=True)
    # The copied arrays are raw; the mapper colours vector fields by the derived magnitude.
    _refresh_magnitudes(scene.xdmf_mesh)
    scene.xdmf_mesh.Modified()

    # Map the frame onto the shown skin; a surface frame is its own skin with ids None.
    if (
        scene.xdmf_surface is not None
        and scene.xdmf_point_ids is not None
        and scene.xdmf_cell_ids is not None
    ):
        for name in new_mesh.point_data:
            scene.xdmf_surface.point_data[name] = np.asarray(new_mesh.point_data[name])[
                scene.xdmf_point_ids
            ]
        for name in new_mesh.cell_data:
            scene.xdmf_surface.cell_data[name] = np.asarray(new_mesh.cell_data[name])[
                scene.xdmf_cell_ids
            ]
        scene.xdmf_surface.points = np.asarray(new_mesh.points)[scene.xdmf_point_ids]
        _refresh_magnitudes(scene.xdmf_surface)
        scene.xdmf_surface.Modified()
    scene.xdmf_actor.GetMapper().Modified()
    push_scene(scene, ctrl, reset_camera=False)

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
            except (KeyError, ValueError):  # array absent in this frame: bar hidden
                pass
        if clim is not None:
            scalar_bar = _scalar_bar_dict(field, clim, cmap)

    return True, stats, scalar_bar


def redraw_ircadb(
    scene: Scene,
    ctrl: TrameCtrl,
    patient_dir: Path,
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None = None,
    reset_camera: bool = True,
) -> RenderResult:
    """Render every organ mesh in *patient_dir* as one merged actor and return the RenderResult."""
    organs = ircadb_organ_names(patient_dir)
    clear_scene(scene, dark_mode)

    parts: list[pv.DataSet] = []
    loaded_organs: list[str] = []
    for organ in organs:
        vtk_path = patient_dir / f"{organ}.vtk"
        if not vtk_path.exists():
            logger.warning("Skipping missing organ file %s.", vtk_path)
            continue
        try:
            mesh = load_mesh(vtk_path).triangulate()
            mesh.clear_data()
            mesh.cell_data["region_id"] = np.full(
                mesh.n_cells, len(parts), dtype=np.int32
            )
            parts.append(mesh)
            loaded_organs.append(organ)
        except Exception as e:  # noqa: BLE001 - a bad organ file skips that organ
            logger.warning("Skipping organ '%s': %s", vtk_path.name, e)

    n = len(parts)
    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]
    colors = region_colors(n, _palette)
    stats: dict[str, int] | None = None
    if parts:
        merged = pv.merge(parts)
        scene.active_actor = scene.plotter.add_mesh(
            as_surface(merged),
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
    apply_opacity(scene, opacity)
    push_scene(scene, ctrl, reset_camera=reset_camera)
    legend = [
        {"names": [format_organ_name(organ)], "color": colors[i]}
        for i, organ in enumerate(loaded_organs)
    ]
    return RenderResult(legend_items=legend, mesh_stats=stats)


def _render_region_array_mesh(
    scene: Scene,
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
    """Render *mesh_path* coloured by the cell array *region_array*, labelled from *region_labels* or *meta*, with an optional *fiber* overlay, and return the RenderResult."""
    if not mesh_path.exists():
        raise FileNotFoundError(f"Missing region mesh: {mesh_path}")
    mesh = load_mesh(mesh_path)

    # region_labels wins; else the labels file, keyed by labels_mesh_key or the mesh filename.
    label_map: dict[int, list[str]] = dict(region_labels) if region_labels else {}
    if not label_map and meta is not None and meta.labels_file:
        labels_path = mesh_path.parent / meta.labels_file
        if labels_path.exists():
            label_map = parse_labels_file(labels_path).get(
                labels_mesh_key or mesh_path.name, {}
            )

    ids = mesh.cell_data[region_array].astype(int)
    unique_ids: list[int] = sorted(int(v) for v in np.unique(ids))
    remap = {rid: i for i, rid in enumerate(unique_ids)}
    region_id = np.array([remap[r] for r in ids], dtype=np.int32)
    mesh.cell_data["region_id"] = region_id
    # The actor shows the cached skin; carry the dense ids over by volume cell id.
    surface, _, cell_ids = load_skin(mesh_path)
    surface.cell_data["region_id"] = (
        region_id if cell_ids is None else region_id[cell_ids]
    )
    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]
    colors = region_colors(len(unique_ids), _palette)
    clear_scene(scene, dark_mode)
    scene.active_actor = scene.plotter.add_mesh(
        surface,
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

    # Fibre glyph overlay, hidden until show_fibers toggles it.
    fiber_actor: vtkActor | None = None
    if fiber is not None and fiber.array in mesh.cell_data:
        cell_idx = np.arange(0, mesh.n_cells, fiber.stride)
        # PyVista's ind type ndarray[dtype[int]] matches no real numpy int array.
        centers = mesh.extract_cells(cell_idx).cell_centers()
        centers[fiber.array] = mesh.cell_data[fiber.array][cell_idx]
        glyphs = centers.glyph(orient=fiber.array, scale=False, factor=fiber.scale)
        fiber_actor = scene.plotter.add_mesh(
            glyphs,
            color="black",
            show_scalar_bar=False,
            copy_mesh=True,
            render=False,
        )
        fiber_actor.SetVisibility(False)

    apply_opacity(scene, opacity)
    push_scene(scene, ctrl, reset_camera=reset_camera)

    legend = [
        {"names": label_map.get(rid, [f"Region {rid}"]), "color": colors[i]}
        for i, rid in enumerate(unique_ids)
    ]
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return RenderResult(legend_items=legend, mesh_stats=stats, fiber_actor=fiber_actor)


def redraw_stl_surface(
    scene: Scene,
    ctrl: TrameCtrl,
    dataset_dir: Path,
    dark_mode: bool,
    opacity: float,
    filename: str,
    palette: list[str] | None = None,
    reset_camera: bool = True,
) -> RenderResult:
    """Render the closed, geometry-only STL/OBJ surface *filename* in one solid colour and return the RenderResult."""
    mesh_path = dataset_dir / filename
    if not mesh_path.exists():
        raise FileNotFoundError(f"Missing surface mesh: {mesh_path}")
    mesh = load_mesh(mesh_path)

    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]
    color = _palette[0] if _palette else "#d62728"
    clear_scene(scene, dark_mode)
    scene.active_actor = scene.plotter.add_mesh(
        as_surface(mesh),
        color=color,
        opacity=opacity,
        show_edges=False,
        show_scalar_bar=False,
        copy_mesh=True,
        render=False,
    )
    apply_opacity(scene, opacity)
    push_scene(scene, ctrl, reset_camera=reset_camera)

    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return RenderResult(mesh_stats=stats)


def _render_region_mesh(
    scene: Scene,
    ctrl: TrameCtrl,
    mesh: pv.DataSet,
    dark_mode: bool,
    opacity: float,
    palette: list[str] | None,
    reset_camera: bool,
    solid: bool = False,
) -> RenderResult:
    """Clear the scene, render *mesh* coloured per ``region_id`` body, or in one colour when *solid* or the array is absent, and return the RenderResult."""
    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]
    clear_scene(scene, dark_mode)
    surface = as_surface(mesh)

    # solid keeps the GRASP phase animation one colour; the body count differs per phase.
    if not solid and "region_id" in mesh.cell_data:
        region_ids = mesh.cell_data["region_id"].astype(int)
        n = int(region_ids.max()) + 1
        colors = region_colors(n, _palette)
        scene.active_actor = scene.plotter.add_mesh(
            surface,
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
        scene.active_actor = scene.plotter.add_mesh(
            surface,
            color=_palette[0],
            opacity=opacity,
            show_edges=False,
            show_scalar_bar=False,
            copy_mesh=True,
            render=False,
        )
        legend = []

    apply_opacity(scene, opacity)
    push_scene(scene, ctrl, reset_camera=reset_camera)
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}
    return RenderResult(legend_items=legend, mesh_stats=stats)


def redraw_region_surface_step(
    scene: Scene,
    ctrl: TrameCtrl,
    pvd_path: Path,
    dark_mode: bool,
    opacity: float,
    step: int,
    palette: list[str] | None = None,
    reset_camera: bool = True,
    solid: bool = True,
) -> RenderResult:
    """Render phase *step* of the region-coloured PVD surface series at *pvd_path* (GRASP MRI) and return the RenderResult."""
    # Phases differ in topology, so each is a full redraw; solid defaults on against colour flicker.
    mesh = load_mesh(pvd_path, step=step)
    return _render_region_mesh(
        scene, ctrl, mesh, dark_mode, opacity, palette, reset_camera, solid=solid
    )


def redraw_scalar_field(
    scene: Scene,
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
    """Render *mesh_file* coloured by *field*, as zones with a legend when categorical or a ramp clamped at *percentile*, and return the RenderResult."""
    sim_path = dataset_dir / mesh_file
    if not sim_path.exists():
        raise FileNotFoundError(f"Missing scalar-field mesh: {sim_path}")
    mesh = load_mesh(sim_path)

    _palette = palette if palette is not None else CATEGORICAL_PALETTES["paired"]
    is_categorical = field in categorical_fields

    # The actor shows the cached skin; the volume mesh gives the stats and colour limits.
    surface, _, cell_ids = load_skin(sim_path)

    # _zone_id is the dense zone index update_scalar_field_view switches to in place.
    if is_categorical:
        zones = mesh.cell_data[field].astype(int)
        zone_ids: list[int] = sorted(int(z) for z in np.unique(zones))
        zone_map = {z: i for i, z in enumerate(zone_ids)}
        zone_id = np.array([zone_map[int(z)] for z in zones], dtype=np.int32)
        surface.cell_data["_zone_id"] = (
            zone_id if cell_ids is None else zone_id[cell_ids]
        )
    clear_scene(scene, dark_mode)
    stats = {"n_cells": mesh.n_cells, "n_points": mesh.n_points}

    if is_categorical:
        n = len(zone_ids)
        colors = region_colors(n, _palette)
        scene.active_actor = scene.plotter.add_mesh(
            surface,
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
        apply_opacity(scene, opacity)
        push_scene(scene, ctrl, reset_camera=reset_camera)
        legend = [
            {"names": zone_labels.get(z, [f"Zone {z}"]), "color": colors[i]}
            for i, z in enumerate(zone_ids)
        ]
        return RenderResult(legend_items=legend, mesh_stats=stats)

    data = mesh.cell_data[field]
    # The upper limit at the percentile keeps outliers from washing out the ramp.
    clim = [float(data.min()), float(np.percentile(data, percentile))]
    scene.active_actor = scene.plotter.add_mesh(
        surface,
        scalars=field,
        cmap=cast("ColormapOptions", cmap),
        clim=clim,
        opacity=opacity,
        show_edges=False,
        show_scalar_bar=False,
        copy_mesh=True,
        render=False,
    )
    apply_opacity(scene, opacity)
    push_scene(scene, ctrl, reset_camera=reset_camera)
    return RenderResult(
        mesh_stats=stats, scalar_bar_info=_scalar_bar_dict(field, clim, cmap)
    )


# Vessel-tree helpers


def _load_multi_part_vtk(
    ddir: Path,
    parts: list[tuple[str, str]],
    extensions: list[str],
) -> list[pv.DataSet]:
    """Load one mesh per part stem in *ddir* by the first matching extension and return them."""
    meshes: list[pv.DataSet] = []
    for stem, _ in parts:
        path: Path | None = None
        for ext in extensions:
            candidate = ddir / f"{stem}{ext}"
            if candidate.exists():
                path = candidate
                break
        if path is None:
            raise FileNotFoundError(
                f"Missing mesh for part '{stem}' in {ddir} (tried {extensions})"
            )
        meshes.append(load_mesh(path).copy())
    return meshes


def _subsample_lines(mesh: pv.PolyData, stride: int) -> pv.PolyData:
    """Return a PolyData with every *stride*-th line cell of *mesh* and its radius array."""
    if stride <= 1 or mesh.n_lines == 0:
        return mesh
    lines = mesh.lines.reshape(-1, 3)[::stride]  # rows of [2, i0, i1]
    # Slicing the connectivity keeps a PolyData, so .tube still applies.
    sub = pv.PolyData(mesh.points, lines=lines.ravel())
    if "radius" in mesh.point_data:
        sub.point_data["radius"] = mesh.point_data["radius"]
    return sub


def _render_labeled_parts(
    scene: Scene,
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
    """Merge *meshes* into one actor coloured per part, tubing radius meshes when *tubify* after subsampling by *tube_stride*, and return the RenderResult."""
    total_cells = 0
    total_points = 0
    processed: list[pv.DataSet] = []
    for i, mesh in enumerate(meshes):
        if tubify and "radius" in mesh.point_data:
            # A full liver vessel tree (~200k segments) tubes to tens of millions of points, beyond what the browser renders.
            if tube_stride > 1 and isinstance(mesh, pv.PolyData):
                mesh = _subsample_lines(mesh, tube_stride)
            # Triangulate the tube strips: a stale strip index in a local-mode delta unzips the whole strip; a poly loses one triangle.
            mesh = mesh.tube(
                scalars="radius", absolute=True, n_sides=n_tube_sides
            ).triangulate()
        mesh.cell_data["region_id"] = np.full(mesh.n_cells, i, dtype=np.int32)
        total_cells += mesh.n_cells
        total_points += mesh.n_points
        processed.append(mesh)
    meshes = processed
    n = len(meshes)

    merged = meshes[0]
    for m in meshes[1:]:
        merged = merged.merge(m)

    scene.active_actor = scene.plotter.add_mesh(
        as_surface(merged),
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
    apply_opacity(scene, opacity)
    push_scene(scene, ctrl, reset_camera=reset_camera)

    legend = [{"names": [label], "color": colors[i]} for i, label in enumerate(labels)]
    stats = {"n_cells": total_cells, "n_points": total_points}
    return RenderResult(legend_items=legend, mesh_stats=stats)
