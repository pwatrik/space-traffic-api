from __future__ import annotations

import json
import queue
import time
from datetime import UTC, datetime
from typing import Any

from flask import Blueprint, Response, jsonify, request

from .auth import require_api_key
from .faults import list_faults
from .generator import DepartureGenerator
from .runtime import RuntimeState
from .scenarios import list_scenarios
from .store import SQLiteStore


def _serialize_departure(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload_json")
    try:
        parsed_payload = json.loads(payload) if payload else None
    except json.JSONDecodeError:
        parsed_payload = payload

    return {
        "id": row["id"],
        "event_uid": row["event_uid"],
        "departure_time": row["departure_time"],
        "ship_id": row.get("ship_id"),
        "source_station_id": row.get("source_station_id"),
        "destination_station_id": row.get("destination_station_id"),
        "est_arrival_time": row.get("est_arrival_time"),
        "scenario": row.get("scenario"),
        "fault_flags": json.loads(row.get("fault_flags") or "[]"),
        "malformed": bool(row.get("malformed")),
        "payload": parsed_payload,
    }


def _serialize_control_event(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload")
    if payload is None:
        raw = row.get("payload_json")
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = raw

    return {
        "id": row["id"],
        "event_time": row["event_time"],
        "event_type": row["event_type"],
        "action": row["action"],
        "payload": payload,
    }


def create_api_blueprint(
    api_key: str,
    store: SQLiteStore,
    runtime: RuntimeState,
    generator: DepartureGenerator,
) -> Blueprint:
    bp = Blueprint("api", __name__)
    guard = require_api_key(api_key)

    @bp.get("/healthz")
    def healthz() -> Response:
        counts = store.get_counts()
        snapshot = runtime.snapshot()
        db_max_size_mb = int(snapshot.get("db_max_size_mb", 512))
        return jsonify(
            {
                "status": "ok",
                "server_time": datetime.now(UTC).isoformat(),
                "counts": counts,
                "active_scenario": snapshot.get("active_scenario"),
                "active_faults": snapshot.get("active_faults", {}),
                "deterministic_mode": snapshot.get("deterministic_mode"),
                "db_size_bytes": store.get_db_size_bytes(),
                "db_max_size_bytes": db_max_size_mb * 1024 * 1024,
            }
        )

    @bp.get("/stations")
    @guard
    def stations() -> Response:
        body_type = request.args.get("body_type")
        rows = store.list_stations(body_type=body_type)
        return jsonify({"stations": rows, "count": len(rows)})

    @bp.get("/ships")
    @guard
    def ships() -> Response:
        rows = store.list_ships(
            faction=request.args.get("faction"),
            home_station_id=request.args.get("home_station_id"),
            cargo=request.args.get("cargo"),
            ship_type=request.args.get("ship_type"),
        )
        return jsonify({"ships": rows, "count": len(rows)})

    @bp.get("/departures")
    @guard
    def departures() -> Response:
        since_id = request.args.get("since_id", type=int)
        since_time = request.args.get("since_time")
        limit = min(1000, max(1, request.args.get("limit", default=100, type=int)))
        order = request.args.get("order", default="asc")

        rows = store.list_departures(
            since_id=since_id,
            since_time=since_time,
            limit=limit,
            order=order,
        )

        serialized = [_serialize_departure(row) for row in rows]
        next_since_id = serialized[-1]["id"] if serialized else since_id

        return jsonify(
            {
                "departures": serialized,
                "count": len(serialized),
                "next_since_id": next_since_id,
            }
        )

    @bp.get("/departures/stream")
    @guard
    def departures_stream() -> Response:
        subscriber = generator.subscribe()

        def event_stream():
            last_heartbeat = time.time()
            try:
                while True:
                    try:
                        row = subscriber.get(timeout=1.0)
                        payload = _serialize_departure(row)
                        yield f"event: departure\ndata: {json.dumps(payload)}\n\n"
                    except queue.Empty:
                        if time.time() - last_heartbeat >= 10:
                            yield ": keepalive\n\n"
                            last_heartbeat = time.time()
            finally:
                generator.unsubscribe(subscriber)

        return Response(event_stream(), mimetype="text/event-stream")

    @bp.get("/control-events")
    @guard
    def control_events() -> Response:
        since_id = request.args.get("since_id", type=int)
        limit = min(1000, max(1, request.args.get("limit", default=100, type=int)))
        order = request.args.get("order", default="asc")
        rows = runtime.list_control_events(since_id=since_id, limit=limit, order=order)
        serialized = [_serialize_control_event(row) for row in rows]
        next_since_id = serialized[-1]["id"] if serialized else since_id
        return jsonify({"control_events": serialized, "count": len(serialized), "next_since_id": next_since_id})

    @bp.get("/control-events/stream")
    @guard
    def control_events_stream() -> Response:
        subscriber = runtime.subscribe()

        def event_stream():
            last_heartbeat = time.time()
            try:
                while True:
                    try:
                        row = subscriber.get(timeout=1.0)
                        payload = _serialize_control_event(row)
                        yield f"event: control_event\ndata: {json.dumps(payload)}\n\n"
                    except queue.Empty:
                        if time.time() - last_heartbeat >= 10:
                            yield ": keepalive\n\n"
                            last_heartbeat = time.time()
            finally:
                runtime.unsubscribe(subscriber)

        return Response(event_stream(), mimetype="text/event-stream")

    @bp.get("/config")
    @guard
    def get_config() -> Response:
        return jsonify(runtime.snapshot())

    @bp.patch("/config")
    @guard
    def patch_config() -> Response:
        payload = request.get_json(silent=True) or {}
        updated = runtime.patch_config(payload)
        return jsonify(updated)

    @bp.get("/scenarios")
    @guard
    def get_scenarios() -> Response:
        snapshot = runtime.snapshot()
        return jsonify({"available": list_scenarios(), "active": snapshot.get("active_scenario")})

    @bp.post("/scenarios/activate")
    @guard
    def activate_scenario() -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            scenario = runtime.activate_scenario(payload)
            return jsonify({"active_scenario": scenario})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @bp.post("/scenarios/deactivate")
    @guard
    def deactivate_scenario() -> Response:
        runtime.deactivate_scenario()
        return jsonify({"active_scenario": None})

    @bp.get("/faults")
    @guard
    def get_faults() -> Response:
        snapshot = runtime.snapshot()
        return jsonify({"available": list_faults(), "active": snapshot.get("active_faults", {})})

    @bp.post("/faults/activate")
    @guard
    def activate_faults() -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            active = runtime.activate_faults(payload)
            return jsonify({"active_faults": active})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @bp.post("/faults/deactivate")
    @guard
    def deactivate_faults() -> Response:
        payload = request.get_json(silent=True) or {}
        names = payload.get("names")
        if names is not None and not isinstance(names, list):
            return jsonify({"error": "names must be an array or omitted"}), 400
        active = runtime.deactivate_faults(names)
        return jsonify({"active_faults": active})

    @bp.post("/control/reset")
    @guard
    def control_reset() -> Response:
        payload = request.get_json(silent=True) or {}
        seed = payload.get("seed")
        runtime_state = runtime.reset(seed=seed)
        store.reset_departures()
        return jsonify({"status": "reset", "runtime": runtime_state})

    return bp
