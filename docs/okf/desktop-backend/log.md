# Desktop Backend OKF Log

## Bootstrap

- Shallow OKF bundle created from repository structure.

## 2026-06-25 Deep Backfill

- Confirmed backend root in `telemetry_tracker/app.py`: `CapturePipeline`, `create_app()`, and FastAPI routes cover status, world-map cache build, feedback reports, export jobs, replay/import jobs, and SSE events.
- Confirmed desktop/runtime entrypoints: `telemetry_tracker/desktop_launcher.py` defines `DesktopBackend`, `DesktopBridge`, smoke HTTP mode, desktop launch, and `main()`; `tools/run-telemetry-tracker.py` creates the app and starts Uvicorn after checking HTTP/UDP port conflicts.
- Confirmed raw capture and session tools: `tools/capture-data-out.py` writes capture artifacts from active FH Data Out packets and rejects reserved ports 5200-5300; `tools/capture-session.py` starts/stops background capture by invoking `tools/capture-data-out.py` and tracks new capture analysis state.
- Confirmed SQLite ownership: `telemetry_tracker/storage.py` has `SCHEMA_VERSION = 12`, `TelemetryStore`, migrations, database-size helpers, session/lap APIs, and packet/sample batch insertion.
- Confirmed packet/listener boundary: `telemetry_tracker/data_out/__init__.py` defines `PACKET_SIZE = 324`, decoding, test encoding, raw packet iteration, capture classification, artifact writing, and latest-pointer writing; `telemetry_tracker/udp_listener.py` validates datagram size before dispatching packets.
- Confirmed dependencies: `requirements-telemetry-tracker.txt` owns FastAPI, Uvicorn, httpx, and multipart runtime; `requirements-telemetry-desktop.txt` adds PyInstaller and pywebview; `requirements-telemetry-test.txt` adds pytest.
- Confirmed test routing: `tests/test_tracker_*.py` files exercise backend modules and API surfaces with `TelemetryStore`, `create_app()`, `TestClient`, and module-specific helpers; `tests/test_capture_tool.py`, `test_tracker_runner.py`, `test_tracker_maintenance_tool.py`, and `test_tracker_desktop_launcher.py` cover the owned tools and launcher.

## Known Gaps

- API contract details remain in source/tests rather than duplicated here; update this bundle only when ownership, entrypoints, or routing changes.
