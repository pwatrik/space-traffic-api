import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from space_traffic_api.app import create_app


def _write_catalog(path: Path, *, pirate_activity: dict, ship_count: int = 8) -> None:
    ship_types = [
        {
            "name": "Freighter",
            "faction": "merchant",
            "size_class": "medium",
            "speed_au_per_hour": 1.0,
            "crew_min": 8,
            "crew_max": 24,
        },
        {
            "name": "Star Wasp",
            "faction": "bounty_hunter",
            "size_class": "small",
            "speed_au_per_hour": 1.9,
            "crew_min": 1,
            "crew_max": 4,
            "displacement_min_million_m3": 0.01,
            "displacement_max_million_m3": 0.5,
        },
    ]

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
            "faction_distribution": {"merchant": 0.5, "bounty_hunter": 0.5},
            "ship_types": ship_types,
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


def _wait_for_condition(predicate, timeout_seconds: float = 5.0, interval_seconds: float = 0.15) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval_seconds)
    return False


def _collect_departure_factions(client, headers: dict[str, str], store, target_count: int, timeout_seconds: float = 8.0) -> list[str]:
    ships = store.list_ships()
    faction_by_ship_id = {row["id"]: row["faction"] for row in ships}

    baseline = client.get("/departures?limit=1000&order=asc", headers=headers)
    assert baseline.status_code == 200
    baseline_departures = baseline.get_json()["departures"]
    since_id = baseline_departures[-1]["id"] if baseline_departures else 0

    deadline = time.time() + timeout_seconds
    factions: list[str] = []
    while time.time() < deadline and len(factions) < target_count:
        chunk = client.get(f"/departures?since_id={since_id}&limit=1000&order=asc", headers=headers)
        assert chunk.status_code == 200
        departures = chunk.get_json()["departures"]
        if departures:
            since_id = departures[-1]["id"]
            for row in departures:
                faction = faction_by_ship_id.get(row.get("ship_id"))
                if faction:
                    factions.append(faction)
        if len(factions) < target_count:
            time.sleep(0.2)
    return factions


def test_pirate_event_spawns_and_is_visible_in_config(monkeypatch):
    pirate_activity = {
        "enabled": True,
        "allowed_anchors": ["Earth", "Mars", "Asteroid Belt"],
        "strength_start": 1.0,
        "strength_end_threshold": 0.5,
        "ambient_strength_decay_per_day": 0.0,
        "merchant_arrival_base_destruction_chance": 0.04,
        "merchant_arrival_destruction_multiplier": 4.0,
        "bounty_hunter_response_bias": 0.9,
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
        "merchant_arrival_base_destruction_chance": 0.04,
        "merchant_arrival_destruction_multiplier": 4.0,
        "bounty_hunter_response_bias": 0.9,
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


def test_pirates_destroy_merchants_arriving_in_affected_zone(monkeypatch):
    pirate_activity = {
        "enabled": True,
        "allowed_anchors": ["Earth"],
        "strength_start": 1.0,
        "strength_end_threshold": 0.5,
        "ambient_strength_decay_per_day": 0.0,
        "merchant_arrival_base_destruction_chance": 1.0,
        "merchant_arrival_destruction_multiplier": 1.0,
        "bounty_hunter_response_bias": 1.0,
        "strength_decay_per_bounty_hunter_arrival": 0.0,
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
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "333")
        monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "300")
        monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "300")

        app = create_app()
        client = app.test_client()
        headers = {"X-API-Key": "test-key"}

        try:
            started = _wait_for_action(client, headers, "pirate_started")
            assert started is not None

            store = app.config["space_store"]
            states = store.list_ship_states(status="active", in_transit=False, limit=5000)
            ship = next(
                (
                    row
                    for row in states
                    if row.get("faction") == "merchant"
                    and row.get("current_station_id")
                    and row.get("current_station_id") != "STN-PLANET-EARTH"
                ),
                None,
            )
            assert ship is not None

            now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
            departed = store.begin_ship_transit(
                ship_id=ship["ship_id"],
                source_station_id=ship["current_station_id"],
                destination_station_id="STN-PLANET-EARTH",
                departure_time=now,
                est_arrival_time=now,
            )
            assert departed is True

            found_loss = _wait_for_condition(
                lambda: any(
                    e["event_type"] == "lifecycle" and e["action"] == "pirate_losses"
                    for e in _get_control_events(client, headers)
                ),
                timeout_seconds=6.0,
            )
            assert found_loss is True

            destroyed = client.get("/ships/state?status=destroyed", headers=headers)
            assert destroyed.status_code == 200
            destroyed_ids = {row["ship_id"] for row in destroyed.get_json()["ships"]}
            assert ship["ship_id"] in destroyed_ids
        finally:
            app.config["space_simulation"].stop(timeout=3.0)
            app.config["space_store"].close()


def test_bounty_hunter_arrival_reduces_pirate_strength(monkeypatch):
    pirate_activity = {
        "enabled": True,
        "allowed_anchors": ["Earth"],
        "strength_start": 1.0,
        "strength_end_threshold": 0.5,
        "ambient_strength_decay_per_day": 0.0,
        "merchant_arrival_base_destruction_chance": 0.0,
        "merchant_arrival_destruction_multiplier": 1.0,
        "bounty_hunter_response_bias": 1.0,
        "strength_decay_per_bounty_hunter_arrival": 0.2,
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
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "444")
        monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "300")
        monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "300")

        app = create_app()
        client = app.test_client()
        headers = {"X-API-Key": "test-key"}

        try:
            started = _wait_for_action(client, headers, "pirate_started")
            assert started is not None

            store = app.config["space_store"]
            states = store.list_ship_states(status="active", in_transit=False, limit=5000)
            hunter = next(
                (
                    row
                    for row in states
                    if row.get("faction") == "bounty_hunter"
                    and row.get("current_station_id")
                    and row.get("current_station_id") != "STN-PLANET-EARTH"
                ),
                None,
            )
            assert hunter is not None

            now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
            departed = store.begin_ship_transit(
                ship_id=hunter["ship_id"],
                source_station_id=hunter["current_station_id"],
                destination_station_id="STN-PLANET-EARTH",
                departure_time=now,
                est_arrival_time=now,
            )
            assert departed is True

            found_strength_change = _wait_for_condition(
                lambda: any(
                    e["event_type"] == "lifecycle" and e["action"] == "pirate_strength_changed"
                    for e in _get_control_events(client, headers)
                ),
                timeout_seconds=6.0,
            )
            assert found_strength_change is True

            cfg = client.get("/config", headers=headers)
            assert cfg.status_code == 200
            pirate_event = cfg.get_json()["pirate_event"]
            assert pirate_event["strength"] < 1.0
        finally:
            app.config["space_simulation"].stop(timeout=3.0)
            app.config["space_store"].close()


def test_bounty_hunter_departures_shift_between_idle_and_active_pirates(monkeypatch):
    base_activity = {
        "strength_start": 1.0,
        "strength_end_threshold": 0.5,
        "ambient_strength_decay_per_day": 0.0,
        "merchant_arrival_base_destruction_chance": 0.0,
        "merchant_arrival_destruction_multiplier": 1.0,
        "bounty_hunter_response_bias": 1.0,
        "bounty_hunter_idle_departure_multiplier": 0.05,
        "bounty_hunter_active_departure_multiplier": 12.0,
        "strength_decay_per_bounty_hunter_arrival": 0.0,
        "respawn_min_days": 10.0,
        "respawn_max_days": 10.0,
    }

    with TemporaryDirectory() as tmp:
        idle_catalog_path = Path(tmp) / "idle_catalog.json"
        active_catalog_path = Path(tmp) / "active_catalog.json"

        _write_catalog(
            idle_catalog_path,
            pirate_activity={
                **base_activity,
                "enabled": False,
                "allowed_anchors": ["Earth"],
            },
            ship_count=60,
        )
        _write_catalog(
            active_catalog_path,
            pirate_activity={
                **base_activity,
                "enabled": True,
                "allowed_anchors": ["Earth"],
            },
            ship_count=60,
        )

        # Idle run: no pirate event should keep bounty-hunter departures infrequent.
        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", f"{tmp}/idle.db")
        monkeypatch.setenv("SPACE_TRAFFIC_API_KEY", "test-key")
        monkeypatch.setenv("SPACE_TRAFFIC_SEED_CATALOG_PATH", str(idle_catalog_path))
        monkeypatch.setenv("SPACE_TRAFFIC_DISABLE_GENERATOR", "false")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_MODE", "true")
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "551")
        monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "300")
        monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "300")

        idle_app = create_app()
        idle_client = idle_app.test_client()
        headers = {"X-API-Key": "test-key"}
        try:
            idle_factions = _collect_departure_factions(
                idle_client,
                headers,
                idle_app.config["space_store"],
                target_count=20,
            )
            assert len(idle_factions) >= 20
            idle_ratio = idle_factions.count("bounty_hunter") / len(idle_factions)
        finally:
            idle_app.config["space_simulation"].stop(timeout=3.0)
            idle_app.config["space_store"].close()

        # Active run: pirate event should increase bounty-hunter departures significantly.
        monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", f"{tmp}/active.db")
        monkeypatch.setenv("SPACE_TRAFFIC_SEED_CATALOG_PATH", str(active_catalog_path))
        monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_SEED", "552")

        active_app = create_app()
        active_client = active_app.test_client()
        try:
            started = _wait_for_action(active_client, headers, "pirate_started")
            assert started is not None

            active_factions = _collect_departure_factions(
                active_client,
                headers,
                active_app.config["space_store"],
                target_count=20,
            )
            assert len(active_factions) >= 20
            active_ratio = active_factions.count("bounty_hunter") / len(active_factions)
        finally:
            active_app.config["space_simulation"].stop(timeout=3.0)
            active_app.config["space_store"].close()

    assert idle_ratio <= 0.35
    assert active_ratio >= 0.55
    assert active_ratio > idle_ratio + 0.2
