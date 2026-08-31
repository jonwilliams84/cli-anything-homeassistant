"""`core/service_errors.py` — recovering the reason HA's REST API discards.

Measured against a live 2025.1.4 before any of this was written:

    POST services/camera/record        -> 500  body "Server got itself in trouble"
    POST services/date/set_value       -> 400  body "400: Bad Request"
    POST services/vacuum/start_pause   -> 400  body "400: Bad Request"

and the same three over the websocket:

    home_assistant_error  camera.demo_camera does not support record service
    invalid_format        Could not parse date for dictionary value @ data['date']
    not_found             Service vacuum.start_pause not found.

The status is the only thing REST gives that carries information, and what it
carries is whether the handler RAN: 400 means it did not, 500 means it did.
That distinction is what decides whether a re-issue is safe.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import service_errors
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

REGISTRY = [
    {"domain": "switch", "services": {"turn_on": {}, "turn_off": {}, "toggle": {}}},
    {
        "domain": "vacuum",
        "services": {"start": {}, "pause": {}, "stop": {}, "return_to_base": {}},
    },
]


@pytest.fixture
def registry_client(fake_client):
    fake_client.set("GET", "services", REGISTRY)
    return fake_client


class TestRegistry:
    def test_registered_services(self, registry_client):
        out = service_errors.registered_services(registry_client)
        assert out["switch"] == ["toggle", "turn_off", "turn_on"]

    def test_is_registered(self, registry_client):
        assert service_errors.is_registered(registry_client, "switch", "turn_on")
        assert not service_errors.is_registered(registry_client, "vacuum", "start_pause")

    def test_services_yaml_is_not_the_registry(self, registry_client):
        """`vacuum/services.yaml` documents start_pause; the registry has it not."""
        with pytest.raises(ValueError, match="not registered"):
            service_errors.assert_registered(registry_client, "vacuum", "start_pause")

    def test_assert_registered_lists_the_alternatives(self, registry_client):
        with pytest.raises(ValueError) as exc:
            service_errors.assert_registered(registry_client, "vacuum", "start_pause")
        assert "return_to_base" in str(exc.value)

    def test_missing_domain_says_integration_not_loaded(self, registry_client):
        with pytest.raises(ValueError, match="not loaded"):
            service_errors.assert_registered(registry_client, "knx", "send")

    def test_assert_registered_passes_silently(self, registry_client):
        assert service_errors.assert_registered(registry_client, "switch", "turn_on") is None

    def test_garbage_registry_does_not_explode(self, fake_client):
        fake_client.set("GET", "services", {"not": "a list"})
        assert service_errors.registered_services(fake_client) == {}

    def test_requires_both_names(self, registry_client):
        with pytest.raises(ValueError, match="domain and service"):
            service_errors.is_registered(registry_client, "switch", "")


class TestExplain:
    def test_success(self, fake_client):
        fake_client.set_ws("call_service", {"context": {"id": "abc"}})
        out = service_errors.explain(fake_client, "switch", "turn_on",
                                     {"entity_id": "switch.ac"})
        assert out["ok"] is True
        assert out["service"] == "switch.turn_on"
        assert fake_client.ws_calls[-1]["payload"] == {
            "domain": "switch",
            "service": "turn_on",
            "service_data": {"entity_id": "switch.ac"},
        }

    def test_failure_carries_has_code_and_sentence(self, fake_client):
        fake_client.set_ws_error(
            "call_service",
            "home_assistant_error",
            "camera.demo_camera does not support record service",
        )
        out = service_errors.explain(fake_client, "camera", "record")
        assert out["ok"] is False
        assert out["code"] == "home_assistant_error"
        assert out["message"] == "camera.demo_camera does not support record service"

    def test_transport_prefix_is_stripped(self, fake_client):
        """`ws_call` prefixes with 'WS command call_service failed: <code> '."""
        fake_client.set_ws_error("call_service", "not_found",
                                 "Service vacuum.start_pause not found.")
        out = service_errors.explain(fake_client, "vacuum", "start_pause")
        assert not out["message"].startswith("WS command")

    def test_meaning_is_attached(self, fake_client):
        fake_client.set_ws_error("call_service", "service_validation_error", "nope")
        out = service_errors.explain(fake_client, "media_player", "media_seek")
        assert "supported_features" in out["meaning"]

    def test_unknown_code_has_no_meaning(self, fake_client):
        fake_client.set_ws_error("call_service", "weird_new_code", "nope")
        assert service_errors.explain(fake_client, "x", "y")["meaning"] is None

    def test_no_service_data_key_when_empty(self, fake_client):
        fake_client.set_ws("call_service", {})
        service_errors.explain(fake_client, "homeassistant", "restart")
        assert "service_data" not in fake_client.ws_calls[-1]["payload"]

    def test_requires_both_names(self, fake_client):
        with pytest.raises(ValueError, match="domain and service"):
            service_errors.explain(fake_client, "", "turn_on")


class TestCall:
    def test_happy_path_is_a_plain_post(self, registry_client):
        registry_client.set_service("switch", "turn_on", [{"entity_id": "switch.ac"}])
        out = service_errors.call(
            registry_client, "switch", "turn_on", {"entity_id": "switch.ac"}
        )
        assert out == [{"entity_id": "switch.ac"}]

    def test_400_is_named_as_never_ran(self, registry_client):
        registry_client.set_rest_error(
            "POST", "services/vacuum/start_pause", 400, "400: Bad Request"
        )
        with pytest.raises(HomeAssistantError) as exc:
            service_errors.call(
                registry_client, "vacuum", "start_pause", {"entity_id": "vacuum.a"}
            )
        message = str(exc.value)
        assert "REFUSED BEFORE IT RAN" in message
        assert "NOT in this instance's registry" in message
        assert "return_to_base" in message

    def test_500_is_named_as_handler_raised(self, registry_client):
        registry_client.set_rest_error(
            "POST", "services/switch/turn_on", 500, "Server got itself in trouble"
        )
        with pytest.raises(HomeAssistantError) as exc:
            service_errors.call(
                registry_client, "switch", "turn_on", {"entity_id": "switch.ac"}
            )
        assert "RAN AND ITS HANDLER RAISED" in str(exc.value)

    def test_500_is_never_re_issued(self, registry_client):
        """The handler already ran; a second attempt could repeat a side
        effect. The 500 path must never touch the websocket on its own."""
        registry_client.set_rest_error("POST", "services/switch/turn_on", 500, "")
        with pytest.raises(HomeAssistantError):
            service_errors.call(
                registry_client,
                "switch",
                "turn_on",
                {"entity_id": "switch.ac"},
                explain_failures=True,
            )
        assert registry_client.ws_calls == []

    def test_500_points_at_the_explain_verb(self, registry_client):
        registry_client.set_rest_error("POST", "services/switch/turn_on", 500, "")
        with pytest.raises(HomeAssistantError, match="service explain switch turn_on"):
            service_errors.call(registry_client, "switch", "turn_on", {})

    def test_400_is_re_issued_only_when_asked(self, registry_client):
        registry_client.set_rest_error("POST", "services/switch/turn_on", 400, "")
        with pytest.raises(HomeAssistantError):
            service_errors.call(registry_client, "switch", "turn_on", {})
        assert registry_client.ws_calls == []

    def test_400_explain_adds_has_sentence(self, registry_client):
        registry_client.set_rest_error("POST", "services/switch/turn_on", 400, "")
        registry_client.set_ws_error(
            "call_service", "invalid_format", "Could not parse date"
        )
        with pytest.raises(HomeAssistantError) as exc:
            service_errors.call(
                registry_client,
                "switch",
                "turn_on",
                {"entity_id": "switch.ac"},
                explain_failures=True,
            )
        assert "HA says: Could not parse date [invalid_format]" in str(exc.value)

    def test_unavailable_entity_is_noted(self, registry_client):
        registry_client.set("GET", "states/switch.ac", {
            "entity_id": "switch.ac", "state": "unavailable",
        })
        registry_client.set_rest_error("POST", "services/switch/turn_on", 500, "")
        with pytest.raises(HomeAssistantError, match="currently unavailable"):
            service_errors.call(
                registry_client, "switch", "turn_on", {"entity_id": "switch.ac"}
            )

    def test_missing_entity_is_noted(self, registry_client):
        registry_client.set_rest_error("GET", "states/switch.nope", 404, "")
        registry_client.set_rest_error("POST", "services/switch/turn_on", 500, "")
        with pytest.raises(HomeAssistantError, match="does not exist in the state machine"):
            service_errors.call(
                registry_client, "switch", "turn_on", {"entity_id": "switch.nope"}
            )

    def test_entity_id_list_uses_the_first(self, registry_client):
        registry_client.set_rest_error("GET", "states/switch.nope", 404, "")
        registry_client.set_rest_error("POST", "services/switch/turn_on", 500, "")
        with pytest.raises(HomeAssistantError, match="switch.nope"):
            service_errors.call(
                registry_client,
                "switch",
                "turn_on",
                {"entity_id": ["switch.nope", "switch.ac"]},
            )

    def test_other_statuses_pass_through_untouched(self, registry_client):
        """A 401/404 already says what it means; do not paper over it."""
        registry_client.set_rest_error("POST", "services/switch/turn_on", 404, "nope")
        with pytest.raises(HomeAssistantError) as exc:
            service_errors.call(registry_client, "switch", "turn_on", {})
        assert str(exc.value).endswith("nope")

    def test_status_survives_on_the_replacement_error(self, registry_client):
        registry_client.set_rest_error("POST", "services/switch/turn_on", 500, "")
        with pytest.raises(HomeAssistantError) as exc:
            service_errors.call(registry_client, "switch", "turn_on", {})
        assert exc.value.status == 500

    def test_a_broken_registry_does_not_mask_the_original(self, fake_client):
        """If `/api/services` itself fails, still report the service failure."""
        fake_client.set_rest_error("GET", "services", 500, "")
        fake_client.set_rest_error("POST", "services/switch/turn_on", 400, "")
        with pytest.raises(HomeAssistantError, match="REFUSED BEFORE IT RAN"):
            service_errors.call(fake_client, "switch", "turn_on", {})


class TestRestErrorCarriesStatus:
    """The `status` attribute is what the whole module keys on."""

    def test_fake_client_matches_the_real_one(self, fake_client):
        fake_client.set_rest_error("POST", "services/a/b", 500, "boom")
        with pytest.raises(HomeAssistantError) as exc:
            fake_client.post("services/a/b", {})
        assert exc.value.status == 500
        assert exc.value.code is None

    def test_default_is_none(self):
        assert HomeAssistantError("x").status is None
