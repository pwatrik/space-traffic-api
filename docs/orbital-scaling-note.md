# Orbital Scaling Engineering Note

## Purpose
Capture the performance assumptions and escalation thresholds for Milestone 2.5 orbital state before implementation begins.

## Recommendation
- Implement Milestone 2.5 with Python stdlib math first.
- Design the orbital state and distance sampling path so it can be migrated to array-based execution later without a model rewrite.
- Do not add Skyfield or similar astronomy libraries.
- Do not add NumPy or Numba preemptively; add them only if profiling shows orbital math is a real hotspot.

## Why Stdlib First
- The expected body count for initial rollout is still small enough that per-tick phase updates are cheap.
- The likely first bottlenecks at higher scale are routing candidate scans, database writes, event persistence, and state serialization rather than trig alone.
- A pure-Python first pass keeps packaging simple and makes correctness/determinism easier to validate.

## Scaling Expectations

### Likely Fine Without NumPy
- Hundreds of bodies with one orbital update per body per tick.
- Low-thousands of departures where each departure samples one source/destination distance from cached body positions.
- A moderate increase in slingshot cargo traffic, provided body positions are updated once per tick and reused.

### Pressure Zone
- Hundreds of bodies plus thousands of departures per tick.
- Merchant or cargo routing that scores many candidate destinations per ship and repeatedly queries distance.
- Slingshot mechanics multiplying effective departure evaluations well beyond current ship count.

### Likely Need for a Numeric Upgrade
- Thousands of bodies.
- Tens of thousands of distance samples per tick.
- Profiling shows orbital state updates or distance sampling are a top-2 contributor to tick time after obvious caching fixes.

## Required Design Constraints

### Keep the Hot Path Cheap
- Cache station-to-body anchor mapping once at startup/reset.
- Update body positions once per tick, not once per departure.
- Cache the body-position snapshot for the tick.
- Cache body-to-body distance lookups for the current tick if many departures reuse the same routes.

### Avoid Dict-Heavy Numeric Work
- Prefer compact orbital-state structures over deep nested dict reads in inner loops.
- Keep runtime control state separate from the per-tick numeric state where practical.
- Treat debug snapshots as derived views, not the hot-path representation.

### Preserve Determinism
- Orbital advancement must be pure math driven by simulated elapsed time.
- Reset with the same seed/config/start time must rebuild identical orbital state.
- Performance optimizations must not change event ordering or RNG consumption unintentionally.

## Dependency Guidance

### NumPy
Use if:
- Orbital updates and distance sampling can be expressed as batch array operations.
- Body state is represented in dense arrays.
- Profiling shows numeric kernels are dominant.

Expected benefit:
- Vectorized body phase/position updates.
- Efficient per-tick recomputation for large body counts.

### Numba
Use only if:
- Profiling shows numeric kernels remain dominant after data layout cleanup.
- NumPy alone is not enough or the algorithm stays loop-heavy.

Tradeoffs:
- More deployment complexity.
- Warm-up cost.
- Harder debugging.

### Astronomy Libraries
Do not use for Milestone 2.5.

Reason:
- Accuracy requirement is intentionally rough.
- Dependency cost outweighs value for the current scope.

## Benchmark Gate Before Dependency Escalation

Add a benchmark harness that measures:
1. Body orbital-state update cost per tick.
2. Distance sampling cost for N departures using cached per-tick positions.
3. Combined routing-adjacent cost for representative candidate scans.

Benchmark matrix:
- Bodies: 100, 500, 1000.
- Departure samples: 1000, 5000, 20000.
- Candidate-route fanout: 10, 50, 100.

Capture:
- Mean tick cost.
- p95 tick cost.
- Fraction of total tick time spent in orbital math vs routing vs storage.

## Escalation Thresholds
- Stay stdlib if orbital update + distance sampling remains under 10-15% of total tick time.
- Revisit NumPy if orbital math becomes a top-2 hotspot.
- Revisit Numba only after NumPy/data-layout improvements if orbital kernels still dominate.

## Immediate Implementation Guidance
- Proceed with stdlib for Sessions 1-3.
- Structure orbital state so an array-backed implementation is possible later.
- Add the benchmark harness before scaling traffic assumptions further.