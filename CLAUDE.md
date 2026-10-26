# CLAUDE.md

This file provides guidance when working with code in this repository.

## Project

VisFEM is a trame web app for the visualization of Finite Element Method (FEM) models, with a focus on biomedical applications, plus a `visfem` command line (`visfem.cli:main`) which launches it and scaffolds, documents, validates and downloads datasets. Requires python >= 3.14 (no 3.15 yet, VTK publishes no wheels for it), packaged with hatchling (version is read from `src/visfem/__init__.py`). Runtime dependencies are trame 4 with its vuetify and vtk widgets, PyVista/VTK, meshio, h5py, numpy, pydantic and rich.

## Commands

```bash
# environment (uv based, versions pinned in uv.lock)
uv sync --extra dev
uv run pre-commit install

# app
DATA_DIR=/path/to/data visfem             # launch, datasets are read from $DATA_DIR/datasets
visfem serve --server --port 9000         # no browser, fixed port
visfem validate-data                      # validate every descriptor of the data directory

# tests
pytest                                    # all tests
tox r -e py3.14                           # single tox env
tox run-parallel                          # full matrix + ty

# lint / format / types
ruff check
ruff format
tox -e ty                       # ty type check (config in [tool.ty] in pyproject.toml)
uvx ty check                    # same check, straight from the working tree

# deployment requirements, after every dependency change
uv export --frozen --no-dev --no-editable --no-emit-project -o setup/requirements.txt
```

`develop` is the default branch and takes every change through a pull request; direct pushes are rejected by the rulesets in `.github/rulesets/` (applied with `.github/rulesets/apply.sh`), which require the `tests`, `ruff`, `ty` and `docs` checks. `main` only tracks the latest release and is fast-forwarded by the `sync-main` job of the release workflow, never by hand.

Release steps are in `docs/development.md`: the release is prepared on a branch, `uvx bump-my-version bump [major|minor|patch]` updates `src/visfem/__init__.py` and `CITATION.cff` and commits without tagging (`tag = false`, a squash merge would rewrite the commit), and the tag is created on `develop` after the pull request was merged, which triggers the PyPI release in `ci-cd.yml` (build without permissions, publish with only `id-token`, then the GitHub release and `sync-main`). All actions are pinned to commit SHAs; dependabot updates them.

Documentation is [Zensical](https://zensical.org/): markdown sources in `docs/`, configured in `zensical.toml`, built into the gitignored `site/docs/` (`uv run zensical build --clean`, `uv run zensical serve` for the preview). The API reference is rendered from the docstrings by mkdocstrings; a page in `docs/api/` is just `::: visfem.<module>`, so nothing is generated into the repository. `scripts/llms_txt.py` runs after the build and writes the agent facing files (`llms.txt`, `llms-full.txt` and the markdown of every page) into `site/docs/`. The `documentation` workflow then copies the interim landing page `deploy/pages/` into `site/` and publishes the whole site from `develop` to GitHub Pages: the landing page at `https://visfem.de/`, the documentation at `https://visfem.de/docs/`. `deploy/landing/` is the different landing page of the server deployment (`docs/deployment.md`).

## Architecture

**`app.py` - the application.** `VisfemApp` (a `TrameApp`) owns one off-screen PyVista plotter wrapped in an `engine.scene.Scene`, the trame state and the callbacks of the UI. `@change` handlers react to state changes from the client; `_claim_busy` serializes the long running actions and shows their failures. The `?model=<key>` URL parameter arrives as `url_model` and selects a dataset once. A single `visfem serve` process is one session shared by every connected browser; the public deployment runs the trame launcher, which starts one process per visitor (`setup/launcher.json`).

**Datasets.** `engine/discovery.py` finds the descriptors: every `*.json` below `$DATA_DIR/datasets` (or `<repo>/data/datasets` in a checkout) except the `*.meta.json` caches, keyed by file stem, filtered by the `VISFEM_DATASETS` allowlist. `models.py` holds the strict pydantic models (unknown fields are rejected): `ProjectMetadata` is the descriptor, `RenderConfig` its optional `render` block, `MeshMetadata` the cached mesh metadata.

**Renderers.** `engine/renderers.py` maps every `RendererName` to a render function in `RENDERER_REGISTRY`; `resolve_render_config` infers the omitted fields (renderer, mesh file) from `mesh_format` and the files of the dataset folder. `engine/selection.py` handles the selections of the UI (dataset, patient, field, step, palette) and dispatches through the registry; `engine/scene.py` builds the actors and lookup tables and pushes the scene to vtk.js (`push_scene`, the delta and full state publishing is in `ui/layout.py`).

**Meshes.** `mesh.py` loads everything meshio and PyVista read, XDMF+HDF5 time series, PVD manifests, flat VTK series and LS-DYNA d3plot databases, and caches the loaded meshes in process wide dicts for the life of the process. Mesh metadata is cached next to the mesh as a `.meta.json` sidecar. `febio.py` reads the geometry of FEBio 2.x models (used by `visfem fetch-openknee`).

**UI.** `ui/` builds the page from trame vuetify widgets: `layout.py` assembles toolbar, left panel (dataset tree, dataset info), the vtk view and the right panel (view, fibres, scalar field, colour, regions, playback, scalar bar). `ui/theme.py` holds the design tokens; `engine/xr_manager.py` the WebXR session handling.

`log.py` attaches one `RichHandler` to the `visfem` logger, level from `VISFEM_LOG_LEVEL` (default `WARNING`); modules get their logger with `log.get_logger(__name__)`. Log calls use lazy `%s` formatting rather than f-strings (enforced by ruff `G`).

## Conventions

- Type checking is done with [ty](https://docs.astral.sh/ty/) (mypy was removed). `[tool.ty.terminal] error-on-warning = true` means warnings fail the check, so the tree must stay at zero diagnostics; the checked python version is inferred from `project.requires-python`. Suppress a diagnostic with a rule-specific `# ty: ignore[rule-name]`, never a blanket `# type: ignore`. The PyVista `Plotter` methods built with `functools.wraps` are typed as unbound; call the typed `plotter.renderer`/`plotter.renderers` methods instead. ty also runs as a pre-commit hook (`--extra dev`).
- Every module, class and function carries full type annotations and a docstring (ruff `D`, google convention). Every `except Exception` carries a `noqa: BLE001` with its reason. The UI is built from nested `with` blocks on purpose (`SIM117` is ignored).
- Text from descriptors and file names reaches the Vue templates; pass it through state bindings or `json.dumps`, never format it into a template string or JS expression.
- `setup/requirements.txt` is generated from `uv.lock` by `uv export`, never edit it by hand.
- Datasets are not part of the repository (`data/` is gitignored); the tests do not need them, `tests/conftest.py` writes synthetic meshes and descriptors into a temporary data directory. `tests/test_app.py` drives `VisfemApp` without a browser on an off-screen plotter; the module-level caches of `mesh.py` are keyed by path, so every test uses its own `tmp_path`. A warning fails a test.
- The series metadata of the app (`xdmf_meta`) is keyed by the path of the XDMF or PVD file, never by its stem.
- Markdown carries no hard line wraps: a paragraph, a list item or a table row is a single line and the wrapping is left to the editor.
- Release notes go in `release-notes/` as part of a release commit.
