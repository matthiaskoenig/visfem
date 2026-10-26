# Renderers

The `render` block of a descriptor selects one of the built-in renderers and configures it. The whole block is optional: without it, the renderer is inferred from `mesh_format` and the files of the dataset, which covers a single surface mesh and an XDMF or PVD time series. `visfem example <renderer>` prints a ready to edit descriptor for every renderer.

## Built-in renderers

| renderer | draws |
| --- | --- |
| `surface` | one solid coloured mesh (STL, VTU, OBJ), the default for a single static surface |
| `multi_part` | several named part files merged and coloured together, e.g. arteries and veins |
| `region_id` | one mesh coloured by an integer cell array (regions or materials), with optional fibre glyphs |
| `scalar_field` | a static mesh coloured by a selectable scalar field, as a continuous ramp and/or as categorical zones |
| `timeseries` | a scalar field animated over time, from XDMF, PVD, a flat VTK series or an LS-DYNA d3plot |
| `pvd_phase_series` | region coloured phase surfaces per patient, driven by a `.pvd` manifest |
| `patient_organs` | per patient folders of per organ `.vtk` meshes, the 3D-IRCADb-01 layout |

## Inference

When `renderer` is not set, it is inferred in this order:

1. `series` or `database` is set: `timeseries`
2. `mesh_format` is `PVD`, contains `XDMF`, or the folder holds XDMF files: `timeseries`
3. the folder holds `patient_<n>` folders: `pvd_phase_series` when a patient has a phase `.pvd`, `patient_organs` when a patient has several `.vtk` meshes
4. otherwise: `surface`, with `mesh_file` set to the only surface mesh of the folder

## Fields of the render block

| field | renderers | content |
| --- | --- | --- |
| `renderer` | all | one of the renderers above |
| `mesh_file` | `surface`, `region_id`, `scalar_field` | mesh file relative to the dataset folder; required by `region_id` and `scalar_field` |
| `mesh_candidates` | `surface` | fallbacks tried in order, e.g. an `.stl` before an `.obj` |
| `parts` | `multi_part` | list of `{"stem": ..., "label": ...}`, the stem is the path without extension relative to the dataset folder |
| `part_extensions` | `multi_part` | extensions tried for every stem, default `.ply`, `.vtk`, `.vtu`, `.stl`, `.obj` |
| `tube` | `multi_part` | `{"enabled": true, "n_sides": 8, "stride": 1}` draws line cells as tubes |
| `categorical_palette` | all | `clinical`, `paired` (default), `tableau`, `wong` or `tol_bright` |
| `continuous_cmap` | scalar fields | `viridis` (default), `plasma`, `cividis`, `inferno` or `turbo` |
| `region_array` | `region_id` | integer cell array with the region ids, e.g. `Material` or `PartId` |
| `region_labels` | region coloured | names per region id, e.g. `{"1": ["Ventricles"]}`; overrides `labels_file` |
| `labels_mesh_key` | region coloured | the mesh section of `labels_file` to use, e.g. `M.vtu` |
| `fiber` | `region_id` | `{"array": "Fiber", "stride": 5, "scale": 1.5}` draws glyphs oriented by a vector cell array |
| `fields` | `scalar_field`, `timeseries` | ordered list of `{"name": ..., "label": ...}`, the selectable fields; required by `scalar_field`, a time series without it offers every field of its mesh |
| `exclude_fields` | `timeseries` | discovered fields to drop |
| `default_field` | `scalar_field`, `timeseries` | field shown first; without it the first listed or discovered field |
| `categorical_fields` | `scalar_field` | fields drawn as discrete zones with a region legend |
| `percentile_clamp` | `scalar_field` | upper percentile the continuous ramp is clamped to, 1 to 100, default 95 |
| `series` | `timeseries` | glob of the per step mesh files relative to the dataset folder, natural sorted, e.g. `frame_*.vtk` |
| `database` | `timeseries` | `"d3plot"`: the dataset folder is an LS-DYNA d3plot database, named by its master file `d3plot` |
| `solid` | `pvd_phase_series` | `true` draws every phase in one colour |

The names of the palettes and colormaps are checked when the descriptor is read, so an unknown name fails `visfem validate-data`.
