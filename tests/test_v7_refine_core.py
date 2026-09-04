"""v1.50.0 refine — owner-only credential admin, websocket ping, detect degradation.

Three unrelated-looking additions that share one root: Home Assistant reports a
machine-readable error CODE that this harness used to flatten into a message
string, so nothing could branch on it. `HomeAssistantError.code` carries it now
and these are the first three users.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import core_config as core_config_core
from cli_anything.homeassistant.core import system as system_core
from cli_anything.homeassistant.core import user_admin as user_admin_core
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

from .conftest import FakeClient


# ────────────────────────────────────────────────────── the error code itself


class TestErrorCode:
    def test_code_is_carried(self):
        exc = HomeAssistantError("boom", code="not_logged_in")
        assert exc.code == "not_logged_in"

    def test_code_defaults_to_none_for_rest_failures(self):
        assert HomeAssistantError("GET x -> 500").code is None

    def test_message_is_unchanged_by_the_code(self):
        """Existing tests assert on `str(exc)`; the code must be additive only."""
        assert str(HomeAssistantError("boom", code="x")) == "boom"

    def test_fake_client_reproduces_the_real_message_shape(self):
        client = FakeClient()
        client.set_ws_error("some/cmd", "unauthorized", "Nope")
        with pytest.raises(HomeAssistantError) as excinfo:
            client.ws_call("some/cmd")
        assert str(excinfo.value) == "WS command some/cmd failed: unauthorized Nope"
        assert excinfo.value.code == "unauthorized"


# ─────────────────────────────────────────────── owner-only credential admin


class TestAdminChangePassword:
    def test_payload(self):
        client = FakeClient()
        out = user_admin_core.admin_change_password(client, user_id="abc", password="hunter2")
        assert client.ws_calls == [
            {
                "type": "config/auth_provider/homeassistant/admin_change_password",
                "payload": {"user_id": "abc", "password": "hunter2"},
            }
        ]
        assert out["applied"] is True
        assert out["changed"] == "password"

    def test_no_current_password_is_needed(self):
        """That is the difference from `change_password` — this is a RESET."""
        client = FakeClient()
        user_admin_core.admin_change_password(client, user_id="abc", password="p")
        assert "current_password" not in client.ws_calls[0]["payload"]

    def test_note_warns_tokens_survive(self):
        client = FakeClient()
        out = user_admin_core.admin_change_password(client, user_id="abc", password="p")
        assert "NOT revoked" in out["note"]

    @pytest.mark.parametrize("kwargs", [
        {"user_id": "", "password": "p"},
        {"user_id": "abc", "password": ""},
    ])
    def test_empty_arguments_refused_before_the_call(self, kwargs):
        client = FakeClient()
        with pytest.raises(ValueError, match="non-empty"):
            user_admin_core.admin_change_password(client, **kwargs)
        assert client.ws_calls == []

    def test_unauthorized_says_owner_not_admin(self):
        """The bare code says neither the requirement nor the remedy."""
        client = FakeClient()
        client.set_ws_error(
            "config/auth_provider/homeassistant/admin_change_password", "unauthorized", ""
        )
        with pytest.raises(ValueError, match="OWNER-only"):
            user_admin_core.admin_change_password(client, user_id="abc", password="p")

    def test_user_not_found_names_the_lookup(self):
        client = FakeClient()
        client.set_ws_error(
            "config/auth_provider/homeassistant/admin_change_password", "user_not_found", ""
        )
        with pytest.raises(ValueError, match="user list"):
            user_admin_core.admin_change_password(client, user_id="ghost", password="p")

    def test_credentials_not_found_explains_the_case(self):
        client = FakeClient()
        client.set_ws_error(
            "config/auth_provider/homeassistant/admin_change_password",
            "credentials_not_found",
            "",
        )
        with pytest.raises(ValueError, match="credential-create"):
            user_admin_core.admin_change_password(client, user_id="abc", password="p")

    def test_unrelated_errors_still_propagate(self):
        client = FakeClient()
        client.set_ws_error(
            "config/auth_provider/homeassistant/admin_change_password", "unknown_error", "boom"
        )
        with pytest.raises(HomeAssistantError):
            user_admin_core.admin_change_password(client, user_id="abc", password="p")


class TestAdminChangeUsername:
    def test_payload(self):
        client = FakeClient()
        out = user_admin_core.admin_change_username(client, user_id="abc", username="newname")
        assert client.ws_calls == [
            {
                "type": "config/auth_provider/homeassistant/admin_change_username",
                "payload": {"user_id": "abc", "username": "newname"},
            }
        ]
        assert out["username"] == "newname"

    def test_note_separates_login_from_display_name(self):
        client = FakeClient()
        out = user_admin_core.admin_change_username(client, user_id="abc", username="n")
        assert "display name" in out["note"]

    @pytest.mark.parametrize("kwargs", [
        {"user_id": "", "username": "n"},
        {"user_id": "abc", "username": ""},
    ])
    def test_empty_arguments_refused(self, kwargs):
        client = FakeClient()
        with pytest.raises(ValueError, match="non-empty"):
            user_admin_core.admin_change_username(client, **kwargs)
        assert client.ws_calls == []

    def test_unauthorized_says_owner(self):
        client = FakeClient()
        client.set_ws_error(
            "config/auth_provider/homeassistant/admin_change_username", "unauthorized", ""
        )
        with pytest.raises(ValueError, match="OWNER-only"):
            user_admin_core.admin_change_username(client, user_id="abc", username="n")


# ──────────────────────────────────────────────────────────── websocket ping


class TestPing:
    def test_single_sample(self):
        client = FakeClient()
        client.set_ping(12.345)
        out = system_core.ping(client)
        assert client.ping_calls == 1
        assert out["ok"] is True
        assert out["latency_ms"] == 12.35
        assert out["min_ms"] == out["max_ms"] == 12.35

    def test_multiple_samples_report_the_spread(self):
        client = FakeClient()
        client.set_ping(10.0, 30.0, 20.0)
        out = system_core.ping(client, count=3)
        assert client.ping_calls == 3
        assert out["min_ms"] == 10.0
        assert out["max_ms"] == 30.0
        assert out["avg_ms"] == 20.0
        assert out["samples_ms"] == [10.0, 30.0, 20.0]

    def test_multi_sample_has_no_single_latency(self):
        """One number would hide the spread that made --count worth passing."""
        client = FakeClient()
        client.set_ping(1.0, 2.0)
        assert system_core.ping(client, count=2)["latency_ms"] is None

    def test_count_below_one_is_refused(self):
        client = FakeClient()
        with pytest.raises(ValueError, match="at least 1"):
            system_core.ping(client, count=0)
        assert client.ping_calls == 0

    def test_transport_failure_propagates(self):
        client = FakeClient()
        client.ping_error = HomeAssistantError("Cannot connect")
        with pytest.raises(HomeAssistantError, match="Cannot connect"):
            system_core.ping(client)

    def test_uses_a_fresh_round_trip_per_sample(self):
        client = FakeClient()
        client.set_ping(1.0)
        system_core.ping(client, count=5)
        assert client.ping_calls == 5


# ──────────────────────────────────────────── detect-location degradation


class TestDetectDegradation:
    def test_normal_detection(self):
        client = FakeClient()
        client.set_ws("config/core/detect", {"latitude": 52.0, "longitude": 4.0})
        out = core_config_core.detect(client)
        assert out["detected"] is True
        assert out["lookup_failed"] is False
        assert out["error"] is None

    def test_empty_result_is_a_clean_not_detected(self):
        client = FakeClient()
        client.set_ws("config/core/detect", {})
        out = core_config_core.detect(client)
        assert out["detected"] is False
        assert out["lookup_failed"] is False

    def test_unknown_error_degrades_instead_of_raising(self):
        """HA only converts the failures it anticipated into `{}`; the rest
        escape as `unknown_error`, which is the SAME condition."""
        client = FakeClient()
        client.set_ws_error("config/core/detect", "unknown_error", "Unknown error")
        out = core_config_core.detect(client)
        assert out["detected"] is False
        assert out["lookup_failed"] is True
        assert "unknown_error" in out["error"]
        assert "error-log" in out["note"]

    @pytest.mark.parametrize("code", ["unauthorized", "unknown_command", "invalid_format"])
    def test_other_codes_still_raise(self, code):
        """`unknown_command` means the command is unusable, not the lookup unlucky."""
        client = FakeClient()
        client.set_ws_error("config/core/detect", code, "")
        with pytest.raises(HomeAssistantError):
            core_config_core.detect(client)

    def test_drift_survives_a_failed_lookup(self):
        client = FakeClient()
        client.set("GET", "config", {"latitude": 52.0, "longitude": 4.0, "elevation": 3})
        client.set_ws_error("config/core/detect", "unknown_error", "Unknown error")
        out = core_config_core.drift(client)
        assert out["detected_ok"] is False
        assert out["drifted"] is False
        assert out["mismatches"] == []
        assert "says nothing" in out["note"]
