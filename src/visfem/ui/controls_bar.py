"""Centered controls bar UI fragment for VisFEM."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3

_BAR_BASE_DARK = (
    "position:absolute; top:12px; left:50%; transform:translateX(-50%); "
    "z-index:10; display:flex; align-items:center; gap:8px; height:38px; "
    "background:rgba(28,35,35,0.88); backdrop-filter:blur(8px); "
    "-webkit-backdrop-filter:blur(8px); border:1px solid rgba(255,255,255,0.07); "
    "border-radius:8px; padding:0 12px;"
)
_BAR_BASE_LIGHT = (
    "position:absolute; top:12px; left:50%; transform:translateX(-50%); "
    "z-index:10; display:flex; align-items:center; gap:8px; height:38px; "
    "background:rgba(240,244,244,0.92); backdrop-filter:blur(8px); "
    "-webkit-backdrop-filter:blur(8px); border:1px solid rgba(0,0,0,0.08); "
    "border-radius:8px; padding:0 12px;"
)
# Explicit fixed width to avoid triggering ResizeObserver loops from dynamic relayout.
# 270px base → +70px for heart fiber toggle → +70px for field selector.
_BAR_STYLE = (
    f"(dark_mode ? '{_BAR_BASE_DARK}' : '{_BAR_BASE_LIGHT}')"
    " + 'width:'"
    " + ((available_scalar_fields && available_scalar_fields.length > 1)"
    "    ? (active_dataset === 'heart' ? '410px' : '340px')"
    "    : (active_dataset === 'heart' ? '340px' : '270px'))"
    " + ';'",
)

_DIVIDER_STYLE = "width:1px; height:20px; background:rgba(255,255,255,0.12); flex-shrink:0;"


def build_controls_bar(on_reset_camera: object, on_select_scalar_field: object) -> None:
    """Build the centered floating controls bar as a single unified pill."""
    with html.Div(style=_BAR_STYLE):

        # ---- Opacity icon ----
        v3.VIcon("mdi-circle-opacity", size="16", style="opacity:0.5; flex-shrink:0;")

        # ---- Opacity slider (disabled during autoplay to avoid race conditions) ----
        v3.VSlider(
            v_model=("ctrl_opacity", 0.9),
            min=0.0, max=1.0, step=0.1,
            density="compact", hide_details=True,
            color="#00897b", track_color="rgba(255,255,255,0.15)",
            thumb_label=False,
            disabled=("autoplay",),
            style="flex:1; min-width:120px; margin:0; padding:0; align-self:center;",
        )

        # ---- Divider ----
        html.Div(style=_DIVIDER_STYLE)

        # ---- Camera reset ----
        with v3.VTooltip(text="Reset camera", location="bottom"):
            with v3.Template(v_slot_activator="{ props }"):
                v3.VBtn(
                    icon="mdi-camera-retake-outline",
                    variant="text", density="compact", size="small",
                    click=on_reset_camera, v_bind="props",
                )

        # ---- Fiber toggle (heart dataset only) ----
        html.Div(
            style=_DIVIDER_STYLE,
            v_if="active_dataset === 'heart'",
        )
        with v3.VTooltip(
            text=("show_fibers ? 'Hide fiber glyphs' : 'Show fiber glyphs'",),
            location="bottom",
            v_if="active_dataset === 'heart'",
        ):
            with v3.Template(v_slot_activator="{ props }"):
                v3.VBtn(
                    icon="mdi-grain",
                    variant=("show_fibers ? 'tonal' : 'text'",),
                    density="compact", size="small",
                    click="show_fibers = !show_fibers",
                    v_bind="props",
                )

        # ---- Scalar field selector (datasets with ≥2 selectable fields) ----
        html.Div(
            style=_DIVIDER_STYLE,
            v_if="available_scalar_fields && available_scalar_fields.length > 1",
        )
        with v3.VMenu(
            v_if="available_scalar_fields && available_scalar_fields.length > 1",
            location="bottom",
            max_height=280,
        ):
            with v3.Template(v_slot_activator="{ props }"):
                with v3.VTooltip(text="Select scalar field", location="bottom"):
                    with v3.Template(v_slot_activator="{ props: tProps }"):
                        v3.VBtn(
                            icon="mdi-layers-outline",
                            variant="text", density="compact", size="small",
                            v_bind="{ ...props, ...tProps }",
                        )
            with v3.VList(density="compact", nav=True):
                with html.Div(
                    v_for="field in available_scalar_fields",
                    key="field.name",
                ):
                    with v3.VListItem(
                        density="compact",
                        click=(on_select_scalar_field, "[field.name]"),
                        active=("active_scalar_field === field.name",),
                        active_color="#00897b",
                    ):
                        with v3.Template(v_slot_title=""):
                            html.Span(
                                "{{ field.label }}",
                                style="font-size:0.82rem;",
                            )
