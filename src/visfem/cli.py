"""Command-line interface for VisFEM.

`visfem` (no args) launches the web app. Subcommands
help users who add their own datasets to a ``DATA_DIR`` folder:

    visfem serve              # launch the app (default)
    visfem renderers          # list the built-in renderers and what each is for
    visfem schema             # concise reference of the dataset JSON fields
    visfem example <renderer>  # print a minimal valid dataset JSON for a renderer
    visfem new-dataset NAME    # scaffold a dataset folder + JSON template
    visfem validate-data      # validate every dataset JSON + check referenced files
    visfem fetch-ircadb       # download the public 3D-IRCADb-01 example dataset
    visfem fetch-openknee     # download the Open Knee(s) knee geometries from SimTK

The data-authoring commands work entirely off the data directory (DATA_DIR /
VISFEM_DATA_DIR, else the bundled data), so a pip-installed user never edits
package source to add a dataset.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from visfem.models import ProjectMetadata, RenderConfig, RendererName


def _serve() -> int:
    """Launch the web app (delegates to app.main)."""
    from visfem.app import main as app_main

    app_main()
    return 0


# One-line "what it's for / when to use it" per renderer, surfaced by `visfem renderers`
_RENDERER_HELP: dict[RendererName, str] = {
    RendererName.SURFACE: "one solid-colour mesh (STL/VTU/OBJ) - the default for a single static surface",
    RendererName.MULTI_PART: "several named part files merged and coloured together (e.g. arteries + veins)",
    RendererName.REGION_ID: "one mesh coloured by an integer cell array (regions/materials), with optional fibre glyphs",
    RendererName.SCALAR_FIELD: "a static mesh coloured by a selectable scalar field (continuous ramp and/or categorical zones)",
    RendererName.TIMESERIES: "a scalar field animated over time from XDMF, PVD, a flat VTK series, or an LS-DYNA d3plot",
    RendererName.PVD_PHASE_SERIES: "per-patient region-coloured phase surfaces driven by a .pvd manifest",
    RendererName.PATIENT_ORGANS: "per-patient folders of per-organ .vtk meshes (the 3D-IRCADb-01 family)",
}


def cmd_renderers(_args: argparse.Namespace) -> int:
    """List the built-in renderers and a one-line description of each."""
    width = max(len(r.value) for r in RendererName)
    print("Built-in renderers (set as render.renderer in a dataset JSON):\n")
    for renderer in RendererName:
        print(f"  {renderer.value:<{width}}  {_RENDERER_HELP[renderer]}")
    print("\nRun `visfem example <renderer>` for a ready-to-edit template.")
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
            meta = ProjectMetadata.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as e:
            errors.append(f"{path}: invalid metadata\n{_format_validation_error(e)}")
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


def _format_validation_error(e: ValidationError) -> str:
    """Render a Pydantic ValidationError as compact `field: message` lines for non-experts."""
    lines: list[str] = []
    for err in e.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def _check_render_files(ddir: Path, cfg: RenderConfig) -> list[str]:
    """Return human-readable problems with the files a render config references."""
    problems: list[str] = []
    patient_driven = any(d.is_dir() for d in ddir.glob("patient_*"))

    if cfg.renderer == RendererName.MULTI_PART:
        for part in cfg.parts:
            if not any(
                (ddir / f"{part.stem}{ext}").exists() for ext in cfg.part_extensions
            ):
                problems.append(
                    f"part '{part.stem}' not found (tried {cfg.part_extensions})"
                )
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
            problems.append(
                "surface renderer could not resolve a mesh file "
                "(set render.mesh_file or render.mesh_candidates)"
            )
    return problems


def cmd_schema(_args: argparse.Namespace) -> int:
    """Print a concise reference of the dataset JSON fields."""
    from visfem.engine.palettes import CATEGORICAL_PALETTES, CONTINUOUS_CMAPS
    from visfem.models import BiologicalScale, OrganSystem

    scales = ", ".join(s.value for s in BiologicalScale)
    systems = ", ".join(s.value for s in OrganSystem)
    renderers = ", ".join(r.value for r in RendererName)
    palettes = ", ".join(CATEGORICAL_PALETTES)
    cmaps = ", ".join(CONTINUOUS_CMAPS)

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
  see `visfem example <renderer>` for a ready-to-edit template per renderer,
  or `visfem renderers` for a one-line description of each.
  Omit the whole block for a single STL or an XDMF/PVD series - it is inferred.

  categorical_palette   one of: {palettes}
  continuous_cmap       one of: {cmaps}
""")
    return 0


# Shared scientific-metadata fields for every example/template.
def _base(**over: object) -> dict:
    d: dict[str, object] = {
        "data_path": "my_dataset",
        "name": "My Dataset",
        "pi": "Your Name",
        "institution": ["Your Lab"],
        "biological_scale": "organ",  # subcellular|cell|tissue|organ|organ_system
        "organ_system": ["heart"],  # run `visfem schema` for valid values
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
        organ_system=["vasculature"],
        mesh_format="VTK",
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
        organ_system=["bone"],
        mesh_format="VTK",
        render={
            "renderer": "region_id",
            "mesh_file": "mesh.vtk",
            "region_array": "PartId",  # integer cell array to colour by
            "categorical_palette": "clinical",
            "region_labels": {"1": ["Region one"], "2": ["Region two"]},
            # Optional fibre/vector glyph overlay (e.g. cardiac fibres):
            # "fiber": {"array": "Fiber", "stride": 5, "scale": 1.5},
        },
    ),
    RendererName.SCALAR_FIELD: _base(
        organ_system=["bone"],
        mesh_format="VTK",
        render={
            "renderer": "scalar_field",
            "mesh_file": "mesh.vtk",
            "continuous_cmap": "viridis",
            "default_field": "stress",
            "percentile_clamp": 95,  # clip continuous ramps to this percentile
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
        organ_system=["liver"],
        mesh_format="VTK",
        render={
            "renderer": "timeseries",
            # A flat series of per-step mesh files (no .pvd/XDMF needed); files are
            # natural-sorted into steps. For XDMF/PVD datasets, omit "series" and the
            # manifest is read directly. For an LS-DYNA d3plot database, instead set
            # "database": "d3plot" (the dataset folder is the database directory).
            "series": "frame_*.vtk",
            "default_field": "concentration",
            "fields": [{"name": "concentration", "label": "concentration"}],
            # "exclude_fields": []   # (manifest series) hide non-display fields
        },
    ),
    RendererName.PVD_PHASE_SERIES: _base(
        organ_system=["abdominal"],
        mesh_format="VTU (per-phase)",
        render={"renderer": "pvd_phase_series", "solid": True},
    ),
    RendererName.PATIENT_ORGANS: _base(
        organ_system=["liver"],
        mesh_format="VTK",
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


# fetch-ircadb: download and lay out the public 3D-IRCADb-01 example dataset.

_IRCAD_URL = "https://cloud.ircad.fr/index.php/s/JN3z7EynBiwYyjy/download"
_IRCAD_PAGE = "https://www.ircad.fr/research/data-sets/liver-segmentation-3d-ircadb-01/"

# Descriptor written next to the fetched meshes
_IRCAD_DESCRIPTOR: dict = {
    "data_path": "ircadb",
    "labels_file": None,
    "name": "3D-IRCADb-01",
    "pi": "Luc Soler",
    "institution": ["IRCAD, Strasbourg, France"],
    "biological_scale": "organ_system",
    "organ_system": ["torso", "lung", "kidney", "bone", "vasculature", "abdominal"],
    "description": (
        "3D-IRCADb-01: CT-segmented surface meshes from 20 patients (10 women, "
        "10 men), hepatic tumours in 75% of cases, covering up to 47 organ types "
        "per patient."
    ),
    "mesh_format": "VTK",
    "references": [
        _IRCAD_PAGE,
        "Soler et al. 3D image reconstruction for comparison of algorithm "
        "database. IRCAD, Strasbourg, France, Tech. Rep (2010)",
    ],
}


def _resolve_data_dir(arg: str | None) -> Path:
    """Target data dir: --data-dir, else $DATA_DIR/$VISFEM_DATA_DIR, else ./visfem_data."""
    env = os.environ.get("DATA_DIR") or os.environ.get("VISFEM_DATA_DIR")
    return Path(arg or env or (Path.cwd() / "visfem_data")).expanduser()


def _download_with_progress(url: str, dest: Path) -> None:
    """Stream `url` to `dest` in 1 MiB chunks, showing a rich download progress bar."""
    import urllib.request

    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        ProgressColumn,
        TextColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )

    req = urllib.request.Request(url, headers={"User-Agent": "visfem-fetch-ircadb"})
    with urllib.request.urlopen(req) as resp:  # noqa: S310 - fixed, trusted IRCAD URL
        total = int(resp.headers.get("Content-Length") or 0)
        columns: list[ProgressColumn] = [
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
        ]
        with Progress(*columns) as progress:
            task = progress.add_task("Downloading", total=total or None)
            with dest.open("wb") as fh:
                while chunk := resp.read(1 << 20):  # 1 MiB
                    fh.write(chunk)
                    progress.update(task, advance=len(chunk))


def _extract_ircadb(zip_path: Path, dest: Path) -> int:
    """Extract per-patient .vtk meshes from the IRCADb archive into dest/patient_NN/.

    The archive expands to 3Dircadb1/3Dircadb1.<N>/MESHES_VTK.zip; each inner zip
    holds the patient's <organ>.vtk surfaces. Returns the number of patients laid out.
    """
    import io
    import re
    import zipfile

    count = 0
    with zipfile.ZipFile(zip_path) as outer:
        # Map patient number -> the inner MESHES_VTK.zip member name.
        mesh_zips: dict[int, str] = {}
        licenses: dict[int, str] = {}
        for member in outer.namelist():
            m = re.search(r"3Dircadb1\.(\d+)/MESHES_VTK\.zip$", member)
            if m:
                mesh_zips[int(m.group(1))] = member
                continue
            lic = re.search(r"3Dircadb1\.(\d+)/LICENSE\.txt$", member)
            if lic:
                licenses[int(lic.group(1))] = member

        for n in sorted(mesh_zips):
            pdir = dest / f"patient_{n:02d}"
            pdir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(outer.read(mesh_zips[n]))) as inner:
                n_vtk = 0
                for name in inner.namelist():
                    if not name.lower().endswith(".vtk"):
                        continue
                    # Flatten: keep only the basename (drop any MESHES_VTK/ prefix).
                    target = pdir / Path(name).name
                    target.write_bytes(inner.read(name))
                    n_vtk += 1
            if n in licenses:
                (pdir / "LICENSE.txt").write_bytes(outer.read(licenses[n]))
            print(f"   + patient_{n:02d}: {n_vtk} meshes")
            count += 1
    return count


def cmd_fetch_ircadb(args: argparse.Namespace) -> int:
    """Download 3D-IRCADb-01 and lay it out as a ready-to-open VisFEM dataset."""
    import tempfile

    data_dir = _resolve_data_dir(args.data_dir)
    dest = data_dir / "datasets" / "ircadb"

    print(
        "3D-IRCADb-01 is provided by IRCAD (Strasbourg) under its own license terms.\n"
        "By downloading you agree to respect them and to cite the dataset.\n"
        f"Source: {_IRCAD_PAGE}\n"
    )
    print(f">> Target VisFEM data dir : {data_dir}")
    print(f">> IRCADb will be placed in: {dest}\n")
    dest.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as work:
        zip_path = Path(work) / "3Dircadb1.zip"
        print(">> Downloading 3D-IRCADb-01 (~3 GB) from IRCAD ...")
        try:
            _download_with_progress(_IRCAD_URL, zip_path)
        except OSError as e:
            print(f"error: download failed: {e}", file=sys.stderr)
            print(f"       check your connection or see {_IRCAD_PAGE}", file=sys.stderr)
            return 1

        print(">> Extracting per-patient meshes ...")
        try:
            count = _extract_ircadb(zip_path, dest)
        except Exception as e:  # zipfile.BadZipFile and friends
            print(f"error: could not extract the archive: {e}", file=sys.stderr)
            print(
                f"       the archive layout may have changed; see {_IRCAD_PAGE}",
                file=sys.stderr,
            )
            return 1

    if count == 0:
        print("error: no patient meshes were extracted.", file=sys.stderr)
        return 1

    descriptor = dest / "ircadb.json"
    if descriptor.exists():
        print(f"\n>> Descriptor already exists, leaving it as-is: {descriptor}")
    else:
        descriptor.write_text(json.dumps(_IRCAD_DESCRIPTOR, indent=2) + "\n")
        print(f"\n>> Wrote dataset descriptor: {descriptor}")

    print(
        f"\n>> Done. Prepared {count} patient(s) under {dest}\n\n"
        "   Next steps:\n"
        f'     export DATA_DIR="{data_dir}"\n'
        "     visfem validate-data     # optional: confirm the dataset resolves\n"
        "     visfem                    # launch; '3D-IRCADb-01' appears in the sidebar"
    )
    return 0


# fetch-openknee: download Open Knee(s) knee geometries from the SimTK SVN repository.
#
# The project's Downloads tab needs a SimTK account, but its Subversion repository
# is readable anonymously over HTTPS and holds all the geometry: the per-specimen
# segmented tissue surfaces of Generation 2 and the Generation 1 tibiofemoral
# FEBio model. Licensing: the repository's license.txt says CC BY-SA 3.0, the
# project page says CC BY 4.0; both files are copied next to the data.

_OPENKNEE_PAGE = "https://simtk.org/projects/openknee"
_OPENKNEE_SVN = "https://simtk.org/svn/openknee"
_OPENKNEE_PI = "Ahmet Erdemir"
_OPENKNEE_INSTITUTION = [
    "Cleveland Clinic, Lerner Research Institute, Department of Biomedical Engineering"
]
_OPENKNEE_GEN2_REFERENCES = [
    "https://doi.org/10.18735/b0zv-n395",
    "https://doi.org/10.1007/s10439-022-03074-0",
    "https://doi.org/10.1016/j.dib.2021.106824",
    _OPENKNEE_PAGE,
]
_OPENKNEE_GEN1_REFERENCES = [
    "https://doi.org/10.1055/s-0035-1564600",
    f"{_OPENKNEE_SVN}/_gen1/",
    _OPENKNEE_PAGE,
]

# Generation 2 specimens with a simulation-ready model (Chokhandre et al. 2023):
# id -> (side, sex, age in years, BMI). oks005 does not exist in the cohort.
_OKS_SPECIMENS: dict[str, tuple[str, str, int, float]] = {
    "oks001": ("Right", "male", 71, 23.1),
    "oks002": ("Right", "female", 67, 18.9),
    "oks003": ("Left", "female", 25, 22.8),
    "oks004": ("Right", "female", 46, 21.9),
    "oks006": ("Right", "female", 71, 21.3),
    "oks007": ("Right", "male", 71, 22.7),
    "oks008": ("Right", "male", 40, 20.09),
    "oks009": ("Left", "male", 34, 20.0),
}
# The first two specimens keep an extra dat/ folder level in the repository.
_OKS_SVN_DAT_LEVEL = {"oks001", "oks002"}

# Connectivity.xml part code -> (file stem in the dataset, display label), legend order.
_OKS_PARTS: list[tuple[str, str, str]] = [
    ("FMB", "femur", "Femur"),
    ("TBB", "tibia", "Tibia"),
    ("FBB", "fibula", "Fibula"),
    ("PTB", "patella", "Patella"),
    ("FMC", "femoral_cartilage", "Femoral cartilage"),
    ("TBC-M", "tibial_cartilage_medial", "Tibial cartilage (medial)"),
    ("TBC-L", "tibial_cartilage_lateral", "Tibial cartilage (lateral)"),
    ("PTC", "patellar_cartilage", "Patellar cartilage"),
    ("MNS-M", "meniscus_medial", "Meniscus (medial)"),
    ("MNS-L", "meniscus_lateral", "Meniscus (lateral)"),
    ("ACL", "acl", "Anterior cruciate ligament"),
    ("PCL", "pcl", "Posterior cruciate ligament"),
    ("MCL", "mcl", "Medial collateral ligament"),
    ("LCL", "lcl", "Lateral collateral ligament"),
    ("PTL", "patellar_ligament", "Patellar ligament"),
    ("QAT", "quadriceps_tendon", "Quadriceps tendon"),
]

# Generation 1 FEBio material id -> legend names. The second name is the material
# name used in the .feb file. Cartilage is meshed in three hex layers through its
# thickness (material suffixes b/m/t); 16 and 17 are empty image-link rigid bodies.
_GEN1_FEB = "tf_joint_FEBio_v2p7.feb"
_GEN1_REGION_LABELS: dict[int, list[str]] = {
    1: ["Femur (rigid)", "femur"],
    2: ["Tibia (rigid)", "tibia"],
    3: ["Femoral cartilage (layer 1 of 3)", "fcartb"],
    4: ["Femoral cartilage (layer 2 of 3)", "fcartm"],
    5: ["Femoral cartilage (layer 3 of 3)", "fcartt"],
    6: ["Tibial cartilage (layer 1 of 3)", "tcartb"],
    7: ["Tibial cartilage (layer 2 of 3)", "tcartm"],
    8: ["Tibial cartilage (layer 3 of 3)", "tcartt"],
    9: ["Lateral meniscus", "lat meni"],
    10: ["Medial meniscus", "med meni"],
    11: ["Anterior cruciate ligament", "acl"],
    12: ["Anterior cruciate ligament (fibre region)", "aclfiber"],
    13: ["Posterior cruciate ligament", "pcl"],
    14: ["Medial collateral ligament", "mcl"],
    15: ["Lateral collateral ligament", "lcl"],
}


def _oks_svn_dir(specimen: str) -> str:
    """Base SVN URL of one specimen's Geometry/ and Model/ folders."""
    base = f"{_OPENKNEE_SVN}/oks/{specimen}"
    return f"{base}/dat" if specimen in _OKS_SVN_DAT_LEVEL else base


def _fetch_bytes(url: str) -> bytes:
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "visfem-fetch-openknee"})
    with urllib.request.urlopen(req) as resp:  # noqa: S310 - fixed, trusted SimTK URL
        return bytes(resp.read())


def parse_connectivity(xml_text: str) -> dict[str, str]:
    """Map part code -> STL filename from an Open Knee(s) Connectivity.xml.

    The file is the assembly description of the specimen's FE model; its
    ``<Assembly>`` children are the part codes (FMB, TBB, ...) and each one's
    ``<file>`` names the segmented surface that was actually meshed.
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)
    files: dict[str, str] = {}
    for part in root:
        name = part.findtext("file")
        if name:
            # Some assemblies (oks006) store Windows paths; only the basename is in SVN.
            files[part.tag] = name.strip().replace("\\", "/").rsplit("/", 1)[-1]
    return files


def openknee_specimen_descriptor(specimen: str) -> dict:
    """Dataset JSON for one Generation 2 specimen (same layout as the bundled datasets)."""
    side, sex, age, bmi = _OKS_SPECIMENS[specimen]
    return {
        "data_path": f"openknees_{specimen}",
        "name": f"Open Knee(s) {specimen.upper()} ({side}, {sex}, {age}y)",
        "pi": _OPENKNEE_PI,
        "institution": _OPENKNEE_INSTITUTION,
        "biological_scale": "organ",
        "organ_system": ["musculoskeletal"],
        "description": (
            f"Specimen-specific knee joint geometry from the Open Knee(s) cohort "
            f"({specimen}: {side.lower()} knee, {sex}, {age} years, BMI {bmi}). "
            "Sixteen smooth, watertight triangulated tissue surfaces segmented from "
            "MRI: bones, cartilage, menisci, cruciate and collateral ligaments, "
            "patellar ligament and quadriceps tendon."
        ),
        "mesh_format": "STL",
        "references": _OPENKNEE_GEN2_REFERENCES,
        "subgroup": "Knee",
        "sort_order": list(_OKS_SPECIMENS).index(specimen) + 1,
        "render": {
            "renderer": "multi_part",
            "part_extensions": [".stl"],
            "categorical_palette": "paired",
            "tube": {"enabled": False},
            "parts": [{"stem": stem, "label": label} for _, stem, label in _OKS_PARTS],
        },
    }


def openknee_gen1_descriptor() -> dict:
    """Dataset JSON for the Generation 1 tibiofemoral FEBio model (region_id renderer)."""
    return {
        "data_path": "openknees_gen1",
        "name": "Open Knee(s) Generation 1 (tibiofemoral FE model)",
        "pi": _OPENKNEE_PI,
        "institution": _OPENKNEE_INSTITUTION,
        "biological_scale": "organ",
        "organ_system": ["musculoskeletal"],
        "description": (
            "Open Knee Generation 1: finite element model of a tibiofemoral joint "
            "(FEBio 2.5, v1.2.0). Rigid femur and tibia surfaces with hexahedral "
            "meshes of femoral and tibial cartilage (three layers each), both "
            "menisci and the ACL, PCL, MCL and LCL. Converted from the original "
            f"{_GEN1_FEB} with `visfem fetch-openknee`; materials are kept as regions."
        ),
        "mesh_format": "VTU",
        "references": _OPENKNEE_GEN1_REFERENCES,
        "subgroup": "Knee",
        "sort_order": 0,
        "render": {
            "renderer": "region_id",
            "mesh_file": "tf_joint.vtu",
            "region_array": "Material",
            "categorical_palette": "paired",
            "region_labels": {str(k): v for k, v in _GEN1_REGION_LABELS.items()},
        },
    }


def _write_descriptor(dest: Path, descriptor: dict) -> None:
    path = dest / f"{descriptor['data_path']}.json"
    if path.exists():
        print(f"   descriptor already exists, leaving it as-is: {path.name}")
    else:
        path.write_text(json.dumps(descriptor, indent=2) + "\n")
        print(f"   wrote dataset descriptor: {path.name}")


def _fetch_openknee_specimen(specimen: str, dest: Path) -> int:
    """Download one specimen's 16 model surfaces into dest; returns the file count.

    Files already present are kept (the SVN server is slow), so the command can be
    re-run to resume. Connectivity.xml is stored beside the surfaces as provenance:
    it records which original file each part came from.
    """
    from rich.progress import BarColumn, Progress, TextColumn

    svn = _oks_svn_dir(specimen)
    dest.mkdir(parents=True, exist_ok=True)
    connectivity = _fetch_bytes(f"{svn}/Model/Connectivity.xml")
    (dest / "Connectivity.xml").write_bytes(connectivity)
    files = parse_connectivity(connectivity.decode("iso-8859-1"))
    missing = [code for code, _, _ in _OKS_PARTS if code not in files]
    if missing:
        raise RuntimeError(f"{specimen}: Connectivity.xml lacks parts {', '.join(missing)}")

    n_done = 0
    with Progress(TextColumn("   {task.description}"), BarColumn(), TextColumn("{task.completed}/{task.total}")) as progress:
        task = progress.add_task(specimen, total=len(_OKS_PARTS))
        for code, stem, _ in _OKS_PARTS:
            target = dest / f"{stem}.stl"
            if not (target.exists() and target.stat().st_size > 0):
                target.write_bytes(_fetch_bytes(f"{svn}/Geometry/{files[code]}"))
            n_done += 1
            progress.update(task, advance=1)
    return n_done


def _fetch_openknee_gen1(dest: Path) -> int:
    """Download the Generation 1 FEBio model and convert it to VTU; returns the cell count."""
    from visfem.febio import febio_to_vtu

    dest.mkdir(parents=True, exist_ok=True)
    feb = dest / _GEN1_FEB
    if not (feb.exists() and feb.stat().st_size > 0):
        _download_with_progress(f"{_OPENKNEE_SVN}/_gen1/src/{_GEN1_FEB}", feb)
    (dest / "LICENSE_gen1.txt").write_bytes(_fetch_bytes(f"{_OPENKNEE_SVN}/_gen1/license.txt"))
    parts = febio_to_vtu(feb, dest / "tf_joint.vtu")
    return sum(p.n_elements for p in parts)


def cmd_fetch_openknee(args: argparse.Namespace) -> int:
    """Download Open Knee(s) geometries and lay them out as VisFEM datasets."""
    data_dir = _resolve_data_dir(args.data_dir)
    datasets = data_dir / "datasets"
    wanted = [] if args.specimens.strip().lower() == "none" else [
        s.strip().lower() for s in args.specimens.split(",") if s.strip()
    ]
    unknown = [s for s in wanted if s not in _OKS_SPECIMENS]
    if unknown:
        print(
            f"error: unknown specimen(s) {', '.join(unknown)}; "
            f"choose from {', '.join(_OKS_SPECIMENS)}",
            file=sys.stderr,
        )
        return 2

    print(
        "Open Knee(s) is provided by the Open Knee(s) Development Team (Cleveland Clinic)\n"
        "under Creative Commons terms (CC BY-SA 3.0 in the repository, CC BY 4.0 on the\n"
        "project page). By downloading you agree to attribute and cite the dataset.\n"
        f"Source: {_OPENKNEE_PAGE}\n"
    )
    print(f">> Target VisFEM data dir : {data_dir}")
    print(f">> Datasets will be placed in: {datasets}\n")

    try:
        license_text = _fetch_bytes(f"{_OPENKNEE_SVN}/license.txt")
        done: list[str] = []
        for specimen in wanted:
            dest = datasets / f"openknees_{specimen}"
            print(f">> {specimen}: downloading 16 tissue surfaces from SimTK SVN ...")
            n = _fetch_openknee_specimen(specimen, dest)
            (dest / "LICENSE.txt").write_bytes(license_text)
            _write_descriptor(dest, openknee_specimen_descriptor(specimen))
            print(f"   + openknees_{specimen}: {n} surfaces")
            done.append(f"openknees_{specimen}")
        if not args.no_gen1:
            dest = datasets / "openknees_gen1"
            print(f">> Generation 1: downloading {_GEN1_FEB} (~15 MB) and converting to VTU ...")
            n_cells = _fetch_openknee_gen1(dest)
            (dest / "LICENSE.txt").write_bytes(license_text)
            _write_descriptor(dest, openknee_gen1_descriptor())
            print(f"   + openknees_gen1: {n_cells} elements")
            done.append("openknees_gen1")
    except OSError as e:
        print(f"error: download failed: {e}", file=sys.stderr)
        print(f"       check your connection or see {_OPENKNEE_PAGE}", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        print(f"       the repository layout may have changed; see {_OPENKNEE_SVN}", file=sys.stderr)
        return 1

    if not done:
        print("nothing to do: no specimens selected and --no-gen1 given")
        return 0
    print(
        f"\n>> Done. Prepared {len(done)} dataset(s) under {datasets}\n\n"
        "   Next steps:\n"
        f'     export DATA_DIR="{data_dir}"\n'
        "     visfem validate-data     # optional: confirm the datasets resolve\n"
        "     visfem                    # launch; the knee datasets appear under Musculoskeletal"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visfem",
        description="VisFEM: web visualization of FEM models. "
        "Run with no arguments to launch the web app.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("serve", help="launch the web app (default)")
    sub.add_parser(
        "renderers",
        help="list the built-in renderers and what each is for",
        description="List every built-in renderer with a one-line description of "
        "what it draws and when to use it.",
    )
    sub.add_parser(
        "schema",
        help="print a concise reference of the dataset JSON fields",
        description="Print the dataset descriptor fields, their meaning, and the "
        "valid values for enum-like fields (scales, organ systems, "
        "renderers, palettes, colormaps).",
    )

    p_ex = sub.add_parser(
        "example",
        help="print a minimal valid dataset JSON for a renderer",
        description="Print a ready-to-edit dataset descriptor for one renderer to "
        "stdout. Run `visfem renderers` to see what each renderer does.",
    )
    p_ex.add_argument(
        "renderer",
        choices=[r.value for r in RendererName],
        help="which renderer to template (see `visfem renderers`)",
    )

    p_new = sub.add_parser(
        "new-dataset",
        help="scaffold a dataset folder + JSON template",
        description="Create datasets/<name>/<name>.json from a commented, "
        "renderer-specific template under your data directory, then "
        "drop your mesh files beside it and run `visfem validate-data`.",
    )
    p_new.add_argument("name", help="dataset key / folder name (e.g. my_model)")
    p_new.add_argument(
        "--renderer",
        choices=[r.value for r in RendererName],
        help="renderer to template (default: surface; "
        "see `visfem renderers` for descriptions)",
    )

    sub.add_parser(
        "validate-data",
        help="validate dataset JSONs and referenced files",
        description="Validate every dataset descriptor under your data directory "
        "and confirm the mesh files each one references exist.",
    )

    p_fetch = sub.add_parser(
        "fetch-ircadb",
        help="download the public 3D-IRCADb-01 example dataset",
        description="Download the public 3D-IRCADb-01 dataset (~3 GB) from IRCAD "
        "and lay it out as a ready-to-open VisFEM dataset. The data is "
        "provided by IRCAD under its own license terms.",
        epilog="Source: " + _IRCAD_PAGE,
    )
    p_fetch.add_argument(
        "--data-dir",
        help="target data directory (default: $DATA_DIR, else ./visfem_data)",
    )

    p_knee = sub.add_parser(
        "fetch-openknee",
        help="download the Open Knee(s) knee geometries from SimTK",
        description="Download Open Knee(s) geometries from the project's public SVN "
        "repository (no SimTK account needed) and lay them out as VisFEM "
        "datasets: the segmented tissue surfaces of the eight simulation-ready "
        "Generation 2 specimens (~25 MB each) and the Generation 1 tibiofemoral "
        "FEBio model (~15 MB, converted to VTU). The data is provided by the "
        "Open Knee(s) Development Team under Creative Commons terms.",
        epilog="Source: " + _OPENKNEE_PAGE,
    )
    p_knee.add_argument(
        "--data-dir",
        help="target data directory (default: $DATA_DIR, else ./visfem_data)",
    )
    p_knee.add_argument(
        "--specimens",
        default=",".join(_OKS_SPECIMENS),
        help="comma-separated Generation 2 specimen ids to fetch "
        f"(default: all of {', '.join(_OKS_SPECIMENS)}); 'none' skips them",
    )
    p_knee.add_argument(
        "--no-gen1",
        action="store_true",
        help="skip the Generation 1 FEBio model",
    )
    return parser


_SUBCOMMANDS = (
    "serve",
    "renderers",
    "schema",
    "example",
    "new-dataset",
    "validate-data",
    "fetch-ircadb",
    "fetch-openknee",
)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    argv = sys.argv[1:] if argv is None else argv

    # No args or an explicit `serve` launches the web app. A leading option
    # (e.g. -h) or a subcommand is handled by argparse below; an unknown first
    # token errors there rather than silently launching the app.
    if not argv or argv[0] == "serve":
        return _serve()

    parser = build_parser()
    first = argv[0]
    if not first.startswith("-") and first not in _SUBCOMMANDS:
        print(f"visfem: unknown command '{first}'\n", file=sys.stderr)
        parser.print_help(sys.stderr)
        return 2

    args = parser.parse_args(argv)
    handlers = {
        "renderers": cmd_renderers,
        "schema": cmd_schema,
        "example": cmd_example,
        "new-dataset": cmd_new_dataset,
        "validate-data": cmd_validate_data,
        "fetch-ircadb": cmd_fetch_ircadb,
        "fetch-openknee": cmd_fetch_openknee,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
