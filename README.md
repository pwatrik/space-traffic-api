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

## Authentication

No authentication is required. All endpoints are public.

---

## API Reference

### Health

#### `GET /`
Redirects to `/ui`.

#### `GET /ui`
Embedded operational dashboard (live SSE feeds + key metrics + top fleet state).

#### `GET /healthz`
Public endpoint.

**Response:**
```json
{
  "status": "ok",
  "server_time": "2150-01-01T00:00:00+00:00",
  "counts": {
    "stations": 40, "ships": 500, "ships_in_transit": 38,
    "departures": 14203, "control_events": 12
  },
  "active_scenario": null,
  "active_faults": {},
  "deterministic_mode": false,
  "db_size_bytes": 10485760,
  "db_max_size_bytes": 536870912
}
```

#### `GET /openapi.yaml`
Returns the OpenAPI 3.1 YAML spec. Public endpoint; import directly into Postman or Insomnia.

---

### Domain Data

#### `GET /stations`
Returns station registry with pagination.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `body_type` | `planet\|moon\|asteroid` | — | Filter by body type |
| `limit` | int 1–5000 | 1000 | Page size |
| `offset` | int ≥ 0 | 0 | Skip N rows |
| `order_by` | `id\|name\|body_name\|body_type\|parent_body` | `body_type` | Sort column |
| `order` | `asc\|desc` | `asc` | Sort direction |

**Response:**
```json
{
  "stations": [
    {
      "id": "STN-PLANET-EARTH",
      "name": "Avalon Prime Port",
      "body_name": "Earth",
      "body_type": "planet",
      "parent_body": "Sun",
      "allowed_size_classes": ["small", "medium"]
    }
  ],
  "count": 9,
  "total_count": 40,
  "offset": 0,
  "limit": 1000
}
```

#### `GET /ships`
Returns ship registry with pagination and filters.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `faction` | `merchant\|government\|military\|bounty_hunter` | — | Filter by faction |
| `home_station_id` | string | — | Filter by home station |
| `cargo` | string | — | Filter by cargo type (exact match) |
| `ship_type` | string | — | Filter by ship type (e.g. `Freighter`) |
| `limit` | int 1–5000 | 1000 | Page size |
| `offset` | int ≥ 0 | 0 | Skip N rows |
| `order_by` | `id\|name\|faction\|ship_type\|cargo\|home_station_id\|size_class` | `id` | Sort column |
| `order` | `asc\|desc` | `asc` | Sort direction |

**Response:**
```json
{
  "ships": [
    {
      "id": "SHIP-00042",
      "name": "Iron Pioneer",
      "faction": "merchant",
      "ship_type": "Freighter",
      "size_class": "large",
      "displacement_million_m3": 1.4,
      "home_station_id": "STN-MOON-TITAN",
      "captain_name": "Mira Voss",
      "cargo": "titanium_alloy_billets"
    }
  ],
  "count": 50,
  "total_count": 500,
  "offset": 0,
  "limit": 1000
}
```

#### `GET /ships/state`
Returns live operational state for ships (status, transit flags, position, age).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `status` | `active\|decommissioned\|destroyed` | — | Filter by status |
| `in_transit` | `1\|0\|true\|false` | — | Filter by transit flag |
| `limit` | int 1–5000 | 500 | Max rows |

**Response:**
```json
{
  "ships": [
    {
      "ship_id": "SHIP-00042",
      "name": "Iron Pioneer",
      "faction": "merchant",
      "ship_type": "Freighter",
      "home_station_id": "STN-MOON-TITAN",
      "status": "active",
      "current_station_id": null,
      "in_transit": 1,
      "source_station_id": "STN-MOON-TITAN",
      "destination_station_id": "STN-PLANET-EARTH",
      "departure_time": "2150-01-01T08:00:00+00:00",
      "est_arrival_time": "2150-01-02T14:22:00+00:00",
      "ship_age_days": 1482.5,
      "updated_at": "2150-01-01T08:00:00+00:00"
    }
  ],
  "count": 38
}
```

#### `GET /stats`
Fleet-wide aggregate counts and simulation state.

**Response:**
```json
{
  "summary": { "stations": 40, "ships": 500, "ships_in_transit": 38, "departures": 14203, "control_events": 12 },
  "factions":   { "merchant": 180, "government": 75, "military": 60, "bounty_hunter": 185 },
  "ship_types": { "Freighter": 62, "Frigate": 30, "Star Wasp": 22 },
  "cargo_types": { "titanium_alloy_billets": 8, "refined_steel": 7 },
  "ship_states": { "active": 497, "decommissioned": 3 },
  "pirate_strength": 0.82,
  "active_scenario": null
}
```

---

### Events

#### `GET /departures`
Cursor-based polling for departure events. Pass `next_since_id` from the previous response as `since_id` on the next call.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `since_id` | int | — | Return only rows with id > this value |
| `since_time` | ISO-8601 | — | Minimum departure_time (ignored if since_id is set) |
| `limit` | int 1–1000 | 100 | Max rows |
| `order` | `asc\|desc` | `asc` | Row order |

**Response:**
```json
{
  "departures": [
    {
      "id": 1024,
      "event_uid": "EVT-20150101-0042-SHIP-00042",
      "departure_time": "2150-01-01T08:00:00+00:00",
      "ship_id": "SHIP-00042",
      "source_station_id": "STN-MOON-TITAN",
      "destination_station_id": "STN-PLANET-EARTH",
      "est_arrival_time": "2150-01-02T14:22:00+00:00",
      "scenario": null,
      "fault_flags": [],
      "malformed": false,
      "payload": { ... }
    }
  ],
  "count": 1,
  "next_since_id": 1024
}
```

#### `GET /departures/stream`
SSE stream. Emits `event: departure` for each new departure. Sends `: keepalive` every 10 s when idle.

```
event: departure
data: {"id": 1025, "event_uid": "...", "departure_time": "...", ...}

: keepalive
```

#### `GET /control-events`
Cursor-based polling for control-plane changes (scenario activations, fault toggles, resets, lifecycle, pirate events).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `since_id` | int | — | Return only rows with id > this value |
| `limit` | int 1–1000 | 100 | Max rows |
| `order` | `asc\|desc` | `asc` | Row order |

**Response:**
```json
{
  "control_events": [
    {
      "id": 7,
      "event_time": "2150-01-01T00:00:00+00:00",
      "event_type": "scenario",
      "action": "activated",
      "payload": { "name": "war", "intensity": 1.5 }
    }
  ],
  "count": 1,
  "next_since_id": 7
}
```

`event_type` values: `control`, `scenario`, `fault`, `lifecycle`, `pirate`

#### `GET /control-events/stream`
SSE stream for control-plane changes. Emits `event: control_event`.

---

### Control

#### `GET /config`
Returns full runtime snapshot including merged `effective_lifecycle` and `effective_ship_generation` configs.

#### `PATCH /config`
| Field | Type | Notes |
|---|---|---|
| `deterministic_mode` | boolean | Toggle deterministic replay |
| `deterministic_seed` | integer | RNG seed |
| `db_max_size_mb` | integer ≥ 50 | SQLite file size cap |

```powershell
Invoke-RestMethod -Method Patch -Uri "http://localhost:8000/config" `
  -ContentType "application/json" `
  -Body '{"deterministic_mode": true, "deterministic_seed": 1337}'
```

#### `GET /scenarios`
Returns available scenarios and the currently active one.

#### `POST /scenarios/activate`
| Field | Type | Default | Notes |
|---|---|---|---|
| `name` | `war\|shortage\|solar_flare` | required | — |
| `intensity` | float 0–5 | 1.0 | Scales all scenario effects |
| `duration_seconds` | int ≥ 1 | 300 | Auto-deactivation after this many seconds |
| `scope` | object | `{"type": "global"}` | — |

**Scenarios:**
| Name | Rate multiplier | Effect |
|---|---|---|
| `war` | 3× | Military surge, increased losses, reduced builds |
| `shortage` | 2.2× | Merchant hauling spike, elevated builds |
| `solar_flare` | 0× | Traffic halt, increased decommissioning |

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/scenarios/activate" `
  -ContentType "application/json" `
  -Body '{"name": "war", "intensity": 1.5, "duration_seconds": 300}'
```

#### `POST /scenarios/deactivate`
No body required. Clears the active scenario immediately.

#### `GET /faults`
Returns available fault types and currently active faults.

#### `POST /faults/activate`
Each fault key maps to an optional config object.

| Fault name | Default rate | Effect |
|---|---|---|
| `malformed_payload` | 0.02 | Corrupt `payload` to invalid JSON |
| `missing_field` | 0.03 | Drop required fields from payload |
| `invalid_enum` | 0.02 | Inject invalid enum values |
| `out_of_order_timestamp` | 0.02 | Skew `departure_time` backwards |
| `delayed_insert` | 0.03 | Delay persistence for a subset of events |
| `duplicate_event_uid` | 0.01 | Reuse a previous `event_uid` |
| `synthetic_error` | 0.01 | Emit error-shaped records |

Per-fault config:
| Field | Type | Default | Notes |
|---|---|---|---|
| `rate` | float 0–1 | fault's default | Fraction of events affected |
| `duration_seconds` | int ≥ 0 | 0 | 0 = indefinite |

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/faults/activate" `
  -ContentType "application/json" `
  -Body '{"faults": {"out_of_order_timestamp": {"rate": 0.2}, "malformed_payload": {"rate": 0.1}}}'
```

#### `POST /faults/deactivate`
```json
{ "names": ["malformed_payload"] }
```
Omit `names` to clear all active faults.

#### `POST /control/reset`
Clears departure and ship-state history. Resets all ships to home stations. Re-seeds RNG if `seed` is provided.

```json
{ "seed": 1337 }
```

**Deterministic replay pattern:**
```powershell
# 1. Enable deterministic mode
Invoke-RestMethod -Method Patch -Uri "http://localhost:8000/config" `
  -ContentType "application/json" `
  -Body '{"deterministic_mode": true, "deterministic_seed": 1337}'

# 2. Reset and seed
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/control/reset" `
  -ContentType "application/json" `
  -Body '{"seed": 1337}'
```

---

## Smoke Check

- `scripts/smoke_check.py` — deterministic replay, scenario/fault controls, control-event visibility. Writes `smoke_report.json`.
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

