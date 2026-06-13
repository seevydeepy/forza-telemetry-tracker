import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from telemetry_tracker.packet_bridge import (
    decode_packet,
    encode_packet_for_test,
    packet_to_live_fields,
)
from telemetry_tracker.storage import (
    LOCAL_USER_ID,
    SCHEMA_VERSION,
    TelemetryStore,
    _ALL_EXTENDED_SAMPLE_COLUMNS,
    _DASHBOARD_SAMPLE_COLUMNS,
)


ISSUE_MARKER_DETAIL_COLUMNS = {
    "anchor_sequence",
    "issue_kind",
    "actual_value",
    "threshold_value",
    "threshold_operator",
    "value_label",
    "value_unit",
}


def _marker_with_detail_fields(marker: dict, **overrides) -> dict:
    details = {
        "anchor_sequence": None,
        "issue_kind": None,
        "actual_value": None,
        "threshold_value": None,
        "threshold_operator": None,
        "value_label": None,
        "value_unit": None,
    }
    details.update(marker)
    details.update(overrides)
    return details


def _sample_from_decoded(index: int, decoded: dict) -> dict:
    sample = {
        "sequence": index + 1,
        "received_at_ms": index * 16,
        "game_timestamp_ms": int(decoded["TimestampMS"]),
        "is_race_on": int(decoded.get("IsRaceOn", 0)) > 0,
        "lap_number": int(decoded["LapNumber"]),
        "current_lap": float(decoded["CurrentLap"]),
        "current_race_time": float(decoded["CurrentRaceTime"]),
        "x": float(decoded["PositionX"]),
        "y": float(decoded["PositionY"]),
        "z": float(decoded["PositionZ"]),
        "speed_mps": float(decoded["Speed"]),
        "throttle": int(decoded["Accel"]),
        "brake": int(decoded["Brake"]),
        "steer": int(decoded["Steer"]),
        "gear": int(decoded["Gear"]),
        "combined_slip": None,
        "rear_combined_slip": None,
        "tire_temp_front_left": None,
        "tire_temp_front_right": None,
        "tire_temp_rear_left": None,
        "tire_temp_rear_right": None,
        "suspension_travel_front_left": None,
        "suspension_travel_front_right": None,
        "suspension_travel_rear_left": None,
        "suspension_travel_rear_right": None,
        "current_rpm": None,
        "engine_max_rpm": None,
    }
    for column in _DASHBOARD_SAMPLE_COLUMNS:
        sample[column] = None
    sample["uncertainty"] = None
    return sample


def _query_plan_details(store: TelemetryStore, sql: str, params: tuple = ()) -> list[str]:
    with store.connect() as con:
        return [
            str(row["detail"])
            for row in con.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
        ]


def _create_legacy_v8_issue_marker_database(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    try:
        with con:
            con.executescript(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at_ms INTEGER NOT NULL
                );
                INSERT INTO schema_migrations(version, applied_at_ms)
                VALUES (1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (6, 1), (7, 1), (8, 1);
                CREATE TABLE issue_markers (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    lap_id TEXT,
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
    finally:
        con.close()


def _create_legacy_v6_database(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    try:
        with con:
            con.executescript(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at_ms INTEGER NOT NULL
                );
                INSERT INTO schema_migrations(version, applied_at_ms)
                VALUES (1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (6, 1);
                CREATE TABLE lap_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    lap_id TEXT,
                    sequence INTEGER NOT NULL,
                    received_at_ms INTEGER NOT NULL,
                    game_timestamp_ms INTEGER NOT NULL,
                    is_race_on INTEGER NOT NULL DEFAULT 1,
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
                """
            )
    finally:
        con.close()


def _create_legacy_v1_database(db_path: Path) -> None:
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
                    status TEXT NOT NULL,
                    started_at_ms INTEGER NOT NULL,
                    ended_at_ms INTEGER
                );
                CREATE TABLE laps (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    lap_number INTEGER,
                    started_at_ms INTEGER NOT NULL,
                    ended_at_ms INTEGER,
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
                CREATE INDEX idx_packet_blobs_session_lap_time
                ON packet_blobs(session_id, lap_id, game_timestamp_ms);
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
                    gear INTEGER NOT NULL
                );
                CREATE INDEX idx_lap_samples_session_time
                ON lap_samples(session_id, game_timestamp_ms);
                CREATE INDEX idx_lap_samples_session_sequence
                ON lap_samples(session_id, sequence);
                """
            )
            con.execute(
                "INSERT INTO schema_migrations(version, applied_at_ms) VALUES (?, ?)",
                (1, 1_000),
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
            con.execute(
                """
                INSERT INTO sessions(id, user_id, label, status, started_at_ms, ended_at_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("legacy-session", LOCAL_USER_ID, "Legacy replay", "recording", 2_000, None),
            )
            con.execute(
                """
                INSERT INTO laps(id, user_id, session_id, lap_number, started_at_ms, ended_at_ms, boundary_confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("legacy-lap", LOCAL_USER_ID, "legacy-session", 3, 2_100, None, "game_field"),
            )
            con.execute(
                """
                INSERT INTO packet_blobs(
                    session_id, lap_id, sequence, received_at_ms, game_timestamp_ms, lap_number,
                    position_x, position_y, position_z, speed_mps, raw_packet
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("legacy-session", "legacy-lap", 1, 2_120, 64, 3, 1.0, 2.0, 3.0, 40.0, b"raw"),
            )
            con.execute(
                """
                INSERT INTO lap_samples(
                    session_id, lap_id, sequence, received_at_ms, game_timestamp_ms, lap_number,
                    current_lap, current_race_time, x, y, z, speed_mps,
                    throttle, brake, steer, gear
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-session",
                    "legacy-lap",
                    1,
                    2_120,
                    64,
                    3,
                    12.5,
                    15.0,
                    1.0,
                    2.0,
                    3.0,
                    40.0,
                    128,
                    0,
                    0,
                    4,
                ),
            )
    finally:
        con.close()


class TelemetryStoreTests(unittest.TestCase):
    def test_migrate_configures_wal_and_seeds_local_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "telemetry_tracker.sqlite3"
            store = TelemetryStore(db_path)
            store.migrate()

            with store.connect() as con:
                journal_mode = con.execute("PRAGMA journal_mode").fetchone()[0]
                synchronous = con.execute("PRAGMA synchronous").fetchone()[0]
                foreign_keys = con.execute("PRAGMA foreign_keys").fetchone()[0]
                busy_timeout = con.execute("PRAGMA busy_timeout").fetchone()[0]
                indexes = {
                    row[1]
                    for row in con.execute(
                        "PRAGMA index_list('lap_samples')",
                    ).fetchall()
                }
                packet_indexes = {
                    row[1]
                    for row in con.execute(
                        "PRAGMA index_list('packet_blobs')",
                    ).fetchall()
                }
                summary_indexes = {
                    row[1]
                    for row in con.execute(
                        "PRAGMA index_list('lap_summaries')",
                    ).fetchall()
                }
                issue_marker_columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(issue_markers)").fetchall()
                }
                tables = {
                    row["name"]
                    for row in con.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                migration_versions = [
                    row[0]
                    for row in con.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]
                user = con.execute("SELECT id, display_name FROM users").fetchone()
                identity = con.execute(
                    "SELECT provider, subject FROM auth_identities WHERE user_id = ?",
                    (user[0],),
                ).fetchone()
                settings = con.execute(
                    "SELECT capture_mode, udp_host, udp_port, unit_system FROM user_settings WHERE user_id = ?",
                    (user[0],),
                ).fetchone()

            self.assertEqual(journal_mode.lower(), "wal")
            self.assertEqual(synchronous, 1)
            self.assertEqual(foreign_keys, 1)
            self.assertEqual(busy_timeout, 5000)
            self.assertIn("idx_lap_samples_session_sequence", indexes)
            self.assertIn("idx_lap_samples_session_race_sequence", indexes)
            self.assertIn("idx_lap_samples_lap_current_lap", indexes)
            self.assertIn("idx_packet_blobs_session_sequence", packet_indexes)
            self.assertIn("idx_lap_summaries_context_track", summary_indexes)
            self.assertIn("idx_lap_summaries_context_track_car", summary_indexes)
            self.assertIn(
                "idx_lap_summaries_context_track_car_build",
                summary_indexes,
            )
            self.assertIn("comparison_refs", tables)
            self.assertTrue(ISSUE_MARKER_DETAIL_COLUMNS.issubset(issue_marker_columns))
            self.assertEqual(SCHEMA_VERSION, 11)
            self.assertEqual(migration_versions, list(range(1, SCHEMA_VERSION + 1)))
            self.assertIsInstance(user, sqlite3.Row)
            self.assertEqual(user[1], "Local User")
            self.assertEqual(tuple(identity), ("local", "local"))
            self.assertEqual(tuple(settings), ("auto", "127.0.0.1", 5400, "imperial"))

    def test_history_queries_use_targeted_lap_sample_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Plan demo")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )

            session_plan = "\n".join(
                _query_plan_details(
                    store,
                    store._session_select_sql("sessions.id = ?"),
                    (session_id,),
                )
            )
            lap_plan = "\n".join(
                _query_plan_details(
                    store,
                    store._laps_query("laps.id = ?"),
                    (lap_id,),
                )
            )
            recent_plan = "\n".join(
                _query_plan_details(
                    store,
                    """
                    SELECT lap_id
                    FROM lap_samples
                    WHERE session_id = ? AND is_race_on = 1
                    ORDER BY sequence DESC
                    LIMIT 1
                    """,
                    (session_id,),
                )
            )

            for plan in (session_plan, lap_plan):
                self.assertNotIn("MATERIALIZE lap_times", plan)
                self.assertNotIn("SCAN lap_samples", plan)
                self.assertIn("idx_lap_samples_lap_current_lap", plan)
            self.assertIn("idx_lap_samples_session_race_sequence", recent_plan)

    def test_migration_v6_backfills_legacy_race_state_from_raw_packets(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.start_session("Backfill race state")
            lap_id = store.create_lap(session_id, 0, "game_field")
            raw_packets = [
                encode_packet_for_test(
                    {
                        "IsRaceOn": 1,
                        "TimestampMS": 100,
                        "LapNumber": 0,
                        "CurrentLap": 1.0,
                        "CurrentRaceTime": 1.0,
                        "PositionX": 10.0,
                        "PositionY": 0.0,
                        "PositionZ": 10.0,
                        "Speed": 20.0,
                    }
                ),
                encode_packet_for_test(
                    {
                        "IsRaceOn": 0,
                        "TimestampMS": 116,
                        "LapNumber": 0,
                        "CurrentLap": 0.0,
                        "CurrentRaceTime": 0.0,
                        "PositionX": 0.0,
                        "PositionY": 0.0,
                        "PositionZ": 0.0,
                        "Speed": 0.0,
                    }
                ),
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [_sample_from_decoded(index, decoded) for index, decoded in enumerate(decoded_packets)]
            samples[0]["lap_id"] = lap_id
            samples[1]["lap_id"] = None
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            with store.connect() as con:
                con.execute("UPDATE lap_samples SET is_race_on = 1")
                con.execute("DELETE FROM schema_migrations WHERE version = 6")

            store.migrate()

            with store.connect() as con:
                race_flags = [
                    (row["sequence"], row["is_race_on"])
                    for row in con.execute(
                        "SELECT sequence, is_race_on FROM lap_samples ORDER BY sequence"
                    ).fetchall()
                ]
                versions = [
                    row["version"]
                    for row in con.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]
            recent = store.latest_session_recent_samples(10)

            self.assertEqual(race_flags, [(1, 1), (2, 0)])
            self.assertEqual(versions, list(range(1, SCHEMA_VERSION + 1)))
            self.assertEqual([sample["sequence"] for sample in recent["samples"]], [1])
            self.assertTrue(recent["samples"][0]["is_race_on"])

    def test_migration_v7_adds_dashboard_sample_columns_to_existing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy-v6.sqlite3"
            _create_legacy_v6_database(db_path)
            store = TelemetryStore(db_path)

            store.migrate()

            with store.connect() as con:
                sample_columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(lap_samples)").fetchall()
                }
                versions = [
                    row["version"]
                    for row in con.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]

            self.assertEqual(versions, list(range(1, SCHEMA_VERSION + 1)))
            for column in _DASHBOARD_SAMPLE_COLUMNS:
                with self.subTest(column=column):
                    self.assertIn(column, sample_columns)

    def test_migration_v9_adds_issue_marker_detail_columns_to_existing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy-v8.sqlite3"
            _create_legacy_v8_issue_marker_database(db_path)
            store = TelemetryStore(db_path)

            store.migrate()

            with store.connect() as con:
                marker_columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(issue_markers)").fetchall()
                }
                versions = [
                    row["version"]
                    for row in con.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]

            self.assertTrue(ISSUE_MARKER_DETAIL_COLUMNS.issubset(marker_columns))
            self.assertEqual(versions, list(range(1, SCHEMA_VERSION + 1)))


    def test_migration_v8_backfills_dashboard_samples_from_raw_packets(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Dashboard backfill demo")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            raw_packet = encode_packet_for_test(
                {
                    "TimestampMS": 88,
                    "LapNumber": 1,
                    "CurrentLap": 8.5,
                    "CurrentRaceTime": 9.5,
                    "PositionX": 11.0,
                    "PositionY": 2.0,
                    "PositionZ": 22.0,
                    "Speed": 32.0,
                    "CurrentEngineRpm": 6_100.0,
                    "EngineMaxRpm": 9_000.0,
                    "AccelerationX": 1.25,
                    "AccelerationY": -0.5,
                    "AccelerationZ": 0.75,
                    "VelocityX": 3.0,
                    "AngularVelocityZ": 0.3,
                    "Yaw": 0.4,
                    "Pitch": 0.5,
                    "Roll": -0.6,
                    "SmashableVelDiff": 4.5,
                    "SmashableMass": 3.25,
                    "TireTempFrontLeft": 92.0,
                    "TireSlipRatioFrontLeft": 0.11,
                    "TireSlipAngleFrontLeft": -0.22,
                    "TireCombinedSlipFrontLeft": 0.33,
                    "WheelRotationSpeedFrontLeft": 42.0,
                    "SurfaceRumbleFrontLeft": 0.66,
                    "SuspensionTravelMetersFrontLeft": 0.77,
                }
            )
            decoded = decode_packet(raw_packet)
            sample = packet_to_live_fields(decoded, sequence=1, received_at_ms=16)
            sample["lap_id"] = lap_id
            store.insert_packet_batch(session_id, [raw_packet], [decoded], [sample])

            with store.connect() as con:
                con.execute(
                    "UPDATE lap_samples SET "
                    + ", ".join(f"{column} = NULL" for column in _ALL_EXTENDED_SAMPLE_COLUMNS)
                )
                con.execute("DELETE FROM schema_migrations WHERE version = 8")

            store.migrate()

            [stored_sample] = store.samples_for_lap(lap_id)
            with store.connect() as con:
                versions = [
                    row["version"]
                    for row in con.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]

            self.assertEqual(versions, list(range(1, SCHEMA_VERSION + 1)))
            for column in (
                "current_rpm",
                "engine_max_rpm",
                "acceleration_x",
                "acceleration_y",
                "acceleration_z",
                "velocity_x",
                "angular_velocity_z",
                "yaw",
                "pitch",
                "roll",
                "smashable_vel_diff",
                "smashable_mass",
                "tire_temp_front_left",
                "tire_slip_ratio_front_left",
                "tire_slip_angle_front_left",
                "tire_combined_slip_front_left",
                "wheel_rotation_speed_front_left",
                "surface_rumble_front_left",
                "suspension_travel_meters_front_left",
            ):
                with self.subTest(column=column):
                    self.assertAlmostEqual(stored_sample[column], sample[column])

    def test_migration_v10_backfills_smashable_samples_when_v8_already_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Smashable backfill demo")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            raw_packet = encode_packet_for_test(
                {
                    "TimestampMS": 88,
                    "LapNumber": 1,
                    "CurrentLap": 8.5,
                    "CurrentRaceTime": 9.5,
                    "PositionX": 11.0,
                    "PositionY": 2.0,
                    "PositionZ": 22.0,
                    "Speed": 32.0,
                    "SmashableVelDiff": 5.75,
                    "SmashableMass": 2.5,
                }
            )
            decoded = decode_packet(raw_packet)
            sample = packet_to_live_fields(decoded, sequence=1, received_at_ms=16)
            sample["lap_id"] = lap_id
            store.insert_packet_batch(session_id, [raw_packet], [decoded], [sample])

            with store.connect() as con:
                con.execute(
                    "UPDATE lap_samples SET smashable_vel_diff = NULL, smashable_mass = NULL"
                )
                con.execute("DELETE FROM schema_migrations WHERE version = 10")

            store.migrate()

            [stored_sample] = store.samples_for_lap(lap_id)
            with store.connect() as con:
                versions = [
                    row["version"]
                    for row in con.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]

            self.assertEqual(versions, list(range(1, SCHEMA_VERSION + 1)))
            self.assertAlmostEqual(stored_sample["smashable_vel_diff"], 5.75)
            self.assertAlmostEqual(stored_sample["smashable_mass"], 2.5)

    def test_migration_v2_adds_lifecycle_columns_without_losing_v1_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.sqlite3"
            _create_legacy_v1_database(db_path)
            store = TelemetryStore(db_path)

            store.migrate()
            store.migrate()

            with store.connect() as con:
                sessions_columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(sessions)").fetchall()
                }
                laps_columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(laps)").fetchall()
                }
                packet_columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(packet_blobs)").fetchall()
                }
                sample_columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(lap_samples)").fetchall()
                }
                tables = {
                    row["name"]
                    for row in con.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                packet_indexes = {
                    row["name"]
                    for row in con.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'packet_blobs'"
                    ).fetchall()
                }
                session = con.execute(
                    "SELECT label, status, ended_at_ms, ended_reason FROM sessions WHERE id = ?",
                    ("legacy-session",),
                ).fetchone()
                lap = con.execute(
                    """
                    SELECT lap_number, status, ended_at_ms, ended_reason, boundary_confidence
                    FROM laps
                    WHERE id = ?
                    """,
                    ("legacy-lap",),
                ).fetchone()
                packet = con.execute(
                    "SELECT sequence, lap_id, speed_mps FROM packet_blobs WHERE session_id = ?",
                    ("legacy-session",),
                ).fetchone()
                sample = con.execute(
                    "SELECT sequence, lap_id, speed_mps FROM lap_samples WHERE session_id = ?",
                    ("legacy-session",),
                ).fetchone()
                settings = con.execute(
                    "SELECT capture_mode, unit_system FROM user_settings WHERE user_id = ?",
                    (LOCAL_USER_ID,),
                ).fetchone()
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
                user_count = int(con.execute("SELECT COUNT(*) FROM users").fetchone()[0])
                identity_count = int(con.execute("SELECT COUNT(*) FROM auth_identities").fetchone()[0])
                settings_count = int(con.execute("SELECT COUNT(*) FROM user_settings").fetchone()[0])

            self.assertIn("ended_reason", sessions_columns)
            self.assertIn("status", laps_columns)
            self.assertIn("ended_reason", laps_columns)
            self.assertIn("lap_id", packet_columns)
            self.assertIn("lap_id", sample_columns)
            self.assertIn("lap_summaries", tables)
            self.assertIn("comparison_refs", tables)
            self.assertIn("idx_packet_blobs_session_sequence", packet_indexes)
            self.assertEqual(tuple(session), ("Legacy replay", "recording", None, None))
            self.assertEqual(tuple(lap), (3, "recording", None, None, "game_field"))
            self.assertEqual(tuple(packet), (1, "legacy-lap", 40.0))
            self.assertEqual(tuple(sample), (1, "legacy-lap", 40.0))
            self.assertEqual(tuple(settings), ("auto", "imperial"))
            self.assertEqual(versions, list(range(1, SCHEMA_VERSION + 1)))
            self.assertEqual(
                version_counts,
                {version: 1 for version in range(1, SCHEMA_VERSION + 1)},
            )
            self.assertEqual(user_count, 1)
            self.assertEqual(identity_count, 1)
            self.assertEqual(settings_count, 1)

            raw_packets = [encode_packet_for_test({"TimestampMS": 128, "PositionX": 2.0, "Speed": 41.0})]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [_sample_from_decoded(1, decoded_packets[0])]
            samples[0]["lap_id"] = "missing-lap"
            with self.assertRaisesRegex(ValueError, "unknown lap_id"):
                store.insert_packet_batch("legacy-session", raw_packets, decoded_packets, samples)
            with store.connect() as con:
                packet_count = int(con.execute("SELECT COUNT(*) FROM packet_blobs").fetchone()[0])
                sample_count = int(con.execute("SELECT COUNT(*) FROM lap_samples").fetchone()[0])
            self.assertEqual(packet_count, 1)
            self.assertEqual(sample_count, 1)

    def test_insert_packets_and_samples_in_one_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Replay demo")
            raw_packets = [
                encode_packet_for_test({"TimestampMS": 0, "PositionX": 1.0, "Speed": 10.0}),
                encode_packet_for_test({"TimestampMS": 16, "PositionX": 2.0, "Speed": 12.0}),
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [_sample_from_decoded(index, decoded) for index, decoded in enumerate(decoded_packets)]

            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            self.assertEqual(store.count_packets(session_id), 2)
            self.assertEqual(store.latest_samples(session_id, limit=10), samples)

    def test_insert_packet_batch_round_trips_dashboard_sample_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Dashboard sample demo")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            raw_packets = [
                encode_packet_for_test(
                    {
                        "TimestampMS": 64,
                        "LapNumber": 1,
                        "CurrentLap": 4.5,
                        "CurrentRaceTime": 5.5,
                        "PositionX": 10.0,
                        "PositionY": 2.0,
                        "PositionZ": 20.0,
                        "Speed": 31.0,
                        "AccelerationX": 1.25,
                        "AccelerationY": -0.5,
                        "AccelerationZ": 0.75,
                        "VelocityX": 3.0,
                        "VelocityY": 4.0,
                        "VelocityZ": 5.0,
                        "AngularVelocityX": 0.1,
                        "AngularVelocityY": 0.2,
                        "AngularVelocityZ": 0.3,
                        "Yaw": 0.4,
                        "Pitch": 0.5,
                        "Roll": -0.6,
                        "Power": 400_000.0,
                        "Torque": 512.0,
                        "Boost": 1.4,
                        "Fuel": 0.6,
                        "DistanceTraveled": 987.0,
                        "BestLap": 60.0,
                        "LastLap": 61.5,
                        "RacePosition": 2,
                        "Clutch": 3,
                        "HandBrake": 4,
                        "NormalizedDrivingLine": -1,
                        "NormalizedAIBrakeDifference": 8,
                        "TireSlipRatioFrontLeft": 0.11,
                        "TireSlipAngleRearRight": -1.4,
                        "TireCombinedSlipRearLeft": 0.33,
                        "WheelRotationSpeedFrontRight": 42.0,
                        "WheelOnRumbleStripRearLeft": 1,
                        "WheelInPuddleRearRight": 5,
                        "SurfaceRumbleFrontLeft": 0.66,
                        "SuspensionTravelMetersRearRight": 0.77,
                    }
                )
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            sample = packet_to_live_fields(
                decoded_packets[0],
                sequence=1,
                received_at_ms=16,
            )
            sample["lap_id"] = lap_id

            store.insert_packet_batch(session_id, raw_packets, decoded_packets, [sample])

            [stored_sample] = store.samples_for_lap(lap_id)
            for column in _DASHBOARD_SAMPLE_COLUMNS:
                with self.subTest(column=column):
                    self.assertEqual(stored_sample[column], sample[column])

    def test_insert_packet_batch_preserves_sample_sequence_across_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Second batch demo")
            first_raw = [encode_packet_for_test({"TimestampMS": 0, "PositionX": 1.0, "Speed": 10.0})]
            first_decoded = [decode_packet(raw) for raw in first_raw]
            first_samples = [
                _sample_from_decoded(index, decoded)
                for index, decoded in enumerate(first_decoded)
            ]
            second_raw = [
                encode_packet_for_test({"TimestampMS": 32, "PositionX": 3.0, "Speed": 13.0}),
                encode_packet_for_test({"TimestampMS": 48, "PositionX": 4.0, "Speed": 14.0}),
            ]
            second_decoded = [decode_packet(raw) for raw in second_raw]
            second_samples = [
                _sample_from_decoded(index + 9, decoded)
                for index, decoded in enumerate(second_decoded)
            ]

            store.insert_packet_batch(session_id, first_raw, first_decoded, first_samples)
            store.insert_packet_batch(session_id, second_raw, second_decoded, second_samples)

            with store.connect() as con:
                packet_sequences = [
                    row[0]
                    for row in con.execute(
                        "SELECT sequence FROM packet_blobs WHERE session_id = ? ORDER BY sequence",
                        (session_id,),
                    ).fetchall()
                ]
                sample_sequences = [
                    row[0]
                    for row in con.execute(
                        "SELECT sequence FROM lap_samples WHERE session_id = ? ORDER BY sequence",
                        (session_id,),
                    ).fetchall()
                ]

            self.assertEqual(packet_sequences, [1, 10, 11])
            self.assertEqual(packet_sequences, sample_sequences)
            self.assertEqual(store.latest_samples(session_id, limit=2), second_samples)

    def test_insert_packet_batch_persists_nullable_lap_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Nullable lap demo")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            raw_packets = [
                encode_packet_for_test({"TimestampMS": 0, "PositionX": 1.0, "Speed": 10.0}),
                encode_packet_for_test({"TimestampMS": 16, "PositionX": 2.0, "Speed": 12.0}),
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [_sample_from_decoded(index, decoded) for index, decoded in enumerate(decoded_packets)]
            samples[0]["lap_id"] = None
            samples[1]["lap_id"] = lap_id

            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            with store.connect() as con:
                packet_lap_ids = [
                    tuple(row)
                    for row in con.execute(
                        "SELECT sequence, lap_id FROM packet_blobs WHERE session_id = ? ORDER BY sequence",
                        (session_id,),
                    ).fetchall()
                ]
                sample_lap_ids = [
                    tuple(row)
                    for row in con.execute(
                        "SELECT sequence, lap_id FROM lap_samples WHERE session_id = ? ORDER BY sequence",
                        (session_id,),
                    ).fetchall()
                ]

            self.assertEqual(packet_lap_ids, [(1, None), (2, lap_id)])
            self.assertEqual(sample_lap_ids, packet_lap_ids)
            self.assertEqual(store.samples_for_lap(lap_id), [samples[1]])

    def test_sample_range_and_lap_queries_include_missing_extended_fields_as_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Extended field demo")
            lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
            raw_packets = [encode_packet_for_test({"TimestampMS": 0, "PositionX": 1.0, "Speed": 10.0})]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [_sample_from_decoded(index, decoded) for index, decoded in enumerate(decoded_packets)]
            samples[0]["lap_id"] = lap_id

            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            lap_samples = store.samples_for_lap(lap_id)
            range_samples = store.samples_for_range(session_id, start_sequence=1, end_sequence=1, lap_id=lap_id)

            self.assertEqual(lap_samples, range_samples)
            for field_name in (
                "combined_slip",
                "rear_combined_slip",
                "tire_temp_front_left",
                "tire_temp_front_right",
                "tire_temp_rear_left",
                "tire_temp_rear_right",
                "suspension_travel_front_left",
                "suspension_travel_front_right",
                "suspension_travel_rear_left",
                "suspension_travel_rear_right",
                "current_rpm",
                "engine_max_rpm",
                *_DASHBOARD_SAMPLE_COLUMNS,
            ):
                self.assertIn(field_name, lap_samples[0])
                self.assertIsNone(lap_samples[0][field_name])

    def test_insert_packet_batch_rejects_unknown_lap_id_without_partial_insert(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Unknown lap demo")
            raw_packets = [encode_packet_for_test({"TimestampMS": 0, "PositionX": 1.0, "Speed": 10.0})]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [_sample_from_decoded(index, decoded) for index, decoded in enumerate(decoded_packets)]
            samples[0]["lap_id"] = "missing-lap"

            with self.assertRaisesRegex(ValueError, "unknown lap_id"):
                store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            self.assertEqual(store.count_packets(session_id), 0)
            self.assertEqual(store.latest_samples(session_id, limit=10), [])
            with store.connect() as con:
                sample_count = int(con.execute("SELECT COUNT(*) FROM lap_samples").fetchone()[0])
            self.assertEqual(sample_count, 0)

    def test_insert_packet_batch_rejects_cross_session_lap_id_without_partial_insert(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Target session")
            other_session_id = store.create_session(label="Other session")
            other_lap_id = store.create_lap(
                session_id=other_session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            raw_packets = [encode_packet_for_test({"TimestampMS": 0, "PositionX": 1.0, "Speed": 10.0})]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [_sample_from_decoded(index, decoded) for index, decoded in enumerate(decoded_packets)]
            samples[0]["lap_id"] = other_lap_id

            with self.assertRaisesRegex(ValueError, "does not belong to session"):
                store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            with store.connect() as con:
                packet_count = int(con.execute("SELECT COUNT(*) FROM packet_blobs").fetchone()[0])
                sample_count = int(con.execute("SELECT COUNT(*) FROM lap_samples").fetchone()[0])
            self.assertEqual(packet_count, 0)
            self.assertEqual(sample_count, 0)

    def test_insert_issue_markers_rejects_unknown_lap_id_without_partial_insert(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Marker session")

            with self.assertRaisesRegex(ValueError, "unknown lap_id"):
                store.insert_issue_markers(
                    [
                        {
                            "id": "marker-1",
                            "session_id": session_id,
                            "lap_id": "missing-lap",
                            "start_sequence": 1,
                            "end_sequence": 1,
                            "metric": "rear_combined_slip",
                            "severity": "critical",
                            "reason": "test",
                            "ruleset_version": 1,
                            "confidence": 0.9,
                        }
                    ]
                )

            with store.connect() as con:
                count = int(con.execute("SELECT COUNT(*) FROM issue_markers").fetchone()[0])
            self.assertEqual(count, 0)

    def test_insert_issue_markers_rejects_cross_session_lap_id_without_partial_insert(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Marker target")
            other_session_id = store.create_session(label="Marker other")
            other_lap_id = store.create_lap(
                session_id=other_session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )

            with self.assertRaisesRegex(ValueError, "does not belong to session"):
                store.insert_issue_markers(
                    [
                        {
                            "id": "marker-1",
                            "session_id": session_id,
                            "lap_id": other_lap_id,
                            "start_sequence": 1,
                            "end_sequence": 1,
                            "metric": "rear_combined_slip",
                            "severity": "critical",
                            "reason": "test",
                            "ruleset_version": 1,
                            "confidence": 0.9,
                        }
                    ]
                )

            with store.connect() as con:
                count = int(con.execute("SELECT COUNT(*) FROM issue_markers").fetchone()[0])
            self.assertEqual(count, 0)

    def test_insert_packet_batch_rejects_mismatched_lengths_without_partial_insert(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Mismatch demo")
            raw_packets = [
                encode_packet_for_test({"TimestampMS": 0, "PositionX": 1.0, "Speed": 10.0}),
                encode_packet_for_test({"TimestampMS": 16, "PositionX": 2.0, "Speed": 12.0}),
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [_sample_from_decoded(index, decoded) for index, decoded in enumerate(decoded_packets)]
            cases = [
                (raw_packets, decoded_packets, samples[:1]),
                (raw_packets, decoded_packets[:1], samples),
                (raw_packets[:1], decoded_packets, samples),
                ([], [], samples[:1]),
            ]

            for mismatched_raw, mismatched_decoded, mismatched_samples in cases:
                with self.subTest(
                    raw=len(mismatched_raw),
                    decoded=len(mismatched_decoded),
                    samples=len(mismatched_samples),
                ):
                    with self.assertRaisesRegex(ValueError, "same length"):
                        store.insert_packet_batch(
                            session_id,
                            mismatched_raw,
                            mismatched_decoded,
                            mismatched_samples,
                        )
                    self.assertEqual(store.count_packets(session_id), 0)
                    self.assertEqual(store.latest_samples(session_id, limit=10), [])

    def test_latest_samples_rejects_non_positive_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Limit demo")

            for limit in (0, -1):
                with self.subTest(limit=limit):
                    with self.assertRaisesRegex(ValueError, "limit must be positive"):
                        store.latest_samples(session_id, limit=limit)

    def test_latest_session_recent_samples_returns_empty_without_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            self.assertEqual(
                store.latest_session_recent_samples(limit=200),
                {"session_id": None, "samples": []},
            )

    def test_latest_session_recent_samples_uses_newest_session_and_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            old_session_id = store.create_session(label="Older replay")
            latest_session_id = store.create_session(label="Latest replay")
            with store.connect() as con:
                con.execute(
                    "UPDATE sessions SET started_at_ms = ? WHERE id = ?",
                    (1_000, old_session_id),
                )
                con.execute(
                    "UPDATE sessions SET started_at_ms = ? WHERE id = ?",
                    (2_000, latest_session_id),
                )
            old_raw = [encode_packet_for_test({"TimestampMS": 0, "PositionX": -10.0, "Speed": 5.0})]
            old_decoded = [decode_packet(raw) for raw in old_raw]
            old_samples = [
                _sample_from_decoded(index, decoded)
                for index, decoded in enumerate(old_decoded)
            ]
            latest_raw = [
                encode_packet_for_test({"TimestampMS": 16, "PositionX": 1.0, "Speed": 10.0}),
                encode_packet_for_test({"TimestampMS": 32, "PositionX": 2.0, "Speed": 11.0}),
                encode_packet_for_test({"TimestampMS": 48, "PositionX": 3.0, "Speed": 12.0}),
            ]
            latest_decoded = [decode_packet(raw) for raw in latest_raw]
            latest_samples = [
                _sample_from_decoded(index + 20, decoded)
                for index, decoded in enumerate(latest_decoded)
            ]

            store.insert_packet_batch(old_session_id, old_raw, old_decoded, old_samples)
            store.insert_packet_batch(latest_session_id, latest_raw, latest_decoded, latest_samples)

            self.assertEqual(
                store.latest_session_recent_samples(limit=2),
                {"session_id": latest_session_id, "samples": latest_samples[-2:]},
            )

    def test_latest_session_recent_samples_excludes_non_race_and_uses_latest_lap(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Live recovery")
            first_lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            second_lap_id = store.create_lap(
                session_id=session_id,
                lap_number=2,
                boundary_confidence="game_field",
            )
            raw_packets = [
                encode_packet_for_test({"TimestampMS": 16, "IsRaceOn": 1, "PositionX": 1.0, "Speed": 10.0}),
                encode_packet_for_test({"TimestampMS": 32, "IsRaceOn": 0, "PositionX": 2.0, "Speed": 0.0}),
                encode_packet_for_test({"TimestampMS": 48, "IsRaceOn": 1, "PositionX": 3.0, "Speed": 11.0}),
                encode_packet_for_test({"TimestampMS": 64, "IsRaceOn": 1, "PositionX": 4.0, "Speed": 12.0}),
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [
                _sample_from_decoded(index, decoded)
                for index, decoded in enumerate(decoded_packets)
            ]
            samples[0]["lap_id"] = first_lap_id
            samples[1]["lap_id"] = first_lap_id
            samples[2]["lap_id"] = second_lap_id
            samples[3]["lap_id"] = second_lap_id

            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            expected = []
            for sample in samples[2:]:
                next_sample = dict(sample)
                next_sample.pop("lap_id", None)
                expected.append(next_sample)
            self.assertEqual(
                store.latest_session_recent_samples(limit=200),
                {"session_id": session_id, "samples": expected},
            )

    def test_latest_session_recent_samples_uses_insertion_order_for_same_started_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            first_session_id = store.create_session(label="First same-ms replay")
            second_session_id = store.create_session(label="Second same-ms replay")
            first_tie_id = "zzzz-first-session"
            second_tie_id = "aaaa-second-session"
            with store.connect() as con:
                con.execute(
                    "UPDATE sessions SET id = ?, started_at_ms = ? WHERE id = ?",
                    (first_tie_id, 1_000, first_session_id),
                )
                con.execute(
                    "UPDATE sessions SET id = ?, started_at_ms = ? WHERE id = ?",
                    (second_tie_id, 1_000, second_session_id),
                )
            first_raw = [encode_packet_for_test({"TimestampMS": 16, "PositionX": 1.0, "Speed": 10.0})]
            first_decoded = [decode_packet(raw) for raw in first_raw]
            first_samples = [
                _sample_from_decoded(index, decoded)
                for index, decoded in enumerate(first_decoded)
            ]
            second_raw = [encode_packet_for_test({"TimestampMS": 32, "PositionX": 2.0, "Speed": 11.0})]
            second_decoded = [decode_packet(raw) for raw in second_raw]
            second_samples = [
                _sample_from_decoded(index + 10, decoded)
                for index, decoded in enumerate(second_decoded)
            ]

            store.insert_packet_batch(first_tie_id, first_raw, first_decoded, first_samples)
            store.insert_packet_batch(second_tie_id, second_raw, second_decoded, second_samples)

            self.assertEqual(
                store.latest_session_recent_samples(limit=200),
                {"session_id": second_tie_id, "samples": second_samples},
            )

    def test_latest_session_recent_samples_rejects_non_positive_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            for limit in (0, -1):
                with self.subTest(limit=limit):
                    with self.assertRaisesRegex(ValueError, "limit must be positive"):
                        store.latest_session_recent_samples(limit=limit)

    def test_create_session_uses_seeded_local_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            session_id = store.create_session(label="Unit test session")

            with store.connect() as con:
                row = con.execute(
                    "SELECT sessions.label, users.display_name FROM sessions JOIN users ON users.id = sessions.user_id WHERE sessions.id = ?",
                    (session_id,),
                ).fetchone()
            self.assertEqual(tuple(row), ("Unit test session", "Local User"))

    def test_migration_v4_adds_session_last_active_and_active_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.sqlite3"
            _create_legacy_v1_database(db_path)
            store = TelemetryStore(db_path)

            store.migrate()

            with store.connect() as con:
                columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(sessions)").fetchall()
                }
                indexes = {
                    row["name"]
                    for row in con.execute("PRAGMA index_list('sessions')").fetchall()
                }
                legacy = con.execute(
                    """
                    SELECT started_at_ms, ended_at_ms, last_active_at_ms
                    FROM sessions
                    WHERE id = ?
                    """,
                    ("legacy-session",),
                ).fetchone()
                versions = [
                    row["version"]
                    for row in con.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]

            self.assertIn("last_active_at_ms", columns)
            self.assertIn("idx_sessions_one_active_user", indexes)
            self.assertEqual(
                legacy["last_active_at_ms"],
                legacy["ended_at_ms"] or legacy["started_at_ms"],
            )
            self.assertEqual(versions, list(range(1, SCHEMA_VERSION + 1)))
            self.assertEqual(SCHEMA_VERSION, 11)

    def test_start_session_creates_default_labels_and_keeps_one_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            first_id = store.start_session()
            second_id = store.start_session()
            active = store.active_session()
            first = store.session(first_id)
            second = store.session(second_id)

            self.assertEqual(first["label"], "Session 1")
            self.assertEqual(second["label"], "Session 2")
            self.assertEqual(active["id"], second_id)
            self.assertEqual(first["status"], "user_end")
            self.assertEqual(first["ended_reason"], "new_session_started")
            self.assertEqual(second["status"], "active")
            self.assertIsNone(second["ended_at_ms"])
            self.assertEqual(second["lap_count"], 0)


    def test_empty_auto_created_car_switch_sessions_can_be_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            manual_id = store.start_session(label="User session")
            self.assertIsNone(
                store.delete_empty_auto_created_session(
                    manual_id,
                    auto_created_reason="car_switch",
                )
            )
            self.assertIsNotNone(store.session(manual_id))

            empty_auto_id = store.start_session(auto_created_reason="car_switch")
            deleted = store.delete_empty_auto_created_session(
                empty_auto_id,
                auto_created_reason="car_switch",
            )
            self.assertIsNotNone(deleted)
            self.assertEqual(deleted["id"], empty_auto_id)
            self.assertIsNone(store.session(empty_auto_id))

    def test_auto_created_car_switch_session_with_finalized_lap_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            session_id = store.start_session(auto_created_reason="car_switch")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            store.finalize_lap(lap_id, reason="lap_boundary")

            self.assertIsNone(
                store.delete_empty_auto_created_session(
                    session_id,
                    auto_created_reason="car_switch",
                )
            )
            self.assertIsNotNone(store.session(session_id))

    def test_start_session_can_persist_car_identity_and_generated_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            identity = {
                "car_identity_key": "ordinal:368|class:3|pi:700|drive:0",
                "car_ordinal": 368,
                "car_name": "Integra R",
                "car_class_id": 3,
                "car_class_label": "A",
                "car_performance_index": 700,
                "drivetrain_id": 0,
                "drivetrain_label": "FWD",
            }

            first_id = store.start_session(car_identity=identity)
            second_id = store.start_session(car_identity=identity)

            self.assertEqual(store.session(first_id)["label"], "Integra R A 700 FWD Session")
            self.assertEqual(store.session(second_id)["label"], "Integra R A 700 FWD Session 2")
            self.assertEqual(store.session(first_id)["car_identity_key"], identity["car_identity_key"])
            self.assertEqual(store.session(first_id)["label_generated"], 1)

    def test_attach_session_car_identity_preserves_custom_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.start_session(label="Custom night run")
            identity = {
                "car_identity_key": "ordinal:1|class:4|pi:800|drive:2",
                "car_ordinal": 1,
                "car_name": "Known Car",
                "car_class_id": 4,
                "car_class_label": "S1",
                "car_performance_index": 800,
                "drivetrain_id": 2,
                "drivetrain_label": "AWD",
            }

            session = store.attach_session_car_identity(session_id, identity)

            self.assertEqual(session["label"], "Custom night run")
            self.assertEqual(session["label_generated"], 0)
            self.assertEqual(session["car_identity_key"], identity["car_identity_key"])

    def test_default_session_labels_do_not_reuse_deleted_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            first_id = store.start_session()
            store.delete_session(first_id)
            second_id = store.start_session()

            self.assertEqual(store.session(second_id)["label"], "Session 2")

    def test_rename_session_rejects_blank_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.start_session(label="Original")

            with self.assertRaisesRegex(ValueError, "label must not be empty"):
                store.rename_session(session_id, "   ")

            updated = store.rename_session(session_id, "Renamed session")
            self.assertEqual(updated["label"], "Renamed session")
            self.assertEqual(store.session(session_id)["label"], "Renamed session")

    def test_paged_sessions_filters_by_name_dates_lap_count_track_and_car(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            profile_id = store.create_track_profile(
                "Emerald Circuit",
                "Full",
                "manual",
                "user",
            )
            old_id = store.create_session(label="Old Road", status="replay_complete")
            target_id = store.create_session(label="Night Track Session", status="user_end")
            other_id = store.create_session(label="Night Other Car", status="user_end")
            store.attach_session_car_identity(target_id, {"car_name": "Mazda Furai"})
            store.attach_session_car_identity(other_id, {"car_name": "Acura Integra"})
            lap_id = store.create_lap(
                target_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            store.assign_track_profile(target_id, lap_id, profile_id)
            store.finalize_lap(
                lap_id,
                reason="lap_boundary",
                boundary_confidence="game_field",
            )
            other_lap_id = store.create_lap(
                other_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            store.assign_track_profile(other_id, other_lap_id, profile_id)
            store.finalize_lap(
                other_lap_id,
                reason="lap_boundary",
                boundary_confidence="game_field",
            )
            with store.connect() as con:
                con.execute(
                    "UPDATE sessions SET started_at_ms = 1000, last_active_at_ms = 1500 WHERE id = ?",
                    (old_id,),
                )
                con.execute(
                    "UPDATE sessions SET started_at_ms = 2000, last_active_at_ms = 2500 WHERE id = ?",
                    (target_id,),
                )
                con.execute(
                    "UPDATE sessions SET started_at_ms = 2200, last_active_at_ms = 2600 WHERE id = ?",
                    (other_id,),
                )

            page = store.paged_sessions(
                page=1,
                page_size=100,
                name="night",
                created_from=1500,
                created_to=2500,
                last_active_from=2000,
                last_active_to=3000,
                lap_count_min=1,
                lap_count_max=2,
                track="emerald",
                car="furai",
            )

            self.assertEqual(page["total"], 1)
            self.assertEqual(page["total_pages"], 1)
            self.assertEqual([session["id"] for session in page["sessions"]], [target_id])
            self.assertEqual(page["sessions"][0]["lap_count"], 1)
            self.assertEqual(page["sessions"][0]["car_name"], "Mazda Furai")
            self.assertNotIn("track_profile_id", page["sessions"][0])
            self.assertNotIn("track_profile_name", page["sessions"][0])
            self.assertNotIn("track_profile_layout", page["sessions"][0])

    def test_single_session_lookup_aggregates_only_requested_session_laps(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            target_session_id = store.create_session(label="Target aggregate")
            other_session_id = store.create_session(label="Other aggregate")
            target_lap_id = store.create_lap(
                target_session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            other_lap_id = store.create_lap(
                other_session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            for session_id, lap_id, offset, duration_seconds in (
                (target_session_id, target_lap_id, 0, 61.0),
                (other_session_id, other_lap_id, 10, 95.0),
            ):
                raw_packets = [
                    encode_packet_for_test(
                        {"TimestampMS": 100 + offset, "CurrentLap": 1.0}
                    ),
                    encode_packet_for_test(
                        {
                            "TimestampMS": 200 + offset,
                            "CurrentLap": 1.0 + duration_seconds,
                        }
                    ),
                ]
                decoded_packets = [decode_packet(raw) for raw in raw_packets]
                samples = [
                    _sample_from_decoded(index + offset, decoded)
                    for index, decoded in enumerate(decoded_packets)
                ]
                for sample in samples:
                    sample["lap_id"] = lap_id
                store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)
                with store.connect() as con:
                    con.execute(
                        """
                        UPDATE laps
                        SET status = ?, ended_reason = ?, started_at_ms = ?, ended_at_ms = ?
                        WHERE id = ?
                        """,
                        ("completed", "completed", 1_000, 99_000, lap_id),
                    )

            session = store.session(target_session_id)

            self.assertIsNotNone(session)
            self.assertEqual(session["lap_count"], 1)
            self.assertEqual(session["completed_lap_count"], 1)
            self.assertEqual(session["best_lap_time_ms"], 61_000)
            self.assertEqual(session["total_lap_time_ms"], 61_000)

    def test_delete_session_cascades_dependent_rows_and_clears_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.start_session(label="Delete me")
            lap_id = store.create_lap(
                session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            raw_packets = [
                encode_packet_for_test(
                    {
                        "TimestampMS": 16,
                        "LapNumber": 1,
                        "CurrentLap": 1.0,
                        "CurrentRaceTime": 1.0,
                    }
                )
            ]
            decoded_packets = [decode_packet(raw_packets[0])]
            sample = _sample_from_decoded(0, decoded_packets[0])
            sample["lap_id"] = lap_id
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, [sample])
            store.insert_lap_summary(lap_id, {"packet_count": 1, "sample_count": 1})
            store.insert_issue_markers(
                [
                    {
                        "id": "marker-delete",
                        "session_id": session_id,
                        "lap_id": lap_id,
                        "start_sequence": 1,
                        "end_sequence": 1,
                        "metric": "speed",
                        "severity": "info",
                        "reason": "test marker",
                        "ruleset_version": 1,
                        "confidence": 1.0,
                    }
                ]
            )
            store.pin_reference_lap("track", "delete-track", lap_id)

            deleted = store.delete_session(session_id)

            self.assertEqual(deleted["id"], session_id)
            self.assertIsNone(store.active_session())
            with store.connect() as con:
                self.assertEqual(
                    con.execute("SELECT COUNT(*) FROM sessions WHERE id = ?", (session_id,)).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    con.execute("SELECT COUNT(*) FROM laps WHERE session_id = ?", (session_id,)).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    con.execute("SELECT COUNT(*) FROM packet_blobs WHERE session_id = ?", (session_id,)).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    con.execute("SELECT COUNT(*) FROM lap_samples WHERE session_id = ?", (session_id,)).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    con.execute("SELECT COUNT(*) FROM lap_summaries WHERE lap_id = ?", (lap_id,)).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    con.execute("SELECT COUNT(*) FROM issue_markers WHERE session_id = ?", (session_id,)).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    con.execute("SELECT COUNT(*) FROM comparison_refs WHERE lap_id = ?", (lap_id,)).fetchone()[0],
                    0,
                )

    def test_lap_and_session_lifecycle_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Lifecycle demo")

            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=7,
                boundary_confidence="heuristic",
            )
            store.finalize_lap(lap_id, reason="completed")
            store.finalize_session(session_id, reason="manual_stop")

            with store.connect() as con:
                lap = con.execute(
                    """
                    SELECT session_id, lap_number, status, ended_at_ms, ended_reason, boundary_confidence
                    FROM laps
                    WHERE id = ?
                    """,
                    (lap_id,),
                ).fetchone()
                session = con.execute(
                    "SELECT label, status, ended_at_ms, ended_reason FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()

            self.assertEqual(lap["session_id"], session_id)
            self.assertEqual(lap["lap_number"], 7)
            self.assertEqual(lap["status"], "completed")
            self.assertIsNotNone(lap["ended_at_ms"])
            self.assertEqual(lap["ended_reason"], "completed")
            self.assertEqual(lap["boundary_confidence"], "heuristic")
            self.assertEqual(session["label"], "Lifecycle demo")
            self.assertEqual(session["status"], "manual_stop")
            self.assertIsNotNone(session["ended_at_ms"])
            self.assertEqual(session["ended_reason"], "manual_stop")

    def test_finalize_lap_can_update_boundary_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Final confidence demo")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )

            store.finalize_lap(
                lap_id,
                reason="lap_boundary",
                boundary_confidence="uncertain",
            )

            with store.connect() as con:
                lap = con.execute(
                    """
                    SELECT status, ended_reason, ended_at_ms, boundary_confidence
                    FROM laps
                    WHERE id = ?
                    """,
                    (lap_id,),
                ).fetchone()

            self.assertEqual(lap["status"], "lap_boundary")
            self.assertEqual(lap["ended_reason"], "lap_boundary")
            self.assertIsNotNone(lap["ended_at_ms"])
            self.assertEqual(lap["boundary_confidence"], "uncertain")


    def test_candidate_reference_laps_rejects_car_switch_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Car switch segment")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            raw_packets = [
                encode_packet_for_test(
                    {
                        "TimestampMS": 16,
                        "LapNumber": 1,
                        "CurrentLap": 1.0,
                        "CurrentRaceTime": 1.0,
                        "PositionX": 1.0,
                        "PositionY": 0.0,
                        "PositionZ": 1.0,
                        "Speed": 30.0,
                    }
                )
            ]
            decoded_packets = [decode_packet(raw_packets[0])]
            sample = _sample_from_decoded(0, decoded_packets[0])
            sample["lap_id"] = lap_id
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, [sample])
            store.insert_lap_summary(
                lap_id,
                {
                    "lap_duration_ms": 60_000,
                    "comparison_contexts": {"track": "emerald"},
                },
            )
            store.finalize_lap(
                lap_id,
                reason="lap_boundary",
                boundary_confidence="game_field",
            )
            with store.connect() as con:
                con.execute(
                    "UPDATE laps SET ended_reason = ? WHERE id = ?",
                    ("car_switch", lap_id),
                )

            candidates = store.candidate_reference_laps("track", "emerald", limit=10)

            self.assertNotIn(lap_id, [candidate["lap_id"] for candidate in candidates])

    def test_finalizers_reject_unknown_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            with self.assertRaisesRegex(ValueError, "unknown lap_id"):
                store.finalize_lap("missing-lap", reason="completed")
            with self.assertRaisesRegex(ValueError, "unknown session_id"):
                store.finalize_session("missing-session", reason="manual_stop")

    def test_latest_laps_and_sessions_return_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            old_session_id = store.create_session(label="Old session")
            new_session_id = store.create_session(label="New session")
            old_lap_id = store.create_lap(old_session_id, lap_number=1, boundary_confidence="game_field")
            new_lap_id = store.create_lap(new_session_id, lap_number=2, boundary_confidence="game_field")
            with store.connect() as con:
                con.execute(
                    "UPDATE sessions SET started_at_ms = ? WHERE id = ?",
                    (1_000, old_session_id),
                )
                con.execute(
                    "UPDATE sessions SET started_at_ms = ? WHERE id = ?",
                    (2_000, new_session_id),
                )
                con.execute(
                    "UPDATE laps SET started_at_ms = ? WHERE id = ?",
                    (1_100, old_lap_id),
                )
                con.execute(
                    "UPDATE laps SET started_at_ms = ? WHERE id = ?",
                    (2_100, new_lap_id),
                )

            latest_laps = store.latest_laps(limit=10)
            latest_sessions = store.latest_sessions(limit=10)

            self.assertEqual([lap["id"] for lap in latest_laps], [new_lap_id, old_lap_id])
            self.assertEqual(
                [(lap["session_id"], lap["session_label"]) for lap in latest_laps],
                [(new_session_id, "New session"), (old_session_id, "Old session")],
            )
            self.assertEqual(
                [session["id"] for session in latest_sessions],
                [new_session_id, old_session_id],
            )

    def _create_stats_lap(
        self,
        store: TelemetryStore,
        session_id: str,
        *,
        lap_number: int,
        duration_ms: int,
        speed_mps: float,
        track_profile_id: str | None = None,
        completed: bool = True,
    ) -> str:
        lap_id = store.create_lap(
            session_id=session_id,
            lap_number=lap_number,
            boundary_confidence="game_field",
        )
        raw_packets = [
            encode_packet_for_test(
                {
                    "TimestampMS": 100 + lap_number,
                    "LapNumber": lap_number,
                    "CurrentLap": 0.0,
                    "CurrentRaceTime": 0.0,
                    "Speed": speed_mps / 2.0,
                }
            ),
            encode_packet_for_test(
                {
                    "TimestampMS": 200 + lap_number,
                    "LapNumber": lap_number,
                    "CurrentLap": duration_ms / 1000.0,
                    "CurrentRaceTime": duration_ms / 1000.0,
                    "Speed": speed_mps,
                }
            ),
        ]
        decoded_packets = [decode_packet(raw) for raw in raw_packets]
        samples = [
            _sample_from_decoded(index, decoded)
            for index, decoded in enumerate(decoded_packets)
        ]
        for sample in samples:
            sample["lap_id"] = lap_id
        store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)
        if track_profile_id is not None:
            store.assign_track_profile(session_id, lap_id, track_profile_id)
        if completed:
            store.finalize_lap(
                lap_id,
                reason="completed",
                boundary_confidence="game_field",
            )
        return lap_id

    def test_stats_summary_aggregates_approved_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            emerald_full = store.create_track_profile(
                "Emerald Circuit",
                "Full",
                "manual",
                "high",
            )
            festival_sprint = store.create_track_profile(
                "Festival Sprint",
                "Sprint",
                "manual",
                "high",
            )
            mazda_1 = store.start_session(
                "Mazda Emerald",
                car_identity={
                    "car_name": "Mazda Furai",
                    "car_class_label": "S1",
                    "drivetrain_label": "RWD",
                },
            )
            mazda_2 = store.start_session(
                "Mazda Festival",
                car_identity={
                    "car_name": "Mazda Furai",
                    "car_class_label": "S1",
                    "drivetrain_label": "AWD",
                },
            )
            honda = store.start_session(
                "Honda Festival",
                car_identity={
                    "car_name": "Honda NSX-R GT",
                    "car_class_label": "A",
                    "drivetrain_label": "FWD",
                },
            )

            lap_ids = []
            lap_ids.append(self._create_stats_lap(
                store,
                mazda_1,
                lap_number=1,
                duration_ms=60_000,
                speed_mps=32.0,
                track_profile_id=emerald_full,
            ))
            lap_ids.append(self._create_stats_lap(
                store,
                mazda_1,
                lap_number=2,
                duration_ms=70_000,
                speed_mps=36.0,
                track_profile_id=emerald_full,
            ))
            lap_ids.append(self._create_stats_lap(
                store,
                mazda_2,
                lap_number=3,
                duration_ms=80_000,
                speed_mps=40.0,
                track_profile_id=festival_sprint,
            ))
            lap_ids.append(self._create_stats_lap(
                store,
                honda,
                lap_number=4,
                duration_ms=63_000,
                speed_mps=28.0,
            ))
            for lap_id in lap_ids:
                store.record_lifetime_lap_stats(lap_id)

            summary = store.stats_summary()

            self.assertEqual(summary["laps_recorded"], 4)
            self.assertEqual(summary["sessions_created"], 3)
            self.assertEqual(summary["max_speed_mps"], 40.0)
            self.assertEqual(summary["time_spent_racing_ms"], 273_000)
            self.assertEqual(summary["tracks_driven"], 2)
            self.assertEqual(summary["cars_driven"], 2)
            self.assertEqual(summary["favourite_car"]["value"], "Mazda Furai")
            self.assertEqual(summary["favourite_car"]["lap_count"], 3)
            self.assertEqual(summary["favourite_pi_class"]["value"], "S1")
            self.assertEqual(summary["favourite_pi_class"]["lap_count"], 3)
            self.assertEqual(summary["favoured_drive"]["value"], "RWD")
            self.assertEqual(summary["favoured_drive"]["lap_count"], 2)
            self.assertEqual(summary["favourite_track"]["value"], "Emerald Circuit")
            self.assertEqual(summary["favourite_track"]["detail"], "Full")
            self.assertEqual(summary["favourite_track"]["lap_count"], 2)

    def test_lifetime_stats_backfill_counts_existing_completed_laps_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "telemetry_tracker.sqlite3"
            store = TelemetryStore(db_path)
            store.migrate()
            track_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "high")
            session_id = store.start_session(
                "Backfill source",
                car_identity={
                    "car_ordinal": 1229,
                    "car_name": "Mazda Furai",
                    "car_class_label": "S1",
                    "drivetrain_label": "RWD",
                },
            )
            lap_id = self._create_stats_lap(
                store,
                session_id,
                lap_number=1,
                duration_ms=61_000,
                speed_mps=42.0,
                track_profile_id=track_id,
            )

            with store.connect() as con:
                con.execute("DELETE FROM lifetime_stat_laps")
                con.execute("DELETE FROM schema_migrations WHERE version = 11")

            store.migrate()
            store.migrate()
            summary = store.stats_summary()

            self.assertEqual(summary["laps_recorded"], 1)
            self.assertEqual(summary["sessions_created"], 1)
            self.assertEqual(summary["max_speed_mps"], 42.0)
            self.assertEqual(summary["time_spent_racing_ms"], 61_000)
            self.assertEqual(summary["tracks_driven"], 1)
            self.assertEqual(summary["cars_driven"], 1)
            self.assertEqual(summary["favourite_car"]["value"], "Mazda Furai")
            self.assertEqual(summary["favourite_track"]["value"], "Emerald Circuit")
            with store.connect() as con:
                rows = con.execute(
                    "SELECT lap_id FROM lifetime_stat_laps ORDER BY lap_id"
                ).fetchall()
            self.assertEqual([row["lap_id"] for row in rows], [lap_id])

            late_lap_id = self._create_stats_lap(
                store,
                session_id,
                lap_number=2,
                duration_ms=62_000,
                speed_mps=43.0,
                track_profile_id=track_id,
            )
            store.migrate()

            with store.connect() as con:
                rows = con.execute(
                    "SELECT lap_id FROM lifetime_stat_laps ORDER BY lap_id"
                ).fetchall()
            self.assertEqual([row["lap_id"] for row in rows], [lap_id])
            self.assertNotIn(late_lap_id, [row["lap_id"] for row in rows])

    def test_lifetime_stats_backfill_excludes_recording_laps(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "telemetry_tracker.sqlite3"
            store = TelemetryStore(db_path)
            store.migrate()
            session_id = store.start_session(
                "Active source",
                car_identity={"car_name": "Mazda Furai"},
            )
            self._create_stats_lap(
                store,
                session_id,
                lap_number=1,
                duration_ms=60_000,
                speed_mps=30.0,
                completed=False,
            )

            with store.connect() as con:
                con.execute("DELETE FROM lifetime_stat_laps")
                con.execute("DELETE FROM schema_migrations WHERE version = 11")

            store.migrate()
            summary = store.stats_summary()

            self.assertEqual(summary["laps_recorded"], 0)
            self.assertEqual(summary["sessions_created"], 0)
            self.assertEqual(summary["tracks_driven"], 0)
            self.assertEqual(summary["cars_driven"], 0)
            with store.connect() as con:
                snapshot_count = con.execute(
                    "SELECT COUNT(*) FROM lifetime_stat_laps"
                ).fetchone()[0]
            self.assertEqual(snapshot_count, 0)

    def test_stats_summary_handles_empty_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            summary = store.stats_summary()

            self.assertEqual(summary["laps_recorded"], 0)
            self.assertEqual(summary["sessions_created"], 0)
            self.assertIsNone(summary["max_speed_mps"])
            self.assertEqual(summary["time_spent_racing_ms"], 0)
            self.assertEqual(summary["tracks_driven"], 0)
            self.assertEqual(summary["cars_driven"], 0)
            self.assertIsNone(summary["favourite_car"])
            self.assertIsNone(summary["favourite_pi_class"])
            self.assertIsNone(summary["favoured_drive"])
            self.assertIsNone(summary["favourite_track"])

    def test_stats_summary_uses_lifetime_snapshots_after_source_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            track_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "high")
            session_id = store.start_session(
                "Deletion stable",
                car_identity={
                    "car_ordinal": 1229,
                    "car_name": "Mazda Furai",
                    "car_class_label": "S1",
                    "drivetrain_label": "RWD",
                },
            )
            lap_id = self._create_stats_lap(
                store,
                session_id,
                lap_number=1,
                duration_ms=62_000,
                speed_mps=41.5,
                track_profile_id=track_id,
            )
            store.record_lifetime_lap_stats(lap_id)

            store.delete_lap(lap_id)
            store.delete_session(session_id)
            summary = store.stats_summary()

            self.assertEqual(summary["laps_recorded"], 1)
            self.assertEqual(summary["sessions_created"], 1)
            self.assertEqual(summary["max_speed_mps"], 41.5)
            self.assertEqual(summary["time_spent_racing_ms"], 62_000)
            self.assertEqual(summary["tracks_driven"], 1)
            self.assertEqual(summary["cars_driven"], 1)
            self.assertEqual(summary["favourite_car"]["value"], "Mazda Furai")
            self.assertEqual(summary["favourite_track"]["value"], "Emerald Circuit")

    def test_stats_summary_cars_driven_ignores_drivetrain_for_same_car(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            rwd = store.start_session(
                "RWD",
                car_identity={"car_ordinal": 100, "car_name": "Same Car", "drivetrain_label": "RWD"},
            )
            awd = store.start_session(
                "AWD",
                car_identity={"car_ordinal": 100, "car_name": "Same Car", "drivetrain_label": "AWD"},
            )
            other = store.start_session(
                "Other",
                car_identity={"car_name": "Other Car", "drivetrain_label": "FWD"},
            )
            for index, session_id in enumerate([rwd, awd, other], start=1):
                lap_id = self._create_stats_lap(
                    store,
                    session_id,
                    lap_number=index,
                    duration_ms=60_000,
                    speed_mps=20.0 + index,
                )
                store.record_lifetime_lap_stats(lap_id)

            summary = store.stats_summary()

            self.assertEqual(summary["laps_recorded"], 3)
            self.assertEqual(summary["cars_driven"], 2)
            self.assertEqual(summary["favourite_car"]["value"], "Same Car")
            self.assertEqual(summary["favourite_car"]["lap_count"], 2)
            self.assertEqual(summary["favoured_drive"]["lap_count"], 1)

    def test_stats_summary_tracks_driven_counts_unique_assigned_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            alpha = store.create_track_profile("Alpha Speedway", "Full", "manual", "high")
            beta = store.create_track_profile("Beta Speedway", "Sprint", "manual", "high")
            session_id = store.start_session("Tracks", car_identity={"car_name": "Mazda Furai"})
            for index, track_id in enumerate([alpha, alpha, beta, None], start=1):
                lap_id = self._create_stats_lap(
                    store,
                    session_id,
                    lap_number=index,
                    duration_ms=60_000,
                    speed_mps=20.0 + index,
                    track_profile_id=track_id,
                )
                store.record_lifetime_lap_stats(lap_id)

            summary = store.stats_summary()

            self.assertEqual(summary["tracks_driven"], 2)
            self.assertEqual(summary["favourite_track"]["value"], "Alpha Speedway")
            self.assertEqual(summary["favourite_track"]["lap_count"], 2)

    def test_stats_summary_favourite_track_groups_renamed_snapshot_track_by_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            alpha = store.create_track_profile("Alpha Old", "Club", "manual", "high")
            session_id = store.start_session("Renamed track", car_identity={"car_name": "Mazda Furai"})
            old_lap = self._create_stats_lap(
                store,
                session_id,
                lap_number=1,
                duration_ms=60_000,
                speed_mps=20.0,
                track_profile_id=alpha,
            )
            store.record_lifetime_lap_stats(old_lap)
            store.update_track_profile(alpha, "Alpha New", "Grand Prix")
            new_lap = self._create_stats_lap(
                store,
                session_id,
                lap_number=2,
                duration_ms=61_000,
                speed_mps=21.0,
                track_profile_id=alpha,
            )
            store.record_lifetime_lap_stats(new_lap)
            with store.connect() as con:
                con.execute(
                    "UPDATE lifetime_stat_laps SET recorded_at_ms = ? WHERE lap_id = ?",
                    (1_000, old_lap),
                )
                con.execute(
                    "UPDATE lifetime_stat_laps SET recorded_at_ms = ? WHERE lap_id = ?",
                    (2_000, new_lap),
                )

            summary = store.stats_summary()

            self.assertEqual(summary["tracks_driven"], 1)
            self.assertEqual(summary["favourite_track"]["value"], "Alpha New")
            self.assertEqual(summary["favourite_track"]["detail"], "Grand Prix")
            self.assertEqual(summary["favourite_track"]["lap_count"], 2)

    def test_lifetime_stats_track_profile_update_refreshes_existing_snapshot_display(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            alpha = store.create_track_profile("Alpha Old", "Club", "manual", "high")
            session_id = store.start_session("Rename one track", car_identity={"car_name": "Mazda Furai"})
            lap_id = self._create_stats_lap(
                store,
                session_id,
                lap_number=1,
                duration_ms=60_000,
                speed_mps=20.0,
                track_profile_id=alpha,
            )
            store.record_lifetime_lap_stats(lap_id)

            store.update_track_profile(alpha, "Alpha New", "Grand Prix")
            summary = store.stats_summary()

            self.assertEqual(summary["tracks_driven"], 1)
            self.assertEqual(summary["favourite_track"]["value"], "Alpha New")
            self.assertEqual(summary["favourite_track"]["detail"], "Grand Prix")
            with store.connect() as con:
                snapshot = con.execute(
                    """
                    SELECT track_profile_id, track_name, track_layout
                    FROM lifetime_stat_laps
                    WHERE lap_id = ?
                    """,
                    (lap_id,),
                ).fetchone()
            self.assertEqual(snapshot["track_profile_id"], alpha)
            self.assertEqual(snapshot["track_name"], "Alpha New")
            self.assertEqual(snapshot["track_layout"], "Grand Prix")

    def test_lifetime_stats_track_profile_merge_collapses_snapshot_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            keep = store.create_track_profile("Alpha Kept", "Full", "manual", "high")
            merge = store.create_track_profile("Alpha Duplicate", "Sprint", "manual", "high")
            session_id = store.start_session("Duplicate tracks", car_identity={"car_name": "Mazda Furai"})
            keep_lap = self._create_stats_lap(
                store,
                session_id,
                lap_number=1,
                duration_ms=60_000,
                speed_mps=20.0,
                track_profile_id=keep,
            )
            merge_lap = self._create_stats_lap(
                store,
                session_id,
                lap_number=2,
                duration_ms=61_000,
                speed_mps=21.0,
                track_profile_id=merge,
            )
            store.record_lifetime_lap_stats(keep_lap)
            store.record_lifetime_lap_stats(merge_lap)
            self.assertEqual(store.stats_summary()["tracks_driven"], 2)

            store.merge_track_profiles(keep, merge)
            summary = store.stats_summary()

            self.assertEqual(summary["tracks_driven"], 1)
            self.assertEqual(summary["favourite_track"]["value"], "Alpha Kept")
            self.assertEqual(summary["favourite_track"]["detail"], "Full")
            self.assertEqual(summary["favourite_track"]["lap_count"], 2)
            with store.connect() as con:
                snapshots = con.execute(
                    """
                    SELECT track_profile_id, track_name, track_layout
                    FROM lifetime_stat_laps
                    ORDER BY lap_id
                    """
                ).fetchall()
            self.assertEqual(len(snapshots), 2)
            self.assertEqual(
                [(row["track_profile_id"], row["track_name"], row["track_layout"]) for row in snapshots],
                [(keep, "Alpha Kept", "Full"), (keep, "Alpha Kept", "Full")],
            )

    def test_lifetime_stats_track_reassignment_updates_existing_snapshot_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            alpha = store.create_track_profile("Alpha Speedway", "Full", "manual", "high")
            beta = store.create_track_profile("Beta Speedway", "Sprint", "manual", "high")
            session_id = store.start_session("Track repair", car_identity={"car_name": "Mazda Furai"})
            counted_lap = self._create_stats_lap(
                store,
                session_id,
                lap_number=1,
                duration_ms=60_000,
                speed_mps=30.0,
                track_profile_id=alpha,
            )
            uncounted_lap = self._create_stats_lap(
                store,
                session_id,
                lap_number=2,
                duration_ms=60_000,
                speed_mps=31.0,
                track_profile_id=alpha,
            )
            store.record_lifetime_lap_stats(counted_lap)
            with store.connect() as con:
                con.execute(
                    "UPDATE lifetime_stat_laps SET updated_at_ms = ? WHERE lap_id = ?",
                    (1, counted_lap),
                )

            store.assign_track_profile(session_id, counted_lap, beta)
            store.assign_track_profile(session_id, uncounted_lap, beta)
            summary = store.stats_summary()

            self.assertEqual(summary["laps_recorded"], 1)
            self.assertEqual(summary["tracks_driven"], 1)
            self.assertEqual(summary["favourite_track"]["value"], "Beta Speedway")
            with store.connect() as con:
                snapshot = con.execute(
                    """
                    SELECT track_profile_id, track_name, track_layout, updated_at_ms
                    FROM lifetime_stat_laps
                    """
                ).fetchone()
                count = con.execute("SELECT COUNT(*) FROM lifetime_stat_laps").fetchone()[0]
            self.assertEqual(count, 1)
            self.assertEqual(snapshot["track_profile_id"], beta)
            self.assertEqual(snapshot["track_name"], "Beta Speedway")
            self.assertEqual(snapshot["track_layout"], "Sprint")
            self.assertGreater(snapshot["updated_at_ms"], 1)

    def test_record_lifetime_lap_stats_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.start_session("Idempotent", car_identity={"car_name": "Mazda Furai"})
            lap_id = self._create_stats_lap(
                store,
                session_id,
                lap_number=1,
                duration_ms=60_000,
                speed_mps=30.0,
            )

            store.record_lifetime_lap_stats(lap_id)
            store.record_lifetime_lap_stats(lap_id)

            with store.connect() as con:
                count = con.execute("SELECT COUNT(*) FROM lifetime_stat_laps").fetchone()[0]
            self.assertEqual(count, 1)
            self.assertEqual(store.stats_summary()["laps_recorded"], 1)

    def test_lifetime_stats_recording_can_include_accepted_heuristic_lap(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.start_session("Auto accepted", car_identity={"car_name": "Mazda Furai"})
            lap_id = self._create_stats_lap(
                store,
                session_id,
                lap_number=1,
                duration_ms=10_000,
                speed_mps=42.0,
                completed=False,
            )
            store.finalize_lap(lap_id, reason="race_off", boundary_confidence="heuristic")
            store.insert_lap_summary(
                lap_id,
                {"completion_type": "track_matched_lap", "lap_time_ms": 10_000},
            )

            store.record_lifetime_lap_stats(lap_id)
            self.assertEqual(store.stats_summary()["laps_recorded"], 0)

            store.record_lifetime_lap_stats(lap_id, require_completed_candidate=False)
            summary = store.stats_summary()

            self.assertEqual(summary["laps_recorded"], 1)
            self.assertEqual(summary["time_spent_racing_ms"], 10_000)
            self.assertEqual(store.lap(lap_id)["boundary_confidence"], "heuristic")

    def test_stats_summary_sessions_created_counts_counted_sessions_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            empty_session = store.start_session("Empty", car_identity={"car_name": "Empty Car"})
            uncounted_session = store.start_session("Uncounted", car_identity={"car_name": "Uncounted Car"})
            counted_session = store.start_session("Counted", car_identity={"car_name": "Counted Car"})
            self._create_stats_lap(
                store,
                uncounted_session,
                lap_number=1,
                duration_ms=60_000,
                speed_mps=20.0,
            )
            counted_lap = self._create_stats_lap(
                store,
                counted_session,
                lap_number=2,
                duration_ms=61_000,
                speed_mps=21.0,
            )
            store.record_lifetime_lap_stats(counted_lap)
            self.assertIsNotNone(empty_session)

            summary = store.stats_summary()

            self.assertEqual(summary["laps_recorded"], 1)
            self.assertEqual(summary["sessions_created"], 1)

    def test_stats_summary_favourites_break_ties_by_recency_then_alphabetically(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            alpha_track = store.create_track_profile("Alpha Speedway", "Full", "manual", "high")
            beta_track = store.create_track_profile("Beta Speedway", "Full", "manual", "high")
            recent = store.start_session("Recent", car_identity={"car_name": "Alpha", "car_class_label": "A", "drivetrain_label": "AWD"})
            older = store.start_session("Older", car_identity={"car_name": "Beta", "car_class_label": "S1", "drivetrain_label": "RWD"})
            recent_lap = self._create_stats_lap(
                store,
                recent,
                lap_number=1,
                duration_ms=60_000,
                speed_mps=20.0,
                track_profile_id=alpha_track,
            )
            older_lap = self._create_stats_lap(
                store,
                older,
                lap_number=2,
                duration_ms=60_000,
                speed_mps=20.0,
                track_profile_id=beta_track,
            )
            store.record_lifetime_lap_stats(recent_lap)
            store.record_lifetime_lap_stats(older_lap)
            with store.connect() as con:
                con.execute("UPDATE lifetime_stat_laps SET recorded_at_ms = ? WHERE lap_id = ?", (5_000, recent_lap))
                con.execute("UPDATE lifetime_stat_laps SET recorded_at_ms = ? WHERE lap_id = ?", (2_000, older_lap))

            summary = store.stats_summary()

            self.assertEqual(summary["favourite_car"]["value"], "Alpha")
            self.assertEqual(summary["favourite_pi_class"]["value"], "A")
            self.assertEqual(summary["favoured_drive"]["value"], "AWD")
            self.assertEqual(summary["favourite_track"]["value"], "Alpha Speedway")
            self.assertEqual(summary["favourite_track"]["detail"], "Full")

            with store.connect() as con:
                con.execute("UPDATE lifetime_stat_laps SET recorded_at_ms = ? WHERE lap_id IN (?, ?)", (3_000, recent_lap, older_lap))

            summary = store.stats_summary()

            self.assertEqual(summary["favourite_car"]["value"], "Alpha")
            self.assertEqual(summary["favourite_pi_class"]["value"], "A")
            self.assertEqual(summary["favoured_drive"]["value"], "AWD")
            self.assertEqual(summary["favourite_track"]["value"], "Alpha Speedway")

    def test_stats_summary_favourite_track_uses_lap_recency_within_mixed_track_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            alpha_track = store.create_track_profile("Alpha Speedway", "Full", "manual", "high")
            beta_track = store.create_track_profile("Beta Speedway", "Full", "manual", "high")
            session_id = store.start_session("Mixed tracks")
            alpha_lap = self._create_stats_lap(
                store,
                session_id,
                lap_number=1,
                duration_ms=60_000,
                speed_mps=20.0,
                track_profile_id=alpha_track,
            )
            beta_lap = self._create_stats_lap(
                store,
                session_id,
                lap_number=2,
                duration_ms=60_000,
                speed_mps=20.0,
                track_profile_id=beta_track,
            )
            store.record_lifetime_lap_stats(alpha_lap)
            store.record_lifetime_lap_stats(beta_lap)
            with store.connect() as con:
                con.execute("UPDATE lifetime_stat_laps SET recorded_at_ms = ? WHERE lap_id = ?", (1_000, alpha_lap))
                con.execute("UPDATE lifetime_stat_laps SET recorded_at_ms = ? WHERE lap_id = ?", (2_000, beta_lap))

            summary = store.stats_summary()

            self.assertEqual(summary["favourite_track"]["value"], "Beta Speedway")
            self.assertEqual(summary["favourite_track"]["detail"], "Full")

    def test_stats_summary_time_spent_uses_lap_summary_primary_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.start_session("Summary time")
            lap_id = self._create_stats_lap(
                store,
                session_id,
                lap_number=1,
                duration_ms=60_000,
                speed_mps=25.0,
            )
            store.insert_lap_summary(lap_id, {"lap_time_ms": 59_000})
            store.record_lifetime_lap_stats(lap_id)

            self.assertEqual(store.stats_summary()["time_spent_racing_ms"], 59_000)

    def test_stats_summary_excludes_active_recording_laps_from_lifetime_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.start_session("Active speed")
            lap_id = self._create_stats_lap(
                store,
                session_id,
                lap_number=1,
                duration_ms=60_000,
                speed_mps=45.0,
                completed=False,
            )
            store.insert_lap_summary(lap_id, {"lap_time_ms": 12_345})

            summary = store.stats_summary()

            self.assertEqual(summary["laps_recorded"], 0)
            self.assertIsNone(summary["max_speed_mps"])
            self.assertEqual(summary["time_spent_racing_ms"], 0)

    def test_latest_laps_includes_game_field_completed_lap_time_from_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Timed session")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            raw_packets = [
                encode_packet_for_test({"TimestampMS": 100, "CurrentLap": 1.25}),
                encode_packet_for_test({"TimestampMS": 200, "CurrentLap": 74.75}),
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [
                _sample_from_decoded(index, decoded)
                for index, decoded in enumerate(decoded_packets)
            ]
            for sample in samples:
                sample["lap_id"] = lap_id
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)
            with store.connect() as con:
                con.execute(
                    """
                    UPDATE laps
                    SET status = ?, ended_reason = ?, started_at_ms = ?, ended_at_ms = ?
                    WHERE id = ?
                    """,
                    ("completed", "completed", 1_000, 99_000, lap_id),
                )

            lap = store.latest_laps(limit=1)[0]

            self.assertEqual(lap["id"], lap_id)
            self.assertEqual(lap["lap_time_ms"], 73_500)

    def test_latest_laps_does_not_use_single_sample_current_lap_as_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Single sample timed session")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            raw_packets = [
                encode_packet_for_test({"TimestampMS": 100, "CurrentLap": 42.5}),
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [
                _sample_from_decoded(index, decoded)
                for index, decoded in enumerate(decoded_packets)
            ]
            samples[0]["lap_id"] = lap_id
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)
            with store.connect() as con:
                con.execute(
                    """
                    UPDATE laps
                    SET status = ?, ended_reason = ?, started_at_ms = ?, ended_at_ms = ?
                    WHERE id = ?
                    """,
                    ("completed", "completed", 1_000, 99_000, lap_id),
                )

            lap = store.latest_laps(limit=1)[0]

            self.assertEqual(lap["id"], lap_id)
            self.assertEqual(lap["lap_time_ms"], 98_000)

    def test_latest_laps_returns_null_lap_time_for_recording_lap(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Recording session")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            raw_packets = [
                encode_packet_for_test({"TimestampMS": 100, "CurrentLap": 2.0}),
                encode_packet_for_test({"TimestampMS": 200, "CurrentLap": 62.0}),
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [
                _sample_from_decoded(index, decoded)
                for index, decoded in enumerate(decoded_packets)
            ]
            for sample in samples:
                sample["lap_id"] = lap_id
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            lap = store.latest_laps(limit=1)[0]

            self.assertEqual(lap["id"], lap_id)
            self.assertIsNone(lap["lap_time_ms"])

    def test_latest_laps_returns_null_lap_time_for_heuristic_low_confidence_lap(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Heuristic session")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="heuristic",
            )
            raw_packets = [
                encode_packet_for_test({"TimestampMS": 100, "CurrentLap": 3.0}),
                encode_packet_for_test({"TimestampMS": 200, "CurrentLap": 63.0}),
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [
                _sample_from_decoded(index, decoded)
                for index, decoded in enumerate(decoded_packets)
            ]
            for sample in samples:
                sample["lap_id"] = lap_id
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)
            with store.connect() as con:
                con.execute(
                    """
                    UPDATE laps
                    SET status = ?, ended_reason = ?, started_at_ms = ?, ended_at_ms = ?
                    WHERE id = ?
                    """,
                    ("completed", "completed", 1_000, 61_000, lap_id),
                )

            lap = store.latest_laps(limit=1)[0]

            self.assertEqual(lap["id"], lap_id)
            self.assertIsNone(lap["lap_time_ms"])

    def test_summary_lap_time_overrides_event_exit_heuristic_lap_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Summary timed sprint")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=0,
                boundary_confidence="heuristic",
            )
            raw_packets = [
                encode_packet_for_test(
                    {
                        "TimestampMS": 100,
                        "LapNumber": 0,
                        "CurrentLap": 0.014,
                        "CurrentRaceTime": 0.014,
                    }
                ),
                encode_packet_for_test(
                    {
                        "TimestampMS": 200,
                        "LapNumber": 0,
                        "CurrentLap": 129.174,
                        "CurrentRaceTime": 129.174,
                    }
                ),
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [
                _sample_from_decoded(index, decoded)
                for index, decoded in enumerate(decoded_packets)
            ]
            for sample in samples:
                sample["lap_id"] = lap_id
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)
            store.finalize_lap(
                lap_id,
                reason="event_exit",
                boundary_confidence="heuristic",
            )
            store.insert_lap_summary(
                lap_id,
                {
                    "packet_count": 2,
                    "sample_count": 2,
                    "completion_type": "sprint_event",
                    "lap_time_ms": 129_160,
                },
            )

            latest_lap = store.latest_laps(limit=1)[0]
            session_lap = store.laps_for_session(session_id)[0]
            session = store.latest_sessions(limit=1)[0]

            self.assertEqual(latest_lap["lap_time_ms"], 129_160)
            self.assertEqual(session_lap["lap_time_ms"], 129_160)
            self.assertEqual(session["completed_lap_count"], 1)
            self.assertEqual(session["best_lap_time_ms"], 129_160)
            self.assertEqual(session["average_lap_time_ms"], 129_160)
            self.assertEqual(session["total_lap_time_ms"], 129_160)

    def test_lap_summary_round_trips_as_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Summary demo")
            lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
            summary = {
                "packet_count": 2,
                "top_speed_mps": 12.5,
                "max_slip": None,
                "uncertainty_count": 1,
            }

            store.insert_lap_summary(lap_id, summary)

            self.assertEqual(store.lap_summary(lap_id), summary)
            self.assertIsNone(store.lap_summary("missing-lap"))

    def test_insert_issue_markers_upserts_detail_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Marker detail upsert")
            lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
            base_marker = {
                "id": "detail-marker",
                "session_id": session_id,
                "lap_id": lap_id,
                "start_sequence": 1,
                "end_sequence": 2,
                "metric": "rear_combined_slip",
                "severity": "critical",
                "reason": "Rear slip is high.",
                "ruleset_version": 1,
                "confidence": 0.75,
            }

            store.insert_issue_markers([base_marker])
            self.assertIsNone(store.issue_markers_for_lap(lap_id)[0]["anchor_sequence"])

            store.insert_issue_markers(
                [
                    _marker_with_detail_fields(
                        base_marker,
                        anchor_sequence=2,
                        issue_kind="Rear combined slip",
                        actual_value=1.28,
                        threshold_value=1.15,
                        threshold_operator="gte",
                        value_label="Rear combined slip",
                        value_unit=None,
                    )
                ]
            )

            stored = store.issue_markers_for_lap(lap_id)[0]
            self.assertEqual(stored["anchor_sequence"], 2)
            self.assertEqual(stored["issue_kind"], "Rear combined slip")
            self.assertAlmostEqual(stored["actual_value"], 1.28)
            self.assertAlmostEqual(stored["threshold_value"], 1.15)
            self.assertEqual(stored["threshold_operator"], "gte")
            self.assertEqual(stored["value_label"], "Rear combined slip")

    def test_issue_markers_for_lap_orders_same_span_markers_by_metric_before_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Marker ordering")
            lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
            store.insert_issue_markers(
                [
                    {
                        "id": "a-hash-for-z-metric",
                        "session_id": session_id,
                        "lap_id": lap_id,
                        "start_sequence": 10,
                        "end_sequence": 10,
                        "metric": "z_metric",
                        "severity": "warning",
                        "reason": "same span later metric",
                        "ruleset_version": 3,
                        "confidence": 0.8,
                    },
                    {
                        "id": "z-hash-for-a-metric",
                        "session_id": session_id,
                        "lap_id": lap_id,
                        "start_sequence": 10,
                        "end_sequence": 10,
                        "metric": "a_metric",
                        "severity": "warning",
                        "reason": "same span earlier metric",
                        "ruleset_version": 3,
                        "confidence": 0.8,
                    },
                ]
            )

            stored = store.issue_markers_for_lap(lap_id)

            self.assertEqual(
                [(marker["metric"], marker["id"]) for marker in stored],
                [
                    ("a_metric", "z-hash-for-a-metric"),
                    ("z_metric", "a-hash-for-z-metric"),
                ],
            )


    def test_replace_analysis_results_replaces_scope_markers_and_summary_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Atomic demo")
            lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
            store.insert_lap_summary(lap_id, {"packet_count": 1})
            store.insert_issue_markers(
                [
                    {
                        "id": "old-marker",
                        "session_id": session_id,
                        "lap_id": lap_id,
                        "start_sequence": 1,
                        "end_sequence": 2,
                        "metric": "rear_combined_slip",
                        "severity": "critical",
                        "reason": "old",
                        "ruleset_version": 1,
                        "confidence": 0.9,
                    }
                ]
            )

            store.replace_analysis_results(
                session_id=session_id,
                lap_id=lap_id,
                summary={"packet_count": 2, "top_speed_mps": 50.0},
                markers=[
                    {
                        "id": "new-marker",
                        "session_id": session_id,
                        "lap_id": lap_id,
                        "start_sequence": 3,
                        "end_sequence": 3,
                        "metric": "engine_rpm",
                        "severity": "info",
                        "reason": "new",
                        "ruleset_version": 1,
                        "confidence": 0.8,
                    }
                ],
            )

            self.assertEqual(store.lap_summary(lap_id), {"packet_count": 2, "top_speed_mps": 50.0})
            self.assertEqual(
                [marker["id"] for marker in store.issue_markers_for_lap(lap_id)],
                ["new-marker"],
            )

    def test_replace_analysis_results_rolls_back_summary_when_marker_insert_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Rollback demo")
            lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
            store.insert_lap_summary(lap_id, {"packet_count": 1})

            with self.assertRaisesRegex(ValueError, "unknown lap_id"):
                store.replace_analysis_results(
                    session_id=session_id,
                    lap_id=lap_id,
                    summary={"packet_count": 99},
                    markers=[
                        {
                            "id": "bad-marker",
                            "session_id": session_id,
                            "lap_id": "missing-lap",
                            "start_sequence": 1,
                            "end_sequence": 1,
                            "metric": "rear_combined_slip",
                            "severity": "critical",
                            "reason": "bad",
                            "ruleset_version": 1,
                            "confidence": 0.7,
                        }
                    ],
                )

            self.assertEqual(store.lap_summary(lap_id), {"packet_count": 1})
            self.assertEqual(store.issue_markers_for_lap(lap_id), [])


    def test_migrate_creates_cars_lookup_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            with store.connect() as con:
                columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(cars)").fetchall()
                }
                tables = {
                    row["name"]
                    for row in con.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }

        self.assertIn("cars", tables)
        self.assertIn("ordinal", columns)
        self.assertIn("display_name", columns)
        self.assertIn("model_short", columns)
        self.assertIn("catalog_source", columns)

    def test_upsert_and_get_car_catalog_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            store.upsert_car_catalog_records(
                [
                    {
                        "ordinal": 1229,
                        "display_name": "Furai",
                        "model_short": "Mazda Furai",
                        "make": "Mazda",
                        "model": "Furai",
                        "year": 2008,
                        "base_class_label": "R",
                        "base_pi": 998,
                        "car_type": "Extreme Track Toys",
                        "country": "Japan",
                        "catalog_source": "test",
                        "asset_name": "MAZ_Furai_08",
                        "asset_zip": "MAZ_Furai_08.zip",
                    }
                ]
            )

            car = store.car_by_ordinal(1229)

        self.assertEqual(car["ordinal"], 1229)
        self.assertEqual(car["display_name"], "Furai")
        self.assertEqual(car["model_short"], "Mazda Furai")
        self.assertEqual(car["year"], 2008)
        self.assertEqual(car["catalog_source"], "test")

    def test_upsert_car_catalog_records_preserves_existing_fields_when_new_values_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            store.upsert_car_catalog_records(
                [
                    {
                        "ordinal": 368,
                        "display_name": "Integra Type R",
                        "model_short": "Acura Integra",
                        "year": 2001,
                        "catalog_source": "string-table",
                    }
                ]
            )
            store.upsert_car_catalog_records(
                [
                    {
                        "ordinal": 368,
                        "asset_name": "ACU_IntegraR_01",
                        "asset_zip": "ACU_IntegraR_01.zip",
                        "catalog_source": "fh6_local_files",
                    }
                ]
            )

            car = store.car_by_ordinal(368)

        self.assertEqual(car["display_name"], "Integra Type R")
        self.assertEqual(car["model_short"], "Acura Integra")
        self.assertEqual(car["asset_zip"], "ACU_IntegraR_01.zip")
        self.assertEqual(car["catalog_source"], "fh6_local_files")

    def test_car_catalog_count_returns_number_of_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            self.assertEqual(store.car_catalog_count(), 0)
            store.upsert_car_catalog_records(
                [
                    {"ordinal": 1, "catalog_source": "test"},
                    {"ordinal": 2, "catalog_source": "test"},
                ]
            )
            self.assertEqual(store.car_catalog_count(), 2)

    def test_migrate_creates_game_track_lookup_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            with store.connect() as con:
                tables = {
                    row["name"]
                    for row in con.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                track_columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(game_tracks)").fetchall()
                }
                locator_columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(game_track_locators)").fetchall()
                }

        self.assertIn("game_tracks", tables)
        self.assertIn("game_map_regions", tables)
        self.assertIn("game_track_locators", tables)
        self.assertIn("game_track_profile_links", tables)
        self.assertIn("track_match_candidates", tables)
        self.assertIn("route_id", track_columns)
        self.assertIn("display_name_key", track_columns)
        self.assertIn("locator_kind", locator_columns)
        self.assertIn("transform_json", locator_columns)

    def test_migrate_adds_track_match_tables_to_existing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            with store.connect() as con:
                con.execute("DROP TABLE track_match_candidates")
                con.execute("DROP TABLE game_track_profile_links")

            store.migrate()
            with store.connect() as con:
                tables = {
                    row["name"]
                    for row in con.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }

        self.assertIn("track_match_candidates", tables)
        self.assertIn("game_track_profile_links", tables)

    def test_upsert_track_catalog_records_populates_tracks_regions_and_locators(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            counts = store.upsert_track_catalog_records(
                [
                    {
                        "track_key": "track-info:42",
                        "source_dataset_key": 42,
                        "route_id": 8001,
                        "custom_route_id": 28006,
                        "media_track_id": 820,
                        "media_track_name": "Brio",
                        "ribbon_config": "Circuit",
                        "display_name": "Legend Island Circuit",
                        "short_display_name": "Legend Island",
                        "short_display_name_all_caps": "LEGEND ISLAND CIRCUIT",
                        "description": "Fast circuit route.",
                        "display_name_key": "CareerTrackInfo.IDS_DisplayName_abc",
                        "catalog_source": "test",
                    }
                ],
                [
                    {
                        "region_key": "map_region_legend_island",
                        "english_name": "Legend Island",
                        "locator_collection_name": "map_region_legend_island",
                        "catalog_source": "test",
                    }
                ],
                [
                    {
                        "source_file": "Tracks/Brio/trackroutes/route3001.nt",
                        "media_track_name": "Brio",
                        "locator_collection": "route3001",
                        "locator_name": "start_line_000",
                        "locator_kind": "start_line",
                        "route_id": 3001,
                        "x": 1199.18,
                        "y": 101.98,
                        "z": -5318.32,
                        "heading_yaw_rad": 0.235,
                        "transform_json": '{"m41":1199.18}',
                        "catalog_source": "test",
                    }
                ],
            )

            track = store.game_track_by_route_id(8001)
            with store.connect() as con:
                region = con.execute(
                    "SELECT * FROM game_map_regions WHERE region_key = ?",
                    ("map_region_legend_island",),
                ).fetchone()
                locator = con.execute(
                    "SELECT * FROM game_track_locators WHERE source_file = ? AND locator_name = ?",
                    ("Tracks/Brio/trackroutes/route3001.nt", "start_line_000"),
                ).fetchone()
            track_catalog_count = store.track_catalog_count()

        self.assertEqual(counts, {"tracks": 1, "map_regions": 1, "locators": 1})
        self.assertEqual(track_catalog_count, 1)
        self.assertEqual(track["display_name"], "Legend Island Circuit")
        self.assertEqual(track["use_cross_country_ai"], None)
        self.assertEqual(region["english_name"], "Legend Island")
        self.assertEqual(locator["locator_kind"], "start_line")
        self.assertEqual(locator["route_id"], 3001)

    def test_migrate_creates_world_map_settings_and_tile_set_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            with store.connect() as con:
                settings_columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(user_settings)").fetchall()
                }
                tile_set_columns = {
                    row["name"]
                    for row in con.execute(
                        "PRAGMA table_info(world_map_tile_sets)"
                    ).fetchall()
                }
                tables = {
                    row["name"]
                    for row in con.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }

            settings = store.world_map_settings()

        self.assertIn("fh6_media_root", settings_columns)
        self.assertIn("world_map_enabled", settings_columns)
        self.assertIn("world_map_season", settings_columns)
        self.assertIn("world_map_tile_sets", tables)
        self.assertIn("world_origin_x", tile_set_columns)
        self.assertEqual(
            settings,
            {
                "fh6_media_root": None,
                "world_map_enabled": False,
                "world_map_season": "summer",
            },
        )

    def test_update_world_map_settings_persists_normalized_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            settings = store.update_world_map_settings(
                media_root=" G:/SteamLibrary/steamapps/common/ForzaHorizon6/media ",
                enabled=True,
                season="Winter",
            )
            reread = store.world_map_settings()

        self.assertEqual(settings["fh6_media_root"], "G:/SteamLibrary/steamapps/common/ForzaHorizon6/media")
        self.assertEqual(settings["world_map_enabled"], True)
        self.assertEqual(settings["world_map_season"], "winter")
        self.assertEqual(reread, settings)

    def test_update_world_map_settings_rejects_unknown_season(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            with self.assertRaisesRegex(ValueError, "world_map_season"):
                store.update_world_map_settings(
                    media_root=None,
                    enabled=False,
                    season="monsoon",
                )

    def test_upsert_and_fetch_world_map_tile_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            record = {
                "id": "fh6-brio-summer",
                "game": "fh6",
                "map_name": "brio",
                "season": "summer",
                "source_zip_path": "G:/FH6/media/UI/Textures/Data_Bound/Map_Brio_Summer.zip",
                "source_zip_mtime_ms": 1710000000000,
                "source_zip_size_bytes": 35635086,
                "cache_dir": "C:/Users/example/AppData/Local/Forza Telemetry Tracker/map-cache/fh6/brio/summer",
                "tile_format": "png",
                "tile_size": 1024,
                "min_zoom": 0,
                "max_zoom": 3,
                "world_origin_x": -12548.0,
                "world_origin_z": -11281.0,
                "world_size": 22035.0,
                "status": "ready",
                "manifest_json": json.dumps({"tileSize": 1024, "tiles": []}),
                "error_message": None,
            }

            inserted = store.upsert_world_map_tile_set(record)
            fetched = store.world_map_tile_set("fh6-brio-summer")
            latest = store.latest_world_map_tile_set("fh6", "brio", "summer")

        self.assertEqual(inserted["id"], "fh6-brio-summer")
        self.assertEqual(inserted["manifest"], {"tileSize": 1024, "tiles": []})
        self.assertEqual(fetched["world_origin_x"], -12548.0)
        self.assertEqual(fetched["status"], "ready")
        self.assertEqual(latest["id"], "fh6-brio-summer")

    def test_upsert_world_map_tile_set_rejects_unknown_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            with self.assertRaisesRegex(ValueError, "status"):
                store.upsert_world_map_tile_set(
                    {
                        "id": "bad-status",
                        "game": "fh6",
                        "map_name": "brio",
                        "season": "summer",
                        "source_zip_path": "G:/FH6/Map_Brio_Summer.zip",
                        "source_zip_mtime_ms": 1,
                        "source_zip_size_bytes": 1,
                        "cache_dir": "C:/cache",
                        "tile_format": "png",
                        "tile_size": 1024,
                        "min_zoom": 0,
                        "max_zoom": 0,
                        "world_origin_x": -12548.0,
                        "world_origin_z": -11281.0,
                        "world_size": 22035.0,
                        "status": "done",
                        "manifest_json": "{}",
                    }
                )


    def test_packet_bytes_for_lap_returns_ordered_raw_packets(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Packet bytes")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            first_raw = encode_packet_for_test({"TimestampMS": 32, "LapNumber": 1})
            second_raw = encode_packet_for_test({"TimestampMS": 16, "LapNumber": 1})
            raw_packets = [first_raw, second_raw]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [
                _sample_from_decoded(2, decoded_packets[0]),
                _sample_from_decoded(1, decoded_packets[1]),
            ]
            for sample in samples:
                sample["lap_id"] = lap_id
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            ordered = store.packet_bytes_for_lap(lap_id)

            self.assertEqual(
                [decode_packet(raw)["TimestampMS"] for raw in ordered],
                [16, 32],
            )

    def test_prune_unassigned_non_race_telemetry_removes_only_zero_state_null_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Maintenance")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            raw_packets = [
                encode_packet_for_test(
                    {
                        "IsRaceOn": 0,
                        "TimestampMS": 16,
                        "LapNumber": 0,
                        "CurrentLap": 0.0,
                        "CurrentRaceTime": 0.0,
                    }
                ),
                encode_packet_for_test(
                    {
                        "IsRaceOn": 1,
                        "TimestampMS": 32,
                        "LapNumber": 0,
                        "CurrentLap": 0.2,
                        "CurrentRaceTime": 0.2,
                    }
                ),
                encode_packet_for_test(
                    {
                        "IsRaceOn": 0,
                        "TimestampMS": 48,
                        "LapNumber": 1,
                        "CurrentLap": 12.0,
                        "CurrentRaceTime": 12.0,
                    }
                ),
                encode_packet_for_test(
                    {
                        "IsRaceOn": 1,
                        "TimestampMS": 64,
                        "LapNumber": 1,
                        "CurrentLap": 1.0,
                        "CurrentRaceTime": 1.0,
                    }
                ),
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [
                _sample_from_decoded(index, decoded)
                for index, decoded in enumerate(decoded_packets)
            ]
            samples[3]["lap_id"] = lap_id
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            dry_run = store.prune_unassigned_non_race_telemetry(dry_run=True)
            self.assertEqual(dry_run["target_sample_count"], 1)
            self.assertEqual(store.count_prunable_unassigned_non_race_telemetry(), 1)

            result = store.prune_unassigned_non_race_telemetry()

            self.assertEqual(result["target_sample_count"], 1)
            self.assertEqual(result["deleted_sample_count"], 1)
            self.assertEqual(result["deleted_packet_count"], 1)
            self.assertEqual(store.count_prunable_unassigned_non_race_telemetry(), 0)
            with store.connect() as con:
                sample_rows = con.execute(
                    "SELECT lap_id, is_race_on, lap_number, current_lap FROM lap_samples ORDER BY sequence"
                ).fetchall()
                packet_count = con.execute("SELECT COUNT(*) FROM packet_blobs").fetchone()[0]
            self.assertEqual(packet_count, 3)
            self.assertEqual(len(sample_rows), 3)
            self.assertIsNone(sample_rows[0]["lap_id"])
            self.assertEqual(sample_rows[0]["is_race_on"], 1)
            self.assertIsNone(sample_rows[1]["lap_id"])
            self.assertEqual(sample_rows[1]["lap_number"], 1)
            self.assertEqual(sample_rows[1]["current_lap"], 12.0)
            self.assertEqual(sample_rows[2]["lap_id"], lap_id)

    def test_prune_unassigned_non_race_telemetry_honors_max_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Maintenance batch")
            raw_packets = [
                encode_packet_for_test(
                    {
                        "IsRaceOn": 0,
                        "TimestampMS": index * 16,
                        "LapNumber": 0,
                        "CurrentLap": 0.0,
                        "CurrentRaceTime": 0.0,
                    }
                )
                for index in range(1, 4)
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [
                _sample_from_decoded(index, decoded)
                for index, decoded in enumerate(decoded_packets)
            ]
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)

            result = store.prune_unassigned_non_race_telemetry(max_rows=2)

            self.assertEqual(result["deleted_sample_count"], 2)
            self.assertEqual(result["deleted_packet_count"], 2)
            self.assertEqual(store.count_prunable_unassigned_non_race_telemetry(), 1)
            with self.assertRaisesRegex(ValueError, "max_rows"):
                store.prune_unassigned_non_race_telemetry(max_rows=0)

    def test_database_size_checkpoint_and_vacuum_threshold_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            info = store.database_size_info()
            self.assertGreater(info["page_size"], 0)
            self.assertGreater(info["page_count"], 0)
            self.assertIn("freelist_ratio", info)
            checkpoint = store.wal_checkpoint_truncate()
            self.assertIn("busy", checkpoint)
            skipped = store.vacuum_if_needed(
                min_freelist_bytes=10**12,
                min_freelist_ratio=1.0,
            )
            self.assertFalse(skipped["ran"])
            self.assertEqual(skipped["reason"], "below_threshold")
            forced = store.vacuum_if_needed(
                min_freelist_bytes=10**12,
                min_freelist_ratio=1.0,
                force=True,
            )
            self.assertTrue(forced["ran"])
            self.assertEqual(forced["reason"], "forced")
            self.assertGreater(forced["after"]["page_count"], 0)

    def test_history_helpers_reject_non_positive_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            for method in (store.latest_laps, store.latest_sessions):
                for limit in (0, -1):
                    with self.subTest(method=method.__name__, limit=limit):
                        with self.assertRaisesRegex(ValueError, "limit must be positive"):
                            method(limit=limit)

    def test_connect_requires_migration_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "missing.sqlite3")
            with self.assertRaises(sqlite3.OperationalError):
                store.create_session(label="No migration")


if __name__ == "__main__":
    unittest.main()
