from __future__ import annotations

import json
import queue
import random
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from ..seed_data import station_distance_groups
from ..store import SQLiteStore
from .runtime import RuntimeState
from .scenarios import SCENARIO_DEFINITIONS


class DepartureGenerator(threading.Thread):
    def __init__(
        self,
        store: SQLiteStore,
        runtime: RuntimeState,
        stations: list[dict[str, Any]],
        ships: list[dict[str, Any]],
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

        self._rng: random.Random | None = None
        self._sim_time: datetime | None = None
        self._event_counter = 0
        self._last_event_uid = ""
        self._next_db_size_check_at = 0.0

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

    def run(self) -> None:
        while not self._stop_event.is_set():
            state = self._runtime.snapshot()
            self._ensure_rng(state)

            scenario = state.get("active_scenario")
            effective_min, effective_max = self._effective_rate_bounds(state, scenario)
            rate = self._rng.randint(effective_min, effective_max)
            interval_seconds = max(0.2, 60.0 / float(rate))
            tick_time = self._current_tick_time(state)

            self._store.complete_ship_arrivals(tick_time.isoformat())

            if self._is_globally_interrupted(scenario):
                self._advance_sim_time(state, tick_time, interval_seconds)
                time.sleep(min(1.0, interval_seconds))
                continue

            event = self._build_event(state, scenario, tick_time)
            if event is None:
                self._advance_sim_time(state, tick_time, interval_seconds)
                time.sleep(min(1.0, interval_seconds))
                continue

            self._apply_faults(event, state)

            if "delayed_insert" in event.get("fault_flags", []):
                time.sleep(1.5)

            row_id = self._store.insert_departure(event)
            event["id"] = row_id
            self._store.trim_departures(state["retention_max_rows"])

            now_monotonic = time.monotonic()
            if now_monotonic >= self._next_db_size_check_at:
                db_max_size_mb = int(state.get("db_max_size_mb", 512))
                self._store.enforce_db_size_limit(max_db_size_bytes=db_max_size_mb * 1024 * 1024)
                self._next_db_size_check_at = now_monotonic + 5.0

            self._publish_event(event)

            self._advance_sim_time(state, tick_time, interval_seconds)

            time.sleep(interval_seconds)

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

    def _set_sim_time(self, state: dict[str, Any]) -> None:
        raw = state.get("deterministic_start_time", "2150-01-01T00:00:00Z")
        try:
            self._sim_time = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            self._sim_time = datetime.now(UTC)

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
        ship = self._pick_ship(scenario)
        if not ship:
            return None

        src = ship["current_station_id"]
        dst = self._pick_destination(src, scenario)
        if not dst:
            return None

        if self._is_scoped_interrupt(scenario, ship, src, dst):
            return None

        departure_time = tick_time
        eta = self._estimate_arrival(departure_time, src, dst)

        departed = self._store.begin_ship_transit(
            ship_id=ship["ship_id"],
            source_station_id=src,
            destination_station_id=dst,
            departure_time=departure_time.isoformat(),
            est_arrival_time=eta.isoformat(),
        )
        if not departed:
            return None

        self._event_counter += 1
        event_uid = f"EVT-{self._event_counter:09d}-{self._rng.getrandbits(32):08x}"
        self._last_event_uid = event_uid

        payload = {
            "event_uid": event_uid,
            "departure_time": departure_time.isoformat(),
            "ship_id": ship["ship_id"],
            "source_station_id": src,
            "destination_station_id": dst,
            "est_arrival_time": eta.isoformat(),
            "scenario": scenario["name"] if scenario else "baseline",
        }

        return {
            **payload,
            "fault_flags": [],
            "malformed": False,
            "payload_json": json.dumps(payload),
        }

    def _pick_ship(self, scenario: dict[str, Any] | None) -> dict[str, Any] | None:
        candidates = self._store.list_available_ships()
        if not candidates:
            return None
        if not scenario:
            return self._rng.choice(candidates)

        definition = SCENARIO_DEFINITIONS.get(scenario["name"], {})
        weights = definition.get("faction_weights")
        if not weights:
            return self._rng.choice(candidates)

        candidates = [s for s in candidates if s["faction"] in weights]
        if not candidates:
            fallback = self._store.list_available_ships()
            if not fallback:
                return None
            return self._rng.choice(fallback)

        cumulative: list[float] = []
        running = 0.0
        for ship in candidates:
            running += float(weights.get(ship["faction"], 0.01))
            cumulative.append(running)

        pick = self._rng.random() * running
        for idx, threshold in enumerate(cumulative):
            if pick <= threshold:
                return candidates[idx]
        return candidates[-1]

    def _pick_destination(self, source_station_id: str, scenario: dict[str, Any] | None) -> str | None:
        station_ids = list(self._station_lookup.keys())
        if source_station_id in station_ids:
            station_ids.remove(source_station_id)
        if not station_ids:
            return None

        if scenario and scenario.get("name") == "shortage":
            keywords = SCENARIO_DEFINITIONS["shortage"].get("preferred_source_keywords", [])
            preferred = [sid for sid in station_ids if any(key in sid for key in keywords)]
            if preferred and self._rng.random() < 0.65:
                return self._rng.choice(preferred)

        return self._rng.choice(station_ids)

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
        if state.get("deterministic_mode"):
            if self._sim_time is None:
                self._set_sim_time(state)
            return self._sim_time
        return datetime.now(UTC)

    def _advance_sim_time(self, state: dict[str, Any], tick_time: datetime, interval_seconds: float) -> None:
        if state.get("deterministic_mode"):
            self._sim_time = tick_time + timedelta(seconds=interval_seconds)

    def _estimate_arrival(self, departure_time: datetime, source: str, destination: str) -> datetime:
        src_group = self._distance_groups.get(source, 5)
        dst_group = self._distance_groups.get(destination, 5)
        hops = abs(src_group - dst_group)
        hours = 6 + (hops * 8) + self._rng.uniform(0.5, 12.0)
        return departure_time + timedelta(hours=hours)

    def _apply_faults(self, event: dict[str, Any], state: dict[str, Any]) -> None:
        active_faults = state.get("active_faults", {}) or {}
        for fault_name, conf in active_faults.items():
            rate = float(conf.get("rate", 0.0))
            if self._rng.random() > rate:
                continue

            flags = event.setdefault("fault_flags", [])
            flags.append(fault_name)

            if fault_name == "missing_field":
                event["destination_station_id"] = None
            elif fault_name == "invalid_enum":
                raw = json.loads(event["payload_json"])
                raw["route_priority"] = "totally_invalid"
                event["payload_json"] = json.dumps(raw)
            elif fault_name == "out_of_order_timestamp":
                dt = datetime.fromisoformat(event["departure_time"]) - timedelta(minutes=self._rng.randint(5, 120))
                event["departure_time"] = dt.isoformat()
            elif fault_name == "malformed_payload":
                event["payload_json"] = "{malformed-json"
                event["malformed"] = True
            elif fault_name == "duplicate_event_uid" and self._last_event_uid:
                event["event_uid"] = self._last_event_uid
            elif fault_name == "synthetic_error":
                event["ship_id"] = None
                event["source_station_id"] = None
                event["destination_station_id"] = None
                event["malformed"] = True
            elif fault_name == "delayed_insert":
                pass

        if event.get("payload_json") and not event.get("malformed"):
            try:
                parsed = json.loads(event["payload_json"])
                parsed["fault_flags"] = event.get("fault_flags", [])
                event["payload_json"] = json.dumps(parsed)
            except json.JSONDecodeError:
                event["malformed"] = True

    def _publish_event(self, event: dict[str, Any]) -> None:
        with self._subscribers_lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                continue
