"""
Bulk "Show" for hidden racks: removes the hidden tag from several racks in one
request. POST {"rack_ids": [1, 2, 3]} or {"all": true}. Idempotent.
"""
import json

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import JsonResponse
from django.views import View

from dcim.models import Rack
from extras.models import Tag

from .hide_views import HIDDEN_TAG_NAME
from .mapdata import HIDDEN_TAG_SLUG


class ShowRacksBulkView(PermissionRequiredMixin, View):
    permission_required = ("dcim.view_rack", "dcim.change_rack")

    def post(self, request):
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid request body."}, status=400)
        if not isinstance(body, dict):
            return JsonResponse({"error": "Invalid request body."}, status=400)

        tag = Tag.objects.filter(slug=HIDDEN_TAG_SLUG).first()
        if tag is None:
            return JsonResponse({"success": True, "shown": 0})

        racks = Rack.objects.filter(tags=tag)
        if not body.get("all"):
            try:
                ids = [int(i) for i in body.get("rack_ids", [])]
            except (TypeError, ValueError):
                return JsonResponse({"error": "rack_ids must be a list of numbers."}, status=400)
            racks = racks.filter(pk__in=ids)

        shown = 0
        for rack in list(racks):
            rack.tags.remove(tag)
            shown += 1
        return JsonResponse({"success": True, "shown": shown})


class HideRacksBulkView(PermissionRequiredMixin, View):
    """POST {"rack_ids": [1, 2, 3]}: hide several racks at once. Idempotent."""

    permission_required = ("dcim.view_rack", "dcim.change_rack")
    MAX_RACKS = 500

    def post(self, request):
        try:
            body = json.loads(request.body or b"{}")
            ids = [int(i) for i in body.get("rack_ids", [])]
        except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
            return JsonResponse({"error": "rack_ids must be a list of numbers."}, status=400)
        if not ids:
            return JsonResponse({"error": "No racks selected."}, status=400)
        if len(ids) > self.MAX_RACKS:
            return JsonResponse({"error": f"Too many racks at once (limit {self.MAX_RACKS})."}, status=400)

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

        hidden = 0
        for rack in list(Rack.objects.filter(pk__in=ids)):
            rack.tags.add(tag)
            hidden += 1
        return JsonResponse({"success": True, "hidden": hidden})
