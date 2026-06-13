"""Temporary helper executable used to install downloaded updates."""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path


def _write_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with log_path.open("a", encoding="utf-8") as target:
        target.write(f"{timestamp} {message}\n")


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_process_exit(pid: int, *, timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _process_alive(pid):
            return
        time.sleep(0.5)
    raise TimeoutError(f"process {pid} did not exit within {timeout_seconds} seconds")


def run_update_helper(args: argparse.Namespace) -> int:
    installer = Path(args.installer)
    app_exe = Path(args.app_exe)
    log_path = Path(args.log)
    _write_log(log_path, f"Updater started for installer {installer.name}")
    try:
        wait_for_process_exit(int(args.wait_pid), timeout_seconds=int(args.wait_timeout_seconds))
        if not installer.is_file():
            raise FileNotFoundError(f"installer not found: {installer}")
        inno_log = log_path.with_name("inno-update-install.log")
        installer_args = [
            str(installer),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/SP-",
            f"/LOG={inno_log}",
        ]
        _write_log(log_path, "Launching silent installer")
        completed = subprocess.run(installer_args, check=False)
        _write_log(log_path, f"Installer exited with code {completed.returncode}")
        if completed.returncode != 0:
            return int(completed.returncode)
        if app_exe.is_file():
            popen_kwargs = {"close_fds": True}
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            subprocess.Popen([str(app_exe)], **popen_kwargs)
            _write_log(log_path, "Relaunched app")
        else:
            _write_log(log_path, f"App executable missing after install: {app_exe}")
        return 0
    except Exception as exc:
        _write_log(log_path, f"Updater failed: {exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Forza Telemetry Tracker update.")
    parser.add_argument("--wait-pid", required=True, type=int)
    parser.add_argument("--installer", required=True)
    parser.add_argument("--app-exe", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--wait-timeout-seconds", default=120, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    return run_update_helper(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
