#Requires -Version 5.1
<#
.SYNOPSIS
    Orchestrates a full desktop release build for Forza Telemetry Tracker.
#>
param(
    [string]$Version = "0.1.0",
    [string]$Configuration = "Release",
    [string]$Repository = "seevydeepy/forza-telemetry-tracker",
    [string]$Channel = "stable",
    [string]$ReleaseDate = "",
    [string]$GitSha = "",
    [string]$TrustedSignerThumbprints = "",
    [string]$WebView2StandaloneInstaller = "",
    [string]$SignToolPath = "",
    [string]$CertificateSubject = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [switch]$SkipSigning,
    [switch]$SkipInstaller,
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$ResolvedWebView2StandaloneInstaller = ""
if ((-not $SkipInstaller) -and $WebView2StandaloneInstaller) {
    $WebView2InstallerItem = Get-Item -LiteralPath (Resolve-Path -LiteralPath $WebView2StandaloneInstaller -ErrorAction Stop).Path -ErrorAction Stop
    if ($WebView2InstallerItem.Length -le 1MB) {
        throw "WebView2 standalone installer must be larger than 1 MB: $($WebView2InstallerItem.FullName)"
    }
    $ResolvedWebView2StandaloneInstaller = $WebView2InstallerItem.FullName
}

function Invoke-Step {
    param([string]$Name, [scriptblock]$Action)
    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Action
}

function Invoke-Sign {
    param([string]$FilePath)
    if ($SkipSigning) { return }
    if (-not $SignToolPath -or -not $CertificateSubject) {
        throw "Signing is required but SignToolPath and CertificateSubject were not provided. Use -SkipSigning to skip."
    }
    & $SignToolPath sign /n $CertificateSubject /fd SHA256 /tr $TimestampUrl /td SHA256 $FilePath
    if ($LASTEXITCODE -ne 0) { throw "signtool failed for $FilePath (exit $LASTEXITCODE)" }
}

function Split-Thumbprints {
    param([string]$Value)
    if (-not $Value) { return @() }
    return @(
        $Value -split '[,;]' |
            ForEach-Object { ($_ -replace '[:\s]', '').ToUpperInvariant() } |
            Where-Object { $_ }
    )
}

if (-not $ReleaseDate) {
    $ReleaseDate = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
}
if (-not $GitSha) {
    $GitSha = (git rev-parse HEAD).Trim()
}
$Version = $Version.TrimStart("v")

Invoke-Step "Generate release metadata" {
    $metadata = [ordered]@{
        version = $Version
        release_date = $ReleaseDate
        git_sha = $GitSha
        repository = $Repository
        channel = $Channel
        trusted_signer_thumbprints = @(Split-Thumbprints $TrustedSignerThumbprints)
    }
    New-Item -ItemType Directory -Force -Path "build" | Out-Null
    $metadata | ConvertTo-Json -Depth 5 | Set-Content -Path "build\release-metadata.json" -Encoding UTF8
}

# Frontend
Invoke-Step "Install frontend dependencies" {
    Push-Location "web\telemetry-tracker"
    try {
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    } finally {
        Pop-Location
    }
}

Invoke-Step "Run frontend tests" {
    Push-Location "web\telemetry-tracker"
    try {
        npm test
        if ($LASTEXITCODE -ne 0) { throw "npm test failed" }
    } finally {
        Pop-Location
    }
}

Invoke-Step "Build frontend" {
    Push-Location "web\telemetry-tracker"
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
    } finally {
        Pop-Location
    }
}

# Python tests
Invoke-Step "Run Python tests" {
    python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
}

# Map converter
$MapConverterOut = "build\map-converter\win-x64"

Invoke-Step "Publish FH6 map converter" {
    if (Test-Path $MapConverterOut) {
        Remove-Item -LiteralPath $MapConverterOut -Recurse -Force
    }
    dotnet publish "tools\fh6-map-tile-converter\ForzaTelemetryTracker.FH6MapTileConverter.csproj" `
        --configuration $Configuration `
        --runtime win-x64 `
        --self-contained true `
        --output $MapConverterOut `
        /p:PublishSingleFile=false
    if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed" }

    $ConverterExe = Join-Path $MapConverterOut "forza-map-tile-converter.exe"
    if (-not (Test-Path $ConverterExe)) {
        throw "Expected output not found: $ConverterExe"
    }
    Invoke-Sign $ConverterExe
}

# Desktop Python app
Invoke-Step "Install desktop Python dependencies" {
    python -m pip install -r requirements-telemetry-desktop.txt
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
}

Invoke-Step "Build PyInstaller app" {
    python -m PyInstaller --clean --noconfirm packaging\pyinstaller\forza-telemetry-tracker.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

    $AppExe = "dist\ForzaTelemetryTracker\ForzaTelemetryTracker.exe"
    if (-not (Test-Path $AppExe)) {
        throw "Expected output not found: $AppExe"
    }
    Invoke-Sign $AppExe
}

Invoke-Step "Build updater helper" {
    python -m PyInstaller --clean --noconfirm --onefile --noconsole --name ForzaTelemetryTrackerUpdater telemetry_tracker\update_helper.py
    if ($LASTEXITCODE -ne 0) { throw "Updater helper PyInstaller build failed" }

    $UpdaterExe = "dist\ForzaTelemetryTrackerUpdater.exe"
    if (-not (Test-Path $UpdaterExe)) {
        throw "Expected updater helper not found: $UpdaterExe"
    }
    Invoke-Sign $UpdaterExe

    Copy-Item -LiteralPath $UpdaterExe -Destination "dist\ForzaTelemetryTracker\ForzaTelemetryTrackerUpdater.exe" -Force
}

# Installer
if (-not $SkipInstaller) {
    Invoke-Step "Build Inno Setup installer" {
        $env:FORZA_TRACKER_VERSION = $Version
        $env:FORZA_TRACKER_INSTALLER_SOURCE = (Resolve-Path "dist\ForzaTelemetryTracker").Path
        $env:WEBVIEW2_STANDALONE_INSTALLER = $ResolvedWebView2StandaloneInstaller

        $iscc = Get-Command iscc -ErrorAction SilentlyContinue
        if (-not $iscc) {
            throw "iscc (Inno Setup compiler) was not found on PATH. Install Inno Setup and ensure iscc.exe is on PATH."
        }

        iscc "packaging\installer\forza-telemetry-tracker.iss"
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed" }

        $InstallerExe = "dist\installer\ForzaTelemetryTrackerSetup-v$Version-x64.exe"
        if (-not (Test-Path $InstallerExe)) {
            throw "Expected installer not found: $InstallerExe"
        }
        Invoke-Sign $InstallerExe
    }
}

# Smoke test
if (-not $SkipSmoke) {
    Invoke-Step "Smoke test packaged app" {
        python tools/smoke-desktop-package.py --app-dir dist\ForzaTelemetryTracker
        if ($LASTEXITCODE -ne 0) { throw "Smoke test failed" }
    }
}

Write-Host ""
Write-Host "Build complete - v$Version" -ForegroundColor Green
