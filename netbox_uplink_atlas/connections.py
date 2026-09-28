"""
Collects switch/interface connection data for the Connections page.
Read-only, same as mapdata.py -- no new models, no writes to NetBox.

Deliberately does NOT reimplement cable tracing. NetBox's own trace view
already correctly handles front/rear ports, circuits, and multi-segment
paths -- this module just lists switches and their interfaces, with a
direct link into that existing, proven trace view for the full diagram.
"""
from django.urls import reverse

from dcim.models import Device, Interface
from netbox.plugins import get_plugin_config

PLUGIN = "netbox_uplink_atlas"

# Sensible defaults matching common NetBox Device Role slugs for switches.
# Override via PLUGINS_CONFIG["netbox_uplink_atlas"]["switch_role_slugs"].
DEFAULT_SWITCH_ROLE_SLUGS = [
    "access-layer-switch",
    "access-switch",
    "core-switch",
    "distribution-switch",
    "edge-switch",
    "hosting-switch",
]


def build_connections_data():
    role_slugs = get_plugin_config(PLUGIN, "switch_role_slugs") or DEFAULT_SWITCH_ROLE_SLUGS

    switches = (
        Device.objects.filter(role__slug__in=role_slugs)
        .select_related("role", "site", "location", "rack")
        .order_by("site__name", "name")
    )

    switch_ids = [d.pk for d in switches]
    interfaces = (
        Interface.objects.filter(device_id__in=switch_ids)
        .select_related("cable")
        .order_by("device_id", "name")
    )

    interfaces_by_device = {}
    for iface in interfaces:
        interfaces_by_device.setdefault(iface.device_id, []).append(iface)

    result = []
    for switch in switches:
        iface_rows = []
        for iface in interfaces_by_device.get(switch.pk, []):
            cable = iface.cable
            trace_url = None
            try:
                trace_url = reverse("dcim:interface_trace", kwargs={"pk": iface.pk})
            except Exception:
                trace_url = None  # fall back gracefully if the URL name ever changes

            iface_rows.append({
                "id": iface.pk,
                "name": iface.name,
                "type": iface.get_type_display() if iface.type else "",
                "enabled": iface.enabled,
                "url": iface.get_absolute_url(),
                "trace_url": trace_url,
                "has_cable": cable is not None,
                "cable_label": (cable.label or f"Cable #{cable.pk}") if cable else None,
                "cable_status": cable.get_status_display() if cable else None,
                "cable_url": cable.get_absolute_url() if cable else None,
            })

        result.append({
            "id": switch.pk,
            "name": switch.name,
            "url": switch.get_absolute_url(),
            "role": switch.role.name if switch.role else "",
            "site": switch.site.name if switch.site else "",
            "location": switch.location.name if switch.location else "",
            "rack": switch.rack.name if switch.rack else "",
            "interfaces": iface_rows,
            "interface_count": len(iface_rows),
            "connected_count": sum(1 for r in iface_rows if r["has_cable"]),
        })

    return {
        "switches": result,
        "stats": {
            "switch_count": len(result),
            "interface_count": sum(s["interface_count"] for s in result),
            "connected_count": sum(s["connected_count"] for s in result),
        },
    }
