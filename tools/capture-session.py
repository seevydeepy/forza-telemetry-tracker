#!/usr/bin/env python
"""Manage an FH6 Data Out capture session for Codex."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TELEMETRY = ROOT / "telemetry"
DEFAULT_SESSION_FILE = DEFAULT_TELEMETRY / "capture-session.json"
DEFAULT_CAPTURE_INDEX = DEFAULT_TELEMETRY / "capture-index.json"
DEFAULT_ANALYSIS_STATE = DEFAULT_TELEMETRY / "analysis-state.json"
ACTIVE_STATUSES = {"running", "continuous"}

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telemetry_tracker import data_out


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_session(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def save_session(path: Path, session: dict) -> None:
    save_json(path, session)


def classify_capture_entry(capture: dict) -> dict:
    enriched = dict(capture)
    if enriched.get("segment_classification"):
        return enriched

    summary_path = enriched.get("summary_path")
    if not summary_path:
        enriched["segment_classification"] = {
            "label": "maybe",
            "score": 0,
            "reasons": ["missing summary path"],
        }
        return enriched

    try:
        summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    except Exception as exc:
        enriched["segment_classification"] = {
            "label": "maybe",
            "score": 0,
            "reasons": [f"could not read summary: {exc}"],
        }
        return enriched

    enriched["segment_classification"] = summary.get(
        "segment_classification",
        data_out.classify_summary(summary),
    )
    return enriched


def recommended_capture(captures: list[dict]) -> dict | None:
    for label in ("useful", "maybe"):
        candidates = [
            capture
            for capture in captures
            if capture.get("segment_classification", {}).get("label") == label
        ]
        if candidates:
            return candidates[-1]
    return None


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.returncode == 0
    except Exception:
        return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_start_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--host", default="127.0.0.1")
        command.add_argument("--port", type=int, default=5400)
        command.add_argument("--output-dir", type=Path, default=DEFAULT_TELEMETRY)
        command.add_argument("--label", default="run")
        command.add_argument("--session-file", type=Path, default=DEFAULT_SESSION_FILE)
        command.add_argument("--ready-timeout", type=float, default=5.0)
        command.add_argument("--socket-timeout", type=float, default=0.2)

    start = sub.add_parser("start", help="start one-shot capture listener in the background")
    add_start_arguments(start)

    start_continuous = sub.add_parser(
        "start-continuous",
        help="start always-on capture listener with automatic run splitting",
    )
    add_start_arguments(start_continuous)
    start_continuous.add_argument(
        "--idle-split-seconds",
        type=float,
        default=15.0,
        help="packet silence window before a run is finalized",
    )
    start_continuous.add_argument(
        "--capture-index",
        type=Path,
        help="JSON index of finalized captures; default is output-dir/capture-index.json",
    )

    status = sub.add_parser("status", help="show current capture session state")
    status.add_argument("--session-file", type=Path, default=DEFAULT_SESSION_FILE)

    stop = sub.add_parser("stop", help="stop current capture session")
    stop.add_argument("--session-file", type=Path, default=DEFAULT_SESSION_FILE)
    stop.add_argument("--wait-timeout", type=float, default=15.0)

    new = sub.add_parser("new", help="list finalized captures not yet marked analyzed")
    new.add_argument("--capture-index", type=Path, default=DEFAULT_CAPTURE_INDEX)
    new.add_argument("--analysis-state", type=Path, default=DEFAULT_ANALYSIS_STATE)
    new.add_argument(
        "--mark-analyzed",
        action="store_true",
        help="record returned captures as analyzed after listing them",
    )

    return parser.parse_args(argv)


def command_start(args: argparse.Namespace) -> int:
    continuous = args.command == "start-continuous"
    output_dir = args.output_dir.resolve()
    capture_index = getattr(args, "capture_index", None) or (output_dir / "capture-index.json")
    analysis_state = output_dir / "analysis-state.json"
    session_file = args.session_file.resolve()
    if session_file.exists():
        existing = load_session(session_file)
        if existing.get("status") in ACTIVE_STATUSES and pid_is_running(int(existing["pid"])):
            print(
                f"Capture already running on {existing['host']}:{existing['port']} "
                f"(pid {existing['pid']}).",
                file=sys.stderr,
            )
            return 2

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    state_dir = output_dir / "sessions"
    state_dir.mkdir(parents=True, exist_ok=True)
    ready_file = state_dir / f"{run_id}-{args.label}-ready.txt"
    stop_file = state_dir / f"{run_id}-{args.label}-stop.txt"
    stdout_path = state_dir / f"{run_id}-{args.label}-stdout.log"
    stderr_path = state_dir / f"{run_id}-{args.label}-stderr.log"

    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    command = [
        sys.executable,
        str(ROOT / "tools" / "capture-data-out.py"),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--output-dir",
        str(args.output_dir),
        "--label",
        args.label,
        "--socket-timeout",
        str(args.socket_timeout),
        "--ready-file",
        str(ready_file),
        "--stop-file",
        str(stop_file),
    ]
    if continuous:
        command.extend(
            [
                "--continuous",
                "--idle-split-seconds",
                str(args.idle_split_seconds),
                "--capture-index",
                str(capture_index),
            ]
        )
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    stdout_handle.close()
    stderr_handle.close()

    deadline = time.monotonic() + args.ready_timeout
    while time.monotonic() < deadline:
        if ready_file.exists():
            break
        if proc.poll() is not None:
            print(f"Capture listener exited early with code {proc.returncode}.", file=sys.stderr)
            print(f"stderr: {stderr_path}", file=sys.stderr)
            return 3
        time.sleep(0.05)

    if not ready_file.exists():
        stop_file.write_text("stop\n", encoding="utf-8")
        print("Capture listener did not become ready in time.", file=sys.stderr)
        return 4

    session = {
        "status": "continuous" if continuous else "running",
        "continuous": continuous,
        "pid": proc.pid,
        "host": args.host,
        "port": args.port,
        "label": args.label,
        "started_utc": utc_now(),
        "output_dir": str(output_dir),
        "session_file": str(session_file),
        "ready_file": str(ready_file),
        "stop_file": str(stop_file),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "latest_path": str((output_dir / "latest.json")),
        "capture_index_path": str(capture_index.resolve()),
        "analysis_state_path": str(analysis_state.resolve()),
    }
    if continuous:
        session["idle_split_seconds"] = args.idle_split_seconds
    save_session(session_file, session)
    if continuous:
        print(f"Continuous capture listening on {args.host}:{args.port} (pid {proc.pid}).")
        print(
            f"Runs finalize after {args.idle_split_seconds:g}s without active driving packets."
        )
        print(f"Capture index: {capture_index.resolve()}")
    else:
        print(f"Listening on {args.host}:{args.port} (pid {proc.pid}).")
    print("In FH6 set Data Out IP Address to 127.0.0.1 and Data Out IP Port to this port.")
    print("Drive your race, then tell Codex when you want the latest run analyzed.")
    return 0


def command_status(args: argparse.Namespace) -> int:
    if not args.session_file.exists():
        print(f"No capture session file at {args.session_file}.")
        return 1
    session = load_session(args.session_file)
    running = session.get("status") in ACTIVE_STATUSES and pid_is_running(int(session.get("pid", 0)))
    state = session.get("status", "stopped") if running else session.get("status", "stopped")
    print(f"Capture session {state}: {session.get('host')}:{session.get('port')} pid={session.get('pid')}")
    return 0 if running else 1


def command_stop(args: argparse.Namespace) -> int:
    if not args.session_file.exists():
        print(f"No capture session file at {args.session_file}.", file=sys.stderr)
        return 2
    session = load_session(args.session_file)
    stop_file = Path(session["stop_file"])
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    stop_file.write_text("stop\n", encoding="utf-8")

    pid = int(session.get("pid", 0))
    deadline = time.monotonic() + args.wait_timeout
    while time.monotonic() < deadline and pid_is_running(pid):
        time.sleep(0.1)

    running = pid_is_running(pid)
    if running:
        session["status"] = "stop-timeout"
        session["stopped_utc"] = utc_now()
        save_session(args.session_file, session)
        print(f"Capture process {pid} did not stop within {args.wait_timeout}s.", file=sys.stderr)
        return 3

    session["status"] = "stopped"
    session["stopped_utc"] = utc_now()
    latest_path = Path(session["latest_path"])
    if latest_path.exists():
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        session["latest_capture"] = latest
        print(f"Capture stopped. Latest capture: {latest.get('capture_dir')}")
        print(f"Summary: {latest.get('summary_path')}")
    else:
        print("Capture stopped, but no latest telemetry was written.", file=sys.stderr)
    save_session(args.session_file, session)
    return 0 if latest_path.exists() else 4


def command_new(args: argparse.Namespace) -> int:
    if args.capture_index.exists():
        capture_index = json.loads(args.capture_index.read_text(encoding="utf-8"))
    else:
        capture_index = {"captures": []}

    if args.analysis_state.exists():
        analysis_state = json.loads(args.analysis_state.read_text(encoding="utf-8"))
    else:
        analysis_state = {"analyzed_manifest_paths": []}

    analyzed = set(analysis_state.get("analyzed_manifest_paths", []))
    captures = capture_index.get("captures", [])
    new_captures = [
        classify_capture_entry(capture)
        for capture in captures
        if capture.get("manifest_path") and capture.get("manifest_path") not in analyzed
    ]
    recommended = recommended_capture(new_captures)
    useful_count = sum(
        capture.get("segment_classification", {}).get("label") == "useful"
        for capture in new_captures
    )
    maybe_count = sum(
        capture.get("segment_classification", {}).get("label") == "maybe"
        for capture in new_captures
    )

    if args.mark_analyzed and new_captures:
        analyzed.update(capture["manifest_path"] for capture in new_captures)
        now = utc_now()
        analysis_state["analyzed_manifest_paths"] = sorted(analyzed)
        analysis_state["last_analyzed_utc"] = now
        analysis_state["updated_utc"] = now
        save_json(args.analysis_state, analysis_state)

    print(
        json.dumps(
            {
                "capture_index": str(args.capture_index.resolve()),
                "analysis_state": str(args.analysis_state.resolve()),
                "new_count": len(new_captures),
                "useful_count": useful_count,
                "maybe_count": maybe_count,
                "ignored_count": len(new_captures) - useful_count - maybe_count,
                "recommended_manifest_path": recommended.get("manifest_path") if recommended else None,
                "recommended_segment_classification": recommended.get("segment_classification") if recommended else None,
                "marked_analyzed": bool(args.mark_analyzed and new_captures),
                "captures": new_captures,
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command in {"start", "start-continuous"}:
        return command_start(args)
    if args.command == "status":
        return command_status(args)
    if args.command == "stop":
        return command_stop(args)
    if args.command == "new":
        return command_new(args)
    raise ValueError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
