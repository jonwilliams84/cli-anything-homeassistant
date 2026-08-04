"""Tests for the ``str:`` prefix that forces a -D / --data value to stay a string.

Regression coverage for the mqtt.publish payload bug where a valid-JSON payload
was silently coerced to a dict by ``parse_kv_pairs`` / the WebSocket ``--data``
path, causing HA to publish something no subscriber could parse.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod
from cli_anything.homeassistant.homeassistant_cli import parse_kv_pairs


# ────────────────────────────────────────────────────── parse_kv_pairs unit tests

class TestParseKvStrPrefix:
    def test_str_prefix_keeps_json_as_string(self):
        """The bug: payload=str:{...} must arrive as a string, not a dict."""
        result = parse_kv_pairs(('payload=str:{"contact":false,"battery":87}',))
        assert result == {"payload": '{"contact":false,"battery":87}'}
        assert isinstance(result["payload"], str)

    def test_str_prefix_with_plain_string(self):
        result = parse_kv_pairs(("topic=str:z2m/Pantry Door",))
        assert result == {"topic": "z2m/Pantry Door"}
        assert isinstance(result["topic"], str)

    def test_str_prefix_empty(self):
        result = parse_kv_pairs(("payload=str:",))
        assert result == {"payload": ""}

    def test_str_prefix_double_escape(self):
        """To send a value that literally starts with 'str:', use str:str:."""
        result = parse_kv_pairs(("msg=str:str:hello",))
        assert result == {"msg": "str:hello"}

    # ── existing coercion must be unchanged ──

    def test_int_coercion_unchanged(self):
        assert parse_kv_pairs(("count=3",)) == {"count": 3}

    def test_bool_coercion_unchanged(self):
        assert parse_kv_pairs(("flag=true",)) == {"flag": True}

    def test_list_coercion_unchanged(self):
        assert parse_kv_pairs(('opts=["a","b"]',)) == {"opts": ["a", "b"]}

    def test_object_coercion_unchanged(self):
        result = parse_kv_pairs(('payload={"a":1}',))
        assert result == {"payload": {"a": 1}}

    def test_plain_string_unchanged(self):
        assert parse_kv_pairs(("k=v",)) == {"k": "v"}


# ────────────────────────────────────────────────────── service call wiring

@pytest.fixture
def runner(monkeypatch, fake_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return CliRunner()


def _invoke(runner, *args, json_out=True):
    full = ["--json"] + list(args) if json_out else list(args)
    return runner.invoke(cli_mod.cli, full,
                         obj={
                             "url": "http://x", "token": "t",
                             "verify_ssl": False, "timeout": 5,
                             "as_json": json_out, "config_path": None,
                         })


class TestServiceCallStrPrefix:
    def test_mqtt_publish_payload_as_string(self, runner, fake_client):
        """The exact reproduction: payload must be a STRING at HA."""
        fake_client.set_service("mqtt", "publish", {"ok": True})
        r = _invoke(
            runner,
            "service", "call", "mqtt", "publish",
            "-D", "topic=z2m/Pantry Door",
            "-D", 'payload=str:{"contact":false,"battery":87}',
        )
        assert r.exit_code == 0, r.output
        last = fake_client.service_calls[-1]
        assert (last["domain"], last["service"]) == ("mqtt", "publish")
        sd = last["service_data"]
        assert sd["topic"] == "z2m/Pantry Door"
        assert sd["payload"] == '{"contact":false,"battery":87}'
        assert isinstance(sd["payload"], str)

    def test_mqtt_publish_payload_coerced_without_prefix(self, runner, fake_client):
        """Without str: prefix, JSON coercion still happens (unchanged behaviour)."""
        fake_client.set_service("mqtt", "publish", {"ok": True})
        r = _invoke(
            runner,
            "service", "call", "mqtt", "publish",
            "-D", "topic=z2m/sensor",
            "-D", 'payload={"contact":false,"battery":87}',
        )
        assert r.exit_code == 0, r.output
        sd = fake_client.service_calls[-1]["service_data"]
        assert sd["payload"] == {"contact": False, "battery": 87}
        assert isinstance(sd["payload"], dict)

    def test_dry_run_shows_string_payload(self, runner, fake_client):
        """--dry-run must also reflect the string, not a dict."""
        r = _invoke(
            runner,
            "service", "call", "mqtt", "publish",
            "-D", "topic=z2m/Pantry Door",
            "-D", 'payload=str:{"contact":false,"battery":87}',
            "--dry-run",
        )
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        assert out["service_data"]["payload"] == '{"contact":false,"battery":87}'
        assert isinstance(out["service_data"]["payload"], str)


# ────────────────────────────────────────────────────── WebSocket --data path

class TestWsDataStrPrefix:
    def test_ws_data_str_prefix(self, runner, fake_client):
        fake_client.set_ws("some/command", {"ok": True})
        r = _invoke(
            runner,
            "ws", "some/command",
            "-D", 'value=str:{"a":1}',
        )
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["payload"]["value"] == '{"a":1}'
        assert isinstance(last["payload"]["value"], str)

    def test_ws_data_coerced_without_prefix(self, runner, fake_client):
        fake_client.set_ws("some/command", {"ok": True})
        r = _invoke(
            runner,
            "ws", "some/command",
            "-D", 'value={"a":1}',
        )
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["payload"]["value"] == {"a": 1}
        assert isinstance(last["payload"]["value"], dict)
