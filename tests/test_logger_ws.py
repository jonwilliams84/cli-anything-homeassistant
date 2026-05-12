"""Unit tests for cli_anything.homeassistant.core.logger_ws."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import logger_ws


class TestLoggerWs:
    # ── log_info ────────────────────────────────────────────────────────────

    def test_log_info_happy(self, fake_client):
        log_data = [
            {"domain": "hue", "level": 20},  # INFO
            {"domain": "mqtt", "level": 10},  # DEBUG
            {"domain": "zwave", "level": 30},  # WARNING
        ]
        fake_client.set_ws("logger/log_info", log_data)
        result = logger_ws.log_info(fake_client)
        assert result == log_data
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["type"] == "logger/log_info"
        assert last_ws["payload"] == {}

    def test_log_info_empty_list(self, fake_client):
        fake_client.set_ws("logger/log_info", [])
        result = logger_ws.log_info(fake_client)
        assert result == []

    def test_log_info_return_shape(self, fake_client):
        fake_client.set_ws(
            "logger/log_info",
            [
                {"domain": "test", "level": 20},
                {"domain": "another", "level": 10},
            ],
        )
        result = logger_ws.log_info(fake_client)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(item, dict) for item in result)

    # ── log_level ───────────────────────────────────────────────────────────

    def test_log_level_integration_happy(self, fake_client):
        fake_client.set_ws(
            "logger/log_level",
            {"integration": "hue", "level": 20},
        )
        result = logger_ws.log_level(fake_client, integration="hue")
        assert result["integration"] == "hue"
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["type"] == "logger/log_level"
        assert last_ws["payload"]["integration"] == "hue"
        assert "namespace" not in last_ws["payload"]

    def test_log_level_namespace_happy(self, fake_client):
        fake_client.set_ws(
            "logger/log_level",
            {"namespace": "homeassistant.components.mqtt", "level": 10},
        )
        result = logger_ws.log_level(
            fake_client, namespace="homeassistant.components.mqtt"
        )
        assert result["namespace"] == "homeassistant.components.mqtt"
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["payload"]["namespace"] == "homeassistant.components.mqtt"
        assert "integration" not in last_ws["payload"]

    def test_log_level_both_raises(self, fake_client):
        with pytest.raises(ValueError, match="cannot set both integration and namespace"):
            logger_ws.log_level(
                fake_client, integration="hue", namespace="homeassistant.components.hue"
            )

    def test_log_level_neither_raises(self, fake_client):
        with pytest.raises(ValueError, match="must set either integration or namespace"):
            logger_ws.log_level(fake_client)

    def test_log_level_return_shape(self, fake_client):
        fake_client.set_ws("logger/log_level", {"integration": "mqtt", "level": 20})
        result = logger_ws.log_level(fake_client, integration="mqtt")
        assert isinstance(result, dict)

    # ── integration_log_level ───────────────────────────────────────────────

    def test_integration_log_level_happy(self, fake_client):
        fake_client.set_ws("logger/integration_log_level", {})
        result = logger_ws.integration_log_level(
            fake_client, integration="hue", level="debug"
        )
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["type"] == "logger/integration_log_level"
        assert last_ws["payload"]["integration"] == "hue"
        assert last_ws["payload"]["level"] == "debug"
        assert last_ws["payload"]["persistence"] == "none"

    def test_integration_log_level_all_levels(self, fake_client):
        for lvl in ("debug", "info", "warning", "error", "critical"):
            fake_client.set_ws("logger/integration_log_level", {})
            logger_ws.integration_log_level(
                fake_client, integration="mqtt", level=lvl
            )
            last_ws = fake_client.ws_calls[-1]
            assert last_ws["payload"]["level"] == lvl

    def test_integration_log_level_persistence_once(self, fake_client):
        fake_client.set_ws("logger/integration_log_level", {})
        logger_ws.integration_log_level(
            fake_client, integration="zwave", level="warning", persistence="once"
        )
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["payload"]["persistence"] == "once"

    def test_integration_log_level_persistence_none_explicit(self, fake_client):
        fake_client.set_ws("logger/integration_log_level", {})
        logger_ws.integration_log_level(
            fake_client, integration="zwave", level="warning", persistence="none"
        )
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["payload"]["persistence"] == "none"

    def test_integration_log_level_empty_integration_raises(self, fake_client):
        with pytest.raises(ValueError, match="integration is required"):
            logger_ws.integration_log_level(fake_client, integration="", level="debug")

    def test_integration_log_level_invalid_level_raises(self, fake_client):
        with pytest.raises(ValueError, match="level must be one of"):
            logger_ws.integration_log_level(
                fake_client, integration="hue", level="verbose"
            )

    def test_integration_log_level_invalid_persistence_raises(self, fake_client):
        with pytest.raises(ValueError, match="persistence must be one of"):
            logger_ws.integration_log_level(
                fake_client,
                integration="hue",
                level="debug",
                persistence="forever",  # type: ignore
            )

    def test_integration_log_level_return_shape(self, fake_client):
        fake_client.set_ws(
            "logger/integration_log_level", {"result": "level_set"}
        )
        result = logger_ws.integration_log_level(
            fake_client, integration="mqtt", level="info"
        )
        assert isinstance(result, dict)
