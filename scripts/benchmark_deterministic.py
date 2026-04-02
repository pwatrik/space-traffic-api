"""Phase 5.3 — Deterministic performance baseline.

Runs the simulation under the canonical baseline preset and measures:
  - Time to first N departures (wall clock)
  - Departures / second throughput
  - Tick latency percentiles (p50, p95, p99, max) sampled via /healthz

Usage (from repo root)::

    .venv\\Scripts\\python.exe scripts\\benchmark_deterministic.py [--events N] [--rate R] [--output PATH]

Output: printed table + benchmark JSON written to PATH (default: repo_root/benchmark_results.json;
relative PATHs are resolved under the repo root).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

repo = Path(__file__).parent.parent
sys.path.insert(0, str(repo / "tests"))
sys.path.insert(0, str(repo / "src"))

from shadow.fixtures import DeterministicRun  # noqa: E402


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_benchmark(n_events: int = 10, rate: int = 300) -> dict:
    print(f"\nBenchmark: baseline preset | seed=99 | rate={rate} ev/min | target={n_events} departures")
    print("-" * 70)

    with DeterministicRun(preset="baseline", seed=99, rate=rate) as run:
        t_start = time.perf_counter()

        # Collect departures and interleave latency sampling
        deadline = time.monotonic() + 60.0
        departures: list[dict] = []
        latency_samples: list[float] = []
        poll_interval = 0.05

        while time.monotonic() < deadline and len(departures) < n_events:
            resp = run.client.get(
                "/departures",
                headers=run.headers,
                query_string={"limit": min(1000, n_events)},
            )
            if resp.status_code == 200:
                departures = resp.get_json().get("departures", [])

            # Sample tick latency on every poll until 200 samples are collected
            if len(latency_samples) < 200:
                healthz = run.client.get("/healthz", headers=run.headers)
                if healthz.status_code == 200:
                    rm = (healthz.get_json() or {}).get("runtime_metrics", {})
                    val = rm.get("tick_latency_ms_last")
                    if val and float(val) > 0:
                        latency_samples.append(float(val))

            if len(departures) >= n_events:
                break
            time.sleep(poll_interval)

        t_end = time.perf_counter()
        elapsed_s = t_end - t_start
        actual_events = len(departures)

        # Final healthz snapshot
        final_resp = run.client.get("/healthz", headers=run.headers)
        final_rm = {}
        if final_resp.status_code == 200:
            final_rm = (final_resp.get_json() or {}).get("runtime_metrics", {})

    # ---------------------------------------------------------------------------
    # Compute stats
    # ---------------------------------------------------------------------------
    departures_per_sec = actual_events / elapsed_s if elapsed_s > 0 else 0.0

    latency_stats: dict[str, float] = {}
    if latency_samples:
        sorted_lat = sorted(latency_samples)
        n = len(sorted_lat)
        latency_stats = {
            "p50_ms": round(sorted_lat[int(n * 0.50)], 3),
            "p95_ms": round(sorted_lat[int(n * 0.95)], 3),
            "p99_ms": round(sorted_lat[min(int(n * 0.99), n - 1)], 3),
            "max_ms": round(sorted_lat[-1], 3),
            "mean_ms": round(statistics.mean(sorted_lat), 3),
            "samples": n,
        }

    results = {
        "preset": "baseline",
        "seed": 99,
        "rate_events_per_min": rate,
        "target_events": n_events,
        "actual_events": actual_events,
        "elapsed_seconds": round(elapsed_s, 3),
        "departures_per_second": round(departures_per_sec, 3),
        "tick_latency": latency_stats,
        "final_engine_metrics": {
            "tick_count": final_rm.get("tick_count"),
            "tick_latency_ms_avg": final_rm.get("tick_latency_ms_avg"),
            "tick_latency_ms_max": final_rm.get("tick_latency_ms_max"),
            "departures_emitted_total": final_rm.get("departures_emitted_total"),
        },
    }

    # ---------------------------------------------------------------------------
    # Print table
    # ---------------------------------------------------------------------------
    print(f"  Departures collected : {actual_events} / {n_events}")
    print(f"  Elapsed              : {elapsed_s:.3f} s")
    print(f"  Throughput           : {departures_per_sec:.2f} departures/sec")
    if latency_stats:
        print(f"  Tick latency p50     : {latency_stats['p50_ms']} ms")
        print(f"  Tick latency p95     : {latency_stats['p95_ms']} ms")
        print(f"  Tick latency p99     : {latency_stats['p99_ms']} ms")
        print(f"  Tick latency max     : {latency_stats['max_ms']} ms")
        print(f"  Tick latency mean    : {latency_stats['mean_ms']} ms  (n={latency_stats['samples']})")
    if final_rm.get("tick_count"):
        print(f"  Engine tick count    : {final_rm['tick_count']}")
        print(f"  Engine avg latency   : {final_rm.get('tick_latency_ms_avg')} ms")
        print(f"  Engine max latency   : {final_rm.get('tick_latency_ms_max')} ms")
    print()

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic simulation benchmark")
    parser.add_argument("--events", type=int, default=10, help="Target departure count (default: 10)")
    parser.add_argument("--rate", type=int, default=300, help="Events per minute (default: 300)")
    parser.add_argument(
        "--output",
        default="benchmark_results.json",
        help="Path for benchmark JSON output (default: benchmark_results.json)",
    )
    args = parser.parse_args()

    results = run_benchmark(n_events=args.events, rate=args.rate)

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = repo / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Results written to {out_path}")


if __name__ == "__main__":
    main()
