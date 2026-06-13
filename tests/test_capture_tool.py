import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from telemetry_tracker import data_out

ROOT = Path(__file__).resolve().parents[1]


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def send_synthetic_packets(
    port: int,
    count: int,
    start_timestamp: int = 0,
    values: dict | None = None,
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for index in range(count):
            packet_values = {"TimestampMS": start_timestamp + index * 16}
            if values:
                packet_values.update(values)
            packet = data_out.encode_packet_for_test(packet_values)
            sock.sendto(packet, ("127.0.0.1", port))
            time.sleep(0.02)


def wait_for_capture_count(index_path: Path, expected_count: int, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if index_path.exists():
            try:
                payload = json.loads(index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                time.sleep(0.05)
                continue
            if len(payload.get("captures", [])) >= expected_count:
                return payload
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {expected_count} capture(s) in {index_path}")


class CaptureToolTests(unittest.TestCase):
    def test_help_mentions_setup_defaults(self):
        result = subprocess.run(
            [sys.executable, "tools/capture-data-out.py", "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("127.0.0.1", result.stdout)
        self.assertIn("5400", result.stdout)
        self.assertIn("5200", result.stdout)

    def test_no_packets_returns_actionable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = free_udp_port()
            result = subprocess.run(
                [
                    sys.executable,
                    "tools/capture-data-out.py",
                    "--duration",
                    "0.1",
                    "--port",
                    str(port),
                    "--output-dir",
                    tmp,
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No packets received", result.stderr)
        self.assertIn("Data Out", result.stderr)

    def test_reserved_port_is_rejected_before_listening(self):
        result = subprocess.run(
            [
                sys.executable,
                "tools/capture-data-out.py",
                "--duration",
                "0.1",
                "--port",
                "5201",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reserved range", result.stderr)

    def test_synthetic_udp_capture_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = free_udp_port()
            ready_file = Path(tmp) / "ready.txt"
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "tools/capture-data-out.py",
                    "--duration",
                    "1.5",
                    "--port",
                    str(port),
                    "--output-dir",
                    tmp,
                    "--label",
                    "unit",
                    "--socket-timeout",
                    "0.05",
                    "--ready-file",
                    str(ready_file),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            deadline = time.monotonic() + 5
            while not ready_file.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(ready_file.exists(), "listener did not signal readiness")
            send_synthetic_packets(port, 3)
            stdout, stderr = proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 0, stderr + stdout)

            telemetry = Path(tmp)
            latest = telemetry / "latest.json"
            self.assertTrue(latest.exists())
            latest_payload = json.loads(latest.read_text(encoding="utf-8"))
            capture_dir = Path(latest_payload["capture_dir"])
            self.assertTrue((capture_dir / "raw.bin").exists())
            self.assertTrue((capture_dir / "packets.csv").exists())
            self.assertTrue((capture_dir / "summary.json").exists())
            self.assertTrue((capture_dir / "manifest.json").exists())
            summary = json.loads((capture_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["packet_count"], 3)

    def test_stop_file_ends_open_capture_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = free_udp_port()
            root = Path(tmp)
            ready_file = root / "ready.txt"
            stop_file = root / "stop.txt"
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "tools/capture-data-out.py",
                    "--port",
                    str(port),
                    "--output-dir",
                    tmp,
                    "--label",
                    "stop-file",
                    "--socket-timeout",
                    "0.05",
                    "--ready-file",
                    str(ready_file),
                    "--stop-file",
                    str(stop_file),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            deadline = time.monotonic() + 5
            while not ready_file.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(ready_file.exists(), "listener did not signal readiness")
            send_synthetic_packets(port, 3)
            stop_file.write_text("stop\n", encoding="utf-8")
            stdout, stderr = proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 0, stderr + stdout)
            latest = root / "latest.json"
            self.assertTrue(latest.exists())
            capture_dir = Path(json.loads(latest.read_text(encoding="utf-8"))["capture_dir"])
            summary = json.loads((capture_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["packet_count"], 3)

    def test_continuous_capture_splits_idle_bursts(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = free_udp_port()
            root = Path(tmp)
            ready_file = root / "ready.txt"
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "tools/capture-data-out.py",
                    "--duration",
                    "1.0",
                    "--port",
                    str(port),
                    "--output-dir",
                    tmp,
                    "--label",
                    "continuous",
                    "--socket-timeout",
                    "0.02",
                    "--continuous",
                    "--idle-split-seconds",
                    "0.12",
                    "--ready-file",
                    str(ready_file),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            deadline = time.monotonic() + 5
            while not ready_file.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(ready_file.exists(), "listener did not signal readiness")

            send_synthetic_packets(port, 2)
            time.sleep(0.25)
            send_synthetic_packets(port, 3, start_timestamp=1000)
            stdout, stderr = proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 0, stderr + stdout)

            index = json.loads((root / "capture-index.json").read_text(encoding="utf-8"))
            captures = index["captures"]
            self.assertEqual(len(captures), 2)
            packet_counts = [
                json.loads(Path(capture["summary_path"]).read_text(encoding="utf-8"))[
                    "packet_count"
                ]
                for capture in captures
            ]
            self.assertEqual(packet_counts, [2, 3])
            self.assertTrue((root / "latest.json").exists())

    def test_continuous_capture_splits_when_inactive_packets_continue(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = free_udp_port()
            root = Path(tmp)
            ready_file = root / "ready.txt"
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "tools/capture-data-out.py",
                    "--duration",
                    "1.2",
                    "--port",
                    str(port),
                    "--output-dir",
                    tmp,
                    "--label",
                    "continuous-inactive",
                    "--socket-timeout",
                    "0.02",
                    "--continuous",
                    "--idle-split-seconds",
                    "0.12",
                    "--ready-file",
                    str(ready_file),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            deadline = time.monotonic() + 5
            while not ready_file.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(ready_file.exists(), "listener did not signal readiness")

            inactive = {
                "IsRaceOn": 0,
                "Speed": 0.0,
                "EngineMaxRpm": 0.0,
                "CarPerformanceIndex": 0,
            }
            send_synthetic_packets(port, 2)
            send_synthetic_packets(port, 10, start_timestamp=1000, values=inactive)
            send_synthetic_packets(port, 3, start_timestamp=2000)
            stdout, stderr = proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 0, stderr + stdout)
            self.assertIn("Ignored", stdout)

            index = json.loads((root / "capture-index.json").read_text(encoding="utf-8"))
            captures = index["captures"]
            self.assertEqual(len(captures), 2)
            packet_counts = [
                json.loads(Path(capture["summary_path"]).read_text(encoding="utf-8"))[
                    "packet_count"
                ]
                for capture in captures
            ]
            self.assertEqual(packet_counts, [2, 3])
            reasons = [capture["metadata"]["segment_reason"] for capture in captures]
            self.assertEqual(reasons[0], "active-idle-split")

    def test_capture_session_start_status_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            port = free_udp_port()
            session_file = root / "capture-session.json"
            start = subprocess.run(
                [
                    sys.executable,
                    "tools/capture-session.py",
                    "start",
                    "--port",
                    str(port),
                    "--output-dir",
                    tmp,
                    "--label",
                    "session",
                    "--session-file",
                    str(session_file),
                    "--ready-timeout",
                    "5",
                    "--socket-timeout",
                    "0.05",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(start.returncode, 0, start.stderr + start.stdout)
            self.assertTrue(session_file.exists())
            session = json.loads(session_file.read_text(encoding="utf-8"))
            self.assertEqual(session["status"], "running")
            self.assertIn("Listening on", start.stdout)

            status = subprocess.run(
                [
                    sys.executable,
                    "tools/capture-session.py",
                    "status",
                    "--session-file",
                    str(session_file),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
            self.assertIn("running", status.stdout)

            send_synthetic_packets(port, 3)

            stop = subprocess.run(
                [
                    sys.executable,
                    "tools/capture-session.py",
                    "stop",
                    "--session-file",
                    str(session_file),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(stop.returncode, 0, stop.stderr + stop.stdout)
            self.assertIn("Capture stopped", stop.stdout)
            session = json.loads(session_file.read_text(encoding="utf-8"))
            self.assertEqual(session["status"], "stopped")
            latest = root / "latest.json"
            self.assertTrue(latest.exists())
            capture_dir = Path(json.loads(latest.read_text(encoding="utf-8"))["capture_dir"])
            summary = json.loads((capture_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["packet_count"], 3)

            status_after = subprocess.run(
                [
                    sys.executable,
                    "tools/capture-session.py",
                    "status",
                    "--session-file",
                    str(session_file),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(status_after.returncode, 0)
            self.assertIn("stopped", status_after.stdout)

    def test_capture_session_continuous_new_mark_analyzed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            port = free_udp_port()
            session_file = root / "capture-session.json"
            start = subprocess.run(
                [
                    sys.executable,
                    "tools/capture-session.py",
                    "start-continuous",
                    "--port",
                    str(port),
                    "--output-dir",
                    tmp,
                    "--label",
                    "session-continuous",
                    "--session-file",
                    str(session_file),
                    "--ready-timeout",
                    "5",
                    "--socket-timeout",
                    "0.02",
                    "--idle-split-seconds",
                    "0.12",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(start.returncode, 0, start.stderr + start.stdout)
            self.assertIn("Continuous capture listening", start.stdout)

            try:
                send_synthetic_packets(port, 2)
                index_path = root / "capture-index.json"
                wait_for_capture_count(index_path, 1)
                send_synthetic_packets(port, 1, start_timestamp=1000)
                wait_for_capture_count(index_path, 2)

                state_path = root / "analysis-state.json"
                first_new = subprocess.run(
                    [
                        sys.executable,
                        "tools/capture-session.py",
                        "new",
                        "--capture-index",
                        str(index_path),
                        "--analysis-state",
                        str(state_path),
                        "--mark-analyzed",
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(first_new.returncode, 0, first_new.stderr + first_new.stdout)
                first_payload = json.loads(first_new.stdout)
                self.assertEqual(first_payload["new_count"], 2)
                self.assertTrue(first_payload["marked_analyzed"])
                self.assertTrue(state_path.exists())

                second_new = subprocess.run(
                    [
                        sys.executable,
                        "tools/capture-session.py",
                        "new",
                        "--capture-index",
                        str(index_path),
                        "--analysis-state",
                        str(state_path),
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(second_new.returncode, 0, second_new.stderr + second_new.stdout)
                second_payload = json.loads(second_new.stdout)
                self.assertEqual(second_payload["new_count"], 0)
            finally:
                subprocess.run(
                    [
                        sys.executable,
                        "tools/capture-session.py",
                        "stop",
                        "--session-file",
                        str(session_file),
                        "--wait-timeout",
                        "5",
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                )

    def test_capture_session_new_classifies_and_recommends_useful_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summaries = {
                "017": {
                    "packet_count": 3931,
                    "duration_seconds": 41.391,
                    "top_speed_mph": 21.2,
                    "lap_number": 0,
                    "best_lap": 0.0,
                    "last_lap": 0.0,
                    "current_lap": 0.0,
                },
                "018": {
                    "packet_count": 24069,
                    "duration_seconds": 334.813,
                    "top_speed_mph": 239.351,
                    "lap_number": 4,
                    "best_lap": 59.454395,
                    "last_lap": 59.454395,
                    "current_lap": 60.740478,
                },
                "019": {
                    "packet_count": 371,
                    "duration_seconds": 7.0,
                    "top_speed_mph": 0.009,
                    "lap_number": 0,
                    "best_lap": 0.0,
                    "last_lap": 0.0,
                    "current_lap": 0.0,
                },
            }
            captures = []
            for segment, summary in summaries.items():
                capture_dir = root / segment
                capture_dir.mkdir()
                summary_path = capture_dir / "summary.json"
                summary_path.write_text(json.dumps(summary), encoding="utf-8")
                manifest_path = capture_dir / "manifest.json"
                manifest_path.write_text("{}", encoding="utf-8")
                captures.append(
                    {
                        "manifest_path": str(manifest_path),
                        "capture_dir": str(capture_dir),
                        "summary_path": str(summary_path),
                        "raw_path": str(capture_dir / "raw.bin"),
                        "packets_csv_path": str(capture_dir / "packets.csv"),
                        "packet_count": summary["packet_count"],
                        "created_utc": "2026-05-30T22:00:00+00:00",
                        "metadata": {"segment_index": int(segment)},
                    }
                )
            index_path = root / "capture-index.json"
            state_path = root / "analysis-state.json"
            index_path.write_text(json.dumps({"captures": captures}), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/capture-session.py",
                    "new",
                    "--capture-index",
                    str(index_path),
                    "--analysis-state",
                    str(state_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["new_count"], 3)
            self.assertEqual(payload["useful_count"], 1)
            self.assertEqual(payload["maybe_count"], 0)
            self.assertEqual(payload["ignored_count"], 2)
            self.assertEqual(payload["recommended_manifest_path"], str(root / "018" / "manifest.json"))
            labels = [
                capture["segment_classification"]["label"]
                for capture in payload["captures"]
            ]
            self.assertEqual(labels, ["staging", "useful", "tail"])


if __name__ == "__main__":
    unittest.main()
