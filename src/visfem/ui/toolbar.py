"""Toolbar UI for VisFEM."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3
from visfem.ui.theme import ACCENT, FS_XL, FW_SEMI, LS_NORMAL


def build_toolbar(
    toggle_theme: object,
    toggle_xr: object,
    toggle_left_panel: object,
    toggle_right_panel: object,
) -> None:
    """Build the main toolbar with theme, VR, and panel toggle buttons."""
    v3.VProgressLinear(
        indeterminate=True, absolute=True, bottom=True,
        active=("trame__busy",), color=ACCENT, height=2,
    )

    html.Div(style="width:15px;")

    # ---- Left panel toggle ----
    with v3.VTooltip(text="Toggle data panel", location="bottom"):
        with v3.Template(v_slot_activator="{ props }"):
            v3.VBtn(
                icon="mdi-dock-left",
                variant="text", density="compact",
                click=toggle_left_panel,
                v_bind="props", classes="mr-1",
                style=("left_panel_open ? '' : 'opacity:0.35'",),
            )

    html.Div(style="width:8px;")
    v3.VIcon("mdi-vector-triangle", color=ACCENT, classes="mr-3")
    html.Span("VisFEM", style=f"font-size:{FS_XL}; font-weight:{FW_SEMI}; letter-spacing:{LS_NORMAL};")
    v3.VSpacer()

    with v3.VTooltip(text="Toggle theme", location="bottom"):
        with v3.Template(v_slot_activator="{ props }"):
            v3.VBtn(
                icon=("dark_mode ? 'mdi-weather-sunny' : 'mdi-weather-night'",),
                variant="text", density="compact",
                click=toggle_theme, v_bind="props", classes="ml-3",
            )

    # ---- Right panel toggle ----
    with v3.VTooltip(text="Toggle controls panel", location="bottom"):
        with v3.Template(v_slot_activator="{ props }"):
            v3.VBtn(
                icon="mdi-dock-right",
                variant="text", density="compact",
                click=toggle_right_panel,
                v_bind="props", classes="ml-3",
                style=("right_panel_open ? '' : 'opacity:0.35'",),
            )

    with v3.VTooltip(text="Toggle VR", location="bottom"):
        with v3.Template(v_slot_activator="{ props }"):
            v3.VBtn(
                icon="mdi-virtual-reality", variant="text", density="compact",
                click=toggle_xr, v_bind="props", classes="ml-3",
            )
    html.Div(style="width: 15px;")
