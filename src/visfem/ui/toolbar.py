"""Toolbar UI for VisFEM."""

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visfem.ui.theme import ACCENT, FS_XL, FW_SEMI, GAP_LG, LS_NORMAL, SEP_DIM
from visfem.ui.widgets import icon_button

_SEP_STYLE = (
    f"width:1px; height:20px; background:{SEP_DIM}; "
    f"margin:0 {GAP_LG}; align-self:center; flex-shrink:0;"
)


def build_toolbar(
    toggle_theme: object,
    toggle_xr: object,
    toggle_left_panel: object,
    toggle_right_panel: object,
    take_screenshot: object,
) -> None:
    """Render toolbar: [left-toggle] | VisFEM ··· [theme][fullscreen][screenshot] | [VR] | [right-toggle]."""
    html.Div(style="width:15px;")

    icon_button(
        "Toggle data panel",
        icon="mdi-dock-left",
        click=toggle_left_panel,
        style=("left_panel_open ? '' : 'opacity:0.35'",),
    )

    html.Span(style=_SEP_STYLE)

    v3.VIcon(
        "mdi-vector-triangle",
        color=ACCENT,
        size="20",
        classes="mr-2",
        style="align-self:center;",
    )
    html.Span(
        "VisFEM",
        style=f"font-size:{FS_XL}; font-weight:{FW_SEMI}; letter-spacing:{LS_NORMAL}; line-height:1;",
    )
    v3.VSpacer()

    icon_button(
        "Toggle theme",
        icon=("dark_mode ? 'mdi-weather-sunny' : 'mdi-weather-night'",),
        click=toggle_theme,
    )

    icon_button(
        "Toggle fullscreen",
        icon=("fullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'",),
        click=(
            "fullscreen = !fullscreen; "
            "fullscreen "
            "? $event.currentTarget.ownerDocument.documentElement.requestFullscreen() "
            ": $event.currentTarget.ownerDocument.exitFullscreen()"
        ),
        classes="ml-1",
    )

    icon_button(
        "Save screenshot",
        icon="mdi-camera-outline",
        click=take_screenshot,
        classes="ml-1",
    )

    html.Span(style=_SEP_STYLE)

    # VR/XR button disabled; uncomment to re-enable.
    # with v3.VTooltip(text=("xr_active ? 'Exit VR' : 'Enter VR'",), location="bottom"):
    #     with v3.Template(v_slot_activator="{ props }"):
    #         v3.VBtn(
    #             icon="mdi-virtual-reality",
    #             variant="text", density="compact",
    #             click=toggle_xr, v_bind="props",
    #             style=("xr_active ? 'color: var(--v-theme-primary)' : ''",),
    #         )
    #
    # html.Span(style=_SEP_STYLE)

    icon_button(
        "Toggle controls panel",
        icon="mdi-dock-right",
        click=toggle_right_panel,
        style=("right_panel_open ? '' : 'opacity:0.35'",),
    )

    html.Div(style="width:15px;")
