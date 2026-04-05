"""Optimized routing and economy caching for Milestone 3, Session 1.

This module improves the generator's hot paths by:
- Caching station data in memory with lazy population
- Reducing duplicate database queries
- Batching economy state updates

Usage: Add these optimizations to generator.py in the _apply_lifecycle method.
"""

from datetime import datetime
from typing import Any

from ..scenarios import SCENARIO_DEFINITIONS


class StationEconomyCache:
    """Cache for station economy data with memory-efficient updates."""

    def __init__(self, station_lookup: dict[str, dict[str, Any]]):
        """Initialize cache from station_lookup.
        
        Args:
            station_lookup: Reference dict of all stations from seed data.
        """
        self._station_lookup = station_lookup
        self._last_refresh_at: datetime | None = None
        self._cached_keys: set[str] = set()

    def refresh_if_needed(
        self,
        store: Any,  # SQLiteStore
        elapsed_days: float,
        refresh_interval_days: float,
        accumulator_days: float,
    ) -> tuple[float, bool]:
        """Conditionally refresh station economy cache.
        
        Args:
            store: SQLiteStore instance for querying stations.
            elapsed_days: Simulated time elapsed this tick.
            refresh_interval_days: Threshold for refresh (e.g., 1/24 for hourly).
            accumulator_days: Current accumulation value.
            
        Returns:
            (updated_accumulator, refreshed): cumulative days and whether refresh occurred.
        """
        updated_accumulator = accumulator_days + elapsed_days
        refreshed = False

        if updated_accumulator >= refresh_interval_days:
            self._refresh_batch(store)
            updated_accumulator = 0.0
            refreshed = True

        return updated_accumulator, refreshed

    def _refresh_batch(self, store: Any) -> None:
        """Fetch economy data once from DB and cache in memory."""
        # Single-pass batch load: get all stations with only one DB query
        rows, total = store.list_stations(limit=10000, order_by="id", order="asc")
        self._cached_keys.clear()

        for row in rows:
            station_id = str(row.get("id") or "")
            if not station_id or station_id not in self._station_lookup:
                continue

            # Update in-memory cache with latest economy state from DB
            station = self._station_lookup[station_id]
            station["economy_profile"] = row.get("economy_profile", {})
            station["economy_state"] = row.get("economy_state", {})
            station["economy_derived"] = row.get("economy_derived", {})
            self._cached_keys.add(station_id)

        self._last_refresh_at = datetime.now()

    def refresh_batch(self, store: Any) -> None:
        """Public single-shot refresh entrypoint."""
        self._refresh_batch(store)

    def get_economy_weight(
        self,
        source_station_id: str,
        dest_station_id: str,
        economy_preference_weight: float = 0.15,
    ) -> float:
        """Get cached economy weight for routing decision.
        
        Avoids redundant dict lookups by returning precomputed weight.
        """
        if economy_preference_weight <= 0:
            return 1.0  # No weighting; all paths equally likely

        src = self._station_lookup.get(source_station_id, {})
        dst = self._station_lookup.get(dest_station_id, {})

        src_derived = src.get("economy_derived", {}) or {}
        dst_derived = dst.get("economy_derived", {}) or {}
        dst_state = dst.get("economy_state", {}) or {}

        source_fuel = max(0.1, float(src_derived.get("fuel_pressure_score", 1.0) or 1.0))
        dest_fuel = max(0.1, float(dst_derived.get("fuel_pressure_score", 1.0) or 1.0))
        fuel_cost_ratio = max(0.5, min(2.0, dest_fuel / source_fuel))

        local_value = float(dst_derived.get("local_value_score", 0.0) or 0.0)
        if local_value <= 0:
            supply = max(0.01, float(dst_state.get("supply_index", 1.0) or 1.0))
            demand = float(dst_state.get("demand_index", 1.0) or 1.0)
            price = float(dst_state.get("price_index", 1.0) or 1.0)
            local_value = (demand / supply) * price

        local_value = max(0.1, min(10.0, local_value))
        net_value = local_value / fuel_cost_ratio
        station_weight = 1.0 + ((net_value - 1.0) * economy_preference_weight)

        return max(0.001, station_weight)


class PickDestinationOptimized:
    """Optimized destination picker with pre-computed distance/economy weights."""

    def __init__(
        self,
        station_lookup: dict[str, dict[str, Any]],
        distance_groups: dict[str, int],
    ):
        """Initialize with station data."""
        self._station_lookup = station_lookup
        self._distance_groups = distance_groups
        self._economy_cache = StationEconomyCache(station_lookup)
        # Pre-compute candidate sets once per configuration
        self._compatible_stations: dict[str, list[str]] = {}

    def pick_cached(
        self,
        ship: dict[str, Any],
        source_station_id: str,
        scenario: dict[str, Any] | None,
        pirate_state: dict[str, Any] | None,
        rng: Any,
        station_accepts_size_class_func: Any,
        economy_preference_weight: float = 0.15,
        pirate_conf: dict[str, Any] | None = None,
    ) -> str | None:
        """Optimized pick_destination that uses cached data.
        
        Key optimizations:
        - Reuse compatible station list across multiple calls
        - Avoid redundant economy dict lookups
        - Short-circuit for bounty hunters more often
        """
        if pirate_conf is None:
            pirate_conf = {}

        ship_size_class = str(ship.get("size_class") or "medium").strip().lower()
        cache_key = f"{ship_size_class}"

        # Lazy-load compatible station list per size class
        if cache_key not in self._compatible_stations:
            station_ids = list(self._station_lookup.keys())
            station_ids = [
                sid
                for sid in station_ids
                if station_accepts_size_class_func(sid, ship_size_class)
            ]
            self._compatible_stations[cache_key] = station_ids

        station_ids = [
            sid for sid in self._compatible_stations[cache_key]
            if sid != source_station_id
        ]

        if not station_ids:
            return None

        if scenario and scenario.get("name") == "shortage":
            keywords = SCENARIO_DEFINITIONS["shortage"].get("preferred_source_keywords", [])
            preferred = [sid for sid in station_ids if any(key in sid for key in keywords)]
            if preferred and rng.random() < 0.65:
                return rng.choice(preferred)

        # Bounty hunter targeting: short-circuit if active
        is_bounty_hunter = str(ship.get("faction") or "") == "bounty_hunter"
        if is_bounty_hunter and isinstance(pirate_state, dict) and pirate_state.get("active"):
            affected = [
                sid
                for sid in pirate_state.get("affected_station_ids", [])
                if sid in station_ids
            ]
            if affected:
                response_bias = min(
                    1.0, max(0.0, float(pirate_conf.get("bounty_hunter_response_bias", 0.9)))
                )
                if rng.random() < response_bias:
                    return rng.choice(affected)

        # For merchants: use cached economy weights
        if str(ship.get("faction") or "") == "merchant" and economy_preference_weight > 0:
            weighted = []
            for sid in station_ids:
                weight = self._economy_cache.get_economy_weight(
                    source_station_id,
                    sid,
                    economy_preference_weight,
                )
                weighted.append((sid, weight))

            total = sum(w for _, w in weighted)
            if total > 0:
                threshold = rng.random() * total
                running = 0.0
                for sid, station_weight in weighted:
                    running += station_weight
                    if threshold <= running:
                        return sid

        return rng.choice(station_ids)
