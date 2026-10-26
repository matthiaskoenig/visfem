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


def test_lists_need_an_entry() -> None:
    """Check that a dataset names at least one organ system and one institution, the tree groups by the first organ system."""
    for field in ("organ_system", "institution"):
        with pytest.raises(ValidationError):
            ProjectMetadata.model_validate({**_DESCRIPTOR, field: []})


def test_render_block_options() -> None:
    """Check the names of palettes and colormaps, the d3plot database and the default field labels."""
    with pytest.raises(ValidationError, match="unknown palette"):
        RenderConfig.model_validate({"categorical_palette": "rainbow"})
    with pytest.raises(ValidationError, match="unknown colormap"):
        RenderConfig.model_validate({"continuous_cmap": "jet"})
    with pytest.raises(ValidationError):
        RenderConfig.model_validate({"database": "results.d3plot"})
    assert RenderConfig.model_validate({"database": "d3plot"}).database == "d3plot"
    cfg = RenderConfig.model_validate(
        {"fields": [{"name": "von_mises"}, {"name": "u", "label": "Displacement"}]}
    )
    assert [f.label for f in cfg.fields] == ["von mises", "Displacement"]


def test_comments_and_unknown_fields() -> None:
    """Check that keys starting with an underscore are comments and unknown keys are errors."""
    meta = ProjectMetadata.model_validate({**_DESCRIPTOR, "_comment": "a note"})
    assert meta.name == "Heart"
    with pytest.raises(ValidationError):
        ProjectMetadata.model_validate({**_DESCRIPTOR, "colour": "red"})
