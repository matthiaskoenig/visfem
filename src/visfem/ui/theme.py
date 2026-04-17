"""Centralized design and style helpers for the VisFEM UI."""

# Colors

ACCENT     = "#00897b"
ACCENT_DIM = "rgba(0,137,123,0.15)"   # organ-system tag background in info panel

TRACK_DARK = "rgba(255,255,255,0.15)"   # inactive slider track (dark mode)

SEP_DIM    = "rgba(128,128,128,0.22)"   # toolbar dividers between button groups
SEP_NORMAL = "rgba(128,128,128,0.30)"   # view-section inline separator

BG_DARK  = "rgb(20,26,26)"     # dark-mode viewport background
BG_LIGHT = "rgb(209,214,214)"  # light-mode viewport background

# Typography

# Font size scale
FS_XS  = "0.68rem"   # captions: timestamps, tag labels, scalar bar labels
FS_SM  = "0.78rem"   # secondary: reference links, region names, scalar bar min/max
FS_MD  = "0.85rem"   # body: descriptions, value rows, list items, patient names
FS_LG  = "0.95rem"   # emphasis: dataset name heading, active dataset label
FS_XL  = "1.2rem"    # brand: toolbar app title

# Font weights
FW_BOLD = "700"
FW_SEMI = "600"

# Letter spacings
LS_NORMAL = "0.05em"   # toolbar title
LS_WIDE   = "0.06em"   # organ-system tags
LS_WIDER  = "0.08em"   # metadata section labels
LS_WIDEST = "0.1em"    # section group headers

# Icon sizes
ICON_SM  = "14"   # inline metadata row icons (account, bank, vector, reference)
ICON_MD  = "16"   # slightly prominent inline icon (opacity icon in View section)
ICON_LG  = "32"   # decorative / empty-state icon

# Opacity levels
OP_GHOST   = "0.35"   # panel-closed toggles, empty-state container
OP_MUTED   = "0.45"   # tree decorative icons, metadata label text
OP_DIM     = "0.50"   # metadata row icons, footer text, step timestamp
OP_SUBDUED = "0.55"   # section header text (all-caps bold compensates)
OP_BODY    = "0.75"   # readable secondary: descriptions, scalar bar labels

# Gaps
GAP_XS  = "3px"   # color swatch rows
GAP_SM  = "4px"   # tag rows, region item rows
GAP_MD  = "6px"   # standard icon-to-text gap
GAP_LG  = "8px"   # metadata row spacing

# Padding
PAD_XS  = "2px"    # tag pill vertical padding
PAD_SM  = "7px"    # tag pill horizontal padding
PAD_MD  = "10px"   # section header top padding
PAD_LG  = "14px"   # panel horizontal padding
PAD_XL  = "24px"   # empty-state / section inner padding

# Geometry

RADIUS_MD   = "10px"   # tag pill
RADIUS_FULL = "50%"    # circular swatches

# Side panel widths
LEFT_PANEL_WIDTH  = "300px"
RIGHT_PANEL_WIDTH = "300px"

# Reusable CSS fragment strings

SWATCH_STYLE = (
    f"display:inline-block; width:10px; height:10px; "
    f"border-radius:{RADIUS_FULL}; flex-shrink:0;"
)
