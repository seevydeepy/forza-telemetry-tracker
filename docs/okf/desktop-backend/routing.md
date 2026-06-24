# Desktop Backend Routing

## Read This When

- A change touches one of this solution's owned paths.
- A symptom matches one of this solution's routing keywords.

## First Files To Inspect

- `docs/okf/desktop-backend/routing_guidance.card`
- `docs/okf/desktop-backend/solution.md`
- `telemetry_tracker/app.py`
- `telemetry_tracker/storage.py`
- `telemetry_tracker/desktop_launcher.py`
- `tools/run-telemetry-tracker.py`

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

## Symptoms And Search Terms

- fastapi
- udp
- data out
- sqlite
- capture
- lap
- session
- export
- replay
- world map
- update check
- feedback client
- pywebview
- port conflict
- raw import
- export job
- sse

## Symptom Routing

- Backend route, HTTP status, API payload, validation, CORS/static serving, REST/SSE event, import/export job, replay, feedback, diagnostics, update check, track profile, or world-map API issue: start in `telemetry_tracker/app.py`, then follow the imported service module.
- Live telemetry missing or listener status wrong: inspect `telemetry_tracker/udp_listener.py`, `telemetry_tracker/packet_bridge.py`, `telemetry_tracker/capture.py`, `telemetry_tracker/lap_detection.py`, and `telemetry_tracker/ingest.py`.
- SQLite schema, migration, stored settings, session/lap/sample query, feedback queue, track profile, map tile record, or database maintenance issue: inspect `telemetry_tracker/storage.py` and `tools/maintain-telemetry-db.py`.
- Packaged desktop startup, pywebview bridge, folder/file picker, user-data path, backend readiness, or UDP port conflict issue: inspect `telemetry_tracker/desktop_launcher.py`, `telemetry_tracker/app_paths.py`, and `telemetry_tracker/port_conflicts.py`.
- Development server startup issue: inspect `tools/run-telemetry-tracker.py`, then `telemetry_tracker/app.py` and `telemetry_tracker/storage.py`.
- Raw FH Data Out packet, parser, capture artifact, latest pointer, capture session, or CLI capture issue: inspect `telemetry_tracker/data_out/`, `tools/capture-data-out.py`, `tools/capture-session.py`, and `tools/parse-data-out.py`.
- Lap analysis, markers, collision/smashable detection, reference lap, ghost, delta, or comparison issue: inspect `telemetry_tracker/analysis.py`, `collision_detection.py`, `comparison.py`, `lap_summaries.py`, and matching API routes in `app.py`.
- Track matching, route signatures, track assets, car catalogue, or local FH6 media scan issue: inspect `telemetry_tracker/track_matcher.py`, `track_profiles.py`, `track_assets.py`, `track_catalog.py`, `car_catalog.py`, and `car_info.py`.
- World-map tile cache, season, calibration, tile serving, or converter subprocess issue: inspect `telemetry_tracker/world_map.py`; hand off converter implementation defects to `fh6-map-tile-converter`.
- Feedback submission, diagnostics payload, pending retry, or worker rejection issue: inspect `telemetry_tracker/feedback.py`, `telemetry_tracker/diagnostics.py`, and backend feedback routes; hand off remote worker/API defects to `feedback-worker`.
- Test failure under `tests/test_tracker_*.py`: route by the module named in the test filename first, then the API/tool entrypoint used by the test.

## Handoffs

- Web Dashboard owns frontend behaviour under `web/telemetry-tracker/`; keep backend payload/API contract changes coordinated there.
- Feedback Worker owns the remote Cloudflare Worker and D1 intake; backend owns local validation, diagnostics, queueing, and retry.
- FH6 Map Tile Converter owns converter internals under `tools/fh6-map-tile-converter/`; backend owns invocation, cache metadata, settings, and tile serving.
- Release, CI, and Packaging owns installer/release workflow and packaged smoke tooling; backend owns the runtime launcher code and requirements listed in this bundle.
