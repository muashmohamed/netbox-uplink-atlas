"""
Device-to-device path finder, reusing NetBox's own cable-path resolution
so passive patch panels / ODFs are automatically skipped -- same engine
that powers the native Trace view, just applied device-to-device instead
of needing to already know a starting interface.

Read-only. Test this against real data via Django shell BEFORE wiring it
into any view -- the exact attribute name for "fully resolved far end"
has changed across NetBox versions, so this needs a real check first.
"""
from collections import deque

from django.urls import reverse

from dcim.models import Device, Interface


def get_connected_device_choices(graph):
    """(id, name) pairs for every device that has at least one resolved
    connection, sorted by name -- for populating the path-finder dropdowns."""
    devices = Device.objects.filter(pk__in=graph.keys()).only("id", "name").order_by("name")
    return [(d.id, d.name) for d in devices]


def build_device_link_graph(device_ids=None):
    """
    Returns {device_id: [(other_device_id, this_iface, other_iface), ...]}
    using each interface's fully-resolved connected endpoint -- i.e. the
    real active device at the far end, with any passive patch panels/ODFs
    in between already skipped by NetBox's own path resolution.
    """
    qs = Interface.objects.filter(cable__isnull=False).select_related("device")
    if device_ids is not None:
        qs = qs.filter(device_id__in=device_ids)

    graph = {}
    skipped_no_attr = 0
    skipped_inactive = 0
    skipped_not_interface = 0

    for iface in qs:
        endpoints = getattr(iface, "connected_endpoints", None)
        if endpoints is None:
            skipped_no_attr += 1
            continue

        path = getattr(iface, "_path", None)
        if path is not None and not getattr(path, "is_active", True):
            skipped_inactive += 1
            continue

        for endpoint in endpoints:
            if not isinstance(endpoint, Interface):
                skipped_not_interface += 1
                continue
            other_device_id = endpoint.device_id
            if other_device_id == iface.device_id:
                continue  # a loopback/internal connection, not a real hop

            graph.setdefault(iface.device_id, []).append((other_device_id, iface, endpoint))

    return graph, {
        "skipped_no_connected_endpoints_attr": skipped_no_attr,
        "skipped_inactive_path": skipped_inactive,
        "skipped_endpoint_not_interface": skipped_not_interface,
    }


def find_device_path(device_a_id, device_b_id, graph):
    """
    Shortest path (fewest hops) between two devices, walking only fully
    resolved active connections (passives already skipped by the graph).
    Returns a dict with the hop-by-hop interface pairs, or None if no path.
    """
    if device_a_id == device_b_id:
        return {"device_ids": [device_a_id], "hops": [], "hop_count": 0}

    if device_a_id not in graph or device_b_id not in graph:
        return None

    visited = {device_a_id}
    came_from = {}
    queue = deque([device_a_id])

    while queue:
        current = queue.popleft()
        if current == device_b_id:
            break
        for other_id, this_iface, other_iface in graph.get(current, []):
            if other_id not in visited:
                visited.add(other_id)
                came_from[other_id] = (current, this_iface, other_iface)
                queue.append(other_id)

    if device_b_id not in came_from:
        return None

    device_ids = [device_b_id]
    hops = []
    node = device_b_id
    while node != device_a_id:
        prev, this_iface, other_iface = came_from[node]
        # this_iface belongs to `prev`, other_iface belongs to `node`
        hops.append({
            "from_device_id": prev,
            "from_device_name": this_iface.device.name,
            "from_interface": this_iface.name,
            "to_device_id": node,
            "to_device_name": other_iface.device.name,
            "to_interface": other_iface.name,
            "trace_url": _safe_trace_url(this_iface),
        })
        device_ids.append(prev)
        node = prev
    device_ids.reverse()
    hops.reverse()

    return {"device_ids": device_ids, "hops": hops, "hop_count": len(hops)}


def _safe_trace_url(interface):
    try:
        return reverse("dcim:interface_trace", kwargs={"pk": interface.pk})
    except Exception:
        return None
