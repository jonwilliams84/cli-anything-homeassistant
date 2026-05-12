"""Unit tests for cli_anything.homeassistant.core.user_admin — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import user_admin


class TestUserAdmin:
    # ────────────────────────────────────────────────────────────────────
    # create_user
    # ────────────────────────────────────────────────────────────────────

    def test_create_user_ws_payload(self, fake_client):
        """create_user sends config/auth/create with name."""
        fake_client.set_ws("config/auth/create", {"user": {"id": "u1", "name": "Alice"}})
        user_admin.create_user(fake_client, name="Alice")
        assert fake_client.ws_calls == [
            {"type": "config/auth/create", "payload": {"name": "Alice"}}
        ]

    def test_create_user_with_group_ids(self, fake_client):
        """create_user includes group_ids when provided."""
        fake_client.set_ws("config/auth/create", {"user": {"id": "u1"}})
        user_admin.create_user(fake_client, name="Bob", group_ids=["g1", "g2"])
        call = fake_client.ws_calls[-1]
        assert call["payload"]["group_ids"] == ["g1", "g2"]

    def test_create_user_with_local_only(self, fake_client):
        """create_user includes local_only when provided."""
        fake_client.set_ws("config/auth/create", {"user": {"id": "u2"}})
        user_admin.create_user(fake_client, name="Carol", local_only=True)
        call = fake_client.ws_calls[-1]
        assert call["payload"]["local_only"] is True

    def test_create_user_return_shape(self, fake_client):
        """create_user returns the dict with user record."""
        expected = {"user": {"id": "u3", "name": "Dave", "is_active": True}}
        fake_client.set_ws("config/auth/create", expected)
        result = user_admin.create_user(fake_client, name="Dave")
        assert "user" in result
        assert result["user"]["id"] == "u3"

    def test_create_user_empty_name(self, fake_client):
        """Raises ValueError when name is empty."""
        with pytest.raises(ValueError, match="name"):
            user_admin.create_user(fake_client, name="")

    # ────────────────────────────────────────────────────────────────────
    # update_user
    # ────────────────────────────────────────────────────────────────────

    def test_update_user_name_only(self, fake_client):
        """update_user sends config/auth/update with user_id and name."""
        fake_client.set_ws("config/auth/update", {"user": {"id": "u1", "name": "New"}})
        user_admin.update_user(fake_client, user_id="u1", name="New")
        assert fake_client.ws_calls == [
            {"type": "config/auth/update",
             "payload": {"user_id": "u1", "name": "New"}}
        ]

    def test_update_user_is_active(self, fake_client):
        """update_user includes is_active when provided."""
        fake_client.set_ws("config/auth/update", {"user": {"id": "u2"}})
        user_admin.update_user(fake_client, user_id="u2", is_active=False)
        call = fake_client.ws_calls[-1]
        assert call["payload"]["is_active"] is False

    def test_update_user_group_ids(self, fake_client):
        """update_user includes group_ids when provided."""
        fake_client.set_ws("config/auth/update", {"user": {"id": "u3"}})
        user_admin.update_user(fake_client, user_id="u3", group_ids=["g3"])
        call = fake_client.ws_calls[-1]
        assert call["payload"]["group_ids"] == ["g3"]

    def test_update_user_local_only(self, fake_client):
        """update_user includes local_only when provided."""
        fake_client.set_ws("config/auth/update", {"user": {"id": "u4"}})
        user_admin.update_user(fake_client, user_id="u4", local_only=True)
        call = fake_client.ws_calls[-1]
        assert call["payload"]["local_only"] is True

    def test_update_user_multiple_fields(self, fake_client):
        """update_user can update multiple fields at once."""
        fake_client.set_ws("config/auth/update", {"user": {"id": "u5"}})
        user_admin.update_user(fake_client, user_id="u5", name="Updated",
                             is_active=True, group_ids=["g1"])
        call = fake_client.ws_calls[-1]
        assert call["payload"]["name"] == "Updated"
        assert call["payload"]["is_active"] is True
        assert call["payload"]["group_ids"] == ["g1"]

    def test_update_user_return_shape(self, fake_client):
        """update_user returns the dict with updated user record."""
        expected = {"user": {"id": "u6", "name": "Modified"}}
        fake_client.set_ws("config/auth/update", expected)
        result = user_admin.update_user(fake_client, user_id="u6", name="Modified")
        assert "user" in result
        assert result["user"]["name"] == "Modified"

    def test_update_user_empty_user_id(self, fake_client):
        """Raises ValueError when user_id is empty."""
        with pytest.raises(ValueError, match="user_id"):
            user_admin.update_user(fake_client, user_id="", name="New")

    def test_update_user_no_updateable_fields(self, fake_client):
        """Raises ValueError when no updateable fields are provided."""
        with pytest.raises(ValueError, match="pass at least one"):
            user_admin.update_user(fake_client, user_id="u7")

    # ────────────────────────────────────────────────────────────────────
    # create_credential
    # ────────────────────────────────────────────────────────────────────

    def test_create_credential_ws_payload(self, fake_client):
        """create_credential sends config/auth_provider/homeassistant/create."""
        fake_client.set_ws("config/auth_provider/homeassistant/create", {})
        user_admin.create_credential(fake_client, user_id="u1",
                                     username="alice", password="secret")
        assert fake_client.ws_calls == [
            {"type": "config/auth_provider/homeassistant/create",
             "payload": {"user_id": "u1", "username": "alice",
                        "password": "secret"}}
        ]

    def test_create_credential_return_shape(self, fake_client):
        """create_credential returns the WS response dict."""
        fake_client.set_ws("config/auth_provider/homeassistant/create", {})
        result = user_admin.create_credential(fake_client, user_id="u2",
                                              username="bob", password="pass123")
        assert isinstance(result, dict)

    def test_create_credential_empty_user_id(self, fake_client):
        """Raises ValueError when user_id is empty."""
        with pytest.raises(ValueError, match="user_id"):
            user_admin.create_credential(fake_client, user_id="",
                                        username="alice", password="secret")

    def test_create_credential_empty_username(self, fake_client):
        """Raises ValueError when username is empty."""
        with pytest.raises(ValueError, match="username"):
            user_admin.create_credential(fake_client, user_id="u3",
                                        username="", password="secret")

    def test_create_credential_empty_password(self, fake_client):
        """Raises ValueError when password is empty."""
        with pytest.raises(ValueError, match="password"):
            user_admin.create_credential(fake_client, user_id="u4",
                                        username="carol", password="")

    # ────────────────────────────────────────────────────────────────────
    # delete_credential
    # ────────────────────────────────────────────────────────────────────

    def test_delete_credential_ws_payload(self, fake_client):
        """delete_credential sends config/auth_provider/homeassistant/delete."""
        fake_client.set_ws("config/auth_provider/homeassistant/delete", {})
        user_admin.delete_credential(fake_client, username="alice")
        assert fake_client.ws_calls == [
            {"type": "config/auth_provider/homeassistant/delete",
             "payload": {"username": "alice"}}
        ]

    def test_delete_credential_return_shape(self, fake_client):
        """delete_credential returns the WS response dict."""
        fake_client.set_ws("config/auth_provider/homeassistant/delete", {})
        result = user_admin.delete_credential(fake_client, username="bob")
        assert isinstance(result, dict)

    def test_delete_credential_empty_username(self, fake_client):
        """Raises ValueError when username is empty."""
        with pytest.raises(ValueError, match="username"):
            user_admin.delete_credential(fake_client, username="")

    # ────────────────────────────────────────────────────────────────────
    # change_password
    # ────────────────────────────────────────────────────────────────────

    def test_change_password_ws_payload(self, fake_client):
        """change_password sends config/auth_provider/homeassistant/change_password."""
        fake_client.set_ws("config/auth_provider/homeassistant/change_password", {})
        user_admin.change_password(fake_client, current_password="old",
                                   new_password="new")
        assert fake_client.ws_calls == [
            {"type": "config/auth_provider/homeassistant/change_password",
             "payload": {"current_password": "old", "new_password": "new"}}
        ]

    def test_change_password_return_shape(self, fake_client):
        """change_password returns the WS response dict."""
        fake_client.set_ws("config/auth_provider/homeassistant/change_password", {})
        result = user_admin.change_password(fake_client,
                                            current_password="secret1",
                                            new_password="secret2")
        assert isinstance(result, dict)

    def test_change_password_empty_current(self, fake_client):
        """Raises ValueError when current_password is empty."""
        with pytest.raises(ValueError, match="current_password"):
            user_admin.change_password(fake_client, current_password="",
                                      new_password="new")

    def test_change_password_empty_new(self, fake_client):
        """Raises ValueError when new_password is empty."""
        with pytest.raises(ValueError, match="new_password"):
            user_admin.change_password(fake_client, current_password="old",
                                      new_password="")

    def test_change_password_same_as_current(self, fake_client):
        """Raises ValueError when new_password equals current_password."""
        with pytest.raises(ValueError, match="new_password must differ"):
            user_admin.change_password(fake_client, current_password="same",
                                      new_password="same")
