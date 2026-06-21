import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { createGitHubAppJwt } from "../src/githubApp";
import worker, { Env } from "../src/index";

type ReportStatus = "creating" | "created" | "failed";

interface MockReportRow {
  report_ref: string;
  reporter_hash: string;
  ip_hash: string;
  status: ReportStatus;
  github_issue_number: number | null;
  github_issue_url: string | null;
  created_at: number;
  updated_at: number;
}

interface MockRateRow {
  key: string;
  windowStart: number;
  count: number;
}

class MockStatement {
  private parameters: unknown[] = [];

  public constructor(
    private readonly database: MockD1Database,
    private readonly sql: string
  ) {}

  public bind(...parameters: unknown[]): MockStatement {
    this.parameters = parameters;
    return this;
  }

  public async first<T = unknown>(): Promise<T | null> {
    const normalized = this.sql.toLowerCase();
    if (normalized.includes("insert into rate_limits")) {
      const [key, windowStart] = this.parameters as [string, number];
      const current = this.database.rateLimits.get(key);
      if (!current || current.windowStart !== windowStart) {
        const next = { key, windowStart, count: 1 };
        this.database.rateLimits.set(key, next);
        return { windowStart: next.windowStart, count: next.count } as T;
      }

      current.count += 1;
      return { windowStart: current.windowStart, count: current.count } as T;
    }

    if (normalized.includes("from reports") && normalized.includes("where report_ref")) {
      const [reportRef] = this.parameters as [string];
      const row = this.database.reports.get(reportRef);
      return row ? ({ ...row } as T) : null;
    }

    throw new Error(`MockD1 first() did not recognize SQL: ${this.sql}`);
  }

  public async run(): Promise<D1Result> {
    const normalized = this.sql.toLowerCase();
    if (normalized.includes("insert into reports")) {
      if (normalized.includes("'created'")) {
        const [reportRef, reporterHash, ipHash, issueNumber, issueUrl, createdAt, updatedAt] = this.parameters as [
          string,
          string,
          string,
          number,
          string,
          number,
          number
        ];
        if (this.database.reports.has(reportRef)) {
          return this.result(0);
        }

        this.database.reports.set(reportRef, {
          report_ref: reportRef,
          reporter_hash: reporterHash,
          ip_hash: ipHash,
          status: "created",
          github_issue_number: issueNumber,
          github_issue_url: issueUrl,
          created_at: createdAt,
          updated_at: updatedAt
        });
        return this.result(1);
      }

      const [reportRef, reporterHash, ipHash, createdAt, updatedAt] = this.parameters as [string, string, string, number, number];
      if (this.database.reports.has(reportRef)) {
        return this.result(0);
      }

      this.database.reports.set(reportRef, {
        report_ref: reportRef,
        reporter_hash: reporterHash,
        ip_hash: ipHash,
        status: "creating",
        github_issue_number: null,
        github_issue_url: null,
        created_at: createdAt,
        updated_at: updatedAt
      });
      return this.result(1);
    }

    if (normalized.includes("set status = 'creating'")) {
      const [updatedAt, reportRef] = this.parameters as [number, string];
      const row = this.database.reports.get(reportRef);
      if (!row || row.status !== "failed") {
        return this.result(0);
      }

      row.status = "creating";
      row.updated_at = updatedAt;
      return this.result(1);
    }

    if (normalized.includes("set status = 'created'")) {
      if (this.database.failCreatedUpdateCount > 0) {
        this.database.failCreatedUpdateCount -= 1;
        throw new Error("simulated markCreated failure");
      }

      const [issueNumber, issueUrl, updatedAt, reportRef] = this.parameters as [number, string, number, string];
      const row = this.database.reports.get(reportRef);
      if (!row || row.status === "created") {
        return this.result(0);
      }

      row.status = "created";
      row.github_issue_number = issueNumber;
      row.github_issue_url = issueUrl;
      row.updated_at = updatedAt;
      return this.result(1);
    }

    if (normalized.includes("set status = 'failed'")) {
      const [updatedAt, reportRef] = this.parameters as [number, string];
      const row = this.database.reports.get(reportRef);
      if (!row || row.status !== "creating") {
        return this.result(0);
      }

      row.status = "failed";
      row.updated_at = updatedAt;
      return this.result(1);
    }

    throw new Error(`MockD1 run() did not recognize SQL: ${this.sql}`);
  }

  public async all<T = unknown>(): Promise<D1Result<T>> {
    return { success: true, results: [], meta: { changes: 0 } } as unknown as D1Result<T>;
  }

  private result(changes: number): D1Result {
    return { success: true, meta: { changes } } as unknown as D1Result;
  }
}

class MockD1Database {
  public readonly reports = new Map<string, MockReportRow>();
  public readonly rateLimits = new Map<string, MockRateRow>();
  public failCreatedUpdateCount = 0;

  public prepare(sql: string): MockStatement {
    return new MockStatement(this, sql);
  }
}

let privateKeyPem: string;
let pkcs1PrivateKeyPem: string;

beforeAll(async () => {
  const keyPair = await crypto.subtle.generateKey(
    {
      name: "RSASSA-PKCS1-v1_5",
      modulusLength: 2048,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: "SHA-256"
    },
    true,
    ["sign", "verify"]
  );
  const pkcs8 = await crypto.subtle.exportKey("pkcs8", keyPair.privateKey);
  privateKeyPem = toPem(pkcs8);
  const jwk = await crypto.subtle.exportKey("jwk", keyPair.privateKey);
  pkcs1PrivateKeyPem = toPem(pkcs1DerFromJwk(jwk), "RSA PRIVATE KEY");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function toPem(buffer: ArrayBuffer | Uint8Array, label = "PRIVATE KEY"): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  const base64 = btoa(binary);
  const lines = base64.match(/.{1,64}/g) ?? [];
  return `-----BEGIN ${label}-----\n${lines.join("\n")}\n-----END ${label}-----`;
}

function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return bytes;
}

function base64UrlToBytes(value: string): Uint8Array {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  return base64ToBytes(`${value}${padding}`.replace(/-/g, "+").replace(/_/g, "/"));
}

function concatBytes(...parts: Uint8Array[]): Uint8Array {
  const totalLength = parts.reduce((total, part) => total + part.length, 0);
  const output = new Uint8Array(totalLength);
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }

  return output;
}

function derLength(length: number): Uint8Array {
  if (length < 0x80) {
    return Uint8Array.of(length);
  }

  const bytes: number[] = [];
  let remaining = length;
  while (remaining > 0) {
    bytes.unshift(remaining & 0xff);
    remaining = Math.floor(remaining / 256);
  }

  return Uint8Array.of(0x80 | bytes.length, ...bytes);
}

function derElement(tag: number, content: Uint8Array): Uint8Array {
  return concatBytes(Uint8Array.of(tag), derLength(content.length), content);
}

function derIntegerFromUnsigned(bytes: Uint8Array): Uint8Array {
  let start = 0;
  while (start < bytes.length - 1 && bytes[start] === 0) {
    start += 1;
  }

  const trimmed = bytes.slice(start);
  const unsigned = trimmed[0] >= 0x80 ? concatBytes(Uint8Array.of(0), trimmed) : trimmed;
  return derElement(0x02, unsigned);
}

function jwkFieldBytes(jwk: JsonWebKey, fieldName: keyof JsonWebKey): Uint8Array {
  const value = jwk[fieldName];
  if (typeof value !== "string") {
    throw new Error(`Generated RSA JWK did not include ${String(fieldName)}`);
  }

  return base64UrlToBytes(value);
}

function pkcs1DerFromJwk(jwk: JsonWebKey): Uint8Array {
  const version = Uint8Array.of(0x02, 0x01, 0x00);
  const fields = ["n", "e", "d", "p", "q", "dp", "dq", "qi"] as Array<keyof JsonWebKey>;
  return derElement(
    0x30,
    concatBytes(version, ...fields.map((fieldName) => derIntegerFromUnsigned(jwkFieldBytes(jwk, fieldName))))
  );
}

function env(overrides: Partial<Env> = {}): Env {
  return {
    FEEDBACK_DB: new MockD1Database() as unknown as D1Database,
    REPORT_HMAC_SECRET: "test-hmac-secret",
    GITHUB_APP_ID: "12345",
    GITHUB_INSTALLATION_ID: "67890",
    GITHUB_PRIVATE_KEY_PEM: privateKeyPem,
    GITHUB_OWNER: "seevydeepy",
    GITHUB_REPO: "forza-telemetry-feedback",
    MAX_BODY_BYTES: "65536",
    REPORTER_LIMIT_PER_HOUR: "5",
    IP_LIMIT_PER_HOUR: "20",
    ...overrides
  };
}

function sampleReport(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: 1,
    report_ref: "FTT-ABC234DE",
    reporter_id: "11111111-2222-3333-4444-555555555555",
    category: "Bug",
    description: "Lap capture stopped while reviewing the telemetry dashboard.",
    source: "desktop-app",
    scene: "dashboard",
    include_diagnostics: true,
    build: {
      display_version: "0.1.0",
      build_identifier: "local-test",
      build_channel: "dev",
      git_short_sha: "abc1234",
      metadata_source: "test"
    },
    platform: {
      os_name: "Windows",
      display_server: "windows",
      locale: "en_GB"
    },
    settings: {
      reduced_motion: false,
      high_contrast: false,
      window_mode: "Windowed",
      display_resolution: "1920x1080",
      vsync_mode_index: 1,
      max_fps_limit: 144,
      shadow_quality: "High",
      glow_quality: "High",
      sky_fx_quality: "High",
      trail_effects_quality: "High",
      dynamic_lights_quality: "High"
    },
    diagnostics: {
      recent_log: "recent local log"
    },
    client_timestamp_utc: "2026-06-17T12:00:00Z",
    ...overrides
  };
}

function postReport(report: unknown, envValue: Env, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!headers.has("CF-Connecting-IP")) {
    headers.set("CF-Connecting-IP", "203.0.113.99");
  }

  return worker.fetch(
    new Request("https://feedback.example/v1/reports", {
      method: "POST",
      ...init,
      headers,
      body: typeof report === "string" ? report : JSON.stringify(report)
    }),
    envValue
  );
}

function installGitHubFetchMock(options: { issueDelayMs?: number; issueStatus?: number; failLabelsOnce?: boolean } = {}) {
  const issuePayloads: Array<Record<string, unknown>> = [];
  const createdIssues: Array<{ number: number; html_url: string; title: string; body: string }> = [];
  let rejectedLabels = false;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = input.toString();
    if (url.includes("/app/installations/") && url.endsWith("/access_tokens")) {
      return Response.json({ token: "installation-token" });
    }

    if (url.startsWith("https://api.github.com/search/issues")) {
      const parsedUrl = new URL(url);
      const query = parsedUrl.searchParams.get("q") ?? "";
      const refMatch = query.match(/\"(FTT-[A-Z2-7]{8})\"/);
      const reportRef = refMatch?.[1];
      const items = reportRef
        ? createdIssues.filter((issue) => issue.title.includes(`[${reportRef}]`) || issue.body.includes(`Report ref: ${reportRef}`))
        : [];
      return Response.json({ items });
    }

    if (url.endsWith("/repos/seevydeepy/forza-telemetry-feedback/issues")) {
      if (options.issueDelayMs) {
        await new Promise((resolve) => setTimeout(resolve, options.issueDelayMs));
      }
      issuePayloads.push(JSON.parse(init?.body?.toString() ?? "{}"));
      if (options.failLabelsOnce && !rejectedLabels && Array.isArray(issuePayloads[issuePayloads.length - 1].labels)) {
        rejectedLabels = true;
        return Response.json({ message: "labels do not exist" }, { status: 422 });
      }

      const status = options.issueStatus ?? 201;
      if (status >= 400) {
        return Response.json({ message: "issue failed" }, { status });
      }

      const issue = {
        number: 101,
        html_url: "https://github.com/seevydeepy/forza-telemetry-feedback/issues/101",
        title: String(issuePayloads[issuePayloads.length - 1].title),
        body: String(issuePayloads[issuePayloads.length - 1].body)
      };
      createdIssues.push(issue);
      return Response.json(issue, { status });
    }

    throw new Error(`Unexpected GitHub fetch URL: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, issuePayloads, createdIssues };
}

describe("feedback worker", () => {
  it("signs GitHub App JWTs with PKCS#8 private key PEM", async () => {
    const jwt = await createGitHubAppJwt(env(), 1_800_000_000);
    const parts = jwt.split(".");
    const header = JSON.parse(new TextDecoder().decode(base64UrlToBytes(parts[0])));

    expect(parts).toHaveLength(3);
    expect(header).toMatchObject({ alg: "RS256", typ: "JWT" });
  });

  it("signs GitHub App JWTs with PKCS#1 RSA private key PEM", async () => {
    const jwt = await createGitHubAppJwt(env({ GITHUB_PRIVATE_KEY_PEM: pkcs1PrivateKeyPem }), 1_800_000_000);
    const parts = jwt.split(".");
    const header = JSON.parse(new TextDecoder().decode(base64UrlToBytes(parts[0])));

    expect(parts).toHaveLength(3);
    expect(header).toMatchObject({ alg: "RS256", typ: "JWT" });
  });

  it("serves GET /health", async () => {
    const response = await worker.fetch(new Request("https://feedback.example/health"), env());

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
  });

  it("rejects invalid JSON", async () => {
    const response = await postReport("{", env());

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toMatchObject({ ok: false, error: "invalid JSON" });
  });

  it("rejects invalid schema", async () => {
    const response = await postReport(sampleReport({ category: "Crash" }), env());

    expect(response.status).toBe(422);
    await expect(response.json()).resolves.toMatchObject({ ok: false, error: "invalid report" });
  });

  it("rejects invalid report refs with the Forza ref pattern", async () => {
    const response = await postReport(sampleReport({ report_ref: "MS-ABC234" }), env());

    expect(response.status).toBe(422);
    await expect(response.json()).resolves.toMatchObject({
      ok: false,
      error: "invalid report",
      details: ["report_ref must match ^FTT-[A-Z2-7]{8}$"]
    });
  });

  it("rejects malformed client timestamps", async () => {
    const response = await postReport(sampleReport({ client_timestamp_utc: "not-a-date" }), env());

    expect(response.status).toBe(422);
    await expect(response.json()).resolves.toMatchObject({
      ok: false,
      error: "invalid report",
      details: ["client_timestamp_utc must be a valid timestamp"]
    });
  });

  it("rejects requests over the configured size limit", async () => {
    const response = await postReport(
      sampleReport(),
      env({ MAX_BODY_BYTES: "10" }),
      { headers: { "Content-Length": "65537", "CF-Connecting-IP": "203.0.113.99" } }
    );

    expect(response.status).toBe(413);
    await expect(response.json()).resolves.toMatchObject({ ok: false, error: "request body is too large" });
  });

  it("creates a GitHub issue for a valid report", async () => {
    const envValue = env();
    const { issuePayloads } = installGitHubFetchMock();

    const response = await postReport(sampleReport(), envValue);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({ ok: true, report_ref: "FTT-ABC234DE", issue_number: 101 });
    expect(issuePayloads).toHaveLength(1);
    expect(issuePayloads[0]).toMatchObject({
      title: "[FTT-ABC234DE] Bug",
      labels: ["type:bug"]
    });
    expect(issuePayloads[0].body).toContain("Reporter fingerprint:");
  });

  it("returns an existing created issue idempotently for duplicate report_ref", async () => {
    const envValue = env();
    const { issuePayloads } = installGitHubFetchMock();

    const first = await postReport(sampleReport(), envValue);
    const second = await postReport(sampleReport(), envValue);

    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    await expect(second.json()).resolves.toMatchObject({ ok: true, report_ref: "FTT-ABC234DE", issue_number: 101 });
    expect(issuePayloads).toHaveLength(1);
  });

  it("does not consume rate-limit quota for an idempotent created retry", async () => {
    const database = new MockD1Database();
    const envValue = env({
      FEEDBACK_DB: database as unknown as D1Database,
      REPORTER_LIMIT_PER_HOUR: "1",
      IP_LIMIT_PER_HOUR: "1"
    });
    const { issuePayloads } = installGitHubFetchMock();

    const first = await postReport(sampleReport(), envValue);
    const second = await postReport(sampleReport(), envValue);

    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    expect(issuePayloads).toHaveLength(1);
    const counts = Array.from(database.rateLimits.values()).map((row) => row.count);
    expect(counts).toEqual([1, 1]);
  });

  it("rejects duplicate report_ref ownership mismatches without creating another issue", async () => {
    const envValue = env();
    const { issuePayloads } = installGitHubFetchMock();

    const first = await postReport(sampleReport(), envValue);
    const second = await postReport(
      sampleReport({
        reporter_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
      }),
      envValue
    );

    expect(first.status).toBe(200);
    expect(second.status).toBe(409);
    await expect(second.json()).resolves.toMatchObject({ ok: false, error: "report_ref belongs to a different reporter" });
    expect(issuePayloads).toHaveLength(1);
  });

  it("handles concurrent duplicate report_ref with one GitHub issue creation", async () => {
    const envValue = env();
    const { issuePayloads } = installGitHubFetchMock({ issueDelayMs: 20 });

    const [first, second] = await Promise.all([
      postReport(sampleReport(), envValue),
      postReport(sampleReport(), envValue)
    ]);

    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    await expect(first.json()).resolves.toMatchObject({ ok: true, report_ref: "FTT-ABC234DE", issue_number: 101 });
    await expect(second.json()).resolves.toMatchObject({ ok: true, report_ref: "FTT-ABC234DE", issue_number: 101 });
    expect(issuePayloads).toHaveLength(1);
  });

  it("reconciles an issue created before a D1 mark-created failure without posting a duplicate issue", async () => {
    const database = new MockD1Database();
    database.failCreatedUpdateCount = 1;
    const envValue = env({ FEEDBACK_DB: database as unknown as D1Database });
    const { issuePayloads } = installGitHubFetchMock();

    const first = await postReport(sampleReport(), envValue);
    const statusAfterFailure = database.reports.get("FTT-ABC234DE")?.status;
    const second = await postReport(sampleReport(), envValue);

    expect(first.status).toBe(503);
    await expect(first.json()).resolves.toMatchObject({ ok: false, error: "report issue was created but state update failed" });
    expect(statusAfterFailure).toBe("creating");
    expect(second.status).toBe(200);
    await expect(second.json()).resolves.toMatchObject({ ok: true, report_ref: "FTT-ABC234DE", issue_number: 101 });
    expect(database.reports.get("FTT-ABC234DE")?.status).toBe("created");
    expect(issuePayloads).toHaveLength(1);
  });

  it("rejects reports over the reporter fixed-window rate limit", async () => {
    const envValue = env({ REPORTER_LIMIT_PER_HOUR: "1" });
    const { issuePayloads } = installGitHubFetchMock();

    const first = await postReport(sampleReport({ report_ref: "FTT-ABC234DE" }), envValue);
    const second = await postReport(sampleReport({ report_ref: "FTT-DEF234GH" }), envValue);

    expect(first.status).toBe(200);
    expect(second.status).toBe(429);
    await expect(second.json()).resolves.toMatchObject({ ok: false, error: "reporter rate limit exceeded" });
    expect(issuePayloads).toHaveLength(1);
  });

  it("rejects reports over the IP fixed-window rate limit", async () => {
    const envValue = env({ IP_LIMIT_PER_HOUR: "1" });
    const { issuePayloads } = installGitHubFetchMock();

    const first = await postReport(sampleReport({ report_ref: "FTT-ABC234DE" }), envValue);
    const second = await postReport(
      sampleReport({
        report_ref: "FTT-DEF234GH",
        reporter_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
      }),
      envValue
    );

    expect(first.status).toBe(200);
    expect(second.status).toBe(429);
    await expect(second.json()).resolves.toMatchObject({ ok: false, error: "IP rate limit exceeded" });
    expect(issuePayloads).toHaveLength(1);
  });

  it("reclaims a failed report row and creates the issue on retry", async () => {
    const envValue = env();
    installGitHubFetchMock({ issueStatus: 500 });

    const first = await postReport(sampleReport(), envValue);
    expect(first.status).toBe(503);

    const { issuePayloads } = installGitHubFetchMock();
    const second = await postReport(sampleReport(), envValue);

    expect(second.status).toBe(200);
    await expect(second.json()).resolves.toMatchObject({ ok: true, report_ref: "FTT-ABC234DE", issue_number: 101 });
    expect(issuePayloads).toHaveLength(1);
  });

  it("retries GitHub issue creation without labels when labels are rejected", async () => {
    const envValue = env();
    const { issuePayloads } = installGitHubFetchMock({ failLabelsOnce: true });

    const response = await postReport(sampleReport(), envValue);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({ ok: true, report_ref: "FTT-ABC234DE", issue_number: 101 });
    expect(issuePayloads).toHaveLength(2);
    expect(issuePayloads[0]).toMatchObject({ labels: ["type:bug"] });
    expect(issuePayloads[1].labels).toBeUndefined();
  });

  it("does not put raw reporter UUID or raw CF-Connecting-IP into the GitHub issue", async () => {
    const envValue = env();
    const rawReporterId = "11111111-2222-3333-4444-555555555555";
    const rawIp = "198.51.100.45";
    const { issuePayloads } = installGitHubFetchMock();

    const response = await postReport(
      sampleReport({
        reporter_id: rawReporterId,
        description: `Report text should redact ${rawReporterId} and ${rawIp}.`,
        diagnostics: { recent_log: `Log mentions ${rawReporterId} from ${rawIp}.` }
      }),
      envValue,
      { headers: { "CF-Connecting-IP": rawIp } }
    );

    expect(response.status).toBe(200);
    expect(issuePayloads).toHaveLength(1);
    expect(issuePayloads[0].title).not.toContain(rawReporterId);
    expect(issuePayloads[0].title).not.toContain(rawIp);
    expect(issuePayloads[0].body).not.toContain(rawReporterId);
    expect(issuePayloads[0].body).not.toContain(rawIp);
    expect(issuePayloads[0].body).toContain("[redacted reporter id]");
    expect(issuePayloads[0].body).toContain("[redacted ip]");
  });

  it("scrubs common diagnostics secrets and identifiers before creating the GitHub issue", async () => {
    const envValue = env();
    const { issuePayloads } = installGitHubFetchMock();

    const response = await postReport(
      sampleReport({
        diagnostics: {
          recent_log: [
            "Authorization: Bearer abc.def.ghi",
            "api_key=sk_test_123456",
            "password: hunter2",
            "email player@example.com",
            "connect 203.0.113.77 and 2001:db8::1",
            "load C:\\Users\\Alice\\AppData\\Local\\Forza Telemetry Tracker\\logs\\app.log",
            "env_TOKEN=env_secret_value"
          ].join("\n")
        }
      }),
      envValue
    );

    expect(response.status).toBe(200);
    expect(issuePayloads).toHaveLength(1);
    const body = String(issuePayloads[0].body);
    expect(body).not.toContain("abc.def.ghi");
    expect(body).not.toContain("sk_test_123456");
    expect(body).not.toContain("hunter2");
    expect(body).not.toContain("player@example.com");
    expect(body).not.toContain("203.0.113.77");
    expect(body).not.toContain("2001:db8::1");
    expect(body).not.toContain("C:\\Users\\Alice");
    expect(body).not.toContain("env_secret_value");
    expect(body).toContain("[redacted token]");
    expect(body).toContain("api_key=[redacted secret]");
    expect(body).toContain("password=[redacted secret]");
    expect(body).toContain("env_TOKEN=[redacted secret]");
    expect(body).toContain("[redacted email]");
    expect(body).toContain("[redacted ip address]");
    expect(body).toContain("C:\\Users\\[redacted-user]");
  });
});
