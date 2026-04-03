from __future__ import annotations

import json
import math
import random
import re
from pathlib import Path
from typing import Any

def _default_catalog_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "catalog_config.json"


def _default_naming_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "naming_config.json"


def load_naming_config(naming_path: str | None = None) -> dict[str, Any]:
    path = Path(naming_path) if naming_path else _default_naming_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse JSON in naming config at {path}") from exc
    except OSError as exc:
        raise ValueError(f"Failed to read naming config at {path}") from exc


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
    normalized = [item.strip().lower() for item in classes]
    if not all(normalized):
        raise ValueError(f"{path} entries must be non-empty strings after normalization")
    return normalized


def _ensure_probability(path: str, value: Any) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number")
    probability = float(value)
    if probability < 0:
        raise ValueError(f"{path} must be non-negative")
    return probability


def _ensure_positive_number(path: str, value: Any) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number")
    number = float(value)
    if number <= 0:
        raise ValueError(f"{path} must be greater than 0")
    return number


def _ensure_non_negative_number(path: str, value: Any) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number")
    number = float(value)
    if number < 0:
        raise ValueError(f"{path} must be non-negative")
    return number


def _normalize_weight_map(path: str, value: Any) -> dict[str, float]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{path} must be a non-empty object")

    weights: dict[str, float] = {}
    for key, raw_weight in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{path} keys must be non-empty strings")
        if not isinstance(raw_weight, (int, float)) or float(raw_weight) <= 0:
            raise ValueError(f"{path}.{key} must be a positive number")
        weights[key.strip().lower()] = float(raw_weight)
    return weights


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
        parent_body_raw = template.get("parent_body")
        if parent_body_raw is not None and not isinstance(parent_body_raw, str):
            raise ValueError(f"stations.templates[{idx}].parent_body must be a string or null")
        station_templates[body_type] = {
            "id_prefix": id_prefix,
            "name_template": name_template,
            "parent_body": parent_body_raw or "",
            "allowed_size_classes": _normalize_size_classes(
                f"stations.templates[{idx}].allowed_size_classes", raw_size_classes
            ),
        }

    normalized_distribution = _normalize_weight_map(
        "ship_generation.faction_distribution", ship_generation.get("faction_distribution")
    )

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
        normalized_faction = faction.strip().lower()
        if normalized_faction not in normalized_distribution:
            raise ValueError(
                f"ship_generation.ship_types[{idx}].faction '{normalized_faction}' must exist in "
                "ship_generation.faction_distribution"
            )
        displacement_min = _ensure_non_negative_number(
            f"ship_generation.ship_types[{idx}].displacement_min_million_m3",
            row.get("displacement_min_million_m3", 0.8),
        )
        displacement_max = _ensure_non_negative_number(
            f"ship_generation.ship_types[{idx}].displacement_max_million_m3",
            row.get("displacement_max_million_m3", 22.0),
        )
        if displacement_max < displacement_min:
            raise ValueError(
                f"ship_generation.ship_types[{idx}].displacement_max_million_m3 must be >= "
                "displacement_min_million_m3"
            )
        normalized = dict(row)
        normalized["faction"] = normalized_faction
        normalized["size_class"] = size_class.strip().lower()
        normalized["displacement_min_million_m3"] = displacement_min
        normalized["displacement_max_million_m3"] = displacement_max
        ship_types.append(normalized)

    naming = ship_generation.get("naming")
    if naming is not None and not isinstance(naming, dict):
        raise ValueError("ship_generation.naming must be an object")
    naming = naming or {}

    naming_fallback = load_naming_config()

    def _resolve_naming_list(key: str, default: list[str]) -> list[str]:
        if key in naming:
            value = naming.get(key)
        else:
            value = naming_fallback.get(key, default)
        return _ensure_str_list(f"ship_generation.naming.{key}", value, min_items=1)

    defaults = ship_generation.get("defaults")
    if not isinstance(defaults, dict):
        raise ValueError("ship_generation.defaults must be an object")
    ship_count = defaults.get("ship_count", 500)
    ship_seed = defaults.get("ship_seed", 9001)
    ship_speed_multiplier = defaults.get("ship_speed_multiplier", 84.0)
    if not isinstance(ship_count, int) or ship_count < 1:
        raise ValueError("ship_generation.defaults.ship_count must be a positive integer")
    if not isinstance(ship_seed, int):
        raise ValueError("ship_generation.defaults.ship_seed must be an integer")
    ship_speed_multiplier = _ensure_positive_number(
        "ship_generation.defaults.ship_speed_multiplier",
        ship_speed_multiplier,
    )

    lifecycle_raw = raw.get("lifecycle", {})
    if lifecycle_raw is None:
        lifecycle_raw = {}
    if not isinstance(lifecycle_raw, dict):
        raise ValueError("lifecycle must be an object")

    decommission_raw = lifecycle_raw.get("decommission", {})
    if decommission_raw is None:
        decommission_raw = {}
    if not isinstance(decommission_raw, dict):
        raise ValueError("lifecycle.decommission must be an object")
    decommission = {
        "enabled": bool(decommission_raw.get("enabled", True)),
        "base_probability_per_day": _ensure_probability(
            "lifecycle.decommission.base_probability_per_day",
            decommission_raw.get("base_probability_per_day", 0.0006),
        ),
        "age_years_soft_limit": _ensure_positive_number(
            "lifecycle.decommission.age_years_soft_limit",
            decommission_raw.get("age_years_soft_limit", 18),
        ),
        "age_acceleration_per_year": _ensure_probability(
            "lifecycle.decommission.age_acceleration_per_year",
            decommission_raw.get("age_acceleration_per_year", 0.00025),
        ),
        "max_probability_per_day": _ensure_probability(
            "lifecycle.decommission.max_probability_per_day",
            decommission_raw.get("max_probability_per_day", 0.015),
        ),
    }

    war_raw = lifecycle_raw.get("war_impact", {})
    if war_raw is None:
        war_raw = {}
    if not isinstance(war_raw, dict):
        raise ValueError("lifecycle.war_impact must be an object")
    war_faction_multipliers = _normalize_weight_map(
        "lifecycle.war_impact.faction_loss_multiplier",
        war_raw.get(
            "faction_loss_multiplier",
            {"merchant": 1.35, "government": 1.0, "military": 0.7},
        ),
    )
    max_losses_per_event = war_raw.get("max_losses_per_event", 3)
    if not isinstance(max_losses_per_event, int) or max_losses_per_event < 1:
        raise ValueError("lifecycle.war_impact.max_losses_per_event must be a positive integer")
    war_impact = {
        "enabled": bool(war_raw.get("enabled", True)),
        "base_probability_per_day": _ensure_probability(
            "lifecycle.war_impact.base_probability_per_day",
            war_raw.get("base_probability_per_day", 0.0012),
        ),
        "faction_loss_multiplier": war_faction_multipliers,
        "max_losses_per_event": max_losses_per_event,
    }

    build_raw = lifecycle_raw.get("build_queue", {})
    if build_raw is None:
        build_raw = {}
    if not isinstance(build_raw, dict):
        raise ValueError("lifecycle.build_queue must be an object")
    max_builds_per_day = build_raw.get("max_builds_per_day", 5)
    if not isinstance(max_builds_per_day, int) or max_builds_per_day < 1:
        raise ValueError("lifecycle.build_queue.max_builds_per_day must be a positive integer")
    spawn_policy = build_raw.get("spawn_policy", "compatible_random_station")
    if not isinstance(spawn_policy, str) or not spawn_policy.strip():
        raise ValueError("lifecycle.build_queue.spawn_policy must be a non-empty string")
    build_queue = {
        "enabled": bool(build_raw.get("enabled", True)),
        "base_builds_per_day": _ensure_probability(
            "lifecycle.build_queue.base_builds_per_day",
            build_raw.get("base_builds_per_day", 1.8),
        ),
        "max_builds_per_day": max_builds_per_day,
        "faction_distribution": _normalize_weight_map(
            "lifecycle.build_queue.faction_distribution",
            build_raw.get("faction_distribution", normalized_distribution),
        ),
        "spawn_policy": spawn_policy.strip().lower(),
    }

    pirate_raw = lifecycle_raw.get("pirate_activity", {})
    if pirate_raw is None:
        pirate_raw = {}
    if not isinstance(pirate_raw, dict):
        raise ValueError("lifecycle.pirate_activity must be an object")

    anchors_default = list(planets)
    if "Asteroid Belt" not in anchors_default:
        anchors_default.append("Asteroid Belt")
    allowed_anchors = _ensure_str_list(
        "lifecycle.pirate_activity.allowed_anchors",
        pirate_raw.get("allowed_anchors", anchors_default),
        min_items=1,
    )
    allowed_anchor_list = list(dict.fromkeys(allowed_anchors))
    for anchor in allowed_anchor_list:
        if anchor not in normalized_distance_order:
            raise ValueError(
                "lifecycle.pirate_activity.allowed_anchors entries must exist in "
                "celestial.distance_order"
            )

    strength_start = _ensure_positive_number(
        "lifecycle.pirate_activity.strength_start",
        pirate_raw.get("strength_start", 1.0),
    )
    strength_end_threshold = _ensure_positive_number(
        "lifecycle.pirate_activity.strength_end_threshold",
        pirate_raw.get("strength_end_threshold", 0.5),
    )
    if strength_end_threshold >= strength_start:
        raise ValueError("lifecycle.pirate_activity.strength_end_threshold must be less than strength_start")

    respawn_min_days = _ensure_non_negative_number(
        "lifecycle.pirate_activity.respawn_min_days",
        pirate_raw.get("respawn_min_days", 10.0),
    )
    respawn_max_days = _ensure_non_negative_number(
        "lifecycle.pirate_activity.respawn_max_days",
        pirate_raw.get("respawn_max_days", 30.0),
    )
    if respawn_max_days < respawn_min_days:
        raise ValueError("lifecycle.pirate_activity.respawn_max_days must be >= respawn_min_days")

    pirate_activity = {
        "enabled": bool(pirate_raw.get("enabled", True)),
        "allowed_anchors": allowed_anchor_list,
        "strength_start": strength_start,
        "strength_end_threshold": strength_end_threshold,
        "ambient_strength_decay_per_day": _ensure_non_negative_number(
            "lifecycle.pirate_activity.ambient_strength_decay_per_day",
            pirate_raw.get("ambient_strength_decay_per_day", 0.0),
        ),
        "merchant_arrival_base_destruction_chance": _ensure_probability(
            "lifecycle.pirate_activity.merchant_arrival_base_destruction_chance",
            pirate_raw.get("merchant_arrival_base_destruction_chance", 0.04),
        ),
        "merchant_arrival_destruction_multiplier": _ensure_positive_number(
            "lifecycle.pirate_activity.merchant_arrival_destruction_multiplier",
            pirate_raw.get("merchant_arrival_destruction_multiplier", 4.0),
        ),
        "bounty_hunter_response_bias": _ensure_probability(
            "lifecycle.pirate_activity.bounty_hunter_response_bias",
            pirate_raw.get("bounty_hunter_response_bias", 0.9),
        ),
        "bounty_hunter_idle_departure_multiplier": _ensure_non_negative_number(
            "lifecycle.pirate_activity.bounty_hunter_idle_departure_multiplier",
            pirate_raw.get("bounty_hunter_idle_departure_multiplier", 0.2),
        ),
        "bounty_hunter_active_departure_multiplier": _ensure_non_negative_number(
            "lifecycle.pirate_activity.bounty_hunter_active_departure_multiplier",
            pirate_raw.get("bounty_hunter_active_departure_multiplier", 6.0),
        ),
        "strength_decay_per_bounty_hunter_arrival": _ensure_non_negative_number(
            "lifecycle.pirate_activity.strength_decay_per_bounty_hunter_arrival",
            pirate_raw.get("strength_decay_per_bounty_hunter_arrival", 0.02),
        ),
        "respawn_min_days": respawn_min_days,
        "respawn_max_days": respawn_max_days,
    }

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
                "adjectives": _resolve_naming_list("adjectives", ["Solar"]),
                "nouns": _resolve_naming_list("nouns", ["Pioneer"]),
                "captain_first": _resolve_naming_list("captain_first", ["Alex"]),
                "captain_last": _resolve_naming_list("captain_last", ["Voss"]),
            },
            "defaults": {
                "ship_count": ship_count,
                "ship_seed": ship_seed,
                "ship_speed_multiplier": ship_speed_multiplier,
            },
        },
        "lifecycle": {
            "decommission": decommission,
            "war_impact": war_impact,
            "build_queue": build_queue,
            "pirate_activity": pirate_activity,
        },
    }


def build_stations(catalog_path: str | None = None, catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    catalog = catalog or load_seed_catalog(catalog_path)
    templates = catalog["stations"]["templates"]
    stations: list[dict[str, Any]] = []
    cargo_types = list(catalog.get("ship_generation", {}).get("cargo_types", []))
    if not cargo_types:
        cargo_types = ["general_supplies"]

    naming_ext = load_naming_config()
    raw_base_names = naming_ext.get("base_names_singular")
    if raw_base_names is not None:
        base_names = _ensure_str_list("naming.base_names_singular", raw_base_names, min_items=0)
    else:
        base_names = []
    if base_names:
        ship_seed = int(((catalog.get("ship_generation") or {}).get("defaults") or {}).get("ship_seed", 9001))
        random.Random(ship_seed).shuffle(base_names)
    _name_counter = [0]
    _style_counter = [0]

    large_planetoids = {
        "Mercury",
        "Venus",
        "Earth",
        "Mars",
        "Moon",
        "Triton",
        "Ceres",
    }
    rng = random.Random(int(((catalog.get("ship_generation") or {}).get("defaults") or {}).get("ship_seed", 9001)) + 17)
    nickname_pool = ["The Edge", "The Narrows", "The Beacon", "The Spindle", "The Lantern"]
    designation_prefixes = ["HX", "AX", "CN", "OR", "VX", "RZ"]

    def _is_large_planetoid(body_name: str) -> bool:
        return body_name in large_planetoids

    def _station_count(min_count: int, max_count: int) -> int:
        if max_count <= min_count:
            return min_count
        return rng.randint(min_count, max_count)

    def _station_cargo() -> str:
        return rng.choice(cargo_types)

    def _station_economy_profile(body_type: str) -> dict[str, float | str]:
        # These are placeholder station attributes for Milestone 2 economy work.
        baseline = {
            "planet": {
                "temperature_band": "temperate",
                "food_production": 0.75,
                "oxygen": 0.80,
                "water": 0.70,
                "manufacturing_material_demand": 0.65,
                "producer_rate": 0.075,
                "consumer_rate": 0.060,
            },
            "moon": {
                "temperature_band": "cold",
                "food_production": 0.35,
                "oxygen": 0.45,
                "water": 0.40,
                "manufacturing_material_demand": 0.75,
                "producer_rate": 0.050,
                "consumer_rate": 0.065,
            },
            "asteroid": {
                "temperature_band": "cold",
                "food_production": 0.15,
                "oxygen": 0.25,
                "water": 0.30,
                "manufacturing_material_demand": 0.85,
                "producer_rate": 0.070,
                "consumer_rate": 0.055,
            },
        }
        row = dict(baseline.get(body_type, baseline["planet"]))
        jitter = lambda: round(min(1.0, max(0.0, rng.uniform(-0.05, 0.05) + 0.5)) - 0.5, 3)
        row["food_production"] = round(max(0.0, min(1.0, float(row["food_production"]) + jitter())), 3)
        row["oxygen"] = round(max(0.0, min(1.0, float(row["oxygen"]) + jitter())), 3)
        row["water"] = round(max(0.0, min(1.0, float(row["water"]) + jitter())), 3)
        row["manufacturing_material_demand"] = round(
            max(0.0, min(1.0, float(row["manufacturing_material_demand"]) + jitter())),
            3,
        )
        row["producer_rate"] = round(max(0.01, min(0.25, float(row["producer_rate"]) + jitter() * 0.04)), 4)
        row["consumer_rate"] = round(max(0.01, min(0.25, float(row["consumer_rate"]) + jitter() * 0.04)), 4)
        return row

    def _station_economy_state(cargo_type: str) -> dict[str, float | str]:
        return {
            "primary_good": cargo_type,
            "supply_index": round(rng.uniform(0.7, 1.3), 3),
            "demand_index": round(rng.uniform(0.7, 1.3), 3),
            "price_index": round(rng.uniform(0.85, 1.15), 3),
            "fuel_price_index": round(rng.uniform(0.9, 1.2), 3),
        }

    def _next_station_name(body: str, role_labels: list[str], fallback: str) -> str:
        style = _style_counter[0] % 3
        _style_counter[0] += 1

        if style == 1:
            nickname = nickname_pool[_name_counter[0] % len(nickname_pool)]
            _name_counter[0] += 1
            return nickname

        if style == 2:
            prefix = designation_prefixes[_name_counter[0] % len(designation_prefixes)]
            _name_counter[0] += 1
            return f"{body} {prefix}-{rng.randint(10, 999)}"

        label = role_labels[_name_counter[0] % len(role_labels)]
        _name_counter[0] += 1
        if base_names:
            return f"{base_names[(_name_counter[0] - 1) % len(base_names)]} {label}"
        return fallback

    for planet in catalog["celestial"]["planets"]:
        template = templates["planet"]
        base_token = _sanitize_station_token(planet)

        starbases = _station_count(1, 2) if _is_large_planetoid(planet) else 1
        for idx in range(1, starbases + 1):
            sid = f"{template['id_prefix']}-{base_token}" if idx == 1 else f"{template['id_prefix']}-{base_token}-SB{idx}"
            cargo_type = _station_cargo()
            stations.append(
                {
                    "id": sid,
                    "name": _next_station_name(
                        planet,
                        ["Starbase", "Citadel", "Port", "Harbor"],
                        template["name_template"].format(body=planet),
                    ),
                    "body_name": planet,
                    "body_type": "planet",
                    "parent_body": planet,
                    "cargo_type": cargo_type,
                    "allowed_size_classes": template["allowed_size_classes"],
                    "economy_profile": _station_economy_profile("planet"),
                    "economy_state": _station_economy_state(cargo_type),
                }
            )

        orbitals = _station_count(1, 3) if _is_large_planetoid(planet) else 1
        for idx in range(1, orbitals + 1):
            sid = f"{template['id_prefix']}-{base_token}-ORB{idx}"
            cargo_type = _station_cargo()
            stations.append(
                {
                    "id": sid,
                    "name": _next_station_name(
                        planet,
                        ["Orbital", "Ring", "Array", "Anchor"],
                        f"{planet} Orbital",
                    ),
                    "body_name": planet,
                    "body_type": "planet",
                    "parent_body": planet,
                    "cargo_type": cargo_type,
                    "allowed_size_classes": template["allowed_size_classes"],
                    "economy_profile": _station_economy_profile("planet"),
                    "economy_state": _station_economy_state(cargo_type),
                }
            )

    for moon in catalog["celestial"]["moons"]:
        moon_name = moon["name"]
        parent = moon["parent"]
        template = templates["moon"]
        base_token = _sanitize_station_token(moon_name)

        orbitals = _station_count(1, 3) if _is_large_planetoid(moon_name) else 1
        for idx in range(1, orbitals + 1):
            sid = f"{template['id_prefix']}-{base_token}" if idx == 1 else f"{template['id_prefix']}-{base_token}-ORB{idx}"
            cargo_type = _station_cargo()
            stations.append(
                {
                    "id": sid,
                    "name": _next_station_name(
                        moon_name,
                        ["Orbital", "Ring", "Relay", "Dock"],
                        template["name_template"].format(body=moon_name),
                    ),
                    "body_name": moon_name,
                    "body_type": "moon",
                    "parent_body": parent,
                    "cargo_type": cargo_type,
                    "allowed_size_classes": template["allowed_size_classes"],
                    "economy_profile": _station_economy_profile("moon"),
                    "economy_state": _station_economy_state(cargo_type),
                }
            )

        if _is_large_planetoid(moon_name):
            starbases = _station_count(1, 2)
            for idx in range(1, starbases + 1):
                sid = f"{template['id_prefix']}-{base_token}-SB{idx}"
                cargo_type = _station_cargo()
                stations.append(
                    {
                        "id": sid,
                        "name": _next_station_name(
                            moon_name,
                            ["Starbase", "Citadel", "Outpost"],
                            f"{moon_name} Starbase",
                        ),
                        "body_name": moon_name,
                        "body_type": "moon",
                        "parent_body": parent,
                        "cargo_type": cargo_type,
                        "allowed_size_classes": template["allowed_size_classes"],
                        "economy_profile": _station_economy_profile("moon"),
                        "economy_state": _station_economy_state(cargo_type),
                    }
                )

    for asteroid in catalog["celestial"]["asteroids"]:
        template = templates["asteroid"]
        sid = f"{template['id_prefix']}-{_sanitize_station_token(asteroid)}"
        cargo_type = _station_cargo()
        stations.append(
            {
                "id": sid,
                "name": _next_station_name(
                    asteroid,
                    ["Exchange", "Nexus", "Hold", "Yard"],
                    template["name_template"].format(body=asteroid),
                ),
                "body_name": asteroid,
                "body_type": "asteroid",
                "parent_body": template["parent_body"] or "Asteroid Belt",
                "cargo_type": cargo_type,
                "allowed_size_classes": template["allowed_size_classes"],
                "economy_profile": _station_economy_profile("asteroid"),
                "economy_state": _station_economy_state(cargo_type),
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
    catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    catalog = catalog or load_seed_catalog(catalog_path)
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
    naming_ext = load_naming_config()
    adjectives = naming["adjectives"]
    nouns = naming["nouns"]
    captain_first = naming["captain_first"]
    captain_last = naming["captain_last"]
    ship_names_singular_raw = naming_ext.get("ship_names_singular")
    if ship_names_singular_raw is not None:
        ship_names_singular = _ensure_str_list("naming.ship_names_singular", ship_names_singular_raw, min_items=0)
    else:
        ship_names_singular = []

    for i in range(1, count + 1):
        faction = _pick_faction(rng, ship_generation["faction_distribution"])
        ship_type_options = ship_types_by_faction.get(faction)
        if not ship_type_options:
            ship_type_options = list(ship_generation["ship_types"])
        ship_type_choice = rng.choice(ship_type_options)
        ship_type = ship_type_choice["name"]
        size_class = ship_type_choice["size_class"]
        displacement_min = float(ship_type_choice.get("displacement_min_million_m3", 0.8))
        displacement_max = float(ship_type_choice.get("displacement_max_million_m3", 22.0))

        compatible_station_ids = [
            station_id
            for station_id in station_ids
            if not station_capabilities.get(station_id) or size_class in station_capabilities[station_id]
        ]
        if not compatible_station_ids:
            raise ValueError(
                f"No compatible home stations found for ship size class '{size_class}' "
                f"(ship type: '{ship_type}'). Check station allowed_size_classes configuration."
            )
        home_station_id = rng.choice(compatible_station_ids)

        if ship_names_singular and rng.random() < 0.5:
            ship_name = rng.choice(ship_names_singular)
        else:
            ship_name = f"{rng.choice(adjectives)} {rng.choice(nouns)}"
        captain = f"{rng.choice(captain_first)} {rng.choice(captain_last)}"
        displacement = round(rng.uniform(displacement_min, displacement_max), 3)

        if faction == "bounty_hunter":
            crew = rng.randint(1, 5)
        else:
            crew_min = max(1, int(math.ceil(displacement * 200.0)))
            crew_max = max(crew_min, int(math.floor(displacement * 500.0)))
            crew = rng.randint(crew_min, crew_max)

        if faction == "merchant":
            cargo = rng.choice(ship_generation["cargo_types"])
            passengers = rng.randint(0, 10_000)
        elif faction == "government":
            cargo = ""
            passengers = rng.randint(10, 500)
        else:
            cargo = ""
            passengers = 0

        ships.append(
            {
                "id": f"SHIP-{i:04d}",
                "name": ship_name,
                "faction": faction,
                "ship_type": ship_type,
                "size_class": size_class,
                "displacement_million_m3": displacement,
                "home_station_id": home_station_id,
                "captain_name": captain,
                "cargo": cargo,
                "crew": crew,
                "passengers": passengers,
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
