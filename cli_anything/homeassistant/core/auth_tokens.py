"""Auth token management — Unit S3A.

Wraps the HA WebSocket API surface exposed by
``homeassistant.components.auth``:

  auth/current_user
  auth/refresh_tokens
  auth/long_lived_access_token
  auth/delete_refresh_token
  auth/delete_all_refresh_tokens
  auth/refresh_token_set_expiry
  auth/sign_path
"""

from __future__ import annotations

_VALID_TOKEN_TYPES = {"normal", "system", "long_lived_access_token"}


def current_user(client) -> dict:
    """Return the user the active token belongs to.

    Sends ``auth/current_user`` via WebSocket.
    Returns a dict with at least ``id``, ``name``, ``is_admin``.
    """
    return client.ws_call("auth/current_user")


def list_refresh_tokens(client) -> list:
    """Return all refresh tokens visible to the active user.

    Sends ``auth/refresh_tokens`` via WebSocket.
    """
    return client.ws_call("auth/refresh_tokens")


def create_long_lived_access_token(
    client,
    *,
    client_name: str,
    lifespan: int = 365,
) -> dict:
    """Create a long-lived access token for the active user.

    Sends ``auth/long_lived_access_token`` via WebSocket with
    ``{client_name, lifespan}`` in the payload.

    ``client_name`` must be a non-empty string.
    ``lifespan`` is in days and must be positive (default 365).

    Returns a dict containing ``token`` — the caller must store it
    securely; HA will not expose it again.
    """
    if not client_name:
        raise ValueError("client_name must be a non-empty string")
    if lifespan <= 0:
        raise ValueError("lifespan must be a positive integer (days)")
    return client.ws_call(
        "auth/long_lived_access_token",
        {"client_name": client_name, "lifespan": lifespan},
    )


def delete_refresh_token(client, *, refresh_token_id: str) -> dict:
    """Delete a single refresh token by its ID.

    Sends ``auth/delete_refresh_token`` via WebSocket.
    ``refresh_token_id`` must be a non-empty string.
    """
    if not refresh_token_id:
        raise ValueError("refresh_token_id must be a non-empty string")
    return client.ws_call(
        "auth/delete_refresh_token",
        {"refresh_token_id": refresh_token_id},
    )


def delete_all_refresh_tokens(
    client,
    *,
    delete_current_token: bool = False,
    token_type: str | None = None,
) -> dict:
    """Delete all refresh tokens, optionally filtered by type.

    Sends ``auth/delete_all_refresh_tokens`` via WebSocket.

    ``delete_current_token`` — if ``True``, also deletes the token used
    by the current session (defaults to ``False``).

    ``token_type`` — when supplied must be one of
    ``"normal"``, ``"system"``, or ``"long_lived_access_token"``.
    Pass ``None`` (the default) to delete across all types.
    """
    if token_type is not None and token_type not in _VALID_TOKEN_TYPES:
        raise ValueError(
            f"token_type must be one of {sorted(_VALID_TOKEN_TYPES)}, "
            f"got {token_type!r}"
        )
    payload: dict = {"delete_current_token": delete_current_token}
    if token_type is not None:
        payload["token_type"] = token_type
    return client.ws_call("auth/delete_all_refresh_tokens", payload)


def set_refresh_token_expiry(
    client,
    *,
    refresh_token_id: str,
    enable_expiry: bool,
) -> dict:
    """Enable or disable expiry for a specific refresh token.

    Sends ``auth/refresh_token_set_expiry`` via WebSocket.
    ``refresh_token_id`` must be a non-empty string.
    """
    if not refresh_token_id:
        raise ValueError("refresh_token_id must be a non-empty string")
    return client.ws_call(
        "auth/refresh_token_set_expiry",
        {"refresh_token_id": refresh_token_id, "enable_expiry": enable_expiry},
    )


def sign_path(client, *, path: str, expires: int = 30) -> dict:
    """Return a signed URL path for temporary, unauthenticated access.

    Sends ``auth/sign_path`` via WebSocket with ``{path, expires}``.

    ``path`` must be a non-empty string (e.g. ``"/api/camera_proxy/..."``).
    ``expires`` is the validity window in seconds and must be positive
    (default 30).

    Returns a dict containing ``path`` — the signed URL path.
    """
    if not path:
        raise ValueError("path must be a non-empty string")
    if expires <= 0:
        raise ValueError("expires must be a positive integer (seconds)")
    return client.ws_call(
        "auth/sign_path",
        {"path": path, "expires": expires},
    )
