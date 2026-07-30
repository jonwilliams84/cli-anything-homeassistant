"""Unit tests for cli_anything.homeassistant.core.config_entries.

Covers the uncovered walk() multi-step flow, error cleanup paths,
disable_entry, and validation branches that the existing suite misses.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import config_entries


class _RecordingClient:
    """Records REST + WS calls and returns canned responses."""

    def __init__(self):
        self.ws_calls: list[dict] = []
        self.get_calls: list[dict] = []
        self.post_calls: list[dict] = []
        self.delete_calls: list[dict] = []
        self._ws_response = None
        self._get_response = {}
        self._post_response = {}
        self._delete_response = {}
        # For walk(): a list of responses to return from post() in order.
        self._post_responses: list = []
        self._post_index = 0

    def set_ws(self, response):
        self._ws_response = response

    def set_post_sequence(self, responses):
        self._post_responses = responses
        self._post_index = 0

    def ws_call(self, msg_type, payload=None):
        self.ws_calls.append({"type": msg_type, "payload": payload})
        return self._ws_response

    def get(self, path, params=None):
        self.get_calls.append({"path": path, "params": params})
        return self._get_response

    def post(self, path, payload=None, params=None):
        self.post_calls.append({"path": path, "payload": payload, "params": params})
        if self._post_responses:
            resp = self._post_responses[self._post_index]
            self._post_index += 1
            if isinstance(resp, Exception):
                raise resp
            return resp
        return self._post_response

    def delete(self, path, params=None):
        self.delete_calls.append({"path": path, "params": params})
        return self._delete_response


# ────────────────────────────────────────────────────────── list / get


class TestListEntries:
    def test_no_domain_sends_none_payload(self):
        client = _RecordingClient()
        client.set_ws([{"entry_id": "e1"}])
        result = config_entries.list_entries(client)
        assert result == [{"entry_id": "e1"}]
        assert client.ws_calls[0] == {"type": "config_entries/get", "payload": None}

    def test_with_domain_sends_domain_payload(self):
        client = _RecordingClient()
        client.set_ws([{"entry_id": "e1", "domain": "hue"}])
        result = config_entries.list_entries(client, domain="hue")
        assert client.ws_calls[0]["payload"] == {"domain": "hue"}

    def test_non_list_response_returns_empty(self):
        client = _RecordingClient()
        client.set_ws({"not": "a list"})
        assert config_entries.list_entries(client) == []


class TestGetEntry:
    def test_requires_entry_id(self):
        with pytest.raises(ValueError, match="entry_id is required"):
            config_entries.get_entry(_RecordingClient(), "")

    def test_returns_matching_entry(self):
        client = _RecordingClient()
        client.set_ws([{"entry_id": "e1"}, {"entry_id": "e2"}])
        result = config_entries.get_entry(client, "e2")
        assert result == {"entry_id": "e2"}

    def test_returns_none_when_not_found(self):
        client = _RecordingClient()
        client.set_ws([{"entry_id": "e1"}])
        assert config_entries.get_entry(client, "nope") is None


# ────────────────────────────────────────────────────────── delete / reload


class TestDeleteEntry:
    def test_requires_entry_id(self):
        with pytest.raises(ValueError, match="entry_id is required"):
            config_entries.delete_entry(_RecordingClient(), "")

    def test_calls_delete_endpoint(self):
        client = _RecordingClient()
        client._delete_response = {"require_restart": True}
        result = config_entries.delete_entry(client, "e1")
        assert result == {"require_restart": True}
        assert client.delete_calls[0]["path"] == "config/config_entries/entry/e1"


class TestReloadEntry:
    def test_requires_entry_id(self):
        with pytest.raises(ValueError, match="entry_id is required"):
            config_entries.reload_entry(_RecordingClient(), "")

    def test_calls_reload_endpoint(self):
        client = _RecordingClient()
        config_entries.reload_entry(client, "e1")
        assert client.post_calls[0]["path"] == "config/config_entries/entry/e1/reload"


# ────────────────────────────────────────────────────────── update


class TestUpdateEntry:
    def test_requires_entry_id(self):
        with pytest.raises(ValueError, match="entry_id is required"):
            config_entries.update_entry(_RecordingClient(), "")

    def test_sends_only_provided_fields(self):
        client = _RecordingClient()
        client.set_ws({"entry_id": "e1"})
        config_entries.update_entry(client, "e1", options={"key": "val"})
        payload = client.ws_calls[0]["payload"]
        assert payload["entry_id"] == "e1"
        assert payload["data"] == {"key": "val"}
        assert "title" not in payload

    def test_sends_title_when_provided(self):
        client = _RecordingClient()
        client.set_ws({})
        config_entries.update_entry(client, "e1", title="New Title")
        payload = client.ws_calls[0]["payload"]
        assert payload["title"] == "New Title"
        assert "data" not in payload

    def test_sends_both_when_provided(self):
        client = _RecordingClient()
        client.set_ws({})
        config_entries.update_entry(client, "e1", options={"k": "v"}, title="T")
        payload = client.ws_calls[0]["payload"]
        assert payload["data"] == {"k": "v"}
        assert payload["title"] == "T"


# ────────────────────────────────────────────────────────── options flow


class TestOptionsFlow:
    def test_init_requires_entry_id(self):
        with pytest.raises(ValueError, match="entry_id is required"):
            config_entries.options_flow_init(_RecordingClient(), "")

    def test_init_posts_handler(self):
        client = _RecordingClient()
        config_entries.options_flow_init(client, "e1")
        assert client.post_calls[0] == {
            "path": "config/config_entries/options/flow",
            "payload": {"handler": "e1"},
            "params": None,
        }

    def test_configure_requires_flow_id(self):
        with pytest.raises(ValueError, match="flow_id is required"):
            config_entries.options_flow_configure(_RecordingClient(), "", {})

    def test_configure_posts_user_input(self):
        client = _RecordingClient()
        config_entries.options_flow_configure(client, "flow-1", {"field": "val"})
        assert client.post_calls[0]["path"] == "config/config_entries/options/flow/flow-1"
        assert client.post_calls[0]["payload"] == {"field": "val"}

    def test_configure_empty_input_sends_empty_dict(self):
        client = _RecordingClient()
        config_entries.options_flow_configure(client, "flow-1", None)
        assert client.post_calls[0]["payload"] == {}

    def test_set_raises_when_no_flow_id(self):
        client = _RecordingClient()
        client._post_response = {"type": "form"}  # no flow_id
        with pytest.raises(ValueError, match="options flow did not return flow_id"):
            config_entries.options_flow_set(client, "e1", {"k": "v"})

    def test_set_init_and_configure(self):
        client = _RecordingClient()
        client.set_post_sequence([
            {"flow_id": "f1", "type": "form"},
            {"type": "create_entry"},
        ])
        result = config_entries.options_flow_set(client, "e1", {"k": "v"})
        assert result == {"type": "create_entry"}
        assert client.post_calls[0]["payload"] == {"handler": "e1"}
        assert client.post_calls[1]["path"] == "config/config_entries/options/flow/f1"
        assert client.post_calls[1]["payload"] == {"k": "v"}


# ────────────────────────────────────────────────────────── config flow


class TestFlowInit:
    def test_requires_handler(self):
        with pytest.raises(ValueError, match="handler is required"):
            config_entries.flow_init(_RecordingClient(), "")

    def test_basic_payload(self):
        client = _RecordingClient()
        config_entries.flow_init(client, "hue")
        assert client.post_calls[0] == {
            "path": "config/config_entries/flow",
            "payload": {"handler": "hue"},
            "params": None,
        }

    def test_show_advanced_options(self):
        client = _RecordingClient()
        config_entries.flow_init(client, "hue", show_advanced_options=True)
        assert client.post_calls[0]["payload"]["show_advanced_options"] is True


class TestFlowConfigure:
    def test_requires_flow_id(self):
        with pytest.raises(ValueError, match="flow_id is required"):
            config_entries.flow_configure(_RecordingClient(), "")

    def test_posts_user_input(self):
        client = _RecordingClient()
        config_entries.flow_configure(client, "f1", {"host": "1.2.3.4"})
        assert client.post_calls[0]["path"] == "config/config_entries/flow/f1"
        assert client.post_calls[0]["payload"] == {"host": "1.2.3.4"}

    def test_none_input_sends_empty_dict(self):
        client = _RecordingClient()
        config_entries.flow_configure(client, "f1", None)
        assert client.post_calls[0]["payload"] == {}


class TestFlowAbort:
    def test_requires_flow_id(self):
        with pytest.raises(ValueError, match="flow_id is required"):
            config_entries.flow_abort(_RecordingClient(), "")

    def test_calls_delete(self):
        client = _RecordingClient()
        config_entries.flow_abort(client, "f1")
        assert client.delete_calls[0]["path"] == "config/config_entries/flow/f1"


class TestFlowGet:
    def test_requires_flow_id(self):
        with pytest.raises(ValueError, match="flow_id is required"):
            config_entries.flow_get(_RecordingClient(), "")

    def test_calls_get(self):
        client = _RecordingClient()
        client._get_response = {"flow_id": "f1", "type": "form"}
        result = config_entries.flow_get(client, "f1")
        assert result == {"flow_id": "f1", "type": "form"}
        assert client.get_calls[0]["path"] == "config/config_entries/flow/f1"


class TestCreate:
    def test_returns_init_when_no_flow_id(self):
        """If flow_init returns a create_entry directly, create returns it."""
        client = _RecordingClient()
        client._post_response = {"type": "create_entry", "title": "Done"}
        result = config_entries.create(client, "hue", {"host": "1.2.3.4"})
        assert result == {"type": "create_entry", "title": "Done"}

    def test_init_then_configure(self):
        client = _RecordingClient()
        client.set_post_sequence([
            {"flow_id": "f1", "type": "form"},
            {"type": "create_entry", "title": "Hue"},
        ])
        result = config_entries.create(client, "hue", {"host": "1.2.3.4"})
        assert result == {"type": "create_entry", "title": "Hue"}


# ────────────────────────────────────────────────────────── walk()


class TestWalk:
    def test_init_returns_create_entry_immediately(self):
        """If flow_init returns create_entry, walk completes without any steps."""
        client = _RecordingClient()
        client._post_response = {"type": "create_entry", "title": "Done"}
        result = config_entries.walk(client, "hue", [{"host": "x"}])
        assert result["completed"] is True
        assert result["final"]["type"] == "create_entry"
        # No flow_configure calls should have been made.
        assert len(client.post_calls) == 1  # only the init

    def test_init_returns_abort_immediately(self):
        client = _RecordingClient()
        client._post_response = {"type": "abort", "reason": "already configured"}
        result = config_entries.walk(client, "hue", [{"host": "x"}])
        assert result["completed"] is True
        assert result["final"]["type"] == "abort"

    def test_init_returns_no_flow_id(self):
        """If init returns something without a flow_id and not a terminal type,
        walk reports incomplete."""
        client = _RecordingClient()
        client._post_response = {"type": "form"}  # no flow_id
        result = config_entries.walk(client, "hue", [{"host": "x"}])
        assert result["completed"] is False
        assert result["flow_id"] is None

    def test_multi_step_completes_on_create_entry(self):
        client = _RecordingClient()
        client.set_post_sequence([
            {"flow_id": "f1", "type": "form", "step_id": "user"},
            {"type": "form", "step_id": "credentials"},
            {"type": "create_entry", "title": "Hue Bridge"},
        ])
        result = config_entries.walk(
            client, "hue",
            [{"host": "1.2.3.4"}, {"username": "u", "password": "p"}],
        )
        assert result["completed"] is True
        assert result["final"]["type"] == "create_entry"
        assert len(result["history"]) == 3

    def test_stop_on_form_returns_incomplete(self):
        client = _RecordingClient()
        client.set_post_sequence([
            {"flow_id": "f1", "type": "form", "step_id": "user"},
            {"type": "form", "step_id": "credentials"},
        ])
        result = config_entries.walk(
            client, "hue",
            [{"host": "1.2.3.4"}],
            stop_on_form=True,
        )
        assert result["completed"] is False
        assert result["final"]["type"] == "form"
        assert result["final"]["step_id"] == "credentials"

    def test_configure_error_aborts_flow_and_returns_error(self):
        """When flow_configure raises, walk aborts the flow and records the error."""
        client = _RecordingClient()
        client.set_post_sequence([
            {"flow_id": "f1", "type": "form", "step_id": "user"},
            RuntimeError("connection reset"),
        ])
        result = config_entries.walk(client, "hue", [{"host": "x"}])
        assert result["completed"] is False
        assert result["final"] is None
        assert "error" in result["history"][-1]
        # flow_abort should have been called via delete.
        assert len(client.delete_calls) == 1
        assert client.delete_calls[0]["path"] == "config/config_entries/flow/f1"

    def test_ran_out_of_steps_incomplete(self):
        """When all steps are consumed but flow isn't done, walk reports incomplete."""
        client = _RecordingClient()
        client.set_post_sequence([
            {"flow_id": "f1", "type": "form", "step_id": "user"},
            {"type": "form", "step_id": "more"},
        ])
        result = config_entries.walk(client, "hue", [{"host": "x"}])
        assert result["completed"] is False
        # final should be the last response.
        assert result["final"]["step_id"] == "more"


# ────────────────────────────────────────────────────────── disable


class TestDisableEntry:
    def test_requires_entry_id(self):
        with pytest.raises(ValueError, match="entry_id is required"):
            config_entries.disable_entry(_RecordingClient(), "")

    def test_disable_sets_user(self):
        client = _RecordingClient()
        client.set_ws({})
        config_entries.disable_entry(client, "e1", disabled=True)
        payload = client.ws_calls[0]["payload"]
        assert payload["entry_id"] == "e1"
        assert payload["disabled_by"] == "user"

    def test_enable_sets_none(self):
        client = _RecordingClient()
        client.set_ws({})
        config_entries.disable_entry(client, "e1", disabled=False)
        payload = client.ws_calls[0]["payload"]
        assert payload["disabled_by"] is None
