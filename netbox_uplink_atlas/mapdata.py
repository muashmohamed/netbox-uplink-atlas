"""
Collects everything the map needs, straight from NetBox. Read-only.

- Racks get coordinates from a device inside them (preferred roles first),
  otherwise from their site.
- A link is any cable whose A end and B end sit in different racks.
- A link is a "trunk" when both ends are rear ports (ODF to ODF fiber).
"""
from collections import defaultdict, deque

from dcim.models import Cable, CableTermination, Device, Rack
from netbox.plugins import get_plugin_config

PLUGIN = "netbox_uplink_atlas"

# Racks carrying this tag are left off the map (see hide_views.py).
HIDDEN_TAG_SLUG = "uplink-atlas-hidden"


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
    hidden = []
    hidden_ids = set(Rack.objects.filter(tags__slug=HIDDEN_TAG_SLUG).values_list("pk", flat=True))
    qs = Rack.objects.select_related("site", "location").order_by("site__name", "name")

    for rack in qs:
        if rack.pk in hidden_ids:
            hidden.append({"id": rack.pk, "name": rack.name, "url": rack.get_absolute_url()})
            continue
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
        "hidden": hidden,
        "stats": {
            "racks_total": len(placed) + len(unplaced),
            "racks_precise": sum(1 for r in placed if r["precise"]),
            "racks_site_only": sum(1 for r in placed if not r["precise"]),
            "racks_unplaced": len(unplaced),
            "racks_hidden": len(hidden),
            "links": len(links),
            "trunks": sum(1 for l in links if l["trunks"]),
            "links_hidden": hidden_links,
        },
    }


def get_rack_panel_data(rack_id, map_data):
    """
    Everything the 'rack panel' needs for one rack: its own info, plus every
    direct link (neighbor rack) it has, with cable/trunk counts.

    `map_data` is the dict already returned by build_map_data() — this
    function just filters/reshapes it, it doesn't touch NetBox directly.
    """
    rack = next((r for r in map_data["racks"] if r["id"] == rack_id), None)
    if rack is None:
        return None

    neighbors = []
    for link in map_data["links"]:
        other_id = None
        if link["a"] == rack_id:
            other_id = link["b"]
        elif link["b"] == rack_id:
            other_id = link["a"]
        if other_id is None:
            continue

        other_rack = next((r for r in map_data["racks"] if r["id"] == other_id), None)
        neighbors.append({
            "rack_id": other_id,
            "rack_name": other_rack["name"] if other_rack else f"Rack #{other_id}",
            "rack_url": other_rack["url"] if other_rack else "",
            "cable_count": link["count"],
            "trunk_count": link["trunks"],
            "cables": link["cables"],
        })

    # Most-connected neighbors first — usually what you want to see first
    # when looking at a rack's uplinks.
    neighbors.sort(key=lambda n: n["cable_count"], reverse=True)

    return {
        "rack": rack,
        "neighbors": neighbors,
        "neighbor_count": len(neighbors),
        "total_cables": sum(n["cable_count"] for n in neighbors),
        "total_trunks": sum(n["trunk_count"] for n in neighbors),
    }


def find_path(rack_a_id, rack_b_id, map_data):
    """
    Shortest path between two racks, hopping only along existing cable
    links (breadth-first search — finds the path with the fewest hops,
    not necessarily the shortest cable length).

    Returns a dict describing the path, or None if there's no path at all
    (the two racks aren't connected through any chain of cables).
    """
    if rack_a_id == rack_b_id:
        return {"racks": [rack_a_id], "hops": [], "hop_count": 0}

    # Build an adjacency list once: {rack_id: [(neighbor_id, link), ...]}
    adjacency = {}
    for link in map_data["links"]:
        adjacency.setdefault(link["a"], []).append((link["b"], link))
        adjacency.setdefault(link["b"], []).append((link["a"], link))

    if rack_a_id not in adjacency or rack_b_id not in adjacency:
        return None  # one of the racks has no cable links at all

    # Standard BFS, tracking how we got to each rack so we can rebuild the path.
    visited = {rack_a_id}
    came_from = {}  # rack_id -> (previous_rack_id, link_used)
    queue = deque([rack_a_id])

    while queue:
        current = queue.popleft()
        if current == rack_b_id:
            break
        for neighbor_id, link in adjacency.get(current, []):
            if neighbor_id not in visited:
                visited.add(neighbor_id)
                came_from[neighbor_id] = (current, link)
                queue.append(neighbor_id)

    if rack_b_id not in came_from and rack_a_id != rack_b_id:
        return None  # no path exists between these two racks

    # Walk backwards from B to A to rebuild the path, then reverse it.
    path_racks = [rack_b_id]
    path_links = []
    node = rack_b_id
    while node != rack_a_id:
        prev, link = came_from[node]
        path_links.append(link)
        path_racks.append(prev)
        node = prev
    path_racks.reverse()
    path_links.reverse()

    rack_lookup = {r["id"]: r for r in map_data["racks"]}
    return {
        "racks": [
            {"id": rid, "name": rack_lookup.get(rid, {}).get("name", f"Rack #{rid}")}
            for rid in path_racks
        ],
        "hops": path_links,
        "hop_count": len(path_links),
        "total_cables": sum(l["count"] for l in path_links),
    }
