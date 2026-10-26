"""Tests of the FEBio geometry reader."""

from pathlib import Path

import numpy as np
import pytest
import pyvista as pv

from visfem.febio import febio_to_vtu, read_febio

_FEB = """<?xml version="1.0"?>
<febio_spec version="2.5">
  <Material>
    <material id="1" name="bone" type="rigid body"/>
    <material id="2" name="cartilage" type="neo-Hookean"/>
  </Material>
  <Geometry>
    <Nodes>
      <node id="1">0,0,0</node>
      <node id="2">1,0,0</node>
      <node id="3">0,1,0</node>
    </Nodes>
    <Nodes>
      <node id="10">0,0,1</node>
    </Nodes>
    <Elements type="tet4" mat="1" name="Part1">
      <elem id="1">1,2,3,10</elem>
    </Elements>
    <Elements type="tri3" mat="2" name="Part2">
      <elem id="2">1,2,3</elem>
      <elem id="3">1,3,10</elem>
    </Elements>
  </Geometry>
</febio_spec>
"""


def test_read_febio(tmp_path: Path) -> None:
    """Check nodes over several blocks, the element blocks and the Material and Part arrays."""
    path = tmp_path / "model.feb"
    path.write_text(_FEB)
    grid, parts = read_febio(path)
    assert grid.n_points == 4
    assert grid.n_cells == 3
    assert list(grid.celltypes) == [
        pv.CellType.TETRA,
        pv.CellType.TRIANGLE,
        pv.CellType.TRIANGLE,
    ]
    assert list(grid.cell_data["Material"]) == [1, 2, 2]
    assert list(grid.cell_data["Part"]) == [0, 1, 1]
    # node id 10 is the fourth point
    assert np.allclose(grid.points[3], [0, 0, 1])
    assert [(p.name, p.element_type, p.material_name, p.n_elements) for p in parts] == [
        ("Part1", "tet4", "bone", 1),
        ("Part2", "tri3", "cartilage", 2),
    ]

    vtu = tmp_path / "model.vtu"
    febio_to_vtu(path, vtu)
    assert pv.read(vtu).n_cells == 3


@pytest.mark.parametrize(
    ("replace", "message"),
    [
        (("<Geometry>", "<Geom>"), "malformed XML"),
        (('type="tri3"', 'type="tri6"'), "unsupported FEBio element type"),
        (("1,3,10</elem>", "1,3,99</elem>"), "unknown node id"),
        (("1,3,10</elem>", "1,3</elem>"), "has 2 nodes"),
    ],
)
def test_read_febio_errors(
    tmp_path: Path, replace: tuple[str, str], message: str
) -> None:
    """Check that a broken model is reported with what is wrong."""
    path = tmp_path / "model.feb"
    path.write_text(_FEB.replace(*replace))
    with pytest.raises(ValueError, match=message):
        read_febio(path)
