from netbox.plugins import PluginConfig


class UplinkAtlasConfig(PluginConfig):
    name = "netbox_uplink_atlas"
    verbose_name = "Uplink Atlas"
    description = "Racks on a map with the fiber uplinks between them (read-only)."
    version = "0.1.0"
    author = "Muash Mohamed"
    base_url = "uplink-atlas"
    min_version = "4.6.0"
    default_settings = {
        # Device role slugs whose GPS coordinates place the rack, best first.
        "gps_role_priority": ["odf"],
        # Map start point [lat, lon] when nothing has coordinates yet (Male').
        "default_center": [4.1755, 73.5093],
        "default_zoom": 8,
    }


config = UplinkAtlasConfig
