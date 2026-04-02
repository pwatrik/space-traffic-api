"""Shadow harness tests — Phase SH-2: Parity validation.

Structural invariants and field-level coherence checks that hold regardless of
seed:

  * payload blob mirrors every top-level departure field it claims to contain
  * source_station_id != destination_station_id for every event
  * est_arrival_time > departure_time for every event
  * departure_time >= the deterministic simulation start time
  * ship roster is reproducible from the catalog seed, independent of the
    departure-generator seed
  * every departure's ship_id appears in the initial fleet roster
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from shadow.assertions import assert_departure_sequences_equal
from shadow.fixtures import DeterministicRun


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SIM_START = datetime(2150, 1, 1, tzinfo=timezone.utc)

# Maps payload blob keys -> expected matching top-level departure keys
_PAYLOAD_MIRROR_FIELDS: dict[str, str] = {
    "event_uid": "event_uid",
    "departure_time": "departure_time",
    "ship_id": "ship_id",
    "source_station_id": "source_station_id",
    "destination_station_id": "destination_station_id",
    "est_arrival_time": "est_arrival_time",
    "scenario": "scenario",
}


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# SH-2-A: Payload coherence
# ---------------------------------------------------------------------------


class TestPayloadCoherence:
    """payload blob must mirror every top-level field it claims to contain."""

    def test_baseline_payload_mirrors_top_level(self):
        with DeterministicRun(preset="baseline") as run:
            departures = run.collect_departures(n=8)

        assert len(departures) >= 8
        for i, event in enumerate(departures):
            payload = event.get("payload")
            assert isinstance(payload, dict), f"Departure[{i}]: payload is not a dict"
            for inner_key, outer_key in _PAYLOAD_MIRROR_FIELDS.items():
                assert inner_key in payload, (
                    f"Departure[{i}]: payload missing key '{inner_key}'"
                )
                assert payload[inner_key] == event[outer_key], (
                    f"Departure[{i}]: payload['{inner_key}']={payload[inner_key]!r} "
                    f"!= event['{outer_key}']={event[outer_key]!r}"
                )

    @pytest.mark.slow
    @pytest.mark.parametrize("preset,seed", [
        ("war_heavy", 77),
        ("pirate_enabled", 55),
    ])
    def test_payload_coherence_non_baseline_presets(self, preset: str, seed: int):
        with DeterministicRun(preset=preset, seed=seed) as run:
            departures = run.collect_departures(n=5)

        assert len(departures) >= 5
        for i, event in enumerate(departures):
            payload = event.get("payload")
            assert isinstance(payload, dict), (
                f"[{preset}] Departure[{i}]: payload is not a dict"
            )
            for inner_key, outer_key in _PAYLOAD_MIRROR_FIELDS.items():
                assert inner_key in payload, (
                    f"[{preset}] Departure[{i}]: payload missing key '{inner_key}'"
                )
                assert payload[inner_key] == event[outer_key], (
                    f"[{preset}] Departure[{i}]: payload['{inner_key}'] != "
                    f"event['{outer_key}']"
                )


# ---------------------------------------------------------------------------
# SH-2-B: Routing and timestamp invariants
# ---------------------------------------------------------------------------


class TestEventStructuralInvariants:
    """Hard invariants that must hold for every departure, regardless of seed."""

    def test_source_differs_from_destination(self):
        with DeterministicRun(preset="baseline") as run:
            departures = run.collect_departures(n=8)

        assert len(departures) >= 8
        for i, event in enumerate(departures):
            assert event["source_station_id"] != event["destination_station_id"], (
                f"Departure[{i}]: source == destination == {event['source_station_id']!r}"
            )

    def test_arrival_after_departure(self):
        with DeterministicRun(preset="baseline") as run:
            departures = run.collect_departures(n=8)

        assert len(departures) >= 8
        for i, event in enumerate(departures):
            dep = _parse_iso(event["departure_time"])
            arr = _parse_iso(event["est_arrival_time"])
            assert arr > dep, (
                f"Departure[{i}]: est_arrival_time {arr.isoformat()} is not after "
                f"departure_time {dep.isoformat()}"
            )

    def test_departure_times_at_or_after_sim_start(self):
        with DeterministicRun(preset="baseline") as run:
            departures = run.collect_departures(n=8)

        assert len(departures) >= 8
        for i, event in enumerate(departures):
            dep = _parse_iso(event["departure_time"])
            assert dep >= _SIM_START, (
                f"Departure[{i}]: departure_time {dep.isoformat()} precedes sim start "
                f"{_SIM_START.isoformat()}"
            )

    @pytest.mark.slow
    @pytest.mark.parametrize("preset,seed", [
        ("war_heavy", 77),
        ("pirate_enabled", 55),
    ])
    def test_routing_and_timing_non_baseline_presets(self, preset: str, seed: int):
        """source != destination and arrival > departure hold across non-baseline presets."""
        with DeterministicRun(preset=preset, seed=seed) as run:
            departures = run.collect_departures(n=5)

        assert len(departures) >= 5
        for i, event in enumerate(departures):
            assert event["source_station_id"] != event["destination_station_id"], (
                f"[{preset}] Departure[{i}]: source == destination"
            )
            dep = _parse_iso(event["departure_time"])
            arr = _parse_iso(event["est_arrival_time"])
            assert arr > dep, (
                f"[{preset}] Departure[{i}]: est_arrival_time not after departure_time"
            )


# ---------------------------------------------------------------------------
# SH-2-C: Ship roster determinism
# ---------------------------------------------------------------------------


class TestShipRosterDeterminism:
    """Catalog seed controls the fleet; departure-generator seed must not affect it."""

    def test_ship_roster_independent_of_departure_seed(self):
        """Same catalog -> same ship IDs even when departure seeds differ."""
        with DeterministicRun(preset="baseline", seed=99) as run_a:
            state_a = run_a.get_ships_state()

        with DeterministicRun(preset="baseline", seed=88) as run_b:
            state_b = run_b.get_ships_state()

        ids_a = sorted(s["ship_id"] for s in state_a["ships"])
        ids_b = sorted(s["ship_id"] for s in state_b["ships"])
        assert ids_a, "Fleet A is empty — catalog likely failed to seed ships"
        assert ids_a == ids_b, (
            "Fleet IDs differ when only departure seed changes — "
            f"symmetric difference: {set(ids_a) ^ set(ids_b)}"
        )

    def test_departure_ship_ids_in_initial_fleet(self):
        """Every departure's ship_id must be in the initial fleet roster."""
        with DeterministicRun(preset="baseline") as run:
            state = run.get_ships_state()
            departures = run.collect_departures(n=8)

        fleet_ids = {s["ship_id"] for s in state["ships"]}
        assert fleet_ids, "Initial fleet is empty"

        for i, event in enumerate(departures):
            assert event["ship_id"] in fleet_ids, (
                f"Departure[{i}]: ship_id={event['ship_id']!r} not in initial fleet. "
                f"Known IDs: {sorted(fleet_ids)}"
            )
