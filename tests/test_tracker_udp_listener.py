import asyncio
import socket
import unittest

from telemetry_tracker.events import EventBus
from telemetry_tracker.packet_bridge import encode_packet_for_test
from telemetry_tracker.udp_listener import UdpTelemetryListener


def _drain(queue: asyncio.Queue) -> list[dict]:
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


async def _next_event(queue: asyncio.Queue, predicate, timeout: float = 1.0) -> dict:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise AssertionError("timed out waiting for matching listener event")
        event = await asyncio.wait_for(queue.get(), timeout=remaining)
        if predicate(event):
            return event


def _send_datagram(host: str, port: int, payload: bytes) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(payload, (host, port))


class ControlledBindUdpTelemetryListener(UdpTelemetryListener):
    def __init__(self, host: str, port: int, bus: EventBus, packet_handler):
        super().__init__(host, port, bus, packet_handler)
        self.bind_started = asyncio.Event()
        self.release_bind = asyncio.Event()
        self.bind_count = 0

    async def _bind_datagram_endpoint(self, protocol):
        self.bind_count += 1
        self.bind_started.set()
        await self.release_bind.wait()
        return await super()._bind_datagram_endpoint(protocol)


class CollectingUdpTelemetryListener(UdpTelemetryListener):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.published: list[dict] = []

    def _queue_publish(self, *events: dict) -> None:
        self.published.extend(events)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class UdpTelemetryListenerTests(unittest.TestCase):
    def test_start_binds_ephemeral_port_and_publishes_waiting_status(self):
        async def scenario():
            bus = EventBus()
            events = bus.subscribe()
            listener = UdpTelemetryListener("127.0.0.1", 0, bus, lambda raw, received_at_ms: None)
            try:
                await listener.start()

                status = listener.status()
                self.assertTrue(status["running"])
                self.assertEqual(status["state"], "waiting")
                self.assertEqual(status["requested_udp_port"], 0)
                self.assertGreater(status["udp_port"], 0)
                self.assertEqual(status["packets_received"], 0)

                event = await _next_event(
                    events,
                    lambda candidate: candidate.get("type") == "status"
                    and candidate.get("state") == "waiting",
                )
                self.assertEqual(event["udp_host"], "127.0.0.1")
                self.assertEqual(event["udp_port"], status["udp_port"])
                self.assertIn("listening", event["message"])
            finally:
                await listener.stop()
                bus.unsubscribe(events)

        asyncio.run(scenario())

    def test_receives_valid_packet_and_publishes_receiving_status(self):
        async def scenario():
            bus = EventBus()
            events = bus.subscribe()
            received = []
            received_event = asyncio.Event()

            def packet_handler(raw: bytes, received_at_ms: int) -> None:
                received.append((raw, received_at_ms))
                received_event.set()

            listener = UdpTelemetryListener("127.0.0.1", 0, bus, packet_handler)
            try:
                await listener.start()
                _drain(events)

                packet = encode_packet_for_test({"TimestampMS": 16, "Speed": 42.0})
                _send_datagram("127.0.0.1", listener.status()["udp_port"], packet)

                await asyncio.wait_for(received_event.wait(), timeout=1.0)
                self.assertEqual(len(received), 1)
                self.assertEqual(received[0][0], packet)
                self.assertIsInstance(received[0][1], int)
                self.assertGreater(received[0][1], 0)

                event = await _next_event(
                    events,
                    lambda candidate: candidate.get("type") == "status"
                    and candidate.get("state") == "receiving",
                )
                self.assertEqual(event["packets_received"], 1)
                self.assertEqual(event["udp_port"], listener.status()["udp_port"])
                self.assertEqual(listener.status()["state"], "receiving")
            finally:
                await listener.stop()
                bus.unsubscribe(events)

        asyncio.run(scenario())

    def test_packet_status_events_are_throttled_without_dropping_packets(self):
        bus = EventBus()
        clock = FakeClock()
        received = []
        listener = CollectingUdpTelemetryListener(
            "127.0.0.1",
            5400,
            bus,
            lambda raw, received_at_ms: received.append((raw, received_at_ms)),
            status_publish_interval_seconds=0.5,
            clock=clock,
        )
        packet = encode_packet_for_test({"TimestampMS": 16, "Speed": 42.0})

        listener._handle_datagram(packet)
        for _index in range(4):
            clock.advance(0.1)
            listener._handle_datagram(packet)
        clock.advance(0.1)
        listener._handle_datagram(packet)

        status_events = [
            event for event in listener.published if event.get("type") == "status"
        ]
        self.assertEqual(len(received), 6)
        self.assertEqual([event["packets_received"] for event in status_events], [1, 6])
        self.assertEqual(listener.status()["packets_received"], 6)

    def test_malformed_datagram_bypasses_packet_status_throttle(self):
        bus = EventBus()
        clock = FakeClock()
        listener = CollectingUdpTelemetryListener(
            "127.0.0.1",
            5400,
            bus,
            lambda raw, received_at_ms: None,
            status_publish_interval_seconds=60.0,
            clock=clock,
        )
        packet = encode_packet_for_test({"TimestampMS": 16, "Speed": 42.0})

        listener._handle_datagram(packet)
        listener._handle_datagram(b"not a packet")

        self.assertEqual(
            [event.get("level") for event in listener.published if event["type"] == "status"],
            [None, "warning"],
        )
        warning_toasts = [
            event
            for event in listener.published
            if event.get("type") == "toast" and event.get("level") == "warning"
        ]
        self.assertEqual(len(warning_toasts), 1)
        self.assertEqual(listener.status()["packets_received"], 1)
        self.assertEqual(listener.status()["malformed_packets"], 1)

    def test_malformed_datagram_warns_and_continues_listening(self):
        async def scenario():
            bus = EventBus()
            events = bus.subscribe()
            received = []
            received_event = asyncio.Event()

            def packet_handler(raw: bytes, received_at_ms: int) -> None:
                received.append((raw, received_at_ms))
                received_event.set()

            listener = UdpTelemetryListener("127.0.0.1", 0, bus, packet_handler)
            try:
                await listener.start()
                _drain(events)

                _send_datagram("127.0.0.1", listener.status()["udp_port"], b"not a packet")

                warning = await _next_event(
                    events,
                    lambda candidate: candidate.get("type") == "toast"
                    and candidate.get("level") == "warning",
                )
                self.assertIn("malformed", warning["message"])
                self.assertEqual(received, [])
                self.assertEqual(listener.status()["malformed_packets"], 1)
                self.assertEqual(listener.status()["packets_received"], 0)

                packet = encode_packet_for_test({"TimestampMS": 32, "Speed": 43.0})
                _send_datagram("127.0.0.1", listener.status()["udp_port"], packet)

                await asyncio.wait_for(received_event.wait(), timeout=1.0)
                self.assertEqual(len(received), 1)
                self.assertEqual(received[0][0], packet)
                self.assertEqual(listener.status()["packets_received"], 1)
            finally:
                await listener.stop()
                bus.unsubscribe(events)

        asyncio.run(scenario())

    def test_port_in_use_reports_error_status(self):
        async def scenario():
            occupying_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                occupying_socket.bind(("127.0.0.1", 0))
                occupied_port = occupying_socket.getsockname()[1]
                bus = EventBus()
                events = bus.subscribe()
                listener = UdpTelemetryListener(
                    "127.0.0.1",
                    occupied_port,
                    bus,
                    lambda raw, received_at_ms: None,
                )

                with self.assertRaises(OSError):
                    await listener.start()

                status = listener.status()
                self.assertFalse(status["running"])
                self.assertEqual(status["state"], "error")
                self.assertEqual(status["udp_port"], occupied_port)
                self.assertIn("bind", status["message"])

                error_status = await _next_event(
                    events,
                    lambda candidate: candidate.get("type") == "status"
                    and candidate.get("state") == "error",
                )
                self.assertEqual(error_status["level"], "error")
                self.assertEqual(error_status["udp_port"], occupied_port)

                error_toast = await _next_event(
                    events,
                    lambda candidate: candidate.get("type") == "toast"
                    and candidate.get("level") == "error",
                )
                self.assertTrue(error_toast["sticky"])
                self.assertIn(str(occupied_port), error_toast["message"])
                bus.unsubscribe(events)
            finally:
                occupying_socket.close()

        asyncio.run(scenario())

    def test_stop_closes_socket_and_is_idempotent(self):
        async def scenario():
            bus = EventBus()
            listener = UdpTelemetryListener("127.0.0.1", 0, bus, lambda raw, received_at_ms: None)

            await listener.start()
            bound_port = listener.status()["udp_port"]

            await listener.stop()
            stopped_status = listener.status()
            self.assertFalse(stopped_status["running"])
            self.assertEqual(stopped_status["state"], "waiting")
            self.assertIn("stopped", stopped_status["message"])

            await listener.stop()
            self.assertFalse(listener.status()["running"])

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                # The probe deliberately binds loopback only to confirm the listener released its test port.
                # codeql[py/bind-socket-all-network-interfaces]
                probe.bind(("127.0.0.1", bound_port))

        asyncio.run(scenario())

    def test_concurrent_start_calls_bind_once_and_share_socket(self):
        async def scenario():
            bus = EventBus()
            listener = ControlledBindUdpTelemetryListener(
                "127.0.0.1",
                0,
                bus,
                lambda raw, received_at_ms: None,
            )
            try:
                first_start = asyncio.create_task(listener.start())
                await asyncio.wait_for(listener.bind_started.wait(), timeout=1.0)

                second_start = asyncio.create_task(listener.start())
                await asyncio.sleep(0)
                self.assertEqual(listener.bind_count, 1)

                listener.release_bind.set()
                await asyncio.wait_for(asyncio.gather(first_start, second_start), timeout=2.0)

                status = listener.status()
                self.assertTrue(status["running"])
                self.assertGreater(status["udp_port"], 0)
                self.assertEqual(listener.bind_count, 1)
            finally:
                await listener.stop()

        asyncio.run(scenario())

    def test_stop_racing_in_progress_start_leaves_listener_stopped(self):
        async def scenario():
            bus = EventBus()
            listener = ControlledBindUdpTelemetryListener(
                "127.0.0.1",
                0,
                bus,
                lambda raw, received_at_ms: None,
            )

            start_task = asyncio.create_task(listener.start())
            await asyncio.wait_for(listener.bind_started.wait(), timeout=1.0)

            stop_task = asyncio.create_task(listener.stop())
            while listener._stop_generation == 0:
                await asyncio.sleep(0)

            listener.release_bind.set()
            await asyncio.wait_for(asyncio.gather(start_task, stop_task), timeout=2.0)

            status = listener.status()
            self.assertFalse(status["running"])
            self.assertIn("stopped", status["message"])
            self.assertGreater(status["udp_port"], 0)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(("127.0.0.1", status["udp_port"]))

        asyncio.run(scenario())

    def test_external_transport_close_marks_not_running_and_allows_restart(self):
        async def scenario():
            bus = EventBus()
            events = bus.subscribe()
            listener = UdpTelemetryListener("127.0.0.1", 0, bus, lambda raw, received_at_ms: None)
            try:
                await listener.start()
                _drain(events)
                first_port = listener.status()["udp_port"]
                transport = listener._transport
                self.assertIsNotNone(transport)

                transport.close()

                close_event = await _next_event(
                    events,
                    lambda candidate: candidate.get("type") == "status"
                    and not candidate.get("running")
                    and "closed" in candidate.get("message", ""),
                )
                self.assertFalse(close_event["running"])
                self.assertFalse(listener.status()["running"])

                await listener.start()
                restarted_status = listener.status()
                self.assertTrue(restarted_status["running"])
                self.assertGreater(restarted_status["udp_port"], 0)
                self.assertNotEqual(restarted_status["message"], close_event["message"])
                self.assertGreaterEqual(restarted_status["udp_port"], 1)
                self.assertGreater(first_port, 0)
            finally:
                await listener.stop()
                bus.unsubscribe(events)

        asyncio.run(scenario())

    def test_async_packet_handler_receives_timestamp_and_stop_waits_for_completion(self):
        async def scenario():
            bus = EventBus()
            received = []
            handler_started = asyncio.Event()
            release_handler = asyncio.Event()
            handler_completed = asyncio.Event()

            async def packet_handler(raw: bytes, received_at_ms: int) -> None:
                received.append((raw, received_at_ms))
                handler_started.set()
                await release_handler.wait()
                handler_completed.set()

            listener = UdpTelemetryListener("127.0.0.1", 0, bus, packet_handler)
            try:
                await listener.start()
                packet = encode_packet_for_test({"TimestampMS": 48, "Speed": 44.0})
                _send_datagram("127.0.0.1", listener.status()["udp_port"], packet)

                await asyncio.wait_for(handler_started.wait(), timeout=1.0)
                self.assertEqual(len(received), 1)
                self.assertEqual(received[0][0], packet)
                self.assertIsInstance(received[0][1], int)
                self.assertGreater(received[0][1], 0)

                stop_task = asyncio.create_task(listener.stop())
                await asyncio.sleep(0)
                self.assertFalse(stop_task.done())

                release_handler.set()
                await asyncio.wait_for(stop_task, timeout=2.0)
                self.assertTrue(handler_completed.is_set())
                self.assertFalse(listener.status()["running"])
            finally:
                if listener.status()["running"]:
                    release_handler.set()
                    await listener.stop()

        asyncio.run(scenario())

    def test_async_packet_handler_error_reports_and_later_packets_continue(self):
        async def scenario():
            bus = EventBus()
            events = bus.subscribe()
            attempts = 0
            successful_packets = []
            success_event = asyncio.Event()

            async def packet_handler(raw: bytes, received_at_ms: int) -> None:
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise RuntimeError("handler boom")
                successful_packets.append((raw, received_at_ms))
                success_event.set()

            listener = UdpTelemetryListener("127.0.0.1", 0, bus, packet_handler)
            try:
                await listener.start()
                _drain(events)

                first_packet = encode_packet_for_test({"TimestampMS": 64, "Speed": 45.0})
                _send_datagram("127.0.0.1", listener.status()["udp_port"], first_packet)

                first_packet_events = [
                    await asyncio.wait_for(events.get(), timeout=1.0)
                    for _index in range(3)
                ]
                receiving_status, error_status, error_toast = first_packet_events
                self.assertEqual(receiving_status["type"], "status")
                self.assertEqual(receiving_status["state"], "receiving")
                self.assertEqual(receiving_status["packets_received"], 1)
                self.assertEqual(error_status["level"], "error")
                self.assertEqual(error_status["type"], "status")
                self.assertEqual(error_status["state"], "error")
                self.assertIn("handler boom", error_status["message"])
                self.assertEqual(error_toast["type"], "toast")
                self.assertEqual(error_toast["level"], "error")
                self.assertTrue(error_toast["sticky"])
                self.assertIn("handler boom", error_toast["message"])
                self.assertTrue(listener.status()["running"])

                second_packet = encode_packet_for_test({"TimestampMS": 80, "Speed": 46.0})
                _send_datagram("127.0.0.1", listener.status()["udp_port"], second_packet)

                await asyncio.wait_for(success_event.wait(), timeout=1.0)
                self.assertEqual(len(successful_packets), 1)
                self.assertEqual(successful_packets[0][0], second_packet)

                receiving_status = await _next_event(
                    events,
                    lambda candidate: candidate.get("type") == "status"
                    and candidate.get("state") == "receiving"
                    and candidate.get("packets_received") == 2,
                )
                self.assertEqual(receiving_status["udp_port"], listener.status()["udp_port"])
                self.assertEqual(listener.status()["state"], "receiving")
            finally:
                await listener.stop()
                bus.unsubscribe(events)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
