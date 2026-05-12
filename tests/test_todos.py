"""Unit tests for cli_anything.homeassistant.core.todos — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import todos


ENTITY_ID = "todo.shopping_list"
BAD_ENTITY  = "sensor.temperature"


class TestTodos:
    # ────────────────────────────────────────────────────────── list_items

    def test_list_items_ws_call(self, fake_client):
        """list_items sends todo/item/list with entity_id payload."""
        fake_client.set_ws("todo/item/list", {"items": []})
        todos.list_items(fake_client, ENTITY_ID)
        assert fake_client.ws_calls == [
            {"type": "todo/item/list", "payload": {"entity_id": ENTITY_ID}}
        ]

    def test_list_items_returns_items(self, fake_client):
        """list_items unwraps the HA {items: [...]} envelope."""
        items = [
            {"uid": "abc", "summary": "Milk", "status": "needs_action",
             "due": None, "description": None},
            {"uid": "def", "summary": "Eggs", "status": "completed",
             "due": "2026-05-12", "description": "free range"},
        ]
        fake_client.set_ws("todo/item/list", {"items": items})
        result = todos.list_items(fake_client, ENTITY_ID)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["uid"] == "abc"
        assert result[1]["summary"] == "Eggs"

    def test_list_items_bad_entity_id(self, fake_client):
        with pytest.raises(ValueError, match="expected todo\\.*"):
            todos.list_items(fake_client, BAD_ENTITY)

    # ────────────────────────────────────────────────────────── add_item

    def test_add_item_minimal(self, fake_client):
        """add_item sends minimal POST with entity_id + item fields only."""
        todos.add_item(fake_client, ENTITY_ID, summary="Buy bread")
        assert fake_client.calls[-1] == {
            "verb": "POST",
            "path": "services/todo/add_item",
            "payload": {"entity_id": ENTITY_ID, "item": "Buy bread"},
        }

    def test_add_item_with_optional_fields(self, fake_client):
        """add_item includes due and description when provided."""
        todos.add_item(fake_client, ENTITY_ID, summary="Call dentist",
                       due="2026-05-20", description="Annual checkup")
        payload = fake_client.calls[-1]["payload"]
        assert payload["item"] == "Call dentist"
        assert payload["due"] == "2026-05-20"
        assert payload["description"] == "Annual checkup"

    def test_add_item_bad_entity_id(self, fake_client):
        with pytest.raises(ValueError, match="expected todo\\.*"):
            todos.add_item(fake_client, BAD_ENTITY, summary="x")

    def test_add_item_empty_summary(self, fake_client):
        with pytest.raises(ValueError, match="summary must be a non-empty"):
            todos.add_item(fake_client, ENTITY_ID, summary="")

    # ────────────────────────────────────────────────────────── update_item

    def test_update_item_rename(self, fake_client):
        """update_item sends correct POST when renaming an item."""
        todos.update_item(fake_client, ENTITY_ID, item="Buy bread",
                          rename="Buy sourdough")
        assert fake_client.calls[-1] == {
            "verb": "POST",
            "path": "services/todo/update_item",
            "payload": {
                "entity_id": ENTITY_ID,
                "item": "Buy bread",
                "rename": "Buy sourdough",
            },
        }

    def test_update_item_status(self, fake_client):
        """update_item sends status field when only status is changed."""
        todos.update_item(fake_client, ENTITY_ID, item="abc",
                          status="completed")
        payload = fake_client.calls[-1]["payload"]
        assert payload["status"] == "completed"
        assert "rename" not in payload

    def test_update_item_all_fields(self, fake_client):
        """update_item sends all optional fields when all are provided."""
        todos.update_item(fake_client, ENTITY_ID, item="uid-123",
                          rename="New name", status="needs_action",
                          due="2026-06-01", description="updated note")
        payload = fake_client.calls[-1]["payload"]
        assert payload == {
            "entity_id": ENTITY_ID,
            "item": "uid-123",
            "rename": "New name",
            "status": "needs_action",
            "due": "2026-06-01",
            "description": "updated note",
        }

    def test_update_item_bad_entity_id(self, fake_client):
        with pytest.raises(ValueError, match="expected todo\\.*"):
            todos.update_item(fake_client, BAD_ENTITY, item="x", rename="y")

    def test_update_item_invalid_status(self, fake_client):
        with pytest.raises(ValueError, match="status must be one of"):
            todos.update_item(fake_client, ENTITY_ID, item="x", status="done")

    def test_update_item_no_fields(self, fake_client):
        with pytest.raises(ValueError, match="at least one of"):
            todos.update_item(fake_client, ENTITY_ID, item="x")

    # ────────────────────────────────────────────────────────── remove_item

    def test_remove_item_single(self, fake_client):
        """remove_item with a single string sends that string as item."""
        todos.remove_item(fake_client, ENTITY_ID, item="Buy bread")
        assert fake_client.calls[-1] == {
            "verb": "POST",
            "path": "services/todo/remove_item",
            "payload": {"entity_id": ENTITY_ID, "item": "Buy bread"},
        }

    def test_remove_item_list(self, fake_client):
        """remove_item accepts a list of uid/summary strings."""
        todos.remove_item(fake_client, ENTITY_ID, item=["uid-1", "uid-2"])
        payload = fake_client.calls[-1]["payload"]
        assert payload["item"] == ["uid-1", "uid-2"]

    def test_remove_item_bad_entity_id(self, fake_client):
        with pytest.raises(ValueError, match="expected todo\\.*"):
            todos.remove_item(fake_client, BAD_ENTITY, item="x")

    def test_remove_item_empty_string(self, fake_client):
        with pytest.raises(ValueError, match="non-empty"):
            todos.remove_item(fake_client, ENTITY_ID, item="")

    # ────────────────────────────────────────────────────────── move_item

    def test_move_item_to_top(self, fake_client):
        """move_item without previous_uid omits that key from WS payload."""
        fake_client.set_ws("todo/item/move", {})
        todos.move_item(fake_client, ENTITY_ID, uid="uid-5")
        assert fake_client.ws_calls[-1] == {
            "type": "todo/item/move",
            "payload": {"entity_id": ENTITY_ID, "uid": "uid-5"},
        }

    def test_move_item_after_previous(self, fake_client):
        """move_item with previous_uid includes it in the WS payload."""
        fake_client.set_ws("todo/item/move", {})
        todos.move_item(fake_client, ENTITY_ID, uid="uid-5",
                        previous_uid="uid-3")
        assert fake_client.ws_calls[-1] == {
            "type": "todo/item/move",
            "payload": {
                "entity_id": ENTITY_ID,
                "uid": "uid-5",
                "previous_uid": "uid-3",
            },
        }

    def test_move_item_bad_entity_id(self, fake_client):
        with pytest.raises(ValueError, match="expected todo\\.*"):
            todos.move_item(fake_client, BAD_ENTITY, uid="uid-5")

    def test_move_item_empty_uid(self, fake_client):
        with pytest.raises(ValueError, match="uid must be a non-empty"):
            todos.move_item(fake_client, ENTITY_ID, uid="")

    # ────────────────────────────────────────────── remove_completed_items

    def test_remove_completed_items(self, fake_client):
        """remove_completed_items sends correct POST with entity_id."""
        todos.remove_completed_items(fake_client, ENTITY_ID)
        assert fake_client.calls[-1] == {
            "verb": "POST",
            "path": "services/todo/remove_completed_items",
            "payload": {"entity_id": ENTITY_ID},
        }

    def test_remove_completed_items_bad_entity_id(self, fake_client):
        with pytest.raises(ValueError, match="expected todo\\.*"):
            todos.remove_completed_items(fake_client, BAD_ENTITY)
