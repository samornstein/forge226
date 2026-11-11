# Forge226 outputs

Default to a local HTML dashboard for ongoing use; also produce Excel when requested. A request for a dashboard alone does not require creating a new plan. Read the canonical saved state and show its date/version prominently. Separate draft from active. Never fill missing analysis cards with fabricated statistics.

## Bundled dashboard

Run `scripts/render_dashboard.py STATE OUTPUT.html`. It produces a self-contained offline snapshot styled after Forge226: warm background, dark cards and orange accents; goal/version, weekly volume, AM/PM capacity, framework, filterable session calendar, evidence, readiness, analysis and revision history. Text is escaped; no network calls or credentials. It includes JSON download to resume elsewhere and print styles. Check the HTML visually and exercise filters when browser tools are available. It has no backend, automatic Strava sync or editable completion database.

The renderer rejects structural/scheduling errors. For intake-only or blocked drafts, show the assessment in conversation instead of claiming an executable dashboard has passed. Coaching review still needs to assess equipment, recovery and clinical concerns beyond the script.

## Excel

Use the host spreadsheet skill/tool when available. Create a real .xlsx with Overview, Athlete & Constraints, Framework, Calendar, Weekly Summary, Actuals, Check-ins, Evidence and Revisions. Calendar carries stable IDs, actual Excel dates, AM/PM, discipline, duration, intensity, purpose, prescription and alternatives. Keep actuals editable and separate. Use formulas for weekly and discipline summaries referencing session rows; label race minutes separately and partial weeks explicitly. Show current training hours separately from capacity and planned hours. Use readable widths, frozen headers and filters; validate formulas and render representative sheets. Never silently produce CSV with an .xlsx extension.

Derive both formats from the same state/version, reconcile session IDs and totals, and preserve unit preferences. Include import instructions for edited actuals. File creation capabilities vary; explain missing tooling and provide a clearly labeled fallback only when needed. Publishing or creating a hosted application is a separate requested workflow.

## Sharing and continuity

Deliver the HTML/workbook plus athlete-state.json for continuity. Export a clean complete-plugin ZIP separately for sharing when integrations are wanted; exclude athlete state, activity exports, receipts with personal data and credentials. For Work installation, use its supported skill creation/installation flow; attaching a ZIP alone is not proof of installation. With the entire skill folder supplied, ask Work's skill creator to preserve the references and runnable scripts rather than flattening everything into a prompt. If the skill is installed locally, report that scope precisely rather than claiming workspace-wide availability.

## Goal progress and evidence dates

The HTML renderer shows saved feasibility, current priorities, uncertainty, block checkpoints, benchmark history and the latest review decision before the schedule. Preserve the distinction between the assessment date and the latest export/calculation date. No qualification probability or composite readiness score is generated. Existing plans without a coaching record show an assessment-not-yet-saved message.

For Excel, add Goal Assessment, Checkpoints, Benchmarks and Review Decisions sheets using the same canonical fields. Include method/date/conditions for benchmarks, checkpoint evidence/status, and the reason/next-review date for each decision. Cross-check the overview's next action and latest decision against the HTML state. A new export must not silently rewrite saved coaching findings in analysis; calculatedAnalysis is the latest observed evidence.


## Calendar navigation and hosted dashboards (0.8)
The bundled dashboard now includes Month, Week and Day views, phase navigation, sport filtering, per-day and per-week totals, AM/PM organization and click-through prescriptions. Render all views from the same saved canonical state/version. Phase names/dates, volume, goals and status are dynamic; never copy a demonstration athlete's targets into another athlete's dashboard. Empty or unknown coverage is not a missed workout. Race minutes remain separate from training totals. Test month boundaries, week totals, daily detail, phase navigation and filters when browser tools are available.

The HTML remains an offline snapshot. A request to make it a live site authorizes the separate hosting workflow through an available host website tool/skill; default private and preserve audience on updates. Do not claim that publication enables automatic Garmin sync. A live URL, durable edits, automatic refresh and backend account access are separate capabilities. Reuse the returned Site identity on future updates, save deployment metadata outside the plugin package, verify publication success, and retry a saved version rather than create another site after transient deployment failures. No Garmin credentials, localhost setup links or personal site IDs belong in the shareable plugin.

Export the complete clean plugin for friends, not only the skill text when integrations are wanted. Keep personal plans, profile, activities, wellness, receipts, databases, screenshots, deployments and credentials outside the distribution. Each friend starts with their own profile, availability, preferences and provider authorization. Existing users retain their local store; updating the package must not replace it.
