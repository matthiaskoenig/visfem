"""Toolbar UI for VisFEM."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3


def build_toolbar(
    toggle_theme: object,
    toggle_xr: object,
) -> None:
    """Build the main toolbar with theme and VR buttons."""
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
                click=toggle_theme, v_bind="props", classes="ml-3",
            )
    with v3.VTooltip(text="Toggle VR", location="bottom"):
        with v3.Template(v_slot_activator="{ props }"):
            v3.VBtn(
                icon="mdi-virtual-reality", variant="text", density="compact",
                click=toggle_xr, v_bind="props", classes="ml-3",
            )
    html.Div(style="width: 15px;")