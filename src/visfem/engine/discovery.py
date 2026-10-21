"""Dataset discovery and project metadata helpers."""

import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from visfem.log import get_logger
from visfem.models import ProjectMetadata

logger = get_logger(__name__)

# ---- Paths ----

# Datasets default to <repo>/data/datasets, a path that resolves only from an editable checkout; a deployment sets DATA_DIR or VISFEM_DATA_DIR to the mounted data directory.
_DATA_ENV = os.environ.get("DATA_DIR") or os.environ.get("VISFEM_DATA_DIR")
DATASETS_DIR = (
    (Path(_DATA_ENV) / "datasets")
    if _DATA_ENV
    else (Path(__file__).parents[3] / "data" / "datasets")
)

# VISFEM_DATASETS is a comma-separated allowlist of dataset keys; empty exposes every dataset and deployment sets the SPP2311 subset.
_DATASETS_ENV = os.environ.get("VISFEM_DATASETS", "").strip()
ALLOWED_DATASETS: set[str] | None = (
    {k.strip() for k in _DATASETS_ENV.split(",") if k.strip()}
    if _DATASETS_ENV
    else None
)


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
    """Return *name* with a space inserted after a known leading prefix word."""
    _prefixes = (
        "left",
        "right",
        "small",
        "large",
        "portal",
        "surrenal",
        "vena",
        "venous",
        "biliary",
    )
    lower = name.lower()
    for prefix in _prefixes:
        if lower.startswith(prefix) and len(name) > len(prefix):
            return name[: len(prefix)] + " " + name[len(prefix) :]
    return name


def xdmf_display_name(stem: str) -> str:
    """Return a readable display name for an XDMF *stem*."""
    if stem.startswith("lobule_sixth_"):
        suffix = stem[len("lobule_sixth_") :]
        if suffix:
            return suffix
    return stem.replace("_", " ").title()


# ---- Metadata ----


def iter_descriptor_paths() -> list[Path]:
    """Return the sorted paths of every dataset descriptor JSON under DATASETS_DIR."""
    # A .meta.json sidecar is a cache.
    return [
        p
        for p in sorted(DATASETS_DIR.rglob("*.json"))
        if not p.name.endswith(".meta.json")
    ]


def load_descriptor(path: Path) -> ProjectMetadata:
    """Return the validated ProjectMetadata parsed from the JSON at *path*; raises ValidationError or OSError."""
    return ProjectMetadata.model_validate_json(path.read_text(encoding="utf-8"))


def load_project_metadata() -> dict[str, ProjectMetadata]:
    """Return ProjectMetadata for each readable, valid dataset JSON under DATASETS_DIR, keyed by file stem and filtered by ALLOWED_DATASETS."""
    result: dict[str, ProjectMetadata] = {}
    if not DATASETS_DIR.is_dir():
        logger.warning(f"Datasets directory missing: {DATASETS_DIR} (set DATA_DIR)")
        return result
    for path in iter_descriptor_paths():
        key = path.stem
        if ALLOWED_DATASETS is not None and key not in ALLOWED_DATASETS:
            continue
        if key in result:
            logger.warning(
                f"Skipping '{path}': dataset key '{key}' is already loaded from another JSON"
            )
            continue
        try:
            result[key] = load_descriptor(path)
        except (ValidationError, ValueError, OSError) as e:
            reason = " ".join(line.strip() for line in str(e).splitlines()[:2])
            logger.warning(f"Skipping dataset '{path}': {reason}")
    return result


def patient_numbers(ddir: Path) -> list[int]:
    """Return the sorted numeric ids of the ``patient_<n>`` folders in *ddir*."""
    numbers: list[int] = []
    for d in ddir.glob("patient_*"):
        suffix = d.name.removeprefix("patient_")
        if d.is_dir() and suffix.isdigit():
            numbers.append(int(suffix))
    return sorted(numbers)


def group_by_organ_system(
    metadata: dict[str, ProjectMetadata],
) -> dict[str, list[tuple[str, ProjectMetadata]]]:
    """Return the datasets in *metadata* grouped by first organ_system value, groups sorted by that value and entries by sort_order then name."""
    groups: dict[str, list[tuple[str, ProjectMetadata]]] = {}
    for key, meta in metadata.items():
        system = meta.organ_system[0].value
        groups.setdefault(system, [])
        groups[system].append((key, meta))

    def _sort_key(t: tuple[str, ProjectMetadata]) -> tuple[int, str]:
        """Return the (sort_order, name) sort key of a (key, meta) pair."""
        meta = t[1]
        # 999 sorts entries without sort_order last.
        return (meta.sort_order if meta.sort_order is not None else 999, meta.name)

    return {
        system: sorted(items, key=_sort_key) for system, items in sorted(groups.items())
    }


def dataset_dir(meta: ProjectMetadata) -> Path:
    """Return the dataset directory for *meta*."""
    return DATASETS_DIR / meta.data_path


def pvd_file_path(meta: ProjectMetadata) -> Path | None:
    """Return the PVD file path for PVD-format datasets, else None."""
    if meta.mesh_format == "PVD":
        return DATASETS_DIR / meta.data_path
    return None


def patient_subdir(ddir: Path, patient: int) -> Path:
    """Return the ``patient_NN`` folder for *patient* under *ddir*."""
    return ddir / f"patient_{int(patient):02d}"


def active_timeseries_path(
    meta: ProjectMetadata, state: Any, ddir: Path
) -> Path | None:
    """Return the active timeseries file of *meta*: its PVD for a PVD dataset, else the XDMF in *ddir* named by ``state.active_xdmf``, else the first XDMF in *ddir*, else None."""
    if meta.mesh_format == "PVD":
        return pvd_file_path(meta)
    xdmf_files = discover_xdmf(ddir)
    stem: str | None = state.active_xdmf
    return xdmf_files.get(stem) if stem else next(iter(xdmf_files.values()), None)


def grasp_phase_pvd(patient_dir: Path) -> Path | None:
    """Return the per-patient GRASP phase-series PVD path, or None if absent."""
    pvd = patient_dir / "tissue_surface.pvd"
    return pvd if pvd.exists() else None


def grasp_phase_count(pvd_path: Path) -> int:
    """Return the number of contrast phases in a GRASP per-patient PVD."""
    from visfem.mesh import pvd_steps

    return len(pvd_steps(pvd_path))


def meta_to_state(meta: ProjectMetadata) -> dict[str, object]:
    """Return a plain dict of *meta* for Trame state."""
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
