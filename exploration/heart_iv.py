"""Exploration script for heart IV timeseries (PVD + VTU)."""

from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import pyvista as pv
from visfem.console import console

# --- Paths ---
HEART_DIR = Path("data/fem_data/heart")
PVD_PATH = HEART_DIR / "IV.pvd"
VTU_DIR = HEART_DIR / "IV_vtu"

# Steps to sample for consistency + range checks
SAMPLE_STEPS = [0, 100, 400, 800, 1200, 1600]


# --- PVD inspection ---
def inspect_pvd(pvd_path: Path) -> dict[int, Path]:
    """Parse PVD index, print summary, return step -> vtu_path mapping."""
    console.rule("[bold]PVD index")
    tree = ET.parse(pvd_path)
    datasets = tree.findall(".//DataSet")
    console.print(f"Total timesteps: {len(datasets)}")
    console.print(f"t_start: {datasets[0].attrib.get('timestep')}")
    console.print(f"t_end:   {datasets[-1].attrib.get('timestep')}")

    step_to_path = {
        i: pvd_path.parent / ds.attrib["file"]
        for i, ds in enumerate(datasets)
    }
    return step_to_path


# --- Single VTU inspection ---
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


# --- Topology consistency check ---
def check_topology_consistency(step_to_path: dict[int, Path], steps: list[int]) -> None:
    """Check that mesh topology (n_points, n_cells, points) is identical across steps."""
    console.rule("[bold]Topology consistency check")
    reference = None
    reference_points = None

    for step in steps:
        path = step_to_path[step]
        mesh = pv.read(path)
        if reference is None:
            reference = (mesh.n_points, mesh.n_cells)
            reference_points = mesh.points.copy()
            console.print(f"  Step {step:>4}: reference  —  n_points={mesh.n_points}  n_cells={mesh.n_cells}")
            continue

        points_identical = np.allclose(mesh.points, reference_points)
        topology_match = (mesh.n_points, mesh.n_cells) == reference
        status = "[green]OK[/green]" if (topology_match and points_identical) else "[red]MISMATCH[/red]"
        console.print(f"  Step {step:>4}: {status}  —  n_points={mesh.n_points}  n_cells={mesh.n_cells}  points_identical={points_identical}")


# --- Field range across sampled steps ---
def inspect_field_ranges(step_to_path: dict[int, Path], steps: list[int]) -> None:
    """Print min/max of each field across sampled steps to find meaningful value ranges."""
    console.rule("[bold]Field ranges across sampled steps")

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


# --- Main ---
if __name__ == "__main__":
    step_to_path = inspect_pvd(PVD_PATH)
    inspect_vtu_fields(step_to_path[0])
    check_topology_consistency(step_to_path, SAMPLE_STEPS)
    inspect_field_ranges(step_to_path, SAMPLE_STEPS)