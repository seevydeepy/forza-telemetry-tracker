# Feedback Worker

## Purpose

Cloudflare Worker backend and runbook for user-initiated anonymous feedback reports. It accepts `POST /v1/reports`, validates the Forza report schema, enforces D1-backed idempotency and rate limits, and creates private GitHub triage issues through a dedicated GitHub App.

## Owned Paths

- tools/feedback_worker/
- docs/feedback_reporting_setup.md
- docs/feedback_reporting_design_handoff.md

## Entrypoints

- `tools/feedback_worker/src/index.ts`: Worker fetch handler, `GET /health`, `POST /v1/reports`, body size checks, report state transitions, HMAC reporter/IP hashes, fixed-window rate limits, and D1 idempotency.
- `tools/feedback_worker/src/schema.ts`: accepted report categories, `FTT-[A-Z2-7]{8}` report refs, GUID reporter IDs, description limits, diagnostics log cap, and timestamp validation.
- `tools/feedback_worker/src/githubApp.ts`: GitHub App JWT/token exchange, exact report-ref search, private issue creation, category labels, label fallback, and issue-body redaction.
- `tools/feedback_worker/src/rateLimit.ts`: D1 fixed-window counter update.
- `tools/feedback_worker/migrations/0001_feedback_state.sql`: `reports` and `rate_limits` tables.
- `tools/feedback_worker/wrangler.toml`: Worker name, D1 binding, GitHub repo vars, body and rate-limit defaults.
- `tools/feedback_worker/test/worker.test.ts`: executable coverage for schema rejection, idempotency, failed-row retry, rate limits, label fallback, JWT key formats, and redaction.

## Neighbouring Systems

- Desktop Backend builds and submits reports through local FastAPI; the Svelte UI should not call Cloudflare directly.
- Desktop Backend also owns diagnostics collection, sanitisation before submission, and the local retry outbox when the endpoint is unavailable.
- Web Dashboard owns the Send Feedback modal, category selection, opt-out diagnostics toggle, and sent/queued/error toast flow.
- Release CI Packaging controls when packaged builds receive the production `https://forza-telemetry-feedback.cvdp.workers.dev/v1/reports` endpoint.
- The private `seevydeepy/forza-telemetry-feedback` repository is the triage target. User feedback must not be filed in the public tracker repository.

## Maintenance Notes

- Keep Worker changes paired with `npm test` and `npm run typecheck` from `tools/feedback_worker`.
- Keep deployment and privacy claims aligned with `docs/feedback_reporting_setup.md`; do not document unprovisioned buckets, attachments, screenshots, or telemetry uploads.
- Treat raw IPs, reporter UUIDs, credentials, local user paths, emails, and tokens as privacy-sensitive. The Worker should only persist HMAC-derived identifiers and redacted issue text.
