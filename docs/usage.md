# Running the app

VisFEM runs as a local web server which the browser connects to; the `visfem` command starts it and prepares the datasets it shows.

## Launching

```bash
visfem
```

starts the web app and opens it in the browser. `visfem` without a command is the same as `visfem serve`, which accepts the options of the trame server:

```bash
visfem serve --server --port 9000     # no browser, fixed port
visfem serve --host 0.0.0.0           # listen on all interfaces of the machine
visfem serve --help                   # every option of the trame server
```

The server listens on `localhost` by default. A single `visfem serve` process is one session which every connected browser shares; a public instance runs behind the trame launcher, which starts one process per visitor, see [Deployment](deployment.md).

## Data directory

VisFEM shows the datasets of a data directory. It reads the `datasets/` folder inside the directory that `DATA_DIR` names:

```bash
export DATA_DIR=/path/to/your/data    # datasets are read from /path/to/your/data/datasets
visfem
```

Without `DATA_DIR`, a checkout of the repository uses its own `data/` folder and an installed VisFEM uses `./visfem_data` in the working directory, where the fetch commands of the [example data](example-data.md) put their datasets. How a dataset is laid out is described in [Datasets](datasets.md).

## Environment variables

| variable | effect |
| --- | --- |
| `DATA_DIR` | data directory, the datasets are read from its `datasets/` folder; `VISFEM_DATA_DIR` is an alias |
| `VISFEM_DATASETS` | comma separated allowlist of dataset keys, e.g. `heart,ircadb`; the other datasets stay hidden. Empty shows every dataset |
| `VISFEM_LOG_LEVEL` | level of the log output, e.g. `DEBUG` or `INFO`; the default is `WARNING` |
| `VISFEM_PRELOAD` | `1` loads every mesh into memory at startup, so the first selection of a dataset does not wait for the disk |

## Opening a dataset by link

The `model` query parameter, or its alias `dataset`, selects a dataset when the app opens, e.g. [app.visfem.de/?model=heart](https://app.visfem.de/?model=heart). The value is the key of the dataset, i.e., the file name of its JSON descriptor without `.json`. The tiles of the landing page link to the models this way.

## Command line

Besides `serve`, the `visfem` command documents, scaffolds and validates datasets and downloads the example data:

| command | purpose |
| --- | --- |
| `visfem renderers` | the built-in renderers and what each one draws |
| `visfem schema` | the fields of a dataset descriptor |
| `visfem example <renderer>` | a minimal valid descriptor for a renderer |
| `visfem new-dataset <name> --renderer <renderer>` | scaffold `datasets/<name>/` with a descriptor template |
| `visfem validate-data` | validate every descriptor and check that the files it references exist |
| `visfem fetch-ircadb` | download the 3D-IRCADb-01 dataset, see [Example data](example-data.md) |
| `visfem fetch-openknee` | download the Open Knee(s) geometries, see [Example data](example-data.md) |

`visfem <command> --help` lists the options of a command.
