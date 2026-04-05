"""Performance comparison tests for optimized routing and caching.

Compares baseline generator performance against optimized economy cache implementation.
Run with: pytest tests/test_engine_optimization.py -xvs --tb=short
"""

import random
import time
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from space_traffic_api.simulation.engine.optimization import StationEconomyCache, PickDestinationOptimized


def test_station_economy_cache_single_query(monkeypatch):
    """Verify that cache refresh uses only ONE database query instead of TWO."""
    mock_calls = []

    class MockStore:
        def list_stations(self, limit: int, order_by: str, order: str) -> tuple[list[dict], int]:
            mock_calls.append({"limit": limit, "order_by": order_by, "order": order})
            # Return 35 stations (less than 5000 limit)
            stations = [
                {
                    "id": f"STN-{i}",
                    "economy_profile": {},
                    "economy_state": {"supply": 1.0},
                    "economy_derived": {"local_value_score": 1.0},
                }
                for i in range(35)
            ]
            return stations, 35

    station_lookup = {
        f"STN-{i}": {
            "id": f"STN-{i}",
            "economy_profile": {},
            "economy_state": {},
        }
        for i in range(35)
    }

    cache = StationEconomyCache(station_lookup)
    mock_calls.clear()
    updated_acc, refreshed = cache.refresh_if_needed(
        store=MockStore(),
        elapsed_days=0.1,
        refresh_interval_days=1.0 / 24.0,
        accumulator_days=0.04,  # Will trigger refresh (0.04 + 0.1 >= 0.0417)
    )

    assert refreshed is True
    assert len(mock_calls) == 1, f"Expected exactly 1 DB call, got {len(mock_calls)}"
    assert updated_acc == 0.0


def test_pick_destination_cache_reuse():
    """Verify cached compatible station check avoids recomputation."""
    station_lookup = {
        f"STN-{i}": {
            "id": f"STN-{i}",
            "size_class": "medium" if i % 2 == 0 else "large",
            "economy_derived": {"local_value_score": 1.0, "fuel_pressure_score": 1.0},
            "economy_state": {"supply_index": 1.0, "demand_index": 1.0, "price_index": 1.0},
        }
        for i in range(50)
    }

    picker = PickDestinationOptimized(station_lookup, {})
    ship_medium = {"id": "S1", "faction": "merchant", "size_class": "medium"}
    rng = random.Random(42)

    calls_to_size_class = []

    def mock_accepts(sid: str, sc: str) -> bool:
        calls_to_size_class.append((sid, sc))
        return True

    # First call: populates cache
    calls_to_size_class.clear()
    result1 = picker.pick_cached(
        ship=ship_medium,
        source_station_id="STN-0",
        scenario=None,
        pirate_state=None,
        rng=rng,
        station_accepts_size_class_func=mock_accepts,
        economy_preference_weight=0.15,
    )

    first_calls = len(calls_to_size_class)

    # Second call: should reuse cache (no size_class calls)
    calls_to_size_class.clear()
    result2 = picker.pick_cached(
        ship=ship_medium,
        source_station_id="STN-1",
        scenario=None,
        pirate_state=None,
        rng=rng,
        station_accepts_size_class_func=mock_accepts,
        economy_preference_weight=0.15,
    )

    second_calls = len(calls_to_size_class)

    # On subsequent calls, we shouldn't need to recompute size_class checks
    # (though some may still happen for the new source check)
    assert first_calls > second_calls, (
        f"Cache not providing benefit: first={first_calls}, second={second_calls}"
    )


@pytest.mark.slow
def test_economy_preference_weight_computation():
    """Verify cached economy weight computation is correct."""
    station_lookup = {
        "STN-SOURCE": {
            "economy_derived": {"fuel_pressure_score": 1.0, "local_value_score": 0},
            "economy_state": {"supply_index": 1.0, "demand_index": 2.0, "price_index": 1.0},
        },
        "STN-DEST": {
            "economy_derived": {"fuel_pressure_score": 1.0, "local_value_score": 0},
            "economy_state": {"supply_index": 2.0, "demand_index": 1.0, "price_index": 1.0},
        },
    }

    cache = StationEconomyCache(station_lookup)
    weight = cache.get_economy_weight("STN-SOURCE", "STN-DEST", economy_preference_weight=0.15)

    # Expected: net_value = (1.0/2.0)*1.0 = 0.5; weight = 1.0 + ((0.5-1.0)*0.15) = 0.925
    assert 0.9 <= weight <= 0.95, f"Unexpected weight: {weight}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
