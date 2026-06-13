import unittest

from telemetry_tracker.capture import CaptureMode, CapturePhase, CaptureStateMachine
from telemetry_tracker.packet_bridge import decode_packet, encode_packet_for_test


def _packet(overrides: dict | None = None) -> tuple[bytes, dict]:
    raw = encode_packet_for_test(overrides or {})
    return raw, decode_packet(raw)


def _menu_packet(index: int, **overrides) -> tuple[bytes, dict]:
    values = {
        "IsRaceOn": 0,
        "TimestampMS": index * 16,
        "CurrentEngineRpm": 0.0,
        "CarClass": 0,
        "CarPerformanceIndex": 0,
        "DrivetrainType": 0,
        "PositionX": 0.0,
        "PositionY": 0.0,
        "PositionZ": 0.0,
        "Speed": 0.0,
        "CurrentLap": 0.0,
        "CurrentRaceTime": 0.0,
        "LapNumber": 0,
    }
    values.update(overrides)
    return _packet(values)


def _race_packet(index: int, **overrides) -> tuple[bytes, dict]:
    values = {
        "IsRaceOn": 1,
        "TimestampMS": index * 16,
        "CurrentEngineRpm": 3500.0,
        "CarClass": 4,
        "CarPerformanceIndex": 800,
        "DrivetrainType": 2,
        "PositionX": float(index),
        "PositionY": 0.0,
        "PositionZ": float(index) * 2.0,
        "Speed": 30.0,
        "CurrentLap": float(index) / 10.0,
        "CurrentRaceTime": float(index) / 10.0,
        "LapNumber": 1,
    }
    values.update(overrides)
    return _packet(values)


class CaptureStateMachineTests(unittest.TestCase):
    def test_default_mode_is_auto(self):
        machine = CaptureStateMachine()
        status = machine.status()

        self.assertEqual(machine.mode, CaptureMode.AUTO)
        self.assertEqual(machine.phase, CapturePhase.IDLE)
        self.assertEqual(status["mode"], "auto")
        self.assertNotIn("listener", status)
        self.assertFalse(status["recording"]["active"])
        self.assertEqual(status["recording"]["total_live_packets_recorded_excluding_prebuffer"], 0)
        self.assertIsNone(status["packet_receipt"]["last_is_race_on"])
        self.assertEqual(status["packet_receipt"]["last_packet_type"], "unknown")

    def test_constructor_rejects_invalid_mode_and_prebuffer_size(self):
        with self.assertRaisesRegex(ValueError, "mode"):
            CaptureStateMachine(mode="sometimes")

        with self.assertRaisesRegex(ValueError, "prebuffer_packets"):
            CaptureStateMachine(prebuffer_packets=-1)

    def test_manual_mode_starts_recording_only_after_start_manual(self):
        machine = CaptureStateMachine(mode="manual", prebuffer_packets=2)
        first_raw, first_decoded = _race_packet(1)
        second_raw, second_decoded = _race_packet(2)

        should_record, flush = machine.observe_packet(first_raw, first_decoded)
        self.assertFalse(should_record)
        self.assertEqual(flush, [])
        self.assertEqual(machine.phase, CapturePhase.RECEIVING_NOT_RECORDING)

        flush = machine.start_manual()
        self.assertEqual(flush, [first_raw])
        self.assertEqual(machine.phase, CapturePhase.RECORDING)

        should_record, flush = machine.observe_packet(second_raw, second_decoded)
        self.assertTrue(should_record)
        self.assertEqual(flush, [])

    def test_auto_mode_stays_receiving_not_recording_for_static_menu_packets(self):
        machine = CaptureStateMachine(mode="auto")

        for index in range(3):
            raw, decoded = _menu_packet(index)
            should_record, flush = machine.observe_packet(raw, decoded)

            self.assertFalse(should_record)
            self.assertEqual(flush, [])

        status = machine.status()
        self.assertEqual(machine.phase, CapturePhase.RECEIVING_NOT_RECORDING)
        self.assertEqual(status["packet_receipt"]["packets_observed"], 3)
        self.assertFalse(status["packet_receipt"]["last_is_race_on"])
        self.assertEqual(status["packet_receipt"]["last_packet_type"], "non_race")
        self.assertFalse(status["recording"]["active"])

    def test_status_reports_latest_packet_race_flag_independent_of_recording(self):
        machine = CaptureStateMachine(mode="manual")
        menu_raw, menu_decoded = _menu_packet(1)
        race_raw, race_decoded = _race_packet(2)

        self.assertEqual(machine.observe_packet(menu_raw, menu_decoded), (False, []))
        menu_status = machine.status()["packet_receipt"]
        self.assertFalse(menu_status["last_is_race_on"])
        self.assertEqual(menu_status["last_packet_type"], "non_race")

        self.assertEqual(machine.observe_packet(race_raw, race_decoded), (False, []))
        race_status = machine.status()["packet_receipt"]
        self.assertTrue(race_status["last_is_race_on"])
        self.assertEqual(race_status["last_packet_type"], "race")
        self.assertFalse(machine.status()["recording"]["active"])

    def test_auto_mode_transitions_to_recording_when_race_like_signals_are_present(self):
        machine = CaptureStateMachine(mode="auto", prebuffer_packets=3)
        menu_raw, menu_decoded = _menu_packet(0)
        race_raw, race_decoded = _race_packet(10)

        self.assertEqual(machine.observe_packet(menu_raw, menu_decoded), (False, []))
        should_record, flush = machine.observe_packet(race_raw, race_decoded)

        self.assertTrue(should_record)
        self.assertEqual(flush, [])
        self.assertEqual(machine.phase, CapturePhase.RECORDING)
        auto_detection = machine.status()["auto_detection"]
        self.assertTrue(auto_detection["last_signals"]["race_on"])
        self.assertTrue(auto_detection["last_signals"]["moving"])
        self.assertTrue(auto_detection["last_signals"]["valid_vehicle"])
        self.assertTrue(auto_detection["last_signals"]["race_time_progressing"])

    def test_first_race_like_packet_does_not_start_until_race_time_progresses(self):
        machine = CaptureStateMachine(mode="auto", prebuffer_packets=3)
        first_raw, first_decoded = _race_packet(1, CurrentRaceTime=1.0)
        second_raw, second_decoded = _race_packet(2, CurrentRaceTime=1.5)

        should_record, flush = machine.observe_packet(first_raw, first_decoded)
        self.assertFalse(should_record)
        self.assertEqual(flush, [])
        self.assertEqual(machine.phase, CapturePhase.RECEIVING_NOT_RECORDING)
        self.assertFalse(
            machine.status()["auto_detection"]["last_signals"]["race_time_progressing"]
        )

        should_record, flush = machine.observe_packet(second_raw, second_decoded)
        self.assertTrue(should_record)
        self.assertEqual(flush, [first_raw])

    def test_switching_auto_to_manual_stops_active_recording_until_manual_start(self):
        machine = CaptureStateMachine(mode="auto", prebuffer_packets=3)
        first_raw, first_decoded = _race_packet(1)
        second_raw, second_decoded = _race_packet(2)
        self.assertEqual(machine.observe_packet(first_raw, first_decoded), (False, []))
        self.assertEqual(
            machine.observe_packet(second_raw, second_decoded),
            (True, [first_raw]),
        )

        machine.set_mode("manual")
        self.assertEqual(machine.mode, CaptureMode.MANUAL)
        self.assertEqual(machine.phase, CapturePhase.RECEIVING_NOT_RECORDING)
        self.assertFalse(machine.status()["recording"]["active"])

        post_switch_raw, post_switch_decoded = _race_packet(3)
        self.assertEqual(
            machine.observe_packet(post_switch_raw, post_switch_decoded),
            (False, []),
        )
        self.assertEqual(machine.start_manual(), [post_switch_raw])

    def test_switching_auto_to_manual_clears_prebuffer_observed_before_switch(self):
        machine = CaptureStateMachine(mode="auto", prebuffer_packets=3)
        buffered_raw, buffered_decoded = _menu_packet(1)
        post_switch_raw, post_switch_decoded = _menu_packet(2)

        self.assertEqual(machine.observe_packet(buffered_raw, buffered_decoded), (False, []))

        machine.set_mode("manual")
        self.assertEqual(machine.start_manual(), [])
        machine.stop_manual()

        self.assertEqual(
            machine.observe_packet(post_switch_raw, post_switch_decoded),
            (False, []),
        )
        self.assertEqual(machine.start_manual(), [post_switch_raw])

    def test_switching_manual_to_auto_stops_and_rebuilds_auto_confidence(self):
        machine = CaptureStateMachine(mode="manual", prebuffer_packets=3)
        buffered_raw, buffered_decoded = _menu_packet(1)
        machine.observe_packet(buffered_raw, buffered_decoded)
        self.assertEqual(machine.start_manual(), [buffered_raw])
        manual_raw, manual_decoded = _race_packet(2)
        self.assertEqual(machine.observe_packet(manual_raw, manual_decoded), (True, []))

        machine.set_mode("auto")
        self.assertEqual(machine.mode, CaptureMode.AUTO)
        self.assertEqual(machine.phase, CapturePhase.RECEIVING_NOT_RECORDING)

        first_auto_raw, first_auto_decoded = _race_packet(3)
        second_auto_raw, second_auto_decoded = _race_packet(4)
        self.assertEqual(
            machine.observe_packet(first_auto_raw, first_auto_decoded),
            (False, []),
        )
        self.assertEqual(
            machine.observe_packet(second_auto_raw, second_auto_decoded),
            (True, [first_auto_raw]),
        )

    def test_switching_manual_to_auto_clears_prebuffer_observed_before_switch(self):
        machine = CaptureStateMachine(mode="manual", prebuffer_packets=3)
        buffered_raw, buffered_decoded = _menu_packet(1)
        first_auto_raw, first_auto_decoded = _race_packet(2, CurrentRaceTime=1.0)
        second_auto_raw, second_auto_decoded = _race_packet(3, CurrentRaceTime=1.5)

        self.assertEqual(machine.observe_packet(buffered_raw, buffered_decoded), (False, []))

        machine.set_mode("auto")
        self.assertEqual(machine.status()["prebuffer"]["size"], 0)
        self.assertEqual(
            machine.observe_packet(first_auto_raw, first_auto_decoded),
            (False, []),
        )
        self.assertEqual(
            machine.observe_packet(second_auto_raw, second_auto_decoded),
            (True, [first_auto_raw]),
        )

    def test_stop_manual_does_not_stop_auto_recording(self):
        machine = CaptureStateMachine(mode="auto")
        first_raw, first_decoded = _race_packet(1)
        second_raw, second_decoded = _race_packet(2)
        third_raw, third_decoded = _race_packet(3)
        self.assertEqual(machine.observe_packet(first_raw, first_decoded), (False, []))
        self.assertEqual(machine.observe_packet(second_raw, second_decoded), (True, [first_raw]))

        machine.stop_manual()
        self.assertEqual(machine.mode, CaptureMode.AUTO)
        self.assertEqual(machine.phase, CapturePhase.RECORDING)
        self.assertEqual(machine.observe_packet(third_raw, third_decoded), (True, []))

    def test_rolling_prebuffer_flushes_last_n_packets_exactly_once(self):
        machine = CaptureStateMachine(mode="auto", prebuffer_packets=3)
        static_packets = [_menu_packet(index) for index in range(5)]
        for raw, decoded in static_packets:
            should_record, flush = machine.observe_packet(raw, decoded)
            self.assertFalse(should_record)
            self.assertEqual(flush, [])

        trigger_raw, trigger_decoded = _race_packet(20)
        should_record, flush = machine.observe_packet(trigger_raw, trigger_decoded)
        self.assertTrue(should_record)
        self.assertEqual(flush, [])

        next_raw, next_decoded = _race_packet(21)
        should_record, flush = machine.observe_packet(next_raw, next_decoded)
        self.assertTrue(should_record)
        self.assertEqual(flush, [])

    def test_auto_prebuffer_discards_race_off_packets_but_keeps_initial_race_packet(self):
        machine = CaptureStateMachine(mode="auto", prebuffer_packets=3)
        menu_raw, menu_decoded = _menu_packet(0)
        first_race_raw, first_race_decoded = _race_packet(1, CurrentRaceTime=0.0)
        second_race_raw, second_race_decoded = _race_packet(2, CurrentRaceTime=1.5)

        self.assertEqual(machine.observe_packet(menu_raw, menu_decoded), (False, []))
        self.assertEqual(machine.observe_packet(first_race_raw, first_race_decoded), (False, []))
        should_record, flush = machine.observe_packet(second_race_raw, second_race_decoded)

        self.assertTrue(should_record)
        self.assertEqual(flush, [first_race_raw])

    def test_stop_finalizes_recording_and_preserves_future_prebuffer_behavior(self):
        machine = CaptureStateMachine(mode="manual", prebuffer_packets=2)
        first_raw, first_decoded = _menu_packet(1)
        record_raw, record_decoded = _race_packet(2)
        machine.observe_packet(first_raw, first_decoded)
        self.assertEqual(machine.start_manual(), [first_raw])
        self.assertEqual(machine.observe_packet(record_raw, record_decoded), (True, []))

        machine.stop_manual()
        self.assertEqual(machine.phase, CapturePhase.RECEIVING_NOT_RECORDING)
        self.assertFalse(machine.status()["recording"]["active"])

        post_stop_packets = [_menu_packet(3), _menu_packet(4)]
        for raw, decoded in post_stop_packets:
            self.assertEqual(machine.observe_packet(raw, decoded), (False, []))

        self.assertEqual(machine.start_manual(), [raw for raw, _decoded in post_stop_packets])
        self.assertEqual(machine.start_manual(), [])


if __name__ == "__main__":
    unittest.main()
