# API reference

The API reference is generated from the docstrings of the package. VisFEM is an application: the reference documents its internals for development, not a stable library interface.

## Application

| module | description |
| --- | --- |
| [app](app.md) | the trame application, its state and the callbacks of the UI |
| [cli](cli.md) | the `visfem` command line |
| [models](models.md) | the pydantic models of the dataset descriptors and the mesh metadata |
| [mesh](mesh.md) | loading of meshes and time series, metadata extraction and caching |
| [febio](febio.md) | reader of the geometry of FEBio 2.x models |
| [log](log.md) | logging of the app |

## visfem.engine

| module | description |
| --- | --- |
| [discovery](engine/discovery.md) | discovery of the datasets of the data directory |
| [renderers](engine/renderers.md) | the renderer registry and the resolution of the `render` block |
| [scene](engine/scene.md) | the plotter, its actors and the scalar bar |
| [selection](engine/selection.md) | handlers of the dataset selection |
| [playback](engine/playback.md) | autoplay of time series and the vtk.js warmup |
| [xr_manager](engine/xr_manager.md) | WebXR sessions |
| [colors](engine/colors.md) | colour utilities and the background colours |
| [palettes](engine/palettes.md) | categorical palettes and continuous colormaps |

## visfem.ui

| module | description |
| --- | --- |
| [layout](ui/layout.md) | assembly of the page |
| [toolbar](ui/toolbar.md) | the toolbar |
| [left_panel](ui/left_panel.md) | dataset tree and dataset info |
| [right_panel](ui/right_panel.md) | view, colour, regions, fields and playback |
| [footer](ui/footer.md) | the footer |
| [widgets](ui/widgets.md) | widgets shared by the panels |
| [theme](ui/theme.md) | design tokens and CSS fragments |
