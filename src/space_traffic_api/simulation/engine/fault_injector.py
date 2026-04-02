from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from typing import Any


def apply_faults(
	event: dict[str, Any],
	state: dict[str, Any],
	rng: random.Random,
	last_event_uid: str | None = None,
) -> None:
	"""Apply active fault mutations to an event payload in place."""

	active_faults = state.get("active_faults", {}) or {}
	for fault_name, conf in active_faults.items():
		rate = float(conf.get("rate", 0.0))
		if rng.random() > rate:
			continue

		flags = event.setdefault("fault_flags", [])
		flags.append(fault_name)

		if fault_name == "missing_field":
			event["destination_station_id"] = None
		elif fault_name == "invalid_enum":
			if event.get("malformed"):
				continue
			try:
				raw = json.loads(event["payload_json"])
			except json.JSONDecodeError:
				event["malformed"] = True
				continue
			raw["route_priority"] = "totally_invalid"
			event["payload_json"] = json.dumps(raw)
		elif fault_name == "out_of_order_timestamp":
			dt = datetime.fromisoformat(event["departure_time"]) - timedelta(minutes=rng.randint(5, 120))
			event["departure_time"] = dt.isoformat()
		elif fault_name == "malformed_payload":
			event["payload_json"] = "{malformed-json"
			event["malformed"] = True
		elif fault_name == "duplicate_event_uid" and last_event_uid:
			event["event_uid"] = last_event_uid
		elif fault_name == "synthetic_error":
			event["ship_id"] = None
			event["source_station_id"] = None
			event["destination_station_id"] = None
			event["malformed"] = True
		elif fault_name == "delayed_insert":
			pass

	if event.get("payload_json") and not event.get("malformed"):
		try:
			parsed = json.loads(event["payload_json"])
			parsed["fault_flags"] = event.get("fault_flags", [])
			event["payload_json"] = json.dumps(parsed)
		except json.JSONDecodeError:
			event["malformed"] = True
