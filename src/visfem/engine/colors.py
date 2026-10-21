"""Color utilities and background constants for VisFEM."""

import re
from typing import Any

# ---- Background gradients ----

BG_DARK_BOTTOM = (0.08, 0.10, 0.10)
BG_DARK_TOP = (0.13, 0.16, 0.16)
BG_LIGHT_BOTTOM = (1.0, 1.0, 1.0)  # white viewport in light mode
BG_LIGHT_TOP = (1.0, 1.0, 1.0)


def css_rgb(rgb: tuple[float, float, float]) -> str:
    """Return the CSS rgb() string for a unit-range (r, g, b) tuple, each channel rounded to 0..255."""
    r, g, b = (round(c * 255) for c in rgb)
    return f"rgb({r},{g},{b})"


# ---- Color palettes ----


def scheme_to_hex(scheme_id: int) -> list[str]:
    """Convert a PyVista color scheme to a list of hex color strings."""
    # Imported here: the UI theme imports this module and stays free of the VTK stack.
    import pyvista.plotting.colors as pvc

    colors = []
    for item in pvc.color_scheme_to_cycler(scheme_id):
        c = item["color"]
        colors.append(f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}")
    return colors


def region_colors(n: int, palette: list[str]) -> list[str]:
    """Return n colors cycled from palette."""
    return [palette[i % len(palette)] for i in range(n)]


# ---- Per-category color overrides ----

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def is_valid_hex(color: Any) -> bool:
    """True when *color* is a '#rrggbb' string safe to hand to a VTK lookup table."""
    return isinstance(color, str) and _HEX_RE.match(color) is not None


def category_key(item: dict[str, Any]) -> str:
    """Return the override key for a legend item: its first display name.

    Names come from the dataset's region labels / organ filenames / part labels, so
    they are stable across palette changes and re-renders in a way the legend index
    is not (region ordering can differ between patients).
    """
    names = item.get("names") or []
    return str(names[0]) if names else ""


def apply_color_overrides(
    legend_items: list[dict[str, Any]], overrides: dict[str, str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Apply per-category color overrides to legend items.

    Returns the legend items with overridden colors and the matching LUT color list
    (same order, one entry per item). Items with no override — or with an override
    that is not a valid hex string — keep their palette color.
    """
    out: list[dict[str, Any]] = []
    colors: list[str] = []
    for item in legend_items:
        key = category_key(item)
        # An unnamed item has no addressable key, so it can never be overridden.
        color = overrides.get(key) if key else None
        color = color if is_valid_hex(color) else item.get("color")
        out.append({**item, "color": color})
        colors.append(str(color))
    return out, colors


# ---- Override state (Trame state helpers) ----
#
# These live here rather than in selection.py so that renderers.py can reuse them
# without importing selection.py, which imports renderers.py.


def color_scope(state: Any) -> str:
    """Return the override scope key for the current scene.

    Patients get their own scope: organ sets (and so category names) differ between
    them, and a colour set on one patient's liver shouldn't silently apply to another.
    """
    return f"{state.active_dataset}:{state.active_patient}"


def active_overrides(state: Any) -> dict[str, str]:
    """Return the category -> hex overrides for the current scope (never None)."""
    store = getattr(state, "category_colors", None) or {}
    return dict(store.get(color_scope(state), {}))


def set_override(state: Any, name: str, color: str | None) -> None:
    """Set (or clear, when *color* is None) one category override in the current scope."""
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
    # Reassign rather than mutate: Trame only syncs state on assignment.
    state.category_colors = store


def clear_overrides(state: Any) -> None:
    """Drop every override in the current scope."""
    store = dict(getattr(state, "category_colors", None) or {})
    store.pop(color_scope(state), None)
    state.category_colors = store


def apply_overrides_to_state(
    state: Any, legend_items: list[dict[str, Any]]
) -> list[str]:
    """Write *legend_items* to state with overrides applied; return the LUT colors.

    Single funnel for every path that produces a legend, so an override survives a
    full re-render, a palette swap, and a patient switch alike.
    """
    overrides = active_overrides(state)
    items, colors = apply_color_overrides(legend_items, overrides)
    state.legend_items = items
    # Mirror only the overrides that actually matched a visible category, so the UI's
    # "any overrides set?" check reflects this scene.
    keys = {item["names"][0] for item in items if item.get("names")}
    state.category_colors_active = {k: v for k, v in overrides.items() if k in keys}
    return colors
