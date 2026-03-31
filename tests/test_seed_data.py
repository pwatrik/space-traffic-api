import json
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from space_traffic_api.seed_data import build_ships, build_stations, load_naming_config, load_seed_catalog


_MINIMAL_CATALOG = {
    "celestial": {
        "planets": ["Earth"],
        "moons": [],
        "asteroids": [],
        "distance_order": {"Earth": 1, "Asteroid Belt": 2},
    },
    "stations": {
        "templates": [
            {
                "body_type": "planet",
                "id_prefix": "STN-PLANET",
                "name_template": "{body} Prime Port",
                "allowed_size_classes": ["small", "medium", "large", "xlarge"],
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
                "allowed_size_classes": ["small", "medium", "large", "xlarge"],
            },
        ]
    },
    "ship_generation": {
        "faction_distribution": {"merchant": 1.0},
        "ship_types": [
            {
                "name": "Freighter",
                "faction": "merchant",
                "size_class": "medium",
                "displacement_min_million_m3": 0.8,
                "displacement_max_million_m3": 5.0,
            }
        ],
        "cargo_types": ["water_ice"],
        "naming": {
            "adjectives": ["Solar"],
            "nouns": ["Voyager"],
            "captain_first": ["Avery"],
            "captain_last": ["Voss"],
        },
        "defaults": {"ship_count": 50, "ship_seed": 42},
    },
    "lifecycle": {
        "decommission": {
            "enabled": False,
            "base_probability_per_day": 0.0,
            "age_years_soft_limit": 10,
            "age_acceleration_per_year": 0.0,
            "max_probability_per_day": 0.0,
        },
        "war_impact": {
            "enabled": False,
            "base_probability_per_day": 0.0,
            "faction_loss_multiplier": {"merchant": 1.0},
            "max_losses_per_event": 1,
        },
        "build_queue": {
            "enabled": False,
            "base_builds_per_day": 0.0,
            "max_builds_per_day": 1,
            "faction_distribution": {"merchant": 1.0},
            "spawn_policy": "compatible_random_station",
        },
        "pirate_activity": {
            "enabled": False,
            "allowed_anchors": ["Earth"],
            "strength_start": 1.0,
            "strength_end_threshold": 0.5,
            "merchant_arrival_destruction_multiplier": 1.0,
            "strength_decay_per_bounty_hunter_arrival": 0.01,
            "respawn_min_days": 10,
            "respawn_max_days": 20,
        },
    },
}


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


def test_load_naming_config_raises_on_invalid_json():
    with TemporaryDirectory() as tmp:
        path = f"{tmp}/bad_naming.json"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{invalid json}")

        with pytest.raises(ValueError, match="Failed to parse JSON in naming config"):
            load_naming_config(path)


def test_build_ships_uses_singular_names_from_naming_config():
    """When naming_config has ship_names_singular, ~50% of ships use names from that list."""
    singular_names = {"Nebula Drifter", "Star Ghost", "Ion Veil"}

    with TemporaryDirectory() as tmp:
        catalog_path = f"{tmp}/catalog.json"
        with open(catalog_path, "w", encoding="utf-8") as fh:
            json.dump(_MINIMAL_CATALOG, fh)

        with patch("space_traffic_api.seed_data.load_naming_config") as mock_load:
            mock_load.return_value = {"ship_names_singular": list(singular_names)}
            stations = build_stations(catalog_path=catalog_path)
            ships = build_ships(stations=stations, count=50, seed=42, catalog_path=catalog_path)

    ship_names = [s["name"] for s in ships]
    assert any(name in singular_names for name in ship_names), (
        "Expected at least one ship named from ship_names_singular"
    )
    assert any(name not in singular_names for name in ship_names), (
        "Expected some ships to still use adjective+noun naming when singular names are present"
    )


def test_build_ships_uses_only_adjective_noun_without_singular_config():
    """Without ship_names_singular, all ship names follow adjective+noun format from the catalog."""
    with TemporaryDirectory() as tmp:
        catalog_path = f"{tmp}/catalog.json"
        with open(catalog_path, "w", encoding="utf-8") as fh:
            json.dump(_MINIMAL_CATALOG, fh)

        with patch("space_traffic_api.seed_data.load_naming_config") as mock_load:
            mock_load.return_value = {}
            stations = build_stations(catalog_path=catalog_path)
            ships = build_ships(stations=stations, count=10, seed=42, catalog_path=catalog_path)

    for ship in ships:
        assert ship["name"] == "Solar Voyager", (
            f"Expected 'Solar Voyager' (adjective+noun from catalog), got '{ship['name']}'"
        )


def test_build_ships_catalog_naming_takes_priority_over_naming_config():
    """Catalog adjectives/nouns take priority over naming_config adjectives/nouns."""
    with TemporaryDirectory() as tmp:
        catalog_path = f"{tmp}/catalog.json"
        with open(catalog_path, "w", encoding="utf-8") as fh:
            json.dump(_MINIMAL_CATALOG, fh)

        with patch("space_traffic_api.seed_data.load_naming_config") as mock_load:
            mock_load.return_value = {
                "adjectives": ["Cosmic"],
                "nouns": ["Wanderer"],
            }
            stations = build_stations(catalog_path=catalog_path)
            ships = build_ships(stations=stations, count=10, seed=42, catalog_path=catalog_path)

    for ship in ships:
        assert ship["name"] == "Solar Voyager", (
            f"Catalog adjectives/nouns should take priority over naming_config; got '{ship['name']}'"
        )


def test_build_stations_validates_invalid_base_names_singular():
    """If naming_config base_names_singular is not a list of strings, build_stations should raise."""
    with TemporaryDirectory() as tmp:
        catalog_path = f"{tmp}/catalog.json"
        with open(catalog_path, "w", encoding="utf-8") as fh:
            json.dump(_MINIMAL_CATALOG, fh)

        with patch("space_traffic_api.seed_data.load_naming_config") as mock_load:
            mock_load.return_value = {"base_names_singular": "not-a-list"}
            with pytest.raises(ValueError, match="naming.base_names_singular"):
                build_stations(catalog_path=catalog_path)

