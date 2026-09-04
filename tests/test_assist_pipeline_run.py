"""Unit tests for `assist_pipeline/run` — core/assist_pipeline_run.py.

The wire payloads, the binary framing and the terminal event are pinned here
against `FakeClient`; `tests/test_ws_run_events.py` proves the same framing
against a websocket server that speaks HA's protocol for real.
"""

from __future__ import annotations

import struct
import wave

import pytest

from cli_anything.homeassistant.core import assist_pipeline_run as apr
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError


# ───────────────────────────────────────────────────────────────── helpers

def _wav(path, *, seconds=0.25, rate=16000, channels=1, width=2):
    frames = int(rate * seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        if width == 2:
            wav.writeframes(struct.pack("<" + "h" * frames * channels,
                                        *([1000] * frames * channels)))
        else:
            wav.writeframes(bytes([128]) * frames * channels * width)
    return str(path)


def _events(*, handler=1, stt=None, speech="ok", tts_url="/api/tts_proxy/x.mp3"):
    evts = [{
        "type": "run-start",
        "data": {"pipeline": "01ABC", "language": "en",
                 "runner_data": {"stt_binary_handler_id": handler, "timeout": 300}},
    }]
    if stt is not None:
        evts.append({"type": "stt-start", "data": {}})
        evts.append({"type": "stt-end", "data": {"stt_output": {"text": stt}}})
    evts.append({
        "type": "intent-end",
        "data": {"processed_locally": True, "intent_output": {
            "response": {"speech": {"plain": {"speech": speech}}},
            "conversation_id": "conv-1"}},
    })
    evts.append({
        "type": "tts-end",
        "data": {"tts_output": {"media_id": "media-source://x", "url": tts_url,
                                "mime_type": "audio/mpeg"}},
    })
    evts.append({"type": "run-end", "data": {}})
    return evts


# ───────────────────────────────────────────────────────── stage validation

class TestStageValidation:
    def test_unknown_start_stage_is_named(self, fake_client):
        with pytest.raises(ValueError, match="start_stage must be one of"):
            apr.run(fake_client, text="hi", start_stage="nope")

    def test_unknown_end_stage_is_named(self, fake_client):
        with pytest.raises(ValueError, match="end_stage must be one of"):
            apr.run(fake_client, text="hi", end_stage="nope")

    def test_end_stage_end_is_refused_locally(self, fake_client):
        """`end` is a real PipelineStage with no place in HA's stage order.

        Sent to the server it dies on a bare list.index ValueError inside
        PipelineRun.__post_init__, so it must never leave the client.
        """
        with pytest.raises(ValueError, match="'end' is a PipelineStage"):
            apr.run(fake_client, text="hi", end_stage="end")
        assert fake_client.run_event_calls == []

    def test_reversed_stages_refused_before_the_call(self, fake_client):
        with pytest.raises(ValueError, match="comes before"):
            apr.run(fake_client, text="hi", start_stage="tts", end_stage="intent")
        assert fake_client.run_event_calls == []

    def test_equal_stages_are_allowed(self, fake_client):
        fake_client.set_run_events(*_events())
        apr.run(fake_client, text="hi", start_stage="intent", end_stage="intent")
        payload = fake_client.run_event_calls[0]["payload"]
        assert payload["start_stage"] == "intent"
        assert payload["end_stage"] == "intent"


# ─────────────────────────────────────────────────────────── text pipelines

class TestTextRun:
    def test_default_is_intent_to_tts(self, fake_client):
        fake_client.set_run_events(*_events())
        apr.run(fake_client, text="turn on the light")
        call = fake_client.run_event_calls[0]
        assert call["type"] == "assist_pipeline/run"
        assert call["payload"] == {
            "start_stage": "intent",
            "end_stage": "tts",
            "input": {"text": "turn on the light"},
        }

    def test_text_is_required_for_intent(self, fake_client):
        with pytest.raises(ValueError, match="requires text"):
            apr.run(fake_client, start_stage="intent")

    def test_optional_fields_are_only_sent_when_given(self, fake_client):
        fake_client.set_run_events(*_events())
        apr.run(
            fake_client,
            text="hi",
            pipeline="01ABC",
            conversation_id="conv-9",
            device_id="dev-9",
            timeout=12,
        )
        payload = fake_client.run_event_calls[0]["payload"]
        assert payload["pipeline"] == "01ABC"
        assert payload["conversation_id"] == "conv-9"
        assert payload["device_id"] == "dev-9"
        assert payload["timeout"] == 12.0

    def test_audio_options_refused_on_a_text_stage(self, fake_client, tmp_path):
        path = _wav(tmp_path / "a.wav")
        with pytest.raises(ValueError, match="takes text, not audio"):
            apr.run(fake_client, text="hi", start_stage="intent", audio_path=path)

    def test_wake_word_phrase_refused_on_a_text_stage(self, fake_client):
        with pytest.raises(ValueError, match="only applies to start_stage 'stt'"):
            apr.run(fake_client, text="hi", wake_word_phrase="jarvis")

    def test_tts_only_run(self, fake_client):
        fake_client.set_run_events(*_events())
        apr.run(fake_client, text="say this", start_stage="tts", end_stage="tts")
        assert fake_client.run_event_calls[0]["payload"]["input"] == {"text": "say this"}


# ────────────────────────────────────────────────────────── audio pipelines

class TestAudioRun:
    def test_stt_requires_audio(self, fake_client):
        with pytest.raises(ValueError, match="reads its input from audio"):
            apr.run(fake_client, start_stage="stt")

    def test_stt_refuses_text(self, fake_client, tmp_path):
        path = _wav(tmp_path / "a.wav")
        with pytest.raises(ValueError, match="takes audio, not text"):
            apr.run(fake_client, text="hi", start_stage="stt", audio_path=path)

    def test_sample_rate_comes_from_the_wav(self, fake_client, tmp_path):
        path = _wav(tmp_path / "a.wav", rate=44100)
        fake_client.set_run_events(*_events(stt="hello"))
        out = apr.run(fake_client, start_stage="stt", audio_path=path)
        assert fake_client.run_event_calls[0]["payload"]["input"]["sample_rate"] == 44100
        assert out["audio"]["sample_rate"] == 44100

    def test_sample_rate_can_be_overridden(self, fake_client, tmp_path):
        path = _wav(tmp_path / "a.wav", rate=44100)
        fake_client.set_run_events(*_events(stt="hello"))
        apr.run(fake_client, start_stage="stt", audio_path=path, sample_rate=16000)
        assert fake_client.run_event_calls[0]["payload"]["input"]["sample_rate"] == 16000

    def test_wake_word_phrase_is_sent_for_stt(self, fake_client, tmp_path):
        path = _wav(tmp_path / "a.wav")
        fake_client.set_run_events(*_events(stt="hello"))
        apr.run(fake_client, start_stage="stt", audio_path=path,
                wake_word_phrase="ok nabu")
        assert fake_client.run_event_calls[0]["payload"]["input"][
            "wake_word_phrase"] == "ok nabu"

    def test_frames_are_prefixed_with_the_handler_id_and_terminated(
        self, fake_client, tmp_path
    ):
        """Every frame carries the handler byte; the last one is that byte ALONE.

        HA reads `while chunk := await audio_queue.get()`, so the empty-payload
        frame is what ends the stream. Without it the run hangs to timeout.
        """
        path = _wav(tmp_path / "a.wav", seconds=0.5, rate=16000)  # 16000 bytes
        fake_client.set_run_events(*_events(handler=7, stt="hello"))
        apr.run(fake_client, start_stage="stt", audio_path=path)
        frames = fake_client.binary_frames
        assert all(f[0] == 7 for f in frames)
        assert frames[-1] == bytes([7])
        payload = b"".join(f[1:] for f in frames)
        assert len(payload) == 16000
        assert len(frames) == 16000 // apr.CHUNK_BYTES + 1 + 1

    def test_audio_is_not_sent_when_the_handler_id_is_missing(
        self, fake_client, tmp_path
    ):
        path = _wav(tmp_path / "a.wav")
        events = _events(stt="hello")
        events[0]["data"]["runner_data"] = {"timeout": 300}
        fake_client.set_run_events(*events)
        with pytest.raises(ValueError, match="refusing to guess"):
            apr.run(fake_client, start_stage="stt", audio_path=path)
        assert fake_client.binary_frames == []

    def test_sender_failure_surfaces_rather_than_a_silent_no_audio_run(
        self, fake_client, tmp_path, monkeypatch
    ):
        path = _wav(tmp_path / "a.wav")
        fake_client.set_run_events(*_events(stt="hello"))
        monkeypatch.setattr(apr, "HANDLER_WAIT_SECONDS", 0.01)
        # No run-start at all: the sender times out waiting for the handler.
        fake_client.queued_run_events = [{"type": "run-end", "data": {}}]
        with pytest.raises(ValueError, match="never emitted run-start"):
            apr.run(fake_client, start_stage="stt", audio_path=path)

    def test_wake_word_start_stage_also_streams_audio(self, fake_client, tmp_path):
        path = _wav(tmp_path / "a.wav")
        fake_client.set_run_events(*_events(handler=3, stt="hello"))
        apr.run(fake_client, start_stage="wake_word", audio_path=path)
        assert fake_client.binary_frames
        assert fake_client.binary_frames[0][0] == 3


# ────────────────────────────────────────────────────────────── WAV reading

class TestReadWav:
    def test_missing_file(self):
        with pytest.raises(ValueError, match="audio file not found"):
            apr.read_wav("/nonexistent/none.wav")

    def test_not_a_wav(self, tmp_path):
        p = tmp_path / "x.wav"
        p.write_bytes(b"this is not a wav")
        with pytest.raises(ValueError, match="not a readable WAV"):
            apr.read_wav(str(p))

    def test_stereo_is_refused_with_the_conversion_command(self, tmp_path):
        path = _wav(tmp_path / "s.wav", channels=2)
        with pytest.raises(ValueError, match="2 channels"):
            apr.read_wav(path)

    def test_eight_bit_is_refused(self, tmp_path):
        path = _wav(tmp_path / "e.wav", width=1)
        with pytest.raises(ValueError, match="8-bit samples"):
            apr.read_wav(path)

    def test_empty_wav_is_refused(self, tmp_path):
        path = _wav(tmp_path / "z.wav", seconds=0)
        with pytest.raises(ValueError, match="no audio frames"):
            apr.read_wav(path)

    def test_duration_is_reported(self, tmp_path):
        path = _wav(tmp_path / "d.wav", seconds=1.5, rate=16000)
        out = apr.read_wav(path)
        assert out["sample_rate"] == 16000
        assert out["bytes"] == 48000
        assert out["seconds"] == pytest.approx(1.5)

    def test_chunking_is_exact(self):
        assert list(apr.iter_chunks(b"abcdef", 2)) == [b"ab", b"cd", b"ef"]
        assert list(apr.iter_chunks(b"abcde", 2)) == [b"ab", b"cd", b"e"]
        assert list(apr.iter_chunks(b"")) == []

    def test_chunk_size_must_be_positive(self):
        with pytest.raises(ValueError, match="must be positive"):
            list(apr.iter_chunks(b"ab", 0))


# ───────────────────────────────────────────────────────────── summarising

class TestSummarize:
    def test_full_run(self):
        out = apr.summarize(_events(stt="turn on the light", speech="Turned on"))
        assert out["completed"] is True
        assert out["pipeline"] == "01ABC"
        assert out["language"] == "en"
        assert out["stt_text"] == "turn on the light"
        assert out["speech"] == "Turned on"
        assert out["conversation_id"] == "conv-1"
        assert out["tts_url"] == "/api/tts_proxy/x.mp3"
        assert out["tts_mime_type"] == "audio/mpeg"
        assert out["error"] is None

    def test_stage_keys_are_present_but_none_when_the_stage_did_not_run(self):
        out = apr.summarize([{"type": "run-start", "data": {}},
                             {"type": "run-end", "data": {}}])
        assert out["stt_text"] is None
        assert out["speech"] is None
        assert out["tts_url"] is None
        assert out["completed"] is True

    def test_an_error_event_does_not_prevent_completion(self):
        out = apr.summarize([
            {"type": "run-start", "data": {}},
            {"type": "error", "data": {"code": "stt-no-text-recognized",
                                       "message": "No text recognized"}},
            {"type": "run-end", "data": {}},
        ])
        assert out["error"] == {"code": "stt-no-text-recognized",
                                "message": "No text recognized"}
        assert out["completed"] is True

    def test_incomplete_run_is_reported_as_incomplete(self):
        out = apr.summarize([{"type": "run-start", "data": {}}])
        assert out["completed"] is False

    def test_wake_word_id_is_extracted(self):
        out = apr.summarize([{"type": "wake_word-end",
                              "data": {"wake_word_output": {"wake_word_id": "ok_nabu"}}}])
        assert out["wake_word"] == "ok_nabu"

    def test_stage_order_is_recorded(self):
        out = apr.summarize(_events(stt="x"))
        assert out["stages"][0] == "run-start"
        assert out["stages"][-1] == "run-end"

    def test_non_dict_events_are_ignored(self):
        assert apr.summarize([None, "junk", 3])["stages"] == []

    def test_empty_event_list(self):
        assert apr.summarize([])["completed"] is False
        assert apr.summarize(None)["stages"] == []


class TestBinaryHandlerId:
    def test_found(self):
        assert apr.binary_handler_id(_events(handler=5)) == 5

    def test_absent_without_run_start(self):
        assert apr.binary_handler_id([{"type": "run-end", "data": {}}]) is None

    def test_absent_on_junk(self):
        assert apr.binary_handler_id([None, "x"]) is None
        assert apr.binary_handler_id(None) is None

    def test_non_int_handler_is_not_accepted(self):
        evts = _events()
        evts[0]["data"]["runner_data"]["stt_binary_handler_id"] = "1"
        assert apr.binary_handler_id(evts) is None


# ──────────────────────────────────────────────────────────── run() results

class TestRunResult:
    def test_events_are_omitted_unless_asked_for(self, fake_client):
        fake_client.set_run_events(*_events())
        assert "events" not in apr.run(fake_client, text="hi")

    def test_events_are_included_on_request(self, fake_client):
        fake_client.set_run_events(*_events())
        out = apr.run(fake_client, text="hi", include_events=True)
        assert out["events"][-1]["type"] == "run-end"

    def test_stages_are_echoed_back(self, fake_client):
        fake_client.set_run_events(*_events())
        out = apr.run(fake_client, text="hi", start_stage="intent", end_stage="intent")
        assert out["start_stage"] == "intent"
        assert out["end_stage"] == "intent"

    def test_on_event_callback_sees_every_event(self, fake_client):
        fake_client.set_run_events(*_events())
        seen = []
        apr.run(fake_client, text="hi", on_event=seen.append)
        assert [e["type"] for e in seen][-1] == "run-end"

    def test_transport_gets_a_grace_margin_over_the_pipeline_timeout(self, fake_client):
        """HA answers its own timeout with an error event; don't race it."""
        fake_client.set_run_events(*_events())
        apr.run(fake_client, text="hi", timeout=20)
        call = fake_client.run_event_calls[0]
        assert call["payload"]["timeout"] == 20.0
        assert call["timeout"] == 20.0 + apr.TIMEOUT_GRACE_SECONDS

    def test_no_timeout_leaves_both_at_the_client_default(self, fake_client):
        fake_client.set_run_events(*_events())
        apr.run(fake_client, text="hi")
        call = fake_client.run_event_calls[0]
        assert "timeout" not in call["payload"]
        assert call["timeout"] is None

    def test_pipeline_not_found_propagates_with_its_code(self, fake_client):
        fake_client.set_ws_error("assist_pipeline/run", "pipeline-not-found")
        with pytest.raises(HomeAssistantError) as exc:
            apr.run(fake_client, text="hi")
        assert exc.value.code == "pipeline-not-found"


class TestSaveTts:
    def test_downloads_the_reported_url(self, fake_client, tmp_path):
        dest = tmp_path / "out.mp3"
        out = apr.save_tts(fake_client, "/api/tts_proxy/abc.mp3", str(dest))
        assert fake_client.download_calls[0]["path"] == "api/tts_proxy/abc.mp3"
        assert out["bytes"] == len(fake_client.download_payload)
        assert dest.read_bytes() == fake_client.download_payload

    def test_refuses_without_a_url(self, fake_client, tmp_path):
        with pytest.raises(ValueError, match="did not reach the tts stage"):
            apr.save_tts(fake_client, None, str(tmp_path / "x"))

    def test_refuses_without_a_dest(self, fake_client):
        with pytest.raises(ValueError, match="dest is required"):
            apr.save_tts(fake_client, "/api/tts_proxy/a.mp3", "")
