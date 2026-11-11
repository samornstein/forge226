# Release verification — 0.9.0

89 synthetic regression tests passed. Synthetic dose checks covered mixed estimated and timed minutes, non-run sessions and absent dose.

# Release verification — 0.8.0

- 89 automated synthetic tests passed with Python 3.12 on macOS.
- Tests cover existing imports, versioning, athlete isolation, coaching state and new history, all-supported import, TLS fallback, strict form origin/CSRF behavior, specific expiry errors, large PTY requests and date-specific constraints.
- Interactive calendar checked in the in-app browser using a synthetic athlete: month, week, day, session detail dialog, sport filter, phase navigation and consistent 2h15 weekly total.
- Portable and compatibility JSON manifests and YAML skill/agent metadata parsed.
- Distribution scanned for personal athlete/site identifiers, local user paths, databases, credential files, bytecode and unrelated project files.

These tests do not establish training outcomes or guarantee third-party API availability. Garmin/Strava use fake API responses in automated tests. Real accounts require each athlete's authorization. This release does not automatically install itself, connect accounts, activate a plan or publish a site.
