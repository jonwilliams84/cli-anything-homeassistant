"""Card-type discovery and HACS cross-reference.

Walks Lovelace configs to enumerate every `type:` value in use, then
cross-references custom (`custom:*`) types against installed HACS
plugins so the agent can flag orphans.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from cli_anything.homeassistant.core import lovelace_cards as cards_core


def card_types_in_use(config: dict) -> dict[str, int]:
    """Return a {type: count} dict for every card type referenced in the
    given dashboard config (recursive, includes nested stacks)."""
    counts: Counter[str] = Counter()
    for _, card in cards_core.all_cards(config):
        t = card.get("type")
        if t:
            counts[str(t)] += 1
    return dict(counts)


def types_across_dashboards(client) -> dict[str, dict[str, int]]:
    """Walk every dashboard and report `{dashboard_url: {type: count}}`."""
    from cli_anything.homeassistant.core import lovelace as lovelace_core
    dashboards = lovelace_core.list_dashboards(client)
    out: dict[str, dict[str, int]] = {}
    # Storage-mode dashboards have url_path; YAML-mode ones aren't accessible
    seen: set[str] = set()
    for d in dashboards:
        url = d.get("url_path")
        if not url or url in seen:
            continue
        seen.add(url)
        try:
            cfg = lovelace_core.get_dashboard_config(client, url)
        except Exception:
            continue
        types = card_types_in_use(cfg)
        if types:
            out[url] = types
    # Also include the default Overview dashboard (url_path=None) if no
    # explicit "lovelace" entry was returned
    try:
        cfg = lovelace_core.get_dashboard_config(client, None)
        out.setdefault("(default)", card_types_in_use(cfg))
    except Exception:
        pass
    return out


def custom_types_only(types: Iterable[str]) -> list[str]:
    return [t for t in types if t.startswith("custom:")]


def cross_reference_hacs(client, custom_types: Iterable[str]) -> dict:
    """For each `custom:*` type, attempt to match an installed HACS plugin.

    HACS doesn't expose a direct "card-type → plugin" map, but most plugins
    expose a JS module whose filename matches the card type. We fuzzy-match
    on the HACS repository `name` and `full_name`.

    Returns {type: {plugin: <hacs repo info>|None, installed: bool}}.
    """
    from cli_anything.homeassistant.core import hacs as hacs_core
    try:
        plugins = hacs_core.list_repos(client, category="plugin")
    except Exception as exc:
        return {"_error": str(exc)}
    # Index HACS plugins by lowercase token sets
    def tokens(s: str) -> set[str]:
        return set(s.lower().replace("-", " ").replace("_", " ").split())

    indexed = []
    for p in plugins:
        full = p.get("full_name", "") or ""
        name = p.get("name", "") or ""
        short = full.split("/")[-1].lower() if "/" in full else full.lower()
        indexed.append({
            "id": p.get("id"),
            "full_name": full,
            "name": name,
            "short": short,
            "installed": bool(p.get("installed")),
            "tokens": tokens(full) | tokens(name) | tokens(short),
        })

    out: dict = {}
    for ct in custom_types:
        if not ct.startswith("custom:"):
            continue
        bare = ct[len("custom:"):]
        bare_tokens = tokens(bare)
        # Score by token overlap, then exact-substring boost
        best = None; best_score = 0
        for p in indexed:
            score = len(bare_tokens & p["tokens"])
            if bare in p["short"] or p["short"] in bare:
                score += 2
            if score > best_score:
                best_score = score; best = p
        out[ct] = {
            "plugin": ({"id": best["id"], "full_name": best["full_name"],
                        "name": best["name"]} if best and best_score >= 1 else None),
            "installed": bool(best and best["installed"] and best_score >= 1),
            "score": best_score,
        }
    return out
