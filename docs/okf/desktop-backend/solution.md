# Desktop Backend

## Purpose

Python FastAPI desktop backend for local UDP telemetry capture, SQLite storage, lap/session analysis, export, replay, update checks, feedback submission, and FH6 world-map integration.

## Owned Paths

- telemetry_tracker/
- tests/
- tools/run-telemetry-tracker.py
- tools/capture-data-out.py
- tools/capture-session.py
- tools/parse-data-out.py
- tools/maintain-telemetry-db.py
- requirements-telemetry-tracker.txt
- requirements-telemetry-desktop.txt
- requirements-telemetry-test.txt

## Entrypoints

- `telemetry_tracker/app.py` exposes `create_app()` and the FastAPI routes for status, capture control, sessions, laps, replay/import, export jobs, feedback, diagnostics, update checks, track profiles, and world-map APIs.
- `telemetry_tracker/app.py` `CapturePipeline` wires raw packets through packet decoding, capture state, lap detection, storage, analysis, and live event publication.
- `telemetry_tracker/desktop_launcher.py` starts the packaged Windows desktop app: allocates the local HTTP port, starts the backend, resolves UDP port conflicts, opens pywebview, and exposes native file/folder selection.
- `tools/run-telemetry-tracker.py` is the development HTTP entrypoint for Uvicorn plus optional UDP listener startup.
- `tools/capture-data-out.py`, `tools/capture-session.py`, and `tools/parse-data-out.py` are raw FH Data Out capture/session/parse utilities.
- `tools/maintain-telemetry-db.py` prunes eligible non-race samples, checkpoints WAL, and optionally VACUUMs the SQLite database.

## Neighbouring Systems

- Web Dashboard (`web/telemetry-tracker/`) consumes these REST/SSE APIs, mounted static assets, and pywebview bridge selections.
- Feedback Worker receives reports submitted by the backend feedback client; backend owns local validation, diagnostics collection, queueing, and retry.
- FH6 Map Tile Converter is called from the world-map cache path; backend owns cache status, settings, tile serving, and converter invocation.
- Release, CI, and Packaging owns PyInstaller/Inno/metadata packaging around the backend launcher, requirements, and smoke checks.

## Key Internal Files

- `telemetry_tracker/storage.py`: SQLite schema, migrations, settings, sessions, laps, samples, track profiles, world-map records, feedback queue, and maintenance helpers.
- `telemetry_tracker/udp_listener.py`: async UDP socket lifecycle, packet-size validation, status events, and packet handler dispatch.
- `telemetry_tracker/packet_bridge.py` and `telemetry_tracker/data_out/`: FH Data Out packet schema, decoding, test encoding, raw packet iteration, capture summaries, and CSV/artifact writing.
- `telemetry_tracker/capture.py`, `lap_detection.py`, `lap_quality.py`, `ingest.py`: live capture state, auto/manual lap/session handling, quality decisions, and recent-sample ingestion.
- `telemetry_tracker/analysis.py`, `comparison.py`, `track_matcher.py`, `track_profiles.py`, `track_assets.py`: lap analysis, reference/ghost/delta data, track matching, route signatures, and uploaded track assets.
- `telemetry_tracker/export.py`, `replay.py`, `feedback.py`, `diagnostics.py`, `app_updates.py`, `world_map.py`: export/import jobs, raw replay, feedback, diagnostics, update checks, and map tile cache support.

## Maintenance Notes

- Keep this page focused on stable ownership, entrypoints, and contracts.
- Use `routing.md` for symptom/search routing details.
- Use the focused `tests/test_tracker_*.py` or `tests/test_capture_tool.py` file that matches the touched backend module or tool; broad backend changes normally route through `pytest tests`.
