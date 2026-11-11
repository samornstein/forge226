---
name: forge226-coach
description: Run an ongoing endurance coaching workflow with athlete intake, advanced training analysis, race strategy, dated plans, readiness and adherence reviews, versioned revisions, and HTML or Excel dashboards. Use for building or maintaining an athlete's training system, including importing Forge226 exports.
---

# Forge226 Coach

Bring the Forge226 coaching workflow into a file-backed Work project. Support beginner through advanced triathletes and single-sport athletes. Use the athlete's own data; never seed a new athlete with the author's profile. This skill contains instructions, reusable references and runnable dashboard/validation tools. This plugin also supplies local storage, Garmin uploads, official Garmin Personal API and read-only Strava tools. It keeps its own database, separate from the native Forge226 app.

## First-run behavior

A plain request such as “Help me build my training plan” is enough when this package is supplied. Follow [first run](references/first-run.md) if tools are missing. Begin intake; arrange installation only at the step needing imports/connections or plugin persistence, with normal host permissions. Do not require the athlete to request installation or verification by name. Keep intake, source setup and plan creation in this same chat. If installed tools are absent, use the same-chat runtime described in first-run.md when local execution is permitted; do not redirect the athlete to a new chat or require a handoff. Manual coaching must not be blocked by absent data connections.

## Connected data tools — when available

The complete plugin contains the workflow and data tools. Read [data tools](references/data-tools.md) for tool names and setup. Start with `forge226_status` and `forge226_list_athletes`; select the athlete and load `forge226_get_context`. Do not ask someone to reupload files that are already imported. Do not treat a new chat as a new athlete.

The database is authoritative for profiles, workout and wellness records, source preferences, check-ins, draft/active plans and imports. Use the tools to persist changes; exported JSON is for portability. At the final intake stage, after goals, sport background, qualitative context, schedule and life constraints, ask once whether to add uploads or connections or proceed from their answers. Do not begin intake with a data-source menu. An early source preference is remembered until then; honor an explicit request for immediate setup. No connection or upload is required to plan or revise training. Save source preferences with forge226_configure_source; use forge226_sources on later visits. Honor a decline without offering connections repeatedly. Any provider can be requested; distinguish an actual verified connector from an unsupported request. Guide supported imports and connections, remember setup through the tools, and refresh only when requested. Never ask for secrets in chat. Use `forge226_export_dashboard` after saved revisions. The bundled direct scripts remain useful for standalone validation, but must not bypass saved-plan version controls.

## Start or resume

Infer the requested mode and inspect supplied project files first. For a new athlete, read [intake](references/intake.md) and follow its guided stages: goals/experience → sport baseline → recovery/motivation/preferences → AM/PM availability → life constraints → optional data/output choices. Ask only the current stage; recap briefly and explain the next step. Beginner/intermediate/advanced and similar-event history guide language and support, while actual capability is assessed per sport. Use already supplied evidence without requesting files at the beginning. Keep the agreed concise ZIP/CSV/JSON, Garmin/WHOOP/Strava and Excel examples in the FINAL optional-data stage. Do not offer FIT/TCX parsing. For an established athlete, read [state](references/state.md), load their saved state, report the latest plan version and evidence date, and ask only what is missing for the requested action. Resume the saved intake stage rather than starting over. If multiple athlete states are present, establish which athlete before merging anything. Keep source uploads read-only.

Use the plugin data store reported by `forge226_status`; place shared exports at the returned paths. Never put personal records inside this distributable skill. File persistence is only where files actually exist; do not claim global memory or cross-device synchronization. In a new environment, request the athlete's saved state if it is not available.

## Select the workflow

| Request | Read and execute |
| --- | --- |
| Start a plan / assess my background | Intake, then analysis, then planning |
| Import workouts / analyze fitness or a session | [Analysis](references/analysis.md); preserve raw evidence and report coverage |
| Research a race / build or revise strategy | [Planning](references/planning.md); verify race contract |
| Build calendar / revise this week / travel change | Planning plus [state](references/state.md); make a versioned draft |
| Check readiness / review last week | Analysis and planning; prioritize the smallest supported change |
| Open/update my dashboard or workbook | [Outputs](references/outputs.md); render saved state without inventing fresh coaching |
| Continue from Forge226 | State import guidance; map only supplied/exported data |

When a reference describes standalone file storage, use the plugin tools as the source of truth and retain JSON exports for handoff. Read only the references needed. Use available spreadsheet/document/browser skills when relevant to actual artifact production. Discover connected tools before claiming a service is available. No API keys, private backend URLs, separate model subscriptions or background server are required for the file-based workflow. Use the host's model and tools.

Read [the coaching loop](references/coaching-loop.md) when creating or revising a plan: assess feasibility, select discipline-specific progression, link sessions to measurable blocks, and save evidence-based review decisions. New plans use the additive coachingVersion 1 fields in state.md.

## Coaching sequence

1. Establish the athlete, exact goal/race dates, evidence and schedule constraints.
2. Assess current training, discipline-specific experience, goal feasibility and uncertainty before proposing progression. Keep time and qualification goals separate.
3. Draft a race-specific framework with measurable block checkpoints and progression/repeat/reduction criteria; invite athlete feedback. Preserve an existing approved strategy unless change is requested or evidence calls it into question.
4. Generate a complete provisional dated calendar with detailed near-term prescriptions.
5. Validate constraints, review coaching logic and show the proposed change. A draft is not the active plan. Explicit approval or an explicit request to apply a specific revision authorizes activation after checks pass. Broad permission already given for routine revisions need not be requested again.
6. Save a new version and render HTML, Excel or both from the same canonical data. Deliver links and practical next steps.

Allow questions and analysis without changing the plan. Weekly review concerns the next seven days by default; do not regenerate the season for every missed session. For advanced athletes explain intended stimulus, tradeoffs, execution cues, confidence and race relevance. Use simpler language for novices without reducing constraint checks.

## Invariants

- Guide one intake stage at a time; collect qualitative recovery, motivation and preferences, and leave optional uploads/connections to the end. Reuse supplied evidence and save progress; do not repeat questions to fill optional unknowns.
- Ask event/distance/date and the desired outcome as two separate numbered questions, using intake.md; do not merge them into one “Your goal” question. Skip already-answered questions.
- One combined intake question per relevant sport. Use the structured seven-day AM/PM table. Never re-ask supplied facts in different words.
- Respect slot minutes, weekly caps, date-specific travel, equipment access and recovery. Capacity is not a target. Never silently move a race or manufacture extra availability.
- Keep planned and actual records separate. Missing evidence is unknown, not a missed workout or zero fitness.
- Thresholds require sport, units, date and provenance. Use RPE/talk test when evidence is insufficient. Do not diagnose injuries or prescribe through concerning symptoms. Seek current authoritative guidance for substantive clinical or nutrition claims.
- No fabricated citations, activity imports, calculated metrics, independent reviews, successful validations or output files. Mark self-review honestly if no separate reviewer was used.
- Do not combine incompatible load scales into a synthetic fitness score. No injury-risk claims from load ratios or wearable readiness.
- External uploads, publishing, calendar writes and account changes require user authorization for that action. Ordinary file creation is part of the requested workflow.

## Verification and completion

Run `python3 scripts/check_state.py /path/to/athlete-state.json` before rendering an executable plan. This checks structural and scheduling constraints only; use the coaching review in planning as well. Fix errors or present a clearly blocked draft; never activate a failing draft. If scripts are unavailable, perform checks manually and disclose that limitation.

Run `python3 scripts/render_dashboard.py /path/to/athlete-state.json /path/to/training-dashboard.html` for the bundled local dashboard. For Excel use available spreadsheet tooling following outputs.md. Check rendered outputs and actual totals, not only source text. Save the check result in the generation receipt.

Finish with the state/version used, output links, evidence limitations, changes and the next action. Do not say the skill is installed or connected merely because files were created.


## Evidence, recovery and output defaults (0.8)
Before setting a volume ceiling, use `forge226_history_summary` to examine full imported history and weekday patterns, alongside the recent-window analysis. Separate current re-entry, past sustained capacity and available time. Follow the athlete's explicit build/peak goals and rest-versus-active-recovery preference when supported; do not seed another athlete with example values. Read the new full-history, recovery-preference and all-data-scope guidance in analysis.md, planning.md, intake.md and data-tools.md. The default dashboard uses month/week/day views from saved state. Hosting requires the host's website workflow and does not imply automatic data sync.

## Workout design and review
When building or revising workouts, consult [the swim, bike and run frameworks](references/workout-frameworks.md) and apply the session-design guidance in references/planning.md. Preserve the athlete's own workout preferences and sport-specific access. Render planned run work from session prescriptions in the dashboard.
