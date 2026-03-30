from __future__ import annotations

import json
import os
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = os.getenv("SPACE_TRAFFIC_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.getenv("SPACE_TRAFFIC_API_KEY", "space-demo-key")
REPORT_PATH = Path("container_sanity_report.json")
ERROR_PATH = Path("container_sanity_report.error.txt")


def _request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    with_auth: bool = True,
    expected_status: int = 200,
) -> Any:
    url = f"{BASE_URL}{path}"
    headers: dict[str, str] = {}
    data: bytes | None = None

    if with_auth:
        headers["X-API-Key"] = API_KEY

    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, method=method, headers=headers, data=data)

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status != expected_status:
                raise RuntimeError(f"{method} {path} returned {response.status}, expected {expected_status}")
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        if exc.code != expected_status:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} returned {exc.code}, expected {expected_status}. Body: {body}") from exc
        return {"status": exc.code}


def _wait_for_health() -> dict[str, Any]:
    for _ in range(30):
        try:
            payload = _request_json("GET", "/healthz", with_auth=False)
            if payload.get("status") == "ok":
                return payload
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"Container service at {BASE_URL} did not become healthy")


def main() -> None:
    try:
        health = _wait_for_health()
        _request_json("GET", "/stations", with_auth=False, expected_status=401)

        stations = _request_json("GET", "/stations")

        config = _request_json("GET", "/config")
        ships = _request_json("GET", "/ships")

        departures = None
        for _ in range(20):
            departures = _request_json("GET", "/departures?limit=5")
            if departures["count"] > 0:
                break
            time.sleep(1)

        control_events = _request_json("GET", "/control-events?limit=5")

        summary = {
            "base_url": BASE_URL,
            "health": health,
            "stations_count": stations["count"],
            "ships_count": ships["count"],
            "departures_count": departures["count"] if departures else 0,
            "control_events_count": control_events["count"],
            "deterministic_mode": config.get("deterministic_mode"),
            "active_scenario": config.get("active_scenario"),
            "active_faults": config.get("active_faults", {}),
            "sample_departure": (departures["departures"][0] if departures and departures["count"] > 0 else None),
        }

        REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if ERROR_PATH.exists():
            ERROR_PATH.unlink()
        print(json.dumps(summary, indent=2))
    except Exception:
        ERROR_PATH.write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
