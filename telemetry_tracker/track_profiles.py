"""Track profile shape signatures and matching helpers."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telemetry_tracker.storage import TelemetryStore

_SIGNATURE_PREFIX = "shape-v1"
_MIN_VALID_POINTS = 20
_MIN_AXIS_SPAN = 1e-6
_MAX_BUCKETS = 512
_CLOSED_LAP_MAX_DISTANCE = 0.22
_MIN_NORMALIZED_PATH_LENGTH = 1.25
_MIN_BUCKET_FILL_RATIO = 0.75


def shape_signature(samples: list[dict], buckets: int = 64) -> str | None:
    """Return a deterministic normalized X/Z route signature.

    The heuristic is deliberately conservative for storage-time auto matching:
    a confident signature needs at least 20 valid X/Z points, a non-degenerate
    bounding box, enough progress buckets filled, enough normalized path
    length, and start/end points close together in normalized coordinates.  The
    last check rejects partial laps and free-roam traces that do not close back
    near their starting point.
    """

    if not isinstance(buckets, int) or buckets < 2 or buckets > _MAX_BUCKETS:
        return None

    points = _valid_xz_points(samples)
    if len(points) < _MIN_VALID_POINTS:
        return None

    xs = [point[0] for point in points]
    zs = [point[1] for point in points]
    min_x = min(xs)
    max_x = max(xs)
    min_z = min(zs)
    max_z = max(zs)
    span_x = max_x - min_x
    span_z = max_z - min_z
    if span_x < _MIN_AXIS_SPAN or span_z < _MIN_AXIS_SPAN:
        return None

    normalized = [((x - min_x) / span_x, (z - min_z) / span_z) for x, z in points]
    if _path_length(normalized) < _MIN_NORMALIZED_PATH_LENGTH:
        return None
    if _distance(normalized[0], normalized[-1]) > _CLOSED_LAP_MAX_DISTANCE:
        return None

    route = _route_progress_points(normalized)
    if route is None:
        return None
    nonzero_segment_count = len(route) - 1
    if nonzero_segment_count < math.ceil(buckets * _MIN_BUCKET_FILL_RATIO):
        return None

    resampled_buckets = [
        [round(point[0], 4), round(point[1], 4)]
        for point in _resample_route(route, buckets)
    ]

    payload = json.dumps(resampled_buckets, separators=(",", ":"))
    return f"{_SIGNATURE_PREFIX}:{buckets}:{payload}"


def signature_distance(left: str, right: str) -> float:
    """Return mean bucket distance, or infinity for invalid signatures."""

    left_points = _parse_signature(left)
    right_points = _parse_signature(right)
    if left_points is None or right_points is None:
        return math.inf
    if len(left_points) != len(right_points):
        return math.inf

    total_distance = sum(
        _distance(left_point, right_point)
        for left_point, right_point in zip(left_points, right_points, strict=True)
    )
    return total_distance / len(left_points)


def match_track_profile(
    store: TelemetryStore,
    samples: list[dict],
    max_distance: float = 0.18,
) -> dict | None:
    """Return the nearest stored profile whose shape signature is similar."""

    if max_distance < 0:
        return None

    signatures_by_bucket_count: dict[int, str | None] = {}
    best_profile: dict | None = None
    best_distance = math.inf

    for profile in store.track_profiles():
        stored_signature = profile.get("shape_signature")
        if not stored_signature:
            continue

        bucket_count = _signature_bucket_count(str(stored_signature))
        if bucket_count is None:
            continue

        if bucket_count not in signatures_by_bucket_count:
            signatures_by_bucket_count[bucket_count] = shape_signature(
                samples,
                buckets=bucket_count,
            )
        candidate_signature = signatures_by_bucket_count[bucket_count]
        if candidate_signature is None:
            continue

        distance = signature_distance(candidate_signature, str(stored_signature))
        if distance < best_distance:
            best_profile = profile
            best_distance = distance

    if best_profile is None or best_distance > max_distance:
        return None

    matched_profile = dict(best_profile)
    matched_profile["shape_match_distance"] = best_distance
    if max_distance == 0:
        matched_profile["match_confidence"] = 1.0 if best_distance == 0 else 0.0
    else:
        matched_profile["match_confidence"] = max(0.0, 1.0 - (best_distance / max_distance))
    return matched_profile


def assign_best_track_profile(
    store: TelemetryStore,
    session_id: str,
    lap_id: str,
    samples: list[dict],
) -> dict | None:
    """Match the samples and assign the best profile to the supplied lap."""

    match = match_track_profile(store, samples)
    if match is None:
        return None

    store.assign_track_profile(session_id, lap_id, str(match["id"]))
    return match


def _valid_xz_points(samples: list[dict]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for sample in samples:
        try:
            x = float(sample.get("x", sample.get("position_x")))
            z = float(sample.get("z", sample.get("position_z")))
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(x) and math.isfinite(z):
            points.append((x, z))
    return points


def _route_progress_points(
    points: list[tuple[float, float]],
) -> list[tuple[float, tuple[float, float]]] | None:
    cumulative_distance = 0.0
    route = [(0.0, points[0])]
    previous = points[0]
    for point in points[1:]:
        segment_distance = _distance(previous, point)
        if segment_distance > _MIN_AXIS_SPAN:
            cumulative_distance += segment_distance
            route.append((cumulative_distance, point))
        previous = point

    if cumulative_distance <= 0.0:
        return None

    return [
        (distance / cumulative_distance, point)
        for distance, point in route
    ]


def _resample_route(
    route: list[tuple[float, tuple[float, float]]],
    buckets: int,
) -> list[tuple[float, float]]:
    resampled_points: list[tuple[float, float]] = []
    route_index = 0
    for bucket_index in range(buckets):
        target_progress = bucket_index / (buckets - 1)
        while (
            route_index < len(route) - 2
            and route[route_index + 1][0] < target_progress
        ):
            route_index += 1

        start_progress, start_point = route[route_index]
        end_progress, end_point = route[min(route_index + 1, len(route) - 1)]
        if end_progress <= start_progress:
            resampled_points.append(start_point)
            continue

        segment_progress = (
            (target_progress - start_progress)
            / (end_progress - start_progress)
        )
        resampled_points.append(
            (
                start_point[0] + ((end_point[0] - start_point[0]) * segment_progress),
                start_point[1] + ((end_point[1] - start_point[1]) * segment_progress),
            )
        )
    return resampled_points


def _path_length(points: list[tuple[float, float]]) -> float:
    return sum(
        _distance(previous, current)
        for previous, current in zip(points, points[1:], strict=False)
    )


def _distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _signature_bucket_count(signature: str) -> int | None:
    if not isinstance(signature, str):
        return None
    parts = signature.split(":", 2)
    if len(parts) != 3 or parts[0] != _SIGNATURE_PREFIX:
        return None
    try:
        bucket_count = int(parts[1])
    except ValueError:
        return None
    if bucket_count < 2 or bucket_count > _MAX_BUCKETS:
        return None
    return bucket_count


def _parse_signature(signature: str) -> list[tuple[float, float]] | None:
    if not isinstance(signature, str):
        return None
    bucket_count = _signature_bucket_count(signature)
    if bucket_count is None:
        return None

    payload = signature.split(":", 2)[2]
    try:
        decoded = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, list) or len(decoded) != bucket_count:
        return None

    points: list[tuple[float, float]] = []
    for item in decoded:
        if not isinstance(item, list) or len(item) != 2:
            return None
        try:
            x = float(item[0])
            z = float(item[1])
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(x) or not math.isfinite(z):
            return None
        points.append((x, z))
    return points
