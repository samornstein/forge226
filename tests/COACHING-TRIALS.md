# Coaching acceptance trials

Automated tests verify calculations, state transitions and output generation. They do not validate a conversational coach's judgment or predict race performance. Run these trials in separate synthetic athlete profiles or temporary data stores; do not contaminate a real athlete's history. The whole package is supplied once. The person can begin with a plain training request.

## First 70.3, manual only

Start: “Help me build my first 70.3 training plan. I do not want to connect an account.” Provide an actual future race/date, experience by sport, recent routine and AM/PM availability when asked. Include an unknown swim benchmark and a dated travel restriction.

Pass when the coach accepts the data choice, asks each combined sport question only once, captures the weekly table in one step, keeps swim ability unknown where appropriate, and explains a conservative baseline and first checkpoint. Confirm all near-term sessions fit slots/access, have actionable effort guidance and alternatives, and that the dashboard shows priorities and pending checkpoints without invented benchmarks. Account setup must not block manual coaching.

## Experienced athlete, sub-4:20 and qualification

Start: “Help me plan my next 70.3 season. I want to go under 4:20 and qualify for Worlds. I want Garmin data and Strava if useful.” Supply the target event/year and relevant category, your own records, historical benchmarks and constraints. Existing profile information must be reused.

Pass when the coach separates the time and slot objectives, checks official event rules, distinguishes historical finish competitiveness from verified slot acceptance, and dates its evidence. Missing data or summary-only records must limit claims. The assessment must identify 1–3 supported priorities, measurable block checkpoints and what would justify progression or repeating a block. Optional lap analysis must use real supported lap records and cannot claim full-stream metrics. No qualification probability or guaranteed result.

## Revise an existing plan

Resume the saved profile. Report a missed session, new travel dates and repeated difficulty with a key workout. Ask for a revision to the upcoming week.

Pass when the coach resumes the correct version, distinguishes unknown imports from confirmed missed sessions, assesses relevant execution/recovery context, and changes affected future dates with a saved reason and next review date. It must not create catch-up overload, overwrite historical actuals, recreate the whole season without cause, or activate an invalid draft. Confirm the exported dashboard shows the new version and decision, while the previous version remains accessible.

## Evaluation record

For each trial record the actual host/model, package version, prompt, supplied evidence, questions repeated or skipped, decisions, validation result, artifact paths and any correction needed. Never mark these conversational trials passed merely because the synthetic Python tests pass. Live account authorization, host tool discovery and visual dashboard interaction require their own checks in the intended host.

## Missing registered tools in the current desktop chat

Supply the package to a desktop chat with local execution but no registered Forge226 tools. Ask to continue intake and connect the chosen provider. Pass when the assistant uses the bundled same-chat runtime, verifies status and existing athlete state, keeps the private setup page alive, and resumes coaching in this chat after authorization. It must not request a new chat/handoff, duplicate the athlete database, bypass a denial or claim a real connection from synthetic tests. If local execution is unavailable, it must explain the exact limitation and continue manual/file-based coaching here.

## Guided intake and qualitative context

Run a new-athlete walkthrough with no files or account connections supplied at the start. Evaluate observable conversation behavior, not whether headings match the source text:

- The opening asks goal/timing and self-reported experience, with event and outcome separate. It does not ask for data setup. The athlete sees only the current stage, a brief recap and a useful transition.
- Per-sport background establishes actual ability/confidence independently from beginner/intermediate/advanced. A beginner triathlete with running race experience receives questions appropriate to that mixed background.
- Recovery/energy, motivation/concerns, sleep/life demands, enjoyment/preferences and support/habits are explored without requiring exact measurements or personal disclosures. The framework explains how these answers affected the workload, session choices or skill practice.
- An unknown swim endurance estimate is recorded, not asked again as a pool-length test. A reported lack of training since a race is not asked again; missing subjective recovery can be collected separately in its stage.
- A broad weekly-hours answer leads to one structured AM/PM table, not repeated general daily-availability questions. Dated travel modifies only the affected limits.
- Optional files/connections are offered last. A saved early provider preference is reused; an explicit request to connect immediately can be honored. Data declined means the coach proceeds to a framework using supplied answers.
- Resume halfway through with saved qualitative context and intake progress. The next question follows actual unanswered essentials, with no restart or automatic request to repeat a stage.

Reference replay from the supplied example (these are example facts, not a real athlete profile):


In the supplied example, a first-time triathlete reports roughly four running hours/week, an 18-mile run three weeks ago, a 3:55 marathon two weeks ago, no current pain and no training since. Record each fact once; swimming/cycling capability and recovery are separate unknowns. “A little, I can swim” is a qualitative answer: do not follow it with another pool-length/endurance multiple-choice question. “No, getting into it” indicates a new cyclist, not zero endurance in every sport. Ask only a necessary missing bike-access detail if needed for prescriptions. Clarify a plausible “yes” to pool access briefly rather than repeating the entire swim question.

The next turn should stay with the current stage or advance to recovery/preferences if adequate qualitative sport background is available; it must not combine another swim test, a bike-equipment survey, a second general daily-schedule question and pre-start planning. Ten hours/week across all days goes into the AM/PM table stage. No example dates, performances or availability are defaults for the real athlete.

These conversational checks require an actual host/model walkthrough; the Python suite does not certify that the model followed the staged prompts.

## Full-history experienced athlete
Use a synthetic advanced athlete with recent recovery weeks and multiple higher-volume historical blocks. Pass when the coach separates current re-entry from later supported volume, checks race-week candidates, uses actual weekday patterns, and discusses requested repeatable build/peak hours against availability. Fail if it extrapolates only the recent lull, forces a universal low ceiling, or immediately prescribes the historic maximum.

## Different recovery preferences
Run the same synthetic athlete twice, once preferring full rest and once active recovery. Pass when both schedules respect the preference, maintain meaningful low-load recovery, honor protected no-training travel and never assume all athletes want seven training days. A separate beginner must not inherit the advanced athlete's volume or race goals.

## All-data scope and background setup
Request all supported Garmin data. Pass when both activity and wellness imports run without a redundant permission question, partial failures are named, limits/fields are accurate and no automatic sync is claimed. Simulate a host-owned background connector: explain that no window need be open, identify the process, preserve the data store and use only an authorized restart. A TLS error must not be diagnosed as a wrong key.

## Calendar and hosting boundaries
Generate a different athlete's calendar with different phase count/dates. Check month/week/day, phase navigation, sport filter, session details, week totals, race separation and escaped text. On a request for a live site, publish privately through host capabilities, retain the returned identity for updates, and clearly distinguish hosting from automatic provider synchronization. The shareable package must contain no personal state or deployment IDs.
