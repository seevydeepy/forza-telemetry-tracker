#!/usr/bin/env python
"""Smoke-test a built ForzaTelemetryTracker desktop package."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from telemetry_tracker.storage import TelemetryStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test a built ForzaTelemetryTracker desktop package")
    parser.add_argument("--app-dir", type=Path, required=True, help="Path to the unpacked app directory")
    parser.add_argument("--timeout", type=float, default=30.0, help="Seconds to wait for the app to become ready")
    return parser.parse_args()


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _pick_free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _prepare_smoke_user_data(user_data_root: Path, udp_port: int) -> None:
    store = TelemetryStore(user_data_root / "telemetry_tracker.sqlite3")
    store.migrate()
    with store.connect() as con:
        con.execute(
            """
            UPDATE user_settings
            SET udp_host = ?, udp_port = ?, updated_at_ms = ?
            """,
            ("127.0.0.1", int(udp_port), int(time.time() * 1000)),
        )


def wait_for_status(base_url: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    url = f"{base_url}/api/status"
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=2.0)
            if resp.status_code == 200:
                return resp.json()
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"App did not respond at {url} within {timeout}s")


def read_one_sse_event(base_url: str, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    client_timeout = httpx.Timeout(timeout=5.0, read=1.0)
    with httpx.Client(timeout=client_timeout) as client:
        with client.stream("GET", f"{base_url}/events") as stream:
            if stream.status_code != 200:
                raise RuntimeError(f"events endpoint returned HTTP {stream.status_code}")
            client.post(f"{base_url}/api/capture/start")
            while time.monotonic() < deadline:
                try:
                    for line in stream.iter_lines():
                        if line.startswith("data:"):
                            return line
                        if time.monotonic() >= deadline:
                            break
                except httpx.ReadTimeout:
                    pass
    raise RuntimeError(f"No SSE data: line received within {timeout}s")


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def main() -> int:
    args = parse_args()
    app_dir: Path = args.app_dir.resolve()
    timeout: float = args.timeout

    exe = app_dir / "ForzaTelemetryTracker.exe"
    if not exe.exists():
        print(f"ERROR: exe not found: {exe}", file=sys.stderr)
        return 1

    resource_root = app_dir / "_internal" if (app_dir / "_internal").is_dir() else app_dir

    converter = resource_root / "bin" / "map-converter" / "forza-map-tile-converter.exe"
    if not converter.exists():
        print(f"ERROR: bundled converter not found: {converter}", file=sys.stderr)
        return 1

    port = _pick_free_port()
    udp_port = _pick_free_udp_port()
    base_url = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory() as tmpdir:
        user_data_root = Path(tmpdir) / "data"
        _prepare_smoke_user_data(user_data_root, udp_port)
        env = os.environ.copy()
        env["FORZA_TRACKER_USER_DATA_ROOT"] = str(user_data_root)
        env["FORZA_TRACKER_RESOURCE_ROOT"] = str(resource_root)
        env["FORZA_TRACKER_SMOKE_HTTP_PORT"] = str(port)

        proc = subprocess.Popen(
            [str(exe), "--smoke-http-only"],
            cwd=str(app_dir),
            env=env,
        )
        try:
            print(f"Launched PID {proc.pid}, waiting for {base_url}/api/status (UDP {udp_port}) …")
            status = wait_for_status(base_url, timeout)

            udp_host = status.get("settings", {}).get("udp_host")
            status_udp_port = int(status.get("settings", {}).get("udp_port") or 0)
            if udp_host != "127.0.0.1":
                raise AssertionError(f"Expected udp_host '127.0.0.1', got {udp_host!r}")
            if status_udp_port != udp_port:
                raise AssertionError(f"Expected udp_port {udp_port}, got {status_udp_port!r}")
            print(f"  /api/status OK — udp_host={udp_host}, udp_port={status_udp_port}")

            resp = httpx.get(base_url + "/", timeout=5.0)
            if resp.status_code != 200:
                raise AssertionError(f"GET / returned {resp.status_code}")
            print(f"  GET / OK ({resp.status_code})")

            sse_line = read_one_sse_event(base_url, timeout)
            print(f"  SSE OK — {sse_line[:80]}")
        except Exception as exc:
            print(f"SMOKE FAILED: {exc}", file=sys.stderr)
            _terminate(proc)
            return 1
        else:
            _terminate(proc)

    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
