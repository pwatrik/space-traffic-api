"""Phase 6.3 — Determinism contract lock via golden-output snapshots.

These tests pin the *exact* departure sequence (event_uid, ship_id,
source/destination) produced by canonical seeded presets. Any change to
the simulation engine, departure builder, or seeding strategy that shifts the
output will fail here immediately and loudly.

Design notes
------------
* NOT marked ``@pytest.mark.slow`` — runs in the fast CI pass.
* Collects only 5 events per preset.
* The canonical sequence below was captured with::

      .venv\\Scripts\\python.exe scripts\\capture_golden_snapshot.py

  Re-run that script when you intentionally change deterministic behaviour and
  want to update the contract.
"""
from __future__ import annotations

import pytest

from shadow.fixtures import DeterministicRun


# ---------------------------------------------------------------------------
# Canonical sequences — presets from tests/shadow/fixtures.py
# Generated: 2026-04-03 (capture script — chunk 10: departure price ease)
# ---------------------------------------------------------------------------

GOLDEN_BY_PRESET: dict[str, list[dict[str, str]]] = {
    "baseline": [
        {
            "event_uid": "EVT-000000001-16ff82e3",
            "ship_id": "SHIP-0005",
            "source_station_id": "STN-PLANET-MARS",
            "destination_station_id": "STN-PLANET-EARTH-ORB3",
        },
        {
            "event_uid": "EVT-000000002-e6e96d45",
            "ship_id": "SHIP-0006",
            "source_station_id": "STN-PLANET-MARS-ORB1",
            "destination_station_id": "STN-PLANET-EARTH-ORB3",
        },
        {
            "event_uid": "EVT-000000003-2dd301c8",
            "ship_id": "SHIP-0008",
            "source_station_id": "STN-PLANET-EARTH-ORB2",
            "destination_station_id": "STN-PLANET-EARTH-ORB1",
        },
        {
            "event_uid": "EVT-000000004-7812f170",
            "ship_id": "SHIP-0009",
            "source_station_id": "STN-PLANET-MARS-ORB1",
            "destination_station_id": "STN-PLANET-EARTH-ORB3",
        },
        {
            "event_uid": "EVT-000000005-eee1f220",
            "ship_id": "SHIP-0001",
            "source_station_id": "STN-PLANET-MARS-ORB1",
            "destination_station_id": "STN-PLANET-EARTH-ORB2",
        },
    ],
    "war_heavy": [
        {
            "event_uid": "EVT-000000001-f5097b4f",
            "ship_id": "SHIP-0011",
            "source_station_id": "STN-PLANET-MARS-ORB1",
            "destination_station_id": "STN-MOON-PHOBOS",
        },
        {
            "event_uid": "EVT-000000002-54dc77a7",
            "ship_id": "SHIP-0001",
            "source_station_id": "STN-PLANET-MARS-ORB1",
            "destination_station_id": "STN-MOON-PHOBOS",
        },
        {
            "event_uid": "EVT-000000003-311275fc",
            "ship_id": "SHIP-0003",
            "source_station_id": "STN-MOON-PHOBOS",
            "destination_station_id": "STN-PLANET-EARTH-ORB3",
        },
        {
            "event_uid": "EVT-000000004-89eb3061",
            "ship_id": "SHIP-0014",
            "source_station_id": "STN-PLANET-EARTH-ORB1",
            "destination_station_id": "STN-MOON-PHOBOS",
        },
        {
            "event_uid": "EVT-000000005-d988d7c6",
            "ship_id": "SHIP-0010",
            "source_station_id": "STN-PLANET-EARTH-ORB1",
            "destination_station_id": "STN-PLANET-MARS-ORB1",
        },
    ],
    "pirate_enabled": [
        {
            "event_uid": "EVT-000000001-fd50b64c",
            "ship_id": "SHIP-0007",
            "source_station_id": "STN-PLANET-EARTH-ORB3",
            "destination_station_id": "STN-PLANET-EARTH-ORB1",
        },
        {
            "event_uid": "EVT-000000002-b4aca4b3",
            "ship_id": "SHIP-0006",
            "source_station_id": "STN-PLANET-MARS-ORB1",
            "destination_station_id": "STN-PLANET-EARTH",
        },
        {
            "event_uid": "EVT-000000003-a4f05582",
            "ship_id": "SHIP-0010",
            "source_station_id": "STN-PLANET-EARTH-ORB1",
            "destination_station_id": "STN-PLANET-EARTH-ORB3",
        },
        {
            "event_uid": "EVT-000000004-d4571b4c",
            "ship_id": "SHIP-0008",
            "source_station_id": "STN-PLANET-EARTH-ORB2",
            "destination_station_id": "STN-PLANET-EARTH-ORB3",
        },
        {
            "event_uid": "EVT-000000005-3d8fbae5",
            "ship_id": "SHIP-0014",
            "source_station_id": "STN-PLANET-EARTH-ORB1",
            "destination_station_id": "STN-PLANET-EARTH-ORB2",
        },
    ],
}

SEED_BY_PRESET = {
    "baseline": 99,
    "war_heavy": 77,
    "pirate_enabled": 55,
}

_CHECKED_FIELDS = ("event_uid", "ship_id", "source_station_id", "destination_station_id")


class TestGoldenSequenceByPreset:
    """The first 5 departures from each canonical preset must match exactly."""

    def _collect(self, preset: str) -> list[dict]:
        expected = GOLDEN_BY_PRESET[preset]
        with DeterministicRun(preset=preset, seed=SEED_BY_PRESET[preset], rate=300) as run:
            return run.collect_departures(n=len(expected))

    @pytest.mark.parametrize("preset", ["baseline", "war_heavy", "pirate_enabled"])
    def test_event_uid_sequence_is_locked(self, preset: str):
        """Top-level contract: UIDs must match the captured canonical sequence."""
        departures = self._collect(preset)
        actual_uids = [d["event_uid"] for d in departures]
        golden_uids = [g["event_uid"] for g in GOLDEN_BY_PRESET[preset]]
        assert actual_uids == golden_uids, (
            f"Departure UID sequence drifted for preset={preset!r}.\n"
            f"  expected: {golden_uids}\n"
            f"  actual:   {actual_uids}\n"
            "If this change is intentional, re-run scripts/capture_golden_snapshot.py "
            "and update GOLDEN_BY_PRESET in this file."
        )

    @pytest.mark.parametrize("preset", ["baseline", "war_heavy", "pirate_enabled"])
    @pytest.mark.parametrize("idx", range(5))
    def test_departure_fields_match_golden(self, preset: str, idx: int):
        """Each individual departure row must match all pinned fields."""
        departures = self._collect(preset)
        actual = departures[idx]
        golden = GOLDEN_BY_PRESET[preset][idx]
        mismatches = {
            field: {"expected": golden[field], "actual": actual.get(field)}
            for field in _CHECKED_FIELDS
            if actual.get(field) != golden[field]
        }
        assert not mismatches, (
            f"Departure[{idx}] differs for preset={preset!r}: {mismatches}"
        )
