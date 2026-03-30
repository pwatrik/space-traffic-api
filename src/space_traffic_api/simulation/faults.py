from __future__ import annotations

from typing import Any


FAULT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "malformed_payload": {
        "description": "Emit invalid JSON payload text while retaining DB envelope fields.",
        "default_rate": 0.02,
    },
    "missing_field": {
        "description": "Remove required event fields in payload.",
        "default_rate": 0.03,
    },
    "invalid_enum": {
        "description": "Inject invalid enum values for schema robustness tests.",
        "default_rate": 0.02,
    },
    "out_of_order_timestamp": {
        "description": "Skew departure time backwards to simulate out-of-order arrival.",
        "default_rate": 0.02,
    },
    "delayed_insert": {
        "description": "Delay persistence for a subset of events.",
        "default_rate": 0.03,
    },
    "duplicate_event_uid": {
        "description": "Reuse a previous event UID to simulate duplication.",
        "default_rate": 0.01,
    },
    "synthetic_error": {
        "description": "Emit synthetic error-shaped records.",
        "default_rate": 0.01,
    },
}


def list_faults() -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for name, details in FAULT_DEFINITIONS.items():
        payload.append({"name": name, **details})
    return payload


def normalize_fault_request(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    rate = raw.get("rate", FAULT_DEFINITIONS[name]["default_rate"])
    duration_seconds = int(raw.get("duration_seconds", 0))
    scope = raw.get("scope", {"type": "global"})
    return {
        "rate": max(0.0, min(1.0, float(rate))),
        "duration_seconds": max(0, duration_seconds),
        "scope": scope,
    }
