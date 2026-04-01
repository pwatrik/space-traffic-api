import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class AppConfig:
    db_path: str
    seed_catalog_path: str | None
    base_min_events_per_minute: int
    base_max_events_per_minute: int
    deterministic_mode: bool
    deterministic_seed: int
    deterministic_start_time: str
    retention_max_rows: int
    db_max_size_mb: int
    disable_generator: bool
    merchant_idle_pause_seconds: int
    simulation_time_scale: float

    @staticmethod
    def from_env() -> "AppConfig":
        return AppConfig(
            db_path=os.getenv("SPACE_TRAFFIC_DB_PATH", "space_traffic.db"),
            seed_catalog_path=os.getenv("SPACE_TRAFFIC_SEED_CATALOG_PATH"),
            base_min_events_per_minute=_as_int(os.getenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN"), 10),
            base_max_events_per_minute=_as_int(os.getenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN"), 20),
            deterministic_mode=_as_bool(os.getenv("SPACE_TRAFFIC_DETERMINISTIC_MODE"), False),
            deterministic_seed=_as_int(os.getenv("SPACE_TRAFFIC_DETERMINISTIC_SEED"), 424242),
            deterministic_start_time=os.getenv("SPACE_TRAFFIC_DETERMINISTIC_START_TIME", "2150-01-01T00:00:00Z"),
            retention_max_rows=_as_int(os.getenv("SPACE_TRAFFIC_RETENTION_MAX_ROWS"), 200000),
            db_max_size_mb=_as_int(os.getenv("SPACE_TRAFFIC_DB_MAX_SIZE_MB"), 512),
            disable_generator=_as_bool(os.getenv("SPACE_TRAFFIC_DISABLE_GENERATOR"), False),
            merchant_idle_pause_seconds=_as_int(os.getenv("SPACE_TRAFFIC_MERCHANT_IDLE_PAUSE_SECONDS"), 120),
            simulation_time_scale=float(os.getenv("SPACE_TRAFFIC_SIMULATION_TIME_SCALE", "1.0")),
        )
