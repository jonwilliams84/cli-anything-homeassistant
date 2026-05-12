"""Unit tests for cli_anything.homeassistant.core.frontend_prefs.

All tests run against FakeClient (auto-injected via the ``fake_client``
fixture in conftest.py) — no live Home Assistant required.

WS message types covered:
  frontend/get_user_data  — get_user_data
  frontend/set_user_data  — set_user_data
  template/start_preview  — start_template_preview

REST endpoint covered:
  POST api/template       — render_template
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import frontend_prefs


class TestFrontendPrefs:
    # ────────────────────────────── get_user_data ────────────────────────────

    def test_get_user_data_with_key_payload(self, fake_client):
        """get_user_data with a key sends ``frontend/get_user_data`` with {key}."""
        fake_client.set_ws("frontend/get_user_data", {"value": "dark"})
        frontend_prefs.get_user_data(fake_client, key="theme")
        call = fake_client.ws_calls[-1]
        assert call["type"] == "frontend/get_user_data"
        assert call["payload"] == {"key": "theme"}

    def test_get_user_data_without_key_payload(self, fake_client):
        """get_user_data without a key sends an empty payload."""
        fake_client.set_ws("frontend/get_user_data", {"value": {}})
        frontend_prefs.get_user_data(fake_client)
        call = fake_client.ws_calls[-1]
        assert call["type"] == "frontend/get_user_data"
        assert call["payload"] == {}

    def test_get_user_data_returns_value_dict(self, fake_client):
        """get_user_data returns the full dict from the WS response."""
        expected = {"value": {"theme": "dark", "sidebar_open": True}}
        fake_client.set_ws("frontend/get_user_data", expected)
        result = frontend_prefs.get_user_data(fake_client)
        assert result == expected

    def test_get_user_data_single_key_return_shape(self, fake_client):
        """get_user_data with key returns a dict containing the value."""
        fake_client.set_ws("frontend/get_user_data", {"value": 42})
        result = frontend_prefs.get_user_data(fake_client, key="counter")
        assert isinstance(result, dict)
        assert result["value"] == 42

    # ────────────────────────────── set_user_data ────────────────────────────

    def test_set_user_data_happy_path_payload(self, fake_client):
        """set_user_data sends ``frontend/set_user_data`` with {key, value}."""
        fake_client.set_ws("frontend/set_user_data", {})
        frontend_prefs.set_user_data(fake_client, key="theme", value="dark")
        call = fake_client.ws_calls[-1]
        assert call["type"] == "frontend/set_user_data"
        assert call["payload"] == {"key": "theme", "value": "dark"}

    def test_set_user_data_dict_value(self, fake_client):
        """set_user_data accepts a dict as value and records it correctly."""
        fake_client.set_ws("frontend/set_user_data", {})
        frontend_prefs.set_user_data(
            fake_client, key="prefs", value={"sidebar": True, "density": "compact"}
        )
        call = fake_client.ws_calls[-1]
        assert call["payload"]["key"] == "prefs"
        assert call["payload"]["value"] == {"sidebar": True, "density": "compact"}

    def test_set_user_data_none_value_accepted(self, fake_client):
        """set_user_data accepts None as a JSON-serialisable value."""
        fake_client.set_ws("frontend/set_user_data", {})
        frontend_prefs.set_user_data(fake_client, key="reset", value=None)
        call = fake_client.ws_calls[-1]
        assert call["payload"]["value"] is None

    def test_set_user_data_empty_key_raises(self, fake_client):
        """set_user_data raises ValueError when key is an empty string."""
        with pytest.raises(ValueError, match="key must be a non-empty string"):
            frontend_prefs.set_user_data(fake_client, key="", value="anything")

    def test_set_user_data_non_serialisable_raises(self, fake_client):
        """set_user_data raises ValueError when value is not JSON-serialisable."""
        with pytest.raises(ValueError, match="JSON-serialisable"):
            frontend_prefs.set_user_data(fake_client, key="bad", value=object())

    # ────────────────────────────── render_template ──────────────────────────

    def test_render_template_happy_path_payload(self, fake_client):
        """render_template POSTs to ``api/template`` with the template string."""
        fake_client.set("POST", "api/template", "on")
        frontend_prefs.render_template(fake_client, template="{{ states('light.bed') }}")
        call = fake_client.calls[-1]
        assert call["verb"] == "POST"
        assert call["path"] == "api/template"
        assert call["payload"]["template"] == "{{ states('light.bed') }}"

    def test_render_template_with_variables_payload(self, fake_client):
        """render_template includes variables in the POST body when supplied."""
        fake_client.set("POST", "api/template", "Hello world")
        frontend_prefs.render_template(
            fake_client,
            template="{{ greeting }} world",
            variables={"greeting": "Hello"},
        )
        call = fake_client.calls[-1]
        assert call["payload"]["variables"] == {"greeting": "Hello"}

    def test_render_template_with_timeout_payload(self, fake_client):
        """render_template includes timeout in the POST body when supplied."""
        fake_client.set("POST", "api/template", "5")
        frontend_prefs.render_template(
            fake_client, template="{{ 2 + 3 }}", timeout=5.0
        )
        call = fake_client.calls[-1]
        assert call["payload"]["timeout"] == 5.0

    def test_render_template_no_variables_in_payload(self, fake_client):
        """render_template omits variables from POST body when not supplied."""
        fake_client.set("POST", "api/template", "result")
        frontend_prefs.render_template(fake_client, template="{{ 1 + 1 }}")
        call = fake_client.calls[-1]
        assert "variables" not in call["payload"]

    def test_render_template_returns_string(self, fake_client):
        """render_template returns the rendered string from the response."""
        fake_client.set("POST", "api/template", "unavailable")
        result = frontend_prefs.render_template(
            fake_client, template="{{ states('sensor.temp') }}"
        )
        assert isinstance(result, str)
        assert result == "unavailable"

    def test_render_template_empty_template_raises(self, fake_client):
        """render_template raises ValueError when template is empty."""
        with pytest.raises(ValueError, match="template must be a non-empty string"):
            frontend_prefs.render_template(fake_client, template="")

    # ─────────────────────────── start_template_preview ─────────────────────

    def test_start_template_preview_happy_path_payload(self, fake_client):
        """start_template_preview sends ``template/start_preview`` WS message."""
        fake_client.set_ws("template/start_preview", None)
        frontend_prefs.start_template_preview(
            fake_client, template="{{ states('light.living') }}"
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "template/start_preview"
        assert call["payload"]["template"] == "{{ states('light.living') }}"

    def test_start_template_preview_with_variables_payload(self, fake_client):
        """start_template_preview includes variables in the WS payload."""
        fake_client.set_ws("template/start_preview", None)
        frontend_prefs.start_template_preview(
            fake_client,
            template="{{ x + 1 }}",
            variables={"x": 10},
        )
        call = fake_client.ws_calls[-1]
        assert call["payload"]["variables"] == {"x": 10}

    def test_start_template_preview_no_variables_omitted(self, fake_client):
        """start_template_preview omits variables from WS payload when not supplied."""
        fake_client.set_ws("template/start_preview", None)
        frontend_prefs.start_template_preview(
            fake_client, template="{{ now() }}"
        )
        call = fake_client.ws_calls[-1]
        assert "variables" not in call["payload"]

    def test_start_template_preview_returns_none(self, fake_client):
        """start_template_preview returns None (streaming needs ws_subscribe)."""
        fake_client.set_ws("template/start_preview", None)
        result = frontend_prefs.start_template_preview(
            fake_client, template="{{ states('sensor.x') }}"
        )
        assert result is None

    def test_start_template_preview_empty_template_raises(self, fake_client):
        """start_template_preview raises ValueError when template is empty."""
        with pytest.raises(ValueError, match="template must be a non-empty string"):
            frontend_prefs.start_template_preview(fake_client, template="")

    def test_start_template_preview_recorded_in_ws_calls(self, fake_client):
        """start_template_preview is recorded in ws_calls for orchestrators."""
        fake_client.set_ws("template/start_preview", None)
        frontend_prefs.start_template_preview(
            fake_client, template="{{ 'hello' }}"
        )
        types = [c["type"] for c in fake_client.ws_calls]
        assert "template/start_preview" in types
