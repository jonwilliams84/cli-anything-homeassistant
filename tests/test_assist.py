"""Unit tests for cli_anything.homeassistant.core.assist."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import assist


class TestProcess:
    def test_basic_process(self, fake_client):
        fake_client.set("POST", "conversation/process", {"response": {"speech": {"plain": {"speech": "Hello"}}}})
        result = assist.process(fake_client, "turn on the lights")
        assert result["response"]["speech"]["plain"]["speech"] == "Hello"
        call = fake_client.calls[-1]
        assert call["path"] == "conversation/process"
        assert call["payload"]["text"] == "turn on the lights"

    def test_with_all_options(self, fake_client):
        fake_client.set("POST", "conversation/process", {})
        assist.process(
            fake_client, "hello",
            conversation_id="conv-1",
            language="en",
            agent_id="agent-1",
        )
        body = fake_client.calls[-1]["payload"]
        assert body["text"] == "hello"
        assert body["conversation_id"] == "conv-1"
        assert body["language"] == "en"
        assert body["agent_id"] == "agent-1"

    def test_empty_text_raises(self, fake_client):
        with pytest.raises(ValueError, match="text is required"):
            assist.process(fake_client, "")

    def test_none_text_raises(self, fake_client):
        with pytest.raises(ValueError, match="text is required"):
            assist.process(fake_client, None)  # type: ignore[arg-type]


class TestPipelines:
    def test_returns_dict(self, fake_client):
        fake_client.set_ws("assist_pipeline/pipeline/list", {
            "pipelines": [{"id": "p1"}],
            "preferred_pipeline": "p1",
        })
        result = assist.pipelines(fake_client)
        assert result["pipelines"] == [{"id": "p1"}]
        assert result["preferred_pipeline"] == "p1"

    def test_non_dict_returns_default(self, fake_client):
        fake_client.set_ws("assist_pipeline/pipeline/list", "not a dict")
        result = assist.pipelines(fake_client)
        assert result == {"pipelines": [], "preferred_pipeline": None}

    def test_none_response_returns_empty_dict(self, fake_client):
        """When ws_call returns None, `or {}` yields empty dict (truthy branch not hit)."""
        fake_client.set_ws("assist_pipeline/pipeline/list", None)
        result = assist.pipelines(fake_client)
        assert result == {}


class TestPipelineGet:
    def test_returns_pipeline_config(self, fake_client):
        fake_client.set_ws("assist_pipeline/pipeline/get", {"id": "p1", "name": "Default"})
        result = assist.pipeline_get(fake_client, "p1")
        assert result == {"id": "p1", "name": "Default"}

    def test_empty_pipeline_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="pipeline_id is required"):
            assist.pipeline_get(fake_client, "")

    def test_empty_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("assist_pipeline/pipeline/get", None)
        assert assist.pipeline_get(fake_client, "p1") == {}
