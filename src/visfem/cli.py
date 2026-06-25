"""Command-line interface for VisFEM.

`visfem` (no args) launches the web app. Subcommands
help users who add their own datasets to a ``DATA_DIR`` folder:

    visfem serve              # launch the app (default)
    visfem validate-data      # validate every dataset JSON + check referenced files
    visfem schema             # concise reference of the dataset JSON fields
    visfem example <renderer>  # print a minimal valid dataset JSON for a renderer
    visfem new-dataset NAME    # scaffold a dataset folder + JSON template

The data-authoring commands work entirely off the data directory (DATA_DIR /
VISFEM_DATA_DIR, else the bundled data), so a pip-installed user never edits
package source to add a dataset.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from visfem.models import ProjectMetadata, RenderConfig, RendererName


def _serve() -> int:
    """Launch the web app (delegates to app.main)."""
    from visfem.app import main as app_main
    app_main()
    return 0


def cmd_validate_data(_args: argparse.Namespace) -> int:
    """Validate every dataset JSON and confirm its referenced mesh files exist."""
    from visfem.engine.discovery import DATASETS_DIR, dataset_dir
    from visfem.engine.renderers import resolve_render_config

    if not DATASETS_DIR.is_dir():
        print(f"error: datasets dir not found: {DATASETS_DIR}", file=sys.stderr)
        return 1

    errors: list[str] = []
    n_ok = 0
    for path in sorted(DATASETS_DIR.rglob("*.json")):
        if path.name.endswith(".meta.json"):
            continue
        try:
            meta = ProjectMetadata.model_validate_json(path.read_text())
        except ValidationError as e:
            errors.append(f"{path}: invalid metadata\n{e}")
            continue

        # PVD datasets point data_path at the .pvd file itself; others at a dir.
        ddir = dataset_dir(meta)
        if meta.mesh_format.upper() == "PVD":
            from visfem.engine.discovery import pvd_file_path
            pvd = pvd_file_path(meta)
            if pvd is None or not pvd.exists():
                errors.append(f"{path}: PVD file '{meta.data_path}' not found")
            else:
                n_ok += 1
            continue
        if not ddir.is_dir():
            errors.append(f"{path}: data_path '{meta.data_path}' not found at {ddir}")
            continue

        cfg = resolve_render_config(meta, ddir)
        problems = _check_render_files(ddir, cfg)
        if problems:
            errors.extend(f"{path}: {p}" for p in problems)
        else:
            n_ok += 1

    for err in errors:
        print(f"FAIL {err}", file=sys.stderr)
    print(f"\n{n_ok} dataset(s) OK, {len(errors)} problem(s).")
    return 1 if errors else 0


def _check_render_files(ddir: Path, cfg: RenderConfig) -> list[str]:
    """Return human-readable problems with the files a render config references."""
    problems: list[str] = []
    patient_driven = any(d.is_dir() for d in ddir.glob("patient_*"))

    if cfg.renderer == RendererName.MULTI_PART:
        for part in cfg.parts:
            if not any((ddir / f"{part.stem}{ext}").exists() for ext in cfg.part_extensions):
                problems.append(f"part '{part.stem}' not found (tried {cfg.part_extensions})")
    elif cfg.renderer in (RendererName.REGION_ID, RendererName.SCALAR_FIELD):
        if cfg.mesh_file and not (ddir / cfg.mesh_file).exists():
            problems.append(f"mesh_file '{cfg.mesh_file}' not found")
    elif cfg.renderer == RendererName.TIMESERIES and cfg.series:
        if not any(ddir.glob(cfg.series)):
            problems.append(f"series glob '{cfg.series}' matched no files")
    elif cfg.renderer == RendererName.TIMESERIES and cfg.database:
        if not (ddir / cfg.database).exists():
            problems.append(f"d3plot master '{cfg.database}' not found in {ddir}")
    elif cfg.renderer == RendererName.SURFACE and not patient_driven:
        from visfem.engine.renderers import resolve_mesh_file
        if resolve_mesh_file(ddir, cfg) is None:
            problems.append("surface renderer could not resolve a mesh file "
                            "(set render.mesh_file or render.mesh_candidates)")
    return problems


def cmd_schema(_args: argparse.Namespace) -> int:
    """Print a concise, human-readable reference of the dataset JSON fields."""
    from visfem.models import BiologicalScale, OrganSystem

    scales = ", ".join(s.value for s in BiologicalScale)
    systems = ", ".join(s.value for s in OrganSystem)
    renderers = ", ".join(r.value for r in RendererName)

    print(f"""\
Dataset descriptor fields (datasets/<name>/<name>.json)

Required:
  data_path         folder under datasets/ holding the meshes (usually <name>)
  name              display name
  pi                principal investigator
  institution       list of strings
  biological_scale  one of: {scales}
  organ_system      list of: {systems}
  description        short text (<= 500 chars)
  mesh_format        e.g. VTK, VTU, STL, XDMF+HDF5

Optional:
  references         list of DOIs / URLs
  spp_project        SPP2311 project title (None for non-SPP)
  spp_badge          true to show the SPP2311 badge
  subgroup           sub-group label within the organ group
  sort_order         explicit sort position (int)
  render             how to draw it (see below); omit to infer from mesh_format

render block (renderer = one of: {renderers}):
  see `visfem example <renderer>` for a ready-to-edit template per renderer.
  Omit the whole block for a single STL or an XDMF/PVD series - it is inferred.
""")
    return 0


# Shared scientific-metadata fields for every example/template.
def _base(**over: object) -> dict:
    d: dict[str, object] = {
        "data_path": "my_dataset",
        "name": "My Dataset",
        "pi": "Your Name",
        "institution": ["Your Lab"],
        "biological_scale": "organ",          # subcellular|cell|tissue|organ|organ_system
        "organ_system": ["heart"],            # run `visfem schema` for valid values
        "description": "Short description of the model.",
        "mesh_format": "VTU",
        "references": [],
    }
    d.update(over)
    return d


# One canonical, valid example per renderer. Shared by `example` and `new-dataset`.
_EXAMPLES: dict[RendererName, dict] = {
    RendererName.SURFACE: _base(
        mesh_format="STL",
        render={"renderer": "surface", "mesh_file": "mesh.stl"},
    ),
    RendererName.MULTI_PART: _base(
        organ_system=["vasculature"], mesh_format="VTK",
        render={
            "renderer": "multi_part",
            "part_extensions": [".vtk", ".vtu", ".stl"],
            "parts": [
                {"stem": "arteries", "label": "Arteries"},
                {"stem": "veins", "label": "Veins"},
            ],
        },
    ),
    RendererName.REGION_ID: _base(
        organ_system=["bone"], mesh_format="VTK",
        render={
            "renderer": "region_id",
            "mesh_file": "mesh.vtk",
            "region_array": "PartId",      # integer cell array to colour by
            "categorical_palette": "clinical",
            "region_labels": {"1": ["Region one"], "2": ["Region two"]},
            # Optional fibre/vector glyph overlay (e.g. cardiac fibres):
            # "fiber": {"array": "Fiber", "stride": 5, "scale": 1.5},
        },
    ),
    RendererName.SCALAR_FIELD: _base(
        organ_system=["bone"], mesh_format="VTK",
        render={
            "renderer": "scalar_field",
            "mesh_file": "mesh.vtk",
            "continuous_cmap": "viridis",
            "default_field": "stress",
            "percentile_clamp": 95,        # clip continuous ramps to this percentile
            "fields": [
                {"name": "stress", "label": "stress"},
                {"name": "strain", "label": "strain"},
            ],
            # Fields rendered as discrete zones (with region_labels) instead of a ramp:
            "categorical_fields": [],
            "region_labels": {},
        },
    ),
    RendererName.TIMESERIES: _base(
        organ_system=["liver"], mesh_format="VTK",
        render={
            "renderer": "timeseries",
            # A flat series of per-step mesh files (no .pvd/XDMF needed); files are
            # natural-sorted into steps. For XDMF/PVD datasets, omit "series" and the
            # manifest is read directly. For an LS-DYNA d3plot database, instead set
            # "database": "d3plot" (the dataset folder is the database directory).
            "series": "frame_*.vtk",
            "default_field": "concentration",
            "fields": [
                {"name": "concentration", "label": "concentration"}
            ],
            # "exclude_fields": []   # (manifest series) hide non-display fields
        },
    ),
    RendererName.PVD_PHASE_SERIES: _base(
        organ_system=["abdominal"], mesh_format="VTU (per-phase)",
        render={"renderer": "pvd_phase_series", "solid": True},
    ),
    RendererName.PATIENT_ORGANS: _base(
        organ_system=["liver"], mesh_format="VTK",
        render={"renderer": "patient_organs"},
    ),
}

# Inline guidance written into a scaffolded template (Pydantic ignores _comment keys).
_TEMPLATE_HELP = {
    "_comment": "Edit the fields below, drop your meshes in this folder, then run: visfem validate-data",
    "_comment_data_path": "folder under datasets/ holding the meshes (usually this dataset's name)",
    "_comment_render": "how to draw it; run `visfem example <renderer>` for other renderer templates",
}


def cmd_example(args: argparse.Namespace) -> int:
    """Print a minimal valid dataset JSON for a renderer to stdout."""
    example = _EXAMPLES[RendererName(args.renderer)]
    print(json.dumps(example, indent=2))
    return 0


def cmd_new_dataset(args: argparse.Namespace) -> int:
    """Scaffold datasets/<name>/<name>.json from a commented, renderer-specific template."""
    from visfem.engine.discovery import DATASETS_DIR

    name: str = args.name
    folder = DATASETS_DIR / name
    out = folder / f"{name}.json"
    if out.exists():
        print(f"error: {out} already exists", file=sys.stderr)
        return 1
    folder.mkdir(parents=True, exist_ok=True)

    renderer = args.renderer or "surface"
    tmpl: dict = dict(_TEMPLATE_HELP)
    tmpl.update(_EXAMPLES[RendererName(renderer)])
    tmpl["data_path"] = name
    tmpl["name"] = name
    out.write_text(json.dumps(tmpl, indent=2) + "\n")
    print(
        f"created {out}\n"
        f"Edit it and drop your mesh files in {folder}, then: visfem validate-data\n"
        f"Tip: `visfem example <renderer>` shows a template for any of: "
        f"{', '.join(r.value for r in RendererName)}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="visfem", description="VisFEM: web visualization of FEM models.")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("serve", help="launch the web app (default)")
    sub.add_parser("validate-data", help="validate dataset JSONs and referenced files")
    sub.add_parser("schema", help="print a concise reference of the dataset JSON fields")

    p_ex = sub.add_parser("example", help="print a minimal valid dataset JSON for a renderer")
    p_ex.add_argument("renderer", choices=[r.value for r in RendererName])

    p_new = sub.add_parser("new-dataset", help="scaffold a dataset folder + JSON template")
    p_new.add_argument("name", help="dataset key / folder name (e.g. my_model)")
    p_new.add_argument("--renderer", choices=[r.value for r in RendererName],
                       help="renderer to template (default: surface)")
    return parser


_SUBCOMMANDS = ("serve", "validate-data", "schema", "example", "new-dataset")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in _SUBCOMMANDS or argv[0] == "serve":
        return _serve()

    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "validate-data": cmd_validate_data,
        "schema": cmd_schema,
        "example": cmd_example,
        "new-dataset": cmd_new_dataset,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
