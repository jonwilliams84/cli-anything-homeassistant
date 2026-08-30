"""Multipart frame capture against Home Assistant's REAL stream writer.

WHY THIS EXISTS RATHER THAN ANOTHER HAND-BUILT FIXTURE
    The client's job here is to parse a multipart stream, and the only thing
    that can prove it parses HA's stream is HA's stream. A fixture written by
    the same author as the parser encodes the same assumption twice and agrees
    with itself — which is exactly how the `--frameboundary` trap below would
    have been missed.

    So the camera route calls `homeassistant.components.camera.
    async_get_still_stream` — the actual function that serves
    `/api/camera_proxy_stream` — over a real TCP socket, and the client reads
    it with the same `requests` session it uses in production. The image route
    reproduces `ImageStreamView` using the image component's OWN constants
    (`FRAME_SEPARATOR`, `FRAME_BOUNDARY`) and its own frame-doubling, so a
    change to either upstream breaks this test rather than silently changing
    behaviour.

WHAT IT PINS
    * The two views declare INCOMPATIBLE boundaries. Camera declares
      `boundary=--frameboundary` — dashes baked into the value — and writes
      `--frameboundary`. Image declares `boundary=frame-boundary` and writes
      `\\r\\n--frame-boundary\\r\\n`. A parser that follows RFC 2046 and prepends
      `--` to the declared value works on one and hangs forever on the other.
      `test_camera_declares_a_boundary_that_is_already_dashed` asserts the trap
      is still there; the capture tests assert the client is immune to it.
    * The deliberate duplicate frames are collapsed, not written twice.
    * A stream that never ends is cut off by the deadline with
      `complete: false` instead of blocking.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
import requests

from cli_anything.homeassistant.core import media_proxy

aiohttp = pytest.importorskip("aiohttp", reason="aiohttp ships with homeassistant")
from aiohttp import web  # noqa: E402

ha_camera = pytest.importorskip(
    "homeassistant.components.camera", reason="needs the homeassistant package"
)
ha_image = pytest.importorskip("homeassistant.components.image")

JPEGS = [b"\xff\xd8FRAME-ONE\xff\xd9", b"\xff\xd8FRAME-TWO\xff\xd9", b"\xff\xd8FRAME-3\xff\xd9"]


class StreamServer:
    """Serves the two multipart views the way Home Assistant serves them."""

    def __init__(self, *, images=None, interval=0.5, endless=False):
        self.images = list(images if images is not None else JPEGS)
        self.interval = interval
        self.endless = endless
        self.url = ""
        self.camera_content_type = None
        self._loop = None
        self._runner = None
        self._thread = None
        self._ready = threading.Event()

    # ── /api/camera_proxy_stream/{entity_id} — HA's own writer, unmodified
    async def _camera(self, request):
        pending = list(self.images)

        async def image_cb():
            if pending:
                return pending.pop(0)
            if self.endless:
                # A camera that keeps serving the SAME frame forever: HA only
                # writes when the image changes, so nothing more is sent and
                # the connection just stays open. This is the hang the client
                # deadline exists for.
                await asyncio.sleep(3600)
            return None

        return await ha_camera.async_get_still_stream(
            request, image_cb, "image/jpeg", self.interval
        )

    # ── /api/image_proxy_stream/{entity_id} — ImageStreamView's framing
    async def _image(self, request):
        response = web.StreamResponse()
        response.content_type = ha_image.CONTENT_TYPE_MULTIPART.format(ha_image.FRAME_BOUNDARY)
        await response.prepare(request)
        for img in self.images:
            frame = bytearray(ha_image.FRAME_SEPARATOR)
            frame.extend(
                bytes(
                    f"Content-Type: image/png\r\nContent-Length: {len(img)}\r\n\r\n",
                    "utf-8",
                )
            )
            frame.extend(img)
            # ImageStreamView doubles EVERY frame, not just the first.
            frame.extend(frame)
            await response.write(frame)
        if self.endless:
            await asyncio.sleep(3600)
        else:
            await response.write(ha_image.LAST_FRAME_MARKER)
        return response

    async def _camera_error(self, request):
        return web.Response(status=int(request.match_info["code"]))

    def start(self):
        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            app = web.Application()
            app.router.add_get("/api/camera_proxy_stream/{entity_id}", self._camera)
            app.router.add_get("/api/image_proxy_stream/{entity_id}", self._image)
            app.router.add_get("/status/{code}", self._camera_error)
            self._runner = web.AppRunner(app)
            self._loop.run_until_complete(self._runner.setup())
            site = web.TCPSite(self._runner, "127.0.0.1", 0)
            self._loop.run_until_complete(site.start())
            port = site._server.sockets[0].getsockname()[1]
            self.url = f"http://127.0.0.1:{port}"
            self._ready.set()
            self._loop.run_forever()
            self._loop.run_until_complete(self._runner.cleanup())
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        assert self._ready.wait(20), "stream server never came up"
        return self

    def stop(self):
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=10)

    def client(self, timeout=20):
        """A minimal real client: a live `requests.Session` and a base_url."""

        class _Client:
            def __init__(self, base_url):
                self.base_url = base_url
                self.timeout = timeout
                self.session = requests.Session()
                self.session.headers.update(
                    {"Authorization": "Bearer test", "Content-Type": "application/json"}
                )

        return _Client(self.url)


@pytest.fixture
def serve():
    servers: list[StreamServer] = []

    def _make(**kwargs):
        server = StreamServer(**kwargs).start()
        servers.append(server)
        return server

    yield _make
    for server in servers:
        server.stop()


# ─────────────────────────────────────────────────── the incompatible framing


def test_camera_declares_a_boundary_that_is_already_dashed(serve):
    """The trap, asserted against HA's real writer.

    If this ever starts failing, HA has been fixed and the parser could be
    simplified — but until then a conformant `--` + boundary parser is wrong.
    """
    server = serve()
    resp = requests.get(f"{server.url}/api/camera_proxy_stream/camera.front", stream=True,
                        timeout=20)
    try:
        assert resp.headers["Content-Type"] == "multipart/x-mixed-replace; boundary=--frameboundary"
        # RFC 2046 says the delimiter is "--" + boundary. HA's own bytes are
        # NOT that, which is why the parser is length-driven.
        head = next(resp.iter_content(chunk_size=64))
        assert head.startswith(b"--frameboundary\r\n")
        assert not head.startswith(b"----frameboundary")
    finally:
        resp.close()


def test_image_declares_a_plain_boundary(serve):
    """...and the image view does the opposite, from the same constants."""
    server = serve()
    resp = requests.get(f"{server.url}/api/image_proxy_stream/image.doorbell", stream=True,
                        timeout=20)
    try:
        assert resp.headers["Content-Type"] == "multipart/x-mixed-replace; boundary=frame-boundary"
        head = next(resp.iter_content(chunk_size=64))
        assert head.startswith(b"\r\n--frame-boundary\r\n")
    finally:
        resp.close()


# ────────────────────────────────────────────────────────────── camera capture


def test_camera_capture_reads_has_real_stream(serve, tmp_path):
    server = serve()
    result = media_proxy.camera_capture(
        server.client(),
        entity_id="camera.front",
        output_dir=str(tmp_path / "shots"),
        frames=3,
        interval=0.5,
        timeout=20.0,
    )
    assert result["complete"] is True
    assert result["frames"] == 3
    assert [f["bytes"] for f in result["files"]] == [len(j) for j in JPEGS]
    written = [open(f["path"], "rb").read() for f in result["files"]]
    assert written == JPEGS
    assert all(f["content_type"] == "image/jpeg" for f in result["files"])


def test_camera_capture_collapses_has_deliberate_duplicate_first_frame(serve, tmp_path):
    """HA writes frame 1 twice so Chrome shows it. Three files, not four."""
    server = serve()
    result = media_proxy.camera_capture(
        server.client(),
        entity_id="camera.front",
        output_dir=str(tmp_path / "shots"),
        frames=3,
        interval=0.5,
        timeout=20.0,
    )
    assert result["duplicates_skipped"] >= 1
    files = sorted((tmp_path / "shots").iterdir())
    assert len(files) == 3
    assert len({p.read_bytes() for p in files}) == 3


def test_camera_frames_are_named_in_order_with_a_jpeg_extension(serve, tmp_path):
    server = serve()
    media_proxy.camera_capture(
        server.client(),
        entity_id="camera.front",
        output_dir=str(tmp_path / "shots"),
        frames=2,
        interval=0.5,
        timeout=20.0,
        prefix="cam",
    )
    names = sorted(p.name for p in (tmp_path / "shots").iterdir())
    assert names == ["cam-001.jpg", "cam-002.jpg"]


def test_camera_capture_stops_at_the_frame_budget(serve, tmp_path):
    """Asking for one frame must not drain the whole stream."""
    server = serve()
    result = media_proxy.camera_capture(
        server.client(),
        entity_id="camera.front",
        output_dir=str(tmp_path / "shots"),
        frames=1,
        interval=0.5,
        timeout=20.0,
    )
    assert result["frames"] == 1
    assert result["complete"] is True
    assert len(list((tmp_path / "shots").iterdir())) == 1


def test_camera_capture_refuses_to_clobber_existing_frames(serve, tmp_path):
    server = serve()
    out = tmp_path / "shots"
    out.mkdir()
    (out / "frame-001.jpg").write_bytes(b"old")
    with pytest.raises(FileExistsError, match="--prefix"):
        media_proxy.camera_capture(
            server.client(),
            entity_id="camera.front",
            output_dir=str(out),
            frames=1,
            interval=0.5,
            timeout=20.0,
        )


def test_camera_capture_overwrites_when_asked(serve, tmp_path):
    server = serve()
    out = tmp_path / "shots"
    out.mkdir()
    (out / "frame-001.jpg").write_bytes(b"old")
    result = media_proxy.camera_capture(
        server.client(),
        entity_id="camera.front",
        output_dir=str(out),
        frames=1,
        interval=0.5,
        timeout=20.0,
        overwrite=True,
    )
    assert result["frames"] == 1
    assert (out / "frame-001.jpg").read_bytes() == JPEGS[0]


# ─────────────────────────────────────────────────────────────── image capture


def test_image_capture_reads_the_doubled_image_framing(serve, tmp_path):
    """ImageStreamView duplicates EVERY frame — 3 images must yield 3 files."""
    server = serve()
    result = media_proxy.image_capture(
        server.client(),
        entity_id="image.doorbell",
        output_dir=str(tmp_path / "shots"),
        frames=3,
        timeout=20.0,
    )
    assert result["complete"] is True
    assert result["frames"] == 3
    # Six parts are on the wire (f1 f1 f2 f2 f3 f3) but only five are READ:
    # the third distinct frame satisfies the budget and the capture stops
    # before pulling its duplicate. Two duplicates skipped, not three.
    assert result["duplicates_skipped"] == 2
    assert [open(f["path"], "rb").read() for f in result["files"]] == JPEGS
    assert sorted(p.name for p in (tmp_path / "shots").iterdir()) == [
        "frame-001.png",
        "frame-002.png",
        "frame-003.png",
    ]


# ───────────────────────────────────────────────────────── bounded by deadline


def test_a_stream_that_never_ends_is_cut_off_not_hung(serve, tmp_path):
    """The whole reason `download()` cannot be used for these views."""
    server = serve(endless=True)
    started = time.monotonic()
    result = media_proxy.camera_capture(
        server.client(timeout=30),
        entity_id="camera.front",
        output_dir=str(tmp_path / "shots"),
        frames=10,          # more than the server will ever send
        interval=0.5,
        timeout=6.0,
    )
    elapsed = time.monotonic() - started
    assert elapsed < 25, f"capture did not honour its deadline (took {elapsed:.1f}s)"
    assert result["complete"] is False
    assert result["frames"] == len(JPEGS)
    assert "timeout" in result["note"]
    assert "--timeout" in result["note"]
