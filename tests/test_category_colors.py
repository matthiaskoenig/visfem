"""Per-category color override behaviour (visfem.engine.colors)."""

from typing import Any

import pytest

from visfem.engine.colors import (
    active_overrides,
    apply_color_overrides,
    apply_overrides_to_state,
    category_key,
    clear_overrides,
    color_scope,
    is_valid_hex,
    set_override,
)


class FakeState:
    """Stand-in for Trame state, which is a flat attribute bag."""

    def __init__(self, **kwargs: Any) -> None:
        self.active_dataset: str | None = None
        self.active_patient: int | None = None
        self.category_colors: dict[str, dict[str, str]] = {}
        self.category_colors_active: dict[str, str] = {}
        self.legend_items: list[dict[str, Any]] = []
        self.__dict__.update(kwargs)


@pytest.fixture
def legend() -> list[dict[str, Any]]:
    return [
        {"names": ["Left ventricle"], "color": "#111111"},
        {"names": ["Right ventricle", "RV"], "color": "#222222"},
        {"names": ["Aorta"], "color": "#333333"},
    ]


@pytest.fixture
def state() -> FakeState:
    return FakeState(active_dataset="heart_ep")


# ---- hex validation ----


@pytest.mark.parametrize("value", ["#abc123", "#ABC123", "#000000"])
def test_valid_hex(value: str) -> None:
    assert is_valid_hex(value)


@pytest.mark.parametrize(
    "value", ["#abc", "#ff00", "red", "abc123", "", None, 123, "#gggggg"]
)
def test_invalid_hex(value: Any) -> None:
    assert not is_valid_hex(value)


# ---- category_key ----


def test_category_key_uses_first_name() -> None:
    assert category_key({"names": ["A", "B"]}) == "A"


@pytest.mark.parametrize("item", [{}, {"names": []}, {"names": None}])
def test_category_key_missing_names(item: dict[str, Any]) -> None:
    assert category_key(item) == ""


# ---- apply_color_overrides ----


def test_override_hit_and_miss(legend: list[dict[str, Any]]) -> None:
    items, colors = apply_color_overrides(
        legend, {"Aorta": "#ff0000", "Absent": "#00ff00"}
    )
    assert colors == ["#111111", "#222222", "#ff0000"]
    assert items[2]["color"] == "#ff0000"


def test_override_preserves_other_item_keys(legend: list[dict[str, Any]]) -> None:
    items, _ = apply_color_overrides(legend, {"Aorta": "#ff0000"})
    assert items[1]["names"] == ["Right ventricle", "RV"]


def test_override_keyed_on_first_name_only(legend: list[dict[str, Any]]) -> None:
    """An alias name is not an addressable key."""
    _, colors = apply_color_overrides(legend, {"RV": "#ff0000"})
    assert colors[1] == "#222222"


@pytest.mark.parametrize("bad", ["red", "#ff00", "", None])
def test_invalid_override_falls_back_to_palette(
    legend: list[dict[str, Any]], bad: Any
) -> None:
    _, colors = apply_color_overrides(legend, {"Aorta": bad})
    assert colors[2] == "#333333"


def test_empty_legend() -> None:
    assert apply_color_overrides([], {"Aorta": "#ff0000"}) == ([], [])


def test_unnamed_item_is_not_overridable() -> None:
    """An item with no names has no key, so an "" override must not reach it."""
    _, colors = apply_color_overrides(
        [{"names": [], "color": "#abcdef"}], {"": "#ff0000"}
    )
    assert colors == ["#abcdef"]


# ---- scoping ----


def test_scope_separates_patients(state: FakeState) -> None:
    set_override(state, "Aorta", "#ff0000")
    state.active_patient = 3
    assert active_overrides(state) == {}
    set_override(state, "liver", "#00ff00")
    state.active_patient = None
    assert active_overrides(state) == {"Aorta": "#ff0000"}


def test_scope_separates_datasets(state: FakeState) -> None:
    set_override(state, "Aorta", "#ff0000")
    state.active_dataset = "tibia_mesh"
    assert active_overrides(state) == {}
    set_override(state, "Bone", "#0000ff")
    state.active_dataset = "heart_ep"
    assert active_overrides(state) == {"Aorta": "#ff0000"}


def test_overrides_are_sticky_across_dataset_switches(state: FakeState) -> None:
    set_override(state, "Aorta", "#ff0000")
    state.active_dataset = "tibia_mesh"
    state.active_dataset = "heart_ep"
    assert active_overrides(state) == {"Aorta": "#ff0000"}


def test_color_scope_includes_dataset_and_patient(state: FakeState) -> None:
    state.active_patient = 7
    assert color_scope(state) == "heart_ep:7"


# ---- store mutation ----


def test_invalid_hex_never_enters_store(state: FakeState) -> None:
    set_override(state, "Aorta", "#ff0000")
    set_override(state, "Aorta", "nonsense")
    assert active_overrides(state) == {"Aorta": "#ff0000"}


def test_clear_single_override(state: FakeState) -> None:
    set_override(state, "Aorta", "#ff0000")
    set_override(state, "Apex", "#123456")
    set_override(state, "Apex", None)
    assert active_overrides(state) == {"Aorta": "#ff0000"}


def test_clear_all_overrides_prunes_scope(state: FakeState) -> None:
    set_override(state, "Aorta", "#ff0000")
    clear_overrides(state)
    assert active_overrides(state) == {}
    assert color_scope(state) not in state.category_colors


def test_set_override_reassigns_for_trame_sync(state: FakeState) -> None:
    """Trame only syncs state on assignment, so the dict must not be mutated in place."""
    before = state.category_colors
    set_override(state, "Aorta", "#ff0000")
    assert state.category_colors is not before


# ---- apply_overrides_to_state ----


def test_apply_to_state_writes_legend_and_returns_lut(
    state: FakeState, legend: list[dict[str, Any]]
) -> None:
    set_override(state, "Aorta", "#ff0000")
    colors = apply_overrides_to_state(state, legend)
    assert colors == ["#111111", "#222222", "#ff0000"]
    assert state.legend_items[2]["color"] == "#ff0000"


def test_apply_to_state_mirrors_only_visible_categories(
    state: FakeState, legend: list[dict[str, Any]]
) -> None:
    """An override for a category absent from this scene must not show in the UI mirror."""
    set_override(state, "Aorta", "#ff0000")
    set_override(state, "Not in this scene", "#0f0f0f")
    apply_overrides_to_state(state, legend)
    assert state.category_colors_active == {"Aorta": "#ff0000"}


def test_apply_to_state_with_no_overrides(
    state: FakeState, legend: list[dict[str, Any]]
) -> None:
    colors = apply_overrides_to_state(state, legend)
    assert colors == ["#111111", "#222222", "#333333"]
    assert state.category_colors_active == {}
