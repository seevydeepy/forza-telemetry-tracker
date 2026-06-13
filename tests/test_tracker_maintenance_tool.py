import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from telemetry_tracker.packet_bridge import decode_packet, encode_packet_for_test, packet_to_live_fields
from telemetry_tracker.storage import TelemetryStore


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "maintain-telemetry-db.py"


def _insert_prunable_packet(store: TelemetryStore, session_id: str) -> None:
    raw = encode_packet_for_test(
        {
            "IsRaceOn": 0,
            "TimestampMS": 16,
            "LapNumber": 0,
            "CurrentLap": 0.0,
            "CurrentRaceTime": 0.0,
        }
    )
    decoded = decode_packet(raw)
    sample = packet_to_live_fields(decoded, sequence=1, received_at_ms=16)
    store.insert_packet_batch(session_id, [raw], [decoded], [sample])


class TelemetryMaintenanceToolTests(unittest.TestCase):
    def test_dry_run_reports_prunable_rows_without_deleting(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "telemetry_tracker.sqlite3"
            store = TelemetryStore(db_path)
            store.migrate()
            session_id = store.create_session(label="CLI dry-run")
            _insert_prunable_packet(store, session_id)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--db",
                    str(db_path),
                    "--dry-run",
                    "--vacuum",
                    "always",
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["eligible_prunable_samples_before"], 1)
            self.assertEqual(payload["prune"]["target_sample_count"], 1)
            self.assertEqual(payload["prune"]["deleted_sample_count"], 0)
            self.assertTrue(payload["vacuum"]["would_run"])
            self.assertEqual(store.count_prunable_unassigned_non_race_telemetry(), 1)

    def test_prune_run_deletes_matching_samples_and_packets(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "telemetry_tracker.sqlite3"
            store = TelemetryStore(db_path)
            store.migrate()
            session_id = store.create_session(label="CLI prune")
            _insert_prunable_packet(store, session_id)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--db",
                    str(db_path),
                    "--vacuum",
                    "off",
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["dry_run"])
            self.assertEqual(payload["prune"]["deleted_sample_count"], 1)
            self.assertEqual(payload["prune"]["deleted_packet_count"], 1)
            self.assertEqual(payload["eligible_prunable_samples_after"], 0)
            with store.connect() as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM lap_samples").fetchone()[0], 0)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM packet_blobs").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
