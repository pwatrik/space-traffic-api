from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any


def _unit_interval(seed: int, label: str) -> float:
    digest = hashlib.sha256(f"{seed}:{label}".encode("utf-8")).digest()
    numerator = int.from_bytes(digest[:8], "big")
    return numerator / float((1 << 64) - 1)


@dataclass(slots=True, frozen=True)
class OrbitalBodyTemplate:
    body_id: str
    body_type: str
    distance_rank: float
    radius_scale: float
    orbital_period_days: float
    initial_phase_radians: float


@dataclass(slots=True)
class OrbitalBodyState:
    body_id: str
    body_type: str
    distance_rank: float
    radius_scale: float
    orbital_period_days: float
    angular_velocity_radians_per_day: float
    phase_radians: float
    x: float
    y: float

    @classmethod
    def from_template(cls, template: OrbitalBodyTemplate) -> "OrbitalBodyState":
        angular_velocity = math.tau / template.orbital_period_days
        x = math.cos(template.initial_phase_radians) * template.radius_scale
        y = math.sin(template.initial_phase_radians) * template.radius_scale
        return cls(
            body_id=template.body_id,
            body_type=template.body_type,
            distance_rank=template.distance_rank,
            radius_scale=template.radius_scale,
            orbital_period_days=template.orbital_period_days,
            angular_velocity_radians_per_day=angular_velocity,
            phase_radians=template.initial_phase_radians,
            x=x,
            y=y,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "body_id": self.body_id,
            "body_type": self.body_type,
            "distance_rank": round(self.distance_rank, 3),
            "radius_scale": round(self.radius_scale, 6),
            "orbital_period_days": round(self.orbital_period_days, 6),
            "angular_velocity_radians_per_day": round(self.angular_velocity_radians_per_day, 9),
            "phase_radians": round(self.phase_radians, 9),
            "x": round(self.x, 9),
            "y": round(self.y, 9),
        }


def build_orbital_body_templates(catalog: dict[str, Any], deterministic_seed: int) -> dict[str, OrbitalBodyTemplate]:
    celestial = catalog.get("celestial") if isinstance(catalog.get("celestial"), dict) else {}
    distance_order = celestial.get("distance_order") if isinstance(celestial.get("distance_order"), dict) else {}

    templates: dict[str, OrbitalBodyTemplate] = {}

    planets = sorted(
        (str(name) for name in celestial.get("planets", []) if str(name).strip()),
        key=lambda name: (int(distance_order.get(name, 99)), name),
    )
    for planet in planets:
        rank = float(distance_order.get(planet, 5) or 5)
        phase = _unit_interval(deterministic_seed, f"planet:{planet}:phase") * math.tau
        templates[planet] = OrbitalBodyTemplate(
            body_id=planet,
            body_type="planet",
            distance_rank=rank,
            radius_scale=max(1.0, rank),
            orbital_period_days=40.0 + (rank * 18.0),
            initial_phase_radians=phase,
        )

    belt_rank = float(distance_order.get("Asteroid Belt", 5) or 5)
    asteroids = sorted(str(name) for name in celestial.get("asteroids", []) if str(name).strip())
    for asteroid in asteroids:
        phase = _unit_interval(deterministic_seed, f"asteroid:{asteroid}:phase") * math.tau
        radius_variation = (_unit_interval(deterministic_seed, f"asteroid:{asteroid}:radius") - 0.5) * 0.4
        period_variation = (_unit_interval(deterministic_seed, f"asteroid:{asteroid}:period") - 0.5) * 10.0
        templates[asteroid] = OrbitalBodyTemplate(
            body_id=asteroid,
            body_type="asteroid",
            distance_rank=belt_rank,
            radius_scale=max(0.5, belt_rank + radius_variation),
            orbital_period_days=max(10.0, 40.0 + (belt_rank * 18.0) + period_variation),
            initial_phase_radians=phase,
        )

    return templates


def initialize_orbital_body_state(catalog: dict[str, Any], deterministic_seed: int) -> dict[str, OrbitalBodyState]:
    templates = build_orbital_body_templates(catalog, deterministic_seed)
    return {
        body_id: OrbitalBodyState.from_template(template)
        for body_id, template in templates.items()
    }