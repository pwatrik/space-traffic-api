from datetime import UTC, datetime

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
