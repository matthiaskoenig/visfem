"""Tests of the dataset discovery."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from visfem.engine import discovery


def test_keys_are_restricted(add_dataset: Callable[..., Path]) -> None:
    """Check that a descriptor whose key is unsafe in URLs and templates is skipped."""
    for key in ["heart", "f100-Results.v2", "bad'key", "bad key"]:
        add_dataset(key)
    (add_dataset("heart") / "mesh.meta.json").write_text("{}")
    assert sorted(discovery.load_project_metadata()) == ["f100-Results.v2", "heart"]


def test_invalid_and_duplicate_descriptors_are_skipped(
    datasets_dir: Path, add_dataset: Callable[..., Path]
) -> None:
    """Check that an invalid descriptor or a second one of the same key does not stop the others."""
    add_dataset("heart")
    add_dataset("broken")
    (datasets_dir / "broken" / "broken.json").write_text(json.dumps({"name": "x"}))
    (datasets_dir / "copy").mkdir()
    (datasets_dir / "copy" / "heart.json").write_text(
        (datasets_dir / "heart" / "heart.json").read_text()
    )
    assert list(discovery.load_project_metadata()) == ["heart"]


def test_allowlist(
    add_dataset: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that VISFEM_DATASETS hides every dataset it does not list."""
    for key in ["heart", "liver", "knee"]:
        add_dataset(key)
    monkeypatch.setattr(discovery, "ALLOWED_DATASETS", {"liver", "knee"})
    assert sorted(discovery.load_project_metadata()) == ["knee", "liver"]


def test_missing_datasets_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that a missing datasets folder gives no datasets instead of an error."""
    monkeypatch.setattr(discovery, "DATASETS_DIR", tmp_path / "missing")
    assert discovery.load_project_metadata() == {}


def test_group_by_organ_system(add_dataset: Callable[..., Path]) -> None:
    """Check the dataset tree: grouped by the first organ system, ordered by sort_order, then name."""
    add_dataset("b", name="B heart", organ_system=["heart"])
    add_dataset("a", name="A heart", organ_system=["heart", "vasculature"])
    add_dataset("first", name="Z heart", organ_system=["heart"], sort_order=1)
    add_dataset("bone", name="Bone", organ_system=["bone"])
    groups = discovery.group_by_organ_system(discovery.load_project_metadata())
    assert list(groups) == ["bone", "heart"]
    assert [key for key, _ in groups["heart"]] == ["first", "a", "b"]


def test_meta_to_state(add_dataset: Callable[..., Path]) -> None:
    """Check the dataset info of the client: labels, references split into links and texts."""
    add_dataset(
        "heart",
        biological_scale="organ_system",
        organ_system=["heart", "vasculature"],
        references=["https://doi.org/10.1/x", "Doe et al. 2026"],
        spp_project="SPP2311 project",
    )
    state = discovery.meta_to_state(discovery.load_project_metadata()["heart"])
    assert state["biological_scale"] == "Organ System"
    assert state["organ_system"] == ["Heart", "Vasculature"]
    assert state["ref_urls"] == ["https://doi.org/10.1/x"]
    assert state["ref_texts"] == ["Doe et al. 2026"]
    assert state["spp_badge"] is True


def test_patients_and_xdmf(tmp_path: Path) -> None:
    """Check the patient folders and the XDMF files with their HDF5 companion."""
    for name in ["patient_10", "patient_2", "patient_x", "other"]:
        (tmp_path / name).mkdir()
    assert discovery.patient_numbers(tmp_path) == [2, 10]
    assert discovery.patient_subdir(tmp_path, 2) == tmp_path / "patient_02"

    for stem in ["a", "b"]:
        (tmp_path / f"{stem}.xdmf").write_text("")
    (tmp_path / "a.h5").write_text("")
    assert discovery.discover_xdmf(tmp_path) == {"a": tmp_path / "a.xdmf"}


def test_default_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check the data directory without DATA_DIR: data/ of a source checkout, else ./visfem_data."""
    repo = Path(discovery.__file__).parents[3]
    expected = (
        repo / "data"
        if (repo / "pyproject.toml").exists()
        else tmp_path / "visfem_data"
    )
    monkeypatch.chdir(tmp_path)
    assert discovery.default_data_dir() == expected
