"""Centralized design and style helpers for the VisFEM UI."""

# Colors

ACCENT     = "#00897b"
ACCENT_DIM = "rgba(0,137,123,0.18)"   # organ-system tag background in info panel

TRACK_DARK = "rgba(255,255,255,0.15)"   # inactive slider track (dark mode)

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
