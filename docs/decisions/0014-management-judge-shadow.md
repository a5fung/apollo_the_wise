# ADR 0014 — P3 Management Judge (SHADOW, telemetry-only)

**Status:** PROPOSED (2026-06-17) · v2.0 pull-forward, launch-DoD §8 · runway Wed–Thu 6/17–18.
**Decision point:** the grade judge (ADR 0011) governs ENTRY. P3 governs the *second* decision —
**EXIT / position management** — as a SHADOW LLM second-opinion, accruing the agree/disagree-with-
mechanical evidence the real (load-bearing) P3 will need. **Zero execution authority.**

## Decision

A daily **16:00 ET** pass over open live positions runs one holistic LLM call per position and
emits a **bounded enum verdict** — `HOLD · PARTIAL_TAKE · TRAIL_TIGHTEN · FORCE_EXIT` — plus a
rationale, persisted as a telemetry row. It mirrors the grade-judge pattern: Opus, fail-open (a None
verdict writes nothing / audit-only), bounded output, the operator (later) labels it. **It never
submits, cancels, or modifies an order** — the mechanical exit system (stop trail, partials,
time-stop) remains the sole authority; P3 only *observes and opines*.

## Inputs (per open position) — reuse, don't rebuild

From `db.get_open_live_trades()` (the canonical open-position reader): ticker, entry_price,
stop_price, remaining_shares, hold_days, ep_score, catalyst_quality, alert_date, ORB levels,
account_mode. Plus, fetched at pass time:
- **current price** — from a **live SNAPSHOT** (`collector.get_snapshot_all`), NOT `mi_daily_closes`:
  the 16:00 ET pass runs BEFORE the 17:00 nightly pull populates today's close (advisor C). Tonight's
  after-hours smoke gets the last print — fine for machinery, but "R looks off tonight" would be the
  stale price, not the math.
- **`pct_from_entry`** = `(px − entry) / entry` — always well-defined, the primary move metric.
- **`r_multiple`** = `(px − entry) / (entry − orb_low)` — the ORIGINAL ORB-entry risk per share.
  ⚠ Use `orb_low`, NEVER the trailed `stop_price` (FPS proves it: stop 59.03 > entry 53.79 → a
  NEGATIVE denominator → garbage R that won't throw, advisor A). Emit R **only** when `orb_low` is
  present AND `< entry`; else None. CAVEAT: `orb_low` is the correct initial-risk ref for MAGNA53 ORB
  entries; **9M Day-2 stops on the prior-day low** (not ORB low) — reconcile the 9M risk basis in
  part 2 when a 9M position is open (until then, R is None / ORB-only).
- the **original entry thesis** (the catalyst + the judge tier/grade from `mi_ep_alerts`) — so the
  judge weighs "is the thesis still intact" not just price;
- the **mechanical posture** as DESCRIPTIVE fields (current trailed stop vs entry = profit locked or
  not; whether a partial was already taken; time-stop eligibility #91) — recorded for the operator to
  judge agreement at label time, NOT compared into a bool here (see schema).

## Output schema + telemetry table `mi_position_mgmt_decisions`

One row per (position, pass): `position_id, ticker, decision_date, account_mode, verdict (enum),
rationale, pct_from_entry, r_multiple (nullable), hold_days, current_price, trailed_stop, orb_low,
stop_above_entry (bool), partial_taken (bool), time_stop_eligible (bool), model, created_at`. Bounded
enum CHECK constraint, like the skip-reason/action vocabularies.

**No auto-computed `agree_with_mechanical` bool (advisor B).** The mechanical system has no verdict in
the 4-enum vocabulary — at a 16:00 snapshot it is almost always "holding with stop at X," so a baked
"agreement" flag collapses to "did the LLM say HOLD" and mapping PARTIAL_TAKE/TRAIL_TIGHTEN onto what
the mechanical already did intraday is a temporal-granularity mismatch. More importantly, computing
the comparison ourselves IS the agent self-certifying — the exact thing ADR 0011 says the OPERATOR
owns. So part 1 records the raw verdict + rationale + the full position snapshot + the mechanical
posture as descriptive fields; **agreement is assessed at operator label/review time, not now.** (Any
convenience flag stays a transparent `verdict == 'HOLD'`, named for what it is — not a fuzzy
"alignment.") Bonus: this removes any need to encode the mechanical exit rules tonight.

## Safety (the line)

- **SHADOW**: no order submit/cancel/replace, no trade-state mutation. Telemetry + a digest line only.
- **Fail-open**: LLM None/timeout → no row, audit `position_mgmt_judge_null` (counted), never raises.
- **Role**: INTELLIGENCE (it reads position state via DB + a price fetch, emits telemetry). Reads are
  DB-sourced ground truth (`feedback_scheduler_aggregators_db_sourced`); no module state.
- **Bounded vocabulary**: the 4-enum verdict, validated; an out-of-enum LLM answer → fail-open.

## Reuse map

- LLM call shape + fail-open + bounded-JSON parse: mirror `ep_grade_judge.grade_holistic` /
  `assemble_judge_inputs` (a sibling `manage_holistic` / `assemble_mgmt_inputs`).
- Position read: `get_open_live_trades()`. Current price: `collector.get_snapshot_all()` /
  `mi_daily_closes`. Entry thesis: `mi_ep_alerts` join on (ticker, alert_date).
- Job placement: a 16:00 ET `audit_wrap`'d scheduler job (`position_mgmt_judge`), classified in
  `INTELLIGENCE_OWNED_JOB_IDS`; pattern = the EOD digest jobs.

## Part 1 (today 6/17) vs Part 2 (Thu 6/18)

- **Part 1 (this build):** the judge module (`assemble_mgmt_inputs` + `manage_holistic`, pure-ish +
  unit-tested), the `mi_position_mgmt_decisions` schema + writer, and a **read-only smoke** over the
  2 current open positions (FPS 15d/stop-above-entry, QURE day-0) — no scheduler wiring yet.
- **Part 2 (Thu):** wire the 16:00 ET scheduler job + the EOD digest line + verify-live (rows written
  on the first real pass). Operator labeling of the agree/disagree rows begins accruing.

## Why this is safe to build now (markets closed, pre-launch)

Telemetry-only with zero execution authority = it cannot disturb live trades. It's the judge pattern
we just hardened, applied to the exit decision; the launch carries it as a shadow seed (DoD §8),
graduating to load-bearing only post-launch under its own evidence + CHANGE_PROCESS + sign-off — the
exact arc P2 tape (#299) and the grade judge (ADR 0011) followed.
