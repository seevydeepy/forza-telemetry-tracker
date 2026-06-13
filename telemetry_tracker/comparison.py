"""Reference-lap selection and lap-progress delta calculations."""

from __future__ import annotations

import bisect
import json
import math
from typing import Any

from telemetry_tracker.storage import LOCAL_USER_ID, TelemetryStore


DEFAULT_SCOPE = "track_car"
SUPPORTED_SCOPES = ("track", "track_car", "track_car_build")

_TRACK_FIELDS = (
    "track_profile_id",
    "track_profile",
    "track_layout_id",
    "track_id",
    "track_slug",
    "layout_id",
    "layout_slug",
    "track_name",
)
_TRACK_SIGNATURE_FIELDS = ("track_signature", "track_hash", "route_signature")
_CAR_FIELDS = (
    "car_profile_id",
    "car_id",
    "car_slug",
    "vehicle_id",
    "vehicle_slug",
    "car_ordinal",
    "car_name",
)
_BUILD_FIELDS = (
    "build_id",
    "build_slug",
    "tune_id",
    "tune_slug",
    "setup_id",
    "setup_slug",
    "variant_id",
    "variant_slug",
    "build_name",
)
_PROGRESS_KEYS = (
    "lap_progress",
    "progress",
    "track_progress",
    "distance_progress",
    "lap_distance_progress",
    "normalized_progress",
)
_DIRECT_ELAPSED_MS_KEYS = ("lap_elapsed_ms", "elapsed_ms", "current_lap_ms")
_TIMESTAMP_MS_KEYS = ("game_timestamp_ms", "received_at_ms")


def context_key_for_lap(scope: str, lap: dict) -> str:
    """Return the stable comparison context key for ``lap`` at ``scope``.

    The storage layer already supports persisted ``comparison_contexts`` metadata.
    Current track-profile assignments take precedence over historical summary
    track contexts, so user corrections immediately affect reference selection.
    When no current assignment exists, persisted summary contexts remain the
    stable fallback.  Unknown tracks are deliberately scoped by track signature
    or session id so different unknown layouts do not collapse into one global
    bucket.
    """

    scope = _validate_scope(scope)
    if not isinstance(lap, dict):
        lap = {}

    contexts = _comparison_contexts(lap)
    track_key = _current_track_profile_key(lap)
    if track_key is None:
        direct_context = _context_from_summary_metadata(lap, scope)
        if direct_context is not None:
            return direct_context
        track_key = _track_key(lap, contexts)
    if scope == "track":
        return track_key

    car_key = _car_key(lap, contexts, scope)
    if scope == "track_car":
        return f"{track_key}|{car_key}"

    build_key = _build_key(lap, contexts)
    return f"{track_key}|{car_key}|{build_key}"


def select_reference_lap(
    store: TelemetryStore,
    lap_id: str,
    scope: str = DEFAULT_SCOPE,
) -> dict | None:
    """Select a safe reference lap for ``lap_id``.

    When the current lap has an assigned track profile the fastest eligible
    lap in the **same session** with the same profile is returned (session-
    best selection).  A lap may be its own reference when it is the fastest
    candidate.  Laps without an assigned ``track_profile_id`` never receive
    a reference.
    """

    scope = _validate_scope(scope)
    current_lap = _lap_metadata(store, lap_id)
    if current_lap is None:
        return None

    track_profile_id = _context_value_as_string(current_lap.get("track_profile_id"))
    if not track_profile_id:
        return None

    context_key = context_key_for_lap(scope, current_lap)
    session_id = _context_value_as_string(current_lap.get("session_id"))
    if session_id is None:
        return None

    candidates = store.candidate_reference_laps(
        scope,
        context_key,
        limit=1,
        session_id=session_id,
    )
    if not candidates:
        return None
    reference = dict(candidates[0])
    reference["source"] = "session_best"
    return reference


def ghost_samples_for_reference(
    store: TelemetryStore,
    reference_lap_id: str,
) -> list[dict]:
    """Return render-ready reference samples annotated with lap progress."""

    return _annotated_samples(store.samples_for_lap(reference_lap_id))


def delta_summary(
    current_samples: list[dict],
    reference_samples: list[dict],
    start_sequence: int | None = None,
    end_sequence: int | None = None,
) -> dict:
    """Compare current samples with a reference using lap progress.

    Current samples are first annotated over their full supplied lap/range so
    sequence selection keeps absolute lap-progress positions.  Reference elapsed
    time and speed are then interpolated at each selected current progress point.
    Summary time gain/loss metrics are section-local: they measure change from
    the first valid selected current-vs-reference time gap.
    """

    annotated_current = _annotated_samples(current_samples)
    annotated_reference = _annotated_samples(reference_samples)
    selected_current = _select_sequence_range(
        annotated_current,
        start_sequence=start_sequence,
        end_sequence=end_sequence,
    )
    selected_start_sequence = _selected_start_sequence(selected_current, start_sequence)
    selected_end_sequence = _selected_end_sequence(selected_current, end_sequence)
    result = {
        "start_sequence": selected_start_sequence,
        "end_sequence": selected_end_sequence,
        "sample_count": len(selected_current),
        "current_sample_count": len(selected_current),
        "reference_sample_count": len(annotated_reference),
        "time_delta_ms": None,
        "average_speed_delta_mps": None,
        "max_gain_ms": 0.0,
        "max_loss_ms": 0.0,
        "points": [],
    }
    if not selected_current or not annotated_reference:
        return result

    reference_elapsed_series = _reference_value_series(annotated_reference, "elapsed_ms")
    reference_speed_series = _reference_value_series(annotated_reference, "speed_mps")
    points: list[dict] = []
    time_deltas: list[float] = []
    speed_deltas: list[float] = []
    for sample in selected_current:
        progress = _finite_float(sample.get("lap_progress"))
        current_elapsed_ms = _finite_float(sample.get("elapsed_ms"))
        current_speed = _finite_float(sample.get("speed_mps"))
        reference_elapsed_ms = _interpolate_reference_series(
            reference_elapsed_series,
            progress,
        )
        reference_speed = _interpolate_reference_series(
            reference_speed_series,
            progress,
        )
        time_delta_ms = None
        if current_elapsed_ms is not None and reference_elapsed_ms is not None:
            time_delta_ms = current_elapsed_ms - reference_elapsed_ms
            time_deltas.append(time_delta_ms)

        speed_delta_mps = None
        if current_speed is not None and reference_speed is not None:
            speed_delta_mps = current_speed - reference_speed
            speed_deltas.append(speed_delta_mps)

        points.append(
            {
                "sequence": sample.get("sequence"),
                "lap_progress": progress,
                "current_elapsed_ms": current_elapsed_ms,
                "reference_elapsed_ms": reference_elapsed_ms,
                "time_delta_ms": time_delta_ms,
                "current_speed_mps": current_speed,
                "reference_speed_mps": reference_speed,
                "speed_delta_mps": speed_delta_mps,
            }
        )

    result["points"] = points
    if time_deltas:
        entry_time_delta_ms = time_deltas[0]
        section_time_deltas = [
            time_delta - entry_time_delta_ms
            for time_delta in time_deltas
        ]
        result["time_delta_ms"] = section_time_deltas[-1]
        result["max_gain_ms"] = max(0.0, -min(section_time_deltas))
        result["max_loss_ms"] = max(0.0, max(section_time_deltas))
    if speed_deltas:
        result["average_speed_delta_mps"] = sum(speed_deltas) / len(speed_deltas)
    return result


def _validate_scope(scope: str) -> str:
    if scope not in SUPPORTED_SCOPES:
        supported = ", ".join(SUPPORTED_SCOPES)
        raise ValueError(f"unsupported reference scope: {scope}; expected one of {supported}")
    return scope


def _lap_metadata(store: TelemetryStore, lap_id: str) -> dict | None:
    with store.connect() as con:
        row = con.execute(
            """
            SELECT laps.id AS id,
                   laps.id AS lap_id,
                   laps.user_id AS user_id,
                   laps.session_id AS session_id,
                   sessions.label AS session_label,
                   laps.lap_number AS lap_number,
                   laps.status AS status,
                   laps.started_at_ms AS started_at_ms,
                   laps.ended_at_ms AS ended_at_ms,
                   laps.ended_reason AS ended_reason,
                   laps.boundary_confidence AS boundary_confidence,
                   laps.track_profile_id AS track_profile_id,
                   lap_summaries.summary_json AS summary_json,
                   (
                       SELECT COUNT(*)
                       FROM lap_samples
                       WHERE lap_samples.lap_id = laps.id
                   ) AS stored_sample_count
            FROM laps
            JOIN sessions ON sessions.id = laps.session_id
            LEFT JOIN lap_summaries ON lap_summaries.lap_id = laps.id
            WHERE laps.id = ? AND laps.user_id = ?
            """,
            (lap_id, LOCAL_USER_ID),
        ).fetchone()
    if row is None:
        return None

    summary = _summary_from_json(row["summary_json"])
    metadata = {
        "id": row["id"],
        "lap_id": row["lap_id"],
        "user_id": row["user_id"],
        "session_id": row["session_id"],
        "session_label": row["session_label"],
        "lap_number": row["lap_number"],
        "status": row["status"],
        "started_at_ms": row["started_at_ms"],
        "ended_at_ms": row["ended_at_ms"],
        "ended_reason": row["ended_reason"],
        "boundary_confidence": row["boundary_confidence"],
        "track_profile_id": row["track_profile_id"],
        "stored_sample_count": int(row["stored_sample_count"] or 0),
        "summary": summary,
    }
    if isinstance(summary, dict):
        for key in (
            "comparison_contexts",
            "track_profile_id",
            "track_signature",
            "car_id",
            "car_slug",
            "build_id",
            "build_slug",
        ):
            if key in summary and key not in metadata:
                metadata[key] = summary[key]
    return metadata


def _summary_from_json(summary_json: str | None) -> dict | None:
    if summary_json is None:
        return None
    try:
        summary = json.loads(summary_json)
    except json.JSONDecodeError:
        return None
    return summary if isinstance(summary, dict) else None


def _context_from_summary_metadata(lap: dict, scope: str) -> str | None:
    contexts = _comparison_contexts(lap)
    if not isinstance(contexts, dict):
        return None
    return _context_value_as_string(contexts.get(scope))


def _comparison_contexts(lap: dict) -> dict | None:
    contexts = lap.get("comparison_contexts")
    if isinstance(contexts, dict):
        return contexts
    summary = lap.get("summary")
    if isinstance(summary, dict) and isinstance(summary.get("comparison_contexts"), dict):
        return summary["comparison_contexts"]
    return None


def _track_key(lap: dict, contexts: dict | None) -> str:
    context_track = _context_component(contexts, "track")
    if context_track is not None:
        return context_track

    track_profile = _field_value(lap, _TRACK_FIELDS)
    if track_profile is not None:
        return track_profile

    track_signature = _field_value(lap, _TRACK_SIGNATURE_FIELDS)
    if track_signature is not None:
        return f"unknown_track:{track_signature}"

    session_id = _field_value(lap, ("session_id", "session_uuid"), default="unknown_session")
    return f"unknown_track:{session_id}"


def _current_track_profile_key(lap: dict) -> str | None:
    return _context_value_as_string(lap.get("track_profile_id"))


def _car_key(lap: dict, contexts: dict | None, scope: str) -> str:
    direct_key = _context_component(contexts, "car") or _field_value(lap, _CAR_FIELDS)
    if direct_key is not None:
        return direct_key
    if scope == "track_car_build":
        return (
            _context_scope_part(contexts, "track_car_build", 1)
            or _context_scope_part(contexts, "track_car", 1)
            or "unknown_car"
        )
    return (
        _context_scope_part(contexts, "track_car", 1)
        or _context_scope_part(contexts, "track_car_build", 1)
        or "unknown_car"
    )


def _build_key(lap: dict, contexts: dict | None) -> str:
    return (
        _context_component(contexts, "build")
        or _field_value(lap, _BUILD_FIELDS)
        or _context_scope_part(contexts, "track_car_build", 2)
        or "unknown_build"
    )


def _context_component(contexts: dict | None, key: str) -> str | None:
    if not isinstance(contexts, dict):
        return None
    return _context_value_as_string(contexts.get(key))


def _context_scope_part(contexts: dict | None, key: str, index: int) -> str | None:
    value = _context_component(contexts, key)
    if value is None:
        return None
    parts = value.split("|")
    if len(parts) <= index:
        return None
    return _context_value_as_string(parts[index])


def _context_value_as_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, dict):
        for key in ("context_key", "key", "id", "slug", "name"):
            parsed_value = _context_value_as_string(value.get(key))
            if parsed_value is not None:
                return parsed_value
        return None
    if isinstance(value, (list, tuple, set)):
        for candidate in value:
            parsed_value = _context_value_as_string(candidate)
            if parsed_value is not None:
                return parsed_value
        return None
    return str(value)


def _field_value(
    lap: dict,
    keys: tuple[str, ...],
    *,
    default: str | None = None,
) -> str | None:
    containers = [lap]
    summary = lap.get("summary")
    if isinstance(summary, dict):
        containers.append(summary)
    for container in list(containers):
        for nested_key in ("metadata", "context", "lap_context"):
            nested = container.get(nested_key)
            if isinstance(nested, dict):
                containers.append(nested)

    for container in containers:
        for key in keys:
            value = _context_value_as_string(container.get(key))
            if value is not None:
                return value
    return default


def _annotated_samples(samples: list[dict]) -> list[dict]:
    ordered_samples = _ordered_sample_copies(samples)
    if not ordered_samples:
        return []

    progress_values = _progress_values(ordered_samples)
    elapsed_values = _elapsed_values_ms(ordered_samples)
    annotated = []
    for index, sample in enumerate(ordered_samples):
        annotated_sample = dict(sample)
        annotated_sample["lap_progress"] = progress_values[index]
        annotated_sample["elapsed_ms"] = elapsed_values[index]
        annotated.append(annotated_sample)
    return annotated


def _ordered_sample_copies(samples: list[dict]) -> list[dict]:
    indexed_samples = [
        (index, sample)
        for index, sample in enumerate(samples)
        if isinstance(sample, dict)
    ]
    indexed_samples.sort(key=lambda item: (_sequence_sort_value(item[1], item[0]), item[0]))
    return [dict(sample) for _, sample in indexed_samples]


def _sequence_sort_value(sample: dict, fallback: int) -> tuple[int, float | int]:
    sequence = _finite_float(sample.get("sequence"))
    if sequence is None:
        return (1, fallback)
    return (0, sequence)


def _progress_values(samples: list[dict]) -> list[float]:
    explicit_progress = _explicit_progress_values(samples)
    if explicit_progress is not None:
        return explicit_progress

    distance_progress = _distance_progress_values(samples)
    if distance_progress is not None:
        return distance_progress

    elapsed_values = _elapsed_values_ms(samples)
    elapsed_progress = _normalized_values(elapsed_values)
    if elapsed_progress is not None:
        return elapsed_progress

    if len(samples) == 1:
        return [0.0]
    return [index / (len(samples) - 1) for index in range(len(samples))]


def _explicit_progress_values(samples: list[dict]) -> list[float] | None:
    for key in _PROGRESS_KEYS:
        values = [_finite_float(sample.get(key)) for sample in samples]
        if any(value is None for value in values):
            continue
        finite_values = [float(value) for value in values if value is not None]
        if not finite_values:
            continue
        if min(finite_values) >= 0.0 and max(finite_values) <= 1.0:
            return [_clamp_unit(value) for value in finite_values]
        normalized = _normalized_values(finite_values)
        if normalized is not None:
            return normalized
    return None


def _distance_progress_values(samples: list[dict]) -> list[float] | None:
    positions = [_position(sample) for sample in samples]
    if any(position is None for position in positions):
        return None

    distances = [0.0]
    total_distance = 0.0
    previous = positions[0]
    for position in positions[1:]:
        assert previous is not None
        assert position is not None
        total_distance += math.dist(previous, position)
        distances.append(total_distance)
        previous = position

    if total_distance <= 0.0:
        return None
    return [distance / total_distance for distance in distances]


def _position(sample: dict) -> tuple[float, float, float] | None:
    x = _finite_float(sample.get("x", sample.get("position_x")))
    y = _finite_float(sample.get("y", sample.get("position_y", 0.0)))
    z = _finite_float(sample.get("z", sample.get("position_z", 0.0)))
    if x is None or y is None or z is None:
        return None
    return (x, y, z)


def _elapsed_values_ms(samples: list[dict]) -> list[float | None]:
    direct_values = _values_for_first_available_key(samples, _DIRECT_ELAPSED_MS_KEYS)
    if direct_values is not None:
        return direct_values

    current_lap_values = _values_for_first_available_key(samples, ("current_lap",))
    if current_lap_values is not None and any(value > 0.0 for value in current_lap_values):
        return [value * 1000.0 for value in current_lap_values]

    timestamp_values = _values_for_first_available_key(samples, _TIMESTAMP_MS_KEYS)
    if timestamp_values is not None:
        return _offset_from_first(timestamp_values)

    race_time_values = _values_for_first_available_key(samples, ("current_race_time",))
    if race_time_values is not None:
        return [value * 1000.0 for value in _offset_from_first(race_time_values)]

    return [None for _ in samples]


def _values_for_first_available_key(
    samples: list[dict],
    keys: tuple[str, ...],
) -> list[float] | None:
    for key in keys:
        values = [_finite_float(sample.get(key)) for sample in samples]
        if any(value is None for value in values):
            continue
        return [float(value) for value in values if value is not None]
    return None


def _offset_from_first(values: list[float]) -> list[float]:
    if not values:
        return []
    first_value = values[0]
    return [value - first_value for value in values]


def _normalized_values(values: list[float | None]) -> list[float] | None:
    finite_values = [float(value) for value in values if value is not None]
    if len(finite_values) != len(values) or not finite_values:
        return None
    first_value = finite_values[0]
    last_value = finite_values[-1]
    span = last_value - first_value
    if span <= 0.0:
        return None
    return [_clamp_unit((value - first_value) / span) for value in finite_values]


def _select_sequence_range(
    samples: list[dict],
    *,
    start_sequence: int | None,
    end_sequence: int | None,
) -> list[dict]:
    if start_sequence is None and end_sequence is None:
        return list(samples)
    if start_sequence is not None and end_sequence is not None:
        lower_sequence = min(start_sequence, end_sequence)
        upper_sequence = max(start_sequence, end_sequence)
    else:
        lower_sequence = start_sequence
        upper_sequence = end_sequence

    selected = []
    for sample in samples:
        sequence = _finite_float(sample.get("sequence"))
        if sequence is None:
            continue
        if lower_sequence is not None and sequence < lower_sequence:
            continue
        if upper_sequence is not None and sequence > upper_sequence:
            continue
        selected.append(sample)
    return selected


def _selected_start_sequence(
    selected_samples: list[dict],
    requested_start_sequence: int | None,
) -> int | None:
    if requested_start_sequence is not None:
        return int(requested_start_sequence)
    if not selected_samples:
        return None
    return _int_or_none(selected_samples[0].get("sequence"))


def _selected_end_sequence(
    selected_samples: list[dict],
    requested_end_sequence: int | None,
) -> int | None:
    if requested_end_sequence is not None:
        return int(requested_end_sequence)
    if not selected_samples:
        return None
    return _int_or_none(selected_samples[-1].get("sequence"))


def _interpolate_reference_value(
    reference_samples: list[dict],
    progress: float | None,
    value_key: str,
) -> float | None:
    return _interpolate_reference_series(
        _reference_value_series(reference_samples, value_key),
        progress,
    )


def _reference_value_series(
    reference_samples: list[dict],
    value_key: str,
) -> tuple[list[float], list[tuple[float, float]]]:
    points = []
    for sample in reference_samples:
        sample_progress = _finite_float(sample.get("lap_progress"))
        sample_value = _finite_float(sample.get(value_key))
        if sample_progress is None or sample_value is None:
            continue
        points.append((sample_progress, sample_value))
    if not points:
        return [], []

    points.sort(key=lambda point: point[0])
    collapsed_points = _collapse_duplicate_progress(points)
    progress_values = [point[0] for point in collapsed_points]
    return progress_values, collapsed_points


def _interpolate_reference_series(
    reference_series: tuple[list[float], list[tuple[float, float]]],
    progress: float | None,
) -> float | None:
    progress = _finite_float(progress)
    if progress is None:
        return None

    progress_values, collapsed_points = reference_series
    if not collapsed_points:
        return None

    insertion_index = bisect.bisect_left(progress_values, progress)
    if insertion_index <= 0:
        return collapsed_points[0][1]
    if insertion_index >= len(collapsed_points):
        return collapsed_points[-1][1]

    previous_progress, previous_value = collapsed_points[insertion_index - 1]
    next_progress, next_value = collapsed_points[insertion_index]
    span = next_progress - previous_progress
    if span <= 0.0:
        return previous_value
    ratio = (progress - previous_progress) / span
    return previous_value + ratio * (next_value - previous_value)


def _collapse_duplicate_progress(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    collapsed: list[tuple[float, float]] = []
    for progress, value in points:
        if collapsed and math.isclose(progress, collapsed[-1][0], abs_tol=1e-12):
            collapsed[-1] = (progress, value)
        else:
            collapsed.append((progress, value))
    return collapsed


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _clamp_unit(value: float) -> float:
    return min(1.0, max(0.0, value))


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None
