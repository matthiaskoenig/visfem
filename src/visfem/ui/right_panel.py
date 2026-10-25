"""Right panel: view, fibers, scalar field, color, regions, playback and scalar bar sections."""

from collections.abc import Generator
from contextlib import contextmanager
from functools import partial

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visfem.ui.theme import (
    ACCENT,
    FS_MD,
    FS_SM,
    FS_XS,
    GAP_LG,
    GAP_MD,
    GAP_SM,
    GAP_XS,
    OP_DIM,
    OP_SUBDUED,
    PAD_LG,
    PAD_MD,
    SEP_NORMAL,
    SWATCH_STYLE,
    TRACK_DARK,
    TRACK_LIGHT,
)
from visfem.ui.widgets import icon_button, section_header

# Slider track color, per theme.
_TRACK_COLOR = (f"dark_mode ? '{TRACK_DARK}' : '{TRACK_LIGHT}'",)

# Kwargs shared by the opacity and playback sliders.
_SLIDER_KW: dict[str, object] = {
    "density": "compact",
    "hide_details": True,
    "color": ACCENT,
    "track_color": _TRACK_COLOR,
    "thumb_label": False,
    "style": "flex:1; margin:0; padding:0;",
}

# Style of the underlined text field for one scalar bar colour limit.
_CLIM_INPUT_STYLE = (
    f"width:52px; flex-shrink:0; font-size:{FS_SM}; font-variant-numeric:tabular-nums; "
    "background:transparent; border:none; "
    "border-bottom:1px solid rgba(var(--v-border-color),var(--v-border-opacity)); "
    "color:inherit; outline:none; padding:1px 2px; text-align:center; cursor:text;"
)


def build_right_panel(
    on_reset_camera: object,
    on_select_scalar_field: object,
    on_select_color_scheme: object,
    on_toggle_color_reversed: object,
    on_select_step: object,
    on_toggle_autoplay: object,
    on_apply_clim: object,
    on_set_category_color: object,
    on_reset_category_colors: object,
) -> None:
    """Build the right panel sections, each control wired to its on_* callback."""
    with html.Div(
        style=f"padding:{PAD_MD} {PAD_LG}; display:flex; flex-direction:column; height:100%; overflow-y:auto; box-sizing:border-box;"
    ):
        section_header("mdi-eye-outline", "View", "right_view_open")

        with html.Div(v_show="right_view_open"):
            # One row: camera reset, separator, opacity icon and opacity slider.
            with html.Div(
                style=f"display:flex; align-items:center; gap:{GAP_MD}; margin-bottom:12px; padding-right:26px;"
            ):
                icon_button(
                    "Reset camera",
                    v_if="!camera_resetting",
                    icon="mdi-camera-retake-outline",
                    size="small",
                    disabled=("busy",),
                    click=on_reset_camera,
                )
                _busy_spinner()
                html.Span(
                    style=f"width:1px; height:18px; background:{SEP_NORMAL}; flex-shrink:0;"
                )
                with v3.VTooltip(
                    v_if="!opacity_adjusting", text="Mesh opacity", location="bottom"
                ):
                    with v3.Template(v_slot_activator="{ props }"):
                        v3.VIcon(
                            "mdi-circle-opacity",
                            size="small",
                            style=f"opacity:{OP_DIM}; flex-shrink:0; cursor:default;",
                            v_bind="props",
                        )
                _busy_spinner()
                v3.VSlider(
                    v_model=("ctrl_opacity", 0.9),
                    min=0.05,
                    max=0.95,
                    step=0.05,
                    disabled=("autoplay || busy",),
                    **_SLIDER_KW,
                )

        v3.VDivider(style="margin-bottom:10px;")

        # Fibers: only when the dataset has a fibre overlay.

        with html.Div(v_if="has_fibers"):
            section_header("mdi-grain", "Fibers", "right_fibers_open")
            with html.Div(v_show="right_fibers_open", style="margin-bottom:4px;"):
                # the label takes the body size of the panel rows; the thumb
                # overhangs the track, the margin keeps it inside the panel padding
                with v3.VSwitch(
                    v_model=("show_fibers", False),
                    density="compact",
                    hide_details=True,
                    color=ACCENT,
                    style="margin-left:6px;",
                ):
                    with v3.Template(v_slot_label=""):
                        html.Span(
                            "Show fiber glyphs",
                            style=f"font-size:{FS_MD}; margin-left:8px;",
                        )
            v3.VDivider(style="margin-bottom:10px;")

        # Scalar Field: only for multi-field datasets.

        with html.Div(
            v_if="available_scalar_fields && available_scalar_fields.length > 1"
        ):
            section_header(
                "mdi-layers-outline", "Scalar Field", "right_scalar_field_open"
            )
            with html.Div(v_show="right_scalar_field_open"):
                with _choice_list(
                    "field in available_scalar_fields",
                    "active_scalar_field",
                    on_select_scalar_field,
                    style="padding:0; margin-bottom:4px; max-height:160px; overflow-y:auto;",
                ):
                    html.Span("{{ field.label }}", style=f"font-size:{FS_MD};")
            v3.VDivider(style="margin-bottom:10px;")

        # The reverse toggle sits in the header outside the collapse click target.
        section_header(
            "mdi-palette-outline",
            "Color",
            "right_color_open",
            action=partial(
                icon_button,
                "Reverse color order",
                icon="mdi-swap-horizontal",
                variant=("color_reversed ? 'tonal' : 'text'",),
                size="x-small",
                color=(f"color_reversed ? '{ACCENT}' : ''",),
                disabled=("active_dataset === null || busy",),
                click=on_toggle_color_reversed,
            ),
        )

        with html.Div(v_show="right_color_open"):
            # Categorical palettes, for a categorical active field.
            with html.Div(
                v_if="scalar_bar === null || scalar_bar === undefined",
                style="margin-bottom:8px;",
            ):
                with _choice_list(
                    "palette in categorical_palette_meta",
                    "active_categorical_palette",
                    on_select_color_scheme,
                ):
                    with html.Div(
                        style=f"display:flex; align-items:center; gap:{GAP_MD};"
                    ):
                        html.Span(
                            "{{ palette.label }}",
                            style=f"font-size:{FS_MD}; width:72px; flex-shrink:0;",
                        )
                        with html.Div(
                            style=(
                                f"'display:flex; gap:{GAP_XS}; ' + (color_reversed ? 'flex-direction:row-reverse;' : '')",
                            )
                        ):
                            with html.Div(
                                v_for="(swatch, i) in palette.swatches", key="i"
                            ):
                                html.Div(
                                    style=(
                                        f"'{SWATCH_STYLE} background:' + swatch + ';'",
                                    )
                                )

            # Continuous colormaps, for a continuous active field.
            with html.Div(
                v_if="scalar_bar !== null && scalar_bar !== undefined",
                style="margin-bottom:8px;",
            ):
                with _choice_list(
                    "cmap in continuous_cmap_meta",
                    "active_continuous_cmap",
                    on_select_color_scheme,
                ):
                    with html.Div(
                        style=f"display:flex; align-items:center; gap:{GAP_LG};"
                    ):
                        html.Span(
                            "{{ cmap.label }}",
                            style=f"font-size:{FS_MD}; width:52px; flex-shrink:0;",
                        )
                        html.Div(
                            style=(
                                "'flex:1; height:14px; border-radius:4px; background:' + cmap.gradient + '; ' + (color_reversed ? 'transform:scaleX(-1);' : '')",
                            )
                        )

        # Regions: only for categorical datasets with a legend.

        with html.Div(v_if="legend_items && legend_items.length > 0"):
            v3.VDivider(style="margin-bottom:10px;")

            # The header carries a "reset all" action, shown once a region colour is overridden.
            section_header(
                "mdi-tag-multiple-outline",
                "Regions",
                "right_regions_open",
                action=partial(
                    icon_button,
                    "Reset all region colors",
                    v_if="Object.keys(category_colors_active || {}).length > 0",
                    icon="mdi-backup-restore",
                    size="x-small",
                    disabled=("busy",),
                    click=(on_reset_category_colors, "[]"),
                ),
            )

            with html.Div(v_show="right_regions_open"):
                with html.Div(
                    style=f"display:flex; flex-direction:column; gap:{GAP_SM}; margin-bottom:8px; padding-left:8px;"
                ):
                    # One row per legend item: one picker swatch, then every alias name the item carries.
                    with html.Div(
                        v_for="item in legend_items",
                        key="item.names[0]",
                        style=f"display:flex; align-items:flex-start; gap:{GAP_MD};",
                    ):
                        _category_swatch(
                            on_set_category_color, on_reset_category_colors
                        )
                        with html.Div(style="display:flex; flex-direction:column;"):
                            html.Span(
                                "{{ n }}",
                                v_for="n in item.names",
                                key="n",
                                style=f"font-size:{FS_SM}; line-height:1.6;",
                            )

        # Playback: only for multi-step datasets.

        with html.Div(v_if="n_steps > 1"):
            v3.VDivider(style="margin-bottom:10px;")
            section_header("mdi-play-circle-outline", "Playback", "right_playback_open")

            with html.Div(v_show="right_playback_open"):
                with html.Div(
                    style=f"display:flex; align-items:center; gap:{GAP_SM}; margin-bottom:4px;"
                ):
                    icon_button(
                        ("autoplay ? 'Pause animation' : 'Play animation'",),
                        icon=("autoplay ? 'mdi-pause' : 'mdi-play'",),
                        variant=("autoplay ? 'tonal' : 'text'",),
                        size="x-small",
                        disabled=("loading || busy",),
                        click=on_toggle_autoplay,
                    )
                    icon_button(
                        "Previous step",
                        icon="mdi-chevron-left",
                        size="x-small",
                        disabled=("loading || busy || active_step === 0",),
                        click=(on_select_step, "[Math.max(0, active_step - step_inc)]"),
                    )
                    v3.VSlider(
                        v_model=("active_step", 0),
                        min=0,
                        max=("n_steps - 1",),
                        step=("step_inc",),
                        disabled=("loading || busy",),
                        end=(on_select_step, "[active_step]"),
                        **_SLIDER_KW,
                    )
                    icon_button(
                        "Next step",
                        icon="mdi-chevron-right",
                        size="x-small",
                        disabled=(
                            "loading || busy || active_step + step_inc >= n_steps",
                        ),
                        click=(
                            on_select_step,
                            "[Math.min(n_steps - 1, active_step + step_inc)]",
                        ),
                    )
                    # Playback speed: click to cycle the multiplier (applies live while playing).
                    icon_button(
                        "Playback speed (click to cycle)",
                        text=("playback_speed + 'x'",),
                        size="x-small",
                        disabled=("loading || busy",),
                        click="playback_speed = [0.5, 1, 1.5, 2, 4]"
                        "[([0.5, 1, 1.5, 2, 4].indexOf(playback_speed) + 1) % 5]",
                        style="min-width:34px; font-variant-numeric:tabular-nums;",
                    )

                html.Span(
                    "{{ step_times.length > 0 ? 't = ' + Number(step_times[active_step]).toFixed(1) : (active_step + 1) + ' / ' + n_steps }}",
                    style=f"font-size:{FS_XS}; opacity:{OP_DIM}; display:block; text-align:right; margin-bottom:8px; font-variant-numeric:tabular-nums;",
                )

        # Scalar Bar: only for a continuous scalar field.

        with html.Div(v_if="scalar_bar !== null"):
            v3.VDivider(style="margin-bottom:10px;")
            section_header(
                "mdi-gradient-horizontal", "Scalar Bar", "right_scalar_bar_open"
            )

            with html.Div(v_show="right_scalar_bar_open"):
                html.Div(
                    "{{ scalar_bar.field_label }}",
                    style=f"font-size:{FS_SM}; opacity:{OP_DIM}; text-align:center; letter-spacing:0.04em; margin-bottom:5px;",
                )
                with html.Div(style=f"display:flex; align-items:center; gap:{GAP_LG};"):
                    _clim_input("clim_input_min", on_apply_clim)
                    html.Div(
                        style=(
                            "'flex:1; height:16px; border-radius:4px; background:' + scalar_bar.gradient",
                        ),
                    )
                    _clim_input("clim_input_max", on_apply_clim)


def _category_swatch(
    on_set_category_color: object, on_reset_category_colors: object
) -> None:
    """Legend dot that opens a colour picker for one category; takes the set and reset callbacks and reads ``item`` from the enclosing ``legend_items`` loop."""
    with v3.VMenu(
        close_on_content_click=False,
        location="start",
    ):
        with v3.Template(v_slot_activator="{ props }"):
            html.Span(
                v_bind="props",
                style=(
                    "'width:9px; height:9px; border-radius:50%; flex-shrink:0; cursor:pointer; margin-top:6px; "
                    "background:' + item.color + ';' + "
                    "((category_colors_active || {})[item.names[0]] "
                    "? ' box-shadow:0 0 0 2px rgba(127,127,127,0.55);' : '')",
                ),
            )
        with v3.VCard(style="padding:8px;", elevation=0, border=True):
            html.Div(
                "{{ item.names[0] }}",
                style=f"font-size:{FS_SM}; opacity:{OP_SUBDUED}; margin-bottom:6px; max-width:230px;",
            )
            # draft keeps the picker colour in a loop-scoped variable until Apply; each applied colour costs a full scene push.
            with html.Div(v_for="draft in [{ v: item.color }]", key="'picker'"):
                v3.VColorPicker(
                    v_model=("draft.v",),
                    mode="hex",
                    modes=("['hex']",),
                    hide_inputs=False,
                    show_swatches=False,
                    width="230",
                    elevation=0,
                )
                with html.Div(
                    style=f"display:flex; align-items:center; gap:{GAP_SM}; margin-top:6px;"
                ):
                    v3.VBtn(
                        text="Reset",
                        variant="outlined",
                        density="compact",
                        size="small",
                        disabled=("busy",),
                        click=(on_reset_category_colors, "[item.names[0]]"),
                        style="flex:1;",
                    )
                    v3.VBtn(
                        text="Apply",
                        variant="flat",
                        color=ACCENT,
                        density="compact",
                        size="small",
                        disabled=("busy",),
                        click=(
                            on_set_category_color,
                            "[item.names[0], typeof draft.v === 'string' "
                            "? draft.v : (draft.v && draft.v.hex)]",
                        ),
                        style="flex:1;",
                    )


def _busy_spinner() -> None:
    """Render the accent spinner that replaces the preceding v-if control while its action runs."""
    v3.VProgressCircular(
        v_else=True,
        indeterminate=True,
        color=ACCENT,
        size="20",
        width="2",
        style="flex-shrink:0;",
    )


def _clim_input(state_key: str, on_apply_clim: object) -> None:
    """Render one colour limit text field bound to state_key; blur or Enter calls on_apply_clim."""
    html.Input(
        type="text",
        v_model=(state_key, ""),
        style=_CLIM_INPUT_STYLE,
        blur=on_apply_clim,
        keydown="$event.key === 'Enter' && $event.target.blur()",
    )


@contextmanager
def _choice_list(
    loop: str, active_var: str, on_select: object, *, style: str = "padding:0;"
) -> Generator[None]:
    """Open a single-choice VList over the v-for expression loop with CSS style; the item whose name equals active_var is active, a click calls on_select with the name, and the body yields inside the item title slot."""
    var = loop.split(" in ")[0]
    with v3.VList(density="compact", nav=True, bg_color="transparent", style=style):
        with html.Div(v_for=loop, key=f"{var}.name"):
            with v3.VListItem(
                density="compact",
                click=(on_select, f"[{var}.name]"),
                active=(f"{active_var} === {var}.name",),
                active_color=ACCENT,
                disabled=("busy",),
            ):
                with v3.Template(v_slot_title=""):
                    yield
