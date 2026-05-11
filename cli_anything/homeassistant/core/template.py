"""Template rendering via /api/template."""

from __future__ import annotations


def render(client, template: str, variables: dict | None = None) -> str:
    """Render a Jinja2 template against the live Home Assistant state."""
    if not template:
        raise ValueError("template cannot be empty")
    payload = {"template": template}
    if variables:
        payload["variables"] = variables
    result = client.post("template", payload)
    if isinstance(result, str):
        return result
    return str(result)
