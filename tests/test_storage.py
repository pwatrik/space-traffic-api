import os
import random
from tempfile import TemporaryDirectory

from space_traffic_api.store import SQLiteStore
from space_traffic_api.seed_data import build_stations


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


def test_advance_station_economy_updates_supply_and_demand_within_bounds():
    with TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = SQLiteStore(db_path)
        store.init_schema()
        store.seed_stations(build_stations())
        try:
            before_rows, _ = store.list_stations(limit=5000, order_by="id", order="asc")
            before = {
                row["id"]: (
                    float((row.get("economy_state") or {}).get("supply_index", 1.0)),
                    float((row.get("economy_state") or {}).get("demand_index", 1.0)),
                )
                for row in before_rows
            }

            updated = store.advance_station_economy(elapsed_days=0.5, rng=random.Random(12345))
            assert updated == len(before_rows)

            after_rows, _ = store.list_stations(limit=5000, order_by="id", order="asc")
            after = {
                row["id"]: (
                    float((row.get("economy_state") or {}).get("supply_index", 1.0)),
                    float((row.get("economy_state") or {}).get("demand_index", 1.0)),
                )
                for row in after_rows
            }

            assert after.keys() == before.keys()
            assert any(after[sid] != before[sid] for sid in after)
            assert all(0.1 <= vals[0] <= 5.0 for vals in after.values())
            assert all(0.1 <= vals[1] <= 5.0 for vals in after.values())
        finally:
            store.close()


def test_advance_station_economy_is_deterministic_with_seeded_rng():
    with TemporaryDirectory() as tmp1, TemporaryDirectory() as tmp2:
        stations = build_stations()

        db1 = os.path.join(tmp1, "test1.db")
        db2 = os.path.join(tmp2, "test2.db")

        s1 = SQLiteStore(db1)
        s2 = SQLiteStore(db2)
        s1.init_schema()
        s2.init_schema()
        s1.seed_stations(stations)
        s2.seed_stations(stations)
        try:
            s1.advance_station_economy(elapsed_days=0.75, rng=random.Random(777))
            s2.advance_station_economy(elapsed_days=0.75, rng=random.Random(777))

            rows1, _ = s1.list_stations(limit=5000, order_by="id", order="asc")
            rows2, _ = s2.list_stations(limit=5000, order_by="id", order="asc")

            state1 = {row["id"]: row.get("economy_state", {}) for row in rows1}
            state2 = {row["id"]: row.get("economy_state", {}) for row in rows2}

            assert state1 == state2
        finally:
            s1.close()
            s2.close()
