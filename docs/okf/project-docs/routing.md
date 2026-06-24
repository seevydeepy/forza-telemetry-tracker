# Project Docs and Community Metadata Routing

## Read This When

- A change touches one of this solution's owned paths.
- A symptom matches one of this solution's routing keywords.

## First Files To Inspect

- `docs/okf/project-docs/routing_guidance.card`
- `docs/okf/project-docs/solution.md`
- For landing-page, install, preview, privacy summary, support-link, update-check, or Ko-fi wording: `README.md`
- For contributor setup, validation, release-lock, forbidden artefact, or PR expectation changes: `CONTRIBUTING.md`
- For user help, troubleshooting, public issue routing, SmartScreen support wording, or feedback intake: `SUPPORT.md`
- For local data, network behaviour, feedback diagnostics, outbox, GitHub Releases, Ko-fi, or localhost health-check claims: `PRIVACY.md`
- For vulnerability handling and supported-version wording: `SECURITY.md`
- For GitHub intake fields or public-release-impact checklist changes: `.github/PULL_REQUEST_TEMPLATE.md` and `.github/ISSUE_TEMPLATE/`
- For README preview media: `docs/assets/`
- For historical implementation plans/specs: `docs/superpowers/`

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

## Symptoms And Search Terms

- readme
- contributing
- support
- privacy
- security
- community
- issue template
- pull request template
- design plan
- preview asset
- funding
- ko-fi
- smart screen
- unaffiliated
- unofficial
- data out setup
- public issue
- private vulnerability
- local-first
- privacy policy
- telemetry database
- generated map cache
- support route

## Handoffs

- Route runtime implementation questions to `desktop-backend` when the doc claim depends on Python/FastAPI, UDP Data Out capture, SQLite, local outbox, update checks, desktop launcher health checks, or world-map status.
- Route dashboard or visible UI behaviour questions to `web-dashboard` when the doc claim depends on Svelte components, modals, replay, route review, settings, import/export, or feedback UI.
- Route anonymous feedback infrastructure questions to `feedback-worker` when the doc claim depends on Worker/D1/GitHub App/private triage/rate-limit/HMAC behaviour. Do not use this bundle for `docs/feedback_reporting_*.md`.
- Route installer, release, attestation, dependency-lock, third-party notice, licence-bundle, and `docs/desktop-release.md` questions to `release-ci-packaging`.
- Route map tile conversion internals to `fh6-map-tile-converter`; keep this bundle limited to public-facing install-folder and map-cache documentation.
