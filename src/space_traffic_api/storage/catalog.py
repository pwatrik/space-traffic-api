from __future__ import annotations

from typing import Any

from .shared import StorageContext


class CatalogRepository:
    def __init__(self, context: StorageContext):
        self._context = context

    def seed_stations(self, stations: list[dict[str, Any]]) -> None:
        with self._context.lock:
            self._context.conn.executemany(
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
            self._context.conn.commit()

    def seed_ships(self, ships: list[dict[str, Any]]) -> None:
        with self._context.lock:
            self._context.conn.executemany(
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
            self._context.conn.commit()

    def list_stations(self, body_type: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM stations"
        params: list[Any] = []
        if body_type:
            query += " WHERE body_type = ?"
            params.append(body_type)
        query += " ORDER BY body_type, body_name"

        with self._context.lock:
            rows = self._context.conn.execute(query, params).fetchall()
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

        with self._context.lock:
            rows = self._context.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def count_stations(self) -> int:
        with self._context.lock:
            return int(self._context.conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0])

    def count_ships(self) -> int:
        with self._context.lock:
            return int(self._context.conn.execute("SELECT COUNT(*) FROM ships").fetchone()[0])
