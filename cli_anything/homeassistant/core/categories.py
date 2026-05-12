"""Category registry CRUD.

WS namespace: ``config/category_registry/*``. Each category has:
  category_id, name, icon?, created_at, modified_at.

Categories are scoped to an entity-collection (e.g. "automation",
"script", "todo"). They provide a way to group/label entries within
that scope without affecting other scopes.
"""

from __future__ import annotations

from typing import Any, Optional


# ────────────────────────────────────────────────────────────────────────────
# Internal helper
# ────────────────────────────────────────────────────────────────────────────

def _require_non_empty(value: str, name: str) -> None:
    """Raise ValueError if *value* is falsy (empty string, None, etc.)."""
    if not value:
        raise ValueError(f"{name} must be a non-empty string")


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────

def list_categories(client, *, scope: str) -> list[dict]:
    """Return all category records for *scope*.

    ``scope`` is the entity-collection identifier (e.g. ``"automation"``,
    ``"script"``, ``"todo"``).  A non-empty value is required — HA's WS
    command maps it directly to the registry lookup key.

    Returns a list of category dicts as sent by HA.
    """
    _require_non_empty(scope, "scope")
    data = client.ws_call("config/category_registry/list", {"scope": scope})
    return list(data) if isinstance(data, list) else []


def create_category(client, *, scope: str, name: str,
                    icon: Optional[str] = None) -> dict[str, Any]:
    """Create a new category in *scope*.

    ``scope`` and ``name`` are both required non-empty strings.
    ``icon`` is optional (e.g. ``"mdi:tag"``).

    Returns the newly created category dict.
    """
    _require_non_empty(scope, "scope")
    _require_non_empty(name, "name")
    payload: dict[str, Any] = {"scope": scope, "name": name}
    if icon is not None:
        payload["icon"] = icon
    return client.ws_call("config/category_registry/create", payload) or {}


def update_category(client, *, scope: str, category_id: str,
                    name: Optional[str] = None,
                    icon: Optional[str] = None) -> dict[str, Any]:
    """Update an existing category identified by *scope* + *category_id*.

    At least one of ``name`` or ``icon`` must be provided.

    Returns the updated category dict.
    """
    _require_non_empty(scope, "scope")
    _require_non_empty(category_id, "category_id")
    if name is None and icon is None:
        raise ValueError(
            "at least one of name or icon must be supplied to update_category"
        )
    payload: dict[str, Any] = {"scope": scope, "category_id": category_id}
    if name is not None:
        payload["name"] = name
    if icon is not None:
        payload["icon"] = icon
    return client.ws_call("config/category_registry/update", payload) or {}


def delete_category(client, *, scope: str, category_id: str) -> Any:
    """Delete the category identified by *scope* + *category_id*.

    Returns whatever HA sends back (typically ``None`` / empty on success).
    """
    _require_non_empty(scope, "scope")
    _require_non_empty(category_id, "category_id")
    return client.ws_call(
        "config/category_registry/delete",
        {"scope": scope, "category_id": category_id},
    )


# ────────────────────────────────────────────────────────────────────────────
# Convenience
# ────────────────────────────────────────────────────────────────────────────

def categories_by_name(client, *, scope: str) -> dict[str, dict]:
    """Return a ``{name: full_record}`` mapping for all categories in *scope*.

    Calls :func:`list_categories` internally; validation of *scope* is
    delegated to that function.
    """
    records = list_categories(client, scope=scope)
    return {record["name"]: record for record in records if "name" in record}
