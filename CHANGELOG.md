# Changelog

All notable changes to `cli-anything-homeassistant` are documented here.

The project versions follow semver (MAJOR.MINOR.PATCH).

## [1.51.0] — 2026-08-30

Refine pass scoped by re-enumerating the running version's surface (235
websocket commands, 88 REST views on 2025.1.4) and diffing it against every
string this harness sends. Websocket coverage came back 204/235, and the
remainder belongs to integrations this harness cannot reach (KNX, LCN,
dynalite). **The REST side had a real hole, and it was the one that returns
pixels:** four binary GET views that nothing here called.

### Added — get the BYTES an entity is serving

The harness could describe a camera in complete detail and could not show you
what it sees. `camera capabilities` / `stream` / `prefs-get` read the wiring
and `camera_ws` negotiates WebRTC, but none of them returns an image.
`image snapshot` existed for `image.*` entities only.

- `camera snapshot ENTITY_ID OUTPUT_PATH` — `/api/camera_proxy/<entity_id>`.
  `--width`/`--height` (refused unless BOTH are given, see below),
  `--overwrite`, `--signed`/`--direct`, `--expires`. Reports `resized` — did
  HA actually rescale, not did you ask it to.
- `camera capture ENTITY_ID OUTPUT_DIR` — N distinct frames off
  `/api/camera_proxy_stream/<entity_id>`. `--frames`, `--interval`,
  `--timeout`, `--prefix`, `--overwrite`, `--signed`, `--expires`.
- `image capture ENTITY_ID OUTPUT_DIR` — the same for
  `/api/image_proxy_stream/<entity_id>`, which has no interval.
- `camera proxy-url ENTITY_ID` — signed (default) or plain URL for the still
  or, with `--stream`, the MJPEG view. Mirrors `image proxy-url`.
- `media-player artwork ENTITY_ID OUTPUT_PATH` —
  `/api/media_player_proxy/<entity_id>`: the cover art for what is playing,
  or with `--content-type`/`--content-id` the thumbnail for one node of the
  `media_player browse` tree, whose URLs point straight back at this endpoint.

### Added — `core/media_proxy.py`

One module for all four views, with the transport details that make them
different from every other endpoint in this harness:

- **`requires_auth = False` does not mean unauthenticated.** All three views
  check `request[KEY_AUTHENTICATED]` or a per-entity access token by hand.
  The refusal differs from the rest of the API: with an `Authorization`
  header present HA answers 401, with none at all it answers **403**. A
  signed request therefore has to have the bearer header REMOVED, or a
  signature failure is reported as a token failure.
- **A camera that is off is a 503 with an empty body.** `CameraView.get`
  checks `camera.is_on` before taking a picture. The error now names
  `camera turn-on <entity_id>` instead of repeating a bare status.
- **Bounded capture.** Both streams run forever by design, so handing either
  to `client.download()` writes an infinitely growing file. Every capture is
  limited by a frame budget AND a deadline, and closes the response — which
  is what makes HA stop.
- **Duplicate frames are collapsed.** HA sends the first frame twice
  (camera) or every frame twice (image) because Chrome renders the n-1 frame
  of a multipart stream. Reported as `duplicates_skipped`.
- **Length-driven multipart parsing** rather than boundary-driven, because
  the two views declare incompatible boundaries (see below).

### Fixed — a wire failure in these commands was a traceback, not a message

`_HandledGroup` catches `HomeAssistantError`, `ValueError` and now
`FileExistsError`. The new core functions raise `HomeAssistantError` (which
subclasses `RuntimeError`) rather than a bare `RuntimeError`, so a 404/503/500
from a proxy view is presented as `error: …` from every entry point. Refusing
to clobber an existing file — a normal outcome of any command that writes one,
including the pre-existing `image snapshot` — is now a sentence carrying its
own remedy instead of a stack trace. Caught by the live e2e test, not by
review.

### Tests

+99 (3,885 → 3,984 passing, 30 skipped).

- `tests/test_media_proxy.py` — 50 unit tests: URL and query construction,
  the signed/bearer split, every bodyless status translated, all client-side
  refusals.
- `tests/test_media_proxy_stream.py` — 10 tests against **Home Assistant's own
  stream writer over a real socket**. The camera route calls
  `homeassistant.components.camera.async_get_still_stream` — the actual
  function that serves `/api/camera_proxy_stream` — and the image route is
  built from the image component's own constants. This found two bugs a
  hand-written fixture would have agreed with.
- `tests/test_cli_media_proxy_wiring.py` — 24 CliRunner tests.
- `tests/test_full_e2e.py::TestMediaProxyLive` — 15 tests against a real HA:
  a genuinely HA-minted signed URL (`auth/sign_path` is a core command and
  needs no camera platform), named 404s, and every refusal proven to stop
  before the wire.

## [1.50.0] — 2026-08-27

Refine pass scoped by re-enumerating HA's websocket + REST surface and diffing
it against every string this harness sends. Of the commands still missing,
almost all belong to integrations this harness cannot reach (KNX, LCN, iOS,
Nest, UniFi Protect, Plex, Reolink, hassio/supervisor). **One core command was
missing, and it was the one that makes a voice assistant do anything:**
`assist_pipeline/run`.

### Added — run an Assist pipeline end to end (`assist run`)

The harness could describe a voice assistant in complete detail and could not
make one speak. `assist pipelines` / `pipeline-get` read the wiring, `assist
stt-engines` / `tts-engines` / `wake-words` enumerate the parts, `assist ask`
reaches the conversation agent — but `conversation/process` is ONE stage of
four. It never runs speech-to-text and never invokes the pipeline's own TTS
engine, so the question you actually have after wiring a pipeline together —
*does this pipeline work?* — had no command.

- `assist run [TEXT]` — runs `start_stage` through `end_stage` of a pipeline
  and reports what each stage produced: `stt_text`, `speech`,
  `conversation_id`, `tts_url`, `error`, `completed`.
  - `--start-stage / --end-stage` from `wake_word | stt | intent | tts`
    (default `intent` → `tts`).
  - `--audio FILE` — a 16-bit mono PCM WAV, required by the `stt` and
    `wake_word` start stages, streamed to HA as binary websocket frames.
  - `--save-tts FILE` — download the audio the run produced.
  - `--stream` — print each event as it arrives, on **stderr**, so `--json`
    stdout stays parseable.
  - `--events`, `--pipeline`, `--conversation-id`, `--device-id`,
    `--wake-word-phrase`, `--sample-rate`, `--timeout`.

### Added — a third websocket shape: `ws_run_events`

HA has three shapes of websocket command and this harness only had clients for
two. Request/response (`ws_call`) and open-ended subscription (`ws_subscribe`)
were covered; **run-to-completion** — an empty ack, then events, then the run
ends *on its own* — was not, and neither existing client can fake it:

- through `ws_call` the run returns `None` at the empty ack and **closes the
  socket, which cancels the run server-side** before it produces anything (HA
  registers `connection.subscriptions[msg["id"]] = run_task.cancel`);
- through `ws_subscribe` it never returns, because nothing outside the stream
  knows the run ended.

`HomeAssistantClient.ws_run_events(...)` takes the missing piece — a terminal
condition read from the DATA (`is_terminal`) — and adds an `on_ack(send_binary)`
hook that runs on a daemon thread, which is how audio is pushed into a pipeline
*while* its events arrive. Sending it inline would deadlock the moment HA's
send buffer filled, because nothing would be draining the socket.

### Gotchas measured this pass

- **The ack is not the start.** HA sends the empty `result` and only *then*
  emits `run-start`, which is where `stt_binary_handler_id` lives. A sender
  that reads the collected events straight after the ack finds an empty list
  every time; it has to wait for `run-start`.
- **The binary handler id is 1-based and framed as the first byte.** HA does
  `index = handler_id - 1` against `connection.binary_handlers`, and a wrong
  first byte is answered with a server-side log line and *nothing at all* on
  the wire. The id is never guessed — a `run-start` without one is refused.
- **The empty frame is not optional.** HA's reader is `while chunk := await
  audio_queue.get()`, so a frame carrying the handler byte *alone* is what ends
  the audio stream. Omit it and the run hangs until its timeout.
- **`end` is a valid `PipelineStage` and an invalid argument.** The enum has
  five members; the ordering table `PIPELINE_STAGE_ORDER` has four. Passing
  `end_stage="end"` clears voluptuous and then dies on a bare `list.index`
  ValueError inside `PipelineRun.__post_init__`. Both stage arguments are
  restricted to the four ordered stages client-side.
- **Don't race HA's own timeout.** `--timeout` is the *pipeline's* timeout, and
  HA answers it with an `error` event (code `timeout`) followed by `run-end` —
  an actual diagnosis. The collector therefore gets a 5s grace margin, or a
  local "did not finish" would replace the server's answer.

### Testing

- `tests/test_ws_run_events.py` (12 tests) runs the new transport against a
  **real websocket server** that implements HA's protocol from the other side:
  the `auth_required` handshake, an empty ack, and binary frames decoded as
  `handler = data[0]; payload = data[1:]`. A WAV goes in and the server
  reassembles it byte for byte. Wrong framing hangs or fails there, which is
  precisely what a FakeClient cannot tell you.
- `tests/test_assist_pipeline_run.py` (50) pins payloads, framing, WAV
  validation and the event summary; `tests/test_cli_assist_run_wiring.py` (18)
  pins the CLI options and the clean-error contract; 6 e2e tests.
- **The live e2e test SKIPS here, and that is the honest outcome.**
  `assist_pipeline` requires `pyspeex-noise`, whose wheel does not build in
  this environment, so the test instance never loads the integration and the
  command answers `unknown_command`. The event payload *shapes* were read off
  `components/assist_pipeline/websocket_api.py` and `pipeline.py` and should be
  treated as version-sensitive; the framing was measured and is not.

## [1.49.0] — 2026-08-11

Refine pass scoped by enumerating the WebSocket + REST surface of the RUNNING
2026.8.1 instance (`/usr/src/homeassistant` inside the pod) and diffing it
against every string this harness sends. HA registers **304** websocket
commands and serves **113** REST views; this closes three clusters of the
remainder. Every command below was exercised against that live instance.

*(Method note: matching `vol.Required("type")` finds 309 commands. Requiring
the `websocket_command(` decorator in scope drops five false positives —
`solar`, `gas`, `battery`, `water`, `grid` are energy SOURCE kinds inside a
schema, not commands.)*

*(Overlap note: this was written on a branch that had never been rebased —
1.48.0 had already covered `validate_config`, `test_condition`,
`execute_script`, `entity/source` and device-class units as the `action` group,
`entity source` and `entity convertible-units`. They are NOT duplicated here:
`target source` and a `validate`/`units` group were written, measured, and then
dropped in favour of what 1.48.0 shipped.)*

### Added — what a target actually hits (`target`)

A service call takes an area/device/floor/label and HA expands it. The harness
could send that target and could not ask what it would resolve to.

- **`target extract`** — `extract_from_target`, through HA's own
  `async_extract_referenced_entity_ids`. Returns the referenced entities,
  devices and areas plus **`missing_areas` / `missing_labels` /
  `missing_devices`** — the parts a real service call ignores in silence.
- **`target services` / `triggers` / `conditions`** — the three `*_for_target`
  commands: what can be done with this target. An empty list is a real answer.
- **`target slugify`** — HA's own slugify, asked rather than reimplemented
  (`Living Room — Lamp #2` -> `living_room_lamp_2`).

`expand_group` defaults FALSE on `extract` and TRUE on the other three. That
asymmetry is HA's and is preserved rather than smoothed over.

### Added — getting bytes in and out

The harness could `backup create|list|show|restore` and could not get a backup
**off the box** — the wrong half for the only reason a backup exists.

- **`backup download` / `backup upload`** — the real tarball, streamed to disk
  and pushed back. Verified against a live 195MB backup: 204523520 bytes
  matching HA's `Content-Length`, opening cleanly with `tarfile` and containing
  `backup.json` + `homeassistant.tar.gz`.
- **`file upload`** — `/api/file_upload`, returning the `file_id` a config flow
  wants for a certificate or a keyfile.
- **`media upload` / `image upload`** — into the media library and the
  image_upload integration.
- **`media search` / `media-player search`** — HA's own search instead of
  recursing `browse` client-side.
- **`tts get-url`** — synthesise and return a playable URL without playing it.
- **`intent handle`** — fire an intent by name, skipping the sentence parser,
  which is what separates a sentence-match failure from a handler failure.

New on the client: `download()` (streamed, so a multi-GB backup never lands in
memory) and `upload()` (multipart). Three things had to be read out of HA's
source, each producing an unhelpful failure otherwise:

1. **`agent_id` is required and REPEATABLE** (`query.getone()`/`getall()`), so
   it is passed as a list of PAIRS — a dict cannot express it. A missing one is
   a **bare 400 with no body**, so it is refused client-side with the remedy.
2. **The multipart field name matters for one endpoint and not the other.**
   `/api/file_upload` rejects any part not called `file`; `/api/backup/upload`
   reads the first part whatever it is called.
3. **The media endpoint filters by CONTENT TYPE and logs the reason
   server-side only.** It checks `content_type.startswith(("image/","video/",
   "audio/"))` and answers a bare 400; "Content type not allowed" appears in
   HA's log and never in the response. The client now guesses the type from the
   filename and `media upload` refuses a non-media file locally.

### Added — preferences that explain odd behaviour

- **`labs list|show|set`** — HA 2026 preview features. One of these changes
  behaviour underneath everything else this harness reports and there was no
  way to see it was on. `--create-backup` is explicit because a preview feature
  can migrate storage.
- **`prefs ai-task`** — which AI Task entity serves `generate_data` /
  `generate_image`. A job that reached the wrong model is nearly always this.
- **`prefs http`** — the stored HTTP config and its STABLE/PENDING split. A
  CORS or trusted-proxy change that "did not take" is usually sitting in
  `pending`, unpromoted.
- **`prefs entity-naming` / `prefs auto-entity-id`** — the automatic entity-id
  rule, and what HA WOULD call an entity. Run before renaming.
- **`prefs recorded`** — `recording_disabled_by`. An entity excluded from the
  recorder has no history and no statistics, which every history command here
  would otherwise report as an empty result indistinguishable from a quiet
  entity. Measured: `sun.sun` is disabled by `user` on a real instance.
- **`device-links splits|split-for|linked`** — composite splits and linked
  devices, topology the flat registry cannot show. A device-scoped target
  applies to ONE registry entry, so a split device is a silent partial hit;
  `split-for` names the `siblings` a call would miss.

### Fixed

- **`tts list` reported `supported_languages: []` for every engine.** It read
  the entity attributes, which do not carry the list; HA keeps it on
  `tts/engine/list`. On a real instance that meant printing an empty list next
  to an engine supporting 81 languages. Now merged from the WS command with
  `languages_from` naming the source, falling back to the old behaviour rather
  than raising if that command is absent.
- **A 500 from `/api/tts_get_url` is now caught before it happens.** HA answers
  a bare `500: Internal Server Error` with no body when the engine does not
  declare the language. Measured across four engines:

  | engine | (no language) | `en_GB` | `en-GB` |
  |---|---|---|---|
  | tts.piper | 200 | 200 | 500 |
  | tts.omnivoice | 200 | 500 | 200 |
  | tts.chatterbox_wyoming | 200 | 500 | 200 |
  | tts.google_ai_tts | 200 | 500 | 500 |

  **Omitting `language` works everywhere** — which corrects the belief that a
  missing `language` field causes the 500. What causes it is a string the
  engine does not declare, and there is no rule to infer: piper's 50 languages
  include both `en_GB` and `en-us`, the Wyoming pair declare only `en-GB`, and
  google_ai_tts declares 81 with no British English at all. `tts get-url`
  checks the engine's own list first and names the near matches.
- **Error presentation depended on the entry point.** `HomeAssistantError` and
  `ValueError` were caught in `main()` only, so a core function's validation
  message was a clean `error: …` under the console script and an uncaught
  traceback under `python -m`, under an embedding caller, and under Click's
  CliRunner — where `result.output` came back EMPTY. Handling moved onto the
  root group (`_HandledGroup`), so presentation is a property of the CLI rather
  than of how it was launched. `main()` keeps its own handler for anything
  raised before the group is entered.
- **`media search` on the root is an ERROR, not an empty result.** Measured:
  the root and `media-source://frigate` answer `search_not_supported`,
  `media-source://music_assistant` answers `search_media_failed`, and only
  `media-source://media_source` returns a list. The first is re-raised with the
  scope named and a working one suggested, because HA's own message is two
  words.

### Tests

3193 -> **3238** unit tests across `test_targets.py`, `test_transfer.py`,
`test_prefs_labs.py` and `test_cli_refine_wiring_v4.py`, plus 13 live-instance
tests in `test_full_e2e.py`. All 29 commands were additionally run against the
production 2026.8.1 instance: **29 passed, 0 failed**.

## [1.48.0] — 2026-08-11

### Added — script-engine primitives (`action` group + `entity source`)

The four core `websocket_api` commands that back Home Assistant's automation
and script *editor* were the last big unwrapped surface in `commands.py`:
`execute_script`, `validate_config`, `test_condition` and `entity/source`.
Together they close the authoring loop — until now an agent could only write
an automation blind, save it, and find out from the error log whether HA
accepted it.

New core module `core/script_engine.py` (pure functions, `FakeClient`-testable)
and a new `action` command group:

- **`action run`** — execute an ad-hoc action sequence via WS `execute_script`.
  Runs through HA's script engine rather than a flat REST service call, so the
  run is traced, gets a script context, supports full script syntax
  (`choose`/`repeat`/`delay`/`wait_template`/`stop`) and can collect a
  `response_variable` payload — all without creating a `script.*` entity.
  Input via `--sequence` JSON, `--sequence-file`, or the
  `--service domain.service -t k=v -d k=v` shorthand; `--var k=v` injects
  script variables; `--dry-run` prints the WS payload and sends nothing.
- **`action validate`** — WS `validate_config` on any combination of
  `--triggers` / `--conditions` / `--actions` (each also `-file`). Returns
  HA's own `{valid, error}` verdict per block.
- **`action validate-automation <file>` / `action validate-script <file>`** —
  pre-flight a whole config file before `automation save` / `script save`.
  Legacy singular `trigger:` / `condition:` / `action:` keys are upgraded to
  the plural spelling `validate_config` expects; results are folded into
  `{valid, checked, results, errors}` and the command **exits non-zero when
  invalid**, so it chains: `action validate-automation a.json && automation
  save automation.x a.json --yes`.
- **`action test-condition`** — WS `test_condition`: evaluate a condition
  config against *live* state. A JSON list is evaluated per-item and is
  error-tolerant (one bogus condition reports its error instead of aborting
  the batch, mirroring `entity prune`). `--exit-code` turns a false result
  into exit 1 for shell chaining; `--var k=v` injects variables.
- **`entity source [entity_id]`** — WS `entity/source`: which integration
  actually supplies an entity. This is provenance, not registry — only
  entities whose integration is loaded appear, so a registry entry with no
  source is a strong orphan signal that complements `entity orphans` /
  `entity restored` before an `entity prune`. `--by-integration` groups
  entity ids per integration, `-i <domain>` filters.

### Fixed

- New CLI commands appended to `homeassistant_cli.py` must land **above** the
  `if __name__ == "__main__": main()` guard. Anything defined after it is
  never registered when the CLI is invoked as
  `python -m cli_anything.homeassistant.homeassistant_cli` (the guard runs
  `main()` before the rest of the module body executes) — the e2e suite's
  `_resolve_cli` fallback path. Caught by the new live subprocess tests.

### Tests

- `tests/test_script_engine.py` (71) — every function against `FakeClient`:
  payload shapes, sequence coercion, legacy-key normalization, per-item error
  tolerance, and each `ValueError` guard.
- `tests/test_cli_action_wiring.py` (42) — full CliRunner coverage of the new
  commands: inline vs file input, mutually-exclusive flags, dry-run, exit
  codes on invalid configs / false conditions, plain and `--json` output.
- `tests/test_full_e2e.py` (+18) — live against a real booted HA: a real
  `execute_script` that creates a persistent notification, a real
  `validate_config` rejecting a bogus trigger platform, real `test_condition`
  template evaluation (true → exit 0, false + `--exit-code` → exit 1), real
  `entity/source` cross-checked against the grouped view, and a
  validate → run → verify workflow.
- Suite: 2,910 → 3,041 passing, 0 regressions.

## [1.47.0] — 2026-07-19

### Security
- **`blueprint import`** (`blueprints.import_blueprint`) previously only checked
  that a supplied URL started with `http://`/`https://` before handing it to
  HA's `blueprint/import` WebSocket command — which makes HA itself fetch that
  URL server-side. Nothing stopped it pointing at `http://169.254.169.254/...`
  (a cloud metadata endpoint), `http://localhost:...`, or any RFC1918 private
  address — a classic SSRF (Server-Side Request Forgery). Added
  `_is_internal_host()` (loopback/link-local/private/reserved/unspecified/
  multicast, IPv6-aware, plus bare `localhost`) and reject any import URL
  resolving to one before the WS call is made. Genuine public URLs (GitHub,
  gist, raw file hosts) are unaffected. 9 new tests: 8 parametrized rejection
  cases (`127.0.0.1`, `169.254.169.254`, `localhost`, `10.x`, `::1`, `::`,
  `192.168.x`, `172.16.x`) + 1 confirming a real public URL still passes
  through unchanged.

## [1.46.4] — 2026-07-19

### Fixed
- **`service call`** in plain (non-`--json`) mode printed nothing at all
  when the service response was an empty list — which is exactly what
  many stateless service calls return on success (HA's REST response for
  `rest_command.*`/`shell_command.*`/anything that changes no entity
  state is literally `[]`, the empty "changed_states" array). That made a
  successful call visually indistinguishable from a hang or a silently
  swallowed error. `service_call`'s existing `result if result is not
  None else {"called": ...}` fallback only caught `None`, not `[]`.
  Changed to `result if result else {"called": ...}` so any falsy result
  (`None`, `[]`, `{}`) now falls back to the `{"called": ...}` message,
  while genuinely populated results (e.g. `--return-response` payloads, or
  services that do report `changed_states`) still pass through unchanged.
  Scoped to `service_call` only — `emit()` itself is untouched, since an
  empty list legitimately means "nothing found" for many other commands
  (e.g. `entity list`).

## [1.46.3] — 2026-07-19

### Added
- **`automation delete <entity_id>`** / **`script delete <entity_id>`** —
  proper delete for UI-managed automations/scripts, hitting HA's real
  `DELETE config/automation/config/{id}` / `DELETE config/script/config/
  {object_id}` REST endpoints (the same URL shape `get`/`save` already use,
  just DELETE instead of POST/GET). Previously the only way to remove one
  was the generic `entity remove` (WS `config/entity_registry/remove`),
  which only tears out the registry entry, not the underlying automation/
  script config, and isn't documented as the delete path for these.
  Confirmation-gated like the other destructive verbs (`--yes` to skip the
  prompt when scripted).

## [1.46.2] — 2026-07-04

### Documentation
- Document the `alarmo` command group in the packaged `SKILL.md` — the
  command-group index row and a pitfall note on the destructive sensor/area/
  config writes (weaken a home alarm; `--dry-run`/`--yes`; ghost-sensor
  removal). The 1.46.0 group shipped without its skill-doc entry.

## [1.46.1] — 2026-07-04

### Fixed
- `render_template` (frontend-prefs / template-preview path) posted to
  `api/template`, which the backend's `_url()` double-prefixed to
  `/api/api/template` — the render request never hit HA's real
  `/api/template` endpoint. Corrected to `client.post("template", …)`,
  matching `core/template.py`. Tests updated (they had asserted the
  double-prefixed path, so the bug stayed green).

## [1.46.0] — 2026-07-04

New **`alarmo`** group: full CLI coverage for the [Alarmo](https://github.com/nielsfaber/alarmo)
custom integration (HACS alarm system). Alarmo exposes three API surfaces —
the `alarmo` domain services, WebSocket reads (`alarmo/config`,
`alarmo/areas`, …), and REST writes (`/api/alarmo/*`) — all now wrapped.

### Added
- **`alarmo arm <entity>`** — call the `alarmo/arm` service with `--mode`
  (away/night/home/vacation/custom), `--code`, `--skip-delay`, `--force`.
- **`alarmo disarm <entity>`** — `alarmo/disarm` service with `--code`,
  `--skip-delay`.
- **`alarmo enable-user <name>`** / **`alarmo disable-user <name>`** —
  grant/revoke arm/disarm permissions for an Alarmo user.
- **`alarmo config`** — read Alarmo's global config via the `alarmo/config`
  WS command (code requirements, MQTT, master, ...).
- **`alarmo config-set --data-json`** — partial config update via the
  `/api/alarmo/config` REST view. Destructive — `--dry-run` previews the
  body, `--yes` skips confirmation (required non-TTY).
- **`alarmo areas`** / **`alarmo area-create`** / **`alarmo area-delete`** —
  list, create/rename, and delete Alarmo areas (the `alarmo/areas` WS read +
  `/api/alarmo/area` REST write). `area-delete` is destructive: `--dry-run`
  previews, `--yes` skips confirmation.
- **`alarmo sensor-show <entity>`** — read one sensor's full Alarmo config
  via the `alarmo/sensors` WS command. Validates `binary_sensor.*` /
  `sensor.*` entity domain.
- **`alarmo sensor-remove <entity>`** — remove a sensor from Alarmo via
  `POST /api/alarmo/sensors {"entity_id":..., "remove": true}`. The
  original use case: removing a dead/ghost sensor that no longer exists in
  HA but still blocks arming. Safety: `--dry-run` previews the REST body,
  `--yes` skips confirmation; in a TTY without `--yes` it prints the
  sensor's current config first, then prompts naming the entity and effect.
- **`alarmo sensor-update <entity>`** — update fields on an Alarmo sensor
  via `POST /api/alarmo/sensors`. Typed flags: `--type`
  (door/window/motion/tamper/environmental/other), `--modes`
  (comma-separated armed_away/armed_home/armed_night/armed_vacation/
  armed_custom_bypass), `--allow-open`/`--no-allow-open`,
  `--always-on`/`--no-always-on`, `--auto-bypass`/`--no-auto-bypass`,
  `--trigger-unavailable`/`--no-trigger-unavailable`,
  `--arm-on-close`/`--no-arm-on-close`, `--area`, `--enabled`/`--disabled`,
  `--group`. Only fields the user actually passed on the command line are
  sent (Click `ParameterSource` detection) — unset fields are never
  clobbered. Same `--dry-run` / `--yes` / TTY-confirm safety as
  `sensor-remove`.
- **`alarmo sensors`** / **`alarmo users`** / **`alarmo automations`** /
  **`alarmo sensor-groups`** / **`alarmo entities`** — five WS-backed list
  readers for Alarmo's internal registries.
- New core module `cli_anything/homeassistant/core/alarmo.py` (pure
  functions, one per operation, callable from Python directly).
- 93 unit tests covering core functions + CLI wiring + safety guards
  (`tests/test_alarmo.py`).

## [1.45.0] — 2026-06-24

### Added
- `automation trace` / `script trace`: accept the **run_id positionally**
  (`automation trace <entity> <run_id>`, matching `traces` output) in addition to
  `--run-id`, and a new **`--vars`** flag that flattens the trace to per-step
  changed variables + service calls — the `line`/`description`/`say`/persona
  values and the notify/tts/script calls — instead of forcing a hand-dig of the
  deeply-nested `trace[step][].changed_variables` / `result.params`.

## [1.44.0] — 2026-06-20

Gap surfaced while migrating the Haier hOn integration off the dead
`Andre0512/hon` onto a maintained fork: the `hacs` group could `install`/
`remove`/`refresh` but had **no way to register a custom repository**, forcing a
hand-rolled `hacs/repositories/add` WebSocket call.

### Added
- **`hacs add <owner/repo> [--category]`** — register a custom repository (the
  frontend's "Custom repositories" dialog) via the `hacs/repositories/add` WS
  command. `install` only works on repos HACS already knows, so a brand-new
  fork must be added here first. Validates the `owner/repo` slug and the
  category (`integration` default; also `plugin`/`theme`/`appdaemon`/
  `python_script`/`netdaemon`/`template`). Typical flow:
  `hacs add owner/repo` → `hacs refresh owner/repo` → `hacs install owner/repo`.
  Note HACS's own API is plural for `repositories/list` + `repositories/add`
  but singular (`repository/*`) for everything else.

## [1.43.0] — 2026-06-12

Gaps surfaced during a long session building a switchable HA TTS-persona
(input_select + script + multi-voice Wyoming). Three friction points fixed.

### Added
- **`helpers input-select update`** — PERSISTENT option/name/icon/initial edit
  via the `input_select/update` storage-collection WS command. Unlike
  `set-options` (the `input_select.set_options` *service*, runtime-only — it
  silently reverts on HA restart), this survives restart. The wrapper was
  missing even though the `input_select_update` core fn already existed.
- **`ws <type>`** — raw WebSocket escape hatch. Sends any WS command with a
  payload built from repeatable `-D key=value` (JSON-parsed) and/or
  `--data-json`, handling the connect/auth/`id` handshake. Covers WS commands
  that have no dedicated subcommand (storage-collection updates, niche calls).

### Fixed
- **No more Python traceback on a wrong-domain entity.** Typed-group commands
  (e.g. `select set input_select.foo`) raise `ValueError` from the core
  domain-prefix check; `main()` only caught `HomeAssistantError`, so it dumped
  a raw traceback. It now catches `ValueError` too and prints a clean
  `error: expected select.* entity_id, got 'input_select.foo'`.
- **`input_select_update` options-only update no longer rejected.** HA's
  `input_select/update` REPLACES the whole item and *requires* `name`, so an
  options-only update failed with `required key not provided @ data['name']`.
  It now backfills `name`/`icon` from the current state when omitted, so you
  can change just the options.

## [1.42.0] — 2026-06-03

Safe powercalc **group membership** editing. A 2026-06-02 session migrated 30
spotlights linear→fixed by delete+recreate and silently lost them from their
area + energy rollups: the recreate didn't re-add them, a repair via the old
`add_group_members` wrote the *resolved leaf list* back into the wrong field
and never persisted across a restart, and nothing ever touched the energy
side. This release rebuilds the group wrappers so that can't happen, and
restores the rollups.

### Fixed
- **`get_group_config` reads the configured lists correctly.** The current
  values live under each form field's `description.suggested_value`; the old
  code read the top-level `suggested_value`/`default`, which powercalc leaves
  empty here, so reads silently came back blank. `read_entry` had the same bug
  and is fixed too.
- **Writes preserve every field you don't touch.** The group `group_custom`
  form clears any optional field you omit, so setting only the energy list used
  to blank the member/power lists. `set_group_members` now reads the current
  config and resends all membership fields (member_sensors, power, energy,
  sub_groups) plus area/floor, mutating only what you asked.
- **Writes are reloaded and read-back-verified.** An options-flow
  `create_entry` doesn't guarantee the entry reloaded, so a membership could
  read correct in-session yet evaporate on the next HA restart. Writers now
  reload the entry and re-read the stored config, raising if it didn't persist.
- **Power and energy roll up together.** `add_group_members` /
  `set_group_members` take `energy_entities` alongside `power_entities`, and
  `member_sensors` (powercalc config-entry ids) rolls up both automatically.

### Added
- **`powercalc group config <entry>`** — show a group's configured membership
  lists (the editable source of truth), distinct from `group members` (the
  resolved leaf list a group power sensor actually sums).
- **`powercalc group groups-of`** — list every group whose config references a
  given member/sensor: the snapshot a safe delete+recreate restores from.
- **`energy_siblings_for` / `find_groups_containing` /
  `recreate_preserving_groups`** — helpers to derive a power sensor's matching
  energy sensor, discover a member's groups, and (because powercalc's options
  flow exposes no in-place mode change) wrap a `linear→fixed` delete+recreate
  with snapshot→delete→recreate→restore so the round-trip can't strip rollups.

### Changed
- `powercalc group add-members` / `remove-members` now take `--member`
  (config-entry id), `--power-entity`, and `--energy-entity` instead of the old
  `--sensor` + `--member` (power-only) form, and reload + verify by default
  (`--no-verify` to skip). `set-members` likewise gained `--member` /
  `--energy-entity`.

## [1.41.0] — 2026-06-02

Powercalc editing gaps exposed while setting a lamp's standby power. The only
way to set off-state power on an existing entry was hand-driving the options
flow; there was no way to read an entry's configured options back; and
`set-power` could be silently shadowed by a stale template.

### Added
- **`powercalc set-standby <entry> <watts>`** — set the OFF-state
  `standby_power` on an existing virtual_power entry. It lives on the
  `basic_options` step (not `fixed`), so `set-power`/`set-template` never
  reached it. The source `entity_id` is auto-resolved and re-sent so the
  submit can't blank the entry's source (`--source` to override). Pairs with
  `set-power`: on-state W vs off-state W.
- **`powercalc show <entry>`** — read an entry's live + configured state
  (`calculation_mode`, `source_entity`, current W, and best-effort
  `power`/`power_template`/`standby_power`). The config-entry list doesn't
  expose powercalc options; previously you had to infer them from the sensor.

### Changed / fixed
- **`set-power` now clears any stale `power_template`** before writing the
  constant — powercalc gives a template precedence over the fixed value, so a
  leftover template silently shadowed the new number.
- **`set-power` / `set-template` now auto-reload the entry** after writing
  (`reload=False` to skip) so the change lands on the sensor immediately — an
  options-flow `create_entry` didn't always reload on its own, the usual
  reason a freshly-written value "didn't take".

## [1.40.0] — 2026-06-02

Noise rejection for the **active** powercalc calibrators (`calibrate`,
`calibrate-template`). Previously they computed `delta = load − baseline`
against the whole-home smart meter and blindly trusted the device under test
was the only thing moving — so a kettle/microwave/another light switching
mid-window silently poisoned the result. Now each measurement window is
gated two ways and re-measured (then excluded) if either trips:

### Added
- **Variance gate** — rejects a window whose spread (max − min) exceeds
  `--max-variance-w` (default 50 W). Catches large spikes from **untracked**
  loads (no powercalc profile, no native sensor) — they show up as a blown
  spread on the whole-home meter.
- **Confounder watch** — before/after each window we snapshot OTHER tracked
  devices and reject the window if any moved:
  - source entities of other **powercalc** profiles (discrete on/off/bright
    state change), and
  - **natively-metered** entities (`device_class: power`, non-powercalc) whose
    value moves beyond a 5 W epsilon.
  Catches a neighbour toggling even when its draw is too small to trip the
  variance gate.
- `--max-variance-w` / `--max-retries` flags on both commands (set
  `--max-variance-w 0` to disable the gate — legacy behaviour).
- New result fields: `calibrate` → `noisy`; `calibrate-template` →
  `baseline_noisy`, `excluded_steps`, and per-step `spread`/`attempts`/
  `excluded`/`confounder`. Each measurement carries `spread`/`stdev`/
  `attempts`/`accepted`/`confounder`.

### Changed
- A noisy run **never auto-applies**: `calibrate` skips the write when
  `noisy`; `calibrate-template` fits the template only from clean steps and
  refuses to apply on a poisoned baseline.

## [1.39.0] — 2026-05-29

Safety + correctness refine. The headline change: most v6-listed agent
footguns are now closed. `whoami` no longer crashes, WS subscriptions don't
leak server-side state on exit, lovelace card writes auto-validate before
posting, and every destructive verb now accepts `--yes` for non-interactive
use. Plus 17 previously library-only modules got CLI surfaces.

### Fixed — bugs that would burn an agent

- **`whoami` was broken at runtime.** It called `auth_core.current_user`
  which doesn't exist; the real implementation is in
  `auth_tokens_core.current_user`. Every cold-start agent that followed
  SKILL.md hit `AttributeError`. Now wired correctly + smoke-tested.
- **WS subscriptions leaked server-side ids on exit.** `ws_subscribe()`
  closed the socket without sending `unsubscribe_events`, so Ctrl-C'd
  `event subscribe` / `state watch` / `mqtt subscribe` left the HA
  server tracking dangling subscriptions until the next restart. Now
  unsubscribes before close. Backend: `utils/homeassistant_backend.py`.
- **`entity prune --protect-user-disabled` was bypassed by `--entity-id`.**
  The early-return branch for explicit entity lists skipped the safety
  filter loop, so a typo deleted a user-disabled entry despite the flag.
  Now honored in both branches. CLI: `entity_prune` at homeassistant_cli.py.
- **`mqtt subscribe --limit 0 --out FILE` grew memory unboundedly.** The
  in-memory `seen[]` buffer was populated even when messages streamed to
  a file. Now skips the buffer in streaming-only mode; the final JSON
  emit reports `{"streamed_only": true, "received": N}` instead of the
  message array.
- **`project.save_config()` had a token-write race.** It wrote the JSON
  then `chmod 0o600`'d it — a permissive umask left the token briefly
  world-readable. Now uses `os.open(O_CREAT, mode=0o600)` so the file is
  never less than 0600.

### Changed — safety / correctness

- **`automation save` / `script save` no longer silently overwrite.**
  Both gain `--dry-run` (prints a unified diff vs the live config) and
  `--yes` (skips the new interactive prompt). Without either, the command
  prompts; without a TTY, it aborts.
- **`lovelace card insert` and `card delete` gain `--dry-run`.** Matches
  `card replace` which already had it.
- **`lovelace config save` requires `--yes` when scripted.** Adds
  `--dry-run` (full unified diff vs live dashboard) and `--yes`
  (skips prompt). Wholesale dashboard overwrite is destructive — typos
  here wipe entire dashboards.
- **`lovelace_card_validate` is now wired** (was implemented + tested
  but never called). `lovelace card insert`, `card replace`,
  `section set`, `view set`, `view add` all run the validator first
  and refuse the write on `error`-severity issues. Pass `--no-validate`
  to bypass (e.g. when the HACS plugin will be installed later).
- **Four destructive verbs gain confirmation prompts** (Click
  `@confirmation_option`, accepts `--yes` to skip): `shopping-list
  remove`, `shopping-list clear-completed`, `todo remove`,
  `todo clear-completed`.
- **`system reload-core-config` and `system reload-all` gain
  confirmation prompts.** They're mutating; match the pre-existing
  `system restart` / `system stop` pattern.

### Added — surface

- **`state delete <entity_id>`** wires the long-documented but never-
  implemented `DELETE /api/states/<entity_id>` (HOMEASSISTANT.md and
  SKILL.md both promised it). Tears an entity out of the state machine
  without touching the registry. Confirmation-gated.
- **`tag create` and `tag delete`.** Tags went from list/find/update
  only to full CRUD (`tag/create` and `tag/delete` WS namespaces).
- **`event subscribe --filter 'key.path=value'`.** Repeatable client-
  side filter that runs after HA's server-side event_type filter.
  SKILL.md already documented it; now implemented.
- **`history` flags `--no-attributes` and `--significant-changes-only`.**
  HA's REST API supports both — exposes the size/speed knobs to agents
  hitting big installs.
- **`_TOGGLABLE_DOMAINS` covers 5 more domains**: `valve`,
  `lawn_mower`, `lock`, `alarm_control_panel`, `group`. Means the
  generic `domain turn-on valve.x` now works.
- **17 previously-unwired core modules now have CLI surfaces** (sprint
  artifacts that landed code without wiring): `backup_advanced`
  (subgroup), `calendar_ws`, `diagnostics_dl`, `entity_registry_extras`,
  `frontend_prefs`, `network`, `energy_advanced`, `statistics_admin`,
  `helper_previews`, `history_ext`, `history_logbook` (the
  `history_during_period` WS path that bypasses the REST "first 24h
  only" gotcha), `lovelace_layout_lint`, `lovelace_sections_ext`,
  `lovelace_views`, `state_stream`, `trace_debug`, `trace_debugger`.

### Changed — internals

- **`backend.HomeAssistantClient.post()` and `.delete()` now accept
  `params=`.** `core/services.py::call_service` switched from a hand-
  built `?return_response` suffix to `params={"return_response": "true"}`.
- **`backend.HomeAssistantClient.ws_subscribe()` sends
  `unsubscribe_events` on exit** (see Fixed above).

### Docs

- **README.md**: corrected env var names from `CLI_HA_URL`/`CLI_HA_TOKEN`
  (didn't exist) to the actual `HASS_URL`/`HASS_TOKEN`/`HASS_VERIFY_SSL`/
  `HASS_TIMEOUT`. Also flagged the 0600 profile mode.
- **HOMEASSISTANT.md**: dropped `pyyaml` from the dependencies list
  (not installed, not imported).
- **SKILL.md**: documented the new safety surface, the 17 newly-wired
  command groups, and the `--no-validate` escape hatch.

### Tests

- **`tests/test_v6_refine_fixes.py`** — 41 new regression tests covering
  every behaviour change above: whoami fix, WS unsubscribe, entity
  prune safety, mqtt buffer, project.py file perms, automation/script
  save `--dry-run`/`--yes`, lovelace card insert/delete `--dry-run`,
  lovelace validation wiring, lovelace config save `--yes` gate,
  shopping-list/todo confirmation, system reload confirmation,
  `state delete` wiring, new toggleable domains, `tag create`/`delete`,
  services params, history flags, `event subscribe --filter`.
- **`tests/test_v6_core_coverage.py`** — 26 new tests for previously-
  untested core modules: `groups`, `lovelace_mirror` (pure-Python
  paths), `mqtt_discovery`, `template_helpers` (validation paths),
  `watch`, `_ws_subscribe_utils`.
- **`tests/conftest.py::FakeClient`**: `post()` and `delete()` now
  accept `params=` to match the real backend signature change.
- Existing tests adjusted for the new confirmation prompts (added
  `--yes` where appropriate) and the new params-shape on services
  return_response.
- **2024 tests pass** (was 1957 before the refine, +67 v6 fixtures).
  4 skipped (real-HA fixtures), 0 failures.

## [1.38.0] — pre-refine

(See git log for prior changes.)
