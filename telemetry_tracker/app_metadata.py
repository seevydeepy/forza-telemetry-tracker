"""Build/release metadata for the desktop tracker."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from telemetry_tracker import __version__

DEFAULT_RELEASE_REPOSITORY = "seevydeepy/forza-telemetry-tracker"
DEFAULT_UPDATE_CHANNEL = "dev"
ENV_VERSION = "FORZA_TRACKER_VERSION"
ENV_RELEASE_DATE = "FORZA_TRACKER_RELEASE_DATE"
ENV_GIT_SHA = "FORZA_TRACKER_GIT_SHA"
ENV_RELEASE_REPOSITORY = "FORZA_TRACKER_RELEASE_REPOSITORY"
ENV_UPDATE_CHANNEL = "FORZA_TRACKER_UPDATE_CHANNEL"


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class ReleaseMetadata:
    """Metadata embedded in packaged builds and exposed through the About API."""

    version: str = __version__
    release_date: str | None = None
    git_sha: str | None = None
    repository: str = DEFAULT_RELEASE_REPOSITORY
    channel: str = DEFAULT_UPDATE_CHANNEL
    packaged: bool = field(default_factory=lambda: bool(getattr(sys, "frozen", False)))

    @property
    def stable_channel(self) -> bool:
        return self.channel.strip().lower() == "stable"

    def to_about_payload(self, *, updates: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": "Forza Telemetry Tracker",
            "version": self.version,
            "release_date": self.release_date,
            "git_sha": self.git_sha,
            "channel": self.channel,
            "repository": self.repository,
            "packaged": self.packaged,
            "updates": updates,
        }


def metadata_from_mapping(data: dict[str, Any], *, packaged: bool | None = None) -> ReleaseMetadata:
    return ReleaseMetadata(
        version=_clean_text(data.get("version")) or __version__,
        release_date=_clean_text(data.get("release_date") or data.get("releaseDate")),
        git_sha=_clean_text(data.get("git_sha") or data.get("gitSha")),
        repository=_clean_text(data.get("repository") or data.get("repo")) or DEFAULT_RELEASE_REPOSITORY,
        channel=_clean_text(data.get("channel")) or DEFAULT_UPDATE_CHANNEL,
        packaged=bool(getattr(sys, "frozen", False)) if packaged is None else packaged,
    )


def load_release_metadata(path: Path | None = None) -> ReleaseMetadata:
    """Load release metadata from an embedded JSON file with environment overrides.

    Development runs fall back to ``telemetry_tracker.__version__``. Packaged
    release builds embed ``release-metadata.json``; CI and smoke tests can still
    override individual fields through environment variables.
    """

    data: dict[str, Any] = {}
    if path is not None and Path(path).is_file():
        try:
            loaded = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, json.JSONDecodeError):
            # Metadata should never prevent the tracker from starting.
            data = {}

    env_overrides = {
        "version": os.environ.get(ENV_VERSION),
        "release_date": os.environ.get(ENV_RELEASE_DATE),
        "git_sha": os.environ.get(ENV_GIT_SHA),
        "repository": os.environ.get(ENV_RELEASE_REPOSITORY),
        "channel": os.environ.get(ENV_UPDATE_CHANNEL),
    }
    for key, value in env_overrides.items():
        if _clean_text(value) is not None:
            data[key] = value
    return metadata_from_mapping(data)


def write_release_metadata(path: Path, metadata: ReleaseMetadata) -> None:
    """Write deterministic release metadata for packaging scripts."""

    payload = {
        "version": metadata.version,
        "release_date": metadata.release_date,
        "git_sha": metadata.git_sha,
        "repository": metadata.repository,
        "channel": metadata.channel,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
