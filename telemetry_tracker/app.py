"""FastAPI app for the local Forza Telemetry Tracker."""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from telemetry_tracker.app_metadata import load_release_metadata
from telemetry_tracker.app_paths import DesktopPaths, default_desktop_paths
from telemetry_tracker.app_updates import (
    FORZA_APP_ACTION_HEADER,
    FORZA_APP_ACTION_VALUE,
    UpdateError,
    UpdateService,
    UpdateUnsupported,
    UpdateVerificationError,
)
from telemetry_tracker.car_catalog import load_local_fh6_catalog
from telemetry_tracker.car_info import (
    car_identity_from_packet,
    car_info_for_lap,
    car_info_from_packet_bytes,
)
from telemetry_tracker.capture import CapturePhase, CaptureStateMachine, has_race_packet_signal
from telemetry_tracker.comparison import (
    DEFAULT_SCOPE,
    SUPPORTED_SCOPES,
    context_key_for_lap,
    delta_summary,
    ghost_samples_for_reference,
    select_reference_lap,
)
from telemetry_tracker.diagnostics import diagnostics_payload
from telemetry_tracker.events import EventBus
from telemetry_tracker.export import (
    TelemetryExportKind,
    TelemetryExportResult,
    export_estimate,
    export_telemetry,
)
from telemetry_tracker.ingest import IngestService
from telemetry_tracker.lap_detection import LapDetector
from telemetry_tracker.lap_quality import evaluate_auto_lap
from telemetry_tracker.analysis import analyze_lap, summarize_samples, summarize_section
from telemetry_tracker.lap_summaries import compute_lap_summary
from telemetry_tracker.packet_bridge import PACKET_SIZE, decode_packet, iter_packet_bytes
from telemetry_tracker.replay import replay_raw_bytes, replay_raw_file
from telemetry_tracker.rules import load_default_ruleset
from telemetry_tracker.storage import LOCAL_USER_ID, TelemetryStore
from telemetry_tracker.track_catalog import load_local_fh6_track_catalog
from telemetry_tracker.track_matcher import MATCHER_VERSION, match_lap_track
from telemetry_tracker.track_assets import validate_asset, validate_transform
from telemetry_tracker.udp_listener import UdpTelemetryListener
from telemetry_tracker.github_token_store import TokenStorageUnavailable
from telemetry_tracker.world_map import (
    build_world_map_cache,
    safe_cache_tile_path,
    tile_set_uses_current_tile_coordinates,
    world_map_status_payload,
)


OVERLAY_IDS = (
    "issues",
    "speed",
    "inputs",
    "grip",
    "temperature",
    "suspension",
    "rpm",
)
UNIT_SYSTEMS = frozenset({"imperial", "metric"})
RAW_TELEMETRY_UPLOAD_MAX_BYTES = 512 * 1024 * 1024
RAW_TELEMETRY_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024
RAW_TELEMETRY_IMPORT_MAX_FILES = 500
RAW_TELEMETRY_IMPORT_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
RAW_TELEMETRY_IMPORT_PROGRESS_PACKET_INTERVAL = 120
RAW_TELEMETRY_IMPORT_ERROR_LIMIT = 20
FH6_MEDIA_ROOT_ENV = "FH6_MEDIA_ROOT"
FH6_REFRESH_CAR_CATALOG_ENV = "FH6_REFRESH_CAR_CATALOG"
FH6_REFRESH_TRACK_CATALOG_ENV = "FH6_REFRESH_TRACK_CATALOG"
DEFAULT_FH6_MEDIA_ROOT = Path(r"G:\SteamLibrary\steamapps\common\ForzaHorizon6\media")

ANALYSIS_SUMMARY_KEYS = frozenset(
    {
        "packet_count",
        "top_speed_mps",
        "average_speed_mps",
        "peak_combined_slip",
        "limiter_samples",
        "bottoming_events",
        "start_sequence",
        "end_sequence",
    }
)


class TelemetryExportJobRequest(BaseModel):
    kind: str | None = None
    output_dir: str | None = None
    outputDir: str | None = None
    filename_prefix: str | None = None
    filenamePrefix: str | None = None

    def selected_kind(self) -> TelemetryExportKind:
        try:
            return TelemetryExportKind(self.kind or TelemetryExportKind.raw_csv.value)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in TelemetryExportKind)
            raise ValueError(f"kind must be one of: {allowed}") from exc

    def selected_output_dir(self, default_output_dir: Path) -> str:
        value = self.output_dir if self.output_dir is not None else self.outputDir
        return str(default_output_dir if value is None else value)

    def selected_filename_prefix(self) -> str:
        value = self.filename_prefix if self.filename_prefix is not None else self.filenamePrefix
        return "forza-telemetry-tracker" if value is None else str(value)


class ReplayRequest(BaseModel):
    raw_path: str
    label: str = "API replay"
    recording_mode: bool = False


class CaptureModeRequest(BaseModel):
    mode: str | None = None
    capture_mode: str | None = None

    def selected_mode(self) -> str:
        mode = self.mode if self.mode is not None else self.capture_mode
        if mode is None:
            raise ValueError("mode must be 'auto' or 'manual'")
        return mode


class SessionStartRequest(BaseModel):
    label: str | None = None


class SessionUpdateRequest(BaseModel):
    label: str


class VisualiserSettingsRequest(BaseModel):
    unit_system: str | None = None
    unitSystem: str | None = None
    preferred_overlay: str | None = None
    preferredOverlay: str | None = None

    def selected_unit_system(self) -> str | None:
        unit_system = self.unit_system if self.unit_system is not None else self.unitSystem
        if unit_system is None:
            return None
        normalized = unit_system.strip().lower()
        if normalized not in UNIT_SYSTEMS:
            raise ValueError("unit_system must be 'imperial' or 'metric'")
        return normalized

    def selected_preferred_overlay(self) -> str | None:
        preferred_overlay = self.preferred_overlay if self.preferred_overlay is not None else self.preferredOverlay
        if preferred_overlay is None:
            return None
        normalized = preferred_overlay.strip().lower()
        if normalized not in OVERLAY_IDS:
            raise ValueError(f"preferred_overlay must be one of: {', '.join(OVERLAY_IDS)}")
        return normalized


class WorldMapSettingsRequest(BaseModel):
    fh6_media_root: str | None = None
    fh6MediaRoot: str | None = None
    world_map_enabled: bool | None = None
    worldMapEnabled: bool | None = None
    world_map_season: str | None = None
    worldMapSeason: str | None = None

    def selected_media_root(self, current: dict) -> str | None:
        if self.fh6_media_root is not None:
            return self.fh6_media_root
        if self.fh6MediaRoot is not None:
            return self.fh6MediaRoot
        return current.get("fh6_media_root")

    def selected_enabled(self, current: dict) -> bool:
        if self.world_map_enabled is not None:
            return bool(self.world_map_enabled)
        if self.worldMapEnabled is not None:
            return bool(self.worldMapEnabled)
        return bool(current.get("world_map_enabled", False))

    def selected_season(self, current: dict) -> str:
        if self.world_map_season is not None:
            return str(self.world_map_season)
        if self.worldMapSeason is not None:
            return str(self.worldMapSeason)
        return str(current.get("world_map_season") or "summer")


class WorldMapBuildRequest(BaseModel):
    season: str | None = None


class TrackProfileCreateRequest(BaseModel):
    name: str | None = None
    layout: str | None = None
    source: str | None = None
    confidence: str | None = None
    shape_signature: str | None = None


class TrackProfileUpdateRequest(BaseModel):
    name: str | None = None
    layout: str | None = None


class TrackProfileAssignRequest(BaseModel):
    session_id: str | None = None
    sessionId: str | None = None
    lap_id: str | None = None
    lapId: str | None = None

    def selected_session_id(self) -> str:
        return _required_text_value(
            self.session_id if self.session_id is not None else self.sessionId,
            "session_id",
        )

    def selected_lap_id(self) -> str | None:
        lap_id = self.lap_id if self.lap_id is not None else self.lapId
        return None if lap_id is None else _required_text_value(lap_id, "lap_id")


class TrackProfileMergeRequest(BaseModel):
    keep_profile_id: str | None = None
    keepProfileId: str | None = None
    merge_profile_id: str | None = None
    mergeProfileId: str | None = None

    def selected_keep_profile_id(self) -> str:
        return _required_text_value(
            self.keep_profile_id
            if self.keep_profile_id is not None
            else self.keepProfileId,
            "keep_profile_id",
        )

    def selected_merge_profile_id(self) -> str:
        return _required_text_value(
            self.merge_profile_id
            if self.merge_profile_id is not None
            else self.mergeProfileId,
            "merge_profile_id",
        )


class AppUpdateCheckRequest(BaseModel):
    force: bool = False


class AppUpdateInstallRequest(BaseModel):
    version: str | None = None


class AppUpdateTokenRequest(BaseModel):
    token: str


class TrackAssetCreateRequest(BaseModel):
    filename: str | None = None
    source_path: str | None = None
    sourcePath: str | None = None
    mime_type: str | None = None
    mimeType: str | None = None
    size_bytes: int | None = None
    sizeBytes: int | None = None
    transform: dict | None = None

    def selected_source_path(self) -> str:
        return _required_text_value(
            self.source_path if self.source_path is not None else self.sourcePath,
            "source_path",
        )

    def selected_mime_type(self) -> str:
        return _required_text_value(
            self.mime_type if self.mime_type is not None else self.mimeType,
            "mime_type",
        )

    def selected_size_bytes(self) -> int:
        value = self.size_bytes if self.size_bytes is not None else self.sizeBytes
        if value is None:
            raise ValueError("size_bytes is required")
        return int(value)


class TrackAssetTransformRequest(BaseModel):
    scale: float | None = None
    rotate_deg: float | None = None
    rotateDeg: float | None = None
    translate_x: float | None = None
    translateX: float | None = None
    translate_y: float | None = None
    translateY: float | None = None
    transform: dict | None = None

    def selected_transform(self) -> dict:
        if self.transform is not None:
            return self.transform
        return {
            "scale": self.scale,
            "rotate_deg": self.rotate_deg if self.rotate_deg is not None else self.rotateDeg,
            "translate_x": self.translate_x if self.translate_x is not None else self.translateX,
            "translate_y": self.translate_y if self.translate_y is not None else self.translateY,
        }


def _positive_int(value) -> int | None:
    if value is None:
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric > 0 else None


def _has_reliable_car_identity(identity: dict | None) -> bool:
    if identity is None:
        return False
    # FH Data Out transition/menu packets can retain class/drivetrain while
    # reporting default car fields such as ordinal 0 or PI 0.  Those packets are
    # useful to record, but they are not strong enough evidence for splitting a
    # user-visible session.
    return (
        _positive_int(identity.get("car_ordinal")) is not None
        and _positive_int(identity.get("car_performance_index")) is not None
    )


ReplayProgressCallback = Callable[[int, int], Awaitable[None] | None]


def _discard_ingest_pending_state(ingest: IngestService) -> None:
    pending = getattr(ingest, "_pending", None)
    clear_pending = getattr(pending, "clear", None)
    if callable(clear_pending):
        clear_pending()


def _raw_packet_count_for_path(raw_path: Path) -> int:
    size = raw_path.stat().st_size
    if size <= 0:
        raise ValueError("raw file contains no packets")
    if size % PACKET_SIZE != 0:
        raise ValueError(f"raw telemetry bytes must be a multiple of {PACKET_SIZE}")
    return size // PACKET_SIZE


def _iter_raw_packet_file(raw_path: Path) -> Iterable[bytes]:
    with raw_path.open("rb") as source:
        while True:
            packet = source.read(PACKET_SIZE)
            if not packet:
                return
            if len(packet) != PACKET_SIZE:
                raise ValueError(f"raw telemetry bytes must be a multiple of {PACKET_SIZE}")
            yield packet


async def _maybe_await(value: Awaitable[None] | None) -> None:
    if value is not None:
        await value


@dataclass(frozen=True)
class RawTelemetryImportSource:
    display_name: str
    staged_path: Path
    size_bytes: int


@dataclass
class TelemetryExportJob:
    id: str
    kind: TelemetryExportKind
    label: str
    output_dir: str
    filename_prefix: str
    created_at_ms: int
    status: str = "queued"
    status_text: str = "Queued"
    progress: float = 0.0
    output_files: list[dict] = field(default_factory=list)
    total_size_bytes: int = 0
    row_count: int = 0
    started_at_ms: int | None = None
    completed_at_ms: int | None = None
    duration_ms: int | None = None
    error: str | None = None
    cancel_requested: bool = False
    task: asyncio.Task | None = field(default=None, repr=False, compare=False)

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "label": self.label,
            "status": self.status,
            "status_text": self.status_text,
            "progress": self.progress,
            "output_dir": self.output_dir,
            "filename_prefix": self.filename_prefix,
            "output_files": list(self.output_files),
            "total_size_bytes": self.total_size_bytes,
            "row_count": self.row_count,
            "created_at_ms": self.created_at_ms,
            "started_at_ms": self.started_at_ms,
            "completed_at_ms": self.completed_at_ms,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "can_cancel": self.status in {"queued", "running", "cancelling"},
        }


@dataclass
class RawTelemetryImportJob:
    id: str
    label: str
    source_type: str
    files: list[RawTelemetryImportSource]
    staged_dir: Path
    total_bytes: int
    created_at_ms: int
    status: str = "queued"
    status_text: str = "Queued"
    progress: float = 0.0
    processed_files: int = 0
    failed_files: int = 0
    packet_count: int = 0
    session_ids: list[str] = field(default_factory=list)
    lap_ids: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    error_count: int = 0
    current_file: str | None = None
    current_file_index: int | None = None
    current_file_packets: int = 0
    current_file_packets_processed: int = 0
    started_at_ms: int | None = None
    completed_at_ms: int | None = None
    cancel_requested: bool = False
    task: asyncio.Task | None = field(default=None, repr=False, compare=False)

    @property
    def total_files(self) -> int:
        return len(self.files)

    def add_error(self, source: RawTelemetryImportSource | None, message: str) -> None:
        self.error_count += 1
        if len(self.errors) < RAW_TELEMETRY_IMPORT_ERROR_LIMIT:
            self.errors.append(
                {
                    "file": source.display_name if source is not None else None,
                    "message": str(message),
                }
            )

    def update_file_progress(self, processed_packets: int, total_packets: int) -> None:
        self.current_file_packets = max(0, int(total_packets))
        self.current_file_packets_processed = max(0, int(processed_packets))
        file_fraction = (
            min(1.0, self.current_file_packets_processed / self.current_file_packets)
            if self.current_file_packets > 0
            else 0.0
        )
        self.progress = min(
            1.0,
            max(0.0, (self.processed_files + file_fraction) / max(1, self.total_files)),
        )

    def mark_terminal(self, status: str, text: str) -> None:
        self.status = status
        self.status_text = text
        self.current_file = None
        self.current_file_index = None
        self.current_file_packets = 0
        self.current_file_packets_processed = 0
        self.progress = 1.0
        self.completed_at_ms = int(time.time() * 1000)

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "source_type": self.source_type,
            "status": self.status,
            "status_text": self.status_text,
            "progress": self.progress,
            "created_at_ms": self.created_at_ms,
            "started_at_ms": self.started_at_ms,
            "completed_at_ms": self.completed_at_ms,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "total_bytes": self.total_bytes,
            "packet_count": self.packet_count,
            "session_ids": list(self.session_ids),
            "lap_ids": list(self.lap_ids),
            "current_file": self.current_file,
            "current_file_index": self.current_file_index,
            "current_file_packets": self.current_file_packets,
            "current_file_packets_processed": self.current_file_packets_processed,
            "errors": list(self.errors),
            "error_count": self.error_count,
            "can_cancel": self.status in {"queued", "running"},
        }

class CapturePipeline:
    """Wire raw packets through capture, lap detection, storage, and live ingest."""

    def __init__(
        self,
        store: TelemetryStore,
        bus: EventBus,
        ingest: IngestService,
        capture: CaptureStateMachine,
        lap_detector: LapDetector,
        use_active_sessions: bool = True,
        *,
        count_lifetime_stats: bool = True,
    ) -> None:
        self.store = store
        self.bus = bus
        self.ingest = ingest
        self.capture = capture
        self.lap_detector = lap_detector
        self.use_active_sessions = use_active_sessions
        self.count_lifetime_stats = count_lifetime_stats
        self._capture_lock = asyncio.Lock()
        self._session_ids: dict[int, str] = {}
        self._lap_ids: dict[int, str] = {}
        self._auto_lap_ids: dict[int, bool] = {}
        self._created_session_ids: list[str] = []
        self._last_ignored_race_toast_ms_by_reason: dict[str, int] = {}
        self._last_is_race_on: bool | None = None

    async def process_live_packet(
        self,
        raw: bytes,
        received_at_ms: int | None = None,
        label: str = "Live capture",
    ) -> None:
        """Process one raw packet received by live UDP or replay emulation."""

        async with self._capture_lock:
            await self._process_live_packet_unlocked(
                raw,
                received_at_ms=received_at_ms,
                label=label,
            )

    async def start_manual(self) -> dict:
        """Start manual capture and persist any rolling pre-buffer packets."""

        async with self._capture_lock:
            if self.capture.mode.value != "manual":
                self.capture.set_mode("manual")
            packets_to_flush = self.capture.start_manual()
            if self.use_active_sessions and self.store.active_session() is None:
                self.store.start_session()
            if packets_to_flush:
                await self._record_prebuffer_packets(
                    packets_to_flush,
                    int(time.time() * 1000),
                    "Manual capture",
                )
            await self.bus.publish({"type": "capture", **self.capture.status()})
            return self.capture.status()

    async def set_mode(self, mode: str) -> dict:
        """Switch capture mode while serializing live packet processing."""

        async with self._capture_lock:
            mode_changes = mode != self.capture.mode.value
            if mode_changes and self.capture.status()["recording"]["active"]:
                await self._finalize_open_records_unlocked(
                    reason="capture_mode_change",
                    reset_detector=True,
                    finalize_sessions=not self.use_active_sessions,
                )
            self.capture.set_mode(mode)
            self._last_is_race_on = None
            await self.bus.publish({"type": "capture", **self.capture.status()})
            return self.capture.status()

    async def stop_manual(self) -> dict:
        """Stop manual capture and finalize any open storage records."""

        async with self._capture_lock:
            self.capture.stop_manual()
            await self._finalize_open_records_unlocked(
                reason="manual_stop",
                reset_detector=True,
                finalize_sessions=False,
            )
            await self.bus.publish({"type": "capture", **self.capture.status()})
            return self.capture.status()

    async def replay_packets(self, packets: list[bytes], label: str) -> list[str]:
        """Replay packets through the recording pipeline and finalize the replay run."""

        return await self.replay_packet_iterable(
            packets,
            label=label,
            total_packets=len(packets),
        )

    async def replay_packet_iterable(
        self,
        packets: Iterable[bytes],
        *,
        label: str,
        total_packets: int,
        event_bus: EventBus | None = None,
        progress_callback: ReplayProgressCallback | None = None,
    ) -> list[str]:
        """Replay packets through an isolated recording pipeline.

        ``event_bus`` lets background import jobs avoid flooding the live SSE bus
        while still reusing the same session/lap/analysis pipeline.
        """

        replay_pipeline = self._new_replay_pipeline(event_bus=event_bus)
        start_received_at_ms = int(time.time() * 1000)
        completed = False
        try:
            if progress_callback is not None:
                await _maybe_await(progress_callback(0, total_packets))
            for index, raw in enumerate(packets):
                await replay_pipeline.process_live_packet(
                    raw,
                    received_at_ms=start_received_at_ms + (index * 16),
                    label=label,
                )
                processed = index + 1
                if (
                    progress_callback is not None
                    and (
                        processed == total_packets
                        or processed % RAW_TELEMETRY_IMPORT_PROGRESS_PACKET_INTERVAL == 0
                    )
                ):
                    await _maybe_await(progress_callback(processed, total_packets))
            await replay_pipeline.finalize_open_records(
                reason="replay_complete",
                reset_detector=False,
                finalize_sessions=True,
            )
            completed = True
            return list(replay_pipeline._created_session_ids)
        finally:
            if not completed:
                _discard_ingest_pending_state(replay_pipeline.ingest)
                for session_id in reversed(replay_pipeline._created_session_ids):
                    with contextlib.suppress(ValueError):
                        self.store.delete_session(session_id)

    def _new_replay_pipeline(self, event_bus: EventBus | None = None) -> "CapturePipeline":
        replay_bus = event_bus if event_bus is not None else self.bus
        replay_capture = CaptureStateMachine(mode="manual", prebuffer_packets=0)
        replay_capture.start_manual()
        replay_ingest = IngestService(
            self.store,
            replay_bus,
            live_decimation_hz=self.ingest.live_decimation_hz,
            batch_size=self.ingest.batch_size,
        )
        return CapturePipeline(
            self.store,
            replay_bus,
            replay_ingest,
            replay_capture,
            LapDetector(),
            use_active_sessions=False,
            count_lifetime_stats=False,
        )

    async def start_new_session(self, label: str | None = None) -> str:
        """Start a new active user session while holding the capture lock."""

        async with self._capture_lock:
            await self._finalize_open_records_unlocked(
                reason="new_session_started",
                reset_detector=True,
                finalize_sessions=False,
            )
            self._session_ids.clear()
            return self.store.start_session(label=label)

    async def activate_session(self, session_id: str) -> dict:
        """Make an existing session the active recording target."""

        async with self._capture_lock:
            target = self.store.session(session_id)
            if target is None:
                raise ValueError(f"unknown session_id: {session_id}")
            active = self.store.active_session()
            switching_sessions = active is None or str(active["id"]) != session_id
            if switching_sessions:
                await self._finalize_open_records_unlocked(
                    reason="session_activated",
                    reset_detector=True,
                    finalize_sessions=False,
                )
                self._session_ids.clear()
                self._lap_ids.clear()
                self._auto_lap_ids.clear()
            session = self.store.activate_session(session_id)
            self.ingest.reset_live_decimation(session_id)
            await self.bus.publish(
                {
                    "type": "session_started",
                    "session": session,
                    "reason": "session_activated",
                }
            )
            await self.bus.publish(
                {
                    "type": "live_reset",
                    "reason": "session_activated",
                    "received_at_ms": int(time.time() * 1000),
                    "session_id": session_id,
                }
            )
            return session

    async def clear_live_session_state(self, reason: str) -> None:
        """Clear transient live capture state without deleting durable rows."""

        async with self._capture_lock:
            await self._finalize_open_records_unlocked(
                reason=reason,
                reset_detector=True,
                finalize_sessions=False,
            )
            self._session_ids.clear()

    async def end_active_session(self, session_id: str, reason: str = "user_end") -> None:
        """Finalize transient records and end the active storage session."""

        async with self._capture_lock:
            await self._finalize_open_records_unlocked(
                reason=reason,
                reset_detector=True,
                finalize_sessions=False,
            )
            active = self.store.active_session()
            if active is not None and active["id"] == session_id:
                self.store.end_session(session_id, reason=reason)
            self._session_ids.clear()
            await self.bus.publish(
                {
                    "type": "session_finalized",
                    "session_id": session_id,
                    "reason": reason,
                }
            )

    async def clear_session_if_active(self, session_id: str, reason: str) -> None:
        """Clear transient mappings for an active session before destructive changes."""

        async with self._capture_lock:
            active = self.store.active_session()
            if active is None or active["id"] != session_id:
                return
            await self._finalize_open_records_unlocked(
                reason=reason,
                reset_detector=True,
                finalize_sessions=False,
            )
            self._session_ids.clear()

    async def finalize_open_records(
        self,
        reason: str,
        reset_detector: bool = False,
        finalize_sessions: bool = True,
    ) -> None:
        async with self._capture_lock:
            await self._finalize_open_records_unlocked(
                reason=reason,
                reset_detector=reset_detector,
                finalize_sessions=finalize_sessions,
            )

    async def delete_lap(self, lap_id: str) -> dict | None:
        """Delete a lap while keeping live capture state consistent.

        Users can delete stale or currently open laps.  Serialize with packet
        processing, flush any buffered samples first so storage can cleanly
        remove every durable row for the lap, and reset transient detector
        mappings if the deleted lap was still considered active by the
        pipeline.
        """

        async with self._capture_lock:
            await self.ingest.flush()
            lap = self.store.delete_lap(lap_id)
            if lap is None:
                return None

            was_transient_lap = any(
                stored_lap_id == lap_id for stored_lap_id in self._lap_ids.values()
            )
            if was_transient_lap:
                self._reset_lap_detector()
            return lap

    async def delete_all_recorded_telemetry(self, reason: str) -> dict[str, int]:
        """Delete all durable telemetry while clearing transient capture state."""

        async with self._capture_lock:
            await self._finalize_open_records_unlocked(
                reason=reason,
                reset_detector=True,
                finalize_sessions=False,
            )
            deleted_counts = self.store.delete_all_recorded_telemetry()
            self._session_ids.clear()
            self._lap_ids.clear()
            self._auto_lap_ids.clear()
            self.ingest.reset_live_decimation()
            await self.bus.publish(
                {
                    "type": "live_reset",
                    "reason": reason,
                    "received_at_ms": int(time.time() * 1000),
                    "session_id": None,
                }
            )
            await self.bus.publish(
                {
                    "type": "telemetry_deleted_all",
                    "deleted_counts": deleted_counts,
                }
            )
            return deleted_counts

    async def _process_live_packet_unlocked(
        self,
        raw: bytes,
        received_at_ms: int | None = None,
        label: str = "Live capture",
    ) -> None:
        if received_at_ms is None:
            received_at_ms = int(time.time() * 1000)
        decoded = decode_packet(raw)
        is_race_on = _is_race_on_packet(decoded)
        auto_race_started = (
            self.capture.mode.value == "auto"
            and is_race_on
            and self._last_is_race_on is False
        )
        previous_capture_phase = self.capture.phase
        previous_packet_type = self.capture.status()["packet_receipt"]["last_packet_type"]
        should_record, packets_to_flush = self.capture.observe_packet(raw, decoded)
        next_capture_status = self.capture.status()
        next_packet_type = next_capture_status["packet_receipt"]["last_packet_type"]
        if self.capture.phase != previous_capture_phase or next_packet_type != previous_packet_type:
            await self.bus.publish({"type": "capture", **next_capture_status})
        if packets_to_flush:
            await self._record_prebuffer_packets(packets_to_flush, received_at_ms, label)
        if (
            auto_race_started
            and previous_capture_phase != CapturePhase.RECORDING
            and self.capture.phase == CapturePhase.RECORDING
        ):
            await self.bus.publish(
                {
                    "type": "live_reset",
                    "reason": "race_on_started",
                    "received_at_ms": received_at_ms,
                    "session_id": (self.store.active_session() or {}).get("id"),
                }
            )
        if should_record:
            await self._record_packet(
                raw,
                received_at_ms,
                label=label,
                decoded=decoded,
                publish_live=is_race_on,
            )
        elif self.capture.mode.value == "manual" and has_race_packet_signal(decoded):
            await self._publish_ignored_race_packet_warning(received_at_ms)
        if self._last_is_race_on is True and not is_race_on:
            await self._match_open_laps_on_race_off()
        self._last_is_race_on = is_race_on

    async def _publish_ignored_race_packet_warning(self, received_at_ms: int) -> None:
        reasons = ["no active recorder"]
        if self.store.active_session() is None:
            reasons.append("no active session")
        reason_key = "+".join(reasons)
        last_published_at = self._last_ignored_race_toast_ms_by_reason.get(reason_key)
        if last_published_at is not None and received_at_ms - last_published_at < 10_000:
            return

        self._last_ignored_race_toast_ms_by_reason[reason_key] = received_at_ms
        await self.bus.publish(
            {
                "type": "toast",
                "level": "warning",
                "message": (
                    "Race packets are being ignored because there is "
                    f"{' and '.join(reasons)}."
                ),
                "sticky": False,
            }
        )

    async def _finalize_open_records_unlocked(
        self,
        reason: str,
        reset_detector: bool = False,
        finalize_sessions: bool = True,
    ) -> None:
        await self.ingest.flush()
        for internal_lap_id in list(self._lap_ids):
            await self._finalize_lap(
                internal_lap_id=internal_lap_id,
                reason=reason,
                boundary_confidence="heuristic",
                uncertainty=None,
            )
        if finalize_sessions:
            for internal_session_id in list(self._session_ids):
                await self._finalize_session(internal_session_id, reason=reason)
        if reset_detector:
            self._reset_lap_detector()

    async def _record_prebuffer_packets(
        self,
        raw_packets: list[bytes],
        received_at_ms: int,
        label: str,
    ) -> None:
        start_received_at_ms = received_at_ms - (len(raw_packets) * 16)
        for index, buffered_raw in enumerate(raw_packets):
            await self._record_packet(
                buffered_raw,
                start_received_at_ms + (index * 16),
                label=label,
                publish_live=False,
            )

    async def _prepare_active_session_for_car_identity(
        self,
        car_identity: dict | None,
    ) -> str | None:
        if not self.use_active_sessions or car_identity is None:
            return None
        active = self.store.active_session()
        if active is None:
            return None
        active_key = active.get("car_identity_key")
        next_key = car_identity.get("car_identity_key")
        if not next_key:
            return None

        active_reliable = _has_reliable_car_identity(active)
        next_reliable = _has_reliable_car_identity(car_identity)
        if active_key and active_key != next_key:
            if active_reliable and next_reliable:
                await self._finalize_open_records_unlocked(
                    reason="car_switch",
                    reset_detector=True,
                    finalize_sessions=False,
                )
                await self._finalize_or_delete_session(
                    str(active["id"]),
                    reason="car_switch",
                )
                self._session_ids.clear()
                return "car_switch"
            if not active_reliable and next_reliable:
                self.store.attach_session_car_identity(str(active["id"]), car_identity)
            return None

        if not active_key or (not active_reliable and next_reliable):
            self.store.attach_session_car_identity(str(active["id"]), car_identity)
        return None

    async def _record_packet(
        self,
        raw: bytes,
        received_at_ms: int,
        *,
        label: str,
        decoded: dict | None = None,
        publish_live: bool = True,
    ) -> dict | None:
        if decoded is None:
            decoded = decode_packet(raw)
        car_identity = car_identity_from_packet(self.store, decoded)
        session_start_reason = await self._prepare_active_session_for_car_identity(
            car_identity
        )
        action = self.lap_detector.observe(decoded, received_at_ms)
        if action.get("finalized_lap_id") is not None:
            await self._finalize_lap(
                internal_lap_id=int(action["finalized_lap_id"]),
                reason=_lap_finalized_reason(action),
                boundary_confidence=action.get("boundary_confidence", "unknown"),
                uncertainty=_lap_finalized_uncertainty(action),
            )

        if self._should_skip_auto_packet(action):
            await self._handle_finalized_action_session(action)
            return None

        internal_session_id = (
            action.get("session_id")
            or action.get("active_session_id")
            or action.get("finalized_session_id")
        )

        if self.use_active_sessions:
            session_id = await self._ensure_recording_session(
                int(internal_session_id) if internal_session_id is not None else None,
                label,
                car_identity=car_identity,
                received_at_ms=received_at_ms,
                session_start_reason=session_start_reason,
            )
        else:
            if internal_session_id is None:
                return None
            session_id = self._ensure_session(int(internal_session_id), label)

        active_lap_id = action.get("active_lap_id")
        if active_lap_id is not None:
            self._ensure_lap(
                internal_lap_id=int(active_lap_id),
                session_id=session_id,
                lap_number=action.get("lap_number"),
                boundary_confidence=action.get("boundary_confidence", "unknown"),
            )

        live_reset_reason = None
        if publish_live and action.get("lap_action") == "finalize_and_start":
            if action.get("session_action") == "resume":
                live_reset_reason = "race_resume_split"
            elif action.get("uncertainty") == "teleport":
                live_reset_reason = "telemetry_gap"
        if live_reset_reason is not None:
            self.ingest.reset_live_decimation(session_id)
            await self.bus.publish(
                {
                    "type": "live_reset",
                    "reason": live_reset_reason,
                    "received_at_ms": received_at_ms,
                    "session_id": session_id,
                    "uncertainty": action.get("uncertainty"),
                }
            )

        packet_lap_id = action.get("lap_id")
        stored_lap_id = (
            self._lap_ids.get(int(packet_lap_id))
            if packet_lap_id is not None
            else None
        )
        if stored_lap_id is not None and action.get("uncertainty") in {"rewind", "reset"}:
            await self._trim_replaced_race_control_segment(stored_lap_id, action)
        sample_metadata = {
            "lap_id": stored_lap_id,
            "boundary_confidence": action.get("boundary_confidence"),
            "session_action": action.get("session_action"),
            "lap_action": action.get("lap_action"),
        }
        if action.get("uncertainty") is not None:
            sample_metadata["uncertainty"] = action["uncertainty"]

        sample = await self.ingest.ingest_decoded_packet(
            session_id=session_id,
            raw=raw,
            decoded=decoded,
            received_at_ms=received_at_ms,
            sample_metadata=sample_metadata,
            publish_live=publish_live,
        )

        if action.get("finalized_session_id") is not None:
            await self._handle_finalized_action_session(action)
        return sample

    async def _trim_replaced_race_control_segment(self, lap_id: str, action: dict) -> None:
        discard_after = action.get("race_control_discard_after_current_lap")
        if discard_after is None:
            return
        await self.ingest.flush()
        deleted = self.store.delete_lap_samples_after_current_lap(
            lap_id,
            float(discard_after),
        )
        if deleted <= 0:
            return
        lap = self.store.lap(lap_id)
        await self.bus.publish(
            {
                "type": "live_reset",
                "reason": action.get("uncertainty"),
                "received_at_ms": action.get("received_at_ms"),
                "session_id": lap["session_id"] if lap else None,
                "lap_id": lap_id,
                "trimmed_sample_count": deleted,
                "uncertainty": action.get("uncertainty"),
            }
        )

    def _should_skip_auto_packet(self, action: dict) -> bool:
        if self.capture.mode.value != "auto":
            return False
        if action.get("lap_id") is not None:
            return False
        # Finalization is handled before this check. Auto mode should not keep
        # paused/menu/no-signal packets as lap_id=NULL telemetry just because an
        # internal lap remains open; useful lap packets carry packet-level lap_id.
        if action.get("uncertainty") in {"event_exit", "paused", "no_lap_signal"}:
            return True
        if action.get("active_lap_id") is not None:
            return False
        return False

    async def _handle_finalized_action_session(self, action: dict) -> None:
        if action.get("finalized_session_id") is None:
            return
        await self.ingest.flush()
        finalized_session_id = int(action["finalized_session_id"])
        if self.use_active_sessions:
            self._session_ids.pop(finalized_session_id, None)
        else:
            await self._finalize_session(
                finalized_session_id,
                reason=_session_finalized_reason(action),
            )

    def _ensure_session(self, internal_session_id: int, label: str) -> str:
        session_id = self._session_ids.get(internal_session_id)
        if session_id is not None:
            return session_id

        session_id = self.store.create_session(label=label)
        self._session_ids[internal_session_id] = session_id
        self._created_session_ids.append(session_id)
        return session_id

    async def _ensure_recording_session(
        self,
        internal_session_id: int | None,
        label: str,
        *,
        car_identity: dict | None = None,
        received_at_ms: int | None = None,
        session_start_reason: str | None = None,
    ) -> str:
        if not self.use_active_sessions:
            raise RuntimeError("detector sessions must use _ensure_session")
        if internal_session_id is not None:
            cached_session_id = self._session_ids.get(internal_session_id)
            if cached_session_id is not None:
                return cached_session_id

        active = self.store.active_session()
        if active is not None:
            if car_identity is not None and not active.get("car_identity_key"):
                active = self.store.attach_session_car_identity(
                    str(active["id"]),
                    car_identity,
                )
            session_id = str(active["id"])
        else:
            reason = session_start_reason or "recording_session_started"
            session_id = self.store.start_session(
                car_identity=car_identity,
                auto_created_reason="car_switch" if reason == "car_switch" else None,
            )
            await self._publish_session_started(session_id, reason=reason)
            self.ingest.reset_live_decimation(session_id)
            await self.bus.publish(
                {
                    "type": "live_reset",
                    "reason": reason,
                    "received_at_ms": received_at_ms,
                    "session_id": session_id,
                }
            )

        if internal_session_id is not None:
            self._session_ids[internal_session_id] = session_id
        return session_id

    async def _publish_session_started(self, session_id: str, reason: str) -> None:
        session = self.store.session(session_id)
        if session is None:
            return
        await self.bus.publish(
            {
                "type": "session_started",
                "session": session,
                "reason": reason,
            }
        )

    async def _finalize_or_delete_session(self, session_id: str, reason: str) -> None:
        deleted = self.store.delete_empty_auto_created_session(
            session_id,
            auto_created_reason="car_switch",
        )
        if deleted is not None:
            await self.bus.publish(
                {
                    "type": "session_deleted",
                    "session_id": session_id,
                    "session": deleted,
                    "reason": "empty_auto_car_switch_session",
                    "finalize_reason": reason,
                }
            )
            return

        self.store.finalize_session(session_id, reason=reason)
        await self.bus.publish(
            {
                "type": "session_finalized",
                "session_id": session_id,
                "reason": reason,
            }
        )

    def _ensure_lap(
        self,
        *,
        internal_lap_id: int,
        session_id: str,
        lap_number: int | None,
        boundary_confidence: str,
    ) -> str:
        lap_id = self._lap_ids.get(internal_lap_id)
        if lap_id is not None:
            return lap_id

        lap_id = self.store.create_lap(
            session_id=session_id,
            lap_number=lap_number,
            boundary_confidence=boundary_confidence,
        )
        self._lap_ids[internal_lap_id] = lap_id
        self._auto_lap_ids[internal_lap_id] = self.capture.mode.value == "auto"
        return lap_id

    async def _finalize_lap(
        self,
        *,
        internal_lap_id: int,
        reason: str,
        boundary_confidence: str,
        uncertainty: str | None,
    ) -> None:
        lap_id = self._lap_ids.pop(internal_lap_id, None)
        auto_created = self._auto_lap_ids.pop(internal_lap_id, False)
        if lap_id is None:
            return

        await self.ingest.flush()
        track_match = await self._match_lap_track_for_capture_boundary(lap_id)
        lap_before_quality = self.store.lap(lap_id)
        track_profile_assigned = bool(
            lap_before_quality is not None and lap_before_quality.get("track_profile_id")
        )
        auto_verdict = None
        if auto_created:
            samples = self.store.samples_for_lap(lap_id)
            auto_verdict = evaluate_auto_lap(
                samples,
                reason=reason,
                boundary_confidence=boundary_confidence,
                uncertainty=uncertainty,
                track_profile_assigned=track_profile_assigned,
            )
            if not auto_verdict.keep:
                deleted = self.store.delete_lap(lap_id)
                session_id = deleted["session_id"] if deleted is not None else None
                await self.bus.publish(
                    {
                        "type": "auto_lap_discarded",
                        "lap_id": lap_id,
                        "session_id": session_id,
                        "reason": auto_verdict.reason,
                        "metrics": auto_verdict.metrics or {},
                    }
                )
                await self.bus.publish(
                    {
                        "type": "toast",
                        "level": "info",
                        "message": (
                            "Auto recorder discarded incomplete lap "
                            f"({auto_verdict.reason})."
                        ),
                        "sticky": False,
                    }
                )
                return
        self.store.finalize_lap(
            lap_id,
            reason=reason,
            boundary_confidence=boundary_confidence,
        )
        summary = compute_lap_summary(self.store.samples_for_lap(lap_id))
        if auto_verdict is not None and auto_verdict.keep:
            summary = dict(summary)
            summary["completion_type"] = auto_verdict.completion_type
            summary["lap_time_ms"] = auto_verdict.lap_time_ms
            summary["auto_lap_quality"] = {
                "reason": auto_verdict.reason,
                "metrics": auto_verdict.metrics or {},
            }
        self.store.insert_lap_summary(lap_id, summary)
        analysis_result = _analyze_lap_preserving_summary(
            self.store,
            lap_id=lap_id,
            existing_summary=summary,
        )
        summary = _merge_lap_summaries(summary, analysis_result["summary"])
        if not _track_match_assigned(track_match):
            track_match = await self._match_lap_track_for_capture_boundary(lap_id)
        if self.count_lifetime_stats:
            self.store.record_lifetime_lap_stats(
                lap_id,
                require_completed_candidate=not (
                    auto_verdict is not None and auto_verdict.keep
                ),
            )
        lap = self.store.lap(lap_id)
        await self.bus.publish(
            {
                "type": "lap_finalized",
                "lap_id": lap_id,
                "session_id": lap.get("session_id") if lap is not None else None,
                "reason": reason,
                "boundary_confidence": boundary_confidence,
                "uncertainty": uncertainty,
                "summary": summary,
                "lap": _json_safe(lap),
                "track_match": _json_safe(track_match),
            }
        )
        message = f"Lap finalized ({boundary_confidence})"
        if uncertainty:
            message = f"{message}; uncertainty: {uncertainty}"
        await self.bus.publish(
            {
                "type": "toast",
                "level": "info",
                "message": message,
                "sticky": False,
            }
        )

    async def _match_open_laps_on_race_off(self) -> None:
        for lap_id in list(dict.fromkeys(self._lap_ids.values())):
            track_match = await self._match_lap_track_for_capture_boundary(lap_id)
            if not _track_match_assigned(track_match):
                continue
            await self._publish_lap_track_matched(
                lap_id,
                track_match,
                reason="race_off",
            )

    async def _match_lap_track_for_capture_boundary(self, lap_id: str) -> dict | None:
        lap = self.store.lap(lap_id)
        if lap is None or lap.get("track_profile_id"):
            return None
        await self.ingest.flush()
        try:
            return await asyncio.to_thread(self._match_lap_track_sync, lap_id)
        except Exception as exc:
            return {
                "lap_id": lap_id,
                "matcher_version": MATCHER_VERSION,
                "error": str(exc),
                "assignment": {
                    "assigned": False,
                    "reason": "matcher_error",
                },
            }

    def _match_lap_track_sync(self, lap_id: str) -> dict:
        self.store.ensure_game_track_profiles()
        return match_lap_track(self.store, lap_id, auto_assign=True)

    async def _publish_lap_track_matched(
        self,
        lap_id: str,
        track_match: dict,
        *,
        reason: str,
    ) -> None:
        lap = self.store.lap(lap_id)
        if lap is None:
            return
        await self.bus.publish(
            {
                "type": "lap_track_matched",
                "lap_id": lap_id,
                "session_id": lap.get("session_id"),
                "reason": reason,
                "lap": _json_safe(lap),
                "track_match": _json_safe(track_match),
            }
        )

    async def _finalize_session(self, internal_session_id: int, reason: str) -> None:
        session_id = self._session_ids.pop(internal_session_id, None)
        if session_id is None:
            return

        await self._finalize_or_delete_session(session_id, reason=reason)

    def _reset_lap_detector(self) -> None:
        self.lap_detector = LapDetector()
        self._session_ids.clear()
        self._lap_ids.clear()
        self._auto_lap_ids.clear()


def _settings_payload(store: TelemetryStore) -> dict:
    with store.connect() as con:
        row = con.execute(
            """
            SELECT capture_mode, udp_host, udp_port, preferred_overlay, unit_system
            FROM user_settings
            LIMIT 1
            """
        ).fetchone()
    return dict(row)


def _persist_capture_mode(
    store: TelemetryStore,
    mode: str,
    user_id: str = LOCAL_USER_ID,
) -> None:
    with store.connect() as con:
        con.execute(
            """
            UPDATE user_settings
            SET capture_mode = ?, updated_at_ms = ?
            WHERE user_id = ?
            """,
            (mode, int(time.time() * 1000), user_id),
        )


def _persist_visualiser_settings(
    store: TelemetryStore,
    *,
    unit_system: str | None = None,
    preferred_overlay: str | None = None,
    user_id: str = LOCAL_USER_ID,
) -> None:
    updates: list[str] = []
    values: list[object] = []
    if unit_system is not None:
        updates.append("unit_system = ?")
        values.append(unit_system)
    if preferred_overlay is not None:
        updates.append("preferred_overlay = ?")
        values.append(preferred_overlay)
    if not updates:
        return
    updates.append("updated_at_ms = ?")
    values.append(int(time.time() * 1000))
    values.append(user_id)

    with store.connect() as con:
        con.execute(
            f"""
            UPDATE user_settings
            SET {", ".join(updates)}
            WHERE user_id = ?
            """,
            tuple(values),
        )


def _raw_path_for_replay(raw_path: str) -> Path:
    if not raw_path:
        raise HTTPException(status_code=400, detail="raw_path must not be empty")
    path = Path(raw_path)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail="raw_path does not exist") from exc
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="raw_path must be a file")
    return resolved


def _label_for_uploaded_replay(label: str | None, filename: str | None) -> str:
    cleaned_label = str(label or "").strip()
    if cleaned_label:
        return cleaned_label
    cleaned_filename = Path(str(filename or "")).name.strip()
    if cleaned_filename:
        return f"Imported {cleaned_filename}"
    return "Imported raw telemetry"


def _lap_ids_for_sessions(store: TelemetryStore, session_ids: list[str]) -> list[str]:
    if not session_ids:
        return []
    placeholders = ",".join("?" for _ in session_ids)
    with store.connect() as con:
        rows = con.execute(
            f"""
            SELECT id
            FROM laps
            WHERE session_id IN ({placeholders})
            ORDER BY COALESCE(ended_at_ms, started_at_ms) DESC,
                     started_at_ms DESC,
                     rowid DESC
            """,
            tuple(session_ids),
        ).fetchall()
    return [row["id"] for row in rows]


def _truthy_env_value(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "force"}


def _refresh_car_catalog_from_local_files(store: TelemetryStore) -> int:
    raw_root = os.environ.get(FH6_MEDIA_ROOT_ENV)
    media_root = Path(raw_root) if raw_root else DEFAULT_FH6_MEDIA_ROOT
    if not media_root.exists():
        return 0
    force_refresh = _truthy_env_value(os.environ.get(FH6_REFRESH_CAR_CATALOG_ENV))
    if not force_refresh and store.car_catalog_count() > 0:
        return 0
    try:
        records = load_local_fh6_catalog(media_root)
    except (OSError, ValueError):
        return 0
    return store.upsert_car_catalog_records(records)


def _refresh_track_catalog_from_local_files(store: TelemetryStore) -> dict[str, int]:
    raw_root = os.environ.get(FH6_MEDIA_ROOT_ENV)
    media_root = Path(raw_root) if raw_root else DEFAULT_FH6_MEDIA_ROOT
    if not media_root.exists():
        return {"tracks": 0, "map_regions": 0, "locators": 0}
    force_refresh = _truthy_env_value(os.environ.get(FH6_REFRESH_TRACK_CATALOG_ENV))
    has_ai_track_geometry = (
        store.game_track_locator_count(source_file_like="OpenWorld/%/AITracks/Route%.owt") > 0
    )
    if not force_refresh and store.track_catalog_count() > 0 and has_ai_track_geometry:
        return {"tracks": 0, "map_regions": 0, "locators": 0}
    try:
        catalog = load_local_fh6_track_catalog(media_root)
    except (OSError, ValueError):
        return {"tracks": 0, "map_regions": 0, "locators": 0}
    counts = store.upsert_track_catalog_records(catalog.tracks, catalog.map_regions, catalog.locators)
    store.ensure_game_track_profiles()
    return counts


def _upload_size_limit_message() -> str:
    return f"raw telemetry upload exceeds maximum allowed size of {RAW_TELEMETRY_UPLOAD_MAX_BYTES} bytes"


def _import_total_size_limit_message() -> str:
    return (
        "raw telemetry import exceeds maximum allowed total size of "
        f"{RAW_TELEMETRY_IMPORT_MAX_TOTAL_BYTES} bytes"
    )


async def _read_uploaded_raw_telemetry(file: UploadFile) -> bytes:
    if file.size is not None and file.size > RAW_TELEMETRY_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail=_upload_size_limit_message())

    raw = bytearray()
    while True:
        chunk = await file.read(RAW_TELEMETRY_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        if len(raw) + len(chunk) > RAW_TELEMETRY_UPLOAD_MAX_BYTES:
            raise HTTPException(status_code=413, detail=_upload_size_limit_message())
        raw.extend(chunk)
    return bytes(raw)


def _clean_import_display_name(filename: str | None, index: int) -> str:
    display = str(filename or "").replace("\\", "/").strip().strip("/")
    return display or f"raw-telemetry-{index}.bin"


def _safe_staged_upload_name(display_name: str, index: int) -> str:
    basename = Path(display_name.replace("\\", "/")).name.strip()
    if not basename:
        basename = f"raw-telemetry-{index}.bin"
    safe = "".join(
        character if character.isalnum() or character in {".", "-", "_"} else "_"
        for character in basename
    ).strip("._")
    return f"{index:04d}-{safe or 'raw-telemetry.bin'}"


async def _stage_uploaded_raw_telemetry_files(files: list[UploadFile]) -> tuple[list[RawTelemetryImportSource], Path, int]:
    if not files:
        raise HTTPException(status_code=400, detail="at least one raw telemetry file is required")
    if len(files) > RAW_TELEMETRY_IMPORT_MAX_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"raw telemetry import accepts at most {RAW_TELEMETRY_IMPORT_MAX_FILES} files",
        )

    staged_dir = Path(tempfile.mkdtemp(prefix="fh6-raw-import-"))
    staged: list[RawTelemetryImportSource] = []
    total_bytes = 0
    try:
        for index, upload in enumerate(files, start=1):
            display_name = _clean_import_display_name(upload.filename, index)
            staged_path = staged_dir / _safe_staged_upload_name(display_name, index)
            file_size = 0
            with staged_path.open("wb") as destination:
                while True:
                    chunk = await upload.read(RAW_TELEMETRY_UPLOAD_READ_CHUNK_BYTES)
                    if not chunk:
                        break
                    file_size += len(chunk)
                    total_bytes += len(chunk)
                    if file_size > RAW_TELEMETRY_UPLOAD_MAX_BYTES:
                        raise HTTPException(status_code=413, detail=_upload_size_limit_message())
                    if total_bytes > RAW_TELEMETRY_IMPORT_MAX_TOTAL_BYTES:
                        raise HTTPException(status_code=413, detail=_import_total_size_limit_message())
                    destination.write(chunk)
            staged.append(
                RawTelemetryImportSource(
                    display_name=display_name,
                    staged_path=staged_path,
                    size_bytes=file_size,
                )
            )
    except Exception:
        shutil.rmtree(staged_dir, ignore_errors=True)
        raise
    return staged, staged_dir, total_bytes


def _label_for_import_job(label: str | None, source_type: str, files: list[RawTelemetryImportSource]) -> str:
    cleaned_label = str(label or "").strip()
    if cleaned_label:
        return cleaned_label
    if len(files) == 1:
        return _label_for_uploaded_replay(None, files[0].display_name)
    if source_type == "folder":
        first_folder = files[0].display_name.replace("\\", "/").split("/", 1)[0].strip()
        if first_folder:
            return f"Imported {first_folder}"
        return "Imported raw telemetry folder"
    return "Imported raw telemetry files"


def _label_for_import_source(job: RawTelemetryImportJob, source: RawTelemetryImportSource) -> str:
    if job.total_files == 1:
        return job.label
    stem = Path(source.display_name.replace("\\", "/")).stem.strip()
    if not stem:
        stem = f"file {job.processed_files + 1}"
    return f"{job.label} - {stem}"


def _sse_frame(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\n" f"data: {json.dumps(payload)}\n\n"


def _lap_metadata(store: TelemetryStore, lap_id: str) -> dict | None:
    return store.lap(lap_id)


def _comparison_scope(scope: str) -> str:
    if scope not in SUPPORTED_SCOPES:
        supported = ", ".join(SUPPORTED_SCOPES)
        raise HTTPException(
            status_code=400,
            detail=f"unsupported reference scope: {scope}; expected one of {supported}",
        )
    return scope


def _required_text_value(value: str | None, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    return text


def _track_profile_or_404(store: TelemetryStore, profile_id: str) -> dict:
    profile = store.track_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="unknown track_profile_id")
    return profile


def _track_profile_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if "unknown track_profile_id" in detail:
        return HTTPException(status_code=404, detail="unknown track_profile_id")
    if "unknown track_asset_id" in detail:
        return HTTPException(status_code=404, detail="unknown track_asset_id")
    if "unknown session_id" in detail:
        return HTTPException(status_code=404, detail="unknown session_id")
    if "unknown lap_id" in detail:
        return HTTPException(status_code=404, detail="unknown lap_id")
    return HTTPException(status_code=400, detail=detail)


def _sorted_track_profiles(store: TelemetryStore) -> list[dict]:
    return sorted(
        store.track_profiles(),
        key=lambda profile: (
            -int(profile.get("updated_at_ms") or 0),
            str(profile.get("name") or "").lower(),
            str(profile.get("layout") or "").lower(),
            str(profile.get("id") or ""),
        ),
    )


def _track_asset_payload(asset: dict) -> dict:
    payload = dict(asset)
    payload.pop("stored_path", None)
    payload["file_url"] = f"/api/tracks/assets/{asset['id']}/file"
    return payload


def _track_assets_payload(assets: list[dict]) -> list[dict]:
    return [_track_asset_payload(asset) for asset in assets]


def _track_asset_storage_dir(store: TelemetryStore, profile_id: str) -> Path:
    root = _track_asset_storage_root(store)
    target = (root / profile_id).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid track_profile_id path") from exc
    target.mkdir(parents=True, exist_ok=True)
    return target


def _track_asset_storage_root(store: TelemetryStore) -> Path:
    return (store.db_path.parent / "track_assets").resolve()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _asset_source_path(raw_path: str) -> Path:
    if not raw_path:
        raise HTTPException(status_code=400, detail="source_path must not be empty")
    try:
        resolved = Path(raw_path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail="source_path does not exist") from exc
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="source_path must be a file")
    return resolved


def _copy_track_asset_source(
    store: TelemetryStore,
    *,
    profile_id: str,
    source_path: Path,
    filename: str,
) -> Path:
    safe_filename = Path(filename).name
    if safe_filename != filename:
        raise HTTPException(status_code=400, detail="filename must not include path components")
    destination_dir = _track_asset_storage_dir(store, profile_id)
    destination = (destination_dir / f"{time.time_ns()}-{safe_filename}").resolve()
    try:
        destination.relative_to(destination_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid asset destination") from exc
    try:
        shutil.copy2(source_path, destination)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"failed to copy asset: {exc}") from exc
    return destination


def _remove_copied_track_asset(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _comparison_lap_context(
    store: TelemetryStore,
    lap_id: str,
    scope: str,
) -> tuple[dict, str]:
    scope = _comparison_scope(scope)
    lap = _lap_metadata(store, lap_id)
    if lap is None:
        raise HTTPException(status_code=404, detail="unknown lap_id")

    comparison_lap = dict(lap)
    comparison_lap["lap_id"] = lap_id
    summary = store.lap_summary(lap_id)
    if summary is not None:
        comparison_lap["summary"] = summary
        for key in (
            "comparison_contexts",
            "track_profile_id",
            "track_signature",
            "car_id",
            "car_slug",
            "build_id",
            "build_slug",
        ):
            if (
                isinstance(summary, dict)
                and key in summary
                and (key not in comparison_lap or comparison_lap.get(key) is None)
            ):
                comparison_lap[key] = summary[key]

    try:
        context_key = context_key_for_lap(scope, comparison_lap)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return comparison_lap, context_key


def _reference_payload(
    store: TelemetryStore,
    lap_id: str,
    scope: str,
    context_key: str,
) -> dict:
    try:
        reference = select_reference_lap(store, lap_id, scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "lap_id": lap_id,
        "scope": scope,
        "context_key": context_key,
        "reference": _json_safe(reference),
    }


def _session_metadata(store: TelemetryStore, session_id: str) -> dict | None:
    with store.connect() as con:
        row = con.execute(
            """
            SELECT id, user_id, label, status, started_at_ms, ended_at_ms, ended_reason
            FROM sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
    return None if row is None else dict(row)


def _json_safe(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return list(bytes(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _track_match_assigned(track_match: dict | None) -> bool:
    if not isinstance(track_match, dict):
        return False
    assignment = track_match.get("assignment")
    return isinstance(assignment, dict) and assignment.get("assigned") is True


def _summary_range(start_sequence: int | None, end_sequence: int | None) -> tuple[int, int] | None:
    if start_sequence is None and end_sequence is None:
        return None
    if start_sequence is None or end_sequence is None:
        raise HTTPException(
            status_code=400,
            detail="start_sequence and end_sequence are required together",
        )
    if start_sequence <= 0 or end_sequence <= 0:
        raise HTTPException(status_code=400, detail="sequence range must be positive")
    if start_sequence > end_sequence:
        raise HTTPException(
            status_code=400,
            detail="start_sequence must be less than or equal to end_sequence",
        )
    return (int(start_sequence), int(end_sequence))

def _has_analysis_summary_shape(summary: dict | None) -> bool:
    if not isinstance(summary, dict):
        return False
    return ANALYSIS_SUMMARY_KEYS.issubset(summary)


def _merge_lap_summaries(existing_summary: dict | None, analysis_summary: dict) -> dict:
    merged: dict = {}
    if isinstance(existing_summary, dict):
        merged.update(existing_summary)
    merged.update(analysis_summary)
    return merged


def _analyze_lap_preserving_summary(
    store: TelemetryStore,
    *,
    lap_id: str,
    session_id: str | None = None,
    existing_summary: dict | None = None,
) -> dict:
    if session_id is None:
        lap = _lap_metadata(store, lap_id)
        if lap is None:
            raise HTTPException(status_code=404, detail="unknown lap_id")
        session_id = lap["session_id"]

    summary_to_preserve = (
        existing_summary
        if existing_summary is not None
        else store.lap_summary(lap_id)
    )
    result = analyze_lap(store, session_id=session_id, lap_id=lap_id)
    if summary_to_preserve is not None:
        store.insert_lap_summary(
            lap_id,
            _merge_lap_summaries(summary_to_preserve, result["summary"]),
        )
    return result


def _analysis_summary_for_lap(store: TelemetryStore, lap_id: str) -> dict:
    stored_summary = store.lap_summary(lap_id)
    if _has_analysis_summary_shape(stored_summary):
        return stored_summary

    samples = store.samples_for_lap(lap_id)
    summary = summarize_samples(samples)
    if samples:
        summary["start_sequence"] = int(samples[0]["sequence"])
        summary["end_sequence"] = int(samples[-1]["sequence"])
    return summary


def _marker_ruleset_version(marker: dict) -> int:
    try:
        return int(marker.get("ruleset_version") or 0)
    except (TypeError, ValueError):
        return 0


def _marker_has_current_detail_shape(marker: dict) -> bool:
    if _marker_ruleset_version(marker) < load_default_ruleset().schema_version:
        return False
    return (
        "anchor_sequence" in marker
        and marker.get("issue_kind") is not None
        and marker.get("actual_value") is not None
        and marker.get("threshold_value") is not None
        and marker.get("threshold_operator") in {"gte", "lte"}
        and marker.get("value_label") is not None
    )


def _issue_markers_for_lap_with_backfill(
    store: TelemetryStore,
    *,
    lap_id: str,
    lap: dict,
) -> list[dict]:
    markers = store.issue_markers_for_lap(lap_id=lap_id)
    stored_summary = store.lap_summary(lap_id)
    if markers and all(_marker_has_current_detail_shape(marker) for marker in markers):
        return markers
    if markers:
        _analyze_lap_preserving_summary(
            store,
            lap_id=lap_id,
            session_id=lap["session_id"],
            existing_summary=stored_summary,
        )
        return store.issue_markers_for_lap(lap_id=lap_id)

    if _has_analysis_summary_shape(stored_summary):
        return []

    _analyze_lap_preserving_summary(
        store,
        lap_id=lap_id,
        session_id=lap["session_id"],
        existing_summary=stored_summary,
    )
    return store.issue_markers_for_lap(lap_id=lap_id)


def _positive_limit(limit: int) -> int:
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be positive")
    return limit


def _positive_page(value: int, name: str) -> int:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _session_or_404(store: TelemetryStore, session_id: str) -> dict:
    session = store.session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session_id")
    return session


def _is_race_on_packet(decoded: dict) -> bool:
    try:
        return int(decoded.get("IsRaceOn", 0)) > 0
    except (TypeError, ValueError):
        return False


def _is_teleport_lap_split(action: dict) -> bool:
    return action.get("lap_action") == "finalize_and_start" and action.get("uncertainty") == "teleport"


def _lap_finalized_reason(action: dict) -> str:
    if action.get("uncertainty") == "event_exit":
        return "event_exit"
    if _is_teleport_lap_split(action):
        return "telemetry_gap"
    return "lap_boundary"


def _lap_finalized_uncertainty(action: dict) -> str | None:
    if _is_teleport_lap_split(action):
        return "telemetry_gap"
    uncertainty = action.get("uncertainty")
    return uncertainty if isinstance(uncertainty, str) else None


def _session_finalized_reason(action: dict) -> str:
    if action.get("uncertainty") == "event_exit":
        return "event_exit"
    return "session_boundary"


async def stream_sse_events(bus: EventBus) -> AsyncIterator[str]:
    queue = bus.subscribe()
    try:
        yield _sse_frame("status", {"state": "waiting", "message": "waiting for telemetry"})
        while True:
            event = await queue.get()
            event_type = event.get("type", "message")
            yield _sse_frame(event_type, event)
    except asyncio.CancelledError:
        raise
    finally:
        bus.unsubscribe(queue)


def create_app(
    db_path: Path | None = None,
    frontend_dist: Path | None = None,
    start_udp_listener: bool = False,
    refresh_car_catalog: bool = False,
    refresh_track_catalog: bool = False,
    runtime_paths: DesktopPaths | None = None,
    map_converter_path: Path | None = None,
    map_cache_dir: Path | None = None,
    fh6_media_root: Path | None = None,
    update_service: UpdateService | None = None,
    request_shutdown: Callable[[], None] | None = None,
) -> FastAPI:
    if runtime_paths is not None:
        runtime_paths.ensure_user_directories()
        if db_path is None:
            db_path = runtime_paths.database
        if frontend_dist is None:
            frontend_dist = runtime_paths.frontend_dist
        if map_converter_path is None:
            map_converter_path = runtime_paths.map_converter
        if map_cache_dir is None:
            map_cache_dir = runtime_paths.map_cache_dir
    if db_path is None:
        db_path = Path("telemetry_tracker.sqlite3")
    store = TelemetryStore(Path(db_path))
    store.migrate()
    if refresh_car_catalog:
        _refresh_car_catalog_from_local_files(store)
    if refresh_track_catalog:
        _refresh_track_catalog_from_local_files(store)
    settings = _settings_payload(store)
    bus = EventBus()
    ingest = IngestService(store, bus)
    capture = CaptureStateMachine(mode=settings["capture_mode"])
    lap_detector = LapDetector()
    pipeline = CapturePipeline(store, bus, ingest, capture, lap_detector)
    listener = UdpTelemetryListener(
        settings["udp_host"],
        int(settings["udp_port"]),
        bus,
        pipeline.process_live_packet,
    )
    app = FastAPI(title="Forza Telemetry Tracker")
    app.state.store = store
    app.state.bus = bus
    app.state.ingest = ingest
    app.state.capture = capture
    app.state.lap_detector = lap_detector
    app.state.capture_pipeline = pipeline
    app.state.udp_listener = listener
    app.state.listener_restart_lock = asyncio.Lock()
    app.state.world_map_build_lock = asyncio.Lock()
    app.state.runtime_paths = runtime_paths
    app.state.map_converter_path = Path(map_converter_path) if map_converter_path is not None else None
    app.state.map_cache_dir = Path(map_cache_dir) if map_cache_dir is not None else None
    release_metadata = load_release_metadata(runtime_paths.release_metadata if runtime_paths is not None else None)
    if update_service is not None and hasattr(update_service, "metadata"):
        release_metadata = update_service.metadata
    if update_service is None:
        update_paths = runtime_paths or default_desktop_paths()
        update_service = UpdateService(
            metadata=release_metadata,
            updates_dir=update_paths.updates_dir,
            updater_helper_path=update_paths.updater_helper,
        )
    app.state.release_metadata = release_metadata
    app.state.update_service = update_service
    app.state.request_shutdown = request_shutdown
    app.state.update_check_lock = asyncio.Lock()
    default_export_dir = (
        Path(runtime_paths.exports_dir)
        if runtime_paths is not None
        else default_desktop_paths().exports_dir
    )
    export_jobs: dict[str, TelemetryExportJob] = {}
    export_jobs_lock = asyncio.Lock()
    export_runner_lock = asyncio.Lock()
    app.state.export_jobs = export_jobs
    raw_import_jobs: dict[str, RawTelemetryImportJob] = {}
    raw_import_jobs_lock = asyncio.Lock()
    raw_import_runner_lock = asyncio.Lock()
    app.state.raw_import_jobs = raw_import_jobs

    if start_udp_listener:
        @app.on_event("startup")
        async def start_listener() -> None:
            await listener.start()

        @app.on_event("shutdown")
        async def stop_listener() -> None:
            await listener.stop()

    async def cancel_raw_import_jobs_on_shutdown() -> None:
        tasks: list[asyncio.Task] = []
        for job in list(raw_import_jobs.values()):
            if job.status not in {"queued", "running", "cancelling"}:
                continue
            job.cancel_requested = True
            job.status = "cancelling"
            job.status_text = "Cancelling because the tracker is closing..."
            if job.task is not None and not job.task.done():
                job.task.cancel()
                tasks.append(job.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def cancel_export_jobs_on_shutdown() -> None:
        tasks: list[asyncio.Task] = []
        for job in list(export_jobs.values()):
            if job.status not in {"queued", "running", "cancelling"}:
                continue
            job.cancel_requested = True
            job.status = "cancelling"
            job.status_text = "Cancelling because the tracker is closing..."
            if job.task is not None and not job.task.done():
                job.task.cancel()
                tasks.append(job.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    app.router.on_shutdown.append(cancel_raw_import_jobs_on_shutdown)
    app.router.on_shutdown.append(cancel_export_jobs_on_shutdown)

    def capture_payload() -> dict:
        payload = capture.status()
        payload["listener"] = listener.status()
        payload["settings"] = _settings_payload(store)
        return payload

    @app.get("/api/status")
    async def status() -> dict:
        settings = _settings_payload(store)
        return {
            "listener": listener.status(),
            "settings": settings,
            "capture": capture.status(),
        }

    def _require_app_action_header(value: str | None) -> None:
        if value != FORZA_APP_ACTION_VALUE:
            raise HTTPException(
                status_code=400,
                detail=f"{FORZA_APP_ACTION_HEADER} header with value {FORZA_APP_ACTION_VALUE} is required",
            )

    @app.get("/api/app/about")
    async def app_about() -> dict:
        return release_metadata.to_about_payload(
            updates=app.state.update_service.about_update_payload(),
        )

    @app.get("/api/app/update/token")
    async def app_update_token_status() -> dict:
        return app.state.update_service.token_status_payload()

    @app.post("/api/app/update/token")
    async def app_update_token_configure(
        request: AppUpdateTokenRequest,
        x_forza_app_action: str | None = Header(default=None, alias=FORZA_APP_ACTION_HEADER),
    ) -> dict:
        _require_app_action_header(x_forza_app_action)
        token = request.token.strip()
        if not token:
            raise HTTPException(status_code=400, detail="token must not be empty")
        try:
            await asyncio.to_thread(app.state.update_service.save_token, token)
        except (TokenStorageUnavailable, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload = app.state.update_service.token_status_payload()
        payload["message"] = "GitHub update token saved."
        return payload

    @app.delete("/api/app/update/token")
    async def app_update_token_clear(
        x_forza_app_action: str | None = Header(default=None, alias=FORZA_APP_ACTION_HEADER),
    ) -> dict:
        _require_app_action_header(x_forza_app_action)
        try:
            await asyncio.to_thread(app.state.update_service.clear_token)
        except TokenStorageUnavailable as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload = app.state.update_service.token_status_payload()
        payload["message"] = "GitHub update token removed."
        return payload

    @app.post("/api/app/update/check")
    async def app_update_check(request: AppUpdateCheckRequest | None = None) -> dict:
        async with app.state.update_check_lock:
            result = await asyncio.to_thread(
                app.state.update_service.check_for_updates,
                force=bool(request.force) if request is not None else False,
            )
        return result.to_payload()

    @app.post("/api/app/update/install")
    async def app_update_install(
        background_tasks: BackgroundTasks,
        request: AppUpdateInstallRequest | None = None,
        x_forza_app_action: str | None = Header(default=None, alias=FORZA_APP_ACTION_HEADER),
    ) -> dict:
        _require_app_action_header(x_forza_app_action)
        if bool(capture.status()["recording"]["active"]):
            raise HTTPException(
                status_code=409,
                detail="Stop telemetry capture before installing an update.",
            )
        try:
            payload = await asyncio.to_thread(
                app.state.update_service.install_update,
                version=request.version if request is not None else None,
            )
        except UpdateUnsupported as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except UpdateVerificationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except UpdateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        shutdown = app.state.request_shutdown
        if callable(shutdown) and payload.get("status") == "installing":
            background_tasks.add_task(shutdown)
        return payload

    @app.patch("/api/settings")
    async def update_settings(request: VisualiserSettingsRequest) -> dict:
        try:
            unit_system = request.selected_unit_system()
            preferred_overlay = request.selected_preferred_overlay()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _persist_visualiser_settings(store, unit_system=unit_system, preferred_overlay=preferred_overlay)
        return _settings_payload(store)

    @app.get("/api/map/status")
    async def map_status() -> dict:
        return world_map_status_payload(store, converter_path=app.state.map_converter_path)

    @app.patch("/api/map/settings")
    async def update_map_settings(request: WorldMapSettingsRequest) -> dict:
        current = store.world_map_settings()
        try:
            store.update_world_map_settings(
                media_root=request.selected_media_root(current),
                enabled=request.selected_enabled(current),
                season=request.selected_season(current),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return world_map_status_payload(store, converter_path=app.state.map_converter_path)

    @app.post("/api/map/cache/build")
    async def build_map_cache(request: WorldMapBuildRequest) -> dict:
        settings = store.world_map_settings()
        media_root = settings.get("fh6_media_root")
        if not media_root:
            raise HTTPException(
                status_code=400,
                detail="fh6_media_root must be configured before building the map cache",
            )
        season = request.season or settings.get("world_map_season") or "summer"
        try:
            async with app.state.world_map_build_lock:
                return await asyncio.to_thread(
                    build_world_map_cache,
                    store=store,
                    media_root=Path(str(media_root)),
                    season=str(season),
                    converter_path=app.state.map_converter_path,
                    cache_root=app.state.map_cache_dir,
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/map/tiles/{tile_set_id}/{z}/{x}/{y}.png")
    async def map_tile(tile_set_id: str, z: int, x: int, y: int) -> FileResponse:
        tile_set = store.world_map_tile_set(tile_set_id)
        if (
            tile_set is None
            or tile_set.get("status") != "ready"
            or not tile_set_uses_current_tile_coordinates(tile_set)
        ):
            raise HTTPException(status_code=404, detail="world map tile set not found")
        try:
            tile_path = safe_cache_tile_path(
                Path(str(tile_set["cache_dir"])),
                z=z,
                x=x,
                y=y,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not tile_path.exists() or not tile_path.is_file():
            raise HTTPException(status_code=404, detail="world map tile not found")
        return FileResponse(tile_path, media_type="image/png")

    @app.get("/api/diagnostics")
    async def diagnostics() -> dict:
        return diagnostics_payload(
            store,
            app_version=release_metadata.version,
            listener_status=listener.status(),
            capture_status=capture.status(),
        )

    @app.delete("/api/telemetry/delete-all")
    async def delete_all_telemetry() -> dict:
        deleted_counts = await pipeline.delete_all_recorded_telemetry(
            reason="telemetry_delete_all"
        )
        payload = diagnostics_payload(
            store,
            app_version=release_metadata.version,
            listener_status=listener.status(),
            capture_status=capture.status(),
        )
        return {
            "deleted": True,
            "deleted_counts": deleted_counts,
            "row_counts": payload["row_counts"],
        }

    @app.post("/api/listener/restart")
    async def restart_listener() -> dict:
        try:
            async with app.state.listener_restart_lock:
                active_listener = getattr(app.state, "udp_listener", None)
                if active_listener is None:
                    raise HTTPException(status_code=503, detail="UDP listener is unavailable")
                await active_listener.stop()
                await active_listener.start()
                return active_listener.status()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to restart UDP listener: {exc}") from exc

    @app.get("/api/capture")
    async def get_capture() -> dict:
        return capture_payload()

    @app.post("/api/capture/mode")
    async def set_capture_mode(request: CaptureModeRequest) -> dict:
        try:
            selected_mode = CaptureStateMachine(
                mode=request.selected_mode(),
                prebuffer_packets=0,
            ).mode.value
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await pipeline.set_mode(selected_mode)
        app.state.lap_detector = pipeline.lap_detector
        _persist_capture_mode(store, capture.mode.value)
        return capture_payload()

    @app.post("/api/capture/start")
    async def start_capture() -> dict:
        await pipeline.start_manual()
        _persist_capture_mode(store, capture.mode.value)
        app.state.lap_detector = pipeline.lap_detector
        return capture_payload()

    @app.post("/api/capture/stop")
    async def stop_capture() -> dict:
        await pipeline.stop_manual()
        app.state.lap_detector = pipeline.lap_detector
        return capture_payload()

    @app.get("/api/live/recent")
    async def recent_live(limit: int = 200) -> dict:
        selected_limit = _positive_limit(limit)
        payload = store.latest_session_recent_samples(limit=selected_limit)
        session_id = payload.get("session_id")
        payload["car"] = (
            _json_safe(
                car_info_from_packet_bytes(
                    store,
                    store.latest_packet_bytes(session_id, limit=selected_limit),
                )
            )
            if session_id
            else None
        )
        return payload

    @app.get("/api/overlays")
    async def overlays() -> dict:
        return {"overlays": [{"id": overlay_id} for overlay_id in OVERLAY_IDS]}

    @app.get("/api/stats")
    async def stats() -> dict:
        return {"stats": store.stats_summary()}

    @app.get("/api/laps")
    async def laps(limit: int = 50) -> dict:
        try:
            return {"laps": store.latest_laps(limit=_positive_limit(limit))}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/laps/{lap_id}")
    async def lap_detail(lap_id: str) -> dict:
        lap = _lap_metadata(store, lap_id)
        if lap is None:
            raise HTTPException(status_code=404, detail="unknown lap_id")
        summary = store.lap_summary(lap_id)
        if summary is None:
            summary = compute_lap_summary(store.samples_for_lap(lap_id))
        return {"lap": lap, "summary": summary}

    @app.delete("/api/laps/{lap_id}")
    async def delete_lap(lap_id: str) -> dict:
        try:
            lap = await pipeline.delete_lap(lap_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if lap is None:
            raise HTTPException(status_code=404, detail="unknown lap_id")
        return {
            "deleted": True,
            "lap_id": lap_id,
            "session_id": lap["session_id"],
            "lap": lap,
        }

    @app.get("/api/laps/{lap_id}/samples")
    async def lap_samples(lap_id: str) -> dict:
        lap = _lap_metadata(store, lap_id)
        if lap is None:
            raise HTTPException(status_code=404, detail="unknown lap_id")
        return {"lap_id": lap_id, "samples": store.samples_for_lap(lap_id)}

    @app.get("/api/laps/{lap_id}/reference")
    async def lap_reference(lap_id: str, scope: str = DEFAULT_SCOPE) -> dict:
        scope = _comparison_scope(scope)
        _, context_key = _comparison_lap_context(store, lap_id, scope)
        return _reference_payload(store, lap_id, scope, context_key)

    @app.get("/api/laps/{lap_id}/ghost")
    async def lap_ghost(lap_id: str, scope: str = DEFAULT_SCOPE) -> dict:
        scope = _comparison_scope(scope)
        _, context_key = _comparison_lap_context(store, lap_id, scope)
        reference_payload = _reference_payload(store, lap_id, scope, context_key)
        reference = reference_payload["reference"]
        samples = []
        if reference is not None:
            samples = ghost_samples_for_reference(store, reference["lap_id"])
        return {
            **reference_payload,
            "samples": _json_safe(samples),
        }

    @app.get("/api/laps/{lap_id}/delta")
    async def lap_delta(
        lap_id: str,
        scope: str = DEFAULT_SCOPE,
        start_sequence: int | None = None,
        end_sequence: int | None = None,
    ) -> dict:
        scope = _comparison_scope(scope)
        _, context_key = _comparison_lap_context(store, lap_id, scope)
        sequence_range = _summary_range(start_sequence, end_sequence)
        reference_payload = _reference_payload(store, lap_id, scope, context_key)
        current_samples = store.samples_for_lap(lap_id)
        reference_samples = []
        reference = reference_payload["reference"]
        if reference is not None:
            reference_samples = store.samples_for_lap(reference["lap_id"])
        if sequence_range is None:
            summary = delta_summary(current_samples, reference_samples)
        else:
            summary = delta_summary(
                current_samples,
                reference_samples,
                start_sequence=sequence_range[0],
                end_sequence=sequence_range[1],
            )
        return {
            **reference_payload,
            "summary": _json_safe(summary),
        }

    @app.post("/api/laps/{lap_id}/analyze")
    async def analyze_lap_endpoint(lap_id: str) -> dict:
        lap = _lap_metadata(store, lap_id)
        if lap is None:
            raise HTTPException(status_code=404, detail="unknown lap_id")
        result = analyze_lap(store, session_id=lap["session_id"], lap_id=lap_id)
        result["markers"] = store.issue_markers_for_lap(lap_id=lap_id)
        return result

    @app.post("/api/laps/{lap_id}/track-match")
    async def match_lap_track_endpoint(lap_id: str) -> dict:
        lap = _lap_metadata(store, lap_id)
        if lap is None:
            raise HTTPException(status_code=404, detail="unknown lap_id")
        try:
            store.ensure_game_track_profiles()
            return match_lap_track(store, lap_id, auto_assign=True)
        except ValueError as exc:
            detail = str(exc)
            if "unknown lap_id" in detail:
                raise HTTPException(status_code=404, detail="unknown lap_id") from exc
            raise HTTPException(status_code=400, detail=detail) from exc

    @app.get("/api/laps/{lap_id}/track-match")
    async def lap_track_match(lap_id: str) -> dict:
        lap = _lap_metadata(store, lap_id)
        if lap is None:
            raise HTTPException(status_code=404, detail="unknown lap_id")
        candidates = store.track_match_candidates_for_lap(lap_id, MATCHER_VERSION)
        return {
            "lap_id": lap_id,
            "session_id": lap["session_id"],
            "matcher_version": MATCHER_VERSION,
            "candidates": candidates,
            "best_candidate": candidates[0] if candidates else None,
        }

    @app.get("/api/laps/{lap_id}/summary")
    async def lap_summary(
        lap_id: str,
        start_sequence: int | None = None,
        end_sequence: int | None = None,
    ) -> dict:
        lap = _lap_metadata(store, lap_id)
        if lap is None:
            raise HTTPException(status_code=404, detail="unknown lap_id")

        sequence_range = _summary_range(start_sequence, end_sequence)
        if sequence_range is None:
            summary = _analysis_summary_for_lap(store, lap_id)
            return {
                "lap_id": lap_id,
                "session_id": lap["session_id"],
                "summary": summary,
                "car": _json_safe(car_info_for_lap(store, lap_id)),
            }

        section_samples = store.samples_for_range(
            lap["session_id"],
            start_sequence=sequence_range[0],
            end_sequence=sequence_range[1],
            lap_id=lap_id,
        )
        if not section_samples:
            raise HTTPException(
                status_code=400,
                detail="sequence range does not contain samples for this lap",
            )
        actual_sequences = [int(sample["sequence"]) for sample in section_samples]
        expected_count = sequence_range[1] - sequence_range[0] + 1
        if (
            actual_sequences[0] != sequence_range[0]
            or actual_sequences[-1] != sequence_range[1]
            or len(set(actual_sequences)) != expected_count
        ):
            raise HTTPException(
                status_code=400,
                detail="sequence range is not fully represented by samples for this lap",
            )
        summary = summarize_section(
            section_samples,
            start_sequence=sequence_range[0],
            end_sequence=sequence_range[1],
        )
        return {"lap_id": lap_id, "session_id": lap["session_id"], "summary": summary}

    @app.get("/api/laps/{lap_id}/markers")
    async def lap_markers(lap_id: str) -> dict:
        lap = _lap_metadata(store, lap_id)
        if lap is None:
            raise HTTPException(status_code=404, detail="unknown lap_id")
        return {
            "lap_id": lap_id,
            "session_id": lap["session_id"],
            "markers": _issue_markers_for_lap_with_backfill(
                store,
                lap_id=lap_id,
                lap=lap,
            ),
        }

    @app.get("/api/sessions")
    async def sessions(
        page: int = 1,
        page_size: int = 100,
        name: str | None = None,
        created_from: int | None = None,
        created_to: int | None = None,
        last_active_from: int | None = None,
        last_active_to: int | None = None,
        lap_count_min: int | None = None,
        lap_count_max: int | None = None,
        track: str | None = None,
        car: str | None = None,
        limit: int | None = None,
    ) -> dict:
        try:
            selected_page_size = _positive_limit(limit) if limit is not None else page_size
            return store.paged_sessions(
                page=_positive_page(page, "page"),
                page_size=selected_page_size,
                name=name,
                created_from=created_from,
                created_to=created_to,
                last_active_from=last_active_from,
                last_active_to=last_active_to,
                lap_count_min=lap_count_min,
                lap_count_max=lap_count_max,
                track=track,
                car=car,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/sessions/active")
    async def active_session() -> dict:
        return {"session": store.active_session()}

    @app.post("/api/sessions/start")
    async def start_session(request: SessionStartRequest | None = None) -> dict:
        try:
            session_id = await pipeline.start_new_session(
                label=request.label if request else None
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session = _session_or_404(store, session_id)
        await bus.publish({"type": "session_started", "session": session})
        return {"session": session}

    @app.post("/api/sessions/{session_id}/activate")
    async def activate_session(session_id: str) -> dict:
        try:
            session = await pipeline.activate_session(session_id)
        except ValueError as exc:
            if "unknown session_id" in str(exc):
                raise HTTPException(status_code=404, detail="unknown session_id") from exc
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"session": session}

    @app.post("/api/sessions/{session_id}/end")
    async def end_session(session_id: str) -> dict:
        _session_or_404(store, session_id)
        await pipeline.end_active_session(session_id, reason="user_end")
        return {"session": _session_or_404(store, session_id)}

    @app.patch("/api/sessions/{session_id}")
    async def rename_session(session_id: str, request: SessionUpdateRequest) -> dict:
        try:
            session = store.rename_session(session_id, request.label)
        except ValueError as exc:
            if "unknown session_id" in str(exc):
                raise HTTPException(status_code=404, detail="unknown session_id") from exc
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await bus.publish({"type": "session_updated", "session": session})
        return {"session": session}

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str) -> dict:
        _session_or_404(store, session_id)
        await pipeline.clear_session_if_active(session_id, reason="session_deleted")
        try:
            deleted = store.delete_session(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="unknown session_id") from exc
        await bus.publish({"type": "session_deleted", "session_id": session_id})
        return {"deleted": True, "session_id": session_id, "session": deleted}

    @app.get("/api/sessions/{session_id}/laps")
    async def session_laps(session_id: str) -> dict:
        _session_or_404(store, session_id)
        return {"session_id": session_id, "laps": store.laps_for_session(session_id)}

    @app.get("/api/tracks/profiles")
    async def track_profiles() -> dict:
        store.ensure_game_track_profiles()
        return {"profiles": _sorted_track_profiles(store)}

    @app.post("/api/tracks/profiles")
    async def create_track_profile(request: TrackProfileCreateRequest) -> dict:
        try:
            profile_id = store.create_track_profile(
                name=_required_text_value(request.name, "name"),
                layout=_required_text_value(request.layout, "layout"),
                source=_required_text_value(request.source or "manual", "source"),
                confidence=_required_text_value(request.confidence or "user", "confidence"),
                shape_signature=request.shape_signature,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"profile": _track_profile_or_404(store, profile_id)}

    @app.post("/api/tracks/profiles/merge")
    async def merge_track_profiles(request: TrackProfileMergeRequest) -> dict:
        keep_profile_id = request.selected_keep_profile_id()
        merge_profile_id = request.selected_merge_profile_id()
        try:
            store.merge_track_profiles(keep_profile_id, merge_profile_id)
        except ValueError as exc:
            raise _track_profile_error(exc) from exc
        return {
            "profile": _track_profile_or_404(store, keep_profile_id),
            "merged_profile_id": merge_profile_id,
        }

    @app.patch("/api/tracks/profiles/{profile_id}")
    async def update_track_profile(
        profile_id: str,
        request: TrackProfileUpdateRequest,
    ) -> dict:
        try:
            store.update_track_profile(
                profile_id,
                _required_text_value(request.name, "name"),
                _required_text_value(request.layout, "layout"),
            )
        except ValueError as exc:
            raise _track_profile_error(exc) from exc
        return {"profile": _track_profile_or_404(store, profile_id)}

    @app.get("/api/tracks/profiles/{profile_id}/assets")
    async def track_assets(profile_id: str) -> dict:
        try:
            return {"assets": _track_assets_payload(store.track_assets_for_profile(profile_id))}
        except ValueError as exc:
            raise _track_profile_error(exc) from exc

    @app.post("/api/tracks/profiles/{profile_id}/assets")
    async def create_track_asset(profile_id: str, request: TrackAssetCreateRequest) -> dict:
        try:
            _track_profile_or_404(store, profile_id)
            filename = _required_text_value(request.filename, "filename")
            mime_type = request.selected_mime_type()
            requested_size = request.selected_size_bytes()
            source_path = _asset_source_path(request.selected_source_path())
            actual_size = source_path.stat().st_size
            if int(requested_size) != int(actual_size):
                raise HTTPException(status_code=400, detail="size_bytes does not match source_path size")
            validate_asset(filename, mime_type, actual_size)
            transform = validate_transform(request.transform)
            stored_path = _copy_track_asset_source(
                store,
                profile_id=profile_id,
                source_path=source_path,
                filename=filename,
            )
            try:
                asset_id = store.create_track_asset(
                    track_profile_id=profile_id,
                    filename=filename,
                    stored_path=str(stored_path),
                    mime_type=mime_type,
                    size_bytes=actual_size,
                    transform=transform,
                )
            except Exception:
                _remove_copied_track_asset(stored_path)
                raise
        except HTTPException:
            raise
        except ValueError as exc:
            raise _track_profile_error(exc) from exc
        asset = store.track_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown track_asset_id")
        return {"asset": _track_asset_payload(asset)}

    @app.patch("/api/tracks/assets/{asset_id}/transform")
    async def update_track_asset_transform(
        asset_id: str,
        request: TrackAssetTransformRequest,
    ) -> dict:
        try:
            asset = store.update_track_asset_transform(asset_id, request.selected_transform())
        except ValueError as exc:
            raise _track_profile_error(exc) from exc
        return {"asset": _track_asset_payload(asset)}

    @app.delete("/api/tracks/assets/{asset_id}")
    async def delete_track_asset(asset_id: str) -> dict:
        try:
            asset = store.delete_track_asset(asset_id)
        except ValueError as exc:
            raise _track_profile_error(exc) from exc
        return {"deleted": True, "asset_id": asset_id, "asset": _track_asset_payload(asset)}

    @app.get("/api/tracks/assets/{asset_id}/file")
    async def track_asset_file(asset_id: str) -> FileResponse:
        asset = store.track_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown track_asset_id")
        path = Path(asset["stored_path"])
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise HTTPException(status_code=404, detail="track asset file is missing") from exc
        storage_root = _track_asset_storage_root(store)
        if not _is_relative_to(resolved, storage_root):
            raise HTTPException(status_code=404, detail="track asset file is missing")
        if not resolved.is_file():
            raise HTTPException(status_code=404, detail="track asset file is missing")
        return FileResponse(
            resolved,
            media_type=str(asset["mime_type"]),
            filename=str(asset["filename"]),
        )

    @app.post("/api/tracks/profiles/{profile_id}/assign")
    async def assign_track_profile(
        profile_id: str,
        request: TrackProfileAssignRequest,
    ) -> dict:
        profile = _track_profile_or_404(store, profile_id)
        session_id = request.selected_session_id()
        lap_id = request.selected_lap_id()
        if lap_id is None:
            raise HTTPException(
                status_code=400,
                detail="lap_id is required for track profile assignment",
            )
        try:
            store.assign_track_profile(session_id, lap_id, profile_id)
        except ValueError as exc:
            raise _track_profile_error(exc) from exc
        return {
            "assignment": {
                "profile_id": profile_id,
                "session_id": session_id,
                "lap_id": lap_id,
            },
            "profile": profile,
        }

    @app.get("/api/sessions/{session_id}/points/{sequence}")
    async def point_detail(session_id: str, sequence: int) -> dict:
        if sequence <= 0:
            raise HTTPException(status_code=400, detail="sequence must be positive")
        session = _session_metadata(store, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="unknown session_id")
        raw_packet = store.raw_packet_at_sequence(session_id, sequence)
        if raw_packet is None:
            raise HTTPException(status_code=404, detail="unknown sequence")
        return {
            "session_id": session_id,
            "sequence": int(sequence),
            "point": _json_safe(decode_packet(raw_packet)),
        }

    async def wait_for_import_safe_slot(job: RawTelemetryImportJob) -> None:
        while bool(capture.status()["recording"]["active"]):
            if job.cancel_requested:
                raise asyncio.CancelledError
            job.status = "running"
            job.status_text = "Waiting for live recording to stop before importing..."
            await asyncio.sleep(0.5)

    async def run_raw_import_job(job: RawTelemetryImportJob) -> None:
        try:
            async with raw_import_runner_lock:
                if job.cancel_requested:
                    raise asyncio.CancelledError
                job.status = "running"
                job.started_at_ms = int(time.time() * 1000)
                job.status_text = "Starting raw telemetry import..."

                for index, source in enumerate(job.files, start=1):
                    if job.cancel_requested:
                        raise asyncio.CancelledError
                    await wait_for_import_safe_slot(job)
                    job.current_file = source.display_name
                    job.current_file_index = index
                    job.current_file_packets = 0
                    job.current_file_packets_processed = 0
                    job.status_text = f"Checking {source.display_name}..."

                    try:
                        total_packets = _raw_packet_count_for_path(source.staged_path)

                        async def update_progress(processed_packets: int, file_packets: int) -> None:
                            job.update_file_progress(processed_packets, file_packets)
                            job.status_text = (
                                f"Importing {source.display_name} "
                                f"({processed_packets:,}/{file_packets:,} packets)..."
                            )

                        file_label = _label_for_import_source(job, source)
                        session_ids = await pipeline.replay_packet_iterable(
                            _iter_raw_packet_file(source.staged_path),
                            label=file_label,
                            total_packets=total_packets,
                            event_bus=EventBus(),
                            progress_callback=update_progress,
                        )
                        job.session_ids.extend(session_ids)
                        job.lap_ids.extend(_lap_ids_for_sessions(store, session_ids))
                        packet_count = sum(store.count_packets(session_id) for session_id in session_ids)
                        job.packet_count += packet_count
                        job.processed_files += 1
                        job.update_file_progress(total_packets, total_packets)
                        job.status_text = (
                            f"Imported {source.display_name} "
                            f"({packet_count:,} stored packets)."
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        job.failed_files += 1
                        job.processed_files += 1
                        job.add_error(source, str(exc))
                        job.progress = min(1.0, job.processed_files / max(1, job.total_files))
                        job.status_text = f"Skipped {source.display_name}: {exc}"

                imported_files = job.processed_files - job.failed_files
                if job.session_ids:
                    text = (
                        f"Imported {job.packet_count:,} packets from "
                        f"{imported_files} of {job.total_files} files."
                    )
                    if job.failed_files:
                        text += f" {job.failed_files} files failed."
                    job.mark_terminal("completed", text)
                elif job.error_count:
                    first_error = job.errors[0]["message"] if job.errors else "no telemetry was imported"
                    job.mark_terminal("failed", f"No telemetry imported: {first_error}")
                else:
                    job.mark_terminal("failed", "No telemetry was imported.")
        except asyncio.CancelledError:
            kept = len(job.session_ids)
            text = "Import job cancelled."
            if kept:
                text = f"Import job cancelled; {kept} completed sessions were kept."
            job.mark_terminal("cancelled", text)
        except Exception as exc:  # pragma: no cover - defensive guard for unexpected job failures
            job.add_error(None, str(exc))
            job.mark_terminal("failed", f"Import job failed: {exc}")
        finally:
            shutil.rmtree(job.staged_dir, ignore_errors=True)

    async def raw_import_job_snapshots() -> list[dict]:
        async with raw_import_jobs_lock:
            jobs = sorted(raw_import_jobs.values(), key=lambda item: item.created_at_ms, reverse=True)
            return [job.snapshot() for job in jobs]

    async def raw_import_job_or_404(job_id: str) -> RawTelemetryImportJob:
        async with raw_import_jobs_lock:
            job = raw_import_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown import job")
        return job

    async def replay_raw_bytes_payload(raw: bytes, label: str, recording_mode: bool) -> dict:
        if recording_mode:
            try:
                if not raw:
                    raise ValueError("raw file contains no packets")
                packets = list(iter_packet_bytes(raw))
                session_ids = await pipeline.replay_packets(packets, label=label)
                app.state.lap_detector = pipeline.lap_detector
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            session_id = session_ids[-1] if session_ids else None
            packet_count = (
                sum(store.count_packets(candidate_session_id) for candidate_session_id in session_ids)
                if session_ids
                else 0
            )
            samples = store.latest_samples(session_id, limit=200) if session_id else []
            return {
                "session_id": session_id,
                "session_ids": session_ids,
                "lap_ids": _lap_ids_for_sessions(store, session_ids),
                "packet_count": packet_count,
                "samples": samples,
            }

        try:
            session_id = await replay_raw_bytes(raw, store, ingest, label=label)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "session_id": session_id,
            "session_ids": [session_id],
            "lap_ids": [],
            "packet_count": store.count_packets(session_id),
            "samples": store.latest_samples(session_id, limit=200),
        }

    def export_file_payload(result: TelemetryExportResult) -> list[dict]:
        return [
            {
                "path": str(item.path),
                "filename": item.filename,
                "size_bytes": item.size_bytes,
            }
            for item in result.output_files
        ]

    async def run_export_job(job: TelemetryExportJob) -> None:
        try:
            async with export_runner_lock:
                if job.cancel_requested:
                    raise asyncio.CancelledError
                job.status = "running"
                job.status_text = f"Exporting {job.label}..."
                job.started_at_ms = int(time.time() * 1000)
                estimate = export_estimate(store.db_path)
                if (
                    job.kind in {TelemetryExportKind.raw_binary, TelemetryExportKind.raw_csv}
                    and int(estimate.get("raw_packet_count", 0)) == 0
                ) or (
                    job.kind == TelemetryExportKind.curated_csv
                    and int(estimate.get("curated_sample_count", 0)) == 0
                ):
                    raise ValueError("No recorded telemetry is available to export")
                result = await asyncio.to_thread(
                    export_telemetry,
                    store.db_path,
                    job.kind,
                    job.output_dir,
                    filename_prefix=job.filename_prefix,
                    should_cancel=lambda: job.cancel_requested,
                )
                job.output_files = export_file_payload(result)
                job.total_size_bytes = int(result.total_size_bytes)
                job.row_count = int(result.row_count)
                job.progress = 1.0
                job.completed_at_ms = int(time.time() * 1000)
                job.duration_ms = job.completed_at_ms - (
                    job.started_at_ms or job.completed_at_ms
                )
                job.status = "completed"
                job.status_text = f"Exported {job.row_count:,} rows."
        except (asyncio.CancelledError, InterruptedError):
            job.output_files = []
            job.completed_at_ms = int(time.time() * 1000)
            job.duration_ms = (
                job.completed_at_ms - job.started_at_ms
                if job.started_at_ms is not None
                else None
            )
            job.status = "cancelled"
            job.status_text = "Telemetry export cancelled."
            job.progress = 1.0
        except Exception as exc:
            job.output_files = []
            job.total_size_bytes = 0
            job.row_count = 0
            job.completed_at_ms = int(time.time() * 1000)
            job.duration_ms = (
                job.completed_at_ms - job.started_at_ms
                if job.started_at_ms is not None
                else None
            )
            job.status = "failed"
            job.status_text = "Telemetry export failed."
            job.error = str(exc)
            job.progress = 1.0

    async def export_job_snapshots() -> list[dict]:
        async with export_jobs_lock:
            jobs = sorted(export_jobs.values(), key=lambda item: item.created_at_ms, reverse=True)
            return [job.snapshot() for job in jobs]

    async def export_job_or_404(job_id: str) -> TelemetryExportJob:
        async with export_jobs_lock:
            job = export_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown export job")
        return job

    @app.get("/api/telemetry/export-defaults")
    async def telemetry_export_defaults() -> dict:
        estimate = export_estimate(store.db_path)
        return {
            "output_dir": str(default_export_dir),
            "filename_prefix": "forza-telemetry-tracker",
            "estimate": estimate,
            "kinds": [
                {"kind": kind.value, "label": kind.label}
                for kind in TelemetryExportKind
            ],
        }

    @app.get("/api/telemetry/export-jobs")
    async def telemetry_export_jobs() -> dict:
        return {"jobs": await export_job_snapshots()}

    @app.post("/api/telemetry/export-jobs")
    async def create_telemetry_export_job(
        request: TelemetryExportJobRequest,
        x_forza_telemetry_export: str | None = Header(
            default=None,
            alias="X-Forza-Telemetry-Export",
        ),
    ) -> dict:
        if x_forza_telemetry_export != "1":
            raise HTTPException(
                status_code=400,
                detail="X-Forza-Telemetry-Export header with value 1 is required",
            )
        try:
            kind = request.selected_kind()
            output_dir = request.selected_output_dir(default_export_dir)
            filename_prefix = request.selected_filename_prefix()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        job = TelemetryExportJob(
            id=str(uuid.uuid4()),
            kind=kind,
            label=kind.label,
            output_dir=output_dir,
            filename_prefix=filename_prefix,
            created_at_ms=int(time.time() * 1000),
        )
        async with export_jobs_lock:
            queued_ahead = sum(
                1
                for existing_job in export_jobs.values()
                if existing_job.status in {"queued", "running", "cancelling"}
            )
            if queued_ahead:
                job_noun = "job" if queued_ahead == 1 else "jobs"
                job.status_text = f"Queued behind {queued_ahead} active export {job_noun}."
            export_jobs[job.id] = job
        job.task = asyncio.create_task(run_export_job(job))
        return {"job": job.snapshot()}

    @app.post("/api/telemetry/export-jobs/{job_id}/cancel")
    async def cancel_telemetry_export_job(job_id: str) -> dict:
        job = await export_job_or_404(job_id)
        if job.status in {"completed", "failed", "cancelled"}:
            return {"job": job.snapshot()}
        job.cancel_requested = True
        job.status = "cancelling"
        job.status_text = "Cancelling telemetry export..."
        if job.task is not None and not job.task.done() and job.started_at_ms is None:
            job.task.cancel()
        return {"job": job.snapshot()}

    @app.get("/api/replay/import-jobs")
    async def replay_import_jobs() -> dict:
        return {"jobs": await raw_import_job_snapshots()}

    @app.post("/api/replay/import-jobs/upload")
    async def replay_import_job_upload(
        files: list[UploadFile] = File(...),
        label: str | None = Form(None),
        source_type: str | None = Form(None),
    ) -> dict:
        try:
            staged_files, staged_dir, total_bytes = await _stage_uploaded_raw_telemetry_files(files)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"failed to read uploaded raw telemetry: {exc}") from exc
        finally:
            for file in files:
                await file.close()

        clean_source_type = str(source_type or "").strip().lower()
        if clean_source_type not in {"file", "files", "folder"}:
            clean_source_type = "folder" if len(staged_files) > 1 else "file"
        job = RawTelemetryImportJob(
            id=str(uuid.uuid4()),
            label=_label_for_import_job(label, clean_source_type, staged_files),
            source_type=clean_source_type,
            files=staged_files,
            staged_dir=staged_dir,
            total_bytes=total_bytes,
            created_at_ms=int(time.time() * 1000),
        )
        async with raw_import_jobs_lock:
            queued_ahead = sum(
                1
                for existing_job in raw_import_jobs.values()
                if existing_job.status in {"queued", "running", "cancelling"}
            )
            if queued_ahead:
                job_noun = "job" if queued_ahead == 1 else "jobs"
                job.status_text = f"Queued behind {queued_ahead} active import {job_noun}."
            raw_import_jobs[job.id] = job
        job.task = asyncio.create_task(run_raw_import_job(job))
        return {"job": job.snapshot()}

    @app.post("/api/replay/import-jobs/{job_id}/cancel")
    async def cancel_replay_import_job(job_id: str) -> dict:
        job = await raw_import_job_or_404(job_id)
        if job.status in {"completed", "failed", "cancelled"}:
            return {"job": job.snapshot()}
        job.cancel_requested = True
        job.status = "cancelling"
        job.status_text = "Cancelling raw telemetry import..."
        if job.task is not None and not job.task.done():
            job.task.cancel()
        return {"job": job.snapshot()}

    @app.post("/api/replay/upload")
    async def replay_upload(
        file: UploadFile = File(...),
        label: str | None = Form(None),
    ) -> dict:
        try:
            raw = await _read_uploaded_raw_telemetry(file)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"failed to read uploaded raw telemetry: {exc}") from exc
        finally:
            await file.close()
        return await replay_raw_bytes_payload(
            raw,
            _label_for_uploaded_replay(label, file.filename),
            True,
        )

    @app.post("/api/replay")
    async def replay(request: ReplayRequest) -> dict:
        raw_path = _raw_path_for_replay(request.raw_path)
        if request.recording_mode:
            try:
                raw = raw_path.read_bytes()
            except OSError as exc:
                raise HTTPException(status_code=400, detail=f"failed to read raw_path: {exc}") from exc
            return await replay_raw_bytes_payload(raw, request.label, True)

        try:
            session_id = await replay_raw_file(raw_path, store, ingest, label=request.label)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"failed to read raw_path: {exc}") from exc
        return {
            "session_id": session_id,
            "session_ids": [session_id],
            "lap_ids": [],
            "packet_count": store.count_packets(session_id),
            "samples": store.latest_samples(session_id, limit=200),
        }

    @app.get("/events")
    async def events() -> StreamingResponse:
        return StreamingResponse(stream_sse_events(bus), media_type="text/event-stream")

    if frontend_dist is None:
        frontend_dist = default_desktop_paths().frontend_dist
    frontend_dist = Path(frontend_dist)
    if frontend_dist.is_dir():
        assets_dir = frontend_dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        index_path = frontend_dist / "index.html"
        if index_path.is_file():
            @app.get("/")
            async def frontend_index() -> FileResponse:
                return FileResponse(index_path)

    return app
