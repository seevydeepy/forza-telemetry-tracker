# Release, CI, and Packaging

## Purpose

Build, verify, sign, and publish the Windows desktop installer. This bundle owns GitHub CI/release workflows, Dependabot coverage, PyInstaller/Inno Setup packaging, release dependency locks, third-party notices, licence copies, packaged-app smoke tooling, and the maintainer release guide.

## Owned Paths

- .github/workflows/
- .github/dependabot.yml
- packaging/
- tools/build-desktop-release.ps1
- tools/smoke-desktop-package.py
- requirements-telemetry-release-lock.txt
- THIRD_PARTY_NOTICES.md
- licenses/
- docs/desktop-release.md

## Entrypoints

- `.github/workflows/ci.yml` runs Windows CI for Python tests/audit, frontend tests/build/audit, and .NET map-converter restore/audit/build.
- `.github/workflows/desktop-release.yml` is a manual diagnostic package build; it does not run on tag push and does not publish GitHub Releases.
- `tools/build-desktop-release.ps1` is the local and CI package orchestrator: writes `build/release-metadata.json`, builds frontend assets, installs locked Python dependencies, runs tests, publishes the map converter, runs PyInstaller, runs Inno Setup, and optionally smokes the packaged app.
- `packaging/pyinstaller/forza-telemetry-tracker.spec` defines bundled frontend, resources, map converter output, licence/notices, and release metadata.
- `packaging/installer/forza-telemetry-tracker.iss` defines the per-user Inno Setup installer, shortcuts, WebView2 prerequisite handling, and installer output name.
- `tools/smoke-desktop-package.py` launches the built package with smoke-only environment overrides and checks the GUI subsystem, bundled converter, `/api/status`, `/`, and `/events`.
- `docs/desktop-release.md` is the maintainer/user release-process reference.

## Neighbouring Systems

- Desktop Backend provides the packaged launcher, `/api/status`, `/events`, metadata/update logic, user-data paths, and smoke HTTP mode.
- Web Dashboard provides the frontend build output that PyInstaller embeds.
- FH6 Map Tile Converter provides the .NET converter source; release tooling publishes and packages its Windows output.
- Feedback Worker is wired into stable builds through the release metadata feedback endpoint.
- Project Docs owns broad README/support/community pages; release-specific installer, signing, checksum, WebView2, and validation guidance lives here.

## Maintenance Notes

- Stable releases are built, signed, checksummed, and uploaded from the maintainer's Windows signing machine; tag pushes do not publish unsigned installers.
- SHA-256 checksums must be generated after Authenticode signing because signing changes installer bytes.
- Keep dependency-lock changes aligned with the Windows/Python 3.12 `uv pip compile` command documented in `docs/desktop-release.md`.
