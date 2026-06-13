"""Aggregate telemetry samples into durable lap-history summaries."""

from __future__ import annotations

import math
from typing import Any


def compute_lap_summary(samples: list[dict]) -> dict:
    """Return aggregate lap stats using existing sample keys.

    Missing metrics are reported as ``None`` instead of raising where practical.
    Counts are still returned for empty or partially populated sample lists.
    """

    samples = list(samples)
    speeds = _values(samples, "speed_mps")
    throttles = _values(samples, "throttle")
    brakes = _values(samples, "brake")
    slips = _slip_values(samples)

    return {
        "sample_count": len(samples),
        "packet_count": len(samples),
        "lap_duration_ms": _duration_ms(samples),
        "distance_estimate_m": _distance_estimate_m(samples),
        "top_speed_mps": max(speeds) if speeds else None,
        "average_speed_mps": _average(speeds),
        "max_throttle": max(throttles) if throttles else None,
        "average_throttle": _average(throttles),
        "max_brake": max(brakes) if brakes else None,
        "average_brake": _average(brakes),
        "max_slip": max(slips) if slips else None,
        "uncertainty_count": sum(1 for sample in samples if sample.get("uncertainty")),
    }


def _duration_ms(samples: list[dict]) -> int | None:
    timestamps = _values(samples, "game_timestamp_ms")
    if not timestamps:
        return None
    return int(max(timestamps) - min(timestamps))


def _distance_estimate_m(samples: list[dict]) -> float | None:
    if not samples:
        return 0.0

    distance = 0.0
    previous: tuple[float, float, float] | None = None
    for sample in samples:
        position = _position(sample)
        if position is None:
            return None
        if previous is not None:
            distance += math.dist(previous, position)
        previous = position
    return distance


def _position(sample: dict) -> tuple[float, float, float] | None:
    x = _finite_float(sample.get("x"))
    y = _finite_float(sample.get("y"))
    z = _finite_float(sample.get("z"))
    if x is None or y is None or z is None:
        return None
    return (x, y, z)


def _values(samples: list[dict], key: str) -> list[float]:
    values: list[float] = []
    for sample in samples:
        value = _finite_float(sample.get(key))
        if value is not None:
            values.append(value)
    return values


def _slip_values(samples: list[dict]) -> list[float]:
    values: list[float] = []
    for sample in samples:
        for key, raw_value in sample.items():
            if not _is_slip_key(str(key)):
                continue
            value = _finite_float(raw_value)
            if value is not None:
                values.append(abs(value))
    return values


def _is_slip_key(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered == "slip"
        or lowered.startswith("tire_slip_")
        or lowered.startswith("tirecombinedslip")
    )


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None
