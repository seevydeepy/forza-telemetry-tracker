import logging
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from telemetry_tracker.app_paths import default_desktop_paths
from telemetry_tracker.desktop_launcher import (
    DesktopBackend,
    allocate_local_port,
    configure_desktop_logging,
    desktop_url,
    ensure_udp_port_available,
)


class DesktopLauncherTests(unittest.TestCase):
    def test_allocate_local_port_returns_bindable_loopback_port(self):
        port = allocate_local_port()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))

    def test_desktop_url_uses_loopback_port(self):
        self.assertEqual(desktop_url(49152), "http://127.0.0.1:49152")

    def test_backend_builds_app_with_runtime_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = default_desktop_paths(resource_base=Path(tmp) / "resources", user_data_base=Path(tmp) / "data")
            backend = DesktopBackend(paths=paths, http_port=45678)
            with patch("telemetry_tracker.desktop_launcher.create_app") as create_app:
                app = object()
                create_app.return_value = app
                self.assertIs(backend.build_app(), app)
        create_app.assert_called_once_with(
            runtime_paths=paths,
            start_udp_listener=True,
            refresh_car_catalog=True,
            refresh_track_catalog=True,
            request_shutdown=backend.request_process_shutdown,
        )

    def test_backend_start_and_stop_delegate_to_uvicorn_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = default_desktop_paths(resource_base=Path(tmp) / "resources", user_data_base=Path(tmp) / "data")
            backend = DesktopBackend(paths=paths, http_port=45678)
            fake_server = MagicMock()
            fake_config = MagicMock()
            with (
                patch.object(backend, "build_app", return_value=object()),
                patch("telemetry_tracker.desktop_launcher.uvicorn.Config", return_value=fake_config) as config_class,
                patch("telemetry_tracker.desktop_launcher.uvicorn.Server", return_value=fake_server),
                patch("telemetry_tracker.desktop_launcher.threading.Thread") as thread_class,
                patch.object(backend, "wait_until_ready"),
                patch("telemetry_tracker.desktop_launcher.ensure_udp_port_available"),
                patch("telemetry_tracker.desktop_launcher.configure_desktop_logging"),
            ):
                thread = MagicMock()
                thread_class.return_value = thread
                backend.start()
                backend.stop()
        thread.start.assert_called_once()
        self.assertTrue(fake_server.should_exit)
        config_class.assert_called_once()
        self.assertIsNone(config_class.call_args.kwargs["log_config"])

    def test_udp_conflict_cancel_raises_before_backend_starts(self):
        from telemetry_tracker.port_conflicts import PortBinding, ProcessConflict

        binding = PortBinding("UDP", "127.0.0.1", 5400, "Forza UDP listener")
        conflict = ProcessConflict(binding, 1234, "python.exe", command_line="old tracker")
        with (
            patch("telemetry_tracker.desktop_launcher.find_port_conflicts", return_value=[conflict]),
            patch("telemetry_tracker.desktop_launcher.kill_process_tree") as kill,
        ):
            with self.assertRaisesRegex(RuntimeError, "cancelled"):
                ensure_udp_port_available(binding, prompt_user=lambda message: False)
        kill.assert_not_called()

    def test_udp_conflict_user_approval_kills_and_waits(self):
        from telemetry_tracker.port_conflicts import PortBinding, ProcessConflict

        binding = PortBinding("UDP", "127.0.0.1", 5400, "Forza UDP listener")
        conflict = ProcessConflict(binding, 1234, "python.exe", command_line="old tracker")
        with (
            patch("telemetry_tracker.desktop_launcher.find_port_conflicts", return_value=[conflict]),
            patch("telemetry_tracker.desktop_launcher.kill_process_tree") as kill,
            patch("telemetry_tracker.desktop_launcher.wait_for_bindings_to_clear") as wait,
        ):
            ensure_udp_port_available(binding, prompt_user=lambda message: True)
        kill.assert_called_once_with(1234)
        wait.assert_called_once_with([binding])

    def test_desktop_logging_writes_app_log(self):
        root = logging.getLogger()
        saved_handlers = root.handlers[:]
        saved_level = root.level
        uvicorn_logger = logging.getLogger("uvicorn")
        saved_uvicorn_handlers = uvicorn_logger.handlers[:]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                paths = default_desktop_paths(resource_base=Path(tmp) / "resources", user_data_base=Path(tmp) / "data")
                configure_desktop_logging(paths)
                logging.getLogger("telemetry_tracker.desktop").info("desktop log smoke")
                added_root = [h for h in root.handlers if h not in saved_handlers]
                added_uvicorn = [h for h in uvicorn_logger.handlers if h not in saved_uvicorn_handlers]
                for handler in added_root + added_uvicorn:
                    handler.flush()
                    handler.close()
                self.assertIn("desktop log smoke", (paths.logs_dir / "app.log").read_text(encoding="utf-8"))
        finally:
            root.handlers = saved_handlers
            root.setLevel(saved_level)
            uvicorn_logger.handlers = saved_uvicorn_handlers

    def test_main_uses_smoke_mode_when_requested(self):
        with (
            patch("telemetry_tracker.desktop_launcher.sys.argv", ["ForzaTelemetryTracker.exe", "--smoke-http-only"]),
            patch("telemetry_tracker.desktop_launcher.run_smoke_http_only", return_value=0) as run_smoke,
        ):
            from telemetry_tracker.desktop_launcher import main

            result = main()
        self.assertEqual(result, 0)
        run_smoke.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
