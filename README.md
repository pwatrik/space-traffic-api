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

Workflow file: `.github/workflows/ci.yml`

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

