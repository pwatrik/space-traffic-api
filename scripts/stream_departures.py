from __future__ import annotations

import argparse
import signal
import sys
import urllib.request
from datetime import UTC, datetime


def _now() -> str:
    return datetime.now(UTC).isoformat()


def stream_departures(base_url: str, show_keepalive: bool) -> None:
    url = f"{base_url.rstrip('/')}/departures/stream"
    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"}, method="GET")

    print(f"[{_now()}] Connecting to {url}")
    print(f"[{_now()}] Streaming departures. Press Ctrl-C to stop.")

    event_lines: list[str] = []

    with urllib.request.urlopen(req, timeout=None) as response:
        for raw in response:
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")

            # Blank line indicates end of a server-sent event block.
            if line == "":
                if event_lines:
                    print("\n".join(event_lines), flush=True)
                    print("", flush=True)
                    event_lines.clear()
                continue

            if line.startswith(":"):
                if show_keepalive:
                    print(line, flush=True)
                continue

            event_lines.append(line)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Attach to /departures/stream on a running Space Traffic API container and print SSE output.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the running app (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--show-keepalive",
        action="store_true",
        help="Print SSE keepalive comment lines (default: off)",
    )
    args = parser.parse_args()

    # Allow Ctrl-C to terminate immediately on Windows and POSIX.
    signal.signal(signal.SIGINT, signal.default_int_handler)

    try:
        stream_departures(base_url=args.base_url, show_keepalive=args.show_keepalive)
        return 0
    except KeyboardInterrupt:
        print(f"\n[{_now()}] Stopped by user.")
        return 0
    except Exception as exc:
        print(f"[{_now()}] Stream error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
