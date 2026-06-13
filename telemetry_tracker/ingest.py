"""Telemetry ingest, persistence batching, and live sample publishing."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from telemetry_tracker.events import EventBus
from telemetry_tracker.car_info import car_info_from_packets
from telemetry_tracker.packet_bridge import (
    OPTIONAL_LIVE_FIELDS,
    decode_packet,
    packet_to_live_fields,
)
from telemetry_tracker.storage import TelemetryStore


@dataclass
class _PendingBatch:
    session_id: str | None = None
    raw_packets: list[bytes] = field(default_factory=list)
    decoded_packets: list[dict] = field(default_factory=list)
    samples: list[dict] = field(default_factory=list)

    def clear(self) -> None:
        self.session_id = None
        self.raw_packets.clear()
        self.decoded_packets.clear()
        self.samples.clear()


class IngestService:
    def __init__(
        self,
        store: TelemetryStore,
        bus: EventBus,
        live_decimation_hz: int = 15,
        batch_size: int = 120,
    ):
        if live_decimation_hz <= 0:
            raise ValueError("live_decimation_hz must be positive")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.store = store
        self.bus = bus
        self.live_decimation_hz = live_decimation_hz
        self.batch_size = batch_size
        self._pending = _PendingBatch()
        self._sequence = 0
        self._live_decimation_session_id: str | None = None
        self._last_live_game_timestamp_ms: int | None = None

    async def ingest_packets(
        self,
        session_id: str,
        raw_packets: list[bytes],
        start_received_at_ms: int | None = None,
    ) -> None:
        if start_received_at_ms is None:
            start_received_at_ms = int(time.time() * 1000)
        await self.bus.publish(
            {
                "type": "status",
                "state": "receiving",
                "message": f"receiving {len(raw_packets)} replay packets",
            }
        )
        for index, raw in enumerate(raw_packets):
            received_at_ms = start_received_at_ms + (index * 16)
            decoded = decode_packet(raw)
            await self.ingest_decoded_packet(
                session_id=session_id,
                raw=raw,
                decoded=decoded,
                received_at_ms=received_at_ms,
            )
        await self.bus.publish(
            {
                "type": "toast",
                "level": "success",
                "message": f"Ingested {len(raw_packets)} packets",
                "sticky": False,
            }
        )

    async def ingest_decoded_packet(
        self,
        session_id: str,
        raw: bytes,
        decoded: dict,
        received_at_ms: int,
        sample_metadata: dict | None = None,
        publish_live: bool = True,
    ) -> dict:
        """Build and persist a live/sample row from a decoded packet.

        ``sample_metadata`` lets the capture/lap pipeline add per-sample lap IDs
        and uncertainty fields while keeping Milestone 1 replay behavior intact.
        """

        self._sequence += 1
        sample = packet_to_live_fields(decoded, self._sequence, received_at_ms)
        if sample_metadata:
            sample.update(sample_metadata)
        self._ensure_optional_sample_fields(sample)
        return await self.ingest_sample(
            session_id=session_id,
            raw=raw,
            decoded=decoded,
            sample=sample,
            publish_live=publish_live,
        )

    async def ingest_sample(
        self,
        session_id: str,
        raw: bytes,
        decoded: dict,
        sample: dict,
        publish_live: bool = True,
    ) -> dict:
        """Persist one already-decoded sample and publish its decimated live event.

        Capture/lap wiring supplies samples with explicit ``lap_id`` and boundary
        metadata. Milestone 1 replay keeps using ``ingest_packets`` above, which
        builds the same sample shape without lap metadata.
        """

        if self._pending.session_id is not None and self._pending.session_id != session_id:
            await self.flush()
        stored_sample = dict(sample)
        self._ensure_optional_sample_fields(stored_sample)
        self._append_pending(session_id, raw, decoded, stored_sample)
        if publish_live and self._should_publish_live(session_id, stored_sample):
            await self.bus.publish(
                {
                    "type": "live_sample",
                    "sample": stored_sample,
                    "car": car_info_from_packets(self.store, [decoded]),
                }
            )
        if len(self._pending.raw_packets) >= self.batch_size:
            await self.flush()
        return stored_sample

    def _ensure_optional_sample_fields(self, sample: dict) -> None:
        for field_name in OPTIONAL_LIVE_FIELDS:
            sample.setdefault(field_name, None)

    def _append_pending(self, session_id: str, raw: bytes, decoded: dict, live: dict) -> None:
        if self._pending.session_id is None:
            self._pending.session_id = session_id
        if self._pending.session_id != session_id:
            raise ValueError("pending batch cannot mix sessions")
        self._pending.raw_packets.append(raw)
        self._pending.decoded_packets.append(decoded)
        self._pending.samples.append(live)

    def reset_live_decimation(self, session_id: str | None = None) -> None:
        self._live_decimation_session_id = session_id
        self._last_live_game_timestamp_ms = None

    def _should_publish_live(self, session_id: str, live: dict) -> bool:
        if self._live_decimation_session_id != session_id:
            self._live_decimation_session_id = session_id
            self._last_live_game_timestamp_ms = live["game_timestamp_ms"]
            return True
        if self._last_live_game_timestamp_ms is None:
            self._last_live_game_timestamp_ms = live["game_timestamp_ms"]
            return True
        min_delta = int(1000 / self.live_decimation_hz)
        if live["game_timestamp_ms"] - self._last_live_game_timestamp_ms >= min_delta:
            self._last_live_game_timestamp_ms = live["game_timestamp_ms"]
            return True
        return False

    async def flush(self) -> None:
        if not self._pending.raw_packets or self._pending.session_id is None:
            return
        self.store.insert_packet_batch(
            self._pending.session_id,
            list(self._pending.raw_packets),
            list(self._pending.decoded_packets),
            list(self._pending.samples),
        )
        self._pending.clear()
