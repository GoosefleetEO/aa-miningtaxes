import datetime as dt

from dateutil.relativedelta import relativedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.db import transaction
from django.http import (
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseNotFound,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.timezone import now
from esi.decorators import token_required

from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.helpers import humanize_number
from app_utils.logging import LoggerAddTag
from app_utils.views import bootstrap_icon_plus_name_html

from . import __title__, tasks
from .decorators import fetch_character_if_allowed
from .forms import SettingsForm
from .models import AdminCharacter, Character, Settings

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


@login_required
@permission_required("miningtaxes.admin_access")
def admin_launcher(request):
    settings = Settings.load()
    if request.method == "POST":
        form = SettingsForm(request.POST)
        if form.is_valid():
            form = SettingsForm(request.POST, instance=settings)
            form.save()
            messages.success(
                request,
                format_html("Changes saved!"),
            )
    else:
        form = SettingsForm(instance=settings)

    admin_query = AdminCharacter.objects.all()
    auth_characters = list()
    for a_character in admin_query:
        eve_character = a_character.eve_character
        auth_characters.append(
            {
                "character_id": eve_character.character_id,
                "character_name": eve_character.character_name,
                "character": a_character,
                "alliance_id": eve_character.alliance_id,
                "alliance_name": eve_character.alliance_name,
                "corporation_id": eve_character.corporation_id,
                "corporation_name": eve_character.corporation_name,
            }
        )

    context = {
        "page_title": "Admin Settings",
        "auth_characters": auth_characters,
        "has_registered_characters": len(auth_characters) > 0,
        "form": form,
    }
    return render(request, "miningtaxes/admin_launcher.html", context)


@login_required
@permission_required("miningtaxes.admin_access")
def admin_char_json(request):
    char_level = {}

    for char in Character.objects.all():
        char_level[char] = {
            "life_tax": char.get_lifetime_taxes(),
            "life_credits": char.get_lifetime_credits(),
        }
        char_level[char]["bal"] = (
            char_level[char]["life_tax"] - char_level[char]["life_credits"]
        )

    char_data = []
    for c in char_level.keys():
        char_data.append(
            {
                "name": bootstrap_icon_plus_name_html(
                    icon_url=c.eve_character.portrait_url(),
                    name=c.eve_character.character_name,
                    size=16,
                ),
                "corp": bootstrap_icon_plus_name_html(
                    icon_url=c.eve_character.corporation_logo_url(),
                    name=c.eve_character.corporation_name,
                    size=16,
                ),
                "main_name": bootstrap_icon_plus_name_html(
                    icon_url=c.main_character.portrait_url(),
                    name=c.main_character.character_name,
                    size=16,
                ),
                "taxes": char_level[c]["life_tax"],
                "credits": char_level[c]["life_credits"],
                "balance": char_level[c]["bal"],
            }
        )

    return JsonResponse({"data": char_data})


def main_data_helper(chars):
    main_level = {}
    last_paid = None
    char2user = {}

    for char in chars:
        m = char.main_character
        char2user[m] = char.user.pk
        if m not in main_level:
            main_level[m] = {"life_tax": 0.0, "life_credits": 0.0}
        main_level[m]["life_tax"] += char.get_lifetime_taxes()
        main_level[m]["life_credits"] += char.get_lifetime_credits()
        if char.last_paid() is not None and (
            last_paid is None or char.last_paid() > last_paid
        ):
            last_paid = char.last_paid()
    for m in main_level.keys():
        main_level[m]["balance"] = (
            main_level[m]["life_tax"] - main_level[m]["life_credits"]
        )
    return main_level, last_paid, char2user


@login_required
@permission_required("miningtaxes.admin_access")
def admin_main_json(request):
    main_level, last_paid, char2user = main_data_helper(Character.objects.all())
    main_data = []
    for i, m in enumerate(main_level.keys()):
        summary_url = reverse("miningtaxes:user_summary", args=[char2user[m]])
        action_html = (
            '<a class="btn btn-primary btn-sm" '
            f"href='{summary_url}'>"
            '<i class="fas fa-search"></i></a>'
            '<button type="button" class="btn btn-primary btn-sm" '
            'data-toggle="modal" data-target="#modalCredit" '
            f'onClick="populate({i})" >'
            "$$</button>"
        )
        main_data.append(
            {
                "name": bootstrap_icon_plus_name_html(
                    icon_url=m.portrait_url(), name=m.character_name, size=16
                ),
                "corp": bootstrap_icon_plus_name_html(
                    icon_url=m.corporation_logo_url(), name=m.corporation_name, size=16
                ),
                "balance": main_level[m]["balance"],
                "last_paid": last_paid,
                "action": action_html,
                "user": char2user[m],
            }
        )
    return JsonResponse({"data": main_data})


@login_required
@permission_required("miningtaxes.admin_access")
def admin_tables(request):
    if request.method == "POST":
        isk = request.POST["creditbox"].replace(",", "")
        try:
            isk = float(isk)
        except ValueError:
            isk = None
            pass
        if isk is None:
            messages.warning(
                request,
                format_html("Invalid amount. Please enter a valid number"),
            )
        else:
            user = User.objects.get(pk=int(request.POST["userid"]))
            characters = Character.objects.owned_by_user(user)
            suitable = None
            for c in characters:
                if c.is_main:
                    suitable = c
                    break
                suitable = c
            suitable.give_credit(isk)
            messages.warning(
                request,
                format_html("Tax credit given!"),
            )

    context = {
        "page_title": "Admin Tables",
    }
    return render(request, "miningtaxes/admin_tables.html", context)


@login_required
@permission_required("miningtaxes.basic_access")
def index(request):
    characters = Character.objects.owned_by_user(request.user)
    if len(characters) == 0:
        return redirect("miningtaxes:launcher")
    return redirect("miningtaxes:user_summary", request.user.pk)


@login_required
@permission_required("miningtaxes.basic_access")
def user_summary(request, user_pk: int):
    user = User.objects.get(pk=user_pk)
    owned_chars_query = (
        EveCharacter.objects.filter(character_ownership__user=user)
        .select_related(
            "miningtaxes_character",
        )
        .order_by("character_name")
    )
    auth_characters = list()
    unregistered_chars = list()
    for eve_character in owned_chars_query:
        try:
            character = eve_character.miningtaxes_character
        except AttributeError:
            unregistered_chars.append(eve_character.character_name)
        else:
            auth_characters.append(character)
    unregistered_chars = sorted(unregistered_chars)
    main_character_id = request.user.profile.main_character.character_id
    main_data, last_paid, _ = main_data_helper(auth_characters)
    context = {
        "page_title": "Taxes Summary",
        "auth_characters": auth_characters,
        "unregistered_chars": unregistered_chars,
        "main_character_id": main_character_id,
        "balance": humanize_number(main_data[list(main_data.keys())[0]]["balance"]),
        "balance_raw": "{:,}".format(main_data[list(main_data.keys())[0]]["balance"]),
        "last_paid": last_paid,
        "user_pk": user_pk,
    }
    return render(request, "miningtaxes/user_summary.html", context)


@login_required
@permission_required("miningtaxes.basic_access")
def summary_month_json(request, user_pk: int):
    user = User.objects.get(pk=user_pk)
    characters = Character.objects.owned_by_user(user)
    monthly = list(map(lambda x: x.get_monthly_taxes(), characters))
    firstmonth = None
    for entries in monthly:
        if len(entries.keys()) == 0:
            continue
        if firstmonth is None or firstmonth > sorted(entries.keys())[0]:
            firstmonth = sorted(entries.keys())[0]
    xs = None
    ys = []
    for i, entries in enumerate(monthly):
        y = [characters[i].name]
        x = ["x"]
        curmonth = firstmonth
        lastmonth = dt.date(now().year, now().month, 1)
        while curmonth <= lastmonth:
            if curmonth not in entries:
                entries[curmonth] = 0.0
            x.append(curmonth)
            curmonth += relativedelta(months=1)

        if xs is None:
            xs = x

        for i in range(1, len(xs)):
            y.append(entries[xs[i]])
        ys.append(y)
    return JsonResponse({"xdata": xs, "ydata": ys})


@login_required
@permission_required("miningtaxes.basic_access")
def all_tax_credits(request, user_pk: int):
    user = User.objects.get(pk=user_pk)
    characters = Character.objects.owned_by_user(user)
    allcredits = []
    for c in characters:
        allcredits += map(
            lambda x: {
                "date": x.date,
                "character": bootstrap_icon_plus_name_html(
                    icon_url=c.eve_character.portrait_url(),
                    name=c.eve_character.character_name,
                    size=16,
                ),
                "amount": x.credit,
            },
            c.tax_credits.all(),
        )

    return JsonResponse({"data": allcredits})


@login_required
@permission_required("miningtaxes.basic_access")
def leaderboards(request):
    characters = Character.objects.all()
    allentries = list(map(lambda x: x.get_monthly_mining(), characters))
    combined = {}
    for i, entries in enumerate(allentries):
        c = characters[i].main_character
        for m in entries.keys():
            if m not in combined:
                combined[m] = {}
            if c.character_name not in combined[m]:
                combined[m][c.character_name] = 0.0
            combined[m][c.character_name] += entries[m]
    output = []
    for m in sorted(combined.keys()):
        users = sorted(combined[m], key=lambda x: -combined[m][x])
        table = []
        for i, u in enumerate(users):
            table.append({"rank": i + 1, "character": u, "amount": combined[m][u]})
        output.append({"month": m, "table": table})

    return JsonResponse({"data": output})


@login_required
@permission_required("miningtaxes.basic_access")
def launcher(request) -> HttpResponse:
    owned_chars_query = (
        EveCharacter.objects.filter(character_ownership__user=request.user)
        .select_related(
            "miningtaxes_character",
        )
        .order_by("character_name")
    )
    has_auth_characters = owned_chars_query.exists()
    auth_characters = list()
    unregistered_chars = list()
    for eve_character in owned_chars_query:
        try:
            character = eve_character.miningtaxes_character
        except AttributeError:
            unregistered_chars.append(eve_character.character_name)
        else:
            auth_characters.append(
                {
                    "character_id": eve_character.character_id,
                    "character_name": eve_character.character_name,
                    "character": character,
                    "alliance_id": eve_character.alliance_id,
                    "alliance_name": eve_character.alliance_name,
                    "corporation_id": eve_character.corporation_id,
                    "corporation_name": eve_character.corporation_name,
                }
            )

    unregistered_chars = sorted(unregistered_chars)

    try:
        main_character_id = request.user.profile.main_character.character_id
    except AttributeError:
        main_character_id = None

    context = {
        "page_title": "My Characters",
        "auth_characters": auth_characters,
        "has_auth_characters": has_auth_characters,
        "unregistered_chars": unregistered_chars,
        "has_registered_characters": len(auth_characters) > 0,
        "main_character_id": main_character_id,
    }

    """
    if has_auth_characters:
        messages.warning(
            request,
            format_html(
                "Please register all your characters. "
                "You currently have <strong>{}</strong> unregistered characters.",
                unregistered_chars,
            ),
        )
    """
    return render(request, "miningtaxes/launcher.html", context)


@login_required
@permission_required("miningtaxes.admin_access")
@token_required(scopes=AdminCharacter.get_esi_scopes())
def add_admin_character(request, token) -> HttpResponse:
    eve_character = get_object_or_404(EveCharacter, character_id=token.character_id)
    with transaction.atomic():
        character, _ = AdminCharacter.objects.update_or_create(
            eve_character=eve_character
        )
    tasks.update_admin_character.delay(character_pk=character.pk)
    messages.success(
        request,
        format_html(
            "<strong>{}</strong> has been registered. "
            "Note that it can take a minute until all character data is visible.",
            eve_character,
        ),
    )
    return redirect("miningtaxes:admin_launcher")


@login_required
@permission_required("miningtaxes.basic_access")
@token_required(scopes=Character.get_esi_scopes())
def add_character(request, token) -> HttpResponse:
    eve_character = get_object_or_404(EveCharacter, character_id=token.character_id)
    with transaction.atomic():
        character, _ = Character.objects.update_or_create(eve_character=eve_character)
    tasks.update_character.delay(character_pk=character.pk)
    messages.success(
        request,
        format_html(
            "<strong>{}</strong> has been registered. "
            "Note that it can take a minute until all character data is visible.",
            eve_character,
        ),
    )
    return redirect("miningtaxes:launcher")


@login_required
@permission_required("miningtaxes.admin_access")
def remove_admin_character(request, character_pk: int) -> HttpResponse:
    try:
        character = AdminCharacter.objects.select_related(
            "eve_character__character_ownership__user", "eve_character"
        ).get(pk=character_pk)
    except Character.DoesNotExist:
        return HttpResponseNotFound(f"Character with pk {character_pk} not found")
    if character.user and character.user == request.user:
        character_name = character.eve_character.character_name

        character.delete()
        messages.success(
            request,
            format_html(
                "Removed character <strong>{}</strong> as requested.", character_name
            ),
        )
    else:
        return HttpResponseForbidden(
            f"No permission to remove Character with pk {character_pk}"
        )
    return redirect("miningtaxes:admin_launcher")


@login_required
@permission_required("miningtaxes.basic_access")
def remove_character(request, character_pk: int) -> HttpResponse:
    try:
        character = Character.objects.select_related(
            "eve_character__character_ownership__user", "eve_character"
        ).get(pk=character_pk)
    except Character.DoesNotExist:
        return HttpResponseNotFound(f"Character with pk {character_pk} not found")
    if character.user and character.user == request.user:
        character_name = character.eve_character.character_name

        # Notify that character has been dropped
        # permission_to_notify = Permission.objects.select_related("content_type").get(
        #    content_type__app_label=Character._meta.app_label,
        #    codename="notified_on_character_removal",
        # )
        # title = f"{__title__}: Character has been removed!"
        # message = f"{request.user} has removed character '{character_name}'"
        # for to_notify in users_with_permission(permission_to_notify):
        #    if character.user_has_scope(to_notify):
        #        notify(user=to_notify, title=title, message=message, level="INFO")

        character.delete()
        messages.success(
            request,
            format_html(
                "Removed character <strong>{}</strong> as requested.", character_name
            ),
        )
    else:
        return HttpResponseForbidden(
            f"No permission to remove Character with pk {character_pk}"
        )
    return redirect("miningtaxes:launcher")


@login_required
@permission_required("miningtaxes.basic_access")
def character_viewer(request, character_pk: int):
    character = Character.objects.get(pk=character_pk)
    context = {
        "character": character,
    }

    return render(request, "miningtaxes/character_viewer.html", context)


@login_required
@permission_required("memberaudit.basic_access")
@fetch_character_if_allowed()
def character_mining_ledger_data(
    request, character_pk: int, character: Character
) -> JsonResponse:
    qs = character.mining_ledger.select_related(
        "eve_solar_system",
        "eve_solar_system__eve_constellation__eve_region",
        "eve_type",
    )
    data = [
        {
            "date": row.date.isoformat(),
            "quantity": row.quantity,
            "region": row.eve_solar_system.eve_constellation.eve_region.name,
            "solar_system": row.eve_solar_system.name,
            "raw price": row.raw_price,
            "refined price": row.refined_price,
            "taxed value": row.taxed_value,
            "taxes owed": row.taxes_owed,
            "type": row.eve_type.name,
        }
        for row in qs
    ]
    return JsonResponse({"data": data})
