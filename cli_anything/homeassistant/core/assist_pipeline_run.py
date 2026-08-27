"""Run an Assist pipeline end to end — `assist_pipeline/run`.

THE GAP THIS CLOSES
    The harness could describe a voice assistant in complete detail and could
    not make one speak. `assist pipelines` / `pipeline-get` read the wiring,
    `assist stt-engines` / `tts-engines` / `wake-words` enumerate the parts,
    `assist languages` says what it understands, `assist ask` reaches the
    conversation agent — but `conversation/process` is ONE stage of four. It
    skips speech-to-text entirely, it never invokes the pipeline's configured
    TTS engine, and its answer is the agent's, not the pipeline's. So the
    question an operator actually has after wiring a pipeline together —
    "does this pipeline work?" — had no command. `assist_pipeline/run` is
    that command, and it is the only way to exercise a pipeline's own stage
    chain without a physical satellite in the room.

WHY THIS NEEDED A NEW TRANSPORT
    `assist_pipeline/run` acks with an EMPTY result and then streams events
    until the run completes on its own. `ws_call` returns at that empty ack
    and closes the socket, which cancels the run before it does anything;
    `ws_subscribe` never returns because nothing outside the stream knows the
    run ended. Both would have shipped a command that reports success and
    produces nothing. The run therefore goes through
    `HomeAssistantClient.ws_run_events`, which treats `run-end` as the
    terminal event.

WHAT THE STAGES MEAN, AND WHICH ONES TAKE AUDIO
    A pipeline is `wake_word -> stt -> intent -> tts`, and a run names the
    slice of it to execute. The first two consume audio, which arrives as
    BINARY websocket frames rather than in the command payload:

      * `--start-stage intent` (the default) takes `--text` and needs no audio.
        `intent -> tts` is the useful smoke test: the pipeline's own agent
        answers and the pipeline's own TTS engine renders it.
      * `--start-stage tts` takes `--text` and only speaks it.
      * `--start-stage stt` and `wake_word` require `--audio`, a 16-bit mono
        PCM WAV. HA resamples anything that is not 16 kHz itself, so the file's
        own rate is declared and sent as-is.

    Audio is framed exactly the way HA's websocket API demands: one binary
    message per chunk whose FIRST BYTE is the `stt_binary_handler_id` handed
    out in the `run-start` event, followed by an empty-payload frame (the
    handler byte alone) to close the stream. HA's reader is
    `while chunk := await audio_queue.get()`, so the empty frame is not
    optional — without it the pipeline waits for more audio until the run
    times out.

`end` IS A VALID PipelineStage AND AN INVALID ARGUMENT
    HA's `PipelineStage` enum has five members and its ordering table
    `PIPELINE_STAGE_ORDER` has four; `end` is missing from the table. Passing
    `end_stage="end"` therefore passes voluptuous and then dies on a bare
    `list.index` ValueError inside `PipelineRun.__post_init__`, which reaches
    the client as an unexplained failure. Both stage arguments are restricted
    to the four ordered stages here, and the ordering is checked locally so a
    reversed pair is refused by name instead of by traceback.

MEASURED AGAINST THE SOURCE AND A PROTOCOL FAKE, NOT A LIVE PIPELINE — SAY SO
    Every payload key, the binary framing, the event names and the terminal
    condition were read off `components/assist_pipeline/websocket_api.py`,
    `pipeline.py` and `components/websocket_api/http.py`. They were NOT run
    against a live voice pipeline: `assist_pipeline` requires
    `pyspeex-noise`, whose wheel does not build in this environment, so the
    e2e instance cannot load the integration at all. The transport is instead
    exercised against a websocket server that speaks HA's framing byte for
    byte, and the e2e test skips cleanly on `unknown_command` rather than
    pretending. Treat the event payload SHAPES as version-sensitive; the
    framing is not.

WHAT IS DELIBERATELY NOT HERE
    * Live microphone capture. Choosing an input device, a sample format and
      a VAD is an audio application, not a CLI flag, and it would put a
      PortAudio build between this harness and every other command it ships.
      A WAV file is the same bytes with a reproducible test.
    * `assist_pipeline/device/capture`, already shipped as
      `assist-satellite capture` — that records what a satellite HEARS. This
      runs a pipeline. Two different questions.
"""

from __future__ import annotations

import threading
import wave
from typing import Any, Callable, Iterator, Optional

#: HA's `PIPELINE_STAGE_ORDER` — the four stages that can be named as a start
#: or an end. `PipelineStage.END` ("end") is deliberately absent; see above.
STAGES: tuple[str, ...] = ("wake_word", "stt", "intent", "tts")

#: Stages that read their input from binary websocket frames.
AUDIO_STAGES: tuple[str, ...] = ("wake_word", "stt")

#: The event that ends a run. `error` does NOT end it — HA emits the error and
#: still follows it with `run-end`.
TERMINAL_EVENT = "run-end"

#: Bytes per binary frame. 4 KiB is 128 ms at 16 kHz/16-bit/mono: small enough
#: that a VAD sees speech start promptly, large enough not to make a websocket
#: frame per 10 ms chunk.
CHUNK_BYTES = 4096

#: How long the audio sender waits for `run-start` (and with it the handler id)
#: before giving up. This is a local handshake, not a pipeline stage: if HA has
#: acked, `run-start` is the very next message it sends.
HANDLER_WAIT_SECONDS = 10.0

#: Added to the caller's `timeout` for the COLLECTOR only, so HA's own timeout
#: error arrives before the client stops listening for it.
TIMEOUT_GRACE_SECONDS = 5.0


def _stage_index(name: str, label: str) -> int:
    if name not in STAGES:
        raise ValueError(
            f"{label} must be one of {', '.join(STAGES)} (got {name!r}). "
            "'end' is a PipelineStage in HA but has no position in its stage "
            "ordering, so it fails inside the server rather than as an answer."
        )
    return STAGES.index(name)


def read_wav(path: str) -> dict:
    """Read a 16-bit mono PCM WAV and return its frames plus its sample rate.

    Refuses anything HA's `stt` metadata cannot describe. HA declares the
    stream as PCM/16-bit/mono and resamples the RATE itself, so the rate is
    reported rather than rejected — but a stereo or 8-bit file would be
    silently misread as garbage audio and transcribed as nothing, which is
    the failure that looks like a broken pipeline.
    """
    try:
        with wave.open(path, "rb") as wav:
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
    except FileNotFoundError as exc:
        raise ValueError(f"audio file not found: {path}") from exc
    except wave.Error as exc:
        raise ValueError(
            f"{path} is not a readable WAV file ({exc}). "
            "Convert with: ffmpeg -i in.mp3 -ac 1 -ar 16000 -sample_fmt s16 out.wav"
        ) from exc

    problems = []
    if channels != 1:
        problems.append(f"{channels} channels (need mono)")
    if width != 2:
        problems.append(f"{width * 8}-bit samples (need 16-bit)")
    if problems:
        raise ValueError(
            f"{path} has {' and '.join(problems)}. Home Assistant's pipeline "
            "input is 16-bit mono PCM. Convert with: "
            f"ffmpeg -i {path} -ac 1 -ar 16000 -sample_fmt s16 out.wav"
        )
    if not frames:
        raise ValueError(f"{path} contains no audio frames")
    return {
        "pcm": frames,
        "sample_rate": rate,
        "bytes": len(frames),
        "seconds": round(len(frames) / (rate * 2), 3),
    }


def iter_chunks(pcm: bytes, chunk_bytes: int = CHUNK_BYTES) -> Iterator[bytes]:
    """Split raw PCM into websocket-sized chunks."""
    if chunk_bytes < 1:
        raise ValueError("chunk_bytes must be positive")
    for offset in range(0, len(pcm), chunk_bytes):
        yield pcm[offset : offset + chunk_bytes]


def binary_handler_id(events: list[dict]) -> Optional[int]:
    """Pull `stt_binary_handler_id` out of the `run-start` event.

    HA allocates the handler per run and reports it once. It is 1-based: the
    server subtracts one to index `connection.binary_handlers`, so a 0 first
    byte is rejected as a non-existing handler and logged server-side only.
    """
    for event in events or []:
        if isinstance(event, dict) and event.get("type") == "run-start":
            runner = (event.get("data") or {}).get("runner_data") or {}
            handler = runner.get("stt_binary_handler_id")
            if isinstance(handler, int):
                return handler
    return None


def summarize(events: list[dict]) -> dict:
    """Reduce a run's event stream to what each stage produced.

    Keys are present and `None` when the stage did not run, so a caller can
    tell "the pipeline stopped before TTS" from "TTS produced nothing".
    """
    out: dict[str, Any] = {
        "stages": [],
        "wake_word": None,
        "stt_text": None,
        "intent_response": None,
        "speech": None,
        "conversation_id": None,
        "tts_url": None,
        "tts_media_id": None,
        "tts_mime_type": None,
        "error": None,
        "completed": False,
        "pipeline": None,
        "language": None,
    }
    for event in events or []:
        if not isinstance(event, dict):
            continue
        etype = event.get("type")
        data = event.get("data") or {}
        out["stages"].append(etype)
        if etype == "run-start":
            out["pipeline"] = data.get("pipeline")
            out["language"] = data.get("language")
        elif etype == "run-end":
            out["completed"] = True
        elif etype == "wake_word-end":
            out["wake_word"] = (data.get("wake_word_output") or {}).get("wake_word_id")
        elif etype == "stt-end":
            out["stt_text"] = (data.get("stt_output") or {}).get("text")
        elif etype == "intent-end":
            intent = data.get("intent_output") or {}
            out["intent_response"] = intent.get("response")
            out["conversation_id"] = intent.get("conversation_id")
            speech = ((intent.get("response") or {}).get("speech") or {}).get("plain") or {}
            out["speech"] = speech.get("speech")
        elif etype == "tts-end":
            tts = data.get("tts_output") or {}
            out["tts_url"] = tts.get("url")
            out["tts_media_id"] = tts.get("media_id")
            out["tts_mime_type"] = tts.get("mime_type")
        elif etype == "error":
            out["error"] = {"code": data.get("code"), "message": data.get("message")}
    return out


def run(
    client,
    *,
    text: Optional[str] = None,
    audio_path: Optional[str] = None,
    start_stage: str = "intent",
    end_stage: str = "tts",
    pipeline: Optional[str] = None,
    conversation_id: Optional[str] = None,
    device_id: Optional[str] = None,
    wake_word_phrase: Optional[str] = None,
    sample_rate: Optional[int] = None,
    timeout: Optional[float] = None,
    include_events: bool = False,
    on_event: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Run one Assist pipeline from `start_stage` through `end_stage`.

    Returns the stage-by-stage summary; the raw event list is attached as
    `events` only when `include_events` is set, because a wake-word run emits
    one event per VAD transition and drowns the answer.
    """
    start_idx = _stage_index(start_stage, "start_stage")
    end_idx = _stage_index(end_stage, "end_stage")
    if end_idx < start_idx:
        raise ValueError(
            f"end_stage {end_stage!r} comes before start_stage {start_stage!r} "
            f"in HA's pipeline order ({' -> '.join(STAGES)})"
        )

    payload: dict[str, Any] = {"start_stage": start_stage, "end_stage": end_stage}
    if pipeline:
        payload["pipeline"] = pipeline
    if conversation_id:
        payload["conversation_id"] = conversation_id
    if device_id:
        payload["device_id"] = device_id
    if timeout:
        payload["timeout"] = float(timeout)

    audio: Optional[dict] = None
    if start_stage in AUDIO_STAGES:
        if not audio_path:
            raise ValueError(
                f"start_stage {start_stage!r} reads its input from audio; "
                "pass audio_path (a 16-bit mono PCM WAV)"
            )
        if text:
            raise ValueError(
                f"start_stage {start_stage!r} takes audio, not text; drop text or start at 'intent'"
            )
        audio = read_wav(audio_path)
        rate = int(sample_rate or audio["sample_rate"])
        payload["input"] = {"sample_rate": rate}
        if start_stage == "stt" and wake_word_phrase:
            payload["input"]["wake_word_phrase"] = wake_word_phrase
    else:
        if audio_path:
            raise ValueError(
                f"start_stage {start_stage!r} takes text, not audio; "
                "use --start-stage stt to transcribe a file"
            )
        if wake_word_phrase:
            raise ValueError("wake_word_phrase only applies to start_stage 'stt'")
        if not text:
            raise ValueError(f"start_stage {start_stage!r} requires text")
        payload["input"] = {"text": text}

    collected: list[dict] = []
    started = threading.Event()

    def _record(event) -> None:
        if isinstance(event, dict):
            collected.append(event)
            if event.get("type") == "run-start":
                started.set()
        if on_event is not None:
            on_event(event)

    on_ack = None
    if audio is not None:
        pcm = audio["pcm"]

        def on_ack(send_binary) -> None:  # noqa: F811
            # THE ACK IS NOT THE START. HA sends the empty `result` and only
            # then emits `run-start`, which is where the handler id lives — so
            # the sender thread has to wait for it. Reading `collected`
            # straight away finds an empty list every time.
            if not started.wait(HANDLER_WAIT_SECONDS):
                raise ValueError(
                    "pipeline acked but never emitted run-start within "
                    f"{HANDLER_WAIT_SECONDS}s; no audio was sent"
                )
            handler = binary_handler_id(collected)
            if handler is None:
                # A run-start without a handler id means HA did not open an
                # audio channel for this run. Guessing a first byte would put
                # the audio into another handler or into a server-side log
                # line, never into an error the caller can see.
                raise ValueError(
                    "pipeline did not report an stt_binary_handler_id in its "
                    "run-start event; refusing to guess where to send audio"
                )
            prefix = bytes([handler])
            for chunk in iter_chunks(pcm):
                send_binary(prefix + chunk)
            # Empty payload = end of stream. HA's reader stops on a falsy chunk.
            send_binary(prefix)

    # THE TRANSPORT MUST OUTLIVE THE SERVER'S OWN CLOCK. `timeout` is HA's
    # pipeline timeout, and HA answers it with an `error` event (code
    # `timeout`) followed by `run-end` — an actual diagnosis. Giving the
    # collector the same deadline would race that answer and replace it with a
    # local "did not finish", so the transport gets a grace margin.
    transport_timeout = (float(timeout) + TIMEOUT_GRACE_SECONDS) if timeout else None

    events = client.ws_run_events(
        "assist_pipeline/run",
        payload,
        is_terminal=lambda event: isinstance(event, dict) and event.get("type") == TERMINAL_EVENT,
        timeout=transport_timeout,
        on_ack=on_ack,
        on_event=_record,
    )

    result = summarize(events)
    result["start_stage"] = start_stage
    result["end_stage"] = end_stage
    if audio is not None:
        result["audio"] = {
            "path": audio_path,
            "bytes": audio["bytes"],
            "seconds": audio["seconds"],
            "sample_rate": int(sample_rate or audio["sample_rate"]),
        }
    if include_events:
        result["events"] = events
    return result


def save_tts(client, url: str, dest: str) -> dict:
    """Download the audio a run produced, from the `tts_output.url` it reported.

    HA returns a SITE-RELATIVE url (`/api/tts_proxy/...`); the client's
    `download()` joins it to the configured base, so the token that authorises
    the rest of the session authorises this too.
    """
    if not url:
        raise ValueError("no tts url — the run did not reach the tts stage")
    if not dest:
        raise ValueError("dest is required")
    return client.download(url.lstrip("/"), dest)
