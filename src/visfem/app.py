"""Trame web application for FEM mesh visualization."""
from pathlib import Path

import numpy as np
import pyvista as pv
import pyvista.plotting.colors as pvc
from trame.app import TrameApp
from trame.decorators import change
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import html
from trame.widgets import vuetify3 as v3
from trame.widgets.vtk import VtkLocalView, VtkWebXRHelper

from visfem.log import get_logger
from visfem.mesh import get_metadata, load_mesh, parse_labels_file
from visfem.models import MeshMetadata, ProjectMetadata
from vtkmodules.vtkRenderingCore import vtkActor

logger = get_logger(__name__)


# ---- Background gradients ----

_BG_DARK_BOTTOM  = (0.08, 0.10, 0.10)
_BG_DARK_TOP     = (0.13, 0.16, 0.16)
_BG_LIGHT_BOTTOM = (0.82, 0.84, 0.84)
_BG_LIGHT_TOP    = (0.95, 0.96, 0.96)


# ---- Color palettes ----

def _scheme_to_hex(scheme_id: int) -> list[str]:
    """Convert a PyVista color scheme to a list of hex color strings."""
    colors = []
    for item in pvc.color_scheme_to_cycler(scheme_id):
        c = item["color"]
        colors.append("#{:02x}{:02x}{:02x}".format(c[0], c[1], c[2]))
    return colors


_COLORS_PAIRED = _scheme_to_hex(60)  # qual_paired (11 colors) for all region renders


def _region_colors(n: int, palette: list[str]) -> list[str]:
    """Return n colors cycled from palette."""
    return [palette[i % len(palette)] for i in range(n)]


# ---- Paths ----

_DATA_BASE    = Path(__file__).parents[2] / "data" / "fem_data"
_METADATA_DIR = Path(__file__).parents[2] / "data" / "metadata"


# ---- Discovery helpers ----

def _discover_xdmf(directory: Path) -> dict[str, Path]:
    """Return stem->path for all .xdmf files with a matching .h5 in directory."""
    return {
        p.stem: p
        for p in sorted(directory.glob("*.xdmf"))
        if p.with_suffix(".h5").exists()
    }


def _ircadb_organ_names(patient_dir: Path) -> list[str]:
    """Return sorted organ names available for a patient directory."""
    return sorted(f.stem for f in patient_dir.glob("*.vtk"))


def _format_organ_name(name: str) -> str:
    """Insert space before known prefix words in organ names."""
    _prefixes = ("left", "right", "small", "large", "portal", "surrenal", "vena", "venous", "biliary")
    lower = name.lower()
    for prefix in _prefixes:
        if lower.startswith(prefix) and len(name) > len(prefix):
            return name[:len(prefix)] + " " + name[len(prefix):]
    return name


def _xdmf_display_name(stem: str) -> str:
    """Convert an XDMF stem to a readable display name."""
    if stem.startswith("lobule_sixth_"):
        suffix = stem[len("lobule_sixth_"):]
        try:
            return f"Resolution {int(suffix)}"
        except ValueError:
            pass
    return stem.replace("_", " ").title()


# ---- Metadata helpers ----

def _load_project_metadata() -> dict[str, ProjectMetadata]:
    """Load and validate all ProjectMetadata JSONs from data/metadata/."""
    result: dict[str, ProjectMetadata] = {}
    for path in sorted(_METADATA_DIR.glob("*.json")):
        result[path.stem] = ProjectMetadata.model_validate_json(path.read_text())
    return result


def _group_by_organ_system(
    metadata: dict[str, ProjectMetadata],
) -> dict[str, list[tuple[str, ProjectMetadata]]]:
    """Group datasets by first organ_system value."""
    groups: dict[str, list[tuple[str, ProjectMetadata]]] = {}
    for key, meta in metadata.items():
        system = meta.organ_system[0].value
        groups.setdefault(system, [])
        groups[system].append((key, meta))
    return groups


def _dataset_dir(meta: ProjectMetadata) -> Path:
    """Resolve the filesystem directory for a dataset from its metadata."""
    return _DATA_BASE / meta.data_path


# ---- App ----

class VisfemApp(TrameApp):
    """Main Trame application for VisFEM."""

    def __init__(self, server: object = None) -> None:
        super().__init__(server)
        self._project_metadata = _load_project_metadata()
        self._organ_groups = _group_by_organ_system(self._project_metadata)
        self._xdmf_meta: dict[str, MeshMetadata] = {}
        for meta in self._project_metadata.values():
            for name, path in _discover_xdmf(_dataset_dir(meta)).items():
                self._xdmf_meta[name] = get_metadata(path)
        ircadb_meta = self._project_metadata.get("ircadb")
        ircadb_dir = _dataset_dir(ircadb_meta) if ircadb_meta else None
        self._ircadb_patients: list[int] = sorted(
            int(d.name.split("_")[-1])
            for d in (ircadb_dir.glob("patient_*") if ircadb_dir else [])
            if d.is_dir()
        )
        self._setup_plotter()
        self._setup_state()
        self._build_ui()
        self.ctrl.on_client_connected.add(self._reset_xr_state)

    def _setup_plotter(self) -> None:
        """Initialize an empty off-screen plotter."""
        self.plotter = pv.Plotter(off_screen=True, theme=pv.themes.DarkTheme())
        self.plotter.enable_depth_peeling(number_of_peels=4)
        self.plotter.set_background(_BG_DARK_BOTTOM, top=_BG_DARK_TOP)

    def _setup_state(self) -> None:
        """Initialize all Trame state variables."""
        self.state.update({
            "dark_mode": True,
            "xr_active": False,
            "active_dataset": None,
            "active_patient": None,
            "active_xdmf": None,
            "panel_datasets_open": True,
            "panel_controls_open": True,
            "legend_items": [],
            "ctrl_opacity": 0.8,
        })

    # ---- Theme ----

    def toggle_theme(self) -> None:
        """Toggle between dark and light mode."""
        self.state.dark_mode = not self.state.dark_mode
        if self.state.dark_mode:
            self.plotter.set_background(_BG_DARK_BOTTOM, top=_BG_DARK_TOP)
        else:
            self.plotter.set_background(_BG_LIGHT_BOTTOM, top=_BG_LIGHT_TOP)
        self.ctrl.view_update()

    # ---- Camera ----

    def reset_camera(self) -> None:
        """Reset camera to fit current scene."""
        self.plotter.reset_camera()
        self.ctrl.view_push_camera()
        self.ctrl.reset_camera()

    # ---- XR ----

    def _reset_xr_state(self, **kwargs: object) -> None:
        """Reset XR state on client reconnect."""
        self.state.xr_active = False

    def _on_enter_xr(self) -> None:
        """Called when XR session starts."""
        self.state.xr_active = True

    def _on_exit_xr(self) -> None:
        """Called when XR session ends."""
        self.state.xr_active = False
        self.ctrl.view_update()

    def toggle_xr(self) -> None:
        """Toggle WebXR session on/off."""
        if self.state.xr_active:
            self.ctrl.stop_xr()
        else:
            self.ctrl.start_xr(VtkWebXRHelper.XrSessionTypes.HmdVR)

    # ---- Reactive callbacks ----

    @change("ctrl_opacity")
    def _on_opacity_change(self, ctrl_opacity, **_: object) -> None:
        """Apply opacity to all actors when slider changes."""
        if self.state.active_dataset is None:
            return
        for actor in self.plotter.renderer.actors.values():
            if isinstance(actor, vtkActor):
                actor.GetProperty().SetOpacity(float(ctrl_opacity))
        self.ctrl.view_update()

    # ---- Dataset selection ----

    def select_dataset(self, key: str) -> None:
        """Route to the correct redraw based on dataset key."""
        self.state.active_dataset = key
        self.state.active_patient = None
        self.state.active_xdmf = None
        self.state.ctrl_opacity = 0.8
        self.state.trame__busy = True
        try:
            meta = self._project_metadata[key]
            dataset_dir = _dataset_dir(meta)
            xdmf_files = _discover_xdmf(dataset_dir)
            if key == "heart":
                self._redraw_heart(meta, dataset_dir)
            elif key == "ircadb":
                self.state.legend_items = []
                self._clear_scene()
            elif xdmf_files:
                first_path = next(iter(xdmf_files.values()))
                self._redraw_xdmf(first_path)
        finally:
            self.state.trame__busy = False

    def select_xdmf(self, key: str, stem: str) -> None:
        """Load and render a specific XDMF file within a multi-file dataset."""
        self.state.active_dataset = key
        self.state.active_xdmf = stem
        self.state.active_patient = None
        self.state.ctrl_opacity = 0.8
        self.state.trame__busy = True
        try:
            meta = self._project_metadata[key]
            path = _discover_xdmf(_dataset_dir(meta)).get(stem)
            if path is None:
                logger.error(f"XDMF file not found: {stem} in {key}")
                return
            self._redraw_xdmf(path)
        finally:
            self.state.trame__busy = False

    def select_patient(self, patient: int) -> None:
        """Load and render a specific IRCADb patient."""
        self.state.active_dataset = "ircadb"
        self.state.active_patient = patient
        self.state.active_xdmf = None
        self.state.ctrl_opacity = 0.8
        self.state.trame__busy = True
        try:
            ircadb_meta = self._project_metadata["ircadb"]
            patient_dir = _dataset_dir(ircadb_meta) / f"patient_{patient:02d}"
            self._redraw_ircadb(patient_dir)
        finally:
            self.state.trame__busy = False

    # ---- Render helpers ----

    def _clear_scene(self) -> None:
        """Remove all actors and reset renderer state before each render.

        plotter.clear() resets the full renderer including LUT/colormap state,
        preventing stale color accumulation across dataset switches. Called
        before set_background so the background is restored after the reset.
        """
        self.plotter.clear()
        if self.state.dark_mode:
            self.plotter.set_background(_BG_DARK_BOTTOM, top=_BG_DARK_TOP)
        else:
            self.plotter.set_background(_BG_LIGHT_BOTTOM, top=_BG_LIGHT_TOP)

    def _apply_opacity(self) -> None:
        """Push current ctrl_opacity to every actor."""
        opacity = float(self.state.ctrl_opacity)
        for actor in self.plotter.renderer.actors.values():
            if isinstance(actor, vtkActor):
                actor.GetProperty().SetOpacity(opacity)

    def _push_scene(self) -> None:
        """Flush VTK pipeline and push the complete scene to vtk.js."""
        self.plotter.render()
        self.plotter.reset_camera()
        self.ctrl.view_push_camera()
        self.ctrl.view_update()

    def _redraw_xdmf(self, path: Path) -> None:
        """Load and render the first step of an XDMF mesh."""
        self._clear_scene()
        try:
            mesh = load_mesh(path, step=0)
        except Exception as e:
            logger.error(f"Failed to load '{path.name}': {e}")
            return

        mesh_meta = self._xdmf_meta.get(path.stem)
        field = next(iter(mesh_meta.fields), None) if mesh_meta else None

        self.plotter.add_mesh(
            mesh,
            scalars=field,
            show_edges=True,
            edge_color="#000000",
            copy_mesh=True,
            show_scalar_bar=False,
            opacity=self.state.ctrl_opacity,
        )
        self.state.legend_items = []
        self._apply_opacity()
        self._push_scene()

    def _redraw_ircadb(self, patient_dir: Path) -> None:
        """Load all organ meshes for a patient and render as one merged actor."""
        organs = _ircadb_organ_names(patient_dir)
        self._clear_scene()

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
        colors = _region_colors(n, _COLORS_PAIRED)
        if parts:
            self.plotter.add_mesh(
                pv.merge(parts),
                scalars="region_id",
                cmap=colors,
                clim=[0, max(n - 1, 1)],
                n_colors=n,
                opacity=self.state.ctrl_opacity,
                show_edges=False,
                show_scalar_bar=False,
                copy_mesh=True,
                interpolate_before_map=False,
            )
        self.state.legend_items = [
            {"name": _format_organ_name(organ), "color": colors[i]}
            for i, organ in enumerate(loaded_organs)
        ]
        self._apply_opacity()
        self._push_scene()

    def _redraw_heart(self, meta: ProjectMetadata, dataset_dir: Path) -> None:
        """Render the heart mesh colored by material region."""
        mesh_path = dataset_dir / "M.vtu"
        if not mesh_path.exists():
            logger.error(f"Heart mesh not found: {mesh_path}")
            return

        label_map: dict[int, str] = {}
        if meta.labels_file:
            labels_path = dataset_dir / meta.labels_file
            if labels_path.exists():
                label_map = parse_labels_file(labels_path).get("M.vtu", {})

        try:
            mesh = load_mesh(mesh_path)
        except Exception as e:
            logger.error(f"Failed to load heart mesh: {e}")
            return

        material_ids = mesh.cell_data["Material"].astype(int)
        unique_ids: list[int] = sorted(int(v) for v in np.unique(material_ids))
        mesh.cell_data["region_id"] = np.array(
            [{mid: i for i, mid in enumerate(unique_ids)}[mid] for mid in material_ids],
            dtype=np.int32,
        )
        colors = _region_colors(len(unique_ids), _COLORS_PAIRED)

        self._clear_scene()
        self.plotter.add_mesh(
            mesh,
            scalars="region_id",
            cmap=colors,
            clim=[0, len(unique_ids) - 1],
            n_colors=len(unique_ids),
            opacity=self.state.ctrl_opacity,
            show_edges=False,
            show_scalar_bar=False,
            copy_mesh=True,
            interpolate_before_map=False,
        )
        self.state.legend_items = [
            {"name": label_map.get(mid, f"Region {mid}"), "color": colors[i]}
            for i, mid in enumerate(unique_ids)
        ]
        self._apply_opacity()
        self._push_scene()

    # ---- UI ----

    def _build_ui(self) -> None:
        """Build the full UI layout."""
        with SinglePageLayout(self.server, theme=("dark_mode ? 'dark' : 'light'",)) as self.ui:
            self.ui.title.hide()
            self.ui.icon.hide()

            with self.ui.toolbar as toolbar:
                toolbar.density = "compact"
                v3.VProgressLinear(
                    indeterminate=True, absolute=True, bottom=True,
                    active=("trame__busy",), color="#00897b", height=2,
                )
                html.Div(style="width: 15px;")
                v3.VIcon("mdi-vector-triangle", color="#00897b", classes="mr-3")
                html.Span("VisFEM", style="font-size: 1.2rem; font-weight: 600; letter-spacing: 0.05em;")
                v3.VSpacer()
                with v3.VTooltip(text="Toggle theme", location="bottom"):
                    with v3.Template(v_slot_activator="{ props }"):
                        v3.VBtn(
                            icon=("dark_mode ? 'mdi-weather-sunny' : 'mdi-weather-night'",),
                            variant="text", density="compact",
                            click=self.toggle_theme, v_bind="props", classes="ml-3",
                        )
                with v3.VTooltip(text="Reset camera", location="bottom"):
                    with v3.Template(v_slot_activator="{ props }"):
                        v3.VBtn(
                            icon="mdi-crop-free", variant="text", density="compact",
                            click=self.reset_camera, v_bind="props", classes="ml-3",
                        )
                with v3.VTooltip(text="Screenshot", location="bottom"):
                    with v3.Template(v_slot_activator="{ props }"):
                        v3.VBtn(
                            icon="mdi-camera", variant="text", density="compact",
                            v_bind="props", classes="ml-3",
                        )
                with v3.VTooltip(text="Toggle VR", location="bottom"):
                    with v3.Template(v_slot_activator="{ props }"):
                        v3.VBtn(
                            icon="mdi-virtual-reality", variant="text", density="compact",
                            click=self.toggle_xr, v_bind="props", classes="ml-3",
                        )
                html.Div(style="width: 15px;")

            with self.ui.content:
                with v3.VContainer(fluid=True, classes="pa-0 fill-height", style="position: relative;"):
                    with VtkLocalView(self.plotter.render_window) as view:
                        self.ctrl.reset_camera = view.reset_camera
                        self.ctrl.view_push_camera = view.push_camera
                        self.ctrl.view_update = view.update
                        webxr_helper = VtkWebXRHelper(
                            draw_controllers_ray=True,
                            enter_xr=(self._on_enter_xr,),
                            exit_xr=(self._on_exit_xr,),
                        )
                        self.ctrl.start_xr = webxr_helper.start_xr
                        self.ctrl.stop_xr = webxr_helper.stop_xr

                    self._build_dataset_panel()
                    self._build_controls_panel()

    def _build_dataset_panel(self) -> None:
        """Build the floating dataset selection panel on the left."""
        panel_style = (
            "dark_mode ? "
            "'position:absolute; top:12px; left:12px; width:270px; z-index:10; "
            "background:rgba(28,35,35,0.88); backdrop-filter:blur(8px); "
            "-webkit-backdrop-filter:blur(8px); border:1px solid rgba(255,255,255,0.07);' "
            ": "
            "'position:absolute; top:12px; left:12px; width:270px; z-index:10; "
            "background:rgba(240,244,244,0.92); backdrop-filter:blur(8px); "
            "-webkit-backdrop-filter:blur(8px); border:1px solid rgba(0,0,0,0.08);'"
        ,)
        with v3.VCard(style=panel_style, elevation=6, rounded="lg"):
            with v3.VCardTitle(
                style="font-size: 0.85rem; padding: 8px 12px; cursor: pointer; user-select: none;",
                click="panel_datasets_open = !panel_datasets_open",
            ):
                with html.Div(style="display: flex; align-items: center;"):
                    v3.VIcon("mdi-layers-outline", size="small", color="#00897b", classes="mr-2")
                    html.Span("Datasets", style="flex: 1;")
                    v3.VIcon(
                        ("panel_datasets_open ? 'mdi-chevron-up' : 'mdi-chevron-down'",),
                        size="small", style="opacity: 0.6;",
                    )
            with v3.VExpandTransition():
                with html.Div(v_show="panel_datasets_open", style="max-height: 70vh; overflow-y: auto;"):
                    v3.VDivider()
                    with v3.VList(density="compact", nav=True, bg_color="transparent", style="padding: 4px 0;"):
                        for system, datasets in self._organ_groups.items():
                            with v3.VListGroup(value=system):
                                with v3.Template(v_slot_activator="{ props }"):
                                    with v3.VListItem(v_bind="props", density="compact"):
                                        with v3.Template(v_slot_prepend=""):
                                            v3.VIcon("mdi-chevron-right", size="x-small", style="opacity: 0.5;")
                                        with v3.Template(v_slot_title=""):
                                            html.Span(
                                                system.title(),
                                                style="font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; opacity: 0.6;",
                                            )
                                for key, meta in datasets:
                                    dataset_dir = _dataset_dir(meta)
                                    xdmf_files = _discover_xdmf(dataset_dir)

                                    if key == "ircadb":
                                        with v3.VListGroup(value="ircadb"):
                                            with v3.Template(v_slot_activator="{ props }"):
                                                with v3.VListItem(
                                                    v_bind="props", density="compact",
                                                    active=("active_dataset === 'ircadb'",),
                                                    active_color="#00897b", rounded="lg",
                                                    style="padding-left: 24px;",
                                                ):
                                                    with v3.Template(v_slot_prepend=""):
                                                        v3.VIcon("mdi-circle-medium", size="x-small", style="opacity: 0.5;")
                                                    with v3.Template(v_slot_title=""):
                                                        html.Span(meta.name, style="font-size: 0.82rem;")
                                            for patient in self._ircadb_patients:
                                                with v3.VListItem(
                                                    density="compact",
                                                    active=(f"active_dataset === 'ircadb' && active_patient === {patient}",),
                                                    active_color="#00897b", rounded="lg",
                                                    click=(self.select_patient, f"[{patient}]"),
                                                    style="padding-left: 40px;",
                                                ):
                                                    with v3.Template(v_slot_prepend=""):
                                                        v3.VIcon("mdi-account", size="x-small", style="opacity: 0.5;")
                                                    with v3.Template(v_slot_title=""):
                                                        html.Span(f"Patient {patient:02d}", style="font-size: 0.80rem;")

                                    elif key == "heart":
                                        with v3.VListItem(
                                            density="compact",
                                            active=("active_dataset === 'heart'",),
                                            active_color="#00897b", rounded="lg",
                                            click=(self.select_dataset, "['heart']"),
                                            style="padding-left: 24px;",
                                        ):
                                            with v3.Template(v_slot_prepend=""):
                                                v3.VIcon("mdi-circle-medium", size="x-small", style="opacity: 0.5;")
                                            with v3.Template(v_slot_title=""):
                                                html.Span(meta.name, style="font-size: 0.82rem; white-space: normal; word-break: break-word;")

                                    elif len(xdmf_files) == 1:
                                        with v3.VListItem(
                                            density="compact",
                                            active=(f"active_dataset === '{key}'",),
                                            active_color="#00897b", rounded="lg",
                                            click=(self.select_dataset, f"['{key}']"),
                                            style="padding-left: 24px;",
                                        ):
                                            with v3.Template(v_slot_prepend=""):
                                                v3.VIcon("mdi-circle-medium", size="x-small", style="opacity: 0.5;")
                                            with v3.Template(v_slot_title=""):
                                                html.Span(meta.name, style="font-size: 0.82rem; white-space: normal; word-break: break-word;")

                                    elif len(xdmf_files) > 1:
                                        with v3.VListGroup(value=key):
                                            with v3.Template(v_slot_activator="{ props }"):
                                                with v3.VListItem(
                                                    v_bind="props", density="compact",
                                                    active=(f"active_dataset === '{key}'",),
                                                    active_color="#00897b", rounded="lg",
                                                    style="padding-left: 24px;",
                                                ):
                                                    with v3.Template(v_slot_prepend=""):
                                                        v3.VIcon("mdi-circle-medium", size="x-small", style="opacity: 0.5;")
                                                    with v3.Template(v_slot_title=""):
                                                        html.Span(meta.name, style="font-size: 0.82rem; white-space: normal; word-break: break-word;")
                                            for stem, path in xdmf_files.items():
                                                with v3.VListItem(
                                                    density="compact",
                                                    active=(f"active_dataset === '{key}' && active_xdmf === '{stem}'",),
                                                    active_color="#00897b", rounded="lg",
                                                    click=(self.select_xdmf, f"['{key}', '{stem}']"),
                                                    style="padding-left: 40px;",
                                                ):
                                                    with v3.Template(v_slot_prepend=""):
                                                        v3.VIcon("mdi-circle-small", size="x-small", style="opacity: 0.5;")
                                                    with v3.Template(v_slot_title=""):
                                                        html.Span(_xdmf_display_name(stem), style="font-size: 0.80rem;")

    @staticmethod
    def _build_controls_panel() -> None:
        """Build the floating controls panel with opacity slider."""
        panel_style = (
            "dark_mode ? "
            "'position:absolute; top:12px; left:294px; width:220px; z-index:10; "
            "background:rgba(28,35,35,0.88); backdrop-filter:blur(8px); "
            "-webkit-backdrop-filter:blur(8px); border:1px solid rgba(255,255,255,0.07);' "
            ": "
            "'position:absolute; top:12px; left:294px; width:220px; z-index:10; "
            "background:rgba(240,244,244,0.92); backdrop-filter:blur(8px); "
            "-webkit-backdrop-filter:blur(8px); border:1px solid rgba(0,0,0,0.08);'"
        ,)
        with v3.VCard(v_if="active_dataset !== null", style=panel_style, elevation=6, rounded="lg"):
            with v3.VCardTitle(
                style="font-size: 0.85rem; padding: 8px 12px; cursor: pointer; user-select: none;",
                click="panel_controls_open = !panel_controls_open",
            ):
                with html.Div(style="display: flex; align-items: center;"):
                    v3.VIcon("mdi-tune", size="small", color="#00897b", classes="mr-2")
                    html.Span("Controls", style="flex: 1;")
                    v3.VIcon(
                        ("panel_controls_open ? 'mdi-chevron-up' : 'mdi-chevron-down'",),
                        size="small", style="opacity: 0.6;",
                    )
            with v3.VExpandTransition():
                with html.Div(v_show="panel_controls_open"):
                    v3.VDivider()
                    with html.Div(style="padding: 12px 16px;"):
                        html.Div("Opacity", style="font-size: 0.78rem; opacity: 0.6; margin-bottom: 4px;")
                        v3.VSlider(
                            v_model=("ctrl_opacity", 0.8),
                            min=0.0, max=1.0, step=0.1,
                            density="compact", hide_details=True,
                            color="#00897b", track_color="rgba(255,255,255,0.1)",
                            thumb_label=True,
                        )


def main() -> None:
    """Entry point."""
    app = VisfemApp()
    app.server.start()


if __name__ == "__main__":
    main()