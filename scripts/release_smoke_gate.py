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
    .venv\\Scripts\\python.exe scripts\\release_smoke_gate.py [--report-out PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

repo = Path(__file__).parent.parent
sys.path.insert(0, str(repo / "tests"))
sys.path.insert(0, str(repo / "src"))

from shadow.fixtures import DeterministicRun  # noqa: E402


class SmokeGateCheckError(RuntimeError):
    def __init__(self, label: str, category: str, reason: str):
        super().__init__(reason)
        self.label = label
        self.category = category


def _write_report(report_out: str, report: dict[str, Any]) -> None:
    if not report_out:
        return

    report_path = Path(report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[gate] wrote smoke report: {report_path}")


def _run_pytest(label: str, category: str, args: list[str]) -> dict[str, Any]:
    cmd = [sys.executable, "-m", "pytest", *args]
    print(f"\n[gate] {label}")
    print(f"[gate] command: {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=repo, check=False)
    if completed.returncode != 0:
        raise SmokeGateCheckError(label, category, f"pytest exited with code {completed.returncode}")

    return {
        "name": label,
        "category": category,
        "status": "pass",
        "details": "pytest command succeeded",
    }


def _runtime_metrics_sanity() -> dict[str, object]:
    print("\n[gate] runtime metrics sanity")
    with DeterministicRun(preset="baseline", seed=99, rate=300) as run:
        # Ensure the engine is active and has produced some events.
        departures = run.collect_departures(n=5, timeout_seconds=12.0)
        if len(departures) < 5:
            raise RuntimeError("expected at least 5 departures during smoke run")

        tick_count = 0
        backlog_total = 0
        backlog_max = 0
        for _ in range(20):
            healthz = run.client.get("/healthz", headers=run.headers)
            if healthz.status_code != 200:
                raise RuntimeError(f"expected /healthz=200, got {healthz.status_code}")
            payload = healthz.get_json() or {}
            runtime_metrics = payload.get("runtime_metrics", {})
            tick_count = int(runtime_metrics.get("tick_count", 0))
            backlog_total = int(runtime_metrics.get("control_event_backlog_total", 0))
            backlog_max = int(runtime_metrics.get("control_event_backlog_max", 0))
            if tick_count > 0:
                break
            time.sleep(0.05)

        if tick_count <= 0:
            raise RuntimeError(f"tick_count must be > 0, got {tick_count}")

        if backlog_total > 1000:
            raise RuntimeError(f"control_event_backlog_total too high: {backlog_total}")

        if backlog_max > 500:
            raise RuntimeError(f"control_event_backlog_max too high: {backlog_max}")

        snapshot = {
            "tick_count": tick_count,
            "control_event_backlog_total": backlog_total,
            "control_event_backlog_max": backlog_max,
            "departures_checked": len(departures),
        }
        print(f"[gate] runtime metrics snapshot: {json.dumps(snapshot)}")
        return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Release smoke gate")
    parser.add_argument(
        "--report-out",
        default="",
        help="Optional path for writing a JSON smoke report artifact",
    )
    args = parser.parse_args()

    print("=== release smoke gate ===")
    print(f"python: {sys.executable}")
    print(f"repo:   {repo}")

    report: dict[str, Any] = {"status": "pass", "checks": []}

    checks: list[tuple[str, str, list[str]]] = [
        ("fast suite", "fast_suite", ["-m", "not slow", "-q"]),
        ("golden snapshot", "golden_snapshot", ["tests/test_golden_snapshot.py", "-q"]),
        ("api contract", "api_contract", ["tests/test_api_contract.py", "-q"]),
        (
            "shadow core",
            "shadow_core",
            [
                "tests/test_shadow_stability.py::TestHarnessDefaults::test_default_start_time_is_stable_and_exposed",
                "tests/test_shadow_comparison_harness.py::TestGeneratorDeterminism::test_baseline_determinism",
                "-q",
            ],
        ),
    ]

    try:
        for label, category, check_args in checks:
            report["checks"].append(_run_pytest(label, category, check_args))

        metrics = _runtime_metrics_sanity()
        report["checks"].append(
            {
                "name": "runtime metrics sanity",
                "category": "runtime_metrics",
                "status": "pass",
                "details": "runtime metrics are within expected bounds",
            }
        )
        report["runtime_metrics"] = metrics
    except BaseException as exc:
        if isinstance(exc, SystemExit):
            raise

        failed_label = "runtime metrics sanity"
        failed_category = "runtime_metrics"

        if isinstance(exc, SmokeGateCheckError):
            failed_label = exc.label
            failed_category = exc.category
        elif isinstance(exc, KeyboardInterrupt):
            failed_label = "operator interrupt"
            failed_category = "interrupted"

        report["status"] = "fail"
        report["failure"] = {
            "check": failed_label,
            "category": failed_category,
            "reason": str(exc),
        }

        _write_report(args.report_out, report)
        print("\n=== release smoke gate: FAIL ===")
        print(json.dumps(report, indent=2))
        raise SystemExit(1)

    _write_report(args.report_out, report)
    print("\n=== release smoke gate: PASS ===")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    # Ensure subprocess pytest calls run from the project root even when invoked elsewhere.
    os.chdir(repo)
    main()
