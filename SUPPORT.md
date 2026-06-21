# Support

## Getting help

Use `Send Feedback` in the app for reproducible bugs, setup problems, feature requests, and rough feedback. It does not require a GitHub account and sends the report to a private maintainer triage repository.

Include the app version from the About window, whether you installed a release or are running a developer checkout, and the smallest set of steps needed to reproduce the problem.

Do not include telemetry databases, local game files, generated map-cache files, credentials, or private keys unless a maintainer explicitly asks for a redacted sample.

Public GitHub Issues remain suitable for development discussion, pull requests, and problems that are safe to discuss in public. Do not put private diagnostics or sensitive local paths in public issues.

## Troubleshooting checklist

- Confirm Forza Horizon 6 Data Out is enabled.
- Set the Data Out IP to `127.0.0.1` and port to `5400`.
- Close other telemetry tools that may already be listening on the same UDP port.
- For map setup, choose the top-level local game install folder, not a generated cache folder.
- Use the About window to check whether a newer public GitHub Release is available.
- If `Send Feedback` reports that feedback was saved for retry, leave the app installed so the local outbox can retry later.

## Security reports

Report suspected vulnerabilities using [SECURITY.md](SECURITY.md). Do not put exploit details in public issues.

## Privacy

Review [PRIVACY.md](PRIVACY.md) for local data storage and network behavior.

## Project status

Current releases are unsigned Windows desktop installers. Windows SmartScreen warnings are expected until the project has code-signing infrastructure and reputation.
