![visfem logo](https://github.com/matthiaskoenig/visfem/raw/develop/docs/images/favicon/visfem-100x100.png)

# VisFEM: Web visualization of FEM models

[![GitHub Actions CI/CD Status](https://github.com/matthiaskoenig/visfem/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/matthiaskoenig/visfem/actions/workflows/ci-cd.yml)
[![Documentation](https://img.shields.io/badge/docs-visfem-009688.svg)](https://visfem.de/docs/)
[![Version](https://img.shields.io/pypi/v/visfem.svg)](https://pypi.org/project/visfem/)
[![Python Versions](https://img.shields.io/pypi/pyversions/visfem.svg)](https://pypi.org/project/visfem/)
[![MIT License](https://img.shields.io/pypi/l/visfem.svg)](https://opensource.org/licenses/MIT)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19220183.svg)](https://doi.org/10.5281/zenodo.19220183)

VisFEM is an interactive web app for visualizing Finite Element Method (FEM) simulation results, with a focus on biomedical applications. It is built on [trame](https://kitware.github.io/trame/), [PyVista](https://pyvista.org/) and [VTK](https://vtk.org/). The public instance runs at [app.visfem.de](https://app.visfem.de).

```bash
pip install visfem
visfem
```

The documentation is at **[visfem.de/docs](https://visfem.de/docs/)**:

- [Installation](https://visfem.de/docs/installation/)
- [Running the app](https://visfem.de/docs/usage/) and the command line
- [Datasets](https://visfem.de/docs/datasets/), [renderers](https://visfem.de/docs/renderers/) and [example data](https://visfem.de/docs/example-data/)
- [Deployment](https://visfem.de/docs/deployment/)
- [API reference](https://visfem.de/docs/api/)
- [Contributing](https://visfem.de/docs/development/)

The release notes are in [`release-notes/`](./release-notes).

## For agents

The documentation is published as markdown as well, following the [llms.txt convention](https://llmstxt.org/): [llms.txt](https://visfem.de/docs/llms.txt) is an annotated index of every page, [llms-full.txt](https://visfem.de/docs/llms-full.txt) the complete documentation in a single file, and the markdown of every page sits next to its html.

## How to cite

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19220183.svg)](https://doi.org/10.5281/zenodo.19220183)

If you use VisFEM please cite the archived software on Zenodo, see [`CITATION.cff`](./CITATION.cff):

> Elias, M. & König, M. (2026). *VisFEM: Web visualization of FEM models.* Zenodo. [https://doi.org/10.5281/zenodo.19220183](https://doi.org/10.5281/zenodo.19220183)

## License

- Source code: [MIT](https://opensource.org/license/MIT)
- Documentation: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

The example datasets keep the licenses of their providers, see [Example data](https://visfem.de/docs/example-data/).

## Funding

The German Research Foundation (DFG) supports Matthias König within the Research Unit Programme FOR 5151 "QuaLiPerF (Quantifying Liver Perfusion-Function Relationship in Complex Resection - A Systems Medicine Approach)" by grant number 436883643 and by grant number 465194077 (Priority Programme SPP2311, Subproject SimLivA).

The Federal Ministry of Education and Research (BMBF, Germany) supported Matthias König within the research network Systems Medicine of the Liver (LiSyM, grant number 031L0054).

The German Research Foundation (DFG) supports Michelle Elias under grant number 465194077 (Priority Programme SPP2311).

© 2026 Michelle Elias & Matthias König
