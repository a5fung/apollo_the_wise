# Task close ledger — every task that left PLAN.md, and what it was judged against

**Why this file exists (operator 2026-09-10).** He spent a morning catching four bad calls in a
row — a task marked `deployed` that was never deployed, two verify conditions that could not fail,
and a task CLOSED on the wrong evidence — and then asked the question that produced this file:
*"Do I need to ask you to double check all your work every time and re prompt you after things are
closed? You can expect me to do this every time. How do we solve this?"*

The answer is not that I will be more careful. Every prose commitment in this repo has failed and
been replaced by a gate; this is that gate for closes. **A close was the one irreversible act with
nothing checking it** — a closed task simply disappears from `PLAN.md`, and any unmet criterion
disappears with it, silently and permanently.

`check_plan._close_evidence_gate` (pre-commit) FAILS the commit when a task line is removed from
`PLAN.md` without an entry here, and — the part that matters — when the `BAR:` quoted does not
actually appear in the task's own DoD. **Substituting a convenient criterion for the real one is
the specific failure it catches**, because that is what happened to #540.

## Format

    ## #<id> — <one-line what it was> (<YYYY-MM-DD>)
    BAR: <quote the criterion from the task's own line — its DoD if it has one>
    EVIDENCE: <what was observed in prod that satisfies it — a query, a row, a count>

`BAR:` must be quoted from the task, not paraphrased into something easier. Where a line states no
DoD or VERIFY criterion at all, `NO-BAR-DECLARED: <why closing is right anyway>` is required
instead — deliberately awkward, because closing a task that never said what done meant should be.

---

## #582 — theme_synthesis truncation guard (2026-09-10)
BAR: tonight's synthesis run completes and its audit row reads normally
EVIDENCE: The 09-09 18:05 run — the first after the 09-08 21:15 deploy — recorded
`stop_reason='tool_use'`, 63 candidates → 2 proposed → 1 kept, and wrote no `theme_synthesis_error`.
The `n_proposed` field is parsed downstream of the guard with no branch between, so the row proves
execution passed THROUGH it; `if is_truncated(resp)` and the `theme_synthesis_error` event were both
confirmed present by importing the module inside the running apollo-market container.
⚠ Honest limit, recorded rather than glossed: this is a NEGATIVE check — the guard's firing side is
covered by tests, not by prod. The task's own criterion was written that way ("a truncation is rare,
so the verify is that the guard does not misfire on healthy runs").

## #452 — same-family exposure hook (2026-09-10)
BAR: the hook logs on a real entry evaluation. If Monday passes with entries evaluated and still zero
rows, the hook is INERT and that is a bug, not a wait
EVIDENCE: Five `exposure_family_checked` rows on 09-08 at the ORB. PHVS reads "0 same-family
open(s), breach=False" — the real comparison branch, not the no-theme-membership early exit — so the
hook demonstrably computed rather than merely running. The promote-on-3-breaches question stays in
its registered gated review (`exposure_family_cap_promotion_r2`), which is where a future decision
belongs, not in an open task.

## #471 — theme re-granularization, parent/child depth (2026-09-10)
BAR: VERIFY-LIVE = `mi_themes.parent_theme` NON-NULL for the cyber-vuln child
EVIDENCE: "Cyber Exposure Management & Vulnerability Assessment" reads parent_theme = "Network
Security & Zero-Trust Edge" on prod. 461 child themes exist of which 234 are live (94 Nascent,
79 Mainstream, 55 Fading, 6 Accelerating), and the 09-09 17:00 run alone produced 19 more — so the
mechanism is producing, not a single fixture row.

---

## Re-opened after a bad close — kept here because the mistake is the lesson

## Lesson — task #471, closed 2026-09-10 07:28 and re-opened 2026-09-11

⚠ Not a close record — #471 is OPEN again. Deliberately not a `## #<id>` heading so the gate cannot
read this post-mortem as a justification.
ITS REAL DoD: **fixture replays green + a synthetic unassigned cluster fires the veto alert +
promotes on no-veto** — three clauses joined by ` + `.
WHAT I QUOTED INSTEAD: `VERIFY-LIVE = mi_themes.parent_theme NON-NULL for the cyber-vuln child`.
That is a real line in the task, and it is not any of the three clauses. `close_bar_for` ranks DoD
ABOVE VERIFY-LIVE for exactly this reason.
WHY NOTHING STOPPED IT: I closed it at **07:28**; `_close_evidence_gate` shipped at **08:28** the
same morning. It missed the gate by one hour. Run against it today the gate fails it outright —
`close_bar_matches` returns False on the whole bar, not merely on a clause.
WHAT IS AND IS NOT TRUE: the parent/child depth evidence stands — 461 child themes, 234 live, the
09-09 run produced 19 more. `theme_subtheme_arm` reads **True** on prod. What is NOT shown is the
veto half: no unassigned-cluster veto alert emitter is findable in `agents/market_intelligence/`,
and the DoD's grace-end/veto/cooldown path is the Phase-2 design, not the parent_theme column.
HOW IT SURFACED: not by review. He asked whether #501's DoD was really met; calibrating the
partial-bar rule against the whole ledger printed #471 as the only other entry whose quote matches
no clause of its own DoD. **The check I built to answer one question found the older instance.**

## Lesson — task #540, closed 2026-09-10 and re-opened the same day

⚠ Not a close record — #540 is OPEN. Deliberately not written as a `## #<id>` heading so the gate
cannot mistake this post-mortem for a justification of a close.
BAR I SHOULD HAVE USED: the next broker cancel OR rejection carries a non-null `broker_reason` in its
audit row and Telegram — proven on a real live event, not a replay
WHAT I ACTUALLY CHECKED: `entry_rejection_watch_armed`, 3 rows, latest 09-09 12:18 — the HEARTBEAT,
which fires on the branch where there is no tracked entry row and therefore carries no
`broker_reason` at all. It proves the handler is alive. That is a strictly weaker claim that
happened to be true.
WHY IT PASSED MY OWN REVIEW: the line carried both a DoD and a later, narrower `VERIFY:` sentence
about the heartbeat sub-feature, and I matched the narrow one. **A task's closing bar is its DoD; a
verify line added for one sub-feature does not replace it.** `close_bar_for` encodes exactly that
ordering.
THE TRUTH: every `entry_order_rejected` row in prod is 08-07, 08-06 and 07-22 — all three predate the
08-10 fix and all three carry a NULL reason. The reason-capture path has never run in production.

## #636 — regime-freshness threshold coupled to the closes-ingest schedule (2026-09-10)
BAR: either his go-ahead for the one-character hardening (plus a test pinning that a same-day closes
row cannot move the threshold), or an explicit ruling to leave it coupled
EVIDENCE: Operator chose "Change <= to <" on 2026-09-10. Shipped in `cf16da34`:
`order_manager.py:298` now reads `WHERE trade_date < $1`, with the reason recorded at the call site.
`tests/test_regime_freshness_same_day_row_636.py` carries the required pin —
`test_a_same_day_closes_row_cannot_move_the_threshold` — and is RED-proven: reverting to `<=` fails
it plus the SQL-text pin. `docs/setups/safeguards.md` updated in the same commit. Deployed
2026-09-10 12:0x ET (`both` exit 0, then `execution` exit 0, server `074a6ebd`) and confirmed by
importing the module INSIDE the running apollo-execution container: strict `<` True, legacy `<=`
False — read off the container that actually runs broker code, not the repo.

## #612 — a live API key written to mi_audit_log in plain text (2026-09-10)
BAR: the redaction holds at the chokepoint, proven by a NEGATIVE query — zero rows in
`mi_audit_log` contain an unmasked credential pattern (`apikey=`, `token=`, `Bearer `) from the fix
date forward — AND the 99 historical rows are purged or masked in place
EVIDENCE: Both halves confirmed on prod, by a query run independently of the script that did the
work. (a) The chokepoint holds: every row from 2026-09-02 onward was already masked before I touched
anything — 569 of them — so `db.log_audit_event` → `redact_secrets` is working on the live path.
(b) The historical rows are masked in place: `scripts/probes/_612_redact_historical_audit_rows.py`
applied the SHIPPED `redact_secrets` (not a SQL copy of its regex) to 202 rows carrying an unmasked
value, inside one transaction. Verification query afterwards: **0 rows matching
`(apikey|api_key|token|secret)\s*=\s*[A-Za-z0-9]{12,}`, 771 rows carrying the mask.**
⚠ THE TASK'S OWN NUMBER WAS WRONG AND THE CLOSE RECORDS IT: the line said 99 rows. 99 is the count
for the `summary` column alone; `detail` held far more. The real exposure was **202 unmasked rows,
2026-06-26 → 2026-09-01**. Masking preserves the audit record — the parameter name stays, so the
rows are still diagnosable.
⚠ NOT CLOSED WITH IT: 4 of the rows are POLYGON, not FMP, and the earliest unmasked row of all is a
Polygon one. The FMP key is dead; Polygon's is presumably live. Filed as #637 for his rotate-or-
accept ruling rather than folded in here, because it is a different credential and a different
decision.

## #637 — Polygon credential exposed in mi_audit_log: rotate or accept (2026-09-10)
BAR: he rules ROTATE or ACCEPT. If ROTATE: the new key is in the secrets bundle, `deploy.sh`
preflight passes, and one full scan cycle completes on it. If ACCEPT: the ruling is recorded here
and this closes.
EVIDENCE: **Operator ruled ACCEPT on 2026-09-10**, asked directly with the trade-off stated (an
internal-only exposure in our own database against a rotation that stops the EP scan if it goes
wrong). No rotation performed. The exposure itself is closed either way: all 771 rows carrying
`apikey=` are masked, verified by a query independent of the script that masked them — zero rows
match `(apikey|api_key|token|secret)\s*=\s*[A-Za-z0-9]{12,}`, and the write path
(`db.log_audit_event` → `redact_secrets`) has been masking every new row since 2026-09-02.
⚠ WHAT THIS RULING DOES AND DOES NOT COVER: it accepts the risk of a Polygon key that sat in our own
database 2026-06-26 → 2026-09-01. It is NOT a standing ruling about credential exposure generally —
a key reaching a surface OUTSIDE our infrastructure (a Telegram render, a shared doc, a public log)
is a different question and does not inherit this answer.

## #634 — a new review must prove it can fire before it is accepted (2026-09-10)
BAR: FOLD INTO `scripts/operator_asks.py`, DO NOT BUILD A NEW GATE — add a `--audit` mode that
reports the five verdicts per review, and have `check_plan` fail a NEW/EDITED review that has no
recorded evidence block. One new flag and one gate arm — not a second runner, not a second script.
And check (c) must name its population.
EVIDENCE: Both halves shipped, and no new script was created. (a) `operator_asks.py --audit` reuses
the existing `_run_predicates` — the same one ssh, predicates isolated — and reports per review:
PREDICATE DID NOT RUN, ZERO PAST ITS ELIGIBLE DATE, and NO `can_fire:` EVIDENCE. It suppresses zeros
already carrying a `zero_verdict` so the six ruled on 2026-09-09 are not re-raised, and it reports
only OPEN reviews (2 of the first 3 "cannot fire" hits were `status: done`). (b)
`check_plan._review_can_fire_gate` fails the commit on a new or edited review whose `can_fire:` block
is absent or thin — RED-proven both ways: a review with no block is refused, and one with five
one-word values is refused as too thin. Check (c) is `threshold_vs_observed`, whose name carries the
population requirement, and the fixed review's own entry states which table its range was measured
on.
⚠ IT PAID FOR ITSELF ON THE FIRST RUN: `chart_reading_review_cycle`'s predicate was **100% SQL
comment** — YAML's `>-` folds every line into one, so a `--` comment swallowed the SELECT. It could
never have returned a number, and nothing else would have noticed. Fixed, evidenced, and pinned by
`tests/test_review_can_fire_gate.py`.
⚠ NOT CLOSED WITH IT: the 153 existing reviews have no `can_fire:` block. That is a standing backlog
the audit surfaces every OPEN, not part of this DoD.


## Lesson — task #486, a close the gate REFUSED on 2026-09-10

⚠ Not a close record — #486 is OPEN. Written as a `## Lesson` heading so the gate cannot mistake it
for a justification.

I tried to close #486 on *"scratchpads non-empty and covered_share/covered_by populated"* — the
verify line **I wrote that same morning** for one fix inside it. `check_plan._close_evidence_gate`
refused the removal and quoted the task's real DoD back at me: *"a periodic agreement readout
(themed-per-engine vs themed-per-judge, the mismatch cohorts, an engine-improvement candidate
queue)."* None of that is built.

**This is the #540 failure exactly, attempted again eight hours after writing the gate that catches
it** — and by the person who wrote it. A fix landing and being verified is not the task being done;
the recorder was one component of a readout that does not exist yet. The gate held, which is the
argument for gates over intentions in one line.

## #555 — rewrite canonicalize_themes as a model, not a tenth guard (closed 2026-09-10, shipped 2026-09-05)
BAR: cohort identity is decided by ONE model rather than nine stacked constraints — the rewrite
replaces greedy pairwise overlap, and the nine guards are RETIRED, not joined by a tenth
(the line also carries an earlier bar: the regression set green, the two residuals resolved or
explicitly accepted, and knob count DOWN not up — both are satisfied by the evidence below)
EVIDENCE: Shipped in `portfolio-app2` commit `1c19c76` on 2026-09-05 — *"a cohort identity model,
not a tenth guard: all three false merges gone, ranking unmoved"* — 846 lines of `theme_canon.py`
rewritten with `test_theme_canon.py` and `theme_data.py`. Verified today rather than taken on the
commit message: **the suite is 90/90 green**, and the discriminating clause holds — **tunable knobs
went 5 → 2**. `_MIN_SHARED`, `_MAX_SET_SIZE` and `_FIRST_CONTACT_THRESHOLD` are gone; the last of
those is the 0.70 the task line called out for sitting in a 0.014-wide margin between the bad case
(0.667) and the nearest genuine rename (0.714) on N=2. What remains is `_OVERLAP_THRESHOLD` (reused
from `dedup_themes`) and `_MAX_GAP_DAYS`. Knob count down, not up, exactly as the bar asked.
⛔ THE PROCESS FAILURE, recorded because it is the point: **this shipped five days before I closed
it, and I did not notice twice in one day.** This morning I wrote #555 a fresh "DoD (written
2026-09-10)" describing a rewrite that already existed, and this evening I scheduled it into the
weekend. A Sonnet card building #561 found it by running `git log` — the exact check
[[grep-git-before-scoping-a-card]] exists for, which I hold as a memory and did not apply. The
LIKELY-BUILT surface could not help: it keys on built/deployed markers in the task text, and this
line had none, because nobody had written one.

## #638 — the revert monitor may not blame the lattice without checking it did anything (closed 2026-09-10, shipped + verified live the same evening)
BAR: the trigger gains a DISCRIMINATING pre-condition — it may only recommend a revert when the
lattice actually CHANGED a grade in the window (`shadow_tier` ≠ `llm_quality` on at least one row)
EVIDENCE: Shipped in `99b19289` and extended in `33cccd13`; deployed 2026-09-10 21:1x ET, `both`
then `execution`, both green, box on `33cccd13`. **Verified on the RUNNING apollo-market image
against real prod data, not on a green suite:** `_lattice_retier_rows` over 2026-09-09/09-10 — the
exact window that produced tonight's false alarm — reads **13 rows** and `lattice_altered_nothing`
returns **True**, which is the branch that withholds the revert SQL. So the pre-condition
discriminates on the case it was built for, through the deployed code.
⛔ AND THE FIRST VERSION ONLY COVERED ONE OF THREE ENTRANCES. `lattice_inert` was computed inside
trigger (c)'s branch while the announce block that prints the SQL is shared by all three, so an (a)-
or (b)-only firing left the key unset and printed the prescription with no check and no caveat —
identical behaviour to before the fix. Trigger (a) was the worse half: `_lattice_acting_tier`
returns the raw LLM grade whenever `live_side != "lattice"`, so it could name the lattice for a
missed real EP the lattice was never in the path of. The verdict now belongs to the shared block,
over the union of every fired trigger's dates: confirmed on the running image — computed once,
after the last trigger append, with all three triggers feeding it. Found by the cleanup review, not
by me. ⚠ The DoD's `WOULD-FAIL-IF` (it fires again on a window where the lattice altered nothing)
is a falsification condition, not a further requirement — and it is now structurally unreachable on
any trigger, which is what the bar asked for.

## #642 — the two audit rows the old blind cut left unreadable (closed 2026-09-10, same evening, on his go-ahead)
BAR: zero rows where `length(detail)=8000 AND left(ltrim(detail),1) IN ('{','[') AND NOT
pg_input_is_valid(detail,'json')`. WOULD-FAIL-IF: the count comes back non-zero, or a repaired
row's `_head` no longer prefixes the snapshotted original
EVIDENCE: `scripts/probes/_501_repair_unreadable_audit_rows.py --commit` run on prod 2026-09-10
21:45 ET with his explicit go-ahead (it mutates audit history, so it was not mine to run). Two rows
repaired — `theme_birth_gate` id 39426 (2026-09-03) and `theme_discovery_shown_declined` id 42037
(2026-09-10 17:13, the row that exposed the bug). **Bar confirmed by direct query: the count is 0.**
Both rows now read `pg_input_is_valid = true`, `_truncated = true`, and `_head` is **8,000
characters** — the surviving text preserved exactly, nothing deleted, originals snapshotted to
`/tmp/_501_audit_repair_20260910T214502.json` before any write.
⛔ TWO THINGS THIS PROBE GOT WRONG BEFORE IT GOT THEM RIGHT, both caught by running it rather than
reading it. (1) The first FIND query selected every row whose detail is not JSON — which includes
rows that are legitimately plain prose — and offered to rewrite an 11-character `stage_change` row;
the verbatim-head assertion stopped it. (2) The SUCCESS CHECK had the same defect and survived
longer: after a clean repair it reported **24,367 unreadable rows remaining**, because it counted
that same broad population instead of the one it had just fixed. A check that measures the wrong
population reads like a failure here and would read like a pass somewhere else. Both narrowed.
⚠ THE COUNT WAS WRONG TWICE TODAY BEFORE IT WAS RIGHT: I told him "15 hit the cap, only 1 broken",
then a wider query said 10, and the answer is 2. The other 8 hold plain prose and were never JSON —
their tails are gone and no repair restores them. All three numbers are recorded in the probe's own
docstring so the corrected one is the one that survives.

## #631 — one exit recorder, twelve arms (closed 2026-09-11, shipped 2026-09-09, index fix 2026-09-10)
BAR: (a) every arm the other three tables test exists as an arm in the one recorder, with coverage
PROVEN arm-by-arm before anything is retired; (b) history preserved — migrate or leave the old
tables read-only, never dropped; (c) the duplicate reviews retired with a pointer to the single
read, and ONLY those whose question is genuinely covered; (d) one gated review does the reading
EVIDENCE: all four checked against prod today rather than taken from the task line —
(a) `mi_live_fill_counterfactuals` holds **12 distinct arms, 79 rows, 8 trades**, fills 2026-08-18 →
2026-09-08 — every arm in the `ARMS` table is writing.
(b) `mi_orb_shadow_trades` still exists with **356 rows**; nothing dropped.
(c) **CHECKED AFTER THE FACT, because he asked whether the DoD was really met and this clause was
the one I had asserted rather than verified.** It holds: **6 reviews carry an explicit `FOLDED INTO
live_fill_counterfactuals_first_read_482 (#631)` pointer and all 6 are `status: done`**
(`harvest_rule_effectiveness`, `pivot_stop_shadow_review`, `exit_regime_interaction_review`,
`stop_2r_running_comparison`, `exit_path_shadow_first_read`, `regime_conditional_exit_grid_parked`);
**1 was deliberately NOT folded** (`exit_tune_cohort_review`, the wide-grid OFFLINE read, kept as
its own review) and **1 was closed by operator ruling, not folded** (`giveback_shadow_review`).
That split is the *"ONLY those whose question is genuinely covered"* half of the clause being
honoured rather than everything being swept. `tests/test_exit_counterfactual_consolidation_631.py`
pins it — 34 tests green.
(d) `live_fill_counterfactuals_first_read_482` is the single gated review and reads 7 of 20
(earliest 2026-10-05) — confirmed in `operator_asks.py` output this morning.
▶ THE LAST OPEN ITEM — the `arm[5]` index fix — is live on the running image (confirmed 2026-09-10
inside apollo-market) AND, checked today, **the bug never reached the data**. It sat only in the
`missing_inputs` / `invalid_frame` branch, and every `harvest_*` row in prod is `settled`: 24 rows
across the four harvest arms, **0 with `breakeven_arm_r` set and avg `target_r` = 2.00**, which is
the fixed premise those arms are supposed to walk. Had the bug fired, they would carry the live
level and a non-null breakeven arm.
⛔ WHY IT WAS REAL ANYWAY, recorded so the next reader does not dismiss it: `arm[4]` is `trail_rule`
and **every arm in the table carries a non-empty one**, so the old index read TRUTHY for all twelve —
the four `follows_live_rule=False` arms included. Latent, not harmless: the first unscoreable fill
would have recorded four arms against a premise they do not hold.

## #501 — the jobs that could die without telling anyone, Tier-1 (closed 2026-09-11, deployed 2026-09-10)
⚠ SAY THIS FIRST: **the DoD sentence as written has TWO clauses and this close satisfies ONE.** The
second — *operator rules the Tier-2/3 batch* — was moved to **#635** in a scope split on 2026-09-10,
before this close. So the bar below is the NARROWED bar, and the narrowing happened first. That is
legitimate bookkeeping and it is also exactly the shape of a substituted criterion, so it is stated
at the top rather than left at the bottom for a reader to find.
BAR: the Tier-1 four surfaced (audit + deduped Telegram)
MOVED: #635 — the unquoted clause (*operator rules the Tier-2/3 batch*, F5–F13) lives there,
open, dated 2026-10-03, with its own DoD. Added 2026-09-11 when the gate learned to ask.
EVIDENCE: deployed 2026-09-10 12:0x ET, both scopes. The task's own verify line called for the
NEGATIVE check — *no false page fired* — which is the shape this week's rule forbids on its own, so
each of the four carries a POSITIVE companion proving its host path actually ran, all queried on
prod this morning (07:00–09:15 ET, a live market day):
- **Zero** `job_failed_error`, `polygon_snapshot_empty_error` or `order_status_reconcile_mode_error`
  rows since the deploy. That is the absence half.
- **F1** — 105 job runs over 18 distinct jobs since 07:00 ET, every one `success`, including the two
  watchdogs that are the whole reason this is Tier-1: `stop_ack_timeout_watchdog` ×32 and
  `stuck_fill_watchdog` ×16. A handler-less death would have written a row; none did.
- **F2** — 1,867 `mi_ep_scan_log` rows over **28 distinct ticks** today, so the full-market snapshot
  came back non-empty on every tick and the guard was exercised 28 times without firing. An empty
  snapshot pages; an inverted guard would have paged 28 times.
- **F3** — `stream_health_watchdog` ran 4 times (last 09:15 ET) with no failure row; the WS-outage
  backstop chain is alive.
- **F4** — `order_status_reconciled` fired 4 times since 07:00 ET, so the 15-minute reconcile is
  walking its modes; a mode dropping out writes the mode-error row, and none exists.
▶ SCOPE, stated because the DoD sentence still carries it: the second clause — *operator rules the
Tier-2/3 batch* — moved to **#635** on 2026-09-10 (F5–F13, never built). This line was narrowed to
Tier-1 that day so neither half wore a false headline.
⛔ AND ITS OPEN OPERATOR FORK WAS MOVED OUT BEFORE CLOSING, not closed with it. *Every job-failure
page arrives silent* (`core/notifications.py:90`, `:104`) — it had been written inside this task's
text on 2026-09-10 and was therefore invisible to `operator_asks.py`, which reads only the standing
table. It is now a row in that table with a proof. **A close must not take an unanswered ask down
with it**, which is the whole reason this ledger exists.
