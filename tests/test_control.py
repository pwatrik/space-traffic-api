import os
from tempfile import TemporaryDirectory

from space_traffic_api.app import create_app


def test_activate_scenario_fault_and_reset():
    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_API_KEY"] = "test-key"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        headers = {"X-API-Key": "test-key"}
        try:
            scenario = client.post(
                "/scenarios/activate",
                headers=headers,
                json={"name": "war", "intensity": 1.8, "duration_seconds": 120},
            )
            assert scenario.status_code == 200
            assert scenario.get_json()["active_scenario"]["name"] == "war"

            faults = client.post(
                "/faults/activate",
                headers=headers,
                json={"faults": {"malformed_payload": {"rate": 0.5}}},
            )
            assert faults.status_code == 200
            assert "malformed_payload" in faults.get_json()["active_faults"]

            reset = client.post("/control/reset", headers=headers, json={"seed": 555})
            assert reset.status_code == 200
            body = reset.get_json()
            assert body["status"] == "reset"
            assert body["runtime"]["deterministic_seed"] == 555

            patched = client.patch("/config", headers=headers, json={"db_max_size_mb": 20})
            assert patched.status_code == 200
            assert patched.get_json()["db_max_size_mb"] == 50

            patched_ok = client.patch("/config", headers=headers, json={"db_max_size_mb": 256})
            assert patched_ok.status_code == 200
            assert patched_ok.get_json()["db_max_size_mb"] == 256

            cfg = client.get("/config", headers=headers)
            assert cfg.status_code == 200
            cfg_body = cfg.get_json()
            assert "effective_lifecycle" in cfg_body
            assert "war_impact" in cfg_body["effective_lifecycle"]
            assert cfg_body["effective_lifecycle"]["war_impact"]["max_losses_per_event"] >= 3
            assert cfg_body["effective_ship_generation"]["defaults"]["ship_speed_multiplier"] == 84.0
            assert "runtime_metrics" in cfg_body
            assert "tick_latency_ms_last" in cfg_body["runtime_metrics"]
            assert "control_event_backlog_max" in cfg_body["runtime_metrics"]

            control_events = client.get("/control-events", headers=headers)
            assert control_events.status_code == 200
            events_payload = control_events.get_json()
            assert events_payload["count"] >= 3
            assert all(event.get("observed_at") for event in events_payload["control_events"])
            actions = {(event["event_type"], event["action"]) for event in events_payload["control_events"]}
            assert ("scenario", "activated") in actions
            assert ("fault", "activated") in actions
            assert ("control", "reset") in actions
        finally:
            app.config["space_store"].close()


def test_patch_config_clamps_economy_knobs():
    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_API_KEY"] = "test-key"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        headers = {"X-API-Key": "test-key"}
        try:
            low = client.patch(
                "/config",
                headers=headers,
                json={
                    "economy_preference_weight": -5,
                    "economy_drift_magnitude": 0,
                    "economy_departure_impact_magnitude": 0,
                },
            )
            assert low.status_code == 200
            low_body = low.get_json()
            assert low_body["economy_preference_weight"] == 0.0
            assert low_body["economy_drift_magnitude"] == 0.1
            assert low_body["economy_departure_impact_magnitude"] == 0.001

            high = client.patch(
                "/config",
                headers=headers,
                json={
                    "economy_preference_weight": 7,
                    "economy_drift_magnitude": 99,
                    "economy_departure_impact_magnitude": 5,
                },
            )
            assert high.status_code == 200
            high_body = high.get_json()
            assert high_body["economy_preference_weight"] == 1.0
            assert high_body["economy_drift_magnitude"] == 5.0
            assert high_body["economy_departure_impact_magnitude"] == 0.2
        finally:
            app.config["space_store"].close()


def test_patch_config_clamps_orbital_knobs():
    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_API_KEY"] = "test-key"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        headers = {"X-API-Key": "test-key"}
        try:
            low = client.patch(
                "/config",
                headers=headers,
                json={
                    "orbital_distance_model_enabled": "yes",
                    "orbital_distance_multiplier_min": -5,
                    "orbital_distance_multiplier_max": 0,
                },
            )
            assert low.status_code == 200
            low_body = low.get_json()
            assert low_body["orbital_distance_model_enabled"] is True
            assert low_body["orbital_distance_multiplier_min"] == 0.5
            assert low_body["orbital_distance_multiplier_max"] == 1.0

            high = client.patch(
                "/config",
                headers=headers,
                json={
                    "orbital_distance_model_enabled": False,
                    "orbital_distance_multiplier_min": 5,
                    "orbital_distance_multiplier_max": 9,
                },
            )
            assert high.status_code == 200
            high_body = high.get_json()
            assert high_body["orbital_distance_model_enabled"] is False
            assert high_body["orbital_distance_multiplier_min"] == 1.0
            assert high_body["orbital_distance_multiplier_max"] == 1.5
        finally:
            app.config["space_store"].close()
