# Example data

Two public datasets are downloaded and laid out by the command line, so VisFEM can be tried without data of your own. Both commands write into the data directory, i.e., `--data-dir`, else `DATA_DIR`, else the default of the app (`data/` of a source checkout, else `./visfem_data`), and print the `DATA_DIR` to launch the app with.

## 3D-IRCADb-01

The [3D-IRCADb-01](https://www.ircad.fr/research/data-sets/liver-segmentation-3d-ircadb-01/) dataset of IRCAD contains the CT segmented organ surface meshes of 20 patients (10 women, 10 men), hepatic tumours in 75% of the cases, covering up to 47 organ types per patient.

```bash
export DATA_DIR=/path/to/your/data
visfem fetch-ircadb                      # download (~820 MB) and lay out the dataset
visfem                                   # '3D-IRCADb-01' appears in the sidebar
```

`--keep-archive` keeps the downloaded archive below `<data-dir>/downloads/`.

Before anything is extracted, the meshes and licenses in the archive are checked against the SHA-256 checksum of those VisFEM was tested with; the archive itself is zipped anew for every download and differs in its timestamps. An archive with other content, e.g. a corrupted download or a new release of IRCAD, is not extracted; it is kept below `<data-dir>/downloads/` and both checksums are printed.

IRCAD provides the 3D-IRCADb-01 dataset under its own license terms.

## Open Knee(s)

[Open Knee(s)](https://simtk.org/projects/openknee) of the Cleveland Clinic provides the segmented tissue surfaces of eight simulation ready specimens (16 STL surfaces each) and the Generation 1 tibiofemoral finite element model. The command fetches them from the public SVN repository of the project, which serves anonymous checkouts, and converts the FEBio model to VTU:

```bash
visfem fetch-openknee                                  # all eight specimens and the Generation 1 model (~220 MB)
visfem fetch-openknee --specimens oks003 --no-gen1     # a single specimen
visfem                                                 # the knees appear under 'Musculoskeletal'
```

The Open Knee(s) Development Team provides Open Knee(s) under Creative Commons terms (CC BY-SA 3.0 in the repository, CC BY 4.0 on the project page). Cite Chokhandre et al. (2023), [doi:10.1007/s10439-022-03074-0](https://doi.org/10.1007/s10439-022-03074-0), for the specimens and Erdemir (2016), [doi:10.1055/s-0035-1564600](https://doi.org/10.1055/s-0035-1564600), for the Generation 1 model.
