"""Confidence-based canonical track matching for telemetry laps."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telemetry_tracker.storage import TelemetryStore

MATCHER_VERSION = "track-match-v1"
HIGH_CONFIDENCE_THRESHOLD = 0.90
HIGH_CONFIDENCE_MARGIN = 0.15
MIN_SAMPLE_POINTS = 8
START_NEAR_METERS = 80.0
FINISH_NEAR_METERS = 100.0
LOCATOR_NEAR_METERS = 140.0
BOUNDS_PADDING_METERS = 220.0
MAX_CANDIDATES = 8
MIN_AUTO_ASSIGN_LOCATOR_HIT_RATIO = 0.55
MIN_AUTO_ASSIGN_BOUNDS_SCORE = 0.75
MAX_SCORING_POINTS = 600


@dataclass(frozen=True)
class _Point:
    x: float
    z: float


def match_lap_track(
    store: TelemetryStore,
    lap_id: str,
    *,
    auto_assign: bool = True,
    high_confidence_threshold: float = HIGH_CONFIDENCE_THRESHOLD,
    high_confidence_margin: float = HIGH_CONFIDENCE_MARGIN,
) -> dict:
    """Match a stored lap to canonical FH6 track data and maybe auto-assign it."""

    lap = store.lap(lap_id)
    if lap is None:
        raise ValueError(f"unknown lap_id: {lap_id}")
    session_id = str(lap["session_id"])
    samples = store.samples_for_lap(lap_id)
    candidates = match_samples_to_tracks(store, samples)
    _attach_catalog_profile_ids(store, candidates)

    assignment = _auto_assignment_decision(
        store,
        lap,
        candidates,
        enabled=auto_assign,
        threshold=high_confidence_threshold,
        margin=high_confidence_margin,
    )
    assigned_profile_id = assignment.get("track_profile_id") if assignment.get("assigned") else None
    store.replace_track_match_candidates(
        lap_id=lap_id,
        session_id=session_id,
        matcher_version=MATCHER_VERSION,
        candidates=candidates,
        assigned_track_profile_id=assigned_profile_id,
    )
    return {
        "lap_id": lap_id,
        "session_id": session_id,
        "matcher_version": MATCHER_VERSION,
        "candidates": candidates,
        "best_candidate": candidates[0] if candidates else None,
        "assignment": assignment,
    }


def match_samples_to_tracks(store: TelemetryStore, samples: list[dict]) -> list[dict]:
    """Return ranked canonical game-track candidates for the supplied samples."""

    points = _valid_points(samples)
    if len(points) < MIN_SAMPLE_POINTS:
        return []
    scoring_points = _scoring_points(points)

    tracks = store.game_tracks()
    locators = store.game_track_locators()
    locators_by_route_id: dict[int, list[dict]] = {}
    for locator in locators:
        route_id = _optional_int(locator.get("route_id"))
        if route_id is None:
            continue
        locators_by_route_id.setdefault(route_id, []).append(locator)

    candidates: list[dict] = []
    for track in tracks:
        route_id = _optional_int(track.get("route_id"))
        if route_id is None:
            continue
        route_locators = locators_by_route_id.get(route_id, [])
        if not route_locators:
            continue
        if not _candidate_bounds_may_overlap(points, route_locators, BOUNDS_PADDING_METERS):
            continue
        candidate = _score_track_candidate(track, route_locators, scoring_points)
        if candidate["confidence"] <= 0.0:
            continue
        candidates.append(candidate)

    candidates.sort(
        key=lambda candidate: (
            -float(candidate["confidence"]),
            str(candidate.get("display_name") or ""),
            str(candidate.get("track_key") or ""),
        )
    )
    return candidates[:MAX_CANDIDATES]


def _attach_catalog_profile_ids(store: TelemetryStore, candidates: list[dict]) -> None:
    profile_ids_by_track_key = store.game_track_profile_ids_by_track_key(
        str(candidate["track_key"])
        for candidate in candidates
        if candidate.get("track_key") and not candidate.get("track_profile_id")
    )
    for candidate in candidates:
        if candidate.get("track_profile_id"):
            continue
        track_key = candidate.get("track_key")
        if track_key:
            candidate["track_profile_id"] = profile_ids_by_track_key.get(str(track_key))


def _auto_assignment_decision(
    store: TelemetryStore,
    lap: dict,
    candidates: list[dict],
    *,
    enabled: bool,
    threshold: float,
    margin: float,
) -> dict:
    if not enabled:
        return {"assigned": False, "reason": "auto_assign_disabled"}
    if lap.get("track_profile_id"):
        return {
            "assigned": False,
            "reason": "existing_track_profile_id",
            "track_profile_id": lap.get("track_profile_id"),
        }
    if not candidates:
        return {"assigned": False, "reason": "no_candidates"}

    best = candidates[0]
    second_confidence = float(candidates[1]["confidence"]) if len(candidates) > 1 else 0.0
    best_confidence = float(best["confidence"])
    best_margin = best_confidence - second_confidence
    if best_confidence < threshold:
        return {
            "assigned": False,
            "reason": "confidence_below_threshold",
            "confidence": best_confidence,
            "threshold": threshold,
        }
    score_components = best.get("score_components") or {}
    locator_hit_ratio = float(score_components.get("locator_hit_ratio") or 0.0)
    bounds_score = float(score_components.get("bounds_score") or 0.0)
    if locator_hit_ratio < MIN_AUTO_ASSIGN_LOCATOR_HIT_RATIO:
        return {
            "assigned": False,
            "reason": "route_locator_coverage_too_low",
            "confidence": best_confidence,
            "locator_hit_ratio": locator_hit_ratio,
            "required_locator_hit_ratio": MIN_AUTO_ASSIGN_LOCATOR_HIT_RATIO,
        }
    if bounds_score < MIN_AUTO_ASSIGN_BOUNDS_SCORE:
        return {
            "assigned": False,
            "reason": "route_bounds_overlap_too_low",
            "confidence": best_confidence,
            "bounds_score": bounds_score,
            "required_bounds_score": MIN_AUTO_ASSIGN_BOUNDS_SCORE,
        }
    if best_margin < margin:
        return {
            "assigned": False,
            "reason": "confidence_margin_too_small",
            "confidence": best_confidence,
            "second_confidence": second_confidence,
            "margin": best_margin,
            "required_margin": margin,
        }
    track_key = best.get("track_key")
    if not track_key:
        return {"assigned": False, "reason": "candidate_has_no_track_key"}

    profile = store.ensure_game_track_profile(str(track_key))
    store.assign_track_profile(str(lap["session_id"]), str(lap["id"]), str(profile["id"]))
    best["track_profile_id"] = profile["id"]
    best["is_auto_assignable"] = True
    return {
        "assigned": True,
        "reason": "high_confidence_match",
        "track_profile_id": profile["id"],
        "track_key": track_key,
        "confidence": best_confidence,
        "margin": best_margin,
    }


def _score_track_candidate(track: dict, locators: list[dict], points: list[_Point]) -> dict:
    start_locators = [locator for locator in locators if _locator_kind(locator) in {"start_line", "challenge_start"}]
    finish_locators = [locator for locator in locators if _locator_kind(locator) in {"finish_line", "challenge_end"}]

    start_distance = _nearest_distance(points[0], start_locators or locators)
    finish_distance = _nearest_distance(points[-1], finish_locators or locators)
    start_score = _distance_score(start_distance, START_NEAR_METERS)
    finish_score = _distance_score(finish_distance, FINISH_NEAR_METERS)
    locator_hit_ratio = _locator_hit_ratio(locators, points, LOCATOR_NEAR_METERS)
    sample_near_ratio = _sample_near_ratio(points, locators, LOCATOR_NEAR_METERS)
    bounds_score = _bounds_score(points, locators, BOUNDS_PADDING_METERS)

    confidence = (
        (start_score * 0.32)
        + (finish_score * 0.28)
        + (locator_hit_ratio * 0.20)
        + (sample_near_ratio * 0.10)
        + (bounds_score * 0.10)
    )
    confidence = max(0.0, min(1.0, confidence))

    reasons = [
        f"start distance {start_distance:.1f}m",
        f"finish distance {finish_distance:.1f}m",
        f"locator hit ratio {locator_hit_ratio:.2f}",
        f"sample near-locator ratio {sample_near_ratio:.2f}",
        f"bounds overlap score {bounds_score:.2f}",
    ]
    return {
        "candidate_kind": "game_track",
        "track_key": track.get("track_key"),
        "route_id": track.get("route_id"),
        "display_name": track.get("display_name") or track.get("short_display_name"),
        "confidence": round(confidence, 4),
        "is_auto_assignable": False,
        "score_components": {
            "start_score": round(start_score, 4),
            "finish_score": round(finish_score, 4),
            "locator_hit_ratio": round(locator_hit_ratio, 4),
            "sample_near_ratio": round(sample_near_ratio, 4),
            "bounds_score": round(bounds_score, 4),
            "start_distance_m": round(start_distance, 3),
            "finish_distance_m": round(finish_distance, 3),
            "locator_count": len(locators),
            "sample_count": len(points),
        },
        "reasons": reasons,
    }


def _valid_points(samples: list[dict]) -> list[_Point]:
    points: list[_Point] = []
    for sample in samples:
        try:
            x = float(sample.get("x", sample.get("position_x")))
            z = float(sample.get("z", sample.get("position_z")))
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(x) and math.isfinite(z):
            points.append(_Point(x, z))
    return points


def _scoring_points(points: list[_Point]) -> list[_Point]:
    if len(points) <= MAX_SCORING_POINTS:
        return points

    last_index = len(points) - 1
    selected: list[_Point] = []
    selected_indexes: set[int] = set()
    for index in range(MAX_SCORING_POINTS):
        source_index = round(index * last_index / (MAX_SCORING_POINTS - 1))
        if source_index in selected_indexes:
            continue
        selected_indexes.add(source_index)
        selected.append(points[source_index])
    return selected


def _locator_kind(locator: dict) -> str:
    return str(locator.get("locator_kind") or "").lower()


def _locator_point(locator: dict) -> _Point | None:
    try:
        x = float(locator["x"])
        z = float(locator["z"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(x) or not math.isfinite(z):
        return None
    return _Point(x, z)


def _distance(left: _Point, right: _Point) -> float:
    return math.hypot(left.x - right.x, left.z - right.z)


def _nearest_distance(point: _Point, locators: list[dict]) -> float:
    distances = [
        _distance(point, locator_point)
        for locator in locators
        if (locator_point := _locator_point(locator)) is not None
    ]
    return min(distances) if distances else math.inf


def _distance_score(distance: float, limit: float) -> float:
    if not math.isfinite(distance):
        return 0.0
    if distance <= 0.0:
        return 1.0
    return max(0.0, 1.0 - (distance / limit))


def _locator_hit_ratio(locators: list[dict], points: list[_Point], limit: float) -> float:
    locator_points = [point for locator in locators if (point := _locator_point(locator)) is not None]
    if not locator_points:
        return 0.0
    hit_count = 0
    for locator_point in locator_points:
        if min(_distance(locator_point, point) for point in points) <= limit:
            hit_count += 1
    return hit_count / len(locator_points)


def _sample_near_ratio(points: list[_Point], locators: list[dict], limit: float) -> float:
    locator_points = [point for locator in locators if (point := _locator_point(locator)) is not None]
    if not locator_points or not points:
        return 0.0
    near_count = 0
    for point in points:
        if min(_distance(point, locator_point) for locator_point in locator_points) <= limit:
            near_count += 1
    return near_count / len(points)


def _candidate_bounds_may_overlap(points: list[_Point], locators: list[dict], padding: float) -> bool:
    locator_points = [point for locator in locators if (point := _locator_point(locator)) is not None]
    if not locator_points or not points:
        return False
    point_min_x = min(point.x for point in points)
    point_max_x = max(point.x for point in points)
    point_min_z = min(point.z for point in points)
    point_max_z = max(point.z for point in points)
    locator_min_x = min(point.x for point in locator_points) - padding
    locator_max_x = max(point.x for point in locator_points) + padding
    locator_min_z = min(point.z for point in locator_points) - padding
    locator_max_z = max(point.z for point in locator_points) + padding
    return not (
        point_max_x < locator_min_x
        or point_min_x > locator_max_x
        or point_max_z < locator_min_z
        or point_min_z > locator_max_z
    )


def _bounds_score(points: list[_Point], locators: list[dict], padding: float) -> float:
    locator_points = [point for locator in locators if (point := _locator_point(locator)) is not None]
    if not locator_points or not points:
        return 0.0
    min_x = min(point.x for point in locator_points) - padding
    max_x = max(point.x for point in locator_points) + padding
    min_z = min(point.z for point in locator_points) - padding
    max_z = max(point.z for point in locator_points) + padding
    inside_count = sum(1 for point in points if min_x <= point.x <= max_x and min_z <= point.z <= max_z)
    return inside_count / len(points)


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None
