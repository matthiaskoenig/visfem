"""Top-level UI assembly for VisFEM."""

from typing import Any

import pyvista as pv
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import html
from trame.widgets import vuetify3 as v3
from trame.widgets.vtk import VtkRemoteLocalView, VtkWebXRHelper
from trame_client.widgets.trame import Script

from visfem.models import ProjectMetadata
from visfem.ui.footer import FOOTER_STYLE, build_footer
from visfem.ui.left_panel import build_left_panel
from visfem.ui.right_panel import build_right_panel
from visfem.ui.toolbar import build_toolbar
from visfem.ui.theme import ACCENT, BG_DARK, BG_LIGHT, LEFT_PANEL_WIDTH, PAD_LG, RIGHT_PANEL_WIDTH


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
    on_toggle_color_reversed: object,
    on_toggle_autoplay: object,
    on_toggle_theme: object,
    on_reset_camera: object,
    on_toggle_xr: object,
    on_enter_xr: object,
    on_exit_xr: object,
    on_toggle_left_panel: object,
    on_toggle_right_panel: object,
    on_toggle_render_mode: object,
    on_take_screenshot: object,
) -> SinglePageLayout:
    """Assemble the full SinglePageLayout and return it."""
    with SinglePageLayout(server, theme=("dark_mode ? 'dark' : 'light'",)) as layout:
        layout.title.hide()
        layout.icon.hide()

        with layout.toolbar as toolbar:
            toolbar.density = "compact"
            toolbar.style = "background-color: color-mix(in srgb, rgb(var(--v-theme-surface)) 88%, black 12%);"
            toolbar.elevation = 0
            build_toolbar(on_toggle_theme, on_toggle_xr, on_toggle_left_panel, on_toggle_right_panel, on_toggle_render_mode, on_take_screenshot)
            v3.VProgressLinear(
                v_if="busy",
                indeterminate=True,
                color=ACCENT,
                height=2,
                style="position:absolute; bottom:0; left:0; right:0; z-index:20;",
            )

        layout.footer.clear()
        with layout.footer as footer:
            footer.style = FOOTER_STYLE
            build_footer()

        Script(
            "document.addEventListener('fullscreenchange', function() {"
            "  if (window.trame && window.trame.state) {"
            "    window.trame.state.set('fullscreen', !!document.fullscreenElement);"
            "  }"
            "});"
        )
        Script(
            "if (navigator.xr) {"
            "  var _origReq = navigator.xr.requestSession.bind(navigator.xr);"
            "  navigator.xr.requestSession = function(mode, opts) {"
            "    return _origReq(mode, opts).then(function(session) {"
            "      session.addEventListener('end', function() {"
            "        location.reload();"
            "      });"
            "      return session;"
            "    });"
            "  };"
            "}"
        )

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
                        f"(xr_active || !left_panel_open ? 'width:0px;' : 'width:{LEFT_PANEL_WIDTH}; "
                        "border-right:1px solid rgba(var(--v-border-color), var(--v-border-opacity));')",
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
                with html.Div(
                    style=(
                        f"'flex:1; min-width:0; height:100%; position:relative; "
                        f"background-color:' + (dark_mode ? '{BG_DARK}' : '{BG_LIGHT}')",
                    ),
                ):
                    with VtkRemoteLocalView(
                        plotter.render_window,
                        namespace="view",
                        mode=("render_mode", "local"),
                        ref="view",
                        camera="camera",
                        still_quality=100,
                        interactive_quality=100,
                        disable_auto_switch=True,
                        on_local_image_capture="utils.download(`screenshot_${new Date().toISOString().slice(0,19).replace(/[T:]/g,'-')}.png`, $event)",
                    ) as view:
                        ctrl.reset_camera = view.reset_camera
                        ctrl.view_push_camera = view.push_camera
                        ctrl.view_update = view.update
                        ctrl.capture_screenshot = view.capture_image
                        webxr_helper = VtkWebXRHelper(
                            draw_controllers_ray=True,
                            enter_xr=(on_enter_xr,),
                            exit_xr=(on_exit_xr,),
                        )
                        ctrl.start_xr = webxr_helper.start_xr
                        ctrl.stop_xr = webxr_helper.stop_xr

                    with html.Div(
                        v_if="loading",
                        style=(
                            "position:absolute; inset:0; z-index:10; "
                            f"display:flex; flex-direction:column; align-items:center; justify-content:center; gap:{PAD_LG}; "
                            "background:rgba(0,0,0,0.35);"
                        ),
                    ):
                        v3.VProgressCircular(indeterminate=True, color=ACCENT, size="36", width="2")
                        html.Span(
                            "Loading",
                            style="font-size:0.7rem; letter-spacing:0.12em; text-transform:uppercase; opacity:0.5;",
                        )

                # ---- Right panel ----
                with html.Div(
                    style=(
                        f"'flex-shrink:0; height:100%; overflow:hidden; "
                        "display:flex; flex-direction:column; "
                        "transition:width 0.22s ease; ' + "
                        f"(xr_active || !right_panel_open ? 'width:0px;' : 'width:{RIGHT_PANEL_WIDTH}; "
                        "border-left:1px solid rgba(var(--v-border-color), var(--v-border-opacity));')",
                    ),
                ):
                    build_right_panel(
                        on_reset_camera,
                        on_select_scalar_field,
                        on_select_color_scheme,
                        on_toggle_color_reversed,
                        on_select_step,
                        on_toggle_autoplay,
                    )

    return layout
