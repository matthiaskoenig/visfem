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

The server listens on `localhost` by default, unless `--host` or the `TRAME_DEFAULT_HOST` environment variable names another interface; the `0.0.0.0` which `visfem serve --help` gives as the default of `--host` is not what the server uses. A single `visfem serve` process is one session which every connected browser shares; a public instance runs behind the trame launcher, which starts one process per visitor, see [Deployment](deployment.md).

## Port

The server listens on port 8080 by default. `--port`, or its short form `-p`, starts it on another port, with or without the `serve` command:

```bash
visfem --port 9000                    # the app at http://localhost:9000/
visfem serve --server -p 9000         # the same without opening a browser
visfem --port 0                       # any free port, the address is printed at startup
```

The `TRAME_ARGS` environment variable sets the options as well, e.g. `TRAME_ARGS="--port 9000 --server" visfem`; when it is set, the options of the command line are ignored.

Every running `visfem` needs a port of its own. If the port is taken, e.g. by a second `visfem` on the default port, the start fails with `address already in use`; start it on another port or stop the process which holds the port.

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
| `VISFEM_MESH_CACHE_MB` | memory in MB for the loaded meshes, the time steps of a series included; the default is `2048`. Beyond it the least recently used meshes are dropped and read from disk again when they are shown. A series plays from memory while its keyframes fit, `0` caches only the mesh on display |
| `VISFEM_PRELOAD` | `1` loads every mesh into memory at startup, so the first selection of a dataset does not wait for the disk; the meshes beyond `VISFEM_MESH_CACHE_MB` are dropped again |
| `VISFEM_SHOW_ERRORS` | `1` appends the text of the exception to the error messages of the app, e.g. the path of a file which could not be read. Unset, the messages only name what failed and the details go to the log; the public deployment leaves it unset |

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
