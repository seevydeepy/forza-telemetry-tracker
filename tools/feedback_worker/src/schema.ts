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
const guidPattern = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const categories = new Set(Object.keys(categoryLabels));

export type FeedbackCategory = keyof typeof categoryLabels;

export interface FeedbackReport {
  schema_version: 1;
  report_ref: string;
  reporter_id: string;
  category: FeedbackCategory;
  description: string;
  source?: string;
  scene?: string;
  include_diagnostics?: boolean;
  build?: unknown;
  platform?: unknown;
  settings?: unknown;
  diagnostics?: {
    recent_log?: string;
    [key: string]: unknown;
  };
  client_timestamp_utc?: string;
  [key: string]: unknown;
}

export interface ValidationResult {
  ok: boolean;
  report?: FeedbackReport;
  errors?: string[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(record: Record<string, unknown>, key: string, errors: string[]): string | undefined {
  const value = record[key];
  if (typeof value !== "string") {
    errors.push(`${key} must be a string`);
    return undefined;
  }

  return value;
}

export function validateFeedbackReport(value: unknown): ValidationResult {
  const errors: string[] = [];

  if (!isRecord(value)) {
    return { ok: false, errors: ["request body must be a JSON object"] };
  }

  if (value.schema_version !== 1) {
    errors.push("schema_version must be 1");
  }

  const reportRef = requireString(value, "report_ref", errors);
  if (reportRef !== undefined && !reportRefPattern.test(reportRef)) {
    errors.push("report_ref must match ^FTT-[A-Z2-7]{8}$");
  }

  const reporterId = requireString(value, "reporter_id", errors);
  if (reporterId !== undefined) {
    if (reporterId.length < 16 || reporterId.length > 80) {
      errors.push("reporter_id must be 16-80 characters");
    }

    if (!guidPattern.test(reporterId)) {
      errors.push("reporter_id must be a GUID string");
    }
  }

  const category = requireString(value, "category", errors);
  if (category !== undefined && !categories.has(category)) {
    errors.push("category is not supported");
  }

  const description = requireString(value, "description", errors);
  if (description !== undefined) {
    const trimmedLength = description.trim().length;
    if (trimmedLength < 3 || description.length > 4000) {
      errors.push("description must be 3-4000 characters");
    }
  }

  if (value.diagnostics !== undefined) {
    if (!isRecord(value.diagnostics)) {
      errors.push("diagnostics must be an object");
    } else if (value.diagnostics.recent_log !== undefined) {
      if (typeof value.diagnostics.recent_log !== "string") {
        errors.push("diagnostics.recent_log must be a string");
      } else if (value.diagnostics.recent_log.length > 16000) {
        errors.push("diagnostics.recent_log must be 16000 characters or fewer");
      }
    }
  }

  if (value.client_timestamp_utc !== undefined) {
    if (typeof value.client_timestamp_utc !== "string") {
      errors.push("client_timestamp_utc must be a string");
    } else {
      const timestamp = Date.parse(value.client_timestamp_utc);
      if (!Number.isFinite(timestamp)) {
        errors.push("client_timestamp_utc must be a valid timestamp");
      }
    }
  }

  if (errors.length > 0) {
    return { ok: false, errors };
  }

  return { ok: true, report: value as FeedbackReport };
}

export function labelsForCategory(category: FeedbackCategory): string[] {
  const label = categoryLabels[category];
  return label ? [label] : [];
}
