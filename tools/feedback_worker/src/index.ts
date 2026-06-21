import { createGitHubIssue, findExistingGitHubIssue, GitHubAppEnv } from "./githubApp";
import { incrementFixedWindow } from "./rateLimit";
import { validateFeedbackReport, FeedbackReport } from "./schema";

export interface Env extends GitHubAppEnv {
  FEEDBACK_DB: D1Database;
  REPORT_HMAC_SECRET: string;
  MAX_BODY_BYTES?: string;
  REPORTER_LIMIT_PER_HOUR?: string;
  IP_LIMIT_PER_HOUR?: string;
}

interface ReportRow {
  report_ref: string;
  reporter_hash: string;
  ip_hash: string;
  status: "creating" | "created" | "failed";
  github_issue_number: number | null;
  github_issue_url: string | null;
  created_at: number;
  updated_at: number;
}

const oneHourSeconds = 60 * 60;
const defaultMaxBodyBytes = 65_536;
const defaultReporterLimit = 5;
const defaultIpLimit = 20;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" }
  });
}

function parsePositiveInteger(value: string | undefined, fallback: number): number {
  if (!value) {
    return fallback;
  }

  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function resultChanges(result: D1Result<unknown>): number {
  return typeof result.meta?.changes === "number" ? result.meta.changes : 0;
}

function assertConfigured(env: Env): void {
  const requiredValues: Array<[string, string | undefined]> = [
    ["REPORT_HMAC_SECRET", env.REPORT_HMAC_SECRET],
    ["GITHUB_APP_ID", env.GITHUB_APP_ID],
    ["GITHUB_INSTALLATION_ID", env.GITHUB_INSTALLATION_ID],
    ["GITHUB_PRIVATE_KEY_PEM", env.GITHUB_PRIVATE_KEY_PEM],
    ["GITHUB_OWNER", env.GITHUB_OWNER],
    ["GITHUB_REPO", env.GITHUB_REPO]
  ];
  const missing = requiredValues.filter(([, value]) => !value).map(([name]) => name);
  if (missing.length > 0) {
    throw new Error(`Worker is missing required configuration: ${missing.join(", ")}`);
  }
}

function hex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function hmacHex(secret: string, value: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  return hex(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value)));
}

async function readReport(db: D1Database, reportRef: string): Promise<ReportRow | null> {
  return db
    .prepare(
      `SELECT report_ref, reporter_hash, ip_hash, status, github_issue_number, github_issue_url, created_at, updated_at
       FROM reports
       WHERE report_ref = ?`
    )
    .bind(reportRef)
    .first<ReportRow>();
}

function createdResponse(row: ReportRow): Response {
  return jsonResponse({
    ok: true,
    report_ref: row.report_ref,
    issue_number: row.github_issue_number,
    issue_url: row.github_issue_url
  });
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForCreatedReport(db: D1Database, reportRef: string): Promise<Response> {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    await delay(25);
    const row = await readReport(db, reportRef);
    if (row?.status === "created") {
      return createdResponse(row);
    }

    if (row?.status === "failed") {
      return jsonResponse({ ok: false, error: "report creation failed" }, 503);
    }
  }

  return jsonResponse({ ok: true, report_ref: reportRef, status: "creating" }, 202);
}

async function insertCreatingReport(
  db: D1Database,
  report: FeedbackReport,
  reporterHash: string,
  ipHash: string,
  nowSeconds: number
): Promise<boolean> {
  const result = await db
    .prepare(
      `INSERT INTO reports (report_ref, reporter_hash, ip_hash, status, created_at, updated_at)
       VALUES (?, ?, ?, 'creating', ?, ?)
       ON CONFLICT(report_ref) DO NOTHING`
    )
    .bind(report.report_ref, reporterHash, ipHash, nowSeconds, nowSeconds)
    .run();

  return resultChanges(result) > 0;
}

async function claimFailedReport(db: D1Database, reportRef: string, nowSeconds: number): Promise<boolean> {
  const result = await db
    .prepare(
      `UPDATE reports
       SET status = 'creating', updated_at = ?
       WHERE report_ref = ? AND status = 'failed'`
    )
    .bind(nowSeconds, reportRef)
    .run();

  return resultChanges(result) > 0;
}

async function markCreated(db: D1Database, reportRef: string, issueNumber: number, issueUrl: string, nowSeconds: number): Promise<boolean> {
  const result = await db
    .prepare(
      `UPDATE reports
       SET status = 'created', github_issue_number = ?, github_issue_url = ?, updated_at = ?
       WHERE report_ref = ? AND status <> 'created'`
    )
    .bind(issueNumber, issueUrl, nowSeconds, reportRef)
    .run();

  return resultChanges(result) > 0;
}

async function markFailed(db: D1Database, reportRef: string, nowSeconds: number): Promise<void> {
  await db
    .prepare(
      `UPDATE reports
       SET status = 'failed', updated_at = ?
       WHERE report_ref = ? AND status = 'creating'`
    )
    .bind(nowSeconds, reportRef)
    .run();
}

async function applyRateLimits(env: Env, reporterHash: string, ipHash: string, nowSeconds: number): Promise<Response | null> {
  const reporterWindow = await incrementFixedWindow(env.FEEDBACK_DB, `reporter:${reporterHash}`, nowSeconds, oneHourSeconds);
  const reporterLimit = parsePositiveInteger(env.REPORTER_LIMIT_PER_HOUR, defaultReporterLimit);
  if (reporterWindow.count > reporterLimit) {
    return jsonResponse({ ok: false, error: "reporter rate limit exceeded" }, 429);
  }

  const ipWindow = await incrementFixedWindow(env.FEEDBACK_DB, `ip:${ipHash}`, nowSeconds, oneHourSeconds);
  const ipLimit = parsePositiveInteger(env.IP_LIMIT_PER_HOUR, defaultIpLimit);
  if (ipWindow.count > ipLimit) {
    return jsonResponse({ ok: false, error: "IP rate limit exceeded" }, 429);
  }

  return null;
}

async function reconcileExistingGitHubIssue(
  env: Env,
  report: FeedbackReport,
  reporterHash: string,
  ipHash: string,
  nowSeconds: number,
  existing: ReportRow | null
): Promise<Response | null> {
  const issue = await findExistingGitHubIssue(env, report.report_ref, nowSeconds);
  if (!issue) {
    return null;
  }

  if (existing) {
    await markCreated(env.FEEDBACK_DB, report.report_ref, issue.number, issue.html_url, nowSeconds);
  } else {
    const inserted = await env.FEEDBACK_DB
      .prepare(
        `INSERT INTO reports (report_ref, reporter_hash, ip_hash, status, github_issue_number, github_issue_url, created_at, updated_at)
         VALUES (?, ?, ?, 'created', ?, ?, ?, ?)
         ON CONFLICT(report_ref) DO NOTHING`
      )
      .bind(report.report_ref, reporterHash, ipHash, issue.number, issue.html_url, nowSeconds, nowSeconds)
      .run();

    if (resultChanges(inserted) === 0) {
      const row = await readReport(env.FEEDBACK_DB, report.report_ref);
      if (row?.status === "created") {
        return createdResponse(row);
      }

      await markCreated(env.FEEDBACK_DB, report.report_ref, issue.number, issue.html_url, nowSeconds);
    }
  }

  return jsonResponse({ ok: true, report_ref: report.report_ref, issue_number: issue.number, issue_url: issue.html_url });
}

async function handleCreateReport(request: Request, env: Env): Promise<Response> {
  const maxBodyBytes = parsePositiveInteger(env.MAX_BODY_BYTES, defaultMaxBodyBytes);
  const contentLength = request.headers.get("content-length");
  if (contentLength && Number.parseInt(contentLength, 10) > maxBodyBytes) {
    return jsonResponse({ ok: false, error: "request body is too large" }, 413);
  }

  const bodyText = await request.text();
  if (new TextEncoder().encode(bodyText).byteLength > maxBodyBytes) {
    return jsonResponse({ ok: false, error: "request body is too large" }, 413);
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(bodyText);
  } catch {
    return jsonResponse({ ok: false, error: "invalid JSON" }, 400);
  }

  const validation = validateFeedbackReport(parsed);
  if (!validation.ok || !validation.report) {
    return jsonResponse({ ok: false, error: "invalid report", details: validation.errors ?? [] }, 422);
  }

  const report = validation.report;
  assertConfigured(env);
  const nowSeconds = Math.floor(Date.now() / 1000);
  const clientIp = request.headers.get("CF-Connecting-IP");
  const reporterHash = await hmacHex(env.REPORT_HMAC_SECRET, `reporter:${report.reporter_id}`);
  const ipHash = await hmacHex(env.REPORT_HMAC_SECRET, `ip:${clientIp ?? ""}`);

  const existing = await readReport(env.FEEDBACK_DB, report.report_ref);
  if (existing && existing.reporter_hash !== reporterHash) {
    return jsonResponse({ ok: false, error: "report_ref belongs to a different reporter" }, 409);
  }

  if (existing?.status === "created") {
    return createdResponse(existing);
  }

  if (existing?.status === "creating") {
    let reconciled: Response | null;
    try {
      reconciled = await reconcileExistingGitHubIssue(env, report, reporterHash, ipHash, nowSeconds, existing);
    } catch {
      return jsonResponse({ ok: false, error: "report reconciliation failed" }, 503);
    }

    return reconciled ?? waitForCreatedReport(env.FEEDBACK_DB, report.report_ref);
  }

  const rateLimitResponse = await applyRateLimits(env, reporterHash, ipHash, nowSeconds);
  if (rateLimitResponse) {
    return rateLimitResponse;
  }

  let reconciled: Response | null;
  try {
    reconciled = await reconcileExistingGitHubIssue(env, report, reporterHash, ipHash, nowSeconds, existing);
  } catch {
    return jsonResponse({ ok: false, error: "report reconciliation failed" }, 503);
  }

  if (reconciled) {
    return reconciled;
  }

  let claimed = false;
  if (existing?.status === "failed") {
    claimed = await claimFailedReport(env.FEEDBACK_DB, report.report_ref, nowSeconds);
  } else {
    claimed = await insertCreatingReport(env.FEEDBACK_DB, report, reporterHash, ipHash, nowSeconds);
  }

  if (!claimed) {
    return waitForCreatedReport(env.FEEDBACK_DB, report.report_ref);
  }

  let issue;
  try {
    issue = await createGitHubIssue(env, report, reporterHash.slice(0, 12), report.reporter_id, clientIp, nowSeconds);
  } catch {
    await markFailed(env.FEEDBACK_DB, report.report_ref, nowSeconds);
    return jsonResponse({ ok: false, error: "GitHub issue creation failed" }, 503);
  }

  try {
    const updated = await markCreated(env.FEEDBACK_DB, report.report_ref, issue.number, issue.html_url, nowSeconds);
    if (!updated) {
      const row = await readReport(env.FEEDBACK_DB, report.report_ref);
      if (row?.status === "created") {
        return createdResponse(row);
      }

      return jsonResponse({ ok: false, error: "report state changed while creating issue" }, 503);
    }

    return jsonResponse({ ok: true, report_ref: report.report_ref, issue_number: issue.number, issue_url: issue.html_url });
  } catch {
    return jsonResponse({ ok: false, error: "report issue was created but state update failed" }, 503);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return jsonResponse({ ok: true });
    }

    if (url.pathname !== "/v1/reports") {
      return jsonResponse({ ok: false, error: "not found" }, 404);
    }

    if (request.method !== "POST") {
      return jsonResponse({ ok: false, error: "method not allowed" }, 405);
    }

    return handleCreateReport(request, env);
  }
} satisfies ExportedHandler<Env>;
