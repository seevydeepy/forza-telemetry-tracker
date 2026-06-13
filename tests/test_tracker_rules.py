import unittest

from telemetry_tracker.rules import load_default_ruleset


class TrackerRuleTests(unittest.TestCase):
    def test_default_ruleset_schema_and_overlay(self):
        ruleset = load_default_ruleset()

        self.assertEqual(ruleset.schema_version, 3)
        self.assertEqual(ruleset.default_overlay, "issues")

    def test_default_ruleset_uses_stable_rule_ids(self):
        ruleset = load_default_ruleset()
        rule_ids = [rule.rule_id for rule in ruleset.rules]

        self.assertEqual(
            rule_ids,
            [
                "slip.rear_combined.critical",
                "braking.instability.warning",
                "traction_exit.wheelspin.warning",
                "suspension.bottoming.critical",
                "limiter.engaged.info",
                "bogging.low_rpm.warning",
                "tires.temperature.hot.warning",
            ],
        )

    def test_default_ruleset_covers_expected_families(self):
        ruleset = load_default_ruleset()
        families = {rule.rule_id.split(".", 1)[0] for rule in ruleset.rules}

        self.assertEqual(
            families,
            {
                "slip",
                "braking",
                "traction_exit",
                "suspension",
                "limiter",
                "bogging",
                "tires",
            },
        )

    def test_each_rule_has_required_fields(self):
        ruleset = load_default_ruleset()

        for rule in ruleset.rules:
            with self.subTest(rule_id=rule.rule_id):
                self.assertIsInstance(rule.rule_id, str)
                self.assertTrue(rule.metric)
                self.assertIn(rule.severity, {"info", "warning", "critical"})
                self.assertIsNotNone(rule.threshold)
                self.assertTrue(rule.reason)

    def test_default_ruleset_matches_issue_overlay_catalog_values(self):
        ruleset = load_default_ruleset()
        rules_by_metric = {rule.metric: rule for rule in ruleset.rules}

        self.assertEqual(
            list(rules_by_metric),
            [
                "rear_combined_slip",
                "brake_pressure_and_slip",
                "throttle_and_rear_slip",
                "suspension_travel",
                "engine_rpm",
                "engine_rpm_and_throttle",
                "tire_temperature",
            ],
        )
        self.assertEqual(rules_by_metric["rear_combined_slip"].threshold, {"gte": 1.15})
        self.assertEqual(rules_by_metric["brake_pressure_and_slip"].threshold, {"brake_gte": 80, "slip_gte": 0.35})
        self.assertEqual(rules_by_metric["throttle_and_rear_slip"].threshold, {"throttle_gte": 90, "slip_gte": 0.3})
        self.assertEqual(rules_by_metric["suspension_travel"].threshold, {"compression_gte": 0.98})
        self.assertEqual(rules_by_metric["engine_rpm"].threshold, {"rpm_ratio_gte": 0.99, "duration_samples_gte": 3})
        self.assertEqual(rules_by_metric["engine_rpm_and_throttle"].threshold, {"throttle_gte": 70, "rpm_ratio_lte": 0.4})
        self.assertEqual(rules_by_metric["tire_temperature"].threshold, {"temperature_c_gte": 105})


if __name__ == "__main__":
    unittest.main()
