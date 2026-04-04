from datetime import UTC, datetime, timedelta

from space_traffic_api.app import create_app


def test_distance_model_keeps_earth_mars_close_route_in_day_scale(monkeypatch, tmp_path):
    db_path = tmp_path / "travel_time.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "99")

    app = create_app()
    try:
        simulation = app.config["space_simulation"]
        samples: list[float] = []
        for day_offset in range(0, 900, 7):
            departure_time = datetime(2100, 1, 1, tzinfo=UTC) + timedelta(days=day_offset)
            eta = simulation.estimate_arrival(departure_time, "STN-PLANET-EARTH", "STN-PLANET-MARS")
            samples.append((eta - departure_time).total_seconds() / 86400.0)

        assert min(samples) <= 4.6
        assert min(samples) >= 2.8
    finally:
        app.config["space_store"].close()


def test_distance_model_keeps_neptune_pluto_far_route_in_multi_month_scale(monkeypatch, tmp_path):
    db_path = tmp_path / "travel_time_far.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "99")

    app = create_app()
    try:
        simulation = app.config["space_simulation"]
        samples: list[float] = []
        for day_offset in range(0, 365 * 4, 14):
            departure_time = datetime(2100, 1, 1, tzinfo=UTC) + timedelta(days=day_offset)
            eta = simulation.estimate_arrival(departure_time, "STN-PLANET-NEPTUNE", "STN-PLANET-PLUTO")
            samples.append((eta - departure_time).total_seconds() / 86400.0)

        assert max(samples) >= 160.0
        assert max(samples) <= 210.0
    finally:
        app.config["space_store"].close()
