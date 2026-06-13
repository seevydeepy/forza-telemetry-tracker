"""Versioned built-in telemetry tracker rule defaults."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Severity = Literal["info", "warning", "critical"]


@dataclass(frozen=True)
class RuleDefinition:
    """Plain rule definition for issue detection."""

    rule_id: str
    metric: str
    severity: Severity
    threshold: dict[str, Any]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "metric": self.metric,
            "severity": self.severity,
            "threshold": dict(self.threshold),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RuleSet:
    """Container for a versioned default rule collection."""

    schema_version: int
    default_overlay: str
    rules: tuple[RuleDefinition, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "default_overlay": self.default_overlay,
            "rules": [rule.to_dict() for rule in self.rules],
        }


def load_default_ruleset() -> RuleSet:
    """Return the in-code default ruleset for milestone 3."""

    rules = (
        RuleDefinition(
            rule_id="slip.rear_combined.critical",
            metric="rear_combined_slip",
            severity="critical",
            threshold={"gte": 1.15},
            reason="Rear combined slip is so high that the car is likely sliding hard.",
        ),
        RuleDefinition(
            rule_id="braking.instability.warning",
            metric="brake_pressure_and_slip",
            severity="warning",
            threshold={"brake_gte": 80, "slip_gte": 0.35},
            reason="Strong braking with rising slip suggests the car is becoming unstable.",
        ),
        RuleDefinition(
            rule_id="traction_exit.wheelspin.warning",
            metric="throttle_and_rear_slip",
            severity="warning",
            threshold={"throttle_gte": 90, "slip_gte": 0.3},
            reason="High throttle with elevated rear slip indicates a traction-limited exit.",
        ),
        RuleDefinition(
            rule_id="suspension.bottoming.critical",
            metric="suspension_travel",
            severity="critical",
            threshold={"compression_gte": 0.98},
            reason="Suspension travel is near full compression and may be bottoming out.",
        ),
        RuleDefinition(
            rule_id="limiter.engaged.info",
            metric="engine_rpm",
            severity="info",
            threshold={"rpm_ratio_gte": 0.99, "duration_samples_gte": 3},
            reason="The engine is spending time at or near the rev limiter.",
        ),
        RuleDefinition(
            rule_id="bogging.low_rpm.warning",
            metric="engine_rpm_and_throttle",
            severity="warning",
            threshold={"throttle_gte": 70, "rpm_ratio_lte": 0.4},
            reason="The engine is on throttle but not pulling strongly, suggesting bogging.",
        ),
        RuleDefinition(
            rule_id="tires.temperature.hot.warning",
            metric="tire_temperature",
            severity="warning",
            threshold={"temperature_c_gte": 105},
            reason="Tire temperatures are hot enough to suggest degradation risk.",
        ),
    )
    return RuleSet(schema_version=3, default_overlay="issues", rules=rules)
