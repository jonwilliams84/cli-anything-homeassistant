"""Trace introspection — thin wrappers over the HA trace WebSocket API.

All three commands below are admin-only in HA and operate on the
``trace`` component's storage. They do NOT include breakpoint or
step-debugger commands (those belong to the in-flight script debugger,
not the persisted-trace surface).

Supported WS message types:
  trace/list      — list trace summaries for a domain/item
  trace/get       — fetch the full trace for one run
  trace/contexts  — enumerate run contexts (context_id → trace coords)
"""

from __future__ import annotations

_VALID_DOMAINS = frozenset({"automation", "script"})


def _validate_domain(domain: str) -> None:
    """Raise ValueError when *domain* is not a valid trace domain."""
    if domain not in _VALID_DOMAINS:
        raise ValueError(
            f"domain must be one of {sorted(_VALID_DOMAINS)}, got {domain!r}"
        )


def _validate_item_id(item_id: str) -> None:
    """Raise ValueError when *item_id* is empty."""
    if not item_id:
        raise ValueError("item_id must be a non-empty string")


def list_traces(
    client,
    *,
    domain: str | None = None,
    item_id: str | None = None,
) -> list[dict]:
    """Return trace summaries via WS ``trace/list``.

    HA requires *domain* (``"automation"`` or ``"script"``); *item_id* is
    optional. When *domain* is ``None`` and *item_id* is ``None`` the call
    is made without either filter — callers should pass *domain* in practice
    because HA's WS schema marks it as required.

    Validation:
        - *domain* when supplied must be ``"automation"`` or ``"script"``.
        - *item_id* when supplied must be non-empty.
    """
    payload: dict = {}
    if domain is not None:
        _validate_domain(domain)
        payload["domain"] = domain
    if item_id is not None:
        _validate_item_id(item_id)
        payload["item_id"] = item_id
    result = client.ws_call("trace/list", payload)
    return result if isinstance(result, list) else []


def get_trace(
    client,
    *,
    domain: str,
    item_id: str,
    run_id: str,
) -> dict:
    """Return the full trace dict for one run via WS ``trace/get``.

    All three parameters are required by the HA WS schema.

    Validation:
        - *domain* must be ``"automation"`` or ``"script"``.
        - *item_id* must be non-empty.
        - *run_id* must be non-empty.
    """
    _validate_domain(domain)
    _validate_item_id(item_id)
    if not run_id:
        raise ValueError("run_id must be a non-empty string")
    result = client.ws_call(
        "trace/get",
        {"domain": domain, "item_id": item_id, "run_id": run_id},
    )
    return result if isinstance(result, dict) else {}


def list_contexts(
    client,
    *,
    domain: str | None = None,
    item_id: str | None = None,
) -> dict:
    """Return a mapping of context_id → trace coordinates via WS ``trace/contexts``.

    HA's schema uses ``vol.Inclusive`` so *domain* and *item_id* must be
    supplied together or not at all.

    Returns a dict keyed by ``context_id`` with values containing
    ``domain``, ``item_id``, and ``run_id``.

    Validation:
        - *domain* when supplied must be ``"automation"`` or ``"script"``.
        - *item_id* when supplied must be non-empty.
        - Exactly one of (*domain*, *item_id*) must not be supplied alone
          (HA's ``vol.Inclusive`` requires both or neither).
    """
    if (domain is None) != (item_id is None):
        raise ValueError(
            "domain and item_id must be supplied together or both omitted"
        )
    payload: dict = {}
    if domain is not None:
        _validate_domain(domain)
        payload["domain"] = domain
    if item_id is not None:
        _validate_item_id(item_id)
        payload["item_id"] = item_id
    result = client.ws_call("trace/contexts", payload)
    return result if isinstance(result, dict) else {}
