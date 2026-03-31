"""Trame web application for FEM mesh visualization."""
from pathlib import Path
import pyvista as pv
from trame.app import TrameApp
from trame.decorators import change
from trame.ui.vuetify3 import SinglePageWithDrawerLayout
from trame.widgets import vuetify3 as v3
from trame.widgets.vtk import VtkLocalView, VtkWebXRHelper
from visfem.log import get_logger
from visfem.mesh import get_metadata, load_mesh, MeshMetadata

logger = get_logger(__name__)

# ---- Dataset paths ----
# Base directory for all datasets, three levels up from the package root
_DATA_BASE = Path(__file__).parents[3] / "visfem_data"

DATA_DIR  = _DATA_BASE / "convergence_sixth" / "xdmf"
SPP_DIR   = _DATA_BASE / "08_SPP_FEMVis"
IRCADB_DIR = _DATA_BASE / "3Dircadb1"

# Four mesh resolutions of the same liver lobule geometry (timeseries XDMF)
CONVERGENCE_FILES = {
    "Coarse (00005)":         DATA_DIR / "lobule_sixth_00005.xdmf",
    "Medium-coarse (000025)": DATA_DIR / "lobule_sixth_000025.xdmf",
    "Medium-fine (0000125)":  DATA_DIR / "lobule_sixth_0000125.xdmf",
    "Fine (00000625)":        DATA_DIR / "lobule_sixth_00000625.xdmf",
}

# Four FEniCS XDMF files: 2D deformation, lobule (p1/p6), and scan meshes
SPP_FILES = {
    "Deformation": SPP_DIR / "deformation" / "deformation.xdmf",
    "Lobule p1":   SPP_DIR / "lobule" / "lobule_spt_p1.xdmf",
    "Lobule p6":   SPP_DIR / "lobule" / "lobule_spt_p6.xdmf",
    "Scan 64 p1":  SPP_DIR / "scan" / "scan_64_p1.xdmf",
}

# Discover available patient subdirectories (3Dircadb1.1, .2, ...) at startup
IRCADB_PATIENTS: list[int] = sorted(
    int(d.name.split(".")[-1])
    for d in IRCADB_DIR.glob("3Dircadb1.*")
    if d.is_dir()
)

# Distinct colors cycled over organs when rendering a full patient scene
_ORGAN_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#42d4f4", "#f032e6", "#bfef45", "#fabed4", "#469990",
    "#dcbeff", "#9a6324", "#fffac8", "#800000", "#aaffc3",
    "#808000", "#ffd8b1", "#000075", "#a9a9a9", "#ffffff",
]


# ---- Helpers ----

def _ircadb_vtk_path(patient: int, organ: str) -> Path:
    """Return the VTK file path for a given patient and organ name."""
    return IRCADB_DIR / f"3Dircadb1.{patient}" / "MESHES_VTK" / f"{organ}.vtk"


def _ircadb_organ_names(patient: int) -> list[str]:
    """Return sorted list of organ names available for a patient."""
    vtk_dir = IRCADB_DIR / f"3Dircadb1.{patient}" / "MESHES_VTK"
    return sorted(f.stem for f in vtk_dir.glob("*.vtk"))


def _all_fields(meta: MeshMetadata) -> list[str]:
    """Return all field names from metadata, including vectors."""
    return list(meta["fields"].keys())


def _format_time(t: float) -> str:
    """Format a time value compactly for display."""
    if t == 0.0:
        return "0"
    if abs(t) >= 1000 or (abs(t) < 0.01 and t != 0):
        return f"{t:.3e}"
    return f"{t:.4g}"


# ---- App ----

class VisfemApp(TrameApp):
    """Main Trame application.

    Manages plotter state, reactive callbacks, and the UI layout
    for all three dataset modes (convergence, SPP, IRCADb).
    """

    def __init__(self, server: object = None) -> None:
        super().__init__(server)
        self._setup_state()
        self._build_ui()
        # Reset XR state whenever a client reconnects
        self.ctrl.on_client_connected.add(self._reset_xr_state)

    def _setup_state(self) -> None:
        """Initialize plotter, pre-load metadata, and set all Trame state variables.

        Metadata is loaded from .meta.json sidecars (fast), no mesh data is read here
        except for the initial convergence mesh shown on startup.
        """
        # Pre-load all metadata at startup using sidecar cache (no full mesh loading every time)
        self._convergence_meta: dict[str, MeshMetadata] = {
            name: get_metadata(path) for name, path in CONVERGENCE_FILES.items()
        }
        self._spp_meta: dict[str, MeshMetadata] = {
            name: get_metadata(path) for name, path in SPP_FILES.items()
        }

        # --- Convergence initial values ---
        conv_names = list(CONVERGENCE_FILES.keys())
        initial_conv_name = conv_names[0]
        initial_conv_meta = self._convergence_meta[initial_conv_name]
        initial_conv_fields = _all_fields(initial_conv_meta)
        initial_conv_times = initial_conv_meta["times"]

        # --- SPP initial values ---
        spp_names = list(SPP_FILES.keys())
        initial_spp_name = spp_names[0]
        initial_spp_meta = self._spp_meta[initial_spp_name]
        initial_spp_fields = _all_fields(initial_spp_meta)
        initial_spp_times = initial_spp_meta["times"]

        initial_patient = IRCADB_PATIENTS[0] if IRCADB_PATIENTS else None

        # Build the plotter and load the first convergence mesh to show on startup
        self.plotter = pv.Plotter(off_screen=True, theme=pv.themes.DarkTheme())
        self.pvmesh = load_mesh(CONVERGENCE_FILES[initial_conv_name], step=1)
        self.plotter.add_mesh(
            self.pvmesh,
            scalars=initial_conv_fields[0] if initial_conv_fields else None,
            show_edges=True,
            copy_mesh=False,
        )
        self.plotter.reset_camera()

        # All Trame state variables - drives UI reactivity
        self.state.update({
            "mode": "convergence",  # active dataset section: "convergence" | "spp" | "ircadb"
            # --- Convergence state ---
            "conv_names": conv_names,
            "conv_name": initial_conv_name,
            "conv_fields": initial_conv_fields,
            "conv_field": initial_conv_fields[0] if initial_conv_fields else None,
            "conv_step": 1,
            "conv_num_steps": initial_conv_meta["n_steps"],
            "conv_times": initial_conv_times,
            "conv_time_label": _format_time(initial_conv_times[1] if len(initial_conv_times) > 1 else 0),
            # --- SPP state ---
            "spp_names": spp_names,
            "spp_name": initial_spp_name,
            "spp_fields": initial_spp_fields,
            "spp_field": initial_spp_fields[0] if initial_spp_fields else None,
            "spp_step": 0,
            "spp_num_steps": initial_spp_meta["n_steps"],
            "spp_times": initial_spp_times,
            "spp_time_label": _format_time(initial_spp_times[0] if initial_spp_times else 0),
            # --- IRCADb state ---
            "patient_names": [f"Patient {p}" for p in IRCADB_PATIENTS],
            "patient_name": f"Patient {initial_patient}" if initial_patient else "",
            # --- WebXR state ---
            "xr_active": False,  # toggled by VtkWebXRHelper enter/exit callbacks
        })

    def _reset_xr_state(self, **_: object) -> None:
        """Reset XR state on client connect; browser never preserves an XR session across refreshes."""
        self.state.xr_active = False

    # ---- Redraw helpers ----
    # Each helper clears the plotter, loads the requested mesh, and pushes
    # the updated render to the browser via ctrl.view_update().

    def _redraw_convergence(self, name: str, field: str | None, step: int) -> None:
        """Load and render a convergence mesh at the given step and field."""
        path = CONVERGENCE_FILES.get(name)
        if path is None or not path.exists():
            logger.error(f"Convergence file not found: {path}")
            return
        meta = self._convergence_meta[name]
        step = max(1, min(step, meta["n_steps"] - 1))
        try:
            new_mesh = load_mesh(path, step=step)
        except Exception as e:
            logger.error(f"Failed to load '{path.name}' step {step}: {e}")
            return
        self.plotter.clear()
        self.pvmesh = new_mesh
        self.plotter.add_mesh(self.pvmesh, scalars=field, show_edges=True, copy_mesh=False)
        self.plotter.reset_camera()
        self.ctrl.view_push_camera()
        self.ctrl.view_update()

    def _redraw_spp(self, name: str, field: str | None, step: int) -> None:
        """Load and render an SPP FEMVis mesh at the given step and field."""
        path = SPP_FILES.get(name)
        if path is None or not path.exists():
            logger.error(f"SPP file not found: {path}")
            return
        meta = self._spp_meta[name]
        step = max(0, min(step, meta["n_steps"] - 1))
        try:
            new_mesh = load_mesh(path, step=step)
        except Exception as e:
            logger.error(f"Failed to load '{path.name}' step {step}: {e}")
            return
        self.plotter.clear()
        self.pvmesh = new_mesh
        self.plotter.add_mesh(self.pvmesh, scalars=field, show_edges=True, copy_mesh=False)
        self.plotter.reset_camera()
        self.ctrl.view_push_camera()
        self.ctrl.view_update()

    def _redraw_ircadb(self, patient_name: str, opacity: float = 0.5) -> None:
        """Load all organ meshes for a patient and render them with distinct colors."""
        if not patient_name:
            return
        try:
            patient = int(patient_name.split()[-1])
        except ValueError:
            logger.error(f"Cannot parse patient number from '{patient_name}'")
            return
        organs = _ircadb_organ_names(patient)
        self.plotter.clear()
        # Add each organ as a separate actor; missing files are skipped with a warning
        for i, organ in enumerate(organs):
            vtk_path = _ircadb_vtk_path(patient, organ)
            if not vtk_path.exists():
                logger.warning(f"Organ file not found: {vtk_path}, skipping.")
                continue
            try:
                mesh = load_mesh(vtk_path)
                self.plotter.add_mesh(
                    mesh,
                    color=_ORGAN_COLORS[i % len(_ORGAN_COLORS)],
                    opacity=opacity,
                    show_edges=False,
                    name=organ,
                    copy_mesh=False,
                )
            except Exception as e:
                logger.error(f"Failed to load '{vtk_path.name}': {e}")
        self.plotter.reset_camera()
        self.ctrl.view_push_camera()
        self.ctrl.view_update()

    # ---- Button handlers ----
    # Called by the "Load" buttons in the drawer; set mode and trigger a redraw.

    def activate_convergence(self) -> None:
        """Switch to convergence mode and redraw with current UI state."""
        self.state.mode = "convergence"
        name = self.state.conv_name
        meta = self._convergence_meta.get(name)
        if meta is None:
            return
        self.state.conv_num_steps = meta["n_steps"]
        self.state.conv_times = meta["times"]
        step = max(1, min(int(self.state.conv_step), meta["n_steps"] - 1))
        self.state.conv_step = step
        self.state.conv_time_label = _format_time(meta["times"][step])
        fields = _all_fields(meta)
        self.state.conv_fields = fields
        current = self.state.conv_field
        self.state.conv_field = current if current in fields else (fields[0] if fields else None)
        self._redraw_convergence(name, self.state.conv_field, step)

    def activate_spp(self) -> None:
        """Switch to SPP mode and redraw with current UI state."""
        self.state.mode = "spp"
        name = self.state.spp_name
        meta = self._spp_meta.get(name)
        if meta is None:
            return
        self.state.spp_num_steps = meta["n_steps"]
        self.state.spp_times = meta["times"]
        step = max(0, min(int(self.state.spp_step), meta["n_steps"] - 1))
        self.state.spp_step = step
        self.state.spp_time_label = _format_time(meta["times"][step])
        fields = _all_fields(meta)
        self.state.spp_fields = fields
        current = self.state.spp_field
        self.state.spp_field = current if current in fields else (fields[0] if fields else None)
        self._redraw_spp(name, self.state.spp_field, step)

    def activate_ircadb(self) -> None:
        """Switch to IRCADb mode and redraw the selected patient."""
        self.state.mode = "ircadb"
        self._redraw_ircadb(self.state.patient_name)

    # ---- WebXR handlers ----

    def _on_enter_xr(self) -> None:
        """Called by VtkWebXRHelper when the XR session starts."""
        self.state.xr_active = True

    def _on_exit_xr(self) -> None:
        """Called by VtkWebXRHelper when the XR session ends."""
        self.state.xr_active = False
        self.ctrl.view_update()

    def toggle_xr(self) -> None:
        """Toggle WebXR session on/off; session type is HMD (headset) VR."""
        if self.state.xr_active:
            self.ctrl.stop_xr()
        else:
            self.ctrl.start_xr(VtkWebXRHelper.XrSessionTypes.HmdVR)

    # ---- Reactive callbacks ----
    # Decorated with @change - fired automatically when the named state variable changes.
    # Mode guard at the top of each callback prevents cross-section redraws.

    @change("conv_name")
    def _on_conv_name_change(self, **_: object) -> None:
        """Update field list, step bounds, and redraw when the resolution is changed."""
        if self.state.mode != "convergence":
            return
        name = self.state.conv_name
        meta = self._convergence_meta.get(name)
        if meta is None:
            return
        self.state.conv_num_steps = meta["n_steps"]
        self.state.conv_times = meta["times"]
        step = max(1, min(int(self.state.conv_step), meta["n_steps"] - 1))
        self.state.conv_step = step
        self.state.conv_time_label = _format_time(meta["times"][step])
        fields = _all_fields(meta)
        self.state.conv_fields = fields
        current = self.state.conv_field
        self.state.conv_field = current if current in fields else (fields[0] if fields else None)
        self._redraw_convergence(name, self.state.conv_field, step)

    @change("conv_field", "conv_step")
    def _on_conv_field_or_step_change(self, **_: object) -> None:
        """Redraw and update the time label when field or timestep changes."""
        if self.state.mode != "convergence":
            return
        step = int(self.state.conv_step)
        meta = self._convergence_meta.get(self.state.conv_name)
        if meta and step < len(meta["times"]):
            self.state.conv_time_label = _format_time(meta["times"][step])
        self._redraw_convergence(self.state.conv_name, self.state.conv_field, step)

    @change("spp_name")
    def _on_spp_name_change(self, **_: object) -> None:
        """Update field list, step bounds, and redraw when the SPP file is changed."""
        if self.state.mode != "spp":
            return
        name = self.state.spp_name
        meta = self._spp_meta.get(name)
        if meta is None:
            return
        self.state.spp_num_steps = meta["n_steps"]
        self.state.spp_times = meta["times"]
        step = max(0, min(int(self.state.spp_step), meta["n_steps"] - 1))
        self.state.spp_step = step
        self.state.spp_time_label = _format_time(meta["times"][step])
        fields = _all_fields(meta)
        self.state.spp_fields = fields
        current = self.state.spp_field
        self.state.spp_field = current if current in fields else (fields[0] if fields else None)
        self._redraw_spp(name, self.state.spp_field, step)

    @change("spp_field", "spp_step")
    def _on_spp_field_or_step_change(self, **_: object) -> None:
        """Redraw and update the time label when SPP field or timestep changes."""
        if self.state.mode != "spp":
            return
        step = int(self.state.spp_step)
        meta = self._spp_meta.get(self.state.spp_name)
        if meta and step < len(meta["times"]):
            self.state.spp_time_label = _format_time(meta["times"][step])
        self._redraw_spp(self.state.spp_name, self.state.spp_field, step)

    @change("patient_name")
    def _on_patient_change(self, **_: object) -> None:
        """Redraw all organ meshes when the selected IRCADb patient changes."""
        if self.state.mode != "ircadb":
            return
        self._redraw_ircadb(self.state.patient_name)

    # ---- Camera ----

    def reset_camera(self) -> None:
        """Reset the camera to fit the current scene, then push to the browser."""
        self.plotter.reset_camera()
        self.ctrl.view_push_camera()
        self.ctrl.reset_camera()

    # ---- UI layout ----

    def _build_ui(self) -> None:
        """Construct the full Trame/Vuetify3 UI: drawer controls, toolbar, and VTK viewport."""
        with SinglePageWithDrawerLayout(self.server, theme="dark") as self.ui:
            self.ui.title.set_text("VisFEM")

            # --- Left drawer: dataset selector panels ---
            with self.ui.drawer as drawer:
                drawer.width = 280
                with v3.VContainer(classes="pa-4"):

                    # Convergence sixth section
                    v3.VListSubheader("Liver Lobule")
                    v3.VSelect(           # mesh resolution
                        v_model=("conv_name",),
                        items=("conv_names",),
                        density="compact",
                        hide_details=True,
                    )
                    v3.VSelect(           # scalar/vector field to color by
                        v_model=("conv_field",),
                        items=("conv_fields",),
                        label="Field",
                        density="compact",
                        hide_details=True,
                        classes="mt-2",
                    )
                    v3.VSlider(           # timestep slider
                        v_model=("conv_step",),
                        min=1,
                        max=("conv_num_steps - 1",),
                        step=1,
                        label="Step",
                        thumb_label=True,
                        density="compact",
                        hide_details=True,
                        classes="mt-2",
                    )
                    v3.VTextField(        # readonly display of the actual time value
                        model_value=("conv_time_label",),
                        label="Time",
                        density="compact",
                        hide_details=True,
                        readonly=True,
                        classes="mt-2",
                    )
                    v3.VBtn(
                        "Load",
                        block=True,
                        color="primary",
                        density="compact",
                        classes="mt-3",
                        click=self.activate_convergence,
                    )
                    v3.VDivider(classes="my-4")

                    # SPP FEMVis section
                    v3.VListSubheader("SPP FEMVis")
                    v3.VSelect(           # file selector (deformation / lobule / scan)
                        v_model=("spp_name",),
                        items=("spp_names",),
                        density="compact",
                        hide_details=True,
                    )
                    v3.VSelect(           # scalar/vector field
                        v_model=("spp_field",),
                        items=("spp_fields",),
                        label="Field",
                        density="compact",
                        hide_details=True,
                        classes="mt-2",
                    )
                    v3.VSlider(           # timestep slider
                        v_model=("spp_step",),
                        min=0,
                        max=("spp_num_steps - 1",),
                        step=1,
                        label="Step",
                        thumb_label=True,
                        density="compact",
                        hide_details=True,
                        classes="mt-2",
                    )
                    v3.VTextField(        # readonly display of the actual time value
                        model_value=("spp_time_label",),
                        label="Time",
                        density="compact",
                        hide_details=True,
                        readonly=True,
                        classes="mt-2",
                    )
                    v3.VBtn(
                        "Load",
                        block=True,
                        color="primary",
                        density="compact",
                        classes="mt-3",
                        click=self.activate_spp,
                    )
                    v3.VDivider(classes="my-4")

                    # IRCADb section (patient-level loading; organ list auto-discovered)
                    v3.VListSubheader("3D-IRCADb-01")
                    v3.VSelect(
                        v_model=("patient_name",),
                        items=("patient_names",),
                        density="compact",
                        hide_details=True,
                    )
                    v3.VBtn(
                        "Load",
                        block=True,
                        color="primary",
                        density="compact",
                        classes="mt-3",
                        click=self.activate_ircadb,
                    )

            # --- Top toolbar: camera reset, VR toggle ---
            with self.ui.toolbar:
                v3.VSpacer()
                v3.VBtn(icon="mdi-crop-free", click=self.reset_camera)
                v3.VBtn(icon="mdi-eye", click=self.toggle_xr)

            # --- Main content: VTK render viewport with embedded WebXR helper ---
            with self.ui.content:
                with v3.VContainer(fluid=True, classes="pa-0 fill-height"):
                    with VtkLocalView(self.plotter.render_window) as view:
                        # Register view controls so other methods can push updates
                        self.ctrl.reset_camera = view.reset_camera
                        self.ctrl.view_push_camera = view.push_camera
                        self.ctrl.view_update = view.update
                        # VtkWebXRHelper must be nested inside VtkLocalView
                        webxr_helper = VtkWebXRHelper(
                            draw_controllers_ray=True,
                            enter_xr=(self._on_enter_xr,),
                            exit_xr=(self._on_exit_xr,),
                        )
                        self.ctrl.start_xr = webxr_helper.start_xr
                        self.ctrl.stop_xr = webxr_helper.stop_xr


def main() -> None:
    """Entry point: instantiate and start the Trame server."""
    app = VisfemApp()
    app.server.start()


if __name__ == "__main__":
    main()