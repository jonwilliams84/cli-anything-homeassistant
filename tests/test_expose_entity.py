"""Unit tests for expose_entity module."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import expose_entity


class TestExposeEntity:
    """Tests for expose_entity module functions."""

    def test_list_exposed_all(self, fake_client):
        """Test listing all exposed entities."""
        fake_client.set_ws("homeassistant/expose_entity/list", {
            "exposed_entities": {
                "light.living_room": {"conversation": True, "cloud.alexa": False},
                "switch.kitchen": {"conversation": False},
            }
        })
        result = expose_entity.list_exposed(fake_client)
        assert result == {
            "light.living_room": {"conversation": True, "cloud.alexa": False},
            "switch.kitchen": {"conversation": False},
        }
        assert fake_client.ws_calls[-1]["type"] == "homeassistant/expose_entity/list"
        assert fake_client.ws_calls[-1]["payload"] == {}

    def test_list_exposed_filtered_by_assistant(self, fake_client):
        """Test listing exposed entities filtered by assistant."""
        fake_client.set_ws("homeassistant/expose_entity/list", {
            "exposed_entities": {
                "light.living_room": {"conversation": True, "cloud.alexa": False},
                "switch.kitchen": {"conversation": False},
                "light.bedroom": {"cloud.alexa": True},
            }
        })
        result = expose_entity.list_exposed(fake_client, assistant="conversation")
        assert result == {
            "light.living_room": {"conversation": True},
            "switch.kitchen": {"conversation": False},
        }

    def test_expose_entity_happy_path(self, fake_client):
        """Test exposing an entity to assistants."""
        fake_client.set_ws("homeassistant/expose_entity", {})
        result = expose_entity.expose_entity(
            fake_client,
            assistants=["conversation"],
            entity_ids=["light.living_room"],
            should_expose=True,
        )
        assert result == {}
        assert fake_client.ws_calls[-1]["type"] == "homeassistant/expose_entity"
        assert fake_client.ws_calls[-1]["payload"] == {
            "assistants": ["conversation"],
            "entity_ids": ["light.living_room"],
            "should_expose": True,
        }

    def test_expose_entity_multiple_assistants_and_entities(self, fake_client):
        """Test exposing multiple entities to multiple assistants."""
        fake_client.set_ws("homeassistant/expose_entity", {})
        expose_entity.expose_entity(
            fake_client,
            assistants=["conversation", "cloud.alexa"],
            entity_ids=["light.living_room", "switch.kitchen"],
            should_expose=False,
        )
        assert fake_client.ws_calls[-1]["payload"] == {
            "assistants": ["conversation", "cloud.alexa"],
            "entity_ids": ["light.living_room", "switch.kitchen"],
            "should_expose": False,
        }

    def test_expose_entity_empty_assistants_raises(self, fake_client):
        """Test that empty assistants list raises ValueError."""
        with pytest.raises(ValueError, match="assistants must be a non-empty list"):
            expose_entity.expose_entity(
                fake_client,
                assistants=[],
                entity_ids=["light.living_room"],
                should_expose=True,
            )

    def test_expose_entity_non_list_assistants_raises(self, fake_client):
        """Test that non-list assistants raises ValueError."""
        with pytest.raises(ValueError, match="assistants must be a list"):
            expose_entity.expose_entity(
                fake_client,
                assistants="conversation",
                entity_ids=["light.living_room"],
                should_expose=True,
            )

    def test_expose_entity_empty_entity_ids_raises(self, fake_client):
        """Test that empty entity_ids list raises ValueError."""
        with pytest.raises(ValueError, match="entity_ids must be a non-empty list"):
            expose_entity.expose_entity(
                fake_client,
                assistants=["conversation"],
                entity_ids=[],
                should_expose=True,
            )

    def test_expose_entity_non_list_entity_ids_raises(self, fake_client):
        """Test that non-list entity_ids raises ValueError."""
        with pytest.raises(ValueError, match="entity_ids must be a list"):
            expose_entity.expose_entity(
                fake_client,
                assistants=["conversation"],
                entity_ids="light.living_room",
                should_expose=True,
            )

    def test_get_expose_new_entities_true(self, fake_client):
        """Test getting auto-expose setting when True."""
        fake_client.set_ws("homeassistant/expose_new_entities/get", {
            "expose_new": True,
        })
        result = expose_entity.get_expose_new_entities(
            fake_client, assistant="conversation"
        )
        assert result is True
        assert fake_client.ws_calls[-1]["type"] == "homeassistant/expose_new_entities/get"
        assert fake_client.ws_calls[-1]["payload"] == {"assistant": "conversation"}

    def test_get_expose_new_entities_false(self, fake_client):
        """Test getting auto-expose setting when False."""
        fake_client.set_ws("homeassistant/expose_new_entities/get", {
            "expose_new": False,
        })
        result = expose_entity.get_expose_new_entities(
            fake_client, assistant="cloud.alexa"
        )
        assert result is False

    def test_get_expose_new_entities_missing_key(self, fake_client):
        """Test getting auto-expose with missing expose_new key defaults to False."""
        fake_client.set_ws("homeassistant/expose_new_entities/get", {})
        result = expose_entity.get_expose_new_entities(
            fake_client, assistant="conversation"
        )
        assert result is False

    def test_get_expose_new_entities_empty_assistant_raises(self, fake_client):
        """Test that empty assistant raises ValueError."""
        with pytest.raises(ValueError, match="assistant is required"):
            expose_entity.get_expose_new_entities(fake_client, assistant="")

    def test_get_expose_new_entities_non_string_assistant_raises(self, fake_client):
        """Test that non-string assistant raises ValueError."""
        with pytest.raises(ValueError, match="assistant must be a string"):
            expose_entity.get_expose_new_entities(fake_client, assistant=123)

    def test_set_expose_new_entities_true(self, fake_client):
        """Test setting auto-expose to True."""
        fake_client.set_ws("homeassistant/expose_new_entities/set", {})
        result = expose_entity.set_expose_new_entities(
            fake_client, assistant="conversation", expose_new=True
        )
        assert result == {}
        assert fake_client.ws_calls[-1]["type"] == "homeassistant/expose_new_entities/set"
        assert fake_client.ws_calls[-1]["payload"] == {
            "assistant": "conversation",
            "expose_new": True,
        }

    def test_set_expose_new_entities_false(self, fake_client):
        """Test setting auto-expose to False."""
        fake_client.set_ws("homeassistant/expose_new_entities/set", {})
        expose_entity.set_expose_new_entities(
            fake_client, assistant="cloud.alexa", expose_new=False
        )
        assert fake_client.ws_calls[-1]["payload"] == {
            "assistant": "cloud.alexa",
            "expose_new": False,
        }

    def test_set_expose_new_entities_empty_assistant_raises(self, fake_client):
        """Test that empty assistant raises ValueError."""
        with pytest.raises(ValueError, match="assistant is required"):
            expose_entity.set_expose_new_entities(
                fake_client, assistant="", expose_new=True
            )

    def test_set_expose_new_entities_non_string_assistant_raises(self, fake_client):
        """Test that non-string assistant raises ValueError."""
        with pytest.raises(ValueError, match="assistant must be a string"):
            expose_entity.set_expose_new_entities(
                fake_client, assistant=123, expose_new=True
            )

    def test_list_exposed_return_shape(self, fake_client):
        """Test that list_exposed returns correct shape."""
        fake_client.set_ws("homeassistant/expose_entity/list", {
            "exposed_entities": {
                "light.a": {"conversation": True},
                "light.b": {"conversation": False, "cloud.alexa": True},
            }
        })
        result = expose_entity.list_exposed(fake_client)
        assert isinstance(result, dict)
        for entity_id, settings in result.items():
            assert isinstance(entity_id, str)
            assert isinstance(settings, dict)
            for assistant, exposed in settings.items():
                assert isinstance(assistant, str)
                assert isinstance(exposed, bool)

    def test_expose_entity_return_shape(self, fake_client):
        """Test that expose_entity returns a dict."""
        fake_client.set_ws("homeassistant/expose_entity", {"some": "response"})
        result = expose_entity.expose_entity(
            fake_client,
            assistants=["conversation"],
            entity_ids=["light.a"],
            should_expose=True,
        )
        assert isinstance(result, dict)

    def test_get_expose_new_entities_return_shape(self, fake_client):
        """Test that get_expose_new_entities returns a boolean."""
        fake_client.set_ws("homeassistant/expose_new_entities/get", {
            "expose_new": True,
        })
        result = expose_entity.get_expose_new_entities(
            fake_client, assistant="conversation"
        )
        assert isinstance(result, bool)

    def test_set_expose_new_entities_return_shape(self, fake_client):
        """Test that set_expose_new_entities returns a dict."""
        fake_client.set_ws("homeassistant/expose_new_entities/set", {})
        result = expose_entity.set_expose_new_entities(
            fake_client, assistant="conversation", expose_new=True
        )
        assert isinstance(result, dict)
