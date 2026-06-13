import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from importlib import util
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tools" / "run-telemetry-tracker.py"


def _load_runner_module():
    spec = util.spec_from_file_location("run_telemetry_tracker_for_test", RUNNER_PATH)
    module = util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TrackerRunnerTests(unittest.TestCase):
    def test_runner_help_mentions_host_port_and_db(self):
        result = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--host", result.stdout)
        self.assertIn("--port", result.stdout)
        self.assertIn("--db", result.stdout)
        self.assertIn("Forza Telemetry Tracker", result.stdout)

    def test_runner_enables_udp_listener_lifespan_for_local_app(self):
        runner = _load_runner_module()
        app = object()
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "telemetry_tracker.sqlite3"
            argv = [
                "run-telemetry-tracker.py",
                "--host",
                "127.0.0.2",
                "--port",
                "9876",
                "--db",
                str(db_path),
            ]

            with (
                patch.object(sys, "argv", argv),
                patch.object(
                    runner,
                    "_listener_binding_from_db",
                    return_value=runner.PortBinding("UDP", "127.0.0.1", 5400, "Forza UDP listener"),
                ),
                patch.object(runner, "find_port_conflicts", return_value=[]),
                patch.object(runner, "create_app", return_value=app) as create_app,
                patch.object(runner.uvicorn, "run") as uvicorn_run,
            ):
                result = runner.main()

        self.assertEqual(result, 0)
        create_app.assert_called_once_with(
            db_path=db_path,
            start_udp_listener=True,
            refresh_car_catalog=True,
            refresh_track_catalog=True,
        )
        uvicorn_run.assert_called_once_with(app, host="127.0.0.2", port=9876)

    def test_runner_exits_cleanly_when_user_declines_to_kill_conflicting_process(self):
        runner = _load_runner_module()
        udp_binding = runner.PortBinding("UDP", "127.0.0.1", 5400, "Forza UDP listener")
        conflict = runner.ProcessConflict(
            binding=udp_binding,
            pid=12156,
            process_name="python",
            command_line="python tools/run-telemetry-tracker.py --port 8766",
        )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "telemetry_tracker.sqlite3"
            argv = [
                "run-telemetry-tracker.py",
                "--host",
                "127.0.0.1",
                "--port",
                "8765",
                "--db",
                str(db_path),
            ]
            stdout = StringIO()

            with (
                patch.object(sys, "argv", argv),
                patch.object(runner, "_listener_binding_from_db", return_value=udp_binding),
                patch.object(runner, "find_port_conflicts", return_value=[conflict]),
                patch("builtins.input", return_value=""),
                patch.object(runner, "kill_process_tree") as kill_process_tree,
                patch.object(runner, "create_app") as create_app,
                patch.object(runner.uvicorn, "run") as uvicorn_run,
                redirect_stdout(stdout),
            ):
                result = runner.main()

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn("Port conflict detected", output)
        self.assertIn("127.0.0.1:5400", output)
        self.assertIn("PID 12156", output)
        kill_process_tree.assert_not_called()
        create_app.assert_not_called()
        uvicorn_run.assert_not_called()

    def test_runner_kills_approved_conflicting_processes_once_then_starts(self):
        runner = _load_runner_module()
        app = object()
        http_binding = runner.PortBinding("TCP", "127.0.0.1", 8765, "HTTP site")
        udp_binding = runner.PortBinding("UDP", "127.0.0.1", 5400, "Forza UDP listener")
        conflicts = [
            runner.ProcessConflict(
                binding=http_binding,
                pid=12156,
                process_name="python",
                command_line="python tools/run-telemetry-tracker.py --port 8766",
            ),
            runner.ProcessConflict(
                binding=udp_binding,
                pid=12156,
                process_name="python",
                command_line="python tools/run-telemetry-tracker.py --port 8766",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "telemetry_tracker.sqlite3"
            argv = [
                "run-telemetry-tracker.py",
                "--host",
                "127.0.0.1",
                "--port",
                "8765",
                "--db",
                str(db_path),
            ]
            stdout = StringIO()

            with (
                patch.object(sys, "argv", argv),
                patch.object(runner, "_listener_binding_from_db", return_value=udp_binding),
                patch.object(runner, "find_port_conflicts", return_value=conflicts) as find_conflicts,
                patch("builtins.input", return_value="y"),
                patch.object(runner, "kill_process_tree") as kill_process_tree,
                patch.object(runner, "wait_for_bindings_to_clear") as wait_for_bindings_to_clear,
                patch.object(runner, "create_app", return_value=app) as create_app,
                patch.object(runner.uvicorn, "run") as uvicorn_run,
                redirect_stdout(stdout),
            ):
                result = runner.main()

        self.assertEqual(result, 0)
        find_conflicts.assert_called_once_with([http_binding, udp_binding])
        kill_process_tree.assert_called_once_with(12156)
        wait_for_bindings_to_clear.assert_called_once_with([http_binding, udp_binding])
        create_app.assert_called_once_with(
            db_path=db_path,
            start_udp_listener=True,
            refresh_car_catalog=True,
            refresh_track_catalog=True,
        )
        uvicorn_run.assert_called_once_with(app, host="127.0.0.1", port=8765)


if __name__ == "__main__":
    unittest.main()
