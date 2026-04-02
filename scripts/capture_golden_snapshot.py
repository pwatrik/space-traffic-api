"""One-shot helper: print the canonical first-N departure UIDs and core fields
for the baseline deterministic run.  Used to seed tests/test_golden_snapshot.py.

Run from the repo root:
    .venv\\Scripts\\python.exe scripts\\capture_golden_snapshot.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

repo = Path(__file__).parent.parent
sys.path.insert(0, str(repo / "tests"))
sys.path.insert(0, str(repo / "src"))

from shadow.fixtures import DeterministicRun

N = 5


def main() -> None:
    print(f"Collecting first {N} departures from baseline seed=99 rate=300 ...\n")
    with DeterministicRun(preset="baseline", seed=99, rate=300) as run:
        departures = run.collect_departures(n=N)

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
