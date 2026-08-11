"""HA Labs — the preview features an instance can opt into, and what they cost.

WHAT IT IS
    `labs` is Home Assistant's 2026 feature-flag surface: per-integration
    preview features that are off by default, each with a feedback URL and a
    "learn more" link, and each capable of changing behaviour underneath
    everything else this harness reports.

    That last part is why it belongs here rather than in a UI. An agent
    debugging why an integration behaves unlike its documentation has, until
    now, had no way to see that a preview feature was switched on.

THE ONE THAT MATTERS WHEN ENABLING
    `labs/update` takes `create_backup` (default FALSE). A preview feature can
    migrate storage, so the flag exists precisely because some of these are not
    cleanly reversible. `enable()` surfaces it as an explicit argument rather
    than defaulting it, and the CLI wrapper asks.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)


def list_features(client) -> list[dict]:
    """Every preview feature this instance knows about, with its state.

    HA filters the list to LOADED integrations, so this is what is available
    here rather than everything Labs has ever shipped.
    """
    data = client.ws_call("labs/list") or {}
    features = data.get("features") if isinstance(data, dict) else None
    rows = []
    for f in features or []:
        rows.append(
            {
                "domain": f.get("domain"),
                "preview_feature": f.get("preview_feature"),
                "enabled": f.get("enabled"),
                "is_built_in": f.get("is_built_in"),
                "learn_more_url": f.get("learn_more_url"),
                "feedback_url": f.get("feedback_url"),
                # Present on features whose activation needs a restart; worth
                # keeping, because "enabled" alone then overstates the state.
                "report_issue_url": f.get("report_issue_url"),
            }
        )
    return rows


def get_feature(client, domain: str, preview_feature: str) -> dict:
    """One feature, or a clear error naming what does exist for that domain."""
    rows = list_features(client)
    for row in rows:
        if row["domain"] == domain and row["preview_feature"] == preview_feature:
            return row
    same_domain = [r["preview_feature"] for r in rows if r["domain"] == domain]
    if same_domain:
        raise ValueError(
            f"{domain} has no preview feature {preview_feature!r}. It has: "
            + ", ".join(same_domain)
        )
    raise ValueError(
        f"No preview features for domain {domain!r}. Domains with features here: "
        + ", ".join(sorted({r["domain"] for r in rows}))
    )


def set_feature(
    client,
    domain: str,
    preview_feature: str,
    enabled: bool,
    *,
    create_backup: bool = False,
) -> dict:
    """Turn a preview feature on or off.

    `create_backup` defaults to False because that is HA's own default, not
    because it is the safe choice — a preview feature may migrate storage. The
    CLI wrapper is where the prompt lives.
    """
    before = get_feature(client, domain, preview_feature)
    client.ws_call(
        "labs/update",
        {
            "domain": domain,
            "preview_feature": preview_feature,
            "enabled": bool(enabled),
            "create_backup": bool(create_backup),
        },
    )
    after = get_feature(client, domain, preview_feature)
    return {
        "domain": domain,
        "preview_feature": preview_feature,
        "was": before.get("enabled"),
        "now": after.get("enabled"),
        "changed": before.get("enabled") != after.get("enabled"),
        "backup_requested": bool(create_backup),
    }


def enabled_features(client) -> list[dict]:
    """Only the features that are ON — the ones that can explain odd behaviour."""
    return [f for f in list_features(client) if f.get("enabled")]
