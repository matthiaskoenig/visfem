# Installation

VisFEM requires python >= 3.14 and is available from [pypi](https://pypi.org/project/visfem/). It is an application, so it is best installed as a tool into an environment of its own.

## With uv

[uv](https://docs.astral.sh/uv/) is the recommended way to install VisFEM. As a tool, it gets an isolated environment and the `visfem` command is put on the `PATH`:

```bash
uv tool install visfem
visfem --help
```

`uvx visfem` runs it without installing it permanently.

## With pip

```bash
python -m venv .venv
source .venv/bin/activate        # Linux and macOS
.venv\Scripts\activate           # Windows
pip install visfem
```

## Development version

The current state of the `develop` branch is installed directly from GitHub:

```bash
uv tool install "visfem @ git+https://github.com/matthiaskoenig/visfem.git@develop"
```

or, with pip,

```bash
pip install git+https://github.com/matthiaskoenig/visfem.git@develop
```

To work on the repository itself, with the test and documentation tooling, see [Contributing](development.md).

## Dependencies

The app is built with [trame](https://kitware.github.io/trame/) and its [vuetify](https://github.com/Kitware/trame-vuetify) and [vtk](https://github.com/Kitware/trame-vtk) widgets. The meshes are read with [PyVista](https://pyvista.org/), [VTK](https://vtk.org/), [meshio](https://github.com/nschloe/meshio) and [h5py](https://www.h5py.org/), the dataset descriptors are validated with [pydantic](https://docs.pydantic.dev/). All of them ship wheels for Linux, macOS and Windows, so no compiler is needed.

The server renders off screen. On a headless Linux machine, e.g., in a container, VTK needs an OpenGL implementation such as OSMesa or EGL, see the [Dockerfile](https://github.com/matthiaskoenig/visfem/blob/develop/Dockerfile) of the deployment.
