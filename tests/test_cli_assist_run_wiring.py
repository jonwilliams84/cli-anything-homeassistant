"""CLI wiring tests for `assist run`.

Every option must reach `assist_pipeline_run.run` with the name the core
function expects, and every locally-refused combination must come back as a
clean `error:` line rather than a traceback (the `_HandledGroup` contract).
"""

from __future__ import annotations

import json
import struct
import wave

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod


@pytest.fixture
def runner(monkeypatch, fake_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return CliRunner()


def _invoke(runner, *args, json_out=True):
    full = (["--json"] if json_out else []) + list(args)
    return runner.invoke(
        cli_mod.cli,
        full,
        obj={
            "url": "http://x", "token": "t", "verify_ssl": False,
            "timeout": 5, "as_json": json_out, "config_path": None,
        },
    )


def _wav(tmp_path, name="cmd.wav", *, seconds=0.2, rate=16000):
    path = tmp_path / name
    frames = int(rate * seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(struct.pack("<" + "h" * frames, *([1500] * frames)))
    return str(path)


def _events(*, handler=1, stt=None):
    evts = [{"type": "run-start", "data": {
        "pipeline": "01ABC", "language": "en",
        "runner_data": {"stt_binary_handler_id": handler}}}]
    if stt is not None:
        evts.append({"type": "stt-end", "data": {"stt_output": {"text": stt}}})
    evts += [
        {"type": "intent-end", "data": {"intent_output": {
            "response": {"speech": {"plain": {"speech": "Turned on"}}},
            "conversation_id": "conv-1"}}},
        {"type": "tts-end", "data": {"tts_output": {
            "url": "/api/tts_proxy/a.mp3", "mime_type": "audio/mpeg"}}},
        {"type": "run-end", "data": {}},
    ]
    return evts


class TestAssistRunText:
    def test_registered_under_the_assist_group(self):
        assert "run" in cli_mod.assist.commands

    def test_default_run(self, runner, fake_client):
        fake_client.set_run_events(*_events())
        r = _invoke(runner, "assist", "run", "turn on the light")
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        assert out["speech"] == "Turned on"
        assert out["completed"] is True
        assert out["start_stage"] == "intent"
        assert fake_client.run_event_calls[0]["payload"] == {
            "start_stage": "intent", "end_stage": "tts",
            "input": {"text": "turn on the light"},
        }

    def test_all_passthrough_options(self, runner, fake_client):
        fake_client.set_run_events(*_events())
        r = _invoke(
            runner, "assist", "run", "hello",
            "--end-stage", "intent",
            "--pipeline", "01ABC",
            "--conversation-id", "conv-7",
            "--device-id", "dev-7",
            "--timeout", "25",
        )
        assert r.exit_code == 0, r.output
        payload = fake_client.run_event_calls[0]["payload"]
        assert payload["end_stage"] == "intent"
        assert payload["pipeline"] == "01ABC"
        assert payload["conversation_id"] == "conv-7"
        assert payload["device_id"] == "dev-7"
        assert payload["timeout"] == 25.0

    def test_events_flag_includes_the_raw_stream(self, runner, fake_client):
        fake_client.set_run_events(*_events())
        r = _invoke(runner, "assist", "run", "hi", "--events")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["events"][-1]["type"] == "run-end"

    def test_events_are_omitted_by_default(self, runner, fake_client):
        fake_client.set_run_events(*_events())
        r = _invoke(runner, "assist", "run", "hi")
        assert "events" not in json.loads(r.output)

    def test_stream_writes_events_to_stderr_so_json_stays_parseable(
        self, monkeypatch, fake_client
    ):
        monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
        fake_client.set_run_events(*_events())
        result = CliRunner().invoke(
            cli_mod.cli, ["--json", "assist", "run", "hi", "--stream"],
            obj={"url": "http://x", "token": "t", "verify_ssl": False,
                 "timeout": 5, "as_json": True, "config_path": None},
        )
        assert result.exit_code == 0, result.output
        # `output` mixes both streams under CliRunner; the payload must still
        # be the LAST JSON document and must parse on its own.
        assert json.loads(result.stdout)["speech"] == "Turned on"

    def test_human_output_without_json(self, runner, fake_client):
        fake_client.set_run_events(*_events())
        r = _invoke(runner, "assist", "run", "hi", json_out=False)
        assert r.exit_code == 0, r.output
        assert "speech: Turned on" in r.output


class TestAssistRunAudio:
    def test_stt_run_streams_the_file(self, runner, fake_client, tmp_path):
        path = _wav(tmp_path)
        fake_client.set_run_events(*_events(handler=2, stt="turn on the light"))
        r = _invoke(runner, "assist", "run", "--start-stage", "stt", "--audio", path)
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        assert out["stt_text"] == "turn on the light"
        assert out["audio"]["sample_rate"] == 16000
        assert fake_client.binary_frames[0][0] == 2

    def test_sample_rate_override_reaches_the_payload(
        self, runner, fake_client, tmp_path
    ):
        path = _wav(tmp_path, rate=44100)
        fake_client.set_run_events(*_events(stt="x"))
        r = _invoke(runner, "assist", "run", "--start-stage", "stt",
                    "--audio", path, "--sample-rate", "16000")
        assert r.exit_code == 0, r.output
        assert fake_client.run_event_calls[0]["payload"]["input"][
            "sample_rate"] == 16000

    def test_wake_word_phrase_reaches_the_payload(self, runner, fake_client, tmp_path):
        path = _wav(tmp_path)
        fake_client.set_run_events(*_events(stt="x"))
        r = _invoke(runner, "assist", "run", "--start-stage", "stt",
                    "--audio", path, "--wake-word-phrase", "ok nabu")
        assert r.exit_code == 0, r.output
        assert fake_client.run_event_calls[0]["payload"]["input"][
            "wake_word_phrase"] == "ok nabu"

    def test_a_missing_audio_file_is_a_click_error(self, runner):
        r = _invoke(runner, "assist", "run", "--start-stage", "stt",
                    "--audio", "/nonexistent/x.wav")
        assert r.exit_code != 0
        assert "does not exist" in r.output


class TestAssistRunErrors:
    def test_stt_without_audio_is_a_clean_error(self, runner):
        r = _invoke(runner, "assist", "run", "--start-stage", "stt")
        assert r.exit_code != 0
        assert "reads its input from audio" in r.output
        assert "Traceback" not in r.output

    def test_missing_text_is_a_clean_error(self, runner):
        r = _invoke(runner, "assist", "run")
        assert r.exit_code != 0
        assert "requires text" in r.output

    def test_reversed_stages_is_a_clean_error(self, runner):
        r = _invoke(runner, "assist", "run", "hi",
                    "--start-stage", "tts", "--end-stage", "intent")
        assert r.exit_code != 0
        assert "comes before" in r.output

    def test_end_is_not_an_accepted_stage(self, runner):
        r = _invoke(runner, "assist", "run", "hi", "--end-stage", "end")
        assert r.exit_code != 0
        assert "Invalid value" in r.output

    def test_a_pipeline_error_event_is_reported_not_swallowed(
        self, runner, fake_client
    ):
        fake_client.set_run_events(
            {"type": "run-start", "data": {}},
            {"type": "error", "data": {"code": "stt-provider-missing",
                                       "message": "No provider"}},
            {"type": "run-end", "data": {}},
        )
        r = _invoke(runner, "assist", "run", "hi")
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        assert out["error"]["code"] == "stt-provider-missing"
        assert out["speech"] is None


class TestAssistRunSaveTts:
    def test_saves_the_reported_url(self, runner, fake_client, tmp_path):
        dest = tmp_path / "reply.mp3"
        fake_client.set_run_events(*_events())
        r = _invoke(runner, "assist", "run", "hi", "--save-tts", str(dest))
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        assert out["saved_tts"]["bytes"] == len(fake_client.download_payload)
        assert fake_client.download_calls[0]["path"] == "api/tts_proxy/a.mp3"
        assert dest.exists()

    def test_save_tts_without_a_tts_stage_is_a_clean_error(
        self, runner, fake_client, tmp_path
    ):
        fake_client.set_run_events(
            {"type": "run-start", "data": {}},
            {"type": "intent-end", "data": {}},
            {"type": "run-end", "data": {}},
        )
        r = _invoke(runner, "assist", "run", "hi", "--end-stage", "intent",
                    "--save-tts", str(tmp_path / "x.mp3"))
        assert r.exit_code != 0
        assert "did not reach the tts stage" in r.output
