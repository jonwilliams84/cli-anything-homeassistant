"""Home Assistant Cloud (Nabu Casa): account, subscription, remote UI, Alexa, Google.

THE GAP THIS CLOSES
    Home Assistant Cloud is how most instances get a public URL, Alexa and
    Google Assistant. The harness could already see the *result* of it —
    `network urls` reports the `cloud_url`, `webhook cloudhooks` lists the
    hooks it created, `expose list` shows which entities are exposed to
    `cloud.alexa` / `cloud.google_assistant` — and could not ask the cloud
    itself anything. Whether the account was even logged in, whether the
    subscription had expired, whether remote access was connected: all
    invisible. That is the wrong half. `expose set --assistant cloud.alexa`
    does nothing observable if `alexa_enabled` is false, and nothing in this
    harness could say so.

"NOT LOGGED IN" IS AN ANSWER TO A QUESTION, AND AN OBSTACLE TO AN ACTION
    Home Assistant guards most of these commands with `_require_cloud_login`,
    which fails them with the code `not_logged_in`. This module splits on what
    the caller was trying to do:

      * READ commands (`status`, `subscription`, `alexa_entities`,
        `google_entities`, …) return a normal dict with `logged_in: false` and
        the payload key set to `None`. Not being signed in is a true and
        complete answer to "what is my subscription" — the answer is "there
        isn't one" — and an agent polling status should not have to catch an
        exception to learn it.
      * WRITE commands (`set_prefs`, `alexa_sync`, `remote_connect`,
        `remote_disconnect`, `google_set_2fa`) raise `ValueError` naming the
        remedy. Here it is not an answer, it is the reason nothing happened,
        and it must not be swallowed into a success-shaped return.

    Both paths are driven by the error CODE (`HomeAssistantError.code`), never
    by matching the message text.

MEASURED AGAINST THE SOURCE, NOT A LIVE ACCOUNT — SAY SO
    Every payload and response shape here was read off HA's
    `components/cloud/http_api.py`. They were NOT exercised against a live
    Nabu Casa account: the `cloud` integration depends on `assist_pipeline`,
    whose `pyspeex-noise` wheel does not build in this environment, so the
    test instance cannot even load it. The unit tests pin the wire payloads
    with `FakeClient`; the e2e tests skip cleanly on `unknown_command` rather
    than pretending. Treat the response *shapes* as version-sensitive.

WHAT IS DELIBERATELY NOT HERE
    * `cloud/thingtalk/convert` — ThingTalk is a dead feature; the endpoint
      exists but the backing service is gone, so wrapping it would add a
      command whose only outcome is a timeout.
    * `/api/cloud/login`, `/api/cloud/register`, `/api/cloud/forgot_password`,
      `/api/cloud/resend_confirm` — these take an account PASSWORD as an
      argument. A password in argv is a password in the shell history and in
      `ps`; signing in belongs in the UI. `status` reports the result of it.
    * `cloud/cloudhook/create|delete` — already shipped as `webhook
      cloudhook-create` / `cloudhook-delete`. Two commands for one call is
      worse than either.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

#: HA's own code when `_require_cloud_login` refuses a command.
NOT_LOGGED_IN = "not_logged_in"

#: The keys `cloud/update_prefs` accepts, mapped from CLI-friendly names.
#: Note what is ABSENT: `remote_enabled`. Remote access is NOT a preference
#: you can set through this command — HA toggles it with `cloud/remote/connect`
#: and `cloud/remote/disconnect`, which is why `set_prefs` rejects it by name
#: instead of letting voluptuous answer "extra keys not allowed".
PREF_KEYS = (
    "alexa_enabled",
    "alexa_report_state",
    "google_enabled",
    "google_report_state",
    "google_secure_devices_pin",
    "remote_allow_remote_enable",
    "cloud_ice_servers_enabled",
    "tts_default_voice",
)


def _note(logged_in: bool, subject: str) -> str:
    if logged_in:
        return f"{subject} as reported by Home Assistant Cloud."
    return (
        "Not logged in to Home Assistant Cloud, so there is no "
        f"{subject.lower()} to report. Sign in under Settings > Home Assistant "
        "Cloud in the UI — this harness deliberately does not take an account "
        "password on the command line."
    )


def _read(client, command: str, key: str, subject: str, payload: Optional[dict] = None) -> dict:
    """Run a login-guarded READ, turning `not_logged_in` into a named answer."""
    try:
        result = client.ws_call(command, payload)
    except HomeAssistantError as exc:
        if getattr(exc, "code", None) != NOT_LOGGED_IN:
            raise
        return {"logged_in": False, key: None, "note": _note(False, subject)}
    return {"logged_in": True, key: result, "note": _note(True, subject)}


def _write(client, command: str, subject: str, payload: Optional[dict] = None) -> Any:
    """Run a login-guarded WRITE; refuse loudly when not signed in."""
    try:
        return client.ws_call(command, payload)
    except HomeAssistantError as exc:
        if getattr(exc, "code", None) != NOT_LOGGED_IN:
            raise
        raise ValueError(
            f"Cannot {subject}: this instance is not logged in to Home Assistant "
            "Cloud. Sign in under Settings > Home Assistant Cloud in the UI, then "
            "re-run. `cloud status` reports whether it worked."
        ) from exc


# ─────────────────────────────────────────────────────────────────── account


def status(client) -> dict:
    """The cloud account: signed in, connected, subscribed, remote URL.

    `cloud/status` is the one command in this group that is NOT login-guarded,
    so it answers on every instance that has the integration. Logged out it
    returns only three keys (`logged_in`, `cloud`, `http_use_ssl`); logged in
    it returns the full account including `prefs`. Rather than pass that
    difference on, the summary below is always present with `None` for what
    could not be known.

    `cloud` is the IoT CONNECTION state (`connected` / `disconnected`), which
    is not the same as `logged_in`: a valid account whose instance has lost
    the socket is logged in and disconnected, and that pair is precisely the
    "Alexa stopped responding" symptom.
    """
    raw = client.ws_call("cloud/status") or {}
    if not isinstance(raw, dict):
        raise ValueError(f"cloud/status returned {type(raw).__name__}, expected an object")
    prefs = raw.get("prefs") or {}
    logged_in = bool(raw.get("logged_in"))
    return {
        "logged_in": logged_in,
        "email": raw.get("email"),
        "connection": raw.get("cloud"),
        "connected": raw.get("cloud") == "connected",
        "active_subscription": raw.get("active_subscription"),
        "last_disconnect_reason": raw.get("cloud_last_disconnect_reason"),
        "remote": {
            "connected": raw.get("remote_connected"),
            "domain": raw.get("remote_domain"),
            "certificate_status": raw.get("remote_certificate_status"),
            "certificate": raw.get("remote_certificate"),
            "allow_remote_enable": prefs.get("remote_allow_remote_enable"),
        },
        "alexa": {
            "enabled": prefs.get("alexa_enabled"),
            "report_state": prefs.get("alexa_report_state"),
            "registered": raw.get("alexa_registered"),
        },
        "google": {
            "enabled": prefs.get("google_enabled"),
            "report_state": prefs.get("google_report_state"),
            "registered": raw.get("google_registered"),
            "local_connected": raw.get("google_local_connected"),
            "secure_devices_pin_set": bool(prefs.get("google_secure_devices_pin")),
        },
        "prefs": prefs,
        "raw": raw,
        "note": (
            "`connection` is the IoT socket state and is not the same as "
            "`logged_in` — a signed-in instance can be disconnected."
            if logged_in
            else _note(False, "Account")
        ),
    }


def subscription(client) -> dict:
    """The Nabu Casa subscription behind this instance.

    Login-guarded, so a logged-out instance answers `logged_in: false` rather
    than raising. HA answers `request_failed` when it cannot reach the
    subscription service — that is NOT translated, because "we could not ask"
    and "there is no subscription" are different facts.
    """
    return _read(client, "cloud/subscription", "subscription", "Subscription")


def remove_data(client, *, apply: bool = False) -> dict:
    """Erase the local cloud configuration. Dry-run unless `apply=True`.

    Inverted guard, and this is not a typo: `cloud/remove_data` refuses while
    you ARE logged in (code `logged_in`) and only works once signed out. It
    deletes the stored preferences — which entities were exposed to Alexa and
    Google, the Google PIN, every cloudhook — and there is no undo.
    """
    if not apply:
        return {
            "applied": False,
            "would_remove": "the stored Home Assistant Cloud configuration",
            "note": (
                "Dry run. This erases the local cloud config — exposed-entity "
                "settings for Alexa and Google, the secure-devices PIN and the "
                "cloudhook list — with no undo. Re-run with --apply to commit. "
                "HA refuses this while logged IN; sign out first."
            ),
        }
    try:
        client.ws_call("cloud/remove_data")
    except HomeAssistantError as exc:
        if getattr(exc, "code", None) != "logged_in":
            raise
        raise ValueError(
            "Cannot remove cloud data while logged in. Sign out of Home "
            "Assistant Cloud first, then re-run."
        ) from exc
    return {
        "applied": True,
        "removed": "the stored Home Assistant Cloud configuration",
        "note": "Local cloud config erased. Alexa/Google exposure settings are gone.",
    }


# ─────────────────────────────────────────────────────────────────── prefs


def set_prefs(
    client,
    *,
    alexa_enabled: Optional[bool] = None,
    alexa_report_state: Optional[bool] = None,
    google_enabled: Optional[bool] = None,
    google_report_state: Optional[bool] = None,
    google_secure_devices_pin: Optional[str] = None,
    remote_allow_remote_enable: Optional[bool] = None,
    cloud_ice_servers_enabled: Optional[bool] = None,
    tts_default_voice: Optional[tuple] = None,
) -> dict:
    """Update cloud preferences. Only the flags you pass are sent.

    Unlike the powercalc options flow this is a genuine PARTIAL update — HA's
    schema marks every key `vol.Optional` and leaves the rest alone — so there
    is no read-modify-write and no REPLACE hazard here.

    `google_secure_devices_pin` accepts `""` to clear it: its schema is
    `vol.Any(None, str)` and an empty string is how the UI unsets it.

    `tts_default_voice` is a (language, voice) PAIR validated server-side
    against HA's own `TTS_VOICES` table, and a wrong pair is a voluptuous
    error naming the schema rather than the mistake — so the pair is checked
    for shape here first.
    """
    payload: dict[str, Any] = {}
    for key, value in (
        ("alexa_enabled", alexa_enabled),
        ("alexa_report_state", alexa_report_state),
        ("google_enabled", google_enabled),
        ("google_report_state", google_report_state),
        ("remote_allow_remote_enable", remote_allow_remote_enable),
        ("cloud_ice_servers_enabled", cloud_ice_servers_enabled),
    ):
        if value is not None:
            payload[key] = bool(value)
    if google_secure_devices_pin is not None:
        payload["google_secure_devices_pin"] = google_secure_devices_pin or None
    if tts_default_voice is not None:
        pair = list(tts_default_voice)
        if len(pair) != 2 or not all(isinstance(p, str) and p for p in pair):
            raise ValueError(
                "tts_default_voice must be a (language, voice) pair, e.g. "
                "('en-US', 'JennyNeural'). HA validates the pair against its own "
                "voice table and rejects an unknown language or voice."
            )
        payload["tts_default_voice"] = pair
    if not payload:
        raise ValueError(
            "Nothing to update. Pass at least one preference: "
            + ", ".join(f"--{k.replace('_', '-')}" for k in PREF_KEYS)
        )
    _write(client, "cloud/update_prefs", "update cloud preferences", payload)
    return {
        "applied": True,
        "updated": payload,
        "note": (
            "Only the listed keys were sent; every other preference is "
            "untouched. `cloud status` shows the result."
        ),
    }


# ─────────────────────────────────────────────────────────────────── remote


def remote_connect(client) -> dict:
    """Turn on remote access (the Nabu Casa public URL) and connect it."""
    _write(client, "cloud/remote/connect", "connect remote access")
    return {
        "applied": True,
        "remote": "connect",
        "note": (
            "Remote access enabled. The public URL appears as "
            "`remote.domain` in `cloud status`, and as `cloud_url` in "
            "`network urls`. Provisioning the certificate can take a minute "
            "on first use."
        ),
    }


def remote_disconnect(client) -> dict:
    """Turn remote access off. The public URL stops answering."""
    _write(client, "cloud/remote/disconnect", "disconnect remote access")
    return {
        "applied": True,
        "remote": "disconnect",
        "note": (
            "Remote access disabled. Anything reaching this instance through "
            "the Nabu Casa URL — including cloudhooks and the mobile app when "
            "away from home — stops working until it is reconnected."
        ),
    }


# ─────────────────────────────────────────────────────────────────── alexa


def alexa_entities(client) -> dict:
    """Every entity Alexa can see, with its display categories and interfaces.

    This is the ALEXA-side view and is not the same list as `expose list
    --assistant cloud.alexa`: this one is what Alexa is capable of
    representing, that one is what you have chosen to expose. An entity
    missing here cannot be exposed at all.
    """
    return _read(client, "cloud/alexa/entities", "entities", "Alexa entities")


def alexa_entity(client, entity_id: str) -> dict:
    """Whether one entity is supported by Alexa.

    HA answers this with an EMPTY result on success and the error code
    `not_supported` on failure — there is no payload either way. That is
    normalised into `supported: true|false` here, because a bare `null` is not
    an answer a caller can branch on.
    """
    if not entity_id or "." not in entity_id:
        raise ValueError(f"Not an entity_id: {entity_id!r}. Expected e.g. `light.kitchen`.")
    try:
        client.ws_call("cloud/alexa/entities/get", {"entity_id": entity_id})
    except HomeAssistantError as exc:
        code = getattr(exc, "code", None)
        if code == NOT_LOGGED_IN:
            return {
                "logged_in": False,
                "entity_id": entity_id,
                "supported": None,
                "note": _note(False, "Alexa support"),
            }
        if code == "not_supported":
            return {
                "logged_in": True,
                "entity_id": entity_id,
                "supported": False,
                "note": (
                    f"{entity_id} cannot be represented by Alexa — either its "
                    "domain has no Alexa mapping, or it is one of the entities "
                    "HA never exposes (e.g. `group.all_*`). Exposing it will "
                    "not make it appear."
                ),
            }
        raise
    return {
        "logged_in": True,
        "entity_id": entity_id,
        "supported": True,
        "note": (
            f"{entity_id} is supported by Alexa. Supported is not exposed — "
            "`expose set --assistant cloud.alexa` is what makes it visible."
        ),
    }


def alexa_sync(client) -> dict:
    """Push the current entity list to Alexa.

    Needed after changing what is exposed: Alexa caches the device list and
    will not notice on its own. HA answers `alexa_relink` when the skill's
    token has expired, which no amount of retrying fixes — the remedy is in
    the Alexa app.
    """
    try:
        _write(client, "cloud/alexa/sync", "sync entities to Alexa")
    except HomeAssistantError as exc:
        if getattr(exc, "code", None) != "alexa_relink":
            raise
        raise ValueError(
            "Alexa rejected the sync: the Home Assistant skill needs to be "
            "re-linked. Open the Alexa app > Skills > Home Assistant and link "
            "the account again. Retrying this command will not help."
        ) from exc
    return {
        "applied": True,
        "note": "Entity list pushed to Alexa. Newly exposed entities appear after this.",
    }


# ────────────────────────────────────────────────────────────────── google


def google_entities(client) -> dict:
    """Every entity Google Assistant can see, with its traits.

    `might_2fa` is the one to read: those entities ask for a PIN before they
    act, and a Google command against them silently fails when no secure-
    devices PIN is set. Pair it with `cloud google set-2fa`.
    """
    return _read(client, "cloud/google_assistant/entities", "entities", "Google Assistant entities")


def google_entity(client, entity_id: str) -> dict:
    """One entity's Google traits, and whether 2FA is disabled for it."""
    if not entity_id or "." not in entity_id:
        raise ValueError(f"Not an entity_id: {entity_id!r}. Expected e.g. `lock.front_door`.")
    try:
        result = client.ws_call("cloud/google_assistant/entities/get", {"entity_id": entity_id})
    except HomeAssistantError as exc:
        code = getattr(exc, "code", None)
        if code == NOT_LOGGED_IN:
            return {
                "logged_in": False,
                "entity_id": entity_id,
                "entity": None,
                "note": _note(False, "Google Assistant support"),
            }
        if code in ("not_found", "not_supported"):
            raise ValueError(
                f"{entity_id}: {'no such entity' if code == 'not_found' else 'not supported by Google Assistant'}."
            ) from exc
        raise
    return {
        "logged_in": True,
        "entity_id": entity_id,
        "entity": result,
        "note": ("`might_2fa` traits ask for the secure-devices PIN before they act."),
    }


def google_set_2fa(client, entity_id: str, *, disable_2fa: bool) -> dict:
    """Turn the Google 2FA (PIN) prompt off or on for one entity.

    `disable_2fa=True` means Google will act WITHOUT asking for the PIN. On a
    lock or a garage door that is the difference between "anyone who can talk
    to the speaker can open it" and not, so it is stated plainly rather than
    hidden behind a flag name that reads as an improvement.

    HA answers this one with NOTHING when the value is already what you asked
    for — it returns early without sending a result — so `changed` cannot be
    reported from the response. Read it back with `cloud google entity`.
    """
    if not entity_id or "." not in entity_id:
        raise ValueError(f"Not an entity_id: {entity_id!r}. Expected e.g. `lock.front_door`.")
    _write(
        client,
        "cloud/google_assistant/entities/update",
        "update Google Assistant entity settings",
        {"entity_id": entity_id, "disable_2fa": bool(disable_2fa)},
    )
    return {
        "applied": True,
        "entity_id": entity_id,
        "disable_2fa": bool(disable_2fa),
        "note": (
            f"{entity_id} will now act WITHOUT asking for the secure-devices PIN."
            if disable_2fa
            else f"{entity_id} will now require the secure-devices PIN before acting."
        ),
    }


# ───────────────────────────────────────────────────────────────────── tts


def tts_info(client, *, language: Optional[str] = None) -> dict:
    """The cloud TTS voices, as (language, voice) pairs.

    Not login-guarded — the table is static, so it answers on a logged-out
    instance too. Returned grouped by language, because the raw form is a flat
    list of ~1,500 pairs that no caller wants to read.
    """
    raw = client.ws_call("cloud/tts/info") or {}
    pairs = raw.get("languages") or [] if isinstance(raw, dict) else []
    by_language: dict[str, list[str]] = {}
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        by_language.setdefault(str(pair[0]), []).append(str(pair[1]))
    if language is not None:
        wanted = language.strip()
        if wanted not in by_language:
            close = sorted(
                lang
                for lang in by_language
                if lang.lower().startswith(wanted.split("-")[0].lower())
            )
            raise ValueError(
                f"No cloud TTS voices for language {wanted!r}."
                + (f" Did you mean: {', '.join(close[:10])}?" if close else "")
            )
        by_language = {wanted: by_language[wanted]}
    return {
        "languages": sorted(by_language),
        "voices": {lang: sorted(v) for lang, v in sorted(by_language.items())},
        "language_count": len(by_language),
        "voice_count": sum(len(v) for v in by_language.values()),
        "note": (
            "A (language, voice) pair from here is what `cloud set-prefs "
            "--tts-voice LANG VOICE` accepts."
        ),
    }
