"""Replay saved raw packet bytes through the tracker ingest pipeline."""

from __future__ import annotations

from pathlib import Path

from telemetry_tracker.ingest import IngestService
from telemetry_tracker.packet_bridge import iter_packet_bytes
from telemetry_tracker.storage import TelemetryStore


def _delete_session(store: TelemetryStore, session_id: str) -> None:
    with store.connect() as con:
        con.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def _discard_ingest_pending_state(ingest: IngestService) -> None:
    pending = getattr(ingest, "_pending", None)
    clear_pending = getattr(pending, "clear", None)
    if callable(clear_pending):
        clear_pending()


async def replay_raw_bytes(
    raw: bytes,
    store: TelemetryStore,
    ingest: IngestService,
    label: str = "Replay",
) -> str:
    if not raw:
        raise ValueError("raw file contains no packets")
    packets = list(iter_packet_bytes(raw))
    session_id = store.create_session(label=label)
    completed = False
    try:
        await ingest.ingest_packets(session_id, packets)
        await ingest.flush()
        completed = True
    finally:
        if not completed:
            _discard_ingest_pending_state(ingest)
            _delete_session(store, session_id)
    return session_id


async def replay_raw_file(
    raw_path: Path,
    store: TelemetryStore,
    ingest: IngestService,
    label: str = "Replay",
) -> str:
    return await replay_raw_bytes(Path(raw_path).read_bytes(), store, ingest, label=label)
