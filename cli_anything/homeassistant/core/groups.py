"""Group expansion — list the child entities of a group (light, switch, etc).

Uses Jinja's `expand()` filter via the template render API, so it works for
every group domain HA supports (light, switch, sensor groups, person groups,
device_tracker groups).
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.core import template as template_core
from cli_anything.homeassistant.core import states as states_core


def expand(client, entity_id: str, *, include_state: bool = True) -> list[dict]:
    """Return one row per child entity: {entity_id, state?, friendly_name?}."""
    if "." not in entity_id:
        raise ValueError("entity_id must be in 'domain.object' form")
    tpl = (
        "{% for s in expand('" + entity_id + "') %}"
        + "{{ s.entity_id }}|||{{ s.state }}|||{{ s.attributes.friendly_name or '' }}\n"
        + "{% endfor %}"
    )
    rendered = template_core.render(client, tpl, None)
    rows: list[dict] = []
    for line in rendered.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|||")
        ent = parts[0] if parts else None
        if not ent:
            continue
        row: dict[str, Any] = {"entity_id": ent}
        if include_state and len(parts) > 1:
            row["state"] = parts[1]
        if len(parts) > 2 and parts[2]:
            row["friendly_name"] = parts[2]
        rows.append(row)
    return rows


def deep_expand(client, entity_id: str) -> list[str]:
    """Same as expand() but returns only the flat entity_id list (no state)."""
    return [r["entity_id"] for r in expand(client, entity_id, include_state=False)]
