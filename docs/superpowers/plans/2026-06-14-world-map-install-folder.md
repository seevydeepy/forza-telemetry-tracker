# World Map Install Folder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. For eligible non-work repositories, use enabled ask-mimo as the default fast read-only checkpoint for non-trivial plans, meaningful implementation diffs, debugging conclusions, and final outputs; subagents should use one focused end-of-task Ask MiMo check before returning non-trivial work. Use ask-claude only from the orchestrator when MiMo is unavailable or deeper Claude review is more appropriate. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change FH6 world-map setup/settings to accept only the top-level install folder and discover map assets under its `media` child.

**Architecture:** Keep the existing storage/API field `fh6_media_root` to avoid schema churn, but introduce world-map helper functions that resolve a configured install root to its `media` directory. Reuse `AppModal` for the first-run setup surface and reuse the same install-location label/help UI in both setup and settings panels.

**Tech Stack:** Python/FastAPI backend, SQLite storage, Svelte frontend, Vitest/jsdom frontend tests, pytest backend tests.

---

### Task 1: Backend Install-Root Resolution

**Files:**
- Modify: `telemetry_tracker/world_map.py`
- Test: `tests/test_tracker_world_map.py`

- [ ] **Step 1: Add failing backend tests**

Add tests that pass the install root returned by `_make_media_root(root).parent` and assert `season_source_zip()` resolves through the `media` child. Add a test that passes the direct `media` folder into `build_world_map_cache()` and expects `source_missing`.

- [ ] **Step 2: Run the backend test and confirm failure**

Run: `python -m pytest tests/test_tracker_world_map.py -q`

Expected before implementation: failures showing source lookup still assumes the configured path is the media folder.

- [ ] **Step 3: Implement install-root helpers**

Add helper functions in `telemetry_tracker/world_map.py`:

```python
def resolve_media_root(install_root: Path) -> Path:
    root = Path(install_root).expanduser()
    if root.name.lower() == "media":
        return root / "__invalid_direct_media_folder__"
    return root / "media"
```

Use `resolve_media_root()` in `season_source_zip()`, `load_map_calibration()`, `build_world_map_cache()`, and `world_map_status_payload()` so source and calibration paths look under `<install root>/media`.

- [ ] **Step 4: Run backend tests**

Run: `python -m pytest tests/test_tracker_world_map.py tests/test_tracker_storage.py::TelemetryStoreTests::test_update_world_map_settings_persists_normalized_values -q`

Expected: all selected tests pass.

### Task 2: Setup Modal UI

**Files:**
- Modify: `web/telemetry-tracker/src/WorldMapSetupPanel.svelte`
- Create: `web/telemetry-tracker/src/WorldMapInstallLocationField.svelte`
- Modify: `web/telemetry-tracker/src/app.css`
- Test: `web/telemetry-tracker/src/App.test.ts`

- [ ] **Step 1: Update tests for modal behavior**

Change first-run setup tests to query `role="dialog"` with name `World Map Setup`, verify the input label `FH6 Local Install Location`, the placeholder `e.g. C:\SteamLibrary\steamapps\common\ForzaHorizon6`, and the install-folder copy.

- [ ] **Step 2: Run the focused frontend tests and confirm failure**

Run: `npm test -- --run src/App.test.ts -t "world map"`

Expected before implementation: tests fail because the setup is still a stage region with old copy and label.

- [ ] **Step 3: Wrap setup in `AppModal`**

Import `AppModal`, remove the custom setup header, render:

```svelte
<AppModal title="World Map Setup" on:close={() => dispatch('close')}>
  <section class="world-map-setup-panel" aria-label="FH6 world map setup">
    ...
  </section>
</AppModal>
```

Keep the existing ready/error event behavior unchanged.

- [ ] **Step 4: Add label help popover**

Add local state for `helpOpen`, `helpX`, and `helpY`. Add an `IconButton icon="help"` next to the label text. On click, position the popover from `event.clientX/clientY` or the button bounds. Render a fixed `.world-map-location-help-popover` containing the four ordered steps and final sentence.

- [ ] **Step 5: Remove obsolete floating setup styles**

Update `app.css` so `.world-map-setup-panel` is an unpositioned grid inside the modal, and keep the status/actions styles.

- [ ] **Step 6: Run focused frontend tests**

Run: `npm test -- --run src/App.test.ts -t "world map"`

Expected: selected frontend tests pass.

### Task 3: Settings Panel Parity

**Files:**
- Modify: `web/telemetry-tracker/src/WorldMapSettingsPanel.svelte`
- Create: `web/telemetry-tracker/src/WorldMapInstallLocationField.svelte`
- Modify: `web/telemetry-tracker/src/app.css`
- Test: `web/telemetry-tracker/src/App.test.ts`

- [ ] **Step 1: Update settings tests**

Assert the settings dialog contains the updated label and install-folder copy. Add a click on the help icon and verify the Task Manager steps are visible.

- [ ] **Step 2: Implement the same label/help UI**

Use the same label row, `IconButton icon="help"`, placeholder, and popover behavior in `WorldMapSettingsPanel.svelte`. Keep save/build request payloads unchanged except values now represent install roots.

- [ ] **Step 3: Run settings-focused frontend tests**

Run: `npm test -- --run src/App.test.ts -t "settings"`

Expected: selected tests pass.

### Task 4: Final Validation And Commit

**Files:**
- Review all changed files.

- [ ] **Step 1: Run targeted backend validation**

Run: `python -m pytest tests/test_tracker_world_map.py tests/test_tracker_storage.py::TelemetryStoreTests::test_update_world_map_settings_persists_normalized_values -q`

Expected: all selected backend tests pass.

- [ ] **Step 2: Run targeted frontend validation**

Run: `npm test -- --run src/App.test.ts -t "world map|settings"`

Expected: all selected frontend tests pass.

- [ ] **Step 3: Build frontend**

Run: `npm run build`

Expected: Vite build succeeds.

- [ ] **Step 4: Ask MiMo for diff review if enabled**

Provide a compact diff/test evidence packet and ask for correctness risks, missed duplicated labels, and test gaps. Apply only verified useful feedback.

- [ ] **Step 5: Commit and merge back**

Commit the focused implementation in the isolated worktree, merge it into the original `master` checkout, then remove the worktree if safe.
