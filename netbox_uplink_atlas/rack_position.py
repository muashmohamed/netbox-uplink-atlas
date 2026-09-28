"""
Finds which Device should hold a rack's map position -- either the one
currently providing it (for Move/Unplace), or the best candidate to
receive a brand-new position (for Place, when the rack has none yet).

Returns None when there's genuinely no device to work with (the rack has
no devices at all) -- in that case there's nothing safe to place/move.
"""
from dcim.models import Device
from netbox.plugins import get_plugin_config

PLUGIN = "netbox_uplink_atlas"


def _rank_fn():
    priority = [s.lower() for s in get_plugin_config(PLUGIN, "gps_role_priority") or []]

    def rank(role_slug):
        slug = (role_slug or "").lower()
        return priority.index(slug) if slug in priority else len(priority)
    return rank


def get_rack_position_device(rack_id):
    """The Device CURRENTLY providing this rack's position (has coordinates
    set already). None if the rack isn't placed via a device (site-only or
    entirely unplaced)."""
    rank = _rank_fn()
    candidates = Device.objects.filter(
        rack_id=rack_id, latitude__isnull=False, longitude__isnull=False
    ).select_related("role")

    best, best_rank = None, None
    for d in candidates:
        r = rank(d.role.slug if d.role else None)
        if best is None or r < best_rank:
            best, best_rank = d, r
    return best


def get_best_device_for_rack(rack_id):
    """The best candidate Device in this rack to receive a NEW position,
    regardless of whether it already has coordinates -- used for Place,
    when the rack has no position yet at all. Prefers whichever device
    already provides the position (if any), otherwise the highest-priority
    device in the rack by role. None only if the rack has zero devices."""
    existing = get_rack_position_device(rack_id)
    if existing is not None:
        return existing

    rank = _rank_fn()
    candidates = Device.objects.filter(rack_id=rack_id).select_related("role")

    best, best_rank = None, None
    for d in candidates:
        r = rank(d.role.slug if d.role else None)
        if best is None or r < best_rank:
            best, best_rank = d, r
    return best
