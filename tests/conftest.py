"""Shared pytest fixtures for cli-anything-homeassistant."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
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

    def set_service(self, domain: str, service: str, response: Any) -> None:
        self.service_responses[f"{domain}.{service}"] = response

    def set(self, verb: str, path: str, response: Any) -> None:
        self.responses[(verb.upper(), path.lstrip("/"))] = response

    def set_ws(self, msg_type: str, response: Any) -> None:
        self.ws_responses[msg_type] = response

    def get(self, path: str, params: dict | None = None) -> Any:
        path = path.lstrip("/")
        # Strip any querystring fragment for matching.
        match_path = path.split("?", 1)[0]
        self.calls.append({"verb": "GET", "path": path, "params": params})
        return self.responses.get(("GET", match_path),
                                  self.responses.get(("GET", path), []))

    def post(self, path: str, payload: Any = None) -> Any:
        path = path.lstrip("/")
        match_path = path.split("?", 1)[0]
        self.calls.append({"verb": "POST", "path": path, "payload": payload})
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

    def delete(self, path: str) -> Any:
        path = path.lstrip("/")
        self.calls.append({"verb": "DELETE", "path": path})
        return self.responses.get(("DELETE", path), {})

    def ws_call(self, msg_type: str, payload: dict | None = None) -> Any:
        self.ws_calls.append({"type": msg_type, "payload": payload})
        return self.ws_responses.get(msg_type, [])


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


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
        try:
            await manager.async_update_user(user, is_owner=True)
        except Exception:
            pass
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
