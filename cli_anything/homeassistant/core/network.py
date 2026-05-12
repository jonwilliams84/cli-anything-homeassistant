"""Network configuration and information.

Manage network adapter configuration and retrieve internal/external/cloud URLs
via the ``network/*`` WebSocket commands.

(`info()` is also exported as `network_info` for unambiguous `from X import` usage.)
"""

from __future__ import annotations


def info(client) -> dict:
    """Get network adapter information.

    WS: ``network``

    Returns a dict with:
      - adapters: list of available network adapters
      - configured_adapters: list of currently enabled adapter names
    """
    return client.ws_call("network", {})


def configure(client, *, configured_adapters: list[str]) -> dict:
    """Configure which network adapters are active.

    WS: ``network/configure``

    Payload: {config: {configured_adapters: [...]}}
    Returns the new configured_adapters list.
    """
    if not configured_adapters:
        raise ValueError("configured_adapters must be a non-empty list")
    if not isinstance(configured_adapters, list):
        raise ValueError("configured_adapters must be a list")

    return client.ws_call("network/configure", {
        "config": {
            "configured_adapters": configured_adapters,
        }
    })


def url(client) -> dict:
    """Get internal, external, and cloud URLs.

    WS: ``network/url``

    Returns a dict with:
      - internal: internal URL (or None)
      - external: external URL (or None)
      - cloud: cloud URL (or None)
    """
    result = client.ws_call("network/url", {})
    return {
        "internal_url": result.get("internal"),
        "external_url": result.get("external"),
        "cloud_url": result.get("cloud"),
    }


network_info = info
