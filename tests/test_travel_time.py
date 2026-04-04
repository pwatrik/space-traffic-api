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
