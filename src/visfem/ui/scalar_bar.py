"""Scalar bar and timestep navigation overlay for continuous field datasets."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3

_BAR_BASE = (
    "position:absolute; bottom:16px; left:50%; transform:translateX(-50%); "
    "z-index:10; border-radius:8px; padding:7px 14px; width:300px;"
)
_BAR_DARK = _BAR_BASE + (
    "background:rgba(28,35,35,0.88); backdrop-filter:blur(8px); "
    "-webkit-backdrop-filter:blur(8px); border:1px solid rgba(255,255,255,0.07);"
)
_BAR_LIGHT = _BAR_BASE + (
    "background:rgba(240,244,244,0.92); backdrop-filter:blur(8px); "
    "-webkit-backdrop-filter:blur(8px); border:1px solid rgba(0,0,0,0.08);"
)
_STYLE = (f"dark_mode ? '{_BAR_DARK}' : '{_BAR_LIGHT}'",)

_BTN_STYLE = "opacity:0.7; flex-shrink:0;"
_TIME_LABEL_STYLE = (
    "font-size:0.68rem; opacity:0.60; flex-shrink:0; min-width:52px; "
    "text-align:right; font-variant-numeric:tabular-nums;"
)

# Vue template expression for the time/step label — {{ }} is the correct syntax
# for dynamic text content in html.* elements (tuples only work for prop values).
_TIME_LABEL_EXPR = (
    "{{ step_times.length > 0"
    " ? 't = ' + Number(step_times[active_step]).toFixed(1)"
    " : (active_step + 1) + ' / ' + n_steps }}"
)

# JS expression for the gradient strip background — tuple makes it a bound prop.
_GRADIENT_STYLE = (
    "'flex:1; height:10px; border-radius:4px; background:' + scalar_bar.gradient",
)


def build_scalar_bar(on_select_step: object) -> None:
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
            v3.VBtn(
                icon="mdi-chevron-left",
                variant="text", density="compact", size="x-small",
                style=_BTN_STYLE,
                disabled=("active_step === 0",),
                click=(on_select_step, "[active_step - 1]"),
            )

            # Slider: v_model updates active_step for visual feedback while
            # dragging; `end` fires only on release to avoid queuing renders.
            v3.VSlider(
                v_model=("active_step", 0),
                min=0, max=("n_steps - 1",), step=1,
                density="compact", hide_details=True,
                color="#00897b", track_color="rgba(255,255,255,0.15)",
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

            # One-item tuple → Trame/Vue evaluates it as a bound JS expression.
            html.Span(_TIME_LABEL_EXPR, style=_TIME_LABEL_STYLE)

        # ---- Scalar bar (continuous scalar field only) ----
        with html.Div(v_if="scalar_bar !== null"):

            html.Div(
                "{{ scalar_bar.field_label }}",
                style=(
                    "font-size:0.70rem; opacity:0.50; text-align:center; "
                    "text-transform:uppercase; letter-spacing:0.08em; margin-bottom:5px;"
                ),
            )

            with html.Div(style="display:flex; align-items:center; gap:8px;"):
                html.Span(
                    "{{ scalar_bar.min_label }}",
                    style=(
                        "font-size:0.70rem; opacity:0.75; flex-shrink:0; "
                        "font-variant-numeric:tabular-nums;"
                    ),
                )
                # Trailing comma is required — makes this a tuple (JS expression),
                # not a plain Python string.
                html.Div(style=_GRADIENT_STYLE)
                html.Span(
                    "{{ scalar_bar.max_label }}",
                    style=(
                        "font-size:0.70rem; opacity:0.75; flex-shrink:0; "
                        "font-variant-numeric:tabular-nums;"
                    ),
                )
