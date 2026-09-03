"""Onboarding — turning a brand-new Home Assistant into a usable one.

WHAT WAS MISSING. `core/auth_login.py` closed the "I have no token" gap for an
instance that is already set up: username + password → IndieAuth flow → access
token. It cannot help with a FRESH instance, and it says so — `/auth/providers`
answers `400 {"code": "onboarding_required"}` before onboarding is finished, so
there is no provider to log in against and no user to log in AS. Every command
in this harness was therefore unreachable on a container that had just started
for the first time; the first user had to be created by hand in the browser.

This module wraps the five views Home Assistant mounts under
`/api/onboarding/`, which are how that first user is created:

    GET  /api/onboarding                    OnboardingView              no auth
    GET  /api/onboarding/installation_type  InstallationTypeOnboardingView  no auth
    POST /api/onboarding/users              UserOnboardingView          no auth
    POST /api/onboarding/core_config        CoreConfigOnboardingView    AUTH
    POST /api/onboarding/analytics          AnalyticsOnboardingView     AUTH
    POST /api/onboarding/integration        IntegrationOnboardingView   AUTH

`provision()` drives the whole sequence — create the owner, exchange the
authorization code for tokens, then finish the remaining steps with the token
it just minted — so a fresh instance goes from "nothing" to "scriptable" in one
call.

MEASURED, NOT ASSUMED. Everything below was read off
`components/onboarding/views.py` and then driven against a real, never-onboarded
2025.1.4 over a socket (`tests/test_onboarding_e2e.py` repeats the run).

THE ONE THING THAT MATTERS MOST

  * EVERY STEP IS MARKED DONE BEFORE IT CAN FAIL. `_BaseOnboardingView` calls
    `_async_mark_done()` at the TOP of each handler, ahead of the work and
    ahead of every validity check. Measured: `POST /api/onboarding/integration`
    with a long-lived access token answers `403 Credentials for user not
    available` — and `GET /api/onboarding` then reports that step DONE. The
    same is true of the 500 below. So:

      - A FAILED STEP IS SPENT, NOT RETRYABLE. Retrying answers `403 "<Step>
        step already done"`, which reads like a different fault entirely. Every
        function here reports `committed` separately from `ok` and nothing
        retries.
      - `provision()` does the steps that can fail LAST, and never aborts the
        whole run for one of them — the user and the token, which are what the
        caller actually needs, are already secured by then.

THE REST OF THE TRAPS, IN THE ORDER THEY BITE

  * THE FIRST THREE VIEWS TAKE NO TOKEN AND THE LAST THREE REQUIRE ONE.
    `UserOnboardingView` sets `requires_auth = False`; `CoreConfigOnboardingView`,
    `AnalyticsOnboardingView` and `IntegrationOnboardingView` inherit the
    default `True`. Measured without a token they are a bare `401: Unauthorized`
    in text/plain — a body with nothing in it to distinguish "wrong token" from
    "this endpoint needs one". The chicken-and-egg is only apparent: the token
    for them comes from the user step that precedes them.

  * `installation_type` 401s AS SOON AS ANY STEP IS DONE, not when onboarding
    finishes. The guard is `if self._data["done"]: raise HTTPUnauthorized` and
    `done` is a LIST of completed steps, so it is truthy after the FIRST one.
    Read it before creating the user or not at all.

  * `core_config` ANSWERS 500 ON A PERFECTLY GOOD REQUEST. After marking itself
    done it starts `google_translate`, `met`, `radio_browser` and
    `shopping_list`; on any install where one of those cannot import (measured:
    `google_translate` → `No module named 'mutagen'`) the exception escapes the
    handler and aiohttp answers `500 Internal Server Error` with the text body
    "Server got itself in trouble". That is a report about the SERVER'S optional
    integrations, not about the call — and the step is done either way.

  * THE `integration` STEP NEEDS A CREDENTIAL-BACKED TOKEN. It reads
    `refresh_token.credential`, which is set for a token minted through the
    authorization-code grant and is `None` for a long-lived access token
    (`auth/long_lived_access_token` creates the refresh token without one). With
    an LLAT it is `403 Credentials for user not available` — and, again, spent.
    `provision()` therefore uses the token it derived from the auth code.

  * `POST /api/onboarding/users` RETURNS ONLY AN AUTHORIZATION CODE. It is
    single-use, expires in 10 minutes, and is bound to the `client_id` it was
    created with — `retrieve_result` keys the store on `(client_id, code)`. Feed
    exactly the same `client_id` to `/auth/token`.

  * ...AND IT DOES NOT VALIDATE THAT `client_id`. The view passes it straight to
    `create_auth_code`; `indieauth.verify_client_id` runs at `/auth/token`,
    afterwards. A malformed one therefore burns the ONE user step and yields a
    code that can never be redeemed. `auth_login.validate_client_id` is applied
    here, before the request goes out.

  * A MISSING FIELD IS A 400 THAT NAMES THE KEY — but only the FIRST one
    (`required key not provided @ data['password']`), and all five of name,
    username, password, client_id and language are required. They are checked
    locally so the caller is told about all of them at once, and so a typo does
    not consume the step.
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.core import auth_login
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

#: The onboarding steps, in the order `components/onboarding/const.py` lists
#: them. `GET /api/onboarding` reports one entry per step in this order.
STEPS = ("user", "core_config", "analytics", "integration")

#: The steps `finish_step()` can complete on its own. `user` is not one of them
#: — it needs credentials, so it has its own function — and `integration` needs
#: a redirect_uri, so it has one too.
SIMPLE_STEPS = ("core_config", "analytics")

_BASE = "/api/onboarding"


def _body_message(body: Any) -> str:
    """The human part of an onboarding error body.

    The step views answer with `{"message": …}` (json_message) but aiohttp's own
    401/500 pages are text/plain, so `body` may be a plain string — or, for the
    empty 401, effectively nothing.
    """
    if isinstance(body, dict):
        return str(body.get("message") or body.get("error") or body)
    if isinstance(body, str):
        return " ".join(body.split())
    return "" if body is None else str(body)


def status(client) -> dict:
    """Onboarding progress. No token needed — this is the pre-auth view.

    Returns ``{"onboarded": bool, "steps": {<step>: <done>}, "done": [...],
    "remaining": [...]}``. `onboarded` is true only when EVERY step is done,
    which is the condition that unblocks `/auth/providers` and the rest of the
    API.
    """
    code, body = client.root_request("GET", _BASE, send_auth=False)
    if code == 404:
        raise HomeAssistantError(
            "This Home Assistant does not serve /api/onboarding — the `onboarding` "
            "integration is not loaded (it is part of `default_config`). Nothing to "
            "do here; if the instance already works, use `auth login` instead.",
            status=404,
        )
    if code != 200 or not isinstance(body, list):
        raise HomeAssistantError(
            f"Could not read onboarding status (HTTP {code}): {_body_message(body)}",
            status=code,
        )
    steps = {str(entry.get("step")): bool(entry.get("done")) for entry in body}
    done = [s for s in STEPS if steps.get(s)]
    remaining = [s for s in STEPS if s in steps and not steps[s]]
    return {
        "onboarded": bool(steps) and all(steps.values()),
        "steps": steps,
        "done": done,
        "remaining": remaining,
    }


def installation_type(client) -> dict:
    """How this instance was installed (`Home Assistant OS`, `Container`, …).

    READ THIS FIRST OR NOT AT ALL. The view refuses once ANY step is done, not
    once onboarding is finished, so it is only answerable on a completely
    untouched instance.
    """
    code, body = client.root_request("GET", f"{_BASE}/installation_type", send_auth=False)
    if code == 401:
        raise HomeAssistantError(
            "installation_type is only readable before onboarding STARTS — Home "
            "Assistant refuses it as soon as the first step is done (the guard is "
            "`if self._data['done']`, a non-empty list). Use `system info` once you "
            "have a token.",
            status=401,
        )
    if code != 200 or not isinstance(body, dict):
        raise HomeAssistantError(
            f"Could not read installation type (HTTP {code}): {_body_message(body)}",
            status=code,
        )
    return body


def create_user(
    client,
    *,
    name: str,
    username: str,
    password: str,
    language: str = "en",
    client_id: str | None = None,
) -> dict:
    """Create the owner account. THE ONE-SHOT STEP — there is no second chance.

    Home Assistant marks the `user` step done inside the same handler, so this
    can be called exactly once per instance; afterwards it is
    `403 "User step already done"`.

    Returns ``{"auth_code", "client_id", "username", "committed": True}``. The
    code is single-use, valid 10 minutes, and only redeemable at `/auth/token`
    with the SAME `client_id` — pass the returned value straight to
    `auth_login.exchange_code`, or just call `provision()`, which does both.
    """
    missing = [
        field
        for field, value in (
            ("name", name),
            ("username", username),
            ("password", password),
            ("language", language),
        )
        if not value
    ]
    if missing:
        raise ValueError(
            f"{', '.join(missing)} required — Home Assistant rejects an incomplete "
            "user step with a 400 and, worse, names only the first missing key"
        )
    # Validated locally because the view does NOT validate it: a malformed
    # client_id is accepted here, spends the single user step, and only fails
    # later at /auth/token with `invalid_request`.
    cid = auth_login.validate_client_id(client_id or auth_login.default_client_id(client.base_url))

    code, body = client.root_request(
        "POST",
        f"{_BASE}/users",
        json_payload={
            "name": name,
            "username": username,
            "password": password,
            "client_id": cid,
            "language": language,
        },
        send_auth=False,
    )
    if code == 403:
        raise HomeAssistantError(
            "The user step is already done — this instance has an owner. Onboarding "
            "creates exactly one account; add more with `auth user create` once you "
            "have a token, or sign in with `auth login`.",
            status=403,
        )
    if code != 200 or not isinstance(body, dict) or not body.get("auth_code"):
        raise HomeAssistantError(
            f"Creating the owner account failed (HTTP {code}): {_body_message(body)}",
            status=code,
        )
    return {
        "auth_code": body["auth_code"],
        "client_id": cid,
        "username": username,
        "committed": True,
    }


def finish_step(client, step: str, *, token: str | None = None) -> dict:
    """Complete `core_config` or `analytics`. NEEDS A TOKEN.

    `token` overrides the client's own bearer for this call — during a fresh
    provision the only usable token is the one just minted from the user
    step's authorization code, which the client was not built with.

    Returns ``{"step", "ok", "committed", "detail"}``. `committed` is true
    whenever Home Assistant reached the handler at all, because the handler
    marks the step done before doing anything else — so `ok=False,
    committed=True` means "this step is finished and will never run its work",
    which is a normal outcome for `core_config` and not something to retry.
    """
    if step not in SIMPLE_STEPS:
        raise ValueError(
            f"step must be one of {', '.join(SIMPLE_STEPS)} — `user` needs "
            "credentials (use create_user) and `integration` needs a redirect_uri "
            "(use finish_integration)"
        )
    code, body = client.root_request("POST", f"{_BASE}/{step}", json_payload={}, auth_token=token)
    if code == 200:
        return {"step": step, "ok": True, "committed": True, "detail": None}
    if code == 403:
        return {
            "step": step,
            "ok": False,
            "committed": True,
            "detail": "already done — onboarding steps are one-shot",
        }
    if code == 401:
        raise HomeAssistantError(
            f"The {step} step requires a token (only `user` and the two read views "
            "are unauthenticated). Create the owner first, exchange its auth_code "
            "for a token, and pass that — `onboarding provision` does all three.",
            status=401,
        )
    if code == 500 and step == "core_config":
        # Measured on 2025.1.4: after marking itself done, the handler starts
        # google_translate / met / radio_browser / shopping_list, and an import
        # error in any of them escapes as a bare 500. The step IS done.
        return {
            "step": step,
            "ok": False,
            "committed": True,
            "detail": (
                "Home Assistant answered 500 while starting the integrations this "
                "step sets up (google_translate, met, radio_browser, "
                "shopping_list) — a missing dependency on the server, not a bad "
                "request. The step itself is done; check the HA log if you want "
                "those integrations."
            ),
        }
    raise HomeAssistantError(
        f"Onboarding step {step} failed (HTTP {code}): {_body_message(body)} "
        "— note the step is marked done regardless, so do not retry it.",
        status=code,
    )


def finish_integration(
    client,
    *,
    client_id: str | None = None,
    redirect_uri: str | None = None,
    token: str | None = None,
) -> dict:
    """Complete the `integration` step. NEEDS A CREDENTIAL-BACKED TOKEN.

    Returns a SECOND authorization code (for handing the session to a
    companion app), alongside the same `ok`/`committed` pair as `finish_step`.

    A long-lived access token does not work here: the view reads
    `refresh_token.credential`, which HA leaves `None` for an LLAT, and answers
    `403 Credentials for user not available` — after marking the step done.
    Use a token from `auth login` or from the auth code `create_user` returned.
    """
    cid = auth_login.validate_client_id(client_id or auth_login.default_client_id(client.base_url))
    redirect = redirect_uri or cid
    code, body = client.root_request(
        "POST",
        f"{_BASE}/integration",
        json_payload={"client_id": cid, "redirect_uri": redirect},
        auth_token=token,
    )
    if code == 200 and isinstance(body, dict) and body.get("auth_code"):
        return {
            "step": "integration",
            "ok": True,
            "committed": True,
            "auth_code": body["auth_code"],
            "client_id": cid,
            "detail": None,
        }
    if code == 403:
        message = _body_message(body)
        if "Credentials" in message:
            detail = (
                "the token used has no credential behind it. A long-lived access "
                "token never does; use one from `auth login` or from the auth code "
                "`onboarding create-user` returned. The step is spent either way."
            )
        else:
            detail = "already done — onboarding steps are one-shot"
        return {
            "step": "integration",
            "ok": False,
            "committed": True,
            "auth_code": None,
            "client_id": cid,
            "detail": detail,
        }
    if code == 401:
        raise HomeAssistantError(
            "The integration step requires a token. See `onboarding provision`.",
            status=401,
        )
    raise HomeAssistantError(
        f"Onboarding step integration failed (HTTP {code}): {_body_message(body)} "
        "— note the step is marked done regardless, so do not retry it.",
        status=code,
    )


def provision(
    client,
    *,
    name: str,
    username: str,
    password: str,
    language: str = "en",
    client_id: str | None = None,
    redirect_uri: str | None = None,
    finish: bool = True,
) -> dict:
    """Take a fresh Home Assistant from nothing to a usable access token.

    1. Read the status; refuse early if the user step is already done.
    2. Create the owner (`create_user`).
    3. Redeem its authorization code for an access + refresh token
       (`auth_login.exchange_code`).
    4. With `finish=True`, complete `analytics`, `core_config` and
       `integration` using that token — in that order, because the last two are
       the ones that can fail, and by then the credential the caller came for is
       already in hand.

    Returns the token bundle plus a `steps` map. NOTHING AFTER STEP 3 CAN COST
    YOU THE TOKEN: a step that Home Assistant refuses is recorded in `steps`
    and the run continues, because a refused step is already spent and retrying
    it is not an option anyway.
    """
    before = status(client)
    if before["steps"].get("user"):
        raise HomeAssistantError(
            "This instance already has an owner (the `user` onboarding step is "
            f"done; remaining: {', '.join(before['remaining']) or 'none'}). Use "
            "`auth login` to get a token for the existing account.",
            status=403,
        )

    created = create_user(
        client,
        name=name,
        username=username,
        password=password,
        language=language,
        client_id=client_id,
    )
    cid = created["client_id"]
    tokens = auth_login.exchange_code(client, code=created["auth_code"], client_id=cid)

    out: dict[str, Any] = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "expires_in": tokens.get("expires_in"),
        "token_type": tokens.get("token_type"),
        "client_id": cid,
        "username": username,
        "steps": {"user": {"ok": True, "committed": True, "detail": None}},
    }
    if not finish:
        out["onboarded"] = False
        out["steps_skipped"] = [s for s in STEPS if s != "user"]
        return out

    # The remaining views need a token, and the client we were handed has none
    # (that is the whole point of onboarding), so speak to them as the user we
    # just created.
    access = tokens["access_token"]
    for step in ("analytics", "core_config"):
        try:
            result = finish_step(client, step, token=access)
        except HomeAssistantError as exc:
            result = {"step": step, "ok": False, "committed": True, "detail": str(exc)}
        out["steps"][step] = {k: v for k, v in result.items() if k != "step"}
    try:
        result = finish_integration(client, client_id=cid, redirect_uri=redirect_uri, token=access)
    except HomeAssistantError as exc:
        result = {
            "step": "integration",
            "ok": False,
            "committed": True,
            "auth_code": None,
            "detail": str(exc),
        }
    out["steps"]["integration"] = {k: v for k, v in result.items() if k != "step"}

    after = status(client)
    out["onboarded"] = after["onboarded"]
    out["remaining"] = after["remaining"]
    return out
