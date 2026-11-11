# Local data tools and setup

## Resume and select
If registered Forge226 tools are absent, use [the same-chat runtime](same-chat.md) under normal local execution permissions. It calls the same tools/engine without opening another chat; it does not override a denied integration or host restriction.
Call forge226_status then forge226_list_athletes. If none exist, ask name/timezone and create one with forge226_create_athlete. If several exist, identify the intended athlete before reading private details. Save the merged profile using forge226_save_profile and its expected revision. Get existing context, active plan, check-ins and receipts before asking more intake questions.

## Optional and mixed data sources

For new-athlete intake, offer optional files/connections LAST, after the qualitative and scheduling stages in intake.md. Read already supplied evidence/context earlier, but do not ask for new files, source selection or credentials at the beginning. An early mention of Garmin or another service is a remembered preference, not a request to interrupt intake; honor an explicit request for immediate setup. Resuming an established profile or an explicit connection task need not rerun onboarding.

Use the exact concise Past workouts option from intake.md at the final optional-data stage. The following separate choices are only for someone who then needs help selecting a sharing method. Keep each choice to 1–2 short sentences; expand only the selected path afterward:

“How would you like to share your recent training?
- **Answer questions:** Describe your usual training week; estimates are fine.
- **Upload a file:** Share a supported ZIP, CSV or JSON workout-history export. I’ll help you find and download the right file.
- **Connect an account:** Connect Garmin or Strava through an API so I can retrieve workouts when you ask. I’ll walk you through the prerequisites and setup.
- **Combine options or decide later:** Tell me which apps you use, and I’ll help you choose.”


Ask once and honor the response. Do not assume that the author's preferences apply. No-data mode must still reach strategy, calendar and dashboard without another integration offer. Do not repeat this menu on later visits once preferences are saved.

### Guided prerequisites and setup

After a choice, guide the selected path in small steps; do not dump technical instructions for every provider or make the athlete discover prerequisites independently.
1. Confirm the service and reuse known device/account details. Check actual host tool support and saved connection status first. If export navigation depends on the device/site, establish that context only when needed and verify current official instructions rather than inventing menu labels.
2. Explain a short checklist for that path before starting: uploads need access to the account/export and a supported readable file; Garmin connection needs access to Personal API settings, acceptance of Garmin terms and creation of a personal key; Strava connection needs API-app configuration and read authorization. Local integrations also need a compatible desktop host, Python and installed Forge226 tools—check those yourself and follow first-run.md if missing. Explain only prerequisites that apply or remain incomplete.
3. Walk through the next actionable step and wait for its result before dependent steps. Use existing setup links/tools; never request secrets in chat or accept terms/authorize accounts for the person. Keep collected coaching answers in this chat; if registered tools are missing, follow [the same-chat runtime](same-chat.md) when local execution is permitted. Mention provider limitations when encountered and offer manual answers/uploads if the chosen path is unavailable.
4. Preview and validate an upload, or verify connection status and complete the requested initial read. Report actual date coverage and missing fields. A key saved, permission granted or file attached is not proof that usable workout history was retrieved.
5. Save the preference and receipt, then refine affected assessment findings and proceed to the framework (or the next unanswered item if the athlete explicitly connected early). Do not restart intake or require the athlete to request the next setup step by name.


Use forge226_sources and forge226_configure_source to remember choices. provider is a lowercase identifier; mode is manual, upload, native, external or requested. provider=manual/mode=manual/enabled=true selects manual-only coaching and disables other saved source preferences. It does not revoke connections or delete their history. Enabled uploaded sources can later coexist with manual answers. Disabling a source excludes its records from subsequent coaching summaries and dashboards while preserving them in the store. Requested means the integration is not available; it is never represented as connected.

For live providers beyond built-in Strava and Garmin, search the host's available connectors/plugins and verify their real capabilities before promising access. Follow their normal authorization flow, and verify success with an actual status/read call. mode=external records the preference only; the third-party connector owns authorization and credentials. Use it to retrieve authorized data, then normalize/export the records for the generic importer. Do not invent a WHOOP, Garmin or Wahoo API endpoint or ask for arbitrary API keys in chat. If no integration is available, offer uploads or manual answers without blocking planning. A provider-specific adapter can be added later, but selecting a name does not build one automatically.

### General file import

1. Use forge226_source_inspect on a supplied CSV/JSON/ZIP. Inspect table names, column meanings and units; do not assume vendor exports are identical across versions.
2. Select workout or wellness. Map actual columns with mapping.fields; use mapping.scales for explicit numeric conversion, mapping.units for the resulting canonical units, and mapping.constants for known sport/name when absent. Mapping.table selects one table in a ZIP; mapping.records_path selects a nested JSON array. Do not ask the athlete to do the technical mapping when the fields are unambiguous; explain or clarify only genuinely uncertain semantics.
3. Preview using forge226_source_preview, inspect coverage and rejected rows, then save with forge226_source_import using the returned SHA256 and identical mapping. The import saves provenance and mapping. Use a supplied stable source ID when available; otherwise unchanged rows receive a content-derived ID. Corrected rows without stable IDs may require review for duplicates.
4. Keep wellness separate: list_wellness provides sleep/recovery records; analyze/list_activities count workouts only. Vendor recovery scores retain their original named scales. Never add sleep to training volume or merge arbitrary device readiness scores.

Example workout mapping for a hypothetical Wahoo/custom CSV (column names are examples, not a claim about actual Wahoo exports):

```json
{"fields":{"id":"activity_id","startTime":"started_at","sport":"sport","durationSeconds":"duration_minutes","distanceMeters":"distance_km"},"scales":{"durationSeconds":60,"distanceMeters":1000},"units":{"durationSeconds":"s","distanceMeters":"m"}}
```

Example recovery mapping for a hypothetical WHOOP/custom CSV:

```json
{"fields":{"date":"day","sleepHours":"sleep_minutes","hrvMs":"hrv","recoveryScore":"recovery"},"scales":{"sleepHours":0.016666666666666666},"units":{"sleepHours":"h","hrvMs":"ms","recoveryScore":"source score 0–100"}}
```

Canonical dates use YYYY-MM-DD and timestamps use ISO with timezone if available. Canonical numeric fields require explicit units after scaling: s, m, bpm, W, h and ms as applicable. If a source uses proprietary binary formats, time strings or a different structure not supported by these parsers, use available conversion tools with an explained transformation and preserve the original upload; otherwise request a supported export. Generic mapping support is not a claim that every vendor format has been validated.

## Garmin Personal API connection

When the athlete chooses a live Garmin connection, use forge226_garmin_status. If unconnected, use forge226_garmin_connect and give the returned local setup link. The athlete creates their own Personal API key in Garmin Connect, accepts Garmin's terms themselves and pastes the key ONLY into the local form. Never ask for the key or Garmin password in chat. The local form verifies the account with Garmin before storing credentials and records the native source preference. Garmin uploads remain an alternative and can coexist with a live connection.

Garmin Personal API is for each individual's own data, not a shared multi-user commercial API application. Each friend uses their own key in their own local installation. Personal keys expire; record optional expiry metadata if supplied and direct renewal back to the local form. Access tokens are obtained from the key and renewed before expiry; there is no refresh token. The form supports global and China endpoints only. No arbitrary API host can receive the key.

Use forge226_garmin_sync when asked for workouts (default recent 183 days; shorter windows can be requested). Use forge226_garmin_sync_wellness when sleep/overnight HRV is wanted, including an explicit all-supported-data request (default 28 days). Read forge226_garmin_status for per-provider last successful sync and cached connection information. A stored status is not a live test of an expired or revoked key. A 401 receives one token-renewal retry; denied/expired-key, network, rate-limit, malformed or truncated syncs must not claim success or erase old history.

Uploads and API imports share Garmin source IDs so repeated activity imports upsert rather than duplicate the same workout. Multi-sport parent summaries are excluded when child legs occur in the fetched result. Verify ambiguous history rather than assuming all cross-source duplicates or older aggregate uploads are removed automatically. Sleep and HRV have their own stable dated IDs in wellness storage.

forge226_garmin_disconnect removes the local key/token and keeps imported history. It does not revoke the Personal API key at Garmin; explain that the athlete can delete the key in Garmin Connect. Normal Garmin wearable-to-Connect syncing remains Garmin's responsibility; this tool fetches data already available through the supported API. No background polling, Garmin writes, full activity stream/FIT import or entire Garmin API coverage is implied.

Official references: [FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/), [Swagger](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/), [Garmin reference client](https://github.com/garmin/connect-personal-api-python).

## Garmin
Ask for a Garmin account export ZIP, activity JSON or CSV. Use the absolute supplied file path with forge226_garmin_preview. Show recognized count, coverage, units and rejected records. For a named summarizedActivities JSON export, the importer applies milliseconds/centimeters explicitly; conventional activityTypeDTO JSON uses seconds/meters. Unknown formats require an explicit units choice after inspection, never a magnitude guess. CSV may require distance units. FIT/TCX are not implemented: ask for ZIP/JSON/CSV instead.

Call forge226_garmin_import with the preview SHA256 and identical unit options. An upload request authorizes this import once valid; do not add a gratuitous permission question. Explain rejected records and obtain agreement before allow_partial=true. Upsert preserves unmatched existing history. No destructive replace option is exposed. Remember imports through receipts, not chat memory. A new export is imported the same way and will update matching source IDs.

## Strava
Call forge226_strava_status. If unconfigured/disconnected, call forge226_strava_connect and show the returned local URL. The athlete enters app credentials on that page and authorizes Strava directly. Never request passwords, client secrets, access tokens or refresh tokens in conversation. First-time app configuration uses Strava's API settings; callback domain localhost. Each friend configures their own app/account unless an approved multi-athlete app is deliberately supplied. Do not copy the author's credentials or existing dashboard cookies.

After the browser flow, check status again. Then call forge226_strava_sync when asked to import/update recent activities; report completed coverage and count. Tokens refresh internally; rate limits/network errors retain existing history and do not advance successful-sync state. Sync is on request, not a background automation. If OAuth is revoked/expired, guide reconnection. Use forge226_strava_disconnect only for an explicit disconnect request; this revokes authorization but retains previously imported local history.

Strava data are activity summaries, not full streams. No Garmin password login, built-in WHOOP/Wahoo live API, FIT parser or Strava stream downloader is bundled. Garmin instead uses its official Personal API key. Their readable files can use the mapped importer and an available host connector can provide live access. Be explicit about these boundaries.

## Coaching state and plan changes
Read forge226_get_context and forge226_get_plan. Activity records come from forge226_list_activities; computed duration analysis from forge226_analyze. Keep unknown completion separate from confirmed missed sessions. The analysis reports provisional cross-source duplicate candidates; originals are preserved.

Readiness is persisted with forge226_save_checkin. For plans, build the canonical state from state.md; include review.type=self-review or independent-review (only when true), review.decision=pass or needs_changes, and review.issues. Call forge226_save_plan_draft with the current active parent_version or null. Show validation and concrete changes. Call forge226_activate_plan only after user authorization for that change, with expected_active matching the version read. Stale parents or failed checks cannot activate. Earlier explicitly authorized changes do not need another permission round.

Export with forge226_export_dashboard. It uses the saved plan plus the latest imported activities/check-ins and returns HTML/state paths. Excel generation uses available host spreadsheet tools from that exported state. The plugin does not silently update the original Forge226 desktop database or host a public dashboard.

## Persistence and sharing
Data stays in the local directory shown by status, outside the plugin cache. Credentials are separate owner-only files (not encrypted by the plugin); OS account protections apply. Do not read or echo credential files. The plugin requires Python 3.10+ and a local stdio-capable desktop host. It is not a web/mobile hosted service. Installation and tool access must be verified in the target host before claiming setup is complete.

Share only the plugin archive. Never bundle an athlete database, connection credentials, raw exports or generated personal dashboards unless that sharing is explicitly requested. Each installation starts with its own local data store. The server accepts one active process per data directory to prevent token rotation races.

## Goal analysis and weekly reviews

Use forge226_analyze for completed-week comparisons and benchmark history. Save confirmed coverage and dated benchmarks in the merged profile using the shapes in state.md. Missing weeks are unknown; an API sync is not proof of all training/rest. Confirm material duplicate candidates before interpreting trends. Do not set coverage complete just to obtain percentages.

Use forge226_review_summary with athlete_id, optional as_of/from_date and optional saved version. It reads actuals, confirmed sessionOutcomes, candidate matches, check-ins, assessment, blocks and decisions. It never revises or activates the plan. Persist confirmed outcomes and the reasoned review decision in the next version; show the exact affected dates and apply only authorized changes. In a new plan, use coachingVersion 1, assessment, trainingBlocks and reviewDecisions as specified in state.md.

### Optional normalized lap analysis

forge226_analyze_session reads a supplied or faithfully converted JSON file against an enabled stored activity. It is read-only; retain results and provenance in saved analysis/evidence if used for a coaching decision. It does not fetch Garmin/Strava laps, parse FIT, or persist the source file. Inspect a supplied export and convert only fields whose semantics and units are explicit. Never invent intervals from summary averages. This is optional for advanced evidence, never an onboarding requirement.

File shape (values below are format examples, not athlete targets):

```json
{"activityId":"stored-activity-id","source":"filename and conversion receipt","units":{"duration":"s","distance":"m","power":"W","heartRate":"bpm"},"laps":[{"id":"lap-1","startSeconds":0,"durationSeconds":300,"distanceMeters":2000,"meanPowerWatts":180,"meanHeartRateBpm":130}]}
```

Lap starts/durations use a consistent elapsed-time basis and cannot overlap. Power/HR/distance may be omitted when unavailable; missing is not zero. Optional comparison object: `{ "firstLapIds": ["lap-1"], "secondLapIds": ["lap-2"], "context": "What makes these segments comparable; terrain, weather, effort and stops" }`. Groups must be disjoint. Means are duration weighted; run pace uses distance and duration. Differences are descriptive, not a validated fatigue/decoupling metric or proof of readiness. Source provenance and actual activity linkage must be checked before interpretation.


## Complete supported import and transparent limits
`forge226_garmin_sync_all(athlete_id, activity_days=730, wellness_days=90)` runs both supported imports after an explicit all-data request and returns per-dataset receipts/errors. It is not atomic across datasets: one can succeed while the other fails. Report actual saved counts, requested windows and failures; never call a partial import complete. Validate requested windows before starting. A calendar-year request should calculate days in the athlete's timezone; do not silently expand a narrower scope. No background refresh is implied.

Supported maximums: activity summaries, 730 recent days and fewer than 2,000 fetched records per sync; wellness, 90 recent days, sleep duration and overnight average HRV only. These are connector limits, not claims about all Garmin history. No sleep stages, Body Battery, stress, Training Readiness, detailed streams or full laps are imported by these tools. Never describe this as every metric Garmin stores. Record enabled datasets/preferences and successful receipts so the athlete need not re-authorize the same scope in every turn.

Garmin alone is sufficient when it contains the athlete's history. Repeated Garmin imports upsert source IDs. Cross-provider duplicate candidates remain provisional, and both originals are retained: do not promise guaranteed automatic de-duplication. Use `forge226_history_summary` for full-history coaching review; default `forge226_analyze` remains a recent 84-day view.

## Setup troubleshooting without exposing credentials
- A running connector can be owned by the desktop host in the background, without a visible window. Explain that plainly. Lock metadata names the process; identify it read-only before offering a restart. Never kill an unidentified process, delete a live lock, or switch stores to evade it. Follow existing authorization for a specific restart; do not demand another permission round once authorized.
- Keep setup servers alive through form submission and verification. Fresh URLs expire after 15 minutes; expired forms require a fresh URL. `same-origin` referrer policy preserves the origin check; do not weaken origin or CSRF checks to get past a form error.
- Verified TLS uses Python trust configuration with a macOS system-certificate fallback only when defaults are missing. Never disable verification. Network, TLS, form validation and API rejection are different failures; explain the observed category, not an unsupported diagnosis that the key is wrong.
- Keys go only into the private form. Use the exact newly displayed Personal API key without prefixes or quotes. Optional expiry is metadata, may be left blank, and does not alter Garmin's real expiration. Dates are checked against the selected athlete's timezone. Never print raw exceptions, request headers, response tokens or key values while troubleshooting.
- After form success, verify account status and perform the already-requested initial import. Do not stop at connection success or ask again for import permission.
