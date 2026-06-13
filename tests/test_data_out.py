import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from telemetry_tracker import data_out

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "parse-data-out.py"


class DataOutTests(unittest.TestCase):
    def test_schema_matches_declared_packet_size(self):
        offset = 0
        for name, type_name, declared_offset in data_out.SCHEMA:
            self.assertEqual(declared_offset, offset, name)
            offset += data_out.TYPE_SIZES[type_name]
        self.assertEqual(offset, data_out.PACKET_SIZE)
        self.assertEqual(data_out.PACKET_STRUCT.size, data_out.PACKET_SIZE)

    def test_decode_synthetic_packet(self):
        packet = data_out.encode_packet_for_test(
            {
                "TimestampMS": 1000,
                "CurrentEngineRpm": 7200.0,
                "Speed": 44.0,
                "CarClass": 5,
                "CarPerformanceIndex": 900,
                "DrivetrainType": 1,
                "Accel": 255,
                "Brake": 12,
                "Gear": 5,
                "Steer": -20,
                "TireCombinedSlipRearRight": 1.25,
            }
        )
        self.assertEqual(len(packet), 324)
        decoded = data_out.decode_packet(packet)
        self.assertEqual(decoded["IsRaceOn"], 1)
        self.assertEqual(decoded["TimestampMS"], 1000)
        self.assertAlmostEqual(decoded["CurrentEngineRpm"], 7200.0)
        self.assertAlmostEqual(decoded["Speed"], 44.0)
        self.assertEqual(decoded["CarClass"], 5)
        self.assertEqual(decoded["CarPerformanceIndex"], 900)
        self.assertEqual(decoded["DrivetrainType"], 1)
        self.assertEqual(decoded["Accel"], 255)
        self.assertEqual(decoded["Brake"], 12)
        self.assertEqual(decoded["Gear"], 5)
        self.assertEqual(decoded["Steer"], -20)
        self.assertAlmostEqual(decoded["TireCombinedSlipRearRight"], 1.25)

    def test_decode_rejects_bad_length(self):
        with self.assertRaisesRegex(ValueError, "324 bytes"):
            data_out.decode_packet(b"short")

    def test_summary_reports_useful_metrics(self):
        packets = [
            data_out.decode_packet(
                data_out.encode_packet_for_test(
                    {
                        "TimestampMS": index * 16,
                        "Speed": 20.0 + index,
                        "CurrentEngineRpm": 7900.0,
                        "Accel": 255,
                        "NormalizedSuspensionTravelFrontLeft": 0.96 if index == 1 else 0.3,
                        "TireCombinedSlipFrontLeft": 0.2,
                        "TireCombinedSlipRearRight": 1.4 if index == 2 else 0.1,
                    }
                )
            )
            for index in range(3)
        ]
        summary = data_out.summarize_packets(packets)
        self.assertEqual(summary["packet_count"], 3)
        self.assertEqual(summary["active_packet_count"], 3)
        self.assertEqual(summary["car_class_label"], "S1")
        self.assertEqual(summary["car_performance_index"], 800)
        self.assertEqual(summary["car_class_pi_cap"], 800)
        self.assertEqual(summary["pi_to_class_cap_delta"], 0)
        self.assertEqual(summary["drivetrain_label"], "AWD")
        self.assertGreater(summary["top_speed_mph"], 45)
        self.assertEqual(summary["bottoming_events"], 1)
        self.assertEqual(summary["limiter_samples"], 3)
        self.assertAlmostEqual(summary["peak_rear_combined_slip"], 1.4)
        self.assertEqual(summary["tire_temp_unit"], "raw_game_value_unit_unverified")
        self.assertIn("segment_classification", summary)

    def test_segment_classification_labels_useful_staging_and_tail(self):
        useful = data_out.classify_summary(
            {
                "packet_count": 24069,
                "duration_seconds": 334.813,
                "top_speed_mph": 239.351,
                "lap_number": 4,
                "best_lap": 59.454,
                "last_lap": 59.454,
                "current_lap": 60.740,
            }
        )
        self.assertEqual(useful["label"], "useful")
        self.assertIn("lap fields present", useful["reasons"])

        staging = data_out.classify_summary(
            {
                "packet_count": 3931,
                "duration_seconds": 41.391,
                "top_speed_mph": 21.2,
                "lap_number": 0,
                "best_lap": 0.0,
                "last_lap": 0.0,
                "current_lap": 0.0,
            }
        )
        self.assertEqual(staging["label"], "staging")

        tail = data_out.classify_summary(
            {
                "packet_count": 371,
                "duration_seconds": 7.0,
                "top_speed_mph": 0.009,
                "lap_number": 0,
                "best_lap": 0.0,
                "last_lap": 0.0,
                "current_lap": 0.0,
            }
        )
        self.assertEqual(tail["label"], "tail")

    def test_summary_uses_active_packets_for_car_metadata(self):
        active = data_out.decode_packet(
            data_out.encode_packet_for_test(
                {
                    "IsRaceOn": 1,
                    "TimestampMS": 1000,
                    "CarClass": 3,
                    "CarPerformanceIndex": 700,
                    "DrivetrainType": 2,
                    "Speed": 40.0,
                }
            )
        )
        inactive = data_out.decode_packet(
            data_out.encode_packet_for_test(
                {
                    "IsRaceOn": 0,
                    "TimestampMS": 2000,
                    "CarClass": 0,
                    "CarPerformanceIndex": 0,
                    "DrivetrainType": 0,
                    "Speed": 0.0,
                    "EngineMaxRpm": 0.0,
                }
            )
        )
        summary = data_out.summarize_packets([active, inactive])
        self.assertEqual(summary["packet_count"], 2)
        self.assertEqual(summary["active_packet_count"], 1)
        self.assertEqual(summary["car_class_label"], "A")
        self.assertEqual(summary["car_performance_index"], 700)
        self.assertEqual(summary["drivetrain_label"], "AWD")

    def test_summary_reports_fh6_r_class_metadata(self):
        packet = data_out.decode_packet(
            data_out.encode_packet_for_test(
                {
                    "CarClass": 6,
                    "CarPerformanceIndex": 952,
                    "DrivetrainType": 1,
                }
            )
        )
        summary = data_out.summarize_packets([packet])
        self.assertEqual(summary["car_class_label"], "R")
        self.assertEqual(summary["car_class_pi_min"], 901)
        self.assertEqual(summary["car_class_pi_cap"], 998)
        self.assertEqual(summary["pi_to_class_cap_delta"], 46)

    def test_write_capture_artifacts_and_latest_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture_dir = root / "capture"
            raw_packets = [
                data_out.encode_packet_for_test({"TimestampMS": 0}),
                data_out.encode_packet_for_test({"TimestampMS": 16, "Speed": 50.0}),
            ]
            manifest = data_out.write_capture_artifacts(
                capture_dir, raw_packets, {"label": "unit"}
            )
            self.assertTrue((capture_dir / "raw.bin").exists())
            self.assertTrue((capture_dir / "packets.csv").exists())
            self.assertTrue((capture_dir / "summary.json").exists())
            self.assertTrue((capture_dir / "manifest.json").exists())
            self.assertEqual(manifest["packet_count"], 2)

            latest = root / "latest.json"
            data_out.write_latest_pointer(latest, capture_dir / "manifest.json")
            payload = json.loads(latest.read_text(encoding="utf-8"))
            self.assertEqual(payload["packet_count"], 2)
            self.assertTrue(Path(payload["raw_path"]).exists())

            latest_result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--latest",
                    str(latest),
                    "--output-dir",
                    str(root / "latest-output"),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(latest_result.returncode, 0, latest_result.stderr)
            latest_summary = json.loads(
                (root / "latest-output" / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(latest_summary["packet_count"], 2)

    def test_parse_cli_outputs_summary_and_csv(self):
        cli = CLI
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw.bin"
            raw.write_bytes(
                b"".join(
                    data_out.encode_packet_for_test({"TimestampMS": index * 16})
                    for index in range(3)
                )
            )
            result = subprocess.run(
                [sys.executable, str(cli), "--input", str(raw), "--output-dir", str(root)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "packets.csv").exists())
            summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["packet_count"], 3)

            bad = root / "bad.bin"
            bad.write_bytes(b"1234567890")
            bad_result = subprocess.run(
                [sys.executable, str(cli), "--input", str(bad), "--output-dir", str(root)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(bad_result.returncode, 0)
            self.assertIn("324", bad_result.stderr)


if __name__ == "__main__":
    unittest.main()
