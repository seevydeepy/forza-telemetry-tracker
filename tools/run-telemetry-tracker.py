#!/usr/bin/env python
"""Run the local Forza Telemetry Tracker web app."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telemetry_tracker.app import _settings_payload, create_app
from telemetry_tracker.port_conflicts import (
    PortBinding,
    ProcessConflict,
    find_port_conflicts,
    kill_process_tree,
    wait_for_bindings_to_clear,
)
from telemetry_tracker.storage import TelemetryStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forza Telemetry Tracker local app")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8765, help="HTTP bind port")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("telemetry") / "telemetry_tracker.sqlite3",
        help="SQLite database path",
    )
    return parser.parse_args()


def _listener_binding_from_db(db_path: Path) -> PortBinding:
    """Read the persisted UDP listener binding that create_app() will use."""

    store = TelemetryStore(Path(db_path))
    store.migrate()
    settings = _settings_payload(store)
    return PortBinding(
        "UDP",
        str(settings["udp_host"]),
        int(settings["udp_port"]),
        "Forza UDP listener",
    )


def _print_port_conflicts(conflicts: list[ProcessConflict]) -> None:
    print("Port conflict detected; the tracker cannot start until these ports are free:")
    for conflict in conflicts:
        binding = conflict.binding
        print(
            f"- {binding.label}: {binding.protocol.upper()} "
            f"{binding.host}:{binding.port} is owned by PID {conflict.pid}"
        )
        if conflict.process_name:
            print(f"  Process: {conflict.process_name}")
        if conflict.executable_path:
            print(f"  Path: {conflict.executable_path}")
        if conflict.command_line:
            print(f"  Command: {conflict.command_line}")


def _resolve_port_conflicts(bindings: list[PortBinding]) -> bool:
    conflicts = find_port_conflicts(bindings)
    if not conflicts:
        return True

    _print_port_conflicts(conflicts)
    try:
        answer = input("Kill these process(es) and continue? [y/N] ")
    except EOFError:
        answer = ""

    if answer.strip().lower() not in {"y", "yes"}:
        print("Not killing existing process(es). Tracker startup cancelled.")
        return False

    killed_pids: set[int] = set()
    for conflict in conflicts:
        if conflict.pid in killed_pids:
            continue
        print(f"Killing PID {conflict.pid}...")
        kill_process_tree(conflict.pid)
        killed_pids.add(conflict.pid)

    wait_for_bindings_to_clear(bindings)
    return True


def main() -> int:
    args = parse_args()
    http_binding = PortBinding("TCP", args.host, args.port, "HTTP site")
    udp_binding = _listener_binding_from_db(args.db)
    bindings = [http_binding, udp_binding]

    try:
        if not _resolve_port_conflicts(bindings):
            return 1
    except RuntimeError as exc:
        print(str(exc))
        return 1

    app = create_app(
        db_path=args.db,
        start_udp_listener=True,
        refresh_car_catalog=True,
        refresh_track_catalog=True,
    )
    print(f"Forza Telemetry Tracker: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
