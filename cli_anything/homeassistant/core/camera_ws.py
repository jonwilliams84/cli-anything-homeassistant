"""Camera WebSocket command wrappers.

Home Assistant exposes camera streaming, preferences, and WebRTC control
through the camera WebSocket API. This module wraps these commands for easier
use in scripts and automation.
"""

from __future__ import annotations


def capabilities(client, *, entity_id: str) -> dict:
    """Get camera capabilities via WS `camera/capabilities`.

    Returns a dict with camera capabilities including frontend_stream_types.
    """
    if not entity_id.startswith("camera."):
        raise ValueError(f"expected camera.* entity_id, got {entity_id!r}")
    return client.ws_call("camera/capabilities", {"entity_id": entity_id})


def stream(client, *, entity_id: str, format: str = "hls") -> dict:
    """Request a stream URL via WS `camera/stream`.

    Args:
        entity_id: The camera entity (must start with "camera.").
        format: Stream format; only "hls" is currently supported (default: "hls").

    Returns a dict with the stream URL, e.g. {"url": "..."}
    """
    if not entity_id.startswith("camera."):
        raise ValueError(f"expected camera.* entity_id, got {entity_id!r}")
    if format not in ("hls",):
        raise ValueError(f"format must be 'hls', got {format!r}")
    return client.ws_call("camera/stream", {"entity_id": entity_id, "format": format})


def get_prefs(client, *, entity_id: str) -> dict:
    """Get camera stream preferences via WS `camera/get_prefs`.

    Returns a dict with current preferences (preload_stream, orientation, etc.).
    """
    if not entity_id.startswith("camera."):
        raise ValueError(f"expected camera.* entity_id, got {entity_id!r}")
    return client.ws_call("camera/get_prefs", {"entity_id": entity_id})


def update_prefs(client, *, entity_id: str,
                 preload_stream: bool | None = None,
                 orientation: int | None = None) -> dict:
    """Update camera stream preferences via WS `camera/update_prefs`.

    Args:
        entity_id: The camera entity (must start with "camera.").
        preload_stream: Whether to preload the stream on frontend load.
        orientation: EXIF orientation code (1-8; see Orientation enum in HA).

    At least one of preload_stream or orientation must be set.
    orientation must be in range 1..8 if provided.

    Returns updated preferences dict.
    """
    if not entity_id.startswith("camera."):
        raise ValueError(f"expected camera.* entity_id, got {entity_id!r}")
    if preload_stream is None and orientation is None:
        raise ValueError("at least one of preload_stream/orientation must be set")
    if orientation is not None:
        if not isinstance(orientation, int) or orientation < 1 or orientation > 8:
            raise ValueError(
                f"orientation must be an integer in range 1..8, got {orientation!r}"
            )
    payload = {"entity_id": entity_id}
    if preload_stream is not None:
        payload["preload_stream"] = preload_stream
    if orientation is not None:
        payload["orientation"] = orientation
    return client.ws_call("camera/update_prefs", payload)


def webrtc_get_client_config(client, *, entity_id: str) -> dict:
    """Get WebRTC client configuration via WS `camera/webrtc/get_client_config`.

    Returns a dict with ICE servers and other WebRTC configuration.
    """
    if not entity_id.startswith("camera."):
        raise ValueError(f"expected camera.* entity_id, got {entity_id!r}")
    return client.ws_call("camera/webrtc/get_client_config", {"entity_id": entity_id})


def webrtc_offer(client, *, entity_id: str, offer: str) -> dict:
    """Send a WebRTC offer via WS `camera/webrtc/offer`.

    Args:
        entity_id: The camera entity (must start with "camera.").
        offer: The WebRTC offer (SDP string, must be non-empty).

    Returns a dict with session_id and other metadata.
    """
    if not entity_id.startswith("camera."):
        raise ValueError(f"expected camera.* entity_id, got {entity_id!r}")
    if not isinstance(offer, str) or not offer:
        raise ValueError(f"offer must be a non-empty string, got {offer!r}")
    return client.ws_call("camera/webrtc/offer", {"entity_id": entity_id, "offer": offer})


def webrtc_candidate(client, *, session_id: str, candidate: dict) -> dict:
    """Send a WebRTC ICE candidate via WS `camera/webrtc/candidate`.

    Args:
        session_id: The WebRTC session ID from webrtc_offer (must be non-empty).
        candidate: The ICE candidate dict (must be non-empty).

    Returns a confirmation dict.
    """
    if not isinstance(session_id, str) or not session_id:
        raise ValueError(f"session_id must be a non-empty string, got {session_id!r}")
    if not isinstance(candidate, dict) or not candidate:
        raise ValueError(f"candidate must be a non-empty dict, got {candidate!r}")
    return client.ws_call("camera/webrtc/candidate",
                           {"session_id": session_id, "candidate": candidate})
