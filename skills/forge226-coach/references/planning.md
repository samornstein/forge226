# Strategy, session design and revisions

Use [the coaching loop](coaching-loop.md) for assessment, block checkpoints and revision decisions before populating this calendar.

## Race contract and framework

Record exact event, discipline/distance, race date, planning start/end and priority. Browse official race/athlete guides for current course and rules when available; cite actual sources and retrieval dates. Confirm date conflicts with the athlete. Historical climate is not a forecast. If lookup is unavailable, label course details unknown rather than guessing.

Assess feasibility from the athlete's actual recent consistency, not only lifetime experience. Build phase goals, dates, volume ranges, sport distribution, key-session progression, recovery intent, strength, race specificity and taper where appropriate. Explain each phase's contribution. Include travel and access restrictions at framework level. Do not force fixed phases or a universal volume-ramp percentage. Separate aspirational performance targets from supported predictions; use ranges and assumptions when estimating outcomes.

Advanced planning should address the athlete's current limiter and tradeoffs: sport-specific frequency, intensity distribution, long-session durability, race-position/terrain practice, bricks, pacing rehearsals, practiced fueling and transitions. Preserve effective established training; more complex sessions are not inherently better. Avoid consecutive hard days by default. Deliberately clustered stress for an experienced athlete needs explicit rationale, demonstrated tolerance, recovery placement and athlete agreement.

## Executable prescriptions

Each session has a purpose, AM/PM slot, minutes including warm-up/cool-down, intensity definition, detailed sets/recoveries, execution cue, success criterion and shorter/easier alternative. Swim set distances must sum to stated total, using the athlete's pool units and allowing recovery time within slot limits. Bike/run distance estimates are optional ranges based on known pace/conditions; never fabricate distances just to imitate the app. Bike targets use % FTP; include dated threshold reference. Running uses supported pace/HR/RPE with terrain and heat caveats. Never transfer run HR zones to cycling by default.

Use duration and recent consistency to govern progression. For advanced athletes distinguish threshold work, race-specific endurance, technique and recovery by stimulus and context. Avoid designing every workout as a test. Explain fueling practice based on prior tolerance and event demands; verify current authoritative guidance for specific quantitative advice. A performance goal never overrides health or calendar constraints.

The next 1–2 weeks are executable detail; later calendar entries are provisional and marked accordingly. Include rest/travel days and the exact race date. Date-specific limits override recurring slots. Sum all sessions in each slot; do not join AM and PM availability into one continuous long session. Race start uses a separate race entry; race-day training must still respect explicit no-training constraints. Discuss event-day exceptions rather than silently exceeding availability.

## Review and versioning

Before activation review: race/date coverage; AM/PM and weekly caps; travel/access; baseline realism; threshold confidence; recovery and cross-sport stress; key-session progression; swim arithmetic; race specificity; taper; nutrition assumptions; plan/actual separation. Categorize findings as blocking, material or advisory with corrections.

A separate reviewer may be used only when available and authorized by the host/user. Otherwise perform a deliberate self-review and label it that way. Never claim two independent coaches when one model reviewed its own draft. Validation scripts are structural checks, not a coaching endorsement.

When changes are proposed, show changed dates, old/new prescriptions, reason and weekly-hour effect. Default to revising only the next seven days. If strategy must change, state why and present the strategy revision before regenerating affected weeks. Save a draft; retain the active plan until the requested change is authorized. If approval was already explicit for the specific edit, apply after checks without repeating the question.

Keep append-only version snapshots and a concise receipt: state version, parent version, generated date, evidence cutoff, source strategy, review type/findings, checks actually run, assumptions, changes, approval status. On a failed generation, keep the active plan and files usable. Do not copy Forge226's internal API credentials, hard-coded model names, or database identifiers.


## Capacity, ambition and recovery preference
Use full-history evidence to set the later build, and recent tolerance to set the starting block. When an experienced athlete requests repeated higher-volume weeks, assess that target explicitly against repeated historical training, current constraints, the available runway, and recovery. Do not silently impose a low-volume ceiling from a short recovery window. Do not prescribe any fixed hours from this package: every athlete's supported volume differs.

Show dated weekly volume targets including recovery/travel weeks, repeated build weeks, peak and taper. Make peak volume conditional on absorbing preceding weeks. Add appropriate aerobic bike/swim time before using extra running merely to fill a time budget. Weekly availability is a ceiling, not a target. A fixed full rest day may make a requested peak mathematically impossible; explain the tradeoff and honor the athlete's stated preference.

Ask once whether they prefer full rest, active recovery, or flexibility, unless known. Active recovery is a distinct low-load session with purpose, minutes, easy effort and an easier/stop option; it is not a disguised quality workout. Use Swim/Bike/Other with `recoveryType: "active"` if helpful. Preserve protected no-training travel, illness/injury constraints, and the option to rest when needed. Do not default every athlete to seven training days or to mandatory Monday rest.

Inspect historical day-of-week patterns before rebuilding the schedule. Preserve proven long-ride/brick/long-run and recovery placement where feasible; avoid consecutive hard days unless explicitly justified. Never merge separate AM/PM slots to recreate an old continuous session. When increasing volume, show old/new weekly totals and check combined per-slot minutes, aggregate date-specific daily caps, travel equipment access and race-day exceptions.

## Design a progression from the athlete's resources
Ask which sessions the athlete values and inspect available activity titles, dates and local training slots. Treat uploaded coach plans and workout lists as reference material. Select sets for their purpose, adapt their dose and recoveries to the athlete, and clarify ambiguous notation before using it. Record pool access, preferred quality days, travel equipment and session-duration floors per athlete. A minimum ride duration and minutes of interval work are distinct quantities.

Give each quality workout a main set, relative or benchmarked intensity, recovery between reps, warm-up, cooldown, total duration, purpose, execution cue and shorter alternative. Count only recoveries actually prescribed. Check the arithmetic and all other sessions sharing the slot. Use current fitness for pace and power. Historical FTP and goal race pace can inform comparisons; validate race power and run effort together in bricks.

Build purposeful work from the foundation phase onward. Use threshold, track or hills, selected steady segments in long runs and event-specific bricks as appropriate. For cycling, distinguish threshold, sweet spot, aero endurance and sustainable race effort. Choose time or distance reps to suit the athlete, terrain and session goal. Repeat a benchmark when comparing adaptation; vary continuous work duration, recovery, posture, cadence or speed when the intended stimulus changes. Review the whole week, allow recovery and taper, and state which run(s) to retain or shorten when life interrupts.

For planned runs optionally save runDose as an object mapping effort names to positive minutes of work. Exclude warm-up, cooldown and recovery jogs. Mixed sets may have multiple efforts. For distance work, keep reps and recoveries explicit, estimate minutes from current evidence and set runDoseEstimated to true; if pace is unknown leave minutes unknown. Compare actual lap times and next-day recovery before advancing. Never treat another athlete's workouts, goals or dose as a default.
