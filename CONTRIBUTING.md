# Contributing

## Project expectations

This is a local-first Windows desktop app. Keep changes focused, avoid bundling generated user data, and do not add private repository access, private keys, telemetry upload paths, or automatic installer execution.

Forza is a trademark of Microsoft. Keep public wording clear that this project is unofficial and unaffiliated.

## Development setup

Install Python 3.12, Node.js 22, npm, and the .NET 9 SDK.

```powershell
python -m pip install -r requirements-telemetry-tracker.txt
python -m pip install -r requirements-telemetry-test.txt
npm --prefix web\telemetry-tracker ci
```

Run the local app:

```powershell
python tools\run-telemetry-tracker.py
```

## Validation

Run the relevant checks before opening a pull request:

```powershell
python -m pytest
Push-Location web\telemetry-tracker
npm test
npm run build
Pop-Location
dotnet build tools\fh6-map-tile-converter\ForzaTelemetryTracker.FH6MapTileConverter.csproj --configuration Release
```

For release dependency checks:

```powershell
npm --prefix web\telemetry-tracker audit --audit-level=moderate
uvx pip-audit -r requirements-telemetry-desktop.txt -r requirements-telemetry-test.txt
dotnet list tools\fh6-map-tile-converter\ForzaTelemetryTracker.FH6MapTileConverter.csproj package --vulnerable --include-transitive
```

## Pull requests

- Explain user-visible behavior changes.
- Add or update tests when behavior changes.
- Update README, support, release, or security docs when public-facing behavior changes.
- Do not commit `node_modules`, `dist`, generated map caches, local SQLite databases, local game files, installer outputs, private keys, or credentials.
- Use `npm ci` in automation and release workflows.

## Python release lock

`requirements-telemetry-release-lock.txt` is generated for Windows/Python 3.12 release builds:

```powershell
uv pip compile requirements-telemetry-desktop.txt requirements-telemetry-test.txt --python-version 3.12 --python-platform windows --generate-hashes -o requirements-telemetry-release-lock.txt
```

Regenerate it whenever Python release or test dependency ranges change.
