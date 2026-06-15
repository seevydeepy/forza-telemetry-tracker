# Security Policy

## Supported versions

Security fixes are handled on the latest stable release line only. If you are using an older installer, update to the latest release before reporting a vulnerability unless the issue prevents you from updating.

## Reporting a vulnerability

Do not open a public issue for a suspected security vulnerability. Use GitHub private vulnerability reporting when it is enabled for this repository. If it is not available, contact the maintainer privately before sharing exploit details.

Include:

- the affected version or commit;
- steps to reproduce;
- the impact you believe is possible;
- whether any local files, telemetry databases, or generated map-cache data are involved.

Do not send secrets, personal telemetry databases, local game files, generated map caches, or credentials unless a maintainer specifically asks for a redacted sample.

## Scope

The app is a local-first Windows desktop telemetry tool. Security-relevant areas include local HTTP endpoints, import/export handling, packaged release artifacts, updater behavior, installer behavior, and handling of local data paths.

Out of scope:

- reports that require modifying the user's local machine or game install outside normal app usage;
- denial-of-service reports that only affect the reporter's own local process without data exposure or privilege impact;
- vulnerabilities in third-party services that this project links to but does not control.
