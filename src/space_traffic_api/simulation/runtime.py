from __future__ import annotations

import queue
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from ..config import AppConfig
from ..store import SQLiteStore
from .faults import FAULT_DEFINITIONS, normalize_fault_request
from .scenarios import SCENARIO_DEFINITIONS


def _parse_deterministic_start(raw: str | None) -> datetime:
    """Parse and normalize a deterministic start time string, falling back to UTC now."""
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


class RuntimeState:
    def __init__(self, config: AppConfig, store: SQLiteStore):
        self._lock = threading.Lock()
        self._store = store
        self._subscribers: list[queue.Queue[dict[str, Any]]] = []
        self._subscribers_lock = threading.Lock()
        self._state: dict[str, Any] = {
            "base_min_events_per_minute": config.base_min_events_per_minute,
            "base_max_events_per_minute": config.base_max_events_per_minute,
            "deterministic_mode": config.deterministic_mode,
            "deterministic_seed": config.deterministic_seed,
            "deterministic_start_time": config.deterministic_start_time,
            "retention_max_rows": config.retention_max_rows,
            "db_max_size_mb": config.db_max_size_mb,
            "merchant_idle_pause_seconds": config.merchant_idle_pause_seconds,
            "simulation_time_scale": config.simulation_time_scale,
            "economy_preference_weight": config.economy_preference_weight,
            "economy_drift_magnitude": config.economy_drift_magnitude,
            "economy_departure_impact_magnitude": config.economy_departure_impact_magnitude,
            "simulation_now": _parse_deterministic_start(config.deterministic_start_time).isoformat(),
            "active_scenario": None,
            "active_faults": {},
                       "pirate_spawn_probability_per_day": None,
                       "pirate_strength_start": None,
                       "pirate_strength_end_threshold": None,
                       "pirate_strength_decay_per_day": None,
                       "pirate_respawn_min_days": None,
                       "pirate_respawn_max_days": None,
            "pirate_event": {
                "active": False,
                "anchor_body": None,
                "previous_anchor_body": None,
                "strength": 0.0,
                "started_at": None,
                "ended_at": None,
                "next_spawn_earliest_at": None,
                "affected_station_ids": [],
            },
            "last_reset_at": None,
        }

        persisted = self._store.get_control_state("runtime")
        if persisted:
            self._state.update(persisted)
        if "pirate_event" not in self._state or not isinstance(self._state["pirate_event"], dict):
            self._state["pirate_event"] = {
                "active": False,
                "anchor_body": None,
                "previous_anchor_body": None,
                "strength": 0.0,
                "started_at": None,
                "ended_at": None,
                "next_spawn_earliest_at": None,
                "affected_station_ids": [],
            }

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1000)
        with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[dict[str, Any]]) -> None:
        with self._subscribers_lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def subscriber_metrics(self) -> dict[str, int]:
        with self._subscribers_lock:
            subscribers = list(self._subscribers)
        backlogs = [q.qsize() for q in subscribers]
        return {
            "subscribers": len(subscribers),
            "backlog_total": sum(backlogs),
            "backlog_max": max(backlogs) if backlogs else 0,
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._expire_unlocked()
            return dict(self._state)

    def patch_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "base_min_events_per_minute",
            "base_max_events_per_minute",
            "deterministic_mode",
            "deterministic_seed",
            "deterministic_start_time",
            "retention_max_rows",
            "db_max_size_mb",
            "merchant_idle_pause_seconds",
            "simulation_time_scale",
                        "economy_preference_weight",
                        "economy_drift_magnitude",
                        "economy_departure_impact_magnitude",
                        "pirate_spawn_probability_per_day",
                        "pirate_strength_start",
                        "pirate_strength_end_threshold",
                        "pirate_strength_decay_per_day",
                        "pirate_respawn_min_days",
                        "pirate_respawn_max_days",
        }

        with self._lock:
            for key, value in patch.items():
                if key not in allowed:
                    continue
                self._state[key] = value

            if self._state["base_min_events_per_minute"] < 1:
                self._state["base_min_events_per_minute"] = 1
            if self._state["base_max_events_per_minute"] < self._state["base_min_events_per_minute"]:
                self._state["base_max_events_per_minute"] = self._state["base_min_events_per_minute"]
            if self._state["retention_max_rows"] < 100:
                self._state["retention_max_rows"] = 100
            if self._state["db_max_size_mb"] < 50:
                self._state["db_max_size_mb"] = 50
            pause_seconds = int(self._state.get("merchant_idle_pause_seconds", 120))
            self._state["merchant_idle_pause_seconds"] = max(0, pause_seconds)
            try:
                scale = float(self._state.get("simulation_time_scale", 1.0))
            except (TypeError, ValueError):
                scale = 1.0
            self._state["simulation_time_scale"] = max(0.1, scale)

            try:
                econ_weight = float(self._state.get("economy_preference_weight", 0.15))
            except (TypeError, ValueError):
                econ_weight = 0.15
            self._state["economy_preference_weight"] = max(0.0, min(1.0, econ_weight))

            try:
                drift_mag = float(self._state.get("economy_drift_magnitude", 1.0))
            except (TypeError, ValueError):
                drift_mag = 1.0
            self._state["economy_drift_magnitude"] = max(0.1, min(5.0, drift_mag))

            try:
                departure_mag = float(self._state.get("economy_departure_impact_magnitude", 0.012))
            except (TypeError, ValueError):
                departure_mag = 0.012
            self._state["economy_departure_impact_magnitude"] = max(0.001, min(0.2, departure_mag))

            def _to_float(value: Any) -> float | None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None

            if self._state.get("pirate_spawn_probability_per_day") is not None:
                _val = _to_float(self._state["pirate_spawn_probability_per_day"])
                if _val is not None:
                    self._state["pirate_spawn_probability_per_day"] = max(0.0, min(1.0, _val))
            if self._state.get("pirate_strength_start") is not None:
                _val = _to_float(self._state["pirate_strength_start"])
                if _val is not None:
                    self._state["pirate_strength_start"] = max(0.1, _val)
            if self._state.get("pirate_strength_end_threshold") is not None:
                _val = _to_float(self._state["pirate_strength_end_threshold"])
                if _val is not None:
                    self._state["pirate_strength_end_threshold"] = max(0.01, _val)
            if self._state.get("pirate_strength_decay_per_day") is not None:
                _val = _to_float(self._state["pirate_strength_decay_per_day"])
                if _val is not None:
                    self._state["pirate_strength_decay_per_day"] = max(0.0, _val)
            if self._state.get("pirate_respawn_min_days") is not None:
                _val = _to_float(self._state["pirate_respawn_min_days"])
                if _val is not None:
                    self._state["pirate_respawn_min_days"] = max(0.1, _val)
            if self._state.get("pirate_respawn_max_days") is not None:
                _val = _to_float(self._state["pirate_respawn_max_days"])
                if _val is not None:
                    self._state["pirate_respawn_max_days"] = max(0.1, _val)
            if (
                self._state.get("pirate_respawn_min_days") is not None
                and self._state.get("pirate_respawn_max_days") is not None
                and self._state["pirate_respawn_max_days"] < self._state["pirate_respawn_min_days"]
            ):
                self._state["pirate_respawn_max_days"] = self._state["pirate_respawn_min_days"]
            self._persist_unlocked()
            self._emit_control_event_unlocked("config", "patched", {"config": dict(self._state)})
            return dict(self._state)

    def activate_scenario(self, request: dict[str, Any]) -> dict[str, Any]:
        name = request.get("name", "").strip().lower()
        if name not in SCENARIO_DEFINITIONS:
            raise ValueError(f"unknown scenario '{name}'")

        intensity = float(request.get("intensity", 1.0))
        intensity = max(0.0, min(5.0, intensity))
        duration_seconds = max(1, int(request.get("duration_seconds", 300)))
        scope = request.get("scope", {"type": "global"})

        with self._lock:
            now = self._clock_now_unlocked()
            ends_at = now + timedelta(seconds=duration_seconds)
            self._state["active_scenario"] = {
                "name": name,
                "intensity": intensity,
                "duration_seconds": duration_seconds,
                "scope": scope,
                "started_at": now.isoformat(),
                "ends_at": ends_at.isoformat(),
            }
            self._persist_unlocked()
            self._emit_control_event_unlocked("scenario", "activated", {"scenario": dict(self._state["active_scenario"])})
            return dict(self._state["active_scenario"])

    def deactivate_scenario(self) -> None:
        with self._lock:
            prior = self._state.get("active_scenario")
            self._state["active_scenario"] = None
            self._persist_unlocked()
            self._emit_control_event_unlocked("scenario", "deactivated", {"previous": prior})

    def activate_faults(self, request: dict[str, Any]) -> dict[str, Any]:
        faults = request.get("faults", {})
        if not isinstance(faults, dict):
            raise ValueError("faults must be an object keyed by fault name")

        with self._lock:
            active_faults: dict[str, Any] = dict(self._state.get("active_faults", {}))
            now = self._clock_now_unlocked()

            for name, raw in faults.items():
                if name not in FAULT_DEFINITIONS:
                    raise ValueError(f"unknown fault '{name}'")
                conf = normalize_fault_request(name, raw or {})
                ends_at = None
                if conf["duration_seconds"] > 0:
                    ends_at = (now + timedelta(seconds=conf["duration_seconds"])).isoformat()
                active_faults[name] = {
                    "rate": conf["rate"],
                    "scope": conf["scope"],
                    "duration_seconds": conf["duration_seconds"],
                    "started_at": now.isoformat(),
                    "ends_at": ends_at,
                }

            self._state["active_faults"] = active_faults
            self._persist_unlocked()
            self._emit_control_event_unlocked("fault", "activated", {"faults": dict(active_faults)})
            return dict(active_faults)

    def deactivate_faults(self, names: list[str] | None = None) -> dict[str, Any]:
        with self._lock:
            active = dict(self._state.get("active_faults", {}))
            if not names:
                active = {}
            else:
                for name in names:
                    active.pop(name, None)
            self._state["active_faults"] = active
            self._persist_unlocked()
            self._emit_control_event_unlocked("fault", "deactivated", {"active_faults": dict(active), "names": names or []})
            return dict(active)

    def reset(self, seed: int | None = None) -> dict[str, Any]:
        with self._lock:
            now = self._clock_now_unlocked()
            if seed is not None:
                self._state["deterministic_seed"] = int(seed)
            pirate_event = self._state.get("pirate_event", {})
            if isinstance(pirate_event, dict):
                self._state["pirate_event"] = {
                    **pirate_event,
                    "active": False,
                    "anchor_body": None,
                    "strength": 0.0,
                    "started_at": None,
                    "ended_at": now.isoformat(),
                    "next_spawn_earliest_at": None,
                    "affected_station_ids": [],
                }
            deterministic_start = self._state.get("deterministic_start_time")
            simulation_now_dt = _parse_deterministic_start(deterministic_start)
            self._state["simulation_now"] = simulation_now_dt.isoformat()
            self._state["last_reset_at"] = now.isoformat()
            self._persist_unlocked()
            self._emit_control_event_unlocked(
                "control",
                "reset",
                {
                    "seed": self._state["deterministic_seed"],
                    "deterministic_mode": self._state["deterministic_mode"],
                    "last_reset_at": self._state["last_reset_at"],
                },
            )
            return dict(self._state)

    def list_control_events(self, since_id: int | None, limit: int, order: str) -> list[dict[str, Any]]:
        return self._store.list_control_events(since_id=since_id, limit=limit, order=order)

    def set_pirate_event_state(self, pirate_event: dict[str, Any]) -> None:
        with self._lock:
            self._state["pirate_event"] = dict(pirate_event)
            self._persist_unlocked()

    def set_simulation_now(self, now_iso: str) -> None:
        with self._lock:
            self._state["simulation_now"] = now_iso

    def _persist_unlocked(self) -> None:
        self._store.set_control_state("runtime", self._state)

    def _expire_unlocked(self) -> None:
        now = self._clock_now_unlocked()
        scenario = self._state.get("active_scenario")
        scenario_dirty = False
        if scenario and scenario.get("ends_at"):
            try:
                if datetime.fromisoformat(scenario["ends_at"]) <= now:
                    prior = dict(scenario)
                    self._state["active_scenario"] = None
                    scenario_dirty = True
                    self._emit_control_event_unlocked("scenario", "expired", {"previous": prior})
            except ValueError:
                prior = dict(scenario)
                self._state["active_scenario"] = None
                scenario_dirty = True
                self._emit_control_event_unlocked("scenario", "expired", {"previous": prior})

        if scenario_dirty:
            self._persist_unlocked()

        active_faults = dict(self._state.get("active_faults", {}))
        dirty = False
        for fault_name, conf in list(active_faults.items()):
            ends_at = conf.get("ends_at")
            if ends_at:
                try:
                    if datetime.fromisoformat(ends_at) <= now:
                        expired = dict(conf)
                        active_faults.pop(fault_name, None)
                        dirty = True
                        self._emit_control_event_unlocked("fault", "expired", {"name": fault_name, "fault": expired})
                except ValueError:
                    expired = dict(conf)
                    active_faults.pop(fault_name, None)
                    dirty = True
                    self._emit_control_event_unlocked("fault", "expired", {"name": fault_name, "fault": expired})

        if dirty:
            self._state["active_faults"] = active_faults
            self._persist_unlocked()

    def _emit_control_event_unlocked(self, event_type: str, action: str, payload: dict[str, Any]) -> None:
        event_time = self._clock_now_unlocked().isoformat()
        observed_at = datetime.now(UTC).isoformat()
        record = {
            "event_type": event_type,
            "action": action,
            "payload": payload,
        }
        record["id"] = self._store.insert_control_event(
            event_type=event_type,
            action=action,
            payload=payload,
            event_time=event_time,
            created_at=observed_at,
        )
        record["event_time"] = event_time
        record["observed_at"] = observed_at

        with self._subscribers_lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(record)
            except queue.Full:
                continue

    def _clock_now_unlocked(self) -> datetime:
        raw = self._state.get("simulation_now")
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return parsed
            except ValueError:
                pass
        return datetime.now(UTC)
