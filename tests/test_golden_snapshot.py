"""Phase 5.2 — Determinism contract lock via golden-output snapshots.

These tests pin the *exact* departure sequence (event_uid, ship_id,
source/destination) produced by the canonical baseline seed.  Any change to
the simulation engine, departure builder, or seeding strategy that shifts the
output will fail here immediately and loudly.

Design notes
------------
* NOT marked ``@pytest.mark.slow`` — runs in the fast CI pass.
* Collects only 5 events; typical wall time < 2 s on a dev machine.
* The canonical sequence below was captured with::

      .venv\\Scripts\\python.exe scripts\\capture_golden_snapshot.py

  Re-run that script when you intentionally change deterministic behaviour and
  want to update the contract.
"""
from __future__ import annotations

import pytest

from shadow.fixtures import DeterministicRun


# ---------------------------------------------------------------------------
# Canonical sequence — baseline preset, seed=99, rate=300
# Generated: 2026-04-01 (capture_golden_snapshot.py)
# ---------------------------------------------------------------------------

GOLDEN_BASELINE: list[dict[str, str]] = [
    {
        "event_uid": "EVT-000000001-89e3995a",
        "ship_id": "SHIP-0005",
        "source_station_id": "STN-PLANET-EARTH-ORB1",
        "destination_station_id": "STN-PLANET-MARS-ORB1",
    },
    {
        "event_uid": "EVT-000000002-7d411fab",
        "ship_id": "SHIP-0006",
        "source_station_id": "STN-PLANET-EARTH-ORB3",
        "destination_station_id": "STN-PLANET-EARTH",
    },
    {
        "event_uid": "EVT-000000003-9cfbba43",
        "ship_id": "SHIP-0008",
        "source_station_id": "STN-PLANET-MARS",
        "destination_station_id": "STN-PLANET-EARTH-ORB1",
    },
    {
        "event_uid": "EVT-000000004-e6e96d45",
        "ship_id": "SHIP-0009",
        "source_station_id": "STN-PLANET-EARTH-ORB2",
        "destination_station_id": "STN-PLANET-MARS-ORB1",
    },
    {
        "event_uid": "EVT-000000005-635b4c41",
        "ship_id": "SHIP-0001",
        "source_station_id": "STN-PLANET-MARS",
        "destination_station_id": "STN-MOON-PHOBOS",
    },
]

_CHECKED_FIELDS = ("event_uid", "ship_id", "source_station_id", "destination_station_id")


class TestGoldenBaselineSequence:
    """The first 5 departures from the canonical baseline run must match exactly."""

    def _collect(self) -> list[dict]:
        with DeterministicRun(preset="baseline", seed=99, rate=300) as run:
            return run.collect_departures(n=len(GOLDEN_BASELINE))

    def test_event_uid_sequence_is_locked(self):
        """Top-level contract: UIDs must match the captured canonical sequence."""
        departures = self._collect()
        actual_uids = [d["event_uid"] for d in departures]
        golden_uids = [g["event_uid"] for g in GOLDEN_BASELINE]
        assert actual_uids == golden_uids, (
            "Departure UID sequence has drifted from the golden snapshot.\n"
            f"  expected: {golden_uids}\n"
            f"  actual:   {actual_uids}\n"
            "If this change is intentional, re-run scripts/capture_golden_snapshot.py "
            "and update GOLDEN_BASELINE in this file."
        )

    @pytest.mark.parametrize("idx", range(len(GOLDEN_BASELINE)))
    def test_departure_fields_match_golden(self, idx: int):
        """Each individual departure row must match all pinned fields."""
        departures = self._collect()
        actual = departures[idx]
        golden = GOLDEN_BASELINE[idx]
        mismatches = {
            field: {"expected": golden[field], "actual": actual.get(field)}
            for field in _CHECKED_FIELDS
            if actual.get(field) != golden[field]
        }
        assert not mismatches, (
            f"Departure[{idx}] fields differ from golden snapshot: {mismatches}"
        )
