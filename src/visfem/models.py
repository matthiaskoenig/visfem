"""Pydantic models for mesh and project metadata validation.

Two distinct metadata types:
  MeshMetadata     -- auto-generated from mesh files, cached as .meta.json sidecars
  ProjectMetadata  -- hand-authored per dataset, stored in data/datasets/**/*.json
"""

import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, Field


# ===========================================================================
# MeshMetadata
# Auto-generated from mesh files and cached as .meta.json sidecars.
# ===========================================================================

class FieldInfo(BaseModel):
    """Descriptor for one scalar/vector/tensor field on a mesh."""
    center: str       # "point" or "cell"
    shape: list[int]  # [1] scalar, [3] vector, [3, 3] tensor


class MeshMetadata(BaseModel):
    """Auto-generated metadata for a single mesh file.

    Cached as a .meta.json sidecar to avoid re-parsing the (potentially large)
    mesh file on every startup. Sidecars are automatically invalidated and
    regenerated when the schema changes, detected via schema_hash.
    """
    schema_hash: str = ""
    format: str           # fenics_xdmf | timeseries_xdmf | pyvista_native | meshio_fallback
    n_steps: int = Field(ge=1)
    times: list[float]    # empty for static datasets
    n_points: int = Field(ge=0)
    n_cells: int = Field(ge=0)
    cell_types: list[str]
    fields: dict[str, FieldInfo]
    bounds: tuple[float, float, float, float, float, float] | None = None
    # xmin, xmax, ymin, ymax, zmin, zmax -- None if not precomputed
    scalar_bounds: dict[str, list[float]] = {}
    # field_name -> [global_min, global_max] across all timesteps


def compute_mesh_metadata_hash() -> str:
    """
    Return an 8-char hash of MeshMetadata field names and types.
    Changes automatically whenever fields are added, removed, or retyped.
    """
    fields = {
        name: str(field.annotation)
        for name, field in MeshMetadata.model_fields.items()
        if name != "schema_hash"
    }
    return hashlib.md5(
        json.dumps(fields, sort_keys=True).encode()
    ).hexdigest()[:8]


# Computed once at import time; used by mesh.py for sidecar validation
MESH_METADATA_HASH: str = compute_mesh_metadata_hash()


# ===========================================================================
# ProjectMetadata
# Hand-authored per dataset, stored in data/datasets/**/*.json.
# ===========================================================================

class BiologicalScale(StrEnum):
    """Biological scale at which the model operates."""
    SUBCELLULAR  = "subcellular"
    CELL         = "cell"
    TISSUE       = "tissue"
    ORGAN        = "organ"
    ORGAN_SYSTEM = "organ_system"


class OrganSystem(StrEnum):
    """Organ system addressed by the dataset."""
    ABDOMINAL       = "abdominal"
    BONE            = "bone"
    HEART           = "heart"
    KIDNEY          = "kidney"
    LIVER           = "liver"
    LUNG            = "lung"
    MUSCULOSKELETAL = "musculoskeletal"
    TORSO           = "torso"
    VASCULATURE     = "vasculature"


class ProjectMetadata(BaseModel):
    """
    Hand-authored descriptor for a dataset, stored in data/metadata/*.json.
    Captures scientific context for UI display.
    """
    data_path: str
    labels_file: str | None = None
    name: str
    pi: str
    institution: list[str]
    biological_scale: BiologicalScale
    organ_system: list[OrganSystem]  # list because multi-system datasets (e.g. IRCADb)
    description: str = Field(max_length=500)
    mesh_format: str                 # e.g. "VTK", "XDMF+HDF5", "VTU"
    references: list[str] = []       # DOIs, URLs, or citations