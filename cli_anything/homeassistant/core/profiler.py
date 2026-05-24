"""profiler.* services — runtime profiling toolkit.

The Home Assistant ``profiler`` integration exposes a fixed set of services
useful for chasing perf regressions and memory leaks in a live install:

* ``profiler.start`` — cProfile dump
* ``profiler.memory`` — memray dump
* ``profiler.dump_log_objects`` — log every live instance of a given class
* ``profiler.log_thread_frames`` — stack-frame snapshot for every thread
* ``profiler.log_event_loop_scheduled`` — scheduled asyncio callbacks
* ``profiler.log_current_tasks`` — currently running asyncio tasks
* ``profiler.lru_stats`` — @lru_cache statistics across all caches
* ``profiler.set_asyncio_debug`` — toggle asyncio debug mode
* ``profiler.log_events`` — event bus listener counts

Every helper here is a thin service-call wrapper; the integration must be
loaded for the calls to land. ``status()`` is a cheap probe agents can use
to confirm availability before kicking off a dump.

Service-call output is always wrapped in ``{"service": "profiler.<name>",
"call": ...}`` so the CLI's JSON layer presents a uniform shape.
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.core import services as services_core


_DOMAIN = "profiler"


# ──────────────────────────────────────────────────────────────────── helpers

def _call(client, service: str, data: dict | None = None) -> dict:
    response = services_core.call_service(client, _DOMAIN, service, service_data=data)
    return {"service": f"{_DOMAIN}.{service}", "data": data or {}, "response": response}


def _is_loaded(client) -> bool:
    try:
        components = client.get("components") or []
    except Exception:
        return False
    if not isinstance(components, list):
        return False
    return _DOMAIN in components


def _exposed_services(client) -> list[str]:
    """Return the list of profiler.* service names known to the server."""
    try:
        all_services = client.get("services") or []
    except Exception:
        return []
    if not isinstance(all_services, list):
        return []
    for entry in all_services:
        if isinstance(entry, dict) and entry.get("domain") == _DOMAIN:
            svc_dict = entry.get("services") or {}
            if isinstance(svc_dict, dict):
                return sorted(svc_dict.keys())
    return []


# ─────────────────────────────────────────────────────────────────── services

def start(client, *, seconds: int = 60) -> dict:
    if seconds <= 0:
        raise ValueError("seconds must be positive")
    return _call(client, "start", {"seconds": int(seconds)})


def memory(client, *, seconds: int = 60) -> dict:
    if seconds <= 0:
        raise ValueError("seconds must be positive")
    return _call(client, "memory", {"seconds": int(seconds)})


def dump_log_objects(client, *, type_: str) -> dict:
    if not type_:
        raise ValueError("type_ is required (Python class name)")
    return _call(client, "dump_log_objects", {"type": type_})


def log_thread_frames(client) -> dict:
    return _call(client, "log_thread_frames")


def log_event_loop_scheduled(client) -> dict:
    return _call(client, "log_event_loop_scheduled")


def log_current_tasks(client) -> dict:
    return _call(client, "log_current_tasks")


def lru_stats(client) -> dict:
    return _call(client, "lru_stats")


def set_asyncio_debug(client, *, enabled: bool = True) -> dict:
    return _call(client, "set_asyncio_debug", {"enabled": bool(enabled)})


def log_events(client) -> dict:
    return _call(client, "log_events")


# ───────────────────────────────────────────────────────────────────── status

def status(client) -> dict:
    """Cheap probe — is the profiler integration loaded? Which services exist?"""
    return {
        "loaded": _is_loaded(client),
        "services": _exposed_services(client),
    }
