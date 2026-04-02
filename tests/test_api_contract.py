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
