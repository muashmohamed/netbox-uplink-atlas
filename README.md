# NetBox Uplink Atlas

A **read-only** NetBox plugin that places racks on an OpenStreetMap / satellite map
and draws the cables that run between racks (ODF-to-ODF fiber trunks), so you can
see where each uplink comes from.

It adds no database tables, needs no migrations, and never writes to NetBox.
Uninstalling it leaves no trace.

## Where the data comes from

| What | NetBox source |
|---|---|
| Rack position | Latitude/longitude of a device in the rack (ODF preferred), else the rack's site |
| Lines between racks | Cables whose two ends are in different racks |
| Fiber trunk | A cable with a rear port at both ends (ODF to ODF) |

## Roadmap

1. Map with racks and fiber lines *(this release)*
2. Rack panel, uplink trace and A-to-B path view
3. Status from built-in ping (PRTG optional), fault location
4. Data health page
5. VLAN tagging planner

## Settings (`configuration/plugins.py`)

```python
PLUGINS_CONFIG = {
    "netbox_uplink_atlas": {
        # Device role slugs whose GPS places the rack, in order of preference
        "gps_role_priority": ["odf"],
        # Map starting point if nothing has coordinates yet [lat, lon]
        "default_center": [4.1755, 73.5093],
        "default_zoom": 8,
    }
}
```

## License

Apache-2.0
