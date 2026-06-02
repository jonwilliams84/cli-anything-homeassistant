"""cli-anything-homeassistant — control a running Home Assistant from the CLI."""

from __future__ import annotations

import json
import shlex
import sys
import threading
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

import click


def _resolve_version() -> str:
    """Single source of truth: read from installed package metadata.

    Falls back to "0.0.0+unknown" when running from an uninstalled checkout
    (no `pip install -e .`) so the REPL still launches.
    """
    try:
        return _pkg_version("cli-anything-homeassistant")
    except PackageNotFoundError:
        return "0.0.0+unknown"


__version__ = _resolve_version()

from cli_anything.homeassistant.core import auth as auth_core
from cli_anything.homeassistant.core import automation as automation_core
from cli_anything.homeassistant.core import config_entries as config_entries_core
from cli_anything.homeassistant.core import domain as domain_core
from cli_anything.homeassistant.core import events as events_core
from cli_anything.homeassistant.core import helpers as helpers_core
from cli_anything.homeassistant.core import history as history_core
from cli_anything.homeassistant.core import lovelace as lovelace_core
from cli_anything.homeassistant.core import areas as areas_core
from cli_anything.homeassistant.core import assist as assist_core
from cli_anything.homeassistant.core import backup as backup_core
from cli_anything.homeassistant.core import blueprints as blueprints_core
from cli_anything.homeassistant.core import calendars as calendars_core
from cli_anything.homeassistant.core import energy as energy_core
from cli_anything.homeassistant.core import themes as themes_core
from cli_anything.homeassistant.core import tts as tts_core
from cli_anything.homeassistant.core import control as control_core
from cli_anything.homeassistant.core import diagnostics as diagnostics_core
from cli_anything.homeassistant.core import floors as floors_core
from cli_anything.homeassistant.core import groups as groups_core
from cli_anything.homeassistant.core import inspect as inspect_core
from cli_anything.homeassistant.core import labels as labels_core
from cli_anything.homeassistant.core import logger as logger_core
from cli_anything.homeassistant.core import lovelace_cards as lovelace_cards_core
from cli_anything.homeassistant.core import lovelace_card_builders as lovelace_builders_core
from cli_anything.homeassistant.core import lovelace_card_ops as lovelace_card_ops_core
from cli_anything.homeassistant.core import lovelace_card_types as lovelace_card_types_core
from cli_anything.homeassistant.core import lovelace_card_validate as lovelace_validate_core
from cli_anything.homeassistant.core import lovelace_badges as lovelace_badges_core
from cli_anything.homeassistant.core import lovelace_sections as lovelace_sections_core
from cli_anything.homeassistant.core import lovelace_paths as lovelace_paths_core
from cli_anything.homeassistant.core import mqtt_discovery as mqtt_discovery_core
from cli_anything.homeassistant.core import notifications as notifications_core
from cli_anything.homeassistant.core import persons as persons_core
from cli_anything.homeassistant.core import references as references_core
from cli_anything.homeassistant.core import repairs as repairs_core
from cli_anything.homeassistant.core import statistics as statistics_core
from cli_anything.homeassistant.core import tags as tags_core
from cli_anything.homeassistant.core import updates as updates_core
from cli_anything.homeassistant.core import watch as watch_core
from cli_anything.homeassistant.core import lovelace_mirror as lovelace_mirror_core
from cli_anything.homeassistant.core import project
from cli_anything.homeassistant.core import registry as registry_core
from cli_anything.homeassistant.core import script as script_core
from cli_anything.homeassistant.core import services as services_core
from cli_anything.homeassistant.core import states as states_core
from cli_anything.homeassistant.core import assist_satellite as assist_satellite_core
from cli_anything.homeassistant.core import auth_tokens as auth_tokens_core
from cli_anything.homeassistant.core import camera_ws as camera_ws_core
from cli_anything.homeassistant.core import categories as categories_core
from cli_anything.homeassistant.core import conversation_advanced as conversation_advanced_core
from cli_anything.homeassistant.core import device_automation as device_automation_core
from cli_anything.homeassistant.core import expose_entity as expose_entity_core
from cli_anything.homeassistant.core import hacs as hacs_core
from cli_anything.homeassistant.core import hardware_info as hardware_info_core
from cli_anything.homeassistant.core import logger_ws as logger_ws_core
from cli_anything.homeassistant.core import media_source as media_source_core
from cli_anything.homeassistant.core import mobile_app as mobile_app_core
from cli_anything.homeassistant.core import recorder as recorder_core
from cli_anything.homeassistant.core import scenes as scenes_core
from cli_anything.homeassistant.core import service_shortcuts as service_shortcuts_core
from cli_anything.homeassistant.core import entity_control as entity_control_core
from cli_anything.homeassistant.core import powercalc as powercalc_core
from cli_anything.homeassistant.core import powercalc_calibration as powercalc_calibration_core
from cli_anything.homeassistant.core import powercalc_regression as powercalc_regression_core
from cli_anything.homeassistant.core import shopping_list as shopping_list_core
from cli_anything.homeassistant.core import singletons as singletons_core
from cli_anything.homeassistant.core import subentries as subentries_core
from cli_anything.homeassistant.core import system as system_core
from cli_anything.homeassistant.core import system_log as system_log_core
from cli_anything.homeassistant.core import system_ops as system_ops_core
from cli_anything.homeassistant.core import template as template_core
from cli_anything.homeassistant.core import template_helpers as template_helpers_core
from cli_anything.homeassistant.core import todos as todos_core
from cli_anything.homeassistant.core import user_admin as user_admin_core
from cli_anything.homeassistant.core import weather_advanced as weather_advanced_core
from cli_anything.homeassistant.core import zone as zone_core
from cli_anything.homeassistant.core import webhook as webhook_core
from cli_anything.homeassistant.core import image as image_core
from cli_anything.homeassistant.core import profiler as profiler_core
from cli_anything.homeassistant.core import backup_advanced as backup_advanced_core
from cli_anything.homeassistant.core import calendar_ws as calendar_ws_core
from cli_anything.homeassistant.core import diagnostics_dl as diagnostics_dl_core
from cli_anything.homeassistant.core import entity_registry_extras as entity_registry_extras_core
from cli_anything.homeassistant.core import frontend_prefs as frontend_prefs_core
from cli_anything.homeassistant.core import network as network_core
from cli_anything.homeassistant.core import energy_advanced as energy_advanced_core
from cli_anything.homeassistant.core import statistics_admin as statistics_admin_core
from cli_anything.homeassistant.core import helper_previews as helper_previews_core
from cli_anything.homeassistant.core import history_ext as history_ext_core
from cli_anything.homeassistant.core import history_logbook as history_logbook_core
from cli_anything.homeassistant.core import lovelace_layout_lint as lovelace_layout_lint_core
from cli_anything.homeassistant.core import lovelace_sections_ext as lovelace_sections_ext_core
from cli_anything.homeassistant.core import lovelace_views as lovelace_views_core
from cli_anything.homeassistant.core import state_stream as state_stream_core
from cli_anything.homeassistant.core import trace_debug as trace_debug_core
from cli_anything.homeassistant.core import trace_debugger as trace_debugger_core
from cli_anything.homeassistant.utils.homeassistant_backend import (
    HomeAssistantClient,
    HomeAssistantError,
)
from cli_anything.homeassistant.utils.repl_skin import ReplSkin

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


# ──────────────────────────────────────────────────────────────────────── helpers

def make_client(ctx: click.Context) -> HomeAssistantClient:
    obj = ctx.obj
    return HomeAssistantClient(
        url=obj["url"],
        token=obj["token"],
        verify_ssl=obj["verify_ssl"],
        timeout=obj["timeout"],
    )


def emit(ctx: click.Context, data) -> None:
    """Print results in JSON or human form depending on --json."""
    if ctx.obj.get("as_json"):
        click.echo(json.dumps(data, indent=2, default=str, sort_keys=True))
        return
    if isinstance(data, str):
        click.echo(data)
    elif isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                click.echo(f"{k}: {json.dumps(v, default=str)}")
            else:
                click.echo(f"{k}: {v}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                click.echo(json.dumps(item, default=str))
            else:
                click.echo(str(item))
    elif data is None:
        pass
    else:
        click.echo(str(data))


def _validate_card_or_abort(card_or_dash, *, client=None,
                              skip: bool = False, is_dashboard: bool = False) -> None:
    """Run lovelace_card_validate on a card (or full dashboard).

    Aborts the CLI with ``click.ClickException`` if any ``error``-severity
    issue is found. Warnings are printed to stderr and the caller is allowed
    to proceed.

    Pass ``skip=True`` (wired to a CLI ``--no-validate`` flag) to bypass
    entirely — useful when the validator's heuristics are wrong, or when
    posting a card whose plugin will be installed later.
    """
    if skip:
        return
    try:
        if is_dashboard:
            issues = lovelace_validate_core.validate_dashboard(card_or_dash, client=client)
        else:
            installed = (lovelace_validate_core.installed_card_types(client)
                          if client is not None else None)
            issues = lovelace_validate_core.validate_card(
                card_or_dash, installed=installed,
            )
    except Exception as exc:
        # Validator itself broke — surface and continue rather than block on a
        # validator bug. (The user can always pass --no-validate.)
        click.echo(f"  [validate] internal error, skipping: {exc}", err=True)
        return
    errors = [i for i in issues if i.get("severity") == "error"]
    warnings = [i for i in issues if i.get("severity") == "warning"]
    for w in warnings:
        click.echo(f"  [validate] WARN {w.get('path') or '<root>'}: "
                    f"{w.get('message')}", err=True)
    if errors:
        body = lovelace_validate_core.format_issues(errors)
        raise click.ClickException(
            f"lovelace validation failed ({len(errors)} error(s)):\n"
            f"{body}\n\n(pass --no-validate to override)"
        )


def _config_diff(current, new, *, label_a: str = "live",
                  label_b: str = "new") -> str:
    """Return a unified diff string between two JSON-serialisable configs.

    Used by ``automation save --dry-run`` / ``script save --dry-run`` /
    ``lovelace card insert|delete --dry-run`` to let agents preview a
    destructive write before committing. ``current`` may be ``None`` (e.g.
    new entity) — the diff then shows the full new config as additions.
    """
    import difflib
    a_text = json.dumps(current, indent=2, default=str, sort_keys=True) if current is not None else ""
    b_text = json.dumps(new, indent=2, default=str, sort_keys=True)
    a_lines = a_text.splitlines(keepends=True)
    b_lines = b_text.splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        a_lines, b_lines, fromfile=label_a, tofile=label_b, n=3,
    )) or "(no changes)"


def parse_kv_pairs(pairs: tuple[str, ...]) -> dict:
    """Parse `key=value` pairs into a dict.

    Values are JSON-decoded when possible (so `count=3` becomes int, `flag=true`
    becomes bool, lists/objects work via JSON), otherwise treated as raw strings.
    """
    out: dict = {}
    for raw in pairs:
        if "=" not in raw:
            raise click.BadParameter(f"Expected key=value, got: {raw!r}")
        key, val = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise click.BadParameter(f"Empty key in: {raw!r}")
        try:
            out[key] = json.loads(val)
        except json.JSONDecodeError:
            out[key] = val
    return out


def _abort(message: str) -> None:
    click.echo(f"error: {message}", err=True)
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────── root

@click.group(context_settings=CONTEXT_SETTINGS, invoke_without_command=True)
@click.option("--url", default=None, help="Home Assistant base URL (e.g. http://localhost:8123)")
@click.option("--token", default=None, help="Long-lived access token")
@click.option("--verify-ssl/--no-verify-ssl", default=None, help="Verify TLS cert (default: on)")
@click.option("--timeout", default=None, type=int, help="HTTP timeout in seconds (default 30)")
@click.option("--config", "config_path", default=None, type=click.Path(),
              help="Path to connection profile (defaults to ~/.config/cli-anything-homeassistant.json)")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Emit machine-readable JSON output")
@click.pass_context
def cli(ctx, url, token, verify_ssl, timeout, config_path, as_json):
    """cli-anything-homeassistant — control a running Home Assistant instance."""
    ctx.ensure_object(dict)
    cfg_path_obj = Path(config_path).expanduser() if config_path else None
    cfg = project.load_config(cfg_path_obj)
    ctx.obj["url"] = url or cfg["url"]
    ctx.obj["token"] = token if token is not None else cfg["token"]
    ctx.obj["verify_ssl"] = verify_ssl if verify_ssl is not None else cfg["verify_ssl"]
    ctx.obj["timeout"] = timeout if timeout is not None else cfg["timeout"]
    ctx.obj["as_json"] = as_json
    ctx.obj["config_path"] = cfg_path_obj

    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


def main():
    # Move global flags to the front of argv so they work in any position.
    # Click parses options strictly before subcommands; shifting these here
    # means `cmd subcmd --json` and `cmd --json subcmd` both work.
    GLOBAL_FLAGS = {"--json"}
    GLOBAL_FLAGS_WITH_VALUE = {"--url", "--token", "--timeout", "--config"}
    if len(sys.argv) > 1:
        rest, hoist = [sys.argv[0]], []
        i = 1
        argv = sys.argv
        while i < len(argv):
            tok = argv[i]
            if tok in GLOBAL_FLAGS:
                hoist.append(tok)
                i += 1
            elif tok in GLOBAL_FLAGS_WITH_VALUE and i + 1 < len(argv):
                hoist.extend([tok, argv[i + 1]])
                i += 2
            elif any(tok.startswith(f"{f}=") for f in GLOBAL_FLAGS_WITH_VALUE):
                hoist.append(tok)
                i += 1
            elif tok in {"--verify-ssl", "--no-verify-ssl"}:
                hoist.append(tok)
                i += 1
            else:
                rest.append(tok)
                i += 1
        # Inject hoisted flags after argv[0]
        sys.argv = [rest[0], *hoist, *rest[1:]]
    try:
        cli(obj={})
    except HomeAssistantError as exc:
        _abort(str(exc))


# ──────────────────────────────────────────────────────────────────────── REPL

@cli.command(hidden=True)
@click.pass_context
def repl(ctx):
    """Interactive REPL."""
    skin = ReplSkin("homeassistant", version=__version__)
    skin.print_banner()

    url = ctx.obj["url"]
    if ctx.obj["token"]:
        skin.info(f"Connected profile: {url} (token: ***{ctx.obj['token'][-4:]})")
    else:
        skin.warning(f"No token set for {url}. Run `config set --token <token>`.")

    pt_session = skin.create_prompt_session()

    while True:
        try:
            line = skin.get_input(pt_session, project_name=url)
        except (EOFError, KeyboardInterrupt):
            break

        line = line.strip()
        if not line:
            continue
        if line in ("exit", "quit"):
            break
        if line == "help":
            skin.help({
                "config show/set/save/test": "Connection profile",
                "system info/config/core-state/error-log/components": "Server status",
                "state list/get/set/delete": "Entity states",
                "service list/call": "Services",
                "event list/fire": "Event bus",
                "template render": "Render Jinja templates",
                "area list / device list / entity list": "Registries (WebSocket)",
                "automation list/trigger/toggle/reload": "Automations",
                "script list/run/reload": "Scripts",
                "domain turn-on/turn-off/toggle/list": "Per-domain helpers",
                "history / logbook": "Time-series",
            })
            continue

        try:
            args = shlex.split(line)
            cli.main(args=args, obj=dict(ctx.obj), standalone_mode=False)
        except click.exceptions.UsageError as exc:
            skin.error(str(exc))
        except HomeAssistantError as exc:
            skin.error(str(exc))
        except SystemExit:
            pass
        except Exception as exc:  # noqa: BLE001
            skin.error(f"Unexpected error: {exc}")

    skin.print_goodbye()


# ──────────────────────────────────────────────────────────────────────── config

@cli.group()
@click.pass_context
def config(ctx):
    """Connection profile management."""


@config.command("show")
@click.pass_context
def config_show(ctx):
    """Show the active connection profile (token redacted)."""
    cfg = {
        "url": ctx.obj["url"],
        "token": ctx.obj["token"],
        "verify_ssl": ctx.obj["verify_ssl"],
        "timeout": ctx.obj["timeout"],
    }
    emit(ctx, project.redact(cfg))


@config.command("set")
@click.option("--url", default=None, help="Home Assistant URL")
@click.option("--token", default=None, help="Long-lived access token")
@click.option("--verify-ssl/--no-verify-ssl", default=None)
@click.option("--timeout", default=None, type=int)
@click.pass_context
def config_set(ctx, url, token, verify_ssl, timeout):
    """Set values and save them to the profile file."""
    new_url = url or ctx.obj["url"]
    new_token = token if token is not None else ctx.obj["token"]
    new_verify = verify_ssl if verify_ssl is not None else ctx.obj["verify_ssl"]
    new_timeout = timeout if timeout is not None else ctx.obj["timeout"]
    path = project.save_config(
        url=new_url, token=new_token,
        verify_ssl=new_verify, timeout=new_timeout,
        config_path=ctx.obj.get("config_path"),
    )
    emit(ctx, {
        "saved": str(path),
        "profile": project.redact({
            "url": new_url, "token": new_token,
            "verify_ssl": new_verify, "timeout": new_timeout,
        }),
    })


@config.command("save")
@click.pass_context
def config_save(ctx):
    """Save the in-memory profile values back to disk."""
    path = project.save_config(
        url=ctx.obj["url"], token=ctx.obj["token"],
        verify_ssl=ctx.obj["verify_ssl"], timeout=ctx.obj["timeout"],
        config_path=ctx.obj.get("config_path"),
    )
    emit(ctx, {"saved": str(path)})


@config.command("test")
@click.pass_context
def config_test(ctx):
    """Verify the profile can talk to Home Assistant."""
    client = make_client(ctx)
    data = system_core.status(client)
    emit(ctx, {"connected": True, "url": ctx.obj["url"], **(data if isinstance(data, dict) else {})})


# ──────────────────────────────────────────────────────────────────────── system

@cli.group()
def system():
    """Server-level introspection."""


@system.command("info")
@click.pass_context
def system_info(ctx):
    """Return /api/ status (auth check)."""
    emit(ctx, system_core.status(make_client(ctx)))


@system.command("config")
@click.pass_context
def system_config(ctx):
    """Return /api/config — server config."""
    emit(ctx, system_core.config(make_client(ctx)))


@system.command("core-state")
@click.pass_context
def system_core_state(ctx):
    """Return /api/core/state — running/stopped/etc."""
    emit(ctx, system_core.core_state(make_client(ctx)))


@system.command("error-log")
@click.option("--lines", "-n", default=None, type=int, help="Tail the last N lines")
@click.option("--grep", "-g", default=None,
              help="Only print lines matching this substring (case-insensitive)")
@click.option("--regex", default=None,
              help="Only print lines matching this Python regex (case-insensitive)")
@click.option("--exclude", "-x", multiple=True,
              help="Drop lines matching these substrings (repeatable)")
@click.option("--summary", is_flag=True, default=False,
              help="Show counts by error category instead of raw lines")
@click.option("--since", "since_value", default=None,
              help="Only lines at/after this timestamp. Accepts "
                   "'1h' / '30m' / '15s' / '08:17' / 'YYYY-MM-DD HH:MM:SS' / "
                   "'2h ago'.")
@click.option("--errors-only", is_flag=True, default=False,
              help="Drop WARNING/INFO/DEBUG lines; keep ERROR + CRITICAL only.")
@click.option("--component", default=None,
              help="Filter to a single component (e.g. 'custom_components.hon').")
@click.option("--level", default=None,
              type=click.Choice(["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                                  case_sensitive=False),
              help="Filter to a single log level.")
@click.option("--top", default=None, type=int,
              help="Print the top N buckets instead of raw lines.")
@click.option("--by", default="component",
              type=click.Choice(["component", "level", "hour"]),
              help="What to bucket --top by (default component).")
@click.option("--watch", is_flag=True, default=False,
              help="Poll the log and print only NEW lines as they arrive "
                   "(Ctrl-C to stop). Pair with --grep/--component/--errors-only.")
@click.option("--watch-interval", default=5, type=int,
              help="Poll interval in seconds for --watch (default 5).")
@click.pass_context
def system_error_log(ctx, lines, grep, regex, exclude, summary,
                       since_value, errors_only, component, level,
                       top, by, watch, watch_interval):
    """Return /api/error_log with rich triage filters.

    Examples:
        system error-log -n 200 --grep template
        system error-log --since '1h' --errors-only --top 10 --by component
        system error-log --since '08:17' --component custom_components.hon
        system error-log --watch --errors-only --component homeassistant.components.mqtt.number
        system error-log --summary    # buckets by component / level
    """
    import re as _re
    import time

    # ─── parse --since once ────────────────────────────────────────────
    since_dt = None
    if since_value:
        try:
            since_dt = system_core.parse_since(since_value)
        except ValueError as exc:
            _abort(str(exc))

    # ─── helpers shared by one-shot + watch ────────────────────────────
    pat = _re.compile(regex, _re.IGNORECASE) if regex else None
    exclude_lower = [x.lower() for x in exclude]
    level_upper = level.upper() if level else None

    def _text_filter(line: str) -> bool:
        if grep and grep.lower() not in line.lower():
            return False
        if pat and not pat.search(line):
            return False
        if exclude_lower and any(x in line.lower() for x in exclude_lower):
            return False
        return True

    def _records_after_filters(text: str):
        for rec in system_core.parse_lines(text):
            if not _text_filter(rec["raw"]):
                continue
            yield rec

    def _filtered_text(text: str) -> tuple[str, list[dict]]:
        """Return (joined-text, list-of-structured-records) after every filter."""
        recs = list(system_core.filter_records(
            _records_after_filters(text),
            since=since_dt, errors_only=errors_only,
            component=component, level=level_upper,
        ))
        return "\n".join(r["raw"] for r in recs), recs

    # ─── --watch: poll and print delta ─────────────────────────────────
    if watch:
        seen: set[tuple[str | None, str | None]] = set()
        # bootstrap from current tail so we don't reprint history
        initial = system_core.error_log(make_client(ctx), lines=lines or 5000)
        for r in system_core.parse_lines(initial):
            seen.add((r.get("ts"), r.get("raw")))
        try:
            while True:
                time.sleep(max(1, watch_interval))
                text = system_core.error_log(make_client(ctx), lines=lines or 5000)
                for r in system_core.parse_lines(text):
                    key = (r.get("ts"), r.get("raw"))
                    if key in seen:
                        continue
                    seen.add(key)
                    if not _text_filter(r["raw"]):
                        continue
                    if since_dt and r.get("ts_dt") and r["ts_dt"] < since_dt:
                        continue
                    if errors_only and r.get("level") not in ("ERROR", "CRITICAL"):
                        continue
                    if component and r.get("component") != component:
                        continue
                    if level_upper and r.get("level") != level_upper:
                        continue
                    click.echo(r["raw"])
        except KeyboardInterrupt:
            return

    # ─── one-shot fetch ────────────────────────────────────────────────
    text = system_core.error_log(make_client(ctx), lines=lines)
    filtered_text, recs = _filtered_text(text)

    # ─── --top: bucket and print ───────────────────────────────────────
    if top is not None:
        rows = system_core.bucket_counts(recs, by=by, top=top)
        out = [{"key": k, "count": v} for k, v in rows]
        if ctx.obj.get("as_json"):
            emit(ctx, out)
        else:
            for k, v in rows:
                click.echo(f"  {v:>6}  {k}")
        return

    # ─── --summary: structured rollup ─────────────────────────────────
    if summary:
        from collections import Counter
        by_level_c: Counter[str] = Counter()
        by_component_c: Counter[str] = Counter()
        for r in recs:
            if r.get("level"):
                by_level_c[r["level"]] += 1
            if r.get("component"):
                by_component_c[r["component"]] += 1
        emit(ctx, {
            "by_level": dict(by_level_c.most_common()),
            "by_component": dict(by_component_c.most_common(20)),
            "total_lines": len(filtered_text.splitlines()),
            "matched_records": len(recs),
            "since": since_value,
        })
        return

    if ctx.obj.get("as_json"):
        emit(ctx, {"error_log": filtered_text})
    else:
        click.echo(filtered_text)


@system.command("components")
@click.pass_context
def system_components(ctx):
    """List loaded components."""
    emit(ctx, system_core.components(make_client(ctx)))


@system.command("health")
@click.pass_context
def system_health_cmd(ctx):
    """Return system_health/info via WebSocket."""
    emit(ctx, system_core.system_health(make_client(ctx)))


# ──────────────────────────────────────────────────────────────────────── state

@cli.group()
def state():
    """Entity state operations."""


@state.command("list")
@click.option("--domain", "-d", default=None, help="Filter by domain (e.g. light)")
@click.option("--ids-only", is_flag=True, default=False, help="Only print entity IDs")
@click.pass_context
def state_list(ctx, domain, ids_only):
    """List all entity states (or filter by domain)."""
    items = states_core.list_states(make_client(ctx), domain=domain)
    if ids_only:
        emit(ctx, [s.get("entity_id") for s in items])
    else:
        emit(ctx, items)


@state.command("get")
@click.argument("entity_id")
@click.option("--attribute", "-a", default=None,
              help="Print only this attribute's value (e.g. -a friendly_name)")
@click.option("--state-only", is_flag=True, default=False,
              help="Print only the state string (no attributes, no JSON)")
@click.pass_context
def state_get(ctx, entity_id, attribute, state_only):
    """Get the state of a single entity.

    With --attribute, drill into a single attribute and emit just that
    value (handy in shell pipelines). With --state-only, emit only the
    primary state string.
    """
    full = states_core.get_state(make_client(ctx), entity_id)
    if state_only:
        if ctx.obj.get("as_json"):
            emit(ctx, full.get("state"))
        else:
            click.echo(full.get("state", ""))
        return
    if attribute is not None:
        val = full.get("attributes", {}).get(attribute)
        if val is None and attribute not in full.get("attributes", {}):
            click.echo(f"error: entity {entity_id!r} has no attribute "
                       f"{attribute!r}", err=True)
            sys.exit(1)
        if ctx.obj.get("as_json"):
            emit(ctx, val)
        else:
            click.echo(val if isinstance(val, str) else json.dumps(val))
        return
    emit(ctx, full)


@state.command("set")
@click.argument("entity_id")
@click.argument("state_value")
@click.option("--attr", "-a", multiple=True,
              help="Attribute key=value (repeatable, JSON-decoded values)")
@click.pass_context
def state_set(ctx, entity_id, state_value, attr):
    """Set an entity state (POST /api/states/<entity_id>)."""
    attributes = parse_kv_pairs(attr) if attr else None
    emit(ctx, states_core.set_state(make_client(ctx), entity_id, state_value, attributes))


@state.command("delete")
@click.argument("entity_id")
@click.confirmation_option(
    prompt="Delete this entity from HA's state machine? "
           "(Registry entries are NOT affected; use `entity delete` for those.)")
@click.pass_context
def state_delete(ctx, entity_id):
    """Delete an entity state (DELETE /api/states/<entity_id>).

    Tears down a state entry — useful for stale REST/template-only entities.
    Does NOT touch the entity registry or any UI-managed automation; for
    those use ``entity delete``.
    """
    emit(ctx, states_core.delete_state(make_client(ctx), entity_id))


@state.command("domains")
@click.pass_context
def state_domains(ctx):
    """List unique domains across all states."""
    emit(ctx, states_core.list_domains(make_client(ctx)))


@state.command("counts")
@click.pass_context
def state_counts(ctx):
    """Return per-domain entity counts."""
    emit(ctx, states_core.count_by_domain(make_client(ctx)))


# ──────────────────────────────────────────────────────────────────────── service

@cli.group()
def service():
    """Service registry and service calls."""


@service.command("list")
@click.option("--domain", "-d", default=None, help="Filter to a single domain")
@click.pass_context
def service_list(ctx, domain):
    """List services registered on the server."""
    emit(ctx, services_core.list_services(make_client(ctx), domain=domain))


@service.command("domains")
@click.pass_context
def service_domains(ctx):
    """List service domains."""
    emit(ctx, services_core.list_domains(make_client(ctx)))


@service.command("describe")
@click.argument("domain_arg")
@click.argument("service_arg")
@click.pass_context
def service_describe(ctx, domain_arg, service_arg):
    """Show the registered schema for one service.

    Useful when a `service call` returns 400 and you need to see which
    fields the service accepts, which are required, and their selector
    types — e.g. `service describe notify alexa_media` or
    `service describe ai_task generate_data`.
    """
    info = services_core.get_service(make_client(ctx), domain_arg, service_arg)
    if info is None:
        click.echo(f"error: {domain_arg}.{service_arg} not in service registry",
                   err=True)
        sys.exit(1)
    emit(ctx, info)


@service.command("call")
@click.argument("domain_arg")
@click.argument("service_arg")
@click.option("--data", "-D", multiple=True,
              help="Service data key=value (JSON values supported, repeatable)")
@click.option("--target", "-T", multiple=True,
              help="Target key=value (entity_id=light.kitchen, area_id=living_room, ...)")
@click.option("--return-response", is_flag=True, default=False,
              help="Pass return_response (HA 2024.8+) to receive the service response")
@click.option("--dry-run", is_flag=True, default=False,
              help="Print what would be sent without invoking the service")
@click.pass_context
def service_call(ctx, domain_arg, service_arg, data, target, return_response, dry_run):
    """Call a service: `service call light turn_on -T entity_id=light.kitchen`."""
    sd = parse_kv_pairs(data) if data else None
    tgt = parse_kv_pairs(target) if target else None
    if dry_run:
        emit(ctx, {
            "dry_run": True,
            "domain": domain_arg,
            "service": service_arg,
            "service_data": sd,
            "target": tgt,
            "return_response": return_response,
        })
        return
    result = services_core.call_service(
        make_client(ctx), domain_arg, service_arg,
        service_data=sd, target=tgt, return_response=return_response,
    )
    emit(ctx, result if result is not None else {"called": f"{domain_arg}.{service_arg}"})


# ──────────────────────────────────────────────────────────────────────── event

@cli.group()
def event():
    """Event bus operations."""


@event.command("list")
@click.pass_context
def event_list(ctx):
    """List event listener counts."""
    emit(ctx, events_core.list_listeners(make_client(ctx)))


@event.command("fire")
@click.argument("event_type")
@click.option("--data", "-D", multiple=True,
              help="Event data key=value (JSON values supported, repeatable)")
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def event_fire(ctx, event_type, data, dry_run):
    """Fire an event."""
    payload = parse_kv_pairs(data) if data else None
    if dry_run:
        emit(ctx, {"dry_run": True, "event_type": event_type, "data": payload})
        return
    emit(ctx, events_core.fire_event(make_client(ctx), event_type, payload))


# Note: a second `event subscribe` is defined further down (line ~4075). Both
# are registered under the same Click name; the later definition wins. The
# canonical definition lives there and now carries --filter; this stub is
# kept only as a documentation breadcrumb pointing at the real one.


# ──────────────────────────────────────────────────────────────────────── template

@cli.command("template")
@click.argument("template_str", required=False)
@click.option("--file", "-f", "template_file",
              type=click.Path(exists=True, dir_okay=False),
              help="Read template from this file (use - for stdin)")
@click.option("--var", "-V", multiple=True,
              help="Template variable key=value (repeatable, JSON values)")
@click.pass_context
def template_cmd(ctx, template_str, template_file, var):
    """Render a Jinja2 template against the live state.

    Pass the template as an argument, via --file <path>, or via stdin
    (use --file -). Stdin/file are reliable for multi-line / Jinja-heavy
    templates that shells mangle.
    """
    if template_str is None and template_file is None and not sys.stdin.isatty():
        template_str = sys.stdin.read()
    elif template_file == "-":
        template_str = sys.stdin.read()
    elif template_file:
        template_str = open(template_file).read()
    if not template_str:
        click.echo("error: provide a template argument, --file, or stdin", err=True)
        sys.exit(1)
    variables = parse_kv_pairs(var) if var else None
    text = template_core.render(make_client(ctx), template_str, variables)
    if ctx.obj.get("as_json"):
        emit(ctx, {"rendered": text})
    else:
        click.echo(text)


# ──────────────────────────────────────────────────────────────────────── area / device / entity

@cli.group()
def area():
    """Area registry (WebSocket)."""


@area.command("list")
@click.pass_context
def area_list(ctx):
    emit(ctx, registry_core.list_areas(make_client(ctx)))


@cli.group()
def device():
    """Device registry (WebSocket)."""


@device.command("get")
@click.argument("device_id")
@click.pass_context
def device_get(ctx, device_id):
    """Fetch one device registry record by device_id.

    HA's device-registry WS surface has no "get-one" endpoint, so this
    grabs the full list and returns just the matching record — easier
    than piping `device list` through grep when you have the id from
    e.g. `entity inspect`.
    """
    dev = registry_core.get_device(make_client(ctx), device_id)
    if dev is None:
        click.echo(f"error: device {device_id!r} not found", err=True)
        sys.exit(1)
    emit(ctx, dev)


@device.command("list")
@click.option("--area", "area_id", default=None, help="Filter by area_id")
@click.pass_context
def device_list(ctx, area_id):
    devices = registry_core.list_devices(make_client(ctx))
    if area_id:
        devices = registry_core.filter_devices_by_area(devices, area_id)
    emit(ctx, devices)


@cli.group()
def entity():
    """Entity registry (WebSocket)."""


@entity.command("list")
@click.option("--domain", default=None, help="Filter by domain prefix")
@click.pass_context
def entity_list(ctx, domain):
    entities = registry_core.list_entities(make_client(ctx))
    if domain:
        entities = registry_core.filter_entities_by_domain(entities, domain)
    emit(ctx, entities)


# ──────────────────────────────────────────────────────── registries write

@area.command("create")
@click.argument("name")
@click.option("--floor", "floor_id", default=None)
@click.option("--icon", default=None)
@click.option("--picture", default=None)
@click.option("--alias", "aliases", multiple=True)
@click.option("--label", "labels", multiple=True)
@click.pass_context
def area_create(ctx, name, floor_id, icon, picture, aliases, labels):
    emit(ctx, areas_core.create(
        make_client(ctx), name=name, floor_id=floor_id, icon=icon,
        picture=picture,
        aliases=list(aliases) or None,
        labels=list(labels) or None,
    ))


@area.command("update")
@click.argument("area_id")
@click.option("--name", default=None)
@click.option("--floor", "floor_id", default=None)
@click.option("--icon", default=None)
@click.option("--picture", default=None)
@click.option("--alias", "aliases", multiple=True,
              help="Replace the alias list (repeatable). Pass none to clear.")
@click.option("--label", "labels", multiple=True,
              help="Replace the label list (repeatable). Pass none to clear.")
@click.option("--clear-aliases", is_flag=True, default=False)
@click.option("--clear-labels", is_flag=True, default=False)
@click.pass_context
def area_update(ctx, area_id, name, floor_id, icon, picture,
                  aliases, labels, clear_aliases, clear_labels):
    al = [] if clear_aliases else (list(aliases) if aliases else None)
    lb = [] if clear_labels  else (list(labels)  if labels  else None)
    emit(ctx, areas_core.update(
        make_client(ctx), area_id, name=name, floor_id=floor_id,
        icon=icon, picture=picture, aliases=al, labels=lb,
    ))


@area.command("delete")
@click.argument("area_id")
@click.confirmation_option(prompt="Delete this area?")
@click.pass_context
def area_delete(ctx, area_id):
    emit(ctx, areas_core.delete(make_client(ctx), area_id))


@area.command("find")
@click.argument("ident")
@click.pass_context
def area_find(ctx, ident):
    """Look up an area by area_id OR by case-insensitive name."""
    out = areas_core.find_area(make_client(ctx), ident)
    if not out:
        _abort(f"no area matching {ident!r}")
    emit(ctx, out)


# Floors

@cli.group()
def floor():
    """Floor registry (multi-storey topology above areas)."""


@floor.command("list")
@click.pass_context
def floor_list(ctx):
    emit(ctx, floors_core.list_floors(make_client(ctx)))


@floor.command("create")
@click.argument("name")
@click.option("--level", type=int, default=None,
              help="Storey index (lower=lower; 0=ground)")
@click.option("--icon", default=None)
@click.option("--alias", "aliases", multiple=True)
@click.pass_context
def floor_create(ctx, name, level, icon, aliases):
    emit(ctx, floors_core.create(
        make_client(ctx), name=name, level=level, icon=icon,
        aliases=list(aliases) or None,
    ))


@floor.command("update")
@click.argument("floor_id")
@click.option("--name", default=None)
@click.option("--level", type=int, default=None)
@click.option("--icon", default=None)
@click.option("--alias", "aliases", multiple=True)
@click.option("--clear-aliases", is_flag=True, default=False)
@click.pass_context
def floor_update(ctx, floor_id, name, level, icon, aliases, clear_aliases):
    al = [] if clear_aliases else (list(aliases) if aliases else None)
    emit(ctx, floors_core.update(
        make_client(ctx), floor_id, name=name, level=level, icon=icon,
        aliases=al,
    ))


@floor.command("delete")
@click.argument("floor_id")
@click.confirmation_option(prompt="Delete this floor?")
@click.pass_context
def floor_delete(ctx, floor_id):
    emit(ctx, floors_core.delete(make_client(ctx), floor_id))


@floor.command("find")
@click.argument("ident")
@click.pass_context
def floor_find(ctx, ident):
    out = floors_core.find_floor(make_client(ctx), ident)
    if not out:
        _abort(f"no floor matching {ident!r}")
    emit(ctx, out)


# Labels

@cli.group()
def label():
    """Label registry (cross-cutting tags)."""


@label.command("list")
@click.pass_context
def label_list(ctx):
    emit(ctx, labels_core.list_labels(make_client(ctx)))


@label.command("create")
@click.argument("name")
@click.option("--color", default=None)
@click.option("--icon", default=None)
@click.option("--description", default=None)
@click.pass_context
def label_create(ctx, name, color, icon, description):
    emit(ctx, labels_core.create(
        make_client(ctx), name=name, color=color, icon=icon,
        description=description,
    ))


@label.command("update")
@click.argument("label_id")
@click.option("--name", default=None)
@click.option("--color", default=None)
@click.option("--icon", default=None)
@click.option("--description", default=None)
@click.pass_context
def label_update(ctx, label_id, name, color, icon, description):
    emit(ctx, labels_core.update(
        make_client(ctx), label_id, name=name, color=color, icon=icon,
        description=description,
    ))


@label.command("delete")
@click.argument("label_id")
@click.confirmation_option(prompt="Delete this label?")
@click.pass_context
def label_delete(ctx, label_id):
    emit(ctx, labels_core.delete(make_client(ctx), label_id))


@label.command("find")
@click.argument("ident")
@click.pass_context
def label_find(ctx, ident):
    out = labels_core.find_label(make_client(ctx), ident)
    if not out:
        _abort(f"no label matching {ident!r}")
    emit(ctx, out)


# Entity registry write — single + bulk

@entity.command("update")
@click.argument("entity_id")
@click.option("--name", default=None)
@click.option("--rename", "new_entity_id", default=None,
              help="Change the entity_id slug (also updates references)")
@click.option("--icon", default=None)
@click.option("--area", "area_id", default=None)
@click.option("--label", "labels", multiple=True,
              help="Replace the label list (repeatable)")
@click.option("--alias", "aliases", multiple=True)
@click.option("--clear-labels", is_flag=True, default=False)
@click.option("--clear-aliases", is_flag=True, default=False)
@click.option("--disable", is_flag=True, default=False)
@click.option("--enable", is_flag=True, default=False)
@click.option("--hide", is_flag=True, default=False)
@click.option("--show", is_flag=True, default=False)
@click.pass_context
def entity_update(ctx, entity_id, name, new_entity_id, icon, area_id,
                    labels, aliases, clear_labels, clear_aliases,
                    disable, enable, hide, show):
    """Mutate one entity's registry record."""
    if disable and enable:
        _abort("--disable and --enable are mutually exclusive")
    if hide and show:
        _abort("--hide and --show are mutually exclusive")
    kwargs: dict = {}
    if name is not None: kwargs["name"] = name
    if new_entity_id:    kwargs["new_entity_id"] = new_entity_id
    if icon is not None: kwargs["icon"] = icon
    if area_id is not None: kwargs["area_id"] = area_id
    if clear_labels:        kwargs["labels"] = []
    elif labels:            kwargs["labels"] = list(labels)
    if clear_aliases:       kwargs["aliases"] = []
    elif aliases:           kwargs["aliases"] = list(aliases)
    if disable: kwargs["disabled_by"] = "user"
    if enable:  kwargs["disabled_by"] = None
    if hide:    kwargs["hidden_by"]   = "user"
    if show:    kwargs["hidden_by"]   = None
    emit(ctx, registry_core.update_entity(make_client(ctx), entity_id, **kwargs))


@entity.command("bulk-update")
@click.option("--pattern", default=None,
              help="Regex matched against entity_id")
@click.option("--domain", default=None, help="Restrict to one domain")
@click.option("--area", "area_id", default=None,
              help="Restrict to entities already in this area")
@click.option("--current-label", default=None,
              help="Restrict to entities that already have this label")
@click.option("--integration", default=None,
              help="Restrict to one platform/integration (entity.platform)")
@click.option("--set-name", default=None,
              help="Set the friendly_name on every match")
@click.option("--set-area", default=None,
              help="Move every match to this area")
@click.option("--add-label", "add_labels", multiple=True,
              help="Append labels (repeatable)")
@click.option("--set-labels", "set_labels", multiple=True,
              help="Replace the label list on every match")
@click.option("--remove-label", "remove_labels", multiple=True,
              help="Remove specific labels (repeatable)")
@click.option("--rename-prefix", default=None,
              help="Two-arg form: --rename-prefix 'old_=new_' rewrites entity_id prefixes")
@click.option("--disable", is_flag=True, default=False)
@click.option("--enable", is_flag=True, default=False)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--limit", type=int, default=None,
              help="Only touch the first N matches (useful with --dry-run)")
@click.pass_context
def entity_bulk_update(ctx, pattern, domain, area_id, current_label,
                          integration, set_name, set_area,
                          add_labels, set_labels, remove_labels,
                          rename_prefix, disable, enable, dry_run, limit):
    """Mass-update entities matched by criteria.

    Examples:
      # Move every Sophie's-bedroom entity to the new area
      entity bulk-update --pattern '_sophie_bedroom' --set-area sophie_bedroom

      # Add a `presence_sensor` label to every Aqara FP1E sensitivity entity
      entity bulk-update --pattern 'presence_.*_sensitivity' --add-label presence_sensor

      # Rename pattern: old prefix → new prefix
      entity bulk-update --pattern '^sensor.old_' --rename-prefix 'old_=new_' --dry-run
    """
    if disable and enable:
        _abort("--disable and --enable are mutually exclusive")
    client = make_client(ctx)
    entities = registry_core.list_entities(client)
    matches = registry_core.match_entities(
        entities,
        pattern=pattern, domain=domain, area_id=area_id,
        label=current_label, integration=integration,
    )
    if limit:
        matches = matches[:limit]

    updates: list[dict] = []
    rp_old, rp_new = None, None
    if rename_prefix:
        if "=" not in rename_prefix:
            _abort("--rename-prefix must be of the form 'old=new'")
        rp_old, rp_new = rename_prefix.split("=", 1)

    for e in matches:
        eid = e.get("entity_id", "")
        row: dict = {"entity_id": eid}
        if set_name is not None: row["name"] = set_name
        if set_area is not None: row["area_id"] = set_area
        current_labels = list(e.get("labels") or [])
        if set_labels:
            new_labels = list(set_labels)
        else:
            new_labels = list(current_labels)  # copy so appends don't alias
            for l in add_labels:
                if l not in new_labels:
                    new_labels.append(l)
            for l in remove_labels:
                if l in new_labels:
                    new_labels.remove(l)
        if new_labels != current_labels:
            row["labels"] = new_labels
        if rp_old and rp_old in eid:
            row["new_entity_id"] = eid.replace(rp_old, rp_new, 1)
        if disable: row["disabled_by"] = "user"
        if enable:  row["disabled_by"] = None
        if len(row) > 1:
            updates.append(row)

    summary = registry_core.bulk_update_entities(client, updates=updates,
                                                  dry_run=dry_run)
    emit(ctx, {
        "matched": len(matches),
        "to_update": len(updates),
        "applied_ok": len(summary["applied"]),
        "failed": len(summary["failed"]),
        "dry_run": dry_run,
        "details": summary,
    })


# Device registry write

@device.command("update")
@click.argument("device_id")
@click.option("--name", "name_by_user", default=None,
              help="User-set name (overrides manufacturer's default)")
@click.option("--area", "area_id", default=None)
@click.option("--label", "labels", multiple=True,
              help="Replace the label list (repeatable)")
@click.option("--clear-labels", is_flag=True, default=False)
@click.option("--disable", is_flag=True, default=False)
@click.option("--enable", is_flag=True, default=False)
@click.pass_context
def device_update(ctx, device_id, name_by_user, area_id, labels,
                    clear_labels, disable, enable):
    if disable and enable:
        _abort("--disable and --enable are mutually exclusive")
    kwargs: dict = {}
    if name_by_user is not None: kwargs["name_by_user"] = name_by_user
    if area_id is not None:      kwargs["area_id"] = area_id
    if clear_labels:             kwargs["labels"] = []
    elif labels:                 kwargs["labels"] = list(labels)
    if disable: kwargs["disabled_by"] = "user"
    if enable:  kwargs["disabled_by"] = None
    emit(ctx, registry_core.update_device(make_client(ctx), device_id, **kwargs))


# Persons

@cli.group()
def person():
    """Person registry (people + their device_trackers)."""


@person.command("list")
@click.pass_context
def person_list(ctx):
    emit(ctx, persons_core.list_persons(make_client(ctx)))


@person.command("create")
@click.argument("name")
@click.option("--user", "user_id", default=None,
              help="Link to this HA user_id")
@click.option("--device-tracker", "device_trackers", multiple=True)
@click.option("--picture", default=None)
@click.pass_context
def person_create(ctx, name, user_id, device_trackers, picture):
    emit(ctx, persons_core.create(
        make_client(ctx), name=name, user_id=user_id,
        device_trackers=list(device_trackers) or None, picture=picture,
    ))


@person.command("update")
@click.argument("person_id")
@click.option("--name", default=None)
@click.option("--user", "user_id", default=None)
@click.option("--device-tracker", "device_trackers", multiple=True)
@click.option("--clear-device-trackers", is_flag=True, default=False)
@click.option("--picture", default=None)
@click.pass_context
def person_update(ctx, person_id, name, user_id, device_trackers,
                    clear_device_trackers, picture):
    dt = [] if clear_device_trackers else (list(device_trackers) if device_trackers else None)
    emit(ctx, persons_core.update(
        make_client(ctx), person_id, name=name, user_id=user_id,
        device_trackers=dt, picture=picture,
    ))


@person.command("delete")
@click.argument("person_id")
@click.confirmation_option(prompt="Delete this person?")
@click.pass_context
def person_delete(ctx, person_id):
    emit(ctx, persons_core.delete(make_client(ctx), person_id))


# Tags

@cli.group()
def tag():
    """NFC tags + Home Assistant tag IDs."""


@tag.command("list")
@click.pass_context
def tag_list(ctx):
    emit(ctx, tags_core.list_tags(make_client(ctx)))


@tag.command("create")
@click.argument("tag_id")
@click.option("--name", default=None, help="Friendly name for the tag")
@click.option("--description", default=None)
@click.pass_context
def tag_create(ctx, tag_id, name, description):
    """Register a new tag in HA via ``tag/create``."""
    emit(ctx, tags_core.create(make_client(ctx), tag_id,
                                 name=name, description=description))


@tag.command("update")
@click.argument("tag_id")
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.pass_context
def tag_update(ctx, tag_id, name, description):
    emit(ctx, tags_core.update(make_client(ctx), tag_id,
                                 name=name, description=description))


@tag.command("delete")
@click.argument("tag_id")
@click.confirmation_option(prompt="Delete this tag from the registry?")
@click.pass_context
def tag_delete(ctx, tag_id):
    """Remove a tag via ``tag/delete``. Automations bound to this tag stop firing silently."""
    emit(ctx, tags_core.delete(make_client(ctx), tag_id))


# ──────────────────────────────────────────────────────────────────────── automation

@cli.group()
def automation():
    """Automation operations."""


@automation.command("list")
@click.pass_context
def automation_list(ctx):
    emit(ctx, automation_core.list_automations(make_client(ctx)))


@automation.command("trigger")
@click.argument("entity_id")
@click.option("--skip-condition", is_flag=True, default=False)
@click.pass_context
def automation_trigger(ctx, entity_id, skip_condition):
    emit(ctx, automation_core.trigger(make_client(ctx), entity_id, skip_condition=skip_condition))


@automation.command("toggle")
@click.argument("entity_id")
@click.pass_context
def automation_toggle(ctx, entity_id):
    emit(ctx, automation_core.toggle(make_client(ctx), entity_id))


@automation.command("turn-on")
@click.argument("entity_id")
@click.pass_context
def automation_turn_on(ctx, entity_id):
    emit(ctx, automation_core.turn_on(make_client(ctx), entity_id))


@automation.command("turn-off")
@click.argument("entity_id")
@click.pass_context
def automation_turn_off(ctx, entity_id):
    emit(ctx, automation_core.turn_off(make_client(ctx), entity_id))


@automation.command("reload")
@click.pass_context
def automation_reload(ctx):
    emit(ctx, automation_core.reload(make_client(ctx)))


@automation.command("traces")
@click.argument("entity_id")
@click.option("--limit", "-n", type=int, default=None,
              help="Return only the most-recent N traces. Default: all "
                   "(HA keeps up to 5 per automation).")
@click.option("--since", default=None,
              help="Only return traces whose start time is within the "
                   "given window. Accepts a duration like '30s', '5m', "
                   "'2h', '1d', or an ISO-8601 timestamp.")
@click.pass_context
def automation_traces(ctx, entity_id, limit, since):
    """List recent execution traces for an automation (most recent last)."""
    traces = automation_core.list_traces(make_client(ctx), entity_id) or []
    if since:
        cutoff = _resolve_since(since)
        traces = [t for t in traces
                  if _trace_start(t) and _trace_start(t) >= cutoff]
    if limit is not None and limit >= 0:
        traces = traces[-limit:]
    emit(ctx, traces)


def _resolve_since(value: str):
    """Parse '30s'/'5m'/'2h'/'1d' or an ISO-8601 timestamp into an aware datetime."""
    import re
    from datetime import datetime, timedelta, timezone
    m = re.fullmatch(r"\s*(\d+)\s*([smhdSMHD])\s*", value)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {"s": timedelta(seconds=n), "m": timedelta(minutes=n),
                 "h": timedelta(hours=n),   "d": timedelta(days=n)}[unit]
        return datetime.now(timezone.utc) - delta
    # ISO-8601 fallback. Accept trailing 'Z' as +00:00.
    iso = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _trace_start(trace: dict):
    """Return the trace's start time as an aware datetime, or None."""
    from datetime import datetime, timezone
    ts = ((trace.get("timestamp") or {}).get("start"))
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@automation.command("trace")
@click.argument("entity_id")
@click.option("--run-id", default=None,
              help="Specific run_id to fetch (default: most recent)")
@click.option("--summary", is_flag=True, default=False,
              help="Compact: just trigger / condition outcomes / "
                   "result, instead of the full action-by-action trace")
@click.pass_context
def automation_trace(ctx, entity_id, run_id, summary):
    """Fetch a single execution trace.

    Use this when an automation didn't fire (or fired wrong) and you
    want to know why: which trigger ran, did the conditions pass, did
    any action fail.
    """
    full = automation_core.get_trace(make_client(ctx), entity_id, run_id=run_id)
    if not summary:
        emit(ctx, full)
        return
    # Compact view
    out = {
        "run_id": full.get("run_id"),
        "timestamp_start": full.get("timestamp", {}).get("start"),
        "timestamp_finish": full.get("timestamp", {}).get("finish"),
        "trigger": (full.get("trace", {}).get("trigger", [{}])[0]
                    .get("result", {}).get("description")
                    if full.get("trace", {}).get("trigger") else None),
        "condition_result": full.get("script_execution"),
        "error": full.get("error"),
        "state": full.get("state"),
    }
    emit(ctx, out)


# ──────────────────────────────────────────────────────────────────────── script

@cli.group()
def script():
    """Script operations."""


@script.command("list")
@click.pass_context
def script_list(ctx):
    emit(ctx, script_core.list_scripts(make_client(ctx)))


@script.command("run")
@click.argument("entity_id")
@click.option("--var", "-V", multiple=True, help="Script variable key=value")
@click.pass_context
def script_run(ctx, entity_id, var):
    variables = parse_kv_pairs(var) if var else None
    emit(ctx, script_core.run(make_client(ctx), entity_id, variables=variables))


@script.command("reload")
@click.pass_context
def script_reload(ctx):
    emit(ctx, script_core.reload(make_client(ctx)))


@script.command("traces")
@click.argument("entity_id")
@click.pass_context
def script_traces(ctx, entity_id):
    """List recent execution traces for a script (most recent last)."""
    emit(ctx, script_core.list_traces(make_client(ctx), entity_id))


@script.command("trace")
@click.argument("entity_id")
@click.option("--run-id", default=None,
              help="Specific run id (default: most recent)")
@click.pass_context
def script_trace(ctx, entity_id, run_id):
    """Fetch the full trace dict for a single script run."""
    emit(ctx, script_core.get_trace(make_client(ctx), entity_id, run_id))


# ──────────────────────────────────────────────────────────────────────── domain helpers

@cli.group()
def domain():
    """Per-domain shortcuts (turn-on/off/toggle for any controllable domain)."""


@domain.command("list")
@click.argument("domain_name")
@click.pass_context
def domain_list(ctx, domain_name):
    emit(ctx, domain_core.list_entities(make_client(ctx), domain_name))


@domain.command("turn-on")
@click.argument("domain_name")
@click.argument("entity_id", required=False)
@click.option("--data", "-D", multiple=True)
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def domain_turn_on(ctx, domain_name, entity_id, data, dry_run):
    extra = parse_kv_pairs(data) if data else None
    if dry_run:
        emit(ctx, {"dry_run": True, "domain": domain_name, "service": "turn_on",
                   "entity_id": entity_id, "data": extra})
        return
    emit(ctx, domain_core.turn_on(make_client(ctx), domain_name, entity_id, extra))


@domain.command("turn-off")
@click.argument("domain_name")
@click.argument("entity_id", required=False)
@click.option("--data", "-D", multiple=True)
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def domain_turn_off(ctx, domain_name, entity_id, data, dry_run):
    extra = parse_kv_pairs(data) if data else None
    if dry_run:
        emit(ctx, {"dry_run": True, "domain": domain_name, "service": "turn_off",
                   "entity_id": entity_id, "data": extra})
        return
    emit(ctx, domain_core.turn_off(make_client(ctx), domain_name, entity_id, extra))


@domain.command("toggle")
@click.argument("domain_name")
@click.argument("entity_id", required=False)
@click.option("--data", "-D", multiple=True)
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def domain_toggle(ctx, domain_name, entity_id, data, dry_run):
    extra = parse_kv_pairs(data) if data else None
    if dry_run:
        emit(ctx, {"dry_run": True, "domain": domain_name, "service": "toggle",
                   "entity_id": entity_id, "data": extra})
        return
    emit(ctx, domain_core.toggle(make_client(ctx), domain_name, entity_id, extra))


# ──────────────────────────────────────────────────────────────────────── history / logbook

@cli.command("history")
@click.option("--entity", "-e", "entity_ids", multiple=True,
              help="Filter to entity_id (repeatable)")
@click.option("--hours", default=None, type=float,
              help="Look back N hours from now (start = now - N, end = now)")
@click.option("--start", "start_iso", default=None,
              help="Explicit ISO-8601 start time (e.g. 2026-05-01T00:00:00)")
@click.option("--end", "end_iso", default=None,
              help="Explicit ISO-8601 end time")
@click.option("--minimal/--full", "minimal", default=True)
@click.option("--no-attributes", is_flag=True, default=False,
              help="Omit per-sample attributes blob. Big speed/size win on "
                   "installs with heavy entities.")
@click.option("--significant-changes-only", is_flag=True, default=False,
              help="Only return samples representing a meaningful state "
                   "change. Trades resolution for response size.")
@click.pass_context
def history_cmd(ctx, entity_ids, hours, start_iso, end_iso, minimal,
                no_attributes, significant_changes_only):
    """Return historical state changes.

    NOTE: HA's history API returns at most one 24-hour slice per call,
    starting at the `start` time. ``--hours 168`` does NOT return seven
    days — it returns the FIRST 24 hours of that 7-day window. Pass
    explicit ``--start`` and ``--end`` for arbitrary ranges, or call
    repeatedly with different starts.
    """
    from datetime import datetime, timedelta, timezone
    start, end = None, None
    if hours is not None:
        start = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    if start_iso:
        start = datetime.fromisoformat(start_iso)
    if end_iso:
        end = datetime.fromisoformat(end_iso)
    emit(ctx, history_core.history(
        make_client(ctx),
        entity_ids=list(entity_ids) if entity_ids else None,
        start=start, end=end,
        minimal_response=minimal,
        no_attributes=no_attributes,
        significant_changes_only=significant_changes_only,
    ))


# ──────────────────────────────────────────────────────────────────────── recorder

@cli.group()
def recorder():
    """Recorder introspection — entity history depth checks."""


@recorder.command("stats")
@click.argument("entity_ids", nargs=-1, required=True)
@click.option("--hours", default=24.0, type=float,
              help="Window in hours to count history points (default 24)")
@click.pass_context
def recorder_stats(ctx, entity_ids, hours):
    """Show whether each entity has recorded history.

    Example: confirm that a sensor your chart depends on is actually
    being tracked by the recorder:

        cli-anything-homeassistant recorder stats sensor.time_in_range sensor.foo
    """
    result = recorder_core.batch_stats(make_client(ctx), entity_ids, hours=hours)
    emit(ctx, result)


@recorder.command("find-unrecorded")
@click.argument("entity_ids", nargs=-1, required=True)
@click.option("--hours", default=24.0, type=float)
@click.pass_context
def recorder_find_unrecorded(ctx, entity_ids, hours):
    """List entity_ids with ZERO history points in the last N hours."""
    emit(ctx, recorder_core.find_unrecorded(make_client(ctx),
                                              entity_ids, hours=hours))


# ──────────────────────────────────────────────────────────────────────── template-helper

@cli.group("template-helper")
def template_helper():
    """Create / update template helpers (sensor, binary_sensor, etc.)."""


@template_helper.command("create")
@click.option("--name", required=True, help="Display name (also entity slug)")
@click.option("--state", "state_template", default=None,
              help="State template (Jinja2). Use --state-file for long ones.")
@click.option("--state-file", type=click.Path(exists=True, dir_okay=False),
              help="Read state template from this file")
@click.option("--type", "template_type", default="sensor",
              type=click.Choice(["sensor","binary_sensor","number",
                                  "switch","select","button"]),
              help="Helper type (default: sensor)")
@click.option("--unit", "unit_of_measurement", default=None,
              help="Unit of measurement (e.g. Mbps, %)")
@click.option("--device-class", default=None)
@click.option("--state-class", default=None,
              help="e.g. measurement, total, total_increasing")
@click.option("--extra-file", type=click.Path(exists=True, dir_okay=False),
              help="JSON file with extra fields to merge into the submission")
@click.pass_context
def template_helper_create(ctx, name, state_template, state_file, template_type,
                             unit_of_measurement, device_class, state_class,
                             extra_file):
    """Create a NEW template helper via the config-flow API.

    The new entity is registered immediately (survives restart, no
    YAML edits required). Idempotent? NO — calling twice creates two
    helpers with the same name. Use `config-entry options-set` to
    UPDATE an existing one, or `template-helper update` for the same.
    """
    if state_file:
        state_template = open(state_file).read()
    if not state_template:
        click.echo("error: pass --state or --state-file", err=True)
        sys.exit(1)
    extra = None
    if extra_file:
        extra = json.loads(open(extra_file).read())
    emit(ctx, template_helpers_core.create(
        make_client(ctx), name=name, state_template=state_template,
        template_type=template_type,
        unit_of_measurement=unit_of_measurement,
        device_class=device_class, state_class=state_class,
        extra=extra,
    ))


@template_helper.command("update")
@click.argument("entry_id")
@click.option("--name", default=None)
@click.option("--state", "state_template", default=None)
@click.option("--state-file", type=click.Path(exists=True, dir_okay=False))
@click.option("--unit", "unit_of_measurement", default=None)
@click.option("--device-class", default=None)
@click.option("--state-class", default=None)
@click.option("--extra-file", type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def template_helper_update(ctx, entry_id, name, state_template, state_file,
                             unit_of_measurement, device_class, state_class,
                             extra_file):
    """Update an existing template helper. Fields not passed are preserved."""
    if state_file:
        state_template = open(state_file).read()
    extra = None
    if extra_file:
        extra = json.loads(open(extra_file).read())
    emit(ctx, template_helpers_core.update(
        make_client(ctx), entry_id,
        name=name, state_template=state_template,
        unit_of_measurement=unit_of_measurement,
        device_class=device_class, state_class=state_class,
        extra=extra,
    ))


@template_helper.command("show")
@click.argument("ident")
@click.pass_context
def template_helper_show(ctx, ident):
    """Print the current options of a template helper.

    `ident` is either the config-entry id (e.g. `01KR9E...`) or an entity_id
    the helper produces (e.g. `sensor.k8s_cluster_online_label`).
    """
    emit(ctx, template_helpers_core.show(make_client(ctx), ident))


@cli.command("logbook")
@click.option("--entity", "-e", "entity_id", default=None)
@click.option("--hours", default=None, type=float, help="Look back N hours from now")
@click.pass_context
def logbook_cmd(ctx, entity_id, hours):
    """Return logbook entries."""
    emit(ctx, history_core.logbook(make_client(ctx), entity_id=entity_id, hours=hours))


# ──────────────────────────────────────────────────────────────────────── auth / whoami

@cli.command("whoami")
@click.pass_context
def whoami_cmd(ctx):
    """Show which HA user the active token belongs to + admin/owner flags."""
    emit(ctx, auth_tokens_core.current_user(make_client(ctx)))


# ──────────────────────────────────────────────────────── entity references

@cli.command("entity-references")
@click.argument("entity_id")
@click.option("--kind", multiple=True,
              type=click.Choice([
                  "automation", "script", "scene", "template_helper", "lovelace",
              ]),
              help="Restrict the search to specific kinds (repeatable).")
@click.option("--max", "max_hits", default=30, type=int,
              help="Cap per-kind result count (default 30).")
@click.pass_context
def entity_references_cmd(ctx, entity_id, kind, max_hits):
    """Find every UI-managed automation / script / scene / template helper /
    lovelace card that mentions an entity_id.

    Example:  cli-anything-homeassistant entity-references sensor.elt_k8s_3_cpu_usage
    """
    emit(ctx, references_core.find_references(
        make_client(ctx), entity_id,
        include_kinds=set(kind) if kind else None,
        max_hits_per_kind=max_hits,
    ))


# ──────────────────────────────────────────────────────── logger / groups / discovery

@cli.group()
def logger():
    """Runtime log-level control (no restart needed)."""


@logger.command("set")
@click.argument("component")
@click.argument("level",
                 type=click.Choice(sorted(logger_core.VALID_LEVELS),
                                    case_sensitive=False))
@click.pass_context
def logger_set(ctx, component, level):
    """Set one component's log level.

    Examples:
      logger set custom_components.hon critical
      logger set pychromecast.socket_client critical
    """
    emit(ctx, logger_core.set_level(make_client(ctx), {component: level}))


@logger.command("set-many")
@click.argument("pairs", nargs=-1)
@click.pass_context
def logger_set_many(ctx, pairs):
    """Set multiple components in one service call.

    Each PAIRS arg is `component=level`. e.g.
      logger set-many custom_components.hon=critical pychromecast.socket_client=critical
    """
    levels: dict[str, str] = {}
    for p in pairs:
        if "=" not in p:
            _abort(f"expected component=level, got {p!r}")
        k, v = p.split("=", 1)
        levels[k.strip()] = v.strip()
    if not levels:
        _abort("provide at least one component=level pair")
    emit(ctx, logger_core.set_level(make_client(ctx), levels))


@logger.command("default")
@click.argument("level",
                 type=click.Choice(sorted(logger_core.VALID_LEVELS),
                                    case_sensitive=False))
@click.pass_context
def logger_default(ctx, level):
    """Set the global default log level."""
    emit(ctx, logger_core.set_default_level(make_client(ctx), level))


@cli.group()
def group():
    """Group inspection — list members of a light/switch/sensor group."""


@group.command("expand")
@click.argument("entity_id")
@click.option("--no-state", is_flag=True, default=False,
              help="Only print the flat list of entity_ids (no state column)")
@click.pass_context
def group_expand(ctx, entity_id, no_state):
    """List the children of a group, with their current states."""
    if no_state:
        emit(ctx, groups_core.deep_expand(make_client(ctx), entity_id))
    else:
        emit(ctx, groups_core.expand(make_client(ctx), entity_id))


@cli.group("mqtt-discovery")
def mqtt_discovery():
    """HA MQTT-discovery topic management."""


@mqtt_discovery.command("list")
@click.option("--prefix", default="homeassistant",
              help="Discovery topic prefix (default 'homeassistant')")
@click.option("--timeout", default=5.0, type=float,
              help="How long to collect retained messages (default 5s)")
@click.pass_context
def mqtt_discovery_list(ctx, prefix, timeout):
    """Enumerate currently-discovered objects (one row per topic)."""
    emit(ctx, mqtt_discovery_core.list_discovered(
        make_client(ctx), prefix=prefix, timeout=timeout,
    ))


@mqtt_discovery.command("show")
@click.argument("topic")
@click.option("--timeout", default=3.0, type=float)
@click.pass_context
def mqtt_discovery_show(ctx, topic, timeout):
    """Return the retained discovery payload at a specific topic."""
    emit(ctx, mqtt_discovery_core.show(make_client(ctx), topic, timeout=timeout))


@mqtt_discovery.command("delete")
@click.argument("topic")
@click.confirmation_option(prompt="Wipe this discovery topic?")
@click.pass_context
def mqtt_discovery_delete(ctx, topic):
    """Wipe a discovery topic by publishing an empty retained message."""
    emit(ctx, mqtt_discovery_core.delete(make_client(ctx), topic))


@mqtt_discovery.command("republish")
@click.pass_context
def mqtt_discovery_republish(ctx):
    """Ask the MQTT integration to re-emit its discovery topics (reload)."""
    emit(ctx, mqtt_discovery_core.republish(make_client(ctx)))


@cli.group()
def auth():
    """Auth operations (users, long-lived tokens)."""


@auth.command("users")
@click.pass_context
def auth_users(ctx):
    """List HA users (admin only)."""
    emit(ctx, auth_core.list_users(make_client(ctx)))


@auth.group("tokens")
def auth_tokens():
    """Long-lived access tokens."""


@auth_tokens.command("create")
@click.argument("client_name")
@click.option("--lifespan-days", default=3650, type=int,
              help="Token lifespan in days (default 3650 = ~10 years)")
@click.pass_context
def auth_tokens_create(ctx, client_name, lifespan_days):
    """Mint a new long-lived access token under the active user.

    HA only shows the token once — capture it from the output.
    """
    token = auth_core.create_long_lived_token(
        make_client(ctx), client_name, lifespan_days=lifespan_days,
    )
    emit(ctx, {"client_name": client_name, "lifespan_days": lifespan_days, "token": token})


# ──────────────────────────────────────────────────────────────────────── lovelace

@cli.group()
def lovelace():
    """Lovelace dashboard operations (UI configs + resources)."""


@lovelace.group("dashboards")
def lovelace_dashboards():
    """Dashboard inventory."""


@lovelace_dashboards.command("list")
@click.pass_context
def lovelace_dashboards_list(ctx):
    """List all Lovelace dashboards."""
    emit(ctx, lovelace_core.list_dashboards(make_client(ctx)))


@lovelace_dashboards.command("create")
@click.argument("url_path")
@click.argument("title")
@click.option("--mode", default="storage",
              type=click.Choice(["storage", "yaml"]),
              help="Dashboard mode (default storage)")
@click.option("--icon", default=None, help="MDI icon, e.g. mdi:bird")
@click.option("--filename", default=None,
              help="Required for --mode yaml; path under /config")
@click.option("--show-in-sidebar/--no-show-in-sidebar", default=True)
@click.option("--require-admin/--no-require-admin", default=False)
@click.pass_context
def lovelace_dashboards_create(ctx, url_path, title, mode, icon, filename,
                                show_in_sidebar, require_admin):
    """Register a new Lovelace dashboard.

    NOTE: integration-registered dashboards (e.g. UI Lovelace Minimalist
    side panels) aren't in this registry — update them via the owning
    integration's options flow instead.
    """
    emit(ctx, lovelace_core.create_dashboard(
        make_client(ctx), url_path, title,
        mode=mode, icon=icon, filename=filename,
        show_in_sidebar=show_in_sidebar, require_admin=require_admin,
    ))


@lovelace_dashboards.command("update")
@click.argument("dashboard_id")
@click.option("--title", default=None)
@click.option("--icon", default=None)
@click.option("--url-path", default=None,
              help="Change the URL path under which the dashboard is served")
@click.option("--show-in-sidebar/--no-show-in-sidebar", "show_in_sidebar",
              default=None)
@click.option("--require-admin/--no-require-admin", "require_admin",
              default=None)
@click.pass_context
def lovelace_dashboards_update(ctx, dashboard_id, title, icon, url_path,
                                show_in_sidebar, require_admin):
    """Update a Lovelace dashboard's registry entry (storage-mode only).

    Supply only the fields you want to change. The dashboard_id is the
    `id` field from `lovelace dashboards list`.
    """
    emit(ctx, lovelace_core.update_dashboard(
        make_client(ctx), dashboard_id,
        title=title, icon=icon, url_path=url_path,
        show_in_sidebar=show_in_sidebar, require_admin=require_admin,
    ))


@lovelace_dashboards.command("delete")
@click.argument("dashboard_id")
@click.pass_context
def lovelace_dashboards_delete(ctx, dashboard_id):
    """Remove a Lovelace dashboard registration by id."""
    emit(ctx, {
        "deleted": dashboard_id,
        "result": lovelace_core.delete_dashboard(make_client(ctx), dashboard_id),
    })


@lovelace.group("config")
def lovelace_config():
    """Read or write a dashboard's full config."""


@lovelace_config.command("get")
@click.argument("url_path", required=False)
@click.option("--out", "-o", default=None, type=click.Path(),
              help="Write JSON to this file (default: stdout)")
@click.pass_context
def lovelace_config_get(ctx, url_path, out):
    """Fetch the config of a dashboard (omit url_path for the main 'lovelace')."""
    cfg = lovelace_core.get_dashboard_config(make_client(ctx), url_path)
    text = json.dumps(cfg, indent=2, default=str, sort_keys=True)
    if out:
        Path(out).write_text(text)
        emit(ctx, {"saved": out, "size_bytes": len(text)})
    else:
        click.echo(text)


@lovelace_config.command("save")
@click.argument("url_path")
@click.argument("config_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, default=False,
              help="Show a unified diff vs the live dashboard; do not write.")
@click.option("--yes", "-y", is_flag=True, default=False,
              help="Skip the interactive confirmation (required for scripted use).")
@click.pass_context
def lovelace_config_save(ctx, url_path, config_file, dry_run, yes):
    """Replace a dashboard's config from a JSON file.

    Wholesale dashboard overwrite — a typo here erases every view and card on
    the target dashboard. Without --yes the command prompts; with --dry-run
    it prints a unified diff vs the live config and exits without writing.
    """
    cfg = json.loads(Path(config_file).read_text())
    client = make_client(ctx)
    if dry_run:
        try:
            current = lovelace_core.get_dashboard_config(client, url_path)
        except Exception:
            current = None
        emit(ctx, {
            "dry_run": True, "url_path": url_path,
            "view_count": len(cfg.get("views", [])),
            "diff": _config_diff(current, cfg,
                                  label_a=f"live:{url_path}",
                                  label_b=f"new:{config_file}"),
        })
        return
    if not yes and not click.confirm(
        f"Overwrite ENTIRE dashboard {url_path!r} "
        f"({len(cfg.get('views', []))} views in new config)?",
        default=False,
    ):
        raise click.ClickException("aborted")
    result = lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"saved": url_path, "result": result})


# ──────────────────────────────────────────────────────── lovelace surgical edits

def _fetch_dash_cfg(ctx, url_path: str) -> dict:
    return lovelace_core.get_dashboard_config(make_client(ctx), url_path)


def _push_dash_cfg(ctx, url_path: str, cfg: dict, *, dry_run: bool) -> dict:
    if dry_run:
        return {"dry_run": True, "view_count": len(cfg.get("views", []))}
    return {
        "saved": url_path,
        "result": lovelace_core.save_dashboard_config(make_client(ctx), url_path, cfg),
    }


@lovelace.group("view")
def lovelace_view():
    """Surgical edits at the view level — get/set/add/delete by view path slug."""


@lovelace_view.command("get")
@click.argument("url_path")
@click.argument("view_path")
@click.option("-o", "--out", type=click.Path(), default=None,
              help="Write the view JSON to a file (default: stdout)")
@click.pass_context
def lovelace_view_get(ctx, url_path, view_path, out):
    """Print (or save) one view from a dashboard."""
    cfg = _fetch_dash_cfg(ctx, url_path)
    view = lovelace_paths_core.get_view(cfg, view_path)
    if out:
        Path(out).write_text(json.dumps(view, indent=2, default=str))
        emit(ctx, {"wrote": out, "bytes": Path(out).stat().st_size})
    else:
        emit(ctx, view)


@lovelace_view.command("set")
@click.argument("url_path")
@click.argument("view_path")
@click.argument("view_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--no-validate", is_flag=True, default=False,
              help="Skip lovelace_card_validate on the cards in this view.")
@click.pass_context
def lovelace_view_set(ctx, url_path, view_path, view_file, dry_run, no_validate):
    """Replace one view in a dashboard from a JSON file."""
    new_view = json.loads(Path(view_file).read_text())
    client = make_client(ctx)
    for card in new_view.get("cards", []) or []:
        _validate_card_or_abort(card, client=client, skip=no_validate)
    cfg = _fetch_dash_cfg(ctx, url_path)
    lovelace_paths_core.set_view(cfg, view_path, new_view)
    emit(ctx, _push_dash_cfg(ctx, url_path, cfg, dry_run=dry_run))


@lovelace_view.command("add")
@click.argument("url_path")
@click.argument("view_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--index", type=int, default=None,
              help="Insert at this index (default: append)")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--no-validate", is_flag=True, default=False,
              help="Skip lovelace_card_validate on the cards in this view.")
@click.pass_context
def lovelace_view_add(ctx, url_path, view_file, index, dry_run, no_validate):
    """Append (or insert at --index) a new view from a JSON file."""
    new_view = json.loads(Path(view_file).read_text())
    client = make_client(ctx)
    for card in new_view.get("cards", []) or []:
        _validate_card_or_abort(card, client=client, skip=no_validate)
    cfg = _fetch_dash_cfg(ctx, url_path)
    lovelace_paths_core.add_view(cfg, new_view, index=index)
    emit(ctx, _push_dash_cfg(ctx, url_path, cfg, dry_run=dry_run))


@lovelace_view.command("delete")
@click.argument("url_path")
@click.argument("view_path")
@click.confirmation_option(prompt="Delete this view?")
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def lovelace_view_delete(ctx, url_path, view_path, dry_run):
    """Remove a view from a dashboard by path."""
    cfg = _fetch_dash_cfg(ctx, url_path)
    lovelace_paths_core.delete_view(cfg, view_path)
    emit(ctx, _push_dash_cfg(ctx, url_path, cfg, dry_run=dry_run))


@lovelace.group("section")
def lovelace_section():
    """Surgical edits at the section level."""


@lovelace_section.command("get")
@click.argument("url_path")
@click.argument("view_path")
@click.argument("section_idx", type=int)
@click.pass_context
def lovelace_section_get(ctx, url_path, view_path, section_idx):
    cfg = _fetch_dash_cfg(ctx, url_path)
    emit(ctx, lovelace_paths_core.get_section(cfg, view_path, section_idx))


@lovelace_section.command("set")
@click.argument("url_path")
@click.argument("view_path")
@click.argument("section_idx", type=int)
@click.argument("section_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--no-validate", is_flag=True, default=False,
              help="Skip lovelace_card_validate on the cards in this section.")
@click.pass_context
def lovelace_section_set(ctx, url_path, view_path, section_idx, section_file, dry_run, no_validate):
    new_section = json.loads(Path(section_file).read_text())
    client = make_client(ctx)
    for card in new_section.get("cards", []) or []:
        _validate_card_or_abort(card, client=client, skip=no_validate)
    cfg = _fetch_dash_cfg(ctx, url_path)
    lovelace_paths_core.set_section(cfg, view_path, section_idx, new_section)
    emit(ctx, _push_dash_cfg(ctx, url_path, cfg, dry_run=dry_run))


# Card-level surgical edits live under the existing `lovelace card` group
# (lovelace_cards_core, defined further down) — its pointer-based commands
# (get/replace/delete/find/insert) cover the same ground.


@lovelace.command("search")
@click.argument("url_path")
@click.argument("query")
@click.option("--limit", type=int, default=50)
@click.option("--case-sensitive", is_flag=True, default=False)
@click.pass_context
def lovelace_search(ctx, url_path, query, limit, case_sensitive):
    """Free-text search for any view/section/card field matching `query`.

    Returns one row per matching node: path, type, title, match field + snippet.
    """
    cfg = _fetch_dash_cfg(ctx, url_path)
    emit(ctx, lovelace_paths_core.search(
        cfg, query, case_sensitive=case_sensitive, limit=limit,
    ))


@lovelace.command("paths")
@click.argument("url_path")
@click.option("--depth", "max_depth", default=4, type=int,
              help="3=stop at sections, 4=down to cards (default)")
@click.pass_context
def lovelace_paths_cmd(ctx, url_path, max_depth):
    """Print every view/section/card path with its type and title."""
    cfg = _fetch_dash_cfg(ctx, url_path)
    emit(ctx, lovelace_paths_core.list_paths(cfg, max_depth=max_depth))


@lovelace.group("resources")
def lovelace_resources():
    """Lovelace resource registrations (custom card JS/CSS modules)."""


@lovelace_resources.command("list")
@click.pass_context
def lovelace_resources_list(ctx):
    """List registered Lovelace resources."""
    emit(ctx, lovelace_core.list_resources(make_client(ctx)))


@lovelace_resources.command("delete")
@click.argument("resource_id")
@click.pass_context
def lovelace_resources_delete(ctx, resource_id):
    """Remove a Lovelace resource registration by id."""
    emit(ctx, {"deleted": resource_id, "result": lovelace_core.delete_resource(make_client(ctx), resource_id)})


@lovelace_resources.command("create")
@click.argument("url")
@click.option("--type", "res_type", default="module",
              type=click.Choice(["module", "css", "js"]))
@click.pass_context
def lovelace_resources_create(ctx, url, res_type):
    """Register a new Lovelace resource."""
    emit(ctx, lovelace_core.create_resource(make_client(ctx), url, res_type))


# ──────────────────────────────────────────────────────────── lovelace card editor

@lovelace.group("card")
def lovelace_card():
    """Surgical card-level editing within a dashboard.

    Pointer addressing: views[N]/cards[M]/cards[X] walks the tree.
    """


@lovelace_card.command("find")
@click.argument("url_path")
@click.option("--type", "card_type", default=None, help="Match cards with this 'type:'")
@click.option("--entity", default=None, help="Match cards referencing this entity_id")
@click.option("--contains", default=None,
              help="Match cards whose serialised JSON contains this substring")
@click.pass_context
def lovelace_card_find(ctx, url_path, card_type, entity, contains):
    """List cards matching the given criteria, with their pointers."""
    cfg = lovelace_core.get_dashboard_config(make_client(ctx), url_path)
    hits = lovelace_cards_core.find_cards(
        cfg, card_type=card_type, entity=entity, contains=contains,
    )
    out = [{"pointer": p, "type": c.get("type"),
            "title": c.get("title") or c.get("name") or c.get("entity")}
           for p, c in hits]
    emit(ctx, out)


@lovelace_card.command("get")
@click.argument("url_path")
@click.argument("pointer")
@click.option("--out", "-o", default=None, type=click.Path())
@click.pass_context
def lovelace_card_get(ctx, url_path, pointer, out):
    """Fetch a single card from a dashboard by pointer."""
    cfg = lovelace_core.get_dashboard_config(make_client(ctx), url_path)
    try:
        card = lovelace_cards_core.get_card(cfg, pointer)
    except (KeyError, IndexError, ValueError) as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    text = json.dumps(card, indent=2, default=str, sort_keys=True)
    if out:
        Path(out).write_text(text)
        emit(ctx, {"saved": out, "size_bytes": len(text)})
    else:
        click.echo(text)


@lovelace_card.command("replace")
@click.argument("url_path")
@click.argument("pointer")
@click.argument("card_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, default=False,
              help="Show what would change without saving")
@click.option("--no-validate", is_flag=True, default=False,
              help="Skip lovelace_card_validate (default: validate, abort on error).")
@click.pass_context
def lovelace_card_replace(ctx, url_path, pointer, card_file, dry_run, no_validate):
    """Replace a single card at <pointer> with the JSON from <card_file>."""
    new_card = json.loads(Path(card_file).read_text())
    client = make_client(ctx)
    _validate_card_or_abort(new_card, client=client, skip=no_validate)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        old_card = dict(lovelace_cards_core.get_card(cfg, pointer))
        lovelace_cards_core.replace_card(cfg, pointer, new_card)
    except (KeyError, IndexError, ValueError) as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    summary = {
        "pointer": pointer,
        "old_type": old_card.get("type"),
        "new_type": new_card.get("type"),
        "dry_run": dry_run,
    }
    if dry_run:
        emit(ctx, summary)
        return
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    summary["saved"] = True
    emit(ctx, summary)


@lovelace_card.command("delete")
@click.argument("url_path")
@click.argument("pointer")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation")
@click.option("--dry-run", is_flag=True, default=False,
              help="Describe what would be deleted without saving the dashboard.")
@click.pass_context
def lovelace_card_delete(ctx, url_path, pointer, yes, dry_run):
    """Delete the card at <pointer>."""
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        old_card = dict(lovelace_cards_core.get_card(cfg, pointer))
    except (KeyError, IndexError, ValueError) as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": pointer,
                    "type": old_card.get("type")})
        return
    if not yes and not click.confirm(
        f"Delete {old_card.get('type')!r} card at {pointer}?", default=False,
    ):
        click.echo("aborted")
        return
    lovelace_cards_core.delete_card(cfg, pointer)
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"deleted": pointer, "old_type": old_card.get("type")})


@lovelace_card.command("insert")
@click.argument("url_path")
@click.argument("parent_pointer")
@click.argument("card_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--position", default=None, type=int,
              help="Position in the parent's cards[] (default: append)")
@click.option("--dry-run", is_flag=True, default=False,
              help="Describe what would change without saving the dashboard.")
@click.option("--no-validate", is_flag=True, default=False,
              help="Skip lovelace_card_validate (default: validate, abort on error).")
@click.pass_context
def lovelace_card_insert(ctx, url_path, parent_pointer, card_file, position, dry_run, no_validate):
    """Insert a new card into <parent_pointer>'s cards[] array."""
    new_card = json.loads(Path(card_file).read_text())
    client = make_client(ctx)
    _validate_card_or_abort(new_card, client=client, skip=no_validate)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        lovelace_cards_core.insert_card(cfg, parent_pointer, new_card, position=position)
    except (KeyError, IndexError, ValueError) as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_insert_into": parent_pointer,
                    "type": new_card.get("type"), "position": position})
        return
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"inserted_into": parent_pointer, "type": new_card.get("type"),
               "position": position})


@lovelace.command("lint")
@click.argument("url_path")
@click.option("--check-types", is_flag=True, default=False,
              help="Also flag cards with types that aren't built-in or in lovelace_resources")
@click.option("--templates", "check_templates", is_flag=True, default=False,
              help="Render every Jinja template in the dashboard against the "
                   "live state and flag any that throw")
@click.pass_context
def lovelace_lint(ctx, url_path, check_types, check_templates):
    """Validate a dashboard: dead entity refs, unknown card types."""
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    all_states = states_core.list_states(client)
    all_eids = {s["entity_id"] for s in all_states}
    known_types: set[str] | None = None
    if check_types:
        # Built-in card types are well-known; custom ones come from lovelace_resources.
        builtin = {
            "alarm-panel", "area", "button", "calendar", "conditional", "energy-",
            "entities", "entity", "entity-filter", "gauge", "glance", "grid",
            "history-graph", "horizontal-stack", "humidifier", "iframe",
            "light", "logbook", "map", "markdown", "media-control",
            "picture", "picture-elements", "picture-entity", "picture-glance",
            "plant-status", "sensor", "shopping-list", "statistic", "statistics-graph",
            "statistic-card", "thermostat", "tile", "todo-list", "vertical-stack",
            "weather-forecast",
        }
        known_types = set(builtin)
        # Add any 'custom:*' types from registered resources (we can't enumerate
        # exact card names, so we just allow ALL custom: prefixes when there are
        # any resources registered).
        try:
            resources = lovelace_core.list_resources(client)
            if resources:
                # We can't validate custom cards by name without per-resource
                # introspection, so don't flag any custom: prefix.
                pass
        except Exception:
            pass
    # Build the set of view paths on this dashboard so we can validate
    # tap_action navigation_paths.
    known_view_paths = {v.get("path") or v.get("title") for v in cfg.get("views", [])
                         if v.get("path") or v.get("title")}
    result = lovelace_cards_core.lint_with_navigation(
        cfg, all_eids,
        dashboard_url_path=url_path,
        known_view_paths=known_view_paths,
        known_card_types=known_types,
    )
    if check_types and known_types is not None:
        # Don't flag custom: prefix as unknown — too noisy.
        result["unknown_card_types"] = [
            x for x in result["unknown_card_types"]
            if not str(x.get("card_type", "")).startswith("custom:")
        ]
    if check_templates:
        tpl_result = lovelace_cards_core.validate_templates(client, cfg)
        result["template_check"] = {
            "total_templates": tpl_result["total_templates"],
            "failures": tpl_result["failures"],
        }
    emit(ctx, result)


@lovelace.command("prune")
@click.argument("url_path")
@click.option("--type", "types", multiple=True,
              help="Drop any card whose type matches (repeatable)")
@click.option("--entity-prefix", "entity_prefixes", multiple=True,
              help="Drop any card whose entity (or entities[].entity) starts "
                   "with this prefix (repeatable). E.g. 'climate.'")
@click.option("--markdown-contains", "markdown_contains", multiple=True,
              help="Drop any markdown card whose content contains this substring")
@click.option("--subheading", "subheadings", multiple=True,
              help="Drop a heading card with this text AND every following card "
                   "until the next heading (repeatable)")
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def lovelace_prune(ctx, url_path, types, entity_prefixes, markdown_contains,
                     subheadings, dry_run):
    """Recursively remove cards from a dashboard by type / entity / markdown.

    Walks every section/stack. Containers (horizontal-stack, vertical-stack,
    grid) that lose all their children are also removed. Pair with --dry-run
    to count what'd be removed before committing.

    Example: strip every climate card + the kitchen-appliances subheading
    block from gem-mobile in one shot:

      lovelace prune gem-mobile \\
        --entity-prefix climate. \\
        --type custom:better-thermostat-ui-card \\
        --subheading '🧹 Kitchen Appliances'
    """
    if not (types or entity_prefixes or markdown_contains or subheadings):
        click.echo("error: pass at least one filter "
                   "(--type / --entity-prefix / --markdown-contains / "
                   "--subheading)", err=True)
        sys.exit(1)
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    new_cfg, counters = lovelace_cards_core.prune(
        cfg,
        types=set(types) if types else None,
        entity_prefixes=set(entity_prefixes) if entity_prefixes else None,
        markdown_contains=set(markdown_contains) if markdown_contains else None,
        blocked_subheadings=set(subheadings) if subheadings else None,
    )
    if not dry_run:
        lovelace_core.save_dashboard_config(client, url_path, new_cfg)
    emit(ctx, {**counters, "url_path": url_path, "saved": not dry_run})


@lovelace.command("mirror")
@click.argument("source_url_path")
@click.argument("dest_url_path")
@click.option("--sub", "substitutions", multiple=True,
              help='old=new substitution applied to every string '
                   '(repeatable). E.g. --sub sensor.jon_phone=sensor.gem_phone')
@click.option("--keep-view", "keep_views", multiple=True,
              help="If passed, only these view paths/titles are mirrored")
@click.option("--skip-view", "skip_views", multiple=True, default=("scratch",),
              help="View paths/titles to drop (default: scratch)")
@click.option("--allowed-room", "allowed_rooms", multiple=True,
              help="In Rooms view: keep only sections whose visibility "
                   "references one of these room_selector option names")
@click.option("--subheading-block", "blocked_subheadings", multiple=True,
              help="Drop heading cards + their following groups")
@click.option("--card-type-block", "blocked_card_types", multiple=True,
              help="Drop cards matching these types (recursive)")
@click.option("--entity-prefix-block", "blocked_entity_prefixes", multiple=True,
              help="Drop cards whose entity starts with these prefixes")
@click.option("--markdown-block", "blocked_markdown_contains", multiple=True,
              help="Drop markdown cards whose content contains these substrings")
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def lovelace_mirror(ctx, source_url_path, dest_url_path, substitutions,
                      keep_views, skip_views, allowed_rooms, blocked_subheadings,
                      blocked_card_types, blocked_entity_prefixes,
                      blocked_markdown_contains, dry_run):
    """Mirror one dashboard to another with optional substitutions + filters.

    Subsumes the bespoke mirror_dashboard.py pattern as a first-class
    command. Example — produce a kid-safe mirror with filters:

      lovelace mirror jon-mobile noah-mobile \\
        --sub sensor.jon_phone=sensor.noah_phone \\
        --sub input_select.room_selector_jon=input_select.room_selector_noah \\
        --keep-view Rooms \\
        --allowed-room Bathroom --allowed-room Lounge \\
        --allowed-room "Living · Dining · Kitchen" \\
        --entity-prefix-block climate. \\
        --subheading-block '🧹 Kitchen Appliances'
    """
    subs = []
    for s in substitutions:
        if "=" not in s:
            click.echo(f"error: --sub expects old=new, got {s!r}", err=True)
            sys.exit(1)
        old, new = s.split("=", 1)
        subs.append((old, new))
    emit(ctx, lovelace_mirror_core.mirror(
        make_client(ctx),
        source_url_path=source_url_path,
        dest_url_path=dest_url_path,
        substitutions=subs,
        keep_views=set(keep_views) if keep_views else None,
        skip_views=set(skip_views) if skip_views else None,
        allowed_rooms=set(allowed_rooms) if allowed_rooms else None,
        blocked_subheadings=set(blocked_subheadings) if blocked_subheadings else None,
        blocked_card_types=set(blocked_card_types) if blocked_card_types else None,
        blocked_entity_prefixes=set(blocked_entity_prefixes) if blocked_entity_prefixes else None,
        blocked_markdown_contains=set(blocked_markdown_contains) if blocked_markdown_contains else None,
        dry_run=dry_run,
    ))


@lovelace.command("patch")
@click.argument("url_path")
@click.argument("pointer")
@click.option("--value", default=None,
              help="JSON value to set at the pointer (use '-' for stdin)")
@click.option("--value-file", type=click.Path(exists=True, dir_okay=False),
              help="Read JSON value from a file")
@click.option("--delete", is_flag=True, default=False,
              help="Delete the node at the pointer instead of replacing")
@click.option("--dry-run", is_flag=True, default=False,
              help="Print the resulting config but don't save it")
@click.pass_context
def lovelace_patch(ctx, url_path, pointer, value, value_file, delete, dry_run):
    """Surgical edit of a dashboard config via JSON pointer.

    Pointer syntax matches the lovelace-cards module:
        views[0]/sections[4]/cards[1]
        views[8]/cards[0]/cards[2]/grid_options/rows

    Examples:
      # Bump a stack's grid_options.rows
      lovelace patch jon-mobile views[8]/sections[0]/cards[1]/grid_options/rows --value 12

      # Replace a whole card from a JSON file
      lovelace patch jon-mobile views[0]/sections[4]/cards[1] --value-file new.json

      # Delete a card
      lovelace patch jon-mobile views[14]/sections[2] --delete
    """
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    if delete and (value or value_file):
        click.echo("error: --delete is mutually exclusive with --value/--value-file",
                   err=True)
        sys.exit(1)
    if not delete:
        if value_file:
            with open(value_file) as f:
                new_value = json.loads(f.read())
        elif value == "-":
            new_value = json.loads(sys.stdin.read())
        elif value is not None:
            try:
                new_value = json.loads(value)
            except json.JSONDecodeError:
                new_value = value  # treat as raw string
        else:
            click.echo("error: provide --value, --value-file, or --delete",
                       err=True)
            sys.exit(1)
    try:
        if delete:
            lovelace_cards_core.delete_at_pointer(cfg, pointer)
        else:
            lovelace_cards_core.set_at_pointer(cfg, pointer, new_value)
    except (KeyError, IndexError, ValueError) as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    if dry_run:
        emit(ctx, {"dry_run": True, "pointer": pointer,
                   "would_save_to": url_path})
        return
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"patched": pointer, "deleted": delete,
               "url_path": url_path})


# ──────────────────────────────────────────────────────────────────────── config-entry

@cli.group("config-entry")
def config_entry():
    """Config entry management (integration instances)."""


@config_entry.command("list")
@click.option("--domain", "-d", default=None, help="Filter to a single integration")
@click.pass_context
def config_entry_list(ctx, domain):
    """List config entries, optionally filtered by integration domain."""
    emit(ctx, config_entries_core.list_entries(make_client(ctx), domain=domain))


@config_entry.command("get")
@click.argument("entry_id")
@click.pass_context
def config_entry_get(ctx, entry_id):
    """Show a single config entry by ID."""
    entry = config_entries_core.get_entry(make_client(ctx), entry_id)
    if entry is None:
        click.echo(f"error: no config entry found with id {entry_id!r}", err=True)
        sys.exit(1)
    emit(ctx, entry)


@config_entry.command("delete")
@click.argument("entry_id")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation")
@click.pass_context
def config_entry_delete(ctx, entry_id, yes):
    """Delete a config entry. Destructive — requires --yes (or REPL prompt)."""
    if not yes:
        if not click.confirm(f"Delete config entry {entry_id}?", default=False):
            click.echo("aborted")
            return
    emit(ctx, {"deleted": entry_id, "result": config_entries_core.delete_entry(make_client(ctx), entry_id)})


@config_entry.command("reload")
@click.argument("entry_id")
@click.pass_context
def config_entry_reload(ctx, entry_id):
    """Reload a config entry without restarting HA."""
    emit(ctx, {"reloaded": entry_id, "result": config_entries_core.reload_entry(make_client(ctx), entry_id)})


@config_entry.command("options-init")
@click.argument("entry_id")
@click.pass_context
def config_entry_options_init(ctx, entry_id):
    """Start an options flow — returns form descriptor + flow_id.

    Use the flow_id with `config-entry options-configure` to submit input.
    For one-shot updates, use `config-entry options-set` instead.
    """
    emit(ctx, config_entries_core.options_flow_init(make_client(ctx), entry_id))


@config_entry.command("options-configure")
@click.argument("flow_id")
@click.option("--data", "-D", multiple=True,
              help="key=value (JSON values supported, repeatable)")
@click.option("--data-file", type=click.Path(exists=True, dir_okay=False),
              help="Read user_input as JSON from a file")
@click.pass_context
def config_entry_options_configure(ctx, flow_id, data, data_file):
    """Submit input to an active options flow."""
    user_input = parse_kv_pairs(data) if data else {}
    if data_file:
        user_input.update(json.loads(open(data_file).read()))
    emit(ctx, config_entries_core.options_flow_configure(
        make_client(ctx), flow_id, user_input))


@config_entry.command("options-set")
@click.argument("entry_id")
@click.option("--data", "-D", multiple=True,
              help="key=value (JSON values supported, repeatable)")
@click.option("--data-file", type=click.Path(exists=True, dir_okay=False),
              help="Read user_input as JSON from a file")
@click.pass_context
def config_entry_options_set(ctx, entry_id, data, data_file):
    """Init + configure an options flow in one call.

    Useful for editing UI-created template helpers without restarting HA.
    For multi-line / Jinja-heavy values, --data-file is more reliable.
    """
    user_input = parse_kv_pairs(data) if data else {}
    if data_file:
        user_input.update(json.loads(open(data_file).read()))
    if not user_input:
        click.echo("error: provide --data or --data-file", err=True)
        sys.exit(1)
    emit(ctx, config_entries_core.options_flow_set(
        make_client(ctx), entry_id, user_input))


@config_entry.command("update")
@click.argument("entry_id")
@click.option("--title", default=None, help="New title for the entry")
@click.option("--data", "-D", multiple=True,
              help="entry.data key=value (JSON values supported, repeatable)")
@click.pass_context
def config_entry_update(ctx, entry_id, title, data):
    """Update an entry's title and/or its raw entry.data dict.

    Note: this writes directly to the entry, bypassing any options flow.
    Use `options-set` if the integration has an options flow with validation.
    """
    options = parse_kv_pairs(data) if data else None
    if title is None and options is None:
        click.echo("error: provide --title and/or --data", err=True)
        sys.exit(1)
    emit(ctx, config_entries_core.update_entry(
        make_client(ctx), entry_id, title=title, options=options))


# ──────────────────────────────────────────────────────────────────────── automation/script config edit

@automation.command("get")
@click.argument("entity_id")
@click.option("--out", "-o", default=None, type=click.Path(),
              help="Write JSON to this file (default: stdout)")
@click.pass_context
def automation_get(ctx, entity_id, out):
    """Fetch the raw config of a UI-managed automation as JSON."""
    cfg = automation_core.get_config(make_client(ctx), entity_id)
    text = json.dumps(cfg, indent=2, default=str, sort_keys=True)
    if out:
        Path(out).write_text(text)
        emit(ctx, {"saved": out, "size_bytes": len(text)})
    else:
        click.echo(text)


@automation.command("save")
@click.argument("entity_id")
@click.argument("config_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, default=False,
              help="Show a unified diff vs the live config; do not write.")
@click.option("--yes", "-y", is_flag=True, default=False,
              help="Skip the interactive confirmation (required for scripted use).")
@click.pass_context
def automation_save(ctx, entity_id, config_file, dry_run, yes):
    """Replace a UI-managed automation's config from a JSON file.

    Without --dry-run / --yes the command prompts before overwriting. With
    --dry-run it prints a unified diff between the live config and the
    proposed body and exits without writing.
    """
    cfg = json.loads(Path(config_file).read_text())
    client = make_client(ctx)
    if dry_run:
        try:
            current = automation_core.get_config(client, entity_id)
        except Exception:
            current = None
        diff = _config_diff(current, cfg, label_a=f"live:{entity_id}",
                             label_b=f"new:{config_file}")
        emit(ctx, {"dry_run": True, "entity_id": entity_id, "diff": diff})
        return
    if not yes and not click.confirm(
        f"Overwrite automation {entity_id!r} with contents of {config_file}?",
        default=False,
    ):
        raise click.ClickException("aborted")
    emit(ctx, {"saved": entity_id, "result": automation_core.save_config(make_client(ctx), entity_id, cfg)})


@script.command("get")
@click.argument("entity_id")
@click.option("--out", "-o", default=None, type=click.Path(),
              help="Write JSON to this file (default: stdout)")
@click.pass_context
def script_get(ctx, entity_id, out):
    """Fetch the raw config of a UI-managed script as JSON."""
    cfg = script_core.get_config(make_client(ctx), entity_id)
    text = json.dumps(cfg, indent=2, default=str, sort_keys=True)
    if out:
        Path(out).write_text(text)
        emit(ctx, {"saved": out, "size_bytes": len(text)})
    else:
        click.echo(text)


@script.command("save")
@click.argument("entity_id")
@click.argument("config_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, default=False,
              help="Show a unified diff vs the live config; do not write.")
@click.option("--yes", "-y", is_flag=True, default=False,
              help="Skip the interactive confirmation (required for scripted use).")
@click.pass_context
def script_save(ctx, entity_id, config_file, dry_run, yes):
    """Replace a UI-managed script's config from a JSON file.

    Without --dry-run / --yes the command prompts before overwriting. With
    --dry-run it prints a unified diff between the live config and the
    proposed body and exits without writing.
    """
    cfg = json.loads(Path(config_file).read_text())
    client = make_client(ctx)
    if dry_run:
        try:
            current = script_core.get_config(client, entity_id)
        except Exception:
            current = None
        diff = _config_diff(current, cfg, label_a=f"live:{entity_id}",
                             label_b=f"new:{config_file}")
        emit(ctx, {"dry_run": True, "entity_id": entity_id, "diff": diff})
        return
    if not yes and not click.confirm(
        f"Overwrite script {entity_id!r} with contents of {config_file}?",
        default=False,
    ):
        raise click.ClickException("aborted")
    emit(ctx, {"saved": entity_id, "result": script_core.save_config(make_client(ctx), entity_id, cfg)})


# ──────────────────────────────────────────────────────────────────────── mqtt subscribe / publish

@cli.group()
def mqtt():
    """MQTT publish + subscribe diagnostics."""


@mqtt.command("publish")
@click.argument("topic")
@click.argument("payload", required=False)
@click.option("--qos", default=0, type=int, help="QoS (0/1/2)")
@click.option("--retain/--no-retain", default=False, help="Set retain flag")
@click.option("--from-file", type=click.Path(exists=True, dir_okay=False),
              help="Read payload from a file (overrides positional payload)")
@click.pass_context
def mqtt_publish(ctx, topic, payload, qos, retain, from_file):
    """Publish a message to an MQTT topic.

    Wraps `service call mqtt publish` with a friendlier interface. Empty
    payloads are allowed (sends a zero-byte message — useful for clearing
    retained values).
    """
    if from_file:
        with open(from_file) as f:
            payload = f.read()
    if payload is None:
        payload = ""
    services_core.call_service(
        make_client(ctx), "mqtt", "publish",
        service_data={"topic": topic, "payload": payload,
                      "qos": qos, "retain": retain},
    )
    emit(ctx, {"published": True, "topic": topic, "qos": qos, "retain": retain,
               "bytes": len(payload)})


@mqtt.command("subscribe")
@click.argument("topic")
@click.option("--limit", default=0, type=int,
              help="Stop after this many messages (0 = unlimited; require --timeout or Ctrl+C)")
@click.option("--timeout", default=None, type=int, help="Stop after N seconds")
@click.option("--qos", default=0, type=int, help="MQTT subscription QoS (0/1/2)")
@click.option("--out", "-o", type=click.Path(dir_okay=False),
              help="Append each message as JSON to this file (line-delimited)")
@click.pass_context
def mqtt_subscribe(ctx, topic, limit, timeout, qos, out):
    """Subscribe to an MQTT topic via WebSocket and print messages.

    Default --limit is 0 (unlimited) — pair with --timeout for time-boxed
    diagnostic captures. Use --out to stream messages to a file as they
    arrive without buffering everything in memory.
    """
    client = make_client(ctx)
    stop = threading.Event()
    out_fh = open(out, "a") if out else None
    # Only retain messages in memory when we will need them for the final emit
    # — i.e. JSON mode with no --out file. Otherwise streaming-only: messages
    # go directly to stdout and/or the file and a counter tracks --limit, so
    # the process is memory-flat regardless of message volume.
    buffer_messages = ctx.obj.get("as_json") and out_fh is None
    seen: list[dict] = []
    count = [0]

    def on_msg(evt):
        count[0] += 1
        if buffer_messages:
            seen.append(evt)
        line = json.dumps(evt, default=str)
        if not ctx.obj.get("as_json"):
            click.echo(line)
        if out_fh is not None:
            out_fh.write(line + "\n")
            out_fh.flush()
        if limit and count[0] >= limit:
            stop.set()

    if timeout:
        threading.Timer(timeout, stop.set).start()

    try:
        client.ws_subscribe("mqtt/subscribe", {"topic": topic, "qos": qos},
                             on_msg, stop)
    except KeyboardInterrupt:
        stop.set()
    finally:
        if out_fh is not None:
            out_fh.close()

    if ctx.obj.get("as_json"):
        emit(ctx, seen if buffer_messages else
             {"received": count[0], "out": out, "streamed_only": True})
    else:
        click.echo(f"received {count[0]} message(s)")


# ──────────────────────────────────────────────────────────────────────── helpers

@cli.group("helpers")
def helpers():
    """input_select / input_number / etc. helper management."""


@helpers.group("input-select")
def helpers_input_select():
    """input_select-specific helper operations."""


@helpers_input_select.command("set-options")
@click.argument("entity_id")
@click.argument("options", nargs=-1, required=True)
@click.option("--from-file", type=click.Path(exists=True, dir_okay=False),
              help="Read options as JSON list from a file (alternative to args)")
@click.pass_context
def helpers_input_select_set_options(ctx, entity_id, options, from_file):
    """Replace the options list on an input_select.

    Either pass options as positional args:
        helpers input-select set-options input_select.foo Auto Bedroom Lounge
    or pass --from-file pointing at a JSON list.
    """
    if from_file:
        opts = json.loads(open(from_file).read())
        if not isinstance(opts, list):
            click.echo("error: --from-file must contain a JSON list", err=True)
            sys.exit(1)
    else:
        opts = list(options)
    emit(ctx, helpers_core.input_select_set_options(make_client(ctx), entity_id, opts))


@helpers_input_select.command("sync")
@click.argument("src_entity_id")
@click.argument("dst_entity_id")
@click.option("--fallback", default="Auto",
              help="Option to fall back to if dst's current state would become invalid")
@click.pass_context
def helpers_input_select_sync(ctx, src_entity_id, dst_entity_id, fallback):
    """Copy the options list from src to dst input_select.

    State (current selection) stays per-helper. If the destination's
    current state isn't in the new options list, --fallback is selected
    first to avoid stranding the helper in an unknown value.
    """
    emit(ctx, helpers_core.input_select_sync(
        make_client(ctx), src_entity_id, dst_entity_id, fallback=fallback))


@helpers_input_select.command("create")
@click.option("--name", required=True, help="Display name (also entity slug)")
@click.argument("options", nargs=-1, required=True)
@click.option("--icon", default=None, help="mdi:xxx icon")
@click.option("--initial", default=None, help="Initial selected option")
@click.pass_context
def helpers_input_select_create(ctx, name, options, icon, initial):
    """Create a NEW input_select helper at runtime.

    Registered immediately to .storage/input_select; survives restart.

    Example:
      helpers input-select create --name "Room Selector - Kid" \\
        Auto Bedroom Lounge Bathroom
    """
    emit(ctx, helpers_core.input_select_create(
        make_client(ctx), name=name, options=list(options),
        icon=icon, initial=initial,
    ))


# ──────────────────────────────────────────────────────────────────────── helpers — input_boolean

@helpers.group("input-boolean")
def helpers_input_boolean():
    """input_boolean (toggle) helper operations."""


@helpers_input_boolean.command("list")
@click.pass_context
def helpers_input_boolean_list(ctx):
    """List every input_boolean helper (UI-managed)."""
    for h in helpers_core.input_boolean_list(make_client(ctx)) or []:
        emit(ctx, h)


@helpers_input_boolean.command("create")
@click.option("--name", required=True, help="Display name (also drives the entity slug)")
@click.option("--icon", default=None, help="mdi:xxx icon")
@click.option("--initial/--no-initial", "initial", default=None,
              help="Initial on/off state (omit to leave HA default)")
@click.pass_context
def helpers_input_boolean_create(ctx, name, icon, initial):
    """Create a NEW input_boolean. Persists across restart."""
    emit(ctx, helpers_core.input_boolean_create(
        make_client(ctx), name=name, icon=icon, initial=initial))


@helpers_input_boolean.command("update")
@click.argument("entity_id")
@click.option("--name", default=None)
@click.option("--icon", default=None)
@click.option("--initial/--no-initial", "initial", default=None)
@click.pass_context
def helpers_input_boolean_update(ctx, entity_id, name, icon, initial):
    """Update an existing input_boolean (storage-mode only)."""
    emit(ctx, helpers_core.input_boolean_update(
        make_client(ctx), entity_id, name=name, icon=icon, initial=initial))


@helpers_input_boolean.command("delete")
@click.argument("entity_id")
@click.pass_context
def helpers_input_boolean_delete(ctx, entity_id):
    """Remove an input_boolean registration."""
    emit(ctx, {"deleted": entity_id,
               "result": helpers_core.input_boolean_delete(make_client(ctx), entity_id)})


@helpers_input_boolean.command("turn-on")
@click.argument("entity_id")
@click.pass_context
def helpers_input_boolean_turn_on(ctx, entity_id):
    emit(ctx, helpers_core.input_boolean_turn_on(make_client(ctx), entity_id))


@helpers_input_boolean.command("turn-off")
@click.argument("entity_id")
@click.pass_context
def helpers_input_boolean_turn_off(ctx, entity_id):
    emit(ctx, helpers_core.input_boolean_turn_off(make_client(ctx), entity_id))


@helpers_input_boolean.command("toggle")
@click.argument("entity_id")
@click.pass_context
def helpers_input_boolean_toggle(ctx, entity_id):
    emit(ctx, helpers_core.input_boolean_toggle(make_client(ctx), entity_id))


# ──────────────────────────────────────────────────────────────────────── helpers — input_button

@helpers.group("input-button")
def helpers_input_button():
    """input_button (momentary press) helper operations."""


@helpers_input_button.command("list")
@click.pass_context
def helpers_input_button_list(ctx):
    for h in helpers_core.input_button_list(make_client(ctx)) or []:
        emit(ctx, h)


@helpers_input_button.command("create")
@click.option("--name", required=True)
@click.option("--icon", default=None)
@click.pass_context
def helpers_input_button_create(ctx, name, icon):
    emit(ctx, helpers_core.input_button_create(make_client(ctx), name=name, icon=icon))


@helpers_input_button.command("update")
@click.argument("entity_id")
@click.option("--name", default=None)
@click.option("--icon", default=None)
@click.pass_context
def helpers_input_button_update(ctx, entity_id, name, icon):
    emit(ctx, helpers_core.input_button_update(
        make_client(ctx), entity_id, name=name, icon=icon))


@helpers_input_button.command("delete")
@click.argument("entity_id")
@click.pass_context
def helpers_input_button_delete(ctx, entity_id):
    emit(ctx, {"deleted": entity_id,
               "result": helpers_core.input_button_delete(make_client(ctx), entity_id)})


@helpers_input_button.command("press")
@click.argument("entity_id")
@click.pass_context
def helpers_input_button_press(ctx, entity_id):
    """Fire a press event on the input_button."""
    emit(ctx, helpers_core.input_button_press(make_client(ctx), entity_id))


# ──────────────────────────────────────────────────────────────────────── helpers — input_number

@helpers.group("input-number")
def helpers_input_number():
    """input_number (slider/box) helper operations."""


@helpers_input_number.command("list")
@click.pass_context
def helpers_input_number_list(ctx):
    for h in helpers_core.input_number_list(make_client(ctx)) or []:
        emit(ctx, h)


@helpers_input_number.command("create")
@click.option("--name", required=True)
@click.option("--min", "min_", type=float, required=True)
@click.option("--max", "max_", type=float, required=True)
@click.option("--step", type=float, default=1.0)
@click.option("--mode", type=click.Choice(["slider", "box"]), default="slider")
@click.option("--unit", "unit_of_measurement", default=None)
@click.option("--icon", default=None)
@click.option("--initial", type=float, default=None)
@click.pass_context
def helpers_input_number_create(ctx, name, min_, max_, step, mode,
                                 unit_of_measurement, icon, initial):
    emit(ctx, helpers_core.input_number_create(
        make_client(ctx), name=name, min=min_, max=max_, step=step, mode=mode,
        unit_of_measurement=unit_of_measurement, icon=icon, initial=initial))


@helpers_input_number.command("update")
@click.argument("entity_id")
@click.option("--name", default=None)
@click.option("--min", "min_", type=float, default=None)
@click.option("--max", "max_", type=float, default=None)
@click.option("--step", type=float, default=None)
@click.option("--mode", type=click.Choice(["slider", "box"]), default=None)
@click.option("--unit", "unit_of_measurement", default=None)
@click.option("--icon", default=None)
@click.option("--initial", type=float, default=None)
@click.pass_context
def helpers_input_number_update(ctx, entity_id, name, min_, max_, step, mode,
                                 unit_of_measurement, icon, initial):
    emit(ctx, helpers_core.input_number_update(
        make_client(ctx), entity_id, name=name, min=min_, max=max_, step=step,
        mode=mode, unit_of_measurement=unit_of_measurement, icon=icon, initial=initial))


@helpers_input_number.command("delete")
@click.argument("entity_id")
@click.pass_context
def helpers_input_number_delete(ctx, entity_id):
    emit(ctx, {"deleted": entity_id,
               "result": helpers_core.input_number_delete(make_client(ctx), entity_id)})


@helpers_input_number.command("set-value")
@click.argument("entity_id")
@click.argument("value", type=float)
@click.pass_context
def helpers_input_number_set_value(ctx, entity_id, value):
    emit(ctx, helpers_core.input_number_set_value(make_client(ctx), entity_id, value))


@helpers_input_number.command("increment")
@click.argument("entity_id")
@click.pass_context
def helpers_input_number_increment(ctx, entity_id):
    emit(ctx, helpers_core.input_number_increment(make_client(ctx), entity_id))


@helpers_input_number.command("decrement")
@click.argument("entity_id")
@click.pass_context
def helpers_input_number_decrement(ctx, entity_id):
    emit(ctx, helpers_core.input_number_decrement(make_client(ctx), entity_id))


# ──────────────────────────────────────────────────────────────────────── helpers — input_text

@helpers.group("input-text")
def helpers_input_text():
    """input_text (free string) helper operations."""


@helpers_input_text.command("list")
@click.pass_context
def helpers_input_text_list(ctx):
    for h in helpers_core.input_text_list(make_client(ctx)) or []:
        emit(ctx, h)


@helpers_input_text.command("create")
@click.option("--name", required=True)
@click.option("--min", "min_", type=int, default=0)
@click.option("--max", "max_", type=int, default=100)
@click.option("--pattern", default=None, help="Regex the value must match")
@click.option("--mode", type=click.Choice(["text", "password"]), default="text")
@click.option("--icon", default=None)
@click.option("--initial", default=None)
@click.pass_context
def helpers_input_text_create(ctx, name, min_, max_, pattern, mode, icon, initial):
    emit(ctx, helpers_core.input_text_create(
        make_client(ctx), name=name, min=min_, max=max_, pattern=pattern,
        mode=mode, icon=icon, initial=initial))


@helpers_input_text.command("update")
@click.argument("entity_id")
@click.option("--name", default=None)
@click.option("--min", "min_", type=int, default=None)
@click.option("--max", "max_", type=int, default=None)
@click.option("--pattern", default=None)
@click.option("--mode", type=click.Choice(["text", "password"]), default=None)
@click.option("--icon", default=None)
@click.option("--initial", default=None)
@click.pass_context
def helpers_input_text_update(ctx, entity_id, name, min_, max_, pattern,
                               mode, icon, initial):
    emit(ctx, helpers_core.input_text_update(
        make_client(ctx), entity_id, name=name, min=min_, max=max_,
        pattern=pattern, mode=mode, icon=icon, initial=initial))


@helpers_input_text.command("delete")
@click.argument("entity_id")
@click.pass_context
def helpers_input_text_delete(ctx, entity_id):
    emit(ctx, {"deleted": entity_id,
               "result": helpers_core.input_text_delete(make_client(ctx), entity_id)})


@helpers_input_text.command("set-value")
@click.argument("entity_id")
@click.argument("value")
@click.pass_context
def helpers_input_text_set_value(ctx, entity_id, value):
    emit(ctx, helpers_core.input_text_set_value(make_client(ctx), entity_id, value))


# ──────────────────────────────────────────────────────────────────────── helpers — input_datetime

@helpers.group("input-datetime")
def helpers_input_datetime():
    """input_datetime (date/time/datetime) helper operations."""


@helpers_input_datetime.command("list")
@click.pass_context
def helpers_input_datetime_list(ctx):
    for h in helpers_core.input_datetime_list(make_client(ctx)) or []:
        emit(ctx, h)


@helpers_input_datetime.command("create")
@click.option("--name", required=True)
@click.option("--has-date/--no-has-date", "has_date", default=True)
@click.option("--has-time/--no-has-time", "has_time", default=True)
@click.option("--icon", default=None)
@click.option("--initial", default=None,
              help="Initial value: YYYY-MM-DD, HH:MM:SS, or YYYY-MM-DD HH:MM:SS")
@click.pass_context
def helpers_input_datetime_create(ctx, name, has_date, has_time, icon, initial):
    emit(ctx, helpers_core.input_datetime_create(
        make_client(ctx), name=name, has_date=has_date, has_time=has_time,
        icon=icon, initial=initial))


@helpers_input_datetime.command("update")
@click.argument("entity_id")
@click.option("--name", default=None)
@click.option("--has-date/--no-has-date", "has_date", default=None)
@click.option("--has-time/--no-has-time", "has_time", default=None)
@click.option("--icon", default=None)
@click.option("--initial", default=None)
@click.pass_context
def helpers_input_datetime_update(ctx, entity_id, name, has_date, has_time,
                                   icon, initial):
    emit(ctx, helpers_core.input_datetime_update(
        make_client(ctx), entity_id, name=name, has_date=has_date,
        has_time=has_time, icon=icon, initial=initial))


@helpers_input_datetime.command("delete")
@click.argument("entity_id")
@click.pass_context
def helpers_input_datetime_delete(ctx, entity_id):
    emit(ctx, {"deleted": entity_id,
               "result": helpers_core.input_datetime_delete(make_client(ctx), entity_id)})


@helpers_input_datetime.command("set")
@click.argument("entity_id")
@click.option("--date", default=None, help="YYYY-MM-DD")
@click.option("--time", default=None, help="HH:MM:SS")
@click.option("--datetime", "datetime_", default=None, help="YYYY-MM-DD HH:MM:SS")
@click.pass_context
def helpers_input_datetime_set(ctx, entity_id, date, time, datetime_):
    emit(ctx, helpers_core.input_datetime_set(
        make_client(ctx), entity_id, date=date, time=time, datetime=datetime_))


# ──────────────────────────────────────────────────────────────────────── helpers — counter / timer / schedule

@helpers.group("counter")
def helpers_counter():
    """counter (integer that increments) helper operations."""


@helpers_counter.command("list")
@click.pass_context
def helpers_counter_list(ctx):
    for h in helpers_core.counter_list(make_client(ctx)) or []:
        emit(ctx, h)


@helpers_counter.command("create")
@click.option("--name", required=True)
@click.option("--initial", type=int, default=0)
@click.option("--step", type=int, default=1)
@click.option("--min", "minimum", type=int, default=None)
@click.option("--max", "maximum", type=int, default=None)
@click.option("--restore/--no-restore", default=True,
              help="Keep value across HA restart")
@click.option("--icon", default=None)
@click.pass_context
def helpers_counter_create(ctx, name, initial, step, minimum, maximum, restore, icon):
    emit(ctx, helpers_core.counter_create(
        make_client(ctx), name=name, initial=initial, step=step,
        minimum=minimum, maximum=maximum, restore=restore, icon=icon))


@helpers_counter.command("update")
@click.argument("entity_id")
@click.option("--name", default=None)
@click.option("--initial", type=int, default=None)
@click.option("--step", type=int, default=None)
@click.option("--min", "minimum", type=int, default=None)
@click.option("--max", "maximum", type=int, default=None)
@click.option("--restore/--no-restore", default=None)
@click.option("--icon", default=None)
@click.pass_context
def helpers_counter_update(ctx, entity_id, name, initial, step, minimum,
                            maximum, restore, icon):
    emit(ctx, helpers_core.counter_update(
        make_client(ctx), entity_id, name=name, initial=initial, step=step,
        minimum=minimum, maximum=maximum, restore=restore, icon=icon))


@helpers_counter.command("delete")
@click.argument("entity_id")
@click.pass_context
def helpers_counter_delete(ctx, entity_id):
    emit(ctx, {"deleted": entity_id,
               "result": helpers_core.counter_delete(make_client(ctx), entity_id)})


@helpers_counter.command("increment")
@click.argument("entity_id")
@click.pass_context
def helpers_counter_increment(ctx, entity_id):
    emit(ctx, helpers_core.counter_increment(make_client(ctx), entity_id))


@helpers_counter.command("decrement")
@click.argument("entity_id")
@click.pass_context
def helpers_counter_decrement(ctx, entity_id):
    emit(ctx, helpers_core.counter_decrement(make_client(ctx), entity_id))


@helpers_counter.command("reset")
@click.argument("entity_id")
@click.pass_context
def helpers_counter_reset(ctx, entity_id):
    emit(ctx, helpers_core.counter_reset(make_client(ctx), entity_id))


@helpers_counter.command("set-value")
@click.argument("entity_id")
@click.argument("value", type=int)
@click.pass_context
def helpers_counter_set_value(ctx, entity_id, value):
    emit(ctx, helpers_core.counter_set_value(make_client(ctx), entity_id, value))


@helpers.group("timer")
def helpers_timer():
    """timer (countdown) helper operations."""


@helpers_timer.command("list")
@click.pass_context
def helpers_timer_list(ctx):
    for h in helpers_core.timer_list(make_client(ctx)) or []:
        emit(ctx, h)


@helpers_timer.command("create")
@click.option("--name", required=True)
@click.option("--duration", default="00:00:00", help="HH:MM:SS")
@click.option("--restore/--no-restore", default=False)
@click.option("--icon", default=None)
@click.pass_context
def helpers_timer_create(ctx, name, duration, restore, icon):
    emit(ctx, helpers_core.timer_create(
        make_client(ctx), name=name, duration=duration,
        restore=restore, icon=icon))


@helpers_timer.command("update")
@click.argument("entity_id")
@click.option("--name", default=None)
@click.option("--duration", default=None)
@click.option("--restore/--no-restore", default=None)
@click.option("--icon", default=None)
@click.pass_context
def helpers_timer_update(ctx, entity_id, name, duration, restore, icon):
    emit(ctx, helpers_core.timer_update(
        make_client(ctx), entity_id, name=name, duration=duration,
        restore=restore, icon=icon))


@helpers_timer.command("delete")
@click.argument("entity_id")
@click.pass_context
def helpers_timer_delete(ctx, entity_id):
    emit(ctx, {"deleted": entity_id,
               "result": helpers_core.timer_delete(make_client(ctx), entity_id)})


@helpers_timer.command("start")
@click.argument("entity_id")
@click.option("--duration", default=None, help="Override default duration (HH:MM:SS)")
@click.pass_context
def helpers_timer_start(ctx, entity_id, duration):
    emit(ctx, helpers_core.timer_start(make_client(ctx), entity_id, duration=duration))


@helpers_timer.command("pause")
@click.argument("entity_id")
@click.pass_context
def helpers_timer_pause(ctx, entity_id):
    emit(ctx, helpers_core.timer_pause(make_client(ctx), entity_id))


@helpers_timer.command("cancel")
@click.argument("entity_id")
@click.pass_context
def helpers_timer_cancel(ctx, entity_id):
    emit(ctx, helpers_core.timer_cancel(make_client(ctx), entity_id))


@helpers_timer.command("finish")
@click.argument("entity_id")
@click.pass_context
def helpers_timer_finish(ctx, entity_id):
    emit(ctx, helpers_core.timer_finish(make_client(ctx), entity_id))


@helpers_timer.command("change")
@click.argument("entity_id")
@click.argument("duration")
@click.pass_context
def helpers_timer_change(ctx, entity_id, duration):
    """Add (positive) or subtract (negative) HH:MM:SS from a running timer."""
    emit(ctx, helpers_core.timer_change(make_client(ctx), entity_id, duration))


@helpers.group("schedule")
def helpers_schedule():
    """schedule (weekly on/off windows) helper operations."""


@helpers_schedule.command("list")
@click.pass_context
def helpers_schedule_list(ctx):
    for h in helpers_core.schedule_list(make_client(ctx)) or []:
        emit(ctx, h)


@helpers_schedule.command("delete")
@click.argument("entity_id")
@click.pass_context
def helpers_schedule_delete(ctx, entity_id):
    emit(ctx, {"deleted": entity_id,
               "result": helpers_core.schedule_delete(make_client(ctx), entity_id)})


# Schedule create/update take per-day window lists which are awkward as CLI
# flags. Expose a --from-file path that takes the whole config as JSON, so
# callers can build the structure in whatever language they prefer.

@helpers_schedule.command("create")
@click.option("--name", required=True)
@click.option("--from-file", type=click.Path(exists=True, dir_okay=False), required=True,
              help='JSON file with optional keys: monday..sunday (each a list of '
                   '{from,to} windows), and optional "icon".')
@click.pass_context
def helpers_schedule_create(ctx, name, from_file):
    cfg = json.loads(open(from_file).read())
    if not isinstance(cfg, dict):
        click.echo("error: --from-file must contain a JSON object", err=True)
        sys.exit(1)
    emit(ctx, helpers_core.schedule_create(make_client(ctx), name=name, **cfg))


@helpers_schedule.command("update")
@click.argument("entity_id")
@click.option("--from-file", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--name", default=None)
@click.pass_context
def helpers_schedule_update(ctx, entity_id, from_file, name):
    cfg = json.loads(open(from_file).read())
    if not isinstance(cfg, dict):
        click.echo("error: --from-file must contain a JSON object", err=True)
        sys.exit(1)
    emit(ctx, helpers_core.schedule_update(
        make_client(ctx), entity_id, name=name, **cfg))


@helpers.command("list-all")
@click.option("--no-config-flow", is_flag=True,
              help="Skip the config-flow helpers (derivative, template, group, ...)")
@click.pass_context
def helpers_list_all(ctx, no_config_flow):
    """Enumerate every helper across every type, grouped by type."""
    emit(ctx, helpers_core.list_all_helpers(
        make_client(ctx), include_config_flow=not no_config_flow))


# ──────────────────────────────────────────────────────────────────────── lovelace backup / diff

@cli.group("lovelace-tools")
def lovelace_tools():
    """Lovelace dashboard backup / diff utilities."""


@lovelace_tools.command("backup")
@click.option("--out-dir", "-d", required=True, type=click.Path(),
              help="Directory to write per-dashboard JSON snapshots into")
@click.option("--url-path", "-u", multiple=True,
              help="One or more dashboard url_paths (default: all)")
@click.pass_context
def lovelace_tools_backup(ctx, out_dir, url_path):
    """Snapshot every (or selected) dashboard config as JSON files."""
    import os
    os.makedirs(out_dir, exist_ok=True)
    client = make_client(ctx)
    if url_path:
        targets = list(url_path)
    else:
        # Pull all dashboards; the default 'lovelace' (Overview) is implicit
        dashboards = client.ws_call("lovelace/dashboards/list", None) or []
        targets = [d.get("url_path") for d in dashboards if d.get("url_path")]
        if "lovelace" not in targets:
            targets.append("lovelace")
    written = []
    for path in targets:
        try:
            cfg = client.ws_call("lovelace/config", {"url_path": path})
        except Exception as exc:  # noqa: BLE001
            click.echo(f"  skip {path}: {exc}", err=True)
            continue
        out = os.path.join(out_dir, f"lovelace.{path}.json")
        with open(out, "w") as f:
            json.dump(cfg, f, indent=2)
        written.append({"url_path": path, "file": out,
                        "views": len(cfg.get("views", []))})
    emit(ctx, written)


@lovelace_tools.command("diff")
@click.argument("file_a", type=click.Path(exists=True, dir_okay=False))
@click.argument("file_b", type=click.Path(exists=True, dir_okay=False))
@click.option("--summary/--full", default=True,
              help="Summary by default; --full for the unified JSON diff")
@click.pass_context
def lovelace_tools_diff(ctx, file_a, file_b, summary):
    """Diff two dashboard JSON files (e.g. backup vs current)."""
    a = json.load(open(file_a))
    b = json.load(open(file_b))
    if summary:
        result = {
            "views_a": len(a.get("views", [])),
            "views_b": len(b.get("views", [])),
            "views_added": [], "views_removed": [], "views_changed": [],
        }
        a_paths = {v.get("path") or v.get("title"): v for v in a.get("views", [])}
        b_paths = {v.get("path") or v.get("title"): v for v in b.get("views", [])}
        for k in b_paths:
            if k not in a_paths:
                result["views_added"].append(k)
            elif json.dumps(a_paths[k], sort_keys=True) != json.dumps(b_paths[k], sort_keys=True):
                result["views_changed"].append(k)
        for k in a_paths:
            if k not in b_paths:
                result["views_removed"].append(k)
        emit(ctx, result)
    else:
        # produce a per-line unified diff of the JSON canonicalised form
        import difflib
        a_text = json.dumps(a, indent=2, sort_keys=True).splitlines(keepends=True)
        b_text = json.dumps(b, indent=2, sort_keys=True).splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(a_text, b_text,
                                            fromfile=file_a, tofile=file_b,
                                            n=3))
        if ctx.obj.get("as_json"):
            emit(ctx, {"diff": diff})
        else:
            click.echo(diff or "(no differences)")


# ──────────────────────────────────────────────────────── operational basics

# 1. BACKUP
@cli.group()
def backup():
    """Backup snapshots — list / create / show / delete / restore."""


@backup.command("info")
@click.pass_context
def backup_info(ctx):
    """Overall backup state — running job, last completed, configured agents."""
    data = backup_core.info(make_client(ctx))
    # Trim the noisy `backups` array out of the summary view; users can `backup list` instead.
    summary = {k: v for k, v in data.items() if k != "backups"}
    summary["backup_count"] = len(data.get("backups") or [])
    emit(ctx, summary)


@backup.command("list")
@click.pass_context
def backup_list(ctx):
    """Flat table of backups: id, name, date, size, agents."""
    rows = []
    for b in backup_core.list_backups(make_client(ctx)):
        # `size_bytes`, `agent_ids`, `protected` are now promoted from the
        # per-agent dict by core/backup.py::_enrich. Fall back to the
        # legacy top-level `size` if some future HA version puts it back.
        size_bytes = b.get("size_bytes") or b.get("size")
        rows.append({
            "backup_id": b.get("backup_id") or b.get("slug"),
            "name": b.get("name"),
            "date": b.get("date") or b.get("created_at"),
            "size_mb": (round(size_bytes / (1024 * 1024), 2)
                        if size_bytes else None),
            "protected": b.get("protected"),
            "type": b.get("type"),
            "agents": b.get("agent_ids")
                       or list((b.get("agents") or {}).keys()) or None,
        })
    emit(ctx, rows)


@backup.command("show")
@click.argument("backup_id")
@click.pass_context
def backup_show(ctx, backup_id):
    emit(ctx, backup_core.details(make_client(ctx), backup_id))


@backup.command("create")
@click.option("--name", default=None, help="Backup name (default: auto-generated)")
@click.option("--password", default=None,
              help="Encrypt with this password (writes/reads must match)")
@click.option("--no-database", is_flag=True, default=False,
              help="Skip the recorder database (smaller, faster)")
@click.option("--agent", "agent_ids", multiple=True,
              help="Limit to specific backup agents (repeatable, HA 2024.7+)")
@click.pass_context
def backup_create(ctx, name, password, no_database, agent_ids):
    """Trigger a backup. Returns the job descriptor — the backup itself runs async."""
    emit(ctx, backup_core.generate(
        make_client(ctx),
        name=name, password=password,
        database_included=not no_database,
        agent_ids=list(agent_ids) or None,
    ))


@backup.command("delete")
@click.argument("backup_id")
@click.option("--agent", "agent_ids", multiple=True,
              help="Delete only from these agents (default: all)")
@click.confirmation_option(prompt="Delete this backup?")
@click.pass_context
def backup_delete(ctx, backup_id, agent_ids):
    emit(ctx, backup_core.remove(
        make_client(ctx), backup_id,
        agent_ids=list(agent_ids) or None,
    ))


@backup.command("restore")
@click.argument("backup_id")
@click.option("--password", default=None,
              help="Password for an encrypted backup")
@click.option("--no-database", is_flag=True, default=False)
@click.option("--folder", "restore_folders", multiple=True,
              help="Folders to restore (repeatable; HA 2024.7+)")
@click.option("--addon", "restore_addons", multiple=True,
              help="Add-ons to restore (repeatable)")
@click.option("--agent", "agent_id", default=None,
              help="Restore from this specific agent")
@click.confirmation_option(prompt="Restore this backup? HA will restart.")
@click.pass_context
def backup_restore(ctx, backup_id, password, no_database,
                    restore_folders, restore_addons, agent_id):
    emit(ctx, backup_core.restore(
        make_client(ctx), backup_id,
        password=password, restore_database=not no_database,
        restore_folders=list(restore_folders) or None,
        restore_addons=list(restore_addons) or None,
        agent_id=agent_id,
    ))


@backup.command("agents")
@click.pass_context
def backup_agents(ctx):
    emit(ctx, backup_core.agents_info(make_client(ctx)))


# 2. SYSTEM CONTROL
@system.command("restart")
@click.option("--safe-mode", is_flag=True, default=False)
@click.confirmation_option(prompt="Restart Home Assistant?")
@click.pass_context
def system_restart(ctx, safe_mode):
    """Restart HA (the WS connection will drop; reconnect in 20-60s)."""
    emit(ctx, {"restart": "sent",
                "result": control_core.restart(make_client(ctx), safe_mode=safe_mode)})


@system.command("stop")
@click.confirmation_option(prompt="Stop Home Assistant? (won't auto-restart)")
@click.pass_context
def system_stop(ctx):
    emit(ctx, {"stop": "sent",
                "result": control_core.stop(make_client(ctx))})


@system.command("check-config")
@click.option("--wait", "wait_secs", default=8.0, type=float)
@click.pass_context
def system_check_config(ctx, wait_secs):
    """Validate configuration.yaml. Returns {valid, message?}."""
    emit(ctx, control_core.check_config(make_client(ctx), wait_secs=wait_secs))


@system.command("reload-core-config")
@click.confirmation_option(prompt="Reload core configuration? (mutating)")
@click.pass_context
def system_reload_core(ctx):
    emit(ctx, {"reloaded": "core_config",
                "result": control_core.reload_core_config(make_client(ctx))})


@system.command("reload-all")
@click.confirmation_option(
    prompt="Reload all integrations (automations, scripts, scenes, groups, "
           "templates, helpers, customize)?")
@click.pass_context
def system_reload_all(ctx):
    """Reload automations, scripts, scenes, groups, templates, helpers, customize — without restart."""
    emit(ctx, {"reloaded": "all",
                "result": control_core.reload_all(make_client(ctx))})


@system.command("safe-restart")
@click.option("--wait", "wait_secs", default=8.0, type=float,
              help="How long to wait for the config-check notification")
@click.confirmation_option(prompt="check-config first, then restart if clean?")
@click.pass_context
def system_safe_restart(ctx, wait_secs):
    """check-config; restart only if the check passes."""
    emit(ctx, control_core.safe_restart(make_client(ctx), wait_check_secs=wait_secs))


# 3. REPAIRS
@cli.group()
def repairs():
    """The Repairs feed — what HA thinks is wrong."""


@repairs.command("list")
@click.option("--severity", default=None,
              type=click.Choice(["error", "warning", "critical"]))
@click.option("--domain", default=None)
@click.option("--include-dismissed", is_flag=True, default=False)
@click.pass_context
def repairs_list(ctx, severity, domain, include_dismissed):
    rows = repairs_core.list_issues(
        make_client(ctx),
        severity=severity, domain=domain,
        include_dismissed=include_dismissed,
    )
    # Slim the rows for table display
    out = [{
        "domain": r.get("domain"),
        "issue_id": r.get("issue_id"),
        "severity": r.get("severity"),
        "breaks_in": r.get("breaks_in_ha_version"),
        "active_since": r.get("created"),
        "translation_key": r.get("translation_key"),
        "dismissed": bool(r.get("dismissed_version")),
    } for r in rows]
    emit(ctx, out)


@repairs.command("show")
@click.argument("issue_id")
@click.option("--domain", default=None)
@click.pass_context
def repairs_show(ctx, issue_id, domain):
    out = repairs_core.show(make_client(ctx), issue_id, domain=domain)
    if not out:
        _abort(f"no issue found with id={issue_id!r}")
    emit(ctx, out)


@repairs.command("ignore")
@click.argument("issue_id")
@click.option("--domain", required=True,
              help="The issue's domain (run `repairs list` to see)")
@click.option("--undismiss", is_flag=True, default=False,
              help="Un-dismiss an issue you previously ignored")
@click.pass_context
def repairs_ignore(ctx, issue_id, domain, undismiss):
    emit(ctx, repairs_core.ignore(
        make_client(ctx), issue_id=issue_id, domain=domain,
        ignore_value=not undismiss,
    ))


@repairs.command("fix")
@click.argument("issue_id")
@click.option("--domain", required=True)
@click.pass_context
def repairs_fix(ctx, issue_id, domain):
    """Start the fix-flow for an issue (returns the flow_id to drive)."""
    emit(ctx, repairs_core.fix(
        make_client(ctx), issue_id=issue_id, domain=domain,
    ))


# 4. PERSISTENT NOTIFICATIONS
@cli.group("notifications")
def notifications_grp():
    """Persistent notifications (the bell icon in the HA UI)."""


@notifications_grp.command("list")
@click.pass_context
def notifications_list(ctx):
    emit(ctx, notifications_core.list_notifications(make_client(ctx)))


@notifications_grp.command("create")
@click.argument("message")
@click.option("--title", default=None)
@click.option("--id", "notification_id", default=None,
              help="Stable id — calls with same id update in place")
@click.pass_context
def notifications_create(ctx, message, title, notification_id):
    emit(ctx, notifications_core.create(
        make_client(ctx),
        message=message, title=title,
        notification_id=notification_id,
    ))


@notifications_grp.command("dismiss")
@click.argument("notification_id")
@click.pass_context
def notifications_dismiss(ctx, notification_id):
    emit(ctx, notifications_core.dismiss(make_client(ctx), notification_id))


@notifications_grp.command("dismiss-all")
@click.confirmation_option(prompt="Dismiss ALL persistent notifications?")
@click.pass_context
def notifications_dismiss_all(ctx):
    emit(ctx, notifications_core.dismiss_all(make_client(ctx)))


@notifications_grp.command("mark-read")
@click.argument("notification_id")
@click.pass_context
def notifications_mark_read(ctx, notification_id):
    emit(ctx, notifications_core.mark_read(make_client(ctx), notification_id))


# 5. WATCH (event subscribe + state watch)
@event.command("subscribe")
@click.argument("event_type_pos", required=False, default=None,
                metavar="[EVENT_TYPE]")
@click.option("--type", "event_type_opt", default=None,
              help="Event type to filter (default: all events). Also accepted as positional arg.")
@click.option("--duration", type=float, default=10.0,
              help="Seconds to listen (default 10)")
@click.option("--limit", type=int, default=None,
              help="Stop after N events")
@click.option("--filter", "filters", multiple=True,
              help="Client-side filter, e.g. 'data.entity_id=sensor.x'. "
                   "Dotted-path key matched against str(value). Repeatable; AND.")
@click.pass_context
def event_subscribe(ctx, event_type_pos, event_type_opt, duration, limit, filters):
    """Tail the HA event bus.

    With --json, returns a list of captured events. Without --json, prints
    each event one per line as it arrives.

    --filter applies *after* the server-side event_type filter; useful when
    HA's subscribe_events doesn't support the narrower predicate you want.
    """
    event_type = event_type_opt or event_type_pos
    parsed_filters: list[tuple[tuple[str, ...], str]] = []
    for raw in filters:
        if "=" not in raw:
            raise click.ClickException(
                f"--filter expects key=value, got {raw!r}"
            )
        k, v = raw.split("=", 1)
        parsed_filters.append((tuple(k.split(".")), v))

    def _matches(evt) -> bool:
        for path, expected in parsed_filters:
            node = evt
            for p in path:
                if not isinstance(node, dict):
                    return False
                node = node.get(p)
            if str(node) != expected:
                return False
        return True

    if ctx.obj.get("as_json"):
        all_events = watch_core.subscribe_events(
            make_client(ctx),
            event_type=event_type, duration=duration, limit=limit,
        )
        if parsed_filters:
            all_events = [e for e in (all_events or []) if _matches(e)]
        emit(ctx, all_events)
        return

    def _cb(ev):
        if parsed_filters and not _matches(ev):
            return
        click.echo(json.dumps(ev, default=str))
    watch_core.subscribe_events(
        make_client(ctx),
        event_type=event_type, duration=duration, limit=limit,
        callback=_cb,
    )


@state.command("watch")
@click.argument("entity_id")
@click.option("--until-state", default=None,
              help="Stop as soon as the entity reaches this state")
@click.option("--duration", type=float, default=30.0)
@click.pass_context
def state_watch(ctx, entity_id, until_state, duration):
    """Watch one entity for state changes.

    Example:  state watch person.jon --until-state home --duration 600
    """
    if ctx.obj.get("as_json"):
        emit(ctx, watch_core.watch_state(
            make_client(ctx), entity_id,
            until_state=until_state, duration=duration,
        ))
        return
    def _cb(ev):
        new = (ev.get("data") or {}).get("new_state") or {}
        click.echo(f"{ev.get('time_fired','')} -> {new.get('state','?')}")
    watch_core.watch_state(
        make_client(ctx), entity_id,
        until_state=until_state, duration=duration,
        callback=_cb,
    )


# ──────────────────────────────────────────────────────── diagnostics + introspection

# 1. DIAGNOSTICS
@cli.group()
def diagnostics():
    """Integration / device diagnostics download — same JSON the UI's
    "Download diagnostics" link produces."""


@diagnostics.command("list")
@click.pass_context
def diagnostics_list(ctx):
    """List integrations that support diagnostics export."""
    emit(ctx, diagnostics_core.list_handlers(make_client(ctx)))


@diagnostics.command("get")
@click.argument("entry_id")
@click.option("-o", "--out", type=click.Path(), default=None,
              help="Save to file instead of printing")
@click.pass_context
def diagnostics_get(ctx, entry_id, out):
    """Download config-entry-level diagnostics."""
    data = diagnostics_core.get_config_entry(make_client(ctx), entry_id)
    if out:
        n = diagnostics_core.save_to_file(data, out)
        emit(ctx, {"saved": out, "bytes": n})
    else:
        emit(ctx, data)


@diagnostics.command("device")
@click.argument("entry_id")
@click.argument("device_id")
@click.option("-o", "--out", type=click.Path(), default=None)
@click.pass_context
def diagnostics_device(ctx, entry_id, device_id, out):
    """Download device-level diagnostics for a device managed by an integration."""
    data = diagnostics_core.get_device(make_client(ctx), entry_id, device_id)
    if out:
        n = diagnostics_core.save_to_file(data, out)
        emit(ctx, {"saved": out, "bytes": n})
    else:
        emit(ctx, data)


# 2. STATISTICS (long-term)
@cli.group()
def statistics():
    """Long-term statistics — the compacted recorder data behind every HA chart."""


@statistics.command("info")
@click.pass_context
def statistics_info(ctx):
    """Recorder DB state: backlog, migration, db_in_default_location, recording flag."""
    emit(ctx, statistics_core.info(make_client(ctx)))


@statistics.command("list")
@click.option("--statistic-type",
              type=click.Choice(["mean", "sum"], case_sensitive=False),
              default=None,
              help="Filter to ids that have this metric kind")
@click.option("--grep", default=None,
              help="Substring filter on statistic_id (case-insensitive)")
@click.pass_context
def statistics_list(ctx, statistic_type, grep):
    """List every statistic id the recorder has metadata for."""
    rows = statistics_core.list_statistic_ids(
        make_client(ctx),
        statistic_type=statistic_type.lower() if statistic_type else None,
    )
    if grep:
        g = grep.lower()
        rows = [r for r in rows if g in (r.get("statistic_id", "") or "").lower()]
    emit(ctx, rows)


@statistics.command("metadata")
@click.argument("statistic_ids", nargs=-1)
@click.pass_context
def statistics_metadata(ctx, statistic_ids):
    """Show the recorder's metadata for specific statistic ids (or all)."""
    emit(ctx, statistics_core.get_metadata(
        make_client(ctx), list(statistic_ids) or None,
    ))


@statistics.command("series")
@click.argument("statistic_ids", nargs=-1)
@click.option("--period", default="hour",
              type=click.Choice(["5minute", "hour", "day", "week", "month"]))
@click.option("--start", "start_time", default=None,
              help="ISO timestamp (default: 24h ago, UTC)")
@click.option("--end", "end_time", default=None)
@click.option("--type", "types", multiple=True,
              help="Value kinds to include: change|mean|min|max|state|sum|last_reset")
@click.option("--unit", "unit_pairs", multiple=True,
              help="Force-convert units (--unit sensor.foo=kWh, repeatable)")
@click.pass_context
def statistics_series(ctx, statistic_ids, period, start_time, end_time,
                        types, unit_pairs):
    """Fetch chart-data buckets for one or more statistic ids.

    Example:
      statistics series sensor.smart_meter_electricity_import_today \\
        --period hour --start 2026-05-10T00:00:00Z --type sum --type change
    """
    if not statistic_ids:
        _abort("provide at least one statistic_id")
    units = None
    if unit_pairs:
        units = {}
        for p in unit_pairs:
            if "=" not in p:
                _abort(f"--unit expected key=value, got {p!r}")
            k, v = p.split("=", 1)
            units[k.strip()] = v.strip()
    emit(ctx, statistics_core.statistics_during_period(
        make_client(ctx),
        statistic_ids=list(statistic_ids),
        start_time=start_time, end_time=end_time, period=period,
        types=list(types) or None, units=units,
    ))


@statistics.command("update-metadata")
@click.argument("statistic_id")
@click.option("--unit", "unit_of_measurement", default=None)
@click.pass_context
def statistics_update_metadata(ctx, statistic_id, unit_of_measurement):
    """Patch metadata after a sensor's unit changed upstream."""
    emit(ctx, statistics_core.update_metadata(
        make_client(ctx), statistic_id=statistic_id,
        unit_of_measurement=unit_of_measurement,
    ))


@statistics.command("clear")
@click.argument("statistic_ids", nargs=-1)
@click.confirmation_option(prompt="Clear statistics for these ids? (destructive)")
@click.pass_context
def statistics_clear(ctx, statistic_ids):
    if not statistic_ids:
        _abort("provide at least one statistic_id")
    emit(ctx, statistics_core.clear(make_client(ctx), list(statistic_ids)))


# 3. ASSIST / CONVERSATION
@cli.group()
def assist():
    """Send text to HA's conversation pipeline (Assist)."""


@assist.command("ask")
@click.argument("text")
@click.option("--conversation-id", default=None,
              help="Reuse a previous conversation context")
@click.option("--language", default=None)
@click.option("--agent", "agent_id", default=None,
              help="Specific Assist pipeline or conversation agent id")
@click.pass_context
def assist_ask(ctx, text, conversation_id, language, agent_id):
    """Ask HA a question; returns the structured response."""
    emit(ctx, assist_core.process(
        make_client(ctx), text,
        conversation_id=conversation_id, language=language, agent_id=agent_id,
    ))


@assist.command("pipelines")
@click.pass_context
def assist_pipelines(ctx):
    """List configured Assist pipelines + the preferred one."""
    emit(ctx, assist_core.pipelines(make_client(ctx)))


@assist.command("pipeline-get")
@click.argument("pipeline_id")
@click.pass_context
def assist_pipeline_get(ctx, pipeline_id):
    emit(ctx, assist_core.pipeline_get(make_client(ctx), pipeline_id))


# 4. UPDATES
@cli.group("updates")
def updates_grp():
    """Manage update.* entities (HA Core, add-ons, integrations, devices)."""


@updates_grp.command("list")
@click.option("--all", "include_off", is_flag=True, default=False,
              help="Include entities with no update available")
@click.pass_context
def updates_list(ctx, include_off):
    emit(ctx, updates_core.list_updates(
        make_client(ctx), available_only=not include_off,
    ))


@updates_grp.command("install")
@click.argument("entity_id")
@click.option("--version", default=None,
              help="Specific version (default: latest)")
@click.option("--backup", is_flag=True, default=False,
              help="Backup before installing")
@click.pass_context
def updates_install(ctx, entity_id, version, backup):
    emit(ctx, updates_core.install(
        make_client(ctx), entity_id, version=version, backup=backup,
    ))


@updates_grp.command("skip")
@click.argument("entity_id")
@click.pass_context
def updates_skip(ctx, entity_id):
    emit(ctx, updates_core.skip(make_client(ctx), entity_id))


@updates_grp.command("clear-skipped")
@click.argument("entity_id")
@click.pass_context
def updates_clear_skipped(ctx, entity_id):
    emit(ctx, updates_core.clear_skipped(make_client(ctx), entity_id))


# 5. ENTITY INSPECT (combined view)
@entity.command("inspect")
@click.argument("entity_id")
@click.option("--history/--no-history", default=False,
              help="Include recent history (slower on busy entities)")
@click.option("--history-hours", default=24, type=int)
@click.option("--no-references", is_flag=True, default=False,
              help="Skip the cross-search for automations/templates/lovelace")
@click.option("--ref-kind", multiple=True,
              type=click.Choice(["automation", "script", "scene",
                                  "template_helper", "lovelace"]),
              help="Restrict references search to these kinds")
@click.pass_context
def entity_inspect(ctx, entity_id, history, history_hours,
                     no_references, ref_kind):
    """One-shot diagnostic: state + registry + device + area + history + references."""
    emit(ctx, inspect_core.inspect_entity(
        make_client(ctx), entity_id,
        include_history=history, history_hours=history_hours,
        include_references=not no_references,
        reference_kinds=list(ref_kind) or None,
    ))


# ──────────────────────────────────────────────────────── config-flow (create new integration)

@cli.group("config-flow")
def config_flow():
    """Create new integrations via the config-flow API.

    Most integrations finish in a single step (host + credentials), in which
    case `config-flow create <handler> --data ...` is the one-shot.
    Multi-step flows (re-auth, OAuth) need init + configure separately.
    """


@config_flow.command("init")
@click.argument("handler")
@click.option("--advanced", "show_advanced_options", is_flag=True, default=False,
              help="Show advanced fields in the form schema")
@click.pass_context
def config_flow_init(ctx, handler, show_advanced_options):
    """Start a flow for integration `handler` (e.g. 'mqtt', 'mobile_app')."""
    emit(ctx, config_entries_core.flow_init(
        make_client(ctx), handler,
        show_advanced_options=show_advanced_options,
    ))


@config_flow.command("configure")
@click.argument("flow_id")
@click.option("--data", "-D", multiple=True,
              help="Form field key=value (repeatable, JSON values supported)")
@click.option("--data-file", type=click.Path(exists=True, dir_okay=False),
              help="Read form input as JSON from a file (for big payloads)")
@click.pass_context
def config_flow_configure(ctx, flow_id, data, data_file):
    """Submit user input to the current step of a flow."""
    if data_file:
        payload = json.loads(Path(data_file).read_text())
    else:
        payload = parse_kv_pairs(data) if data else {}
    emit(ctx, config_entries_core.flow_configure(make_client(ctx), flow_id, payload))


@config_flow.command("abort")
@click.argument("flow_id")
@click.pass_context
def config_flow_abort(ctx, flow_id):
    emit(ctx, config_entries_core.flow_abort(make_client(ctx), flow_id))


@config_flow.command("get")
@click.argument("flow_id")
@click.pass_context
def config_flow_get(ctx, flow_id):
    """Get the current step descriptor for a flow."""
    emit(ctx, config_entries_core.flow_get(make_client(ctx), flow_id))


@config_flow.command("create")
@click.argument("handler")
@click.option("--data", "-D", multiple=True,
              help="First-step form input as key=value (repeatable, JSON-aware)")
@click.option("--data-file", type=click.Path(exists=True, dir_okay=False))
@click.option("--advanced", "show_advanced_options", is_flag=True, default=False)
@click.pass_context
def config_flow_create(ctx, handler, data, data_file, show_advanced_options):
    """Init a flow and submit `--data` to its first step. Single-shot create.

    Example:
      config-flow create mqtt -D broker=10.32.100.5 -D port=1883
    """
    if data_file:
        payload = json.loads(Path(data_file).read_text())
    else:
        payload = parse_kv_pairs(data) if data else {}
    emit(ctx, config_entries_core.create(
        make_client(ctx), handler, payload,
        show_advanced_options=show_advanced_options,
    ))


# ──────────────────────────────────────────────────────── blueprints

@cli.group()
def blueprint():
    """Reusable automation / script blueprints."""


@blueprint.command("list")
@click.argument("domain", type=click.Choice(["automation", "script"]))
@click.pass_context
def blueprint_list(ctx, domain):
    """List installed blueprints for one domain (returns a {path: meta} map)."""
    emit(ctx, blueprints_core.list_blueprints(make_client(ctx), domain))


@blueprint.command("show")
@click.argument("domain", type=click.Choice(["automation", "script"]))
@click.argument("path")
@click.pass_context
def blueprint_show(ctx, domain, path):
    """Show one blueprint's full record."""
    out = blueprints_core.show(make_client(ctx), domain, path)
    if not out:
        _abort(f"no blueprint at {path!r} in {domain}")
    emit(ctx, out)


@blueprint.command("import")
@click.argument("url")
@click.pass_context
def blueprint_import(ctx, url):
    """Import a blueprint from a URL (GitHub, gist, raw .yaml).

    Returns metadata + suggested_filename. Use `blueprint save` next to
    persist it under `blueprints/<domain>/<path>.yaml`.
    """
    emit(ctx, blueprints_core.import_blueprint(make_client(ctx), url=url))


@blueprint.command("save")
@click.argument("domain", type=click.Choice(["automation", "script"]))
@click.argument("path")
@click.argument("yaml_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--source-url", default=None,
              help="Original import URL (preserved for traceability)")
@click.pass_context
def blueprint_save(ctx, domain, path, yaml_file, source_url):
    """Persist a blueprint YAML to `blueprints/<domain>/<path>.yaml`."""
    yaml_text = Path(yaml_file).read_text()
    emit(ctx, blueprints_core.save_imported(
        make_client(ctx),
        domain=domain, path=path, yaml_text=yaml_text,
        source_url=source_url,
    ))


@blueprint.command("delete")
@click.argument("domain", type=click.Choice(["automation", "script"]))
@click.argument("path")
@click.confirmation_option(prompt="Delete this blueprint?")
@click.pass_context
def blueprint_delete(ctx, domain, path):
    emit(ctx, blueprints_core.delete(
        make_client(ctx), domain=domain, path=path,
    ))


@blueprint.command("substitute")
@click.argument("domain", type=click.Choice(["automation", "script"]))
@click.argument("path")
@click.option("--input", "-i", "inputs", multiple=True,
              help="Blueprint input key=value (repeatable, JSON values)")
@click.option("--input-file", type=click.Path(exists=True, dir_okay=False),
              help="Read inputs as JSON from a file")
@click.pass_context
def blueprint_substitute(ctx, domain, path, inputs, input_file):
    """Render a blueprint with the supplied inputs.

    Returns the resulting automation/script body — useful as a dry-run before
    instantiating it.
    """
    if input_file:
        user_input = json.loads(Path(input_file).read_text())
    else:
        user_input = parse_kv_pairs(inputs) if inputs else {}
    emit(ctx, blueprints_core.substitute(
        make_client(ctx), domain=domain, path=path, user_input=user_input,
    ))


# ──────────────────────────────────────────────────────── energy

@cli.group()
def energy():
    """Energy dashboard preferences + fossil-fuel derivations."""


@energy.command("get-prefs")
@click.pass_context
def energy_get_prefs(ctx):
    """Read the full Energy dashboard config."""
    emit(ctx, energy_core.get_prefs(make_client(ctx)))


@energy.command("set-prefs")
@click.argument("prefs_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def energy_set_prefs(ctx, prefs_file, dry_run):
    """Replace the Energy dashboard config from a JSON file.

    Read the current shape with `energy get-prefs` first, edit, and pass back.
    """
    prefs = json.loads(Path(prefs_file).read_text())
    if dry_run:
        emit(ctx, {"dry_run": True, "would_save_keys": list(prefs.keys())})
        return
    emit(ctx, energy_core.save_prefs(make_client(ctx), prefs))


@energy.command("info")
@click.pass_context
def energy_info(ctx):
    """Energy integration capability flags."""
    emit(ctx, energy_core.info(make_client(ctx)))


@energy.command("fossil")
@click.argument("energy_statistic_ids", nargs=-1)
@click.option("--co2-signal", required=True,
              help="The sensor.* entity from the co2signal integration")
@click.option("--start", "start_time", required=True,
              help="ISO-8601 start time")
@click.option("--end", "end_time", default=None)
@click.option("--period", default="hour",
              type=click.Choice(["5minute", "hour", "day", "week", "month"]))
@click.pass_context
def energy_fossil(ctx, energy_statistic_ids, co2_signal, start_time,
                    end_time, period):
    """Compute fossil-fuel kWh-equivalent for energy stats over a period."""
    if not energy_statistic_ids:
        _abort("provide at least one energy_statistic_id")
    emit(ctx, energy_core.fossil_energy_consumption(
        make_client(ctx),
        energy_statistic_ids=list(energy_statistic_ids),
        co2_signal_entity=co2_signal,
        start_time=start_time, end_time=end_time, period=period,
    ))


# ──────────────────────────────────────────────────────── themes

@cli.group()
def theme():
    """Frontend themes — list / set / reload."""


@theme.command("list")
@click.option("--names-only", is_flag=True, default=False,
              help="Print just the sorted theme name list")
@click.pass_context
def theme_list(ctx, names_only):
    """Show installed themes + the configured default(s)."""
    if names_only:
        emit(ctx, themes_core.names(make_client(ctx)))
    else:
        emit(ctx, themes_core.list_themes(make_client(ctx)))


@theme.command("set")
@click.argument("name")
@click.option("--mode", default=None,
              type=click.Choice(["dark", "light"]),
              help="Apply only for this color scheme (default: both)")
@click.pass_context
def theme_set(ctx, name, mode):
    """Set the active theme. Pass `default` to restore HA's built-in."""
    emit(ctx, themes_core.set_theme(make_client(ctx), name, mode=mode))


@theme.command("reload")
@click.pass_context
def theme_reload(ctx):
    """Reload themes from configuration.yaml."""
    emit(ctx, themes_core.reload(make_client(ctx)))


# ──────────────────────────────────────────────────────── calendars

@cli.group()
def calendar():
    """Calendar entities — list / events / create / update / delete."""


@calendar.command("list")
@click.pass_context
def calendar_list(ctx):
    emit(ctx, calendars_core.list_calendars(make_client(ctx)))


@calendar.command("events")
@click.argument("entity_id")
@click.option("--start", default=None, help="ISO-8601 (default: now)")
@click.option("--end", default=None, help="ISO-8601 (default: +7d)")
@click.option("--duration", default=None,
              help="Alt to --end: '01:30:00' or '7 days' etc")
@click.pass_context
def calendar_events(ctx, entity_id, start, end, duration):
    """List events in a date range for one calendar entity."""
    emit(ctx, calendars_core.events(
        make_client(ctx), entity_id,
        start=start, end=end, duration=duration,
    ))


@calendar.command("create-event")
@click.argument("entity_id")
@click.option("--summary", required=True)
@click.option("--start", required=True,
              help="ISO timestamp (T present) or YYYY-MM-DD (all-day)")
@click.option("--end", default=None,
              help="ISO timestamp or YYYY-MM-DD (matches start's format)")
@click.option("--description", default=None)
@click.option("--location", default=None)
@click.option("--rrule", default=None,
              help="Recurrence rule, e.g. FREQ=WEEKLY;BYDAY=MO,WE,FR")
@click.pass_context
def calendar_create(ctx, entity_id, summary, start, end, description,
                      location, rrule):
    emit(ctx, calendars_core.create_event(
        make_client(ctx), entity_id,
        summary=summary, start=start, end=end,
        description=description, location=location, rrule=rrule,
    ))


@calendar.command("update-event")
@click.argument("entity_id")
@click.option("--uid", required=True, help="Event uid (from `calendar events`)")
@click.option("--summary", default=None)
@click.option("--start", default=None)
@click.option("--end", default=None)
@click.option("--description", default=None)
@click.option("--location", default=None)
@click.option("--rrule", default=None)
@click.option("--recurrence-id", default=None)
@click.option("--recurrence-range", default=None)
@click.pass_context
def calendar_update(ctx, entity_id, uid, summary, start, end,
                      description, location, rrule, recurrence_id, recurrence_range):
    emit(ctx, calendars_core.update_event(
        make_client(ctx), entity_id,
        uid=uid, summary=summary, start=start, end=end,
        description=description, location=location, rrule=rrule,
        recurrence_id=recurrence_id, recurrence_range=recurrence_range,
    ))


@calendar.command("delete-event")
@click.argument("entity_id")
@click.option("--uid", required=True)
@click.option("--recurrence-id", default=None)
@click.option("--recurrence-range", default=None,
              type=click.Choice(["THISANDFUTURE", "THISANDPRIOR"]))
@click.confirmation_option(prompt="Delete this event?")
@click.pass_context
def calendar_delete(ctx, entity_id, uid, recurrence_id, recurrence_range):
    emit(ctx, calendars_core.delete_event(
        make_client(ctx), entity_id,
        uid=uid, recurrence_id=recurrence_id,
        recurrence_range=recurrence_range,
    ))


# ──────────────────────────────────────────────────────── tts

@cli.group()
def tts():
    """Text-to-speech — engines list / speak / clear-cache."""


@tts.command("list")
@click.pass_context
def tts_list(ctx):
    """List every tts.* engine + its languages."""
    emit(ctx, tts_core.list_engines(make_client(ctx)))


@tts.command("speak")
@click.argument("tts_entity")
@click.argument("message")
@click.option("--media-player", "media_player_entity", required=True)
@click.option("--language", default=None)
@click.option("--no-cache", is_flag=True, default=False,
              help="Bypass HA's TTS audio cache (re-synth even if cached)")
@click.option("--option", "options_kv", multiple=True,
              help="Engine option key=value (repeatable)")
@click.pass_context
def tts_speak(ctx, tts_entity, message, media_player_entity, language,
                no_cache, options_kv):
    """Synthesise `message` via `tts_entity` and play on `--media-player`."""
    options = parse_kv_pairs(options_kv) if options_kv else None
    emit(ctx, tts_core.speak(
        make_client(ctx),
        tts_entity=tts_entity,
        media_player_entity=media_player_entity,
        message=message, language=language,
        options=options, cache=not no_cache,
    ))


@tts.command("clear-cache")
@click.argument("tts_entity", required=False)
@click.confirmation_option(prompt="Clear TTS audio cache?")
@click.pass_context
def tts_clear_cache(ctx, tts_entity):
    emit(ctx, tts_core.clear_cache(make_client(ctx), tts_entity))


# ──────────────────────────────────────────────────────── subentries

@cli.group()
def subentry():
    """Manage config-entry SUBENTRIES (e.g. Google AI conversation/tts/stt/ai_task_data).

    Many modern integrations expose sub-configurations on one config entry —
    each subentry has its own reconfigure flow distinct from the parent
    entry's options. Use this group to list, inspect, and reconfigure them.
    """


@subentry.command("list")
@click.argument("entry_id")
@click.pass_context
def subentry_list(ctx, entry_id):
    """List subentries of a parent config entry."""
    rows = subentries_core.list_subentries(make_client(ctx), entry_id)
    if not ctx.obj.get("as_json"):
        # Compact display
        rows = [{
            "subentry_id": r.get("subentry_id"),
            "subentry_type": r.get("subentry_type"),
            "title": r.get("title"),
            "unique_id": r.get("unique_id"),
        } for r in rows]
    emit(ctx, rows)


@subentry.command("show")
@click.argument("entry_id")
@click.argument("ident",
                 metavar="SUBENTRY_ID_OR_TITLE")
@click.pass_context
def subentry_show(ctx, entry_id, ident):
    """Show the current options of a subentry.

    `ident` is either the subentry_id (`01K...`) or its title (case-
    insensitive match against `subentry list`).
    """
    emit(ctx, subentries_core.read_subentry(make_client(ctx), entry_id, ident))


@subentry.command("reconfigure")
@click.argument("entry_id")
@click.argument("ident",
                 metavar="SUBENTRY_ID_OR_TITLE")
@click.option("--set", "set_pairs", multiple=True,
              help="Field override key=value (repeatable, JSON-aware)")
@click.option("--data-file", type=click.Path(exists=True, dir_okay=False),
              help="Read full overrides as JSON from a file")
@click.option("--dry-run", is_flag=True, default=False,
              help="Print the would-be merged payload without submitting")
@click.pass_context
def subentry_reconfigure(ctx, entry_id, ident, set_pairs, data_file, dry_run):
    """Reconfigure a subentry, preserving untouched fields.

    Examples:

      # Switch the AI Task model on a Google Generative AI entry
      cli-anything-homeassistant subentry reconfigure \\
          34a3b367d65a3e0b61a99d7202f7d4eb 'Google AI Task' \\
          --set chat_model=models/gemini-2.5-flash \\
          --set recommended=false

      # Read-only preview
      cli-anything-homeassistant subentry reconfigure ... --dry-run
    """
    overrides: dict = {}
    if data_file:
        overrides.update(json.loads(Path(data_file).read_text()))
    if set_pairs:
        overrides.update(parse_kv_pairs(set_pairs))
    if not overrides:
        _abort("provide at least one --set key=value or --data-file")
    emit(ctx, subentries_core.reconfigure(
        make_client(ctx), entry_id, ident, overrides, dry_run=dry_run,
    ))


# ──────────────────────────────────────────────────────── HACS

@cli.group()
def hacs():
    """HACS (Home Assistant Community Store) repository management."""


@hacs.command("info")
@click.pass_context
def hacs_info(ctx):
    """Global HACS state: version, stage, categories."""
    emit(ctx, hacs_core.info(make_client(ctx)))


@hacs.command("list")
@click.option("--installed", is_flag=True, default=False,
              help="Only show installed repos (default: every known repo, ~3000)")
@click.option("--category", default=None,
              help="Filter by category (integration / plugin / theme / appdaemon / ...)")
@click.option("--pattern", default=None,
              help="Substring filter on name OR full_name (case-insensitive)")
@click.pass_context
def hacs_list(ctx, installed, category, pattern):
    rows = hacs_core.list_repos(
        make_client(ctx),
        installed_only=installed, category=category, pattern=pattern,
    )
    # Slim output for the table view
    slim = [{
        "id": r.get("id"),
        "full_name": r.get("full_name"),
        "category": r.get("category"),
        "installed": r.get("installed"),
        "installed_version": r.get("installed_version"),
        "available_version": r.get("available_version"),
    } for r in rows]
    emit(ctx, slim if not ctx.obj.get("as_json") else rows)


@hacs.command("show")
@click.argument("ident")
@click.pass_context
def hacs_show(ctx, ident):
    emit(ctx, hacs_core.show(make_client(ctx), ident))


@hacs.command("install")
@click.argument("ident")
@click.option("--version", default=None,
              help="Specific version tag (default: latest)")
@click.confirmation_option(prompt="Install this HACS repo?")
@click.pass_context
def hacs_install(ctx, ident, version):
    emit(ctx, hacs_core.install(make_client(ctx), ident, version=version))


@hacs.command("remove")
@click.argument("ident")
@click.confirmation_option(prompt="Uninstall this HACS repo? (deletes files + resource)")
@click.pass_context
def hacs_remove(ctx, ident):
    emit(ctx, hacs_core.remove(make_client(ctx), ident))


@hacs.command("refresh")
@click.argument("ident")
@click.pass_context
def hacs_refresh(ctx, ident):
    """Re-fetch upstream metadata for one repo (versions, README, etc)."""
    emit(ctx, hacs_core.refresh(make_client(ctx), ident))


# ──────────────────────────────────────────────────────── subentry list-all

@subentry.command("list-all")
@click.option("--type", "subentry_type", default=None,
              help="Filter to one subentry_type (e.g. 'ai_task_data')")
@click.option("--title", "title_pattern", default=None,
              help="Substring match on subentry title (case-insensitive)")
@click.option("--domain", default=None,
              help="Restrict to parent entries in this integration domain")
@click.pass_context
def subentry_list_all(ctx, subentry_type, title_pattern, domain):
    """List subentries across EVERY config entry.

    Use this when you don't know which integration owns the subentry.
    Returns each subentry with entry_id / entry_title / entry_domain merged in.
    """
    emit(ctx, subentries_core.list_all(
        make_client(ctx),
        subentry_type=subentry_type, title_pattern=title_pattern, domain=domain,
    ))


# ──────────────────────────────────────────────────────── config-flow walk

@config_flow.command("walk")
@click.argument("handler")
@click.argument("step_files", nargs=-1, type=click.Path(exists=True, dir_okay=False))
@click.option("--advanced", "show_advanced_options", is_flag=True, default=False)
@click.option("--stop-on-form", is_flag=True, default=False,
              help="Stop and return the form if the flow asks for more input")
@click.pass_context
def config_flow_walk(ctx, handler, step_files, show_advanced_options, stop_on_form):
    """Drive a multi-step config flow: init → submit each step file in turn.

    Each STEP_FILE is a JSON file with the payload for that step. The flow
    aborts cleanly on any error.

    Example:
      config-flow walk statistics step1.json step2.json step3.json
    """
    if not step_files:
        _abort("provide at least one step file")
    steps = [json.loads(Path(f).read_text()) for f in step_files]
    emit(ctx, config_entries_core.walk(
        make_client(ctx), handler, steps,
        show_advanced_options=show_advanced_options,
        stop_on_form=stop_on_form,
    ))


# ──────────────────────────────────────────────────────── lovelace card patch

@lovelace_card.command("patch")
@click.argument("url_path")
@click.option("--pointer", required=True,
              help="Card pointer, e.g. 'views[3]/cards[11]/cards[0]/cards[0]'")
@click.option("--set", "set_pairs", multiple=True,
              help="Field override key=value (repeatable, JSON-aware)")
@click.option("--data-file", type=click.Path(exists=True, dir_okay=False),
              help="Read patch as a JSON object from a file")
@click.option("--strict", is_flag=True, default=False,
              help="Error if a field doesn't already exist on the card")
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def lovelace_card_patch(ctx, url_path, pointer, set_pairs, data_file, strict, dry_run):
    """Patch individual fields on one card by pointer.

    Avoids fetching/pushing the whole dashboard for a one-field change:

      lovelace card patch jon-mobile --pointer views[3]/cards[11]/cards[0]/cards[0] \\
          --set camera_image=camera.doorbell_last_event
    """
    fields: dict = {}
    if data_file:
        fields.update(json.loads(Path(data_file).read_text()))
    if set_pairs:
        fields.update(parse_kv_pairs(set_pairs))
    if not fields:
        _abort("provide at least one --set key=value or --data-file")

    # The existing pointer-resolver in lovelace_cards_core uses
    # `views[N]/cards[M]/...` syntax. Convert to the dot-path lovelace_paths
    # expects.
    # Easy bridge: parse the pointer into a dot-path via _resolve_dotpath's
    # input format.
    # Format: views[3]/cards[11]/cards[0]/cards[0] →
    #         "3.sections.0.cards.0" OR "3.cards.0" depending on view shape
    cfg = lovelace_core.get_dashboard_config(make_client(ctx), url_path)
    # Convert the / pointer to the dot-form by walking the tree.
    parts = [p for p in pointer.split("/") if p]
    target = cfg
    walked_keys: list[str] = []
    for p in parts:
        if "[" in p and p.endswith("]"):
            base, idx = p.split("[", 1)
            idx = int(idx[:-1])
            target = target[base][idx] if base else target[idx]
            walked_keys.append(base or str(idx))
            walked_keys.append(str(idx))
        else:
            target = target[p]
            walked_keys.append(p)
    if not isinstance(target, dict):
        _abort(f"pointer {pointer!r} resolves to a {type(target).__name__}, not a card")

    if dry_run:
        before = {k: target.get(k) for k in fields}
        emit(ctx, {"pointer": pointer, "dry_run": True,
                    "before": before, "would_set": fields})
        return

    # Apply patch in-place to the dict we walked into (cfg is mutated)
    for k, v in fields.items():
        if strict and k not in target:
            _abort(f"unknown field {k!r}; existing: {sorted(target)}")
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            target[k] = {**target[k], **v}
        else:
            target[k] = v
    res = lovelace_core.save_dashboard_config(make_client(ctx), url_path, cfg)
    emit(ctx, {"pointer": pointer, "patched_fields": list(fields),
                "result": res})


# ──────────────────────────────────────────────────────── lovelace v1.14: layout ops

@lovelace_card.command("move")
@click.argument("url_path")
@click.argument("src_pointer")
@click.argument("dest_parent_pointer")
@click.option("--index", type=int, default=None,
                help="Position in destination cards[] (default: append)")
@click.pass_context
def lovelace_card_move(ctx, url_path, src_pointer, dest_parent_pointer, index):
    """Move a card from one pointer to another container's cards[]."""
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        lovelace_card_ops_core.move_card(cfg, src_pointer, dest_parent_pointer,
                                            index=index)
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"moved": src_pointer, "to": dest_parent_pointer,
                 "at_index": index})


@lovelace_card.command("reorder")
@click.argument("url_path")
@click.argument("pointer")
@click.argument("new_index", type=int)
@click.pass_context
def lovelace_card_reorder(ctx, url_path, pointer, new_index):
    """Change a card's index within its current parent list."""
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        lovelace_card_ops_core.reorder_card(cfg, pointer, new_index)
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"reordered": pointer, "to_index": new_index})


@lovelace_card.command("wrap")
@click.argument("url_path")
@click.argument("pointers", nargs=-1, required=True)
@click.option("--stack-type",
                type=click.Choice(["vertical-stack", "horizontal-stack", "grid"]),
                default="vertical-stack", show_default=True)
@click.option("--columns", type=int, default=None,
                help="Grid column count (only with --stack-type grid)")
@click.option("--title", help="Optional title for the new stack")
@click.pass_context
def lovelace_card_wrap(ctx, url_path, pointers, stack_type, columns, title):
    """Wrap one or more cards (sharing a parent) into a stack card."""
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        new_ptr = lovelace_card_ops_core.wrap_in_stack(
            cfg, list(pointers), stack_type=stack_type,
            columns=columns, title=title,
        )
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"wrapped": list(pointers), "stack_type": stack_type,
                 "new_pointer": new_ptr})


@lovelace_card.command("wrap-conditional")
@click.argument("url_path")
@click.argument("pointer")
@click.option("--entity", required=True,
                help="Entity to gate on")
@click.option("--state", required=True,
                help="State value the entity must equal")
@click.pass_context
def lovelace_card_wrap_conditional(ctx, url_path, pointer, entity, state):
    """Wrap a card in a `conditional` showing it only when entity == state."""
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    cond = [{"entity": entity, "state": state}]
    try:
        lovelace_card_ops_core.wrap_in_conditional(cfg, pointer, cond)
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"wrapped": pointer, "condition": cond[0]})


@lovelace_card.command("duplicate")
@click.argument("url_path")
@click.argument("pointer")
@click.option("--substitute", "-s", "subs", multiple=True,
                help="Regex substitution old=new (repeatable)")
@click.option("--index-offset", default=1, type=int, show_default=True,
                help="Insert N positions after the source")
@click.pass_context
def lovelace_card_duplicate(ctx, url_path, pointer, subs, index_offset):
    """Clone a card; optionally apply --substitute regex pairs."""
    sub_map: dict[str, str] = {}
    for s in subs:
        if "=" not in s:
            _abort(f"--substitute must be 'old=new', got {s!r}")
        k, v = s.split("=", 1)
        sub_map[k] = v
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        new_ptr = lovelace_card_ops_core.duplicate_card(
            cfg, pointer, substitutions=sub_map or None,
            index_offset=index_offset,
        )
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"duplicated": pointer, "new_pointer": new_ptr,
                 "substitutions": sub_map})


@lovelace_card.command("style")
@click.argument("url_path")
@click.argument("pointer")
@click.option("--css", help="Raw CSS to inject")
@click.option("--css-file", type=click.Path(exists=True, dir_okay=False),
                help="Read CSS from a file instead")
@click.option("--target", default="root", show_default=True,
                help="Card-mod target selector (root, ha-card, etc.)")
@click.option("--clear", is_flag=True,
                help="Remove all card_mod from this card instead")
@click.pass_context
def lovelace_card_style(ctx, url_path, pointer, css, css_file, target, clear):
    """Inject a card_mod CSS block on a card (or --clear to remove)."""
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    if clear:
        try:
            lovelace_card_ops_core.clear_card_mod(cfg, pointer)
        except (KeyError, IndexError, ValueError) as e:
            _abort(str(e))
        lovelace_core.save_dashboard_config(client, url_path, cfg)
        emit(ctx, {"cleared_card_mod_on": pointer})
        return
    css_text = css
    if css_file:
        css_text = (css_text or "") + "\n" + Path(css_file).read_text()
    if not css_text:
        _abort("provide --css or --css-file (or --clear)")
    try:
        lovelace_card_ops_core.inject_card_mod(cfg, pointer, css_text, target=target)
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"styled": pointer, "target": target,
                 "css_lines": len(css_text.splitlines())})


# ──────────────────────────────────────────────────────── lovelace v1.14: card create

@lovelace_card.command("types")
@click.option("--dashboard", "url_path", default=None,
                help="Limit to one dashboard (default: scan all)")
@click.option("--installed", is_flag=True,
                help="Cross-reference custom types against HACS plugins")
@click.pass_context
def lovelace_card_types_cmd(ctx, url_path, installed):
    """List every card `type:` in use across dashboards."""
    client = make_client(ctx)
    if url_path:
        cfg = lovelace_core.get_dashboard_config(client, url_path)
        types = lovelace_card_types_core.card_types_in_use(cfg)
        out: dict = {"dashboard": url_path, "types": types}
    else:
        out = {"by_dashboard": lovelace_card_types_core.types_across_dashboards(client)}
        # also unique aggregate
        all_types: dict[str, int] = {}
        for d, ts in out["by_dashboard"].items():
            for t, n in ts.items():
                all_types[t] = all_types.get(t, 0) + n
        out["unique"] = sorted(all_types)
    if installed:
        all_types_list = []
        if "types" in out:
            all_types_list = list(out["types"])
        else:
            all_types_list = out["unique"]
        custom = lovelace_card_types_core.custom_types_only(all_types_list)
        if custom:
            out["hacs_matches"] = lovelace_card_types_core.cross_reference_hacs(
                client, custom,
            )
    emit(ctx, out)


@lovelace_card.command("builders")
@click.pass_context
def lovelace_card_builders_cmd(ctx):
    """List every card type that has a built-in builder."""
    emit(ctx, {"builders": lovelace_builders_core.list_builders()})


@lovelace_card.command("create")
@click.argument("url_path")
@click.argument("parent_pointer")
@click.argument("card_type")
@click.option("--set", "set_pairs", multiple=True,
                help="Builder kwarg as key=value (JSON-aware, repeatable)")
@click.option("--data-file", type=click.Path(exists=True, dir_okay=False),
                help="Read full builder kwargs from a JSON file")
@click.option("--position", type=int, default=None,
                help="Insert at this index in parent's cards[]")
@click.option("--dry-run", is_flag=True, default=False,
                help="Build and print the card without saving")
@click.pass_context
def lovelace_card_create(ctx, url_path, parent_pointer, card_type,
                            set_pairs, data_file, position, dry_run):
    """Create a card via a type-aware builder and insert it.

    Run `lovelace card builders` to list every known type. Builder kwargs
    are passed via --set name=value; values are parsed as JSON when
    possible (so `--set entities='["light.a","light.b"]'` becomes a list).
    """
    kwargs: dict = {}
    if data_file:
        kwargs.update(json.loads(Path(data_file).read_text()))
    if set_pairs:
        kwargs.update(parse_kv_pairs(set_pairs))
    try:
        new_card = lovelace_builders_core.build(card_type, **kwargs)
    except (TypeError, ValueError) as e:
        _abort(f"build failed: {e}")
    if dry_run:
        emit(ctx, {"would_insert_at": parent_pointer, "card": new_card})
        return
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        lovelace_cards_core.insert_card(cfg, parent_pointer, new_card,
                                          position=position)
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"created": new_card.get("type"),
                 "into": parent_pointer, "position": position})


# ──────────────────────────────────────────────────────── lovelace v1.14: section CRUD

@lovelace_section.command("list")
@click.argument("url_path")
@click.argument("view_path")
@click.pass_context
def lovelace_section_list(ctx, url_path, view_path):
    """List sections in a sections view."""
    cfg = lovelace_core.get_dashboard_config(make_client(ctx), url_path)
    try:
        sections = lovelace_sections_core.list_sections(cfg, view_path)
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    emit(ctx, [{"index": i, "type": s.get("type"),
                  "cards": len(s.get("cards", []))}
                 for i, s in enumerate(sections)])


@lovelace_section.command("add")
@click.argument("url_path")
@click.argument("view_path")
@click.option("--title", help="Section heading title")
@click.option("--column-span", type=int)
@click.option("--index", type=int, default=None,
                help="Insert at this position (default: append)")
@click.pass_context
def lovelace_section_add(ctx, url_path, view_path, title, column_span, index):
    """Add a new section to a sections view."""
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        section = lovelace_sections_core.add_section(
            cfg, view_path, title=title,
            column_span=column_span, index=index,
        )
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"added": section})


@lovelace_section.command("delete")
@click.argument("url_path")
@click.argument("view_path")
@click.argument("section_idx", type=int)
@click.pass_context
def lovelace_section_delete(ctx, url_path, view_path, section_idx):
    """Delete a section by index."""
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        lovelace_sections_core.delete_section(cfg, view_path, section_idx)
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"deleted_section": section_idx})


@lovelace_section.command("move")
@click.argument("url_path")
@click.argument("view_path")
@click.argument("section_idx", type=int)
@click.argument("new_index", type=int)
@click.pass_context
def lovelace_section_move(ctx, url_path, view_path, section_idx, new_index):
    """Move a section to a new index within its view."""
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        lovelace_sections_core.move_section(cfg, view_path, section_idx, new_index)
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"moved_section": section_idx, "to_index": new_index})


# ──────────────────────────────────────────────────────── lovelace v1.14: badges

@lovelace.group("badge")
def lovelace_badge():
    """Badge (top-of-view chip) operations."""


@lovelace_badge.command("list")
@click.argument("url_path")
@click.argument("view_path")
@click.pass_context
def lovelace_badge_list(ctx, url_path, view_path):
    """List badges on a view."""
    cfg = lovelace_core.get_dashboard_config(make_client(ctx), url_path)
    try:
        badges = lovelace_badges_core.list_badges(cfg, view_path)
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    emit(ctx, badges)


@lovelace_badge.command("add")
@click.argument("url_path")
@click.argument("view_path")
@click.argument("entity_or_json")
@click.option("--index", type=int, default=None,
                help="Insert at this position (default: append)")
@click.pass_context
def lovelace_badge_add(ctx, url_path, view_path, entity_or_json, index):
    """Add a badge. ENTITY_OR_JSON is an entity_id string OR a JSON dict."""
    badge: object = entity_or_json
    if entity_or_json.strip().startswith("{"):
        try:
            badge = json.loads(entity_or_json)
        except json.JSONDecodeError as e:
            _abort(f"bad JSON: {e}")
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        lovelace_badges_core.add_badge(cfg, view_path, badge, index=index)
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"added_badge": badge})


@lovelace_badge.command("delete")
@click.argument("url_path")
@click.argument("view_path")
@click.argument("badge_idx", type=int)
@click.pass_context
def lovelace_badge_delete(ctx, url_path, view_path, badge_idx):
    """Delete a badge by index."""
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        lovelace_badges_core.delete_badge(cfg, view_path, badge_idx)
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"deleted_badge": badge_idx})


@lovelace_badge.command("move")
@click.argument("url_path")
@click.argument("view_path")
@click.argument("badge_idx", type=int)
@click.argument("new_index", type=int)
@click.pass_context
def lovelace_badge_move(ctx, url_path, view_path, badge_idx, new_index):
    """Move a badge to a new index."""
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        lovelace_badges_core.move_badge(cfg, view_path, badge_idx, new_index)
    except (KeyError, IndexError, ValueError) as e:
        _abort(str(e))
    lovelace_core.save_dashboard_config(client, url_path, cfg)
    emit(ctx, {"moved_badge": badge_idx, "to_index": new_index})


# ──────────────────────────────────────────────────────── small wins

@updates_grp.command("install-all")
@click.option("--exclude", "-x", multiple=True,
              help="Substring patterns to skip (repeatable)")
@click.option("--backup", is_flag=True, default=False,
              help="Backup before each install")
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def updates_install_all(ctx, exclude, backup, dry_run):
    """Install every available update in one go."""
    emit(ctx, updates_core.install_all(
        make_client(ctx),
        exclude=list(exclude) or None, backup=backup, dry_run=dry_run,
    ))


@entity.command("disable")
@click.argument("entity_id")
@click.pass_context
def entity_disable(ctx, entity_id):
    """Disable an entity (sets disabled_by=user)."""
    emit(ctx, registry_core.update_entity(make_client(ctx), entity_id,
                                            disabled_by="user"))


@entity.command("enable")
@click.argument("entity_id")
@click.pass_context
def entity_enable(ctx, entity_id):
    """Re-enable a previously disabled entity."""
    emit(ctx, registry_core.update_entity(make_client(ctx), entity_id,
                                            disabled_by=None))


@recorder.command("purge")
@click.option("--keep-days", type=int, default=None,
              help="How many days of history to keep (default: recorder's own)")
@click.option("--repack", is_flag=True, default=False,
              help="VACUUM the DB after purge (slow)")
@click.option("--apply-filter", is_flag=True, default=False,
              help="Apply include/exclude filter from configuration.yaml")
@click.confirmation_option(prompt="Purge recorder history?")
@click.pass_context
def recorder_purge(ctx, keep_days, repack, apply_filter):
    """Trigger recorder.purge — global retention enforcement."""
    emit(ctx, recorder_core.purge(make_client(ctx),
                                    keep_days=keep_days,
                                    repack=repack,
                                    apply_filter=apply_filter))


@recorder.command("purge-entities")
@click.option("--entity", "entity_ids", multiple=True,
              help="Exact entity_id to wipe (repeatable)")
@click.option("--domain", "domains", multiple=True,
              help="Wipe every entity in this domain (repeatable)")
@click.option("--glob", "entity_globs", multiple=True,
              help="Wildcard pattern e.g. 'sensor.test_*' (repeatable)")
@click.option("--days", type=int, default=None,
              help="Keep this many days; older rows go")
@click.confirmation_option(prompt="Purge history for these entities? (destructive)")
@click.pass_context
def recorder_purge_entities(ctx, entity_ids, domains, entity_globs, days):
    """Purge history for specific entities, domains, or wildcard patterns."""
    emit(ctx, recorder_core.purge_entities(
        make_client(ctx),
        entity_ids=list(entity_ids), domains=list(domains),
        entity_globs=list(entity_globs), days=days,
    ))


# ──────────────────────────────────────────────────────── scene

@cli.group()
def scene():
    """Activate / create / apply scenes (scene.* entities)."""


@scene.command("list")
@click.pass_context
def scene_list(ctx):
    """List every scene.* entity registered."""
    emit(ctx, scenes_core.list_scenes(make_client(ctx)))


@scene.command("activate")
@click.argument("entity_id")
@click.option("--transition", type=float, default=None,
              help="Fade duration in seconds")
@click.pass_context
def scene_activate(ctx, entity_id, transition):
    """Activate a stored scene by entity_id."""
    emit(ctx, scenes_core.activate(make_client(ctx), entity_id,
                                   transition=transition))


@scene.command("apply")
@click.option("--entity", "entity_pairs", multiple=True, required=True,
              help="entity_id=state or entity_id=<json-object> (repeatable)")
@click.option("--transition", type=float, default=None,
              help="Fade duration in seconds")
@click.pass_context
def scene_apply(ctx, entity_pairs, transition):
    """Apply an ad-hoc set of states without persisting a scene.

    Example:
      scene apply --entity light.kitchen=on \\
                  --entity 'light.lamp={"state":"on","brightness":120}'
    """
    entities = parse_kv_pairs(entity_pairs)
    emit(ctx, scenes_core.apply(make_client(ctx),
                                entities=entities,
                                transition=transition))


@scene.command("create")
@click.argument("scene_id")
@click.option("--entity", "entity_pairs", multiple=True,
              help="Explicit entity_id=state pair (repeatable)")
@click.option("--snapshot", "snapshot", multiple=True,
              help="entity_id whose current state will be captured (repeatable)")
@click.pass_context
def scene_create(ctx, scene_id, entity_pairs, snapshot):
    """Persist a new scene from explicit states and/or live snapshots."""
    entities = parse_kv_pairs(entity_pairs) if entity_pairs else None
    snap = list(snapshot) if snapshot else None
    if not entities and not snap:
        _abort("provide --entity and/or --snapshot")
    emit(ctx, scenes_core.create(make_client(ctx), scene_id=scene_id,
                                 entities=entities, snapshot_entities=snap))


@scene.command("reload")
@click.pass_context
def scene_reload(ctx):
    """Reload scenes from configuration.yaml."""
    emit(ctx, scenes_core.reload(make_client(ctx)))


# ──────────────────────────────────────────────────────── weather

@cli.group()
def weather():
    """Weather entities — list, forecast, unit conversions."""


@weather.command("list")
@click.pass_context
def weather_list(ctx):
    """List weather.* entities."""
    states = make_client(ctx).get("states")
    rows = [s for s in (states or []) if isinstance(s, dict)
            and (s.get("entity_id") or "").startswith("weather.")]
    emit(ctx, rows)


@weather.command("units")
@click.pass_context
def weather_units(ctx):
    """Show convertible units per measurement type (temperature, speed, ...)."""
    emit(ctx, weather_advanced_core.convertible_units(make_client(ctx)))


@weather.command("forecast")
@click.argument("entity_id")
@click.option("--type", "forecast_type", default="daily",
              type=click.Choice(["daily", "hourly", "twice_daily"]),
              help="Forecast resolution (default: daily)")
@click.pass_context
def weather_forecast(ctx, entity_id, forecast_type):
    """Fetch a one-shot forecast for a weather entity via the service API."""
    emit(ctx, weather_advanced_core.get_forecasts(
        make_client(ctx), entity_id=entity_id, forecast_type=forecast_type,
    ))


@weather.command("forecast-subscribe")
@click.argument("entity_id")
@click.option("--type", "forecast_type", default="daily",
              type=click.Choice(["daily", "hourly", "twice_daily"]))
@click.pass_context
def weather_forecast_subscribe(ctx, entity_id, forecast_type):
    """Issue a WS subscribe for forecast updates (one-shot subscribe ack)."""
    emit(ctx, weather_advanced_core.subscribe_forecast(
        make_client(ctx), entity_id=entity_id, forecast_type=forecast_type,
    ))


# ──────────────────────────────────────────────────────── shopping-list

@cli.group("shopping-list")
def shopping_list_grp():
    """Default shopping_list integration (the built-in HA list)."""


@shopping_list_grp.command("list")
@click.pass_context
def shopping_list_list(ctx):
    """List every shopping list item (id / name / complete)."""
    emit(ctx, shopping_list_core.list_items(make_client(ctx)))


@shopping_list_grp.command("add")
@click.argument("name")
@click.pass_context
def shopping_list_add(ctx, name):
    """Add a new item."""
    emit(ctx, shopping_list_core.add_item(make_client(ctx), name=name))


@shopping_list_grp.command("update")
@click.argument("item_id")
@click.option("--name", default=None, help="Rename the item")
@click.option("--complete/--incomplete", "complete", default=None,
              help="Mark complete / incomplete")
@click.pass_context
def shopping_list_update(ctx, item_id, name, complete):
    """Update an item (rename and/or set complete state)."""
    if name is None and complete is None:
        _abort("provide --name and/or --complete/--incomplete")
    emit(ctx, shopping_list_core.update_item(
        make_client(ctx), item_id=item_id, name=name, complete=complete,
    ))


@shopping_list_grp.command("remove")
@click.argument("item_id")
@click.confirmation_option(prompt="Remove this shopping-list item?")
@click.pass_context
def shopping_list_remove(ctx, item_id):
    """Remove an item by id."""
    emit(ctx, shopping_list_core.remove_item(
        make_client(ctx), item_id=item_id,
    ))


@shopping_list_grp.command("clear-completed")
@click.confirmation_option(prompt="Remove every completed shopping-list item?")
@click.pass_context
def shopping_list_clear(ctx):
    """Remove every item with complete=True."""
    emit(ctx, shopping_list_core.clear_completed(make_client(ctx)))


@shopping_list_grp.command("reorder")
@click.argument("item_ids", nargs=-1, required=True)
@click.pass_context
def shopping_list_reorder(ctx, item_ids):
    """Reorder items by passing the ids in the new order."""
    emit(ctx, shopping_list_core.reorder_items(
        make_client(ctx), item_ids=list(item_ids),
    ))


# ──────────────────────────────────────────────────────── todo

@cli.group()
def todo():
    """todo.* entities (any HA todo integration — Google Tasks, local, ...)."""


@todo.command("list")
@click.argument("entity_id")
@click.pass_context
def todo_list(ctx, entity_id):
    """List items in a todo list."""
    emit(ctx, todos_core.list_items(make_client(ctx), entity_id))


@todo.command("add")
@click.argument("entity_id")
@click.argument("summary")
@click.option("--due", default=None, help="ISO date or datetime")
@click.option("--description", default=None, help="Free-text note")
@click.pass_context
def todo_add(ctx, entity_id, summary, due, description):
    """Add a new todo item."""
    emit(ctx, todos_core.add_item(make_client(ctx), entity_id,
                                  summary=summary, due=due,
                                  description=description))


@todo.command("update")
@click.argument("entity_id")
@click.argument("item")
@click.option("--rename", default=None, help="New summary text")
@click.option("--status", default=None,
              type=click.Choice(["needs_action", "completed"]))
@click.option("--due", default=None)
@click.option("--description", default=None)
@click.pass_context
def todo_update(ctx, entity_id, item, rename, status, due, description):
    """Update a todo item (`item` may be its summary or uid)."""
    if rename is None and status is None and due is None and description is None:
        _abort("provide --rename / --status / --due / --description")
    emit(ctx, todos_core.update_item(
        make_client(ctx), entity_id,
        item=item, rename=rename, status=status,
        due=due, description=description,
    ))


@todo.command("complete")
@click.argument("entity_id")
@click.argument("item")
@click.pass_context
def todo_complete(ctx, entity_id, item):
    """Convenience: mark an item completed."""
    emit(ctx, todos_core.update_item(
        make_client(ctx), entity_id, item=item, status="completed",
    ))


@todo.command("remove")
@click.argument("entity_id")
@click.argument("items", nargs=-1, required=True)
@click.confirmation_option(prompt="Remove the listed todo item(s)?")
@click.pass_context
def todo_remove(ctx, entity_id, items):
    """Remove one or more items by uid or summary."""
    target: str | list[str] = items[0] if len(items) == 1 else list(items)
    emit(ctx, todos_core.remove_item(
        make_client(ctx), entity_id, item=target,
    ))


@todo.command("move")
@click.argument("entity_id")
@click.argument("uid")
@click.option("--after", "previous_uid", default=None,
              help="uid that should precede the moved item (omit = move to top)")
@click.pass_context
def todo_move(ctx, entity_id, uid, previous_uid):
    """Move an item to a new position."""
    emit(ctx, todos_core.move_item(make_client(ctx), entity_id,
                                   uid=uid, previous_uid=previous_uid))


@todo.command("clear-completed")
@click.argument("entity_id")
@click.confirmation_option(prompt="Remove every completed item from this todo list?")
@click.pass_context
def todo_clear_completed(ctx, entity_id):
    """Remove every completed item from a todo list."""
    emit(ctx, todos_core.remove_completed_items(make_client(ctx), entity_id))


# ──────────────────────────────────────────────────────── lock

@cli.group()
def lock():
    """lock.* entities — lock / unlock / open (for garage-door-style locks)."""


@lock.command("lock")
@click.argument("entity_id")
@click.option("--code", default=None, help="Optional unlock code")
@click.pass_context
def lock_lock(ctx, entity_id, code):
    emit(ctx, service_shortcuts_core.lock_lock(
        make_client(ctx), entity_id, code=code,
    ))


@lock.command("unlock")
@click.argument("entity_id")
@click.option("--code", default=None, help="Optional unlock code")
@click.pass_context
def lock_unlock(ctx, entity_id, code):
    emit(ctx, service_shortcuts_core.lock_unlock(
        make_client(ctx), entity_id, code=code,
    ))


@lock.command("open")
@click.argument("entity_id")
@click.option("--code", default=None)
@click.pass_context
def lock_open(ctx, entity_id, code):
    """Open the lock (used by garage doors and a few smart locks)."""
    emit(ctx, service_shortcuts_core.lock_open(
        make_client(ctx), entity_id, code=code,
    ))


# ──────────────────────────────────────────────────────── alarm

@cli.group()
def alarm():
    """alarm_control_panel.* entities — arm / disarm shortcuts."""


@alarm.command("arm-away")
@click.argument("entity_id")
@click.option("--code", default=None)
@click.pass_context
def alarm_arm_away(ctx, entity_id, code):
    emit(ctx, service_shortcuts_core.alarm_arm_away(
        make_client(ctx), entity_id, code=code,
    ))


@alarm.command("arm-home")
@click.argument("entity_id")
@click.option("--code", default=None)
@click.pass_context
def alarm_arm_home(ctx, entity_id, code):
    emit(ctx, service_shortcuts_core.alarm_arm_home(
        make_client(ctx), entity_id, code=code,
    ))


@alarm.command("arm-night")
@click.argument("entity_id")
@click.option("--code", default=None)
@click.pass_context
def alarm_arm_night(ctx, entity_id, code):
    emit(ctx, service_shortcuts_core.alarm_arm_night(
        make_client(ctx), entity_id, code=code,
    ))


@alarm.command("arm-vacation")
@click.argument("entity_id")
@click.option("--code", default=None)
@click.pass_context
def alarm_arm_vacation(ctx, entity_id, code):
    emit(ctx, service_shortcuts_core.alarm_arm_vacation(
        make_client(ctx), entity_id, code=code,
    ))


@alarm.command("disarm")
@click.argument("entity_id")
@click.option("--code", default=None)
@click.pass_context
def alarm_disarm(ctx, entity_id, code):
    emit(ctx, service_shortcuts_core.alarm_disarm(
        make_client(ctx), entity_id, code=code,
    ))


# ──────────────────────────────────────────────────────── search

@cli.command("search")
@click.argument("item_type",
                type=click.Choice([
                    "automation", "config_entry", "area", "device", "entity",
                    "floor", "group", "label", "person", "scene", "script",
                ]))
@click.argument("item_id")
@click.pass_context
def search(ctx, item_type, item_id):
    """Find everything related to a given entity / device / area / etc.

    Example:
      search entity light.kitchen
      search device 1a2b3c4d5e6f7g
      search area kitchen
    """
    emit(ctx, singletons_core.search_related(
        make_client(ctx), item_type=item_type, item_id=item_id,
    ))


# ──────────────────────────────────────────────────────── entity expose

@entity.group("expose")
def entity_expose():
    """Manage which entities are exposed to voice assistants (Alexa / Google / cloud)."""


@entity_expose.command("list")
@click.option("--assistant", default=None,
              help="Filter to one assistant (e.g. cloud.alexa, cloud.google_assistant)")
@click.pass_context
def entity_expose_list(ctx, assistant):
    """List the expose flags per entity (optionally one assistant)."""
    emit(ctx, expose_entity_core.list_exposed(
        make_client(ctx), assistant=assistant,
    ))


@entity_expose.command("set")
@click.option("--assistant", "assistants", multiple=True, required=True,
              help="Assistant id (repeatable). e.g. cloud.alexa")
@click.option("--entity", "entity_ids", multiple=True, required=True,
              help="Entity id (repeatable)")
@click.option("--expose/--hide", "should_expose", default=True,
              help="Expose (default) or hide the entities")
@click.pass_context
def entity_expose_set(ctx, assistants, entity_ids, should_expose):
    """Expose/hide one or more entities from one or more assistants."""
    emit(ctx, expose_entity_core.expose_entity(
        make_client(ctx),
        assistants=list(assistants),
        entity_ids=list(entity_ids),
        should_expose=should_expose,
    ))


@entity_expose.command("new-default-get")
@click.argument("assistant")
@click.pass_context
def entity_expose_new_get(ctx, assistant):
    """Show whether new entities are auto-exposed to this assistant."""
    emit(ctx, {
        "assistant": assistant,
        "expose_new": expose_entity_core.get_expose_new_entities(
            make_client(ctx), assistant=assistant,
        ),
    })


@entity_expose.command("new-default-set")
@click.argument("assistant")
@click.option("--expose/--no-expose", "expose_new", default=True,
              help="Auto-expose new entities to this assistant (default: yes)")
@click.pass_context
def entity_expose_new_set(ctx, assistant, expose_new):
    emit(ctx, expose_entity_core.set_expose_new_entities(
        make_client(ctx), assistant=assistant, expose_new=expose_new,
    ))


# ──────────────────────────────────────────────────────── camera

@cli.group()
def camera():
    """camera.* entities — stream URLs, capabilities, prefs, WebRTC config."""


@camera.command("capabilities")
@click.argument("entity_id")
@click.pass_context
def camera_capabilities(ctx, entity_id):
    """Get camera capabilities (supported stream types, etc.)."""
    emit(ctx, camera_ws_core.capabilities(make_client(ctx), entity_id=entity_id))


@camera.command("stream")
@click.argument("entity_id")
@click.option("--format", "stream_format", default="hls",
              type=click.Choice(["hls"]),
              help="Stream container format (only 'hls' is supported by HA today)")
@click.pass_context
def camera_stream(ctx, entity_id, stream_format):
    """Request an HLS stream URL for a camera entity."""
    emit(ctx, camera_ws_core.stream(make_client(ctx),
                                    entity_id=entity_id,
                                    format=stream_format))


@camera.command("prefs-get")
@click.argument("entity_id")
@click.pass_context
def camera_prefs_get(ctx, entity_id):
    """Show current stream preferences for a camera entity."""
    emit(ctx, camera_ws_core.get_prefs(make_client(ctx), entity_id=entity_id))


@camera.command("prefs-set")
@click.argument("entity_id")
@click.option("--preload-stream/--no-preload-stream", "preload_stream",
              default=None, help="Preload the stream on frontend load")
@click.option("--orientation", type=int, default=None,
              help="EXIF orientation code (1-8)")
@click.pass_context
def camera_prefs_set(ctx, entity_id, preload_stream, orientation):
    """Update camera stream preferences."""
    if preload_stream is None and orientation is None:
        _abort("provide --preload-stream/--no-preload-stream and/or --orientation")
    emit(ctx, camera_ws_core.update_prefs(
        make_client(ctx), entity_id=entity_id,
        preload_stream=preload_stream, orientation=orientation,
    ))


@camera.command("webrtc-config")
@click.argument("entity_id")
@click.pass_context
def camera_webrtc_config(ctx, entity_id):
    """Get WebRTC client config (ICE servers, etc.) for a camera entity."""
    emit(ctx, camera_ws_core.webrtc_get_client_config(
        make_client(ctx), entity_id=entity_id,
    ))


# ──────────────────────────────────────────────────────── device-automation

@cli.group("device-automation")
def device_automation_grp():
    """List a device's available triggers, conditions and actions.

    These are the dropdown options the HA UI shows in the automation editor —
    surfaced as JSON so agents can build automations programmatically.
    """


@device_automation_grp.command("triggers")
@click.argument("device_id")
@click.pass_context
def device_automation_triggers(ctx, device_id):
    """List trigger options for a device."""
    emit(ctx, device_automation_core.list_triggers(
        make_client(ctx), device_id=device_id,
    ))


@device_automation_grp.command("conditions")
@click.argument("device_id")
@click.pass_context
def device_automation_conditions(ctx, device_id):
    """List condition options for a device."""
    emit(ctx, device_automation_core.list_conditions(
        make_client(ctx), device_id=device_id,
    ))


@device_automation_grp.command("actions")
@click.argument("device_id")
@click.pass_context
def device_automation_actions(ctx, device_id):
    """List action options for a device."""
    emit(ctx, device_automation_core.list_actions(
        make_client(ctx), device_id=device_id,
    ))


@device_automation_grp.command("summary")
@click.argument("device_id")
@click.pass_context
def device_automation_summary(ctx, device_id):
    """One-shot: triggers + conditions + actions for a device."""
    emit(ctx, device_automation_core.summarise_device(
        make_client(ctx), device_id=device_id,
    ))


# ──────────────────────────────────────────────────────── assist (extensions)

@assist.command("agents")
@click.option("--country", default=None, help="ISO country code")
@click.option("--language", default=None, help="Language tag, e.g. en, fr")
@click.pass_context
def assist_agents(ctx, country, language):
    """List available conversation agents (Home Assistant + LLM plugins)."""
    emit(ctx, conversation_advanced_core.list_agents(
        make_client(ctx), country=country, language=language,
    ))


@assist.command("sentences")
@click.argument("language")
@click.pass_context
def assist_sentences(ctx, language):
    """List the built-in sentence templates the default agent matches."""
    emit(ctx, conversation_advanced_core.list_sentences(
        make_client(ctx), language=language,
    ))


@assist.command("debug")
@click.argument("sentence")
@click.option("--language", default="en", help="Language code (default: en)")
@click.pass_context
def assist_debug(ctx, sentence, language):
    """Show how the default agent would match a sentence (intent / slots)."""
    emit(ctx, conversation_advanced_core.debug_agent(
        make_client(ctx), sentence=sentence, language=language,
    ))


@assist.command("satellites")
@click.pass_context
def assist_satellites(ctx):
    """List satellite (voice puck) devices known to the assist pipeline."""
    emit(ctx, conversation_advanced_core.list_satellite_devices(make_client(ctx)))


@assist.command("languages")
@click.pass_context
def assist_languages(ctx):
    """List which languages each pipeline component (STT/TTS/intent) supports."""
    emit(ctx, conversation_advanced_core.list_pipeline_languages(make_client(ctx)))


# ──────────────────────────────────────────────────────── assist-satellite

@cli.group("assist-satellite")
def assist_satellite_grp():
    """assist_satellite.* entities — wake word config + connection test."""


@assist_satellite_grp.command("config")
@click.argument("entity_id")
@click.pass_context
def assist_satellite_config(ctx, entity_id):
    """Show the satellite's current configuration (active wake words, etc.)."""
    emit(ctx, assist_satellite_core.get_configuration(
        make_client(ctx), entity_id=entity_id,
    ))


@assist_satellite_grp.command("wake-words-set")
@click.argument("entity_id")
@click.argument("wake_word_ids", nargs=-1, required=True)
@click.pass_context
def assist_satellite_wake_words(ctx, entity_id, wake_word_ids):
    """Set the active wake word ids for a satellite."""
    emit(ctx, assist_satellite_core.set_wake_words(
        make_client(ctx), entity_id=entity_id,
        wake_word_ids=list(wake_word_ids),
    ))


@assist_satellite_grp.command("test-connection")
@click.argument("entity_id")
@click.pass_context
def assist_satellite_test(ctx, entity_id):
    """Trigger a satellite connection test (round-trip a tone over the pipeline)."""
    emit(ctx, assist_satellite_core.test_connection(
        make_client(ctx), entity_id=entity_id,
    ))


# ──────────────────────────────────────────────────────── mobile-app

@cli.group("mobile-app")
def mobile_app_grp():
    """Home Assistant Companion app integrations."""


@mobile_app_grp.command("confirm-push")
@click.argument("webhook_id")
@click.argument("confirm_id")
@click.pass_context
def mobile_app_confirm_push(ctx, webhook_id, confirm_id):
    """Acknowledge receipt of a push notification (delivery-receipt API)."""
    emit(ctx, mobile_app_core.confirm_push_notification(
        make_client(ctx), webhook_id=webhook_id, confirm_id=confirm_id,
    ))


# ──────────────────────────────────────────────────────── media (browse/resolve)

@cli.group()
def media():
    """Browse and resolve HA media sources (local media, TTS cache, integrations)."""


@media.command("browse")
@click.option("--media-content-id", "media_content_id", default=None,
              help="Drill into a specific media path (omit for root)")
@click.pass_context
def media_browse(ctx, media_content_id):
    """Browse the media library tree (returns children of the given node)."""
    emit(ctx, media_source_core.browse_media(
        make_client(ctx), media_content_id=media_content_id,
    ))


@media.command("resolve")
@click.argument("media_content_id")
@click.pass_context
def media_resolve(ctx, media_content_id):
    """Resolve a media_content_id to a playable URL + mime type."""
    emit(ctx, media_source_core.resolve_media(
        make_client(ctx), media_content_id=media_content_id,
    ))


@media.command("remove")
@click.argument("media_content_id")
@click.confirmation_option(prompt="Delete this local media item?")
@click.pass_context
def media_remove(ctx, media_content_id):
    """Delete a locally-stored media item (only works for media_source/local)."""
    emit(ctx, media_source_core.local_source_remove(
        make_client(ctx), media_content_id=media_content_id,
    ))


# ──────────────────────────────────────────────────────── auth extensions

@auth.command("me")
@click.pass_context
def auth_me(ctx):
    """Show the active user (id, name, is_admin, group_ids)."""
    emit(ctx, auth_tokens_core.current_user(make_client(ctx)))


@auth.command("sign-path")
@click.argument("path")
@click.option("--expires", type=int, default=30,
              help="Seconds until the signed URL expires (default 30)")
@click.pass_context
def auth_sign_path(ctx, path, expires):
    """Sign a /api/... path so it can be fetched without an Authorization header.

    Useful for download URLs (snapshots, camera stills) that can be safely
    passed to other tooling.
    """
    emit(ctx, auth_tokens_core.sign_path(
        make_client(ctx), path=path, expires=expires,
    ))


@auth_tokens.command("list")
@click.pass_context
def auth_tokens_list(ctx):
    """List every refresh token issued for the active user."""
    emit(ctx, auth_tokens_core.list_refresh_tokens(make_client(ctx)))


@auth_tokens.command("delete")
@click.argument("refresh_token_id")
@click.confirmation_option(prompt="Revoke this refresh token?")
@click.pass_context
def auth_tokens_delete(ctx, refresh_token_id):
    """Revoke a specific refresh token by id."""
    emit(ctx, auth_tokens_core.delete_refresh_token(
        make_client(ctx), refresh_token_id=refresh_token_id,
    ))


@auth_tokens.command("delete-all")
@click.option("--delete-current/--keep-current", "delete_current", default=False,
              help="Also revoke the token used by this CLI (will sign you out!)")
@click.option("--token-type", "token_type", default=None,
              type=click.Choice(["normal", "system", "long_lived_access_token"]),
              help="Restrict to one token kind (default: all kinds)")
@click.confirmation_option(prompt="Revoke ALL refresh tokens?")
@click.pass_context
def auth_tokens_delete_all(ctx, delete_current, token_type):
    """Revoke every refresh token (use --delete-current to log this CLI out too)."""
    emit(ctx, auth_tokens_core.delete_all_refresh_tokens(
        make_client(ctx),
        delete_current_token=delete_current,
        token_type=token_type,
    ))


@auth_tokens.command("set-expiry")
@click.argument("refresh_token_id")
@click.option("--expiry/--no-expiry", "enable_expiry", default=True,
              help="Enable expiry (default) or disable it (long-lived)")
@click.pass_context
def auth_tokens_set_expiry(ctx, refresh_token_id, enable_expiry):
    """Toggle expiry on a refresh token."""
    emit(ctx, auth_tokens_core.set_refresh_token_expiry(
        make_client(ctx), refresh_token_id=refresh_token_id,
        enable_expiry=enable_expiry,
    ))


@auth.group("user")
def auth_user():
    """User admin — create / update users, manage credentials, change password."""


@auth_user.command("create")
@click.argument("name")
@click.option("--group", "group_ids", multiple=True,
              help="Group id (e.g. 'system-admin', 'system-users'). Repeatable.")
@click.option("--local-only/--remote-allowed", "local_only", default=None,
              help="Restrict to local-network logins")
@click.pass_context
def auth_user_create(ctx, name, group_ids, local_only):
    """Create a new HA user."""
    emit(ctx, user_admin_core.create_user(
        make_client(ctx), name=name,
        group_ids=list(group_ids) or None,
        local_only=local_only,
    ))


@auth_user.command("update")
@click.argument("user_id")
@click.option("--name", default=None)
@click.option("--group", "group_ids", multiple=True,
              help="Replace group membership (repeatable)")
@click.option("--local-only/--remote-allowed", "local_only", default=None)
@click.option("--active/--inactive", "is_active", default=None)
@click.pass_context
def auth_user_update(ctx, user_id, name, group_ids, local_only, is_active):
    """Update an existing user (any combination of fields)."""
    if (name is None and not group_ids and local_only is None
            and is_active is None):
        _abort("provide at least one of --name/--group/--local-only/--active")
    emit(ctx, user_admin_core.update_user(
        make_client(ctx), user_id=user_id,
        name=name, group_ids=list(group_ids) or None,
        local_only=local_only, is_active=is_active,
    ))


@auth_user.command("credential-create")
@click.argument("user_id")
@click.argument("username")
@click.option("--password", required=True, prompt=True, hide_input=True,
              confirmation_prompt=True)
@click.pass_context
def auth_user_credential_create(ctx, user_id, username, password):
    """Attach a homeassistant-provider login (username + password) to a user."""
    emit(ctx, user_admin_core.create_credential(
        make_client(ctx), user_id=user_id, username=username, password=password,
    ))


@auth_user.command("credential-delete")
@click.argument("username")
@click.confirmation_option(prompt="Delete this credential?")
@click.pass_context
def auth_user_credential_delete(ctx, username):
    """Delete a homeassistant-provider credential by username."""
    emit(ctx, user_admin_core.delete_credential(
        make_client(ctx), username=username,
    ))


@auth_user.command("change-password")
@click.option("--current-password", required=True, prompt=True, hide_input=True)
@click.option("--new-password", required=True, prompt=True, hide_input=True,
              confirmation_prompt=True)
@click.pass_context
def auth_user_change_password(ctx, current_password, new_password):
    """Change the active user's password."""
    emit(ctx, user_admin_core.change_password(
        make_client(ctx),
        current_password=current_password,
        new_password=new_password,
    ))


# ──────────────────────────────────────────────────────── category

@cli.group()
def category():
    """Category registry — cross-cutting tags scoped to a collection.

    Categories are like labels but scoped (per automation / script / todo / ...).
    Most useful for grouping automations by purpose ("alerts", "lighting", ...).
    """


@category.command("list")
@click.argument("scope")
@click.pass_context
def category_list(ctx, scope):
    """List categories in a scope (e.g. 'automation', 'script', 'todo')."""
    emit(ctx, categories_core.list_categories(make_client(ctx), scope=scope))


@category.command("create")
@click.argument("scope")
@click.argument("name")
@click.option("--icon", default=None, help="e.g. mdi:tag")
@click.pass_context
def category_create(ctx, scope, name, icon):
    """Create a new category in a scope."""
    emit(ctx, categories_core.create_category(
        make_client(ctx), scope=scope, name=name, icon=icon,
    ))


@category.command("update")
@click.argument("scope")
@click.argument("category_id")
@click.option("--name", default=None)
@click.option("--icon", default=None)
@click.pass_context
def category_update(ctx, scope, category_id, name, icon):
    """Rename or re-icon an existing category."""
    if name is None and icon is None:
        _abort("provide --name and/or --icon")
    emit(ctx, categories_core.update_category(
        make_client(ctx), scope=scope, category_id=category_id,
        name=name, icon=icon,
    ))


@category.command("delete")
@click.argument("scope")
@click.argument("category_id")
@click.confirmation_option(prompt="Delete this category?")
@click.pass_context
def category_delete(ctx, scope, category_id):
    emit(ctx, categories_core.delete_category(
        make_client(ctx), scope=scope, category_id=category_id,
    ))


@category.command("by-name")
@click.argument("scope")
@click.pass_context
def category_by_name(ctx, scope):
    """Return a {name → record} mapping for the scope (handy for lookups)."""
    emit(ctx, categories_core.categories_by_name(make_client(ctx), scope=scope))


# ──────────────────────────────────────────────────────── logger (WS variants)

@logger.command("info-ws")
@click.pass_context
def logger_info_ws(ctx):
    """Show the WS-side per-component log levels (raw integer levels).

    Distinct from `logger default/set` which use the REST/service path.
    """
    emit(ctx, logger_ws_core.log_info(make_client(ctx)))


@logger.command("level-get")
@click.option("--integration", default=None,
              help="Integration domain (mutually exclusive with --namespace)")
@click.option("--namespace", default=None,
              help="Python module namespace (mutually exclusive with --integration)")
@click.pass_context
def logger_level_get(ctx, integration, namespace):
    """Get the active log level for an integration or module namespace."""
    if not integration and not namespace:
        _abort("provide --integration or --namespace")
    emit(ctx, logger_ws_core.log_level(
        make_client(ctx), integration=integration, namespace=namespace,
    ))


@logger.command("level-set")
@click.argument("integration")
@click.argument("level",
                type=click.Choice(["debug", "info", "warning", "error",
                                   "critical", "fatal", "notset"],
                                  case_sensitive=False))
@click.option("--persistence", default="none",
              type=click.Choice(["none", "once", "always"]),
              help="Whether the change survives a restart")
@click.pass_context
def logger_level_set(ctx, integration, level, persistence):
    """Set an integration's log level via WS (with optional persistence)."""
    emit(ctx, logger_ws_core.integration_log_level(
        make_client(ctx), integration=integration, level=level.lower(),
        persistence=persistence,
    ))


# ──────────────────────────────────────────────────────── system extensions

@system.group("manifest")
def system_manifest():
    """Integration manifests (the metadata files HA uses to load integrations)."""


@system_manifest.command("list")
@click.pass_context
def system_manifest_list(ctx):
    """List manifests for every loaded integration."""
    emit(ctx, system_ops_core.list_manifests(make_client(ctx)))


@system_manifest.command("get")
@click.argument("integration")
@click.pass_context
def system_manifest_get(ctx, integration):
    """Show the manifest for one integration (version, requirements, …)."""
    emit(ctx, system_ops_core.get_manifest(
        make_client(ctx), integration=integration,
    ))


@system.group("analytics")
def system_analytics():
    """HA telemetry/analytics — opt-in tracking preferences."""


@system_analytics.command("get")
@click.pass_context
def system_analytics_get(ctx):
    """Show current analytics preferences and onboarded status."""
    emit(ctx, system_ops_core.get_analytics(make_client(ctx)))


@system_analytics.command("set")
@click.argument("preferences_json")
@click.pass_context
def system_analytics_set(ctx, preferences_json):
    """Update analytics preferences from a JSON object (see HA docs for keys)."""
    try:
        prefs = json.loads(preferences_json)
    except json.JSONDecodeError as exc:
        _abort(f"preferences must be valid JSON: {exc}")
    emit(ctx, system_ops_core.set_analytics_preferences(
        make_client(ctx), preferences=prefs,
    ))


@system.group("app-credentials")
def system_app_credentials():
    """OAuth application credentials (Google Calendar, Spotify, …)."""


@system_app_credentials.command("config")
@click.pass_context
def system_app_credentials_config(ctx):
    """List integration domains that support OAuth application credentials."""
    emit(ctx, system_ops_core.application_credentials_config(make_client(ctx)))


@system_app_credentials.command("entry")
@click.argument("config_entry_id")
@click.pass_context
def system_app_credentials_entry(ctx, config_entry_id):
    """Show the OAuth credentials wired to a specific config entry."""
    emit(ctx, system_ops_core.application_credentials_config_entry(
        make_client(ctx), config_entry_id=config_entry_id,
    ))


@system.group("issue")
def system_issue():
    """The Repairs issue feed (per-issue data + ignore toggle)."""


@system_issue.command("get-data")
@click.argument("domain")
@click.argument("issue_id")
@click.pass_context
def system_issue_get_data(ctx, domain, issue_id):
    """Fetch the structured issue_data for a Repairs issue."""
    emit(ctx, system_ops_core.get_issue_data(
        make_client(ctx), domain=domain, issue_id=issue_id,
    ))


@system_issue.command("ignore")
@click.argument("domain")
@click.argument("issue_id")
@click.option("--unignore", "ignore_flag", flag_value=False, default=True,
              help="Un-ignore the issue (default action is to ignore)")
@click.pass_context
def system_issue_ignore(ctx, domain, issue_id, ignore_flag):
    emit(ctx, system_ops_core.ignore_issue(
        make_client(ctx), domain=domain, issue_id=issue_id,
        ignore=ignore_flag,
    ))


@system.command("usb-scan")
@click.pass_context
def system_usb_scan(ctx):
    """Trigger a USB hardware rescan (picks up newly-plugged dongles)."""
    emit(ctx, singletons_core.usb_scan(make_client(ctx)))


@system.command("zha-permit-join")
@click.option("--duration", type=int, default=60,
              help="Permit window in seconds (1-254, default 60)")
@click.option("--ieee", default=None,
              help="Restrict permit to a specific device IEEE address")
@click.pass_context
def system_zha_permit_join(ctx, duration, ieee):
    """Open the ZHA Zigbee network for new device joins."""
    emit(ctx, singletons_core.zha_devices_permit(
        make_client(ctx), duration=duration, ieee=ieee,
    ))


@system.command("hardware-info")
@click.pass_context
def system_hardware_info(ctx):
    """Show hardware info (model, hostname, OS) via the hardware integration."""
    emit(ctx, hardware_info_core.info(make_client(ctx)))


@system.command("board-info")
@click.pass_context
def system_board_info(ctx):
    """Show known board info entries."""
    emit(ctx, hardware_info_core.board_info(make_client(ctx)))


@system.command("cpu-info")
@click.pass_context
def system_cpu_info(ctx):
    """Show CPU info reported by HA's hardware integration."""
    emit(ctx, hardware_info_core.cpu_info(make_client(ctx)))


@system.group("log")
def system_log_grp():
    """system_log.* — runtime error log management (WS-backed)."""


@system_log_grp.command("errors")
@click.pass_context
def system_log_errors(ctx):
    """List the structured errors HA has logged at WARNING+ level."""
    emit(ctx, system_log_core.list_errors(make_client(ctx)))


@system_log_grp.command("clear")
@click.confirmation_option(prompt="Clear the system error log?")
@click.pass_context
def system_log_clear(ctx):
    """Wipe HA's runtime error log."""
    emit(ctx, system_log_core.clear(make_client(ctx)))


@system_log_grp.command("write")
@click.argument("message")
@click.option("--level", default="error",
              type=click.Choice(["debug", "info", "warning", "error",
                                 "critical"], case_sensitive=False))
@click.option("--logger-name", default=None,
              help="Synthetic logger name (defaults to homeassistant.components)")
@click.pass_context
def system_log_write(ctx, message, level, logger_name):
    """Inject a synthetic log entry (useful for testing log-driven automations)."""
    emit(ctx, system_log_core.write(
        make_client(ctx),
        message=message,
        level=level.lower(),
        logger=logger_name,
    ))


# ──────────────────────────────────────────────────────── light

@cli.group()
def light():
    """light.* entities — brightness, color, kelvin, effect shortcuts."""


@light.command("on")
@click.argument("entity_id")
@click.option("--brightness", type=int, default=None, help="0..255")
@click.option("--brightness-pct", "brightness_pct", type=float, default=None,
              help="0..100")
@click.option("--kelvin", type=int, default=None)
@click.option("--color-temp-kelvin", "color_temp_kelvin", type=int,
              default=None)
@click.option("--rgb", "rgb_color", default=None,
              help="Comma-separated r,g,b (e.g. 255,128,0)")
@click.option("--rgbw", "rgbw_color", default=None,
              help="Comma-separated r,g,b,w")
@click.option("--rgbww", "rgbww_color", default=None,
              help="Comma-separated r,g,b,cw,ww")
@click.option("--xy", "xy_color", default=None,
              help="Comma-separated x,y")
@click.option("--hs", "hs_color", default=None,
              help="Comma-separated hue,saturation")
@click.option("--color-name", "color_name", default=None)
@click.option("--effect", default=None)
@click.option("--flash", default=None,
              type=click.Choice(["short", "long"], case_sensitive=False))
@click.option("--transition", type=float, default=None)
@click.option("--profile", default=None)
@click.option("--white", type=int, default=None,
              help="White-channel value 0..255")
@click.pass_context
def light_on(ctx, entity_id, brightness, brightness_pct, kelvin,
             color_temp_kelvin, rgb_color, rgbw_color, rgbww_color,
             xy_color, hs_color, color_name, effect, flash,
             transition, profile, white):
    """Turn a light on (with optional brightness/color/kelvin/effect)."""
    def _parse_list(raw, cast):
        if raw is None:
            return None
        return [cast(p.strip()) for p in raw.split(",")]

    emit(ctx, entity_control_core.light_turn_on(
        make_client(ctx), entity_id,
        brightness=brightness,
        brightness_pct=brightness_pct,
        kelvin=kelvin,
        color_temp_kelvin=color_temp_kelvin,
        rgb_color=_parse_list(rgb_color, int),
        rgbw_color=_parse_list(rgbw_color, int),
        rgbww_color=_parse_list(rgbww_color, int),
        xy_color=_parse_list(xy_color, float),
        hs_color=_parse_list(hs_color, float),
        color_name=color_name,
        effect=effect,
        flash=flash.lower() if flash else None,
        transition=transition,
        profile=profile,
        white=white,
    ))


@light.command("off")
@click.argument("entity_id")
@click.option("--transition", type=float, default=None)
@click.option("--flash", default=None,
              type=click.Choice(["short", "long"], case_sensitive=False))
@click.pass_context
def light_off(ctx, entity_id, transition, flash):
    """Turn a light off."""
    emit(ctx, entity_control_core.light_turn_off(
        make_client(ctx), entity_id,
        transition=transition,
        flash=flash.lower() if flash else None,
    ))


@light.command("toggle")
@click.argument("entity_id")
@click.option("--brightness", type=int, default=None)
@click.option("--brightness-pct", "brightness_pct", type=float, default=None)
@click.option("--kelvin", type=int, default=None)
@click.option("--rgb", "rgb_color", default=None)
@click.option("--transition", type=float, default=None)
@click.pass_context
def light_toggle_cmd(ctx, entity_id, brightness, brightness_pct, kelvin,
                     rgb_color, transition):
    """Toggle a light."""
    rgb_parsed = ([int(p.strip()) for p in rgb_color.split(",")]
                  if rgb_color else None)
    emit(ctx, entity_control_core.light_toggle(
        make_client(ctx), entity_id,
        brightness=brightness,
        brightness_pct=brightness_pct,
        kelvin=kelvin,
        rgb_color=rgb_parsed,
        transition=transition,
    ))


# ──────────────────────────────────────────────────────── media-player

@cli.group("media-player")
def media_player_grp():
    """media_player.* entities — playback, volume, source, play-media."""


@media_player_grp.command("play")
@click.argument("entity_id")
@click.pass_context
def mp_play(ctx, entity_id):
    emit(ctx, entity_control_core.media_player_play(make_client(ctx), entity_id))


@media_player_grp.command("pause")
@click.argument("entity_id")
@click.pass_context
def mp_pause(ctx, entity_id):
    emit(ctx, entity_control_core.media_player_pause(make_client(ctx), entity_id))


@media_player_grp.command("stop")
@click.argument("entity_id")
@click.pass_context
def mp_stop(ctx, entity_id):
    emit(ctx, entity_control_core.media_player_stop(make_client(ctx), entity_id))


@media_player_grp.command("play-pause")
@click.argument("entity_id")
@click.pass_context
def mp_play_pause(ctx, entity_id):
    emit(ctx, entity_control_core.media_player_play_pause(make_client(ctx),
                                                          entity_id))


@media_player_grp.command("next")
@click.argument("entity_id")
@click.pass_context
def mp_next(ctx, entity_id):
    emit(ctx, entity_control_core.media_player_next(make_client(ctx), entity_id))


@media_player_grp.command("previous")
@click.argument("entity_id")
@click.pass_context
def mp_previous(ctx, entity_id):
    emit(ctx, entity_control_core.media_player_previous(make_client(ctx),
                                                        entity_id))


@media_player_grp.command("volume-set")
@click.argument("entity_id")
@click.argument("volume", type=float)
@click.pass_context
def mp_volume_set(ctx, entity_id, volume):
    """Set absolute volume (0.0..1.0)."""
    emit(ctx, entity_control_core.media_player_volume_set(
        make_client(ctx), entity_id, volume=volume,
    ))


@media_player_grp.command("volume-up")
@click.argument("entity_id")
@click.pass_context
def mp_volume_up(ctx, entity_id):
    emit(ctx, entity_control_core.media_player_volume_up(make_client(ctx),
                                                         entity_id))


@media_player_grp.command("volume-down")
@click.argument("entity_id")
@click.pass_context
def mp_volume_down(ctx, entity_id):
    emit(ctx, entity_control_core.media_player_volume_down(make_client(ctx),
                                                           entity_id))


@media_player_grp.command("mute")
@click.argument("entity_id")
@click.option("--off", "off", is_flag=True, default=False,
              help="Unmute (default action: mute)")
@click.pass_context
def mp_mute(ctx, entity_id, off):
    emit(ctx, entity_control_core.media_player_mute(
        make_client(ctx), entity_id, mute=not off,
    ))


@media_player_grp.command("select-source")
@click.argument("entity_id")
@click.argument("source")
@click.pass_context
def mp_select_source(ctx, entity_id, source):
    emit(ctx, entity_control_core.media_player_select_source(
        make_client(ctx), entity_id, source=source,
    ))


@media_player_grp.command("select-sound-mode")
@click.argument("entity_id")
@click.argument("sound_mode")
@click.pass_context
def mp_select_sound_mode(ctx, entity_id, sound_mode):
    emit(ctx, entity_control_core.media_player_select_sound_mode(
        make_client(ctx), entity_id, sound_mode=sound_mode,
    ))


@media_player_grp.command("play-media")
@click.argument("entity_id")
@click.argument("media_content_id")
@click.argument("media_content_type")
@click.option("--enqueue", default=None,
              help="play|add|next|replace, or true/false")
@click.option("--announce/--no-announce", default=None,
              help="Use the announce surface where supported")
@click.option("--extra", default=None, help="JSON-encoded extra payload")
@click.pass_context
def mp_play_media(ctx, entity_id, media_content_id, media_content_type,
                  enqueue, announce, extra):
    parsed_extra = json.loads(extra) if extra else None
    emit(ctx, entity_control_core.media_player_play_media(
        make_client(ctx), entity_id,
        media_content_id=media_content_id,
        media_content_type=media_content_type,
        enqueue=enqueue,
        announce=announce,
        extra=parsed_extra,
    ))


@media_player_grp.command("shuffle")
@click.argument("entity_id")
@click.option("--off", "off", is_flag=True, default=False,
              help="Turn shuffle off (default: on)")
@click.pass_context
def mp_shuffle(ctx, entity_id, off):
    emit(ctx, entity_control_core.media_player_shuffle(
        make_client(ctx), entity_id, shuffle=not off,
    ))


@media_player_grp.command("repeat")
@click.argument("entity_id")
@click.argument("mode", type=click.Choice(["off", "all", "one"],
                                          case_sensitive=False))
@click.pass_context
def mp_repeat(ctx, entity_id, mode):
    emit(ctx, entity_control_core.media_player_repeat(
        make_client(ctx), entity_id, repeat=mode.lower(),
    ))


@media_player_grp.command("clear-playlist")
@click.argument("entity_id")
@click.pass_context
def mp_clear_playlist(ctx, entity_id):
    emit(ctx, entity_control_core.media_player_clear_playlist(
        make_client(ctx), entity_id,
    ))


@media_player_grp.command("turn-on")
@click.argument("entity_id")
@click.pass_context
def mp_turn_on(ctx, entity_id):
    emit(ctx, entity_control_core.media_player_turn_on(make_client(ctx),
                                                       entity_id))


@media_player_grp.command("turn-off")
@click.argument("entity_id")
@click.pass_context
def mp_turn_off(ctx, entity_id):
    emit(ctx, entity_control_core.media_player_turn_off(make_client(ctx),
                                                        entity_id))


@media_player_grp.command("join")
@click.argument("entity_id")
@click.option("--member", "members", multiple=True, required=True,
              help="Group member entity_id (repeatable)")
@click.pass_context
def mp_join(ctx, entity_id, members):
    emit(ctx, entity_control_core.media_player_join(
        make_client(ctx), entity_id, group_members=list(members),
    ))


@media_player_grp.command("unjoin")
@click.argument("entity_id")
@click.pass_context
def mp_unjoin(ctx, entity_id):
    emit(ctx, entity_control_core.media_player_unjoin(make_client(ctx),
                                                      entity_id))


# ──────────────────────────────────────────────────────── climate

@cli.group()
def climate():
    """climate.* entities — temperature, hvac mode, fan/preset/swing mode."""


@climate.command("set-temperature")
@click.argument("entity_id")
@click.option("--temperature", "-t", type=float, default=None)
@click.option("--high", "target_temp_high", type=float, default=None)
@click.option("--low", "target_temp_low", type=float, default=None)
@click.option("--hvac-mode", "hvac_mode", default=None,
              help="Optional hvac_mode to set atomically")
@click.pass_context
def climate_set_temp(ctx, entity_id, temperature, target_temp_high,
                     target_temp_low, hvac_mode):
    emit(ctx, entity_control_core.climate_set_temperature(
        make_client(ctx), entity_id,
        temperature=temperature,
        target_temp_high=target_temp_high,
        target_temp_low=target_temp_low,
        hvac_mode=hvac_mode,
    ))


@climate.command("set-hvac-mode")
@click.argument("entity_id")
@click.argument("hvac_mode")
@click.pass_context
def climate_set_hvac(ctx, entity_id, hvac_mode):
    """Common modes: off, auto, heat, cool, heat_cool, dry, fan_only."""
    emit(ctx, entity_control_core.climate_set_hvac_mode(
        make_client(ctx), entity_id, hvac_mode=hvac_mode,
    ))


@climate.command("set-fan-mode")
@click.argument("entity_id")
@click.argument("fan_mode")
@click.pass_context
def climate_set_fan(ctx, entity_id, fan_mode):
    emit(ctx, entity_control_core.climate_set_fan_mode(
        make_client(ctx), entity_id, fan_mode=fan_mode,
    ))


@climate.command("set-preset")
@click.argument("entity_id")
@click.argument("preset_mode")
@click.pass_context
def climate_set_preset(ctx, entity_id, preset_mode):
    emit(ctx, entity_control_core.climate_set_preset_mode(
        make_client(ctx), entity_id, preset_mode=preset_mode,
    ))


@climate.command("set-humidity")
@click.argument("entity_id")
@click.argument("humidity", type=int)
@click.pass_context
def climate_set_hum(ctx, entity_id, humidity):
    emit(ctx, entity_control_core.climate_set_humidity(
        make_client(ctx), entity_id, humidity=humidity,
    ))


@climate.command("set-swing")
@click.argument("entity_id")
@click.argument("swing_mode")
@click.pass_context
def climate_set_swing(ctx, entity_id, swing_mode):
    emit(ctx, entity_control_core.climate_set_swing_mode(
        make_client(ctx), entity_id, swing_mode=swing_mode,
    ))


@climate.command("turn-on")
@click.argument("entity_id")
@click.pass_context
def climate_on(ctx, entity_id):
    emit(ctx, entity_control_core.climate_turn_on(make_client(ctx), entity_id))


@climate.command("turn-off")
@click.argument("entity_id")
@click.pass_context
def climate_off(ctx, entity_id):
    emit(ctx, entity_control_core.climate_turn_off(make_client(ctx), entity_id))


# ──────────────────────────────────────────────────────── cover

@cli.group()
def cover():
    """cover.* entities — open / close / stop / set-position / set-tilt."""


@cover.command("open")
@click.argument("entity_id")
@click.pass_context
def cover_open_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.cover_open(make_client(ctx), entity_id))


@cover.command("close")
@click.argument("entity_id")
@click.pass_context
def cover_close_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.cover_close(make_client(ctx), entity_id))


@cover.command("stop")
@click.argument("entity_id")
@click.pass_context
def cover_stop_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.cover_stop(make_client(ctx), entity_id))


@cover.command("toggle")
@click.argument("entity_id")
@click.pass_context
def cover_toggle_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.cover_toggle(make_client(ctx), entity_id))


@cover.command("set-position")
@click.argument("entity_id")
@click.argument("position", type=int)
@click.pass_context
def cover_set_pos(ctx, entity_id, position):
    """Position 0 (closed) .. 100 (open)."""
    emit(ctx, entity_control_core.cover_set_position(
        make_client(ctx), entity_id, position=position,
    ))


@cover.command("set-tilt")
@click.argument("entity_id")
@click.argument("tilt_position", type=int)
@click.pass_context
def cover_set_tilt_cmd(ctx, entity_id, tilt_position):
    emit(ctx, entity_control_core.cover_set_tilt(
        make_client(ctx), entity_id, tilt_position=tilt_position,
    ))


@cover.command("open-tilt")
@click.argument("entity_id")
@click.pass_context
def cover_open_tilt_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.cover_open_tilt(make_client(ctx), entity_id))


@cover.command("close-tilt")
@click.argument("entity_id")
@click.pass_context
def cover_close_tilt_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.cover_close_tilt(make_client(ctx), entity_id))


@cover.command("stop-tilt")
@click.argument("entity_id")
@click.pass_context
def cover_stop_tilt_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.cover_stop_tilt(make_client(ctx), entity_id))


# ──────────────────────────────────────────────────────── fan

@cli.group()
def fan():
    """fan.* entities — percentage / preset / direction / oscillate."""


@fan.command("turn-on")
@click.argument("entity_id")
@click.option("--percentage", type=int, default=None)
@click.option("--preset", "preset_mode", default=None)
@click.pass_context
def fan_on_cmd(ctx, entity_id, percentage, preset_mode):
    emit(ctx, entity_control_core.fan_turn_on(
        make_client(ctx), entity_id,
        percentage=percentage,
        preset_mode=preset_mode,
    ))


@fan.command("turn-off")
@click.argument("entity_id")
@click.pass_context
def fan_off_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.fan_turn_off(make_client(ctx), entity_id))


@fan.command("toggle")
@click.argument("entity_id")
@click.pass_context
def fan_toggle_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.fan_toggle(make_client(ctx), entity_id))


@fan.command("set-percentage")
@click.argument("entity_id")
@click.argument("percentage", type=int)
@click.pass_context
def fan_set_pct(ctx, entity_id, percentage):
    emit(ctx, entity_control_core.fan_set_percentage(
        make_client(ctx), entity_id, percentage=percentage,
    ))


@fan.command("set-preset")
@click.argument("entity_id")
@click.argument("preset_mode")
@click.pass_context
def fan_set_preset_cmd(ctx, entity_id, preset_mode):
    emit(ctx, entity_control_core.fan_set_preset(
        make_client(ctx), entity_id, preset_mode=preset_mode,
    ))


@fan.command("set-direction")
@click.argument("entity_id")
@click.argument("direction",
                type=click.Choice(["forward", "reverse"], case_sensitive=False))
@click.pass_context
def fan_set_dir(ctx, entity_id, direction):
    emit(ctx, entity_control_core.fan_set_direction(
        make_client(ctx), entity_id, direction=direction.lower(),
    ))


@fan.command("oscillate")
@click.argument("entity_id")
@click.option("--off", "off", is_flag=True, default=False,
              help="Stop oscillation (default: start)")
@click.pass_context
def fan_osc(ctx, entity_id, off):
    emit(ctx, entity_control_core.fan_oscillate(
        make_client(ctx), entity_id, oscillating=not off,
    ))


@fan.command("increase")
@click.argument("entity_id")
@click.option("--step", "percentage_step", type=int, default=None)
@click.pass_context
def fan_inc(ctx, entity_id, percentage_step):
    emit(ctx, entity_control_core.fan_increase(
        make_client(ctx), entity_id, percentage_step=percentage_step,
    ))


@fan.command("decrease")
@click.argument("entity_id")
@click.option("--step", "percentage_step", type=int, default=None)
@click.pass_context
def fan_dec(ctx, entity_id, percentage_step):
    emit(ctx, entity_control_core.fan_decrease(
        make_client(ctx), entity_id, percentage_step=percentage_step,
    ))


# ──────────────────────────────────────────────────────── vacuum

@cli.group()
def vacuum():
    """vacuum.* entities — start / dock / locate / clean_spot / fan_speed."""


@vacuum.command("start")
@click.argument("entity_id")
@click.pass_context
def vacuum_start_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.vacuum_start(make_client(ctx), entity_id))


@vacuum.command("stop")
@click.argument("entity_id")
@click.pass_context
def vacuum_stop_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.vacuum_stop(make_client(ctx), entity_id))


@vacuum.command("pause")
@click.argument("entity_id")
@click.pass_context
def vacuum_pause_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.vacuum_pause(make_client(ctx), entity_id))


@vacuum.command("return-to-base")
@click.argument("entity_id")
@click.pass_context
def vacuum_return_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.vacuum_return_to_base(make_client(ctx),
                                                       entity_id))


@vacuum.command("locate")
@click.argument("entity_id")
@click.pass_context
def vacuum_locate_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.vacuum_locate(make_client(ctx), entity_id))


@vacuum.command("clean-spot")
@click.argument("entity_id")
@click.pass_context
def vacuum_clean_spot_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.vacuum_clean_spot(make_client(ctx),
                                                    entity_id))


@vacuum.command("set-fan-speed")
@click.argument("entity_id")
@click.argument("fan_speed")
@click.pass_context
def vacuum_fan_speed_cmd(ctx, entity_id, fan_speed):
    emit(ctx, entity_control_core.vacuum_set_fan_speed(
        make_client(ctx), entity_id, fan_speed=fan_speed,
    ))


@vacuum.command("send-command")
@click.argument("entity_id")
@click.argument("command")
@click.option("--params", default=None,
              help="JSON-encoded params payload")
@click.pass_context
def vacuum_send_cmd(ctx, entity_id, command, params):
    parsed = json.loads(params) if params else None
    emit(ctx, entity_control_core.vacuum_send_command(
        make_client(ctx), entity_id, command=command, params=parsed,
    ))


# ──────────────────────────────────────────────────────── humidifier

@cli.group()
def humidifier():
    """humidifier.* entities — on/off, set humidity / mode."""


@humidifier.command("turn-on")
@click.argument("entity_id")
@click.pass_context
def humidifier_on(ctx, entity_id):
    emit(ctx, entity_control_core.humidifier_turn_on(make_client(ctx),
                                                     entity_id))


@humidifier.command("turn-off")
@click.argument("entity_id")
@click.pass_context
def humidifier_off(ctx, entity_id):
    emit(ctx, entity_control_core.humidifier_turn_off(make_client(ctx),
                                                      entity_id))


@humidifier.command("toggle")
@click.argument("entity_id")
@click.pass_context
def humidifier_toggle_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.humidifier_toggle(make_client(ctx),
                                                    entity_id))


@humidifier.command("set-humidity")
@click.argument("entity_id")
@click.argument("humidity", type=int)
@click.pass_context
def humidifier_set_hum(ctx, entity_id, humidity):
    emit(ctx, entity_control_core.humidifier_set_humidity(
        make_client(ctx), entity_id, humidity=humidity,
    ))


@humidifier.command("set-mode")
@click.argument("entity_id")
@click.argument("mode")
@click.pass_context
def humidifier_set_mode_cmd(ctx, entity_id, mode):
    emit(ctx, entity_control_core.humidifier_set_mode(
        make_client(ctx), entity_id, mode=mode,
    ))


# ──────────────────────────────────────────────────────── water-heater

@cli.group("water-heater")
def water_heater_grp():
    """water_heater.* entities — on/off, set temperature / op mode / away."""


@water_heater_grp.command("turn-on")
@click.argument("entity_id")
@click.pass_context
def wh_on(ctx, entity_id):
    emit(ctx, entity_control_core.water_heater_turn_on(make_client(ctx),
                                                       entity_id))


@water_heater_grp.command("turn-off")
@click.argument("entity_id")
@click.pass_context
def wh_off(ctx, entity_id):
    emit(ctx, entity_control_core.water_heater_turn_off(make_client(ctx),
                                                        entity_id))


@water_heater_grp.command("set-temperature")
@click.argument("entity_id")
@click.argument("temperature", type=float)
@click.pass_context
def wh_set_temp(ctx, entity_id, temperature):
    emit(ctx, entity_control_core.water_heater_set_temperature(
        make_client(ctx), entity_id, temperature=temperature,
    ))


@water_heater_grp.command("set-operation-mode")
@click.argument("entity_id")
@click.argument("operation_mode")
@click.pass_context
def wh_set_op_mode(ctx, entity_id, operation_mode):
    emit(ctx, entity_control_core.water_heater_set_operation_mode(
        make_client(ctx), entity_id, operation_mode=operation_mode,
    ))


@water_heater_grp.command("set-away-mode")
@click.argument("entity_id")
@click.option("--off", "off", is_flag=True, default=False,
              help="Turn away mode off (default: on)")
@click.pass_context
def wh_set_away(ctx, entity_id, off):
    emit(ctx, entity_control_core.water_heater_set_away_mode(
        make_client(ctx), entity_id, away_mode=not off,
    ))


# ──────────────────────────────────────────────────────── valve

@cli.group()
def valve():
    """valve.* entities — open / close / stop / set-position / toggle."""


@valve.command("open")
@click.argument("entity_id")
@click.pass_context
def valve_open_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.valve_open(make_client(ctx), entity_id))


@valve.command("close")
@click.argument("entity_id")
@click.pass_context
def valve_close_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.valve_close(make_client(ctx), entity_id))


@valve.command("stop")
@click.argument("entity_id")
@click.pass_context
def valve_stop_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.valve_stop(make_client(ctx), entity_id))


@valve.command("toggle")
@click.argument("entity_id")
@click.pass_context
def valve_toggle_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.valve_toggle(make_client(ctx), entity_id))


@valve.command("set-position")
@click.argument("entity_id")
@click.argument("position", type=int)
@click.pass_context
def valve_set_pos(ctx, entity_id, position):
    emit(ctx, entity_control_core.valve_set_position(
        make_client(ctx), entity_id, position=position,
    ))


# ──────────────────────────────────────────────────────── lawn-mower

@cli.group("lawn-mower")
def lawn_mower_grp():
    """lawn_mower.* entities — start-mowing / pause / dock."""


@lawn_mower_grp.command("start")
@click.argument("entity_id")
@click.pass_context
def lm_start(ctx, entity_id):
    emit(ctx, entity_control_core.lawn_mower_start(make_client(ctx), entity_id))


@lawn_mower_grp.command("pause")
@click.argument("entity_id")
@click.pass_context
def lm_pause(ctx, entity_id):
    emit(ctx, entity_control_core.lawn_mower_pause(make_client(ctx), entity_id))


@lawn_mower_grp.command("dock")
@click.argument("entity_id")
@click.pass_context
def lm_dock(ctx, entity_id):
    emit(ctx, entity_control_core.lawn_mower_dock(make_client(ctx), entity_id))


# ──────────────────────────────────────────────────────── siren

@cli.group()
def siren():
    """siren.* entities — on (duration/tone/volume) / off / toggle."""


@siren.command("on")
@click.argument("entity_id")
@click.option("--duration", type=int, default=None, help="Seconds")
@click.option("--tone", default=None)
@click.option("--volume", "volume_level", type=float, default=None,
              help="0.0..1.0")
@click.pass_context
def siren_on_cmd(ctx, entity_id, duration, tone, volume_level):
    emit(ctx, entity_control_core.siren_turn_on(
        make_client(ctx), entity_id,
        duration=duration, tone=tone, volume_level=volume_level,
    ))


@siren.command("off")
@click.argument("entity_id")
@click.pass_context
def siren_off_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.siren_turn_off(make_client(ctx), entity_id))


@siren.command("toggle")
@click.argument("entity_id")
@click.pass_context
def siren_toggle_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.siren_toggle(make_client(ctx), entity_id))


# ──────────────────────────────────────────────────────── remote

@cli.group()
def remote():
    """remote.* entities — send / learn / delete IR-style commands."""


@remote.command("turn-on")
@click.argument("entity_id")
@click.option("--activity", default=None,
              help="Harmony-style activity to switch to")
@click.pass_context
def remote_on(ctx, entity_id, activity):
    emit(ctx, entity_control_core.remote_turn_on(
        make_client(ctx), entity_id, activity=activity,
    ))


@remote.command("turn-off")
@click.argument("entity_id")
@click.pass_context
def remote_off(ctx, entity_id):
    emit(ctx, entity_control_core.remote_turn_off(make_client(ctx), entity_id))


@remote.command("toggle")
@click.argument("entity_id")
@click.pass_context
def remote_toggle_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.remote_toggle(make_client(ctx), entity_id))


@remote.command("send-command")
@click.argument("entity_id")
@click.option("--command", "-c", "commands", multiple=True, required=True,
              help="Command name (repeatable; sends as a list)")
@click.option("--device", default=None)
@click.option("--num-repeats", "num_repeats", type=int, default=None)
@click.option("--delay-secs", "delay_secs", type=float, default=None)
@click.option("--hold-secs", "hold_secs", type=float, default=None)
@click.pass_context
def remote_send_cmd(ctx, entity_id, commands, device, num_repeats,
                    delay_secs, hold_secs):
    cmd: str | list[str] = list(commands) if len(commands) > 1 else commands[0]
    emit(ctx, entity_control_core.remote_send_command(
        make_client(ctx), entity_id,
        command=cmd, device=device,
        num_repeats=num_repeats, delay_secs=delay_secs,
        hold_secs=hold_secs,
    ))


@remote.command("learn-command")
@click.argument("entity_id")
@click.option("--command", "-c", "commands", multiple=True,
              help="Command name (repeatable; learns as a list)")
@click.option("--device", default=None)
@click.option("--command-type", "command_type", default=None,
              help="ir|rf|... (backend-specific)")
@click.option("--alternative/--no-alternative", default=None)
@click.option("--timeout", type=float, default=None)
@click.pass_context
def remote_learn_cmd(ctx, entity_id, commands, device, command_type,
                     alternative, timeout):
    cmd: str | list[str] | None = None
    if commands:
        cmd = list(commands) if len(commands) > 1 else commands[0]
    emit(ctx, entity_control_core.remote_learn_command(
        make_client(ctx), entity_id,
        command=cmd, device=device, command_type=command_type,
        alternative=alternative, timeout=timeout,
    ))


@remote.command("delete-command")
@click.argument("entity_id")
@click.option("--command", "-c", "commands", multiple=True, required=True,
              help="Command name (repeatable; deletes as a list)")
@click.option("--device", default=None)
@click.pass_context
def remote_delete_cmd(ctx, entity_id, commands, device):
    cmd: str | list[str] = list(commands) if len(commands) > 1 else commands[0]
    emit(ctx, entity_control_core.remote_delete_command(
        make_client(ctx), entity_id, command=cmd, device=device,
    ))


# ──────────────────────────────────────────────────────── number

@cli.group()
def number():
    """number.* entities — set numeric value."""


@number.command("set")
@click.argument("entity_id")
@click.argument("value", type=float)
@click.pass_context
def number_set(ctx, entity_id, value):
    emit(ctx, entity_control_core.number_set_value(
        make_client(ctx), entity_id, value=value,
    ))


# ──────────────────────────────────────────────────────── select

@cli.group()
def select():
    """select.* entities — pick an option / next / previous / first / last."""


@select.command("set")
@click.argument("entity_id")
@click.argument("option")
@click.pass_context
def select_set(ctx, entity_id, option):
    """Alias for select_option."""
    emit(ctx, entity_control_core.select_select_option(
        make_client(ctx), entity_id, option=option,
    ))


@select.command("next")
@click.argument("entity_id")
@click.option("--cycle/--no-cycle", default=None)
@click.pass_context
def select_next_cmd(ctx, entity_id, cycle):
    emit(ctx, entity_control_core.select_next(
        make_client(ctx), entity_id, cycle=cycle,
    ))


@select.command("previous")
@click.argument("entity_id")
@click.option("--cycle/--no-cycle", default=None)
@click.pass_context
def select_prev_cmd(ctx, entity_id, cycle):
    emit(ctx, entity_control_core.select_previous(
        make_client(ctx), entity_id, cycle=cycle,
    ))


@select.command("first")
@click.argument("entity_id")
@click.pass_context
def select_first_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.select_first(make_client(ctx), entity_id))


@select.command("last")
@click.argument("entity_id")
@click.pass_context
def select_last_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.select_last(make_client(ctx), entity_id))


# ──────────────────────────────────────────────────────── button

@cli.group()
def button():
    """button.* entities — press."""


@button.command("press")
@click.argument("entity_id")
@click.pass_context
def button_press_cmd(ctx, entity_id):
    emit(ctx, entity_control_core.button_press(make_client(ctx), entity_id))


# ──────────────────────────────────────────────────────── text

@cli.group()
def text():
    """text.* entities — set value."""


@text.command("set")
@click.argument("entity_id")
@click.argument("value")
@click.pass_context
def text_set(ctx, entity_id, value):
    emit(ctx, entity_control_core.text_set_value(
        make_client(ctx), entity_id, value=value,
    ))


# ──────────────────────────────────────────────────────── notify

@cli.group()
def notify():
    """notify.* services — send a notification with title/data/target."""


@notify.command("send")
@click.argument("message")
@click.option("--title", default=None)
@click.option("--service", default="notify",
              help="Which notify.<service> to call (default: notify)")
@click.option("--target", "targets", multiple=True,
              help="Target id (repeatable)")
@click.option("--data", default=None, help="JSON-encoded data payload")
@click.pass_context
def notify_send_cmd(ctx, message, title, service, targets, data):
    target: str | list[str] | None
    if not targets:
        target = None
    elif len(targets) == 1:
        target = targets[0]
    else:
        target = list(targets)
    parsed_data = json.loads(data) if data else None
    emit(ctx, entity_control_core.notify_send(
        make_client(ctx),
        message=message,
        title=title,
        target=target,
        data=parsed_data,
        service=service,
    ))


# ──────────────────────────────────────────────────────── powercalc

@cli.group()
def powercalc():
    """Powercalc safety wrappers — virtual_power create / group membership /
    fixed-mode template edits. Uses the same safety helpers that defuse the
    REPLACE-on-write and binary_sensor-no-op footguns."""


@powercalc.command("list")
@click.option("--title-contains", default=None,
              help="Case-insensitive substring filter on entry title")
@click.option("--state", default=None,
              help="Filter by config-entry state (loaded/not_loaded/...)")
@click.pass_context
def powercalc_list(ctx, title_contains, state):
    """List powercalc config entries."""
    emit(ctx, powercalc_core.list_entries(
        make_client(ctx),
        title_contains=title_contains, state=state,
    ))


@powercalc.command("create")
@click.option("--source", "source_entity", required=True,
              help="Source entity_id powering the calculation")
@click.option("--name", required=True, help="Entry name")
@click.option("--power", type=float, default=None,
              help="Fixed wattage when source is 'on' (mutually exclusive with --template)")
@click.option("--template", "power_template", default=None,
              help="Jinja power_template (mutually exclusive with --power)")
@click.option("--standby", "standby_power", type=float, default=0,
              help="Standby power in W (default 0)")
@click.option("--no-energy-sensor", "create_energy_sensor",
              is_flag=True, default=True, flag_value=False,
              help="Don't create the matching energy sensor (default: do create)")
@click.option("--utility-meters", "create_utility_meters",
              is_flag=True, default=False,
              help="Also create utility_meter helpers (default: off)")
@click.option("--group", "groups", multiple=True,
              help="Powercalc group entry_id to auto-join (repeatable)")
@click.pass_context
def powercalc_create(ctx, source_entity, name, power, power_template,
                     standby_power, create_energy_sensor,
                     create_utility_meters, groups):
    """Create a virtual_power entry.

    Refuses fixed-mode (--power) on binary_sensor sources — those silently
    no-op in powercalc. Use --template "{{ <W> if is_state(...,'on') else 0 }}"."""
    emit(ctx, powercalc_core.create_virtual_power(
        make_client(ctx),
        source_entity=source_entity, name=name,
        power=power, power_template=power_template,
        standby_power=standby_power,
        create_energy_sensor=create_energy_sensor,
        create_utility_meters=create_utility_meters,
        groups=list(groups) if groups else None,
    ))


@powercalc.command("set-template")
@click.argument("entry_id")
@click.argument("power_template")
@click.pass_context
def powercalc_set_template(ctx, entry_id, power_template):
    """Replace the power_template on a fixed-mode virtual_power entry.

    Collapses the manual options-init → options-configure(next=fixed) →
    options-configure(power_template=...) flow into one call. Example:

      powercalc set-template <entry_id> \\
        "{{ 30 * ((state_attr('fan.x','percentage')|float(0))/100)**3
            if is_state('fan.x','on') else 0 }}"
    """
    emit(ctx, powercalc_core.set_power_template(
        make_client(ctx), entry_id, power_template=power_template,
    ))


@powercalc.command("set-power")
@click.argument("entry_id")
@click.argument("power", type=float)
@click.pass_context
def powercalc_set_power(ctx, entry_id, power):
    """Replace the fixed power (W) on a fixed-mode virtual_power entry."""
    emit(ctx, powercalc_core.set_fixed_power(
        make_client(ctx), entry_id, power=power,
    ))


@powercalc.command("set-standby")
@click.argument("entry_id")
@click.argument("standby_power", type=float)
@click.option("--source", "source_entity", default=None,
              help="Source entity_id to re-send (auto-resolved if omitted; "
                   "pass it if resolution fails so the source isn't blanked)")
@click.pass_context
def powercalc_set_standby(ctx, entry_id, standby_power, source_entity):
    """Set the OFF-state standby power (W) on a virtual_power entry.

    standby_power lives on the basic_options step — `set-power` / `set-template`
    can't reach it. Pairs with `set-power` (on-state W). Example:

      powercalc set-power   <entry_id> 7.4    # on  = 7.4 W
      powercalc set-standby <entry_id> 1.0    # off = 1.0 W
    """
    emit(ctx, powercalc_core.set_standby(
        make_client(ctx), entry_id,
        standby_power=standby_power, source_entity=source_entity,
    ))


@powercalc.command("show")
@click.argument("entry_id")
@click.pass_context
def powercalc_show(ctx, entry_id):
    """Show a virtual_power entry's live + configured state.

    Surfaces calculation_mode, source_entity, the current power reading, and
    (best-effort) the configured fixed power / template / standby_power — the
    options the config-entry list does not expose.
    """
    emit(ctx, powercalc_core.read_entry(make_client(ctx), entry_id))


@powercalc.command("reload")
@click.argument("entry_ids", nargs=-1, required=True)
@click.pass_context
def powercalc_reload(ctx, entry_ids):
    """Reload one or more powercalc entries (e.g. parent groups after a new
    leaf joined, so their flat 'entities' attribute regenerates)."""
    emit(ctx, powercalc_core.reload_groups_for_member(
        make_client(ctx), parent_entry_ids=list(entry_ids),
    ))


@powercalc.group("group")
def powercalc_group():
    """Manage powercalc group membership safely (read-merge-write)."""


@powercalc_group.command("members")
@click.argument("sensor_entity_id")
@click.pass_context
def powercalc_group_members(ctx, sensor_entity_id):
    """List the resolved entity list for a group's power sensor."""
    emit(ctx, powercalc_core.get_group_members(
        make_client(ctx), sensor_entity_id,
    ))


@powercalc_group.command("add-members")
@click.option("--entry-id", required=True, help="Group's config-entry id")
@click.option("--sensor", "sensor_entity_id", required=True,
              help="Group's power sensor entity_id (used to read current list)")
@click.option("--member", "entities", multiple=True, required=True,
              help="Power sensor entity_id to add (repeatable)")
@click.pass_context
def powercalc_group_add_members(ctx, entry_id, sensor_entity_id, entities):
    """SAFELY add members (read current list, merge, write back)."""
    emit(ctx, powercalc_core.add_group_members(
        make_client(ctx), entry_id,
        sensor_entity_id=sensor_entity_id, entities=list(entities),
    ))


@powercalc_group.command("remove-members")
@click.option("--entry-id", required=True, help="Group's config-entry id")
@click.option("--sensor", "sensor_entity_id", required=True)
@click.option("--member", "entities", multiple=True, required=True,
              help="Power sensor entity_id to drop (repeatable)")
@click.pass_context
def powercalc_group_remove_members(ctx, entry_id, sensor_entity_id, entities):
    """SAFELY remove members (read current list, filter, write back)."""
    emit(ctx, powercalc_core.remove_group_members(
        make_client(ctx), entry_id,
        sensor_entity_id=sensor_entity_id, entities=list(entities),
    ))


@powercalc_group.command("set-members")
@click.option("--entry-id", required=True)
@click.option("--power-entity", "power_entities", multiple=True,
              help="Replacement power-sensor list (repeatable). Pass --power-entity= once with empty value to clear.")
@click.option("--sub-group", "sub_groups", multiple=True,
              help="Replacement sub_groups list (repeatable)")
@click.option("--energy-entity", "energy_entities", multiple=True,
              help="Replacement energy-sensor list (repeatable)")
@click.confirmation_option(prompt="REPLACE all group members. Continue?")
@click.pass_context
def powercalc_group_set_members(ctx, entry_id, power_entities,
                                sub_groups, energy_entities):
    """DESTRUCTIVE: replace a group's membership lists with the provided
    sets. Prefer add-members / remove-members unless you really do want
    to overwrite the whole list."""
    emit(ctx, powercalc_core.set_group_members(
        make_client(ctx), entry_id,
        power_entities=list(power_entities) if power_entities else None,
        sub_groups=list(sub_groups) if sub_groups else None,
        energy_entities=list(energy_entities) if energy_entities else None,
    ))


# ──────────────────────────────────────────────────────── entity restored / prune

@entity.command("restored")
@click.option("--platform", default=None,
              help="Filter to entities whose registry platform matches")
@click.option("--summary/--no-summary", default=True,
              help="Print platform breakdown only (default) vs full entity list")
@click.pass_context
def entity_restored(ctx, platform, summary):
    """List entities currently flagged restored=true (HA loaded them from
    registry but no integration claimed them on boot).

    Strong orphan signal — but mind false positives for intermittent
    integrations (iBeacon, doorbell, MQTT-after-quiet)."""
    from collections import Counter
    rows = registry_core.find_restored_entities(make_client(ctx))
    if platform:
        rows = [r for r in rows if r.get("platform") == platform]
    if summary and not ctx.obj.get("as_json"):
        by_plat = Counter(r.get("platform") for r in rows)
        emit(ctx, {"total": len(rows),
                   "by_platform": dict(by_plat.most_common())})
        return
    emit(ctx, rows)


@entity.command("orphans")
@click.option("--reason", default=None,
              type=click.Choice(["missing", "no_config_entry"]),
              help="Filter to one orphan flavor")
@click.pass_context
def entity_orphans(ctx, reason):
    """List entities whose config_entry_id references a missing config entry,
    OR has no config_entry_id at all (typically YAML-helper leftovers)."""
    rows = registry_core.find_orphan_entities(make_client(ctx))
    if reason:
        rows = [r for r in rows if r.get("_orphan_reason") == reason]
    emit(ctx, rows)


@entity.command("prune")
@click.option("--platform", default=None,
              help="Only delete entries with this registry platform")
@click.option("--restored", is_flag=True, default=False,
              help="Only delete entries currently flagged restored=true")
@click.option("--orphan", is_flag=True, default=False,
              help="Only delete entries whose config entry is missing")
@click.option("--disabled-by", default=None,
              type=click.Choice(["integration", "user", "device", "config_entry",
                                 "hass", "any"], case_sensitive=False),
              help="Only delete entries with this disabled_by value (or 'any')")
@click.option("--entity-id", "entity_ids", multiple=True,
              help="Exact entity_id (repeatable). When supplied, all other filters are ignored.")
@click.option("--dry-run/--apply", default=True,
              help="Default: dry run. Pass --apply to actually delete.")
@click.option("--protect-user-disabled/--no-protect-user-disabled",
              default=True,
              help="Never delete user-disabled entries (default: on)")
@click.pass_context
def entity_prune(ctx, platform, restored, orphan, disabled_by,
                 entity_ids, dry_run, protect_user_disabled):
    """Bulk-delete registry entries matching criteria. Backup first."""
    client = make_client(ctx)

    if entity_ids:
        # Explicit entity list — but still honour --protect-user-disabled so a
        # typo in --entity-id can't smash a registry entry the operator chose
        # to keep around as "disabled by user".
        requested = list(entity_ids)
        if protect_user_disabled:
            reg = registry_core.list_entities(client)
            user_disabled = {e["entity_id"] for e in reg
                              if e.get("disabled_by") == "user"}
            skipped = [eid for eid in requested if eid in user_disabled]
            targets = [eid for eid in requested if eid not in user_disabled]
            if skipped and not ctx.obj.get("as_json"):
                click.echo(
                    f"  skipped {len(skipped)} user-disabled entries "
                    f"(--protect-user-disabled): {skipped[:5]}"
                    + ("..." if len(skipped) > 5 else ""),
                    err=True,
                )
        else:
            targets = requested
    else:
        reg = registry_core.list_entities(client)
        live_ids = set()
        if restored:
            states = client.get("states")
            live_ids = {s["entity_id"] for s in states
                        if s.get("attributes", {}).get("restored") is True}

        orphan_ids: set[str] = set()
        if orphan:
            orphans = registry_core.find_orphan_entities(client)
            orphan_ids = {e["entity_id"] for e in orphans}

        targets = []
        for e in reg:
            if platform and e.get("platform") != platform:
                continue
            if restored and e["entity_id"] not in live_ids:
                continue
            if orphan and e["entity_id"] not in orphan_ids:
                continue
            if disabled_by:
                if disabled_by.lower() == "any":
                    if not e.get("disabled_by"):
                        continue
                elif e.get("disabled_by") != disabled_by.lower():
                    continue
            if protect_user_disabled and e.get("disabled_by") == "user":
                continue
            targets.append(e["entity_id"])

    if not targets:
        emit(ctx, {"dry_run": dry_run, "total": 0, "removed": [], "failed": [],
                   "note": "no entries matched filters"})
        return

    def _progress(done, total, ok, errs):
        if not ctx.obj.get("as_json"):
            click.echo(f"  {done}/{total}  ok={ok} errs={errs}", err=True)

    res = registry_core.bulk_remove_entities(
        client, entity_ids=targets, dry_run=dry_run,
        on_progress=_progress,
    )
    emit(ctx, {
        "dry_run": res["dry_run"],
        "total": res["total"],
        "removed_count": len(res["removed"]),
        "failed_count": len(res["failed"]),
        "failed": res["failed"][:20],
        "removed_sample": res["removed"][:10],
    })


# ──────────────────────────────────────────────────────── recorder top

@recorder.command("top")
@click.option("--hours", type=float, default=24,
              help="Window (default 24h)")
@click.option("--domain", "domains", multiple=True,
              help="Restrict to these domains (repeatable). Recommended on big installs.")
@click.option("--limit", type=int, default=20)
@click.pass_context
def recorder_top(ctx, hours, domains, limit):
    """Rank entities by state-change count over the last N hours.

    The first question when investigating recorder bloat. Cost: one
    history call per sampled entity, so set --domain on big installs."""
    emit(ctx, recorder_core.top_entities(
        make_client(ctx),
        hours=hours, domains=list(domains) if domains else None,
        limit=limit, by="changes",
    ))


# ──────────────────────────────────────────────────────── powercalc calibration

@powercalc.command("audit")
@click.option("--smart-meter", "smart_meter", default=None,
              help="Smart-meter sensor (default: sensor.smart_meter_electricity_power)")
@click.option("--home-total", "home_total", default=None,
              help="Powercalc Home Total sensor (default: sensor.power_home_total_power)")
@click.option("--hours", type=float, default=24,
              help="Window in hours (default 24)")
@click.option("--top", "top_n", type=int, default=8,
              help="How many groups to rank (default 8)")
@click.pass_context
def powercalc_audit(ctx, smart_meter, home_total, hours, top_n):
    """Passive coverage report — smart-meter actual vs powercalc Home Total
    over a window, plus a ranked list of sub-groups by contribution.

    Points you at the biggest mis-modelled chunks without flipping any
    switches. Read-only."""
    kw = {"hours": hours, "top_n": top_n}
    if smart_meter:
        kw["smart_meter"] = smart_meter
    if home_total:
        kw["home_total"] = home_total
    emit(ctx, powercalc_calibration_core.audit(make_client(ctx), **kw))


@powercalc.command("calibrate")
@click.argument("entry_id")
@click.option("--service-on", "service_on", required=True,
              help="Service to invoke to put the device under load "
                   "(e.g. light.turn_on, switch.turn_on)")
@click.option("--target", required=True,
              help="entity_id to target (or a JSON dict for richer targets)")
@click.option("--service-off", "service_off", default=None,
              help="Service to fire after measurement to leave device idle")
@click.option("--smart-meter", "smart_meter", default=None,
              help="Smart-meter sensor (default: sensor.smart_meter_electricity_power)")
@click.option("--baseline-seconds", "baseline_seconds", type=float, default=30,
              help="Baseline measurement duration (default 30s)")
@click.option("--stabilisation-seconds", "stabilisation_seconds",
              type=float, default=10,
              help="Pause after service_on before sampling load (default 10s)")
@click.option("--load-seconds", "load_seconds", type=float, default=30,
              help="Load measurement duration (default 30s)")
@click.option("--samples", type=int, default=6,
              help="Samples per measurement window (default 6)")
@click.option("--max-variance-w", "max_variance_w", type=float, default=50.0,
              help="Reject+retry a measurement window whose spread (max−min) "
                   "exceeds this many watts — i.e. another load moved during "
                   "it (default 50; 0 or negative disables the gate)")
@click.option("--max-retries", "max_retries", type=int, default=2,
              help="Extra attempts for a noisy window before giving up "
                   "(default 2)")
@click.option("--apply", "apply_", is_flag=True, default=False,
              help="Write the measured delta into the entry's fixed power")
@click.pass_context
def powercalc_calibrate(ctx, entry_id, service_on, target, service_off,
                         smart_meter, baseline_seconds, stabilisation_seconds,
                         load_seconds, samples, max_variance_w, max_retries,
                         apply_):
    """Active single-shot calibration for a FIXED-POWER device.

    Reads smart-meter baseline → fires --service-on → waits for
    stabilisation → reads smart-meter load → computes delta → optionally
    writes via `powercalc set-power`.

    Example: calibrate a tower-fan switch at full speed:

      powercalc calibrate <entry_id> --service-on switch.turn_on \\
        --target switch.tower_fan --service-off switch.turn_off \\
        --baseline-seconds 30 --load-seconds 30 --apply
    """
    # Allow JSON-dict target for richer targets (area/device).
    target_val: str | dict = target
    if target.lstrip().startswith("{"):
        try:
            target_val = json.loads(target)
        except json.JSONDecodeError:
            pass
    kw = {
        "service_on": service_on,
        "target": target_val,
        "baseline_seconds": baseline_seconds,
        "stabilisation_seconds": stabilisation_seconds,
        "load_seconds": load_seconds,
        "samples": samples,
        "service_off": service_off,
        "max_spread_w": (max_variance_w if max_variance_w > 0 else None),
        "max_retries": max_retries,
        "apply_": apply_,
    }
    if smart_meter:
        kw["smart_meter"] = smart_meter
    emit(ctx, powercalc_calibration_core.calibrate(
        make_client(ctx), entry_id, **kw,
    ))


@powercalc.command("calibrate-template")
@click.argument("entry_id")
@click.option("--source", "source_entity", required=True,
              help="Device entity_id (e.g. fan.dining_room_fan_main_fan)")
@click.option("--attribute", required=True,
              help="State attribute keying the template (e.g. percentage)")
@click.option("--service-set", "service_set", required=True,
              help="Service that sets the attribute (e.g. fan.set_percentage)")
@click.option("--state-arg", "state_arg", required=True,
              help="Service-data key carrying the step value (e.g. percentage)")
@click.option("--service-off", "service_off", required=True,
              help="Service to turn the device off (e.g. fan.turn_off)")
@click.option("--states", required=True,
              help="Comma-separated list of values to walk through "
                   "(e.g. 0,25,50,75,100)")
@click.option("--smart-meter", "smart_meter", default=None)
@click.option("--baseline-seconds", "baseline_seconds", type=float, default=20)
@click.option("--stabilisation-seconds", "stabilisation_seconds",
              type=float, default=15)
@click.option("--load-seconds", "load_seconds", type=float, default=20)
@click.option("--samples", type=int, default=5)
@click.option("--max-variance-w", "max_variance_w", type=float, default=50.0,
              help="Reject+retry a step whose smart-meter window spread "
                   "(max−min) exceeds this many watts; persistently-noisy "
                   "steps are excluded from the fitted template "
                   "(default 50; 0 or negative disables the gate)")
@click.option("--max-retries", "max_retries", type=int, default=2,
              help="Extra attempts for a noisy step before excluding it "
                   "(default 2)")
@click.option("--apply", "apply_", is_flag=True, default=False,
              help="Write the generated power_template into the entry")
@click.pass_context
def powercalc_calibrate_template(ctx, entry_id, source_entity, attribute,
                                  service_set, state_arg, service_off,
                                  states, smart_meter, baseline_seconds,
                                  stabilisation_seconds, load_seconds,
                                  samples, max_variance_w, max_retries,
                                  apply_):
    """Active multi-step calibration for a VARIABLE device.

    Walks the device through each value in --states, measures the
    smart-meter delta per state, and builds a piecewise power_template.

    Example: fit a fan's per-percentage profile:

      powercalc calibrate-template <entry_id> \\
        --source fan.dining_room_fan_main_fan \\
        --attribute percentage \\
        --service-set fan.set_percentage \\
        --state-arg percentage \\
        --service-off fan.turn_off \\
        --states 16,33,50,66,83,100 --apply
    """
    try:
        state_values: list[float | int] = []
        for s in states.split(","):
            s = s.strip()
            if not s:
                continue
            v = float(s)
            state_values.append(int(v) if v.is_integer() else v)
    except ValueError:
        raise click.BadParameter(f"could not parse --states {states!r}")
    kw = {
        "source_entity": source_entity,
        "attribute": attribute,
        "service_set": service_set,
        "state_arg": state_arg,
        "service_off": service_off,
        "states": state_values,
        "baseline_seconds": baseline_seconds,
        "stabilisation_seconds": stabilisation_seconds,
        "load_seconds": load_seconds,
        "samples": samples,
        "max_spread_w": (max_variance_w if max_variance_w > 0 else None),
        "max_retries": max_retries,
        "apply_": apply_,
    }
    if smart_meter:
        kw["smart_meter"] = smart_meter
    emit(ctx, powercalc_calibration_core.calibrate_template(
        make_client(ctx), entry_id, **kw,
    ))


@powercalc.command("auto-calibrate")
@click.option("--smart-meter", "smart_meter", default=None,
              help="Smart-meter sensor (default: sensor.smart_meter_electricity_power)")
@click.option("--hours", type=float, default=24 * 7,
              help="History window (default 168h = 7 days)")
@click.option("--pre-seconds", "pre_window_seconds", type=float, default=30,
              help="Baseline window before each transition (default 30s)")
@click.option("--post-seconds", "post_window_seconds", type=float, default=30,
              help="Load window after each transition (default 30s)")
@click.option("--quiet-seconds", "quiet_seconds", type=float, default=10,
              help="Reject transitions where any other tracked device "
                   "changed within ±this many seconds (default 10s)")
@click.option("--min-samples", "min_samples", type=int, default=5,
              help="Minimum clean transitions before suggesting (default 5)")
@click.option("--title-contains", "title_contains", default=None,
              help="Only process entries whose title contains this substring")
@click.option("--apply", "apply_", is_flag=True, default=False,
              help="Apply median deltas via powercalc set-power. "
                   "Dry-run by default.")
@click.pass_context
def powercalc_auto_calibrate(ctx, smart_meter, hours, pre_window_seconds,
                              post_window_seconds, quiet_seconds, min_samples,
                              title_contains, apply_):
    """PASSIVE calibration: scan recorder history for clean on/off
    transitions, compute median smart-meter delta per device, and
    optionally write the result into each entry's fixed power.

    No switches need to be flipped — runs entirely on saved history.
    Default is dry-run.

    Example workflow:

      # 1. See what auto-calibration would suggest (dry-run):
      powercalc auto-calibrate --hours 168 --json | jq '.candidates'

      # 2. Apply only to entries whose title contains "Lamp":
      powercalc auto-calibrate --title-contains Lamp --apply
    """
    kw = {
        "hours": hours,
        "pre_window_seconds": pre_window_seconds,
        "post_window_seconds": post_window_seconds,
        "quiet_seconds": quiet_seconds,
        "min_samples": min_samples,
        "title_contains": title_contains,
        "apply_": apply_,
    }
    if smart_meter:
        kw["smart_meter"] = smart_meter
    emit(ctx, powercalc_calibration_core.auto_calibrate(
        make_client(ctx), **kw,
    ))


# ──────────────────────────────────────────────────────── powercalc regress (Tier 2)

@powercalc.command("regress")
@click.option("--smart-meter", "smart_meter", default=None,
              help="Smart-meter sensor (default: sensor.smart_meter_electricity_power)")
@click.option("--hours", type=float, default=24 * 7,
              help="History window (default 168h = 7 days)")
@click.option("--interval", "interval_seconds", type=float, default=60,
              help="Grid spacing in seconds (default 60s = 1 min)")
@click.option("--title-contains", "title_contains", default=None,
              help="Only fit entries whose title contains this substring")
@click.option("--min-on", "min_on_fraction", type=float, default=0.005,
              help="Drop devices on for less than this fraction of samples (default 0.5%)")
@click.option("--min-off", "min_off_fraction", type=float, default=0.005,
              help="Drop devices on for MORE than 1-this fraction (no variance)")
@click.option("--apply", "apply_", is_flag=True, default=False,
              help="Write each fitted coefficient into the matching entry's "
                   "fixed power. Dry-run by default.")
@click.pass_context
def powercalc_regress(ctx, smart_meter, hours, interval_seconds,
                       title_contains, min_on_fraction, min_off_fraction,
                       apply_):
    """TIER-2 ML: fit a linear regression of the smart-meter signal
    against the binary on/off state of every tracked device
    simultaneously.

    Each device's regression coefficient is its expected smart-meter
    delta when on, holding every other tracked device fixed — what
    powercalc's fixed_power should be set to. Output also reports
    R² (model quality) and per-coefficient 95 % confidence interval.

    Catches two cases that the median-of-transitions auto-calibrate
    misses: devices that always switch in concert with another device,
    and devices with no clean OFF→ON transitions (e.g. cycling fridges).

    Default dry-run. Example:

      # Inspect what 7 days of data would suggest:
      powercalc regress --hours 168 --json | jq '.candidates'

      # Apply only to entries whose title contains "Lamp":
      powercalc regress --title-contains Lamp --apply
    """
    kw = {
        "hours": hours,
        "interval_seconds": interval_seconds,
        "title_contains": title_contains,
        "min_on_fraction": min_on_fraction,
        "min_off_fraction": min_off_fraction,
        "apply_": apply_,
    }
    if smart_meter:
        kw["smart_meter"] = smart_meter
    emit(ctx, powercalc_regression_core.regress(make_client(ctx), **kw))


# ════════════════════════════════════════════════════════════════════════════
# refine pass: zone, webhook, image, profiler
# ════════════════════════════════════════════════════════════════════════════

# ────────────────────────────────────────────────────────────── zone registry

@cli.group()
def zone():
    """Zone registry — storage zones from the UI (config/zone WS).

    YAML-declared zones in configuration.yaml are not in the registry; use
    `zone state-list` to see every `zone.*` entity, registry-backed or not.
    """


@zone.command("list")
@click.pass_context
def zone_list(ctx):
    """List storage zones (does NOT include YAML zones)."""
    emit(ctx, zone_core.list_zones(make_client(ctx)))


@zone.command("state-list")
@click.pass_context
def zone_state_list(ctx):
    """List every zone.* entity state (registry + YAML, combined)."""
    emit(ctx, zone_core.list_state_zones(make_client(ctx)))


@zone.command("find")
@click.argument("ident")
@click.pass_context
def zone_find(ctx, ident):
    """Find a storage zone by id or by case-insensitive name."""
    out = zone_core.find_zone(make_client(ctx), ident)
    if not out:
        _abort(f"no zone matching {ident!r}")
    emit(ctx, out)


@zone.command("create")
@click.argument("name")
@click.option("--lat", "latitude", type=float, required=True,
              help="Centre latitude (decimal degrees)")
@click.option("--lon", "longitude", type=float, required=True,
              help="Centre longitude (decimal degrees)")
@click.option("--radius", type=float, default=None,
              help="Zone radius in metres (default 100m on the server side)")
@click.option("--icon", default=None, help="mdi: icon, e.g. mdi:school")
@click.option("--passive/--active", "passive", default=None,
              help="Passive zones don't influence presence resolution")
@click.pass_context
def zone_create(ctx, name, latitude, longitude, radius, icon, passive):
    """Create a new storage zone."""
    emit(ctx, zone_core.create(
        make_client(ctx),
        name=name, latitude=latitude, longitude=longitude,
        radius=radius, icon=icon, passive=passive,
    ))


@zone.command("update")
@click.argument("zone_id")
@click.option("--name", default=None)
@click.option("--lat", "latitude", type=float, default=None)
@click.option("--lon", "longitude", type=float, default=None)
@click.option("--radius", type=float, default=None)
@click.option("--icon", default=None)
@click.option("--passive/--active", "passive", default=None)
@click.pass_context
def zone_update(ctx, zone_id, name, latitude, longitude, radius, icon, passive):
    """Patch a storage zone — only fields you pass are sent."""
    emit(ctx, zone_core.update(
        make_client(ctx), zone_id,
        name=name, latitude=latitude, longitude=longitude,
        radius=radius, icon=icon, passive=passive,
    ))


@zone.command("delete")
@click.argument("zone_id")
@click.confirmation_option(prompt="Delete this zone?")
@click.pass_context
def zone_delete(ctx, zone_id):
    """Delete a storage zone (YAML zones are read-only)."""
    emit(ctx, zone_core.delete(make_client(ctx), zone_id))


@zone.command("entities")
@click.argument("zone_ident")
@click.pass_context
def zone_entities(ctx, zone_ident):
    """List person/device_tracker entities currently inside ZONE_IDENT.

    ZONE_IDENT may be an entity_id (`zone.home`) or a friendly name.
    """
    emit(ctx, zone_core.entities_in_zone(make_client(ctx), zone_ident))


# ──────────────────────────────────────────────────────────────────── webhook

@cli.group()
def webhook():
    """Webhook triggers — the `/api/webhook/<id>` endpoint plus discovery.

    Webhooks here are HA's incoming-call surface: automations register one,
    HA assigns an id, and external systems POST to `/api/webhook/<id>` to
    trigger the automation. This group lets you list registered webhooks,
    fire one for testing, generate a fresh webhook id, and read cloudhook
    pairings when Nabu Casa cloud is connected.
    """


@webhook.command("list")
@click.option("--include-automations/--no-automations", default=True,
              help="Scan automations for `webhook` triggers and surface their ids")
@click.option("--include-mobile/--no-mobile", default=True,
              help="Include mobile_app webhooks registered per device")
@click.pass_context
def webhook_list(ctx, include_automations, include_mobile):
    """List every webhook id this HA instance currently honours."""
    emit(ctx, webhook_core.list_webhooks(
        make_client(ctx),
        include_automations=include_automations,
        include_mobile=include_mobile,
    ))


@webhook.command("trigger")
@click.argument("webhook_id")
@click.option("--method", type=click.Choice(["POST", "PUT", "GET", "HEAD"]),
              default="POST", show_default=True)
@click.option("--data", default=None,
              help="JSON body to send (object). Mutually exclusive with --form-data")
@click.option("--form-data", "form_pairs", multiple=True,
              help="key=value form fields (repeatable). Sent as form-urlencoded")
@click.option("--allowed/--all", "allowed_only", default=True,
              help="--allowed = only attempt if id is in the registry list (safer)")
@click.pass_context
def webhook_trigger(ctx, webhook_id, method, data, form_pairs, allowed_only):
    """Fire a webhook by id — POSTs to `/api/webhook/<id>` by default."""
    body: Any = None
    if data and form_pairs:
        _abort("--data and --form-data are mutually exclusive")
    if data:
        try:
            body = json.loads(data)
        except json.JSONDecodeError as exc:
            _abort(f"--data must be valid JSON: {exc}")
    elif form_pairs:
        body = parse_kv_pairs(form_pairs)
    emit(ctx, webhook_core.trigger(
        make_client(ctx),
        webhook_id=webhook_id,
        method=method,
        body=body,
        guard_registered=allowed_only,
    ))


@webhook.command("generate-id")
@click.pass_context
def webhook_generate_id(ctx):
    """Mint a fresh webhook id without registering it anywhere.

    Same RNG HA uses for automation webhook ids. Useful for scripting an
    automation creation flow.
    """
    emit(ctx, webhook_core.generate_id())


@webhook.command("cloudhooks")
@click.pass_context
def webhook_cloudhooks(ctx):
    """List cloudhook bindings (Nabu Casa) — webhook_id → external URL."""
    emit(ctx, webhook_core.cloudhooks(make_client(ctx)))


@webhook.command("cloudhook-create")
@click.argument("webhook_id")
@click.pass_context
def webhook_cloudhook_create(ctx, webhook_id):
    """Create a cloudhook binding for an existing local webhook id."""
    emit(ctx, webhook_core.cloudhook_create(make_client(ctx), webhook_id))


@webhook.command("cloudhook-delete")
@click.argument("webhook_id")
@click.confirmation_option(prompt="Delete the cloudhook binding?")
@click.pass_context
def webhook_cloudhook_delete(ctx, webhook_id):
    """Delete a cloudhook binding (the local webhook keeps working)."""
    emit(ctx, webhook_core.cloudhook_delete(make_client(ctx), webhook_id))


# ────────────────────────────────────────────────────────────────────── image

@cli.group()
def image():
    """image.* entities — snapshots, live image-proxy URLs, signed URLs."""


@image.command("list")
@click.option("--include-attributes/--no-attributes", default=False)
@click.pass_context
def image_list(ctx, include_attributes):
    """List every image.* entity with its current state."""
    emit(ctx, image_core.list_image_entities(
        make_client(ctx), include_attributes=include_attributes,
    ))


@image.command("show")
@click.argument("entity_id")
@click.pass_context
def image_show(ctx, entity_id):
    """Show the full state record for an image entity (state + attributes)."""
    emit(ctx, image_core.get_image_entity(make_client(ctx), entity_id))


@image.command("snapshot")
@click.argument("entity_id")
@click.argument("output_path", type=click.Path(dir_okay=False, writable=True))
@click.option("--overwrite/--no-overwrite", default=False,
              help="Replace OUTPUT_PATH if it already exists")
@click.option("--signed/--direct", default=False,
              help="Use auth/sign_path to mint a one-shot URL, then fetch unauthenticated")
@click.option("--expires", type=int, default=30,
              help="If --signed, seconds the signed URL is valid for")
@click.pass_context
def image_snapshot(ctx, entity_id, output_path, overwrite, signed, expires):
    """Download the current frame from an image entity to OUTPUT_PATH."""
    result = image_core.snapshot(
        make_client(ctx),
        entity_id=entity_id,
        output_path=output_path,
        overwrite=overwrite,
        signed=signed,
        expires=expires,
    )
    emit(ctx, result)


@image.command("proxy-url")
@click.argument("entity_id")
@click.option("--signed/--unsigned", default=True,
              help="Sign the URL so it works without an Authorization header (default: signed)")
@click.option("--expires", type=int, default=30, show_default=True)
@click.pass_context
def image_proxy_url(ctx, entity_id, signed, expires):
    """Return the `/api/image_proxy/<entity_id>` URL (signed by default)."""
    emit(ctx, image_core.proxy_url(
        make_client(ctx), entity_id=entity_id,
        signed=signed, expires=expires,
    ))


@image.command("subscribe")
@click.argument("entity_id")
@click.option("--timeout", type=int, default=10,
              help="Stop after N seconds (default 10)")
@click.pass_context
def image_subscribe(ctx, entity_id, timeout):
    """Subscribe to image_updated events for ENTITY_ID and print each.

    Uses the state-change event stream filtered to this entity. Image-domain
    entities update their `state` attribute (an opaque hash) whenever a new
    frame is ready, so each emitted event marks a fresh snapshot.
    """
    emit(ctx, image_core.subscribe_updates(
        make_client(ctx), entity_id=entity_id, timeout=timeout,
    ))


# ─────────────────────────────────────────────────────────────────── profiler

@cli.group()
def profiler():
    """profiler.* services — cProfile / memray / object dumps / async tasks.

    All commands here are pass-throughs to the `profiler` integration. Add
    the integration first if it isn't loaded:

      service call profiler.start --data '{"seconds": 60}'

    is the long form; this group is the safety-wrappered version.
    """


@profiler.command("start")
@click.option("--seconds", type=int, default=60, show_default=True,
              help="Profiling window. cProfile dump is written to .storage")
@click.pass_context
def profiler_start(ctx, seconds):
    """Start cProfile profiling for N seconds."""
    emit(ctx, profiler_core.start(make_client(ctx), seconds=seconds))


@profiler.command("memory")
@click.option("--seconds", type=int, default=60, show_default=True)
@click.pass_context
def profiler_memory(ctx, seconds):
    """Capture a memory profile via memray for N seconds."""
    emit(ctx, profiler_core.memory(make_client(ctx), seconds=seconds))


@profiler.command("dump-log-objects")
@click.option("--type", "type_", required=True,
              help="Python class name to dump (e.g. State, Event, EntityFilter)")
@click.pass_context
def profiler_dump_log_objects(ctx, type_):
    """Dump every live instance of TYPE to the log."""
    emit(ctx, profiler_core.dump_log_objects(make_client(ctx), type_=type_))


@profiler.command("log-thread-frames")
@click.pass_context
def profiler_log_thread_frames(ctx):
    """Log a stack frame for every running thread (snapshot of the GIL)."""
    emit(ctx, profiler_core.log_thread_frames(make_client(ctx)))


@profiler.command("log-event-loop-scheduled")
@click.pass_context
def profiler_log_event_loop_scheduled(ctx):
    """Log every scheduled callback queued on the asyncio event loop."""
    emit(ctx, profiler_core.log_event_loop_scheduled(make_client(ctx)))


@profiler.command("log-current-tasks")
@click.pass_context
def profiler_log_current_tasks(ctx):
    """Log every currently running asyncio task (active stack)."""
    emit(ctx, profiler_core.log_current_tasks(make_client(ctx)))


@profiler.command("lru-stats")
@click.pass_context
def profiler_lru_stats(ctx):
    """Dump @lru_cache statistics for every cache HA has registered."""
    emit(ctx, profiler_core.lru_stats(make_client(ctx)))


@profiler.command("set-asyncio-debug")
@click.option("--enabled/--disabled", default=True, show_default=True)
@click.pass_context
def profiler_set_asyncio_debug(ctx, enabled):
    """Toggle asyncio debug mode at runtime (slow-callback warnings, etc.)."""
    emit(ctx, profiler_core.set_asyncio_debug(make_client(ctx), enabled=enabled))


@profiler.command("log-events")
@click.pass_context
def profiler_log_events(ctx):
    """Log a one-shot snapshot of the event bus listener counts."""
    emit(ctx, profiler_core.log_events(make_client(ctx)))


@profiler.command("status")
@click.pass_context
def profiler_status(ctx):
    """Is the profiler integration loaded? Which services are exposed?"""
    emit(ctx, profiler_core.status(make_client(ctx)))


# ════════════════════════════════════════════════════════════════════════════
# Newly-wired core modules (17 — see prompt 2026-05-29)
# ════════════════════════════════════════════════════════════════════════════


# ────────────────────────────────────────────────────────── backup-advanced
# Sub-group under existing `backup` (overlaps backup_core but covers HA
# 2024.6+ WS-only commands: backup/details, agents/info, config/info|update,
# can_decrypt_on_download, generate_with_automatic_settings).

@backup.group("advanced")
def backup_advanced():
    """Backup WS API for HA 2024.6+ — details, agents, config, decrypt-check."""


@backup_advanced.command("details")
@click.argument("backup_id")
@click.pass_context
def backup_advanced_details(ctx, backup_id):
    """Full metadata for one backup including per-agent availability."""
    emit(ctx, backup_advanced_core.details(make_client(ctx), backup_id=backup_id))


@backup_advanced.command("delete")
@click.argument("backup_id")
@click.confirmation_option(prompt="Delete this backup across ALL agents?")
@click.pass_context
def backup_advanced_delete(ctx, backup_id):
    """Delete a backup across all agents (WS backup/delete)."""
    emit(ctx, backup_advanced_core.delete(make_client(ctx), backup_id=backup_id))


@backup_advanced.command("restore")
@click.argument("backup_id")
@click.argument("agent_id")
@click.option("--password", default=None, help="Decryption password (if encrypted)")
@click.option("--restore-addon", "restore_addons", multiple=True,
              help="Subset of add-ons to restore (repeatable). Omit for all.")
@click.option("--restore-database/--no-restore-database", default=True)
@click.option("--restore-folder", "restore_folders", multiple=True,
              help="Subset of folders to restore (repeatable). Omit for all.")
@click.option("--restore-homeassistant/--no-restore-homeassistant", default=True)
@click.confirmation_option(prompt="Restore will RESTART Home Assistant. Proceed?")
@click.pass_context
def backup_advanced_restore(ctx, backup_id, agent_id, password,
                             restore_addons, restore_database,
                             restore_folders, restore_homeassistant):
    """Restore HA from a backup. **Destructive — HA will restart.**"""
    emit(ctx, backup_advanced_core.restore(
        make_client(ctx),
        backup_id=backup_id, agent_id=agent_id, password=password,
        restore_addons=list(restore_addons) or None,
        restore_database=restore_database,
        restore_folders=list(restore_folders) or None,
        restore_homeassistant=restore_homeassistant,
    ))


@backup_advanced.command("auto-generate")
@click.confirmation_option(prompt="Trigger an automatic backup now?")
@click.pass_context
def backup_advanced_auto_generate(ctx):
    """Trigger a backup using the stored automatic-backup configuration."""
    emit(ctx, backup_advanced_core.generate_with_automatic_settings(make_client(ctx)))


@backup_advanced.command("list-agents")
@click.pass_context
def backup_advanced_list_agents(ctx):
    """List available backup storage agents (local, cloud, network, …)."""
    emit(ctx, backup_advanced_core.list_agents(make_client(ctx)))


@backup_advanced.command("get-config")
@click.pass_context
def backup_advanced_get_config(ctx):
    """Read the current backup automation / schedule configuration."""
    emit(ctx, backup_advanced_core.get_config(make_client(ctx)))


@backup_advanced.command("update-config")
@click.option("--body-json", default=None,
              help="Raw JSON for the full payload (overrides per-field flags)")
@click.option("--from-file", "from_file", type=click.Path(exists=True, dir_okay=False),
              default=None, help="Read JSON payload from file")
@click.option("--create-backup", "create_backup_json", default=None,
              help="JSON for create_backup dict (agent_ids, include_*, name, password)")
@click.option("--retention", "retention_json", default=None,
              help='JSON for retention dict, e.g. \'{"copies": 3, "days": 30}\'')
@click.option("--schedule", "schedule_json", default=None,
              help='JSON for schedule dict, e.g. \'{"state": "daily"}\'')
@click.option("--last-attempted", "last_attempted", default=None,
              help="ISO-8601 timestamp")
@click.option("--last-completed", "last_completed", default=None,
              help="ISO-8601 timestamp")
@click.option("--automatic/--no-automatic", "automatic", default=None)
@click.confirmation_option(prompt="Update backup configuration?")
@click.pass_context
def backup_advanced_update_config(ctx, body_json, from_file,
                                    create_backup_json, retention_json,
                                    schedule_json, last_attempted, last_completed,
                                    automatic):
    """Update the backup automation configuration (at least one field required)."""
    if from_file:
        payload = json.loads(Path(from_file).read_text())
    elif body_json:
        payload = json.loads(body_json)
    else:
        payload = {}
        if create_backup_json is not None:
            payload["create_backup"] = json.loads(create_backup_json)
        if retention_json is not None:
            payload["retention"] = json.loads(retention_json)
        if schedule_json is not None:
            payload["schedule"] = json.loads(schedule_json)
        if last_attempted is not None:
            payload["last_attempted_automatic_backup"] = last_attempted
        if last_completed is not None:
            payload["last_completed_automatic_backup"] = last_completed
        if automatic is not None:
            payload["automatic_backups_configured"] = automatic
    emit(ctx, backup_advanced_core.update_config(make_client(ctx), **payload))


@backup_advanced.command("can-decrypt")
@click.argument("backup_id")
@click.argument("agent_id")
@click.option("--password", required=True)
@click.pass_context
def backup_advanced_can_decrypt(ctx, backup_id, agent_id, password):
    """Check whether the password decrypts the backup on download."""
    emit(ctx, backup_advanced_core.can_decrypt_on_download(
        make_client(ctx), backup_id=backup_id,
        agent_id=agent_id, password=password,
    ))


# ────────────────────────────────────────────────────────── calendar-ws
# The existing `calendar` group is REST-based; this one wraps the WS event
# CRUD path (calendar/event/create|update|delete).

@cli.group("calendar-ws")
def calendar_ws():
    """Calendar event CRUD via WebSocket — create/update/delete."""


@calendar_ws.command("create")
@click.argument("entity_id")
@click.option("--body-json", default=None,
              help="Inline JSON for the event dict")
@click.option("--from-file", "from_file", type=click.Path(exists=True, dir_okay=False),
              default=None, help="Read event JSON from a file")
@click.confirmation_option(prompt="Create this calendar event?")
@click.pass_context
def calendar_ws_create(ctx, entity_id, body_json, from_file):
    """Create a new event on a calendar entity (requires --body-json or --from-file)."""
    if from_file:
        event = json.loads(Path(from_file).read_text())
    elif body_json:
        event = json.loads(body_json)
    else:
        raise click.UsageError("Provide --body-json or --from-file")
    emit(ctx, calendar_ws_core.create_event(
        make_client(ctx), entity_id=entity_id, event=event,
    ))


@calendar_ws.command("update")
@click.argument("entity_id")
@click.option("--body-json", default=None,
              help="Inline JSON for the event dict (must include uid)")
@click.option("--from-file", "from_file", type=click.Path(exists=True, dir_okay=False),
              default=None)
@click.option("--recurrence-id", default=None,
              help="ISO-8601 datetime for a recurring instance")
@click.option("--recurrence-range", default=None,
              type=click.Choice(["", "THISANDFUTURE"]))
@click.confirmation_option(prompt="Update this calendar event?")
@click.pass_context
def calendar_ws_update(ctx, entity_id, body_json, from_file,
                         recurrence_id, recurrence_range):
    """Update an existing calendar event (event must include uid)."""
    if from_file:
        event = json.loads(Path(from_file).read_text())
    elif body_json:
        event = json.loads(body_json)
    else:
        raise click.UsageError("Provide --body-json or --from-file")
    emit(ctx, calendar_ws_core.update_event(
        make_client(ctx), entity_id=entity_id, event=event,
        recurrence_id=recurrence_id, recurrence_range=recurrence_range,
    ))


@calendar_ws.command("delete")
@click.argument("entity_id")
@click.argument("uid")
@click.option("--recurrence-id", default=None)
@click.option("--recurrence-range", default=None,
              type=click.Choice(["", "THISANDFUTURE"]))
@click.confirmation_option(prompt="Delete this calendar event?")
@click.pass_context
def calendar_ws_delete(ctx, entity_id, uid, recurrence_id, recurrence_range):
    """Delete a calendar event by uid."""
    emit(ctx, calendar_ws_core.delete_event(
        make_client(ctx), entity_id=entity_id, uid=uid,
        recurrence_id=recurrence_id, recurrence_range=recurrence_range,
    ))


# ────────────────────────────────────────────────────────── diagnostics download
# Sits under existing `diagnostics` group (already has list/get/device).

@diagnostics.command("download")
@click.argument("entry_id")
@click.option("--device-id", default=None,
              help="When set, downloads device diagnostics instead of entry-level")
@click.option("-o", "--out", type=click.Path(), default=None,
              help="Save to file instead of printing")
@click.pass_context
def diagnostics_download(ctx, entry_id, device_id, out):
    """Download integration (or device) diagnostics bundle as JSON."""
    client = make_client(ctx)
    if device_id:
        data = diagnostics_dl_core.download_device_diagnostics(
            client, entry_id=entry_id, device_id=device_id,
        )
    else:
        data = diagnostics_dl_core.download_config_entry_diagnostics(
            client, entry_id=entry_id,
        )
    if out:
        n = diagnostics_dl_core.save_diagnostics_to_file(data, out)
        emit(ctx, {"saved": out, "bytes": n})
    else:
        emit(ctx, data)


# ────────────────────────────────────────────────────────── entity registry extras
# Subcommands on existing `entity` group.

@entity.command("get")
@click.argument("entity_id")
@click.pass_context
def entity_get_registry(ctx, entity_id):
    """Retrieve a single entity registry entry (WS config/entity_registry/get)."""
    emit(ctx, entity_registry_extras_core.get_entity_registry_entry(
        make_client(ctx), entity_id=entity_id,
    ))


@entity.command("get-many")
@click.argument("entity_ids", nargs=-1, required=True)
@click.pass_context
def entity_get_many(ctx, entity_ids):
    """Retrieve multiple entity registry entries by id."""
    emit(ctx, entity_registry_extras_core.get_entity_registry_entries(
        make_client(ctx), entity_ids=list(entity_ids),
    ))


@entity.command("list-for-display")
@click.pass_context
def entity_list_for_display(ctx):
    """List entity registry in the UI-optimised display format."""
    emit(ctx, entity_registry_extras_core.list_entity_registry_for_display(
        make_client(ctx),
    ))


@entity.command("remove")
@click.argument("entity_id")
@click.confirmation_option(prompt="Remove this entity from the registry?")
@click.pass_context
def entity_remove_registry(ctx, entity_id):
    """Remove an entity from the registry (WS config/entity_registry/remove)."""
    emit(ctx, entity_registry_extras_core.remove_entity_registry_entry(
        make_client(ctx), entity_id=entity_id,
    ))


@entity.command("subscribe-config-entries")
@click.pass_context
def entity_subscribe_config_entries(ctx):
    """One-shot snapshot of config_entries/subscribe state."""
    emit(ctx, entity_registry_extras_core.subscribe_config_entries(make_client(ctx)))


@entity.command("integration-setup-info")
@click.pass_context
def entity_integration_setup_info(ctx):
    """Get integration setup timings + errors (WS integration/setup_info)."""
    emit(ctx, entity_registry_extras_core.get_integration_setup_info(make_client(ctx)))


@entity.command("statistic-during-period")
@click.argument("statistic_id")
@click.option("--fixed-period", default=None,
              help='JSON for fixed_period, e.g. \'{"start_time":"...","end_time":"..."}\'')
@click.option("--calendar", "calendar_json", default=None,
              help="JSON for calendar period dict")
@click.option("--rolling-window", default=None,
              help="JSON for rolling_window dict")
@click.option("--type", "types", multiple=True,
              help="Statistic types to include (repeatable)")
@click.option("--units", default=None,
              help="JSON dict of unit overrides per statistic_id")
@click.pass_context
def entity_statistic_during_period(ctx, statistic_id, fixed_period,
                                     calendar_json, rolling_window,
                                     types, units):
    """Query statistics for one statistic_id over a time period (singular)."""
    emit(ctx, entity_registry_extras_core.statistic_during_period(
        make_client(ctx),
        statistic_id=statistic_id,
        fixed_period=json.loads(fixed_period) if fixed_period else None,
        calendar=json.loads(calendar_json) if calendar_json else None,
        rolling_window=json.loads(rolling_window) if rolling_window else None,
        types=list(types) or None,
        units=json.loads(units) if units else None,
    ))


# ────────────────────────────────────────────────────────── frontend prefs

@cli.group()
def frontend():
    """Frontend prefs — per-user data store + template render/preview."""


@frontend.command("get-user-data")
@click.option("--key", default=None,
              help="Single key to read (omit for the whole store)")
@click.pass_context
def frontend_get_user_data(ctx, key):
    """Read frontend user-data (WS frontend/get_user_data)."""
    emit(ctx, frontend_prefs_core.get_user_data(make_client(ctx), key=key))


@frontend.command("set-user-data")
@click.argument("key")
@click.option("--value", "value_str", default=None,
              help="JSON-encoded value (preferred). Strings fall back to raw text.")
@click.option("--from-file", "from_file",
              type=click.Path(exists=True, dir_okay=False), default=None,
              help="Read JSON value from a file")
@click.confirmation_option(prompt="Write this key to frontend user-data?")
@click.pass_context
def frontend_set_user_data(ctx, key, value_str, from_file):
    """Write a key/value pair to the frontend user-data store."""
    if from_file:
        value = json.loads(Path(from_file).read_text())
    elif value_str is not None:
        try:
            value = json.loads(value_str)
        except json.JSONDecodeError:
            value = value_str
    else:
        raise click.UsageError("Provide --value or --from-file")
    emit(ctx, frontend_prefs_core.set_user_data(
        make_client(ctx), key=key, value=value,
    ))


@frontend.command("render-template")
@click.option("--template", "template_str", default=None,
              help="Inline Jinja2 template string")
@click.option("--from-file", "from_file",
              type=click.Path(exists=True, dir_okay=False), default=None,
              help="Read template from a file")
@click.option("--variables", default=None,
              help="JSON dict of extra variables")
@click.option("--timeout", type=float, default=None,
              help="Render timeout in seconds")
@click.pass_context
def frontend_render_template(ctx, template_str, from_file, variables, timeout):
    """One-shot render of a Jinja2 template via REST POST /api/template."""
    if from_file:
        tpl = Path(from_file).read_text()
    elif template_str:
        tpl = template_str
    else:
        raise click.UsageError("Provide --template or --from-file")
    emit(ctx, frontend_prefs_core.render_template(
        make_client(ctx),
        template=tpl,
        variables=json.loads(variables) if variables else None,
        timeout=timeout,
    ))


@frontend.command("start-template-preview")
@click.option("--template", "template_str", default=None)
@click.option("--from-file", "from_file",
              type=click.Path(exists=True, dir_okay=False), default=None)
@click.option("--variables", default=None,
              help="JSON dict of extra variables")
@click.pass_context
def frontend_start_template_preview(ctx, template_str, from_file, variables):
    """Send the initial WS template/start_preview subscription message.

    Note: this only kicks off the subscription; consuming streamed events
    requires the WS subscribe machinery in the underlying client.
    """
    if from_file:
        tpl = Path(from_file).read_text()
    elif template_str:
        tpl = template_str
    else:
        raise click.UsageError("Provide --template or --from-file")
    result = frontend_prefs_core.start_template_preview(
        make_client(ctx),
        template=tpl,
        variables=json.loads(variables) if variables else None,
    )
    emit(ctx, {"started": True, "result": result})


# ────────────────────────────────────────────────────────── network

@cli.group()
def network():
    """Network adapters + internal/external/cloud URLs (WS network/*)."""


@network.command("info")
@click.pass_context
def network_info(ctx):
    """Get network adapter information."""
    emit(ctx, network_core.info(make_client(ctx)))


@network.command("configure")
@click.option("--adapter", "configured_adapters", multiple=True, required=True,
              help="Adapter name to enable (repeatable)")
@click.confirmation_option(prompt="Apply this network adapter configuration?")
@click.pass_context
def network_configure(ctx, configured_adapters):
    """Configure which network adapters are active."""
    emit(ctx, network_core.configure(
        make_client(ctx),
        configured_adapters=list(configured_adapters),
    ))


@network.command("url")
@click.pass_context
def network_url(ctx):
    """Get internal, external, and cloud URLs."""
    emit(ctx, network_core.url(make_client(ctx)))


# ────────────────────────────────────────────────────────── energy advanced
# Subcommands on existing `energy` group.

@energy.command("validate")
@click.pass_context
def energy_validate(ctx):
    """Validate the current Energy dashboard preferences (WS energy/validate)."""
    emit(ctx, energy_advanced_core.validate_energy_prefs(make_client(ctx)))


@energy.command("solar-forecast")
@click.pass_context
def energy_solar_forecast(ctx):
    """Solar production forecast for the next day (WS energy/solar_forecast)."""
    emit(ctx, energy_advanced_core.solar_forecast(make_client(ctx)))


@energy.command("fossil-consumption")
@click.option("--start", "start_time", required=True, help="ISO-8601 start (UTC)")
@click.option("--end", "end_time", required=True, help="ISO-8601 end (UTC)")
@click.option("--energy-statistic-id", "energy_statistic_ids", multiple=True,
              required=True,
              help="Recorder statistic id for an energy source (repeatable)")
@click.option("--co2-statistic-id", required=True,
              help="Recorder statistic id for the CO2-intensity signal")
@click.option("--period", default="hour",
              type=click.Choice(["5minute", "hour", "day", "week", "month"]))
@click.pass_context
def energy_fossil_consumption(ctx, start_time, end_time,
                                energy_statistic_ids, co2_statistic_id, period):
    """Compute fossil-fuel energy consumption with the HA 2024+ signature."""
    emit(ctx, energy_advanced_core.fossil_energy_consumption(
        make_client(ctx),
        start_time=start_time, end_time=end_time,
        energy_statistic_ids=list(energy_statistic_ids),
        co2_statistic_id=co2_statistic_id,
        period=period,
    ))


@energy.command("save-prefs-structured")
@click.option("--energy-sources", default=None,
              help="JSON list of energy-source dicts (required)")
@click.option("--device-consumption", default=None,
              help="JSON list of device-consumption dicts")
@click.option("--manual-statistic-id", "manual_statistic_ids", multiple=True,
              help="Manually-configured statistic id (repeatable)")
@click.option("--from-file", "from_file",
              type=click.Path(exists=True, dir_okay=False), default=None,
              help="Read the full payload from a JSON file")
@click.confirmation_option(prompt="Replace Energy dashboard prefs?")
@click.pass_context
def energy_save_prefs_structured(ctx, energy_sources, device_consumption,
                                   manual_statistic_ids, from_file):
    """Save structured Energy prefs (energy_sources required)."""
    if from_file:
        payload = json.loads(Path(from_file).read_text())
    else:
        if not energy_sources:
            raise click.UsageError("Provide --energy-sources or --from-file")
        payload = {
            "energy_sources": json.loads(energy_sources),
        }
        if device_consumption is not None:
            payload["device_consumption"] = json.loads(device_consumption)
        if manual_statistic_ids:
            payload["manual_configured_statistic_ids"] = list(manual_statistic_ids)
    emit(ctx, energy_advanced_core.save_prefs(make_client(ctx), **payload))


# ────────────────────────────────────────────────────────── statistics admin
# Subcommands on existing `statistics` group.

@statistics.command("adjust-sum")
@click.argument("statistic_id")
@click.option("--start", "start_time", required=True, help="ISO-8601 UTC")
@click.option("--adjustment", type=float, required=True,
              help="Signed float to add to the stored sum")
@click.option("--adjustment-unit", "adjustment_unit_of_measurement", default=None,
              help="Unit for the adjustment value (defaults to stored unit)")
@click.confirmation_option(prompt="Adjust the sum statistic? (destructive)")
@click.pass_context
def statistics_adjust_sum(ctx, statistic_id, start_time, adjustment,
                            adjustment_unit_of_measurement):
    """Adjust the stored sum of a statistic series from a point in time."""
    emit(ctx, statistics_admin_core.adjust_sum_statistics(
        make_client(ctx),
        statistic_id=statistic_id,
        start_time=start_time,
        adjustment=adjustment,
        adjustment_unit_of_measurement=adjustment_unit_of_measurement,
    ))


@statistics.command("change-unit")
@click.argument("statistic_id")
@click.option("--new-unit", "new_unit_of_measurement", required=True)
@click.option("--old-unit", "old_unit_of_measurement", required=True)
@click.confirmation_option(prompt="Convert all stored statistics to the new unit?")
@click.pass_context
def statistics_change_unit(ctx, statistic_id,
                             new_unit_of_measurement, old_unit_of_measurement):
    """Convert all stored statistics for a series to a new unit."""
    emit(ctx, statistics_admin_core.change_statistics_unit(
        make_client(ctx),
        statistic_id=statistic_id,
        new_unit_of_measurement=new_unit_of_measurement,
        old_unit_of_measurement=old_unit_of_measurement,
    ))


@statistics.command("validate")
@click.pass_context
def statistics_validate(ctx):
    """Run recorder validation; returns {statistic_id: [issue, ...]}."""
    emit(ctx, statistics_admin_core.validate_statistics(make_client(ctx)))


@statistics.command("update-issue")
@click.argument("statistic_id")
@click.option("--issue-type", required=True,
              help="e.g. unsupported_state_class, units_changed")
@click.confirmation_option(prompt="Update / clear this statistics issue?")
@click.pass_context
def statistics_update_issue(ctx, statistic_id, issue_type):
    """Acknowledge or clear a recorder statistics issue."""
    emit(ctx, statistics_admin_core.update_statistics_issues(
        make_client(ctx),
        statistic_id=statistic_id,
        issue_type=issue_type,
    ))


@statistics.command("update-stored-metadata")
@click.argument("statistic_id")
@click.option("--unit", "unit_of_measurement", default=None,
              help="New stored unit. Pass empty/omit to clear.")
@click.confirmation_option(prompt="Update stored statistics metadata?")
@click.pass_context
def statistics_update_stored_metadata(ctx, statistic_id, unit_of_measurement):
    """Update the stored unit_of_measurement for a statistic id."""
    emit(ctx, statistics_admin_core.update_statistics_metadata(
        make_client(ctx),
        statistic_id=statistic_id,
        unit_of_measurement=unit_of_measurement,
    ))


@statistics.command("import")
@click.option("--metadata", "metadata_json", default=None,
              help="Inline JSON for the metadata dict")
@click.option("--stats", "stats_json", default=None,
              help="Inline JSON for the stats list")
@click.option("--from-file", "from_file",
              type=click.Path(exists=True, dir_okay=False), default=None,
              help='File containing {"metadata": {...}, "stats": [...]}')
@click.confirmation_option(prompt="Import these statistics rows?")
@click.pass_context
def statistics_import(ctx, metadata_json, stats_json, from_file):
    """Import external or internal statistics into the recorder."""
    if from_file:
        payload = json.loads(Path(from_file).read_text())
        metadata = payload["metadata"]
        stats = payload["stats"]
    else:
        if not (metadata_json and stats_json):
            raise click.UsageError(
                "Provide --metadata+--stats together, or --from-file",
            )
        metadata = json.loads(metadata_json)
        stats = json.loads(stats_json)
    emit(ctx, statistics_admin_core.import_statistics(
        make_client(ctx), metadata=metadata, stats=stats,
    ))


# ────────────────────────────────────────────────────────── helper previews

@cli.group("helper-preview")
def helper_preview():
    """Live config-flow preview subscriptions for helper domains.

    These are WebSocket subscription commands — this CLI only sends the
    initial subscribe message; full event-stream consumption requires the
    underlying client's ws_subscribe machinery.
    """


def _print_preview_event(event):
    """Default on_event callback for helper-preview commands."""
    click.echo(json.dumps(event, default=str))


_HELPER_PREVIEW_DOMAINS = (
    "group", "generic_camera", "mold_indicator", "statistics",
    "threshold", "time_date", "switch_as_x",
)


@helper_preview.command("start")
@click.option("--domain", required=True,
              type=click.Choice(_HELPER_PREVIEW_DOMAINS),
              help="Helper domain to preview")
@click.option("--flow-id", required=True)
@click.option("--flow-type", default="config_flow",
              type=click.Choice(["config_flow", "options_flow"]))
@click.option("--user-input", "user_input_json", default=None,
              help="JSON dict of user input (required)")
@click.option("--from-file", "from_file",
              type=click.Path(exists=True, dir_okay=False), default=None,
              help="Read user_input JSON from file")
@click.option("--max-events", type=int, default=10, show_default=True,
              help="Stop after N events")
@click.pass_context
def helper_preview_start(ctx, domain, flow_id, flow_type,
                           user_input_json, from_file, max_events):
    """Start a live <domain>/start_preview subscription for a helper config flow."""
    if from_file:
        user_input = json.loads(Path(from_file).read_text())
    elif user_input_json:
        user_input = json.loads(user_input_json)
    else:
        raise click.UsageError("Provide --user-input or --from-file")
    helper_previews_core.start_helper_preview(
        make_client(ctx),
        domain=domain,
        flow_id=flow_id,
        flow_type=flow_type,
        user_input=user_input,
        on_event=_print_preview_event,
        max_events=max_events,
    )
    emit(ctx, {"started": False, "stopped": True, "domain": domain})


# ────────────────────────────────────────────────────────── history extras
# New group `history-ext` (the existing `history` is a single command).

@cli.group("history-ext")
def history_ext():
    """Long-history fallback — recorder states → long-term statistics."""


@history_ext.command("with-stats-fallback")
@click.argument("entity_id")
@click.option("--start", "start_iso", required=True, help="ISO-8601 start time")
@click.option("--end", "end_iso", default=None, help="ISO-8601 end (default: now)")
@click.option("--period", default="hour",
              type=click.Choice(["5minute", "hour", "day", "week", "month"]))
@click.option("--value-field", default="mean",
              type=click.Choice(["mean", "min", "max", "state", "sum", "change"]))
@click.pass_context
def history_ext_with_stats_fallback(ctx, entity_id, start_iso, end_iso,
                                       period, value_field):
    """Return a unified history list (recorder + statistics back-fill)."""
    from datetime import datetime as _dt
    start = _dt.fromisoformat(start_iso.replace("Z", "+00:00"))
    end = _dt.fromisoformat(end_iso.replace("Z", "+00:00")) if end_iso else None
    emit(ctx, history_ext_core.history_with_stats_fallback(
        make_client(ctx),
        entity_id=entity_id, start=start, end=end,
        period=period, value_field=value_field,
    ))


@history_ext.command("retention-estimate")
@click.argument("entity_id")
@click.option("--probe-days", type=int, default=60, show_default=True)
@click.pass_context
def history_ext_retention_estimate(ctx, entity_id, probe_days):
    """Estimate how far back the recorder retains states for an entity."""
    emit(ctx, history_ext_core.recorder_retention_estimate(
        make_client(ctx), entity_id=entity_id, probe_days=probe_days,
    ))


@history_ext.command("stats-to-samples")
@click.argument("statistic_id")
@click.option("--stats-json", default=None,
              help="Inline JSON for the stats_response dict")
@click.option("--from-file", "from_file",
              type=click.Path(exists=True, dir_okay=False), default=None)
@click.option("--value-field", default="mean",
              type=click.Choice(["mean", "min", "max", "state", "sum", "change"]))
@click.pass_context
def history_ext_stats_to_samples(ctx, statistic_id, stats_json,
                                     from_file, value_field):
    """Flatten a recorder/statistics_during_period response to {when,value,source} rows."""
    if from_file:
        stats_resp = json.loads(Path(from_file).read_text())
    elif stats_json:
        stats_resp = json.loads(stats_json)
    else:
        raise click.UsageError("Provide --stats-json or --from-file")
    emit(ctx, history_ext_core.statistics_to_samples(
        stats_resp, statistic_id=statistic_id, value_field=value_field,
    ))


# ────────────────────────────────────────────────────────── history-logbook
# Uses WS history/history_during_period which works around the REST
# "first 24h only" gotcha — handy for arbitrary multi-day windows.

@cli.group("history-logbook")
def history_logbook():
    """WS history + logbook — bypasses the REST first-24h-only gotcha."""


@history_logbook.command("history-during-period")
@click.option("--start", "start_time", required=True, help="RFC 3339 start_time")
@click.option("--end", "end_time", default=None, help="RFC 3339 end_time")
@click.option("--entity", "entity_ids", multiple=True, required=True,
              help="entity_id (repeatable)")
@click.option("--minimal-response", is_flag=True, default=False)
@click.option("--no-attributes", is_flag=True, default=False)
@click.option("--significant-only/--all-changes",
              "significant_changes_only", default=True)
@click.pass_context
def history_logbook_during_period(ctx, start_time, end_time, entity_ids,
                                     minimal_response, no_attributes,
                                     significant_changes_only):
    """Fetch full history for entities via WS history/history_during_period.

    NOTE: unlike the REST `history` command this honours the full --start
    → --end window rather than returning only the first 24h.
    """
    emit(ctx, history_logbook_core.history_during_period(
        make_client(ctx),
        start_time=start_time, end_time=end_time,
        entity_ids=list(entity_ids),
        minimal_response=minimal_response,
        no_attributes=no_attributes,
        significant_changes_only=significant_changes_only,
    ))


@history_logbook.command("history-stream")
@click.option("--start", "start_time", required=True)
@click.option("--end", "end_time", default=None)
@click.option("--entity", "entity_ids", multiple=True, required=True)
@click.option("--minimal-response", is_flag=True, default=False)
@click.option("--no-attributes", is_flag=True, default=False)
@click.option("--significant-only/--all-changes",
              "significant_changes_only", default=True)
@click.pass_context
def history_logbook_stream(ctx, start_time, end_time, entity_ids,
                              minimal_response, no_attributes,
                              significant_changes_only):
    """Initiate a history/stream subscription (initial backfill returned)."""
    emit(ctx, history_logbook_core.history_stream(
        make_client(ctx),
        entity_ids=list(entity_ids),
        start_time=start_time, end_time=end_time,
        minimal_response=minimal_response,
        no_attributes=no_attributes,
        significant_changes_only=significant_changes_only,
    ))


@history_logbook.command("logbook-events")
@click.option("--start", "start_time", required=True)
@click.option("--end", "end_time", default=None)
@click.option("--entity", "entity_ids", multiple=True,
              help="Filter by entity_id (repeatable)")
@click.option("--device", "device_ids", multiple=True,
              help="Filter by device_id (repeatable)")
@click.option("--context-id", default=None)
@click.pass_context
def history_logbook_events(ctx, start_time, end_time, entity_ids,
                              device_ids, context_id):
    """Fetch logbook events for a period (WS logbook/get_events)."""
    emit(ctx, history_logbook_core.logbook_get_events(
        make_client(ctx),
        start_time=start_time, end_time=end_time,
        entity_ids=list(entity_ids) or None,
        device_ids=list(device_ids) or None,
        context_id=context_id,
    ))


@history_logbook.command("logbook-stream")
@click.option("--start", "start_time", required=True)
@click.option("--end", "end_time", default=None)
@click.option("--entity", "entity_ids", multiple=True)
@click.option("--device", "device_ids", multiple=True)
@click.pass_context
def history_logbook_stream_cmd(ctx, start_time, end_time, entity_ids, device_ids):
    """Initiate a logbook/event_stream subscription (initial backfill returned)."""
    emit(ctx, history_logbook_core.logbook_event_stream(
        make_client(ctx),
        start_time=start_time, end_time=end_time,
        entity_ids=list(entity_ids) or None,
        device_ids=list(device_ids) or None,
    ))


# ────────────────────────────────────────────────────────── lovelace layout-lint
# Sits under the existing `lovelace` group (read-only).

@lovelace.command("layout-lint")
@click.argument("url_path")
@click.option("--rule", "rules", multiple=True,
              help="Restrict to a subset of rule names (repeatable)")
@click.option("--viewport", default="mobile",
              type=click.Choice(["mobile", "desktop", "both"]))
@click.option("--summary", is_flag=True, default=False,
              help="Print issue counts by rule instead of full issues")
@click.option("--format", "format_", default="auto",
              type=click.Choice(["auto", "human", "json"]),
              help="Output format. `auto` follows --json")
@click.pass_context
def lovelace_layout_lint(ctx, url_path, rules, viewport, summary, format_):
    """Layout-quality lint for a dashboard (warnings/info only — never errors)."""
    cfg = _fetch_dash_cfg(ctx, url_path)
    issues = lovelace_layout_lint_core.lint_layout(
        cfg,
        rules=set(rules) if rules else None,
        viewport=viewport,
    )
    if summary:
        emit(ctx, lovelace_layout_lint_core.summarise_by_rule(issues))
        return
    if format_ == "human" or (format_ == "auto" and not ctx.obj.get("as_json")):
        click.echo(lovelace_layout_lint_core.format_issues(issues))
        return
    emit(ctx, issues)


# ────────────────────────────────────────────────────────── lovelace sections-ext
# Layout-polish builders under existing `lovelace section` group.

@lovelace_section.command("hero")
@click.option("--card", "card_json", default=None,
              help="Inline JSON for the inner card dict")
@click.option("--from-file", "from_file",
              type=click.Path(exists=True, dir_okay=False), default=None,
              help="Read card JSON from file")
@click.option("--column-span", type=int, default=4, show_default=True)
@click.option("--heading-style", default="title",
              type=click.Choice(["title", "subtitle", "default"]))
@click.option("--top-margin/--no-top-margin", default=False)
@click.pass_context
def lovelace_section_hero(ctx, card_json, from_file, column_span,
                            heading_style, top_margin):
    """Build a hero section (single prominent card) — prints the JSON."""
    if from_file:
        card = json.loads(Path(from_file).read_text())
    elif card_json:
        card = json.loads(card_json)
    else:
        raise click.UsageError("Provide --card or --from-file")
    emit(ctx, lovelace_sections_ext_core.hero_section(
        card=card, column_span=column_span,
        heading_style=heading_style, top_margin=top_margin,
    ))


@lovelace_section.command("spacer")
@click.option("--column-span", type=int, default=4, show_default=True)
@click.pass_context
def lovelace_section_spacer(ctx, column_span):
    """Build a blank spacer section."""
    emit(ctx, lovelace_sections_ext_core.spacer_section(column_span=column_span))


@lovelace_section.command("divider")
@click.argument("label")
@click.option("--column-span", type=int, default=4, show_default=True)
@click.pass_context
def lovelace_section_divider(ctx, label, column_span):
    """Build a divider section containing only a heading card."""
    emit(ctx, lovelace_sections_ext_core.divider_section(
        label=label, column_span=column_span,
    ))


@lovelace_section.command("with-options")
@click.option("--section-json", default=None,
              help="Inline JSON for the section dict to mutate")
@click.option("--from-file", "from_file",
              type=click.Path(exists=True, dir_okay=False), default=None)
@click.option("--heading-style", default=None,
              type=click.Choice(["title", "subtitle", "default"]))
@click.option("--top-margin/--no-top-margin", "top_margin", default=None)
@click.option("--column-span", type=int, default=None)
@click.option("--row-span", type=int, default=None)
@click.pass_context
def lovelace_section_with_options(ctx, section_json, from_file,
                                    heading_style, top_margin,
                                    column_span, row_span):
    """Apply option fields to a section dict (returns the mutated copy)."""
    if from_file:
        section = json.loads(Path(from_file).read_text())
    elif section_json:
        section = json.loads(section_json)
    else:
        raise click.UsageError("Provide --section-json or --from-file")
    emit(ctx, lovelace_sections_ext_core.with_section_options(
        section,
        heading_style=heading_style, top_margin=top_margin,
        column_span=column_span, row_span=row_span,
    ))


# ────────────────────────────────────────────────────────── lovelace-views
# View-type-aware builders under existing `lovelace view` group.

@lovelace_view.command("build-sections")
@click.option("--title", required=True)
@click.option("--path", default=None)
@click.option("--sections", default=None, help="JSON list of section dicts")
@click.option("--sections-file", type=click.Path(exists=True, dir_okay=False),
              default=None)
@click.option("--max-columns", type=int, default=4, show_default=True)
@click.option("--dense-section-placement/--no-dense", "dense_section_placement",
              default=None)
@click.option("--top-margin/--no-top-margin", "top_margin", default=None)
@click.option("--icon", default=None)
@click.option("--theme", default=None)
@click.option("--subview", is_flag=True, default=False)
@click.option("--back-path", default=None)
@click.pass_context
def lovelace_view_build_sections(ctx, title, path, sections, sections_file,
                                    max_columns, dense_section_placement,
                                    top_margin, icon, theme, subview, back_path):
    """Build a `sections`-type view dict (modern HA layout)."""
    if sections_file:
        sec_list = json.loads(Path(sections_file).read_text())
    elif sections:
        sec_list = json.loads(sections)
    else:
        sec_list = None
    emit(ctx, lovelace_views_core.view_sections(
        title=title, path=path, sections=sec_list, max_columns=max_columns,
        dense_section_placement=dense_section_placement, top_margin=top_margin,
        icon=icon, theme=theme, subview=subview, back_path=back_path,
    ))


@lovelace_view.command("build-masonry")
@click.option("--title", required=True)
@click.option("--path", default=None)
@click.option("--cards", default=None, help="JSON list of card dicts")
@click.option("--cards-file", type=click.Path(exists=True, dir_okay=False),
              default=None)
@click.option("--icon", default=None)
@click.option("--theme", default=None)
@click.option("--subview", is_flag=True, default=False)
@click.option("--back-path", default=None)
@click.pass_context
def lovelace_view_build_masonry(ctx, title, path, cards, cards_file,
                                  icon, theme, subview, back_path):
    """Build a legacy `masonry`-type view dict."""
    if cards_file:
        card_list = json.loads(Path(cards_file).read_text())
    elif cards:
        card_list = json.loads(cards)
    else:
        card_list = None
    emit(ctx, lovelace_views_core.view_masonry(
        title=title, path=path, cards=card_list,
        icon=icon, theme=theme, subview=subview, back_path=back_path,
    ))


@lovelace_view.command("build-panel")
@click.option("--title", required=True)
@click.option("--path", default=None)
@click.option("--card", "card_json", default=None, help="Inline JSON for the single card")
@click.option("--card-file", type=click.Path(exists=True, dir_okay=False),
              default=None)
@click.option("--icon", default=None)
@click.option("--theme", default=None)
@click.option("--subview", is_flag=True, default=False)
@click.option("--back-path", default=None)
@click.pass_context
def lovelace_view_build_panel(ctx, title, path, card_json, card_file,
                                icon, theme, subview, back_path):
    """Build a `panel`-type view dict (one card fills the viewport)."""
    if card_file:
        card = json.loads(Path(card_file).read_text())
    elif card_json:
        card = json.loads(card_json)
    else:
        raise click.UsageError("Provide --card or --card-file")
    emit(ctx, lovelace_views_core.view_panel(
        title=title, card=card, path=path,
        icon=icon, theme=theme, subview=subview, back_path=back_path,
    ))


@lovelace_view.command("build-sidebar")
@click.option("--title", required=True)
@click.option("--path", default=None)
@click.option("--cards", default=None)
@click.option("--cards-file", type=click.Path(exists=True, dir_okay=False),
              default=None)
@click.option("--icon", default=None)
@click.option("--theme", default=None)
@click.option("--subview", is_flag=True, default=False)
@click.option("--back-path", default=None)
@click.pass_context
def lovelace_view_build_sidebar(ctx, title, path, cards, cards_file,
                                  icon, theme, subview, back_path):
    """Build a `sidebar`-type view dict (deprecated but functional)."""
    if cards_file:
        card_list = json.loads(Path(cards_file).read_text())
    elif cards:
        card_list = json.loads(cards)
    else:
        card_list = None
    emit(ctx, lovelace_views_core.view_sidebar(
        title=title, path=path, cards=card_list,
        icon=icon, theme=theme, subview=subview, back_path=back_path,
    ))


@lovelace_view.command("build-grid-layout")
@click.option("--title", required=True)
@click.option("--path", default=None)
@click.option("--cards", default=None)
@click.option("--cards-file", type=click.Path(exists=True, dir_okay=False),
              default=None)
@click.option("--grid-template-columns", default=None)
@click.option("--grid-template-rows", default=None)
@click.option("--grid-template-areas", default=None)
@click.option("--grid-gap", default=None)
@click.option("--max-cols", type=int, default=None)
@click.option("--max-width", type=int, default=None)
@click.option("--min-width", type=int, default=None)
@click.option("--mediaquery", default=None, help="JSON dict of breakpoint overrides")
@click.option("--icon", default=None)
@click.option("--theme", default=None)
@click.option("--subview", is_flag=True, default=False)
@click.option("--back-path", default=None)
@click.pass_context
def lovelace_view_build_grid_layout(ctx, title, path, cards, cards_file,
                                       grid_template_columns,
                                       grid_template_rows,
                                       grid_template_areas, grid_gap,
                                       max_cols, max_width, min_width,
                                       mediaquery, icon, theme,
                                       subview, back_path):
    """Build a `custom:grid-layout` view dict (layout-card plugin)."""
    if cards_file:
        card_list = json.loads(Path(cards_file).read_text())
    elif cards:
        card_list = json.loads(cards)
    else:
        card_list = None
    emit(ctx, lovelace_views_core.view_grid_layout(
        title=title, path=path, cards=card_list,
        grid_template_columns=grid_template_columns,
        grid_template_rows=grid_template_rows,
        grid_template_areas=grid_template_areas,
        grid_gap=grid_gap,
        max_cols=max_cols, max_width=max_width, min_width=min_width,
        mediaquery=json.loads(mediaquery) if mediaquery else None,
        icon=icon, theme=theme, subview=subview, back_path=back_path,
    ))


@lovelace_view.command("build-masonry-layout")
@click.option("--title", required=True)
@click.option("--path", default=None)
@click.option("--cards", default=None)
@click.option("--cards-file", type=click.Path(exists=True, dir_okay=False),
              default=None)
@click.option("--width", type=int, default=None)
@click.option("--max-cols", type=int, default=None)
@click.option("--max-width", type=int, default=None)
@click.option("--mediaquery", default=None)
@click.option("--icon", default=None)
@click.option("--theme", default=None)
@click.option("--subview", is_flag=True, default=False)
@click.option("--back-path", default=None)
@click.pass_context
def lovelace_view_build_masonry_layout(ctx, title, path, cards, cards_file,
                                          width, max_cols, max_width,
                                          mediaquery, icon, theme,
                                          subview, back_path):
    """Build a `custom:masonry-layout` view dict (layout-card plugin)."""
    if cards_file:
        card_list = json.loads(Path(cards_file).read_text())
    elif cards:
        card_list = json.loads(cards)
    else:
        card_list = None
    emit(ctx, lovelace_views_core.view_masonry_layout(
        title=title, path=path, cards=card_list,
        width=width, max_cols=max_cols, max_width=max_width,
        mediaquery=json.loads(mediaquery) if mediaquery else None,
        icon=icon, theme=theme, subview=subview, back_path=back_path,
    ))


@lovelace_view.command("summaries")
@click.argument("url_path")
@click.pass_context
def lovelace_view_summaries(ctx, url_path):
    """Print compact summaries of every view in a dashboard."""
    cfg = _fetch_dash_cfg(ctx, url_path)
    emit(ctx, lovelace_views_core.list_view_summaries(cfg))


@lovelace_view.command("set-max-columns")
@click.argument("url_path")
@click.argument("view_path")
@click.argument("n", type=int)
@click.option("--dry-run", is_flag=True, default=False)
@click.confirmation_option(prompt="Set max_columns on this view?")
@click.pass_context
def lovelace_view_set_max_columns(ctx, url_path, view_path, n, dry_run):
    """Set max_columns on a sections view (in-place mutation + save)."""
    cfg = _fetch_dash_cfg(ctx, url_path)
    view = lovelace_paths_core.get_view(cfg, view_path)
    lovelace_views_core.set_max_columns(view, n)
    lovelace_paths_core.set_view(cfg, view_path, view)
    emit(ctx, _push_dash_cfg(ctx, url_path, cfg, dry_run=dry_run))


@lovelace_view.command("set-subview")
@click.argument("url_path")
@click.argument("view_path")
@click.option("--subview/--no-subview", default=True)
@click.option("--back-path", default=None)
@click.option("--dry-run", is_flag=True, default=False)
@click.confirmation_option(prompt="Apply subview change?")
@click.pass_context
def lovelace_view_set_subview(ctx, url_path, view_path, subview, back_path, dry_run):
    """Mark / unmark a view as a subview, optionally setting back_path."""
    cfg = _fetch_dash_cfg(ctx, url_path)
    view = lovelace_paths_core.get_view(cfg, view_path)
    lovelace_views_core.set_subview(view, subview, back_path=back_path)
    lovelace_paths_core.set_view(cfg, view_path, view)
    emit(ctx, _push_dash_cfg(ctx, url_path, cfg, dry_run=dry_run))


@lovelace_view.command("set-visibility")
@click.argument("url_path")
@click.argument("view_path")
@click.option("--conditions", default=None,
              help="JSON for visibility conditions, `true`, `false`, or `null`")
@click.option("--dry-run", is_flag=True, default=False)
@click.confirmation_option(prompt="Apply visibility change?")
@click.pass_context
def lovelace_view_set_visibility(ctx, url_path, view_path, conditions, dry_run):
    """Set visibility on a view (list of conds, bool, or null to clear)."""
    cond = json.loads(conditions) if conditions is not None else None
    cfg = _fetch_dash_cfg(ctx, url_path)
    view = lovelace_paths_core.get_view(cfg, view_path)
    lovelace_views_core.set_visibility(view, cond)
    lovelace_paths_core.set_view(cfg, view_path, view)
    emit(ctx, _push_dash_cfg(ctx, url_path, cfg, dry_run=dry_run))


@lovelace_view.command("set-dense-section-placement")
@click.argument("url_path")
@click.argument("view_path")
@click.option("--dense/--no-dense", default=True)
@click.option("--dry-run", is_flag=True, default=False)
@click.confirmation_option(prompt="Apply dense_section_placement change?")
@click.pass_context
def lovelace_view_set_dense(ctx, url_path, view_path, dense, dry_run):
    """Toggle dense_section_placement on a sections view."""
    cfg = _fetch_dash_cfg(ctx, url_path)
    view = lovelace_paths_core.get_view(cfg, view_path)
    lovelace_views_core.set_dense_section_placement(view, dense)
    lovelace_paths_core.set_view(cfg, view_path, view)
    emit(ctx, _push_dash_cfg(ctx, url_path, cfg, dry_run=dry_run))


# ────────────────────────────────────────────────────────── state-stream

@cli.group("state-stream")
def state_stream():
    """Live WS event subscriptions — events, state_changed, triggers."""


def _print_event(event):
    """Default on_event for state-stream subcommands."""
    click.echo(json.dumps(event, default=str))


@state_stream.command("events")
@click.option("--event-type", default=None,
              help="Filter to this event type (omit for all events)")
@click.option("--max-events", type=int, default=10, show_default=True)
@click.pass_context
def state_stream_events(ctx, event_type, max_events):
    """Subscribe to HA event bus events and print each one."""
    state_stream_core.subscribe_events(
        make_client(ctx),
        event_type=event_type,
        on_event=_print_event,
        max_events=max_events,
    )
    emit(ctx, {"stopped": True, "max_events": max_events})


@state_stream.command("state-changed")
@click.option("--entity", "entity_ids", multiple=True,
              help="Filter to these entity_ids (repeatable)")
@click.option("--max-events", type=int, default=10, show_default=True)
@click.pass_context
def state_stream_state_changed(ctx, entity_ids, max_events):
    """Subscribe to state_changed events, optionally entity-filtered."""
    state_stream_core.subscribe_state_changed(
        make_client(ctx),
        entity_ids=list(entity_ids) or None,
        on_change=_print_event,
        max_events=max_events,
    )
    emit(ctx, {"stopped": True, "max_events": max_events})


@state_stream.command("trigger")
@click.option("--trigger", "trigger_json", default=None,
              help="Inline JSON for the trigger dict")
@click.option("--from-file", "from_file",
              type=click.Path(exists=True, dir_okay=False), default=None,
              help="Read trigger JSON from a file")
@click.option("--variables", default=None, help="JSON dict of variables")
@click.option("--max-events", type=int, default=10, show_default=True)
@click.pass_context
def state_stream_trigger(ctx, trigger_json, from_file, variables, max_events):
    """Subscribe to HA trigger evaluations and print each fired event."""
    if from_file:
        trig = json.loads(Path(from_file).read_text())
    elif trigger_json:
        trig = json.loads(trigger_json)
    else:
        raise click.UsageError("Provide --trigger or --from-file")
    state_stream_core.subscribe_trigger(
        make_client(ctx),
        trigger=trig,
        on_trigger=_print_event,
        variables=json.loads(variables) if variables else None,
        max_events=max_events,
    )
    emit(ctx, {"stopped": True, "max_events": max_events})


@state_stream.command("collect")
@click.option("--event-type", default=None)
@click.option("--count", type=int, default=1, show_default=True)
@click.option("--timeout-seconds", type=float, default=10.0, show_default=True)
@click.pass_context
def state_stream_collect(ctx, event_type, count, timeout_seconds):
    """Synchronously collect N events and print them as a list."""
    emit(ctx, state_stream_core.collect_events(
        make_client(ctx),
        event_type=event_type,
        count=count,
        timeout_seconds=timeout_seconds,
    ))


# ────────────────────────────────────────────────────────── trace-debug
# Distinct group from the existing automation/script trace commands.

@cli.group("trace-debug")
def trace_debug():
    """Trace introspection — WS trace/list, trace/get, trace/contexts."""


@trace_debug.command("list")
@click.option("--domain", default=None,
              type=click.Choice(["automation", "script"]))
@click.option("--item-id", default=None)
@click.pass_context
def trace_debug_list(ctx, domain, item_id):
    """List trace summaries (optionally filtered by domain/item_id)."""
    emit(ctx, trace_debug_core.list_traces(
        make_client(ctx), domain=domain, item_id=item_id,
    ))


@trace_debug.command("get")
@click.option("--domain", required=True,
              type=click.Choice(["automation", "script"]))
@click.option("--item-id", required=True)
@click.option("--run-id", required=True)
@click.pass_context
def trace_debug_get(ctx, domain, item_id, run_id):
    """Fetch the full trace dict for one run."""
    emit(ctx, trace_debug_core.get_trace(
        make_client(ctx), domain=domain, item_id=item_id, run_id=run_id,
    ))


@trace_debug.command("contexts")
@click.option("--domain", default=None,
              type=click.Choice(["automation", "script"]))
@click.option("--item-id", default=None)
@click.pass_context
def trace_debug_contexts(ctx, domain, item_id):
    """Return a mapping of context_id → trace coordinates."""
    emit(ctx, trace_debug_core.list_contexts(
        make_client(ctx), domain=domain, item_id=item_id,
    ))


# ────────────────────────────────────────────────────────── trace-debugger
# Live breakpoint debugger (advanced). /* TODO refine UX */

@cli.group("trace-debugger")
def trace_debugger():
    """Live breakpoint debugger for running scripts/automations.

    /* TODO refine UX */ — these wrap the WS trace/debug/* commands. The
    subscribe path is a streaming subscription in real HA (events fire on
    each breakpoint hit) and consuming that stream requires the underlying
    client's ws_subscribe machinery; the CLI here only sends the initial
    subscribe message.
    """


@trace_debugger.command("list-breakpoints")
@click.pass_context
def trace_debugger_list_breakpoints(ctx):
    """List currently registered breakpoints."""
    emit(ctx, trace_debugger_core.list_breakpoints(make_client(ctx)))


@trace_debugger.command("subscribe-breakpoints")
@click.pass_context
def trace_debugger_subscribe_breakpoints(ctx):
    """Send the initial trace/debug/breakpoint/subscribe message.

    Required before any set/clear breakpoint operations will be accepted.
    """
    emit(ctx, trace_debugger_core.subscribe_breakpoints(make_client(ctx)))


@trace_debugger.command("set-breakpoint")
@click.option("--domain", required=True,
              type=click.Choice(["automation", "script"]))
@click.option("--item-id", required=True)
@click.option("--node", required=True,
              help='Trace-node path, e.g. "action/0"')
@click.option("--run-id", default=None,
              help="Restrict the breakpoint to a specific run")
@click.confirmation_option(prompt="Register this breakpoint?")
@click.pass_context
def trace_debugger_set_breakpoint(ctx, domain, item_id, node, run_id):
    """Register a breakpoint on an automation/script trace node."""
    emit(ctx, trace_debugger_core.set_breakpoint(
        make_client(ctx),
        domain=domain, item_id=item_id, node=node, run_id=run_id,
    ))


@trace_debugger.command("clear-breakpoint")
@click.option("--domain", required=True,
              type=click.Choice(["automation", "script"]))
@click.option("--item-id", required=True)
@click.option("--node", required=True)
@click.option("--run-id", default=None)
@click.confirmation_option(prompt="Clear this breakpoint?")
@click.pass_context
def trace_debugger_clear_breakpoint(ctx, domain, item_id, node, run_id):
    """Remove a breakpoint (args must match the original set call)."""
    emit(ctx, trace_debugger_core.clear_breakpoint(
        make_client(ctx),
        domain=domain, item_id=item_id, node=node, run_id=run_id,
    ))


@trace_debugger.command("step")
@click.option("--domain", required=True,
              type=click.Choice(["automation", "script"]))
@click.option("--item-id", required=True)
@click.option("--run-id", required=True)
@click.confirmation_option(prompt="Step this paused run by one node?")
@click.pass_context
def trace_debugger_step(ctx, domain, item_id, run_id):
    """Advance a paused run by one step."""
    emit(ctx, trace_debugger_core.step_execution(
        make_client(ctx),
        domain=domain, item_id=item_id, run_id=run_id,
    ))


@trace_debugger.command("continue")
@click.option("--domain", required=True,
              type=click.Choice(["automation", "script"]))
@click.option("--item-id", required=True)
@click.option("--run-id", required=True)
@click.confirmation_option(prompt="Resume this paused run?")
@click.pass_context
def trace_debugger_continue(ctx, domain, item_id, run_id):
    """Resume a paused run until the next breakpoint."""
    emit(ctx, trace_debugger_core.continue_execution(
        make_client(ctx),
        domain=domain, item_id=item_id, run_id=run_id,
    ))


@trace_debugger.command("stop")
@click.option("--domain", required=True,
              type=click.Choice(["automation", "script"]))
@click.option("--item-id", required=True)
@click.option("--run-id", required=True)
@click.confirmation_option(prompt="Abort this paused run?")
@click.pass_context
def trace_debugger_stop(ctx, domain, item_id, run_id):
    """Abort a paused run."""
    emit(ctx, trace_debugger_core.stop_execution(
        make_client(ctx),
        domain=domain, item_id=item_id, run_id=run_id,
    ))


if __name__ == "__main__":
    main()
