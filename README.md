# Forge226 Coach — local plugin 0.9.1

This package includes the coaching skill AND working data tools. Keep the complete folder together; SKILL.md alone cannot provide the integrations.

## Start with a simple request

Supply this complete package to a desktop Work chat and say “Help me build my training plan.” START-HERE.md is the entry point. The assistant should read it and begin intake, checking existing tools and athlete context where available. It should guide any necessary tool setup at the step that needs it; you do not need to write installation or verification commands.

A folder/ZIP upload is not itself an installation. The host must be able to read the package and support local tools for the integrations. Local execution may require normal host approval. When the current chat has not discovered the installed tools, the assistant can run the bundled engine directly in a persistent local execution session, keeping intake, private account setup and planning together. If the host cannot execute local tools, manual coaching and file outputs continue in the same chat with clear limits.

If already available in this chat, select Forge226 Coach and continue. Existing profiles are resumed rather than recreated. Provider authorization happens only after that provider is chosen.

## Install on another Mac

Requires Python 3.10+ and a desktop host with local Codex plugin support. From this extracted folder run `python3 install.py`. It copies the clean plugin into your own local plugin source directory and uses the installed Codex CLI to register and install it. It does not copy anyone's athlete data or account credentials. It does not make a remote/web/mobile server.

You can instead provide this complete package to your local desktop agent and ask it to install using its supported plugin workflow. An upload alone does not install a local server. If the current chat cannot see registered tools, follow [the same-chat runtime](skills/forge226-coach/references/same-chat.md): the assistant operates bin/chat-session.py against the same database. Keep that process alive during private account setup.

## Choose your own sources — or none

After the guided goal, background, qualitative, schedule and life-constraint questions, the coach offers optional uploads/connections as the last intake step. No wearable/account is required. It remembers each athlete's choices and will not keep asking someone who declined data sharing.

Built-in live Strava, official Garmin Personal API and dedicated Garmin uploads are available. Other providers (including WHOOP, Wahoo or personal training logs) can use mapped CSV/JSON/ZIP imports. The coach inspects real column names/units and records the mapping; workouts and sleep/recovery are stored separately. Generic support does not imply every proprietary vendor export has a dedicated parser.

Live access for other services uses a verified host connector when one is available. Otherwise the coach records the request and offers uploads or manual answers. Naming a provider does not create an API integration. Connections are optional and can be mixed freely with manual context. Disabling a source excludes it from future analysis/dashboard output but keeps history and does not itself revoke account authorization.

## Garmin setup

Provide an account export ZIP, activity JSON or CSV. The coach previews the file, shows coverage and unit handling, then imports it. Later exports upsert matching source IDs and retain other activities. Partial/ambiguous imports need resolution. FIT/TCX parsing is not implemented. Live Garmin access is available separately through the official Personal API.

## Garmin Personal API setup

Ask “Connect my Garmin.” Forge226 returns a local key-entry page. Create your own key in Garmin Connect → Personal API settings, accept Garmin's terms directly there, choose its expiry and paste the key into that local page. Do not paste it into chat. The integration verifies account identity before saving credentials in owner-only local files and supports the global and China Personal API hosts.

Then ask “Sync my Garmin workouts.” Optional: “Also sync the last 28 days of sleep and HRV.” Activities and recovery data are stored separately, and repeated activity IDs update existing Garmin records. Garmin uploads still work. Bearer tokens are renewed from the stored key; when the key itself expires or is revoked, replace it through local setup. Each friend uses their own key for their own account. There is no shared application secret or commercial multi-user Garmin service in this package.

Official API references: https://developer.garmin.com/gc-developer-program/personal/personal-faq/ and https://developer.garmin.com/gc-developer-program/personal/swagger-docs/.

## Strava setup

Ask “Connect my Strava.” The tool opens a setup flow through a local browser URL. On first setup, create a Strava API app at https://www.strava.com/settings/api, use localhost as the callback domain, and enter the client ID/secret directly into the local setup page. Then authorize activity read access on Strava. Never paste secrets into chat. Keep the desktop/plugin session open until you return from Strava.

Each friend can configure their own API app. An app used for multiple athletes is subject to Strava's access limits and approval process. Credentials are NOT embedded in this package. The source documentation is https://developers.strava.com/docs/authentication/.

After connection, ask “Sync my recent Strava activities.” The tool remembers the authorized account and refreshes expiring tokens. It imports activity summaries on request; it does not post workouts or run a background sync. Source IDs prevent duplicate imports; cross-source Garmin/Strava matches are reported as provisional analysis candidates, with both originals retained.

## Coaching assessment and progress

The coach distinguishes first-time completion, performance and qualification goals, and assesses experience separately for each sport. It records a goal-feasibility judgment and evidence gaps before prescribing sessions. Time targets and championship qualification are separate; target-event rules must be verified for the relevant season.

Plans link sessions to measurable training blocks with checkpoints and explicit conditions to progress, repeat or reduce. Weekly reviews combine execution, recovery and schedule changes into a saved decision. The dashboard shows priorities, checkpoint results, benchmark history and why the plan changed. Existing saved plans remain readable and gain the new coaching fields on revision.

The analysis tools calculate coverage-qualified completed-week comparisons, benchmark history and conservative session-match candidates. Missing evidence does not become a missed workout. Optional normalized JSON lap analysis supports weighted segment comparisons, but does not fetch streams, parse FIT or establish physiological readiness. Exports preserve the saved coaching interpretation alongside newly calculated evidence.

## Plan changes and dashboards

Ask for an assessment, strategy or calendar. New plans are stored as drafts, checked against schedule constraints and reviewed before activation. Specific requests to apply a change authorize it after checks. Concurrent/stale revisions cannot silently overwrite the active plan. Old versions remain in the database.

Ask “Update my dashboard” to generate an HTML snapshot and portable state from the stored plan with current imported evidence. Excel output uses the host's spreadsheet tools. This plugin has no built-in Excel writer or hosted dashboard.

## Storage and privacy

Default: ~/Library/Application Support/Forge226Work. This is separate from the existing Forge226 desktop app. FORGE226_DATA_DIR can select a different location before starting the server. The local directory is owner-only; credentials are separate 0600 files and excluded from exports. The plugin itself does not encrypt them. OS account protections and disk encryption remain relevant. No credential or athlete record is included in the shareable archive.

Only one plugin process can write a data store at a time, to avoid token-refresh races. The desktop host may own a background connector even when no window is open. The coach checks the owner and guides an authorized restart if necessary. Separate athlete IDs prevent accidental cross-profile merges; this local installation is intended for one OS user's trusted use, not a shared multi-user server.

Existing Forge226 data is not migrated automatically. Supply exported profile/plan data to map into this plugin, or start a new season profile. The original application remains unchanged.

## Verification

The automated suite contains synthetic tests, including manual-only planning, mixed source preferences, custom workout/recovery imports, disabled-source history retention, unit validation and digest checks. Garmin tests also cover key entry, account binding, token renewal, 401 retry, paging, sleep/HRV separation and failure preservation. The automated tests use fake APIs; they do not validate a friend’s real account authorization.


Run `python3 -m unittest discover -s tests -v`. The suite uses synthetic data and a fake Strava API, including a loopback OAuth callback; no real Strava credentials are required. Live Strava authorization must still be completed by each athlete. Host discovery and real-file import should be checked during initial setup.

The new coaching tests exercise manual-only persistence/export, a qualification assessment with unverified rules, travel revisions, historical-plan retention, coverage gaps, duplicate ambiguity, benchmark comparability, conservative adherence and lap calculations. These are synthetic software scenarios, not proof of conversational coaching quality or athletic outcomes. Use [the coaching acceptance trials](tests/COACHING-TRIALS.md) for the first live walkthroughs.

The same-chat launcher uses the existing server and JSON-RPC protocol; it does not create a second database or grant account access. It needs a desktop host with a persistent local execution facility and normal permissions. It cannot bypass denied integrations or make local tools work in a browser-only host.

Process-level tests also exercise the same-chat launcher: discovery, saved-plan/export continuity, Garmin private key entry, Strava OAuth callback and sync against fake APIs, lock enforcement, and recovery after an invalid request. The interactive launcher was also exercised through the desktop execution session. Real account authorization and actual workout retrieval still require the athlete’s own setup.

## Guided intake

The coach asks one stage at a time: (1) goal/timing and experience, (2) sport background/current baseline, (3) recovery, motivation and preferences, (4) the seven-day AM/PM availability table, (5) dated life constraints, and (6) optional files/connections and output choice. It briefly recaps answers and explains why the next step matters. A beginner/intermediate/advanced label guides the conversation alongside actual experience per sport; optional unknowns do not cause repeated swim questions. Qualitative context and intake progress are saved with the athlete profile when persistence is available. Existing supplied history is reused immediately, while new connection setup is left until the end unless explicitly requested sooner.


## New in 0.8.0
- Full-history evidence and weekday-pattern tool, including distinct training days versus activity-file counts and possible race-week flags.
- Athlete-specific higher-volume builds, active-recovery preferences, and dated old/new weekly totals. No personal athlete targets are bundled.
- Interactive month/week/day calendar with phases, sport filters and full session detail.
- One explicit all-supported-Garmin-data operation with separate receipts and honest partial-failure reporting.
- Garmin/Strava form origin-policy correction, verified macOS TLS certificate fallback, clearer Garmin validation messages, background-process diagnostics and large-plan terminal input fix.
- Guidance for publishing private hosted dashboards through available host tools; automatic cloud Garmin sync is not included.

### Share or upgrade
Share this complete ZIP. Friends can extract it, supply it to their desktop assistant and say “Help me build my training plan.” Each person authorizes their own accounts; uploads and manual coaching remain valid alternatives. Use the included installer or your host's local-plugin update workflow to install this release. Downloading the ZIP alone does not update an already installed copy. The package does not modify your athlete database; it preserves the default data-store path and existing version checks.

See CHANGELOG.md for implementation and verification scope.
