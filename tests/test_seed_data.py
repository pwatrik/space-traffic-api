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
    assert len(ships) == 220
    assert ships[0]["id"] == "SHIP-0001"


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
                {"body_type": "planet", "id_prefix": "STN-PLANET", "name_template": "{body} Prime Port"},
                {"body_type": "moon", "id_prefix": "STN-MOON", "name_template": "{body} Orbital"},
                {
                    "body_type": "asteroid",
                    "id_prefix": "STN-AST",
                    "name_template": "{body} Hub",
                    "parent_body": "Asteroid Belt",
                },
            ]
        },
        "ship_generation": {
            "faction_distribution": {"merchant": 1.0},
            "ship_types": [{"name": "Freighter", "faction": "merchant"}],
            "cargo_types": ["water_ice"],
            "naming": {
                "adjectives": ["Solar"],
                "nouns": ["Voyager"],
                "captain_first": ["Avery"],
                "captain_last": ["Voss"],
            },
            "defaults": {"ship_count": 3, "ship_seed": 42},
        },
    }

    with TemporaryDirectory() as tmp:
        path = f"{tmp}/catalog.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(custom, fh)

        stations = build_stations(catalog_path=path)
        ships = build_ships(stations=stations, catalog_path=path)

    assert len(stations) == 2
    assert len(ships) == 3
    assert all(ship["ship_type"] == "Freighter" for ship in ships)


def test_invalid_seed_catalog_raises():
    with TemporaryDirectory() as tmp:
        path = f"{tmp}/broken.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"celestial": {}}, fh)

        with pytest.raises(ValueError):
            load_seed_catalog(path)
