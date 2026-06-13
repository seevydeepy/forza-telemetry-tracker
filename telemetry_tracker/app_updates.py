"""GitHub Releases update checking and installation helpers."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from telemetry_tracker.app_metadata import ReleaseMetadata
from telemetry_tracker.github_token_store import GitHubTokenStore, TokenStatus

SEMVER_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
INSTALLER_ASSET_RE = re.compile(r"^ForzaTelemetryTrackerSetup-v\d+\.\d+\.\d+-x64\.exe$", re.IGNORECASE)
CHECKSUM_ASSET_RE = re.compile(r"\.(sha256|sha256sum|sha256\.txt|txt)$", re.IGNORECASE)
DEFAULT_CACHE_TTL_SECONDS = 15 * 60
GITHUB_API_ROOT = "https://api.github.com"
FORZA_APP_ACTION_HEADER = "X-Forza-App-Action"
FORZA_APP_ACTION_VALUE = "1"


class UpdateError(RuntimeError):
    """Base class for update failures that are safe to show to the user."""


class UpdateUnsupported(UpdateError):
    """Raised when self-update cannot run in the current process/build."""


class UpdateVerificationError(UpdateError):
    """Raised when a downloaded installer fails hash/signature checks."""


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


@dataclass(frozen=True)
class AuthenticodeResult:
    valid: bool
    status: str
    thumbprint: str | None = None
    subject: str | None = None
    message: str | None = None


def parse_checksum_text(text: str, expected_name: str | None = None) -> str:
    """Extract a SHA-256 digest from a checksum asset."""

    expected_lower = expected_name.lower() if expected_name else None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace("*", " ").split()
        digest = next((part for part in parts if re.fullmatch(r"[a-fA-F0-9]{64}", part)), None)
        if digest is None:
            continue
        if expected_lower is not None and len(parts) > 1:
            filenames = [Path(part).name.lower() for part in parts[1:]]
            if filenames and expected_lower not in filenames:
                continue
        return digest.lower()
    raise UpdateVerificationError("SHA-256 checksum file did not contain a matching digest")


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


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
    """Small GitHub Releases API client.

    Token values are used only in Authorization headers and never returned.
    """

    def __init__(self, repository: str, token: str | None = None, *, api_root: str = GITHUB_API_ROOT) -> None:
        self.repository = repository.strip().strip("/")
        self.token = token
        self.api_root = api_root.rstrip("/")

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        headers = {
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Forza-Telemetry-Tracker",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def list_releases(self) -> list[dict[str, Any]]:
        url = f"{self.api_root}/repos/{self.repository}/releases?per_page=100"
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url, headers=self._headers())
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise UpdateError("GitHub releases response was not a list")
            return payload

    def download_asset(self, asset: ReleaseAsset, destination: Path) -> Path:
        if not asset.api_url:
            raise UpdateError(f"release asset {asset.name!r} did not include an API URL")
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".part")
        with httpx.Client(timeout=None, follow_redirects=True) as client:
            with client.stream(
                "GET",
                asset.api_url,
                headers=self._headers("application/octet-stream"),
            ) as response:
                response.raise_for_status()
                with partial.open("wb") as target:
                    for chunk in response.iter_bytes():
                        if chunk:
                            target.write(chunk)
        if asset.size is not None and partial.stat().st_size != asset.size:
            downloaded_size = partial.stat().st_size
            partial.unlink(missing_ok=True)
            raise UpdateVerificationError(
                f"downloaded {asset.name} was incomplete ({downloaded_size} of {asset.size} bytes)"
            )
        partial.replace(destination)
        return destination

    def read_asset_text(self, asset: ReleaseAsset) -> str:
        if not asset.api_url:
            raise UpdateError(f"release asset {asset.name!r} did not include an API URL")
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(asset.api_url, headers=self._headers("application/octet-stream"))
            response.raise_for_status()
            return response.text


def verify_authenticode(installer_path: Path, trusted_thumbprints: list[str] | tuple[str, ...]) -> AuthenticodeResult:
    """Verify Authenticode status and signer certificate thumbprint allowlist."""

    allowed = {thumbprint.replace(" ", "").replace(":", "").upper() for thumbprint in trusted_thumbprints if thumbprint}
    if not allowed:
        raise UpdateVerificationError("No trusted signer certificate thumbprints are configured")
    if os.name != "nt":
        raise UpdateVerificationError("Authenticode verification is only supported on Windows")
    script = r"""
param([string]$Path)
$signature = Get-AuthenticodeSignature -LiteralPath $Path
$thumbprint = $null
$subject = $null
if ($signature.SignerCertificate -ne $null) {
  $thumbprint = $signature.SignerCertificate.GetCertHashString([System.Security.Cryptography.HashAlgorithmName]::SHA256)
  $subject = $signature.SignerCertificate.Subject
}
[pscustomobject]@{
  Status = [string]$signature.Status
  StatusMessage = [string]$signature.StatusMessage
  Thumbprint = $thumbprint
  Subject = $subject
} | ConvertTo-Json -Compress
"""
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script, "-Path", str(installer_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise UpdateVerificationError("Authenticode verification failed to run")
    try:
        payload = json.loads(completed.stdout.strip())
    except json.JSONDecodeError as exc:
        raise UpdateVerificationError("Authenticode verification returned invalid output") from exc
    thumbprint = str(payload.get("Thumbprint") or "").replace(" ", "").replace(":", "").upper() or None
    status = str(payload.get("Status") or "")
    result = AuthenticodeResult(
        valid=status == "Valid" and thumbprint in allowed,
        status=status,
        thumbprint=thumbprint,
        subject=payload.get("Subject"),
        message=payload.get("StatusMessage"),
    )
    if status != "Valid":
        raise UpdateVerificationError(f"Installer signature is not valid ({status})")
    if thumbprint not in allowed:
        raise UpdateVerificationError("Installer signer certificate is not trusted by this app version")
    return result


def _default_updater_helper_path() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent / "ForzaTelemetryTrackerUpdater.exe"


def launch_update_helper(
    *,
    installer_path: Path,
    updates_dir: Path,
    updater_helper_path: Path | None = None,
    app_executable: Path | None = None,
    wait_pid: int | None = None,
) -> subprocess.Popen:
    """Launch a temporary updater helper that survives app shutdown."""

    helper_source = Path(updater_helper_path) if updater_helper_path is not None else _default_updater_helper_path()
    if helper_source is None or not helper_source.is_file():
        raise UpdateUnsupported("Updater helper executable is missing from this installation")
    updates_dir = Path(updates_dir)
    updates_dir.mkdir(parents=True, exist_ok=True)
    helper_copy = updates_dir / f"ForzaTelemetryTrackerUpdater-{os.getpid()}.exe"
    shutil.copy2(helper_source, helper_copy)
    log_path = updates_dir / "update-helper.log"
    app_exe = Path(app_executable) if app_executable is not None else Path(sys.executable)
    args = [
        str(helper_copy),
        "--wait-pid",
        str(os.getpid() if wait_pid is None else wait_pid),
        "--installer",
        str(installer_path),
        "--app-exe",
        str(app_exe),
        "--log",
        str(log_path),
    ]
    popen_kwargs: dict[str, Any] = {"close_fds": True}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(args, **popen_kwargs)


class UpdateService:
    def __init__(
        self,
        *,
        metadata: ReleaseMetadata,
        updates_dir: Path,
        token_store: GitHubTokenStore | None = None,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        client_factory: Callable[[str, str | None], GitHubReleaseClient] | None = None,
        signature_verifier: Callable[[Path, tuple[str, ...]], AuthenticodeResult] = verify_authenticode,
        helper_launcher: Callable[..., subprocess.Popen] = launch_update_helper,
        updater_helper_path: Path | None = None,
    ) -> None:
        self.metadata = metadata
        self.updates_dir = Path(updates_dir)
        self.token_store = token_store or GitHubTokenStore()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.client_factory = client_factory or (lambda repository, token: GitHubReleaseClient(repository, token))
        self.signature_verifier = signature_verifier
        self.helper_launcher = helper_launcher
        self.updater_helper_path = updater_helper_path
        self._cached_at = 0.0
        self._cached_result: UpdateCheckResult | None = None

    def token_status_payload(self) -> dict[str, Any]:
        status = self.token_store.status()
        return {
            "token_configured": status.configured,
            "token_source": status.source,
            "token_storage_available": status.storage_available,
            "trusted_signer_configured": bool(self.metadata.trusted_signer_thumbprints),
        }

    def about_update_payload(self) -> dict[str, Any]:
        payload = self.token_status_payload()
        payload["supported"] = self.update_check_supported()
        return payload

    def update_check_supported(self) -> bool:
        return bool(self.metadata.repository and SemVer.parse(self.metadata.version) and self.metadata.stable_channel)

    def self_update_supported(self) -> bool:
        return bool(getattr(sys, "frozen", False) and self.update_check_supported())

    def _client(self) -> GitHubReleaseClient:
        return self.client_factory(self.metadata.repository, self.token_store.read_token())

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
            if not self.token_store.status().configured and exc.response.status_code in {401, 403, 404}:
                message += " Configure a repository-only GitHub token for private release testing."
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

    def save_token(self, token: str) -> TokenStatus:
        status = self.token_store.save_token(token)
        self._cached_result = None
        return status

    def clear_token(self) -> TokenStatus:
        status = self.token_store.clear_token()
        self._cached_result = None
        return status

    def install_update(self, *, version: str | None = None) -> dict[str, Any]:
        if not self.self_update_supported():
            raise UpdateUnsupported("Self-update is only available in installed stable desktop builds")
        result = self.check_for_updates(force=False)
        if result.status != "update_available" or result.candidate is None:
            raise UpdateError(result.message or "No update is available")
        candidate = result.candidate
        if version is not None and version.strip() and version.strip().lstrip("v") != candidate.version_text:
            raise UpdateError(f"Requested update {version} is not the latest available stable version")

        client = self._client()
        installer_path = self.updates_dir / candidate.installer.name
        checksum_text = client.read_asset_text(candidate.checksum)
        expected_hash = parse_checksum_text(checksum_text, candidate.installer.name)
        client.download_asset(candidate.installer, installer_path)
        actual_hash = sha256_file(installer_path)
        if actual_hash.lower() != expected_hash.lower():
            installer_path.unlink(missing_ok=True)
            raise UpdateVerificationError("Downloaded installer SHA-256 checksum did not match release checksum")
        self.signature_verifier(installer_path, self.metadata.trusted_signer_thumbprints)
        self.helper_launcher(
            installer_path=installer_path,
            updates_dir=self.updates_dir,
            updater_helper_path=self.updater_helper_path,
            app_executable=Path(sys.executable),
            wait_pid=os.getpid(),
        )
        return {
            "status": "installing",
            "message": "The update installer will run after the app closes.",
            "version": candidate.version_text,
        }
