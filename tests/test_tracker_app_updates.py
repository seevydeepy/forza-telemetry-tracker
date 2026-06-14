import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from telemetry_tracker.app_metadata import (
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
from telemetry_tracker.github_token_store import GitHubTokenStore, TokenStatus


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
                ),
            )
            with patch.dict(
                "os.environ",
                {
                    ENV_VERSION: "1.0.1",
                    ENV_RELEASE_REPOSITORY: "override/repo",
                    ENV_UPDATE_CHANNEL: "stable",
                },
                clear=False,
            ):
                metadata = load_release_metadata(path)

        self.assertEqual(metadata.version, "1.0.1")
        self.assertEqual(metadata.release_date, "2026-06-13")
        self.assertEqual(metadata.repository, "override/repo")

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


class FakeTokenStore(GitHubTokenStore):
    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def read_token(self) -> str | None:
        return self.token

    def status(self) -> TokenStatus:
        return TokenStatus(configured=bool(self.token), source="credential_manager" if self.token else None)

    def save_token(self, token: str) -> TokenStatus:
        self.token = token
        return self.status()

    def clear_token(self) -> TokenStatus:
        self.token = None
        return self.status()


class FakeGitHubClient:
    def __init__(self, releases: list[dict]) -> None:
        self.releases = releases

    def list_releases(self) -> list[dict]:
        return self.releases


class AppUpdateServiceTests(unittest.TestCase):
    def test_update_check_reports_unsupported_for_dev_channel(self):
        service = UpdateService(
            metadata=ReleaseMetadata(version="1.0.0", channel="dev", repository="owner/repo"),
            token_store=FakeTokenStore(),
        )

        result = service.check_for_updates(force=True)

        self.assertEqual(result.status, "unsupported")

    def test_update_check_caches_github_result(self):
        client = FakeGitHubClient([_release("v1.1.0")])
        factory = Mock(return_value=client)
        service = UpdateService(
            metadata=ReleaseMetadata(version="1.0.0", channel="stable", repository="owner/repo"),
            token_store=FakeTokenStore("token"),
            client_factory=factory,
            cache_ttl_seconds=60,
        )

        first = service.check_for_updates(force=True)
        second = service.check_for_updates(force=False)

        self.assertEqual(first.status, "update_available")
        self.assertEqual(second.latest_version, "1.1.0")
        self.assertEqual(factory.call_count, 1)

    def test_token_status_redacts_token_value(self):
        service = UpdateService(
            metadata=ReleaseMetadata(version="1.0.0", channel="stable", repository="owner/repo"),
            token_store=FakeTokenStore("secret-token"),
        )

        payload = service.token_status_payload()

        self.assertEqual(
            payload,
            {
                "token_configured": True,
                "token_source": "credential_manager",
                "token_storage_available": True,
            },
        )
        self.assertNotIn("secret-token", repr(payload))


if __name__ == "__main__":
    unittest.main()
