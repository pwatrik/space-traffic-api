from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .shared import StorageContext


class FleetRepository:
    def __init__(self, context: StorageContext):
        self._context = context

    def seed_ship_states(self, ships: list[dict[str, Any]]) -> None:
        now = datetime.now(UTC).isoformat()
        rows = [
            {
                "ship_id": ship["id"],
                "current_station_id": ship["home_station_id"],
                "updated_at": now,
            }
            for ship in ships
        ]
        with self._context.lock:
            self._context.conn.executemany(
                """
                INSERT INTO ship_state (
                    ship_id,
                    status,
                    current_station_id,
                    in_transit,
                    source_station_id,
                    destination_station_id,
                    departure_time,
                    est_arrival_time,
                    updated_at
                )
                VALUES (
                    :ship_id,
                    'active',
                    :current_station_id,
                    0,
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    :updated_at
                )
                ON CONFLICT(ship_id) DO NOTHING
                """,
                rows,
            )
            self._context.conn.commit()

    def list_ship_states(
        self,
        status: str | None = None,
        in_transit: bool | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []

        if status is not None:
            where.append("ss.status = ?")
            params.append(status)
        if in_transit is not None:
            where.append("ss.in_transit = ?")
            params.append(1 if in_transit else 0)

        query = """
            SELECT
                ss.ship_id,
                s.name,
                s.faction,
                s.ship_type,
                s.home_station_id,
                ss.status,
                ss.current_station_id,
                ss.in_transit,
                ss.source_station_id,
                ss.destination_station_id,
                ss.departure_time,
                ss.est_arrival_time,
                ss.updated_at
            FROM ship_state ss
            JOIN ships s ON s.id = ss.ship_id
        """
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY ss.ship_id LIMIT ?"
        params.append(limit)

        with self._context.lock:
            rows = self._context.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def list_available_ships(self) -> list[dict[str, Any]]:
        query = """
            SELECT
                ss.ship_id,
                ss.current_station_id,
                s.faction,
                s.ship_type,
                s.size_class
            FROM ship_state ss
            JOIN ships s ON s.id = ss.ship_id
            WHERE ss.status = 'active' AND ss.in_transit = 0 AND ss.current_station_id IS NOT NULL
            ORDER BY ss.ship_id
        """
        with self._context.lock:
            rows = self._context.conn.execute(query).fetchall()
        return [dict(row) for row in rows]

    def begin_transit(
        self,
        ship_id: str,
        source_station_id: str,
        destination_station_id: str,
        departure_time: str,
        est_arrival_time: str,
    ) -> bool:
        now = datetime.now(UTC).isoformat()
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
            self._context.conn.commit()
            return int(cur.rowcount) > 0

    def complete_arrivals(self, as_of_time: str) -> int:
        now = datetime.now(UTC).isoformat()
        with self._context.lock:
            cur = self._context.conn.execute(
                """
                UPDATE ship_state
                SET
                    in_transit = 0,
                    current_station_id = destination_station_id,
                    source_station_id = NULL,
                    destination_station_id = NULL,
                    departure_time = NULL,
                    est_arrival_time = NULL,
                    updated_at = ?
                WHERE
                    status = 'active'
                    AND in_transit = 1
                    AND est_arrival_time IS NOT NULL
                    AND est_arrival_time <= ?
                """,
                (now, as_of_time),
            )
            self._context.conn.commit()
            return int(cur.rowcount)

    def reset_to_home_station(self) -> None:
        now = datetime.now(UTC).isoformat()
        with self._context.lock:
            self._context.conn.execute(
                """
                UPDATE ship_state
                SET
                    status = 'active',
                    in_transit = 0,
                    current_station_id = (
                        SELECT ships.home_station_id
                        FROM ships
                        WHERE ships.id = ship_state.ship_id
                    ),
                    source_station_id = NULL,
                    destination_station_id = NULL,
                    departure_time = NULL,
                    est_arrival_time = NULL,
                    updated_at = ?
                """,
                (now,),
            )
            self._context.conn.commit()

    def count_in_transit(self) -> int:
        with self._context.lock:
            return int(
                self._context.conn.execute(
                    "SELECT COUNT(*) FROM ship_state WHERE in_transit = 1"
                ).fetchone()[0]
            )
