"""User and auth-provider admin — Unit U3.

Wraps the HA WebSocket API surface exposed by:

  homeassistant.components.config.auth:
    config/auth/create
    config/auth/update

  homeassistant.components.config.auth_provider_homeassistant:
    config/auth_provider/homeassistant/create
    config/auth_provider/homeassistant/delete
    config/auth_provider/homeassistant/change_password
    config/auth_provider/homeassistant/admin_change_password
    config/auth_provider/homeassistant/admin_change_username

THE `admin_*` PAIR IS OWNER-ONLY, NOT ADMIN-ONLY
    Despite the name, `require_admin` is only the outer gate on those two
    commands: the handler then checks `connection.user.is_owner` and raises
    `Unauthorized` if not. An ADMIN token is refused. There is exactly one
    owner per instance — the account created during onboarding — so an
    automation token minted by a second admin cannot reset passwords, and the
    failure reads as a bare `unauthorized` that names neither the requirement
    nor the remedy. Both wrappers say it in the error instead.

    They also differ from `change_password` in what they need: the admin form
    takes a `user_id` and NO current password, which is what makes it a reset
    (for a locked-out user) rather than a change.
"""

from __future__ import annotations


def create_user(
    client, *, name: str, group_ids: list[str] | None = None, local_only: bool | None = None
) -> dict:
    """Create a new user in Home Assistant.

    Sends ``config/auth/create`` via WebSocket.

    ``name`` — user's display name (required, must be non-empty).
    ``group_ids`` — list of group IDs for the user (optional).
    ``local_only`` — if True, user can only authenticate locally (optional).

    Returns a dict containing ``user`` — the created user record with ``id``.
    """
    if not name:
        raise ValueError("name must be a non-empty string")
    payload: dict = {"name": name}
    if group_ids is not None:
        payload["group_ids"] = list(group_ids)
    if local_only is not None:
        payload["local_only"] = local_only
    return client.ws_call("config/auth/create", payload)


def update_user(
    client,
    *,
    user_id: str,
    name: str | None = None,
    group_ids: list[str] | None = None,
    local_only: bool | None = None,
    is_active: bool | None = None,
) -> dict:
    """Update an existing user.

    Sends ``config/auth/update`` via WebSocket.

    ``user_id`` — the user's UUID (required, must be non-empty).
    ``name`` — new display name (optional).
    ``group_ids`` — new list of group IDs (optional).
    ``local_only`` — toggle local-only auth (optional).
    ``is_active`` — activate or deactivate the user (optional).

    At least one updateable field (name, group_ids, local_only, is_active)
    must be supplied.

    Returns a dict containing ``user`` — the updated user record.
    """
    if not user_id:
        raise ValueError("user_id must be a non-empty string")
    if name is None and group_ids is None and local_only is None and is_active is None:
        raise ValueError("pass at least one of name/group_ids/local_only/is_active")
    payload: dict = {"user_id": user_id}
    if name is not None:
        payload["name"] = name
    if group_ids is not None:
        payload["group_ids"] = list(group_ids)
    if local_only is not None:
        payload["local_only"] = local_only
    if is_active is not None:
        payload["is_active"] = is_active
    return client.ws_call("config/auth/update", payload)


def create_credential(client, *, user_id: str, username: str, password: str) -> dict:
    """Create homeassistant-provider credentials for a user.

    Sends ``config/auth_provider/homeassistant/create`` via WebSocket.

    ``user_id`` — the user's UUID (required, must be non-empty).
    ``username`` — login username (required, must be non-empty).
    ``password`` — login password (required, must be non-empty).

    Returns a dict (typically empty ``{}`` on success).
    """
    if not user_id:
        raise ValueError("user_id must be a non-empty string")
    if not username:
        raise ValueError("username must be a non-empty string")
    if not password:
        raise ValueError("password must be a non-empty string")
    payload: dict = {
        "user_id": user_id,
        "username": username,
        "password": password,
    }
    return client.ws_call("config/auth_provider/homeassistant/create", payload)


def delete_credential(client, *, username: str) -> dict:
    """Delete a homeassistant-provider credential by username.

    Sends ``config/auth_provider/homeassistant/delete`` via WebSocket.

    ``username`` — the username to delete (required, must be non-empty).

    Returns a dict (typically empty ``{}`` on success).
    """
    if not username:
        raise ValueError("username must be a non-empty string")
    payload: dict = {"username": username}
    return client.ws_call("config/auth_provider/homeassistant/delete", payload)


def change_password(client, *, current_password: str, new_password: str) -> dict:
    """Change the current user's password via the homeassistant provider.

    Sends ``config/auth_provider/homeassistant/change_password`` via WebSocket.

    ``current_password`` — the user's current password (required, non-empty).
    ``new_password`` — the new password (required, non-empty and != current).

    Returns a dict (typically empty ``{}`` on success).
    """
    if not current_password:
        raise ValueError("current_password must be a non-empty string")
    if not new_password:
        raise ValueError("new_password must be a non-empty string")
    if current_password == new_password:
        raise ValueError("new_password must differ from current_password")
    payload: dict = {
        "current_password": current_password,
        "new_password": new_password,
    }
    return client.ws_call("config/auth_provider/homeassistant/change_password", payload)


#: HA's codes for the two ways the `admin_*` pair fails on a valid request.
_ADMIN_CODES = {
    "user_not_found": "no user with that user_id (list them with `user list`)",
    "credentials_not_found": (
        "that user has no username/password credential to change — they sign in "
        "another way (a trusted network, or a link-only account). Give them one "
        "with `user credential-create` first"
    ),
}


def _admin_credential_call(client, command: str, payload: dict, *, action: str):
    """Send an owner-only credential command, naming why it was refused.

    `unauthorized` here means the TOKEN IS NOT THE OWNER'S, which the raw code
    does not say. Admin is not enough (see the module docstring).
    """
    from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

    try:
        return client.ws_call(command, payload)
    except HomeAssistantError as exc:
        code = getattr(exc, "code", None)
        if code == "unauthorized":
            raise ValueError(
                f"Refused: {action} is OWNER-only. Being an admin is not enough — "
                "Home Assistant checks `user.is_owner`. Use a long-lived token "
                "belonging to the owner account (the one created at onboarding)."
            ) from exc
        if code in _ADMIN_CODES:
            raise ValueError(f"Cannot {action}: {_ADMIN_CODES[code]}.") from exc
        raise


def admin_change_password(client, *, user_id: str, password: str) -> dict:
    """Reset ANOTHER user's password. Owner-only; no current password needed.

    This is the locked-out-user remedy: `change_password` needs the existing
    password and this does not. The user is not notified and any session they
    already hold stays valid — HA does not revoke tokens on a password change,
    so a compromised account needs `auth-token delete` as well.

    Sends ``config/auth_provider/homeassistant/admin_change_password``.
    """
    if not user_id:
        raise ValueError("user_id must be a non-empty string")
    if not password:
        raise ValueError("password must be a non-empty string")
    _admin_credential_call(
        client,
        "config/auth_provider/homeassistant/admin_change_password",
        {"user_id": user_id, "password": password},
        action="resetting another user's password",
    )
    return {
        "applied": True,
        "user_id": user_id,
        "changed": "password",
        "note": (
            "Password reset. Existing sessions and long-lived tokens for this "
            "user are NOT revoked — use `auth-token list`/`delete` for that."
        ),
    }


def admin_change_username(client, *, user_id: str, username: str) -> dict:
    """Rename the login of ANOTHER user. Owner-only.

    The username is the LOGIN, not the display name — `user update --name`
    changes what the UI shows and leaves the credential alone. Changing this
    changes what the person types to sign in; their password is unaffected.

    Sends ``config/auth_provider/homeassistant/admin_change_username``.
    """
    if not user_id:
        raise ValueError("user_id must be a non-empty string")
    if not username:
        raise ValueError("username must be a non-empty string")
    _admin_credential_call(
        client,
        "config/auth_provider/homeassistant/admin_change_username",
        {"user_id": user_id, "username": username},
        action="renaming another user's login",
    )
    return {
        "applied": True,
        "user_id": user_id,
        "changed": "username",
        "username": username,
        "note": (
            "Login renamed. This is the sign-in username, not the display name "
            "(`user update --name`). The password is unchanged."
        ),
    }
