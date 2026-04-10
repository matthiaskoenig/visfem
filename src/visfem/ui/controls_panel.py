"""Controls panel UI fragment for VisFEM."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3


def build_controls_panel() -> None:
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