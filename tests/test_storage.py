import os
from tempfile import TemporaryDirectory

from space_traffic_api.store import SQLiteStore


def _event(i: int, payload_size: int) -> dict:
    payload = "X" * payload_size
    return {
        "event_uid": f"E-{i}",
        "departure_time": "2150-01-01T00:00:00+00:00",
        "ship_id": "SHIP-0001",
        "source_station_id": "STN-PLANET-EARTH",
        "destination_station_id": "STN-PLANET-MARS",
        "est_arrival_time": "2150-01-01T08:00:00+00:00",
        "scenario": "baseline",
        "fault_flags": [],
        "malformed": False,
        "payload_json": "{\"payload\": \"" + payload + "\"}",
    }


def test_enforce_db_size_limit_culls_old_departures():
    with TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = SQLiteStore(db_path)
        store.init_schema()
        try:
            for i in range(120):
                store.insert_departure(_event(i, payload_size=4000))

            before = store.get_db_size_bytes()
            result = store.enforce_db_size_limit(max_db_size_bytes=max(1, before // 2))
            after = store.get_db_size_bytes()

            assert result["culled_departures"] > 0
            assert after < before
            assert store.get_counts()["departures"] < 120
        finally:
            store.close()
