#!/usr/bin/env python3
"""One-off migration: add explicit `render` blocks to dataset JSONs.

Datasets whose renderer + parameters cannot be inferred from mesh_format + file
layout (the bespoke ones: multi-part vessels, region-id meshes, heart fibres,
tibia zones, ambiguous surface dirs) get an explicit `render` block written here,
migrating the constants that used to live in selection.py / scene.py into data.

Fully inferable datasets (XDMF series, patient-organ globs, single-surface dirs)
are intentionally left without a block — resolve_render_config infers them.

Idempotent: re-running overwrites the `render` block of the listed datasets only.
Run from the repo root:  python scripts/add_render_blocks.py
"""
from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

DATASETS = Path(__file__).resolve().parents[1] / "data" / "datasets"

# key -> render block. Only datasets that need an EXPLICIT block appear here.
RENDER: dict[str, dict] = {
    # --- surfaces with a filename inference can't pick (dir has >1 mesh) ---
    "ia_ai4ia": {"renderer": "surface", "mesh_file": "IA_AI4IA.stl"},
    "avm_md":   {"renderer": "surface", "mesh_file": "AVM_Modell_MD.stl"},
    "aneurysm": {
        "renderer": "surface",
        "mesh_candidates": ["Aneurysm_small_Full.stl", "Aneurysm_small_Full.obj"],
    },

    # --- region-id meshes (coloured by an integer cell array) ---
    "heart_ep": {
        "renderer": "region_id",
        "mesh_file": "surfaces/ep_surface.vtp",
        "region_array": "Material",
        "region_labels": {
            "1": ["Ventricle endocardium"], "2": ["Ventricle myocardium"],
            "3": ["Ventricle epicardium"], "32": ["Right atrial bulk tissue"],
            "33": ["Left atrial bulk tissue"], "72": ["Crista terminalis"],
            "73": ["Sinus node"], "74": ["Pectinate muscles"],
            "75": ["Bachmann bundle"], "76": ["Middle posterior bridge"],
            "77": ["Lower posterior bridge"], "78": ["Coronary sinus bridge"],
            "79": ["L/R atrial appendage"], "80": ["Inferior isthmus"],
        },
    },
    "tibia_mesh": {
        "renderer": "region_id",
        "mesh_file": "Tibia_Mesh.vtk",
        "region_array": "PartId",
        "categorical_palette": "clinical",
        "region_labels": {
            "1": ["Bone"], "2": ["Fracture / Callus"], "3": ["Implant screws"],
        },
    },

    # --- heart: region-id coloured mesh + fibre glyph overlay; labels via LabelIDs.txt ---
    "heart": {
        "renderer": "region_id",
        "mesh_file": "M.vtu",
        "region_array": "Material",
        "labels_mesh_key": "M.vtu",
        "fiber": {"array": "Fiber", "stride": 5, "scale": 1.5},
    },

    # --- tibia simulation: scalar field with an explicit field list + Claes zones ---
    "tibia_simulation": {
        "renderer": "scalar_field",
        "mesh_file": "Tibia_Simulation.vtk",
        "categorical_palette": "clinical",
        "continuous_cmap": "turbo",
        "categorical_fields": ["Claes_window"],
        "percentile_clamp": 95,
        "default_field": "vonMises_stress",
        "fields": [
            {"name": "vonMises_stress", "label": "von Mises stress"},
            {"name": "vonMises_equivalent_strain", "label": "von Mises eq. strain"},
            {"name": "octahedral_shear_strain", "label": "octahedral shear strain"},
            {"name": "hydrostatic_strain", "label": "hydrostatic strain"},
            {"name": "volumetric_strain", "label": "volumetric strain"},
            {"name": "Claes_window", "label": "healing window (Claes)"},
        ],
        "region_labels": {
            "1": ["Too much movement"], "2": ["Transition (excess)"],
            "3": ["Perfect healing window"], "4": ["Transition (lazy)"],
            "5": ["Bone resorption"],
        },
    },

    # --- multi-part labelled meshes ---
    "aneurysm_coils": {
        "renderer": "multi_part",
        "part_extensions": [".stl", ".obj"],
        "parts": [
            {"stem": "FramingCoil", "label": "Framing Coil"},
            {"stem": "FillingCoil", "label": "Filling Coil"},
        ],
    },
    "rectangle_one_tree": {
        "renderer": "multi_part",
        "part_extensions": [".vtk", ".vtu", ".ply"],
        "parts": [
            {"stem": "rectangle", "label": "Background tissue"},
            {"stem": "Test1", "label": "Vessel tree"},
        ],
    },
    "rectangle_two_trees": {
        "renderer": "multi_part",
        "part_extensions": [".vtk", ".vtu", ".ply"],
        "parts": [
            {"stem": "rectangle", "label": "Background tissue"},
            {"stem": "Test1", "label": "Vessel tree 1"},
            {"stem": "Test2", "label": "Vessel tree 2"},
        ],
    },
    "liver_vessels": {
        "renderer": "multi_part",
        "part_extensions": [".ply", ".vtk", ".vtu"],
        "parts": [
            {"stem": "liver", "label": "Liver"},
            {"stem": "Liver_100000/julia/A", "label": "Arterial"},
            {"stem": "Liver_100000/julia/P", "label": "Portal"},
            {"stem": "Liver_100000/julia/V", "label": "Venous"},
        ],
        "tube": {"enabled": True, "n_sides": 6, "stride": 10},
    },

    # --- XDMF/PVD time series with a field deny-list ---
    "heart_iv": {
        "renderer": "timeseries",
        "exclude_fields": ["Fixation", "PointID", "Material", "CellID", "f", "n", "s"],
    },

    # --- per-patient phase series (solid colour to avoid per-phase flicker) ---
    "mri_grasp_abdomen": {"renderer": "pvd_phase_series", "solid": True},

    # --- per-patient single surface (file lives under patient_NN/, not top level) ---
    "ct_abdomen": {"renderer": "surface", "mesh_file": "bone_surface.vtu"},
}

# The three rectangle_quad sizes share one multi-part config (A/B/P/V).
_QUAD = {
    "renderer": "multi_part",
    "part_extensions": [".vtk", ".vtu"],
    "parts": [
        {"stem": "A", "label": "Arterial"},
        {"stem": "B", "label": "Biliary"},
        {"stem": "P", "label": "Portal"},
        {"stem": "V", "label": "Venous"},
    ],
}
for _q in ("rectangle_quad_500", "rectangle_quad_2000", "rectangle_quad_3000"):
    RENDER[_q] = _QUAD


def _json_path(key: str) -> Path | None:
    for p in DATASETS.rglob(f"{key}.json"):
        if not p.name.endswith(".meta.json"):
            return p
    return None


def main() -> int:
    missing: list[str] = []
    for key, block in RENDER.items():
        path = _json_path(key)
        if path is None:
            missing.append(key)
            continue
        data = json.loads(path.read_text(), object_pairs_hook=OrderedDict)
        data["render"] = block
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print(f"  render block -> {path.relative_to(DATASETS.parents[1])}")
    if missing:
        print(f"WARNING: JSON not found for: {', '.join(missing)}")
        return 1
    print(f"Done: {len(RENDER)} datasets updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
