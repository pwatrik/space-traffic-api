import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from space_traffic_api.app import create_app


def _legacy_bootstrap_schema(db_path: Path) -> None:
    """Create a pre-migration schema that intentionally misses newer columns."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE stations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                body_name TEXT NOT NULL,
                body_type TEXT NOT NULL,
                parent_body TEXT NOT NULL
            );

            CREATE TABLE ships (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                faction TEXT NOT NULL,
                ship_type TEXT NOT NULL,
                displacement_million_m3 REAL NOT NULL,
                home_station_id TEXT NOT NULL,
                captain_name TEXT NOT NULL
            );

            CREATE TABLE ship_state (
                ship_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                current_station_id TEXT,
                in_transit INTEGER NOT NULL DEFAULT 0,
                source_station_id TEXT,
                destination_station_id TEXT,
                departure_time TEXT,
                est_arrival_time TEXT,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _column_names(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row[1] for row in rows}
    finally:
        conn.close()


def test_create_app_migrates_legacy_schema_columns(monkeypatch):
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "legacy.db"
        _legacy_bootstrap_schema(db_path)

        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")

        app = create_app()
        client = app.test_client()
        try:
            stations_resp = client.get("/stations")
            assert stations_resp.status_code == 200
            assert stations_resp.get_json()["total_count"] >= 30

            ships_resp = client.get("/ships?limit=1")
            assert ships_resp.status_code == 200
            ship = ships_resp.get_json()["ships"][0]
            assert "size_class" in ship
            assert "cargo" in ship
            assert "crew" in ship
            assert "passengers" in ship

            state_resp = client.get("/ships/state?limit=1")
            assert state_resp.status_code == 200
            ship_state = state_resp.get_json()["ships"][0]
            assert "ship_age_days" in ship_state
            assert "observed_at" in ship_state

            stations_cols = _column_names(db_path, "stations")
            ships_cols = _column_names(db_path, "ships")
            ship_state_cols = _column_names(db_path, "ship_state")
            assert "allowed_size_classes" in stations_cols
            assert "cargo_type" in stations_cols
            assert "economy_profile" in stations_cols
            assert "economy_state" in stations_cols
            assert "size_class" in ships_cols
            assert "cargo" in ships_cols
            assert "crew" in ships_cols
            assert "passengers" in ships_cols
            assert "ship_age_days" in ship_state_cols
            assert "observed_at" in ship_state_cols
        finally:
            app.config["space_store"].close()


def test_prepopulated_db_startup_and_reset_departures(monkeypatch):
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "prepopulated.db"

        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", str(db_path))
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "true")

        app1 = create_app()
        try:
            store = app1.config["space_store"]
            store.insert_departure(
                {
                    "event_uid": "LEGACY-EVT-1",
                    "departure_time": "2150-01-01T00:00:00+00:00",
                    "ship_id": "SHIP-0001",
                    "source_station_id": "STN-PLANET-EARTH",
                    "destination_station_id": "STN-PLANET-MARS",
                    "est_arrival_time": "2150-01-01T08:00:00+00:00",
                    "scenario": "baseline",
                    "fault_flags": [],
                    "malformed": False,
                    "payload_json": "{\"event_uid\":\"LEGACY-EVT-1\"}",
                }
            )
            store.insert_control_event(
                event_type="control",
                action="seeded",
                payload={"source": "phase65-test"},
            )
        finally:
            app1.config["space_store"].close()

        app2 = create_app()
        client = app2.test_client()
        headers = {"X-API-Key": "test-key"}
        try:
            deps_before = client.get("/departures?limit=10", headers=headers)
            assert deps_before.status_code == 200
            departures = deps_before.get_json()["departures"]
            assert len(departures) >= 1
            assert departures[0]["event_uid"] == "LEGACY-EVT-1"

            reset = client.post("/control/reset", headers=headers, json={"seed": 555})
            assert reset.status_code == 200
            assert reset.get_json()["status"] == "reset"

            deps_after = client.get("/departures?limit=10", headers=headers)
            assert deps_after.status_code == 200
            assert deps_after.get_json()["count"] == 0

            states_after = client.get("/ships/state?limit=1000", headers=headers)
            assert states_after.status_code == 200
            rows = states_after.get_json()["ships"]
            assert rows
            assert all(row["in_transit"] == 0 for row in rows)

            control_events = client.get("/control-events?limit=50", headers=headers)
            assert control_events.status_code == 200
            actions = {event["action"] for event in control_events.get_json()["control_events"]}
            assert "seeded" in actions
            assert "reset" in actions
        finally:
            app2.config["space_store"].close()
