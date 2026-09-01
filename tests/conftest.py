"""Shared pytest fixtures for cli-anything-homeassistant."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

import pytest


# ────────────────────────────────────────────────────────── unit-test fixtures

class FakeClient:
    """Records calls; returns prepared responses indexed by (verb, path)."""

    def __init__(self):
        self.calls: list[dict] = []
        self.responses: dict[tuple[str, str], Any] = {}
        self.ws_responses: dict[str, Any] = {}
        self.ws_calls: list[dict] = []
        # Service-call recorder. `set_service(domain, svc, response)` registers a
        # canned response keyed by `domain.svc`; every call is appended to
        # `service_calls` so tests can assert on the payload.
        self.service_responses: dict[str, Any] = {}
        self.service_calls: list[dict] = []
        # WS failure recorder. `set_ws_error(type, code)` makes `ws_call` raise
        # the same `HomeAssistantError` the real client raises for a
        # `success: false` result — including HA's machine-readable `code`,
        # which core modules branch on (cloud's `not_logged_in`, detect's
        # `unknown_error`).
        self.ws_errors: dict[str, tuple[str, str]] = {}
        # `ws_ping` samples, in ms, popped in order; the last one repeats.
        self.ping_samples: list[float] = [1.0]
        self.ping_calls: int = 0
        self.ping_error: Exception | None = None
        # `ws_run_events` recorder — the ack-then-stream-to-completion shape.
        # `set_run_events(*events)` queues what the next run streams back;
        # every call is recorded in `run_event_calls`, and any binary frames
        # the caller pushed through `on_ack` land in `binary_frames`.
        self.run_event_calls: list[dict] = []
        self.queued_run_events: list[Any] = []
        self.binary_frames: list[bytes] = []
        # Downloads: `download()` writes this payload and reports its size.
        self.download_calls: list[dict] = []
        self.download_payload: bytes = b"fake-audio"
        # REST failure recorder — see `set_rest_error`.
        self.rest_errors: dict[tuple[str, str], tuple[int, str]] = {}
        # Root-path recorder — the `/auth/*` and `/.well-known/*` views, which
        # live OUTSIDE `/api/` and so never reach `get`/`post`. Keyed by
        # (VERB, path) and queued as a LIST, because the auth endpoints answer
        # the same (verb, path) differently on consecutive calls: a login flow
        # POSTs twice to `/auth/login_flow/{id}` and gets a form step then a
        # create_entry, and `revoke --verify` POSTs to `/auth/token` expecting
        # the refresh to now FAIL.
        self.root_calls: list[dict] = []
        self.root_responses: dict[tuple[str, str], list[tuple[int, Any]]] = {}

    #: Whatever a core module derives a default client_id from. A real-looking
    #: origin, since `validate_client_id` is applied to it for real.
    base_url = "http://fake.local:8123"

    def set_root(self, verb: str, path: str, status: int, body: Any = None) -> None:
        """Queue one `(status, body)` answer for `verb path` on `root_request`.

        Repeated calls QUEUE rather than overwrite; the last queued answer
        repeats once the queue is drained.
        """
        self.root_responses.setdefault((verb.upper(), path), []).append((status, body))

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
        """Shim for the non-`/api/` transport. Returns `(status, body)`.

        `send_auth` and the json/form split are RECORDED, not just accepted:
        which of the two encodings a call uses is the single most consequential
        detail on these endpoints (`/auth/login_flow` parses only JSON,
        `/auth/token` only a form body), so tests assert on it.
        """
        self.root_calls.append(
            {
                "method": method.upper(),
                "path": path,
                "json": json_payload,
                "form": form,
                "params": params,
                "send_auth": send_auth,
            }
        )
        queue = self.root_responses.get((method.upper(), path))
        if not queue:
            return 200, {}
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def set_run_events(self, *events: Any) -> None:
        """Queue the events the next `ws_run_events` call streams back."""
        self.queued_run_events.extend(events)

    def ws_run_events(
        self,
        msg_type: str,
        payload: dict | None = None,
        *,
        is_terminal=None,
        timeout: float | None = None,
        on_ack=None,
        on_event=None,
    ) -> list[Any]:
        """Shim for the run-to-completion websocket shape.

        Reproduces the ORDERING the real client has, because that ordering is
        what the audio path depends on: the ack lands first and starts
        `on_ack` on its own thread, the events follow, and only a delivered
        `run-start` can release a sender waiting for its handler id. A fake
        that called `on_ack` after the events would make a deadlock look fine.
        """
        self.run_event_calls.append(
            {"type": msg_type, "payload": payload, "timeout": timeout}
        )
        if msg_type in self.ws_errors:
            from cli_anything.homeassistant.utils.homeassistant_backend import (
                HomeAssistantError,
            )

            code, message = self.ws_errors[msg_type]
            raise HomeAssistantError(
                f"WS command {msg_type} failed: {code} {message}", code=code
            )

        sender_error: list[BaseException] = []
        sender: threading.Thread | None = None
        if on_ack is not None:

            def _pump() -> None:
                try:
                    on_ack(self.binary_frames.append)
                except BaseException as exc:  # noqa: BLE001
                    sender_error.append(exc)

            sender = threading.Thread(target=_pump, daemon=True)
            sender.start()

        delivered: list[Any] = []
        for event in self.queued_run_events:
            delivered.append(event)
            if on_event is not None:
                on_event(event)
            if is_terminal is not None and is_terminal(event):
                break
        self.queued_run_events.clear()
        if sender is not None:
            sender.join(timeout=15.0)
        if sender_error:
            raise sender_error[0]
        return delivered

    def download(self, path: str, dest, params: Any = None, chunk_size: int = 0) -> dict:
        path = path.lstrip("/")
        self.download_calls.append({"path": path, "dest": str(dest), "params": params})
        with open(dest, "wb") as fh:
            fh.write(self.download_payload)
        return {
            "path": str(dest),
            "bytes": len(self.download_payload),
            "content_type": "audio/x-wav",
            "declared_length": len(self.download_payload),
            "size_matches": True,
        }

    def set_ws_error(self, msg_type: str, code: str, message: str = "") -> None:
        self.ws_errors[msg_type] = (code, message)

    def set_ping(self, *samples: float) -> None:
        self.ping_samples = list(samples) or [1.0]

    def ws_ping(self) -> float:
        self.ping_calls += 1
        if self.ping_error is not None:
            raise self.ping_error
        idx = min(self.ping_calls - 1, len(self.ping_samples) - 1)
        return self.ping_samples[idx]

    def set_service(self, domain: str, service: str, response: Any) -> None:
        self.service_responses[f"{domain}.{service}"] = response

    def set_rest_error(self, verb: str, path: str, status: int, body: str = "") -> None:
        """Make `verb path` raise the same error the real client raises on a
        non-ok REST response — INCLUDING the HTTP status.

        The status is the whole point for `core/service_errors.py`: the
        service endpoint answers a failure with a status and an empty body, so
        400 ("HA never ran this") vs 500 ("HA ran it and the handler raised")
        is the only signal the client gets.
        """
        self.rest_errors[(verb.upper(), path.lstrip("/"))] = (status, body)

    def _maybe_rest_error(self, verb: str, path: str) -> None:
        entry = self.rest_errors.get((verb.upper(), path.lstrip("/").split("?", 1)[0]))
        if entry is None:
            return
        from cli_anything.homeassistant.utils.homeassistant_backend import (
            HomeAssistantError,
        )

        status, body = entry
        raise HomeAssistantError(
            f"{verb.upper()} {path} -> {status}: {body}", status=status
        )

    def set(self, verb: str, path: str, response: Any) -> None:
        self.responses[(verb.upper(), path.lstrip("/"))] = response

    def set_ws(self, msg_type: str, response: Any) -> None:
        self.ws_responses[msg_type] = response

    def get(self, path: str, params: dict | None = None) -> Any:
        path = path.lstrip("/")
        # Strip any querystring fragment for matching.
        match_path = path.split("?", 1)[0]
        self.calls.append({"verb": "GET", "path": path, "params": params})
        self._maybe_rest_error("GET", path)
        return self.responses.get(("GET", match_path),
                                  self.responses.get(("GET", path), []))

    def post(self, path: str, payload: Any = None,
              params: dict | None = None) -> Any:
        path = path.lstrip("/")
        match_path = path.split("?", 1)[0]
        call = {"verb": "POST", "path": path, "payload": payload}
        if params is not None:
            call["params"] = params
        self.calls.append(call)
        self._maybe_rest_error("POST", path)
        # If this looks like services/<domain>/<svc>, also record it via the
        # service-call recorder so logger / mqtt tests can inspect.
        if match_path.startswith("services/"):
            parts = match_path.split("/")
            if len(parts) >= 3:
                domain, service = parts[1], parts[2]
                self.service_calls.append({
                    "domain": domain, "service": service,
                    "service_data": payload,
                })
                key = f"{domain}.{service}"
                if key in self.service_responses:
                    return self.service_responses[key]
        return self.responses.get(("POST", match_path),
                                  self.responses.get(("POST", path), {}))

    def delete(self, path: str, params: dict | None = None) -> Any:
        path = path.lstrip("/")
        call = {"verb": "DELETE", "path": path}
        if params is not None:
            call["params"] = params
        self.calls.append(call)
        return self.responses.get(("DELETE", path), {})

    def ws_call(self, msg_type: str, payload: dict | None = None) -> Any:
        self.ws_calls.append({"type": msg_type, "payload": payload})
        if msg_type in self.ws_errors:
            from cli_anything.homeassistant.utils.homeassistant_backend import (
                HomeAssistantError,
            )

            code, message = self.ws_errors[msg_type]
            raise HomeAssistantError(
                f"WS command {msg_type} failed: {code} {message}", code=code
            )
        return self.ws_responses.get(msg_type, [])


class SubscribingFakeClient(FakeClient):
    """FakeClient subclass that supports ws_subscribe.

    Records each ``ws_subscribe`` call and delivers a queue of pre-set
    events synchronously before setting the stop_event so callers that
    block on the event loop return cleanly.

    Usage::

        client = SubscribingFakeClient()
        client.queue_events({"type": "event_1"}, {"type": "event_2"})
        # ws_subscribe will deliver both events and then set stop_event.

    Attributes
    ----------
    subscribe_calls:
        List of ``(msg_type, payload)`` tuples recorded for each
        ws_subscribe invocation.
    """

    def __init__(self) -> None:
        super().__init__()
        self.subscribe_calls: list[tuple[str, Any]] = []
        self._queued_events: list[Any] = []

    def queue_events(self, *events: Any) -> None:
        """Pre-load events to be delivered by the next ws_subscribe call."""
        self._queued_events.extend(events)

    # Accept both positional and keyword forms of on_message/stop_event so
    # callers using keyword-only args (hardware_info style) work transparently.
    def ws_subscribe(
        self,
        msg_type: str,
        payload: dict | None,
        on_message=None,
        stop_event: threading.Event | None = None,
        **kwargs,
    ) -> None:
        """Shim: record the call, deliver queued events, then stop."""
        if on_message is None:
            on_message = kwargs.get("on_message")
        if stop_event is None:
            stop_event = kwargs.get("stop_event")

        self.subscribe_calls.append((msg_type, payload))
        for event in self._queued_events:
            if stop_event is not None and stop_event.is_set():
                break
            on_message(event)
        self._queued_events.clear()
        # Signal stop so callers that block on the event loop can return.
        if stop_event is not None:
            stop_event.set()


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def subscribing_client() -> SubscribingFakeClient:
    return SubscribingFakeClient()


@pytest.fixture
def tmp_dir(tmp_path: Path) -> str:
    return str(tmp_path)


# ────────────────────────────────────────────────────────── E2E fixtures (real HA)

def _hass_available() -> bool:
    """Return True if the homeassistant Python package is importable."""
    try:
        import homeassistant  # noqa: F401
        return True
    except ImportError:
        return False


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_http(url: str, timeout: float) -> None:
    """Wait until URL responds with anything (404/401 included)."""
    import urllib.error
    import urllib.request
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except urllib.error.HTTPError:
            return
        except (urllib.error.URLError, OSError, ConnectionResetError):
            time.sleep(1.0)
    raise TimeoutError(f"Service at {url} never came up within {timeout}s")


def _create_long_lived_token(config_dir: Path, owner_username: str = "agent") -> str:
    """Create an owner user + long-lived access token directly via HA's auth store.

    This avoids the OAuth2 flow we'd otherwise have to drive in tests.
    """
    import asyncio

    from homeassistant import core
    from homeassistant.auth import auth_manager_from_config, models as auth_models
    from homeassistant.auth.providers import homeassistant as ha_auth

    async def _create() -> str:
        hass = core.HomeAssistant(str(config_dir))
        manager = await auth_manager_from_config(
            hass,
            [{"type": "homeassistant"}],
            [],
        )
        provider = manager.auth_providers[0]
        await provider.async_initialize()
        if isinstance(provider, ha_auth.HassAuthProvider):
            try:
                await provider.async_add_auth(owner_username, "test-password")
            except Exception:
                pass
        credentials = await provider.async_get_or_create_credentials(
            {"username": owner_username},
        )
        user = await manager.async_get_or_create_user(credentials)
        await manager.async_activate_user(user)
        # OWNERSHIP IS SET ON THE MODEL, NOT THROUGH `async_update_user`.
        #
        # This used to be `await manager.async_update_user(user, is_owner=True)`
        # inside a bare `except Exception: pass`. That method has no `is_owner`
        # parameter — only name/is_active/group_ids/local_only — so every call
        # raised `TypeError` and was swallowed, and the "owner user" this
        # helper documents was a plain admin on every run since. Nothing
        # noticed until a command that checks `user.is_owner` (the owner-only
        # credential admin pair) was tested against it and came back
        # `unauthorized`.
        #
        # `is_owner` is an attrs field on `auth.models.User` whose setter
        # refreshes the permission policy, and `_data_to_save()` reads it back
        # off the model, so assigning it directly both takes effect and
        # persists. Asserted rather than tried, so a future HA that moves it
        # fails loudly here instead of silently downgrading every e2e run.
        user.is_owner = True
        assert user.is_owner, "could not make the test user an owner"
        from datetime import timedelta
        refresh = await manager.async_create_refresh_token(
            user,
            client_name=f"cli-anything-tests-{uuid.uuid4().hex[:6]}",
            token_type=auth_models.TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN,
            access_token_expiration=timedelta(days=3650),
        )
        token = manager.async_create_access_token(refresh)
        # Force-save auth + provider data before shutdown — the AuthStore uses
        # debounced saves and hass.async_stop() may not flush them.
        await manager._store._store.async_save(manager._store._data_to_save())
        if hasattr(provider, "data") and provider.data is not None:
            await provider.data.async_save()
        await hass.async_stop()
        return token

    return asyncio.run(_create())


@pytest.fixture(scope="session")
def hass_instance() -> Iterator[dict]:
    """Boot a real Home Assistant in a tmp config; yield {url, token, config_dir, proc}."""
    if not _hass_available():
        pytest.skip(
            "Real Home Assistant not installed. "
            "Install with: pip install homeassistant"
        )

    port = _free_port()
    config_dir = Path(tempfile.mkdtemp(prefix="cli-hass-test-"))

    # Minimal config: only the API surface we need (no default_config to keep
    # boot times reasonable and avoid pulling huge requirements at runtime).
    (config_dir / "configuration.yaml").write_text(
        "homeassistant:\n"
        "  name: cli-anything-test\n"
        "  latitude: 52.3676\n"
        "  longitude: 4.9041\n"
        "  elevation: 0\n"
        "  unit_system: metric\n"
        "  time_zone: Etc/UTC\n"
        "api:\n"
        "auth:\n"
        "logbook:\n"
        "history:\n"
        "persistent_notification:\n"
        "conversation:\n"
        "media_source:\n"
        "automation: !include automations.yaml\n"
        "script: !include scripts.yaml\n"
        f"http:\n  server_port: {port}\n  server_host: 127.0.0.1\n"
        "logger:\n  default: warning\n"
    )
    for f in ("automations.yaml", "scripts.yaml"):
        (config_dir / f).write_text("[]\n")

    # Pre-create an owner user + long-lived access token.
    try:
        token = _create_long_lived_token(config_dir)
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        shutil.rmtree(config_dir, ignore_errors=True)
        pytest.skip(f"Could not provision HA auth in tmp config: {exc}\n{tb}")

    # Start HA
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "homeassistant", "--config", str(config_dir)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_http(base_url + "/api/", timeout=180)
    except TimeoutError as exc:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
        shutil.rmtree(config_dir, ignore_errors=True)
        pytest.skip(f"Home Assistant did not come up: {exc}\nLog:\n{out[-2000:]}")

    yield {
        "url": base_url,
        "token": token,
        "config_dir": str(config_dir),
        "proc": proc,
    }

    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    shutil.rmtree(config_dir, ignore_errors=True)
