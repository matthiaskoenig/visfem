"""Design tokens and CSS fragments for the VisFEM UI."""

from visfem.engine.colors import BG_DARK_BOTTOM, BG_LIGHT_BOTTOM, css_rgb

# Colors

ACCENT = "#00897b"
ACCENT_DIM = "rgba(0,137,123,0.15)"  # organ-system tag background in info panel

SPP_COLOR = "#c49a00"  # SPP2311 badge text and border
SPP_DIM = "rgba(196,154,0,0.15)"  # SPP2311 badge background

TRACK_DARK = "rgba(255,255,255,0.15)"  # inactive slider track (dark mode)
TRACK_LIGHT = "rgba(0,0,0,0.12)"  # inactive slider track (light mode)

SEP_DIM = "rgba(128,128,128,0.22)"  # toolbar dividers between button groups
SEP_NORMAL = "rgba(128,128,128,0.30)"  # view-section inline separator

# CSS colour of the div behind the VTK canvas: the bottom colour of each plotter gradient.
BG_DARK = css_rgb(BG_DARK_BOTTOM)
BG_LIGHT = css_rgb(BG_LIGHT_BOTTOM)

# Vuetify light theme; dark mode uses Vuetify's stock theme.
LIGHT_THEME_COLORS = {
    "primary": ACCENT,  # active items, toggles, progress bars
    "surface": "#EDF1F1",  # panels, toolbar, footer
    "background": "#F4F7F7",  # app background
    "on-surface": "#1B2524",  # text
}

# Typography

# Font size scale
FS_XS = "0.68rem"  # captions: timestamps, tag labels, scalar bar labels
FS_SM = "0.78rem"  # secondary: reference links, region names, scalar bar min/max
FS_MD = "0.85rem"  # body: descriptions, value rows, list items, patient names
FS_LG = "0.95rem"  # emphasis: dataset name heading, active dataset label
FS_XL = "1.2rem"  # brand: toolbar app title

# Font weights
FW_BOLD = "700"
FW_SEMI = "600"

# Letter spacings
LS_NORMAL = "0.05em"  # toolbar title
LS_WIDE = "0.06em"  # organ-system tags
LS_WIDER = "0.08em"  # metadata section labels
LS_WIDEST = "0.1em"  # section group headers

# Icon sizes
ICON_SM = "14"  # inline metadata row icons (account, bank, vector, reference)
ICON_LG = "32"  # decorative and empty-state icons

# Opacity levels
OP_GHOST = "0.35"  # panel-closed toggles, empty-state container
OP_MUTED = "0.45"  # tree decorative icons, metadata label text
OP_DIM = "0.50"  # metadata row icons, footer text, step timestamp
OP_SUBDUED = "0.55"  # section header text (all-caps bold compensates)
OP_BODY = "0.75"  # readable secondary: descriptions, scalar bar labels

# Gaps
GAP_XS = "3px"  # color swatch rows
GAP_SM = "4px"  # tag rows, region item rows
GAP_MD = "6px"  # standard icon-to-text gap
GAP_LG = "8px"  # metadata row spacing

# Padding
PAD_XS = "2px"  # tag pill vertical padding
PAD_SM = "7px"  # tag pill horizontal padding
PAD_MD = "10px"  # section header top padding
PAD_LG = "14px"  # panel horizontal padding
PAD_XL = "24px"  # empty-state and section inner padding

# Geometry

RADIUS_MD = "10px"  # tag pill
RADIUS_FULL = "50%"  # circular swatches

# Side panel widths
LEFT_PANEL_WIDTH = "300px"
RIGHT_PANEL_WIDTH = "300px"

# CSS fragments

SWATCH_STYLE = (
    f"display:inline-block; width:10px; height:10px; "
    f"border-radius:{RADIUS_FULL}; flex-shrink:0;"
)

# Toolbar and footer background.
BAR_BG = "color-mix(in srgb, rgb(var(--v-theme-surface)) 88%, black 12%)"

# Border in Vuetify's theme border colour.
BORDER_THEME = "1px solid rgba(var(--v-border-color), var(--v-border-opacity))"
