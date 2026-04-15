"""Exploration script for heart datasets.

Static meshes
-------------
  M.vtu   mechanical volumetric mesh (~129k tetra, 12 material regions)
  EP.vtu  electrophysiology volumetric mesh (640 MB, 7.4M cells)
  surfaces/  pre-extracted STL cavity / epicardium surfaces

Timeseries (IV)
---------------
  IV.pvd  PVD index ~1600 timesteps
  IV_vtu/ per-timestep VTU files
"""

from pathlib import Path
from typing import cast
import xml.etree.ElementTree as ET

import numpy as np
import pyvista as pv

from visfem.console import console
from visfem.mesh import get_metadata, load_mesh


# Paths
_DATA_BASE   = Path(__file__).parents[1] / "data" / "fem_data"
HEART_DIR    = _DATA_BASE / "heart"

# Static meshes
MESH_PATH    = HEART_DIR / "M.vtu"
EP_MESH_PATH = HEART_DIR / "EP.vtu"
SURFACE_DIR  = HEART_DIR / "surfaces"

# STL surfaces
SURFACES: dict[str, Path] = {p.stem: p for p in sorted(SURFACE_DIR.glob("*.stl"))}

# IV timeseries
PVD_PATH = HEART_DIR / "IV.pvd"
VTU_DIR  = HEART_DIR / "IV_vtu"

# Steps to sample for IV range / topology checks
IV_SAMPLE_STEPS = [0, 100, 400, 800, 1200, 1600]



# Material ID tables
# M.vtu mechanical mesh
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

# EP.vtu electrophysiology mesh
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

_EP_MATERIAL_COLORS: dict[int, str] = {
    1:  "#c0152a",   # ventricle endocardium
    2:  "#e8603c",   # ventricle myocardium
    3:  "#f4a261",   # ventricle epicardium
    32: "#d45087",   # RA bulk
    33: "#ff6b9d",   # LA bulk
    72: "#4363d8",   # crista terminalis
    73: "#f032e6",   # sinus node
    74: "#9b2d7f",   # pectinate muscles
    75: "#42d4f4",   # Bachmann bundle
    76: "#3cb44b",   # middle posterior bridge
    77: "#bfef45",   # lower posterior bridge
    78: "#469990",   # coronary sinus bridge
    79: "#ffb347",   # atrial appendage
    80: "#c77dff",   # inferior isthmus
}


# Inspection static meshes (M.vtu / EP.vtu / surfaces)

def print_metadata() -> None:
    """Print metadata summary for M.vtu."""
    meta = get_metadata(MESH_PATH)
    print("\nM.vtu")
    print(f"  format     : {meta.format}")
    print(f"  n_points   : {meta.n_points}")
    print(f"  n_cells    : {meta.n_cells}")
    print(f"  cell_types : {meta.cell_types}")
    print(f"  fields ({len(meta.fields)}):")
    for name, info in meta.fields.items():
        print(f"    {name:<20} center={info.center}  shape={info.shape}")


def print_material_distribution() -> None:
    """Print cell count per material ID in M.vtu."""
    mesh = load_mesh(MESH_PATH)
    material_ids = mesh.cell_data["Material"]
    unique_ids, cell_counts = np.unique(material_ids, return_counts=True)
    print(f"\nMaterial distribution ({mesh.n_cells} total cells):")
    for mat_id, cell_count in zip(unique_ids, cell_counts):
        name = MATERIAL_NAMES.get(int(mat_id), "unknown")
        print(f"  MaterialID {int(mat_id):>3}  {name:<35}  {cell_count:>6} cells  ({100*cell_count/mesh.n_cells:.1f}%)")


def print_ep_material_distribution() -> None:
    """Print cell count per EP material ID (loads full 640 MB mesh, ~10 s)."""
    ep_mesh = cast(pv.DataSet, pv.read(str(EP_MESH_PATH)))
    material_ids = ep_mesh.cell_data["Material"]
    unique_ids, cell_counts = np.unique(material_ids, return_counts=True)
    print(f"\nEP material distribution ({ep_mesh.n_cells} total cells):")
    for mat_id, cell_count in zip(unique_ids, cell_counts):
        name = EP_MATERIAL_NAMES.get(int(mat_id), "unknown")
        print(f"  MaterialID {int(mat_id):>3}  {name:<30}  {cell_count:>9} cells  ({100*cell_count/ep_mesh.n_cells:.2f}%)")


def print_surface_summary() -> None:
    """Print point/cell counts for all STL surface files."""
    print("\nSurface meshes:")
    for name, path in SURFACES.items():
        if path.exists():
            mesh = cast(pv.DataSet, pv.read(str(path)))
            print(f"  {name:<15}  {mesh.n_points:>6} pts  {mesh.n_cells:>6} cells")
        else:
            print(f"  {name:<15}  NOT FOUND")


def print_heart_data_summary() -> None:
    """Print a full summary of all heart data files (M, EP, surfaces, ep_surface)."""
    print("\n=== M.vtu (mechanical volumetric mesh) ===")
    m = pv.read(str(MESH_PATH))
    print(f"  points: {m.n_points}, cells: {m.n_cells}")
    print(f"  arrays: {m.array_names}")
    for mid, cnt in zip(*np.unique(m.cell_data["Material"].astype(int), return_counts=True)):
        print(f"    Material {int(mid):>3}  {MATERIAL_NAMES.get(int(mid), 'unknown'):<35} {cnt:>7} cells")

    print("\n=== EP.vtu (electrophysiology volumetric mesh) ===")
    ep = pv.read(str(EP_MESH_PATH))
    print(f"  points: {ep.n_points}, cells: {ep.n_cells}")
    print(f"  arrays: {ep.array_names}")
    for mid, cnt in zip(*np.unique(ep.cell_data["Material"].astype(int), return_counts=True)):
        print(f"    Material {int(mid):>3}  {EP_MATERIAL_NAMES.get(int(mid), 'unknown'):<35} {cnt:>7} cells")

    print("\n=== surfaces/ STL files (pre-extracted surfaces) ===")
    for name, path in SURFACES.items():
        mesh = pv.read(str(path))
        print(f"  {name:<20} {mesh.n_points:>7} pts  {mesh.n_cells:>7} cells  arrays={mesh.array_names}")

    print("\n=== ep_surface.vtp (extracted EP outer surface) ===")
    ep_surf_path = SURFACE_DIR / "ep_surface.vtp"
    if ep_surf_path.exists():
        ep_surf = pv.read(str(ep_surf_path))
        print(f"  points: {ep_surf.n_points}, cells: {ep_surf.n_cells}")
        print(f"  arrays: {ep_surf.array_names}")
        for mid, cnt in zip(*np.unique(ep_surf.cell_data["Material"].astype(int), return_counts=True)):
            print(f"    Material {int(mid):>3}  {EP_MATERIAL_NAMES.get(int(mid), 'unknown'):<35} {cnt:>7} cells")
    else:
        print("  NOT FOUND. un extract_ep_surface() first")


# Inspection IV timeseries (PVD + VTU)
def inspect_pvd(pvd_path: Path = PVD_PATH) -> dict[int, Path]:
    """Parse PVD index, print summary, return step -> vtu_path mapping."""
    console.rule("[bold]PVD index")
    tree = ET.parse(pvd_path)
    datasets = tree.findall(".//DataSet")
    console.print(f"Total timesteps: {len(datasets)}")
    console.print(f"t_start: {datasets[0].attrib.get('timestep')}")
    console.print(f"t_end:   {datasets[-1].attrib.get('timestep')}")
    return {i: pvd_path.parent / ds.attrib["file"] for i, ds in enumerate(datasets)}


def inspect_vtu_fields(vtu_path: Path) -> pv.UnstructuredGrid:
    """Load a VTU and print mesh + field info."""
    console.rule(f"[bold]VTU: {vtu_path.name}")
    mesh = pv.read(vtu_path)
    console.print(f"Type:       {type(mesh).__name__}")
    console.print(f"n_points:   {mesh.n_points}")
    console.print(f"n_cells:    {mesh.n_cells}")
    console.print(f"Bounds:     {[round(b, 4) for b in mesh.bounds]}")
    console.print(f"Cell types: {set(mesh.celltypes.tolist())}")

    console.print("\n[bold]Point data fields:")
    for name, arr in mesh.point_data.items():
        console.print(f"  {name:<30} shape={str(arr.shape):<18} dtype={arr.dtype}  "
                      f"min={arr.min():.4g}  max={arr.max():.4g}")

    console.print("\n[bold]Cell data fields:")
    for name, arr in mesh.cell_data.items():
        console.print(f"  {name:<30} shape={str(arr.shape):<18} dtype={arr.dtype}  "
                      f"min={arr.min():.4g}  max={arr.max():.4g}")
    return mesh


def check_iv_topology_consistency(
    step_to_path: dict[int, Path],
    steps: list[int] = IV_SAMPLE_STEPS,
) -> None:
    """Verify mesh topology (n_points, n_cells, point coords) is identical across steps."""
    console.rule("[bold]IV topology consistency check")
    reference: tuple[int, int] | None = None
    reference_points: np.ndarray | None = None

    for step in steps:
        mesh = pv.read(step_to_path[step])
        if reference is None:
            reference = (mesh.n_points, mesh.n_cells)
            reference_points = mesh.points.copy()
            console.print(f"  Step {step:>4}: reference  -  n_points={mesh.n_points}  n_cells={mesh.n_cells}")
            continue
        assert reference_points is not None
        points_identical = np.allclose(mesh.points, reference_points)
        topology_match = (mesh.n_points, mesh.n_cells) == reference
        status = "[green]OK[/green]" if (topology_match and points_identical) else "[red]MISMATCH[/red]"
        console.print(f"  Step {step:>4}: {status}  -  n_points={mesh.n_points}  n_cells={mesh.n_cells}  points_identical={points_identical}")


def inspect_iv_field_ranges(
    step_to_path: dict[int, Path],
    steps: list[int] = IV_SAMPLE_STEPS,
) -> None:
    """Print min/max of each field across sampled IV steps."""
    console.rule("[bold]IV field ranges across sampled steps")
    point_ranges: dict[str, list] = {}
    cell_ranges: dict[str, list] = {}

    for step in steps:
        mesh = pv.read(step_to_path[step])
        for name, arr in mesh.point_data.items():
            point_ranges.setdefault(name, [np.inf, -np.inf])
            point_ranges[name][0] = min(point_ranges[name][0], float(arr.min()))
            point_ranges[name][1] = max(point_ranges[name][1], float(arr.max()))
        for name, arr in mesh.cell_data.items():
            cell_ranges.setdefault(name, [np.inf, -np.inf])
            cell_ranges[name][0] = min(cell_ranges[name][0], float(arr.min()))
            cell_ranges[name][1] = max(cell_ranges[name][1], float(arr.max()))

    console.print(f"Sampled steps: {steps}\n")
    console.print("[bold]Point data:")
    for name, (lo, hi) in point_ranges.items():
        console.print(f"  {name:<30} min={lo:.4g}  max={hi:.4g}")
    console.print("\n[bold]Cell data:")
    for name, (lo, hi) in cell_ranges.items():
        console.print(f"  {name:<30} min={lo:.4g}  max={hi:.4g}")


# Visualization M.vtu (mechanical mesh)
def plot_material_colored() -> None:
    """Render M.vtu colored by MaterialID scalar."""
    mesh = load_mesh(MESH_PATH)
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, scalars="Material", show_edges=False, cmap="tab20")
    plotter.add_title("Four-chamber heart  colored by MaterialID", font_size=9)
    plotter.show()


def plot_material_colored_per_region() -> None:
    """Render each material region as a separate actor with anatomical colors."""
    mesh = load_mesh(MESH_PATH)
    material_ids = mesh.cell_data["Material"]
    plotter = pv.Plotter()
    for mat_id, color in _MATERIAL_COLORS.items():
        mask = material_ids == mat_id
        if not mask.any():
            continue
        submesh = mesh.extract_cells(np.where(mask)[0])
        plotter.add_mesh(submesh, color=color, label=MATERIAL_NAMES.get(mat_id, f"Material {mat_id}"), show_edges=False)
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


def plot_fiber_orientation(subsample: int = 5) -> None:
    """Show fiber vectors as glyphs on a subsampled mesh."""
    mesh = load_mesh(MESH_PATH)
    cell_idx = np.arange(0, mesh.n_cells, subsample)
    submesh = mesh.extract_cells(cell_idx).cell_centers()
    submesh["Fiber"] = mesh.cell_data["Fiber"][cell_idx]
    glyphs = submesh.glyph(orient="Fiber", scale=False, factor=1.5)
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, opacity=0.5, color="darkgray", show_edges=False)
    plotter.add_mesh(glyphs, color="red")
    plotter.add_title(f"Fiber orientation (1 in {subsample} cells)", font_size=9)
    plotter.show()


# Visualization surfaces (STL)
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


# Visualization EP.vtu (electrophysiology mesh)
def plot_ep_surface_per_region() -> None:
    """Extract EP.vtu surface and render with per-region colors (~15 s total)."""
    ep_mesh = cast(pv.DataSet, pv.read(str(EP_MESH_PATH)))
    surface_mesh = ep_mesh.extract_surface(algorithm="dataset_surface")
    material_ids = surface_mesh.cell_data["Material"]
    plotter = pv.Plotter()
    for mat_id, color in _EP_MATERIAL_COLORS.items():
        mask = material_ids == mat_id
        if not mask.any():
            continue
        submesh = surface_mesh.extract_cells(np.where(mask)[0])
        plotter.add_mesh(submesh, color=color, label=EP_MATERIAL_NAMES.get(mat_id, f"Material {mat_id}"), show_edges=False)
    plotter.add_legend(bcolor="black", border=False)
    plotter.add_title("EP.vtu surface  per-region colors", font_size=9)
    plotter.show()


def plot_ep_single_region(mat_id: int) -> None:
    """Extract one EP region from the surface and render with ghost context."""
    ep_mesh = cast(pv.DataSet, pv.read(str(EP_MESH_PATH)))
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


# Utility
def extract_ep_surface() -> None:
    """Extract EP.vtu outer surface and save as ep_surface.vtp.

    Preserves the Material cell array for per-region coloring in the app.
    Output: data/fem_data/heart/surfaces/ep_surface.vtp
    """
    out_path = SURFACE_DIR / "ep_surface.vtp"
    if out_path.exists():
        print(f"Already exists: {out_path}")
        return
    print("Loading EP.vtu (~640 MB) ...")
    ep_mesh = pv.read(str(EP_MESH_PATH))
    print(f"  {ep_mesh.n_points} points, {ep_mesh.n_cells} cells")
    print("Extracting surface ...")
    surface = ep_mesh.extract_surface(algorithm="dataset_surface")
    print(f"  surface: {surface.n_points} points, {surface.n_cells} cells")
    for arr in list(surface.point_data.keys()):
        del surface.point_data[arr]
    for arr in list(surface.cell_data.keys()):
        if arr != "Material":
            del surface.cell_data[arr]
    surface.save(str(out_path))
    print(f"Saved: {out_path}  ({out_path.stat().st_size / 1e6:.1f} MB)")



if __name__ == "__main__":

    # --- Basic data summary (always on) ---
    print_heart_data_summary()

    
    # Inspection static meshes
    
    # print_metadata()
    # print_material_distribution()
    # print_ep_material_distribution()
    # print_surface_summary()

    
    # Inspection IV timeseries
    
    # step_to_path = inspect_pvd()
    # inspect_vtu_fields(step_to_path[0])
    # check_iv_topology_consistency(step_to_path)
    # inspect_iv_field_ranges(step_to_path)

    
    # Visualization M.vtu
    
    # plot_material_colored()
    # plot_material_colored_per_region()
    # plot_single_material(30)  # Left ventricle
    # plot_fiber_orientation(subsample=5)

    
    # Visualization surfaces (STL)
    
    # plot_surface("epicard")
    # plot_cavities_combined()
    # plot_mesh_with_surface_overlay("epicard")

    
    # Visualization EP.vtu
    
    # plot_ep_surface_per_region()
    # plot_ep_single_region(73)  # Sinus node

    
    # Utility
    
    # extract_ep_surface()
