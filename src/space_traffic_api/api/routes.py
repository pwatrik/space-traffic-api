from __future__ import annotations

import json
import queue
import time
from datetime import UTC, datetime

from flask import Blueprint, Response, jsonify, request

from ..auth import require_api_key
from ..simulation import SimulationService, list_faults, list_scenarios
from ..store import SQLiteStore
from .serializers import serialize_control_event, serialize_departure


def create_api_blueprint(
    api_key: str,
    store: SQLiteStore,
    simulation: SimulationService,
) -> Blueprint:
    bp = Blueprint("api", __name__)
    guard = require_api_key(api_key)

    @bp.get("/healthz")
    def healthz() -> Response:
        counts = store.get_counts()
        snapshot = simulation.snapshot()
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
        offset = min(1000000, max(0, request.args.get("offset", default=0, type=int)))
        limit = min(5000, max(1, request.args.get("limit", default=1000, type=int)))
        order_by = request.args.get("order_by", default="body_type")
        order = request.args.get("order", default="asc")
        rows, total_count = store.list_stations(
            body_type=body_type, offset=offset, limit=limit, order_by=order_by, order=order
        )
        return jsonify(
            {"stations": rows, "count": len(rows), "total_count": total_count, "offset": offset, "limit": limit}
        )

    @bp.get("/ships")
    @guard
    def ships() -> Response:
        offset = min(1000000, max(0, request.args.get("offset", default=0, type=int)))
        limit = min(5000, max(1, request.args.get("limit", default=1000, type=int)))
        order_by = request.args.get("order_by", default="id")
        order = request.args.get("order", default="asc")
        rows, total_count = store.list_ships(
            faction=request.args.get("faction"),
            home_station_id=request.args.get("home_station_id"),
            cargo=request.args.get("cargo"),
            ship_type=request.args.get("ship_type"),
            offset=offset,
            limit=limit,
            order_by=order_by,
            order=order,
        )
        return jsonify(
            {"ships": rows, "count": len(rows), "total_count": total_count, "offset": offset, "limit": limit}
        )

    @bp.get("/ships/state")
    @guard
    def ship_states() -> Response:
        status = request.args.get("status")
        in_transit_raw = request.args.get("in_transit")
        in_transit: bool | None = None
        if in_transit_raw is not None:
            in_transit = in_transit_raw.strip().lower() in {"1", "true", "yes", "on"}
        limit = min(5000, max(1, request.args.get("limit", default=500, type=int)))
        rows = store.list_ship_states(status=status, in_transit=in_transit, limit=limit)
        return jsonify({"ships": rows, "count": len(rows)})

    @bp.get("/stats")
    @guard
    def stats() -> Response:
        snapshot = simulation.snapshot()
        return jsonify(
            {
                "summary": store.get_counts(),
                "factions": store.get_ship_stats_by_faction(),
                "ship_types": store.get_ship_stats_by_type(),
                "cargo_types": store.get_cargo_stats(),
                "ship_states": store.get_ship_state_summary(),
                "pirate_strength": snapshot.get("pirate_strength", 0.0),
                "active_scenario": snapshot.get("active_scenario"),
            }
        )

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

        serialized = [serialize_departure(row) for row in rows]
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
        subscriber = simulation.subscribe_departures()

        def event_stream():
            last_heartbeat = time.time()
            try:
                while True:
                    try:
                        row = subscriber.get(timeout=1.0)
                        payload = serialize_departure(row)
                        yield f"event: departure\ndata: {json.dumps(payload)}\n\n"
                    except queue.Empty:
                        if time.time() - last_heartbeat >= 10:
                            yield ": keepalive\n\n"
                            last_heartbeat = time.time()
            finally:
                simulation.unsubscribe_departures(subscriber)

        return Response(event_stream(), mimetype="text/event-stream")

    @bp.get("/control-events")
    @guard
    def control_events() -> Response:
        since_id = request.args.get("since_id", type=int)
        limit = min(1000, max(1, request.args.get("limit", default=100, type=int)))
        order = request.args.get("order", default="asc")
        rows = simulation.list_control_events(since_id=since_id, limit=limit, order=order)
        serialized = [serialize_control_event(row) for row in rows]
        next_since_id = serialized[-1]["id"] if serialized else since_id
        return jsonify({"control_events": serialized, "count": len(serialized), "next_since_id": next_since_id})

    @bp.get("/control-events/stream")
    @guard
    def control_events_stream() -> Response:
        subscriber = simulation.subscribe_control_events()

        def event_stream():
            last_heartbeat = time.time()
            try:
                while True:
                    try:
                        row = subscriber.get(timeout=1.0)
                        payload = serialize_control_event(row)
                        yield f"event: control_event\ndata: {json.dumps(payload)}\n\n"
                    except queue.Empty:
                        if time.time() - last_heartbeat >= 10:
                            yield ": keepalive\n\n"
                            last_heartbeat = time.time()
            finally:
                simulation.unsubscribe_control_events(subscriber)

        return Response(event_stream(), mimetype="text/event-stream")

    @bp.get("/config")
    @guard
    def get_config() -> Response:
        return jsonify(simulation.snapshot())

    @bp.patch("/config")
    @guard
    def patch_config() -> Response:
        payload = request.get_json(silent=True) or {}
        updated = simulation.patch_config(payload)
        return jsonify(updated)

    @bp.get("/scenarios")
    @guard
    def get_scenarios() -> Response:
        snapshot = simulation.snapshot()
        return jsonify({"available": list_scenarios(), "active": snapshot.get("active_scenario")})

    @bp.post("/scenarios/activate")
    @guard
    def activate_scenario() -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            scenario = simulation.activate_scenario(payload)
            return jsonify({"active_scenario": scenario})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @bp.post("/scenarios/deactivate")
    @guard
    def deactivate_scenario() -> Response:
        simulation.deactivate_scenario()
        return jsonify({"active_scenario": None})

    @bp.get("/faults")
    @guard
    def get_faults() -> Response:
        snapshot = simulation.snapshot()
        return jsonify({"available": list_faults(), "active": snapshot.get("active_faults", {})})

    @bp.post("/faults/activate")
    @guard
    def activate_faults() -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            active = simulation.activate_faults(payload)
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
        active = simulation.deactivate_faults(names)
        return jsonify({"active_faults": active})

    @bp.post("/control/reset")
    @guard
    def control_reset() -> Response:
        payload = request.get_json(silent=True) or {}
        seed = payload.get("seed")
        runtime_state = simulation.reset(seed=seed)
        store.reset_departures()
        store.reset_ship_states()
        return jsonify({"status": "reset", "runtime": runtime_state})

    return bp
