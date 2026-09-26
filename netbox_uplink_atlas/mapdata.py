"""
Collects everything the map needs, straight from NetBox. Read-only.

- Racks get coordinates from a device inside them (preferred roles first),
  otherwise from their site.
- A link is any cable whose A end and B end sit in different racks.
- A link is a "trunk" when both ends are rear ports (ODF to ODF fiber).
"""
from collections import defaultdict
from collections import deque

from dcim.models import Cable, CableTermination, Device, Rack
from netbox.plugins import get_plugin_config

PLUGIN = "netbox_uplink_atlas"


def _rack_coordinates():
    """Return {rack_id: (lat, lon, source)} using device GPS by role priority."""
    priority = [s.lower() for s in get_plugin_config(PLUGIN, "gps_role_priority") or []]

    def rank(role_slug):
        slug = (role_slug or "").lower()
        return priority.index(slug) if slug in priority else len(priority)

    best = {}
    rows = (
        Device.objects.filter(
            rack__isnull=False, latitude__isnull=False, longitude__isnull=False
        )
        .values("rack_id", "latitude", "longitude", "role__slug", "name")
        .order_by("rack_id", "name")
    )
    for row in rows:
        r = rank(row["role__slug"])
        current = best.get(row["rack_id"])
        if current is None or r < current[0]:
            best[row["rack_id"]] = (
                r,
                float(row["latitude"]),
                float(row["longitude"]),
                row["name"],
            )
    return {rid: (lat, lon, f"device:{name}") for rid, (_, lat, lon, name) in best.items()}


def build_map_data():
    device_gps = _rack_coordinates()

    racks = {}
    unplaced = []
    qs = Rack.objects.select_related("site", "location").order_by("site__name", "name")

    for rack in qs:
        if rack.pk in device_gps:
            lat, lon, source = device_gps[rack.pk]
            precise = True
        elif rack.site and rack.site.latitude is not None and rack.site.longitude is not None:
            lat, lon = float(rack.site.latitude), float(rack.site.longitude)
            source, precise = "site", False
        else:
            unplaced.append({"id": rack.pk, "name": rack.name, "url": rack.get_absolute_url()})
            continue

        racks[rack.pk] = {
            "id": rack.pk,
            "name": rack.name,
            "url": rack.get_absolute_url(),
            "site": rack.site.name if rack.site else "",
            "location": rack.location.name if rack.location else "",
            "lat": lat,
            "lon": lon,
            "precise": precise,
            "source": source,
        }

    # Group cable ends by cable: {cable_id: {"A": {rack ids}, "B": {...}, types: set}}
    ends = defaultdict(lambda: {"A": set(), "B": set(), "types": set()})
    terms = CableTermination.objects.filter(_rack__isnull=False).values(
        "cable_id", "cable_end", "_rack_id", "termination_type__model"
    )
    for t in terms:
        e = ends[t["cable_id"]]
        e[t["cable_end"]].add(t["_rack_id"])
        e["types"].add(t["termination_type__model"])

    pairs = defaultdict(lambda: {"cables": [], "trunks": 0})
    for cable_id, e in ends.items():
        if not e["A"] or not e["B"]:
            continue
        a, b = min(e["A"]), min(e["B"])
        if a == b:
            continue  # both ends in the same rack: not an uplink
        key = tuple(sorted((a, b)))
        is_trunk = e["types"] == {"rearport"}
        pairs[key]["cables"].append((cable_id, is_trunk))
        if is_trunk:
            pairs[key]["trunks"] += 1

    cable_ids = [cid for p in pairs.values() for cid, _ in p["cables"]]
    cable_info = {
        c.pk: c
        for c in Cable.objects.filter(pk__in=cable_ids).only(
            "id", "label", "type", "status", "length", "length_unit"
        )
    }

    links = []
    hidden_links = 0
    for (a, b), p in pairs.items():
        if a not in racks or b not in racks:
            hidden_links += 1
            continue
        cables = []
        for cid, is_trunk in p["cables"]:
            c = cable_info.get(cid)
            if c is None:
                continue
            length = f"{c.length:g} {c.length_unit}" if c.length is not None and c.length_unit else ""
            cables.append({
                "id": cid,
                "label": c.label or f"Cable #{cid}",
                "url": c.get_absolute_url(),
                "type": c.get_type_display() if c.type else "",
                "status": c.status,
                "length": length,
                "trunk": is_trunk,
            })
        links.append({
            "a": a,
            "b": b,
            "trunks": p["trunks"],
            "count": len(cables),
            "cables": cables,
        })

    placed = list(racks.values())
    return {
        "racks": placed,
        "links": links,
        "unplaced": unplaced,
        "stats": {
            "racks_total": len(placed) + len(unplaced),
            "racks_precise": sum(1 for r in placed if r["precise"]),
            "racks_site_only": sum(1 for r in placed if not r["precise"]),
            "racks_unplaced": len(unplaced),
            "links": len(links),
            "trunks": sum(1 for l in links if l["trunks"]),
            "links_hidden": hidden_links,
        },
    }
