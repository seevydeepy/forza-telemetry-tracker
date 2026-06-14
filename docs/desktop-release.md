# Desktop Release Guide

## Release artifact

The user-facing artifact is `ForzaTelemetryTrackerSetup-vX.Y.Z-x64.exe`. Users do not install Python, Node, .NET, run PowerShell scripts, run `pip`, or start multiple programs.

The project currently publishes unsigned Windows installers. Windows SmartScreen may warn on first launch or install because unsigned binaries do not build publisher reputation.

## v1 scope

- Same-PC Forza Data Out only.
- Data Out target: IP `127.0.0.1`, port `5400`.
- Per-user install under `%LOCALAPPDATA%\Programs\Forza Telemetry Tracker`.
- User data under `%LOCALAPPDATA%\Forza Telemetry Tracker`.
- User-initiated update checks from the About window with manual download/install from GitHub Releases.
- Bundled WebView2 Evergreen Standalone installer.
- Bundled self-contained FH6 map tile converter.

## Build prerequisites for maintainers

- Python 3.12.
- Node.js and npm.
- .NET 9 SDK.
- Inno Setup with `iscc` on `PATH`.
- Microsoft WebView2 Evergreen Standalone installer downloaded locally.

## Local build

```powershell
powershell -ExecutionPolicy Bypass -File tools\build-desktop-release.ps1 `
  -Version 0.1.0-local `
  -WebView2StandaloneInstaller C:\ReleaseInputs\MicrosoftEdgeWebView2RuntimeInstallerX64.exe
```

Use `-SkipInstaller` for a local app-bundle build that does not require Inno Setup or WebView2 installer input, and `-SkipSmoke` only when the HTTP smoke test is not useful for the current packaging check.

## GitHub release build

Stable releases are produced by pushing an annotated or lightweight SemVer tag:

```powershell
git tag v1.2.3
git push origin v1.2.3
```

The `.github/workflows/desktop-release.yml` workflow:

1. validates that the tag matches `vX.Y.Z`;
2. runs the frontend tests/build, Python tests, .NET map converter publish, PyInstaller app build, Inno Setup compile, and smoke test;
3. embeds `build/release-metadata.json` into the packaged app;
4. uploads a GitHub Release containing:
   - `ForzaTelemetryTrackerSetup-vX.Y.Z-x64.exe`
   - `ForzaTelemetryTrackerSetup-vX.Y.Z-x64.exe.sha256`

The build job needs no code-signing secrets or certificate configuration. The release publishing job grants `contents: write` only so it can create the GitHub Release.

## About window and updates

The About window is opened from the left slide-out menu. It shows installed build metadata from `/api/app/about`:

- version,
- release date,
- Git SHA,
- repository,
- channel,
- packaging/update readiness.

Update checks are user-initiated only. The app checks GitHub Releases, ignores drafts and prereleases, and compares SemVer tags instead of publish dates.

For private-repository testing, configure a fine-grained GitHub PAT with repository-only `Contents: read`. Installed Windows builds store the token in Windows Credential Manager. Development runs can use the `FORZA_TRACKER_GITHUB_TOKEN` environment variable. Tokens are never returned by the API or logged by the app.

When a newer stable release exists, the About button changes from `Check for updates` to `Open release X.Y.Z`. The app opens the GitHub Release page in the user's browser. The user downloads the installer, optionally checks the attached SHA-256 file, closes the tracker, and runs the installer manually.

There is intentionally no automatic installer launch and no in-app executable verification path. That keeps the open-source release process free of mandatory paid code-signing infrastructure.

## Required validation

1. Install on Windows without Python, Node, or .NET available on `PATH`.
2. Verify WebView2-present install skips the bundled prerequisite.
3. Verify WebView2-missing install installs the bundled Evergreen runtime.
4. Launch from Start Menu.
5. Launch from Desktop shortcut when selected.
6. Verify no terminal window appears.
7. Verify `/api/status` responds during smoke testing.
8. Verify `/events` connects during smoke testing.
9. Send a sample Data Out UDP packet to `127.0.0.1:5400` and confirm receipt.
10. Record telemetry and confirm `telemetry_tracker.sqlite3` under `%LOCALAPPDATA%\Forza Telemetry Tracker`.
11. Build the world-map cache from a valid local FH6 media folder.
12. Confirm generated tiles under `%LOCALAPPDATA%\Forza Telemetry Tracker\map-cache`.
13. Close the app and verify HTTP and UDP ports are released.
14. Install an older build, configure a private release token if the repo is private, detect a newer stable release from About, open the GitHub Release link, and install the newer build manually.
15. Confirm update-check failure handling for invalid token, no network, missing checksum asset, prerelease ignored, and malformed release tags.
16. Install a newer build over an older build and confirm user data remains.
17. Uninstall and confirm app files are removed while user data remains.
