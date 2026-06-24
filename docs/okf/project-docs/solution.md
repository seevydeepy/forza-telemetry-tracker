# Project Docs and Community Metadata

## Purpose

Root project documentation, community metadata, support, privacy, security, funding, issue templates, design plans, and preview assets not owned by a narrower runtime or release bundle.

## Owned Paths

- README.md
- CONTRIBUTING.md
- SUPPORT.md
- PRIVACY.md
- SECURITY.md
- CODE_OF_CONDUCT.md
- LICENSE
- .github/FUNDING.yml
- .github/PULL_REQUEST_TEMPLATE.md
- .github/ISSUE_TEMPLATE/
- docs/assets/
- docs/superpowers/

## Entrypoints

- `README.md` is the public project landing page. It states the local-first Windows desktop purpose, preview GIFs, install flow, Data Out setup, privacy summary, developer commands, support routes, licence, and Ko-fi link.
- `CONTRIBUTING.md` is the maintainer/contributor entrypoint for local setup, validation commands, pull request expectations, release-lock regeneration, and forbidden artefacts.
- `SUPPORT.md`, `PRIVACY.md`, and `SECURITY.md` are the public support, data-handling, and vulnerability-reporting entrypoints.
- `.github/PULL_REQUEST_TEMPLATE.md` and `.github/ISSUE_TEMPLATE/` are the GitHub intake surfaces for validation evidence, public-release impact checks, bug reports, feature requests, support links, and security routing.
- `docs/assets/` holds README preview media. `docs/superpowers/` holds historical plans and specs for agentic implementation work.

## Neighbouring Systems

- `desktop-backend`: owns the FastAPI/Python runtime, local SQLite storage, Data Out capture, local feedback client/outbox, update-check implementation, and world-map status described by the public docs.
- `web-dashboard`: owns the Svelte UI surfaces referenced by docs, including feedback, settings, import/export, replay, route review, and dashboard behaviour.
- `feedback-worker`: owns Cloudflare Worker, D1, GitHub App, private triage repository, HMAC/rate-limit, and feedback-reporting runbook details; project-docs only summarises public user-facing behaviour.
- `release-ci-packaging`: owns installer packaging, release workflow, dependency locks, third-party notices, licences folder, release attestations, and `docs/desktop-release.md`.
- `fh6-map-tile-converter`: owns map tile conversion internals; project-docs only documents the user-facing install-folder and map-cache privacy expectations.

## Contracts

- Public docs must keep the project framed as an unofficial community tool unaffiliated with Microsoft, Xbox Game Studios, Turn 10 Studios, Playground Games, or the Forza franchise owners.
- Public docs must preserve the local-first privacy contract: no automatic analytics, crash reporting, tracking pixels, advertising SDKs, user accounts, or background telemetry upload behaviour.
- Support and issue intake must steer private diagnostics, security reports, telemetry databases, local game files, generated map caches, credentials, and private keys away from public issues unless a maintainer explicitly asks for a redacted sample.
- README release/install wording should stay aligned with the Windows installer path, unsigned SmartScreen warning, GitHub Releases update check, and release/packaging ownership.

## Maintenance Notes

- Keep this page focused on stable ownership, entrypoints, and contracts.
- Use `routing.md` for symptom/search routing details.
