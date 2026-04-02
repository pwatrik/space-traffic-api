from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


@dataclass(slots=True)
class TickResult:
    """Structured output from a single simulation engine tick."""

    departed_event: dict[str, Any] | None
    interrupted: bool
    startup_merchants_launched: bool
    arrived_ships: list[dict[str, Any]]
    interval_seconds: float
    wait_seconds: float


class SimulationEngine:
    """Stateless orchestration façade for generator tick logic."""

    def tick(
        self,
        *,
        state: dict[str, Any],
        scenario: dict[str, Any] | None,
        tick_time: datetime,
        interval_seconds: float,
        wait_seconds: float,
        startup_merchants_launched: bool,
        launch_startup_merchants: Callable[[dict[str, Any], dict[str, Any] | None, datetime], None],
        complete_arrivals: Callable[[datetime], list[dict[str, Any]]],
        apply_lifecycle: Callable[[float, datetime, dict[str, Any] | None, list[dict[str, Any]]], None],
        is_globally_interrupted: Callable[[dict[str, Any] | None], bool],
        build_event: Callable[[dict[str, Any], dict[str, Any] | None, datetime], dict[str, Any] | None],
        apply_faults: Callable[[dict[str, Any], dict[str, Any]], None],
        delayed_insert_pause: Callable[[dict[str, Any]], bool],
        persist_and_publish_event: Callable[[dict[str, Any], dict[str, Any]], None],
        advance_sim_time: Callable[[datetime, float], None],
    ) -> TickResult:
        """Run one simulation tick using injected collaborators and callbacks.

        delayed_insert_pause(event) is called after apply_faults when the event
        carries a delayed_insert fault flag. It should sleep for the delay duration
        and return True if the thread should stop, False otherwise.
        """

        launched = startup_merchants_launched
        if not launched:
            launch_startup_merchants(state, scenario, tick_time)
            launched = True

        arrived_ships = complete_arrivals(tick_time)
        apply_lifecycle(interval_seconds, tick_time, scenario, arrived_ships)

        if is_globally_interrupted(scenario):
            advance_sim_time(tick_time, interval_seconds)
            return TickResult(
                departed_event=None,
                interrupted=True,
                startup_merchants_launched=launched,
                arrived_ships=arrived_ships,
                interval_seconds=interval_seconds,
                wait_seconds=min(1.0, wait_seconds),
            )

        event = build_event(state, scenario, tick_time)
        if event is None:
            advance_sim_time(tick_time, interval_seconds)
            return TickResult(
                departed_event=None,
                interrupted=False,
                startup_merchants_launched=launched,
                arrived_ships=arrived_ships,
                interval_seconds=interval_seconds,
                wait_seconds=min(1.0, wait_seconds),
            )

        apply_faults(event, state)

        if "delayed_insert" in event.get("fault_flags", []):
            should_stop = delayed_insert_pause(event)
            if should_stop:
                advance_sim_time(tick_time, interval_seconds)
                return TickResult(
                    departed_event=None,
                    interrupted=False,
                    startup_merchants_launched=launched,
                    arrived_ships=arrived_ships,
                    interval_seconds=interval_seconds,
                    wait_seconds=0.0,
                )

        persist_and_publish_event(event, state)
        advance_sim_time(tick_time, interval_seconds)

        return TickResult(
            departed_event=event,
            interrupted=False,
            startup_merchants_launched=launched,
            arrived_ships=arrived_ships,
            interval_seconds=interval_seconds,
            wait_seconds=wait_seconds,
        )
