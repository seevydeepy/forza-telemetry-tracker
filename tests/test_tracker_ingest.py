import asyncio
import tempfile
import unittest
from pathlib import Path

from telemetry_tracker.events import EventBus
from telemetry_tracker.ingest import IngestService
from telemetry_tracker.packet_bridge import encode_packet_for_test
from telemetry_tracker.storage import TelemetryStore


def _drain(queue):
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


def _raw_packets(count: int) -> list[bytes]:
    return [
        encode_packet_for_test(
            {
                "TimestampMS": index * 16,
                "PositionX": float(index),
                "PositionZ": float(index * 2),
                "Speed": 20.0 + index,
            }
        )
        for index in range(count)
    ]


class EventBusTests(unittest.TestCase):
    def test_publish_drops_full_subscriber_without_blocking_healthy_subscriber(self):
        async def scenario():
            bus = EventBus(max_queue_size=1)
            stale = bus.subscribe()
            healthy = bus.subscribe()

            await bus.publish({"type": "first"})
            self.assertEqual(healthy.get_nowait()["type"], "first")

            await bus.publish({"type": "second"})
            self.assertEqual(healthy.get_nowait()["type"], "second")
            self.assertEqual(stale.get_nowait()["type"], "first")
            self.assertTrue(stale.empty())

            await bus.publish({"type": "third"})
            self.assertEqual(healthy.get_nowait()["type"], "third")
            self.assertTrue(stale.empty())

        asyncio.run(scenario())

    def test_publish_enqueues_independent_nested_payloads(self):
        async def scenario():
            bus = EventBus()
            first = bus.subscribe()
            second = bus.subscribe()
            event = {"type": "live_sample", "sample": {"sequence": 1, "speed_mps": 42.0}}

            await bus.publish(event)
            first_event = first.get_nowait()
            second_event = second.get_nowait()
            event["sample"]["speed_mps"] = 0.0
            first_event["sample"]["speed_mps"] = 99.0

            self.assertIsNot(first_event, event)
            self.assertIsNot(second_event, event)
            self.assertIsNot(first_event, second_event)
            self.assertIsNot(first_event["sample"], event["sample"])
            self.assertIsNot(second_event["sample"], event["sample"])
            self.assertIsNot(first_event["sample"], second_event["sample"])
            self.assertEqual(second_event["sample"]["speed_mps"], 42.0)

        asyncio.run(scenario())

    def test_event_bus_rejects_unbounded_queue_size(self):
        with self.assertRaisesRegex(ValueError, "max_queue_size"):
            EventBus(max_queue_size=0)


class IngestServiceTests(unittest.TestCase):
    def test_ingest_persists_all_packets_but_publishes_decimated_samples(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
                store.migrate()
                session_id = store.create_session("Replay")
                bus = EventBus()
                ingest = IngestService(store, bus, live_decimation_hz=10, batch_size=5)
                subscriber = bus.subscribe()
                raw_packets = _raw_packets(30)

                await ingest.ingest_packets(session_id, raw_packets, start_received_at_ms=1000)
                await ingest.flush()
                events = _drain(subscriber)

                self.assertEqual(store.count_packets(session_id), 30)
                samples = store.latest_samples(session_id, limit=100)
                self.assertEqual(len(samples), 30)
                self.assertEqual([sample["sequence"] for sample in samples], list(range(1, 31)))
                live_events = [event for event in events if event["type"] == "live_sample"]
                self.assertEqual(
                    [event["sample"]["game_timestamp_ms"] for event in live_events],
                    [0, 112, 224, 336, 448],
                )
                self.assertEqual(len(live_events), 5)
                self.assertLess(len(live_events), store.count_packets(session_id))
                self.assertTrue(any(event["type"] == "toast" for event in events))

        asyncio.run(scenario())

    def test_live_decimation_resets_when_new_session_restarts_timestamps(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
                store.migrate()
                first_session_id = store.create_session("Replay A")
                second_session_id = store.create_session("Replay B")
                bus = EventBus()
                ingest = IngestService(store, bus, live_decimation_hz=10)
                subscriber = bus.subscribe()
                raw_packets = _raw_packets(3)

                await ingest.ingest_packets(first_session_id, raw_packets, start_received_at_ms=1000)
                await ingest.flush()
                first_events = _drain(subscriber)

                await ingest.ingest_packets(second_session_id, raw_packets, start_received_at_ms=2000)
                await ingest.flush()
                second_events = _drain(subscriber)

                self.assertEqual(
                    [
                        event["sample"]["game_timestamp_ms"]
                        for event in first_events
                        if event["type"] == "live_sample"
                    ],
                    [0],
                )
                self.assertEqual(
                    [
                        event["sample"]["game_timestamp_ms"]
                        for event in second_events
                        if event["type"] == "live_sample"
                    ],
                    [0],
                )

        asyncio.run(scenario())

    def test_constructor_rejects_non_positive_live_decimation_hz(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            bus = EventBus()

            with self.assertRaisesRegex(ValueError, "live_decimation_hz"):
                IngestService(store, bus, live_decimation_hz=0)

            with self.assertRaisesRegex(ValueError, "live_decimation_hz"):
                IngestService(store, bus, live_decimation_hz=-1)

    def test_constructor_rejects_non_positive_batch_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            bus = EventBus()

            with self.assertRaisesRegex(ValueError, "batch_size"):
                IngestService(store, bus, batch_size=0)

            with self.assertRaisesRegex(ValueError, "batch_size"):
                IngestService(store, bus, batch_size=-1)

    def test_flush_without_packets_is_safe(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
                store.migrate()
                bus = EventBus()
                ingest = IngestService(store, bus)
                await ingest.flush()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
