"""Trusted local file selections shared by the desktop bridge and API."""

from __future__ import annotations

import re
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


SelectionClock = Callable[[], float]
SelectionTokenFactory = Callable[[], str]

_SELECTION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
DEFAULT_MAX_SELECTION_FILES = 500


@dataclass(frozen=True)
class LocalFileSelection:
    selection_id: str
    source_type: str
    paths: tuple[Path, ...]
    folder_path: Path | None
    display_name: str
    summary: str
    created_at: float
    expires_at: float

    @property
    def file_count(self) -> int:
        return len(self.paths)

    def payload(self) -> dict:
        return {
            "selection_id": self.selection_id,
            "source_type": self.source_type,
            "file_count": self.file_count,
            "display_name": self.display_name,
            "summary": self.summary,
            "expires_at_ms": int(self.expires_at * 1000),
        }


class LocalFileSelectionRegistry:
    """One-time registry for paths selected through trusted desktop dialogs."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 300.0,
        max_files: int = DEFAULT_MAX_SELECTION_FILES,
        clock: SelectionClock = time.monotonic,
        token_factory: SelectionTokenFactory | None = None,
    ) -> None:
        self.ttl_seconds = float(ttl_seconds)
        self.max_files = int(max_files)
        self._clock = clock
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(24))
        self._selections: dict[str, LocalFileSelection] = {}
        self._lock = threading.RLock()

    def register_files(self, raw_paths: Iterable[str | Path]) -> dict:
        paths = tuple(self._resolve_file_path(path) for path in raw_paths)
        if not paths:
            raise ValueError("at least one raw telemetry file must be selected")
        self._validate_file_count(len(paths))
        source_type = "files" if len(paths) > 1 else "file"
        display_name = self._display_name_for_files(paths)
        summary = (
            f"Selected {len(paths):,} native files"
            if len(paths) > 1
            else f"Selected native file: {paths[0].name or 'raw telemetry'}"
        )
        with self._lock:
            selection = self._selection(
                source_type=source_type,
                paths=paths,
                folder_path=None,
                display_name=display_name,
                summary=summary,
            )
        return selection.payload()

    def register_folder(self, raw_path: str | Path) -> dict:
        folder = self._resolve_folder_path(raw_path)
        paths = self._folder_files(folder)
        display_name = folder.name.strip() or "Imported raw telemetry folder"
        summary = f"Selected native folder: {display_name}"
        with self._lock:
            selection = self._selection(
                source_type="folder",
                paths=paths,
                folder_path=folder,
                display_name=display_name,
                summary=summary,
            )
        return selection.payload()

    def _folder_files(self, folder: Path) -> tuple[Path, ...]:
        paths: list[Path] = []
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            paths.append(path)
            self._validate_file_count(len(paths))
        return tuple(sorted(paths, key=lambda item: str(item).lower()))

    def consume(self, selection_id: str) -> LocalFileSelection:
        with self._lock:
            clean_id = self._validate_selection_id(selection_id)
            self._purge_expired()
            selection = self._selections.pop(clean_id, None)
            if selection is None:
                raise ValueError("unknown or expired local file selection")
            if selection.expires_at <= self._clock():
                raise ValueError("unknown or expired local file selection")
            return selection

    def _selection(
        self,
        *,
        source_type: str,
        paths: tuple[Path, ...],
        folder_path: Path | None,
        display_name: str,
        summary: str,
    ) -> LocalFileSelection:
        self._purge_expired()
        now = self._clock()
        selection_id = self._new_selection_id()
        selection = LocalFileSelection(
            selection_id=selection_id,
            source_type=source_type,
            paths=paths,
            folder_path=folder_path,
            display_name=display_name,
            summary=summary,
            created_at=now,
            expires_at=now + self.ttl_seconds,
        )
        self._selections[selection_id] = selection
        return selection

    def _new_selection_id(self) -> str:
        for _ in range(10):
            selection_id = self._validate_selection_id(self._token_factory())
            if selection_id not in self._selections:
                return selection_id
        raise RuntimeError("failed to allocate unique local file selection id")

    def _purge_expired(self) -> None:
        now = self._clock()
        expired = [selection_id for selection_id, selection in self._selections.items() if selection.expires_at <= now]
        for selection_id in expired:
            self._selections.pop(selection_id, None)

    def _validate_file_count(self, count: int) -> None:
        if count > self.max_files:
            raise ValueError(f"raw telemetry selection accepts at most {self.max_files} files")

    @staticmethod
    def _validate_selection_id(selection_id: str) -> str:
        clean_id = str(selection_id or "").strip()
        if not _SELECTION_ID_RE.fullmatch(clean_id):
            raise ValueError("invalid local file selection id")
        return clean_id

    @staticmethod
    def _resolve_file_path(raw_path: str | Path) -> Path:
        try:
            resolved = Path(raw_path).expanduser().resolve(strict=True)
        except OSError as exc:
            raise ValueError("selected raw telemetry file does not exist") from exc
        if not resolved.is_file():
            raise ValueError("selected raw telemetry path must be a file")
        return resolved

    @staticmethod
    def _resolve_folder_path(raw_path: str | Path) -> Path:
        try:
            resolved = Path(raw_path).expanduser().resolve(strict=True)
        except OSError as exc:
            raise ValueError("selected raw telemetry folder does not exist") from exc
        if not resolved.is_dir():
            raise ValueError("selected raw telemetry path must be a folder")
        return resolved

    @staticmethod
    def _display_name_for_files(paths: tuple[Path, ...]) -> str:
        if len(paths) > 1:
            return f"Imported {len(paths)} raw telemetry files"
        return paths[0].stem.strip() or paths[0].name.strip() or "Imported raw telemetry"
