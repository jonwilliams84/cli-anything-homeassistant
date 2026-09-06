"""`HomeAssistantClient` transport paths the FakeClient cannot reach.

FakeClient replaces the client entirely, so every failure branch INSIDE the
real `HomeAssistantClient` — the 401 probe, the timeout messages, the multipart
upload, the streamed download, the websocket handshake failures — is only
exercised by pointing the real client at a real socket. REST is served by a
programmable `http.server`; the websocket side is a fake socket that replays a
scripted protocol, which is enough for the handshake/loop logic that has no
server of its own here (the REAL websocket server cases live in
`test_ws_run_events.py`).
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cli_anything.homeassistant.utils import homeassistant_backend as backend
from cli_anything.homeassistant.utils.homeassistant_backend import (
    HomeAssistantClient,
    HomeAssistantError,
    _normalize_base,
    _ws_url_from_http,
)


# ════════════════════════════════════════════════════════════ URL helpers


class TestUrlHelpers:
    def test_normalize_base_strips_path(self):
        assert _normalize_base("http://h:8123/config") == "http://h:8123"

    def test_normalize_base_adds_http_scheme(self):
        assert _normalize_base("h:8123") == "http://h:8123"

    def test_normalize_base_empty_raises(self):
        with pytest.raises(ValueError, match="URL cannot be empty"):
            _normalize_base("")

    def test_normalize_base_unparsable_raises(self):
        with pytest.raises(ValueError, match="Invalid URL"):
            _normalize_base("http://")

    def test_ws_url_from_http(self):
        assert _ws_url_from_http("http://h:8123") == "ws://h:8123/api/websocket"
        assert _ws_url_from_http("https://h") == "wss://h/api/websocket"


# ════════════════════════════════════════════════════════════════ REST server


class _Hass(BaseHTTPRequestHandler):
    """Serves a per-test route table: {(method, path): (status, body, ctype)}."""

    def log_message(self, *args):  # noqa: D102
        pass

    def _handle(self):
        cfg = self.server.cfg
        length = int(self.headers.get("Content-Length") or 0)
        req_body = self.rfile.read(length) if length else b""
        cfg.setdefault("log", []).append(
            {
                "method": self.command,
                "path": self.path,
                "content_type": self.headers.get("Content-Type"),
                "authorization": self.headers.get("Authorization"),
                "body": req_body,
            }
        )
        entry = cfg["routes"].get((self.command, self.path))
        if entry is None:
            status, body, ctype = 404, json.dumps({"error": "no route"}).encode(), "application/json"
        else:
            status, body, ctype = entry
            if callable(body):
                body = body(req_body)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_DELETE = _handle


@pytest.fixture
def hass_server():
    server = HTTPServer(("127.0.0.1", 0), _Hass)
    server.cfg = {"routes": {}, "log": []}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def client(hass_server):
    return HomeAssistantClient(
        url=f"http://127.0.0.1:{hass_server.server_port}",
        token="tok-1",
        timeout=5,
    )


def route(server, method, path, status=200, body=b'{"ok": true}', ctype="application/json"):
    server.cfg["routes"][(method, path)] = (status, body, ctype)


class TestRest:
    def test_get_decodes_json(self, client, hass_server):
        route(hass_server, "GET", "/api/states")
        assert client.get("states") == {"ok": True}

    def test_get_empty_body_becomes_empty_dict(self, client, hass_server):
        route(hass_server, "GET", "/api/empty", body=b"")
        assert client.get("empty") == {}

    def test_get_text_content_type_returns_text(self, client, hass_server):
        route(hass_server, "GET", "/api/log", body=b"plain text", ctype="text/plain")
        assert client.get("log") == "plain text"

    def test_get_broken_json_body_returns_text(self, client, hass_server):
        route(hass_server, "GET", "/api/broken", body=b"{not json", ctype="application/json")
        assert client.get("broken") == "{not json"

    def test_get_non_ok_raises_with_status(self, client, hass_server):
        route(hass_server, "GET", "/api/nope", status=404, body=b"missing")
        with pytest.raises(HomeAssistantError, match="GET nope -> 404") as exc:
            client.get("nope")
        assert exc.value.status == 404

    def test_post_without_payload_sends_no_body(self, client, hass_server):
        route(hass_server, "POST", "/api/thing")
        client.post("thing")
        rec = hass_server.cfg["log"][-1]
        assert rec["body"] == b""

    def test_post_string_payload_becomes_template_object(self, client, hass_server):
        """`/api/template` wants {"template": …} — the str payload is wrapped."""
        route(hass_server, "POST", "/api/template")
        client.post("template", "{{ states() }}")
        rec = hass_server.cfg["log"][-1]
        assert json.loads(rec["body"]) == {"template": "{{ states() }}"}

    def test_post_dict_payload_sent_verbatim(self, client, hass_server):
        route(hass_server, "POST", "/api/services/light/turn_on")
        client.post("services/light/turn_on", {"entity_id": "light.tv"})
        rec = hass_server.cfg["log"][-1]
        assert json.loads(rec["body"]) == {"entity_id": "light.tv"}

    def test_post_non_ok_raises_with_status(self, client, hass_server):
        route(hass_server, "POST", "/api/bad", status=500, body=b"boom")
        with pytest.raises(HomeAssistantError, match="POST bad -> 500") as exc:
            client.post("bad")
        assert exc.value.status == 500

    def test_delete_non_ok_raises(self, client, hass_server):
        route(hass_server, "DELETE", "/api/nope", status=405, body=b"no")
        with pytest.raises(HomeAssistantError, match="DELETE nope -> 405") as exc:
            client.delete("nope")
        assert exc.value.status == 405

    def test_unreachable_host_raises_connection_error(self):
        client = HomeAssistantClient(url="http://127.0.0.1:9", token="t", timeout=1)
        with pytest.raises(HomeAssistantError, match="Cannot reach Home Assistant"):
            client.get("states")

    def test_slow_endpoint_raises_timeout(self, hass_server):
        def slow(body):
            time.sleep(3)
            return b"{}"

        route(hass_server, "GET", "/api/slow", body=slow)
        client = HomeAssistantClient(
            url=f"http://127.0.0.1:{hass_server.server_port}", token="t", timeout=1
        )
        with pytest.raises(HomeAssistantError, match="timed out after 1s"):
            client.get("slow")

    def test_get_request_headers_merged_over_session(self, client, hass_server):
        """The Supervisor log limit rides a `Range` header — assert it leaves."""
        route(hass_server, "GET", "/api/addon/core_mosquitto/logs")
        client.get("addon/core_mosquitto/logs", headers={"Range": "entries=:-50:"})
        assert hass_server.cfg["log"][-1]["authorization"] == "Bearer tok-1"


class TestAuth401:
    def test_401_with_working_root_probe_names_elevated_permissions(self, client, hass_server):
        """Root `/api/` answers 200 → the token is fine, the endpoint is admin-only."""
        route(hass_server, "GET", "/api/", body=b"{}")
        route(hass_server, "GET", "/api/template", status=401, body=b"denied")
        with pytest.raises(HomeAssistantError, match="elevated permissions"):
            client.get("template")

    def test_401_with_failing_probe_is_bad_token(self, client, hass_server):
        """Root `/api/` also 401s → the token itself is the problem."""
        route(hass_server, "GET", "/api/", status=401, body=b"{}")
        route(hass_server, "GET", "/api/anything", status=401, body=b"{}")
        with pytest.raises(HomeAssistantError, match="Set a valid long-lived access token"):
            client.get("anything")


class TestDownload:
    def test_download_streams_to_file_and_reports(self, client, hass_server, tmp_path):
        payload = b"x" * 2048
        route(
            hass_server,
            "GET",
            "/api/backup/download/x",
            body=payload,
            ctype="application/x-tar",
        )
        dest = tmp_path / "backup.tar"
        out = client.download("backup/download/x", dest)
        assert dest.read_bytes() == payload
        assert out["bytes"] == 2048
        assert out["content_type"] == "application/x-tar"
        # The server declared Content-Length and every byte arrived.
        assert out["declared_length"] == 2048
        assert out["size_matches"] is True

    def test_download_error_does_not_touch_dest(self, client, hass_server, tmp_path):
        dest = tmp_path / "precious.tar"
        dest.write_bytes(b"KEEP ME")
        route(hass_server, "GET", "/api/backup/download/y", status=404, body=b"gone")
        with pytest.raises(HomeAssistantError, match="-> 404"):
            client.download("backup/download/y", dest)
        assert dest.read_bytes() == b"KEEP ME"

    def test_download_unreachable_raises(self, tmp_path):
        client = HomeAssistantClient(url="http://127.0.0.1:9", token="t", timeout=1)
        with pytest.raises(HomeAssistantError, match="Cannot reach"):
            client.download("backup/download/z", tmp_path / "o")


class TestUpload:
    def test_upload_sends_multipart_without_json_content_type(self, client, hass_server, tmp_path):
        f = tmp_path / "media.mp4"
        f.write_bytes(b"0123456789")
        route(hass_server, "POST", "/api/media_source/local_source/upload", body=b'{"ok": true}')
        client.upload("media_source/local_source/upload", f)
        rec = hass_server.cfg["log"][-1]
        # The session's application/json must NOT ride along on a multipart body.
        assert rec["content_type"].startswith("multipart/form-data; boundary=")
        assert b"media.mp4" in rec["body"]

    def test_upload_guesses_content_type_from_extension(self, client, hass_server, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"ff")
        route(hass_server, "POST", "/api/media/upload")
        client.upload("media/upload", f)
        body = hass_server.cfg["log"][-1]["body"]
        assert b"image/jpeg" in body

    def test_upload_missing_file_raises_named_error(self, client, tmp_path):
        with pytest.raises(HomeAssistantError, match="No such file to upload"):
            client.upload("api/x", tmp_path / "nope.bin")

    def test_upload_non_ok_raises(self, client, hass_server, tmp_path):
        f = tmp_path / "a.bin"
        f.write_bytes(b"z")
        route(hass_server, "POST", "/api/backup/upload", status=400, body=b"bad")
        with pytest.raises(HomeAssistantError, match="-> 400"):
            client.upload("backup/upload", f)

    def test_upload_extra_fields_sent_as_form_parts(self, client, hass_server, tmp_path):
        f = tmp_path / "a.bin"
        f.write_bytes(b"z")
        route(hass_server, "POST", "/api/backup/upload")
        client.upload("backup/upload", f, extra_fields={"agent": "backup.local"})
        assert b"agent" in hass_server.cfg["log"][-1]["body"]


# ════════════════════════════════════════════════════════════ root_request


class TestRootRequestExtra:
    def test_contradictory_auth_args_raise(self, client):
        with pytest.raises(ValueError, match="contradictory"):
            client.root_request("GET", "auth/token", send_auth=False, auth_token="t")

    def test_unreachable_raises_connection_error(self):
        client = HomeAssistantClient(url="http://127.0.0.1:9", token="t", timeout=1)
        with pytest.raises(HomeAssistantError, match="Cannot reach"):
            client.root_request("GET", "auth/providers")


# ══════════════════════════════════════════════════════════════ websocket


class FakeWS:
    """Replays a scripted list of wire messages; records what was sent."""

    def __init__(self, incoming=None, fail_recv=None):
        self.incoming = list(incoming or [])
        self.fail_recv = fail_recv
        self.sent: list[str] = []
        self.sent_binary: list[bytes] = []
        self.closed = False
        self.timeouts: list[float] = []

    def settimeout(self, t):
        self.timeouts.append(t)

    def send(self, raw):
        self.sent.append(raw)

    def send_binary(self, blob):
        self.sent_binary.append(blob)

    def recv(self):
        if self.incoming:
            return self.incoming.pop(0)
        if self.fail_recv is not None:
            raise self.fail_recv
        return ""  # keeps bounded loops spinning to their deadline

    def close(self):
        self.closed = True


_AUTH_OK = [
    json.dumps({"type": "auth_required"}),
    json.dumps({"type": "auth_ok", "ha_version": "2025.1"}),
]


def make_client(monkeypatch, incoming=None, connect=None, timeout=0.2, token="tok"):
    """A real client whose websocket factory returns a scripted fake."""
    ws = FakeWS(incoming)
    import cli_anything.homeassistant.utils.homeassistant_backend as backend

    calls: list[dict] = []

    def fake_create_connection(url, timeout=None, sslopt=None):
        calls.append({"url": url, "sslopt": sslopt})
        if connect is not None:
            raise connect
        return ws

    monkeypatch.setattr(backend.websocket, "create_connection", fake_create_connection)
    client = HomeAssistantClient(url="http://h:8123", token=token, timeout=timeout)
    return client, ws, calls


class TestWsCall:
    def test_successful_call_returns_result(self, monkeypatch):
        client, ws, calls = make_client(
            monkeypatch,
            _AUTH_OK + [json.dumps({"id": 1, "type": "result", "success": True, "result": [1, 2]})],
        )
        assert client.ws_call("config/area_registry/list") == [1, 2]
        sent = [json.loads(s) for s in ws.sent]
        assert sent[0] == {"type": "auth", "access_token": "tok"}
        assert sent[1]["type"] == "config/area_registry/list"
        assert ws.closed
        assert calls[0]["url"].endswith("/api/websocket")

    def test_failed_result_raises_with_machine_code(self, monkeypatch):
        client, _, _ = make_client(
            monkeypatch,
            _AUTH_OK
            + [
                json.dumps(
                    {
                        "id": 1,
                        "type": "result",
                        "success": False,
                        "error": {"code": "unauthorized", "message": "nope"},
                    }
                )
            ],
        )
        with pytest.raises(HomeAssistantError, match="unauthorized") as exc:
            client.ws_call("anything")
        assert exc.value.code == "unauthorized"

    def test_unexpected_handshake_raises(self, monkeypatch):
        client, _, _ = make_client(monkeypatch, [json.dumps({"type": "hello"})])
        with pytest.raises(HomeAssistantError, match="Unexpected WS handshake"):
            client.ws_call("anything")

    def test_auth_invalid_raises(self, monkeypatch):
        client, _, _ = make_client(
            monkeypatch,
            [json.dumps({"type": "auth_required"}), json.dumps({"type": "auth_invalid", "message": "bad"})],
        )
        with pytest.raises(HomeAssistantError, match="auth_invalid: bad"):
            client.ws_call("anything")

    def test_unknown_auth_result_raises(self, monkeypatch):
        client, _, _ = make_client(
            monkeypatch,
            [json.dumps({"type": "auth_required"}), json.dumps({"type": "weird"})],
        )
        with pytest.raises(HomeAssistantError, match="auth failed"):
            client.ws_call("anything")

    def test_unreachable_socket_raises_connection_error(self, monkeypatch):
        client, _, _ = make_client(monkeypatch, connect=OSError("refused"))
        with pytest.raises(HomeAssistantError, match="Cannot reach"):
            client.ws_call("anything")

    def test_socket_never_answers_times_out(self, monkeypatch):
        client, _, _ = make_client(monkeypatch, _AUTH_OK, timeout=0.05)
        with pytest.raises(HomeAssistantError, match="timed out after 0.05s"):
            client.ws_call("anything")

    def test_ssl_opt_set_when_verify_off(self, monkeypatch):
        client, ws, calls = make_client(
            monkeypatch,
            _AUTH_OK + [json.dumps({"id": 1, "type": "result", "success": True, "result": None})],
        )
        client.verify_ssl = False
        client.ws_call("anything")
        assert calls[-1]["sslopt"] == {"cert_reqs": 0}


class TestWsPing:
    def test_pong_returns_latency(self, monkeypatch):
        client, ws, _ = make_client(
            monkeypatch, _AUTH_OK + [json.dumps({"id": 1, "type": "pong"})]
        )
        ms = client.ws_ping()
        assert ms >= 0
        assert json.loads(ws.sent[1]) == {"id": 1, "type": "ping"}

    def test_failed_ping_result_raises_with_code(self, monkeypatch):
        client, _, _ = make_client(
            monkeypatch,
            _AUTH_OK
            + [
                json.dumps(
                    {
                        "id": 1,
                        "type": "result",
                        "success": False,
                        "error": {"code": "unknown_command", "message": "no ping"},
                    }
                )
            ],
        )
        with pytest.raises(HomeAssistantError, match="unknown_command") as exc:
            client.ws_ping()
        assert exc.value.code == "unknown_command"

    def test_other_messages_are_skipped_until_pong(self, monkeypatch):
        client, _, _ = make_client(
            monkeypatch,
            _AUTH_OK
            + [json.dumps({"id": 9, "type": "event", "event": {}}),
               json.dumps({"id": 1, "type": "pong"})],
        )
        assert client.ws_ping() >= 0

    def test_unreachable_socket_raises_connection_error(self, monkeypatch):
        client, _, _ = make_client(monkeypatch, connect=OSError("refused"))
        with pytest.raises(HomeAssistantError, match="Cannot reach"):
            client.ws_ping()

    def test_without_websocket_package_raises_install_hint(self, monkeypatch):
        import cli_anything.homeassistant.utils.homeassistant_backend as backend

        monkeypatch.setattr(backend, "websocket", None)
        client = HomeAssistantClient(url="http://h", token="t")
        with pytest.raises(HomeAssistantError, match="pip install websocket-client"):
            client.ws_ping()
        with pytest.raises(HomeAssistantError, match="pip install websocket-client"):
            client.ws_call("x")
        with pytest.raises(HomeAssistantError, match="pip install websocket-client"):
            client.ws_run_events("x")
        with pytest.raises(HomeAssistantError, match="pip install websocket-client"):
            client.ws_subscribe("x", {}, lambda e: None, threading.Event())


class TestWsRunEvents:
    def test_acks_then_streams_until_terminal(self, monkeypatch):
        events = [
            json.dumps({"id": 1, "type": "result", "success": True, "result": None}),
            json.dumps({"id": 1, "type": "event", "event": {"x": 1}}),
            json.dumps({"id": 1, "type": "event", "event": {"x": 2, "done": True}}),
        ]
        client, ws, _ = make_client(monkeypatch, _AUTH_OK + events)
        seen = []
        out = client.ws_run_events(
            "assist_pipeline/run",
            {},
            is_terminal=lambda e: e.get("done"),
            on_event=seen.append,
        )
        assert out == [{"x": 1}, {"x": 2, "done": True}]
        assert seen == out

    def test_binary_frames_are_ignored(self, monkeypatch):
        events = [
            json.dumps({"id": 1, "type": "result", "success": True, "result": None}),
            json.dumps({"id": 1, "type": "event", "event": {"done": True}}),
        ]
        client, _, _ = make_client(monkeypatch, _AUTH_OK + [b"\x01\x02audio"] + events)
        out = client.ws_run_events("x", {}, is_terminal=lambda e: True)
        assert out == [{"done": True}]

    def test_failed_ack_raises_with_code(self, monkeypatch):
        client, _, _ = make_client(
            monkeypatch,
            _AUTH_OK
            + [
                json.dumps(
                    {
                        "id": 1,
                        "type": "result",
                        "success": False,
                        "error": {"code": "unknown_error", "message": "boom"},
                    }
                )
            ],
        )
        with pytest.raises(HomeAssistantError, match="unknown_error"):
            client.ws_run_events("x", {}, is_terminal=lambda e: False)

    def test_connection_drop_is_named_not_silent(self, monkeypatch):
        ack = json.dumps({"id": 1, "type": "result", "success": True, "result": None})
        ws = FakeWS(_AUTH_OK + [ack], fail_recv=OSError("socket gone"))
        import cli_anything.homeassistant.utils.homeassistant_backend as backend

        monkeypatch.setattr(backend.websocket, "create_connection", lambda *a, **k: ws)
        client = HomeAssistantClient(url="http://h", token="t", timeout=5)
        with pytest.raises(HomeAssistantError, match="the connection closed"):
            client.ws_run_events("x", {}, is_terminal=lambda e: False)

    def test_on_ack_sends_binary_and_errors_are_reraised(self, monkeypatch):
        ack = json.dumps({"id": 1, "type": "result", "success": True, "result": None})
        ev = json.dumps({"id": 1, "type": "event", "event": {"done": True}})
        client, ws, _ = make_client(monkeypatch, _AUTH_OK + [ack, ev])

        def bad_sender(send_binary):
            send_binary(b"audio")
            raise RuntimeError("wav vanished")

        with pytest.raises(RuntimeError, match="wav vanished"):
            client.ws_run_events("x", {}, is_terminal=lambda e: True, on_ack=bad_sender)
        assert ws.sent_binary == [b"audio"]

    def test_unreachable_socket_raises_connection_error(self, monkeypatch):
        client, _, _ = make_client(monkeypatch, connect=OSError("refused"))
        with pytest.raises(HomeAssistantError, match="Cannot reach"):
            client.ws_run_events("x", {}, is_terminal=lambda e: False)


class TestWsSubscribe:
    def test_subscribe_streams_until_stopped(self, monkeypatch):
        events = [
            json.dumps({"id": 1, "type": "result", "success": True, "result": None}),
            json.dumps({"id": 1, "type": "event", "event": {"n": 1}}),
            json.dumps({"id": 1, "type": "event", "event": {"n": 2}}),
        ]
        client, ws, _ = make_client(monkeypatch, _AUTH_OK + events, timeout=5)
        got: list = []
        stop = threading.Event()

        def on_message(event):
            got.append(event)
            if len(got) == 2:
                stop.set()

        client.ws_subscribe("subscribe_events", {}, on_message, stop)
        assert got == [{"n": 1}, {"n": 2}]
        # The unsubscribe frame must have been sent before close.
        types = [json.loads(s).get("type") for s in ws.sent]
        assert "subscribe_events" in types and "unsubscribe_events" in types
        assert ws.closed

    def test_bad_handshake_raises(self, monkeypatch):
        client, _, _ = make_client(monkeypatch, [json.dumps({"type": "nope"})])
        with pytest.raises(HomeAssistantError, match="Unexpected WS handshake"):
            client.ws_subscribe("x", {}, lambda e: None, threading.Event())

    def test_auth_failure_raises(self, monkeypatch):
        client, _, _ = make_client(
            monkeypatch,
            [json.dumps({"type": "auth_required"}), json.dumps({"type": "auth_invalid"})],
        )
        with pytest.raises(HomeAssistantError, match="auth failed"):
            client.ws_subscribe("x", {}, lambda e: None, threading.Event())

    def test_failed_result_raises(self, monkeypatch):
        client, _, _ = make_client(
            monkeypatch,
            _AUTH_OK
            + [
                json.dumps(
                    {
                        "id": 1,
                        "type": "result",
                        "success": False,
                        "error": {"code": "x", "message": "denied"},
                    }
                )
            ],
        )
        with pytest.raises(HomeAssistantError, match="denied"):
            client.ws_subscribe("x", {}, lambda e: None, threading.Event())

    def test_socket_error_ends_the_loop_without_hanging(self, monkeypatch):
        ack = json.dumps({"id": 1, "type": "result", "success": True, "result": None})
        ws = FakeWS(_AUTH_OK + [ack], fail_recv=OSError("gone"))
        import cli_anything.homeassistant.utils.homeassistant_backend as backend

        monkeypatch.setattr(backend.websocket, "create_connection", lambda *a, **k: ws)
        client = HomeAssistantClient(url="http://h", token="t", timeout=5)
        client.ws_subscribe("x", {}, lambda e: None, threading.Event())
        assert ws.closed
