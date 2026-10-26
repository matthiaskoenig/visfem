"""Tests of the dataset discovery."""

import json
from pathlib import Path

import pytest

from visfem.engine import discovery

_DESCRIPTOR = {
    "name": "Heart",
    "pi": "PI",
    "institution": ["Lab"],
    "biological_scale": "organ",
    "organ_system": ["heart"],
    "description": "A heart.",
    "mesh_format": "VTU",
}


def test_keys_are_restricted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that a descriptor whose key is unsafe in URLs and templates is skipped."""
    for key in ["heart", "f100-Results.v2", "bad'key", "bad key"]:
        folder = tmp_path / key
        folder.mkdir()
        (folder / f"{key}.json").write_text(
            json.dumps({**_DESCRIPTOR, "data_path": key})
        )
    (tmp_path / "heart" / "mesh.meta.json").write_text("{}")
    monkeypatch.setattr(discovery, "DATASETS_DIR", tmp_path)
    monkeypatch.setattr(discovery, "ALLOWED_DATASETS", None)
    assert sorted(discovery.load_project_metadata()) == ["f100-Results.v2", "heart"]
