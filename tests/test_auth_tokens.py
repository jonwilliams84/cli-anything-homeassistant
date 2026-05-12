"""Unit tests for cli_anything.homeassistant.core.auth_tokens — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import auth_tokens


class TestAuthTokens:
    # ────────────────────────────────────────────────────────────────────
    # current_user
    # ────────────────────────────────────────────────────────────────────

    def test_current_user_ws_payload(self, fake_client):
        """current_user sends auth/current_user with empty payload."""
        fake_client.set_ws("auth/current_user", {"id": "u1", "name": "Alice", "is_admin": True})
        auth_tokens.current_user(fake_client)
        assert fake_client.ws_calls == [
            {"type": "auth/current_user", "payload": {}}
        ]

    def test_current_user_return_shape(self, fake_client):
        """current_user returns the dict the WS layer provides."""
        data = {"id": "u1", "name": "Alice", "is_admin": True, "is_owner": False}
        fake_client.set_ws("auth/current_user", data)
        result = auth_tokens.current_user(fake_client)
        assert result["id"] == "u1"
        assert result["name"] == "Alice"
        assert result["is_admin"] is True

    # ────────────────────────────────────────────────────────────────────
    # list_refresh_tokens
    # ────────────────────────────────────────────────────────────────────

    def test_list_refresh_tokens_ws_payload(self, fake_client):
        """list_refresh_tokens sends auth/refresh_tokens with empty payload."""
        fake_client.set_ws("auth/refresh_tokens", [])
        auth_tokens.list_refresh_tokens(fake_client)
        assert fake_client.ws_calls == [
            {"type": "auth/refresh_tokens", "payload": {}}
        ]

    def test_list_refresh_tokens_return_shape(self, fake_client):
        """list_refresh_tokens returns a list from the WS response."""
        tokens = [
            {"id": "rt1", "client_name": "Mobile App", "token_type": "normal"},
            {"id": "rt2", "client_name": "My Script", "token_type": "long_lived_access_token"},
        ]
        fake_client.set_ws("auth/refresh_tokens", tokens)
        result = auth_tokens.list_refresh_tokens(fake_client)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "rt1"

    # ────────────────────────────────────────────────────────────────────
    # create_long_lived_access_token
    # ────────────────────────────────────────────────────────────────────

    def test_create_long_lived_access_token_ws_payload(self, fake_client):
        """create_long_lived_access_token sends correct type and payload."""
        fake_client.set_ws("auth/long_lived_access_token", {"token": "abc123"})
        auth_tokens.create_long_lived_access_token(
            fake_client, client_name="My Script", lifespan=180
        )
        assert fake_client.ws_calls == [
            {
                "type": "auth/long_lived_access_token",
                "payload": {"client_name": "My Script", "lifespan": 180},
            }
        ]

    def test_create_long_lived_access_token_default_lifespan(self, fake_client):
        """Default lifespan of 365 days is sent when not specified."""
        fake_client.set_ws("auth/long_lived_access_token", {"token": "xyz"})
        auth_tokens.create_long_lived_access_token(fake_client, client_name="Bot")
        call = fake_client.ws_calls[-1]
        assert call["payload"]["lifespan"] == 365

    def test_create_long_lived_access_token_return_shape(self, fake_client):
        """Returns dict containing 'token' key."""
        fake_client.set_ws("auth/long_lived_access_token", {"token": "tok-secret"})
        result = auth_tokens.create_long_lived_access_token(
            fake_client, client_name="Tester"
        )
        assert "token" in result
        assert result["token"] == "tok-secret"

    def test_create_long_lived_access_token_empty_client_name(self, fake_client):
        """Raises ValueError when client_name is empty string."""
        with pytest.raises(ValueError, match="client_name"):
            auth_tokens.create_long_lived_access_token(fake_client, client_name="")

    def test_create_long_lived_access_token_zero_lifespan(self, fake_client):
        """Raises ValueError when lifespan is zero."""
        with pytest.raises(ValueError, match="lifespan"):
            auth_tokens.create_long_lived_access_token(
                fake_client, client_name="Bot", lifespan=0
            )

    def test_create_long_lived_access_token_negative_lifespan(self, fake_client):
        """Raises ValueError when lifespan is negative."""
        with pytest.raises(ValueError, match="lifespan"):
            auth_tokens.create_long_lived_access_token(
                fake_client, client_name="Bot", lifespan=-10
            )

    # ────────────────────────────────────────────────────────────────────
    # delete_refresh_token
    # ────────────────────────────────────────────────────────────────────

    def test_delete_refresh_token_ws_payload(self, fake_client):
        """delete_refresh_token sends auth/delete_refresh_token with correct payload."""
        fake_client.set_ws("auth/delete_refresh_token", {})
        auth_tokens.delete_refresh_token(fake_client, refresh_token_id="rt-abc")
        assert fake_client.ws_calls == [
            {
                "type": "auth/delete_refresh_token",
                "payload": {"refresh_token_id": "rt-abc"},
            }
        ]

    def test_delete_refresh_token_empty_id(self, fake_client):
        """Raises ValueError when refresh_token_id is empty."""
        with pytest.raises(ValueError, match="refresh_token_id"):
            auth_tokens.delete_refresh_token(fake_client, refresh_token_id="")

    # ────────────────────────────────────────────────────────────────────
    # delete_all_refresh_tokens
    # ────────────────────────────────────────────────────────────────────

    def test_delete_all_refresh_tokens_ws_payload_defaults(self, fake_client):
        """delete_all_refresh_tokens sends correct defaults (no token_type)."""
        fake_client.set_ws("auth/delete_all_refresh_tokens", {})
        auth_tokens.delete_all_refresh_tokens(fake_client)
        assert fake_client.ws_calls == [
            {
                "type": "auth/delete_all_refresh_tokens",
                "payload": {"delete_current_token": False},
            }
        ]

    def test_delete_all_refresh_tokens_with_token_type(self, fake_client):
        """delete_all_refresh_tokens sends token_type when supplied."""
        fake_client.set_ws("auth/delete_all_refresh_tokens", {})
        auth_tokens.delete_all_refresh_tokens(
            fake_client,
            delete_current_token=True,
            token_type="long_lived_access_token",
        )
        call = fake_client.ws_calls[-1]
        assert call["payload"] == {
            "delete_current_token": True,
            "token_type": "long_lived_access_token",
        }

    def test_delete_all_refresh_tokens_invalid_token_type(self, fake_client):
        """Raises ValueError for an unrecognised token_type."""
        with pytest.raises(ValueError, match="token_type"):
            auth_tokens.delete_all_refresh_tokens(
                fake_client, token_type="unknown_type"
            )

    def test_delete_all_refresh_tokens_valid_token_types(self, fake_client):
        """All three valid token_type values are accepted without error."""
        fake_client.set_ws("auth/delete_all_refresh_tokens", {})
        for tt in ("normal", "system", "long_lived_access_token"):
            auth_tokens.delete_all_refresh_tokens(fake_client, token_type=tt)
        assert len(fake_client.ws_calls) == 3

    # ────────────────────────────────────────────────────────────────────
    # set_refresh_token_expiry
    # ────────────────────────────────────────────────────────────────────

    def test_set_refresh_token_expiry_ws_payload_enable(self, fake_client):
        """set_refresh_token_expiry sends correct payload when enabling expiry."""
        fake_client.set_ws("auth/refresh_token_set_expiry", {})
        auth_tokens.set_refresh_token_expiry(
            fake_client, refresh_token_id="rt-123", enable_expiry=True
        )
        assert fake_client.ws_calls == [
            {
                "type": "auth/refresh_token_set_expiry",
                "payload": {"refresh_token_id": "rt-123", "enable_expiry": True},
            }
        ]

    def test_set_refresh_token_expiry_ws_payload_disable(self, fake_client):
        """set_refresh_token_expiry sends correct payload when disabling expiry."""
        fake_client.set_ws("auth/refresh_token_set_expiry", {})
        auth_tokens.set_refresh_token_expiry(
            fake_client, refresh_token_id="rt-123", enable_expiry=False
        )
        call = fake_client.ws_calls[-1]
        assert call["payload"]["enable_expiry"] is False

    def test_set_refresh_token_expiry_return_shape(self, fake_client):
        """set_refresh_token_expiry returns the WS response dict."""
        fake_client.set_ws("auth/refresh_token_set_expiry", {"success": True})
        result = auth_tokens.set_refresh_token_expiry(
            fake_client, refresh_token_id="rt-x", enable_expiry=True
        )
        assert isinstance(result, dict)

    def test_set_refresh_token_expiry_empty_id(self, fake_client):
        """Raises ValueError when refresh_token_id is empty."""
        with pytest.raises(ValueError, match="refresh_token_id"):
            auth_tokens.set_refresh_token_expiry(
                fake_client, refresh_token_id="", enable_expiry=True
            )

    # ────────────────────────────────────────────────────────────────────
    # sign_path
    # ────────────────────────────────────────────────────────────────────

    def test_sign_path_ws_payload(self, fake_client):
        """sign_path sends auth/sign_path with path and expires."""
        fake_client.set_ws("auth/sign_path", {"path": "/api/camera_proxy/...?authSig=x"})
        auth_tokens.sign_path(fake_client, path="/api/camera_proxy/camera.front_door", expires=60)
        assert fake_client.ws_calls == [
            {
                "type": "auth/sign_path",
                "payload": {
                    "path": "/api/camera_proxy/camera.front_door",
                    "expires": 60,
                },
            }
        ]

    def test_sign_path_default_expires(self, fake_client):
        """sign_path uses 30-second default when expires is not supplied."""
        fake_client.set_ws("auth/sign_path", {"path": "/api/tts_proxy/...?authSig=y"})
        auth_tokens.sign_path(fake_client, path="/api/tts_proxy/file.mp3")
        call = fake_client.ws_calls[-1]
        assert call["payload"]["expires"] == 30

    def test_sign_path_return_shape(self, fake_client):
        """sign_path returns a dict containing the 'path' key."""
        signed = {"path": "/api/camera_proxy/camera.front_door?authSig=abc"}
        fake_client.set_ws("auth/sign_path", signed)
        result = auth_tokens.sign_path(fake_client, path="/api/camera_proxy/camera.front_door")
        assert "path" in result
        assert "authSig" in result["path"]

    def test_sign_path_empty_path(self, fake_client):
        """Raises ValueError when path is empty."""
        with pytest.raises(ValueError, match="path"):
            auth_tokens.sign_path(fake_client, path="")

    def test_sign_path_zero_expires(self, fake_client):
        """Raises ValueError when expires is zero."""
        with pytest.raises(ValueError, match="expires"):
            auth_tokens.sign_path(fake_client, path="/api/something", expires=0)

    def test_sign_path_negative_expires(self, fake_client):
        """Raises ValueError when expires is negative."""
        with pytest.raises(ValueError, match="expires"):
            auth_tokens.sign_path(fake_client, path="/api/something", expires=-5)
