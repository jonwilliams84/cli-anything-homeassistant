"""Tests for the ``str:`` prefix that forces a ``-D`` / ``--data`` value to
stay a literal string even when it is valid JSON.

The motivating bug: ``mqtt.publish`` expects ``payload`` to be a **string**,
but ``parse_kv_pairs`` silently JSON-decoded any value that was valid JSON,
turning ``payload={"contact":false}`` into a dict.  The call returned HTTP
200 and published something no subscriber could parse — a silent failure.

The fix adds an explicit ``str:`` prefix: ``-D 'payload=str:{"a":1}'``
keeps the value as a literal string.  Existing JSON coercion for numbers,
booleans, lists and nested objects is unchanged.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod


# ──────────────────────────────────────────────────────────── unit: _coerce_value

class TestCoerceValue:
    """Direct unit tests for the shared ``_coerce_value`` helper."""

    def test_json_number_stays_int(self):
        assert cli_mod._coerce_value("3") == 3
        assert isinstance(cli_mod._coerce_value("3"), int)

    def test_json_boolean_stays_bool(self):
        assert cli_mod._coerce_value("true") is True
        assert cli_mod._coerce_value("false") is False

    def test_json_list_stays_list(self):
        assert cli_mod._coerce_value('["a", "b"]') == ["a", "b"]

    def test_json_object_stays_dict(self):
        assert cli_mod._coerce_value('{"a": 1}') == {"a": 1}

    def test_plain_string_stays_string(self):
        assert cli_mod._coerce_value("hello") == "hello"

    def test_str_prefix_forces_string_for_json(self):
        result = cli_mod._coerce_value('str:{"contact":false}')
        assert result == '{"contact":false}'
        assert isinstance(result, str)

    def test_str_prefix_forces_string_for_number(self):
        result = cli_mod._coerce_value("str:42")
        assert result == "42"
        assert isinstance(result, str)

    def test_str_prefix_forces_string_for_boolean(self):
        result = cli_mod._coerce_value("str:true")
        assert result == "true"
        assert isinstance(result, str)

    def test_str_prefix_empty(self):
        result = cli_mod._coerce_value("str:")
        assert result == ""
        assert isinstance(result, str)

    def test_str_prefix_double_escape(self):
        """``str:str:foo`` → ``str:foo`` (literal str: prefix)."""
        result = cli_mod._coerce_value("str:str:foo")
        assert result == "str:foo"
        assert isinstance(result, str)


# ──────────────────────────────────────────────────────────── unit: parse_kv_pairs

class TestParseKvPairs:
    def test_str_prefix_in_kv(self):
        d = cli_mod.parse_kv_pairs(('payload=str:{"contact":false}',))
        assert d == {"payload": '{"contact":false}'}
        assert isinstance(d["payload"], str)

    def test_json_coercion_unchanged_for_number(self):
        d = cli_mod.parse_kv_pairs(("count=3",))
        assert d == {"count": 3}
        assert isinstance(d["count"], int)

    def test_json_coercion_unchanged_for_bool(self):
        d = cli_mod.parse_kv_pairs(("flag=true",))
        assert d == {"flag": True}

    def test_json_coercion_unchanged_for_list(self):
        d = cli_mod.parse_kv_pairs(('options=["A","B"]',))
        assert d == {"options": ["A", "B"]}

    def test_json_coercion_unchanged_for_object(self):
        d = cli_mod.parse_kv_pairs(('config={"nested":{"a":1}}',))
        assert d == {"config": {"nested": {"a": 1}}}

    def test_plain_string_unchanged(self):
        d = cli_mod.parse_kv_pairs(("topic=z2m/Pantry Door",))
        assert d == {"topic": "z2m/Pantry Door"}

    def test_mixed_str_and_coerced(self):
        d = cli_mod.parse_kv_pairs((
            'topic=z2m/Pantry Door',
            'payload=str:{"contact":false,"battery":87}',
            'retain=true',
        ))
        assert d == {
            "topic": "z2m/Pantry Door",
            "payload": '{"contact":false,"battery":87}',
            "retain": True,
        }
        assert isinstance(d["payload"], str)
        assert isinstance(d["retain"], bool)


# ──────────────────────────────────────────────────────────── CLI: service call

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
    """End-to-end CLI tests through Click's CliRunner + FakeClient."""

    def test_mqtt_payload_stays_string_with_str_prefix(self, runner, fake_client):
        """The motivating bug: mqtt.publish payload must be a string."""
        fake_client.set_service("mqtt", "publish", {})
        r = _invoke(
            runner, "service", "call", "mqtt", "publish",
            "-D", "topic=z2m/Pantry Door",
            "-D", 'payload=str:{"contact":false,"battery":87}',
        )
        assert r.exit_code == 0, r.output
        sd = fake_client.service_calls[-1]["service_data"]
        assert sd == {
            "topic": "z2m/Pantry Door",
            "payload": '{"contact":false,"battery":87}',
        }
        assert isinstance(sd["payload"], str)

    def test_mqtt_payload_becomes_dict_without_str_prefix(self, runner, fake_client):
        """Without the prefix, JSON coercion still turns it into a dict.

        This documents the old behaviour so the fix is clearly opt-in.
        """
        fake_client.set_service("mqtt", "publish", {})
        r = _invoke(
            runner, "service", "call", "mqtt", "publish",
            "-D", "topic=z2m/Pantry Door",
            "-D", 'payload={"contact":false,"battery":87}',
        )
        assert r.exit_code == 0, r.output
        sd = fake_client.service_calls[-1]["service_data"]
        assert sd == {
            "topic": "z2m/Pantry Door",
            "payload": {"contact": False, "battery": 87},
        }
        assert isinstance(sd["payload"], dict)

    def test_coerced_values_unchanged_alongside_str_prefix(self, runner, fake_client):
        """Numbers, booleans, lists and nested objects still coerce."""
        fake_client.set_service("mqtt", "publish", {})
        r = _invoke(
            runner, "service", "call", "mqtt", "publish",
            "-D", "topic=z2m/sensor",
            "-D", 'payload=str:{"temperature":22.5}',
            "-D", "retain=true",
            "-D", "qos=1",
        )
        assert r.exit_code == 0, r.output
        sd = fake_client.service_calls[-1]["service_data"]
        assert sd == {
            "topic": "z2m/sensor",
            "payload": '{"temperature":22.5}',
            "retain": True,
            "qos": 1,
        }
        assert isinstance(sd["payload"], str)
        assert isinstance(sd["retain"], bool)
        assert isinstance(sd["qos"], int)


# ──────────────────────────────────────────────────────────── CLI: ws --data

class TestWsStrPrefix:
    """The same ``str:`` convention applies to the WebSocket ``--data`` path."""

    def test_ws_data_str_prefix(self, runner, fake_client):
        fake_client.set_ws("some/command", {"ok": True})
        r = _invoke(
            runner, "ws", "some/command",
            "-D", 'value=str:{"a":1}',
        )
        assert r.exit_code == 0, r.output
        call = fake_client.ws_calls[-1]
        assert call["type"] == "some/command"
        assert call["payload"] == {"value": '{"a":1}'}
        assert isinstance(call["payload"]["value"], str)

    def test_ws_data_json_coercion_unchanged(self, runner, fake_client):
        fake_client.set_ws("some/command", {"ok": True})
        r = _invoke(
            runner, "ws", "some/command",
            "-D", 'value={"a":1}',
            "-D", "count=3",
        )
        assert r.exit_code == 0, r.output
        call = fake_client.ws_calls[-1]
        assert call["payload"] == {"value": {"a": 1}, "count": 3}
        assert isinstance(call["payload"]["value"], dict)
        assert isinstance(call["payload"]["count"], int)
