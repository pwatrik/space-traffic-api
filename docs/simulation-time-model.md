# Simulation Time Model Contract (Milestone 2.6 Session 1)

This document defines the current contract and target contract for simulation time behavior.

## Purpose

- Make wall-clock and simulated-time semantics explicit for operators and API consumers.
- Establish migration-safe naming before clock refactor work.
- Lock down expectations for determinism and reset behavior.

## Terms

- wall-clock time: real elapsed host time.
- simulated time: in-universe time used by departures, arrivals, orbital movement, and economy.
- sim-to-wall ratio: how many simulated seconds advance per one wall-clock second.

## Current Behavior (Pre-Clock Refactor)

- Simulation progression is currently coupled to generator tick cadence.
- The runtime config field simulation_time_scale currently acts as a speed multiplier.
- Deterministic mode seeds RNG and also sets initial simulated timestamp from deterministic_start_time.
- API payloads include timestamps that are primarily simulated-time fields; some fields represent persistence/observation time.

## Session 1 Contract Decisions

1. Naming and compatibility
- simulation_time_scale remains the authoritative runtime field for backward compatibility.
- simulation_time_scale is defined as sim-to-wall ratio semantics (higher means faster simulated progression).
- Future naming cleanup may add an alias field, but simulation_time_scale remains supported for the full Milestone 2.6 rollout.

2. Epoch target (planned for Session 3)
- Product target startup/reset epoch: 2100-01-01T00:00:00Z.
- Current default remains unchanged in code for now; this session documents the target contract only.

3. Time-field interpretation guidance
- departure_time and est_arrival_time are simulated timeline values.
- control event timestamps are currently event timeline values used by existing consumers; explicit wall-clock split is planned for Session 5.
- updated_at in ship state is currently persistence/update time as emitted by the current runtime path.

4. Determinism constraints
- For fixed seed + config + start time, simulated outcomes must remain reproducible.
- Any timestamp-contract split must preserve deterministic snapshot/golden behavior unless intentionally recaptured.

## Planned Migration Sequence

1. Session 2: introduce dedicated simulation clock loop and decouple progression from generation cadence.
2. Session 3: move default epoch/reset behavior to 2100-01-01T00:00:00Z and expose ratio controls cleanly.
3. Session 4: recalibrate distance-driven travel durations against target route envelopes.
4. Session 5: split wall-clock and simulated-time fields in API payloads.
5. Session 6+: add regression and calibration coverage, then tune.

## API Documentation Requirements (Session 1)

- OpenAPI descriptions should state whether each timing field is simulated-time, wall-clock, or transitional.
- /config should document simulation_time_scale as sim-to-wall ratio semantics.
- /config should include deterministic_start_time and simulation_now in schema descriptions.
