import asyncio
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from telemetry_tracker.app import create_app, stream_sse_events
from telemetry_tracker.app_metadata import ReleaseMetadata
from telemetry_tracker.app_updates import UpdateCheckResult
from telemetry_tracker.app_paths import default_desktop_paths
from telemetry_tracker.events import EventBus
from telemetry_tracker.local_file_selection import LocalFileSelectionRegistry
from telemetry_tracker.packet_bridge import decode_packet, encode_packet_for_test, packet_to_live_fields
from telemetry_tracker.track_matcher import MATCHER_VERSION



def _wait_for_export_job(client: TestClient, job_id: str, predicate, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    last_job = None
    while time.monotonic() < deadline:
        response = client.get("/api/telemetry/export-jobs")
        if response.status_code == 200:
            jobs = response.json()["jobs"]
            last_job = next((job for job in jobs if job["id"] == job_id), None)
            if last_job is not None and predicate(last_job):
                return last_job
        time.sleep(0.02)
    raise AssertionError(f"export job {job_id} did not reach expected state; last={last_job}")


def _test_runtime_paths(tmp: str | Path):
    base = Path(tmp)
    return default_desktop_paths(resource_base=base / "resources", user_data_base=base / "app-data")


class FakeUpdateService:
    def __init__(self):
        self.metadata = ReleaseMetadata(
            version="1.0.0",
            release_date="2026-06-13",
            git_sha="abc123",
            repository="owner/repo",
            channel="stable",
            packaged=True,
        )
        self.check_calls = []

    def about_update_payload(self):
        return {
            "supported": True,
            "release_access": "public",
        }

    def check_for_updates(self, *, force=False):
        self.check_calls.append(force)
        return UpdateCheckResult(
            status="update_available",
            current_version="1.0.0",
            latest_version="1.1.0",
            release_url="https://github.example/releases/v1.1.0",
            published_at="2026-06-13T12:00:00Z",
            asset_name="ForzaTelemetryTrackerSetup-v1.1.0-x64.exe",
            message="Update 1.1.0 is available.",
        )


def _frame_payload(frame: str) -> dict:
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    return json.loads(data_line.removeprefix("data: "))


def _insert_samples(store, session_id: str, raw_packets: list[bytes], sequence_offset: int = 0) -> list[dict]:
    decoded_packets = [decode_packet(raw) for raw in raw_packets]
    samples = [
        {
            **packet_to_live_fields(decoded, sequence_offset + index + 1, index * 16),
            "uncertainty": None,
        }
        for index, decoded in enumerate(decoded_packets)
    ]
    store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)
    return samples


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
        "Speed": 30.0,
        "CurrentLap": float(index) / 10.0,
        "CurrentRaceTime": float(index) / 10.0,
        "LapNumber": 1,
    }
    values.update(overrides)
    return encode_packet_for_test(values)


def _drain_events(queue) -> list[dict]:
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


def _line_track_points(offset_z: float = 0.0) -> list[tuple[float, float]]:
    return [(float(index * 10), offset_z) for index in range(11)]


def _seed_line_track(
    store,
    *,
    track_key: str,
    route_id: int,
    display_name: str,
    offset_z: float = 0.0,
) -> None:
    store.upsert_track_catalog_records(
        [
            {
                "track_key": track_key,
                "source_dataset_key": route_id,
                "route_id": route_id,
                "media_track_id": 820,
                "media_track_name": "Brio",
                "ribbon_config": "Circuit",
                "display_name": display_name,
                "catalog_source": "test",
            }
        ],
        [],
        [
            {
                "source_file": f"OpenWorld/Brio/AITracks/Route{route_id}.owt",
                "media_track_name": "Brio",
                "locator_collection": f"aitrack_route{route_id}",
                "locator_name": f"route_point_{index:05d}",
                "locator_kind": "route_point",
                "route_id": route_id,
                "x": x,
                "y": 0.0,
                "z": z,
                "heading_yaw_rad": None,
                "transform_json": "{}",
                "catalog_source": "test",
            }
            for index, (x, z) in enumerate(_line_track_points(offset_z))
        ],
    )


class SpyEventBus(EventBus):
    def __init__(self):
        super().__init__()
        self.unsubscribed_queues = []

    def unsubscribe(self, queue) -> None:
        self.unsubscribed_queues.append(queue)
        super().unsubscribe(queue)


class TrackerAppTests(unittest.TestCase):
    def test_about_endpoint_returns_release_metadata_with_public_update_access(self):
        update_service = FakeUpdateService()
        app = create_app(db_path=Path(tempfile.mkdtemp()) / "telemetry_tracker.sqlite3", update_service=update_service)

        with TestClient(app) as client:
            response = client.get("/api/app/about")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["version"], "1.0.0")
        self.assertEqual(payload["release_date"], "2026-06-13")
        self.assertEqual(payload["repository"], "owner/repo")
        self.assertEqual(payload["updates"], {"supported": True, "release_access": "public"})

    def test_update_check_endpoint_delegates_force_flag(self):
        update_service = FakeUpdateService()
        app = create_app(db_path=Path(tempfile.mkdtemp()) / "telemetry_tracker.sqlite3", update_service=update_service)

        with TestClient(app) as client:
            response = client.post("/api/app/update/check", json={"force": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "update_available")
        self.assertEqual(update_service.check_calls, [True])

    def test_update_token_endpoint_is_removed_for_public_releases(self):
        update_service = FakeUpdateService()
        app = create_app(db_path=Path(tempfile.mkdtemp()) / "telemetry_tracker.sqlite3", update_service=update_service)

        with TestClient(app) as client:
            get_response = client.get("/api/app/update/token")
            post_response = client.post("/api/app/update/token", json={"token": "fake-token"})
            delete_response = client.delete("/api/app/update/token")

        self.assertEqual(get_response.status_code, 404)
        self.assertEqual(post_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)

    def test_export_defaults_endpoint_uses_app_data_exports_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_paths = _test_runtime_paths(tmp)
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3", runtime_paths=runtime_paths)
            store = app.state.store
            session_id = store.create_session(label="Export defaults")
            raw_packet = _race_packet(1)
            _insert_samples(store, session_id, [raw_packet])

            with TestClient(app) as client:
                response = client.get("/api/telemetry/export-defaults")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(Path(payload["output_dir"]), runtime_paths.exports_dir)
            self.assertNotIn("forza-telemetry-tracker-exporter-spec", payload["output_dir"])
            self.assertIn("forza-telemetry-tracker", payload["filename_prefix"])
            self.assertEqual(payload["estimate"]["raw_packet_count"], 1)
            self.assertEqual(payload["estimate"]["curated_sample_count"], 1)
            self.assertEqual(payload["estimate"]["session_count"], 1)

    def test_export_job_create_requires_custom_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_paths = _test_runtime_paths(tmp)
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3", runtime_paths=runtime_paths)
            with TestClient(app) as client:
                response = client.post(
                    "/api/telemetry/export-jobs",
                    json={"kind": "raw_csv"},
                )

            self.assertEqual(response.status_code, 400)
            self.assertIn("X-Forza-Telemetry-Export", response.json()["detail"])

    def test_export_job_writes_raw_csv_and_reports_completed_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_paths = _test_runtime_paths(tmp)
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3", runtime_paths=runtime_paths)
            store = app.state.store
            session_id = store.create_session(label="Raw CSV export")
            _insert_samples(store, session_id, [_race_packet(1), _race_packet(2)])

            with TestClient(app) as client:
                response = client.post(
                    "/api/telemetry/export-jobs",
                    headers={"X-Forza-Telemetry-Export": "1"},
                    json={"kind": "raw_csv"},
                )
                self.assertEqual(response.status_code, 200)
                created = response.json()["job"]
                job = _wait_for_export_job(
                    client,
                    created["id"],
                    lambda candidate: candidate["status"] == "completed",
                )

            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["kind"], "raw_csv")
            self.assertEqual(Path(job["output_dir"]), runtime_paths.exports_dir)
            self.assertEqual(len(job["output_files"]), 1)
            output_file = job["output_files"][0]
            self.assertTrue(Path(output_file["path"]).is_file())
            self.assertEqual(output_file["filename"], Path(output_file["path"]).name)
            self.assertGreater(output_file["size_bytes"], 0)
            self.assertEqual(job["total_size_bytes"], output_file["size_bytes"])
            self.assertEqual(job["row_count"], 2)
            self.assertIsNotNone(job["started_at_ms"])
            self.assertIsInstance(job["duration_ms"], int)
            self.assertGreaterEqual(job["duration_ms"], 0)

    def test_export_job_empty_database_fails_without_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_paths = _test_runtime_paths(tmp)
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3", runtime_paths=runtime_paths)
            with TestClient(app) as client:
                response = client.post(
                    "/api/telemetry/export-jobs",
                    headers={"X-Forza-Telemetry-Export": "1"},
                    json={"kind": "curated_csv"},
                )
                self.assertEqual(response.status_code, 200)
                job_id = response.json()["job"]["id"]
                job = _wait_for_export_job(
                    client,
                    job_id,
                    lambda candidate: candidate["status"] == "failed",
                )

            self.assertEqual(job["status"], "failed")
            self.assertIn("No recorded telemetry", job["error"])
            self.assertEqual(job["output_files"], [])
            self.assertEqual(job["total_size_bytes"], 0)

    def test_export_job_accepts_camel_case_request_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_paths = _test_runtime_paths(tmp)
            output_dir = Path(tmp) / "custom-exports"
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3", runtime_paths=runtime_paths)
            store = app.state.store
            session_id = store.create_session(label="Camel case export")
            _insert_samples(store, session_id, [_race_packet(1)])

            with TestClient(app) as client:
                response = client.post(
                    "/api/telemetry/export-jobs",
                    headers={"X-Forza-Telemetry-Export": "1"},
                    json={
                        "kind": "raw_csv",
                        "outputDir": str(output_dir),
                        "filenamePrefix": "camel-prefix",
                    },
                )
                self.assertEqual(response.status_code, 200)
                created = response.json()["job"]
                self.assertEqual(created["output_dir"], str(output_dir))
                self.assertEqual(created["filename_prefix"], "camel-prefix")
                job = _wait_for_export_job(
                    client,
                    created["id"],
                    lambda candidate: candidate["status"] == "completed",
                )

            self.assertEqual(Path(job["output_dir"]), output_dir)
            self.assertEqual(job["filename_prefix"], "camel-prefix")
            self.assertTrue(job["output_files"][0]["filename"].startswith("camel-prefix-raw-"))

    def test_export_job_cancel_sets_cancelled_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_paths = _test_runtime_paths(tmp)
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3", runtime_paths=runtime_paths)
            session_id = app.state.store.create_session(label="Cancelled export")
            _insert_samples(app.state.store, session_id, [_race_packet(1)])
            export_started = threading.Event()

            def cancellable_export(db_path, kind, output_dir, filename_prefix=None, *, should_cancel=None, timestamp_ms=None):
                export_started.set()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if should_cancel is not None and should_cancel():
                        raise InterruptedError("Telemetry export cancelled")
                    time.sleep(0.02)
                raise AssertionError("export was not cancelled")

            with patch("telemetry_tracker.app.export_telemetry", side_effect=cancellable_export):
                with TestClient(app) as client:
                    response = client.post(
                        "/api/telemetry/export-jobs",
                        headers={"X-Forza-Telemetry-Export": "1"},
                        json={"kind": "raw_csv"},
                    )
                    self.assertEqual(response.status_code, 200)
                    job_id = response.json()["job"]["id"]
                    self.assertTrue(export_started.wait(timeout=5))
                    running = _wait_for_export_job(
                        client,
                        job_id,
                        lambda candidate: candidate["status"] == "running",
                    )
                    cancel_response = client.post(f"/api/telemetry/export-jobs/{job_id}/cancel")
                    cancelled = _wait_for_export_job(
                        client,
                        job_id,
                        lambda candidate: candidate["status"] == "cancelled",
                    )

            self.assertEqual(running["can_cancel"], True)
            self.assertEqual(cancel_response.status_code, 200)
            self.assertEqual(cancel_response.json()["job"]["status"], "cancelling")
            self.assertEqual(cancelled["status"], "cancelled")
            self.assertEqual(cancelled["output_files"], [])

    def test_export_jobs_serialize_concurrent_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_paths = _test_runtime_paths(tmp)
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3", runtime_paths=runtime_paths)
            session_id = app.state.store.create_session(label="Serialized export")
            _insert_samples(app.state.store, session_id, [_race_packet(1)])
            first_started = threading.Event()
            release_first = threading.Event()
            calls = []

            def blocking_export(db_path, kind, output_dir, filename_prefix=None, *, should_cancel=None, timestamp_ms=None):
                call_index = len(calls) + 1
                calls.append(call_index)
                output_path = Path(output_dir) / f"serialized-{call_index}.csv"
                if call_index == 1:
                    first_started.set()
                    self.assertTrue(release_first.wait(timeout=5))
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text("sequence\n1\n", encoding="utf-8")
                from telemetry_tracker.export import ExportedFile, TelemetryExportKind, TelemetryExportResult

                exported = ExportedFile(output_path, output_path.name, output_path.stat().st_size)
                return TelemetryExportResult(TelemetryExportKind(kind), (exported,), exported.size_bytes, 1)

            with patch("telemetry_tracker.app.export_telemetry", side_effect=blocking_export):
                with TestClient(app) as client:
                    first = client.post(
                        "/api/telemetry/export-jobs",
                        headers={"X-Forza-Telemetry-Export": "1"},
                        json={"kind": "raw_csv"},
                    ).json()["job"]
                    self.assertTrue(first_started.wait(timeout=5))
                    running_first = _wait_for_export_job(
                        client,
                        first["id"],
                        lambda candidate: candidate["status"] == "running",
                    )
                    second = client.post(
                        "/api/telemetry/export-jobs",
                        headers={"X-Forza-Telemetry-Export": "1"},
                        json={"kind": "raw_csv"},
                    ).json()["job"]
                    queued_second = _wait_for_export_job(
                        client,
                        second["id"],
                        lambda candidate: candidate["status"] == "queued",
                    )
                    self.assertEqual(running_first["status"], "running")
                    self.assertEqual(queued_second["status"], "queued")
                    release_first.set()
                    completed_first = _wait_for_export_job(
                        client,
                        first["id"],
                        lambda candidate: candidate["status"] == "completed",
                    )
                    running_or_completed_second = _wait_for_export_job(
                        client,
                        second["id"],
                        lambda candidate: candidate["status"] in {"running", "completed"},
                    )
                    completed_second = _wait_for_export_job(
                        client,
                        second["id"],
                        lambda candidate: candidate["status"] == "completed",
                    )

            self.assertEqual(completed_first["status"], "completed")
            self.assertIn(running_or_completed_second["status"], {"running", "completed"})
            self.assertEqual(completed_second["status"], "completed")
            self.assertEqual(calls, [1, 2])

    def test_status_endpoint_reports_seeded_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            with TestClient(app) as client:
                response = client.get("/api/status")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["listener"]["udp_host"], "127.0.0.1")
            self.assertEqual(payload["listener"]["udp_port"], 5400)
            self.assertEqual(payload["listener"]["state"], "waiting")
            self.assertEqual(payload["settings"]["capture_mode"], "auto")
            self.assertEqual(payload["settings"]["preferred_overlay"], "issues")
            self.assertEqual(payload["settings"]["unit_system"], "imperial")

    def test_listener_restart_endpoint_stops_starts_and_returns_fresh_status(self):
        class FakeListener:
            def __init__(self):
                self.calls = []

            async def stop(self):
                self.calls.append("stop")

            async def start(self):
                self.calls.append("start")

            def status(self):
                return {
                    "state": "waiting",
                    "udp_host": "127.0.0.1",
                    "udp_port": 5400,
                    "packets_received": 8,
                    "packets_recorded": 3,
                    "message": "waiting for telemetry",
                }

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            fake_listener = FakeListener()
            app.state.udp_listener = fake_listener
            with TestClient(app) as client:
                response = client.post("/api/listener/restart")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(fake_listener.calls, ["stop", "start"])
            payload = response.json()
            self.assertEqual(payload["state"], "waiting")
            self.assertEqual(payload["udp_port"], 5400)
            self.assertEqual(payload["packets_received"], 8)

    def test_listener_restart_endpoint_can_start_inactive_listener(self):
        class ColdListener:
            def __init__(self):
                self.running = False

            async def stop(self):
                self.running = False

            async def start(self):
                self.running = True

            def status(self):
                return {
                    "state": "waiting",
                    "udp_host": "127.0.0.1",
                    "udp_port": 5400,
                    "packets_received": 0,
                    "message": "waiting for telemetry" if self.running else "listener not started",
                }

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            app.state.udp_listener = ColdListener()
            with TestClient(app) as client:
                response = client.post("/api/listener/restart")
                status = client.get("/api/status")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["state"], "waiting")
            self.assertEqual(payload["udp_host"], "127.0.0.1")
            self.assertEqual(payload["udp_port"], 5400)
            self.assertEqual(payload["message"], "waiting for telemetry")
            self.assertEqual(status.json()["listener"]["state"], "waiting")
            self.assertEqual(status.json()["listener"]["message"], "waiting for telemetry")

    def test_listener_restart_endpoint_reports_start_failures(self):
        class FailingListener:
            async def stop(self):
                return None

            async def start(self):
                raise OSError("address already in use")

            def status(self):
                return {
                    "state": "error",
                    "udp_host": "127.0.0.1",
                    "udp_port": 5400,
                    "packets_received": 0,
                    "message": "failed to bind UDP listener",
                }

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            app.state.udp_listener = FailingListener()
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post("/api/listener/restart")

            self.assertEqual(response.status_code, 500)
            self.assertIn("Failed to restart UDP listener", response.json()["detail"])

    def test_listener_restart_endpoint_reports_stop_failures(self):
        class StopFailingListener:
            async def stop(self):
                raise RuntimeError("transport close failed")

            async def start(self):
                raise AssertionError("start should not run after stop failure")

            def status(self):
                return {
                    "state": "error",
                    "udp_host": "127.0.0.1",
                    "udp_port": 5400,
                    "packets_received": 0,
                    "message": "transport close failed",
                }

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            app.state.udp_listener = StopFailingListener()
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post("/api/listener/restart")

            self.assertEqual(response.status_code, 500)
            self.assertIn("transport close failed", response.json()["detail"])

    def test_listener_restart_endpoint_reports_missing_listener(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            app.state.udp_listener = None
            with TestClient(app) as client:
                response = client.post("/api/listener/restart")

            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["detail"], "UDP listener is unavailable")

    def test_settings_endpoint_updates_unit_system_and_status_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            with TestClient(app) as client:
                response = client.patch("/api/settings", json={"unit_system": "metric"})
                status = client.get("/api/status")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["unit_system"], "metric")
            self.assertEqual(status.json()["settings"]["unit_system"], "metric")
            with app.state.store.connect() as con:
                row = con.execute("SELECT unit_system FROM user_settings LIMIT 1").fetchone()
            self.assertEqual(row["unit_system"], "metric")

    def test_settings_endpoint_updates_preferred_overlay_and_status_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            with TestClient(app) as client:
                response = client.patch("/api/settings", json={"preferred_overlay": "speed"})
                status = client.get("/api/status")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["preferred_overlay"], "speed")
            self.assertEqual(status.json()["settings"]["preferred_overlay"], "speed")
            with app.state.store.connect() as con:
                row = con.execute("SELECT preferred_overlay FROM user_settings LIMIT 1").fetchone()
            self.assertEqual(row["preferred_overlay"], "speed")

    def test_settings_endpoint_rejects_bad_unit_system(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            with TestClient(app) as client:
                response = client.patch("/api/settings", json={"unit_system": "knots"})

            self.assertEqual(response.status_code, 400)
            self.assertIn("unit_system", response.json()["detail"])

    def test_settings_endpoint_rejects_bad_preferred_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            with TestClient(app) as client:
                response = client.patch("/api/settings", json={"preferred_overlay": "map"})

            self.assertEqual(response.status_code, 400)
            self.assertIn("preferred_overlay", response.json()["detail"])
            with app.state.store.connect() as con:
                row = con.execute("SELECT preferred_overlay FROM user_settings LIMIT 1").fetchone()
            self.assertEqual(row["preferred_overlay"], "issues")

    def test_live_recent_endpoint_returns_empty_without_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            with TestClient(app) as client:
                response = client.get("/api/live/recent")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"session_id": None, "samples": [], "car": None})

    def test_live_recent_endpoint_returns_latest_session_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            older_session_id = store.create_session(label="Older replay")
            latest_session_id = store.create_session(label="Latest replay")
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
            with store.connect() as con:
                con.execute(
                    "UPDATE sessions SET started_at_ms = ? WHERE id = ?",
                    (1_000, older_session_id),
                )
                con.execute(
                    "UPDATE sessions SET started_at_ms = ? WHERE id = ?",
                    (2_000, latest_session_id),
                )
            _insert_samples(
                store,
                older_session_id,
                [encode_packet_for_test({"TimestampMS": 0, "PositionX": -10.0, "Speed": 5.0})],
            )
            latest_samples = _insert_samples(
                store,
                latest_session_id,
                [
                    encode_packet_for_test(
                        {
                            "TimestampMS": 16,
                            "PositionX": 1.0,
                            "Speed": 10.0,
                            "CarOrdinal": 1229,
                            "CarClass": 6,
                            "CarPerformanceIndex": 998,
                            "DrivetrainType": 1,
                            "NumCylinders": 3,
                            "CarGroup": 26,
                            "Power": 300_000.0,
                            "Torque": 350.0,
                            "Fuel": 0.5,
                        }
                    ),
                    encode_packet_for_test(
                        {
                            "TimestampMS": 32,
                            "PositionX": 2.0,
                            "Speed": 11.0,
                            "CarOrdinal": 1229,
                            "CarClass": 6,
                            "CarPerformanceIndex": 998,
                            "DrivetrainType": 1,
                            "NumCylinders": 3,
                            "CarGroup": 26,
                            "Power": 325_000.0,
                            "Torque": 375.0,
                            "Fuel": 0.625,
                        }
                    ),
                    encode_packet_for_test(
                        {
                            "TimestampMS": 48,
                            "PositionX": 3.0,
                            "Speed": 12.0,
                            "CarOrdinal": 1229,
                            "CarClass": 6,
                            "CarPerformanceIndex": 998,
                            "DrivetrainType": 1,
                            "NumCylinders": 3,
                            "CarGroup": 26,
                            "Power": 350_000.0,
                            "Torque": 400.0,
                            "Fuel": 0.75,
                        }
                    ),
                ],
                sequence_offset=10,
            )

            with TestClient(app) as client:
                response = client.get("/api/live/recent?limit=2")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["session_id"], latest_session_id)
            self.assertEqual(payload["samples"], latest_samples[-2:])
            self.assertEqual(payload["samples"][-1]["power_w"], 350_000.0)
            self.assertEqual(payload["samples"][-1]["torque_nm"], 400.0)
            self.assertEqual(payload["samples"][-1]["fuel"], 0.75)
            self.assertEqual(payload["car"]["ordinal"], 1229)
            self.assertEqual(payload["car"]["name"], "Mazda Furai")
            self.assertEqual(payload["car"]["year"], 2008)
            self.assertEqual(payload["car"]["class_label"], "R")
            self.assertEqual(payload["car"]["performance_index"], 998)
            self.assertEqual(payload["car"]["drivetrain_label"], "RWD")
            self.assertEqual(payload["car"]["details"]["num_cylinders"], 3)
            self.assertEqual(payload["car"]["details"]["car_group_label"], "Extreme Track Toys")
            self.assertEqual(payload["car"]["details"]["fuel"], 0.75)

    def test_live_recent_endpoint_rejects_non_positive_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            with TestClient(app) as client:
                for limit in (0, -1):
                    with self.subTest(limit=limit):
                        response = client.get(f"/api/live/recent?limit={limit}")

                        self.assertEqual(response.status_code, 400)
                        self.assertIn("limit must be positive", response.json()["detail"])

    def test_stats_endpoint_returns_store_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Stats session")
            store.attach_session_car_identity(
                session_id,
                {
                    "car_identity_key": "mazda-furai-r-998-rwd",
                    "car_name": "Mazda Furai",
                    "car_class_id": 6,
                    "car_class_label": "R",
                    "car_performance_index": 998,
                    "drivetrain_id": 1,
                    "drivetrain_label": "RWD",
                },
            )
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="confident",
            )
            raw_packets = [
                _race_packet(1, CurrentLap=0.0, CurrentRaceTime=0.0),
                _race_packet(2, CurrentLap=61.0, CurrentRaceTime=61.0),
            ]
            decoded_packets = [decode_packet(raw) for raw in raw_packets]
            samples = [
                packet_to_live_fields(decoded, index + 1, index * 16)
                for index, decoded in enumerate(decoded_packets)
            ]
            for sample in samples:
                sample["lap_id"] = lap_id
            store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)
            store.finalize_lap(lap_id, reason="manual_stop", boundary_confidence="confident")
            store.record_lifetime_lap_stats(lap_id)

            with TestClient(app) as client:
                response = client.get("/api/stats")

            self.assertEqual(response.status_code, 200)
            stats = response.json()["stats"]
            self.assertEqual(stats["laps_recorded"], 1)
            self.assertEqual(stats["sessions_created"], 1)
            self.assertEqual(stats["tracks_driven"], 0)
            self.assertEqual(stats["cars_driven"], 1)
            self.assertEqual(stats["max_speed_mps"], 30.0)
            self.assertEqual(stats["time_spent_racing_ms"], 61000)
            self.assertEqual(stats["favourite_car"]["value"], "Mazda Furai")
            self.assertEqual(stats["favourite_pi_class"]["value"], "R")
            self.assertEqual(stats["favoured_drive"]["value"], "RWD")

    def test_replay_upload_recording_mode_does_not_count_lifetime_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            raw_packets = b"".join(
                [
                    _race_packet(1, CurrentLap=0.0, CurrentRaceTime=0.0),
                    _race_packet(2, CurrentLap=61.0, CurrentRaceTime=61.0),
                ]
            )

            with TestClient(app) as client:
                response = client.post(
                    "/api/replay/upload",
                    files={"file": ("import.raw", raw_packets, "application/octet-stream")},
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertGreater(payload["packet_count"], 0)
                self.assertTrue(payload["session_ids"])
                session_id = payload["session_ids"][0]
                store = app.state.store
                self.assertIsNotNone(store.session(session_id))
                self.assertGreater(len(store.latest_packet_bytes(session_id, 10)), 0)
                self.assertGreater(len(store.latest_samples(session_id, 10)), 0)
                stats_response = client.get("/api/stats")

            self.assertEqual(stats_response.status_code, 200)
            stats = stats_response.json()["stats"]
            self.assertEqual(stats["laps_recorded"], 0)
            self.assertEqual(stats["sessions_created"], 0)
            self.assertEqual(stats["tracks_driven"], 0)
            self.assertEqual(stats["cars_driven"], 0)

    def test_root_serves_frontend_shell_when_dist_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "dist"
            dist.mkdir()
            (dist / "index.html").write_text("<h1>Frontend shell</h1>", encoding="utf-8")
            app = create_app(db_path=root / "telemetry_tracker.sqlite3", frontend_dist=dist)
            with TestClient(app) as client:
                response = client.get("/")

            self.assertEqual(response.status_code, 200)
            self.assertIn("Frontend shell", response.text)

    def test_root_returns_404_when_dist_exists_without_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "dist"
            dist.mkdir()
            app = create_app(db_path=root / "telemetry_tracker.sqlite3", frontend_dist=dist)
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/")

            self.assertNotEqual(response.status_code, 500)
            self.assertEqual(response.status_code, 404)

    def test_api_route_still_works_when_frontend_dist_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "dist"
            dist.mkdir()
            (dist / "index.html").write_text("<h1>Frontend shell</h1>", encoding="utf-8")
            app = create_app(db_path=root / "telemetry_tracker.sqlite3", frontend_dist=dist)
            with TestClient(app) as client:
                response = client.get("/api/status")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["listener"]["state"], "waiting")
            self.assertEqual(payload["settings"]["capture_mode"], "auto")
            self.assertEqual(payload["settings"]["unit_system"], "imperial")

    def test_events_route_still_streams_when_frontend_dist_exists(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                dist = root / "dist"
                dist.mkdir()
                (dist / "index.html").write_text("<h1>Frontend shell</h1>", encoding="utf-8")
                app = create_app(db_path=root / "telemetry_tracker.sqlite3", frontend_dist=dist)
                route = next(route for route in app.routes if getattr(route, "path", None) == "/events")
                response = await route.endpoint()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.media_type, "text/event-stream")

        asyncio.run(scenario())

    def test_assets_route_serves_concrete_frontend_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "dist"
            assets = dist / "assets"
            assets.mkdir(parents=True)
            (dist / "index.html").write_text("<h1>Frontend shell</h1>", encoding="utf-8")
            (assets / "app.js").write_text("console.log('asset loaded');", encoding="utf-8")
            app = create_app(db_path=root / "telemetry_tracker.sqlite3", frontend_dist=dist)
            with TestClient(app) as client:
                response = client.get("/assets/app.js")

            self.assertEqual(response.status_code, 200)
            self.assertIn("asset loaded", response.text)

    def test_create_app_uses_runtime_paths_for_database_and_frontend(self):
        from telemetry_tracker.app_paths import default_desktop_paths
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resources = root / "resources"
            dist = resources / "frontend-dist"
            dist.mkdir(parents=True)
            (dist / "index.html").write_text("<h1>Desktop shell</h1>", encoding="utf-8")
            paths = default_desktop_paths(resource_base=resources, user_data_base=root / "data")
            app = create_app(runtime_paths=paths)
            with TestClient(app) as client:
                response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Desktop shell", response.text)
            self.assertEqual(app.state.runtime_paths, paths)
            self.assertTrue(paths.database.exists())

    def test_replay_endpoint_persists_raw_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "raw.bin"
            raw_path.write_bytes(
                b"".join(
                    encode_packet_for_test({"TimestampMS": index * 16, "PositionX": float(index)})
                    for index in range(8)
                )
            )
            registry = LocalFileSelectionRegistry()
            selection = registry.register_files([raw_path])
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )
            with TestClient(app) as client:
                response = client.post(
                    "/api/replay",
                    json={"selection_id": selection["selection_id"], "label": "API replay"},
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["packet_count"], 8)
            self.assertTrue(payload["session_id"])

    def test_replay_endpoint_returns_400_for_unknown_selection_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            with TestClient(app) as client:
                response = client.post("/api/replay", json={"selection_id": "unknownselectionid"})

            self.assertEqual(response.status_code, 400)
            self.assertIn("unknown or expired local file selection", response.json()["detail"])

    def test_replay_endpoint_rejects_legacy_raw_path_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "raw.bin"
            raw_path.write_bytes(encode_packet_for_test({"TimestampMS": 16, "PositionX": 1.0}))
            app = create_app(db_path=root / "telemetry_tracker.sqlite3")

            with TestClient(app) as client:
                response = client.post("/api/replay", json={"raw_path": str(raw_path), "label": "Legacy replay"})

            self.assertEqual(response.status_code, 400)
            self.assertIn("selection_id is required", response.json()["detail"])

    def test_replay_endpoint_returns_400_for_folder_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected_file = root / "capture.bin"
            selected_file.write_bytes(encode_packet_for_test({"TimestampMS": 16, "PositionX": 1.0}))
            registry = LocalFileSelectionRegistry()
            selection = registry.register_folder(root)
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )
            with TestClient(app) as client:
                response = client.post("/api/replay", json={"selection_id": selection["selection_id"]})

            self.assertEqual(response.status_code, 400)
            self.assertIn("replay requires a single-file local selection", response.json()["detail"])

    def test_replay_endpoint_returns_400_for_empty_selection_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            with TestClient(app) as client:
                response = client.post("/api/replay", json={"selection_id": ""})

            self.assertEqual(response.status_code, 400)
            self.assertIn("selection_id is required", response.json()["detail"])

    def test_replay_endpoint_returns_400_for_empty_raw_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "empty.bin"
            raw_path.write_bytes(b"")
            registry = LocalFileSelectionRegistry()
            selection = registry.register_files([raw_path])
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )
            with TestClient(app) as client:
                response = client.post("/api/replay", json={"selection_id": selection["selection_id"]})

            self.assertEqual(response.status_code, 400)
            self.assertIn("raw file contains no packets", response.json()["detail"])

    def test_replay_endpoint_returns_400_for_partial_raw_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "partial.bin"
            raw_path.write_bytes(b"partial")
            registry = LocalFileSelectionRegistry()
            selection = registry.register_files([raw_path])
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )
            with TestClient(app) as client:
                response = client.post("/api/replay", json={"selection_id": selection["selection_id"]})

            self.assertEqual(response.status_code, 400)
            self.assertIn("multiple of", response.json()["detail"])

    def test_replay_endpoint_returns_400_for_raw_read_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "raw.bin"
            raw_path.write_bytes(encode_packet_for_test({"TimestampMS": 16, "PositionX": 1.0}))
            registry = LocalFileSelectionRegistry()
            selection = registry.register_files([raw_path])
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )
            with patch(
                "telemetry_tracker.app.replay_raw_file",
                new=AsyncMock(side_effect=OSError("permission denied")),
            ):
                with TestClient(app) as client:
                    response = client.post("/api/replay", json={"selection_id": selection["selection_id"]})

            self.assertEqual(response.status_code, 400)
            self.assertIn("failed to read selected raw telemetry file", response.json()["detail"])
            self.assertNotIn("permission denied", response.json()["detail"])

    def test_events_endpoint_returns_streaming_response(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                route = next(route for route in app.routes if getattr(route, "path", None) == "/events")
                response = await route.endpoint()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.media_type, "text/event-stream")

        asyncio.run(scenario())

    def test_auto_recording_publishes_capture_state_before_first_live_race_sample(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                bus = app.state.bus
                events = bus.subscribe()
                try:
                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(1, CurrentRaceTime=1.0),
                        received_at_ms=1_000,
                    )
                    _drain_events(events)

                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(
                            2,
                            CurrentRaceTime=1.5,
                            Power=275_000.0,
                            Torque=410.0,
                            Boost=1.1,
                            AccelerationX=0.5,
                            WheelOnRumbleStripFrontLeft=1,
                        ),
                        received_at_ms=1_016,
                    )

                    recorded_events = _drain_events(events)
                finally:
                    bus.unsubscribe(events)

            event_types = [event["type"] for event in recorded_events]
            recording_capture_index = next(
                index
                for index, event in enumerate(recorded_events)
                if event["type"] == "capture" and event["recording"]["active"]
            )
            first_live_index = event_types.index("live_sample")
            live_events = [event for event in recorded_events if event["type"] == "live_sample"]

            self.assertLess(recording_capture_index, first_live_index)
            self.assertEqual(len(live_events), 1)
            self.assertEqual(live_events[0]["sample"]["game_timestamp_ms"], 32)
            self.assertEqual(live_events[0]["sample"]["power_w"], 275_000.0)
            self.assertEqual(live_events[0]["sample"]["torque_nm"], 410.0)
            self.assertAlmostEqual(live_events[0]["sample"]["boost_bar"], 1.1, places=5)
            self.assertAlmostEqual(live_events[0]["sample"]["acceleration_x"], 0.5)
            self.assertEqual(live_events[0]["sample"]["wheel_on_rumble_strip_front_left"], 1)
            self.assertEqual(live_events[0]["car"]["class_label"], "S1")
            self.assertEqual(live_events[0]["car"]["performance_index"], 800)
            self.assertEqual(live_events[0]["car"]["drivetrain_label"], "AWD")

        asyncio.run(scenario())

    def test_auto_recording_publishes_live_reset_when_race_on_starts_from_idle(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                bus = app.state.bus
                events = bus.subscribe()
                try:
                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(
                            1,
                            IsRaceOn=0,
                            CurrentRaceTime=0.0,
                            CurrentLap=0.0,
                            LapNumber=0,
                        ),
                        received_at_ms=1_000,
                    )
                    _drain_events(events)

                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(10, CurrentLap=0.1, CurrentRaceTime=0.1),
                        received_at_ms=1_016,
                    )
                    recorded_events = _drain_events(events)
                finally:
                    bus.unsubscribe(events)

            event_types = [event["type"] for event in recorded_events]
            self.assertIn("live_reset", event_types)
            self.assertIn("live_sample", event_types)
            self.assertLess(event_types.index("live_reset"), event_types.index("live_sample"))
            reset = next(event for event in recorded_events if event["type"] == "live_reset")
            self.assertEqual(reset["reason"], "race_on_started")

        asyncio.run(scenario())

    def test_auto_recording_does_not_publish_non_race_samples_or_reset_same_resume(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                bus = app.state.bus
                events = bus.subscribe()
                try:
                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(1, CurrentRaceTime=0.1),
                        received_at_ms=1_000,
                    )
                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(10, CurrentLap=1.0, CurrentRaceTime=1.0, PositionX=10.0, PositionZ=20.0),
                        received_at_ms=1_016,
                    )
                    _drain_events(events)

                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(
                            20,
                            IsRaceOn=0,
                            CurrentRaceTime=0.0,
                            CurrentLap=0.0,
                            LapNumber=0,
                            PositionX=0.0,
                            PositionZ=0.0,
                        ),
                        received_at_ms=1_032,
                    )
                    non_race_events = _drain_events(events)

                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(30, CurrentLap=1.1, CurrentRaceTime=1.1, PositionX=10.1, PositionZ=20.1),
                        received_at_ms=1_048,
                    )
                    resumed_events = _drain_events(events)
                    await app.state.ingest.flush()
                    with app.state.store.connect() as con:
                        null_sample_count = con.execute(
                            "SELECT COUNT(*) FROM lap_samples WHERE lap_id IS NULL"
                        ).fetchone()[0]
                        null_packet_count = con.execute(
                            "SELECT COUNT(*) FROM packet_blobs WHERE lap_id IS NULL"
                        ).fetchone()[0]
                finally:
                    bus.unsubscribe(events)

            self.assertEqual(null_sample_count, 0)
            self.assertEqual(null_packet_count, 0)
            self.assertNotIn("live_sample", [event["type"] for event in non_race_events])
            self.assertNotIn("live_reset", [event["type"] for event in resumed_events])
            live_events = [event for event in resumed_events if event["type"] == "live_sample"]
            self.assertEqual(len(live_events), 1)
            self.assertTrue(live_events[0]["sample"]["is_race_on"])
            self.assertEqual(live_events[0]["sample"]["lap_action"], "none")

        asyncio.run(scenario())

    def test_auto_recording_resume_split_marks_first_new_race_sample(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                bus = app.state.bus
                events = bus.subscribe()
                try:
                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(1, CurrentRaceTime=0.1),
                        received_at_ms=1_000,
                    )
                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(10, CurrentLap=8.0, CurrentRaceTime=8.0, PositionX=0.0, PositionZ=0.0),
                        received_at_ms=1_016,
                    )
                    _drain_events(events)

                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(20, IsRaceOn=0, CurrentLap=0.0, CurrentRaceTime=0.0, LapNumber=0),
                        received_at_ms=1_032,
                    )
                    _drain_events(events)

                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(
                            30,
                            CurrentLap=8.5,
                            CurrentRaceTime=8.5,
                            PositionX=1_500.0,
                            PositionZ=0.0,
                        ),
                        received_at_ms=1_048,
                    )
                    resumed_events = _drain_events(events)
                finally:
                    bus.unsubscribe(events)

            event_types = [event["type"] for event in resumed_events]
            self.assertIn("live_reset", event_types)
            self.assertIn("live_sample", event_types)
            self.assertLess(event_types.index("live_reset"), event_types.index("live_sample"))
            reset = next(event for event in resumed_events if event["type"] == "live_reset")
            self.assertEqual(reset["reason"], "race_resume_split")
            self.assertEqual(reset["uncertainty"], "teleport")
            live_events = [event for event in resumed_events if event["type"] == "live_sample"]
            self.assertEqual(len(live_events), 1)
            self.assertEqual(live_events[0]["sample"]["lap_action"], "finalize_and_start")
            self.assertEqual(live_events[0]["sample"]["uncertainty"], "teleport")
            self.assertTrue(live_events[0]["sample"]["is_race_on"])

        asyncio.run(scenario())

    def test_auto_recording_direct_teleport_publishes_live_reset_and_starts_new_trace(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                bus = app.state.bus
                events = bus.subscribe()
                try:
                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(1, CurrentLap=1.0, CurrentRaceTime=1.0, PositionX=0.0, PositionZ=0.0),
                        received_at_ms=1_000,
                    )
                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(2, CurrentLap=2.0, CurrentRaceTime=2.0, PositionX=10.0, PositionZ=0.0),
                        received_at_ms=1_016,
                    )
                    _drain_events(events)

                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(3, CurrentLap=2.5, CurrentRaceTime=2.5, PositionX=1_500.0, PositionZ=0.0),
                        received_at_ms=1_032,
                    )
                    recorded_events = _drain_events(events)
                finally:
                    bus.unsubscribe(events)

            event_types = [event["type"] for event in recorded_events]
            self.assertIn("live_reset", event_types)
            self.assertIn("live_sample", event_types)
            self.assertLess(event_types.index("live_reset"), event_types.index("live_sample"))
            reset = next(event for event in recorded_events if event["type"] == "live_reset")
            self.assertEqual(reset["reason"], "telemetry_gap")
            self.assertEqual(reset["uncertainty"], "teleport")
            live_events = [event for event in recorded_events if event["type"] == "live_sample"]
            self.assertEqual(len(live_events), 1)
            self.assertEqual(live_events[0]["sample"]["lap_action"], "finalize_and_start")
            self.assertEqual(live_events[0]["sample"]["uncertainty"], "teleport")
            self.assertTrue(live_events[0]["sample"]["is_race_on"])

        asyncio.run(scenario())

    def test_capture_event_publishes_when_latest_packet_type_changes(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                bus = app.state.bus
                events = bus.subscribe()
                try:
                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(1, CurrentRaceTime=0.1),
                        received_at_ms=1_000,
                    )
                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(2, CurrentRaceTime=0.2),
                        received_at_ms=1_016,
                    )
                    _drain_events(events)

                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(
                            3,
                            IsRaceOn=0,
                            CurrentRaceTime=0.0,
                            CurrentLap=0.0,
                            LapNumber=0,
                        ),
                        received_at_ms=1_032,
                    )
                    recorded_events = _drain_events(events)
                finally:
                    bus.unsubscribe(events)

            packet_type_events = [
                event
                for event in recorded_events
                if event["type"] == "capture"
                and event["packet_receipt"]["last_packet_type"] == "non_race"
            ]
            self.assertEqual(len(packet_type_events), 1)
            self.assertFalse(packet_type_events[0]["packet_receipt"]["last_is_race_on"])
            self.assertTrue(packet_type_events[0]["recording"]["active"])

        asyncio.run(scenario())

    def test_manual_recording_does_not_publish_prebuffered_idle_packets_as_live_samples(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                bus = app.state.bus
                events = bus.subscribe()
                try:
                    await app.state.capture_pipeline.set_mode("manual")
                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(1, IsRaceOn=0, CurrentRaceTime=0.0),
                        received_at_ms=1_000,
                    )
                    _drain_events(events)

                    await app.state.capture_pipeline.start_manual()
                    start_events = _drain_events(events)

                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(2, CurrentRaceTime=1.0),
                        received_at_ms=1_016,
                    )
                    post_start_events = _drain_events(events)
                finally:
                    bus.unsubscribe(events)

            self.assertTrue(
                any(
                    event["type"] == "capture" and event["recording"]["active"]
                    for event in start_events
                )
            )
            self.assertNotIn("live_sample", [event["type"] for event in start_events])

            live_events = [event for event in post_start_events if event["type"] == "live_sample"]
            self.assertEqual(len(live_events), 1)
            self.assertEqual(live_events[0]["sample"]["game_timestamp_ms"], 32)

        asyncio.run(scenario())

    def test_auto_recording_creates_active_session_when_race_packets_arrive(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                store = app.state.store

                await app.state.capture_pipeline.process_live_packet(
                    _race_packet(1, CurrentRaceTime=1.0),
                    received_at_ms=1_000,
                )
                self.assertIsNone(store.active_session())

                await app.state.capture_pipeline.process_live_packet(
                    _race_packet(2, CurrentRaceTime=1.5),
                    received_at_ms=1_016,
                )
                await app.state.capture_pipeline.ingest.flush()

                active = store.active_session()
                self.assertIsNotNone(active)
                self.assertEqual(active["label"], "Unknown car S1 800 AWD Session")
                self.assertEqual(active["status"], "active")
                self.assertGreaterEqual(store.count_packets(active["id"]), 1)

        asyncio.run(scenario())

    def test_auto_recording_appends_to_existing_active_session(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                store = app.state.store
                session_id = store.start_session(label="Existing active")

                await app.state.capture_pipeline.process_live_packet(
                    _race_packet(1, CurrentRaceTime=1.0),
                    received_at_ms=1_000,
                )
                await app.state.capture_pipeline.process_live_packet(
                    _race_packet(2, CurrentRaceTime=1.5),
                    received_at_ms=1_016,
                )
                await app.state.capture_pipeline.ingest.flush()

                self.assertEqual(store.active_session()["id"], session_id)
                self.assertGreaterEqual(store.count_packets(session_id), 1)

        asyncio.run(scenario())

    def test_auto_car_switch_promotes_new_active_session_to_live_events(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                pipeline = app.state.capture_pipeline
                store = app.state.store
                bus = app.state.bus
                events = bus.subscribe()
                try:
                    await pipeline.process_live_packet(
                        _race_packet(1, CarOrdinal=368, CurrentRaceTime=1.0),
                        received_at_ms=1_000,
                    )
                    await pipeline.process_live_packet(
                        _race_packet(2, CarOrdinal=368, CurrentRaceTime=1.5),
                        received_at_ms=1_016,
                    )
                    await pipeline.ingest.flush()
                    _drain_events(events)

                    first_session = store.active_session()
                    self.assertIsNotNone(first_session)

                    await pipeline.process_live_packet(
                        _race_packet(3, CarOrdinal=999, CurrentRaceTime=2.0),
                        received_at_ms=1_032,
                    )
                    await pipeline.ingest.flush()
                    switched_events = _drain_events(events)
                    active = store.active_session()
                finally:
                    bus.unsubscribe(events)

            self.assertIsNotNone(active)
            self.assertNotEqual(active["id"], first_session["id"])
            self.assertEqual(active["car_ordinal"], 999)

            event_types = [event["type"] for event in switched_events]
            self.assertIn("session_finalized", event_types)
            self.assertIn("session_started", event_types)
            self.assertIn("live_reset", event_types)
            self.assertIn("live_sample", event_types)
            self.assertLess(event_types.index("session_started"), event_types.index("live_reset"))
            self.assertLess(event_types.index("live_reset"), event_types.index("live_sample"))

            finalized = next(
                event for event in switched_events if event["type"] == "session_finalized"
            )
            self.assertEqual(finalized["session_id"], first_session["id"])
            self.assertEqual(finalized["reason"], "car_switch")

            started = next(
                event for event in switched_events if event["type"] == "session_started"
            )
            self.assertEqual(started["reason"], "car_switch")
            self.assertEqual(started["session"]["id"], active["id"])
            self.assertEqual(started["session"]["status"], "active")
            self.assertEqual(started["session"]["car_ordinal"], 999)
            self.assertEqual(started["session"]["auto_created_reason"], "car_switch")

            reset = next(event for event in switched_events if event["type"] == "live_reset")
            self.assertEqual(reset["reason"], "car_switch")
            self.assertEqual(reset["session_id"], active["id"])

        asyncio.run(scenario())

    def test_empty_auto_car_switch_session_is_deleted_on_next_switch(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                pipeline = app.state.capture_pipeline
                store = app.state.store
                bus = app.state.bus
                events = bus.subscribe()
                try:
                    await pipeline.process_live_packet(
                        _race_packet(1, CarOrdinal=368, CurrentRaceTime=1.0),
                        received_at_ms=1_000,
                    )
                    await pipeline.process_live_packet(
                        _race_packet(2, CarOrdinal=368, CurrentRaceTime=1.5),
                        received_at_ms=1_016,
                    )
                    await pipeline.ingest.flush()
                    initial_session = store.active_session()
                    _drain_events(events)

                    await pipeline.process_live_packet(
                        _race_packet(3, CarOrdinal=999, CurrentRaceTime=2.0),
                        received_at_ms=1_032,
                    )
                    await pipeline.ingest.flush()
                    car_switch_session = store.active_session()
                    _drain_events(events)

                    await pipeline.process_live_packet(
                        _race_packet(4, CarOrdinal=555, CurrentRaceTime=2.5),
                        received_at_ms=1_048,
                    )
                    await pipeline.ingest.flush()
                    switched_events = _drain_events(events)
                    active = store.active_session()
                    sessions = store.latest_sessions(limit=10)
                    deleted_session = store.session(car_switch_session["id"])
                finally:
                    bus.unsubscribe(events)

            self.assertIsNotNone(initial_session)
            self.assertIsNotNone(car_switch_session)
            self.assertEqual(car_switch_session["auto_created_reason"], "car_switch")
            self.assertIsNotNone(active)
            self.assertEqual(active["car_ordinal"], 555)
            self.assertIsNone(deleted_session)
            self.assertNotIn(car_switch_session["id"], [session["id"] for session in sessions])
            self.assertIn(initial_session["id"], [session["id"] for session in sessions])
            self.assertIn(active["id"], [session["id"] for session in sessions])

            event_types = [event["type"] for event in switched_events]
            self.assertIn("session_deleted", event_types)
            self.assertIn("session_started", event_types)
            self.assertLess(
                event_types.index("session_deleted"),
                event_types.index("session_started"),
            )
            deleted = next(
                event for event in switched_events if event["type"] == "session_deleted"
            )
            self.assertEqual(deleted["session_id"], car_switch_session["id"])
            self.assertEqual(deleted["reason"], "empty_auto_car_switch_session")
            self.assertEqual(deleted["finalize_reason"], "car_switch")

        asyncio.run(scenario())

    def test_auto_car_switch_ignores_unknown_identity_between_same_known_car(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                pipeline = app.state.capture_pipeline
                store = app.state.store
                bus = app.state.bus
                events = bus.subscribe()
                try:
                    await pipeline.process_live_packet(
                        _race_packet(1, CarOrdinal=368, CurrentRaceTime=1.0),
                        received_at_ms=1_000,
                    )
                    await pipeline.process_live_packet(
                        _race_packet(2, CarOrdinal=368, CurrentRaceTime=1.5),
                        received_at_ms=1_016,
                    )
                    await pipeline.ingest.flush()
                    initial_session = store.active_session()
                    _drain_events(events)

                    await pipeline.process_live_packet(
                        _race_packet(3, CarOrdinal=0, CurrentRaceTime=2.0),
                        received_at_ms=1_032,
                    )
                    await pipeline.ingest.flush()
                    after_unknown = store.active_session()
                    sessions_after_unknown = store.latest_sessions(limit=10)
                    unknown_events = _drain_events(events)

                    await pipeline.process_live_packet(
                        _race_packet(4, CarOrdinal=368, CurrentRaceTime=2.5),
                        received_at_ms=1_048,
                    )
                    await pipeline.ingest.flush()
                    transition_events = _drain_events(events)
                    active = store.active_session()
                    sessions = store.latest_sessions(limit=10)
                finally:
                    bus.unsubscribe(events)

            self.assertIsNotNone(initial_session)
            self.assertIsNotNone(after_unknown)
            self.assertIsNotNone(active)
            self.assertEqual(after_unknown["id"], initial_session["id"])
            self.assertEqual(
                after_unknown["car_identity_key"],
                initial_session["car_identity_key"],
            )
            self.assertEqual(after_unknown["car_ordinal"], 368)
            self.assertEqual(
                [session["id"] for session in sessions_after_unknown],
                [initial_session["id"]],
            )
            self.assertEqual(active["id"], initial_session["id"])
            self.assertEqual(active["car_ordinal"], 368)
            self.assertEqual([session["id"] for session in sessions], [initial_session["id"]])
            all_transition_events = unknown_events + transition_events
            self.assertNotIn(
                ("session_finalized", "car_switch"),
                [(event["type"], event.get("reason")) for event in all_transition_events],
            )
            self.assertNotIn(
                ("session_started", "car_switch"),
                [(event["type"], event.get("reason")) for event in all_transition_events],
            )

        asyncio.run(scenario())

    def test_auto_unknown_active_session_is_upgraded_without_car_switch(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                pipeline = app.state.capture_pipeline
                store = app.state.store
                bus = app.state.bus
                events = bus.subscribe()
                try:
                    await pipeline.process_live_packet(
                        _race_packet(1, CarOrdinal=0, CurrentRaceTime=1.0),
                        received_at_ms=1_000,
                    )
                    await pipeline.process_live_packet(
                        _race_packet(2, CarOrdinal=0, CurrentRaceTime=1.5),
                        received_at_ms=1_016,
                    )
                    await pipeline.ingest.flush()
                    initial_session = store.active_session()
                    _drain_events(events)

                    await pipeline.process_live_packet(
                        _race_packet(3, CarOrdinal=368, CurrentRaceTime=2.0),
                        received_at_ms=1_032,
                    )
                    await pipeline.ingest.flush()
                    upgrade_events = _drain_events(events)
                    active = store.active_session()
                    sessions = store.latest_sessions(limit=10)
                finally:
                    bus.unsubscribe(events)

            self.assertIsNotNone(initial_session)
            self.assertIsNotNone(active)
            self.assertEqual(active["id"], initial_session["id"])
            self.assertEqual(active["car_ordinal"], 368)
            self.assertEqual([session["id"] for session in sessions], [initial_session["id"]])
            self.assertNotIn(
                ("session_finalized", "car_switch"),
                [(event["type"], event.get("reason")) for event in upgrade_events],
            )
            self.assertNotIn(
                ("session_started", "car_switch"),
                [(event["type"], event.get("reason")) for event in upgrade_events],
            )

        asyncio.run(scenario())

    def test_live_capture_splits_active_session_when_car_identity_changes(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                pipeline = app.state.capture_pipeline
                store = app.state.store
                await pipeline.set_mode("manual")
                await pipeline.start_manual()
                await pipeline.process_live_packet(
                    _race_packet(
                        1,
                        CarOrdinal=368,
                        CarClass=3,
                        CarPerformanceIndex=700,
                        DrivetrainType=0,
                    ),
                    received_at_ms=1_000,
                )
                first_session = store.active_session()
                await pipeline.process_live_packet(
                    _race_packet(
                        2,
                        CarOrdinal=368,
                        CarClass=3,
                        CarPerformanceIndex=700,
                        DrivetrainType=0,
                    ),
                    received_at_ms=1_016,
                )
                await pipeline.process_live_packet(
                    _race_packet(
                        3,
                        CarOrdinal=999,
                        CarClass=4,
                        CarPerformanceIndex=800,
                        DrivetrainType=2,
                    ),
                    received_at_ms=1_032,
                )
                await pipeline.ingest.flush()

                sessions = store.latest_sessions(limit=10)
                active = store.active_session()
                self.assertEqual(len(sessions), 2)
                self.assertEqual(sessions[1]["id"], first_session["id"])
                self.assertEqual(sessions[1]["ended_reason"], "car_switch")
                self.assertEqual(active["id"], sessions[0]["id"])
                self.assertEqual(active["car_ordinal"], 999)
                self.assertEqual(store.count_packets(sessions[1]["id"]), 2)
                self.assertEqual(store.count_packets(active["id"]), 1)

        asyncio.run(scenario())

    def test_live_capture_keeps_same_car_identity_in_one_session(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                pipeline = app.state.capture_pipeline
                store = app.state.store
                await pipeline.set_mode("manual")
                await pipeline.start_manual()
                for index in range(1, 4):
                    await pipeline.process_live_packet(
                        _race_packet(
                            index,
                            CarOrdinal=368,
                            CarClass=3,
                            CarPerformanceIndex=700,
                            DrivetrainType=0,
                        ),
                        received_at_ms=1_000 + index * 16,
                    )
                await pipeline.ingest.flush()

                self.assertEqual(len(store.latest_sessions(limit=10)), 1)
                self.assertEqual(
                    store.active_session()["car_identity_key"],
                    "ordinal:368|class:3|pi:700|drive:0",
                )
                self.assertEqual(store.count_packets(store.active_session()["id"]), 3)

        asyncio.run(scenario())

    def test_manual_stopped_race_packets_are_ignored_and_warn_once_per_throttle_window(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                events = app.state.bus.subscribe()
                try:
                    await app.state.capture_pipeline.set_mode("manual")
                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(1, CurrentRaceTime=1.0),
                        received_at_ms=1_000,
                    )
                    await app.state.capture_pipeline.process_live_packet(
                        _race_packet(2, CurrentRaceTime=2.0),
                        received_at_ms=1_016,
                    )
                    recorded_events = _drain_events(events)
                finally:
                    app.state.bus.unsubscribe(events)

                toasts = [event for event in recorded_events if event["type"] == "toast"]
                live_samples = [
                    event for event in recorded_events if event["type"] == "live_sample"
                ]
                self.assertEqual(len(live_samples), 0)
                self.assertEqual(len(toasts), 1)
                self.assertEqual(toasts[0]["level"], "warning")
                self.assertIn("Race packets are being ignored", toasts[0]["message"])
                self.assertIn("no active recorder", toasts[0]["message"])
                self.assertIn("no active session", toasts[0]["message"])
                self.assertEqual(app.state.store.latest_sessions(limit=10), [])

        asyncio.run(scenario())

    def test_manual_start_creates_active_session_but_manual_stop_does_not_end_it(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                pipeline = app.state.capture_pipeline
                store = app.state.store

                await pipeline.set_mode("manual")
                await pipeline.start_manual()
                session = store.active_session()
                await pipeline.process_live_packet(
                    _race_packet(1, CurrentRaceTime=1.0),
                    received_at_ms=1_000,
                )
                await pipeline.stop_manual()
                await pipeline.ingest.flush()

                active_after_stop = store.active_session()
                self.assertEqual(session["label"], "Session 1")
                self.assertEqual(active_after_stop["id"], session["id"])
                self.assertEqual(active_after_stop["status"], "active")
                self.assertEqual(store.count_packets(session["id"]), 1)

        asyncio.run(scenario())

    def test_manual_stop_finalization_generates_issue_markers(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                pipeline = app.state.capture_pipeline
                store = app.state.store

                await pipeline.set_mode("manual")
                await pipeline.start_manual()
                for index in range(1, 4):
                    await pipeline.process_live_packet(
                        _race_packet(
                            index,
                            CurrentLap=float(index),
                            CurrentRaceTime=float(index),
                            TireCombinedSlipRearLeft=1.32 if index in (2, 3) else 0.1,
                            TireCombinedSlipRearRight=1.28 if index in (2, 3) else 0.1,
                        ),
                        received_at_ms=1_000 + index * 16,
                    )
                await pipeline.stop_manual()

                session = store.active_session()
                laps = store.laps_for_session(session["id"])
                self.assertEqual(len(laps), 1)
                markers = store.issue_markers_for_lap(lap_id=laps[0]["id"])
                summary = store.lap_summary(laps[0]["id"])

                self.assertTrue(markers)
                self.assertTrue(
                    any(
                        marker["metric"] == "rear_combined_slip"
                        and marker["severity"] == "critical"
                        for marker in markers
                    )
                )
                self.assertEqual(summary["sample_count"], 3)
                self.assertIn("peak_combined_slip", summary)

        asyncio.run(scenario())

    def test_lap_finalization_invokes_track_matcher_and_publishes_assigned_lap(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                pipeline = app.state.capture_pipeline
                store = app.state.store
                _seed_line_track(
                    store,
                    track_key="track-info:161",
                    route_id=161,
                    display_name="Shirakawa Circuit",
                )
                _seed_line_track(
                    store,
                    track_key="track-info:999",
                    route_id=999,
                    display_name="Emerald Circuit",
                    offset_z=1_000.0,
                )
                events = app.state.bus.subscribe()
                try:
                    await pipeline.set_mode("manual")
                    await pipeline.start_manual()
                    for index, (x, z) in enumerate(_line_track_points(), start=1):
                        await pipeline.process_live_packet(
                            _race_packet(
                                index,
                                PositionX=x,
                                PositionZ=z,
                                CurrentLap=float(index),
                                CurrentRaceTime=float(index),
                                LapNumber=1,
                            ),
                            received_at_ms=1_000 + index * 16,
                        )
                    _drain_events(events)

                    await pipeline.stop_manual()
                    recorded_events = _drain_events(events)
                finally:
                    app.state.bus.unsubscribe(events)

                session = store.active_session()
                laps = store.laps_for_session(session["id"])
                finalized_lap = laps[0]
                candidates = store.track_match_candidates_for_lap(
                    finalized_lap["id"],
                    MATCHER_VERSION,
                )

                return finalized_lap, candidates, recorded_events

        finalized_lap, candidates, recorded_events = asyncio.run(scenario())

        self.assertEqual(finalized_lap["track_profile_name"], "Shirakawa Circuit")
        self.assertEqual(candidates[0]["track_key"], "track-info:161")
        self.assertEqual(candidates[0]["assigned_track_profile_id"], finalized_lap["track_profile_id"])
        lap_finalized = next(event for event in recorded_events if event["type"] == "lap_finalized")
        self.assertEqual(lap_finalized["session_id"], finalized_lap["session_id"])
        self.assertEqual(lap_finalized["lap"]["track_profile_name"], "Shirakawa Circuit")
        self.assertTrue(lap_finalized["track_match"]["assignment"]["assigned"])

    def test_race_to_non_race_boundary_invokes_track_matcher_for_open_lap(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                pipeline = app.state.capture_pipeline
                store = app.state.store
                _seed_line_track(
                    store,
                    track_key="track-info:161",
                    route_id=161,
                    display_name="Shirakawa Circuit",
                )
                _seed_line_track(
                    store,
                    track_key="track-info:999",
                    route_id=999,
                    display_name="Emerald Circuit",
                    offset_z=1_000.0,
                )
                events = app.state.bus.subscribe()
                try:
                    await pipeline.set_mode("manual")
                    await pipeline.start_manual()
                    for index, (x, z) in enumerate(_line_track_points(), start=1):
                        await pipeline.process_live_packet(
                            _race_packet(
                                index,
                                PositionX=x,
                                PositionZ=z,
                                CurrentLap=float(index),
                                CurrentRaceTime=float(index),
                                LapNumber=1,
                            ),
                            received_at_ms=1_000 + index * 16,
                        )
                    _drain_events(events)

                    await pipeline.process_live_packet(
                        _race_packet(
                            20,
                            IsRaceOn=0,
                            CurrentLap=0.0,
                            CurrentRaceTime=0.0,
                            LapNumber=0,
                            PositionX=100.0,
                            PositionZ=0.0,
                        ),
                        received_at_ms=2_000,
                    )
                    recorded_events = _drain_events(events)
                finally:
                    app.state.bus.unsubscribe(events)

                session = store.active_session()
                laps = store.laps_for_session(session["id"])
                open_lap = laps[0]
                return open_lap, recorded_events

        open_lap, recorded_events = asyncio.run(scenario())

        self.assertEqual(open_lap["status"], "recording")
        self.assertEqual(open_lap["track_profile_name"], "Shirakawa Circuit")
        track_events = [event for event in recorded_events if event["type"] == "lap_track_matched"]
        self.assertEqual(len(track_events), 1)
        self.assertEqual(track_events[0]["lap_id"], open_lap["id"])
        self.assertEqual(track_events[0]["lap"]["track_profile_name"], "Shirakawa Circuit")
        self.assertTrue(track_events[0]["track_match"]["assignment"]["assigned"])

    def test_auto_finalizer_keeps_track_matched_point_to_point_lap(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                pipeline = app.state.capture_pipeline
                store = app.state.store
                _seed_line_track(
                    store,
                    track_key="track-info:161",
                    route_id=161,
                    display_name="Shirakawa Sprint",
                )
                _seed_line_track(
                    store,
                    track_key="track-info:999",
                    route_id=999,
                    display_name="Emerald Sprint",
                    offset_z=1_000.0,
                )
                events = app.state.bus.subscribe()
                try:
                    for index, (x, z) in enumerate(_line_track_points(), start=1):
                        await pipeline.process_live_packet(
                            _race_packet(
                                index,
                                PositionX=x,
                                PositionZ=z,
                                CurrentLap=float(index),
                                CurrentRaceTime=float(index),
                                LapNumber=0,
                            ),
                            received_at_ms=1_000 + index * 16,
                        )
                    _drain_events(events)

                    await pipeline.process_live_packet(
                        _race_packet(
                            20,
                            IsRaceOn=0,
                            CurrentLap=0.0,
                            CurrentRaceTime=0.0,
                            LapNumber=0,
                            PositionX=100.0,
                            PositionZ=0.0,
                        ),
                        received_at_ms=2_000,
                    )
                    await pipeline.finalize_open_records(
                        reason="race_off",
                        finalize_sessions=False,
                    )
                    recorded_events = _drain_events(events)
                finally:
                    app.state.bus.unsubscribe(events)

                session = store.active_session()
                laps = store.laps_for_session(session["id"])
                finalized_lap = laps[0]
                summary = store.lap_summary(finalized_lap["id"])
                stats = store.stats_summary()
                return finalized_lap, summary, recorded_events, stats

        finalized_lap, summary, recorded_events, stats = asyncio.run(scenario())

        self.assertEqual(finalized_lap["status"], "race_off")
        self.assertEqual(finalized_lap["boundary_confidence"], "heuristic")
        self.assertEqual(finalized_lap["track_profile_name"], "Shirakawa Sprint")
        self.assertEqual(finalized_lap["lap_time_ms"], 10_000)
        self.assertEqual(summary["completion_type"], "track_matched_lap")
        self.assertEqual(summary["auto_lap_quality"]["reason"], "accepted_track_matched_lap")
        self.assertFalse(
            [event for event in recorded_events if event["type"] == "auto_lap_discarded"]
        )
        lap_finalized = next(event for event in recorded_events if event["type"] == "lap_finalized")
        self.assertEqual(lap_finalized["boundary_confidence"], "heuristic")
        self.assertEqual(lap_finalized["lap"]["boundary_confidence"], "heuristic")
        self.assertEqual(lap_finalized["lap"]["track_profile_name"], "Shirakawa Sprint")
        self.assertEqual(stats["laps_recorded"], 1)
        self.assertEqual(stats["sessions_created"], 1)
        self.assertEqual(stats["tracks_driven"], 1)
        self.assertEqual(stats["favourite_track"]["value"], "Shirakawa Sprint")

    def test_manual_start_uses_existing_active_session(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                store = app.state.store
                existing_id = store.start_session(label="Existing")

                await app.state.capture_pipeline.set_mode("manual")
                await app.state.capture_pipeline.start_manual()
                await app.state.capture_pipeline.process_live_packet(
                    _race_packet(1, CurrentRaceTime=1.0),
                    received_at_ms=1_000,
                )
                await app.state.capture_pipeline.ingest.flush()

                self.assertEqual(store.active_session()["id"], existing_id)
                self.assertEqual(
                    [session["label"] for session in store.latest_sessions(limit=10)],
                    ["Existing"],
                )
                self.assertEqual(store.count_packets(existing_id), 1)

        asyncio.run(scenario())

    def test_sse_stream_yields_initial_status_frame(self):
        async def scenario():
            bus = EventBus()
            stream = stream_sse_events(bus)
            try:
                frame = await stream.__anext__()
                self.assertTrue(frame.startswith("event: status\n"))
                self.assertEqual(
                    _frame_payload(frame),
                    {"state": "waiting", "message": "waiting for telemetry"},
                )
            finally:
                await stream.aclose()

        asyncio.run(scenario())

    def test_sse_stream_forwards_published_event(self):
        async def scenario():
            bus = EventBus()
            stream = stream_sse_events(bus)
            try:
                await stream.__anext__()
                await bus.publish({"type": "toast", "level": "success", "message": "Replay complete"})

                frame = await asyncio.wait_for(stream.__anext__(), timeout=1)

                self.assertTrue(frame.startswith("event: toast\n"))
                self.assertEqual(
                    _frame_payload(frame),
                    {"type": "toast", "level": "success", "message": "Replay complete"},
                )
            finally:
                await stream.aclose()

        asyncio.run(scenario())

    def test_sse_stream_unsubscribes_when_closed(self):
        async def scenario():
            bus = SpyEventBus()
            stream = stream_sse_events(bus)

            await stream.__anext__()
            self.assertEqual(len(bus._subscribers), 1)

            await stream.aclose()

            self.assertEqual(len(bus._subscribers), 0)
            self.assertEqual(len(bus.unsubscribed_queues), 1)

        asyncio.run(scenario())

    def test_sse_stream_unsubscribes_when_cancelled(self):
        async def scenario():
            bus = SpyEventBus()
            stream = stream_sse_events(bus)

            await stream.__anext__()
            self.assertEqual(len(bus._subscribers), 1)
            next_frame = asyncio.create_task(stream.__anext__())
            await asyncio.sleep(0)

            next_frame.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await next_frame

            self.assertEqual(len(bus._subscribers), 0)
            self.assertEqual(len(bus.unsubscribed_queues), 1)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
