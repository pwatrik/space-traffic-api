"""Comparison utilities and divergence diagnostics for shadow harness tests."""
from __future__ import annotations

from typing import Any


# Fields that are legitimately non-deterministic or wall-clock-stamped and must
# be excluded from sequence comparisons.
_DEFAULT_IGNORE_FIELDS: frozenset[str] = frozenset(
    {
        "id",          # SQLite rowid — depends on insertion timing
        "created_at",  # wall-clock timestamp
    }
)


def normalize_departure(event: dict[str, Any], ignore: frozenset[str] = _DEFAULT_IGNORE_FIELDS) -> dict[str, Any]:
    """Return a copy of *event* with non-deterministic fields removed."""
    return {k: v for k, v in event.items() if k not in ignore}


def assert_departure_sequences_equal(
    run_a: list[dict[str, Any]],
    run_b: list[dict[str, Any]],
    *,
    label_a: str = "run_a",
    label_b: str = "run_b",
    ignore: frozenset[str] = _DEFAULT_IGNORE_FIELDS,
) -> None:
    """Assert that two departure sequences are identical after normalization.

    On failure, emits a human-readable first-mismatch report showing the index,
    field name, and both values so divergence is easy to diagnose.
    """
    norm_a = [normalize_departure(e, ignore) for e in run_a]
    norm_b = [normalize_departure(e, ignore) for e in run_b]

    assert len(norm_a) == len(norm_b), (
        f"Sequence length mismatch: {label_a}={len(norm_a)}, {label_b}={len(norm_b)}"
    )

    for i, (a, b) in enumerate(zip(norm_a, norm_b)):
        differences = _diff_event(a, b)
        assert not differences, _format_mismatch(i, differences, label_a, label_b)


def assert_event_uids_equal(
    run_a: list[dict[str, Any]],
    run_b: list[dict[str, Any]],
    *,
    label_a: str = "run_a",
    label_b: str = "run_b",
) -> None:
    """Stricter check: event_uid sequence must be identical."""
    uids_a = [e.get("event_uid") for e in run_a]
    uids_b = [e.get("event_uid") for e in run_b]
    assert uids_a == uids_b, (
        f"event_uid sequences differ.\n"
        f"  {label_a}: {uids_a}\n"
        f"  {label_b}: {uids_b}"
    )


def assert_ship_fields_equal(
    run_a: list[dict[str, Any]],
    run_b: list[dict[str, Any]],
    *,
    fields: list[str],
    label_a: str = "run_a",
    label_b: str = "run_b",
) -> None:
    """Assert specific fields in ship-state lists match across two runs."""
    assert len(run_a) == len(run_b), (
        f"Ship list length mismatch: {label_a}={len(run_a)}, {label_b}={len(run_b)}"
    )
    for i, (a, b) in enumerate(zip(run_a, run_b)):
        for field in fields:
            assert a.get(field) == b.get(field), (
                f"Ship[{i}] field '{field}' differs: "
                f"{label_a}={a.get(field)!r}, {label_b}={b.get(field)!r}"
            )


def summarize_departures(departures: list[dict[str, Any]]) -> dict[str, Any]:
    """Return aggregate summary useful as a lightweight parity check."""
    factions: dict[str, int] = {}
    destinations: set[str] = set()
    fault_count = 0
    for d in departures:
        f = d.get("faction", "unknown")
        factions[f] = factions.get(f, 0) + 1
        if d.get("destination_station_id"):
            destinations.add(d["destination_station_id"])
        if d.get("fault_flags"):
            fault_count += 1
    return {
        "count": len(departures),
        "factions": factions,
        "unique_destinations": len(destinations),
        "fault_count": fault_count,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _diff_event(a: dict[str, Any], b: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    """Return list of (field, a_val, b_val) for all differing fields."""
    all_keys = set(a) | set(b)
    return [
        (k, a.get(k), b.get(k))
        for k in sorted(all_keys)
        if a.get(k) != b.get(k)
    ]


def _format_mismatch(
    index: int,
    differences: list[tuple[str, Any, Any]],
    label_a: str,
    label_b: str,
) -> str:
    lines = [f"First mismatch at departure index {index}:"]
    for field, val_a, val_b in differences:
        lines.append(f"  field '{field}': {label_a}={val_a!r}  vs  {label_b}={val_b!r}")
    return "\n".join(lines)
