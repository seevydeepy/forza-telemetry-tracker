# Web Dashboard

## Purpose

Svelte/Vite frontend for the local Forza Telemetry Tracker app. It presents live capture status, route visualisation, dashboard widgets, replay/session review, map overlays, diagnostics, feedback, import/export jobs, and settings.

## Owned Paths

- `web/telemetry-tracker/`

## Key Entrypoints

- `web/telemetry-tracker/src/main.ts` mounts the Svelte app into `#app`.
- `web/telemetry-tracker/src/App.svelte` is the main orchestration surface for API loading, SSE connection, capture controls, modals, route/dashboard mode, session/lap selection, import/export jobs, diagnostics, and toasts.
- `web/telemetry-tracker/src/api.ts` centralises frontend HTTP calls to `/api/*`.
- `web/telemetry-tracker/src/desktopBridge.ts` wraps optional `window.pywebview.api` native picker calls.
- `web/telemetry-tracker/vite.config.ts` defines the Vite/Svelte build, Vitest setup, and dev proxy for `/api` and `/events`.

## Neighbouring Systems

- Backend API owns the `/api/*` contracts consumed by `api.ts`; change both sides when payload shape, endpoint name, or error handling changes.
- Backend event stream owns `/events`; frontend reconnect, sample ingestion, and toast behaviour live in `App.svelte`.
- Desktop host owns `window.pywebview.api` picker methods used by `desktopBridge.ts`.
- Telemetry storage, analysis, track profiles, world-map cache, feedback, diagnostics, import, and export systems feed this UI through API payloads rather than direct frontend ownership.

## Maintenance Notes

- Start with `App.svelte` for workflow bugs, then narrow to the component, helper, test, or API wrapper named by the symptom.
- Keep UI copy/layout changes in Svelte/CSS files and contract changes in `api.ts`/`types.ts` with matching backend verification.
- Use `routing.md` for symptom/search routing details.
