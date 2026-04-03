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