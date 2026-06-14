from __future__ import annotations

import concurrent.futures
import csv
import inspect
import json
import os
import threading
import time
import zipfile
from pathlib import Path

import pytest

from telemetry_tracker.export import (
    CAR_FIELDS,
    LAP_FIELDS,
    MATCH_FIELDS,
    SESSION_FIELDS,
    SUMMARY_SCALAR_FIELDS,
    TRACK_PROFILE_FIELDS,
    TelemetryExportKind,
    build_export_output_path,
    export_estimate,
    export_telemetry,
    normalize_output_dir,
    sanitize_filename_prefix,
)
from telemetry_tracker.packet_bridge import FIELD_NAMES, decode_packet, encode_packet_for_test, packet_to_live_fields
from telemetry_tracker.storage import TelemetryStore


def _race_packet(index: int, **overrides) -> bytes:
    values = {
        "IsRaceOn": 1,
        "TimestampMS": index * 16,
        "CurrentEngineRpm": 3500.0,
        "CarClass": 4,
        "CarPerformanceIndex": 800,
        "DrivetrainType": 2,
        "PositionX": float(index),
        "PositionY": 0.0,
        "PositionZ": float(index) * 2.0,
        "Speed": 30.0 + index,
        "CurrentLap": float(index) / 10.0,
        "CurrentRaceTime": float(index) / 10.0,
        "LapNumber": 1,
    }
    values.update(overrides)
    return encode_packet_for_test(values)


def _store(tmp_path: Path) -> TelemetryStore:
    store = TelemetryStore(tmp_path / "telemetry_tracker.sqlite3")
    store.migrate()
    return store


def _insert_samples(store: TelemetryStore, session_id: str, raw_packets: list[bytes], *, lap_id: str | None = None, sequences: list[int] | None = None) -> list[dict]:
    decoded_packets = [decode_packet(raw) for raw in raw_packets]
    samples = []
    for index, decoded in enumerate(decoded_packets):
        sequence = sequences[index] if sequences is not None else index + 1
        sample = {
            **packet_to_live_fields(decoded, sequence, index * 16),
            "lap_id": lap_id,
            "uncertainty": None,
        }
        samples.append(sample)
    store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)
    return samples


def _seed_raw_store(tmp_path: Path) -> tuple[TelemetryStore, str, str]:
    store = _store(tmp_path)
    first = store.create_session("Session A", status="complete")
    second = store.create_session("../C:/unsafe\\session", status="complete")
    with store.connect() as con:
        con.execute("UPDATE sessions SET started_at_ms = 200, ended_at_ms = 260 WHERE id = ?", (first,))
        con.execute("UPDATE sessions SET started_at_ms = 100, ended_at_ms = 160 WHERE id = ?", (second,))
    _insert_samples(store, first, [_race_packet(20), _race_packet(10)], sequences=[2, 1])
    _insert_samples(store, second, [_race_packet(1)], sequences=[1])
    return store, first, second


def _seed_curated_store(tmp_path: Path) -> tuple[TelemetryStore, str, str]:
    store = _store(tmp_path)
    session_id = store.create_session("Curated Session", status="complete")
    lap_id = store.create_lap(session_id, 7, "high")
    with store.connect() as con:
        con.execute(
            """
            UPDATE sessions
            SET started_at_ms = 1000, ended_at_ms = 2000, car_ordinal = 123,
                car_name = 'Catalog Car', car_class_id = 4, car_class_label = 'S1',
                car_performance_index = 800, drivetrain_id = 2, drivetrain_label = 'AWD'
            WHERE id = ?
            """,
            (session_id,),
        )
        con.execute("UPDATE laps SET started_at_ms = 1100, ended_at_ms = 1900, status = 'complete' WHERE id = ?", (lap_id,))
        con.execute(
            """
            INSERT INTO cars(ordinal, display_name, model_short, make, model, year, base_class_label,
                             base_pi, car_type, country, value_cr, rarity, source, source_info,
                             asset_name, asset_zip, catalog_source, updated_at_ms)
            VALUES (123, 'Catalog Car', 'Cat', 'Make', 'Model', 2026, 'A', 700, 'Coupe', 'UK',
                    100000, 'Rare', 'test', 'fixture', 'asset', 'asset.zip', 'unit-test', 1200)
            """
        )
        con.execute(
            """
            INSERT INTO track_profiles(id, owner_user_id, name, layout, source, confidence,
                                       shape_signature, created_at_ms, updated_at_ms)
            VALUES ('track-profile-1', NULL, 'Cathedral Circuit', 'Full', 'manual', 'high', 'abc', 1, 2)
            """
        )
        con.execute("UPDATE laps SET track_profile_id = 'track-profile-1' WHERE id = ?", (lap_id,))
        con.execute(
            """
            INSERT INTO game_tracks(track_key, source_dataset_key, route_id, display_name, catalog_source, updated_at_ms)
            VALUES ('route-1', 44, 44, 'Matched Track', 'unit-test', 1300)
            """
        )
        con.execute(
            """
            INSERT INTO track_match_candidates(lap_id, session_id, matcher_version, candidate_rank,
                candidate_kind, track_key, track_profile_id, route_id, display_name, confidence,
                score_components_json, reasons_json, is_auto_assignable, assigned_track_profile_id, created_at_ms)
            VALUES (?, ?, 'matcher-v1', 1, 'game_track', 'route-1', 'track-profile-1', 44,
                    'Matched Track', 0.98, '{"distance": 1}', '["close"]', 1, 'track-profile-1', 1300)
            """,
            (lap_id, session_id),
        )
        summary = {field: index + 1 for index, field in enumerate(SUMMARY_SCALAR_FIELDS)}
        con.execute(
            "INSERT INTO lap_summaries(lap_id, summary_json, created_at_ms, updated_at_ms) VALUES (?, ?, 1, 2)",
            (lap_id, json.dumps(summary)),
        )
    _insert_samples(store, session_id, [_race_packet(1), _race_packet(2)], lap_id=lap_id)
    return store, session_id, lap_id


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_normalize_output_dir_trims_expands_creates_rejects_files_and_probes_writable(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("USERPROFILE", str(home))
    path = normalize_output_dir(f' "{tmp_path / "missing"}" ')
    assert path == (tmp_path / "missing").resolve()
    assert path.is_dir()
    assert not list(path.glob(".forza-telemetry-tracker-export-probe-*"))

    expanded = normalize_output_dir("~/exports")
    assert expanded == (home / "exports").resolve()

    existing_file = tmp_path / "file.txt"
    existing_file.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory"):
        normalize_output_dir(existing_file)


def test_normalize_output_dir_rejects_unwritable_probe_failures(tmp_path, monkeypatch):
    original_open = Path.open

    def failing_probe_open(self, *args, **kwargs):
        if self.name.startswith(".forza-telemetry-tracker-export-probe-"):
            raise OSError("permission denied")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_probe_open)
    with pytest.raises(ValueError, match="not writable"):
        normalize_output_dir(tmp_path / "exports")


def test_build_export_output_path_sanitizes_and_never_overwrites(tmp_path):
    first = build_export_output_path(tmp_path, TelemetryExportKind.raw_csv, " ../bad: prefix ", timestamp_ms=123)
    assert first.name == "bad-prefix-raw-123.csv"
    first.write_text("exists", encoding="utf-8")
    second = build_export_output_path(tmp_path, TelemetryExportKind.raw_csv, " ../bad: prefix ", timestamp_ms=123)
    assert second.name == "bad-prefix-raw-123-1.csv"
    second.with_name(second.name + ".forza-telemetry-tracker-export.tmp").write_text("temp", encoding="utf-8")
    third = build_export_output_path(tmp_path, TelemetryExportKind.raw_csv, " ../bad: prefix ", timestamp_ms=123)
    assert third.name == "bad-prefix-raw-123-2.csv"
    assert sanitize_filename_prefix("../bad: prefix") == "bad-prefix"


def test_raw_binary_export_zip_manifest_order_packet_order_and_safe_member_names(tmp_path):
    store, first, second = _seed_raw_store(tmp_path)
    result = export_telemetry(store.db_path, TelemetryExportKind.raw_binary, tmp_path / "exports", "dump", timestamp_ms=456)
    zip_path = result.output_files[0].path
    assert zip_path.name == "dump-raw-binary-456.zip"
    assert result.row_count == 3

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        assert names[-1] == "manifest.csv"
        for name in names:
            assert ".." not in name
            assert ":" not in name
            assert "\\" not in name
            assert not name.startswith("/")
        manifest = list(csv.DictReader(archive.read("manifest.csv").decode("utf-8").splitlines()))
        assert [row["session_id"] for row in manifest] == [second, first]
        unsafe_member = manifest[0]["packet_file"]
        assert unsafe_member.startswith("sessions/")
        assert int(manifest[0]["packet_count"]) == 1
        first_payload = archive.read(manifest[1]["packet_file"])
        assert first_payload == _race_packet(10) + _race_packet(20)


def test_raw_csv_exports_metadata_field_names_and_decode_errors(tmp_path):
    store, session_id, _second = _seed_raw_store(tmp_path)
    with store.connect() as con:
        con.execute(
            """
            INSERT INTO packet_blobs(session_id, lap_id, sequence, received_at_ms, game_timestamp_ms,
                                     lap_number, position_x, position_y, position_z, speed_mps, raw_packet)
            VALUES (?, NULL, 99, 1, 2, 3, 4, 5, 6, 7, ?)
            """,
            (session_id, b"bad"),
        )
    result = export_telemetry(store.db_path, "raw_csv", tmp_path / "exports", "raw", timestamp_ms=1)
    rows = _read_csv(result.output_files[0].path)
    assert result.row_count == 4
    assert list(rows[0].keys()) == [
        "packet_id", "session_id", "session_label", "lap_id", "sequence", "received_at_ms",
        "game_timestamp_ms", "lap_number", "position_x", "position_y", "position_z", "speed_mps",
        "packet_byte_length", "decode_error", *FIELD_NAMES,
    ]
    malformed = next(row for row in rows if row["sequence"] == "99")
    assert malformed["packet_byte_length"] == "3"
    assert malformed["decode_error"]
    assert all(malformed[field] == "" for field in FIELD_NAMES)


def test_raw_and_curated_exports_stream_cursor_rows_without_fetchall():
    import telemetry_tracker.export as export_module

    source = inspect.getsource(export_module)
    assert ".fetchall(" not in source
    assert "for packet in rows" in source
    assert "for row in rows" in source


def test_curated_csv_flattens_joined_summary_and_all_sample_columns(tmp_path):
    store, session_id, lap_id = _seed_curated_store(tmp_path)
    result = export_telemetry(store.db_path, TelemetryExportKind.curated_csv, tmp_path / "exports", "curated", timestamp_ms=2)
    rows = _read_csv(result.output_files[0].path)
    assert result.row_count == 2
    assert len(rows) == 2
    row = rows[0]
    assert row["session_id"] == session_id
    assert row["session_label"] == "Curated Session"
    assert row["lap_id"] == lap_id
    assert row["lap_lap_number"] == "7"
    assert row["car_catalog_display_name"] == "Catalog Car"
    assert row["track_profile_name"] == "Cathedral Circuit"
    assert row["match_candidate_rank"] == "1"
    assert row["match_display_name"] == "Matched Track"
    assert row["summary_sample_count"] == "1"
    assert row["summary_lap_time_ms"] == str(len(SUMMARY_SCALAR_FIELDS))
    assert row["sample_session_id"] == session_id
    assert row["sample_lap_id"] == lap_id
    assert row["sample_sequence"] == "1"


def test_curated_csv_column_regression_matches_fixed_columns_plus_current_lap_samples(tmp_path):
    store, _session_id, _lap_id = _seed_curated_store(tmp_path)
    result = export_telemetry(store.db_path, TelemetryExportKind.curated_csv, tmp_path / "exports", "curated", timestamp_ms=3)
    with store.connect() as con:
        sample_columns = [row["name"] for row in con.execute("PRAGMA table_info(lap_samples)")]
    expected = [
        *[f"session_{column}" for column in SESSION_FIELDS],
        *[f"lap_{column}" for column in LAP_FIELDS],
        *[f"car_catalog_{column}" for column in CAR_FIELDS],
        *[f"track_profile_{column}" for column in TRACK_PROFILE_FIELDS],
        *[f"match_{column}" for column in MATCH_FIELDS],
        *[f"summary_{column}" for column in SUMMARY_SCALAR_FIELDS],
        *[f"sample_{column}" for column in sample_columns],
    ]
    with result.output_files[0].path.open(newline="", encoding="utf-8") as handle:
        assert next(csv.reader(handle)) == expected


@pytest.mark.parametrize("kind", [TelemetryExportKind.raw_binary, TelemetryExportKind.raw_csv, TelemetryExportKind.curated_csv])
def test_empty_exports_raise_and_leave_no_final_output(tmp_path, kind):
    store = _store(tmp_path)
    output_dir = tmp_path / "exports"
    with pytest.raises(ValueError, match="No recorded telemetry is available to export"):
        export_telemetry(store.db_path, kind, output_dir, "empty", timestamp_ms=10)
    assert not list(output_dir.glob("empty-*"))


def test_export_estimate_counts_raw_curated_sessions_and_laps(tmp_path):
    store, session_id, lap_id = _seed_curated_store(tmp_path)
    estimate = export_estimate(store.db_path)
    assert estimate == {
        "raw_packet_count": 2,
        "raw_byte_count": sum(len(_race_packet(index)) for index in [1, 2]),
        "curated_sample_count": 2,
        "session_count": 1,
        "lap_count": 1,
    }


def test_cancellation_after_first_row_removes_temp_and_final_files(tmp_path):
    store, _first, _second = _seed_raw_store(tmp_path)
    calls = {"count": 0}

    def should_cancel() -> bool:
        calls["count"] += 1
        return calls["count"] >= 4

    output_dir = tmp_path / "exports"
    with pytest.raises(InterruptedError):
        export_telemetry(store.db_path, TelemetryExportKind.raw_csv, output_dir, "cancel", should_cancel=should_cancel, timestamp_ms=1)
    assert not list(output_dir.glob("cancel-*"))


def test_cancellation_after_writer_completes_before_replace_removes_temp_and_final(tmp_path):
    store = _store(tmp_path)
    session_id = store.create_session("One row", status="complete")
    _insert_samples(store, session_id, [_race_packet(1)])
    calls = {"count": 0}

    def should_cancel() -> bool:
        calls["count"] += 1
        return calls["count"] >= 3

    output_dir = tmp_path / "exports"
    with pytest.raises(InterruptedError):
        export_telemetry(store.db_path, TelemetryExportKind.raw_csv, output_dir, "late", should_cancel=should_cancel, timestamp_ms=1)
    assert not list(output_dir.glob("late-*"))


def test_replace_failure_cleans_temp_and_reserved_final_file(tmp_path, monkeypatch):
    store = _store(tmp_path)
    session_id = store.create_session("One row", status="complete")
    _insert_samples(store, session_id, [_race_packet(1)])
    final_paths: list[Path] = []

    def failing_replace(src, dst):
        final_path = Path(dst)
        final_paths.append(final_path)
        assert final_path.exists()
        raise PermissionError("replace denied")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(PermissionError, match="replace denied"):
        export_telemetry(store.db_path, TelemetryExportKind.raw_csv, tmp_path / "exports", "replace", timestamp_ms=1)

    assert final_paths
    final_path = final_paths[0]
    assert not final_path.exists()
    assert not list(final_path.parent.glob("*.forza-telemetry-tracker-export.tmp"))


def test_export_reroutes_when_final_file_appears_before_replace(tmp_path):
    store = _store(tmp_path)
    session_id = store.create_session("One row", status="complete")
    _insert_samples(store, session_id, [_race_packet(1)])
    output_dir = tmp_path / "exports"
    original_final = output_dir / "race-raw-777.csv"
    suffixed_final = output_dir / "race-raw-777-1.csv"
    calls = {"count": 0}

    def create_raced_final_before_replace() -> bool:
        calls["count"] += 1
        if calls["count"] == 3:
            original_final.write_text("do not overwrite", encoding="utf-8")
            suffixed_final.write_text("do not overwrite either", encoding="utf-8")
        return False

    result = export_telemetry(
        store.db_path,
        TelemetryExportKind.raw_csv,
        output_dir,
        "race",
        should_cancel=create_raced_final_before_replace,
        timestamp_ms=777,
    )

    assert original_final.read_text(encoding="utf-8") == "do not overwrite"
    assert suffixed_final.read_text(encoding="utf-8") == "do not overwrite either"
    assert result.output_files[0].path == output_dir / "race-raw-777-2.csv"
    assert result.output_files[0].path.exists()
    assert not list(output_dir.glob("*.forza-telemetry-tracker-export.tmp"))


def test_concurrent_exports_from_same_candidate_use_distinct_unique_temp_files(tmp_path, monkeypatch):
    store = _store(tmp_path)
    session_id = store.create_session("One row", status="complete")
    _insert_samples(store, session_id, [_race_packet(1)])
    output_dir = tmp_path / "exports"
    timeout_seconds = 60.0
    both_writers_ready = threading.Event()
    release_writers = threading.Event()
    temp_paths_lock = threading.Lock()
    temp_paths: list[Path] = []

    import telemetry_tracker.export as export_module

    original_write_raw_csv = export_module._write_raw_csv

    def waiting_write_raw_csv(con, path, should_cancel):
        with temp_paths_lock:
            temp_paths.append(Path(path))
            if len(temp_paths) == 2:
                both_writers_ready.set()
        if not release_writers.wait(timeout=timeout_seconds):
            raise AssertionError("Timed out waiting for the test to release concurrent exports")
        return original_write_raw_csv(con, path, should_cancel)

    monkeypatch.setattr(export_module, "_write_raw_csv", waiting_write_raw_csv)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                export_telemetry,
                store.db_path,
                TelemetryExportKind.raw_csv,
                output_dir,
                "same",
                timestamp_ms=999,
            )
            for _index in range(2)
        ]
        deadline = time.monotonic() + timeout_seconds
        try:
            while not both_writers_ready.is_set():
                for future in futures:
                    if future.done():
                        future.result()
                if time.monotonic() >= deadline:
                    with temp_paths_lock:
                        observed_temp_paths = list(temp_paths)
                    raise AssertionError(
                        "Timed out waiting for both concurrent exports to reach raw CSV writing; "
                        f"observed temp paths: {observed_temp_paths!r}"
                    )
                both_writers_ready.wait(timeout=0.05)
        finally:
            release_writers.set()
        results = [future.result(timeout=timeout_seconds) for future in futures]

    output_paths = [result.output_files[0].path for result in results]
    assert set(output_paths) == {output_dir / "same-raw-999.csv", output_dir / "same-raw-999-1.csv"}
    assert len(temp_paths) == 2
    assert temp_paths[0] != temp_paths[1]
    assert all(path.name.startswith(".forza-telemetry-tracker-export-") for path in temp_paths)
    assert not list(output_dir.glob("*.forza-telemetry-tracker-export.tmp"))
    assert len(_read_csv(output_paths[0])) == 1
    assert len(_read_csv(output_paths[1])) == 1


def test_curated_csv_selects_one_latest_rank_one_match_per_lap(tmp_path):
    store, _session_id, lap_id = _seed_curated_store(tmp_path)
    with store.connect() as con:
        con.execute(
            """
            INSERT INTO track_match_candidates(lap_id, session_id, matcher_version, candidate_rank,
                candidate_kind, track_key, track_profile_id, route_id, display_name, confidence,
                score_components_json, reasons_json, is_auto_assignable, assigned_track_profile_id, created_at_ms)
            SELECT ?, id, 'matcher-v2', 1, 'game_track', 'route-1', 'track-profile-1', 44,
                   'Newer Matched Track', 0.88, '{"distance": 2}', '["newer"]', 1, 'track-profile-1', 1400
            FROM sessions
            WHERE label = 'Curated Session'
            """,
            (lap_id,),
        )
    result = export_telemetry(store.db_path, TelemetryExportKind.curated_csv, tmp_path / "exports", "curated", timestamp_ms=4)
    rows = _read_csv(result.output_files[0].path)

    assert result.row_count == 2
    assert len(rows) == 2
    assert {row["sample_id"] for row in rows}
    assert [row["match_matcher_version"] for row in rows] == ["matcher-v2", "matcher-v2"]
    assert [row["match_display_name"] for row in rows] == ["Newer Matched Track", "Newer Matched Track"]
