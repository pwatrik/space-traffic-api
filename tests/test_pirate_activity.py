import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from space_traffic_api.app import create_app


def _write_catalog(path: Path, *, pirate_activity: dict) -> None:
    catalog = {
        "celestial": {
            "planets": ["Earth", "Mars"],
            "moons": [{"name": "Phobos", "parent": "Mars"}],
            "asteroids": ["Ceres"],
            "distance_order": {
                "Earth": 1,
                "Mars": 2,
                "Asteroid Belt": 3,
            },
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
                    "speed_au_per_hour": 1.0,
                    "crew_min": 8,
                    "crew_max": 24,
                }
            ],
            "cargo_types": ["water_ice"],
            "naming": {
                "adjectives": ["Solar"],
                "nouns": ["Voyager"],
                "captain_first": ["Avery"],
                "captain_last": ["Voss"],
            },
            "defaults": {
                "ship_count": 8,
                "ship_seed": 42,
            },
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
            "pirate_activity": pirate_activity,
        },
    }
    path.write_text(json.dumps(catalog), encoding="utf-8")


def _get_control_events(client, headers: dict[str, str]) -> list[dict]:
    response = client.get("/control-events", headers=headers)
    assert response.status_code == 200
    return response.get_json()["control_events"]


def _wait_for_action(client, headers: dict[str, str], action: str, timeout_seconds: float = 5.0) -> dict | None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for event in _get_control_events(client, headers):
            if event["event_type"] == "lifecycle" and event["action"] == action:
                return event
        time.sleep(0.2)
    return None


def test_pirate_event_spawns_and_is_visible_in_config(monkeypatch):
    pirate_activity = {
        "enabled": True,
        "allowed_anchors": ["Earth", "Mars", "Asteroid Belt"],
        "strength_start": 1.0,
        "strength_end_threshold": 0.5,
        "ambient_strength_decay_per_day": 0.0,
        "merchant_arrival_destruction_multiplier": 4.0,
        "strength_decay_per_bounty_hunter_arrival": 0.02,
        "respawn_min_days": 10.0,
        "respawn_max_days": 10.0,
    }

    with TemporaryDirectory() as tmp:
        catalog_path = Path(tmp) / "catalog.json"
        _write_catalog(catalog_path, pirate_activity=pirate_activity)

        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", f"{tmp}/test.db")
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_SEED_CATALOG_PATH", str(catalog_path))
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "false")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "111")
        monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "300")
        monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "300")

        app = create_app()
        client = app.test_client()
        headers = {"X-API-Key": "test-key"}

        try:
            started = _wait_for_action(client, headers, "pirate_started")
            assert started is not None
            assert started["payload"]["strength"] == 1.0

            cfg = client.get("/config", headers=headers)
            assert cfg.status_code == 200
            pirate_event = cfg.get_json()["pirate_event"]
            assert pirate_event["active"] is True
            assert pirate_event["anchor_body"] in {"Earth", "Mars", "Asteroid Belt"}
            assert pirate_event["strength"] == 1.0
            assert pirate_event["affected_station_ids"]
        finally:
            app.config["space_simulation"].stop(timeout=3.0)
            app.config["space_store"].close()


def test_pirate_event_ends_and_respawns_at_new_anchor(monkeypatch):
    pirate_activity = {
        "enabled": True,
        "allowed_anchors": ["Earth", "Mars", "Asteroid Belt"],
        "strength_start": 1.0,
        "strength_end_threshold": 0.5,
        "ambient_strength_decay_per_day": 500000.0,
        "merchant_arrival_destruction_multiplier": 4.0,
        "strength_decay_per_bounty_hunter_arrival": 0.02,
        "respawn_min_days": 0.0,
        "respawn_max_days": 0.0,
    }

    with TemporaryDirectory() as tmp:
        catalog_path = Path(tmp) / "catalog.json"
        _write_catalog(catalog_path, pirate_activity=pirate_activity)

        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", f"{tmp}/test.db")
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_SEED_CATALOG_PATH", str(catalog_path))
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "false")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "222")
        monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "300")
        monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "300")

        app = create_app()
        client = app.test_client()
        headers = {"X-API-Key": "test-key"}

        try:
            deadline = time.time() + 6.0
            started_events: list[dict] = []
            ended_events: list[dict] = []
            while time.time() < deadline:
                events = _get_control_events(client, headers)
                started_events = [e for e in events if e["event_type"] == "lifecycle" and e["action"] == "pirate_started"]
                ended_events = [e for e in events if e["event_type"] == "lifecycle" and e["action"] == "pirate_ended"]
                if len(started_events) >= 2 and len(ended_events) >= 1:
                    break
                time.sleep(0.2)

            assert len(started_events) >= 2
            assert len(ended_events) >= 1

            first_anchor = started_events[0]["payload"]["anchor_body"]
            second_anchor = started_events[1]["payload"]["anchor_body"]
            assert second_anchor != first_anchor
            assert ended_events[0]["payload"]["anchor_body"] == first_anchor
        finally:
            app.config["space_simulation"].stop(timeout=3.0)
            app.config["space_store"].close()
