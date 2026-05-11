"""Connection profile management for cli-anything-homeassistant.

Holds URL + long-lived access token. The CLI itself is stateless across runs —
this is the only persistent state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "cli-anything-homeassistant.json"
DEFAULT_URL = "http://localhost:8123"
DEFAULT_TIMEOUT = 30


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def load_config(config_path: Path | None = None) -> dict:
    """Load connection config from file, applying env-var overrides."""
    path = config_path or DEFAULT_CONFIG_PATH
    cfg = {
        "url": DEFAULT_URL,
        "token": "",
        "verify_ssl": True,
        "timeout": DEFAULT_TIMEOUT,
    }
    if path.exists():
        try:
            with open(path) as f:
                file_cfg = json.load(f)
            for key in ("url", "token", "verify_ssl", "timeout"):
                if key in file_cfg:
                    cfg[key] = file_cfg[key]
        except (json.JSONDecodeError, OSError):
            pass

    if os.getenv("HASS_URL"):
        cfg["url"] = os.environ["HASS_URL"]
    if os.getenv("HASS_TOKEN"):
        cfg["token"] = os.environ["HASS_TOKEN"]
    if os.getenv("HASS_VERIFY_SSL") is not None:
        cfg["verify_ssl"] = _to_bool(os.environ["HASS_VERIFY_SSL"])
    if os.getenv("HASS_TIMEOUT"):
        try:
            cfg["timeout"] = int(os.environ["HASS_TIMEOUT"])
        except ValueError:
            pass
    return cfg


def save_config(
    url: str,
    token: str,
    verify_ssl: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    config_path: Path | None = None,
) -> Path:
    """Persist the connection profile."""
    path = config_path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "url": url,
        "token": token,
        "verify_ssl": bool(verify_ssl),
        "timeout": int(timeout),
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover — best-effort permission tightening
        pass
    return path


def redact(cfg: dict) -> dict:
    """Return a copy of cfg with the token redacted for display."""
    out = dict(cfg)
    if out.get("token"):
        out["token"] = "***" + str(out["token"])[-4:]
    return out
