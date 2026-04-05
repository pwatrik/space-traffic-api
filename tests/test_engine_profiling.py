"""Performance profiling tests for engine hot paths (routing, ship selection).

This module profiles the main computational bottlenecks in the simulation engine:
- pick_destination() with economy weighting
- select_ship() with faction-based and pirate weighting
- Generator tick under load

Run with: pytest tests/test_engine_profiling.py -xvs --tb=short
"""

import random
import time
from tempfile import TemporaryDirectory

import pytest

from space_traffic_api.app import create_app
from space_traffic_api.simulation.engine.routing import pick_destination
from space_traffic_api.simulation.engine.ship_selector import select_ship


@pytest.mark.slow
def test_pick_destination_throughput():
    """Profile: how many destination picks per second for merchant ships?"""
    # Setup a minimal station lookup with 50 stations
    station_lookup = {
        f"STN-{i}": {
            "id": f"STN-{i}",
            "size_class": "medium" if i % 3 != 0 else "large",
            "economy_derived": {
                "local_value_score": random.uniform(0.5, 2.0),
                "fuel_pressure_score": random.uniform(0.7, 1.3),
            },
            "economy_state": {
                "supply_index": random.uniform(0.8, 1.2),
                "demand_index": random.uniform(0.8, 1.2),
                "price_index": random.uniform(0.9, 1.1),
            },
        }
        for i in range(50)
    }

    ship = {
        "id": "SHIP-1",
        "faction": "merchant",
        "size_class": "medium",
    }

    rng = random.Random(42)
    iterations = 1000

    start = time.perf_counter()
    for i in range(iterations):
        source = f"STN-{i % 50}"
        pick_destination(
            ship=ship,
            source_station_id=source,
            scenario=None,
            station_lookup=station_lookup,
            pirate_conf={},
            pirate_state=None,
            rng=rng,
            station_accepts_size_class=lambda sid, sc: True,
            economy_preference_weight=0.15,
        )
    elapsed = time.perf_counter() - start

    throughput = iterations / elapsed
    print(f"\npick_destination throughput: {throughput:.1f} calls/sec")
    assert throughput > 100, f"Expected > 100 calls/sec, got {throughput:.1f}"


@pytest.mark.slow
def test_select_ship_throughput():
    """Profile: how many ship selections per second?"""
    # Setup 500 ships across 5 factions
    candidates = [
        {
            "id": f"SHIP-{i}",
            "faction": ["merchant", "bounty_hunter", "pirate"][i % 3],
            "size_class": ["small", "medium", "large"][i % 3],
        }
        for i in range(500)
    ]

    runtime_snap = {
        "pirate_event": {
            "active": True,
            "affected_station_ids": ["STN-1", "STN-2"],
        },
    }
    pirate_conf = {
        "bounty_hunter_idle_departure_multiplier": 0.2,
        "bounty_hunter_active_departure_multiplier": 6.0,
    }

    rng = random.Random(42)
    iterations = 1000

    start = time.perf_counter()
    for _ in range(iterations):
        select_ship(
            candidates=candidates,
            fallback_candidates=candidates,
            scenario=None,
            runtime_snap=runtime_snap,
            pirate_conf=pirate_conf,
            rng=rng,
        )
    elapsed = time.perf_counter() - start

    throughput = iterations / elapsed
    print(f"\nselect_ship throughput: {throughput:.1f} calls/sec")
    assert throughput > 1000, f"Expected > 1000 calls/sec, got {throughput:.1f}"


@pytest.mark.slow
def test_generator_tick_throughput_small_scenario(monkeypatch):
    """Profile: generator loops under realistic load (small scenario).

    This is a guardrail test, not a microbenchmark. It validates that throughput
    stays healthy in CI while startup bursts are being processed.
    """
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", f"{tmp}/test.db")
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "99")
        # Higher rate to stress the selector/router
        monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "300")
        monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "300")

        app = create_app()
        simulation = app.config["space_simulation"]
        store = app.config["space_store"]

        try:
            # Run for a fixed wall-clock duration and measure throughput
            start = time.perf_counter()
            measured_time = 5.0  # 5 seconds
            
            while time.perf_counter() - start < measured_time:
                time.sleep(0.1)

            initial_metrics = simulation.snapshot()["runtime_metrics"]
            departed_count = initial_metrics.get("departures_emitted_total", 0)
            tick_count = initial_metrics.get("tick_count", 0)
            elapsed = time.perf_counter() - start

            if tick_count > 0:
                avg_tick_ms = (elapsed * 1000.0) / tick_count
                print(f"\nGenerator throughput: {tick_count} ticks in {elapsed:.2f}s")
                print(f"Avg tick latency: {avg_tick_ms:.2f} ms")
                print(f"Accumulated departures: {departed_count}")
                assert tick_count >= 3, f"Expected at least 3 ticks in window, got {tick_count}"
                assert departed_count >= 100, f"Expected at least 100 departures, got {departed_count}"
                assert avg_tick_ms < 1500, f"Expected avg tick < 1500ms, got {avg_tick_ms:.2f}ms"
        finally:
            simulation.stop(timeout=3.0)
            store.close()


@pytest.mark.slow
def test_generator_tick_latency_p95(monkeypatch):
    """Profile: p95 tick latency to catch outliers in scheduling."""
    with TemporaryDirectory() as tmp:
        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", f"{tmp}/test.db")
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "99")
        monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "100")
        monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "200")

        app = create_app()
        simulation = app.config["space_simulation"]
        store = app.config["space_store"]

        try:
            time.sleep(3.0)  # Let it run for 3 seconds
            
            metrics = simulation.snapshot()["runtime_metrics"]
            max_latency = metrics.get("tick_latency_ms_max", 0)
            avg_latency = metrics.get("tick_latency_ms_avg", 0)
            
            print(f"\nTick latency stats:")
            print(f"  Average: {avg_latency:.2f}ms")
            print(f"  Peak: {max_latency:.2f}ms")
            
            # Guardrail: under heavy startup/lifecycle work, peak latency should stay bounded.
            assert avg_latency < 1200, f"Average tick latency too high: {avg_latency:.2f}ms"
            assert max_latency < 1500, f"Peak tick latency too high: {max_latency:.2f}ms"
        finally:
            simulation.stop(timeout=3.0)
            store.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
