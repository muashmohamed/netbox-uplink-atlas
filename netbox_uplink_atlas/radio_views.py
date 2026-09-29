"""
Move a wireless radio (a device with no rack and a wireless link) from the map.
Writes the device's own latitude/longitude. Requires dcim.change_device.
"""
import json
from decimal import Decimal

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.views import View

from dcim.models import Device


class MoveRadioView(PermissionRequiredMixin, View):
    permission_required = ("dcim.view_device", "dcim.change_device")

    def post(self, request, device_id):
        try:
            body = json.loads(request.body or b"{}")
            lat = float(body["lat"])
            lon = float(body["lon"])
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({"error": "Invalid request -- expected JSON with lat/lon."}, status=400)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return JsonResponse({"error": "Coordinates out of valid range."}, status=400)

        device = Device.objects.filter(pk=device_id).first()
        if device is None:
            return JsonResponse({"error": "Device not found."}, status=404)
        if device.rack_id is not None:
            return JsonResponse({
                "error": (
                    "This device is inside a rack, and its position may also place that rack "
                    "on the map. Move the rack instead."
                )
            }, status=400)

        from wireless.models import WirelessLink

        if not WirelessLink.objects.filter(Q(interface_a__device=device) | Q(interface_b__device=device)).exists():
            return JsonResponse({"error": "This device has no wireless link, so it is not a radio on the map."}, status=400)

        device.latitude = Decimal(f"{lat:.6f}")
        device.longitude = Decimal(f"{lon:.6f}")
        device.save()
        return JsonResponse({"success": True, "device_name": device.name, "lat": lat, "lon": lon})


class HideRadioView(PermissionRequiredMixin, View):
    """Hides a radio the same way a rack is hidden: adds the shared hidden tag
    to the device. No coordinates are touched."""

    permission_required = ("dcim.view_device", "dcim.change_device")

    def post(self, request, device_id):
        from extras.models import Tag

        from .hide_views import HIDDEN_TAG_NAME
        from .mapdata import HIDDEN_TAG_SLUG

        device = Device.objects.filter(pk=device_id).first()
        if device is None:
            return JsonResponse({"error": "Device not found."}, status=404)

        tag = Tag.objects.filter(slug=HIDDEN_TAG_SLUG).first()
        if tag is None:
            if not request.user.has_perm("extras.add_tag"):
                return JsonResponse({
                    "error": (
                        f'The tag "{HIDDEN_TAG_NAME}" does not exist yet and you do not have '
                        "permission to create tags. Ask an administrator to hide the first item."
                    )
                }, status=403)
            tag = Tag.objects.create(slug=HIDDEN_TAG_SLUG, name=HIDDEN_TAG_NAME, color="9e9e9e")

        device.tags.add(tag)
        for peer in _wireless_peers(device):
            peer.tags.add(tag)
        return JsonResponse({"success": True, "device_name": device.name})


class ShowRadioView(PermissionRequiredMixin, View):
    """Un-hides a radio. Idempotent -- showing an already-visible radio is a no-op."""

    permission_required = ("dcim.view_device", "dcim.change_device")

    def post(self, request, device_id):
        from extras.models import Tag

        from .mapdata import HIDDEN_TAG_SLUG

        device = Device.objects.filter(pk=device_id).first()
        if device is None:
            return JsonResponse({"error": "Device not found."}, status=404)

        tag = Tag.objects.filter(slug=HIDDEN_TAG_SLUG).first()
        if tag is not None:
            device.tags.remove(tag)
            for peer in _wireless_peers(device):
                peer.tags.remove(tag)
        return JsonResponse({"success": True, "device_name": device.name})


def _wireless_peers(device):
    """Every device on the other end of one of this device's wireless links."""
    from django.db.models import Q

    from wireless.models import WirelessLink

    peers = []
    for link in WirelessLink.objects.filter(
        Q(interface_a__device=device) | Q(interface_b__device=device)
    ).select_related("interface_a__device", "interface_b__device"):
        other = link.interface_b.device if link.interface_a.device_id == device.pk else link.interface_a.device
        if other.pk != device.pk:
            peers.append(other)
    return peers
