# Support

## Getting help

Use GitHub Issues for reproducible bugs and feature requests. Include the app version from the About window, whether you installed a release or are running a developer checkout, and the smallest set of steps needed to reproduce the problem.

Do not attach telemetry databases, local game files, generated map-cache files, credentials, or private keys unless a maintainer explicitly asks for a redacted sample.

## Troubleshooting checklist

- Confirm Forza Horizon 6 Data Out is enabled.
- Set the Data Out IP to `127.0.0.1` and port to `5400`.
- Close other telemetry tools that may already be listening on the same UDP port.
- For map setup, choose the top-level local game install folder, not a generated cache folder.
- Use the About window to check whether a newer public GitHub Release is available.

## Security reports

Report suspected vulnerabilities using [SECURITY.md](SECURITY.md). Do not put exploit details in public issues.

## Privacy

Review [PRIVACY.md](PRIVACY.md) for local data storage and network behavior.

## Project status

Current releases are unsigned Windows desktop installers. Windows SmartScreen warnings are expected until the project has code-signing infrastructure and reputation.
