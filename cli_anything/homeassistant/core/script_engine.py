"""Script-engine primitives — ad-hoc action execution, config validation,
condition testing and entity provenance.

These wrap the four core ``websocket_api`` commands that back Home
Assistant's automation/script *editor* (the "Run actions", "Test
condition" and live-validation buttons in the UI). Together they let an
agent author an automation safely: validate the config, evaluate its
conditions against live state, dry-run its actions, and only then write
it with ``automation save``.

WS commands wrapped
-------------------
* ``execute_script``  — run an arbitrary action sequence (script syntax),
  no ``script.*`` entity required. Returns the run ``context`` plus any
  ``response`` collected from ``response_variable`` actions.
* ``validate_config`` — static + dynamic validation of ``triggers`` /
  ``conditions`` / ``actions`` blocks. Per-key ``{valid, error}``.
* ``test_condition``  — evaluate one condition config against the *current*
  state and return the boolean outcome.
* ``entity/source``   — map every ``entity_id`` to the integration domain
  that supplies it.

All four are admin-only on the HA side except ``entity/source``.

Public API
----------
* :func:`execute_script`
* :func:`build_service_action`
* :func:`run_service_action`
* :func:`validate_config`
* :func:`normalize_automation_config`
* :func:`validate_automation_config`
* :func:`validate_script_config`
* :func:`test_condition`
* :func:`condition_holds`
* :func:`test_conditions`
* :func:`entity_source`
* :func:`entity_source_for`
* :func:`sources_by_integration`
"""

from __future__ import annotations

from typing import Any

# Automation configs accept both the modern plural keys and the legacy
# singular ones. `validate_config` only speaks plural, so we translate.
_LEGACY_KEYS = {
    "trigger": "triggers",
    "condition": "conditions",
    "action": "actions",
}
_VALIDATE_KEYS = ("triggers", "conditions", "actions")


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────


def _ensure_sequence(sequence: Any) -> list[dict]:
    """Coerce ``sequence`` into a non-empty list of action mappings."""
    if isinstance(sequence, dict):
        sequence = [sequence]
    if not isinstance(sequence, list):
        raise ValueError("sequence must be a list of action mappings (or a single mapping)")
    if not sequence:
        raise ValueError("sequence must contain at least one action")
    for index, step in enumerate(sequence):
        if not isinstance(step, dict):
            raise ValueError(f"sequence[{index}] must be a mapping, got {type(step).__name__}")
    return sequence


def _ensure_variables(variables: Any) -> dict | None:
    if variables is None:
        return None
    if not isinstance(variables, dict):
        raise ValueError("variables must be a mapping")
    return variables or None


def _ensure_condition(condition: Any) -> dict | str:
    """A condition is a mapping, or a shorthand template string."""
    if isinstance(condition, str):
        if not condition.strip():
            raise ValueError("condition must be a non-empty template string")
        return condition
    if not isinstance(condition, dict):
        raise ValueError("condition must be a mapping (or a shorthand template string)")
    if not condition:
        raise ValueError("condition must not be empty")
    return condition


# ────────────────────────────────────────────────────────────────────────────
# execute_script
# ────────────────────────────────────────────────────────────────────────────


def execute_script(client, sequence, variables: dict | None = None) -> dict:
    """Run an ad-hoc action sequence via the ``execute_script`` WS command.

    ``sequence`` uses the same syntax as a script's ``sequence:`` block —
    service calls, ``delay``, ``wait_template``, ``choose``, ``repeat``,
    ``stop`` … A single action mapping is accepted and wrapped for you.

    Returns HA's result dict: ``{"context": {...}, "response": ...}`` where
    ``response`` carries any ``response_variable`` payload (``None`` when the
    sequence produced no response).
    """
    payload: dict[str, Any] = {"sequence": _ensure_sequence(sequence)}
    variables = _ensure_variables(variables)
    if variables:
        payload["variables"] = variables
    return client.ws_call("execute_script", payload) or {}


def build_service_action(
    action: str,
    *,
    data: dict | None = None,
    target: dict | None = None,
    response_variable: str | None = None,
) -> dict:
    """Build a single ``action:`` step for :func:`execute_script`.

    ``action`` is a ``domain.service`` string (HA's modern spelling of what
    used to be ``service:``).
    """
    if not isinstance(action, str) or action.count(".") != 1 or not all(action.split(".")):
        raise ValueError(f"action must be 'domain.service', got: {action!r}")
    if data is not None and not isinstance(data, dict):
        raise ValueError("data must be a mapping")
    if target is not None and not isinstance(target, dict):
        raise ValueError("target must be a mapping")
    step: dict[str, Any] = {"action": action}
    if target:
        step["target"] = target
    if data:
        step["data"] = data
    if response_variable:
        if not isinstance(response_variable, str) or not response_variable.strip():
            raise ValueError("response_variable must be a non-empty string")
        step["response_variable"] = response_variable
    return step


def run_service_action(
    client,
    action: str,
    *,
    data: dict | None = None,
    target: dict | None = None,
    response_variable: str | None = None,
    variables: dict | None = None,
) -> dict:
    """Convenience: build one service action and execute it.

    Unlike ``service call`` (REST) this runs through HA's *script engine*,
    so the call is traced, gets a script context, and can return a
    ``response_variable`` payload.
    """
    step = build_service_action(
        action, data=data, target=target, response_variable=response_variable
    )
    return execute_script(client, [step], variables=variables)


# ────────────────────────────────────────────────────────────────────────────
# validate_config
# ────────────────────────────────────────────────────────────────────────────


def validate_config(
    client,
    *,
    triggers: Any = None,
    conditions: Any = None,
    actions: Any = None,
) -> dict:
    """Validate trigger/condition/action blocks without saving anything.

    Wraps the ``validate_config`` WS command. Returns a dict keyed by the
    blocks you supplied, each ``{"valid": bool, "error": str | None}``.
    At least one block must be given.
    """
    payload: dict[str, Any] = {}
    for key, value in (
        ("triggers", triggers),
        ("conditions", conditions),
        ("actions", actions),
    ):
        if value is None:
            continue
        payload[key] = value
    if not payload:
        raise ValueError("supply at least one of triggers / conditions / actions")
    return client.ws_call("validate_config", payload) or {}


def normalize_automation_config(config: dict) -> dict:
    """Return the ``triggers``/``conditions``/``actions`` blocks of a config.

    Accepts both modern plural keys and the legacy singular ``trigger:`` /
    ``condition:`` / ``action:`` spellings (the plural wins if both exist).
    Keys that are absent are omitted entirely so ``validate_config`` doesn't
    report them.
    """
    if not isinstance(config, dict):
        raise ValueError("config must be a mapping")
    out: dict[str, Any] = {}
    for legacy, plural in _LEGACY_KEYS.items():
        if config.get(plural) is not None:
            out[plural] = config[plural]
        elif config.get(legacy) is not None:
            out[plural] = config[legacy]
    return out


def _summarize(result: dict, blocks: dict) -> dict:
    """Fold HA's per-block result into a single verdict + error list."""
    errors: list[dict] = []
    for key in _VALIDATE_KEYS:
        entry = result.get(key)
        if isinstance(entry, dict) and not entry.get("valid", False):
            errors.append({"block": key, "error": entry.get("error") or "invalid"})
    return {
        "valid": not errors,
        "checked": sorted(blocks),
        "results": result,
        "errors": errors,
    }


def validate_automation_config(client, config: dict) -> dict:
    """Validate a whole automation config before writing it.

    Splits the config into its trigger/condition/action blocks (legacy keys
    included), validates each, and folds the answers into
    ``{"valid": bool, "checked": [...], "results": {...}, "errors": [...]}``.

    Intended as the pre-flight for ``automation save``.
    """
    blocks = normalize_automation_config(config)
    if not blocks:
        raise ValueError(
            "config has no triggers/conditions/actions block to validate "
            "(is this an automation config?)"
        )
    return _summarize(validate_config(client, **blocks), blocks)


def validate_script_config(client, config: dict) -> dict:
    """Validate a script config (its ``sequence``) before writing it.

    A bare list of actions is also accepted. Same result shape as
    :func:`validate_automation_config`.
    """
    if isinstance(config, list):
        sequence: Any = config
    elif isinstance(config, dict):
        sequence = config.get("sequence")
        if sequence is None:
            raise ValueError("script config has no 'sequence' block to validate")
    else:
        raise ValueError("config must be a mapping (or a bare action list)")
    blocks = {"actions": sequence}
    return _summarize(validate_config(client, actions=sequence), blocks)


# ────────────────────────────────────────────────────────────────────────────
# test_condition
# ────────────────────────────────────────────────────────────────────────────


def test_condition(client, condition, variables: dict | None = None) -> dict:
    """Evaluate a condition against live state via ``test_condition``.

    Returns HA's raw result — ``{"result": true|false}``. Invalid condition
    configs surface as a ``HomeAssistantError`` from the WS layer.
    """
    payload: dict[str, Any] = {"condition": _ensure_condition(condition)}
    variables = _ensure_variables(variables)
    if variables:
        payload["variables"] = variables
    return client.ws_call("test_condition", payload) or {}


def condition_holds(client, condition, variables: dict | None = None) -> bool:
    """:func:`test_condition` reduced to a plain bool."""
    return bool(test_condition(client, condition, variables=variables).get("result"))


def test_conditions(client, conditions, variables: dict | None = None) -> list[dict]:
    """Evaluate several conditions, one WS call each, error-tolerant.

    Each entry is ``{"index", "condition", "result", "error"}``; a condition
    that fails to validate records ``result: None`` plus the error string
    instead of aborting the whole batch (mirrors ``entity prune``'s
    per-item tolerance).
    """
    if isinstance(conditions, dict) or isinstance(conditions, str):
        conditions = [conditions]
    if not isinstance(conditions, list):
        raise ValueError("conditions must be a list of condition mappings")
    if not conditions:
        raise ValueError("conditions must contain at least one condition")
    out: list[dict] = []
    for index, cond in enumerate(conditions):
        entry: dict[str, Any] = {"index": index, "condition": cond}
        try:
            entry["result"] = bool(test_condition(client, cond, variables=variables).get("result"))
            entry["error"] = None
        except Exception as exc:  # noqa: BLE001 — per-item tolerance is the point
            entry["result"] = None
            entry["error"] = str(exc)
        out.append(entry)
    return out


# ────────────────────────────────────────────────────────────────────────────
# entity/source
# ────────────────────────────────────────────────────────────────────────────


def entity_source(client) -> dict:
    """Return ``{entity_id: {"domain": <integration>}}`` for every entity.

    This is *provenance*: which integration currently supplies the entity —
    distinct from the entity registry (which also lists entities whose
    integration isn't loaded).
    """
    return client.ws_call("entity/source", {}) or {}


def entity_source_for(client, entity_id: str) -> dict | None:
    """Source record for one entity, or ``None`` when it has no live source."""
    if not isinstance(entity_id, str) or "." not in entity_id:
        raise ValueError(f"Expected an entity_id like 'light.kitchen', got: {entity_id!r}")
    return entity_source(client).get(entity_id)


def sources_by_integration(client, integration: str | None = None) -> dict:
    """Group entity ids by the integration that supplies them.

    ``{"hue": ["light.kitchen", ...], "sun": ["sun.sun"]}``, sorted. Pass
    ``integration`` to restrict the result to a single domain (empty dict
    when nothing matches).
    """
    grouped: dict[str, list[str]] = {}
    for entity_id, source in entity_source(client).items():
        domain = (source or {}).get("domain") if isinstance(source, dict) else None
        if not domain:
            domain = "unknown"
        if integration and domain != integration:
            continue
        grouped.setdefault(domain, []).append(entity_id)
    return {domain: sorted(ids) for domain, ids in sorted(grouped.items())}
