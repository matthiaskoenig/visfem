"""Exploratory script for the four-chamber heart dataset.

Two meshes: M.vtu (mechanical, ~129k tetra, 12 material regions) and
EP.vtu (electrophysiology, 640MB, surface-extracted for visualization).
"""

from pathlib import Path
from typing import cast

import numpy as np
import pyvista as pv

from visfem.mesh import get_metadata, load_mesh


# ---- Paths ----

_DATA_BASE  = Path(__file__).parents[1] / "data" / "fem_data"
HEART_DIR   = _DATA_BASE / "heart"
MESH_PATH   = HEART_DIR / "M.vtu"
EP_MESH_PATH = HEART_DIR / "EP.vtu"
SURFACE_DIR = HEART_DIR / "surfaces"

# STL surface files — discovered dynamically from surfaces/
SURFACES: dict[str, Path] = {p.stem: p for p in sorted(SURFACE_DIR.glob("*.stl"))}

# MaterialID -> anatomical structure name (from LabelIDs.txt)
MATERIAL_NAMES: dict[int, str] = {
    30: "Left ventricle",
    31: "Right ventricle",
    32: "Right atrium",
    33: "Left atrium",
    34: "Pulmonary aortic valve",
    35: "Aortic valve",
    36: "Tricuspid valve",
    37: "Mitral valve",
    38: "Vein/vena cava orifice",
    39: "Aorta/pulmonary artery/veins",
    60: "Pericardium (inner)",
    61: "Pericardium (outer)",
}

# Distinct colors per material for multi-region rendering
_MATERIAL_COLORS: dict[int, str] = {
    30: "#c0152a",   # LV
    31: "#e8603c",   # RV
    32: "#d45087",   # RA
    33: "#f4a261",   # LA
    34: "#9b2d7f",   # pulmonary aortic valve
    35: "#c77dff",   # aortic valve
    36: "#e63e8c",   # tricuspid valve
    37: "#ff6b9d",   # mitral valve
    38: "#ffb347",   # orifices
    39: "#4363d8",   # vessels
    60: "#f9c0c0",   # pericardium inner
    61: "#ffe0d0",   # pericardium outer
}

# EP MaterialID -> anatomical structure name (from LabelIDs.txt)
EP_MATERIAL_NAMES: dict[int, str] = {
    1:  "Ventricle endocardium",
    2:  "Ventricle myocardium",
    3:  "Ventricle epicardium",
    32: "Right atrial bulk tissue",
    33: "Left atrial bulk tissue",
    72: "Crista terminalis",
    73: "Sinus node",
    74: "Pectinate muscles",
    75: "Bachmann bundle",
    76: "Middle posterior bridge",
    77: "Lower posterior bridge",
    78: "Coronary sinus bridge",
    79: "L/R atrial appendage",
    80: "Inferior isthmus",
}

# EP colors: warm reds/oranges for ventricles, pinks for atria, teals/purples for conduction
_EP_MATERIAL_COLORS: dict[int, str] = {
    1:  "#c0152a",   # ventricle endocardium - deep red
    2:  "#e8603c",   # ventricle myocardium - burnt orange
    3:  "#f4a261",   # ventricle epicardium - warm peach
    32: "#d45087",   # RA bulk - raspberry
    33: "#ff6b9d",   # LA bulk - light pink
    72: "#4363d8",   # crista terminalis - blue
    73: "#f032e6",   # sinus node - magenta (small but important)
    74: "#9b2d7f",   # pectinate muscles - deep purple
    75: "#42d4f4",   # Bachmann bundle - cyan
    76: "#3cb44b",   # middle posterior bridge - green
    77: "#bfef45",   # lower posterior bridge - lime
    78: "#469990",   # coronary sinus bridge - teal
    79: "#ffb347",   # atrial appendage - amber
    80: "#c77dff",   # inferior isthmus - violet
}


# ---- Inspection ----

def print_metadata() -> None:
    """Print metadata summary for M.vtu."""
    meta = get_metadata(MESH_PATH)
    print("\nM.vtu")
    print(f"  format     : {meta['format']}")
    print(f"  n_points   : {meta['n_points']}")
    print(f"  n_cells    : {meta['n_cells']}")
    print(f"  cell_types : {meta['cell_types']}")
    print(f"  fields ({len(meta['fields'])}):")
    for name, info in meta["fields"].items():
        print(f"    {name:<20} center={info['center']}  shape={info['shape']}")


def print_material_distribution() -> None:
    """Print cell count per material ID."""
    mesh = load_mesh(MESH_PATH)
    material_ids = mesh.cell_data["Material"]
    unique_ids, cell_counts = np.unique(material_ids, return_counts=True)
    print(f"\nMaterial distribution ({mesh.n_cells} total cells):")
    for mat_id, cell_count in zip(unique_ids, cell_counts):
        name = MATERIAL_NAMES.get(int(mat_id), "unknown")
        print(f"  MaterialID {int(mat_id):>3}  {name:<35}  {cell_count:>6} cells  ({100*cell_count/mesh.n_cells:.1f}%)")


def print_surface_summary() -> None:
    """Print point/cell counts for all STL surface files."""
    print("\nSurface meshes:")
    for name, path in SURFACES.items():
        if path.exists():
            mesh = cast(pv.DataSet, pv.read(str(path)))
            print(f"  {name:<15}  {mesh.n_points:>6} pts  {mesh.n_cells:>6} cells")
        else:
            print(f"  {name:<15}  NOT FOUND")


# ---- Visualization ----

def plot_material_colored() -> None:
    """Render M.vtu colored by MaterialID scalar."""
    mesh = load_mesh(MESH_PATH)
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, scalars="Material", show_edges=False, cmap="tab20")
    plotter.add_title("Four-chamber heart  colored by MaterialID", font_size=9)
    plotter.show()


def plot_material_colored_per_region() -> None:
    """Render each material as a separate actor with anatomically meaningful colors."""
    mesh = load_mesh(MESH_PATH)
    material_ids = mesh.cell_data["Material"]
    plotter = pv.Plotter()

    for mat_id, color in _MATERIAL_COLORS.items():
        mask = material_ids == mat_id
        if not mask.any():
            continue
        submesh = mesh.extract_cells(np.where(mask)[0])
        label = MATERIAL_NAMES.get(mat_id, f"Material {mat_id}")
        plotter.add_mesh(submesh, color=color, label=label, show_edges=False)

    plotter.add_legend(bcolor="black", border=False)
    plotter.add_title("Four-chamber heart  per-region colors", font_size=9)
    plotter.show()


def plot_single_material(mat_id: int, show_context: bool = True) -> None:
    """Render one material region, optionally with the rest as a ghost mesh."""
    mesh = load_mesh(MESH_PATH)
    material_ids = mesh.cell_data["Material"]
    mask = material_ids == mat_id
    if not mask.any():
        print(f"MaterialID {mat_id} not found in mesh.")
        return
    submesh = mesh.extract_cells(np.where(mask)[0])
    name = MATERIAL_NAMES.get(mat_id, f"Material {mat_id}")
    color = _MATERIAL_COLORS.get(mat_id, "white")
    plotter = pv.Plotter()
    if show_context:
        plotter.add_mesh(mesh, opacity=0.08, color="lightgray", show_edges=False)
    plotter.add_mesh(submesh, color=color, show_edges=False)
    plotter.add_title(f"{name}  (MaterialID {mat_id})", font_size=9)
    plotter.show()


def plot_surface(name: str) -> None:
    """Render a single STL surface mesh."""
    path = SURFACES.get(name)
    if path is None or not path.exists():
        print(f"Surface '{name}' not found. Available: {list(SURFACES.keys())}")
        return
    mesh = cast(pv.DataSet, pv.read(str(path)))
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, show_edges=True)
    plotter.add_title(f"Surface: {name}", font_size=9)
    plotter.show()


def plot_cavities_combined(opacity: float = 0.6) -> None:
    """Render all four cavity STL surfaces in one scene."""
    cavity_colors = {
        "cavityLV": "#e6194b",
        "cavityRV": "#4363d8",
        "cavityLA": "#f58231",
        "cavityRA": "#3cb44b",
    }
    plotter = pv.Plotter()
    for name, color in cavity_colors.items():
        path = SURFACES.get(name)
        if path and path.exists():
            mesh = cast(pv.DataSet, pv.read(str(path)))
            plotter.add_mesh(mesh, color=color, opacity=opacity, label=name)
    plotter.add_legend(bcolor="black", border=False)
    plotter.add_title("Four cardiac cavities", font_size=9)
    plotter.show()


def plot_mesh_with_surface_overlay(surface_name: str = "epicard", opacity: float = 0.15) -> None:
    """Render M.vtu colored by material with an STL surface overlaid as a ghost."""
    mesh = load_mesh(MESH_PATH)
    path = SURFACES.get(surface_name)
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, scalars="Material", show_edges=False, cmap="tab20")
    if path and path.exists():
        surface_mesh = cast(pv.DataSet, pv.read(str(path)))
        plotter.add_mesh(surface_mesh, opacity=opacity, color="white", show_edges=False)
    plotter.add_title(f"M.vtu + {surface_name} overlay", font_size=9)
    plotter.show()


def plot_fiber_orientation(subsample: int = 5) -> None:
    """Show fiber vectors as glyphs on a subsampled version of the mesh."""
    mesh = load_mesh(MESH_PATH)
    # Sample every nth cell to keep glyph count manageable (~129k cells total)
    cell_idx = np.arange(0, mesh.n_cells, subsample)
    submesh = mesh.extract_cells(cell_idx)
    # Convert to cell centers so arrows are placed at centroid positions
    submesh = submesh.cell_centers()
    submesh["Fiber"] = mesh.cell_data["Fiber"][cell_idx]
    glyphs = submesh.glyph(orient="Fiber", scale=False, factor=1.5)
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, opacity=0.08, color="lightgray", show_edges=False)
    plotter.add_mesh(glyphs, color="red")
    plotter.add_title(f"Fiber orientation (1 in {subsample} cells)", font_size=9)
    plotter.show()


# ---- EP mesh functions ----

def print_ep_material_distribution() -> None:
    """Print cell count per EP material ID (loads full 640MB mesh, takes ~10s)."""
    ep_mesh = cast(pv.DataSet, pv.read(str(EP_MESH_PATH)))
    material_ids = ep_mesh.cell_data["Material"]
    unique_ids, cell_counts = np.unique(material_ids, return_counts=True)
    print(f"\nEP material distribution ({ep_mesh.n_cells} total cells):")
    for mat_id, cell_count in zip(unique_ids, cell_counts):
        name = EP_MATERIAL_NAMES.get(int(mat_id), "unknown")
        print(f"  MaterialID {int(mat_id):>3}  {name:<30}  {cell_count:>9} cells  ({100*cell_count/ep_mesh.n_cells:.2f}%)")


def plot_ep_surface_per_region() -> None:
    """Extract EP.vtu surface and render with per-region colors (~15s total)."""
    ep_mesh = cast(pv.DataSet, pv.read(str(EP_MESH_PATH)))
    # dataset_surface preserves cell data arrays (vs. contour which does not)
    surface_mesh = ep_mesh.extract_surface(algorithm="dataset_surface")
    material_ids = surface_mesh.cell_data["Material"]

    plotter = pv.Plotter()
    for mat_id, color in _EP_MATERIAL_COLORS.items():
        mask = material_ids == mat_id
        if not mask.any():
            continue
        submesh = surface_mesh.extract_cells(np.where(mask)[0])
        label = EP_MATERIAL_NAMES.get(mat_id, f"Material {mat_id}")
        plotter.add_mesh(submesh, color=color, label=label, show_edges=False)

    plotter.add_legend(bcolor="black", border=False)
    plotter.add_title("EP.vtu surface  per-region colors", font_size=9)
    plotter.show()


def plot_ep_single_region(mat_id: int) -> None:
    """Extract one EP region from the surface and render with ghost context."""
    ep_mesh = cast(pv.DataSet, pv.read(str(EP_MESH_PATH)))
    # dataset_surface preserves cell data arrays (vs. contour which does not)
    surface_mesh = ep_mesh.extract_surface(algorithm="dataset_surface")
    material_ids = surface_mesh.cell_data["Material"]
    mask = material_ids == mat_id
    if not mask.any():
        print(f"EP MaterialID {mat_id} not found on surface.")
        return
    submesh = surface_mesh.extract_cells(np.where(mask)[0])
    name = EP_MATERIAL_NAMES.get(mat_id, f"Material {mat_id}")
    color = _EP_MATERIAL_COLORS.get(mat_id, "white")
    plotter = pv.Plotter()
    plotter.add_mesh(surface_mesh, opacity=0.08, color="lightgray", show_edges=False)
    plotter.add_mesh(submesh, color=color, show_edges=False)
    plotter.add_title(f"EP: {name}  (MaterialID {mat_id})", font_size=9)
    plotter.show()


if __name__ == "__main__":
    MAT_ID = 30      # M.vtu: 30=LV, 31=RV, 32=RA, 33=LA
    EP_MAT_ID = 73   # EP.vtu: 73=sinus node, 75=Bachmann bundle, 2=myocardium
    SURFACE = "epicard"

    # M.vtu inspection
    print_metadata()
    # print_material_distribution()
    # print_surface_summary()

    # M.vtu visualization
    # plot_material_colored()
    # plot_material_colored_per_region()
    # plot_single_material(MAT_ID)
    # plot_single_material(MAT_ID, show_context=False)

    # STL surfaces
    # plot_surface(SURFACE)
    # plot_cavities_combined()
    # plot_mesh_with_surface_overlay(surface_name=SURFACE)

    # M.vtu fiber vectors
    # plot_fiber_orientation(subsample=5)

    # EP.vtu
    # print_ep_material_distribution()
    # plot_ep_surface_per_region()
    # plot_ep_single_region(EP_MAT_ID)