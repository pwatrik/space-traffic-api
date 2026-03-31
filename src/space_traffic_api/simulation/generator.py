from __future__ import annotations

import json
import queue
import random
import threading
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from ..seed_data import station_distance_groups
from ..store import SQLiteStore
from .runtime import RuntimeState
from .scenarios import SCENARIO_DEFINITIONS


def build_effective_lifecycle_config(
    base_lifecycle: dict[str, Any],
    scenario_definition: dict[str, Any] | None,
    intensity: float,
) -> dict[str, Any]:
    """Merge base lifecycle config with scenario-specific modifiers."""

    effective = deepcopy(base_lifecycle)
    if not scenario_definition:
        return effective

    overrides = scenario_definition.get("lifecycle_overrides")
    if not isinstance(overrides, dict):
        return effective

    clamped_intensity = max(0.0, float(intensity))

    def _scale_multiplier(raw_multiplier: Any) -> float:
        multiplier = max(0.0, float(raw_multiplier))
        return max(0.0, 1.0 + ((multiplier - 1.0) * clamped_intensity))

    for channel, conf in overrides.items():
        if not isinstance(conf, dict):
            continue

        target = effective.setdefault(channel, {})
        if not isinstance(target, dict):
            continue

        if "enabled" in conf and clamped_intensity > 0:
            target["enabled"] = bool(conf["enabled"])

        if "base_probability_per_day_multiplier" in conf and "base_probability_per_day" in target:
            scale = _scale_multiplier(conf["base_probability_per_day_multiplier"])
            target["base_probability_per_day"] = max(0.0, float(target["base_probability_per_day"]) * scale)

        if "max_probability_per_day_multiplier" in conf and "max_probability_per_day" in target:
            scale = _scale_multiplier(conf["max_probability_per_day_multiplier"])
            target["max_probability_per_day"] = max(0.0, float(target["max_probability_per_day"]) * scale)

        if "base_builds_per_day_multiplier" in conf and "base_builds_per_day" in target:
            scale = _scale_multiplier(conf["base_builds_per_day_multiplier"])
            target["base_builds_per_day"] = max(0.0, float(target["base_builds_per_day"]) * scale)

        if "max_losses_per_event_add" in conf and "max_losses_per_event" in target:
            add = int(round(float(conf["max_losses_per_event_add"]) * clamped_intensity))
            target["max_losses_per_event"] = max(1, int(target["max_losses_per_event"]) + add)

        if channel == "war_impact":
            raw = conf.get("faction_loss_multiplier_overrides")
            if isinstance(raw, dict):
                current = target.get("faction_loss_multiplier")
                if isinstance(current, dict):
                    merged = dict(current)
                    for faction, faction_multiplier in raw.items():
                        key = str(faction).strip().lower()
                        if not key:
                            continue
                        scale = _scale_multiplier(faction_multiplier)
                        merged[key] = max(0.0, float(merged.get(key, 1.0)) * scale)
                    target["faction_loss_multiplier"] = merged

        if channel == "build_queue" and clamped_intensity > 0:
            raw = conf.get("faction_distribution")
            if isinstance(raw, dict) and raw:
                normalized: dict[str, float] = {}
                for faction, weight in raw.items():
                    if not isinstance(weight, (int, float)) or float(weight) <= 0:
                        continue
                    key = str(faction).strip().lower()
                    if key:
                        normalized[key] = float(weight)
                if normalized:
                    target["faction_distribution"] = normalized

    return effective


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

        self._rng: random.Random | None = None
        self._sim_time: datetime | None = None
        self._event_counter = 0
        self._last_event_uid = ""
        self._next_db_size_check_at = 0.0
        self._next_ship_sequence = self._store.max_ship_sequence() + 1
        self._age_update_accumulator_days: float = 0.0

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

    def run(self) -> None:
        while not self._stop_event.is_set():
            state = self._runtime.snapshot()
            self._ensure_rng(state)

            scenario = state.get("active_scenario")
            effective_min, effective_max = self._effective_rate_bounds(state, scenario)
            rate = self._rng.randint(effective_min, effective_max)
            interval_seconds = max(0.2, 60.0 / float(rate))
            tick_time = self._current_tick_time(state)

            arrived_ships = self._store.complete_ship_arrivals_with_details(tick_time.isoformat())
            self._apply_lifecycle(
                interval_seconds=interval_seconds,
                tick_time=tick_time,
                scenario=scenario,
                arrived_ships=arrived_ships,
            )

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
            self._store.increment_ship_age(age_update_days)

        self._manage_pirate_activity(
            tick_time=tick_time,
            elapsed_days=elapsed_days,
            lifecycle_conf=effective_lifecycle,
        )
        self._apply_pirate_arrival_effects(
            tick_time=tick_time,
            lifecycle_conf=effective_lifecycle,
            arrived_ships=arrived_ships,
        )

        active_ships = self._store.list_active_ships_for_lifecycle()
        if not active_ships:
            return

        self._run_decommission(
            active_ships=active_ships,
            elapsed_days=elapsed_days,
            tick_time=tick_time,
            lifecycle_conf=effective_lifecycle,
        )
        active_ships = self._store.list_active_ships_for_lifecycle()
        if not active_ships:
            return

        self._run_war_impact(
            active_ships=active_ships,
            elapsed_days=elapsed_days,
            tick_time=tick_time,
            lifecycle_conf=effective_lifecycle,
        )
        active_ships = self._store.list_active_ships_for_lifecycle()
        self._run_build_queue(
            active_ships=active_ships,
            elapsed_days=elapsed_days,
            tick_time=tick_time,
            lifecycle_conf=effective_lifecycle,
        )

    def _manage_pirate_activity(
        self,
        tick_time: datetime,
        elapsed_days: float,
        lifecycle_conf: dict[str, Any],
    ) -> None:
        conf = lifecycle_conf.get("pirate_activity") or {}
        if not conf.get("enabled", False):
            return

        state = self._runtime.snapshot().get("pirate_event")
        if not isinstance(state, dict):
            state = {}

        active = bool(state.get("active", False))
        strength = float(state.get("strength") or 0.0)
        strength_end_threshold = float(conf.get("strength_end_threshold", 0.5))

        if active:
            decay_per_day = float(conf.get("ambient_strength_decay_per_day", 0.0))
            if decay_per_day > 0 and elapsed_days > 0:
                next_strength = max(0.0, strength - (decay_per_day * elapsed_days))
                if abs(next_strength - strength) >= 1e-9:
                    strength = next_strength
                    state["strength"] = strength
                    state["updated_at"] = tick_time.isoformat()
                    self._runtime.set_pirate_event_state(state)

            if strength <= strength_end_threshold:
                self._end_pirate_event(state=state, conf=conf, tick_time=tick_time)
            return

        next_spawn_raw = state.get("next_spawn_earliest_at")
        next_spawn_at = self._parse_iso(next_spawn_raw)
        if next_spawn_at and tick_time < next_spawn_at:
            return

        allowed_anchors = [str(x) for x in conf.get("allowed_anchors", []) if str(x).strip()]
        if not allowed_anchors:
            return

        previous_anchor = state.get("previous_anchor_body")
        candidates = [anchor for anchor in allowed_anchors if anchor != previous_anchor]
        if not candidates:
            candidates = allowed_anchors
        anchor = self._rng.choice(candidates)
        affected_station_ids = sorted(
            [
                station_id
                for station_id, station in self._station_lookup.items()
                if str(station.get("parent_body") or "") == anchor
            ]
        )

        strength_start = float(conf.get("strength_start", 1.0))
        next_state = {
            "active": True,
            "anchor_body": anchor,
            "previous_anchor_body": previous_anchor,
            "strength": strength_start,
            "started_at": tick_time.isoformat(),
            "ended_at": None,
            "next_spawn_earliest_at": None,
            "affected_station_ids": affected_station_ids,
            "updated_at": tick_time.isoformat(),
        }
        self._runtime.set_pirate_event_state(next_state)
        self._store.insert_control_event(
            event_type="lifecycle",
            action="pirate_started",
            payload={
                "anchor_body": anchor,
                "strength": strength_start,
                "affected_station_ids": affected_station_ids,
                "at": tick_time.isoformat(),
            },
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

        state = self._runtime.snapshot().get("pirate_event")
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
                if self._store.deactivate_ship(ship_id=ship_id, status="destroyed", current_station_id=destination):
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
        )

        threshold = float(conf.get("strength_end_threshold", 0.5))
        if next_strength <= threshold:
            self._end_pirate_event(state=state, conf=conf, tick_time=tick_time)

    def _end_pirate_event(self, state: dict[str, Any], conf: dict[str, Any], tick_time: datetime) -> None:
        previous_anchor = state.get("anchor_body")
        strength = float(state.get("strength") or 0.0)
        min_days = float(conf.get("respawn_min_days", 10.0))
        max_days = float(conf.get("respawn_max_days", 30.0))
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
        )

    def _parse_iso(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _run_decommission(
        self,
        active_ships: list[dict[str, Any]],
        elapsed_days: float,
        tick_time: datetime,
        lifecycle_conf: dict[str, Any],
    ) -> None:
        conf = lifecycle_conf.get("decommission") or {}
        if not conf.get("enabled", False):
            return

        base = float(conf.get("base_probability_per_day", 0.0))
        if base <= 0:
            return

        soft_limit_days = float(conf.get("age_years_soft_limit", 18.0)) * 365.0
        accel = float(conf.get("age_acceleration_per_year", 0.0))
        max_probability_per_day = float(conf.get("max_probability_per_day", base))

        retired_ids: list[str] = []
        for ship in active_ships:
            age_days = float(ship.get("ship_age_days") or 0.0)
            years_over = max(0.0, (age_days - soft_limit_days) / 365.0)
            per_day = min(max_probability_per_day, base + (years_over * accel))
            per_tick = min(1.0, max(0.0, per_day * elapsed_days))
            if self._rng.random() >= per_tick:
                continue

            ship_id = ship["ship_id"]
            if self._store.deactivate_ship(ship_id=ship_id, status="decommissioned", current_station_id=ship.get("current_station_id")):
                retired_ids.append(ship_id)

        if retired_ids:
            self._store.insert_control_event(
                event_type="lifecycle",
                action="decommissioned",
                payload={
                    "ship_ids": retired_ids,
                    "count": len(retired_ids),
                    "at": tick_time.isoformat(),
                },
            )

    def _run_war_impact(
        self,
        active_ships: list[dict[str, Any]],
        elapsed_days: float,
        tick_time: datetime,
        lifecycle_conf: dict[str, Any],
    ) -> None:
        conf = lifecycle_conf.get("war_impact") or {}
        if not conf.get("enabled", False):
            return

        base = float(conf.get("base_probability_per_day", 0.0))
        if base <= 0:
            return

        faction_multiplier = conf.get("faction_loss_multiplier") or {}
        max_losses = int(conf.get("max_losses_per_event", 1))
        if max_losses < 1:
            return

        weighted_candidates: list[dict[str, Any]] = []
        for ship in active_ships:
            weight = float(faction_multiplier.get(ship.get("faction"), 1.0))
            if weight <= 0:
                continue
            chance = max(0.0, min(1.0, base * weight * elapsed_days))
            if self._rng.random() < chance:
                weighted_candidates.append(ship)

        if not weighted_candidates:
            return

        self._rng.shuffle(weighted_candidates)
        selected = weighted_candidates[:max_losses]
        destroyed: list[str] = []
        for ship in selected:
            ship_id = ship["ship_id"]
            if self._store.deactivate_ship(ship_id=ship_id, status="destroyed", current_station_id=ship.get("current_station_id")):
                destroyed.append(ship_id)

        if destroyed:
            self._store.insert_control_event(
                event_type="lifecycle",
                action="war_losses",
                payload={
                    "ship_ids": destroyed,
                    "count": len(destroyed),
                    "at": tick_time.isoformat(),
                },
            )

    def _run_build_queue(
        self,
        active_ships: list[dict[str, Any]],
        elapsed_days: float,
        tick_time: datetime,
        lifecycle_conf: dict[str, Any],
    ) -> None:
        conf = lifecycle_conf.get("build_queue") or {}
        if not conf.get("enabled", False):
            return

        base_builds_per_day = float(conf.get("base_builds_per_day", 0.0))
        max_builds_per_day = int(conf.get("max_builds_per_day", 1))
        if base_builds_per_day <= 0 or max_builds_per_day < 1:
            return

        expected_builds = base_builds_per_day * elapsed_days
        if expected_builds <= 0:
            return

        builds = int(expected_builds)
        if self._rng.random() < (expected_builds - builds):
            builds += 1

        tick_cap = max(1, int(max_builds_per_day * elapsed_days) + 1)
        builds = min(builds, tick_cap)
        if builds < 1:
            return

        faction_weights_raw = conf.get("faction_distribution") or {}
        faction_weights = {k: float(v) for k, v in faction_weights_raw.items() if float(v) > 0}
        if not faction_weights:
            return

        spawn_policy = str(conf.get("spawn_policy", "compatible_random_station")).strip().lower()

        ship_types = self._ship_generation.get("ship_types") or []
        cargo_types = self._ship_generation.get("cargo_types") or []
        naming = self._ship_generation.get("naming") or {}
        adjectives = naming.get("adjectives") or ["Solar"]
        nouns = naming.get("nouns") or ["Pioneer"]
        captain_first = naming.get("captain_first") or ["Alex"]
        captain_last = naming.get("captain_last") or ["Voss"]

        if not ship_types or not cargo_types:
            return

        ship_types_by_faction: dict[str, list[dict[str, Any]]] = {}
        for ship_type in ship_types:
            ship_types_by_faction.setdefault(ship_type.get("faction"), []).append(ship_type)

        built_ship_ids: list[str] = []
        for _ in range(builds):
            faction = self._pick_weighted_key(faction_weights)
            candidates = ship_types_by_faction.get(faction) or ship_types
            choice = self._rng.choice(candidates)
            size_class = str(choice.get("size_class") or "medium").strip().lower()
            home_station_id = self._pick_station_by_policy(spawn_policy, size_class)
            if not home_station_id:
                continue

            ship_id = f"SHIP-{self._next_ship_sequence:04d}"
            self._next_ship_sequence += 1
            ship = {
                "id": ship_id,
                "name": f"{self._rng.choice(adjectives)} {self._rng.choice(nouns)}",
                "faction": str(choice.get("faction") or faction),
                "ship_type": str(choice.get("name") or "Auxiliary"),
                "size_class": size_class,
                "displacement_million_m3": round(
                    self._rng.uniform(
                        float(choice.get("displacement_min_million_m3", 0.8)),
                        float(choice.get("displacement_max_million_m3", 22.0)),
                    ),
                    3,
                ),
                "home_station_id": home_station_id,
                "captain_name": f"{self._rng.choice(captain_first)} {self._rng.choice(captain_last)}",
                "cargo": self._rng.choice(cargo_types),
            }
            self._store.seed_ships([ship])
            self._store.seed_ship_states([ship])
            self._ship_lookup[ship_id] = ship
            built_ship_ids.append(ship_id)

        if built_ship_ids:
            self._store.insert_control_event(
                event_type="lifecycle",
                action="ships_built",
                payload={
                    "ship_ids": built_ship_ids,
                    "count": len(built_ship_ids),
                    "at": tick_time.isoformat(),
                },
            )

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
        ship = self._pick_ship(scenario)
        if not ship:
            return None

        src = ship["current_station_id"]
        dst = self._pick_destination(ship, src, scenario)
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

        pirate_conf = self._lifecycle.get("pirate_activity") or {}
        pirate_state = self._runtime.snapshot().get("pirate_event")
        pirate_active = bool(isinstance(pirate_state, dict) and pirate_state.get("active"))
        idle_bounty_multiplier = max(
            0.0,
            float(pirate_conf.get("bounty_hunter_idle_departure_multiplier", 0.2)),
        )
        active_bounty_multiplier = max(
            0.0,
            float(pirate_conf.get("bounty_hunter_active_departure_multiplier", 6.0)),
        )
        bounty_multiplier = active_bounty_multiplier if pirate_active else idle_bounty_multiplier

        definition = SCENARIO_DEFINITIONS.get(scenario["name"], {}) if scenario else {}
        faction_weights = definition.get("faction_weights")

        if faction_weights:
            candidates = [s for s in candidates if s["faction"] in faction_weights]
            if not candidates:
                fallback = self._store.list_available_ships()
                if not fallback:
                    return None
                candidates = fallback

        cumulative: list[float] = []
        running = 0.0
        for ship in candidates:
            faction = str(ship.get("faction") or "")
            base_weight = float(faction_weights.get(faction, 1.0)) if faction_weights else 1.0
            multiplier = bounty_multiplier if faction == "bounty_hunter" else 1.0
            effective_weight = max(0.0, base_weight * multiplier)
            running += effective_weight
            cumulative.append(running)

        if running <= 0:
            return self._rng.choice(candidates)

        pick = self._rng.random() * running
        for idx, threshold in enumerate(cumulative):
            if pick <= threshold:
                return candidates[idx]
        return candidates[-1]

    def _pick_destination(
        self,
        ship: dict[str, Any],
        source_station_id: str,
        scenario: dict[str, Any] | None,
    ) -> str | None:
        ship_size_class = str(ship.get("size_class") or "medium").strip().lower()

        station_ids = list(self._station_lookup.keys())
        if source_station_id in station_ids:
            station_ids.remove(source_station_id)

        station_ids = [sid for sid in station_ids if self._station_accepts_size_class(sid, ship_size_class)]
        if not station_ids:
            return None

        pirate_conf = self._lifecycle.get("pirate_activity") or {}
        pirate_state = self._runtime.snapshot().get("pirate_event")
        is_bounty_hunter = str(ship.get("faction") or "") == "bounty_hunter"
        if is_bounty_hunter and isinstance(pirate_state, dict) and pirate_state.get("active"):
            affected = [sid for sid in pirate_state.get("affected_station_ids", []) if sid in station_ids]
            if affected:
                response_bias = min(1.0, max(0.0, float(pirate_conf.get("bounty_hunter_response_bias", 0.9))))
                if self._rng.random() < response_bias:
                    return self._rng.choice(affected)

        if scenario and scenario.get("name") == "shortage":
            keywords = SCENARIO_DEFINITIONS["shortage"].get("preferred_source_keywords", [])
            preferred = [sid for sid in station_ids if any(key in sid for key in keywords)]
            if preferred and self._rng.random() < 0.65:
                return self._rng.choice(preferred)

        return self._rng.choice(station_ids)

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
