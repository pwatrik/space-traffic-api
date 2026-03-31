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


def test_stats_endpoint():
    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_API_KEY"] = "test-key"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        try:
            response = client.get("/stats", headers={"X-API-Key": "test-key"})
            assert response.status_code == 200
            payload = response.get_json()
            # Verify required keys
            assert "summary" in payload
            assert "factions" in payload
            assert "ship_types" in payload
            assert "cargo_types" in payload
            assert "ship_states" in payload
            assert "pirate_strength" in payload
            assert "active_scenario" in payload
            # Verify summary has expected structure
            assert "stations" in payload["summary"]
            assert "ships" in payload["summary"]
            assert payload["summary"]["ships"] > 0
            # Verify faction stats has entries
            assert len(payload["factions"]) > 0
            # Verify ship_types has entries
            assert len(payload["ship_types"]) > 0
        finally:
            app.config["space_store"].close()


def test_ships_pagination():
    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_API_KEY"] = "test-key"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        try:
            # Test default pagination
            response = client.get("/ships", headers={"X-API-Key": "test-key"})
            assert response.status_code == 200
            payload = response.get_json()
            assert "ships" in payload
            assert "count" in payload
            assert "total_count" in payload
            assert "offset" in payload
            assert "limit" in payload
            assert payload["offset"] == 0
            assert payload["limit"] == 1000
            total_ships = payload["total_count"]
            assert total_ships == 500  # Default fleet size

            # Test with limit
            response = client.get("/ships?limit=10", headers={"X-API-Key": "test-key"})
            payload = response.get_json()
            assert len(payload["ships"]) == 10
            assert payload["count"] == 10
            assert payload["total_count"] == total_ships
            assert payload["limit"] == 10

            # Test with offset
            response = client.get("/ships?limit=10&offset=5", headers={"X-API-Key": "test-key"})
            payload = response.get_json()
            assert len(payload["ships"]) == 10
            assert payload["offset"] == 5

            # Test with order_by and order
            response1 = client.get("/ships?limit=20&order_by=faction&order=asc", headers={"X-API-Key": "test-key"})
            payload1 = response1.get_json()
            factions1 = [ship["faction"] for ship in payload1["ships"]]

            response2 = client.get("/ships?limit=20&order_by=faction&order=desc", headers={"X-API-Key": "test-key"})
            payload2 = response2.get_json()
            factions2 = [ship["faction"] for ship in payload2["ships"]]
            # Should be different order
            assert factions1 != factions2 or len(set(factions1)) == 1  # Allow if all same faction
        finally:
            app.config["space_store"].close()


def test_stations_pagination():
    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_API_KEY"] = "test-key"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        try:
            # Test default pagination
            response = client.get("/stations", headers={"X-API-Key": "test-key"})
            assert response.status_code == 200
            payload = response.get_json()
            assert "stations" in payload
            assert "count" in payload
            assert "total_count" in payload
            assert "offset" in payload
            assert "limit" in payload
            assert payload["offset"] == 0
            total_stations = payload["total_count"]
            assert total_stations >= 30

            # Test with limit
            response = client.get("/stations?limit=10", headers={"X-API-Key": "test-key"})
            payload = response.get_json()
            assert len(payload["stations"]) == 10
            assert payload["count"] == 10
            assert payload["total_count"] == total_stations
            assert payload["limit"] == 10

            # Test body_type filter with pagination
            response = client.get("/stations?body_type=planet&limit=5", headers={"X-API-Key": "test-key"})
            payload = response.get_json()
            assert payload["count"] <= 5
            for station in payload["stations"]:
                assert station["body_type"] == "planet"
        finally:
            app.config["space_store"].close()
