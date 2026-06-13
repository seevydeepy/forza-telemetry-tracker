"""Async UDP telemetry listener for FH Data Out packets."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from telemetry_tracker.events import EventBus
from telemetry_tracker.packet_bridge import PACKET_SIZE


PacketHandler = Callable[[bytes, int], object]
DEFAULT_STATUS_PUBLISH_INTERVAL_SECONDS = 0.25


class _TelemetryDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, listener: "UdpTelemetryListener", closed: asyncio.Future):
        self._listener = listener
        self._closed = closed

    def datagram_received(self, data: bytes, addr) -> None:
        self._listener._handle_datagram(bytes(data))

    def error_received(self, exc: Exception) -> None:
        self._listener._report_socket_error(exc)

    def connection_lost(self, exc: Exception | None) -> None:
        self._listener._connection_lost(self, exc)
        if not self._closed.done():
            self._closed.set_result(None)


class UdpTelemetryListener:
    """Bind a UDP socket, validate packet-sized datagrams, and forward raw packets."""

    def __init__(
        self,
        host: str,
        port: int,
        bus: EventBus,
        packet_handler: PacketHandler,
        *,
        status_publish_interval_seconds: float = DEFAULT_STATUS_PUBLISH_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.host = host
        self.port = int(port)
        self.bus = bus
        self.packet_handler = packet_handler
        self._status_publish_interval_seconds = max(
            0.0,
            float(status_publish_interval_seconds),
        )
        self._clock = clock
        self._last_packet_status_published_at: float | None = None

        self._lifecycle_lock = asyncio.Lock()
        self._stop_generation = 0
        self._transport: asyncio.DatagramTransport | None = None
        self._closed: asyncio.Future | None = None
        self._protocol: _TelemetryDatagramProtocol | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._background_tasks: set[asyncio.Task] = set()

        self._actual_port = self.port
        self._state = "waiting"
        self._message = "waiting for telemetry"
        self._packets_received = 0
        self._malformed_packets = 0
        self._last_received_at_ms: int | None = None
        self._last_error: str | None = None

    async def start(self) -> None:
        """Bind the UDP socket and publish a waiting/listening status event."""

        requested_stop_generation = self._stop_generation
        async with self._lifecycle_lock:
            if requested_stop_generation != self._stop_generation:
                self._state = "waiting"
                self._message = "listener stopped before start completed"
                await self._publish_status()
                return

            if self._transport is not None:
                await self._publish_status()
                return

            self._loop = asyncio.get_running_loop()
            self._state = "starting"
            self._message = f"binding UDP listener on {self.host}:{self.port}"
            self._last_error = None
            closed = self._loop.create_future()
            protocol = _TelemetryDatagramProtocol(self, closed)

            try:
                transport = await self._bind_datagram_endpoint(protocol)
            except OSError as exc:
                self._state = "error"
                self._actual_port = self.port
                self._last_error = str(exc)
                self._message = f"failed to bind UDP listener on {self.host}:{self.port}: {exc}"
                await self._publish_status(level="error")
                await self.bus.publish(
                    {
                        "type": "toast",
                        "level": "error",
                        "message": self._message,
                        "sticky": True,
                    }
                )
                raise

            sock = transport.get_extra_info("socket")
            if sock is not None:
                self._actual_port = int(sock.getsockname()[1])

            if requested_stop_generation != self._stop_generation:
                await self._close_transport(transport, closed)
                self._state = "waiting"
                self._message = "listener stopped before start completed"
                await self._publish_status()
                return

            self._transport = transport
            self._closed = closed
            self._protocol = protocol
            self._state = "waiting"
            self._message = f"listening for UDP telemetry on {self.host}:{self._actual_port}"
            await self._publish_status()

    async def stop(self) -> None:
        """Close the UDP socket and wait for listener-owned background work."""

        self._stop_generation += 1
        async with self._lifecycle_lock:
            transport = self._transport
            closed = self._closed
            self._transport = None
            self._closed = None
            self._protocol = None

            if transport is not None and closed is not None:
                await self._close_transport(transport, closed)

            await self._drain_background_tasks()
            self._state = "waiting"
            self._message = "listener stopped"
            await self._publish_status()

    def status(self) -> dict:
        """Return a snapshot of listener state, including the actual bound port."""

        payload = self._status_payload()
        payload.pop("type", None)
        return payload

    def _handle_datagram(self, raw: bytes) -> None:
        if len(raw) != PACKET_SIZE:
            self._malformed_packets += 1
            self._message = f"ignored malformed UDP datagram ({len(raw)} bytes; expected {PACKET_SIZE})"
            self._last_error = self._message
            self._queue_publish(
                self._status_payload(level="warning"),
                {
                    "type": "toast",
                    "level": "warning",
                    "message": self._message,
                    "sticky": False,
                },
            )
            return

        previous_state = self._state
        previous_error = self._last_error
        received_at_ms = int(time.time() * 1000)
        self._packets_received += 1
        self._last_received_at_ms = received_at_ms
        self._state = "receiving"
        self._message = f"receiving UDP telemetry on {self.host}:{self._actual_port}"
        self._last_error = None

        try:
            result = self.packet_handler(raw, received_at_ms)
        except Exception as exc:  # pragma: no cover - defensive path for application handlers
            self._report_handler_error(exc)
            return

        if self._should_publish_packet_status(
            force=previous_state != "receiving" or previous_error is not None
        ):
            self._queue_publish(self._status_payload())
        if hasattr(result, "__await__"):
            self._track_task(self._await_handler(result))

    def _should_publish_packet_status(self, *, force: bool = False) -> bool:
        interval = self._status_publish_interval_seconds
        if interval <= 0:
            return True

        now = self._clock()
        if force:
            self._last_packet_status_published_at = now
            return True
        if (
            self._last_packet_status_published_at is None
            or now - self._last_packet_status_published_at >= interval
        ):
            self._last_packet_status_published_at = now
            return True
        return False

    async def _bind_datagram_endpoint(
        self,
        protocol: _TelemetryDatagramProtocol,
    ) -> asyncio.DatagramTransport:
        if self._loop is None:
            raise RuntimeError("listener has no running event loop")
        transport, _ = await self._loop.create_datagram_endpoint(
            lambda: protocol,
            local_addr=(self.host, self.port),
        )
        return transport

    async def _close_transport(
        self,
        transport: asyncio.DatagramTransport,
        closed: asyncio.Future,
    ) -> None:
        transport.close()
        if not closed.done():
            try:
                await asyncio.wait_for(asyncio.shield(closed), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    def _connection_lost(
        self,
        protocol: _TelemetryDatagramProtocol,
        exc: Exception | None,
    ) -> None:
        if protocol is not self._protocol:
            return

        self._transport = None
        self._closed = None
        self._protocol = None
        if exc is None:
            self._state = "waiting"
            self._message = "UDP listener transport closed"
            self._last_error = None
            self._queue_publish(self._status_payload())
        else:
            self._state = "error"
            self._last_error = str(exc)
            self._message = f"UDP listener socket error: {exc}"
            self._queue_publish(
                self._status_payload(level="error"),
                {
                    "type": "toast",
                    "level": "error",
                    "message": self._message,
                    "sticky": True,
                },
            )

    def _report_socket_error(self, exc: Exception) -> None:
        self._state = "error"
        self._last_error = str(exc)
        self._message = f"UDP listener socket error: {exc}"
        self._queue_publish(
            self._status_payload(level="error"),
            {
                "type": "toast",
                "level": "error",
                "message": self._message,
                "sticky": True,
            },
        )

    def _report_handler_error(self, exc: Exception) -> None:
        self._state = "error"
        self._last_error = str(exc)
        self._message = f"UDP packet handler error: {exc}"
        self._queue_publish(
            self._status_payload(level="error"),
            {
                "type": "toast",
                "level": "error",
                "message": self._message,
                "sticky": True,
            },
        )

    async def _await_handler(self, awaitable: Awaitable) -> None:
        try:
            await awaitable
        except Exception as exc:  # pragma: no cover - defensive path for application handlers
            self._state = "error"
            self._last_error = str(exc)
            self._message = f"UDP packet handler error: {exc}"
            await self._publish_status(level="error")
            await self.bus.publish(
                {
                    "type": "toast",
                    "level": "error",
                    "message": self._message,
                    "sticky": True,
                }
            )

    async def _publish_status(self, level: str | None = None) -> None:
        await self.bus.publish(self._status_payload(level=level))

    def _queue_publish(self, *events: dict) -> None:
        async def publish_all() -> None:
            for event in events:
                await self.bus.publish(event)

        self._track_task(publish_all())

    def _track_task(self, awaitable: Awaitable) -> None:
        if self._loop is None or self._loop.is_closed():
            return
        task = self._loop.create_task(awaitable)
        self._background_tasks.add(task)

        def task_done(done_task: asyncio.Task) -> None:
            self._background_tasks.discard(done_task)
            try:
                done_task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # pragma: no cover - EventBus publish is not expected to fail
                self._last_error = str(exc)

        task.add_done_callback(task_done)

    async def _drain_background_tasks(self) -> None:
        current = asyncio.current_task()
        while True:
            tasks = [task for task in self._background_tasks if task is not current]
            if not tasks:
                return
            await asyncio.gather(*tasks, return_exceptions=True)

    def _status_payload(self, level: str | None = None) -> dict:
        payload = {
            "type": "status",
            "state": self._state,
            "udp_host": self.host,
            "udp_port": self._actual_port,
            "requested_udp_port": self.port,
            "running": self._transport is not None,
            "packets_received": self._packets_received,
            "malformed_packets": self._malformed_packets,
            "message": self._message,
        }
        if self._last_received_at_ms is not None:
            payload["last_received_at_ms"] = self._last_received_at_ms
        if self._last_error is not None:
            payload["error"] = self._last_error
        if level is not None:
            payload["level"] = level
        return payload
