import random

from space_traffic_api.simulation.engine.routing import pick_destination


def _accepts_all(_station_id: str, _size_class: str) -> bool:
    return True


def test_merchant_prefers_higher_value_destination():
    station_lookup = {
        "SRC": {"id": "SRC", "economy_derived": {"local_value_score": 1.0}},
        "DST_LOW": {"id": "DST_LOW", "economy_derived": {"local_value_score": 0.8}},
        "DST_HIGH": {"id": "DST_HIGH", "economy_derived": {"local_value_score": 3.2}},
    }

    ship = {"faction": "merchant", "size_class": "medium"}
    rng = random.Random(1337)
    counts = {"DST_LOW": 0, "DST_HIGH": 0}

    for _ in range(600):
        dst = pick_destination(
            ship=ship,
            source_station_id="SRC",
            scenario=None,
            station_lookup=station_lookup,
            pirate_conf={},
            pirate_state=None,
            rng=rng,
            station_accepts_size_class=_accepts_all,
            economy_preference_weight=0.15,
        )
        counts[dst] += 1

    assert counts["DST_HIGH"] > counts["DST_LOW"]


def test_non_merchant_ignores_economy_preference_weight():
    station_lookup = {
        "SRC": {"id": "SRC", "economy_derived": {"local_value_score": 1.0}},
        "DST_A": {"id": "DST_A", "economy_derived": {"local_value_score": 0.5}},
        "DST_B": {"id": "DST_B", "economy_derived": {"local_value_score": 4.0}},
    }
    ship = {"faction": "military", "size_class": "medium"}

    rng_low = random.Random(2468)
    rng_high = random.Random(2468)

    picks_low = []
    picks_high = []
    for _ in range(120):
        picks_low.append(
            pick_destination(
                ship=ship,
                source_station_id="SRC",
                scenario=None,
                station_lookup=station_lookup,
                pirate_conf={},
                pirate_state=None,
                rng=rng_low,
                station_accepts_size_class=_accepts_all,
                economy_preference_weight=0.0,
            )
        )
        picks_high.append(
            pick_destination(
                ship=ship,
                source_station_id="SRC",
                scenario=None,
                station_lookup=station_lookup,
                pirate_conf={},
                pirate_state=None,
                rng=rng_high,
                station_accepts_size_class=_accepts_all,
                economy_preference_weight=1.0,
            )
        )

    assert picks_low == picks_high


def test_merchant_routing_is_deterministic_with_seeded_rng():
    station_lookup = {
        "SRC": {"id": "SRC", "economy_derived": {"local_value_score": 1.0}},
        "DST_1": {"id": "DST_1", "economy_derived": {"local_value_score": 2.0}},
        "DST_2": {"id": "DST_2", "economy_derived": {"local_value_score": 2.5}},
        "DST_3": {"id": "DST_3", "economy_derived": {"local_value_score": 1.8}},
    }
    ship = {"faction": "merchant", "size_class": "medium"}

    rng1 = random.Random(999)
    rng2 = random.Random(999)

    seq1 = [
        pick_destination(
            ship=ship,
            source_station_id="SRC",
            scenario=None,
            station_lookup=station_lookup,
            pirate_conf={},
            pirate_state=None,
            rng=rng1,
            station_accepts_size_class=_accepts_all,
            economy_preference_weight=0.15,
        )
        for _ in range(80)
    ]
    seq2 = [
        pick_destination(
            ship=ship,
            source_station_id="SRC",
            scenario=None,
            station_lookup=station_lookup,
            pirate_conf={},
            pirate_state=None,
            rng=rng2,
            station_accepts_size_class=_accepts_all,
            economy_preference_weight=0.15,
        )
        for _ in range(80)
    ]

    assert seq1 == seq2


def test_merchant_penalizes_high_fuel_cost_destination():
    """Merchant prefers a nearby moderate-value over a far same-value when fuel cost is high."""
    station_lookup = {
        "SRC": {
            "id": "SRC",
            "economy_derived": {"local_value_score": 1.0, "fuel_pressure_score": 1.1},
        },
        "DST_NEAR": {
            "id": "DST_NEAR",
            "economy_derived": {"local_value_score": 1.5, "fuel_pressure_score": 1.1},
        },
        "DST_FAR": {
            "id": "DST_FAR",
            "economy_derived": {"local_value_score": 1.5, "fuel_pressure_score": 2.2},
        },
    }
    ship = {"faction": "merchant", "size_class": "medium"}
    rng = random.Random(7777)
    counts = {"DST_NEAR": 0, "DST_FAR": 0}

    for _ in range(600):
        dst = pick_destination(
            ship=ship,
            source_station_id="SRC",
            scenario=None,
            station_lookup=station_lookup,
            pirate_conf={},
            pirate_state=None,
            rng=rng,
            station_accepts_size_class=_accepts_all,
            economy_preference_weight=0.5,
        )
        counts[dst] += 1

    assert counts["DST_NEAR"] > counts["DST_FAR"]


def test_merchant_routing_uses_price_index_from_economy_state():
    """When economy_derived is absent, routing falls back to economy_state and price_index influences
    destination preference: higher price_index means higher effective local value."""
    station_lookup = {
        "SRC": {
            "id": "SRC",
            "economy_state": {"supply_index": 1.0, "demand_index": 1.0, "price_index": 1.0},
        },
        "DST_HIGH_PRICE": {
            "id": "DST_HIGH_PRICE",
            "economy_state": {"supply_index": 1.0, "demand_index": 1.0, "price_index": 2.5},
        },
        "DST_LOW_PRICE": {
            "id": "DST_LOW_PRICE",
            "economy_state": {"supply_index": 1.0, "demand_index": 1.0, "price_index": 0.6},
        },
    }
    ship = {"faction": "merchant", "size_class": "medium"}
    rng = random.Random(8888)
    counts = {"DST_HIGH_PRICE": 0, "DST_LOW_PRICE": 0}

    for _ in range(600):
        dst = pick_destination(
            ship=ship,
            source_station_id="SRC",
            scenario=None,
            station_lookup=station_lookup,
            pirate_conf={},
            pirate_state=None,
            rng=rng,
            station_accepts_size_class=_accepts_all,
            economy_preference_weight=0.5,
        )
        if dst in counts:
            counts[dst] += 1

    assert counts["DST_HIGH_PRICE"] > counts["DST_LOW_PRICE"]
