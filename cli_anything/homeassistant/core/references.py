"""Cross-search for entity_id mentions across automations, scripts, scenes,
template helpers, blueprints, and Lovelace dashboards.

This is the diagnostic command for "where is X used?" — saves the grep
configuration.yaml dance.

Returns one row per hit:
  {kind, name, entry_id|id, where, snippet}

Coverage so far:
- automations  (config/automation/config — UI managed only)
- scripts      (config/script/config       — UI managed only)
- scenes       (config/scene/config        — UI managed only)
- template helpers (config_entries domain=template — via options-flow read)
- lovelace dashboards (every dashboard via lovelace/config)

Caller-owned YAML packages aren't covered (no public API to read them), but
all the UI-managed integrations above are.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable


def _walk_strings(obj: Any, path: str = ""):
    """Yield (path, string) for every string value found inside obj."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_strings(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def _matches_entity(text: str, entity_id: str, *,
                     also_match_unique_id: str | None = None) -> bool:
    """Return True iff `text` mentions `entity_id` as a whole token."""
    # Use a word-boundary-style match (avoid 'sensor.foo' matching 'sensor.foo_bar')
    pat = re.compile(r"(?<![a-zA-Z0-9_])" + re.escape(entity_id) + r"(?![a-zA-Z0-9_])")
    if pat.search(text):
        return True
    if also_match_unique_id and re.search(
        r"(?<![a-zA-Z0-9_])" + re.escape(also_match_unique_id) + r"(?![a-zA-Z0-9_])", text
    ):
        return True
    return False


def _snippet(text: str, entity_id: str, *, span: int = 40) -> str:
    idx = text.find(entity_id)
    if idx < 0:
        return text[:80]
    start = max(0, idx - span)
    end = min(len(text), idx + len(entity_id) + span)
    out = text[start:end].replace("\n", " ")
    if start > 0:
        out = "…" + out
    if end < len(text):
        out = out + "…"
    return out


# ── UI-managed automations / scripts / scenes ───────────────────────────────

def _ui_configs(client, domain: str) -> list[tuple[str, dict]]:
    """Return [(id, config)] for every UI-managed item in `domain`."""
    # The HA states list gives us the entity_id; we then ask
    # /api/config/<domain>/config/<id> for the full body. The numeric id
    # lives in attributes.id for automations; scripts / scenes use the
    # object_id (entity_id suffix).
    out: list[tuple[str, dict]] = []
    try:
        states = client.get("states") or []
    except Exception:
        return out
    for s in states:
        eid = s.get("entity_id", "")
        if not eid.startswith(domain + "."):
            continue
        obj_id = eid.split(".", 1)[1]
        cfg_id: str | None = None
        if domain == "automation":
            cfg_id = (s.get("attributes") or {}).get("id") or obj_id
        else:
            cfg_id = obj_id
        try:
            cfg = client.get(f"config/{domain}/config/{cfg_id}")
            if isinstance(cfg, dict):
                out.append((eid, cfg))
        except Exception:
            # not UI-managed (YAML-only) — skip silently
            continue
    return out


# ── template helpers ────────────────────────────────────────────────────────

def _template_helper_entries(client) -> list[dict]:
    """Return [{entry_id, title, options}] for every template config entry."""
    out: list[dict] = []
    try:
        entries = client.ws_call("config_entries/get",
                                    {"domain_list": ["template"]}) or []
    except Exception:
        try:
            entries = client.ws_call("config_entries/get") or []
            entries = [e for e in entries if e.get("domain") == "template"]
        except Exception:
            return out
    for e in entries:
        entry_id = e.get("entry_id")
        if not entry_id:
            continue
        try:
            init = client.post("config/config_entries/options/flow",
                                {"handler": entry_id})
            opts: dict = {}
            for f in init.get("data_schema", []) or []:
                if isinstance(f, dict) and "name" in f:
                    desc = f.get("description") or {}
                    if "suggested_value" in desc:
                        opts[f["name"]] = desc["suggested_value"]
            # Best-effort abort the flow we just opened
            flow_id = init.get("flow_id")
            if flow_id:
                try:
                    client.request("DELETE",
                                    f"config/config_entries/options/flow/{flow_id}")
                except Exception:
                    pass
            out.append({"entry_id": entry_id, "title": e.get("title"),
                         "options": opts})
        except Exception:
            continue
    return out


# ── Lovelace ────────────────────────────────────────────────────────────────

def _lovelace_configs(client) -> list[tuple[str, dict]]:
    """Return [(url_path or 'lovelace', config)] for every dashboard."""
    out: list[tuple[str, dict]] = []
    try:
        boards = client.ws_call("lovelace/dashboards/list") or []
    except Exception:
        boards = []
    # The main dashboard isn't always in the dashboards list; try None first.
    try:
        cfg = client.ws_call("lovelace/config", {})
        if isinstance(cfg, dict):
            out.append(("lovelace", cfg))
    except Exception:
        pass
    for b in boards:
        url = b.get("url_path")
        if not url:
            continue
        try:
            cfg = client.ws_call("lovelace/config", {"url_path": url})
            if isinstance(cfg, dict):
                out.append((url, cfg))
        except Exception:
            continue
    return out


# ── public ──────────────────────────────────────────────────────────────────

def find_references(client, entity_id: str, *,
                     include_kinds: Iterable[str] | None = None,
                     max_hits_per_kind: int = 30) -> list[dict]:
    """Return all references to `entity_id` across UI-managed config.

    `include_kinds` filters which categories to search: any subset of
    {"automation", "script", "scene", "template_helper", "lovelace"}.
    """
    if not entity_id or "." not in entity_id:
        raise ValueError("entity_id must be in 'domain.object' form")
    kinds = set(include_kinds) if include_kinds else {
        "automation", "script", "scene", "template_helper", "lovelace",
    }
    hits: list[dict] = []

    # automations / scripts / scenes — all share the same /api/config/<d>/config/<id> shape
    for kind in ("automation", "script", "scene"):
        if kind not in kinds:
            continue
        count = 0
        for ent_id, cfg in _ui_configs(client, kind):
            blob = json.dumps(cfg, default=str)
            if _matches_entity(blob, entity_id):
                # which field? walk for nicer snippet
                matched_path = None
                for p, s in _walk_strings(cfg):
                    if _matches_entity(s, entity_id):
                        matched_path = p
                        break
                hits.append({
                    "kind": kind,
                    "entity_id": ent_id,
                    "name": cfg.get("alias") or cfg.get("description") or ent_id,
                    "where": matched_path or "?",
                    "snippet": _snippet(blob, entity_id),
                })
                count += 1
                if count >= max_hits_per_kind:
                    break

    if "template_helper" in kinds:
        count = 0
        for entry in _template_helper_entries(client):
            blob = json.dumps(entry["options"], default=str)
            if _matches_entity(blob, entity_id):
                matched_path = None
                for p, s in _walk_strings(entry["options"]):
                    if _matches_entity(s, entity_id):
                        matched_path = p
                        break
                hits.append({
                    "kind": "template_helper",
                    "entry_id": entry["entry_id"],
                    "name": entry.get("title"),
                    "where": matched_path or "?",
                    "snippet": _snippet(blob, entity_id),
                })
                count += 1
                if count >= max_hits_per_kind:
                    break

    if "lovelace" in kinds:
        count = 0
        for url, cfg in _lovelace_configs(client):
            blob = json.dumps(cfg, default=str)
            if not _matches_entity(blob, entity_id):
                continue
            # Walk every node to give per-card paths back
            for p, s in _walk_strings(cfg):
                if not _matches_entity(s, entity_id):
                    continue
                hits.append({
                    "kind": "lovelace",
                    "dashboard": url,
                    "where": p,
                    "snippet": _snippet(s, entity_id),
                })
                count += 1
                if count >= max_hits_per_kind:
                    break
            if count >= max_hits_per_kind:
                break

    return hits
