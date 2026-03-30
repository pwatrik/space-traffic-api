from __future__ import annotations

import random
from typing import Any


_PLANETS = [
    "Mercury",
    "Venus",
    "Earth",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
]

_MOONS = [
    ("Moon", "Earth"),
    ("Phobos", "Mars"),
    ("Deimos", "Mars"),
    ("Io", "Jupiter"),
    ("Europa", "Jupiter"),
    ("Ganymede", "Jupiter"),
    ("Callisto", "Jupiter"),
    ("Titan", "Saturn"),
    ("Enceladus", "Saturn"),
    ("Rhea", "Saturn"),
    ("Dione", "Saturn"),
    ("Iapetus", "Saturn"),
    ("Mimas", "Saturn"),
    ("Tethys", "Saturn"),
    ("Miranda", "Uranus"),
    ("Ariel", "Uranus"),
    ("Umbriel", "Uranus"),
    ("Titania", "Uranus"),
    ("Oberon", "Uranus"),
    ("Triton", "Neptune"),
    ("Charon", "Pluto"),
]

_ASTEROIDS = [
    "Ceres",
    "Vesta",
    "Pallas",
    "Hygiea",
    "Eros",
    "Psyche",
    "Juno",
    "Davida",
    "Interamnia",
    "Europa-Asteroid",
]

_MERCHANT_SHIP_TYPES = ["Freighter", "Bulk Carrier", "Tanker", "Courier", "Passenger Liner"]
_GOVERNMENT_SHIP_TYPES = ["Surveyor", "Diplomatic Transport", "Research Vessel", "Colony Support"]
_MILITARY_SHIP_TYPES = ["Destroyer", "Frigate", "Interceptor", "Carrier", "Recon Cruiser"]

_CARGO_TYPES = [
    "rare_earth_metals",
    "foodstuffs",
    "cryogenic_fuel",
    "medical_supplies",
    "consumer_goods",
    "reactor_parts",
    "water_ice",
    "helium-3",
    "construction_materials",
    "defense_systems",
]


_ADJECTIVES = [
    "Aurora",
    "Crimson",
    "Silent",
    "Iron",
    "Emerald",
    "Solar",
    "Vigilant",
    "Endless",
    "Nebula",
    "Radiant",
    "Atlas",
    "Frontier",
    "Zenith",
    "Orion",
]

_NOUNS = [
    "Pioneer",
    "Arrow",
    "Harbor",
    "Drift",
    "Sentinel",
    "Voyager",
    "Mercy",
    "Comet",
    "Mariner",
    "Falcon",
    "Dawn",
    "Vector",
    "Relay",
    "Nomad",
]

_CAPTAIN_FIRST = [
    "Avery",
    "Sloan",
    "Kai",
    "Morgan",
    "Rin",
    "Jordan",
    "Harper",
    "Rowan",
    "Dakota",
    "Elliot",
    "Alex",
    "Sam",
]

_CAPTAIN_LAST = [
    "Voss",
    "Kade",
    "Shaw",
    "Miro",
    "Nolan",
    "Vega",
    "Drake",
    "Ibarra",
    "Sato",
    "Rhee",
    "Navarro",
    "Petrov",
]


def build_stations() -> list[dict[str, Any]]:
    stations: list[dict[str, Any]] = []

    for planet in _PLANETS:
        sid = f"STN-PLANET-{planet.upper()}"
        stations.append(
            {
                "id": sid,
                "name": f"{planet} Prime Port",
                "body_name": planet,
                "body_type": "planet",
                "parent_body": planet,
            }
        )

    for moon, parent in _MOONS:
        sid = f"STN-MOON-{moon.upper().replace('-', '_')}"
        stations.append(
            {
                "id": sid,
                "name": f"{moon} Orbital",
                "body_name": moon,
                "body_type": "moon",
                "parent_body": parent,
            }
        )

    for asteroid in _ASTEROIDS:
        sid = f"STN-AST-{asteroid.upper().replace('-', '_')}"
        stations.append(
            {
                "id": sid,
                "name": f"{asteroid} Hub",
                "body_name": asteroid,
                "body_type": "asteroid",
                "parent_body": "Asteroid Belt",
            }
        )

    return stations


def build_ships(stations: list[dict[str, Any]], count: int = 220, seed: int = 1001) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    ships: list[dict[str, Any]] = []
    station_ids = [row["id"] for row in stations]

    for i in range(1, count + 1):
        faction_roll = rng.random()
        if faction_roll < 0.60:
            faction = "merchant"
            ship_type = rng.choice(_MERCHANT_SHIP_TYPES)
        elif faction_roll < 0.85:
            faction = "government"
            ship_type = rng.choice(_GOVERNMENT_SHIP_TYPES)
        else:
            faction = "military"
            ship_type = rng.choice(_MILITARY_SHIP_TYPES)

        ship_name = f"{rng.choice(_ADJECTIVES)} {rng.choice(_NOUNS)}"
        captain = f"{rng.choice(_CAPTAIN_FIRST)} {rng.choice(_CAPTAIN_LAST)}"
        cargo = rng.choice(_CARGO_TYPES)

        ships.append(
            {
                "id": f"SHIP-{i:04d}",
                "name": ship_name,
                "faction": faction,
                "ship_type": ship_type,
                "displacement_million_m3": round(rng.uniform(0.8, 22.0), 3),
                "home_station_id": rng.choice(station_ids),
                "captain_name": captain,
                "cargo": cargo,
            }
        )

    return ships


def station_distance_groups(stations: list[dict[str, Any]]) -> dict[str, int]:
    order = {
        "Mercury": 1,
        "Venus": 2,
        "Earth": 3,
        "Mars": 4,
        "Asteroid Belt": 5,
        "Jupiter": 6,
        "Saturn": 7,
        "Uranus": 8,
        "Neptune": 9,
        "Pluto": 10,
    }
    grouping: dict[str, int] = {}
    for row in stations:
        grouping[row["id"]] = order.get(row["parent_body"], order.get(row["body_name"], 5))
    return grouping
