import math
import sqlite3
import tempfile
import unittest
from pathlib import Path

from telemetry_tracker.storage import LOCAL_USER_ID, TelemetryStore
from telemetry_tracker.track_profiles import (
    assign_best_track_profile,
    match_track_profile,
    shape_signature,
    signature_distance,
)


def _store_in(tmp: str) -> TelemetryStore:
    store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
    store.migrate()
    return store


def _oval_samples(
    count: int = 96,
    *,
    scale: float = 1.0,
    offset_x: float = 0.0,
    offset_z: float = 0.0,
    use_aliases: bool = False,
) -> list[dict]:
    samples = []
    for index in range(count):
        angle = (2.0 * math.pi * index) / (count - 1)
        x = offset_x + scale * 120.0 * math.cos(angle)
        z = offset_z + scale * 70.0 * math.sin(angle)
        if use_aliases:
            samples.append({"position_x": x, "position_z": z})
        else:
            samples.append({"x": x, "z": z})
    return samples


def _nonuniform_oval_samples(count: int = 160) -> list[dict]:
    samples = []
    for index in range(count):
        progress = index / (count - 1)
        angle = 2.0 * math.pi * (progress**2.35)
        samples.append(
            {
                "x": 120.0 * math.cos(angle),
                "z": 70.0 * math.sin(angle),
            }
        )
    return samples


def _triangle_samples(count: int = 96) -> list[dict]:
    vertices = [(0.0, 0.0), (1.0, 1.0), (2.0, 0.0), (0.0, 0.0)]
    samples = []
    for index in range(count):
        progress = index / (count - 1)
        scaled = progress * (len(vertices) - 1)
        segment = min(len(vertices) - 2, int(scaled))
        segment_progress = scaled - segment
        start = vertices[segment]
        end = vertices[segment + 1]
        samples.append(
            {
                "x": start[0] + ((end[0] - start[0]) * segment_progress),
                "z": start[1] + ((end[1] - start[1]) * segment_progress),
            }
        )
    return samples


def _half_lap_samples(count: int = 64) -> list[dict]:
    samples = []
    for index in range(count):
        angle = (math.pi * index) / (count - 1)
        samples.append({"x": 100.0 * math.cos(angle), "z": 60.0 * math.sin(angle)})
    return samples


def _track_columns(store: TelemetryStore, table_name: str) -> set[str]:
    with store.connect() as con:
        return {
            row["name"]
            for row in con.execute(f"PRAGMA table_info({table_name})").fetchall()
        }


def _track_profile_foreign_keys(store: TelemetryStore, table_name: str) -> set[tuple]:
    with store.connect() as con:
        return {
            (row["from"], row["table"], row["to"], row["on_delete"])
            for row in con.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
        }


def _create_database_with_plain_track_profile_columns(db_path: Path) -> None:
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
                CREATE TABLE track_profiles (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT,
                    name TEXT NOT NULL,
                    layout TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    shape_signature TEXT,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    label TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'recording',
                    started_at_ms INTEGER NOT NULL,
                    ended_at_ms INTEGER,
                    ended_reason TEXT,
                    track_profile_id TEXT,
                    notes TEXT
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
                    boundary_confidence TEXT NOT NULL DEFAULT 'unknown',
                    track_profile_id TEXT,
                    notes TEXT
                );
                CREATE TABLE migration_audit (
                    table_name TEXT NOT NULL,
                    row_id TEXT NOT NULL,
                    note TEXT NOT NULL
                );
                CREATE INDEX idx_legacy_sessions_notes
                ON sessions(notes);
                CREATE INDEX idx_legacy_laps_notes
                ON laps(notes);
                CREATE TRIGGER trg_legacy_sessions_notes
                AFTER INSERT ON sessions
                WHEN NEW.notes IS NOT NULL
                BEGIN
                    INSERT INTO migration_audit(table_name, row_id, note)
                    VALUES ('sessions', NEW.id, NEW.notes);
                END;
                CREATE TRIGGER trg_legacy_laps_notes
                AFTER INSERT ON laps
                WHEN NEW.notes IS NOT NULL
                BEGIN
                    INSERT INTO migration_audit(table_name, row_id, note)
                    VALUES ('laps', NEW.id, NEW.notes);
                END;
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
                    gear INTEGER NOT NULL
                );
                """
            )
            con.executemany(
                "INSERT INTO schema_migrations(version, applied_at_ms) VALUES (?, ?)",
                [(1, 1_000), (2, 2_000), (3, 3_000)],
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
                INSERT INTO track_profiles(
                    id, owner_user_id, name, layout, source, confidence,
                    created_at_ms, updated_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "valid-profile",
                    LOCAL_USER_ID,
                    "Valid",
                    "Full",
                    "manual",
                    "user",
                    1_000,
                    1_000,
                ),
            )
            con.executemany(
                """
                INSERT INTO sessions(
                    id, user_id, label, status, started_at_ms,
                    track_profile_id, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "valid-session",
                        LOCAL_USER_ID,
                        "Valid session",
                        "recording",
                        2_000,
                        "valid-profile",
                        "keep session note",
                    ),
                    (
                        "invalid-session",
                        LOCAL_USER_ID,
                        "Invalid session",
                        "recording",
                        2_100,
                        "missing-profile",
                        "drop invalid profile only",
                    ),
                ],
            )
            con.executemany(
                """
                INSERT INTO laps(
                    id, user_id, session_id, lap_number, status, started_at_ms,
                    boundary_confidence, track_profile_id, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "valid-lap",
                        LOCAL_USER_ID,
                        "valid-session",
                        1,
                        "recording",
                        2_010,
                        "game_field",
                        "valid-profile",
                        "keep lap note",
                    ),
                    (
                        "invalid-lap",
                        LOCAL_USER_ID,
                        "invalid-session",
                        1,
                        "recording",
                        2_110,
                        "game_field",
                        "missing-profile",
                        "drop invalid lap profile only",
                    ),
                ],
            )
    finally:
        con.close()


class _BrokenDependentSqlStore(TelemetryStore):
    def _table_dependent_sql(
        self,
        con: sqlite3.Connection,
        table_name: str,
    ) -> list[str]:
        dependent_sql = super()._table_dependent_sql(con, table_name)
        if table_name == "sessions":
            return [*dependent_sql, "CREATE INDEX broken dependent sql"]
        return dependent_sql


class TrackProfileStorageTests(unittest.TestCase):
    def test_migration_adds_track_profiles_and_nullable_reference_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            store.migrate()

            with store.connect() as con:
                tables = {
                    row["name"]
                    for row in con.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                profile_columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(track_profiles)").fetchall()
                }
                session_column = con.execute(
                    """
                    SELECT [notnull]
                    FROM pragma_table_info('sessions')
                    WHERE name = 'track_profile_id'
                    """
                ).fetchone()
                lap_column = con.execute(
                    """
                    SELECT [notnull]
                    FROM pragma_table_info('laps')
                    WHERE name = 'track_profile_id'
                    """
                ).fetchone()

            self.assertIn("track_profiles", tables)
            self.assertEqual(
                profile_columns,
                {
                    "id",
                    "owner_user_id",
                    "name",
                    "layout",
                    "source",
                    "confidence",
                    "shape_signature",
                    "created_at_ms",
                    "updated_at_ms",
                },
            )
            self.assertEqual(session_column["notnull"], 0)
            self.assertEqual(lap_column["notnull"], 0)
            self.assertIn(
                ("track_profile_id", "track_profiles", "id", "SET NULL"),
                _track_profile_foreign_keys(store, "sessions"),
            )
            self.assertIn(
                ("track_profile_id", "track_profiles", "id", "SET NULL"),
                _track_profile_foreign_keys(store, "laps"),
            )

    def test_migration_repairs_plain_track_profile_columns_to_foreign_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.sqlite3"
            _create_database_with_plain_track_profile_columns(db_path)
            store = TelemetryStore(db_path)

            store.migrate()
            store.migrate()

            self.assertIn(
                ("track_profile_id", "track_profiles", "id", "SET NULL"),
                _track_profile_foreign_keys(store, "sessions"),
            )
            self.assertIn(
                ("track_profile_id", "track_profiles", "id", "SET NULL"),
                _track_profile_foreign_keys(store, "laps"),
            )
            with store.connect() as con:
                session_rows = {
                    row["id"]: (row["track_profile_id"], row["notes"])
                    for row in con.execute(
                        "SELECT id, track_profile_id, notes FROM sessions"
                    ).fetchall()
                }
                lap_rows = {
                    row["id"]: (row["track_profile_id"], row["notes"])
                    for row in con.execute(
                        "SELECT id, track_profile_id, notes FROM laps"
                    ).fetchall()
                }
                preserved_objects = {
                    row["name"]
                    for row in con.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type IN ('index', 'trigger')
                          AND tbl_name IN ('sessions', 'laps')
                        """
                    ).fetchall()
                }
                con.execute(
                    """
                    INSERT INTO sessions(
                        id, user_id, label, status, started_at_ms, notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "trigger-session",
                        LOCAL_USER_ID,
                        "Trigger session",
                        "recording",
                        3_000,
                        "session trigger survived",
                    ),
                )
                con.execute(
                    """
                    INSERT INTO laps(
                        id, user_id, session_id, lap_number, status, started_at_ms,
                        boundary_confidence, notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "trigger-lap",
                        LOCAL_USER_ID,
                        "trigger-session",
                        1,
                        "recording",
                        3_010,
                        "game_field",
                        "lap trigger survived",
                    ),
                )
                audit_rows = {
                    (row["table_name"], row["row_id"], row["note"])
                    for row in con.execute(
                        "SELECT table_name, row_id, note FROM migration_audit"
                    ).fetchall()
                }
            self.assertEqual(
                session_rows["valid-session"],
                ("valid-profile", "keep session note"),
            )
            self.assertEqual(
                session_rows["invalid-session"],
                (None, "drop invalid profile only"),
            )
            self.assertEqual(lap_rows["valid-lap"], ("valid-profile", "keep lap note"))
            self.assertEqual(
                lap_rows["invalid-lap"],
                (None, "drop invalid lap profile only"),
            )
            self.assertIn("idx_legacy_sessions_notes", preserved_objects)
            self.assertIn("idx_legacy_laps_notes", preserved_objects)
            self.assertIn("trg_legacy_sessions_notes", preserved_objects)
            self.assertIn("trg_legacy_laps_notes", preserved_objects)
            self.assertIn(
                ("sessions", "trigger-session", "session trigger survived"),
                audit_rows,
            )
            self.assertIn(("laps", "trigger-lap", "lap trigger survived"), audit_rows)

    def test_failed_dependent_sql_recreation_rolls_back_fk_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.sqlite3"
            _create_database_with_plain_track_profile_columns(db_path)
            store = _BrokenDependentSqlStore(db_path)

            with self.assertRaises(sqlite3.OperationalError):
                store.migrate()

            self.assertNotIn(
                ("track_profile_id", "track_profiles", "id", "SET NULL"),
                _track_profile_foreign_keys(store, "sessions"),
            )
            self.assertIn("notes", _track_columns(store, "sessions"))
            with store.connect() as con:
                preserved_objects = {
                    row["name"]
                    for row in con.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type IN ('index', 'trigger')
                          AND tbl_name = 'sessions'
                        """
                    ).fetchall()
                }
                row = con.execute(
                    "SELECT track_profile_id, notes FROM sessions WHERE id = ?",
                    ("valid-session",),
                ).fetchone()
                old_tables = {
                    row["name"]
                    for row in con.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'table'
                          AND name LIKE '__sessions_old_track_profile_fk_%'
                        """
                    ).fetchall()
                }

            self.assertEqual(tuple(row), ("valid-profile", "keep session note"))
            self.assertIn("idx_legacy_sessions_notes", preserved_objects)
            self.assertIn("trg_legacy_sessions_notes", preserved_objects)
            self.assertEqual(old_tables, set())

    def test_create_track_profile_returns_id_and_persists_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            signature = shape_signature(_oval_samples(), buckets=8)

            profile_id = store.create_track_profile(
                name="Horizon Mexico Circuit",
                layout="Full",
                source="shape_match",
                confidence="auto",
                shape_signature=signature,
            )

            profile = store.track_profile(profile_id)
            self.assertIsNotNone(profile)
            self.assertEqual(profile["id"], profile_id)
            self.assertEqual(profile["name"], "Horizon Mexico Circuit")
            self.assertEqual(profile["layout"], "Full")
            self.assertEqual(profile["source"], "shape_match")
            self.assertEqual(profile["confidence"], "auto")
            self.assertEqual(profile["shape_signature"], signature)

    def test_track_profile_text_fields_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)

            create_cases = [
                ("name", ("", "Full", "manual", "user")),
                ("layout", ("Emerald", " ", "manual", "user")),
                ("source", ("Emerald", "Full", "", "user")),
                ("confidence", ("Emerald", "Full", "manual", " ")),
            ]
            for field_name, args in create_cases:
                with self.subTest(method="create", field=field_name):
                    with self.assertRaisesRegex(ValueError, f"{field_name} is required"):
                        store.create_track_profile(*args)

            profile_id = store.create_track_profile("Emerald", "Full", "manual", "user")
            update_cases = [
                ("name", ("", "Full")),
                ("layout", ("Emerald", " ")),
            ]
            for field_name, args in update_cases:
                with self.subTest(method="update", field=field_name):
                    with self.assertRaisesRegex(ValueError, f"{field_name} is required"):
                        store.update_track_profile(profile_id, *args)

    def test_track_profile_foreign_keys_reject_invalid_ids_and_set_null_on_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald", "Full", "manual", "user")
            session_id = store.create_session("FK demo")
            lap_id = store.create_lap(
                session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            with store.connect() as con:
                con.execute(
                    "UPDATE sessions SET track_profile_id = ? WHERE id = ?",
                    (profile_id, session_id),
                )
            store.assign_track_profile(session_id, lap_id, profile_id)

            with self.assertRaises(sqlite3.IntegrityError):
                with store.connect() as con:
                    con.execute(
                        "UPDATE sessions SET track_profile_id = ? WHERE id = ?",
                        ("missing-profile", session_id),
                    )
            with self.assertRaises(sqlite3.IntegrityError):
                with store.connect() as con:
                    con.execute(
                        "UPDATE laps SET track_profile_id = ? WHERE id = ?",
                        ("missing-profile", lap_id),
                    )

            with store.connect() as con:
                con.execute("DELETE FROM track_profiles WHERE id = ?", (profile_id,))
                session_profile_id = con.execute(
                    "SELECT track_profile_id FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()["track_profile_id"]
                lap_profile_id = con.execute(
                    "SELECT track_profile_id FROM laps WHERE id = ?",
                    (lap_id,),
                ).fetchone()["track_profile_id"]

            self.assertIsNone(session_profile_id)
            self.assertIsNone(lap_profile_id)

    def test_legacy_session_track_profile_backfills_unassigned_laps_on_migrate(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "telemetry_tracker.sqlite3"
            store = _store_in(tmp)
            legacy_profile_id = store.create_track_profile("Legacy", "Full", "manual", "user")
            explicit_profile_id = store.create_track_profile("Explicit", "Sprint", "manual", "user")
            session_id = store.create_session("Legacy session track")
            unassigned_lap_id = store.create_lap(
                session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            explicit_lap_id = store.create_lap(
                session_id,
                lap_number=2,
                boundary_confidence="game_field",
            )
            with store.connect() as con:
                con.execute(
                    "UPDATE sessions SET track_profile_id = ? WHERE id = ?",
                    (legacy_profile_id, session_id),
                )
                con.execute(
                    "UPDATE laps SET track_profile_id = ? WHERE id = ?",
                    (explicit_profile_id, explicit_lap_id),
                )

            TelemetryStore(db_path).migrate()

            with store.connect() as con:
                rows = {
                    row["id"]: row["track_profile_id"]
                    for row in con.execute(
                        "SELECT id, track_profile_id FROM laps WHERE session_id = ?",
                        (session_id,),
                    ).fetchall()
                }
            self.assertEqual(rows[unassigned_lap_id], legacy_profile_id)
            self.assertEqual(rows[explicit_lap_id], explicit_profile_id)

    def test_new_lap_does_not_inherit_legacy_session_track_profile_assignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald", "Full", "manual", "user")
            session_id = store.create_session("Track day")
            with store.connect() as con:
                con.execute(
                    "UPDATE sessions SET track_profile_id = ? WHERE id = ?",
                    (profile_id, session_id),
                )

            lap_id = store.create_lap(
                session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )

            lap = store.lap(lap_id)
            self.assertIsNotNone(lap)
            self.assertIsNone(lap["track_profile_id"])
            self.assertIsNone(lap["track_profile_name"])
            self.assertIsNone(lap["track_profile_layout"])

    def test_assign_track_profile_requires_lap_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald", "Full", "manual", "user")
            session_id = store.create_session("Track day")
            store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")

            with self.assertRaisesRegex(ValueError, "lap_id is required"):
                store.assign_track_profile(session_id, None, profile_id)

    def test_latest_history_includes_track_profile_display_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald", "Full", "manual", "user")
            session_id = store.create_session("History profile")
            lap_id = store.create_lap(
                session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )

            store.assign_track_profile(session_id, lap_id, profile_id)

            session = store.latest_sessions(limit=1)[0]
            lap = store.latest_laps(limit=1)[0]
            self.assertEqual(session["id"], session_id)
            self.assertNotIn("track_profile_id", session)
            self.assertNotIn("track_profile_name", session)
            self.assertNotIn("track_profile_layout", session)
            self.assertEqual(lap["id"], lap_id)
            self.assertEqual(lap["track_profile_id"], profile_id)
            self.assertEqual(lap["track_profile_name"], "Emerald")
            self.assertEqual(lap["track_profile_layout"], "Full")

    def test_assign_track_profile_to_one_lap_leaves_siblings_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            original_profile_id = store.create_track_profile(
                "Original",
                "Full",
                "manual",
                "user",
            )
            lap_profile_id = store.create_track_profile(
                "Corrected",
                "Sprint",
                "manual",
                "user",
            )
            session_id = store.create_session("Mixed track day")
            first_lap_id = store.create_lap(
                session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            second_lap_id = store.create_lap(
                session_id,
                lap_number=2,
                boundary_confidence="game_field",
            )
            store.assign_track_profile(session_id, second_lap_id, original_profile_id)

            store.assign_track_profile(session_id, first_lap_id, lap_profile_id)

            with store.connect() as con:
                rows = con.execute(
                    "SELECT id, track_profile_id FROM laps WHERE session_id = ? ORDER BY lap_number",
                    (session_id,),
                ).fetchall()

            self.assertEqual(rows[0]["id"], first_lap_id)
            self.assertEqual(rows[0]["track_profile_id"], lap_profile_id)
            self.assertEqual(rows[1]["id"], second_lap_id)
            self.assertEqual(rows[1]["track_profile_id"], original_profile_id)

    def test_renaming_profile_changes_historical_display_by_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Auto Name", "Full", "manual", "user")
            session_id = store.create_session("Rename demo")
            lap_id = store.create_lap(
                session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            store.assign_track_profile(session_id, lap_id, profile_id)

            store.update_track_profile(profile_id, "User Corrected Name", "Sprint")

            with store.connect() as con:
                row = con.execute(
                    """
                    SELECT laps.track_profile_id, track_profiles.name, track_profiles.layout
                    FROM laps
                    JOIN track_profiles ON track_profiles.id = laps.track_profile_id
                    WHERE laps.id = ?
                    """,
                    (lap_id,),
                ).fetchone()

            self.assertEqual(row["track_profile_id"], profile_id)
            self.assertEqual(row["name"], "User Corrected Name")
            self.assertEqual(row["layout"], "Sprint")
            self.assertNotIn("name", _track_columns(store, "laps"))
            self.assertNotIn("layout", _track_columns(store, "laps"))

    def test_merge_track_profiles_moves_references_and_assets_then_deletes_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            keep_profile_id = store.create_track_profile("Keep", "Full", "manual", "user")
            merge_profile_id = store.create_track_profile("Merge", "Full", "manual", "user")
            session_id = store.create_session("Merge demo")
            lap_id = store.create_lap(
                session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            with store.connect() as con:
                con.execute(
                    "UPDATE sessions SET track_profile_id = ? WHERE id = ?",
                    (merge_profile_id, session_id),
                )
            store.assign_track_profile(session_id, lap_id, merge_profile_id)
            asset_id = store.create_track_asset(
                track_profile_id=merge_profile_id,
                filename="merge-map.png",
                stored_path=str(Path(tmp) / "merge-map.png"),
                mime_type="image/png",
                size_bytes=1024,
            )

            store.merge_track_profiles(keep_profile_id, merge_profile_id)

            with store.connect() as con:
                session_profile_id = con.execute(
                    "SELECT track_profile_id FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()["track_profile_id"]
                lap_profile_id = con.execute(
                    "SELECT track_profile_id FROM laps WHERE id = ?",
                    (lap_id,),
                ).fetchone()["track_profile_id"]
                asset_profile_id = con.execute(
                    "SELECT track_profile_id FROM track_assets WHERE id = ?",
                    (asset_id,),
                ).fetchone()["track_profile_id"]

            self.assertEqual(session_profile_id, keep_profile_id)
            self.assertEqual(lap_profile_id, keep_profile_id)
            self.assertEqual(asset_profile_id, keep_profile_id)
            self.assertIsNone(store.track_profile(merge_profile_id))

    def test_merge_track_profiles_rewrites_future_profile_reference_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            keep_profile_id = store.create_track_profile("Keep", "Full", "manual", "user")
            merge_profile_id = store.create_track_profile("Merge", "Full", "manual", "user")
            with store.connect() as con:
                con.execute(
                    """
                    CREATE TABLE profile_notes (
                        id TEXT PRIMARY KEY,
                        track_profile_id TEXT NOT NULL REFERENCES track_profiles(id),
                        body TEXT NOT NULL
                    )
                    """
                )
                con.execute(
                    """
                    INSERT INTO profile_notes(id, track_profile_id, body)
                    VALUES (?, ?, ?)
                    """,
                    ("note-1", merge_profile_id, "future table"),
                )

            store.merge_track_profiles(keep_profile_id, merge_profile_id)

            with store.connect() as con:
                note_profile_id = con.execute(
                    "SELECT track_profile_id FROM profile_notes WHERE id = ?",
                    ("note-1",),
                ).fetchone()["track_profile_id"]
            self.assertEqual(note_profile_id, keep_profile_id)
            self.assertIsNone(store.track_profile(merge_profile_id))

    def test_merge_track_profiles_works_without_track_assets_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            keep_profile_id = store.create_track_profile("Keep", "Full", "manual", "user")
            merge_profile_id = store.create_track_profile("Merge", "Full", "manual", "user")

            store.merge_track_profiles(keep_profile_id, merge_profile_id)

            self.assertIsNotNone(store.track_profile(keep_profile_id))
            self.assertIsNone(store.track_profile(merge_profile_id))

    def test_assign_track_profile_rejects_unknown_ids_without_partial_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Valid", "Full", "manual", "user")
            session_id = store.create_session("Validation demo")
            lap_id = store.create_lap(
                session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )

            with self.assertRaisesRegex(ValueError, "unknown track_profile_id"):
                store.assign_track_profile(session_id, None, "missing-profile")
            with self.assertRaisesRegex(ValueError, "unknown session_id"):
                store.assign_track_profile("missing-session", None, profile_id)
            with self.assertRaisesRegex(ValueError, "unknown lap_id"):
                store.assign_track_profile(session_id, "missing-lap", profile_id)

            with store.connect() as con:
                row = con.execute(
                    "SELECT track_profile_id FROM laps WHERE id = ?",
                    (lap_id,),
                ).fetchone()
            self.assertIsNone(row["track_profile_id"])


class TrackProfileSignatureTests(unittest.TestCase):
    def test_shape_signature_is_stable_for_equivalent_normalized_paths(self):
        base_signature = shape_signature(_oval_samples(), buckets=8)
        transformed_signature = shape_signature(
            _oval_samples(scale=3.5, offset_x=500.0, offset_z=-250.0, use_aliases=True),
            buckets=8,
        )

        self.assertIsNotNone(base_signature)
        self.assertEqual(base_signature, transformed_signature)

    def test_shape_signature_resamples_by_route_progress_not_sample_density(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            uniform_signature = shape_signature(_oval_samples(count=160), buckets=32)
            nonuniform_signature = shape_signature(_nonuniform_oval_samples(), buckets=32)
            profile_id = store.create_track_profile(
                "Emerald",
                "Full",
                "shape_match",
                "auto",
                shape_signature=uniform_signature,
            )

            distance = signature_distance(uniform_signature, nonuniform_signature)
            match = match_track_profile(
                store,
                _nonuniform_oval_samples(),
                max_distance=0.18,
            )

            self.assertLess(distance, 0.05)
            self.assertIsNotNone(match)
            self.assertEqual(match["id"], profile_id)

    def test_shape_signature_returns_none_for_low_sample_or_partial_lap_paths(self):
        cases = [
            _oval_samples(count=19),
            _half_lap_samples(),
            [{"x": float(index), "z": 0.0} for index in range(64)],
        ]

        for samples in cases:
            with self.subTest(sample_count=len(samples)):
                self.assertIsNone(shape_signature(samples, buckets=8))

    def test_signature_distance_returns_infinity_for_invalid_or_incompatible_signatures(self):
        signature = shape_signature(_oval_samples(), buckets=8)
        incompatible = shape_signature(_oval_samples(), buckets=16)

        self.assertEqual(signature_distance("not-a-signature", signature), math.inf)
        self.assertEqual(signature_distance(signature, incompatible), math.inf)
        self.assertEqual(signature_distance(None, signature), math.inf)
        self.assertEqual(signature_distance(123, signature), math.inf)

    def test_match_track_profile_returns_nearest_profile_or_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            signature = shape_signature(_oval_samples(), buckets=8)
            profile_id = store.create_track_profile(
                "Emerald",
                "Full",
                "shape_match",
                "auto",
                shape_signature=signature,
            )
            store.create_track_profile("Manual only", "Full", "manual", "user")

            match = match_track_profile(
                store,
                _oval_samples(scale=1.4, offset_x=123.0, offset_z=-456.0),
                max_distance=0.18,
            )
            miss = match_track_profile(store, _triangle_samples(), max_distance=0.18)

            self.assertIsNotNone(match)
            self.assertEqual(match["id"], profile_id)
            self.assertIn("match_confidence", match)
            self.assertGreater(match["match_confidence"], 0.9)
            self.assertIsNone(miss)

    def test_assign_best_track_profile_assigns_matched_lap(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            signature = shape_signature(_oval_samples(), buckets=8)
            profile_id = store.create_track_profile(
                "Emerald",
                "Full",
                "shape_match",
                "auto",
                shape_signature=signature,
            )
            session_id = store.create_session("Auto assign")
            lap_id = store.create_lap(
                session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )

            match = assign_best_track_profile(
                store,
                session_id,
                lap_id,
                _oval_samples(scale=2.0, offset_x=4.0, offset_z=9.0),
            )

            with store.connect() as con:
                assigned_profile_id = con.execute(
                    "SELECT track_profile_id FROM laps WHERE id = ?",
                    (lap_id,),
                ).fetchone()["track_profile_id"]
            self.assertIsNotNone(match)
            self.assertEqual(match["id"], profile_id)
            self.assertEqual(assigned_profile_id, profile_id)


if __name__ == "__main__":
    unittest.main()
