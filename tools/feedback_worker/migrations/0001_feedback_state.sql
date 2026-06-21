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
