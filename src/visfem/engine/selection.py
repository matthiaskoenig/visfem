"""Dataset selection handlers for VisFEM."""
import pyvista as pv
from typing import Any
from vtkmodules.vtkRenderingCore import vtkActor

from visfem.engine.palettes import CATEGORICAL_PALETTES
from visfem.engine.scene import (
    TIBIA_SIM_FIELDS,
    clear_scene, field_label, redraw_heart, redraw_heart_ep,
    redraw_ircadb, redraw_tibia_mesh, redraw_tibia_simulation, redraw_xdmf,
)
from visfem.log import get_logger
from visfem.models import MeshMetadata, ProjectMetadata
from visfem.engine.discovery import dataset_dir, discover_xdmf, meta_to_state

logger = get_logger(__name__)


def _scalar_fields_from_meta(mesh_meta: MeshMetadata | None) -> list[dict[str, str]]:
    """Return {name, label} entries for scalar (shape==[1]) fields in *mesh_meta*."""
    if mesh_meta is None:
        return []
    return [
        {"name": fname, "label": field_label(fname)}
        for fname, finfo in mesh_meta.fields.items()
        if finfo.shape == [1]
    ]


def _resolve_palette(state: Any) -> list[str]:
    """Return the active categorical palette colors from state."""
    name: str = str(state.active_categorical_palette)  # type: ignore[attr-defined]
    return CATEGORICAL_PALETTES.get(name, CATEGORICAL_PALETTES["paired"])


def _resolve_cmap(state: Any) -> str:
    """Return the active continuous colormap name from state."""
    return str(state.active_continuous_cmap)  # type: ignore[attr-defined]


def select_dataset(
    plotter: pv.Plotter,
    ctrl: object,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    key: str,
) -> vtkActor | None:
    """Route to the correct redraw based on dataset key.

    Returns the fiber glyph actor when key=='heart', otherwise None.
    Sets per-dataset palette/cmap defaults before rendering.
    """
    state.active_dataset = key  # type: ignore[attr-defined]
    state.active_patient = None  # type: ignore[attr-defined]
    state.active_xdmf = None  # type: ignore[attr-defined]
    state.show_fibers = False  # type: ignore[attr-defined]
    state.available_scalar_fields = []  # type: ignore[attr-defined]
    state.active_scalar_field = None  # type: ignore[attr-defined]
    state.n_steps = 1  # type: ignore[attr-defined]
    state.active_step = 0  # type: ignore[attr-defined]
    state.step_times = []  # type: ignore[attr-defined]

    # Reset color defaults per dataset type.
    # Tibia datasets default to "clinical" palette (suits Claes healing zones).
    # Everything else defaults to "paired" (enough distinct colors for many regions).
    if key in ("tibia_simulation", "tibia_mesh"):
        state.active_categorical_palette = "clinical"  # type: ignore[attr-defined]
    else:
        state.active_categorical_palette = "paired"  # type: ignore[attr-defined]
    state.active_continuous_cmap = "viridis"  # type: ignore[attr-defined]

    opacity = float(state.ctrl_opacity)  # type: ignore[attr-defined]
    state.trame__busy = True  # type: ignore[attr-defined]
    fiber_actor: vtkActor | None = None
    try:
        meta = project_metadata[key]
        ddir = dataset_dir(meta)
        xdmf_files = discover_xdmf(ddir)
        if key == "heart":
            legend, stats, fiber_actor = redraw_heart(
                plotter, ctrl, meta, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
            )
            state.legend_items = legend
            state.mesh_stats = stats
            state.scalar_bar = None
        elif key == "tibia_mesh":
            legend, stats = redraw_tibia_mesh(
                plotter, ctrl, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
            )
            state.legend_items = legend
            state.mesh_stats = stats
            state.scalar_bar = None
        elif key == "tibia_simulation":
            default_field = TIBIA_SIM_FIELDS[0]["name"]
            legend, stats, scalar_bar = redraw_tibia_simulation(
                plotter, ctrl, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                field=default_field,
                palette=_resolve_palette(state),
                cmap=_resolve_cmap(state),
            )
            state.legend_items = legend
            state.mesh_stats = stats
            state.scalar_bar = scalar_bar
            state.available_scalar_fields = TIBIA_SIM_FIELDS  # type: ignore[attr-defined]
            state.active_scalar_field = default_field  # type: ignore[attr-defined]
        elif key == "heart_ep":
            legend, stats = redraw_heart_ep(
                plotter, ctrl, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
            )
            state.legend_items = legend
            state.mesh_stats = stats
            state.scalar_bar = None
        elif key == "ircadb":
            state.legend_items = []
            state.mesh_stats = None
            state.scalar_bar = None
            clear_scene(plotter, state.dark_mode)
        elif xdmf_files:
            first_stem, first_path = next(iter(xdmf_files.items()))
            first_meta = xdmf_meta.get(first_stem)
            scalar_fields = _scalar_fields_from_meta(first_meta)
            default_field = scalar_fields[0]["name"] if scalar_fields else None
            legend, stats, scalar_bar = redraw_xdmf(
                plotter, ctrl, first_path, xdmf_meta,
                dark_mode=state.dark_mode,
                opacity=opacity,
                field=default_field,
                step=0,
                cmap=_resolve_cmap(state),
            )
            state.legend_items = legend
            state.mesh_stats = stats
            state.scalar_bar = scalar_bar
            state.available_scalar_fields = scalar_fields  # type: ignore[attr-defined]
            state.active_scalar_field = default_field  # type: ignore[attr-defined]
            state.n_steps = first_meta.n_steps if first_meta else 1  # type: ignore[attr-defined]
            state.step_times = list(first_meta.times) if first_meta else []  # type: ignore[attr-defined]
        state.active_meta = meta_to_state(meta)
    finally:
        state.trame__busy = False  # type: ignore[attr-defined]
    return fiber_actor


def select_xdmf(
    plotter: pv.Plotter,
    ctrl: object,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    key: str,
    stem: str,
) -> None:
    """Load and render a specific XDMF file within a multi-file dataset."""
    state.active_dataset = key  # type: ignore[attr-defined]
    state.active_xdmf = stem  # type: ignore[attr-defined]
    state.active_patient = None  # type: ignore[attr-defined]
    state.available_scalar_fields = []  # type: ignore[attr-defined]
    state.active_scalar_field = None  # type: ignore[attr-defined]
    state.n_steps = 1  # type: ignore[attr-defined]
    state.active_step = 0  # type: ignore[attr-defined]
    state.step_times = []  # type: ignore[attr-defined]
    opacity = float(state.ctrl_opacity)  # type: ignore[attr-defined]
    state.trame__busy = True  # type: ignore[attr-defined]
    try:
        meta = project_metadata[key]
        path = discover_xdmf(dataset_dir(meta)).get(stem)
        if path is None:
            logger.error(f"XDMF file not found: {stem} in {key}")
            return
        stem_meta = xdmf_meta.get(stem)
        scalar_fields = _scalar_fields_from_meta(stem_meta)
        default_field = scalar_fields[0]["name"] if scalar_fields else None
        legend, stats, scalar_bar = redraw_xdmf(
            plotter, ctrl, path, xdmf_meta,
            dark_mode=state.dark_mode,
            opacity=opacity,
            field=default_field,
            step=0,
            cmap=_resolve_cmap(state),
        )
        state.legend_items = legend
        state.mesh_stats = stats
        state.scalar_bar = scalar_bar
        state.available_scalar_fields = scalar_fields  # type: ignore[attr-defined]
        state.active_scalar_field = default_field  # type: ignore[attr-defined]
        state.n_steps = stem_meta.n_steps if stem_meta else 1  # type: ignore[attr-defined]
        state.step_times = list(stem_meta.times) if stem_meta else []  # type: ignore[attr-defined]
        state.active_meta = meta_to_state(project_metadata[key])
    finally:
        state.trame__busy = False  # type: ignore[attr-defined]


def select_scalar_field(
    plotter: pv.Plotter,
    ctrl: object,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    field: str,
) -> None:
    """Re-render the current dataset with a different scalar field."""
    state.active_scalar_field = field  # type: ignore[attr-defined]
    opacity = float(state.ctrl_opacity)  # type: ignore[attr-defined]
    state.trame__busy = True  # type: ignore[attr-defined]
    try:
        active_dataset: str = state.active_dataset  # type: ignore[attr-defined]
        if active_dataset == "tibia_simulation":
            meta = project_metadata["tibia_simulation"]
            legend, stats, scalar_bar = redraw_tibia_simulation(
                plotter, ctrl, dataset_dir(meta),
                dark_mode=state.dark_mode,
                opacity=opacity,
                field=field,
                palette=_resolve_palette(state),
                cmap=_resolve_cmap(state),
            )
            state.legend_items = legend
            state.mesh_stats = stats
            state.scalar_bar = scalar_bar
        else:
            # XDMF dataset — resolve file path from active_xdmf or first available file.
            meta = project_metadata[active_dataset]
            xdmf_files = discover_xdmf(dataset_dir(meta))
            stem: str | None = state.active_xdmf  # type: ignore[attr-defined]
            path = xdmf_files.get(stem) if stem else next(iter(xdmf_files.values()), None)
            if path is None:
                logger.error(f"No XDMF file found for dataset '{active_dataset}'")
                return
            current_step: int = int(state.active_step)  # type: ignore[attr-defined]
            legend, stats, scalar_bar = redraw_xdmf(
                plotter, ctrl, path, xdmf_meta,
                dark_mode=state.dark_mode,
                opacity=opacity,
                field=field,
                step=current_step,
                reset_camera=False,
                cmap=_resolve_cmap(state),
            )
            state.legend_items = legend
            state.mesh_stats = stats
            state.scalar_bar = scalar_bar
    finally:
        state.trame__busy = False  # type: ignore[attr-defined]


def select_step(
    plotter: pv.Plotter,
    ctrl: object,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    step: int,
) -> None:
    """Navigate the current XDMF dataset to a different timestep.

    Camera position is preserved — only the mesh data and scalar bar are updated.
    """
    state.active_step = step  # type: ignore[attr-defined]
    opacity = float(state.ctrl_opacity)  # type: ignore[attr-defined]
    state.trame__busy = True  # type: ignore[attr-defined]
    try:
        active_dataset: str = state.active_dataset  # type: ignore[attr-defined]
        meta = project_metadata[active_dataset]
        xdmf_files = discover_xdmf(dataset_dir(meta))
        stem: str | None = state.active_xdmf  # type: ignore[attr-defined]
        path = xdmf_files.get(stem) if stem else next(iter(xdmf_files.values()), None)
        if path is None:
            logger.error(f"No XDMF file found for dataset '{active_dataset}'")
            return
        field: str | None = state.active_scalar_field  # type: ignore[attr-defined]
        _legend, stats, scalar_bar = redraw_xdmf(
            plotter, ctrl, path, xdmf_meta,
            dark_mode=state.dark_mode,
            opacity=opacity,
            field=field,
            step=step,
            reset_camera=False,  # preserve the user's current camera position
            cmap=_resolve_cmap(state),
        )
        state.mesh_stats = stats
        state.scalar_bar = scalar_bar
    finally:
        state.trame__busy = False  # type: ignore[attr-defined]


def select_patient(
    plotter: pv.Plotter,
    ctrl: object,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    patient: int,
) -> None:
    """Load and render a specific IRCADb patient."""
    state.active_dataset = "ircadb"  # type: ignore[attr-defined]
    state.active_patient = patient  # type: ignore[attr-defined]
    state.active_xdmf = None  # type: ignore[attr-defined]
    state.available_scalar_fields = []  # type: ignore[attr-defined]
    state.active_scalar_field = None  # type: ignore[attr-defined]
    state.scalar_bar = None  # type: ignore[attr-defined]
    state.n_steps = 1  # type: ignore[attr-defined]
    state.active_step = 0  # type: ignore[attr-defined]
    state.step_times = []  # type: ignore[attr-defined]
    opacity = float(state.ctrl_opacity)  # type: ignore[attr-defined]
    state.trame__busy = True  # type: ignore[attr-defined]
    try:
        ircadb_meta = project_metadata["ircadb"]
        patient_dir = dataset_dir(ircadb_meta) / f"patient_{patient:02d}"
        legend, stats = redraw_ircadb(
            plotter, ctrl, patient_dir,
            dark_mode=state.dark_mode,
            opacity=opacity,
            palette=_resolve_palette(state),
        )
        state.legend_items = legend
        state.mesh_stats = stats
        state.active_meta = meta_to_state(project_metadata["ircadb"])
    finally:
        state.trame__busy = False  # type: ignore[attr-defined]


def select_color_scheme(
    plotter: pv.Plotter,
    ctrl: object,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
) -> None:
    """Re-render the current scene after a palette or colormap change.

    Does not change navigation state (field, step, patient, camera).
    The caller is responsible for updating active_categorical_palette or
    active_continuous_cmap in state before calling this function.
    """
    key: str | None = state.active_dataset  # type: ignore[attr-defined]
    if key is None:
        return

    opacity = float(state.ctrl_opacity)  # type: ignore[attr-defined]
    state.trame__busy = True  # type: ignore[attr-defined]
    try:
        if key == "ircadb":
            patient: int | None = state.active_patient  # type: ignore[attr-defined]
            if patient is None:
                return
            ircadb_meta = project_metadata["ircadb"]
            patient_dir = dataset_dir(ircadb_meta) / f"patient_{patient:02d}"
            legend, stats = redraw_ircadb(
                plotter, ctrl, patient_dir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
            )
            state.legend_items = legend
            state.mesh_stats = stats
        elif key == "heart":
            meta = project_metadata["heart"]
            ddir = dataset_dir(meta)
            legend, stats, _ = redraw_heart(
                plotter, ctrl, meta, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
            )
            state.legend_items = legend
            state.mesh_stats = stats
        elif key == "heart_ep":
            meta = project_metadata["heart_ep"]
            ddir = dataset_dir(meta)
            legend, stats = redraw_heart_ep(
                plotter, ctrl, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
            )
            state.legend_items = legend
            state.mesh_stats = stats
        elif key == "tibia_mesh":
            meta = project_metadata["tibia_mesh"]
            ddir = dataset_dir(meta)
            legend, stats = redraw_tibia_mesh(
                plotter, ctrl, ddir,
                dark_mode=state.dark_mode,
                opacity=opacity,
                palette=_resolve_palette(state),
            )
            state.legend_items = legend
            state.mesh_stats = stats
        elif key == "tibia_simulation":
            meta = project_metadata["tibia_simulation"]
            field: str = state.active_scalar_field  # type: ignore[attr-defined]
            legend, stats, scalar_bar = redraw_tibia_simulation(
                plotter, ctrl, dataset_dir(meta),
                dark_mode=state.dark_mode,
                opacity=opacity,
                field=field,
                palette=_resolve_palette(state),
                cmap=_resolve_cmap(state),
            )
            state.legend_items = legend
            state.mesh_stats = stats
            state.scalar_bar = scalar_bar
        else:
            # XDMF dataset.
            meta = project_metadata[key]
            xdmf_files = discover_xdmf(dataset_dir(meta))
            stem: str | None = state.active_xdmf  # type: ignore[attr-defined]
            path = xdmf_files.get(stem) if stem else next(iter(xdmf_files.values()), None)
            if path is None:
                logger.error(f"No XDMF file found for dataset '{key}'")
                return
            field = state.active_scalar_field  # type: ignore[attr-defined]
            step: int = int(state.active_step)  # type: ignore[attr-defined]
            _legend, stats, scalar_bar = redraw_xdmf(
                plotter, ctrl, path, xdmf_meta,
                dark_mode=state.dark_mode,
                opacity=opacity,
                field=field,
                step=step,
                reset_camera=False,
                cmap=_resolve_cmap(state),
            )
            state.mesh_stats = stats
            state.scalar_bar = scalar_bar
    finally:
        state.trame__busy = False  # type: ignore[attr-defined]
