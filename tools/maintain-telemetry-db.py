#!/usr/bin/env python
"""Prune and compact the local telemetry tracker SQLite database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telemetry_tracker.storage import TelemetryStore

DEFAULT_DB = Path("telemetry") / "telemetry_tracker.sqlite3"
DEFAULT_MIN_FREE_BYTES = 256 * 1024 * 1024
DEFAULT_MIN_FREE_RATIO = 0.25


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def _ratio(value: str) -> float:
    parsed = float(value)
    if parsed < 0.0 or parsed > 1.0:
        raise argparse.ArgumentTypeError("ratio must be between 0 and 1")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be pruned or vacuumed without changing the database")
    parser.add_argument(
        "--max-prune-rows",
        type=_positive_int,
        default=None,
        help="Maximum prunable lap_samples rows to remove in this run; default removes all eligible rows",
    )
    parser.add_argument(
        "--vacuum",
        choices=("off", "auto", "always"),
        default="auto",
        help="Run full SQLite VACUUM never, only when thresholds are met, or always",
    )
    parser.add_argument(
        "--min-free-bytes",
        type=_non_negative_int,
        default=DEFAULT_MIN_FREE_BYTES,
        help="Auto-VACUUM minimum freelist bytes threshold",
    )
    parser.add_argument(
        "--min-free-ratio",
        type=_ratio,
        default=DEFAULT_MIN_FREE_RATIO,
        help="Auto-VACUUM minimum freelist/page-count ratio threshold",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON summary instead of human text",
    )
    return parser.parse_args(argv)


def _format_bytes(value: int | float) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(value)
    for unit in units:
        if abs(size) < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TiB"


def _summarize_size(info: dict[str, Any]) -> str:
    return (
        f"file={_format_bytes(int(info['file_bytes']))}, "
        f"allocated={_format_bytes(int(info['allocated_bytes']))}, "
        f"free={_format_bytes(int(info['freelist_bytes']))} "
        f"({float(info['freelist_ratio']) * 100:.1f}%), "
        f"used={_format_bytes(int(info['used_bytes']))}"
    )


def run_maintenance(args: argparse.Namespace) -> dict:
    store = TelemetryStore(Path(args.db))
    store.migrate()

    before = store.database_size_info()
    eligible_before = store.count_prunable_unassigned_non_race_telemetry()
    prune_result = store.prune_unassigned_non_race_telemetry(
        max_rows=args.max_prune_rows,
        dry_run=args.dry_run,
    )

    checkpoint_result = None
    vacuum_result: dict[str, Any]
    if args.dry_run:
        after_prune = before
        vacuum_would_run = args.vacuum == "always" or (
            args.vacuum == "auto"
            and int(before["freelist_bytes"]) >= int(args.min_free_bytes)
            and float(before["freelist_ratio"]) >= float(args.min_free_ratio)
        )
        vacuum_result = {
            "ran": False,
            "dry_run": True,
            "would_run": vacuum_would_run,
            "reason": "dry_run",
            "before": before,
            "after": before,
        }
    else:
        checkpoint_result = store.wal_checkpoint_truncate()
        after_prune = store.database_size_info()
        if args.vacuum == "off":
            vacuum_result = {
                "ran": False,
                "reason": "disabled",
                "before": after_prune,
                "after": after_prune,
            }
        else:
            vacuum_result = store.vacuum_if_needed(
                min_freelist_bytes=args.min_free_bytes,
                min_freelist_ratio=args.min_free_ratio,
                force=args.vacuum == "always",
            )

    after = store.database_size_info() if not args.dry_run else before
    eligible_after = (
        store.count_prunable_unassigned_non_race_telemetry()
        if not args.dry_run
        else eligible_before
    )
    return {
        "db_path": str(Path(args.db)),
        "dry_run": bool(args.dry_run),
        "eligible_prunable_samples_before": eligible_before,
        "eligible_prunable_samples_after": eligible_after,
        "prune": prune_result,
        "checkpoint": checkpoint_result,
        "vacuum": vacuum_result,
        "size_before": before,
        "size_after_prune": after_prune,
        "size_after": after,
    }


def print_human(summary: dict) -> None:
    print(f"Database: {summary['db_path']}")
    if summary["dry_run"]:
        print("Mode: dry run")
    print(f"Before: {_summarize_size(summary['size_before'])}")
    print(f"Eligible prunable samples: {summary['eligible_prunable_samples_before']:,}")
    prune = summary["prune"]
    print(
        "Prune: "
        f"targeted {int(prune['target_sample_count']):,}, "
        f"deleted {int(prune['deleted_sample_count']):,} samples and "
        f"{int(prune['deleted_packet_count']):,} raw packets"
    )
    checkpoint = summary.get("checkpoint")
    if checkpoint is not None:
        print(
            "WAL checkpoint: "
            f"busy={checkpoint['busy']}, "
            f"log_frames={checkpoint['log_frames']}, "
            f"checkpointed_frames={checkpoint['checkpointed_frames']}"
        )
    vacuum = summary["vacuum"]
    if vacuum.get("dry_run"):
        print(f"VACUUM: dry-run would_run={vacuum['would_run']}")
    else:
        print(f"VACUUM: ran={vacuum['ran']} reason={vacuum['reason']}")
    print(f"After: {_summarize_size(summary['size_after'])}")
    print(f"Remaining eligible prunable samples: {summary['eligible_prunable_samples_after']:,}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_maintenance(args)
    except Exception as exc:
        print(f"Telemetry DB maintenance failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print_human(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
