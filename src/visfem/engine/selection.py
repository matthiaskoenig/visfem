"""Dataset selection handlers for VisFEM."""
import pyvista as pv
from typing import Any

from visfem.engine.scene import clear_scene, redraw_heart, redraw_heart_ep, redraw_ircadb, redraw_xdmf
from visfem.log import get_logger
from visfem.models import MeshMetadata, ProjectMetadata
from visfem.engine.discovery import dataset_dir, discover_xdmf, meta_to_state

logger = get_logger(__name__)


def select_dataset(
    plotter: pv.Plotter,
    ctrl: object,
    state: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    key: str,
) -> None:
    """Route to the correct redraw based on dataset key."""
    state.active_dataset = key  # type: ignore[attr-defined]
    state.active_patient = None  # type: ignore[attr-defined]
    state.active_xdmf = None  # type: ignore[attr-defined]
    state.ctrl_opacity = 0.8  # type: ignore[attr-defined]
    state.trame__busy = True  # type: ignore[attr-defined]
    try:
        meta = project_metadata[key]
        ddir = dataset_dir(meta)
        xdmf_files = discover_xdmf(ddir)
        if key == "heart":
            legend, stats = redraw_heart(
                plotter, ctrl, meta, ddir,
                dark_mode=state.dark_mode,
                opacity=state.ctrl_opacity,
            )
            state.legend_items = legend
            state.mesh_stats = stats
        elif key == "heart_ep":
            legend, stats = redraw_heart_ep(
                plotter, ctrl, ddir,
                dark_mode=state.dark_mode,
                opacity=state.ctrl_opacity,
            )
            state.legend_items = legend
            state.mesh_stats = stats
        elif key == "ircadb":
            state.legend_items = []
            state.mesh_stats = None
            clear_scene(plotter, state.dark_mode)
        elif xdmf_files:
            first_path = next(iter(xdmf_files.values()))
            legend, stats = redraw_xdmf(
                plotter, ctrl, first_path, xdmf_meta,
                dark_mode=state.dark_mode,
                opacity=state.ctrl_opacity,
            )
            state.legend_items = legend
            state.mesh_stats = stats
        state.active_meta = meta_to_state(meta)
    finally:
        state.trame__busy = False  # type: ignore[attr-defined]


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
    state.ctrl_opacity = 0.8  # type: ignore[attr-defined]
    state.trame__busy = True  # type: ignore[attr-defined]
    try:
        meta = project_metadata[key]
        path = discover_xdmf(dataset_dir(meta)).get(stem)
        if path is None:
            logger.error(f"XDMF file not found: {stem} in {key}")
            return
        legend, stats = redraw_xdmf(
            plotter, ctrl, path, xdmf_meta,
            dark_mode=state.dark_mode,
            opacity=state.ctrl_opacity,
        )
        state.legend_items = legend
        state.mesh_stats = stats
        state.active_meta = meta_to_state(project_metadata[key])
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
    state.ctrl_opacity = 0.8  # type: ignore[attr-defined]
    state.trame__busy = True  # type: ignore[attr-defined]
    try:
        ircadb_meta = project_metadata["ircadb"]
        patient_dir = dataset_dir(ircadb_meta) / f"patient_{patient:02d}"
        legend, stats = redraw_ircadb(
            plotter, ctrl, patient_dir,
            dark_mode=state.dark_mode,
            opacity=state.ctrl_opacity,
        )
        state.legend_items = legend
        state.mesh_stats = stats
        state.active_meta = meta_to_state(project_metadata["ircadb"])
    finally:
        state.trame__busy = False  # type: ignore[attr-defined]