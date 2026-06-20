"""Unit tests for the persistent ``input_select_update`` helper.

Covers the storage-collection WS update and, in particular, the name/icon
backfill that lets callers change *just* the options — HA's
``input_select/update`` REPLACES the whole item and requires ``name``, so a
naive options-only update is rejected. See `helpers.input_select_update`.
"""
from __future__ import annotations

import pytest

from tests.conftest import FakeClient
from cli_anything.homeassistant.core import helpers


def _client_with_state(name="Voice Persona", icon="mdi:account-voice"):
    c = FakeClient()
    c.set("GET", "states/input_select.voice_persona", {
        "entity_id": "input_select.voice_persona",
        "state": "Attenborough",
        "attributes": {"friendly_name": name, "icon": icon,
                       "options": ["Attenborough"]},
    })
    c.set_ws("input_select/update", {"id": "voice_persona", "name": name,
                                     "icon": icon, "options": []})
    return c


def test_update_backfills_name_and_icon_for_options_only():
    """Options-only update must still send name+icon (HA requires name)."""
    c = _client_with_state()
    helpers.input_select_update(
        c, "input_select.voice_persona",
        options=["Alexa", "Attenborough", "Crabtree"],
    )
    assert len(c.ws_calls) == 1
    call = c.ws_calls[0]
    assert call["type"] == "input_select/update"
    p = call["payload"]
    assert p["input_select_id"] == "voice_persona"
    assert p["options"] == ["Alexa", "Attenborough", "Crabtree"]
    # backfilled from current state so HA doesn't reject / drop them
    assert p["name"] == "Voice Persona"
    assert p["icon"] == "mdi:account-voice"


def test_update_explicit_name_overrides_backfill():
    c = _client_with_state()
    helpers.input_select_update(
        c, "input_select.voice_persona", options=["A"], name="Custom Name",
    )
    assert c.ws_calls[0]["payload"]["name"] == "Custom Name"
    # state was not consulted for name, but icon backfill still happened
    assert c.ws_calls[0]["payload"]["icon"] == "mdi:account-voice"


def test_update_wrong_domain_raises():
    c = FakeClient()
    with pytest.raises(ValueError, match="input_select"):
        helpers.input_select_update(c, "select.bad", options=["A"])
    assert c.ws_calls == []


def test_update_nothing_to_change_raises():
    c = FakeClient()
    with pytest.raises(ValueError, match="nothing to update"):
        helpers.input_select_update(c, "input_select.voice_persona")
    assert c.ws_calls == []


def test_update_empty_options_list_raises():
    c = _client_with_state()
    with pytest.raises(ValueError, match="non-empty"):
        helpers.input_select_update(c, "input_select.voice_persona", options=[])
