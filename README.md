# Forza Telemetry Tracker

Windows desktop telemetry companion for Forza Horizon 6 Data Out; records local UDP telemetry, stores sessions in SQLite, shows live/review dashboards, supports route/map visualisation from locally owned game files, and can install signed updates from GitHub Releases.

## User install flow

The intended user experience is a single Windows setup executable downloaded from GitHub Releases. Users do not need Python, Node.js, .NET, PowerShell scripts, or command-line setup.

## Developer workflow

```powershell
python -m pip install -r requirements-telemetry-tracker.txt
npm --prefix web\telemetry-tracker install
python tools\run-telemetry-tracker.py
```

## License

MIT License. Third-party notices and bundled licenses are in `THIRD_PARTY_NOTICES.md` and `licenses/`.
