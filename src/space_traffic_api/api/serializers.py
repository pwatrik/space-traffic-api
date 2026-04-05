"""Serialization logic for API responses."""

from __future__ import annotations

import json
from typing import Any


def _parse_fault_flags(value: Any) -> list:
    """Parse fault_flags from either a Python list or a JSON string."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            return []
    return []


def serialize_departure(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize a departure row from the database to API response format."""
    payload = row.get("payload_json")
    try:
        parsed_payload = json.loads(payload) if payload else None
    except json.JSONDecodeError:
        parsed_payload = payload

    return {
        "id": row["id"],
        "event_uid": row["event_uid"],
        "departure_time": row["departure_time"],
        "departure_time_simulated": row["departure_time"],
        "ship_id": row.get("ship_id"),
        "source_station_id": row.get("source_station_id"),
        "destination_station_id": row.get("destination_station_id"),
        "est_arrival_time": row.get("est_arrival_time"),
        "est_arrival_time_simulated": row.get("est_arrival_time"),
        "recorded_at_wall": row.get("created_at"),
        "scenario": row.get("scenario"),
        "fault_flags": _parse_fault_flags(row.get("fault_flags")),
        "malformed": bool(row.get("malformed")),
        "payload": parsed_payload,
    }


def serialize_control_event(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize a control event row from the database to API response format."""
    payload = row.get("payload")
    if payload is None:
        raw = row.get("payload_json")
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = raw

    return {
        "id": row["id"],
        "event_time": row["event_time"],
        "event_time_simulated": row["event_time"],
        "recorded_at_wall": row.get("created_at"),
        "event_type": row["event_type"],
        "action": row["action"],
        "payload": payload,
    }


def serialize_ship_state(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "departure_time_simulated": row.get("departure_time"),
        "est_arrival_time_simulated": row.get("est_arrival_time"),
        "updated_at_simulated": row.get("updated_at"),
        "updated_at_wall": row.get("updated_at_wall") or row.get("updated_at"),
    }
