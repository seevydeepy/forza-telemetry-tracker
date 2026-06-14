# Forza Telemetry Tracker

<a href='https://ko-fi.com/Z4I021C66X' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi3.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>

Windows desktop telemetry companion for Forza Horizon 6 Data Out; records local UDP telemetry, stores sessions in SQLite, shows live/review dashboards, supports route/map visualisation from locally owned game files, and can check GitHub Releases for manual updates.

## User install flow

The intended user experience is a single Windows setup executable downloaded from GitHub Releases. Users do not need Python, Node.js, .NET, PowerShell scripts, or command-line setup.

## Developer workflow

```powershell
python -m pip install -r requirements-telemetry-tracker.txt
python -m pip install -r requirements-telemetry-test.txt
npm --prefix web\telemetry-tracker install
python tools\run-telemetry-tracker.py
```

## License

MIT License. Third-party notices and bundled licenses are in `THIRD_PARTY_NOTICES.md` and `licenses/`.
