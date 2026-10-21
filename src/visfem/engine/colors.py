"""Color utilities and background constants for VisFEM."""

import re
from typing import Any

# ---- Background gradients ----

BG_DARK_BOTTOM = (0.08, 0.10, 0.10)
BG_DARK_TOP = (0.13, 0.16, 0.16)
BG_LIGHT_BOTTOM = (1.0, 1.0, 1.0)
BG_LIGHT_TOP = (1.0, 1.0, 1.0)


def css_rgb(rgb: tuple[float, float, float]) -> str:
    """Return the CSS rgb() string for unit-range tuple *rgb*, each channel rounded to 0 to 255."""
    r, g, b = (round(c * 255) for c in rgb)
    return f"rgb({r},{g},{b})"


# ---- Color palettes ----


def scheme_to_hex(scheme_id: int) -> list[str]:
    """Return the colors of PyVista color scheme *scheme_id* as '#rrggbb' strings."""
    # Lazy import: the UI theme imports this module without the VTK stack.
    import pyvista.plotting.colors as pvc

    colors = []
    for item in pvc.color_scheme_to_cycler(scheme_id):
        c = item["color"]
        colors.append(f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}")
    return colors


def region_colors(n: int, palette: list[str]) -> list[str]:
    """Return *n* colors cycled from *palette*."""
    return [palette[i % len(palette)] for i in range(n)]


# ---- Per-category color overrides ----

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def is_valid_hex(color: Any) -> bool:
    """Return True when *color* is a '#rrggbb' string a VTK lookup table accepts."""
    return isinstance(color, str) and _HEX_RE.match(color) is not None


def category_key(item: dict[str, Any]) -> str:
    """Return the override key for *item*: its first display name (region label, organ filename or part label)."""
    # Names outlast palette swaps and re-renders; the legend index follows region order, which differs between patients.
    names = item.get("names") or []
    return str(names[0]) if names else ""


def apply_color_overrides(
    legend_items: list[dict[str, Any]], overrides: dict[str, str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Apply *overrides* to *legend_items*; return the recolored items and their LUT colors in item order."""
    out: list[dict[str, Any]] = []
    colors: list[str] = []
    for item in legend_items:
        key = category_key(item)
        # Overrides address items by name; an unnamed item keeps its palette color.
        color = overrides.get(key) if key else None
        color = color if is_valid_hex(color) else item.get("color")
        out.append({**item, "color": color})
        colors.append(str(color))
    return out, colors


# ---- Override state (Trame state helpers) ----
# Shared by renderers.py and selection.py, which imports renderers.py; keeping them here avoids an import cycle.


def color_scope(state: Any) -> str:
    """Return the override scope key for the current scene."""
    # One scope per patient: organ sets and category names differ between patients.
    return f"{state.active_dataset}:{state.active_patient}"


def active_overrides(state: Any) -> dict[str, str]:
    """Return a dict of category -> hex overrides for the current scope."""
    store = getattr(state, "category_colors", None) or {}
    return dict(store.get(color_scope(state), {}))


def set_override(state: Any, name: str, color: str | None) -> None:
    """Set the override for category *name* to *color* in the current scope; None clears it."""
    store = dict(getattr(state, "category_colors", None) or {})
    scope = color_scope(state)
    scoped = dict(store.get(scope, {}))
    if color is None:
        scoped.pop(name, None)
    elif is_valid_hex(color):
        scoped[name] = color
    else:
        return
    if scoped:
        store[scope] = scoped
    else:
        store.pop(scope, None)
    # Trame syncs state only on assignment.
    state.category_colors = store


def clear_overrides(state: Any) -> None:
    """Drop every override in the current scope."""
    store = dict(getattr(state, "category_colors", None) or {})
    store.pop(color_scope(state), None)
    state.category_colors = store


def apply_overrides_to_state(
    state: Any, legend_items: list[dict[str, Any]]
) -> list[str]:
    """Write *legend_items* to state with overrides applied; return the LUT colors."""
    # Single funnel for every legend path: overrides survive re-renders, palette swaps and patient switches.
    overrides = active_overrides(state)
    items, colors = apply_color_overrides(legend_items, overrides)
    state.legend_items = items
    # Mirror the overrides that match a visible category; the UI's overrides-set check reads this.
    keys = {item["names"][0] for item in items if item.get("names")}
    state.category_colors_active = {k: v for k, v in overrides.items() if k in keys}
    return colors
