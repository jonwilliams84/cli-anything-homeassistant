"""Home Assistant HTTP + WebSocket client.

This module is the backend that talks to the real Home Assistant server.
The CLI never reimplements Home Assistant logic — every command resolves to
one or more API calls handled here.
"""

from __future__ import annotations

import json
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
    """Raised for any Home Assistant API failure."""


class HomeAssistantClient:
    """Thin client wrapping Home Assistant's REST + WebSocket APIs."""

    def __init__(
        self,
        url: str = "http://localhost:8123",
        token: str = "",
        verify_ssl: bool = True,
        timeout: int = _DEFAULT_TIMEOUT,
    ):
        self.base_url = _normalize_base(url)
        self.token = token
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
                    f"{self.base_url}/api/", timeout=min(self.timeout, 5),
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
                f"GET {path} -> {resp.status_code}: {resp.text[:500]}"
            )
        return self._decode(resp)

    def post(self, path: str, payload: Any = None) -> Any:
        """POST JSON payload to a REST endpoint and return the decoded response."""
        try:
            if payload is None:
                resp = self.session.post(self._url(path), timeout=self.timeout)
            elif isinstance(payload, str):
                # Used by /api/template which expects a JSON object body, but
                # also for endpoints that take raw text. Default: send as JSON.
                resp = self.session.post(
                    self._url(path), json={"template": payload}, timeout=self.timeout
                )
            else:
                resp = self.session.post(self._url(path), json=payload, timeout=self.timeout)
        except requests.exceptions.ConnectionError as exc:
            raise self._connection_error(exc) from exc
        except requests.exceptions.Timeout as exc:
            raise HomeAssistantError(f"Request timed out after {self.timeout}s: {exc}") from exc
        self._check_auth(resp)
        if not resp.ok:
            raise HomeAssistantError(
                f"POST {path} -> {resp.status_code}: {resp.text[:500]}"
            )
        return self._decode(resp)

    def delete(self, path: str) -> Any:
        """DELETE a REST endpoint and return the decoded response."""
        try:
            resp = self.session.delete(self._url(path), timeout=self.timeout)
        except requests.exceptions.ConnectionError as exc:
            raise self._connection_error(exc) from exc
        self._check_auth(resp)
        if not resp.ok:
            raise HomeAssistantError(
                f"DELETE {path} -> {resp.status_code}: {resp.text[:500]}"
            )
        return self._decode(resp)

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
                pass

    def _ws_run(self, ws, msg_type: str, payload: dict | None) -> Any:
        """Auth + single command exchange on an open WebSocket."""
        auth_required = json.loads(ws.recv())
        if auth_required.get("type") != "auth_required":
            raise HomeAssistantError(
                f"Unexpected WS handshake: {auth_required!r}"
            )
        ws.send(json.dumps({"type": "auth", "access_token": self.token}))
        auth_result = json.loads(ws.recv())
        if auth_result.get("type") == "auth_invalid":
            raise HomeAssistantError(
                f"WebSocket auth_invalid: {auth_result.get('message', 'invalid token')}"
            )
        if auth_result.get("type") != "auth_ok":
            raise HomeAssistantError(f"WebSocket auth failed: {auth_result!r}")

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
                        f"{err.get('code', 'unknown')} {err.get('message', '')}"
                    )
                return data.get("result")
        raise HomeAssistantError(f"WS command {msg_type} timed out after {self.timeout}s")

    def ws_subscribe(self, msg_type: str, payload: dict | None,
                     on_message, stop_event: threading.Event) -> None:
        """Subscribe and stream messages until ``stop_event`` is set.

        ``on_message`` receives parsed event dicts (the inner ``event`` payload).
        """
        if websocket is None:
            raise HomeAssistantError(
                "The `websocket-client` package is required. "
                "Install with: pip install websocket-client"
            )

        url = _ws_url_from_http(self.base_url)
        ssl_opts = None if self.verify_ssl else {"cert_reqs": 0}
        ws = websocket.create_connection(url, timeout=self.timeout, sslopt=ssl_opts)
        try:
            handshake = json.loads(ws.recv())
            if handshake.get("type") != "auth_required":
                raise HomeAssistantError(f"Unexpected WS handshake: {handshake!r}")
            ws.send(json.dumps({"type": "auth", "access_token": self.token}))
            auth_result = json.loads(ws.recv())
            if auth_result.get("type") != "auth_ok":
                raise HomeAssistantError(f"WS auth failed: {auth_result!r}")

            ids = count(1)
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
                    raise HomeAssistantError(
                        f"WS subscribe failed: {data.get('error')}"
                    )
        finally:
            try:
                ws.close()
            except Exception:  # pragma: no cover
                pass
