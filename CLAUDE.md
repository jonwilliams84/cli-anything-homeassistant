# cli-anything-homeassistant

A `click`-based CLI + interactive REPL that exposes the full Home Assistant REST +
WebSocket API surface (states, services, registries, lovelace, automations, backups,
diagnostics, statistics, powercalc, 17 typed entity-control groups, …) for agents and
shell scripts. Stateless thin client — HA does all the work; this never runs automation
logic or renders templates locally. Every command supports `--json`.

## Layout
- `cli_anything/homeassistant/homeassistant_cli.py` — the Click CLI + REPL (~10k lines, single file; all commands wired here). Entry point: `main`.
- `cli_anything/homeassistant/core/` — ~102 modules, one HA API surface each (states, registry, lovelace*, automation, backup, statistics, powercalc*, …). Each is pure function-per-operation, callable from Python directly or via the Click wrapper.
- `cli_anything/homeassistant/utils/homeassistant_backend.py` — the wire client: `requests.Session` (REST) + websocket-client (WS) + `download()` (streamed binary, for a multi-GB backup) and `upload()` (multipart). All core modules call through this. Three WS shapes, three methods: `ws_call` (request/response), `ws_subscribe` (open-ended, caller stops it), `ws_run_events` (run-to-completion — empty ack, then events, terminal condition read from the data; `on_ack` pushes binary audio on a daemon thread).
- `cli_anything/homeassistant/skills/SKILL.md` — packaged self-contained skill manifest (full command docs); packaged via `package_data`.
- `tests/` — 87 files, 3,800+ tests. `tests/conftest.py` defines `FakeClient` (records every REST/WS call, returns prepared responses). E2e tests boot a real HA in a temp config dir.
- `HOMEASSISTANT.md` — SOP / agent operating guide. `CHANGELOG.md` — per-version detail.

## Commands
- Install (editable): `pip install -e .` → exposes `cli-anything-homeassistant`.
- Test: `pip install -e '.[test]'` (installs pytest + homeassistant for e2e), then `python3 -m pytest tests/ -v` (config in `pytest.ini`: importlib mode, `testpaths=tests`).
- Run needs a live HA: `--url`/`--token` flags or env `HASS_URL` / `HASS_TOKEN` / `HASS_VERIFY_SSL` / `HASS_TIMEOUT`; persisted profile at `~/.config/cli-anything-homeassistant.json` (mode 0600).

## Conventions
- Deps are minimal and deliberate: `click`, `prompt-toolkit`, `requests`, `websocket-client`, `numpy` (numpy only for `powercalc regress` linear regression — no scipy/sklearn). Python >= 3.10.
- New API surface = new module under `core/` (pure functions) + a Click wrapper in `homeassistant_cli.py` + a unit test using `FakeClient`. Keep `--json` output on every new command.
- Versioning: bump `version` in `setup.py`, add a `CHANGELOG.md` entry. Work happens on `feat/*` branches → PR → merge to `main` (see git history). Tags like `v1.42.0` per release.
- Powercalc commands are safety wrappers over HA footguns (REPLACE-on-write options flow, binary_sensor no-op); preserve the backup-first / dry-run-by-default / `--apply`-to-commit pattern when extending them (mirrored in `entity prune`).

## Gotchas from the v1.50.0 refine pass (`assist run`)
- **HA has THREE websocket shapes and two of them look identical at the ack.**
  A run-to-completion command (`assist_pipeline/run`) acks with an empty
  `result` exactly like a subscription does. Through `ws_call` it returns
  `None` and CLOSES THE SOCKET, which cancels the run server-side
  (`connection.subscriptions[msg["id"]] = run_task.cancel`) — a command that
  reports success and produces nothing. Through `ws_subscribe` it never
  returns. Use `ws_run_events` and give it a terminal predicate.
- **The ack is not the start.** `run-start` — which carries
  `stt_binary_handler_id` — arrives AFTER the ack. Anything reading the event
  list inside `on_ack` sees an empty list; wait for `run-start`.
- **Binary frames are `handler_id` byte + payload, and the id is 1-based**
  (`index = handler_id - 1`). A wrong first byte is logged server-side and
  answered with nothing at all. The terminating frame is the handler byte
  ALONE — HA reads `while chunk := await audio_queue.get()`, so without it the
  run hangs to timeout.
- **`end` is a valid `PipelineStage` and an invalid argument.** The enum has 5
  members, `PIPELINE_STAGE_ORDER` has 4; `end_stage="end"` clears voluptuous
  then dies on a bare `list.index` ValueError inside `__post_init__`. Restrict
  stage arguments client-side.
- **Do not give the client the same deadline as the server.** HA answers its
  own pipeline timeout with an `error` event then `run-end`. Matching deadlines
  replaces that diagnosis with a local "did not finish"; add a grace margin.
- **`assist_pipeline` cannot load in this environment** — `pyspeex-noise` will
  not build (`pymicro-vad` will). e2e skips on `unknown_command`; the transport
  is instead proven against an aiohttp server that speaks HA's framing
  (`tests/test_ws_run_events.py`). A fake built from the same misunderstanding
  as the client agrees with it — a real second implementation does not.

## Gotchas from the v1.49.0 refine pass
- **Scope a refine by diffing the RUNNING instance, not the docs.** HA's source
  lives at `/usr/src/homeassistant` inside the pod, so a `kubectl exec` walk +
  regex enumerates exactly what this version serves: 304 websocket commands and
  113 REST views on 2026.8.1. Require the `websocket_command(` decorator in
  scope when matching `vol.Required("type")` — without it five energy SOURCE
  kinds (`solar`, `gas`, `battery`, `water`, `grid`) come back as commands.
- **CHECK OUT THE BASE BEFORE STARTING. THIS PASS DID NOT.** Work began on
  whichever branch the checkout happened to be sitting on — a stale `fix-ruff`
  — with no `git fetch` first. Nothing drifted mid-pass: `origin/main` was
  ALREADY 15 commits ahead before the first line was written, including a
  1.48.0 that covered `validate_config`/`test_condition`/`execute_script`/
  `entity/source` as the `action` group and device-class units as `entity
  convertible-units`. Three finished, tested command groups were thrown away
  rather than shipped as duplicates. The fix is one command before any work:
  `git fetch origin && git checkout -b <branch> origin/main`. Describing this
  as "main moved while I worked" is the wrong lesson — it was never looked at.
- **The session sets `Content-Type: application/json`, which breaks every
  multipart upload.** `requests` only generates a multipart boundary header
  when one is not already set, so `upload()` passes `headers={"Content-Type":
  None}` to drop it for that request. Without it HA answers a 400 that says
  nothing.
- **`/api/media_source/local_source/upload` filters by CONTENT TYPE and logs
  the reason server-side only.** It checks `content_type.startswith(("image/",
  "video/","audio/"))` and returns a bare 400; "Content type not allowed"
  appears in HA's log and never in the response. The client guesses the type
  from the filename and `transfer.upload_media` refuses locally.
- **`agent_id` on the backup endpoints is REPEATABLE**
  (`query.getone()`/`getall()`), so it is passed as a list of PAIRS. A missing
  one is a bare 400 with no body — refuse it client-side and name the remedy.
- **Error presentation must not depend on the entry point.** `HomeAssistantError`
  and `ValueError` used to be caught in `main()` alone, so the same failure was
  a clean `error: …` under the console script and an uncaught traceback under
  `python -m`, under an embedding caller, and under CliRunner (where
  `result.output` came back EMPTY). The root group is now `_HandledGroup`.
  Keep new core functions raising `ValueError`, never `KeyError`.
- **A composite-split key is NOT a device id.** `config/device_registry/
  list_composite_splits` returns `{composite_id: {primary_id, split_ids}}`;
  measured, 0 of 51 keys were also a `primary_id` and none of the 102 split ids
  was a key. Look a device up through the reverse index, never as a key.
- **A read-only command must not use `@click.confirmation_option`.** It prompts
  on the read too. `prefs entity-naming` reads with no options and confirms
  inline only when `--set-parts` is given.

## Gotchas
- `homeassistant_cli.py` is one huge file — grep for the command name; new commands go alongside existing siblings. They must be defined **above** the trailing `if __name__ == "__main__": main()` guard: anything after it never registers when the CLI runs as `python -m cli_anything.homeassistant.homeassistant_cli` (the e2e fallback path), because `main()` executes before the rest of the module body.
- Never commit a token: `.gitignore` excludes the connection-profile JSON.
- Sibling family: `cli-anything-zigbee2mqtt`, `cli-anything-espresense` share the profile/JSON/REPL pattern.
