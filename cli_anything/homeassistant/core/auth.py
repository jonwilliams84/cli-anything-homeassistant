"""Auth-related operations: long-lived access tokens, user list."""

from __future__ import annotations

from datetime import timedelta
from typing import Any


def list_users(client) -> list[dict]:
    """Return all HA users (admin only)."""
    data = client.ws_call("config/auth/list")
    return list(data) if isinstance(data, list) else []


def create_long_lived_token(
    client,
    client_name: str,
    lifespan_days: int = 3650,
    client_icon: str | None = None,
) -> str:
    """Create a long-lived access token under the active user.

    Returns the new token string. Caller is responsible for storing it
    securely — HA will not show it again.
    """
    if not client_name:
        raise ValueError("client_name is required")
    payload: dict[str, Any] = {
        "client_name": client_name,
        "lifespan": int(lifespan_days),
    }
    if client_icon:
        payload["client_icon"] = client_icon
    return client.ws_call("auth/long_lived_access_token", payload)
