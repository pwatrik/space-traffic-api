from __future__ import annotations

import time
from datetime import datetime

from space_traffic_api.app import create_app


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_simulation_clock_advances_with_wall_time_not_tick_interval(monkeypatch, tmp_path):
    db_path = tmp_path / "sim_clock_wall.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "424242")
    monkeypatch.setenv("SPACE_TRAFFIC_SIMULATION_TIME_SCALE", "1.0")
    monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "1")
    monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "1")

    app = create_app()
    simulation = app.config["space_simulation"]
    store = app.config["space_store"]
    try:
        before = _parse_iso(simulation.snapshot()["simulation_now"])
        time.sleep(1.2)
        after = _parse_iso(simulation.snapshot()["simulation_now"])
        elapsed = (after - before).total_seconds()

        # Clock should track wall time progression, not jump by one full generator interval (60s).
        assert 0.5 <= elapsed < 10.0
    finally:
        simulation.stop(timeout=3.0)
        store.close()


def test_simulation_clock_respects_time_scale_ratio(monkeypatch, tmp_path):
    db_path = tmp_path / "sim_clock_scale.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "424242")
    monkeypatch.setenv("SPACE_TRAFFIC_SIMULATION_TIME_SCALE", "5.0")
    monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "1")
    monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "1")

    app = create_app()
    simulation = app.config["space_simulation"]
    store = app.config["space_store"]
    try:
        before = _parse_iso(simulation.snapshot()["simulation_now"])
        time.sleep(1.0)
        after = _parse_iso(simulation.snapshot()["simulation_now"])
        elapsed = (after - before).total_seconds()

        assert elapsed >= 3.0
        assert elapsed < 20.0
    finally:
        simulation.stop(timeout=3.0)
        store.close()
