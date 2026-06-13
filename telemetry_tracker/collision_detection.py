"""Collision issue detection for telemetry tracker samples.

The detector deliberately emits sparse issue markers: direct smashable telemetry
is treated as a candidate signal, then gated by measured slowdown and estimated
time loss so minor contacts do not spam the issues overlay.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from statistics import median
from typing import Any


SMASHABLE_CANDIDATE_VEL_DIFF_MPS = 0.5
SMASHABLE_MASS_CANDIDATE_VEL_DIFF_MPS = 0.1
SMASHABLE_EVENT_MIN_VEL_DIFF_MPS = 1.5
SMASHABLE_MIN_SPEED_DROP_MPS = 3.0
SMASHABLE_MIN_SPEED_DROP_PERCENT = 0.08
SMASHABLE_WARNING_TIME_LOSS_S = 0.20
SMASHABLE_CRITICAL_TIME_LOSS_S = 0.60
SMASHABLE_CRITICAL_SPEED_DROP_MPS = 8.0
SOLID_MIN_SPEED_DROP_MPS = 4.0
SOLID_MIN_SPEED_DROP_PERCENT = 0.10
SOLID_MIN_DEFICIT_DURATION_MS = 300
SOLID_CRITICAL_SPEED_DROP_MPS = 10.0
SOLID_SUPPRESSION_WINDOW_MS = 250
SOLID_ACCEL_SPIKE_MPS2 = 18.0
SOLID_ACCEL_DELTA_MPS2 = 18.0
SOLID_ANGULAR_SPIKE_RADPS = 1.5
SOLID_ANGULAR_DELTA_RADPS = 1.0
SOLID_HARD_BRAKE_INPUT = 180.0
SOLID_WARNING_TIME_LOSS_S = 0.25
SOLID_CRITICAL_TIME_LOSS_S = 0.75
GROUP_GAP_MS = 100
PRE_WINDOW_MS = 300
POST_MIN_WINDOW_MS = 500
RECOVERY_WINDOW_MS = 1500
RECOVERY_SETTLED_MS = 250
MAX_REASONABLE_SAMPLE_GAP_MS = 250


def _safe_float(value: Any, default: float | None = None) -> float | None:
    """Return ``value`` as a finite float, or ``default`` when unavailable."""

    if value is None:
        return default
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return numeric if math.isfinite(numeric) else default


def _safe_int(value: Any, default: int | None = None) -> int | None:
    """Return ``value`` as an integer, or ``default`` when unavailable."""

    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _sample_time_ms(sample: dict) -> int:
    """Return the sample timestamp used for ordering and event windows."""

    game_timestamp_ms = _safe_int(sample.get("game_timestamp_ms"))
    if game_timestamp_ms is not None:
        return game_timestamp_ms
    return _safe_int(sample.get("received_at_ms"), 0) or 0


def _sequence(sample: dict) -> int:
    """Return the sample sequence number."""

    return _safe_int(sample.get("sequence"), 0) or 0


def _speed(sample: dict) -> float:
    """Return non-negative speed in meters per second."""

    return max(0.0, _safe_float(sample.get("speed_mps"), 0.0) or 0.0)


def _brake_input(sample: dict) -> float:
    """Return non-negative brake input."""

    return max(0.0, _safe_float(sample.get("brake"), 0.0) or 0.0)


def _vector_magnitude(sample: dict, *field_names: str) -> float:
    """Return the magnitude of telemetry vector fields, treating missing values as zero."""

    return math.sqrt(
        sum((_safe_float(sample.get(field_name), 0.0) or 0.0) ** 2 for field_name in field_names)
    )


def _acceleration_magnitude(sample: dict) -> float:
    """Return acceleration magnitude in meters per second squared."""

    return _vector_magnitude(sample, "acceleration_x", "acceleration_y", "acceleration_z")


def _angular_velocity_magnitude(sample: dict) -> float:
    """Return angular velocity magnitude in radians per second."""

    return _vector_magnitude(
        sample,
        "angular_velocity_x",
        "angular_velocity_y",
        "angular_velocity_z",
    )


def _ordered_race_samples(samples: list[dict]) -> list[dict]:
    """Return race-on samples sorted by timestamp and sequence."""

    race_samples: list[dict] = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        if _is_race_on(sample):
            race_samples.append(sample)
    return sorted(race_samples, key=lambda sample: (_sample_time_ms(sample), _sequence(sample)))


def _smashable_vel_diff(sample: dict) -> float:
    """Return non-negative smashable velocity difference in meters per second."""

    return max(0.0, _safe_float(sample.get("smashable_vel_diff"), 0.0) or 0.0)


def _smashable_mass(sample: dict) -> float:
    """Return non-negative smashable mass signal."""

    return max(0.0, _safe_float(sample.get("smashable_mass"), 0.0) or 0.0)


def _is_smashable_candidate(sample: dict) -> bool:
    """Return whether a sample has enough direct smashable signal to inspect."""

    vel_diff = _smashable_vel_diff(sample)
    return (
        vel_diff > SMASHABLE_CANDIDATE_VEL_DIFF_MPS
        or (
            _smashable_mass(sample) > 0.0
            and vel_diff > SMASHABLE_MASS_CANDIDATE_VEL_DIFF_MPS
        )
    )


def _group_candidates(
    candidates: list[dict],
    anchor_score: Callable[[dict], float],
) -> list[dict]:
    """Group candidates separated by at most ``GROUP_GAP_MS``.

    The returned group dictionaries intentionally keep the anchor sample and
    grouped candidate samples explicit so later collision rules can extend the
    grouping primitive without changing callers.
    """

    groups: list[dict] = []
    current: list[dict] = []
    last_time_ms: int | None = None

    for candidate in sorted(candidates, key=lambda sample: (_sample_time_ms(sample), _sequence(sample))):
        candidate_time_ms = _sample_time_ms(candidate)
        if current and last_time_ms is not None and candidate_time_ms - last_time_ms > GROUP_GAP_MS:
            groups.append(_candidate_group(current, anchor_score))
            current = []

        current.append(candidate)
        last_time_ms = candidate_time_ms

    if current:
        groups.append(_candidate_group(current, anchor_score))
    return groups


def _samples_between(ordered_samples: list[dict], start_ms: int, end_ms: int) -> list[dict]:
    """Return samples with timestamps inside the inclusive window."""

    return [
        sample
        for sample in ordered_samples
        if start_ms <= _sample_time_ms(sample) <= end_ms
    ]


def _estimate_kinematics(ordered_samples: list[dict], anchor_sample: dict) -> dict:
    """Estimate speed loss and time-loss primitives around an anchor sample."""

    anchor_time_ms = _sample_time_ms(anchor_sample)
    pre_samples = [
        sample
        for sample in ordered_samples
        if anchor_time_ms - PRE_WINDOW_MS <= _sample_time_ms(sample) < anchor_time_ms
    ]
    pre_speed_mps = median([_speed(sample) for sample in pre_samples]) if pre_samples else _speed(anchor_sample)

    post_min_samples = _samples_between(
        ordered_samples,
        anchor_time_ms,
        anchor_time_ms + POST_MIN_WINDOW_MS,
    )
    if not post_min_samples:
        post_min_samples = [anchor_sample]
    min_post_speed_mps = min(_speed(sample) for sample in post_min_samples)
    speed_drop_mps = max(0.0, pre_speed_mps - min_post_speed_mps)
    speed_drop_percent = speed_drop_mps / max(pre_speed_mps, 1.0)

    recovery_samples = _samples_between(
        ordered_samples,
        anchor_time_ms,
        anchor_time_ms + RECOVERY_WINDOW_MS,
    )
    previous_time_ms: int | None = None
    lost_distance_m = 0.0
    deficit_duration_ms = 0
    settled_since_ms: int | None = None

    for sample in recovery_samples:
        sample_time_ms = _sample_time_ms(sample)
        if previous_time_ms is None:
            previous_time_ms = sample_time_ms
            continue

        dt_ms = sample_time_ms - previous_time_ms
        previous_time_ms = sample_time_ms
        if dt_ms <= 0 or dt_ms > MAX_REASONABLE_SAMPLE_GAP_MS:
            settled_since_ms = None
            continue

        dt_s = dt_ms / 1000.0
        actual_speed_mps = _speed(sample)
        speed_deficit_mps = max(0.0, pre_speed_mps - actual_speed_mps)
        if speed_deficit_mps > 0.0:
            lost_distance_m += speed_deficit_mps * dt_s
            deficit_duration_ms += dt_ms
            settled_since_ms = None
            continue

        if settled_since_ms is None:
            settled_since_ms = sample_time_ms
        elif sample_time_ms - settled_since_ms >= RECOVERY_SETTLED_MS:
            break

    estimated_time_loss_s = lost_distance_m / max(pre_speed_mps, 5.0)

    return {
        "pre_speed_mps": pre_speed_mps,
        "min_post_speed_mps": min_post_speed_mps,
        "speed_drop_mps": speed_drop_mps,
        "speed_drop_percent": speed_drop_percent,
        "deficit_duration_ms": deficit_duration_ms,
        "lost_distance_m": lost_distance_m,
        "estimated_time_loss_s": estimated_time_loss_s,
    }


def _generate_smashable_markers(ordered_samples: list[dict], ruleset_version: int) -> list[dict]:
    """Generate time-loss-gated direct smashable collision markers."""

    candidates = [sample for sample in ordered_samples if _is_smashable_candidate(sample)]
    markers: list[dict] = []

    for group in _group_candidates(candidates, _smashable_vel_diff):
        group_samples = group["samples"]
        max_vel_diff = max((_smashable_vel_diff(sample) for sample in group_samples), default=0.0)
        if max_vel_diff < SMASHABLE_EVENT_MIN_VEL_DIFF_MPS:
            continue

        anchor_sample = group["anchor_sample"]
        kinematics = _estimate_kinematics(ordered_samples, anchor_sample)
        speed_drop_mps = float(kinematics["speed_drop_mps"])
        speed_drop_percent = float(kinematics["speed_drop_percent"])
        estimated_time_loss_s = float(kinematics["estimated_time_loss_s"])
        if (
            speed_drop_mps < SMASHABLE_MIN_SPEED_DROP_MPS
            and speed_drop_percent < SMASHABLE_MIN_SPEED_DROP_PERCENT
        ):
            continue
        if estimated_time_loss_s < SMASHABLE_WARNING_TIME_LOSS_S:
            continue

        start_sequence = min(_sequence(sample) for sample in group_samples)
        end_sequence = max(_sequence(sample) for sample in group_samples)
        severity = (
            "critical"
            if estimated_time_loss_s >= SMASHABLE_CRITICAL_TIME_LOSS_S
            or speed_drop_mps >= SMASHABLE_CRITICAL_SPEED_DROP_MPS
            else "warning"
        )
        markers.append(
            {
                "start_sequence": start_sequence,
                "end_sequence": end_sequence,
                "metric": "collision_smashable_time_loss",
                "severity": severity,
                "reason": (
                    f"Smashable collision lost about {estimated_time_loss_s:.2f}s "
                    f"with a {speed_drop_mps:.1f} m/s speed drop."
                ),
                "ruleset_version": int(ruleset_version),
                "confidence": _smashable_confidence(
                    estimated_time_loss_s=estimated_time_loss_s,
                    speed_drop_mps=speed_drop_mps,
                    pre_speed_mps=float(kinematics["pre_speed_mps"]),
                    max_vel_diff=max_vel_diff,
                ),
                "anchor_sequence": _sequence(anchor_sample),
                "issue_kind": "Smashable collision",
                "actual_value": round(estimated_time_loss_s, 3),
                "threshold_value": SMASHABLE_WARNING_TIME_LOSS_S,
                "threshold_operator": "gte",
                "value_label": "Estimated time loss",
                "value_unit": "s",
            }
        )

    return sorted(
        markers,
        key=lambda marker: (
            int(marker.get("start_sequence", 0)),
            int(marker.get("end_sequence", 0)),
            str(marker.get("metric", "")),
        ),
    )


def _has_invalid_packet_gap(ordered_samples: list[dict], start_index: int, end_index: int) -> bool:
    """Return whether a candidate span crosses an unreliable packet gap."""

    for index in range(start_index + 1, end_index + 1):
        dt_ms = _sample_time_ms(ordered_samples[index]) - _sample_time_ms(ordered_samples[index - 1])
        if dt_ms <= 0 or dt_ms > MAX_REASONABLE_SAMPLE_GAP_MS:
            return True
    return False


def _sample_by_sequence(ordered_samples: list[dict], sequence: int) -> dict | None:
    """Return the first sample matching ``sequence``."""

    for sample in ordered_samples:
        if _sequence(sample) == sequence:
            return sample
    return None


def _has_nearby_smashable_marker(
    ordered_samples: list[dict],
    smashable_markers: list[dict],
    anchor_time_ms: int,
) -> bool:
    """Return whether a real emitted smashable marker is near an inferred anchor."""

    for marker in smashable_markers:
        marker_sequences = [
            _safe_int(marker.get("start_sequence")),
            _safe_int(marker.get("end_sequence")),
            _safe_int(marker.get("anchor_sequence")),
        ]
        marker_times = [
            _sample_time_ms(sample)
            for sequence in marker_sequences
            if sequence is not None
            for sample in [_sample_by_sequence(ordered_samples, sequence)]
            if sample is not None
        ]
        if any(abs(marker_time_ms - anchor_time_ms) <= SOLID_SUPPRESSION_WINDOW_MS for marker_time_ms in marker_times):
            return True
    return False


def _solid_candidate_impulse(previous_sample: dict, current_sample: dict) -> dict:
    """Return impulse corroborators for an inferred solid candidate pair."""

    acceleration_mps2 = _acceleration_magnitude(current_sample)
    acceleration_delta_mps2 = abs(acceleration_mps2 - _acceleration_magnitude(previous_sample))
    angular_velocity_radps = _angular_velocity_magnitude(current_sample)
    angular_delta_radps = abs(angular_velocity_radps - _angular_velocity_magnitude(previous_sample))
    acceleration_disruption = (
        acceleration_mps2 >= SOLID_ACCEL_SPIKE_MPS2
        or acceleration_delta_mps2 >= SOLID_ACCEL_DELTA_MPS2
    )
    angular_disruption = (
        angular_velocity_radps >= SOLID_ANGULAR_SPIKE_RADPS
        or angular_delta_radps >= SOLID_ANGULAR_DELTA_RADPS
    )

    return {
        "acceleration_mps2": acceleration_mps2,
        "acceleration_delta_mps2": acceleration_delta_mps2,
        "angular_velocity_radps": angular_velocity_radps,
        "angular_delta_radps": angular_delta_radps,
        "has_impulse": acceleration_disruption or angular_disruption,
        "has_angular_disruption": angular_disruption,
    }


def _solid_impulse_score(impulse: dict) -> float:
    """Return a normalized impulse clarity score for confidence ranking."""

    return max(
        float(impulse["acceleration_mps2"]) / SOLID_ACCEL_SPIKE_MPS2,
        float(impulse["acceleration_delta_mps2"]) / SOLID_ACCEL_DELTA_MPS2,
        float(impulse["angular_velocity_radps"]) / SOLID_ANGULAR_SPIKE_RADPS,
        float(impulse["angular_delta_radps"]) / SOLID_ANGULAR_DELTA_RADPS,
    )


def _is_hard_braking_without_angular_disruption(
    ordered_samples: list[dict],
    previous_sample: dict,
    current_sample: dict,
    impulse: dict,
) -> bool:
    """Return whether a candidate is better explained by deliberate hard braking."""

    if bool(impulse["has_angular_disruption"]):
        return False

    start_ms = _sample_time_ms(previous_sample) - SOLID_SUPPRESSION_WINDOW_MS
    end_ms = _sample_time_ms(current_sample)
    nearby_samples = _samples_between(ordered_samples, start_ms, end_ms)
    return any(_brake_input(sample) >= SOLID_HARD_BRAKE_INPUT for sample in nearby_samples)


def _solid_confidence(
    *,
    estimated_time_loss_s: float,
    speed_drop_mps: float,
    speed_drop_percent: float,
    impulse: dict,
) -> float:
    """Return bounded confidence for inferred solid markers."""

    time_loss_factor = min(
        0.08,
        max(0.0, estimated_time_loss_s - SOLID_WARNING_TIME_LOSS_S) / 5.0,
    )
    speed_drop_factor = min(
        0.10,
        max(speed_drop_mps / 25.0, speed_drop_percent) * 0.25,
    )
    impulse_factor = min(0.07, max(0.0, _solid_impulse_score(impulse) - 1.0) * 0.035)
    return round(min(0.95, 0.70 + time_loss_factor + speed_drop_factor + impulse_factor), 3)


def _generate_inferred_solid_markers(
    ordered_samples: list[dict],
    ruleset_version: int,
    smashable_markers: list[dict],
) -> list[dict]:
    """Generate sparse inferred solid impact markers from severe kinematic losses."""

    candidate_metadata: dict[int, dict] = {}
    candidate_samples: list[dict] = []

    for current_index in range(1, len(ordered_samples)):
        current_sample = ordered_samples[current_index]
        current_time_ms = _sample_time_ms(current_sample)
        current_speed_mps = _speed(current_sample)

        best_previous_index: int | None = None
        best_pair_speed_drop_mps = 0.0
        best_pair_speed_drop_percent = 0.0
        for previous_index in range(current_index - 1, -1, -1):
            previous_sample = ordered_samples[previous_index]
            elapsed_ms = current_time_ms - _sample_time_ms(previous_sample)
            if elapsed_ms > MAX_REASONABLE_SAMPLE_GAP_MS:
                break
            if elapsed_ms < 50:
                continue
            if _has_invalid_packet_gap(ordered_samples, previous_index, current_index):
                continue

            previous_speed_mps = _speed(previous_sample)
            pair_speed_drop_mps = previous_speed_mps - current_speed_mps
            pair_speed_drop_percent = pair_speed_drop_mps / max(previous_speed_mps, 1.0)
            if (
                pair_speed_drop_mps < SOLID_MIN_SPEED_DROP_MPS
                and pair_speed_drop_percent < SOLID_MIN_SPEED_DROP_PERCENT
            ):
                continue
            if pair_speed_drop_mps > best_pair_speed_drop_mps or (
                pair_speed_drop_mps == best_pair_speed_drop_mps
                and pair_speed_drop_percent > best_pair_speed_drop_percent
            ):
                best_previous_index = previous_index
                best_pair_speed_drop_mps = pair_speed_drop_mps
                best_pair_speed_drop_percent = pair_speed_drop_percent

        if best_previous_index is None:
            continue

        if _has_nearby_smashable_marker(ordered_samples, smashable_markers, current_time_ms):
            continue

        previous_sample = ordered_samples[best_previous_index]
        impulse = _solid_candidate_impulse(previous_sample, current_sample)
        if not bool(impulse["has_impulse"]):
            continue

        if _is_hard_braking_without_angular_disruption(
            ordered_samples,
            previous_sample,
            current_sample,
            impulse,
        ):
            continue

        candidate_samples.append(current_sample)
        candidate_metadata[id(current_sample)] = {
            "pair_speed_drop_mps": best_pair_speed_drop_mps,
            "pair_speed_drop_percent": best_pair_speed_drop_percent,
            "impulse": impulse,
        }

    markers: list[dict] = []
    for group in _group_candidates(
        candidate_samples,
        lambda sample: (
            candidate_metadata[id(sample)]["pair_speed_drop_mps"]
            + _solid_impulse_score(candidate_metadata[id(sample)]["impulse"])
        ),
    ):
        anchor_sample = group["anchor_sample"]
        anchor_metadata = candidate_metadata[id(anchor_sample)]
        kinematics = _estimate_kinematics(ordered_samples, anchor_sample)
        speed_drop_mps = float(kinematics["speed_drop_mps"])
        speed_drop_percent = float(kinematics["speed_drop_percent"])
        deficit_duration_ms = int(kinematics["deficit_duration_ms"])
        estimated_time_loss_s = float(kinematics["estimated_time_loss_s"])

        if (
            speed_drop_mps < SOLID_MIN_SPEED_DROP_MPS
            and speed_drop_percent < SOLID_MIN_SPEED_DROP_PERCENT
        ):
            continue
        if estimated_time_loss_s < SOLID_WARNING_TIME_LOSS_S:
            continue
        if (
            deficit_duration_ms < SOLID_MIN_DEFICIT_DURATION_MS
            and speed_drop_mps < SOLID_CRITICAL_SPEED_DROP_MPS
        ):
            continue

        severity = (
            "critical"
            if estimated_time_loss_s >= SOLID_CRITICAL_TIME_LOSS_S
            or speed_drop_mps >= SOLID_CRITICAL_SPEED_DROP_MPS
            else "warning"
        )
        markers.append(
            {
                "start_sequence": min(_sequence(sample) for sample in group["samples"]),
                "end_sequence": max(_sequence(sample) for sample in group["samples"]),
                "metric": "collision_solid_inferred_time_loss",
                "severity": severity,
                "reason": (
                    f"Inferred solid impact from abrupt speed loss of {speed_drop_mps:.1f} m/s "
                    f"and impulse signals, with no nearby qualifying smashable collision marker; "
                    f"estimated loss is about {estimated_time_loss_s:.2f}s."
                ),
                "ruleset_version": int(ruleset_version),
                "confidence": _solid_confidence(
                    estimated_time_loss_s=estimated_time_loss_s,
                    speed_drop_mps=speed_drop_mps,
                    speed_drop_percent=speed_drop_percent,
                    impulse=anchor_metadata["impulse"],
                ),
                "anchor_sequence": _sequence(anchor_sample),
                "issue_kind": "Solid impact (inferred)",
                "actual_value": round(estimated_time_loss_s, 3),
                "threshold_value": SOLID_WARNING_TIME_LOSS_S,
                "threshold_operator": "gte",
                "value_label": "Estimated time loss",
                "value_unit": "s",
            }
        )

    return sorted(
        markers,
        key=lambda marker: (
            int(marker.get("start_sequence", 0)),
            int(marker.get("end_sequence", 0)),
            str(marker.get("metric", "")),
        ),
    )


def generate_collision_markers(samples: list[dict], ruleset_version: int) -> list[dict]:
    """Return collision issue markers for race-on telemetry samples."""

    ordered_samples = _ordered_race_samples(samples)
    smashable_markers = _generate_smashable_markers(ordered_samples, ruleset_version)
    markers = [
        *smashable_markers,
        *_generate_inferred_solid_markers(ordered_samples, ruleset_version, smashable_markers),
    ]
    return sorted(
        markers,
        key=lambda marker: (
            int(marker.get("start_sequence", 0)),
            int(marker.get("end_sequence", 0)),
            str(marker.get("metric", "")),
        ),
    )



def _is_race_on(sample: dict) -> bool:
    race_on = sample.get("is_race_on", True)
    if race_on is None:
        return True
    if isinstance(race_on, str):
        normalized = race_on.strip().lower()
        if normalized in {"0", "false", "no", "off"}:
            return False
        if normalized in {"1", "true", "yes", "on"}:
            return True
    return bool(race_on)


def _candidate_group(
    candidates: list[dict],
    anchor_score: Callable[[dict], float],
) -> dict:
    anchor_sample = max(
        candidates,
        key=lambda sample: (anchor_score(sample), -_sample_time_ms(sample), -_sequence(sample)),
    )
    return {
        "samples": list(candidates),
        "anchor_sample": anchor_sample,
        "anchor_score": anchor_score(anchor_sample),
        "start_ms": min(_sample_time_ms(sample) for sample in candidates),
        "end_ms": max(_sample_time_ms(sample) for sample in candidates),
    }


def _smashable_confidence(
    *,
    estimated_time_loss_s: float,
    speed_drop_mps: float,
    pre_speed_mps: float,
    max_vel_diff: float,
) -> float:
    time_loss_factor = min(0.10, max(0.0, estimated_time_loss_s - SMASHABLE_WARNING_TIME_LOSS_S) / 4.0)
    speed_drop_factor = min(0.07, speed_drop_mps / max(pre_speed_mps, 1.0) * 0.20)
    vel_diff_factor = min(0.03, max_vel_diff / 50.0)
    return round(min(1.0, 0.80 + time_loss_factor + speed_drop_factor + vel_diff_factor), 3)
