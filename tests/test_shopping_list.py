"""Unit tests for cli_anything.homeassistant.core.shopping_list — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import shopping_list


class TestShoppingList:
    # ────────────────────────────────────────────────────────── list_items

    def test_list_items_ws_call(self, fake_client):
        """list_items sends shopping_list/items with no payload."""
        fake_client.set_ws("shopping_list/items", [])
        shopping_list.list_items(fake_client)
        assert fake_client.ws_calls == [
            {"type": "shopping_list/items", "payload": None}
        ]

    def test_list_items_returns_items(self, fake_client):
        """list_items unwraps the HA list response."""
        items = [
            {"id": "abc123", "name": "Milk", "complete": False},
            {"id": "def456", "name": "Eggs", "complete": True},
        ]
        fake_client.set_ws("shopping_list/items", items)
        result = shopping_list.list_items(fake_client)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "abc123"
        assert result[1]["name"] == "Eggs"

    def test_list_items_empty(self, fake_client):
        """list_items returns empty list when response is empty."""
        fake_client.set_ws("shopping_list/items", [])
        result = shopping_list.list_items(fake_client)
        assert result == []

    # ────────────────────────────────────────────────────────── add_item

    def test_add_item_minimal(self, fake_client):
        """add_item sends shopping_list/items/add with name only."""
        item = {"id": "new123", "name": "Bread", "complete": False}
        fake_client.set_ws("shopping_list/items/add", item)
        result = shopping_list.add_item(fake_client, name="Bread")
        assert fake_client.ws_calls[-1] == {
            "type": "shopping_list/items/add",
            "payload": {"name": "Bread"},
        }
        assert result["id"] == "new123"

    def test_add_item_empty_name(self, fake_client):
        with pytest.raises(ValueError, match="name must be a non-empty"):
            shopping_list.add_item(fake_client, name="")

    # ────────────────────────────────────────────────────────── update_item

    def test_update_item_rename(self, fake_client):
        """update_item sends correct WS when renaming an item."""
        updated = {"id": "abc123", "name": "Sourdough", "complete": False}
        fake_client.set_ws("shopping_list/items/update", updated)
        shopping_list.update_item(fake_client, item_id="abc123", name="Sourdough")
        assert fake_client.ws_calls[-1] == {
            "type": "shopping_list/items/update",
            "payload": {"item_id": "abc123", "name": "Sourdough"},
        }

    def test_update_item_complete(self, fake_client):
        """update_item sends correct WS when completing an item."""
        updated = {"id": "abc123", "name": "Milk", "complete": True}
        fake_client.set_ws("shopping_list/items/update", updated)
        shopping_list.update_item(fake_client, item_id="abc123", complete=True)
        assert fake_client.ws_calls[-1] == {
            "type": "shopping_list/items/update",
            "payload": {"item_id": "abc123", "complete": True},
        }

    def test_update_item_both_fields(self, fake_client):
        """update_item sends both name and complete when provided."""
        updated = {"id": "abc123", "name": "Sourdough", "complete": True}
        fake_client.set_ws("shopping_list/items/update", updated)
        shopping_list.update_item(
            fake_client, item_id="abc123", name="Sourdough", complete=True
        )
        assert fake_client.ws_calls[-1] == {
            "type": "shopping_list/items/update",
            "payload": {"item_id": "abc123", "name": "Sourdough", "complete": True},
        }

    def test_update_item_empty_item_id(self, fake_client):
        with pytest.raises(ValueError, match="item_id must be a non-empty"):
            shopping_list.update_item(fake_client, item_id="", name="x")

    def test_update_item_no_fields(self, fake_client):
        with pytest.raises(ValueError, match="at least one of"):
            shopping_list.update_item(fake_client, item_id="abc123")

    # ────────────────────────────────────────────────────────── remove_item

    def test_remove_item(self, fake_client):
        """remove_item sends correct WS with item_id."""
        fake_client.set_ws("shopping_list/items/remove", {})
        shopping_list.remove_item(fake_client, item_id="abc123")
        assert fake_client.ws_calls[-1] == {
            "type": "shopping_list/items/remove",
            "payload": {"item_id": "abc123"},
        }

    def test_remove_item_empty_id(self, fake_client):
        with pytest.raises(ValueError, match="item_id must be a non-empty"):
            shopping_list.remove_item(fake_client, item_id="")

    # ────────────────────────────────────────────────────────── clear_completed

    def test_clear_completed(self, fake_client):
        """clear_completed sends shopping_list/items/clear with no payload."""
        fake_client.set_ws("shopping_list/items/clear", {})
        shopping_list.clear_completed(fake_client)
        assert fake_client.ws_calls[-1] == {
            "type": "shopping_list/items/clear",
            "payload": None,
        }

    # ────────────────────────────────────────────────────────── reorder_items

    def test_reorder_items(self, fake_client):
        """reorder_items sends correct WS with item_ids list."""
        fake_client.set_ws("shopping_list/items/reorder", {})
        shopping_list.reorder_items(
            fake_client, item_ids=["id1", "id2", "id3"]
        )
        assert fake_client.ws_calls[-1] == {
            "type": "shopping_list/items/reorder",
            "payload": {"item_ids": ["id1", "id2", "id3"]},
        }

    def test_reorder_items_empty_list(self, fake_client):
        with pytest.raises(ValueError, match="item_ids must be a non-empty"):
            shopping_list.reorder_items(fake_client, item_ids=[])

    def test_reorder_items_empty_string_id(self, fake_client):
        with pytest.raises(ValueError, match="item_ids must contain only non-empty"):
            shopping_list.reorder_items(fake_client, item_ids=["id1", "", "id3"])
