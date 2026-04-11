# API Consumption Guide

This guide shows practical ways to combine polling, streaming, and export endpoints while keeping cursor semantics stable.

## Event Cursor Basics

- `id` on departures/control-events is the canonical incremental cursor.
- Polling endpoints return `next_since_id`; use that value on your next request.
- Streaming endpoints can replay from `replay_since_id` before switching to live events.
- Export endpoints are for backfills/snapshots and support the same filter envelope used by poll/stream.

## Polling Pattern (Reliable Incremental Pull)

Use polling when you need predictable batches and explicit checkpoints.

```bash
curl "http://localhost:8000/departures?since_id=1200&limit=500&order=asc"
```

```bash
curl "http://localhost:8000/control-events?since_id=300&event_type=scenario&limit=200"
```

Recommended loop:

1. Read with `since_id` and bounded `limit`.
2. Process records in order.
3. Persist `next_since_id` only after successful downstream write.
4. Retry with same `since_id` on transient failures.

## Streaming Pattern (Low-Latency Consumption)

Use streaming when you want near-real-time updates.

```bash
curl -N "http://localhost:8000/departures/stream?replay_since_id=1200&replay_limit=500&ship_id=SHIP-0001"
```

```bash
curl -N "http://localhost:8000/control-events/stream?replay_since_id=300&replay_limit=200&event_type=fault"
```

Notes:

- `replay_limit` provides warm-start catch-up before live events.
- `: keepalive` comments are emitted periodically; ignore these in parsers.
- If stream connection drops, reconnect with last committed cursor via `replay_since_id`.

## Export Pattern (Backfill and Reconciliation)

Use exports for ad-hoc snapshots, bulk replay, or periodic reconciliation.

### Departures Export

```bash
curl "http://localhost:8000/departures/export?format=ndjson&since_time=2100-01-01T00:00:00+00:00&until_time=2100-01-02T00:00:00+00:00"
```

```bash
curl "http://localhost:8000/departures/export?format=csv&scenario=war&order_by=departure_time&order=asc" > departures.csv
```

### Control Events Export

```bash
curl "http://localhost:8000/control-events/export?format=ndjson&event_type=control"
```

```bash
curl "http://localhost:8000/control-events/export?format=csv&action=reset" > control_events.csv
```

## Compatibility Guidance

- Prefer cursor-based resumption (`since_id`) over time-only checkpoints.
- For deterministic replay windows, use both time filters and cursor filters.
- Keep consumers tolerant of additional response fields in JSON objects.
- Keep exporters strict on format values (`ndjson`, `csv`) and fail fast on invalid values.
- For exactly-once downstream semantics, deduplicate by primary key (`id`) or event UID where available.

## Backward Compatibility Contract

The API follows additive-first evolution and stable cursor semantics.

- Polling endpoints keep `next_since_id` semantics stable; cursor values are monotonic and safe for resume.
- Streaming endpoints preserve event ordering within each stream and keep replay bootstrap behavior (`replay_since_id`, `replay_limit`) backward compatible.
- Export endpoints preserve supported format values (`ndjson`, `csv`); unsupported formats continue to return `400` with a machine-readable `error` field.
- New fields may be added to JSON payloads over time, but existing stable field names are not removed/renamed in patch releases.

Consumer recommendations:

1. Treat unknown JSON fields as forward-compatible extensions.
2. Persist cursor checkpoints after successful downstream commit.
3. Use idempotent upserts keyed by `id` (and `event_uid` for departures when available).

## Suggested Integration Strategy

1. Bootstrap historical window with export endpoint (`ndjson`).
2. Continue with polling loop for stable batches.
3. Move to streaming for low-latency once baseline is in sync.
4. Run periodic export reconciliation to detect drift.
