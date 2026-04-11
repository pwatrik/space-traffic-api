import os
from pathlib import Path
from tempfile import TemporaryDirectory

from space_traffic_api.app import create_app


def test_healthz_contract_shape_is_stable():
    expected_keys = {
        "status",
        "server_time",
        "counts",
        "active_scenario",
        "active_faults",
        "deterministic_mode",
        "db_size_bytes",
        "db_max_size_bytes",
        "runtime_metrics",
    }

    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_API_KEY"] = "test-key"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        try:
            response = client.get("/healthz")
            assert response.status_code == 200
            payload = response.get_json()
            assert set(payload.keys()) == expected_keys

            metrics = payload["runtime_metrics"]
            assert "tick_count" in metrics
            assert "tick_latency_ms_avg" in metrics
            assert "departures_per_minute_recent" in metrics
        finally:
            app.config["space_store"].close()


def test_stats_contract_shape_is_stable():
    expected_keys = {
        "summary",
        "factions",
        "ship_types",
        "cargo_types",
        "ship_states",
        "economy_summary",
        "pirate_strength",
        "active_scenario",
        "runtime_metrics",
    }

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
            assert set(payload.keys()) == expected_keys
        finally:
            app.config["space_store"].close()


def test_openapi_contract_contains_core_paths():
    spec_path = Path(__file__).parent.parent / "docs" / "openapi.yaml"
    content = spec_path.read_text(encoding="utf-8")

    # Lightweight canary checks to catch accidental path removals.
    required_paths = [
        "/healthz:",
        "/stats:",
        "/departures:",
        "/control-events:",
        "/config:",
    ]
    for required in required_paths:
        assert required in content, f"Missing OpenAPI path entry: {required}"


def test_stations_and_ships_contract_shapes_are_stable():
    stations_meta_keys = {"stations", "count", "total_count", "offset", "limit"}
    ships_meta_keys = {"ships", "count", "total_count", "offset", "limit"}
    station_keys = {
        "id",
        "name",
        "body_name",
        "body_type",
        "parent_body",
        "allowed_size_classes",
        "cargo_type",
        "economy_profile",
        "economy_state",
        "economy_derived",
    }
    ship_keys = {
        "id",
        "name",
        "faction",
        "ship_type",
        "size_class",
        "displacement_million_m3",
        "home_station_id",
        "captain_name",
        "cargo",
        "crew",
        "passengers",
    }

    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        try:
            stations_resp = client.get("/stations?limit=1")
            assert stations_resp.status_code == 200
            stations_payload = stations_resp.get_json()
            assert set(stations_payload.keys()) == stations_meta_keys
            assert stations_payload["count"] == 1
            assert stations_payload["limit"] == 1
            assert stations_payload["offset"] == 0
            assert set(stations_payload["stations"][0].keys()) == station_keys

            ships_resp = client.get("/ships?limit=1")
            assert ships_resp.status_code == 200
            ships_payload = ships_resp.get_json()
            assert set(ships_payload.keys()) == ships_meta_keys
            assert ships_payload["count"] == 1
            assert ships_payload["limit"] == 1
            assert ships_payload["offset"] == 0
            assert set(ships_payload["ships"][0].keys()) == ship_keys
        finally:
            app.config["space_store"].close()


def test_ship_state_contract_shape_is_stable():
    response_keys = {"ships", "count"}
    ship_state_keys = {
        "ship_id",
        "name",
        "faction",
        "ship_type",
        "status",
        "home_station_id",
        "current_station_id",
        "in_transit",
        "source_station_id",
        "destination_station_id",
        "departure_time",
        "est_arrival_time",
        "ship_age_days",
        "updated_at",
    }

    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        try:
            state_resp = client.get("/ships/state?limit=1")
            assert state_resp.status_code == 200
            state_payload = state_resp.get_json()
            assert set(state_payload.keys()) == response_keys
            assert state_payload["count"] == 1
            assert set(state_payload["ships"][0].keys()) == ship_state_keys
        finally:
            app.config["space_store"].close()


def test_departure_and_control_event_contract_shapes_are_stable():
    departures_response_keys = {"departures", "count", "next_since_id"}
    control_response_keys = {"control_events", "count", "next_since_id"}
    departure_keys = {
        "id",
        "event_uid",
        "departure_time",
        "ship_id",
        "source_station_id",
        "destination_station_id",
        "est_arrival_time",
        "scenario",
        "fault_flags",
        "malformed",
        "payload",
    }
    control_event_keys = {"id", "event_time", "event_type", "action", "payload"}

    with TemporaryDirectory() as tmp:
        os.environ["SPACE_TRAFFIC_DB_PATH"] = f"{tmp}/test.db"
        os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "true"
        app = create_app()
        client = app.test_client()
        store = app.config["space_store"]
        try:
            store.insert_departure(
                {
                    "event_uid": "M4-CONTRACT-DEP-1",
                    "departure_time": "2100-01-01T00:00:00+00:00",
                    "ship_id": "SHIP-0001",
                    "source_station_id": "STN-PLANET-EARTH",
                    "destination_station_id": "STN-PLANET-MARS",
                    "est_arrival_time": "2100-01-03T00:00:00+00:00",
                    "scenario": "baseline",
                    "fault_flags": [],
                    "malformed": False,
                    "payload_json": '{"event_uid":"M4-CONTRACT-DEP-1"}',
                }
            )
            store.insert_control_event(
                event_type="control",
                action="reset",
                payload={"seed": 123},
                event_time="2100-01-01T00:00:00+00:00",
            )

            departures_resp = client.get("/departures?limit=1")
            assert departures_resp.status_code == 200
            departures_payload = departures_resp.get_json()
            assert set(departures_payload.keys()) == departures_response_keys
            assert departures_payload["count"] == 1
            assert set(departures_payload["departures"][0].keys()) == departure_keys

            control_resp = client.get("/control-events?limit=1")
            assert control_resp.status_code == 200
            control_payload = control_resp.get_json()
            assert set(control_payload.keys()) == control_response_keys
            assert control_payload["count"] >= 1
            assert set(control_payload["control_events"][0].keys()) == control_event_keys
        finally:
            app.config["space_store"].close()
