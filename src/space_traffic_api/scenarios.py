from __future__ import annotations

from typing import Any


SCENARIO_DEFINITIONS: dict[str, dict[str, Any]] = {
    "war": {
        "description": "Military surge with strategic reroutes.",
        "rate_multiplier": 3.0,
        "faction_weights": {"military": 0.8, "government": 0.15, "merchant": 0.05},
    },
    "shortage": {
        "description": "Resource shortages increase merchant hauling from mining/agri corridors.",
        "rate_multiplier": 2.2,
        "faction_weights": {"merchant": 0.75, "government": 0.15, "military": 0.10},
        "preferred_source_keywords": ["CERES", "VESTA", "GANYMEDE", "EUROPA", "TITAN"],
    },
    "solar_flare": {
        "description": "Solar storms can halt or partially interrupt traffic, then recover.",
        "rate_multiplier": 0.0,
        "interruptive": True,
    },
}


def list_scenarios() -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for name, details in SCENARIO_DEFINITIONS.items():
        payload.append({"name": name, **details})
    return payload
