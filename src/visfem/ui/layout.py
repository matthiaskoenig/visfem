"""Top-level UI assembly for VisFEM."""
from typing import Any

import pyvista as pv
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import vuetify3 as v3
from trame.widgets.vtk import VtkLocalView, VtkWebXRHelper

from visfem.models import ProjectMetadata
from visfem.ui.controls_bar import build_controls_bar
from visfem.ui.dataset_panel import build_dataset_panel
from visfem.ui.toolbar import build_toolbar
from visfem.ui.info_panel import build_info_panel
from visfem.ui.scalar_bar import build_scalar_bar


def build_ui(
    server: object,
    plotter: pv.Plotter,
    ctrl: Any,
    organ_groups: dict[str, list[tuple[str, ProjectMetadata]]],
    ircadb_patients: list[int],
    on_select_dataset: object,
    on_select_xdmf: object,
    on_select_patient: object,
    on_select_scalar_field: object,
    on_select_step: object,
    on_toggle_autoplay: object,
    on_toggle_theme: object,
    on_reset_camera: object,
    on_toggle_xr: object,
    on_enter_xr: object,
    on_exit_xr: object,
) -> SinglePageLayout:
    """Assemble the full SinglePageLayout and return it."""
    with SinglePageLayout(server, theme=("dark_mode ? 'dark' : 'light'",)) as layout:
        layout.title.hide()
        layout.icon.hide()

        with layout.toolbar as toolbar:
            toolbar.density = "compact"
            build_toolbar(on_toggle_theme, on_toggle_xr)

        with layout.content:
            with v3.VContainer(fluid=True, classes="pa-0 fill-height", style="position: relative;"):
                with VtkLocalView(plotter.render_window, ref="view", camera="camera") as view:
                    ctrl.reset_camera = view.reset_camera  
                    ctrl.view_push_camera = view.push_camera  
                    ctrl.view_update = view.update  
                    webxr_helper = VtkWebXRHelper(
                        draw_controllers_ray=True,
                        enter_xr=(on_enter_xr,),
                        exit_xr=(on_exit_xr,),
                    )
                    ctrl.start_xr = webxr_helper.start_xr  
                    ctrl.stop_xr = webxr_helper.stop_xr  

                build_dataset_panel(
                    organ_groups, ircadb_patients,
                    on_select_dataset, on_select_xdmf, on_select_patient,
                )
                build_controls_bar(on_reset_camera, on_select_scalar_field)
                build_info_panel()
                build_scalar_bar(on_select_step, on_toggle_autoplay)

    return layout