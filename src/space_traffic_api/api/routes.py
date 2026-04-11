from __future__ import annotations

import json
import pathlib
import queue
import time
from csv import DictWriter
from datetime import UTC, datetime
from io import StringIO

from flask import Blueprint, Response, jsonify, redirect, render_template, request

from ..simulation import SimulationService, list_faults, list_scenarios
from ..store import SQLiteStore
from .serializers import serialize_control_event, serialize_departure


def _parse_optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _normalize_dt(dt: datetime | None) -> datetime | None:
    """Return dt converted to UTC-aware; naive datetimes are assumed UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _matches_time_window(value: str | None, since_time: str | None, until_time: str | None) -> bool:
    if value is None:
        return False
    event_time = _normalize_dt(_parse_iso_datetime(value))
    since_dt = _normalize_dt(_parse_iso_datetime(since_time))
    until_dt = _normalize_dt(_parse_iso_datetime(until_time))
    if event_time is None:
        return False
    if since_dt is not None and event_time < since_dt:
        return False
    if until_dt is not None and event_time > until_dt:
        return False
    return True


def _matches_departure_filters(
    payload: dict[str, object],
    *,
    since_time: str | None,
    until_time: str | None,
    ship_id: str | None,
    source_station_id: str | None,
    destination_station_id: str | None,
    scenario: str | None,
    malformed: bool | None,
) -> bool:
    if not _matches_time_window(payload.get("departure_time"), since_time, until_time):
        return False
    if ship_id and payload.get("ship_id") != ship_id:
        return False
    if source_station_id and payload.get("source_station_id") != source_station_id:
        return False
    if destination_station_id and payload.get("destination_station_id") != destination_station_id:
        return False
    if scenario and payload.get("scenario") != scenario:
        return False
    if malformed is not None and bool(payload.get("malformed")) != malformed:
        return False
    return True


def _matches_control_event_filters(
    payload: dict[str, object],
    *,
    since_time: str | None,
    until_time: str | None,
    event_type: str | None,
    action: str | None,
) -> bool:
    if not _matches_time_window(payload.get("event_time"), since_time, until_time):
        return False
    if event_type and payload.get("event_type") != event_type:
        return False
    if action and payload.get("action") != action:
        return False
    return True


def create_api_blueprint(
    store: SQLiteStore,
    simulation: SimulationService,
) -> Blueprint:
    bp = Blueprint("api", __name__)

    _OPENAPI_PATH = pathlib.Path(__file__).parent.parent.parent.parent / "docs" / "openapi.yaml"

    @bp.get("/openapi.yaml")
    def openapi_spec() -> Response:
        try:
            content = _OPENAPI_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            return Response("OpenAPI spec not found.", status=404, mimetype="text/plain")
        return Response(content, mimetype="application/yaml")

    @bp.get("/")
    def root_ui() -> Response:
        return redirect("/ui", code=302)

    @bp.get("/ui")
    def dashboard_ui() -> str:
        return render_template("dashboard.html")

    @bp.get("/healthz")
    def healthz() -> Response:
        counts = store.get_counts()
        snapshot = simulation.snapshot(counts=counts)
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
                "runtime_metrics": snapshot.get("runtime_metrics", {}),
            }
        )

    @bp.get("/stations")
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
    def stats() -> Response:
        counts = store.get_counts()
        snapshot = simulation.snapshot(counts=counts)
        return jsonify(
            {
                "summary": counts,
                "factions": store.get_ship_stats_by_faction(),
                "ship_types": store.get_ship_stats_by_type(),
                "cargo_types": store.get_cargo_stats(),
                "ship_states": store.get_ship_state_summary(),
                "economy_summary": store.get_economy_summary(),
                "pirate_strength": snapshot.get("pirate_strength", 0.0),
                "active_scenario": snapshot.get("active_scenario"),
                "runtime_metrics": snapshot.get("runtime_metrics", {}),
            }
        )

    @bp.get("/departures")
    def departures() -> Response:
        since_id = request.args.get("since_id", type=int)
        since_time = request.args.get("since_time")
        until_time = request.args.get("until_time")
        ship_id = request.args.get("ship_id")
        source_station_id = request.args.get("source_station_id")
        destination_station_id = request.args.get("destination_station_id")
        scenario = request.args.get("scenario")
        malformed = _parse_optional_bool(request.args.get("malformed"))
        limit = min(1000, max(1, request.args.get("limit", default=100, type=int)))
        order_by = request.args.get("order_by", default="id")
        order = request.args.get("order", default="asc")

        rows = store.list_departures(
            since_id=since_id,
            since_time=since_time,
            until_time=until_time,
            ship_id=ship_id,
            source_station_id=source_station_id,
            destination_station_id=destination_station_id,
            scenario=scenario,
            malformed=malformed,
            limit=limit,
            order_by=order_by,
            order=order,
        )

        serialized = [serialize_departure(row) for row in rows]
        next_since_id = max((r["id"] for r in serialized), default=since_id)

        return jsonify(
            {
                "departures": serialized,
                "count": len(serialized),
                "next_since_id": next_since_id,
            }
        )

    @bp.get("/departures/export")
    def departures_export() -> Response:
        since_id = request.args.get("since_id", type=int)
        since_time = request.args.get("since_time")
        until_time = request.args.get("until_time")
        ship_id = request.args.get("ship_id")
        source_station_id = request.args.get("source_station_id")
        destination_station_id = request.args.get("destination_station_id")
        scenario = request.args.get("scenario")
        malformed = _parse_optional_bool(request.args.get("malformed"))
        limit = min(10000, max(1, request.args.get("limit", default=1000, type=int)))
        order_by = request.args.get("order_by", default="id")
        order = request.args.get("order", default="asc")
        export_format = request.args.get("format", default="ndjson").strip().lower()

        if export_format not in {"ndjson", "csv"}:
            return jsonify({"error": "format must be one of: ndjson, csv"}), 400

        rows = store.list_departures(
            since_id=since_id,
            since_time=since_time,
            until_time=until_time,
            ship_id=ship_id,
            source_station_id=source_station_id,
            destination_station_id=destination_station_id,
            scenario=scenario,
            malformed=malformed,
            limit=limit,
            order_by=order_by,
            order=order,
        )
        serialized = [serialize_departure(row) for row in rows]

        if export_format == "ndjson":
            lines = [json.dumps(item, separators=(",", ":")) for item in serialized]
            body = "\n".join(lines)
            if body:
                body += "\n"
            return Response(body, mimetype="application/x-ndjson")

        output = StringIO()
        fieldnames = [
            "id",
            "event_uid",
            "departure_time",
            "ship_id",
            "source_station_id",
            "destination_station_id",
            "est_arrival_time",
            "scenario",
            "fault_flags",
            "malformed",
            "payload",
        ]
        writer = DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for item in serialized:
            row = dict(item)
            row["fault_flags"] = json.dumps(row.get("fault_flags", []), separators=(",", ":"))
            row["payload"] = json.dumps(row.get("payload"), separators=(",", ":"))
            writer.writerow(row)

        return Response(output.getvalue(), mimetype="text/csv")

    @bp.get("/departures/stream")
    def departures_stream() -> Response:
        replay_since_id = request.args.get("replay_since_id", type=int)
        replay_limit = min(1000, max(0, request.args.get("replay_limit", default=0, type=int)))
        since_time = request.args.get("since_time")
        until_time = request.args.get("until_time")
        ship_id = request.args.get("ship_id")
        source_station_id = request.args.get("source_station_id")
        destination_station_id = request.args.get("destination_station_id")
        scenario = request.args.get("scenario")
        malformed = _parse_optional_bool(request.args.get("malformed"))
        subscriber = simulation.subscribe_departures()

        def event_stream():
            last_heartbeat = time.time()
            try:
                if replay_limit > 0:
                    replay_rows = store.list_departures(
                        since_id=replay_since_id,
                        since_time=since_time,
                        until_time=until_time,
                        ship_id=ship_id,
                        source_station_id=source_station_id,
                        destination_station_id=destination_station_id,
                        scenario=scenario,
                        malformed=malformed,
                        limit=replay_limit,
                        order_by="id",
                        order="asc",
                    )
                    for row in replay_rows:
                        payload = serialize_departure(row)
                        yield f"event: departure\ndata: {json.dumps(payload)}\n\n"

                while True:
                    try:
                        row = subscriber.get(timeout=1.0)
                        payload = serialize_departure(row)
                        if not _matches_departure_filters(
                            payload,
                            since_time=since_time,
                            until_time=until_time,
                            ship_id=ship_id,
                            source_station_id=source_station_id,
                            destination_station_id=destination_station_id,
                            scenario=scenario,
                            malformed=malformed,
                        ):
                            continue
                        yield f"event: departure\ndata: {json.dumps(payload)}\n\n"
                    except queue.Empty:
                        if time.time() - last_heartbeat >= 10:
                            yield ": keepalive\n\n"
                            last_heartbeat = time.time()
            finally:
                simulation.unsubscribe_departures(subscriber)

        return Response(event_stream(), mimetype="text/event-stream")

    @bp.get("/control-events")
    def control_events() -> Response:
        since_id = request.args.get("since_id", type=int)
        since_time = request.args.get("since_time")
        until_time = request.args.get("until_time")
        event_type = request.args.get("event_type")
        action = request.args.get("action")
        limit = min(1000, max(1, request.args.get("limit", default=100, type=int)))
        order_by = request.args.get("order_by", default="id")
        order = request.args.get("order", default="asc")
        rows = simulation.list_control_events(
            since_id=since_id,
            since_time=since_time,
            until_time=until_time,
            event_type=event_type,
            action=action,
            limit=limit,
            order_by=order_by,
            order=order,
        )
        serialized = [serialize_control_event(row) for row in rows]
        next_since_id = max((r["id"] for r in serialized), default=since_id)
        return jsonify({"control_events": serialized, "count": len(serialized), "next_since_id": next_since_id})

    @bp.get("/control-events/export")
    def control_events_export() -> Response:
        since_id = request.args.get("since_id", type=int)
        since_time = request.args.get("since_time")
        until_time = request.args.get("until_time")
        event_type = request.args.get("event_type")
        action = request.args.get("action")
        limit = min(10000, max(1, request.args.get("limit", default=1000, type=int)))
        order_by = request.args.get("order_by", default="id")
        order = request.args.get("order", default="asc")
        export_format = request.args.get("format", default="ndjson").strip().lower()

        if export_format not in {"ndjson", "csv"}:
            return jsonify({"error": "format must be one of: ndjson, csv"}), 400

        rows = simulation.list_control_events(
            since_id=since_id,
            since_time=since_time,
            until_time=until_time,
            event_type=event_type,
            action=action,
            limit=limit,
            order_by=order_by,
            order=order,
        )
        serialized = [serialize_control_event(row) for row in rows]

        if export_format == "ndjson":
            lines = [json.dumps(item, separators=(",", ":")) for item in serialized]
            body = "\n".join(lines)
            if body:
                body += "\n"
            return Response(body, mimetype="application/x-ndjson")

        output = StringIO()
        fieldnames = ["id", "event_time", "event_type", "action", "payload"]
        writer = DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for item in serialized:
            row = dict(item)
            row["payload"] = json.dumps(row.get("payload"), separators=(",", ":"))
            writer.writerow(row)

        return Response(output.getvalue(), mimetype="text/csv")

    @bp.get("/control-events/stream")
    def control_events_stream() -> Response:
        replay_since_id = request.args.get("replay_since_id", type=int)
        replay_limit = min(1000, max(0, request.args.get("replay_limit", default=0, type=int)))
        since_time = request.args.get("since_time")
        until_time = request.args.get("until_time")
        event_type = request.args.get("event_type")
        action = request.args.get("action")
        subscriber = simulation.subscribe_control_events()

        def event_stream():
            last_heartbeat = time.time()
            try:
                if replay_limit > 0:
                    replay_rows = simulation.list_control_events(
                        since_id=replay_since_id,
                        since_time=since_time,
                        until_time=until_time,
                        event_type=event_type,
                        action=action,
                        limit=replay_limit,
                        order_by="id",
                        order="asc",
                    )
                    for row in replay_rows:
                        payload = serialize_control_event(row)
                        yield f"event: control_event\ndata: {json.dumps(payload)}\n\n"

                while True:
                    try:
                        row = subscriber.get(timeout=1.0)
                        payload = serialize_control_event(row)
                        if not _matches_control_event_filters(
                            payload,
                            since_time=since_time,
                            until_time=until_time,
                            event_type=event_type,
                            action=action,
                        ):
                            continue
                        yield f"event: control_event\ndata: {json.dumps(payload)}\n\n"
                    except queue.Empty:
                        if time.time() - last_heartbeat >= 10:
                            yield ": keepalive\n\n"
                            last_heartbeat = time.time()
            finally:
                simulation.unsubscribe_control_events(subscriber)

        return Response(event_stream(), mimetype="text/event-stream")

    @bp.get("/config")
    def get_config() -> Response:
        return jsonify(simulation.snapshot())

    @bp.patch("/config")
    def patch_config() -> Response:
        payload = request.get_json(silent=True) or {}
        updated = simulation.patch_config(payload)
        return jsonify(updated)

    @bp.get("/scenarios")
    def get_scenarios() -> Response:
        snapshot = simulation.snapshot()
        return jsonify({"available": list_scenarios(), "active": snapshot.get("active_scenario")})

    @bp.post("/scenarios/activate")
    def activate_scenario() -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            scenario = simulation.activate_scenario(payload)
            return jsonify({"active_scenario": scenario})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @bp.post("/scenarios/deactivate")
    def deactivate_scenario() -> Response:
        simulation.deactivate_scenario()
        return jsonify({"active_scenario": None})

    @bp.get("/faults")
    def get_faults() -> Response:
        snapshot = simulation.snapshot()
        return jsonify({"available": list_faults(), "active": snapshot.get("active_faults", {})})

    @bp.post("/faults/activate")
    def activate_faults() -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            active = simulation.activate_faults(payload)
            return jsonify({"active_faults": active})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @bp.post("/faults/deactivate")
    def deactivate_faults() -> Response:
        payload = request.get_json(silent=True) or {}
        names = payload.get("names")
        if names is not None and not isinstance(names, list):
            return jsonify({"error": "names must be an array or omitted"}), 400
        active = simulation.deactivate_faults(names)
        return jsonify({"active_faults": active})

    @bp.post("/control/reset")
    def control_reset() -> Response:
        payload = request.get_json(silent=True) or {}
        seed = payload.get("seed")
        runtime_state = simulation.reset(seed=seed)
        store.reset_departures()
        store.reset_ship_states(now_iso=runtime_state.get("simulation_now"))
        return jsonify({"status": "reset", "runtime": runtime_state})

    return bp
