"""Opinionated auto-mode lap persistence policy."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


MIN_RACE_ON_SAMPLES = 120
MIN_CURRENT_LAP_ELAPSED_SECONDS = 20.0
MAX_STARTING_CURRENT_LAP_SECONDS = 5.0
MIN_PATH_DISTANCE_METERS = 250.0
MIN_TERMINAL_DISTANCE_TRAVELED_DELTA_METERS = 1_000.0
MIN_SPRINT_DISTANCE_TRAVELED_DELTA_METERS = 1_000.0
MIN_SPRINT_RACE_POSITION_SAMPLES = 30
MIN_SPRINT_ROUTE_GUIDANCE_SAMPLES = 30
RACE_TIME_ALIGNMENT_ABSOLUTE_TOLERANCE_SECONDS = 5.0
RACE_TIME_ALIGNMENT_RELATIVE_TOLERANCE = 0.20
HARD_REJECT_UNCERTAINTIES = frozenset({"partial_lap", "no_lap_signal", "teleport", "paused"})


@dataclass(frozen=True)
class AutoLapVerdict:
    keep: bool
    reason: str
    completion_type: str | None = None
    lap_time_ms: int | None = None
    metrics: dict[str, float | int | bool | None] | None = None


def evaluate_auto_lap(
    samples: list[dict[str, Any]],
    *,
    reason: str,
    boundary_confidence: str,
    uncertainty: str | None,
    track_profile_assigned: bool = False,
) -> AutoLapVerdict:
    """Return whether an auto-created lap record is worth keeping.

    Manual mode bypasses this helper.  The rules are deliberately conservative:
    only records that look like full circuit laps, terminal race-end circuit
    laps, or full sprint events survive.
    """

    metrics = _metrics(samples)
    lap_time_ms = _lap_time_ms(metrics)
    base_rejection = _base_rejection(metrics)
    if base_rejection is not None:
        if _is_track_matched_event(metrics, track_profile_assigned):
            return AutoLapVerdict(
                True,
                "accepted_track_matched_lap",
                completion_type="track_matched_lap",
                lap_time_ms=lap_time_ms,
                metrics=metrics,
            )
        return AutoLapVerdict(False, base_rejection, metrics=metrics)

    if _is_track_matched_event(metrics, track_profile_assigned):
        return AutoLapVerdict(
            True,
            "accepted_track_matched_lap",
            completion_type="track_matched_lap",
            lap_time_ms=lap_time_ms,
            metrics=metrics,
        )

    if _is_completed_circuit(metrics, reason, boundary_confidence, uncertainty):
        return AutoLapVerdict(
            True,
            "accepted_circuit_lap",
            completion_type="circuit_lap",
            lap_time_ms=lap_time_ms,
            metrics=metrics,
        )
    if _is_terminal_circuit(metrics, uncertainty):
        return AutoLapVerdict(
            True,
            "accepted_terminal_circuit_lap",
            completion_type="terminal_circuit_lap",
            lap_time_ms=lap_time_ms,
            metrics=metrics,
        )
    if _is_completed_sprint(metrics, uncertainty):
        return AutoLapVerdict(
            True,
            "accepted_sprint_event",
            completion_type="sprint_event",
            lap_time_ms=lap_time_ms,
            metrics=metrics,
        )

    reject_reason = _profile_rejection_reason(metrics, uncertainty)
    return AutoLapVerdict(False, reject_reason, metrics=metrics)


def _metrics(samples: list[dict[str, Any]]) -> dict[str, float | int | bool | None]:
    sample_list = list(samples)
    race_on_samples = [sample for sample in sample_list if bool(sample.get("is_race_on"))]
    current_lap_values = _values(sample_list, "current_lap")
    current_race_values = _values(sample_list, "current_race_time")
    lap_numbers = [_int_value(sample.get("lap_number")) for sample in sample_list]
    lap_numbers = [value for value in lap_numbers if value is not None]
    distance_values = _values(sample_list, "distance_traveled_m")
    path_distance = _path_distance(sample_list)
    current_lap_start = current_lap_values[0] if current_lap_values else None
    current_lap_elapsed = _elapsed(current_lap_values)
    current_race_elapsed = _elapsed(current_race_values)
    distance_traveled_delta = _elapsed(distance_values)

    return {
        "sample_count": len(sample_list),
        "race_on_sample_count": len(race_on_samples),
        "current_lap_start_s": current_lap_start,
        "current_lap_elapsed_s": current_lap_elapsed,
        "current_race_time_elapsed_s": current_race_elapsed,
        "race_time_delta_aligned": _race_time_delta_aligned(
            current_lap_elapsed,
            current_race_elapsed,
        ),
        "started_near_zero": (
            current_lap_start is not None
            and current_lap_start <= MAX_STARTING_CURRENT_LAP_SECONDS
        ),
        "path_distance_m": path_distance,
        "distance_traveled_delta_m": distance_traveled_delta,
        "min_lap_number": min(lap_numbers) if lap_numbers else None,
        "max_lap_number": max(lap_numbers) if lap_numbers else None,
        "non_zero_race_position_samples": _count_non_zero(sample_list, "race_position"),
        "non_zero_route_guidance_samples": _count_route_guidance(sample_list),
    }


def _base_rejection(metrics: dict[str, float | int | bool | None]) -> str | None:
    if int(metrics["race_on_sample_count"] or 0) < MIN_RACE_ON_SAMPLES:
        return "too_few_samples"
    elapsed = float(metrics["current_lap_elapsed_s"] or 0.0)
    if elapsed <= 0.0:
        return "no_current_lap_progress"
    if elapsed < MIN_CURRENT_LAP_ELAPSED_SECONDS:
        return "current_lap_too_short"
    if metrics["started_near_zero"] is False:
        return "starts_mid_lap"
    return None


def _lap_time_ms(metrics: dict[str, float | int | bool | None]) -> int | None:
    elapsed = _float_value(metrics.get("current_lap_elapsed_s"))
    if elapsed is None or elapsed <= 0.0:
        return None
    return int(round(elapsed * 1000.0))


def _is_track_matched_event(
    metrics: dict[str, float | int | bool | None],
    track_profile_assigned: bool,
) -> bool:
    return track_profile_assigned and _lap_time_ms(metrics) is not None


def _is_completed_circuit(
    metrics: dict[str, float | int | bool | None],
    reason: str,
    boundary_confidence: str,
    uncertainty: str | None,
) -> bool:
    return (
        str(reason).lower() == "lap_boundary"
        and _normalized(boundary_confidence) == "game_field"
        and uncertainty is None
        and _max_lap_number(metrics) > 0
        and _has_substantial_path(metrics)
    )


def _is_terminal_circuit(
    metrics: dict[str, float | int | bool | None],
    uncertainty: str | None,
) -> bool:
    return (
        _normalized(uncertainty) not in HARD_REJECT_UNCERTAINTIES
        and _max_lap_number(metrics) > 0
        and _has_substantial_path(metrics)
        and float(metrics["distance_traveled_delta_m"] or 0.0)
        >= MIN_TERMINAL_DISTANCE_TRAVELED_DELTA_METERS
        and bool(metrics["race_time_delta_aligned"])
    )


def _is_completed_sprint(
    metrics: dict[str, float | int | bool | None],
    uncertainty: str | None,
) -> bool:
    return (
        _normalized(uncertainty) not in HARD_REJECT_UNCERTAINTIES
        and _max_lap_number(metrics) == 0
        and _min_lap_number(metrics) == 0
        and _has_substantial_path(metrics)
        and float(metrics["distance_traveled_delta_m"] or 0.0)
        >= MIN_SPRINT_DISTANCE_TRAVELED_DELTA_METERS
        and int(metrics["non_zero_race_position_samples"] or 0)
        >= MIN_SPRINT_RACE_POSITION_SAMPLES
        and int(metrics["non_zero_route_guidance_samples"] or 0)
        >= MIN_SPRINT_ROUTE_GUIDANCE_SAMPLES
        and bool(metrics["race_time_delta_aligned"])
    )


def _profile_rejection_reason(
    metrics: dict[str, float | int | bool | None],
    uncertainty: str | None,
) -> str:
    if _normalized(uncertainty) in HARD_REJECT_UNCERTAINTIES:
        return f"uncertainty_{_normalized(uncertainty)}"
    if float(metrics["path_distance_m"] or 0.0) < MIN_PATH_DISTANCE_METERS:
        return "insufficient_path_distance"
    if not bool(metrics["race_time_delta_aligned"]):
        return "race_time_misaligned"
    if float(metrics["distance_traveled_delta_m"] or 0.0) < MIN_TERMINAL_DISTANCE_TRAVELED_DELTA_METERS:
        return "insufficient_distance_traveled"
    if _max_lap_number(metrics) == 0:
        if int(metrics["non_zero_race_position_samples"] or 0) < MIN_SPRINT_RACE_POSITION_SAMPLES:
            return "missing_race_position"
        if int(metrics["non_zero_route_guidance_samples"] or 0) < MIN_SPRINT_ROUTE_GUIDANCE_SAMPLES:
            return "missing_route_guidance"
    return "low_confidence_boundary"


def _has_substantial_path(metrics: dict[str, float | int | bool | None]) -> bool:
    return float(metrics["path_distance_m"] or 0.0) >= MIN_PATH_DISTANCE_METERS


def _race_time_delta_aligned(current_lap_elapsed: float, current_race_elapsed: float) -> bool:
    if current_lap_elapsed <= 0.0 or current_race_elapsed <= 0.0:
        return False
    allowed_delta = max(
        RACE_TIME_ALIGNMENT_ABSOLUTE_TOLERANCE_SECONDS,
        current_lap_elapsed * RACE_TIME_ALIGNMENT_RELATIVE_TOLERANCE,
    )
    return abs(current_lap_elapsed - current_race_elapsed) <= allowed_delta


def _path_distance(samples: list[dict[str, Any]]) -> float:
    distance = 0.0
    previous: tuple[float, float, float] | None = None
    for sample in samples:
        position = _position(sample)
        if position is None:
            continue
        if previous is not None:
            distance += math.dist(previous, position)
        previous = position
    return distance


def _position(sample: dict[str, Any]) -> tuple[float, float, float] | None:
    x = _float_value(sample.get("x"))
    y = _float_value(sample.get("y"))
    z = _float_value(sample.get("z"))
    if x is None or y is None or z is None:
        return None
    return (x, y, z)


def _values(samples: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for sample in samples:
        value = _float_value(sample.get(key))
        if value is not None:
            values.append(value)
    return values


def _elapsed(values: list[float]) -> float:
    if not values:
        return 0.0
    return max(values) - min(values)


def _count_non_zero(samples: list[dict[str, Any]], key: str) -> int:
    return sum(1 for sample in samples if abs(_float_value(sample.get(key)) or 0.0) > 0.0)


def _count_route_guidance(samples: list[dict[str, Any]]) -> int:
    return sum(
        1
        for sample in samples
        if (
            abs(_float_value(sample.get("normalized_driving_line")) or 0.0) > 0.0
            or abs(_float_value(sample.get("normalized_ai_brake_difference")) or 0.0) > 0.0
        )
    )


def _max_lap_number(metrics: dict[str, float | int | bool | None]) -> int:
    value = metrics.get("max_lap_number")
    return -1 if value is None else int(value)


def _min_lap_number(metrics: dict[str, float | int | bool | None]) -> int:
    value = metrics.get("min_lap_number")
    return -1 if value is None else int(value)


def _normalized(value: object) -> str:
    return str(value or "").strip().lower()


def _int_value(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed


def _float_value(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


__all__ = ["AutoLapVerdict", "evaluate_auto_lap"]
