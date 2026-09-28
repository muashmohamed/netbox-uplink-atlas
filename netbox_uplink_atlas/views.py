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


from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import render
from django.views import View

from .connections import build_connections_data
from .device_path import build_device_link_graph, find_device_path, get_connected_device_choices


class ConnectionsView(PermissionRequiredMixin, View):
    """Switch/interface browser, plus a device-to-device path finder. Read-only."""

    permission_required = "dcim.view_interface"

    def get(self, request):
        data = build_connections_data()

        graph, _skip_stats = build_device_link_graph()
        device_choices = get_connected_device_choices(graph)

        path_result = None
        path_error = None
        device_a = request.GET.get("device_a")
        device_b = request.GET.get("device_b")

        if device_a and device_b:
            try:
                device_a_id = int(device_a)
                device_b_id = int(device_b)
                if device_a_id == device_b_id:
                    path_error = "Pick two different devices."
                else:
                    path_result = find_device_path(device_a_id, device_b_id, graph)
                    if path_result is None:
                        path_error = "No path found between these two devices."
            except (TypeError, ValueError):
                path_error = "Invalid device selection."

        return render(
            request,
            "netbox_uplink_atlas/connections.html",
            {
                "switches": data["switches"],
                "stats": data["stats"],
                "device_choices": device_choices,
                "selected_device_a": device_a,
                "selected_device_b": device_b,
                "path_result": path_result,
                "path_error": path_error,
            },
        )


import json

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import JsonResponse
from django.views import View

from dcim.models import Rack

from .rack_position import get_best_device_for_rack, get_rack_position_device


class MoveRackView(PermissionRequiredMixin, View):
    """
    Sets a rack's map position by writing GPS coordinates to the
    appropriate Device. Handles BOTH scenarios the same way:
      - Move: the rack already has a position-providing device -- update it.
      - Place: the rack has no position yet -- pick the best candidate
        device in the rack (by role priority) and give it coordinates
        for the first time.
    This is the only "write" path in this plugin, alongside UnplaceRackView.
    Requires dcim.change_device, not just view permissions.
    """

    permission_required = ("dcim.view_rack", "dcim.change_device")

    def post(self, request, rack_id):
        try:
            body = json.loads(request.body)
            lat = float(body["lat"])
            lon = float(body["lon"])
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({"error": "Invalid request -- expected JSON with lat/lon."}, status=400)

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return JsonResponse({"error": "Coordinates out of valid range."}, status=400)

        rack = Rack.objects.filter(pk=rack_id).first()
        if rack is None:
            return JsonResponse({"error": "Rack not found."}, status=404)

        device = get_best_device_for_rack(rack_id)
        if device is None:
            return JsonResponse({
                "error": (
                    "This rack has no devices at all yet, so there's nothing to "
                    "give a position to. Add a device to this rack first (an ODF "
                    "works best), then it can be placed from the map."
                )
            }, status=400)

        device.latitude = lat
        device.longitude = lon
        device.save()

        return JsonResponse({
            "success": True,
            "rack_name": rack.name,
            "device_name": device.name,
            "lat": lat,
            "lon": lon,
        })


class UnplaceRackView(PermissionRequiredMixin, View):
    """
    Clears a rack's position by wiping the GPS coordinates on whichever
    Device is currently providing it. The rack falls back to the site's
    position, or the "unplaced" list if the site has no coordinates either.
    Idempotent -- calling this on an already-unplaced rack is a harmless no-op.
    """

    permission_required = ("dcim.view_rack", "dcim.change_device")

    def post(self, request, rack_id):
        rack = Rack.objects.filter(pk=rack_id).first()
        if rack is None:
            return JsonResponse({"error": "Rack not found."}, status=404)

        device = get_rack_position_device(rack_id)
        if device is None:
            # Already has no device-based position -- nothing to do, not an error.
            return JsonResponse({"success": True, "rack_name": rack.name, "already_unplaced": True})

        device_name = device.name
        device.latitude = None
        device.longitude = None
        device.save()

        return JsonResponse({
            "success": True,
            "rack_name": rack.name,
            "device_name": device_name,
        })
