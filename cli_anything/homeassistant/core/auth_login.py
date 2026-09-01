"""The pre-authentication half of Home Assistant's auth API.

WHAT WAS MISSING. The `auth` group already covered everything you can do once
you ALREADY have a token: `auth me`, `auth tokens list/create/delete`,
`auth sign-path`, `auth user …`. All of it goes over the authenticated
WebSocket. None of it can be reached without a token, and nothing in this
harness could obtain one — the token had to be minted by hand in the Home
Assistant UI (Profile → Long-Lived Access Tokens) before any command worked.

This module closes that loop. It wraps the views Home Assistant mounts at the
server ROOT, outside `/api/`, which is why `client.get()`/`post()` (they
hardcode the `/api/` prefix) could not call them:

    GET    /.well-known/oauth-authorization-server  WellKnownOAuthInfoView
    GET    /auth/providers                          AuthProvidersView
    POST   /auth/login_flow                         LoginFlowIndexView
    POST   /auth/login_flow/{flow_id}               LoginFlowResourceView
    DELETE /auth/login_flow/{flow_id}               LoginFlowResourceView
    POST   /auth/token                              TokenView
    POST   /auth/revoke                             RevokeTokenView
    POST   /auth/link_user                          LinkUserView

`login()` drives the whole IndieAuth dance — providers → flow → credentials →
(optional MFA) → authorization code → access + refresh tokens — in one call.

MEASURED, NOT ASSUMED. Every status code, encoding and quirk below was read off
`components/auth/__init__.py`, `components/auth/login_flow.py` and
`components/auth/indieauth.py`, then confirmed against a live 2025.1.4.

THE TRAPS, IN THE ORDER THEY BITE

  * THE TWO HALVES OF THE FLOW DISAGREE ABOUT BODY ENCODING. `/auth/login_flow`
    parses JSON and answers a form body with `400 {"message": "Invalid
    JSON."}`. `/auth/token` and `/auth/revoke` call `await request.post()` and
    see ONLY a form body; sent JSON, they answer `400 {"error":
    "unsupported_grant_type"}` — which blames the grant type for what is
    actually a content-type error, and is exactly what this client's default
    `Content-Type: application/json` session header produces. Handled in
    `HomeAssistantClient.root_request` via `form=`.

  * A WRONG PASSWORD IS AN HTTP 200. `_async_flow_result_to_response` returns
    the next FORM step with `errors = {"base": "invalid_auth"}` and status 200.
    Anything that trusts the status reports a successful login and returns no
    token. `_check_step` reads the body instead.

  * ...AND EACH ONE IS COUNTED TOWARD AN IP BAN. The same branch calls
    `process_wrong_login(request)`. Retrying a guessed password in a loop can
    lock the calling host out of Home Assistant entirely, so nothing here
    retries credentials.

  * A MISMATCHED `redirect_uri` IS REJECTED ONLY AFTER THE PASSWORD IS
    ACCEPTED. `verify_redirect_uri` runs in the CREATE_ENTRY branch, so bad
    values burn a real credential check and then return 403 with no token. And
    when scheme+netloc differ, Home Assistant tries to FETCH the `client_id`
    URL over the network (IndieAuth 4.2.2 link-tag discovery, 5 s timeout) to
    look for a matching link tag. `redirect_uri` therefore defaults to
    `client_id` here: identical origins short-circuit the check before any
    outbound request happens.

  * THE REFRESH GRANT REQUIRES THE ORIGINAL `client_id`. `_async_handle_refresh_token`
    compares `refresh_token.client_id != client_id`, so refreshing with a
    different one — or with none at all — is `400 {"error":
    "invalid_request"}`, a body with no description and no hint. `login()`
    returns the `client_id` it used so it can be fed back to `refresh()`.

  * AN UNKNOWN HANDLER IS A 500, NOT THE DOCUMENTED 404. `LoginFlowIndexView.post`
    catches `data_entry_flow.UnknownHandler` and means to answer `404 Invalid
    handler specified`; a handler that no provider serves in fact escapes as
    something else and aiohttp returns `500 Internal Server Error` as
    text/plain. Measured on 2025.1.4. `login()` validates the requested
    provider against `/auth/providers` first so the caller gets a list of what
    IS available instead of a server error.

  * REVOCATION IS UNFALSIFIABLE. RFC 7009 §2.2 says an invalid token must also
    succeed, so `/auth/revoke` answers `200` with an EMPTY body for a real
    token, a bogus token and a missing token alike. `revoke_token(verify=True)`
    proves it instead, by trying the refresh grant afterwards and requiring
    `invalid_grant`.

  * `/auth/providers` 400s BEFORE ONBOARDING IS FINISHED (`message_code =
    onboarding_required`), which is a statement about the instance, not about
    the request.
"""

from __future__ import annotations

from ipaddress import ip_address, ip_network
from typing import Any
from urllib.parse import urlparse

from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

#: Home Assistant's built-in username/password provider. `handler` is always a
#: two-element `[type, id]` pair — `vol.Length(2, 2)` — and `id` is null for a
#: provider configured without one, which is the normal case.
DEFAULT_PROVIDER_TYPE = "homeassistant"

#: Flow types accepted by `LoginFlowIndexView`. Anything other than
#: `link_user` is treated as `authorize`, but only these two mean anything.
FLOW_TYPES = ("authorize", "link_user")

_WELL_KNOWN = "/.well-known/oauth-authorization-server"

#: The networks `homeassistant.util.network.is_local` treats as local, copied
#: rather than approximated with `ipaddress`'s own `.is_private`.
#:
#: THE STDLIB PROPERTY IS WIDER THAN HOME ASSISTANT'S. `IPv4Address.is_private`
#: is true for the CGNAT range 100.64.0.0/10, for 192.0.0.0/24 and for several
#: others that are absent from HA's RFC6890 table, so validating with it would
#: locally ACCEPT client_ids the server then rejects with a bare
#: `400 {"message": "Invalid client id"}` — putting this check back exactly
#: where it started. These are fixed RFC6890 allocations, so the copy does not
#: drift.
_LOCAL_NETWORKS = (
    ip_network("127.0.0.0/8"),
    ip_network("::1/128"),
    ip_network("::ffff:127.0.0.0/104"),
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("fd00::/8"),
    ip_network("::ffff:10.0.0.0/104"),
    ip_network("::ffff:172.16.0.0/108"),
    ip_network("::ffff:192.168.0.0/112"),
    ip_network("169.254.0.0/16"),
    ip_network("fe80::/10"),
    ip_network("::ffff:169.254.0.0/112"),
)


# ---------------------------------------------------------------- client ids


def default_client_id(base_url: str) -> str:
    """The `client_id` to use when the caller does not supply one.

    Home Assistant's own frontend uses its base URL, and using it here means
    `client_id` and `redirect_uri` share an origin — which is what makes
    `verify_redirect_uri` return early instead of fetching the client_id URL
    over the network. The trailing slash is not cosmetic: IndieAuth 3.2 says a
    URL with no path component MUST be treated as if it had the path `/`, and
    `_parse_url` canonicalises it that way, so adding it up front keeps the
    string we send identical to the string Home Assistant compares.
    """
    return base_url.rstrip("/") + "/"


def validate_client_id(client_id: str) -> str:
    """Apply Home Assistant's IndieAuth rules locally, or raise `ValueError`.

    `verify_client_id` server-side is a bool, so every violation collapses to
    the same `400 {"message": "Invalid client id"}` with no indication of WHICH
    rule failed. This mirrors `indieauth._parse_client_id` so the caller is told
    that instead.

    Note the port quirk, which is reproduced deliberately rather than fixed:
    the hostname check is `ip_address(parts.netloc)` and `netloc` INCLUDES the
    port, so `http://8.8.8.8/` parses as a public IP and is rejected while
    `http://8.8.8.8:8123/` fails to parse as an address at all, is taken for a
    domain name, and is accepted. Both measured. Rejecting the second here
    would refuse a client_id the server accepts.
    """
    if not client_id:
        raise ValueError("client_id cannot be empty")
    parts = urlparse(client_id)
    if parts.path == "":
        parts = parts._replace(path="/")
    if parts.scheme not in ("http", "https"):
        raise ValueError(
            f"Invalid client_id {client_id!r}: must be an absolute http:// or https:// URL "
            "(IndieAuth 3.2). Try the Home Assistant base URL, e.g. http://localhost:8123/"
        )
    if any(segment in (".", "..") for segment in parts.path.split("/")):
        raise ValueError(
            f"Invalid client_id {client_id!r}: must not contain '.' or '..' path segments."
        )
    if parts.fragment:
        raise ValueError(f"Invalid client_id {client_id!r}: must not contain a '#' fragment.")
    if parts.username is not None:
        raise ValueError(f"Invalid client_id {client_id!r}: must not contain a username.")
    if parts.password is not None:
        raise ValueError(f"Invalid client_id {client_id!r}: must not contain a password.")
    try:
        parts.port
    except ValueError as exc:
        raise ValueError(f"Invalid client_id {client_id!r}: invalid port.") from exc

    netloc = parts.netloc
    if netloc.startswith("[") and netloc.endswith("]"):
        netloc = netloc[1:-1]
    try:
        address = ip_address(netloc)
    except ValueError:
        address = None
    if address is not None and not any(address in net for net in _LOCAL_NETWORKS):
        raise ValueError(
            f"Invalid client_id {client_id!r}: a bare public IP address is refused "
            "(IndieAuth 3.2 allows only domain names or local IPs). Use a hostname, "
            f"or include the port — Home Assistant accepts 'http://{netloc}:8123/' "
            "because it parses netloc-with-port as a domain name."
        )
    return client_id


def _resolve_ids(client, client_id: str | None, redirect_uri: str | None) -> tuple[str, str]:
    cid = validate_client_id(client_id or default_client_id(client.base_url))
    return cid, redirect_uri or cid


# ------------------------------------------------------------------ discovery


def oauth_metadata(client) -> dict:
    """Return the RFC 8414 authorization-server metadata document.

    Unauthenticated, and the only endpoint here that cannot fail for a reason
    worth naming — it is a static dict in `WellKnownOAuthInfoView.get`.
    """
    status, body = client.root_request("GET", _WELL_KNOWN, send_auth=False)
    if status != 200:
        raise HomeAssistantError(
            f"GET {_WELL_KNOWN} -> {status}: {_describe(body)}", status=status
        )
    return body


def list_providers(client) -> dict:
    """List the auth providers this instance offers, for use as `handler`.

    Returns the raw document: `{"providers": [{name, id, type}, …],
    "preselect_remember_me": bool}`.

    `trusted_networks` providers are filtered out by Home Assistant unless the
    CALLER's IP is actually trusted, so the list is relative to where this runs.
    """
    status, body = client.root_request("GET", "/auth/providers", send_auth=False)
    if status == 400 and isinstance(body, dict) and body.get("code") == "onboarding_required":
        raise HomeAssistantError(
            "Home Assistant has not finished onboarding, so it will not list auth "
            "providers yet. Create the owner account first (open the web UI, or use "
            "`hass --script auth add <user> <password>` in the config directory).",
            code="onboarding_required",
            status=400,
        )
    if status != 200:
        raise HomeAssistantError(
            f"GET /auth/providers -> {status}: {_describe(body)}", status=status
        )
    return body


def resolve_handler(
    client,
    *,
    provider_type: str | None = None,
    provider_id: str | None = None,
) -> list:
    """Pick a `[type, id]` handler pair, checking it against `/auth/providers`.

    Exists because an unknown handler is a bare `500 Internal Server Error`
    (text/plain) rather than the `404 Invalid handler specified` the view's
    source intends — a response that tells the caller nothing and looks like
    Home Assistant is broken. Resolving first turns a typo into a message
    naming every provider that IS configured.
    """
    providers = list_providers(client).get("providers") or []
    if not providers:
        raise HomeAssistantError(
            "Home Assistant reports no usable auth providers. If this instance "
            "only uses trusted_networks, note that it is hidden from callers "
            "whose IP is not trusted."
        )
    if provider_type is None and provider_id is None:
        chosen = next((p for p in providers if p.get("type") == DEFAULT_PROVIDER_TYPE), None)
        chosen = chosen or providers[0]
        return [chosen.get("type"), chosen.get("id")]
    for provider in providers:
        if provider_type is not None and provider.get("type") != provider_type:
            continue
        if provider_id is not None and provider.get("id") != provider_id:
            continue
        return [provider.get("type"), provider.get("id")]
    available = ", ".join(f"{p.get('type')}/{p.get('id')}" for p in providers)
    raise ValueError(
        f"No auth provider matches type={provider_type!r} id={provider_id!r}. "
        f"This instance offers: {available}"
    )


# ----------------------------------------------------------------- login flow


def start_login_flow(
    client,
    *,
    handler: list | tuple | None = None,
    client_id: str | None = None,
    redirect_uri: str | None = None,
    flow_type: str = "authorize",
) -> dict:
    """Open a login flow and return its first step.

    The step is a data-entry-flow result: `type: form` with a serialized
    `data_schema` naming the fields to send to `advance_login_flow`, or —
    for a provider that needs no input, such as `trusted_networks` —
    `type: create_entry` with the authorization code already in `result`.
    """
    if flow_type not in FLOW_TYPES:
        raise ValueError(f"flow_type must be one of {', '.join(FLOW_TYPES)}, got {flow_type!r}")
    cid, redirect = _resolve_ids(client, client_id, redirect_uri)
    handler = list(handler) if handler is not None else [DEFAULT_PROVIDER_TYPE, None]
    if len(handler) != 2:
        raise ValueError(
            f"handler must be exactly [type, id] (two elements), got {handler!r}. "
            "Home Assistant validates it with vol.Length(2, 2); id is null when the "
            "provider was configured without one."
        )
    status, body = client.root_request(
        "POST",
        "/auth/login_flow",
        json_payload={
            "client_id": cid,
            "handler": handler,
            "redirect_uri": redirect,
            "type": flow_type,
        },
        send_auth=False,
    )
    if status == 500:
        raise HomeAssistantError(
            f"Home Assistant returned 500 for handler {handler!r}. This is what an "
            "UNKNOWN auth provider looks like — the view means to answer 404 "
            "'Invalid handler specified' but the error escapes. Run "
            "`auth providers` to see the configured ones.",
            status=500,
        )
    if status != 200:
        raise HomeAssistantError(
            f"POST /auth/login_flow -> {status}: {_describe(body)}", status=status
        )
    return _check_step(body, stage="starting the login flow")


def advance_login_flow(
    client,
    *,
    flow_id: str,
    step_data: dict,
    client_id: str | None = None,
) -> dict:
    """Submit one step of a login flow (credentials, then MFA if asked).

    `step_data` is merged with `client_id` and posted as JSON — the view's
    schema is `{Required("client_id"): str}` with `extra=vol.ALLOW_EXTRA`, so
    whatever else is present is handed to the provider unchanged.

    The flow is pinned to the IP that opened it (`flow["context"]["ip_address"]
    != ip_address(request.remote)` → `400 IP address changed`), so it cannot be
    resumed from another host.
    """
    if not flow_id:
        raise ValueError("flow_id is required")
    if "client_id" in step_data:
        raise ValueError(
            "step_data must not contain client_id — it is sent separately and "
            "popped by the view before the rest reaches the provider."
        )
    cid = validate_client_id(client_id or default_client_id(client.base_url))
    status, body = client.root_request(
        "POST",
        f"/auth/login_flow/{flow_id}",
        json_payload={"client_id": cid, **step_data},
        send_auth=False,
    )
    if status == 404:
        raise HomeAssistantError(
            f"Login flow {flow_id} is not in progress (it may have been aborted, "
            "already completed, or opened from a different IP).",
            status=404,
        )
    if status == 403:
        raise HomeAssistantError(
            "Home Assistant accepted the credentials and then refused the redirect "
            f"URI: {_describe(body)}. redirect_uri must share a scheme and host with "
            f"client_id ({cid}) unless the client_id URL publishes a matching "
            "<link rel=redirect_uri> tag.",
            status=403,
        )
    if status != 200:
        raise HomeAssistantError(
            f"POST /auth/login_flow/{flow_id} -> {status}: {_describe(body)}", status=status
        )
    return _check_step(body, stage="submitting the login step")


def abort_login_flow(client, *, flow_id: str) -> dict:
    """Cancel a login flow that was started and not finished."""
    if not flow_id:
        raise ValueError("flow_id is required")
    status, body = client.root_request(
        "DELETE", f"/auth/login_flow/{flow_id}", send_auth=False
    )
    if status == 404:
        raise HomeAssistantError(
            f"Login flow {flow_id} is not in progress — nothing to abort.", status=404
        )
    if status != 200:
        raise HomeAssistantError(
            f"DELETE /auth/login_flow/{flow_id} -> {status}: {_describe(body)}", status=status
        )
    return {"flow_id": flow_id, "aborted": True, "message": _describe(body)}


def _check_step(step: Any, *, stage: str) -> dict:
    """Turn a 200-with-errors login step into an exception.

    THE REASON THIS FUNCTION EXISTS: a rejected password is HTTP 200. The body
    is the same `type: form` step that was just submitted, with `errors.base`
    set. Callers that check the status see success.
    """
    if not isinstance(step, dict):
        raise HomeAssistantError(f"Unexpected response while {stage}: {step!r}")
    errors = step.get("errors") or {}
    if errors:
        base = errors.get("base") or next(iter(errors.values()), "unknown")
        hint = ""
        if base == "invalid_auth":
            hint = (
                " — the username or password was rejected. Note that Home Assistant "
                "counts this toward an IP ban (process_wrong_login), so do not retry "
                "in a loop."
            )
        elif base == "invalid_code":
            hint = " — the multi-factor code was rejected."
        raise HomeAssistantError(
            f"Login step failed ({base}){hint}", code=str(base)
        )
    return step


# --------------------------------------------------------------------- tokens


def exchange_code(client, *, code: str, client_id: str | None = None) -> dict:
    """Trade an authorization code for an access token + refresh token.

    The code is single-use: `retrieve_auth` pops it, so a second exchange is
    `400 invalid_request / "Invalid code"` even though the first succeeded.
    Codes also expire after a couple of minutes.
    """
    if not code:
        raise ValueError("code is required")
    cid = validate_client_id(client_id or default_client_id(client.base_url))
    status, body = client.root_request(
        "POST",
        "/auth/token",
        form={"grant_type": "authorization_code", "code": code, "client_id": cid},
        send_auth=False,
    )
    if status != 200:
        raise HomeAssistantError(_token_error(status, body, grant="authorization_code"), status=status)
    return {**body, "client_id": cid}


def refresh_access_token(client, *, refresh_token: str, client_id: str | None = None) -> dict:
    """Mint a fresh access token from a refresh token.

    `client_id` MUST be the one the refresh token was issued to — Home
    Assistant compares them and answers a descriptionless `400
    invalid_request` on any mismatch, including omitting it entirely. The
    response carries NO new refresh token, only `access_token`, `token_type`
    and `expires_in`.

    Called twice within the same second this returns a byte-identical
    `access_token`: the JWT's only varying claims are `iat`/`exp`, at
    one-second resolution. That is not a failure to refresh.
    """
    if not refresh_token:
        raise ValueError("refresh_token is required")
    cid = validate_client_id(client_id or default_client_id(client.base_url))
    status, body = client.root_request(
        "POST",
        "/auth/token",
        form={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": cid,
        },
        send_auth=False,
    )
    if status != 200:
        raise HomeAssistantError(_token_error(status, body, grant="refresh_token"), status=status)
    return {**body, "client_id": cid}


def revoke_token(
    client,
    *,
    token: str,
    verify: bool = False,
    client_id: str | None = None,
) -> dict:
    """Revoke a refresh token (and every access token derived from it).

    `/auth/revoke` ALWAYS answers `200` with an empty body — RFC 7009 §2.2
    requires that an invalid token succeed too — so the response proves
    nothing. With `verify=True` the refresh grant is attempted afterwards and
    the revocation is only reported as confirmed when it comes back
    `invalid_grant`.
    """
    if not token:
        raise ValueError("token is required")
    cid = validate_client_id(client_id or default_client_id(client.base_url))
    status, body = client.root_request(
        "POST", "/auth/revoke", form={"token": token}, send_auth=False
    )
    if status != 200:
        raise HomeAssistantError(
            f"POST /auth/revoke -> {status}: {_describe(body)}", status=status
        )
    result = {
        "revoked": True,
        "verified": False,
        "note": (
            "/auth/revoke returns 200 for a valid token, an invalid token and a "
            "missing token alike (RFC 7009 2.2); pass verify=True to confirm."
        ),
    }
    if not verify:
        return result
    try:
        refresh_access_token(client, refresh_token=token, client_id=cid)
    except HomeAssistantError as exc:
        result["verified"] = "invalid_grant" in str(exc)
        result["note"] = (
            "Confirmed: the refresh grant now fails with invalid_grant."
            if result["verified"]
            else f"Could not confirm revocation: {exc}"
        )
        return result
    result["revoked"] = False
    result["note"] = (
        "NOT revoked — the refresh grant still works. This is what revoking an "
        "ACCESS token (rather than a refresh token) looks like: Home Assistant "
        "looks the value up with async_get_refresh_token_by_token, finds nothing, "
        "and returns 200 anyway."
    )
    return result


def link_user(client, *, code: str, client_id: str | None = None) -> dict:
    """Attach the credential behind an authorization code to the ACTIVE user.

    Unlike everything else in this module this endpoint REQUIRES a bearer token
    (`requires_auth` is left at its default) and takes a JSON body. The code
    must come from a flow started with `flow_type="link_user"`, which makes it
    credential-only.
    """
    if not code:
        raise ValueError("code is required")
    cid = validate_client_id(client_id or default_client_id(client.base_url))
    status, body = client.root_request(
        "POST", "/auth/link_user", json_payload={"code": code, "client_id": cid}
    )
    if status == 401:
        raise HomeAssistantError(
            "Unauthorized (401). /auth/link_user is the one auth endpoint that needs "
            "an existing token — it links a credential to the CURRENTLY logged-in "
            "user. Set one with `config set --token` or HASS_TOKEN.",
            status=401,
        )
    if status != 200:
        raise HomeAssistantError(
            f"POST /auth/link_user -> {status}: {_describe(body)}", status=status
        )
    return {"linked": True, "message": _describe(body)}


# ------------------------------------------------------------------ composite


def login(
    client,
    *,
    username: str,
    password: str,
    mfa_code: str | None = None,
    client_id: str | None = None,
    redirect_uri: str | None = None,
    provider_type: str | None = None,
    provider_id: str | None = None,
) -> dict:
    """Username + password → access token, refresh token and expiry, in one call.

    Runs the full IndieAuth exchange: resolve the provider, open a flow, submit
    credentials, answer an MFA step if the provider asks for one, then trade
    the authorization code at `/auth/token`.

    Returns the token document plus the `client_id` that was used — keep it,
    because `refresh_access_token` will not work without the same value.

    The access token is SHORT-LIVED (`expires_in`, 1800 s by default). For a
    credential that lasts, follow this with `auth tokens create` using the
    access token, which mints a long-lived one.

    If a step other than credentials or MFA comes back, the flow is ABORTED
    before raising, so an unfinished flow is not left pinned to this IP.
    """
    if not username or not password:
        raise ValueError("username and password are required")
    cid, redirect = _resolve_ids(client, client_id, redirect_uri)
    handler = resolve_handler(client, provider_type=provider_type, provider_id=provider_id)

    step = start_login_flow(
        client, handler=handler, client_id=cid, redirect_uri=redirect, flow_type="authorize"
    )
    flow_id = step.get("flow_id")
    steps = [step.get("step_id")]

    if step.get("type") != "create_entry":
        step = advance_login_flow(
            client,
            flow_id=flow_id,
            step_data={"username": username, "password": password},
            client_id=cid,
        )
        steps.append(step.get("step_id"))

    if step.get("type") != "create_entry" and _is_mfa_step(step):
        if not mfa_code:
            _safe_abort(client, flow_id)
            raise ValueError(
                f"This account requires multi-factor authentication (step "
                f"{step.get('step_id')!r}). Re-run with an --mfa-code, or drive the "
                "flow manually with `auth login-flow start` / `step`."
            )
        step = advance_login_flow(
            client, flow_id=flow_id, step_data={"code": mfa_code}, client_id=cid
        )
        steps.append(step.get("step_id"))

    if step.get("type") != "create_entry":
        _safe_abort(client, flow_id)
        raise HomeAssistantError(
            f"Login stopped at an unsupported step {step.get('step_id')!r} "
            f"(type {step.get('type')!r}). Drive it with `auth login-flow start` / "
            "`step`, which passes arbitrary fields through."
        )

    code = step.get("result")
    if not code:
        raise HomeAssistantError(
            f"Login flow completed without an authorization code: {step!r}"
        )
    tokens = exchange_code(client, code=code, client_id=cid)
    return {
        **tokens,
        "username": username,
        "handler": handler,
        "steps": [s for s in steps if s],
    }


def _is_mfa_step(step: dict) -> bool:
    """Whether a step is asking for a multi-factor code.

    HA's own TOTP module is `mfa_setup_flow` and the login step it inserts is
    `step_id: "mfa"`, but a custom MFA module may name it anything, so the
    serialized schema is the reliable signal: a single required `code` field.
    """
    if step.get("step_id") == "mfa":
        return True
    schema = step.get("data_schema") or []
    names = {field.get("name") for field in schema if isinstance(field, dict)}
    return names == {"code"}


def _safe_abort(client, flow_id: str | None) -> None:
    if not flow_id:
        return
    try:
        abort_login_flow(client, flow_id=flow_id)
    except (HomeAssistantError, ValueError):  # pragma: no cover - best effort
        pass


# ------------------------------------------------------------------- messages


def _describe(body: Any) -> str:
    """Render an auth-endpoint body as a sentence.

    These views answer with three different shapes — `{"message": …}` from
    `json_message`, `{"error": …, "error_description": …}` from the OAuth
    endpoints, and an empty body from `/auth/revoke` — and one of them is
    text/plain (`401: Unauthorized`, `500 Internal Server Error`).
    """
    if isinstance(body, dict):
        if body.get("error_description"):
            return f"{body.get('error')}: {body['error_description']}"
        if body.get("error"):
            return str(body["error"])
        if body.get("message"):
            return str(body["message"])
        return str(body) if body else "(empty body)"
    text = str(body).strip()
    return text or "(empty body)"


def _token_error(status: int, body: Any, *, grant: str) -> str:
    """Explain a `/auth/token` refusal, whose bodies are terse to the point of wrong."""
    error = body.get("error") if isinstance(body, dict) else None
    detail = _describe(body)
    if error == "unsupported_grant_type":
        return (
            f"POST /auth/token -> {status}: {detail}. Home Assistant reports this when "
            "the FORM BODY did not parse, which usually means the request went out as "
            "JSON — /auth/token reads `await request.post()` and sees only "
            "application/x-www-form-urlencoded."
        )
    if error == "invalid_grant":
        return (
            f"POST /auth/token -> {status}: {detail}. The refresh token is unknown to "
            "this instance — it was revoked, or it belongs to another Home Assistant."
        )
    if error == "invalid_request" and grant == "refresh_token":
        return (
            f"POST /auth/token -> {status}: {detail}. This grant checks that client_id "
            "matches the one the refresh token was ISSUED to, and reports a mismatch "
            "(or a missing client_id) with no further detail. Pass the same client_id "
            "`auth login` reported."
        )
    if error == "access_denied":
        return (
            f"POST /auth/token -> {status}: {detail}. The credentials are valid but the "
            "user may not log in — deactivated, or restricted to local access while "
            "this request arrived from elsewhere."
        )
    return f"POST /auth/token -> {status}: {detail}"
