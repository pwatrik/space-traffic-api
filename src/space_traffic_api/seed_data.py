from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

def _default_catalog_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "catalog_config.json"


def _ensure_str_list(path: str, value: Any, *, min_items: int = 1) -> list[str]:
    if not isinstance(value, list) or len(value) < min_items or not all(isinstance(item, str) and item for item in value):
        if min_items > 0:
            raise ValueError(f"{path} must be an array of strings with at least {min_items} item(s)")
        raise ValueError(f"{path} must be an array of strings")
    return list(value)


def _sanitize_station_token(raw: str) -> str:
    return re.sub(r"[^A-Z0-9_]+", "_", raw.upper()).strip("_")


def _normalize_size_classes(path: str, value: Any) -> list[str]:
    classes = _ensure_str_list(path, value, min_items=1)
    return [item.strip().lower() for item in classes]


def load_seed_catalog(catalog_path: str | None = None) -> dict[str, Any]:
    path = Path(catalog_path) if catalog_path else _default_catalog_path()
    if not path.exists():
        raise ValueError(f"seed catalog file does not exist: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid seed catalog JSON at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("seed catalog root must be an object")

    celestial = raw.get("celestial")
    stations = raw.get("stations")
    ship_generation = raw.get("ship_generation")
    if not isinstance(celestial, dict):
        raise ValueError("celestial must be an object")
    if not isinstance(stations, dict):
        raise ValueError("stations must be an object")
    if not isinstance(ship_generation, dict):
        raise ValueError("ship_generation must be an object")

    planets = _ensure_str_list("celestial.planets", celestial.get("planets"), min_items=1)
    asteroids = _ensure_str_list("celestial.asteroids", celestial.get("asteroids"), min_items=0)

    moons_raw = celestial.get("moons")
    if not isinstance(moons_raw, list):
        raise ValueError("celestial.moons must be an array")
    moons: list[dict[str, str]] = []
    for idx, moon in enumerate(moons_raw):
        if not isinstance(moon, dict):
            raise ValueError(f"celestial.moons[{idx}] must be an object")
        name = moon.get("name")
        parent = moon.get("parent")
        if not isinstance(name, str) or not name or not isinstance(parent, str) or not parent:
            raise ValueError(f"celestial.moons[{idx}] must include non-empty name and parent")
        moons.append({"name": name, "parent": parent})

    distance_order = celestial.get("distance_order")
    if not isinstance(distance_order, dict) or not distance_order:
        raise ValueError("celestial.distance_order must be a non-empty object")
    normalized_distance_order: dict[str, int] = {}
    for key, value in distance_order.items():
        if not isinstance(key, str) or not key:
            raise ValueError("celestial.distance_order keys must be non-empty strings")
        if not isinstance(value, int) or value < 0:
            raise ValueError("celestial.distance_order values must be non-negative integers")
        normalized_distance_order[key] = value

    templates_raw = stations.get("templates")
    if not isinstance(templates_raw, list) or not templates_raw:
        raise ValueError("stations.templates must be a non-empty array")
    station_templates: dict[str, dict[str, Any]] = {}
    for idx, template in enumerate(templates_raw):
        if not isinstance(template, dict):
            raise ValueError(f"stations.templates[{idx}] must be an object")
        body_type = template.get("body_type")
        id_prefix = template.get("id_prefix")
        name_template = template.get("name_template")
        if not isinstance(body_type, str) or not body_type:
            raise ValueError(f"stations.templates[{idx}].body_type must be a non-empty string")
        if not isinstance(id_prefix, str) or not id_prefix:
            raise ValueError(f"stations.templates[{idx}].id_prefix must be a non-empty string")
        if not isinstance(name_template, str) or "{body}" not in name_template:
            raise ValueError(f"stations.templates[{idx}].name_template must include {{body}}")
        raw_size_classes = template.get("allowed_size_classes", ["small", "medium", "large", "xlarge"])
        station_templates[body_type] = {
            "id_prefix": id_prefix,
            "name_template": name_template,
            "parent_body": str(template.get("parent_body", "")),
            "allowed_size_classes": _normalize_size_classes(
                f"stations.templates[{idx}].allowed_size_classes", raw_size_classes
            ),
        }

    faction_distribution = ship_generation.get("faction_distribution")
    if not isinstance(faction_distribution, dict) or not faction_distribution:
        raise ValueError("ship_generation.faction_distribution must be a non-empty object")
    normalized_distribution: dict[str, float] = {}
    for faction, weight in faction_distribution.items():
        if not isinstance(faction, str) or not faction:
            raise ValueError("ship_generation.faction_distribution keys must be non-empty strings")
        if not isinstance(weight, (int, float)) or float(weight) <= 0:
            raise ValueError("ship_generation.faction_distribution values must be positive numbers")
        normalized_distribution[faction] = float(weight)

    ship_types_raw = ship_generation.get("ship_types")
    if not isinstance(ship_types_raw, list) or not ship_types_raw:
        raise ValueError("ship_generation.ship_types must be a non-empty array")
    ship_types: list[dict[str, Any]] = []
    for idx, row in enumerate(ship_types_raw):
        if not isinstance(row, dict):
            raise ValueError(f"ship_generation.ship_types[{idx}] must be an object")
        name = row.get("name")
        faction = row.get("faction")
        size_class = row.get("size_class")
        if not isinstance(name, str) or not name:
            raise ValueError(f"ship_generation.ship_types[{idx}].name must be a non-empty string")
        if not isinstance(faction, str) or not faction:
            raise ValueError(f"ship_generation.ship_types[{idx}].faction must be a non-empty string")
        if not isinstance(size_class, str) or not size_class.strip():
            raise ValueError(f"ship_generation.ship_types[{idx}].size_class must be a non-empty string")
        normalized = dict(row)
        normalized["size_class"] = size_class.strip().lower()
        ship_types.append(normalized)

    naming = ship_generation.get("naming")
    if not isinstance(naming, dict):
        raise ValueError("ship_generation.naming must be an object")

    defaults = ship_generation.get("defaults")
    if not isinstance(defaults, dict):
        raise ValueError("ship_generation.defaults must be an object")
    ship_count = defaults.get("ship_count", 220)
    ship_seed = defaults.get("ship_seed", 9001)
    if not isinstance(ship_count, int) or ship_count < 1:
        raise ValueError("ship_generation.defaults.ship_count must be a positive integer")
    if not isinstance(ship_seed, int):
        raise ValueError("ship_generation.defaults.ship_seed must be an integer")

    return {
        "celestial": {
            "planets": planets,
            "moons": moons,
            "asteroids": asteroids,
            "distance_order": normalized_distance_order,
        },
        "stations": {
            "templates": station_templates,
        },
        "ship_generation": {
            "faction_distribution": normalized_distribution,
            "ship_types": ship_types,
            "cargo_types": _ensure_str_list("ship_generation.cargo_types", ship_generation.get("cargo_types"), min_items=1),
            "naming": {
                "adjectives": _ensure_str_list("ship_generation.naming.adjectives", naming.get("adjectives"), min_items=1),
                "nouns": _ensure_str_list("ship_generation.naming.nouns", naming.get("nouns"), min_items=1),
                "captain_first": _ensure_str_list("ship_generation.naming.captain_first", naming.get("captain_first"), min_items=1),
                "captain_last": _ensure_str_list("ship_generation.naming.captain_last", naming.get("captain_last"), min_items=1),
            },
            "defaults": {
                "ship_count": ship_count,
                "ship_seed": ship_seed,
            },
        },
    }


def build_stations(catalog_path: str | None = None) -> list[dict[str, Any]]:
    catalog = load_seed_catalog(catalog_path)
    templates = catalog["stations"]["templates"]
    stations: list[dict[str, Any]] = []

    for planet in catalog["celestial"]["planets"]:
        template = templates["planet"]
        sid = f"{template['id_prefix']}-{_sanitize_station_token(planet)}"
        stations.append(
            {
                "id": sid,
                "name": template["name_template"].format(body=planet),
                "body_name": planet,
                "body_type": "planet",
                "parent_body": planet,
                "allowed_size_classes": template["allowed_size_classes"],
            }
        )

    for moon in catalog["celestial"]["moons"]:
        moon_name = moon["name"]
        parent = moon["parent"]
        template = templates["moon"]
        sid = f"{template['id_prefix']}-{_sanitize_station_token(moon_name)}"
        stations.append(
            {
                "id": sid,
                "name": template["name_template"].format(body=moon_name),
                "body_name": moon_name,
                "body_type": "moon",
                "parent_body": parent,
                "allowed_size_classes": template["allowed_size_classes"],
            }
        )

    for asteroid in catalog["celestial"]["asteroids"]:
        template = templates["asteroid"]
        sid = f"{template['id_prefix']}-{_sanitize_station_token(asteroid)}"
        stations.append(
            {
                "id": sid,
                "name": template["name_template"].format(body=asteroid),
                "body_name": asteroid,
                "body_type": "asteroid",
                "parent_body": template["parent_body"] or "Asteroid Belt",
                "allowed_size_classes": template["allowed_size_classes"],
            }
        )

    return stations


def _pick_faction(rng: random.Random, faction_distribution: dict[str, float]) -> str:
    total = sum(faction_distribution.values())
    threshold = rng.random() * total
    running = 0.0
    for faction, weight in faction_distribution.items():
        running += weight
        if threshold <= running:
            return faction
    return next(iter(faction_distribution))


def build_ships(
    stations: list[dict[str, Any]],
    count: int | None = None,
    seed: int | None = None,
    catalog_path: str | None = None,
) -> list[dict[str, Any]]:
    catalog = load_seed_catalog(catalog_path)
    ship_generation = catalog["ship_generation"]
    defaults = ship_generation["defaults"]
    ship_types_by_faction: dict[str, list[dict[str, Any]]] = {}
    for row in ship_generation["ship_types"]:
        ship_types_by_faction.setdefault(row["faction"], []).append(row)

    if count is None:
        count = int(defaults["ship_count"])
    if seed is None:
        seed = int(defaults["ship_seed"])

    rng = random.Random(seed)
    ships: list[dict[str, Any]] = []
    station_ids = [row["id"] for row in stations]
    station_capabilities = {
        row["id"]: {str(item).strip().lower() for item in row.get("allowed_size_classes", [])}
        for row in stations
    }
    naming = ship_generation["naming"]

    for i in range(1, count + 1):
        faction = _pick_faction(rng, ship_generation["faction_distribution"])
        ship_type_options = ship_types_by_faction.get(faction)
        if not ship_type_options:
            ship_type_options = list(ship_generation["ship_types"])
        ship_type_choice = rng.choice(ship_type_options)
        ship_type = ship_type_choice["name"]
        size_class = ship_type_choice["size_class"]

        compatible_station_ids = [
            station_id
            for station_id in station_ids
            if not station_capabilities.get(station_id) or size_class in station_capabilities[station_id]
        ]
        home_station_id = rng.choice(compatible_station_ids or station_ids)

        ship_name = f"{rng.choice(naming['adjectives'])} {rng.choice(naming['nouns'])}"
        captain = f"{rng.choice(naming['captain_first'])} {rng.choice(naming['captain_last'])}"
        cargo = rng.choice(ship_generation["cargo_types"])

        ships.append(
            {
                "id": f"SHIP-{i:04d}",
                "name": ship_name,
                "faction": faction,
                "ship_type": ship_type,
                "size_class": size_class,
                "displacement_million_m3": round(rng.uniform(0.8, 22.0), 3),
                "home_station_id": home_station_id,
                "captain_name": captain,
                "cargo": cargo,
            }
        )

    return ships


def station_distance_groups(stations: list[dict[str, Any]], catalog_path: str | None = None) -> dict[str, int]:
    """
    Compute distance groups for stations based solely on the provided station data.

    The optional ``catalog_path`` parameter is accepted for backwards compatibility
    but is ignored, so this function does not depend on any external catalog
    configuration. This ensures consistent behavior even when custom catalogs
    are used elsewhere in the application.
    """
    grouping: dict[str, int] = {}
    body_groups: dict[str, int] = {}
    next_group = 0

    for row in stations:
        station_id = row["id"]

        # Prefer an explicit distance_group field if present.
        explicit_group = row.get("distance_group")
        if isinstance(explicit_group, int):
            grouping[station_id] = explicit_group
            continue

        body = row.get("parent_body") or row.get("body_name")
        if not body:
            # Fallback group if no body information is available.
            grouping[station_id] = 5
            continue

        if body not in body_groups:
            body_groups[body] = next_group
            next_group += 1

        grouping[station_id] = body_groups[body]
    return grouping
