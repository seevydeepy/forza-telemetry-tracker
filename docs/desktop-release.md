# Desktop Release Guide

## Release artifact

The user-facing artifact is `ForzaTelemetryTrackerSetup-vX.Y.Z-x64.exe`. Users do not install Python, Node, .NET, run PowerShell scripts, run `pip`, or start multiple programs.

## v1 scope

- Same-PC Forza Data Out only.
- Data Out target: IP `127.0.0.1`, port `5400`.
- Per-user install under `%LOCALAPPDATA%\Programs\Forza Telemetry Tracker`.
- User data under `%LOCALAPPDATA%\Forza Telemetry Tracker`.
- User-initiated in-app updates from the About window.
- Bundled WebView2 Evergreen Standalone installer.
- Bundled self-contained FH6 map tile converter.
- Bundled updater helper executable.

## Build prerequisites for maintainers

- Python 3.12.
- Node.js and npm.
- .NET 9 SDK.
- Inno Setup with `iscc` on `PATH`.
- Windows SDK `signtool.exe` for local signed builds only.
- SSL.com IV Code Signing + eSigner credentials for GitHub Actions signed releases.
- Microsoft WebView2 Evergreen Standalone installer downloaded locally.

## Unsigned local build

```powershell
powershell -ExecutionPolicy Bypass -File tools\build-desktop-release.ps1 -Version 0.1.0-local -SkipSigning
```

## Local signed build

```powershell
powershell -ExecutionPolicy Bypass -File tools\build-desktop-release.ps1 `
  -Version 0.1.0 `
  -Channel stable `
  -Repository seevydeepy/forza-telemetry-tracker `
  -TrustedSignerThumbprints "SHA256_CERT_THUMBPRINT" `
  -WebView2StandaloneInstaller C:\ReleaseInputs\MicrosoftEdgeWebView2RuntimeInstallerX64.exe `
  -SignToolPath "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe" `
  -CertificateSubject "Forza Telemetry Tracker" `
  -TimestampUrl "http://timestamp.digicert.com"
```

## GitHub release build

Stable releases are produced by pushing an annotated or lightweight SemVer tag:

```powershell
git tag v1.2.3
git push origin v1.2.3
```

The `.github/workflows/desktop-release.yml` workflow:

1. validates that the tag matches `vX.Y.Z`;
2. runs the frontend tests/build, Python tests, .NET map converter publish, PyInstaller app build, updater helper build, Inno Setup compile, and smoke test;
3. embeds `build/release-metadata.json` into the packaged app;
4. signs project-owned executables and the installer through SSL.com eSigner;
5. verifies Authenticode status for signed artifacts;
6. uploads a GitHub Release containing:
   - `ForzaTelemetryTrackerSetup-vX.Y.Z-x64.exe`
   - `ForzaTelemetryTrackerSetup-vX.Y.Z-x64.exe.sha256`

Required repository configuration:

- GitHub Actions secrets:
  - `ES_USERNAME`
  - `ES_PASSWORD`
  - `ES_CREDENTIAL_ID`
  - `ES_TOTP_SECRET`
  - optional `ES_ENVIRONMENT_NAME` (`PROD` by default)
- GitHub Actions variable:
  - `FORZA_TRUSTED_SIGNER_THUMBPRINTS`: comma-separated SHA-256 certificate thumbprints trusted by the app updater.

The workflow grants `contents: write` only to the release publishing job.

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

When a newer stable release exists, the About button changes from `Check for updates` to `Update to X.Y.Z`. The app then:

1. asks the user to confirm restart/install;
2. refuses while telemetry capture is active;
3. downloads the installer under `%LOCALAPPDATA%\Forza Telemetry Tracker\updates`;
4. verifies download size, SHA-256 checksum, Authenticode validity, and signer thumbprint allowlist;
5. launches `ForzaTelemetryTrackerUpdater.exe` from a temporary copy;
6. closes the app;
7. runs the Inno installer silently;
8. relaunches the app if installation succeeds.

Certificate rotation requires a bridge release that trusts both old and new signer thumbprints. Code signing improves Windows trust and enables updater verification, but it does not guarantee SmartScreen warnings disappear immediately.

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
14. Install an older signed build, configure a private release token if the repo is private, detect a newer stable release from About, run the in-app update, and confirm relaunch on the newer version.
15. Confirm update failure handling for invalid token, no network, checksum mismatch, signature mismatch, prerelease ignored, and active capture blocked.
16. Install a newer build over an older build and confirm user data remains.
17. Uninstall and confirm app files are removed while user data remains.

## Signing scope

Sign `ForzaTelemetryTrackerSetup-vX.Y.Z-x64.exe`, `ForzaTelemetryTracker.exe`, `ForzaTelemetryTrackerUpdater.exe`, `forza-map-tile-converter.exe`, and project-owned helper executables. Preserve the Microsoft signature on the bundled WebView2 installer. Use timestamping.
