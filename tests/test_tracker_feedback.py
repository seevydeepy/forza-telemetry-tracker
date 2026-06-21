import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from telemetry_tracker.app_metadata import ReleaseMetadata
from telemetry_tracker.app_paths import default_desktop_paths
from telemetry_tracker.feedback import (
    DIAGNOSTICS_DESCRIPTION,
    FEEDBACK_CATEGORIES,
    MAX_DESCRIPTION_LENGTH,
    MAX_DIAGNOSTICS_LOG_CHARS,
    FeedbackRequest,
    FeedbackService,
    FeedbackValidationError,
    build_feedback_report,
    generate_report_ref,
    get_or_create_reporter_id,
    sanitize_log_text,
)
from telemetry_tracker.storage import TelemetryStore


def _store(tmp: str | Path) -> TelemetryStore:
    store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
    store.migrate()
    return store


def _client_factory(handler):
    transport = httpx.MockTransport(handler)
    return lambda: httpx.AsyncClient(transport=transport)


class FeedbackBuilderTests(unittest.TestCase):
    def test_generate_report_ref_uses_forza_pattern(self):
        self.assertRegex(generate_report_ref(), r"^FTT-[A-Z2-7]{8}$")

    def test_get_or_create_reporter_id_is_stable_guid(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)

            first = get_or_create_reporter_id(store)
            second = get_or_create_reporter_id(store)

            self.assertEqual(first, second)
            self.assertRegex(
                first,
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            )

    def test_diagnostics_off_excludes_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)

            payload = build_feedback_report(
                store=store,
                category="Bug",
                description="Something broke",
                include_diagnostics=False,
                report_ref="FTT-ABC234DE",
                reporter_id="11111111-2222-4333-8444-555555555555",
                source="desktop-app",
            )

            self.assertNotIn("diagnostics", payload)
            self.assertEqual(payload["include_diagnostics"], False)

    def test_diagnostics_on_includes_allowlisted_snapshot_and_sanitized_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            paths = default_desktop_paths(
                resource_base=Path(tmp) / "resources",
                user_data_base=Path(tmp) / "app-data",
            )
            paths.ensure_user_directories()
            store.update_world_map_settings(
                media_root=r"C:\Users\Alice\Games\ForzaHorizon6\media",
                enabled=True,
                season="winter",
            )
            (paths.logs_dir / "app.log").write_text(
                "\n".join(
                    [
                        "Authorization: Bearer abc.def.ghi",
                        "api_key=sk_test_123456",
                        "password: hunter2",
                        "email player@example.com",
                        "connect 203.0.113.77 and 2001:db8::1",
                        r"load C:\Users\Alice\AppData\Local\Forza Telemetry Tracker\logs\app.log",
                    ]
                ),
                encoding="utf-8",
            )

            payload = build_feedback_report(
                store=store,
                category="Performance",
                description="Review got slow with a large session",
                include_diagnostics=True,
                report_ref="FTT-ABC234DE",
                reporter_id="11111111-2222-4333-8444-555555555555",
                source="desktop-app",
                release_metadata=ReleaseMetadata(version="1.2.3", git_sha="abcdef1234567890", channel="dev"),
                runtime_paths=paths,
                listener_status={"state": "waiting"},
                capture_status={"mode": "auto"},
            )

            diagnostics = payload["diagnostics"]
            self.assertEqual(diagnostics["app_version"], "1.2.3")
            self.assertIn("row_counts", diagnostics)
            self.assertIn("database_size_bytes", diagnostics)
            self.assertIn("wal_size_bytes", diagnostics)
            self.assertEqual(diagnostics["listener_status"], {"state": "waiting"})
            self.assertEqual(diagnostics["capture_status"], {"mode": "auto"})
            self.assertEqual(
                diagnostics["world_map"]["settings"]["fh6_media_root"],
                "[redacted local path]",
            )

            serialized = json.dumps(diagnostics)
            for sensitive in (
                "abc.def.ghi",
                "sk_test_123456",
                "hunter2",
                "player@example.com",
                "203.0.113.77",
                "2001:db8::1",
                r"C:\Users\Alice",
            ):
                self.assertNotIn(sensitive, serialized)
            self.assertIn("[redacted token]", diagnostics["recent_log"])
            self.assertIn("[redacted secret]", diagnostics["recent_log"])
            self.assertIn("[redacted email]", diagnostics["recent_log"])
            self.assertLessEqual(len(diagnostics["recent_log"]), MAX_DIAGNOSTICS_LOG_CHARS)

    def test_redaction_caps_recent_log_text(self):
        text = "x" * (MAX_DIAGNOSTICS_LOG_CHARS + 500)

        redacted = sanitize_log_text(text)

        self.assertEqual(len(redacted), MAX_DIAGNOSTICS_LOG_CHARS)

    def test_local_validation_rejects_short_and_long_descriptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            kwargs = {
                "store": store,
                "category": "Bug",
                "include_diagnostics": False,
                "report_ref": "FTT-ABC234DE",
                "reporter_id": "11111111-2222-4333-8444-555555555555",
                "source": "desktop-app",
            }

            with self.assertRaises(FeedbackValidationError):
                build_feedback_report(description="  a ", **kwargs)
            with self.assertRaises(FeedbackValidationError):
                build_feedback_report(description="x" * (MAX_DESCRIPTION_LENGTH + 1), **kwargs)
            with self.assertRaises(FeedbackValidationError):
                build_feedback_report(description="Valid text", category="Crash", **{k: v for k, v in kwargs.items() if k != "category"})


class FeedbackServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_config_defaults_diagnostics_on_with_privacy_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            service = FeedbackService(store=store, endpoint=None)

            config = await service.config()

            self.assertEqual(config["diagnostics_default"], True)
            self.assertEqual(config["diagnostics_description"], DIAGNOSTICS_DESCRIPTION)

    async def test_submit_without_endpoint_queues_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            service = FeedbackService(store=store, endpoint=None)

            result = await service.submit(
                FeedbackRequest(category="Other", description="I have a small suggestion")
            )

            self.assertEqual(result["status"], "queued")
            self.assertRegex(result["report_ref"], r"^FTT-[A-Z2-7]{8}$")
            with store.connect() as con:
                queued = con.execute("SELECT COUNT(*) FROM feedback_outbox").fetchone()[0]
            self.assertEqual(queued, 1)

    async def test_submit_retries_generated_report_ref_on_local_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            store.enqueue_feedback_report("FTT-AAAA2222", "{}", 1000, 1000)
            service = FeedbackService(store=store, endpoint=None)

            with patch(
                "telemetry_tracker.feedback.generate_report_ref",
                side_effect=["FTT-AAAA2222", "FTT-BBBB2222"],
            ):
                result = await service.submit(
                    FeedbackRequest(category="Other", description="Collision retry please")
                )

            self.assertEqual(result["report_ref"], "FTT-BBBB2222")

    async def test_submit_success_posts_to_worker_and_returns_issue(self):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "report_ref": "FTT-ABC234DE",
                    "issue_number": 101,
                    "issue_url": "https://github.com/seevydeepy/forza-telemetry-feedback/issues/101",
                },
            )

        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            service = FeedbackService(
                store=store,
                endpoint="https://feedback.example/v1/reports",
                client_factory=_client_factory(handler),
            )

            with patch("telemetry_tracker.feedback.generate_report_ref", return_value="FTT-ABC234DE"):
                result = await service.submit(
                    FeedbackRequest(category="Bug", description="Dashboard failed to load")
                )

            self.assertEqual(result["status"], "sent")
            self.assertEqual(result["issue_number"], 101)
            self.assertEqual(len(requests), 1)
            posted = json.loads(requests[0].content)
            self.assertEqual(posted["report_ref"], "FTT-ABC234DE")
            self.assertIn(posted["category"], FEEDBACK_CATEGORIES)

    async def test_retryable_worker_failure_queues_report(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "temporary failure"})

        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            service = FeedbackService(
                store=store,
                endpoint="https://feedback.example/v1/reports",
                client_factory=_client_factory(handler),
            )

            with patch("telemetry_tracker.feedback.generate_report_ref", return_value="FTT-ABC234DE"):
                result = await service.submit(
                    FeedbackRequest(category="Bug", description="Dashboard failed to load")
                )

            self.assertEqual(result["status"], "queued")
            with store.connect() as con:
                row = con.execute("SELECT report_ref, status FROM feedback_outbox").fetchone()
            self.assertEqual(tuple(row), ("FTT-ABC234DE", "pending"))

    async def test_worker_validation_rejection_does_not_queue_report(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"error": "invalid report"})

        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            service = FeedbackService(
                store=store,
                endpoint="https://feedback.example/v1/reports",
                client_factory=_client_factory(handler),
            )

            with patch("telemetry_tracker.feedback.generate_report_ref", return_value="FTT-ABC234DE"):
                result = await service.submit(
                    FeedbackRequest(category="Bug", description="Dashboard failed to load")
                )

            self.assertEqual(result["status"], "rejected")
            with store.connect() as con:
                queued = con.execute("SELECT COUNT(*) FROM feedback_outbox").fetchone()[0]
            self.assertEqual(queued, 0)

    async def test_retry_pending_marks_sent(self):
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "report_ref": payload["report_ref"],
                    "issue_number": 101,
                    "issue_url": "https://github.com/seevydeepy/forza-telemetry-feedback/issues/101",
                },
            )

        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            payload = {
                "schema_version": 1,
                "report_ref": "FTT-ABC234DE",
                "reporter_id": "11111111-2222-4333-8444-555555555555",
                "category": "Other",
                "description": "Retry this queued feedback",
            }
            store.enqueue_feedback_report("FTT-ABC234DE", json.dumps(payload), 1000, 1000)
            service = FeedbackService(
                store=store,
                endpoint="https://feedback.example/v1/reports",
                client_factory=_client_factory(handler),
            )

            result = await service.retry_pending(limit=5)

            self.assertEqual(result["attempted"], 1)
            self.assertEqual(result["sent"], 1)
            with store.connect() as con:
                row = con.execute(
                    "SELECT status, issue_number FROM feedback_outbox WHERE report_ref = ?",
                    ("FTT-ABC234DE",),
                ).fetchone()
            self.assertEqual(tuple(row), ("sent", 101))


if __name__ == "__main__":
    unittest.main()
