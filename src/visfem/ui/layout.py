"""Top-level UI assembly for VisFEM."""

from typing import Any

import pyvista as pv
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import html
from trame.widgets.vtk import VtkLocalView, VtkWebXRHelper

from visfem.models import ProjectMetadata
from visfem.ui.left_panel import build_left_panel
from visfem.ui.right_panel import build_right_panel
from visfem.ui.toolbar import build_toolbar
from visfem.ui.theme import LEFT_PANEL_WIDTH, RIGHT_PANEL_WIDTH


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
    on_select_color_scheme: object,
    on_toggle_autoplay: object,
    on_toggle_theme: object,
    on_reset_camera: object,
    on_toggle_xr: object,
    on_enter_xr: object,
    on_exit_xr: object,
    on_toggle_left_panel: object,
    on_toggle_right_panel: object,
) -> SinglePageLayout:
    """Assemble the full SinglePageLayout and return it."""
    with SinglePageLayout(server, theme=("dark_mode ? 'dark' : 'light'",)) as layout:
        layout.title.hide()
        layout.icon.hide()

        with layout.toolbar as toolbar:
            toolbar.density = "compact"
            toolbar.style = "background-color: color-mix(in srgb, rgb(var(--v-theme-surface)) 88%, black 12%);"
            toolbar.elevation = 0
            build_toolbar(on_toggle_theme, on_toggle_xr, on_toggle_left_panel, on_toggle_right_panel)

        with layout.content:
            # Flex row: [left panel] | [vtk view] | [right panel]
            # height uses Vuetify's --v-layout-top variable (toolbar offset) so the
            # container is always exactly viewport-height minus the toolbar — independent
            # of content, which keeps panels scrollable and prevents page extension.
            with html.Div(
                style="display:flex; height:calc(100vh - var(--v-layout-top, 0px)); overflow:hidden;"
            ):

                # ---- Left panel ----
                with html.Div(
                    v_show="left_panel_open",
                    style=(
                        f"width:{LEFT_PANEL_WIDTH}; flex-shrink:0; "
                        "height:100%; overflow:hidden; "
                        "display:flex; flex-direction:column; "
                        "border-right:1px solid rgba(var(--v-border-color), var(--v-border-opacity));"
                    ),
                ):
                    build_left_panel(
                        organ_groups,
                        ircadb_patients,
                        on_select_dataset,
                        on_select_xdmf,
                        on_select_patient,
                    )

                # ---- VTK viewport (fills remaining space) ----
                with html.Div(style="flex:1; min-width:0; height:100%; position:relative;"):
                    with VtkLocalView(
                        plotter.render_window, ref="view", camera="camera"
                    ) as view:
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

                # ---- Right panel ----
                with html.Div(
                    v_show="right_panel_open",
                    style=(
                        f"width:{RIGHT_PANEL_WIDTH}; flex-shrink:0; "
                        "height:100%; overflow:hidden; "
                        "display:flex; flex-direction:column; "
                        "border-left:1px solid rgba(var(--v-border-color), var(--v-border-opacity));"
                    ),
                ):
                    build_right_panel(
                        on_reset_camera,
                        on_select_scalar_field,
                        on_select_color_scheme,
                        on_select_step,
                        on_toggle_autoplay,
                    )

    return layout
