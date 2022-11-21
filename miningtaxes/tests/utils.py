import datetime as dt
from typing import Tuple

from django.contrib.auth.models import User
from django.utils.timezone import now

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from allianceauth.tests.auth_utils import AuthUtils
from app_utils.testing import add_character_to_user

from ..models import AdminCharacter, Character, CharacterUpdateStatus


def create_character_update_status(
    character: Character, **kwargs
) -> CharacterUpdateStatus:
    params = {
        "character": character,
        "is_success": True,
        "started_at": now() - dt.timedelta(minutes=5),
        "finished_at": now(),
    }
    params.update(kwargs)
    return CharacterUpdateStatus.objects.create(**params)


def create_character(eve_character, **kwargs) -> Character:
    params = {"eve_character": eve_character}
    params.update(kwargs)
    return Character.objects.create(**params)


def create_character_from_user(user: User, **kwargs):
    """Create new Character object from user. The user needs to have a main character.

    This factory is designed to work with both the old and new variant of Character
    introduced in version 2.
    """
    try:
        character_ownership = user.profile.main_character.character_ownership
    except AttributeError:
        raise ValueError("User needs to have a main character.")
    if hasattr(Character, "eve_character"):
        params = {"eve_character": character_ownership.character}
    else:
        params = {"character_ownership": character_ownership}
    params.update(kwargs)
    return Character.objects.create(**params)


def create_user_from_evecharacter_with_access(
    character_id: int,
) -> Tuple[User, CharacterOwnership]:
    auth_character = EveCharacter.objects.get(character_id=character_id)
    user = AuthUtils.create_user(auth_character.character_name)
    user = AuthUtils.add_permission_to_user_by_name("miningtaxes.basic_access", user)
    character_ownership = add_character_to_user(
        user, auth_character, is_main=True, scopes=Character.get_esi_scopes()
    )
    return user, character_ownership


def create_miningtaxes_character(character_id: int) -> Character:
    _, character_ownership = create_user_from_evecharacter_with_access(character_id)
    return Character.objects.create(eve_character=character_ownership.character)


def create_miningtaxes_admincharacter(character_id: int) -> Character:
    _, character_ownership = create_user_from_evecharacter_with_access(character_id)
    return AdminCharacter.objects.create(eve_character=character_ownership.character)


def add_auth_character_to_user(
    user: User, character_id: int, scopes=None
) -> CharacterOwnership:
    auth_character = EveCharacter.objects.get(character_id=character_id)
    if not scopes:
        scopes = Character.get_esi_scopes()

    return add_character_to_user(user, auth_character, is_main=False, scopes=scopes)


def add_miningtaxes_character_to_user(user: User, character_id: int) -> Character:
    character_ownership = add_auth_character_to_user(user, character_id)
    return Character.objects.create(eve_character=character_ownership.character)
