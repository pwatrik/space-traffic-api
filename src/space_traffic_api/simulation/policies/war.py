from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from ...store import SQLiteStore


def apply_war_impact_policy(
	active_ships: list[dict[str, Any]],
	elapsed_days: float,
	tick_time: datetime,
	lifecycle_conf: dict[str, Any],
	store: SQLiteStore,
	rng: random.Random,
) -> list[str]:
	"""Apply war-impact lifecycle rules and persist resulting events."""

	conf = lifecycle_conf.get("war_impact") or {}
	if not conf.get("enabled", False):
		return []

	base = float(conf.get("base_probability_per_day", 0.0))
	if base <= 0:
		return []

	faction_multiplier = conf.get("faction_loss_multiplier") or {}
	max_losses = int(conf.get("max_losses_per_event", 1))
	if max_losses < 1:
		return []

	weighted_candidates: list[dict[str, Any]] = []
	for ship in active_ships:
		weight = float(faction_multiplier.get(ship.get("faction"), 1.0))
		if weight <= 0:
			continue
		chance = max(0.0, min(1.0, base * weight * elapsed_days))
		if rng.random() < chance:
			weighted_candidates.append(ship)

	if not weighted_candidates:
		return []

	rng.shuffle(weighted_candidates)
	selected = weighted_candidates[:max_losses]
	destroyed: list[str] = []
	for ship in selected:
		ship_id = ship["ship_id"]
		if store.deactivate_ship(
			ship_id=ship_id,
			status="destroyed",
			current_station_id=ship.get("current_station_id"),
			now_iso=tick_time.isoformat(),
		):
			destroyed.append(ship_id)

	if destroyed:
		store.insert_control_event(
			event_type="lifecycle",
			action="war_losses",
			payload={
				"ship_ids": destroyed,
				"count": len(destroyed),
				"at": tick_time.isoformat(),
			},
			event_time=tick_time.isoformat(),
		)

	return destroyed
