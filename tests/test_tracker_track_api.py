import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from telemetry_tracker.app import create_app


def _client_and_store(tmp: str):
    app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
    return TestClient(app), app.state.store


def _table_columns(store, table_name: str) -> set[str]:
    with store.connect() as con:
        return {
            row["name"]
            for row in con.execute(f"PRAGMA table_info({table_name})").fetchall()
        }


def _seed_completed_reference_lap(
    store,
    *,
    label: str,
    lap_number: int,
    started_at_ms: int,
    ended_at_ms: int,
    lap_duration_ms: int,
    comparison_context: str,
    car_context: str = "test-car",
    build_context: str = "test-build",
    session_id: str | None = None,
) -> tuple[str, str]:
    created_session = session_id is None
    if session_id is None:
        session_id = store.create_session(label)
    lap_id = store.create_lap(
        session_id,
        lap_number=lap_number,
        boundary_confidence="game_field",
    )
    store.finalize_lap(
        lap_id,
        reason="lap_boundary",
        boundary_confidence="game_field",
    )
    summary = {
        "sample_count": 2,
        "packet_count": 2,
        "lap_time_ms": lap_duration_ms,
        "lap_duration_ms": lap_duration_ms,
        "uncertainty_count": 0,
        "comparison_contexts": {
            "track": comparison_context,
            "track_car": f"{comparison_context}|{car_context}",
            "track_car_build": f"{comparison_context}|{car_context}|{build_context}",
        },
    }
    with store.connect() as con:
        if created_session:
            con.execute(
                """
                UPDATE sessions
                SET started_at_ms = ?, ended_at_ms = ?, status = ?, ended_reason = ?
                WHERE id = ?
                """,
                (
                    started_at_ms - 100,
                    ended_at_ms + 100,
                    "lap_boundary",
                    "lap_boundary",
                    session_id,
                ),
            )
        else:
            con.execute(
                """
                UPDATE sessions
                SET started_at_ms = MIN(COALESCE(started_at_ms, ?), ?),
                    ended_at_ms = MAX(COALESCE(ended_at_ms, ?), ?),
                    status = ?,
                    ended_reason = ?
                WHERE id = ?
                """,
                (
                    started_at_ms - 100,
                    started_at_ms - 100,
                    ended_at_ms + 100,
                    ended_at_ms + 100,
                    "lap_boundary",
                    "lap_boundary",
                    session_id,
                ),
            )
        con.execute(
            """
            UPDATE laps
            SET started_at_ms = ?, ended_at_ms = ?, status = ?, ended_reason = ?,
                boundary_confidence = ?
            WHERE id = ?
            """,
            (
                started_at_ms,
                ended_at_ms,
                "lap_boundary",
                "lap_boundary",
                "game_field",
                lap_id,
            ),
        )
        con.executemany(
            """
            INSERT INTO lap_samples(
                session_id, lap_id, sequence, received_at_ms, game_timestamp_ms,
                lap_number, current_lap, current_race_time, x, y, z, speed_mps,
                throttle, brake, steer, gear
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    session_id,
                    lap_id,
                    sequence,
                    started_at_ms + sequence,
                    started_at_ms + sequence,
                    lap_number,
                    float(sequence - 1),
                    float(sequence - 1),
                    float(sequence - 1),
                    0.0,
                    0.0,
                    40.0 + sequence,
                    255,
                    0,
                    0,
                    3,
                )
                for sequence in (1, 2)
            ],
        )
        con.execute(
            """
            INSERT INTO lap_summaries(lap_id, summary_json, created_at_ms, updated_at_ms)
            VALUES (?, ?, ?, ?)
            """,
            (
                lap_id,
                json.dumps(summary, sort_keys=True, separators=(",", ":")),
                ended_at_ms,
                ended_at_ms,
            ),
        )
    return session_id, lap_id


class TrackProfileApiTests(unittest.TestCase):
    def test_get_profiles_sorts_by_updated_time_descending(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            older_id = store.create_track_profile("B Track", "Full", "manual", "user")
            newer_id = store.create_track_profile("A Track", "Full", "manual", "user")
            tied_id = store.create_track_profile("C Track", "Full", "manual", "user")
            with store.connect() as con:
                con.execute(
                    "UPDATE track_profiles SET updated_at_ms = ? WHERE id = ?",
                    (1_000, older_id),
                )
                con.execute(
                    "UPDATE track_profiles SET updated_at_ms = ? WHERE id = ?",
                    (2_000, newer_id),
                )
                con.execute(
                    "UPDATE track_profiles SET updated_at_ms = ? WHERE id = ?",
                    (2_000, tied_id),
                )

            with client:
                response = client.get("/api/tracks/profiles")

            self.assertEqual(response.status_code, 200)
            profiles = response.json()["profiles"]
            self.assertEqual(
                [profile["id"] for profile in profiles],
                [newer_id, tied_id, older_id],
            )

    def test_get_profiles_backfills_catalog_tracks_as_selectable_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            store.upsert_track_catalog_records(
                [
                    {
                        "track_key": "track-info:161",
                        "source_dataset_key": 161,
                        "route_id": 161,
                        "media_track_name": "Brio",
                        "ribbon_config": "Circuit",
                        "display_name": "Shirakawa Circuit",
                        "catalog_source": "test",
                    }
                ]
            )

            with client:
                response = client.get("/api/tracks/profiles")

            self.assertEqual(response.status_code, 200)
            profiles = response.json()["profiles"]
            self.assertEqual(len(profiles), 1)
            self.assertEqual(profiles[0]["name"], "Shirakawa Circuit")
            self.assertEqual(profiles[0]["layout"], "Circuit")
            self.assertEqual(profiles[0]["source"], "fh6_catalog_match")

    def test_post_creates_profile_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = _client_and_store(tmp)

            with client:
                response = client.post(
                    "/api/tracks/profiles",
                    json={"name": "Emerald Circuit", "layout": "Full"},
                )

            self.assertEqual(response.status_code, 200)
            profile = response.json()["profile"]
            self.assertEqual(profile["name"], "Emerald Circuit")
            self.assertEqual(profile["layout"], "Full")
            self.assertEqual(profile["source"], "manual")
            self.assertEqual(profile["confidence"], "user")
            self.assertTrue(profile["id"])

    def test_patch_renames_profile_and_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            profile_id = store.create_track_profile("Auto Name", "Full", "manual", "user")

            with client:
                response = client.patch(
                    f"/api/tracks/profiles/{profile_id}",
                    json={"name": "Corrected Name", "layout": "Sprint"},
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["profile"]["id"], profile_id)
            self.assertEqual(response.json()["profile"]["name"], "Corrected Name")
            self.assertEqual(response.json()["profile"]["layout"], "Sprint")

    def test_post_assign_requires_lap_id_and_updates_selected_lap_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            profile_id = store.create_track_profile("Lap Track", "Alt", "manual", "user")
            session_id = store.create_session("Assignment demo")
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

            with client:
                missing_lap_response = client.post(
                    f"/api/tracks/profiles/{profile_id}/assign",
                    json={"sessionId": session_id},
                )
                lap_response = client.post(
                    f"/api/tracks/profiles/{profile_id}/assign",
                    json={"session_id": session_id, "lap_id": first_lap_id},
                )

            self.assertEqual(missing_lap_response.status_code, 400)
            self.assertEqual(
                missing_lap_response.json()["detail"],
                "lap_id is required for track profile assignment",
            )
            self.assertEqual(lap_response.status_code, 200)
            self.assertEqual(
                lap_response.json()["assignment"],
                {
                    "profile_id": profile_id,
                    "session_id": session_id,
                    "lap_id": first_lap_id,
                },
            )
            self.assertEqual(store.lap(first_lap_id)["track_profile_id"], profile_id)
            self.assertIsNone(store.lap(second_lap_id)["track_profile_id"])

    def test_post_merge_merges_duplicates_and_rejects_same_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            keep_id = store.create_track_profile("Keep", "Full", "manual", "user")
            merge_id = store.create_track_profile("Duplicate", "Full", "manual", "user")
            session_id = store.create_session("Merge API")
            lap_id = store.create_lap(
                session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            store.assign_track_profile(session_id, lap_id, merge_id)

            with client:
                same_response = client.post(
                    "/api/tracks/profiles/merge",
                    json={"keepProfileId": keep_id, "mergeProfileId": keep_id},
                )
                merge_response = client.post(
                    "/api/tracks/profiles/merge",
                    json={"keep_profile_id": keep_id, "merge_profile_id": merge_id},
                )

            self.assertEqual(same_response.status_code, 400)
            self.assertEqual(merge_response.status_code, 200)
            self.assertEqual(merge_response.json()["profile"]["id"], keep_id)
            self.assertEqual(merge_response.json()["merged_profile_id"], merge_id)
            self.assertIsNone(store.track_profile(merge_id))
            self.assertEqual(store.latest_laps(limit=1)[0]["track_profile_id"], keep_id)

    def test_unknown_profile_ids_return_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            known_id = store.create_track_profile("Known", "Full", "manual", "user")
            session_id = store.create_session("Unknown IDs")

            with client:
                patch_response = client.patch(
                    "/api/tracks/profiles/missing-profile",
                    json={"name": "Missing", "layout": "Full"},
                )
                assign_response = client.post(
                    "/api/tracks/profiles/missing-profile/assign",
                    json={"session_id": session_id},
                )
                merge_response = client.post(
                    "/api/tracks/profiles/merge",
                    json={
                        "keep_profile_id": known_id,
                        "merge_profile_id": "missing-profile",
                    },
                )

            self.assertEqual(patch_response.status_code, 404)
            self.assertEqual(assign_response.status_code, 404)
            self.assertEqual(merge_response.status_code, 404)

    def test_assign_unknown_session_or_lap_ids_return_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            profile_id = store.create_track_profile("Known", "Full", "manual", "user")
            session_id = store.create_session("Assignment errors")

            with client:
                unknown_session = client.post(
                    f"/api/tracks/profiles/{profile_id}/assign",
                    json={"session_id": "missing-session", "lap_id": "missing-lap"},
                )
                unknown_lap = client.post(
                    f"/api/tracks/profiles/{profile_id}/assign",
                    json={"session_id": session_id, "lap_id": "missing-lap"},
                )

            self.assertEqual(unknown_session.status_code, 404)
            self.assertEqual(unknown_session.json()["detail"], "unknown session_id")
            self.assertEqual(unknown_lap.status_code, 404)
            self.assertEqual(unknown_lap.json()["detail"], "unknown lap_id")

    def test_assignment_updates_references_not_duplicated_track_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            profile_id = store.create_track_profile("Original", "Full", "manual", "user")
            session_id = store.create_session("Reference labels")
            lap_id = store.create_lap(
                session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )

            with client:
                assign = client.post(
                    f"/api/tracks/profiles/{profile_id}/assign",
                    json={"session_id": session_id, "lap_id": lap_id},
                )
                rename = client.patch(
                    f"/api/tracks/profiles/{profile_id}",
                    json={"name": "Renamed By Reference", "layout": "Sprint"},
                )
                laps = client.get("/api/laps").json()["laps"]

            self.assertEqual(assign.status_code, 200)
            self.assertEqual(rename.status_code, 200)
            self.assertEqual(laps[0]["track_profile_id"], profile_id)
            self.assertEqual(laps[0]["track_profile_name"], "Renamed By Reference")
            self.assertEqual(laps[0]["track_profile_layout"], "Sprint")
            self.assertNotIn("track_name", _table_columns(store, "laps"))
            self.assertNotIn("track_layout", _table_columns(store, "laps"))

    def test_assignment_refreshes_reference_context_from_current_track_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            profile_id = store.create_track_profile("Corrected", "Full", "manual", "user")
            session_id = store.create_session("Reference context")
            first_session_id, first_lap_id = _seed_completed_reference_lap(
                store,
                label="Stale track one",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                comparison_context="stale-track-one",
                session_id=session_id,
            )
            second_session_id, second_lap_id = _seed_completed_reference_lap(
                store,
                label="Stale track two",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=59_000,
                comparison_context="stale-track-two",
                session_id=session_id,
            )

            with client:
                first_assign = client.post(
                    f"/api/tracks/profiles/{profile_id}/assign",
                    json={"session_id": first_session_id, "lap_id": first_lap_id},
                )
                second_assign = client.post(
                    f"/api/tracks/profiles/{profile_id}/assign",
                    json={"session_id": second_session_id, "lap_id": second_lap_id},
                )
                reference = client.get(
                    f"/api/laps/{first_lap_id}/reference",
                    params={"scope": "track"},
                )

            self.assertEqual(first_assign.status_code, 200)
            self.assertEqual(second_assign.status_code, 200)
            self.assertEqual(reference.status_code, 200)
            payload = reference.json()
            self.assertEqual(payload["context_key"], profile_id)
            self.assertIsNotNone(payload["reference"])
            self.assertEqual(payload["reference"]["lap_id"], second_lap_id)
            self.assertEqual(payload["reference"]["context_key"], profile_id)

    def test_assignment_reference_context_preserves_summary_car_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            profile_id = store.create_track_profile("Corrected", "Full", "manual", "user")
            session_id = store.create_session("Reference car context")
            current_session_id, current_lap_id = _seed_completed_reference_lap(
                store,
                label="Current corrected car",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                comparison_context="old-current-track",
                car_context="car-a",
                session_id=session_id,
            )
            wrong_car_session_id, wrong_car_lap_id = _seed_completed_reference_lap(
                store,
                label="Wrong car corrected track",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=58_000,
                comparison_context="old-wrong-track",
                car_context="car-b",
                session_id=session_id,
            )
            same_car_session_id, same_car_lap_id = _seed_completed_reference_lap(
                store,
                label="Same car corrected track",
                lap_number=3,
                started_at_ms=5_000,
                ended_at_ms=6_000,
                lap_duration_ms=59_000,
                comparison_context="old-same-track",
                car_context="car-a",
                session_id=session_id,
            )

            with client:
                for session_id, lap_id in (
                    (current_session_id, current_lap_id),
                    (wrong_car_session_id, wrong_car_lap_id),
                    (same_car_session_id, same_car_lap_id),
                ):
                    response = client.post(
                        f"/api/tracks/profiles/{profile_id}/assign",
                        json={"session_id": session_id, "lap_id": lap_id},
                    )
                    self.assertEqual(response.status_code, 200)
                reference = client.get(
                    f"/api/laps/{current_lap_id}/reference",
                    params={"scope": "track_car"},
                )

            self.assertEqual(reference.status_code, 200)
            payload = reference.json()
            self.assertEqual(payload["context_key"], f"{profile_id}|car-a")
            self.assertIsNotNone(payload["reference"])
            self.assertEqual(payload["reference"]["lap_id"], same_car_lap_id)
            self.assertNotEqual(payload["reference"]["lap_id"], wrong_car_lap_id)
            self.assertEqual(payload["reference"]["context_key"], f"{profile_id}|car-a")

    def test_assignment_reference_context_preserves_summary_build_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            profile_id = store.create_track_profile("Corrected", "Full", "manual", "user")
            session_id = store.create_session("Reference build context")
            current_session_id, current_lap_id = _seed_completed_reference_lap(
                store,
                label="Current corrected build",
                lap_number=1,
                started_at_ms=1_000,
                ended_at_ms=2_000,
                lap_duration_ms=60_000,
                comparison_context="old-current-track",
                car_context="car-a",
                build_context="build-x",
                session_id=session_id,
            )
            wrong_build_session_id, wrong_build_lap_id = _seed_completed_reference_lap(
                store,
                label="Wrong build corrected track",
                lap_number=2,
                started_at_ms=3_000,
                ended_at_ms=4_000,
                lap_duration_ms=58_000,
                comparison_context="old-wrong-track",
                car_context="car-a",
                build_context="build-y",
                session_id=session_id,
            )
            same_build_session_id, same_build_lap_id = _seed_completed_reference_lap(
                store,
                label="Same build corrected track",
                lap_number=3,
                started_at_ms=5_000,
                ended_at_ms=6_000,
                lap_duration_ms=59_000,
                comparison_context="old-same-track",
                car_context="car-a",
                build_context="build-x",
                session_id=session_id,
            )

            with client:
                for session_id, lap_id in (
                    (current_session_id, current_lap_id),
                    (wrong_build_session_id, wrong_build_lap_id),
                    (same_build_session_id, same_build_lap_id),
                ):
                    response = client.post(
                        f"/api/tracks/profiles/{profile_id}/assign",
                        json={"session_id": session_id, "lap_id": lap_id},
                    )
                    self.assertEqual(response.status_code, 200)
                reference = client.get(
                    f"/api/laps/{current_lap_id}/reference",
                    params={"scope": "track_car_build"},
                )

            self.assertEqual(reference.status_code, 200)
            payload = reference.json()
            self.assertEqual(payload["context_key"], f"{profile_id}|car-a|build-x")
            self.assertIsNotNone(payload["reference"])
            self.assertEqual(payload["reference"]["lap_id"], same_build_lap_id)
            self.assertNotEqual(payload["reference"]["lap_id"], wrong_build_lap_id)
            self.assertEqual(
                payload["reference"]["context_key"],
                f"{profile_id}|car-a|build-x",
            )


if __name__ == "__main__":
    unittest.main()
