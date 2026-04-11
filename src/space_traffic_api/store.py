from __future__ import annotations

import json
import sqlite3
import threading
import random
from datetime import UTC, datetime
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
                    parent_body TEXT NOT NULL,
                    cargo_type TEXT NOT NULL DEFAULT '',
                    allowed_size_classes TEXT NOT NULL DEFAULT '[]',
                    economy_profile TEXT NOT NULL DEFAULT '{}',
                    economy_state TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS ships (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    faction TEXT NOT NULL,
                    ship_type TEXT NOT NULL,
                    size_class TEXT NOT NULL DEFAULT 'medium',
                    displacement_million_m3 REAL NOT NULL,
                    home_station_id TEXT NOT NULL,
                    captain_name TEXT NOT NULL,
                    cargo TEXT NOT NULL DEFAULT '',
                    crew INTEGER NOT NULL DEFAULT 0,
                    passengers INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS ship_state (
                    ship_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    current_station_id TEXT,
                    in_transit INTEGER NOT NULL DEFAULT 0,
                    ship_age_days REAL NOT NULL DEFAULT 0,
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
            # Backfill columns for pre-migration databases where tables already existed.
            self._ensure_column("stations", "allowed_size_classes", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column("stations", "cargo_type", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("stations", "economy_profile", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column("stations", "economy_state", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column("ships", "size_class", "TEXT NOT NULL DEFAULT 'medium'")
            self._ensure_column("ships", "cargo", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("ships", "crew", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("ships", "passengers", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("ship_state", "ship_age_days", "REAL NOT NULL DEFAULT 0")
            self._context.conn.commit()

    def _ensure_column(self, table_name: str, column_name: str, column_sql: str) -> None:
        cols = {
            row["name"]
            for row in self._context.conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in cols:
            self._context.conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"
            )

    def seed_stations(self, stations: list[dict[str, Any]]) -> None:
        self.catalog.seed_stations(stations)

    def seed_ships(self, ships: list[dict[str, Any]]) -> None:
        self.catalog.seed_ships(ships)

    def set_ship_cargo(self, ship_id: str, cargo: str) -> bool:
        return self.catalog.set_ship_cargo(ship_id=ship_id, cargo=cargo)

    def seed_ship_states(self, ships: list[dict[str, Any]], now_iso: str | None = None) -> None:
        self.fleet.seed_ship_states(ships, now_iso=now_iso)

    def list_stations(
        self,
        body_type: str | None = None,
        offset: int = 0,
        limit: int = 1000,
        order_by: str = "body_type",
        order: str = "asc",
    ) -> tuple[list[dict[str, Any]], int]:
        return self.catalog.list_stations(
            body_type=body_type, offset=offset, limit=limit, order_by=order_by, order=order
        )

    def list_ships(
        self,
        faction: str | None = None,
        home_station_id: str | None = None,
        cargo: str | None = None,
        ship_type: str | None = None,
        offset: int = 0,
        limit: int = 1000,
        order_by: str = "id",
        order: str = "asc",
    ) -> tuple[list[dict[str, Any]], int]:
        return self.catalog.list_ships(
            faction=faction,
            home_station_id=home_station_id,
            cargo=cargo,
            ship_type=ship_type,
            offset=offset,
            limit=limit,
            order_by=order_by,
            order=order,
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

    def list_active_ships_for_lifecycle(self) -> list[dict[str, Any]]:
        return self.fleet.list_active_ships_for_lifecycle()

    def increment_ship_age(self, elapsed_days: float, now_iso: str | None = None) -> int:
        return self.fleet.increment_ship_age(elapsed_days, now_iso=now_iso)

    def deactivate_ship(
        self,
        ship_id: str,
        status: str,
        current_station_id: str | None = None,
        now_iso: str | None = None,
    ) -> bool:
        return self.fleet.deactivate_ship(
            ship_id=ship_id,
            status=status,
            current_station_id=current_station_id,
            now_iso=now_iso,
        )

    def max_ship_sequence(self) -> int:
        return self.fleet.max_ship_sequence()

    def begin_ship_transit(
        self,
        ship_id: str,
        source_station_id: str,
        destination_station_id: str,
        departure_time: str,
        est_arrival_time: str,
        now_iso: str | None = None,
    ) -> bool:
        return self.fleet.begin_transit(
            ship_id=ship_id,
            source_station_id=source_station_id,
            destination_station_id=destination_station_id,
            departure_time=departure_time,
            est_arrival_time=est_arrival_time,
            now_iso=now_iso,
        )

    def begin_departure(
        self,
        ship_id: str,
        source_station_id: str,
        destination_station_id: str,
        departure_time: str,
        est_arrival_time: str,
        cargo: str | None = None,
        now_iso: str | None = None,
    ) -> bool:
        now = now_iso or departure_time
        with self._context.lock:
            cur = self._context.conn.execute(
                """
                UPDATE ship_state
                SET
                    in_transit = 1,
                    current_station_id = NULL,
                    source_station_id = ?,
                    destination_station_id = ?,
                    departure_time = ?,
                    est_arrival_time = ?,
                    updated_at = ?
                WHERE
                    ship_id = ?
                    AND status = 'active'
                    AND in_transit = 0
                    AND current_station_id = ?
                """,
                (
                    source_station_id,
                    destination_station_id,
                    departure_time,
                    est_arrival_time,
                    now,
                    ship_id,
                    source_station_id,
                ),
            )
            if int(cur.rowcount) <= 0:
                self._context.conn.rollback()
                return False

            if cargo is not None:
                self._context.conn.execute(
                    "UPDATE ships SET cargo = ? WHERE id = ?",
                    (cargo, ship_id),
                )

            self._context.conn.commit()
            return True

    def complete_ship_arrivals(self, as_of_time: str) -> int:
        return self.fleet.complete_arrivals(as_of_time)

    def complete_ship_arrivals_with_details(self, as_of_time: str, now_iso: str | None = None) -> list[dict[str, Any]]:
        return self.fleet.complete_arrivals_with_details(as_of_time, now_iso=now_iso)

    def reset_ship_states(self, now_iso: str | None = None) -> None:
        self.fleet.reset_to_home_station(now_iso=now_iso)

    def insert_departure(self, event: dict[str, Any]) -> int:
        return self.departures.insert(event)

    def persist_departure_with_economy_impact(
        self,
        event: dict[str, Any],
        rng: random.Random | None = None,
        magnitude: float = 0.012,
    ) -> int:
        rng = rng or random.Random()
        magnitude = max(0.001, min(0.2, float(magnitude)))

        with self._context.lock:
            cur = self._context.conn.execute(
                """
                INSERT INTO departures (
                    event_uid, departure_time, ship_id, source_station_id, destination_station_id,
                    est_arrival_time, scenario, fault_flags, malformed, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_uid"],
                    event["departure_time"],
                    event.get("ship_id"),
                    event.get("source_station_id"),
                    event.get("destination_station_id"),
                    event.get("est_arrival_time"),
                    event.get("scenario"),
                    json.dumps(event.get("fault_flags", [])),
                    1 if event.get("malformed") else 0,
                    event["payload_json"],
                    event.get("created_at") or datetime.now(UTC).isoformat(),
                ),
            )

            source_station_id = str(event.get("source_station_id") or "")
            destination_station_id = str(event.get("destination_station_id") or "")
            if source_station_id and destination_station_id:
                self.catalog._apply_economy_impact_no_commit(
                    conn=self._context.conn,
                    source_station_id=source_station_id,
                    destination_station_id=destination_station_id,
                    rng=rng,
                    magnitude=magnitude,
                )

            self._context.conn.commit()
            return int(cur.lastrowid)

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

    def insert_control_event(
        self,
        event_type: str,
        action: str,
        payload: dict[str, Any],
        event_time: str | None = None,
    ) -> int:
        return self.control.insert_event(
            event_type=event_type,
            action=action,
            payload=payload,
            event_time=event_time,
        )

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

    def get_ship_stats_by_faction(self) -> dict[str, int]:
        return self.catalog.get_ship_stats_by_faction()

    def get_ship_stats_by_type(self) -> dict[str, int]:
        return self.catalog.get_ship_stats_by_type()

    def get_cargo_stats(self) -> dict[str, int]:
        return self.catalog.get_cargo_stats()

    def get_ship_state_summary(self) -> dict[str, int]:
        return self.fleet.get_ship_state_summary()

    def get_economy_summary(self) -> dict[str, Any]:
        return self.catalog.get_economy_summary()

    def advance_station_economy(
        self,
        elapsed_days: float,
        rng: random.Random | None = None,
        magnitude: float = 1.0,
    ) -> int:
        return self.catalog.advance_station_economy(elapsed_days=elapsed_days, rng=rng, magnitude=magnitude)

    def apply_departure_economy_impact(
        self,
        source_station_id: str,
        destination_station_id: str,
        rng: random.Random | None = None,
        magnitude: float = 0.012,
    ) -> int:
        return self.catalog.apply_departure_economy_impact(
            source_station_id=source_station_id,
            destination_station_id=destination_station_id,
            rng=rng,
            magnitude=magnitude,
        )

    def set_control_state(self, state_key: str, payload: dict[str, Any]) -> None:
        self.control.set_state(state_key=state_key, payload=payload)

    def get_control_state(self, state_key: str) -> dict[str, Any] | None:
        return self.control.get_state(state_key)

    def close(self) -> None:
        with self._context.lock:
            self._context.conn.close()
