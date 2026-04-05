from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from typing import Any

from ..config import AppConfig
from ..store import SQLiteStore
from .generator import DepartureGenerator
from .runtime import RuntimeState


class SimulationService:
    """Facade over runtime control state and departure generation lifecycle."""

    def __init__(
        self,
        config: AppConfig,
        store: SQLiteStore,
        stations: list[dict[str, Any]],
        ships: list[dict[str, Any]],
        catalog: dict[str, Any] | None = None,
    ):
        self._store = store
        self._runtime = RuntimeState(config=config, store=store)
        self._generator = DepartureGenerator(
            store=store,
            runtime=self._runtime,
            stations=stations,
            ships=ships,
            catalog=catalog,
        )
        self._clock_stop_event = threading.Event()
        self._clock_thread: threading.Thread | None = None

    def start(self) -> None:
        if self._clock_thread is None or not self._clock_thread.is_alive():
            self._clock_stop_event.clear()
            self._clock_thread = threading.Thread(target=self._run_clock, daemon=True)
            self._clock_thread.start()
        if not self._generator.is_alive():
            self._generator.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._clock_stop_event.set()
        if self._generator.is_alive():
            self._generator.stop()
            self._generator.join(timeout=timeout)
        if self._clock_thread is not None and self._clock_thread.is_alive():
            self._clock_thread.join(timeout=timeout)

    def _run_clock(self) -> None:
        last = time.monotonic()
        while not self._clock_stop_event.wait(timeout=0.1):
            now = time.monotonic()
            elapsed = max(0.0, now - last)
            last = now
            self._runtime.advance_simulation_clock(elapsed)

    def is_running(self) -> bool:
        return self._generator.is_alive()

    def snapshot(self, counts: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self._runtime.snapshot()
        if counts is None:
            counts = self._store.get_counts()
        generator_metrics = self._generator.runtime_metrics()
        control_metrics = self._runtime.subscriber_metrics()
        orbital_diagnostics = self._generator.orbital_diagnostics_snapshot()
        generator_metrics["control_events_total"] = counts.get("control_events", 0)
        generator_metrics["control_event_subscribers"] = control_metrics["subscribers"]
        generator_metrics["control_event_backlog_total"] = control_metrics["backlog_total"]
        generator_metrics["control_event_backlog_max"] = control_metrics["backlog_max"]
        generator_metrics["departures_total"] = counts.get("departures", 0)
        generator_metrics["ships_in_transit"] = counts.get("ships_in_transit", 0)

        state["effective_lifecycle"] = self._generator.effective_lifecycle_config(state.get("active_scenario"))
        state["effective_ship_generation"] = self._generator.effective_ship_generation_config()
        state["runtime_metrics"] = generator_metrics
        state["orbital_diagnostics"] = {
            "enabled": bool(state.get("orbital_distance_model_enabled", False)),
            **orbital_diagnostics,
        }
        return state

    def patch_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        return self._runtime.patch_config(patch)

    def activate_scenario(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._runtime.activate_scenario(request)

    def deactivate_scenario(self) -> None:
        self._runtime.deactivate_scenario()

    def activate_faults(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._runtime.activate_faults(request)

    def deactivate_faults(self, names: list[str] | None = None) -> dict[str, Any]:
        return self._runtime.deactivate_faults(names)

    def reset(self, seed: int | None = None) -> dict[str, Any]:
        return self._runtime.reset(seed=seed)

    def estimate_arrival(self, departure_time: datetime, source: str, destination: str) -> datetime:
        return self._generator.estimate_arrival(departure_time, source, destination)

    def orbital_state_snapshot(self) -> dict[str, dict[str, Any]]:
        return self._generator.orbital_state_snapshot()

    def list_control_events(self, since_id: int | None, limit: int, order: str) -> list[dict[str, Any]]:
        return self._runtime.list_control_events(since_id=since_id, limit=limit, order=order)

    def subscribe_departures(self) -> queue.Queue[dict[str, Any]]:
        return self._generator.subscribe()

    def unsubscribe_departures(self, q: queue.Queue[dict[str, Any]]) -> None:
        self._generator.unsubscribe(q)

    def subscribe_control_events(self) -> queue.Queue[dict[str, Any]]:
        return self._runtime.subscribe()

    def unsubscribe_control_events(self, q: queue.Queue[dict[str, Any]]) -> None:
        self._runtime.unsubscribe(q)
