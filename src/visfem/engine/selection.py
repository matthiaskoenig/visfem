"""Dataset selection handlers for VisFEM."""
from pathlib import Path
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
from visfem.engine.discovery import dataset_dir, discover_xdmf, meta_to_state, pvd_file_path

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
    name: str = str(state.active_categorical_palette)  
    return CATEGORICAL_PALETTES.get(name, CATEGORICAL_PALETTES["paired"])


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
    return str(state.active_continuous_cmap)  


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
    state.active_dataset = key  
    state.active_patient = None  
    state.active_xdmf = None  
    state.show_fibers = False  
    state.available_scalar_fields = []  
    state.active_scalar_field = None  
    state.n_steps = 1  
    state.active_step = 0  
    state.step_times = []  

    # Reset color defaults per dataset type
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
            default_field: str | None = TIBIA_SIM_FIELDS[0]["name"]
            assert default_field is not None
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
            state.available_scalar_fields = TIBIA_SIM_FIELDS  
            state.active_scalar_field = default_field  
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
                legend, stats, scalar_bar = redraw_xdmf(
                    plotter, ctrl, pvd_p, xdmf_meta,
                    dark_mode=state.dark_mode,
                    opacity=opacity,
                    field=default_field,
                    step=0,
                    cmap=_resolve_cmap(state),
                )
                state.legend_items = legend
                state.mesh_stats = stats
                state.scalar_bar = scalar_bar
                state.available_scalar_fields = scalar_fields  
                state.active_scalar_field = default_field  
                state.n_steps = pvd_meta.n_steps if pvd_meta else 1  
                state.step_times = list(pvd_meta.times) if pvd_meta else []  
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
    ctrl: object,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    key: str,
    stem: str,
) -> None:
    """Load and render a specific XDMF file within a multi-file dataset."""
    state.active_dataset = key  
    state.active_xdmf = stem  
    state.active_patient = None  
    state.available_scalar_fields = []  
    state.active_scalar_field = None  
    state.n_steps = 1  
    state.active_step = 0  
    state.step_times = []  
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
        state.available_scalar_fields = scalar_fields  
        state.active_scalar_field = default_field  
        state.n_steps = stem_meta.n_steps if stem_meta else 1  
        state.step_times = list(stem_meta.times) if stem_meta else []  
        state.active_meta = meta_to_state(project_metadata[key])
    finally:
        state.trame__busy = False  


def select_scalar_field(
    plotter: pv.Plotter,
    ctrl: object,
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
            # XDMF or PVD dataset — resolve the active timeseries file path.
            meta = project_metadata[active_dataset]
            xdmf_files = discover_xdmf(dataset_dir(meta))
            path = _timeseries_path(meta, state, xdmf_files)
            if path is None:
                logger.error(f"No timeseries file found for dataset '{active_dataset}'")
                return
            current_step: int = int(state.active_step)  
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
        state.trame__busy = False  


def select_step(
    plotter: pv.Plotter,
    ctrl: object,
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
        state.trame__busy = False  


def select_patient(
    plotter: pv.Plotter,
    ctrl: object,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    patient: int,
) -> None:
    """Load and render a specific IRCADb patient."""
    state.active_dataset = "ircadb"  
    state.active_patient = patient  
    state.active_xdmf = None  
    state.available_scalar_fields = []  
    state.active_scalar_field = None  
    state.scalar_bar = None  
    state.n_steps = 1  
    state.active_step = 0  
    state.step_times = []  
    opacity = float(state.ctrl_opacity)  
    state.trame__busy = True  
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
        state.trame__busy = False  


def select_color_scheme(
    plotter: pv.Plotter,
    ctrl: object,
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
        if key == "ircadb":
            patient: int | None = state.active_patient  
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
            field: str = state.active_scalar_field  
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
            # XDMF or PVD dataset
            meta = project_metadata[key]
            xdmf_files = discover_xdmf(dataset_dir(meta))
            path = _timeseries_path(meta, state, xdmf_files)
            if path is None:
                logger.error(f"No timeseries file found for dataset '{key}'")
                return
            field = state.active_scalar_field  
            step: int = int(state.active_step)  
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
        state.trame__busy = False  
