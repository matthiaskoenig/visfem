"""Dataset selection panel UI for VisFEM."""
from visfem.engine.discovery import dataset_dir, discover_xdmf, xdmf_display_name
from visfem.models import ProjectMetadata
from trame.widgets import html
from trame.widgets import vuetify3 as v3
from visfem.ui.theme import (
    ACCENT,
    FS_MD2, FS_MD3, FS_MD4,
    FW_BOLD, LS_WIDEST,
    Z_PANEL, PANEL_TOP, PANEL_LEFT, PANEL_WIDTH,
    panel_style,
)

_panel_style = panel_style(
    f"position:absolute; top:{PANEL_TOP}; left:{PANEL_LEFT}; "
    f"width:{PANEL_WIDTH}; z-index:{Z_PANEL}; "
)


def build_dataset_panel(
    organ_groups: dict[str, list[tuple[str, ProjectMetadata]]],
    ircadb_patients: list[int],
    on_select_dataset: object,
    on_select_xdmf: object,
    on_select_patient: object,
) -> None:
    """Build the floating dataset selection panel on the left."""
    with v3.VCard(style=_panel_style, elevation=6, rounded="lg"):
        with v3.VCardTitle(
            style="font-size: 0.85rem; padding: 8px 12px; cursor: pointer; user-select: none;",
            click="panel_datasets_open = !panel_datasets_open",
        ):
            with html.Div(style="display: flex; align-items: center;"):
                v3.VIcon("mdi-layers-outline", size="small", color=ACCENT, classes="mr-2")
                html.Span("Datasets", style="flex: 1;")
                v3.VIcon(
                    ("panel_datasets_open ? 'mdi-chevron-up' : 'mdi-chevron-down'",),
                    size="small", style="opacity: 0.6;",
                )
        with v3.VExpandTransition():
            with html.Div(v_show="panel_datasets_open", style="max-height: 70vh; overflow-y: auto;"):
                v3.VDivider()
                with v3.VList(density="compact", nav=True, bg_color="transparent", style="padding: 4px 0;"):
                    for system, datasets in organ_groups.items():
                        with v3.VListGroup(value=system):
                            with v3.Template(v_slot_activator="{ props }"):
                                with v3.VListItem(v_bind="props", density="compact"):
                                    with v3.Template(v_slot_prepend=""):
                                        v3.VIcon("mdi-chevron-right", size="x-small", style="opacity: 0.5;")
                                    with v3.Template(v_slot_title=""):
                                        html.Span(
                                            system.title(),
                                            style=f"font-size:{FS_MD2}; font-weight:{FW_BOLD}; text-transform:uppercase; letter-spacing:{LS_WIDEST}; opacity:0.6;",
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
                                                style="padding-left: 24px;",
                                            ):
                                                with v3.Template(v_slot_prepend=""):
                                                    v3.VIcon("mdi-circle-medium", size="x-small", style="opacity: 0.5;")
                                                with v3.Template(v_slot_title=""):
                                                    html.Span(meta.name, style=f"font-size:{FS_MD4};")
                                        for patient in ircadb_patients:
                                            with v3.VListItem(
                                                density="compact",
                                                active=(f"active_dataset === 'ircadb' && active_patient === {patient}",),
                                                active_color=ACCENT, rounded="lg",
                                                click=(on_select_patient, f"[{patient}]"),
                                                style="padding-left: 40px;",
                                            ):
                                                with v3.Template(v_slot_prepend=""):
                                                    v3.VIcon("mdi-account", size="x-small", style="opacity: 0.5;")
                                                with v3.Template(v_slot_title=""):
                                                    html.Span(f"Patient {patient:02d}", style=f"font-size:{FS_MD3};")

                                elif len(xdmf_files) <= 1:
                                    with v3.VListItem(
                                        density="compact",
                                        active=(f"active_dataset === '{key}'",),
                                        active_color=ACCENT, rounded="lg",
                                        click=(on_select_dataset, f"['{key}']"),
                                        style="padding-left: 24px;",
                                    ):
                                        with v3.Template(v_slot_prepend=""):
                                            v3.VIcon("mdi-circle-medium", size="x-small", style="opacity: 0.5;")
                                        with v3.Template(v_slot_title=""):
                                            html.Span(meta.name, style=f"font-size:{FS_MD4}; white-space:normal; word-break:break-word;")

                                elif len(xdmf_files) > 1:
                                    with v3.VListGroup(value=key):
                                        with v3.Template(v_slot_activator="{ props }"):
                                            with v3.VListItem(
                                                v_bind="props", density="compact",
                                                active=(f"active_dataset === '{key}'",),
                                                active_color=ACCENT, rounded="lg",
                                                style="padding-left: 24px;",
                                            ):
                                                with v3.Template(v_slot_prepend=""):
                                                    v3.VIcon("mdi-circle-medium", size="x-small", style="opacity: 0.5;")
                                                with v3.Template(v_slot_title=""):
                                                    html.Span(meta.name, style=f"font-size:{FS_MD4}; white-space:normal; word-break:break-word;")
                                        for stem, _ in xdmf_files.items():
                                            with v3.VListItem(
                                                density="compact",
                                                active=(f"active_dataset === '{key}' && active_xdmf === '{stem}'",),
                                                active_color=ACCENT, rounded="lg",
                                                click=(on_select_xdmf, f"['{key}', '{stem}']"),
                                                style="padding-left: 40px;",
                                            ):
                                                with v3.Template(v_slot_prepend=""):
                                                    v3.VIcon("mdi-circle-small", size="x-small", style="opacity: 0.5;")
                                                with v3.Template(v_slot_title=""):
                                                    html.Span(xdmf_display_name(stem), style=f"font-size:{FS_MD3};")
