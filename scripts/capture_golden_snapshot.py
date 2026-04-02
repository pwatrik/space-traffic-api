"""One-shot helper: print canonical first-N departure rows for seeded presets.

Used to seed tests/test_golden_snapshot.py.

Run from the repo root:
    .venv\\Scripts\\python.exe scripts\\capture_golden_snapshot.py --preset baseline
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

repo = Path(__file__).parent.parent
sys.path.insert(0, str(repo / "tests"))
sys.path.insert(0, str(repo / "src"))

from shadow.fixtures import DeterministicRun

N = 5

DEFAULT_SEED_BY_PRESET = {
    "baseline": 99,
    "war_heavy": 77,
    "pirate_enabled": 55,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture deterministic golden departures")
    parser.add_argument("--preset", default="baseline", help="Preset name (baseline/war_heavy/pirate_enabled)")
    parser.add_argument("--seed", type=int, default=None, help="Optional deterministic seed override")
    parser.add_argument("--rate", type=int, default=300, help="Events per minute (default: 300)")
    parser.add_argument("--count", type=int, default=N, help="Number of departures to capture (default: 5)")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else DEFAULT_SEED_BY_PRESET.get(args.preset, 99)

    print(
        f"Collecting first {args.count} departures from preset={args.preset} "
        f"seed={seed} rate={args.rate} ...\n"
    )
    with DeterministicRun(preset=args.preset, seed=seed, rate=args.rate) as run:
        departures = run.collect_departures(n=args.count)

    snapshot = [
        {
            "event_uid": d["event_uid"],
            "ship_id": d["ship_id"],
            "source_station_id": d["source_station_id"],
            "destination_station_id": d["destination_station_id"],
        }
        for d in departures
    ]

    print("Golden snapshot (copy into test_golden_snapshot.py):\n")
    print(json.dumps(snapshot, indent=2))


if __name__ == "__main__":
    main()
