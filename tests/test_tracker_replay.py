import asyncio
import tempfile
import unittest
from pathlib import Path

from telemetry_tracker.events import EventBus
from telemetry_tracker.ingest import IngestService
from telemetry_tracker.packet_bridge import encode_packet_for_test
from telemetry_tracker.replay import replay_raw_file
from telemetry_tracker.storage import TelemetryStore


def _count_sessions(store: TelemetryStore) -> int:
    with store.connect() as con:
        return int(con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])


class ReplayHarnessTests(unittest.TestCase):
    def test_replay_raw_file_creates_session_and_persists_packets(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                raw_path = root / "raw.bin"
                raw_path.write_bytes(
                    b"".join(
                        encode_packet_for_test({"TimestampMS": index * 16, "PositionX": float(index)})
                        for index in range(12)
                    )
                )
                store = TelemetryStore(root / "telemetry_tracker.sqlite3")
                store.migrate()
                bus = EventBus()
                ingest = IngestService(store, bus, live_decimation_hz=10)

                session_id = await replay_raw_file(raw_path, store, ingest, label="Replay fixture")

                self.assertEqual(store.count_packets(session_id), 12)
                self.assertEqual(len(store.latest_samples(session_id, limit=20)), 12)

        asyncio.run(scenario())

    def test_replay_rejects_partial_raw_file(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                raw_path = root / "bad.bin"
                raw_path.write_bytes(b"partial")
                store = TelemetryStore(root / "telemetry_tracker.sqlite3")
                store.migrate()
                bus = EventBus()
                ingest = IngestService(store, bus)

                with self.assertRaisesRegex(ValueError, "multiple of 324"):
                    await replay_raw_file(raw_path, store, ingest, label="Bad replay")

                self.assertEqual(_count_sessions(store), 0)

        asyncio.run(scenario())

    def test_replay_rejects_empty_raw_file_without_creating_session(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                raw_path = root / "empty.bin"
                raw_path.write_bytes(b"")
                store = TelemetryStore(root / "telemetry_tracker.sqlite3")
                store.migrate()
                bus = EventBus()
                ingest = IngestService(store, bus)

                with self.assertRaisesRegex(ValueError, "raw file contains no packets"):
                    await replay_raw_file(raw_path, store, ingest, label="Empty replay")

                self.assertEqual(_count_sessions(store), 0)

        asyncio.run(scenario())

    def test_replay_removes_created_session_when_flush_fails(self):
        class FailingFlushIngest:
            def __init__(self):
                self.session_id = None
                self.packet_count = None

            async def ingest_packets(self, session_id: str, raw_packets: list[bytes]) -> None:
                self.session_id = session_id
                self.packet_count = len(raw_packets)

            async def flush(self) -> None:
                raise RuntimeError("flush failed")

        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                raw_path = root / "raw.bin"
                raw_path.write_bytes(encode_packet_for_test({"TimestampMS": 16, "PositionX": 1.0}))
                store = TelemetryStore(root / "telemetry_tracker.sqlite3")
                store.migrate()
                ingest = FailingFlushIngest()

                with self.assertRaisesRegex(RuntimeError, "flush failed"):
                    await replay_raw_file(raw_path, store, ingest, label="Failing replay")

                self.assertIsNotNone(ingest.session_id)
                self.assertEqual(ingest.packet_count, 1)
                self.assertEqual(_count_sessions(store), 0)

        asyncio.run(scenario())

    def test_replay_removes_created_session_when_ingest_packets_fails(self):
        class FailingIngest:
            def __init__(self):
                self.session_id = None
                self.packet_count = None
                self.flush_called = False

            async def ingest_packets(self, session_id: str, raw_packets: list[bytes]) -> None:
                self.session_id = session_id
                self.packet_count = len(raw_packets)
                raise RuntimeError("ingest failed")

            async def flush(self) -> None:
                self.flush_called = True

        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                raw_path = root / "raw.bin"
                raw_path.write_bytes(encode_packet_for_test({"TimestampMS": 16, "PositionX": 1.0}))
                store = TelemetryStore(root / "telemetry_tracker.sqlite3")
                store.migrate()
                ingest = FailingIngest()

                with self.assertRaisesRegex(RuntimeError, "ingest failed"):
                    await replay_raw_file(raw_path, store, ingest, label="Failing replay")

                self.assertIsNotNone(ingest.session_id)
                self.assertEqual(ingest.packet_count, 1)
                self.assertFalse(ingest.flush_called)
                self.assertEqual(_count_sessions(store), 0)

        asyncio.run(scenario())

    def test_replay_reuses_ingest_service_after_mid_ingest_failure(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                failing_raw_path = root / "failing.bin"
                failing_raw_path.write_bytes(encode_packet_for_test({"TimestampMS": 16, "PositionX": 1.0}))
                replay_raw_path = root / "replay.bin"
                replay_raw_path.write_bytes(
                    b"".join(
                        encode_packet_for_test({"TimestampMS": index * 16, "PositionX": float(index)})
                        for index in range(2)
                    )
                )
                store = TelemetryStore(root / "telemetry_tracker.sqlite3")
                store.migrate()
                bus = EventBus()
                ingest = IngestService(store, bus)

                def fail_after_pending_append(session_id: str, live: dict) -> bool:
                    raise RuntimeError("mid-ingest failure")

                ingest._should_publish_live = fail_after_pending_append
                with self.assertRaisesRegex(RuntimeError, "mid-ingest failure"):
                    await replay_raw_file(failing_raw_path, store, ingest, label="Failing replay")

                del ingest._should_publish_live
                session_id = await replay_raw_file(replay_raw_path, store, ingest, label="Recovered replay")

                self.assertEqual(_count_sessions(store), 1)
                self.assertEqual(store.count_packets(session_id), 2)
                self.assertEqual(len(store.latest_samples(session_id, limit=20)), 2)

        asyncio.run(scenario())

    def test_replay_cancellation_cleans_pending_ingest_state(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                cancelled_raw_path = root / "cancelled.bin"
                cancelled_raw_path.write_bytes(encode_packet_for_test({"TimestampMS": 16, "PositionX": 1.0}))
                replay_raw_path = root / "replay.bin"
                replay_raw_path.write_bytes(
                    b"".join(
                        encode_packet_for_test({"TimestampMS": index * 16, "PositionX": float(index)})
                        for index in range(2)
                    )
                )
                store = TelemetryStore(root / "telemetry_tracker.sqlite3")
                store.migrate()
                bus = EventBus()
                ingest = IngestService(store, bus)
                original_publish = bus.publish
                cancelled_once = False

                async def cancel_during_live_sample(event: dict) -> None:
                    nonlocal cancelled_once
                    await original_publish(event)
                    if event.get("type") == "live_sample" and not cancelled_once:
                        cancelled_once = True
                        task = asyncio.current_task()
                        self.assertIsNotNone(task)
                        task.cancel()
                        await asyncio.sleep(0)

                bus.publish = cancel_during_live_sample
                with self.assertRaises(asyncio.CancelledError):
                    await replay_raw_file(cancelled_raw_path, store, ingest, label="Cancelled replay")

                self.assertTrue(cancelled_once)
                self.assertEqual(_count_sessions(store), 0)
                self.assertIsNone(ingest._pending.session_id)
                self.assertEqual(ingest._pending.raw_packets, [])
                self.assertEqual(ingest._pending.decoded_packets, [])
                self.assertEqual(ingest._pending.samples, [])

                bus.publish = original_publish
                session_id = await replay_raw_file(replay_raw_path, store, ingest, label="Recovered replay")

                self.assertEqual(_count_sessions(store), 1)
                self.assertEqual(store.count_packets(session_id), 2)
                self.assertEqual(len(store.latest_samples(session_id, limit=20)), 2)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
