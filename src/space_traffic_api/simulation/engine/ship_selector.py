from __future__ import annotations

import random
from typing import Any

from ..scenarios import SCENARIO_DEFINITIONS


def select_ship(
	candidates: list[dict[str, Any]],
	fallback_candidates: list[dict[str, Any]],
	scenario: dict[str, Any] | None,
	runtime_snap: dict[str, Any],
	pirate_conf: dict[str, Any],
	rng: random.Random,
) -> dict[str, Any] | None:
	"""Select a ship for departure with scenario and pirate weighting rules."""

	if not candidates:
		return None

	pirate_state = runtime_snap.get("pirate_event")
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

	weighted_candidates = candidates
	if faction_weights:
		weighted_candidates = [s for s in candidates if s["faction"] in faction_weights]
		if not weighted_candidates:
			if not fallback_candidates:
				return None
			weighted_candidates = fallback_candidates

	cumulative: list[float] = []
	running = 0.0
	for ship in weighted_candidates:
		faction = str(ship.get("faction") or "")
		base_weight = float(faction_weights.get(faction, 1.0)) if faction_weights else 1.0
		multiplier = bounty_multiplier if faction == "bounty_hunter" else 1.0
		effective_weight = max(0.0, base_weight * multiplier)
		running += effective_weight
		cumulative.append(running)

	if running <= 0:
		return rng.choice(weighted_candidates)

	pick = rng.random() * running
	for idx, threshold in enumerate(cumulative):
		if pick <= threshold:
			return weighted_candidates[idx]
	return weighted_candidates[-1]
