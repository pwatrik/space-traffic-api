import os
import time
from tempfile import TemporaryDirectory

from space_traffic_api.app import create_app


def test_healthz_and_public_endpoints():
    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_API_KEY"] = "test-key"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        try:
            health = client.get("/healthz")
            assert health.status_code == 200
            health_payload = health.get_json()
            assert "runtime_metrics" in health_payload
            assert "tick_count" in health_payload["runtime_metrics"]
            assert "departures_per_minute_recent" in health_payload["runtime_metrics"]

            stations = client.get("/stations")
            assert stations.status_code == 200
            payload = stations.get_json()
            assert payload["count"] >= 30
            station_ids = {station["id"] for station in payload["stations"]}
            assert "STN-PLANET-PLUTO" in station_ids
            assert "STN-MOON-CHARON" in station_ids
        finally:
            app.config["space_store"].close()


def test_ui_dashboard_page_loads():
    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        try:
            response = client.get("/ui")
            assert response.status_code == 200
            content = response.get_data(as_text=True)
            assert "Space Traffic Console" in content
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
            response = client.get("/stats")
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
            assert "runtime_metrics" in payload
            assert "control_event_backlog_total" in payload["runtime_metrics"]
            assert "tick_latency_ms_avg" in payload["runtime_metrics"]
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


def test_stats_includes_economy_summary():
    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        try:
            response = client.get("/stats")
            assert response.status_code == 200
            payload = response.get_json()
            assert "economy_summary" in payload, "economy_summary missing from /stats"
            eco = payload["economy_summary"]
            assert eco["station_count"] > 0
            assert "price_index_avg" in eco
            assert "price_index_min" in eco
            assert "price_index_max" in eco
            assert "supply_index_avg" in eco
            assert "demand_index_avg" in eco
            assert "stations_above_equilibrium" in eco
            assert "stations_below_equilibrium" in eco
            # Sanity bounds
            assert 0.5 <= eco["price_index_min"] <= eco["price_index_max"] <= 3.0
            assert eco["stations_above_equilibrium"] + eco["stations_below_equilibrium"] <= eco["station_count"]
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
            response = client.get("/ships")
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
            response = client.get("/ships?limit=10")
            payload = response.get_json()
            assert len(payload["ships"]) == 10
            assert payload["count"] == 10
            assert payload["total_count"] == total_ships
            assert payload["limit"] == 10

            # Test with offset
            response = client.get("/ships?limit=10&offset=5")
            payload = response.get_json()
            assert len(payload["ships"]) == 10
            assert payload["offset"] == 5

            # Test with order_by and order
            response1 = client.get("/ships?limit=20&order_by=faction&order=asc")
            payload1 = response1.get_json()
            factions1 = [ship["faction"] for ship in payload1["ships"]]

            response2 = client.get("/ships?limit=20&order_by=faction&order=desc")
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
            response = client.get("/stations")
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
            response = client.get("/stations?limit=10")
            payload = response.get_json()
            assert len(payload["stations"]) == 10
            assert payload["count"] == 10
            assert payload["total_count"] == total_stations
            assert payload["limit"] == 10

            # Test body_type filter with pagination
            response = client.get("/stations?body_type=planet&limit=5")
            payload = response.get_json()
            assert payload["count"] <= 5
            for station in payload["stations"]:
                assert station["body_type"] == "planet"
        finally:
            app.config["space_store"].close()


def test_stations_include_economy_scaffold_fields():
    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        try:
            response = client.get("/stations?limit=1")
            assert response.status_code == 200
            payload = response.get_json()
            assert payload["count"] == 1
            station = payload["stations"][0]
            assert "economy_profile" in station
            assert "economy_state" in station
            assert isinstance(station["economy_profile"], dict)
            assert isinstance(station["economy_state"], dict)
            assert "primary_good" in station["economy_state"]
            assert "economy_derived" in station
            assert "local_value_score" in station["economy_derived"]
            assert "scarcity_index" in station["economy_derived"]
            assert "fuel_pressure_score" in station["economy_derived"]

            assert 0.1 <= float(station["economy_derived"]["local_value_score"]) <= 10.0
            assert 0.1 <= float(station["economy_derived"]["scarcity_index"]) <= 10.0
            assert 0.1 <= float(station["economy_derived"]["fuel_pressure_score"]) <= 10.0
        finally:
            app.config["space_store"].close()


def test_station_economy_derived_metrics_are_deterministic_across_boots():
    with TemporaryDirectory() as tmp1, TemporaryDirectory() as tmp2:
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"

        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp1}/test.db"
        app1 = create_app()
        client1 = app1.test_client()
        try:
            r1 = client1.get("/stations?limit=5000&order_by=id&order=asc")
            assert r1.status_code == 200
            s1 = {
                row["id"]: row.get("economy_derived", {})
                for row in r1.get_json()["stations"]
            }
        finally:
            app1.config["space_store"].close()

        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp2}/test.db"
        app2 = create_app()
        client2 = app2.test_client()
        try:
            r2 = client2.get("/stations?limit=5000&order_by=id&order=asc")
            assert r2.status_code == 200
            s2 = {
                row["id"]: row.get("economy_derived", {})
                for row in r2.get_json()["stations"]
            }
        finally:
            app2.config["space_store"].close()

        assert s1 == s2


def test_merchant_departure_updates_ship_cargo_from_source_station(monkeypatch):
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", f"{tmp}/test.db")
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "false")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "777")
        monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "240")
        monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "240")

        app = create_app()
        client = app.test_client()
        try:
            stations_resp = client.get("/stations?limit=5000")
            assert stations_resp.status_code == 200
            stations = stations_resp.get_json()["stations"]
            station_cargo = {row["id"]: row.get("cargo_type", "") for row in stations}

            merchant_departure = None

            deadline = time.time() + 6.0
            while time.time() < deadline and merchant_departure is None:
                dep_resp = client.get("/departures?limit=200")
                assert dep_resp.status_code == 200
                departures = dep_resp.get_json()["departures"]

                ships_resp = client.get("/ships?limit=5000")
                assert ships_resp.status_code == 200
                ship_by_id = {row["id"]: row for row in ships_resp.get_json()["ships"]}

                for dep in departures:
                    ship = ship_by_id.get(dep["ship_id"])
                    if ship and ship.get("faction") == "merchant":
                        merchant_departure = dep
                        break

                if merchant_departure is None:
                    time.sleep(0.2)

            assert merchant_departure is not None

            source_station_id = merchant_departure["source_station_id"]
            expected_cargo = station_cargo.get(source_station_id, "")
            assert expected_cargo

            # Re-fetch ships after finding the departure so cargo reflects the
            # set_ship_cargo update made by create_departure_event.
            refreshed = client.get("/ships?limit=5000")
            assert refreshed.status_code == 200
            refreshed_by_id = {row["id"]: row for row in refreshed.get_json()["ships"]}
            merchant_ship = refreshed_by_id[merchant_departure["ship_id"]]
            assert merchant_ship["cargo"] == expected_cargo
        finally:
            app.config["space_simulation"].stop(timeout=6.0)
            app.config["space_store"].close()


def test_config_includes_orbital_diagnostics(monkeypatch):
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", f"{tmp}/test.db")
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "5150")
        monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MODEL_ENABLED", "true")

        app = create_app()
        client = app.test_client()
        try:
            response = client.get("/config")
            assert response.status_code == 200
            payload = response.get_json()
            assert "orbital_diagnostics" in payload

            diagnostics = payload["orbital_diagnostics"]
            assert diagnostics["enabled"] is True
            assert diagnostics["body_count"] > 0
            assert diagnostics["station_anchor_count"] >= diagnostics["body_count"]
            assert "bodies" in diagnostics
            assert "Earth" in diagnostics["bodies"]

            earth = diagnostics["bodies"]["Earth"]
            assert earth["body_id"] == "Earth"
            assert "phase_radians" in earth
            assert "x" in earth
            assert "y" in earth
        finally:
            app.config["space_store"].close()


