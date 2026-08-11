"""Unit tests for `core/frontend_meta.py`.

Covers the sidebar panel inventory (`get_panels`), the frontend build
version, translation/icon resource fetches and the integration catalog
flattening.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import frontend_meta as fm


PANELS = {
    "lovelace": {
        "component_name": "lovelace",
        "title": "Overview",
        "icon": "mdi:view-dashboard",
        "url_path": "lovelace",
        "require_admin": False,
        "config": {"mode": "storage"},
        "config_panel_domain": None,
    },
    "energy": {
        "component_name": "energy",
        "title": "Energy",
        "icon": None,
        "url_path": "energy",
        "require_admin": False,
        "config": None,
        "config_panel_domain": None,
    },
    "solar": {
        "component_name": "lovelace",
        "title": "Solar",
        "url_path": "solar",
        "require_admin": True,
    },
}

CATALOG = {
    "core": {
        "integration": {
            "hue": {
                "name": "Philips Hue",
                "config_flow": True,
                "iot_class": "local_push",
                "integration_type": "hub",
                "single_config_entry": False,
            },
            "command_line": {
                "name": "Command Line",
                "config_flow": False,
                "iot_class": "local_polling",
            },
        },
        "helper": {
            "derivative": {"name": "Derivative", "config_flow": True, "iot_class": "calculated"}
        },
        "translated_name": ["hue"],
    },
    "custom": {
        "integration": {
            "hacs": {"name": "HACS", "config_flow": True, "iot_class": "cloud_polling"}
        },
        "helper": {},
    },
}

# HA nests related integrations under a brand: `philips` is not itself an
# integration, it holds `hue` and `philips_js`.
BRAND_CATALOG = {
    "core": {
        "integration": {
            "philips": {
                "name": "Philips",
                "integrations": {
                    "hue": {
                        "name": "Philips Hue",
                        "config_flow": True,
                        "iot_class": "local_push",
                        "integration_type": "hub",
                    },
                    "philips_js": {"name": "Philips TV", "config_flow": True},
                },
            },
            "sun": {"config_flow": True, "iot_class": "calculated"},
        },
        "helper": {},
    },
    "custom": {"integration": {}, "helper": {}},
}


# ─────────────────────────────────────────────────────────────────── panels

class TestPanels:
    def test_panels_raw(self, fake_client):
        fake_client.set_ws("get_panels", PANELS)
        assert set(fm.panels(fake_client)) == {"lovelace", "energy", "solar"}
        assert fake_client.ws_calls[-1] == {"type": "get_panels", "payload": {}}

    def test_panels_empty_when_ha_returns_nothing(self, fake_client):
        fake_client.set_ws("get_panels", None)
        assert fm.panels(fake_client) == {}

    def test_list_panels_is_sorted_and_normalized(self, fake_client):
        fake_client.set_ws("get_panels", PANELS)
        rows = fm.list_panels(fake_client)
        assert [r["url_path"] for r in rows] == ["energy", "lovelace", "solar"]
        assert rows[2]["require_admin"] is True
        assert rows[0]["config_panel_domain"] is None

    def test_list_panels_filtered_by_component(self, fake_client):
        fake_client.set_ws("get_panels", PANELS)
        rows = fm.list_panels(fake_client, component_name="lovelace")
        assert [r["url_path"] for r in rows] == ["lovelace", "solar"]

    def test_url_path_falls_back_to_key(self, fake_client):
        fake_client.set_ws("get_panels", {"todo": {"component_name": "todo"}})
        assert fm.list_panels(fake_client)[0]["url_path"] == "todo"

    def test_get_panel(self, fake_client):
        fake_client.set_ws("get_panels", PANELS)
        assert fm.get_panel(fake_client, "energy")["title"] == "Energy"

    def test_get_panel_unknown_raises(self, fake_client):
        fake_client.set_ws("get_panels", PANELS)
        with pytest.raises(ValueError, match="no panel at url_path"):
            fm.get_panel(fake_client, "nope")

    def test_get_panel_requires_url_path(self, fake_client):
        with pytest.raises(ValueError, match="url_path is required"):
            fm.get_panel(fake_client, "")

    def test_dashboards_are_lovelace_panels(self, fake_client):
        fake_client.set_ws("get_panels", PANELS)
        assert [d["url_path"] for d in fm.dashboards(fake_client)] == ["lovelace", "solar"]


# ─────────────────────────────────────────────── version / translations / icons

class TestFrontendResources:
    def test_version(self, fake_client):
        fake_client.set_ws("frontend/get_version", {"version": "20250109.0"})
        assert fm.frontend_version(fake_client) == {"version": "20250109.0"}

    def test_translations_defaults(self, fake_client):
        fake_client.set_ws("frontend/get_translations", {"resources": {"a": "b"}})
        assert fm.translations(fake_client) == {"a": "b"}
        assert fake_client.ws_calls[-1]["payload"] == {
            "language": "en",
            "category": "entity_component",
        }

    def test_translations_with_filters(self, fake_client):
        fake_client.set_ws("frontend/get_translations", {"resources": {}})
        fm.translations(
            fake_client, language="nl", category="state", integration="person", config_flow=True
        )
        assert fake_client.ws_calls[-1]["payload"] == {
            "language": "nl",
            "category": "state",
            "integration": ["person"],
            "config_flow": True,
        }

    def test_translations_accepts_integration_list(self, fake_client):
        fake_client.set_ws("frontend/get_translations", {"resources": {}})
        fm.translations(fake_client, integration=["hue", "mqtt"])
        assert fake_client.ws_calls[-1]["payload"]["integration"] == ["hue", "mqtt"]

    def test_translations_requires_language(self, fake_client):
        with pytest.raises(ValueError, match="language is required"):
            fm.translations(fake_client, language="")

    def test_icons(self, fake_client):
        fake_client.set_ws("frontend/get_icons", {"resources": {"light": {}}})
        assert fm.icons(fake_client, category="entity_component") == {"light": {}}

    def test_icons_rejects_bad_category(self, fake_client):
        with pytest.raises(ValueError, match="category must be one of"):
            fm.icons(fake_client, category="bogus")

    def test_icons_integration_filter(self, fake_client):
        fake_client.set_ws("frontend/get_icons", {"resources": {}})
        fm.icons(fake_client, category="services", integration="mqtt")
        assert fake_client.ws_calls[-1]["payload"] == {
            "category": "services",
            "integration": ["mqtt"],
        }

    def test_resources_missing_key_returns_empty(self, fake_client):
        fake_client.set_ws("frontend/get_icons", {})
        assert fm.icons(fake_client) == {}


# ─────────────────────────────────────────────────────────── integration catalog

class TestIntegrationCatalog:
    def test_raw_descriptions(self, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        assert set(fm.integration_descriptions(fake_client)) == {"core", "custom"}

    def test_flattened_rows_sorted(self, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        rows = fm.list_integrations(fake_client)
        assert [r["domain"] for r in rows] == ["command_line", "derivative", "hacs", "hue"]

    def test_row_shape(self, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        hue = next(r for r in fm.list_integrations(fake_client) if r["domain"] == "hue")
        assert hue == {
            "domain": "hue",
            "name": "Philips Hue",
            "kind": "integration",
            "source": "core",
            "brand": None,
            "integration_type": "hub",
            "iot_class": "local_push",
            "config_flow": True,
            "single_config_entry": False,
        }

    def test_filter_by_source(self, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        rows = fm.list_integrations(fake_client, source="custom")
        assert [r["domain"] for r in rows] == ["hacs"]

    def test_filter_by_kind(self, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        rows = fm.list_integrations(fake_client, kind="helper")
        assert [r["domain"] for r in rows] == ["derivative"]

    def test_config_flow_only(self, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        rows = fm.list_integrations(fake_client, config_flow_only=True)
        assert "command_line" not in [r["domain"] for r in rows]

    def test_filter_by_iot_class(self, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        rows = fm.list_integrations(fake_client, iot_class="cloud_polling")
        assert [r["domain"] for r in rows] == ["hacs"]

    def test_translated_name_list_is_ignored(self, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        assert all(r["kind"] in ("integration", "helper") for r in fm.list_integrations(fake_client))

    def test_rejects_bad_kind(self, fake_client):
        with pytest.raises(ValueError, match="kind must be one of"):
            fm.list_integrations(fake_client, kind="nope")

    def test_rejects_bad_source(self, fake_client):
        with pytest.raises(ValueError, match="source must be"):
            fm.list_integrations(fake_client, source="nope")

    def test_empty_catalog(self, fake_client):
        fake_client.set_ws("integration/descriptions", None)
        assert fm.list_integrations(fake_client) == []

    def test_find_integration(self, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        assert fm.find_integration(fake_client, "hacs")["source"] == "custom"

    def test_find_integration_missing(self, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        assert fm.find_integration(fake_client, "zwave_js") is None

    def test_find_integration_requires_domain(self, fake_client):
        with pytest.raises(ValueError, match="domain is required"):
            fm.find_integration(fake_client, "")


class TestBrandUnpacking:
    def test_brand_children_become_rows(self, fake_client):
        fake_client.set_ws("integration/descriptions", BRAND_CATALOG)
        rows = fm.list_integrations(fake_client)
        assert [r["domain"] for r in rows] == ["hue", "philips_js", "sun"]

    def test_brand_is_recorded_on_the_child(self, fake_client):
        fake_client.set_ws("integration/descriptions", BRAND_CATALOG)
        hue = next(r for r in fm.list_integrations(fake_client) if r["domain"] == "hue")
        assert hue["brand"] == "philips"
        assert hue["name"] == "Philips Hue"
        assert hue["iot_class"] == "local_push"

    def test_plain_entry_has_no_brand(self, fake_client):
        fake_client.set_ws("integration/descriptions", BRAND_CATALOG)
        sun = next(r for r in fm.list_integrations(fake_client) if r["domain"] == "sun")
        assert sun["brand"] is None

    def test_find_integration_reaches_into_brands(self, fake_client):
        fake_client.set_ws("integration/descriptions", BRAND_CATALOG)
        assert fm.find_integration(fake_client, "hue")["brand"] == "philips"

    def test_empty_brand_falls_back_to_itself(self, fake_client):
        fake_client.set_ws(
            "integration/descriptions",
            {"core": {"integration": {"weird": {"name": "Weird", "integrations": {}}}}},
        )
        rows = fm.list_integrations(fake_client)
        assert [r["domain"] for r in rows] == ["weird"]
