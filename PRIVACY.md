# Privacy

Forza Telemetry Tracker is a local-first Windows desktop tool.

## Local data

The app stores telemetry sessions, settings, logs, generated map cache files, imports, exports, and related metadata under `%LOCALAPPDATA%\Forza Telemetry Tracker` by default.

The main database is `telemetry_tracker.sqlite3`. SQLite may also create sidecar files such as `telemetry_tracker.sqlite3-wal` and `telemetry_tracker.sqlite3-shm`.

World-map cache files are generated locally from a valid local game install folder that you choose. The repository and release artifacts do not include local game files or generated map-cache files.

## Network behavior

The app does not include automatic analytics, crash reporting, tracking pixels, advertising SDKs, user accounts, or background telemetry upload behavior.

The About window checks public GitHub Releases only when you click `Check for updates`. That request fetches release metadata from GitHub and does not send telemetry sessions or local app data.

The `Send Feedback` window sends data only when you choose to submit a report. The report goes from the local app to the configured Forza Telemetry Feedback Cloudflare Worker, then to private maintainer triage issues in `seevydeepy/forza-telemetry-feedback`. You do not need a GitHub account, and feedback is not filed in the public `seevydeepy/forza-telemetry-tracker` repository.

If the feedback endpoint is unavailable, the app may save the report in the local SQLite feedback outbox and retry later. Queued reports are limited by count, retry attempts, and age.

Cloudflare may expose your public IP address to the Worker request context. The Worker uses it only to derive an HMAC rate-limit key for anti-abuse checks. The raw public IP must not be written to GitHub issues, D1 rows, durable logs, or API responses.

The optional feedback diagnostics checkbox defaults off. When enabled, diagnostics are sanitized and limited to app version/channel/git SHA, platform details, listener/capture status, local database and log sizes, row counts, and recent sanitized app log lines. Feedback diagnostics do not include raw Data Out packets, `telemetry_tracker.sqlite3`, exported telemetry files, raw/imported telemetry uploads, world-map cache image files, local game files, screenshots, user documents, personal files, GitHub credentials, or Cloudflare credentials.

The Ko-fi support link opens your browser only when clicked.

The desktop launcher performs local health checks against `127.0.0.1` to confirm the bundled backend is running.

## Sharing data

Do not attach telemetry databases, local game files, generated map-cache files, credentials, or private keys to public issues or feedback reports. If a maintainer asks for a sample, provide the smallest redacted file that reproduces the problem.

## Updates

If privacy-relevant behavior changes, this file and README.md should be updated in the same pull request.
