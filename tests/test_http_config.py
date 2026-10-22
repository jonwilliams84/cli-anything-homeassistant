"""Unit tests for cli_anything.homeassistant.core.http_config."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import http_config


class TestGetConfig:
    def test_reads_the_websocket(self, fake_client):
        fake_client.set_ws("http/config", {"stable": {"server_port": 8123}})
        assert http_config.get_config(fake_client) == {"stable": {"server_port": 8123}}
        assert fake_client.ws_calls[-1]["type"] == "http/config"


class TestSetConfig:
    def test_merges_onto_the_stable_config(self, fake_client):
        fake_client.set_ws("http/config", {"stable": {"server_port": 8123}, "pending": None})
        fake_client.set_ws("http/config/configure", {"restart": True})
        out = http_config.set_config(fake_client, {"server_port": 8124})
        assert out == {"restart": True}
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload == {"config": {"server_port": 8124}}

    def test_pending_config_is_the_base(self, fake_client):
        fake_client.set_ws(
            "http/config",
            {"stable": {"server_port": 8123}, "pending": {"server_port": 8124}},
        )
        fake_client.set_ws("http/config/configure", {"restart": False})
        http_config.set_config(fake_client, {"ip_ban_enabled": False})
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["config"]["server_port"] == 8124
        assert payload["config"]["ip_ban_enabled"] is False

    def test_meta_keys_are_dropped(self, fake_client):
        """The store's own bookkeeping keys are not part of HA's schema."""
        fake_client.set_ws(
            "http/config",
            {
                "stable": {
                    "server_port": 8123,
                    "created_at": "2026-10-22T00:00:00",
                    "error": None,
                    "error_message": None,
                }
            },
        )
        fake_client.set_ws("http/config/configure", {"restart": True})
        http_config.set_config(fake_client, {"server_port": 8124})
        config = fake_client.ws_calls[-1]["payload"]["config"]
        assert "created_at" not in config
        assert "error" not in config
        assert "error_message" not in config

    def test_unknown_update_key_is_refused(self, fake_client):
        with pytest.raises(ValueError, match="unknown HTTP config key"):
            http_config.set_config(fake_client, {"server_portz": 8124})

    def test_empty_updates_refused(self, fake_client):
        with pytest.raises(ValueError, match="at least one config key"):
            http_config.set_config(fake_client, {})

    def test_extra_key_rejected_by_ha_is_dropped(self, fake_client):
        """A key this HA does not know is named by HA — drop it and retry."""
        fake_client.set_ws("http/config", {"stable": {"server_port": 8123, "future_key": 1}})
        calls = []

        def ws_call(msg_type, payload=None):
            calls.append((msg_type, payload))
            if msg_type == "http/config/configure":
                if "future_key" in payload["config"]:
                    raise RuntimeError(
                        "extra keys not allowed @ data['future_key']"
                    )
                return {"restart": True}
            return {"stable": {"server_port": 8123, "future_key": 1}}

        fake_client.ws_call = ws_call
        out = http_config.set_config(fake_client, {"server_port": 8124})
        assert out == {"restart": True}
        assert "future_key" not in calls[-1][1]["config"]


class TestPromote:
    def test_calls_promote(self, fake_client):
        fake_client.set_ws("http/config/promote", {})
        http_config.promote(fake_client)
        assert fake_client.ws_calls[-1]["type"] == "http/config/promote"


class TestDescribe:
    def test_flattens_the_state(self, fake_client):
        fake_client.set_ws(
            "http/config",
            {
                "stable": {"server_port": 8123},
                "pending": None,
                "default": {"server_port": 8123},
                "active_config_type": "stable",
                "revert_at": None,
            },
        )
        out = http_config.describe(fake_client)
        assert out["active_config_type"] == "stable"
        assert out["stable"] == {"server_port": 8123}
        assert out["pending"] is None
        assert out["pending_keys"] == []


class TestCoerceValue:
    def test_single_string_becomes_a_list(self):
        assert http_config.coerce_value("server_host", "0.0.0.0") == ["0.0.0.0"]

    def test_list_stays_a_list(self):
        assert http_config.coerce_value("trusted_proxies", ["10.0.0.0/8"]) == ["10.0.0.0/8"]

    def test_scalar_untouched(self):
        assert http_config.coerce_value("server_port", 8124) == 8124
