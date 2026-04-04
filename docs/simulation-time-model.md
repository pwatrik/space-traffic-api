# Simulation Time Model (Milestone 2.6)

Status: Session 1 complete (contract and naming formalization)

## Purpose
Define a single simulation-time contract before implementation refactors in Milestone 2.6.

## Time Domains

1. Wall Clock Time
- Meaning: real machine/server clock when an API-visible change was observed or persisted.
- Source: `datetime.now(UTC)` at write/emit boundaries.
- Use: external observability, ingestion ordering, latency and operations analysis.

2. Simulation Time
- Meaning: in-universe timeline that drives ship travel, orbital movement, timed events, and economy progression.
- Source: simulation clock authority (`simulation_now`).
- Use: game/simulation semantics and deterministic replay contracts.

## Canonical Principles

1. Single simulation clock authority
- All simulation subsystems must consume the same simulated delta:
  - orbital advancement
  - ship transit and arrival completion
  - scenario/fault expirations
  - pirate lifecycle
  - economy drift and policy updates

2. Startup/reset epoch target
- Default simulation epoch target for Milestone 2.6 is `2100-01-01T00:00:00Z`.
- Startup/reset epoch semantics should be independent of deterministic RNG mode.

3. Compression ratio semantics
- `simulation_time_scale` is treated as `sim_seconds_per_wall_second`.
- Example mapping target:
  - 180 simulated days should elapse in about 3 wall-clock hours.
  - Equivalent scale is about 1440x (`180 * 24 * 3600 / (3 * 3600)`).

4. Departure-time ETA sampling
- Arrival ETA is sampled once when departure is created.
- In-flight ETA does not drift due to later orbital movement.

## API Time Contract (Target)

For timing-sensitive payloads, expose both domains explicitly.

1. Departures
- Simulated fields:
  - `departure_time`
  - `est_arrival_time`
- Wall-clock field:
  - `observed_at` or `created_at` (final name decided during implementation)

2. Control events
- Simulated field:
  - `event_time`
- Wall-clock field:
  - `observed_at` or `created_at` (final name decided during implementation)

3. Ship state
- Simulated fields:
  - `departure_time`
  - `est_arrival_time`
- Add explicit wall-clock change tracking field if needed for external consumers.

## Current State Snapshot (pre-implementation)

- Simulated time exists as `simulation_now` and drives most simulation logic.
- Simulated time progression is currently coupled to departure-generator cadence.
- Startup epoch default is still `2150-01-01T00:00:00Z` in config.
- ETA estimation still uses a hop-based heuristic and does not satisfy long-route targets.
- API currently mixes time semantics; wall-clock timestamps are not explicit on all event surfaces.

## Implementation Sequence (Milestone 2.6)

1. Session 2: dedicated simulation clock path.
2. Session 3: epoch + compression defaults and controls.
3. Session 4: distance-driven ETA calibration.
4. Session 5: API wall-clock/sim-clock split.
5. Session 6+: deterministic and route-duration regression hardening.
