"""Left panel: dataset selection tree + active dataset info."""

from collections.abc import Iterator
from contextlib import contextmanager

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visfem.engine.discovery import dataset_dir, discover_xdmf, xdmf_display_name
from visfem.models import ProjectMetadata
from visfem.ui.theme import (
    ACCENT,
    ACCENT_DIM,
    FS_LG,
    FS_MD,
    FS_SM,
    FS_XS,
    FW_BOLD,
    FW_SEMI,
    GAP_LG,
    GAP_MD,
    GAP_SM,
    ICON_LG,
    ICON_SM,
    LS_WIDE,
    LS_WIDER,
    OP_BODY,
    OP_DIM,
    OP_GHOST,
    OP_MUTED,
    PAD_LG,
    PAD_MD,
    PAD_SM,
    PAD_XL,
    PAD_XS,
    RADIUS_MD,
    SPP_COLOR,
    SPP_DIM,
)
from visfem.ui.widgets import section_header

# Compact gap between the leading icon and the item label
_ICON_GAP = f"display:flex; align-items:center; gap:{GAP_MD};"

# Padding of the two left panel section headers.
_HEADER_PAD = f"padding:{PAD_MD} {PAD_LG} 4px {PAD_LG};"

# Metadata row container and its leading icon.
_ROW_STYLE = f"display:flex; gap:{GAP_LG}; margin-bottom:8px; align-items:flex-start;"
_ROW_ICON_STYLE = f"opacity:{OP_DIM}; margin-top:2px; flex-shrink:0;"


def build_left_panel(
    organ_groups: dict[str, list[tuple[str, ProjectMetadata]]],
    patients_by_dataset: dict[str, list[int]],
    on_select_dataset: object,
    on_select_xdmf: object,
    on_select_patient: object,
) -> None:
    """Left panel content: dataset tree (top) + active dataset info (bottom)."""
    with html.Div(style="display:flex; flex-direction:column; height:100%;"):
        section_header(
            "mdi-layers-outline",
            "Datasets",
            "left_datasets_section_open",
            prefix=_HEADER_PAD,
            suffix="flex-shrink:0;",
        )

        with html.Div(
            v_show="left_datasets_section_open",
            style="flex:0 1 auto; max-height:45%; overflow-y:auto;",
        ):
            with v3.VList(
                density="compact",
                nav=True,
                bg_color="transparent",
                opened=("active_organ_group_open",),
                update_opened="active_organ_group_open = $event",
                style="padding:0 6px; --v-list-item-min-height: 28px;",
            ):
                for system, datasets in organ_groups.items():
                    with _tree_group(system):
                        with v3.Template(v_slot_activator="{ props }"):
                            with v3.VListItem(v_bind="props", density="compact"):
                                with v3.Template(v_slot_title=""):
                                    html.Span(
                                        system.title(),
                                        style=f"font-size:{FS_SM}; font-weight:{FW_SEMI}; text-transform:uppercase; letter-spacing:{LS_WIDE}; opacity:{OP_MUTED};",
                                    )
                        # Split datasets into ungrouped and sub-grouped buckets
                        ungrouped = [(k, m) for k, m in datasets if not m.subgroup]
                        subgroups: dict[str, list[tuple[str, ProjectMetadata]]] = {}
                        for k, m in datasets:
                            if m.subgroup:
                                subgroups.setdefault(m.subgroup, []).append((k, m))

                        for key, meta in ungrouped:
                            _render_dataset_item(
                                key,
                                meta,
                                "12px",
                                patients_by_dataset,
                                on_select_dataset,
                                on_select_xdmf,
                                on_select_patient,
                            )

                        for subgroup_name, subgroup_datasets in sorted(
                            subgroups.items()
                        ):
                            with _tree_group(subgroup_name):
                                with v3.Template(v_slot_activator="{ props }"):
                                    _tree_item(
                                        subgroup_name,
                                        "mdi-circle-medium",
                                        indent="12px",
                                        activator=True,
                                        highlight=False,
                                    )
                                for key, meta in subgroup_datasets:
                                    _render_dataset_item(
                                        key,
                                        meta,
                                        "24px",
                                        patients_by_dataset,
                                        on_select_dataset,
                                        on_select_xdmf,
                                        on_select_patient,
                                    )

        v3.VDivider()

        section_header(
            "mdi-information-outline",
            "Dataset Info",
            "left_info_section_open",
            prefix=_HEADER_PAD,
            suffix="flex-shrink:0;",
        )

        with html.Div(
            v_show="left_info_section_open",
            style=f"flex:1; overflow-y:auto; min-height:0; padding:0 {PAD_LG} {PAD_LG} {PAD_LG};",
        ):
            # Empty state
            with html.Div(
                v_if="active_meta === null",
                style=f"padding:{PAD_XL} 0; text-align:center; opacity:{OP_GHOST};",
            ):
                v3.VIcon(
                    "mdi-cube-outline",
                    size=ICON_LG,
                    style="display:block; margin:0 auto 8px;",
                )
                html.Div(
                    "Select a dataset to view metadata", style=f"font-size:{FS_MD};"
                )

            # Filled state
            with html.Div(v_if="active_meta !== null"):
                with html.Div(
                    style=f"display:flex; align-items:center; gap:{GAP_MD}; flex-wrap:wrap; margin-bottom:6px;"
                ):
                    html.Div(
                        "{{ active_meta.name }}",
                        style=f"font-size:{FS_LG}; font-weight:{FW_BOLD}; line-height:1.3;",
                    )
                    html.Span(
                        "SPP2311",
                        v_if="active_meta.spp_badge",
                        style=f"font-size:{FS_XS}; padding:3px 8px; border-radius:{RADIUS_MD}; background:{SPP_DIM}; color:{SPP_COLOR}; font-weight:{FW_BOLD}; letter-spacing:{LS_WIDER}; border:1px solid {SPP_COLOR}; flex-shrink:0; line-height:1.6;",
                    )

                with html.Div(
                    style=f"display:flex; flex-wrap:wrap; gap:{GAP_SM}; margin-bottom:10px;"
                ):
                    with html.Div(v_for="sys in active_meta.organ_system", key="sys"):
                        html.Span(
                            "{{ sys }}",
                            style=f"font-size:{FS_XS}; padding:{PAD_XS} {PAD_SM}; border-radius:{RADIUS_MD}; background:{ACCENT_DIM}; color:{ACCENT}; text-transform:uppercase; letter-spacing:{LS_WIDE};",
                        )

                html.Div(
                    "{{ active_meta.description }}",
                    style=f"font-size:{FS_MD}; line-height:1.5; opacity:{OP_BODY}; margin-bottom:12px;",
                )

                v3.VDivider(style="margin-bottom:10px;")

                with _row(
                    "mdi-certificate-outline",
                    "SPP2311 Project",
                    v_if="active_meta && active_meta.spp_project",
                    icon_style=f"color:{SPP_COLOR}; opacity:0.7; margin-top:2px; flex-shrink:0;",
                ):
                    html.Div(
                        "{{ active_meta.spp_project }}",
                        style=f"font-size:{FS_MD}; line-height:1.4; opacity:{OP_BODY};",
                    )

                # The label keeps its case: uppercase would read "PI(S)".
                with _row("mdi-account-outline", "PI(s)", label_upper=False):
                    html.Div("{{ active_meta.pi }}", style=f"font-size:{FS_MD};")

                with _row("mdi-bank-outline", "Institution"):
                    with html.Div(v_for="inst in active_meta.institution", key="inst"):
                        html.Div(
                            "{{ inst }}",
                            style=f"font-size:{FS_MD}; line-height:1.5;",
                        )

                _value_row(
                    "mdi-magnify",
                    "Biological scale",
                    "{{ active_meta.biological_scale }}",
                )

                _value_row(
                    "mdi-cube-scan", "Mesh format", "{{ active_meta.mesh_format }}"
                )

                with _row("mdi-vector-triangle", "Mesh", v_if="mesh_stats !== null"):
                    html.Div(
                        "{{ mesh_stats.n_cells.toLocaleString() }} cells / {{ mesh_stats.n_points.toLocaleString() }} points",
                        style=f"font-size:{FS_MD};",
                    )

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
                        html.Div(
                            "{{ ref }}", style=f"font-size:{FS_SM}; opacity:{OP_BODY};"
                        )


def _render_dataset_item(
    key: str,
    meta: ProjectMetadata,
    indent: str,
    patients_by_dataset: dict[str, list[int]],
    on_select_dataset: object,
    on_select_xdmf: object,
    on_select_patient: object,
) -> None:
    """Render the entry for dataset key with metadata meta at the given indent: a patient group when key is in patients_by_dataset, a single item, or an XDMF file group, dispatching to the three select callbacks; returns None."""
    ddir = dataset_dir(meta)
    xdmf_files = discover_xdmf(ddir)
    if key in patients_by_dataset:
        with _tree_group(key):
            with v3.Template(v_slot_activator="{ props }"):
                _tree_item(
                    meta.name,
                    "mdi-circle-medium",
                    indent=indent,
                    active=f"active_dataset === '{key}'",
                    activator=True,
                )
            for patient in patients_by_dataset[key]:
                _tree_item(
                    f"Patient {patient:02d}",
                    "mdi-account",
                    indent="24px",
                    active=f"active_dataset === '{key}' && active_patient === {patient}",
                    click=(on_select_patient, f"['{key}', {patient}]"),
                )
    elif len(xdmf_files) <= 1:
        _tree_item(
            meta.name,
            "mdi-circle-medium",
            indent=indent,
            wrap=True,
            active=f"active_dataset === '{key}'",
            click=(on_select_dataset, f"['{key}']"),
        )
    else:
        with _tree_group(key):
            with v3.Template(v_slot_activator="{ props }"):
                _tree_item(
                    meta.name,
                    "mdi-circle-medium",
                    indent=indent,
                    wrap=True,
                    active=f"active_dataset === '{key}'",
                    activator=True,
                )
            for stem, _ in xdmf_files.items():
                _tree_item(
                    xdmf_display_name(stem),
                    "mdi-circle-small",
                    indent="24px",
                    icon_size="small",
                    active=f"active_dataset === '{key}' && active_xdmf === '{stem}'",
                    click=(on_select_xdmf, f"['{key}', '{stem}']"),
                )


def _tree_group(value: str) -> v3.VListGroup:
    """Return a VListGroup for the tree with the chevron expand and collapse icons, keyed by value."""
    return v3.VListGroup(
        value=value,
        expand_icon="mdi-chevron-right",
        collapse_icon="mdi-chevron-down",
    )


def _tree_item(
    label: str,
    icon: str,
    *,
    indent: str,
    icon_size: str = "x-small",
    wrap: bool = False,
    active: str | None = None,
    click: tuple[object, str] | None = None,
    activator: bool = False,
    highlight: bool = True,
) -> None:
    """Render one tree list item with a muted icon of icon_size and label at the given indent; active is a JS expression, click a (callback, args) tuple that also disables the item while loading or busy, activator binds the slot props, wrap lets the label break, highlight adds the rounded accent active style; returns None."""
    with v3.VListItem(
        v_bind="props" if activator else None,
        density="compact",
        active=(active,) if active else None,
        active_color=ACCENT if highlight else None,
        rounded="lg" if highlight else None,
        click=click,
        disabled=("loading || busy",) if click else None,
        style=f"padding-left:{indent};",
    ):
        with v3.Template(v_slot_title=""):
            with html.Div(style=_ICON_GAP):
                v3.VIcon(
                    icon,
                    size=icon_size,
                    style=f"opacity:{OP_MUTED}; flex-shrink:0;",
                )
                html.Span(
                    label,
                    style=f"font-size:{FS_MD};"
                    + (" white-space:normal; word-break:break-word;" if wrap else ""),
                )


def _label(text: str, *, upper: bool = True) -> None:
    """Render text as a small metadata label; upper selects uppercase or unchanged case; returns None."""
    transform = "uppercase" if upper else "none"
    html.Div(
        text,
        style=f"font-size:{FS_XS}; opacity:{OP_MUTED}; text-transform:{transform}; letter-spacing:{LS_WIDER}; margin-bottom:2px;",
    )


@contextmanager
def _row(
    icon: str,
    label: str,
    *,
    v_if: str | None = None,
    icon_style: str | None = None,
    label_upper: bool = True,
) -> Iterator[None]:
    """Open an icon + label metadata row gated by the v_if expression and yield inside its value column; icon_style replaces the muted icon style, label_upper selects the label case; yields None."""
    with html.Div(v_if=v_if, style=_ROW_STYLE):
        v3.VIcon(icon, size=ICON_SM, style=icon_style or _ROW_ICON_STYLE)
        with html.Div():
            _label(label, upper=label_upper)
            yield


def _value_row(icon: str, label: str, value_template: str) -> None:
    """Render an icon + label + single value metadata row from the value template; returns None."""
    with _row(icon, label):
        html.Div(value_template, style=f"font-size:{FS_MD};")
