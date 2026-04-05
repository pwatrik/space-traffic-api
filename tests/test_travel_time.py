from datetime import UTC, datetime
import random

from space_traffic_api.app import create_app


def test_calibrated_earth_mars_close_approach_is_about_three_to_four_days(monkeypatch, tmp_path):
    db_path = tmp_path / "travel_time.db"
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

        # Calibrate against close approach: Earth -> Mars should be around 3-4 simulated days.
        min_days = float("inf")
        for _ in range(120):
            tick_time = generator._current_tick_time(simulation.snapshot())
            generator._rng = random.Random(1337)
            eta = simulation.estimate_arrival(tick_time, "STN-PLANET-EARTH", "STN-PLANET-MARS")
            trip_days = (eta - tick_time).total_seconds() / 86400.0
            min_days = min(min_days, trip_days)
            generator._advance_sim_time(tick_time, 3 * 86400.0)

        assert 3.0 <= min_days <= 4.2
    finally:
        app.config["space_store"].close()


def test_calibrated_neptune_pluto_far_separation_reaches_about_180_days(monkeypatch, tmp_path):
    db_path = tmp_path / "travel_time_far_calibration.db"
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

        max_days = 0.0
        for _ in range(200):
            tick_time = generator._current_tick_time(simulation.snapshot())
            generator._rng = random.Random(1337)
            eta = simulation.estimate_arrival(tick_time, "STN-PLANET-NEPTUNE", "STN-PLANET-PLUTO")
            trip_days = (eta - tick_time).total_seconds() / 86400.0
            max_days = max(max_days, trip_days)
            generator._advance_sim_time(tick_time, 7 * 86400.0)

        assert 165.0 <= max_days <= 200.0
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


def test_departure_persists_est_arrival_time_even_as_orbital_state_moves(monkeypatch, tmp_path):
    db_path = tmp_path / "travel_time_persisted_eta.db"
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
        store = app.config["space_store"]
        generator = simulation._generator
        runtime_state = simulation.snapshot()
        generator._ensure_rng(runtime_state)
        departure_time = generator._current_tick_time(runtime_state)

        ship = next(iter(store.list_available_ships()))
        source = ship["current_station_id"]
        destination = generator._pick_destination(ship, source, scenario=None)
        assert destination is not None

        generator._rng = random.Random(1337)
        event = generator._create_departure_event(
            ship_id=ship["ship_id"],
            source_station_id=source,
            destination_station_id=destination,
            departure_time=departure_time,
            scenario=None,
            ship_faction=str(ship.get("faction") or ""),
        )
        assert event is not None
        persisted_eta = event["est_arrival_time"]

        ship_state_before = next(
            row for row in store.list_ship_states(in_transit=True, limit=5000)
            if row["ship_id"] == ship["ship_id"]
        )
        assert ship_state_before["est_arrival_time"] == persisted_eta

        generator._advance_sim_time(departure_time, 180 * 86400.0)

        generator._rng = random.Random(1337)
        recomputed_eta = simulation.estimate_arrival(departure_time, source, destination).isoformat()
        ship_state_after = next(
            row for row in store.list_ship_states(in_transit=True, limit=5000)
            if row["ship_id"] == ship["ship_id"]
        )

        assert recomputed_eta != persisted_eta
        assert ship_state_after["est_arrival_time"] == persisted_eta
    finally:
        app.config["space_store"].close()


def _sample_route_days(
    simulation,
    generator,
    source: str,
    destination: str,
    *,
    samples: int,
    step_days: float,
) -> list[float]:
    values: list[float] = []
    for _ in range(samples):
        tick_time = generator._current_tick_time(simulation.snapshot())
        generator._rng = random.Random(1337)
        eta = simulation.estimate_arrival(tick_time, source, destination)
        values.append((eta - tick_time).total_seconds() / 86400.0)
        generator._advance_sim_time(tick_time, step_days * 86400.0)
    return values


def test_calibrated_route_durations_are_deterministic_across_boots(monkeypatch, tmp_path):
    def _run(db_name: str) -> tuple[list[float], list[float]]:
        db_path = tmp_path / db_name
        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "424242")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_START_TIME", "2150-01-01T00:00:00Z")
        monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MODEL_ENABLED", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MIN", "0.7")
        monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MAX", "1.3")

        app = create_app()
        try:
            simulation = app.config["space_simulation"]
            generator = simulation._generator
            generator._ensure_rng(simulation.snapshot())

            earth_mars = _sample_route_days(
                simulation,
                generator,
                "STN-PLANET-EARTH",
                "STN-PLANET-MARS",
                samples=16,
                step_days=5.0,
            )
            neptune_pluto = _sample_route_days(
                simulation,
                generator,
                "STN-PLANET-NEPTUNE",
                "STN-PLANET-PLUTO",
                samples=16,
                step_days=11.0,
            )
            return earth_mars, neptune_pluto
        finally:
            app.config["space_store"].close()

    em_a, np_a = _run("travel_det_a.db")
    em_b, np_b = _run("travel_det_b.db")

    assert em_a == em_b
    assert np_a == np_b


def test_calibrated_route_envelope_snapshot_is_stable(monkeypatch, tmp_path):
    db_path = tmp_path / "travel_envelope_snapshot.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "424242")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_START_TIME", "2150-01-01T00:00:00Z")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MODEL_ENABLED", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MIN", "0.7")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MAX", "1.3")

    app = create_app()
    try:
        simulation = app.config["space_simulation"]
        generator = simulation._generator
        generator._ensure_rng(simulation.snapshot())

        earth_mars = _sample_route_days(
            simulation,
            generator,
            "STN-PLANET-EARTH",
            "STN-PLANET-MARS",
            samples=120,
            step_days=3.0,
        )
        neptune_pluto = _sample_route_days(
            simulation,
            generator,
            "STN-PLANET-NEPTUNE",
            "STN-PLANET-PLUTO",
            samples=200,
            step_days=7.0,
        )

        # Session 6 stability snapshot for calibration envelope.
        assert round(min(earth_mars), 3) == 3.525
        assert round(max(neptune_pluto), 3) == 184.058
    finally:
        app.config["space_store"].close()
