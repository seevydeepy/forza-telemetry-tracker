# Release, CI, and Packaging OKF Log

## Bootstrap

- Shallow OKF bundle created from repository structure.

## Deep Backfill 2026-06-25

- Inspected `.github/workflows/ci.yml`: Windows CI installs `requirements-telemetry-release-lock.txt`, runs Python tests and `pip-audit`, runs frontend `npm ci`/audit/tests/build, and restores/audits/builds the .NET map converter.
- At the time of this backfill, `.github/workflows/desktop-release.yml` was tag-triggered and published an unsigned installer with GitHub Artifact Attestations. This entry is historical; see the 2026-07-03 release signing update below for the current flow.
- Inspected `tools/build-desktop-release.ps1`: local/CI build writes `build/release-metadata.json`, builds frontend assets, installs locked release dependencies, runs tests, publishes the converter, runs PyInstaller, runs Inno Setup, and runs `tools/smoke-desktop-package.py` unless skipped.
- Inspected `packaging/pyinstaller/forza-telemetry-tracker.spec`: bundled data includes frontend dist, tracker resources, `build/map-converter/win-x64`, `licenses/`, `THIRD_PARTY_NOTICES.md`, and `build/release-metadata.json`.
- Inspected `packaging/installer/forza-telemetry-tracker.iss`: installer is per-user, names `ForzaTelemetryTrackerSetup-v{version}-x64`, creates shortcuts, launches post-install, and conditionally installs bundled WebView2.
- Inspected `tools/smoke-desktop-package.py`: smoke checks Windows GUI subsystem, bundled converter presence, temporary user settings, `/api/status`, `/`, and one `/events` SSE line.
- Inspected `docs/desktop-release.md`: documented release artifact, unsigned-installer warning, prerequisites, local build command, tagged GitHub release path, attestation/checksum verification, update behaviour, and manual validation checklist.
- Inspected `THIRD_PARTY_NOTICES.md` and `licenses/`: notices cover Google Material Design Icons, ForzaTechStudio, and BCnEncoder.NET with corresponding licence copies.
- Inspected `.github/dependabot.yml`: weekly Dependabot coverage exists for GitHub Actions, npm frontend, pip root dependencies, and NuGet map converter dependencies.

## Release Signing Update 2026-07-03

- Updated `.github/workflows/desktop-release.yml` so tag pushes no longer publish unsigned installers; it is now a manual unsigned diagnostic package build only.
- Updated `docs/desktop-release.md` so stable releases are built locally, signed with Authenticode, checksummed after signing, and uploaded with `gh release create`.
- Existing unsigned GitHub Releases remain historical assets until replaced or superseded by a signed release.

## Known Gaps

- No release-packaging routing gaps were recorded by this backfill.
