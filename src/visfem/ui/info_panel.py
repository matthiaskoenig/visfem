"""Metadata info panel UI for VisFEM."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3
from visfem.ui.theme import (
    ACCENT, ACCENT_DIM,
    FS_XS, FS_SM3, FS_MD, FS_MD2, FS_SM2, FS_LG,
    FW_BOLD,
    LS_WIDE, LS_WIDER,
    RADIUS_MD,
    Z_PANEL, PANEL_TOP, PANEL_RIGHT, PANEL_WIDTH,
    panel_style,
)

_panel_style = panel_style(
    f"position:absolute; top:{PANEL_TOP}; right:{PANEL_RIGHT}; "
    f"width:{PANEL_WIDTH}; z-index:{Z_PANEL}; "
)


def build_info_panel() -> None:
    """Build the floating metadata info panel on the right."""
    with v3.VCard(style=_panel_style, elevation=6, rounded="lg"):

        # ---- Header ----
        with v3.VCardTitle(
            style="font-size: 0.85rem; padding: 8px 12px; cursor: pointer; user-select: none;",
            click="panel_info_open = !panel_info_open",
        ):
            with html.Div(style="display: flex; align-items: center;"):
                v3.VIcon("mdi-information-outline", size="small", color=ACCENT, classes="mr-2")
                html.Span("Dataset Info", style="flex: 1;")
                v3.VIcon(
                    ("panel_info_open ? 'mdi-chevron-up' : 'mdi-chevron-down'",),
                    size="small", style="opacity: 0.6;",
                )

        with v3.VExpandTransition():
            with html.Div(v_show="panel_info_open", style="max-height: 80vh; overflow-y: auto;"):
                v3.VDivider()

                # ---- Empty state ----
                with html.Div(
                    v_if="active_meta === null",
                    style="padding: 24px 16px; text-align: center; opacity: 0.35;",
                ):
                    v3.VIcon("mdi-cube-outline", size="32", style="margin-bottom: 8px; display: block; margin-left: auto; margin-right: auto;")
                    html.Div("Select a dataset to view metadata", style=f"font-size:{FS_MD2};")

                # ---- Filled state ----
                with html.Div(v_if="active_meta !== null", style="padding: 12px 14px;"):

                    # ---- Name ----
                    html.Div(
                        "{{ active_meta.name }}",
                        style=f"font-size:{FS_LG}; font-weight:{FW_BOLD}; margin-bottom:6px; line-height:1.3;",
                    )

                    # ---- Organ system tags ----
                    with html.Div(style="display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px;"):
                        with html.Div(v_for="sys in active_meta.organ_system", key="sys"):
                            html.Span(
                                "{{ sys }}",
                                style=f"font-size:{FS_XS}; padding:2px 7px; border-radius:{RADIUS_MD}; background:{ACCENT_DIM}; color:{ACCENT}; text-transform:uppercase; letter-spacing:{LS_WIDE};",
                            )

                    # ---- Description ----
                    html.Div(
                        "{{ active_meta.description }}",
                        style=f"font-size:{FS_MD}; line-height:1.5; opacity:0.75; margin-bottom:12px;",
                    )

                    v3.VDivider(style="margin-bottom: 10px;")

                    # ---- PI ----
                    with html.Div(style="display: flex; gap: 8px; margin-bottom: 8px; align-items: flex-start;"):
                        v3.VIcon("mdi-account-outline", size="14", style="opacity: 0.5; margin-top: 2px; flex-shrink: 0;")
                        with html.Div():
                            html.Div(
                                "PI(s)",
                                style=f"font-size:{FS_XS}; opacity:0.45; text-transform:none; letter-spacing:{LS_WIDER}; margin-bottom:2px;",
                            )
                            html.Div("{{ active_meta.pi }}", style=f"font-size:{FS_MD};")

                    # ---- Institution ----
                    with html.Div(style="display: flex; gap: 8px; margin-bottom: 8px; align-items: flex-start;"):
                        v3.VIcon("mdi-bank-outline", size="14", style="opacity: 0.5; margin-top: 2px; flex-shrink: 0;")
                        with html.Div():
                            _label("Institution")
                            with html.Div(v_for="inst in active_meta.institution", key="inst"):
                                html.Div("{{ inst }}", style=f"font-size:{FS_MD}; line-height:1.5;")

                    # ---- Biological scale ----
                    _row("mdi-magnify", "Biological scale", "{{ active_meta.biological_scale }}")

                    # ---- Mesh format ----
                    _row("mdi-cube-scan", "Mesh format", "{{ active_meta.mesh_format }}")

                    # ---- Mesh stats ----
                    with html.Div(
                        v_if="mesh_stats !== null",
                        style="display: flex; gap: 8px; margin-bottom: 8px; align-items: flex-start;",
                    ):
                        v3.VIcon("mdi-vector-triangle", size="14", style="opacity: 0.5; margin-top: 2px; flex-shrink: 0;")
                        with html.Div():
                            _label("Mesh")
                            html.Div(
                                "{{ mesh_stats.n_cells.toLocaleString() }} cells / {{ mesh_stats.n_points.toLocaleString() }} points",
                                style=f"font-size:{FS_MD};",
                            )

                    # ---- References ----
                    with html.Div(
                        v_if="active_meta && (active_meta.ref_urls.length > 0 || active_meta.ref_texts.length > 0)",
                        style="margin-top: 10px;",
                    ):
                        v3.VDivider(style="margin-bottom: 8px;")
                        _label("References")
                        with html.Div(
                                v_for="ref in active_meta.ref_urls",
                                key="ref",
                                style="display:flex; align-items:flex-start; gap:5px; margin-top:5px;",
                        ):
                            v3.VIcon(
                                icon=(
                                    "ref.toLowerCase().includes('zenodo') ? 'mdi-database' :"
                                    " ref.toLowerCase().includes('github') ? 'mdi-github' :"
                                    " ref.toLowerCase().includes('doi.org') ? 'mdi-file-document-outline' :"
                                    " 'mdi-open-in-new'",
                                ),
                                size="13",
                                style="flex-shrink:0; margin-top:1px; opacity:0.5;",
                            )
                            html.A(
                                "{{ ref }}",
                                href=("ref",),
                                target="_blank",
                                style=f"color:{ACCENT}; font-size:{FS_SM3}; word-break:break-all; text-decoration:none;",
                            )
                        with html.Div(
                                v_for="ref in active_meta.ref_texts",
                                key="ref",
                                style="margin-top: 4px;",
                        ):
                            html.Div("{{ ref }}", style=f"font-size:{FS_SM3}; opacity:0.75;")

                    # ---- Region legend ----
                    with html.Div(
                        v_if="legend_items && legend_items.length > 0",
                        style="margin-top: 10px;",
                    ):
                        v3.VDivider(style="margin-bottom: 8px;")
                        _label("Regions")
                        with html.Div(style="display: flex; flex-direction: column; gap: 5px; margin-top: 4px;"):
                            with html.Div(
                                v_for="item in legend_items",
                                key="item.names[0]",
                                style="display: flex; align-items: center; gap: 6px;",
                            ):
                                html.Span(
                                    style=("'width:10px; height:10px; border-radius:50%; flex-shrink:0; background:' + item.color",),
                                )
                                with html.Div():
                                    with html.Div(
                                        v_for="n in item.names",
                                        key="n",
                                    ):
                                        html.Span("{{ n }}", style=f"font-size:{FS_SM2}; line-height:1.6;")


def _label(text: str) -> None:
    """Render a small uppercase section label."""
    html.Div(
        text,
        style=f"font-size:{FS_XS}; opacity:0.45; text-transform:uppercase; letter-spacing:{LS_WIDER}; margin-bottom:2px;",
    )


def _row(icon: str, label: str, value_template: str) -> None:
    """Render an icon + label + value row."""
    with html.Div(style="display: flex; gap: 8px; margin-bottom: 8px; align-items: flex-start;"):
        v3.VIcon(icon, size="14", style="opacity: 0.5; margin-top: 2px; flex-shrink: 0;")
        with html.Div():
            _label(label)
            html.Div(value_template, style=f"font-size:{FS_MD};")
