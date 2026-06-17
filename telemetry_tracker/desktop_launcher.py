"""Windows desktop launcher for the Forza Telemetry Tracker."""
from __future__ import annotations

import ctypes
import logging
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import uvicorn

from telemetry_tracker.app import _settings_payload, create_app
from telemetry_tracker.app_paths import DesktopPaths, default_desktop_paths
from telemetry_tracker.local_file_selection import LocalFileSelectionRegistry
from telemetry_tracker.port_conflicts import (
    PortBinding,
    find_port_conflicts,
    kill_process_tree,
    wait_for_bindings_to_clear,
)
from telemetry_tracker.storage import TelemetryStore

DEFAULT_HTTP_HOST = "127.0.0.1"
BACKEND_READY_TIMEOUT_SECONDS = 20.0


def load_webview():
    try:
        import webview  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("pywebview is required for the desktop launcher") from exc
    return webview


def allocate_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((DEFAULT_HTTP_HOST, 0))
        return int(sock.getsockname()[1])


def desktop_url(port: int) -> str:
    return f"http://{DEFAULT_HTTP_HOST}:{int(port)}"


def configure_desktop_logging(paths: DesktopPaths) -> None:
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(paths.logs_dir / "app.log", encoding="utf-8")],
        force=True,
    )
    backend_handler = logging.FileHandler(paths.logs_dir / "backend.log", encoding="utf-8")
    logging.getLogger("uvicorn").addHandler(backend_handler)


def listener_binding_from_paths(paths: DesktopPaths) -> PortBinding:
    store = TelemetryStore(paths.database)
    store.migrate()
    settings = _settings_payload(store)
    return PortBinding("UDP", str(settings["udp_host"]), int(settings["udp_port"]), "Forza UDP listener")


def format_conflict_message(conflicts: list) -> str:
    lines = [
        "The Forza UDP listener port is already in use.",
        "Close the other process, or allow this app to stop it before continuing.",
    ]
    for conflict in conflicts:
        line = f"{conflict.binding.protocol.upper()} {conflict.binding.host}:{conflict.binding.port} is owned by PID {conflict.pid} {conflict.process_name}".strip()
        lines.append(line)
        if conflict.command_line:
            lines.append(conflict.command_line)
    return "\n".join(lines)


def message_box_yes_no(message: str) -> bool:
    if os.name != "nt":
        return False
    MB_ICONWARNING = 0x30
    MB_YESNO = 0x04
    IDYES = 6
    result = ctypes.windll.user32.MessageBoxW(None, message, "Forza Telemetry Tracker", MB_ICONWARNING | MB_YESNO)
    return result == IDYES


def ensure_udp_port_available(
    binding: PortBinding,
    *,
    prompt_user=message_box_yes_no,
) -> None:
    conflicts = find_port_conflicts([binding])
    if not conflicts:
        return
    if not prompt_user(format_conflict_message(conflicts)):
        raise RuntimeError("Tracker startup cancelled because the UDP listener port is in use.")
    killed: set[int] = set()
    for conflict in conflicts:
        if conflict.pid > 0 and conflict.pid not in killed:
            kill_process_tree(conflict.pid)
            killed.add(conflict.pid)
    wait_for_bindings_to_clear([binding])


@dataclass
class DesktopBackend:
    paths: DesktopPaths
    http_port: int
    http_host: str = DEFAULT_HTTP_HOST
    local_file_selection_registry: LocalFileSelectionRegistry = field(default_factory=LocalFileSelectionRegistry)
    _server: uvicorn.Server | None = field(default=None, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def build_app(self):
        return create_app(
            runtime_paths=self.paths,
            start_udp_listener=True,
            refresh_car_catalog=True,
            refresh_track_catalog=True,
            local_file_selection_registry=self.local_file_selection_registry,
        )

    def start(self) -> None:
        self.paths.ensure_user_directories()
        configure_desktop_logging(self.paths)
        ensure_udp_port_available(listener_binding_from_paths(self.paths))
        config = uvicorn.Config(
            self.build_app(),
            host=self.http_host,
            port=self.http_port,
            log_level="info",
            access_log=False,
            log_config=None,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run,
            name="forza-tracker-backend",
            daemon=True,
        )
        self._thread.start()
        self.wait_until_ready()

    def wait_until_ready(self) -> None:
        deadline = time.monotonic() + BACKEND_READY_TIMEOUT_SECONDS
        url = f"{desktop_url(self.http_port)}/api/status"
        while time.monotonic() < deadline:
            try:
                if httpx.get(url, timeout=1.0).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise RuntimeError("Forza Telemetry Tracker backend did not become ready")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            self._thread = None
        self._server = None


class DesktopBridge:
    def __init__(
        self,
        webview_module=None,
        local_file_selection_registry: LocalFileSelectionRegistry | None = None,
    ) -> None:
        self._webview = webview_module
        self._local_file_selection_registry = local_file_selection_registry or LocalFileSelectionRegistry()
        self._window = None

    def bind_window(self, window) -> None:
        self._window = window

    def _webview_module(self):
        if self._webview is None:
            self._webview = load_webview()
        return self._webview

    def _dialog_window(self):
        if self._window is not None:
            return self._window
        windows = getattr(self._webview_module(), "windows", None)
        if isinstance(windows, list) and windows:
            return windows[0]
        return None

    def _dialog_directory(self, current_path: str | None = None) -> str:
        if not current_path:
            return ""
        try:
            candidate = Path(str(current_path)).expanduser()
            if candidate.exists() and candidate.is_dir():
                return str(candidate)
            if candidate.exists() and candidate.is_file():
                return str(candidate.parent)
        except OSError:
            return ""
        return ""

    def _choose_folder(self, current_path: str | None = None) -> str | None:
        window = self._dialog_window()
        if window is None:
            return None

        selected = window.create_file_dialog(
            self._webview_module().FOLDER_DIALOG,
            directory=self._dialog_directory(current_path),
            allow_multiple=False,
        )
        if not selected:
            return None
        return str(selected[0])

    def choose_fh6_install_folder(self, current_path: str | None = None) -> str | None:
        return self._choose_folder(current_path)

    def choose_export_folder(self, current_path: str | None = None) -> str | None:
        return self._choose_folder(current_path)

    def choose_raw_telemetry_folder(self, current_path: str | None = None) -> dict | None:
        selected = self._choose_folder(current_path)
        if selected is None:
            return None
        return self._local_file_selection_registry.register_folder(selected)

    def choose_raw_telemetry_files(self, current_path: str | None = None) -> dict | None:
        window = self._dialog_window()
        if window is None:
            return None

        selected = window.create_file_dialog(
            self._webview_module().OPEN_DIALOG,
            directory=self._dialog_directory(current_path),
            allow_multiple=True,
        )
        if not selected:
            return None
        return self._local_file_selection_registry.register_files([str(path) for path in selected])


def run_smoke_http_only(paths: DesktopPaths | None = None) -> int:
    resolved_paths = paths or default_desktop_paths()
    resolved_paths.ensure_user_directories()
    port = int(os.environ.get("FORZA_TRACKER_SMOKE_HTTP_PORT") or allocate_local_port())
    backend = DesktopBackend(paths=resolved_paths, http_port=port)
    backend.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        backend.stop()


def run_desktop_app(paths: DesktopPaths | None = None) -> int:
    resolved_paths = paths or default_desktop_paths()
    resolved_paths.ensure_user_directories()
    port = allocate_local_port()
    backend = DesktopBackend(paths=resolved_paths, http_port=port)
    backend.start()
    try:
        webview = load_webview()
        bridge = DesktopBridge(webview, backend.local_file_selection_registry)
        window = webview.create_window(
            "Forza Telemetry Tracker",
            desktop_url(port),
            width=1600,
            height=900,
            min_size=(1200, 780),
            background_color="#101820",
            js_api=bridge,
        )
        bridge.bind_window(window)
        webview.start()
        return 0
    finally:
        backend.stop()


def main() -> int:
    if "--smoke-http-only" in sys.argv:
        return run_smoke_http_only()
    return run_desktop_app()


if __name__ == "__main__":
    raise SystemExit(main())
