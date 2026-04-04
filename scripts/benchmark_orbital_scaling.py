"""Orbital scaling benchmark harness for Milestone 2.5.

Measures three cost buckets across a matrix of body counts, departure samples,
and routing fanout:
  1) Orbital-state update cost per simulated tick.
  2) Departure-time distance sampling cost using cached per-tick positions.
  3) Routing-adjacent candidate scan + storage write cost.

Usage (from repo root)::

    .venv\\Scripts\\python.exe scripts\\benchmark_orbital_scaling.py
    .venv\\Scripts\\python.exe scripts\\benchmark_orbital_scaling.py --repetitions 5 --warmup 1
    .venv\\Scripts\\python.exe scripts\\benchmark_orbital_scaling.py --output artifacts\\orbital_benchmark_results.json
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import statistics
import sys
import time
from pathlib import Path
from typing import Any

repo = Path(__file__).parent.parent
sys.path.insert(0, str(repo / "src"))

from space_traffic_api.simulation.engine.orbital_state import (  # noqa: E402
    OrbitalBodyState,
    advance_orbital_body_state,
    initialize_orbital_body_state,
)
from space_traffic_api.simulation.engine.routing import pick_destination  # noqa: E402


BODIES_MATRIX = (100, 500, 1000)
DEPARTURE_SAMPLES_MATRIX = (1000, 5000, 20000)
CANDIDATE_FANOUT_MATRIX = (10, 50, 100)
ROUTING_SCAN_CAP = 3000
STORAGE_WRITE_CAP = 3000


def _build_catalog(body_count: int) -> dict[str, Any]:
    planet_names = [
        "Mercury",
        "Venus",
        "Earth",
        "Mars",
        "Jupiter",
        "Saturn",
        "Uranus",
        "Neptune",
    ]
    planets = planet_names[: min(len(planet_names), max(1, body_count // 16))]
    asteroid_count = max(0, body_count - len(planets))
    asteroids = [f"A-{idx:04d}" for idx in range(asteroid_count)]

    distance_order: dict[str, int] = {
        "Mercury": 1,
        "Venus": 2,
        "Earth": 3,
        "Mars": 4,
        "Asteroid Belt": 5,
        "Jupiter": 6,
        "Saturn": 7,
        "Uranus": 8,
        "Neptune": 9,
    }

    return {
        "celestial": {
            "planets": planets,
            "asteroids": asteroids,
            "distance_order": distance_order,
        }
    }


def _compute_orbital_hops(
    state_by_body: dict[str, OrbitalBodyState],
    source_body: str,
    destination_body: str,
    base_hops: float,
    min_multiplier: float = 0.7,
    max_multiplier: float = 1.3,
) -> float:
    src_state = state_by_body[source_body]
    dst_state = state_by_body[destination_body]

    radial_distance = math.hypot(dst_state.x - src_state.x, dst_state.y - src_state.y)
    min_distance = abs(src_state.radius_scale - dst_state.radius_scale)
    max_distance = src_state.radius_scale + dst_state.radius_scale
    spread = max(0.001, max_distance - min_distance)
    normalized_distance = max(0.0, min(1.0, (radial_distance - min_distance) / spread))
    multiplier = min_multiplier + ((max_multiplier - min_multiplier) * normalized_distance)
    return base_hops * multiplier


def _prepare_sample_pairs(body_ids: list[str], sample_count: int, rng: random.Random) -> list[tuple[str, str, float]]:
    pairs: list[tuple[str, str, float]] = []
    for _ in range(sample_count):
        src = rng.choice(body_ids)
        dst = rng.choice(body_ids)
        while dst == src:
            dst = rng.choice(body_ids)
        base_hops = float(abs((hash(src) % 10) - (hash(dst) % 10)) + 1)
        pairs.append((src, dst, base_hops))
    return pairs


def _prepare_routing_data(fanout: int) -> tuple[dict[str, dict[str, Any]], dict[str, Any], str]:
    station_lookup: dict[str, dict[str, Any]] = {
        "SRC": {
            "economy_derived": {"fuel_pressure_score": 1.0, "local_value_score": 1.0},
            "economy_state": {"supply_index": 1.0, "demand_index": 1.0, "price_index": 1.0},
        }
    }
    for idx in range(fanout):
        station_lookup[f"DST-{idx:03d}"] = {
            "economy_derived": {
                "fuel_pressure_score": 0.8 + (idx % 5) * 0.15,
                "local_value_score": 0.7 + (idx % 9) * 0.12,
            },
            "economy_state": {
                "supply_index": 0.8 + (idx % 7) * 0.07,
                "demand_index": 0.9 + (idx % 6) * 0.08,
                "price_index": 0.95 + (idx % 4) * 0.05,
            },
        }
    ship = {"faction": "merchant", "size_class": "medium"}
    return station_lookup, ship, "SRC"


def _station_accepts_size_class(_station_id: str, _size_class: str) -> bool:
    return True


def _create_storage_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=MEMORY")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS departures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ship_id TEXT NOT NULL,
            source_station_id TEXT NOT NULL,
            destination_station_id TEXT NOT NULL,
            departure_time TEXT NOT NULL,
            estimated_arrival TEXT NOT NULL,
            event_uid TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _percentile_ms(samples: list[float], percentile: float) -> float:
    if not samples:
        return 0.0
    idx = min(len(samples) - 1, max(0, int(math.ceil((percentile / 100.0) * len(samples)) - 1)))
    return samples[idx]


def _run_combo(
    body_count: int,
    departure_samples: int,
    candidate_fanout: int,
    repetitions: int,
    warmup: int,
    seed: int,
) -> dict[str, Any]:
    rng = random.Random(seed + (body_count * 100_000) + (departure_samples * 10) + candidate_fanout)
    catalog = _build_catalog(body_count)
    orbital_state = initialize_orbital_body_state(catalog, deterministic_seed=seed)
    body_ids = sorted(orbital_state.keys())
    pairs = _prepare_sample_pairs(body_ids, departure_samples, rng)
    station_lookup, ship, source_station_id = _prepare_routing_data(candidate_fanout)
    routing_scans = min(departure_samples, ROUTING_SCAN_CAP)
    storage_writes = min(departure_samples, STORAGE_WRITE_CAP)
    routing_scale = departure_samples / float(routing_scans)
    storage_scale = departure_samples / float(storage_writes)

    update_samples_ms: list[float] = []
    distance_samples_ms: list[float] = []
    routing_samples_ms: list[float] = []
    storage_samples_ms: list[float] = []
    combined_samples_ms: list[float] = []

    total_iterations = warmup + repetitions
    for idx in range(total_iterations):
        started_combo = time.perf_counter()

        t0 = time.perf_counter()
        advance_orbital_body_state(orbital_state, elapsed_days=1.0 / 1440.0)
        update_ms = (time.perf_counter() - t0) * 1000.0

        t1 = time.perf_counter()
        hop_accumulator = 0.0
        for src_body, dst_body, base_hops in pairs:
            hop_accumulator += _compute_orbital_hops(orbital_state, src_body, dst_body, base_hops)
        distance_ms = (time.perf_counter() - t1) * 1000.0

        local_rng = random.Random(seed + idx)
        t2 = time.perf_counter()
        route_accumulator = 0
        for _ in range(routing_scans):
            destination = pick_destination(
                ship=ship,
                source_station_id=source_station_id,
                scenario=None,
                station_lookup=station_lookup,
                pirate_conf={},
                pirate_state=None,
                rng=local_rng,
                station_accepts_size_class=_station_accepts_size_class,
                economy_preference_weight=0.15,
            )
            route_accumulator += 1 if destination else 0
        routing_ms_measured = (time.perf_counter() - t2) * 1000.0
        routing_ms = routing_ms_measured * routing_scale

        conn = _create_storage_connection()
        t3 = time.perf_counter()
        payload = [
            (
                f"ship-{n}",
                source_station_id,
                f"DST-{n % candidate_fanout:03d}",
                "2150-01-01T00:00:00+00:00",
                "2150-01-01T08:00:00+00:00",
                f"evt-{n}",
            )
            for n in range(storage_writes)
        ]
        conn.executemany(
            """
            INSERT INTO departures (
                ship_id, source_station_id, destination_station_id,
                departure_time, estimated_arrival, event_uid
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
        conn.commit()
        storage_ms_measured = (time.perf_counter() - t3) * 1000.0
        storage_ms = storage_ms_measured * storage_scale
        conn.close()

        _ = hop_accumulator + route_accumulator
        combined_ms = (time.perf_counter() - started_combo) * 1000.0

        if idx >= warmup:
            update_samples_ms.append(update_ms)
            distance_samples_ms.append(distance_ms)
            routing_samples_ms.append(routing_ms)
            storage_samples_ms.append(storage_ms)
            combined_samples_ms.append(combined_ms)

    update_sorted = sorted(update_samples_ms)
    distance_sorted = sorted(distance_samples_ms)
    routing_sorted = sorted(routing_samples_ms)
    storage_sorted = sorted(storage_samples_ms)
    combined_sorted = sorted(combined_samples_ms)

    mean_update = statistics.mean(update_samples_ms)
    mean_distance = statistics.mean(distance_samples_ms)
    mean_routing = statistics.mean(routing_samples_ms)
    mean_storage = statistics.mean(storage_samples_ms)
    mean_combined = statistics.mean(combined_samples_ms)
    subtotal = max(0.000001, mean_update + mean_distance + mean_routing + mean_storage)

    return {
        "body_count": body_count,
        "departure_samples": departure_samples,
        "candidate_fanout": candidate_fanout,
        "measured_routing_scans": routing_scans,
        "measured_storage_writes": storage_writes,
        "repetitions": repetitions,
        "warmup": warmup,
        "metrics_ms": {
            "orbital_update": {
                "mean": round(mean_update, 3),
                "p95": round(_percentile_ms(update_sorted, 95), 3),
            },
            "distance_sampling": {
                "mean": round(mean_distance, 3),
                "p95": round(_percentile_ms(distance_sorted, 95), 3),
            },
            "routing_candidate_scan": {
                "mean": round(mean_routing, 3),
                "p95": round(_percentile_ms(routing_sorted, 95), 3),
            },
            "storage_insert": {
                "mean": round(mean_storage, 3),
                "p95": round(_percentile_ms(storage_sorted, 95), 3),
            },
            "combined_tick_adjacent": {
                "mean": round(mean_combined, 3),
                "p95": round(_percentile_ms(combined_sorted, 95), 3),
            },
        },
        "fraction_of_combined_mean": {
            "orbital_math": round((mean_update + mean_distance) / subtotal, 4),
            "routing": round(mean_routing / subtotal, 4),
            "storage": round(mean_storage / subtotal, 4),
        },
    }


def run_benchmark(
    body_counts: tuple[int, ...],
    departure_samples: tuple[int, ...],
    fanouts: tuple[int, ...],
    repetitions: int,
    warmup: int,
    seed: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    combos: list[dict[str, Any]] = []

    for body_count in body_counts:
        for sample_count in departure_samples:
            for fanout in fanouts:
                result = _run_combo(
                    body_count=body_count,
                    departure_samples=sample_count,
                    candidate_fanout=fanout,
                    repetitions=repetitions,
                    warmup=warmup,
                    seed=seed,
                )
                combos.append(result)
                orbital_share = result["fraction_of_combined_mean"]["orbital_math"]
                print(
                    f"combo bodies={body_count:4d} samples={sample_count:5d} fanout={fanout:3d} "
                    f"| orbital-share={orbital_share * 100:5.1f}% "
                    f"| combined-mean={result['metrics_ms']['combined_tick_adjacent']['mean']:8.3f} ms"
                )

    elapsed = time.perf_counter() - started
    orbital_shares = [entry["fraction_of_combined_mean"]["orbital_math"] for entry in combos]
    routing_shares = [entry["fraction_of_combined_mean"]["routing"] for entry in combos]
    storage_shares = [entry["fraction_of_combined_mean"]["storage"] for entry in combos]

    return {
        "benchmark": "orbital_scaling",
        "seed": seed,
        "matrix": {
            "body_counts": list(body_counts),
            "departure_samples": list(departure_samples),
            "candidate_fanout": list(fanouts),
        },
        "repetitions": repetitions,
        "warmup": warmup,
        "elapsed_seconds": round(elapsed, 3),
        "summary": {
            "orbital_math_share_mean": round(statistics.mean(orbital_shares), 4),
            "orbital_math_share_max": round(max(orbital_shares), 4),
            "routing_share_mean": round(statistics.mean(routing_shares), 4),
            "storage_share_mean": round(statistics.mean(storage_shares), 4),
        },
        "combos": combos,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Orbital scaling benchmark harness")
    parser.add_argument("--repetitions", type=int, default=7, help="Measured repetitions per matrix combo")
    parser.add_argument("--warmup", type=int, default=2, help="Warmup repetitions per matrix combo")
    parser.add_argument("--seed", type=int, default=424242, help="Deterministic benchmark seed")
    parser.add_argument(
        "--output",
        type=str,
        default="artifacts/orbital_benchmark_results.json",
        help="Output path for benchmark JSON artifact",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    repetitions = max(1, int(args.repetitions))
    warmup = max(0, int(args.warmup))

    print("Orbital scaling benchmark matrix")
    print("-" * 72)
    print(f"bodies={BODIES_MATRIX} departures={DEPARTURE_SAMPLES_MATRIX} fanout={CANDIDATE_FANOUT_MATRIX}")
    print(f"repetitions={repetitions} warmup={warmup} seed={args.seed}")
    print("-" * 72)

    result = run_benchmark(
        body_counts=BODIES_MATRIX,
        departure_samples=DEPARTURE_SAMPLES_MATRIX,
        fanouts=CANDIDATE_FANOUT_MATRIX,
        repetitions=repetitions,
        warmup=warmup,
        seed=int(args.seed),
    )

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = repo / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("\nSummary")
    print("-" * 72)
    print(f"elapsed: {result['elapsed_seconds']} s")
    print(f"orbital mean share: {result['summary']['orbital_math_share_mean'] * 100:.1f}%")
    print(f"orbital max share : {result['summary']['orbital_math_share_max'] * 100:.1f}%")
    print(f"routing mean share: {result['summary']['routing_share_mean'] * 100:.1f}%")
    print(f"storage mean share: {result['summary']['storage_share_mean'] * 100:.1f}%")
    print(f"wrote artifact: {out_path}")


if __name__ == "__main__":
    main()
