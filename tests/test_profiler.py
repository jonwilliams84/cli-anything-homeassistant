"""Unit tests for cli_anything.homeassistant.core.profiler."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import profiler


class TestProfilerServices:

    def _registered_response(self, fake_client):
        """Set up the canned profiler.<svc> response shape."""
        # services_core.call_service POSTs to /services/<domain>/<svc>
        for svc in ("start", "memory", "dump_log_objects",
                     "log_thread_frames", "log_event_loop_scheduled",
                     "log_current_tasks", "lru_stats", "set_asyncio_debug",
                     "log_events"):
            fake_client.set_service("profiler", svc, [])

    def test_start_payload(self, fake_client):
        self._registered_response(fake_client)
        result = profiler.start(fake_client, seconds=120)
        assert result["service"] == "profiler.start"
        assert result["data"] == {"seconds": 120}
        # The service was POSTed
        call = fake_client.service_calls[0]
        assert call["domain"] == "profiler"
        assert call["service"] == "start"
        assert call["service_data"] == {"seconds": 120}

    def test_start_rejects_zero_seconds(self, fake_client):
        with pytest.raises(ValueError, match="seconds"):
            profiler.start(fake_client, seconds=0)
        with pytest.raises(ValueError, match="seconds"):
            profiler.start(fake_client, seconds=-5)

    def test_memory_payload(self, fake_client):
        self._registered_response(fake_client)
        profiler.memory(fake_client, seconds=90)
        call = fake_client.service_calls[0]
        assert call["service"] == "memory"
        assert call["service_data"] == {"seconds": 90}

    def test_memory_rejects_zero(self, fake_client):
        with pytest.raises(ValueError, match="seconds"):
            profiler.memory(fake_client, seconds=0)

    def test_dump_log_objects_payload(self, fake_client):
        self._registered_response(fake_client)
        profiler.dump_log_objects(fake_client, type_="State")
        call = fake_client.service_calls[0]
        assert call["service"] == "dump_log_objects"
        assert call["service_data"] == {"type": "State"}

    def test_dump_log_objects_missing_type(self, fake_client):
        with pytest.raises(ValueError, match="type_"):
            profiler.dump_log_objects(fake_client, type_="")

    def test_log_thread_frames(self, fake_client):
        self._registered_response(fake_client)
        result = profiler.log_thread_frames(fake_client)
        assert result["service"] == "profiler.log_thread_frames"
        assert result["data"] == {}
        call = fake_client.service_calls[0]
        assert call["service"] == "log_thread_frames"

    def test_log_event_loop_scheduled(self, fake_client):
        self._registered_response(fake_client)
        profiler.log_event_loop_scheduled(fake_client)
        assert fake_client.service_calls[0]["service"] == "log_event_loop_scheduled"

    def test_log_current_tasks(self, fake_client):
        self._registered_response(fake_client)
        profiler.log_current_tasks(fake_client)
        assert fake_client.service_calls[0]["service"] == "log_current_tasks"

    def test_lru_stats(self, fake_client):
        self._registered_response(fake_client)
        profiler.lru_stats(fake_client)
        assert fake_client.service_calls[0]["service"] == "lru_stats"

    def test_set_asyncio_debug(self, fake_client):
        self._registered_response(fake_client)
        profiler.set_asyncio_debug(fake_client, enabled=True)
        call = fake_client.service_calls[0]
        assert call["service"] == "set_asyncio_debug"
        assert call["service_data"] == {"enabled": True}

    def test_set_asyncio_debug_disabled(self, fake_client):
        self._registered_response(fake_client)
        profiler.set_asyncio_debug(fake_client, enabled=False)
        call = fake_client.service_calls[0]
        assert call["service_data"] == {"enabled": False}

    def test_log_events(self, fake_client):
        self._registered_response(fake_client)
        profiler.log_events(fake_client)
        assert fake_client.service_calls[0]["service"] == "log_events"


class TestProfilerStatus:

    def test_status_loaded_with_services(self, fake_client):
        fake_client.set("GET", "components",
                          ["frontend", "profiler", "recorder"])
        fake_client.set("GET", "services", [
            {"domain": "profiler", "services": {
                "start": {}, "memory": {}, "lru_stats": {},
                "set_asyncio_debug": {},
            }},
            {"domain": "light", "services": {"turn_on": {}}},
        ])
        result = profiler.status(fake_client)
        assert result["loaded"] is True
        assert result["services"] == sorted([
            "start", "memory", "lru_stats", "set_asyncio_debug",
        ])

    def test_status_not_loaded(self, fake_client):
        fake_client.set("GET", "components", ["frontend", "recorder"])
        fake_client.set("GET", "services", [])
        result = profiler.status(fake_client)
        assert result["loaded"] is False
        assert result["services"] == []

    def test_status_loaded_but_no_services(self, fake_client):
        fake_client.set("GET", "components", ["profiler"])
        fake_client.set("GET", "services", [
            {"domain": "light", "services": {"turn_on": {}}},
        ])
        result = profiler.status(fake_client)
        assert result["loaded"] is True
        assert result["services"] == []

    def test_status_components_error_silent(self, fake_client):
        # When the GET /api/components call raises, _is_loaded returns False
        def raise_get(*a, **k):
            raise RuntimeError("net down")
        fake_client.get = raise_get  # type: ignore[assignment]
        result = profiler.status(fake_client)
        assert result["loaded"] is False
