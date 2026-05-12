"""User and auth-provider admin — Unit U3.

Wraps the HA WebSocket API surface exposed by:

  homeassistant.components.config.auth:
    config/auth/create
    config/auth/update

  homeassistant.components.config.auth_provider_homeassistant:
    config/auth_provider/homeassistant/create
    config/auth_provider/homeassistant/delete
    config/auth_provider/homeassistant/change_password
"""

from __future__ import annotations


def create_user(client, *, name: str, group_ids: list[str] | None = None,
                local_only: bool | None = None) -> dict:
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


def update_user(client, *, user_id: str, name: str | None = None,
                group_ids: list[str] | None = None,
                local_only: bool | None = None,
                is_active: bool | None = None) -> dict:
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
    if name is None and group_ids is None and local_only is None \
            and is_active is None:
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


def create_credential(client, *, user_id: str, username: str,
                      password: str) -> dict:
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


def change_password(client, *, current_password: str,
                    new_password: str) -> dict:
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
    return client.ws_call("config/auth_provider/homeassistant/change_password",
                          payload)
