import unittest

from telemetry_tracker.lap_detection import (
    MEANINGFUL_RACE_TIME_SECONDS,
    TELEPORT_DISTANCE_METERS,
    LapDetector,
)
from telemetry_tracker.packet_bridge import decode_packet, encode_packet_for_test


def _packet(**overrides) -> dict:
    values = {
        "IsRaceOn": 1,
        "TimestampMS": 1000,
        "PositionX": 0.0,
        "PositionY": 0.0,
        "PositionZ": 0.0,
        "Speed": 20.0,
        "CurrentLap": 0.0,
        "CurrentRaceTime": 0.0,
        "LapNumber": 0,
        "LastLap": 0.0,
        "BestLap": 0.0,
    }
    values.update(overrides)
    return decode_packet(encode_packet_for_test(values))


def _lap_packet(lap_number: int = 1, **overrides) -> dict:
    values = {
        "LapNumber": lap_number,
        "CurrentLap": 1.0,
        "CurrentRaceTime": 1.0,
        "LastLap": 0.0,
        "IsRaceOn": 1,
    }
    values.update(overrides)
    return _packet(**values)


class LapDetectorTests(unittest.TestCase):
    def test_session_starts_when_first_recording_packet_arrives(self):
        detector = LapDetector()

        result = detector.observe(_packet(), received_at_ms=1000)

        self.assertEqual(result["session_action"], "start")
        self.assertEqual(result["session_id"], 1)
        self.assertTrue(result["session_active"])
        self.assertEqual(result["received_at_ms"], 1000)

    def test_lap_zero_and_one_packets_create_active_lap_with_game_fields(self):
        for lap_number in (0, 1):
            with self.subTest(lap_number=lap_number):
                detector = LapDetector()

                result = detector.observe(
                    _lap_packet(
                        lap_number,
                        CurrentLap=0.5,
                        CurrentRaceTime=0.5,
                    ),
                    received_at_ms=1000,
                )

                self.assertEqual(result["session_action"], "start")
                self.assertEqual(result["lap_action"], "start")
                self.assertEqual(result["lap_number"], lap_number)
                self.assertEqual(result["lap_id"], 1)
                self.assertEqual(result["active_lap_id"], 1)
                self.assertEqual(result["boundary_confidence"], "game_field")
                self.assertIsNone(result["uncertainty"])

    def test_increasing_lap_number_finalizes_previous_lap_and_opens_new_lap(self):
        detector = LapDetector()
        first = detector.observe(
            _lap_packet(0, CurrentLap=12.0, CurrentRaceTime=12.0),
            received_at_ms=1000,
        )

        result = detector.observe(
            _lap_packet(1, CurrentLap=0.1, CurrentRaceTime=62.0),
            received_at_ms=2000,
        )

        self.assertEqual(first["lap_id"], 1)
        self.assertEqual(result["session_action"], "none")
        self.assertEqual(result["lap_action"], "finalize_and_start")
        self.assertEqual(result["previous_lap_number"], 0)
        self.assertEqual(result["lap_number"], 1)
        self.assertEqual(result["finalized_lap_id"], 1)
        self.assertEqual(result["lap_id"], 2)
        self.assertEqual(result["active_lap_id"], 2)
        self.assertEqual(result["boundary_confidence"], "game_field")
        self.assertIsNone(result["uncertainty"])

    def test_positive_last_lap_starts_next_lap_when_current_fields_are_active(self):
        detector = LapDetector()
        started = detector.observe(
            _lap_packet(1, CurrentLap=22.0, CurrentRaceTime=22.0),
            received_at_ms=1000,
        )

        result = detector.observe(
            _lap_packet(1, LastLap=61.234, CurrentLap=0.2, CurrentRaceTime=61.5),
            received_at_ms=2000,
        )

        self.assertEqual(started["lap_id"], 1)
        self.assertEqual(result["lap_action"], "finalize_and_start")
        self.assertEqual(result["lap_number"], 1)
        self.assertEqual(result["finalized_lap_id"], 1)
        self.assertEqual(result["lap_id"], 2)
        self.assertEqual(result["active_lap_id"], 2)
        self.assertAlmostEqual(result["last_lap"], 61.234, places=3)
        self.assertEqual(result["boundary_confidence"], "game_field")
        self.assertIsNone(result["uncertainty"])

    def test_stale_last_lap_and_best_lap_only_packets_do_not_start_laps(self):
        for field_name in ("LastLap", "BestLap"):
            with self.subTest(field_name=field_name):
                detector = LapDetector()

                result = detector.observe(
                    _packet(
                        CurrentLap=0.0,
                        CurrentRaceTime=0.0,
                        LapNumber=0,
                        **{field_name: 61.234},
                    ),
                    received_at_ms=1000,
                )

                self.assertEqual(result["session_action"], "start")
                self.assertEqual(result["lap_action"], "none")
                self.assertIsNone(result["lap_id"])
                self.assertIsNone(result["active_lap_id"])
                self.assertIsNone(result["lap_number"])
                self.assertEqual(result["uncertainty"], "no_lap_signal")
                self.assertEqual(result["boundary_confidence"], "uncertain")

    def test_repeated_stale_last_lap_after_finalize_does_not_create_new_lap(self):
        detector = LapDetector()
        detector.observe(
            _lap_packet(0, CurrentLap=2.0, CurrentRaceTime=2.0),
            received_at_ms=1000,
        )
        finalized = detector.observe(
            _packet(
                LastLap=30.0,
                CurrentLap=0.0,
                CurrentRaceTime=0.0,
                LapNumber=0,
            ),
            received_at_ms=2000,
        )

        repeated = detector.observe(
            _packet(
                LastLap=30.0,
                CurrentLap=0.0,
                CurrentRaceTime=0.0,
                LapNumber=0,
            ),
            received_at_ms=3000,
        )

        self.assertEqual(finalized["lap_action"], "finalize")
        self.assertEqual(finalized["finalized_lap_id"], 1)
        self.assertIsNone(finalized["lap_id"])
        self.assertIsNone(finalized["active_lap_id"])
        self.assertEqual(repeated["lap_action"], "none")
        self.assertIsNone(repeated["lap_id"])
        self.assertIsNone(repeated["active_lap_id"])
        self.assertIsNone(repeated["lap_number"])
        self.assertEqual(repeated["uncertainty"], "no_lap_signal")

    def test_free_roam_no_lap_packets_are_retained_without_lap_id(self):
        detector = LapDetector()

        result = detector.observe(
            _packet(PositionX=120.0, PositionZ=-50.0),
            received_at_ms=1000,
        )

        self.assertEqual(result["session_action"], "start")
        self.assertEqual(result["lap_action"], "none")
        self.assertEqual(result["session_id"], 1)
        self.assertTrue(result["session_active"])
        self.assertIsNone(result["lap_id"])
        self.assertIsNone(result["active_lap_id"])
        self.assertIsNone(result["lap_number"])
        self.assertEqual(result["uncertainty"], "no_lap_signal")
        self.assertEqual(result["boundary_confidence"], "uncertain")

    def test_menu_pause_packets_do_not_delete_active_session(self):
        detector = LapDetector()
        started = detector.observe(
            _lap_packet(1, CurrentLap=2.0, CurrentRaceTime=2.0),
            received_at_ms=1000,
        )

        paused = detector.observe(
            _packet(IsRaceOn=0, CurrentLap=0.0, CurrentRaceTime=0.0, LapNumber=0),
            received_at_ms=2000,
        )
        resumed = detector.observe(
            _lap_packet(1, CurrentLap=2.5, CurrentRaceTime=2.5),
            received_at_ms=3000,
        )

        self.assertEqual(started["session_id"], 1)
        self.assertEqual(paused["session_action"], "pause")
        self.assertEqual(paused["session_id"], 1)
        self.assertTrue(paused["session_active"])
        self.assertEqual(paused["uncertainty"], "paused")
        self.assertEqual(resumed["session_action"], "resume")
        self.assertEqual(resumed["session_id"], 1)
        self.assertTrue(resumed["session_active"])
        self.assertEqual(resumed["lap_action"], "none")
        self.assertEqual(resumed["lap_id"], 1)
        self.assertEqual(resumed["active_lap_id"], 1)
        self.assertIsNone(resumed["uncertainty"])

    def test_resume_after_pause_with_teleport_starts_new_lap_on_resume_packet(self):
        detector = LapDetector()
        detector.observe(
            _lap_packet(
                1,
                CurrentLap=8.0,
                CurrentRaceTime=8.0,
                PositionX=0.0,
                PositionY=0.0,
                PositionZ=0.0,
            ),
            received_at_ms=1000,
        )
        detector.observe(
            _packet(IsRaceOn=0, CurrentLap=0.0, CurrentRaceTime=0.0, LapNumber=0),
            received_at_ms=2000,
        )

        resumed = detector.observe(
            _lap_packet(
                1,
                CurrentLap=8.5,
                CurrentRaceTime=8.5,
                PositionX=TELEPORT_DISTANCE_METERS + 1.0,
                PositionY=0.0,
                PositionZ=0.0,
            ),
            received_at_ms=3000,
        )

        self.assertEqual(resumed["session_action"], "resume")
        self.assertEqual(resumed["lap_action"], "finalize_and_start")
        self.assertEqual(resumed["finalized_lap_id"], 1)
        self.assertEqual(resumed["lap_id"], 2)
        self.assertEqual(resumed["active_lap_id"], 2)
        self.assertEqual(resumed["uncertainty"], "teleport")
        self.assertEqual(resumed["boundary_confidence"], "uncertain")

    def test_resume_after_pause_with_lap_timer_reset_starts_new_lap_on_resume_packet(self):
        detector = LapDetector()
        detector.observe(
            _lap_packet(
                1,
                CurrentLap=8.0,
                CurrentRaceTime=8.0,
                PositionX=10.0,
                PositionZ=10.0,
            ),
            received_at_ms=1000,
        )
        detector.observe(
            _packet(IsRaceOn=0, CurrentLap=0.0, CurrentRaceTime=0.0, LapNumber=0),
            received_at_ms=2000,
        )

        resumed = detector.observe(
            _lap_packet(
                1,
                CurrentLap=0.4,
                CurrentRaceTime=8.4,
                PositionX=10.2,
                PositionZ=10.2,
            ),
            received_at_ms=3000,
        )

        self.assertEqual(resumed["session_action"], "resume")
        self.assertEqual(resumed["lap_action"], "finalize_and_start")
        self.assertEqual(resumed["finalized_lap_id"], 1)
        self.assertEqual(resumed["lap_id"], 2)
        self.assertEqual(resumed["active_lap_id"], 2)
        self.assertEqual(resumed["uncertainty"], "partial_lap")
        self.assertEqual(resumed["boundary_confidence"], "uncertain")

    def test_resume_after_pause_with_race_time_reset_starts_new_lap_on_resume_packet(self):
        detector = LapDetector()
        detector.observe(
            _lap_packet(
                1,
                CurrentLap=8.0,
                CurrentRaceTime=8.0,
                PositionX=10.0,
                PositionZ=10.0,
            ),
            received_at_ms=1000,
        )
        detector.observe(
            _packet(IsRaceOn=0, CurrentLap=0.0, CurrentRaceTime=0.0, LapNumber=0),
            received_at_ms=2000,
        )

        resumed = detector.observe(
            _lap_packet(
                1,
                CurrentLap=8.4,
                CurrentRaceTime=2.0,
                PositionX=10.2,
                PositionZ=10.2,
            ),
            received_at_ms=3000,
        )

        self.assertEqual(resumed["session_action"], "resume")
        self.assertEqual(resumed["lap_action"], "finalize_and_start")
        self.assertEqual(resumed["finalized_lap_id"], 1)
        self.assertEqual(resumed["lap_id"], 2)
        self.assertEqual(resumed["active_lap_id"], 2)
        self.assertEqual(resumed["uncertainty"], "partial_lap")
        self.assertEqual(resumed["boundary_confidence"], "uncertain")

    def test_resume_after_pause_with_lower_lap_number_starts_new_lap_on_resume_packet(self):
        detector = LapDetector()
        detector.observe(
            _lap_packet(
                3,
                CurrentLap=8.0,
                CurrentRaceTime=8.0,
                PositionX=10.0,
                PositionZ=10.0,
            ),
            received_at_ms=1000,
        )
        detector.observe(
            _packet(IsRaceOn=0, CurrentLap=0.0, CurrentRaceTime=0.0, LapNumber=0),
            received_at_ms=2000,
        )

        resumed = detector.observe(
            _lap_packet(
                1,
                CurrentLap=8.4,
                CurrentRaceTime=8.4,
                PositionX=10.2,
                PositionZ=10.2,
            ),
            received_at_ms=3000,
        )

        self.assertEqual(resumed["session_action"], "resume")
        self.assertEqual(resumed["lap_action"], "finalize_and_start")
        self.assertEqual(resumed["finalized_lap_id"], 1)
        self.assertEqual(resumed["lap_id"], 2)
        self.assertEqual(resumed["active_lap_id"], 2)
        self.assertEqual(resumed["uncertainty"], "partial_lap")
        self.assertEqual(resumed["boundary_confidence"], "uncertain")


    def test_race_off_return_to_prior_route_point_marks_rewind_without_splitting_lap(self):
        detector = LapDetector()
        detector.observe(
            _lap_packet(
                0,
                CurrentLap=28.388,
                CurrentRaceTime=30.104,
                PositionX=4314.6,
                PositionY=151.4,
                PositionZ=-5860.1,
                Speed=39.6,
            ),
            received_at_ms=1000,
        )
        detector.observe(
            _lap_packet(
                0,
                CurrentLap=33.617,
                CurrentRaceTime=35.333,
                PositionX=4067.5,
                PositionY=148.8,
                PositionZ=-5750.4,
                Speed=73.7,
            ),
            received_at_ms=2000,
        )
        detector.observe(
            _packet(IsRaceOn=0, CurrentLap=0.0, CurrentRaceTime=0.0, LapNumber=0),
            received_at_ms=3000,
        )

        resumed = detector.observe(
            _lap_packet(
                0,
                CurrentLap=28.388,
                CurrentRaceTime=30.104,
                PositionX=4314.61,
                PositionY=151.4,
                PositionZ=-5860.1,
                Speed=39.6,
            ),
            received_at_ms=4000,
        )

        self.assertEqual(resumed["session_action"], "resume")
        self.assertEqual(resumed["lap_action"], "none")
        self.assertIsNone(resumed["finalized_lap_id"])
        self.assertEqual(resumed["lap_id"], 1)
        self.assertEqual(resumed["active_lap_id"], 1)
        self.assertEqual(resumed["uncertainty"], "rewind")
        self.assertEqual(resumed["boundary_confidence"], "uncertain")
        self.assertAlmostEqual(resumed["race_control_match_distance_m"], 0.01, places=2)
        self.assertAlmostEqual(resumed["race_control_discard_after_current_lap"], 28.388, places=3)

    def test_race_off_rewind_suppresses_lap_number_boundary(self):
        detector = LapDetector()
        detector.observe(
            _lap_packet(
                0,
                CurrentLap=0.0,
                CurrentRaceTime=10.0,
                PositionX=100.0,
                PositionY=0.0,
                PositionZ=100.0,
                Speed=20.0,
            ),
            received_at_ms=1000,
        )
        detector.observe(
            _lap_packet(
                0,
                CurrentLap=5.0,
                CurrentRaceTime=15.0,
                PositionX=250.0,
                PositionY=0.0,
                PositionZ=250.0,
                Speed=40.0,
            ),
            received_at_ms=2000,
        )
        detector.observe(
            _packet(IsRaceOn=0, CurrentLap=0.0, CurrentRaceTime=0.0, LapNumber=0),
            received_at_ms=3000,
        )

        resumed = detector.observe(
            _lap_packet(
                1,
                CurrentLap=0.0,
                CurrentRaceTime=20.0,
                PositionX=100.0,
                PositionY=0.0,
                PositionZ=100.0,
                Speed=20.0,
            ),
            received_at_ms=4000,
        )

        self.assertEqual(resumed["session_action"], "resume")
        self.assertEqual(resumed["lap_action"], "none")
        self.assertIsNone(resumed["finalized_lap_id"])
        self.assertEqual(resumed["lap_id"], 1)
        self.assertEqual(resumed["active_lap_id"], 1)
        self.assertEqual(resumed["uncertainty"], "rewind")
        self.assertAlmostEqual(resumed["race_control_discard_after_current_lap"], 0.0)

    def test_in_race_reset_prefers_recent_route_match_over_older_closer_overlap(self):
        detector = LapDetector()
        detector.observe(
            _lap_packet(
                1,
                CurrentLap=1.0,
                CurrentRaceTime=1.0,
                PositionX=0.0,
                PositionY=0.0,
                PositionZ=0.0,
            ),
            received_at_ms=1000,
        )
        detector.observe(
            _lap_packet(
                1,
                CurrentLap=8.0,
                CurrentRaceTime=8.0,
                PositionX=20.0,
                PositionY=0.0,
                PositionZ=0.0,
            ),
            received_at_ms=2000,
        )
        detector.observe(
            _lap_packet(
                1,
                CurrentLap=9.0,
                CurrentRaceTime=9.0,
                PositionX=500.0,
                PositionY=0.0,
                PositionZ=0.0,
            ),
            received_at_ms=3000,
        )

        reset = detector.observe(
            _lap_packet(
                1,
                CurrentLap=9.1,
                CurrentRaceTime=9.1,
                PositionX=0.0,
                PositionY=0.0,
                PositionZ=0.0,
                Speed=0.0,
            ),
            received_at_ms=4000,
        )

        self.assertEqual(reset["uncertainty"], "reset")
        self.assertEqual(reset["lap_action"], "none")
        self.assertAlmostEqual(reset["race_control_discard_after_current_lap"], 8.0)
        self.assertAlmostEqual(reset["race_control_match_distance_m"], 20.0)

    def test_in_race_jump_to_recent_route_point_marks_reset_without_splitting_lap(self):
        detector = LapDetector()
        detector.observe(
            _lap_packet(
                0,
                CurrentLap=49.203,
                CurrentRaceTime=50.920,
                PositionX=4079.1,
                PositionY=144.4,
                PositionZ=-5355.9,
                Speed=65.4,
            ),
            received_at_ms=1000,
        )
        detector.observe(
            _lap_packet(
                0,
                CurrentLap=54.614,
                CurrentRaceTime=56.330,
                PositionX=4152.9,
                PositionY=165.9,
                PositionZ=-5749.9,
                Speed=79.3,
            ),
            received_at_ms=2000,
        )

        reset = detector.observe(
            _lap_packet(
                0,
                CurrentLap=54.629,
                CurrentRaceTime=56.345,
                PositionX=4089.9,
                PositionY=144.8,
                PositionZ=-5357.0,
                Speed=0.0,
            ),
            received_at_ms=2017,
        )

        self.assertEqual(reset["session_action"], "none")
        self.assertEqual(reset["lap_action"], "none")
        self.assertIsNone(reset["finalized_lap_id"])
        self.assertEqual(reset["lap_id"], 1)
        self.assertEqual(reset["active_lap_id"], 1)
        self.assertEqual(reset["uncertainty"], "reset")
        self.assertEqual(reset["boundary_confidence"], "uncertain")
        self.assertGreater(reset["position_delta_m"], 300.0)
        self.assertLess(reset["position_delta_m"], TELEPORT_DISTANCE_METERS)
        self.assertLess(reset["race_control_match_distance_m"], 12.0)
        self.assertAlmostEqual(reset["race_control_discard_after_current_lap"], 49.203, places=3)

    def test_menu_pause_after_meaningful_progress_does_not_finalize_session(self):
        detector = LapDetector()
        started = detector.observe(
            _lap_packet(1, CurrentLap=1.0, CurrentRaceTime=1.0),
            received_at_ms=1000,
        )
        detector.observe(
            _lap_packet(
                1,
                CurrentLap=MEANINGFUL_RACE_TIME_SECONDS + 2.0,
                CurrentRaceTime=MEANINGFUL_RACE_TIME_SECONDS + 2.0,
            ),
            received_at_ms=2000,
        )

        result = detector.observe(
            _packet(IsRaceOn=0, CurrentLap=0.0, CurrentRaceTime=0.0, LapNumber=0),
            received_at_ms=3000,
        )

        self.assertEqual(started["session_id"], 1)
        self.assertEqual(result["session_action"], "pause")
        self.assertEqual(result["lap_action"], "none")
        self.assertEqual(result["session_id"], 1)
        self.assertTrue(result["session_active"])
        self.assertEqual(result["active_session_id"], 1)
        self.assertEqual(result["active_lap_id"], 1)
        self.assertIsNone(result["finalized_session_id"])
        self.assertEqual(result["uncertainty"], "paused")
        self.assertEqual(result["boundary_confidence"], "uncertain")

    def test_implausible_position_jump_splits_teleport_lap(self):
        detector = LapDetector()
        detector.observe(
            _lap_packet(1, PositionX=0.0, PositionY=0.0, PositionZ=0.0),
            received_at_ms=1000,
        )

        result = detector.observe(
            _lap_packet(
                1,
                PositionX=TELEPORT_DISTANCE_METERS + 1.0,
                PositionY=0.0,
                PositionZ=0.0,
                CurrentLap=1.2,
                CurrentRaceTime=1.2,
            ),
            received_at_ms=2000,
        )

        self.assertEqual(result["session_action"], "none")
        self.assertEqual(result["lap_action"], "finalize_and_start")
        self.assertEqual(result["session_id"], 1)
        self.assertEqual(result["active_session_id"], 1)
        self.assertEqual(result["finalized_lap_id"], 1)
        self.assertEqual(result["lap_id"], 2)
        self.assertEqual(result["active_lap_id"], 2)
        self.assertEqual(result["uncertainty"], "teleport")
        self.assertEqual(result["boundary_confidence"], "uncertain")
        self.assertGreater(result["position_delta_m"], TELEPORT_DISTANCE_METERS)

    def test_event_exit_without_active_lap_finalizes_session_only(self):
        detector = LapDetector()
        detector._active_session_id = 7
        detector._active_lap_id = None
        detector._active_lap_number = None
        detector._last_race_time = MEANINGFUL_RACE_TIME_SECONDS + 3.0
        detector._max_race_time = detector._last_race_time

        result = detector.observe(
            _packet(IsRaceOn=1, CurrentLap=0.0, CurrentRaceTime=0.1, LapNumber=0),
            received_at_ms=1000,
        )

        self.assertEqual(result["session_action"], "finalize")
        self.assertEqual(result["lap_action"], "none")
        self.assertEqual(result["finalized_session_id"], 7)
        self.assertIsNone(result["finalized_lap_id"])
        self.assertFalse(result["session_active"])
        self.assertIsNone(result["active_session_id"])
        self.assertIsNone(result["active_lap_id"])
        self.assertEqual(result["uncertainty"], "event_exit")

    def test_race_time_reset_after_meaningful_progress_finalizes_session_as_event_exit(self):
        detector = LapDetector()
        started = detector.observe(
            _lap_packet(1, CurrentLap=1.0, CurrentRaceTime=1.0),
            received_at_ms=1000,
        )
        detector.observe(
            _lap_packet(
                1,
                CurrentLap=MEANINGFUL_RACE_TIME_SECONDS + 2.0,
                CurrentRaceTime=MEANINGFUL_RACE_TIME_SECONDS + 2.0,
            ),
            received_at_ms=2000,
        )

        result = detector.observe(
            _packet(IsRaceOn=1, CurrentLap=0.0, CurrentRaceTime=0.1, LapNumber=0),
            received_at_ms=3000,
        )

        self.assertEqual(started["session_id"], 1)
        self.assertEqual(result["session_action"], "finalize")
        self.assertEqual(result["lap_action"], "finalize")
        self.assertEqual(result["finalized_session_id"], 1)
        self.assertEqual(result["finalized_lap_id"], 1)
        self.assertFalse(result["session_active"])
        self.assertIsNone(result["active_session_id"])
        self.assertIsNone(result["active_lap_id"])
        self.assertEqual(result["uncertainty"], "event_exit")
        self.assertEqual(result["boundary_confidence"], "heuristic")


if __name__ == "__main__":
    unittest.main()
