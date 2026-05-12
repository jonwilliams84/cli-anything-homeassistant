"""Unit tests for network module."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import network


class TestNetwork:
    """Tests for network module functions."""

    def test_info_happy_path(self, fake_client):
        """Test getting network adapter information."""
        fake_client.set_ws("network", {
            "adapters": [
                {"name": "eth0", "enabled": True},
                {"name": "wlan0", "enabled": False},
            ],
            "configured_adapters": ["eth0"],
        })
        result = network.info(fake_client)
        assert result == {
            "adapters": [
                {"name": "eth0", "enabled": True},
                {"name": "wlan0", "enabled": False},
            ],
            "configured_adapters": ["eth0"],
        }
        assert fake_client.ws_calls[-1]["type"] == "network"
        assert fake_client.ws_calls[-1]["payload"] == {}

    def test_info_empty_adapters(self, fake_client):
        """Test info with no adapters."""
        fake_client.set_ws("network", {
            "adapters": [],
            "configured_adapters": [],
        })
        result = network.info(fake_client)
        assert result["adapters"] == []
        assert result["configured_adapters"] == []

    def test_configure_happy_path(self, fake_client):
        """Test configuring network adapters."""
        fake_client.set_ws("network/configure", {
            "configured_adapters": ["eth0", "wlan0"],
        })
        result = network.configure(
            fake_client, configured_adapters=["eth0", "wlan0"]
        )
        assert result == {"configured_adapters": ["eth0", "wlan0"]}
        assert fake_client.ws_calls[-1]["type"] == "network/configure"
        assert fake_client.ws_calls[-1]["payload"] == {
            "config": {
                "configured_adapters": ["eth0", "wlan0"],
            }
        }

    def test_configure_single_adapter(self, fake_client):
        """Test configuring with a single adapter."""
        fake_client.set_ws("network/configure", {
            "configured_adapters": ["eth0"],
        })
        result = network.configure(fake_client, configured_adapters=["eth0"])
        assert result["configured_adapters"] == ["eth0"]
        assert fake_client.ws_calls[-1]["payload"]["config"]["configured_adapters"] == ["eth0"]

    def test_configure_empty_list_raises(self, fake_client):
        """Test that empty configured_adapters list raises ValueError."""
        with pytest.raises(ValueError, match="configured_adapters must be a non-empty list"):
            network.configure(fake_client, configured_adapters=[])

    def test_configure_non_list_raises(self, fake_client):
        """Test that non-list configured_adapters raises ValueError."""
        with pytest.raises(ValueError, match="configured_adapters must be a list"):
            network.configure(fake_client, configured_adapters="eth0")

    def test_url_all_present(self, fake_client):
        """Test getting URLs when all are available."""
        fake_client.set_ws("network/url", {
            "internal": "http://192.168.1.100:8123",
            "external": "https://example.com",
            "cloud": "https://cloud.home-assistant.io",
        })
        result = network.url(fake_client)
        assert result == {
            "internal_url": "http://192.168.1.100:8123",
            "external_url": "https://example.com",
            "cloud_url": "https://cloud.home-assistant.io",
        }
        assert fake_client.ws_calls[-1]["type"] == "network/url"
        assert fake_client.ws_calls[-1]["payload"] == {}

    def test_url_only_internal(self, fake_client):
        """Test getting URLs when only internal is available."""
        fake_client.set_ws("network/url", {
            "internal": "http://localhost:8123",
            "external": None,
            "cloud": None,
        })
        result = network.url(fake_client)
        assert result == {
            "internal_url": "http://localhost:8123",
            "external_url": None,
            "cloud_url": None,
        }

    def test_url_only_external(self, fake_client):
        """Test getting URLs when only external is available."""
        fake_client.set_ws("network/url", {
            "internal": None,
            "external": "https://example.com",
            "cloud": None,
        })
        result = network.url(fake_client)
        assert result == {
            "internal_url": None,
            "external_url": "https://example.com",
            "cloud_url": None,
        }

    def test_url_all_none(self, fake_client):
        """Test getting URLs when none are available."""
        fake_client.set_ws("network/url", {
            "internal": None,
            "external": None,
            "cloud": None,
        })
        result = network.url(fake_client)
        assert result == {
            "internal_url": None,
            "external_url": None,
            "cloud_url": None,
        }

    def test_url_missing_keys(self, fake_client):
        """Test url with missing keys in response defaults to None."""
        fake_client.set_ws("network/url", {})
        result = network.url(fake_client)
        assert result == {
            "internal_url": None,
            "external_url": None,
            "cloud_url": None,
        }

    def test_info_return_shape(self, fake_client):
        """Test that info returns correct shape."""
        fake_client.set_ws("network", {
            "adapters": [{"name": "eth0"}],
            "configured_adapters": ["eth0"],
        })
        result = network.info(fake_client)
        assert isinstance(result, dict)
        assert "adapters" in result
        assert "configured_adapters" in result
        assert isinstance(result["adapters"], list)
        assert isinstance(result["configured_adapters"], list)

    def test_configure_return_shape(self, fake_client):
        """Test that configure returns a dict."""
        fake_client.set_ws("network/configure", {
            "configured_adapters": ["eth0"],
        })
        result = network.configure(fake_client, configured_adapters=["eth0"])
        assert isinstance(result, dict)
        assert "configured_adapters" in result

    def test_url_return_shape(self, fake_client):
        """Test that url returns correct shape with expected keys."""
        fake_client.set_ws("network/url", {
            "internal": "http://localhost:8123",
            "external": None,
            "cloud": None,
        })
        result = network.url(fake_client)
        assert isinstance(result, dict)
        assert set(result.keys()) == {"internal_url", "external_url", "cloud_url"}
        for value in result.values():
            assert value is None or isinstance(value, str)
