"""Device-automation introspection.

Used by the blueprint UI / automation editor to enumerate the triggers,
conditions, and actions a specific device supports, and to fetch the
option schema for any individual trigger, condition, or action.

WS message types wrapped:
  device_automation/trigger/list          — list_triggers
  device_automation/condition/list        — list_conditions
  device_automation/action/list           — list_actions
  device_automation/trigger/capabilities  — trigger_capabilities
  device_automation/condition/capabilities— condition_capabilities
  device_automation/action/capabilities   — action_capabilities

Convenience:
  summarise_device  — calls the three list_* functions in parallel and
                      returns a combined dict with keys ``triggers``,
                      ``conditions``, and ``actions``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed


# ════════════════════════════════════════════════════════════════════════
# List helpers — enumerate what a device supports
# ════════════════════════════════════════════════════════════════════════

def list_triggers(client, *, device_id: str) -> list:
    """List the trigger descriptors supported by ``device_id``.

    Sends ``device_automation/trigger/list`` with ``{device_id}``.
    Raises :class:`ValueError` when ``device_id`` is empty.
    Returns the list of trigger descriptors from HA.
    """
    if not device_id:
        raise ValueError("device_id is required")
    return client.ws_call(
        "device_automation/trigger/list",
        {"device_id": device_id},
    )


def list_conditions(client, *, device_id: str) -> list:
    """List the condition descriptors supported by ``device_id``.

    Sends ``device_automation/condition/list`` with ``{device_id}``.
    Raises :class:`ValueError` when ``device_id`` is empty.
    Returns the list of condition descriptors from HA.
    """
    if not device_id:
        raise ValueError("device_id is required")
    return client.ws_call(
        "device_automation/condition/list",
        {"device_id": device_id},
    )


def list_actions(client, *, device_id: str) -> list:
    """List the action descriptors supported by ``device_id``.

    Sends ``device_automation/action/list`` with ``{device_id}``.
    Raises :class:`ValueError` when ``device_id`` is empty.
    Returns the list of action descriptors from HA.
    """
    if not device_id:
        raise ValueError("device_id is required")
    return client.ws_call(
        "device_automation/action/list",
        {"device_id": device_id},
    )


# ════════════════════════════════════════════════════════════════════════
# Capabilities — option schema for a specific descriptor
# ════════════════════════════════════════════════════════════════════════

def trigger_capabilities(client, *, trigger: dict) -> dict:
    """Return the option schema for a specific trigger descriptor.

    ``trigger`` must be a non-empty dict (one of the items returned by
    :func:`list_triggers`). Raises :class:`ValueError` when ``trigger``
    is empty or not a dict.

    Sends ``device_automation/trigger/capabilities`` with ``{trigger}``.
    """
    if not isinstance(trigger, dict) or not trigger:
        raise ValueError("trigger must be a non-empty dict")
    return client.ws_call(
        "device_automation/trigger/capabilities",
        {"trigger": trigger},
    )


def condition_capabilities(client, *, condition: dict) -> dict:
    """Return the option schema for a specific condition descriptor.

    ``condition`` must be a non-empty dict (one of the items returned by
    :func:`list_conditions`). Raises :class:`ValueError` when
    ``condition`` is empty or not a dict.

    Sends ``device_automation/condition/capabilities`` with
    ``{condition}``.
    """
    if not isinstance(condition, dict) or not condition:
        raise ValueError("condition must be a non-empty dict")
    return client.ws_call(
        "device_automation/condition/capabilities",
        {"condition": condition},
    )


def action_capabilities(client, *, action: dict) -> dict:
    """Return the option schema for a specific action descriptor.

    ``action`` must be a non-empty dict (one of the items returned by
    :func:`list_actions`). Raises :class:`ValueError` when ``action``
    is empty or not a dict.

    Sends ``device_automation/action/capabilities`` with ``{action}``.
    """
    if not isinstance(action, dict) or not action:
        raise ValueError("action must be a non-empty dict")
    return client.ws_call(
        "device_automation/action/capabilities",
        {"action": action},
    )


# ════════════════════════════════════════════════════════════════════════
# Convenience — full device summary in one shot
# ════════════════════════════════════════════════════════════════════════

def summarise_device(client, *, device_id: str) -> dict:
    """Return triggers, conditions, and actions for ``device_id`` as one dict.

    Calls :func:`list_triggers`, :func:`list_conditions`, and
    :func:`list_actions` in parallel (via a thread pool) and aggregates
    the results::

        {
            "triggers":   [...],
            "conditions": [...],
            "actions":    [...],
        }

    Raises :class:`ValueError` when ``device_id`` is empty (propagated
    from the individual list functions).
    """
    if not device_id:
        raise ValueError("device_id is required")

    tasks = {
        "triggers":   lambda: list_triggers(client, device_id=device_id),
        "conditions": lambda: list_conditions(client, device_id=device_id),
        "actions":    lambda: list_actions(client, device_id=device_id),
    }

    results: dict = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(futures):
            key = futures[future]
            results[key] = future.result()

    return {
        "triggers":   results["triggers"],
        "conditions": results["conditions"],
        "actions":    results["actions"],
    }
