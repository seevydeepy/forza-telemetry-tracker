import { FeedbackReport, labelsForCategory } from "./schema";

const githubAccept = "application/vnd.github+json";
const githubApiVersion = "2026-03-10";
const userAgent = "forza-telemetry-feedback-worker";

export interface GitHubAppEnv {
  GITHUB_APP_ID: string;
  GITHUB_INSTALLATION_ID: string;
  GITHUB_PRIVATE_KEY_PEM: string;
  GITHUB_OWNER: string;
  GITHUB_REPO: string;
}

export interface CreatedIssue {
  number: number;
  html_url: string;
}

interface GitHubIssueSearchItem {
  number?: number;
  html_url?: string;
  title?: string;
  body?: string | null;
}

interface GitHubIssueSearchResponse {
  items?: GitHubIssueSearchItem[];
}

interface InstallationTokenResponse {
  token?: string;
}

function normalizePrivateKey(pem: string): string {
  return pem.replace(/\\n/g, "\n").trim();
}

function base64UrlFromBytes(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }

  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function base64UrlFromUtf8(value: string): string {
  return base64UrlFromBytes(new TextEncoder().encode(value));
}

function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value.replace(/\s+/g, ""));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return bytes;
}

function pemBlockFromPrivateKey(pem: string): { label: string; der: Uint8Array } {
  const normalized = normalizePrivateKey(pem);
  const match = normalized.match(/^-----BEGIN ([A-Z ]+)-----\s*([A-Za-z0-9+/=\s]+)\s*-----END \1-----$/);
  if (!match) {
    throw new Error("GitHub App private key must be a PEM PRIVATE KEY or RSA PRIVATE KEY");
  }

  return { label: match[1], der: base64ToBytes(match[2]) };
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
  if (!Number.isInteger(length) || length < 0) {
    throw new Error("DER length must be a non-negative integer");
  }

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

function wrapPkcs1RsaPrivateKeyAsPkcs8(pkcs1Der: Uint8Array): Uint8Array {
  const privateKeyInfoVersion = Uint8Array.of(0x02, 0x01, 0x00);
  const rsaEncryptionAlgorithmIdentifier = Uint8Array.of(
    0x30,
    0x0d,
    0x06,
    0x09,
    0x2a,
    0x86,
    0x48,
    0x86,
    0xf7,
    0x0d,
    0x01,
    0x01,
    0x01,
    0x05,
    0x00
  );
  const privateKey = derElement(0x04, pkcs1Der);
  return derElement(0x30, concatBytes(privateKeyInfoVersion, rsaEncryptionAlgorithmIdentifier, privateKey));
}

function pkcs8DerFromPem(pem: string): Uint8Array {
  const { label, der } = pemBlockFromPrivateKey(pem);
  if (label === "PRIVATE KEY") {
    return der;
  }

  if (label === "RSA PRIVATE KEY") {
    return wrapPkcs1RsaPrivateKeyAsPkcs8(der);
  }

  throw new Error(`Unsupported GitHub App private key PEM type: ${label}`);
}

function exactArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

export async function createGitHubAppJwt(env: GitHubAppEnv, nowSeconds: number): Promise<string> {
  const header = { alg: "RS256", typ: "JWT" };
  const payload = {
    iat: nowSeconds - 60,
    exp: nowSeconds + 9 * 60,
    iss: env.GITHUB_APP_ID
  };
  const signingInput = `${base64UrlFromUtf8(JSON.stringify(header))}.${base64UrlFromUtf8(JSON.stringify(payload))}`;
  const key = await crypto.subtle.importKey(
    "pkcs8",
    exactArrayBuffer(pkcs8DerFromPem(env.GITHUB_PRIVATE_KEY_PEM)),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signature = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(signingInput));
  return `${signingInput}.${base64UrlFromBytes(new Uint8Array(signature))}`;
}

async function requestInstallationToken(env: GitHubAppEnv, nowSeconds: number): Promise<string> {
  const jwt = await createGitHubAppJwt(env, nowSeconds);
  const response = await fetch(
    `https://api.github.com/app/installations/${encodeURIComponent(env.GITHUB_INSTALLATION_ID)}/access_tokens`,
    {
      method: "POST",
      headers: {
        Accept: githubAccept,
        "X-GitHub-Api-Version": githubApiVersion,
        "User-Agent": userAgent,
        Authorization: `Bearer ${jwt}`
      }
    }
  );

  if (!response.ok) {
    throw new Error(`GitHub installation token request failed with ${response.status}`);
  }

  const tokenResponse = (await response.json()) as InstallationTokenResponse;
  if (!tokenResponse.token) {
    throw new Error("GitHub installation token response did not include a token");
  }

  return tokenResponse.token;
}

function redactRawIdentifiers(value: string | undefined, rawReporterId: string, rawIp: string | null): string {
  if (!value) {
    return "";
  }

  let redacted = value.split(rawReporterId).join("[redacted reporter id]");
  if (rawIp) {
    redacted = redacted.split(rawIp).join("[redacted ip]");
  }

  return redacted;
}

function scrubSensitiveText(value: string | undefined, rawReporterId: string, rawIp: string | null): string {
  return redactRawIdentifiers(value, rawReporterId, rawIp)
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [redacted token]")
    .replace(
      /\b([A-Za-z0-9_.-]*(?:api[_-]?key|token|secret|password|passwd|pwd|authorization|auth)[A-Za-z0-9_.-]*)\s*[:=]\s*["']?([^\s"',;]+)/gi,
      "$1=[redacted secret]"
    )
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[redacted email]")
    .replace(/\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b/g, "[redacted ip address]")
    .replace(/\b(?:[A-F0-9]{1,4}:){1,7}:[A-F0-9]{0,4}\b/gi, "[redacted ip address]")
    .replace(/\b(?:[A-F0-9]{1,4}:){2,7}[A-F0-9]{0,4}\b/gi, "[redacted ip address]")
    .replace(/([A-Za-z]:\\Users\\)([^\\\r\n]+)/g, "$1[redacted-user]");
}

function sanitizeStructuredValue(value: unknown, rawReporterId: string, rawIp: string | null): unknown {
  if (typeof value === "string") {
    return scrubSensitiveText(value, rawReporterId, rawIp);
  }

  if (Array.isArray(value)) {
    return value.map((item) => sanitizeStructuredValue(item, rawReporterId, rawIp));
  }

  if (value && typeof value === "object") {
    const sanitized: Record<string, unknown> = {};
    for (const [key, nestedValue] of Object.entries(value)) {
      sanitized[scrubSensitiveText(key, rawReporterId, rawIp)] = sanitizeStructuredValue(nestedValue, rawReporterId, rawIp);
    }
    return sanitized;
  }

  return value;
}

function jsonBlock(value: unknown, rawReporterId: string, rawIp: string | null): string {
  return JSON.stringify(sanitizeStructuredValue(value ?? {}, rawReporterId, rawIp), null, 2);
}

function codeBlock(language: string, value: string): string {
  return `\`\`\`${language}\n${value}\n\`\`\``;
}

export function buildIssueTitle(report: FeedbackReport): string {
  return `[${report.report_ref}] ${report.category}`;
}

export function buildIssueBody(
  report: FeedbackReport,
  reporterFingerprint: string,
  rawReporterId: string,
  rawIp: string | null
): string {
  const diagnosticsLog = report.include_diagnostics
    ? scrubSensitiveText(report.diagnostics?.recent_log ?? "", rawReporterId, rawIp)
    : "";
  const diagnostics = report.include_diagnostics ? report.diagnostics : {};

  const sections = [
    "## Report",
    `- Report ref: ${report.report_ref}`,
    `- Category: ${report.category}`,
    `- Source: ${scrubSensitiveText(report.source, rawReporterId, rawIp) || "unknown"}`,
    `- Scene: ${scrubSensitiveText(report.scene, rawReporterId, rawIp) || "unknown"}`,
    `- Reporter fingerprint: ${reporterFingerprint}`,
    `- Client timestamp (UTC): ${scrubSensitiveText(report.client_timestamp_utc, rawReporterId, rawIp) || "unknown"}`,
    "",
    "## Description",
    scrubSensitiveText(report.description, rawReporterId, rawIp),
    "",
    "## Build",
    codeBlock("json", jsonBlock(report.build, rawReporterId, rawIp)),
    "",
    "## Platform",
    codeBlock("json", jsonBlock(report.platform, rawReporterId, rawIp)),
    "",
    "## Settings",
    codeBlock("json", jsonBlock(report.settings, rawReporterId, rawIp)),
    "",
    "## Diagnostics",
    codeBlock("json", jsonBlock(diagnostics, rawReporterId, rawIp)),
    "",
    "## Recent Log",
    diagnosticsLog ? codeBlock("text", diagnosticsLog) : "Diagnostics were not included."
  ];

  return sections.join("\n");
}

export async function findExistingGitHubIssue(
  env: GitHubAppEnv,
  reportRef: string,
  nowSeconds: number
): Promise<CreatedIssue | null> {
  const token = await requestInstallationToken(env, nowSeconds);
  const query = `repo:${env.GITHUB_OWNER}/${env.GITHUB_REPO} type:issue "${reportRef}"`;
  const response = await fetch(`https://api.github.com/search/issues?q=${encodeURIComponent(query)}`, {
    method: "GET",
    headers: {
      Accept: githubAccept,
      "X-GitHub-Api-Version": githubApiVersion,
      "User-Agent": userAgent,
      Authorization: `Bearer ${token}`
    }
  });

  if (!response.ok) {
    throw new Error(`GitHub issue search failed with ${response.status}`);
  }

  const searchResponse = (await response.json()) as GitHubIssueSearchResponse;
  for (const item of searchResponse.items ?? []) {
    const title = item.title ?? "";
    const body = item.body ?? "";
    const hasExactReportRef = title.includes(`[${reportRef}]`) || body.includes(`Report ref: ${reportRef}`);
    if (hasExactReportRef && typeof item.number === "number" && typeof item.html_url === "string") {
      return { number: item.number, html_url: item.html_url };
    }
  }

  return null;
}

export async function createGitHubIssue(
  env: GitHubAppEnv,
  report: FeedbackReport,
  reporterFingerprint: string,
  rawReporterId: string,
  rawIp: string | null,
  nowSeconds: number
): Promise<CreatedIssue> {
  const token = await requestInstallationToken(env, nowSeconds);
  const labels = labelsForCategory(report.category);
  const requestBody = {
    title: buildIssueTitle(report),
    body: buildIssueBody(report, reporterFingerprint, rawReporterId, rawIp),
    ...(labels.length > 0 ? { labels } : {})
  };

  const postIssue = async (body: typeof requestBody): Promise<Response> =>
    fetch(`https://api.github.com/repos/${encodeURIComponent(env.GITHUB_OWNER)}/${encodeURIComponent(env.GITHUB_REPO)}/issues`, {
      method: "POST",
      headers: {
        Accept: githubAccept,
        "X-GitHub-Api-Version": githubApiVersion,
        "User-Agent": userAgent,
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    });

  let response = await postIssue(requestBody);
  if (response.status === 422 && labels.length > 0) {
    const { labels: _labels, ...withoutLabels } = requestBody;
    response = await postIssue(withoutLabels);
  }

  if (!response.ok) {
    throw new Error(`GitHub issue creation failed with ${response.status}`);
  }

  const issue = (await response.json()) as Partial<CreatedIssue>;
  if (typeof issue.number !== "number" || typeof issue.html_url !== "string") {
    throw new Error("GitHub issue response did not include issue number and html_url");
  }

  return { number: issue.number, html_url: issue.html_url };
}
