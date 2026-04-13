"""Scalar bar overlay for continuous field colormaps."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3

_BAR_BASE = (
    "position:absolute; bottom:16px; left:50%; transform:translateX(-50%); "
    "z-index:10; border-radius:8px; padding:7px 14px; width:280px;"
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


def build_scalar_bar() -> None:
    """Build the floating scalar bar overlay at the bottom-center of the viewport."""
    with html.Div(v_if="scalar_bar !== null", style=_STYLE):

        # ---- Field name label ----
        html.Div(
            "{{ scalar_bar.field_label }}",
            style=(
                "font-size:0.70rem; opacity:0.50; text-align:center; "
                "text-transform:uppercase; letter-spacing:0.08em; margin-bottom:5px;"
            ),
        )

        # ---- min — gradient strip — max ----
        with html.Div(style="display:flex; align-items:center; gap:8px;"):
            html.Span(
                "{{ scalar_bar.min_label }}",
                style=(
                    "font-size:0.70rem; opacity:0.75; flex-shrink:0; "
                    "font-variant-numeric:tabular-nums;"
                ),
            )
            html.Div(
                style=(
                    "'flex:1; height:10px; border-radius:4px; background:' + scalar_bar.gradient",
                ),
            )
            html.Span(
                "{{ scalar_bar.max_label }}",
                style=(
                    "font-size:0.70rem; opacity:0.75; flex-shrink:0; "
                    "font-variant-numeric:tabular-nums;"
                ),
            )
