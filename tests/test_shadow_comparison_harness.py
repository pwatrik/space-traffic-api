"""Shadow harness tests — Phase SH-1 and SH-2.

SH-1: Generator determinism — run the same seeded configuration twice and verify
      that both runs produce identical departure sequences.

SH-2: Cross-preset parity guards — ensure all three catalog presets produce
      internally consistent, non-trivially empty outputs.

These tests are marked ``@pytest.mark.slow`` so they can be excluded from fast
iterative runs with ``-m "not slow"``.  The full suite should always run them.
"""
from __future__ import annotations

import pytest

from shadow.assertions import (
    assert_departure_sequences_equal,
    assert_event_uids_equal,
    summarize_departures,
)
from shadow.fixtures import DeterministicRun


# ---------------------------------------------------------------------------
# SH-1: Determinism — same seed produces identical output
# ---------------------------------------------------------------------------

class TestGeneratorDeterminism:
    """Run twice with the same seed: both runs must produce identical sequences."""

    TARGET_EVENT_COUNT = 8

    def _run(self, preset: str, seed: int, rate: int = 300) -> list[dict]:
        with DeterministicRun(preset=preset, seed=seed, rate=rate) as run:
            return run.collect_departures(self.TARGET_EVENT_COUNT)

    def test_baseline_determinism(self):
        run_a = self._run("baseline", seed=99)
        run_b = self._run("baseline", seed=99)

        assert len(run_a) >= self.TARGET_EVENT_COUNT, "Run A failed to produce enough events"
        assert len(run_b) >= self.TARGET_EVENT_COUNT, "Run B failed to produce enough events"

        assert_event_uids_equal(run_a, run_b, label_a="run_a", label_b="run_b")
        assert_departure_sequences_equal(run_a, run_b, label_a="run_a", label_b="run_b")

    def test_different_seeds_produce_different_sequences(self):
        """Sanity check: different seeds must not produce identical uid sequences."""
        run_a = self._run("baseline", seed=99)
        run_b = self._run("baseline", seed=88)

        assert len(run_a) >= self.TARGET_EVENT_COUNT
        assert len(run_b) >= self.TARGET_EVENT_COUNT

        uids_a = [e.get("event_uid") for e in run_a]
        uids_b = [e.get("event_uid") for e in run_b]
        assert uids_a != uids_b, "Different seeds produced the same uid sequence — seeding is broken"

    @pytest.mark.slow
    def test_war_heavy_determinism(self):
        run_a = self._run("war_heavy", seed=77)
        run_b = self._run("war_heavy", seed=77)

        assert len(run_a) >= self.TARGET_EVENT_COUNT
        assert len(run_b) >= self.TARGET_EVENT_COUNT

        assert_event_uids_equal(run_a, run_b, label_a="run_a", label_b="run_b")
        assert_departure_sequences_equal(run_a, run_b, label_a="run_a", label_b="run_b")

    @pytest.mark.slow
    def test_pirate_enabled_determinism(self):
        run_a = self._run("pirate_enabled", seed=55)
        run_b = self._run("pirate_enabled", seed=55)

        assert len(run_a) >= self.TARGET_EVENT_COUNT
        assert len(run_b) >= self.TARGET_EVENT_COUNT

        assert_event_uids_equal(run_a, run_b, label_a="run_a", label_b="run_b")
        assert_departure_sequences_equal(run_a, run_b, label_a="run_a", label_b="run_b")


# ---------------------------------------------------------------------------
# SH-1: Config snapshot invariants
# ---------------------------------------------------------------------------

class TestConfigSnapshotInvariants:
    """Config endpoint must return consistent, expected shape across seeded runs."""

    def test_config_shape_is_stable(self):
        with DeterministicRun(preset="baseline") as run:
            config = run.get_config()

        assert "deterministic_mode" in config
        assert config["deterministic_mode"] is True
        assert "deterministic_seed" in config
        assert int(config["deterministic_seed"]) == 99
        assert "base_min_events_per_minute" in config
        assert "base_max_events_per_minute" in config

    def test_config_seed_is_reproducible_across_runs(self):
        with DeterministicRun(preset="baseline", seed=99) as run_a:
            config_a = run_a.get_config()

        with DeterministicRun(preset="baseline", seed=99) as run_b:
            config_b = run_b.get_config()

        assert config_a["deterministic_seed"] == config_b["deterministic_seed"]
        assert config_a["deterministic_mode"] == config_b["deterministic_mode"]
        assert config_a["base_min_events_per_minute"] == config_b["base_min_events_per_minute"]


# ---------------------------------------------------------------------------
# SH-2: Cross-preset parity guards
# ---------------------------------------------------------------------------

class TestPresetOutputGuards:
    """Each preset must produce non-trivially empty, structurally valid output."""

    @pytest.mark.parametrize("preset,seed", [
        ("baseline", 99),
        ("war_heavy", 77),
        ("pirate_enabled", 55),
    ])
    @pytest.mark.slow
    def test_preset_produces_departures(self, preset: str, seed: int):
        with DeterministicRun(preset=preset, seed=seed) as run:
            departures = run.collect_departures(n=5, timeout_seconds=10.0)

        assert len(departures) >= 5, (
            f"Preset '{preset}' produced fewer than 5 departures: {len(departures)}"
        )
        summary = summarize_departures(departures)
        assert summary["count"] >= 5

    def test_baseline_departure_fields(self):
        """All baseline departure events must carry the required API fields."""
        required = {
            "event_uid",
            "ship_id",
            "source_station_id",
            "destination_station_id",
            "departure_time",
            "est_arrival_time",
            "fault_flags",
            "malformed",
            "payload",
        }
        with DeterministicRun(preset="baseline") as run:
            departures = run.collect_departures(n=5)

        assert len(departures) >= 5
        for i, event in enumerate(departures):
            missing = required - set(event.keys())
            assert not missing, f"Departure[{i}] missing fields: {missing}"
            # The payload blob mirrors the core fields stored in payload_json
            assert isinstance(event.get("payload"), dict), f"Departure[{i}] payload is not a dict"
            inner = event["payload"]
            assert inner.get("event_uid") == event["event_uid"], (
                f"Departure[{i}] payload.event_uid mismatch"
            )
            assert inner.get("ship_id") == event["ship_id"], (
                f"Departure[{i}] payload.ship_id mismatch"
            )

    def test_baseline_departure_event_uid_sequence_is_monotonic(self):
        """event_uids must be non-empty strings and all distinct."""
        with DeterministicRun(preset="baseline") as run:
            departures = run.collect_departures(n=8)

        assert len(departures) >= 8
        uids = [e["event_uid"] for e in departures]
        assert all(isinstance(uid, str) and uid for uid in uids), "Empty event_uid found"
        assert len(set(uids)) == len(uids), f"Duplicate event_uids detected: {uids}"

    @pytest.mark.slow
    def test_war_heavy_produces_war_loss_control_events(self):
        with DeterministicRun(preset="war_heavy") as run:
            events = run.collect_control_events("war_losses", timeout_seconds=10.0)

        assert len(events) >= 1, "war_heavy preset failed to produce any war_losses control events"
        assert events[0]["payload"]["count"] >= 1
