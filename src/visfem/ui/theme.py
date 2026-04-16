"""Centralized design and style helpers for the VisFEM UI."""

# Colors

ACCENT       = "#00897b"
ACCENT_HOVER = "#00796b"
ACCENT_DIM   = "rgba(0,137,123,0.18)"   # organ-system tag background in info panel

SURFACE_DARK = "rgba(28,35,35,0.88)"
BORDER_DARK  = "rgba(255,255,255,0.07)"
TRACK_DARK   = "rgba(255,255,255,0.15)"   # inactive slider track (dark mode)
DIVIDER_DARK = "rgba(255,255,255,0.12)"   # thin 1px divider in controls bar

SURFACE_LIGHT = "rgba(240,244,244,0.92)"
BORDER_LIGHT  = "rgba(0,0,0,0.08)"

BACKDROP_BLUR = "backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px);"

# Typography

# Font size scale
FS_XS  = "0.68rem"   # labels, timestamps, tags
FS_SM  = "0.70rem"   # scalar bar field label, min/max labels
FS_SM2 = "0.72rem"   # region legend names
FS_SM3 = "0.74rem"   # reference links, ref_texts
FS_MD  = "0.76rem"   # body text, value rows
FS_MD2 = "0.78rem"   # section group headers, empty-state message
FS_MD3 = "0.80rem"   # XDMF sub-items, patient names
FS_MD4 = "0.82rem"   # list items, palette labels
FS_MD5 = "0.85rem"   # panel card title
FS_LG  = "0.92rem"   # dataset name heading in info panel
FS_XL  = "1.2rem"    # toolbar app title

# Font weights
FW_BOLD = "700"
FW_SEMI = "600"

# Letter spacings
LS_NORMAL = "0.05em"   # toolbar title
LS_WIDE   = "0.06em"   # organ-system tags
LS_WIDER  = "0.08em"   # metadata section labels
LS_WIDEST = "0.1em"    # section group headers

# Geometry

RADIUS_SM   = "8px"    # floating panels, buttons
RADIUS_MD   = "10px"   # tag pill
RADIUS_LG   = "12px"   # reserved (landing --radius)
RADIUS_FULL = "50%"    # circular swatches

Z_PANEL = 10   # all floating overlays

# Panel layout
PANEL_WIDTH = "270px"
PANEL_TOP   = "12px"
PANEL_LEFT  = "12px"
PANEL_RIGHT = "12px"

# Controls bar
CONTROLS_BAR_HEIGHT = "38px"
CONTROLS_BAR_TOP    = "12px"
CONTROLS_BAR_GAP    = "8px"
PANEL_PADDING       = "0 12px"

# Scalar bar
SCALAR_BAR_WIDTH   = "300px"
SCALAR_BAR_BOTTOM  = "16px"
SCALAR_BAR_PADDING = "7px 14px"

# Reusable CSS fragment strings

SWATCH_STYLE = (
    f"display:inline-block; width:10px; height:10px; "
    f"border-radius:{RADIUS_FULL}; flex-shrink:0;"
)
GRADIENT_SWATCH_STYLE = (
    "display:inline-block; width:60px; height:10px; "
    "border-radius:3px; flex-shrink:0;"
)
DIVIDER_STYLE = (
    f"width:1px; height:20px; background:{DIVIDER_DARK}; flex-shrink:0;"
)

# Glass-panel style helpers

def glass_panel_styles(pos_css: str) -> tuple[str, str]:
    """Return (dark_css, light_css) for a glass-morphism floating panel.

    pos_css — positioning CSS shared by both modes (position, top/bottom,
              left/right, width, z-index, etc.).
    """
    dark = (
        f"{pos_css}"
        f"background:{SURFACE_DARK}; {BACKDROP_BLUR} "
        f"border:1px solid {BORDER_DARK};"
    )
    light = (
        f"{pos_css}"
        f"background:{SURFACE_LIGHT}; {BACKDROP_BLUR} "
        f"border:1px solid {BORDER_LIGHT};"
    )
    return dark, light


def panel_style(pos_css: str) -> tuple[str]:
    """Return a trame-reactive style 1-tuple using a dark_mode JS ternary.

    Use this for panels whose style is fully static (no reactive sizing).
    For panels with reactive dimensions (e.g. controls bar), call
    glass_panel_styles() directly and append the dynamic suffix manually.
    """
    dark, light = glass_panel_styles(pos_css)
    return (f"dark_mode ? '{dark}' : '{light}'",)
