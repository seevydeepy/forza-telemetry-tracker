#!/usr/bin/env python
"""Listen for FH6 Data Out UDP packets and write capture artifacts."""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telemetry_tracker import data_out


RESERVED_MIN = 5200
RESERVED_MAX = 5300


def safe_label(label: str | None) -> str:
    if not label:
        return "run"
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", label).strip("-")
    return cleaned or "run"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture FH6 Data Out telemetry. In FH6 set Data Out On, "
            "IP 127.0.0.1, and the same port as this listener. "
            "Avoid ports 5200 through 5300."
        )
    )
    parser.add_argument("--host", default="127.0.0.1", help="listen host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5400, help="listen port (default: 5400)")
    parser.add_argument("--duration", type=float, help="capture duration in seconds")
    parser.add_argument("--output-dir", type=Path, default=Path("telemetry"), help="telemetry root")
    parser.add_argument("--label", default="run", help="capture label")
    parser.add_argument("--socket-timeout", type=float, default=0.5, help="socket timeout seconds")
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="keep listening and auto-split captures after packet silence",
    )
    parser.add_argument(
        "--idle-split-seconds",
        type=float,
        default=15.0,
        help=(
            "continuous mode active-driving silence window before finalizing a capture; "
            "inactive menu/end-screen packets do not keep a run open"
        ),
    )
    parser.add_argument(
        "--capture-index",
        type=Path,
        help="JSON index of finalized captures; default is output-dir/capture-index.json",
    )
    parser.add_argument(
        "--allow-reserved-port",
        action="store_true",
        help="allow ports 5200-5300 despite FH6 warning",
    )
    parser.add_argument("--ready-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--stop-file", type=Path, help="stop gracefully when this file appears")
    return parser.parse_args(argv)


def print_setup(host: str, port: int) -> None:
    print("FH6 Data Out capture listener")
    print(f"Listening on {host}:{port}")
    print("In FH6: Settings > HUD and Gameplay > Data Out On")
    print(f"Set Data Out IP Address to {host}")
    print(f"Set Data Out IP Port to {port}")
    print("Avoid ports 5200 through 5300.")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_capture_index(index_path: Path, manifest: dict) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if index_path.exists():
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        payload = {"captures": []}
    payload.setdefault("captures", []).append(
        {
            "manifest_path": manifest["manifest_path"],
            "capture_dir": manifest["capture_dir"],
            "summary_path": manifest["summary_path"],
            "raw_path": manifest["raw_path"],
            "packets_csv_path": manifest["packets_csv_path"],
            "packet_count": manifest["packet_count"],
            "segment_classification": manifest.get("segment_classification"),
            "created_utc": manifest["created_utc"],
            "metadata": manifest.get("metadata", {}),
        }
    )
    payload["updated_utc"] = utc_now()
    tmp = index_path.with_suffix(index_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(index_path)


def write_capture(
    args: argparse.Namespace,
    raw_packets: list[bytes],
    metadata: dict,
    segment_index: int | None = None,
) -> dict:
    label = safe_label(args.label)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if segment_index is None:
        dirname = f"{timestamp}-{label}"
    else:
        dirname = f"{timestamp}-{label}-{segment_index:03d}"
    capture_dir = args.output_dir / "captures" / dirname
    manifest = data_out.write_capture_artifacts(capture_dir, raw_packets, metadata)
    latest_path = args.output_dir / "latest.json"
    data_out.write_latest_pointer(latest_path, Path(manifest["manifest_path"]))
    index_path = args.capture_index or (args.output_dir / "capture-index.json")
    append_capture_index(index_path, manifest)
    return manifest


def is_active_driving_packet(packet: dict) -> bool:
    return int(packet["IsRaceOn"]) == 1 and (
        float(packet["Speed"]) > 0.5
        or float(packet["EngineMaxRpm"]) > 0
        or int(packet["CarPerformanceIndex"]) > 0
    )


def capture(args: argparse.Namespace) -> int:
    if RESERVED_MIN <= args.port <= RESERVED_MAX and not args.allow_reserved_port:
        print(
            f"Error: port {args.port} is in the FH6 reserved range "
            f"{RESERVED_MIN}-{RESERVED_MAX}; choose 5400 or pass --allow-reserved-port.",
            file=sys.stderr,
        )
        return 2

    raw_packets: list[bytes] = []
    malformed = 0
    total_valid_datagrams = 0
    total_recorded_packets = 0
    ignored_inactive_datagrams = 0
    written_captures = 0
    source_addresses: set[str] = set()
    segment_source_addresses: set[str] = set()
    started_utc = utc_now()
    segment_started_utc: str | None = None
    last_active_monotonic: float | None = None
    started_monotonic = time.monotonic()
    deadline = started_monotonic + args.duration if args.duration is not None else None

    def maybe_finalize_active_idle(now: float) -> None:
        if (
            args.continuous
            and raw_packets
            and last_active_monotonic is not None
            and now - last_active_monotonic >= args.idle_split_seconds
        ):
            finalize_segment("active-idle-split")

    def finalize_segment(reason: str) -> None:
        nonlocal raw_packets
        nonlocal written_captures
        nonlocal segment_source_addresses
        nonlocal segment_started_utc
        nonlocal last_active_monotonic
        if not raw_packets:
            return
        ended_utc = utc_now()
        written_captures += 1
        metadata = {
            "host": args.host,
            "port": args.port,
            "duration_requested_seconds": args.duration,
            "label": args.label,
            "continuous": bool(args.continuous),
            "segment_index": written_captures if args.continuous else None,
            "segment_reason": reason,
            "started_utc": segment_started_utc or started_utc,
            "ended_utc": ended_utc,
            "malformed_datagram_count": malformed,
            "total_valid_datagram_count": total_valid_datagrams,
            "ignored_inactive_datagram_count": ignored_inactive_datagrams,
            "source_addresses": sorted(segment_source_addresses or source_addresses),
        }
        manifest = write_capture(
            args,
            raw_packets,
            metadata,
            written_captures if args.continuous else None,
        )
        print(
            f"Captured {len(raw_packets)} valid packets to {manifest['capture_dir']}."
        )
        raw_packets = []
        segment_source_addresses = set()
        segment_started_utc = None
        last_active_monotonic = None

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(args.socket_timeout)
            sock.bind((args.host, args.port))
            if args.ready_file is not None:
                args.ready_file.parent.mkdir(parents=True, exist_ok=True)
                args.ready_file.write_text("ready\n", encoding="utf-8")
            print_setup(args.host, args.port)
            while True:
                maybe_finalize_active_idle(time.monotonic())
                if deadline is not None and time.monotonic() >= deadline:
                    break
                if args.stop_file is not None and args.stop_file.exists():
                    print(f"Stop file detected: {args.stop_file}")
                    break
                try:
                    payload, addr = sock.recvfrom(4096)
                except socket.timeout:
                    maybe_finalize_active_idle(time.monotonic())
                    continue
                if len(payload) != data_out.PACKET_SIZE:
                    malformed += 1
                    continue
                total_valid_datagrams += 1
                decoded = data_out.decode_packet(payload)
                source_addresses.add(f"{addr[0]}:{addr[1]}")
                if not is_active_driving_packet(decoded):
                    ignored_inactive_datagrams += 1
                    maybe_finalize_active_idle(time.monotonic())
                    continue
                if not raw_packets:
                    segment_started_utc = utc_now()
                raw_packets.append(payload)
                total_recorded_packets += 1
                segment_source_addresses.add(f"{addr[0]}:{addr[1]}")
                last_active_monotonic = time.monotonic()
                if args.stop_file is not None and args.stop_file.exists():
                    print(f"Stop file detected: {args.stop_file}")
                    break
    except KeyboardInterrupt:
        print("Capture stopped by Ctrl+C.")
    except OSError as exc:
        print(f"Error: could not listen on {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 3

    if raw_packets:
        finalize_segment("stop")

    if total_recorded_packets == 0:
        if total_valid_datagrams:
            print(
                "No active driving packets received. FH6 sent UDP datagrams, but "
                "they looked like menu, pause, replay, rewind, or post-finish data. "
                "Start driving, then try again.",
                file=sys.stderr,
            )
        else:
            print(
                "No packets received. Check that FH6 Data Out is On, IP is "
                f"{args.host}, port is {args.port}, the car is actively driving, "
                "and firewall rules allow UDP to this listener.",
                file=sys.stderr,
            )
        if malformed:
            print(f"Received {malformed} malformed datagrams.", file=sys.stderr)
        return 4

    latest_path = args.output_dir / "latest.json"

    print(f"Received {total_valid_datagrams} valid datagrams.")
    print(f"Captured {total_recorded_packets} active driving packets.")
    if ignored_inactive_datagrams:
        print(f"Ignored {ignored_inactive_datagrams} inactive datagrams.")
    print(f"Finalized {written_captures} capture(s).")
    print(f"Latest pointer: {latest_path.resolve()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return capture(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
