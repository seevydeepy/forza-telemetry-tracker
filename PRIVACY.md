# Privacy

Forza Telemetry Tracker is a local-first Windows desktop tool.

## Local data

The app stores telemetry sessions, settings, logs, generated map cache files, imports, exports, and related metadata under `%LOCALAPPDATA%\Forza Telemetry Tracker` by default.

The main database is `telemetry_tracker.sqlite3`. SQLite may also create sidecar files such as `telemetry_tracker.sqlite3-wal` and `telemetry_tracker.sqlite3-shm`.

World-map cache files are generated locally from a valid local game install folder that you choose. The repository and release artifacts do not include local game files or generated map-cache files.

## Network behavior

The app does not include analytics, crash reporting, tracking pixels, advertising SDKs, user accounts, or telemetry upload behavior.

The About window checks public GitHub Releases only when you click `Check for updates`. That request fetches release metadata from GitHub and does not send telemetry sessions or local app data.

The Ko-fi support link opens your browser only when clicked.

The desktop launcher performs local health checks against `127.0.0.1` to confirm the bundled backend is running.

## Sharing data

Do not attach telemetry databases, local game files, generated map-cache files, credentials, or private keys to public issues. If a maintainer asks for a sample, provide the smallest redacted file that reproduces the problem.

## Updates

If privacy-relevant behavior changes, this file and README.md should be updated in the same pull request.
