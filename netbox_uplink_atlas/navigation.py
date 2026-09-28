from netbox.plugins import PluginMenu, PluginMenuItem

menu = PluginMenu(
    label="Uplink Atlas",
    icon_class="mdi mdi-map-marker-path",
    groups=(
        (
            "Maps",
            (
                PluginMenuItem(
                    link="plugins:netbox_uplink_atlas:map",
                    link_text="Uplink map",
                    permissions=["dcim.view_rack"],
                ),
            ),
        ),
        (
            "Connections",
            (
                PluginMenuItem(
                    link="plugins:netbox_uplink_atlas:connections",
                    link_text="Switches & interfaces",
                    permissions=["dcim.view_interface"],
                ),
            ),
        ),
    ),
)
