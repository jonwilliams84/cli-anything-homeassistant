"""HA MQTT-discovery topic management.

Lets callers:
  - `list` — enumerate currently-discovered objects (subscribes briefly to
    `homeassistant/+/+/+/config` or `<prefix>/+/+/+/config` and collects
    retained payloads)
  - `show` — get a single retained discovery payload by object_id
  - `delete` — wipe a discovery topic by publishing an empty retained payload
  - `republish` — trigger HA's MQTT integration to re-publish its discovery
"""

from __future__ import annotations

import json
from typing import Any

from cli_anything.homeassistant.core import services as services_core


def _norm_prefix(prefix: str) -> str:
    return prefix.rstrip("/")


def list_discovered(client, prefix: str = "homeassistant",
                     timeout: float = 5.0) -> list[dict]:
    """Subscribe briefly and collect all retained discovery messages.

    Returns one row per topic: {topic, domain, object_id, component,
    name, unique_id}.
    """
    prefix = _norm_prefix(prefix)
    # We rely on the HA-side MQTT subscribe (single-shot is fine for retained).
    topic_filter = f"{prefix}/+/+/+/config"
    rows = _subscribe_collect(client, topic_filter, timeout=timeout)
    out: list[dict] = []
    for r in rows:
        parts = r["topic"].split("/")
        # homeassistant/<component>/<node_id>/<object_id>/config  (5 parts)
        # homeassistant/<component>/<object_id>/config            (4 parts)
        if len(parts) == 5:
            _, component, node_id, object_id, _ = parts
        elif len(parts) == 4:
            _, component, object_id, _ = parts
            node_id = None
        else:
            continue
        try:
            payload = json.loads(r["payload"]) if r["payload"] else {}
        except (json.JSONDecodeError, ValueError):
            payload = {}
        out.append({
            "topic": r["topic"],
            "component": component,
            "node_id": node_id,
            "object_id": object_id,
            "name": payload.get("name"),
            "unique_id": payload.get("unique_id") or payload.get("uniq_id"),
            "device": (payload.get("device") or {}).get("name"),
        })
    return out


def show(client, topic: str, *, timeout: float = 3.0) -> dict | None:
    """Return the retained discovery payload at a specific topic."""
    rows = _subscribe_collect(client, topic, timeout=timeout)
    if not rows:
        return None
    raw = rows[0].get("payload", "")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"raw": raw}


def delete(client, topic: str) -> Any:
    """Wipe a discovery topic by publishing an empty retained message."""
    return services_core.call_service(
        client, "mqtt", "publish",
        service_data={
            "topic": topic,
            "payload": "",
            "retain": True,
        },
    )


def republish(client) -> Any:
    """Ask HA's MQTT integration to re-emit all its own discovery topics."""
    return services_core.call_service(client, "mqtt", "reload")


# ── internal ────────────────────────────────────────────────────────────────

def _subscribe_collect(client, topic_filter: str, *,
                        timeout: float = 5.0, limit: int = 5000) -> list[dict]:
    """Use HA's WebSocket mqtt/subscribe to collect retained + live messages."""
    import threading, time
    out: list[dict] = []
    stop = threading.Event()

    def on_msg(event):
        if not isinstance(event, dict):
            return
        out.append({
            "topic": event.get("topic"),
            "payload": event.get("payload"),
            "qos": event.get("qos"),
            "retain": event.get("retain"),
        })
        if len(out) >= limit:
            stop.set()

    # Run the subscriber in a thread; cap by timeout
    th = threading.Thread(target=client.ws_subscribe, args=(
        "mqtt/subscribe", {"topic": topic_filter}, on_msg, stop,
    ), daemon=True)
    th.start()
    th.join(timeout=timeout)
    stop.set()
    th.join(timeout=2.0)
    return out
