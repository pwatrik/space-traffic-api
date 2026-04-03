from datetime import UTC, datetime
import random

from space_traffic_api.app import create_app


def test_default_ship_speed_multiplier_keeps_long_routes_near_one_hour(monkeypatch, tmp_path):
    db_path = tmp_path / "travel_time.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")

    app = create_app()
    try:
        simulation = app.config["space_simulation"]
        departure_time = datetime.now(UTC)
        eta = simulation.estimate_arrival(departure_time, "STN-PLANET-MERCURY", "STN-PLANET-PLUTO")
        hours = (eta - departure_time).total_seconds() / 3600.0

        assert 0.8 <= hours <= 1.1
    finally:
        app.config["space_store"].close()


def test_orbital_distance_model_disabled_ignores_departure_time(monkeypatch, tmp_path):
    db_path = tmp_path / "travel_time_disabled.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MODEL_ENABLED", "false")

    app = create_app()
    try:
        simulation = app.config["space_simulation"]
        departure_time_a = datetime(2150, 1, 1, tzinfo=UTC)
        departure_time_b = datetime(2150, 7, 1, tzinfo=UTC)

        simulation._generator._rng = random.Random(1337)
        eta_a = simulation.estimate_arrival(departure_time_a, "STN-PLANET-MERCURY", "STN-PLANET-PLUTO")
        simulation._generator._rng = random.Random(1337)
        eta_b = simulation.estimate_arrival(departure_time_b, "STN-PLANET-MERCURY", "STN-PLANET-PLUTO")

        duration_a = (eta_a - departure_time_a).total_seconds()
        duration_b = (eta_b - departure_time_b).total_seconds()
        assert duration_a == duration_b
    finally:
        app.config["space_store"].close()


def test_orbital_distance_model_enabled_changes_by_departure_time(monkeypatch, tmp_path):
    db_path = tmp_path / "travel_time_enabled.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MODEL_ENABLED", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MIN", "0.7")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MAX", "1.3")

    app = create_app()
    try:
        simulation = app.config["space_simulation"]
        departure_time_a = datetime(2150, 1, 1, tzinfo=UTC)
        departure_time_b = datetime(2150, 7, 1, tzinfo=UTC)

        simulation._generator._rng = random.Random(1337)
        eta_a = simulation.estimate_arrival(departure_time_a, "STN-PLANET-MERCURY", "STN-PLANET-PLUTO")
        simulation._generator._rng = random.Random(1337)
        eta_b = simulation.estimate_arrival(departure_time_b, "STN-PLANET-MERCURY", "STN-PLANET-PLUTO")

        duration_a = (eta_a - departure_time_a).total_seconds()
        duration_b = (eta_b - departure_time_b).total_seconds()
        assert duration_a != duration_b
    finally:
        app.config["space_store"].close()
