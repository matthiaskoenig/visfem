# Install the visfem package itself into the build venv (deps come from requirements.txt).
# Runs inside the activated venv created by create_venv.sh; uv targets the active venv.

# Install the pinned dependency set first (trame, wslink, pyvista, ...). Without
# this the venv had only the visfem package and crash-looped on `import wslink`.
uv pip install -r /deploy/setup/requirements.txt

# Then the visfem package itself, without re-resolving deps (already pinned above).
uv pip install --no-deps /deploy
