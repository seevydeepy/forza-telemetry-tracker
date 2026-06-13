#!/usr/bin/env python
"""Parse FH6 Data Out raw captures into CSV and JSON summaries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from telemetry_tracker import data_out


def resolve_input(input_path: Path | None, latest_path: Path | None) -> tuple[Path, Path]:
    if latest_path is not None:
        pointer = json.loads(latest_path.read_text(encoding="utf-8"))
        raw_path = Path(pointer["raw_path"])
        return raw_path, Path(pointer.get("capture_dir", raw_path.parent))

    if input_path is None:
        raise ValueError("--input or --latest is required")

    if input_path.is_dir():
        raw_path = input_path / "raw.bin"
        return raw_path, input_path

    return input_path, input_path.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="raw.bin file or capture directory")
    parser.add_argument("--output-dir", type=Path, help="directory for packets.csv and summary.json")
    parser.add_argument("--latest", type=Path, help="telemetry/latest.json pointer")
    parser.add_argument("--pretty", action="store_true", help="pretty-print the summary")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = None
    try:
        raw_path, default_output = resolve_input(args.input, args.latest)
        output_dir = args.output_dir or default_output
        output_dir.mkdir(parents=True, exist_ok=True)
        packets = list(data_out.iter_raw_packets(raw_path))
        data_out.write_packets_csv(output_dir / "packets.csv", packets)
        summary = data_out.summarize_packets(packets)
        (output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if summary is None:
        print("Error: no summary produced", file=sys.stderr)
        return 2

    if args.pretty:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"Parsed {summary['packet_count']} packets; "
            f"top speed {summary.get('top_speed_mph', 0)} mph; "
            f"class {summary.get('car_class_label', 'unknown')} "
            f"{summary.get('car_performance_index', '')}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
