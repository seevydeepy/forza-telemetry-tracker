# Feedback Worker OKF Log

## Bootstrap

- Shallow OKF bundle created from repository structure.

## Deep Backfill

- Backfilled stable purpose, entrypoints, routing terms, and handoffs from the checked-in Worker scaffold and feedback docs.
- `tools/feedback_worker/src/index.ts` shows the active Worker endpoints: `GET /health` and `POST /v1/reports`. It handles body-size checks, schema validation, HMAC reporter/IP hashes, D1 report rows, fixed-window rate limits, idempotent duplicate handling, failed-row retry, GitHub issue creation, and JSON responses.
- `tools/feedback_worker/src/schema.ts` defines the accepted categories, `FTT-[A-Z2-7]{8}` report refs, GUID reporter IDs, description bounds, diagnostics log cap, and timestamp parsing.
- `tools/feedback_worker/src/githubApp.ts` shows the GitHub App integration, PKCS#1/PKCS#8 private-key support, installation token exchange, exact report-ref search, issue creation, label fallback, and redaction of reporter IDs, IPs, secrets, emails, and local user paths before issue text is written.
- `tools/feedback_worker/src/rateLimit.ts` and `tools/feedback_worker/migrations/0001_feedback_state.sql` show the D1-backed `reports` and `rate_limits` persistence model.
- `tools/feedback_worker/wrangler.toml` names the Worker `forza-telemetry-feedback`, binds `FEEDBACK_DB`, targets private repo `seevydeepy/forza-telemetry-feedback`, and sets default body and hourly rate limits.
- `tools/feedback_worker/test/worker.test.ts` covers health, invalid JSON/schema, size limits, idempotency, duplicate reporter mismatch, concurrent duplicate refs, failed state retry, reporter/IP rate limits, label fallback, JWT key formats, and redaction.
- `docs/feedback_reporting_setup.md` is the deployment and operations runbook: provision private triage repo, GitHub App, Cloudflare D1, Worker secrets, smoke checks, endpoint activation, rollback, privacy checks, local Worker development, and validation commands.
- `docs/feedback_reporting_design_handoff.md` documents the cross-system design: Svelte modal to local FastAPI, Python diagnostics/outbox, Cloudflare Worker, D1 state, GitHub App, and private GitHub issues.

## Known Gaps

- Live Cloudflare deployment and GitHub App installation state are operational facts, not proven by this backfill. Use the smoke checks in `docs/feedback_reporting_setup.md` before claiming production readiness.
- The Worker bundle only covers the Cloudflare/GitHub side. Client UI, local FastAPI feedback endpoints, diagnostics collection, and retry outbox belong to neighbouring solution areas.
