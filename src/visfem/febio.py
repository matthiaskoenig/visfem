"""Minimal FEBio (.feb) geometry reader.

Reads the ``<Geometry>`` section of a FEBio 2.x XML model (``<Nodes>`` and
``<Elements>`` blocks) into a PyVista ``UnstructuredGrid`` so a FEBio mesh can be
rendered by the ``region_id`` renderer like any other VTK file. Materials,
boundary conditions, contact and load steps are ignored: this is a geometry
import, not a solver interface.

Each ``<Elements>`` block becomes one cell block; its ``mat`` attribute is stored
in the ``Material`` cell array and the block index in ``Part``. Element node
ordering for the supported types is identical in FEBio and VTK, so connectivity is
passed through after mapping node ids to 0-based indices.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyvista as pv

# FEBio element type -> (VTK cell type, nodes per element).
_CELL_TYPES: dict[str, tuple[int, int]] = {
    "tri3": (int(pv.CellType.TRIANGLE), 3),
    "quad4": (int(pv.CellType.QUAD), 4),
    "tet4": (int(pv.CellType.TETRA), 4),
    "tet10": (int(pv.CellType.QUADRATIC_TETRA), 10),
    "penta6": (int(pv.CellType.WEDGE), 6),
    "hex8": (int(pv.CellType.HEXAHEDRON), 8),
    "hex20": (int(pv.CellType.QUADRATIC_HEXAHEDRON), 20),
}


@dataclass(frozen=True)
class FebioPart:
    """One ``<Elements>`` block of a FEBio model."""

    index: int            # 0-based block order in the file (the ``Part`` cell array)
    name: str             # the block's name attribute (e.g. "Part18"), "" if absent
    element_type: str     # FEBio type (hex8, tet4, ...)
    material_id: int      # the block's ``mat`` attribute (the ``Material`` cell array)
    material_name: str    # name of that material from <Material>, "" if unknown
    n_elements: int


def read_febio(path: Path) -> tuple[pv.UnstructuredGrid, list[FebioPart]]:
    """Parse the geometry of a FEBio .feb file.

    Returns the mesh with ``Material`` and ``Part`` integer cell arrays, plus one
    FebioPart per element block in file order. Raises ValueError for files
    without a ``<Geometry>`` section or with an unsupported element type.
    """
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise ValueError(f"{path.name}: not a well-formed XML file ({e})") from e
    geometry = root.find("Geometry")
    if geometry is None:
        raise ValueError(f"{path.name}: no <Geometry> section (not a FEBio model?)")

    material_names = {
        int(m.get("id", 0)): m.get("name", "") for m in root.iterfind("Material/material")
    }

    # Nodes: ids are 1-based and may be split over several <Nodes> blocks.
    node_ids: list[int] = []
    coords: list[list[float]] = []
    for nodes in geometry.iterfind("Nodes"):
        for node in nodes.iterfind("node"):
            node_ids.append(int(node.get("id", 0)))
            coords.append([float(v) for v in (node.text or "").split(",")])
    if not node_ids:
        raise ValueError(f"{path.name}: no nodes found")
    points = np.asarray(coords, dtype=np.float64)
    index_of = {nid: i for i, nid in enumerate(node_ids)}

    cells: list[int] = []
    cell_types: list[int] = []
    material: list[int] = []
    part_index: list[int] = []
    parts: list[FebioPart] = []
    for block_index, block in enumerate(geometry.iterfind("Elements")):
        etype = block.get("type", "")
        if etype not in _CELL_TYPES:
            raise ValueError(f"{path.name}: unsupported FEBio element type '{etype}'")
        vtk_type, n_nodes = _CELL_TYPES[etype]
        mat_id = int(block.get("mat", 0))
        n_elems = 0
        for elem in block.iterfind("elem"):
            try:
                conn = [index_of[int(v)] for v in (elem.text or "").split(",")]
            except (KeyError, ValueError) as e:
                raise ValueError(f"{path.name}: element {elem.get('id')} references an unknown node ({e})") from e
            if len(conn) != n_nodes:
                raise ValueError(
                    f"{path.name}: element {elem.get('id')} has {len(conn)} nodes, "
                    f"expected {n_nodes} for {etype}"
                )
            cells.append(n_nodes)
            cells.extend(conn)
            cell_types.append(vtk_type)
            material.append(mat_id)
            part_index.append(block_index)
            n_elems += 1
        parts.append(
            FebioPart(
                index=block_index,
                name=block.get("name", ""),
                element_type=etype,
                material_id=mat_id,
                material_name=material_names.get(mat_id, ""),
                n_elements=n_elems,
            )
        )
    if not cells:
        raise ValueError(f"{path.name}: no elements found")

    grid = pv.UnstructuredGrid(
        np.asarray(cells, dtype=np.int64),
        np.asarray(cell_types, dtype=np.uint8),
        points,
    )
    grid.cell_data["Material"] = np.asarray(material, dtype=np.int32)
    grid.cell_data["Part"] = np.asarray(part_index, dtype=np.int32)
    return grid, parts


def febio_to_vtu(src: Path, dst: Path) -> list[FebioPart]:
    """Convert a FEBio model's geometry to a VTU file; returns the element blocks."""
    grid, parts = read_febio(src)
    grid.save(dst)
    return parts
