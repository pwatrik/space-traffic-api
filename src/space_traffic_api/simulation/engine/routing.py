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

	return rng.choice(station_ids)
