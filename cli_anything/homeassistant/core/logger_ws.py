"""Logger integration control via WS API.

The logger integration manages log levels for integrations and modules at
runtime. Changes can be persisted (survive restart) or temporary.
"""

from __future__ import annotations


def log_info(client) -> list[dict]:
    """Get the current log configuration for all loaded integrations.

    Returns a list of dicts with keys `domain` (integration name) and `level`
    (current log level as an integer, e.g., 20 for INFO, 10 for DEBUG).

    Args:
        client: HomeAssistantClient instance.
    """
    return client.ws_call("logger/log_info", {})


def log_level(
    client,
    *,
    integration: str | None = None,
    namespace: str | None = None,
) -> dict:
    """Get the log level for a specific integration or module namespace.

    Args:
        client: HomeAssistantClient instance.
        integration: Integration name (e.g., "hue", "mqtt"). Mutually
            exclusive with `namespace`.
        namespace: Module namespace (e.g., "homeassistant.components.mqtt").
            Mutually exclusive with `integration`.

    Returns:
        A dict with the integration/namespace info and current level.

    Raises:
        ValueError: If both `integration` and `namespace` are supplied,
            or if neither is supplied.
    """
    if integration is not None and namespace is not None:
        raise ValueError("cannot set both integration and namespace")
    if integration is None and namespace is None:
        raise ValueError("must set either integration or namespace")

    payload: dict = {}
    if integration is not None:
        payload["integration"] = integration
    if namespace is not None:
        payload["namespace"] = namespace
    return client.ws_call("logger/log_level", payload)


def integration_log_level(
    client,
    *,
    integration: str,
    level: str,
    persistence: str = "none",
) -> dict:
    """Set the log level for an integration.

    Args:
        client: HomeAssistantClient instance.
        integration: Integration name (e.g., "hue", "mqtt"). Must be
            non-empty.
        level: Log level as a string. Must be one of: debug, info, warning,
            error, critical.
        persistence: Persistence mode. Must be one of: "none" (temporary,
            lost on restart) or "once" (saved until next restart, then
            reset). Defaults to "none".

    Returns:
        A result dict from the WS API (typically empty on success).

    Raises:
        ValueError: If integration is empty, level is not valid, or
            persistence is not valid.
    """
    if not integration:
        raise ValueError("integration is required and must be non-empty")
    valid_levels = {"debug", "info", "warning", "error", "critical"}
    if level not in valid_levels:
        raise ValueError(
            f"level must be one of {sorted(valid_levels)}, got {level!r}"
        )
    valid_persistence = {"none", "once"}
    if persistence not in valid_persistence:
        raise ValueError(
            f"persistence must be one of {sorted(valid_persistence)}, got {persistence!r}"
        )
    return client.ws_call(
        "logger/integration_log_level",
        {
            "integration": integration,
            "level": level,
            "persistence": persistence,
        },
    )
