"""Pydantic models for mesh and project metadata validation."""

import hashlib
import json
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Strict(BaseModel):
    """Base of the JSON models: unknown keys are errors, keys starting with an underscore are comments and are dropped."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_comments(cls, data: object) -> object:
        """Return data without the keys that start with an underscore."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if not str(k).startswith("_")}
        return data


# MeshMetadata


class FieldInfo(_Strict):
    """Descriptor for one scalar/vector/tensor field on a mesh."""

    center: Literal["point", "cell"]
    shape: list[int]  # [1] scalar, [3] vector, [3, 3] tensor


Bounds3D = tuple[float, float, float, float, float, float]
"""(xmin, xmax, ymin, ymax, zmin, zmax) bounding box."""


class MeshMetadata(_Strict):
    """Per-mesh metadata generated from the mesh file and cached as a .meta.json sidecar."""

    # a sidecar whose hash differs from MESH_METADATA_HASH is regenerated
    schema_hash: str = ""
    format: str  # fenics_xdmf | timeseries_xdmf | pyvista_native | meshio_fallback
    n_steps: int = Field(ge=1)
    times: list[float]  # empty for static datasets
    n_points: int = Field(ge=0)
    n_cells: int = Field(ge=0)
    cell_types: list[str]
    fields: dict[str, FieldInfo]
    bounds: Bounds3D | None = None
    # field name -> [global min, global max] across all timesteps
    scalar_bounds: dict[str, list[float]] = {}


def compute_mesh_metadata_hash() -> str:
    """Return an 8-char hash of MeshMetadata field names and types."""
    fields = {
        name: str(field.annotation)
        for name, field in MeshMetadata.model_fields.items()
        if name != "schema_hash"
    }
    return hashlib.md5(json.dumps(fields, sort_keys=True).encode()).hexdigest()[:8]


MESH_METADATA_HASH: str = compute_mesh_metadata_hash()


# ProjectMetadata


class BiologicalScale(StrEnum):
    """Biological scale at which the model operates."""

    SUBCELLULAR = "subcellular"
    CELL = "cell"
    TISSUE = "tissue"
    ORGAN = "organ"
    ORGAN_SYSTEM = "organ_system"


class OrganSystem(StrEnum):
    """Organ system addressed by the dataset."""

    ABDOMINAL = "abdominal"
    BONE = "bone"
    HEART = "heart"
    KIDNEY = "kidney"
    LIVER = "liver"
    LUNG = "lung"
    MUSCULOSKELETAL = "musculoskeletal"
    TORSO = "torso"
    VASCULATURE = "vasculature"


# RenderConfig


class RendererName(StrEnum):
    """Built-in renderer selected by a dataset's render config."""

    SURFACE = "surface"  # one solid-colour mesh (STL/VTU/OBJ)
    MULTI_PART = "multi_part"  # N labelled part files, merged and coloured
    REGION_ID = "region_id"  # coloured by an integer cell array, optional fibre glyphs
    SCALAR_FIELD = "scalar_field"  # static mesh coloured by a selectable field
    TIMESERIES = "timeseries"  # scalar-field series from XDMF, PVD or flat VTK files
    PVD_PHASE_SERIES = "pvd_phase_series"  # per-patient region-coloured phase surfaces
    PATIENT_ORGANS = "patient_organs"  # per-patient .vtk file per organ (ircadb)


class PartSpec(_Strict):
    """One named part for the multi_part renderer."""

    stem: str  # path stem relative to the dataset dir (may contain subdirs)
    label: str


class ScalarField(_Strict):
    """One selectable scalar field with a display label."""

    name: str
    label: str | None = None  # None: humanised copy of name


class FiberOptions(_Strict):
    """Fibre glyph overlay for the region_id renderer."""

    array: str = "Fiber"  # vector cell array that orients the glyphs
    stride: int = Field(default=5, ge=1)  # subsample every Nth cell
    scale: float = 1.5


class TubeOptions(_Strict):
    """Tubing options for the multi_part renderer (vessel centrelines)."""

    enabled: bool = True
    n_sides: int = Field(default=8, ge=3)
    stride: int = Field(default=1, ge=1)  # subsample line cells before tubing


class RenderConfig(_Strict):
    """Per-dataset render config from the optional JSON `render` block; engine.renderers.resolve_render_config infers omitted fields from mesh_format and file discovery."""

    renderer: RendererName | None = None

    # mesh location
    mesh_file: str | None = None  # single-mesh renderers
    mesh_candidates: list[str] = []  # fallbacks tried in order (.stl -> .obj)
    parts: list[PartSpec] = []  # multi_part renderer
    part_extensions: list[str] = [".ply", ".vtk", ".vtu", ".stl", ".obj"]

    # colouring
    categorical_palette: str = "paired"  # key of palettes.CATEGORICAL_PALETTES
    continuous_cmap: str = "viridis"  # key of palettes.CONTINUOUS_CMAPS
    region_array: str | None = None  # integer cell array (Material / PartId)
    # region id -> display name(s); overrides labels_file
    region_labels: dict[int, list[str]] = {}
    labels_mesh_key: str | None = None  # key of labels_file to use (e.g. "M.vtu")

    # scalar fields
    fields: list[ScalarField] = []  # explicit, ordered selectable fields
    exclude_fields: list[str] = []  # discovered fields to drop
    default_field: str | None = None  # initial field; None: first listed or discovered

    # timeseries renderer: flat VTK series or LS-DYNA database
    # glob of per-step mesh files relative to the dataset dir, natural-sorted
    series: str | None = None
    # LS-DYNA d3plot master filename (e.g. "d3plot") inside the dataset dir
    database: str | None = None

    # renderer-specific options
    fiber: FiberOptions | None = None  # region_id fibre overlay
    tube: TubeOptions | None = None  # multi_part tubing
    solid: bool = False  # pvd_phase_series: one colour for every phase; the body count differs per phase
    # scalar_field renderer
    # fields drawn as discrete zones with a region legend
    categorical_fields: list[str] = []
    # upper clamp percentile for continuous fields
    percentile_clamp: int = Field(default=95, ge=1, le=100)

    @field_validator("categorical_palette")
    @classmethod
    def _known_palette(cls, name: str) -> str:
        """Return name when it is a key of CATEGORICAL_PALETTES; raises ValueError otherwise."""
        from visfem.engine.palettes import CATEGORICAL_PALETTES

        if name not in CATEGORICAL_PALETTES:
            raise ValueError(
                f"unknown palette '{name}', one of: {', '.join(CATEGORICAL_PALETTES)}"
            )
        return name

    @field_validator("continuous_cmap")
    @classmethod
    def _known_cmap(cls, name: str) -> str:
        """Return name when it is a key of CONTINUOUS_CMAPS; raises ValueError otherwise."""
        from visfem.engine.palettes import CONTINUOUS_CMAPS

        if name not in CONTINUOUS_CMAPS:
            raise ValueError(
                f"unknown colormap '{name}', one of: {', '.join(CONTINUOUS_CMAPS)}"
            )
        return name

    @model_validator(mode="after")
    def _coerce_field_labels(self) -> "RenderConfig":
        """Fill missing field labels with the humanised field name and return self."""
        for f in self.fields:
            if f.label is None:
                f.label = f.name.replace("_", " ")
        return self


class ProjectMetadata(_Strict):
    """Hand-authored per-dataset descriptor with the scientific context shown in the UI, stored in data/datasets/**/*.json."""

    data_path: (
        str  # relative to the datasets dir: a folder, or the .pvd file of a PVD dataset
    )
    labels_file: str | None = None
    name: str
    pi: str
    institution: list[str]
    biological_scale: BiologicalScale
    organ_system: list[OrganSystem]  # multi-system datasets list several (e.g. IRCADb)
    description: str = Field(max_length=500)
    mesh_format: str  # display label, e.g. "VTK", "XDMF+HDF5", "VTU (per-phase)"
    references: list[str] = []  # DOIs, URLs, or citations
    spp_project: str | None = None  # SPP2311 project title
    spp_badge: bool = False  # show the SPP2311 badge even when spp_project is None
    # sub-group label within the organ system (e.g. "Vessel")
    subgroup: str | None = None
    # sort position within the organ group or subgroup; None: by name
    sort_order: int | None = None
    render: RenderConfig | None = None  # render config; None: every field inferred

    @field_validator("data_path")
    @classmethod
    def _relative_path(cls, value: str) -> str:
        """Return value when it is a relative path without parent references; raises ValueError otherwise."""
        path = PurePosixPath(value)
        if not value.strip() or path.is_absolute() or ".." in path.parts:
            raise ValueError("must be a relative path inside the datasets dir")
        return value

    @property
    def is_pvd(self) -> bool:
        """Return True when mesh_format names a PVD dataset, whose data_path is the .pvd file."""
        return self.mesh_format.upper() == "PVD"
