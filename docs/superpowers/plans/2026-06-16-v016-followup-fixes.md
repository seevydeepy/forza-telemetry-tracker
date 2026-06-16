# v0.1.6 Follow-Up Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. For eligible non-work repositories, use enabled ask-mimo as the default fast read-only checkpoint for non-trivial plans, meaningful implementation diffs, debugging conclusions, and final outputs; subagents should use one focused end-of-task Ask MiMo check before returning non-trivial work. Use ask-claude only from the orchestrator when MiMo is unavailable or a deeper Claude consult is more appropriate. For `svn_master_*` work repositories, use Cursor delegation where work-repo guidance calls for it. Final implementation review should follow superpowers:requesting-code-review / Ask MiMo / Ask Claude policy. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship v0.1.6 with the requested feedback icon, modal/popover dismissal fixes, lap-summary first-load behavior, native picker coverage for import/export, launcher console mitigation, validation, and public release notes.

**Architecture:** Reuse existing shared UI primitives where possible instead of duplicating behavior. Extend the desktop bridge with narrow picker methods and add a path-based raw import job API only for native desktop selections, while preserving browser upload fallbacks. Treat launcher console changes as evidence-driven packaging/runtime fixes, not speculative churn.

**Tech Stack:** Svelte/Vite/Vitest, Python 3.12/FastAPI/pytest, pywebview, PyInstaller/Inno Setup, PowerShell release tooling, GitHub Releases.

---

### Task 1: Plan And Routing

**Files:**
- Create: `docs/superpowers/plans/2026-06-16-v016-followup-fixes.md`

- [x] Save this approved plan document in the isolated worktree.
- [x] Use `git status --short --branch` to confirm the branch is `codex/v016-followup-fixes` and the only change is the plan before implementation.
- [x] Spawn only bounded sidecar agents whose work can run without blocking the local critical path; keep final accountability local.

### Task 2: Feedback Icon And Diagnostics Modal

**Files:**
- Modify: `web/telemetry-tracker/src/Icon.svelte`
- Modify: `web/telemetry-tracker/src/SlideOutMenu.svelte`
- Modify: `web/telemetry-tracker/src/DiagnosticsPanel.svelte`
- Modify: `web/telemetry-tracker/src/App.test.ts`
- Maybe modify: `web/telemetry-tracker/src/app.css`

- [x] Add a `feedback` icon to `Icon.svelte` using the path from `D:/Downloads/feedback_24dp_E3E3E3_FILL1_wght400_GRAD0_opsz24(1).svg`.
- [x] Replace the slide-out Feedback link icon from `help` to `feedback`.
- [x] Refactor `DiagnosticsPanel.svelte` to render inside `AppModal title="Diagnostics"` and remove its custom outer backdrop/panel/focus trap.
- [x] Keep Diagnostics-specific content, refresh action, delete-confirm action, and delete-confirm outside-click dismissal.
- [x] Use `IconButton icon="refresh"` or add a Material refresh icon if the refresh control needs to remain icon-only; rely on AppModal for the close icon.
- [x] Remove or neutralize obsolete `.diagnostics-backdrop` centering/top-right CSS after the AppModal migration.
- [x] Update diagnostics tests to prove the dialog is still named `Telemetry diagnostics` or adjust accessible naming consistently across test and implementation, then prove backdrop click dismisses the Diagnostics modal and underlying dashboard controls do not receive that click.

### Task 3: Help Popover And Lap Summary State

**Files:**
- Modify: `web/telemetry-tracker/src/WorldMapInstallLocationField.svelte`
- Modify: `web/telemetry-tracker/src/App.svelte`
- Modify: `web/telemetry-tracker/src/App.test.ts`

- [x] Add document-level outside-click dismissal for the FH6 install help popover.
- [x] Do not dismiss the popover when the click target is inside the popover body or the help trigger.
- [x] Preserve the existing `pywebviewready` listener and native FH6 install picker availability behavior.
- [x] Initialize the section summary card hidden when no lap summary is available.
- [x] Track whether the summary card has been auto-shown once and whether the user has explicitly toggled/closed it.
- [x] When `selectedLapSummary` first transitions from `null` to a summary and the user has not touched the card, set `summaryCardVisible = true` and mark the one-time auto-show complete.
- [x] In `hideSummaryCard` and `toggleSummaryCard`, mark the summary as user-touched so later summary loads do not override user actions.
- [x] Keep `resetFloatingPanelsAndLayout` as an explicit layout reset that sets the card visible and clears the manual-touched state.
- [x] Add or update tests for initial hidden state, first summary auto-show, user hide persistence, and reset layout behavior.

### Task 4: Native Picker Bridge And Raw Import API

**Files:**
- Modify: `web/telemetry-tracker/src/desktopBridge.ts`
- Modify: `web/telemetry-tracker/src/ImportTelemetryModal.svelte`
- Modify: `web/telemetry-tracker/src/ExportTelemetryModal.svelte`
- Modify: `web/telemetry-tracker/src/api.ts`
- Modify: `web/telemetry-tracker/src/types.ts`
- Modify: `telemetry_tracker/desktop_launcher.py`
- Modify: `telemetry_tracker/app.py`
- Modify: `tests/test_tracker_desktop_launcher.py`
- Modify/add frontend modal tests as needed.
- Modify/add backend app tests as needed.

- [x] Extend `DesktopBridge` with native folder/file picker methods for export output folder, raw telemetry files, and raw telemetry folder.
- [x] In `desktopBridge.ts`, expose capability and chooser helpers that return trimmed strings or string arrays and return `null`/`[]` on cancel or unavailable bridge methods.
- [x] Keep the existing FH6-specific helper as a compatibility wrapper over the same bridge style.
- [x] For export, add a Browse button when the native folder picker is available; selecting a folder fills the existing output folder text input. The manual text input remains the fallback and remains editable.
- [x] For import, prefer a combined native import picker only if pywebview supports one dialog that can choose either files or a folder. If it does not, keep separate native file/files and folder Browse actions plus the existing browser file/folder fallback inputs.
- [x] Add a JSON background import endpoint, for example `POST /api/replay/import-jobs/paths`, accepting validated `file_paths`, optional `folder_path`, `label`, and `source_type`.
- [x] Validate native path imports with explicit rules: required path, existing file/folder, no directories in `file_paths`, recursive folder enumeration bounded by `RAW_TELEMETRY_IMPORT_MAX_FILES`, per-file and total-size limits, deterministic display names, permission errors returned as job errors or 400s as appropriate, and no deletion of user-selected source files.
- [x] Update `RawTelemetryImportJob` cleanup so uploaded jobs still remove temporary staging directories, while path-based jobs never remove selected source paths.
- [x] Update frontend import dispatch to support either browser `File[]` upload jobs or native path jobs and keep the old upload flow unchanged for web/fallback use.
- [x] Add tests for desktop bridge dialog methods, export Browse behavior, native import path job creation, browser fallback preservation, backend path validation, and non-destructive cleanup semantics.

### Task 5: Launcher Console Flash

**Files:**
- Inspect/modify: `telemetry_tracker/desktop_launcher.py`
- Inspect/modify: `packaging/pyinstaller/forza-telemetry-tracker.spec`
- Inspect/modify: `packaging/installer/forza-telemetry-tracker.iss`
- Maybe modify: release/build scripts under `tools/`
- Test: `tests/test_tracker_desktop_launcher.py`

- [x] Confirm PyInstaller still uses `console=False`.
- [x] Search launcher and release scripts for `subprocess`, `os.system`, `cmd /c`, `CREATE_NEW_CONSOLE`, or other console-spawning paths involved in normal tracker startup.
- [x] Check installer `[Run]` behavior and desktop/start-menu shortcuts for shelling through a console host.
- [x] If a concrete console source exists, fix it with Windows no-window process flags or installer shortcut/run flags that still launch the GUI.
- [x] If no production console source exists and the flash is only from developer `python`/PowerShell launch paths, document that the packaged executable is already windowed and avoid risky speculative changes.
- [x] Add any practical unit test that locks in the discovered fix.

### Task 6: Version, Validation, Review, And Release

**Files:**
- Modify: `telemetry_tracker/__init__.py`
- Modify: any release metadata or docs needed for v0.1.6.

- [x] Bump the package version to `0.1.6`.
- [x] Run focused frontend tests around App, import/export modals, and diagnostics.
- [x] Run focused Python tests for desktop launcher and raw import path jobs.
- [x] Run full frontend build/test and Python test suite or the repo's established release validation path.
- [x] Run an Ask MiMo final read-only diff review and record the outcome.
- [ ] Commit the focused implementation.
- [ ] Merge the worktree branch back to the original `master` checkout.
- [ ] Push `master`, create/push tag `v0.1.6`, monitor GitHub Actions, verify release assets, and publish/update release notes with concrete user-facing bullets.
