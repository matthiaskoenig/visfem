"""Widgets shared by the panels: section headers and tooltip icon buttons."""

from collections.abc import Callable
from typing import Any

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visfem.ui.theme import ACCENT, FS_MD, FW_BOLD, GAP_MD, LS_WIDEST, OP_SUBDUED

# Style of the uppercase section titles.
_TITLE_STYLE = f"font-size:{FS_MD}; font-weight:{FW_BOLD}; text-transform:uppercase; letter-spacing:{LS_WIDEST}; opacity:{OP_SUBDUED};"


def section_header(
    icon: str,
    label: str,
    state_var: str,
    *,
    prefix: str = "",
    suffix: str = "margin-bottom:6px;",
    action: Callable[[], None] | None = None,
) -> None:
    """Render a collapsible section header toggling the boolean state_var, with icon, label and chevrons; prefix and suffix are CSS before and after the flex rule, action builds a widget between label and chevrons; returns None."""
    toggle = f"{state_var} = !{state_var}"
    parts = [prefix, f"display:flex; align-items:center; gap:{GAP_MD};", suffix]
    # The whole row is the click target when action is None.
    if action is None:
        parts.append("cursor:pointer;")
    parts.append("user-select:none;")
    style = " ".join(part for part in parts if part)
    if action is None:
        with html.Div(style=style, click=toggle):
            v3.VIcon(icon, size="small", color=ACCENT)
            html.Span(label, style=f"{_TITLE_STYLE} flex:1;")
            v3.VIcon("mdi-chevron-down", size="small", v_show=f"{state_var}")
            v3.VIcon("mdi-chevron-right", size="small", v_show=f"!{state_var}")
        return
    with html.Div(style=style):
        with html.Div(
            style=f"display:flex; align-items:center; gap:{GAP_MD}; flex:1; cursor:pointer;",
            click=toggle,
        ):
            v3.VIcon(icon, size="small", color=ACCENT)
            html.Span(label, style=_TITLE_STYLE)
        action()
        with html.Div(style="cursor:pointer;", click=toggle):
            v3.VIcon("mdi-chevron-down", size="small", v_show=f"{state_var}")
            v3.VIcon("mdi-chevron-right", size="small", v_show=f"!{state_var}")


def icon_button(
    tooltip: str | tuple[str, ...],
    *,
    v_if: str | None = None,
    location: str = "bottom",
    **btn: Any,
) -> None:
    """Render a compact text-variant VBtn inside a VTooltip; tooltip is the static text or a one-element binding tuple, v_if gates the tooltip, location places it, btn kwargs go to the VBtn; returns None."""
    with v3.VTooltip(v_if=v_if, text=tooltip, location=location):
        with v3.Template(v_slot_activator="{ props }"):
            v3.VBtn(v_bind="props", **{"variant": "text", "density": "compact", **btn})
