"""`HomeAssistantClient.root_request` — the non-`/api/` transport.

Served by a REAL HTTP server over a REAL socket rather than a mock, because
what is being tested is what `requests` puts ON THE WIRE: whether the session's
`Content-Type: application/json` is overridden for a form body, and whether the
`Authorization` header is actually absent when `send_auth=False`. A mock of
`session.request` would only confirm the arguments this module passes, which is
the thing already known.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cli_anything.homeassistant.utils.homeassistant_backend import (
    HomeAssistantClient,
    HomeAssistantError,
)


class _Echo(BaseHTTPRequestHandler):
    """Reflects the request back: path, headers, raw body."""

    def log_message(self, *args):  # noqa: D102 - silence the test server
        pass

    def _reply(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else ""
        status = 418 if self.path.endswith("/teapot") else 200
        payload = json.dumps(
            {
                "method": self.command,
                "path": self.path,
                "content_type": self.headers.get("Content-Type"),
                "authorization": self.headers.get("Authorization"),
                "body": body,
            }
        ).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_DELETE = _reply


@pytest.fixture
def echo_server():
    server = HTTPServer(("127.0.0.1", 0), _Echo)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def client(echo_server):
    return HomeAssistantClient(url=echo_server, token="tok-123", timeout=5)


def test_path_is_not_prefixed_with_api(client):
    """The whole reason this method exists — `get`/`post` route through
    `_url()`, which hardcodes `/api/`, so `/auth/token` is unreachable."""
    status, body = client.root_request("GET", "/auth/providers")
    assert status == 200
    assert body["path"] == "/auth/providers"


def test_leading_slash_is_optional(client):
    _, body = client.root_request("GET", "auth/providers")
    assert body["path"] == "/auth/providers"


def test_a_form_body_overrides_the_session_json_content_type(client):
    """THE TRAP: `__init__` sets `Content-Type: application/json` on the
    session, and `requests` only generates a form content type when one is not
    already set. Left alone, `/auth/token` parses an EMPTY MultiDict and
    answers `unsupported_grant_type`."""
    assert client.session.headers["Content-Type"] == "application/json"
    _, body = client.root_request(
        "POST", "/auth/token", form={"grant_type": "refresh_token", "refresh_token": "r"}
    )
    assert body["content_type"] == "application/x-www-form-urlencoded"
    assert body["body"] == "grant_type=refresh_token&refresh_token=r"


def test_a_json_body_stays_json(client):
    _, body = client.root_request("POST", "/auth/login_flow", json_payload={"client_id": "c"})
    assert "application/json" in body["content_type"]
    assert json.loads(body["body"]) == {"client_id": "c"}


def test_the_session_content_type_is_not_mutated_by_a_form_call(client):
    """The override is per-request; a later JSON call must not inherit it."""
    client.root_request("POST", "/auth/token", form={"a": "b"})
    assert client.session.headers["Content-Type"] == "application/json"
    _, body = client.root_request("POST", "/auth/login_flow", json_payload={"x": 1})
    assert "application/json" in body["content_type"]


def test_send_auth_true_carries_the_bearer(client):
    _, body = client.root_request("POST", "/auth/link_user", json_payload={"code": "c"})
    assert body["authorization"] == "Bearer tok-123"


def test_send_auth_false_removes_the_header_entirely(client):
    """Not an empty header — ABSENT. `requests` drops a session header whose
    per-request value is None."""
    _, body = client.root_request("GET", "/auth/providers", send_auth=False)
    assert body["authorization"] is None


def test_send_auth_false_does_not_mutate_the_session(client):
    client.root_request("GET", "/auth/providers", send_auth=False)
    _, body = client.root_request("GET", "/auth/providers")
    assert body["authorization"] == "Bearer tok-123"


def test_a_non_2xx_is_returned_not_raised(client):
    """The login flow reports a bad password as 200-with-errors and the token
    endpoint reports refusals as 400/403 carrying an OAuth `error` code.
    Raising on status would discard the diagnosis."""
    status, body = client.root_request("GET", "/teapot")
    assert status == 418
    assert body["path"] == "/teapot"


def test_params_are_sent(client):
    _, body = client.root_request("GET", "/auth/providers", params={"a": "1"})
    assert body["path"] == "/auth/providers?a=1"


def test_no_body_when_neither_form_nor_json(client):
    _, body = client.root_request("DELETE", "/auth/login_flow/abc")
    assert body["body"] == ""
    assert body["method"] == "DELETE"


def test_an_unreachable_host_raises_with_the_remedy():
    client = HomeAssistantClient(url="http://127.0.0.1:1", token="t", timeout=2)
    with pytest.raises(HomeAssistantError, match="Cannot reach Home Assistant"):
        client.root_request("GET", "/auth/providers")


def test_a_tokenless_client_sends_no_authorization(echo_server):
    """`auth login` runs on an instance there is no token for yet."""
    client = HomeAssistantClient(url=echo_server, token=None, timeout=5)
    _, body = client.root_request("GET", "/auth/providers")
    assert body["authorization"] is None
