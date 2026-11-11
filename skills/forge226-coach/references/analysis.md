# Evidence and training review

## Import and evidence receipt

Use an available authorized connector or readable exports from Strava, Garmin, WHOOP or other sources. Inspect parser/tool support for CSV, JSON, FIT, TCX and GPX before claiming success. Route-only GPX is not physiological evidence. Offer manual summaries if unsupported. Never request passwords/tokens in chat.

Maintain a receipt with source filenames or connector, retrieved timestamp, coverage dates, timezone, units, included/excluded records, duplicate decisions and missing fields. Never infer Garmin units from unusually large values alone; use field metadata or confirm. Preserve raw values and normalized units separately. Convert actual timestamps to athlete-local dates for calendar matching; date-only planned workouts remain local dates.

Deduplicate with source ID first; cross-source matches require compatible sport, start time, duration and available distance. A close match is a candidate, not proof. Preserve distinct same-day sessions and complementary fields without inventing values. Ask about ambiguous pairs when materially affecting the assessment. Missing distance does not justify collapsing workouts by itself.

## Baseline and advanced assessment

Summarize weekly hours, frequency, discipline balance, consistency and longest sessions over available completed weeks. Compare recent four completed weeks with the preceding four only when coverage supports it. Label partial weeks, known rest days and gaps; do not count missing history as inactivity. Include easy/hard balance only at the granularity supported by data: session-average HR cannot establish time in zones. Use sport-specific zones and their dated thresholds.

For advanced athletes, connect observed patterns to the goal: endurance durability, threshold support, race-specific execution, strength consistency, pacing stability and recovery response. Interval execution, HR/power decoupling, drift, cadence and time in zones require suitable streams or lap data; summary-only files cannot substantiate those claims. Control for terrain, temperature, stops and sensor quality. Distinguish measured finding, interpretation and proposed action.

Use duration by sport as the common baseline. Report power-derived cycling load, session-RPE load and proprietary device scores separately with methods and coverage. Bike load may be computed as hours × (normalized power / contemporaneous FTP)^2 × 100 when supported; do not substitute average power silently or label every estimate TSS. Do not transplant the app's mixed-scale fitness/fatigue/form series. A consistent-load model requires an explicit method, dated thresholds, adequate history and initialization disclosure; it is optional and never proof of readiness or injury probability. Do not fabricate a consistency/readiness score to fill a card.

## Adherence

Match actual activities to individual planned sessions by local date, sport, duration and available details. Use one actual activity for at most one session unless explicitly split with accounted minutes. Match multi-sport legs separately. Ambiguous matches remain unconfirmed. Show completed, shortened, extended, substituted, missed-confirmed, unknown and future as distinct statuses. Do not mark a session missed merely because there was no imported activity. Show matched/planned minutes separately from completion counts and explain denominators. Strength, recovery and technique sessions should not disappear from adherence simply because no device recorded them.

## Readiness and review

Collect only new relevant information: sleep duration/quality, fatigue, soreness, stress, motivation, pain/illness, previous session RPE and today's available minutes. Respect athlete-specific baselines. WHOOP/Garmin scores are contextual signals, not diagnoses or automatic vetoes. Recommend proceed, modify or pause with the evidence and uncertainty; do not manufacture a composite score.

For weekly review: summarize planned vs actual by sport and key session, identify what was absorbed or disrupted, consider readiness and next week's constraints, then propose the smallest changes. No “make-up” overload. Preserve historical actuals and the season framework unless a broader revision is warranted. For concerning symptoms, pause demanding prescriptions and suggest appropriate professional assessment. Do not infer medical clearance from a device score.

## Implemented calculations and their boundaries

`forge226_analyze` returns an 84-day observed-volume view, sport frequency/longest sessions, and the latest four completed Monday–Sunday weeks versus the preceding four. Current-week data is excluded from that comparison. Missing weeks remain unknown. Interpret changes only when complete coverage is supported and duplicate candidates are resolved. A sync receipt alone cannot establish complete history. Record supported evidenceCoverage in the profile; never mark it complete just to unlock a trend. Provisional cross-source dedup retains originals and suppresses comparison claims.

The same tool groups saved benchmarks by sport, metric, units, method and conditions, reports age and numeric change, and flags incomplete entries. It does not decide whether the change reflects improvement or update prescription thresholds. Use `forge226_review_summary` for selected-plan adherence, recent check-ins and saved block/assessment context. Unique date/sport/duration matches are suggestions, not confirmed execution; unrecorded strength can be confirmed manually. No candidate is automatically a missed session or a fulfilled intensity target.

`forge226_analyze_session` supports explicit normalized JSON lap evidence; see data-tools.md. Use actual lap data with provenance, never synthesize laps from an activity average. It calculates lap pace and weighted group differences; it does not calculate normalized power, full-stream decoupling, time in zones or race predictions. If the available input cannot substantiate an advanced claim, state the limitation and use a supported checkpoint instead.


## Full-history and weekly-pattern review (0.8)
Before setting a season volume ceiling, call `forge226_history_summary` as well as recent `forge226_analyze`. Review the athlete's complete imported history, repeated larger weeks, discipline balance and day-of-week structure. Use explicit dates and actual totals. Verify possible race weeks; race events, aggregate multisport records and unrelated activities must not silently establish a training peak. Do not equate activity-file count with session count: warm-up, intervals and cooldown may be separate recordings. Report distinct training days by sport alongside record counts.

Keep three concepts separate: current tolerated/re-entry workload, historically repeated workload, and future available capacity. Recent post-race recovery or travel does not erase historical capability; past peaks do not justify an immediate return. Compare several sustained blocks rather than one maximum. Ask only about material missing history or uncertainty. The summary reports observed records, not confirmed rest or complete coverage.

Before deciding recovery-day placement, inspect the actual weekday pattern in several representative weeks and collect the athlete's recovery preference. Reuse successful structure where compatible with current availability and the new goal. Name the changes and rationale.
