"""Fixtures of the tests: small synthetic meshes and datasets in a temporary data directory."""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import meshio
import numpy as np
import pytest
import pyvista as pv

from visfem.engine import discovery

DESCRIPTOR: dict[str, Any] = {
    "name": "Test dataset",
    "pi": "Jane Doe",
    "institution": ["Test Lab"],
    "biological_scale": "organ",
    "organ_system": ["heart"],
    "description": "A synthetic dataset of the tests.",
    "mesh_format": "VTU",
}


def region_grid() -> pv.UnstructuredGrid:
    """Return a hexahedral grid of 2 x 2 x 2 cells with a `PartId` region array, a `Fiber` vector and a `pressure` scalar."""
    grid = pv.ImageData(dimensions=(3, 3, 3)).cast_to_unstructured_grid()
    grid.cell_data["PartId"] = np.array([1, 1, 2, 2, 3, 3, 3, 3], dtype=np.int32)
    grid.cell_data["Fiber"] = np.tile([1.0, 0.0, 0.0], (grid.n_cells, 1))
    grid.point_data["pressure"] = np.arange(grid.n_points, dtype=float)
    return grid


def write_pvd(directory: Path, name: str, n_steps: int) -> Path:
    """Write a PVD series of *n_steps* VTU files with a `u` field equal to the step index; return the PVD path."""
    directory.mkdir(parents=True, exist_ok=True)
    datasets = []
    for step in range(n_steps):
        grid = region_grid()
        grid.point_data["u"] = np.full(grid.n_points, float(step))
        vtu = directory / f"{name}_{step}.vtu"
        grid.save(vtu)
        # written in reverse time order, the PVD steps are sorted by time
        datasets.append(
            f'<DataSet timestep="{(n_steps - step) * 0.5}" file="{vtu.name}"/>'
        )
    pvd = directory / f"{name}.pvd"
    pvd.write_text(
        '<?xml version="1.0"?>\n<VTKFile type="Collection">\n<Collection>\n'
        + "\n".join(reversed(datasets))
        + "\n</Collection>\n</VTKFile>\n"
    )
    return pvd


def write_xdmf_series(path: Path, n_steps: int) -> Path:
    """Write a meshio XDMF time series of two triangles with a point field `c` equal to the step index; return the path."""
    # meshio writes the HDF5 companion relative to the working directory
    cwd = Path.cwd()
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chdir(path.parent)
    try:
        _write_xdmf_series(Path(path.name), n_steps)
    finally:
        os.chdir(cwd)
    return path


def _write_xdmf_series(path: Path, n_steps: int) -> None:
    """Write the XDMF time series of write_xdmf_series to *path* in the working directory."""
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]
    )
    cells = [("triangle", np.array([[0, 1, 2], [1, 3, 2]]))]
    with meshio.xdmf.TimeSeriesWriter(path) as writer:
        writer.write_points_cells(points, cells)
        for step in range(n_steps):
            writer.write_data(float(step), point_data={"c": np.full(4, float(step))})


@pytest.fixture
def datasets_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return an empty datasets folder which the discovery reads, with every dataset visible."""
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setattr(discovery, "DATASETS_DIR", root)
    monkeypatch.setattr(discovery, "ALLOWED_DATASETS", None)
    return root


@pytest.fixture
def add_dataset(datasets_dir: Path) -> Callable[..., Path]:
    """Return a function writing the descriptor of a dataset folder; it returns the dataset folder."""

    def add(key: str, **fields: Any) -> Path:
        folder = datasets_dir / key
        folder.mkdir(exist_ok=True)
        descriptor = {**DESCRIPTOR, "data_path": key, **fields}
        (folder / f"{key}.json").write_text(json.dumps(descriptor))
        return folder

    return add
