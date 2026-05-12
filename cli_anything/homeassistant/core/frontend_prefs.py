"""Frontend user-data preferences and template rendering helpers.

Wraps two HA subsystems:

1. **Frontend user-data storage** — per-user key/value blobs persisted in
   ``.storage/frontend.user_data_<user_id>``.  Any JSON-serialisable value
   is accepted. Exposed via two WS commands:

     frontend/get_user_data  — read one key or the whole store
     frontend/set_user_data  — write a single key/value pair

2. **Template rendering** — two surfaces:

   * ``render_template`` — single-shot REST POST to ``/api/template``.
     Returns the rendered string immediately.

   * ``start_template_preview`` — WS subscription ``template/start_preview``
     that streams live re-renders whenever referenced entities change.
     **This unit only sends the initial WS subscription message** (recorded
     in ``client.ws_calls``).  Callers that want the event stream must
     consume it via ``client.ws_subscribe`` (or equivalent); see docstring.

WS message types covered:
  frontend/get_user_data
  frontend/set_user_data
  template/start_preview

REST endpoint covered:
  POST /api/template
"""

from __future__ import annotations

import json


# ════════════════════════════════════════════════════════════════════════
# Frontend user-data — persistent per-user key/value store
# ════════════════════════════════════════════════════════════════════════

def get_user_data(client, *, key: str | None = None) -> dict:
    """Fetch frontend user-data via WS ``frontend/get_user_data``.

    When *key* is given, returns ``{"value": <stored value>}``; when
    omitted the whole user-data store is returned as ``{"value": {...}}``.

    HA schema: ``{type: frontend/get_user_data, key?: str}``
    """
    payload: dict = {}
    if key is not None:
        payload["key"] = key
    return client.ws_call("frontend/get_user_data", payload)


def set_user_data(client, *, key: str, value) -> dict:
    """Write a key/value pair to the frontend user-data store.

    Uses WS ``frontend/set_user_data``.

    Validation:
        - *key* must be a non-empty string.
        - *value* must be JSON-serialisable (bool, str, int, float,
          dict, list, or None — matching HA's own vol.Any schema).

    HA schema: ``{type: frontend/set_user_data, key: str, value: any}``
    """
    if not key:
        raise ValueError("key must be a non-empty string")
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"value must be JSON-serialisable (bool/str/int/float/dict/list/None), "
            f"got {type(value).__name__!r}: {exc}"
        ) from exc
    return client.ws_call("frontend/set_user_data", {"key": key, "value": value})


# ════════════════════════════════════════════════════════════════════════
# Template rendering
# ════════════════════════════════════════════════════════════════════════

def render_template(
    client,
    *,
    template: str,
    variables: dict | None = None,
    timeout: float | None = None,
) -> str:
    """Render a Jinja2 template via REST POST ``/api/template``.

    This is a **single-shot** render — HA evaluates the template once
    and returns the rendered string.  For live re-rendering tied to
    entity state changes, use ``start_template_preview`` instead.

    Args:
        template:  The Jinja2 template string.
        variables: Optional mapping of extra variables injected into the
                   template context (passed as ``variables`` in the POST body).
        timeout:   Optional render timeout in seconds (passed as ``timeout``
                   in the POST body).  Omit to use HA's default.

    Returns:
        The rendered string returned by HA.

    Validation:
        - *template* must be a non-empty string.
    """
    if not template:
        raise ValueError("template must be a non-empty string")
    payload: dict = {"template": template}
    if variables is not None:
        payload["variables"] = variables
    if timeout is not None:
        payload["timeout"] = timeout
    result = client.post("api/template", payload)
    # HA returns the rendered text as a plain string; FakeClient may return a
    # dict stub in tests.  Coerce to str for a consistent return type.
    return result if isinstance(result, str) else str(result)


def start_template_preview(
    client,
    *,
    template: str,
    variables: dict | None = None,
    on_event=None,
) -> None:
    """Start a live template-preview subscription via WS ``template/start_preview``.

    HA's ``template/start_preview`` is a **subscription** command: the server
    streams ``event`` messages whenever any entity referenced by the template
    changes state.  This function sends only the *initial* subscription
    message (which is recorded in ``client.ws_calls`` for testability).

    Full streaming:
        To receive the streamed events in a real client, pass your handler
        to ``client.ws_subscribe`` *instead* of (or in addition to) calling
        this function.  Example::

            sub_id = client.ws_subscribe(
                "template/start_preview",
                {"template": template, "variables": variables or {}},
                callback=on_event,
            )

    The *on_event* parameter is accepted for forward-compatibility but is
    NOT wired up in this thin wrapper — callers must handle subscription
    plumbing themselves.

    Args:
        template:  The Jinja2 template string to preview.
        variables: Optional variable dict injected into the template context.
        on_event:  Optional callback (ignored here — see note above).

    Returns:
        None.  In a real implementation the subscription id would be returned.

    Validation:
        - *template* must be a non-empty string.
    """
    if not template:
        raise ValueError("template must be a non-empty string")
    payload: dict = {"template": template}
    if variables is not None:
        payload["variables"] = variables
    # Record the subscription initiation in ws_calls so orchestrators and
    # tests can assert on it.  Full streaming requires ws_subscribe on the
    # real client; FakeClient does not model subscription event streams.
    client.ws_call("template/start_preview", payload)
    return None
