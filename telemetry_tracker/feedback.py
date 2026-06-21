"""Anonymous feedback report construction and delivery."""

from __future__ import annotations

import base64
import copy
import json
import locale
import os
import platform
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from telemetry_tracker import __version__
from telemetry_tracker.app_metadata import ReleaseMetadata
from telemetry_tracker.app_paths import DesktopPaths
from telemetry_tracker.diagnostics import diagnostics_payload
from telemetry_tracker.storage import TelemetryStore

FEEDBACK_CATEGORIES = (
    "Bug",
    "Data Out setup",
    "Telemetry recording",
    "Map or route visualisation",
    "Import or export",
    "Performance",
    "UI or UX",
    "Other",
)
MAX_DESCRIPTION_LENGTH = 4000
MAX_DIAGNOSTICS_LOG_CHARS = 16_000
REPORT_REF_PREFIX = "FTT-"
REPORTER_ID_KEY = "feedback_reporter_id"
DEFAULT_SOURCE = "desktop-app"
QUEUED_MESSAGE = "Feedback saved. We'll send it when you're back online."
DIAGNOSTICS_DESCRIPTION = (
    "Diagnostics may include app version, platform, listener/capture status, "
    "local database/log sizes, row counts, and recent sanitized app log lines. "
    "They do not include raw telemetry packets, session databases, map cache files, "
    "game files, screenshots, exports, personal files, GitHub credentials, or Cloudflare credentials."
)

_RETRYABLE_STATUS_CODES = {408, 425, 429}
_REJECTED_STATUS_CODES = {400, 413, 422}
_LOG_FILE_NAMES = ("app.log", "backend.log")


class FeedbackValidationError(ValueError):
    """Raised when a local feedback request is invalid."""


class RetryableFeedbackError(RuntimeError):
    """Raised when Worker delivery failed in a way that should be queued."""


class RejectedFeedbackError(RuntimeError):
    """Raised when the Worker rejected a report permanently."""


@dataclass(frozen=True)
class FeedbackRequest:
    category: str
    description: str
    include_diagnostics: bool = False
    source: str | None = None
    scene: str | None = None


def generate_report_ref() -> str:
    suffix = base64.b32encode(os.urandom(5)).decode("ascii")
    return f"{REPORT_REF_PREFIX}{suffix}"


def get_or_create_reporter_id(store: TelemetryStore) -> str:
    existing = store.feedback_state_value(REPORTER_ID_KEY)
    if existing:
        try:
            return str(uuid.UUID(existing))
        except ValueError:
            pass

    reporter_id = str(uuid.uuid4())
    store.set_feedback_state_value(REPORTER_ID_KEY, reporter_id)
    return reporter_id


def sanitize_log_text(text: str) -> str:
    sanitized = str(text)
    sanitized = re.sub(
        r"\bBearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer [redacted token]",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"\b([A-Za-z0-9_.-]*(?:api[_-]?key|token|secret|password|passwd|pwd|authorization|auth)[A-Za-z0-9_.-]*)\s*[:=]\s*['\"]?([^\s'\",;]+)",
        r"\1=[redacted secret]",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        "[redacted email]",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b",
        "[redacted ip address]",
        sanitized,
    )
    sanitized = re.sub(
        r"\b(?:[A-F0-9]{1,4}:){1,7}:?[A-F0-9]{0,4}\b",
        "[redacted ip address]",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"([A-Za-z]:\\Users\\)([^\\\r\n]+)",
        r"\1[redacted-user]",
        sanitized,
    )
    sanitized = re.sub(
        r"(/Users/)([^/\r\n]+)",
        r"\1[redacted-user]",
        sanitized,
    )
    sanitized = re.sub(
        r"(/home/)([^/\r\n]+)",
        r"\1[redacted-user]",
        sanitized,
    )
    return sanitized[-MAX_DIAGNOSTICS_LOG_CHARS:]


def build_feedback_diagnostics(
    *,
    store: TelemetryStore,
    app_version: str,
    listener_status: dict | None = None,
    capture_status: dict | None = None,
    logs_dir: Path | None = None,
    include_logs: bool,
) -> dict[str, Any]:
    payload = diagnostics_payload(
        store,
        app_version=app_version,
        listener_status=listener_status,
        capture_status=capture_status,
    )
    diagnostics = _sanitize_diagnostics(payload)
    if include_logs and logs_dir is not None:
        diagnostics["recent_log"] = _read_recent_logs(Path(logs_dir))
    return diagnostics


def build_feedback_report(
    *,
    store: TelemetryStore,
    category: str,
    description: str,
    include_diagnostics: bool,
    report_ref: str,
    reporter_id: str,
    source: str | None,
    release_metadata: ReleaseMetadata | None = None,
    runtime_paths: DesktopPaths | None = None,
    listener_status: dict | None = None,
    capture_status: dict | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    trimmed_description = _validated_description(description)
    if category not in FEEDBACK_CATEGORIES:
        raise FeedbackValidationError("category is not supported")

    metadata = release_metadata or ReleaseMetadata()
    timestamp = now or datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "report_ref": report_ref,
        "reporter_id": reporter_id,
        "category": category,
        "description": trimmed_description,
        "source": (source or DEFAULT_SOURCE).strip() or DEFAULT_SOURCE,
        "scene": "desktop-app",
        "include_diagnostics": bool(include_diagnostics),
        "build": _build_metadata(metadata),
        "platform": _platform_metadata(),
        "settings": _settings_metadata(store),
        "client_timestamp_utc": _format_utc(timestamp),
    }
    if include_diagnostics:
        payload["diagnostics"] = build_feedback_diagnostics(
            store=store,
            app_version=metadata.version,
            listener_status=listener_status,
            capture_status=capture_status,
            logs_dir=runtime_paths.logs_dir if runtime_paths is not None else None,
            include_logs=True,
        )
    return payload


class FeedbackService:
    def __init__(
        self,
        *,
        store: TelemetryStore,
        endpoint: str | None,
        runtime_paths: DesktopPaths | None = None,
        release_metadata: ReleaseMetadata | None = None,
        listener_status: Callable[[], dict] | None = None,
        capture_status: Callable[[], dict] | None = None,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self.store = store
        self.endpoint = endpoint.strip() if endpoint and endpoint.strip() else None
        self.runtime_paths = runtime_paths
        self.release_metadata = release_metadata or ReleaseMetadata()
        self.listener_status = listener_status
        self.capture_status = capture_status
        self.client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=10.0))

    async def config(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "categories": list(FEEDBACK_CATEGORIES),
            "max_description_length": MAX_DESCRIPTION_LENGTH,
            "diagnostics_default": False,
            "diagnostics_description": DIAGNOSTICS_DESCRIPTION,
        }

    async def submit(self, request: FeedbackRequest) -> dict[str, Any]:
        report_ref = self._generate_unique_report_ref()
        reporter_id = get_or_create_reporter_id(self.store)
        now_ms = _now_ms()
        payload = build_feedback_report(
            store=self.store,
            category=request.category,
            description=request.description,
            include_diagnostics=request.include_diagnostics,
            report_ref=report_ref,
            reporter_id=reporter_id,
            source=request.source,
            release_metadata=self.release_metadata,
            runtime_paths=self.runtime_paths,
            listener_status=self._listener_status(),
            capture_status=self._capture_status(),
        )

        if self.endpoint is None:
            self._queue_payload(payload, now_ms, now_ms)
            return _queued_response(report_ref)

        try:
            result = await self._post_payload(payload)
        except RejectedFeedbackError as exc:
            return {"status": "rejected", "report_ref": report_ref, "message": str(exc)}
        except RetryableFeedbackError as exc:
            self._queue_payload(payload, now_ms, _next_attempt_ms(now_ms))
            return _queued_response(report_ref, str(exc))

        self.store.mark_feedback_report_sent(
            report_ref,
            result.get("issue_number"),
            result.get("issue_url"),
            _now_ms(),
        )
        return {
            "status": "sent",
            "report_ref": report_ref,
            "issue_number": result.get("issue_number"),
            "issue_url": result.get("issue_url"),
        }

    async def retry_pending(self, limit: int = 5) -> dict[str, Any]:
        if self.endpoint is None:
            return {"attempted": 0, "sent": 0, "queued": 0, "rejected": 0, "reports": []}

        now_ms = _now_ms()
        rows = self.store.pending_feedback_reports(now_ms, limit=max(1, int(limit)))
        sent = 0
        queued = 0
        rejected = 0
        reports: list[dict[str, Any]] = []
        for row in rows:
            report_ref = str(row["report_ref"])
            payload = json.loads(str(row["payload_json"]))
            try:
                result = await self._post_payload(payload)
            except RejectedFeedbackError as exc:
                rejected += 1
                self.store.delete_feedback_report(report_ref)
                reports.append({"report_ref": report_ref, "status": "rejected", "message": str(exc)})
                continue
            except RetryableFeedbackError as exc:
                queued += 1
                self.store.mark_feedback_report_failed(
                    report_ref,
                    str(exc),
                    _now_ms(),
                    _next_attempt_ms(_now_ms(), int(row["attempt_count"]) + 1),
                )
                reports.append({"report_ref": report_ref, "status": "queued", "message": QUEUED_MESSAGE})
                continue

            sent += 1
            self.store.mark_feedback_report_sent(
                report_ref,
                result.get("issue_number"),
                result.get("issue_url"),
                _now_ms(),
            )
            reports.append(
                {
                    "report_ref": report_ref,
                    "status": "sent",
                    "issue_number": result.get("issue_number"),
                    "issue_url": result.get("issue_url"),
                }
            )

        self.store.prune_feedback_outbox(_now_ms())
        return {
            "attempted": len(rows),
            "sent": sent,
            "queued": queued,
            "rejected": rejected,
            "reports": reports,
        }

    def _generate_unique_report_ref(self) -> str:
        for _attempt in range(20):
            report_ref = generate_report_ref()
            if not self.store.feedback_report_exists(report_ref):
                return report_ref
        raise RuntimeError("could not generate a unique feedback report reference")

    def _queue_payload(self, payload: dict[str, Any], now_ms: int, next_attempt_at_ms: int) -> None:
        self.store.enqueue_feedback_report(
            str(payload["report_ref"]),
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            now_ms,
            next_attempt_at_ms,
        )
        self.store.prune_feedback_outbox(now_ms)

    def _listener_status(self) -> dict | None:
        return self.listener_status() if self.listener_status is not None else None

    def _capture_status(self) -> dict | None:
        return self.capture_status() if self.capture_status is not None else None

    async def _post_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.endpoint is None:
            raise RetryableFeedbackError("Feedback endpoint is not configured")

        try:
            async with self.client_factory() as client:
                response = await client.post(self.endpoint, json=payload)
        except httpx.HTTPError as exc:
            raise RetryableFeedbackError("Feedback endpoint is unavailable") from exc

        response_payload: dict[str, Any] = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                response_payload = parsed
        except ValueError:
            response_payload = {}

        if response.status_code in _REJECTED_STATUS_CODES:
            raise RejectedFeedbackError(_worker_error_message(response_payload, "Feedback report was rejected."))
        if response.status_code in _RETRYABLE_STATUS_CODES or response.status_code >= 500:
            raise RetryableFeedbackError(_worker_error_message(response_payload, "Feedback endpoint is unavailable"))
        if not response.is_success:
            raise RejectedFeedbackError(_worker_error_message(response_payload, "Feedback report was rejected."))
        if response_payload.get("ok") is not True:
            raise RetryableFeedbackError("Feedback endpoint returned an unexpected response")

        return response_payload


def _validated_description(description: str) -> str:
    trimmed = str(description).strip()
    if len(trimmed) < 3:
        raise FeedbackValidationError("description must be at least 3 characters")
    if len(trimmed) > MAX_DESCRIPTION_LENGTH:
        raise FeedbackValidationError(f"description must be {MAX_DESCRIPTION_LENGTH} characters or fewer")
    return trimmed


def _build_metadata(metadata: ReleaseMetadata) -> dict[str, Any]:
    return {
        "display_version": metadata.version,
        "build_identifier": metadata.git_sha or metadata.version or __version__,
        "build_channel": metadata.channel,
        "git_short_sha": metadata.git_sha[:12] if metadata.git_sha else None,
        "metadata_source": "release-metadata" if metadata.packaged else "development",
    }


def _platform_metadata() -> dict[str, Any]:
    return {
        "os_name": platform.system(),
        "os_version": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "locale": locale.getlocale()[0],
    }


def _settings_metadata(store: TelemetryStore) -> dict[str, Any]:
    world_map_settings = dict(store.world_map_settings())
    world_map_settings.pop("fh6_media_root", None)
    return {
        "world_map": {
            "enabled": bool(world_map_settings.get("world_map_enabled")),
            "season": world_map_settings.get("world_map_season"),
        },
    }


def _sanitize_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    diagnostics = copy.deepcopy(payload)
    world_map = diagnostics.get("world_map")
    if isinstance(world_map, dict):
        settings = world_map.get("settings")
        if isinstance(settings, dict) and settings.get("fh6_media_root"):
            settings["fh6_media_root"] = "[redacted local path]"
    return _sanitize_structured(diagnostics)


def _sanitize_structured(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_log_text(value)
    if isinstance(value, list):
        return [_sanitize_structured(item) for item in value]
    if isinstance(value, dict):
        return {sanitize_log_text(str(key)): _sanitize_structured(item) for key, item in value.items()}
    return value


def _read_recent_logs(logs_dir: Path) -> str:
    chunks: list[str] = []
    for file_name in _LOG_FILE_NAMES:
        path = logs_dir / file_name
        if not path.is_file():
            continue
        try:
            tail = path.read_bytes()[-MAX_DIAGNOSTICS_LOG_CHARS:]
        except OSError:
            continue
        text = tail.decode("utf-8", errors="replace")
        chunks.append(f"== {file_name} ==\n{text}")
    return sanitize_log_text("\n".join(chunks))[-MAX_DIAGNOSTICS_LOG_CHARS:]


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _next_attempt_ms(now_ms: int, attempt_count: int = 0) -> int:
    delay_ms = min(60 * 60 * 1000, max(1, attempt_count + 1) * 5 * 60 * 1000)
    return int(now_ms) + delay_ms


def _queued_response(report_ref: str, error: str | None = None) -> dict[str, Any]:
    response = {"status": "queued", "report_ref": report_ref, "message": QUEUED_MESSAGE}
    if error:
        response["last_error"] = error
    return response


def _worker_error_message(payload: dict[str, Any], fallback: str) -> str:
    error = payload.get("error") or payload.get("message") or payload.get("detail")
    return str(error) if error else fallback

