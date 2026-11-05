from django.urls import path

from tracker import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("items/", views.item_list, name="item-list"),
    path("items/add/", views.item_create, name="item-create"),
    path("items/add-link/", views.item_add_link, name="item-add-link"),
    path("items/<int:pk>/", views.item_detail, name="item-detail"),
    path("items/<int:pk>/check/", views.item_check, name="item-check"),
    path("items/<int:pk>/edit/", views.item_update, name="item-update"),
    path("comparisons/", views.comparison_list, name="comparison-list"),
    path("comparisons/add/", views.comparison_create, name="comparison-create"),
    path("comparisons/<int:pk>/", views.comparison_detail, name="comparison-detail"),
    path("settings/", views.settings_view, name="settings"),
]
