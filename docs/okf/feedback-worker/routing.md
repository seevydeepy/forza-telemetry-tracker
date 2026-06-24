# Feedback Worker Routing

## Read This When

- A change touches one of this solution's owned paths.
- A symptom matches one of this solution's routing keywords.

## First Files To Inspect

- `docs/okf/feedback-worker/routing_guidance.card`
- `docs/okf/feedback-worker/solution.md`
- `tools/feedback_worker/src/index.ts`
- `tools/feedback_worker/src/schema.ts`
- `tools/feedback_worker/src/githubApp.ts`

## Owned Paths

- tools/feedback_worker/
- docs/feedback_reporting_setup.md
- docs/feedback_reporting_design_handoff.md

## Symptoms And Search Terms

- cloudflare
- worker
- d1
- github app
- github issue
- feedback report
- report_ref
- FTT-
- rate limit
- hmac
- redaction
- private triage
- anonymous feedback

## Symptom Routing

- Worker returns `400`, `413`, `422`, `429`, `503`, or `202`: start in `tools/feedback_worker/src/index.ts`, then inspect `src/schema.ts` for validation failures or `src/rateLimit.ts` for quota behaviour.
- Duplicate or missing private issues for a report ref: inspect `readReport`, `reconcileExistingGitHubIssue`, `insertCreatingReport`, `claimFailedReport`, and `markCreated` in `tools/feedback_worker/src/index.ts`, then `findExistingGitHubIssue` in `src/githubApp.ts`.
- GitHub authentication, private key, installation token, or label fallback failures: inspect `tools/feedback_worker/src/githubApp.ts` and the setup values documented in `docs/feedback_reporting_setup.md`.
- Sensitive text, raw IPs, reporter IDs, local usernames, emails, or secrets appear in a GitHub issue: inspect `scrubSensitiveText`, `redactRawIdentifiers`, `sanitizeStructuredValue`, and `buildIssueBody` in `tools/feedback_worker/src/githubApp.ts`.
- Bad category, report-ref format, reporter ID, timestamp, description length, or diagnostics size: inspect `tools/feedback_worker/src/schema.ts`.
- D1 migration, binding, Worker name, deployed URL, or limit defaults look wrong: inspect `tools/feedback_worker/wrangler.toml`, `tools/feedback_worker/migrations/0001_feedback_state.sql`, and `docs/feedback_reporting_setup.md`.
- Production endpoint should be enabled or disabled in packaged/local builds: route to Desktop Backend and Release CI Packaging after reading the Client Endpoint Activation and Rollback sections in `docs/feedback_reporting_setup.md`.

## Handoffs

- Desktop Backend: local `/api/feedback/config`, `/api/feedback/reports`, diagnostics sanitisation, SQLite retry outbox, and endpoint activation/rollback.
- Web Dashboard: Send Feedback modal, category dropdown, diagnostics toggle, and progress/success/queued/error toasts.
- Release CI Packaging: release metadata and build workflow arguments that set the production feedback endpoint.
- Project Docs: README, PRIVACY, SUPPORT, and operator-facing feedback setup disclosure.
