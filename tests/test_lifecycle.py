import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from space_traffic_api.app import create_app


def _write_catalog(path: Path, *, ship_count: int, lifecycle: dict) -> None:
    catalog = {
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
                "ship_count": ship_count,
                "ship_seed": 42,
            },
        },
        "lifecycle": lifecycle,
    }
    path.write_text(json.dumps(catalog), encoding="utf-8")


def _wait_for_lifecycle_action(client, headers: dict[str, str], action: str, timeout_seconds: float = 4.0) -> dict | None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = client.get("/control-events", headers=headers)
        assert response.status_code == 200
        payload = response.get_json()
        for event in payload["control_events"]:
            if event["event_type"] == "lifecycle" and event["action"] == action:
                return event
        time.sleep(0.2)
    return None


def test_lifecycle_emits_decommission_events(monkeypatch):
    lifecycle = {
        "decommission": {
            "enabled": True,
            "base_probability_per_day": 500000.0,
            "age_years_soft_limit": 1,
            "age_acceleration_per_year": 0.0,
            "max_probability_per_day": 500000.0,
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
    }

    with TemporaryDirectory() as tmp:
        catalog_path = Path(tmp) / "catalog.json"
        _write_catalog(catalog_path, ship_count=8, lifecycle=lifecycle)

        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", f"{tmp}/test.db")
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_SEED_CATALOG_PATH", str(catalog_path))
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "false")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "123")
        monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "300")
        monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "300")

        app = create_app()
        client = app.test_client()
        headers = {"X-API-Key": "test-key"}

        try:
            event = _wait_for_lifecycle_action(client, headers, "decommissioned")
            assert event is not None
            assert event["payload"]["count"] >= 1
        finally:
            app.config["space_simulation"].stop(timeout=3.0)
            app.config["space_store"].close()


def test_lifecycle_emits_war_loss_events(monkeypatch):
    lifecycle = {
        "decommission": {
            "enabled": False,
            "base_probability_per_day": 0.0,
            "age_years_soft_limit": 1,
            "age_acceleration_per_year": 0.0,
            "max_probability_per_day": 0.0,
        },
        "war_impact": {
            "enabled": True,
            "base_probability_per_day": 500000.0,
            "faction_loss_multiplier": {"merchant": 1.0},
            "max_losses_per_event": 3,
        },
        "build_queue": {
            "enabled": False,
            "base_builds_per_day": 0.0,
            "max_builds_per_day": 1,
            "faction_distribution": {"merchant": 1.0},
            "spawn_policy": "compatible_random_station",
        },
    }

    with TemporaryDirectory() as tmp:
        catalog_path = Path(tmp) / "catalog.json"
        _write_catalog(catalog_path, ship_count=10, lifecycle=lifecycle)

        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", f"{tmp}/test.db")
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_SEED_CATALOG_PATH", str(catalog_path))
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "false")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "456")
        monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "300")
        monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "300")

        app = create_app()
        client = app.test_client()
        headers = {"X-API-Key": "test-key"}

        try:
            event = _wait_for_lifecycle_action(client, headers, "war_losses")
            assert event is not None
            assert event["payload"]["count"] >= 1
        finally:
            app.config["space_simulation"].stop(timeout=3.0)
            app.config["space_store"].close()


def test_lifecycle_emits_build_events(monkeypatch):
    lifecycle = {
        "decommission": {
            "enabled": False,
            "base_probability_per_day": 0.0,
            "age_years_soft_limit": 1,
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
            "enabled": True,
            "base_builds_per_day": 300000.0,
            "max_builds_per_day": 300000,
            "faction_distribution": {"merchant": 1.0},
            "spawn_policy": "compatible_random_station",
        },
    }

    with TemporaryDirectory() as tmp:
        catalog_path = Path(tmp) / "catalog.json"
        _write_catalog(catalog_path, ship_count=1, lifecycle=lifecycle)

        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", f"{tmp}/test.db")
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_SEED_CATALOG_PATH", str(catalog_path))
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "false")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "789")
        monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "300")
        monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "300")

        app = create_app()
        client = app.test_client()
        headers = {"X-API-Key": "test-key"}

        try:
            event = _wait_for_lifecycle_action(client, headers, "ships_built")
            assert event is not None
            assert event["payload"]["count"] >= 1

            ships = client.get("/ships", headers=headers)
            assert ships.status_code == 200
            assert ships.get_json()["count"] > 1
        finally:
            app.config["space_simulation"].stop(timeout=3.0)
            app.config["space_store"].close()


def test_build_queue_uses_ship_names_singular_from_naming_config(monkeypatch):
    """Ships built via the build queue use singular names when naming_config provides them."""
    lifecycle = {
        "decommission": {
            "enabled": False,
            "base_probability_per_day": 0.0,
            "age_years_soft_limit": 1,
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
            "enabled": True,
            "base_builds_per_day": 300000.0,
            "max_builds_per_day": 300000,
            "faction_distribution": {"merchant": 1.0},
            "spawn_policy": "compatible_random_station",
        },
    }
    singular_names = {"Stellar Nomad", "Void Phantom", "Drift Runner"}

    with TemporaryDirectory() as tmp:
        catalog_path = Path(tmp) / "catalog.json"
        _write_catalog(catalog_path, ship_count=1, lifecycle=lifecycle)

        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", f"{tmp}/test.db")
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_SEED_CATALOG_PATH", str(catalog_path))
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "false")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "999")
        monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "300")
        monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "300")

        with patch("space_traffic_api.seed_data.load_naming_config") as mock_naming:
            mock_naming.return_value = {"ship_names_singular": list(singular_names)}
            app = create_app()

        client = app.test_client()
        headers = {"X-API-Key": "test-key"}

        try:
            event = _wait_for_lifecycle_action(client, headers, "ships_built")
            assert event is not None
            assert event["payload"]["count"] >= 1

            ships_resp = client.get("/ships", headers=headers)
            assert ships_resp.status_code == 200
            all_ships = ships_resp.get_json()["ships"]
            built_names = [s["name"] for s in all_ships]
            valid_adjective_noun = {"Solar Voyager"}
            for name in built_names:
                assert name in singular_names or name in valid_adjective_noun, (
                    f"Unexpected ship name '{name}': expected singular or adjective+noun"
                )
        finally:
            app.config["space_simulation"].stop(timeout=3.0)
            app.config["space_store"].close()
