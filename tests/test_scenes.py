"""Unit tests for cli_anything.homeassistant.core.scenes — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import scenes


class TestSceneList:
    def test_filters_to_scene_domain(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "scene.morning", "state": "scening"},
            {"entity_id": "light.kitchen", "state": "on"},
            {"entity_id": "scene.movie", "state": "scening"},
        ])
        rows = scenes.list_scenes(fake_client)
        assert {r["entity_id"] for r in rows} == {"scene.morning", "scene.movie"}

    def test_non_list_response(self, fake_client):
        # Not a list — function returns empty list rather than crashing.
        fake_client.set("GET", "states", None)
        assert scenes.list_scenes(fake_client) == []

    def test_skips_non_dict_rows(self, fake_client):
        fake_client.set("GET", "states", [
            "garbage",
            {"entity_id": "scene.ok"},
        ])
        rows = scenes.list_scenes(fake_client)
        assert len(rows) == 1
        assert rows[0]["entity_id"] == "scene.ok"


class TestSceneActivate:
    def test_minimal(self, fake_client):
        scenes.activate(fake_client, "scene.morning")
        assert fake_client.calls[-1] == {
            "verb": "POST",
            "path": "services/scene/turn_on",
            "payload": {"entity_id": "scene.morning"},
        }

    def test_with_transition(self, fake_client):
        scenes.activate(fake_client, "scene.morning", transition=2.5)
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "scene.morning",
            "transition": 2.5,
        }

    def test_wrong_domain_raises(self, fake_client):
        with pytest.raises(ValueError, match="expected scene"):
            scenes.activate(fake_client, "light.kitchen")

    def test_negative_transition_raises(self, fake_client):
        with pytest.raises(ValueError, match="transition must be >= 0"):
            scenes.activate(fake_client, "scene.morning", transition=-1)


class TestSceneApply:
    def test_minimal(self, fake_client):
        scenes.apply(fake_client, entities={"light.kitchen": "on"})
        assert fake_client.calls[-1] == {
            "verb": "POST",
            "path": "services/scene/apply",
            "payload": {"entities": {"light.kitchen": "on"}},
        }

    def test_with_transition(self, fake_client):
        scenes.apply(
            fake_client,
            entities={"light.lamp": {"state": "on", "brightness": 120}},
            transition=1.0,
        )
        assert fake_client.calls[-1]["payload"] == {
            "entities": {"light.lamp": {"state": "on", "brightness": 120}},
            "transition": 1.0,
        }

    def test_empty_entities_raises(self, fake_client):
        with pytest.raises(ValueError, match="entities is required"):
            scenes.apply(fake_client, entities={})

    def test_non_dict_entities_raises(self, fake_client):
        with pytest.raises(ValueError, match="entities must be a dict"):
            scenes.apply(fake_client, entities=["light.kitchen=on"])


class TestSceneCreate:
    def test_with_entities(self, fake_client):
        scenes.create(fake_client, scene_id="movie_night",
                      entities={"light.kitchen": "off"})
        assert fake_client.calls[-1] == {
            "verb": "POST",
            "path": "services/scene/create",
            "payload": {
                "scene_id": "movie_night",
                "entities": {"light.kitchen": "off"},
            },
        }

    def test_with_snapshot(self, fake_client):
        scenes.create(fake_client, scene_id="current",
                      snapshot_entities=["light.a", "light.b"])
        assert fake_client.calls[-1]["payload"] == {
            "scene_id": "current",
            "snapshot_entities": ["light.a", "light.b"],
        }

    def test_with_both(self, fake_client):
        scenes.create(
            fake_client, scene_id="combo",
            entities={"light.a": "on"},
            snapshot_entities=["light.b"],
        )
        payload = fake_client.calls[-1]["payload"]
        assert payload["scene_id"] == "combo"
        assert payload["entities"] == {"light.a": "on"}
        assert payload["snapshot_entities"] == ["light.b"]

    def test_neither_provided_raises(self, fake_client):
        with pytest.raises(ValueError, match="entities=|snapshot_entities="):
            scenes.create(fake_client, scene_id="x")

    def test_empty_scene_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="scene_id is required"):
            scenes.create(fake_client, scene_id="", entities={"a": "b"})

    def test_scene_id_with_prefix_raises(self, fake_client):
        with pytest.raises(ValueError, match="suffix only"):
            scenes.create(fake_client, scene_id="scene.foo",
                          entities={"a": "b"})


class TestSceneReload:
    def test_reload(self, fake_client):
        scenes.reload(fake_client)
        assert fake_client.calls[-1] == {
            "verb": "POST",
            "path": "services/scene/reload",
            "payload": {},
        }
