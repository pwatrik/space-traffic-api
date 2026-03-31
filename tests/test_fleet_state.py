import os
from tempfile import TemporaryDirectory

from space_traffic_api.app import create_app


def test_ship_state_seeded_and_resettable(monkeypatch):
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", f"{tmp}/test.db")
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")

        app = create_app()
        client = app.test_client()
        headers = {"X-API-Key": "test-key"}
        try:
            states = client.get("/ships/state", headers=headers)
            assert states.status_code == 200
            body = states.get_json()
            assert body["count"] == 220
            assert all(ship["in_transit"] == 0 for ship in body["ships"])

            reset = client.post("/control/reset", headers=headers, json={"seed": 777})
            assert reset.status_code == 200

            states_after = client.get("/ships/state", headers=headers)
            assert states_after.status_code == 200
            body_after = states_after.get_json()
            assert all(ship["in_transit"] == 0 for ship in body_after["ships"])
        finally:
            app.config["space_store"].close()
