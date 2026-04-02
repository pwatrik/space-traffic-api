"""Deterministic app bootstrap and event-collection helpers for shadow harness tests.

All helpers accept explicit parameters rather than relying on global state so that
two parallel runs with identical arguments produce identical, independently verifiable
output sequences.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from space_traffic_api.app import create_app


# ---------------------------------------------------------------------------
# Catalog presets
# ---------------------------------------------------------------------------

def _base_lifecycle(
    *,
    decommission: bool = False,
    war: bool = False,
    build: bool = False,
    pirate: bool = False,
) -> dict[str, Any]:
    return {
        "decommission": {
            "enabled": decommission,
            "base_probability_per_day": 500000.0 if decommission else 0.0,
            "age_years_soft_limit": 1,
            "age_acceleration_per_year": 0.0,
            "max_probability_per_day": 500000.0 if decommission else 0.0,
        },
        "war_impact": {
            "enabled": war,
            "base_probability_per_day": 500000.0 if war else 0.0,
            "faction_loss_multiplier": {"merchant": 1.0},
            "max_losses_per_event": 3,
        },
        "build_queue": {
            "enabled": build,
            "base_builds_per_day": 300000.0 if build else 0.0,
            "max_builds_per_day": 5,
            "faction_distribution": {"merchant": 1.0},
            "spawn_policy": "compatible_random_station",
        },
        "pirate_activity": {
            "enabled": pirate,
            "base_spawn_probability_per_day": 500000.0 if pirate else 0.0,
            "max_active_events": 1,
            "min_strength": 0.5,
            "max_strength": 1.0,
            "strength_end_threshold": 0.3,
            "merchant_arrival_base_destruction_chance": 0.04,
            "merchant_arrival_destruction_multiplier": 4.0,
            "strength_decay_per_bounty_hunter_arrival": 0.1,
            "respawn_min_days": 10.0,
            "respawn_max_days": 30.0,
            "allowed_anchors": ["Earth", "Mars"],
            "affected_stations_per_event": 2,
            "pirate_faction_bias": 2.0,
            "bounty_hunter_spawn_base_probability_per_day": 0.0,
        },
    }


CATALOG_PRESETS: dict[str, dict[str, Any]] = {
    "baseline": {
        "ship_count": 12,
        "ship_seed": 42,
        "lifecycle_kwargs": {},
        "seed": 99,
        "rate": 300,
    },
    "war_heavy": {
        "ship_count": 14,
        "ship_seed": 42,
        "lifecycle_kwargs": {"war": True},
        "seed": 77,
        "rate": 300,
    },
    "pirate_enabled": {
        "ship_count": 14,
        "ship_seed": 42,
        "lifecycle_kwargs": {"pirate": True},
        "seed": 55,
        "rate": 300,
    },
}


# Shared harness defaults to keep slow-test behavior stable across machines.
SHADOW_DEFAULT_START_TIME = "2150-01-01T00:00:00Z"
SHADOW_DEFAULT_TIMEOUT_SECONDS = 12.0
SHADOW_DEFAULT_POLL_INTERVAL_SECONDS = 0.05


def _write_catalog(path: Path, *, ship_count: int, ship_seed: int, lifecycle: dict[str, Any]) -> None:
    catalog = {
        "celestial": {
            "planets": ["Earth", "Mars"],
            "moons": [{"name": "Phobos", "parent": "Mars"}],
            "asteroids": [],
            "distance_order": {"Earth": 1, "Mars": 3, "Phobos": 4},
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
            ]
        },
        "ship_generation": {
            "faction_distribution": {"merchant": 1.0},
            "ship_types": [
                {
                    "name": "Freighter",
                    "faction": "merchant",
                    "size_class": "medium",
                    "speed_au_per_hour": 1.0,
                    "crew_min": 8,
                    "crew_max": 24,
                }
            ],
            "cargo_types": ["water_ice", "metals"],
            "naming": {
                "adjectives": ["Solar", "Stellar"],
                "nouns": ["Voyager", "Runner"],
                "captain_first": ["Avery", "Blake"],
                "captain_last": ["Voss", "Chen"],
            },
            "defaults": {
                "ship_count": ship_count,
                "ship_seed": ship_seed,
            },
        },
        "lifecycle": lifecycle,
    }
    path.write_text(json.dumps(catalog), encoding="utf-8")


# ---------------------------------------------------------------------------
# App lifecycle helpers
# ---------------------------------------------------------------------------

class DeterministicRun:
    """Context manager that bootstraps a deterministic simulated app run.

    Usage::

        with DeterministicRun(seed=99, rate=300) as run:
            events = run.collect_departures(n=10)
            control = run.collect_control_events(action="decommissioned")
    """

    def __init__(
        self,
        *,
        preset: str = "baseline",
        seed: int | None = None,
        rate: int | None = None,
        start_time: str = SHADOW_DEFAULT_START_TIME,
    ) -> None:
        cfg = CATALOG_PRESETS[preset]
        self._ship_count: int = cfg["ship_count"]
        self._ship_seed: int = cfg["ship_seed"]
        self._lifecycle_kwargs: dict[str, Any] = cfg["lifecycle_kwargs"]
        self._seed = seed if seed is not None else cfg["seed"]
        self._rate = rate if rate is not None else cfg["rate"]
        self._start_time = start_time

        self._tmpdir: TemporaryDirectory | None = None
        self.client = None
        self.app = None
        self.headers: dict[str, str] = {"X-API-Key": "shadow-test-key"}

    def __enter__(self) -> "DeterministicRun":
        self._tmpdir = TemporaryDirectory()
        tmp = self._tmpdir.name
        catalog_path = Path(tmp) / "catalog.json"
        _write_catalog(
            catalog_path,
            ship_count=self._ship_count,
            ship_seed=self._ship_seed,
            lifecycle=_base_lifecycle(**self._lifecycle_kwargs),
        )

        import os
        self._saved_env: dict[str, str | None] = {}
        env_updates = {
            "SPACE_TRAFFIC_DB_PATH": f"{tmp}/test.db",
            "SPACE_TRAFFIC_API_KEY": "shadow-test-key",
            "SPACE_TRAFFIC_SEED_CATALOG_PATH": str(catalog_path),
            "SPACE_TRAFFIC_DISABLE_GENERATOR": "false",
            "SPACE_TRAFFIC_DETERMINISTIC_MODE": "true",
            "SPACE_TRAFFIC_DETERMINISTIC_SEED": str(self._seed),
            "SPACE_TRAFFIC_DETERMINISTIC_START_TIME": self._start_time,
            "SPACE_TRAFFIC_MIN_EVENTS_PER_MIN": str(self._rate),
            "SPACE_TRAFFIC_MAX_EVENTS_PER_MIN": str(self._rate),
        }
        try:
            for key, value in env_updates.items():
                self._saved_env[key] = os.environ.get(key)
                os.environ[key] = value

            self.app = create_app()
            self.client = self.app.test_client()
            return self
        except Exception:
            # If app creation fails, restore environment and clean up temp dir
            for key, old_value in self._saved_env.items():
                if old_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_value
            if self._tmpdir:
                self._tmpdir.cleanup()
                self._tmpdir = None
            raise

    def __exit__(self, *_: Any) -> None:
        import os
        try:
            if self.app:
                sim = self.app.config.get("space_simulation")
                if sim:
                    sim.stop(timeout=3.0)
                store = self.app.config.get("space_store")
                if store:
                    store.close()
        finally:
            for key, old_value in self._saved_env.items():
                if old_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_value
            if self._tmpdir:
                self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # Collection helpers
    # ------------------------------------------------------------------

    def collect_departures(
        self,
        n: int,
        timeout_seconds: float = SHADOW_DEFAULT_TIMEOUT_SECONDS,
        poll_interval: float = SHADOW_DEFAULT_POLL_INTERVAL_SECONDS,
        fail_on_timeout: bool = True,
    ) -> list[dict[str, Any]]:
        """Poll /departures until at least *n* events have been produced."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            resp = self.client.get(
                "/departures",
                headers=self.headers,
                query_string={"limit": min(1000, n)},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            departures = data.get("departures", [])
            if len(departures) >= n:
                return departures[:n]
            time.sleep(poll_interval)
        resp = self.client.get(
            "/departures",
            headers=self.headers,
            query_string={"limit": min(1000, n)},
        )
        departures = resp.get_json().get("departures", [])
        if fail_on_timeout:
            from shadow.assertions import summarize_departures

            summary = summarize_departures(departures)
            sampled_ids = [d.get("event_uid") for d in departures[:5]]
            raise AssertionError(
                "Timed out waiting for departures. "
                f"required={n} observed={len(departures)} "
                f"timeout_seconds={timeout_seconds} poll_interval={poll_interval}. "
                f"summary={summary} sample_event_uids={sampled_ids}"
            )
        return departures

    def collect_control_events(
        self,
        action: str,
        timeout_seconds: float = SHADOW_DEFAULT_TIMEOUT_SECONDS,
        poll_interval: float = SHADOW_DEFAULT_POLL_INTERVAL_SECONDS,
        fail_on_timeout: bool = True,
    ) -> list[dict[str, Any]]:
        """Poll /control-events until at least one matching action appears."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            resp = self.client.get("/control-events", headers=self.headers)
            assert resp.status_code == 200
            events = resp.get_json().get("control_events", [])
            matching = [e for e in events if e.get("action") == action]
            if matching:
                return matching
            time.sleep(poll_interval)
        resp = self.client.get("/control-events", headers=self.headers)
        all_events = resp.get_json().get("control_events", [])
        matching = [
            e
            for e in all_events
            if e.get("action") == action
        ]
        if fail_on_timeout and not matching:
            observed_actions = Counter(str(e.get("action")) for e in all_events)
            raise AssertionError(
                "Timed out waiting for control events. "
                f"required_action={action!r} timeout_seconds={timeout_seconds} "
                f"poll_interval={poll_interval} observed_actions={dict(observed_actions)}"
            )
        return matching

    def get_config(self) -> dict[str, Any]:
        resp = self.client.get("/config", headers=self.headers)
        assert resp.status_code == 200
        return resp.get_json()

    def get_ships_state(self) -> dict[str, Any]:
        resp = self.client.get("/ships/state", headers=self.headers)
        assert resp.status_code == 200
        return resp.get_json()
