from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any


class SQLiteStore:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()

    def init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
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
            self._conn.commit()

    def seed_stations(self, stations: list[dict[str, Any]]) -> None:
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO stations (id, name, body_name, body_type, parent_body)
                VALUES (:id, :name, :body_name, :body_type, :parent_body)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    body_name=excluded.body_name,
                    body_type=excluded.body_type,
                    parent_body=excluded.parent_body
                """,
                stations,
            )
            self._conn.commit()

    def seed_ships(self, ships: list[dict[str, Any]]) -> None:
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO ships (
                    id, name, faction, ship_type, displacement_million_m3, home_station_id,
                    captain_name, cargo
                )
                VALUES (
                    :id, :name, :faction, :ship_type, :displacement_million_m3, :home_station_id,
                    :captain_name, :cargo
                )
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    faction=excluded.faction,
                    ship_type=excluded.ship_type,
                    displacement_million_m3=excluded.displacement_million_m3,
                    home_station_id=excluded.home_station_id,
                    captain_name=excluded.captain_name,
                    cargo=excluded.cargo
                """,
                ships,
            )
            self._conn.commit()

    def list_stations(self, body_type: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM stations"
        params: list[Any] = []
        if body_type:
            query += " WHERE body_type = ?"
            params.append(body_type)
        query += " ORDER BY body_type, body_name"

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def list_ships(
        self,
        faction: str | None = None,
        home_station_id: str | None = None,
        cargo: str | None = None,
        ship_type: str | None = None,
    ) -> list[dict[str, Any]]:
        where_clauses: list[str] = []
        params: list[Any] = []
        if faction:
            where_clauses.append("faction = ?")
            params.append(faction)
        if home_station_id:
            where_clauses.append("home_station_id = ?")
            params.append(home_station_id)
        if cargo:
            where_clauses.append("cargo = ?")
            params.append(cargo)
        if ship_type:
            where_clauses.append("ship_type = ?")
            params.append(ship_type)

        query = "SELECT * FROM ships"
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += " ORDER BY id"

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def insert_departure(self, event: dict[str, Any]) -> int:
        now = datetime.now(UTC).isoformat()
        with self._lock:
            cur = self._conn.execute(
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
                    now,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def list_departures(
        self,
        since_id: int | None,
        since_time: str | None,
        limit: int,
        order: str,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []

        if since_id is not None:
            where.append("id > ?")
            params.append(since_id)
        if since_time is not None:
            where.append("departure_time >= ?")
            params.append(since_time)

        query = "SELECT * FROM departures"
        if where:
            query += " WHERE " + " AND ".join(where)

        direction = "DESC" if order.lower() == "desc" else "ASC"
        query += f" ORDER BY id {direction} LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        records = [dict(row) for row in rows]
        if direction == "DESC":
            records.reverse()
        return records

    def trim_departures(self, max_rows: int) -> None:
        with self._lock:
            self._conn.execute(
                """
                DELETE FROM departures
                WHERE id IN (
                    SELECT id FROM departures
                    ORDER BY id ASC
                    LIMIT (
                        SELECT CASE
                            WHEN COUNT(*) > ? THEN COUNT(*) - ?
                            ELSE 0
                        END
                        FROM departures
                    )
                )
                """,
                (max_rows, max_rows),
            )
            self._conn.commit()

    def reset_departures(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM departures")
            self._conn.commit()

    def insert_control_event(self, event_type: str, action: str, payload: dict[str, Any]) -> int:
        event_time = datetime.now(UTC).isoformat()
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO control_events (event_time, event_type, action, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (event_time, event_type, action, json.dumps(payload)),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def list_control_events(
        self,
        since_id: int | None,
        limit: int,
        order: str,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if since_id is not None:
            where.append("id > ?")
            params.append(since_id)

        query = "SELECT * FROM control_events"
        if where:
            query += " WHERE " + " AND ".join(where)

        direction = "DESC" if order.lower() == "desc" else "ASC"
        query += f" ORDER BY id {direction} LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        records = [dict(row) for row in rows]
        if direction == "DESC":
            records.reverse()
        return records

    def get_counts(self) -> dict[str, int]:
        with self._lock:
            stations = self._conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
            ships = self._conn.execute("SELECT COUNT(*) FROM ships").fetchone()[0]
            departures = self._conn.execute("SELECT COUNT(*) FROM departures").fetchone()[0]
            control_events = self._conn.execute("SELECT COUNT(*) FROM control_events").fetchone()[0]
        return {
            "stations": int(stations),
            "ships": int(ships),
            "departures": int(departures),
            "control_events": int(control_events),
        }

    def set_control_state(self, state_key: str, payload: dict[str, Any]) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO control_state (state_key, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    state_json=excluded.state_json,
                    updated_at=excluded.updated_at
                """,
                (state_key, json.dumps(payload), now),
            )
            self._conn.commit()

    def get_control_state(self, state_key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT state_json FROM control_state WHERE state_key = ?",
                (state_key,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()
