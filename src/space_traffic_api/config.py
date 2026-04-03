import os
from datetime import datetime
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int, var_name: str) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{var_name} must be an integer, got {value!r}")


def _as_float(value: str | None, default: float, var_name: str) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"{var_name} must be a float, got {value!r}")


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
    economy_preference_weight: float
    economy_drift_magnitude: float
    economy_departure_impact_magnitude: float

    def validate(self) -> None:
        errors: list[str] = []

        if not self.db_path.strip():
            errors.append("SPACE_TRAFFIC_DB_PATH must not be empty")

        if self.base_min_events_per_minute < 1:
            errors.append("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN must be >= 1")

        if self.base_max_events_per_minute < 1:
            errors.append("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN must be >= 1")

        if self.base_min_events_per_minute > self.base_max_events_per_minute:
            errors.append("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN must be <= SPACE_TRAFFIC_MAX_EVENTS_PER_MIN")

        if self.retention_max_rows < 1:
            errors.append("SPACE_TRAFFIC_RETENTION_MAX_ROWS must be >= 1")

        if self.db_max_size_mb < 1:
            errors.append("SPACE_TRAFFIC_DB_MAX_SIZE_MB must be >= 1")

        if self.merchant_idle_pause_seconds < 0:
            errors.append("SPACE_TRAFFIC_MERCHANT_IDLE_PAUSE_SECONDS must be >= 0")

        if self.simulation_time_scale <= 0:
            errors.append("SPACE_TRAFFIC_SIMULATION_TIME_SCALE must be > 0")

        if not (0.0 <= self.economy_preference_weight <= 1.0):
            errors.append("SPACE_TRAFFIC_ECONOMY_PREFERENCE_WEIGHT must be in [0.0, 1.0]")

        if self.economy_drift_magnitude <= 0:
            errors.append("SPACE_TRAFFIC_ECONOMY_DRIFT_MAGNITUDE must be > 0")

        if self.economy_departure_impact_magnitude <= 0:
            errors.append("SPACE_TRAFFIC_ECONOMY_DEPARTURE_IMPACT_MAGNITUDE must be > 0")

        try:
            datetime.fromisoformat(self.deterministic_start_time.replace("Z", "+00:00"))
        except ValueError:
            errors.append(
                "SPACE_TRAFFIC_DETERMINISTIC_START_TIME must be ISO-8601 (example: 2150-01-01T00:00:00Z)"
            )

        if errors:
            details = "\n".join(f"- {error}" for error in errors)
            raise ValueError(f"Invalid SPACE_TRAFFIC_* configuration:\n{details}")

    @staticmethod
    def from_env() -> "AppConfig":
        config = AppConfig(
            db_path=os.getenv("SPACE_TRAFFIC_DB_PATH", "space_traffic.db"),
            seed_catalog_path=os.getenv("SPACE_TRAFFIC_SEED_CATALOG_PATH"),
            base_min_events_per_minute=_as_int(
                os.getenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN"),
                10,
                "SPACE_TRAFFIC_MIN_EVENTS_PER_MIN",
            ),
            base_max_events_per_minute=_as_int(
                os.getenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN"),
                20,
                "SPACE_TRAFFIC_MAX_EVENTS_PER_MIN",
            ),
            deterministic_mode=_as_bool(os.getenv("SPACE_TRAFFIC_DETERMINISTIC_MODE"), False),
            deterministic_seed=_as_int(
                os.getenv("SPACE_TRAFFIC_DETERMINISTIC_SEED"),
                424242,
                "SPACE_TRAFFIC_DETERMINISTIC_SEED",
            ),
            deterministic_start_time=os.getenv("SPACE_TRAFFIC_DETERMINISTIC_START_TIME", "2150-01-01T00:00:00Z"),
            retention_max_rows=_as_int(
                os.getenv("SPACE_TRAFFIC_RETENTION_MAX_ROWS"),
                200000,
                "SPACE_TRAFFIC_RETENTION_MAX_ROWS",
            ),
            db_max_size_mb=_as_int(
                os.getenv("SPACE_TRAFFIC_DB_MAX_SIZE_MB"),
                512,
                "SPACE_TRAFFIC_DB_MAX_SIZE_MB",
            ),
            disable_generator=_as_bool(os.getenv("SPACE_TRAFFIC_DISABLE_GENERATOR"), False),
            merchant_idle_pause_seconds=_as_int(
                os.getenv("SPACE_TRAFFIC_MERCHANT_IDLE_PAUSE_SECONDS"),
                120,
                "SPACE_TRAFFIC_MERCHANT_IDLE_PAUSE_SECONDS",
            ),
            simulation_time_scale=_as_float(
                os.getenv("SPACE_TRAFFIC_SIMULATION_TIME_SCALE"),
                1.0,
                "SPACE_TRAFFIC_SIMULATION_TIME_SCALE",
            ),
            economy_preference_weight=_as_float(
                os.getenv("SPACE_TRAFFIC_ECONOMY_PREFERENCE_WEIGHT"),
                0.15,
                "SPACE_TRAFFIC_ECONOMY_PREFERENCE_WEIGHT",
            ),
            economy_drift_magnitude=_as_float(
                os.getenv("SPACE_TRAFFIC_ECONOMY_DRIFT_MAGNITUDE"),
                1.0,
                "SPACE_TRAFFIC_ECONOMY_DRIFT_MAGNITUDE",
            ),
            economy_departure_impact_magnitude=_as_float(
                os.getenv("SPACE_TRAFFIC_ECONOMY_DEPARTURE_IMPACT_MAGNITUDE"),
                0.012,
                "SPACE_TRAFFIC_ECONOMY_DEPARTURE_IMPACT_MAGNITUDE",
            ),
        )
        config.validate()
        return config
