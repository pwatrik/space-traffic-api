from __future__ import annotations

import queue
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
    ):
        self._runtime = RuntimeState(config=config, store=store)
        self._generator = DepartureGenerator(store=store, runtime=self._runtime, stations=stations, ships=ships)

    def start(self) -> None:
        if not self._generator.is_alive():
            self._generator.start()

    def stop(self, timeout: float = 2.0) -> None:
        if self._generator.is_alive():
            self._generator.stop()
            self._generator.join(timeout=timeout)

    def is_running(self) -> bool:
        return self._generator.is_alive()

    def snapshot(self) -> dict[str, Any]:
        return self._runtime.snapshot()

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
