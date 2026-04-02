from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_effective_lifecycle_config(
    base_lifecycle: dict[str, Any],
    scenario_definition: dict[str, Any] | None,
    intensity: float,
) -> dict[str, Any]:
    """Merge base lifecycle config with scenario-specific modifiers."""

    effective = deepcopy(base_lifecycle)
    if not scenario_definition:
        return effective

    overrides = scenario_definition.get("lifecycle_overrides")
    if not isinstance(overrides, dict):
        return effective

    clamped_intensity = max(0.0, float(intensity))

    def _scale_multiplier(raw_multiplier: Any) -> float:
        multiplier = max(0.0, float(raw_multiplier))
        return max(0.0, 1.0 + ((multiplier - 1.0) * clamped_intensity))

    for channel, conf in overrides.items():
        if not isinstance(conf, dict):
            continue

        target = effective.setdefault(channel, {})
        if not isinstance(target, dict):
            continue

        if "enabled" in conf and clamped_intensity > 0:
            target["enabled"] = bool(conf["enabled"])

        if "base_probability_per_day_multiplier" in conf and "base_probability_per_day" in target:
            scale = _scale_multiplier(conf["base_probability_per_day_multiplier"])
            target["base_probability_per_day"] = max(0.0, float(target["base_probability_per_day"]) * scale)

        if "max_probability_per_day_multiplier" in conf and "max_probability_per_day" in target:
            scale = _scale_multiplier(conf["max_probability_per_day_multiplier"])
            target["max_probability_per_day"] = max(0.0, float(target["max_probability_per_day"]) * scale)

        if "base_builds_per_day_multiplier" in conf and "base_builds_per_day" in target:
            scale = _scale_multiplier(conf["base_builds_per_day_multiplier"])
            target["base_builds_per_day"] = max(0.0, float(target["base_builds_per_day"]) * scale)

        if "max_losses_per_event_add" in conf and "max_losses_per_event" in target:
            add = int(round(float(conf["max_losses_per_event_add"]) * clamped_intensity))
            target["max_losses_per_event"] = max(1, int(target["max_losses_per_event"]) + add)

        if channel == "war_impact":
            raw = conf.get("faction_loss_multiplier_overrides")
            if isinstance(raw, dict):
                current = target.get("faction_loss_multiplier")
                if isinstance(current, dict):
                    merged = dict(current)
                    for faction, faction_multiplier in raw.items():
                        key = str(faction).strip().lower()
                        if not key:
                            continue
                        scale = _scale_multiplier(faction_multiplier)
                        merged[key] = max(0.0, float(merged.get(key, 1.0)) * scale)
                    target["faction_loss_multiplier"] = merged

        if channel == "build_queue" and clamped_intensity > 0:
            raw = conf.get("faction_distribution")
            if isinstance(raw, dict) and raw:
                normalized: dict[str, float] = {}
                for faction, weight in raw.items():
                    if not isinstance(weight, (int, float)) or float(weight) <= 0:
                        continue
                    key = str(faction).strip().lower()
                    if key:
                        normalized[key] = float(weight)
                if normalized:
                    target["faction_distribution"] = normalized

    return effective
