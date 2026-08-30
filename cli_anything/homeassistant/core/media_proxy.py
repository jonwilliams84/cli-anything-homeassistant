"""Binary media proxy endpoints — get the BYTES an entity is actually serving.

The harness could describe a camera in complete detail and could not show you
what it sees. `camera capabilities` / `stream` / `prefs-get` read the wiring,
`camera_ws` negotiates WebRTC — but none of them returns a pixel. The still
image lives on a REST endpoint (`/api/camera_proxy/<entity_id>`) that nothing
here called. `image snapshot` existed for `image.*` entities only; the
`camera.*` domain, the MJPEG streams for both, and media-player artwork had no
command at all.

This module wraps the four binary GET views:

    /api/camera_proxy/{entity_id}          CameraImageView      still frame
    /api/camera_proxy_stream/{entity_id}   CameraMjpegStream    MJPEG stream
    /api/image_proxy_stream/{entity_id}    ImageStreamView      still stream
    /api/media_player_proxy/{entity_id}    MediaPlayerImageView artwork

MEASURED AGAINST THE SOURCE OF THE RUNNING VERSION
    Every status code, query parameter and framing detail below was read off
    `components/camera/__init__.py`, `components/image/__init__.py` and
    `components/media_player/__init__.py`. Where HA answers with a bare status
    and no body — which is most of the failure modes — the remedy is named
    here, client-side, because the wire carries nothing to name it with.

WHAT MAKES THESE ENDPOINTS DIFFERENT FROM EVERY OTHER ONE IN THIS HARNESS

    * `requires_auth = False`, AND THAT DOES NOT MEAN UNAUTHENTICATED.
      All three views set it, then check `request[KEY_AUTHENTICATED]` or a
      per-entity `access_token` by hand. The bearer header still works. What
      changes is the REFUSAL: with an `Authorization` header present HA raises
      401, and with none at all it raises **403** (camera/image) or **401**
      (media_player, which also answers 401 for an entity that does not
      exist). A 403 here means "your signed URL is wrong or expired", not
      "your user lacks permission".

    * A camera that is OFF is a 503, not a 404 and not an empty image.
      `CameraView.get` checks `camera.is_on` before dispatching and raises
      `HTTPServiceUnavailable` with no body. `camera snapshot` on a disabled
      camera therefore fails in a way that looks like the SERVER is broken.
      `_raise_for_status` says `camera.turn_on` instead.

    * `width`/`height` only do something when BOTH are given AND the image is
      a JPEG. `_async_get_image` forwards them to `async_camera_image()`
      (best-effort, most platforms ignore them) and only actually rescales in
      the `width is not None and height is not None and ("jpeg" in
      content_type or "jpg" in content_type)` branch. A lone `--width` is
      silently a no-op, so it is refused here rather than returning a
      full-size image that the caller believes was resized.

    * The MJPEG stream NEVER ENDS. `CameraMjpegStream` loops until the client
      goes away; `ImageStreamView` blocks on a state-change event forever.
      Handing either to `client.download()` writes an infinitely growing file.
      Every capture here is bounded by BOTH a frame budget and a deadline, and
      closes the response to make HA stop.

    * THE FIRST FRAME IS SENT TWICE — DELIBERATELY, AND DIFFERENTLY IN EACH.
      Chrome renders the n-1 frame of a multipart stream, so HA compensates:
      the camera still-stream writes the first frame twice
      (`if last_image is None: await write_to_mjpeg_stream(img_bytes)`), and
      the image stream duplicates EVERY frame (`frame.extend(frame)`). A
      naive capture of 3 frames therefore returns 2 distinct images from a
      camera and 1 or 2 from an image entity. Consecutive identical parts are
      collapsed here and counted in `duplicates_skipped`. HA never emits two
      consecutive identical frames for any other reason — the camera loop
      writes only `if img_bytes != last_image` — so this cannot drop a real
      frame.

    * THE TWO STREAMS DISAGREE ABOUT WHAT A MIME BOUNDARY IS. The image view
      declares `boundary=frame-boundary` and writes `\\r\\n--frame-boundary\\r\\n`
      — standard. The camera view declares `boundary=--frameboundary`, with
      the dashes baked INTO the declared value, and writes `--frameboundary`
      verbatim. A conformant parser that prepends `--` to the declared
      boundary reads the image stream and hangs forever on the camera one.
      `_iter_parts` ignores the boundary entirely and drives off the
      per-part `Content-Length`, which both views always send.

    * `interval` on the camera stream is validated as `< MIN_STREAM_INTERVAL`
      but the error text says `must be > 0.5`. 0.5 exactly is ACCEPTED; the
      message is wrong. Below it, HA answers a bare 400. Checked here at
      `>= 0.5` — matching the code, not the sentence.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Iterator, Optional

import requests

from cli_anything.homeassistant.core import auth_tokens as auth_tokens_core
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

#: What `requests` raises when a streamed body goes quiet. A read timeout
#: surfaces as `ConnectionError` (it wraps urllib3's `ReadTimeoutError`), NOT
#: as `Timeout` — so catching `Timeout` alone leaves the traceback in place.
_STALL_ERRORS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
)

#: `MIN_STREAM_INTERVAL` from `components/camera/__init__.py`. The comparison
#: there is `interval < MIN_STREAM_INTERVAL`, so this value itself is legal.
MIN_STREAM_INTERVAL = 0.5

#: `CAMERA_IMAGE_TIMEOUT` from `components/camera/const.py` — how long HA will
#: wait for the platform before turning the request into a 500.
CAMERA_IMAGE_TIMEOUT = 10

#: Extensions for the content types these views actually return.
_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}


# ─────────────────────────────────────────────────────────────── validation


def _require_entity(entity_id: str, domain: str) -> None:
    """Refuse an entity_id that is empty or outside *domain*.

    The article is picked from the domain so the message reads the same way
    `image.snapshot` has always phrased it ("is not an image.* entity") — an
    error that reads wrong gets read as a bug in the tool.
    """
    if not entity_id:
        raise ValueError("entity_id is required")
    if not entity_id.startswith(f"{domain}."):
        article = "an" if domain[0] in "aeiou" else "a"
        raise ValueError(f"{entity_id!r} is not {article} {domain}.* entity")


def _require_absent(output_path: str, overwrite: bool) -> None:
    if not output_path:
        raise ValueError("output_path is required")
    if os.path.exists(output_path) and not overwrite:
        raise FileExistsError(f"{output_path} already exists — pass overwrite=True (--overwrite)")


def _validate_dimensions(width: Optional[int], height: Optional[int]) -> None:
    """Refuse a resize request HA would silently ignore.

    `_async_get_image` only rescales when both are present; a lone `--width`
    is forwarded to the platform, almost universally dropped, and the caller
    gets a full-size image believing otherwise. Fail loudly instead.
    """
    if width is None and height is None:
        return
    if width is None or height is None:
        raise ValueError(
            "--width and --height must be given together: Home Assistant only "
            "rescales when both are present (and only for JPEG cameras). One "
            "alone is passed to the camera platform, which almost always "
            "ignores it, and you would get a full-size image back with no error."
        )
    for name, value in (("width", width), ("height", height)):
        if value <= 0:
            raise ValueError(f"{name} must be a positive integer, got {value!r}")


def _validate_capture(frames: int, timeout: float, interval: Optional[float]) -> None:
    """Refuse a capture that cannot finish, before opening the stream."""
    if frames < 1:
        raise ValueError(f"frames must be >= 1, got {frames!r}")
    if timeout <= 0:
        raise ValueError(f"timeout must be > 0, got {timeout!r}")
    if interval is None:
        return
    if interval < MIN_STREAM_INTERVAL:
        raise ValueError(
            f"interval must be >= {MIN_STREAM_INTERVAL} (Home Assistant rejects "
            f"anything below it with a bare 400; its own message says "
            f"'must be > {MIN_STREAM_INTERVAL}' but the check is '<', so "
            f"{MIN_STREAM_INTERVAL} exactly is accepted), got {interval!r}"
        )
    needed = frames * interval
    if timeout < needed:
        raise ValueError(
            f"timeout={timeout}s cannot capture {frames} frames at {interval}s "
            f"apart — that needs at least {needed:g}s. Raise --timeout or lower "
            f"--frames."
        )


# ──────────────────────────────────────────────────────────────── transport


def _session_of(client) -> tuple[Any, str, float]:
    """Return `(session, base_url, timeout)` or explain what is missing."""
    sess = getattr(client, "session", None)
    base = getattr(client, "base_url", None)
    if sess is None or base is None:
        raise ValueError("client lacks an HTTP session — cannot fetch binary media")
    return sess, base, getattr(client, "timeout", 30)


def _open(
    client,
    path: str,
    *,
    params: Optional[dict] = None,
    signed: bool = False,
    expires: int = 30,
    timeout: Optional[float] = None,
):
    """GET *path* as a streamed response, signed or with the bearer header.

    `signed` mints a one-shot URL through `auth/sign_path` and then sends the
    request with the `Authorization` header REMOVED — which matters more here
    than anywhere else in the harness, because these views answer a bare 403
    when no header is present and a 401 when a bad one is. Leaving the header
    on a signed request turns "signature rejected" into "token rejected".
    """
    sess, base, default_timeout = _session_of(client)
    timeout = default_timeout if timeout is None else timeout

    if signed:
        result = auth_tokens_core.sign_path(client, path=path, expires=expires) or {}
        signed_path = result.get("path")
        if not signed_path:
            raise HomeAssistantError("auth/sign_path returned no signed path")
        headers = {k: v for k, v in sess.headers.items() if k.lower() != "authorization"}
        return sess.get(
            f"{base}{signed_path}", params=params, headers=headers, timeout=timeout, stream=True
        )
    return sess.get(f"{base}{path}", params=params, timeout=timeout, stream=True)


def _raise_for_status(resp, *, path: str, entity_id: str, kind: str, signed: bool) -> None:
    """Turn a bodyless status into a sentence that names the remedy.

    Every failure mode of these views is a bare status code. `resp.text` is
    empty for all of them, so an error built from the response alone reads
    "GET … -> 503:" and tells the operator nothing.
    """
    if getattr(resp, "ok", False):
        return
    status = getattr(resp, "status_code", 0)
    body = ""
    try:
        if resp.content:
            body = resp.text[:300]
    except Exception:  # noqa: BLE001 - a stream may not expose .content
        body = ""

    hint = ""
    if status == 404:
        hint = (
            f"no such {kind} entity {entity_id!r} — check `{kind} list` "
            f"(HA returns 404 before it looks at authentication)"
        )
    elif status == 401:
        hint = (
            "Home Assistant rejected the bearer token. Re-check --token / HASS_TOKEN."
            if not signed
            else "the signed URL was rejected; it may have expired — raise --expires"
        )
    elif status == 403:
        hint = (
            "no credentials reached Home Assistant. This view answers 403 when "
            "the request carries NO Authorization header — with --signed that "
            "means the signature was missing or malformed"
        )
    elif status == 503:
        hint = (
            f"{entity_id} is OFF. `CameraView.get` refuses before taking a "
            f"picture; turn it on with `camera turn-on {entity_id}` "
            f"(homeassistant.turn_on) and retry"
        )
    elif status == 502:
        hint = (
            f"{entity_id} produced no MJPEG stream. Not every camera platform "
            f"implements one; try `camera snapshot` (single still) or "
            f"`camera capture --interval 1.0`, which HA composes from stills "
            f"instead"
        )
    elif status == 400:
        hint = (
            f"Home Assistant rejected the stream interval — it must be >= "
            f"{MIN_STREAM_INTERVAL}"
        )
    elif status == 500:
        hint = (
            f"Home Assistant could not produce an image for {entity_id} "
            f"(camera/image: the platform did not answer within "
            f"{CAMERA_IMAGE_TIMEOUT}s; media_player: there is no artwork for "
            f"what is playing)"
        )
    raise HomeAssistantError(f"GET {path} -> {status}: {hint or body}")


# ────────────────────────────────────────────────────────── multipart frames


def _parse_part_headers(blob: bytes) -> tuple[Optional[str], Optional[int]]:
    """Pull `Content-Type` and `Content-Length` out of one part's header block.

    The block may still carry the boundary line in front of it; that is
    ignored on purpose (see the module docstring — the two views declare their
    boundary incompatibly, and `Content-Length` is the only field both send).
    """
    ctype: Optional[str] = None
    length: Optional[int] = None
    for line in blob.split(b"\r\n"):
        lowered = line.lower()
        if lowered.startswith(b"content-type:"):
            ctype = line.split(b":", 1)[1].strip().decode("utf-8", "replace")
        elif lowered.startswith(b"content-length:"):
            raw = line.split(b":", 1)[1].strip()
            if raw.isdigit():
                length = int(raw)
    return ctype, length


def _iter_parts(resp, *, deadline: float, max_parts: int, chunk_size: int = 65536) -> Iterator[tuple]:
    """Yield `(content_type, payload)` for each part, bounded by both limits.

    Length-driven rather than boundary-driven. The deadline is checked between
    socket reads; a stream that goes completely silent is cut off by the
    request's own read timeout, which the caller sets from the same budget.
    """
    buf = bytearray()
    emitted = 0
    stream = resp.iter_content(chunk_size=chunk_size)
    exhausted = False

    while emitted < max_parts:
        if time.monotonic() > deadline:
            return
        sep = buf.find(b"\r\n\r\n")
        if sep != -1:
            ctype, length = _parse_part_headers(bytes(buf[:sep]))
            if length is None:
                raise HomeAssistantError(
                    "multipart part had no Content-Length — this is not a "
                    "Home Assistant camera/image stream"
                )
            body_start = sep + 4
            if len(buf) >= body_start + length:
                payload = bytes(buf[body_start : body_start + length])
                del buf[: body_start + length]
                emitted += 1
                yield ctype, payload
                continue
        if exhausted:
            return
        try:
            chunk = next(stream)
        except StopIteration:
            exhausted = True
            continue
        except _STALL_ERRORS:
            # A stream with nothing left to say does not close — it goes
            # quiet. `CameraMjpegStream` writes only when the image CHANGES
            # and `ImageStreamView` waits on a state-change event, so a static
            # entity leaves the socket open and silent forever. The read
            # timeout (set from this same deadline) fires and `requests` turns
            # it into a ConnectionError. That is the deadline working, not a
            # failure: return what was captured and let the caller report
            # `complete: false`.
            _LOGGER.debug("stream stalled; ending capture at the deadline", exc_info=True)
            return
        if chunk:
            buf.extend(chunk)


def _capture(
    client,
    *,
    entity_id: str,
    domain: str,
    path: str,
    params: Optional[dict],
    output_dir: str,
    frames: int,
    timeout: float,
    prefix: str,
    overwrite: bool,
    signed: bool,
    expires: int,
) -> dict:
    """Shared body of `camera_capture` / `image_capture`."""
    if not output_dir:
        raise ValueError("output_dir is required")

    deadline = time.monotonic() + timeout
    # HA doubles the first frame (camera) or every frame (image), so allow for
    # twice the budget of parts plus slack before giving up on distinctness.
    max_parts = frames * 2 + 2

    resp = _open(client, path, params=params, signed=signed, expires=expires, timeout=timeout)
    written: list[dict] = []
    duplicates = 0
    previous: Optional[bytes] = None
    try:
        _raise_for_status(resp, path=path, entity_id=entity_id, kind=domain, signed=signed)
        os.makedirs(output_dir, exist_ok=True)
        for ctype, payload in _iter_parts(resp, deadline=deadline, max_parts=max_parts):
            if payload == previous:
                duplicates += 1
                continue
            previous = payload
            ext = _EXTENSIONS.get((ctype or "").split(";")[0].strip().lower(), ".bin")
            dest = os.path.join(output_dir, f"{prefix}-{len(written) + 1:03d}{ext}")
            if os.path.exists(dest) and not overwrite:
                raise FileExistsError(
                    f"{dest} already exists — pass overwrite=True (--overwrite) "
                    f"or choose another --prefix"
                )
            with open(dest, "wb") as fh:
                fh.write(payload)
            written.append(
                {"path": os.path.abspath(dest), "bytes": len(payload), "content_type": ctype}
            )
            if len(written) >= frames:
                break
    finally:
        # Closing is what makes HA stop; the stream has no natural end.
        try:
            resp.close()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("closing %s stream failed", domain, exc_info=True)

    complete = len(written) >= frames
    return {
        "entity_id": entity_id,
        "output_dir": os.path.abspath(output_dir),
        "requested_frames": frames,
        "frames": len(written),
        "files": written,
        "duplicates_skipped": duplicates,
        "complete": complete,
        "note": (
            f"captured {len(written)} of {frames} frame(s)"
            if complete
            else (
                f"only {len(written)} of {frames} frame(s) arrived before the "
                f"{timeout}s timeout — an entity that is not updating produces "
                f"no new parts; raise --timeout or lower --frames"
            )
        ),
    }


# ──────────────────────────────────────────────────────────── camera stills


def camera_snapshot(
    client,
    *,
    entity_id: str,
    output_path: str,
    overwrite: bool = False,
    width: Optional[int] = None,
    height: Optional[int] = None,
    signed: bool = False,
    expires: int = 30,
) -> dict:
    """Fetch the current frame from a camera and write it to *output_path*.

    Returns ``{"entity_id", "output_path", "bytes", "content_type",
    "requested_width", "requested_height", "resized"}``.

    `resized` is the honest answer to "did --width/--height do anything": HA
    only rescales JPEG, so a PNG camera returns full-size bytes with no error
    and this reports False.
    """
    _require_entity(entity_id, "camera")
    _require_absent(output_path, overwrite)
    _validate_dimensions(width, height)

    path = f"/api/camera_proxy/{entity_id}"
    params = {}
    if width is not None and height is not None:
        params = {"width": width, "height": height}

    resp = _open(client, path, params=params or None, signed=signed, expires=expires)
    _raise_for_status(resp, path=path, entity_id=entity_id, kind="camera", signed=signed)

    parent = os.path.dirname(os.path.abspath(output_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    total = 0
    with open(output_path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                fh.write(chunk)
                total += len(chunk)

    content_type = resp.headers.get("Content-Type")
    is_jpeg = "jpeg" in (content_type or "").lower() or "jpg" in (content_type or "").lower()
    return {
        "entity_id": entity_id,
        "output_path": os.path.abspath(output_path),
        "bytes": total,
        "content_type": content_type,
        "requested_width": width,
        "requested_height": height,
        # Not "did you ask" — "did HA actually do it".
        "resized": bool(width and height and is_jpeg),
    }


def camera_capture(
    client,
    *,
    entity_id: str,
    output_dir: str,
    frames: int = 1,
    interval: Optional[float] = None,
    timeout: float = 30.0,
    prefix: str = "frame",
    overwrite: bool = False,
    signed: bool = False,
    expires: int = 30,
) -> dict:
    """Capture *frames* distinct frames from a camera's MJPEG stream.

    With *interval* HA composes the stream from stills at that spacing
    (`handle_async_still_stream`); without it, the camera's native MJPEG
    stream is used, and a platform that has none answers 502.
    """
    _require_entity(entity_id, "camera")
    _validate_capture(frames, timeout, interval)
    return _capture(
        client,
        entity_id=entity_id,
        domain="camera",
        path=f"/api/camera_proxy_stream/{entity_id}",
        params={"interval": interval} if interval is not None else None,
        output_dir=output_dir,
        frames=frames,
        timeout=timeout,
        prefix=prefix,
        overwrite=overwrite,
        signed=signed,
        expires=expires,
    )


def image_capture(
    client,
    *,
    entity_id: str,
    output_dir: str,
    frames: int = 1,
    timeout: float = 30.0,
    prefix: str = "frame",
    overwrite: bool = False,
    signed: bool = False,
    expires: int = 30,
) -> dict:
    """Capture *frames* distinct frames from an image entity's still stream.

    Unlike the camera stream this has no interval: `ImageStreamView` pushes a
    frame when the entity's state changes and otherwise re-sends every 55s to
    stop devices going blank. A static image entity will therefore yield ONE
    distinct frame and then block — which is why the result reports
    `complete: false` rather than hanging.
    """
    _require_entity(entity_id, "image")
    _validate_capture(frames, timeout, None)
    return _capture(
        client,
        entity_id=entity_id,
        domain="image",
        path=f"/api/image_proxy_stream/{entity_id}",
        params=None,
        output_dir=output_dir,
        frames=frames,
        timeout=timeout,
        prefix=prefix,
        overwrite=overwrite,
        signed=signed,
        expires=expires,
    )


# ──────────────────────────────────────────────────────── media player art


def media_player_artwork(
    client,
    *,
    entity_id: str,
    output_path: str,
    overwrite: bool = False,
    media_content_type: Optional[str] = None,
    media_content_id: Optional[str] = None,
    media_image_id: Optional[str] = None,
    signed: bool = False,
    expires: int = 30,
) -> dict:
    """Download the artwork a media player is showing, or a browse-media thumb.

    With no `media_content_type`/`media_content_id` this is
    `async_get_media_image()` — the cover art for what is playing now. With
    both, it is `async_get_browse_image()`, the thumbnail for one node of the
    `media_player browse` tree, which is the only way to get those bytes: the
    URLs `media_player/browse_media` returns point straight back here.

    Note the 500: HA answers `Response(status=500)` when `data is None`, i.e.
    when there simply is no artwork. That is a normal outcome for a stopped
    player, not a server fault, and `_raise_for_status` says so.
    """
    _require_entity(entity_id, "media_player")
    _require_absent(output_path, overwrite)
    if bool(media_content_type) != bool(media_content_id):
        raise ValueError(
            "media_content_type and media_content_id must be given together — "
            "HA routes on the pair; one alone falls back to the currently "
            "playing artwork and silently ignores what you asked for."
        )

    path = f"/api/media_player_proxy/{entity_id}"
    if media_content_type and media_content_id:
        path = f"{path}/browse_media/{media_content_type}/{media_content_id}"
    params = {"media_image_id": media_image_id} if media_image_id else None

    resp = _open(client, path, params=params, signed=signed, expires=expires)
    _raise_for_status(resp, path=path, entity_id=entity_id, kind="media_player", signed=signed)

    parent = os.path.dirname(os.path.abspath(output_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    total = 0
    with open(output_path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                fh.write(chunk)
                total += len(chunk)

    return {
        "entity_id": entity_id,
        "output_path": os.path.abspath(output_path),
        "bytes": total,
        "content_type": resp.headers.get("Content-Type"),
        "browse_media": bool(media_content_type and media_content_id),
        "media_content_type": media_content_type,
        "media_content_id": media_content_id,
    }


def proxy_url(
    client,
    *,
    entity_id: str,
    signed: bool = True,
    expires: int = 30,
    stream: bool = False,
) -> dict:
    """Build the camera proxy URL, signed by default.

    Mirrors `image proxy_url` for the camera domain. A signed URL is the only
    way to hand a camera still to something that cannot set headers — a
    browser tag, an `<img>` in a notification, `curl` in a foreign shell.
    """
    _require_entity(entity_id, "camera")
    view = "camera_proxy_stream" if stream else "camera_proxy"
    path = f"/api/{view}/{entity_id}"
    base = getattr(client, "base_url", "") or ""

    if not signed:
        return {
            "entity_id": entity_id,
            "path": path,
            "url": f"{base}{path}" if base else path,
            "signed": False,
            "expires": None,
            "stream": stream,
        }

    result = auth_tokens_core.sign_path(client, path=path, expires=expires) or {}
    signed_path = result.get("path") or path
    return {
        "entity_id": entity_id,
        "path": signed_path,
        "url": f"{base}{signed_path}" if base else signed_path,
        "signed": True,
        "expires": expires,
        "stream": stream,
    }
