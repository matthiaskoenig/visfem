"""Dataset discovery and project metadata helpers."""
from pathlib import Path

from visfem.models import ProjectMetadata

# ---- Paths ----

DATASETS_DIR = Path(__file__).parents[3] / "data" / "datasets"


# ---- Discovery ----

def discover_xdmf(directory: Path) -> dict[str, Path]:
    """Return stem->path for all .xdmf files with a matching .h5 in directory."""
    return {
        p.stem: p
        for p in sorted(directory.glob("*.xdmf"))
        if p.with_suffix(".h5").exists()
    }


def ircadb_organ_names(patient_dir: Path) -> list[str]:
    """Return sorted organ names available for a patient directory."""
    return sorted(f.stem for f in patient_dir.glob("*.vtk"))


def format_organ_name(name: str) -> str:
    """Insert space before known prefix words in organ names."""
    _prefixes = ("left", "right", "small", "large", "portal", "surrenal", "vena", "venous", "biliary")
    lower = name.lower()
    for prefix in _prefixes:
        if lower.startswith(prefix) and len(name) > len(prefix):
            return name[:len(prefix)] + " " + name[len(prefix):]
    return name


def xdmf_display_name(stem: str) -> str:
    """Convert an XDMF stem to a readable display name."""
    if stem.startswith("lobule_sixth_"):
        suffix = stem[len("lobule_sixth_"):]
        if suffix:
            return suffix
    return stem.replace("_", " ").title()


# ---- Metadata ----

def load_project_metadata() -> dict[str, ProjectMetadata]:
    """Load and validate all ProjectMetadata JSONs from data/datasets/."""
    result: dict[str, ProjectMetadata] = {}
    for path in sorted(DATASETS_DIR.rglob("*.json")):
        if path.name.endswith(".meta.json"):
            continue
        result[path.stem] = ProjectMetadata.model_validate_json(path.read_text())
    return result


def group_by_organ_system(
    metadata: dict[str, ProjectMetadata],
) -> dict[str, list[tuple[str, ProjectMetadata]]]:
    """Group datasets by first organ_system value, sorted alphabetically by name."""
    groups: dict[str, list[tuple[str, ProjectMetadata]]] = {}
    for key, meta in metadata.items():
        system = meta.organ_system[0].value
        groups.setdefault(system, [])
        groups[system].append((key, meta))
    def _sort_key(t: tuple[str, ProjectMetadata]) -> tuple[int, str]:
        meta = t[1]
        return (meta.sort_order if meta.sort_order is not None else 999, meta.name)
    return {system: sorted(items, key=_sort_key) for system, items in sorted(groups.items())}


def dataset_dir(meta: ProjectMetadata) -> Path:
    """Resolve the filesystem directory for a dataset from its metadata."""
    return DATASETS_DIR / meta.data_path


def pvd_file_path(meta: ProjectMetadata) -> Path | None:
    """Return the PVD file path for PVD-format datasets, else None."""
    if meta.mesh_format == "PVD":
        return DATASETS_DIR / meta.data_path
    return None

def meta_to_state(meta: ProjectMetadata) -> dict[str, object]:
    """Serialize a ProjectMetadata instance to a plain dict for Trame state."""
    return {
        "name": meta.name,
        "pi": meta.pi,
        "institution": meta.institution,
        "biological_scale": meta.biological_scale.value.replace("_", " ").title(),
        "organ_system": [s.value.replace("_", " ").title() for s in meta.organ_system],
        "description": meta.description,
        "mesh_format": meta.mesh_format,
        "ref_urls": [r for r in meta.references if r.startswith("http")],
        "ref_texts": [r for r in meta.references if not r.startswith("http")],
        "spp_project": meta.spp_project,
        "spp_badge": meta.spp_badge or bool(meta.spp_project),
    }