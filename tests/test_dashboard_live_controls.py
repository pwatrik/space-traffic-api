import time
from datetime import datetime

from space_traffic_api.app import create_app


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def test_dashboard_ui_contains_session_controls(monkeypatch, tmp_path):
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(tmp_path / "ui_controls.db"))
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")

    app = create_app()
    client = app.test_client()
    try:
        response = client.get("/ui")
        assert response.status_code == 200
        content = response.get_data(as_text=True)
        # Controls directly used by the dashboard operator workflow.
        assert "id=\"cfg-start-time\"" in content
        assert "id=\"cfg-time-scale\"" in content
        assert "id=\"cfg-save\"" in content
        assert "id=\"ctl-reset\"" in content
        assert "id=\"scenario-activate\"" in content
        assert "id=\"fault-activate\"" in content
    finally:
        app.config["space_store"].close()


def test_live_operator_controls_round_trip_and_emit_events(monkeypatch, tmp_path):
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(tmp_path / "live_controls.db"))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "false")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "424242")
    monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "120")
    monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "120")

    app = create_app()
    client = app.test_client()
    headers = {"X-API-Key": "test-key"}
    try:
        patched = client.patch(
            "/config",
            headers=headers,
            json={
                "deterministic_mode": True,
                "deterministic_seed": 999,
                "deterministic_start_time": "2158-01-02T03:04:05Z",
                "simulation_time_scale": 4.0,
                "orbital_distance_model_enabled": True,
            },
        )
        assert patched.status_code == 200
        cfg = patched.get_json()
        assert cfg["deterministic_seed"] == 999
        assert cfg["simulation_time_scale"] == 4.0
        assert cfg["orbital_distance_model_enabled"] is True
        assert cfg["simulation_now"].startswith("2158-01-02T03:04:05")

        scenario = client.post(
            "/scenarios/activate",
            headers=headers,
            json={"name": "war", "intensity": 1.5, "duration_seconds": 60},
        )
        assert scenario.status_code == 200

        fault = client.post(
            "/faults/activate",
            headers=headers,
            json={"faults": {"malformed_payload": {"rate": 0.2, "duration_seconds": 60}}},
        )
        assert fault.status_code == 200

        clear_fault = client.post(
            "/faults/deactivate",
            headers=headers,
            json={"names": ["malformed_payload"]},
        )
        assert clear_fault.status_code == 200

        clear_scenario = client.post("/scenarios/deactivate", headers=headers)
        assert clear_scenario.status_code == 200

        reset = client.post("/control/reset", headers=headers, json={"seed": 777})
        assert reset.status_code == 200
        runtime = reset.get_json()["runtime"]
        assert runtime["deterministic_seed"] == 777
        assert runtime["simulation_now"].startswith("2158-01-02T03:04:05")

        events_resp = client.get("/control-events?limit=100", headers=headers)
        assert events_resp.status_code == 200
        events = events_resp.get_json()["control_events"]
        actions = {(e["event_type"], e["action"]) for e in events}
        assert ("config", "patched") in actions
        assert ("scenario", "activated") in actions
        assert ("scenario", "deactivated") in actions
        assert ("fault", "activated") in actions
        assert ("fault", "deactivated") in actions
        assert ("control", "reset") in actions

        # Session 5 split-field behavior should still hold during live controls.
        for event in events:
            assert event["event_time_simulated"] == event["event_time"]
            assert event["recorded_at_wall"] is not None
    finally:
        app.config["space_simulation"].stop(timeout=6.0)
        app.config["space_store"].close()


def test_compression_ratio_changes_live_simulation_clock_rate(monkeypatch, tmp_path):
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(tmp_path / "clock_ratio.db"))
    monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
    monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "false")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_START_TIME", "2150-01-01T00:00:00Z")
    monkeypatch.setenv("SPACE_TRAFFIC_SIMULATION_TIME_SCALE", "1.0")
    monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "60")
    monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "60")

    app = create_app()
    client = app.test_client()
    headers = {"X-API-Key": "test-key"}
    try:
        c1 = client.get("/config", headers=headers).get_json()
        t1 = _parse_iso(c1["simulation_now"])
        time.sleep(0.8)
        c2 = client.get("/config", headers=headers).get_json()
        t2 = _parse_iso(c2["simulation_now"])
        delta_scale_1 = (t2 - t1).total_seconds()

        patch = client.patch("/config", headers=headers, json={"simulation_time_scale": 8.0})
        assert patch.status_code == 200

        c3 = client.get("/config", headers=headers).get_json()
        t3 = _parse_iso(c3["simulation_now"])
        time.sleep(0.8)
        c4 = client.get("/config", headers=headers).get_json()
        t4 = _parse_iso(c4["simulation_now"])
        delta_scale_8 = (t4 - t3).total_seconds()

        assert delta_scale_1 > 0.0
        # With 8x compression ratio, progression should be substantially faster.
        assert delta_scale_8 > delta_scale_1 * 3.0
    finally:
        app.config["space_simulation"].stop(timeout=6.0)
        app.config["space_store"].close()
