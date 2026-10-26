"""Tests of the dataset descriptor models."""

import pytest
from pydantic import ValidationError

from visfem.models import PartSpec, ProjectMetadata, RenderConfig

_DESCRIPTOR = {
    "data_path": "heart",
    "name": "Heart",
    "pi": "PI",
    "institution": ["Lab"],
    "biological_scale": "organ",
    "organ_system": ["heart"],
    "description": "A heart.",
    "mesh_format": "VTU",
}


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "a/../../b", " "])
def test_paths_stay_inside_the_dataset(path: str) -> None:
    """Check that every path of a descriptor is confined to the datasets folder."""
    with pytest.raises(ValidationError):
        ProjectMetadata.model_validate({**_DESCRIPTOR, "data_path": path})
    with pytest.raises(ValidationError):
        ProjectMetadata.model_validate({**_DESCRIPTOR, "labels_file": path})
    for field in ("mesh_file", "series", "database"):
        with pytest.raises(ValidationError):
            RenderConfig.model_validate({field: path})
    with pytest.raises(ValidationError):
        RenderConfig.model_validate({"mesh_candidates": ["mesh.stl", path]})
    with pytest.raises(ValidationError):
        PartSpec.model_validate({"stem": path, "label": "part"})


def test_relative_paths_are_accepted() -> None:
    """Check that paths inside the dataset folder, globs included, are kept."""
    cfg = RenderConfig.model_validate(
        {
            "mesh_file": "sub/mesh.vtu",
            "series": "frame_*.vtk",
            "parts": [{"stem": "a/b", "label": "B"}],
        }
    )
    assert cfg.mesh_file == "sub/mesh.vtu"
    assert cfg.series == "frame_*.vtk"
    assert ProjectMetadata.model_validate(_DESCRIPTOR).data_path == "heart"
