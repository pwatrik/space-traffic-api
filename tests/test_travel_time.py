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


def test_orbital_eta_changes_after_tick_advancement_when_enabled(monkeypatch, tmp_path):
    db_path = tmp_path / "travel_time_orbital_enabled.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "424242")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MODEL_ENABLED", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MIN", "0.7")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MAX", "1.3")

    app = create_app()
    try:
        simulation = app.config["space_simulation"]
        generator = simulation._generator
        runtime_state = simulation.snapshot()
        generator._ensure_rng(runtime_state)
        assert runtime_state["orbital_distance_model_enabled"] is True
        departure_time = generator._current_tick_time(runtime_state)

        source = "STN-PLANET-EARTH"
        destination = "STN-PLANET-MARS"
        base_hops = abs(generator._distance_groups.get(source, 5) - generator._distance_groups.get(destination, 5))
        hops_before = generator._departure_hops_with_orbital_state(
            source_station_id=source,
            destination_station_id=destination,
            base_hops=float(base_hops),
            runtime_snap=runtime_state,
        )

        generator._rng = random.Random(1337)
        eta_before = simulation.estimate_arrival(departure_time, source, destination)

        changed = False
        hops_after = hops_before
        for days in (1, 7, 31, 47, 83, 127):
            tick_now = generator._current_tick_time(simulation.snapshot())
            generator._advance_sim_time(tick_now, days * 86400.0)
            runtime_after = simulation.snapshot()
            hops_after = generator._departure_hops_with_orbital_state(
                source_station_id=source,
                destination_station_id=destination,
                base_hops=float(base_hops),
                runtime_snap=runtime_after,
            )
            if hops_after != hops_before:
                changed = True
                break

        generator._rng = random.Random(1337)
        eta_after = simulation.estimate_arrival(departure_time, source, destination)

        duration_before = (eta_before - departure_time).total_seconds()
        duration_after = (eta_after - departure_time).total_seconds()
        assert changed
        assert duration_before != duration_after
    finally:
        app.config["space_store"].close()


def test_orbital_eta_stable_after_tick_advancement_when_disabled(monkeypatch, tmp_path):
    db_path = tmp_path / "travel_time_orbital_disabled.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "424242")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MODEL_ENABLED", "false")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MIN", "0.7")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MAX", "1.3")

    app = create_app()
    try:
        simulation = app.config["space_simulation"]
        generator = simulation._generator
        runtime_state = simulation.snapshot()
        generator._ensure_rng(runtime_state)
        assert runtime_state["orbital_distance_model_enabled"] is False
        departure_time = generator._current_tick_time(runtime_state)

        source = "STN-PLANET-EARTH"
        destination = "STN-PLANET-MARS"
        base_hops = abs(generator._distance_groups.get(source, 5) - generator._distance_groups.get(destination, 5))
        hops_before = generator._departure_hops_with_orbital_state(
            source_station_id=source,
            destination_station_id=destination,
            base_hops=float(base_hops),
            runtime_snap=runtime_state,
        )

        generator._rng = random.Random(1337)
        eta_before = simulation.estimate_arrival(departure_time, source, destination)

        for days in (1, 7, 31, 47, 83, 127):
            tick_now = generator._current_tick_time(simulation.snapshot())
            generator._advance_sim_time(tick_now, days * 86400.0)
            runtime_after = simulation.snapshot()
            hops_after = generator._departure_hops_with_orbital_state(
                source_station_id=source,
                destination_station_id=destination,
                base_hops=float(base_hops),
                runtime_snap=runtime_after,
            )
            assert hops_before == hops_after

        generator._rng = random.Random(1337)
        eta_after = simulation.estimate_arrival(departure_time, source, destination)

        duration_before = (eta_before - departure_time).total_seconds()
        duration_after = (eta_after - departure_time).total_seconds()
        assert duration_before == duration_after
    finally:
        app.config["space_store"].close()
