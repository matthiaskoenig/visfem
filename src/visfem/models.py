"""Pydantic models for mesh and project metadata validation.

Two metadata types:
  MeshMetadata     -- auto-generated from mesh files, cached as .meta.json sidecars
  ProjectMetadata  -- hand-authored per dataset, stored in data/metadata/*.json
"""

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

    Cached as a .meta.json sidecar next to the source file.
    Delete the sidecar to force regeneration.
    """
    format: str           # fenics_xdmf | timeseries_xdmf | pyvista_native | meshio_fallback (see mesh.py)
    n_steps: int = Field(ge=1)
    times: list[float]    # empty for static datasets
    n_points: int = Field(ge=0)
    n_cells: int = Field(ge=0)
    cell_types: list[str]
    fields: dict[str, FieldInfo]
    bounds: tuple[float, float, float, float, float, float] | None = None
    # xmin, xmax, ymin, ymax, zmin, zmax; None if not precomputed


# ===========================================================================
# ProjectMetadata
# Hand-authored per dataset, stored in data/metadata/*.json.
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
    VASCULATURE     = "vasculature"


class ProjectMetadata(BaseModel):
    """
    Hand-authored descriptor for a dataset, stored in data/metadata/*.json.
    Captures scientific context for UI display.
    """
    pi: str
    institution: str
    biological_scale: BiologicalScale
    organ_system: list[OrganSystem]  # list because multi-system datasets (e.g. IRCADb)
    description: str = Field(max_length=300)
    mesh_format: str                 # e.g. "VTK", "XDMF+HDF5", "VTU"