"""Right panel: all view controls (opacity, field, color, playback, scalar bar)."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visfem.ui.theme import (
    ACCENT, TRACK_DARK,
    SWATCH_STYLE,
    FS_XS, FS_SM, FS_MD2, FS_MD4,
    FW_BOLD, LS_WIDEST,
)


def build_right_panel(
    on_reset_camera: object,
    on_select_scalar_field: object,
    on_select_color_scheme: object,
    on_select_step: object,
    on_toggle_autoplay: object,
) -> None:
    """Right panel content: opacity, camera, field, color, playback, scalar bar."""
    with html.Div(style="padding:10px 14px; display:flex; flex-direction:column; height:100%; overflow-y:auto; box-sizing:border-box;"):

        # ----------------------------------------------------------------
        # Section: View
        # ----------------------------------------------------------------
        _section_header("mdi-eye-outline", "View", "right_view_open")

        with html.Div(v_show="right_view_open"):
            # Single row: [camera reset] | [opacity icon] [opacity slider]
            with html.Div(style="display:flex; align-items:center; gap:6px; margin-bottom:12px;"):
                v3.VBtn(
                    icon="mdi-camera-retake-outline",
                    variant="text", density="compact",
                    click=on_reset_camera,
                    style="opacity:0.65; flex-shrink:0;",
                )
                html.Span(style="width:1px; height:16px; background:rgba(128,128,128,0.3); flex-shrink:0;")
                v3.VIcon("mdi-circle-opacity", size="16", style="opacity:0.5; flex-shrink:0;")
                v3.VSlider(
                    v_model=("ctrl_opacity", 0.9),
                    min=0.0, max=1.0, step=0.1,
                    density="compact", hide_details=True,
                    color=ACCENT, track_color=TRACK_DARK,
                    thumb_label=False,
                    disabled=("autoplay",),
                    style="flex:1; margin:0; padding:0;",
                )

        v3.VDivider(style="margin-bottom:10px;")

        # ----------------------------------------------------------------
        # Section: Fibers (heart dataset only)
        # ----------------------------------------------------------------
        with html.Div(v_if="active_dataset === 'heart'"):
            _section_header("mdi-grain", "Fibers", "right_fibers_open")
            with html.Div(v_show="right_fibers_open", style="margin-bottom:4px;"):
                v3.VSwitch(
                    v_model=("show_fibers", False),
                    label="Show fiber glyphs",
                    density="compact", hide_details=True,
                    color=ACCENT,
                )
            v3.VDivider(style="margin-bottom:10px;")

        # ----------------------------------------------------------------
        # Section: Scalar Field (multi-field datasets only)
        # ----------------------------------------------------------------
        with html.Div(v_if="available_scalar_fields && available_scalar_fields.length > 1"):
            _section_header("mdi-layers-outline", "Scalar Field", "right_scalar_field_open")
            with html.Div(v_show="right_scalar_field_open"):
                with v3.VList(
                    density="compact", nav=True, bg_color="transparent",
                    style="padding:0; margin-bottom:4px; max-height:160px; overflow-y:auto;",
                ):
                    with html.Div(v_for="field in available_scalar_fields", key="field.name"):
                        with v3.VListItem(
                            density="compact",
                            click=(on_select_scalar_field, "[field.name]"),
                            active=("active_scalar_field === field.name",),
                            active_color=ACCENT,
                        ):
                            with v3.Template(v_slot_title=""):
                                html.Span("{{ field.label }}", style=f"font-size:{FS_MD4};")
            v3.VDivider(style="margin-bottom:10px;")

        # ----------------------------------------------------------------
        # Section: Color
        # ----------------------------------------------------------------
        _section_header("mdi-palette-outline", "Color", "right_color_open")

        with html.Div(v_show="right_color_open"):
            # Categorical palettes (no continuous scalar field)
            with html.Div(
                v_if="scalar_bar === null || scalar_bar === undefined",
                style="margin-bottom:8px;",
            ):
                with v3.VList(density="compact", nav=True, bg_color="transparent", style="padding:0;"):
                    with html.Div(v_for="palette in categorical_palette_meta", key="palette.name"):
                        with v3.VListItem(
                            density="compact",
                            click=(on_select_color_scheme, "[palette.name]"),
                            active=("active_categorical_palette === palette.name",),
                            active_color=ACCENT,
                        ):
                            with v3.Template(v_slot_title=""):
                                with html.Div(style="display:flex; align-items:center; gap:6px;"):
                                    html.Span("{{ palette.label }}", style=f"font-size:{FS_MD4}; width:72px; flex-shrink:0;")
                                    with html.Div(style="display:flex; gap:3px;"):
                                        with html.Div(v_for="(swatch, i) in palette.swatches", key="i"):
                                            html.Div(style=(f"'{SWATCH_STYLE} background:' + swatch + ';'",))

            # Continuous colormaps (continuous scalar field active)
            with html.Div(
                v_if="scalar_bar !== null && scalar_bar !== undefined",
                style="margin-bottom:8px;",
            ):
                with v3.VList(density="compact", nav=True, bg_color="transparent", style="padding:0;"):
                    with html.Div(v_for="cmap in continuous_cmap_meta", key="cmap.name"):
                        with v3.VListItem(
                            density="compact",
                            click=(on_select_color_scheme, "[cmap.name]"),
                            active=("active_continuous_cmap === cmap.name",),
                            active_color=ACCENT,
                        ):
                            with v3.Template(v_slot_title=""):
                                with html.Div(style="display:flex; align-items:center; gap:8px;"):
                                    html.Span("{{ cmap.label }}", style=f"font-size:{FS_MD4}; width:52px; flex-shrink:0;")
                                    html.Div(style=("'flex:1; height:14px; border-radius:4px; background:' + cmap.gradient",))

        # ----------------------------------------------------------------
        # Section: Playback (multi-step datasets only)
        # ----------------------------------------------------------------
        with html.Div(v_if="n_steps > 1"):
            v3.VDivider(style="margin-bottom:10px;")
            _section_header("mdi-play-circle-outline", "Playback", "right_playback_open")

            with html.Div(v_show="right_playback_open"):
                with html.Div(style="display:flex; align-items:center; gap:4px; margin-bottom:4px;"):
                    v3.VBtn(
                        icon=("autoplay ? 'mdi-pause' : 'mdi-play'",),
                        variant=("autoplay ? 'tonal' : 'text'",),
                        density="compact", size="x-small",
                        click=on_toggle_autoplay,
                    )
                    v3.VBtn(
                        icon="mdi-chevron-left", variant="text",
                        density="compact", size="x-small",
                        disabled=("active_step === 0",),
                        click=(on_select_step, "[active_step - 1]"),
                    )
                    v3.VSlider(
                        v_model=("active_step", 0),
                        min=0, max=("n_steps - 1",), step=1,
                        density="compact", hide_details=True,
                        color=ACCENT, track_color=TRACK_DARK,
                        thumb_label=False,
                        style="flex:1; margin:0; padding:0;",
                        end=(on_select_step, "[active_step]"),
                    )
                    v3.VBtn(
                        icon="mdi-chevron-right", variant="text",
                        density="compact", size="x-small",
                        disabled=("active_step >= n_steps - 1",),
                        click=(on_select_step, "[active_step + 1]"),
                    )

                html.Span(
                    "{{ step_times.length > 0 ? 't = ' + Number(step_times[active_step]).toFixed(1) : (active_step + 1) + ' / ' + n_steps }}",
                    style=f"font-size:{FS_XS}; opacity:0.60; display:block; text-align:right; margin-bottom:8px; font-variant-numeric:tabular-nums;",
                )

        # ----------------------------------------------------------------
        # Section: Scalar Bar (continuous scalar field only)
        # ----------------------------------------------------------------
        with html.Div(v_if="scalar_bar !== null"):
            v3.VDivider(style="margin-bottom:10px;")
            _section_header("mdi-gradient-horizontal", "Scalar Bar", "right_scalar_bar_open")

            with html.Div(v_show="right_scalar_bar_open"):
                html.Div(
                    "{{ scalar_bar.field_label }}",
                    style=f"font-size:{FS_SM}; opacity:0.50; text-align:center; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:5px;",
                )
                with html.Div(style="display:flex; align-items:center; gap:8px;"):
                    html.Span(
                        "{{ scalar_bar.min_label }}",
                        style=f"font-size:{FS_SM}; opacity:0.75; flex-shrink:0; font-variant-numeric:tabular-nums;",
                    )
                    html.Div(
                        style=("'flex:1; height:10px; border-radius:4px; background:' + scalar_bar.gradient",),
                    )
                    html.Span(
                        "{{ scalar_bar.max_label }}",
                        style=f"font-size:{FS_SM}; opacity:0.75; flex-shrink:0; font-variant-numeric:tabular-nums;",
                    )


def _section_header(icon: str, label: str, state_var: str) -> None:
    """Render a collapsible section header with icon, label, and chevron indicator."""
    with html.Div(
        style="display:flex; align-items:center; gap:6px; margin-bottom:6px; cursor:pointer; user-select:none;",
        click=f"{state_var} = !{state_var}",
    ):
        v3.VIcon(icon, size="small", color=ACCENT)
        html.Span(
            label,
            style=f"font-size:{FS_MD2}; font-weight:{FW_BOLD}; text-transform:uppercase; letter-spacing:{LS_WIDEST}; opacity:0.55; flex:1;",
        )
        v3.VIcon(
            (f"{state_var} ? 'mdi-chevron-down' : 'mdi-chevron-right'",),
            size="x-small", style="opacity:0.40;",
        )
