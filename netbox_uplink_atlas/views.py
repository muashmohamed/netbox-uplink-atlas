from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import render
from django.views import View
from netbox.plugins import get_plugin_config

from .mapdata import build_map_data

PLUGIN = "netbox_uplink_atlas"


class MapView(PermissionRequiredMixin, View):
    """The main map page. Read-only: it only queries NetBox."""

    permission_required = "dcim.view_rack"

    def get(self, request):
        data = build_map_data()
        data["settings"] = {
            "center": get_plugin_config(PLUGIN, "default_center"),
            "zoom": get_plugin_config(PLUGIN, "default_zoom"),
        }
        return render(
            request,
            "netbox_uplink_atlas/map.html",
            {
                "map_data": data,
                "stats": data["stats"],
            },
        )
