from django.urls import path

from . import views
from .hide_views import HideRackView, ShowRackView
from .bulk_views import HideRacksBulkView, ShowRacksBulkView

urlpatterns = [
    path("", views.MapView.as_view(), name="map"),
    path("connections/", views.ConnectionsView.as_view(), name="connections"),
    path("racks/<int:rack_id>/move/", views.MoveRackView.as_view(), name="move_rack"),
    path("racks/<int:rack_id>/unplace/", views.UnplaceRackView.as_view(), name="unplace_rack"),
    path("racks/<int:rack_id>/hide/", HideRackView.as_view(), name="hide_rack"),
    path("racks/<int:rack_id>/show/", ShowRackView.as_view(), name="show_rack"),
    path("racks/show-bulk/", ShowRacksBulkView.as_view(), name="show_racks_bulk"),
    path("racks/hide-bulk/", HideRacksBulkView.as_view(), name="hide_racks_bulk"),
]
