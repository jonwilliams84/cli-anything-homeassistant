"""Unit tests for cli_anything.homeassistant.core.categories.

All tests use FakeClient (auto-injected via the `fake_client` fixture from
conftest.py).  No real Home Assistant instance is required.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import categories as cats


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

_SAMPLE_CAT = {
    "category_id": "cat-001",
    "name": "Morning Routines",
    "icon": "mdi:weather-sunrise",
    "created_at": 1700000000.0,
    "modified_at": 1700000000.0,
}


# ════════════════════════════════════════════════════════════════════════════
# Test class
# ════════════════════════════════════════════════════════════════════════════

class TestCategories:

    # ────────────────────────────────────────────────────────────────────────
    # list_categories — happy path
    # ────────────────────────────────────────────────────────────────────────

    def test_list_categories_happy_path(self, fake_client):
        """list_categories issues correct WS type and passes scope."""
        fake_client.set_ws("config/category_registry/list", [_SAMPLE_CAT])

        result = cats.list_categories(fake_client, scope="automation")

        assert len(fake_client.ws_calls) == 1
        call = fake_client.ws_calls[0]
        assert call["type"] == "config/category_registry/list"
        assert call["payload"] == {"scope": "automation"}

    def test_list_categories_return_shape(self, fake_client):
        """list_categories returns a list of dicts with expected keys."""
        fake_client.set_ws("config/category_registry/list", [_SAMPLE_CAT])

        result = cats.list_categories(fake_client, scope="script")

        assert isinstance(result, list)
        assert len(result) == 1
        record = result[0]
        assert record["category_id"] == "cat-001"
        assert record["name"] == "Morning Routines"
        assert record["icon"] == "mdi:weather-sunrise"

    def test_list_categories_empty_scope_raises(self, fake_client):
        with pytest.raises(ValueError, match="scope"):
            cats.list_categories(fake_client, scope="")

    def test_list_categories_none_scope_raises(self, fake_client):
        with pytest.raises(ValueError, match="scope"):
            cats.list_categories(fake_client, scope=None)  # type: ignore[arg-type]

    # ────────────────────────────────────────────────────────────────────────
    # create_category — happy path
    # ────────────────────────────────────────────────────────────────────────

    def test_create_category_happy_path(self, fake_client):
        """create_category sends correct WS payload with scope, name, icon."""
        fake_client.set_ws("config/category_registry/create", _SAMPLE_CAT)

        result = cats.create_category(
            fake_client,
            scope="automation",
            name="Morning Routines",
            icon="mdi:weather-sunrise",
        )

        assert len(fake_client.ws_calls) == 1
        call = fake_client.ws_calls[0]
        assert call["type"] == "config/category_registry/create"
        assert call["payload"]["scope"] == "automation"
        assert call["payload"]["name"] == "Morning Routines"
        assert call["payload"]["icon"] == "mdi:weather-sunrise"

    def test_create_category_without_icon(self, fake_client):
        """create_category omits icon key when not provided."""
        fake_client.set_ws("config/category_registry/create", _SAMPLE_CAT)

        cats.create_category(fake_client, scope="script", name="Utilities")

        payload = fake_client.ws_calls[0]["payload"]
        assert "icon" not in payload
        assert payload["name"] == "Utilities"

    def test_create_category_empty_scope_raises(self, fake_client):
        with pytest.raises(ValueError, match="scope"):
            cats.create_category(fake_client, scope="", name="X")

    def test_create_category_empty_name_raises(self, fake_client):
        with pytest.raises(ValueError, match="name"):
            cats.create_category(fake_client, scope="automation", name="")

    # ────────────────────────────────────────────────────────────────────────
    # update_category — happy path
    # ────────────────────────────────────────────────────────────────────────

    def test_update_category_happy_path(self, fake_client):
        """update_category sends correct WS payload."""
        updated = {**_SAMPLE_CAT, "name": "Evening Routines"}
        fake_client.set_ws("config/category_registry/update", updated)

        result = cats.update_category(
            fake_client,
            scope="automation",
            category_id="cat-001",
            name="Evening Routines",
        )

        assert len(fake_client.ws_calls) == 1
        call = fake_client.ws_calls[0]
        assert call["type"] == "config/category_registry/update"
        assert call["payload"]["scope"] == "automation"
        assert call["payload"]["category_id"] == "cat-001"
        assert call["payload"]["name"] == "Evening Routines"
        assert "icon" not in call["payload"]

    def test_update_category_with_icon(self, fake_client):
        """update_category includes icon when provided."""
        fake_client.set_ws("config/category_registry/update", _SAMPLE_CAT)

        cats.update_category(
            fake_client,
            scope="script",
            category_id="cat-001",
            icon="mdi:star",
        )

        payload = fake_client.ws_calls[0]["payload"]
        assert payload["icon"] == "mdi:star"
        assert "name" not in payload

    def test_update_category_empty_scope_raises(self, fake_client):
        with pytest.raises(ValueError, match="scope"):
            cats.update_category(fake_client, scope="", category_id="cat-001",
                                 name="X")

    def test_update_category_empty_category_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="category_id"):
            cats.update_category(fake_client, scope="automation",
                                 category_id="", name="X")

    def test_update_category_no_fields_raises(self, fake_client):
        """update_category requires at least name or icon."""
        with pytest.raises(ValueError, match="at least one"):
            cats.update_category(
                fake_client,
                scope="automation",
                category_id="cat-001",
            )

    # ────────────────────────────────────────────────────────────────────────
    # delete_category — happy path
    # ────────────────────────────────────────────────────────────────────────

    def test_delete_category_happy_path(self, fake_client):
        """delete_category sends correct WS payload."""
        fake_client.set_ws("config/category_registry/delete", None)

        cats.delete_category(fake_client, scope="automation",
                             category_id="cat-001")

        assert len(fake_client.ws_calls) == 1
        call = fake_client.ws_calls[0]
        assert call["type"] == "config/category_registry/delete"
        assert call["payload"] == {"scope": "automation", "category_id": "cat-001"}

    def test_delete_category_empty_scope_raises(self, fake_client):
        with pytest.raises(ValueError, match="scope"):
            cats.delete_category(fake_client, scope="", category_id="cat-001")

    def test_delete_category_empty_category_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="category_id"):
            cats.delete_category(fake_client, scope="automation", category_id="")

    # ────────────────────────────────────────────────────────────────────────
    # categories_by_name — happy path + return shape
    # ────────────────────────────────────────────────────────────────────────

    def test_categories_by_name_happy_path(self, fake_client):
        """categories_by_name calls list_categories and returns name-keyed dict."""
        cat2 = {**_SAMPLE_CAT, "category_id": "cat-002", "name": "Evening Routines",
                "icon": "mdi:weather-sunset"}
        fake_client.set_ws("config/category_registry/list", [_SAMPLE_CAT, cat2])

        result = cats.categories_by_name(fake_client, scope="automation")

        # Verify WS call was made correctly
        assert len(fake_client.ws_calls) == 1
        call = fake_client.ws_calls[0]
        assert call["type"] == "config/category_registry/list"
        assert call["payload"]["scope"] == "automation"

    def test_categories_by_name_return_shape(self, fake_client):
        """categories_by_name returns {name: full_record} mapping."""
        cat2 = {**_SAMPLE_CAT, "category_id": "cat-002", "name": "Evening Routines",
                "icon": "mdi:weather-sunset"}
        fake_client.set_ws("config/category_registry/list", [_SAMPLE_CAT, cat2])

        result = cats.categories_by_name(fake_client, scope="automation")

        assert isinstance(result, dict)
        assert set(result.keys()) == {"Morning Routines", "Evening Routines"}
        assert result["Morning Routines"]["category_id"] == "cat-001"
        assert result["Evening Routines"]["category_id"] == "cat-002"

    def test_categories_by_name_empty_scope_raises(self, fake_client):
        """categories_by_name propagates scope validation from list_categories."""
        with pytest.raises(ValueError, match="scope"):
            cats.categories_by_name(fake_client, scope="")
