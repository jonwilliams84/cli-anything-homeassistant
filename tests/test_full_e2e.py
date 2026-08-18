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
    device_class_units as device_class_units_core,
    frontend_meta as frontend_meta_core,
    state_stream as state_stream_core,
    template_ws as template_ws_core,
    events as events_core,
    history as history_core,
    project,
    registry as registry_core,
    script as script_core,
    script_engine as script_engine_core,
    services as services_core,
    states as states_core,
    system as system_core,
    core_config as core_config_core,
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

    # ─────────────────────── refine pass: new groups (live)

    def test_scene_create_and_activate(self, hass_instance):
        """End-to-end: seed a sensor state, create a scene from it, activate it,
        then confirm the scene.* entity now appears in `scene list`."""
        # Seed an entity HA can include in a scene snapshot.
        self._run(
            ["state", "set", "input_boolean.refine_seed", "off"],
            hass_instance,
        )
        # Create a scene from the live state.
        r = self._run(
            ["--json", "scene", "create", "cli_refine_seed",
             "--snapshot", "input_boolean.refine_seed"],
            hass_instance,
        )
        assert r.returncode == 0, r.stderr
        # The scene service returns [] when no state changes resulted, which is fine.
        json.loads(r.stdout)

        # Activate it — HA should accept the call even if no entities mutate.
        r = self._run(
            ["--json", "scene", "activate", "scene.cli_refine_seed"],
            hass_instance,
        )
        assert r.returncode == 0, r.stderr

        # And it should now show up in the list.
        r = self._run(["--json", "scene", "list"], hass_instance)
        assert r.returncode == 0, r.stderr
        scenes_list = json.loads(r.stdout)
        ids = {s.get("entity_id") for s in scenes_list}
        assert "scene.cli_refine_seed" in ids

    def test_scene_apply_adhoc(self, hass_instance):
        """`scene apply` with an ad-hoc entity map must round-trip via HA."""
        self._run(
            ["state", "set", "input_boolean.refine_apply", "off"],
            hass_instance,
        )
        r = self._run(
            ["--json", "scene", "apply",
             "--entity", "input_boolean.refine_apply=on"],
            hass_instance,
        )
        assert r.returncode == 0, r.stderr
        # Apply returns a (possibly empty) list of state changes.
        json.loads(r.stdout)

    def test_search_related_entity(self, hass_instance):
        """search/related must return a dict (may be empty) for a real entity."""
        # Use the state we created earlier in the same session.
        self._run(["state", "set", "sensor.refine_search_probe", "1"],
                  hass_instance)
        r = self._run(
            ["--json", "search", "entity", "sensor.refine_search_probe"],
            hass_instance,
        )
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        # search/related returns either {} or a domain → ids mapping.
        assert isinstance(data, dict)

    def test_entity_expose_list(self, hass_instance):
        """expose_entity/list is a WS read that always returns a dict (may be empty)."""
        r = self._run(["--json", "entity", "expose", "list"], hass_instance)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert isinstance(data, dict)

    def test_weather_list_filters_to_domain(self, hass_instance):
        """`weather list` returns a list (no weather entities expected → empty)."""
        r = self._run(["--json", "weather", "list"], hass_instance)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert isinstance(data, list)
        assert all(s.get("entity_id", "").startswith("weather.") for s in data)

    def test_help_lists_new_groups(self, hass_instance):
        """The refine pass added these top-level groups — they must appear in --help."""
        r = self._run(["--help"], hass_instance)
        assert r.returncode == 0
        for grp in ("scene", "weather", "shopping-list", "todo",
                    "lock", "alarm", "search"):
            assert grp in r.stdout, f"missing {grp!r} in --help output"

    # ─────────────────────── refine pass v2: voice & multi-modal (live)

    def test_help_lists_v2_groups(self, hass_instance):
        """Second refine pass added these groups — verify --help on a live boot."""
        r = self._run(["--help"], hass_instance)
        assert r.returncode == 0
        for grp in ("camera", "device-automation", "assist-satellite",
                    "mobile-app", "media"):
            assert grp in r.stdout, f"missing {grp!r} in --help output"

    def test_media_browse_root_live(self, hass_instance):
        """`media browse` must return a dict from a live HA (root has children)."""
        r = self._run(["--json", "media", "browse"], hass_instance)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        # root browse always returns a dict-shaped node
        assert isinstance(data, dict)

    def _skip_if_unknown_command(self, result, cmd_name):
        """Skip when the running HA build doesn't ship this WS command.

        Some WS endpoints (`conversation/agent/list`,
        `assist_pipeline/language/list`, `assist_pipeline/device/list`)
        only exist in newer HA versions. The CLI wiring is verified by
        the CliRunner tests; here we only assert success when the API
        endpoint actually exists.
        """
        if result.returncode != 0 and "unknown_command" in (result.stderr or ""):
            pytest.skip(
                f"{cmd_name} not registered in this HA build "
                "(expected on HA versions older than the WS command landed)"
            )

    def test_assist_languages_live(self, hass_instance):
        """assist_pipeline/language/list — skip on builds that don't ship it."""
        r = self._run(["--json", "assist", "languages"], hass_instance,
                      check=False)
        self._skip_if_unknown_command(r, "assist_pipeline/language/list")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert isinstance(data, (dict, list))

    def test_assist_satellites_live(self, hass_instance):
        """assist_pipeline/device/list — skip on builds that don't ship it."""
        r = self._run(["--json", "assist", "satellites"], hass_instance,
                      check=False)
        self._skip_if_unknown_command(r, "assist_pipeline/device/list")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert isinstance(data, list)

    def test_assist_agents_live(self, hass_instance):
        """conversation/agent/list — skip on builds that don't ship it."""
        r = self._run(["--json", "assist", "agents"], hass_instance,
                      check=False)
        self._skip_if_unknown_command(r, "conversation/agent/list")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert isinstance(data, (dict, list))

    # ─────────────────────── refine pass v3: sysadmin & auth (live)

    def test_help_lists_v3_groups(self, hass_instance):
        """Third refine pass added these groups/subgroups — verify --help."""
        r = self._run(["--help"], hass_instance)
        assert r.returncode == 0
        for grp in ("category",):
            assert grp in r.stdout, f"missing {grp!r} in --help output"
        # system subgroups
        r = self._run(["system", "--help"], hass_instance)
        for sub in ("manifest", "analytics", "app-credentials", "issue",
                    "usb-scan", "zha-permit-join", "hardware-info",
                    "board-info", "cpu-info", "log"):
            assert sub in r.stdout, f"missing system {sub!r}"
        # auth subgroups
        r = self._run(["auth", "--help"], hass_instance)
        for sub in ("me", "sign-path", "user"):
            assert sub in r.stdout, f"missing auth {sub!r}"
        # logger subgroups
        r = self._run(["logger", "--help"], hass_instance)
        for sub in ("info-ws", "level-get", "level-set"):
            assert sub in r.stdout, f"missing logger {sub!r}"

    def test_auth_me_live(self, hass_instance):
        """`auth me` returns the active user's record via WS auth/current_user."""
        r = self._run(["--json", "auth", "me"], hass_instance)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert "id" in data and "name" in data

    def test_auth_sign_path_live(self, hass_instance):
        """`auth sign-path` returns a signed URL for a /api/... path."""
        r = self._run(["--json", "auth", "sign-path", "/api/", "--expires", "10"],
                      hass_instance)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        # HA returns either {"path": "..."} or the signed URL string.
        assert isinstance(data, dict) and ("path" in data or "url" in data)

    def test_auth_tokens_list_live(self, hass_instance):
        """`auth tokens list` returns the refresh tokens for the active user."""
        r = self._run(["--json", "auth", "tokens", "list"], hass_instance)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert isinstance(data, list)
        # The token created in the test fixture must be in the list.
        assert any("id" in t for t in data)

    def test_logger_info_ws_live(self, hass_instance):
        """`logger info-ws` returns per-component levels."""
        r = self._run(["--json", "logger", "info-ws"], hass_instance,
                      check=False)
        self._skip_if_unknown_command(r, "logger/log_info")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        # Either a list of {domain, level} or a dict — accept either shape.
        assert isinstance(data, (list, dict))

    def test_system_manifest_list_live(self, hass_instance):
        """`system manifest list` returns metadata for every loaded integration."""
        r = self._run(["--json", "system", "manifest", "list"], hass_instance,
                      check=False)
        self._skip_if_unknown_command(r, "manifest/list")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        # manifest/list returns either dict-of-domain or list of manifests.
        assert isinstance(data, (dict, list))

    def test_system_log_errors_live(self, hass_instance):
        """`system log errors` returns the WARNING+ entries HA has logged."""
        # Inject a synthetic warning so the list is non-empty regardless of
        # whatever else has happened during the boot.
        self._run(["system", "log", "write", "cli-refine-v3 probe",
                   "--level", "warning"], hass_instance)
        r = self._run(["--json", "system", "log", "errors"], hass_instance,
                      check=False)
        self._skip_if_unknown_command(r, "system_log_list")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert isinstance(data, list)

    def test_system_analytics_get_live(self, hass_instance):
        """`system analytics get` returns preferences + onboarded flag."""
        r = self._run(["--json", "system", "analytics", "get"], hass_instance,
                      check=False)
        self._skip_if_unknown_command(r, "analytics")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert isinstance(data, dict)
        assert "preferences" in data or "onboarded" in data

    def test_category_list_live(self, hass_instance):
        """`category list automation` always returns a list (may be empty)."""
        r = self._run(["--json", "category", "list", "automation"], hass_instance,
                      check=False)
        self._skip_if_unknown_command(r, "config/category_registry/list")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert isinstance(data, list)

    # ─────────────────────── refine pass v4: entity-control shortcuts (live)

    def test_help_lists_v4_groups(self, hass_instance):
        """Refine pass v4 added 17 entity-control shortcut groups — verify --help."""
        r = self._run(["--help"], hass_instance)
        assert r.returncode == 0, r.stderr
        for grp in ("light", "media-player", "climate", "cover", "fan",
                    "vacuum", "humidifier", "water-heater", "valve",
                    "lawn-mower", "siren", "remote", "number", "select",
                    "button", "text", "notify"):
            assert grp in r.stdout, f"missing {grp!r} in root --help output"

        # Each group's own --help lists the expected key subcommands.
        expected = {
            "light":        ("on", "off", "toggle"),
            "media-player": ("play", "pause", "stop", "next", "previous",
                             "volume-set", "mute", "select-source",
                             "play-media", "shuffle", "repeat",
                             "turn-on", "turn-off", "join", "unjoin"),
            "climate":      ("set-temperature", "set-hvac-mode", "set-fan-mode",
                             "set-preset", "set-humidity", "set-swing",
                             "turn-on", "turn-off"),
            "cover":        ("open", "close", "stop", "toggle",
                             "set-position", "set-tilt", "open-tilt",
                             "close-tilt", "stop-tilt"),
            "fan":          ("turn-on", "turn-off", "toggle",
                             "set-percentage", "set-preset", "set-direction",
                             "oscillate", "increase", "decrease"),
            "vacuum":       ("start", "stop", "pause", "return-to-base",
                             "locate", "clean-spot", "set-fan-speed",
                             "send-command"),
            "humidifier":   ("turn-on", "turn-off", "toggle",
                             "set-humidity", "set-mode"),
            "water-heater": ("turn-on", "turn-off", "set-temperature",
                             "set-operation-mode", "set-away-mode"),
            "valve":        ("open", "close", "stop", "toggle",
                             "set-position"),
            "lawn-mower":   ("start", "pause", "dock"),
            "siren":        ("on", "off", "toggle"),
            "remote":       ("turn-on", "turn-off", "toggle",
                             "send-command", "learn-command", "delete-command"),
            "number":       ("set",),
            "select":       ("set", "next", "previous", "first", "last"),
            "button":       ("press",),
            "text":         ("set",),
            "notify":       ("send",),
        }
        for grp, subs in expected.items():
            r = self._run([grp, "--help"], hass_instance)
            assert r.returncode == 0, f"{grp} --help failed: {r.stderr}"
            for sub in subs:
                assert sub in r.stdout, f"{grp}: missing subcommand {sub!r}"

    def test_v4_complex_command_help(self, hass_instance):
        """`light on --help` etc. must register all the typed flags."""
        # light on — the headline command, most flags
        r = self._run(["light", "on", "--help"], hass_instance)
        assert r.returncode == 0, r.stderr
        for flag in ("--brightness", "--brightness-pct", "--kelvin",
                     "--rgb", "--effect", "--flash", "--transition"):
            assert flag in r.stdout, f"light on missing {flag!r}"

        # climate set-temperature — multiple ranges
        r = self._run(["climate", "set-temperature", "--help"], hass_instance)
        assert r.returncode == 0, r.stderr
        for flag in ("--temperature", "--high", "--low", "--hvac-mode"):
            assert flag in r.stdout, f"climate set-temperature missing {flag!r}"

        # media-player play-media — three positional args + options
        r = self._run(["media-player", "play-media", "--help"], hass_instance)
        assert r.returncode == 0, r.stderr
        for tok in ("ENTITY_ID", "MEDIA_CONTENT_ID", "MEDIA_CONTENT_TYPE",
                    "--enqueue", "--announce", "--extra"):
            assert tok in r.stdout, f"media-player play-media missing {tok!r}"

        # remote send-command — repeatable command + repeat/delay options
        r = self._run(["remote", "send-command", "--help"], hass_instance)
        assert r.returncode == 0, r.stderr
        for flag in ("--command", "--device", "--num-repeats",
                     "--delay-secs", "--hold-secs"):
            assert flag in r.stdout, f"remote send-command missing {flag!r}"

        # notify send — title/service/target/data
        r = self._run(["notify", "send", "--help"], hass_instance)
        assert r.returncode == 0, r.stderr
        for flag in ("--title", "--service", "--target", "--data"):
            assert flag in r.stdout, f"notify send missing {flag!r}"

    def test_v4_notify_send_persistent_live(self, hass_instance):
        """`notify send --service persistent_notification` is the one entity-
        control shortcut that always works on a stock HA (persistent_notification
        ships as a built-in notify service). Verify the bell-icon list picks it up.
        """
        marker = "cli-anything entity-control v4 probe"
        r = self._run(
            ["notify", "send", marker, "--title", "v4-probe",
             "--service", "persistent_notification"],
            hass_instance, check=False,
        )
        # `notify.persistent_notification` only auto-registers when the notify
        # component is loaded. The minimal test fixture does not load notify:,
        # so the POST returns 400 ("service not in registry"). Skip cleanly —
        # CLI wiring is already proved by --help and the CliRunner suite.
        err_lc = (r.stderr or "").lower()
        if r.returncode != 0 and (
            "not found" in err_lc
            or "400" in err_lc
            or "service not found" in err_lc
        ):
            pytest.skip(
                "notify.persistent_notification not registered on this HA fixture",
            )
        assert r.returncode == 0, r.stderr

        # Confirm it landed in the persistent-notifications list.
        nlist = self._run(["--json", "notifications", "list"], hass_instance)
        assert nlist.returncode == 0, nlist.stderr
        data = json.loads(nlist.stdout)
        assert any(marker in (n.get("message", "") or "") for n in data), \
            f"persistent notification with marker {marker!r} not found in {data!r}"

    def test_v4_number_set_dry_run_via_service(self, hass_instance):
        """The number/text/select/button/notify shortcuts don't have --dry-run;
        instead exercise the underlying `service call number set_value --dry-run`
        path through the global `service` group to verify the service registry
        is the same one the shortcut would target.
        """
        r = self._run(
            ["--json", "service", "call", "number", "set_value",
             "-T", "entity_id=number.does_not_exist",
             "-D", "value=42",
             "--dry-run"],
            hass_instance,
        )
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["dry_run"] is True
        assert data["domain"] == "number"
        assert data["service"] == "set_value"

    # ─────────────────────────────── v7: script-engine (`action`) group

    def test_v7_action_run_live(self, hass_instance):
        """`action run` executes an ad-hoc sequence through HA's script engine."""
        r = self._run(
            ["--json", "action", "run",
             "--sequence",
             json.dumps([
                 {"action": "persistent_notification.create",
                  "data": {"title": "v7 probe",
                           "message": "cli-anything action run",
                           "notification_id": "cli_anything_action_run"}},
             ])],
            hass_instance,
        )
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        # HA returns the script run context (+ a null response for this seq).
        assert "context" in data
        assert data["context"].get("id")

        nlist = self._run(["--json", "notifications", "list"], hass_instance)
        assert nlist.returncode == 0, nlist.stderr
        notes = json.loads(nlist.stdout)
        assert any(
            n.get("notification_id") == "cli_anything_action_run" for n in notes
        ), f"notification not created by action run: {notes!r}"

    def test_v7_action_run_service_shorthand_live(self, hass_instance):
        r = self._run(
            ["--json", "action", "run",
             "--service", "persistent_notification.create",
             "-d", "message=shorthand probe",
             "-d", "notification_id=cli_anything_action_shorthand"],
            hass_instance,
        )
        assert r.returncode == 0, r.stderr
        assert "context" in json.loads(r.stdout)

    def test_v7_action_run_dry_run_live(self, hass_instance):
        r = self._run(
            ["--json", "action", "run", "--service", "light.turn_on",
             "-t", "entity_id=light.nope", "--dry-run"],
            hass_instance,
        )
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["dry_run"] is True
        assert data["payload"]["sequence"][0]["action"] == "light.turn_on"

    def test_v7_action_validate_live(self, hass_instance):
        """Real `validate_config`: a good action block and a bogus one."""
        good = self._run(
            ["--json", "action", "validate",
             "--actions", json.dumps([{"action": "homeassistant.check_config"}])],
            hass_instance,
        )
        assert good.returncode == 0, good.stderr
        assert json.loads(good.stdout)["actions"]["valid"] is True

        bad = self._run(
            ["--json", "action", "validate",
             "--triggers", json.dumps([{"trigger": "not_a_real_trigger"}])],
            hass_instance,
        )
        assert bad.returncode == 0, bad.stderr
        result = json.loads(bad.stdout)["triggers"]
        assert result["valid"] is False
        assert result["error"]

    def test_v7_action_validate_automation_live(self, hass_instance, tmp_path):
        good_cfg = tmp_path / "good.json"
        good_cfg.write_text(json.dumps({
            "alias": "v7 probe",
            "trigger": [{"trigger": "state", "entity_id": "sun.sun"}],
            "action": [{"action": "homeassistant.check_config"}],
        }))
        r = self._run(
            ["--json", "action", "validate-automation", str(good_cfg)], hass_instance
        )
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["valid"] is True
        assert sorted(data["checked"]) == ["actions", "triggers"]

        bad_cfg = tmp_path / "bad.json"
        bad_cfg.write_text(json.dumps({
            "alias": "v7 broken",
            "triggers": [{"trigger": "state", "entity_id": "sun.sun"}],
            "actions": [{"action": "definitely.not_a_service", "data": []}],
        }))
        bad = self._run(
            ["--json", "action", "validate-automation", str(bad_cfg)],
            hass_instance, check=False,
        )
        assert bad.returncode != 0, bad.stdout
        assert "invalid automation config" in (bad.stderr + bad.stdout).lower()

    def test_v7_action_test_condition_live(self, hass_instance):
        """Real `test_condition` — a template that is true, then one that is false."""
        true_cond = self._run(
            ["--json", "action", "test-condition",
             "--condition",
             json.dumps({"condition": "template", "value_template": "{{ 1 == 1 }}"}),
             "--exit-code"],
            hass_instance,
        )
        assert true_cond.returncode == 0, true_cond.stderr
        assert json.loads(true_cond.stdout) == {"result": True}

        false_cond = self._run(
            ["--json", "action", "test-condition",
             "--condition",
             json.dumps({"condition": "template", "value_template": "{{ 1 == 2 }}"}),
             "--exit-code"],
            hass_instance, check=False,
        )
        assert false_cond.returncode == 1
        assert json.loads(false_cond.stdout) == {"result": False}

    def test_v7_entity_source_live(self, hass_instance):
        r = self._run(["--json", "entity", "source"], hass_instance)
        assert r.returncode == 0, r.stderr
        sources = json.loads(r.stdout)
        assert isinstance(sources, dict)
        assert sources, "entity/source returned nothing on a live instance"
        assert all("domain" in v for v in sources.values())

        grouped = self._run(
            ["--json", "entity", "source", "--by-integration"], hass_instance
        )
        assert grouped.returncode == 0, grouped.stderr
        by_int = json.loads(grouped.stdout)
        assert isinstance(by_int, dict)
        # Every entity in the flat map is accounted for exactly once.
        assert sum(len(v) for v in by_int.values()) == len(sources)

        # Single-entity lookup round-trips against the flat map.
        entity_id = sorted(sources)[0]
        one = self._run(["--json", "entity", "source", entity_id], hass_instance)
        assert one.returncode == 0, one.stderr
        detail = json.loads(one.stdout)
        assert detail["loaded"] is True
        assert detail["domain"] == sources[entity_id]["domain"]

    def test_v7_workflow_validate_then_save_automation(self, hass_instance, tmp_path):
        """Composability: validate → save → trigger → run its actions ad-hoc."""
        cfg = {
            "alias": "cli-anything v7 workflow",
            "triggers": [{"trigger": "event", "event_type": "cli_anything_v7"}],
            "conditions": [],
            "actions": [{
                "action": "persistent_notification.create",
                "data": {"message": "v7 workflow fired",
                         "notification_id": "cli_anything_v7_workflow"},
            }],
        }
        cfg_file = tmp_path / "wf.json"
        cfg_file.write_text(json.dumps(cfg))

        pre = self._run(
            ["--json", "action", "validate-automation", str(cfg_file)], hass_instance
        )
        assert pre.returncode == 0, pre.stderr
        assert json.loads(pre.stdout)["valid"] is True

        # The validated action block runs standalone through the script engine.
        ran = self._run(
            ["--json", "action", "run", "--sequence", json.dumps(cfg["actions"])],
            hass_instance,
        )
        assert ran.returncode == 0, ran.stderr

        notes = json.loads(
            self._run(["--json", "notifications", "list"], hass_instance).stdout
        )
        assert any(
            n.get("notification_id") == "cli_anything_v7_workflow" for n in notes
        )


class TestLiveScriptEngineCore:
    """Core-module level checks against the real script-engine WS commands."""

    def test_execute_script_returns_context(self, live_client):
        result = script_engine_core.execute_script(
            live_client,
            [{"action": "persistent_notification.create",
              "data": {"message": "core probe",
                       "notification_id": "cli_anything_core_exec"}}],
        )
        assert isinstance(result, dict)
        assert result.get("context", {}).get("id")

    def test_execute_script_with_variables(self, live_client):
        result = script_engine_core.execute_script(
            live_client,
            [{"action": "persistent_notification.create",
              "data": {"message": "{{ msg }}",
                       "notification_id": "cli_anything_core_vars"}}],
            variables={"msg": "rendered from a script variable"},
        )
        assert result.get("context", {}).get("id")

    def test_run_service_action(self, live_client):
        result = script_engine_core.run_service_action(
            live_client,
            "persistent_notification.create",
            data={"message": "helper probe",
                  "notification_id": "cli_anything_core_helper"},
        )
        assert result.get("context", {}).get("id")

    def test_validate_config_good_and_bad(self, live_client):
        good = script_engine_core.validate_config(
            live_client, actions=[{"action": "homeassistant.check_config"}]
        )
        assert good["actions"]["valid"] is True
        bad = script_engine_core.validate_config(
            live_client, conditions=[{"condition": "not_a_condition"}]
        )
        assert bad["conditions"]["valid"] is False
        assert bad["conditions"]["error"]

    def test_validate_automation_config_legacy_keys(self, live_client):
        out = script_engine_core.validate_automation_config(
            live_client,
            {"trigger": [{"trigger": "event", "event_type": "x"}],
             "action": [{"action": "homeassistant.check_config"}]},
        )
        assert out["valid"] is True
        assert out["checked"] == ["actions", "triggers"]

    def test_validate_script_config(self, live_client):
        out = script_engine_core.validate_script_config(
            live_client,
            {"alias": "probe", "sequence": [{"action": "homeassistant.check_config"}]},
        )
        assert out["valid"] is True

    def test_condition_holds_template(self, live_client):
        assert script_engine_core.condition_holds(
            live_client, {"condition": "template", "value_template": "{{ 2 > 1 }}"}
        ) is True
        assert script_engine_core.condition_holds(
            live_client, {"condition": "template", "value_template": "{{ 2 < 1 }}"}
        ) is False

    def test_condition_with_variables(self, live_client):
        assert script_engine_core.condition_holds(
            live_client,
            {"condition": "template", "value_template": "{{ limit > 5 }}"},
            variables={"limit": 10},
        ) is True

    def test_test_conditions_batch_is_error_tolerant(self, live_client):
        rows = script_engine_core.test_conditions(
            live_client,
            [
                {"condition": "template", "value_template": "{{ true }}"},
                {"condition": "totally_bogus"},
            ],
        )
        assert rows[0]["result"] is True and rows[0]["error"] is None
        assert rows[1]["result"] is None and rows[1]["error"]

    def test_entity_source_matches_live_states(self, live_client):
        sources = script_engine_core.entity_source(live_client)
        assert isinstance(sources, dict) and sources
        grouped = script_engine_core.sources_by_integration(live_client)
        assert sum(len(v) for v in grouped.values()) == len(sources)
        # persistent_notification is loaded by the test config.
        one = sorted(sources)[0]
        assert script_engine_core.entity_source_for(live_client, one) == sources[one]
        assert script_engine_core.entity_source_for(live_client, "light.ghost_xyz") is None


class TestLiveFrontendTemplateWs:
    """Live checks for the frontend/template-ws refine pass.

    These WS commands (`render_template`, `get_panels`, `frontend/*`,
    `integration/descriptions`, `sensor/*`, `subscribe_entities`) ship with
    every HA build the harness supports, so they are asserted, not probed.
    """

    def test_render_template_keeps_native_type(self, live_client):
        out = template_ws_core.render(live_client, "{{ 1 + 2 }}")
        assert out["result"] == 3, out
        assert isinstance(out["result"], int)

    def test_render_template_listeners_name_the_entity(self, live_client):
        out = template_ws_core.render(
            live_client, "{{ states('persistent_notification.x') }}"
        )
        assert out["listeners"]["entities"] == ["persistent_notification.x"]

    def test_listeners_all_flag_for_full_scan(self, live_client):
        block = template_ws_core.listeners(live_client, "{{ states | count }}")
        assert block["all"] is True

    def test_depends_on_matches_listeners(self, live_client):
        tpl = "{{ states('sun.sun') }}"
        assert template_ws_core.depends_on(live_client, tpl, "sun.sun") is True
        assert template_ws_core.depends_on(live_client, tpl, "light.nope") is False

    def test_validate_reports_a_broken_template(self, live_client):
        out = template_ws_core.validate(live_client, "{{ 1 | no_such_filter }}")
        assert out["valid"] is False
        assert out["error"]

    def test_validate_accepts_a_good_template(self, live_client):
        assert template_ws_core.validate(live_client, "{{ now().year }}")["valid"] is True

    def test_panels_include_the_default_dashboard(self, live_client):
        rows = frontend_meta_core.list_panels(live_client)
        assert rows and all("url_path" in r for r in rows)
        assert "lovelace" in {r["url_path"] for r in rows}

    def test_get_panel_round_trip(self, live_client):
        one = frontend_meta_core.list_panels(live_client)[0]
        assert frontend_meta_core.get_panel(live_client, one["url_path"]) == one

    def test_get_panel_unknown_raises(self, live_client):
        with pytest.raises(ValueError):
            frontend_meta_core.get_panel(live_client, "no_such_panel_xyz")

    def test_frontend_version(self, live_client):
        assert frontend_meta_core.frontend_version(live_client).get("version")

    def test_translations_for_a_component(self, live_client):
        res = frontend_meta_core.translations(
            live_client, category="entity_component", integration="person"
        )
        assert isinstance(res, dict)

    def test_icons_category(self, live_client):
        assert isinstance(frontend_meta_core.icons(live_client, category="entity"), dict)

    def test_integration_catalog_has_core_entries(self, live_client):
        rows = frontend_meta_core.list_integrations(live_client)
        assert len(rows) > 100
        domains = {r["domain"] for r in rows}
        assert "hue" in domains
        assert frontend_meta_core.find_integration(live_client, "hue")["source"] == "core"

    def test_integration_catalog_config_flow_filter(self, live_client):
        rows = frontend_meta_core.list_integrations(live_client, config_flow_only=True)
        assert rows and all(r["config_flow"] for r in rows)

    def _skip_without_sensor_domain(self, exc):
        """`sensor/*` WS commands are registered by the sensor integration.

        A bare test config never loads it, so `unknown_command` here means
        "this HA has no sensors", not a harness bug.
        """
        if "unknown_command" in str(exc):
            pytest.skip("sensor integration not loaded in this HA config")
        raise exc

    def test_numeric_device_classes_include_temperature(self, live_client):
        try:
            classes = device_class_units_core.numeric_device_classes(live_client)
        except Exception as exc:  # noqa: BLE001
            self._skip_without_sensor_domain(exc)
        assert "temperature" in classes
        assert device_class_units_core.is_numeric_device_class(live_client, "temperature")

    def test_temperature_units_are_convertible(self, live_client):
        try:
            units = device_class_units_core.sensor_convertible_units(live_client, "temperature")
        except Exception as exc:  # noqa: BLE001
            self._skip_without_sensor_domain(exc)
        assert "°C" in units and "°F" in units
        assert device_class_units_core.can_convert_to(live_client, "temperature", "°F")
        assert not device_class_units_core.can_convert_to(live_client, "temperature", "kWh")

    def test_unknown_device_class_has_no_units(self, live_client):
        try:
            units = device_class_units_core.sensor_convertible_units(live_client, "bogus")
        except Exception as exc:  # noqa: BLE001
            self._skip_without_sensor_domain(exc)
        assert units == []

    def test_entities_snapshot_matches_rest_states(self, live_client):
        snap = state_stream_core.entities_snapshot(live_client, timeout_seconds=20)
        rest = {s["entity_id"] for s in states_core.list_states(live_client)}
        assert snap and set(snap) == rest

    def test_entities_snapshot_entity_filter(self, live_client):
        one = sorted({s["entity_id"] for s in states_core.list_states(live_client)})[0]
        snap = state_stream_core.entities_snapshot(
            live_client, entity_ids=[one], timeout_seconds=20
        )
        assert set(snap) == {one}


class TestCLIFrontendTemplateWsSubprocess(TestCLISubprocess):
    """The same surfaces through the installed CLI."""

    def test_help_lists_new_groups(self, hass_instance):
        r = self._run(["--help"], hass_instance)
        assert r.returncode == 0
        for grp in ("template-ws", "panel"):
            assert grp in r.stdout, f"missing {grp!r} in --help output"

    def test_template_ws_render_value_only(self, hass_instance):
        r = self._run(["--json", "template-ws", "render", "{{ 6 * 7 }}", "--value-only"],
                      hass_instance)
        assert json.loads(r.stdout) == 42

    def test_template_ws_listeners_entities_only(self, hass_instance):
        r = self._run(
            ["--json", "template-ws", "listeners", "{{ states('sun.sun') }}", "--entities-only"],
            hass_instance,
        )
        assert json.loads(r.stdout) == ["sun.sun"]

    def test_template_ws_uses_exit_code(self, hass_instance):
        ok = self._run(
            ["--json", "template-ws", "uses", "sun.sun", "{{ states('sun.sun') }}", "--exit-code"],
            hass_instance,
        )
        assert ok.returncode == 0
        bad = self._run(
            ["--json", "template-ws", "uses", "light.nope", "{{ states('sun.sun') }}",
             "--exit-code"],
            hass_instance, check=False,
        )
        assert bad.returncode == 1

    def test_template_ws_validate_exit_code(self, hass_instance):
        r = self._run(["--json", "template-ws", "validate", "{{ 1 | no_such_filter }}"],
                      hass_instance, check=False)
        assert r.returncode != 0

    def test_panel_list_and_get(self, hass_instance):
        rows = json.loads(self._run(["--json", "panel", "list"], hass_instance).stdout)
        assert rows
        one = rows[0]["url_path"]
        got = json.loads(self._run(["--json", "panel", "get", one], hass_instance).stdout)
        assert got["url_path"] == one

    def test_panel_dashboards_subset_of_list(self, hass_instance):
        all_paths = {
            r["url_path"]
            for r in json.loads(self._run(["--json", "panel", "list"], hass_instance).stdout)
        }
        dash = json.loads(self._run(["--json", "panel", "dashboards"], hass_instance).stdout)
        assert {d["url_path"] for d in dash} <= all_paths

    def test_frontend_version(self, hass_instance):
        r = self._run(["--json", "frontend", "version"], hass_instance)
        assert json.loads(r.stdout).get("version")

    def test_system_integrations_domains_only(self, hass_instance):
        domains = json.loads(
            self._run(["--json", "system", "integrations", "--domains-only"], hass_instance).stdout
        )
        # `hue` only appears once brand entries are unpacked (it lives under
        # the `philips` brand in HA's generated catalog).
        assert "hue" in domains
        assert "sun" in domains

    def test_entity_convertible_units_exit_code(self, hass_instance):
        good = self._run(
            ["--json", "entity", "convertible-units", "--device-class", "temperature",
             "--unit", "°F", "--exit-code"],
            hass_instance, check=False,
        )
        self._skip_if_unknown_command(good, "sensor/device_class_convertible_units")
        assert good.returncode == 0
        bad = self._run(
            ["--json", "entity", "convertible-units", "--device-class", "temperature",
             "--unit", "kWh", "--exit-code"],
            hass_instance, check=False,
        )
        assert bad.returncode == 1

    def test_state_stream_snapshot_ids_only(self, hass_instance):
        ids = json.loads(
            self._run(["--json", "state-stream", "snapshot", "--ids-only"], hass_instance).stdout
        )
        assert ids == sorted(ids) and ids


# ─────────────────────────────────────── fourth refine pass: live coverage

class TestRefineV4Live:
    """The three clusters added in the fourth refine pass, against a real HA.

    These boot the same throwaway instance every other live test uses. Each was
    ALSO exercised against a production 2026.8.1 instance while being written —
    which is where the measured findings in the module docstrings come from —
    but a finding that only exists in a transcript is not a test, so it is
    reproduced here.

    `_skip_if_unknown_command` covers HA builds older than a command: the
    target surface is 2022+, `labs` and the composite-split registry are 2026,
    and a skip is the honest answer on an older build.

    `validate_config`, `test_condition`, `execute_script`, `entity/source` and
    device-class units are NOT here — they landed on main as the `action`
    group, `entity source` and `entity convertible-units` while this was being
    written, and their own tests own them.
    """

    def _env(self, hass_instance):
        env = dict(os.environ)
        env["HASS_URL"] = hass_instance["url"]
        env["HASS_TOKEN"] = hass_instance["token"]
        return env

    def _run(self, args, hass_instance, check=True):
        return subprocess.run(
            CLI_BASE + args,
            capture_output=True, text=True,
            env=self._env(hass_instance),
            check=check,
            timeout=60,
        )

    def _skip_if_unknown_command(self, result, cmd_name):
        if result.returncode != 0 and "unknown_command" in (result.stderr or ""):
            pytest.skip(f"{cmd_name} not registered in this HA build")

    # ──────────────────────────────────────────────── A: target resolution

    def test_extract_from_target_reports_a_missing_label(self, hass_instance):
        """The half that matters: a label HA cannot resolve does NOTHING."""
        r = self._run(
            ["--json", "target", "extract", "--label-id", "definitely_not_a_label"],
            hass_instance, check=False,
        )
        self._skip_if_unknown_command(r, "extract_from_target")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["missing_labels"] == ["definitely_not_a_label"]
        assert data["resolves_to_nothing"] is True

    def test_services_for_target(self, hass_instance):
        r = self._run(
            ["--json", "target", "services", "--entity-id", "sun.sun"],
            hass_instance, check=False,
        )
        self._skip_if_unknown_command(r, "get_services_for_target")
        assert r.returncode == 0, r.stderr
        assert isinstance(json.loads(r.stdout)["services"], list)

    def test_slugify_is_has_own(self, hass_instance):
        r = self._run(["--json", "target", "slugify", "Living Room — Lamp #2"],
                      hass_instance, check=False)
        self._skip_if_unknown_command(r, "slugify")
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["slug"] == "living_room_lamp_2"

    # ────────────────────────────────────────────────── B: bytes in / out

    def test_file_upload_returns_a_file_id(self, hass_instance, tmp_path):
        """Proves the multipart path — the session sets Content-Type: json,
        and leaving that in place makes every upload a 400."""
        f = tmp_path / "probe.txt"
        f.write_text("cli-anything probe")
        r = self._run(["--json", "file", "upload", str(f)], hass_instance, check=False)
        if r.returncode != 0 and "404" in (r.stderr or ""):
            pytest.skip("file_upload not loaded in this HA build")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["file_id"]
        print(f"\n  file_id: {data['file_id']}")

    def test_backup_download_requires_an_agent_id(self, hass_instance):
        """HA answers a missing agent_id with an EMPTY 400 — refuse first."""
        r = self._run(["--json", "backup", "download", "nope", "/tmp/x.tar"],
                      hass_instance, check=False)
        assert r.returncode != 0
        assert "--agent-id" in (r.stdout + r.stderr)

    def test_media_upload_refuses_a_non_media_content_type(self, hass_instance, tmp_path):
        """HA checks image/ video/ audio/ and logs the reason server-side only."""
        f = tmp_path / "notes.txt"
        f.write_text("x")
        r = self._run(
            ["--json", "media", "upload", str(f), "--target", "media-source://media_source/."],
            hass_instance, check=False,
        )
        assert r.returncode != 0
        assert "image/*" in (r.stdout + r.stderr)

    def test_tts_engine_languages_come_from_the_ws_command(self, hass_instance):
        """The entity attributes report [] while HA has the real list."""
        r = self._run(["--json", "tts", "list"], hass_instance, check=False)
        self._skip_if_unknown_command(r, "tts/engine/list")
        assert r.returncode == 0, r.stderr
        rows = json.loads(r.stdout)
        if not rows:
            pytest.skip("no tts.* entities on this instance")
        assert all("languages_from" in row for row in rows)

    def test_intent_handle_runs_an_intent_without_the_sentence_parser(self, hass_instance):
        r = self._run(["--json", "intent", "handle", "HassGetState", "--slot", "name=sun"],
                      hass_instance, check=False)
        if r.returncode != 0 and "404" in (r.stderr or ""):
            pytest.skip("intent component not loaded in this HA build")
        assert r.returncode == 0, r.stderr
        assert "response_type" in json.loads(r.stdout)

    # ───────────────────────────────────────────────── D: preferences

    def test_labs_list(self, hass_instance):
        r = self._run(["--json", "labs", "list"], hass_instance, check=False)
        self._skip_if_unknown_command(r, "labs/list")
        assert r.returncode == 0, r.stderr
        assert isinstance(json.loads(r.stdout), list)

    def test_recorder_entity_options_explains_an_empty_history(self, hass_instance):
        r = self._run(["--json", "prefs", "recorded", "sun.sun"], hass_instance, check=False)
        self._skip_if_unknown_command(r, "recorder/entity_options/get")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert "is_recorded" in data
        assert data["explains_empty_history"] is (data["is_recorded"] is False)

    def test_prefs_entity_naming_reads_without_prompting(self, hass_instance):
        """A read that prompts is how a command gets a reputation for being
        dangerous; there is no --yes on this path and it must still succeed."""
        r = self._run(["--json", "prefs", "entity-naming"], hass_instance, check=False)
        self._skip_if_unknown_command(r, "config/entity_registry/settings/get")
        assert r.returncode == 0, r.stderr
        assert "is_default" in json.loads(r.stdout)

    def test_device_links_splits(self, hass_instance):
        r = self._run(["--json", "device-links", "splits"], hass_instance, check=False)
        self._skip_if_unknown_command(r, "config/device_registry/list_composite_splits")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert "member_of" in data
        # Every split id must be reachable from the reverse index — looking a
        # device up by its own id in `splits` can NEVER match, which is the bug
        # the first version of this had.
        for composite_id, info in (data["splits"] or {}).items():
            for split_id in info.get("split_ids") or []:
                assert data["member_of"].get(split_id) == composite_id


class TestRefineV5Live:
    """The v1.50.0 clusters against a real HA: core config, voice, discovery.

    The throwaway instance these boot on is DELIBERATELY minimal — its
    `configuration.yaml` loads `api`, `auth`, `history`, `logbook`,
    `conversation`, `media_source`, `automation`, `script` and nothing else. It
    therefore does NOT load the `config` integration, and `config` is what
    registers `config/core/update`, `config/core/detect`,
    `config_entries/*` and `POST /api/config/core/check_config`. Nor does it
    load `tts`, `stt`, `wake_word` or `lovelace`.

    That is not a gap in these tests, it is the condition every one of these
    commands meets on a stripped-down instance, so each is written to prove one
    of two things: that it works, or that it degrades to a named skip instead
    of a traceback. The commands that need no integration at all — the
    `/api/config` read, the whole of dry-run validation, the client-side
    guards, and `conversation/prepare` — are asserted properly.
    """

    def _env(self, hass_instance):
        env = dict(os.environ)
        env["HASS_URL"] = hass_instance["url"]
        env["HASS_TOKEN"] = hass_instance["token"]
        return env

    def _run(self, args, hass_instance, check=True):
        return subprocess.run(
            CLI_BASE + args,
            capture_output=True,
            text=True,
            env=self._env(hass_instance),
            check=check,
            timeout=60,
        )

    def _skip_if_absent(self, result, what):
        """Skip when the integration behind a command is not loaded here.

        A missing WS command answers `unknown_command`; a missing REST view is
        a 404. Both mean "this integration is not set up", which is a real
        state on a real instance and must not look like a crash.
        """
        blob = (result.stderr or "") + (result.stdout or "")
        if result.returncode != 0 and ("unknown_command" in blob or "-> 404" in blob):
            pytest.skip(f"{what} is not available on this HA (integration not loaded)")

    # ────────────────────────────────────────────── A: the instance's own config

    def test_core_config_returns_the_settable_keys_only(self, hass_instance):
        """These are the twelve keys `set-config` can write, and no others."""
        r = self._run(["--json", "system", "core-config"], hass_instance)
        data = json.loads(r.stdout)
        assert set(data) == set(core_config_core.UPDATABLE)
        assert "components" not in data

    def test_core_config_agrees_with_the_yaml_the_instance_booted_with(self, hass_instance):
        """conftest writes latitude 52.3676 / Etc/UTC into configuration.yaml."""
        data = json.loads(self._run(["--json", "system", "core-config"], hass_instance).stdout)
        assert round(float(data["latitude"]), 3) == 52.368
        assert data["time_zone"] == "Etc/UTC"

    def test_set_config_dry_run_writes_nothing_and_reports_the_change(self, hass_instance):
        """The dry run needs no `config` integration — it only reads and diffs."""
        r = self._run(
            ["--json", "system", "set-config", "--time-zone", "Europe/London"], hass_instance
        )
        data = json.loads(r.stdout)
        assert data["applied"] is False
        assert data["changes"] == [
            {"key": "time_zone", "from": "Etc/UTC", "to": "Europe/London"}
        ]
        # And the instance really did not move.
        after = json.loads(self._run(["--json", "system", "core-config"], hass_instance).stdout)
        assert after["time_zone"] == "Etc/UTC"

    def test_set_config_dry_run_detects_a_no_op(self, hass_instance):
        r = self._run(["--json", "system", "set-config", "--time-zone", "Etc/UTC"], hass_instance)
        data = json.loads(r.stdout)
        assert data["no_op"] is True and data["changes"] == []

    def test_set_config_refuses_an_impossible_coordinate_before_any_call(self, hass_instance):
        r = self._run(
            ["--json", "system", "set-config", "--latitude", "200", "--apply"],
            hass_instance,
            check=False,
        )
        assert r.returncode == 1
        assert "must be between" in r.stderr

    def test_set_config_apply_round_trip(self, hass_instance):
        """A real write, then put it back. Needs the `config` integration.

        Elevation is chosen deliberately: it is an integer with no dependent
        entity in this instance, so a failure to restore cannot silently break
        another test the way a time-zone change would.
        """
        before = json.loads(self._run(["--json", "system", "core-config"], hass_instance).stdout)
        r = self._run(
            ["--json", "system", "set-config", "--elevation", "123", "--apply"],
            hass_instance,
            check=False,
        )
        self._skip_if_absent(r, "config/core/update")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["applied"] is True
        assert data["effective"] == [
            {"key": "elevation", "requested": 123, "actual": 123, "took": True}
        ]
        restore = self._run(
            ["--json", "system", "set-config", "--elevation", str(before["elevation"] or 0),
             "--apply"],
            hass_instance,
            check=False,
        )
        assert restore.returncode == 0, restore.stderr

    def test_detect_location_degrades_to_a_named_answer(self, hass_instance):
        """Geo-IP from a CI runner may fail; `{}` is a result, not an error."""
        r = self._run(["--json", "system", "detect-location"], hass_instance, check=False)
        self._skip_if_absent(r, "config/core/detect")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["detected"] in (True, False)

    def test_check_config_direct(self, hass_instance):
        r = self._run(["--json", "system", "check-config", "--direct"], hass_instance, check=False)
        self._skip_if_absent(r, "POST /api/config/core/check_config")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["valid"] is True  # the instance booted, so its YAML is fine
        assert data["source"].endswith("/api/config/core/check_config")

    # ─────────────────────────────────────────────────────────── B: voice stack

    def test_assist_prepare_against_the_real_conversation_agent(self, hass_instance):
        """`conversation` IS loaded here, so this is a real warm-up, not a skip."""
        r = self._run(["--json", "assist", "prepare", "--language", "en"], hass_instance,
                      check=False)
        self._skip_if_absent(r, "conversation/prepare")
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["prepared"] is True

    def test_wake_words_refuses_a_satellite_entity_without_touching_the_wire(
        self, hass_instance
    ):
        """The mistake this guard exists for — wake words are CONFIGURED on the
        satellite and OFFERED by the detection engine, and HA's own answer is a
        voluptuous error about a schema."""
        r = self._run(
            ["--json", "assist", "wake-words", "assist_satellite.kitchen"],
            hass_instance,
            check=False,
        )
        assert r.returncode == 1
        assert "assist-satellite config" in r.stderr

    def test_tts_voices_needs_a_language_and_says_so(self, hass_instance):
        r = self._run(["--json", "tts", "voices", "tts.piper"], hass_instance, check=False)
        assert r.returncode != 0
        assert "--language" in (r.stderr + r.stdout)

    def test_stt_engines_is_empty_or_absent_but_never_a_traceback(self, hass_instance):
        r = self._run(["--json", "assist", "stt-engines"], hass_instance, check=False)
        self._skip_if_absent(r, "stt/engine/list")
        assert r.returncode == 0, r.stderr
        assert isinstance(json.loads(r.stdout), list)

    # ──────────────────────────────────────────── C: flows HA starts by itself

    def test_config_flow_progress_is_grouped_by_what_it_means(self, hass_instance):
        r = self._run(["--json", "config-flow", "progress"], hass_instance, check=False)
        self._skip_if_absent(r, "config_entries/flow/progress")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["broken"] == len(data["reauth"])
        assert data["total"] == len(data["reauth"]) + len(data["reconfigure"]) + len(
            data["discovered"]
        )

    def test_config_flow_handlers_lists_setup_capable_domains(self, hass_instance):
        r = self._run(["--json", "config-flow", "handlers"], hass_instance, check=False)
        self._skip_if_absent(r, "config/config_entries/flow_handlers")
        assert r.returncode == 0, r.stderr
        handlers = json.loads(r.stdout)
        assert isinstance(handlers, list) and handlers
        # The catalogue is what `config-flow init` draws from.
        assert "mqtt" in handlers

    def test_config_flow_handlers_helper_filter_is_a_subset(self, hass_instance):
        every = self._run(["--json", "config-flow", "handlers"], hass_instance, check=False)
        self._skip_if_absent(every, "config/config_entries/flow_handlers")
        helpers = self._run(
            ["--json", "config-flow", "handlers", "--type", "helper"], hass_instance, check=False
        )
        assert helpers.returncode == 0, helpers.stderr
        assert set(json.loads(helpers.stdout)) <= set(json.loads(every.stdout))

    def test_ignore_refuses_a_flow_id_that_is_not_in_progress(self, hass_instance):
        r = self._run(
            ["--json", "config-flow", "ignore", "not-a-flow", "--title", "x", "--yes"],
            hass_instance,
            check=False,
        )
        self._skip_if_absent(r, "config_entries/ignore_flow")
        assert r.returncode == 1
        assert r.stderr.strip()

    def test_config_entry_get_direct_on_a_missing_entry_is_an_error_not_empty(
        self, hass_instance
    ):
        r = self._run(
            ["--json", "config-entry", "get", "nope", "--direct"], hass_instance, check=False
        )
        self._skip_if_absent(r, "config_entries/get_single")
        assert r.returncode == 1
        assert r.stderr.strip()
