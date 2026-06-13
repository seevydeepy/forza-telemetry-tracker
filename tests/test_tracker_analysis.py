import tempfile
import unittest
from pathlib import Path

from telemetry_tracker.analysis import (
    analyze_lap,
    generate_issue_markers,
    summarize_samples,
    summarize_section,
)
from telemetry_tracker.packet_bridge import (
    decode_packet,
    encode_packet_for_test,
    packet_to_live_fields,
)
from telemetry_tracker.rules import load_default_ruleset
from telemetry_tracker.storage import TelemetryStore


class TrackerAnalysisTests(unittest.TestCase):
    def test_generate_issue_markers_flags_rear_combined_slip_as_critical(self):
        ruleset = load_default_ruleset()
        samples = [
            {"sequence": 10, "combined_slip": 1.25, "rear_combined_slip": 1.25},
            {"sequence": 11, "combined_slip": 1.28, "rear_combined_slip": 1.28},
            {"sequence": 12, "combined_slip": 0.2, "rear_combined_slip": 0.2},
        ]

        markers = generate_issue_markers(samples, ruleset)

        slip = [marker for marker in markers if marker["metric"] == "rear_combined_slip"]
        self.assertEqual(len(slip), 1)
        self.assertEqual(slip[0]["severity"], "critical")
        self.assertEqual((slip[0]["start_sequence"], slip[0]["end_sequence"]), (10, 11))
        self.assertEqual(slip[0]["anchor_sequence"], 11)
        self.assertEqual(slip[0]["issue_kind"], "Rear combined slip")
        self.assertEqual(slip[0]["value_label"], "Rear combined slip")
        self.assertEqual(slip[0]["threshold_operator"], "gte")
        self.assertAlmostEqual(slip[0]["actual_value"], 1.28)
        self.assertAlmostEqual(slip[0]["threshold_value"], 1.15)

    def test_generate_issue_markers_flags_braking_instability(self):
        ruleset = load_default_ruleset()
        samples = [
            {"sequence": 21, "brake": 220, "combined_slip": 0.41},
            {"sequence": 22, "brake": 230, "combined_slip": 0.5},
            {"sequence": 23, "brake": 10, "combined_slip": 0.1},
        ]

        markers = generate_issue_markers(samples, ruleset)

        braking = [marker for marker in markers if marker["metric"] == "brake_pressure_and_slip"]
        self.assertEqual(len(braking), 1)
        self.assertEqual(braking[0]["reason"], ruleset.rules[1].reason)
        self.assertEqual((braking[0]["start_sequence"], braking[0]["end_sequence"]), (21, 22))

    def test_generate_issue_markers_flags_low_rpm_bogging_with_lte_details(self):
        ruleset = load_default_ruleset()
        samples = [
            {"sequence": 51, "throttle": 180, "current_rpm": 3000.0, "engine_max_rpm": 8000.0},
            {"sequence": 52, "throttle": 170, "current_rpm": 2500.0, "engine_max_rpm": 8000.0},
            {"sequence": 53, "throttle": 20, "current_rpm": 6000.0, "engine_max_rpm": 8000.0},
        ]

        markers = generate_issue_markers(samples, ruleset)

        bogging = [marker for marker in markers if marker["metric"] == "engine_rpm_and_throttle"]
        self.assertEqual(len(bogging), 1)
        self.assertEqual(bogging[0]["anchor_sequence"], 52)
        self.assertEqual(bogging[0]["issue_kind"], "Low RPM bogging")
        self.assertEqual(bogging[0]["value_label"], "RPM ratio")
        self.assertEqual(bogging[0]["threshold_operator"], "lte")
        self.assertAlmostEqual(bogging[0]["actual_value"], 0.3125)
        self.assertAlmostEqual(bogging[0]["threshold_value"], 0.4)

    def test_generate_issue_markers_flags_bottoming(self):
        ruleset = load_default_ruleset()
        samples = [
            {"sequence": 31, "suspension_travel_front_left": 0.4, "suspension_travel_front_right": 0.3, "suspension_travel_rear_left": 0.99, "suspension_travel_rear_right": 0.97},
            {"sequence": 32, "suspension_travel_front_left": 0.2, "suspension_travel_front_right": 0.2, "suspension_travel_rear_left": 0.2, "suspension_travel_rear_right": 0.2},
        ]

        markers = generate_issue_markers(samples, ruleset)

        bottoming = [marker for marker in markers if marker["metric"] == "suspension_travel"]
        self.assertEqual(len(bottoming), 1)
        self.assertEqual(bottoming[0]["severity"], "critical")
        self.assertEqual((bottoming[0]["start_sequence"], bottoming[0]["end_sequence"]), (31, 31))

    def test_negative_suspension_travel_does_not_count_as_bottoming(self):
        ruleset = load_default_ruleset()
        samples = [
            {"sequence": 41, "speed_mps": 10.0, "combined_slip": 0.1, "suspension_travel_front_left": -1.0, "suspension_travel_front_right": -0.99, "suspension_travel_rear_left": -0.98, "suspension_travel_rear_right": -0.97},
            {"sequence": 42, "speed_mps": 12.0, "combined_slip": 0.2, "suspension_travel_front_left": -1.1, "suspension_travel_front_right": -1.05, "suspension_travel_rear_left": -1.0, "suspension_travel_rear_right": -0.95},
        ]

        markers = generate_issue_markers(samples, ruleset)
        summary = summarize_samples(samples)

        bottoming = [marker for marker in markers if marker["metric"] == "suspension_travel"]
        self.assertEqual(bottoming, [])
        self.assertEqual(summary["bottoming_events"], 0)


    def test_generate_issue_markers_flags_rewind_and_reset_uncertainties(self):
        ruleset = load_default_ruleset()
        samples = [
            {"sequence": 100, "uncertainty": "rewind"},
            {"sequence": 101, "uncertainty": None},
            {"sequence": 200, "uncertainty": "reset"},
        ]

        markers = generate_issue_markers(samples, ruleset)

        race_markers = [marker for marker in markers if marker["metric"].startswith("race.")]
        self.assertEqual([marker["metric"] for marker in race_markers], ["race.rewind", "race.reset"])
        self.assertEqual([marker["severity"] for marker in race_markers], ["info", "info"])
        self.assertEqual([marker["anchor_sequence"] for marker in race_markers], [100, 200])
        self.assertEqual([marker["issue_kind"] for marker in race_markers], ["Rewind", "Reset"])
        self.assertIn("rewind", race_markers[0]["reason"].lower())
        self.assertIn("reset", race_markers[1]["reason"].lower())

    def test_summarize_samples_reports_full_lap_metrics(self):
        samples = [
            {"sequence": 1, "speed_mps": 10.0, "combined_slip": 0.2, "current_rpm": 6000.0, "engine_max_rpm": 8000.0, "throttle": 255, "suspension_travel_front_left": 0.1, "suspension_travel_front_right": 0.1, "suspension_travel_rear_left": 0.1, "suspension_travel_rear_right": 0.1},
            {"sequence": 2, "speed_mps": 30.0, "combined_slip": 0.35, "current_rpm": 7950.0, "engine_max_rpm": 8000.0, "throttle": 255, "suspension_travel_front_left": 0.99, "suspension_travel_front_right": 0.3, "suspension_travel_rear_left": 0.4, "suspension_travel_rear_right": 0.2},
            {"sequence": 3, "speed_mps": 20.0, "combined_slip": 0.8, "current_rpm": 7960.0, "engine_max_rpm": 8000.0, "throttle": 255, "suspension_travel_front_left": 0.2, "suspension_travel_front_right": 0.2, "suspension_travel_rear_left": 0.2, "suspension_travel_rear_right": 0.2},
            {"sequence": 4, "speed_mps": 40.0, "combined_slip": 0.5, "current_rpm": 7970.0, "engine_max_rpm": 8000.0, "throttle": 255, "suspension_travel_front_left": 0.2, "suspension_travel_front_right": 0.2, "suspension_travel_rear_left": 0.2, "suspension_travel_rear_right": 0.2},
        ]

        summary = summarize_samples(samples)

        self.assertEqual(summary["packet_count"], 4)
        self.assertAlmostEqual(summary["top_speed_mps"], 40.0)
        self.assertAlmostEqual(summary["average_speed_mps"], 25.0)
        self.assertAlmostEqual(summary["peak_combined_slip"], 0.8)
        self.assertEqual(summary["limiter_samples"], 3)
        self.assertEqual(summary["bottoming_events"], 1)

    def test_summarize_section_uses_sequence_range(self):
        samples = [
            {"sequence": 100, "speed_mps": 10.0, "combined_slip": 0.1},
            {"sequence": 101, "speed_mps": 20.0, "combined_slip": 0.5},
            {"sequence": 102, "speed_mps": 30.0, "combined_slip": 0.9},
            {"sequence": 103, "speed_mps": 40.0, "combined_slip": 0.2},
        ]

        summary = summarize_section(samples, start_sequence=101, end_sequence=102)

        self.assertEqual(summary["start_sequence"], 101)
        self.assertEqual(summary["end_sequence"], 102)
        self.assertEqual(summary["packet_count"], 2)
        self.assertAlmostEqual(summary["top_speed_mps"], 30.0)
        self.assertAlmostEqual(summary["average_speed_mps"], 25.0)
        self.assertAlmostEqual(summary["peak_combined_slip"], 0.9)

    def test_store_round_trips_issue_markers_and_range_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session("Analysis")
            lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
            raw_packets = []
            decoded_packets = []
            samples = []
            for index, speed in enumerate((12.0, 24.0, 36.0), start=1):
                raw = encode_packet_for_test({"TimestampMS": index * 16, "PositionX": float(index), "Speed": speed})
                decoded = decode_packet(raw)
                sample = packet_to_live_fields(decoded, sequence=index, received_at_ms=index * 16)
                sample["lap_id"] = lap_id
                raw_packets.append(raw)
                decoded_packets.append(decoded)
                samples.append(sample)
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)
            markers = [
                {
                    "id": "marker-1",
                    "session_id": session_id,
                    "lap_id": lap_id,
                    "start_sequence": 1,
                    "end_sequence": 2,
                    "metric": "rear_combined_slip",
                    "severity": "critical",
                    "reason": "Rear combined slip is high.",
                    "ruleset_version": 1,
                    "confidence": 0.95,
                    "anchor_sequence": 2,
                    "issue_kind": "Rear combined slip",
                    "actual_value": 1.28,
                    "threshold_value": 1.15,
                    "threshold_operator": "gte",
                    "value_label": "Rear combined slip",
                    "value_unit": None,
                },
                {
                    "id": "marker-2",
                    "session_id": session_id,
                    "lap_id": None,
                    "start_sequence": 3,
                    "end_sequence": 3,
                    "metric": "engine_rpm",
                    "severity": "info",
                    "reason": "Limiter hit.",
                    "ruleset_version": 1,
                    "confidence": 0.75,
                    "anchor_sequence": None,
                    "issue_kind": None,
                    "actual_value": None,
                    "threshold_value": None,
                    "threshold_operator": None,
                    "value_label": None,
                    "value_unit": None,
                },
            ]

            store.insert_issue_markers(markers)

            self.assertEqual(store.issue_markers_for_lap(lap_id=lap_id), [markers[0]])
            self.assertEqual(store.issue_markers_for_lap(lap_id=None, session_id=session_id), [markers[1]])
            range_samples = store.samples_for_range(session_id, start_sequence=2, end_sequence=3, lap_id=lap_id)
            self.assertEqual([sample["sequence"] for sample in range_samples], [2, 3])
            raw_point = store.raw_packet_at_sequence(session_id, sequence=2)
            self.assertEqual(raw_point, raw_packets[1])


    def test_store_round_trips_uncertainty_and_deletes_replaced_lap_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session("Race control")
            lap_id = store.create_lap(session_id, lap_number=0, boundary_confidence="game_field")
            raw_packets = []
            decoded_packets = []
            samples = []
            for index, current_lap in enumerate((1.0, 2.0, 3.0), start=1):
                raw = encode_packet_for_test(
                    {
                        "TimestampMS": index * 16,
                        "CurrentLap": current_lap,
                        "CurrentRaceTime": current_lap,
                        "PositionX": float(index),
                        "Speed": 20.0,
                    }
                )
                decoded = decode_packet(raw)
                sample = packet_to_live_fields(decoded, sequence=index, received_at_ms=index * 16)
                sample["lap_id"] = lap_id
                if index == 2:
                    sample["uncertainty"] = "rewind"
                raw_packets.append(raw)
                decoded_packets.append(decoded)
                samples.append(sample)
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            persisted = store.samples_for_lap(lap_id)
            self.assertEqual([sample.get("uncertainty") for sample in persisted], [None, "rewind", None])

            store.insert_issue_markers(
                [
                    {
                        "id": "prefix-marker",
                        "session_id": session_id,
                        "lap_id": lap_id,
                        "start_sequence": 1,
                        "end_sequence": 1,
                        "metric": "combined_slip",
                        "severity": "warning",
                        "reason": "Preserved prefix marker",
                        "ruleset_version": 1,
                        "confidence": 0.8,
                    },
                    {
                        "id": "trimmed-marker",
                        "session_id": session_id,
                        "lap_id": lap_id,
                        "start_sequence": 2,
                        "end_sequence": 2,
                        "metric": "combined_slip",
                        "severity": "warning",
                        "reason": "Trimmed marker",
                        "ruleset_version": 1,
                        "confidence": 0.8,
                    },
                ]
            )

            deleted = store.delete_lap_samples_after_current_lap(lap_id, 1.0)

            self.assertEqual(deleted, 2)
            remaining = store.samples_for_lap(lap_id)
            self.assertEqual([sample["sequence"] for sample in remaining], [1])
            self.assertIsNone(store.raw_packet_at_sequence(session_id, sequence=2))
            with store.connect() as con:
                marker_ids = [
                    row["id"]
                    for row in con.execute(
                        "SELECT id FROM issue_markers WHERE lap_id = ? ORDER BY start_sequence",
                        (lap_id,),
                    ).fetchall()
                ]
            self.assertEqual(marker_ids, ["prefix-marker"])

    def test_packet_bridge_and_store_expose_overlay_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session("Overlay fields")
            lap_id = store.create_lap(session_id, lap_number=7, boundary_confidence="game_field")
            raw = encode_packet_for_test(
                {
                    "TimestampMS": 48,
                    "PositionX": 1.5,
                    "PositionY": 2.5,
                    "PositionZ": 3.5,
                    "Speed": 55.0,
                    "Accel": 210,
                    "Brake": 15,
                    "Steer": -22,
                    "TireCombinedSlipFrontLeft": 0.2,
                    "TireCombinedSlipFrontRight": 0.4,
                    "TireCombinedSlipRearLeft": 0.8,
                    "TireCombinedSlipRearRight": 0.6,
                    "TireTempFrontLeft": 88.0,
                    "TireTempFrontRight": 89.0,
                    "TireTempRearLeft": 90.0,
                    "TireTempRearRight": 91.0,
                    "NormalizedSuspensionTravelFrontLeft": 0.11,
                    "NormalizedSuspensionTravelFrontRight": 0.22,
                    "NormalizedSuspensionTravelRearLeft": 0.33,
                    "NormalizedSuspensionTravelRearRight": 0.44,
                    "CurrentEngineRpm": 7123.0,
                    "EngineMaxRpm": 8500.0,
                }
            )
            decoded = decode_packet(raw)
            sample = packet_to_live_fields(decoded, sequence=9, received_at_ms=1009)
            sample["lap_id"] = lap_id

            self.assertEqual(sample["speed_mps"], 55.0)
            self.assertEqual(sample["throttle"], 210)
            self.assertEqual(sample["brake"], 15)
            self.assertEqual(sample["steer"], -22)
            self.assertAlmostEqual(sample["combined_slip"], 0.8)
            self.assertAlmostEqual(sample["tire_temp_front_left"], 88.0)
            self.assertAlmostEqual(sample["tire_temp_front_right"], 89.0)
            self.assertAlmostEqual(sample["tire_temp_rear_left"], 90.0)
            self.assertAlmostEqual(sample["tire_temp_rear_right"], 91.0)
            self.assertAlmostEqual(sample["suspension_travel_front_left"], 0.11)
            self.assertAlmostEqual(sample["suspension_travel_front_right"], 0.22)
            self.assertAlmostEqual(sample["suspension_travel_rear_left"], 0.33)
            self.assertAlmostEqual(sample["suspension_travel_rear_right"], 0.44)
            self.assertAlmostEqual(sample["current_rpm"], 7123.0)
            self.assertAlmostEqual(sample["engine_max_rpm"], 8500.0)

            store.insert_packet_batch(session_id, [raw], [decoded], [sample])
            persisted = store.samples_for_range(session_id, start_sequence=9, end_sequence=9, lap_id=lap_id)
            self.assertEqual(len(persisted), 1)
            self.assertAlmostEqual(persisted[0]["combined_slip"], 0.8)
            self.assertAlmostEqual(persisted[0]["current_rpm"], 7123.0)

    def test_analyze_lap_persists_summary_and_enriched_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session("Analyze")
            lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
            raw_packets = []
            decoded_packets = []
            samples = []
            for index, values in enumerate(
                [
                    {"TimestampMS": 16, "PositionX": 1.0, "Speed": 20.0, "Accel": 255, "CurrentEngineRpm": 7900.0, "EngineMaxRpm": 8000.0},
                    {"TimestampMS": 32, "PositionX": 2.0, "Speed": 25.0, "Accel": 255, "CurrentEngineRpm": 7950.0, "EngineMaxRpm": 8000.0, "TireCombinedSlipRearLeft": 1.3},
                    {"TimestampMS": 48, "PositionX": 3.0, "Speed": 30.0, "Accel": 255, "CurrentEngineRpm": 7960.0, "EngineMaxRpm": 8000.0, "TireCombinedSlipRearRight": 1.25},
                ],
                start=1,
            ):
                raw = encode_packet_for_test(values)
                decoded = decode_packet(raw)
                sample = packet_to_live_fields(decoded, sequence=index, received_at_ms=index * 16)
                sample["lap_id"] = lap_id
                raw_packets.append(raw)
                decoded_packets.append(decoded)
                samples.append(sample)
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            result = analyze_lap(store, session_id=session_id, lap_id=lap_id)

            self.assertEqual(result["summary"]["packet_count"], 3)
            self.assertTrue(result["markers"])
            self.assertTrue(all(marker["session_id"] == session_id for marker in result["markers"]))
            self.assertTrue(all(marker["lap_id"] == lap_id for marker in result["markers"]))
            self.assertEqual(store.lap_summary(lap_id)["packet_count"], 3)
            stored_markers = store.issue_markers_for_lap(lap_id=lap_id)
            self.assertEqual(len(stored_markers), len(result["markers"]))

    def test_analyze_lap_replaces_stale_markers_for_same_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session("Reanalyze")
            lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
            raw_packets = []
            decoded_packets = []
            samples = []
            for index, values in enumerate(
                [
                    {"TimestampMS": 16, "PositionX": 1.0, "Speed": 20.0, "TireCombinedSlipRearLeft": 1.3},
                    {"TimestampMS": 32, "PositionX": 2.0, "Speed": 25.0, "TireCombinedSlipRearRight": 1.25},
                ],
                start=1,
            ):
                raw = encode_packet_for_test(values)
                decoded = decode_packet(raw)
                sample = packet_to_live_fields(decoded, sequence=index, received_at_ms=index * 16)
                sample["lap_id"] = lap_id
                raw_packets.append(raw)
                decoded_packets.append(decoded)
                samples.append(sample)
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            first_result = analyze_lap(store, session_id=session_id, lap_id=lap_id)
            self.assertTrue(first_result["markers"])

            with store.connect() as con:
                con.execute(
                    """
                    UPDATE lap_samples
                    SET combined_slip = ?, rear_combined_slip = ?
                    WHERE lap_id = ?
                    """,
                    (0.1, 0.1, lap_id),
                )

            second_result = analyze_lap(store, session_id=session_id, lap_id=lap_id)

            self.assertEqual(second_result["markers"], [])
            self.assertEqual(store.issue_markers_for_lap(lap_id=lap_id), [])


if __name__ == "__main__":
    unittest.main()
