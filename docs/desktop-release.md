# Desktop Release Guide

Forza is a trademark of Microsoft. Forza Telemetry Tracker is an unofficial community tool and is not affiliated with, endorsed by, or sponsored by Microsoft, Xbox Game Studios, Turn 10 Studios, Playground Games, or the Forza franchise owners.

## Release artifact

The user-facing artifact is `ForzaTelemetryTrackerSetup-vX.Y.Z-x64.exe`. Users do not install Python, Node, .NET, run PowerShell scripts, run `pip`, or start multiple programs.

Stable releases are published as Authenticode-signed Windows installers plus a SHA-256 checksum. Windows SmartScreen may still warn until the publisher/app builds reputation, but the release asset should not be an unsigned installer.

Existing unsigned releases are historical artefacts. Replace or supersede the latest unsigned release with a signed release before telling users the signed release process is live.

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
- GitHub CLI authenticated for this repository.
- Windows code-signing certificate visible in `Cert:\CurrentUser\My`.
- SimplySign Desktop signed in when using the Certum cloud certificate.
- `uv` when refreshing `requirements-telemetry-release-lock.txt`.

## Local build

```powershell
powershell -ExecutionPolicy Bypass -File tools\build-desktop-release.ps1 `
  -Version 0.1.0-local `
  -WebView2StandaloneInstaller C:\ReleaseInputs\MicrosoftEdgeWebView2RuntimeInstallerX64.exe
```

Use `-SkipInstaller` for a local app-bundle build that does not require Inno Setup or WebView2 installer input, and `-SkipSmoke` only when the HTTP smoke test is not useful for the current packaging check.

The release build uses `npm ci` for the frontend and installs Python dependencies from `requirements-telemetry-release-lock.txt`, which is generated for Windows/Python 3.12 with hashes:

```powershell
uv pip compile requirements-telemetry-desktop.txt requirements-telemetry-test.txt --python-version 3.12 --python-platform windows --generate-hashes -o requirements-telemetry-release-lock.txt
```

## Stable release publish

Stable releases are built, signed, checksummed, and uploaded from the maintainer's Windows signing machine. Do not upload the unsigned installer produced by GitHub Actions.

```powershell
$version = "1.2.3"
$tag = "v$version"
$repo = "seevydeepy/forza-telemetry-tracker"
$webView2 = "C:\ReleaseInputs\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"

powershell -ExecutionPolicy Bypass -File tools\build-desktop-release.ps1 `
  -Version $version `
  -Repository $repo `
  -Channel stable `
  -FeedbackEndpoint "https://forza-telemetry-feedback.cvdp.workers.dev/v1/reports" `
  -WebView2StandaloneInstaller $webView2

$installer = "dist\installer\ForzaTelemetryTrackerSetup-v$version-x64.exe"
```

Sign the installer locally. In this Codex setup, the normal path is:

```text
Use $code-sign to sign dist\installer\ForzaTelemetryTrackerSetup-vX.Y.Z-x64.exe
```

The equivalent PowerShell signing command is:

```powershell
$thumbprint = $env:FORZA_CODE_SIGNING_THUMBPRINT
if (-not $thumbprint) { throw "Set FORZA_CODE_SIGNING_THUMBPRINT to the Authenticode certificate thumbprint." }

$cert = Get-ChildItem "Cert:\CurrentUser\My\$thumbprint"
Set-AuthenticodeSignature `
  -FilePath $installer `
  -Certificate $cert `
  -HashAlgorithm SHA256 `
  -TimeStampServer "http://time.certum.pl"

$signature = Get-AuthenticodeSignature -FilePath $installer
if ($signature.Status -ne "Valid" -or -not $signature.TimeStamperCertificate) {
  throw "Installer signature or timestamp verification failed: $($signature.Status) $($signature.StatusMessage)"
}
```

Create the checksum after signing:

```powershell
$checksum = "$installer.sha256"
$hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $(Split-Path -Leaf $installer)" | Set-Content -Path $checksum -Encoding ascii
```

Push the source commit and tag, then create the release with the signed assets:

```powershell
git push origin master
git tag $tag
git push origin $tag

@"
Stable desktop release $tag

- Signed Windows installer.
- SHA-256 checksum is attached for verification.
- Source commit: $((git rev-parse HEAD).Trim())
"@ | Set-Content -Path release-notes.md -Encoding utf8

gh release create $tag `
  $installer `
  $checksum `
  --repo $repo `
  --title $tag `
  --notes-file release-notes.md `
  --verify-tag
```

The GitHub tag push no longer publishes a release. The `.github/workflows/desktop-release.yml` workflow is manual-only and builds an unsigned diagnostic package artifact for packaging checks.

Published stable releases contain:

- `ForzaTelemetryTrackerSetup-vX.Y.Z-x64.exe`
- `ForzaTelemetryTrackerSetup-vX.Y.Z-x64.exe.sha256`

## Release asset verification

From an empty directory, download a release and verify the installer signature and checksum:

```powershell
gh release download v1.2.3 `
  --repo seevydeepy/forza-telemetry-tracker `
  --pattern "ForzaTelemetryTrackerSetup-v1.2.3-x64.exe*"

$signature = Get-AuthenticodeSignature .\ForzaTelemetryTrackerSetup-v1.2.3-x64.exe
if ($signature.Status -ne "Valid" -or -not $signature.TimeStamperCertificate) {
    throw "Installer signature or timestamp verification failed: $($signature.Status) $($signature.StatusMessage)"
}

$expected = (Get-Content .\ForzaTelemetryTrackerSetup-v1.2.3-x64.exe.sha256).Split(" ")[0].ToLowerInvariant()
$actual = (Get-FileHash .\ForzaTelemetryTrackerSetup-v1.2.3-x64.exe -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) {
    throw "Installer checksum mismatch: expected $expected but got $actual"
}
"Installer signature and checksum verified: $actual"
```

## About window and updates

The About window is opened from the left slide-out menu. It shows installed build metadata from `/api/app/about`:

- version,
- release date,
- Git SHA,
- repository,
- channel,
- packaging/update readiness.

Update checks are user-initiated only. The app checks public GitHub Releases without credentials, ignores drafts and prereleases, and compares SemVer tags instead of publish dates.

When a newer stable release exists, the About button changes from `Check for updates` to `Open release X.Y.Z`. The app opens the GitHub Release page in the user's browser. The user downloads the installer, optionally verifies the Authenticode signature and attached SHA-256 file, closes the tracker, and runs the installer manually.

There is intentionally no automatic installer launch and no in-app executable verification path.

## Required validation

1. Install on Windows without Python, Node, or .NET available on `PATH`.
2. Verify the installer Authenticode signature is valid and timestamped before upload.
3. Verify the attached SHA-256 checksum was generated after signing.
4. Verify WebView2-present install skips the bundled prerequisite.
5. Verify WebView2-missing install installs the bundled Evergreen runtime.
6. Launch from Start Menu.
7. Launch from Desktop shortcut when selected.
8. Verify no terminal window appears.
9. Verify `/api/status` responds during smoke testing.
10. Verify `/events` connects during smoke testing.
11. Send a sample Data Out UDP packet to `127.0.0.1:5400` and confirm receipt.
12. Record telemetry and confirm `telemetry_tracker.sqlite3` under `%LOCALAPPDATA%\Forza Telemetry Tracker`.
13. Build the world-map cache from a valid local FH6 install folder.
14. Confirm generated tiles under `%LOCALAPPDATA%\Forza Telemetry Tracker\map-cache`.
15. Close the app and verify HTTP and UDP ports are released.
16. Install an older build, detect a newer stable release from About, open the GitHub Release link, and install the newer build manually.
17. Confirm update-check failure handling for no network, inaccessible public repository, missing checksum asset, prerelease ignored, and malformed release tags.
18. Install a newer build over an older build and confirm user data remains.
19. Uninstall and confirm app files are removed while user data remains.
