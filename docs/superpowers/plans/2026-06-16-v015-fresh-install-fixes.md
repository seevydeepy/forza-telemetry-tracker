# v0.1.5 Fresh Install Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. For eligible non-work repositories, use enabled ask-mimo as the default fast read-only checkpoint for non-trivial plans, meaningful implementation diffs, debugging conclusions, and final outputs; subagents should use one focused end-of-task Ask MiMo check before returning non-trivial work. Use ask-claude only from the orchestrator when MiMo is unavailable or deeper Claude review is more appropriate. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship v0.1.5 with the fresh-install, update-readiness, Windows chrome, map-cache, sidebar, status bar, feedback, and Ko-fi fixes reported against v0.1.4.

**Architecture:** Keep the fix split between runtime/packaging and frontend UI. Runtime owns packaged metadata loading, Windows process/window behavior, and installer metadata; frontend owns startup session state, drawer behavior, menu/support controls, and status strip layout. The release workflow remains the publishing path, with release notes verified and enriched after the tag build completes.

**Tech Stack:** Python 3.12/FastAPI/PyInstaller/Inno Setup, PowerShell release tooling, Svelte/Vite/Vitest, GitHub Actions/GitHub Releases.

---

### Task 1: Runtime And Packaging Fixes

**Files:**
- Modify: `telemetry_tracker/app_metadata.py`
- Modify: `tools/build-desktop-release.ps1`
- Modify: `packaging/installer/forza-telemetry-tracker.iss`
- Modify: `telemetry_tracker/desktop_launcher.py`
- Modify: `telemetry_tracker/world_map.py`
- Test: `tests/test_tracker_app_updates.py`
- Test: `tests/test_tracker_desktop_launcher.py`
- Test: `tests/test_tracker_world_map.py`

- [x] Load `release-metadata.json` with `utf-8-sig` so existing BOM-prefixed packaged metadata parses as stable SemVer.
- [x] Write release metadata from PowerShell without a UTF-8 BOM.
- [x] Add an app icon to Inno Setup and assign it explicitly to Start Menu/Desktop shortcuts.
- [x] Add guarded Windows subprocess creation flags so the map converter does not show a console window.
- [x] Set pywebview startup size to at least `1600x900` and set a dark startup background.
- [x] Run `python -m pytest tests/test_tracker_app_updates.py tests/test_tracker_desktop_launcher.py tests/test_tracker_world_map.py`.

### Task 2: Frontend UI Fixes

**Files:**
- Modify: `web/telemetry-tracker/src/App.svelte`
- Modify: `web/telemetry-tracker/src/StatusStrip.svelte`
- Modify: `web/telemetry-tracker/src/SlideOutMenu.svelte`
- Modify: `web/telemetry-tracker/src/AboutModal.svelte`
- Modify: `web/telemetry-tracker/src/app.css`
- Modify: `web/telemetry-tracker/index.html`
- Test: `web/telemetry-tracker/src/App.test.ts`
- Test: `web/telemetry-tracker/src/StatusStrip.test.ts`
- Test: `web/telemetry-tracker/src/AboutModal.test.ts`

- [x] Start with no loaded session and a collapsed history drawer during initial recovery.
- [x] Open the history drawer whenever a session is loaded by user action or live-session flow.
- [x] Collapse the history drawer when the loaded session is cleared or deleted.
- [x] Make fixed status sections non-growing and width-stable, with only `Last event` flexing into remaining space.
- [x] Add a bottom-pinned GitHub Issues feedback link to the main menu, using the existing icon fallback if no provided feedback asset is available.
- [x] Restore an external-image Ko-fi support button in About.
- [x] Declare frontend color scheme metadata/CSS for better host chrome/theme integration.
- [x] Run `npm test -- --run src/AboutModal.test.ts src/StatusStrip.test.ts src/App.test.ts`.

### Task 3: Integration, Review, And Release

**Files:**
- Review all changed files from Tasks 1 and 2.
- Modify release notes through GitHub Release metadata after the workflow publishes v0.1.5 if needed.

- [x] Inspect the combined diff for requirement coverage and accidental cross-slice regressions.
- [x] Run full Python tests: `python -m pytest`.
- [x] Run frontend tests/build: `npm test` and `npm run build` from `web/telemetry-tracker`.
- [x] Run or build the desktop release path enough to prove metadata, bundled app smoke, and installer assets are correct.
- [x] Use Ask MiMo for a final read-only diff/requirement review and record the outcome.
- [ ] Commit the focused implementation in the worktree.
- [ ] Merge the commit back to `master`.
- [ ] Push `master`, tag `v0.1.5`, monitor GitHub Actions, verify release assets, and update release notes with concrete bullets.
