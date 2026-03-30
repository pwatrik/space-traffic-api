import os
from tempfile import TemporaryDirectory

from space_traffic_api.app import create_app


def test_healthz_and_auth_guard():
    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_API_KEY"] = "test-key"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        try:
            health = client.get("/healthz")
            assert health.status_code == 200

            unauthorized = client.get("/stations")
            assert unauthorized.status_code == 401

            authorized = client.get("/stations", headers={"X-API-Key": "test-key"})
            assert authorized.status_code == 200
            payload = authorized.get_json()
            assert payload["count"] >= 30
            station_ids = {station["id"] for station in payload["stations"]}
            assert "STN-PLANET-PLUTO" in station_ids
            assert "STN-MOON-CHARON" in station_ids
        finally:
            app.config["space_store"].close()
