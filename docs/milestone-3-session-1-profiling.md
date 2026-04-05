# Milestone 3, Session 1: Performance Profiling & Optimization

**Status:** Bottleneck identified and optimization framework created

## Summary

### Profiling Results
Baseline performance analysis revealed a **critical bottleneck in economy snapshot refresh**:

| Metric | Result |
|--------|--------|
| Routing throughput (pick_destination) | ✓ ~3,000 calls/sec |
| Ship selection throughput (select_ship) | ✓ ~2,000 calls/sec |
| Generator tick latency | ✗ **2,521 ms average** (target: <50ms) |
| Generator ticks per 5 seconds | ✗ Only 2 ticks (target: 25+) |

### Root Cause
The `_refresh_station_economy_snapshot()` function in generator.py:
1. **Makes 2 database queries per refresh** (one with limit 5000, a second if total > 5000 rows)
2. **Refreshes every simulated hour** (configured as 1/24 day threshold)
3. **Blocks the main generator tick** (runs synchronously during _apply_lifecycle)
4. With 300-400 events/minute rate: many refreshes queued, causing extreme latency

### Optimization Framework Created

**New Module: `src/space_traffic_api/simulation/engine/optimization.py`**

#### StationEconomyCache
- Batch-loads all station economy data in **one database query**
- Maintains in-memory cache between refreshes
- Lazy-loads compatible station lists per ship size class

#### PickDestinationOptimized  
- Pre-computes and caches compatible station lookup
- Avoids redundant dictionary traversals
- Pre-computed economy weights reduce per-call overhead

### Test Coverage
- **3 new optimization tests** (all passing):
  - Confirms single-query refresh pattern
  - Validates cache reuse benefit
  - Verifies economy weight computation accuracy
- **4 new profiling tests**: baseline metrics + throughput measurements

### Next Steps (Session 2)
1. Integrate `StationEconomyCache` and `PickDestinationOptimized` into generator.py
2. Re-run profiling tests to measure latency improvement
3. Target: <50ms average tick latency with full economy weighting
4. Validate no regression in functional/determinism tests

### Files Modified/Created
- `/src/space_traffic_api/simulation/engine/optimization.py` — new caching framework
- `/tests/test_engine_profiling.py` — baseline performance measurements
- `/tests/test_engine_optimization.py` — optimization module unit tests
