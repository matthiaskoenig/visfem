"""Tests of the command line: dispatch of the app launch and the IRCADb extraction."""

import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.conftest import region_grid
from visfem import cli
from visfem.models import ProjectMetadata, RendererName


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


def test_renderers_lists_every_renderer(capsys: pytest.CaptureFixture[str]) -> None:
    """Check that `visfem renderers` describes every renderer."""
    assert cli.main(["renderers"]) == 0
    out = capsys.readouterr().out
    for renderer in RendererName:
        assert renderer.value in out


def test_schema(capsys: pytest.CaptureFixture[str]) -> None:
    """Check that `visfem schema` lists the required fields and the renderers."""
    assert cli.main(["schema"]) == 0
    out = capsys.readouterr().out
    for field in ["data_path", "organ_system", "mesh_format", "render"]:
        assert field in out


@pytest.mark.parametrize("renderer", list(RendererName))
def test_example_is_a_valid_descriptor(
    renderer: RendererName, capsys: pytest.CaptureFixture[str]
) -> None:
    """Check that the example of every renderer validates and selects that renderer."""
    assert cli.main(["example", renderer.value]) == 0
    meta = ProjectMetadata.model_validate_json(capsys.readouterr().out)
    assert meta.render is not None
    assert meta.render.renderer == renderer


def test_unknown_command(capsys: pytest.CaptureFixture[str]) -> None:
    """Check that an unknown command exits with the help."""
    assert cli.main(["render"]) == 2
    assert "unknown command 'render'" in capsys.readouterr().err


def test_new_dataset(datasets_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Check the scaffold of a dataset: a valid descriptor which is never overwritten."""
    assert cli.main(["new-dataset", "knee", "--renderer", "region_id"]) == 0
    path = datasets_dir / "knee" / "knee.json"
    meta = ProjectMetadata.model_validate_json(path.read_text())
    assert meta.data_path == "knee"
    assert meta.render is not None and meta.render.renderer == RendererName.REGION_ID

    path.write_text("{}")
    assert cli.main(["new-dataset", "knee"]) == 1
    assert path.read_text() == "{}"
    assert "already exists" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["../outside", "a b", "a/b"])
def test_new_dataset_rejects_bad_keys(
    name: str, datasets_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Check that new-dataset creates nothing for a name which is no dataset key."""
    assert cli.main(["new-dataset", name]) == 1
    assert "no dataset key" in capsys.readouterr().err
    assert not any(datasets_dir.parent.rglob("*.json"))


def test_validate_data(
    add_dataset: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Check that validate-data accepts complete datasets and reports every problem."""
    folder = add_dataset(
        "good",
        render={
            "renderer": "region_id",
            "mesh_file": "mesh.vtu",
            "region_array": "PartId",
        },
    )
    region_grid().save(folder / "mesh.vtu")
    assert cli.main(["validate-data"]) == 0
    assert "1 dataset(s) OK, 0 problem(s)" in capsys.readouterr().out

    add_dataset(
        "missing_mesh", render={"renderer": "region_id", "mesh_file": "nope.vtu"}
    )
    add_dataset("no_series", render={"series": "frame_*.vtk"})
    bad = add_dataset("invalid")
    (bad / "invalid.json").write_text(json.dumps({"name": "only a name"}))
    assert cli.main(["validate-data"]) == 1
    captured = capsys.readouterr()
    assert "mesh_file 'nope.vtu' not found" in captured.err + captured.out
    assert "series glob 'frame_*.vtk' matched no files" in captured.err + captured.out
    assert "invalid metadata" in captured.err + captured.out


def test_validate_data_without_datasets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Check that validate-data fails when the datasets folder does not exist."""
    from visfem.engine import discovery

    monkeypatch.setattr(discovery, "DATASETS_DIR", tmp_path / "missing")
    assert cli.main(["validate-data"]) == 1
    assert "datasets dir not found" in capsys.readouterr().err


def test_validate_data_checks_every_renderer(
    datasets_dir: Path,
    add_dataset: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Check that validate-data finds the missing files of every renderer and the descriptor problems."""
    # a fresh scaffold refers to a mesh which is not there yet
    assert cli.main(["new-dataset", "scaffold"]) == 0
    add_dataset("xdmf", mesh_format="XDMF+HDF5")
    add_dataset("organs", render={"renderer": "patient_organs"})
    add_dataset("region", render={"renderer": "region_id"})
    add_dataset("fields", render={"renderer": "scalar_field", "mesh_file": "m.vtu"})
    region_grid().save(datasets_dir / "fields" / "m.vtu")
    add_dataset("twice")
    (datasets_dir / "copy").mkdir()
    (datasets_dir / "copy" / "twice.json").write_text(
        (datasets_dir / "twice" / "twice.json").read_text()
    )
    (datasets_dir / "twice" / "mesh.vtp").write_text("")
    (datasets_dir / "latin1").mkdir()
    (datasets_dir / "latin1" / "latin1.json").write_bytes(
        '{"name": "K\xf6nig"}'.encode("latin-1")
    )

    assert cli.main(["validate-data"]) == 1
    err = capsys.readouterr().err
    for problem in [
        "scaffold.json: mesh_file 'mesh.stl' not found",
        "xdmf.json: timeseries renderer found no XDMF file",
        "organs.json: patient_organs renderer found no patient_<n> folders",
        "region.json: region_id renderer needs render.mesh_file",
        "fields.json: scalar_field renderer needs render.fields",
        "dataset key 'twice' is already used by",
        "latin1.json: unreadable descriptor",
    ]:
        assert problem in err, problem
