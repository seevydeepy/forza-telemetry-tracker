import copy
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from telemetry_tracker.app import create_app


DEFAULT_CONTEXTS = {
    "track": "emerald-circuit",
    "track_car": "emerald-circuit|2005-porsche-cayman-gt3",
    "track_car_build": "emerald-circuit|2005-porsche-cayman-gt3|wtac",
}


def _add_comparison_lap(
    store,
    *,
    label: str,
    lap_number: int,
    started_at_ms: int,
    ended_at_ms: int,
    lap_duration_ms: int,
    elapsed_scale: float = 1.0,
    speed_offset: float = 0.0,
    sample_count: int = 30,
    session_id: str | None = None,
    track_profile_id: str | None = None,
) -> str:
    created_session = session_id is None
    if session_id is None:
        session_id = store.create_session(label=label)
    lap_id = store.create_lap(
        session_id=session_id,
        lap_number=lap_number,
        boundary_confidence="game_field",
    )
    store.finalize_lap(lap_id, reason="lap_boundary")
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
            SET started_at_ms = ?, ended_at_ms = ?, status = ?, ended_reason = ?, track_profile_id = ?
            WHERE id = ?
            """,
            (started_at_ms, ended_at_ms, "lap_boundary", "lap_boundary", track_profile_id, lap_id),
        )
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
                    sequence,
                    sequence * 16,
                    sequence * 16,
                    lap_number,
                    sequence * elapsed_scale,
                    sequence * elapsed_scale,
                    float(sequence),
                    0.0,
                    0.0,
                    50.0 + speed_offset + sequence,
                    128,
                    0,
                    0,
                    4,
                )
                for sequence in range(1, sample_count + 1)
            ],
        )
    store.insert_lap_summary(
        lap_id,
        {
            "sample_count": sample_count,
            "packet_count": sample_count,
            "lap_duration_ms": lap_duration_ms,
            "lap_time_ms": lap_duration_ms,
            "uncertainty_count": 0,
            "top_speed_mps": 50.0 + speed_offset + sample_count,
            "comparison_contexts": DEFAULT_CONTEXTS,
        },
    )
    return lap_id


def _sample_count(store, lap_id: str) -> int:
    with store.connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS count FROM lap_samples WHERE lap_id = ?",
            (lap_id,),
        ).fetchone()
    return int(row["count"])


def _reference_pin_count(store, scope: str, context_key: str) -> int:
    with store.connect() as con:
        row = con.execute(
            """
            SELECT COUNT(*) AS count
            FROM comparison_refs
            WHERE scope = ? AND context_key = ?
            """,
            (scope, context_key),
        ).fetchone()
    return int(row["count"])


class TrackerComparisonApiTests(unittest.TestCase):
    def _app_with_laps(self):
        tmp = tempfile.TemporaryDirectory()
        app = create_app(db_path=Path(tmp.name) / "telemetry_tracker.sqlite3")
        store = app.state.store
        session_id = store.create_session(label="Shared test session")
        track_profile_id = store.create_track_profile(
            name="Emerald Circuit",
            layout="Full",
            source="test",
            confidence="user",
        )
        current_lap_id = _add_comparison_lap(
            store,
            label="Current lap",
            lap_number=10,
            started_at_ms=10_000,
            ended_at_ms=11_000,
            lap_duration_ms=60_000,
            elapsed_scale=1.0,
            speed_offset=0.0,
            session_id=session_id,
            track_profile_id=track_profile_id,
        )
        faster_lap_id = _add_comparison_lap(
            store,
            label="Faster reference",
            lap_number=1,
            started_at_ms=1_000,
            ended_at_ms=2_000,
            lap_duration_ms=55_000,
            elapsed_scale=0.9,
            speed_offset=5.0,
            session_id=session_id,
            track_profile_id=track_profile_id,
        )
        slower_lap_id = _add_comparison_lap(
            store,
            label="Slower lap",
            lap_number=2,
            started_at_ms=3_000,
            ended_at_ms=4_000,
            lap_duration_ms=65_000,
            elapsed_scale=1.1,
            speed_offset=-5.0,
            session_id=session_id,
            track_profile_id=track_profile_id,
        )
        return tmp, app, store, current_lap_id, faster_lap_id, slower_lap_id, track_profile_id

    def test_get_reference_returns_session_best_reference(self):
        tmp, app, _store, current_lap_id, faster_lap_id, _slower_lap_id, track_profile_id = self._app_with_laps()
        expected_context_key = f"{track_profile_id}|2005-porsche-cayman-gt3"
        with tmp:
            with TestClient(app) as client:
                response = client.get(f"/api/laps/{current_lap_id}/reference")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["lap_id"], current_lap_id)
            self.assertEqual(payload["scope"], "track_car")
            self.assertEqual(payload["context_key"], expected_context_key)
            self.assertEqual(payload["reference"]["lap_id"], faster_lap_id)
            self.assertEqual(payload["reference"]["source"], "session_best")

    def test_post_reference_returns_405(self):
        tmp, app, _store, current_lap_id, _faster_lap_id, slower_lap_id, _track_profile_id = self._app_with_laps()
        with tmp:
            with TestClient(app) as client:
                response = client.post(
                    f"/api/laps/{current_lap_id}/reference",
                    json={"reference_lap_id": slower_lap_id, "scope": "track_car"},
                )

            self.assertEqual(response.status_code, 405)

    def test_delete_reference_returns_405(self):
        tmp, app, _store, current_lap_id, _faster_lap_id, _slower_lap_id, _track_profile_id = self._app_with_laps()
        with tmp:
            with TestClient(app) as client:
                response = client.delete(f"/api/laps/{current_lap_id}/reference")

            self.assertEqual(response.status_code, 405)

    def test_get_reference_ignores_persisted_pins(self):
        tmp, app, store, current_lap_id, faster_lap_id, slower_lap_id, track_profile_id = self._app_with_laps()
        with tmp:
            context_key = f"{track_profile_id}|2005-porsche-cayman-gt3"
            store.pin_reference_lap("track_car", context_key, slower_lap_id)

            with TestClient(app) as client:
                response = client.get(f"/api/laps/{current_lap_id}/reference")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["reference"]["lap_id"], faster_lap_id)
            self.assertEqual(payload["reference"]["source"], "session_best")
            self.assertEqual(_reference_pin_count(store, "track_car", context_key), 1)

    def test_get_reference_returns_null_for_unassigned_track(self):
        tmp, app, store, current_lap_id, _faster_lap_id, _slower_lap_id, _track_profile_id = self._app_with_laps()
        with tmp:
            with store.connect() as con:
                con.execute("UPDATE laps SET track_profile_id = NULL WHERE id = ?", (current_lap_id,))

            with TestClient(app) as client:
                ref_response = client.get(f"/api/laps/{current_lap_id}/reference")
                ghost_response = client.get(f"/api/laps/{current_lap_id}/ghost")
                delta_response = client.get(f"/api/laps/{current_lap_id}/delta")

            self.assertEqual(ref_response.status_code, 200)
            self.assertIsNone(ref_response.json()["reference"])

            self.assertEqual(ghost_response.status_code, 200)
            self.assertIsNone(ghost_response.json()["reference"])
            self.assertEqual(ghost_response.json()["samples"], [])

            self.assertEqual(delta_response.status_code, 200)
            self.assertIsNone(delta_response.json()["reference"])
            self.assertEqual(delta_response.json()["summary"]["reference_sample_count"], 0)

    def test_get_reference_returns_self_when_current_lap_is_fastest(self):
        tmp, app, store, current_lap_id, _faster_lap_id, _slower_lap_id, _track_profile_id = self._app_with_laps()
        with tmp:
            store.insert_lap_summary(
                current_lap_id,
                {
                    "sample_count": 30,
                    "packet_count": 30,
                    "lap_duration_ms": 50,
                    "lap_time_ms": 50,
                    "uncertainty_count": 0,
                    "top_speed_mps": 80.0,
                    "comparison_contexts": DEFAULT_CONTEXTS,
                },
            )

            with TestClient(app) as client:
                ref_response = client.get(f"/api/laps/{current_lap_id}/reference")
                delta_response = client.get(f"/api/laps/{current_lap_id}/delta")

            self.assertEqual(ref_response.status_code, 200)
            self.assertEqual(ref_response.json()["reference"]["lap_id"], current_lap_id)
            self.assertEqual(ref_response.json()["reference"]["source"], "session_best")

            self.assertEqual(delta_response.status_code, 200)
            self.assertEqual(delta_response.json()["reference"]["lap_id"], current_lap_id)
            self.assertAlmostEqual(delta_response.json()["summary"]["time_delta_ms"], 0.0)

    def test_get_ghost_returns_reference_samples(self):
        tmp, app, _store, current_lap_id, faster_lap_id, _slower_lap_id, track_profile_id = self._app_with_laps()
        expected_context_key = f"{track_profile_id}|2005-porsche-cayman-gt3"
        with tmp:
            with TestClient(app) as client:
                response = client.get(f"/api/laps/{current_lap_id}/ghost")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["lap_id"], current_lap_id)
            self.assertEqual(payload["scope"], "track_car")
            self.assertEqual(payload["context_key"], expected_context_key)
            self.assertEqual(payload["reference"]["lap_id"], faster_lap_id)
            self.assertEqual(len(payload["samples"]), 30)
            self.assertEqual(payload["samples"][0]["sequence"], 1)
            self.assertAlmostEqual(payload["samples"][0]["lap_progress"], 0.0)
            self.assertAlmostEqual(payload["samples"][-1]["lap_progress"], 1.0)

    def test_get_delta_returns_full_lap_delta(self):
        tmp, app, _store, current_lap_id, faster_lap_id, _slower_lap_id, _track_profile_id = self._app_with_laps()
        with tmp:
            with TestClient(app) as client:
                response = client.get(f"/api/laps/{current_lap_id}/delta")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["lap_id"], current_lap_id)
            self.assertEqual(payload["scope"], "track_car")
            self.assertEqual(payload["reference"]["lap_id"], faster_lap_id)
            summary = payload["summary"]
            self.assertEqual(summary["start_sequence"], 1)
            self.assertEqual(summary["end_sequence"], 30)
            self.assertEqual(summary["sample_count"], 30)
            self.assertEqual(len(summary["points"]), 30)
            self.assertAlmostEqual(summary["time_delta_ms"], 2_900.0)
            self.assertAlmostEqual(summary["average_speed_delta_mps"], -5.0)

    def test_get_delta_returns_section_delta_for_sequence_range(self):
        tmp, app, _store, current_lap_id, faster_lap_id, _slower_lap_id, _track_profile_id = self._app_with_laps()
        with tmp:
            with TestClient(app) as client:
                response = client.get(
                    f"/api/laps/{current_lap_id}/delta?start_sequence=10&end_sequence=20"
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["lap_id"], current_lap_id)
            self.assertEqual(payload["reference"]["lap_id"], faster_lap_id)
            summary = payload["summary"]
            self.assertEqual(summary["start_sequence"], 10)
            self.assertEqual(summary["end_sequence"], 20)
            self.assertEqual(summary["sample_count"], 11)
            self.assertEqual([point["sequence"] for point in summary["points"]], list(range(10, 21)))
            self.assertAlmostEqual(summary["time_delta_ms"], 1_000.0)

    def test_comparison_routes_validate_scope_and_lap_ids(self):
        tmp, app, _store, current_lap_id, _faster_lap_id, _slower_lap_id, _track_profile_id = self._app_with_laps()
        with tmp:
            with TestClient(app) as client:
                bad_scope = client.get(f"/api/laps/{current_lap_id}/reference?scope=garage")
                bad_ghost_scope = client.get(f"/api/laps/{current_lap_id}/ghost?scope=garage")
                bad_delta_scope = client.get(f"/api/laps/{current_lap_id}/delta?scope=garage")
                missing_current = client.get("/api/laps/missing/reference")
                bad_delta_range = client.get(
                    f"/api/laps/{current_lap_id}/delta?start_sequence=20&end_sequence=10"
                )

            self.assertEqual(bad_scope.status_code, 400)
            self.assertIn("unsupported reference scope", bad_scope.json()["detail"])
            self.assertEqual(bad_ghost_scope.status_code, 400)
            self.assertEqual(bad_delta_scope.status_code, 400)
            self.assertEqual(missing_current.status_code, 404)
            self.assertEqual(bad_delta_range.status_code, 400)

    def test_comparison_routes_do_not_mutate_lap_samples(self):
        tmp, app, store, current_lap_id, faster_lap_id, slower_lap_id, _track_profile_id = self._app_with_laps()
        with tmp:
            current_samples_before = copy.deepcopy(store.samples_for_lap(current_lap_id))
            faster_samples_before = copy.deepcopy(store.samples_for_lap(faster_lap_id))
            slower_samples_before = copy.deepcopy(store.samples_for_lap(slower_lap_id))
            current_count_before = _sample_count(store, current_lap_id)
            faster_count_before = _sample_count(store, faster_lap_id)
            slower_count_before = _sample_count(store, slower_lap_id)

            with TestClient(app) as client:
                responses = [
                    client.get(f"/api/laps/{current_lap_id}/reference"),
                    client.get(f"/api/laps/{current_lap_id}/ghost"),
                    client.get(f"/api/laps/{current_lap_id}/delta"),
                ]

            self.assertEqual([response.status_code for response in responses], [200] * 3)
            self.assertEqual(store.samples_for_lap(current_lap_id), current_samples_before)
            self.assertEqual(store.samples_for_lap(faster_lap_id), faster_samples_before)
            self.assertEqual(store.samples_for_lap(slower_lap_id), slower_samples_before)
            self.assertEqual(_sample_count(store, current_lap_id), current_count_before)
            self.assertEqual(_sample_count(store, faster_lap_id), faster_count_before)
            self.assertEqual(_sample_count(store, slower_lap_id), slower_count_before)


if __name__ == "__main__":
    unittest.main()
