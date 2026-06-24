# Release, CI, and Packaging Routing

## Read This When

- A change touches `.github/workflows/`, `.github/dependabot.yml`, `packaging/`, release locks, installer docs, third-party notices, licence copies, or packaged smoke tooling.
- A symptom involves CI failures, tagged release failures, installer output, PyInstaller bundling, Inno Setup, WebView2 prerequisite handling, artifact attestation, checksum verification, release dependency locks, or packaged-app smoke failures.

## First Files To Inspect

- `docs/okf/release-ci-packaging/routing_guidance.card`
- `docs/okf/release-ci-packaging/solution.md`
- `.github/workflows/desktop-release.yml`
- `tools/build-desktop-release.ps1`
- `docs/desktop-release.md`
- `packaging/pyinstaller/forza-telemetry-tracker.spec`
- `packaging/installer/forza-telemetry-tracker.iss`
- `tools/smoke-desktop-package.py`

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

## Symptoms And Search Terms

- Release does not start: search `desktop-release.yml`, `tags`, `v*.*.*`, `Validate SemVer tag`.
- CI fails before packaging: search `ci.yml`, `requirements-telemetry-release-lock.txt`, `pip-audit`, `npm audit`, `dotnet list`.
- PyInstaller output is missing files: search `packaging/pyinstaller/forza-telemetry-tracker.spec`, `datas`, `frontend-dist`, `release-metadata.json`, `bin/map-converter`, `licenses`.
- Installer build fails or output is missing: search `tools/build-desktop-release.ps1`, `iscc`, `FORZA_TRACKER_VERSION`, `WEBVIEW2_STANDALONE_INSTALLER`, `ForzaTelemetryTrackerSetup-v`.
- WebView2 install behaviour is wrong: search `packaging/installer/forza-telemetry-tracker.iss`, `IsWebView2Installed`, `WebView2ClientKey`, `PrepareToInstall`.
- Packaged app smoke fails: search `tools/smoke-desktop-package.py`, `--smoke-http-only`, `FORZA_TRACKER_SMOKE_HTTP_PORT`, `/api/status`, `/events`, `forza-map-tile-converter.exe`.
- Release metadata/update behaviour is wrong: start here for build metadata, then hand off to Desktop Backend for `telemetry_tracker/app_metadata.py` and `telemetry_tracker/app_updates.py`.
- Attestation or checksum verification fails: search `actions/attest`, `sha256sum -c`, `gh attestation verify`, `--signer-workflow`, `--source-ref`.
- Dependency update routing is unclear: search `.github/dependabot.yml` for `github-actions`, `npm`, `pip`, or `nuget`.
- Licence or notice packaging is wrong: search `THIRD_PARTY_NOTICES.md`, `licenses/`, and PyInstaller `datas`.

## Handoffs

- Route packaged runtime, app metadata parsing, update-selection bugs, and smoke HTTP mode internals to `desktop-backend`.
- Route Svelte/Vite test or build failures under `web/telemetry-tracker/` to `web-dashboard`; keep release orchestration failures here.
- Route converter source or decoding failures under `tools/fh6-map-tile-converter/` to `fh6-map-tile-converter`; keep publish/bundling failures here.
- Route feedback endpoint server behaviour to `feedback-worker`; keep release metadata injection here.
- Route broad README/community-support changes to `project-docs`; keep release-specific installer and verification docs here.
