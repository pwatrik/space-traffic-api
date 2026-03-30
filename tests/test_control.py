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

            control_events = client.get("/control-events", headers=headers)
            assert control_events.status_code == 200
            events_payload = control_events.get_json()
            assert events_payload["count"] >= 3
            actions = {(event["event_type"], event["action"]) for event in events_payload["control_events"]}
            assert ("scenario", "activated") in actions
            assert ("fault", "activated") in actions
            assert ("control", "reset") in actions
        finally:
            app.config["space_store"].close()
