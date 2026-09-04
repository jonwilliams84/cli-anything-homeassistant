"""`HomeAssistantClient.ws_run_events` against a REAL websocket server.

WHY THIS EXISTS RATHER THAN ANOTHER FakeClient TEST
    `assist_pipeline/run` cannot be exercised end-to-end here — the
    integration needs `pyspeex-noise`, whose wheel does not build in this
    environment, so the e2e Home Assistant never loads it. What CAN be
    verified for real is the part that was actually new: a websocket command
    that acks first, streams events, takes binary audio on the same socket
    while those events arrive, and ends on a terminal event.

    The server below is not a mock of this client. It implements the protocol
    from the other side, the way HA's `websocket_api` does: the `auth_required`
    handshake, an empty `result` ack, and binary frames decoded as
    `handler = data[0]; payload = data[1:]`. If the client's framing were
    wrong, this server would see the wrong handler byte or never see the
    end-of-stream frame, and the test would hang or fail — which is exactly
    what a FakeClient cannot tell you.
"""

from __future__ import annotations

import asyncio
import json
import struct
import threading
import time
import wave

import pytest

from cli_anything.homeassistant.core import assist_pipeline_run as apr
from cli_anything.homeassistant.utils.homeassistant_backend import (
    HomeAssistantClient,
    HomeAssistantError,
)

aiohttp = pytest.importorskip("aiohttp", reason="aiohttp ships with homeassistant")
from aiohttp import web  # noqa: E402

TOKEN = "test-token"


class ProtocolServer:
    """A websocket endpoint that speaks HA's `/api/websocket` protocol."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.received_binary: list[bytes] = []
        self.received_commands: list[dict] = []
        self.auth_tokens: list[str] = []
        self.url = ""
        self._loop = None
        self._runner = None
        self._thread = None
        self._ready = threading.Event()
        self.closing = None

    async def _handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"type": "auth_required", "ha_version": "2025.1.4"})
        msg = await ws.receive()
        auth = json.loads(msg.data)
        self.auth_tokens.append(auth.get("access_token"))
        if auth.get("access_token") != TOKEN:
            await ws.send_json({"type": "auth_invalid", "message": "bad token"})
            await ws.close()
            return ws
        await ws.send_json({"type": "auth_ok", "ha_version": "2025.1.4"})

        cmd = json.loads((await ws.receive()).data)
        self.received_commands.append(cmd)
        await self.behaviour(self, ws, cmd)
        return ws

    async def read_audio(self, ws) -> None:
        """Decode binary frames exactly the way HA's http.py does."""
        async for msg in ws:
            if msg.type is aiohttp.WSMsgType.BINARY:
                handler, payload = msg.data[0], msg.data[1:]
                self.received_binary.append(bytes([handler]) + payload)
                if not payload:  # empty payload == end of stream
                    return
            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING,
                              aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                return

    def start(self):
        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self.closing = asyncio.Event()
            app = web.Application()
            app.router.add_get("/api/websocket", self._handler)
            self._runner = web.AppRunner(app)
            self._loop.run_until_complete(self._runner.setup())
            site = web.TCPSite(self._runner, "127.0.0.1", 0)
            self._loop.run_until_complete(site.start())
            port = site._server.sockets[0].getsockname()[1]
            self.url = f"http://127.0.0.1:{port}"
            self._ready.set()
            self._loop.run_forever()
            # Teardown runs on the loop's OWN thread, after run_forever returns.
            # Doing it from the test thread races the handler and turns a clean
            # shutdown into "Event loop is closed" noise on every session.
            self._loop.run_until_complete(self._runner.cleanup())
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True))
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        assert self._ready.wait(20), "protocol server never came up"
        return self

    def stop(self):
        """Release any still-waiting handler, then stop the loop."""
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self.closing.set)
        # Give a handler awaiting `closing` a moment to return before the loop
        # goes away underneath it.
        time.sleep(0.05)
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=10)

    def client(self, timeout=15):
        return HomeAssistantClient(url=self.url, token=TOKEN, timeout=timeout)


@pytest.fixture
def serve():
    servers: list[ProtocolServer] = []

    def _make(behaviour):
        server = ProtocolServer(behaviour).start()
        servers.append(server)
        return server

    yield _make
    for server in servers:
        server.stop()


# ───────────────────────────────────────────────────────────────── behaviours

async def _text_run(server, ws, cmd):
    await ws.send_json({"id": cmd["id"], "type": "result", "success": True,
                        "result": None})
    for event in (
        {"type": "run-start", "data": {"pipeline": "01ABC", "language": "en",
                                       "runner_data": {"stt_binary_handler_id": 1}}},
        {"type": "intent-end", "data": {"intent_output": {
            "response": {"speech": {"plain": {"speech": "Turned on"}}},
            "conversation_id": "conv-1"}}},
        {"type": "tts-end", "data": {"tts_output": {"url": "/api/tts_proxy/a.mp3",
                                                    "mime_type": "audio/mpeg"}}},
        {"type": "run-end", "data": {}},
    ):
        await ws.send_json({"id": cmd["id"], "type": "event", "event": event})


async def _audio_run(server, ws, cmd):
    await ws.send_json({"id": cmd["id"], "type": "result", "success": True,
                        "result": None})
    await ws.send_json({"id": cmd["id"], "type": "event", "event": {
        "type": "run-start",
        "data": {"pipeline": "01ABC", "language": "en",
                 "runner_data": {"stt_binary_handler_id": 4}}}})
    await ws.send_json({"id": cmd["id"], "type": "event",
                        "event": {"type": "stt-start", "data": {}}})
    await server.read_audio(ws)
    received = sum(len(f) - 1 for f in server.received_binary)
    await ws.send_json({"id": cmd["id"], "type": "event", "event": {
        "type": "stt-end", "data": {"stt_output": {"text": f"{received} bytes"}}}})
    intent_event = {
        "type": "intent-end",
        "data": {"intent_output": {"response": {"speech": {"plain": {"speech": "done"}}}}},
    }
    await ws.send_json({"id": cmd["id"], "type": "event", "event": intent_event})
    await ws.send_json({"id": cmd["id"], "type": "event",
                        "event": {"type": "run-end", "data": {}}})


async def _refuse(server, ws, cmd):
    await ws.send_json({"id": cmd["id"], "type": "result", "success": False,
                        "error": {"code": "pipeline-not-found",
                                  "message": "Pipeline not found: id=nope"}})


async def _ack_then_silence(server, ws, cmd):
    """Ack and then say nothing — a run that never reaches `run-end`."""
    await ws.send_json({"id": cmd["id"], "type": "result", "success": True,
                        "result": None})
    await server.closing.wait()


async def _noise_then_run(server, ws, cmd):
    """Interleave traffic the client must ignore: other ids, and binary."""
    await ws.send_json({"id": 99, "type": "event",
                        "event": {"type": "run-end", "data": {"wrong": True}}})
    await ws.send_bytes(b"\x01audio-out")
    await ws.send_json({"id": cmd["id"], "type": "result", "success": True,
                        "result": None})
    await ws.send_json({"id": 99, "type": "event",
                        "event": {"type": "run-end", "data": {"wrong": True}}})
    await ws.send_json({"id": cmd["id"], "type": "event",
                        "event": {"type": "intent-end", "data": {}}})
    await ws.send_json({"id": cmd["id"], "type": "event",
                        "event": {"type": "run-end", "data": {}}})


# ───────────────────────────────────────────────────────────────────── tests

class TestTransport:
    def test_authenticates_then_sends_the_command(self, serve):
        server = serve(_text_run)
        server.client().ws_run_events(
            "assist_pipeline/run", {"start_stage": "intent", "end_stage": "tts"},
            is_terminal=lambda e: e.get("type") == "run-end",
        )
        assert server.auth_tokens == [TOKEN]
        cmd = server.received_commands[0]
        assert cmd["type"] == "assist_pipeline/run"
        assert cmd["start_stage"] == "intent"
        assert cmd["id"] == 1

    def test_collects_events_and_stops_at_the_terminal_one(self, serve):
        server = serve(_text_run)
        events = server.client().ws_run_events(
            "assist_pipeline/run", {"start_stage": "intent", "end_stage": "tts"},
            is_terminal=lambda e: e.get("type") == "run-end",
        )
        assert [e["type"] for e in events] == [
            "run-start", "intent-end", "tts-end", "run-end"]

    def test_a_failed_ack_raises_with_has_code(self, serve):
        server = serve(_refuse)
        with pytest.raises(HomeAssistantError) as exc:
            server.client().ws_run_events(
                "assist_pipeline/run", {"pipeline": "nope"},
                is_terminal=lambda e: e.get("type") == "run-end",
            )
        assert exc.value.code == "pipeline-not-found"

    def test_a_run_that_never_ends_is_an_error_not_a_hang(self, serve):
        server = serve(_ack_then_silence)
        with pytest.raises(HomeAssistantError, match="ended early"):
            server.client(timeout=2).ws_run_events(
                "assist_pipeline/run", {},
                is_terminal=lambda e: e.get("type") == "run-end",
                timeout=2,
            )

    def test_other_subscription_ids_and_binary_frames_are_ignored(self, serve):
        server = serve(_noise_then_run)
        events = server.client().ws_run_events(
            "assist_pipeline/run", {},
            is_terminal=lambda e: e.get("type") == "run-end",
        )
        assert [e["type"] for e in events] == ["intent-end", "run-end"]
        assert all(not e.get("data", {}).get("wrong") for e in events)

    def test_no_predicate_samples_until_the_deadline(self, serve):
        server = serve(_text_run)
        events = server.client(timeout=2).ws_run_events(
            "assist_pipeline/run", {}, timeout=2)
        assert [e["type"] for e in events][-1] == "run-end"

    def test_on_event_is_called_live(self, serve):
        server = serve(_text_run)
        seen = []
        server.client().ws_run_events(
            "assist_pipeline/run", {},
            is_terminal=lambda e: e.get("type") == "run-end",
            on_event=seen.append,
        )
        assert seen[0]["type"] == "run-start"


class TestBinaryFraming:
    @staticmethod
    def _wav(path, *, seconds=0.6, rate=16000):
        frames = int(rate * seconds)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(struct.pack("<" + "h" * frames, *([2000] * frames)))
        return str(path)

    def test_audio_reaches_the_server_byte_for_byte(self, serve, tmp_path):
        """The whole point: a WAV goes in, the server reassembles it exactly."""
        server = serve(_audio_run)
        path = self._wav(tmp_path / "cmd.wav", seconds=0.6)
        expected = apr.read_wav(path)["bytes"]

        out = apr.run(server.client(), start_stage="stt", audio_path=path)

        assert out["completed"] is True
        assert out["stt_text"] == f"{expected} bytes"
        assert out["audio"]["bytes"] == expected

    def test_the_handler_byte_from_run_start_is_used(self, serve, tmp_path):
        server = serve(_audio_run)
        path = self._wav(tmp_path / "cmd.wav", seconds=0.2)
        apr.run(server.client(), start_stage="stt", audio_path=path)
        assert server.received_binary
        assert {f[0] for f in server.received_binary} == {4}

    def test_the_stream_is_closed_with_an_empty_payload_frame(self, serve, tmp_path):
        server = serve(_audio_run)
        path = self._wav(tmp_path / "cmd.wav", seconds=0.2)
        apr.run(server.client(), start_stage="stt", audio_path=path)
        assert server.received_binary[-1] == bytes([4])
        assert all(len(f) > 1 for f in server.received_binary[:-1])

    def test_a_long_file_is_chunked_not_sent_whole(self, serve, tmp_path):
        server = serve(_audio_run)
        path = self._wav(tmp_path / "long.wav", seconds=3.0, rate=16000)
        apr.run(server.client(timeout=30), start_stage="stt", audio_path=path)
        # 96000 bytes of PCM cannot be one frame at CHUNK_BYTES=4096.
        assert len(server.received_binary) > 20
        assert max(len(f) - 1 for f in server.received_binary) == apr.CHUNK_BYTES

    def test_text_runs_send_no_binary_at_all(self, serve):
        server = serve(_text_run)
        out = apr.run(server.client(), text="turn on the light")
        assert server.received_binary == []
        assert out["speech"] == "Turned on"
        assert out["tts_url"] == "/api/tts_proxy/a.mp3"
