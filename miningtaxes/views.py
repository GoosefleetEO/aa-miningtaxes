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
from django.utils.html import format_html
from django.utils.timezone import now

# from django.views.decorators.cache import cache_page
from esi.decorators import token_required

from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.helpers import humanize_number
from app_utils.logging import LoggerAddTag
from app_utils.views import bootstrap_icon_plus_name_html

from . import __title__, __version__, tasks
from .forms import SettingsForm
from .helpers import PriceGroups
from .models import AdminCharacter, AdminMiningObsLog, Character, Settings, Stats

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

    registered = Character.objects.all()
    auth_registered = list()
    for a_character in registered:
        eve_character = a_character.eve_character
        auth_registered.append(
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
        "auth_registered": auth_registered,
        "version": __version__,
        "form": form,
    }
    return render(request, "miningtaxes/admin_launcher.html", context)


@login_required
@permission_required("miningtaxes.auditor_access")
def admin_char_json(request):
    s = Stats.load()
    return JsonResponse({"data": s.get_admin_char_json()})


@login_required
@permission_required("miningtaxes.auditor_access")
def admin_main_json(request):
    s = Stats.load()
    return JsonResponse({"data": s.get_admin_main_json()})


@login_required
@permission_required("miningtaxes.auditor_access")
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
            suitable.give_credit(isk, "credit")
            s = Stats.load()
            s.calc_admin_main_json()
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
def ore_prices(request):
    return render(request, "miningtaxes/ore_prices.html", {})


@login_required
@permission_required("miningtaxes.basic_access")
def ore_prices_json(request):
    s = Stats.load()
    return JsonResponse({"data": s.get_ore_prices_json()})


@login_required
@permission_required("miningtaxes.basic_access")
def faq(request):
    corps = []
    for c in AdminCharacter.objects.all():
        corps.append(c.eve_character.corporation_name)
    corps = ",".join(corps)
    settings = Settings.load()
    context = {"phrase": settings.phrase, "corps": corps}
    return render(request, "miningtaxes/faq.html", context)


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
    s = Stats.load()
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
    main_character_id = user.profile.main_character.character_id
    main_data, _, user2taxes = s.main_data_helper(auth_characters)
    taxes_due = user2taxes[user][0]
    if taxes_due < 0:
        taxes_due = 0

    context = {
        "page_title": "Taxes Summary",
        "auth_characters": auth_characters,
        "unregistered_chars": unregistered_chars,
        "main_character_id": main_character_id,
        "balance": humanize_number(main_data[list(main_data.keys())[0]]["balance"]),
        "balance_raw": main_data[list(main_data.keys())[0]]["balance"],
        "taxes_due": taxes_due,
        "last_paid": main_data[list(main_data.keys())[0]]["last_paid"],
        "user_pk": user_pk,
    }
    return render(request, "miningtaxes/user_summary.html", context)


@login_required
@permission_required("miningtaxes.auditor_access")
def admin_get_all_activity_json(request):
    s = Stats.load()
    return JsonResponse({"data": s.get_admin_get_all_activity_json()})


@login_required
@permission_required("miningtaxes.auditor_access")
def admin_corp_ledger(request):
    s = Stats.load()
    return JsonResponse(s.get_admin_corp_ledger())


@login_required
@permission_required("miningtaxes.auditor_access")
def admin_corp_mining_history(request):
    s = Stats.load()
    return JsonResponse(s.get_admin_corp_mining_history())


@login_required
@permission_required("miningtaxes.auditor_access")
def admin_mining_by_sys_json(request):
    s = Stats.load()
    return JsonResponse(s.get_admin_mining_by_sys_json())


@login_required
@permission_required("miningtaxes.auditor_access")
def admin_tax_revenue_json(request):
    s = Stats.load()
    return JsonResponse(s.get_admin_tax_revenue_json())


@login_required
@permission_required("miningtaxes.auditor_access")
def admin_month_json(request):
    s = Stats.load()
    return JsonResponse(s.get_admin_month_json())


@login_required
@permission_required("miningtaxes.basic_access")
def summary_month_json(request, user_pk: int):
    user = User.objects.get(pk=user_pk)
    if request.user != user and not request.user.has_perm("miningtaxes.auditor_access"):
        return HttpResponseForbidden()
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
    if request.user != user and not request.user.has_perm("miningtaxes.auditor_access"):
        return HttpResponseForbidden()
    characters = Character.objects.owned_by_user(user)
    allcredits = []
    for c in characters:
        if c.eve_character is None:
            continue
        allcredits += map(
            lambda x: {
                "date": x.date,
                "character": bootstrap_icon_plus_name_html(
                    icon_url=c.eve_character.portrait_url(),
                    name=c.eve_character.character_name,
                    size=16,
                ),
                "amount": x.credit,
                "reason": x.credit_type,
            },
            c.tax_credits.all(),
        )

    return JsonResponse({"data": allcredits})


@login_required
@permission_required("miningtaxes.basic_access")
def leaderboards(request):
    s = Stats.load()
    return JsonResponse(s.get_leaderboards())


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
    s = Stats.load()
    s.calc_admin_main_json()
    return redirect("miningtaxes:launcher")


@login_required
@permission_required("miningtaxes.admin_access")
def purge_old_corphistory(request) -> HttpResponse:
    days_90 = now() - dt.timedelta(days=90)

    AdminMiningObsLog.objects.filter(date__lte=days_90).delete()

    messages.success(
        request,
        format_html("Purged old corp mining history as requested."),
    )
    return redirect("miningtaxes:admin_launcher")


@login_required
@permission_required("miningtaxes.admin_access")
def remove_admin_registered(request, character_pk: int) -> HttpResponse:
    try:
        character = Character.objects.select_related(
            "eve_character__character_ownership__user", "eve_character"
        ).get(pk=character_pk)
    except Character.DoesNotExist:
        return HttpResponseNotFound(f"Character with pk {character_pk} not found")

    character_name = character.eve_character.character_name

    character.delete()
    messages.success(
        request,
        format_html(
            "Removed character <strong>{}</strong> as requested.", character_name
        ),
    )
    return redirect("miningtaxes:admin_launcher")


@login_required
@permission_required("miningtaxes.admin_access")
def remove_admin_character(request, character_pk: int) -> HttpResponse:
    try:
        character = AdminCharacter.objects.select_related(
            "eve_character__character_ownership__user", "eve_character"
        ).get(pk=character_pk)
    except Character.DoesNotExist:
        return HttpResponseNotFound(f"Character with pk {character_pk} not found")

    character_name = character.eve_character.character_name

    character.delete()
    messages.success(
        request,
        format_html(
            "Removed character <strong>{}</strong> as requested.", character_name
        ),
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


def char_mining_ledger_data(request, character_pk: int) -> JsonResponse:
    character = Character.objects.get(pk=character_pk)
    if request.user != character.user and not request.user.has_perm(
        "miningtaxes.auditor_access"
    ):
        return HttpResponseForbidden()
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


@login_required
@permission_required("memberaudit.basic_access")
def user_mining_ledger_90day(request, user_pk: int) -> JsonResponse:
    user = User.objects.get(pk=user_pk)
    if request.user != user and not request.user.has_perm("miningtaxes.auditor_access"):
        return HttpResponseForbidden()
    characters = Character.objects.owned_by_user(user)
    pg = PriceGroups()
    allpgs = {}
    alldays = {}
    polar = {}
    for c in characters:
        ledger = c.get_90d_mining()
        for entry in ledger:
            try:
                g = pg.taxgroups[entry.eve_type.eve_group_id]
                allpgs[g] = [g]
                v = entry.taxed_value
            except Exception as e:
                logger.warn(f"Unknown entry: {e} - {entry}")
                continue
            if entry.date not in alldays:
                alldays[entry.date] = {}
            if g not in alldays[entry.date]:
                alldays[entry.date][g] = 0.0
            if g not in polar:
                polar[g] = 0.0
            alldays[entry.date][g] += v
            polar[g] += v
    xs = ["x"]
    curd = sorted(alldays.keys())[0]
    days = [0, 0]
    while curd <= now().date():
        xs.append(curd)
        days[1] += 1
        mined = False
        for g in allpgs.keys():
            if curd not in alldays or g not in alldays[curd]:
                allpgs[g].append(0)
            else:
                mined = True
                allpgs[g].append(alldays[curd][g])
        if mined:
            days[0] += 1
        curd += dt.timedelta(days=1)
    finalgraph = [xs]
    for g in allpgs.keys():
        finalgraph.append(allpgs[g])

    polargraph = []
    for g in polar.keys():
        polargraph.append([g, polar[g]])

    days = round(100.0 * days[0] / days[1], 2)
    return JsonResponse(
        {
            "stacked": finalgraph,
            "polargraph": polargraph,
            "days": [["days mined", days]],
        }
    )
