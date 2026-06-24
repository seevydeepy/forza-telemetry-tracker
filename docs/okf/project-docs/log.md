# Project Docs and Community Metadata OKF Log

## Bootstrap

- Shallow OKF bundle created from repository structure.

## Deep Backfill

- `README.md` establishes the public landing page: local-first Windows desktop tool, FH6 Data Out setup at `127.0.0.1:5400`, GitHub Releases installer flow, preview GIFs in `docs/assets/`, privacy summary, developer commands, support routes, MIT licence, unaffiliated Forza wording, and Ko-fi link.
- `CONTRIBUTING.md` establishes contributor setup and validation commands, PR expectations, release-lock regeneration, and forbidden artefacts such as generated map caches, local SQLite databases, local game files, private keys, and credentials.
- `SUPPORT.md`, `PRIVACY.md`, and `SECURITY.md` establish support routing, local data and network behaviour, feedback privacy, public issue safety, SmartScreen status, and private vulnerability reporting.
- `.github/PULL_REQUEST_TEMPLATE.md` mirrors validation and public-release-impact checks; `.github/ISSUE_TEMPLATE/` provides bug, feature, support, and security intake routing.
- `.github/FUNDING.yml` contains only the Ko-fi funding link used by README/support surfaces.
- `docs/assets/` currently contains `route-review-demo.gif` and `dashboard-replay-demo.gif`, both referenced by README preview sections.
- `docs/superpowers/` contains historical implementation plans/specs for world-map install-folder behaviour, release artifact attestations, v0.1.5/v0.1.6 fixes, and anonymous feedback pipeline work. Those plans route into the owning implementation bundles when active code/docs change.
- Neighbouring OKF routing cards confirm bundle handoffs for desktop backend, web dashboard, feedback worker, release/CI/packaging, and FH6 map tile converter.

## Known Gaps

- Code of conduct content is intentionally minimal in source (`Be chill`); do not infer a fuller moderation policy without a source change.
- `docs/superpowers/` contains historical plans, not guaranteed-current implementation truth. Verify current owner files before using a plan as evidence for behaviour.
- This backfill deliberately did not inspect or change `docs/feedback_reporting_*.md` or `docs/desktop-release.md`; those are owned by neighbouring bundles.
