"""Dynalite — the ``dynalite`` integration's WebSocket config-panel surface.

THE GAP THIS CLOSES
    Dynalite is the Australian RS-485 lighting bus, bundled with HA as an
    ordinary integration — and it is the LAST HA-bundled integration that
    registers its own websocket commands without a matching harness group:
    a diff of `websocket_command(` registrations in 2025.1.4 against the
    core modules left exactly two commands (the v1.60 pass closed the last
    seven, LCN). Both belong to the `dynalite` configuration panel:

    ``dynalite/get-config``  — the config of every Dynalite entry (filtered
                               to the keys the panel reads/writes) plus the
                               panel's built-in defaults
    ``dynalite/save-config`` — REPLACE the entry's whole data with the sent
                               config (validated against ``BRIDGE_SCHEMA``)

    The generic websocket_api commands that were also uncovered in the same
    diff (``get_states``/``get_services``/``fire_event``/…) are already
    reachable through the harness's REST surface, so they are NOT gap.

THE WRITE IS A REPLACE, NOT A PATCH
    ``save-config`` calls ``hass.config_entries.async_update_entry`` with
    the message's config — the ENTIRE entry data goes, same class of
    footgun as Supervisor's options POST (v1.52) and the powercalc options
    flow. The default (:meth:`save` without ``replace=True``) therefore
    reads the entry's current config back and MERGES the new keys on top;
    ``--replace`` on the CLI sends exactly what was given, for the one
    case where you mean it. A write is confirmation-gated in the CLI.

WHEN THE INTEGRATION IS NOT LOADED
    The commands are registered by the Dynalite integration's setup, so on
    an instance with no Dynalite entry they answer ``unknown_command`` —
    the same code a typo gets. Every function raises :data:`ABSENT_NOTE`,
    which names the remedy; ``dynalite available`` turns the same
    condition into an answer with exit 0 (a read — 'no' is an answer).

SILENT FAILURE, THE HA WAY
    A ``save-config`` for an entry id that does not exist is NOT an error
    frame: the upstream handler logs it and answers ``result: {"error":
    True}`` with the success flag still set. :meth:`save` catches that
    shape and raises an error naming the id and `dynalite get-config`,
    because an empty dict with no exception is indistinguishable from a
    write that succeeded.
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

DOMAIN = "dynalite"

#: ``unknown_command`` means the ``dynalite`` integration never set up:
#: usually no Dynalite bridge/entry is configured. Nothing in this group
#: works without it.
ABSENT_NOTE = (
    "This Home Assistant has no Dynalite bridge configured: the `dynalite` "
    "integration is not set up, so it never registered its `dynalite/…` "
    "websocket commands. Confirm it independently with `system components` "
    "— and set up the integration in the HA UI (Settings → Devices & "
    "Services → Add Integration → Dynalite, pointing it at the bridge's "
    "host and port) first."
)

#: The message produced when the merged/sent config has no ``host`` — the
#: one key ``BRIDGE_SCHEMA`` requires. Checked client-side so the refusal
#: names the CLI forms instead of HA's schema text.
HOST_REQUIRED = (
    "config has no 'host': the bridge's hostname/IP is the one key HA "
    "REQUIRES on every Dynalite entry. Add it with --set host=… (or merge "
    "into an entry that already has one — `dynalite get-config` shows it)."
)

#: The keys HA's ``save-config`` handler keeps — ``RELEVANT_CONFS`` in
#: ``components/dynalite/panel.py``. Everything else is DROPPED silently
#: upstream, so the client refuses it instead of letting it vanish.
RELEVANT_CONFS = (
    "name",
    "host",
    "port",
    "autodiscover",
    "area",
    "default",
    "active",
    "preset",
    "template",
)

#: The keys ``get-config`` returns under ``default`` — the panel's
#: built-ins (device classes for covers, default entry name and port).
DEFAULT_KEYS = ("DEFAULT_NAME", "DEVICE_CLASSES", "DEFAULT_PORT")


# ── plumbing ────────────────────────────────────────────────────────────────


def _is_absent(exc: HomeAssistantError) -> bool:
    return exc.code == "unknown_command"


def _raise_absent() -> None:
    raise HomeAssistantError(ABSENT_NOTE, code="unknown_command")


def _ws(client, msg_type: str, payload: dict | None = None) -> Any:
    """One ``dynalite/…`` websocket call, with the absent-integration guard."""
    try:
        return client.ws_call(msg_type, payload)
    except HomeAssistantError as exc:
        if _is_absent(exc):
            _raise_absent()
        raise


def check_keys(config: dict) -> dict:
    """Client-side validation of the keys a ``save-config`` carries.

    Checks the two things that fail SILENTLY or confuse upstream:
    * ``config`` is a non-empty JSON object;
    * every key is one of :data:`RELEVANT_CONFS` — HA drops the rest
      without a word.

    Structural checks only: host reachability, port ranges, the area/
    preset/template sub-schemas are HA's ``BRIDGE_SCHEMA`` and its refusal
    names the offending key.
    """
    if not isinstance(config, dict):
        raise ValueError(
            "config must be a JSON object (merge with --set or send one "
            "with --data/--replace), "
            f"got {type(config).__name__}"
        )
    if not config:
        raise ValueError(
            "config is empty — nothing to save. Give at least one key "
            "with --set or a --data object."
        )
    unknown = sorted(k for k in config if k not in RELEVANT_CONFS)
    if unknown:
        raise ValueError(
            "unknown config key(s) "
            + ", ".join(repr(k) for k in unknown)
            + ": the save handler keeps only "
            + ", ".join(RELEVANT_CONFS)
            + " and DROPS the rest silently. Remove them."
        )
    return config


def check_config(config: dict) -> dict:
    """``check_keys`` PLUS the host the merged config must end up with.

    ``host`` is the one key HA's ``BRIDGE_SCHEMA`` REQUIRES. It is only
    checked on the config that will actually be SENT — the merged one in
    merge mode, so a delta without a host is fine when the entry already
    has one — and refused before the wire otherwise, with the CLI forms
    named instead of HA's schema text.
    """
    check_keys(config)
    if not (config.get("host") or "").strip():
        raise ValueError(HOST_REQUIRED)
    return config


def merge_config(current: dict, updates: dict) -> dict:
    """Overlay *updates* on the entry's current config.

    A key set to ``None`` DELETES: HA reads an explicit null as "back to
    the default", mirroring Supervisor's options semantics — except that
    here the whole data object is replaced anyway, so a dropped key is
    simply absent from the new data.
    """
    if not isinstance(updates, dict):
        raise ValueError(f"updates must be a JSON object, got {type(updates).__name__}")
    merged = {k: v for k, v in (current or {}).items() if v is not None}
    for key, value in updates.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


# ── availability ────────────────────────────────────────────────────────────


def available(client) -> dict:
    """Is the ``dynalite`` integration set up? A READ — 'no' is an answer.

    Checks the integration's presence in the loaded-components list (the
    same independent confirmation the error note points at), so the answer
    never depends on a websocket round-trip to a command that does not
    exist.
    """
    cfg = client.ws_call("get_config") or {}
    loaded = DOMAIN in (cfg.get("components") or [])
    return {
        "available": loaded,
        "note": (
            "dynalite is loaded; every `dynalite` command works here." if loaded else ABSENT_NOTE
        ),
    }


# ── read ────────────────────────────────────────────────────────────────────


def read(client) -> dict:
    """WS ``dynalite/get-config`` — every entry's config plus the defaults.

    Returns the panel's whole view: ``config`` (one object per Dynalite
    config entry, keyed by entry_id) and ``default`` (the panel's
    built-ins — default entry name and port, the cover device classes an
    area's ``class`` may take). The per-entry config contains EXACTLY the
    keys :data:`RELEVANT_CONFS` — which is precisely what a later
    :meth:`save` accepts, so a read is a valid template for a write.
    """
    return _ws(client, "dynalite/get-config", {})


# ── write ───────────────────────────────────────────────────────────────────


def save(client, entry_id: str, config: dict, *, replace: bool = False) -> dict:
    """WS ``dynalite/save-config`` — write an entry's whole config.

    HA REPLACES the entry's data with *config* (filtered to
    :data:`RELEVANT_CONFS`). The default is a MERGE: the entry's current
    config is read with :meth:`read` first and *config* is overlaid on
    top, so you change one key without wiping the areas, presets and
    templates you never named. ``replace=True`` sends *config* verbatim —
    for the rare case you really want to hand-write the whole entry.

    An entry id HA does not know answers ``{"error": True}`` with the
    success flag still set; it is surfaced here as an error naming the id
    and `dynalite get-config`.
    """
    check_keys(config)
    if not replace:
        current = read(client).get("config") or {}
        if entry_id not in current:
            raise ValueError(
                f"no Dynalite entry with id {entry_id!r} — `dynalite "
                "get-config` lists the ids and their configs"
            )
        config = merge_config(current.get(entry_id) or {}, config)
        check_config(config)
    else:
        check_config(config)
    result = _ws(
        client,
        "dynalite/save-config",
        {"entry_id": entry_id, "config": config},
    )
    if isinstance(result, dict) and result.get("error"):
        raise ValueError(
            f"HA answered error for entry {entry_id!r}: the id does not "
            "exist (this refusal is upstream's silent one — success with "
            "an error flag, not an error frame). List ids with `dynalite "
            "get-config`."
        )
    return {
        "saved": True,
        "entry_id": entry_id,
        "replaced": bool(replace),
        "host": config.get("host"),
        "keys": sorted(config),
    }
