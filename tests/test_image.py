"""Unit tests for cli_anything.homeassistant.core.image."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cli_anything.homeassistant.core import image


_SAMPLE_IMAGE_ENTITY = {
    "entity_id": "image.doorbell",
    "state": "2026-05-24T12:00:00+00:00",
    "attributes": {
        "friendly_name": "Doorbell",
        "entity_picture": "/api/image_proxy/image.doorbell?token=xyz",
    },
}


class TestImageList:

    def test_list_strips_attributes_by_default(self, fake_client):
        fake_client.set("GET", "states", [_SAMPLE_IMAGE_ENTITY,
                                            {"entity_id": "light.kitchen",
                                             "state": "on", "attributes": {}}])
        result = image.list_image_entities(fake_client)
        assert len(result) == 1
        row = result[0]
        assert "attributes" not in row
        assert row["friendly_name"] == "Doorbell"
        assert row["entity_picture"].startswith("/api/image_proxy/")

    def test_list_includes_attributes(self, fake_client):
        fake_client.set("GET", "states", [_SAMPLE_IMAGE_ENTITY])
        result = image.list_image_entities(fake_client, include_attributes=True)
        assert "attributes" in result[0]

    def test_list_empty(self, fake_client):
        fake_client.set("GET", "states", [])
        assert image.list_image_entities(fake_client) == []

    def test_get_happy(self, fake_client):
        fake_client.set("GET", f"states/{_SAMPLE_IMAGE_ENTITY['entity_id']}",
                          _SAMPLE_IMAGE_ENTITY)
        result = image.get_image_entity(fake_client, "image.doorbell")
        assert result == _SAMPLE_IMAGE_ENTITY

    def test_get_rejects_non_image_entity(self, fake_client):
        with pytest.raises(ValueError, match="not an image"):
            image.get_image_entity(fake_client, "light.kitchen")

    def test_get_no_entity_id(self, fake_client):
        with pytest.raises(ValueError, match="entity_id"):
            image.get_image_entity(fake_client, "")


class TestProxyURL:

    def _client(self):
        client = MagicMock()
        client.base_url = "http://localhost:8123"
        return client

    def test_proxy_url_unsigned(self):
        client = self._client()
        out = image.proxy_url(client, entity_id="image.doorbell", signed=False)
        assert out["signed"] is False
        assert out["path"] == "/api/image_proxy/image.doorbell"
        assert out["url"] == "http://localhost:8123/api/image_proxy/image.doorbell"
        assert out["expires"] is None

    def test_proxy_url_signed(self):
        client = self._client()
        # auth_tokens_core.sign_path uses client.ws_call under the hood
        client.ws_call = MagicMock(return_value={
            "path": "/api/image_proxy/image.doorbell?authSig=abc.def.ghi",
        })
        out = image.proxy_url(client, entity_id="image.doorbell",
                                signed=True, expires=60)
        assert out["signed"] is True
        assert "authSig=" in out["path"]
        assert out["url"].startswith("http://localhost:8123")
        assert out["expires"] == 60
        # Ensure we called auth/sign_path correctly
        call = client.ws_call.call_args
        assert call.args[0] == "auth/sign_path"
        assert call.args[1]["path"] == "/api/image_proxy/image.doorbell"
        assert call.args[1]["expires"] == 60

    def test_proxy_url_rejects_non_image(self):
        with pytest.raises(ValueError, match="not an image"):
            image.proxy_url(self._client(), entity_id="camera.front", signed=False)

    def test_proxy_url_empty_entity(self):
        with pytest.raises(ValueError, match="entity_id"):
            image.proxy_url(self._client(), entity_id="", signed=False)


class TestSnapshot:

    def _fake_streaming_client(self, *, signed_ok=True, bytes_payload=b"PNG-DATA",
                                content_type="image/png"):
        client = MagicMock()
        client.base_url = "http://localhost:8123"
        client.timeout = 30
        session = MagicMock()
        session.headers = {"Authorization": "Bearer tok", "Content-Type": "application/json"}

        def fake_get(url, **kwargs):
            class _R:
                ok = True
                status_code = 200
                content = bytes_payload
                text = ""
                headers = {"Content-Type": content_type}
                def iter_content(self, chunk_size=8192):
                    yield bytes_payload
            return _R()

        session.get = MagicMock(side_effect=fake_get)
        client.session = session
        if signed_ok:
            client.ws_call = MagicMock(return_value={
                "path": "/api/image_proxy/image.doorbell?authSig=tok",
            })
        else:
            client.ws_call = MagicMock(return_value={})
        return client

    def test_snapshot_direct(self, tmp_path):
        client = self._fake_streaming_client()
        out_path = str(tmp_path / "snap.png")
        result = image.snapshot(client, entity_id="image.doorbell",
                                 output_path=out_path)
        assert os.path.exists(out_path)
        with open(out_path, "rb") as fh:
            assert fh.read() == b"PNG-DATA"
        assert result["bytes"] == len(b"PNG-DATA")
        assert result["content_type"] == "image/png"
        # Direct path: signed-URL ws_call was NOT made
        client.ws_call.assert_not_called()

    def test_snapshot_signed_strips_auth_header(self, tmp_path):
        client = self._fake_streaming_client(signed_ok=True)
        out_path = str(tmp_path / "snap-signed.png")
        image.snapshot(client, entity_id="image.doorbell",
                        output_path=out_path, signed=True, expires=120)
        # ws_call was used for sign_path
        client.ws_call.assert_called_once()
        # The header passed to GET must NOT include Authorization
        call = client.session.get.call_args
        headers = call.kwargs.get("headers", {})
        assert "Authorization" not in headers
        assert "Content-Type" in headers  # Other headers preserved

    def test_snapshot_signed_url_failure(self, tmp_path):
        client = self._fake_streaming_client(signed_ok=False)
        with pytest.raises(RuntimeError, match="sign_path"):
            image.snapshot(client, entity_id="image.doorbell",
                            output_path=str(tmp_path / "f.png"),
                            signed=True)

    def test_snapshot_refuses_existing_file(self, tmp_path):
        client = self._fake_streaming_client()
        out_path = tmp_path / "exists.png"
        out_path.write_bytes(b"old")
        with pytest.raises(FileExistsError):
            image.snapshot(client, entity_id="image.doorbell",
                            output_path=str(out_path))

    def test_snapshot_overwrite(self, tmp_path):
        client = self._fake_streaming_client()
        out_path = tmp_path / "exists.png"
        out_path.write_bytes(b"old")
        result = image.snapshot(client, entity_id="image.doorbell",
                                 output_path=str(out_path), overwrite=True)
        assert result["bytes"] > 0
        assert out_path.read_bytes() == b"PNG-DATA"

    def test_snapshot_rejects_non_image_entity(self, tmp_path):
        client = self._fake_streaming_client()
        with pytest.raises(ValueError, match="not an image"):
            image.snapshot(client, entity_id="camera.front",
                            output_path=str(tmp_path / "x.png"))

    def test_snapshot_no_session(self, tmp_path):
        client = MagicMock()
        client.session = None
        with pytest.raises(ValueError, match="HTTP session"):
            image.snapshot(client, entity_id="image.doorbell",
                            output_path=str(tmp_path / "x.png"))


class TestSubscribe:

    def test_subscribe_filters_to_entity(self, subscribing_client):
        subscribing_client.queue_events(
            {"data": {"entity_id": "image.doorbell"}, "event_type": "state_changed"},
            {"data": {"entity_id": "image.other"}, "event_type": "state_changed"},
            {"data": {"entity_id": "image.doorbell"}, "event_type": "state_changed"},
        )
        result = image.subscribe_updates(subscribing_client,
                                          entity_id="image.doorbell", timeout=2)
        assert len(result) == 2
        # Subscribe was called with state_changed filter
        assert subscribing_client.subscribe_calls
        msg_type, payload = subscribing_client.subscribe_calls[0]
        assert msg_type == "subscribe_events"
        assert payload == {"event_type": "state_changed"}

    def test_subscribe_rejects_non_image(self, subscribing_client):
        with pytest.raises(ValueError, match="not an image"):
            image.subscribe_updates(subscribing_client,
                                     entity_id="light.kitchen")

    def test_subscribe_zero_timeout(self, subscribing_client):
        with pytest.raises(ValueError, match="timeout"):
            image.subscribe_updates(subscribing_client,
                                     entity_id="image.x", timeout=0)
