"""Tests of the mesh loading, the metadata extraction and its sidecar cache."""

import json
from pathlib import Path

import numpy as np
import pytest
import pyvista as pv

from tests.conftest import region_grid, write_pvd, write_xdmf_series
from visfem import mesh
from visfem.models import MESH_METADATA_HASH


def test_static_metadata(tmp_path: Path) -> None:
    """Check the metadata of a static VTU: counts, cell types, fields and scalar bounds."""
    path = tmp_path / "mesh.vtu"
    region_grid().save(path)
    meta = mesh.get_metadata(path)
    assert meta.format == "pyvista_native"
    assert (meta.n_steps, meta.times) == (1, [])
    assert (meta.n_points, meta.n_cells) == (27, 8)
    assert meta.fields["PartId"].center == "cell"
    assert meta.fields["Fiber"].shape == [3]
    assert meta.fields["pressure"].center == "point"
    assert meta.scalar_bounds["pressure"] == [0.0, 26.0]
    assert meta.scalar_bounds["PartId"] == [1.0, 3.0]


def test_metadata_sidecar(tmp_path: Path) -> None:
    """Check that the metadata is cached next to the mesh and regenerated for another schema."""
    path = tmp_path / "mesh.vtu"
    region_grid().save(path)
    sidecar = tmp_path / "mesh.meta.json"
    mesh.get_metadata(path)
    cached = json.loads(sidecar.read_text())
    assert cached["schema_hash"] == MESH_METADATA_HASH

    # a cached value is served as it is
    cached["n_cells"] = 1234
    sidecar.write_text(json.dumps(cached))
    assert mesh.get_metadata(path).n_cells == 1234

    # a sidecar of another schema, or a broken one, is rebuilt
    cached["schema_hash"] = "outdated"
    sidecar.write_text(json.dumps(cached))
    assert mesh.get_metadata(path).n_cells == 8
    sidecar.write_text("{broken")
    assert mesh.get_metadata(path).n_cells == 8


def test_pvd_steps_are_sorted_by_time(tmp_path: Path) -> None:
    """Check that the steps of a PVD are ordered by their time, not by their order in the file."""
    pvd = write_pvd(tmp_path, "series", 3)
    steps = mesh.pvd_steps(pvd)
    assert [t for t, _ in steps] == [0.5, 1.0, 1.5]
    assert [p.name for _, p in steps] == [
        "series_2.vtu",
        "series_1.vtu",
        "series_0.vtu",
    ]


def test_pvd_series(tmp_path: Path) -> None:
    """Check the metadata and the steps of a PVD series, with the global bounds of every step."""
    pvd = write_pvd(tmp_path, "series", 3)
    meta = mesh.get_metadata(pvd)
    assert meta.format == "pvd_timeseries"
    assert (meta.n_steps, meta.times) == (3, [0.5, 1.0, 1.5])
    assert meta.scalar_bounds["u"] == [0.0, 2.0]
    # step 0 is the earliest time, written last
    assert np.all(mesh.load_mesh(pvd, 0).point_data["u"] == 2.0)
    assert np.all(mesh.load_mesh(pvd, 2).point_data["u"] == 0.0)


def test_xdmf_series(tmp_path: Path) -> None:
    """Check the metadata and the steps of a meshio XDMF time series."""
    path = write_xdmf_series(tmp_path / "series.xdmf", 3)
    meta = mesh.get_metadata(path)
    assert meta.format == "timeseries_xdmf"
    assert (meta.n_steps, meta.times) == (3, [0.0, 1.0, 2.0])
    assert meta.fields["c"].center == "point"
    assert meta.scalar_bounds["c"] == [0.0, 2.0]
    assert np.all(mesh.load_mesh(path, 1).point_data["c"] == 1.0)


def test_load_mesh_returns_detached_copies(tmp_path: Path) -> None:
    """Check that a change to a loaded mesh does not reach the mesh cache."""
    path = tmp_path / "mesh.vtu"
    region_grid().save(path)
    first = mesh.load_mesh(path)
    # an in-place change writes into the buffer of the copy only
    np.asarray(first.point_data["pressure"])[:] = -1.0
    first.point_data["added"] = np.zeros(first.n_points)
    second = mesh.load_mesh(path)
    assert second.point_data["pressure"][0] == 0.0
    assert "added" not in second.point_data


def test_lru_cache_evicts_the_least_recently_used() -> None:
    """Check that the cache drops the least recently used values over its limit and keeps a single value above it."""
    cache: mesh.LruCache[str, int] = mesh.LruCache(10, lambda value: value)
    cache.put("a", 4)
    cache.put("b", 4)
    assert cache.get("a") == 4  # b is the least recently used now
    cache.put("c", 4)
    assert ("a" in cache, "b" in cache, "c" in cache) == (True, False, True)
    assert cache.total == 8
    cache.put("a", 5)  # a replaced value is weighed again
    assert cache.total == 9
    cache.put("d", 20)  # the most recent value stays, alone
    assert (len(cache), cache.get("d"), cache.total) == (1, 20, 20)


def test_step_cache_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that the steps of a series over the memory limit are evicted and loaded again on demand."""
    pvd = write_pvd(tmp_path, "series", 4)
    step_bytes = mesh.load_mesh(pvd, 0).actual_memory_size * 1024
    cache: mesh.LruCache = mesh.LruCache(2 * step_bytes, mesh._cache_weight)
    monkeypatch.setattr(mesh, "_mesh_cache", cache)
    loads: list[int] = []
    load_pvd = mesh._load_pvd

    def counting_load_pvd(path: Path, step: int = 0) -> pv.DataSet:
        loads.append(step)
        return load_pvd(path, step)

    monkeypatch.setattr(mesh, "_load_pvd", counting_load_pvd)
    for step in range(4):
        mesh.load_mesh(pvd, step)
    assert len(cache) == 2 and cache.total <= cache.limit
    assert [key[2] for key in cache._entries] == [2, 3]
    # step 3 is served from memory, step 0 was evicted and comes from disk again;
    # step k is the file written as number 3 - k
    assert np.all(mesh.load_mesh(pvd, 3).point_data["u"] == 0.0)
    assert np.all(mesh.load_mesh(pvd, 0).point_data["u"] == 3.0)
    assert loads == [0, 1, 2, 3, 0]


def test_skins_share_the_mesh_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that the skin of a static mesh is cached with its mesh and weighed with its ids."""
    path = tmp_path / "mesh.vtu"
    region_grid().save(path)
    cache: mesh.LruCache = mesh.LruCache(1 << 30, mesh._cache_weight)
    monkeypatch.setattr(mesh, "_mesh_cache", cache)
    surface, point_ids, cell_ids = mesh.load_skin(path)
    assert point_ids is not None and cell_ids is not None
    assert ("mesh", path, 0) in cache and ("skin", path, 0) in cache
    volume = mesh.load_mesh(path).actual_memory_size * 1024
    skin = surface.actual_memory_size * 1024 + point_ids.nbytes + cell_ids.nbytes
    assert cache.total == volume + skin


@pytest.mark.parametrize(
    ("value", "expected"), [("", 2048), ("512", 512), ("lots", 2048), ("-1", 0)]
)
def test_mesh_cache_limit_from_the_environment(
    value: str, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that VISFEM_MESH_CACHE_MB sets the limit and an invalid value falls back to the default."""
    monkeypatch.setenv("VISFEM_MESH_CACHE_MB", value)
    assert mesh._env_megabytes("VISFEM_MESH_CACHE_MB", 2048) == expected << 20


def test_vtk_series_steps_natural_order(tmp_path: Path) -> None:
    """Check that a flat VTK series is ordered by the numbers in the file names."""
    for name in ["frame_10.vtk", "frame_2.vtk", "frame_1.vtk", "other.vtk"]:
        region_grid().save(tmp_path / name)
    steps = mesh.vtk_series_steps(tmp_path, "frame_*.vtk")
    assert [t for t, _ in steps] == [0.0, 1.0, 2.0]
    assert [p.name for _, p in steps] == ["frame_1.vtk", "frame_2.vtk", "frame_10.vtk"]


def test_metadata_for_series(tmp_path: Path) -> None:
    """Check that the metadata of a flat series spans the bounds of every frame."""
    paths = []
    for i in range(3):
        grid = region_grid()
        grid.point_data["pressure"] = grid.point_data["pressure"] * (i + 1)
        paths.append(tmp_path / f"frame_{i}.vtk")
        grid.save(paths[-1])
    meta = mesh.metadata_for_series(paths)
    assert meta.n_steps == 3
    assert meta.scalar_bounds["pressure"] == [0.0, 78.0]
    with pytest.raises(ValueError):
        mesh.metadata_for_series([])


def test_skin_with_ids() -> None:
    """Check that the skin of a volume maps back to the volume and keeps its arrays."""
    grid = region_grid()
    skin, point_ids, cell_ids = mesh.skin_with_ids(grid)
    assert isinstance(skin, pv.PolyData)
    assert point_ids is not None and cell_ids is not None
    assert len(point_ids) == skin.n_points
    assert len(cell_ids) == skin.n_cells
    # the arrays of the skin are the arrays of the volume cells and points it came from
    assert np.array_equal(skin.cell_data["PartId"], grid.cell_data["PartId"][cell_ids])
    assert np.array_equal(
        skin.point_data["pressure"], grid.point_data["pressure"][point_ids]
    )
    surface = pv.Sphere()
    assert mesh.skin_with_ids(surface) == (surface, None, None)
    assert mesh.as_surface(surface) is surface
    assert isinstance(mesh.as_surface(grid), pv.PolyData)


def test_parse_labels_file(tmp_path: Path) -> None:
    """Check the parsing of a LabelIDs.txt file: names per material id per mesh."""
    path = tmp_path / "LabelIDs.txt"
    path.write_text(
        "M.vtu Array explanation\n"
        "Anatomical Structure\tAbbreviation\tMaterial IDs\n"
        "Ventricles\tV\t1,2\n"
        "Atria\tA\t3\n"
        "Ventricles\tV\t2\n"
        "\n"
        "fibres.vtu Array explanation\n"
        "Fibre\tF\t7\n"
        "broken line\n"
    )
    assert mesh.parse_labels_file(path) == {
        "M.vtu": {1: ["Ventricles"], 2: ["Ventricles"], 3: ["Atria"]},
        "fibres.vtu": {7: ["Fibre"]},
    }


def test_metadata_follows_the_source(tmp_path: Path) -> None:
    """Check that the cached metadata is rebuilt when the mesh is exported again."""
    path = tmp_path / "mesh.vtu"
    region_grid().save(path)
    assert mesh.get_metadata(path).n_cells == 8
    bigger = pv.ImageData(dimensions=(4, 3, 3)).cast_to_unstructured_grid()
    bigger.save(path)
    assert mesh.get_metadata(path).n_cells == 12


def test_bounds_ignore_non_finite_values(tmp_path: Path) -> None:
    """Check that NaN and inf mark missing values and do not decide the colour range."""
    grid = region_grid()
    values = np.arange(grid.n_points, dtype=float)
    values[0], values[1] = np.nan, np.inf
    grid.point_data["pressure"] = values
    grid.point_data["missing"] = np.full(grid.n_points, np.nan)
    path = tmp_path / "mesh.vtu"
    grid.save(path)
    meta = mesh.get_metadata(path)
    assert meta.scalar_bounds["pressure"] == [2.0, 26.0]
    assert "missing" not in meta.scalar_bounds
    # the sidecar is valid JSON and served again
    assert mesh.get_metadata(path).scalar_bounds["pressure"] == [2.0, 26.0]


def test_xdmf_series_with_boundary_blocks(tmp_path: Path) -> None:
    """Check that the cell data of the lower-dimensional blocks of an XDMF series goes with them."""
    import os

    import meshio

    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    )
    cells = [
        ("tetra", np.array([[0, 1, 2, 3]])),
        ("triangle", np.array([[0, 1, 2], [0, 1, 3]])),
    ]
    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        with meshio.xdmf.TimeSeriesWriter("series.xdmf") as writer:
            writer.write_points_cells(points, cells)
            for step in range(2):
                writer.write_data(
                    float(step),
                    cell_data={"c": [np.array([step + 1.0]), np.array([9.0, 9.0])]},
                )
    finally:
        os.chdir(cwd)
    path = tmp_path / "series.xdmf"
    meta = mesh.get_metadata(path)
    assert (meta.n_cells, meta.cell_types) == (1, ["tetra"])
    loaded = mesh.load_mesh(path, 1)
    assert loaded.n_cells == 1
    assert list(loaded.cell_data["c"]) == [2.0]
