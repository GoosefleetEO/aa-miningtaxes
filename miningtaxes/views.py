from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.http import (
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseNotFound,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import format_html
from esi.decorators import token_required

from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

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
def admin_tables(request):
    context = {
        "page_title": "Admin Tables",
    }
    return render(request, "miningtaxes/admin_tables.html", context)


@login_required
@permission_required("miningtaxes.basic_access")
def index(request):
    return redirect("miningtaxes:launcher")


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
    character = Character.objects.get_cached(pk=character_pk)
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
