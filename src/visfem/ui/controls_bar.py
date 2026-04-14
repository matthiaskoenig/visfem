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
_BAR_STYLE = (
    f"(dark_mode ? '{_BAR_BASE_DARK}' : '{_BAR_BASE_LIGHT}')"
    " + 'width:'"
    " + ((available_scalar_fields && available_scalar_fields.length > 1)"
    "    ? (active_dataset === 'heart' ? '480px' : '410px')"
    "    : (active_dataset === 'heart' ? '410px' : '340px'))"
    " + ';'",
)

_DIVIDER_STYLE = "width:1px; height:20px; background:rgba(255,255,255,0.12); flex-shrink:0;"

# Swatch dot shown in the palette/colormap menu items.
_SWATCH_STYLE = (
    "display:inline-block; width:10px; height:10px; "
    "border-radius:50%; flex-shrink:0;"
)
# Gradient strip shown in the colormap menu items.
_GRADIENT_STYLE = (
    "display:inline-block; width:60px; height:10px; "
    "border-radius:3px; flex-shrink:0;"
)


def build_controls_bar(
    on_reset_camera: object,
    on_select_scalar_field: object,
    on_select_color_scheme: object,
) -> None:
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

        # ---- Color palette / colormap picker (always visible) ----
        html.Div(style=_DIVIDER_STYLE)
        with v3.VMenu(location="bottom", max_height=280):
            with v3.Template(v_slot_activator="{ props }"):
                with v3.VTooltip(text="Color palette", location="bottom"):
                    with v3.Template(v_slot_activator="{ props: tProps }"):
                        v3.VBtn(
                            icon="mdi-palette-outline",
                            variant="text", density="compact", size="small",
                            disabled=("active_dataset === null",),
                            v_bind="{ ...props, ...tProps }",
                        )

            # ---- Categorical palette options (shown when no scalar_bar is active) ----
            with v3.VList(
                density="compact", nav=True,
                v_if="scalar_bar === null || scalar_bar === undefined",
            ):
                with html.Div(
                    v_for="palette in categorical_palette_meta",
                    key="palette.name",
                ):
                    with v3.VListItem(
                        density="compact",
                        click=(on_select_color_scheme, "[palette.name]"),
                        active=("active_categorical_palette === palette.name",),
                        active_color="#00897b",
                    ):
                        with v3.Template(v_slot_title=""):
                            with html.Div(
                                style="display:flex; align-items:center; gap:6px;",
                            ):
                                html.Span(
                                    "{{ palette.label }}",
                                    style="font-size:0.82rem; min-width:52px;",
                                )
                                with html.Div(
                                    style="display:flex; gap:3px;",
                                ):
                                    with html.Div(
                                        v_for="(swatch, i) in palette.swatches",
                                        key="i",
                                    ):
                                        html.Div(
                                            style=(
                                                f"'{_SWATCH_STYLE} background:' + swatch + ';'",
                                            ),
                                        )

            # ---- Continuous colormap options (shown when scalar_bar is active) ----
            with v3.VList(
                density="compact", nav=True,
                v_if="scalar_bar !== null && scalar_bar !== undefined",
            ):
                with html.Div(
                    v_for="cmap in continuous_cmap_meta",
                    key="cmap.name",
                ):
                    with v3.VListItem(
                        density="compact",
                        click=(on_select_color_scheme, "[cmap.name]"),
                        active=("active_continuous_cmap === cmap.name",),
                        active_color="#00897b",
                    ):
                        with v3.Template(v_slot_title=""):
                            with html.Div(
                                style="display:flex; align-items:center; gap:6px;",
                            ):
                                html.Span(
                                    "{{ cmap.label }}",
                                    style="font-size:0.82rem; min-width:52px;",
                                )
                                html.Div(
                                    style=(
                                        f"'{_GRADIENT_STYLE} background:' + cmap.gradient + ';'",
                                    ),
                                )
