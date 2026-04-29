"""Color palette and colormap definitions for VisFEM."""

from visfem.engine.colors import scheme_to_hex, region_colors  # noqa: F401 re-exported

# ---- Categorical palettes ----

# Clinical Claes healing-zone colors (red=bad, green=good, grey=resorption).
_CLINICAL: list[str] = ["#7f7f7f", "#bcbd22", "#d62728", "#ff7f0e", "#2ca02c"]

# Qual-paired palette (11 distinct colors) for datasets with many regions.
_PAIRED: list[str] = scheme_to_hex(60)

# Tableau 10 colors
_TABLEAU: list[str] = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
]

# Wong (2011) - "Points of view: Color blindness", Nature Methods 8:441.
_WONG: list[str] = [
    "#000000", "#e69f00", "#56b4e9", "#009e73",
    "#f0e442", "#0072b2", "#d55e00", "#cc79a7",
]

# Paul Tol's Bright scheme, optimised for all colour-vision deficiencies.
_TOL_BRIGHT: list[str] = [
    "#4477aa", "#ee6677", "#228833", "#ccbb44",
    "#66ccee", "#aa3377", "#bbbbbb",
]

CATEGORICAL_PALETTES: dict[str, list[str]] = {
    "clinical":  _CLINICAL,
    "paired":    _PAIRED,
    "tableau":   _TABLEAU,
    "wong":      _WONG,
    "tol_bright": _TOL_BRIGHT,
}

# UI metadata for the palette picker (name, display label, preview swatches).
_SWATCH_COUNT = 5  # normalized count - all palettes show same number of dots

CATEGORICAL_META: list[dict] = [
    {"name": "clinical",   "label": "Clinical",   "swatches": _CLINICAL[:_SWATCH_COUNT]},
    {"name": "paired",     "label": "Paired",     "swatches": _PAIRED[:_SWATCH_COUNT]},
    {"name": "tableau",    "label": "Tableau",    "swatches": _TABLEAU[:_SWATCH_COUNT]},
    {"name": "wong",       "label": "Wong",       "swatches": _WONG[:_SWATCH_COUNT]},
    {"name": "tol_bright", "label": "Tol Bright", "swatches": _TOL_BRIGHT[:_SWATCH_COUNT]},
]


# ---- Continuous colormaps ----

CONTINUOUS_CMAPS: dict[str, str] = {
    "viridis": (
        "linear-gradient(to right, "
        "#440154 0%, #3b528b 25%, #21918c 50%, #5ec962 75%, #fde725 100%)"
    ),
    "plasma": (
        "linear-gradient(to right, "
        "#0d0887 0%, #7e03a8 25%, #cc4778 50%, #f89540 75%, #f0f921 100%)"
    ),
    "cividis": (
        "linear-gradient(to right, "
        "#00224d 0%, #384b70 25%, #7b7979 50%, #bda566 75%, #fee867 100%)"
    ),
    "inferno": (
        "linear-gradient(to right, "
        "#000004 0%, #420a68 25%, #932667 50%, #e76f5a 75%, #fcffa4 100%)"
    ),
    "turbo": (
        "linear-gradient(to right, "
        "#30123b 0%, #4145ab 8%, #4675ed 17%, #39a2fc 25%, "
        "#1bcfd4 38%, #24eca6 50%, #61fc6c 62%, "
        "#a4fc3b 70%, #f3c63a 80%, #fe9b2d 88%, "
        "#f36315 93%, #7a0403 100%)"
    ),
}

# UI metadata for the colormap picker (name, display label, gradient CSS string)
CONTINUOUS_META: list[dict] = [
    {"name": "viridis", "label": "Viridis",  "gradient": CONTINUOUS_CMAPS["viridis"]},
    {"name": "plasma",  "label": "Plasma",   "gradient": CONTINUOUS_CMAPS["plasma"]},
    {"name": "cividis", "label": "Cividis",  "gradient": CONTINUOUS_CMAPS["cividis"]},
    {"name": "inferno", "label": "Inferno",  "gradient": CONTINUOUS_CMAPS["inferno"]},
    {"name": "turbo",   "label": "Turbo",  "gradient": CONTINUOUS_CMAPS["turbo"]},
]
