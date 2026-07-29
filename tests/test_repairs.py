"""Unit tests for cli_anything.homeassistant.core.repairs — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import repairs


class TestListIssues:
    def test_returns_all_non_dismissed_by_default(self, fake_client):
        fake_client.set_ws("repairs/list_issues", {
            "issues": [
                {"issue_id": "a", "severity": "error", "domain": "light"},
                {"issue_id": "b", "severity": "warning", "domain": "switch",
                 "dismissed_version": "2024.1"},
                {"issue_id": "c", "severity": "error", "domain": "sensor"},
            ]
        })
        rows = repairs.list_issues(fake_client)
        ids = [r["issue_id"] for r in rows]
        assert "b" not in ids
        assert set(ids) == {"a", "c"}

    def test_include_dismissed_returns_everything(self, fake_client):
        fake_client.set_ws("repairs/list_issues", {
            "issues": [
                {"issue_id": "a", "severity": "error", "domain": "light"},
                {"issue_id": "b", "dismissed_version": "2024.1"},
            ]
        })
        rows = repairs.list_issues(fake_client, include_dismissed=True)
        assert {r["issue_id"] for r in rows} == {"a", "b"}

    def test_filter_by_severity(self, fake_client):
        fake_client.set_ws("repairs/list_issues", {
            "issues": [
                {"issue_id": "a", "severity": "error", "domain": "light"},
                {"issue_id": "b", "severity": "warning", "domain": "switch"},
                {"issue_id": "c", "severity": "error", "domain": "sensor"},
            ]
        })
        rows = repairs.list_issues(fake_client, severity="warning")
        assert [r["issue_id"] for r in rows] == ["b"]

    def test_filter_by_domain(self, fake_client):
        fake_client.set_ws("repairs/list_issues", {
            "issues": [
                {"issue_id": "a", "severity": "error", "domain": "light"},
                {"issue_id": "b", "severity": "warning", "domain": "switch"},
            ]
        })
        rows = repairs.list_issues(fake_client, domain="switch")
        assert [r["issue_id"] for r in rows] == ["b"]

    def test_filter_by_severity_and_domain(self, fake_client):
        fake_client.set_ws("repairs/list_issues", {
            "issues": [
                {"issue_id": "a", "severity": "error", "domain": "light"},
                {"issue_id": "b", "severity": "warning", "domain": "light"},
                {"issue_id": "c", "severity": "error", "domain": "switch"},
            ]
        })
        rows = repairs.list_issues(fake_client, severity="error", domain="light")
        assert [r["issue_id"] for r in rows] == ["a"]

    def test_non_dict_response_returns_empty(self, fake_client):
        fake_client.set_ws("repairs/list_issues", None)
        assert repairs.list_issues(fake_client) == []

    def test_non_list_issues_key_returns_empty(self, fake_client):
        fake_client.set_ws("repairs/list_issues", {"issues": "not a list"})
        assert repairs.list_issues(fake_client) == []

    def test_no_issues_key_returns_empty(self, fake_client):
        fake_client.set_ws("repairs/list_issues", {})
        assert repairs.list_issues(fake_client) == []


class TestShow:
    def test_finds_issue_by_id(self, fake_client):
        fake_client.set_ws("repairs/list_issues", {
            "issues": [
                {"issue_id": "abc", "severity": "error", "domain": "light"},
                {"issue_id": "xyz", "severity": "warning", "domain": "switch"},
            ]
        })
        result = repairs.show(fake_client, "abc")
        assert result is not None
        assert result["issue_id"] == "abc"

    def test_finds_dismissed_issue(self, fake_client):
        """show() searches include_dismissed=True so dismissed issues are findable."""
        fake_client.set_ws("repairs/list_issues", {
            "issues": [
                {"issue_id": "abc", "dismissed_version": "2024.1"},
            ]
        })
        result = repairs.show(fake_client, "abc")
        assert result is not None
        assert result["issue_id"] == "abc"

    def test_narrows_by_domain(self, fake_client):
        """Same issue_id under two domains — domain param picks the right one."""
        fake_client.set_ws("repairs/list_issues", {
            "issues": [
                {"issue_id": "dup", "domain": "light"},
                {"issue_id": "dup", "domain": "switch"},
            ]
        })
        result = repairs.show(fake_client, "dup", domain="switch")
        assert result is not None
        assert result["domain"] == "switch"

    def test_domain_filter_excludes_non_matching(self, fake_client):
        fake_client.set_ws("repairs/list_issues", {
            "issues": [
                {"issue_id": "abc", "domain": "light"},
            ]
        })
        assert repairs.show(fake_client, "abc", domain="switch") is None

    def test_returns_none_when_not_found(self, fake_client):
        fake_client.set_ws("repairs/list_issues", {"issues": []})
        assert repairs.show(fake_client, "missing") is None

    def test_empty_issue_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="issue_id is required"):
            repairs.show(fake_client, "")


class TestIgnore:
    def test_sends_ignore_payload(self, fake_client):
        fake_client.set_ws("repairs/ignore", {"ok": True})
        result = repairs.ignore(fake_client, issue_id="abc", domain="light")
        assert result == {"ok": True}
        assert fake_client.ws_calls[-1]["type"] == "repairs/ignore"
        assert fake_client.ws_calls[-1]["payload"] == {
            "issue_id": "abc", "domain": "light", "ignore": True,
        }

    def test_un_ignore_passes_false(self, fake_client):
        fake_client.set_ws("repairs/ignore", {"ok": True})
        repairs.ignore(fake_client, issue_id="abc", domain="light", ignore_value=False)
        assert fake_client.ws_calls[-1]["payload"]["ignore"] is False

    def test_missing_issue_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="required"):
            repairs.ignore(fake_client, issue_id="", domain="light")

    def test_missing_domain_raises(self, fake_client):
        with pytest.raises(ValueError, match="required"):
            repairs.ignore(fake_client, issue_id="abc", domain="")


class TestFix:
    def test_posts_fix_flow(self, fake_client):
        fake_client.set("POST", "repairs/issues/fix", {"flow_id": "flow123"})
        result = repairs.fix(fake_client, issue_id="abc", domain="light")
        assert result["flow_id"] == "flow123"
        assert fake_client.calls[-1]["verb"] == "POST"
        assert fake_client.calls[-1]["path"] == "repairs/issues/fix"
        assert fake_client.calls[-1]["payload"] == {
            "handler": "light", "issue_id": "abc",
        }

    def test_missing_issue_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="required"):
            repairs.fix(fake_client, issue_id="", domain="light")

    def test_missing_domain_raises(self, fake_client):
        with pytest.raises(ValueError, match="required"):
            repairs.fix(fake_client, issue_id="abc", domain="")
