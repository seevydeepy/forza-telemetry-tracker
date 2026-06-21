import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

from telemetry_tracker.app_metadata import (
    ENV_FEEDBACK_ENDPOINT,
    ENV_RELEASE_REPOSITORY,
    ENV_UPDATE_CHANNEL,
    ENV_VERSION,
    ReleaseMetadata,
    load_release_metadata,
    write_release_metadata,
)
from telemetry_tracker.app_updates import (
    SemVer,
    UpdateService,
    release_candidate_from_github,
    select_latest_stable_release,
)


def _release(
    tag: str,
    *,
    draft: bool = False,
    prerelease: bool = False,
    asset_prefix: str | None = None,
) -> dict:
    prefix = asset_prefix or f"ForzaTelemetryTrackerSetup-{tag}-x64.exe"
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "html_url": f"https://github.example/releases/{tag}",
        "published_at": "2026-06-13T12:00:00Z",
        "assets": [
            {
                "name": prefix,
                "url": f"https://api.github.example/assets/{tag}/installer",
                "browser_download_url": f"https://github.example/assets/{prefix}",
                "size": 123,
            },
            {
                "name": f"{prefix}.sha256",
                "url": f"https://api.github.example/assets/{tag}/sha256",
                "size": 64,
            },
        ],
    }


class AppUpdateSemVerTests(unittest.TestCase):
    def test_release_metadata_loads_packaged_file_with_environment_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-metadata.json"
            write_release_metadata(
                path,
                ReleaseMetadata(
                    version="1.0.0",
                    release_date="2026-06-13",
                    git_sha="abc123",
                    repository="owner/repo",
                    channel="stable",
                    feedback_endpoint="https://old.example/v1/reports",
                ),
            )
            with patch.dict(
                "os.environ",
                {
                    ENV_VERSION: "1.0.1",
                    ENV_RELEASE_REPOSITORY: "override/repo",
                    ENV_UPDATE_CHANNEL: "stable",
                    ENV_FEEDBACK_ENDPOINT: "https://feedback.example/v1/reports",
                },
                clear=False,
            ):
                metadata = load_release_metadata(path)

        self.assertEqual(metadata.version, "1.0.1")
        self.assertEqual(metadata.release_date, "2026-06-13")
        self.assertEqual(metadata.repository, "override/repo")
        self.assertEqual(metadata.feedback_endpoint, "https://feedback.example/v1/reports")

    def test_release_metadata_loads_file_with_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-metadata.json"
            path.write_bytes(
                b'\xef\xbb\xbf{"version":"0.1.4","channel":"stable","repository":"owner/repo","feedback_endpoint":"https://feedback.example/v1/reports"}'
            )

            metadata = load_release_metadata(path)

        self.assertEqual(metadata.version, "0.1.4")
        self.assertEqual(metadata.channel, "stable")
        self.assertEqual(metadata.repository, "owner/repo")
        self.assertEqual(metadata.feedback_endpoint, "https://feedback.example/v1/reports")

    def test_semver_parser_accepts_stable_tags_only(self):
        self.assertEqual(SemVer.parse("v1.2.3"), SemVer(1, 2, 3))
        self.assertEqual(SemVer.parse("1.2.3"), SemVer(1, 2, 3))
        self.assertIsNone(SemVer.parse("v1.2.3-beta.1"))
        self.assertIsNone(SemVer.parse("not-a-version"))

    def test_release_candidate_ignores_drafts_prereleases_and_missing_assets(self):
        self.assertIsNone(release_candidate_from_github(_release("v1.2.3", draft=True)))
        self.assertIsNone(release_candidate_from_github(_release("v1.2.3", prerelease=True)))
        self.assertIsNone(release_candidate_from_github({**_release("v1.2.3"), "assets": []}))
        self.assertIsNotNone(release_candidate_from_github(_release("v1.2.3")))

    def test_select_latest_stable_release_compares_versions_not_publish_dates(self):
        older_published_late = {
            **_release("v1.1.0"),
            "published_at": "2026-06-14T12:00:00Z",
        }
        newer_published_early = {
            **_release("v1.2.0"),
            "published_at": "2026-06-13T12:00:00Z",
        }

        current, candidate = select_latest_stable_release(
            [older_published_late, newer_published_early, _release("v2.0.0", prerelease=True)],
            "1.0.0",
        )

        self.assertEqual(current, SemVer(1, 0, 0))
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.version, SemVer(1, 2, 0))

    def test_select_latest_stable_release_returns_none_when_up_to_date(self):
        current, candidate = select_latest_stable_release([_release("v1.0.0")], "1.0.0")
        self.assertEqual(current, SemVer(1, 0, 0))
        self.assertIsNone(candidate)


class FakeGitHubClient:
    def __init__(self, releases: list[dict]) -> None:
        self.releases = releases

    def list_releases(self) -> list[dict]:
        return self.releases


class FailingGitHubClient:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def list_releases(self) -> list[dict]:
        request = httpx.Request("GET", "https://api.github.example/repos/owner/repo/releases")
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError("release check failed", request=request, response=response)


class AppUpdateServiceTests(unittest.TestCase):
    def test_update_check_reports_unsupported_for_dev_channel(self):
        service = UpdateService(
            metadata=ReleaseMetadata(version="1.0.0", channel="dev", repository="owner/repo"),
        )

        result = service.check_for_updates(force=True)

        self.assertEqual(result.status, "unsupported")

    def test_update_check_caches_github_result(self):
        client = FakeGitHubClient([_release("v1.1.0")])
        factory = Mock(return_value=client)
        service = UpdateService(
            metadata=ReleaseMetadata(version="1.0.0", channel="stable", repository="owner/repo"),
            client_factory=factory,
            cache_ttl_seconds=60,
        )

        first = service.check_for_updates(force=True)
        second = service.check_for_updates(force=False)

        self.assertEqual(first.status, "update_available")
        self.assertEqual(second.latest_version, "1.1.0")
        self.assertEqual(factory.call_count, 1)
        factory.assert_called_once_with("owner/repo")

    def test_about_update_payload_reports_public_release_access(self):
        service = UpdateService(
            metadata=ReleaseMetadata(version="1.0.0", channel="stable", repository="owner/repo"),
        )

        payload = service.about_update_payload()

        self.assertEqual(
            payload,
            {
                "supported": True,
                "release_access": "public",
            },
        )

    def test_update_check_error_mentions_public_repository_not_token_setup(self):
        service = UpdateService(
            metadata=ReleaseMetadata(version="1.0.0", channel="stable", repository="owner/repo"),
            client_factory=lambda repository: FailingGitHubClient(404),
        )

        result = service.check_for_updates(force=True)

        self.assertEqual(result.status, "error")
        self.assertIn("public and reachable", result.message)
        self.assertNotIn("token", result.message.lower())


if __name__ == "__main__":
    unittest.main()
