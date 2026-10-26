"""Tests of the command line: dispatch of the app launch and the IRCADb extraction."""

import io
import zipfile
from pathlib import Path

import pytest

from visfem import cli


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["serve"],
        ["serve", "--port", "9000"],
        # the trame launcher of the deployment, see setup/apps.yml
        ["--host", "0.0.0.0", "--port", "9001", "--authKey", "s", "--server"],
    ],
)
def test_main_launches_the_app(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that no arguments, `serve` and trame server options launch the app."""
    calls: list[bool] = []
    monkeypatch.setattr(cli, "_serve", lambda: calls.append(True) or 0)
    assert cli.main(argv) == 0
    assert calls == [True]


def test_main_help_does_not_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that `--help` prints the help of the command line instead of launching."""
    monkeypatch.setattr(cli, "_serve", lambda: pytest.fail("app launched"))
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0


def _ircadb_archive(path: Path, meshes: dict[str, bytes]) -> Path:
    """Write an archive with the layout of 3D-IRCADb-01 holding *meshes* for patient 1."""
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        for name, data in meshes.items():
            z.writestr(name, data)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("3Dircadb1/3Dircadb1.1/MESHES_VTK.zip", inner.getvalue())
        z.writestr("3Dircadb1/3Dircadb1.1/LICENSE.txt", b"license")
    return path


def test_extract_ircadb(tmp_path: Path) -> None:
    """Check that the meshes land in the patient folder, also those with a parent path."""
    archive = _ircadb_archive(
        tmp_path / "a.zip",
        {"MESHES_VTK/liver.vtk": b"liver", "../../outside.vtk": b"x", "notes.txt": b""},
    )
    assert cli._extract_ircadb(archive, tmp_path / "out") == 1
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    assert "outside.vtk" not in files
    assert (tmp_path / "out/patient_01/liver.vtk").read_bytes() == b"liver"
    assert (tmp_path / "out/patient_01/outside.vtk").exists()
    assert not (tmp_path / "out/patient_01/notes.txt").exists()


def test_extract_ircadb_rejects_oversized_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that a member larger than the limit stops the extraction."""
    archive = _ircadb_archive(tmp_path / "a.zip", {"liver.vtk": b"x" * 100})
    monkeypatch.setattr(cli, "_MAX_MESH", 10)
    with pytest.raises(ValueError, match="exceeds"):
        cli._extract_ircadb(archive, tmp_path / "out")
