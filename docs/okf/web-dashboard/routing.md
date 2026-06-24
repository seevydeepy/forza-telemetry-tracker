# Web Dashboard Routing

## Read This When

- A change touches `web/telemetry-tracker/`.
- A symptom appears in the desktop embedded web UI, Vite dev UI, telemetry canvas, dashboard widgets, modals, import/export flows, or pywebview picker handling.
- A frontend error mentions `/api/*`, `/events`, `EventSource`, `pywebview`, Svelte, Vite, Vitest, canvas rendering, route review, or dashboard playback.

## First Files To Inspect

- `web/telemetry-tracker/src/App.svelte` for workflow state, API orchestration, SSE connection, live/replay mode, modals, and top-level composition.
- `web/telemetry-tracker/src/api.ts` for endpoint names, request bodies, response types, and error messages.
- `web/telemetry-tracker/src/types.ts` for frontend payload shape expectations.
- `web/telemetry-tracker/src/desktopBridge.ts` for native file/folder picker availability and normalisation.
- `web/telemetry-tracker/src/TelemetryCanvas.svelte` for route rendering, overlays, markers, ghosts, track assets, world-map tiles, pan/zoom, and point selection.
- `web/telemetry-tracker/src/TelemetryDashboard.svelte` and `web/telemetry-tracker/src/Dashboard*.svelte` for dashboard widget display.
- `web/telemetry-tracker/vite.config.ts` and `web/telemetry-tracker/package.json` for frontend build/test/dev-server issues.

## Owned Paths

- `web/telemetry-tracker/`

## Symptoms And Search Terms

- Blank or stale UI: `main.ts`, `App.svelte`, `recoverAndConnect`, `fetchStatus`, `fetchRecentLiveSamples`, `EventSource`, `/events`.
- API request failure: `api.ts`, endpoint path, `expectJson`, displayed error text.
- Capture controls or listener status wrong: `CaptureControls`, `FloatingCaptureControls`, `fetchCaptureStatus`, `setCaptureMode`, `startCapture`, `stopCapture`.
- Route visualisation wrong: `TelemetryCanvas.svelte`, `OverlayToolbar`, `ReviewTimeline`, `ghostSamples`, `markers`, `selectedRange`, `worldMapTileSet`.
- Dashboard widgets wrong: `CanvasModeToggle`, `TelemetryDashboard.svelte`, `DashboardPlaybackBar`, `dashboardPlayback.ts`, `dashboardWidgets.ts`.
- Import/export issue: `ImportTelemetryModal`, `ExportTelemetryModal`, `fetchRawTelemetryImportJobs`, `fetchTelemetryExportJobs`, `desktopBridge.ts`.
- Map setup/cache issue: `WorldMapSetupPanel`, `WorldMapSettingsPanel`, `WorldMapInstallLocationField`, `worldMap.ts`, `/api/map`.
- Native picker missing: `desktopBridge.ts`, `pywebview`, `choose_fh6_install_folder`, `choose_export_folder`, `choose_raw_telemetry_files`, `choose_raw_telemetry_folder`.
- Feedback, about, diagnostics, or update UI issue: `FeedbackModal`, `AboutModal`, `DiagnosticsPanel`, `/api/feedback`, `/api/app`, `/api/diagnostics`.
- CSS/layout regression: `app.css`, component-local `<style>`, matching `*.test.ts` style/layout tests.

## Handoffs

- Desktop Backend: route there when frontend calls are correct but `/api/*` or `/events` data, status codes, payload shape, `window.pywebview.api`, summaries, markers, ghosts, track profiles, world-map tiles, imports, exports, or diagnostics are wrong.

## Known Gaps

- This backfill only inspected `web/telemetry-tracker/`; backend route/provider files were not re-mapped here.
- Component-level ownership inside the frontend is broad; use the first-file list before editing scattered widget files.
