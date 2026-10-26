"""Tests of the resolution of the render block: the inferred renderer and mesh file."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import region_grid, write_pvd, write_xdmf_series
from visfem.engine.discovery import load_descriptor
from visfem.engine.renderers import (
    RENDERER_REGISTRY,
    resolve_mesh_file,
    resolve_render_config,
)
from visfem.models import RenderConfig, RendererName


def _resolve(folder: Path) -> RenderConfig:
    """Return the resolved render config of the dataset in *folder*."""
    meta = load_descriptor(folder / f"{folder.name}.json")
    return resolve_render_config(meta, folder)


def _surface(path: Path) -> None:
    """Write a surface mesh to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    region_grid().extract_surface(algorithm="dataset_surface").save(path)


def test_registry_covers_every_renderer() -> None:
    """Check that every renderer of the descriptors has an implementation."""
    assert set(RENDERER_REGISTRY) == set(RendererName)


def test_single_surface(add_dataset: Callable[..., Path]) -> None:
    """Check that a folder with one surface mesh is a surface with that mesh."""
    folder = add_dataset("one")
    _surface(folder / "mesh.vtp")
    cfg = _resolve(folder)
    assert (cfg.renderer, cfg.mesh_file) == (RendererName.SURFACE, "mesh.vtp")


def test_several_surfaces_need_a_mesh_file(add_dataset: Callable[..., Path]) -> None:
    """Check that several surface meshes leave the mesh file to the descriptor."""
    folder = add_dataset("two")
    _surface(folder / "a.vtp")
    _surface(folder / "b.stl")
    cfg = _resolve(folder)
    assert (cfg.renderer, cfg.mesh_file) == (RendererName.SURFACE, None)
    assert resolve_mesh_file(folder, cfg) is None
    cfg.mesh_candidates = ["missing.stl", "b.stl"]
    assert resolve_mesh_file(folder, cfg) == "b.stl"


@pytest.mark.parametrize(
    ("fields", "renderer"),
    [
        ({"mesh_format": "XDMF+HDF5"}, RendererName.TIMESERIES),
        ({"render": {"series": "frame_*.vtk"}}, RendererName.TIMESERIES),
        ({"render": {"database": "d3plot"}}, RendererName.TIMESERIES),
        (
            {"render": {"renderer": "region_id", "mesh_file": "m.vtu"}},
            RendererName.REGION_ID,
        ),
    ],
)
def test_declared_renderers(
    add_dataset: Callable[..., Path], fields: dict[str, Any], renderer: RendererName
) -> None:
    """Check the renderer that mesh_format, a series, a database or an explicit renderer select."""
    folder = add_dataset("declared", **fields)
    _surface(folder / "mesh.vtp")
    assert _resolve(folder).renderer == renderer


def test_xdmf_folder_is_a_timeseries(add_dataset: Callable[..., Path]) -> None:
    """Check that an XDMF file in the folder makes a time series."""
    folder = add_dataset("xdmf")
    write_xdmf_series(folder / "series.xdmf", 2)
    assert _resolve(folder).renderer == RendererName.TIMESERIES


def test_pvd_dataset_is_a_timeseries(
    datasets_dir: Path, add_dataset: Callable[..., Path]
) -> None:
    """Check that a PVD dataset, whose data_path is the PVD file, is a time series."""
    write_pvd(datasets_dir / "pvd", "series", 2)
    folder = add_dataset("pvd", mesh_format="PVD", data_path="pvd/series.pvd")
    meta = load_descriptor(folder / "pvd.json")
    assert resolve_render_config(meta, folder).renderer == RendererName.TIMESERIES


def test_patient_folders(add_dataset: Callable[..., Path]) -> None:
    """Check the renderers of per patient folders: organ meshes or a phase series."""
    organs = add_dataset("organs")
    (organs / "patient_01").mkdir()
    for organ in ["liver", "kidney"]:
        region_grid().save(organs / "patient_01" / f"{organ}.vtk")
    assert _resolve(organs).renderer == RendererName.PATIENT_ORGANS

    phases = add_dataset("phases")
    write_pvd(phases / "patient_01", "tissue_surface", 2)
    assert _resolve(phases).renderer == RendererName.PVD_PHASE_SERIES


def test_resolution_keeps_the_descriptor(add_dataset: Callable[..., Path]) -> None:
    """Check that the inferred fields go into a copy, not into the descriptor."""
    folder = add_dataset("copy", render={"categorical_palette": "wong"})
    _surface(folder / "mesh.vtp")
    meta = load_descriptor(folder / "copy.json")
    cfg = resolve_render_config(meta, folder)
    assert cfg.renderer == RendererName.SURFACE
    assert meta.render is not None and meta.render.renderer is None
    assert cfg.categorical_palette == "wong"
