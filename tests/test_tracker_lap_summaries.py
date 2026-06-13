import unittest

from telemetry_tracker.lap_summaries import compute_lap_summary


class LapSummaryTests(unittest.TestCase):
    def test_compute_lap_summary_aggregates_samples(self):
        samples = [
            {
                "game_timestamp_ms": 1_000,
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "speed_mps": 10.0,
                "throttle": 50,
                "brake": 0,
                "slip": 0.1,
            },
            {
                "game_timestamp_ms": 1_500,
                "x": 3.0,
                "y": 4.0,
                "z": 0.0,
                "speed_mps": 20.0,
                "throttle": 100,
                "brake": 80,
                "tire_slip_front_left": -0.2,
                "uncertainty": "teleport",
            },
            {
                "game_timestamp_ms": 2_000,
                "x": 3.0,
                "y": 4.0,
                "z": 12.0,
                "speed_mps": 15.0,
                "throttle": 0,
                "brake": 40,
                "TireCombinedSlipRearRight": 0.5,
            },
        ]

        summary = compute_lap_summary(samples)

        self.assertEqual(summary["sample_count"], 3)
        self.assertEqual(summary["packet_count"], 3)
        self.assertEqual(summary["lap_duration_ms"], 1_000)
        self.assertAlmostEqual(summary["distance_estimate_m"], 17.0)
        self.assertEqual(summary["top_speed_mps"], 20.0)
        self.assertEqual(summary["average_speed_mps"], 15.0)
        self.assertEqual(summary["max_throttle"], 100.0)
        self.assertEqual(summary["average_throttle"], 50.0)
        self.assertEqual(summary["max_brake"], 80.0)
        self.assertEqual(summary["average_brake"], 40.0)
        self.assertEqual(summary["max_slip"], 0.5)
        self.assertEqual(summary["uncertainty_count"], 1)

    def test_compute_lap_summary_reports_missing_metrics_as_none(self):
        samples = [
            {"game_timestamp_ms": 1_000},
            {"game_timestamp_ms": 1_100, "speed_mps": 12.0},
        ]

        summary = compute_lap_summary(samples)

        self.assertEqual(summary["sample_count"], 2)
        self.assertEqual(summary["lap_duration_ms"], 100)
        self.assertIsNone(summary["distance_estimate_m"])
        self.assertEqual(summary["top_speed_mps"], 12.0)
        self.assertEqual(summary["average_speed_mps"], 12.0)
        self.assertIsNone(summary["max_throttle"])
        self.assertIsNone(summary["average_throttle"])
        self.assertIsNone(summary["max_brake"])
        self.assertIsNone(summary["average_brake"])
        self.assertIsNone(summary["max_slip"])
        self.assertEqual(summary["uncertainty_count"], 0)

    def test_compute_lap_summary_handles_empty_samples(self):
        summary = compute_lap_summary([])

        self.assertEqual(summary["sample_count"], 0)
        self.assertEqual(summary["packet_count"], 0)
        self.assertIsNone(summary["lap_duration_ms"])
        self.assertEqual(summary["distance_estimate_m"], 0.0)
        self.assertIsNone(summary["top_speed_mps"])
        self.assertIsNone(summary["average_speed_mps"])
        self.assertIsNone(summary["max_throttle"])
        self.assertIsNone(summary["average_throttle"])
        self.assertIsNone(summary["max_brake"])
        self.assertIsNone(summary["average_brake"])
        self.assertIsNone(summary["max_slip"])
        self.assertEqual(summary["uncertainty_count"], 0)


if __name__ == "__main__":
    unittest.main()
