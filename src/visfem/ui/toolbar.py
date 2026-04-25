"""Toolbar UI for VisFEM."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3
from visfem.ui.theme import ACCENT, FS_XL, FW_SEMI, GAP_LG, LS_NORMAL, SEP_DIM

# Thin vertical rule that visually separates the panel toggles from the center cluster.
_SEP_STYLE = (
    f"width:1px; height:18px; background:{SEP_DIM}; "
    f"margin:0 {GAP_LG}; align-self:center; flex-shrink:0;"
)


def build_toolbar(
    toggle_theme: object,
    toggle_xr: object,
    toggle_left_panel: object,
    toggle_right_panel: object,
    toggle_render_mode: object,
    take_screenshot: object,
) -> None:
    """Render toolbar: panel toggles, logo, render-mode, theme, VR, fullscreen, and screenshot buttons."""
    #  Left edge
    html.Div(style="width:15px;")

    with v3.VTooltip(text="Toggle data panel", location="bottom"):
        with v3.Template(v_slot_activator="{ props }"):
            v3.VBtn(
                icon="mdi-dock-left",
                variant="text", density="compact",
                click=toggle_left_panel,
                v_bind="props",
                style=("left_panel_open ? '' : 'opacity:0.35'",),
            )

    # Separator between left toggle and center cluster
    html.Span(style=_SEP_STYLE)

    #  Center: logo + title
    v3.VIcon("mdi-vector-triangle", color=ACCENT, size="20", classes="mr-2", style="align-self:center;")
    html.Span("VisFEM", style=f"font-size:{FS_XL}; font-weight:{FW_SEMI}; letter-spacing:{LS_NORMAL}; line-height:1;")
    v3.VSpacer()

    #  Right cluster: render mode + theme + VR
    with v3.VTooltip(
        text=("render_mode === 'local' ? 'Local rendering (browser)' : 'Server rendering (remote)'",),
        location="bottom",
    ):
        with v3.Template(v_slot_activator="{ props }"):
            v3.VBtn(
                icon=("render_mode === 'local' ? 'mdi-monitor' : 'mdi-server'",),
                variant="text", density="compact",
                click=toggle_render_mode, v_bind="props", classes="ml-2",
                style=("render_mode === 'remote' ? 'color: var(--v-theme-primary)' : ''",),
            )

    with v3.VTooltip(text="Toggle theme", location="bottom"):
        with v3.Template(v_slot_activator="{ props }"):
            v3.VBtn(
                icon=("dark_mode ? 'mdi-weather-sunny' : 'mdi-weather-night'",),
                variant="text", density="compact",
                click=toggle_theme, v_bind="props", classes="ml-2",
            )

    with v3.VTooltip(text=("xr_active ? 'Exit VR' : 'Enter VR'",), location="bottom"):
        with v3.Template(v_slot_activator="{ props }"):
            v3.VBtn(
                icon="mdi-virtual-reality", variant="text", density="compact",
                click=toggle_xr, v_bind="props", classes="ml-2",
                style=("xr_active ? 'color: var(--v-theme-primary)' : ''",),
            )

    with v3.VTooltip(text="Toggle fullscreen", location="bottom"):
        with v3.Template(v_slot_activator="{ props }"):
            v3.VBtn(
                icon=("fullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'",),
                variant="text", density="compact",
                click=(
                    "fullscreen = !fullscreen; "
                    "fullscreen "
                    "? $event.currentTarget.ownerDocument.documentElement.requestFullscreen() "
                    ": $event.currentTarget.ownerDocument.exitFullscreen()"
                ),
                v_bind="props", classes="ml-2",
            )

    with v3.VTooltip(text="Save screenshot", location="bottom"):
        with v3.Template(v_slot_activator="{ props }"):
            v3.VBtn(
                icon="mdi-camera-outline",
                variant="text", density="compact",
                click=take_screenshot, v_bind="props", classes="ml-2",
                disabled=("active_dataset === null",),
            )

    # Separator between center cluster and right toggle
    html.Span(style=_SEP_STYLE)

    with v3.VTooltip(text="Toggle controls panel", location="bottom"):
        with v3.Template(v_slot_activator="{ props }"):
            v3.VBtn(
                icon="mdi-dock-right",
                variant="text", density="compact",
                click=toggle_right_panel,
                v_bind="props",
                style=("right_panel_open ? '' : 'opacity:0.35'",),
            )

    #  Right edge ─
    html.Div(style="width:15px;")
