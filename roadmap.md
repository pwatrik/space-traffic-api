# Roadmap

## Planning Assumptions
- A "session" means one focused working block of about 60-90 minutes.
- Estimates include code, tests, and docs updates.
- Order is intentional: Milestone 1 is first to de-risk later feature work.

## Milestone 1: Lightweight Platform Polish (First)
Estimated effort: 4-6 sessions
Status: Complete

### Progress
- Completed: Session 1 (release/version compatibility policy in README)
- Completed: Session 2 (startup config validation implementation)
- Completed: Session 3 (config validation test coverage for invalid combinations and boundary values)
- Implemented: Session 4 (smoke gate structured pass/fail reason categories)
- Completed: Session 5 (runbook quick triage table and common failure signatures)
- Completed: Session 6 buffer (cleanup, final polish, and validation run)
- Verified: clean end-to-end smoke gate run with structured category report artifact

### Goal
Improve release confidence and day-to-day operability without introducing enterprise scope.

### Deliverables
1. Release and compatibility policy
- Add a short versioning and deprecation policy to README.
- Define additive-change rules for API responses and behavior changes.

2. Config and startup safety
- Add startup validation for key env vars and fail-fast messages.
- Add tests for invalid config combinations and boundary values.

3. Guardrail refresh
- Expand release smoke gate output to include pass/fail reason categories.
- Ensure determinism and contract tests remain wired into smoke/release flow.

4. Runbook hardening
- Add "quick triage" and "common failure signatures" table to runbook.
- Document expected artifacts and minimal local pre-tag command sequence.

5. Local dev reliability cleanup
- Keep local artifacts ignored (gitignore upkeep).
- Standardize script outputs to predictable paths where useful.

### Definition of Done
- README contains release/version guidance and updated runbook.
- Smoke gate produces a structured report with clear failure classification.
- Config validation has tests and clear operator-facing messages.
- CI remains green with no increase in flaky behavior.

### Suggested Session Breakdown
1. Session 1: Versioning/deprecation policy + README updates.
2. Session 2: Config validation implementation.
3. Session 3: Config validation test coverage.
4. Session 4: Smoke gate output improvements.
5. Session 5: Runbook triage table and artifact guidance.
6. Session 6 (buffer): Cleanup, final polish, and validation run.

## Milestone 2: Economy Simulation
Estimated effort: 8-12 sessions
Status: In progress

### Progress
- Completed chunk 1: station economy scaffolding fields (economy_profile and economy_state) seeded, persisted, and exposed via /stations
- Completed chunk 1 tests: seed-data shape checks, API shape checks, and migration-column checks
- Completed chunk 2: read-only derived station economy metrics (local_value_score, scarcity_index, fuel_pressure_score) in /stations responses
- Completed chunk 2 tests: bounds checks and deterministic stability across app boots
- Completed chunk 3: producer_rate/consumer_rate station profile fields plus lightweight tick update for supply/demand indexes
- Completed chunk 3 tests: supply/demand drift bounds and deterministic repeatability with seeded RNG
- Next chunk: connect departure events to station economy state (source supply down, destination demand eased) with small deterministic adjustments

### Goal
Real economy with producers at stations, variable prices due to events, distance from materials, or station needs.

### Scope
- Value system that drives trade ship behavior, choice of destinations.
- Production and consumption rates at stations
- Placeholder attributes on stations (temperature, food production, oxygen, water, manufacturing material demand, [make extensible]) that influence the value of goods at each station
- Basic fuel simulation that impacts long distances
- Values at stations are increased with lack of supply, eg if ships do not decide to travel there, the decreased supply drives up price

### Definition of Done
- Independent value lists of goods generated in each station
- Ship behavior influenced by available cargo, high sell prices.
- Tuning controls for adjusting all aspects of economy and behavior (add to api later)

## Milestone 2.5 Orbital Locations

### Goal
Rework of planet/body distances to roughly simulate orbital positions, changing over simulated time.

## Milestone 3: Engine Realism and Determinism Depth
Estimated effort: 10-14 sessions

### Goal
Upgrade engine internals so advanced simulation behavior remains stable, reproducible, and performant.

### Scope
- Improve state model and routing behavior.
- Evolve event scheduling/ordering with deterministic guarantees.
- Add replay/checkpoint capabilities for debugging and backtesting.
- Profile and tune performance envelope for heavier scenarios.

### Definition of Done
- Determinism contracts remain stable across new complexity.
- Engine-level tests validate ordering, routing, and replay behavior.
- Performance baseline remains within agreed envelope.

## Milestone 4: API Surface and Integration Enhancements
Estimated effort: 7-10 sessions

### Goal
Expose richer simulation capabilities through stable, usable API contracts.

### Scope
- Improve query ergonomics (time windows, richer filtering/sorting).
- Expand endpoint contract tests for departures/ships/stations/control payloads.
- Improve stream/replay usability and selective event consumption.
- Add practical integration exports/notifications where they add immediate value.

### Definition of Done
- API contract tests cover all core response shapes.
- New query/stream behavior is documented with examples.
- Backward compatibility rules are respected and validated.

## Session Estimate Summary
- Milestone 1: 4-6 sessions
- Milestone 2: 8-12 sessions
- Milestone 3: 10-14 sessions
- Milestone 4: 7-10 sessions
- Total roadmap estimate: 29-42 sessions

## Notes
- Milestones 2 and 3 can partially overlap after Milestone 1 is complete.
- If throughput is priority, run Milestone 2 scenario work in parallel with Milestone 3 replay/scheduler work.
