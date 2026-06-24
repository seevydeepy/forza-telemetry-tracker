# Web Dashboard OKF Log

## Bootstrap

- Shallow OKF bundle created from repository structure.

## Deep Backfill

- Evidence: `package.json` declares the frontend as the local-first desktop app UI with `vite`, `vite build`, and `vitest run --environment jsdom` scripts.
- Evidence: `main.ts` mounts `App.svelte` into the `#app` element.
- Evidence: `App.svelte` imports API functions, major modal/panel components, `TelemetryCanvas`, `TelemetryDashboard`, `ReviewTimeline`, and `DashboardPlaybackBar`.
- Evidence: `App.svelte` opens `new EventSource('/events')`, loads initial status/live/session/world-map data, and renders route or dashboard mode from the same shell.
- Evidence: `api.ts` centralises `/api/status`, `/api/capture`, `/api/live/recent`, `/api/sessions`, `/api/laps`, `/api/replay/import-jobs`, `/api/telemetry/export-jobs`, `/api/map`, feedback, diagnostics, and app update calls.
- Evidence: `desktopBridge.ts` gates optional `window.pywebview.api` pickers for FH6 install folder, export folder, raw telemetry files, and raw telemetry folders.
- Evidence: `TelemetryCanvas.svelte` owns 2D canvas route rendering with overlays, markers, ghost samples, track assets, world-map tiles, pan/zoom, and point/issue selection events.
- Evidence: `TelemetryDashboard.svelte` composes the tach/speed/gear, inputs, tyres, suspension, accelerometer, lap timing, mini-route, fuel/race, and car-details dashboard widgets.

## Known Gaps

- Backend API, SSE, pywebview provider, storage, map cache, import/export, feedback, and diagnostics implementations were not inspected because this backfill was scoped to `web/telemetry-tracker/`.
