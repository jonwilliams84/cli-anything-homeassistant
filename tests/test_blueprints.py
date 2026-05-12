"""Unit tests for cli_anything.homeassistant.core.blueprints.

All tests run against FakeClient (auto-injected via the ``fake_client``
fixture in conftest.py) — no live Home Assistant required.

WS message types covered:
  blueprint/list       — list_blueprints
  blueprint/import     — import_blueprint
  blueprint/save       — save_blueprint
  blueprint/delete     — delete_blueprint
  blueprint/substitute — substitute_blueprint
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import blueprints


class TestBlueprints:
    # ──────────────────────────────────────── list_blueprints ────────────────

    def test_list_blueprints_with_domain_payload(self, fake_client):
        """list_blueprints sends ``blueprint/list`` with {domain} when given."""
        fake_client.set_ws("blueprint/list", {})
        blueprints.list_blueprints(fake_client, domain="automation")
        call = fake_client.ws_calls[-1]
        assert call["type"] == "blueprint/list"
        assert call["payload"] == {"domain": "automation"}

    def test_list_blueprints_no_domain_empty_payload(self, fake_client):
        """list_blueprints omits domain from payload when not given."""
        fake_client.set_ws("blueprint/list", {})
        blueprints.list_blueprints(fake_client)
        call = fake_client.ws_calls[-1]
        assert call["type"] == "blueprint/list"
        assert call["payload"] == {}

    def test_list_blueprints_script_domain(self, fake_client):
        """list_blueprints accepts ``'script'`` as a valid domain."""
        fake_client.set_ws("blueprint/list", {})
        blueprints.list_blueprints(fake_client, domain="script")
        assert fake_client.ws_calls[-1]["payload"] == {"domain": "script"}

    def test_list_blueprints_template_domain(self, fake_client):
        """list_blueprints accepts ``'template'`` as a valid domain."""
        fake_client.set_ws("blueprint/list", {})
        blueprints.list_blueprints(fake_client, domain="template")
        assert fake_client.ws_calls[-1]["payload"] == {"domain": "template"}

    def test_list_blueprints_returns_dict(self, fake_client):
        """list_blueprints returns the dict from the WS response."""
        response = {
            "automation/my_bp.yaml": {"metadata": {"name": "My BP"}},
        }
        fake_client.set_ws("blueprint/list", response)
        result = blueprints.list_blueprints(fake_client, domain="automation")
        assert result == response

    def test_list_blueprints_non_dict_response_normalised(self, fake_client):
        """list_blueprints returns {} when HA returns a non-dict."""
        fake_client.set_ws("blueprint/list", [])
        result = blueprints.list_blueprints(fake_client, domain="automation")
        assert result == {}

    def test_list_blueprints_invalid_domain(self, fake_client):
        """list_blueprints raises ValueError for an unrecognised domain."""
        with pytest.raises(ValueError, match="domain must be one of"):
            blueprints.list_blueprints(fake_client, domain="sensor")

    def test_list_blueprints_invalid_domain_empty_string(self, fake_client):
        """list_blueprints raises ValueError for an empty domain string."""
        with pytest.raises(ValueError, match="domain must be one of"):
            blueprints.list_blueprints(fake_client, domain="")

    # ──────────────────────────────────────── import_blueprint ───────────────

    def test_import_blueprint_happy_path_payload(self, fake_client):
        """import_blueprint sends ``blueprint/import`` with {url}."""
        url = "https://github.com/user/repo/blob/main/blueprint.yaml"
        fake_client.set_ws("blueprint/import", {})
        blueprints.import_blueprint(fake_client, url=url)
        call = fake_client.ws_calls[-1]
        assert call["type"] == "blueprint/import"
        assert call["payload"] == {"url": url}

    def test_import_blueprint_returns_dict(self, fake_client):
        """import_blueprint returns the dict from the WS response."""
        response = {
            "suggested_filename": "my_blueprint",
            "raw_data": "blueprint:\n  name: My Blueprint\n",
            "blueprint": {"metadata": {"name": "My Blueprint"}},
            "validation_errors": None,
            "exists": False,
        }
        fake_client.set_ws("blueprint/import", response)
        result = blueprints.import_blueprint(
            fake_client, url="https://example.com/bp.yaml"
        )
        assert result == response

    def test_import_blueprint_http_url_accepted(self, fake_client):
        """import_blueprint accepts an http:// URL."""
        fake_client.set_ws("blueprint/import", {})
        blueprints.import_blueprint(fake_client, url="http://example.com/bp.yaml")
        assert fake_client.ws_calls[-1]["payload"]["url"] == "http://example.com/bp.yaml"

    def test_import_blueprint_empty_url_raises(self, fake_client):
        """import_blueprint raises ValueError when url is empty."""
        with pytest.raises(ValueError, match="url is required"):
            blueprints.import_blueprint(fake_client, url="")

    def test_import_blueprint_invalid_scheme_raises(self, fake_client):
        """import_blueprint raises ValueError when url lacks http(s) scheme."""
        with pytest.raises(ValueError, match="url must start with http"):
            blueprints.import_blueprint(fake_client, url="ftp://example.com/bp.yaml")

    def test_import_blueprint_no_scheme_raises(self, fake_client):
        """import_blueprint raises ValueError when url has no scheme."""
        with pytest.raises(ValueError, match="url must start with http"):
            blueprints.import_blueprint(fake_client, url="example.com/bp.yaml")

    # ──────────────────────────────────────── save_blueprint ─────────────────

    def test_save_blueprint_happy_path_payload(self, fake_client):
        """save_blueprint sends ``blueprint/save`` with required fields."""
        fake_client.set_ws("blueprint/save", {"overrides_existing": False})
        blueprints.save_blueprint(
            fake_client,
            domain="automation",
            path="my_blueprint",
            yaml="blueprint:\n  name: Test\n",
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "blueprint/save"
        assert call["payload"] == {
            "domain": "automation",
            "path": "my_blueprint",
            "yaml": "blueprint:\n  name: Test\n",
        }

    def test_save_blueprint_with_source_url(self, fake_client):
        """save_blueprint includes source_url in payload when supplied."""
        fake_client.set_ws("blueprint/save", {})
        blueprints.save_blueprint(
            fake_client,
            domain="script",
            path="my_script_bp",
            yaml="blueprint:\n  name: Script BP\n",
            source_url="https://example.com/bp.yaml",
        )
        call = fake_client.ws_calls[-1]
        assert call["payload"]["source_url"] == "https://example.com/bp.yaml"

    def test_save_blueprint_without_source_url_omitted(self, fake_client):
        """save_blueprint does not send source_url when not provided."""
        fake_client.set_ws("blueprint/save", {})
        blueprints.save_blueprint(
            fake_client,
            domain="template",
            path="my_template",
            yaml="blueprint:\n  name: T\n",
        )
        assert "source_url" not in fake_client.ws_calls[-1]["payload"]

    def test_save_blueprint_invalid_domain(self, fake_client):
        """save_blueprint raises ValueError for an unrecognised domain."""
        with pytest.raises(ValueError, match="domain must be one of"):
            blueprints.save_blueprint(
                fake_client, domain="device_tracker",
                path="bp", yaml="blueprint:\n  name: X\n"
            )

    def test_save_blueprint_empty_path_raises(self, fake_client):
        """save_blueprint raises ValueError when path is empty."""
        with pytest.raises(ValueError, match="path is required"):
            blueprints.save_blueprint(
                fake_client, domain="automation", path="",
                yaml="blueprint:\n  name: X\n"
            )

    def test_save_blueprint_empty_yaml_raises(self, fake_client):
        """save_blueprint raises ValueError when yaml is empty."""
        with pytest.raises(ValueError, match="yaml is required"):
            blueprints.save_blueprint(
                fake_client, domain="automation", path="my_bp", yaml=""
            )

    # ──────────────────────────────────────── delete_blueprint ───────────────

    def test_delete_blueprint_happy_path_payload(self, fake_client):
        """delete_blueprint sends ``blueprint/delete`` with {domain, path}."""
        fake_client.set_ws("blueprint/delete", None)
        blueprints.delete_blueprint(
            fake_client, domain="automation", path="my_blueprint.yaml"
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "blueprint/delete"
        assert call["payload"] == {
            "domain": "automation",
            "path": "my_blueprint.yaml",
        }

    def test_delete_blueprint_invalid_domain(self, fake_client):
        """delete_blueprint raises ValueError for an unrecognised domain."""
        with pytest.raises(ValueError, match="domain must be one of"):
            blueprints.delete_blueprint(
                fake_client, domain="unknown", path="bp.yaml"
            )

    def test_delete_blueprint_empty_path_raises(self, fake_client):
        """delete_blueprint raises ValueError when path is empty."""
        with pytest.raises(ValueError, match="path is required"):
            blueprints.delete_blueprint(
                fake_client, domain="script", path=""
            )

    # ──────────────────────────────────────── substitute_blueprint ───────────

    def test_substitute_blueprint_happy_path_payload(self, fake_client):
        """substitute_blueprint sends ``blueprint/substitute`` with all fields."""
        fake_client.set_ws("blueprint/substitute", {"substituted_config": {}})
        user_input = {"trigger_entity": "sensor.temp", "threshold": 25}
        blueprints.substitute_blueprint(
            fake_client,
            domain="automation",
            path="my_blueprint.yaml",
            input=user_input,
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "blueprint/substitute"
        assert call["payload"] == {
            "domain": "automation",
            "path": "my_blueprint.yaml",
            "input": user_input,
        }

    def test_substitute_blueprint_returns_dict(self, fake_client):
        """substitute_blueprint returns the dict from the WS response."""
        response = {"substituted_config": {"trigger": [], "action": []}}
        fake_client.set_ws("blueprint/substitute", response)
        result = blueprints.substitute_blueprint(
            fake_client,
            domain="script",
            path="my_script_bp.yaml",
            input={"name": "Test"},
        )
        assert result == response

    def test_substitute_blueprint_invalid_domain(self, fake_client):
        """substitute_blueprint raises ValueError for an unrecognised domain."""
        with pytest.raises(ValueError, match="domain must be one of"):
            blueprints.substitute_blueprint(
                fake_client, domain="light", path="bp.yaml", input={}
            )

    def test_substitute_blueprint_empty_path_raises(self, fake_client):
        """substitute_blueprint raises ValueError when path is empty."""
        with pytest.raises(ValueError, match="path is required"):
            blueprints.substitute_blueprint(
                fake_client, domain="automation", path="", input={}
            )

    def test_substitute_blueprint_non_dict_input_raises(self, fake_client):
        """substitute_blueprint raises ValueError when input is not a dict."""
        with pytest.raises(ValueError, match="input must be a dict"):
            blueprints.substitute_blueprint(
                fake_client, domain="automation",
                path="my_bp.yaml", input=["not", "a", "dict"]
            )
