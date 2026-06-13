from __future__ import annotations

import contextlib
import csv
import os
import re
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

from telemetry_tracker.packet_bridge import FIELD_NAMES, decode_packet

_CANCEL_CHECK = Callable[[], bool]
_EMPTY_EXPORT_MESSAGE = "No recorded telemetry is available to export"
_TEMP_SUFFIX = ".forza-telemetry-tracker-export.tmp"


class TelemetryExportKind(str, Enum):
    raw_binary = "raw_binary"
    raw_csv = "raw_csv"
    curated_csv = "curated_csv"

    @property
    def filename_fragment(self) -> str:
        return {
            TelemetryExportKind.raw_binary: "raw-binary",
            TelemetryExportKind.raw_csv: "raw",
            TelemetryExportKind.curated_csv: "curated",
        }[self]

    @property
    def extension(self) -> str:
        return {
            TelemetryExportKind.raw_binary: ".zip",
            TelemetryExportKind.raw_csv: ".csv",
            TelemetryExportKind.curated_csv: ".csv",
        }[self]

    @property
    def label(self) -> str:
        return {
            TelemetryExportKind.raw_binary: "Raw binary package",
            TelemetryExportKind.raw_csv: "Raw CSV",
            TelemetryExportKind.curated_csv: "Curated CSV",
        }[self]


@dataclass(frozen=True)
class ExportedFile:
    path: Path
    filename: str
    size_bytes: int


@dataclass(frozen=True)
class TelemetryExportResult:
    kind: TelemetryExportKind
    output_files: tuple[ExportedFile, ...]
    total_size_bytes: int
    row_count: int


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def _check_cancel(should_cancel: _CANCEL_CHECK) -> None:
    if should_cancel():
        raise InterruptedError("Telemetry export cancelled")


def normalize_output_dir(value: str | os.PathLike[str]) -> Path:
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    if not text:
        raise ValueError("Output directory is required")
    path = Path(text).expanduser()
    if path.exists() and not path.is_dir():
        raise ValueError(f"Output path is not a directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    resolved = path.resolve()
    _probe_output_dir_writable(resolved)
    return resolved


def _probe_output_dir_writable(path: Path) -> None:
    suffix = 0
    while True:
        probe_path = path / f".forza-telemetry-tracker-export-probe-{os.getpid()}{f'-{suffix}' if suffix else ''}.tmp"
        created = False
        try:
            with probe_path.open("xb") as handle:
                created = True
                handle.write(b"ok")
            return
        except FileExistsError:
            suffix += 1
        except OSError as exc:
            raise ValueError(f"Output directory is not writable: {path}") from exc
        finally:
            if created:
                try:
                    probe_path.unlink()
                except FileNotFoundError:
                    pass


def sanitize_filename_prefix(value: str | None) -> str:
    text = str(value or "telemetry").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    text = re.sub(r"[\\/:*?\"<>|]+", "-", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text)
    text = re.sub(r"[-_\.]{2,}", "-", text).strip(" ._-")
    return text or "telemetry"


def build_export_output_path(
    output_dir: str | os.PathLike[str],
    kind: TelemetryExportKind | str,
    filename_prefix: str | None = None,
    *,
    timestamp_ms: int | None = None,
) -> Path:
    export_kind = TelemetryExportKind(kind)
    directory = normalize_output_dir(output_dir)
    timestamp = int(timestamp_ms if timestamp_ms is not None else __import__("time").time() * 1000)
    stem = f"{sanitize_filename_prefix(filename_prefix)}-{export_kind.filename_fragment}-{timestamp}"
    candidate = directory / f"{stem}{export_kind.extension}"
    suffix = 1
    while candidate.exists() or candidate.with_name(candidate.name + _TEMP_SUFFIX).exists():
        candidate = directory / f"{stem}-{suffix}{export_kind.extension}"
        suffix += 1
    return candidate


def _reserve_final_output_path(path: Path) -> Path:
    suffix = 0
    while True:
        candidate = path if suffix == 0 else path.with_name(f"{path.stem}-{suffix}{path.suffix}")
        try:
            with candidate.open("xb"):
                pass
            return candidate
        except FileExistsError:
            suffix += 1


def _create_unique_temp_path(directory: Path) -> Path:
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=".forza-telemetry-tracker-export-",
        suffix=_TEMP_SUFFIX,
        dir=directory,
    )
    os.close(file_descriptor)
    return Path(temp_name)


def export_estimate(db_path: str | os.PathLike[str]) -> dict[str, int]:
    with contextlib.closing(_connect(Path(db_path))) as con:
        raw = con.execute("SELECT COUNT(*) AS count, COALESCE(SUM(length(raw_packet)), 0) AS bytes FROM packet_blobs").fetchone()
        curated = con.execute("SELECT COUNT(*) AS count FROM lap_samples").fetchone()
        sessions = con.execute("SELECT COUNT(*) AS count FROM sessions WHERE EXISTS (SELECT 1 FROM packet_blobs WHERE packet_blobs.session_id = sessions.id) OR EXISTS (SELECT 1 FROM lap_samples WHERE lap_samples.session_id = sessions.id)").fetchone()
        laps = con.execute("SELECT COUNT(DISTINCT lap_id) AS count FROM lap_samples WHERE lap_id IS NOT NULL").fetchone()
    return {
        "raw_packet_count": int(raw["count"] or 0),
        "raw_byte_count": int(raw["bytes"] or 0),
        "curated_sample_count": int(curated["count"] or 0),
        "session_count": int(sessions["count"] or 0),
        "lap_count": int(laps["count"] or 0),
    }


def export_telemetry(
    db_path: str | os.PathLike[str],
    kind: TelemetryExportKind | str,
    output_dir: str | os.PathLike[str],
    filename_prefix: str | None = None,
    *,
    should_cancel: _CANCEL_CHECK | None = None,
    timestamp_ms: int | None = None,
) -> TelemetryExportResult:
    export_kind = TelemetryExportKind(kind)
    cancel = should_cancel or (lambda: False)
    final_path = build_export_output_path(output_dir, export_kind, filename_prefix, timestamp_ms=timestamp_ms)
    temp_path = _create_unique_temp_path(final_path.parent)
    reserved_final_path: Path | None = None
    _check_cancel(cancel)
    row_count = 0
    try:
        with contextlib.closing(_connect(Path(db_path))) as con:
            if export_kind is TelemetryExportKind.raw_binary:
                row_count = _write_raw_binary_zip(con, temp_path, cancel)
            elif export_kind is TelemetryExportKind.raw_csv:
                row_count = _write_raw_csv(con, temp_path, cancel)
            else:
                row_count = _write_curated_csv(con, temp_path, cancel)
        if row_count == 0:
            raise ValueError(_EMPTY_EXPORT_MESSAGE)
        _check_cancel(cancel)
        reserved_final_path = _reserve_final_output_path(final_path)
        final_path = reserved_final_path
        os.replace(temp_path, final_path)
        reserved_final_path = None
    except Exception:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        if reserved_final_path is not None:
            try:
                reserved_final_path.unlink()
            except FileNotFoundError:
                pass
        raise
    exported = ExportedFile(final_path, final_path.name, final_path.stat().st_size)
    return TelemetryExportResult(export_kind, (exported,), exported.size_bytes, row_count)


def _safe_zip_component(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    text = text.replace("\\", "/")
    text = re.sub(r"^[A-Za-z]:", "", text)
    parts = [part for part in text.split("/") if part and part not in {".", ".."}]
    text = "-".join(parts) if parts else fallback
    text = re.sub(r"[:\\/]+", "-", text)
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip(" ._-")
    return text or fallback


def _write_raw_binary_zip(con: sqlite3.Connection, path: Path, should_cancel: _CANCEL_CHECK) -> int:
    sessions = con.execute(
        """
        SELECT s.rowid AS row_number, s.id, s.label, s.status, s.started_at_ms, s.ended_at_ms,
               COUNT(p.id) AS packet_count, COALESCE(SUM(length(p.raw_packet)), 0) AS raw_byte_count
        FROM sessions AS s
        JOIN packet_blobs AS p ON p.session_id = s.id
        GROUP BY s.rowid, s.id, s.label, s.status, s.started_at_ms, s.ended_at_ms
        ORDER BY s.started_at_ms, s.rowid
        """
    )
    manifest_rows: list[dict[str, object]] = []
    packet_count = 0
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for session_index, session in enumerate(sessions, start=1):
            _check_cancel(should_cancel)
            base = _safe_zip_component(session["label"], f"session-{session_index}")
            packet_file = f"sessions/{session_index:04d}-{base}.bin"
            packet_file = packet_file.replace("\\", "/").lstrip("/")
            with archive.open(packet_file, "w") as member:
                packet_rows = con.execute(
                    """
                    SELECT raw_packet
                    FROM packet_blobs
                    WHERE session_id = ?
                    ORDER BY sequence, id
                    """,
                    (session["id"],),
                )
                for packet in packet_rows:
                    _check_cancel(should_cancel)
                    member.write(bytes(packet["raw_packet"]))
                    packet_count += 1
            manifest_rows.append(
                {
                    "session_id": session["id"],
                    "session_label": session["label"],
                    "status": session["status"],
                    "started_at_ms": session["started_at_ms"],
                    "ended_at_ms": session["ended_at_ms"],
                    "packet_count": session["packet_count"],
                    "raw_byte_count": session["raw_byte_count"],
                    "packet_file": packet_file,
                }
            )
        if packet_count == 0:
            return 0
        _check_cancel(should_cancel)
        manifest_fields = ["session_id", "session_label", "status", "started_at_ms", "ended_at_ms", "packet_count", "raw_byte_count", "packet_file"]
        buffer = tempfile.SpooledTemporaryFile(mode="w+t", newline="", encoding="utf-8")
        try:
            writer = csv.DictWriter(buffer, fieldnames=manifest_fields)
            writer.writeheader()
            writer.writerows(manifest_rows)
            buffer.seek(0)
            archive.writestr("manifest.csv", buffer.read().encode("utf-8"))
        finally:
            buffer.close()
    return packet_count


_RAW_CSV_METADATA_FIELDS = [
    "packet_id", "session_id", "session_label", "lap_id", "sequence", "received_at_ms",
    "game_timestamp_ms", "lap_number", "position_x", "position_y", "position_z", "speed_mps",
    "packet_byte_length", "decode_error",
]


def _write_raw_csv(con: sqlite3.Connection, path: Path, should_cancel: _CANCEL_CHECK) -> int:
    rows = con.execute(
        """
        SELECT p.id AS packet_id, p.session_id, s.label AS session_label, p.lap_id, p.sequence,
               p.received_at_ms, p.game_timestamp_ms, p.lap_number, p.position_x, p.position_y,
               p.position_z, p.speed_mps, p.raw_packet
        FROM packet_blobs AS p
        JOIN sessions AS s ON s.id = p.session_id
        ORDER BY s.started_at_ms, s.rowid, p.sequence, p.id
        """
    )
    fieldnames = [*_RAW_CSV_METADATA_FIELDS, *FIELD_NAMES]
    row_count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for packet in rows:
            _check_cancel(should_cancel)
            raw = bytes(packet["raw_packet"])
            output = {field: packet[field] for field in _RAW_CSV_METADATA_FIELDS if field not in {"packet_byte_length", "decode_error"}}
            output["packet_byte_length"] = len(raw)
            try:
                decoded = decode_packet(raw)
                output["decode_error"] = ""
            except Exception as exc:  # malformed historical rows must not abort export
                decoded = {}
                output["decode_error"] = str(exc) or exc.__class__.__name__
            for field in FIELD_NAMES:
                output[field] = decoded.get(field, "")
            writer.writerow(output)
            row_count += 1
    return row_count


SUMMARY_SCALAR_FIELDS = (
    "sample_count", "packet_count", "lap_duration_ms", "distance_estimate_m", "top_speed_mps",
    "average_speed_mps", "max_throttle", "average_throttle", "max_brake", "average_brake",
    "max_combined_slip", "uncertainty_count", "lap_time_ms",
)
SESSION_FIELDS = ("id", "label", "status", "started_at_ms", "ended_at_ms", "ended_reason", "car_ordinal", "car_name", "car_class_id", "car_class_label", "car_performance_index", "drivetrain_id", "drivetrain_label", "track_profile_id")
LAP_FIELDS = ("id", "lap_number", "status", "started_at_ms", "ended_at_ms", "ended_reason", "boundary_confidence", "track_profile_id")
CAR_FIELDS = ("ordinal", "display_name", "model_short", "make", "model", "year", "base_class_label", "base_pi", "car_type", "country", "value_cr", "rarity", "source", "source_info", "asset_name", "asset_zip", "catalog_source")
TRACK_PROFILE_FIELDS = ("id", "name", "layout", "source", "confidence", "shape_signature", "created_at_ms", "updated_at_ms")
MATCH_FIELDS = ("matcher_version", "candidate_rank", "candidate_kind", "track_key", "track_profile_id", "route_id", "display_name", "confidence", "score_components_json", "reasons_json", "is_auto_assignable", "assigned_track_profile_id", "created_at_ms")


def _sample_columns(con: sqlite3.Connection) -> list[str]:
    cursor = con.execute("PRAGMA table_info(lap_samples)")
    return [str(row["name"]) for row in cursor]


def _prefixed(prefix: str, columns: Iterable[str]) -> list[str]:
    return [f"{prefix}_{column}" for column in columns]


def _write_curated_csv(con: sqlite3.Connection, path: Path, should_cancel: _CANCEL_CHECK) -> int:
    sample_columns = _sample_columns(con)
    fieldnames = [
        *_prefixed("session", SESSION_FIELDS),
        *_prefixed("lap", LAP_FIELDS),
        *_prefixed("car_catalog", CAR_FIELDS),
        *_prefixed("track_profile", TRACK_PROFILE_FIELDS),
        *_prefixed("match", MATCH_FIELDS),
        *_prefixed("summary", SUMMARY_SCALAR_FIELDS),
        *_prefixed("sample", sample_columns),
    ]
    sample_select = ", ".join(f"ls.{column} AS sample_{column}" for column in sample_columns)
    summary_select = ", ".join(
        f"CASE WHEN json_valid(summary.summary_json) THEN json_extract(summary.summary_json, '$.{field}') END AS summary_{field}"
        for field in SUMMARY_SCALAR_FIELDS
    )
    select_columns = [
        *(f"s.{column} AS session_{column}" for column in SESSION_FIELDS),
        *(f"lap.{column} AS lap_{column}" for column in LAP_FIELDS),
        *(f"car.{column} AS car_catalog_{column}" for column in CAR_FIELDS),
        *(f"tp.{column} AS track_profile_{column}" for column in TRACK_PROFILE_FIELDS),
        *(f"match.{column} AS match_{column}" for column in MATCH_FIELDS),
        summary_select,
        sample_select,
    ]
    rows = con.execute(
        f"""
        SELECT {", ".join(select_columns)}
        FROM lap_samples AS ls
        JOIN sessions AS s ON s.id = ls.session_id
        LEFT JOIN laps AS lap ON lap.id = ls.lap_id
        LEFT JOIN cars AS car ON car.ordinal = s.car_ordinal
        LEFT JOIN track_profiles AS tp ON tp.id = COALESCE(lap.track_profile_id, s.track_profile_id)
        LEFT JOIN (
            SELECT *
            FROM (
                SELECT track_match_candidates.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY lap_id
                           ORDER BY created_at_ms DESC, matcher_version DESC, candidate_rank ASC
                       ) AS export_match_rank
                FROM track_match_candidates
                WHERE candidate_rank = 1
            )
            WHERE export_match_rank = 1
        ) AS match ON match.lap_id = ls.lap_id
        LEFT JOIN lap_summaries AS summary ON summary.lap_id = ls.lap_id
        ORDER BY s.started_at_ms, s.rowid, lap.started_at_ms, lap.rowid, ls.sequence, ls.id
        """
    )
    row_count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            _check_cancel(should_cancel)
            writer.writerow({field: row[field] for field in fieldnames})
            row_count += 1
    return row_count
