"""Centered controls bar UI fragment for VisFEM."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3

_BAR_STYLE = (
    "dark_mode ? "
    "'position:absolute; top:12px; left:50%; transform:translateX(-50%); "
    "z-index:10; display:flex; align-items:center; gap:8px; height:38px; "
    "background:rgba(28,35,35,0.88); backdrop-filter:blur(8px); "
    "-webkit-backdrop-filter:blur(8px); border:1px solid rgba(255,255,255,0.07); "
    "border-radius:8px; padding:0 12px; width:270px;' "
    ": "
    "'position:absolute; top:12px; left:50%; transform:translateX(-50%); "
    "z-index:10; display:flex; align-items:center; gap:8px; height:38px; "
    "background:rgba(240,244,244,0.92); backdrop-filter:blur(8px); "
    "-webkit-backdrop-filter:blur(8px); border:1px solid rgba(0,0,0,0.08); "
    "border-radius:8px; padding:0 12px; width:270px;'",
)


def build_controls_bar(on_reset_camera: object) -> None:
    """Build the centered floating controls bar as a single unified pill."""
    with html.Div(style=_BAR_STYLE):

        # ---- Opacity icon ----
        v3.VIcon("mdi-circle-opacity", size="16", style="opacity:0.5; flex-shrink:0;")

        # ---- Opacity slider ----
        v3.VSlider(
            v_model=("ctrl_opacity", 0.8),
            min=0.0, max=1.0, step=0.1,
            density="compact", hide_details=True,
            color="#00897b", track_color="rgba(255,255,255,0.15)",
            thumb_label=False,
            style="flex:1; margin:0; padding:0; align-self:center;",
        )

        # ---- Divider ----
        html.Div(style="width:1px; height:20px; background:rgba(255,255,255,0.12); flex-shrink:0;")

        # ---- Camera reset ----
        with v3.VTooltip(text="Reset camera", location="bottom"):
            with v3.Template(v_slot_activator="{ props }"):
                v3.VBtn(
                    icon="mdi-crop-free",
                    variant="text", density="compact", size="small",
                    click=on_reset_camera, v_bind="props",
                )