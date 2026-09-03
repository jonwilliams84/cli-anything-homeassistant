"""LIVE end-to-end tests for `onboarding` against a never-onboarded Home Assistant.

WHY THESE EXIST AND THE UNIT TESTS ARE NOT ENOUGH. The fakes in
`test_onboarding.py` were written from the same reading of HA's source as the
client, so they agree with it whether or not that reading is right. Every
status code, every "the step is done anyway" claim and the whole
nothing → owner → token sequence is read back here off a REAL Home Assistant
over a REAL socket.

EACH TEST GETS ITS OWN INSTANCE. `fresh_hass_instance` is function-scoped
because onboarding steps are one-shot AND are marked done before they can
fail — a shared instance would make every test after the first see "already
done" and be unable to tell that from a regression. The cost is one HA boot
per test, which is why there are few of them and each asserts a lot.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

from cli_anything.homeassistant.core import auth_login, auth_tokens, onboarding
from cli_anything.homeassistant.utils.homeassistant_backend import (
    HomeAssistantClient,
    HomeAssistantError,
)


def _resolve_cli() -> list[str]:
    path = shutil.which("cli-anything-homeassistant")
    if path:
        return [path]
    return [sys.executable, "-m", "cli_anything.homeassistant.homeassistant_cli"]


@pytest.fixture
def anon(fresh_hass_instance) -> HomeAssistantClient:
    """A client with NO token — what you actually have on a fresh instance."""
    return HomeAssistantClient(url=fresh_hass_instance["url"], token=None, timeout=30)


class TestFreshInstanceLive:
    def test_status_and_installation_type_before_anything(self, anon):
        state = onboarding.status(anon)
        assert state["onboarded"] is False
        assert state["done"] == []
        assert state["remaining"] == list(onboarding.STEPS)

        info = onboarding.installation_type(anon)
        assert isinstance(info["installation_type"], str) and info["installation_type"]

    def test_auth_login_is_blocked_until_onboarding_finishes(self, anon):
        """THE GAP THIS MODULE CLOSES, PROVEN. Before onboarding there is no
        provider to log in against, so nothing else in this harness works."""
        with pytest.raises(HomeAssistantError, match="onboarding"):
            auth_login.list_providers(anon)

    def test_the_user_step_is_one_shot(self, anon):
        first = onboarding.create_user(
            anon, name="Agent", username="agent", password="test-password"
        )
        assert first["auth_code"] and first["committed"] is True

        with pytest.raises(HomeAssistantError, match="this instance has an owner"):
            onboarding.create_user(
                anon, name="Second", username="second", password="test-password"
            )

    def test_installation_type_closes_after_the_first_step(self, anon):
        """MEASURED: the guard is a non-empty `done` LIST, so ONE step shuts it."""
        assert onboarding.installation_type(anon)["installation_type"]
        onboarding.create_user(anon, name="A", username="a", password="test-password")
        with pytest.raises(HomeAssistantError, match="before onboarding STARTS"):
            onboarding.installation_type(anon)

    def test_the_authenticated_steps_are_401_without_a_token(self, anon):
        with pytest.raises(HomeAssistantError, match="requires a token"):
            onboarding.finish_step(anon, "analytics")


class TestProvisionLive:
    def test_nothing_to_working_token_in_one_call(self, anon):
        result = onboarding.provision(
            anon, name="Agent", username="agent", password="test-password"
        )
        assert result["access_token"]
        assert result["refresh_token"]
        assert result["onboarded"] is True, result["steps"]

        # THE POINT OF ALL OF IT: the token actually authenticates.
        authed = HomeAssistantClient(url=anon.base_url, token=result["access_token"], timeout=30)
        me = auth_tokens.current_user(authed)
        assert me["name"] == "Agent"
        assert me["is_owner"] is True

        # ...and the instance is now a normal one: auth login works.
        providers = auth_login.list_providers(anon)["providers"]
        assert {"homeassistant"} <= {p["type"] for p in providers}

        # ...and the credentials provisioned here are the ones it accepts.
        login = auth_login.login(anon, username="agent", password="test-password")
        assert login["access_token"]

    def test_core_config_reports_committed_even_when_it_fails(self, anon):
        """`core_config` starts google_translate/met/radio_browser/shopping_list
        after marking itself done. On this install at least one cannot import,
        so HA answers 500 — and the step is finished regardless. Whichever way
        it goes, `committed` is true and `provision` did not abort."""
        result = onboarding.provision(
            anon, name="Agent", username="agent", password="test-password"
        )
        core = result["steps"]["core_config"]
        assert core["committed"] is True
        if not core["ok"]:
            assert "500" in str(core["detail"]) or "dependency" in str(core["detail"])
        assert onboarding.status(anon)["steps"]["core_config"] is True

    def test_no_finish_leaves_the_rest_undone(self, anon):
        result = onboarding.provision(
            anon, name="Agent", username="agent", password="test-password", finish=False
        )
        assert result["access_token"]
        assert result["onboarded"] is False
        state = onboarding.status(anon)
        assert state["steps"]["user"] is True
        assert state["steps"]["analytics"] is False


class TestIntegrationStepLive:
    def test_a_long_lived_token_is_refused_and_the_step_is_spent_anyway(self, anon):
        """THE HEADLINE TRAP, PROVEN. `_async_mark_done` runs before the
        credential check, so a refused call still finishes the step."""
        created = onboarding.provision(
            anon,
            name="Agent",
            username="agent",
            password="test-password",
            finish=False,
        )
        authed = HomeAssistantClient(url=anon.base_url, token=created["access_token"], timeout=30)
        llat = auth_tokens.create_long_lived_access_token(authed, client_name="probe-llat")

        assert onboarding.status(anon)["steps"]["integration"] is False
        out = onboarding.finish_integration(anon, token=llat)
        assert out["ok"] is False
        assert out["committed"] is True
        assert "long-lived access token never does" in out["detail"]
        # SPENT. Not retryable, which is why nothing here retries.
        assert onboarding.status(anon)["steps"]["integration"] is True

    def test_a_credential_backed_token_gets_a_second_auth_code(self, anon):
        created = onboarding.provision(
            anon,
            name="Agent",
            username="agent",
            password="test-password",
            finish=False,
        )
        out = onboarding.finish_integration(
            anon, client_id=created["client_id"], token=created["access_token"]
        )
        assert out["ok"] is True
        assert out["auth_code"]
        # ...and that code redeems for a second, independent token.
        tokens = auth_login.exchange_code(
            anon, code=out["auth_code"], client_id=created["client_id"]
        )
        assert tokens["access_token"] != created["access_token"]


class TestOnboardingCliLive:
    def test_provision_through_the_real_cli(self, fresh_hass_instance, tmp_path):
        profile = tmp_path / "profile.json"
        cmd = [
            *_resolve_cli(),
            "--url", fresh_hass_instance["url"],
            "--config", str(profile),
            "--json",
            "onboarding", "provision",
            "--name", "Agent",
            "--username", "agent",
            "--password", "test-password",
            "--save",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        out = json.loads(proc.stdout)
        assert out["onboarded"] is True
        assert out["saved_to"] == str(profile)

        # The saved profile is enough on its own for the next command.
        follow = subprocess.run(
            [*_resolve_cli(), "--config", str(profile), "--json", "auth", "me"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert follow.returncode == 0, follow.stdout + follow.stderr
        assert json.loads(follow.stdout)["name"] == "Agent"

    def test_status_on_a_fresh_instance_through_the_cli(self, fresh_hass_instance):
        proc = subprocess.run(
            [*_resolve_cli(), "--url", fresh_hass_instance["url"], "--json",
             "onboarding", "status"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert json.loads(proc.stdout)["onboarded"] is False
