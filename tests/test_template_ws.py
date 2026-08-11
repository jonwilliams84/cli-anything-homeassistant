"""Unit tests for `core/template_ws.py`.

Covers the WS `render_template` wrapper: payload construction, the
one-shot subscribe/first-event dance, listener normalization, the
dependency helpers and the non-raising validate path.
"""

from __future__ import annotations

import threading

import pytest

from cli_anything.homeassistant.core import template_ws as tw


LISTENERS = {
    "all": False,
    "entities": ["light.kitchen", "binary_sensor.door"],
    "domains": ["light"],
    "time": False,
}


def _queue_render(client, result=42, listeners=None):
    client.queue_events(
        {"result": result, "listeners": LISTENERS if listeners is None else listeners}
    )
    return client


# ─────────────────────────────────────────────────────────────────── payload

class TestBuildPayload:
    def test_minimal_payload_reports_errors(self):
        assert tw.build_payload("{{ 1 }}") == {"template": "{{ 1 }}", "report_errors": True}

    def test_optional_fields_included(self):
        payload = tw.build_payload(
            "{{ x }}", variables={"x": 1}, strict=True, report_errors=False, timeout=2.5
        )
        assert payload == {
            "template": "{{ x }}",
            "variables": {"x": 1},
            "strict": True,
            "timeout": 2.5,
        }

    def test_empty_variables_omitted(self):
        assert "variables" not in tw.build_payload("{{ 1 }}", variables={})

    @pytest.mark.parametrize("bad", ["", "   ", None, 5])
    def test_rejects_empty_template(self, bad):
        with pytest.raises(ValueError, match="template must be"):
            tw.build_payload(bad)

    def test_rejects_non_mapping_variables(self):
        with pytest.raises(ValueError, match="variables must be a mapping"):
            tw.build_payload("{{ 1 }}", variables=["nope"])

    def test_rejects_non_positive_timeout(self):
        with pytest.raises(ValueError, match="timeout must be"):
            tw.build_payload("{{ 1 }}", timeout=0)


# ─────────────────────────────────────────────────────────────────── render

class TestRender:
    def test_returns_result_and_listeners(self, subscribing_client):
        _queue_render(subscribing_client, result=3)
        out = tw.render(subscribing_client, "{{ 1 + 2 }}")
        assert out["result"] == 3
        assert out["listeners"]["entities"] == ["binary_sensor.door", "light.kitchen"]

    def test_subscribes_with_render_template(self, subscribing_client):
        _queue_render(subscribing_client)
        tw.render(subscribing_client, "{{ 1 }}", variables={"a": 2})
        msg_type, payload = subscribing_client.subscribe_calls[-1]
        assert msg_type == "render_template"
        assert payload["template"] == "{{ 1 }}"
        assert payload["variables"] == {"a": 2}

    def test_native_types_survive(self, subscribing_client):
        _queue_render(subscribing_client, result={"a": [1, 2]})
        assert tw.render(subscribing_client, "{{ x }}")["result"] == {"a": [1, 2]}

    def test_only_first_event_is_used(self, subscribing_client):
        subscribing_client.queue_events(
            {"result": "first", "listeners": LISTENERS},
            {"result": "second", "listeners": LISTENERS},
        )
        assert tw.render(subscribing_client, "{{ 1 }}")["result"] == "first"

    def test_error_event_raises_value_error(self, subscribing_client):
        subscribing_client.queue_events({"error": "boom", "level": "ERROR"})
        with pytest.raises(ValueError, match="template error: boom"):
            tw.render(subscribing_client, "{{ nope() }}")

    def test_missing_listeners_normalized(self, subscribing_client):
        subscribing_client.queue_events({"result": 1})
        assert tw.render(subscribing_client, "{{ 1 }}")["listeners"] == {
            "all": False,
            "entities": [],
            "domains": [],
            "time": False,
        }

    def test_no_event_raises_timeout(self, subscribing_client):
        with pytest.raises(TimeoutError, match="no result"):
            tw.render(subscribing_client, "{{ 1 }}", timeout_seconds=0.2)

    def test_subscribe_error_propagates(self, subscribing_client):
        def boom(*args, **kwargs):
            raise RuntimeError("ws down")

        subscribing_client.ws_subscribe = boom
        with pytest.raises(RuntimeError, match="ws down"):
            tw.render(subscribing_client, "{{ 1 }}", timeout_seconds=1)

    def test_rejects_non_positive_timeout(self, subscribing_client):
        with pytest.raises(ValueError, match="timeout_seconds must be"):
            tw.render(subscribing_client, "{{ 1 }}", timeout_seconds=0)

    def test_render_value_returns_bare_value(self, subscribing_client):
        _queue_render(subscribing_client, result=7)
        assert tw.render_value(subscribing_client, "{{ 7 }}") == 7


# ─────────────────────────────────────────────────────────────────── listeners

class TestListeners:
    def test_normalize_sorts_and_defaults(self):
        out = tw.normalize_listeners({"entities": ["b.b", "a.a"], "all": 1})
        assert out == {"all": True, "entities": ["a.a", "b.b"], "domains": [], "time": False}

    def test_normalize_handles_garbage(self):
        assert tw.normalize_listeners(None)["entities"] == []

    def test_listeners_helper(self, subscribing_client):
        _queue_render(subscribing_client)
        assert tw.listeners(subscribing_client, "{{ 1 }}")["domains"] == ["light"]

    def test_entities_used(self, subscribing_client):
        _queue_render(subscribing_client)
        assert tw.entities_used(subscribing_client, "{{ 1 }}") == [
            "binary_sensor.door",
            "light.kitchen",
        ]


class TestDependsOn:
    def test_direct_entity(self, subscribing_client):
        _queue_render(subscribing_client)
        assert tw.depends_on(subscribing_client, "{{ 1 }}", "light.kitchen") is True

    def test_domain_listener_counts(self, subscribing_client):
        _queue_render(subscribing_client)
        assert tw.depends_on(subscribing_client, "{{ 1 }}", "light.hallway") is True

    def test_all_listener_counts(self, subscribing_client):
        _queue_render(
            subscribing_client,
            listeners={"all": True, "entities": [], "domains": [], "time": False},
        )
        assert tw.depends_on(subscribing_client, "{{ 1 }}", "sensor.anything") is True

    def test_unrelated_entity_is_false(self, subscribing_client):
        _queue_render(subscribing_client)
        assert tw.depends_on(subscribing_client, "{{ 1 }}", "sensor.temp") is False

    def test_rejects_bad_entity_id(self, subscribing_client):
        with pytest.raises(ValueError, match="domain.object_id"):
            tw.depends_on(subscribing_client, "{{ 1 }}", "nodot")


# ─────────────────────────────────────────────────────────────────── validate

class TestValidate:
    def test_valid_template(self, subscribing_client):
        _queue_render(subscribing_client, result="ok")
        out = tw.validate(subscribing_client, "{{ 1 }}")
        assert out["valid"] is True
        assert out["error"] is None
        assert out["result"] == "ok"

    def test_invalid_template_does_not_raise(self, subscribing_client):
        subscribing_client.queue_events({"error": "bad filter", "level": "ERROR"})
        out = tw.validate(subscribing_client, "{{ x | nope }}")
        assert out["valid"] is False
        assert "bad filter" in out["error"]
        assert out["listeners"] is None

    def test_timeout_is_reported_as_invalid(self, subscribing_client):
        out = tw.validate(subscribing_client, "{{ 1 }}", timeout_seconds=0.2)
        assert out["valid"] is False
        assert "no result" in out["error"]


# ─────────────────────────────────────────────────────────────────── watch

class TestWatch:
    def test_streams_events_to_callback(self, subscribing_client):
        subscribing_client.queue_events({"result": 1}, {"result": 2})
        seen = []
        tw.watch(subscribing_client, "{{ 1 }}", seen.append, max_events=2)
        assert seen == [{"result": 1}, {"result": 2}]

    def test_uses_caller_stop_event(self, subscribing_client):
        subscribing_client.queue_events({"result": 1})
        stop = threading.Event()
        tw.watch(subscribing_client, "{{ 1 }}", lambda e: None, stop_event=stop)
        assert subscribing_client.subscribe_calls[-1][0] == "render_template"

    def test_requires_callable(self, subscribing_client):
        with pytest.raises(ValueError, match="on_render"):
            tw.watch(subscribing_client, "{{ 1 }}", "not-callable", max_events=1)

    def test_requires_stop_or_max(self, subscribing_client):
        with pytest.raises(ValueError, match="stop_event or max_events"):
            tw.watch(subscribing_client, "{{ 1 }}", lambda e: None)
