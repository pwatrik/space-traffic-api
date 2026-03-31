import json
from tempfile import TemporaryDirectory

import pytest

from space_traffic_api.seed_data import build_ships, build_stations, load_seed_catalog


def test_default_seed_catalog_builds_expected_ids():
    stations = build_stations()
    assert len(stations) >= 30
    station_ids = {row["id"] for row in stations}
    assert "STN-PLANET-PLUTO" in station_ids
    assert "STN-MOON-CHARON" in station_ids

    ships = build_ships(stations=stations)
    assert len(ships) == 500
    assert ships[0]["id"] == "SHIP-0001"

    catalog = load_seed_catalog()
    lifecycle = catalog["lifecycle"]
    assert lifecycle["decommission"]["enabled"] is True
    assert lifecycle["war_impact"]["enabled"] is True
    assert lifecycle["build_queue"]["enabled"] is True
    assert lifecycle["pirate_activity"]["enabled"] is True
    assert lifecycle["pirate_activity"]["strength_start"] == 1.0
    assert lifecycle["pirate_activity"]["strength_end_threshold"] == 0.5


def test_custom_seed_catalog_defaults_are_applied():
    custom = {
        "celestial": {
            "planets": ["Earth"],
            "moons": [{"name": "Moon", "parent": "Earth"}],
            "asteroids": [],
            "distance_order": {"Earth": 1, "Asteroid Belt": 2},
        },
        "stations": {
            "templates": [
                {
                    "body_type": "planet",
                    "id_prefix": "STN-PLANET",
                    "name_template": "{body} Prime Port",
                    "allowed_size_classes": ["small", "medium"],
                },
                {
                    "body_type": "moon",
                    "id_prefix": "STN-MOON",
                    "name_template": "{body} Orbital",
                    "allowed_size_classes": ["small", "medium", "large", "xlarge"],
                },
                {
                    "body_type": "asteroid",
                    "id_prefix": "STN-AST",
                    "name_template": "{body} Hub",
                    "parent_body": "Asteroid Belt",
                    "allowed_size_classes": ["small", "medium"],
                },
            ]
        },
        "ship_generation": {
            "faction_distribution": {"bounty_hunter": 1.0},
            "ship_types": [
                {
                    "name": "Star Wasp",
                    "faction": "bounty_hunter",
                    "size_class": "small",
                    "displacement_min_million_m3": 0.01,
                    "displacement_max_million_m3": 0.5,
                },
            ],
            "cargo_types": ["water_ice"],
            "naming": {
                "adjectives": ["Solar"],
                "nouns": ["Voyager"],
                "captain_first": ["Avery"],
                "captain_last": ["Voss"],
            },
            "defaults": {"ship_count": 3, "ship_seed": 42},
        },
        "lifecycle": {
            "decommission": {
                "enabled": True,
                "base_probability_per_day": 0.001,
                "age_years_soft_limit": 10,
                "age_acceleration_per_year": 0.0002,
                "max_probability_per_day": 0.02,
            },
            "war_impact": {
                "enabled": True,
                "base_probability_per_day": 0.002,
                "faction_loss_multiplier": {"merchant": 1.5},
                "max_losses_per_event": 2,
            },
            "build_queue": {
                "enabled": True,
                "base_builds_per_day": 2.0,
                "max_builds_per_day": 4,
                "faction_distribution": {"merchant": 1.0},
                "spawn_policy": "compatible_random_station",
            },
            "pirate_activity": {
                "enabled": True,
                "allowed_anchors": ["Earth", "Asteroid Belt"],
                "strength_start": 1.0,
                "strength_end_threshold": 0.5,
                "merchant_arrival_destruction_multiplier": 5.0,
                "strength_decay_per_bounty_hunter_arrival": 0.03,
                "respawn_min_days": 12,
                "respawn_max_days": 22,
            },
        },
    }

    with TemporaryDirectory() as tmp:
        path = f"{tmp}/catalog.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(custom, fh)

        stations = build_stations(catalog_path=path)
        ships = build_ships(stations=stations, catalog_path=path)
        catalog = load_seed_catalog(path)

    assert len(stations) == 2
    assert len(ships) == 3
    bounty_ships = [ship for ship in ships if ship["faction"] == "bounty_hunter"]
    assert bounty_ships
    assert all(0.01 <= ship["displacement_million_m3"] <= 0.5 for ship in bounty_ships)
    assert catalog["lifecycle"]["decommission"]["age_years_soft_limit"] == 10.0
    assert catalog["lifecycle"]["war_impact"]["max_losses_per_event"] == 2
    assert catalog["lifecycle"]["build_queue"]["base_builds_per_day"] == 2.0
    assert catalog["lifecycle"]["pirate_activity"]["respawn_min_days"] == 12.0


def test_invalid_seed_catalog_raises():
    with TemporaryDirectory() as tmp:
        path = f"{tmp}/broken.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"celestial": {}}, fh)

        with pytest.raises(ValueError):
            load_seed_catalog(path)
