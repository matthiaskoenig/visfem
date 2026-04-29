"""Color utilities and background constants for VisFEM."""
import pyvista.plotting.colors as pvc

# ---- Background gradients ----

BG_DARK_BOTTOM  = (0.08, 0.10, 0.10)
BG_DARK_TOP     = (0.13, 0.16, 0.16)
BG_LIGHT_BOTTOM = (0.82, 0.84, 0.84)
BG_LIGHT_TOP    = (0.95, 0.96, 0.96)


# ---- Color palettes ----

def scheme_to_hex(scheme_id: int) -> list[str]:
    """Convert a PyVista color scheme to a list of hex color strings."""
    colors = []
    for item in pvc.color_scheme_to_cycler(scheme_id):
        c = item["color"]
        colors.append("#{:02x}{:02x}{:02x}".format(c[0], c[1], c[2]))
    return colors


def region_colors(n: int, palette: list[str]) -> list[str]:
    """Return n colors cycled from palette."""
    return [palette[i % len(palette)] for i in range(n)]