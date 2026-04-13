"""Exploratory script for the tibia dataset (SPP Use Case 1).

Mesh and simulation results from orthopedic trauma surgery digital twin.
Data from Annchristin Andres, Applied Mechanics / Biomechanics, Uni Saarland.
Reference: 'Advantages of digital twin technology in orthopedic trauma Surgery'
"""

from pathlib import Path

import pyvista as pv


# ---- Paths ----

_DATA_BASE = Path(__file__).parents[1] / "data" / "fem_data"
TIBIA_DIR  = _DATA_BASE / "tibia"
MESH_PATH  = TIBIA_DIR / "Tibia_Mesh.vtk"
SIM_PATH   = TIBIA_DIR / "Tibia_Simulation.vtk"


# ---- Inspection ----

def print_summary() -> None:
    """Print basic info for both tibia VTK files."""
    for path in (MESH_PATH, SIM_PATH):
        print(f"\n=== {path.name} ===")
        mesh = pv.read(str(path))
        print(f"  type       : {type(mesh).__name__}")
        print(f"  points     : {mesh.n_points}")
        print(f"  cells      : {mesh.n_cells}")
        print(f"  bounds     : x=[{mesh.bounds[0]:.1f}, {mesh.bounds[1]:.1f}]  "
              f"y=[{mesh.bounds[2]:.1f}, {mesh.bounds[3]:.1f}]  "
              f"z=[{mesh.bounds[4]:.1f}, {mesh.bounds[5]:.1f}]")
        print(f"  cell_types : {list(set(str(ct) for ct in mesh.celltypes))}")
        print(f"  point_data : {list(mesh.point_data.keys())}")
        print(f"  cell_data  : {list(mesh.cell_data.keys())}")
        for name, arr in mesh.point_data.items():
            print(f"    [point] {name:<30} shape={arr.shape}  dtype={arr.dtype}")
        for name, arr in mesh.cell_data.items():
            print(f"    [cell]  {name:<30} shape={arr.shape}  dtype={arr.dtype}")

def print_part_ids() -> None:
    """Print unique PartId and PartIdTo values for both meshes."""
    import numpy as np

    for path in (MESH_PATH, SIM_PATH):
        mesh = pv.read(str(path))
        print(f"\n=== {path.name} ===")
        for array_name in ("PartId", "PartIdTo", "Mask_ID"):
            if array_name not in mesh.cell_data:
                continue
            arr = mesh.cell_data[array_name].astype(int)
            unique, counts = np.unique(arr, return_counts=True)
            print(f"  {array_name}:")
            for val, cnt in zip(unique, counts):
                print(f"    {val:>4}  {cnt:>8} cells  ({100*cnt/mesh.n_cells:.1f}%)")

    # Also check value ranges for key simulation fields
    print("\n=== Tibia_Simulation.vtk field ranges ===")
    sim = pv.read(str(SIM_PATH))
    for name in ("vonMises_stress", "vonMises_equivalent_strain",
                 "Claes_window", "Frost_window", "Mask_ID"):
        if name in sim.cell_data:
            arr = sim.cell_data[name]
            print(f"  {name:<35} min={arr.min():.4f}  max={arr.max():.4f}")

def plot_tibia_parts() -> None:
    """Render Tibia_Mesh colored by PartId to identify regions visually."""
    import numpy as np

    mesh = pv.read(str(MESH_PATH))
    part_ids = mesh.cell_data["PartId"].astype(int)
    unique_ids = sorted(np.unique(part_ids))

    colors = ["#e8e0d0", "#e8603c", "#4363d8"]  # bone=beige, callus/fracture=orange, implant=blue
    plotter = pv.Plotter()
    for i, pid in enumerate(unique_ids):
        mask = part_ids == pid
        submesh = mesh.extract_cells(mask)
        plotter.add_mesh(submesh, color=colors[i], label=f"PartId {pid}", show_edges=False)
    plotter.add_legend(bcolor="black", border=False)
    plotter.add_title("Tibia_Mesh colored by PartId", font_size=9)
    plotter.show()


def plot_tibia_simulation() -> None:
    """Render Tibia_Simulation colored by vonMises_stress."""
    sim = pv.read(str(SIM_PATH))
    plotter = pv.Plotter()
    plotter.add_mesh(sim, scalars="vonMises_stress", cmap="turbo",
                     show_edges=False, show_scalar_bar=True)
    plotter.add_title("Tibia Simulation — von Mises stress", font_size=9)
    plotter.show()



if __name__ == "__main__":
    # print_summary()
    # print_part_ids()
    # plot_tibia_parts()
    plot_tibia_simulation()