import json
import os
import time
from tempfile import TemporaryDirectory

from space_traffic_api.app import create_app


def test_route_filtering_respects_station_size_class_capabilities(monkeypatch):
    custom_catalog = {
        "celestial": {
            "planets": ["Earth"],
            "moons": [
                {"name": "Moon", "parent": "Earth"},
                {"name": "Phobos", "parent": "Mars"},
            ],
            "asteroids": [],
            "distance_order": {"Earth": 1, "Mars": 2, "Asteroid Belt": 3},
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
                    "allowed_size_classes": ["xlarge"],
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
            "faction_distribution": {"military": 1.0},
            "ship_types": [{"name": "Carrier", "faction": "military", "size_class": "xlarge"}],
            "cargo_types": ["defense_systems"],
            "naming": {
                "adjectives": ["Iron"],
                "nouns": ["Sentinel"],
                "captain_first": ["Alex"],
                "captain_last": ["Drake"],
            },
            "defaults": {"ship_count": 1, "ship_seed": 99},
        },
    }

    with TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        catalog_path = os.path.join(tmp, "catalog.json")
        with open(catalog_path, "w", encoding="utf-8") as fh:
            json.dump(custom_catalog, fh)

        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", db_path)
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "false")
        monkeypatch.setenv("SPACE_TRAFFIC_SEED_CATALOG_PATH", catalog_path)
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "60")
        monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "60")

        app = create_app()
        client = app.test_client()
        headers = {"X-API-Key": "test-key"}
        try:
            # Poll /departures until at least one event is available, or timeout.
            start_time = time.time()
            departures = []
            while True:
                departures_resp = client.get("/departures?limit=20", headers=headers)
                assert departures_resp.status_code == 200
                departures = departures_resp.get_json()["departures"]
                if len(departures) >= 1 or time.time() - start_time > 5.0:
                    break
                time.sleep(0.1)
            assert len(departures) >= 1

            for event in departures:
                assert event["destination_station_id"].startswith("STN-MOON-")
        finally:
            app.config["space_simulation"].stop(timeout=1.5)
            app.config["space_store"].close()
