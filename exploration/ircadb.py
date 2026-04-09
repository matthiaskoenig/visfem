"""Exploratory script for the 3D-IRCADb-01 dataset.

Static VTK surface meshes of segmented organs, 20 patients.
Structure: patient_01/ .. patient_20/*.vtk
Run sections by uncommenting the relevant call at the bottom.
"""

from pathlib import Path

import pyvista as pv

from visfem.mesh import get_metadata, load_mesh


# ---- Paths ----

_DATA_BASE = Path(__file__).parents[1] / "data" / "fem_data"
IRCADB_DIR = _DATA_BASE / "ircadb"

PATIENTS: list[int] = sorted(
    int(d.name.split("_")[-1])
    for d in IRCADB_DIR.glob("patient_*")
    if d.is_dir()
)


def _patient_dir(patient: int) -> Path:
    """Return the directory for a given patient number."""
    return IRCADB_DIR / f"patient_{patient:02d}"


def get_organ_names(patient: int) -> list[str]:
    """Return sorted organ names available for a given patient."""
    return sorted(f.stem for f in _patient_dir(patient).glob("*.vtk"))


# ---- Inspection ----

def print_organ_inventory() -> None:
    """Print which organs are available across all patients."""
    all_organs: set[str] = set()
    patient_organs: dict[int, list[str]] = {}

    for patient in PATIENTS:
        organs = get_organ_names(patient)
        patient_organs[patient] = organs
        all_organs.update(organs)

    all_organs_sorted = sorted(all_organs)
    print(f"\n{'Organ':<30} {'Patients available'}")
    print("=" * 60)
    for organ in all_organs_sorted:
        available = [str(p) for p in PATIENTS if organ in patient_organs[p]]
        print(f"{organ:<30} {', '.join(available)}")

    print(f"\nTotal unique organs across all patients: {len(all_organs_sorted)}")
    print(f"Patients: {len(PATIENTS)}")


def print_patient_summary(patient: int) -> None:
    """Print organ list and mesh stats for one patient."""
    organs = get_organ_names(patient)
    print(f"\nPatient {patient} ({len(organs)} organs):")
    for organ in organs:
        mesh = load_mesh(_patient_dir(patient) / f"{organ}.vtk")
        print(f"  {organ:<25} {mesh.n_points:>6} pts  {mesh.n_cells:>6} cells")


def generate_metadata(patient: int) -> None:
    """Generate and print metadata for all organ meshes of one patient."""
    organs = get_organ_names(patient)
    print(f"\nGenerating metadata for patient {patient}...")
    for organ in organs:
        meta = get_metadata(_patient_dir(patient) / f"{organ}.vtk")
        print(f"  {organ}: {meta['n_points']} pts, {meta['n_cells']} cells, "
              f"cell_types: {meta['cell_types']}")


def generate_all_metadata() -> None:
    """Generate metadata for all organs across all patients."""
    for patient in PATIENTS:
        generate_metadata(patient)


# ---- Visualization ----

def plot_organ(patient: int, organ: str) -> None:
    """Load and display a single organ mesh."""
    mesh = load_mesh(_patient_dir(patient) / f"{organ}.vtk")
    print(f"Patient {patient}  {organ}: {mesh.n_points} pts, {mesh.n_cells} cells")
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, show_edges=True)
    plotter.add_title(f"Patient {patient}  {organ}", font_size=10)
    plotter.show()


def plot_organs_combined(patient: int, organs: list[str], opacity: float = 1.0) -> None:
    """Render a list of organs for one patient in a single scene with distinct colors."""
    colors = [
        "red", "blue", "green", "orange", "purple",
        "cyan", "magenta", "yellow", "brown", "pink",
    ]
    plotter = pv.Plotter()

    for organ_idx, organ in enumerate(organs):
        path = _patient_dir(patient) / f"{organ}.vtk"
        if not path.exists():
            print(f"  WARNING: {organ} not found for patient {patient}, skipping.")
            continue
        mesh = load_mesh(path)
        plotter.add_mesh(mesh, color=colors[organ_idx % len(colors)], opacity=opacity, label=organ)
        print(f"  {organ}: {mesh.n_points} pts, {mesh.n_cells} cells")

    plotter.add_legend()
    plotter.add_title(f"Patient {patient}  {', '.join(organs)}", font_size=8)
    plotter.show()


def plot_all_organs(patient: int, opacity: float = 0.5) -> None:
    """Render all organs for one patient in a single scene."""
    organs = get_organ_names(patient)
    print(f"\nRendering all {len(organs)} organs for patient {patient}...")
    plot_organs_combined(patient, organs, opacity=opacity)


if __name__ == "__main__":
    PATIENT = 1      # change to any patient 1 to 20
    ORGAN = "liver"  # use print_organ_inventory() or print_patient_summary() to see available organs

    # Inspection
    print_organ_inventory()
    # print_patient_summary(PATIENT)
    # generate_metadata(PATIENT)
    generate_all_metadata()

    # Single organ
    # plot_organ(PATIENT, ORGAN)

    # Selected organs in one scene
    # plot_organs_combined(PATIENT, ["liver", "livertumor01", "livertumor02"], opacity=0.5)

    # All organs for one patient
    # plot_all_organs(PATIENT)
    # plot_all_organs(PATIENT, opacity=0.3)