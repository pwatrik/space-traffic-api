from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .shared import StorageContext


class ControlRepository:
    def __init__(self, context: StorageContext):
        self._context = context

    def insert_event(
        self,
        event_type: str,
        action: str,
        payload: dict[str, Any],
        event_time: str | None = None,
    ) -> int:
        effective_event_time = event_time or datetime.now(UTC).isoformat()
        with self._context.lock:
            cur = self._context.conn.execute(
                """
                INSERT INTO control_events (event_time, event_type, action, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (effective_event_time, event_type, action, json.dumps(payload)),
            )
            self._context.conn.commit()
            return int(cur.lastrowid)

    def list_events(
        self,
        since_id: int | None,
        since_time: str | None,
        until_time: str | None,
        event_type: str | None,
        action: str | None,
        limit: int,
        order_by: str,
        order: str,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if since_id is not None:
            where.append("id > ?")
            params.append(since_id)
        if since_time is not None:
            where.append("event_time >= ?")
            params.append(since_time)
        if until_time is not None:
            where.append("event_time <= ?")
            params.append(until_time)
        if event_type:
            where.append("event_type = ?")
            params.append(event_type)
        if action:
            where.append("action = ?")
            params.append(action)

        query = "SELECT * FROM control_events"
        if where:
            query += " WHERE " + " AND ".join(where)

        order_column = "id" if order_by.lower() != "event_time" else "event_time"
        direction = "DESC" if order.lower() == "desc" else "ASC"
        query += f" ORDER BY {order_column} {direction}, id {direction} LIMIT ?"
        params.append(limit)

        with self._context.lock:
            rows = self._context.conn.execute(query, params).fetchall()
        records = [dict(row) for row in rows]
        if direction == "DESC":
            records.reverse()
        return records

    def set_state(self, state_key: str, payload: dict[str, Any]) -> None:
        now = datetime.now(UTC).isoformat()
        with self._context.lock:
            self._context.conn.execute(
                """
                INSERT INTO control_state (state_key, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    state_json=excluded.state_json,
                    updated_at=excluded.updated_at
                """,
                (state_key, json.dumps(payload), now),
            )
            self._context.conn.commit()

    def get_state(self, state_key: str) -> dict[str, Any] | None:
        with self._context.lock:
            row = self._context.conn.execute(
                "SELECT state_json FROM control_state WHERE state_key = ?",
                (state_key,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def count_events(self) -> int:
        with self._context.lock:
            return int(self._context.conn.execute("SELECT COUNT(*) FROM control_events").fetchone()[0])
