"""Phase 5.4 release smoke gate.

This script is intended as a pre-release quality gate. It runs a compact set of
checks that should catch deterministic regressions, flaky harness behavior, and
runtime-health issues quickly.

Checks:
1) Fast suite           : pytest -m "not slow" -q
2) Golden contract      : tests/test_golden_snapshot.py
3) Shadow core          : focused stability checks
4) Runtime metrics      : tick count grows and control-event backlog is bounded

Usage:
    .venv\\Scripts\\python.exe scripts\\release_smoke_gate.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

repo = Path(__file__).parent.parent
sys.path.insert(0, str(repo / "tests"))
sys.path.insert(0, str(repo / "src"))

from shadow.fixtures import DeterministicRun  # noqa: E402


def _run_pytest(label: str, args: list[str]) -> None:
    cmd = [sys.executable, "-m", "pytest", *args]
    print(f"\n[gate] {label}")
    print(f"[gate] command: {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=repo, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def _runtime_metrics_sanity() -> dict[str, object]:
    print("\n[gate] runtime metrics sanity")
    with DeterministicRun(preset="baseline", seed=99, rate=300) as run:
        # Ensure the engine is active and has produced some events.
        departures = run.collect_departures(n=5, timeout_seconds=12.0)
        assert len(departures) >= 5, "Expected at least 5 departures during smoke run"

        tick_count = 0
        backlog_total = 0
        backlog_max = 0
        for _ in range(20):
            healthz = run.client.get("/healthz", headers=run.headers)
            assert healthz.status_code == 200, f"Expected /healthz=200, got {healthz.status_code}"
            payload = healthz.get_json() or {}
            runtime_metrics = payload.get("runtime_metrics", {})
            tick_count = int(runtime_metrics.get("tick_count", 0))
            backlog_total = int(runtime_metrics.get("control_event_backlog_total", 0))
            backlog_max = int(runtime_metrics.get("control_event_backlog_max", 0))
            if tick_count > 0:
                break
            time.sleep(0.05)

        assert tick_count > 0, f"tick_count must be > 0, got {tick_count}"
        assert backlog_total <= 1000, f"control_event_backlog_total too high: {backlog_total}"
        assert backlog_max <= 500, f"control_event_backlog_max too high: {backlog_max}"

        snapshot = {
            "tick_count": tick_count,
            "control_event_backlog_total": backlog_total,
            "control_event_backlog_max": backlog_max,
            "departures_checked": len(departures),
        }
        print(f"[gate] runtime metrics snapshot: {json.dumps(snapshot)}")
        return snapshot


def main() -> None:
    print("=== release smoke gate ===")
    print(f"python: {sys.executable}")
    print(f"repo:   {repo}")

    # 1) Fast test surface
    _run_pytest("fast suite", ["-m", "not slow", "-q"])

    # 2) Determinism contract lock
    _run_pytest("golden snapshot", ["tests/test_golden_snapshot.py", "-q"])

    # 3) Shadow core spot-checks
    _run_pytest(
        "shadow core",
        [
            "tests/test_shadow_stability.py::TestHarnessDefaults::test_default_start_time_is_stable_and_exposed",
            "tests/test_shadow_comparison_harness.py::TestGeneratorDeterminism::test_baseline_determinism",
            "-q",
        ],
    )

    # 4) Runtime metrics sanity
    metrics = _runtime_metrics_sanity()

    print("\n=== release smoke gate: PASS ===")
    print(json.dumps({"status": "pass", "runtime_metrics": metrics}, indent=2))


if __name__ == "__main__":
    # Ensure subprocess pytest calls run from the project root even when invoked elsewhere.
    os.chdir(repo)
    main()
