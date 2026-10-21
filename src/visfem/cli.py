"""Command-line interface for VisFEM.

Usage:
    visfem                     # launch the web app (same as `visfem serve`)
    visfem renderers           # list the built-in renderers and what each is for
    visfem schema              # reference of the dataset JSON fields
    visfem example <renderer>  # print a minimal valid dataset JSON for a renderer
    visfem new-dataset NAME    # scaffold a dataset folder and JSON template
    visfem validate-data       # validate every dataset JSON and its referenced files
    visfem fetch-ircadb        # download the public 3D-IRCADb-01 example dataset
    visfem fetch-openknee      # download the Open Knee(s) knee geometries from SimTK

The data-authoring commands read and write the data directory: DATA_DIR or
VISFEM_DATA_DIR, else the bundled data.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from visfem.models import RenderConfig, RendererName


def _serve() -> int:
    """Launch the web app; returns exit code 0."""
    from visfem.app import main as app_main

    app_main()
    return 0


# One-line description per renderer, printed by `visfem renderers`.
_RENDERER_HELP: dict[RendererName, str] = {
    RendererName.SURFACE: "one solid-colour mesh (STL/VTU/OBJ), the default for a single static surface",
    RendererName.MULTI_PART: "several named part files merged and coloured together (e.g. arteries + veins)",
    RendererName.REGION_ID: "one mesh coloured by an integer cell array (regions/materials), with optional fibre glyphs",
    RendererName.SCALAR_FIELD: "a static mesh coloured by a selectable scalar field (continuous ramp and/or categorical zones)",
    RendererName.TIMESERIES: "a scalar field animated over time from XDMF, PVD, a flat VTK series, or an LS-DYNA d3plot",
    RendererName.PVD_PHASE_SERIES: "per-patient region-coloured phase surfaces driven by a .pvd manifest",
    RendererName.PATIENT_ORGANS: "per-patient folders of per-organ .vtk meshes (the 3D-IRCADb-01 family)",
}


def cmd_renderers(_args: argparse.Namespace) -> int:
    """Print the built-in renderers with a one-line description each; returns 0."""
    width = max(len(r.value) for r in RendererName)
    print("Built-in renderers (set as render.renderer in a dataset JSON):\n")
    for renderer in RendererName:
        print(f"  {renderer.value:<{width}}  {_RENDERER_HELP[renderer]}")
    print("\nRun `visfem example <renderer>` for a ready-to-edit template.")
    return 0


def cmd_validate_data(_args: argparse.Namespace) -> int:
    """Validate every dataset JSON and check its mesh files exist; returns 1 on a problem, else 0."""
    from visfem.engine.discovery import (
        DATASETS_DIR,
        dataset_dir,
        iter_descriptor_paths,
        load_descriptor,
    )
    from visfem.engine.renderers import resolve_render_config

    if not DATASETS_DIR.is_dir():
        print(f"error: datasets dir not found: {DATASETS_DIR}", file=sys.stderr)
        return 1

    errors: list[str] = []
    n_ok = 0
    for path in iter_descriptor_paths():
        try:
            meta = load_descriptor(path)
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
    """Format a ValidationError *e* as indented `field: message` lines."""
    lines: list[str] = []
    for err in e.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def _check_render_files(ddir: Path, cfg: RenderConfig) -> list[str]:
    """Return the problems with the files *cfg* references under *ddir*."""
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
    """Print a reference of the dataset JSON fields; returns 0."""
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
  spp_project        SPP2311 project title (None for projects outside the SPP)
  spp_badge          true to show the SPP2311 badge
  subgroup           sub-group label within the organ group
  sort_order         explicit sort position (int)
  render             how to draw it (see below); omit to infer from mesh_format

render block (renderer = one of: {renderers}):
  see `visfem example <renderer>` for a ready-to-edit template per renderer,
  or `visfem renderers` for a one-line description of each.
  Omit the whole block for a single STL or an XDMF/PVD series; it is inferred.

  categorical_palette   one of: {palettes}
  continuous_cmap       one of: {cmaps}
""")
    return 0


def _base(**over: object) -> dict:
    """Return the shared metadata fields of every example, updated with *over*."""
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


# One valid example per renderer, used by `example` and `new-dataset`.
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
            # Fields drawn as discrete zones labelled by region_labels:
            "categorical_fields": [],
            "region_labels": {},
        },
    ),
    RendererName.TIMESERIES: _base(
        organ_system=["liver"],
        mesh_format="VTK",
        render={
            "renderer": "timeseries",
            # Per-step mesh glob, natural-sorted into steps; XDMF/PVD datasets omit it.
            "series": "frame_*.vtk",
            "default_field": "concentration",
            "fields": [{"name": "concentration", "label": "concentration"}],
            # "exclude_fields": []   # (manifest series) discovered field names to hide
            # "database": "d3plot"   # LS-DYNA master file; the dataset folder is the database directory
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
    """Print the minimal valid dataset JSON for args.renderer; returns 0."""
    example = _EXAMPLES[RendererName(args.renderer)]
    print(json.dumps(example, indent=2))
    return 0


def cmd_new_dataset(args: argparse.Namespace) -> int:
    """Scaffold datasets/<name>/<name>.json from a template; returns 1 when it exists, else 0."""
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

# Shared by both fetch commands.
_USER_AGENT = "visfem-fetch"
_HTTP_TIMEOUT = 60.0  # seconds without any data before a download is abandoned

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
    """Return the data dir: *arg*, else $DATA_DIR or $VISFEM_DATA_DIR, else ./visfem_data."""
    env = os.environ.get("DATA_DIR") or os.environ.get("VISFEM_DATA_DIR")
    return Path(arg or env or (Path.cwd() / "visfem_data")).expanduser()


def _download_with_progress(url: str, dest: Path) -> None:
    """Stream *url* to *dest* with a progress bar, resuming a .part file; raises OSError on failure."""
    import http.client
    import urllib.error
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

    part = dest.with_name(dest.name + ".part")
    offset = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": _USER_AGENT}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT)
    except urllib.error.HTTPError as e:
        if e.code != 416 or not offset:
            raise
        # The range starts past the end: the part is stale. Start over.
        part.unlink()
        _download_with_progress(url, dest)
        return
    with resp:
        if resp.status != 206:
            offset = 0  # a non-206 status carries the whole file: start over
        length = resp.headers.get("Content-Length")
        total = offset + int(length) if length else None
        columns: list[ProgressColumn] = [
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
        ]
        with Progress(*columns) as progress:
            task = progress.add_task("Downloading", total=total, completed=offset)
            with part.open("ab" if offset else "wb") as fh:
                try:
                    while chunk := resp.read(1 << 20):  # 1 MiB
                        fh.write(chunk)
                        progress.update(task, advance=len(chunk))
                except (
                    http.client.HTTPException
                ) as e:  # e.g. IncompleteRead on a dropped connection
                    raise OSError(
                        f"connection lost while downloading {url}: {e}"
                    ) from e
    size = part.stat().st_size
    # The part becomes dest only at full size; a short part stays for the next run.
    if total is not None and size != total:
        raise OSError(
            f"incomplete download of {url}: got {size} of {total} bytes (re-run to resume)"
        )
    part.replace(dest)


def _write_atomic(path: Path, data: bytes) -> None:
    """Write *data* to *path* atomically through a temporary sibling."""
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def _write_descriptor(dest: Path, descriptor: dict) -> None:
    """Write *descriptor* to dest/<data_path>.json, keeping an existing file, and print the outcome."""
    path = dest / f"{descriptor['data_path']}.json"
    if path.exists():
        print(f"   descriptor already exists, leaving it as-is: {path.name}")
    else:
        path.write_text(json.dumps(descriptor, indent=2) + "\n")
        print(f"   wrote dataset descriptor: {path.name}")


def _print_fetch_header(
    notice: str, page: str, data_dir: Path, target_label: str, target: Path
) -> None:
    """Print the license *notice* with its source *page*, then *data_dir* and the *target* path under *target_label*."""
    print(f"{notice}\nSource: {page}\n")
    print(f">> Target VisFEM data dir : {data_dir}")
    print(f">> {target_label} will be placed in: {target}\n")


def _print_next_steps(summary: str, data_dir: Path, launch_hint: str) -> None:
    """Print the fetch epilogue: the *summary* line, the DATA_DIR export for *data_dir* and the *launch_hint*."""
    print(
        f"\n>> Done. {summary}\n\n"
        "   Next steps:\n"
        f'     export DATA_DIR="{data_dir}"\n'
        "     visfem validate-data     # optional: confirm the datasets resolve\n"
        f"     visfem                    # launch; {launch_hint}"
    )


def _report_download_failure(e: OSError, page: str) -> int:
    """Print the download error *e* and the dataset *page* to stderr; returns exit code 1."""
    print(f"error: download failed: {e}", file=sys.stderr)
    print(f"       check your connection or see {page}", file=sys.stderr)
    return 1


def _extract_ircadb(zip_path: Path, dest: Path) -> int:
    """Extract each patient's .vtk meshes from *zip_path* to dest/patient_NN/; returns the patient count."""
    import io
    import re
    import zipfile

    count = 0
    with zipfile.ZipFile(zip_path) as outer:
        # Layout: 3Dircadb1/3Dircadb1.<N>/MESHES_VTK.zip, each holding <organ>.vtk files.
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
                    # Inner zip members may carry a MESHES_VTK/ prefix.
                    target = pdir / Path(name).name
                    target.write_bytes(inner.read(name))
                    n_vtk += 1
            if n in licenses:
                (pdir / "LICENSE.txt").write_bytes(outer.read(licenses[n]))
            print(f"   + patient_{n:02d}: {n_vtk} meshes")
            count += 1
    return count


def cmd_fetch_ircadb(args: argparse.Namespace) -> int:
    """Download 3D-IRCADb-01 and lay it out as a VisFEM dataset; returns 1 on error, else 0."""
    data_dir = _resolve_data_dir(args.data_dir)
    dest = data_dir / "datasets" / "ircadb"

    _print_fetch_header(
        "3D-IRCADb-01 is provided by IRCAD (Strasbourg) under its own license terms.\n"
        "By downloading you agree to respect them and to cite the dataset.",
        _IRCAD_PAGE,
        data_dir,
        "IRCADb",
        dest,
    )
    dest.mkdir(parents=True, exist_ok=True)

    # The archive stays in the data dir: an interrupted download resumes and a failed extraction keeps it.
    zip_path = data_dir / "downloads" / "3Dircadb1.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        print(f">> Using the previously downloaded archive: {zip_path}")
    else:
        print(
            ">> Downloading 3D-IRCADb-01 (~3 GB) from IRCAD (re-run to resume if interrupted) ..."
        )
        try:
            _download_with_progress(_IRCAD_URL, zip_path)
        except OSError as e:
            return _report_download_failure(e, _IRCAD_PAGE)

    print(">> Extracting per-patient meshes ...")
    try:
        count = _extract_ircadb(zip_path, dest)
    except Exception as e:  # noqa: BLE001 - zipfile.BadZipFile and friends
        print(f"error: could not extract the archive: {e}", file=sys.stderr)
        print(
            f"       the archive layout may have changed; see {_IRCAD_PAGE}\n"
            f"       the archive was kept at {zip_path}",
            file=sys.stderr,
        )
        return 1
    if args.keep_archive:
        print(f">> Kept the archive: {zip_path}")
    else:
        zip_path.unlink()

    if count == 0:
        print("error: no patient meshes were extracted.", file=sys.stderr)
        return 1

    _write_descriptor(dest, _IRCAD_DESCRIPTOR)
    _print_next_steps(
        f"Prepared {count} patient(s) under {dest}",
        data_dir,
        "'3D-IRCADb-01' appears in the sidebar",
    )
    return 0


# fetch-openknee: download Open Knee(s) knee geometries from the SimTK SVN repository.
# The SVN repository is readable anonymously over HTTPS; the Downloads tab needs an account.

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

# Generation 2 specimens with a simulation-ready model (Chokhandre et al. 2023).
# id -> (side, sex, age in years, BMI); the cohort numbering skips oks005.
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

# Generation 1 FEBio material id -> [legend name, material name in the .feb file].
# Cartilage is meshed in three hex layers through its thickness (suffixes b/m/t).
# Materials 16 and 17 are empty image-link rigid bodies.
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
    """Return the base SVN URL of *specimen*'s Geometry/ and Model/ folders."""
    base = f"{_OPENKNEE_SVN}/oks/{specimen}"
    return f"{base}/dat" if specimen in _OKS_SVN_DAT_LEVEL else base


def _fetch_bytes(url: str) -> bytes:
    """GET *url* and return the body; raises OSError on a timeout or a truncated response."""
    import http.client
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            data = bytes(resp.read())
            length = resp.headers.get("Content-Length")
    except http.client.HTTPException as e:  # IncompleteRead on a dropped connection
        raise OSError(f"connection lost while fetching {url}: {e}") from e
    if length and len(data) != int(length):
        raise OSError(
            f"truncated response from {url}: got {len(data)} of {length} bytes"
        )
    return data


def parse_connectivity(xml_text: str) -> dict[str, str]:
    """Map part code -> meshed surface filename from an Open Knee(s) Connectivity.xml *xml_text*."""
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
    """Return the dataset JSON for one Generation 2 *specimen*."""
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
    """Return the dataset JSON for the Generation 1 tibiofemoral FEBio model."""
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


def _fetch_openknee_specimen(specimen: str, dest: Path) -> int:
    """Fetch *specimen*'s 16 surfaces and Connectivity.xml into *dest*; returns the surface count."""
    from rich.progress import BarColumn, Progress, TextColumn

    svn = _oks_svn_dir(specimen)
    dest.mkdir(parents=True, exist_ok=True)
    connectivity = _fetch_bytes(f"{svn}/Model/Connectivity.xml")
    # Connectivity.xml stays beside the surfaces as provenance of each part's source file.
    _write_atomic(dest / "Connectivity.xml", connectivity)
    files = parse_connectivity(connectivity.decode("iso-8859-1"))
    missing = [code for code, _, _ in _OKS_PARTS if code not in files]
    if missing:
        raise RuntimeError(
            f"{specimen}: Connectivity.xml lacks parts {', '.join(missing)}"
        )

    n_done = 0
    with Progress(
        TextColumn("   {task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
    ) as progress:
        task = progress.add_task(specimen, total=len(_OKS_PARTS))
        for code, stem, _ in _OKS_PARTS:
            target = dest / f"{stem}.stl"
            # A present file is complete (atomic write) and skipped; a re-run resumes from it on the slow SVN server.
            if not target.exists():
                _write_atomic(target, _fetch_bytes(f"{svn}/Geometry/{files[code]}"))
            n_done += 1
            progress.update(task, advance=1)
    return n_done


def _fetch_openknee_gen1(dest: Path) -> int:
    """Download the Generation 1 FEBio model and convert it to VTU; returns the cell count."""
    from visfem.febio import febio_to_vtu

    dest.mkdir(parents=True, exist_ok=True)
    feb = dest / _GEN1_FEB
    if not feb.exists():
        _download_with_progress(f"{_OPENKNEE_SVN}/_gen1/src/{_GEN1_FEB}", feb)
    _write_atomic(
        dest / "LICENSE_gen1.txt", _fetch_bytes(f"{_OPENKNEE_SVN}/_gen1/license.txt")
    )
    parts = febio_to_vtu(feb, dest / "tf_joint.vtu")
    return sum(p.n_elements for p in parts)


def cmd_fetch_openknee(args: argparse.Namespace) -> int:
    """Fetch Open Knee(s) datasets; returns 2 for an unknown specimen, 1 on error, else 0."""
    data_dir = _resolve_data_dir(args.data_dir)
    datasets = data_dir / "datasets"
    wanted = (
        []
        if args.specimens.strip().lower() == "none"
        else [s.strip().lower() for s in args.specimens.split(",") if s.strip()]
    )
    unknown = [s for s in wanted if s not in _OKS_SPECIMENS]
    if unknown:
        print(
            f"error: unknown specimen(s) {', '.join(unknown)}; "
            f"choose from {', '.join(_OKS_SPECIMENS)}",
            file=sys.stderr,
        )
        return 2

    _print_fetch_header(
        "Open Knee(s) is provided by the Open Knee(s) Development Team (Cleveland Clinic)\n"
        "under Creative Commons terms (CC BY-SA 3.0 in the repository, CC BY 4.0 on the\n"
        "project page). By downloading you agree to attribute and cite the dataset.",
        _OPENKNEE_PAGE,
        data_dir,
        "Datasets",
        datasets,
    )

    try:
        license_text = _fetch_bytes(f"{_OPENKNEE_SVN}/license.txt")
        done: list[str] = []
        for specimen in wanted:
            dest = datasets / f"openknees_{specimen}"
            print(f">> {specimen}: downloading 16 tissue surfaces from SimTK SVN ...")
            n = _fetch_openknee_specimen(specimen, dest)
            _write_atomic(dest / "LICENSE.txt", license_text)
            _write_descriptor(dest, openknee_specimen_descriptor(specimen))
            print(f"   + openknees_{specimen}: {n} surfaces")
            done.append(f"openknees_{specimen}")
        if not args.no_gen1:
            dest = datasets / "openknees_gen1"
            print(
                f">> Generation 1: downloading {_GEN1_FEB} (~15 MB) and converting to VTU ..."
            )
            n_cells = _fetch_openknee_gen1(dest)
            _write_atomic(dest / "LICENSE.txt", license_text)
            _write_descriptor(dest, openknee_gen1_descriptor())
            print(f"   + openknees_gen1: {n_cells} elements")
            done.append("openknees_gen1")
    except OSError as e:
        return _report_download_failure(e, _OPENKNEE_PAGE)
    except (RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        print(
            f"       the repository layout may have changed; see {_OPENKNEE_SVN}",
            file=sys.stderr,
        )
        return 1

    if not done:
        print("nothing to do: the selection is empty (--specimens none with --no-gen1)")
        return 0
    _print_next_steps(
        f"Prepared {len(done)} dataset(s) under {datasets}",
        data_dir,
        "the knee datasets appear under Musculoskeletal",
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Return the visfem parser; each subparser sets ``func`` and the ``commands`` default lists every subcommand."""
    parser = argparse.ArgumentParser(
        prog="visfem",
        description="VisFEM: web visualization of FEM models. "
        "Run with no arguments to launch the web app.",
    )
    sub = parser.add_subparsers(dest="command")
    # Shared by both fetch commands; a parent parser keeps the option first in --help.
    data_dir_opts = argparse.ArgumentParser(add_help=False)
    data_dir_opts.add_argument(
        "--data-dir",
        help="target data directory (default: $DATA_DIR, else ./visfem_data)",
    )

    sub.add_parser("serve", help="launch the web app (default)").set_defaults(
        func=lambda _args: _serve()
    )
    sub.add_parser(
        "renderers",
        help="list the built-in renderers and what each is for",
        description="List every built-in renderer with a one-line description of "
        "what it draws and when to use it.",
    ).set_defaults(func=cmd_renderers)
    sub.add_parser(
        "schema",
        help="print a concise reference of the dataset JSON fields",
        description="Print the dataset descriptor fields, their meaning, and the "
        "valid values for enum-like fields (scales, organ systems, "
        "renderers, palettes, colormaps).",
    ).set_defaults(func=cmd_schema)

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
    p_ex.set_defaults(func=cmd_example)

    p_new = sub.add_parser(
        "new-dataset",
        help="scaffold a dataset folder and JSON template",
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
    p_new.set_defaults(func=cmd_new_dataset)

    sub.add_parser(
        "validate-data",
        help="validate dataset JSONs and referenced files",
        description="Validate every dataset descriptor under your data directory "
        "and confirm the mesh files each one references exist.",
    ).set_defaults(func=cmd_validate_data)

    p_fetch = sub.add_parser(
        "fetch-ircadb",
        parents=[data_dir_opts],
        help="download the public 3D-IRCADb-01 example dataset",
        description="Download the public 3D-IRCADb-01 dataset (~3 GB) from IRCAD "
        "and lay it out as a ready-to-open VisFEM dataset. The data is "
        "provided by IRCAD under its own license terms.",
        epilog="Source: " + _IRCAD_PAGE,
    )
    p_fetch.add_argument(
        "--keep-archive",
        action="store_true",
        help="keep the downloaded archive under <data-dir>/downloads/ after extraction",
    )
    p_fetch.set_defaults(func=cmd_fetch_ircadb)

    p_knee = sub.add_parser(
        "fetch-openknee",
        parents=[data_dir_opts],
        help="download the Open Knee(s) knee geometries from SimTK",
        description="Download Open Knee(s) geometries from the project's anonymously "
        "readable SVN repository and lay them out as VisFEM "
        "datasets: the segmented tissue surfaces of the eight simulation-ready "
        "Generation 2 specimens (~25 MB each) and the Generation 1 tibiofemoral "
        "FEBio model (~15 MB, converted to VTU). The data is provided by the "
        "Open Knee(s) Development Team under Creative Commons terms.",
        epilog="Source: " + _OPENKNEE_PAGE,
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
    p_knee.set_defaults(func=cmd_fetch_openknee)
    parser.set_defaults(commands=tuple(sub.choices))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI on *argv* (default sys.argv[1:]) and return the exit code."""
    argv = sys.argv[1:] if argv is None else argv

    # No args or `serve` launches the app; an unknown first token exits with the help.
    if not argv or argv[0] == "serve":
        return _serve()

    parser = build_parser()
    first = argv[0]
    if not first.startswith("-") and first not in parser.get_default("commands"):
        print(f"visfem: unknown command '{first}'\n", file=sys.stderr)
        parser.print_help(sys.stderr)
        return 2

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
