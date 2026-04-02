from __future__ import annotations

import random
from copy import deepcopy
from datetime import datetime
from typing import Any, Callable

from ...store import SQLiteStore
from ..runtime import RuntimeState


def apply_pirate_activity_policy(
	tick_time: datetime,
	elapsed_days: float,
	lifecycle_conf: dict[str, Any],
	runtime: RuntimeState,
	store: SQLiteStore,
	rng: random.Random,
	station_lookup: dict[str, dict[str, Any]],
	parse_iso: Callable[[Any], datetime | None],
	end_pirate_event: Callable[[dict[str, Any], dict[str, Any], datetime, dict[str, Any] | None], None],
) -> None:
	"""Apply pirate event spawn/decay lifecycle logic."""

	conf = lifecycle_conf.get("pirate_activity") or {}
	if not conf.get("enabled", False):
		snapshot = runtime.snapshot()
		persisted = snapshot.get("pirate_event")
		if isinstance(persisted, dict) and persisted.get("active"):
			ended_at = tick_time.isoformat()
			next_state = deepcopy(persisted)
			next_state["active"] = False
			next_state["strength"] = 0.0
			next_state["ended_at"] = ended_at
			next_state["updated_at"] = ended_at
			next_state["next_spawn_earliest_at"] = None
			runtime.set_pirate_event_state(next_state)
		return

	runtime_snap = runtime.snapshot()
	state = deepcopy(runtime_snap.get("pirate_event") or {})

	active = bool(state.get("active", False))
	strength = float(state.get("strength") or 0.0)
	raw_spawn_probability = runtime_snap.get("pirate_spawn_probability_per_day")
	if raw_spawn_probability is None:
		raw_spawn_probability = conf.get("spawn_probability_per_day", 1.0)
	spawn_probability_per_day = float(raw_spawn_probability)

	raw_strength_end_threshold = runtime_snap.get("pirate_strength_end_threshold")
	if raw_strength_end_threshold is None:
		raw_strength_end_threshold = conf.get("strength_end_threshold", 0.5)
	strength_end_threshold = float(raw_strength_end_threshold)

	raw_decay_per_day = runtime_snap.get("pirate_strength_decay_per_day")
	if raw_decay_per_day is None:
		raw_decay_per_day = conf.get("ambient_strength_decay_per_day", 0.0)
	decay_per_day = float(raw_decay_per_day)

	if active:
		if decay_per_day > 0 and elapsed_days > 0:
			next_strength = max(0.0, strength - (decay_per_day * elapsed_days))
			if abs(next_strength - strength) >= 1e-9:
				strength = next_strength
				state["strength"] = strength
				state["updated_at"] = tick_time.isoformat()
				runtime.set_pirate_event_state(state)

		if strength <= strength_end_threshold:
			end_pirate_event(state=state, conf=conf, tick_time=tick_time, runtime_snap=runtime_snap)
		return

	next_spawn_raw = state.get("next_spawn_earliest_at")
	next_spawn_at = parse_iso(next_spawn_raw)
	if next_spawn_at and tick_time < next_spawn_at:
		return

	if spawn_probability_per_day > 0:
		spawn_chance_when_eligible = min(1.0, max(0.0, spawn_probability_per_day))
		if rng.random() >= spawn_chance_when_eligible:
			return

	allowed_anchors = [str(x) for x in conf.get("allowed_anchors", []) if str(x).strip()]
	if not allowed_anchors:
		return

	previous_anchor = state.get("previous_anchor_body")
	candidates = [anchor for anchor in allowed_anchors if anchor != previous_anchor]
	if not candidates:
		candidates = allowed_anchors
	anchor = rng.choice(candidates)
	affected_station_ids = sorted(
		[
			station_id
			for station_id, station in station_lookup.items()
			if str(station.get("parent_body") or "") == anchor
		]
	)

	raw_strength_start = runtime_snap.get("pirate_strength_start")
	if raw_strength_start is None:
		raw_strength_start = conf.get("strength_start", 1.0)
	strength_start = float(raw_strength_start)
	next_state = {
		"active": True,
		"anchor_body": anchor,
		"previous_anchor_body": previous_anchor,
		"strength": strength_start,
		"started_at": tick_time.isoformat(),
		"ended_at": None,
		"next_spawn_earliest_at": None,
		"affected_station_ids": affected_station_ids,
		"updated_at": tick_time.isoformat(),
	}
	runtime.set_pirate_event_state(next_state)
	store.insert_control_event(
		event_type="lifecycle",
		action="pirate_started",
		payload={
			"anchor_body": anchor,
			"strength": strength_start,
			"affected_station_ids": affected_station_ids,
			"at": tick_time.isoformat(),
		},
		event_time=tick_time.isoformat(),
	)
