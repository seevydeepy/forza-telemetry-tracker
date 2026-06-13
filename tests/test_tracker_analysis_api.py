import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from telemetry_tracker.app import create_app
from telemetry_tracker.packet_bridge import decode_packet, encode_packet_for_test, packet_to_live_fields
from telemetry_tracker.storage import TelemetryStore


OVERLAY_IDS = ["issues", "speed", "inputs", "grip", "temperature", "suspension", "rpm"]


def _insert_analysis_lap(
    store,
    session_id: str,
    *,
    lap_number: int = 1,
    sample_count: int = 25,
    car_values: dict | None = None,
):
    lap_id = store.create_lap(
        session_id=session_id,
        lap_number=lap_number,
        boundary_confidence="game_field",
    )
    raw_packets = []
    decoded_packets = []
    samples = []
    for sequence in range(1, sample_count + 1):
        values = {
            "TimestampMS": sequence * 16,
            "LapNumber": lap_number,
            "CurrentLap": float(sequence),
            "CurrentRaceTime": float(sequence),
            "PositionX": float(sequence),
            "PositionY": 0.0,
            "PositionZ": float(sequence) * 1.5,
            "Speed": float(sequence),
            "Accel": 255 if sequence >= 10 else 128,
            "Brake": 220 if sequence in (10, 11) else 0,
            "Steer": -10 if sequence in (10, 11) else 0,
            "CurrentEngineRpm": 7900.0 if sequence >= 20 else 6000.0,
            "EngineMaxRpm": 8000.0,
            **(car_values or {}),
        }
        if sequence in (10, 11):
            values["TireCombinedSlipFrontLeft"] = 0.45
            values["TireCombinedSlipFrontRight"] = 0.44
            values["TireCombinedSlipRearLeft"] = 1.31
            values["TireCombinedSlipRearRight"] = 1.28
        raw = encode_packet_for_test(values)
        decoded = decode_packet(raw)
        sample = packet_to_live_fields(decoded, sequence=sequence, received_at_ms=sequence * 16)
        sample["lap_id"] = lap_id
        raw_packets.append(raw)
        decoded_packets.append(decoded)
        samples.append(sample)
    store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)
    return lap_id, raw_packets


def _insert_collision_lap(store, session_id: str):
    lap_id = store.create_lap(
        session_id=session_id,
        lap_number=1,
        boundary_confidence="game_field",
    )
    raw_packets = []
    decoded_packets = []
    samples = []
    recovery_speeds = {
        12: 28.0,
        13: 28.0,
        14: 28.0,
        15: 28.0,
        16: 28.0,
        17: 28.0,
        18: 28.0,
        19: 28.0,
        20: 32.0,
        21: 36.0,
        22: 39.0,
    }
    for sequence in range(1, 28):
        values = {
            "IsRaceOn": 1,
            "TimestampMS": sequence * 100,
            "LapNumber": 1,
            "CurrentLap": sequence / 10.0,
            "CurrentRaceTime": sequence / 10.0,
            "PositionX": float(sequence),
            "PositionY": 0.0,
            "PositionZ": float(sequence),
            "Speed": recovery_speeds.get(sequence, 40.0),
            "Accel": 128,
            "Brake": 0,
            "Steer": 0,
            "CurrentEngineRpm": 6000.0,
            "EngineMaxRpm": 8000.0,
        }
        if sequence == 11:
            values["SmashableVelDiff"] = 4.0
            values["SmashableMass"] = 2.0
        raw = encode_packet_for_test(values)
        decoded = decode_packet(raw)
        sample = packet_to_live_fields(decoded, sequence=sequence, received_at_ms=sequence * 100)
        sample["lap_id"] = lap_id
        raw_packets.append(raw)
        decoded_packets.append(decoded)
        samples.append(sample)
    store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)
    return lap_id


class TrackerAnalysisApiTests(unittest.TestCase):
    def test_overlays_endpoint_returns_backend_overlay_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")

            with TestClient(app) as client:
                response = client.get("/api/overlays")

            self.assertEqual(response.status_code, 200)
            self.assertEqual([overlay["id"] for overlay in response.json()["overlays"]], OVERLAY_IDS)

    def test_analyze_endpoint_generates_markers_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Analysis API")
            lap_id, _ = _insert_analysis_lap(store, session_id)

            with TestClient(app) as client:
                response = client.post(f"/api/laps/{lap_id}/analyze")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["lap_id"], lap_id)
            self.assertEqual(payload["session_id"], session_id)
            self.assertEqual(payload["summary"]["packet_count"], 25)
            self.assertEqual(payload["summary"]["start_sequence"], 1)
            self.assertEqual(payload["summary"]["end_sequence"], 25)
            self.assertTrue(payload["markers"])
            self.assertTrue(any(marker["metric"] == "rear_combined_slip" for marker in payload["markers"]))
            self.assertEqual(store.lap_summary(lap_id)["packet_count"], 25)
            self.assertEqual(store.issue_markers_for_lap(lap_id=lap_id), payload["markers"])

    def test_analyze_endpoint_persists_time_loss_collision_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Collision analysis API")
            lap_id = _insert_collision_lap(store, session_id)

            with TestClient(app) as client:
                response = client.post(f"/api/laps/{lap_id}/analyze")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            marker = next(
                marker
                for marker in payload["markers"]
                if marker["metric"] == "collision_smashable_time_loss"
            )
            self.assertEqual(marker["issue_kind"], "Smashable collision")
            self.assertEqual(marker["value_label"], "Estimated time loss")
            self.assertEqual(marker["value_unit"], "s")
            self.assertGreaterEqual(marker["actual_value"], 0.2)
            self.assertEqual(marker["ruleset_version"], 3)
            persisted_markers = store.issue_markers_for_lap(lap_id=lap_id)
            persisted_marker = next(
                (persisted for persisted in persisted_markers if persisted["id"] == marker["id"]),
                None,
            )
            self.assertIsNotNone(persisted_marker)
            self.assertEqual(persisted_marker["metric"], "collision_smashable_time_loss")
            self.assertEqual(persisted_marker["issue_kind"], marker["issue_kind"])
            self.assertEqual(persisted_marker["value_label"], marker["value_label"])
            self.assertEqual(persisted_marker["value_unit"], marker["value_unit"])
            self.assertEqual(persisted_marker["ruleset_version"], marker["ruleset_version"])
            self.assertAlmostEqual(persisted_marker["actual_value"], marker["actual_value"])
            self.assertAlmostEqual(persisted_marker["confidence"], marker["confidence"])

    def test_lap_summary_endpoint_returns_full_lap_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Summary API")
            lap_id, _ = _insert_analysis_lap(store, session_id)

            with TestClient(app) as client:
                analyze = client.post(f"/api/laps/{lap_id}/analyze")
                response = client.get(f"/api/laps/{lap_id}/summary")

            self.assertEqual(analyze.status_code, 200)
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["lap_id"], lap_id)
            self.assertEqual(payload["session_id"], session_id)
            self.assertEqual(payload["summary"]["packet_count"], 25)
            self.assertEqual(payload["summary"]["top_speed_mps"], 25.0)
            self.assertEqual(payload["summary"]["average_speed_mps"], 13.0)
            self.assertEqual(payload["summary"]["start_sequence"], 1)
            self.assertEqual(payload["summary"]["end_sequence"], 25)


    def test_lap_summary_endpoint_includes_car_info_from_packets_and_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            store.upsert_car_catalog_records(
                [
                    {
                        "ordinal": 1229,
                        "display_name": "Furai",
                        "model_short": "Mazda Furai",
                        "year": 2008,
                        "catalog_source": "test",
                    }
                ]
            )
            session_id = store.create_session(label="Car API")
            lap_id, _ = _insert_analysis_lap(
                store,
                session_id,
                car_values={
                    "CarOrdinal": 1229,
                    "CarClass": 6,
                    "CarPerformanceIndex": 998,
                    "DrivetrainType": 1,
                    "NumCylinders": 3,
                    "CarGroup": 26,
                    "Power": 331000.0,
                    "Torque": 392.0,
                    "Fuel": 0.75,
                },
            )

            with TestClient(app) as client:
                response = client.get(f"/api/laps/{lap_id}/summary")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            car = payload["car"]
            self.assertEqual(car["name"], "Mazda Furai")
            self.assertEqual(car["year"], 2008)
            self.assertEqual(car["class_label"], "R")
            self.assertEqual(car["performance_index"], 998)
            self.assertEqual(car["drivetrain_label"], "RWD")
            self.assertEqual(car["details"]["num_cylinders"], 3)

    def test_create_app_can_refresh_car_catalog_from_env_media_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_root = Path(tmp) / "media"
            cars_dir = media_root / "Cars"
            strings_dir = media_root / "Stripped" / "StringTables"
            cars_dir.mkdir(parents=True)
            strings_dir.mkdir(parents=True)
            with zipfile.ZipFile(cars_dir / "ACU_IntegraR_01.zip", "w") as archive:
                archive.writestr("Scene/animations/Mojo/clip/carclips_368.clipd", b"clip")
            with zipfile.ZipFile(strings_dir / "EN.zip", "w") as archive:
                archive.writestr(
                    "Data_Car.str",
                    b"Integra Type R\x00Acura Integra\x00IDS_DisplayName_368\x00IDS_ModelShort_368\x00",
                )

            with patch.dict(os.environ, {"FH6_MEDIA_ROOT": str(media_root)}):
                app = create_app(
                    db_path=Path(tmp) / "telemetry_tracker.sqlite3",
                    refresh_car_catalog=True,
                )

            car = app.state.store.car_by_ordinal(368)
            self.assertEqual(car["display_name"], "Integra Type R")
            self.assertEqual(car["model_short"], "Acura Integra")
            self.assertEqual(car["asset_zip"], "ACU_IntegraR_01.zip")

    def test_create_app_can_refresh_track_catalog_from_env_media_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_root = Path(tmp) / "media"
            media_root.mkdir(parents=True)
            catalog = type(
                "Catalog",
                (),
                {
                    "tracks": [
                        {
                            "track_key": "track-info:42",
                            "source_dataset_key": 42,
                            "route_id": 8001,
                            "media_track_name": "Brio",
                            "ribbon_config": "P2P",
                            "display_name": "Pier Pressure",
                            "catalog_source": "test",
                        }
                    ],
                    "map_regions": [],
                    "locators": [],
                },
            )()

            with (
                patch.dict(os.environ, {"FH6_MEDIA_ROOT": str(media_root)}),
                patch("telemetry_tracker.app.load_local_fh6_track_catalog", return_value=catalog),
            ):
                app = create_app(
                    db_path=Path(tmp) / "telemetry_tracker.sqlite3",
                    refresh_track_catalog=True,
                )

            track = app.state.store.game_track_by_route_id(8001)
            self.assertEqual(track["display_name"], "Pier Pressure")

    def test_create_app_refreshes_existing_track_catalog_when_ai_geometry_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "telemetry_tracker.sqlite3"
            media_root = Path(tmp) / "media"
            media_root.mkdir(parents=True)
            store = TelemetryStore(db_path)
            store.migrate()
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
            catalog = type(
                "Catalog",
                (),
                {
                    "tracks": [
                        {
                            "track_key": "track-info:161",
                            "source_dataset_key": 161,
                            "route_id": 161,
                            "media_track_name": "Brio",
                            "ribbon_config": "Circuit",
                            "display_name": "Shirakawa Circuit",
                            "catalog_source": "test",
                        }
                    ],
                    "map_regions": [],
                    "locators": [
                        {
                            "source_file": "OpenWorld/Brio/AITracks/Route161.owt",
                            "media_track_name": "Brio",
                            "locator_collection": "aitrack_route161",
                            "locator_name": "route_point_00000",
                            "locator_kind": "route_point",
                            "route_id": 161,
                            "x": 1308.0,
                            "y": 120.0,
                            "z": 282.0,
                            "heading_yaw_rad": None,
                            "transform_json": "{}",
                            "catalog_source": "test",
                        }
                    ],
                },
            )()

            with (
                patch.dict(os.environ, {"FH6_MEDIA_ROOT": str(media_root)}),
                patch("telemetry_tracker.app.load_local_fh6_track_catalog", return_value=catalog),
            ):
                app = create_app(db_path=db_path, refresh_track_catalog=True)

            self.assertEqual(
                app.state.store.game_track_locator_count(
                    source_file_like="OpenWorld/%/AITracks/Route%.owt"
                ),
                1,
            )

    def test_lap_summary_endpoint_recomputes_analysis_schema_when_legacy_m2_summary_is_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Legacy summary API")
            lap_id, _ = _insert_analysis_lap(store, session_id)
            store.insert_lap_summary(
                lap_id,
                {
                    "sample_count": 25,
                    "packet_count": 25,
                    "lap_duration_ms": 400,
                    "distance_estimate_m": 123.4,
                    "top_speed_mps": 25.0,
                    "average_speed_mps": 13.0,
                    "max_throttle": 255,
                    "average_throttle": 204,
                    "max_brake": 220,
                    "average_brake": 18,
                    "max_slip": 1.31,
                    "uncertainty_count": 0,
                },
            )

            with TestClient(app) as client:
                response = client.get(f"/api/laps/{lap_id}/summary")

            self.assertEqual(response.status_code, 200)
            summary = response.json()["summary"]
            self.assertEqual(summary["packet_count"], 25)
            self.assertIn("peak_combined_slip", summary)
            self.assertIn("limiter_samples", summary)
            self.assertIn("bottoming_events", summary)
            self.assertEqual(summary["start_sequence"], 1)
            self.assertEqual(summary["end_sequence"], 25)
            self.assertNotIn("sample_count", summary)
            self.assertNotIn("lap_duration_ms", summary)

    def test_lap_summary_endpoint_returns_section_summary_for_sequence_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Section summary API")
            lap_id, _ = _insert_analysis_lap(store, session_id)

            with TestClient(app) as client:
                response = client.get(f"/api/laps/{lap_id}/summary?start_sequence=10&end_sequence=20")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["lap_id"], lap_id)
            self.assertEqual(payload["session_id"], session_id)
            self.assertEqual(payload["summary"]["start_sequence"], 10)
            self.assertEqual(payload["summary"]["end_sequence"], 20)
            self.assertEqual(payload["summary"]["packet_count"], 11)
            self.assertEqual(payload["summary"]["top_speed_mps"], 20.0)
            self.assertEqual(payload["summary"]["average_speed_mps"], 15.0)

    def test_lap_markers_endpoint_returns_persisted_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Markers API")
            lap_id, _ = _insert_analysis_lap(store, session_id)

            with TestClient(app) as client:
                analyze = client.post(f"/api/laps/{lap_id}/analyze")
                response = client.get(f"/api/laps/{lap_id}/markers")

            self.assertEqual(analyze.status_code, 200)
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["lap_id"], lap_id)
            self.assertEqual(payload["session_id"], session_id)
            self.assertEqual(payload["markers"], analyze.json()["markers"])
            marker = payload["markers"][0]
            self.assertIn("anchor_sequence", marker)
            self.assertIn("issue_kind", marker)
            self.assertIn("actual_value", marker)
            self.assertIn("threshold_value", marker)
            self.assertIn("threshold_operator", marker)

    def test_lap_markers_endpoint_backfills_legacy_marker_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Legacy marker details API")
            lap_id, _ = _insert_analysis_lap(store, session_id)
            store.insert_lap_summary(
                lap_id,
                {
                    "packet_count": 25,
                    "top_speed_mps": 25.0,
                    "average_speed_mps": 13.0,
                    "peak_combined_slip": 1.31,
                    "limiter_samples": 6,
                    "bottoming_events": 0,
                    "start_sequence": 1,
                    "end_sequence": 25,
                },
            )
            store.insert_issue_markers(
                [
                    {
                        "id": "legacy-marker",
                        "session_id": session_id,
                        "lap_id": lap_id,
                        "start_sequence": 10,
                        "end_sequence": 11,
                        "metric": "rear_combined_slip",
                        "severity": "critical",
                        "reason": "legacy",
                        "ruleset_version": 1,
                        "confidence": 0.8,
                    }
                ]
            )

            with TestClient(app) as client:
                response = client.get(f"/api/laps/{lap_id}/markers")

            self.assertEqual(response.status_code, 200)
            markers = response.json()["markers"]
            self.assertTrue(markers)
            slip_marker = next(marker for marker in markers if marker["metric"] == "rear_combined_slip")
            self.assertEqual(slip_marker["ruleset_version"], 3)
            self.assertIsNotNone(slip_marker["anchor_sequence"])
            self.assertEqual(slip_marker["issue_kind"], "Rear combined slip")
            self.assertIsNotNone(slip_marker["actual_value"])
            self.assertIsNotNone(slip_marker["threshold_value"])
            self.assertNotIn("legacy-marker", {marker["id"] for marker in markers})

    def test_lap_markers_endpoint_does_not_reanalyze_current_detail_marker_with_null_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Current marker details API")
            lap_id, _ = _insert_analysis_lap(store, session_id)
            store.insert_issue_markers(
                [
                    {
                        "id": "current-detail-marker",
                        "session_id": session_id,
                        "lap_id": lap_id,
                        "start_sequence": 999,
                        "end_sequence": 999,
                        "metric": "rear_combined_slip",
                        "severity": "critical",
                        "reason": "Current marker with no usable anchor.",
                        "ruleset_version": 3,
                        "confidence": 0.8,
                        "anchor_sequence": None,
                        "issue_kind": "Rear combined slip",
                        "actual_value": 1.2,
                        "threshold_value": 1.15,
                        "threshold_operator": "gte",
                        "value_label": "Rear combined slip",
                        "value_unit": None,
                    }
                ]
            )

            with TestClient(app) as client:
                response = client.get(f"/api/laps/{lap_id}/markers")

            self.assertEqual(response.status_code, 200)
            markers = response.json()["markers"]
            self.assertEqual([marker["id"] for marker in markers], ["current-detail-marker"])
            self.assertIsNone(markers[0]["anchor_sequence"])

    def test_lap_markers_endpoint_backfills_missing_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Markers backfill API")
            lap_id, _ = _insert_analysis_lap(store, session_id)
            self.assertEqual(store.issue_markers_for_lap(lap_id=lap_id), [])

            with TestClient(app) as client:
                response = client.get(f"/api/laps/{lap_id}/markers")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["lap_id"], lap_id)
            self.assertEqual(payload["session_id"], session_id)
            self.assertTrue(payload["markers"])
            self.assertTrue(
                any(
                    marker["metric"] == "rear_combined_slip"
                    and marker["severity"] == "critical"
                    for marker in payload["markers"]
                )
            )
            self.assertEqual(store.issue_markers_for_lap(lap_id=lap_id), payload["markers"])

    def test_point_endpoint_decodes_raw_packet_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Point API")
            lap_id, raw_packets = _insert_analysis_lap(store, session_id)
            self.assertTrue(lap_id)

            with TestClient(app) as client:
                response = client.get(f"/api/sessions/{session_id}/points/10")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["session_id"], session_id)
            self.assertEqual(payload["sequence"], 10)
            self.assertEqual(payload["point"]["TimestampMS"], 160)
            self.assertEqual(payload["point"]["Speed"], 10.0)
            self.assertEqual(payload["point"]["TireCombinedSlipRearLeft"], decode_packet(raw_packets[9])["TireCombinedSlipRearLeft"])

    def test_analysis_endpoints_reject_unknown_ids_and_invalid_section_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Errors API")
            lap_id, _ = _insert_analysis_lap(store, session_id)

            with TestClient(app) as client:
                self.assertEqual(client.post("/api/laps/missing/analyze").status_code, 404)
                self.assertEqual(client.get("/api/laps/missing/summary").status_code, 404)
                self.assertEqual(client.get("/api/laps/missing/markers").status_code, 404)
                self.assertEqual(client.get(f"/api/sessions/{session_id}/points/999").status_code, 404)
                self.assertEqual(client.get("/api/sessions/missing/points/10").status_code, 404)

                partial = client.get(f"/api/laps/{lap_id}/summary?start_sequence=10")
                backwards = client.get(f"/api/laps/{lap_id}/summary?start_sequence=20&end_sequence=10")
                outside = client.get(f"/api/laps/{lap_id}/summary?start_sequence=100&end_sequence=110")
                partial_overlap = client.get(f"/api/laps/{lap_id}/summary?start_sequence=20&end_sequence=30")
                non_positive_point = client.get(f"/api/sessions/{session_id}/points/0")

            self.assertEqual(partial.status_code, 400)
            self.assertEqual(backwards.status_code, 400)
            self.assertEqual(outside.status_code, 400)
            self.assertEqual(partial_overlap.status_code, 400)
            self.assertEqual(non_positive_point.status_code, 400)


if __name__ == "__main__":
    unittest.main()
