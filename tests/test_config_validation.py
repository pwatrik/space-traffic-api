import os

import pytest

from space_traffic_api.config import AppConfig


KEY_PREFIX = "SPACE_TRAFFIC_"


def _clear_space_traffic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ.keys()):
        if key.startswith(KEY_PREFIX):
            monkeypatch.delenv(key, raising=False)


def test_from_env_rejects_non_integer_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "not-an-int")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_MIN_EVENTS_PER_MIN"):
        AppConfig.from_env()


def test_from_env_rejects_non_float_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_SIMULATION_TIME_SCALE", "not-a-float")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_SIMULATION_TIME_SCALE"):
        AppConfig.from_env()


def test_from_env_rejects_empty_db_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_DB_PATH", "   ")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_DB_PATH must not be empty"):
        AppConfig.from_env()


def test_from_env_rejects_min_events_below_one(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "0")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_MIN_EVENTS_PER_MIN must be >= 1"):
        AppConfig.from_env()


def test_from_env_rejects_max_events_below_one(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "0")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_MAX_EVENTS_PER_MIN must be >= 1"):
        AppConfig.from_env()


def test_from_env_rejects_retention_max_rows_below_one(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_RETENTION_MAX_ROWS", "0")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_RETENTION_MAX_ROWS must be >= 1"):
        AppConfig.from_env()


def test_from_env_rejects_negative_merchant_idle_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_MERCHANT_IDLE_PAUSE_SECONDS", "-1")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_MERCHANT_IDLE_PAUSE_SECONDS must be >= 0"):
        AppConfig.from_env()


def test_from_env_rejects_simulation_time_scale_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_SIMULATION_TIME_SCALE", "0")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_SIMULATION_TIME_SCALE must be > 0"):
        AppConfig.from_env()


def test_from_env_rejects_simulation_time_scale_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_SIMULATION_TIME_SCALE", "-1.5")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_SIMULATION_TIME_SCALE must be > 0"):
        AppConfig.from_env()


def test_from_env_rejects_invalid_rate_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "25")
    monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "10")

    with pytest.raises(ValueError, match="MIN_EVENTS_PER_MIN must be <= SPACE_TRAFFIC_MAX_EVENTS_PER_MIN"):
        AppConfig.from_env()


def test_from_env_rejects_invalid_boundary_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_DB_MAX_SIZE_MB", "0")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_DB_MAX_SIZE_MB must be >= 1"):
        AppConfig.from_env()


def test_from_env_rejects_invalid_deterministic_start_time(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_START_TIME", "invalid-time")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_DETERMINISTIC_START_TIME"):
        AppConfig.from_env()


def test_from_env_rejects_economy_preference_weight_below_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_ECONOMY_PREFERENCE_WEIGHT", "-0.1")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_ECONOMY_PREFERENCE_WEIGHT"):
        AppConfig.from_env()


def test_from_env_rejects_economy_preference_weight_above_one(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_ECONOMY_PREFERENCE_WEIGHT", "1.1")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_ECONOMY_PREFERENCE_WEIGHT"):
        AppConfig.from_env()


def test_from_env_rejects_economy_drift_magnitude_non_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_ECONOMY_DRIFT_MAGNITUDE", "0")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_ECONOMY_DRIFT_MAGNITUDE"):
        AppConfig.from_env()


def test_from_env_rejects_economy_departure_impact_magnitude_non_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_ECONOMY_DEPARTURE_IMPACT_MAGNITUDE", "0")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_ECONOMY_DEPARTURE_IMPACT_MAGNITUDE"):
        AppConfig.from_env()


def test_from_env_rejects_orbital_distance_multiplier_min_below_range(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MIN", "0.4")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MIN"):
        AppConfig.from_env()


def test_from_env_rejects_orbital_distance_multiplier_max_above_range(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MAX", "1.6")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MAX"):
        AppConfig.from_env()


def test_from_env_rejects_orbital_distance_multiplier_min_greater_than_max(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MIN", "0.95")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MAX", "0.9")

    with pytest.raises(ValueError, match="SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MIN must be <= SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MAX"):
        AppConfig.from_env()


def test_from_env_accepts_boundary_safe_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_space_traffic_env(monkeypatch)
    monkeypatch.setenv("SPACE_TRAFFIC_MIN_EVENTS_PER_MIN", "1")
    monkeypatch.setenv("SPACE_TRAFFIC_MAX_EVENTS_PER_MIN", "1")
    monkeypatch.setenv("SPACE_TRAFFIC_RETENTION_MAX_ROWS", "1")
    monkeypatch.setenv("SPACE_TRAFFIC_DB_MAX_SIZE_MB", "1")
    monkeypatch.setenv("SPACE_TRAFFIC_MERCHANT_IDLE_PAUSE_SECONDS", "0")
    monkeypatch.setenv("SPACE_TRAFFIC_SIMULATION_TIME_SCALE", "0.1")
    monkeypatch.setenv("SPACE_TRAFFIC_ECONOMY_PREFERENCE_WEIGHT", "1.0")
    monkeypatch.setenv("SPACE_TRAFFIC_ECONOMY_DRIFT_MAGNITUDE", "0.1")
    monkeypatch.setenv("SPACE_TRAFFIC_ECONOMY_DEPARTURE_IMPACT_MAGNITUDE", "0.001")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MODEL_ENABLED", "true")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MIN", "0.5")
    monkeypatch.setenv("SPACE_TRAFFIC_ORBITAL_DISTANCE_MULTIPLIER_MAX", "1.5")
    monkeypatch.setenv("SPACE_TRAFFIC_DETERMINISTIC_START_TIME", "2150-01-01T00:00:00Z")

    config = AppConfig.from_env()

    assert config.base_min_events_per_minute == 1
    assert config.base_max_events_per_minute == 1
    assert config.retention_max_rows == 1
    assert config.db_max_size_mb == 1
    assert config.merchant_idle_pause_seconds == 0
    assert config.simulation_time_scale == 0.1
    assert config.economy_preference_weight == 1.0
    assert config.economy_drift_magnitude == 0.1
    assert config.economy_departure_impact_magnitude == 0.001
    assert config.orbital_distance_model_enabled is True
    assert config.orbital_distance_multiplier_min == 0.5
    assert config.orbital_distance_multiplier_max == 1.5
