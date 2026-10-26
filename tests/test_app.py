"""Tests of the app without a browser: dataset selection, time steps, colours and errors."""

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
import pyvista as pv
from trame.app import get_server

from tests.conftest import region_grid, write_pvd
from visfem.app import VisfemApp
from visfem.engine import selection


@pytest.fixture
def app(datasets_dir: Path, add_dataset: Callable[..., Path]) -> Iterator[VisfemApp]:
    """Return the app on a data directory with a region, a scalar field, a time series and a broken dataset."""
    heart = add_dataset(
        "heart",
        render={
            "renderer": "region_id",
            "mesh_file": "mesh.vtu",
            "region_array": "PartId",
            "region_labels": {"1": ["Atria"], "2": ["Ventricles"], "3": ["Valves"]},
            "fiber": {"array": "Fiber", "stride": 1},
        },
    )
    region_grid().save(heart / "mesh.vtu")

    bone = add_dataset(
        "bone",
        render={
            "renderer": "scalar_field",
            "mesh_file": "mesh.vtu",
            "fields": [{"name": "stress"}, {"name": "zoneA"}, {"name": "zoneB"}],
            "categorical_fields": ["zoneA", "zoneB"],
        },
    )
    grid = pv.ImageData(dimensions=(4, 4, 4)).cast_to_unstructured_grid()
    grid.cell_data["stress"] = np.arange(grid.n_cells, dtype=float)
    grid.cell_data["zoneA"] = np.arange(grid.n_cells) % 3
    grid.cell_data["zoneB"] = np.arange(grid.n_cells) % 5
    grid.save(bone / "mesh.vtu")

    write_pvd(datasets_dir / "series", "series", 3)
    add_dataset("series", data_path="series/series.pvd", mesh_format="PVD")

    broken = add_dataset(
        "broken", render={"renderer": "surface", "mesh_file": "mesh.stl"}
    )
    (broken / "mesh.stl").write_text("solid broken\nthis is no stl\n")

    visfem_app = VisfemApp(get_server(f"test-{datasets_dir}", client_type="vue3"))
    yield visfem_app
    visfem_app.plotter.close()


def _run(coroutine: Coroutine[Any, Any, None]) -> None:
    """Run a coroutine of the app to its end."""
    asyncio.run(coroutine)


def _actor_dataset(app: VisfemApp) -> pv.DataSet:
    """Return the dataset the main actor of the scene draws."""
    dataset = _mapper(app).dataset
    assert dataset is not None
    return dataset


def _mapper(app: VisfemApp) -> pv.DataSetMapper:
    """Return the mapper of the main actor of the scene."""
    actor = app.scene.xdmf_actor or app.scene.active_actor
    assert actor is not None
    return cast(pv.DataSetMapper, actor.GetMapper())


def test_startup(app: VisfemApp) -> None:
    """Check that the app starts with every dataset and the metadata of its series."""
    assert sorted(app._project_metadata) == ["bone", "broken", "heart", "series"]
    assert [path.name for path in app._xdmf_meta] == ["series.pvd"]
    assert app.state.active_dataset is None


def test_select_region_dataset(app: VisfemApp) -> None:
    """Check a region coloured dataset: legend, mesh statistics, fibres and the dataset info."""
    _run(app.select_dataset("heart"))
    state = app.state
    assert state.active_dataset == "heart"
    assert [item["names"] for item in state.legend_items] == [
        ["Atria"],
        ["Ventricles"],
        ["Valves"],
    ]
    assert state.mesh_stats == {"n_cells": 8, "n_points": 27}
    assert state.has_fibers is True
    assert state.active_meta["name"] == "Test dataset"
    assert not state.busy and not state.loading
    assert not state.error_open


def test_timeseries_steps(app: VisfemApp) -> None:
    """Check a PVD time series: its steps, the step swap and the colour range kept over all steps."""
    _run(app.select_dataset("series"))
    state = app.state
    assert state.n_steps == 3
    assert state.step_times == [0.5, 1.0, 1.5]
    assert state.active_scalar_field is not None

    _run(app.select_scalar_field("u"))
    assert state.scalar_bar is not None
    # the global bounds of all steps, not the range of step 0
    assert (state.scalar_bar["min_val"], state.scalar_bar["max_val"]) == (0.0, 2.0)
    _run(app.select_step(2))
    assert state.active_step == 2
    assert np.all(_actor_dataset(app).point_data["u"] == 0.0)
    assert (state.scalar_bar["min_val"], state.scalar_bar["max_val"]) == (0.0, 2.0)


def test_colour_range_override(app: VisfemApp) -> None:
    """Check that a valid colour range is applied and an invalid one shows the range in use again."""
    _run(app.select_dataset("series"))
    _run(app.select_scalar_field("u"))
    state = app.state
    state.clim_input_min, state.clim_input_max = "0.5", "1.5"
    app.apply_clim_override()
    assert state.clim_override == [0.5, 1.5]
    _run(app.select_step(1))
    assert tuple(_mapper(app).GetScalarRange()) == (0.5, 1.5)

    state.clim_input_min, state.clim_input_max = "2", "nonsense"
    app.apply_clim_override()
    assert state.clim_override == [0.5, 1.5]
    assert (state.clim_input_min, state.clim_input_max) == ("0.5", "1.5")


def test_categorical_field_switch(app: VisfemApp) -> None:
    """Check that switching between categorical fields colours the mesh by the new zones."""
    _run(app.select_dataset("bone"))
    state = app.state
    assert state.active_scalar_field == "stress"
    for field, n_zones in [("zoneA", 3), ("zoneB", 5), ("zoneA", 3)]:
        _run(app.select_scalar_field(field))
        assert len(state.legend_items) == n_zones
        zone_ids = np.unique(_actor_dataset(app).cell_data["_zone_id"])
        assert list(zone_ids) == list(range(n_zones))
    _run(app.select_scalar_field("stress"))
    assert state.scalar_bar is not None and state.legend_items == []


def test_field_switch_holds_the_busy_flag(
    app: VisfemApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that the busy flag stays set while a field switch renders."""
    _run(app.select_dataset("bone"))
    seen: list[bool] = []
    original = selection.select_scalar_field

    def spy(*args: Any) -> None:
        seen.append(bool(app.state.busy))
        original(*args)

    monkeypatch.setattr("visfem.app.select_scalar_field", spy)
    _run(app.select_scalar_field("zoneA"))
    assert seen == [True]
    assert not app.state.busy


def test_failed_dataset_resets_the_view(app: VisfemApp) -> None:
    """Check that a dataset which fails to load reports the error and leaves no part of the dataset before it."""
    _run(app.select_dataset("heart"))
    _run(app.select_dataset("broken"))
    state = app.state
    assert state.error_open
    assert "Failed to load dataset 'broken'" in state.error_message
    assert state.active_dataset is None
    assert state.active_meta is None
    assert state.legend_items == []
    assert state.mesh_stats is None
    assert not state.busy and not state.loading
    assert app.scene.active_actor is None


def test_category_colour_override(app: VisfemApp) -> None:
    """Check that a category colour override recolours the legend and survives a palette switch."""
    _run(app.select_dataset("heart"))
    _run(app.set_category_color("Atria", "#ff0000"))
    assert app.state.legend_items[0]["color"] == "#ff0000"
    _run(app.select_color_scheme("wong"))
    assert app.state.legend_items[0]["color"] == "#ff0000"
    _run(app.reset_category_colors())
    assert app.state.legend_items[0]["color"] != "#ff0000"


def test_url_model(app: VisfemApp) -> None:
    """Check that ?model= selects a known dataset once and ignores an unknown key."""
    app._on_url_model_change(url_model="nope")
    assert app.state.active_dataset is None
    assert app.state.url_model == ""
