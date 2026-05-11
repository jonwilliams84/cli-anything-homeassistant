"""cli-anything-homeassistant — control a running Home Assistant from the CLI."""

from __future__ import annotations

import json
import shlex
import sys
import threading
from pathlib import Path

import click

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
from cli_anything.homeassistant.core import recorder as recorder_core
from cli_anything.homeassistant.core import system as system_core
from cli_anything.homeassistant.core import template as template_core
from cli_anything.homeassistant.core import template_helpers as template_helpers_core
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
    skin = ReplSkin("homeassistant", version="1.4.0")
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


@event.command("subscribe")
@click.argument("event_type", required=False, default=None)
@click.option("--limit", default=10, type=int, help="Stop after this many events (default 10)")
@click.option("--timeout", "wait_timeout", default=None, type=int,
              help="Stop after N seconds")
@click.pass_context
def event_subscribe(ctx, event_type, limit, wait_timeout):
    """Subscribe to events via WebSocket and print them. Ctrl-C to stop."""
    client = make_client(ctx)
    stop = threading.Event()
    seen: list[dict] = []

    def on_msg(evt):
        seen.append(evt)
        if not ctx.obj.get("as_json"):
            click.echo(json.dumps(evt, default=str))
        if limit and len(seen) >= limit:
            stop.set()

    payload = {"event_type": event_type} if event_type else None

    if wait_timeout:
        threading.Timer(wait_timeout, stop.set).start()

    try:
        client.ws_subscribe("subscribe_events", payload, on_msg, stop)
    except KeyboardInterrupt:
        stop.set()

    if ctx.obj.get("as_json"):
        emit(ctx, seen)
    else:
        click.echo(f"received {len(seen)} event(s)")


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


@tag.command("update")
@click.argument("tag_id")
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.pass_context
def tag_update(ctx, tag_id, name, description):
    emit(ctx, tags_core.update(make_client(ctx), tag_id,
                                 name=name, description=description))


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
@click.pass_context
def automation_traces(ctx, entity_id):
    """List recent execution traces for an automation (most recent last)."""
    emit(ctx, automation_core.list_traces(make_client(ctx), entity_id))


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
@click.pass_context
def history_cmd(ctx, entity_ids, hours, start_iso, end_iso, minimal):
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
    emit(ctx, auth_core.current_user(make_client(ctx)))


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
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def lovelace_config_save(ctx, url_path, config_file, dry_run):
    """Replace a dashboard's config from a JSON file."""
    cfg = json.loads(Path(config_file).read_text())
    if dry_run:
        emit(ctx, {"dry_run": True, "url_path": url_path, "view_count": len(cfg.get("views", []))})
        return
    result = lovelace_core.save_dashboard_config(make_client(ctx), url_path, cfg)
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
@click.pass_context
def lovelace_view_set(ctx, url_path, view_path, view_file, dry_run):
    """Replace one view in a dashboard from a JSON file."""
    new_view = json.loads(Path(view_file).read_text())
    cfg = _fetch_dash_cfg(ctx, url_path)
    lovelace_paths_core.set_view(cfg, view_path, new_view)
    emit(ctx, _push_dash_cfg(ctx, url_path, cfg, dry_run=dry_run))


@lovelace_view.command("add")
@click.argument("url_path")
@click.argument("view_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--index", type=int, default=None,
              help="Insert at this index (default: append)")
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def lovelace_view_add(ctx, url_path, view_file, index, dry_run):
    """Append (or insert at --index) a new view from a JSON file."""
    new_view = json.loads(Path(view_file).read_text())
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
@click.pass_context
def lovelace_section_set(ctx, url_path, view_path, section_idx, section_file, dry_run):
    new_section = json.loads(Path(section_file).read_text())
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
@click.pass_context
def lovelace_card_replace(ctx, url_path, pointer, card_file, dry_run):
    """Replace a single card at <pointer> with the JSON from <card_file>."""
    new_card = json.loads(Path(card_file).read_text())
    client = make_client(ctx)
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
@click.pass_context
def lovelace_card_delete(ctx, url_path, pointer, yes):
    """Delete the card at <pointer>."""
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        old_card = dict(lovelace_cards_core.get_card(cfg, pointer))
    except (KeyError, IndexError, ValueError) as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
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
@click.pass_context
def lovelace_card_insert(ctx, url_path, parent_pointer, card_file, position):
    """Insert a new card into <parent_pointer>'s cards[] array."""
    new_card = json.loads(Path(card_file).read_text())
    client = make_client(ctx)
    cfg = lovelace_core.get_dashboard_config(client, url_path)
    try:
        lovelace_cards_core.insert_card(cfg, parent_pointer, new_card, position=position)
    except (KeyError, IndexError, ValueError) as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
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
@click.pass_context
def automation_save(ctx, entity_id, config_file):
    """Replace a UI-managed automation's config from a JSON file."""
    cfg = json.loads(Path(config_file).read_text())
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
@click.pass_context
def script_save(ctx, entity_id, config_file):
    """Replace a UI-managed script's config from a JSON file."""
    cfg = json.loads(Path(config_file).read_text())
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
    seen: list[dict] = []
    out_fh = open(out, "a") if out else None

    def on_msg(evt):
        seen.append(evt)
        line = json.dumps(evt, default=str)
        if not ctx.obj.get("as_json"):
            click.echo(line)
        if out_fh is not None:
            out_fh.write(line + "\n")
            out_fh.flush()
        if limit and len(seen) >= limit:
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
        emit(ctx, seen)
    else:
        click.echo(f"received {len(seen)} message(s)")


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
        rows.append({
            "backup_id": b.get("backup_id") or b.get("slug"),
            "name": b.get("name"),
            "date": b.get("date") or b.get("created_at"),
            "size_mb": round((b.get("size") or 0) / (1024 * 1024), 2) if b.get("size") else None,
            "protected": b.get("protected"),
            "type": b.get("type"),
            "agents": list((b.get("agents") or {}).keys()) or None,
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
@click.pass_context
def system_reload_core(ctx):
    emit(ctx, {"reloaded": "core_config",
                "result": control_core.reload_core_config(make_client(ctx))})


@system.command("reload-all")
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
@click.option("--type", "event_type", default=None,
              help="Event type to filter (default: all events)")
@click.option("--duration", type=float, default=10.0,
              help="Seconds to listen (default 10)")
@click.option("--limit", type=int, default=None,
              help="Stop after N events")
@click.pass_context
def event_subscribe(ctx, event_type, duration, limit):
    """Tail the HA event bus.

    With --json, returns a list of captured events. Without --json, prints
    each event one per line as it arrives.
    """
    if ctx.obj.get("as_json"):
        emit(ctx, watch_core.subscribe_events(
            make_client(ctx),
            event_type=event_type, duration=duration, limit=limit,
        ))
        return
    def _cb(ev):
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


if __name__ == "__main__":
    main()
