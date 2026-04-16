"""Scalar bar and timestep navigation overlay for continuous field datasets."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3
from visfem.ui.theme import (
    ACCENT, TRACK_DARK,
    FS_XS, FS_SM,
    Z_PANEL, RADIUS_SM, SCALAR_BAR_BOTTOM, SCALAR_BAR_PADDING, SCALAR_BAR_WIDTH,
    panel_style,
)

_POS = (
    f"position:absolute; bottom:{SCALAR_BAR_BOTTOM}; left:50%; transform:translateX(-50%); "
    f"z-index:{Z_PANEL}; border-radius:{RADIUS_SM}; padding:{SCALAR_BAR_PADDING}; width:{SCALAR_BAR_WIDTH};"
)
_STYLE = panel_style(_POS)

_BTN_STYLE = "opacity:0.7; flex-shrink:0;"
_TIME_LABEL_STYLE = (
    f"font-size:{FS_XS}; opacity:0.60; flex-shrink:0; min-width:52px; "
    "text-align:right; font-variant-numeric:tabular-nums;"
)

_TIME_LABEL_EXPR = (
    "{{ step_times.length > 0"
    " ? 't = ' + Number(step_times[active_step]).toFixed(1)"
    " : (active_step + 1) + ' / ' + n_steps }}"
)

_GRADIENT_STYLE = (
    "'flex:1; height:10px; border-radius:4px; background:' + scalar_bar.gradient",
)


def build_scalar_bar(on_select_step: object, on_toggle_autoplay: object) -> None:
    """Build the floating overlay combining step navigation and scalar bar.

    Visible whenever n_steps > 1 (step navigation) or scalar_bar is set
    (continuous scalar field).
    """
    with html.Div(
        v_if="scalar_bar !== null || n_steps > 1",
        style=_STYLE,
    ):

        # ---- Step navigation (multi-step datasets only) ----
        with html.Div(
            v_if="n_steps > 1",
            style="display:flex; align-items:center; gap:4px; margin-bottom:6px;",
        ):
            # Play / pause toggle
            v3.VBtn(
                icon=("autoplay ? 'mdi-pause' : 'mdi-play'",),
                variant=("autoplay ? 'tonal' : 'text'",),
                density="compact", size="x-small",
                style=_BTN_STYLE,
                click=on_toggle_autoplay,
            )

            v3.VBtn(
                icon="mdi-chevron-left",
                variant="text", density="compact", size="x-small",
                style=_BTN_STYLE,
                disabled=("active_step === 0",),
                click=(on_select_step, "[active_step - 1]"),
            )

            v3.VSlider(
                v_model=("active_step", 0),
                min=0, max=("n_steps - 1",), step=1,
                density="compact", hide_details=True,
                color=ACCENT, track_color=TRACK_DARK,
                thumb_label=False,
                style="flex:1; margin:0; padding:0; align-self:center;",
                end=(on_select_step, "[active_step]"),
            )

            v3.VBtn(
                icon="mdi-chevron-right",
                variant="text", density="compact", size="x-small",
                style=_BTN_STYLE,
                disabled=("active_step >= n_steps - 1",),
                click=(on_select_step, "[active_step + 1]"),
            )

            html.Span(_TIME_LABEL_EXPR, style=_TIME_LABEL_STYLE)

        # ---- Scalar bar (continuous scalar field only) ----
        with html.Div(v_if="scalar_bar !== null"):

            html.Div(
                "{{ scalar_bar.field_label }}",
                style=(
                    f"font-size:{FS_SM}; opacity:0.50; text-align:center; "
                    "text-transform:uppercase; letter-spacing:0.08em; margin-bottom:5px;"
                ),
            )

            with html.Div(style="display:flex; align-items:center; gap:8px;"):
                html.Span(
                    "{{ scalar_bar.min_label }}",
                    style=(
                        f"font-size:{FS_SM}; opacity:0.75; flex-shrink:0; "
                        "font-variant-numeric:tabular-nums;"
                    ),
                )

                html.Div(style=_GRADIENT_STYLE)
                html.Span(
                    "{{ scalar_bar.max_label }}",
                    style=(
                        f"font-size:{FS_SM}; opacity:0.75; flex-shrink:0; "
                        "font-variant-numeric:tabular-nums;"
                    ),
                )
