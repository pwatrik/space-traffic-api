# Space Traffic API

Fake event API for data engineering ingestion demos. It simulates ship departures across stations in the solar system and supports runtime controls for deterministic replay, burst scenarios, and fault injection.

## Features

- Static domain data:
  - Stations: one per major planet, major moon, and major asteroid.
  - Pluto is treated as a planet, with Charon as its moon.
  - Ships: 220 registry entries across merchant, government, and military factions.
- Departure generation:
  - Baseline throughput: 10-20 events/minute.
  - Background generator starts at app initialization.
  - Every event is persisted to SQLite.
- Security:
  - Static API key auth via `X-API-Key` or `Authorization: Bearer`.
- Event consumption:
  - Polling endpoint: `GET /departures`
  - SSE endpoint: `GET /departures/stream`
  - Control-plane correlation endpoints: `GET /control-events` and `GET /control-events/stream`
- Control plane:
  - Deterministic mode and seed control.
  - Named scenario bursts: `war`, `shortage`, `solar_flare`.
  - Fault injection toggles for malformed/out-of-order/etc events.

## Run Locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Server starts on `http://localhost:8000`.

## Run In Container

```powershell
docker build -t space-traffic-api .
docker run --rm -p 8000:8000 -e SPACE_TRAFFIC_API_KEY=space-demo-key space-traffic-api
```

## Auth

All endpoints except `GET /healthz` require API key.

Header options:

- `X-API-Key: space-demo-key`
- `Authorization: Bearer space-demo-key`

## Core Endpoints

- `GET /stations?body_type=planet|moon|asteroid`
- `GET /ships?faction=merchant|government|military&home_station_id=...&cargo=...&ship_type=...`
- `GET /departures?since_id=0&since_time=...&limit=100&order=asc|desc`
- `GET /departures/stream`
- `GET /control-events?since_id=0&limit=100&order=asc|desc`
- `GET /control-events/stream`

## Control Endpoints

- `GET /config`
- `PATCH /config`
- `GET /scenarios`
- `POST /scenarios/activate`
- `POST /scenarios/deactivate`
- `GET /faults`
- `POST /faults/activate`
- `POST /faults/deactivate`
- `POST /control/reset`

## Example Control Calls

```powershell
$headers = @{ "X-API-Key" = "space-demo-key" }

Invoke-RestMethod -Method Patch -Uri "http://localhost:8000/config" -Headers $headers -ContentType "application/json" -Body '{"deterministic_mode": true, "deterministic_seed": 1337}'

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/scenarios/activate" -Headers $headers -ContentType "application/json" -Body '{"name": "war", "intensity": 1.5, "duration_seconds": 300, "scope": {"type": "global"}}'

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/faults/activate" -Headers $headers -ContentType "application/json" -Body '{"faults": {"out_of_order_timestamp": {"rate": 0.2}, "malformed_payload": {"rate": 0.1}}}'

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/control/reset" -Headers $headers -ContentType "application/json" -Body '{"seed": 1337}'
```

## Smoke Check

- `scripts/smoke_check.py` runs a quick validation flow for deterministic replay, scenario/fault controls, and control-events visibility.
- It writes a summary to `smoke_report.json` and writes a traceback to `smoke_report.error.txt` on failure.

## Notes

- Deterministic replay is guaranteed when:
  - deterministic mode is enabled,
  - the same seed and config are used,
  - and `/control/reset` is called before each run.
- Fault injections are flagged per event in `fault_flags`.
- Control-plane changes are persisted and streamable as `control_events` so consumers can correlate data anomalies with scenario, fault, and reset actions.
