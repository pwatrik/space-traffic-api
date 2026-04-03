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


def test_price_index_raises_local_value_score():
    """Seeding two identical stations except for price_index should yield a higher
    local_value_score for the station with the higher price_index."""
    with TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = SQLiteStore(db_path)
        store.init_schema()

        base = {
            "body_name": "Test", "body_type": "planet", "parent_body": "Test",
            "cargo_type": "ore", "allowed_size_classes": ["medium"],
            "economy_profile": {"producer_rate": 0.06, "consumer_rate": 0.06,
                                "manufacturing_material_demand": 0.5, "distance_rank": 3},
        }
        stations = [
            {**base, "id": "STN-CHEAP", "name": "Cheap",
             "economy_state": {"primary_good": "ore", "supply_index": 1.0, "demand_index": 1.0,
                               "price_index": 0.7, "fuel_price_index": 1.0}},
            {**base, "id": "STN-EXPENSIVE", "name": "Expensive",
             "economy_state": {"primary_good": "ore", "supply_index": 1.0, "demand_index": 1.0,
                               "price_index": 2.0, "fuel_price_index": 1.0}},
        ]
        store.seed_stations(stations)
        try:
            rows, _ = store.list_stations(limit=10)
            by_id = {row["id"]: row for row in rows}
            score_cheap = float(by_id["STN-CHEAP"]["economy_derived"]["local_value_score"])
            score_expensive = float(by_id["STN-EXPENSIVE"]["economy_derived"]["local_value_score"])
            assert score_expensive > score_cheap, (
                f"Expected STN-EXPENSIVE ({score_expensive}) > STN-CHEAP ({score_cheap})"
            )
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


def test_apply_departure_economy_impact_updates_source_and_destination_indexes():
    with TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = SQLiteStore(db_path)
        store.init_schema()
        store.seed_stations(build_stations())
        try:
            rows_before, _ = store.list_stations(limit=5000, order_by="id", order="asc")
            by_id_before = {row["id"]: row for row in rows_before}

            source_id = "STN-PLANET-EARTH"
            destination_id = "STN-PLANET-MARS"
            src_before_supply = float(by_id_before[source_id]["economy_state"]["supply_index"])
            dst_before_demand = float(by_id_before[destination_id]["economy_state"]["demand_index"])

            updates = store.apply_departure_economy_impact(
                source_station_id=source_id,
                destination_station_id=destination_id,
                rng=random.Random(2026),
            )
            assert updates == 2

            rows_after, _ = store.list_stations(limit=5000, order_by="id", order="asc")
            by_id_after = {row["id"]: row for row in rows_after}
            src_after_supply = float(by_id_after[source_id]["economy_state"]["supply_index"])
            dst_after_demand = float(by_id_after[destination_id]["economy_state"]["demand_index"])

            assert src_after_supply < src_before_supply
            assert dst_after_demand < dst_before_demand
            assert 0.1 <= src_after_supply <= 5.0
            assert 0.1 <= dst_after_demand <= 5.0
        finally:
            store.close()


def test_apply_departure_economy_impact_is_deterministic_with_seeded_rng():
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
            s1.apply_departure_economy_impact(
                source_station_id="STN-PLANET-EARTH",
                destination_station_id="STN-PLANET-MARS",
                rng=random.Random(99),
            )
            s2.apply_departure_economy_impact(
                source_station_id="STN-PLANET-EARTH",
                destination_station_id="STN-PLANET-MARS",
                rng=random.Random(99),
            )

            rows1, _ = s1.list_stations(limit=5000, order_by="id", order="asc")
            rows2, _ = s2.list_stations(limit=5000, order_by="id", order="asc")

            state1 = {row["id"]: row.get("economy_state", {}) for row in rows1}
            state2 = {row["id"]: row.get("economy_state", {}) for row in rows2}

            assert state1 == state2
        finally:
            s1.close()
            s2.close()


def test_fuel_pressure_score_higher_for_distant_station():
    with TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = SQLiteStore(db_path)
        store.init_schema()
        store.seed_stations(build_stations())
        try:
            rows, _ = store.list_stations(limit=5000, order_by="id", order="asc")
            by_id = {row["id"]: row for row in rows}

            earth = by_id.get("STN-PLANET-EARTH")
            pluto = by_id.get("STN-PLANET-PLUTO")

            assert earth is not None and pluto is not None
            earth_fuel = float(earth["economy_derived"]["fuel_pressure_score"])
            pluto_fuel = float(pluto["economy_derived"]["fuel_pressure_score"])

            assert pluto_fuel > earth_fuel
        finally:
            store.close()


def test_economy_magnitude_controls_are_deterministic_with_seeded_rng():
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
            s1.advance_station_economy(elapsed_days=0.75, rng=random.Random(2027), magnitude=1.7)
            s2.advance_station_economy(elapsed_days=0.75, rng=random.Random(2027), magnitude=1.7)

            s1.apply_departure_economy_impact(
                source_station_id="STN-PLANET-EARTH",
                destination_station_id="STN-PLANET-MARS",
                rng=random.Random(2028),
                magnitude=0.03,
            )
            s2.apply_departure_economy_impact(
                source_station_id="STN-PLANET-EARTH",
                destination_station_id="STN-PLANET-MARS",
                rng=random.Random(2028),
                magnitude=0.03,
            )

            rows1, _ = s1.list_stations(limit=5000, order_by="id", order="asc")
            rows2, _ = s2.list_stations(limit=5000, order_by="id", order="asc")

            state1 = {row["id"]: row.get("economy_state", {}) for row in rows1}
            state2 = {row["id"]: row.get("economy_state", {}) for row in rows2}

            assert state1 == state2
        finally:
            s1.close()
            s2.close()


def test_price_index_drifts_toward_demand_over_supply_equilibrium():
    with TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = SQLiteStore(db_path)
        store.init_schema()

        station = {
            "id": "STN-TEST-HIGHDEMAND",
            "name": "Test High Demand",
            "body_name": "Test",
            "body_type": "planet",
            "parent_body": "Test",
            "cargo_type": "fuel",
            "allowed_size_classes": ["medium"],
            "economy_profile": {
                "producer_rate": 0.05,
                "consumer_rate": 0.08,
                "manufacturing_material_demand": 0.5,
                "distance_rank": 3,
            },
            "economy_state": {
                "primary_good": "fuel",
                "supply_index": 0.6,
                "demand_index": 1.8,
                "price_index": 1.0,
                "fuel_price_index": 1.0,
            },
        }
        store.seed_stations([station])
        try:
            store.advance_station_economy(elapsed_days=30.0, rng=random.Random(100), magnitude=1.0)
            rows, _ = store.list_stations(limit=10)
            row = rows[0]
            new_price = float(row["economy_state"]["price_index"])
            assert new_price > 1.0, f"price_index should have risen but got {new_price}"
        finally:
            store.close()


def test_price_index_falls_when_supply_exceeds_demand():
    with TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = SQLiteStore(db_path)
        store.init_schema()

        station = {
            "id": "STN-TEST-OVERSUPPLY",
            "name": "Test Oversupply",
            "body_name": "Test",
            "body_type": "planet",
            "parent_body": "Test",
            "cargo_type": "ore",
            "allowed_size_classes": ["medium"],
            "economy_profile": {
                "producer_rate": 0.08,
                "consumer_rate": 0.04,
                "manufacturing_material_demand": 0.3,
                "distance_rank": 3,
            },
            "economy_state": {
                "primary_good": "ore",
                "supply_index": 2.0,
                "demand_index": 0.8,
                "price_index": 1.0,
                "fuel_price_index": 1.0,
            },
        }
        store.seed_stations([station])
        try:
            store.advance_station_economy(elapsed_days=30.0, rng=random.Random(200), magnitude=1.0)
            rows, _ = store.list_stations(limit=10)
            row = rows[0]
            new_price = float(row["economy_state"]["price_index"])
            assert new_price < 1.0, f"price_index should have fallen but got {new_price}"
        finally:
            store.close()


def test_price_index_stable_when_supply_equals_demand():
    with TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = SQLiteStore(db_path)
        store.init_schema()

        station = {
            "id": "STN-TEST-BALANCED",
            "name": "Test Balanced",
            "body_name": "Test",
            "body_type": "planet",
            "parent_body": "Test",
            "cargo_type": "water",
            "allowed_size_classes": ["medium"],
            "economy_profile": {
                "producer_rate": 0.06,
                "consumer_rate": 0.06,
                "manufacturing_material_demand": 0.5,
                "distance_rank": 3,
            },
            "economy_state": {
                "primary_good": "water",
                "supply_index": 1.0,
                "demand_index": 1.0,
                "price_index": 1.0,
                "fuel_price_index": 1.0,
            },
        }
        store.seed_stations([station])
        try:
            store.advance_station_economy(elapsed_days=60.0, rng=random.Random(300), magnitude=1.0)
            rows, _ = store.list_stations(limit=10)
            row = rows[0]
            new_price = float(row["economy_state"]["price_index"])
            assert 0.8 <= new_price <= 1.2, f"price_index strayed too far: {new_price}"
        finally:
            store.close()


def test_price_index_drift_is_deterministic_with_seeded_rng():
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
            s1.advance_station_economy(elapsed_days=5.0, rng=random.Random(4321), magnitude=1.0)
            s2.advance_station_economy(elapsed_days=5.0, rng=random.Random(4321), magnitude=1.0)

            rows1, _ = s1.list_stations(limit=5000, order_by="id", order="asc")
            rows2, _ = s2.list_stations(limit=5000, order_by="id", order="asc")

            prices1 = {row["id"]: row["economy_state"].get("price_index") for row in rows1}
            prices2 = {row["id"]: row["economy_state"].get("price_index") for row in rows2}
            assert prices1 == prices2
        finally:
            s1.close()
            s2.close()


def test_departure_impact_eases_destination_price_index():
    """A departure shipment should lower the destination station's price_index."""
    with TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = SQLiteStore(db_path)
        store.init_schema()
        store.seed_stations(build_stations())
        try:
            rows_before, _ = store.list_stations(limit=5000, order_by="id", order="asc")
            before = {row["id"]: float((row.get("economy_state") or {}).get("price_index", 1.0)) for row in rows_before}

            destination_id = "STN-PLANET-MARS"
            store.apply_departure_economy_impact(
                source_station_id="STN-PLANET-EARTH",
                destination_station_id=destination_id,
                rng=random.Random(5555),
                magnitude=0.05,
            )

            rows_after, _ = store.list_stations(limit=5000, order_by="id", order="asc")
            after = {row["id"]: float((row.get("economy_state") or {}).get("price_index", 1.0)) for row in rows_after}

            assert after[destination_id] < before[destination_id], (
                f"Expected destination price to fall: before={before[destination_id]}, after={after[destination_id]}"
            )
        finally:
            store.close()


def test_departure_price_ease_is_deterministic_with_seeded_rng():
    """Two identical stores using the same seeded RNG produce identical price_index after departure impact."""
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
            s1.apply_departure_economy_impact(
                source_station_id="STN-PLANET-EARTH",
                destination_station_id="STN-PLANET-MARS",
                rng=random.Random(6789),
                magnitude=0.04,
            )
            s2.apply_departure_economy_impact(
                source_station_id="STN-PLANET-EARTH",
                destination_station_id="STN-PLANET-MARS",
                rng=random.Random(6789),
                magnitude=0.04,
            )

            rows1, _ = s1.list_stations(limit=5000, order_by="id", order="asc")
            rows2, _ = s2.list_stations(limit=5000, order_by="id", order="asc")

            prices1 = {row["id"]: row["economy_state"].get("price_index") for row in rows1}
            prices2 = {row["id"]: row["economy_state"].get("price_index") for row in rows2}
            assert prices1 == prices2
        finally:
            s1.close()
            s2.close()
