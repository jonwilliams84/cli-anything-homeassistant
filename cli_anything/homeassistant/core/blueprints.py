"""Blueprints CRUD — reusable automation/script/template blueprints.

WS namespace: ``blueprint/*``.  Blueprints live under
``blueprints/<domain>/<path>`` in the HA config directory.  This module
wraps the five WS commands exposed by HA:

  blueprint/list       — list installed blueprints (optionally by domain)
  blueprint/import     — fetch a blueprint from a remote URL
  blueprint/save       — write/overwrite a blueprint from raw YAML
  blueprint/delete     — remove a blueprint file
  blueprint/substitute — render a blueprint with caller-supplied inputs

Domain values: ``'automation'``, ``'script'``, ``'template'``.
"""

from __future__ import annotations

from typing import Any

VALID_DOMAINS = ("automation", "script", "template")


def _check_domain(domain: str) -> None:
    """Raise ValueError if *domain* is not a recognised blueprint domain."""
    if domain not in VALID_DOMAINS:
        raise ValueError(
            f"domain must be one of {VALID_DOMAINS}, got {domain!r}"
        )


def list_blueprints(client, domain: str | None = None) -> dict:
    """List installed blueprints, optionally filtered by *domain*.

    `domain` accepts positional OR keyword form. Validates against
    ``'automation' | 'script' | 'template'``.

    Prefer `list_blueprints_kw` in new code; this variant exists for back-compat
    with the legacy positional form.

    Returns the raw HA response (a dict keyed by path / by domain).
    """
    if domain is not None:
        _check_domain(domain)
        payload: dict[str, Any] = {"domain": domain}
    else:
        payload = {}
    data = client.ws_call("blueprint/list", payload)
    return data if isinstance(data, dict) else {}


def list_blueprints_kw(client, *, domain: str | None = None) -> dict:
    """Kwarg-only variant of list_blueprints — preferred for new code."""
    return list_blueprints(client, domain)


def import_blueprint(client, *, url: str) -> dict:
    """Import a blueprint from a remote URL (GitHub, gist, raw file …).

    *url* must be non-empty and start with ``http://`` or ``https://``.

    Returns ``{suggested_filename, raw_data, blueprint, validation_errors,
    exists}`` as sent back by HA.
    """
    if not url:
        raise ValueError("url is required and must be non-empty")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(
            "url must start with http:// or https://"
        )
    return client.ws_call("blueprint/import", {"url": url}) or {}


def save_blueprint(
    client,
    *,
    domain: str,
    path: str,
    yaml: str,
    source_url: str | None = None,
) -> dict:
    """Persist a blueprint from raw YAML to ``blueprints/<domain>/<path>.yaml``.

    *domain* — one of ``'automation'``, ``'script'``, ``'template'``.
    *path*   — relative filename (e.g. ``'my_blueprint'``); non-empty.
    *yaml*   — raw YAML text of the blueprint; non-empty.
    *source_url* — optional originating URL stored in the blueprint metadata.

    Returns ``{"overrides_existing": bool}`` on success.
    """
    _check_domain(domain)
    if not path:
        raise ValueError("path is required and must be non-empty")
    if not yaml:
        raise ValueError("yaml is required and must be non-empty")
    payload: dict[str, Any] = {
        "domain": domain,
        "path": path,
        "yaml": yaml,
    }
    if source_url is not None:
        payload["source_url"] = source_url
    return client.ws_call("blueprint/save", payload) or {}


def delete_blueprint(client, *, domain: str, path: str) -> Any:
    """Delete the blueprint at ``blueprints/<domain>/<path>``.

    *domain* — one of ``'automation'``, ``'script'``, ``'template'``.
    *path*   — relative path of the blueprint file; non-empty.
    """
    _check_domain(domain)
    if not path:
        raise ValueError("path is required and must be non-empty")
    return client.ws_call(
        "blueprint/delete", {"domain": domain, "path": path}
    )


def substitute_blueprint(
    client,
    *,
    domain: str,
    path: str,
    inputs: dict,
) -> dict:
    """Render a blueprint with caller-supplied *inputs* variables.

    *domain* — one of ``'automation'``, ``'script'``, ``'template'``.
    *path*   — relative path of the blueprint file; non-empty.
    *inputs* — dict mapping blueprint input keys to values.

    Returns ``{"substituted_config": <rendered config>}`` on success.
    """
    _check_domain(domain)
    if not path:
        raise ValueError("path is required and must be non-empty")
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be a dict")
    return client.ws_call(
        "blueprint/substitute",
        {"domain": domain, "path": path, "input": inputs},
    ) or {}


# ─────────────────────────────────────────────────────── compat / shortcuts

def show(client, domain: str, path: str) -> dict | None:
    """Return a single blueprint dict by domain+path, or None if not found.

    Convenience over ``list_blueprints`` — many flows want "give me one
    blueprint by name" rather than the full mapping.
    """
    _check_domain(domain)
    if not path:
        raise ValueError("path is required and must be non-empty")
    blueprints = list_blueprints(client, domain) or {}
    return blueprints.get(path)


def substitute(client, *, domain: str, path: str,
                 user_input: dict | None = None,
                 input: dict | None = None,
                 inputs: dict | None = None) -> dict:
    """Backwards-compatible alias for ``substitute_blueprint``.

    Accepts the legacy ``user_input=`` and ``input=`` kwargs as well as the new ``inputs=``.
    """
    # Count how many are provided
    provided = sum([
        user_input is not None,
        input is not None,
        inputs is not None,
    ])
    if provided > 1:
        # Check if all provided values are identical
        values = [v for v in [user_input, input, inputs] if v is not None]
        if not all(v == values[0] for v in values):
            raise ValueError("pass only one of `user_input=`, `input=`, or `inputs=`")

    if provided == 0:
        raise ValueError("one of `user_input=`, `input=`, or `inputs=` is required")

    # Get the first non-None value
    payload_input = user_input or input or inputs
    if not isinstance(payload_input, dict):
        raise ValueError("input must be a dict")
    return substitute_blueprint(client, domain=domain, path=path,
                                  inputs=payload_input)
