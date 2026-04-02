from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Any, Callable

from ...store import SQLiteStore


def create_departure_event(
	ship_id: str,
	source_station_id: str,
	destination_station_id: str,
	departure_time: datetime,
	scenario: dict[str, Any] | None,
	ship_faction: str | None,
	store: SQLiteStore,
	station_lookup: dict[str, dict[str, Any]],
	rng: random.Random,
	estimate_arrival: Callable[[datetime, str, str], datetime],
	event_counter: int,
) -> tuple[dict[str, Any] | None, int, str]:
	"""Build a departure event and return updated counter state."""

	eta = estimate_arrival(departure_time, source_station_id, destination_station_id)

	departed = store.begin_ship_transit(
		ship_id=ship_id,
		source_station_id=source_station_id,
		destination_station_id=destination_station_id,
		departure_time=departure_time.isoformat(),
		est_arrival_time=eta.isoformat(),
		now_iso=departure_time.isoformat(),
	)
	if not departed:
		return None, event_counter, ""

	if ship_faction == "merchant":
		source_station = station_lookup.get(source_station_id) or {}
		source_cargo = str(source_station.get("cargo_type") or "").strip()
		if source_cargo:
			store.set_ship_cargo(ship_id=ship_id, cargo=source_cargo)

	next_event_counter = event_counter + 1
	event_uid = f"EVT-{next_event_counter:09d}-{rng.getrandbits(32):08x}"

	payload = {
		"event_uid": event_uid,
		"departure_time": departure_time.isoformat(),
		"ship_id": ship_id,
		"source_station_id": source_station_id,
		"destination_station_id": destination_station_id,
		"est_arrival_time": eta.isoformat(),
		"scenario": scenario["name"] if scenario else "baseline",
	}

	event = {
		**payload,
		"fault_flags": [],
		"malformed": False,
		"payload_json": json.dumps(payload),
	}
	return event, next_event_counter, event_uid
