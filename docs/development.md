# Development

Contributions are welcome. The repository is [matthiaskoenig/visfem](https://github.com/matthiaskoenig/visfem); development happens against the `develop` branch via pull requests.

## Branch model

Two branches are permanent:

- **`develop`** is the default branch and the branch everything is integrated into. The documentation on [visfem.de/docs](https://visfem.de/docs/) is published from it.
- **`main`** tracks the latest published release. It is fast-forwarded to the released commit by the `sync-main` job of the `CI-CD` workflow after the package went to pypi, so `main` and the newest version on pypi always agree. Nothing is developed on `main` and nothing is merged into it by hand.

Work happens on short lived branches off `develop`, which GitHub deletes after the merge. Releases are tagged on `develop`, see [Release](#release).

## Pull requests

Neither branch accepts a direct push, every change goes through a pull request against `develop`. This includes the maintainer, there is no bypass.

A pull request can only be merged once the four required checks are green:

| check   | workflow      | content                                                              |
| ------- | ------------- | -------------------------------------------------------------------- |
| `tests` | `ci-cd.yml`   | python 3.13 and 3.14 on linux, python 3.14 on macos and windows       |
| `ruff`  | `ruff.yml`    | `ruff check` and `ruff format --check`                                |
| `ty`    | `ty.yml`      | `tox r -e ty`                                                         |
| `docs`  | `docs.yml`    | the zensical build including the api reference, the agent files and the landing page |

`tests` aggregates the test matrix into a single job, so the name of the required check stays the same when the matrix changes.

Further rules of a pull request:

- conversations have to be resolved before the merge
- an approval is dismissed when new commits are pushed
- the history stays linear, i.e., a pull request is merged with squash or rebase; merge commits are disabled
- the maintainer is the code owner of the repository (`.github/CODEOWNERS`) and is requested for review on every pull request. Write access is limited to the two authors of VisFEM; a pull request of another contributor is reviewed and merged by one of them. The rulesets themselves do not require an approval, since requiring one would block an author whose co-author is not available, who cannot approve their own pull request

[Auto-merge](https://docs.github.com/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/automatically-merging-a-pull-request) is enabled for the repository, so a pull request can be queued and is merged as soon as the checks pass and the required approval is there.

### Repository policies { #repository-policies }

The protection is implemented with [repository rulesets](https://docs.github.com/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets). They are part of the repository in `.github/rulesets/` instead of only living in the web interface, so a change to a policy is reviewed like any other change:

| ruleset                 | applies to | rules                                                                                                                                       |
| ----------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `develop.json`          | `develop`  | pull request required, the four checks above, resolved conversations, linear history, no force push, no deletion. **No bypass, for anybody.** |
| `main.json`             | `main`     | linear history, no force push, no deletion, no bypass. The fast-forward of the release workflow needs none, only a force push or a merge commit would be rejected |
| `tags.json`             | all tags   | a tag cannot be deleted or moved, so a release tag keeps pointing at what was released                                                       |

Changing a policy means changing the json and applying it:

```bash
.github/rulesets/apply.sh
```

The script is idempotent: it updates the rulesets which exist and creates the missing ones. It also sets the merge settings of the repository, i.e., auto-merge, delete branch on merge, and squash and rebase as the only merge methods. It needs the [github cli](https://cli.github.com) authenticated as a user with admin permission on the repository.

## Setup development environment

Development needs [uv](https://docs.astral.sh/uv/) and a checkout of the repository:

```bash
git clone https://github.com/matthiaskoenig/visfem.git
cd visfem
```

A single sync creates the virtual environment in `.venv`, installs `visfem` into it in editable mode and adds the complete tooling:

```bash
uv sync --extra dev
```

The `dev` extra contains everything used below, i.e., pytest, ruff, ty, tox, pre-commit, zensical and bump-my-version, so nothing has to be installed separately. `uv.lock` pins the versions of the environment, `uv lock --upgrade` updates them. The python version is taken from `.python-version` (currently 3.14); to work against the oldest supported version instead use `uv sync --extra dev --python 3.13`, which replaces the environment.

The tools are then run either with `uv run <command>`, which uses the environment without activating it, or from the activated environment:

```bash
source .venv/bin/activate        # Linux and macOS
.venv\Scripts\activate           # Windows
```

The commands in this document are written without the `uv run` prefix; prepend it if the environment is not activated.

The last step installs the git hook:

```bash
uv run pre-commit install          # install the hook, once per checkout
uv run pre-commit run --all-files  # check the current state of the repository
```

From now on every commit is checked with ruff (lint and format) and ty, i.e., the same checks that run in continuous integration. On a commit only the changed files are looked at, `--all-files` checks the whole repository and is what a newly added hook should be tried with.

## Testing

The tests are written with pytest, tox runs them against every supported python version.

The tox environments are named after the interpreter (`py3.13` and `py3.14`, see `envlist` in `tox.ini`), a single one is run with
```bash
tox r -e py3.14
```
and the complete matrix, including the `ty` environment, in parallel with
```bash
tox run-parallel
```

This needs the interpreters to be available, which uv installs with `uv python install 3.13 3.14`. Continuous integration runs the same environments as `uvx --with tox-uv tox -e py3.14`. Python 3.15 joins the matrix once [VTK](https://pypi.org/project/vtk/) publishes wheels for it.

To run the tests directly against the development environment use

```bash
pytest                                    # the full suite
pytest tests/test_main.py                 # a single module
```

The tests do not need datasets. To check a change in the app itself, run it against a data directory, see [Running the app](usage.md), and look at the result in the browser.

## Linting and formatting

Linting and formatting use [ruff](https://docs.astral.sh/ruff/):

```bash
ruff check     # lint
ruff format    # format
```

Logging calls use lazy `%s` formatting instead of f-strings (ruff `G`), every `except Exception` carries a `noqa` with its reason (ruff `BLE`).

## Type checking

Type checking is performed with [ty](https://docs.astral.sh/ty/):

```bash
tox r -e ty
```
Or directly in the working tree:
```bash
uvx ty check
```

The configuration lives in `[tool.ty]` in `pyproject.toml`. Warnings are treated as errors, so the codebase is kept free of diagnostics. Suppress an unavoidable diagnostic with a rule specific `# ty: ignore[rule-name]` rather than a blanket comment.

## Documentation

The documentation is built with [Zensical](https://zensical.org/), the static site generator of the Material for MkDocs authors. The sources are markdown files in `docs/`, the site is configured in `zensical.toml` in the repository root. Nothing rendered is committed: the site is built by the `documentation` workflow on every push and published to [visfem.de/docs](https://visfem.de/docs/) from the `develop` branch.

The GitHub Pages site holds two parts: the interim landing page of `deploy/pages/` at [visfem.de](https://visfem.de/) and the documentation below `/docs/`. zensical therefore builds into `site/docs/` (`site_dir` in `zensical.toml`), and the workflow copies the landing page into `site/`. The landing page of the server deployment lives in `deploy/landing/`, see [Deployment](deployment.md). The Pages site of the repository is deployed by GitHub Actions (source `GitHub Actions` in the Pages settings) and carries the custom domain `visfem.de`.

Build the documentation into `site/docs/`:

```bash
uv run zensical build --clean
```

For writing, the preview rebuilds on save:

```bash
uv run zensical serve
```

The API reference is rendered from the docstrings by [mkdocstrings](https://mkdocstrings.github.io/); a page in `docs/api/` only contains the module directive:

```markdown
# mesh

::: visfem.mesh
```

Docstrings are therefore the place to document functions and classes, the markdown files provide the narrative around them. Adding a module to the reference means adding such a page and an entry to `nav` in `zensical.toml`.

### Files for agents { #files-for-agents }

Agents and language models read markdown, not rendered html. `scripts/llms_txt.py` writes the files of the [llms.txt convention](https://llmstxt.org/) into the built site, i.e., [llms.txt](https://visfem.de/docs/llms.txt) as an annotated index of all pages, [llms-full.txt](https://visfem.de/docs/llms-full.txt) with the complete documentation in a single file, and the markdown of every page next to its html (`/docs/usage.md` for `/docs/usage/`). The markdown of the API reference is generated from the docstrings with `inspect`, since the pages themselves only contain the mkdocstrings directive.

```bash
uv run zensical build --clean
uv run python scripts/llms_txt.py
cp -r deploy/pages/. site/        # the landing page, for a preview of the complete site
```

The `documentation` workflow runs both steps, so the files are regenerated with every push. `deploy/pages/robots.txt` at the root of the site points crawlers at the sitemap and at these files.

## Deployment requirements

The container of the [deployment](deployment.md) installs the app from `setup/requirements.txt`, which is exported from `uv.lock`. Regenerate it whenever the dependencies change, never edit it by hand:

```bash
uv export --frozen --no-dev --no-editable --no-emit-project -o setup/requirements.txt
```

## Release

A release is made from `develop`. Since `develop` only accepts pull requests, the release is prepared on a branch and tagged once that pull request is merged:

1. branch off `develop`: `git switch -c release/x.y.z develop`
2. write the release notes for the version in `release-notes/x.y.z.md`
3. make sure everything passes: `tox run-parallel`, `ruff check`, `tox r -e ty`, and that `setup/requirements.txt` is up to date with `uv.lock`
4. check the version bump: `uvx bump-my-version bump [major|minor|patch] --dry-run -vv`
5. bump the version: `uvx bump-my-version bump [major|minor|patch]`, which updates `src/visfem/__init__.py` and `CITATION.cff` and commits; set `date-released` in `CITATION.cff` in the same pull request. It does not create the tag; a squash or rebase merge would rewrite the commit and leave the tag behind on a commit which is not part of `develop`
6. push the branch, open the pull request against `develop` and merge it once the checks are green
7. tag the merged commit on `develop` and push the tag:

    ```bash
    git switch develop
    git pull
    git tag x.y.z
    git push origin x.y.z
    ```

    This starts the `CI-CD` workflow, which runs the test matrix, publishes to [pypi](https://pypi.org/project/visfem/), creates the GitHub release from `release-notes/x.y.z.md` and fast-forwards `main` to the tagged commit. Check the version before pushing, a tag cannot be moved or deleted afterwards.

8. test the installation from pypi in a fresh environment:

    ```bash
    uv venv --python 3.14
    uv pip install visfem
    ```

9. check that Zenodo has archived the release. `CITATION.cff`, the `README.md` and the `How to cite` section of `docs/index.md` carry the concept DOI, which always resolves to the latest version, and stay as they are
