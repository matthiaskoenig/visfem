# Release information

## make release
* update release notes in `release-notes` and `date-released` in `CITATION.cff` with commit
* make sure all tests run (`tox -p`)
* check formating and linting (`ruff check`)
* test bump version (`uvx bump-my-version bump [major|minor|patch] --dry-run -vv`)
* bump version (`uvx bump-my-version bump [major|minor|patch]`)
* `git push --tags` (triggers release)
* `git push`
* test installation in virtualenv from pypi
```bash
uv venv --python 3.14
uv pip install visfem
```

# Install dev dependencies:
```bash
# install core dependencies
uv sync
# install dev dependencies
uv pip install -r pyproject.toml --extra dev
uv tool install tox --with tox-uv
```

## Testing with tox
Run single tox target
```bash
tox r -e py314
```
Run all tests in parallel
```bash
tox run-parallel
```
Continuous integration runs `py3.14` on linux, macos and windows, `py3.13` on linux, and `mypy`; the complete `envlist` runs locally with `tox run-parallel` before a pull request is opened.

# Setup pre-commit
```bash
uv pip install pre-commit
uv run pre-commit install
uv run pre-commit run
```
