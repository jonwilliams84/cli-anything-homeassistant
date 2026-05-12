"""Frontend themes — list / set / reload.

WS `frontend/get_themes` returns {themes: {name: {...}}, default_theme,
default_dark_theme}. The `frontend.set_theme` service applies a theme; the
`frontend.reload_themes` service reloads from configuration.yaml.
"""

from __future__ import annotations

from typing import Any, Optional

from cli_anything.homeassistant.core import services as services_core


def list_themes(client) -> dict:
    """Return the full themes dict + defaults.

    Shape: {themes: {name: {...vars...}}, default_theme, default_dark_theme}.
    """
    return client.ws_call("frontend/get_themes") or {}


def names(client) -> list[str]:
    """Convenience: just the installed theme names, sorted."""
    data = list_themes(client)
    themes = data.get("themes") if isinstance(data, dict) else None
    return sorted(themes.keys()) if isinstance(themes, dict) else []


def set_theme(client, name: str, *,
              mode: Optional[str] = None) -> Any:
    """Set the active theme. `mode` can be 'dark' / 'light' / None (default).

    With `mode`, HA applies the theme only for that color scheme. To restore
    HA's default theme, pass `name='default'`.
    """
    if not name:
        raise ValueError("name is required")
    data: dict[str, Any] = {"name": name}
    if mode:
        if mode not in ("dark", "light"):
            raise ValueError("mode must be 'dark' or 'light'")
        data["mode"] = mode
    return services_core.call_service(client, "frontend", "set_theme",
                                       service_data=data)


def reload(client) -> Any:
    """Reload themes from `themes:` in configuration.yaml."""
    return services_core.call_service(client, "frontend", "reload_themes")


themes_reload = reload
