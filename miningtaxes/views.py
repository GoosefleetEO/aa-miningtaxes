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
from django.views.decorators.cache import cache_page
from esi.decorators import token_required

from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.helpers import humanize_number
from app_utils.logging import LoggerAddTag
from app_utils.views import bootstrap_icon_plus_name_html

from . import __title__, __version__, tasks
from .app_settings import MININGTAXES_TAX_CACHE_VIEW_TIMEOUT
from .forms import SettingsForm
from .helpers import PriceGroups
from .models import (
    AdminCharacter,
    AdminMiningCorpLedgerEntry,
    AdminMiningObsLog,
    Character,
    CharacterMiningLedgerEntry,
    OrePrices,
    Settings,
    ore_calc_prices,
)

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
        "version": __version__,
        "form": form,
    }
    return render(request, "miningtaxes/admin_launcher.html", context)


@login_required
@cache_page(MININGTAXES_TAX_CACHE_VIEW_TIMEOUT)
@permission_required("miningtaxes.auditor_access")
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
        if c.eve_character is None:
            continue
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
    char2user = {}
    user2taxes = tasks.calctaxes()

    for char in chars:
        if char.main_character is None:
            logger.error(f"Missing main: {char}")
            continue
        m = char.main_character
        char2user[m] = char.user
        if m not in main_level:
            main_level[m] = {"life_tax": 0.0, "life_credits": 0.0, "last_paid": None}
        main_level[m]["life_tax"] += char.get_lifetime_taxes()
        main_level[m]["life_credits"] += char.get_lifetime_credits()
        if char.last_paid() is not None and (
            main_level[m]["last_paid"] is None
            or char.last_paid() > main_level[m]["last_paid"]
        ):
            main_level[m]["last_paid"] = char.last_paid()
    for m in main_level.keys():
        main_level[m]["balance"] = (
            main_level[m]["life_tax"] - main_level[m]["life_credits"]
        )
    return main_level, char2user, user2taxes


@login_required
@permission_required("miningtaxes.auditor_access")
def admin_main_json(request):
    main_level, char2user, user2taxes = main_data_helper(Character.objects.all())
    logger.debug("HERE")
    main_data = []
    for i, m in enumerate(main_level.keys()):
        summary_url = reverse("miningtaxes:user_summary", args=[char2user[m].pk])
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
                "last_paid": main_level[m]["last_paid"],
                "action": action_html,
                "user": char2user[m].pk,
                "taxes_due": user2taxes[char2user[m]][0],
            }
        )
    return JsonResponse({"data": main_data})


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
@cache_page(MININGTAXES_TAX_CACHE_VIEW_TIMEOUT)
@permission_required("miningtaxes.basic_access")
def ore_prices_json(request):
    settings = Settings.load()
    data = []
    pg = PriceGroups()
    for ore in OrePrices.objects.all():
        if "Compressed" in ore.eve_type.name:
            continue
        if ore.eve_type.eve_group_id not in pg.taxgroups:
            continue
        raw = 1000.0 * ore.raw_price
        refined = 1000.0 * ore.refined_price
        taxed = 1000.0 * ore.taxed_price
        group = "tax_" + pg.taxgroups[ore.eve_type.eve_group_id]
        tax_rate = settings.__dict__[group] / 100.0

        tax = taxed * tax_rate
        remaining = taxed - tax
        tax_rate = "{0:.0%}".format(tax_rate)
        group = pg.taxgroups[ore.eve_type.eve_group_id]
        data.append(
            {
                "group": group,
                "name": ore.eve_type.name,
                "raw": raw,
                "refined": refined,
                "taxed": taxed,
                "tax_rate": tax_rate,
                "remaining": remaining,
                "tax": tax,
            }
        )

    return JsonResponse({"data": data})


@login_required
@permission_required("miningtaxes.basic_access")
def faq(request):
    settings = Settings.load()
    context = {"phrase": settings.phrase}
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
    main_data, _, user2taxes = main_data_helper(auth_characters)

    context = {
        "page_title": "Taxes Summary",
        "auth_characters": auth_characters,
        "unregistered_chars": unregistered_chars,
        "main_character_id": main_character_id,
        "balance": humanize_number(main_data[list(main_data.keys())[0]]["balance"]),
        "balance_raw": "{:,.2f}".format(
            round(main_data[list(main_data.keys())[0]]["balance"], 2)
        ),
        "taxes_due": user2taxes[user][0],
        "last_paid": main_data[list(main_data.keys())[0]]["last_paid"],
        "user_pk": user_pk,
    }
    return render(request, "miningtaxes/user_summary.html", context)


@login_required
@cache_page(MININGTAXES_TAX_CACHE_VIEW_TIMEOUT)
@permission_required("miningtaxes.auditor_access")
def admin_corp_ledger(request):
    obs = AdminMiningCorpLedgerEntry.objects.all().order_by("-date")
    data = []
    for o in obs:
        char = o.taxed_id
        name = None
        eve_char = None
        try:
            eve_char = EveCharacter.objects.get(character_id=char)
        except EveCharacter.DoesNotExist:
            name = f"<a href='https://evewho.com/character/{char}'>{char}</a>"
            pass
        except Exception as e:
            logger.error(f"Error unknown user: {char}, error: {e}")
            continue
        if eve_char is not None:
            try:
                character = eve_char.miningtaxes_character
                name = character.main_character.character_name
            except AttributeError:
                name = eve_char.character_name
                pass
            except Exception as e:
                logger.error(f"Error unknown user: {eve_char}, error: {e}")
                continue
        data.append(
            {
                "date": o.date,
                "name": name,
                "amount": o.amount,
                "reason": o.reason,
            }
        )
    return JsonResponse({"data": data})


def characterize(char):
    eve_char = None
    category = None
    name = None
    try:
        eve_char = EveCharacter.objects.get(character_id=char)
    except EveCharacter.DoesNotExist:
        name = f"<a href='https://evewho.com/character/{char}'>{char}</a>"
        category = "unknown"
        pass
    if eve_char is not None:
        try:
            character = eve_char.miningtaxes_character
            name = character.main_character.character_name
            category = "found"
        except AttributeError:
            name = eve_char.character_name
            category = "unregistered"
            pass
    return name, category


@login_required
@cache_page(MININGTAXES_TAX_CACHE_VIEW_TIMEOUT)
@permission_required("miningtaxes.auditor_access")
def admin_corp_mining_history(request):
    obs = AdminMiningObsLog.objects.all().order_by("-date")
    cache = {}
    data = []
    unknown_chars = {}
    unregistered_chars = {}
    for o in obs:
        char = o.miner_id
        if char not in cache:
            cache[char] = characterize(char)
        (name, category) = cache[char]

        if category == "unknown":
            if name not in unknown_chars:
                unknown_chars[name] = [0, 0.0, None]
            unknown_chars[name][0] += o.quantity
            (_, _, value) = ore_calc_prices(o.eve_type, o.quantity)
            unknown_chars[name][1] += value
            if unknown_chars[name][2] is None or unknown_chars[name][2] < o.date:
                unknown_chars[name][2] = o.date
        elif category == "unregistered":
            if name not in unregistered_chars:
                unregistered_chars[name] = [0, 0.0, None]
            unregistered_chars[name][0] += o.quantity
            (_, _, value) = ore_calc_prices(o.eve_type, o.quantity)
            unregistered_chars[name][1] += value
            if (
                unregistered_chars[name][2] is None
                or unregistered_chars[name][2] < o.date
            ):
                unregistered_chars[name][2] = o.date
        data.append(
            {
                "date": o.date,
                "ore": o.eve_type.name,
                "name": name,
                "quantity": o.quantity,
                "location": o.eve_solar_system.name,
            }
        )

    unknown_data = []
    for name in unknown_chars.keys():
        unknown_data.append(
            {
                "name": name,
                "quantity": unknown_chars[name][0],
                "isk": unknown_chars[name][1],
                "last": unknown_chars[name][2],
            }
        )

    unregistered_data = []
    for name in unregistered_chars.keys():
        unregistered_data.append(
            {
                "name": name,
                "quantity": unregistered_chars[name][0],
                "isk": unregistered_chars[name][1],
                "last": unregistered_chars[name][2],
            }
        )

    return JsonResponse(
        {
            "mining_log": data,
            "unknown_data": unknown_data,
            "unregistered_data": unregistered_data,
        }
    )


@login_required
@cache_page(MININGTAXES_TAX_CACHE_VIEW_TIMEOUT)
@permission_required("miningtaxes.auditor_access")
def admin_mining_by_sys_json(request):
    entries = CharacterMiningLedgerEntry.objects.all().prefetch_related(
        "character", "eve_type", "eve_solar_system"
    )
    sys = {}
    pg = PriceGroups()
    csv_data = [
        [
            "Date",
            "Sys",
            "Character",
            "Main",
            "Ore",
            "Group",
            "Amount",
            "ISK Value",
            "Taxed",
        ]
    ]
    allgroups = set()
    tables = {}

    for e in entries:
        try:
            s = e.eve_solar_system.name
            if s not in sys:
                sys[s] = {}

            group = pg.taxgroups[e.eve_type.eve_group_id]
            allgroups.add(group)

            csv_data.append(
                [
                    e.date,
                    s,
                    e.character.eve_character.character_name,
                    e.character.main_character.character_name,
                    e.eve_type.name,
                    group,
                    e.quantity,
                    e.taxed_value,
                    e.taxes_owed,
                ]
            )
        except Exception as e:
            logger.error(f"Failed: {e}")
            continue

        month = "%d-%02d" % (e.date.year, e.date.month)
        if month not in tables:
            tables[month] = {}
        if s not in tables[month]:
            tables[month][s] = {}
        if group not in tables[month][s]:
            tables[month][s][group] = {"tax": 0.0, "isk": 0.0}

        tables[month][s][group]["tax"] += e.taxes_owed
        tables[month][s][group]["isk"] += e.taxed_value

        if group not in sys[s]:
            sys[s][group] = {
                "first": e.date,
                "last": e.date,
                "q": e.quantity,
                "isk": e.taxed_value,
                "tax": e.taxes_owed,
            }
            continue
        if e.date < sys[s][group]["first"]:
            sys[s][group]["first"] = e.date
        if e.date > sys[s][group]["last"]:
            sys[s][group]["last"] = e.date
        sys[s][group]["isk"] += e.taxed_value
        sys[s][group]["tax"] += e.taxes_owed
        sys[s][group]["q"] += e.quantity

    # Reformat for billboard and calc stats
    for s in sys.keys():
        for g in allgroups:
            if g not in sys[s]:
                sys[s][g] = {"isk": 0, "tax": 0, "q": 0}
                continue
            # t = (sys[s][g]["last"] - sys[s][g]["first"]).days
            t = (now().date() - sys[s][g]["first"]).days
            t /= 365.25 / 12
            if t < 1:
                t = 1
            sys[s][g]["isk"] /= t
            sys[s][g]["tax"] /= t
            sys[s][g]["q"] /= t

    anal = {}
    for a in ("isk", "tax", "q"):
        x = ["x"]
        order = sorted(
            sys.keys(), key=lambda x: (sum(map(lambda y: -sys[x][y][a], allgroups)))
        )
        gorder = sorted(
            allgroups, key=lambda g: sum(map(lambda s: -sys[s][g][a], sys.keys()))
        )
        ys = []
        for g in gorder:
            ys.append([g])
        for s in order:
            x.append(s)
            for i, g in enumerate(gorder):
                ys[i].append(sys[s][g][a])
            if len(x) > 11:
                break
        ys.append(x)
        anal[a] = ys

    return JsonResponse({"anal": anal, "csv": csv_data, "tables": tables})


@login_required
@cache_page(MININGTAXES_TAX_CACHE_VIEW_TIMEOUT)
@permission_required("miningtaxes.auditor_access")
def admin_tax_revenue_json(request):
    entries = AdminMiningCorpLedgerEntry.objects.all()
    settings = Settings.load()

    months = {}
    for e in entries:
        if settings.phrase != "" and settings.phrase not in e.reason:
            continue
        d = dt.date(year=e.date.year, month=e.date.month, day=15)
        if d not in months:
            months[d] = 0.0
        months[d] += e.amount

    xs = list(sorted(months.keys()))
    ys = list(map(lambda x: months[x], xs))
    xs = ["x"] + xs
    ys = ["Revenue"] + ys

    csv_data = [["Month", "Amount (ISK)"]]
    for i in range(1, len(xs)):
        csv_data.append([xs[i], ys[i]])

    return JsonResponse({"xdata": xs, "ydata": ys, "csv": csv_data})


@login_required
@cache_page(MININGTAXES_TAX_CACHE_VIEW_TIMEOUT)
@permission_required("miningtaxes.auditor_access")
def admin_month_json(request):
    characters = Character.objects.all()
    newchars = []
    for c in characters:
        if c.main_character is None:
            logger.error(f"Missing main for {c}")
            continue
        newchars.append(c)
    characters = newchars
    monthly = list(map(lambda x: x.get_monthly_taxes(), characters))
    users = list(map(lambda x: x.main_character.character_name, characters))
    firstmonth = None
    for entries in monthly:
        if len(entries.keys()) == 0:
            continue
        if firstmonth is None or firstmonth > sorted(entries.keys())[0]:
            firstmonth = sorted(entries.keys())[0]
    xs = None
    ys = {}
    for i, entries in enumerate(monthly):
        if not users[i] in ys:
            ys[users[i]] = []
        x = ["x"]
        y = []
        curmonth = firstmonth
        lastmonth = dt.date(now().year, now().month, 1)
        while curmonth <= lastmonth:
            if curmonth not in entries:
                entries[curmonth] = 0.0
            x.append(curmonth)
            curmonth += relativedelta(months=1)

        if xs is None:
            xs = x

        for yi in range(1, len(xs)):
            y.append(entries[xs[yi]])
        ys[users[i]].append(y)
    yout = []
    for user in ys.keys():
        yout.append([user] + [sum(x) for x in zip(*ys[user])])

    yall = ["all"]
    for yi in range(1, len(xs)):
        sumy = 0
        for row in yout:
            sumy += row[yi]
        yall.append(sumy)
    yout.insert(0, yall)

    csvdata = [["Month", "Main", "Taxes Total"]]
    for xi in range(1, len(xs)):
        month = xs[xi]
        for userarr in yout:
            row = [month, userarr[0], userarr[xi]]
            csvdata.append(row)

    return JsonResponse({"xdata": xs, "ydata": yout, "csv": csvdata})


@login_required
@cache_page(MININGTAXES_TAX_CACHE_VIEW_TIMEOUT)
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
@cache_page(MININGTAXES_TAX_CACHE_VIEW_TIMEOUT)
@permission_required("miningtaxes.basic_access")
def leaderboards(request):
    characters = Character.objects.all()
    allentries = list(map(lambda x: x.get_monthly_mining(), characters))
    combined = {}
    for i, entries in enumerate(allentries):
        c = characters[i].main_character
        if c is None:
            logger.error(f"Missing main for {c}")
            continue
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
    logger.error("HERE")
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
@cache_page(MININGTAXES_TAX_CACHE_VIEW_TIMEOUT)
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
