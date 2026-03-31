from __future__ import annotations

from typing import Any


SCENARIO_DEFINITIONS: dict[str, dict[str, Any]] = {
    "war": {
        "description": "Military surge with strategic reroutes.",
        "rate_multiplier": 3.0,
        "faction_weights": {"military": 0.8, "government": 0.15, "merchant": 0.05},
        "lifecycle_overrides": {
            "decommission": {
                "base_probability_per_day_multiplier": 1.1,
            },
            "war_impact": {
                "base_probability_per_day_multiplier": 4.0,
                "faction_loss_multiplier_overrides": {
                    "merchant": 1.4,
                    "government": 1.2,
                    "military": 1.0,
                },
                "max_losses_per_event_add": 2,
            },
            "build_queue": {
                "base_builds_per_day_multiplier": 0.75,
                "faction_distribution": {"merchant": 0.35, "government": 0.25, "military": 0.40},
            },
        },
    },
    "shortage": {
        "description": "Resource shortages increase merchant hauling from mining/agri corridors.",
        "rate_multiplier": 2.2,
        "faction_weights": {"merchant": 0.75, "government": 0.15, "military": 0.10},
        "preferred_source_keywords": ["CERES", "VESTA", "GANYMEDE", "EUROPA", "TITAN"],
        "lifecycle_overrides": {
            "decommission": {
                "base_probability_per_day_multiplier": 1.2,
            },
            "war_impact": {
                "base_probability_per_day_multiplier": 0.5,
            },
            "build_queue": {
                "base_builds_per_day_multiplier": 2.0,
                "faction_distribution": {"merchant": 0.80, "government": 0.15, "military": 0.05},
            },
        },
    },
    "solar_flare": {
        "description": "Solar storms can halt or partially interrupt traffic, then recover.",
        "rate_multiplier": 0.0,
        "interruptive": True,
        "lifecycle_overrides": {
            "decommission": {
                "base_probability_per_day_multiplier": 1.6,
            },
            "war_impact": {
                "base_probability_per_day_multiplier": 0.2,
            },
            "build_queue": {
                "base_builds_per_day_multiplier": 0.4,
            },
        },
    },
}


def list_scenarios() -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for name, details in SCENARIO_DEFINITIONS.items():
        payload.append({"name": name, **details})
    return payload
