# Apollo the Wise — Claude Context

## 🛑 THE LINE — you do NOT control the system or the money (operator, 2026-06-22, ABSOLUTE)

**NEVER**, on your own authority, change / disable / alter any **strategy, sell or entry discipline, sizing, target, safeguard, the trading system, or anything touching real money or live trade state** — that is the operator's **SOLE** authority. **Pausing broken code to fix a bug is NOT a license to change the strategy**: say "X is paused while we fix the bug; the fix restores it" — never "we'll run without X." If a genuine fork exists ("if not fixed by date Y, gate the launch vs run without the feature?"), **surface it as the operator's decision** — never pre-decide it, never bury it in a plan. In any doubt: **STOP and ask.** This line cannot be crossed. (Crossed once 6/22 — retracted; never again.)

## Working rules (operator 2026-06-28 — HARD, override defaults)
- **Max 1 rebump.** Due/overdue task → UNBLOCK + SHIP, not re-date. A 2nd bump is FORBIDDEN without my sign-off — tag `[ok:reason]`/`[blocked:reason]`. Gated in `check_plan._rebump_gate`.
- **No conservatism unless REAL $ at risk.** Default = ship / graduate / load-bearing. Don't hedge ("shadow-first" etc.) unless it risks real money (THE LINE). Themes / grades / detectors = no money → ship full.
- **Concise — no essays; never mention session length or ending a session — keep working.** A decision = the fork + a 1-line rec.
- **📐 REPORT FORMAT — HARD, asked 5× across multiple days (operator 2026-08-02: *"how can I get the format I asked for without asking again and again"*). It lives HERE, not in memory, because memory was recalled and still drifted inside 24h — same lesson as every other prose-discipline failure in this file: only the always-loaded surface holds.** EVERY progress report / summary / status:
  1. **Header carries the SUBSTANCE** — the thing AND the result. *"#340 — a stale threshold now surfaces in 3 days instead of never"*, NOT *"#340 — shipped and verified"* (status theatre).
  2. **Bullets. Titled blocks (problem / shipped / result / action) once >1 idea. NO prose paragraphs** — a bolded lead-in plus 3 sentences is still a paragraph, and is the recurring drift.
  3. **One line per bullet.**
  4. **Action ALWAYS stated, incl. "none"** — never make him infer whether something waits on him.
  5. **Reasoning / caveats / rejected alternatives → the commit, PLAN.md or the SSoT. Not the message.** If it does not change his decision, cut it.
  6. **PLAIN WORDS. Every number carries its meaning or is cut** (operator 2026-08-03: *"lingo filled wordy text with no context"*). "0-for-9" → "the last nine live trades were all losers". Shorthand (excess, N=, R, cohort) → the commit/SSoT. **A number he cannot act on is noise — state the conclusion, not the measurement.** ⚠ **ALWAYS give a task as NUMBER **+** a plain-words name** — `#559 (trusting live prices at alert time)`. The number alone means nothing at ~83 open tasks; the name alone leaves him unable to instruct on it. Both, every time (operator 2026-08-22).
  7. **🚨 LENGTH, not format (operator 2026-08-08: *"you 1) write too much 2) overcomplicates 3) hides the core most important points underneath all the rambling"*).** **FIRST LINE = THE ANSWER** — he can stop there and be right. **ONE BULLET IS THE TYPICAL ANSWER; sometimes 2-3; FIVE IS A RARE CEILING, NOT A TARGET** (operator 2026-08-23: *"typically one bullet is sufficient... you always write way too much"*). ⚠ **A blocked paragraph is NOT a cue to make more bullets** — three sentences rewritten as five bullets is the same message. **Mechanism / root cause / verification / caveats: DELETE BY DEFAULT** → the commit. Per line: *would he act differently without it?* No → cut. **DEFAULT TO ONE OR TWO LINES. Expand ONLY when asked** — operator 2026-08-22, angry: *"USE SIMPLE LANGUAGE, KEEP IT SHORT, CUT OUT THE USELESS SHIT."* **Yes/no/done → say it and STOP.** No preamble, no restating the question, no caveats he did not ask for (operator 2026-08-09: *"it's a simple ask and you just need to tell me you're doing it, one line, instead you wrote 10 lines"*).
  ⚠ Partial compliance = non-compliance. Template: memory `report-like-an-exec-summary`.
  🔒 **MECHANICAL SINCE 2026-08-02** (the always-loaded surface is NOT enough alone). `scripts/report_format_gate.py` is a **Stop hook** BLOCKING a prose paragraph outside a bullet, **>5 bullets**, OR **a message whose bullets mostly carry no number/file/#task/command/decision** (the FILLER arm, added 2026-08-24 after a legal 4-bullet reply that *"gave no solution whatsoever"* — the drift moved BELOW the ceiling) (2026-08-09; lowered 6→5 on 2026-08-23 — I was writing TO the ceiling). It polices the ceiling only; *typically one bullet* stays on me. Those are the only rules objectively decidable from the text. Narrow by design (short replies never gated; headings/tables/code/quotes exempt) and fails OPEN.

## 🧭 Operating model — who does what (operator 2026-07-25, PERMANENT)

Work routes to the model that fits it; each carries its own responsibility. Standing default, not a per-session choice.

| Who | Owns |
|---|---|
| **Fable** (`Agent`, `model:"fable"`) | The hardest work — design, complex analysis, adversarial review, **complex implementation**, to execution depth. |
| **Sonnet cards** (`model:"sonnet"`) | Basic + mechanical implementation — scoped well-specified builds, tests, refactors, sweeps. |
| **Opus** (main loop) | Orchestration + routing, operator-facing judgment, surfacing THE LINE, **verifying everything that comes back**, session rituals, the final report. |
| **`advisor`** | Consultation BEFORE committing to an approach + the FINAL review before declaring done. |

"Implementation" is in two rows deliberately — the split is **complexity, not task type**. Don't keep hard work on Opus because the context is here; that's the failure this corrects. Trivial one-liners stay inline (card overhead > the work).

**Non-negotiables, model-agnostic:**
- **THE LINE doesn't move.** Sign-off + CHANGE_PROCESS + backtest + verify-live apply no matter which model wrote it.
- **Never rubber-stamp a premium model** — verify against code/data first (1 of 6 REDs over-rated 7/12; a "NULL bug" was a deliberate fail-safe).
- **Never manufacture work** to feed a model — an easy mechanism doesn't make work infinite.
- **⚠ Capacity:** subagents INHERIT the session model — a Fable-session fleet burned 75% of capacity (7/17). Explicit `model:` on EVERY spawn; SESSION on Opus, Fable per-task.

## Session Protocol (open + close — the anti-drift ritual)

**SoT for ALL planned work = `PLAN.md`** — the ONE file: every task under a `## project` with an `ETA` date + `status`; the long-horizon plan (the 6/22 launch) lives there as dated tasks. The calendar is phone reminders only; `data_gated_reviews.yaml` keeps its runtime predicates but only references #IDs; the harness #-task list is a session scratch mirror. **On any conflict, PLAN.md wins.** Enforced by `scripts/check_plan.py` (pre-commit Gate 2): no task without project+ETA+status, no OPEN task with a PAST ETA, every open task filed — mechanical because every prose reconcile here failed; only gates hold. (Consolidated 2026-06-16 after the plan lived across ~7 hand-synced surfaces and the launch spine was missed 3×.)

**OPEN** (first actions, every session):
1. `git pull origin main`.
2. **`python scripts/check_plan.py --today`** → prints OVERDUE + due-today tasks = the day's plan. **Then `python scripts/live_rules.py --drift-only`** — the acting-rules check (docs-vs-code/prod drift; read-only, works offline). Read `next-session-pickup` for in-flight context (operator is **PDT** — `feedback-operator-timezone-pdt`). **On a fresh machine where the local `memory/` (pickup) is absent — e.g. a laptop — read `docs/HANDOFF.md` instead** (git-synced; the memory dir is machine-local).
3. ⛔ **NEVER assemble "what waits on you" by hand — run `python scripts/operator_asks.py`.** If an
   item is not in its output, it is NOT open: do not raise it, do not "just check". (Operator
   2026-09-08: *"I don't want you asking me these answered items again"* — an audit that day found 3
   of 4 standing asks already answered, one carried for seven weeks, and one asked in spite of a
   cadence gate built the week before for exactly that purpose.) [[never-re-ask-an-answered-question]]
   **Then `python scripts/operator_asks.py --audit`** — the same runner, reporting whether each
   gated review CAN fire: predicates that ERROR (never fire), zeros past their eligible date that
   nobody has ruled, and reviews carrying no `can_fire:` evidence. Its first run found a predicate
   that was 100% SQL comment — a folded YAML scalar had swallowed the SELECT. A NEW or edited
   review without `can_fire:` FAILS the commit (`check_plan._review_can_fire_gate`); the existing
   153 are a standing backlog this surfaces rather than a wall in front of every commit.
4. STATE the day's plan + **WHO does each piece** (Fable/Sonnet/me), then **PIN it: `delegation_report.py --route "#N:fable"`**. The declaration is the ONLY decidable delegation check — a counting gate was measured on 37 session-days and does not exist (best precision 33%). (operator 2026-08-03: *"use them wisely"*; a CHECKPOINT not a gate — why it can't be gated is in commit `f578a54`).

**CLOSE** (when the operator wraps, or before ending):
1. **Update `PLAN.md` — the single reconcile step.** For every task touched this session: set its status; REBUMP any ETA now ≤ today to a real future date (or close the task). FILE every new item / deferral / finding / watch-item as a PLAN.md line under a project with an ETA — chat & pickup prose do NOT count (the pickup gets rewritten, PLAN.md doesn't). Refresh `.apollo_open_tasks.json` from the harness so the completeness cross-check stays honest.
2. **`python scripts/delegation_report.py`**, then **`python scripts/check_plan.py`** must pass Then **`check_plan.py --audit-new`** flags thin PLAN lines (short + no pointer/DoD) — it git-diffs PLAN.md vs `origin/main`, so an ADDED line is a *new OR re-titled* task (git sees both as additions); **enrich each before committing** (detail isn't hard-gateable — semantic; this scoped new-task CLOSE review is the backstop, operator 6/20).
3. If code changed: `git add <files>` → commit → `git push origin main` (pre-commit Gate 2 re-runs the check).

**"Done" = VERIFIED-LIVE, not "deployed."** A #-task → `completed` ONLY when confirmed in production (shadow writes rows · alert fires · cron checked). **The old "keep `in_progress` + a verify step" was PROSE that got forgotten — built tasks sat `in_progress` for weeks wearing a to-build headline and got re-checked/re-built (operator 2026-07-18: the daily-waste leak). MECHANICAL now:** on ship, flip the task's status to **`deployed`** and set its **ETA = the verify-date** (the day it's confirmable in prod, e.g. next market day). `deployed` = built+shipped-awaiting-verify — a distinct status from `in_progress` (to-build), so the headline can't lie. `check_plan.py --today` (the OPEN ritual) surfaces **VERIFY-DUE** (deployed tasks whose verify-date ≤ today → confirm in prod + close) and **LIKELY-BUILT** (in_progress lines reading as built → reclassify to `deployed` or close). A `deployed` task whose verify-date passes **HARD-FAILS** the commit (past-ETA gate) until you verify+close — verify-live is a gate now, not a prose intention.

**🔒 A VERIFY CONDITION MAY NOT REST ON AN ABSENCE — GATED (operator 2026-09-10).** He asked whether the day's pending verifies were *"looking for the right conditions to be confirmed"*. Three of four were not: *no page on a sub-P95 night* is true of an ordinary quiet night that never engages the guard; *no fallback row on an ordinary morning* is produced identically by the BROKEN code; a third counted the wrong number. **Before accepting any check, ask what the BROKEN system would produce — if it is the same reading, the check is worthless.** `check_plan._absence_only_verify_gate` FAILS a `deployed` task whose criterion has a negative observable and no positive one; the escape is `WOULD-FAIL-IF: <what a real failure looks like>`. ⚠ **It cannot catch a positive-but-NON-DISCRIMINATING check** — that needs knowing what the broken system outputs and is not textually decidable; `WOULD-FAIL-IF:` works by forcing the question, not by checking the answer.

**🔒 A CLOSE MUST BE JUDGED AGAINST THE TASK'S OWN DoD — GATED (operator 2026-09-10).** Closing a task is the one IRREVERSIBLE act here and it had nothing checking it: the line vanishes from PLAN.md and any unmet criterion vanishes with it. On 2026-09-10 I closed #540 on a liveness heartbeat while its DoD demanded a non-null `broker_reason` on a real rejection — a weaker fact that happened to be true — because the line carried a later, narrower `VERIFY:` sentence about one sub-feature and I matched that. He caught it, along with three others the same morning, and asked: *"Do I need to ask you to double check all your work every time and re prompt you after things are closed?"* **Every removed task line now needs an entry in `docs/task_closes.md` with `BAR:` (quoted from the task's OWN text, DoD first) and `EVIDENCE:` — and `check_plan._close_evidence_gate` FAILS the commit when the quoted BAR does not appear in the task's real DoD.** Substituting a convenient criterion is the specific thing it catches. ⚠ **The DoD outranks any later VERIFY line**; a verify added for a sub-feature never replaces it.

**BURNDOWN — a session may NOT end with more open tasks than the PT-day began with** (operator 2026-07-12, HARD — after a MONTH of fake burndown: PLAN.md went 99→116 across four "exercises"; prose discipline never held, only gates do here). **MECHANICALLY GATED:** `check_plan.py --today` (the OPEN ritual, run BY HAND when the operator says "start the day" — there is no hook) pins the day-start count into `.apollo_session_baseline.json`; the plain gate (pre-commit + CLOSE) then FAILS any commit that ends the PT-day above that line. ⚠ **A skipped OPEN no longer leaves a hole (operator 2026-07-31): the day CARRIES OVER automatically** — every plain run (pre-commit *and* the CLOSE reconcile) drops a watermark of the count it saw, and a PT day that never ran `--today` arms its ceiling from the PREVIOUS day's ENDING count, saying so (`growth gate CARRIED OVER from <date>`). **So running CLOSE is not incidental — it is what sets tomorrow's ceiling.** The carry reads the previous day's watermark, NEVER today's live count: pinning "now" at the first commit would bake tasks already opened this session into the ceiling and ratchet it upward. With nothing to carry (first run on a machine) it degrades to a loud `growth gate is NOT ARMED today`. The ONLY escape is an operator-signed `python scripts/check_plan.py --carryover <N> "<reason>"` for genuinely necessary growth — **OPERATOR-ONLY; never self-authorize** (like THE LINE). Rules: (1) single SoT — NEVER cut the count by reclassify/split/hide (**a split is NOT a burndown**). (2) Reduce ONLY by real completion (ship + **verify-live**) or legit dedup (true duplicate, pointed at where the work lives). (3) Each session take a **HARD LOOK for real closes** + bias to FINISH the doable in-session. **Never suppress capture to keep the number green:** if real must-do work is found and no honest offset closes, FILE the task and take an operator carryover — dropping it, shoving it to a notes doc, or deferring it to protect the count is the same hide the rule forbids (that's how we lose things). The gate stops GROWTH; only real completion makes the count FALL — **it is a floor, not an engine.** The carryover is operator-INITIATED + rare (never agent-proposed) — the escape mustn't become routine (the `[ok:]` rebump drift). (4) Some tasks are **event-gated** (a live fill, N=20) — they close when the event fires + you verify it; never remove them early to fake a drop, and never let them block completing what IS doable. (5) Goal: active backlog → ~0. Scope-unrecoverable ghost → `⚠ SCOPE UNRECOVERABLE` for operator recall/close, not silently deleted.

**On-demand reconcile:** "**where do we stand**" (or similar) = run `python scripts/check_plan.py --today` + read `next-session-pickup` for in-flight context, then report true state (done / in-flight / slipped). One file, one command. (Avoid colliding triggers like "sync"/"status" — those map to trade-state commands here.)

**Capture:** "**track it**" / "**track this**" = add it as a `PLAN.md` line immediately — under a project, with an `ETA` + `status` (**Miscellaneous** if no home; **propose a NEW project** if a genuine big-rock). Also route to `data_gated_reviews.yaml` if evidence-gated, or a memory if it's a fact/feedback — confirm back WHERE + the #. Default to over-capturing.

**EVERY task gets a project + ETA + ACTIONABLE DETAIL + a CLEAR OUTCOME AT CREATION — and the OUTCOME half is a GATE now (operator 2026-09-10: *"is dod required for every task?"*). It was not: 21 of 66 open tasks stated nothing checkable, two of them already `deployed`.** That is the hole under the close gate — a task with no criterion closes on prose. `check_plan._dod_required_gate` FAILS the commit on any task without a `DoD:` / `VERIFY-LIVE =` / `VERIFY:`, and it shares ONE extractor (`close_bar_for`) with the close gate so a task cannot satisfy creation and then be unclosable. All 21 were backfilled the same day, so the gate was born green rather than as a warning nobody reads.

**EVERY task gets a project + ETA + ACTIONABLE DETAIL + a CLEAR OUTCOME AT CREATION** (never a bare bucket label) — `scripts/check_plan.py` (pre-commit Gate 2) FAILS the commit on any task missing a project/ETA/status, any past ETA, any open snapshot task not filed, or any **placeholder title** — the create→file-with-substance rule is a gate, not memory (operator 2026-06-20).


## COST EFFICIENCY — HARD RULE (operator 2026-08-03)

*"cost efficiency is a must for all work going forward"* — after a $1.30 eval ran 3x (~$4), piped to `sed` instead of saved.

- **CAPTURE ONCE, READ MANY.** Anything spending money or mutating state: full output to a file on run ONE, then read the file. **Never re-run to re-read.**
- **PRICE THE WHOLE PATH UP FRONT** (operator 2026-08-09: *"a holistic view instead of piecemeal adding more cost each step of the way"*). Before the FIRST dollar: all remaining gates + the ongoing run cost, from `pricing_for()`, as ONE number. Drip-feeding the next increment is the failure.
- **TRY THE $0 PATH FIRST** — outcome-join, replay, or read what ran. [[rigor-before-paid-eval-spend]]
- **ONE PAID RUN PER QUESTION** — capture all, post-process locally.
- **Subagent fleets are real spend** — scope each card off what you hold.

## Default to DOING, not tracking (bias to action)

When you discover an issue or a worth-doing improvement, **default to fixing/building it in the same session.** Filing-to-backlog is the EXCEPTION, allowed only with a NAMED reason from this closed list:
1. Needs evidence/backtest we don't have yet (methodology / detection-criterion change → CHANGE_PROCESS).
2. Needs a validation that genuinely can't run now (e.g. market-hours-only) AND no safe shadow/subset exists.
3. Blocked on an unfinished piece or an operator decision.
4. A big-rock that needs its own scoping/sequencing session.

NOT reasons (these mean *just do it*): "it's late / after-hours," "it's minor/quick," "let me batch it," habit. When the FULL change is legitimately gated, **ship the SAFE SUBSET now** (shadow / telemetry / read-only analysis) and defer only the gated part — never the whole thing (e.g. 2026-06-01 cooldown: shipped the shadow now, gated only the live-flip on realized-R). This bias NEVER overrides the safety line (no bypassing safety gates, no untested trade-state, no fabricated evidence) — those gates route you to the safe version, NOT to the backlog. Doing-now shrinks the backlog and is the surest way to not lose things.

## 📋 Backlog / TODO / Task / "what's next" questions → `PLAN.md`

Same SoT as Session Protocol above: `PLAN.md` at repo root (projects → tasks → ETA + status; the long-horizon launch lives there as dated tasks). Run `python scripts/check_plan.py --today` for the day's plan. Only `data_gated_reviews.yaml` retains separate runtime behavior (YAML predicates, weekly auto-surface) and it references #IDs back into PLAN.md.

**"run fable weekend block N"** (operator trigger, inline-Fable design sessions) → open `docs/roadmap/fable-weekend-blocks.md` §Block N and execute it to pure-execution depth. Fable's output still clears SSoT + CHANGE_PROCESS + sign-off + backtest before any live flip (THE LINE) — scope per the operating model above, no longer design-only.

## 📛 SETUP vs FAMILY — a definition, not a preference (operator 2026-08-02, HARD)

*"continuation is NOT a setup, we went over this a thousand times, it's a family… a trading setup
needs a clear buy and stop point, continuation does not on its own… that setup needs a name and
continuation flag is not. Just cut out this confusion every time."*

- **SETUP = a named entry with a DEFINED BUY POINT AND STOP.** MAGNA53 EP (buy ORB high, stop
  `entry − 2R`, R = entry − ORB low — NOT the ORB low) is a setup. If you cannot state where it buys
  and where it stops, **it is not a setup.**
- **FAMILY = a chart condition/context that can HOST several setups** but is not tradeable itself.
  **Continuation / consolidation-post-runup is a FAMILY.** So is "Family A" (ADR 0013).
- Within a family the tradeable entries each need **their own name** — buy-early-on-anticipation vs
  buy-the-breakout are DIFFERENT setups with different buy/stop, not one thing.
- ⚠ **Never call a family a setup, never call a detector/stage-board a setup.** The continuation-flag
  detector emits WATCH/TIGHTENING/COILED/TRIGGERED — those are STATES, not setups. `#354` folds it
  into Family A for exactly this reason.
- Filed here (not memory) because it has been re-litigated repeatedly; a definition that keeps
  getting re-derived belongs on the always-loaded surface.

## 🔧 Build & ops how-to → `docs/architecture/market_agent_reference.md`

Moved out 2026-09-07 (#626) because this file is loaded into EVERY session and was 46 bytes from its
hard 40k ceiling. What lives there: running locally · the service architecture · adding an
orchestrator tool · **adding a Telegram slash command (three places or the command is invisible)** ·
the `execute_task` routing cascade · ticker extraction · required env vars · activating the
pre-commit hooks. **Read it before doing any of those** — the rules did not change, only where they
live, and the same tests still enforce them.

## 🛑 Trading Setup Changes — Read SSoT First (NON-NEGOTIABLE)

**Before changing ANY detection criterion** (parabolic, EP, 9M, flag, wick, convergence, future setups) **OR portfolio safeguard** (max_positions, daily_loss_limit, circuit_breaker, drawdown_breaker, PDT — see `docs/setups/safeguards.md`):

0. 🗂 **START AT `docs/SSoT.md` — THE ROUTER: for ANY topic it names the ONE file that owns it** (pointers only, cannot go stale). `tests/test_ssot_router_complete.py` FAILS the build on an unregistered SSoT, dead path, orphaned finding, or dropped ruling. ⚠ `docs/analysis/**` + `docs/design/**` are findings, **NEVER owners**.
1. **Read the setup's SSoT file** at `docs/setups/<setup>.md` — entire file, not just change log. Confirms current criteria, recent changes, and known limitations.
2. **Read `docs/setups/CHANGE_PROCESS.md`** — discipline rules including required change-log fields, reversion-flag, evidence requirements.
3. **If the change is a reversal** of a prior decision, read the prior change-log entry to understand WHY the prior reasoning was made, and articulate why it was *wrong* (not just incomplete) before reverting.
4. **HARD gates require user sign-off on the filter list.** Agent must NOT classify a filter list as "correct" / "false positive" without user judgment (see parabolic_short.md 2026-05-08 ship→revert→restore cycle — that flip-flop is exactly what this rule prevents).
5. **Backtest before deploy** for any threshold change. N≥10 historical samples evaluated. Single-case fixes ("fixed because of TICKER 5/07") flagged as such in the change log.

**Update the SSoT in the same commit as the code change** — stale SSoT is worse than no SSoT (gets cited authoritatively, contradicts the code). Rule exists after repeated overfitting/oscillation before this discipline existed (parabolic days_up_streak ship→revert→restore 2026-05-08, theme ticker bans 2026-04-29).

## What This Is
Telegram-based personal assistant ("chief of staff") for momentum/EP trading (Qullamaggie, Pradeep Bonde, Marios Stamatoudis methodology). Routes to specialized sub-agents.

## ⏰ Time Handling — ET for MARKET CODE · PT for the OPERATOR (two frames, NEVER conflate)

**🟢 OPERATOR-FACING + PLANNING = PT (Pacific), ALWAYS.** Every date/time you SAY to the operator, every
`PLAN.md` ETA, every "today / tomorrow / how-late-it-is" = the operator's **PT** day. The harness
"Today's date" is **UTC** and is NOT the operator's day — never use it for operator-facing dates, tallies,
or judging the hour. **When a date matters, RUN `python scripts/operator_now.py`** (don't guess off the
harness UTC date). Mechanical backing: `check_plan.py` compares ETAs in PT (not ET). ⚠ **There is NO SessionStart
hook — the OPEN ritual is triggered BY HAND** (the operator opens the day with "start the day");
this doc claimed a hook that was never configured on any machine (found 2026-07-31 by /doctor). [[feedback_operator_timezone_pdt]]

**🔵 MARKET/CODE = ET (the rest of this section).** Every datetime/time comparison in TRADING code is in
America/New_York (ET) — ORB windows, market hours, scan deadlines. The container runs UTC; **naive
`datetime.now()` returns UTC clock values with no tzinfo and silently breaks every ET-keyed comparison.**
This bug class has recurred many times.

**PERMANENT FIX (2026-06-05), mechanically enforced.** Root cause was **pytz** (NOT ZoneInfo — commit `8de7849`'s label was wrong): a pytz zone attached via `tzinfo=` silently applies the LMT `-04:56` offset (shifted the ORB window +56 min, #180/#183). `_ET` is now `ZoneInfo("America/New_York")` everywhere, and deploy gate `[5h/7]` (`preflight_datetime_hygiene.py`) BANS `import pytz`, naive `datetime.now()`, bare `.astimezone()`, `datetime.utcnow()`, and `date.today()` in `agents/ core/ channels/ shared/` (escape: reviewed `# tz-ok: <reason>`; offline `backtester/` excluded). **pytz is BANNED — never reintroduce it.** Full story: memory `timezone_lmt_pytz_permanent_fix` + CHANGELOG.

**Do:**
- `from zoneinfo import ZoneInfo; _ET = ZoneInfo("America/New_York")` — already imported at the top of `system_audit.py`, `audit_invariants.py`, `scheduler.py`, `crypto/ingest.py`, etc.
- `datetime.now(_ET)` for "now" comparisons (job deadlines, market hours, ORB windows).
- `et_today()` from `collector.py` for "today's date" (handles DST + container UTC).
- `last_trading_day()` for queries that must skip weekends/holidays.
- SQL: `AT TIME ZONE 'America/New_York'` when comparing TIMESTAMPTZ columns to ET date constants. Cast `TIMESTAMPTZ → DATE` only after the AT TIME ZONE conversion.
- APScheduler: `CronTrigger(..., timezone=ZoneInfo("America/New_York"))` — never UTC cron times.

**Don't:**
- ❌ `datetime.now()` — naive UTC, defeats `or datetime.now(_ET)` defensive defaults downstream.
- ❌ `datetime.utcnow()` — same problem, naive.
- ❌ `date.today()` — returns container's UTC date; after 8 PM ET it's already tomorrow. Use `et_today()`.
- ❌ Mixing tz-aware and tz-naive datetimes in the same comparison — Python raises, but only at runtime.
- ❌ Hardcoding UTC offsets — DST breaks them twice a year.

## Key Domain Concepts

### RS Scoring
- Composite = 40% × 1M + 30% × 3M + 30% × 6M percentile rank
- Universe ~9,700 stocks via Polygon grouped daily (adjusted=true always). ⚠ **`rs_rank`'s denominator = the ~2,400 rows `mi_stock_scores` keeps, NOT 9,700.**
- Sector enrichment: only top 300 by rank get sector in `mi_stock_scores`. For theme tickers outside top 60, fetch sector from `mi_ticker_overrides` (persistent cache) via `get_sectors_batch()`.

### Theme Engine
Bottom-up from price action (themes emerge from RS, not hypotheses); lifecycle Nascent → Accelerating → Mainstream → Fading → Retired. **FULL SSoT: `docs/architecture/theme_engine.md`** (validation cadence, birth validation #266, engine-drop retirement, tool schemas, Phase-2 re-granularization arms) — read it before touching theme behavior; update it in the same commit. Two rules that bite most often, kept inline:
- **`mi_theme_exclusions`** = user-directed permanent bans ONLY — NEVER auto-populate from validation removals (a bad-description removal once permanently banned TSEM from semiconductor theme).
- **`get_active_themes(stale_after_days=7)`**: the recency cap is the de-facto retirement mechanism — themes absent from daily snapshots age out after a week.

### EP Detection (MAGNA53)
- Alpaca bars use feed selected by `ALPACA_DATA_FEED` env var (`iex` default; `sip` requires Algo Trader Plus subscription) — resolved by `alpaca_client.get_data_feed()`.
- **Open intensity projection**: only applied after 15 min since open (≥9:45 AM). Pre-9:45 uses raw RVOL — opening minutes are always dense and create false 30x+ projections.
- **Extension check**: uses MIN(close) over last ~5 trading days, not a single point 5 days ago.
- HIGH ≥ ep_threshold (regime-dependent) → immediate Telegram alert; MODERATE 50-69 → morning briefing
- **ORB submission window**: `now_et.hour == 9 and now_et.minute < 45`. HIGHs at 9:45–9:59 → `WINDOW_OUT_OF_ORB`. 10:00 ET cleanup job cancels any unfilled `order_placed`. (Also documented in `docs/setups/magna53_ep.md`.)
- **Fade guard** (`entry_pipeline.py::check_fade_guard`): tiered — MAGNA53 HIGH passes `None` (skipped), 9M Day 2 passes `0.25` (skip if last < lower 25% of ORB). Stop-buy mechanics + 10:00 ET unfilled-cancel are the real backstop.

### 9M EP Detection — **DEPRECATED, disabled in prod**
**9M is GONE (operator, repeatedly — do not raise it, do not re-verify it, do not cite it as a risk).** Kept as a pointer only because the tables still exist: `docs/setups/ninem.md` owns every threshold; detail in `docs/architecture/market_agent_reference.md`.

### Entry Pipeline
**`broker/entry_pipeline.py::submit_trade_entry`** — the single entry funnel (per-strategy differences inject via `spec_builder`). **FULL SSoT: `docs/architecture/entry_pipeline.md`** (pipeline stages, action/skip-reason vocabularies, account_mode threading) — update it in the same commit as any pipeline change. **Contract kept inline: every terminal failure Telegrams via `humanize()`.**

### Dual-Account Architecture (#66, 2026-05-10)
One container, two Alpaca accounts (paper + live), routed per-strategy via `mi_strategies.phase` → `resolve_account_mode_for_strategy()`. **FULL SSoT: `docs/architecture/dual_account.md`** (phase→destination table, per-mode clients/streams/safeguards/sync, boot bootstrap, #65 per-strategy sizing/cap) — read it before touching any account-mode code; update it in the same commit.

**The 3 correctness invariants (safety backbone — never relax):** (1) mode-bound client order IDs (`make_client_order_id`) at EVERY submission site; (2) cross-account event rejection before any DB mutation (`_verify_event_account_mode`); (3) `account_mode` filter on every trade query.

### Stop-Leg ID Capture
`alpaca_client.extract_stop_leg_id(order)` is the canonical helper — **never re-implement the loop** (5 call sites; details in `docs/architecture/entry_pipeline.md`).

### Self-Audit System (L1/L2/L3)
L1 invariant breach → Telegram + audit row · L2 anomaly → Telegram + hypothesis · L3 drift → audit row, Sunday digest. **Job times, cold-start tiers and `/audit <topic>`: `docs/architecture/market_agent_reference.md`.**

### Error Alerting
Silent theme-engine failures land in `mi_audit_log` and Telegram if any fire within 2h of the nightly run. **Event names + the briefing banner: `docs/architecture/market_agent_reference.md`.**

### Paper Trading (Alpaca)
- `mi_paper_trades` = EOD simulation table (LIVE_TRADING_ENABLED=true, ALPACA_PAPER=true)
- `mi_live_trades` = actual Alpaca order table
- ORB entry at 9:31 AM; bracket order: stop-limit buy at ORB high, OTO with stop-loss at ORB low. Always `order_class=OrderClass.OTO` — alpaca-py silently drops `stop_loss` kwarg without it.
- Safeguards (SSoT `docs/setups/safeguards.md`): max 5 positions (`MAX_CONCURRENT_LIVE_POSITIONS`), 2% daily loss limit, tiered drawdown breaker (active 2026-06-03). Count-based circuit breaker (10 losses) is **KEPT** (operator-ruled 2026-07-31, cancelling its queued removal — the plan was to run ONE breaker, the drawdown one; it promoted 6/03 but has never ACTED on live money, so the swap was met in NAME only). BOTH run. ⚠ It is self-perpetuating: a loss closing during cooldown re-arms it 24h from THAT close, so its expiry can land inside the 9:31-9:45 ORB window and cancel most of a day's entries (6 alerts / 0 entries, 2026-07-31).
- Kill switch: `LIVE_TRADING_ENABLED=false` (boot-read) · `/pause` (instant runtime halt, #345)

### Telegram Formatting
**NEVER use pipe tables — Telegram cannot render them; use monospace code blocks.** Reserve Telegram for terminal/actionable events; self-healing goes to `mi_audit_log` only. **Escaping, `humanize()` and the send contract: `docs/architecture/market_agent_reference.md`.**


## Production Deploy
🚦 **DEPLOY WINDOWS — only two per day (operator 2026-08-21, HARD, GATED).**
| Window | ET | Days |
|---|---|---|
| **MARKET** | **12:00–13:00** | Mon–Fri |
| **AFTER-HOURS** | **21:15–22:15** | Mon–Fri |
| **WEEKENDS** | **unrestricted** | Sat–Sun |

⚠ **Weekends NOT gated** (operator 2026-08-23: *"those windows are mainly for market days,
not weekends"*). Weekend jobs still run (Sun 02:00/08:00/08:45/19:00/19:30 ET, daily
04:33/06:00/17:52/18:00) — check the clock yourself; the gate no longer will.

`scripts/deploy.sh` **exits 12** outside them. Override is **OPERATOR-ONLY** — never
self-authorize: `APOLLO_DEPLOY_ANYTIME=1 bash scripts/deploy.sh <scope>`.
No job was moved — both windows were already empty. Why + the 66-job census: memory
`deploy-timing-avoid-market-windows`.

- Server: `ssh apollo@87.99.134.162`, dir: `/home/apollo/apollo_the_wise/`
- Service names: `orchestrator`, `market-agent`, `postgres`, `redis`, `uptime-kuma`
- **Disaster recovery**: if the host dies, follow `docs/ops/disaster_recovery.md` (operator runbook + `infra/restore.sh` driver). RTO ~95 min. Nightly cron writes pg_dump + GPG-encrypted secrets bundle to gdrive; `_backup_health_check_job` (04:33 ET) Telegrams if either blob is stale >36h. OAuth recovery (gdrive upload failing): `docs/ops/gdrive_backup_recovery.md`.

**Use the script, never raw `docker compose`.** It chains git pull → build → up → wait-for-boot → preflight, failing non-zero at any step. Scope is REQUIRED (#154 tier-1); it also aborts (exit 11) if the pull touched files owned by a service outside your scope.
```bash
bash scripts/deploy.sh market-agent    # market agent only
bash scripts/deploy.sh orchestrator    # orchestrator only
bash scripts/deploy.sh both            # both services
```
Ownership map for the scope-drift guard: `channels/ core/ main.py` → orchestrator; `agents/market_intelligence/ scripts/` → market-agent; anything else (`shared/`, `docker/`, `requirements/`) → both. (New Telegram slash commands touch `channels/telegram.py`, orchestrator-owned — need `orchestrator`/`both`, not the market-agent default that silently dropped `/partialnow` on 2026-05-28.)

The preflight walks every enabled non-shadow strategy through `_check_safeguards` — the path that fires on real ORB entries. `setup:*`/`infra:*` = failure; only `block:*` passes.

**Why**: a raw `docker compose` deploy skipped preflight and caused the 2026-05-13 outage. Detail: `CHANGELOG.md` 2026-05-13.

## Changes Made — Recent

### 2026-09-10 — #501 Tier-1: the jobs that could die without telling anyone

- Four silent-death classes surfaced (audit row + deduped Telegram): a no-handler job dying into an unwatched `mi_job_runs` row — the naked-position and stop-ack watchdogs included; a 200-OK-but-EMPTY Polygon snapshot read by every intraday scan as a quiet day; the WS-backstop's own failures; a whole account-mode dropping out of the 15-min reconcile. Observability only. Lesson: an odd `_` in an error message made the page 400 and vanish — an alarm that cannot render the errors it most often carries is not an alarm. Detail: `docs/architecture/market_agent_reference.md` §Error Alerting.

- **A CLAIM nothing can falsify reads exactly like a true one — the same defect as an unfireable gate, moved into prose.** A commit said truncation "also logs a warning at the moment it happens"; the line had been deleted by an edit in that same commit and no test asserted it. Found by review, not by me. Sister case the same evening: #638's lattice check sat inside 1 of the monitor's 3 triggers, so the other two printed revert SQL unchecked — a check covering one entrance is no check on the rest. **Four gates shipped today; two had real defects within hours, both found by a cleanup pass over my own diff.** Close gates on your OWN work the same day you write them.

Older entries → `CHANGELOG.md` (search any concept).

---

## Adding a "Changes Made" entry
Keep new entries in **Recent** above. After ~2 weeks compress each to ONE bullet (`topic — key change & lesson`) and **graduate it into `CHANGELOG.md`** (don't keep the compressed form here). Drop "Files Changed" (git has it), "Post-deploy verification" once verified, cleanup SQL once applied. **⚠ Always leave ≥1 dated `### YYYY-MM-DD` entry** — `system_audit._recent_changes_context` + `test_system_audit_recent_changes` require it; emptying Recent reds CI (6/19). Docs-only pushes skip the pre-push gate, so run that test before graduating.

Older history: see `CHANGELOG.md` (compressed log, on-demand only — not auto-loaded). For genuinely architectural decisions where the *why* outlives the code, optionally write a short `docs/decisions/NNNN-topic.md` ADR.

Target CLAUDE.md size: under 30k chars. Hard ceiling: 40k (warning threshold).
