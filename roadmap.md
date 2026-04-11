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
- Completed chunk 4: departure-linked economy impacts (source supply down, destination demand eased) with bounded deterministic adjustments
- Completed chunk 4 tests: event-impact bounds and deterministic repeatability with seeded RNG
- Completed chunk 5: merchant destination preference now includes conservative economy_derived value weighting
- Completed chunk 5 tests: merchant preference behavior, non-merchant neutrality, and deterministic seeded routing
- Completed chunk 6: economy tuning knobs for merchant preference, drift magnitude, and departure impact magnitude wired through config, runtime patch controls, and simulation paths
- Completed chunk 6 tests: env/default validation, PATCH /config clamping, and fixed-magnitude deterministic economy-state checks
- Completed chunk 7: distance_rank seeded into economy_profile per station body position; fuel_pressure_score now scales with orbital distance; merchant routing applies fuel cost ratio (dest/source fuel pressure) to net effective destination value
- Completed chunk 7 tests: distance_rank presence + solar position correctness, moon rank inheritance, fuel pressure higher for distant stations, merchant penalizes high-fuel-cost routes
- Completed chunk 8: price_index in advance_station_economy now drifts toward demand/supply equilibrium each tick (target = demand/supply, delta = 5% of gap × day_factor × magnitude), clamped [0.5, 3.0]; all 120 tests green
- Completed chunk 8 tests: price rises when demand > supply, price falls when supply > demand, stable at equilibrium, deterministic with seeded RNG
- Completed chunk 9: confirmed price_index flows end-to-end through economy derivation (local_value_score = demand/supply × price) into merchant routing; routing fallback also reads price_index directly from economy_state; 122 tests green
- Completed chunk 9 tests: local_value_score scales with price_index (higher price → higher score), merchant prefers higher-price-index destination when routed via raw economy_state fallback
- Completed chunk 10: departure impact now also eases destination price_index — arriving shipment signals incoming supply, applying a small downward price nudge (magnitude × 0.3 × [0.8–1.2]) clamped [0.5, 3.0]; goldens recaptured; 124 tests green
- Completed chunk 10 tests: departure lowers destination price_index, departure price ease is deterministic with seeded RNG
- Completed chunk 11: economy health observable via GET /stats — added get_economy_summary() to CatalogRepository and SQLiteStore; /stats now includes economy_summary with station_count, price_index_{avg,min,max}, supply_index_avg, demand_index_avg, stations_above/below_equilibrium; contract test updated; 125 tests green
- Completed chunk 11 tests: /stats includes economy_summary with correct keys and valid bounds
- Completed chunk 12: Economy Health card added to /ui dashboard — shows avg/min/max price_index, avg supply/demand, station count, and above/at/below equilibrium counts; rendered via renderEconomySummary() called from setKpis on every snapshot refresh; 125 tests green (1 transient Windows file-lock flake in shadow stability is pre-existing and unrelated)
- Completed chunk 13: Avg Price Index sparkline wired into live dashboard trend charts using existing history/canvas renderer path; 125 tests green
- Post-chunk refactor pass: extracted shared JSON parsing helper in catalog repository to remove repeated decode fallback blocks with no behavior change

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
Estimated effort: 5-8 sessions
Status: Planned (default-off experimental slice)

### Goal
Introduce rough, deterministic orbital movement where planets/asteroids have tracked positions updated each simulation tick, and departure-time distance uses the current orbital state.

### Scope Boundaries (Locked)
- Include rough, deterministic orbital state per body (not astronomy-grade).
- Include per-tick orbital state advancement tied to simulated time.
- Include departure-time distance sampling from current body positions.
- Exclude in-transit distance recomputation.
- Exclude rerouting due to mid-flight orbital motion.
- Exclude NASA-accurate ephemerides and trajectory complexity.

### Deliverables
1. Body orbital state model
- Add a body-level orbital state representation (for planets/asteroids and inherited station body anchors).
- Define rough orbital parameters and initial phases from deterministic seed/catalog data.
- Persist current orbital phase/position in runtime state (or equivalent deterministic tick-state store).

2. Tick-time orbital updates
- Advance orbital state each simulation tick using simulated elapsed time.
- Keep advancement deterministic for fixed seed/config/start time.
- Expose current orbital state in diagnostics/debug snapshot (lightweight view).

3. Departure-time-only distance integration
- Compute departure distance from source/destination body positions at that tick.
- Keep transit fixed to that sampled distance/time for the whole trip.

4. Runtime control and safety
- Add default-off config/runtime knobs with validation and clamping.
- Keep current behavior unchanged when the feature is disabled.

5. Verification and rollout gate
- Add unit/integration tests for bounds and determinism.
- Add tests for tick-to-tick orbital position advancement and station body-anchor mapping correctness.
- Add regression test proving no in-flight distance changes after departure.
- Run A/B comparison (feature off vs on) and record transit/economy behavior deltas.

### Definition of Done
- Feature is off by default and can be enabled via existing config/control path.
- Planets/asteroids have deterministic orbital positions that advance each tick in simulated time.
- Departure routing/ETA distance uses current orbital state at tick time.
- For fixed seed + config + simulated start time, results remain deterministic.
- Arrival estimation uses departure-time sampled distance only (no mid-flight updates).
- Golden/shadow test impact is understood and either unchanged or intentionally recaptured.
- Observed behavior shift is meaningful but controlled (no extreme routing instability).

### Suggested Session Breakdown
1. Session 1: define orbital state model (body anchors, phase/period representation) and deterministic initialization.
2. Session 2: wire per-tick orbital advancement using simulated elapsed time.
3. Session 3: integrate departure-time distance calculation from current orbital positions.
4. Session 4: add config/runtime controls and debugging snapshot visibility.
5. Session 5: add unit/integration/regression coverage (including no in-flight distance updates).
6. Session 6: run shadow/golden validation and deterministic drift checks.
7. Session 7: A/B analysis on travel/economy effects; tune constraints.
8. Session 8 (buffer): docs, cleanup, and any intentional golden recapture.

### Session 1 Technical Design Checklist (Pre-Implementation)
1. Body Anchor Mapping Contract
- Define canonical body IDs for all orbital participants (planets, dwarf planets, asteroid belts/clusters used by stations).
- Define station-to-body anchor rules (including moon stations inheriting parent orbital body where applicable).
- Add fallback behavior for unknown bodies (deterministic default anchor and warning path).

2. Orbital State Schema
- Define runtime orbital state shape (for each body): phase, angular_velocity, radius_scale, optional eccentricity_hint.
- Define unit conventions (phase in radians, velocity in radians/day, simulated-time day basis).
- Decide where state lives during runtime and how snapshot/debug views expose it.

3. Deterministic Initialization Rules
- Initialization must be reproducible from deterministic seed + catalog metadata + fixed defaults.
- No hidden randomness outside seeded RNG path.
- Reset behavior must recreate identical orbital state for same reset seed/config.

4. Tick Advancement Contract
- Orbital state updates occur once per simulation tick using elapsed simulated days.
- Advancement is pure math with no side effects outside orbital state storage.
- Time-scale and pause/reset semantics are explicitly documented.

5. Distance Sampling Contract
- Departure-time distance reads source/destination body positions from current orbital state.
- Distance is sampled once at departure and persisted into ETA calculation.
- Arrival does not re-query orbital state mid-flight.

6. Config and Guardrails
- Confirm feature gate remains default-off.
- Confirm multiplier/scale knobs and bounds for orbital effect remain conservative.
- Confirm invalid config handling mirrors existing fail-fast startup + runtime clamp behavior.

7. Test Plan (Session 1 Exit Criteria)
- Unit tests for deterministic initialization of orbital state.
- Unit tests for station-to-body anchor mapping (including moon/parent-body behavior).
- Unit tests for tick advancement monotonic phase evolution.
- Regression test proving reset reproduces identical orbital state for same seed.

8. Design Review Exit Criteria
- Data model approved (body anchors + orbital state shape).
- Determinism invariants documented.
- Integration points for Sessions 2-3 identified in generator/runtime flow.
- Open questions list reduced to implementation-ready decisions only.

### Engineering Notes
- See [docs/orbital-scaling-note.md](docs/orbital-scaling-note.md) for performance assumptions, benchmark gates, and dependency escalation thresholds for orbital-state implementation.

## Milestone 2.6 Simulation Time Model
Estimated effort: 6-9 sessions
Status: Planned

### Goal
Introduce a dedicated simulation clock and a clean wall-clock vs simulated-time contract so long-haul travel, orbital movement, economy, and timed events all advance on the same compressed simulation timeline.

### Why This Is Needed
- Current simulated time advancement is still coupled to departure-generation cadence.
- Current ETA calculation is still hop-based and far too short for the target travel envelope.
- Current API payloads mix simulated timestamps with event-observed timestamps, which makes external consumption ambiguous.
- The desired default compression ratio and startup epoch are now product requirements rather than optional tuning details.

### Scope Boundaries (Locked)
- Include a dedicated simulation clock service or equivalent clock loop decoupled from event generation.
- Include a fixed simulation epoch starting at `2100-01-01T00:00:00Z` on startup and reset.
- Include a user-adjustable time-compression ratio in UI and config.
- Include recalibrated travel durations for representative long/short routes.
- Include explicit wall-clock and simulated-time fields in API responses where timing matters.
- Exclude high-fidelity astrophysics, relativistic travel, or route-by-route propulsion simulation.
- Exclude replay/checkpoint architecture work unless directly required by the clock refactor.

### Deliverables
1. Dedicated simulation clock
- Add a clock authority that advances simulation time independently of departure-rate randomness.
- Ensure orbital movement, ship travel, scenario/fault expiry, pirate lifecycle, and economy drift all consume the same simulated delta.

2. Fixed epoch and reset semantics
- Change the default simulation start to `2100-01-01T00:00:00Z`.
- Make startup/reset semantics independent of deterministic RNG mode.
- Preserve deterministic reproducibility when seed + config + start time are fixed.

3. Time-compression controls
- Reframe `simulation_time_scale` as an explicit sim-to-wall-clock ratio.
- Set default compression near the agreed target for long-haul travel.
- Expose the ratio clearly in the UI and `/config` contract.

4. Travel-time recalibration
- Replace hop-based ETA estimation with a calibrated distance-driven model.
- Make Earth-to-Mars at close approach land near 3-4 simulated days.
- Make Neptune-to-Pluto at far separation land near 180 simulated days.
- Preserve departure-time-only sampling so in-flight ETA does not change.

5. API time contract split
- Add wall-clock timestamps for when departures/control events are observed or persisted.
- Keep simulation timestamps for departure/arrival and other in-universe event timing.
- Update serializers, docs, and tests so consumers can distinguish the two clearly.

### Definition of Done
- Simulation starts at `2100-01-01T00:00:00Z` on startup/reset unless explicitly overridden.
- Simulation clock progression is no longer implicitly derived from departure cadence.
- Orbits, ship transit, timed events, and economy all advance from the same simulated clock delta.
- Default compression yields roughly 180 simulated days in about 3 wall-clock hours.
- API responses expose both wall-clock event timing and simulated timing where applicable.
- Deterministic mode still produces reproducible behavior with fixed seed/config/start time.

### Suggested Session Breakdown
1. Session 1: formalize time model, rename/clarify clock semantics, and add roadmap/API notes.
2. Session 2: implement dedicated simulation clock path and decouple it from generator cadence.
3. Session 3: change default epoch/reset behavior to `2100-01-01T00:00:00Z`; add config/runtime/UI controls for compression ratio.
4. Session 4: replace hop-based ETA estimation with calibrated distance-based travel duration.
5. Session 5: split wall-clock vs simulated timestamps in departures/control events/ship state serialization.
6. Session 6: add deterministic regression tests and route-duration calibration tests.
7. Session 7: validate dashboard behavior and operator controls against live simulation.
8. Session 8-9 (buffer): tuning, migration cleanup, and documentation updates.

## Milestone 3: Engine Realism and Determinism Depth
Estimated effort: 10-14 sessions
Status: In progress

### Progress
- Completed: Session 1 profiling harness added for routing, ship selection, and generator throughput/latency guardrails.
- Completed: Session 1 identified startup launch burst and economy snapshot refresh as primary hot paths under high-rate scenarios.
- Completed: Session 2 integrated station economy cache into generator lifecycle refresh path.
- Completed: Session 2 batched startup merchant launches across ticks to reduce long single-tick stalls.
- Completed: Session 2 regression validation for determinism/API suites after scheduler hot-path changes.
- Completed: Session 3 integrated cached destination-picking path and reduced duplicate available-ship list queries in generator hot loops.
- Completed: Session 3 preserved deterministic/golden contracts after optimization-path parity fix.
- Completed: Session 4 reduced lifecycle query churn by eliminating per-stage active-ship re-queries inside generator ticks.
- Completed: Session 4 mutation-aware active-ship filtering validated against determinism/golden/API/scenario/pirate suites.
- Completed: Session 5 reduced per-event retention overhead by throttling departure trimming to periodic checks.
- Completed: Session 5 tuned startup launch batch size for smoother tick latency while preserving deterministic output contracts.
- Completed: Session 6 collapsed ship-state/cargo mutation into a single departure-start transaction.
- Completed: Session 6 collapsed departure insert plus economy-impact writes into a single persistence transaction, materially improving generator throughput while preserving deterministic/golden/API behavior.
- Completed: Session 7 threaded per-tick runtime snapshot state through ship selection, destination choice, and ETA estimation to avoid redundant snapshot reads.
- Completed: Session 7 added adaptive startup launch batch sizing based on recent tick latency while preserving deterministic/golden/API behavior.
- Completed: Session 8 throttled station economy drift mutations to hourly simulated cadence with a dedicated economy RNG stream.
- Completed: Session 8 added arrival completion fast-path (skip UPDATE/commit when no arrivals are due), improving tick throughput while keeping deterministic/golden/API contracts stable.

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
- Milestone 2.5: 5-7 sessions
- Milestone 2.6: 6-9 sessions
- Milestone 3: 10-14 sessions
- Milestone 4: 7-10 sessions
- Total roadmap estimate: 40-58 sessions

## Notes
- Milestones 2 and 3 can partially overlap after Milestone 1 is complete.
- Milestone 2.5 is intentionally constrained and should complete before broad Milestone 3 engine changes.
- Milestone 2.6 should land before deeper Milestone 3 scheduler/replay work so time semantics are stable first.
- If throughput is priority, run Milestone 2 scenario work in parallel with Milestone 3 replay/scheduler work.
