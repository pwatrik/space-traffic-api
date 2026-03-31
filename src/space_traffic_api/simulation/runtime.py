from __future__ import annotations

import queue
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from ..config import AppConfig
from ..store import SQLiteStore
from .faults import FAULT_DEFINITIONS, normalize_fault_request
from .scenarios import SCENARIO_DEFINITIONS


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
            "active_scenario": None,
            "active_faults": {},
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
        ends_at = datetime.now(UTC) + timedelta(seconds=duration_seconds)

        with self._lock:
            self._state["active_scenario"] = {
                "name": name,
                "intensity": intensity,
                "duration_seconds": duration_seconds,
                "scope": scope,
                "started_at": datetime.now(UTC).isoformat(),
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
            now = datetime.now(UTC)

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
                    "ended_at": datetime.now(UTC).isoformat(),
                    "next_spawn_earliest_at": None,
                    "affected_station_ids": [],
                }
            self._state["last_reset_at"] = datetime.now(UTC).isoformat()
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

    def _persist_unlocked(self) -> None:
        self._store.set_control_state("runtime", self._state)

    def _expire_unlocked(self) -> None:
        now = datetime.now(UTC)
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
        record = {
            "event_type": event_type,
            "action": action,
            "payload": payload,
        }
        record["id"] = self._store.insert_control_event(event_type=event_type, action=action, payload=payload)
        record["event_time"] = datetime.now(UTC).isoformat()

        with self._subscribers_lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(record)
            except queue.Full:
                continue
