import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from telemetry_tracker.app import CapturePipeline, create_app
from telemetry_tracker.capture import CaptureStateMachine
from telemetry_tracker.lap_detection import LapDetector
from telemetry_tracker.local_file_selection import LocalFileSelectionRegistry
from telemetry_tracker.packet_bridge import decode_packet, encode_packet_for_test, packet_to_live_fields
from telemetry_tracker.udp_listener import UdpTelemetryListener


def _race_packet(index: int, lap_number: int = 1, **overrides) -> bytes:
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
        "CurrentLap": float(index),
        "CurrentRaceTime": float(index),
        "LapNumber": lap_number,
    }
    values.update(overrides)
    return encode_packet_for_test(values)


def _progress_packet_stream(
    *,
    count: int = 150,
    lap_number: int = 1,
    current_start: float = 0.0,
    current_end: float = 60.0,
    race_start: float = 0.0,
    race_end: float = 60.0,
    distance_start: float = 0.0,
    distance_end: float = 3_000.0,
    race_position: int = 1,
    route_guidance: int = 1,
    last_lap: float = 0.0,
    best_lap: float = 0.0,
    reset_index: int = 10_000,
) -> list[bytes]:
    packets = []
    for index in range(count):
        fraction = index / (count - 1) if count > 1 else 0.0
        packets.append(
            _race_packet(
                index + 1,
                lap_number=lap_number,
                CurrentLap=current_start + ((current_end - current_start) * fraction),
                CurrentRaceTime=race_start + ((race_end - race_start) * fraction),
                PositionX=fraction * 1_000.0,
                PositionY=0.0,
                PositionZ=fraction * 1_000.0,
                Speed=35.0,
                DistanceTraveled=distance_start + ((distance_end - distance_start) * fraction),
                RacePosition=race_position,
                NormalizedDrivingLine=route_guidance,
                NormalizedAIBrakeDifference=0,
                LastLap=last_lap,
                BestLap=best_lap,
            )
        )
    packets.append(
        _race_packet(
            reset_index,
            lap_number=lap_number,
            CurrentLap=0.0,
            CurrentRaceTime=0.0,
            PositionX=0.0,
            PositionY=0.0,
            PositionZ=0.0,
            Speed=0.0,
            DistanceTraveled=0.0,
            RacePosition=0,
            NormalizedDrivingLine=0,
            NormalizedAIBrakeDifference=0,
            LastLap=last_lap,
            BestLap=best_lap,
        )
    )
    return packets


def _auto_junk_stream() -> list[bytes]:
    return _progress_packet_stream(
        count=150,
        lap_number=0,
        current_start=0.0,
        current_end=0.0,
        race_start=0.0,
        race_end=75.0,
        distance_start=0.0,
        distance_end=0.0,
        race_position=0,
        route_guidance=0,
    )


def _sprint_stream() -> list[bytes]:
    return _progress_packet_stream(
        count=150,
        lap_number=0,
        current_start=0.014,
        current_end=129.174,
        race_start=0.014,
        race_end=129.174,
        distance_start=-62.9,
        distance_end=5_951.3,
        race_position=4,
        route_guidance=1,
    )


def _terminal_circuit_stream() -> list[bytes]:
    return _progress_packet_stream(
        count=150,
        lap_number=2,
        current_start=0.0,
        current_end=105.543,
        race_start=87.106,
        race_end=192.649,
        distance_start=11_905.7,
        distance_end=17_858.9,
        race_position=2,
        route_guidance=1,
        last_lap=87.106,
        best_lap=87.106,
    )


async def _process_packets(pipeline, packets: list[bytes]) -> None:
    for index, raw in enumerate(packets):
        await pipeline.process_live_packet(raw, received_at_ms=1_000 + (index * 16))


def _drain_events(queue) -> list[dict]:
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


def _sample_from_raw(raw: bytes, sequence: int, lap_id: str | None = None) -> dict:
    decoded = decode_packet(raw)
    sample = packet_to_live_fields(decoded, sequence=sequence, received_at_ms=sequence * 16)
    sample["lap_id"] = lap_id
    return sample


def _insert_lap_with_samples(store, session_id: str, lap_number: int, sequence_offset: int = 0) -> str:
    lap_id = store.create_lap(
        session_id=session_id,
        lap_number=lap_number,
        boundary_confidence="game_field",
    )
    raw_packets = [
        _race_packet(sequence_offset + 1, lap_number=lap_number),
        _race_packet(sequence_offset + 2, lap_number=lap_number),
    ]
    decoded = [decode_packet(raw) for raw in raw_packets]
    samples = [
        _sample_from_raw(raw, sequence=sequence_offset + index + 1, lap_id=lap_id)
        for index, raw in enumerate(raw_packets)
    ]
    store.insert_packet_batch(session_id, raw_packets, decoded, samples)
    store.insert_lap_summary(
        lap_id,
        {
            "sample_count": len(samples),
            "packet_count": len(samples),
            "lap_duration_ms": 16,
            "distance_estimate_m": 2.23606797749979,
            "top_speed_mps": max(sample["speed_mps"] for sample in samples),
            "average_speed_mps": sum(sample["speed_mps"] for sample in samples) / len(samples),
            "max_throttle": 128,
            "average_throttle": 128,
            "max_brake": 0,
            "average_brake": 0,
            "max_slip": None,
            "uncertainty_count": 0,
        },
    )
    return lap_id


def _session_label(store, session_id: str) -> str:
    with store.connect() as con:
        row = con.execute("SELECT label FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return row["label"]


class TrackerHistoryApiTests(unittest.TestCase):
    def _wait_for_import_job(self, client: TestClient, job_id: str, *, terminal: bool = True) -> dict:
        terminal_statuses = {"completed", "failed", "cancelled"}
        last_job: dict | None = None
        for _ in range(100):
            response = client.get("/api/replay/import-jobs")
            self.assertEqual(response.status_code, 200)
            jobs = response.json()["jobs"]
            last_job = next((candidate for candidate in jobs if candidate["id"] == job_id), None)
            if last_job is not None and (not terminal or last_job["status"] in terminal_statuses):
                return last_job
            time.sleep(0.05)
        self.fail(f"import job {job_id} did not reach expected state; last={last_job}")

    def test_capture_endpoint_reports_mode_phase_status_and_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")

            self.assertIsInstance(app.state.capture, CaptureStateMachine)
            self.assertIsInstance(app.state.lap_detector, LapDetector)
            self.assertIsInstance(app.state.udp_listener, UdpTelemetryListener)

            with TestClient(app) as client:
                response = client.get("/api/capture")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["mode"], "auto")
            self.assertEqual(payload["phase"], "idle")
            self.assertFalse(payload["recording"]["active"])
            self.assertEqual(payload["packet_receipt"]["state"], "waiting")
            self.assertEqual(payload["listener"]["state"], "waiting")

    def test_capture_mode_endpoint_changes_mode_and_persists_user_setting(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "telemetry_tracker.sqlite3"
            app = create_app(db_path=db_path)

            with TestClient(app) as client:
                response = client.post("/api/capture/mode", json={"mode": "manual"})
                persisted = client.get("/api/capture")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["mode"], "manual")
            self.assertEqual(persisted.json()["mode"], "manual")
            with app.state.store.connect() as con:
                row = con.execute("SELECT capture_mode FROM user_settings LIMIT 1").fetchone()
            self.assertEqual(row["capture_mode"], "manual")

            reloaded_app = create_app(db_path=db_path)
            self.assertEqual(reloaded_app.state.capture.status()["mode"], "manual")

    def test_capture_mode_endpoint_rejects_bad_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")

            with TestClient(app) as client:
                response = client.post("/api/capture/mode", json={"mode": "sometimes"})

            self.assertEqual(response.status_code, 400)
            self.assertIn("mode", response.json()["detail"])

    def test_capture_start_and_stop_control_manual_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")

            with TestClient(app) as client:
                start = client.post("/api/capture/start")
                stop = client.post("/api/capture/stop")

            self.assertEqual(start.status_code, 200)
            start_payload = start.json()
            self.assertEqual(start_payload["mode"], "manual")
            self.assertEqual(start_payload["phase"], "recording")
            self.assertTrue(start_payload["recording"]["active"])

            self.assertEqual(stop.status_code, 200)
            stop_payload = stop.json()
            self.assertEqual(stop_payload["mode"], "manual")
            self.assertEqual(stop_payload["phase"], "idle")
            self.assertFalse(stop_payload["recording"]["active"])

    def test_laps_endpoint_returns_newest_laps_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            old_session_id = store.create_session(label="Old session")
            new_session_id = store.create_session(label="New session")
            old_lap_id = _insert_lap_with_samples(store, old_session_id, lap_number=1)
            new_lap_id = _insert_lap_with_samples(store, new_session_id, lap_number=2, sequence_offset=10)
            with store.connect() as con:
                con.execute("UPDATE laps SET started_at_ms = ? WHERE id = ?", (1_100, old_lap_id))
                con.execute("UPDATE laps SET started_at_ms = ? WHERE id = ?", (2_100, new_lap_id))

            with TestClient(app) as client:
                response = client.get("/api/laps")

            self.assertEqual(response.status_code, 200)
            laps = response.json()["laps"]
            self.assertEqual([lap["id"] for lap in laps], [new_lap_id, old_lap_id])
            self.assertEqual(laps[0]["session_label"], "New session")

    def test_lap_detail_endpoint_returns_metadata_plus_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Detail session")
            lap_id = _insert_lap_with_samples(store, session_id, lap_number=7)

            with TestClient(app) as client:
                response = client.get(f"/api/laps/{lap_id}")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["lap"]["id"], lap_id)
            self.assertEqual(payload["lap"]["session_id"], session_id)
            self.assertEqual(payload["lap"]["lap_number"], 7)
            self.assertEqual(payload["lap"]["session_label"], "Detail session")
            self.assertEqual(payload["summary"]["sample_count"], 2)
            self.assertEqual(payload["summary"]["packet_count"], 2)

    def test_lap_detail_endpoint_includes_summary_backed_lap_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Timed detail session")
            lap_id = _insert_lap_with_samples(store, session_id, lap_number=0)
            store.finalize_lap(
                lap_id,
                reason="event_exit",
                boundary_confidence="heuristic",
            )
            store.insert_lap_summary(
                lap_id,
                {
                    "sample_count": 2,
                    "packet_count": 2,
                    "completion_type": "sprint_event",
                    "lap_time_ms": 129_160,
                },
            )

            with TestClient(app) as client:
                response = client.get(f"/api/laps/{lap_id}")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["lap"]["id"], lap_id)
            self.assertEqual(payload["lap"]["lap_time_ms"], 129_160)
            self.assertEqual(payload["summary"]["completion_type"], "sprint_event")

    def test_lap_samples_endpoint_returns_render_ready_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Samples session")
            lap_id = _insert_lap_with_samples(store, session_id, lap_number=3)

            with TestClient(app) as client:
                response = client.get(f"/api/laps/{lap_id}/samples")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["lap_id"], lap_id)
            self.assertEqual(len(payload["samples"]), 2)
            self.assertEqual(payload["samples"][0]["lap_id"], lap_id)
            for key in (
                "sequence",
                "game_timestamp_ms",
                "x",
                "y",
                "z",
                "speed_mps",
                "current_rpm",
                "power_w",
                "torque_nm",
                "fuel",
                "race_position",
                "wheel_on_rumble_strip_front_left",
            ):
                self.assertIn(key, payload["samples"][0])

    def test_lap_detail_and_samples_return_404_for_unknown_lap(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")

            with TestClient(app) as client:
                detail = client.get("/api/laps/missing-lap")
                samples = client.get("/api/laps/missing-lap/samples")

            self.assertEqual(detail.status_code, 404)
            self.assertEqual(samples.status_code, 404)

    def test_sessions_endpoint_returns_newest_sessions_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            old_session_id = store.create_session(label="Old session")
            new_session_id = store.create_session(label="New session")
            with store.connect() as con:
                con.execute("UPDATE sessions SET started_at_ms = ? WHERE id = ?", (1_000, old_session_id))
                con.execute("UPDATE sessions SET started_at_ms = ? WHERE id = ?", (2_000, new_session_id))

            with TestClient(app) as client:
                response = client.get("/api/sessions")

            self.assertEqual(response.status_code, 200)
            sessions = response.json()["sessions"]
            self.assertEqual([session["id"] for session in sessions], [new_session_id, old_session_id])

    def test_sessions_endpoint_returns_lap_aggregate_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Aggregate session")
            fast_lap_id = _insert_lap_with_samples(store, session_id, lap_number=1)
            slow_lap_id = _insert_lap_with_samples(store, session_id, lap_number=2, sequence_offset=10)
            with store.connect() as con:
                con.execute(
                    """
                    UPDATE lap_samples
                    SET current_lap = CASE sequence WHEN 11 THEN 0.0 WHEN 12 THEN 2.0 ELSE current_lap END
                    WHERE lap_id = ?
                    """,
                    (slow_lap_id,),
                )
            store.finalize_lap(fast_lap_id, reason="lap_boundary", boundary_confidence="game_field")
            store.finalize_lap(slow_lap_id, reason="lap_boundary", boundary_confidence="game_field")

            with TestClient(app) as client:
                response = client.get("/api/sessions")

            self.assertEqual(response.status_code, 200)
            [session] = response.json()["sessions"]
            self.assertEqual(session["id"], session_id)
            self.assertEqual(session["lap_count"], 2)
            self.assertEqual(session["completed_lap_count"], 2)
            self.assertEqual(session["best_lap_time_ms"], 1_000)
            self.assertEqual(session["average_lap_time_ms"], 1_500)
            self.assertEqual(session["total_lap_time_ms"], 3_000)

    def test_activate_session_endpoint_reopens_selected_historical_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            historical_id = store.start_session(
                label="Historical Mazda",
                car_identity={
                    "car_identity_key": "ordinal:368|class:3|pi:700|drive:0",
                    "car_ordinal": 368,
                    "car_name": "Mazda 787B",
                    "car_class_id": 3,
                    "car_class_label": "A",
                    "car_performance_index": 700,
                    "drivetrain_id": 0,
                    "drivetrain_label": "RWD",
                },
            )
            store.end_session(historical_id)
            previous_active_id = store.start_session(label="Scratch session")

            with TestClient(app) as client:
                response = client.post(f"/api/sessions/{historical_id}/activate")

            self.assertEqual(response.status_code, 200)
            session = response.json()["session"]
            self.assertEqual(session["id"], historical_id)
            self.assertEqual(session["status"], "active")
            self.assertIsNone(session["ended_at_ms"])
            self.assertIsNone(session["ended_reason"])
            self.assertEqual(store.active_session()["id"], historical_id)
            previous_active = store.session(previous_active_id)
            self.assertEqual(previous_active["status"], "session_activated")
            self.assertEqual(previous_active["ended_reason"], "session_activated")

    def test_activate_session_endpoint_returns_404_for_unknown_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")

            with TestClient(app) as client:
                response = client.post("/api/sessions/missing-session/activate")

            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"], "unknown session_id")

    def test_matching_manual_capture_appends_to_reopened_historical_session(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                store = app.state.store
                pipeline = app.state.capture_pipeline
                historical_id = store.start_session(
                    label="Historical Mazda",
                    car_identity={
                        "car_identity_key": "ordinal:368|class:3|pi:700|drive:0",
                        "car_ordinal": 368,
                        "car_name": "Mazda 787B",
                        "car_class_id": 3,
                        "car_class_label": "A",
                        "car_performance_index": 700,
                        "drivetrain_id": 0,
                        "drivetrain_label": "RWD",
                    },
                )
                store.end_session(historical_id)

                await pipeline.activate_session(historical_id)
                await pipeline.start_manual()
                for index in range(1, 3):
                    await pipeline.process_live_packet(
                        _race_packet(
                            index,
                            CarOrdinal=368,
                            CarClass=3,
                            CarPerformanceIndex=700,
                            DrivetrainType=0,
                            CurrentRaceTime=float(index),
                        ),
                        received_at_ms=1_000 + (index * 16),
                    )
                await pipeline.ingest.flush()

                return {
                    "historical_id": historical_id,
                    "active": store.active_session(),
                    "sessions": store.latest_sessions(limit=10),
                    "packet_count": store.count_packets(historical_id),
                    "laps": store.laps_for_session(historical_id),
                }

        result = asyncio.run(scenario())

        self.assertEqual(result["active"]["id"], result["historical_id"])
        self.assertEqual(result["active"]["label"], "Historical Mazda")
        self.assertEqual(result["active"]["status"], "active")
        self.assertEqual(result["packet_count"], 2)
        self.assertEqual([session["id"] for session in result["sessions"]], [result["active"]["id"]])
        self.assertGreaterEqual(len(result["laps"]), 1)
        self.assertTrue(all(lap["session_id"] == result["active"]["id"] for lap in result["laps"]))

    def test_delete_lap_endpoint_removes_lap_samples_and_session_aggregate(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Delete bad lap")
            kept_lap_id = _insert_lap_with_samples(store, session_id, lap_number=1)
            deleted_lap_id = _insert_lap_with_samples(store, session_id, lap_number=2, sequence_offset=10)
            store.finalize_lap(kept_lap_id, reason="lap_boundary", boundary_confidence="game_field")
            store.finalize_lap(deleted_lap_id, reason="lap_boundary", boundary_confidence="game_field")

            with TestClient(app) as client:
                deleted = client.delete(f"/api/laps/{deleted_lap_id}")
                laps = client.get("/api/laps").json()["laps"]
                samples = client.get(f"/api/laps/{deleted_lap_id}/samples")
                sessions = client.get("/api/sessions").json()["sessions"]

            self.assertEqual(deleted.status_code, 200)
            self.assertTrue(deleted.json()["deleted"])
            self.assertEqual(deleted.json()["lap_id"], deleted_lap_id)
            self.assertEqual(deleted.json()["session_id"], session_id)
            self.assertEqual(samples.status_code, 404)
            self.assertNotIn(deleted_lap_id, [lap["id"] for lap in laps])
            self.assertIn(kept_lap_id, [lap["id"] for lap in laps])
            [session] = sessions
            self.assertEqual(session["lap_count"], 1)
            self.assertEqual(session["completed_lap_count"], 1)
            self.assertEqual(session["total_lap_time_ms"], 1_000)
            self.assertEqual(store.count_packets(session_id), 2)
            with store.connect() as con:
                remaining_deleted_samples = con.execute(
                    "SELECT COUNT(*) FROM lap_samples WHERE lap_id = ?",
                    (deleted_lap_id,),
                ).fetchone()[0]
                remaining_deleted_packets = con.execute(
                    "SELECT COUNT(*) FROM packet_blobs WHERE lap_id = ?",
                    (deleted_lap_id,),
                ).fetchone()[0]
            self.assertEqual(remaining_deleted_samples, 0)
            self.assertEqual(remaining_deleted_packets, 0)

    def test_delete_lap_endpoint_returns_404_for_unknown_lap(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")

            with TestClient(app) as client:
                response = client.delete("/api/laps/missing-lap")

            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"], "unknown lap_id")

    def test_auto_pipeline_discards_no_progress_event_exit_lap(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                store = app.state.store
                queue = app.state.bus.subscribe()
                try:
                    await _process_packets(app.state.capture_pipeline, _auto_junk_stream())
                    events = _drain_events(queue)
                finally:
                    app.state.bus.unsubscribe(queue)

                with store.connect() as con:
                    lap_count = con.execute("SELECT COUNT(*) FROM laps").fetchone()[0]
                    sample_count = con.execute("SELECT COUNT(*) FROM lap_samples").fetchone()[0]
                    packet_count = con.execute("SELECT COUNT(*) FROM packet_blobs").fetchone()[0]

                return events, lap_count, sample_count, packet_count

        events, lap_count, sample_count, packet_count = asyncio.run(scenario())

        self.assertEqual(lap_count, 0)
        self.assertEqual(sample_count, 0)
        self.assertEqual(packet_count, 0)
        discarded_events = [
            event for event in events if event.get("type") == "auto_lap_discarded"
        ]
        self.assertEqual(len(discarded_events), 1)
        self.assertEqual(discarded_events[0]["reason"], "no_current_lap_progress")
        self.assertTrue(
            any(
                event.get("type") == "toast"
                and "Auto recorder discarded incomplete lap" in event.get("message", "")
                for event in events
            )
        )

    def test_auto_pipeline_keeps_completed_sprint_event_summary(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                store = app.state.store
                await _process_packets(app.state.capture_pipeline, _sprint_stream())

                [lap] = store.latest_laps(limit=1)
                return lap, store.lap_summary(lap["id"])

        lap, summary = asyncio.run(scenario())

        self.assertEqual(lap["lap_number"], 0)
        self.assertEqual(lap["status"], "event_exit")
        self.assertEqual(lap["boundary_confidence"], "heuristic")
        self.assertEqual(summary["completion_type"], "sprint_event")
        self.assertEqual(summary["lap_time_ms"], 129_160)

    def test_auto_pipeline_keeps_terminal_race_end_lap_summary(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                store = app.state.store
                await _process_packets(app.state.capture_pipeline, _terminal_circuit_stream())

                [lap] = store.latest_laps(limit=1)
                return lap, store.lap_summary(lap["id"])

        lap, summary = asyncio.run(scenario())

        self.assertEqual(lap["lap_number"], 2)
        self.assertEqual(lap["status"], "event_exit")
        self.assertEqual(lap["boundary_confidence"], "heuristic")
        self.assertEqual(summary["completion_type"], "terminal_circuit_lap")
        self.assertEqual(summary["lap_time_ms"], 105_543)

    def test_manual_pipeline_keeps_no_progress_event_exit_lap(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                store = app.state.store
                pipeline = app.state.capture_pipeline
                await pipeline.set_mode("manual")
                await pipeline.start_manual()
                await _process_packets(pipeline, _auto_junk_stream())
                await pipeline.stop_manual()

                return store.latest_laps(limit=10)

        laps = asyncio.run(scenario())

        self.assertEqual(len(laps), 1)
        self.assertEqual(laps[0]["lap_number"], 0)
        self.assertEqual(laps[0]["status"], "event_exit")
        self.assertEqual(laps[0]["boundary_confidence"], "heuristic")

    def test_delete_lap_endpoint_removes_active_recording_lap(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            session_id = store.create_session(label="Active delete allowed")
            active_lap_id = _insert_lap_with_samples(store, session_id, lap_number=1)

            with TestClient(app) as client:
                response = client.delete(f"/api/laps/{active_lap_id}")
                samples = client.get(f"/api/laps/{active_lap_id}/samples")
                sessions = client.get("/api/sessions").json()["sessions"]

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["deleted"])
            self.assertEqual(response.json()["lap_id"], active_lap_id)
            self.assertEqual(samples.status_code, 404)
            self.assertNotIn(active_lap_id, [lap["id"] for lap in store.latest_laps(limit=10)])
            [session] = sessions
            self.assertEqual(session["id"], session_id)
            self.assertEqual(session["lap_count"], 0)
            self.assertEqual(session["completed_lap_count"], 0)

    def test_delete_lap_endpoint_flushes_and_forgets_active_pipeline_lap(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            pipeline = app.state.capture_pipeline

            asyncio.run(pipeline.start_manual())
            asyncio.run(
                pipeline.process_live_packet(
                    _race_packet(1, lap_number=1),
                    received_at_ms=1_000,
                )
            )
            [active_lap] = store.latest_laps(limit=1)
            active_lap_id = active_lap["id"]
            session_id = active_lap["session_id"]

            with TestClient(app) as client:
                response = client.delete(f"/api/laps/{active_lap_id}")

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["deleted"])
            self.assertNotIn(active_lap_id, pipeline._lap_ids.values())
            asyncio.run(
                pipeline.finalize_open_records(
                    reason="manual_stop",
                    reset_detector=True,
                    finalize_sessions=False,
                )
            )
            self.assertNotIn(active_lap_id, [lap["id"] for lap in store.latest_laps(limit=10)])
            self.assertEqual(store.count_packets(session_id), 0)

    def test_session_lifecycle_endpoints_start_end_rename_delete_and_report_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")

            with TestClient(app) as client:
                no_active = client.get("/api/sessions/active")
                started = client.post("/api/sessions/start")
                session_id = started.json()["session"]["id"]
                active = client.get("/api/sessions/active")
                renamed = client.patch(
                    f"/api/sessions/{session_id}",
                    json={"label": "Practice A"},
                )
                ended = client.post(f"/api/sessions/{session_id}/end")
                ended_again = client.post(f"/api/sessions/{session_id}/end")
                deleted = client.delete(f"/api/sessions/{session_id}")
                active_after_delete = client.get("/api/sessions/active")

            self.assertEqual(no_active.status_code, 200)
            self.assertIsNone(no_active.json()["session"])
            self.assertEqual(started.status_code, 200)
            self.assertEqual(started.json()["session"]["label"], "Session 1")
            self.assertEqual(active.status_code, 200)
            self.assertEqual(active.json()["session"]["id"], session_id)
            self.assertEqual(renamed.status_code, 200)
            self.assertEqual(renamed.json()["session"]["label"], "Practice A")
            self.assertEqual(ended.status_code, 200)
            self.assertEqual(ended.json()["session"]["status"], "user_end")
            self.assertEqual(ended_again.status_code, 200)
            self.assertEqual(ended_again.json()["session"]["id"], session_id)
            self.assertEqual(deleted.status_code, 200)
            self.assertTrue(deleted.json()["deleted"])
            self.assertEqual(deleted.json()["session_id"], session_id)
            self.assertIsNone(active_after_delete.json()["session"])

    def test_sessions_endpoint_supports_page_size_100_and_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            profile_id = store.create_track_profile(
                "Copper Canyon",
                "Sprint",
                "manual",
                "user",
            )
            target_id = store.create_session(label="Filter Target", status="user_end")
            other_id = store.create_session(label="Other", status="user_end")
            lap_id = store.create_lap(
                target_id,
                lap_number=4,
                boundary_confidence="game_field",
            )
            store.assign_track_profile(target_id, lap_id, profile_id)
            store.finalize_lap(
                lap_id,
                reason="lap_boundary",
                boundary_confidence="game_field",
            )
            with store.connect() as con:
                con.execute(
                    "UPDATE sessions SET started_at_ms = 2000, last_active_at_ms = 3000 WHERE id = ?",
                    (target_id,),
                )
                con.execute(
                    "UPDATE sessions SET started_at_ms = 4000, last_active_at_ms = 5000 WHERE id = ?",
                    (other_id,),
                )

            with TestClient(app) as client:
                response = client.get(
                    "/api/sessions",
                    params={
                        "page": 1,
                        "page_size": 100,
                        "name": "target",
                        "created_from": 1000,
                        "created_to": 3000,
                        "last_active_from": 2500,
                        "last_active_to": 3500,
                        "lap_count_min": 1,
                        "lap_count_max": 1,
                        "track": "copper",
                    },
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["page"], 1)
            self.assertEqual(payload["page_size"], 100)
            self.assertEqual(payload["total"], 1)
            self.assertEqual(payload["sessions"][0]["id"], target_id)
            self.assertEqual(payload["sessions"][0]["lap_count"], 1)

    def test_session_laps_endpoint_returns_laps_scoped_to_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            first_session_id = store.create_session(label="First")
            second_session_id = store.create_session(label="Second")
            _insert_lap_with_samples(store, first_session_id, lap_number=1)
            second_lap_id = _insert_lap_with_samples(store, second_session_id, lap_number=2)

            with TestClient(app) as client:
                response = client.get(f"/api/sessions/{second_session_id}/laps")
                missing = client.get("/api/sessions/missing/laps")

            self.assertEqual(response.status_code, 200)
            self.assertEqual([lap["id"] for lap in response.json()["laps"]], [second_lap_id])
            self.assertEqual(missing.status_code, 404)

    def test_replay_recording_mode_routes_packets_through_capture_and_lap_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "recording.bin"
            raw_path.write_bytes(
                b"".join(
                    [
                        _race_packet(1, lap_number=1),
                        _race_packet(2, lap_number=1),
                        _race_packet(3, lap_number=1),
                        _race_packet(4, lap_number=2, CurrentLap=0.1, CurrentRaceTime=64.0),
                        _race_packet(5, lap_number=2, CurrentLap=1.0, CurrentRaceTime=65.0),
                    ]
                )
            )
            registry = LocalFileSelectionRegistry()
            selection = registry.register_files([raw_path])
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )

            with TestClient(app) as client:
                replay = client.post(
                    "/api/replay",
                    json={
                        "selection_id": selection["selection_id"],
                        "label": "Recorded replay",
                        "recording_mode": True,
                    },
                )
                laps = client.get("/api/laps").json()["laps"]
                first_lap_detail = client.get(f"/api/laps/{laps[-1]['id']}").json()

            self.assertEqual(replay.status_code, 200)
            self.assertEqual(replay.json()["packet_count"], 5)
            self.assertEqual(len(laps), 2)
            self.assertTrue(all(lap["session_label"] == "Recorded replay" for lap in laps))
            self.assertEqual(first_lap_detail["summary"]["packet_count"], 3)
            self.assertEqual(first_lap_detail["summary"]["sample_count"], 3)

    def test_replay_upload_routes_file_through_capture_and_lap_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            raw = b"".join(
                [
                    _race_packet(1, lap_number=1),
                    _race_packet(2, lap_number=1),
                    _race_packet(3, lap_number=1),
                    _race_packet(4, lap_number=2, CurrentLap=0.1, CurrentRaceTime=64.0),
                    _race_packet(5, lap_number=2, CurrentLap=1.0, CurrentRaceTime=65.0),
                ]
            )

            with TestClient(app) as client:
                replay = client.post(
                    "/api/replay/upload",
                    data={"label": "Browser upload"},
                    files={"file": ("browser-upload.bin", raw, "application/octet-stream")},
                )
                laps = client.get("/api/laps").json()["laps"]

            self.assertEqual(replay.status_code, 200)
            payload = replay.json()
            self.assertEqual(payload["packet_count"], 5)
            self.assertTrue(payload["session_id"])
            self.assertEqual(len(payload["session_ids"]), 1)
            self.assertEqual(len(payload["lap_ids"]), 2)
            self.assertEqual(len(laps), 2)
            self.assertTrue(all(lap["session_label"] == "Browser upload" for lap in laps))

    def test_replay_import_job_upload_processes_multiple_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            first = b"".join(
                [
                    _race_packet(1, lap_number=1),
                    _race_packet(2, lap_number=1),
                    _race_packet(3, lap_number=2, CurrentLap=0.1, CurrentRaceTime=64.0),
                ]
            )
            second = b"".join(
                [
                    _race_packet(10, lap_number=1),
                    _race_packet(11, lap_number=1),
                    _race_packet(12, lap_number=2, CurrentLap=0.1, CurrentRaceTime=70.0),
                ]
            )

            with TestClient(app) as client:
                response = client.post(
                    "/api/replay/import-jobs/upload",
                    data={"label": "Folder batch", "source_type": "folder"},
                    files=[
                        ("files", ("captures/first.bin", first, "application/octet-stream")),
                        ("files", ("captures/second.bin", second, "application/octet-stream")),
                    ],
                )
                self.assertEqual(response.status_code, 200)
                job_id = response.json()["job"]["id"]
                job = self._wait_for_import_job(client, job_id)
                laps = client.get("/api/laps").json()["laps"]

            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["total_files"], 2)
            self.assertEqual(job["processed_files"], 2)
            self.assertEqual(job["failed_files"], 0)
            self.assertEqual(job["packet_count"], 6)
            self.assertEqual(len(job["session_ids"]), 2)
            self.assertEqual(len(job["lap_ids"]), 4)
            self.assertEqual(len(laps), 4)
            self.assertTrue(any(lap["session_label"] == "Folder batch - first" for lap in laps))
            self.assertTrue(any(lap["session_label"] == "Folder batch - second" for lap in laps))

    def test_replay_import_job_records_file_errors_and_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            valid = b"".join(
                [
                    _race_packet(1, lap_number=1),
                    _race_packet(2, lap_number=1),
                    _race_packet(3, lap_number=2, CurrentLap=0.1, CurrentRaceTime=64.0),
                ]
            )

            with TestClient(app) as client:
                response = client.post(
                    "/api/replay/import-jobs/upload",
                    data={"label": "Mixed batch", "source_type": "folder"},
                    files=[
                        ("files", ("captures/good.bin", valid, "application/octet-stream")),
                        ("files", ("captures/partial.bin", b"partial", "application/octet-stream")),
                    ],
                )
                self.assertEqual(response.status_code, 200)
                job = self._wait_for_import_job(client, response.json()["job"]["id"])

            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["total_files"], 2)
            self.assertEqual(job["processed_files"], 2)
            self.assertEqual(job["failed_files"], 1)
            self.assertEqual(job["packet_count"], 3)
            self.assertEqual(job["error_count"], 1)
            self.assertIn("multiple of", job["errors"][0]["message"])

    def test_replay_import_selection_job_imports_selected_files_without_deleting_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "native-first.bin"
            second = root / "native-second.bin"
            first.write_bytes(
                b"".join(
                    [
                        _race_packet(1, lap_number=1),
                        _race_packet(2, lap_number=1),
                        _race_packet(3, lap_number=2, CurrentLap=0.1, CurrentRaceTime=64.0),
                    ]
                )
            )
            second.write_bytes(
                b"".join(
                    [
                        _race_packet(10, lap_number=1),
                        _race_packet(11, lap_number=1),
                        _race_packet(12, lap_number=2, CurrentLap=0.1, CurrentRaceTime=70.0),
                    ]
                )
            )
            registry = LocalFileSelectionRegistry()
            selection = registry.register_files([first, second])
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )

            with TestClient(app) as client:
                response = client.post(
                    "/api/replay/import-jobs/selections",
                    json={
                        "selection_id": selection["selection_id"],
                        "label": "Native batch",
                        "source_type": "files",
                    },
                )
                self.assertEqual(response.status_code, 200)
                job = self._wait_for_import_job(client, response.json()["job"]["id"])
                laps = client.get("/api/laps").json()["laps"]

            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["source_type"], "files")
            self.assertEqual(job["total_files"], 2)
            self.assertEqual(job["processed_files"], 2)
            self.assertEqual(job["packet_count"], 6)
            self.assertEqual(len(laps), 4)
            self.assertTrue(any(lap["session_label"] == "Native batch - native-first" for lap in laps))
            self.assertTrue(any(lap["session_label"] == "Native batch - native-second" for lap in laps))

    def test_replay_import_selection_job_imports_folder_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "captures"
            folder.mkdir()
            raw_path = folder / "foldered.bin"
            raw_path.write_bytes(
                b"".join(
                    [
                        _race_packet(1, lap_number=1),
                        _race_packet(2, lap_number=1),
                        _race_packet(3, lap_number=2, CurrentLap=0.1, CurrentRaceTime=64.0),
                    ]
                )
            )
            registry = LocalFileSelectionRegistry()
            selection = registry.register_folder(folder)
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )

            with TestClient(app) as client:
                response = client.post(
                    "/api/replay/import-jobs/selections",
                    json={"selection_id": selection["selection_id"], "label": "Native folder"},
                )
                self.assertEqual(response.status_code, 200)
                job = self._wait_for_import_job(client, response.json()["job"]["id"])

            self.assertTrue(raw_path.exists())
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["source_type"], "folder")
            self.assertEqual(job["total_files"], 1)
            self.assertEqual(job["packet_count"], 3)

    def test_replay_import_selection_job_derives_source_type_from_selected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "single.bin"
            raw_path.write_bytes(b"".join(_race_packet(index, lap_number=1) for index in range(1, 4)))
            registry = LocalFileSelectionRegistry()
            selection = registry.register_files([raw_path])
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )

            with TestClient(app) as client:
                response = client.post(
                    "/api/replay/import-jobs/selections",
                    json={"selection_id": selection["selection_id"]},
                )
                self.assertEqual(response.status_code, 200)
                job = self._wait_for_import_job(client, response.json()["job"]["id"])

            self.assertEqual(job["source_type"], "file")

    def test_replay_import_selection_job_rejects_missing_selection_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")

            with TestClient(app) as client:
                response = client.post("/api/replay/import-jobs/selections", json={})

            self.assertEqual(response.status_code, 400)
            self.assertIn("selection_id is required", response.json()["detail"])

    def test_replay_import_selection_job_rejects_wrong_source_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "capture.bin"
            raw_path.write_bytes(_race_packet(1))
            registry = LocalFileSelectionRegistry()
            selection = registry.register_files([raw_path])
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )

            with TestClient(app) as client:
                response = client.post(
                    "/api/replay/import-jobs/selections",
                    json={"selection_id": selection["selection_id"], "source_type": "folder"},
                )

            self.assertEqual(response.status_code, 400)
            self.assertIn("selection source_type does not match request", response.json()["detail"])

    def test_replay_import_selection_job_rejects_unknown_expired_reused_and_malformed_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "capture.bin"
            raw_path.write_bytes(_race_packet(1))
            now = [1_000.0]
            registry = LocalFileSelectionRegistry(clock=lambda: now[0], ttl_seconds=1.0)
            expired = registry.register_files([raw_path])
            now[0] = 1_002.0
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )

            with TestClient(app) as client:
                malformed = client.post("/api/replay/import-jobs/selections", json={"selection_id": "../bad"})
                unknown = client.post(
                    "/api/replay/import-jobs/selections",
                    json={"selection_id": "unknownselectionid"},
                )
                expired_response = client.post(
                    "/api/replay/import-jobs/selections",
                    json={"selection_id": expired["selection_id"]},
                )
                now[0] = 1_003.0
                valid = registry.register_files([raw_path])
                first_use = client.post(
                    "/api/replay/import-jobs/selections",
                    json={"selection_id": valid["selection_id"]},
                )
                second_use = client.post(
                    "/api/replay/import-jobs/selections",
                    json={"selection_id": valid["selection_id"]},
                )

            self.assertEqual(malformed.status_code, 400)
            self.assertIn("invalid local file selection id", malformed.json()["detail"])
            self.assertEqual(unknown.status_code, 400)
            self.assertIn("unknown or expired local file selection", unknown.json()["detail"])
            self.assertEqual(expired_response.status_code, 400)
            self.assertIn("unknown or expired local file selection", expired_response.json()["detail"])
            self.assertEqual(first_use.status_code, 200)
            self.assertEqual(second_use.status_code, 400)
            self.assertIn("unknown or expired local file selection", second_use.json()["detail"])

    def test_replay_import_selection_job_enforces_file_count_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.bin"
            second = root / "second.bin"
            first.write_bytes(_race_packet(1))
            second.write_bytes(_race_packet(2))
            registry = LocalFileSelectionRegistry()
            selection = registry.register_files([first, second])
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )

            with patch("telemetry_tracker.app.RAW_TELEMETRY_IMPORT_MAX_FILES", 1):
                with TestClient(app) as client:
                    response = client.post(
                        "/api/replay/import-jobs/selections",
                        json={"selection_id": selection["selection_id"]},
                    )

            self.assertEqual(response.status_code, 413)
            self.assertIn("accepts at most 1 files", response.json()["detail"])

    def test_local_file_selection_registry_rejects_too_many_files_before_token_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.bin"
            second = root / "second.bin"
            first.write_bytes(_race_packet(1))
            second.write_bytes(_race_packet(2))
            registry = LocalFileSelectionRegistry(max_files=1)

            with self.assertRaisesRegex(ValueError, "accepts at most 1 files"):
                registry.register_files([first, second])

    def test_replay_import_selection_job_enforces_total_size_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "oversized-total.bin"
            raw = _race_packet(1)
            raw_path.write_bytes(raw)
            registry = LocalFileSelectionRegistry()
            selection = registry.register_files([raw_path])
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )

            with patch("telemetry_tracker.app.RAW_TELEMETRY_IMPORT_MAX_TOTAL_BYTES", len(raw) - 1):
                with TestClient(app) as client:
                    response = client.post(
                        "/api/replay/import-jobs/selections",
                        json={"selection_id": selection["selection_id"]},
                    )

            self.assertEqual(response.status_code, 413)
            self.assertIn("raw telemetry import exceeds maximum allowed total size", response.json()["detail"])

    def test_replay_import_path_job_endpoint_is_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "capture.bin"
            raw_path.write_bytes(_race_packet(1))
            app = create_app(db_path=root / "telemetry_tracker.sqlite3")

            with TestClient(app) as client:
                response = client.post(
                    "/api/replay/import-jobs/paths",
                    json={"file_paths": [str(raw_path)]},
                )

            self.assertEqual(response.status_code, 410)
            self.assertIn("selection_id", response.json()["detail"])

    def test_replay_import_job_can_be_cancelled(self):
        async def stall_replay(self, *args, **kwargs):
            await asyncio.sleep(60)

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            raw = b"".join(_race_packet(index, lap_number=1) for index in range(1, 4))

            with patch.object(CapturePipeline, "replay_packet_iterable", new=stall_replay):
                with TestClient(app) as client:
                    response = client.post(
                        "/api/replay/import-jobs/upload",
                        data={"label": "Cancelled batch"},
                        files=[("files", ("cancelled.bin", raw, "application/octet-stream"))],
                    )
                    self.assertEqual(response.status_code, 200)
                    job_id = response.json()["job"]["id"]

                    cancel_response = client.post(f"/api/replay/import-jobs/{job_id}/cancel")
                    self.assertEqual(cancel_response.status_code, 200)
                    self.assertIn(cancel_response.json()["job"]["status"], {"cancelling", "cancelled"})
                    job = self._wait_for_import_job(client, job_id)

            self.assertEqual(job["status"], "cancelled")
            self.assertEqual(job["packet_count"], 0)

    def test_replay_upload_rejects_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")

            with TestClient(app) as client:
                response = client.post(
                    "/api/replay/upload",
                    files={"file": ("empty.bin", b"", "application/octet-stream")},
                )

            self.assertEqual(response.status_code, 400)
            self.assertIn("raw file contains no packets", response.json()["detail"])

    def test_replay_upload_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            raw = _race_packet(1)

            with patch("telemetry_tracker.app.RAW_TELEMETRY_UPLOAD_MAX_BYTES", len(raw) - 1):
                with TestClient(app) as client:
                    response = client.post(
                        "/api/replay/upload",
                        files={"file": ("oversized.bin", raw, "application/octet-stream")},
                    )

            self.assertEqual(response.status_code, 413)
            self.assertIn("exceeds maximum allowed size", response.json()["detail"])

    def test_replay_upload_rejects_partial_packet_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")

            with TestClient(app) as client:
                response = client.post(
                    "/api/replay/upload",
                    files={"file": ("partial.bin", b"partial", "application/octet-stream")},
                )

            self.assertEqual(response.status_code, 400)
            self.assertIn("multiple of", response.json()["detail"])

    def test_replay_recording_mode_records_laps_when_capture_mode_is_manual(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "manual-mode-recording.bin"
            raw_path.write_bytes(
                b"".join(
                    [
                        _race_packet(1, lap_number=1),
                        _race_packet(2, lap_number=1),
                        _race_packet(3, lap_number=1),
                        _race_packet(4, lap_number=2, CurrentLap=0.1, CurrentRaceTime=64.0),
                        _race_packet(5, lap_number=2, CurrentLap=1.0, CurrentRaceTime=65.0),
                    ]
                )
            )
            registry = LocalFileSelectionRegistry()
            selection = registry.register_files([raw_path])
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                local_file_selection_registry=registry,
            )

            with TestClient(app) as client:
                mode = client.post("/api/capture/mode", json={"mode": "manual"})
                replay = client.post(
                    "/api/replay",
                    json={
                        "selection_id": selection["selection_id"],
                        "label": "Manual mode recorded replay",
                        "recording_mode": True,
                    },
                )
                laps = client.get("/api/laps").json()["laps"]
                first_lap_detail = client.get(f"/api/laps/{laps[-1]['id']}").json()
                capture = client.get("/api/capture").json()

            self.assertEqual(mode.status_code, 200)
            self.assertEqual(replay.status_code, 200)
            self.assertEqual(replay.json()["packet_count"], 5)
            self.assertEqual(len(laps), 2)
            self.assertEqual(first_lap_detail["summary"]["packet_count"], 3)
            self.assertEqual(first_lap_detail["summary"]["sample_count"], 3)
            self.assertEqual(capture["mode"], "manual")
            self.assertEqual(capture["settings"]["capture_mode"], "manual")

    def test_replay_recording_mode_does_not_mix_concurrent_live_packet_into_replay_session(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                store = app.state.store
                pipeline = app.state.capture_pipeline
                await pipeline.start_manual()
                replay_packets = [
                    _race_packet(1, lap_number=1),
                    _race_packet(2, lap_number=1),
                    _race_packet(3, lap_number=1),
                ]
                live_packet = _race_packet(50, lap_number=9, CurrentLap=50.0, CurrentRaceTime=50.0)
                pause_replay_ingest = asyncio.Event()
                release_replay_ingest = asyncio.Event()
                replay_ingest_paused = False
                original_ingest_decoded_packet = type(pipeline.ingest).ingest_decoded_packet

                async def wrapped_ingest_decoded_packet(
                    ingest_self,
                    session_id,
                    raw,
                    decoded,
                    received_at_ms,
                    sample_metadata=None,
                    publish_live=True,
                ):
                    nonlocal replay_ingest_paused
                    if (
                        not replay_ingest_paused
                        and _session_label(store, session_id) == "Recorded replay"
                    ):
                        replay_ingest_paused = True
                        pause_replay_ingest.set()
                        await release_replay_ingest.wait()
                    return await original_ingest_decoded_packet(
                        ingest_self,
                        session_id,
                        raw,
                        decoded,
                        received_at_ms,
                        sample_metadata=sample_metadata,
                        publish_live=publish_live,
                    )

                with patch.object(
                    type(pipeline.ingest),
                    "ingest_decoded_packet",
                    new=wrapped_ingest_decoded_packet,
                ):
                    replay_task = asyncio.create_task(
                        pipeline.replay_packets(replay_packets, label="Recorded replay")
                    )
                    await asyncio.wait_for(pause_replay_ingest.wait(), timeout=1.0)

                    live_result = app.state.udp_listener.packet_handler(live_packet, 50_000)
                    if hasattr(live_result, "__await__"):
                        await live_result

                    release_replay_ingest.set()
                    replay_session_ids = await asyncio.wait_for(replay_task, timeout=1.0)

                await pipeline.stop_manual()
                replay_session_id = replay_session_ids[-1]
                live_session = store.active_session()

                self.assertEqual(store.count_packets(replay_session_id), len(replay_packets))
                self.assertIsNotNone(live_session)
                self.assertEqual(live_session["label"], "Unknown car S1 800 AWD Session")
                self.assertEqual(live_session["car_identity_key"], "ordinal:0|class:4|pi:800|drive:2")
                self.assertEqual(store.count_packets(live_session["id"]), 1)

        asyncio.run(scenario())

    def test_capture_mode_change_finalizes_active_manual_recording_and_flushes_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store

            with TestClient(app) as client:
                start = client.post("/api/capture/start")
                asyncio.run(
                    app.state.capture_pipeline.process_live_packet(
                        _race_packet(1, lap_number=1),
                        received_at_ms=1_000,
                    )
                )
                asyncio.run(
                    app.state.capture_pipeline.process_live_packet(
                        _race_packet(2, lap_number=1),
                        received_at_ms=1_016,
                    )
                )
                mode = client.post("/api/capture/mode", json={"mode": "auto"})

            self.assertEqual(start.status_code, 200)
            self.assertEqual(mode.status_code, 200)
            self.assertEqual(mode.json()["mode"], "auto")
            session = store.latest_sessions(limit=1)[0]
            lap = store.latest_laps(limit=1)[0]
            self.assertEqual(session["status"], "active")
            self.assertIsNone(session["ended_reason"])
            self.assertNotEqual(lap["status"], "recording")
            self.assertEqual(lap["ended_reason"], "capture_mode_change")
            self.assertEqual(store.count_packets(session["id"]), 2)
            self.assertEqual(store.lap_summary(lap["id"])["packet_count"], 2)

    def test_pipeline_finalize_lap_persists_final_boundary_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
            store = app.state.store
            pipeline = app.state.capture_pipeline
            session_id = store.create_session(label="Final confidence pipeline")
            lap_id = store.create_lap(
                session_id=session_id,
                lap_number=1,
                boundary_confidence="game_field",
            )
            pipeline._lap_ids[99] = lap_id

            asyncio.run(
                pipeline._finalize_lap(
                    internal_lap_id=99,
                    reason="lap_boundary",
                    boundary_confidence="uncertain",
                    uncertainty="partial_lap",
                )
            )

            with store.connect() as con:
                lap = con.execute(
                    """
                    SELECT status, ended_reason, boundary_confidence
                    FROM laps
                    WHERE id = ?
                    """,
                    (lap_id,),
                ).fetchone()

            self.assertEqual(lap["status"], "lap_boundary")
            self.assertEqual(lap["ended_reason"], "lap_boundary")
            self.assertEqual(lap["boundary_confidence"], "uncertain")

    def test_capture_mode_change_serializes_live_packet_processing(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                app = create_app(db_path=Path(tmp) / "telemetry_tracker.sqlite3")
                pipeline = app.state.capture_pipeline
                store = app.state.store
                await pipeline.start_manual()
                await pipeline.process_live_packet(
                    _race_packet(1, lap_number=1),
                    received_at_ms=1_000,
                )

                flush_started = asyncio.Event()
                release_flush = asyncio.Event()
                flush_calls = 0
                original_flush = pipeline.ingest.flush

                async def wrapped_flush():
                    nonlocal flush_calls
                    flush_calls += 1
                    if flush_calls == 1:
                        flush_started.set()
                        await release_flush.wait()
                    return await original_flush()

                with patch.object(
                    pipeline.ingest,
                    "flush",
                    new=AsyncMock(side_effect=wrapped_flush),
                ):
                    mode_task = asyncio.create_task(pipeline.set_mode("auto"))
                    await asyncio.wait_for(flush_started.wait(), timeout=1.0)

                    live_task = asyncio.create_task(
                        pipeline.process_live_packet(
                            _race_packet(2, lap_number=1, CurrentRaceTime=2.0),
                            received_at_ms=1_016,
                        )
                    )
                    await asyncio.sleep(0)
                    self.assertFalse(live_task.done())

                    release_flush.set()
                    await asyncio.wait_for(mode_task, timeout=1.0)
                    await asyncio.wait_for(live_task, timeout=1.0)

                latest_session = store.latest_sessions(limit=1)[0]
                self.assertEqual(latest_session["status"], "active")
                self.assertIsNone(latest_session["ended_reason"])
                self.assertEqual(store.count_packets(latest_session["id"]), 1)
                self.assertEqual(pipeline.capture.mode.value, "auto")
                self.assertEqual(
                    pipeline.capture.status()["phase"],
                    "receiving_not_recording",
                )

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
