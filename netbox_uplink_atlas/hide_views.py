"""
Hide / Show a rack on the Uplink Atlas map.

Hiding does NOT touch any coordinates. It adds a tag (slug
"uplink-atlas-hidden") to the Rack record, and the map simply skips racks
carrying that tag. Showing removes the tag again. Because it is an ordinary
NetBox tag, the hidden status is also visible (and removable) on the rack's
own page in NetBox, and the plugin still needs no database tables.
"""
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import JsonResponse
from django.views import View

from dcim.models import Rack
from extras.models import Tag

from .mapdata import HIDDEN_TAG_SLUG

HIDDEN_TAG_NAME = "Uplink Atlas: hidden"


class HideRackView(PermissionRequiredMixin, View):
    permission_required = ("dcim.view_rack", "dcim.change_rack")

    def post(self, request, rack_id):
        rack = Rack.objects.filter(pk=rack_id).first()
        if rack is None:
            return JsonResponse({"error": "Rack not found."}, status=404)

        tag = Tag.objects.filter(slug=HIDDEN_TAG_SLUG).first()
        if tag is None:
            # Creating the tag is a separate permission in NetBox, so respect it.
            if not request.user.has_perm("extras.add_tag"):
                return JsonResponse({
                    "error": (
                        f'The tag "{HIDDEN_TAG_NAME}" does not exist yet and you do not have '
                        "permission to create tags. Ask an administrator to hide the first rack."
                    )
                }, status=403)
            tag = Tag.objects.create(slug=HIDDEN_TAG_SLUG, name=HIDDEN_TAG_NAME, color="9e9e9e")

        rack.tags.add(tag)
        return JsonResponse({"success": True, "rack_name": rack.name})


class ShowRackView(PermissionRequiredMixin, View):
    """Un-hide a rack. Idempotent -- showing an already-visible rack is a no-op."""

    permission_required = ("dcim.view_rack", "dcim.change_rack")

    def post(self, request, rack_id):
        rack = Rack.objects.filter(pk=rack_id).first()
        if rack is None:
            return JsonResponse({"error": "Rack not found."}, status=404)

        tag = Tag.objects.filter(slug=HIDDEN_TAG_SLUG).first()
        if tag is not None:
            rack.tags.remove(tag)
        return JsonResponse({"success": True, "rack_name": rack.name})
