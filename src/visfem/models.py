"""Pydantic models for mesh and project metadata validation.

MeshMetadata is auto-generated from mesh files and cached as .meta.json sidecars.
ProjectMetadata is hand-authored per dataset, stored in data/datasets/**/*.json.
"""

import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


# MeshMetadata

class FieldInfo(BaseModel):
    """Descriptor for one scalar/vector/tensor field on a mesh."""
    center: str       # "point" or "cell"
    shape: list[int]  # [1] scalar, [3] vector, [3, 3] tensor


Bounds3D = tuple[float, float, float, float, float, float]
"""(xmin, xmax, ymin, ymax, zmin, zmax) bounding box."""


class MeshMetadata(BaseModel):
    """Auto-generated per-mesh metadata, cached as a .meta.json sidecar (regenerated when schema_hash changes)."""
    schema_hash: str = ""
    format: str           # fenics_xdmf | timeseries_xdmf | pyvista_native | meshio_fallback
    n_steps: int = Field(ge=1)
    times: list[float]    # empty for static datasets
    n_points: int = Field(ge=0)
    n_cells: int = Field(ge=0)
    cell_types: list[str]
    fields: dict[str, FieldInfo]
    bounds: Bounds3D | None = None
    scalar_bounds: dict[str, list[float]] = {}
    # field_name -> [global_min, global_max] across all timesteps


def compute_mesh_metadata_hash() -> str:
    """Return an 8-char hash of MeshMetadata field names and types (changes when fields are added/removed/retyped)."""
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


# ProjectMetadata

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


# Rendering configuration
#
# Declared per dataset in an optional JSON `render` block. Every field is
# optional; omitted values are inferred from mesh_format + file discovery
# (engine.renderers.resolve_render_config), so simple datasets need no block.

class RendererName(StrEnum):
    """Built-in renderer selected by a dataset's render config."""
    SURFACE          = "surface"            # one solid-colour mesh (STL/VTU/OBJ)
    MULTI_PART       = "multi_part"         # N labelled part files, merged + coloured
    REGION_ID        = "region_id"          # mesh coloured by an integer cell array (+ optional fibre overlay)
    SCALAR_FIELD     = "scalar_field"       # static mesh coloured by a selectable scalar field (continuous + categorical zones)
    TIMESERIES       = "timeseries"         # scalar-field time series from XDMF, PVD, or a flat VTK series
    PVD_PHASE_SERIES = "pvd_phase_series"   # per-patient region-coloured phase surfaces
    PATIENT_ORGANS   = "patient_organs"     # per-patient per-organ .vtk glob (ircadb family)


class PartSpec(BaseModel):
    """One named part for the multi_part renderer."""
    stem: str           # path stem relative to the dataset dir (may contain subdirs)
    label: str


class ScalarField(BaseModel):
    """One selectable scalar field with a display label."""
    name: str
    label: str | None = None   # defaults to a humanised name if omitted


class FiberOptions(BaseModel):
    """Fibre glyph overlay for the region_id renderer: a vector cell array drawn as oriented glyphs (e.g. cardiac fibres)."""
    array: str = "Fiber"                      # cell array to orient glyphs by
    stride: int = Field(default=5, ge=1)      # subsample every Nth cell
    scale: float = 1.5


class TubeOptions(BaseModel):
    """Tubing options for the multi_part renderer (vessel centrelines)."""
    enabled: bool = True
    n_sides: int = Field(default=8, ge=3)
    stride: int = Field(default=1, ge=1)      # subsample line cells before tubing


class RenderConfig(BaseModel):
    """Declarative per-dataset render config; omitted fields are inferred in engine.renderers.resolve_render_config."""
    renderer: RendererName | None = None

    # mesh location
    mesh_file: str | None = None              # single-mesh renderers
    mesh_candidates: list[str] = []           # fallbacks tried in order (.stl -> .obj)
    parts: list[PartSpec] = []                # multi_part renderer
    part_extensions: list[str] = [".ply", ".vtk", ".vtu", ".stl", ".obj"]

    # colouring
    categorical_palette: str = "paired"
    continuous_cmap: str = "viridis"
    region_array: str | None = None           # integer cell array (Material / PartId)
    region_labels: dict[int, list[str]] = {}  # region id -> display name(s); supersedes labels_file
    labels_mesh_key: str | None = None        # which key of labels_file to use (e.g. "M.vtu")

    # scalar fields
    fields: list[ScalarField] = []            # explicit, ordered selectable fields
    exclude_fields: list[str] = []            # deny-list applied to discovered fields
    default_field: str | None = None          # initial field; else first listed/discovered

    # timeseries renderer: flat VTK series (no .pvd/XDMF manifest)
    series: str | None = None                 # glob (relative to dataset dir) of per-step mesh files, natural-sorted
    database: str | None = None               # LS-DYNA d3plot master filename (e.g. "d3plot"); dataset dir is the database dir

    # renderer-specific options
    fiber: FiberOptions | None = None         # region_id fibre overlay; None => no fibres
    tube: TubeOptions | None = None           # multi_part tubing; None => no tubing
    solid: bool = False                       # pvd_phase_series: single colour (no flicker)
    # scalar_field renderer
    categorical_fields: list[str] = []        # field names drawn as discrete zones (region legend) not a continuous ramp
    percentile_clamp: int | None = None       # continuous-field upper clamp percentile (default 95 when None)

    @model_validator(mode="after")
    def _coerce_field_labels(self) -> "RenderConfig":
        for f in self.fields:
            if f.label is None:
                f.label = f.name.replace("_", " ")
        return self


class ProjectMetadata(BaseModel):
    """Hand-authored per-dataset descriptor (scientific context for the UI), stored in data/datasets/**/*.json."""
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
    spp_project: str | None = None   # SPP2311 project title, None for non-SPP datasets
    spp_badge: bool = False          # show SPP2311 badge without a project title
    subgroup: str | None = None      # optional sub-group label within the organ system (e.g. "Vessel")
    sort_order: int | None = None    # explicit sort position within organ group / subgroup (None = sort by name)
    render: RenderConfig | None = None  # declarative render config; None => fully inferred