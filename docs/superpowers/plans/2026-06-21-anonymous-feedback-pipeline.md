# Anonymous Feedback Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. For eligible non-work repositories, use enabled ask-mimo as the default fast read-only checkpoint for non-trivial plans, meaningful implementation diffs, debugging conclusions, and final outputs; subagents should use one focused end-of-task Ask MiMo check before returning non-trivial work. Use ask-claude only from the orchestrator when MiMo is unavailable or a deeper Claude consult is more appropriate. For `svn_master_*` work repositories, use Cursor delegation where work-repo guidance calls for it. Final implementation review should follow superpowers:requesting-code-review / Ask MiMo / Ask Claude policy. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current public GitHub Issues-facing feedback link with an in-app anonymous feedback flow that sends sanitized reports through a local FastAPI endpoint to a Forza-specific Cloudflare Worker, which creates issues in the private `seevydeepy/forza-telemetry-feedback` triage repository.

**Architecture:** The Svelte UI opens a local `Send Feedback` modal and posts only to local FastAPI. Python owns report construction, diagnostics allowlisting/redaction, reporter identity persistence, and a SQLite retry outbox in the existing `TelemetryStore` database. The Cloudflare Worker owns schema validation, request-size checks, HMAC-derived rate-limit keys, GitHub App authentication, idempotent issue creation, and the final private GitHub issue write.

**Tech Stack:** Python/FastAPI, SQLite, `httpx`, Svelte/Vite/Vitest, Cloudflare Workers/D1/Wrangler, GitHub App installation authentication, pytest.

---

## Implementation Notes

- Work in an isolated git worktree from the current integration branch.
- Keep `seevydeepy/forza-telemetry-tracker` public. Never create user feedback issues in that repo.
- Create and use the private `seevydeepy/forza-telemetry-feedback` repository for feedback issues.
- The user's raw public IP may exist only as transient Worker request input for rate limiting and redaction checks. Do not write raw IPs to GitHub issue titles, bodies, comments, D1 rows, durable logs, or API responses.
- Do not add client-side GitHub credentials, Worker secrets, Cloudflare credentials, `.dev.vars`, private keys, tokens, or generated Wrangler state to the repo.
- Keep diagnostics default off in the UI and backend.
- Configure the shipped Worker endpoint only after the Worker, D1 database, GitHub App, and private issue smoke check are complete.
- Treat the Worker endpoint as public internet input. Do not add a shared request-signing secret to the packaged desktop app; a client-shipped secret is extractable and would create false confidence. v1 abuse controls are request-size limits, schema validation, IP-derived rate limiting, advisory reporter-derived rate limiting, D1 idempotency, GitHub search-before-create, and private triage.
- `REPORT_HMAC_SECRET` is server-side Worker configuration used to HMAC `reporter_id` and request IP into durable rate-limit/idempotency keys and short reporter fingerprints. It is not a request signing key.

## File Structure

Create:
- `tools/feedback_worker/package.json`: Worker npm scripts and dev dependencies.
- `tools/feedback_worker/package-lock.json`: Locked Worker dependency graph from `npm install`.
- `tools/feedback_worker/tsconfig.json`: Worker TypeScript config.
- `tools/feedback_worker/vitest.config.ts`: Worker test config.
- `tools/feedback_worker/wrangler.toml`: Worker name, non-secret vars, and D1 binding.
- `tools/feedback_worker/migrations/0001_feedback_state.sql`: D1 tables for idempotency and rate limits.
- `tools/feedback_worker/src/index.ts`: Worker request routing, validation, D1 idempotency, rate limits, and GitHub issue orchestration.
- `tools/feedback_worker/src/schema.ts`: Forza report schema, categories, labels, and report ref validation.
- `tools/feedback_worker/src/githubApp.ts`: GitHub App JWT/token exchange, search-before-create, issue body formatting, and redaction.
- `tools/feedback_worker/src/rateLimit.ts`: Fixed-window D1 rate limit helper.
- `tools/feedback_worker/test/worker.test.ts`: Worker unit tests with mocked D1 and GitHub fetch.
- `telemetry_tracker/feedback.py`: Local report builder, diagnostics sanitizer, outbox, submit/retry service, and typed response helpers.
- `tests/test_tracker_feedback.py`: Backend unit tests for report refs, reporter IDs, diagnostics, redaction, queue rules, and retry.
- `web/telemetry-tracker/src/FeedbackModal.svelte`: In-app feedback modal.
- `web/telemetry-tracker/src/FeedbackModal.test.ts`: Modal unit tests.
- `docs/feedback_reporting_setup.md`: Provisioning and smoke-test runbook for the private repo, GitHub App, D1, Worker, and endpoint activation.

Modify:
- `telemetry_tracker/storage.py`: Add `feedback_state` and `feedback_outbox` tables, helper methods, and bump `SCHEMA_VERSION`.
- `tests/test_tracker_storage.py`: Assert new feedback tables, schema version, and outbox helper behavior.
- `telemetry_tracker/app.py`: Add feedback service setup plus `GET /api/feedback/config`, `POST /api/feedback/reports`, and `POST /api/feedback/retry-pending`.
- `telemetry_tracker/app_metadata.py`: Add optional feedback endpoint metadata and environment override.
- `tools/build-desktop-release.ps1`: Include feedback endpoint metadata when activating the shipped endpoint.
- `tests/test_tracker_app.py`: Assert feedback config/report/retry endpoint behavior.
- `web/telemetry-tracker/src/types.ts`: Add feedback request/response/config types and allow toast updates.
- `web/telemetry-tracker/src/api.ts`: Add feedback API helpers.
- `web/telemetry-tracker/src/App.svelte`: Add modal state, menu handling, feedback submit flow, and toast update helper.
- `web/telemetry-tracker/src/SlideOutMenu.svelte`: Replace external GitHub feedback link with a `Send Feedback` menu action.
- `web/telemetry-tracker/src/App.test.ts`: Assert menu, modal, API calls, and toast behavior.
- `README.md`: Document user-initiated feedback upload behavior.
- `PRIVACY.md`: Document network/privacy delta and diagnostics exclusions.
- `SUPPORT.md`: Prefer in-app feedback and keep public Issues guidance safe.

---

### Task 1: Worker Scaffold And Forza Schema

**Files:**
- Create: `tools/feedback_worker/package.json`
- Create: `tools/feedback_worker/tsconfig.json`
- Create: `tools/feedback_worker/vitest.config.ts`
- Create: `tools/feedback_worker/wrangler.toml`
- Create: `tools/feedback_worker/migrations/0001_feedback_state.sql`
- Create: `tools/feedback_worker/src/schema.ts`
- Create: `tools/feedback_worker/src/rateLimit.ts`
- Create: `tools/feedback_worker/src/index.ts`
- Create: `tools/feedback_worker/src/githubApp.ts`
- Create: `tools/feedback_worker/test/worker.test.ts`

- [ ] **Step 1: Copy the Mood Swings Worker scaffold**

Copy these files from `F:\code\git\thegame\tools\feedback_worker` into `tools/feedback_worker`:

```powershell
Copy-Item -Recurse F:\code\git\thegame\tools\feedback_worker tools\feedback_worker
Remove-Item -LiteralPath tools\feedback_worker\package-lock.json -ErrorAction SilentlyContinue
```

Do not copy `.dev.vars`, Wrangler local state, generated logs, or any secrets if they exist.

- [ ] **Step 2: Specialize Worker package and Wrangler config**

Set `tools/feedback_worker/package.json`:

```json
{
  "name": "forza-telemetry-feedback-worker",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "deploy": "wrangler deploy",
    "dev": "wrangler dev"
  },
  "devDependencies": {
    "@cloudflare/workers-types": "4.20260617.1",
    "typescript": "6.0.3",
    "vitest": "4.1.9",
    "wrangler": "4.103.0"
  }
}
```

Set `tools/feedback_worker/wrangler.toml` with a sentinel `database_id` that the runbook will replace after D1 creation:

```toml
name = "forza-telemetry-feedback"
main = "src/index.ts"
compatibility_date = "2026-06-17"
workers_dev = true
preview_urls = false

[vars]
GITHUB_OWNER = "seevydeepy"
GITHUB_REPO = "forza-telemetry-feedback"
MAX_BODY_BYTES = "65536"
REPORTER_LIMIT_PER_HOUR = "5"
IP_LIMIT_PER_HOUR = "20"

[[d1_databases]]
binding = "FEEDBACK_DB"
database_name = "forza-telemetry-feedback"
database_id = "00000000-0000-0000-0000-000000000000"
```

- [ ] **Step 3: Keep D1 idempotency and rate-limit tables explicit**

Keep `tools/feedback_worker/migrations/0001_feedback_state.sql` as:

```sql
CREATE TABLE IF NOT EXISTS reports (
  report_ref TEXT PRIMARY KEY,
  reporter_hash TEXT NOT NULL,
  ip_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  github_issue_number INTEGER,
  github_issue_url TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_reporter_hash ON reports (reporter_hash);
CREATE INDEX IF NOT EXISTS idx_reports_ip_hash ON reports (ip_hash);

CREATE TABLE IF NOT EXISTS rate_limits (
  key TEXT PRIMARY KEY,
  window_start INTEGER NOT NULL,
  count INTEGER NOT NULL
);
```

`reports.report_ref` is the Worker idempotency key. GitHub search-before-create remains a second reconciliation check for cases where GitHub issue creation succeeds but the D1 `created` update fails.

- [ ] **Step 4: Update Worker schema**

In `tools/feedback_worker/src/schema.ts`, replace Mood Swings categories and report refs with Forza values:

```ts
export const categoryLabels = {
  Bug: "type:bug",
  "Data Out setup": "area:data-out",
  "Telemetry recording": "area:capture",
  "Map or route visualisation": "area:map-route",
  "Import or export": "area:import-export",
  Performance: "area:performance",
  "UI or UX": "area:ui",
  Other: "type:feedback"
} as const;

const reportRefPattern = /^FTT-[A-Z2-7]{8}$/;
```

Keep the v1 report shape, description range `3-4000`, GUID `reporter_id`, optional diagnostics, and `diagnostics.recent_log` cap of 16000 characters. If `client_timestamp_utc` is present, require it to parse as a finite timestamp; reject malformed timestamps with schema validation details.

- [ ] **Step 5: Update GitHub issue helper defaults**

In `tools/feedback_worker/src/githubApp.ts`:

- Set `userAgent = "forza-telemetry-feedback-worker"`.
- Keep PKCS#1 and PKCS#8 private key support.
- Keep GitHub search-before-create.
- Keep label fallback: if issue creation returns a GitHub validation error for labels, retry without labels.
- Ensure `buildIssueBody()` never includes raw `reporter_id` or raw `CF-Connecting-IP`.
- Keep `reporterFingerprint` as the short hash shown in issue bodies.

The issue body should include:

~~~md
## Report
- Report ref: FTT-ABCDEFGH
- Category: Bug
- Source: desktop-app
- Scene: dashboard
- Reporter fingerprint: <first 12 hash chars>
- Client timestamp (UTC): 2026-06-21T12:00:00.000000Z

## Description
<redacted user text>

## Build
```json
{}
```

## Platform
```json
{}
```

## Settings
```json
{}
```

## Diagnostics
```json
{}
```

## Recent Log
```text
<redacted and capped log text>
```
~~~

- [ ] **Step 6: Update Worker tests before running them**

In `tools/feedback_worker/test/worker.test.ts`, change sample data and assertions:

- `GET /health` returns `{ ok: true }`
- body-size rejection returns HTTP 413 before schema processing
- report refs use `FTT-ABC234DE`
- invalid report ref test expects `^FTT-[A-Z2-7]{8}$`
- malformed `client_timestamp_utc` returns HTTP 422
- categories use the Forza set
- mocked GitHub issue URL uses `https://github.com/seevydeepy/forza-telemetry-feedback/issues/101`
- issue creation URL is `/repos/seevydeepy/forza-telemetry-feedback/issues`
- duplicate and concurrent submissions for the same `report_ref` create only one GitHub issue
- privacy test asserts issue title/body do not contain the raw reporter GUID or raw IP
- diagnostics scrub test includes:
  - `Authorization: Bearer abc.def.ghi`
  - `api_key=sk_test_123456`
  - `password: hunter2`
  - `player@example.com`
  - `203.0.113.77`
  - `2001:db8::1`
  - `C:\Users\Alice\AppData\Local\Forza Telemetry Tracker\logs\app.log`
  - `env_TOKEN=abc123`

- [ ] **Step 7: Install and validate Worker package**

Run:

```powershell
npm --prefix tools\feedback_worker install
npm --prefix tools\feedback_worker test
npm --prefix tools\feedback_worker run typecheck
```

Expected: package lock is created, Worker tests pass, and TypeScript typecheck succeeds.

- [ ] **Step 8: Commit Worker scaffold**

```powershell
git add tools\feedback_worker
git commit -m "Add Forza feedback Worker scaffold"
```

---

### Task 2: Local Feedback Storage And Report Builder

**Files:**
- Modify: `telemetry_tracker/storage.py`
- Create: `telemetry_tracker/feedback.py`
- Modify: `tests/test_tracker_storage.py`
- Create: `tests/test_tracker_feedback.py`

- [ ] **Step 1: Write storage tests for feedback tables**

Add tests to `tests/test_tracker_storage.py` that assert:

- `SCHEMA_VERSION == 12`
- `feedback_state` exists
- `feedback_outbox` exists
- `feedback_outbox.report_ref` is the primary key
- indexes exist for `status`, `next_attempt_at_ms`, and `updated_at_ms`
- running `store.migrate()` twice leaves one migration row for each version

Expected table shape:

```sql
CREATE TABLE IF NOT EXISTS feedback_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback_outbox (
  report_ref TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  next_attempt_at_ms INTEGER NOT NULL,
  issue_number INTEGER,
  issue_url TEXT
);

CREATE INDEX IF NOT EXISTS idx_feedback_outbox_pending
ON feedback_outbox(status, next_attempt_at_ms);

CREATE INDEX IF NOT EXISTS idx_feedback_outbox_updated
ON feedback_outbox(updated_at_ms);
```

- [ ] **Step 2: Run storage tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_tracker_storage.py::TelemetryStoreTests::test_migrate_configures_wal_and_seeds_local_identity -q
```

Expected before implementation: failure because `SCHEMA_VERSION` is still 11 or feedback tables are missing.

- [ ] **Step 3: Implement storage migration and helpers**

In `telemetry_tracker/storage.py`:

- change `SCHEMA_VERSION = 12`
- add `_apply_feedback_migrations(con)` near other idempotent additive migrations
- call it from `migrate()` before inserting `schema_migrations`

Add helper methods:

```python
def feedback_state_value(self, key: str) -> str | None: ...
def set_feedback_state_value(self, key: str, value: str) -> None: ...
def enqueue_feedback_report(self, report_ref: str, payload_json: str, now_ms: int, next_attempt_at_ms: int) -> None: ...
def mark_feedback_report_sent(self, report_ref: str, issue_number: int | None, issue_url: str | None, now_ms: int) -> None: ...
def mark_feedback_report_failed(self, report_ref: str, error: str, now_ms: int, next_attempt_at_ms: int) -> None: ...
def pending_feedback_reports(self, now_ms: int, limit: int = 5) -> list[dict]: ...
def prune_feedback_outbox(self, now_ms: int, max_pending: int = 25, ttl_ms: int = 30 * 24 * 60 * 60 * 1000) -> None: ...
```

Store helper return values as dictionaries, matching existing storage methods that expose rows to app services.

`prune_feedback_outbox()` should drop unsent rows older than 30 days, sent rows older than 30 days, and oldest pending rows beyond the 25-row cap. Do not let sent rows accumulate without bound.

- [ ] **Step 4: Write feedback builder tests**

In `tests/test_tracker_feedback.py`, cover:

- `generate_report_ref()` returns `FTT-[A-Z2-7]{8}`
- `get_or_create_reporter_id(store)` returns a stable GUID across calls
- diagnostics off excludes `diagnostics`
- diagnostics on includes app version, platform, listener/capture state, row counts, sizes, and sanitized log tails
- feedback diagnostics removes or replaces `world_map.settings.fh6_media_root`
- redaction masks usernames, emails, IPv4, IPv6, bearer tokens, and secret-looking key/value fields
- redaction caps combined recent log text at 16 KB
- local validation rejects descriptions shorter than 3 characters and longer than 4000
- report ref generation retries if a generated ref already exists in local feedback storage

- [ ] **Step 5: Implement `telemetry_tracker/feedback.py`**

Create constants:

```python
FEEDBACK_CATEGORIES = (
    "Bug",
    "Data Out setup",
    "Telemetry recording",
    "Map or route visualisation",
    "Import or export",
    "Performance",
    "UI or UX",
    "Other",
)
MAX_DESCRIPTION_LENGTH = 4000
MAX_DIAGNOSTICS_LOG_CHARS = 16_000
REPORT_REF_PREFIX = "FTT-"
REPORTER_ID_KEY = "feedback_reporter_id"
```

Create functions/classes:

```python
def generate_report_ref() -> str: ...
def get_or_create_reporter_id(store: TelemetryStore) -> str: ...
def sanitize_log_text(text: str) -> str: ...
def build_feedback_diagnostics(..., include_logs: bool) -> dict: ...
def build_feedback_report(..., include_diagnostics: bool) -> dict: ...

class FeedbackValidationError(ValueError): ...
class RetryableFeedbackError(RuntimeError): ...
class RejectedFeedbackError(RuntimeError): ...
class FeedbackService:
    async def config(self) -> dict: ...
    async def submit(self, request: FeedbackRequest) -> dict: ...
    async def retry_pending(self, limit: int = 5) -> dict: ...
```

Use `base64.b32encode(os.urandom(5)).decode("ascii")` for the eight-character suffix. Use `uuid.uuid4()` for the stable reporter ID. Before accepting a generated ref, check local `feedback_outbox` for an existing row and regenerate on collision.

- [ ] **Step 6: Implement local submit and queue rules**

`FeedbackService.submit()` should:

1. validate category and trimmed description
2. build the report payload
3. if no endpoint is configured, enqueue and return:

```python
{"status": "queued", "report_ref": report_ref, "message": "Feedback saved. We'll send it when you're back online."}
```

4. POST to the Worker with `httpx.AsyncClient(timeout=10.0)`
5. on Worker success, mark sent and return:

```python
{"status": "sent", "report_ref": report_ref, "issue_number": 101, "issue_url": "https://github.com/seevydeepy/forza-telemetry-feedback/issues/101"}
```

6. on retryable network errors, HTTP `408`, `425`, `429`, or `5xx`, enqueue and return `status = "queued"`
7. on local validation errors or Worker HTTP `400`, `413`, `422`, return `status = "rejected"` and do not queue

The Worker `REPORTER_LIMIT_PER_HOUR` rate limit is advisory because a motivated caller can rotate the client-controlled `reporter_id`. Keep the IP-derived limit as the primary v1 abuse control.

- [ ] **Step 7: Run backend feedback/storage tests**

Run:

```powershell
python -m pytest tests/test_tracker_feedback.py tests/test_tracker_storage.py -q
```

Expected: selected tests pass.

- [ ] **Step 8: Commit backend storage and builder**

```powershell
git add telemetry_tracker\storage.py telemetry_tracker\feedback.py tests\test_tracker_storage.py tests\test_tracker_feedback.py
git commit -m "Add local feedback report builder and outbox"
```

---

### Task 3: FastAPI Feedback Endpoints

**Files:**
- Modify: `telemetry_tracker/app.py`
- Modify: `telemetry_tracker/app_metadata.py`
- Modify: `tools/build-desktop-release.ps1`
- Modify: `tests/test_tracker_app.py`

- [ ] **Step 1: Write endpoint tests**

In `tests/test_tracker_app.py`, add tests that:

- `GET /api/feedback/config` returns:

```json
{
  "enabled": true,
  "categories": ["Bug", "Data Out setup", "Telemetry recording", "Map or route visualisation", "Import or export", "Performance", "UI or UX", "Other"],
  "max_description_length": 4000,
  "diagnostics_default": false,
  "diagnostics_description": "Diagnostics may include app version, platform, listener/capture status, local database/log sizes, row counts, and recent sanitized app log lines. It does not include raw telemetry packets, session databases, map cache files, game files, screenshots, exports, or personal files."
}
```

- `POST /api/feedback/reports` passes category, description, include diagnostics, and source to the service
- sent responses preserve `status`, `report_ref`, `issue_number`, and `issue_url`
- queued responses return HTTP 202 with `status = "queued"`
- rejected responses return HTTP 422 with `status = "rejected"`
- `POST /api/feedback/retry-pending` returns retry counts
- config endpoint exposure is intentionally local-only and contains no secrets

- [ ] **Step 2: Add endpoint request models**

In `telemetry_tracker/app.py`, add Pydantic models near other request models:

```python
class FeedbackReportRequest(BaseModel):
    category: str
    description: str
    include_diagnostics: bool = False
    source: str | None = None

class FeedbackRetryRequest(BaseModel):
    limit: int = 5
```

- [ ] **Step 3: Add feedback endpoint metadata**

In `telemetry_tracker/app_metadata.py`, add:

```python
ENV_FEEDBACK_ENDPOINT = "FORZA_TRACKER_FEEDBACK_ENDPOINT"
```

Add `feedback_endpoint: str | None = None` to `ReleaseMetadata`, read it from `release-metadata.json` and env overrides, and write it from `write_release_metadata()`.

In `tools/build-desktop-release.ps1`, add an optional parameter:

```powershell
[string]$FeedbackEndpoint = ""
```

Write `feedback_endpoint = $FeedbackEndpoint` only when it is non-empty. The release command should pass the deployed `/v1/reports` endpoint only after smoke checks pass.

- [ ] **Step 4: Wire `FeedbackService` in `create_app()`**

In `create_app()`, instantiate the service after `release_metadata` and `runtime_paths` are available:

```python
feedback_service = FeedbackService(
    store=store,
    endpoint_url=release_metadata.feedback_endpoint,
    runtime_paths=runtime_paths,
    release_metadata=release_metadata,
    listener_status=listener.status,
    capture_status=capture.status,
)
app.state.feedback_service = feedback_service
```

Use `runtime_paths or default_desktop_paths()` inside the service when reading logs.

- [ ] **Step 5: Add FastAPI routes**

Add routes near `/api/diagnostics`:

```python
@app.get("/api/feedback/config")
async def feedback_config() -> dict:
    return app.state.feedback_service.config()

@app.post("/api/feedback/reports")
async def create_feedback_report(request: FeedbackReportRequest) -> dict:
    result = await app.state.feedback_service.submit(request)
    if result["status"] == "queued":
        return JSONResponse(result, status_code=202)
    if result["status"] == "rejected":
        raise HTTPException(status_code=422, detail=result["message"])
    return result

@app.post("/api/feedback/retry-pending")
async def retry_pending_feedback(request: FeedbackRetryRequest | None = None) -> dict:
    limit = request.limit if request is not None else 5
    return await app.state.feedback_service.retry_pending(limit=limit)
```

Import `JSONResponse` from `fastapi.responses`.

Do not add auth to these local FastAPI endpoints in v1. The desktop backend is already a local app surface, and the feedback config contains only categories, limits, and disclosure copy.

- [ ] **Step 6: Run endpoint tests**

Run:

```powershell
python -m pytest tests/test_tracker_app.py::TrackerAppTests -q
```

Expected: selected app tests pass.

- [ ] **Step 7: Commit FastAPI endpoints**

```powershell
git add telemetry_tracker\app.py telemetry_tracker\app_metadata.py tools\build-desktop-release.ps1 tests\test_tracker_app.py
git commit -m "Add local feedback API endpoints"
```

---

### Task 4: Frontend Types, API, And Modal

**Files:**
- Modify: `web/telemetry-tracker/src/types.ts`
- Modify: `web/telemetry-tracker/src/api.ts`
- Create: `web/telemetry-tracker/src/FeedbackModal.svelte`
- Create: `web/telemetry-tracker/src/FeedbackModal.test.ts`

- [ ] **Step 1: Add frontend feedback types**

In `types.ts`, add:

```ts
export type FeedbackCategory =
  | 'Bug'
  | 'Data Out setup'
  | 'Telemetry recording'
  | 'Map or route visualisation'
  | 'Import or export'
  | 'Performance'
  | 'UI or UX'
  | 'Other';

export interface FeedbackConfig {
  enabled: boolean;
  categories: FeedbackCategory[];
  max_description_length: number;
  diagnostics_default: boolean;
  diagnostics_description: string;
}

export interface FeedbackReportInput {
  category: FeedbackCategory;
  description: string;
  include_diagnostics: boolean;
  source?: string;
}

export interface FeedbackReportResponse {
  status: 'sent' | 'queued' | 'rejected';
  report_ref: string;
  issue_number?: number | null;
  issue_url?: string | null;
  message?: string;
}
```

- [ ] **Step 2: Add API helpers**

In `api.ts`, add imports and helpers:

```ts
export async function fetchFeedbackConfig(): Promise<FeedbackConfig> {
  const response = await fetch('/api/feedback/config');
  return expectJson<FeedbackConfig>(response, 'Feedback config request failed');
}

export async function sendFeedbackReport(input: FeedbackReportInput): Promise<FeedbackReportResponse> {
  const response = await fetch('/api/feedback/reports', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
  return expectJson<FeedbackReportResponse>(response, 'Feedback request failed');
}
```

Keep all frontend calls local; do not call the Worker URL from Svelte.

- [ ] **Step 3: Write modal tests**

In `FeedbackModal.test.ts`, assert:

- dialog name is `Send Feedback`
- categories are rendered from config
- diagnostics toggle defaults off
- diagnostics disclosure text is visible
- description placeholder changes for at least `Bug`, `Data Out setup`, and `Other`
- Send is disabled until the trimmed description has at least 3 characters
- dispatches `submit` with `{ category, description, include_diagnostics, source: 'desktop-app' }`
- shows no inline sending status text

- [ ] **Step 4: Implement `FeedbackModal.svelte`**

Use `AppModal` as the shell. Fields:

- category `<select>`
- description `<textarea>`
- diagnostics checkbox/toggle, default from `config.diagnostics_default` but expected false
- Send button
- close handled by `AppModal`

Use placeholders:

```ts
const placeholders: Record<string, string> = {
  Bug: 'What went wrong, and what were you doing just before it happened?',
  'Data Out setup': 'What step of the Forza Data Out setup is confusing or failing?',
  'Telemetry recording': 'What happened while recording or reviewing telemetry?',
  'Map or route visualisation': 'What looks wrong on the map or route visualisation?',
  'Import or export': 'What file or workflow did you try to import or export?',
  Performance: 'What felt slow, and roughly how large was the session?',
  'UI or UX': 'What was hard to find, read, or use?',
  Other: 'What would you like to tell us?'
};
```

No inline progress message belongs in the modal; progress uses toasts in `App.svelte`.

- [ ] **Step 5: Run modal tests**

Run:

```powershell
npm --prefix web\telemetry-tracker test -- --run src/FeedbackModal.test.ts
```

Expected: modal tests pass.

- [ ] **Step 6: Commit frontend modal**

```powershell
git add web\telemetry-tracker\src\types.ts web\telemetry-tracker\src\api.ts web\telemetry-tracker\src\FeedbackModal.svelte web\telemetry-tracker\src\FeedbackModal.test.ts
git commit -m "Add feedback modal and API helpers"
```

---

### Task 5: Frontend App/Menu/Toast Integration

**Files:**
- Modify: `web/telemetry-tracker/src/App.svelte`
- Modify: `web/telemetry-tracker/src/SlideOutMenu.svelte`
- Modify: `web/telemetry-tracker/src/types.ts`
- Modify: `web/telemetry-tracker/src/App.test.ts`

- [ ] **Step 1: Update App tests**

In `App.test.ts`, update the fixture fetch mock to handle:

```ts
if (pathname === '/api/feedback/config') return jsonResponse(defaultFeedbackConfig);
if (pathname === '/api/feedback/reports' && init?.method === 'POST') return jsonResponse({
  status: 'sent',
  report_ref: 'FTT-ABC234DE',
  issue_number: 101,
  issue_url: 'https://github.com/seevydeepy/forza-telemetry-feedback/issues/101'
});
```

Add tests for:

- collapsed/expanded menu exposes `Send Feedback` as a button, not an external link
- clicking the menu action opens the modal
- sending starts one `Sending feedback...` toast
- sent updates the same toast to `Feedback sent. Ref: FTT-ABC234DE`
- queued updates the same toast to `Feedback saved. We'll send it when you're back online. Ref: FTT-ABC234DE`
- error keeps the modal open and updates the same toast to an error
- sent/queued closes the modal

- [ ] **Step 2: Replace external feedback link with menu action**

In `SlideOutMenu.svelte`:

- remove `FEEDBACK_URL`
- add `send-feedback` to `MenuAction`
- add a menu item with `icon: 'feedback'`, `label: 'Send Feedback'`, `title: 'Send feedback'`, `text: 'Send Feedback'`
- remove the footer `<a>` that opens public GitHub Issues

This keeps feedback inside the app and avoids sending users to public issues.

- [ ] **Step 3: Add toast update capability**

In `App.svelte`, keep `ToastStack.svelte` unchanged and add:

```ts
function updateToast(id: number, level: ToastMessage['level'], message: string, sticky = false) {
  lastStatusEvent = message;
  toasts = toasts.map((toast) => (toast.id === id ? { ...toast, level, message, sticky } : toast));
  if (!sticky) {
    window.setTimeout(() => {
      toasts = toasts.filter((item) => item.id !== id);
    }, 4000);
  }
}
```

Use this for the feedback flow so one toast changes level/message instead of creating stacked status messages.

- [ ] **Step 4: Wire modal state and submit handler**

In `App.svelte`:

- import `FeedbackModal`
- import `fetchFeedbackConfig` and `sendFeedbackReport`
- add `feedback` to `UtilityModal`
- add `feedbackConfig`, `feedbackConfigLoading`, and `feedbackSubmitting` state
- load feedback config when opening the modal
- add `case 'send-feedback': openUtilityModal('feedback'); void loadFeedbackConfig(); break;`
- render `<FeedbackModal ... />` when `activeUtilityModal === 'feedback'`

Submit handler:

```ts
async function handleSendFeedback(event: CustomEvent<FeedbackReportInput>) {
  feedbackSubmitting = true;
  const toast = pushToast('info', 'Sending feedback...', true);
  try {
    const response = await sendFeedbackReport(event.detail);
    if (response.status === 'sent') {
      updateToast(toast.id, 'success', `Feedback sent. Ref: ${response.report_ref}`);
      closeUtilityModal();
    } else if (response.status === 'queued') {
      updateToast(toast.id, 'warning', `Feedback saved. We'll send it when you're back online. Ref: ${response.report_ref}`, true);
      closeUtilityModal();
    } else {
      updateToast(toast.id, 'error', response.message ?? 'Feedback could not be sent.', true);
    }
  } catch (error) {
    updateToast(toast.id, 'error', error instanceof Error ? error.message : 'Feedback could not be sent.', true);
  } finally {
    feedbackSubmitting = false;
  }
}
```

- [ ] **Step 5: Run focused frontend tests**

Run:

```powershell
npm --prefix web\telemetry-tracker test -- --run src/App.test.ts src/FeedbackModal.test.ts
```

Expected: focused frontend tests pass.

- [ ] **Step 6: Build frontend**

Run:

```powershell
npm --prefix web\telemetry-tracker run build
```

Expected: Vite build succeeds.

- [ ] **Step 7: Commit frontend integration**

```powershell
git add web\telemetry-tracker\src\App.svelte web\telemetry-tracker\src\SlideOutMenu.svelte web\telemetry-tracker\src\types.ts web\telemetry-tracker\src\App.test.ts
git commit -m "Wire in-app feedback flow"
```

---

### Task 6: Documentation And Provisioning Runbook

**Files:**
- Modify: `README.md`
- Modify: `PRIVACY.md`
- Modify: `SUPPORT.md`
- Create: `docs/feedback_reporting_setup.md`

- [ ] **Step 1: Update README privacy bullets**

Replace the old absolute "no upload path" wording with:

```md
- There is no analytics or automatic telemetry upload path.
- The app sends feedback only when you choose `Send Feedback`.
- Feedback reports include your description, category, and optional diagnostics. Diagnostics default off.
- Feedback reports are sent to the Forza feedback Worker, which creates private triage issues for maintainers.
```

Keep the local-first wording for telemetry sessions, map cache, and game files.

- [ ] **Step 2: Update PRIVACY.md**

Add a `User-initiated feedback` section:

```md
## User-initiated feedback

The `Send Feedback` action sends a report only after you submit the in-app form. The report includes the category and description you entered. Diagnostics are optional and default off.

Optional diagnostics may include app version, platform, listener/capture status, local database/log sizes, row counts, and recent sanitized app log lines. They do not include raw telemetry packets, session databases, map cache files, game files, screenshots, exports, personal files, GitHub credentials, or Cloudflare credentials.

The feedback service receives your network request through Cloudflare. The Worker uses request IP only transiently for rate limiting and anti-abuse. The raw IP is not written to GitHub issues, D1 rows, durable logs, or API responses.

Queued reports may retry later after you already attempted to send them. Unsent reports expire after 30 days.
```

- [ ] **Step 3: Update SUPPORT.md**

Change "Use GitHub Issues" to prefer in-app feedback:

```md
Use `Send Feedback` from the app menu for ordinary bugs, setup problems, and feature feedback. It does not require a GitHub account.

Public GitHub Issues remain available for public project discussion, but do not include telemetry databases, local game files, generated map-cache files, credentials, private keys, raw logs, or personal data there.
```

- [ ] **Step 4: Create the provisioning runbook**

Create `docs/feedback_reporting_setup.md` with these sections:

- Production shape
- Create private triage repo
- GitHub App requirements
- Cloudflare provisioning
- Secrets
- Smoke checks
- Client endpoint activation
- Local development only
- Rollback

Include these commands:

```powershell
gh repo create seevydeepy/forza-telemetry-feedback --private --description "Private feedback triage for Forza Telemetry Tracker"
cd F:\code\git\forza-telemetry-tracker\tools\feedback_worker
npm install
npx wrangler login
npx wrangler whoami
npx wrangler d1 create forza-telemetry-feedback --binding FEEDBACK_DB
npx wrangler d1 migrations apply forza-telemetry-feedback --remote
npx wrangler secret put GITHUB_APP_ID
npx wrangler secret put GITHUB_INSTALLATION_ID
npx wrangler secret put GITHUB_PRIVATE_KEY_PEM
npx wrangler secret put REPORT_HMAC_SECRET
npx wrangler deploy
```

The manual smoke report must use `FTT-[A-Z2-7]{8}`, the private repo, and assert no raw IP or sensitive data appears in the issue body.

- [ ] **Step 5: Commit docs**

```powershell
git add README.md PRIVACY.md SUPPORT.md docs\feedback_reporting_setup.md
git commit -m "Document anonymous feedback reporting"
```

---

### Task 7: Provision Cloud Services And Activate Endpoint

**Files:**
- Modify after smoke: `tools/feedback_worker/wrangler.toml`
- Modify after smoke: `tools/build-desktop-release.ps1` invocation or release metadata generation path
- Optional modify after smoke: `docs/feedback_reporting_setup.md` with real Worker URL and D1 ID if the repo convention accepts checked-in D1 IDs

- [ ] **Step 1: Verify current official docs before provisioning**

Open and verify the current official docs linked from `docs/feedback_reporting_design_handoff.md`:

- Cloudflare Workers secrets
- Cloudflare D1 migrations
- Cloudflare Workers best practices
- GitHub App installation authentication
- GitHub App permissions

If GitHub's recommended API version or Cloudflare Wrangler syntax differs from the ported scaffold, update the Worker and runbook before provisioning.

- [ ] **Step 2: Create private triage repo**

Run:

```powershell
gh repo create seevydeepy/forza-telemetry-feedback --private --description "Private feedback triage for Forza Telemetry Tracker"
```

Add a minimal README in that private repo explaining that issues are generated by the Worker and should not be made public.

- [ ] **Step 3: Create and install GitHub App**

Create a dedicated GitHub App named `Forza Telemetry Feedback`:

- install only on `seevydeepy/forza-telemetry-feedback`
- permissions:
  - Metadata: read-only
  - Issues: read/write

Record only these values for Cloudflare secrets:

- `GITHUB_APP_ID`
- `GITHUB_INSTALLATION_ID`
- `GITHUB_PRIVATE_KEY_PEM`
- `REPORT_HMAC_SECRET`

Do not commit these values.

- [ ] **Step 4: Create D1 and update Wrangler config**

Run:

```powershell
cd F:\code\git\forza-telemetry-tracker\tools\feedback_worker
npx wrangler d1 create forza-telemetry-feedback --binding FEEDBACK_DB
```

Replace the sentinel `database_id` in `wrangler.toml` with the returned UUID.

- [ ] **Step 5: Apply migrations and secrets**

Run:

```powershell
npx wrangler d1 migrations apply forza-telemetry-feedback --remote
npx wrangler secret put GITHUB_APP_ID
npx wrangler secret put GITHUB_INSTALLATION_ID
npx wrangler secret put GITHUB_PRIVATE_KEY_PEM
npx wrangler secret put REPORT_HMAC_SECRET
```

Use an interactive terminal so secret values are not stored in shell history.

- [ ] **Step 6: Deploy and smoke test**

Run:

```powershell
npx wrangler deploy
$workerBaseUrl = "https://forza-telemetry-feedback.<cloudflare-subdomain>.workers.dev"
Invoke-RestMethod -Method Get -Uri "$workerBaseUrl/health"
```

Submit a manual report:

```powershell
$body = @{
  schema_version = 1
  report_ref = "FTT-ABC234DE"
  reporter_id = "00000000-0000-4000-8000-000000000001"
  category = "Other"
  description = "Manual deployment smoke test; close this private issue after verification."
  source = "operator-smoke"
  scene = "runbook"
  include_diagnostics = $true
  build = @{ display_version = "operator-smoke"; build_identifier = "manual"; build_channel = "manual"; git_short_sha = "manual"; metadata_source = "manual" }
  platform = @{ os_name = "operator"; locale = "en" }
  settings = @{}
  diagnostics = @{ recent_log = "Authorization: Bearer fake-token`nemail smoke@example.com`nconnect 203.0.113.77" }
  client_timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json -Depth 8

Invoke-RestMethod -Method Post -Uri "$workerBaseUrl/v1/reports" -ContentType "application/json" -Body $body
```

Expected:

- response has `ok = true`
- issue is created in private `seevydeepy/forza-telemetry-feedback`
- issue body does not contain `fake-token`, `smoke@example.com`, `203.0.113.77`, the raw reporter GUID, or any raw client IP

- [ ] **Step 7: Activate the shipped endpoint**

After smoke passes, set release metadata to the full endpoint:

```text
https://forza-telemetry-feedback.<cloudflare-subdomain>.workers.dev/v1/reports
```

If using the build script parameter, the release build command should include:

```powershell
-FeedbackEndpoint "https://forza-telemetry-feedback.<cloudflare-subdomain>.workers.dev/v1/reports"
```

Run an app-level smoke test that `GET /api/feedback/config` returns `enabled = true` in the packaged build.

- [ ] **Step 8: Commit deployable config updates**

Commit only non-secret config, runbook, and metadata changes:

```powershell
git add tools\feedback_worker\wrangler.toml docs\feedback_reporting_setup.md tools\build-desktop-release.ps1
git commit -m "Activate Forza feedback Worker endpoint"
```

---

### Task 8: Final Validation, Review, And Merge

**Files:**
- Review all changed files.

- [ ] **Step 1: Run backend validation**

Run:

```powershell
python -m pytest tests/test_tracker_feedback.py tests/test_tracker_app.py tests/test_tracker_diagnostics.py tests/test_tracker_storage.py -q
```

Expected: all selected backend tests pass.

- [ ] **Step 2: Run full backend test suite**

Run:

```powershell
python -m pytest
```

Expected: full pytest suite passes.

- [ ] **Step 3: Run frontend validation**

Run:

```powershell
npm --prefix web\telemetry-tracker test
npm --prefix web\telemetry-tracker run build
```

Expected: Vitest suite and Vite build pass.

- [ ] **Step 4: Run Worker validation**

Run:

```powershell
npm --prefix tools\feedback_worker test
npm --prefix tools\feedback_worker run typecheck
```

Expected: Worker tests and TypeScript typecheck pass.

- [ ] **Step 5: Manual privacy inspection**

Inspect one generated private issue from the Worker smoke test and verify:

- no raw public IP
- no raw reporter GUID
- no Windows username
- no email address
- no bearer token
- no key/value secret
- no raw telemetry packet
- no `telemetry_tracker.sqlite3`
- no FH6 install root path
- no map cache file path
- no screenshot or export path

- [ ] **Step 6: Ask MiMo for final diff review if enabled**

Send MiMo a compact packet containing:

- implementation summary
- changed-file list
- relevant privacy/redaction snippets
- test command results
- smoke-test issue privacy checklist

Ask for missed privacy leaks, retry/idempotency gaps, and validation blindspots. Apply only verified feedback.

- [ ] **Step 7: Request final code review**

Use `superpowers:requesting-code-review` or the local `requesting-code-review` skill. Focus the review on:

- no raw IP persistence
- no client-side secrets
- no public tracker issue creation
- outbox retry correctness
- diagnostics allowlist
- frontend toast/modal behavior
- provisioning docs reproducibility

- [ ] **Step 8: Merge and clean up**

After review is resolved:

```powershell
git status --short
git checkout master
git merge --ff-only <implementation-branch>
git worktree remove <implementation-worktree>
```

Do not push unless explicitly asked.

---

## Self-Review Checklist

- Spec coverage:
  - Worker/D1/GitHub App/private repo path: Task 1 and Task 7.
  - Public tracker remains public and does not receive feedback issues: Task 1, Task 6, Task 7.
  - Raw IP only transient for rate limits: Task 1, Task 7, Task 8.
  - Local FastAPI only from frontend: Task 3, Task 4, Task 5.
  - SQLite outbox, retry limits, TTL: Task 2.
  - Diagnostics default off, allowlisted, redacted, capped: Task 2, Task 4, Task 8.
  - Toast progress/update UX: Task 5.
  - README/PRIVACY/SUPPORT/runbook: Task 6.
  - Validation commands: Task 8.
- Placeholder scan:
  - No task uses placeholder markers or asks the implementer to invent unspecified behavior.
  - Live endpoint remains deliberately gated behind smoke checks.
- Type consistency:
  - Backend response status values are `sent`, `queued`, and `rejected`.
  - Frontend response types use the same status values.
  - Worker response remains `{ ok, report_ref, issue_number, issue_url }` for cloud success.
