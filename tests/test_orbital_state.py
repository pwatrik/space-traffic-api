from space_traffic_api.app import create_app


def test_orbital_state_initialization_is_deterministic_for_same_seed(monkeypatch, tmp_path):
    db_path_a = tmp_path / "orbital_a.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path_a))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "5150")

    app_a = create_app()
    try:
        snapshot_a = app_a.config["space_simulation"].orbital_state_snapshot()
    finally:
        app_a.config["space_store"].close()

    db_path_b = tmp_path / "orbital_b.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path_b))
    app_b = create_app()
    try:
        snapshot_b = app_b.config["space_simulation"].orbital_state_snapshot()
    finally:
        app_b.config["space_store"].close()

    assert snapshot_a == snapshot_b
    assert "Earth" in snapshot_a


def test_orbital_state_reset_reproduces_same_seed(monkeypatch, tmp_path):
    db_path = tmp_path / "orbital_reset.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "6161")

    app = create_app()
    try:
        simulation = app.config["space_simulation"]
        before = simulation.orbital_state_snapshot()
        simulation.reset(seed=6161)
        after = simulation.orbital_state_snapshot()
    finally:
        app.config["space_store"].close()

    assert before == after


def test_orbital_state_contains_asteroid_body_entries(monkeypatch, tmp_path):
    db_path = tmp_path / "orbital_asteroid.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "7171")

    app = create_app()
    try:
        snapshot = app.config["space_simulation"].orbital_state_snapshot()
    finally:
        app.config["space_store"].close()

    assert any(body["body_type"] == "asteroid" for body in snapshot.values())


def test_orbital_state_advances_when_sim_time_advances(monkeypatch, tmp_path):
    db_path = tmp_path / "orbital_advance.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "8181")

    app = create_app()
    try:
        simulation = app.config["space_simulation"]
        generator = simulation._generator
        runtime_state = simulation.snapshot()
        tick_time = generator._current_tick_time(runtime_state)
        before = simulation.orbital_state_snapshot()

        generator._advance_sim_time(tick_time, 3600.0)

        after = simulation.orbital_state_snapshot()
    finally:
        app.config["space_store"].close()

    assert before != after
    assert before["Earth"]["phase_radians"] != after["Earth"]["phase_radians"]
    assert before["Earth"]["x"] != after["Earth"]["x"]
    assert before["Earth"]["y"] != after["Earth"]["y"]


def test_orbital_state_does_not_advance_for_zero_elapsed_time(monkeypatch, tmp_path):
    db_path = tmp_path / "orbital_zero.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "9191")

    app = create_app()
    try:
        simulation = app.config["space_simulation"]
        generator = simulation._generator
        runtime_state = simulation.snapshot()
        tick_time = generator._current_tick_time(runtime_state)
        before = simulation.orbital_state_snapshot()

        generator._advance_sim_time(tick_time, 0.0)

        after = simulation.orbital_state_snapshot()
    finally:
        app.config["space_store"].close()

    assert before == after


def test_orbital_state_reset_rewinds_after_advancement(monkeypatch, tmp_path):
    db_path = tmp_path / "orbital_rewind.db"
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "10101")

    app = create_app()
    try:
        simulation = app.config["space_simulation"]
        generator = simulation._generator
        runtime_state = simulation.snapshot()
        tick_time = generator._current_tick_time(runtime_state)
        initial = simulation.orbital_state_snapshot()

        generator._advance_sim_time(tick_time, 7200.0)
        advanced = simulation.orbital_state_snapshot()
        simulation.reset(seed=10101)
        rewound = simulation.orbital_state_snapshot()
    finally:
        app.config["space_store"].close()

    assert advanced != initial
    assert rewound == initial