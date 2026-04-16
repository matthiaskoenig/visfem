"""Top-level UI assembly for VisFEM."""

from typing import Any

import pyvista as pv
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import html
from trame.widgets.vtk import VtkLocalView, VtkWebXRHelper

from visfem.models import ProjectMetadata
from visfem.ui.footer import FOOTER_STYLE, build_footer
from visfem.ui.left_panel import build_left_panel
from visfem.ui.right_panel import build_right_panel
from visfem.ui.toolbar import build_toolbar
from visfem.ui.theme import LEFT_PANEL_WIDTH, RIGHT_PANEL_WIDTH


def build_ui(
    server: object,
    plotter: pv.Plotter,
    ctrl: Any,
    organ_groups: dict[str, list[tuple[str, ProjectMetadata]]],
    patients_by_dataset: dict[str, list[int]],
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

        layout.footer.clear()
        with layout.footer as footer:
            footer.style = FOOTER_STYLE
            build_footer()

        with layout.content:
            with html.Div(
                style=(
                    "display:flex; "
                    "height:calc(100vh - var(--v-layout-top, 0px) - var(--v-layout-bottom, 0px)); "
                    "overflow:hidden;"
                )
            ):

                # ---- Left panel ----
                with html.Div(
                    style=(
                        f"'flex-shrink:0; height:100%; overflow:hidden; "
                        "display:flex; flex-direction:column; "
                        "transition:width 0.22s ease; ' + "
                        f"(left_panel_open ? 'width:{LEFT_PANEL_WIDTH}; "
                        "border-right:1px solid rgba(var(--v-border-color), var(--v-border-opacity));' : 'width:0px;')",
                    ),
                ):
                    build_left_panel(
                        organ_groups,
                        patients_by_dataset,
                        on_select_dataset,
                        on_select_xdmf,
                        on_select_patient,
                    )

                # ---- VTK viewport (fills remaining space) ----
                # background-color matches the scene background so WebGL's framebuffer
                # clear during panel-resize transitions shows the right color, not black.
                with html.Div(
                    style=(
                        "'flex:1; min-width:0; height:100%; position:relative; "
                        "background-color:' + (dark_mode ? 'rgb(20,26,26)' : 'rgb(209,214,214)')",
                    ),
                ):
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
                    style=(
                        f"'flex-shrink:0; height:100%; overflow:hidden; "
                        "display:flex; flex-direction:column; "
                        "transition:width 0.22s ease; ' + "
                        f"(right_panel_open ? 'width:{RIGHT_PANEL_WIDTH}; "
                        "border-left:1px solid rgba(var(--v-border-color), var(--v-border-opacity));' : 'width:0px;')",
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
