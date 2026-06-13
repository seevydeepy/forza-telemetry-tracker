"""Telemetry tracker lap analysis and issue marker generation."""

from __future__ import annotations

import hashlib
from typing import Any

from telemetry_tracker.collision_detection import generate_collision_markers
from telemetry_tracker.rules import RuleDefinition, RuleSet, load_default_ruleset
from telemetry_tracker.storage import TelemetryStore


_DEF_CONFIDENCE = 0.75
_RACE_CONTROL_ISSUES = {
    "rewind": {
        "metric": "race.rewind",
        "issue_kind": "Rewind",
        "reason": "The game rewind returned the car to an earlier route point; the lap was kept and the replaced route segment was flagged.",
    },
    "reset": {
        "metric": "race.reset",
        "issue_kind": "Reset",
        "reason": "The game reset the car to an earlier checkpoint-like route point while race timing continued; the lap was kept and the route discontinuity was flagged.",
    },
}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _rounded_display_value(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _max_abs(values: list[float | None]) -> float | None:
    present = [abs(value) for value in values if value is not None]
    if not present:
        return None
    return max(present)


def _max_positive(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return max(0.0, max(present))


def _rpm_ratio(sample: dict) -> float | None:
    current_rpm = _safe_float(sample.get("current_rpm"))
    engine_max_rpm = _safe_float(sample.get("engine_max_rpm"))
    if current_rpm is None or engine_max_rpm in (None, 0.0):
        return None
    return current_rpm / engine_max_rpm


def _rear_combined_slip(sample: dict) -> float | None:
    rear = _safe_float(sample.get("rear_combined_slip"))
    if rear is not None:
        return abs(rear)
    combined = _safe_float(sample.get("combined_slip"))
    return None if combined is None else abs(combined)


def _bottoming_value(sample: dict) -> float | None:
    return _max_positive(
        [
            _safe_float(sample.get("suspension_travel_front_left")),
            _safe_float(sample.get("suspension_travel_front_right")),
            _safe_float(sample.get("suspension_travel_rear_left")),
            _safe_float(sample.get("suspension_travel_rear_right")),
        ]
    )


def _tire_temp_value(sample: dict) -> float | None:
    return _max_abs(
        [
            _safe_float(sample.get("tire_temp_front_left")),
            _safe_float(sample.get("tire_temp_front_right")),
            _safe_float(sample.get("tire_temp_rear_left")),
            _safe_float(sample.get("tire_temp_rear_right")),
        ]
    )


def _match_detail(
    *,
    matched: bool,
    confidence: float = 0.0,
    issue_kind: str | None = None,
    actual_value: float | None = None,
    threshold_value: float | None = None,
    threshold_operator: str | None = None,
    value_label: str | None = None,
    value_unit: str | None = None,
) -> dict:
    return {
        "matched": matched,
        "confidence": float(confidence),
        "issue_kind": issue_kind,
        "actual_value": actual_value,
        "threshold_value": threshold_value,
        "threshold_operator": threshold_operator,
        "value_label": value_label,
        "value_unit": value_unit,
    }


def _no_match() -> dict:
    return _match_detail(matched=False)


def _sample_matches_rule(sample: dict, rule: RuleDefinition) -> dict:
    metric = rule.metric
    threshold = rule.threshold
    if metric == "rear_combined_slip":
        value = _rear_combined_slip(sample)
        limit = float(threshold["gte"])
        if value is None or value < limit:
            return _no_match()
        return _match_detail(
            matched=True,
            confidence=min(1.0, value / limit),
            issue_kind="Rear combined slip",
            actual_value=value,
            threshold_value=limit,
            threshold_operator="gte",
            value_label="Rear combined slip",
        )

    if metric == "brake_pressure_and_slip":
        brake = _safe_float(sample.get("brake"))
        raw_slip = _safe_float(sample.get("combined_slip"))
        slip = None if raw_slip is None else abs(raw_slip)
        brake_limit = float(threshold["brake_gte"])
        slip_limit = float(threshold["slip_gte"])
        if brake is None or slip is None or brake < brake_limit or slip < slip_limit:
            return _no_match()
        return _match_detail(
            matched=True,
            confidence=min(1.0, max(brake / 255.0, slip / slip_limit)),
            issue_kind="Braking instability",
            actual_value=slip,
            threshold_value=slip_limit,
            threshold_operator="gte",
            value_label="Combined slip",
        )

    if metric == "throttle_and_rear_slip":
        throttle = _safe_float(sample.get("throttle"))
        slip = _rear_combined_slip(sample)
        throttle_limit = float(threshold["throttle_gte"])
        slip_limit = float(threshold["slip_gte"])
        if throttle is None or slip is None or throttle < throttle_limit or slip < slip_limit:
            return _no_match()
        return _match_detail(
            matched=True,
            confidence=min(1.0, max(throttle / 255.0, slip / slip_limit)),
            issue_kind="Traction-limited exit",
            actual_value=slip,
            threshold_value=slip_limit,
            threshold_operator="gte",
            value_label="Rear slip",
        )

    if metric == "suspension_travel":
        value = _bottoming_value(sample)
        limit = float(threshold["compression_gte"])
        if value is None or value < limit:
            return _no_match()
        return _match_detail(
            matched=True,
            confidence=min(1.0, value / limit),
            issue_kind="Suspension bottoming",
            actual_value=value,
            threshold_value=limit,
            threshold_operator="gte",
            value_label="Suspension compression",
        )

    if metric == "engine_rpm":
        ratio = _rpm_ratio(sample)
        limit = float(threshold["rpm_ratio_gte"])
        if ratio is None or ratio < limit:
            return _no_match()
        return _match_detail(
            matched=True,
            confidence=min(1.0, ratio),
            issue_kind="Rev limiter",
            actual_value=ratio,
            threshold_value=limit,
            threshold_operator="gte",
            value_label="RPM ratio",
        )

    if metric == "engine_rpm_and_throttle":
        throttle = _safe_float(sample.get("throttle"))
        ratio = _rpm_ratio(sample)
        throttle_limit = float(threshold["throttle_gte"])
        ratio_limit = float(threshold["rpm_ratio_lte"])
        if throttle is None or ratio is None or throttle < throttle_limit or ratio > ratio_limit:
            return _no_match()
        return _match_detail(
            matched=True,
            confidence=min(1.0, throttle / 255.0),
            issue_kind="Low RPM bogging",
            actual_value=ratio,
            threshold_value=ratio_limit,
            threshold_operator="lte",
            value_label="RPM ratio",
        )

    if metric == "tire_temperature":
        value = _tire_temp_value(sample)
        limit = float(threshold["temperature_c_gte"])
        if value is None or value < limit:
            return _no_match()
        return _match_detail(
            matched=True,
            confidence=min(1.0, value / limit),
            issue_kind="Hot tire temperature",
            actual_value=value,
            threshold_value=limit,
            threshold_operator="gte",
            value_label="Tire temperature",
            value_unit="°C",
        )

    return _no_match()


def _detail_sort_key(item: tuple[int, dict]) -> tuple[float, float, int]:
    sequence, detail = item
    actual_value = detail.get("actual_value")
    threshold_value = detail.get("threshold_value")
    actual = float(actual_value) if actual_value is not None else 0.0
    threshold = float(threshold_value) if threshold_value is not None else 0.0
    operator = detail.get("threshold_operator")
    excess = threshold - actual if operator == "lte" else actual - threshold
    return (excess, float(detail.get("confidence") or 0.0), -int(sequence))


def _selected_detail(details: list[tuple[int, dict]]) -> tuple[int | None, dict | None]:
    if not details:
        return None, None
    return max(details, key=_detail_sort_key)


def _build_marker(
    rule: RuleDefinition,
    ruleset: RuleSet,
    start_sequence: int,
    end_sequence: int,
    confidence: float,
    details: list[tuple[int, dict]],
) -> dict:
    anchor_sequence, selected_detail = _selected_detail(details)
    selected_detail = selected_detail or {}
    return {
        "start_sequence": int(start_sequence),
        "end_sequence": int(end_sequence),
        "metric": rule.metric,
        "severity": rule.severity,
        "reason": rule.reason,
        "ruleset_version": int(ruleset.schema_version),
        "confidence": round(max(_DEF_CONFIDENCE, min(confidence, 1.0)), 3),
        "anchor_sequence": int(anchor_sequence) if anchor_sequence is not None else None,
        "issue_kind": selected_detail.get("issue_kind"),
        "actual_value": _rounded_display_value(selected_detail.get("actual_value")),
        "threshold_value": _rounded_display_value(selected_detail.get("threshold_value")),
        "threshold_operator": selected_detail.get("threshold_operator"),
        "value_label": selected_detail.get("value_label"),
        "value_unit": selected_detail.get("value_unit"),
    }


def _race_control_marker(sample: dict, uncertainty: str, ruleset: RuleSet) -> dict:
    issue = _RACE_CONTROL_ISSUES[uncertainty]
    sequence = int(sample.get("sequence", 0))
    return {
        "start_sequence": sequence,
        "end_sequence": sequence,
        "metric": issue["metric"],
        "severity": "info",
        "reason": issue["reason"],
        "ruleset_version": int(ruleset.schema_version),
        "confidence": 0.95,
        "anchor_sequence": sequence,
        "issue_kind": issue["issue_kind"],
        "actual_value": None,
        "threshold_value": None,
        "threshold_operator": None,
        "value_label": None,
        "value_unit": None,
    }


def _generate_race_control_markers(samples: list[dict], ruleset: RuleSet) -> list[dict]:
    markers: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for sample in samples:
        uncertainty = str(sample.get("uncertainty") or "").strip().lower()
        if uncertainty not in _RACE_CONTROL_ISSUES:
            continue
        sequence = int(sample.get("sequence", 0))
        key = (uncertainty, sequence)
        if key in seen:
            continue
        seen.add(key)
        markers.append(_race_control_marker(sample, uncertainty, ruleset))
    return markers


def _summarize_bottoming_events(samples: list[dict], threshold: float = 0.98) -> int:
    events = 0
    in_event = False
    previous_sequence: int | None = None
    for sample in samples:
        sequence = int(sample.get("sequence", 0))
        active = (_bottoming_value(sample) or 0.0) >= threshold
        contiguous = previous_sequence is not None and sequence == previous_sequence + 1
        if active and (not in_event or not contiguous):
            events += 1
            in_event = True
        elif not active:
            in_event = False
        previous_sequence = sequence
    return events


def generate_issue_markers(samples: list[dict], ruleset: RuleSet) -> list[dict]:
    markers: list[dict] = []
    ordered_samples = sorted(samples, key=lambda sample: (int(sample.get("sequence", 0)),))
    for rule in ruleset.rules:
        start_sequence: int | None = None
        previous_sequence: int | None = None
        confidences: list[float] = []
        details: list[tuple[int, dict]] = []
        matched_count = 0
        minimum_duration = int(rule.threshold.get("duration_samples_gte", 1))

        for sample in ordered_samples:
            sequence = int(sample.get("sequence", 0))
            detail = _sample_matches_rule(sample, rule)
            matched = bool(detail["matched"])
            confidence = float(detail.get("confidence") or 0.0)
            contiguous = previous_sequence is not None and sequence == previous_sequence + 1
            if matched:
                if start_sequence is None or not contiguous:
                    if start_sequence is not None and matched_count >= minimum_duration:
                        markers.append(
                            _build_marker(
                                rule,
                                ruleset,
                                start_sequence,
                                previous_sequence or start_sequence,
                                max(confidences, default=1.0),
                                details,
                            )
                        )
                    start_sequence = sequence
                    confidences = [confidence]
                    details = [(sequence, detail)]
                    matched_count = 1
                else:
                    confidences.append(confidence)
                    details.append((sequence, detail))
                    matched_count += 1
                previous_sequence = sequence
                continue

            if start_sequence is not None and matched_count >= minimum_duration:
                markers.append(
                    _build_marker(
                        rule,
                        ruleset,
                        start_sequence,
                        previous_sequence or start_sequence,
                        max(confidences, default=1.0),
                        details,
                    )
                )
            start_sequence = None
            previous_sequence = sequence
            confidences = []
            details = []
            matched_count = 0

        if start_sequence is not None and matched_count >= minimum_duration:
            markers.append(
                _build_marker(
                    rule,
                    ruleset,
                    start_sequence,
                    previous_sequence or start_sequence,
                    max(confidences, default=1.0),
                    details,
                )
            )
    markers.extend(generate_collision_markers(ordered_samples, ruleset.schema_version))
    markers.extend(_generate_race_control_markers(ordered_samples, ruleset))
    return sorted(
        markers,
        key=lambda marker: (
            int(marker.get("start_sequence", 0)),
            int(marker.get("end_sequence", 0)),
            str(marker.get("metric", "")),
        ),
    )


def summarize_samples(samples: list[dict]) -> dict:
    packet_count = len(samples)
    if not samples:
        return {
            "packet_count": 0,
            "top_speed_mps": 0.0,
            "average_speed_mps": 0.0,
            "peak_combined_slip": 0.0,
            "limiter_samples": 0,
            "bottoming_events": 0,
        }

    speeds = [float(sample.get("speed_mps", 0.0) or 0.0) for sample in samples]
    combined_slips = [abs(float(sample.get("combined_slip", 0.0) or 0.0)) for sample in samples]
    limiter_samples = sum(1 for sample in samples if (_rpm_ratio(sample) or 0.0) >= 0.99)
    return {
        "packet_count": packet_count,
        "top_speed_mps": round(max(speeds), 3),
        "average_speed_mps": round(sum(speeds) / packet_count, 3),
        "peak_combined_slip": round(max(combined_slips, default=0.0), 4),
        "limiter_samples": limiter_samples,
        "bottoming_events": _summarize_bottoming_events(samples),
    }


def summarize_section(samples: list[dict], start_sequence: int, end_sequence: int) -> dict:
    section_samples = [
        sample
        for sample in samples
        if int(sample.get("sequence", 0)) >= int(start_sequence)
        and int(sample.get("sequence", 0)) <= int(end_sequence)
    ]
    summary = summarize_samples(section_samples)
    summary["start_sequence"] = int(start_sequence)
    summary["end_sequence"] = int(end_sequence)
    return summary


def _marker_id(session_id: str, lap_id: str | None, marker: dict) -> str:
    raw = "|".join(
        [
            session_id,
            lap_id or "session",
            marker["metric"],
            str(marker["start_sequence"]),
            str(marker["end_sequence"]),
            str(marker["ruleset_version"]),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def analyze_lap(store: TelemetryStore, session_id: str, lap_id: str | None) -> dict:
    with store.connect() as con:
        if lap_id is None:
            row = con.execute(
                """
                SELECT MIN(sequence) AS start_sequence, MAX(sequence) AS end_sequence
                FROM lap_samples
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        else:
            row = con.execute(
                """
                SELECT MIN(sequence) AS start_sequence, MAX(sequence) AS end_sequence
                FROM lap_samples
                WHERE session_id = ? AND lap_id = ?
                """,
                (session_id, lap_id),
            ).fetchone()

    start_sequence = row["start_sequence"] if row is not None else None
    end_sequence = row["end_sequence"] if row is not None else None
    ruleset = load_default_ruleset()
    if start_sequence is None or end_sequence is None:
        summary = summarize_samples([])
        if lap_id is not None:
            store.replace_analysis_results(
                session_id=session_id,
                lap_id=lap_id,
                summary=summary,
                markers=[],
            )
        else:
            store.replace_analysis_results(
                session_id=session_id,
                lap_id=None,
                summary=None,
                markers=[],
            )
        return {
            "session_id": session_id,
            "lap_id": lap_id,
            "summary": summary,
            "markers": [],
            "ruleset_version": ruleset.schema_version,
        }

    samples = store.samples_for_range(
        session_id,
        start_sequence=int(start_sequence),
        end_sequence=int(end_sequence),
        lap_id=lap_id,
    )
    markers = generate_issue_markers(samples, ruleset)
    enriched_markers = [
        {
            **marker,
            "id": _marker_id(session_id, lap_id, marker),
            "session_id": session_id,
            "lap_id": lap_id,
        }
        for marker in markers
    ]
    summary = summarize_samples(samples)
    summary["start_sequence"] = int(start_sequence)
    summary["end_sequence"] = int(end_sequence)
    store.replace_analysis_results(
        session_id=session_id,
        lap_id=lap_id,
        summary=summary if lap_id is not None else None,
        markers=enriched_markers,
    )
    return {
        "session_id": session_id,
        "lap_id": lap_id,
        "summary": summary,
        "markers": enriched_markers,
        "ruleset_version": ruleset.schema_version,
    }
