from __future__ import annotations

import queue
import random
import threading
import time
from collections import deque
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from ..seed_data import load_naming_config, station_distance_groups
from ..store import SQLiteStore
from .engine.departure_builder import create_departure_event
from .engine.fault_injector import apply_faults
from .engine.routing import pick_destination
from .engine.ship_selector import select_ship
from .engine.simulation_engine import SimulationEngine
from .policies.build import apply_build_queue_policy
from .policies.decommission import apply_decommission_policy
from .policies.lifecycle import build_effective_lifecycle_config
from .policies.pirate import apply_pirate_activity_policy
from .policies.war import apply_war_impact_policy
from .runtime import RuntimeState
from .scenarios import SCENARIO_DEFINITIONS


class DepartureGenerator(threading.Thread):
    def __init__(
        self,
        store: SQLiteStore,
        runtime: RuntimeState,
        stations: list[dict[str, Any]],
        ships: list[dict[str, Any]],
        catalog: dict[str, Any] | None = None,
    ):
        super().__init__(daemon=True)
        self._store = store
        self._runtime = runtime
        self._stations = stations
        self._ships = ships
        self._stop_event = threading.Event()
        self._subscribers: list[queue.Queue[dict[str, Any]]] = []
        self._subscribers_lock = threading.Lock()
        self._distance_groups = station_distance_groups(stations)
        self._ship_lookup = {s["id"]: s for s in ships}
        self._station_lookup = {s["id"]: s for s in stations}
        self._catalog = catalog or {}
        self._lifecycle = self._catalog.get("lifecycle", {})
        self._ship_generation = self._catalog.get("ship_generation", {})
        defaults = self._ship_generation.get("defaults") or {}
        raw_speed_multiplier = defaults.get("ship_speed_multiplier", 84.0)
        if isinstance(raw_speed_multiplier, (int, float)) and float(raw_speed_multiplier) > 0:
            self._ship_speed_multiplier = float(raw_speed_multiplier)
        else:
            self._ship_speed_multiplier = 84.0

        self._naming = load_naming_config()

        self._rng: random.Random | None = None
        self._sim_time: datetime | None = None
        self._event_counter = 0
        self._last_event_uid = ""
        self._next_db_size_check_at = 0.0
        self._next_ship_sequence = self._store.max_ship_sequence() + 1
        self._age_update_accumulator_days: float = 0.0
        self._startup_merchants_launched = False
        self._engine = SimulationEngine()
        self._metrics_lock = threading.Lock()
        self._tick_count = 0
        self._tick_latency_total_ms = 0.0
        self._tick_latency_last_ms = 0.0
        self._tick_latency_max_ms = 0.0
        self._departures_emitted = 0
        self._last_tick_completed_at: str | None = None
        self._departures_window_seconds = 60.0
        self._departure_timestamps: deque[float] = deque()

    def stop(self) -> None:
        self._stop_event.set()

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1000)
        with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[dict[str, Any]]) -> None:
        with self._subscribers_lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def effective_lifecycle_config(self, scenario: dict[str, Any] | None) -> dict[str, Any]:
        scenario_definition = SCENARIO_DEFINITIONS.get((scenario or {}).get("name", ""), {})
        intensity = float((scenario or {}).get("intensity", 1.0))
        return build_effective_lifecycle_config(
            base_lifecycle=self._lifecycle,
            scenario_definition=scenario_definition,
            intensity=intensity,
        )

    def effective_ship_generation_config(self) -> dict[str, Any]:
        defaults = dict(self._ship_generation.get("defaults") or {})
        defaults["ship_speed_multiplier"] = self._ship_speed_multiplier
        return {"defaults": defaults}

    def runtime_metrics(self) -> dict[str, Any]:
        with self._metrics_lock:
            now = time.monotonic()
            while self._departure_timestamps and (now - self._departure_timestamps[0]) > self._departures_window_seconds:
                self._departure_timestamps.popleft()

            tick_count = self._tick_count
            avg_latency = self._tick_latency_total_ms / tick_count if tick_count else 0.0

            return {
                "tick_count": tick_count,
                "tick_latency_ms_last": round(self._tick_latency_last_ms, 3),
                "tick_latency_ms_avg": round(avg_latency, 3),
                "tick_latency_ms_max": round(self._tick_latency_max_ms, 3),
                "departures_emitted_total": self._departures_emitted,
                "departures_per_minute_recent": len(self._departure_timestamps),
                "last_tick_completed_at": self._last_tick_completed_at,
            }

    def run(self) -> None:
        while not self._stop_event.is_set():
            tick_started = time.perf_counter()
            state = self._runtime.snapshot()
            self._ensure_rng(state)

            scenario = state.get("active_scenario")
            effective_min, effective_max = self._effective_rate_bounds(state, scenario)
            rate = self._rng.randint(effective_min, effective_max)
            interval_seconds = max(0.2, 60.0 / float(rate))
            simulation_time_scale = max(0.1, float(state.get("simulation_time_scale", 1.0) or 1.0))
            wait_seconds = interval_seconds / simulation_time_scale
            tick_time = self._current_tick_time(state)

            result = self._engine.tick(
                state=state,
                scenario=scenario,
                tick_time=tick_time,
                interval_seconds=interval_seconds,
                wait_seconds=wait_seconds,
                startup_merchants_launched=self._startup_merchants_launched,
                launch_startup_merchants=self._launch_all_merchants_at_startup,
                complete_arrivals=lambda t: self._store.complete_ship_arrivals_with_details(
                    t.isoformat(), now_iso=t.isoformat()
                ),
                apply_lifecycle=self._apply_lifecycle,
                is_globally_interrupted=self._is_globally_interrupted,
                build_event=self._build_event,
                apply_faults=self._apply_faults,
                delayed_insert_pause=lambda _event: self._stop_event.wait(timeout=1.5),
                persist_and_publish_event=self._persist_and_publish_event,
                advance_sim_time=self._advance_sim_time,
            )

            self._startup_merchants_launched = result.startup_merchants_launched
            tick_latency_ms = (time.perf_counter() - tick_started) * 1000.0
            with self._metrics_lock:
                self._tick_count += 1
                self._tick_latency_last_ms = tick_latency_ms
                self._tick_latency_total_ms += tick_latency_ms
                self._tick_latency_max_ms = max(self._tick_latency_max_ms, tick_latency_ms)
                self._last_tick_completed_at = datetime.now(UTC).isoformat()

            # wait_seconds=0.0 signals the engine encountered a stop condition mid-tick
            if result.wait_seconds == 0.0:
                break

            if self._stop_event.wait(timeout=result.wait_seconds):
                break

    def _ensure_rng(self, state: dict[str, Any]) -> None:
        seed = int(state["deterministic_seed"])
        det_mode = bool(state["deterministic_mode"])

        if self._rng is None:
            self._rng = random.Random(seed if det_mode else None)
            self._set_sim_time(state)
            return

        reset_marker = state.get("last_reset_at")
        cache_key = getattr(self, "_last_reset_marker", None)
        if reset_marker and reset_marker != cache_key:
            self._last_reset_marker = reset_marker
            self._rng = random.Random(seed if det_mode else None)
            self._set_sim_time(state)
            self._event_counter = 0
            self._last_event_uid = ""
            self._startup_merchants_launched = False

    def _set_sim_time(self, state: dict[str, Any]) -> None:
        if state.get("deterministic_mode"):
            raw = state.get("deterministic_start_time", "2150-01-01T00:00:00Z")
            try:
                self._sim_time = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                self._sim_time = datetime.now(UTC)
            self._runtime.set_simulation_now(self._sim_time.isoformat())
            return

        self._sim_time = datetime.now(UTC)
        self._runtime.set_simulation_now(self._sim_time.isoformat())

    def _effective_rate_bounds(
        self,
        state: dict[str, Any],
        scenario: dict[str, Any] | None,
    ) -> tuple[int, int]:
        base_min = int(state["base_min_events_per_minute"])
        base_max = int(state["base_max_events_per_minute"])
        if not scenario:
            return base_min, base_max

        definition = SCENARIO_DEFINITIONS.get(scenario["name"], {})
        multiplier = float(definition.get("rate_multiplier", 1.0)) * float(scenario.get("intensity", 1.0))
        if multiplier <= 0:
            return 1, 1

        eff_min = max(1, int(base_min * multiplier))
        eff_max = max(eff_min, int(base_max * multiplier))
        return eff_min, eff_max

    def _apply_lifecycle(
        self,
        interval_seconds: float,
        tick_time: datetime,
        scenario: dict[str, Any] | None,
        arrived_ships: list[dict[str, Any]],
    ) -> None:
        if interval_seconds <= 0:
            return

        effective_lifecycle = self.effective_lifecycle_config(scenario)

        elapsed_days = interval_seconds / 86400.0

        flush_threshold_days = 1.0 / 24.0  # flush once per simulated hour
        self._age_update_accumulator_days += elapsed_days
        age_update_days = 0.0
        if self._age_update_accumulator_days >= flush_threshold_days:
            chunks = int(self._age_update_accumulator_days / flush_threshold_days)
            age_update_days = chunks * flush_threshold_days
            self._age_update_accumulator_days -= age_update_days

        if age_update_days > 0.0:
            self._store.increment_ship_age(age_update_days, now_iso=tick_time.isoformat())

        apply_pirate_activity_policy(
            tick_time=tick_time,
            elapsed_days=elapsed_days,
            lifecycle_conf=effective_lifecycle,
            runtime=self._runtime,
            store=self._store,
            rng=self._rng,
            station_lookup=self._station_lookup,
            parse_iso=self._parse_iso,
            end_pirate_event=self._end_pirate_event,
        )
        self._apply_pirate_arrival_effects(
            tick_time=tick_time,
            lifecycle_conf=effective_lifecycle,
            arrived_ships=arrived_ships,
        )

        self._store.advance_station_economy(elapsed_days=elapsed_days, rng=self._rng)

        active_ships = self._store.list_active_ships_for_lifecycle()
        if not active_ships:
            return

        apply_decommission_policy(
            active_ships=active_ships,
            elapsed_days=elapsed_days,
            tick_time=tick_time,
            lifecycle_conf=effective_lifecycle,
            store=self._store,
            rng=self._rng,
        )
        active_ships = self._store.list_active_ships_for_lifecycle()
        if not active_ships:
            return

        apply_war_impact_policy(
            active_ships=active_ships,
            elapsed_days=elapsed_days,
            tick_time=tick_time,
            lifecycle_conf=effective_lifecycle,
            store=self._store,
            rng=self._rng,
        )
        active_ships = self._store.list_active_ships_for_lifecycle()
        _, self._next_ship_sequence = apply_build_queue_policy(
            active_ships=active_ships,
            elapsed_days=elapsed_days,
            tick_time=tick_time,
            lifecycle_conf=effective_lifecycle,
            store=self._store,
            rng=self._rng,
            ship_generation=self._ship_generation,
            naming_config=self._naming,
            next_ship_sequence=self._next_ship_sequence,
            ship_lookup=self._ship_lookup,
            pick_weighted_key=self._pick_weighted_key,
            pick_station_by_policy=self._pick_station_by_policy,
        )

    def _apply_pirate_arrival_effects(
        self,
        tick_time: datetime,
        lifecycle_conf: dict[str, Any],
        arrived_ships: list[dict[str, Any]],
    ) -> None:
        if not arrived_ships:
            return

        conf = lifecycle_conf.get("pirate_activity") or {}
        if not conf.get("enabled", False):
            return

        state = deepcopy(self._runtime.snapshot().get("pirate_event"))
        if not isinstance(state, dict) or not state.get("active"):
            return

        affected_station_ids = set(state.get("affected_station_ids") or [])
        if not affected_station_ids:
            return

        merchant_candidates = [
            row
            for row in arrived_ships
            if row.get("faction") == "merchant" and row.get("destination_station_id") in affected_station_ids
        ]
        if merchant_candidates:
            base = max(0.0, float(conf.get("merchant_arrival_base_destruction_chance", 0.04)))
            multiplier = max(0.0, float(conf.get("merchant_arrival_destruction_multiplier", 4.0)))
            destruction_chance = min(1.0, base * multiplier)
            destroyed: list[str] = []
            for row in merchant_candidates:
                if self._rng.random() >= destruction_chance:
                    continue
                ship_id = row["ship_id"]
                destination = row.get("destination_station_id")
                if self._store.deactivate_ship(
                    ship_id=ship_id,
                    status="destroyed",
                    current_station_id=destination,
                    now_iso=tick_time.isoformat(),
                ):
                    destroyed.append(ship_id)

            if destroyed:
                self._store.insert_control_event(
                    event_type="lifecycle",
                    action="pirate_losses",
                    payload={
                        "ship_ids": destroyed,
                        "count": len(destroyed),
                        "anchor_body": state.get("anchor_body"),
                        "at": tick_time.isoformat(),
                    },
                    event_time=tick_time.isoformat(),
                )

        bounty_arrivals = [
            row
            for row in arrived_ships
            if row.get("faction") == "bounty_hunter" and row.get("destination_station_id") in affected_station_ids
        ]
        if not bounty_arrivals:
            return

        decay_per_arrival = max(0.0, float(conf.get("strength_decay_per_bounty_hunter_arrival", 0.02)))
        if decay_per_arrival <= 0:
            return

        prev_strength = float(state.get("strength") or 0.0)
        decay_total = decay_per_arrival * len(bounty_arrivals)
        next_strength = max(0.0, prev_strength - decay_total)
        if next_strength >= prev_strength:
            return

        state["strength"] = next_strength
        state["updated_at"] = tick_time.isoformat()
        self._runtime.set_pirate_event_state(state)
        self._store.insert_control_event(
            event_type="lifecycle",
            action="pirate_strength_changed",
            payload={
                "anchor_body": state.get("anchor_body"),
                "previous_strength": prev_strength,
                "strength": next_strength,
                "delta": prev_strength - next_strength,
                "bounty_hunter_arrivals": len(bounty_arrivals),
                "at": tick_time.isoformat(),
            },
            event_time=tick_time.isoformat(),
        )

        runtime_snap = self._runtime.snapshot()
        raw_threshold = runtime_snap.get("pirate_strength_end_threshold")
        if raw_threshold is None:
            raw_threshold = conf.get("strength_end_threshold", 0.5)
        threshold = float(raw_threshold)
        if next_strength <= threshold:
            self._end_pirate_event(state=state, conf=conf, tick_time=tick_time, runtime_snap=runtime_snap)

    def _end_pirate_event(self, state: dict[str, Any], conf: dict[str, Any], tick_time: datetime, runtime_snap: dict[str, Any] | None = None) -> None:
        previous_anchor = state.get("anchor_body")
        strength = float(state.get("strength") or 0.0)
        if runtime_snap is None:
            runtime_snap = self._runtime.snapshot()
        raw_min_days = runtime_snap.get("pirate_respawn_min_days")
        if raw_min_days is None:
            raw_min_days = conf.get("respawn_min_days", 10.0)
        raw_max_days = runtime_snap.get("pirate_respawn_max_days")
        if raw_max_days is None:
            raw_max_days = conf.get("respawn_max_days", 30.0)
        min_days = float(raw_min_days)
        max_days = float(raw_max_days)
        delay_days = self._rng.uniform(min_days, max_days)
        next_spawn_at = tick_time + timedelta(days=delay_days)

        next_state = {
            **state,
            "active": False,
            "anchor_body": None,
            "previous_anchor_body": previous_anchor,
            "strength": strength,
            "ended_at": tick_time.isoformat(),
            "next_spawn_earliest_at": next_spawn_at.isoformat(),
            "affected_station_ids": [],
            "updated_at": tick_time.isoformat(),
        }
        self._runtime.set_pirate_event_state(next_state)
        self._store.insert_control_event(
            event_type="lifecycle",
            action="pirate_ended",
            payload={
                "anchor_body": previous_anchor,
                "strength": strength,
                "next_spawn_earliest_at": next_spawn_at.isoformat(),
                "at": tick_time.isoformat(),
            },
            event_time=tick_time.isoformat(),
        )

    def _parse_iso(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _pick_weighted_key(self, weights: dict[str, float]) -> str:
        total = sum(weights.values())
        threshold = self._rng.random() * total
        running = 0.0
        for key, weight in weights.items():
            running += weight
            if threshold <= running:
                return key
        return next(iter(weights))

    def _pick_station_by_policy(self, policy: str, size_class: str) -> str | None:
        """Return a home station ID for a newly built ship using the given spawn policy."""
        if policy == "any_random_station":
            station_ids = list(self._station_lookup.keys())
            if not station_ids:
                return None
            return self._rng.choice(station_ids)
        # Default / "compatible_random_station": restrict to stations that accept the size class.
        return self._pick_compatible_station(size_class)

    def _pick_compatible_station(self, size_class: str) -> str | None:
        station_ids = [sid for sid in self._station_lookup if self._station_accepts_size_class(sid, size_class)]
        if not station_ids:
            return None
        return self._rng.choice(station_ids)

    def _is_globally_interrupted(self, scenario: dict[str, Any] | None) -> bool:
        if not scenario or scenario.get("name") != "solar_flare":
            return False
        scope = scenario.get("scope", {"type": "global"})
        return scope.get("type", "global") == "global"

    def _build_event(
        self,
        state: dict[str, Any],
        scenario: dict[str, Any] | None,
        tick_time: datetime,
    ) -> dict[str, Any] | None:
        ship = self._pick_ship(scenario, tick_time)
        if not ship:
            return None

        src = ship["current_station_id"]
        dst = self._pick_destination(ship, src, scenario)
        if not dst:
            return None

        if self._is_scoped_interrupt(scenario, ship, src, dst):
            return None

        event = self._create_departure_event(
            ship_id=ship["ship_id"],
            source_station_id=src,
            destination_station_id=dst,
            departure_time=tick_time,
            scenario=scenario,
            ship_faction=str(ship.get("faction") or ""),
        )
        if event is None:
            return None
        return event

    def _create_departure_event(
        self,
        ship_id: str,
        source_station_id: str,
        destination_station_id: str,
        departure_time: datetime,
        scenario: dict[str, Any] | None,
        ship_faction: str | None = None,
    ) -> dict[str, Any] | None:
        event, self._event_counter, event_uid = create_departure_event(
            ship_id=ship_id,
            source_station_id=source_station_id,
            destination_station_id=destination_station_id,
            departure_time=departure_time,
            scenario=scenario,
            ship_faction=ship_faction,
            store=self._store,
            station_lookup=self._station_lookup,
            rng=self._rng,
            estimate_arrival=self.estimate_arrival,
            event_counter=self._event_counter,
        )
        if event is None:
            return None
        return event

    def _launch_all_merchants_at_startup(
        self,
        state: dict[str, Any],
        scenario: dict[str, Any] | None,
        tick_time: datetime,
    ) -> None:
        candidates = [
            ship
            for ship in self._store.list_available_ships()
            if ship.get("faction") == "merchant" and ship.get("current_station_id")
        ]
        self._rng.shuffle(candidates)

        for ship in candidates:
            src = ship["current_station_id"]
            dst = self._pick_destination(ship, src, scenario)
            if not dst:
                continue
            if self._is_scoped_interrupt(scenario, ship, src, dst):
                continue

            event = self._create_departure_event(
                ship_id=ship["ship_id"],
                source_station_id=src,
                destination_station_id=dst,
                departure_time=tick_time,
                scenario=scenario,
                ship_faction=str(ship.get("faction") or ""),
            )
            if event is None:
                continue

            self._apply_faults(event, state)
            self._persist_and_publish_event(event, state)

    def _persist_and_publish_event(self, event: dict[str, Any], state: dict[str, Any]) -> None:
        row_id = self._store.insert_departure(event)
        event["id"] = row_id
        self._store.trim_departures(state["retention_max_rows"])

        now_monotonic = time.monotonic()
        if now_monotonic >= self._next_db_size_check_at:
            db_max_size_mb = int(state.get("db_max_size_mb", 512))
            self._store.enforce_db_size_limit(max_db_size_bytes=db_max_size_mb * 1024 * 1024)
            self._next_db_size_check_at = now_monotonic + 5.0

        self._publish_event(event)
        self._last_event_uid = event["event_uid"]
        with self._metrics_lock:
            now = time.monotonic()
            self._departures_emitted += 1
            self._departure_timestamps.append(now)
            while self._departure_timestamps and (now - self._departure_timestamps[0]) > self._departures_window_seconds:
                self._departure_timestamps.popleft()

    def _pick_ship(self, scenario: dict[str, Any] | None, tick_time: datetime) -> dict[str, Any] | None:
        candidates = self._store.list_available_ships()
        runtime_snap = self._runtime.snapshot()
        merchant_idle_pause_seconds = int(runtime_snap.get("merchant_idle_pause_seconds", 120))
        candidates = [
            ship
            for ship in candidates
            if self._is_ship_departure_ready(ship, merchant_idle_pause_seconds, tick_time)
        ]
        if not candidates:
            return None

        fallback = self._store.list_available_ships()
        return select_ship(
            candidates=candidates,
            fallback_candidates=fallback,
            scenario=scenario,
            runtime_snap=runtime_snap,
            pirate_conf=self._lifecycle.get("pirate_activity") or {},
            rng=self._rng,
        )

    def _is_ship_departure_ready(
        self,
        ship: dict[str, Any],
        merchant_idle_pause_seconds: int,
        tick_time: datetime,
    ) -> bool:
        if ship.get("faction") != "merchant":
            return True

        updated_at = self._parse_iso(ship.get("updated_at"))
        if updated_at is None:
            return True

        earliest = updated_at + timedelta(seconds=merchant_idle_pause_seconds)
        return tick_time >= earliest

    def _pick_destination(
        self,
        ship: dict[str, Any],
        source_station_id: str,
        scenario: dict[str, Any] | None,
    ) -> str | None:
        return pick_destination(
            ship=ship,
            source_station_id=source_station_id,
            scenario=scenario,
            station_lookup=self._station_lookup,
            pirate_conf=self._lifecycle.get("pirate_activity") or {},
            pirate_state=self._runtime.snapshot().get("pirate_event"),
            rng=self._rng,
            station_accepts_size_class=self._station_accepts_size_class,
        )

    def _station_accepts_size_class(self, station_id: str, ship_size_class: str) -> bool:
        station = self._station_lookup.get(station_id)
        if not station:
            return False

        allowed = station.get("allowed_size_classes")
        if not isinstance(allowed, list) or not allowed:
            return True

        allowed_classes = {str(item).strip().lower() for item in allowed if str(item).strip()}
        return ship_size_class in allowed_classes

    def _is_scoped_interrupt(
        self,
        scenario: dict[str, Any] | None,
        ship: dict[str, Any],
        source: str,
        destination: str,
    ) -> bool:
        if not scenario or scenario.get("name") != "solar_flare":
            return False

        scope = scenario.get("scope", {"type": "global"})
        scope_type = scope.get("type", "global")
        if scope_type == "global":
            return True
        if scope_type == "stations":
            station_ids = set(scope.get("station_ids", []))
            return source in station_ids or destination in station_ids
        if scope_type == "factions":
            factions = set(scope.get("factions", []))
            return ship["faction"] in factions
        if scope_type == "ship_types":
            ship_types = set(scope.get("ship_types", []))
            return ship["ship_type"] in ship_types
        return False

    def _current_tick_time(self, state: dict[str, Any]) -> datetime:
        if self._sim_time is None:
            self._set_sim_time(state)
        return self._sim_time

    def _advance_sim_time(self, tick_time: datetime, interval_seconds: float) -> None:
        self._sim_time = tick_time + timedelta(seconds=interval_seconds)
        self._runtime.set_simulation_now(self._sim_time.isoformat())

    def estimate_arrival(self, departure_time: datetime, source: str, destination: str) -> datetime:
        if self._rng is None:
            self._ensure_rng(self._runtime.snapshot())

        src_group = self._distance_groups.get(source, 5)
        dst_group = self._distance_groups.get(destination, 5)
        hops = abs(src_group - dst_group)
        hours = (6 + (hops * 8) + self._rng.uniform(0.5, 12.0)) / self._ship_speed_multiplier
        return departure_time + timedelta(hours=hours)

    def _apply_faults(self, event: dict[str, Any], state: dict[str, Any]) -> None:
        apply_faults(
            event=event,
            state=state,
            rng=self._rng,
            last_event_uid=self._last_event_uid,
        )

    def _publish_event(self, event: dict[str, Any]) -> None:
        with self._subscribers_lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                continue
