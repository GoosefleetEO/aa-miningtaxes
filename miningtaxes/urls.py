from django.urls import path

from . import views

app_name = "miningtaxes"

urlpatterns = [
    path("", views.index, name="index"),
    path("launcher", views.launcher, name="launcher"),
    path("add_character", views.add_character, name="add_character"),
    path("add_admin_character", views.add_admin_character, name="add_admin_character"),
    path(
        "remove_character/<int:character_pk>/",
        views.remove_character,
        name="remove_character",
    ),
    path(
        "remove_admin_character/<int:character_pk>/",
        views.remove_admin_character,
        name="remove_admin_character",
    ),
    path(
        "character_viewer/<int:character_pk>/",
        views.character_viewer,
        name="character_viewer",
    ),
    path(
        "character_mining_ledger_data/<int:character_pk>/",
        views.character_mining_ledger_data,
        name="character_mining_ledger_data",
    ),
    path("admin/", views.admin_launcher, name="admin_launcher"),
]
