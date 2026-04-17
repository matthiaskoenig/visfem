"""Footer UI for VisFEM."""
from trame.widgets import html

from visfem.ui.theme import ACCENT, FS_XS, OP_DIM

FOOTER_STYLE = (
    "display:flex; align-items:center; justify-content:center; flex-wrap:wrap; "
    "width:100%; min-height:20px; padding:2px 16px; "
    "background-color: color-mix(in srgb, rgb(var(--v-theme-surface)) 88%, black 12%); "
    "border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));"
)

_LINK_STYLE = f"color:{ACCENT}; text-decoration:none; font-size:{FS_XS};"
_TEXT_STYLE = f"font-size:{FS_XS}; opacity:{OP_DIM};"
_SEP = "\u2002\u00b7\u2002"  # en-space · en-space


def build_footer() -> None:
    """Populate the footer with team info and lab link."""
    html.Span("\u00a9 2026\u2002Michelle Elias\u2002&\u2002Matthias K\u00f6nig", style=_TEXT_STYLE)
    html.Span(_SEP, style=_TEXT_STYLE)
    html.A(
        "livermetabolism.com",
        href="https://livermetabolism.com/",
        target="_blank",
        rel="noopener noreferrer",
        style=_LINK_STYLE,
    )
