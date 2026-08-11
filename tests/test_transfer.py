"""Unit tests for the bytes-in/bytes-out cluster.

FakeClient has no `download`/`upload`, so these use a small recorder that
records exactly what the real client would be asked to send. The expectations
come from reading `backup/http.py`, `file_upload/__init__.py` and
`media_source/local_source.py` in the RUNNING 2026.8.1 source, and from a real
195MB download that reported 204523520 bytes against a matching
Content-Length.

REST endpoints covered:
  GET  backup/download/{id}                    — transfer.download_backup
  POST backup/upload                           — transfer.upload_backup
  POST file_upload                             — transfer.upload_file
  POST media_source/local_source/upload        — transfer.upload_media
  POST image/upload                            — transfer.upload_image
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import transfer


class RecordingClient:
    """Records download/upload the way the real client would receive them."""

    def __init__(self, download_result=None, upload_result=None):
        self.downloads: list[dict] = []
        self.uploads: list[dict] = []
        self._download_result = download_result or {}
        self._upload_result = upload_result or {}

    def download(self, path, dest, params=None, chunk_size=None):
        self.downloads.append({"path": path, "dest": str(dest), "params": params})
        return dict(self._download_result)

    def upload(self, path, file_path, field="file", params=None, extra_fields=None,
               content_type=None):
        self.uploads.append(
            {
                "path": path,
                "file_path": str(file_path),
                "field": field,
                "params": params,
                "extra_fields": extra_fields,
            }
        )
        return dict(self._upload_result)


@pytest.fixture
def tar_file(tmp_path):
    p = tmp_path / "backup.tar"
    p.write_bytes(b"x" * 1024)
    return p


@pytest.fixture
def png_file(tmp_path):
    p = tmp_path / "probe.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    return p


class TestDownloadBackup:
    def test_agent_id_is_a_repeated_query_param_not_a_dict(self, tmp_path):
        """HA reads it with query.getone()/getall(); a dict cannot repeat a key."""
        client = RecordingClient({"path": "x", "bytes": 10})
        transfer.download_backup(client, "abc", tmp_path / "out.tar", agent_id="backup.local")
        assert client.downloads[0]["params"] == [("agent_id", "backup.local")]

    def test_a_password_becomes_a_second_param(self, tmp_path):
        client = RecordingClient({"path": "x", "bytes": 10})
        transfer.download_backup(
            client, "abc", tmp_path / "out.tar", agent_id="backup.local", password="s3cret"
        )
        assert ("password", "s3cret") in client.downloads[0]["params"]

    def test_a_directory_destination_gets_the_backup_id_as_a_filename(self, tmp_path):
        client = RecordingClient({"path": "x", "bytes": 10})
        transfer.download_backup(client, "abc123", tmp_path, agent_id="backup.local")
        assert client.downloads[0]["dest"].endswith("abc123.tar")

    def test_a_missing_agent_id_is_refused_before_the_call(self, tmp_path):
        """HA answers an empty 400 — indistinguishable from a dozen failures."""
        client = RecordingClient()
        with pytest.raises(ValueError, match="empty 400"):
            transfer.download_backup(client, "abc", tmp_path, agent_id="")
        assert client.downloads == []

    def test_it_does_not_claim_the_content_was_verified(self, tmp_path):
        """HA sends no digest. Size is checked; content is not."""
        client = RecordingClient({"path": "x", "bytes": 10, "size_matches": True})
        got = transfer.download_backup(client, "abc", tmp_path, agent_id="backup.local")
        assert "no digest" in got["verification"].lower()
        assert got["size_matches"] is True
        # And it must not infer encryption from whether a password was passed —
        # that was wrong in the first version and is now simply reported.
        assert got["password_supplied"] is False
        assert "encrypted" not in got


class TestUploadBackup:
    def test_agent_ids_repeat(self, tar_file):
        client = RecordingClient(upload_result={"backup_id": "x"})
        transfer.upload_backup(client, tar_file, agent_ids=["backup.local", "backup.remote"])
        assert client.uploads[0]["params"] == [
            ("agent_id", "backup.local"),
            ("agent_id", "backup.remote"),
        ]

    def test_no_agent_is_refused(self, tar_file):
        with pytest.raises(ValueError, match="agent-id"):
            transfer.upload_backup(RecordingClient(), tar_file, agent_ids=[])

    def test_a_missing_file_is_refused_before_the_call(self, tmp_path):
        client = RecordingClient()
        with pytest.raises(FileNotFoundError):
            transfer.upload_backup(client, tmp_path / "nope.tar", agent_ids=["backup.local"])
        assert client.uploads == []


class TestUploadFile:
    def test_the_field_must_be_named_file(self, tmp_path):
        """`/api/file_upload` rejects any other name with `Expected a file`."""
        f = tmp_path / "cert.pem"
        f.write_text("x")
        client = RecordingClient(upload_result={"file_id": "abc"})
        got = transfer.upload_file(client, f)
        assert client.uploads[0]["field"] == "file"
        assert got["file_id"] == "abc"

    def test_it_says_the_file_is_staged_not_stored(self, tmp_path):
        f = tmp_path / "cert.pem"
        f.write_text("x")
        got = transfer.upload_file(RecordingClient(upload_result={"file_id": "a"}), f)
        assert "reaps" in got["note"]


class TestUploadMedia:
    def test_a_non_media_content_type_is_refused_locally(self, tmp_path):
        """HA checks image/ video/ audio/ and answers a BARE 400.

        The reason ("Content type not allowed") goes to HA's log and never to
        the caller — measured on a real instance — so refusing here is the only
        way the cause is ever visible.
        """
        f = tmp_path / "notes.txt"
        f.write_text("x")
        client = RecordingClient()
        with pytest.raises(ValueError, match="image/\\*, video/\\* and audio/\\*"):
            transfer.upload_media(client, f, media_content_id="media-source://media_source/.")
        assert client.uploads == []

    def test_an_image_passes_the_check(self, png_file):
        client = RecordingClient(upload_result={"media_content_id": "x"})
        transfer.upload_media(
            client, png_file, media_content_id="media-source://media_source/snapshots/."
        )
        assert client.uploads[0]["extra_fields"] == {
            "media_content_id": "media-source://media_source/snapshots/."
        }

    def test_a_missing_destination_is_refused(self, png_file):
        with pytest.raises(ValueError, match="media browse"):
            transfer.upload_media(RecordingClient(), png_file, media_content_id="")

    def test_the_allowed_prefixes_are_read_from_has_source_not_invented(self):
        assert transfer.MEDIA_CONTENT_PREFIXES == ("image/", "video/", "audio/")


class TestUploadImage:
    def test_it_reports_the_serve_path(self, png_file):
        client = RecordingClient(upload_result={"id": "abc", "content_type": "image/png"})
        got = transfer.upload_image(client, png_file)
        assert got["image_id"] == "abc"
        assert got["serve_path"] == "/api/image/serve/abc/original"

    def test_no_id_means_no_serve_path_rather_than_a_broken_one(self, png_file):
        got = transfer.upload_image(RecordingClient(upload_result={}), png_file)
        assert got["image_id"] is None
        assert got["serve_path"] is None
