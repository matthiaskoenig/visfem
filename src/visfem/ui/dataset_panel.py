"""Dataset selection panel UI fragment for VisFEM."""
from visfem.engine.discovery import dataset_dir, discover_xdmf, xdmf_display_name
from visfem.models import ProjectMetadata
from trame.widgets import html
from trame.widgets import vuetify3 as v3


def build_dataset_panel(
    organ_groups: dict[str, list[tuple[str, ProjectMetadata]]],
    ircadb_patients: list[int],
    on_select_dataset: object,
    on_select_xdmf: object,
    on_select_patient: object,
) -> None:
    """Build the floating dataset selection panel on the left."""
    panel_style = (
        "dark_mode ? "
        "'position:absolute; top:12px; left:12px; width:270px; z-index:10; "
        "background:rgba(28,35,35,0.88); backdrop-filter:blur(8px); "
        "-webkit-backdrop-filter:blur(8px); border:1px solid rgba(255,255,255,0.07);' "
        ": "
        "'position:absolute; top:12px; left:12px; width:270px; z-index:10; "
        "background:rgba(240,244,244,0.92); backdrop-filter:blur(8px); "
        "-webkit-backdrop-filter:blur(8px); border:1px solid rgba(0,0,0,0.08);'"
    ,)
    with v3.VCard(style=panel_style, elevation=6, rounded="lg"):
        with v3.VCardTitle(
            style="font-size: 0.85rem; padding: 8px 12px; cursor: pointer; user-select: none;",
            click="panel_datasets_open = !panel_datasets_open",
        ):
            with html.Div(style="display: flex; align-items: center;"):
                v3.VIcon("mdi-layers-outline", size="small", color="#00897b", classes="mr-2")
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
                                            style="font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; opacity: 0.6;",
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
                                                active_color="#00897b", rounded="lg",
                                                style="padding-left: 24px;",
                                            ):
                                                with v3.Template(v_slot_prepend=""):
                                                    v3.VIcon("mdi-circle-medium", size="x-small", style="opacity: 0.5;")
                                                with v3.Template(v_slot_title=""):
                                                    html.Span(meta.name, style="font-size: 0.82rem;")
                                        for patient in ircadb_patients:
                                            with v3.VListItem(
                                                density="compact",
                                                active=(f"active_dataset === 'ircadb' && active_patient === {patient}",),
                                                active_color="#00897b", rounded="lg",
                                                click=(on_select_patient, f"[{patient}]"),
                                                style="padding-left: 40px;",
                                            ):
                                                with v3.Template(v_slot_prepend=""):
                                                    v3.VIcon("mdi-account", size="x-small", style="opacity: 0.5;")
                                                with v3.Template(v_slot_title=""):
                                                    html.Span(f"Patient {patient:02d}", style="font-size: 0.80rem;")

                                elif key == "heart":
                                    with v3.VListItem(
                                        density="compact",
                                        active=("active_dataset === 'heart'",),
                                        active_color="#00897b", rounded="lg",
                                        click=(on_select_dataset, "['heart']"),
                                        style="padding-left: 24px;",
                                    ):
                                        with v3.Template(v_slot_prepend=""):
                                            v3.VIcon("mdi-circle-medium", size="x-small", style="opacity: 0.5;")
                                        with v3.Template(v_slot_title=""):
                                            html.Span(meta.name, style="font-size: 0.82rem; white-space: normal; word-break: break-word;")

                                elif len(xdmf_files) == 1:
                                    with v3.VListItem(
                                        density="compact",
                                        active=(f"active_dataset === '{key}'",),
                                        active_color="#00897b", rounded="lg",
                                        click=(on_select_dataset, f"['{key}']"),
                                        style="padding-left: 24px;",
                                    ):
                                        with v3.Template(v_slot_prepend=""):
                                            v3.VIcon("mdi-circle-medium", size="x-small", style="opacity: 0.5;")
                                        with v3.Template(v_slot_title=""):
                                            html.Span(meta.name, style="font-size: 0.82rem; white-space: normal; word-break: break-word;")

                                elif len(xdmf_files) > 1:
                                    with v3.VListGroup(value=key):
                                        with v3.Template(v_slot_activator="{ props }"):
                                            with v3.VListItem(
                                                v_bind="props", density="compact",
                                                active=(f"active_dataset === '{key}'",),
                                                active_color="#00897b", rounded="lg",
                                                style="padding-left: 24px;",
                                            ):
                                                with v3.Template(v_slot_prepend=""):
                                                    v3.VIcon("mdi-circle-medium", size="x-small", style="opacity: 0.5;")
                                                with v3.Template(v_slot_title=""):
                                                    html.Span(meta.name, style="font-size: 0.82rem; white-space: normal; word-break: break-word;")
                                        for stem, _ in xdmf_files.items():
                                            with v3.VListItem(
                                                density="compact",
                                                active=(f"active_dataset === '{key}' && active_xdmf === '{stem}'",),
                                                active_color="#00897b", rounded="lg",
                                                click=(on_select_xdmf, f"['{key}', '{stem}']"),
                                                style="padding-left: 40px;",
                                            ):
                                                with v3.Template(v_slot_prepend=""):
                                                    v3.VIcon("mdi-circle-small", size="x-small", style="opacity: 0.5;")
                                                with v3.Template(v_slot_title=""):
                                                    html.Span(xdmf_display_name(stem), style="font-size: 0.80rem;")