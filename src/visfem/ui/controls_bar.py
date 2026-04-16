"""Centered controls bar UI fragment for VisFEM."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3
from visfem.ui.theme import (
    ACCENT, TRACK_DARK,
    DIVIDER_STYLE, SWATCH_STYLE, GRADIENT_SWATCH_STYLE,
    FS_MD4,
    Z_PANEL, RADIUS_SM,
    CONTROLS_BAR_HEIGHT, CONTROLS_BAR_TOP, CONTROLS_BAR_GAP, PANEL_PADDING,
    glass_panel_styles,
)

_BAR_POS = (
    f"position:absolute; top:{CONTROLS_BAR_TOP}; left:50%; transform:translateX(-50%); "
    f"z-index:{Z_PANEL}; display:flex; align-items:center; gap:{CONTROLS_BAR_GAP}; "
    f"height:{CONTROLS_BAR_HEIGHT}; border-radius:{RADIUS_SM}; padding:{PANEL_PADDING};"
)
_BAR_DARK, _BAR_LIGHT = glass_panel_styles(_BAR_POS)
_BAR_STYLE = (
    f"(dark_mode ? '{_BAR_DARK}' : '{_BAR_LIGHT}')"
    " + 'width:'"
    " + ((available_scalar_fields && available_scalar_fields.length > 1)"
    "    ? (active_dataset === 'heart' ? '480px' : '410px')"
    "    : (active_dataset === 'heart' ? '410px' : '340px'))"
    " + ';'",
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
            color=ACCENT, track_color=TRACK_DARK,
            thumb_label=False,
            disabled=("autoplay",),
            style="flex:1; min-width:120px; margin:0; padding:0; align-self:center;",
        )

        # ---- Divider ----
        html.Div(style=DIVIDER_STYLE)

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
            style=DIVIDER_STYLE,
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
            style=DIVIDER_STYLE,
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
                        active_color=ACCENT,
                    ):
                        with v3.Template(v_slot_title=""):
                            html.Span(
                                "{{ field.label }}",
                                style=f"font-size:{FS_MD4};",
                            )

        # ---- Color palette / colormap picker (always visible) ----
        html.Div(style=DIVIDER_STYLE)
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
                        active_color=ACCENT,
                    ):
                        with v3.Template(v_slot_title=""):
                            with html.Div(
                                style="display:flex; align-items:center; gap:6px;",
                            ):
                                html.Span(
                                    "{{ palette.label }}",
                                    style=f"font-size:{FS_MD4}; min-width:52px;",
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
                                                f"'{SWATCH_STYLE} background:' + swatch + ';'",
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
                        active_color=ACCENT,
                    ):
                        with v3.Template(v_slot_title=""):
                            with html.Div(
                                style="display:flex; align-items:center; gap:6px;",
                            ):
                                html.Span(
                                    "{{ cmap.label }}",
                                    style=f"font-size:{FS_MD4}; min-width:52px;",
                                )
                                html.Div(
                                    style=(
                                        f"'{GRADIENT_SWATCH_STYLE} background:' + cmap.gradient + ';'",
                                    ),
                                )
