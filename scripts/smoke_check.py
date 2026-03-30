from __future__ import annotations

import json
import os
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from space_traffic_api.app import create_app


API_KEY = "smoke-key"
REPORT_PATH = Path("smoke_report.json")
ERROR_PATH = Path("smoke_report.error.txt")


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


def _normalize_departures(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "event_uid": row["event_uid"],
            "departure_time": row["departure_time"],
            "ship_id": row["ship_id"],
            "source_station_id": row["source_station_id"],
            "destination_station_id": row["destination_station_id"],
            "est_arrival_time": row["est_arrival_time"],
            "scenario": row["scenario"],
            "malformed": row["malformed"],
            "fault_flags": row["fault_flags"],
        }
        for row in events
    ]


def _capture_first_control_stream_event(app, result: dict[str, Any]) -> None:
    with app.test_client() as client:
        response = client.get("/control-events/stream", headers=_headers(), buffered=False)
        for raw_chunk in response.response:
            chunk = raw_chunk.decode("utf-8")
            for line in chunk.splitlines():
                if line.startswith("data: "):
                    result["event"] = json.loads(line[6:])
                    return


def main() -> None:
    os.environ["SPACE_TRAFFIC_API_KEY"] = API_KEY
    os.environ["SPACE_TRAFFIC_DB_PATH"] = "smoke_selfhost.db"
    os.environ["SPACE_TRAFFIC_DETERMINISTIC_MODE"] = "false"
    os.environ["SPACE_TRAFFIC_DISABLE_GENERATOR"] = "false"

    app = create_app()

    try:
        with app.test_client() as client:
            health = client.get("/healthz")
            stations = client.get("/stations", headers=_headers())
            stations_payload = stations.get_json()

            client.patch(
                "/config",
                headers=_headers(),
                json={
                    "deterministic_mode": True,
                    "deterministic_seed": 1337,
                    "base_min_events_per_minute": 60,
                    "base_max_events_per_minute": 60,
                },
            )

            client.post("/control/reset", headers=_headers(), json={"seed": 1337})
            time.sleep(4)
            first_run = client.get("/departures?limit=3", headers=_headers()).get_json()

            client.post("/control/reset", headers=_headers(), json={"seed": 1337})
            time.sleep(4)
            second_run = client.get("/departures?limit=3", headers=_headers()).get_json()

            stream_result: dict[str, Any] = {}
            stream_thread = threading.Thread(
                target=_capture_first_control_stream_event,
                args=(app, stream_result),
                daemon=True,
            )
            stream_thread.start()
            time.sleep(0.5)

            client.post(
                "/scenarios/activate",
                headers=_headers(),
                json={"name": "war", "intensity": 1.2, "duration_seconds": 120, "scope": {"type": "global"}},
            )
            client.post(
                "/faults/activate",
                headers=_headers(),
                json={
                    "faults": {
                        "malformed_payload": {"rate": 1.0, "duration_seconds": 120},
                        "out_of_order_timestamp": {"rate": 1.0, "duration_seconds": 120},
                    }
                },
            )

            stream_thread.join(timeout=5)
            time.sleep(3)

            war_departures = client.get("/departures?limit=5&order=desc", headers=_headers()).get_json()
            control_events = client.get("/control-events?limit=10&order=desc", headers=_headers()).get_json()

            summary = {
                "health": health.get_json(),
                "station_count": stations_payload["count"],
                "deterministic_match": _normalize_departures(first_run["departures"]) == _normalize_departures(second_run["departures"]),
                "first_run": first_run["departures"],
                "second_run": second_run["departures"],
                "recent_war_departures": war_departures["departures"][:3],
                "recent_control_events": control_events["control_events"][:6],
                "stream_control_event": stream_result.get("event"),
            }

        REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if ERROR_PATH.exists():
            ERROR_PATH.unlink()
        print(json.dumps(summary, indent=2))
    except Exception:
        ERROR_PATH.write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        generator = app.config.get("space_generator")
        if generator and generator.is_alive():
            generator.stop()
            generator.join(timeout=2)
        store = app.config.get("space_store")
        if store:
            store.close()


if __name__ == "__main__":
    main()