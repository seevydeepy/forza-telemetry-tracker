"""GitHub Releases update checking helpers."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from telemetry_tracker.app_metadata import ReleaseMetadata

SEMVER_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
INSTALLER_ASSET_RE = re.compile(r"^ForzaTelemetryTrackerSetup-v\d+\.\d+\.\d+-x64\.exe$", re.IGNORECASE)
CHECKSUM_ASSET_RE = re.compile(r"\.(sha256|sha256sum|sha256\.txt|txt)$", re.IGNORECASE)
DEFAULT_CACHE_TTL_SECONDS = 15 * 60
GITHUB_API_ROOT = "https://api.github.com"


class UpdateError(RuntimeError):
    """Base class for update failures that are safe to show to the user."""


@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str | None) -> "SemVer | None":
        if value is None:
            return None
        match = SEMVER_TAG_RE.match(str(value).strip())
        if not match:
            return None
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    api_url: str
    browser_download_url: str | None = None
    size: int | None = None


@dataclass(frozen=True)
class ReleaseCandidate:
    version: SemVer
    tag_name: str
    html_url: str | None
    published_at: str | None
    installer: ReleaseAsset
    checksum: ReleaseAsset

    @property
    def version_text(self) -> str:
        return str(self.version)


@dataclass
class UpdateCheckResult:
    status: str
    current_version: str
    latest_version: str | None = None
    release_url: str | None = None
    published_at: str | None = None
    asset_name: str | None = None
    message: str = ""
    candidate: ReleaseCandidate | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "release_url": self.release_url,
            "published_at": self.published_at,
            "asset_name": self.asset_name,
            "message": self.message,
        }


def _asset_from_github(payload: dict[str, Any]) -> ReleaseAsset:
    return ReleaseAsset(
        name=str(payload.get("name") or ""),
        api_url=str(payload.get("url") or ""),
        browser_download_url=payload.get("browser_download_url"),
        size=int(payload["size"]) if payload.get("size") is not None else None,
    )


def release_candidate_from_github(payload: dict[str, Any]) -> ReleaseCandidate | None:
    if payload.get("draft") or payload.get("prerelease"):
        return None
    tag_name = str(payload.get("tag_name") or "")
    version = SemVer.parse(tag_name)
    if version is None:
        return None
    assets = [_asset_from_github(asset) for asset in payload.get("assets") or [] if isinstance(asset, dict)]
    installer = next((asset for asset in assets if INSTALLER_ASSET_RE.match(asset.name)), None)
    checksum = next(
        (
            asset
            for asset in assets
            if asset.name.lower().startswith("forzatelemetrytrackersetup-")
            and CHECKSUM_ASSET_RE.search(asset.name)
        ),
        None,
    )
    if installer is None or checksum is None:
        return None
    return ReleaseCandidate(
        version=version,
        tag_name=tag_name,
        html_url=payload.get("html_url"),
        published_at=payload.get("published_at"),
        installer=installer,
        checksum=checksum,
    )


def select_latest_stable_release(
    releases: list[dict[str, Any]],
    current_version: str,
) -> tuple[SemVer | None, ReleaseCandidate | None]:
    current = SemVer.parse(current_version)
    if current is None:
        return None, None
    candidates = [
        candidate
        for release in releases
        if isinstance(release, dict)
        for candidate in [release_candidate_from_github(release)]
        if candidate is not None and candidate.version > current
    ]
    if not candidates:
        return current, None
    return current, max(candidates, key=lambda candidate: candidate.version)


class GitHubReleaseClient:
    """Small public GitHub Releases API client."""

    def __init__(self, repository: str, *, api_root: str = GITHUB_API_ROOT) -> None:
        self.repository = repository.strip().strip("/")
        self.api_root = api_root.rstrip("/")

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        return {
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Forza-Telemetry-Tracker",
        }

    def list_releases(self) -> list[dict[str, Any]]:
        url = f"{self.api_root}/repos/{self.repository}/releases?per_page=100"
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url, headers=self._headers())
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise UpdateError("GitHub releases response was not a list")
            return payload


class UpdateService:
    def __init__(
        self,
        *,
        metadata: ReleaseMetadata,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        client_factory: Callable[[str], GitHubReleaseClient] | None = None,
    ) -> None:
        self.metadata = metadata
        self.cache_ttl_seconds = cache_ttl_seconds
        self.client_factory = client_factory or (lambda repository: GitHubReleaseClient(repository))
        self._cached_at = 0.0
        self._cached_result: UpdateCheckResult | None = None

    def about_update_payload(self) -> dict[str, Any]:
        return {
            "supported": self.update_check_supported(),
            "release_access": "public",
        }

    def update_check_supported(self) -> bool:
        return bool(self.metadata.repository and SemVer.parse(self.metadata.version) and self.metadata.stable_channel)

    def _client(self) -> GitHubReleaseClient:
        return self.client_factory(self.metadata.repository)

    def check_for_updates(self, *, force: bool = False) -> UpdateCheckResult:
        now = time.monotonic()
        if (
            not force
            and self._cached_result is not None
            and now - self._cached_at < self.cache_ttl_seconds
        ):
            return self._cached_result
        if not self.update_check_supported():
            result = UpdateCheckResult(
                status="unsupported",
                current_version=self.metadata.version,
                latest_version=None,
                message="Update checks are only available for stable SemVer desktop builds.",
            )
            self._cache(result)
            return result
        try:
            releases = self._client().list_releases()
            current, candidate = select_latest_stable_release(releases, self.metadata.version)
            if current is None:
                result = UpdateCheckResult(
                    status="unsupported",
                    current_version=self.metadata.version,
                    message="Installed version is not a stable SemVer version.",
                )
            elif candidate is None:
                result = UpdateCheckResult(
                    status="up_to_date",
                    current_version=str(current),
                    latest_version=str(current),
                    message="You're up to date.",
                )
            else:
                result = UpdateCheckResult(
                    status="update_available",
                    current_version=str(current),
                    latest_version=candidate.version_text,
                    release_url=candidate.html_url,
                    published_at=candidate.published_at,
                    asset_name=candidate.installer.name,
                    message=f"Update {candidate.version_text} is available.",
                    candidate=candidate,
                )
        except httpx.HTTPStatusError as exc:
            message = f"GitHub release check failed with HTTP {exc.response.status_code}."
            if exc.response.status_code in {401, 403, 404}:
                message += " Confirm the configured release repository is public and reachable."
            result = UpdateCheckResult(
                status="error",
                current_version=self.metadata.version,
                latest_version=None,
                message=message,
            )
        except Exception as exc:
            result = UpdateCheckResult(
                status="error",
                current_version=self.metadata.version,
                latest_version=None,
                message=f"GitHub release check failed: {exc}",
            )
        self._cache(result)
        return result

    def _cache(self, result: UpdateCheckResult) -> None:
        self._cached_result = result
        self._cached_at = time.monotonic()
