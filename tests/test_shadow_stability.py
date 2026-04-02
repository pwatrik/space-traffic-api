"""Shadow harness tests — Phase SH-3: stability and diagnostics."""
from __future__ import annotations

import pytest

from shadow.assertions import assert_departure_sequences_equal
from shadow.fixtures import (
    DeterministicRun,
    SHADOW_DEFAULT_POLL_INTERVAL_SECONDS,
    SHADOW_DEFAULT_START_TIME,
    SHADOW_DEFAULT_TIMEOUT_SECONDS,
)


class TestHarnessDefaults:
    def test_default_start_time_is_stable_and_exposed(self):
        assert SHADOW_DEFAULT_START_TIME == "2150-01-01T00:00:00Z"
        with DeterministicRun(preset="baseline") as run:
            config = run.get_config()
        assert config.get("deterministic_start_time") == SHADOW_DEFAULT_START_TIME

    def test_timeout_diagnostic_includes_summary(self):
        with DeterministicRun(preset="baseline") as run:
            with pytest.raises(AssertionError) as exc:
                run.collect_departures(
                    n=10_000,
                    timeout_seconds=0.2,
                    poll_interval=0.05,
                    fail_on_timeout=True,
                )

        message = str(exc.value)
        assert "Timed out waiting for departures" in message
        assert "summary=" in message
        assert "sample_event_uids=" in message


class TestFlakeControl:
    @pytest.mark.slow
    def test_baseline_repeatability_across_three_runs(self):
        """Guard against intermittent drift by checking three consecutive runs."""
        runs: list[list[dict]] = []
        for _ in range(3):
            with DeterministicRun(preset="baseline", seed=99) as run:
                departures = run.collect_departures(
                    n=6,
                    timeout_seconds=SHADOW_DEFAULT_TIMEOUT_SECONDS,
                    poll_interval=SHADOW_DEFAULT_POLL_INTERVAL_SECONDS,
                )
                runs.append(departures)

        assert_departure_sequences_equal(runs[0], runs[1], label_a="run_1", label_b="run_2")
        assert_departure_sequences_equal(runs[1], runs[2], label_a="run_2", label_b="run_3")

    @pytest.mark.slow
    def test_war_control_event_timeout_diagnostic(self):
        with DeterministicRun(preset="war_heavy", seed=77) as run:
            with pytest.raises(AssertionError) as exc:
                run.collect_control_events(
                    action="definitely_missing_action",
                    timeout_seconds=0.3,
                    poll_interval=0.05,
                    fail_on_timeout=True,
                )

        message = str(exc.value)
        assert "Timed out waiting for control events" in message
        assert "observed_actions=" in message
