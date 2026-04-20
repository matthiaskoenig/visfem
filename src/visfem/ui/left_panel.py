"""Left panel: dataset selection tree + active dataset info."""
from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visfem.engine.discovery import dataset_dir, discover_xdmf, xdmf_display_name
from visfem.models import ProjectMetadata
from visfem.ui.theme import (
    ACCENT, ACCENT_DIM,
    FS_XS, FS_SM, FS_MD, FS_LG,
    FW_BOLD, FW_SEMI, LS_WIDE, LS_WIDER, LS_WIDEST,
    RADIUS_MD,
    ICON_SM, ICON_LG,
    OP_GHOST, OP_MUTED, OP_DIM, OP_SUBDUED, OP_BODY,
    GAP_SM, GAP_MD, GAP_LG,
    PAD_XS, PAD_SM, PAD_MD, PAD_LG, PAD_XL,
)

# Compact gap between the leading icon and the item label
_ICON_GAP = f"display:flex; align-items:center; gap:{GAP_MD};"


def build_left_panel(
    organ_groups: dict[str, list[tuple[str, ProjectMetadata]]],
    patients_by_dataset: dict[str, list[int]],
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
            style=f"padding:{PAD_MD} {PAD_LG} 4px {PAD_LG}; display:flex; align-items:center; gap:{GAP_MD}; flex-shrink:0; cursor:pointer; user-select:none;",
            click="left_datasets_section_open = !left_datasets_section_open",
        ):
            v3.VIcon("mdi-layers-outline", size="small", color=ACCENT)
            html.Span(
                "Datasets",
                style=f"font-size:{FS_MD}; font-weight:{FW_BOLD}; text-transform:uppercase; letter-spacing:{LS_WIDEST}; opacity:{OP_SUBDUED}; flex:1;",
            )
            v3.VIcon("mdi-chevron-down", size="small", v_show="left_datasets_section_open")
            v3.VIcon("mdi-chevron-right", size="small", v_show="!left_datasets_section_open")

        with html.Div(v_show="left_datasets_section_open", style="flex:0 1 auto; max-height:45%; overflow-y:auto;"):
            with v3.VList(
                density="compact",
                nav=True,
                bg_color="transparent",
                opened=("active_organ_group_open",),
                update_opened="active_organ_group_open = $event",
                style="padding:0 6px; --v-list-item-min-height: 28px;",
            ):
                for system, datasets in organ_groups.items():
                    with v3.VListGroup(
                        value=system,
                        expand_icon="mdi-chevron-right",
                        collapse_icon="mdi-chevron-down",
                    ):
                        with v3.Template(v_slot_activator="{ props }"):
                            with v3.VListItem(v_bind="props", density="compact"):
                                with v3.Template(v_slot_title=""):
                                    html.Span(
                                        system.title(),
                                        style=f"font-size:{FS_SM}; font-weight:{FW_SEMI}; text-transform:uppercase; letter-spacing:{LS_WIDE}; opacity:{OP_MUTED};",
                                    )
                        for key, meta in datasets:
                            ddir = dataset_dir(meta)
                            xdmf_files = discover_xdmf(ddir)

                            if key in patients_by_dataset:
                                with v3.VListGroup(
                                    value=key,
                                    expand_icon="mdi-chevron-right",
                                    collapse_icon="mdi-chevron-down",
                                ):
                                    with v3.Template(v_slot_activator="{ props }"):
                                        with v3.VListItem(
                                            v_bind="props", density="compact",
                                            active=(f"active_dataset === '{key}'",),
                                            active_color=ACCENT, rounded="lg",
                                            style="padding-left:12px;",
                                        ):
                                            with v3.Template(v_slot_title=""):
                                                with html.Div(style=_ICON_GAP):
                                                    v3.VIcon("mdi-circle-medium", size="x-small", style=f"opacity:{OP_MUTED}; flex-shrink:0;")
                                                    html.Span(meta.name, style=f"font-size:{FS_MD};")
                                    for patient in patients_by_dataset[key]:
                                        with v3.VListItem(
                                            density="compact",
                                            active=(f"active_dataset === '{key}' && active_patient === {patient}",),
                                            active_color=ACCENT, rounded="lg",
                                            click=(on_select_patient, f"['{key}', {patient}]"),
                                            disabled=("loading",),
                                            style="padding-left:24px;",
                                        ):
                                            with v3.Template(v_slot_title=""):
                                                with html.Div(style=_ICON_GAP):
                                                    v3.VIcon("mdi-account", size="x-small", style=f"opacity:{OP_MUTED}; flex-shrink:0;")
                                                    html.Span(f"Patient {patient:02d}", style=f"font-size:{FS_MD};")

                            elif len(xdmf_files) <= 1:
                                with v3.VListItem(
                                    density="compact",
                                    active=(f"active_dataset === '{key}'",),
                                    active_color=ACCENT, rounded="lg",
                                    click=(on_select_dataset, f"['{key}']"),
                                    disabled=("loading",),
                                    style="padding-left:12px;",
                                ):
                                    with v3.Template(v_slot_title=""):
                                        with html.Div(style=_ICON_GAP):
                                            v3.VIcon("mdi-circle-medium", size="x-small", style=f"opacity:{OP_MUTED}; flex-shrink:0;")
                                            html.Span(meta.name, style=f"font-size:{FS_MD}; white-space:normal; word-break:break-word;")

                            else:
                                with v3.VListGroup(
                                    value=key,
                                    expand_icon="mdi-chevron-right",
                                    collapse_icon="mdi-chevron-down",
                                ):
                                    with v3.Template(v_slot_activator="{ props }"):
                                        with v3.VListItem(
                                            v_bind="props", density="compact",
                                            active=(f"active_dataset === '{key}'",),
                                            active_color=ACCENT, rounded="lg",
                                            style="padding-left:12px;",
                                        ):
                                            with v3.Template(v_slot_title=""):
                                                with html.Div(style=_ICON_GAP):
                                                    v3.VIcon("mdi-circle-medium", size="x-small", style=f"opacity:{OP_MUTED}; flex-shrink:0;")
                                                    html.Span(meta.name, style=f"font-size:{FS_MD}; white-space:normal; word-break:break-word;")
                                    for stem, _ in xdmf_files.items():
                                        with v3.VListItem(
                                            density="compact",
                                            active=(f"active_dataset === '{key}' && active_xdmf === '{stem}'",),
                                            active_color=ACCENT, rounded="lg",
                                            click=(on_select_xdmf, f"['{key}', '{stem}']"),
                                            disabled=("loading",),
                                            style="padding-left:24px;",
                                        ):
                                            with v3.Template(v_slot_title=""):
                                                with html.Div(style=_ICON_GAP):
                                                    v3.VIcon("mdi-circle-small", size="small", style=f"opacity:{OP_MUTED}; flex-shrink:0;")
                                                    html.Span(xdmf_display_name(stem), style=f"font-size:{FS_MD};")

        # ----------------------------------------------------------------
        # Section: Dataset Info
        # ----------------------------------------------------------------
        v3.VDivider()

        with html.Div(
            style=f"padding:{PAD_MD} {PAD_LG} 4px {PAD_LG}; display:flex; align-items:center; gap:{GAP_MD}; flex-shrink:0; cursor:pointer; user-select:none;",
            click="left_info_section_open = !left_info_section_open",
        ):
            v3.VIcon("mdi-information-outline", size="small", color=ACCENT)
            html.Span(
                "Dataset Info",
                style=f"font-size:{FS_MD}; font-weight:{FW_BOLD}; text-transform:uppercase; letter-spacing:{LS_WIDEST}; opacity:{OP_SUBDUED}; flex:1;",
            )
            v3.VIcon("mdi-chevron-down", size="small", v_show="left_info_section_open")
            v3.VIcon("mdi-chevron-right", size="small", v_show="!left_info_section_open")

        with html.Div(v_show="left_info_section_open", style=f"flex:1; overflow-y:auto; min-height:0; padding:0 {PAD_LG} {PAD_LG} {PAD_LG};"):

            # Empty state
            with html.Div(
                v_if="active_meta === null",
                style=f"padding:{PAD_XL} 0; text-align:center; opacity:{OP_GHOST};",
            ):
                v3.VIcon("mdi-cube-outline", size=ICON_LG, style="display:block; margin:0 auto 8px;")
                html.Div("Select a dataset to view metadata", style=f"font-size:{FS_MD};")

            # Filled state
            with html.Div(v_if="active_meta !== null"):

                html.Div(
                    "{{ active_meta.name }}",
                    style=f"font-size:{FS_LG}; font-weight:{FW_BOLD}; margin-bottom:6px; line-height:1.3;",
                )

                # Organ system tags
                with html.Div(style=f"display:flex; flex-wrap:wrap; gap:{GAP_SM}; margin-bottom:10px;"):
                    with html.Div(v_for="sys in active_meta.organ_system", key="sys"):
                        html.Span(
                            "{{ sys }}",
                            style=f"font-size:{FS_XS}; padding:{PAD_XS} {PAD_SM}; border-radius:{RADIUS_MD}; background:{ACCENT_DIM}; color:{ACCENT}; text-transform:uppercase; letter-spacing:{LS_WIDE};",
                        )

                # Description
                html.Div(
                    "{{ active_meta.description }}",
                    style=f"font-size:{FS_MD}; line-height:1.5; opacity:{OP_BODY}; margin-bottom:12px;",
                )

                v3.VDivider(style="margin-bottom:10px;")

                # PI(s)
                with html.Div(style=f"display:flex; gap:{GAP_LG}; margin-bottom:8px; align-items:flex-start;"):
                    v3.VIcon("mdi-account-outline", size=ICON_SM, style=f"opacity:{OP_DIM}; margin-top:2px; flex-shrink:0;")
                    with html.Div():
                        html.Div(
                            "PI(s)",
                            style=f"font-size:{FS_XS}; opacity:{OP_MUTED}; text-transform:none; letter-spacing:{LS_WIDER}; margin-bottom:2px;",
                        )
                        html.Div("{{ active_meta.pi }}", style=f"font-size:{FS_MD};")

                # Institution
                with html.Div(style=f"display:flex; gap:{GAP_LG}; margin-bottom:8px; align-items:flex-start;"):
                    v3.VIcon("mdi-bank-outline", size=ICON_SM, style=f"opacity:{OP_DIM}; margin-top:2px; flex-shrink:0;")
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
                    style=f"display:flex; gap:{GAP_LG}; margin-bottom:8px; align-items:flex-start;",
                ):
                    v3.VIcon("mdi-vector-triangle", size=ICON_SM, style=f"opacity:{OP_DIM}; margin-top:2px; flex-shrink:0;")
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
                        style=f"display:flex; align-items:flex-start; gap:{GAP_MD}; margin-top:5px;",
                    ):
                        v3.VIcon(
                            icon=(
                                "ref.toLowerCase().includes('zenodo') ? 'mdi-database' :"
                                " ref.toLowerCase().includes('github') ? 'mdi-github' :"
                                " ref.toLowerCase().includes('doi.org') ? 'mdi-file-document-outline' :"
                                " 'mdi-open-in-new'",
                            ),
                            size=ICON_SM,
                            style=f"flex-shrink:0; margin-top:1px; opacity:{OP_DIM};",
                        )
                        html.A(
                            "{{ ref }}",
                            href=("ref",),
                            target="_blank",
                            style=f"color:{ACCENT}; font-size:{FS_SM}; word-break:break-all; text-decoration:none;",
                        )
                    with html.Div(
                        v_for="ref in active_meta.ref_texts",
                        key="ref",
                        style="margin-top:4px;",
                    ):
                        html.Div("{{ ref }}", style=f"font-size:{FS_SM}; opacity:{OP_BODY};")



def _label(text: str) -> None:
    """Render a small uppercase section label."""
    html.Div(
        text,
        style=f"font-size:{FS_XS}; opacity:{OP_MUTED}; text-transform:uppercase; letter-spacing:{LS_WIDER}; margin-bottom:2px;",
    )


def _row(icon: str, label: str, value_template: str) -> None:
    """Render an icon + label + value row."""
    with html.Div(style=f"display:flex; gap:{GAP_LG}; margin-bottom:8px; align-items:flex-start;"):
        v3.VIcon(icon, size=ICON_SM, style=f"opacity:{OP_DIM}; margin-top:2px; flex-shrink:0;")
        with html.Div():
            _label(label)
            html.Div(value_template, style=f"font-size:{FS_MD};")
