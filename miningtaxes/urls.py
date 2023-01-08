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
        "char_mining_ledger_data/<int:character_pk>/",
        views.char_mining_ledger_data,
        name="character_mining_ledger_data",
    ),
    path(
        "user_mining_ledger_90day/<int:user_pk>",
        views.user_mining_ledger_90day,
        name="user_mining_ledger_90day",
    ),
    path("user_summary/<int:user_pk>", views.user_summary, name="user_summary"),
    path(
        "summary_month_json/<int:user_pk>",
        views.summary_month_json,
        name="summary_month_json",
    ),
    path(
        "all_tax_credits/<int:user_pk>",
        views.all_tax_credits,
        name="all_tax_credits",
    ),
    path("faq", views.faq, name="faq"),
    path("ore_prices", views.ore_prices, name="ore_prices"),
    path("ore_prices_json", views.ore_prices_json, name="ore_prices_json"),
    path("leaderboards", views.leaderboards, name="leaderboards"),
    path("admin/", views.admin_launcher, name="admin_launcher"),
    path("admin/tables", views.admin_tables, name="admin_tables"),
    path("admin_main_json", views.admin_main_json, name="admin_main_json"),
    path("admin_char_json", views.admin_char_json, name="admin_char_json"),
    path(
        "admin_mining_by_sys_json",
        views.admin_mining_by_sys_json,
        name="admin_mining_by_sys_json",
    ),
    path(
        "admin_tax_revenue_json",
        views.admin_tax_revenue_json,
        name="admin_tax_revenue_json",
    ),
    path("admin_month_json", views.admin_month_json, name="admin_month_json"),
    path(
        "admin_corp_mining_history",
        views.admin_corp_mining_history,
        name="admin_corp_mining_history",
    ),
    path("admin_corp_ledger", views.admin_corp_ledger, name="admin_corp_ledger"),
]
