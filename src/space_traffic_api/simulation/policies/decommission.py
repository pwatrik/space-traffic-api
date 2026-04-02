from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from ...store import SQLiteStore


def apply_decommission_policy(
    active_ships: list[dict[str, Any]],
    elapsed_days: float,
    tick_time: datetime,
    lifecycle_conf: dict[str, Any],
    store: SQLiteStore,
    rng: random.Random,
) -> list[str]:
    """Apply ship decommissioning lifecycle rules and persist resulting events."""

    conf = lifecycle_conf.get("decommission") or {}
    if not conf.get("enabled", False):
        return []

    base = float(conf.get("base_probability_per_day", 0.0))
    if base <= 0:
        return []

    soft_limit_days = float(conf.get("age_years_soft_limit", 18.0)) * 365.0
    accel = float(conf.get("age_acceleration_per_year", 0.0))
    max_probability_per_day = float(conf.get("max_probability_per_day", base))

    retired_ids: list[str] = []
    for ship in active_ships:
        age_days = float(ship.get("ship_age_days") or 0.0)
        years_over = max(0.0, (age_days - soft_limit_days) / 365.0)
        per_day = min(max_probability_per_day, base + (years_over * accel))
        per_tick = min(1.0, max(0.0, per_day * elapsed_days))
        if rng.random() >= per_tick:
            continue

        ship_id = ship["ship_id"]
        if store.deactivate_ship(
            ship_id=ship_id,
            status="decommissioned",
            current_station_id=ship.get("current_station_id"),
            now_iso=tick_time.isoformat(),
        ):
            retired_ids.append(ship_id)

    if retired_ids:
        store.insert_control_event(
            event_type="lifecycle",
            action="decommissioned",
            payload={
                "ship_ids": retired_ids,
                "count": len(retired_ids),
                "at": tick_time.isoformat(),
            },
            event_time=tick_time.isoformat(),
        )

    return retired_ids
