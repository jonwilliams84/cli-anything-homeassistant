"""End-to-end tests against a real Home Assistant instance.

These tests boot a real Home Assistant in a tmp config directory, mint a
long-lived token via HA's auth manager, and exercise every CLI surface
through both the imported core modules and the installed
`cli-anything-homeassistant` command.

They are NOT skipped on connection errors — they only skip when the
`homeassistant` Python package itself isn't installed (a hard-dependency
gate, per the harness rules).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cli_anything.homeassistant.core import (
    automation as automation_core,
    events as events_core,
    history as history_core,
    project,
    registry as registry_core,
    script as script_core,
    services as services_core,
    states as states_core,
    system as system_core,
    template as template_core,
)
from cli_anything.homeassistant.utils.homeassistant_backend import (
    HomeAssistantClient,
)


def _resolve_cli(name: str) -> list[str]:
    """Resolve the installed CLI command, falling back to `python -m`.

    Set `CLI_ANYTHING_FORCE_INSTALLED=1` to require the installed entry point.
    """
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    module = name.replace("cli-anything-", "cli_anything.") + "." + name.split("-")[-1] + "_cli"
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


CLI_BASE = _resolve_cli("cli-anything-homeassistant")


# ────────────────────────────────────────────────────────── live core tests

@pytest.fixture
def live_client(hass_instance) -> HomeAssistantClient:
    return HomeAssistantClient(
        url=hass_instance["url"],
        token=hass_instance["token"],
        timeout=30,
    )


class TestLiveSystem:
    def test_status(self, live_client):
        s = system_core.status(live_client)
        assert isinstance(s, dict)
        assert "message" in s
        print(f"\n  status: {s}")

    def test_config(self, live_client):
        cfg = system_core.config(live_client)
        assert "version" in cfg
        assert "location_name" in cfg
        print(f"\n  HA version: {cfg.get('version')}")

    def test_core_state(self, live_client):
        cs = system_core.core_state(live_client)
        assert "state" in cs
        # HA reports one of these states depending on bootstrap progress.
        # The case is normalized to uppercase in newer HA versions.
        assert cs["state"].upper() in (
            "RUNNING", "NOT_RUNNING", "STARTING", "STOPPED", "STOPPING", "FINAL_WRITE",
        )
        print(f"\n  core_state: {cs}")

    def test_components(self, live_client):
        comps = system_core.components(live_client)
        assert isinstance(comps, list)
        assert "api" in comps
        print(f"\n  components count: {len(comps)}")

    def test_error_log(self, live_client):
        log = system_core.error_log(live_client, lines=5)
        assert isinstance(log, str)


class TestLiveStates:
    def test_set_and_get(self, live_client):
        states_core.set_state(
            live_client,
            "sensor.cli_anything_test_temp",
            "21.5",
            attributes={"unit_of_measurement": "°C", "friendly_name": "CLI Test Temp"},
        )
        s = states_core.get_state(live_client, "sensor.cli_anything_test_temp")
        assert s["state"] == "21.5"
        assert s["attributes"]["unit_of_measurement"] == "°C"

    def test_list_with_domain(self, live_client):
        # Ensure at least one sensor exists from previous test, otherwise create one.
        states_core.set_state(live_client, "sensor.cli_x", "1")
        items = states_core.list_states(live_client, domain="sensor")
        assert any(s.get("entity_id") == "sensor.cli_x" for s in items)

    def test_count_by_domain(self, live_client):
        counts = states_core.count_by_domain(live_client)
        # `sensor` should exist after the earlier set_state above.
        assert "sensor" in counts
        print(f"\n  domain counts: {counts}")


class TestLiveServices:
    def test_list_includes_persistent_notification(self, live_client):
        domains = services_core.list_domains(live_client)
        assert "persistent_notification" in domains
        assert "homeassistant" in domains

    def test_call_persistent_notification(self, live_client):
        # In modern HA, persistent_notification.create stores into hass.data
        # rather than creating an entity. We just verify the call completes.
        result = services_core.call_service(
            live_client,
            "persistent_notification",
            "create",
            service_data={
                "title": "CLI test",
                "message": "Hello from cli-anything",
                "notification_id": "cli_anything_e2e",
            },
        )
        # The REST endpoint returns the list of state changes (often empty for
        # services that don't mutate states).
        assert result is not None

    def test_call_homeassistant_check_config(self, live_client):
        # `homeassistant.check_config` exists on every install and is safe.
        result = services_core.call_service(
            live_client, "homeassistant", "check_config",
        )
        assert result is not None


class TestLiveEvents:
    def test_list_listeners(self, live_client):
        listeners = events_core.list_listeners(live_client)
        assert isinstance(listeners, list)
        # Always at least state_changed has listeners
        assert any(l.get("event") == "state_changed" for l in listeners)

    def test_fire_event(self, live_client):
        result = events_core.fire_event(live_client, "cli_anything_test", {"hello": "world"})
        assert isinstance(result, dict)


class TestLiveTemplate:
    def test_render_now(self, live_client):
        out = template_core.render(live_client, "{{ now().year }}")
        assert out.isdigit()
        assert int(out) >= 2024

    def test_render_state(self, live_client):
        states_core.set_state(live_client, "sensor.cli_template_test", "42")
        out = template_core.render(
            live_client, '{{ states("sensor.cli_template_test") }}'
        )
        assert out == "42"


class TestLiveRegistry:
    def test_area_list(self, live_client):
        areas = registry_core.list_areas(live_client)
        assert isinstance(areas, list)

    def test_device_list(self, live_client):
        devices = registry_core.list_devices(live_client)
        assert isinstance(devices, list)

    def test_entity_list(self, live_client):
        entities = registry_core.list_entities(live_client)
        assert isinstance(entities, list)


class TestLiveAutomation:
    def test_reload_succeeds(self, live_client):
        # Reload is safe even with empty automations.yaml
        automation_core.reload(live_client)


class TestLiveScript:
    def test_reload_succeeds(self, live_client):
        script_core.reload(live_client)


class TestLiveLogbook:
    def test_logbook_returns_list(self, live_client):
        entries = history_core.logbook(live_client, hours=1)
        assert isinstance(entries, list)


# ────────────────────────────────────────────────────────── subprocess CLI tests

class TestCLISubprocess:
    """Exercise the installed `cli-anything-homeassistant` command end-to-end."""

    def _env(self, hass_instance):
        env = os.environ.copy()
        env["HASS_URL"] = hass_instance["url"]
        env["HASS_TOKEN"] = hass_instance["token"]
        env["HASS_VERIFY_SSL"] = "0"
        return env

    def _run(self, args, hass_instance, check=True):
        return subprocess.run(
            CLI_BASE + args,
            capture_output=True, text=True,
            env=self._env(hass_instance),
            check=check,
            timeout=60,
        )

    def test_help_runs(self, hass_instance):
        result = self._run(["--help"], hass_instance)
        assert result.returncode == 0
        assert "system" in result.stdout
        assert "state" in result.stdout

    def test_config_show_json(self, hass_instance):
        result = self._run(["--json", "config", "show"], hass_instance)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["url"] == hass_instance["url"]
        assert data["token"].startswith("***")  # redacted

    def test_config_test_json(self, hass_instance):
        result = self._run(["--json", "config", "test"], hass_instance)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["connected"] is True

    def test_system_info_json(self, hass_instance):
        result = self._run(["--json", "system", "info"], hass_instance)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "message" in data

    def test_system_config_json(self, hass_instance):
        result = self._run(["--json", "system", "config"], hass_instance)
        data = json.loads(result.stdout)
        assert "version" in data
        print(f"\n  Live HA version: {data['version']}")

    def test_state_set_get_via_cli(self, hass_instance):
        self._run(
            ["state", "set", "sensor.cli_subproc_test", "99",
             "--attr", 'unit_of_measurement="V"'],
            hass_instance,
        )
        result = self._run(
            ["--json", "state", "get", "sensor.cli_subproc_test"],
            hass_instance,
        )
        data = json.loads(result.stdout)
        assert data["state"] == "99"
        assert data["attributes"]["unit_of_measurement"] == "V"

    def test_service_call_dry_run(self, hass_instance):
        result = self._run(
            ["--json", "service", "call", "light", "turn_on",
             "-T", "entity_id=light.does_not_exist", "--dry-run"],
            hass_instance,
        )
        data = json.loads(result.stdout)
        assert data["dry_run"] is True
        assert data["domain"] == "light"
        assert data["service"] == "turn_on"

    def test_service_call_via_subprocess(self, hass_instance):
        # Use homeassistant.check_config — universally available and safe.
        result = self._run(
            ["--json", "service", "call", "homeassistant", "check_config"],
            hass_instance,
        )
        assert result.returncode == 0
        # Result is either an empty list (no state changes) or a JSON object.
        json.loads(result.stdout)

    def test_template_render_via_cli(self, hass_instance):
        result = self._run(
            ["template", "{{ 2 + 2 }}"],
            hass_instance,
        )
        assert result.returncode == 0
        assert "4" in result.stdout.strip()

    def test_area_list_json_via_cli(self, hass_instance):
        result = self._run(["--json", "area", "list"], hass_instance)
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_state_counts_via_cli(self, hass_instance):
        result = self._run(["--json", "state", "counts"], hass_instance)
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert "sensor" in data  # we created sensors above

    def test_state_list_ids_only(self, hass_instance):
        result = self._run(
            ["--json", "state", "list", "--domain", "sensor", "--ids-only"],
            hass_instance,
        )
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert all(isinstance(x, str) and x.startswith("sensor.") for x in data if x)
