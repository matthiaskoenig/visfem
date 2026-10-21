![visfem logo](docs/images/favicon/visfem-100x100.png)

# VisFEM: Web visualization of FEM models
[![GitHub Actions CI/CD Status](https://github.com/matthiaskoenig/visfem/workflows/CI-CD/badge.svg)](https://github.com/matthiaskoenig/visfem/actions/workflows/main.yml)
[![Version](https://img.shields.io/pypi/v/visfem.svg)](https://pypi.org/project/visfem/)
[![Python Versions](https://img.shields.io/pypi/pyversions/visfem.svg)](https://pypi.org/project/visfem/)
[![MIT License](https://img.shields.io/pypi/l/visfem.svg)](https://opensource.org/licenses/MIT)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19220183.svg)](https://doi.org/10.5281/zenodo.19220183)

VisFEM is an interactive web app for visualizing Finite Element Method (FEM) simulation
results, with a focus on biomedical applications. The source code lives at
[https://github.com/matthiaskoenig/visfem](https://github.com/matthiaskoenig/visfem).


## Installation
Install `visfem` from [PyPI](https://pypi.python.org/pypi/visfem):

```bash
pip install visfem
```

## Usage
Launch the app with:
```bash
visfem
```

## Custom datasets

A dataset is a folder of mesh files plus a JSON descriptor. VisFEM discovers
datasets from a data directory; point `DATA_DIR` at your own folder.

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

### Example data

Download the public
[3D-IRCADb-01](https://www.ircad.fr/research/data-sets/liver-segmentation-3d-ircadb-01/)
dataset, CT-segmented organ surface meshes from 20 patients:

```bash
export DATA_DIR=/path/to/your/data
visfem fetch-ircadb                      # download (~3 GB) and lay out the dataset
visfem                                   # launch; '3D-IRCADb-01' appears in the sidebar
```

IRCAD provides the 3D-IRCADb-01 dataset under its own license terms.

[Open Knee(s)](https://simtk.org/projects/openknee) from the Cleveland Clinic is a second
open example. The command below fetches the segmented tissue surfaces of the eight
simulation-ready specimens (16 STL surfaces each) and the Generation 1 tibiofemoral
finite element model (FEBio, converted to VTU) from the project's public SVN repository,
which serves anonymous checkouts:

```bash
visfem fetch-openknee                    # all eight specimens + the Generation 1 model (~220 MB)
visfem fetch-openknee --specimens oks003 --no-gen1   # just one specimen
visfem                                   # launch; the knees appear under 'Musculoskeletal'
```

The Open Knee(s) Development Team provides Open Knee(s) under Creative Commons
terms (CC BY-SA 3.0 in the repository, CC BY 4.0 on the project page). Cite
Chokhandre et al. (2023), [doi:10.1007/s10439-022-03074-0](https://doi.org/10.1007/s10439-022-03074-0),
for the specimens and Erdemir (2016), [doi:10.1055/s-0035-1564600](https://doi.org/10.1055/s-0035-1564600),
for the Generation 1 model.


## Citation
Cite the software repository as:

> Elias, M. & König, M. (2026).
> *VisFEM: Web visualization of FEM models.*
> Zenodo. [https://doi.org/10.5281/zenodo.19220183](https://doi.org/10.5281/zenodo.19220183)


## License

* Source Code: [MIT](https://opensource.org/license/MIT)
* Documentation: [CC BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/)
* Models: [CC BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/)

The software ships as is; the MIT license in `LICENSE` disclaims all warranties,
including merchantability and fitness for a particular purpose.

## Funding
The German Research Foundation (DFG) supports Matthias König within the Research Unit Programme FOR 5151
"QuaLiPerF (Quantifying Liver Perfusion-Function Relationship in Complex Resection -
A Systems Medicine Approach)" by grant number 436883643 and by grant number
465194077 (Priority Programme SPP2311, Subproject SimLivA).

The Federal Ministry of Education and Research (BMBF, Germany) supported Matthias König
within the research network Systems Medicine of the Liver (LiSyM, grant number 031L0054).

The German Research Foundation (DFG) supports Michelle Elias under grant number 465194077
(Priority Programme SPP2311).

© 2026 Michelle Elias & Matthias König
