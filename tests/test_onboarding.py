"""Unit tests for `core/onboarding.py` — the pre-account half of the auth API.

Every status code faked here was first read off a real, never-onboarded Home
Assistant 2025.1.4 over a socket; `tests/test_onboarding_e2e.py` repeats the
whole run live. These pin the behaviour so a regression is caught without
booting HA — in particular the one that shapes the module: EVERY STEP IS
MARKED DONE BEFORE IT CAN FAIL, so `ok` and `committed` are not the same
question.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import onboarding
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

BASE = "/api/onboarding"
CID = "http://fake.local:8123/"


def steps_body(**done):
    """HA's `GET /api/onboarding` answer: one entry per step, in HA's order."""
    return [{"step": s, "done": bool(done.get(s))} for s in onboarding.STEPS]


def root(client, path):
    """Every root_request made to `path`, in order."""
    return [c for c in client.root_calls if c["path"] == path]


# ───────────────────────────────────────────────────────────────── status


class TestStatus:
    def test_fresh_instance(self, fake_client):
        fake_client.set_root("GET", BASE, 200, steps_body())
        out = onboarding.status(fake_client)
        assert out["onboarded"] is False
        assert out["done"] == []
        assert out["remaining"] == list(onboarding.STEPS)

    def test_partly_done(self, fake_client):
        fake_client.set_root("GET", BASE, 200, steps_body(user=True, analytics=True))
        out = onboarding.status(fake_client)
        assert out["onboarded"] is False
        assert out["done"] == ["user", "analytics"]
        assert out["remaining"] == ["core_config", "integration"]

    def test_fully_onboarded(self, fake_client):
        fake_client.set_root("GET", BASE, 200, steps_body(**{s: True for s in onboarding.STEPS}))
        assert onboarding.status(fake_client)["onboarded"] is True

    def test_sends_no_token(self, fake_client):
        """This is the view you call when you have none — do not offer a stale one."""
        fake_client.set_root("GET", BASE, 200, steps_body())
        onboarding.status(fake_client)
        assert root(fake_client, BASE)[0]["send_auth"] is False

    def test_404_names_the_missing_integration(self, fake_client):
        fake_client.set_root("GET", BASE, 404, "404: Not Found")
        with pytest.raises(HomeAssistantError, match="onboarding.*integration is not loaded"):
            onboarding.status(fake_client)

    def test_unexpected_status_is_reported_with_its_body(self, fake_client):
        fake_client.set_root("GET", BASE, 502, {"message": "bad gateway"})
        with pytest.raises(HomeAssistantError, match="bad gateway"):
            onboarding.status(fake_client)


class TestInstallationType:
    def test_reads_the_type(self, fake_client):
        fake_client.set_root(
            "GET", f"{BASE}/installation_type", 200, {"installation_type": "Container"}
        )
        assert onboarding.installation_type(fake_client)["installation_type"] == "Container"

    def test_401_means_onboarding_already_started(self, fake_client):
        """MEASURED: the guard is `if self._data["done"]` — a LIST — so it trips
        after the FIRST step, not when onboarding completes."""
        fake_client.set_root("GET", f"{BASE}/installation_type", 401, "401: Unauthorized")
        with pytest.raises(HomeAssistantError, match="before onboarding STARTS"):
            onboarding.installation_type(fake_client)

    def test_sends_no_token(self, fake_client):
        fake_client.set_root(
            "GET", f"{BASE}/installation_type", 200, {"installation_type": "Core"}
        )
        onboarding.installation_type(fake_client)
        assert root(fake_client, f"{BASE}/installation_type")[0]["send_auth"] is False


# ────────────────────────────────────────────────────────────── create_user


class TestCreateUser:
    def test_creates_and_returns_the_code(self, fake_client):
        fake_client.set_root("POST", f"{BASE}/users", 200, {"auth_code": "AC1"})
        out = onboarding.create_user(
            fake_client, name="Agent", username="agent", password="pw"
        )
        assert out["auth_code"] == "AC1"
        assert out["committed"] is True
        call = root(fake_client, f"{BASE}/users")[0]
        assert call["send_auth"] is False
        assert call["json"] == {
            "name": "Agent",
            "username": "agent",
            "password": "pw",
            "client_id": CID,
            "language": "en",
        }

    def test_language_reaches_the_wire(self, fake_client):
        fake_client.set_root("POST", f"{BASE}/users", 200, {"auth_code": "AC1"})
        onboarding.create_user(
            fake_client, name="A", username="a", password="p", language="nl"
        )
        assert root(fake_client, f"{BASE}/users")[0]["json"]["language"] == "nl"

    def test_every_missing_field_is_named_at_once(self, fake_client):
        """HA's 400 names only the FIRST missing key, and spends the step doing it."""
        with pytest.raises(ValueError) as exc:
            onboarding.create_user(fake_client, name="", username="", password="pw")
        assert "name" in str(exc.value) and "username" in str(exc.value)
        assert fake_client.root_calls == []

    def test_a_bad_client_id_is_refused_before_the_step_is_spent(self, fake_client):
        """The view does NOT validate client_id — /auth/token does, afterwards."""
        with pytest.raises(ValueError, match="client_id"):
            onboarding.create_user(
                fake_client, name="A", username="a", password="p", client_id="not-a-url"
            )
        assert fake_client.root_calls == []

    def test_403_says_the_instance_already_has_an_owner(self, fake_client):
        fake_client.set_root("POST", f"{BASE}/users", 403, {"message": "User step already done"})
        with pytest.raises(HomeAssistantError, match="this instance has an owner"):
            onboarding.create_user(fake_client, name="A", username="a", password="p")

    def test_a_200_with_no_code_is_still_a_failure(self, fake_client):
        fake_client.set_root("POST", f"{BASE}/users", 200, {})
        with pytest.raises(HomeAssistantError, match="Creating the owner account failed"):
            onboarding.create_user(fake_client, name="A", username="a", password="p")


# ────────────────────────────────────────────────────────────── finish_step


class TestFinishStep:
    def test_analytics_ok(self, fake_client):
        fake_client.set_root("POST", f"{BASE}/analytics", 200, {})
        out = onboarding.finish_step(fake_client, "analytics")
        assert out == {"step": "analytics", "ok": True, "committed": True, "detail": None}

    def test_token_override_is_used(self, fake_client):
        fake_client.set_root("POST", f"{BASE}/analytics", 200, {})
        onboarding.finish_step(fake_client, "analytics", token="T1")
        call = root(fake_client, f"{BASE}/analytics")[0]
        assert call["send_auth"] is True
        assert call["auth_token"] == "T1"

    def test_403_is_reported_as_committed_not_raised(self, fake_client):
        """Already-done is an outcome, not an error — the step is finished."""
        fake_client.set_root("POST", f"{BASE}/analytics", 403, {"message": "already done"})
        out = onboarding.finish_step(fake_client, "analytics")
        assert out["ok"] is False and out["committed"] is True

    def test_core_config_500_is_committed_and_explained(self, fake_client):
        """MEASURED: the handler marks itself done, THEN starts google_translate
        et al; an import error there escapes as a bare 500."""
        fake_client.set_root(
            "POST", f"{BASE}/core_config", 500, "500 Internal Server Error\n\nServer got itself in trouble"
        )
        out = onboarding.finish_step(fake_client, "core_config")
        assert out["ok"] is False
        assert out["committed"] is True
        assert "missing dependency on the server" in out["detail"]

    def test_a_500_on_analytics_is_NOT_excused(self, fake_client):
        """Only core_config starts integrations; a 500 anywhere else is real."""
        fake_client.set_root("POST", f"{BASE}/analytics", 500, "boom")
        with pytest.raises(HomeAssistantError, match="do not retry"):
            onboarding.finish_step(fake_client, "analytics")

    def test_401_names_the_token_requirement(self, fake_client):
        fake_client.set_root("POST", f"{BASE}/core_config", 401, "401: Unauthorized")
        with pytest.raises(HomeAssistantError, match="requires a token"):
            onboarding.finish_step(fake_client, "core_config")

    @pytest.mark.parametrize("step", ["user", "integration", "nonsense"])
    def test_refuses_the_steps_it_does_not_own(self, fake_client, step):
        with pytest.raises(ValueError, match="core_config"):
            onboarding.finish_step(fake_client, step)
        assert fake_client.root_calls == []


# ─────────────────────────────────────────────────────── finish_integration


class TestFinishIntegration:
    def test_returns_a_second_auth_code(self, fake_client):
        fake_client.set_root("POST", f"{BASE}/integration", 200, {"auth_code": "AC2"})
        out = onboarding.finish_integration(fake_client)
        assert out["ok"] is True
        assert out["auth_code"] == "AC2"
        assert root(fake_client, f"{BASE}/integration")[0]["json"] == {
            "client_id": CID,
            "redirect_uri": CID,
        }

    def test_redirect_uri_defaults_to_client_id(self, fake_client):
        fake_client.set_root("POST", f"{BASE}/integration", 200, {"auth_code": "AC2"})
        onboarding.finish_integration(fake_client, client_id="http://x.local:8123/")
        body = root(fake_client, f"{BASE}/integration")[0]["json"]
        assert body["redirect_uri"] == body["client_id"] == "http://x.local:8123/"

    def test_llat_403_is_named_and_the_step_is_still_spent(self, fake_client):
        """MEASURED: an LLAT's refresh token has no credential, so this 403s —
        after the step has been marked done."""
        fake_client.set_root(
            "POST", f"{BASE}/integration", 403, {"message": "Credentials for user not available"}
        )
        out = onboarding.finish_integration(fake_client)
        assert out["ok"] is False
        assert out["committed"] is True
        assert out["auth_code"] is None
        assert "long-lived access token never does" in out["detail"]

    def test_an_already_done_403_reads_differently(self, fake_client):
        fake_client.set_root(
            "POST", f"{BASE}/integration", 403, {"message": "Integration step already done"}
        )
        out = onboarding.finish_integration(fake_client)
        assert out["detail"].startswith("already done")

    def test_bad_client_id_is_local(self, fake_client):
        with pytest.raises(ValueError, match="client_id"):
            onboarding.finish_integration(fake_client, client_id="nope")
        assert fake_client.root_calls == []


# ─────────────────────────────────────────────────────────────── provision


def prime_provision(client, *, token_status=200, integration=None, core_config=200):
    client.set_root("GET", "/api/onboarding", 200, steps_body())
    client.set_root("POST", f"{BASE}/users", 200, {"auth_code": "AC1"})
    client.set_root(
        "POST",
        "/auth/token",
        token_status,
        {
            "access_token": "ACCESS",
            "refresh_token": "REFRESH",
            "expires_in": 1800,
            "token_type": "Bearer",
        }
        if token_status == 200
        else {"error": "invalid_request"},
    )
    client.set_root("POST", f"{BASE}/analytics", 200, {})
    client.set_root("POST", f"{BASE}/core_config", core_config, {} if core_config == 200 else "boom")
    if integration is None:
        client.set_root("POST", f"{BASE}/integration", 200, {"auth_code": "AC2"})
    else:
        client.set_root("POST", f"{BASE}/integration", *integration)
    # the closing status read
    client.set_root(
        "GET", "/api/onboarding", 200, steps_body(**{s: True for s in onboarding.STEPS})
    )


class TestProvision:
    def test_happy_path(self, fake_client):
        prime_provision(fake_client)
        out = onboarding.provision(
            fake_client, name="Agent", username="agent", password="pw"
        )
        assert out["access_token"] == "ACCESS"
        assert out["refresh_token"] == "REFRESH"
        assert out["client_id"] == CID
        assert out["onboarded"] is True
        assert all(s["ok"] for s in out["steps"].values())

    def test_the_authenticated_steps_use_the_new_token(self, fake_client):
        """The client was built WITHOUT a token — that is the whole premise."""
        prime_provision(fake_client)
        onboarding.provision(fake_client, name="A", username="a", password="p")
        for path in (f"{BASE}/analytics", f"{BASE}/core_config", f"{BASE}/integration"):
            assert root(fake_client, path)[0]["auth_token"] == "ACCESS", path

    def test_step_order_puts_the_fallible_ones_last(self, fake_client):
        prime_provision(fake_client)
        onboarding.provision(fake_client, name="A", username="a", password="p")
        order = [c["path"] for c in fake_client.root_calls if c["method"] == "POST"]
        assert order == [
            f"{BASE}/users",
            "/auth/token",
            f"{BASE}/analytics",
            f"{BASE}/core_config",
            f"{BASE}/integration",
        ]

    def test_refuses_an_instance_that_already_has_an_owner(self, fake_client):
        fake_client.set_root("GET", "/api/onboarding", 200, steps_body(user=True))
        with pytest.raises(HomeAssistantError, match="already has an owner"):
            onboarding.provision(fake_client, name="A", username="a", password="p")
        # and it did NOT spend the user step finding out
        assert root(fake_client, f"{BASE}/users") == []

    def test_a_failing_core_config_does_not_cost_the_token(self, fake_client):
        prime_provision(fake_client, core_config=500)
        out = onboarding.provision(fake_client, name="A", username="a", password="p")
        assert out["access_token"] == "ACCESS"
        assert out["steps"]["core_config"]["ok"] is False
        assert out["steps"]["core_config"]["committed"] is True
        # the run carried on to the last step
        assert out["steps"]["integration"]["ok"] is True

    def test_a_failing_integration_step_does_not_abort_the_run(self, fake_client):
        prime_provision(
            fake_client,
            integration=(403, {"message": "Credentials for user not available"}),
        )
        out = onboarding.provision(fake_client, name="A", username="a", password="p")
        assert out["access_token"] == "ACCESS"
        assert out["steps"]["integration"]["ok"] is False

    def test_no_finish_stops_after_the_token(self, fake_client):
        prime_provision(fake_client)
        out = onboarding.provision(
            fake_client, name="A", username="a", password="p", finish=False
        )
        assert out["access_token"] == "ACCESS"
        assert out["onboarded"] is False
        assert out["steps_skipped"] == ["core_config", "analytics", "integration"]
        assert root(fake_client, f"{BASE}/analytics") == []

    def test_a_failed_code_exchange_raises(self, fake_client):
        prime_provision(fake_client, token_status=400)
        with pytest.raises(HomeAssistantError):
            onboarding.provision(fake_client, name="A", username="a", password="p")

    def test_the_code_is_exchanged_with_the_same_client_id_as_a_form_body(self, fake_client):
        """The auth-code store is keyed on (client_id, code), and /auth/token
        only reads a FORM body."""
        prime_provision(fake_client)
        onboarding.provision(fake_client, name="A", username="a", password="p")
        token_call = root(fake_client, "/auth/token")[0]
        assert token_call["json"] is None
        assert token_call["form"] == {
            "grant_type": "authorization_code",
            "code": "AC1",
            "client_id": CID,
        }
