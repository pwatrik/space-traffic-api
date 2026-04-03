# Space Traffic API

Simulated solar-system shipping traffic API for data-engineering demos. Generates continuous
departure events across 500 ships, 40+ stations, and four factions. Supports deterministic
replay, named scenario bursts, pirate-activity lifecycle, fault injection, and SSE streaming.

The machine-readable spec is available at `GET /openapi.yaml` (no auth required) and in
[docs/openapi.yaml](docs/openapi.yaml).

## Features

- **Domain data** — 40+ stations (planet/moon/asteroid), 500 ships (merchant, government, military, bounty_hunter), 75 cargo types.
- **Departure generation** — 10–20 events/minute baseline; persisted to SQLite with automatic size-capped culling.
- **Pagination** — `/ships` and `/stations` support `limit`, `offset`, `order_by`, `order`.
- **Aggregate stats** — `GET /stats` returns counts by faction, ship type, cargo, and state.
- **Public API** — All endpoints are accessible without authentication.
- **Event streaming** — Polling (`/departures`) and SSE (`/departures/stream`); same for control events.
- **Control plane** — Deterministic replay, named scenario bursts, fault injection, and reset.
- **Pirate activity** — Localized risk zones suppressed by bounty hunter arrivals; strength tracked in `/config`.
- **Embedded dashboard** — Operational UI at `/ui` with live streams and fleet snapshot.

## Run Locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Server starts on `http://localhost:8000`.

Dashboard starts on `http://localhost:8000/ui`.

## Run In Container

```powershell
docker build -t space-traffic-api .
docker run --rm -p 8000:8000 space-traffic-api
```

## CI Policy

- Pull requests and pushes to `main` run fast checks with slow tests excluded.
- Nightly CI runs the full suite, then repeats shadow slow tests 3 times to detect flakes.
- Release smoke gate runs on push/manual and enforces a compact pre-release checklist.
- Dedicated release workflow runs on `v*` tags and publishes release artifacts.

Workflow file: `.github/workflows/ci.yml`
Release workflow: `.github/workflows/release.yml`

## API Compatibility + Deprecation Policy

This project uses a stability-first policy for the current API surface.

- Additive-first changes: new fields and new endpoints are preferred over changing existing response shapes.
- Existing response keys on stable endpoints should not be removed or renamed in a patch release.
- Behavior changes that impact deterministic output require explicit release notes and golden snapshot updates in the same PR.
- Breaking changes must be called out in release notes and delayed until the next minor or major tagged release.

Deprecation process:

1. Mark target behavior/field as deprecated in README and OpenAPI description text.
2. Keep backward-compatible behavior for at least one tagged release after deprecation notice.
3. Add/adjust contract tests to ensure both old and replacement paths are validated during the deprecation window.
4. Remove deprecated behavior only in a planned versioned release with migration notes.

## Release Smoke Gate

- Script: `scripts/release_smoke_gate.py`
- Runs:
  - `pytest -m "not slow" -q`
  - `pytest tests/test_golden_snapshot.py -q`
  - focused shadow-core checks
  - runtime metrics sanity (`tick_count > 0`, bounded backlog)

Run locally:

```powershell
.\.venv\Scripts\python.exe scripts\release_smoke_gate.py
```

Write a machine-readable smoke report artifact:

```powershell
.\.venv\Scripts\python.exe scripts\release_smoke_gate.py --report-out artifacts\smoke_report.json
```

## Determinism Contract + Perf Baseline

- Golden determinism contract test: `tests/test_golden_snapshot.py`
- Golden capture helper: `scripts/capture_golden_snapshot.py`
- Perf baseline script: `scripts/benchmark_deterministic.py`

Refresh golden snapshot after intentional deterministic behavior changes:

```powershell
.\.venv\Scripts\python.exe scripts\capture_golden_snapshot.py
```

Run baseline benchmark:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_deterministic.py --events 10 --rate 300
```

Write benchmark output to a release artifact path:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_deterministic.py --events 10 --rate 300 --output artifacts\benchmark_results.json
```

## Release Runbook

Use this sequence before creating a `v*` tag.

1. Run the release smoke gate and write an artifact.

```powershell
.\.venv\Scripts\python.exe scripts\release_smoke_gate.py --report-out artifacts\smoke_report.json
```

Expected pass signal:
- terminal includes `=== release smoke gate: PASS ===`
- `artifacts\smoke_report.json` exists with `"status": "pass"`

2. Run the deterministic benchmark and write an artifact.

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_deterministic.py --events 10 --rate 300 --output artifacts\benchmark_results.json
```

Expected pass signal:
- terminal prints `Results written to ...benchmark_results.json`
- artifact contains `elapsed_seconds`, `departures_per_second`, and `tick_latency`

3. (If deterministic behavior intentionally changed) refresh and update golden snapshots.

```powershell
.\.venv\Scripts\python.exe scripts\capture_golden_snapshot.py --preset baseline
.\.venv\Scripts\python.exe scripts\capture_golden_snapshot.py --preset war_heavy
.\.venv\Scripts\python.exe scripts\capture_golden_snapshot.py --preset pirate_enabled
```

Expected pass signal:
- output rows match intended deterministic changes
- `tests/test_golden_snapshot.py` updated in the same PR with rationale

4. Run full regression before tag.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected pass signal:
- all tests pass with no failures

5. Create and push the release tag.

```powershell
git tag vX.Y.Z
git push origin vX.Y.Z
```

Expected CI result:
- [release workflow](.github/workflows/release.yml) runs and publishes artifacts:
  - `openapi.yaml`
  - `smoke_report.json`
  - `benchmark_results.json`
  - `README.release.md`

### Failure Triage

#### Quick Triage Table

| Signal | Likely Cause | First Action |
| --- | --- | --- |
| Smoke gate fails in `fast suite` | Regression in core behavior | Re-run printed pytest command, fix regression before any snapshot updates |
| Smoke gate fails in `golden snapshot` | Deterministic output drift | Confirm seed/preset/rate; update golden only if behavior change is intentional |
| Smoke gate fails in `api contract` | Response shape drift | Diff endpoint payload keys and update implementation or contract test intentionally |
| Smoke gate fails in `shadow core` | Parity or stability regression | Re-run shadow test node IDs locally and inspect recent simulation/runtime changes |
| Smoke gate fails in `runtime_metrics` | Generator startup or control backlog issue | Check `/healthz` runtime metrics and inspect generator/control subscriber behavior |

#### Common Failure Signatures

| Signature | Interpretation | Action |
| --- | --- | --- |
| `pytest exited with code 1` | One of the gate test groups failed | Run that exact group directly and fix root cause |
| `tick_count must be > 0` | Generator did not advance | Verify generator startup and deterministic run setup |
| `control_event_backlog_total too high` | Control event queues are not draining | Check subscriber cleanup and long-lived stream consumers |
| `control_event_backlog_max too high` | At least one subscriber backlog spiked | Inspect per-subscriber behavior and stream disconnect handling |
| `expected /healthz=200` | Health endpoint unavailable during gate | Check app bootstrap and route registration state |

- Smoke gate fails in fast/golden/shadow checks:
  - run the exact failing pytest command printed by `scripts/release_smoke_gate.py`
  - fix regression first; do not update golden snapshots unless behavior change is intentional
- Smoke gate fails runtime metrics sanity:
  - inspect `/healthz` runtime metrics (`tick_count`, backlog values)
  - verify generator start/stop behavior and control event subscriber cleanup
- Benchmark output looks suspicious (for example very low throughput):
  - re-run once to rule out transient machine load
  - compare against recent `benchmark_results.json` from the latest successful release tag
- Golden snapshot mismatch:
  - verify seed/preset/rate are unchanged
  - if intentional, refresh via capture script and review diffs carefully in `tests/test_golden_snapshot.py`

## Authentication

No authentication is required. All endpoints are public.

---

## API Reference
Full API documentation is available here:
- https://pwatrik.github.io/space-traffic-api/

### Endpoints

#### Core
- `GET /` (redirects to `/ui`)
- `GET /ui`
- `GET /healthz`
- `GET /openapi.yaml`

#### Domain Data
- `GET /stations`
- `GET /ships`
- `GET /ships/state`
- `GET /stats`

#### Events
- `GET /departures`
- `GET /departures/stream`
- `GET /control-events`
- `GET /control-events/stream`

#### Controls
- `GET /config`
- `PATCH /config`
- `GET /scenarios`
- `POST /scenarios/activate`
- `POST /scenarios/deactivate`
- `GET /faults`
- `POST /faults/activate`
- `POST /faults/deactivate`
- `POST /control/reset`

### Quick Examples

```powershell
# Health check
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/healthz"

# List ships (paged)
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/ships?limit=25&offset=0&order_by=id&order=asc"

# Tail departures with cursor polling
$r1 = Invoke-RestMethod -Method Get -Uri "http://localhost:8000/departures?limit=50"
$since = $r1.next_since_id
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/departures?since_id=$since&limit=50"

# Toggle deterministic mode
Invoke-RestMethod -Method Patch -Uri "http://localhost:8000/config" `
  -ContentType "application/json" `
  -Body '{"deterministic_mode": true, "deterministic_seed": 1337}'

# Activate a scenario
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/scenarios/activate" `
  -ContentType "application/json" `
  -Body '{"name": "war", "intensity": 1.5, "duration_seconds": 300}'

# Activate a fault
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/faults/activate" `
  -ContentType "application/json" `
  -Body '{"faults": {"out_of_order_timestamp": {"rate": 0.2}}}'
```

---

## Sanity Check

- `scripts/sanity_check.py` — deterministic replay, scenario/fault controls, control-event visibility. Writes `smoke_report.json`.
- `scripts/container_sanity_check.py` — validates a running container at `http://127.0.0.1:8000`. Writes `container_sanity_report.json`.

```powershell
.\.venv\Scripts\python.exe scripts\container_sanity_check.py
```

Optional overrides: `SPACE_TRAFFIC_BASE_URL`

---

## Notes

- Deterministic replay is guaranteed when deterministic mode is on, the same seed and config are used, and `/control/reset` is called before each run.
- `SPACE_TRAFFIC_DB_MAX_SIZE_MB` sets the SQLite cap; oldest departures are culled first when exceeded.
- Fault events are flagged per-departure in `fault_flags`; `malformed: true` means `payload` is corrupted.
- Control-plane changes are persisted as `control_events` so consumers can correlate data anomalies with scenario, fault, and reset actions.
- `GET /config` includes `effective_lifecycle` and `effective_ship_generation` — the base config merged with any active scenario overrides.

