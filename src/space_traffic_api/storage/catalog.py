from __future__ import annotations

import json
from typing import Any

from .shared import StorageContext


class CatalogRepository:
    def __init__(self, context: StorageContext):
        self._context = context

    def seed_stations(self, stations: list[dict[str, Any]]) -> None:
        rows = []
        for station in stations:
            row = dict(station)
            row["allowed_size_classes"] = json.dumps(station.get("allowed_size_classes", []))
            rows.append(row)

        with self._context.lock:
            self._context.conn.executemany(
                """
                INSERT INTO stations (id, name, body_name, body_type, parent_body, allowed_size_classes)
                VALUES (:id, :name, :body_name, :body_type, :parent_body, :allowed_size_classes)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    body_name=excluded.body_name,
                    body_type=excluded.body_type,
                    parent_body=excluded.parent_body,
                    allowed_size_classes=excluded.allowed_size_classes
                """,
                rows,
            )
            self._context.conn.commit()

    def seed_ships(self, ships: list[dict[str, Any]]) -> None:
        with self._context.lock:
            self._context.conn.executemany(
                """
                INSERT INTO ships (
                    id, name, faction, ship_type, size_class, displacement_million_m3, home_station_id,
                    captain_name, cargo
                )
                VALUES (
                    :id, :name, :faction, :ship_type, :size_class, :displacement_million_m3, :home_station_id,
                    :captain_name, :cargo
                )
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    faction=excluded.faction,
                    ship_type=excluded.ship_type,
                    size_class=excluded.size_class,
                    displacement_million_m3=excluded.displacement_million_m3,
                    home_station_id=excluded.home_station_id,
                    captain_name=excluded.captain_name,
                    cargo=excluded.cargo
                """,
                ships,
            )
            self._context.conn.commit()

    def list_stations(
        self,
        body_type: str | None = None,
        offset: int = 0,
        limit: int = 1000,
        order_by: str = "body_type",
        order: str = "asc",
    ) -> tuple[list[dict[str, Any]], int]:
        """List stations with pagination. Returns (rows, total_count)."""
        # Validate order_by and order to prevent SQL injection
        valid_order_by = {"id", "name", "body_name", "body_type", "parent_body"}
        valid_order = {"asc", "desc"}
        order_by = order_by if order_by in valid_order_by else "body_type"
        order = order if order in valid_order else "asc"

        where_clauses: list[str] = []
        params: list[Any] = []
        if body_type:
            where_clauses.append("body_type = ?")
            params.append(body_type)

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        # Get total count
        count_query = f"SELECT COUNT(*) FROM stations{where_sql}"
        with self._context.lock:
            total_count = int(self._context.conn.execute(count_query, params).fetchone()[0])
            # Get paginated results
            query = f"SELECT * FROM stations{where_sql} ORDER BY {order_by} {order}, id ASC LIMIT ? OFFSET ?"
            rows = self._context.conn.execute(query, params + [limit, offset]).fetchall()

        records = [dict(row) for row in rows]
        for row in records:
            raw = row.get("allowed_size_classes")
            try:
                row["allowed_size_classes"] = json.loads(raw) if raw else []
            except json.JSONDecodeError:
                row["allowed_size_classes"] = []
        return records, total_count

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
        """List ships with pagination. Returns (rows, total_count)."""
        # Validate order_by and order to prevent SQL injection
        valid_order_by = {"id", "name", "faction", "ship_type", "cargo", "home_station_id", "size_class"}
        valid_order = {"asc", "desc"}
        order_by = order_by if order_by in valid_order_by else "id"
        order = order if order in valid_order else "asc"

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

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        # Get total count
        count_query = f"SELECT COUNT(*) FROM ships{where_sql}"
        with self._context.lock:
            total_count = int(self._context.conn.execute(count_query, params).fetchone()[0])
            # Get paginated results
            if order_by == "id":
                order_clause = "ORDER BY id " + order
            else:
                # Add a unique tie-breaker to ensure stable pagination when order_by has ties
                order_clause = f"ORDER BY {order_by} {order}, id ASC"
            query = f"SELECT * FROM ships{where_sql} {order_clause} LIMIT ? OFFSET ?"
            rows = self._context.conn.execute(query, params + [limit, offset]).fetchall()
        return [dict(row) for row in rows], total_count

    def count_stations(self) -> int:
        with self._context.lock:
            return int(self._context.conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0])

    def count_ships(self) -> int:
        with self._context.lock:
            return int(self._context.conn.execute("SELECT COUNT(*) FROM ships").fetchone()[0])

    def get_ship_stats_by_faction(self) -> dict[str, int]:
        """Return ship count grouped by faction."""
        with self._context.lock:
            rows = self._context.conn.execute(
                "SELECT faction, COUNT(*) as count FROM ships GROUP BY faction ORDER BY faction"
            ).fetchall()
        return {row["faction"]: row["count"] for row in rows}

    def get_ship_stats_by_type(self) -> dict[str, int]:
        """Return ship count grouped by ship_type."""
        with self._context.lock:
            rows = self._context.conn.execute(
                "SELECT ship_type, COUNT(*) as count FROM ships GROUP BY ship_type ORDER BY ship_type"
            ).fetchall()
        return {row["ship_type"]: row["count"] for row in rows}

    def get_cargo_stats(self) -> dict[str, int]:
        """Return ship count grouped by cargo type."""
        with self._context.lock:
            rows = self._context.conn.execute(
                "SELECT cargo, COUNT(*) as count FROM ships GROUP BY cargo ORDER BY cargo"
            ).fetchall()
        return {row["cargo"]: row["count"] for row in rows}
