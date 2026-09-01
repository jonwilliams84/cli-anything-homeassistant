"""Home Assistant HTTP + WebSocket client.

This module is the backend that talks to the real Home Assistant server.
The CLI never reimplements Home Assistant logic — every command resolves to
one or more API calls handled here.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import threading
import time
from itertools import count
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests

try:
    import websocket  # type: ignore
except ImportError:  # pragma: no cover
    websocket = None  # noqa: N816


_DEFAULT_TIMEOUT = 30

_logger = logging.getLogger(__name__)


def _normalize_base(url: str) -> str:
    """Normalize a Home Assistant URL to scheme://host[:port] (no path)."""
    if not url:
        raise ValueError("URL cannot be empty")
    if "://" not in url:
        url = "http://" + url
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")


def _ws_url_from_http(http_url: str) -> str:
    """Convert http(s)://host[:port] → ws(s)://host[:port]/api/websocket."""
    base = _normalize_base(http_url)
    if base.startswith("https://"):
        ws = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        ws = "ws://" + base[len("http://") :]
    else:  # pragma: no cover — defensive, _normalize_base would have raised
        ws = base
    return ws + "/api/websocket"


class HomeAssistantError(RuntimeError):
    """Raised for any Home Assistant API failure.

    `code` carries Home Assistant's own MACHINE-READABLE error code when the
    failure came back as a websocket `result` with `success: false` — e.g.
    `unknown_command`, `not_logged_in`, `unauthorized`, `unknown_error`. It is
    `None` for transport, auth-handshake and REST failures, which have no such
    code.

    It exists so a core module can branch on the code rather than by matching
    substrings of the message. `cloud.py` uses it to turn `not_logged_in` into
    a named answer, and `core_config.detect()` uses it to tell "the geo-IP
    lookup blew up on the HA host" apart from "you may not call this".

    `status` is the counterpart for the REST side: the HTTP status of a failed
    request. A REST failure has no machine-readable code — and, for the service
    endpoint, no BODY either (see `core/service_errors.py`), so the status is
    the only thing that distinguishes "HA never ran this" (400) from "HA ran it
    and the handler raised" (500). It is `None` for websocket and transport
    failures.

    The `str()` of the exception is UNCHANGED by either of these — both are
    additive, so anything already asserting on the message text keeps working.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


class HomeAssistantClient:
    """Thin client wrapping Home Assistant's REST + WebSocket APIs."""

    def __init__(
        self,
        url: str = "http://localhost:8123",
        token: str | None = None,
        verify_ssl: bool = True,
        timeout: int = _DEFAULT_TIMEOUT,
    ):
        self.base_url = _normalize_base(url)
        self.token = token or ""
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = verify_ssl
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.session.headers.update({"Content-Type": "application/json"})

    # ------------------------------------------------------------------ helpers

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/{path.lstrip('/')}"

    def _connection_error(self, exc: Exception) -> HomeAssistantError:
        return HomeAssistantError(
            f"Cannot reach Home Assistant at {self.base_url}.\n"
            f"Ensure Home Assistant is running and the URL/token are correct.\n"
            f"Install: pip install homeassistant\n"
            f"Or Docker: docker run -d --name hass -p 8123:8123 "
            f"ghcr.io/home-assistant/home-assistant:stable\n"
            f"Underlying error: {exc}"
        )

    def _check_auth(self, resp: requests.Response) -> None:
        if resp.status_code == 401:
            # Distinguish "bad token" from "valid token but the user lacks
            # permission for this endpoint" (e.g. /api/template requires admin).
            # We probe the root /api/ — if THAT works, the token is fine and
            # the 401 is a per-endpoint policy denial.
            try:
                probe = self.session.get(
                    f"{self.base_url}/api/",
                    timeout=min(self.timeout, 5),
                )
                if probe.ok:
                    raise HomeAssistantError(
                        f"Unauthorized (401) for {resp.url}.\n"
                        "Token authenticates fine — but this endpoint requires "
                        "elevated permissions (typically admin). Run `whoami` to "
                        "see the active user, then create a token under an admin "
                        "user via Profile -> Long-Lived Access Tokens."
                    )
            except requests.exceptions.RequestException:
                pass
            raise HomeAssistantError(
                "Unauthorized (401). Set a valid long-lived access token via "
                "`config set --token <token>` or HASS_TOKEN."
            )

    def _decode(self, resp: requests.Response) -> Any:
        if not resp.content:
            return {}
        ctype = resp.headers.get("Content-Type", "")
        if "application/json" in ctype:
            try:
                return resp.json()
            except ValueError:
                return resp.text
        return resp.text

    # ------------------------------------------------------------------ REST

    def get(self, path: str, params: dict | None = None) -> Any:
        """GET a REST endpoint and return the decoded payload."""
        try:
            resp = self.session.get(self._url(path), params=params, timeout=self.timeout)
        except requests.exceptions.ConnectionError as exc:
            raise self._connection_error(exc) from exc
        except requests.exceptions.Timeout as exc:
            raise HomeAssistantError(f"Request timed out after {self.timeout}s: {exc}") from exc
        self._check_auth(resp)
        if not resp.ok:
            raise HomeAssistantError(
                f"GET {path} -> {resp.status_code}: {resp.text[:500]}",
                status=resp.status_code,
            )
        return self._decode(resp)

    def post(self, path: str, payload: Any = None, params: dict | None = None) -> Any:
        """POST JSON payload to a REST endpoint and return the decoded response."""
        try:
            if payload is None:
                resp = self.session.post(self._url(path), params=params, timeout=self.timeout)
            elif isinstance(payload, str):
                # Used by /api/template which expects a JSON object body, but
                # also for endpoints that take raw text. Default: send as JSON.
                resp = self.session.post(
                    self._url(path),
                    params=params,
                    json={"template": payload},
                    timeout=self.timeout,
                )
            else:
                resp = self.session.post(
                    self._url(path),
                    params=params,
                    json=payload,
                    timeout=self.timeout,
                )
        except requests.exceptions.ConnectionError as exc:
            raise self._connection_error(exc) from exc
        except requests.exceptions.Timeout as exc:
            raise HomeAssistantError(f"Request timed out after {self.timeout}s: {exc}") from exc
        self._check_auth(resp)
        if not resp.ok:
            raise HomeAssistantError(
                f"POST {path} -> {resp.status_code}: {resp.text[:500]}",
                status=resp.status_code,
            )
        return self._decode(resp)

    def download(
        self,
        path: str,
        dest,
        params: Any = None,
        chunk_size: int = 1024 * 1024,
    ) -> dict:
        """Stream a binary REST response to a file and report what landed.

        Needed because `get()` decodes the body — fine for JSON, useless for a
        backup tarball, which is measured in gigabytes and must never be held in
        memory. The response is streamed straight to disk.

        `params` accepts a list of pairs as well as a dict, because HA reads
        `agent_id` with `query.getall()` — a backup can be downloaded from, and
        uploaded to, several agents, and a plain dict cannot express a repeated
        key.

        Nothing is written until the status is known: a 4xx from HA is a small
        JSON or text body, and truncating the caller's file to hold an error
        message would be the worst possible outcome for a restore.
        """
        try:
            resp = self.session.get(
                self._url(path), params=params, timeout=self.timeout, stream=True
            )
        except requests.exceptions.ConnectionError as exc:
            raise self._connection_error(exc) from exc
        except requests.exceptions.Timeout as exc:
            raise HomeAssistantError(f"Request timed out after {self.timeout}s: {exc}") from exc
        with resp:
            self._check_auth(resp)
            if not resp.ok:
                raise HomeAssistantError(
                    f"GET {path} -> {resp.status_code}: {resp.text[:500]}",
                    status=resp.status_code,
                )
            written = 0
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        fh.write(chunk)
                        written += len(chunk)
        declared = resp.headers.get("Content-Length")
        return {
            "path": str(dest),
            "bytes": written,
            "content_type": resp.headers.get("Content-Type"),
            "declared_length": int(declared) if declared and declared.isdigit() else None,
            # MEASURED on a real 195MB backup: HA DOES send a Content-Length,
            # and it matched the bytes written exactly. So a truncated transfer
            # is detectable, and `size_matches` says so. It is None — not
            # False — when nothing was declared, because "not checked" and
            # "checked and wrong" must not read the same.
            "size_matches": (
                (written == int(declared)) if declared and declared.isdigit() else None
            ),
        }

    def upload(
        self,
        path: str,
        file_path,
        field: str = "file",
        params: Any = None,
        extra_fields: dict | None = None,
        content_type: str | None = None,
    ) -> Any:
        """POST a multipart/form-data upload and return the decoded response.

        THE SESSION-HEADER TRAP: this client sets `Content-Type: application/json`
        on the SESSION, so it is sent on every request. A multipart POST must
        carry `multipart/form-data; boundary=…` instead, and requests only
        generates that header when it is not already set. Leaving the session
        header in place produces a JSON content-type on a multipart body, and
        HA answers with a 400 that says nothing about the cause. The header is
        therefore removed for this request only, by passing an explicit
        `headers` mapping with Content-Type set to None.

        The field name matters and is not cosmetic: `/api/file_upload` rejects
        anything not called `file`, while `/api/backup/upload` reads the first
        part regardless of its name.

        SO DOES THE CONTENT TYPE, for one endpoint. `/api/media_source/local_source
        /upload` checks `content_type.startswith(("image/", "video/", "audio/"))`
        and returns a bare 400 otherwise — the reason ("Content type not
        allowed") goes to HA's LOG and not to the caller. A hard-coded
        `application/octet-stream` therefore fails every media upload. It is
        guessed from the filename when not given, which is right for media and
        harmless for the endpoints that do not look.
        """
        file_path = str(file_path)
        try:
            with open(file_path, "rb") as fh:
                guessed = content_type or (
                    mimetypes.guess_type(file_path)[0] or "application/octet-stream"
                )
                files = {field: (os.path.basename(file_path), fh, guessed)}
                resp = self.session.post(
                    self._url(path),
                    params=params,
                    files=files,
                    data=extra_fields or None,
                    headers={"Content-Type": None},
                    timeout=self.timeout,
                )
        except FileNotFoundError as exc:
            raise HomeAssistantError(f"No such file to upload: {file_path}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise self._connection_error(exc) from exc
        except requests.exceptions.Timeout as exc:
            raise HomeAssistantError(
                f"Upload timed out after {self.timeout}s — a large backup needs a "
                f"bigger --timeout: {exc}"
            ) from exc
        self._check_auth(resp)
        if not resp.ok:
            raise HomeAssistantError(
                f"POST {path} -> {resp.status_code}: {resp.text[:500]}",
                status=resp.status_code,
            )
        return self._decode(resp)

    def delete(self, path: str, params: dict | None = None) -> Any:
        """DELETE a REST endpoint and return the decoded response."""
        try:
            resp = self.session.delete(self._url(path), params=params, timeout=self.timeout)
        except requests.exceptions.ConnectionError as exc:
            raise self._connection_error(exc) from exc
        self._check_auth(resp)
        if not resp.ok:
            raise HomeAssistantError(
                f"DELETE {path} -> {resp.status_code}: {resp.text[:500]}",
                status=resp.status_code,
            )
        return self._decode(resp)

    def root_request(
        self,
        method: str,
        path: str,
        *,
        json_payload: Any = None,
        form: dict | None = None,
        params: dict | None = None,
        send_auth: bool = True,
    ) -> tuple[int, Any]:
        """Call a path that is NOT under `/api/`, and return `(status, body)`.

        `get`/`post`/`delete` all route through `_url()`, which hardcodes the
        `/api/` prefix. Home Assistant's authentication endpoints do not live
        there — they are mounted at the server ROOT (`/auth/token`,
        `/auth/login_flow`, `/.well-known/oauth-authorization-server`) — so
        they are unreachable through those methods. This is the transport for
        them.

        THREE THINGS DIFFER FROM EVERY OTHER REQUEST THIS CLIENT MAKES.

        1. THE BODY ENCODING IS NOT UNIFORM ACROSS THE AUTH ENDPOINTS.
           `/auth/login_flow` is wrapped in `RequestDataValidator` and parses
           JSON (a form body is answered `400 {"message": "Invalid JSON."}`).
           `/auth/token` and `/auth/revoke` call `await request.post()`, which
           only populates from a FORM content type. Since `__init__` sets
           `Content-Type: application/json` on the session for every request,
           a form body sent without an override is parsed as an EMPTY
           MultiDict, and the reply is `400 {"error":
           "unsupported_grant_type"}` — an error about the grant type when the
           grant type was correct and the CONTENT TYPE was the problem. Pass
           `form=` and the header is set to `application/x-www-form-urlencoded`
           for that one request.

        2. A NON-2xx BODY IS THE ANSWER, NOT A FAILURE. The login flow reports
           a bad password as `200` with `errors.base = invalid_auth`, and the
           token endpoint reports every refusal as a 400/403 carrying an OAuth
           `error` code that names what to do. Raising on status would throw
           the diagnosis away, so the status is RETURNED and the caller
           decides. Transport failures (unreachable, timeout) still raise.

        3. AUTH IS OPTIONAL AND SOMETIMES MUST BE ABSENT. These endpoints exist
           to obtain a token, so they run with none. `send_auth=False` drops
           the session's `Authorization` header for the request — needed for
           `/auth/login_flow`, where a stale bearer would otherwise be offered
           on a call whose entire purpose is that there is no valid one.
           (Measured: `/auth/token` tolerates a garbage bearer and answers 200
           regardless, because `requires_auth = False` and the middleware only
           RECORDS the result. Dropping it is hygiene, not a workaround.)
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers: dict[str, str | None] = {}
        if form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if not send_auth:
            headers["Authorization"] = None
        try:
            resp = self.session.request(
                method.upper(),
                url,
                params=params,
                json=json_payload,
                data=form,
                headers=headers or None,
                timeout=self.timeout,
            )
        except requests.exceptions.ConnectionError as exc:
            raise self._connection_error(exc) from exc
        except requests.exceptions.Timeout as exc:
            raise HomeAssistantError(f"Request timed out after {self.timeout}s: {exc}") from exc
        return resp.status_code, self._decode(resp)

    # ------------------------------------------------------------------ WebSocket

    def ws_call(self, msg_type: str, payload: dict | None = None) -> Any:
        """Open a short-lived WebSocket, authenticate, send one command, return result.

        Suitable for one-off registry calls (`config/area_registry/list`,
        `config/device_registry/list`, etc.). Long-lived subscriptions use
        `ws_subscribe()` instead.
        """
        if websocket is None:
            raise HomeAssistantError(
                "The `websocket-client` package is required for registry commands. "
                "Install with: pip install websocket-client"
            )

        url = _ws_url_from_http(self.base_url)
        ssl_opts = None if self.verify_ssl else {"cert_reqs": 0}
        try:
            ws = websocket.create_connection(url, timeout=self.timeout, sslopt=ssl_opts)
        except (OSError, websocket.WebSocketException) as exc:  # type: ignore[attr-defined]
            raise self._connection_error(exc) from exc
        try:
            return self._ws_run(ws, msg_type, payload)
        finally:
            try:
                ws.close()
            except Exception:  # pragma: no cover
                _logger.debug("error closing websocket", exc_info=True)

    def ws_ping(self) -> float:
        """Round-trip the websocket `ping` command; return the latency in ms.

        WHY THIS IS NOT `ws_call("ping")`
            Every other websocket command answers with a `result` message, and
            `_ws_run` returns as soon as it sees one. `ping` does not: HA's
            handler replies `{"id": N, "type": "pong"}` and never sends a
            `result`. Routed through `ws_call` it therefore matches nothing and
            fails with a `timed out` after the FULL client timeout — reporting
            a healthy instance as unreachable after 30 idle seconds.

        The measurement covers connect + auth + one command, because that is
        the sequence every other websocket command in this harness pays. A
        `ping` that succeeds while REST also works is the evidence that a
        reverse proxy is forwarding `/api/` but not upgrading
        `/api/websocket` — the failure mode that breaks roughly half of these
        commands while `system status` stays green.
        """
        if websocket is None:
            raise HomeAssistantError(
                "The `websocket-client` package is required for registry commands. "
                "Install with: pip install websocket-client"
            )
        url = _ws_url_from_http(self.base_url)
        ssl_opts = None if self.verify_ssl else {"cert_reqs": 0}
        started = time.monotonic()
        try:
            ws = websocket.create_connection(url, timeout=self.timeout, sslopt=ssl_opts)
        except (OSError, websocket.WebSocketException) as exc:  # type: ignore[attr-defined]
            raise self._connection_error(exc) from exc
        try:
            self._ws_authenticate(ws)
            ws.send(json.dumps({"id": 1, "type": "ping"}))
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                raw = ws.recv()
                if not raw:
                    continue
                data = json.loads(raw)
                if data.get("id") != 1:
                    continue
                if data.get("type") == "pong":
                    return (time.monotonic() - started) * 1000.0
                if data.get("type") == "result" and not data.get("success", False):
                    # Older/stripped builds may not register `ping` at all.
                    err = data.get("error", {})
                    raise HomeAssistantError(
                        f"WS command ping failed: "
                        f"{err.get('code', 'unknown')} {err.get('message', '')}",
                        code=err.get("code"),
                    )
            raise HomeAssistantError(f"WS command ping timed out after {self.timeout}s")
        finally:
            try:
                ws.close()
            except Exception:  # pragma: no cover
                _logger.debug("error closing websocket", exc_info=True)

    def _ws_authenticate(self, ws) -> None:
        """Consume `auth_required`, send the token, require `auth_ok`."""
        auth_required = json.loads(ws.recv())
        if auth_required.get("type") != "auth_required":
            raise HomeAssistantError(f"Unexpected WS handshake: {auth_required!r}")
        ws.send(json.dumps({"type": "auth", "access_token": self.token}))
        auth_result = json.loads(ws.recv())
        if auth_result.get("type") == "auth_invalid":
            raise HomeAssistantError(
                f"WebSocket auth_invalid: {auth_result.get('message', 'invalid token')}"
            )
        if auth_result.get("type") != "auth_ok":
            raise HomeAssistantError(f"WebSocket auth failed: {auth_result!r}")

    def _ws_run(self, ws, msg_type: str, payload: dict | None) -> Any:
        """Auth + single command exchange on an open WebSocket."""
        self._ws_authenticate(ws)

        message = {"id": 1, "type": msg_type}
        if payload:
            message.update(payload)
        ws.send(json.dumps(message))

        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            raw = ws.recv()
            if not raw:
                continue
            data = json.loads(raw)
            if data.get("id") != 1:
                continue
            if data.get("type") == "result":
                if not data.get("success", False):
                    err = data.get("error", {})
                    raise HomeAssistantError(
                        f"WS command {msg_type} failed: "
                        f"{err.get('code', 'unknown')} {err.get('message', '')}",
                        code=err.get("code"),
                    )
                return data.get("result")
        raise HomeAssistantError(f"WS command {msg_type} timed out after {self.timeout}s")

    def ws_run_events(
        self,
        msg_type: str,
        payload: dict | None = None,
        *,
        is_terminal=None,
        timeout: float | None = None,
        on_ack=None,
        on_event=None,
    ) -> list[dict]:
        """Send one command that ACKS FIRST and then STREAMS to completion.

        WHY NEITHER `ws_call` NOR `ws_subscribe` CAN DO THIS
            HA has three shapes of websocket command, and this harness only had
            clients for two of them.

              * request/response — one `result` carrying the answer. `ws_call`
                returns at the first `result`, which is correct here.
              * open-ended subscription — an empty `result` ack, then events
                forever. `ws_subscribe` streams until the CALLER stops it.
              * run-to-completion — an empty `result` ack, then events, then
                the run finishes ON ITS OWN. `assist_pipeline/run` is this one.

            Routed through `ws_call`, a run-to-completion command returns
            `None` at the ack and CLOSES THE SOCKET, which cancels the run
            server-side before it produces anything (HA registers
            `connection.subscriptions[msg["id"]] = run_task.cancel`). Routed
            through `ws_subscribe` it never returns, because nothing outside
            knows the run ended. The missing piece is a terminal condition
            that comes from the DATA, which is what `is_terminal` supplies.

        ``is_terminal(event) -> bool`` is called for each streamed event; the
        first True ends the collection and its event is included in the return.
        With no predicate this behaves like a bounded subscription and runs
        until ``timeout``, which is a legitimate way to sample a stream.

        ``on_ack(send_binary)`` runs on a DAEMON THREAD once the server has
        acked, and receives a callable that frames a binary websocket message.
        That is how audio is pushed into a pipeline while its events are
        arriving — sending it inline would deadlock the moment HA's send buffer
        filled, because nothing would be draining the socket. Anything the
        thread raises is captured and re-raised on the caller's thread once
        collection ends, so a failed upload is never reported as a quiet
        no-audio run.

        Returns the list of collected event payloads.
        """
        if websocket is None:
            raise HomeAssistantError(
                "The `websocket-client` package is required. "
                "Install with: pip install websocket-client"
            )

        limit = float(timeout) if timeout else float(self.timeout)
        url = _ws_url_from_http(self.base_url)
        ssl_opts = None if self.verify_ssl else {"cert_reqs": 0}
        try:
            ws = websocket.create_connection(url, timeout=self.timeout, sslopt=ssl_opts)
        except (OSError, websocket.WebSocketException) as exc:  # type: ignore[attr-defined]
            raise self._connection_error(exc) from exc

        events: list[dict] = []
        sender_error: list[BaseException] = []
        sender: threading.Thread | None = None
        try:
            self._ws_authenticate(ws)
            message = {"id": 1, "type": msg_type}
            if payload:
                message.update(payload)
            ws.send(json.dumps(message))

            deadline = time.monotonic() + limit
            acked = False
            finished = is_terminal is None
            closed = False
            ws.settimeout(1.0)
            while time.monotonic() < deadline:
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:  # type: ignore[attr-defined]
                    continue
                except (OSError, websocket.WebSocketException):  # type: ignore[attr-defined]
                    closed = True
                    break
                if not raw:
                    continue
                if isinstance(raw, bytes):
                    # HA only sends binary for audio-output byte streams, which
                    # no command here subscribes to. Ignore rather than crash
                    # the JSON decoder.
                    continue
                data = json.loads(raw)
                if data.get("id") != 1:
                    continue
                kind = data.get("type")
                if kind == "result":
                    if not data.get("success", False):
                        err = data.get("error", {})
                        raise HomeAssistantError(
                            f"WS command {msg_type} failed: "
                            f"{err.get('code', 'unknown')} {err.get('message', '')}",
                            code=err.get("code"),
                        )
                    acked = True
                    if on_ack is not None:

                        def _pump() -> None:
                            try:
                                on_ack(lambda blob: ws.send_binary(blob))
                            except BaseException as exc:  # noqa: BLE001
                                sender_error.append(exc)

                        sender = threading.Thread(target=_pump, daemon=True)
                        sender.start()
                    continue
                if kind == "event":
                    event = data.get("event")
                    events.append(event)
                    if on_event is not None:
                        on_event(event)
                    if is_terminal is not None and is_terminal(event):
                        finished = True
                        break

            if not finished:
                # The sender is joined FIRST so its own failure — a WAV that
                # vanished mid-read, a socket that went away — is reported
                # instead of the timeout it caused.
                if sender is not None:
                    sender.join(timeout=1.0)
                if sender_error:
                    raise sender_error[0]
                reason = "the connection closed" if closed else f"it did not finish within {limit}s"
                raise HomeAssistantError(
                    f"WS command {msg_type} ended early: {reason} "
                    f"({'acked' if acked else 'never acked'}, "
                    f"{len(events)} event(s) received)"
                )
        finally:
            try:
                ws.close()
            except Exception:  # pragma: no cover
                _logger.debug("error closing websocket", exc_info=True)

        if sender is not None:
            sender.join(timeout=1.0)
        if sender_error:
            raise sender_error[0]
        return events

    def ws_subscribe(
        self, msg_type: str, payload: dict | None, on_message, stop_event: threading.Event
    ) -> None:
        """Subscribe and stream messages until ``stop_event`` is set.

        ``on_message`` receives parsed event dicts (the inner ``event`` payload).

        On exit the subscription is explicitly cancelled via ``unsubscribe_events``
        before the WebSocket is closed, so the HA server isn't left tracking
        a dangling subscription when the CLI is Ctrl-C'd.
        """
        if websocket is None:
            raise HomeAssistantError(
                "The `websocket-client` package is required. "
                "Install with: pip install websocket-client"
            )

        url = _ws_url_from_http(self.base_url)
        ssl_opts = None if self.verify_ssl else {"cert_reqs": 0}
        ws = websocket.create_connection(url, timeout=self.timeout, sslopt=ssl_opts)
        sub_id: int | None = None
        ids = count(1)
        try:
            handshake = json.loads(ws.recv())
            if handshake.get("type") != "auth_required":
                raise HomeAssistantError(f"Unexpected WS handshake: {handshake!r}")
            ws.send(json.dumps({"type": "auth", "access_token": self.token}))
            auth_result = json.loads(ws.recv())
            if auth_result.get("type") != "auth_ok":
                raise HomeAssistantError(f"WS auth failed: {auth_result!r}")

            sub_id = next(ids)
            message = {"id": sub_id, "type": msg_type}
            if payload:
                message.update(payload)
            ws.send(json.dumps(message))

            ws.settimeout(1.0)
            while not stop_event.is_set():
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:  # type: ignore[attr-defined]
                    continue
                except (OSError, websocket.WebSocketException):  # type: ignore[attr-defined]
                    break
                if not raw:
                    continue
                data = json.loads(raw)
                if data.get("type") == "event" and data.get("id") == sub_id:
                    on_message(data.get("event"))
                elif data.get("type") == "result" and not data.get("success", False):
                    raise HomeAssistantError(f"WS subscribe failed: {data.get('error')}")
        finally:
            # Best-effort unsubscribe before close so the HA server isn't left
            # tracking a stale subscription id. Ignore failures — the socket
            # may already be half-closed when we get here.
            if sub_id is not None:
                try:
                    ws.settimeout(2.0)
                    ws.send(
                        json.dumps(
                            {
                                "id": next(ids),
                                "type": "unsubscribe_events",
                                "subscription": sub_id,
                            }
                        )
                    )
                except Exception:
                    _logger.debug("error sending unsubscribe_events", exc_info=True)
            try:
                ws.close()
            except Exception:  # pragma: no cover
                _logger.debug("error closing websocket", exc_info=True)
