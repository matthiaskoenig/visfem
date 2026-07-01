#!/usr/bin/env bash
#
# fetch_ircadb.sh: download 3D-IRCADb-01 and lay it out for VisFEM.
#
# Downloads the public 3D-IRCADb-01 dataset from IRCAD, extracts the
# per-patient surface meshes, and writes them into a VisFEM data directory as
#
#     <DATA_DIR>/datasets/ircadb/patient_NN/<organ>.vtk
#
# plus an ircadb.json descriptor, so the dataset loads with the built-in
# `patient_organs` renderer. After running this, point VisFEM at the folder:
#
#     export DATA_DIR="<the data dir this script filled>"
#     visfem
#
# Data: 3D-IRCADb-01, IRCAD, Strasbourg (Soler et al., 2010). The archive
# carries its own LICENSE.txt per patient — please respect IRCAD's terms and
# cite the dataset. Landing page:
#   https://www.ircad.fr/research/data-sets/liver-segmentation-3d-ircadb-01/
#
# Usage:
#   scripts/fetch_ircadb.sh [DATA_DIR]
#
#   DATA_DIR   Target VisFEM data directory (default: ./visfem_data, or $DATA_DIR
#              from the environment if set). The meshes land under
#              <DATA_DIR>/datasets/ircadb/.
#
# Options:
#   -h, --help   Show this help and exit.
#
# Requires: curl, unzip.

set -euo pipefail

IRCAD_URL="https://cloud.ircad.fr/index.php/s/JN3z7EynBiwYyjy/download"
IRCAD_PAGE="https://www.ircad.fr/research/data-sets/liver-segmentation-3d-ircadb-01/"

usage() { sed -n '2,/^# Requires:/p' "$0" | sed 's/^#\{0,1\} \{0,1\}//'; }

for arg in "${@:-}"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
  esac
done

# --- resolve target data dir --------------------------------------------------
DATA_DIR="${1:-${DATA_DIR:-$PWD/visfem_data}}"
DEST="$DATA_DIR/datasets/ircadb"

# --- dependency checks --------------------------------------------------------
missing=()
for cmd in curl unzip; do
  command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "error: missing required command(s): ${missing[*]}" >&2
  echo "       install them and re-run (e.g. 'sudo apt install ${missing[*]}')." >&2
  exit 1
fi

echo ">> Target VisFEM data dir : $DATA_DIR"
echo ">> IRCADb will be placed in: $DEST"
mkdir -p "$DEST"

# --- work in a temp dir, cleaned up on exit -----------------------------------
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

ZIP="$WORK/3Dircadb1.zip"
echo ">> Downloading 3D-IRCADb-01 (~3 GB) from IRCAD ..."
echo "   $IRCAD_URL"
# -L follows the share -> DAV redirect; -f fails loudly on HTTP errors.
curl -fL --progress-bar -o "$ZIP" "$IRCAD_URL"

echo ">> Extracting outer archive ..."
unzip -q "$ZIP" -d "$WORK"

# The archive expands to  3Dircadb1/3Dircadb1.<N>/  (N = 1..20, not zero-padded).
OUTER="$(find "$WORK" -maxdepth 2 -type d -name '3Dircadb1.*' -print -quit)"
if [ -z "$OUTER" ]; then
  echo "error: could not find 3Dircadb1.<N> patient folders in the archive." >&2
  echo "       The archive layout may have changed; see $IRCAD_PAGE" >&2
  exit 1
fi
ROOT="$(dirname "$OUTER")"

# --- per patient: unzip MESHES_VTK.zip into patient_NN/ (zero-padded) ---------
count=0
for d in "$ROOT"/3Dircadb1.*; do
  [ -d "$d" ] || continue
  n="$(basename "$d" | sed 's/.*\.//')"          # 1, 2, ... 20
  case "$n" in ''|*[!0-9]*) continue ;; esac      # skip anything non-numeric
  pdir="$DEST/$(printf 'patient_%02d' "$n")"
  mesh_zip="$d/MESHES_VTK.zip"
  if [ ! -f "$mesh_zip" ]; then
    echo "   ! patient $n: no MESHES_VTK.zip, skipping" >&2
    continue
  fi
  mkdir -p "$pdir"
  # -j flattens (drop the MESHES_VTK/ prefix); keep only .vtk surface meshes.
  unzip -q -o -j "$mesh_zip" '*.vtk' -d "$pdir"
  # Copy the per-patient license alongside the meshes if present.
  [ -f "$d/LICENSE.txt" ] && cp -f "$d/LICENSE.txt" "$pdir/LICENSE.txt" || true
  n_vtk="$(find "$pdir" -maxdepth 1 -name '*.vtk' | wc -l | tr -d ' ')"
  echo "   + $(basename "$pdir"): $n_vtk meshes"
  count=$((count + 1))
done

if [ "$count" -eq 0 ]; then
  echo "error: no patient meshes were extracted." >&2
  exit 1
fi

# --- write the VisFEM descriptor --------
JSON="$DEST/ircadb.json"
if [ -f "$JSON" ]; then
  echo ">> Descriptor already exists, leaving it as-is: $JSON"
else
  echo ">> Writing dataset descriptor: $JSON"
  cat > "$JSON" <<'JSON'
{
  "data_path": "ircadb",
  "name": "3D-IRCADb-01",
  "pi": "Luc Soler",
  "institution": ["IRCAD, Strasbourg, France"],
  "biological_scale": "organ_system",
  "organ_system": ["torso", "lung", "kidney", "bone", "vasculature", "abdominal"],
  "description": "3D-IRCADb-01: CT-segmented surface meshes from 20 patients (10 women, 10 men), hepatic tumours in 75% of cases, covering up to 47 organ types per patient.",
  "mesh_format": "VTK",
  "references": [
    "https://www.ircad.fr/research/data-sets/liver-segmentation-3d-ircadb-01/",
    "Soler et al. 3D image reconstruction for comparison of algorithm database. IRCAD, Strasbourg, France, Tech. Rep (2010)"
  ],
  "render": {"renderer": "patient_organs"}
}
JSON
fi

echo
echo ">> Done. Prepared $count patient(s) under $DEST"
echo
echo "   Next steps:"
echo "     export DATA_DIR=\"$DATA_DIR\""
echo "     visfem validate-data     # optional: confirm the dataset resolves"
echo "     visfem                    # launch; '3D-IRCADb-01' appears in the sidebar"
