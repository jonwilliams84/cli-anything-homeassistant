"""Getting bytes in and out of Home Assistant — backups, media, images, files.

THE GAP THIS CLOSES
    The harness could `backup create`, `backup list`, `backup show` and
    `backup restore`, and could not get a backup OFF THE BOX. Every one of
    those commands talks to HA about a file that stays where it is. For
    disaster recovery — the entire reason a backup exists — that is the wrong
    half: what you need is the tarball on other storage, and the ability to
    push one back to a rebuilt instance.

    Four REST endpoints do the work and none of them was reachable:

        GET  /api/backup/download/{backup_id}?agent_id=…   the tarball
        POST /api/backup/upload?agent_id=…                 push one back
        POST /api/file_upload                              -> {file_id}
        POST /api/media_source/local_source/upload         media library

    Plus `/api/image/upload` for the image_upload integration.

THREE THINGS THAT ARE NOT OBVIOUS AND WERE READ OUT OF HA'S SOURCE
    1. `agent_id` IS REQUIRED AND REPEATABLE. `backup/http.py` reads it with
       `request.query.getone()` on download and `getall()` on upload, so a
       backup can be pushed to several agents at once — and a plain dict of
       query params cannot express a repeated key. `download()` and `upload()`
       on the client take a list of pairs for exactly this.
    2. THE MULTIPART FIELD NAME MATTERS FOR ONE ENDPOINT AND NOT THE OTHER.
       `/api/file_upload` rejects any part not named `file`
       (`file_field_reader.name != "file"` -> `vol.Invalid("Expected a file")`),
       while `/api/backup/upload` reads the first part whatever it is called.
    3. A MISSING `agent_id` IS A BARE 400 WITH NO BODY. HA returns
       `Response(status=HTTPStatus.BAD_REQUEST)` — no message, nothing naming
       the missing parameter. That is why the agent id is required by these
       functions rather than defaulted.

WHAT IS AND IS NOT VERIFIED
    HA sends no digest, so no checksum is claimed and none is invented. It DOES
    send a `Content-Length` — measured on a real 195MB backup, which reported
    204523520 and wrote exactly that — so a TRUNCATED transfer is detectable
    and `size_matches` reports it. That field is None rather than False when
    nothing was declared, because "not checked" and "checked and wrong" must
    not read alike.

    The downloaded file was opened with `tarfile` and contains `backup.json`
    and `homeassistant.tar.gz`, which is what makes this a restore path rather
    than a byte count.
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Optional

_LOGGER = logging.getLogger(__name__)

BACKUP_DOWNLOAD = "backup/download/{backup_id}"
BACKUP_UPLOAD = "backup/upload"
FILE_UPLOAD = "file_upload"
MEDIA_UPLOAD = "media_source/local_source/upload"
IMAGE_UPLOAD = "image/upload"

#: What `/api/media_source/local_source/upload` will accept. Read out of
#: `local_source.py`, not guessed — anything else is a bare 400.
MEDIA_CONTENT_PREFIXES = ("image/", "video/", "audio/")


def _agent_params(agent_ids: list[str]) -> list[tuple[str, str]]:
    """Query params as PAIRS, so `agent_id` can repeat.

    `{"agent_id": [...]}` would work with requests too, but a list of pairs is
    the shape that cannot be accidentally collapsed by a caller building on
    this, and it mirrors what HA's `query.getall()` reads.
    """
    return [("agent_id", a) for a in agent_ids]


def download_backup(
    client,
    backup_id: str,
    dest,
    *,
    agent_id: str,
    password: Optional[str] = None,
) -> dict:
    """Stream a backup tarball to `dest`.

    `agent_id` is required: HA answers a missing one with a bare 400 and no
    body, which is indistinguishable from a dozen other failures. Run
    `backup agents` for the ids this instance has.
    """
    if not agent_id:
        raise ValueError(
            "agent_id is required — HA answers a missing one with an empty 400. "
            "Run `backup agents` for the ids this instance has."
        )
    dest = Path(dest)
    if dest.is_dir():
        dest = dest / f"{backup_id}.tar"
    params = _agent_params([agent_id])
    if password:
        params.append(("password", password))
    result = client.download(BACKUP_DOWNLOAD.format(backup_id=backup_id), dest, params=params)
    return {
        "backup_id": backup_id,
        "agent_id": agent_id,
        # Whether the BACKUP is encrypted is a property of the backup, reported
        # by `backup list` as `protected`. The first version inferred it from
        # whether a password was passed, which is not the same thing and was
        # simply wrong; guessing here has been removed rather than corrected.
        "password_supplied": bool(password),
        **result,
        "verification": (
            "Size checked against HA's Content-Length. No digest is sent by HA, "
            "so content is not verified — open it with `tar tf` to be sure."
        ),
    }


def upload_backup(client, file_path, *, agent_ids: list[str]) -> dict:
    """Push a backup tarball back into HA, to one or more agents."""
    if not agent_ids:
        raise ValueError(
            "At least one --agent-id is required — HA answers a missing one with "
            "an empty 400. Run `backup agents` for the ids this instance has."
        )
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"No such backup file: {file_path}")
    result = client.upload(
        BACKUP_UPLOAD,
        file_path,
        # The name is not read by this endpoint — it takes the first part —
        # but sending something meaningful keeps the request self-describing.
        field="file",
        params=_agent_params(agent_ids),
    )
    return {
        "file": str(file_path),
        "bytes": file_path.stat().st_size,
        "agent_ids": agent_ids,
        "result": result,
    }


def upload_file(client, file_path) -> dict:
    """Upload a file to HA's staging area and return its `file_id`.

    This is the endpoint config flows use for a certificate, a keyfile or an
    image: you upload, get a `file_id`, and hand that id to the flow. The file
    is NOT permanent — HA deletes unclaimed uploads — so the id is the whole
    product.

    The multipart field MUST be named `file`; HA raises `Expected a file`
    otherwise, and that error names nothing useful.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"No such file: {file_path}")
    result = client.upload(FILE_UPLOAD, file_path, field="file")
    file_id = (result or {}).get("file_id") if isinstance(result, dict) else None
    return {
        "file": str(file_path),
        "bytes": file_path.stat().st_size,
        "file_id": file_id,
        "raw": result,
        "note": (
            "Staged, not stored. Hand file_id to a config flow; HA reaps "
            "unclaimed uploads."
        ),
    }


def upload_media(client, file_path, *, media_content_id: str) -> dict:
    """Upload a file into the local media library.

    `media_content_id` is a media-source id naming the FOLDER — the shape
    `media browse` returns, e.g. `media-source://media_source/local/.`. It is
    required because HA has no default destination.
    """
    if not media_content_id:
        raise ValueError(
            "media_content_id is required — run `media browse` and use the "
            "media_content_id of the destination folder."
        )
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"No such file: {file_path}")
    # HA checks `content_type.startswith(("image/", "video/", "audio/"))` and
    # answers a BARE 400 — the reason goes to its log, not to the caller.
    # Measured: a .txt upload returns 400 and "Content type not allowed"
    # appears only in `kubectl logs`. Refusing here names the real cause.
    guessed = mimetypes.guess_type(str(file_path))[0]
    if not (guessed or "").startswith(MEDIA_CONTENT_PREFIXES):
        raise ValueError(
            f"HA's media library only accepts image/*, video/* and audio/* — "
            f"{file_path.name} looks like {guessed or 'an unknown type'}. HA "
            "answers a bare 400 for this and logs the reason server-side only."
        )
    result = client.upload(
        MEDIA_UPLOAD,
        file_path,
        field="file",
        extra_fields={"media_content_id": media_content_id},
    )
    return {
        "file": str(file_path),
        "bytes": file_path.stat().st_size,
        "media_content_id": media_content_id,
        "result": result,
    }


def upload_image(client, file_path) -> dict:
    """Upload an image to the `image_upload` integration.

    Returns the stored image record, whose `id` is what a person avatar or a
    dashboard background refers to. Served afterwards from
    `/api/image/serve/<id>/<size>`.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"No such image: {file_path}")
    result = client.upload(IMAGE_UPLOAD, file_path, field="file")
    image_id = (result or {}).get("id") if isinstance(result, dict) else None
    return {
        "file": str(file_path),
        "bytes": file_path.stat().st_size,
        "image_id": image_id,
        "serve_path": f"/api/image/serve/{image_id}/original" if image_id else None,
        "raw": result,
    }


def local_size(path) -> Optional[int]:
    """Size of a local file, or None. Used by the CLI to report before/after."""
    try:
        return os.path.getsize(path)
    except OSError:
        return None
