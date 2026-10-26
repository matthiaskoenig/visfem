"""Tests of the colour helpers and the per-category colour overrides."""

from types import SimpleNamespace

from visfem.engine import colors
from visfem.engine.palettes import CATEGORICAL_PALETTES, CONTINUOUS_CMAPS


def test_css_rgb_and_hex() -> None:
    """Check the conversion of unit colours and the hex check of overrides."""
    assert colors.css_rgb((1.0, 0.5, 0.0)) == "rgb(255,128,0)"
    assert colors.is_valid_hex("#00aaFF")
    for value in ["00aaff", "#00aaf", "#00aaffff", "red", None, 7]:
        assert not colors.is_valid_hex(value)


def test_region_colors_cycle() -> None:
    """Check that more regions than palette colours reuse the palette."""
    assert colors.region_colors(5, ["#000000", "#ffffff"]) == [
        "#000000",
        "#ffffff",
    ] * 2 + ["#000000"]


def test_palettes() -> None:
    """Check that every categorical palette is a list of valid colours."""
    for palette in CATEGORICAL_PALETTES.values():
        assert palette and all(colors.is_valid_hex(c) for c in palette)
    assert "viridis" in CONTINUOUS_CMAPS


def test_overrides_are_scoped_per_patient() -> None:
    """Check setting, applying and clearing overrides, scoped per dataset and patient."""
    state = SimpleNamespace(
        active_dataset="heart", active_patient=None, category_colors=None
    )
    colors.set_override(state, "Atria", "#ff0000")
    colors.set_override(state, "Ventricles", "not a colour")
    assert colors.active_overrides(state) == {"Atria": "#ff0000"}

    items = [
        {"names": ["Atria"], "color": "#111111"},
        {"names": ["Ventricles"], "color": "#222222"},
        {"names": [], "color": "#333333"},
    ]
    lut = colors.apply_overrides_to_state(state, items)
    assert lut == ["#ff0000", "#222222", "#333333"]
    assert state.category_colors_active == {"Atria": "#ff0000"}

    # another patient has its own overrides
    state.active_patient = 2
    assert colors.active_overrides(state) == {}
    state.active_patient = None
    colors.set_override(state, "Atria", None)
    assert colors.active_overrides(state) == {}
    colors.set_override(state, "Atria", "#00ff00")
    colors.clear_overrides(state)
    assert state.category_colors == {}
