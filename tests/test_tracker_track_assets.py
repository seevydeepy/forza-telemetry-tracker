import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from telemetry_tracker.app import create_app
from telemetry_tracker.storage import TelemetryStore
from telemetry_tracker.track_assets import ALLOWED_MIME_TYPES, MAX_ASSET_BYTES, default_transform, validate_asset


def _store_in(tmp: str) -> TelemetryStore:
    store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
    store.migrate()
    return store


def _track_asset_columns(store: TelemetryStore) -> set[str]:
    with store.connect() as con:
        return {row["name"] for row in con.execute("PRAGMA table_info(track_assets)").fetchall()}


def _client_and_store(tmp: str):
    app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
    return TestClient(app), app.state.store


class TrackAssetStorageTests(unittest.TestCase):
    def test_migration_creates_track_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)

            self.assertEqual(
                _track_asset_columns(store),
                {
                    "id",
                    "track_profile_id",
                    "filename",
                    "stored_path",
                    "mime_type",
                    "size_bytes",
                    "transform_json",
                    "created_at_ms",
                    "updated_at_ms",
                },
            )
            with store.connect() as con:
                foreign_keys = {
                    (row["from"], row["table"], row["to"], row["on_delete"])
                    for row in con.execute("PRAGMA foreign_key_list(track_assets)").fetchall()
                }
            self.assertIn(
                ("track_profile_id", "track_profiles", "id", "CASCADE"),
                foreign_keys,
            )

    def test_allowed_mime_types_are_png_jpeg_webp_and_svg(self):
        self.assertEqual(
            ALLOWED_MIME_TYPES,
            {"image/png", "image/jpeg", "image/webp", "image/svg+xml"},
        )
        for mime_type in ALLOWED_MIME_TYPES:
            validate_asset("track-art", mime_type, 1024)
        with self.assertRaisesRegex(ValueError, "unsupported MIME type"):
            validate_asset("track.gif", "image/gif", 1024)

    def test_files_over_configured_size_limit_are_rejected(self):
        validate_asset("track.png", "image/png", MAX_ASSET_BYTES)
        with self.assertRaisesRegex(ValueError, "asset exceeds maximum size"):
            validate_asset("track.png", "image/png", MAX_ASSET_BYTES + 1)

    def test_storing_asset_records_metadata_and_calibration_transform(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            transform = {
                "scale": 1.25,
                "rotate_deg": 3.5,
                "translate_x": -42.0,
                "translate_y": 18.0,
            }

            asset_id = store.create_track_asset(
                track_profile_id=profile_id,
                filename="emerald.png",
                stored_path=str(Path(tmp) / "assets" / "emerald.png"),
                mime_type="image/png",
                size_bytes=2048,
                transform=transform,
            )

            assets = store.track_assets_for_profile(profile_id)
            self.assertEqual(len(assets), 1)
            asset = assets[0]
            self.assertEqual(asset["id"], asset_id)
            self.assertEqual(asset["track_profile_id"], profile_id)
            self.assertEqual(asset["filename"], "emerald.png")
            self.assertEqual(asset["stored_path"], str(Path(tmp) / "assets" / "emerald.png"))
            self.assertEqual(asset["mime_type"], "image/png")
            self.assertEqual(asset["size_bytes"], 2048)
            self.assertEqual(asset["transform"], transform)
            self.assertIsInstance(asset["created_at_ms"], int)
            self.assertIsInstance(asset["updated_at_ms"], int)

    def test_updating_transform_persists_scale_rotation_and_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            asset_id = store.create_track_asset(
                track_profile_id=profile_id,
                filename="emerald.svg",
                stored_path=str(Path(tmp) / "assets" / "emerald.svg"),
                mime_type="image/svg+xml",
                size_bytes=1024,
            )

            updated = store.update_track_asset_transform(
                asset_id,
                {
                    "scale": 0.75,
                    "rotate_deg": -12.0,
                    "translate_x": 64.5,
                    "translate_y": -9.25,
                },
            )

            self.assertEqual(updated["transform"]["scale"], 0.75)
            self.assertEqual(updated["transform"]["rotate_deg"], -12.0)
            self.assertEqual(updated["transform"]["translate_x"], 64.5)
            self.assertEqual(updated["transform"]["translate_y"], -9.25)
            self.assertEqual(
                store.track_assets_for_profile(profile_id)[0]["transform"],
                updated["transform"],
            )

    def test_default_transform_is_used_when_none_is_supplied(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            asset_id = store.create_track_asset(
                track_profile_id=profile_id,
                filename="emerald.webp",
                stored_path=str(Path(tmp) / "assets" / "emerald.webp"),
                mime_type="image/webp",
                size_bytes=1024,
            )

            self.assertEqual(
                store.track_assets_for_profile(profile_id)[0]["transform"],
                default_transform(),
            )
            with store.connect() as con:
                row = con.execute("SELECT transform_json FROM track_assets WHERE id = ?", (asset_id,)).fetchone()
            self.assertEqual(json.loads(row["transform_json"]), default_transform())

    def test_unknown_profile_and_asset_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            with self.assertRaisesRegex(ValueError, "unknown track_profile_id"):
                store.create_track_asset(
                    track_profile_id="missing-profile",
                    filename="track.png",
                    stored_path=str(Path(tmp) / "track.png"),
                    mime_type="image/png",
                    size_bytes=1024,
                )
            with self.assertRaisesRegex(ValueError, "unknown track_profile_id"):
                store.track_assets_for_profile("missing-profile")
            with self.assertRaisesRegex(ValueError, "unknown track_asset_id"):
                store.update_track_asset_transform("missing-asset", default_transform())
            with self.assertRaisesRegex(ValueError, "unknown track_asset_id"):
                store.delete_track_asset("missing-asset")

    def test_invalid_transform_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            asset_id = store.create_track_asset(
                track_profile_id=profile_id,
                filename="emerald.png",
                stored_path=str(Path(tmp) / "assets" / "emerald.png"),
                mime_type="image/png",
                size_bytes=1024,
            )

            invalid_transforms = [
                {"scale": 0, "rotate_deg": 0, "translate_x": 0, "translate_y": 0},
                {"scale": 1, "rotate_deg": "bad", "translate_x": 0, "translate_y": 0},
                {"scale": 1, "rotate_deg": 0, "translate_x": float("inf"), "translate_y": 0},
                {"scale": 1, "rotate_deg": 0, "translate_x": 0},
            ]
            for transform in invalid_transforms:
                with self.subTest(transform=transform):
                    with self.assertRaises(ValueError):
                        store.update_track_asset_transform(asset_id, transform)

    def test_deleting_asset_removes_metadata_and_leaves_profile_and_lap_data_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store_in(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            session_id = store.create_session("Deletion demo")
            lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
            store.assign_track_profile(session_id, lap_id, profile_id)
            asset_id = store.create_track_asset(
                track_profile_id=profile_id,
                filename="emerald.jpg",
                stored_path=str(Path(tmp) / "assets" / "emerald.jpg"),
                mime_type="image/jpeg",
                size_bytes=1024,
            )

            deleted = store.delete_track_asset(asset_id)

            self.assertEqual(deleted["id"], asset_id)
            self.assertEqual(store.track_assets_for_profile(profile_id), [])
            self.assertIsNotNone(store.track_profile(profile_id))
            with store.connect() as con:
                session = con.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
                lap = con.execute("SELECT track_profile_id FROM laps WHERE id = ?", (lap_id,)).fetchone()
            self.assertEqual(session["id"], session_id)
            self.assertEqual(lap["track_profile_id"], profile_id)


class TrackAssetApiTests(unittest.TestCase):
    def test_asset_routes_create_list_update_delete_and_copy_local_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            source_path = Path(tmp) / "source.svg"
            source_path.write_text("<svg />", encoding="utf-8")

            with client:
                create_response = client.post(
                    f"/api/tracks/profiles/{profile_id}/assets",
                    json={
                        "filename": "track.svg",
                        "sourcePath": str(source_path),
                        "mimeType": "image/svg+xml",
                        "sizeBytes": source_path.stat().st_size,
                        "transform": {
                            "scale": 1.1,
                            "rotate_deg": 2,
                            "translate_x": 3,
                            "translate_y": 4,
                        },
                    },
                )
                list_response = client.get(f"/api/tracks/profiles/{profile_id}/assets")

            self.assertEqual(create_response.status_code, 200)
            asset = create_response.json()["asset"]
            self.assertEqual(asset["track_profile_id"], profile_id)
            self.assertEqual(asset["filename"], "track.svg")
            self.assertEqual(asset["mime_type"], "image/svg+xml")
            self.assertEqual(asset["size_bytes"], source_path.stat().st_size)
            self.assertEqual(
                asset["transform"],
                {"scale": 1.1, "rotate_deg": 2.0, "translate_x": 3.0, "translate_y": 4.0},
            )
            self.assertNotIn("stored_path", asset)
            self.assertTrue(asset["file_url"].endswith(f"/api/tracks/assets/{asset['id']}/file"))
            stored_asset = store.track_asset(asset["id"])
            self.assertIsNotNone(stored_asset)
            self.assertTrue(Path(stored_asset["stored_path"]).is_file())
            self.assertNotEqual(Path(stored_asset["stored_path"]).resolve(), source_path.resolve())

            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(list_response.json()["assets"][0]["id"], asset["id"])
            self.assertNotIn("stored_path", list_response.json()["assets"][0])

            with client:
                file_response = client.get(asset["file_url"])
                patch_response = client.patch(
                    f"/api/tracks/assets/{asset['id']}/transform",
                    json={
                        "scale": 0.8,
                        "rotateDeg": -5,
                        "translateX": 12,
                        "translateY": -9,
                    },
                )
                delete_response = client.delete(f"/api/tracks/assets/{asset['id']}")
                after_delete_response = client.get(f"/api/tracks/profiles/{profile_id}/assets")

            self.assertEqual(file_response.status_code, 200)
            self.assertEqual(file_response.content, source_path.read_bytes())
            self.assertEqual(patch_response.status_code, 200)
            self.assertNotIn("stored_path", patch_response.json()["asset"])
            self.assertEqual(
                patch_response.json()["asset"]["transform"],
                {"scale": 0.8, "rotate_deg": -5.0, "translate_x": 12.0, "translate_y": -9.0},
            )
            self.assertEqual(delete_response.status_code, 200)
            self.assertEqual(delete_response.json()["asset_id"], asset["id"])
            self.assertTrue(delete_response.json()["deleted"])
            self.assertNotIn("stored_path", delete_response.json()["asset"])
            self.assertEqual(after_delete_response.json()["assets"], [])

    def test_injected_asset_outside_storage_is_not_served_or_exposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            outside_path = Path(tmp) / "outside.png"
            outside_path.write_bytes(b"outside")
            with store.connect() as con:
                con.execute(
                    """
                    INSERT INTO track_assets(
                        id, track_profile_id, filename, stored_path, mime_type,
                        size_bytes, transform_json, created_at_ms, updated_at_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "legacy-outside",
                        profile_id,
                        "outside.png",
                        str(outside_path),
                        "image/png",
                        outside_path.stat().st_size,
                        json.dumps(default_transform(), sort_keys=True, separators=(",", ":")),
                        1_000,
                        1_000,
                    ),
                )

            with client:
                list_response = client.get(f"/api/tracks/profiles/{profile_id}/assets")
                file_response = client.get("/api/tracks/assets/legacy-outside/file")

            self.assertEqual(list_response.status_code, 200)
            payload = list_response.json()["assets"][0]
            self.assertEqual(payload["id"], "legacy-outside")
            self.assertNotIn("stored_path", payload)
            self.assertIn("file_url", payload)
            self.assertEqual(file_response.status_code, 404)

    def test_merged_track_asset_remains_servable_from_original_profile_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            keep_profile_id = store.create_track_profile("Keep Circuit", "Full", "manual", "user")
            merge_profile_id = store.create_track_profile("Merge Circuit", "Full", "manual", "user")
            source_path = Path(tmp) / "merge-source.png"
            source_path.write_bytes(b"merged-map")

            with client:
                create_response = client.post(
                    f"/api/tracks/profiles/{merge_profile_id}/assets",
                    json={
                        "filename": "merge-map.png",
                        "sourcePath": str(source_path),
                        "mimeType": "image/png",
                        "sizeBytes": source_path.stat().st_size,
                    },
                )

            self.assertEqual(create_response.status_code, 200)
            asset = create_response.json()["asset"]
            asset_id = asset["id"]
            file_url = asset["file_url"]

            with client:
                before_merge_file_response = client.get(file_url)

            self.assertEqual(before_merge_file_response.status_code, 200)
            self.assertEqual(before_merge_file_response.content, b"merged-map")

            store.merge_track_profiles(keep_profile_id, merge_profile_id)
            outside_path = Path(tmp) / "outside-after-merge.png"
            outside_path.write_bytes(b"outside")
            with store.connect() as con:
                con.execute(
                    """
                    INSERT INTO track_assets(
                        id, track_profile_id, filename, stored_path, mime_type,
                        size_bytes, transform_json, created_at_ms, updated_at_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "outside-after-merge",
                        keep_profile_id,
                        "outside-after-merge.png",
                        str(outside_path),
                        "image/png",
                        outside_path.stat().st_size,
                        json.dumps(default_transform(), sort_keys=True, separators=(",", ":")),
                        1_000,
                        1_000,
                    ),
                )

            with client:
                list_response = client.get(f"/api/tracks/profiles/{keep_profile_id}/assets")
                after_merge_file_response = client.get(file_url)
                outside_file_response = client.get("/api/tracks/assets/outside-after-merge/file")

            self.assertEqual(list_response.status_code, 200)
            listed_assets = list_response.json()["assets"]
            listed_asset = next((item for item in listed_assets if item["id"] == asset_id), None)
            self.assertIsNotNone(listed_asset)
            self.assertEqual(listed_asset["track_profile_id"], keep_profile_id)
            self.assertNotIn("stored_path", listed_asset)
            self.assertEqual(after_merge_file_response.status_code, 200)
            self.assertEqual(after_merge_file_response.content, b"merged-map")
            self.assertEqual(outside_file_response.status_code, 404)

    def test_copied_file_is_removed_when_metadata_insert_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            source_path = Path(tmp) / "source.png"
            source_path.write_bytes(b"png")
            asset_dir = Path(tmp) / "track_assets" / profile_id
            original_create = store.create_track_asset

            def failing_create_track_asset(**kwargs):
                raise ValueError("forced insert failure")

            store.create_track_asset = failing_create_track_asset  # type: ignore[method-assign]
            try:
                with client:
                    response = client.post(
                        f"/api/tracks/profiles/{profile_id}/assets",
                        json={
                            "filename": "track.png",
                            "source_path": str(source_path),
                            "mime_type": "image/png",
                            "size_bytes": source_path.stat().st_size,
                        },
                    )
            finally:
                store.create_track_asset = original_create  # type: ignore[method-assign]

            self.assertEqual(response.status_code, 400)
            self.assertTrue(source_path.exists())
            self.assertEqual(list(asset_dir.glob("*")) if asset_dir.exists() else [], [])

    def test_asset_routes_map_unknown_ids_to_404_and_validation_to_400(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, store = _client_and_store(tmp)
            profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
            source_path = Path(tmp) / "source.png"
            source_path.write_bytes(b"png")

            with client:
                unknown_profile = client.get("/api/tracks/profiles/missing-profile/assets")
                bad_mime = client.post(
                    f"/api/tracks/profiles/{profile_id}/assets",
                    json={
                        "filename": "track.gif",
                        "source_path": str(source_path),
                        "mime_type": "image/gif",
                        "size_bytes": source_path.stat().st_size,
                    },
                )
                size_mismatch = client.post(
                    f"/api/tracks/profiles/{profile_id}/assets",
                    json={
                        "filename": "track.png",
                        "source_path": str(source_path),
                        "mime_type": "image/png",
                        "size_bytes": source_path.stat().st_size + 1,
                    },
                )
                missing_asset = client.patch(
                    "/api/tracks/assets/missing-asset/transform",
                    json=default_transform(),
                )

            self.assertEqual(unknown_profile.status_code, 404)
            self.assertEqual(bad_mime.status_code, 400)
            self.assertEqual(size_mismatch.status_code, 400)
            self.assertEqual(missing_asset.status_code, 404)


if __name__ == "__main__":
    unittest.main()
