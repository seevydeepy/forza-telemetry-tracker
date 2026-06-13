import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from telemetry_tracker import __version__
from telemetry_tracker.app import create_app
from telemetry_tracker.diagnostics import diagnostics_payload
from telemetry_tracker.storage import LOCAL_USER_ID, TelemetryStore


def _store_for_tmp(tmp: str) -> tuple[TelemetryStore, Path]:
    db_path = Path(tmp) / "telemetry_tracker.sqlite3"
    store = TelemetryStore(db_path)
    store.migrate()
    return store, db_path


def _seed_diagnostic_rows(store: TelemetryStore) -> tuple[str, str, str]:
    session_id = store.create_session(label="Diagnostics session")
    lap_id = store.create_lap(
        session_id=session_id,
        lap_number=1,
        boundary_confidence="game_field",
    )
    profile_id = store.create_track_profile(
        name="Emerald Circuit",
        layout="Full",
        source="manual",
        confidence="user",
    )
    store.insert_issue_markers(
        [
            {
                "id": "diagnostic-marker",
                "session_id": session_id,
                "lap_id": lap_id,
                "start_sequence": 1,
                "end_sequence": 2,
                "metric": "combined_slip",
                "severity": "warning",
                "reason": "High slip",
                "ruleset_version": 1,
                "confidence": 0.9,
            }
        ]
    )
    with store.connect() as con:
        con.executemany(
            """
            INSERT INTO packet_blobs(
                session_id, lap_id, sequence, received_at_ms, game_timestamp_ms,
                lap_number, position_x, position_y, position_z, speed_mps, raw_packet
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    session_id,
                    lap_id,
                    sequence,
                    1_000 + sequence,
                    2_000 + sequence,
                    1,
                    float(sequence),
                    0.0,
                    float(sequence) * 2.0,
                    30.0 + sequence,
                    b"raw-packet-payload-" + bytes([sequence]),
                )
                for sequence in (1, 2, 3)
            ],
        )
    return session_id, lap_id, profile_id


def _table_count(store: TelemetryStore, table_name: str) -> int:
    with store.connect() as con:
        return int(con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


class _TrackingConnection:
    def __init__(self, connection, queries: list[str]):
        self._connection = connection
        self._queries = queries

    def execute(self, sql: str, parameters=()):
        self._queries.append(str(sql))
        lowered = str(sql).lower()
        if "packet_blobs" in lowered and (
            "raw_packet" in lowered or "select *" in lowered
        ):
            raise AssertionError("diagnostics must not select packet blob payload data")
        return self._connection.execute(sql, parameters)

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._connection.__exit__(exc_type, exc_value, traceback)

    def __getattr__(self, name: str):
        return getattr(self._connection, name)


class TrackerDiagnosticsTests(unittest.TestCase):
    def test_payload_reports_database_file_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, db_path = _store_for_tmp(tmp)

            payload = diagnostics_payload(store, app_version="test-version")

            self.assertEqual(payload["database_path"], db_path.name)
            self.assertNotIn(str(db_path.parent), payload["database_path"])
            self.assertEqual(payload["database_size_bytes"], db_path.stat().st_size)

    def test_payload_reports_wal_file_size_when_wal_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, db_path = _store_for_tmp(tmp)
            live_connection = store.connect()
            try:
                live_connection.execute("PRAGMA journal_mode=WAL")
                live_connection.execute(
                    "CREATE TABLE IF NOT EXISTS wal_probe(id INTEGER PRIMARY KEY, value TEXT)"
                )
                live_connection.execute(
                    "INSERT INTO wal_probe(value) VALUES (?)",
                    ("x" * 2048,),
                )
                live_connection.commit()
                wal_path = Path(str(db_path) + "-wal")
                self.assertTrue(wal_path.exists(), "test setup did not create a WAL file")

                payload = diagnostics_payload(store, app_version="test-version")

                self.assertEqual(payload["wal_size_bytes"], wal_path.stat().st_size)
            finally:
                live_connection.close()

    def test_payload_reports_row_counts_and_latest_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, _ = _store_for_tmp(tmp)
            _seed_diagnostic_rows(store)
            listener_status = {
                "state": "receiving",
                "udp_host": "127.0.0.1",
                "udp_port": 5400,
                "message": "receiving UDP telemetry",
            }
            capture_status = {
                "mode": "manual",
                "phase": "recording",
                "recording": {"active": True},
            }

            payload = diagnostics_payload(
                store,
                app_version="test-version",
                listener_status=listener_status,
                capture_status=capture_status,
            )

            self.assertEqual(
                payload["row_counts"],
                {
                    "sessions": 1,
                    "laps": 1,
                    "packets": 3,
                    "issue_markers": 1,
                    "track_profiles": 1,
                    "world_map_tile_sets": 0,
                },
            )
            self.assertEqual(payload["world_map"]["tile_set_count"], 0)
            self.assertEqual(payload["listener_status"], listener_status)
            self.assertEqual(payload["capture_status"], capture_status)
            self.assertEqual(payload["app_version"], "test-version")
            self.assertEqual(payload["recent_errors"], [])

    def test_api_diagnostics_returns_database_metadata_counts_version_and_recent_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "telemetry_tracker.sqlite3"
            app = create_app(db_path=db_path)
            _seed_diagnostic_rows(app.state.store)

            with TestClient(app) as client:
                response = client.get("/api/diagnostics")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["database_path"], db_path.name)
            self.assertNotIn(str(db_path.parent), payload["database_path"])
            self.assertEqual(payload["database_size_bytes"], db_path.stat().st_size)
            self.assertEqual(
                payload["row_counts"],
                {
                    "sessions": 1,
                    "laps": 1,
                    "packets": 3,
                    "issue_markers": 1,
                    "track_profiles": 1,
                    "world_map_tile_sets": 0,
                },
            )
            self.assertEqual(payload["world_map"]["tile_set_count"], 0)
            self.assertEqual(payload["app_version"], __version__)
            self.assertEqual(payload["recent_errors"], [])
            self.assertEqual(payload["listener_status"]["state"], "waiting")
            self.assertEqual(payload["capture_status"]["mode"], "auto")

    def test_delete_all_telemetry_endpoint_clears_recorded_rows_and_preserves_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "telemetry_tracker.sqlite3"
            app = create_app(db_path=db_path)
            store = app.state.store
            session_id, lap_id, profile_id = _seed_diagnostic_rows(store)
            with store.connect() as con:
                con.execute(
                    """
                    INSERT INTO lap_samples(
                        session_id, lap_id, sequence, received_at_ms, game_timestamp_ms,
                        lap_number, current_lap, current_race_time, x, y, z, speed_mps,
                        throttle, brake, steer, gear
                    )
                    VALUES (?, ?, 1, 1000, 2000, 1, 12.3, 12.3, 1.0, 0.0, 2.0, 44.0, 100, 0, 0, 3)
                    """,
                    (session_id, lap_id),
                )
                con.execute(
                    """
                    INSERT INTO lap_summaries(lap_id, summary_json, created_at_ms, updated_at_ms)
                    VALUES (?, '{}', 3000, 3000)
                    """,
                    (lap_id,),
                )
                con.execute(
                    """
                    INSERT INTO comparison_refs(user_id, scope, context_key, lap_id, pinned_at_ms)
                    VALUES (?, 'track', ?, ?, 3000)
                    """,
                    (LOCAL_USER_ID, profile_id, lap_id),
                )
                con.execute(
                    """
                    INSERT INTO track_match_candidates(
                        lap_id, session_id, matcher_version, candidate_rank, candidate_kind,
                        track_profile_id, confidence, score_components_json, reasons_json,
                        is_auto_assignable, assigned_track_profile_id, created_at_ms
                    )
                    VALUES (?, ?, 'test', 1, 'profile', ?, 0.95, '{}', '[]', 1, ?, 3000)
                    """,
                    (lap_id, session_id, profile_id, profile_id),
                )
                con.execute(
                    """
                    INSERT INTO lifetime_stat_laps(
                        lap_id, user_id, session_id, recorded_at_ms, lap_time_ms,
                        max_speed_mps, track_profile_id, track_name, track_layout,
                        created_at_ms, updated_at_ms
                    )
                    VALUES (?, ?, ?, 3000, 12345, 44.0, ?, 'Emerald Circuit', 'Full', 3000, 3000)
                    """,
                    (lap_id, LOCAL_USER_ID, session_id, profile_id),
                )
                con.execute(
                    """
                    INSERT OR REPLACE INTO session_counters(user_id, next_session_number)
                    VALUES (?, 12)
                    """,
                    (LOCAL_USER_ID,),
                )

            with TestClient(app) as client:
                deleted = client.delete("/api/telemetry/delete-all")
                diagnostics = client.get("/api/diagnostics")

            self.assertEqual(deleted.status_code, 200)
            payload = deleted.json()
            self.assertTrue(payload["deleted"])
            self.assertEqual(payload["deleted_counts"]["sessions"], 1)
            self.assertEqual(payload["deleted_counts"]["laps"], 1)
            self.assertEqual(payload["deleted_counts"]["packet_blobs"], 3)
            self.assertEqual(payload["deleted_counts"]["lap_samples"], 1)
            self.assertEqual(payload["deleted_counts"]["lifetime_stat_laps"], 1)
            self.assertEqual(
                payload["row_counts"],
                {
                    "sessions": 0,
                    "laps": 0,
                    "packets": 0,
                    "issue_markers": 0,
                    "track_profiles": 1,
                    "world_map_tile_sets": 0,
                },
            )
            self.assertEqual(diagnostics.status_code, 200)
            self.assertEqual(diagnostics.json()["row_counts"], payload["row_counts"])
            for table_name in (
                "sessions",
                "laps",
                "packet_blobs",
                "lap_samples",
                "issue_markers",
                "lap_summaries",
                "comparison_refs",
                "track_match_candidates",
                "lifetime_stat_laps",
                "session_counters",
            ):
                self.assertEqual(_table_count(store, table_name), 0, table_name)
            self.assertEqual(_table_count(store, "track_profiles"), 1)
            self.assertIsNotNone(store.track_profile(profile_id))

    def test_row_counts_use_count_queries_without_loading_packet_blob_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, _ = _store_for_tmp(tmp)
            _seed_diagnostic_rows(store)
            original_connect = store.connect
            queries: list[str] = []

            def tracking_connect():
                return _TrackingConnection(original_connect(), queries)

            store.connect = tracking_connect  # type: ignore[method-assign]

            payload = diagnostics_payload(store, app_version="test-version")

            self.assertEqual(payload["row_counts"]["packets"], 3)
            packet_queries = [
                query for query in queries if "packet_blobs" in query.lower()
            ]
            self.assertEqual(len(packet_queries), 1)
            self.assertIn("count(*)", packet_queries[0].lower())
            self.assertNotIn("raw_packet", "\n".join(queries).lower())


if __name__ == "__main__":
    unittest.main()
