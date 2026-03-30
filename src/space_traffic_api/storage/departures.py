from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from .shared import StorageContext


class DepartureRepository:
    def __init__(self, context: StorageContext):
        self._context = context

    def insert(self, event: dict[str, Any]) -> int:
        now = datetime.now(UTC).isoformat()
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
                    now,
                ),
            )
            self._context.conn.commit()
            return int(cur.lastrowid)

    def list(
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

        with self._context.lock:
            rows = self._context.conn.execute(query, params).fetchall()
        records = [dict(row) for row in rows]
        if direction == "DESC":
            records.reverse()
        return records

    def trim(self, max_rows: int) -> None:
        with self._context.lock:
            self._context.conn.execute(
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
            self._context.conn.commit()

    def reset(self) -> None:
        with self._context.lock:
            self._context.conn.execute("DELETE FROM departures")
            self._context.conn.commit()

    def get_db_size_bytes(self) -> int:
        if os.path.exists(self._context.db_path):
            return int(os.path.getsize(self._context.db_path))

        with self._context.lock:
            page_count = self._context.conn.execute("PRAGMA page_count").fetchone()[0]
            page_size = self._context.conn.execute("PRAGMA page_size").fetchone()[0]
        return int(page_count) * int(page_size)

    def enforce_db_size_limit(
        self,
        max_db_size_bytes: int,
        target_utilization: float = 0.90,
        batch_size: int = 5000,
    ) -> dict[str, int]:
        if max_db_size_bytes < 1:
            current_size = self.get_db_size_bytes()
            return {
                "before_bytes": current_size,
                "after_bytes": current_size,
                "culled_departures": 0,
                "culled_control_events": 0,
            }

        before = self.get_db_size_bytes()
        if before <= max_db_size_bytes:
            return {
                "before_bytes": before,
                "after_bytes": before,
                "culled_departures": 0,
                "culled_control_events": 0,
            }

        target_size = int(max_db_size_bytes * max(0.50, min(0.99, target_utilization)))
        culled_departures = 0
        culled_control_events = 0

        with self._context.lock:
            while self.get_db_size_bytes() > target_size:
                departures_deleted = self._context.conn.execute(
                    """
                    DELETE FROM departures
                    WHERE id IN (
                        SELECT id FROM departures
                        ORDER BY id ASC
                        LIMIT ?
                    )
                    """,
                    (batch_size,),
                ).rowcount

                if departures_deleted > 0:
                    culled_departures += int(departures_deleted)
                    self._context.conn.commit()
                    continue

                controls_deleted = self._context.conn.execute(
                    """
                    DELETE FROM control_events
                    WHERE id IN (
                        SELECT id FROM control_events
                        ORDER BY id ASC
                        LIMIT ?
                    )
                    """,
                    (batch_size,),
                ).rowcount
                if controls_deleted > 0:
                    culled_control_events += int(controls_deleted)
                    self._context.conn.commit()
                    continue

                break

            self._context.conn.commit()
            self._context.conn.execute("VACUUM")
            self._context.conn.commit()

        after = self.get_db_size_bytes()
        return {
            "before_bytes": before,
            "after_bytes": after,
            "culled_departures": culled_departures,
            "culled_control_events": culled_control_events,
        }

    def count(self) -> int:
        with self._context.lock:
            return int(self._context.conn.execute("SELECT COUNT(*) FROM departures").fetchone()[0])
