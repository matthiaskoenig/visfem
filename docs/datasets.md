# Datasets

A dataset is a folder of mesh files plus a JSON descriptor. The descriptor carries the scientific context which the app shows next to the model, and optionally a `render` block which says how to draw the meshes.

## Layout

The datasets live in the `datasets/` folder of the data directory, see [Data directory](usage.md#data-directory). Every JSON file below `datasets/` is a descriptor, except the `*.meta.json` files, which are caches of the mesh metadata written by the app. The file name without `.json` is the key of the dataset, e.g. in the `?model=` link; it has to be unique.

```text
$DATA_DIR/
  datasets/
    my_model/
      my_model.json      # the descriptor, key "my_model"
      mesh.vtu           # the meshes the descriptor refers to
```

`data_path` is the folder holding the meshes, relative to `datasets/`. For a PVD dataset (`mesh_format` is `PVD`) it is the `.pvd` file itself. It must stay inside `datasets/`: absolute paths and `..` are rejected.

The quickest start is the scaffold of the command line:

```bash
export DATA_DIR=/path/to/your/data
visfem new-dataset my_model --renderer region_id   # datasets/my_model/my_model.json
# copy the mesh files into datasets/my_model/ and edit the JSON
visfem validate-data                               # check the JSON and the referenced files
visfem                                             # my_model now appears
```

## Descriptor fields

| field | required | content |
| --- | --- | --- |
| `data_path` | yes | folder under `datasets/` holding the meshes, usually the key; the `.pvd` file for a PVD dataset |
| `name` | yes | display name |
| `pi` | yes | principal investigator |
| `institution` | yes | list of institutions |
| `biological_scale` | yes | one of `subcellular`, `cell`, `tissue`, `organ`, `organ_system` |
| `organ_system` | yes | list of `abdominal`, `bone`, `heart`, `kidney`, `liver`, `lung`, `musculoskeletal`, `torso`, `vasculature`; the dataset is listed under every one of them |
| `description` | yes | short description, at most 500 characters |
| `mesh_format` | yes | display label of the format, e.g. `VTK`, `VTU`, `STL`, `XDMF+HDF5`, `PVD` |
| `references` | no | list of DOIs, URLs or citations |
| `spp_project` | no | title of the SPP2311 project the dataset belongs to |
| `spp_badge` | no | `true` shows the SPP2311 badge even without `spp_project` |
| `subgroup` | no | label of a sub group within the organ system, e.g. `Vessel` |
| `sort_order` | no | position within the organ system or sub group; without it the datasets are sorted by name |
| `labels_file` | no | `LabelIDs.txt` file with the names of the regions per mesh, next to the meshes |
| `render` | no | how to draw the dataset, see [Renderers](renderers.md); omitted fields are inferred |

Unknown fields are rejected, so a typo does not go unnoticed. `visfem schema` prints the same reference on the command line.

## Example

A region coloured mesh, as printed by `visfem example region_id`:

```json
{
  "data_path": "my_dataset",
  "name": "My Dataset",
  "pi": "Your Name",
  "institution": ["Your Lab"],
  "biological_scale": "organ",
  "organ_system": ["bone"],
  "description": "Short description of the model.",
  "mesh_format": "VTK",
  "references": [],
  "render": {
    "renderer": "region_id",
    "mesh_file": "mesh.vtk",
    "region_array": "PartId",
    "categorical_palette": "clinical",
    "region_labels": {
      "1": ["Region one"],
      "2": ["Region two"]
    }
  }
}
```

## Validation

```bash
visfem validate-data
```

validates every descriptor of the data directory against the schema and checks that the files it refers to exist. The app applies the same validation on startup: an invalid descriptor is skipped with a warning in the log, the other datasets load as usual.
