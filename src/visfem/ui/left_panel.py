"""Left panel: dataset selection tree + active dataset info."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visfem.engine.discovery import dataset_dir, discover_xdmf, xdmf_display_name
from visfem.models import ProjectMetadata
from visfem.ui.theme import (
    ACCENT, ACCENT_DIM,
    FS_XS, FS_SM2, FS_SM3, FS_MD, FS_MD2, FS_MD3, FS_MD4, FS_LG,
    FW_BOLD, LS_WIDE, LS_WIDER, LS_WIDEST,
    RADIUS_MD,
)


def build_left_panel(
    organ_groups: dict[str, list[tuple[str, ProjectMetadata]]],
    ircadb_patients: list[int],
    on_select_dataset: object,
    on_select_xdmf: object,
    on_select_patient: object,
) -> None:
    """Left panel content: dataset tree (top) + active dataset info (bottom)."""
    with html.Div(style="display:flex; flex-direction:column; height:100%;"):

        # ----------------------------------------------------------------
        # Section: Datasets
        # ----------------------------------------------------------------
        with html.Div(
            style="padding:10px 14px 4px 14px; display:flex; align-items:center; gap:6px; flex-shrink:0; cursor:pointer; user-select:none;",
            click="left_datasets_section_open = !left_datasets_section_open",
        ):
            v3.VIcon("mdi-layers-outline", size="small", color=ACCENT)
            html.Span(
                "Datasets",
                style=f"font-size:{FS_MD2}; font-weight:{FW_BOLD}; text-transform:uppercase; letter-spacing:{LS_WIDEST}; opacity:0.55; flex:1;",
            )
            v3.VIcon(
                ("left_datasets_section_open ? 'mdi-chevron-down' : 'mdi-chevron-right'",),
                size="x-small", style="opacity:0.40;",
            )

        with html.Div(v_show="left_datasets_section_open", style="flex:0 1 auto; max-height:45%; overflow-y:auto;"):
            with v3.VList(
                density="compact",
                nav=True,
                bg_color="transparent",
                opened=("active_organ_group_open",),
                update_opened="active_organ_group_open = $event",
                style="padding:0 6px;",
            ):
                for system, datasets in organ_groups.items():
                    with v3.VListGroup(value=system):
                        with v3.Template(v_slot_activator="{ props }"):
                            with v3.VListItem(v_bind="props", density="compact"):
                                with v3.Template(v_slot_prepend=""):
                                    v3.VIcon("mdi-chevron-right", size="x-small", style="opacity:0.45;")
                                with v3.Template(v_slot_title=""):
                                    html.Span(
                                        system.title(),
                                        style=f"font-size:{FS_MD2}; font-weight:{FW_BOLD}; text-transform:uppercase; letter-spacing:{LS_WIDEST}; opacity:0.55;",
                                    )
                        for key, meta in datasets:
                            ddir = dataset_dir(meta)
                            xdmf_files = discover_xdmf(ddir)

                            if key == "ircadb":
                                with v3.VListGroup(value="ircadb"):
                                    with v3.Template(v_slot_activator="{ props }"):
                                        with v3.VListItem(
                                            v_bind="props", density="compact",
                                            active=("active_dataset === 'ircadb'",),
                                            active_color=ACCENT, rounded="lg",
                                            style="padding-left:12px;",
                                        ):
                                            with v3.Template(v_slot_prepend=""):
                                                v3.VIcon("mdi-circle-medium", size="x-small", style="opacity:0.45;")
                                            with v3.Template(v_slot_title=""):
                                                html.Span(meta.name, style=f"font-size:{FS_MD4};")
                                    for patient in ircadb_patients:
                                        with v3.VListItem(
                                            density="compact",
                                            active=(f"active_dataset === 'ircadb' && active_patient === {patient}",),
                                            active_color=ACCENT, rounded="lg",
                                            click=(on_select_patient, f"[{patient}]"),
                                            style="padding-left:24px;",
                                        ):
                                            with v3.Template(v_slot_prepend=""):
                                                v3.VIcon("mdi-account", size="x-small", style="opacity:0.45;")
                                            with v3.Template(v_slot_title=""):
                                                html.Span(f"Patient {patient:02d}", style=f"font-size:{FS_MD3};")

                            elif len(xdmf_files) <= 1:
                                with v3.VListItem(
                                    density="compact",
                                    active=(f"active_dataset === '{key}'",),
                                    active_color=ACCENT, rounded="lg",
                                    click=(on_select_dataset, f"['{key}']"),
                                    style="padding-left:12px;",
                                ):
                                    with v3.Template(v_slot_prepend=""):
                                        v3.VIcon("mdi-circle-medium", size="x-small", style="opacity:0.45;")
                                    with v3.Template(v_slot_title=""):
                                        html.Span(meta.name, style=f"font-size:{FS_MD4}; white-space:normal; word-break:break-word;")

                            else:
                                with v3.VListGroup(value=key):
                                    with v3.Template(v_slot_activator="{ props }"):
                                        with v3.VListItem(
                                            v_bind="props", density="compact",
                                            active=(f"active_dataset === '{key}'",),
                                            active_color=ACCENT, rounded="lg",
                                            style="padding-left:12px;",
                                        ):
                                            with v3.Template(v_slot_prepend=""):
                                                v3.VIcon("mdi-circle-medium", size="x-small", style="opacity:0.45;")
                                            with v3.Template(v_slot_title=""):
                                                html.Span(meta.name, style=f"font-size:{FS_MD4}; white-space:normal; word-break:break-word;")
                                    for stem, _ in xdmf_files.items():
                                        with v3.VListItem(
                                            density="compact",
                                            active=(f"active_dataset === '{key}' && active_xdmf === '{stem}'",),
                                            active_color=ACCENT, rounded="lg",
                                            click=(on_select_xdmf, f"['{key}', '{stem}']"),
                                            style="padding-left:24px;",
                                        ):
                                            with v3.Template(v_slot_prepend=""):
                                                v3.VIcon("mdi-circle-small", size="x-small", style="opacity:0.45;")
                                            with v3.Template(v_slot_title=""):
                                                html.Span(xdmf_display_name(stem), style=f"font-size:{FS_MD3};")

        # ----------------------------------------------------------------
        # Section: Dataset Info
        # ----------------------------------------------------------------
        v3.VDivider()

        with html.Div(
            style="padding:10px 14px 4px 14px; display:flex; align-items:center; gap:6px; flex-shrink:0; cursor:pointer; user-select:none;",
            click="left_info_section_open = !left_info_section_open",
        ):
            v3.VIcon("mdi-information-outline", size="small", color=ACCENT)
            html.Span(
                "Dataset Info",
                style=f"font-size:{FS_MD2}; font-weight:{FW_BOLD}; text-transform:uppercase; letter-spacing:{LS_WIDEST}; opacity:0.55; flex:1;",
            )
            v3.VIcon(
                ("left_info_section_open ? 'mdi-chevron-down' : 'mdi-chevron-right'",),
                size="x-small", style="opacity:0.40;",
            )

        with html.Div(v_show="left_info_section_open", style="flex:1; overflow-y:auto; min-height:0; padding:0 14px 14px 14px;"):

            # Empty state
            with html.Div(
                v_if="active_meta === null",
                style="padding:24px 0; text-align:center; opacity:0.35;",
            ):
                v3.VIcon("mdi-cube-outline", size="32", style="display:block; margin:0 auto 8px;")
                html.Div("Select a dataset to view metadata", style=f"font-size:{FS_MD2};")

            # Filled state
            with html.Div(v_if="active_meta !== null"):

                html.Div(
                    "{{ active_meta.name }}",
                    style=f"font-size:{FS_LG}; font-weight:{FW_BOLD}; margin-bottom:6px; line-height:1.3;",
                )

                # Organ system tags
                with html.Div(style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:10px;"):
                    with html.Div(v_for="sys in active_meta.organ_system", key="sys"):
                        html.Span(
                            "{{ sys }}",
                            style=f"font-size:{FS_XS}; padding:2px 7px; border-radius:{RADIUS_MD}; background:{ACCENT_DIM}; color:{ACCENT}; text-transform:uppercase; letter-spacing:{LS_WIDE};",
                        )

                # Description
                html.Div(
                    "{{ active_meta.description }}",
                    style=f"font-size:{FS_MD}; line-height:1.5; opacity:0.75; margin-bottom:12px;",
                )

                v3.VDivider(style="margin-bottom:10px;")

                # PI(s)
                with html.Div(style="display:flex; gap:8px; margin-bottom:8px; align-items:flex-start;"):
                    v3.VIcon("mdi-account-outline", size="14", style="opacity:0.5; margin-top:2px; flex-shrink:0;")
                    with html.Div():
                        html.Div(
                            "PI(s)",
                            style=f"font-size:{FS_XS}; opacity:0.45; text-transform:none; letter-spacing:{LS_WIDER}; margin-bottom:2px;",
                        )
                        html.Div("{{ active_meta.pi }}", style=f"font-size:{FS_MD};")

                # Institution
                with html.Div(style="display:flex; gap:8px; margin-bottom:8px; align-items:flex-start;"):
                    v3.VIcon("mdi-bank-outline", size="14", style="opacity:0.5; margin-top:2px; flex-shrink:0;")
                    with html.Div():
                        _label("Institution")
                        with html.Div(v_for="inst in active_meta.institution", key="inst"):
                            html.Div("{{ inst }}", style=f"font-size:{FS_MD}; line-height:1.5;")

                # Biological scale
                _row("mdi-magnify", "Biological scale", "{{ active_meta.biological_scale }}")

                # Mesh format
                _row("mdi-cube-scan", "Mesh format", "{{ active_meta.mesh_format }}")

                # Mesh stats
                with html.Div(
                    v_if="mesh_stats !== null",
                    style="display:flex; gap:8px; margin-bottom:8px; align-items:flex-start;",
                ):
                    v3.VIcon("mdi-vector-triangle", size="14", style="opacity:0.5; margin-top:2px; flex-shrink:0;")
                    with html.Div():
                        _label("Mesh")
                        html.Div(
                            "{{ mesh_stats.n_cells.toLocaleString() }} cells / {{ mesh_stats.n_points.toLocaleString() }} points",
                            style=f"font-size:{FS_MD};",
                        )

                # References
                with html.Div(
                    v_if="active_meta && (active_meta.ref_urls.length > 0 || active_meta.ref_texts.length > 0)",
                    style="margin-top:10px;",
                ):
                    v3.VDivider(style="margin-bottom:8px;")
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
                        style="margin-top:4px;",
                    ):
                        html.Div("{{ ref }}", style=f"font-size:{FS_SM3}; opacity:0.75;")

                # Region legend
                with html.Div(
                    v_if="legend_items && legend_items.length > 0",
                    style="margin-top:10px;",
                ):
                    v3.VDivider(style="margin-bottom:8px;")
                    _label("Regions")
                    with html.Div(style="display:flex; flex-direction:column; gap:5px; margin-top:4px;"):
                        with html.Div(
                            v_for="item in legend_items",
                            key="item.names[0]",
                            style="display:flex; align-items:center; gap:6px;",
                        ):
                            html.Span(
                                style=("'width:10px; height:10px; border-radius:50%; flex-shrink:0; background:' + item.color",),
                            )
                            with html.Div():
                                with html.Div(v_for="n in item.names", key="n"):
                                    html.Span("{{ n }}", style=f"font-size:{FS_SM2}; line-height:1.6;")


def _label(text: str) -> None:
    """Render a small uppercase section label."""
    html.Div(
        text,
        style=f"font-size:{FS_XS}; opacity:0.45; text-transform:uppercase; letter-spacing:{LS_WIDER}; margin-bottom:2px;",
    )


def _row(icon: str, label: str, value_template: str) -> None:
    """Render an icon + label + value row."""
    with html.Div(style="display:flex; gap:8px; margin-bottom:8px; align-items:flex-start;"):
        v3.VIcon(icon, size="14", style="opacity:0.5; margin-top:2px; flex-shrink:0;")
        with html.Div():
            _label(label)
            html.Div(value_template, style=f"font-size:{FS_MD};")
