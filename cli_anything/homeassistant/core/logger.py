"""Runtime log-level control via the `logger.set_level` service.

This silences (or amplifies) a noisy component without editing
configuration.yaml or restarting HA. Resets on next restart.
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.core import services as services_core

VALID_LEVELS = {"critical", "fatal", "error", "warning", "warn",
                 "info", "debug", "notset"}


def set_level(client, levels: dict[str, str]) -> Any:
    """Set log levels for one or more loggers.

    `levels` is `{logger.dotted.name: level}`. e.g.::

        set_level(client, {"custom_components.hon": "critical",
                            "pychromecast.socket_client": "critical"})
    """
    if not isinstance(levels, dict) or not levels:
        raise ValueError("levels must be a non-empty {component: level} dict")
    payload: dict[str, str] = {}
    for k, v in levels.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ValueError("levels must map str -> str")
        lv = v.strip().lower()
        if lv not in VALID_LEVELS:
            raise ValueError(f"invalid level {v!r}; expected one of {sorted(VALID_LEVELS)}")
        payload[k] = lv
    return services_core.call_service(client, "logger", "set_level",
                                       service_data=payload)


def set_default_level(client, level: str) -> Any:
    """Change the global default log level."""
    if level.strip().lower() not in VALID_LEVELS:
        raise ValueError(f"invalid level {level!r}")
    return services_core.call_service(client, "logger", "set_default_level",
                                       service_data={"level": level.strip().lower()})
