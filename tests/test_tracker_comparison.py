import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from telemetry_tracker.comparison import (
    DEFAULT_SCOPE,
    SUPPORTED_SCOPES,
    context_key_for_lap,
    delta_summary,
    ghost_samples_for_reference,
    select_reference_lap,
)
from telemetry_tracker.storage import LOCAL_USER_ID, SCHEMA_VERSION, TelemetryStore


DEFAULT_CONTEXTS = {
    "track": "emerald-circuit",
    "track_car": "emerald-circuit|2005-porsche-cayman-gt3",
    "track_car_build": "emerald-circuit|2005-porsche-cayman-gt3|wtac",
}


def _store_in(tmp: str) -> TelemetryStore:
    store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
    store.migrate()
    return store


def _create_legacy_v2_database_without_comparison_refs(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    try:
        with con:
            con.executescript(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at_ms INTEGER NOT NULL
                );
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL
                );
                CREATE TABLE auth_identities (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    provider TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    UNIQUE(provider, subject)
                );
                CREATE TABLE user_settings (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    capture_mode TEXT NOT NULL,
                    udp_host TEXT NOT NULL,
                    udp_port INTEGER NOT NULL,
                    preferred_overlay TEXT NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    label TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'recording',
                    started_at_ms INTEGER NOT NULL,
                    ended_at_ms INTEGER,
                    ended_reason TEXT
                );
                CREATE TABLE laps (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    lap_number INTEGER,
                    status TEXT NOT NULL DEFAULT 'recording',
                    started_at_ms INTEGER NOT NULL,
                    ended_at_ms INTEGER,
                    ended_reason TEXT,
                    boundary_confidence TEXT NOT NULL DEFAULT 'unknown'
                );
                CREATE TABLE packet_blobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    lap_id TEXT REFERENCES laps(id) ON DELETE SET NULL,
                    sequence INTEGER NOT NULL,
                    received_at_ms INTEGER NOT NULL,
                    game_timestamp_ms INTEGER NOT NULL,
                    lap_number INTEGER NOT NULL,
                    position_x REAL NOT NULL,
                    position_y REAL NOT NULL,
                    position_z REAL NOT NULL,
                    speed_mps REAL NOT NULL,
                    raw_packet BLOB NOT NULL
                );
                CREATE TABLE lap_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    lap_id TEXT REFERENCES laps(id) ON DELETE SET NULL,
                    sequence INTEGER NOT NULL,
                    received_at_ms INTEGER NOT NULL,
                    game_timestamp_ms INTEGER NOT NULL,
                    lap_number INTEGER NOT NULL,
                    current_lap REAL NOT NULL,
                    current_race_time REAL NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    z REAL NOT NULL,
                    speed_mps REAL NOT NULL,
                    throttle INTEGER NOT NULL,
                    brake INTEGER NOT NULL,
                    steer INTEGER NOT NULL,
                    gear INTEGER NOT NULL,
                    combined_slip REAL,
                    rear_combined_slip REAL,
                    tire_temp_front_left REAL,
                    tire_temp_front_right REAL,
                    tire_temp_rear_left REAL,
                    tire_temp_rear_right REAL,
                    suspension_travel_front_left REAL,
                    suspension_travel_front_right REAL,
                    suspension_travel_rear_left REAL,
                    suspension_travel_rear_right REAL,
                    current_rpm REAL,
                    engine_max_rpm REAL
                );
                CREATE TABLE lap_summaries (
                    lap_id TEXT PRIMARY KEY REFERENCES laps(id) ON DELETE CASCADE,
                    summary_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE issue_markers (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    lap_id TEXT REFERENCES laps(id) ON DELETE CASCADE,
                    start_sequence INTEGER NOT NULL,
                    end_sequence INTEGER NOT NULL,
                    metric TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    ruleset_version INTEGER NOT NULL,
                    confidence REAL NOT NULL
                );
                """
            )
            con.executemany(
                "INSERT INTO schema_migrations(version, applied_at_ms) VALUES (?, ?)",
                [(1, 1_000), (2, 2_000)],
            )
            con.execute(
                "INSERT INTO users(id, display_name, created_at_ms) VALUES (?, ?, ?)",
                (LOCAL_USER_ID, "Local User", 1_000),
            )
            con.execute(
                """
                INSERT INTO auth_identities(id, user_id, provider, subject, created_at_ms)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("legacy-auth", LOCAL_USER_ID, "local", "local", 1_000),
            )
            con.execute(
                """
                INSERT INTO user_settings(user_id, capture_mode, udp_host, udp_port, preferred_overlay, updated_at_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (LOCAL_USER_ID, "auto", "127.0.0.1", 5400, "issues", 1_000),
            )
    finally:
        con.close()


def _add_reference_lap(
    store: TelemetryStore,
    *,
    label: str,
    lap_number: int,
    started_at_ms: int,
    ended_at_ms: int,
    lap_duration_ms: int | None,
    status: str = "lap_boundary",
    ended_reason: str | None = None,
    boundary_confidence: str = "game_field",
    uncertainty_count: int = 0,
    summary_packet_count: int = 8,
    stored_sample_count: int = 2,
    comparison_contexts: dict | None = None,
    session_id: str | None = None,
    track_profile_id: str | None = None,
) -> str:
    created_session = session_id is None
    if session_id is None:
        session_id = store.create_session(label=label)
    lap_id = store.create_lap(
        session_id=session_id,
        lap_number=lap_number,
        boundary_confidence=boundary_confidence,
    )
    reason = ended_reason or status
    store.finalize_lap(lap_id, reason=reason)
    with store.connect() as con:
        if created_session:
            con.execute(
                "UPDATE sessions SET started_at_ms = ?, ended_at_ms = ?, status = ? WHERE id = ?",
                (started_at_ms - 100, ended_at_ms + 100, "complete", session_id),
            )
        else:
            con.execute(
                """
                UPDATE sessions
                SET started_at_ms = MIN(COALESCE(started_at_ms, ?), ?),
                    ended_at_ms = MAX(COALESCE(ended_at_ms, ?), ?),
                    status = ?
                WHERE id = ?
                """,
                (started_at_ms - 100, started_at_ms - 100, ended_at_ms + 100, ended_at_ms + 100, "complete", session_id),
            )
        con.execute(
            """
            UPDATE laps
            SET started_at_ms = ?, ended_at_ms = ?, status = ?, ended_reason = ?,
                boundary_confidence = ?, track_profile_id = ?
            WHERE id = ?
            """,
            (started_at_ms, ended_at_ms, status, reason, boundary_confidence, track_profile_id, lap_id),
        )
    if stored_sample_count > 0:
        _insert_lap_samples(
            store,
            session_id=session_id,
            lap_id=lap_id,
            lap_number=lap_number,
            sample_count=stored_sample_count,
        )
    summary = {
        "sample_count": summary_packet_count,
        "packet_count": summary_packet_count,
        "lap_time_ms": lap_duration_ms,
        "lap_duration_ms": lap_duration_ms,
        "uncertainty_count": uncertainty_count,
        "top_speed_mps": 60.0,
    }
    if comparison_contexts is not None:
        summary["comparison_contexts"] = comparison_contexts
    store.insert_lap_summary(lap_id, summary)
    return lap_id


def _insert_lap_samples(
    store: TelemetryStore,
    *,
    session_id: str,
    lap_id: str,
    lap_number: int,
    sample_count: int,
) -> None:
    with store.connect() as con:
        con.executemany(
            """
            INSERT INTO lap_samples(
                session_id, lap_id, sequence, received_at_ms, game_timestamp_ms, lap_number,
                current_lap, current_race_time, x, y, z, speed_mps,
                throttle, brake, steer, gear
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    session_id,
                    lap_id,
                    index + 1,
                    index * 16,
                    index * 16,
                    lap_number,
                    float(index),
                    float(index),
                    float(index),
                    0.0,
                    float(index) * 2.0,
                    40.0 + index,
                    128,
                    0,
                    0,
                    4,
                )
                for index in range(sample_count)
            ],
        )


def _insert_custom_lap_samples(
    store: TelemetryStore,
    *,
    session_id: str,
    lap_id: str,
    lap_number: int,
    samples: list[dict],
) -> None:
    with store.connect() as con:
        con.executemany(
            """
            INSERT INTO lap_samples(
                session_id, lap_id, sequence, received_at_ms, game_timestamp_ms, lap_number,
                current_lap, current_race_time, x, y, z, speed_mps,
                throttle, brake, steer, gear
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    session_id,
                    lap_id,
                    int(sample["sequence"]),
                    int(sample.get("received_at_ms", sample["sequence"] * 100)),
                    int(sample.get("game_timestamp_ms", sample["sequence"] * 100)),
                    lap_number,
                    float(sample.get("current_lap", 0.0)),
                    float(sample.get("current_race_time", 0.0)),
                    float(sample.get("x", 0.0)),
                    float(sample.get("y", 0.0)),
                    float(sample.get("z", 0.0)),
                    float(sample.get("speed_mps", 0.0)),
                    int(sample.get("throttle", 128)),
                    int(sample.get("brake", 0)),
                    int(sample.get("steer", 0)),
                    int(sample.get("gear", 4)),
                )
                for sample in samples
            ],
        )


def _contexts(track: str, car: str, build: str) -> dict:
    return {
        "track": track,
        "track_car": f"{track}|{car}",
        "track_car_build": f"{track}|{car}|{build}",
    }


def _delta_sample(
    sequence: int,
    lap_progress: float,
    elapsed_ms: float,
    speed_mps: float = 50.0,
) -> dict:
    return {
        "sequence": sequence,
        "lap_progress": lap_progress,
        "elapsed_ms": elapsed_ms,
        "speed_mps": speed_mps,
    }


def _comparison_ref_count(store: TelemetryStore, scope: str, context_key: str) -> int:
    with store.connect() as con:
        return int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM comparison_refs
                WHERE scope = ? AND context_key = ?
                """,
                (scope, context_key),
            ).fetchone()[0]
        )


def _lap_session_id(store: TelemetryStore, lap_id: str) -> str:
    with store.connect() as con:
        row = con.execute(
            "SELECT session_id FROM laps WHERE id = ?",
            (lap_id,),
        ).fetchone()
    return row["session_id"]


class TrackerComparisonStorageTests(unittest.TestCase):
    def test_migration_adds_comparison_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)

            with store.connect() as con:
                tables = {
                    row["name"]
                    for row in con.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(comparison_refs)").fetchall()
                }
                indexes = {
                    row["name"]
                    for row in con.execute("PRAGMA index_list(comparison_refs)").fetchall()
                }
                versions = [
                    row["version"]
                    for row in con.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]

            self.assertEqual(SCHEMA_VERSION, 12)
            self.assertIn("comparison_refs", tables)
            self.assertIn("user_id", columns)
            self.assertIn("scope", columns)
            self.assertIn("context_key", columns)
            self.assertIn("lap_id", columns)
            self.assertIn("pinned_at_ms", columns)
            self.assertIn("idx_comparison_refs_lap", indexes)
            self.assertEqual(versions, list(range(1, SCHEMA_VERSION + 1)))

    def test_migration_v3_adds_comparison_refs_to_legacy_v2_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy-v2.sqlite3"
            _create_legacy_v2_database_without_comparison_refs(db_path)
            store = TelemetryStore(db_path)

            store.migrate()
            store.migrate()

            with store.connect() as con:
                tables = {
                    row["name"]
                    for row in con.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                versions = [
                    row["version"]
                    for row in con.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]
                version_counts = {
                    row["version"]: row["version_count"]
                    for row in con.execute(
                        """
                        SELECT version, COUNT(*) AS version_count
                        FROM schema_migrations
                        GROUP BY version
                        """
                    ).fetchall()
                }

            self.assertIn("comparison_refs", tables)
            self.assertEqual(versions, list(range(1, SCHEMA_VERSION + 1)))
            self.assertEqual(
                version_counts,
                {version: 1 for version in range(1, SCHEMA_VERSION + 1)},
            )

    def test_user_can_pin_lap_for_track_car_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            lap_id = _add_reference_lap(
                store,
                label="Emerald Circuit - Cayman GT3",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                comparison_contexts=DEFAULT_CONTEXTS,
            )

            store.pin_reference_lap(
                "track_car",
                DEFAULT_CONTEXTS["track_car"],
                lap_id,
            )

            reference = store.pinned_reference_lap(
                "track_car",
                DEFAULT_CONTEXTS["track_car"],
            )
            self.assertIsNotNone(reference)
            self.assertEqual(reference["lap_id"], lap_id)
            self.assertEqual(reference["scope"], "track_car")
            self.assertEqual(reference["context_key"], DEFAULT_CONTEXTS["track_car"])
            self.assertEqual(reference["source"], "pinned")
            self.assertIsNotNone(reference["pinned_at_ms"])

    def test_latest_pinned_ref_replaces_previous_for_same_scope_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            old_lap_id = _add_reference_lap(
                store,
                label="Old ref",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=62_000,
                comparison_contexts=DEFAULT_CONTEXTS,
            )
            new_lap_id = _add_reference_lap(
                store,
                label="New ref",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=61_000,
                comparison_contexts=DEFAULT_CONTEXTS,
            )

            store.pin_reference_lap("track_car", DEFAULT_CONTEXTS["track_car"], old_lap_id)
            store.pin_reference_lap("track_car", DEFAULT_CONTEXTS["track_car"], new_lap_id)

            reference = store.pinned_reference_lap("track_car", DEFAULT_CONTEXTS["track_car"])
            self.assertEqual(reference["lap_id"], new_lap_id)
            self.assertEqual(_comparison_ref_count(store, "track_car", DEFAULT_CONTEXTS["track_car"]), 1)

    def test_reference_query_filters_context_and_uses_best_available_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            slower_newer_lap_id = _add_reference_lap(
                store,
                label="Slower newer",
                lap_number=3,
                started_at_ms=5_000,
                ended_at_ms=6_000,
                lap_duration_ms=63_000,
                comparison_contexts=DEFAULT_CONTEXTS,
            )
            faster_older_lap_id = _add_reference_lap(
                store,
                label="Faster older",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=59_000,
                comparison_contexts=DEFAULT_CONTEXTS,
            )
            unrelated_lap_id = _add_reference_lap(
                store,
                label="Unrelated faster track",
                lap_number=1,
                started_at_ms=7_000,
                ended_at_ms=8_000,
                lap_duration_ms=1_000,
                comparison_contexts={
                    **DEFAULT_CONTEXTS,
                    "track": "other-circuit",
                },
            )
            no_context_lap_id = _add_reference_lap(
                store,
                label="No context metadata",
                lap_number=4,
                started_at_ms=9_000,
                ended_at_ms=10_000,
                lap_duration_ms=500,
                comparison_contexts=None,
            )

            candidates = store.candidate_reference_laps(
                "track",
                DEFAULT_CONTEXTS["track"],
                limit=10,
            )
            reference = store.pinned_reference_lap("track", DEFAULT_CONTEXTS["track"])
            missing_reference = store.pinned_reference_lap("track", "missing-circuit")

            candidate_ids = [candidate["lap_id"] for candidate in candidates]
            self.assertEqual(candidate_ids, [faster_older_lap_id, slower_newer_lap_id])
            self.assertNotIn(unrelated_lap_id, candidate_ids)
            self.assertNotIn(no_context_lap_id, candidate_ids)
            self.assertEqual(reference["lap_id"], faster_older_lap_id)
            self.assertEqual(reference["source"], "best_available")
            self.assertIsNone(missing_reference)

    def test_reference_query_filters_context_before_converting_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            matching_lap_id = _add_reference_lap(
                store,
                label="Matching context",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                comparison_contexts=DEFAULT_CONTEXTS,
            )
            wrong_context_lap_ids = {
                _add_reference_lap(
                    store,
                    label=f"Wrong context {index}",
                    lap_number=index + 2,
                    started_at_ms=3_000 + (index * 1_000),
                    ended_at_ms=4_000 + (index * 1_000),
                    lap_duration_ms=1_000 + index,
                    comparison_contexts={
                        **DEFAULT_CONTEXTS,
                        "track": f"wrong-circuit-{index}",
                    },
                )
                for index in range(20)
            }

            converted_lap_ids = []
            original_from_row = store._reference_lap_from_row

            def counting_from_row(row, **kwargs):
                converted_lap_ids.append(row["lap_id"])
                return original_from_row(row, **kwargs)

            store._reference_lap_from_row = counting_from_row

            candidates = store.candidate_reference_laps(
                "track",
                DEFAULT_CONTEXTS["track"],
                limit=10,
            )

            self.assertEqual([candidate["lap_id"] for candidate in candidates], [matching_lap_id])
            self.assertEqual(converted_lap_ids, [matching_lap_id])
            self.assertTrue(wrong_context_lap_ids.isdisjoint(converted_lap_ids))

    def test_reference_lookup_excludes_current_from_best_available_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            current_lap_id = _add_reference_lap(
                store,
                label="Current fastest",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=50_000,
                comparison_contexts=DEFAULT_CONTEXTS,
            )
            fallback_lap_id = _add_reference_lap(
                store,
                label="Fallback candidate",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=60_000,
                comparison_contexts=DEFAULT_CONTEXTS,
            )

            candidates = store.candidate_reference_laps(
                "track_car",
                DEFAULT_CONTEXTS["track_car"],
                limit=10,
                exclude_lap_id=current_lap_id,
            )
            fallback = store.pinned_reference_lap(
                "track_car",
                DEFAULT_CONTEXTS["track_car"],
                exclude_lap_id=current_lap_id,
            )

            self.assertEqual([candidate["lap_id"] for candidate in candidates], [fallback_lap_id])
            self.assertIsNotNone(fallback)
            self.assertEqual(fallback["lap_id"], fallback_lap_id)
            self.assertEqual(fallback["source"], "best_available")

    def test_summary_only_laps_are_ignored_without_stored_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            valid_lap_id = _add_reference_lap(
                store,
                label="Sample-backed ref",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                comparison_contexts=DEFAULT_CONTEXTS,
                stored_sample_count=2,
            )
            summary_only_lap_id = _add_reference_lap(
                store,
                label="Summary only ref",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=1_000,
                comparison_contexts=DEFAULT_CONTEXTS,
                stored_sample_count=0,
                summary_packet_count=99,
            )

            candidates = store.candidate_reference_laps(
                "track_car",
                DEFAULT_CONTEXTS["track_car"],
                limit=10,
            )

            candidate_ids = [candidate["lap_id"] for candidate in candidates]
            self.assertEqual(candidate_ids, [valid_lap_id])
            self.assertNotIn(summary_only_lap_id, candidate_ids)

    def test_insert_lap_summary_preserves_comparison_contexts_when_replacing_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            lap_id = _add_reference_lap(
                store,
                label="Context-preserving insert summary",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                comparison_contexts=DEFAULT_CONTEXTS,
            )

            store.insert_lap_summary(
                lap_id,
                {
                    "sample_count": 2,
                    "packet_count": 2,
                    "lap_duration_ms": 59_000,
                    "uncertainty_count": 0,
                    "top_speed_mps": 61.0,
                },
            )

            summary = store.lap_summary(lap_id)
            candidates = store.candidate_reference_laps(
                "track",
                DEFAULT_CONTEXTS["track"],
                limit=10,
            )
            self.assertEqual(summary["comparison_contexts"], DEFAULT_CONTEXTS)
            self.assertEqual(summary["lap_duration_ms"], 59_000)
            self.assertIn(lap_id, [candidate["lap_id"] for candidate in candidates])

    def test_replace_analysis_results_preserves_comparison_contexts_when_replacing_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            lap_id = _add_reference_lap(
                store,
                label="Context-preserving analysis summary",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                comparison_contexts=DEFAULT_CONTEXTS,
            )
            session_id = _lap_session_id(store, lap_id)

            store.replace_analysis_results(
                session_id=session_id,
                lap_id=lap_id,
                summary={
                    "sample_count": 2,
                    "packet_count": 2,
                    "lap_duration_ms": 58_000,
                    "uncertainty_count": 0,
                    "top_speed_mps": 62.0,
                },
                markers=[],
            )

            summary = store.lap_summary(lap_id)
            candidates = store.candidate_reference_laps(
                "track_car",
                DEFAULT_CONTEXTS["track_car"],
                limit=10,
            )
            self.assertEqual(summary["comparison_contexts"], DEFAULT_CONTEXTS)
            self.assertEqual(summary["lap_duration_ms"], 58_000)
            self.assertIn(lap_id, [candidate["lap_id"] for candidate in candidates])

    def test_candidate_filter_excludes_unknown_or_uncertain_boundary_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            valid_lap_id = _add_reference_lap(
                store,
                label="Known boundary confidence",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                boundary_confidence="game_field",
                comparison_contexts=DEFAULT_CONTEXTS,
            )
            unknown_lap_id = _add_reference_lap(
                store,
                label="Unknown boundary confidence",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=1_000,
                boundary_confidence="unknown",
                comparison_contexts=DEFAULT_CONTEXTS,
            )
            uncertain_lap_id = _add_reference_lap(
                store,
                label="Uncertain boundary confidence",
                lap_number=3,
                started_at_ms=5_000,
                ended_at_ms=6_000,
                lap_duration_ms=2_000,
                boundary_confidence="uncertain",
                comparison_contexts=DEFAULT_CONTEXTS,
            )

            candidates = store.candidate_reference_laps(
                "track_car_build",
                DEFAULT_CONTEXTS["track_car_build"],
                limit=10,
            )

            candidate_ids = [candidate["lap_id"] for candidate in candidates]
            self.assertEqual(candidate_ids, [valid_lap_id])
            self.assertNotIn(unknown_lap_id, candidate_ids)
            self.assertNotIn(uncertain_lap_id, candidate_ids)

    def test_candidate_filter_uses_finalized_boundary_confidence_from_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            valid_lap_id = _add_reference_lap(
                store,
                label="Known final boundary confidence",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                boundary_confidence="game_field",
                comparison_contexts=DEFAULT_CONTEXTS,
            )
            session_id = store.create_session(label="Stale initial boundary confidence")
            stale_lap_id = store.create_lap(
                session_id=session_id,
                lap_number=2,
                boundary_confidence="game_field",
            )
            _insert_lap_samples(
                store,
                session_id=session_id,
                lap_id=stale_lap_id,
                lap_number=2,
                sample_count=2,
            )
            store.insert_lap_summary(
                stale_lap_id,
                {
                    "sample_count": 2,
                    "packet_count": 2,
                    "lap_duration_ms": 1_000,
                    "uncertainty_count": 0,
                    "top_speed_mps": 60.0,
                    "comparison_contexts": DEFAULT_CONTEXTS,
                },
            )

            store.finalize_lap(
                stale_lap_id,
                reason="lap_boundary",
                boundary_confidence="uncertain",
            )

            candidates = store.candidate_reference_laps(
                "track_car_build",
                DEFAULT_CONTEXTS["track_car_build"],
                limit=10,
            )

            candidate_ids = [candidate["lap_id"] for candidate in candidates]
            self.assertIn(valid_lap_id, candidate_ids)
            self.assertNotIn(stale_lap_id, candidate_ids)

    def test_candidate_status_filter_accepts_finalized_laps_and_excludes_unusable_laps(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            allowed_lap_ids = {
                _add_reference_lap(
                    store,
                    label=f"Allowed {status}",
                    lap_number=index,
                    started_at_ms=index * 1_000,
                    ended_at_ms=index * 1_000 + 500,
                    lap_duration_ms=60_000 + index,
                    status=status,
                    boundary_confidence="heuristic" if status == "manual_stop" else "game_field",
                    comparison_contexts=DEFAULT_CONTEXTS,
                )
                for index, status in enumerate(
                    ("finalized", "lap_boundary", "manual_stop", "replay_complete"),
                    start=1,
                )
            }
            rejected_lap_ids = {
                _add_reference_lap(
                    store,
                    label=f"Rejected {status}",
                    lap_number=index,
                    started_at_ms=10_000 + index * 1_000,
                    ended_at_ms=10_000 + index * 1_000 + 500,
                    lap_duration_ms=1_000 + index,
                    status=status,
                    comparison_contexts=DEFAULT_CONTEXTS,
                )
                for index, status in enumerate(
                    (
                        "active",
                        "recording",
                        "invalid",
                        "uncertain",
                        "deleted",
                        "unavailable",
                        "event_exit",
                        "free_roam",
                        "no_lap",
                    ),
                    start=1,
                )
            }
            partial_lap_id = _add_reference_lap(
                store,
                label="Partial lap uncertainty",
                lap_number=99,
                started_at_ms=30_000,
                ended_at_ms=31_000,
                lap_duration_ms=500,
                status="lap_boundary",
                uncertainty_count=1,
                comparison_contexts=DEFAULT_CONTEXTS,
            )
            rejected_lap_ids.add(partial_lap_id)

            candidates = store.candidate_reference_laps(
                "track_car_build",
                DEFAULT_CONTEXTS["track_car_build"],
                limit=20,
            )
            candidate_ids = {candidate["lap_id"] for candidate in candidates}

            self.assertEqual(candidate_ids, allowed_lap_ids)
            self.assertTrue(rejected_lap_ids.isdisjoint(candidate_ids))

    def test_supported_scopes_are_exactly_track_track_car_and_track_car_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            lap_id = _add_reference_lap(
                store,
                label="Scoped ref",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=61_000,
                comparison_contexts=DEFAULT_CONTEXTS,
            )

            for scope, context_key in DEFAULT_CONTEXTS.items():
                with self.subTest(scope=scope):
                    store.pin_reference_lap(scope, context_key, lap_id)
                    self.assertEqual(
                        store.pinned_reference_lap(scope, context_key)["lap_id"],
                        lap_id,
                    )
                    self.assertEqual(_comparison_ref_count(store, scope, context_key), 1)
                    store.clear_reference_lap(scope, context_key)
                    self.assertEqual(_comparison_ref_count(store, scope, context_key), 0)
                    fallback = store.pinned_reference_lap(scope, context_key)
                    self.assertEqual(fallback["lap_id"], lap_id)
                    self.assertEqual(fallback["source"], "best_available")

            with store.connect() as con:
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute(
                        """
                        INSERT INTO comparison_refs(user_id, scope, context_key, lap_id, pinned_at_ms)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (LOCAL_USER_ID, "driver", "emerald", lap_id, 1_000),
                    )

            for method_name in (
                "pin_reference_lap",
                "clear_reference_lap",
                "pinned_reference_lap",
                "candidate_reference_laps",
            ):
                with self.subTest(method=method_name):
                    method = getattr(store, method_name)
                    with self.assertRaisesRegex(ValueError, "unsupported reference scope"):
                        if method_name == "pin_reference_lap":
                            method("driver", "emerald", lap_id)
                        else:
                            method("driver", "emerald")

    def test_deleted_or_unavailable_pinned_references_use_best_available_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            fallback_lap_id = _add_reference_lap(
                store,
                label="Best fallback",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=58_000,
                comparison_contexts=DEFAULT_CONTEXTS,
            )
            unavailable_lap_id = _add_reference_lap(
                store,
                label="Unavailable pinned",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=57_000,
                status="unavailable",
                comparison_contexts=DEFAULT_CONTEXTS,
            )
            deleted_lap_id = _add_reference_lap(
                store,
                label="Deleted pinned",
                lap_number=3,
                started_at_ms=5_000,
                ended_at_ms=6_000,
                lap_duration_ms=66_000,
                comparison_contexts=DEFAULT_CONTEXTS,
            )

            store.pin_reference_lap(
                "track_car_build",
                DEFAULT_CONTEXTS["track_car_build"],
                unavailable_lap_id,
            )
            unavailable_reference = store.pinned_reference_lap(
                "track_car_build",
                DEFAULT_CONTEXTS["track_car_build"],
            )
            self.assertEqual(unavailable_reference["lap_id"], fallback_lap_id)
            self.assertEqual(unavailable_reference["source"], "best_available")
            self.assertEqual(
                _comparison_ref_count(store, "track_car_build", DEFAULT_CONTEXTS["track_car_build"]),
                1,
            )

            store.pin_reference_lap(
                "track_car_build",
                DEFAULT_CONTEXTS["track_car_build"],
                deleted_lap_id,
            )
            with store.connect() as con:
                con.execute("DELETE FROM laps WHERE id = ?", (deleted_lap_id,))
            deleted_reference = store.pinned_reference_lap(
                "track_car_build",
                DEFAULT_CONTEXTS["track_car_build"],
            )
            self.assertEqual(
                _comparison_ref_count(store, "track_car_build", DEFAULT_CONTEXTS["track_car_build"]),
                0,
            )
            self.assertEqual(deleted_reference["lap_id"], fallback_lap_id)
            self.assertEqual(deleted_reference["source"], "best_available")


class TrackerComparisonEngineTests(unittest.TestCase):
    def test_context_key_for_lap_uses_stable_scope_strings(self):
        lap = {
            "track_profile_id": "emerald-circuit",
            "car_slug": "2005-porsche-cayman-gt3",
            "build_slug": "wtac",
            "session_id": "session-a",
        }

        self.assertEqual(context_key_for_lap("track", lap), "emerald-circuit")
        self.assertEqual(
            context_key_for_lap("track_car", lap),
            "emerald-circuit|2005-porsche-cayman-gt3",
        )
        self.assertEqual(
            context_key_for_lap("track_car_build", lap),
            "emerald-circuit|2005-porsche-cayman-gt3|wtac",
        )

        current_profile_lap = {
            "track_profile_id": "corrected-track",
            "summary": {
                "comparison_contexts": {
                    "track": "stored-track",
                    "track_car": "stored-track|stored-car",
                    "track_car_build": "stored-track|stored-car|stored-build",
                }
            },
        }
        self.assertEqual(
            context_key_for_lap("track_car", current_profile_lap),
            "corrected-track|stored-car",
        )
        self.assertEqual(
            context_key_for_lap("track_car_build", current_profile_lap),
            "corrected-track|stored-car|stored-build",
        )

        direct_metadata_lap = {
            "track_profile_id": "corrected-track",
            "car_slug": "direct-car",
            "build_slug": "direct-build",
            "summary": {
                "comparison_contexts": {
                    "track_car": "stored-track|stored-car",
                    "track_car_build": "stored-track|stored-car|stored-build",
                }
            },
        }
        self.assertEqual(
            context_key_for_lap("track_car_build", direct_metadata_lap),
            "corrected-track|direct-car|direct-build",
        )

        summary_context_lap = {
            "summary": {
                "comparison_contexts": {
                    "track": "stored-track",
                    "track_car": "stored-track|stored-car",
                    "track_car_build": "stored-track|stored-car|stored-build",
                }
            },
        }
        self.assertEqual(
            context_key_for_lap("track_car_build", summary_context_lap),
            "stored-track|stored-car|stored-build",
        )
        self.assertEqual(tuple(SUPPORTED_SCOPES), ("track", "track_car", "track_car_build"))

    def test_default_scope_selects_track_car_reference(self):
        self.assertEqual(DEFAULT_SCOPE, "track_car")
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            session_id = store.create_session(label="Default scope")
            current_lap_id = _add_reference_lap(
                store,
                label="Current lap",
                lap_number=10,
                started_at_ms=10_000,
                ended_at_ms=11_000,
                lap_duration_ms=60_000,
                comparison_contexts=DEFAULT_CONTEXTS,
                session_id=session_id,
                track_profile_id=profile_id,
            )
            fastest_lap_id = _add_reference_lap(
                store,
                label="Fastest lap",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=59_000,
                comparison_contexts=DEFAULT_CONTEXTS,
                session_id=session_id,
                track_profile_id=profile_id,
            )
            _add_reference_lap(
                store,
                label="Slowest lap",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=61_000,
                comparison_contexts=DEFAULT_CONTEXTS,
                session_id=session_id,
                track_profile_id=profile_id,
            )

            reference = select_reference_lap(store, current_lap_id)

            self.assertIsNotNone(reference)
            self.assertEqual(reference["lap_id"], fastest_lap_id)
            self.assertEqual(reference["scope"], "track_car")

    def test_session_best_reference_uses_fastest_assigned_track_car_lap_in_same_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            other_profile_id = store.create_track_profile("Copper Canyon", "Sprint", "manual", "user")
            session_id = store.create_session(label="Mixed session")
            current_lap_id = _add_reference_lap(
                store,
                label="Current lap",
                lap_number=3,
                started_at_ms=5_000,
                ended_at_ms=6_000,
                lap_duration_ms=60_000,
                comparison_contexts=_contexts("old-current", "car-a", "build-x"),
                session_id=session_id,
                track_profile_id=profile_id,
            )
            same_session_fastest_id = _add_reference_lap(
                store,
                label="Same session fastest",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=55_000,
                comparison_contexts=_contexts("old-expected", "car-a", "build-y"),
                session_id=session_id,
                track_profile_id=profile_id,
            )
            _add_reference_lap(
                store,
                label="Cross session faster",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=50_000,
                comparison_contexts=_contexts("old-track", "car-a", "build-z"),
                track_profile_id=profile_id,
            )
            _add_reference_lap(
                store,
                label="Wrong assigned track",
                lap_number=4,
                started_at_ms=7_000,
                ended_at_ms=8_000,
                lap_duration_ms=45_000,
                comparison_contexts=_contexts("other-track", "car-a", "build-x"),
                session_id=session_id,
                track_profile_id=other_profile_id,
            )
            _add_reference_lap(
                store,
                label="Wrong car",
                lap_number=5,
                started_at_ms=9_000,
                ended_at_ms=10_000,
                lap_duration_ms=40_000,
                comparison_contexts=_contexts("old-track", "car-b", "build-x"),
                session_id=session_id,
                track_profile_id=profile_id,
            )
            _add_reference_lap(
                store,
                label="Faster unusable same context",
                lap_number=6,
                started_at_ms=11_000,
                ended_at_ms=12_000,
                lap_duration_ms=30_000,
                status="invalid",
                comparison_contexts=_contexts("old-track", "car-a", "build-x"),
                session_id=session_id,
                track_profile_id=profile_id,
            )

            reference = select_reference_lap(store, current_lap_id, scope="track_car")

            self.assertIsNotNone(reference)
            self.assertEqual(reference["lap_id"], same_session_fastest_id)
            self.assertEqual(reference["source"], "session_best")
            self.assertEqual(reference["context_key"], f"{profile_id}|car-a")

    def test_session_best_reference_can_be_current_lap_when_current_is_fastest(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            session_id = store.create_session(label="Best current")
            current_lap_id = _add_reference_lap(
                store,
                label="Current fastest lap",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=50_000,
                comparison_contexts=_contexts("track-a", "car-a", "build-x"),
                session_id=session_id,
                track_profile_id=profile_id,
            )
            _add_reference_lap(
                store,
                label="Same session slower lap",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                comparison_contexts=_contexts("track-a", "car-a", "build-y"),
                session_id=session_id,
                track_profile_id=profile_id,
            )

            reference = select_reference_lap(store, current_lap_id, scope="track_car")

            self.assertIsNotNone(reference)
            self.assertEqual(reference["lap_id"], current_lap_id)
            self.assertEqual(reference["source"], "session_best")

    def test_session_best_reference_returns_none_without_assigned_track(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            session_id = store.create_session(label="Unassigned track")
            current_lap_id = _add_reference_lap(
                store,
                label="Current unassigned",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                comparison_contexts=_contexts("track-a", "car-a", "build-x"),
                session_id=session_id,
                track_profile_id=None,
            )
            _add_reference_lap(
                store,
                label="Same context but no assignment",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=55_000,
                comparison_contexts=_contexts("track-a", "car-a", "build-y"),
                session_id=session_id,
                track_profile_id=None,
            )

            self.assertIsNone(select_reference_lap(store, current_lap_id, scope="track_car"))

    def test_assigned_profile_candidates_preserve_summary_car_and_build_suffixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Corrected", "Full", "manual", "user")
            session_id = store.create_session(label="Profile candidates")
            current_lap_id = _add_reference_lap(
                store,
                label="Current corrected car",
                lap_number=10,
                started_at_ms=10_000,
                ended_at_ms=11_000,
                lap_duration_ms=60_000,
                comparison_contexts=_contexts("old-current-track", "car-a", "build-x"),
                session_id=session_id,
                track_profile_id=profile_id,
            )
            wrong_car_lap_id = _add_reference_lap(
                store,
                label="Wrong car corrected track",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=58_000,
                comparison_contexts=_contexts("old-wrong-track", "car-b", "build-x"),
                session_id=session_id,
                track_profile_id=profile_id,
            )
            same_build_lap_id = _add_reference_lap(
                store,
                label="Same build corrected track",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=59_000,
                comparison_contexts=_contexts("old-same-track", "car-a", "build-x"),
                session_id=session_id,
                track_profile_id=profile_id,
            )

            track_car_candidates = store.candidate_reference_laps(
                "track_car",
                f"{profile_id}|car-a",
                limit=10,
                exclude_lap_id=current_lap_id,
            )
            track_car_build_reference = select_reference_lap(
                store,
                current_lap_id,
                scope="track_car_build",
            )

            self.assertEqual(
                [candidate["lap_id"] for candidate in track_car_candidates],
                [same_build_lap_id],
            )
            self.assertNotIn(
                wrong_car_lap_id,
                [candidate["lap_id"] for candidate in track_car_candidates],
            )
            self.assertIsNotNone(track_car_build_reference)
            self.assertEqual(track_car_build_reference["lap_id"], same_build_lap_id)
            self.assertEqual(
                track_car_build_reference["context_key"],
                f"{profile_id}|car-a|build-x",
            )

    def test_session_best_reference_ignores_unusable_candidates_even_when_faster(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            session_id = store.create_session(label="Unusable faster")
            current_lap_id = _add_reference_lap(
                store,
                label="Current lap",
                lap_number=3,
                started_at_ms=5_000,
                ended_at_ms=6_000,
                lap_duration_ms=60_000,
                comparison_contexts=_contexts("track-a", "car-a", "build-x"),
                session_id=session_id,
                track_profile_id=profile_id,
            )
            valid_slower_id = _add_reference_lap(
                store,
                label="Valid slower lap",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=65_000,
                comparison_contexts=_contexts("track-a", "car-a", "build-y"),
                session_id=session_id,
                track_profile_id=profile_id,
            )
            _add_reference_lap(
                store,
                label="Faster invalid lap",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=40_000,
                status="invalid",
                comparison_contexts=_contexts("track-a", "car-a", "build-z"),
                session_id=session_id,
                track_profile_id=profile_id,
            )

            reference = select_reference_lap(store, current_lap_id, scope="track_car")

            self.assertIsNotNone(reference)
            self.assertEqual(reference["lap_id"], current_lap_id)
            self.assertEqual(reference["source"], "session_best")

    def test_select_reference_lap_ignores_persisted_pin_in_favor_of_session_best(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            session_id = store.create_session(label="Pin ignored")
            current_lap_id = _add_reference_lap(
                store,
                label="Current lap",
                lap_number=3,
                started_at_ms=5_000,
                ended_at_ms=6_000,
                lap_duration_ms=60_000,
                comparison_contexts=_contexts("old-track", "car-a", "build-x"),
                session_id=session_id,
                track_profile_id=profile_id,
            )
            session_best_id = _add_reference_lap(
                store,
                label="Session best lap",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=55_000,
                comparison_contexts=_contexts("old-track", "car-a", "build-y"),
                session_id=session_id,
                track_profile_id=profile_id,
            )
            pinned_id = _add_reference_lap(
                store,
                label="Pinned cross-session lap",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=50_000,
                comparison_contexts=_contexts("old-track", "car-a", "build-z"),
                track_profile_id=profile_id,
            )

            context_key = f"{profile_id}|car-a"
            store.pin_reference_lap("track_car", context_key, pinned_id)

            reference = select_reference_lap(store, current_lap_id, scope="track_car")

            self.assertIsNotNone(reference)
            self.assertEqual(reference["lap_id"], session_best_id)
            self.assertEqual(reference["source"], "session_best")
            self.assertNotEqual(reference["lap_id"], pinned_id)

    def test_session_best_reference_returns_none_when_no_usable_timed_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            session_id = store.create_session(label="No timed candidate")
            current_lap_id = _add_reference_lap(
                store,
                label="Unusable current lap",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=None,
                status="active",
                comparison_contexts=_contexts("track-a", "car-a", "build-x"),
                session_id=session_id,
                track_profile_id=profile_id,
            )
            _add_reference_lap(
                store,
                label="Uncertain timed lap",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=55_000,
                boundary_confidence="uncertain",
                comparison_contexts=_contexts("track-a", "car-a", "build-y"),
                session_id=session_id,
                track_profile_id=profile_id,
            )

            self.assertIsNone(select_reference_lap(store, current_lap_id, scope="track_car"))

    def test_session_best_reference_exposes_normalized_lap_time_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            session_id = store.create_session(label="Lap time aliases")
            current_lap_id = _add_reference_lap(
                store,
                label="Current best lap",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=58_000,
                comparison_contexts=_contexts("track-a", "car-a", "build-x"),
                session_id=session_id,
                track_profile_id=profile_id,
            )
            _add_reference_lap(
                store,
                label="Slower lap",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=60_000,
                comparison_contexts=_contexts("track-a", "car-a", "build-y"),
                session_id=session_id,
                track_profile_id=profile_id,
            )

            reference = select_reference_lap(store, current_lap_id, scope="track_car")

            self.assertIsNotNone(reference)
            self.assertEqual(reference["lap_id"], current_lap_id)
            self.assertEqual(reference["lap_time_ms"], 58_000)
            self.assertEqual(reference["lap_duration_ms"], 58_000)

    def test_session_best_reference_uses_row_lap_time_when_summary_duration_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            session_id = store.create_session(label="Row lap time fallback")
            current_lap_id = _add_reference_lap(
                store,
                label="Current lap",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=60_000,
                comparison_contexts=_contexts("track-a", "car-a", "build-x"),
                session_id=session_id,
                track_profile_id=profile_id,
            )
            row_timed_lap_id = _add_reference_lap(
                store,
                label="Row timed lap",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=99_000,
                comparison_contexts=_contexts("track-a", "car-a", "build-y"),
                session_id=session_id,
                track_profile_id=profile_id,
                stored_sample_count=0,
            )
            _insert_custom_lap_samples(
                store,
                session_id=session_id,
                lap_id=row_timed_lap_id,
                lap_number=1,
                samples=[
                    {"sequence": 1, "current_lap": 0.0},
                    {"sequence": 2, "current_lap": 57.5},
                ],
            )
            with store.connect() as con:
                row = con.execute(
                    "SELECT summary_json FROM lap_summaries WHERE lap_id = ?",
                    (row_timed_lap_id,),
                ).fetchone()
                summary = json.loads(row["summary_json"])
                summary["lap_time_ms"] = None
                summary["lap_duration_ms"] = 99_000
                con.execute(
                    "UPDATE lap_summaries SET summary_json = ? WHERE lap_id = ?",
                    (json.dumps(summary), row_timed_lap_id),
                )

            reference = select_reference_lap(store, current_lap_id, scope="track_car")

            self.assertIsNotNone(reference)
            self.assertEqual(reference["lap_id"], row_timed_lap_id)
            self.assertEqual(reference["lap_time_ms"], 57_500)
            self.assertEqual(reference["lap_duration_ms"], 57_500)

    def test_best_available_uses_fastest_lap_duration_when_summaries_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            session_id = store.create_session(label="Best available")
            current_lap_id = _add_reference_lap(
                store,
                label="Current lap",
                lap_number=10,
                started_at_ms=10_000,
                ended_at_ms=11_000,
                lap_duration_ms=60_000,
                comparison_contexts=DEFAULT_CONTEXTS,
                session_id=session_id,
                track_profile_id=profile_id,
            )
            _add_reference_lap(
                store,
                label="Slower candidate",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=62_000,
                comparison_contexts=DEFAULT_CONTEXTS,
                session_id=session_id,
                track_profile_id=profile_id,
            )
            faster_lap_id = _add_reference_lap(
                store,
                label="Faster candidate",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=58_000,
                comparison_contexts=DEFAULT_CONTEXTS,
                session_id=session_id,
                track_profile_id=profile_id,
            )

            reference = select_reference_lap(store, current_lap_id, scope="track_car")

            self.assertIsNotNone(reference)
            self.assertEqual(reference["lap_id"], faster_lap_id)

    def test_unknown_track_context_is_stable_and_empty_when_no_safe_candidate(self):
        self.assertEqual(
            context_key_for_lap(
                "track",
                {
                    "track_signature": "shape-abc123",
                    "session_id": "session-a",
                },
            ),
            "unknown_track:shape-abc123",
        )
        self.assertEqual(
            context_key_for_lap("track", {"session_id": "session-b"}),
            "unknown_track:session-b",
        )
        self.assertEqual(
            context_key_for_lap(
                "track_car",
                {
                    "summary": {"track_signature": "shape-abc123"},
                    "session_id": "session-c",
                },
            ),
            "unknown_track:shape-abc123|unknown_car",
        )

        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            current_lap_id = _add_reference_lap(
                store,
                label="Unknown current",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                comparison_contexts=None,
            )
            store.insert_lap_summary(
                current_lap_id,
                {
                    "sample_count": 2,
                    "packet_count": 2,
                    "lap_duration_ms": 60_000,
                    "uncertainty_count": 0,
                    "track_signature": "shape-abc123",
                },
            )

            self.assertIsNone(select_reference_lap(store, current_lap_id, scope="track_car"))

    def test_ghost_samples_include_distance_based_lap_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            lap_id = _add_reference_lap(
                store,
                label="Ghost source",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                stored_sample_count=0,
                comparison_contexts=DEFAULT_CONTEXTS,
            )
            _insert_custom_lap_samples(
                store,
                session_id=_lap_session_id(store, lap_id),
                lap_id=lap_id,
                lap_number=1,
                samples=[
                    {"sequence": 1, "x": 0.0, "speed_mps": 40.0},
                    {"sequence": 2, "x": 10.0, "speed_mps": 50.0},
                    {"sequence": 3, "x": 40.0, "speed_mps": 60.0},
                ],
            )

            ghost_samples = ghost_samples_for_reference(store, lap_id)

            self.assertEqual([sample["sequence"] for sample in ghost_samples], [1, 2, 3])
            self.assertAlmostEqual(ghost_samples[0]["lap_progress"], 0.0)
            self.assertAlmostEqual(ghost_samples[1]["lap_progress"], 0.25)
            self.assertAlmostEqual(ghost_samples[2]["lap_progress"], 1.0)
            self.assertAlmostEqual(ghost_samples[1]["speed_mps"], 50.0)

    def test_delta_summary_resamples_reference_by_progress_and_reports_metrics(self):
        current_samples = [
            {
                "sequence": 1,
                "game_timestamp_ms": 0,
                "current_lap": 0.0,
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "speed_mps": 50.0,
            },
            {
                "sequence": 2,
                "game_timestamp_ms": 4_000,
                "current_lap": 4.0,
                "x": 50.0,
                "y": 0.0,
                "z": 0.0,
                "speed_mps": 60.0,
            },
            {
                "sequence": 3,
                "game_timestamp_ms": 8_000,
                "current_lap": 8.0,
                "x": 100.0,
                "y": 0.0,
                "z": 0.0,
                "speed_mps": 70.0,
            },
        ]
        reference_samples = [
            {
                "sequence": 10,
                "game_timestamp_ms": 0,
                "current_lap": 0.0,
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "speed_mps": 40.0,
            },
            {
                "sequence": 11,
                "game_timestamp_ms": 2_500,
                "current_lap": 2.5,
                "x": 25.0,
                "y": 0.0,
                "z": 0.0,
                "speed_mps": 45.0,
            },
            {
                "sequence": 12,
                "game_timestamp_ms": 5_000,
                "current_lap": 5.0,
                "x": 50.0,
                "y": 0.0,
                "z": 0.0,
                "speed_mps": 55.0,
            },
            {
                "sequence": 13,
                "game_timestamp_ms": 7_500,
                "current_lap": 7.5,
                "x": 75.0,
                "y": 0.0,
                "z": 0.0,
                "speed_mps": 65.0,
            },
            {
                "sequence": 14,
                "game_timestamp_ms": 10_000,
                "current_lap": 10.0,
                "x": 100.0,
                "y": 0.0,
                "z": 0.0,
                "speed_mps": 80.0,
            },
        ]

        full_lap_summary = delta_summary(current_samples, reference_samples)
        summary = delta_summary(
            current_samples,
            reference_samples,
            start_sequence=2,
            end_sequence=2,
        )

        self.assertAlmostEqual(full_lap_summary["time_delta_ms"], -2_000.0)
        self.assertAlmostEqual(full_lap_summary["max_gain_ms"], 2_000.0)
        self.assertAlmostEqual(full_lap_summary["max_loss_ms"], 0.0)
        self.assertEqual(summary["start_sequence"], 2)
        self.assertEqual(summary["end_sequence"], 2)
        self.assertEqual(summary["sample_count"], 1)
        self.assertIn("time_delta_ms", summary)
        self.assertIn("average_speed_delta_mps", summary)
        self.assertIn("max_gain_ms", summary)
        self.assertIn("max_loss_ms", summary)
        self.assertEqual(len(summary["points"]), 1)
        point = summary["points"][0]
        self.assertAlmostEqual(point["lap_progress"], 0.5)
        self.assertAlmostEqual(point["reference_elapsed_ms"], 5_000.0)
        self.assertAlmostEqual(point["time_delta_ms"], -1_000.0)
        self.assertAlmostEqual(summary["time_delta_ms"], 0.0)
        self.assertAlmostEqual(summary["average_speed_delta_mps"], 5.0)
        self.assertAlmostEqual(summary["max_gain_ms"], 0.0)
        self.assertAlmostEqual(summary["max_loss_ms"], 0.0)

    def test_delta_summary_selected_range_uses_entry_gap_as_baseline(self):
        current_samples = [
            _delta_sample(1, 0.0, 0.0),
            _delta_sample(2, 0.25, 30_000.0),
            _delta_sample(3, 0.5, 55_000.0),
            _delta_sample(4, 0.75, 81_000.0),
            _delta_sample(5, 1.0, 100_000.0),
        ]
        reference_samples = [
            _delta_sample(101, 0.0, 0.0),
            _delta_sample(102, 0.25, 25_000.0),
            _delta_sample(103, 0.5, 50_500.0),
            _delta_sample(104, 0.75, 75_000.0),
            _delta_sample(105, 1.0, 95_000.0),
        ]

        summary = delta_summary(
            current_samples,
            reference_samples,
            start_sequence=2,
            end_sequence=4,
        )

        self.assertEqual(summary["start_sequence"], 2)
        self.assertEqual(summary["end_sequence"], 4)
        self.assertEqual(summary["sample_count"], 3)
        self.assertEqual(
            [point["time_delta_ms"] for point in summary["points"]],
            [5_000.0, 4_500.0, 6_000.0],
        )
        self.assertAlmostEqual(summary["time_delta_ms"], 1_000.0)
        self.assertAlmostEqual(summary["max_gain_ms"], 500.0)
        self.assertAlmostEqual(summary["max_loss_ms"], 1_000.0)

    def test_delta_summary_equal_selected_section_reports_zero_despite_entry_gap(self):
        current_samples = [
            _delta_sample(1, 0.0, 10_000.0),
            _delta_sample(2, 0.25, 30_000.0),
            _delta_sample(3, 0.5, 55_000.0),
            _delta_sample(4, 0.75, 80_000.0),
            _delta_sample(5, 1.0, 100_000.0),
        ]
        reference_samples = [
            _delta_sample(101, 0.0, 0.0),
            _delta_sample(102, 0.25, 25_000.0),
            _delta_sample(103, 0.5, 50_000.0),
            _delta_sample(104, 0.75, 75_000.0),
            _delta_sample(105, 1.0, 95_000.0),
        ]

        summary = delta_summary(
            current_samples,
            reference_samples,
            start_sequence=2,
            end_sequence=4,
        )

        self.assertEqual(
            [point["time_delta_ms"] for point in summary["points"]],
            [5_000.0, 5_000.0, 5_000.0],
        )
        self.assertAlmostEqual(summary["time_delta_ms"], 0.0)
        self.assertAlmostEqual(summary["max_gain_ms"], 0.0)
        self.assertAlmostEqual(summary["max_loss_ms"], 0.0)

    def test_delta_summary_collapses_duplicate_reference_progress_before_interpolating(self):
        current_samples = [
            _delta_sample(1, 0.0, 0.0),
            _delta_sample(2, 0.5, 50_000.0),
            _delta_sample(3, 1.0, 100_000.0),
        ]
        reference_samples = [
            _delta_sample(101, 0.0, 0.0, speed_mps=40.0),
            _delta_sample(102, 0.5, 40_000.0, speed_mps=50.0),
            _delta_sample(103, 0.5 + 5e-13, 45_000.0, speed_mps=55.0),
            _delta_sample(104, 1.0, 90_000.0, speed_mps=60.0),
        ]

        summary = delta_summary(current_samples, reference_samples)

        middle_point = summary["points"][1]
        self.assertAlmostEqual(middle_point["reference_elapsed_ms"], 45_000.0)
        self.assertAlmostEqual(middle_point["reference_speed_mps"], 55.0)
        self.assertAlmostEqual(middle_point["time_delta_ms"], 5_000.0)
        self.assertAlmostEqual(summary["time_delta_ms"], 10_000.0)

    def test_delta_summary_large_reference_completes_without_per_sample_reference_rebuilds(self):
        sample_count = 2_500
        current_samples = [
            _delta_sample(
                sequence=index + 1,
                lap_progress=index / (sample_count - 1),
                elapsed_ms=float(index * 20),
                speed_mps=50.0 + (index % 17),
            )
            for index in range(sample_count)
        ]
        reference_samples = [
            _delta_sample(
                sequence=10_000 + index,
                lap_progress=index / (sample_count - 1),
                elapsed_ms=float(index * 19),
                speed_mps=48.0 + (index % 13),
            )
            for index in range(sample_count)
        ]

        started_at = time.perf_counter()
        summary = delta_summary(current_samples, reference_samples)
        elapsed = time.perf_counter() - started_at

        self.assertEqual(summary["sample_count"], sample_count)
        self.assertEqual(len(summary["points"]), sample_count)
        self.assertLess(elapsed, 1.5, f"delta_summary took {elapsed:.3f}s for {sample_count}x{sample_count} samples")

    def test_delta_summary_returns_safe_empty_state_for_missing_data(self):
        summary = delta_summary([], [], start_sequence=10, end_sequence=20)

        self.assertEqual(summary["start_sequence"], 10)
        self.assertEqual(summary["end_sequence"], 20)
        self.assertEqual(summary["sample_count"], 0)
        self.assertIsNone(summary["time_delta_ms"])
        self.assertIsNone(summary["average_speed_delta_mps"])
        self.assertEqual(summary["max_gain_ms"], 0.0)
        self.assertEqual(summary["max_loss_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()
