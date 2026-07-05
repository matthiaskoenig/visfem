![visfem logo](docs/images/favicon/visfem-100x100.png)

# VisFEM: Web visualization of FEM models
[![GitHub Actions CI/CD Status](https://github.com/matthiaskoenig/visfem/workflows/CI-CD/badge.svg)](https://github.com/matthiaskoenig/visfem/actions/workflows/main.yml)
[![Version](https://img.shields.io/pypi/v/visfem.svg)](https://pypi.org/project/visfem/)
[![Python Versions](https://img.shields.io/pypi/pyversions/visfem.svg)](https://pypi.org/project/visfem/)
[![MIT License](https://img.shields.io/pypi/l/visfem.svg)](https://opensource.org/licenses/MIT)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19220183.svg)](https://doi.org/10.5281/zenodo.19220183)

VisFEM is an interactive web-based tool for visualization of Finite Element Method (FEM) simulation
results, with a focus on biomedical applications. Source code is available from
[https://github.com/matthiaskoenig/visfem](https://github.com/matthiaskoenig/visfem).


## Installation
`visfem` is available from [PyPI](https://pypi.python.org/pypi/visfem) and can be installed via

```bash
pip install visfem
```

## Run app
After installing, launch the app with:
```bash
visfem
```

## Adding your own dataset

A dataset is a folder of mesh files plus a JSON descriptor. VisFEM discovers
datasets from a data directory; point `DATA_DIR` at your own folder:

The CLI walks you through it:

```bash
export DATA_DIR=/path/to/your/data

visfem renderers                         # what each renderer draws, and when to use it
visfem schema                            # the JSON fields and what they mean
visfem example region_id                 # a ready-to-edit template for a renderer
visfem new-dataset my_model --renderer region_id   # scaffold a folder + JSON
# drop your mesh files into datasets/my_model/, edit the JSON, then:
visfem validate-data                     # check the JSON and that the files resolve
visfem                                   # launch; my_model now appears
```

### Try it with example data

To explore VisFEM with real, openly available data, download the public
[3D-IRCADb-01](https://www.ircad.fr/research/data-sets/liver-segmentation-3d-ircadb-01/)
dataset: CT-segmented organ surface meshes from 20 patients

```bash
export DATA_DIR=/path/to/your/data
visfem fetch-ircadb                      # download (~3 GB) and lay out the dataset
visfem                                   # launch; '3D-IRCADb-01' appears in the sidebar
```

The 3D-IRCADb-01 dataset is provided by IRCAD under its own license terms.


## How to cite
To cite the software repository

> Elias, M. & König, M. (2026).
> *VisFEM: Web visualization of FEM models.*
> Zenodo. [https://doi.org/10.5281/zenodo.19220183](https://doi.org/10.5281/zenodo.19220183)


## License

* Source Code: [MIT](https://opensource.org/license/MIT)
* Documentation: [CC BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/)
* Models: [CC BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/)

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.

## Funding
Matthias König is supported by the German Research Foundation (DFG) within the Research Unit Programme FOR 5151
"QuaLiPerF (Quantifying Liver Perfusion-Function Relationship in Complex Resection -
A Systems Medicine Approach)" by grant number 436883643 and by grant number
465194077 (Priority Programme SPP2311, Subproject SimLivA).

Matthias König was supported by the Federal Ministry of Education and Research (BMBF, Germany)
within the research network Systems Medicine of the Liver (LiSyM, grant number 031L0054).

Michelle Elias is supported by the German Research Foundation (DFG) under grant number 465194077
(Priority Programme SPP2311).

© 2026 Michelle Elias & Matthias König
