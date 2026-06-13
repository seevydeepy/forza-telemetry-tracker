import unittest

from telemetry_tracker.lap_quality import evaluate_auto_lap


def _samples(
    *,
    count: int = 121,
    lap_number: int = 1,
    current_start: float = 0.0,
    current_end: float = 60.0,
    race_start: float = 0.0,
    race_end: float = 60.0,
    distance_start: float = 0.0,
    distance_end: float = 3000.0,
    race_position: int = 1,
    route_guidance: int = 1,
    last_lap: float = 0.0,
    best_lap: float = 0.0,
):
    samples = []
    for index in range(count):
        fraction = index / (count - 1) if count > 1 else 0.0
        samples.append(
            {
                "sequence": index + 1,
                "received_at_ms": index * 16,
                "game_timestamp_ms": index * 16,
                "is_race_on": True,
                "lap_number": lap_number,
                "current_lap": current_start + ((current_end - current_start) * fraction),
                "current_race_time": race_start + ((race_end - race_start) * fraction),
                "x": fraction * 1000.0,
                "y": 0.0,
                "z": fraction * 1000.0,
                "speed_mps": 30.0,
                "throttle": 128,
                "brake": 0,
                "steer": 0,
                "gear": 4,
                "distance_traveled_m": distance_start + ((distance_end - distance_start) * fraction),
                "race_position": race_position,
                "normalized_driving_line": route_guidance,
                "normalized_ai_brake_difference": 0,
                "last_lap": last_lap,
                "best_lap": best_lap,
            }
        )
    return samples


class AutoLapQualityTests(unittest.TestCase):
    def test_accepts_completed_circuit_lap(self):
        verdict = evaluate_auto_lap(
            _samples(lap_number=3, current_end=72.345),
            reason="lap_boundary",
            boundary_confidence="game_field",
            uncertainty=None,
        )

        self.assertTrue(verdict.keep)
        self.assertEqual(verdict.completion_type, "circuit_lap")
        self.assertEqual(verdict.lap_time_ms, 72_345)

    def test_accepts_terminal_circuit_lap_with_stale_last_lap(self):
        verdict = evaluate_auto_lap(
            _samples(
                count=150,
                lap_number=2,
                current_end=105.543,
                race_start=87.106,
                race_end=192.649,
                distance_start=11905.7,
                distance_end=17858.9,
                last_lap=87.106,
                best_lap=87.106,
            ),
            reason="event_exit",
            boundary_confidence="heuristic",
            uncertainty="event_exit",
        )

        self.assertTrue(verdict.keep)
        self.assertEqual(verdict.completion_type, "terminal_circuit_lap")
        self.assertEqual(verdict.lap_time_ms, 105_543)

    def test_accepts_telemetry_gap_terminal_circuit_when_metrics_look_real(self):
        verdict = evaluate_auto_lap(
            _samples(
                count=150,
                lap_number=2,
                current_end=84.0,
                race_start=10.0,
                race_end=94.0,
                distance_start=1200.0,
                distance_end=5200.0,
            ),
            reason="telemetry_gap",
            boundary_confidence="uncertain",
            uncertainty="telemetry_gap",
        )

        self.assertTrue(verdict.keep)
        self.assertEqual(verdict.completion_type, "terminal_circuit_lap")
        self.assertEqual(verdict.lap_time_ms, 84_000)

    def test_rejects_telemetry_gap_lap_when_metrics_look_junk(self):
        verdict = evaluate_auto_lap(
            _samples(count=10, lap_number=2, current_end=4.0, distance_end=50.0),
            reason="telemetry_gap",
            boundary_confidence="uncertain",
            uncertainty="telemetry_gap",
        )

        self.assertFalse(verdict.keep)
        self.assertEqual(verdict.reason, "too_few_samples")


    def test_accepts_terminal_lap_with_rewind_or_reset_uncertainty_when_metrics_look_real(self):
        for uncertainty in ("rewind", "reset"):
            with self.subTest(uncertainty=uncertainty):
                verdict = evaluate_auto_lap(
                    _samples(
                        count=180,
                        lap_number=0,
                        current_start=0.0,
                        current_end=80.0,
                        race_start=0.0,
                        race_end=80.0,
                        distance_start=0.0,
                        distance_end=5500.0,
                        race_position=3,
                        route_guidance=1,
                    ),
                    reason="manual_stop",
                    boundary_confidence="heuristic",
                    uncertainty=uncertainty,
                )

                self.assertTrue(verdict.keep)
                self.assertEqual(verdict.completion_type, "sprint_event")
                self.assertEqual(verdict.lap_time_ms, 80_000)

    def test_accepts_completed_sprint_event(self):
        verdict = evaluate_auto_lap(
            _samples(
                count=150,
                lap_number=0,
                current_start=0.014,
                current_end=129.174,
                race_start=0.014,
                race_end=129.174,
                distance_start=-62.9,
                distance_end=5951.3,
                race_position=4,
                route_guidance=1,
            ),
            reason="lap_boundary",
            boundary_confidence="uncertain",
            uncertainty=None,
        )

        self.assertTrue(verdict.keep)
        self.assertEqual(verdict.completion_type, "sprint_event")
        self.assertEqual(verdict.lap_time_ms, 129_160)

    def test_accepts_track_matched_lap_even_when_generic_auto_rules_would_bin_it(self):
        verdict = evaluate_auto_lap(
            _samples(count=11, lap_number=0, current_end=10.0, race_end=10.0),
            reason="race_off",
            boundary_confidence="heuristic",
            uncertainty=None,
            track_profile_assigned=True,
        )

        self.assertTrue(verdict.keep)
        self.assertEqual(verdict.reason, "accepted_track_matched_lap")
        self.assertEqual(verdict.completion_type, "track_matched_lap")
        self.assertEqual(verdict.lap_time_ms, 10_000)

    def test_track_match_overrides_hard_reject_uncertainty_when_lap_time_exists(self):
        verdict = evaluate_auto_lap(
            _samples(count=11, lap_number=0, current_end=10.0, race_end=10.0),
            reason="telemetry_gap",
            boundary_confidence="uncertain",
            uncertainty="teleport",
            track_profile_assigned=True,
        )

        self.assertTrue(verdict.keep)
        self.assertEqual(verdict.reason, "accepted_track_matched_lap")
        self.assertEqual(verdict.lap_time_ms, 10_000)

    def test_track_matched_lap_still_rejects_when_no_lap_time_exists(self):
        verdict = evaluate_auto_lap(
            _samples(count=150, lap_number=0, current_start=10.0, current_end=10.0),
            reason="race_off",
            boundary_confidence="heuristic",
            uncertainty=None,
            track_profile_assigned=True,
        )

        self.assertFalse(verdict.keep)
        self.assertEqual(verdict.reason, "no_current_lap_progress")

    def test_rejects_event_exit_junk_with_no_lap_or_route_progress(self):
        verdict = evaluate_auto_lap(
            _samples(
                count=150,
                lap_number=0,
                current_start=0.0,
                current_end=0.0,
                race_start=10.0,
                race_end=130.0,
                distance_start=0.0,
                distance_end=0.0,
                race_position=0,
                route_guidance=0,
            ),
            reason="event_exit",
            boundary_confidence="heuristic",
            uncertainty="event_exit",
        )

        self.assertFalse(verdict.keep)
        self.assertEqual(verdict.reason, "no_current_lap_progress")

    def test_rejects_terminal_race_end_fragment(self):
        verdict = evaluate_auto_lap(
            _samples(
                count=335,
                lap_number=5,
                current_start=0.0,
                current_end=3.394,
                distance_start=1000.0,
                distance_end=1200.0,
            ),
            reason="event_exit",
            boundary_confidence="heuristic",
            uncertainty="event_exit",
        )

        self.assertFalse(verdict.keep)
        self.assertEqual(verdict.reason, "current_lap_too_short")

    def test_rejects_too_few_samples(self):
        verdict = evaluate_auto_lap(
            _samples(count=10, lap_number=1, current_end=60.0),
            reason="lap_boundary",
            boundary_confidence="game_field",
            uncertainty=None,
        )

        self.assertFalse(verdict.keep)
        self.assertEqual(verdict.reason, "too_few_samples")


if __name__ == "__main__":
    unittest.main()
