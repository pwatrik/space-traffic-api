from space_traffic_api.simulation.generator import build_effective_lifecycle_config
from space_traffic_api.simulation.scenarios import SCENARIO_DEFINITIONS


def _base_lifecycle() -> dict:
    return {
        "decommission": {
            "enabled": True,
            "base_probability_per_day": 0.01,
            "max_probability_per_day": 0.1,
        },
        "war_impact": {
            "enabled": True,
            "base_probability_per_day": 0.02,
            "faction_loss_multiplier": {
                "merchant": 1.0,
                "government": 1.0,
                "military": 1.0,
            },
            "max_losses_per_event": 2,
        },
        "build_queue": {
            "enabled": True,
            "base_builds_per_day": 2.0,
            "faction_distribution": {
                "merchant": 0.6,
                "government": 0.25,
                "military": 0.15,
            },
        },
    }


def test_war_scenario_lifecycle_overrides_apply_at_intensity_1():
    base = _base_lifecycle()
    effective = build_effective_lifecycle_config(base, SCENARIO_DEFINITIONS["war"], intensity=1.0)

    assert effective["war_impact"]["base_probability_per_day"] > base["war_impact"]["base_probability_per_day"]
    assert effective["war_impact"]["max_losses_per_event"] > base["war_impact"]["max_losses_per_event"]
    assert effective["build_queue"]["base_builds_per_day"] < base["build_queue"]["base_builds_per_day"]
    assert effective["build_queue"]["faction_distribution"]["military"] > base["build_queue"]["faction_distribution"]["military"]


def test_shortage_scenario_amplifies_build_queue_and_reduces_war():
    base = _base_lifecycle()
    effective = build_effective_lifecycle_config(base, SCENARIO_DEFINITIONS["shortage"], intensity=1.0)

    assert effective["build_queue"]["base_builds_per_day"] > base["build_queue"]["base_builds_per_day"]
    assert effective["build_queue"]["faction_distribution"]["merchant"] > base["build_queue"]["faction_distribution"]["merchant"]
    assert effective["war_impact"]["base_probability_per_day"] < base["war_impact"]["base_probability_per_day"]


def test_intensity_zero_keeps_base_values_and_no_mutation():
    base = _base_lifecycle()
    original_snapshot = _base_lifecycle()

    effective = build_effective_lifecycle_config(base, SCENARIO_DEFINITIONS["war"], intensity=0.0)

    assert effective["war_impact"]["base_probability_per_day"] == base["war_impact"]["base_probability_per_day"]
    assert effective["build_queue"]["base_builds_per_day"] == base["build_queue"]["base_builds_per_day"]
    assert base == original_snapshot
