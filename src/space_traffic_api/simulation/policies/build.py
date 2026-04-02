from __future__ import annotations

import math
import random
from datetime import datetime
from typing import Any, Callable

from ...store import SQLiteStore


def apply_build_queue_policy(
	active_ships: list[dict[str, Any]],
	elapsed_days: float,
	tick_time: datetime,
	lifecycle_conf: dict[str, Any],
	store: SQLiteStore,
	rng: random.Random,
	ship_generation: dict[str, Any],
	naming_config: dict[str, Any],
	next_ship_sequence: int,
	ship_lookup: dict[str, dict[str, Any]],
	pick_weighted_key: Callable[[dict[str, float]], str],
	pick_station_by_policy: Callable[[str, str], str | None],
) -> tuple[list[str], int]:
	"""Apply build-queue lifecycle rules and persist resulting events."""

	conf = lifecycle_conf.get("build_queue") or {}
	if not conf.get("enabled", False):
		return [], next_ship_sequence

	base_builds_per_day = float(conf.get("base_builds_per_day", 0.0))
	max_builds_per_day = int(conf.get("max_builds_per_day", 1))
	if base_builds_per_day <= 0 or max_builds_per_day < 1:
		return [], next_ship_sequence

	expected_builds = base_builds_per_day * elapsed_days
	if expected_builds <= 0:
		return [], next_ship_sequence

	builds = int(expected_builds)
	if rng.random() < (expected_builds - builds):
		builds += 1

	tick_cap = max(1, int(max_builds_per_day * elapsed_days) + 1)
	builds = min(builds, tick_cap)
	if builds < 1:
		return [], next_ship_sequence

	faction_weights_raw = conf.get("faction_distribution") or {}
	faction_weights = {k: float(v) for k, v in faction_weights_raw.items() if float(v) > 0}
	if not faction_weights:
		return [], next_ship_sequence

	spawn_policy = str(conf.get("spawn_policy", "compatible_random_station")).strip().lower()

	ship_types = ship_generation.get("ship_types") or []
	cargo_types = ship_generation.get("cargo_types") or []
	naming = ship_generation.get("naming") or {}
	adjectives = naming.get("adjectives") or naming_config.get("adjectives") or ["Solar"]
	nouns = naming.get("nouns") or naming_config.get("nouns") or ["Pioneer"]
	captain_first = naming.get("captain_first") or naming_config.get("captain_first") or ["Alex"]
	captain_last = naming.get("captain_last") or naming_config.get("captain_last") or ["Voss"]
	ship_names_singular_raw = naming_config.get("ship_names_singular")
	ship_names_singular = list(ship_names_singular_raw) if isinstance(ship_names_singular_raw, list) else []

	if not ship_types or not cargo_types:
		return [], next_ship_sequence

	ship_types_by_faction: dict[str, list[dict[str, Any]]] = {}
	for ship_type in ship_types:
		ship_types_by_faction.setdefault(ship_type.get("faction"), []).append(ship_type)

	built_ship_ids: list[str] = []
	for _ in range(builds):
		faction = pick_weighted_key(faction_weights)
		candidates = ship_types_by_faction.get(faction) or ship_types
		choice = rng.choice(candidates)
		size_class = str(choice.get("size_class") or "medium").strip().lower()
		home_station_id = pick_station_by_policy(spawn_policy, size_class)
		if not home_station_id:
			continue

		ship_id = f"SHIP-{next_ship_sequence:04d}"
		next_ship_sequence += 1
		if ship_names_singular and rng.random() < 0.5:
			new_ship_name = rng.choice(ship_names_singular)
		else:
			new_ship_name = f"{rng.choice(adjectives)} {rng.choice(nouns)}"
		displacement = round(
			rng.uniform(
				float(choice.get("displacement_min_million_m3", 0.8)),
				float(choice.get("displacement_max_million_m3", 22.0)),
			),
			3,
		)

		built_faction = str(choice.get("faction") or faction)
		if built_faction == "bounty_hunter":
			crew = rng.randint(1, 5)
		else:
			crew_min = max(1, int(math.ceil(displacement * 200.0)))
			crew_max = max(crew_min, int(math.floor(displacement * 500.0)))
			crew = rng.randint(crew_min, crew_max)

		if built_faction == "merchant":
			cargo = rng.choice(cargo_types)
			passengers = rng.randint(0, 10_000)
		elif built_faction == "government":
			cargo = ""
			passengers = rng.randint(10, 500)
		else:
			cargo = ""
			passengers = 0

		ship = {
			"id": ship_id,
			"name": new_ship_name,
			"faction": built_faction,
			"ship_type": str(choice.get("name") or "Auxiliary"),
			"size_class": size_class,
			"displacement_million_m3": displacement,
			"home_station_id": home_station_id,
			"captain_name": f"{rng.choice(captain_first)} {rng.choice(captain_last)}",
			"cargo": cargo,
			"crew": crew,
			"passengers": passengers,
		}
		store.seed_ships([ship])
		store.seed_ship_states([ship], now_iso=tick_time.isoformat())
		ship_lookup[ship_id] = ship
		built_ship_ids.append(ship_id)

	if built_ship_ids:
		store.insert_control_event(
			event_type="lifecycle",
			action="ships_built",
			payload={
				"ship_ids": built_ship_ids,
				"count": len(built_ship_ids),
				"at": tick_time.isoformat(),
			},
			event_time=tick_time.isoformat(),
		)

	return built_ship_ids, next_ship_sequence
