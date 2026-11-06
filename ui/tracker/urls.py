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
    path("items/<int:pk>/add-to-comparison/", views.item_add_to_comparison, name="item-add-to-comparison"),
    path("comparisons/", views.comparison_list, name="comparison-list"),
    path("comparisons/add/", views.comparison_create, name="comparison-create"),
    path("comparisons/<int:pk>/", views.comparison_detail, name="comparison-detail"),
    path("comparisons/<int:pk>/edit/", views.comparison_update, name="comparison-update"),
    path("comparisons/<int:pk>/delete/", views.comparison_delete, name="comparison-delete"),
    path("settings/", views.settings_view, name="settings"),
]
