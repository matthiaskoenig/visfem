"""Tests of the files generated from the lock file."""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).parent.parent
REQUIREMENTS = REPO_DIR / "setup" / "requirements.txt"


@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv")
@pytest.mark.skipif(
    not (REPO_DIR / "uv.lock").exists(), reason="needs the lock file of a checkout"
)
def test_deployment_requirements_match_the_lock_file(tmp_path: Path) -> None:
    """Check that setup/requirements.txt is the export of uv.lock, a dependency update regenerates it."""
    out = tmp_path / "requirements.txt"
    subprocess.run(
        [
            "uv",
            "export",
            "--quiet",
            "--frozen",
            "--no-dev",
            "--no-editable",
            "--no-emit-project",
            "-o",
            str(out),
        ],
        cwd=REPO_DIR,
        check=True,
    )
    # the header names the output file of the export
    exported = out.read_text().replace(str(out), "setup/requirements.txt")
    assert exported == REQUIREMENTS.read_text(), (
        "setup/requirements.txt is outdated, run: "
        "uv export --frozen --no-dev --no-editable --no-emit-project -o setup/requirements.txt"
    )
