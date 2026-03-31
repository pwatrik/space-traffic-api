from __future__ import annotations

import sqlite3
import threading
from typing import Any

from .storage import CatalogRepository, ControlRepository, DepartureRepository, FleetRepository, StorageContext


class SQLiteStore:
    def __init__(self, db_path: str):
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        context = StorageContext(db_path=db_path, conn=conn, lock=threading.Lock())
        self._context = context
        self.catalog = CatalogRepository(context)
        self.departures = DepartureRepository(context)
        self.control = ControlRepository(context)
        self.fleet = FleetRepository(context)

    def init_schema(self) -> None:
        with self._context.lock:
            self._context.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    body_name TEXT NOT NULL,
                    body_type TEXT NOT NULL,
                    parent_body TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ships (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    faction TEXT NOT NULL,
                    ship_type TEXT NOT NULL,
                    displacement_million_m3 REAL NOT NULL,
                    home_station_id TEXT NOT NULL,
                    captain_name TEXT NOT NULL,
                    cargo TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ship_state (
                    ship_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    current_station_id TEXT,
                    in_transit INTEGER NOT NULL DEFAULT 0,
                    source_station_id TEXT,
                    destination_station_id TEXT,
                    departure_time TEXT,
                    est_arrival_time TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(ship_id) REFERENCES ships(id)
                );

                CREATE INDEX IF NOT EXISTS idx_ship_state_in_transit ON ship_state(in_transit);
                CREATE INDEX IF NOT EXISTS idx_ship_state_est_arrival_time ON ship_state(est_arrival_time);

                CREATE TABLE IF NOT EXISTS departures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_uid TEXT NOT NULL,
                    departure_time TEXT NOT NULL,
                    ship_id TEXT,
                    source_station_id TEXT,
                    destination_station_id TEXT,
                    est_arrival_time TEXT,
                    scenario TEXT,
                    fault_flags TEXT,
                    malformed INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_departures_id ON departures(id);
                CREATE INDEX IF NOT EXISTS idx_departures_departure_time ON departures(departure_time);

                CREATE TABLE IF NOT EXISTS control_state (
                    state_key TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS control_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_control_events_id ON control_events(id);
                CREATE INDEX IF NOT EXISTS idx_control_events_event_time ON control_events(event_time);
                """
            )
            self._context.conn.commit()

    def seed_stations(self, stations: list[dict[str, Any]]) -> None:
        self.catalog.seed_stations(stations)

    def seed_ships(self, ships: list[dict[str, Any]]) -> None:
        self.catalog.seed_ships(ships)

    def seed_ship_states(self, ships: list[dict[str, Any]]) -> None:
        self.fleet.seed_ship_states(ships)

    def list_stations(self, body_type: str | None = None) -> list[dict[str, Any]]:
        return self.catalog.list_stations(body_type=body_type)

    def list_ships(
        self,
        faction: str | None = None,
        home_station_id: str | None = None,
        cargo: str | None = None,
        ship_type: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.catalog.list_ships(
            faction=faction,
            home_station_id=home_station_id,
            cargo=cargo,
            ship_type=ship_type,
        )

    def list_ship_states(
        self,
        status: str | None = None,
        in_transit: bool | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        return self.fleet.list_ship_states(status=status, in_transit=in_transit, limit=limit)

    def list_available_ships(self) -> list[dict[str, Any]]:
        return self.fleet.list_available_ships()

    def begin_ship_transit(
        self,
        ship_id: str,
        source_station_id: str,
        destination_station_id: str,
        departure_time: str,
        est_arrival_time: str,
    ) -> bool:
        return self.fleet.begin_transit(
            ship_id=ship_id,
            source_station_id=source_station_id,
            destination_station_id=destination_station_id,
            departure_time=departure_time,
            est_arrival_time=est_arrival_time,
        )

    def complete_ship_arrivals(self, as_of_time: str) -> int:
        return self.fleet.complete_arrivals(as_of_time)

    def reset_ship_states(self) -> None:
        self.fleet.reset_to_home_station()

    def insert_departure(self, event: dict[str, Any]) -> int:
        return self.departures.insert(event)

    def list_departures(
        self,
        since_id: int | None,
        since_time: str | None,
        limit: int,
        order: str,
    ) -> list[dict[str, Any]]:
        return self.departures.list(
            since_id=since_id,
            since_time=since_time,
            limit=limit,
            order=order,
        )

    def trim_departures(self, max_rows: int) -> None:
        self.departures.trim(max_rows)

    def reset_departures(self) -> None:
        self.departures.reset()

    def get_db_size_bytes(self) -> int:
        return self.departures.get_db_size_bytes()

    def enforce_db_size_limit(
        self,
        max_db_size_bytes: int,
        target_utilization: float = 0.90,
        batch_size: int = 5000,
    ) -> dict[str, int]:
        return self.departures.enforce_db_size_limit(
            max_db_size_bytes=max_db_size_bytes,
            target_utilization=target_utilization,
            batch_size=batch_size,
        )

    def insert_control_event(self, event_type: str, action: str, payload: dict[str, Any]) -> int:
        return self.control.insert_event(event_type=event_type, action=action, payload=payload)

    def list_control_events(
        self,
        since_id: int | None,
        limit: int,
        order: str,
    ) -> list[dict[str, Any]]:
        return self.control.list_events(since_id=since_id, limit=limit, order=order)

    def get_counts(self) -> dict[str, int]:
        return {
            "stations": self.catalog.count_stations(),
            "ships": self.catalog.count_ships(),
            "ships_in_transit": self.fleet.count_in_transit(),
            "departures": self.departures.count(),
            "control_events": self.control.count_events(),
        }

    def set_control_state(self, state_key: str, payload: dict[str, Any]) -> None:
        self.control.set_state(state_key=state_key, payload=payload)

    def get_control_state(self, state_key: str) -> dict[str, Any] | None:
        return self.control.get_state(state_key)

    def close(self) -> None:
        with self._context.lock:
            self._context.conn.close()
