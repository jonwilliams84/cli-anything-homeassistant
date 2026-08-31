"""Group expansion — list the child entities of a group (light, switch, etc).

Uses Jinja's `expand()` filter via the template render API, so it works for
every group domain HA supports (light, switch, sensor groups, person groups,
device_tracker groups).
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.core import template as template_core


def expand(client, entity_id: str, *, include_state: bool = True) -> list[dict]:
    """Return one row per child entity: {entity_id, state?, friendly_name?}."""
    if "." not in entity_id:
        raise ValueError("entity_id must be in 'domain.object' form")
    tpl = (
        "{% for s in expand('"
        + entity_id
        + "') %}"
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


# ─────────────────────────────────────────── runtime group CRUD (group.set/remove)
#
# `group.set` creates and edits groups AT RUNTIME, without touching
# configuration.yaml and without a restart. The group it makes lives in
# `.storage` and survives a restart, but a group defined in YAML is
# re-created from YAML on reload, so editing one of those with `set` is
# temporary. Both services are addressed by OBJECT ID (`kitchen`), not by
# entity id (`group.kitchen`).


def _object_id(value: str) -> str:
    """Accept either `kitchen` or `group.kitchen` and return the object id.

    `group.set`/`group.remove` take `object_id`, and passing a full entity id
    creates `group.group.kitchen` rather than failing — an easy mistake with
    no error attached to it, since every other command in this harness takes
    an entity id.
    """
    if not value:
        raise ValueError("object_id is required")
    if value.startswith("group."):
        return value.split(".", 1)[1]
    if "." in value:
        raise ValueError(
            f"object_id must be a bare id like 'kitchen' (or 'group.kitchen'), "
            f"got {value!r}"
        )
    return value


def set_group(
    client,
    object_id: str,
    *,
    name: str | None = None,
    icon: str | None = None,
    entities: list[str] | None = None,
    add_entities: list[str] | None = None,
    remove_entities: list[str] | None = None,
    all_must_be_on: bool | None = None,
) -> dict:
    """`group.set` — create or update a group at runtime.

    `entities` REPLACES the membership; `add_entities`/`remove_entities` edit
    it in place. Passing `entities` together with either of the others makes
    the outcome depend on HA's internal ordering, so it is refused here.

    `all_must_be_on` is HA's `all` field: when true the group is `on` only
    while EVERY member is on (the default is "on if any member is on").
    """
    oid = _object_id(object_id)
    if entities is not None and (add_entities or remove_entities):
        raise ValueError(
            "pass either --entities (replace the whole membership) or "
            "--add/--remove (edit it), not both"
        )
    if (
        name is None
        and icon is None
        and entities is None
        and not add_entities
        and not remove_entities
        and all_must_be_on is None
    ):
        raise ValueError("nothing to set — give at least one of name/icon/entities/add/remove/all")
    payload: dict[str, Any] = {"object_id": oid}
    if name is not None:
        payload["name"] = name
    if icon is not None:
        payload["icon"] = icon
    if entities is not None:
        payload["entities"] = list(entities)
    if add_entities:
        payload["add_entities"] = list(add_entities)
    if remove_entities:
        payload["remove_entities"] = list(remove_entities)
    if all_must_be_on is not None:
        payload["all"] = bool(all_must_be_on)
    client.post("services/group/set", payload)
    return {"object_id": oid, "entity_id": f"group.{oid}", "applied": payload}


def remove_group(client, object_id: str) -> dict:
    """`group.remove` — delete a runtime group.

    A group that came from `configuration.yaml` comes back on the next
    `group.reload`; only a group created by `group.set` stays gone.
    """
    oid = _object_id(object_id)
    client.post("services/group/remove", {"object_id": oid})
    return {"object_id": oid, "entity_id": f"group.{oid}", "removed": True}


def reload_groups(client) -> dict:
    """`group.reload` — re-read the group section of `configuration.yaml`."""
    client.post("services/group/reload", {})
    return {"reloaded": "group"}
