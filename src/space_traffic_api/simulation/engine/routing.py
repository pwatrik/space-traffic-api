from __future__ import annotations

import random
from typing import Any, Callable

from ..scenarios import SCENARIO_DEFINITIONS


def pick_destination(
	ship: dict[str, Any],
	source_station_id: str,
	scenario: dict[str, Any] | None,
	station_lookup: dict[str, dict[str, Any]],
	pirate_conf: dict[str, Any],
	pirate_state: dict[str, Any] | None,
	rng: random.Random,
	station_accepts_size_class: Callable[[str, str], bool],
	economy_preference_weight: float = 0.15,
) -> str | None:
	"""Select a compatible destination station for a ship."""

	ship_size_class = str(ship.get("size_class") or "medium").strip().lower()

	station_ids = list(station_lookup.keys())
	if source_station_id in station_ids:
		station_ids.remove(source_station_id)

	station_ids = [sid for sid in station_ids if station_accepts_size_class(sid, ship_size_class)]
	if not station_ids:
		return None

	is_bounty_hunter = str(ship.get("faction") or "") == "bounty_hunter"
	if is_bounty_hunter and isinstance(pirate_state, dict) and pirate_state.get("active"):
		affected = [sid for sid in pirate_state.get("affected_station_ids", []) if sid in station_ids]
		if affected:
			response_bias = min(1.0, max(0.0, float(pirate_conf.get("bounty_hunter_response_bias", 0.9))))
			if rng.random() < response_bias:
				return rng.choice(affected)

	if scenario and scenario.get("name") == "shortage":
		keywords = SCENARIO_DEFINITIONS["shortage"].get("preferred_source_keywords", [])
		preferred = [sid for sid in station_ids if any(key in sid for key in keywords)]
		if preferred and rng.random() < 0.65:
			return rng.choice(preferred)

	if str(ship.get("faction") or "") == "merchant" and economy_preference_weight > 0:
		weight = max(0.0, min(1.0, float(economy_preference_weight)))
		src_station = station_lookup.get(source_station_id, {})
		src_derived = src_station.get("economy_derived") if isinstance(src_station.get("economy_derived"), dict) else {}
		source_fuel = max(0.1, float(src_derived.get("fuel_pressure_score", 1.0) or 1.0))
		weighted: list[tuple[str, float]] = []
		for sid in station_ids:
			station = station_lookup.get(sid, {})
			derived = station.get("economy_derived") if isinstance(station.get("economy_derived"), dict) else {}
			state = station.get("economy_state") if isinstance(station.get("economy_state"), dict) else {}
			local_value = float(derived.get("local_value_score", 0.0) or 0.0)
			if local_value <= 0:
				supply = max(0.01, float(state.get("supply_index", 1.0) or 1.0))
				demand = float(state.get("demand_index", 1.0) or 1.0)
				price = float(state.get("price_index", 1.0) or 1.0)
				local_value = (demand / supply) * price
			local_value = max(0.1, min(10.0, local_value))
			dest_fuel = max(0.1, float(derived.get("fuel_pressure_score", 1.0) or 1.0))
			fuel_cost_ratio = max(0.5, min(2.0, dest_fuel / source_fuel))
			net_value = local_value / fuel_cost_ratio
			station_weight = 1.0 + ((net_value - 1.0) * weight)
			weighted.append((sid, max(0.001, station_weight)))

		total = sum(w for _, w in weighted)
		if total > 0:
			threshold = rng.random() * total
			running = 0.0
			for sid, station_weight in weighted:
				running += station_weight
				if threshold <= running:
					return sid

	return rng.choice(station_ids)
