"""Unit tests for `core/auth_login.py` — the pre-authentication auth API.

Every expectation here was first MEASURED against a live Home Assistant
2025.1.4 (see the module docstring of `core/auth_login.py`); the fakes below
reproduce what was observed on the wire, not what the docs describe. Where the
two differ — an unknown handler is a 500 and not the documented 404, a wrong
password is a 200 — the measurement wins.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import auth_login
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

CID = "http://fake.local:8123/"
PROVIDERS = {
    "providers": [{"name": "Home Assistant Local", "id": None, "type": "homeassistant"}],
    "preselect_remember_me": True,
}
FORM_STEP = {
    "type": "form",
    "flow_id": "abc123",
    "handler": ["homeassistant", None],
    "step_id": "init",
    "data_schema": [
        {"type": "string", "name": "username", "required": True},
        {"type": "string", "name": "password", "required": True},
    ],
    "errors": {},
}
CREATE_ENTRY = {
    "type": "create_entry",
    "flow_id": "abc123",
    "handler": ["homeassistant", None],
    "result": "authcode-xyz",
}
TOKENS = {
    "access_token": "eyJ-access",
    "token_type": "Bearer",
    "refresh_token": "refresh-abc",
    "expires_in": 1800,
    "ha_auth_provider": "homeassistant",
}


def _happy_login(client):
    client.set_root("GET", "/auth/providers", 200, PROVIDERS)
    client.set_root("POST", "/auth/login_flow", 200, FORM_STEP)
    client.set_root("POST", "/auth/login_flow/abc123", 200, CREATE_ENTRY)
    client.set_root("POST", "/auth/token", 200, TOKENS)


# ─────────────────────────────────────────────────────────── client id rules


class TestValidateClientId:
    """These mirror `indieauth._parse_client_id`; a differential run against
    Home Assistant's own `verify_client_id` agreed on all of them."""

    @pytest.mark.parametrize(
        "client_id",
        [
            "http://localhost:8123/",
            "https://ha.example.com/",
            "http://127.0.0.1:8123/",
            "http://10.0.0.5/",
            "http://192.168.1.2/",
            "http://[::1]:8123/",
            "http://[fd00::1]/",
            "http://example.com",
            "https://x.com/path?q=1",
        ],
    )
    def test_accepts(self, client_id):
        assert auth_login.validate_client_id(client_id) == client_id

    @pytest.mark.parametrize(
        ("client_id", "needle"),
        [
            ("", "cannot be empty"),
            ("not-a-url", "absolute http"),
            ("ftp://x.com/", "absolute http"),
            ("https://x.com/a/../b", "path segments"),
            ("https://x.com/a/./b", "path segments"),
            ("http://x.com/#frag", "fragment"),
            ("http://u:p@x.com/", "username"),
            ("http://x.com:notaport/", "invalid port"),
            ("http://8.8.8.8/", "public IP"),
            ("http://[2001:db8::1]/", "public IP"),
        ],
    )
    def test_rejects_with_the_reason(self, client_id, needle):
        with pytest.raises(ValueError, match=needle):
            auth_login.validate_client_id(client_id)

    def test_public_ip_with_a_port_is_accepted_like_ha_does(self):
        """HA checks `ip_address(parts.netloc)` and netloc INCLUDES the port,
        so a public IP with a port fails to parse as an address, is taken for
        a domain name and is accepted. Refusing it here would reject something
        the server allows."""
        assert auth_login.validate_client_id("http://8.8.8.8:8123/")

    def test_cgnat_is_refused_because_ha_refuses_it(self):
        """100.64.0.0/10 is `is_private` to the stdlib but absent from HA's
        RFC6890 table, so validating with the stdlib property would accept a
        client_id the server rejects with a bare 400."""
        with pytest.raises(ValueError, match="public IP"):
            auth_login.validate_client_id("http://100.64.0.1/")

    def test_default_client_id_gets_a_trailing_slash(self):
        assert auth_login.default_client_id("http://h:8123") == "http://h:8123/"
        assert auth_login.default_client_id("http://h:8123/") == "http://h:8123/"


# ───────────────────────────────────────────────────────────────── discovery


class TestDiscovery:
    def test_oauth_metadata(self, fake_client):
        doc = {"token_endpoint": "/auth/token", "response_types_supported": ["code"]}
        fake_client.set_root("GET", "/.well-known/oauth-authorization-server", 200, doc)
        assert auth_login.oauth_metadata(fake_client) == doc

    def test_metadata_is_fetched_without_a_bearer(self, fake_client):
        fake_client.set_root("GET", "/.well-known/oauth-authorization-server", 200, {})
        auth_login.oauth_metadata(fake_client)
        assert fake_client.root_calls[0]["send_auth"] is False

    def test_list_providers(self, fake_client):
        fake_client.set_root("GET", "/auth/providers", 200, PROVIDERS)
        assert auth_login.list_providers(fake_client)["providers"][0]["type"] == "homeassistant"

    def test_onboarding_required_is_explained(self, fake_client):
        fake_client.set_root(
            "GET",
            "/auth/providers",
            400,
            {"message": "Onboarding not finished", "code": "onboarding_required"},
        )
        with pytest.raises(HomeAssistantError, match="onboarding"):
            auth_login.list_providers(fake_client)

    def test_providers_transport_failure(self, fake_client):
        fake_client.set_root("GET", "/auth/providers", 502, "bad gateway")
        with pytest.raises(HomeAssistantError, match="502"):
            auth_login.list_providers(fake_client)


class TestResolveHandler:
    def test_defaults_to_the_homeassistant_provider(self, fake_client):
        fake_client.set_root(
            "GET",
            "/auth/providers",
            200,
            {"providers": [{"type": "trusted_networks", "id": None}, {"type": "homeassistant", "id": None}]},
        )
        assert auth_login.resolve_handler(fake_client) == ["homeassistant", None]

    def test_falls_back_to_the_first_provider(self, fake_client):
        fake_client.set_root(
            "GET", "/auth/providers", 200, {"providers": [{"type": "command_line", "id": "cl1"}]}
        )
        assert auth_login.resolve_handler(fake_client) == ["command_line", "cl1"]

    def test_selects_by_type_and_id(self, fake_client):
        fake_client.set_root(
            "GET",
            "/auth/providers",
            200,
            {"providers": [{"type": "legacy_api_password", "id": None}, {"type": "homeassistant", "id": "b"}]},
        )
        assert auth_login.resolve_handler(fake_client, provider_type="homeassistant") == [
            "homeassistant",
            "b",
        ]

    def test_unknown_type_lists_what_exists_instead_of_500ing(self, fake_client):
        """An unknown handler reaches HA as a 500 with a text/plain body, so
        the point of resolving first is that the caller gets this instead."""
        fake_client.set_root("GET", "/auth/providers", 200, PROVIDERS)
        with pytest.raises(ValueError, match="homeassistant/None"):
            auth_login.resolve_handler(fake_client, provider_type="nope")

    def test_no_providers_at_all(self, fake_client):
        fake_client.set_root("GET", "/auth/providers", 200, {"providers": []})
        with pytest.raises(HomeAssistantError, match="no usable auth providers"):
            auth_login.resolve_handler(fake_client)


# ─────────────────────────────────────────────────────────────── login flow


class TestStartLoginFlow:
    def test_returns_the_first_step(self, fake_client):
        fake_client.set_root("POST", "/auth/login_flow", 200, FORM_STEP)
        assert auth_login.start_login_flow(fake_client)["flow_id"] == "abc123"

    def test_sends_json_not_a_form(self, fake_client):
        """`/auth/login_flow` is wrapped in RequestDataValidator and answers a
        form body with 400 'Invalid JSON.'."""
        fake_client.set_root("POST", "/auth/login_flow", 200, FORM_STEP)
        auth_login.start_login_flow(fake_client)
        call = fake_client.root_calls[-1]
        assert call["form"] is None
        assert call["json"]["handler"] == ["homeassistant", None]

    def test_redirect_uri_defaults_to_client_id(self, fake_client):
        """Same origin makes `verify_redirect_uri` return early instead of
        fetching the client_id URL over the network."""
        fake_client.set_root("POST", "/auth/login_flow", 200, FORM_STEP)
        auth_login.start_login_flow(fake_client)
        body = fake_client.root_calls[-1]["json"]
        assert body["redirect_uri"] == body["client_id"] == CID

    def test_explicit_redirect_uri_is_kept(self, fake_client):
        fake_client.set_root("POST", "/auth/login_flow", 200, FORM_STEP)
        auth_login.start_login_flow(fake_client, redirect_uri="http://fake.local:8123/cb")
        assert fake_client.root_calls[-1]["json"]["redirect_uri"] == "http://fake.local:8123/cb"

    def test_500_is_reported_as_an_unknown_handler(self, fake_client):
        """MEASURED: `LoginFlowIndexView.post` means to answer 404 'Invalid
        handler specified' but a handler no provider serves escapes as a bare
        500 text/plain instead."""
        fake_client.set_root("POST", "/auth/login_flow", 500, "500 Internal Server Error")
        with pytest.raises(HomeAssistantError, match="UNKNOWN auth provider"):
            auth_login.start_login_flow(fake_client, handler=["nope", None])

    def test_handler_must_be_a_pair(self, fake_client):
        with pytest.raises(ValueError, match="two elements"):
            auth_login.start_login_flow(fake_client, handler=["homeassistant"])

    def test_bad_flow_type(self, fake_client):
        with pytest.raises(ValueError, match="flow_type"):
            auth_login.start_login_flow(fake_client, flow_type="whatever")

    def test_link_user_type_is_passed_through(self, fake_client):
        fake_client.set_root("POST", "/auth/login_flow", 200, FORM_STEP)
        auth_login.start_login_flow(fake_client, flow_type="link_user")
        assert fake_client.root_calls[-1]["json"]["type"] == "link_user"

    def test_bad_client_id_never_reaches_the_wire(self, fake_client):
        with pytest.raises(ValueError, match="absolute http"):
            auth_login.start_login_flow(fake_client, client_id="nope")
        assert fake_client.root_calls == []


class TestAdvanceLoginFlow:
    def test_returns_create_entry_with_the_code(self, fake_client):
        fake_client.set_root("POST", "/auth/login_flow/abc123", 200, CREATE_ENTRY)
        step = auth_login.advance_login_flow(
            fake_client, flow_id="abc123", step_data={"username": "u", "password": "p"}
        )
        assert step["result"] == "authcode-xyz"

    def test_a_wrong_password_is_an_error_even_though_it_is_a_200(self, fake_client):
        """THE CENTRAL TRAP. HA answers a rejected credential with HTTP 200 and
        the same form step, flagged only in `errors.base`."""
        fake_client.set_root(
            "POST", "/auth/login_flow/abc123", 200, {**FORM_STEP, "errors": {"base": "invalid_auth"}}
        )
        with pytest.raises(HomeAssistantError, match="invalid_auth") as exc:
            auth_login.advance_login_flow(
                fake_client, flow_id="abc123", step_data={"username": "u", "password": "bad"}
            )
        assert "IP ban" in str(exc.value)
        assert exc.value.code == "invalid_auth"

    def test_a_wrong_mfa_code_is_also_a_200(self, fake_client):
        fake_client.set_root(
            "POST", "/auth/login_flow/abc123", 200, {**FORM_STEP, "errors": {"base": "invalid_code"}}
        )
        with pytest.raises(HomeAssistantError, match="multi-factor code"):
            auth_login.advance_login_flow(
                fake_client, flow_id="abc123", step_data={"code": "000000"}
            )

    def test_403_explains_the_redirect_uri(self, fake_client):
        fake_client.set_root(
            "POST", "/auth/login_flow/abc123", 403, {"message": "Invalid redirect URI"}
        )
        with pytest.raises(HomeAssistantError, match="accepted the credentials"):
            auth_login.advance_login_flow(
                fake_client, flow_id="abc123", step_data={"username": "u", "password": "p"}
            )

    def test_404_names_the_causes(self, fake_client):
        fake_client.set_root(
            "POST", "/auth/login_flow/gone", 404, {"message": "Invalid flow specified"}
        )
        with pytest.raises(HomeAssistantError, match="different IP"):
            auth_login.advance_login_flow(fake_client, flow_id="gone", step_data={})

    def test_client_id_in_step_data_is_refused(self, fake_client):
        with pytest.raises(ValueError, match="must not contain client_id"):
            auth_login.advance_login_flow(
                fake_client, flow_id="abc123", step_data={"client_id": "x"}
            )

    def test_flow_id_required(self, fake_client):
        with pytest.raises(ValueError, match="flow_id"):
            auth_login.advance_login_flow(fake_client, flow_id="", step_data={})

    def test_arbitrary_fields_pass_through(self, fake_client):
        """The view's schema is `extra=vol.ALLOW_EXTRA`, so a custom provider's
        fields reach it unchanged."""
        fake_client.set_root("POST", "/auth/login_flow/abc123", 200, CREATE_ENTRY)
        auth_login.advance_login_flow(
            fake_client, flow_id="abc123", step_data={"pin": "1234", "device": "kiosk"}
        )
        body = fake_client.root_calls[-1]["json"]
        assert body["pin"] == "1234" and body["device"] == "kiosk"
        assert body["client_id"] == CID


class TestAbortLoginFlow:
    def test_abort(self, fake_client):
        fake_client.set_root("DELETE", "/auth/login_flow/abc123", 200, {"message": "Flow aborted"})
        out = auth_login.abort_login_flow(fake_client, flow_id="abc123")
        assert out == {"flow_id": "abc123", "aborted": True, "message": "Flow aborted"}

    def test_abort_unknown(self, fake_client):
        fake_client.set_root("DELETE", "/auth/login_flow/x", 404, {"message": "Invalid flow"})
        with pytest.raises(HomeAssistantError, match="nothing to abort"):
            auth_login.abort_login_flow(fake_client, flow_id="x")

    def test_flow_id_required(self, fake_client):
        with pytest.raises(ValueError, match="flow_id"):
            auth_login.abort_login_flow(fake_client, flow_id="")


# ─────────────────────────────────────────────────────────────────── tokens


class TestExchangeCode:
    def test_returns_tokens_and_the_client_id_used(self, fake_client):
        fake_client.set_root("POST", "/auth/token", 200, TOKENS)
        out = auth_login.exchange_code(fake_client, code="authcode-xyz")
        assert out["access_token"] == "eyJ-access"
        assert out["client_id"] == CID

    def test_sends_a_form_body_not_json(self, fake_client):
        """`/auth/token` reads `await request.post()`, which only populates
        from a form content type. Sent JSON it answers `unsupported_grant_type`
        — an error naming the wrong cause."""
        fake_client.set_root("POST", "/auth/token", 200, TOKENS)
        auth_login.exchange_code(fake_client, code="c")
        call = fake_client.root_calls[-1]
        assert call["json"] is None
        assert call["form"] == {
            "grant_type": "authorization_code",
            "code": "c",
            "client_id": CID,
        }

    def test_reused_code(self, fake_client):
        fake_client.set_root(
            "POST",
            "/auth/token",
            400,
            {"error": "invalid_request", "error_description": "Invalid code"},
        )
        with pytest.raises(HomeAssistantError, match="Invalid code"):
            auth_login.exchange_code(fake_client, code="used")

    def test_unsupported_grant_type_names_the_real_cause(self, fake_client):
        fake_client.set_root("POST", "/auth/token", 400, {"error": "unsupported_grant_type"})
        with pytest.raises(HomeAssistantError, match="FORM BODY did not parse"):
            auth_login.exchange_code(fake_client, code="c")

    def test_access_denied(self, fake_client):
        fake_client.set_root(
            "POST",
            "/auth/token",
            403,
            {"error": "access_denied", "error_description": "User is not active"},
        )
        with pytest.raises(HomeAssistantError, match="may not log in"):
            auth_login.exchange_code(fake_client, code="c")

    def test_code_required(self, fake_client):
        with pytest.raises(ValueError, match="code is required"):
            auth_login.exchange_code(fake_client, code="")


class TestRefreshAccessToken:
    def test_refresh(self, fake_client):
        fake_client.set_root(
            "POST", "/auth/token", 200, {"access_token": "new", "expires_in": 1800}
        )
        out = auth_login.refresh_access_token(fake_client, refresh_token="r")
        assert out["access_token"] == "new"
        assert fake_client.root_calls[-1]["form"]["grant_type"] == "refresh_token"

    def test_client_id_mismatch_is_explained(self, fake_client):
        """HA compares `refresh_token.client_id != client_id` and answers a
        descriptionless 400 for a mismatch AND for omitting it entirely."""
        fake_client.set_root("POST", "/auth/token", 400, {"error": "invalid_request"})
        with pytest.raises(HomeAssistantError, match="ISSUED to"):
            auth_login.refresh_access_token(fake_client, refresh_token="r")

    def test_revoked_token_is_invalid_grant(self, fake_client):
        fake_client.set_root("POST", "/auth/token", 400, {"error": "invalid_grant"})
        with pytest.raises(HomeAssistantError, match="revoked, or it belongs"):
            auth_login.refresh_access_token(fake_client, refresh_token="r")

    def test_refresh_token_required(self, fake_client):
        with pytest.raises(ValueError, match="refresh_token is required"):
            auth_login.refresh_access_token(fake_client, refresh_token="")


class TestRevokeToken:
    def test_unverified_revoke_says_so(self, fake_client):
        fake_client.set_root("POST", "/auth/revoke", 200, "")
        out = auth_login.revoke_token(fake_client, token="r")
        assert out["revoked"] is True and out["verified"] is False
        assert "RFC 7009" in out["note"]

    def test_sends_a_form_body(self, fake_client):
        fake_client.set_root("POST", "/auth/revoke", 200, "")
        auth_login.revoke_token(fake_client, token="r")
        assert fake_client.root_calls[-1]["form"] == {"token": "r"}

    def test_verify_confirms_via_invalid_grant(self, fake_client):
        fake_client.set_root("POST", "/auth/revoke", 200, "")
        fake_client.set_root("POST", "/auth/token", 400, {"error": "invalid_grant"})
        out = auth_login.revoke_token(fake_client, token="r", verify=True)
        assert out["revoked"] is True and out["verified"] is True

    def test_verify_catches_a_revoke_that_did_nothing(self, fake_client):
        """Revoking an ACCESS token rather than a refresh token: HA looks the
        value up, finds no refresh token, and returns 200 anyway."""
        fake_client.set_root("POST", "/auth/revoke", 200, "")
        fake_client.set_root("POST", "/auth/token", 200, {"access_token": "still-works"})
        out = auth_login.revoke_token(fake_client, token="an-access-token", verify=True)
        assert out["revoked"] is False
        assert "NOT revoked" in out["note"]

    def test_token_required(self, fake_client):
        with pytest.raises(ValueError, match="token is required"):
            auth_login.revoke_token(fake_client, token="")


class TestLinkUser:
    def test_link(self, fake_client):
        fake_client.set_root("POST", "/auth/link_user", 200, {"message": "User linked"})
        assert auth_login.link_user(fake_client, code="c")["linked"] is True

    def test_uses_json_and_keeps_the_bearer(self, fake_client):
        """The one endpoint here with `requires_auth` left at its default, and
        the only one of the three POST shapes that takes JSON."""
        fake_client.set_root("POST", "/auth/link_user", 200, {"message": "User linked"})
        auth_login.link_user(fake_client, code="c")
        call = fake_client.root_calls[-1]
        assert call["send_auth"] is True and call["form"] is None
        assert call["json"] == {"code": "c", "client_id": CID}

    def test_401_names_the_asymmetry(self, fake_client):
        fake_client.set_root("POST", "/auth/link_user", 401, "401: Unauthorized")
        with pytest.raises(HomeAssistantError, match="one auth endpoint that needs"):
            auth_login.link_user(fake_client, code="c")

    def test_bad_code(self, fake_client):
        fake_client.set_root("POST", "/auth/link_user", 400, {"message": "Invalid code"})
        with pytest.raises(HomeAssistantError, match="Invalid code"):
            auth_login.link_user(fake_client, code="c")


# ──────────────────────────────────────────────────────────────── composite


class TestLogin:
    def test_end_to_end(self, fake_client):
        _happy_login(fake_client)
        out = auth_login.login(fake_client, username="agent", password="pw")
        assert out["access_token"] == "eyJ-access"
        assert out["refresh_token"] == "refresh-abc"
        assert out["username"] == "agent"
        assert out["handler"] == ["homeassistant", None]
        assert out["client_id"] == CID

    def test_the_call_sequence(self, fake_client):
        _happy_login(fake_client)
        auth_login.login(fake_client, username="agent", password="pw")
        assert [(c["method"], c["path"]) for c in fake_client.root_calls] == [
            ("GET", "/auth/providers"),
            ("POST", "/auth/login_flow"),
            ("POST", "/auth/login_flow/abc123"),
            ("POST", "/auth/token"),
        ]

    def test_the_whole_flow_runs_without_a_bearer(self, fake_client):
        """The point of the command: it works on an instance you have no token
        for."""
        _happy_login(fake_client)
        auth_login.login(fake_client, username="agent", password="pw")
        assert all(c["send_auth"] is False for c in fake_client.root_calls)

    def test_wrong_password_raises_and_does_not_reach_the_token_endpoint(self, fake_client):
        fake_client.set_root("GET", "/auth/providers", 200, PROVIDERS)
        fake_client.set_root("POST", "/auth/login_flow", 200, FORM_STEP)
        fake_client.set_root(
            "POST", "/auth/login_flow/abc123", 200, {**FORM_STEP, "errors": {"base": "invalid_auth"}}
        )
        with pytest.raises(HomeAssistantError, match="invalid_auth"):
            auth_login.login(fake_client, username="agent", password="bad")
        assert not any(c["path"] == "/auth/token" for c in fake_client.root_calls)

    def test_mfa_step_is_answered_when_a_code_is_given(self, fake_client):
        mfa = {
            "type": "form",
            "flow_id": "abc123",
            "step_id": "mfa",
            "data_schema": [{"type": "string", "name": "code", "required": True}],
            "errors": {},
        }
        fake_client.set_root("GET", "/auth/providers", 200, PROVIDERS)
        fake_client.set_root("POST", "/auth/login_flow", 200, FORM_STEP)
        fake_client.set_root("POST", "/auth/login_flow/abc123", 200, mfa)
        fake_client.set_root("POST", "/auth/login_flow/abc123", 200, CREATE_ENTRY)
        fake_client.set_root("POST", "/auth/token", 200, TOKENS)
        out = auth_login.login(
            fake_client, username="agent", password="pw", mfa_code="123456"
        )
        assert out["access_token"] == "eyJ-access"
        assert out["steps"] == ["init", "mfa"]
        mfa_call = [c for c in fake_client.root_calls if c["path"] == "/auth/login_flow/abc123"][1]
        assert mfa_call["json"]["code"] == "123456"

    def test_mfa_without_a_code_aborts_the_flow_before_raising(self, fake_client):
        """An unfinished flow stays pinned to this IP, so it is cleaned up."""
        mfa = {
            "type": "form",
            "flow_id": "abc123",
            "step_id": "mfa",
            "data_schema": [{"type": "string", "name": "code", "required": True}],
            "errors": {},
        }
        fake_client.set_root("GET", "/auth/providers", 200, PROVIDERS)
        fake_client.set_root("POST", "/auth/login_flow", 200, FORM_STEP)
        fake_client.set_root("POST", "/auth/login_flow/abc123", 200, mfa)
        fake_client.set_root("DELETE", "/auth/login_flow/abc123", 200, {"message": "Flow aborted"})
        with pytest.raises(ValueError, match="multi-factor"):
            auth_login.login(fake_client, username="agent", password="pw")
        assert ("DELETE", "/auth/login_flow/abc123") in [
            (c["method"], c["path"]) for c in fake_client.root_calls
        ]

    def test_mfa_is_detected_from_the_schema_when_the_step_is_named_otherwise(self, fake_client):
        custom = {
            "type": "form",
            "flow_id": "abc123",
            "step_id": "totp_challenge",
            "data_schema": [{"type": "string", "name": "code", "required": True}],
            "errors": {},
        }
        fake_client.set_root("GET", "/auth/providers", 200, PROVIDERS)
        fake_client.set_root("POST", "/auth/login_flow", 200, FORM_STEP)
        fake_client.set_root("POST", "/auth/login_flow/abc123", 200, custom)
        fake_client.set_root("POST", "/auth/login_flow/abc123", 200, CREATE_ENTRY)
        fake_client.set_root("POST", "/auth/token", 200, TOKENS)
        assert auth_login.login(
            fake_client, username="agent", password="pw", mfa_code="9"
        )["access_token"]

    def test_a_provider_needing_no_input_skips_straight_to_the_code(self, fake_client):
        """`trusted_networks` completes at init — the first step is already a
        create_entry, so no credentials are submitted at all."""
        fake_client.set_root(
            "GET", "/auth/providers", 200, {"providers": [{"type": "trusted_networks", "id": None}]}
        )
        fake_client.set_root("POST", "/auth/login_flow", 200, CREATE_ENTRY)
        fake_client.set_root("POST", "/auth/token", 200, TOKENS)
        auth_login.login(fake_client, username="agent", password="pw")
        assert not any(c["path"] == "/auth/login_flow/abc123" for c in fake_client.root_calls)

    def test_an_unsupported_step_aborts_and_explains(self, fake_client):
        weird = {
            "type": "form",
            "flow_id": "abc123",
            "step_id": "pick_a_device",
            "data_schema": [{"type": "string", "name": "device", "required": True}],
            "errors": {},
        }
        fake_client.set_root("GET", "/auth/providers", 200, PROVIDERS)
        fake_client.set_root("POST", "/auth/login_flow", 200, FORM_STEP)
        fake_client.set_root("POST", "/auth/login_flow/abc123", 200, weird)
        fake_client.set_root("DELETE", "/auth/login_flow/abc123", 200, {"message": "Flow aborted"})
        with pytest.raises(HomeAssistantError, match="pick_a_device"):
            auth_login.login(fake_client, username="agent", password="pw")

    def test_create_entry_without_a_code(self, fake_client):
        fake_client.set_root("GET", "/auth/providers", 200, PROVIDERS)
        fake_client.set_root("POST", "/auth/login_flow", 200, FORM_STEP)
        fake_client.set_root(
            "POST", "/auth/login_flow/abc123", 200, {"type": "create_entry", "flow_id": "abc123"}
        )
        with pytest.raises(HomeAssistantError, match="without an authorization code"):
            auth_login.login(fake_client, username="agent", password="pw")

    def test_credentials_required(self, fake_client):
        with pytest.raises(ValueError, match="username and password"):
            auth_login.login(fake_client, username="", password="p")

    def test_the_same_client_id_is_used_at_every_hop(self, fake_client):
        """The refresh grant compares client_id against the one the token was
        issued to, so a flow that drifted between steps would produce a token
        that cannot be refreshed."""
        _happy_login(fake_client)
        out = auth_login.login(
            fake_client, username="agent", password="pw", client_id="https://ha.example.com/"
        )
        used = {
            (c["json"] or c["form"] or {}).get("client_id")
            for c in fake_client.root_calls
            if (c["json"] or c["form"])
        }
        assert used == {"https://ha.example.com/"} == {out["client_id"]}


class TestDescribe:
    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            ({"message": "Invalid client id"}, "Invalid client id"),
            ({"error": "invalid_grant"}, "invalid_grant"),
            ({"error": "e", "error_description": "d"}, "e: d"),
            ("401: Unauthorized", "401: Unauthorized"),
            ("", "(empty body)"),
            ({}, "(empty body)"),
        ],
    )
    def test_shapes(self, body, expected):
        assert auth_login._describe(body) == expected
