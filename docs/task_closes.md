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
BAR: a cut `theme_synthesis` response produces a loud audit row, not a silent zero; a test pins it
⚠ BAR CORRECTED 2026-09-11 (the close itself stands). The original entry quoted *"tonight's
synthesis run completes and its audit row reads normally"* — a later verify sentence, not the DoD.
`--audit-closes` caught it. Clause by clause: **"a test pins it"** is met outright; **"a cut
response produces a loud audit row"** is proven by TEST and by the guard being present in the
running container, NOT by a real truncation in prod — which the entry below already said in its own
words, and which is why the close stands rather than reopening.
EVIDENCE: The 09-09 18:05 run — the first after the 09-08 21:15 deploy — recorded
`stop_reason='tool_use'`, 63 candidates → 2 proposed → 1 kept, and wrote no `theme_synthesis_error`.
The `n_proposed` field is parsed downstream of the guard with no branch between, so the row proves
execution passed THROUGH it; `if is_truncated(resp)` and the `theme_synthesis_error` event were both
confirmed present by importing the module inside the running apollo-market container.
⚠ Honest limit, recorded rather than glossed: this is a NEGATIVE check — the guard's firing side is
covered by tests, not by prod. The task's own criterion was written that way ("a truncation is rare,
so the verify is that the guard does not misfire on healthy runs").

## #452 — same-family exposure hook (2026-09-10)
BAR: stage-1 live; stage-2 backtested + decided
⚠ BAR CORRECTED 2026-09-11 (the close itself stands). The original entry quoted the task's later
verify sentence — *"the hook logs on a real entry evaluation..."* — instead of its DoD.
`--audit-closes` caught it. Clause by clause: **stage-1 live** is met by the evidence below (five
rows, the real comparison branch). **Stage-2 decided** is met by the operator's ruling of
2026-09-07 — *stays observe-only; reopens only on same-family entries*. **Stage-2 backtested** was
NOT run and is not claimed: his ruling settled the question without one, and the promote decision
sits in `exposure_family_cap_promotion_r2`, which is still accruing. Recorded plainly rather than
folded into the stage-2 tick.
EVIDENCE: Five `exposure_family_checked` rows on 09-08 at the ORB. PHVS reads "0 same-family
open(s), breach=False" — the real comparison branch, not the no-theme-membership early exit — so the
hook demonstrably computed rather than merely running. The promote-on-3-breaches question stays in
its registered gated review (`exposure_family_cap_promotion_r2`), which is where a future decision
belongs, not in an open task.

## Theme re-granularization, parent/child depth — originally filed as #471, closed 2026-09-10

⚠ **HEADING CHANGED 2026-09-20 so it no longer shadows the number.** `#471` was closed on that date for the
re-granularization work, and the SAME id was then carried forward for the ecosystem-discovery veto lane, which
closed today against a different DoD. `_close_evidence_gate` slices the ledger with `^##\s*#<id>` and takes the
FIRST block, so two closes under one number meant the later one was invisible and the gate compared today's DoD
against September 10th's bar. The evidence below is unchanged and still stands on its own; only the heading moved.
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

## #553 — cohort identity: containment alone may no longer merge (closed 2026-09-11, shipped 2026-09-05)
BAR: containment alone can no longer merge — `dedup_themes` requires a similarity gate (not a
tie-break), and the recorded false-merge cases stay SEPARATE when the matcher is replayed over them.
WOULD-FAIL-IF: a small theme wholly inside a larger unrelated one still merges at containment 1.00,
or merges still CHAIN (A~B, B~C → A+B+C) across unrelated cohorts
EVIDENCE: shipped in `portfolio-app2` `1c19c76` (2026-09-05) and **replayed over the REAL committed
snapshot today, not a synthetic fixture** — `TestRealSnapshot*` runs `canonicalize_themes` across the
full series and all 9 pass:
- **The three operator-evidenced false merges stay split across every day**: satellite-mobile never
  shares a cohort with defense primes; niche specialty chemicals never with IP licensing; the nylon
  rows never with agri or nitrogen.
- **The one true duplicate stays merged on every day it appears** (defense spending / contract
  surge) — so the gate did not simply stop merging, which is the failure mode a "nothing merges
  now" fix would hide behind.
- The same-day absorb is refused (`test_same_day_blob_does_not_absorb_optical_networking`) and
  alternating names on one basket resolve to one cohort.
- `test_grid_output_unchanged` pins the Grid view's own dedup byte-identical to the pre-#553
  original — the change is contained to cohort identity.
The gate itself: `_OVERLAP_THRESHOLD = 0.50` is a Jaccard FLOOR required before any merge, not a
tie-break, and the tiny-inside-huge case is pinned by its own test. Suite 36 green on that module.
⛔ AND IT SAT OPEN FIVE DAYS AFTER SHIPPING, which is the reason it is closable today: it lives in
the dashboard repo, and until `#641` half (a) shipped this morning **no git-derived surface in this
board could see a commit there**. `--today` named it within minutes of that scan going live.

## #561 — Weekly Movers: name the movers, rank by the jump (closed 2026-09-11, shipped 2026-09-10)
BAR: the list renders on his phone, names the movers, and he can tell in one look which themes got
stronger this week. Ask HIM to confirm that, since 'readable' is his call and this task exists
because I judged it for him once already
EVIDENCE: **He confirmed it himself, unprompted, in one line: *"pure play nand/dram 90->18, +72"*.**
That is the DoD executing — he opened the view, found the mover, and read its jump without being
told what to look for. Nobody else could have produced that evidence, which is exactly why the DoD
was written to require him.
▶ **And the number is RIGHT, checked rather than accepted:** recomputing `compute_weekly_movers`
against the same snapshot the page reads returns `Pure-Play NAND/DRAM Memory Chip Makers`,
`prev_rank 90 → curr_rank 18, delta 72` as the TOP gainer of 15, with `entrants_total 9`. A readable
view showing a wrong number would be worse than an unreadable one, so his reading was verified
against the data, not taken on trust.
▶ Shipped `26ebd91` (2026-09-10) and corrected the same evening in `5d119e0`: *entrants* had read
19 when **12 of those 19 carried a known rank the previous week** — a known prior rank is a known
prior rank, even past the board cut. Corrected to 9, which is the number the page now shows. The
identical defect was found in Rank Flow the next day (#640) and in the same shape.
⛔ IT SAT `in_progress` WITH ITS WORK LIVE because the commit is in the dashboard repo, invisible to
every git-derived surface here until #641's second-repo scan shipped this morning.

## #641 — the dashboard repo was invisible to every gate here (closed 2026-09-11, same day)
BAR: (1) `check_plan.py` reads `portfolio-app2`'s git log for the
SHIPPED-BUT-UNRECORDED and LIKELY-BUILT surfaces, so a dashboard task that ships cannot stay
`pending` — RED-proven by pointing it at #555's own commit and watching it fire; (2) the deployed
URL is captured in `portfolio-app2/CLAUDE.md` and a verify step exists that touches the RENDERED
page, not the local recompute — even if that step is *ask him to look*, it must be a named step,
not an assumption
EVIDENCE: half (a) shipped in `cb14a3f8`; `--today` now prints a SECOND-REPO SHIPS block. **On the
real board it named #553 and #561 within minutes of going live, and BOTH CLOSED the same morning on
the evidence it produced** — #553 had been shipped and invisible for five days, #561 for one. The
matcher is looser than this repo's on purpose and calibrated, not assumed: 182 commits in
`portfolio-app2`, 15 mentioning an id, 11 distinct ids, **9 of the 11 already-closed tasks that flag
nothing**. The anchored rule this repo uses would have missed **#555 itself** (*"#553/#555 — a
cohort identity model, not a tenth guard"*). 7 tests including a real temp git repo, RED-proven by
re-anchoring the regex. Fails OPEN: `APOLLO_SIDECAR_REPOS` overrides, a missing or non-git directory
is skipped, any git error returns nothing — the repo is absent on the laptop and the prod box.
▶ HALF (b): the verify step is NAMED, which is what the bar asked for. It could not be
"touch the rendered page": the app is SSO-gated at the Streamlit platform level, so no automated
fetch reaches it and a password in `st.secrets` would not change that. `portfolio-app2/CLAUDE.md`
now carries the URL (`alvin-portfolio-dashboard.streamlit.app`) and a three-step rule — recompute
the page's own function against the same snapshot JSON the page reads and assert the rendered
numbers; state that the page was not opened; ask him to look ONLY when the change is visual. **It
was exercised twice the same day before being written down**: #640's numbers were recomputed and
reported as not-opened, and #561 closed on step 3 — his own words, *"pure play nand/dram 90->18,
+72"*.
⛔ TWO ERRORS OF MINE ARE RECORDED IN THAT FILE RATHER THAN QUIETLY FIXED. I raised the URL as an
operator ask after searching every FILE, when one HTTP request would have settled it — and then the
URL I "found" that way was WRONG, because a 303 to Streamlit's auth endpoint proves nothing (it
answers for any `*.streamlit.app` subdomain). The real one came from his screenshot. Also recorded:
Streamlit served the pre-push build for ~14 minutes, which made a working fix look broken.

## #233 — Perplexity repositioned as a labelled second opinion, and the agreement boost retired (closed 2026-09-11)
BAR: the Perplexity grade reaches the judge as a LABELED second opinion and its DISAGREEMENT with
Claude is visible in a real judge rationale, with the mechanical `confidence_multiplier` floor
retired. WOULD-FAIL-IF: the multiplier is still doing the work, or the judge reads the text but
never the grade — the exact half-integration this line was written to finish
EVIDENCE: both clauses proven on prod data, not on code reading.
▶ **The boost is retired and the DATA says so:** in `mi_ep_alerts`, `confidence_multiplier = 1.2`
appears on 37 alerts from 2026-08-04 to **2026-08-27 — the sign-off date — and never again**. All
74 alerts since read 1.0. So the WOULD-FAIL-IF's first arm ("the multiplier is still doing the
work") is answered by the column itself, and it was genuinely acting before: it multiplies straight
into the score via `regime_multiplier * confidence_multiplier` at three sites.
▶ **The judge reads the GRADE, not just the text** — the second arm of the WOULD-FAIL-IF, and the
half this task existed to finish. Two of the 11 post-flip alerts carry a judge rationale citing it,
and both show the disagreement DOING something:
  - **QCOM 2026-09-08** — Claude `strong`, judge `game_changer`: *"Second opinion prompted a
    re-read: the 8-K's $60B purchase-linked warrant on a $180B cap is a hyperscaler design win of
    transformative scale, not just a legal-overhang removal, so I move up to game_changer."*
  - **SEI 2026-09-08** — *"The second opinion's 'strong' reads the Omega deal as the driver;
    re-reading, the load-bearing item is today's guidance raise..."* — the judge names the second
    opinion's GRADE and overrules it on evidence.
⚖ No strategy, threshold or sizing change was made in closing this; the flip itself was
operator-signed 2026-08-27 and the evidence for retiring the boost is in
`docs/analysis/pplx_agreement_boost_233_2026-08-27.md` (boosted names ran a SMALLER 5-day max move,
9.17% vs 11.20%, and the effect is a null once score band is held constant).

## #639 — two thirds of the theme board is new every week, and nobody owned that (2026-09-12)
BAR: separate REAL rotation from IDENTITY INSTABILITY, and say which dominates. For each week's
entrants, is the cohort genuinely new (its tickers were not together on the board under any name)
or is it an existing cohort under a changed name/membership?
EVIDENCE: `docs/analysis/639_board_churn_split_2026-09-11.md`, from the canonical grid's own
`canonical_id` and `tickers` columns over eleven post-launch weeks. The split, at the middle
Jaccard threshold: **NEW 107 (70%) · REAPPEARED 44 (29%) · RENAMED 1**. The answer to "which
dominates" is unambiguous and is stated: **real rotation dominates — identity instability is not
the cause.** RENAMED is ONE entrant in eleven weeks and holds at every threshold tested, falling
to zero under the stricter previous-week-board variant. The WOULD-FAIL-IF is satisfied in the
strong direction: the finding is reported as the three-way split, never as a single churn
percentage.
CARRIED FORWARD, not deleted: the one surviving remedy — label *week 1* apart from *held N weeks*
on the board — is UNBUILT and is now #648. Two other candidate remedies died on measurement and
their refutations live in the analysis doc, not only in the closed line: a basket-size floor (small
cohorts persist slightly BETTER, 43% vs 52% gone after one week) and a two-week confirmation delay
(it costs the 20% worth having exactly the five sessions #486 step-3 showed lift remaining runway
from 29% to 55%).

## #633 — eleven gated reviews had produced nothing since becoming eligible, and nobody had ruled them (2026-09-12)
BAR: no pending review reads ZERO-since-eligible without a dated note saying which it is.
EVIDENCE: read POSITIVELY rather than as an absence — `operator_asks.py --audit` run today
enumerates every review currently reading zero since its eligible date, and ALL SIX carry a dated
ruling in their own entry: `drawdown_breaker_active_effectiveness`, `exit_tune_cohort_review`,
`exposure_family_cap_promotion_r2`, `stop_reprotect_floor_first_fire_600`,
`sustain_reject_tradeable_miss_rate_593`, `wave_c_part2_boost_demotion`. A review reading zero
with no dated note would appear in that same output and does not.
RESIDUAL, built and DEPLOYED rather than carried forward: `spiky_guard_first_engagement` could not
distinguish a suppressed alert from an ordinary quiet night — the guard's demotion wrote the same
band field an unremarkable night writes, and on a night following another band-2 night it wrote
nothing at all. Fixed in `97baa0f6`, live in both images 2026-09-12: the engagement now stamps
itself at the demotion site and records even when the band is unchanged, while the guard's own
behaviour is untouched and pinned by test.
NOTHING IS ORPHANED BY THIS CLOSE: the residual's first-firing watch lives in the
`spiky_guard_first_engagement` review itself, which is a data-gated review and survives in
`data_gated_reviews.yaml` independently of this line.

## #485 — a meta-LLM reviewing the judge (2026-09-12)
BAR: feasibility read — does a meta-LLM add signal over the operator-labeled sample + the by-tier
outcome cross-tab #337 already surfaces? → if yes, design + shadow (advisory only, NEVER a grade
input — THE LINE); if no, retire the idea.
ACCEPTED-PARTIAL: the DoD is a FORK, and the read resolved it to the "no" branch, so the "if yes,
design + shadow (advisory only, NEVER a grade input)" clause is unreachable by construction rather
than unmet — there is nothing to design because the feasibility answer was negative. Nothing is
being quietly dropped: the by-tier outcome cross-tab the DoD names as the comparison baseline is
#337's, which is a SEPARATE surface that remains live and untouched by this close.
EVIDENCE: the read was done at $0 and the answer is NO —
`docs/analysis/485_judge_meta_review_feasibility_2026-09-12.md`. Three independent reasons:
(1) COVERAGE ALREADY EXISTS — `mi_judge_divergence` holds **97 runs, 80 agreed, 17 disagreed, over
24 distinct days from 2026-07-27 to 09-08**, i.e. every judge HIGH already receives an independent
second-model read, queried on prod today.
(2) THE QUESTION IS ALREADY QUEUED — "were the disagreed calls the weaker ones" is the registered
gated review `judge_divergence_marginal_high_signal`, at 8 of 15 settled; a meta-LLM would be a
second instrument asking a question already instrumented.
(3) THERE IS NOTHING TO CALIBRATE AGAINST — under the rules actually running (rubric v4 from
08-28) the judge has decided **10** alerts with **4** settled outcomes.
And a reviewer that FLAGS judge calls is a self-score, which ADR 0011 forbids outright — so the
"yes" branch was never available in the shape the idea imagined.
OPERATOR RULING: retire — *"aligned"*, 2026-09-12, against the standing priority that EP
profitability is an EXIT problem, making selection-side polish a detour.
CARRIED FORWARD, not deleted: the demotion gap — 17 demotions since 07-27 with zero second reads,
because #301's trigger is HIGH-only — is real, is NEW work rather than this task's bar, and was
FILED AS #650 on 2026-09-12 (a doc alone is not a rehome; the board is).
⚠ MY OWN ERROR, kept because it is instructive: I first reported that coverage could NOT be proven,
having read only `mi_audit_log` (which records disagreements only) and missed the per-run table
write one line above it. Same shape as the defect I was accusing the analysis of.

## #564 — an ad-hoc lookup on a weekend used to write a row dated a day the market never traded (2026-09-12)
BAR: decide and implement what an ad-hoc lookup should do on a non-trading day — write against the
last trading day, or compute without persisting — then confirm no new off-calendar rows appear.
EVIDENCE: both halves. DECIDED AND IMPLEMENTED — compute without persisting (`rs_engine.py:728`,
the guard confirmed present in the RUNNING apollo-market image, not just the repo). CONFIRMED on a
real weekend, by TRIGGERING the path rather than by watching for silence: `score_single_ticker`
called in prod today (Saturday 2026-09-12) returned **rs_composite 87.8 with score_date 2026-09-11**
— a real score, ranked against Friday's distribution — and logged *"SMCI on 2026-09-12 is not a
trading day — score computed but NOT persisted (#564)"*. The weekend-dated row census is UNCHANGED
before and after: 2026-03-21 (9,784 — a one-off bulk backfill, a different class), then the four
singleton bug rows 05-30, 07-05, 07-12, 08-08, and nothing since. `mi_tracked_stocks` has no SMCI
row at all, so the bookkeeping half wrote nothing either.
⚠ WHY THE TRIGGER MATTERS: a passive scan would have been absence-only — a broken system also shows
no weekend row on a weekend when nobody looks anything up, and the bug fired 4 times in 3.5 months.
The positive observables (a returned score, Friday's date, the skip-branch log line) are what make
the absence mean something.
⚠ AND THE LINE NAMED THE WRONG COMMAND: its later VERIFY sentence says `/setup TICKER`, which routes
to the detector-chronology lookup and never reaches this writer — running that and seeing no row
would have been a FALSE PASS on an unfixed system. The DoD, not that sentence, is what was checked.
CARRIED FORWARD, not deleted: the four legacy rows are still in the table. Deleting them is a
production write and the line records it as the operator's call, not a condition of this fix.

## #600 — the repair could re-arm a stop at a price the broker had already beaten (2026-09-12)
BAR: route the place branch through the same raise-only floor, or state why it must not be.
EVIDENCE: routed, and verified INSIDE BOTH RUNNING IMAGES rather than in the repo — apollo-execution
(which actually runs `broker/`) and apollo-market both report: the place branch calls
`_apply_reprotect_floor` with `site="ensure_stop_coverage.place"` = True; it places the FLOORED
price (`int(target), place_price`) = True; it places the RAW db price = **False**; and both fork-2
helpers (`_preserve_dead_stop_price`, `_current_stop_pointer`) are present. The third line is the
discriminating one — a system with the bug still in it would place `float(db_stop_price)` there, so
this is not an absence check.

## #545 — the entry/exit tactics program: its design deliverable (2026-09-12)
BAR: a design doc with the variant inventory, the parameter grid, the answerable-vs-needs-capture
split, and a phased execution plan for the operator to sequence.
EVIDENCE: delivered TWICE, and both files exist on disk — `docs/design/545_entry_exit_program_v2_2026-09-02.md`
(66,275 bytes) and its successor `docs/design/545_entry_exit_program_2026-09-05.md` (66,415 bytes),
the second re-graded under the operator's tail-first objective. All four named parts are present in
the current version.
⚠ THE STATUS WORD WAS SET FOR SOMETHING ELSE, and that is worth stating rather than glossing: this
line reads `deployed` because of the 2026-09-06 LIVE EXIT FLIP (`b52fdcbc` — partial to +8R,
price-armed breakeven at +3R), not because of the design doc. The DoD is the doc, and a DoD outranks
a later status or verify sentence.
NOTHING IS ORPHANED: the flip's own effectiveness evaluation is already rehomed as the data-gated
review `exit_regime_interaction_review` — verified today as era-scoped on the flip date, threshold
20, earliest 2026-10-15, so it CANNOT speak about the current rule until it has trades from the
current rule. That re-gating was itself the fix for this line's worst moment: a recommendation built
on 28 trades of which 27 predated the rule it proposed changing.

## #653 — ration the brittle tests, not the count (2026-09-13)

BAR: a gate FAILS the commit when a NEW or EDITED test asserts on source text, with a reviewed
escape (`# source-pin-ok: <why behaviour cannot be exercised>`) — NEW/EDITED only, the existing 285
stay a surfaced backlog rather than a wall; the gate reports the current source-pin count so the
trend is visible and must go DOWN; a written rule for when a new test file is justified versus
extending an existing one.

EVIDENCE: all three parts shipped and the gate was exercised end-to-end, not merely written.
(1) `scripts/check_test_source_pins.py`, wired as Gate 7 in `.githooks/pre-commit`, diff-based
new/edited-only in the same shape as `check_plan._review_can_fire_gate`. Verified by staging a real
source-pinning probe test and watching the hook BLOCK it with the right message, then cleaning up —
the gate has been made to fail, which is this repo's own bar for believing a gate. The escape
requires a stated reason of >=12 chars, so a bare marker does not satisfy it. (2) The count prints
on every run (`source-pin test count: 444 total, baseline 444 (flat)`) and is held by a RATCHET
(`total <= baseline`), not an exact snapshot — the first version was an exact lock that would have
reddened the whole suite whenever unrelated concurrent work shifted a count, which was caught and
replaced before shipping. (3) `docs/testing/test_discipline.md`, registered in `docs/SSoT.md` and
pointed to from the Gate 7 failure text: a new file is justified only by no existing coverage, new
infrastructure, or a deliberate topical split — "task #NNN" is never a reason.
19 mutations run against the real file, each confirmed RED then restored. Suite 8,288 passed.

▶ **CLEANUP SWEEP, same day (2026-09-13):** the gate stops new pins but nothing drove the existing ones down, so a scoped sweep ran over the nine worst NON-money-path files. **444 → 403 total, 444 → 362 unescaped — 82 pins in those files became 41, and every survivor carries a stated reason.** 45 behavioural tests written or converted, each mutation-proven RED-then-restored. Verified by me independently rather than taken on report: `git diff --stat` shows exactly 9 test files plus the baseline changed — **zero production code** — and my own run of the scanner reads 403/362. Suite 8,307. ⚠ **41 stayed TAGGED and that is the honest answer, not a shortfall: 30 of them sit inside `run_ep_scan` / `run_theme_engine` / `_post_nightly_audit_job`** — orchestrators with no independently-callable seam short of a production refactor, which is a scope decision rather than a test one. Money-path files (stop / partial / profit / broker / exit / order / coverage) were deliberately NOT touched — that is a separate, slower job.

⚠ THE TASK'S OWN NUMBER WAS WRONG AND THE CARD CORRECTED IT RATHER THAN FITTING TO IT. The line
said 285 source-pin tests across 120 files; the real figure is **444 across 136 files** — 7.6% of
5,881 test functions, not 4.8%. My original scan counted only source reads inside a test body and
missed the indirection this repo actually uses: a module-level `HEALTH = Path(...).read_text()`, and
the `def _src(): return open("agents/...").read()` helper pattern present in at least four test
files. Hand-verified on `tests/test_486_bounded_read_is_nightly.py:34` — `_src()` opens
`scheduler.py` and `test_the_slot_avoids_both_deploy_windows` regexes it, a genuine pin my scan did
not see. The baseline is set to the measured 444, NOT force-fit to the number in the task text.

## #516 — the M&A filter that wrongly suppressed material movers (2026-09-13)

BAR: false-positive rate on material movers measured before/after, WEN's repeat misfire explained,
and `unknown` match-path share reduced or justified.

EVIDENCE: all three clauses, the last two settled today — measured on prod, not inferred.

(1) FALSE-POSITIVE RATE, measured 2026-08-08 (`docs/analysis/516_ma_filter_false_positives_2026-08-08.md`):
per suppression path over 60 days, screened on pin-vs-keeps-running. `claude_classifier` 0 of 26 ran
>=10%; `polygon_news` 5 of 18 (worst +154.6%); `keyword_in_text_1` 2 of 11; `keyword_in_text_0` 2 of 8.
The LLM path is clean; the keyword/news paths account for every runner. His own operator judgement
supplied the labels (3 false positives, 1 correct) — CHANGE_PROCESS r3/r4 reserves that call to him
and #514 delivered it.

(2) WEN'S REPEAT MISFIRE — EXPLAINED, and this line's own account of it was WRONG. The line said
"the #89 dedup did not stop it repeating for two months." It did exactly its job. The dedup key is
(ticker, detector_tag) per TRADING DAY and it shipped 2026-05-23. Measured on prod today, WEN's
fires by day and detector:

    2026-05-12  (no detector tag)  32 fires   <- PREDATES the dedup by 11 days
    2026-06-26  9m_intraday         1
    2026-06-29  9m_intraday         1
    2026-06-29  9m_sugar_baby       1         <- different detector, same day: correctly allowed
    2026-07-01  9m_intraday         1
    2026-07-01  9m_sugar_baby       1

After the ship date there is NEVER more than one fire per detector per day. The 32-fire burst is
pre-dedup and also pre-dates the summary contract that standardised the `(detector_tag)` format,
which is why those rows carry no tag. So WEN's "repeat" is not a dedup failure at all: it is the
same name being a false positive on FIVE SEPARATE DAYS via `polygon_news` — the path clause (1)
already measured as 2-of-3 wrong on material movers. The defect is filter accuracy, not logging.

(3) `unknown` MATCH-PATH SHARE — JUSTIFIED, because there is no unknown share. `ma_filter.py` emits
exactly four literals (`title`:626, `description+insights`:692, `claude_classifier`:737,
`keyword_in_text_{idx}`:777). All 946 `mna_filter_fired` rows name their path in the SUMMARY — 100%,
both eras. The structured `detail.match_path` field went from 5.4% populated (52 of 961) to 100%
(5 of 5) after the DoD-3 fix. ZERO rows carry an unrecognised value. The task's founding premise —
"70% carry match_path='unknown'" — was reading the narrow field instead of the summary.

⚠ TWO MEASUREMENT ARTIFACTS HIT WHILE CLOSING THIS, both of which looked like findings: the era
boundary was wrong by three weeks (the `claude_classifier` stamp shipped 2026-08-30, not 08-08, so
splitting at 08-08 makes clause 3 look unmet), and a naive value regex misses `description+insights`
(the `+`) while a ` via <path> ` match with a trailing space misses the 452 rows that END with the
path, reading 52% coverage instead of 100%. Both were caught by checking, not by the numbers looking
wrong.

## #648 — a first-week theme no longer looks identical to one held a month (2026-09-13)

BAR: "the board shows first-week cohorts distinguishably from held-N-weeks ones, so a provisional
theme stops rendering identically to a matured one — the reader discounts with the fact in front of
him rather than having it hidden."

EVIDENCE: shipped in `portfolio-app2` as `d75271f` ("#648: the board now says how long each cohort
has held its place"), on `origin/main`. `theme_movers.py:68` adds `_weeks_on_board(...)` — CONSECUTIVE
weeks on the board ending at the week being rendered, 1 = its first week — carried into every mover
row as `weeks_held` (`:186`, `:195`) and rendered on every line via `_tenure()` (`:220`) as
"1st week" / "2nd week" / "4th week": `:235` for new entrants ("outside → 12 · 1st week") and `:244`
for gainers ("18 → 9 (+9) · 4th week").

WOULD-FAIL-IF (from the task): "a cohort in its first week and one held four weeks render the same
on the deployed board." They do not — the two examples above are the two cases, and they differ in
the rendered string. `test_648_board_tenure.py`: 6 passed.

⚖ Display only, as the task required — no engine, grade, ranking or membership change.
⚠ Streamlit serves from `main` and #640 records that a rebuild has needed forcing before; the code
is on origin and the tenure string is unconditional, so a stale render would show the OLD lines
rather than wrong new ones.

## #488 — authoritative halt data is live on the ORB stream, and it caught a real halt (2026-09-14)

BAR: "the Alpaca-WS `statuses` channel is captured and a REAL halt appears in our data with its
authoritative status, on the live path. WOULD-FAIL-IF: the capture ships and no halt is ever
recorded — a subscription nobody can prove is receiving."

EVIDENCE: verified on prod this morning, not taken from a report.
- **The subscribe RAN**, and this is the half that could have been faked by silence:
  `halt-status shadow: trading-statuses (*) capture registered (#488)` at 2026-09-13T23:29:23Z,
  3 seconds after the container start at 23:29:20Z, with no restart since. `capture_enabled()`
  returns True inside the running `apollo-execution` image.
- **A REAL halt appeared with its authoritative status:** `mi_halt_status_events` holds 79 rows for
  today, ticker **VRC**, `status_code = 2` / `status_message = 'Trading Halt'`, `feed = 'sip'`,
  tape B, first at 13:33:14Z. That is the authoritative per-security halt source the whole task was
  about, and before today it had never recorded anything.
- **On the LIVE path, with the shared stream intact** — the S2 risk this task existed to bound
  (`websocket.py:352`: a subscribe on an un-entitled feed kills the ORB price stream). At 13:31:00Z
  the same stream delivered `first bar received for SRRK O=56.50 H=56.90 L=55.00 C=55.51` and at
  13:31:11Z the same for DFTX, both logged `stream healthy=True`, and DFTX went on to a real live
  order (`trade_id=399`, stop-limit BUY @$43.61). **Bars kept flowing through a session in which the
  statuses subscription was attached.**

⚠ **I checked the discriminating fact first rather than the convenient one.** Bars flowing proves
nothing on its own — an unsubscribed stream delivers bars identically. The registration log line and
`capture_enabled()` are what separate the working system from the broken one; the bar flow is only
meaningful once those are established.

⚠ **The RMV heuristic still owns the consolidation guard**, exactly as the task required — this
changed nothing there. `mi_dead_data_guard_shadow` is at 0 rows; it accrues on the nightly compare,
which has not run since the flip, so the "does authoritative beat the heuristic" question is open
and belongs to whoever reads that table, not to this bar.

⚠ **Noted, not fixed: 79 rows are ONE halt, not 79.** The writer records a row every ~5 seconds for
as long as a security stays halted, so the table counts feed heartbeats rather than halt events. It
is shadow-only (SQL table, no Telegram, no reader in the money path) so nothing is wrong today, but
any query over it must count DISTINCT halts, and the writer should dedupe until the status changes.
Filed as #659.

## #651 — the judge names groups we don't have, and now they reach him with a button (2026-09-14)

BAR: "a theme the judge names that does not match an existing theme is captured as a STRUCTURED
candidate — ticker, alert date, the proposed name, the judge's own words — and surfaced for his
ruling; nothing auto-creates a theme."

EVIDENCE: the first live nightly run, 2026-09-14 22:20 UTC, verified on prod — the prediction held on members not just count, the rows carry the judge's own sentences, and the send is proven by the audit row's own gating.

- **The prediction held exactly, members and all.** The 09-12 prod dry run named TWO groups that
  would fire: `ai-monetization` and `semiconductor-equipment-cycle-recovery`. Tonight's audit row
  reads *"7 recurring group(s): 5 matched a theme, 2 unmatched (0 already surfaced, 0 re-seeded),
  2 fired"* — and the two that fired are those two, on the same tickers. ⚠ A matching COUNT with
  different members would have been a false pass; I checked the members, not the number.
- **Structured, with the judge's own words** — `mi_judge_named_themes` holds 157 rows, 70 carrying
  a non-sentinel `canonical_key` AND non-empty `evidence`. The four rows behind tonight's pages:
  `ai-monetization` NMAX 2026-08-14 (*"new multi-year Meta AI content-licensing partnership…"*) and
  TEAM 2026-08-07; `semiconductor-equipment-cycle-recovery` ONTO and ACMR, both 2026-08-07
  (*"The advanced-packaging/ECP driver plugs directly into the active 'Semiconductor Equipment
  Cycle…'"*). Ticker, alert date, proposed name and the judge's sentence, as the bar requires.
- **"Surfaced for his ruling" is PROVEN, not assumed, and this is the part I nearly took on faith.**
  There is no telegram-send audit row, so I read the code instead: `judge_named_themes.py:724`
  does `ok = await send_telegram_message(...)`, then `if not ok: … continue` — the
  `judge_named_theme_candidate` audit row at `:729` is UNREACHABLE unless the send returned ok.
  Both rows exist, so both pages landed.
- **The button was attached.** `markup = build_synthesis_keyboard(…) if seeded else None`, and the
  summary appends `" (SEED FAILED)"` when it is not. Neither row carries it (`seed_failed = f`,
  both end `seeded source=judge_named`), so both pages went out WITH the promote button — the
  clause its own WOULD-FAIL-IF calls out ("a 🧭 alert arrives without the button").
- **Nothing auto-created a theme.** Tonight's `mi_themes` rows are 125 `live` + 5
  `shadow_promoted`; the judge-named candidates are seeds awaiting his button.

⚠ **Its liveness WOULD-FAIL-IF ("no row by 18:30 while new graded alerts exist") is satisfied by
the same run**: `judge_named_themes_extracted` — 2 alerts, 2 rows written, 0 failed, ~$0.0030.

⚠ Left open deliberately, and NOT part of this bar: whether he promotes either group. The task's
job was to stop throwing the judge's names away and put them in front of him; the ruling is his.

## #645 — an arm that changed nothing now says 0.0, and the replay gap has its own line (2026-09-14)

BAR: "an arm that changed nothing displays 0.0, and the replay-vs-actual fidelity gap is reported as
its OWN line with its own n — the two facts stop sharing a column." Plus the format half he asked
for in the same breath: "a reader can tell where one item ends and the next begins, and the arms
that CHANGED something are separable at a glance from the arms that did not."

EVIDENCE: the RENDERED digest, pulled read-only out of `apollo-execution` on 2026-09-14 rather than
inferred from the DB — this is an operator-facing surface, so the rendered text is the only thing
that can settle it.

- **The verify needed a settled fill and finally got one.** DFTX filled 09:33 ET and stopped out at
  10:19 ET (−$23.73), so the digest reads **2 fills** (PHVS 09-08 + DFTX 09-14), not the single
  trade that made every number in that block one trade wide.
- **Arms that changed nothing print 0.0 — once, as a named list, not six phantom percentages:**
  `changed NOTHING on any of 2 fills, so 0.0% each:` followed by *partial-but-no-breakeven · no
  partial, trail only · partial, sell the rest three days later · the old rule (partial at +2R) ·
  swing-stop rule · character-based rule*. **Its WOULD-FAIL-IF was "an arm with `changed 0` prints
  a non-zero percentage" — not one does.** That is the original defect he spotted (*"I find it odd
  that most exit is the same at +0.2%"*): those six were all showing PHVS's +0.19pp replay drift as
  if it were an exit result.
- **The fidelity gap moved to its own section with its own n**, labelled as a method check rather
  than an exit: *"HOW CLOSE IS THE REPLAY TO THE REAL FILL? (a check on the method, not an exit) —
  our own rule replayed, as a check: +0.1% average gap vs the real result over 2 fills; off by over
  a quarter of the fill's risk on 0 of 2 fills."*
- **The format half holds too:** the three arms that DID change something lead with `▸` markers and
  one line each (+3.8% / +5.7% / +4.5%, each "changed 2 of 2 fills"), the inert six collapse into a
  single named list beneath them, and `──────────` rules separate the sections that used to read as
  one wall on a phone. Rendered length 2,026 chars against the 2,500 cap.

⚠ Deliberately NOT read as a finding: the three stop-variant arms show +3.8% to +5.7% on 2 of 2
fills. That is n=2 and it is #482's question, not this one. This task was about the DISPLAY telling
the truth, and a two-fill improvement signal is exactly the kind of number the old format would have
let someone act on.

## #643 — BGSI was not delay-missed; the overlay declined it in real time and was right (2026-09-15)

BAR: (the task's own DoD, verbatim) "a one-paragraph answer naming which of the two measurements describes what the live system acts on, why BGSI and ALMR diverged on the same tick, and — if the tracker's basis no longer matches the live path — the corrected LABEL for its alert, which currently calls a non-delay case delay-missed."

WOULD-FAIL-IF: (its own) "the answer rests on reading the code alone without re-deriving both numbers."

EVIDENCE: both numbers re-derived from prod FIRST; the code was read only afterwards, to name the mechanism the data had already exposed.

**There was never a two-number disagreement. The two numbers are fifteen minutes apart.**
`mi_ep_scan_log` carries both readings in the same row: `gap_pct_rt` is the real-time feed and
`gap_pct_delayed` is the 15-minute-lagged one. BGSI's 09:50 row reads **rt 7.39% / delayed 10.21%**
against a `prev_close` of **81.55** (confirmed in `mi_daily_closes`, 2026-09-10). Those are not two
sources contradicting each other at one moment — they are the price at 09:50 and the price at
~09:35. **BGSI was +10.2% at 09:35 and had faded to +7.4% by 09:50.** ALMR's own 09:50 row says the
same thing louder: **rt 1.51% / delayed 10.26%** — it faded harder still, from +10.26% to +1.51%.

**THE LIVE SYSTEM ACTS ON `gap_pct_rt`**, and prod states this itself rather than leaving it to be
inferred — `ep_rt_floor_flip_down` @09:50:23, *"BGSI delayed 10.2% >=9 > rt 7.4% (stale false-admit
REMOVED)"*.

**BGSI AND ALMR DID NOT DIVERGE ON MEASUREMENT — THEY DIVERGED ON THE SUSTAIN RULE.** Both were
~+10.2% at the 09:35 tick. ALMR's level held three consecutive bars, so the real-time universe
admitted it (`price_source = alpaca_sip_universe`), after which it died on SCORE, not on the
universe floor — *score 52 < bar 65*. BGSI's level did not hold, and the overlay said so at
09:35:04, four seconds after the tick: **`ep_rt_sustain_reject` — "BGSI rt 10.2% but the level did
NOT hold 3 consecutive bars @ 09:35 ET — no catch"**. The fade to 7.4% fifteen minutes later is the
evidence that the decline was correct.

**THE CORRECTED LABEL: not "delay-missed" — DECLINED IN REAL TIME, ON PURPOSE.** At the same second
as that rejection, `ep_rt_live_miss` fired anyway: *"BGSI rt 10.2% ≥10 @ 09:35 ET, passes mechanical
EP gates but NOT a scan candidate (delay-missed EP)"*. The watchdog asked *is it a scan candidate?*
and never asked *why not* — so the overlay's own deliberate rejection was re-reported as a miss the
hybrid could not catch. **This is the session's recurring defect class: a measure that never asks
what the system already did counts its wins as losses.** [[check-what-the-system-already-did]]

**VERIFIED LIVE, and the check discriminates rather than resting on an absence.** The fix
(`fe121f89`, 2026-09-11) threads `declined_out[tkr] = "ep_rt_sustain_reject"` so the watchdog skips
names the overlay declined. A ticker-day carrying BOTH events is the defect; carrying only the
sustain reject is the fix. Over the last 30 days:

| | ticker-days with BOTH (the defect) | sustain-reject only |
|---|---|---|
| pre-fix (08-17 → 09-11) | **14**, on 8 separate days | 72 |
| post-fix, exercised (09-14, 09-15) | **0** | **7** |

The mechanism was engaged seven times after the fix and mislabelled none of them — so this is not a
quiet-window zero. ⚠ 09-12 produced no sustain rejects at all and is excluded rather than counted as
a passing day.

⚠ **Deliberately NOT read as a finding:** that the sustain rule is correct in general. This close
rests on one name where the fade is visible. The rule's own standing evidence is
`sustain_reject_tradeable_miss_rate_593` — 102 scoreable declines, 7 would have made money, 0
reached 4R.

## #579 — ad-hoc discovery spoke for the first time, and the other pair stayed quiet (2026-09-15)

BAR: (the task's own DoD, verbatim) "(a) a reusable 'is this reading unusual for THIS series' primitive, lifted from the crypto lane; (b) applied first to the strength-map spreads, with the firing distribution MEASURED before any threshold is chosen (P2 — price it like the gap floor, do not guess); (c) it speaks when the reading changes, at whatever hour that is; (d) a stated silence rate — how often it says nothing — because that is the number that proves it is not noise."

EVIDENCE: the 17:40 ET run on 2026-09-15 fired the first real alert this surface has ever produced, and the prediction for it was written down BEFORE it ran.

**PRE-REGISTERED at 2026-09-15 ~10:50 PT, recorded on the task and committed (`cab7106c`) hours
before the job fired:** *"two `strength_spread_alert_check` rows, `measured:true`, `judged` 565 —
and a Telegram on ENERGY: move −15.49 against its own band 12.67, state `falling_behind`. Precious
metals stays SILENT (move +8.37 inside band 11.22, `crossed:false`) — the silence is half the
proof."*

**WHAT ACTUALLY LANDED at 17:40:00 ET:**

| | predicted | observed |
|---|---|---|
| rows | 2, measured | **2** |
| Energy state | `falling_behind`, crossed | **`falling_behind`, crossed=True** |
| Energy band | 12.67 | **12.67** |
| Energy move | −15.49 | **−17.69** (one more session of data) |
| Precious metals | silent, crossed=False | **`quiet`, crossed=False** |
| Precious metals band | 11.22 | **11.20** |

The two bands match to the second decimal; the moves differ only because the prediction was
computed through 2026-09-14 and the job ran on 09-15 data.

**THE TELEGRAM DEMONSTRABLY SENT, and this is a positive check rather than an absence.**
`run_spread_crossing_alert` advances `mi_strength_spread_alert_state` ONLY after
`send_telegram_message` returns true — a failed send deliberately leaves the state unadvanced so
the crossing retries. `mi_strength_spread_alert_state` now reads `Energy | falling_behind | -17.69
| 12.67`, so the send succeeded. A silent failure would have left the row absent or `quiet`.

**EACH DoD CLAUSE, CHECKED SEPARATELY:**
- **(a)** `evaluate_spread_crossing` + `_classify_spread_state` + `_is_new_crossing` are the
  reusable "unusual for THIS series" primitive, percentile-based like the crypto lane's own
  measured-typical-move test. PURE, no I/O, unit-tested away from a database.
- **(b)** the bar is each pair's own 75th percentile recalculated on the run, not a picked number —
  and it survived an 8x increase in its own history when the ETF backfill took judged days from 224
  to 565 (`crossings_per_month` ~1.3 against the ~1.2 priced on 2026-09-11).
- **(c)** it spoke at 17:40 on a genuine crossing, not on a schedule: the 11 prior sessions all read
  `quiet` (−3.45 to −12.48, inside the band) and 09-14 was the first to break it.
- **(d)** the message states its own silence rate in plain words — *"Fires about 1.3x a month for
  this pair — quiet the rest of the time · a READ, not a rule"* (`format_spread_crossing_alert`).

**AND THE SILENCE HALF HELD:** Precious metals sat at +5.4 inside an 11.2 bar and said nothing.
A discovery feed that always has something to say is worth nothing — that was the task's own stated
failure mode, and on its first live evening one pair spoke and one did not.

⚠ **What this does NOT establish:** that the 1.3-per-month rate holds — it is computed over history,
not observed live, and one evening is one evening. The unintended-consequence watch items written
into the task's EXPECT (a first-measured-day false fire, a rate above the priced ~1.2, a send that
fires but fails to advance state) stay open as things to notice, not as things now disproven.

⚠ **Also not established: that the READ is useful.** Energy stocks falling behind oil and gas by
17.7 points is a true statement about the tape; whether it is worth acting on is the operator's
call and always was — the message says "a READ, not a rule" for that reason.

---

## #650 — the judge's demotions now get the same second opinion a HIGH does (closed 2026-09-16)

BAR: "a judge demotion receives the same zero-authority second-model read a HIGH does, and
disagreements land in `mi_judge_divergence` the same way"

WOULD-FAIL-IF: "a week passes with demotions recorded and zero corresponding divergence rows" —
and, from the VERIFY line, if a demoted alert has NEITHER a divergence row NOR a
`JUDGE_DIVERGENCE_CHECK_FAILED` audit event. A week with no demotion at all is NOT a pass; it is
unrunnable, and the EXPECT written before the first query said so explicitly.

EVIDENCE: **CIFR 2026-09-16 is the first real demotion since the 2026-09-12 deploy — floor HIGH,
judge MODERATE — and it produced a `mi_judge_divergence` row at 09:45:43 ET** (primary MODERATE,
secondary MODERATE, agree=true). Before #650 that name would have had no second read at all: the
table held 99 rows, every one `primary_tier='HIGH'`, across 2026-07-27 → 09-14.

- **1:1 pairing, no gaps.** All 3 judged alerts since the deploy (SRRK 09-14, DFTX 09-14, CIFR
  09-16) carry a divergence row. `JUDGE_DIVERGENCE_CHECK_FAILED` count is **0**.
- **The "disagreements land the same way" half is STRUCTURAL, not assumed.** CIFR agreed, so the
  disagree path was not exercised by this row — checked in code rather than closed over:
  `judge_divergence.py:134-155` computes `agree` and writes it as a COLUMN in a single
  unconditional INSERT; the `if not agree:` block at :156 only adds an audit breadcrumb AFTER the
  row exists. There is no branch in which a disagreement fails to land. **And it is not untested
  either — 17 of the 99 HIGH-sourced rows carry `agree=false`.**
- **Zero authority re-verified, not inherited:** no reference to `mi_judge_divergence` in
  `ep_detector.py`, `entry_pipeline.py` or `broker/` beyond the dedupe key (ADR 0011).

**THE UNINTENDED-CONSEQUENCE HALF, checked in the same pass rather than afterwards** — the card
fixed two readers that would otherwise have blended demotions into HIGH-only statistics, and that
fix is what the widening could most plausibly have broken:

- `judge_divergence_marginal_high_signal` reads **8**, with **0 non-HIGH rows leaked** into its
  population. The table splits cleanly: `primary_tier='HIGH'` 99 rows / `'MODERATE'` 1 row.
- Cost: **1 demotion call in 4 days ≈ 1.8/week against the priced ~5/week.** Below, not above.

⚠ **What this does NOT establish.** One demotion is one demotion. The dedupe key held over 3 alerts
in a thin window (nothing alerted 09-15) — that is not a volume test, and a busy morning is where a
dedupe key would actually be stressed. The priced ~5/week rate is likewise unobserved: it comes
from 17 demotions over 24 days of history, not from live counting. Neither was part of the DoD.

---

## #239 — closed as a CONVENTION, not as finished work (operator-ruled 2026-09-16)

BAR: "part (a) extracts at the THIRD PERMANENT consumer and not before, and part (b) stays unbuilt
with its over-abstraction reasoning intact"

WOULD-FAIL-IF: "the trailing-baseline is extracted while both consumers are still disposable
scripts". Nothing was extracted — the duplication is still two copies, deliberately.

EVIDENCE: **Both halves of that bar are preserved, on a durable surface rather than on a dated PLAN
line.** The operator ruled the close on 2026-09-16 after the alternative (a third signed re-date)
was put to him alongside it.

- **Part (a) — the deferral still holds, re-verified not assumed.** `grep -rn "catalyst_quality =
  'game_changer'" --include='*.py'` across the repo (tests and agent worktrees excluded) returns
  **exactly two files, both still throwaway `scripts/`**: `_wave_a_grade_inflation_check.py` and
  `verify_monday_firstfire.py`. **Permanent consumers: zero.** Nothing in `agents/`, `core/` or
  `channels/` computes a per-day game_changer/HIGH count over a trailing `alert_date` window.
- **Part (b) is unchanged WON'T-DO**, with its reasoning carried over verbatim: provenance is
  intra-grade while the tape and Perplexity reads are post-grade, so one envelope over both hides
  the context difference.
- **Both now live in `docs/architecture/market_agent_reference.md` § "When to extract a shared
  helper"** — the build-conventions doc CLAUDE.md already routes to.

**WHY THIS IS A CLOSE AND NOT A BURNDOWN DODGE.** The bar above describes a STATE TO MAINTAIN, not
an action to complete: "extracts at the third permanent consumer **and not before**" can never be
finished, only kept. A line that cannot complete re-dates forever — this one had been on the board
since June and was already `[b2]` with two signed `[ok:]` tags, so its third re-date needed his
sign-off anyway. The rule did not disappear; it moved to where rules belong. Nothing about the code
changed in either direction.

⛔ **A GATE WAS CONSIDERED AND DELIBERATELY REJECTED.** The obvious "mechanise it then close it" move
— a test that greps for this SQL shape and fails at a third hit — would be a guard over a condition
a real third consumer would most likely never trip: a different column alias, `catalyst_quality IN
(...)`, or a `TIER_RANK` comparison all read as new code while computing the same thing. Building a
check that cannot fire and then closing the task **because** a check exists is fake burndown wearing
mechanisation, and the burndown rule forbids exactly that. The written convention is the honest
instrument here, and its limitation is stated where it lives.

⚠ **What this does NOT establish:** that the duplication is harmless. It is real — the 2026-06-28
review was right about that — and a third permanent consumer makes extracting it correct. What
changed is only where that instruction is recorded.

---

## #656 — a `core/` change no longer ships to orchestrator and leaves the trading box stale (closed 2026-09-16)

BAR: "a `core/` file that the market image COPYs sets NEED_MARKET and NEED_EXEC, and a test derives
the expectation FROM `docker/Dockerfile.market`'s COPY lines rather than restating a hand-written
list — a hardcoded list rots the same way this arm did"

WOULD-FAIL-IF: "it prints DEPLOY OK with no execution warning, as it did today" (2026-09-13).

EVIDENCE: **VERIFY-LIVE ran on the prod checkout at 2026-09-16 12:0x ET, against the two exit codes
pre-registered on the task BEFORE it shipped** — `core/job_audit.py` → **exit 0**, `core/orchestrator.py`
→ **exit 1**. Both halves matter: the positive proves the new arm is on the box, the negative proves
it did not become a blanket that drags every orchestrator-only `core/` edit into a three-service
deploy. `core/notifications.py` (exit 0) and `core/router.py` (exit 1) confirm the pair.

- **Both DoD halves are met, and the second one is the point.** `_market_image_copies_path`
  (`scripts/deploy.sh:177`) awk-parses `docker/Dockerfile.market`'s COPY lines **on every run** —
  exact path or directory-COPY prefix — and the split-out `core/*` arm sets `NEED_MARKET=1;
  NEED_EXEC=1` only when it says yes. No hand-kept list in the script OR the test: the old arm was
  CORRECT when written and rotted the day those two COPY lines were added, so a list either place
  would just certify the next rot.
- **The test executes the real shell.** `tests/test_deploy_scope_core_copies.py` extracts the helper
  AND the entire per-file `case` block verbatim from `deploy.sh` and runs them, so it cannot pass
  against a drifted re-implementation. It also runs **the DoD's own acceptance check** — touch a
  COPY'd `core/` file, classify as `both`, assert `EXEC_DRIFT=1` and that the warning names
  `bash scripts/deploy.sh execution`.
- **RED-proven against three mutations, not written green:** restoring the original merged arm → 3
  red (including the acceptance check); an over-broad `core/* always market+exec` → 1 red; hand-listing
  the two paths in the helper → 1 red. A vacuity guard fails loudly if `Dockerfile.market` ever stops
  COPYing `core/` at all, so none of these can pass by having nothing to check.

⚠ **What this does NOT establish.** It has not yet been exercised by a REAL `core/` change flowing
through a real deploy — the verify ran the classifier on the prod checkout, which is the decision the
guard makes, but not the full `deploy.sh both` path end to end. That path is covered by the extracted
acceptance test rather than by a live run, because manufacturing a `core/` edit to watch the warning
fire is not worth a deploy. The next genuine `core/` change is the real proof.

⚠ **And it fixes the packaging half only.** The guard is still coarse elsewhere by design — the
`agents/market_intelligence/*` arm leans on the machine-derived `scripts/exec_loaded_modules.txt`
(#456), and anything unrecognised falls to the catch-all that requires all three. Those were already
right; nothing here touched them.

---

## #316 — PDT / Rule 4210: the work was done on 2026-06-04 and the task waited three months for it (closed 2026-09-16)

BAR: "Alpaca's OWN 4210 rollout is confirmed from Alpaca (not inferred from Fidelity's), and
`BLOCK_PDT_LOCKOUT` is then relaxed through CHANGE_PROCESS or explicitly kept"

WOULD-FAIL-IF: "the lockout is relaxed on a broker announcement that was never Alpaca's — the
confusion this line was created to prevent." **It was Alpaca's, in writing, on our own account.**

EVIDENCE: **Both halves were satisfied on 2026-06-04 and written into the safeguards SSoT the same
day. Nothing was outstanding; the line was re-dated four times waiting for an event that had already
happened, and the proof was in our own change log the whole time.**

- **Half one — it was ALPACA, which is the entire point of the WOULD-FAIL-IF.**
  `docs/setups/safeguards.md` change log, **2026-06-04**, Trigger: *"Alpaca operator email 2026-06-04
  — 'We have officially lifted the Pattern Day Trader rule and replaced it with the new intraday
  margin framework.' FINRA retired the PDT rule; **Alpaca confirmed the rollout on our account.**"*
  The entry names the memory this task cites and quotes its gate verbatim.
- **Half two — relaxed through CHANGE_PROCESS, with every required field.** The same entry carries
  Trigger / Evidence / Anticipated effect / Reversion-flag / Status. `BLOCK_PDT_LOCKOUT_ACTIVE` and
  `_IMMINENT` plus `_emit_pdt_warning_once` were removed from `live_tracker.py`; no Apollo-side
  day-trade gate replaced them (overextension is Alpaca's broker-side intraday-margin pre-trade
  check). The skip-reason constants were deliberately KEPT so historical rows still render — which
  is why grep still finds the names and why this looked open at a glance.
- **Verified in PRODUCTION today, not inferred from main:** `grep -c BLOCK_PDT_LOCKOUT` inside the
  running `apollo-execution` image's `live_tracker.py` returns **0**, and the retirement comment sits
  at line 215 where the guard used to be.
- **And it never blocked anything:** `mi_live_trades` carries **0 rows** with a `block:pdt_lockout%`
  skip reason, lifetime.

**WHAT TRIGGERED THE CLOSE.** The operator said *"The day trading rule is live"* on 2026-09-16. That
is true and was the half this task was gated on — but checking our own side before acting on it
showed the gate had been cleared in June. The task's last bump said *"If Alpaca has still said
nothing by then, propose closing it and re-opening on the announcement rather than bumping a ninth
time."* Alpaca had said something, fifteen weeks earlier, to us, by email, and we had already acted.

⚠ **What this does NOT establish.** That the new intraday-margin framework is safe for us — that is
Alpaca's broker-side check now, and nothing Apollo-side replaces it. The June entry says so plainly
and accepted it; this close does not re-open or re-endorse that decision, it only records that the
decision was made, documented and shipped.

⚠ **Left deliberately:** `BLOCK_PDT_LOCKOUT_IMMINENT` / `_ACTIVE` remain in
`broker/skip_reasons.py` with their `humanize()` labels. They are dead vocabulary, kept on purpose
so historical rows render. Do not "clean them up" — removing them makes old rows unreadable, and
their presence is what makes this task look open to a grep.

## #667 — the HTF outcome table recorded trades we could not have taken (2026-09-18)
BAR: the settler REFUSES to book a fill it could not have got — if the break day's low is above the entry it abstains and says so — and it abstains across a split between the break date and the settle date instead of comparing raw to adjusted prices. Plus a one-off pass marking the two known-bad rows so they cannot be counted.
EVIDENCE: Deployed two-step 2026-09-19 00:14–00:19 ET (market-agent then execution; server HEAD `c5def058`, both containers healthy). The task's own confirming check — *"re-run the prod query that found these (2 of 18) and get 0 bookable-but-unfillable rows"* — returns **0** against a measured baseline of **2**, a positive count against a known-nonzero start rather than an absence. Readout read from INSIDE the running image, not the banner: `open_n 10→9 · settled_n 10→8 · capture_n 1→0 · stop_n 3→2 · timeout_n 6 (unchanged) · unbookable_n 0→3`, and the operator-facing line renders `🚩 Breakout-entry shadow — 9 open · 8 settled (0% capture) · 3 unbookable`. WOULD-FAIL-IF checked in both directions: all 8 rows that still carry an outcome have a break-day low BELOW their entry, so nothing was over-marked. ⚠ The one-off pass covered **three** rows, not the two the DoD names: id 7 CDNA 2026-07-31 (entry 40.47 vs break low 40.67 — unfillable, and the table's only `capture`), id 3 CRWD 2026-07-01 (1:4 split on 07-02), and id 18 IOVA 2026-09-16 (entry 9.41 vs low 9.44), which landed after the 2026-09-16 measurement — the accrual the task warned about. CRWD is invisible to the unfillable query (raw 778.82 vs adjusted 191.25 reads as fillable), so the two defects needed two detectors. Pre-state snapshotted before the UPDATE. Both guards RED-proven in `tests/test_667_unbookable_htf_fills.py` (7 tests, two exercising the real settle job end to end). Suite 8466. ⚖ Shadow telemetry only — `prepare_htf_breakout_order` untouched, no detection criterion or entry rule changed. 🔴 Stated plainly: the HTF breakout shadow now shows **zero winners in 8 settled rows**; nothing downstream breaks, because #397 was never near its N≥10 winners and the 2026-09-10 conclusions came from a 148-breakout raw-bar replay, not this table.

⚠ **AMENDED 2026-09-19 (same night, found by review): THE CLOSE ABOVE COVERED THE PRODUCER AND NOT THE CONSUMERS — the defect is real and is now fixed, so the close stands with this correction attached rather than being reopened.** Marking a row unbookable stops Phase 3 SETTLING it. It does not stop anything else READING it. `get_htf_management_shadow_candidates` (#396, the Phase-4 management replay) selects on `would_reject_reason IS NULL AND m.status = 'open'` — the new column is not in that predicate — so **CDNA/shadow 7, the 40.47 entry against a 40.67 break-day low, had already been carried to `closed_trail_exit` at +1.96R** in `mi_htf_management_shadow`, and IOVA/shadow 18 was queued to be replayed again on the next 21:36 ET run. A winner, in the readout that answers *"what would the sourced management protocol have done"*, on a fill that could not have happened. **This is the day's own defect class one layer out — the deal-pin fix filtered one of six POOLS; this filtered one of four CONSUMERS.** [[derive-the-population-never-hand-list-it]] **Fixed:** the candidate query excludes them, and `get_htf_management_shadow_summary` now counts `unbookable_n` separately and excludes it from every other figure (measured on prod: open 2→1, closed 10→9, trail-exit **4→3**, hard-stop 6 unchanged, median realized-R −0.508, unbookable_n 2). The two rows already written are **kept, not deleted** — the replay is a full recompute each run, so they carry no state, and a count that vanishes cannot be questioned. ⚠ The other two readers were checked and are clean by construction: `sell_discipline.py` filters `outcome IN ('capture','stop')` and an unbookable row's outcome stays NULL forever; `health_checks.py` reads `break_date` freshness only. **The guard is now DERIVED, not hand-listed** — `test_no_reader_of_the_shadow_table_can_count_an_unbookable_row` walks every `FROM`/`JOIN` of the table across `agents/` and requires each to exclude the abstained rows or filter on a positive outcome; it goes RED on the pre-fix predicate, verified by mutation. ⚠ **The `keep` decision was then checked against its own population, because keeping the rows is only safe while every read of `mi_htf_management_shadow` joins its parent.** Derived: `db.py`'s three statements (all fixed), `sell_discipline.py` (outcome-positive, clean), and **one reader the regex cannot see** — `health_checks._SWEEP_LANES` names the table in a registry TUPLE and interpolates it, so there is no literal `FROM` to match. It is safe by what it COMPUTES rather than by a predicate: it counts DISTINCT `trail_mode` values per subject and skips any lane under 10 multi-variant subjects, and prod has exactly one arm (`ema_10_20`, 12 rows), so `realized_r` is never aggregated into a claim there. The gate now walks **both** tables and requires the literal predicate `settle_abstain_reason IS NULL`, not a mention of the column — a first draft accepted the mention and passed clean against a mutation that deleted the whole parent join, the same failure as anchoring a registry edit on a mention instead of the declaration. ⚠ **`docs/analysis/610_htf_replay_2026-09-10.md` footnoted:** its reconciliation paragraph cites `CDNA 07-31 +1.959` as a validity spot-check. **The +0.74R mean quoted on #397's line is NOT contaminated** — it comes from the 147-breakout raw-bar replay, not this table, and that document already carries the fill-realistic figure (+0.55 excluding the 8 unfillable entries). 🔎 **Scope, stated honestly: `get_htf_management_shadow_summary` has zero callers, so the impossible +1.96R sat in a stored table and never reached the operator through any command.**

## #660 — the market-adjusted correlation maths moved out of the EP module (2026-09-18)
BAR: no `etb._`-prefixed access anywhere outside `ep_theme_belonging.py`; neither module lazily imports the other for this math; and the full suite passes with NO test edited except import paths — a move that needs a behavioural test changed is not a move.
EVIDENCE: All three clauses checked by hand, not taken from the card's report. (1) `grep -rn "etb\._" agents/ scripts/ tests/ channels/ core/` excluding `ep_theme_belonging.py` returns **nothing**. (2) The only remaining `import ep_theme_belonging` in `theme_engine.py` is at MODULE level (`:4396`), not lazy, and is for `fetch_closes` — I/O, which deliberately did not move because `tests/test_theme_assign_comove.py` patches it to drive the context loader. (3) `git diff ee7842cf HEAD -- tests/` is **one file, +2/−1**: an added `import market_adjusted_correlation as mac` and `etb._basket_mean` → `mac._basket_mean`. An import-path edit and nothing else. Suite **8467 passed, 7 skipped**. WOULD-FAIL-IF (*"any correlation value or admit/reject verdict differs before vs after on a replay of the same inputs"*) tested on REAL prod data — 25 active themes, 152 tickers, 10,437 closes as of 2026-09-18 — under both code versions: **155 (theme, member) rows, 128 carrying a real correlation, ZERO differences**, locally AND inside both deployed containers (`excess_md5 380d36cc…`, row set `90f0855f…`, identical old vs new). Deployed two-step 2026-09-19 00:38–00:42 ET, server HEAD `e867b592`, both containers healthy. 🛑 **AND MY FIRST VERIFY CRITERION WAS WRONG — recorded because the correction is the useful part.** I wrote VERIFY-LIVE as *"re-run the harness inside the image and get the identical md5 to my local run"*. The container returned different hashes, and for a moment that read as a regression. It was not: the largest difference across 128 correlations was **5.55e-16**, one float64 ULP, because macOS numpy reduces through Accelerate and the image through OpenBLAS. **A cross-platform byte-match is a criterion correct code fails** — it tests the BLAS, not the refactor. The right criterion is OLD vs NEW on the SAME platform, which is what the evidence above reports. Zero verdicts moved across the 0.35 admit bar either way. ⚖ Refactor only: no bar, no threshold, no criterion; the beta-residual and SPY-subtraction definitions stay separate.


## #560 — what theme assignment actually costs, and against what pool (2026-09-19)

BAR: after 5+ weekday runs, report from `api_usage`: assignment cost/night and the uncovered-pool size/night as a PAIR (the cost is only interpretable against the pool), the trend, and the implied monthly run-rate. Then a straight recommendation: keep / bound the pool / pull it.

EVIDENCE: **Nine weekday runs** (2026-09-08 → 09-18), read from prod and written up in `docs/analysis/560_theme_assignment_steady_state_cost_2026-09-19.md` — every night's cost paired with the candidate pool it acted on, which is the half the bar insists on. **Cost/night: $0.2084–$0.2433, mean $0.2204, FLAT across all nine.** **Pool: 178 → 159, about −2 a session.** **Implied run-rate ≈ $4.63/month.** **RECOMMENDATION GIVEN, and it is one word: KEEP** — do not bound the pool, do not pull it. The condition this task set was *"pull it if the backlog does not clear"*, and the backlog is clearing; bounding a pool that is already shrinking would trade coverage for no saving. ✅ **The DoD's `ALSO CHECK` is answered too: `batch = 18` HELD** — it reads 18 on all nine nights, and this is the FIRST time it has been measured rather than modelled (the task flagged it as modelled because every pre-fix call was censored at the token cap, so no clean sample existed). **Zero calls hit `max_tokens` on any night**, so the 2026-08-10 output-bounding fix held. ⚠ **Population trap avoided and recorded:** `caller ILIKE '%assign%'` also matches `theme_ecosystem_assignment` and inflates every figure — the read uses `caller = 'theme_assignment'` exactly. My first pass used the ILIKE and would have overstated the cost by ~20%. ⚠ **Not over-read:** n=9 and the decline is gentle; at −2/session the pool takes ~80 sessions to empty and may plateau in the 120–160 band instead. That is a reason not to claim the backlog is solved — not a reason to pull a $5/month job. ⚠ **AMENDED the same day, on his question — *"Are these stocks being assigned to themes?"* — and it corrects my DESCRIPTION, not the verdict.** They are: **13–36 proposals a night, 11–18 surviving the co-movement gate.** But **total theme membership is FLAT at ~705 (ticker, theme) pairs, oscillating 682–735 with no trend**, because assignments are offset almost exactly by removals (`ticker_revalidated_out`, `validation_cooldown_triggered`, theme retirements). **So the pool is NOT a pile being worked down: if 11–18 leave it nightly by assignment and it falls only ~2, then 10–16 NEW candidates arrive each night.** It is a steady-state QUEUE with inflow ≈ outflow. **"The backlog is clearing" was the wrong description** — I had implicitly modelled a pile with an end, and there is no such end. The correct statement is that the pool is stable and slightly declining because inflow and outflow are near balance. ⚖ **The recommendation is UNCHANGED and better supported:** the worry was unbounded growth, there is none, and the job places 11–18 stocks into themes every night for 22 cents. KEEP. ⚖ Measurement and a recommendation only; no code, threshold, schedule or detection criterion changed.


## #669 — a review must now declare that its predicate counts what its action can act on (2026-09-19)

BAR: TWO HALVES, BOTH REQUIRED. **(a) A FORCED DECLARATION, the `discriminates_on:`/`WOULD-FAIL-IF:` pattern**: every new or edited review states, in `can_fire:`, **that the rows its predicate COUNTS are rows its action can ACT on**, and **what instrument the action reads and why that instrument is trustworthy**. Gated in `check_plan`, new/edited only, existing entries a counted backlog. A gate cannot check the answer — it forces the question, which is what stopped this class before. **(b) AN AUDIT PASS over all 55 pending entries** producing, per entry: does the predicate's population match the action's · is the question already answered elsewhere · does the method read an instrument known to be broken · can the decision rule return more than one answer.

EVIDENCE: **Both halves shipped and merged to main 2026-09-19.** ⚙ **(a)** `check_plan._CAN_FIRE_KEYS` went 5 → 7 with `population_actionable` and `instrument_trusted`, and `era_scoped` was re-defined as the eras of every table the METHOD reads rather than the window the cohort spans. New/edited-only exactly as the bar specifies, with the untouched entries printed as a counted backlog; `status: done` added to the skip tuple so a CLOSED review is no longer treated as a proposal. 6 tests in `tests/test_review_can_fire_gate.py`, each RED-proven by mutation. 📋 **(b)** All **60** open entries audited (54 pending + 6 deferred) in `docs/analysis/669_review_registry_audit_2026-09-19.md`, one row each with population / answered-elsewhere / instrument / decision-rule / era, and a disposition — **19 re-gated, 1 closed, 40 verified. None left un-triaged.** 38 entries edited in the registry, **0 added, 0 removed**.

🔍 **VERIFIED BY ME RATHER THAN TAKEN FROM THE CARD'S REPORT** (CLAUDE.md: never rubber-stamp a premium model), and the verification pass found a real error. **The one CLOSURE, checked first because closing is irreversible:** `perplexity_transient_timeout_alert_noise` is CORRECT and its data claim is exact — prod holds **5 timeout alerts life-to-date** (first 2026-06-29, last 2026-09-04), **0 in the trailing 14 days and 0 in the trailing 7**, against a threshold of *6 in ~1 week*, and the entry's own `action_when_ready` says *"If under threshold, the default is fine — mark done, no change."* **Mechanics:** `operator_asks.py --audit` reports **0 predicates erroring** and **0 zeros past their eligible date** (down from 1 at that morning's OPEN), and the `can_fire` backlog moved **39 → 22 of 160**, measured before and after rather than quoted. 🔴 **One load-bearing NUMBER was wrong and is corrected in both the YAML and the audit doc:** the entry for `orb_bar1_wick_outlier_persistence_filter` cited *"58 of 58 live entries since 06-18 have their 9:30 bar"* and **58 is not reproducible on any obvious population** — prod holds 138 distinct `(ticker, alert_date)` rows since 2026-06-18, of which **80 `skipped` and 24 `cancelled` never held a share**; the rows that actually entered are **31 `closed` + 3 `filled` = 34, and 34 of 34 have the bar (100%)**. The disposition was RIGHT and in fact stronger than claimed; only the count was wrong.

⚠ **THE LIMIT OF THIS CLOSE, stated rather than implied:** I verified the irreversible act, the mechanics, and **two of the 38 dispositions in depth — one of which carried an unreproducible number.** The other ~36 were not re-derived one at a time. That is the rate to assume for the rest, not zero, and it is recorded at the foot of the audit doc so the next reader inherits the caveat rather than the impression of a fully re-checked board. ⚖ Read-only diagnosis, registry edits and one `check_plan` gate — no detection criterion, threshold, trade state or money path touched.


## #168 — the shadow-detector promotion filter, RETIRED with a written reason (2026-09-19)

BAR: each shadow detector either graduates to a LIVE ping with its own evidence, or is retired with a written reason. WOULD-FAIL-IF: another silent date-roll — this line has been rolled repeatedly with no work, and its own text already says the next move is a real work/descope/split decision, not another roll.

EVIDENCE: **This closes on the RETIRED branch of its own DoD, with the reason written here — not on the graduation branch, and explicitly not on a seventh date-roll.** ▶ **THE REASON: the task's premise cannot fire.** It exists to be a quality filter GATING a shadow detector's promotion to live pings, and the operator's standing ruling is that **EP profitability comes before new setups — consolidation / HTF / wick must NOT graduate to LIVE until EP works** [[priority-ep-profitability-before-new-setups]]. Nothing is permitted to promote, so there is no promotion for this filter to gate. That was already established by the 2026-08-21 decision pass on the line; what was missing was the willingness to act on it. **Six re-dates, every one on *"not enough evidence yet"* — a reason that cannot be falsified and therefore re-dates forever.** The line's own WOULD-FAIL-IF names that as the failure, so keeping it open to roll a seventh time IS the failure mode, not a cautious alternative.

▶ **THE ONE LIVE CONCERN WAS MEASURED AND IS NOT A CONCERN — and the operator corrected my framing before I could file it.** I proposed a narrow follow-up task for detector VOLUME (`mi_flag_candidates` at **57,162 rows**, up from 46,300 in August; parabolic 2,179, consolidation 1,981, wick 105, HTF 20). His ruling, 2026-09-19: ***"size only an issue if we're low on storage, so no artificial rules unless we're negatively impacted by it."*** **Measured on prod rather than assumed: the box has 47 GB free of 75 GB (35% used), the database is 4.78 GB, and `db_growth_check` reads +43.7 MB/8d ≈ 5.5 MB/day ≈ 2 GB/year. That is roughly 23 YEARS of headroom.** So the flood risk this task carried since July is real as an arithmetic fact and irrelevant as an operational one. **NOTHING IS FILED.** Inventing a retention rule against a resource with two decades of slack would be the artificial rule he just ruled out. ⚠ **AND IT WAS ALREADY GUARDED — he asked *"we have a separate storage watchdog I believe"* and he was right, so the rule I proposed would have been a SECOND, dumber gate over a problem an existing one already watches.** `run_db_growth_check` (`health_checks.py:1479`) writes a `db_growth_check` audit row nightly using the audit log itself as the baseline store, and **Telegrams** when pro-rated weekly growth exceeds **300 MB** (`_DB_GROWTH_ALERT_BYTES`, ~10× the planned ~30 MB/wk, so a heavy earnings week or a 100–200 MB backfill stays quiet) **or** total size crosses **30 GB** (`_DB_SIZE_CEILING_BYTES`, half the disk headroom — the *someone should look regardless of rate* line), re-announcing at most weekly. **Today: ~38 MB/wk against a 300 MB trigger and 4.78 GB against a 30 GB ceiling — roughly 8× and 6× of margin.** Its own comment records that retention was ALREADY relaxed on measured storage maths (`mi_ep_alerts` kept forever, `mi_intraday_bars` 120d → 5y) against his condition that unbounded retention must not go unwatched. **So the volume concern this task carried since July was never unguarded, and I did not check before proposing to guard it again.** [[no-rules-without-measured-harm]]

⚖ Nothing shipped, nothing deployed, no detector promoted, demoted or silenced — a shadow detector that pings nobody today still pings nobody tomorrow. The graduation question returns through the EP programme, which is where it actually belongs.


## #299 — the tape-axis spend: page written, question asked, answer is NO (2026-09-19)

BAR: a written page saying what a tape-axis read would CHANGE — which decision it moves and what we do differently at each outcome — plus a scoped-smaller option and its price from `pricing_for()`, put in front of him for a yes or no. WOULD-FAIL-IF: the eval is funded and run without that page, which is precisely what he refused on 2026-09-07.

EVIDENCE: **The page exists (`docs/analysis/299_tape_axis_funding_page_2026-09-19.md`, 187 lines), it was put in front of him, and HE RULED: NO — confirmed 2026-09-19, *"we already aligned on no."*** The WOULD-FAIL-IF is satisfied in the strongest possible direction: **nothing was funded and nothing was run.** ▶ **What the page carries, against each clause of the bar:** *which decision it moves* — exactly one, the judge's tier on a HIGH alert, and the judge is load-bearing (178 of 181 alerts in 95 days carry `grade_engine_authority = judge`), so a demote removes the Telegram alert and the ORB entry; *what we do differently at each outcome* — a section per outcome including the null; *a scoped option and its price from `pricing_for()`* — **$86 full / $34 scoped**, against the **$170** figure that had been carried since June. ▶ **THE $0 CHECK WAS RUN FIRST and it is what decided the answer** (`scripts/probes/_299_tape_free_features.py`): **85 HIGH alert-days since 2026-08-01, 61 of them graded before 09:35 ET — verified against prod by me, not taken from the card.** The opening range does not exist until the open, so the axis's one genuinely new fact is absent when 7 in 10 grades are made. ▶ **And where it IS measurable it points the wrong way on his own ground truth:** of the 7 operator-named EPs, 4 reached the judge, **0 would gain anything**, and HTFL / MRNA / CHPT sit at the **88th–99th percentile of opening violence** — the class the tape block instructs the judge to mark DOWN. The block carries no promote instruction at all, so on the named EPs there was only recall RISK to buy. ⚖ A finding and a decision, nothing else: no toggle, prompt, rule, threshold or entry criterion changed, and no money spent. The task is closed on his answer, not on the page's recommendation.


## #368 — the theme weighting is spec'd: leave it at 10, do not extend it (2026-09-19)

BAR: the weighting spec'd + the labeled themeless-winner-inclusive cohort.

EVIDENCE: **Both halves met, and the operator ruled on the number today.**

▶ **THE LABELLED COHORT — already done, and he was the one who said so.** He challenged my listing it as outstanding (*"I thought I already did the labeling"*) and prod agrees: `mi_theme_relevance_cohort` holds **103 of 103 `themed` rows labelled** (last 2026-09-13) and **134 labels overall — 92 yes / 41 no / 1 unsure**. The 136 unlabelled rows are all `themeless_winner` and unlabelled **by this entry's own design** (*"do not pad it with the themeless stratum by default"* — that stratum guards a DIRECTION, never penalise themeless, not the MAGNITUDE the weighting rests on). **31 themeless winners ARE labelled, so the cohort is themeless-winner-inclusive exactly as the bar words it.** ⚠ I raised finished work as outstanding without checking; the check is one query. [[never-re-ask-an-answered-question]]

▶ **THE WEIGHTING — SPEC'D: `theme_bonus` stays at 10 points, paid only to Accelerating/Mainstream, `R4_THEME_BONUS_ENABLED` unchanged. Do not raise it, do not extend it to Nascent, do not cut it to zero.** Operator: *"Ok"*, 2026-09-19, on that recommendation.

▶ **WHAT DECIDED IT — the quality read he himself asked for** (`docs/analysis/368_theme_boost_reach_vs_quality_2026-09-19.md`). His 2026-09-14 ruling was **YES to Nascent paying, conditional**: *"as ITS OWN change, AFTER the 2026-09-14 deploy has been read"*, with the warning that the evidence was **reach, not quality**. That read has now happened and **the condition failed**: alerts whose ticker sat in a Nascent theme on its own alert date perform the SAME as alerts in no theme at all — **10.66% vs 10.46% at five days, 13.34% vs 13.45% at ten, n=27 against n=293**. Two-tenths of a point is noise. **So this is not a reversal of his ruling; it is the test his ruling asked for, returning no.** ⚠ The +10% hit rate leans the other way (59% vs 43%) on ~4 alerts of swing — recorded, not weighted.

▶ **WHY NOT CUT IT TO ZERO EITHER:** the +10 was signed on real May-2026 evidence (67% WR in-theme vs 40% uncovered, +27pp). Today's read does not reproduce that lift — mature-theme alerts run 8.88%/9.74% against a 10.46%/13.45% themeless control — **but it rests on 23 settled outcomes, and 23 rows are not grounds to reverse a signed decision.** Leaving a number alone when the evidence is too thin to move it in EITHER direction is the decision, not the absence of one.

⚠ **CARRY THE CAVEAT: this is a BASELINE, not a verdict on the theme engine** — *getting themes right and getting returns are separate questions until the engine is fixed* [[themes-not-judged-on-returns-yet]].

🔭 **THE RE-READ IS MINE, NOT HIS, and it is measurement rather than a decision:** re-run the same table when the paying buckets reach ~25 settled outcomes each. **Accelerating is the one to watch — n=5 today, the most eye-catching number in the table (18.49% / 22.43%) and the least trustworthy.** Filed under #655's theme-measurement lane rather than as a new board line, since it is a re-run of an existing query against a bigger n.

⚖ Nothing shipped: no toggle, no threshold, no prompt and no grade changed. STEP-3 (the #335 flip) is separately already done — `compute_theme_axis_credit_live` was unplugged and retired 2026-09-19.


## #674 — WITHDRAWN the same night it was filed: one job has ever needed a ceiling (2026-09-19)

BAR: a second job can be given a ceiling by adding one kwarg at its registration site, with no new wrapper function and no second audit row or Telegram for one incident.

EVIDENCE: **Withdrawn, not completed — and the distinction is the whole entry.** ▶ **It was filed hours earlier, from my own simplify pass, and the operator asked the question that killed it: *"are those legit new work?"*** An adversarial audit of all four filings returned NOT_WORTH_DOING on this one, and the reasoning holds: **its DoD is written about a SECOND job that does not exist.** Exactly one job in 78 has ever needed a ceiling (`nightly_data_pull`, #672), and the concrete harm this line was reacting to — the bounded wrapper shipping its own duplicate audit row and Telegram on top of `audit_wrap`'s — **is already fixed and deployed** (`592987ec`, verified in both containers). What was left was general infrastructure built ahead of its second caller, which is the repo's own standing rule in reverse: *"no artificial rules unless we're negatively impacted by it"* (operator, 2026-09-19). ⚠ **The premise checked out TRUE** — `audit_wrap(fn, job_id, expected_min_rows=None)` has no `timeout_s`, and `audit_run`'s `CancelledError` branch does already carry the right vocabulary for a deliberate cut-off. **Its facts were right and its timing was wrong**, which is a different failure from #673's beside it, where the facts themselves were false. 🎯 **THE TRIGGER, recorded so the insight is not lost with the line: the day a SECOND job needs a ceiling, add the `timeout_s` kwarg to `audit_wrap` rather than writing a second wrapper — and whoever does it should read #672's wrapper first, because its first draft shipped a duplicate failure surface and that is the mistake the kwarg exists to prevent.** ⚖ Nothing shipped, nothing deployed, no job's behaviour changed by this withdrawal.


## #676 — the delegation ledger can see workflow-spawned agents now (2026-09-20)

BAR: a day whose work ran through `Workflow` shows those agents in the ledger with their models, and the ROUTING GAPS section stops flagging a task that was in fact carded. VERIFY: re-run `delegation_report.py --day 2026-09-19` after the fix and confirm it reports the Fable cards behind #652/#669/#299/#610, not zero. WOULD-FAIL-IF: the count still reads 4 on a day with workflow cards.

EVIDENCE: **Both halves met, and the VERIFY re-run is the evidence rather than a description of it.** ▶ **`--day 2026-09-19` now reads `agent spawns: 22 · sonnet 17, fable 5` against the 4 it reported at Friday's CLOSE.** All four tasks the VERIFY names are present — checked in the DATA, not from the printed list, because the CLI truncates at four and #652 sat past the display cap: `scan_day("2026-09-19").spawns` filtered to `fable` returns exactly five — `#640 mobile Rank Flow`, `#610 HTF four-reading observer`, `#669 review registry`, `#299 priced tape-axis page`, `#652 Telegram HTML default`. ▶ **Second half, on today's REAL declaration** (09-19's was overwritten by this morning's OPEN, so it cannot be read back): `--day 2026-09-20` prints *"routing gaps: none — every declared card model ran"* against `#661->fable, #662->fable, #673->fable, #675->sonnet, #676->sonnet, #672->main`, with #661/#662 fable and #676 sonnet having actually run. Before the fix that same day would have accused all three of being done inline.

⚠ **MY FIRST TWO VERIFICATION RUNS WERE WRONG AND SAID THE OPPOSITE.** From inside the card's worktree, `--day 2026-09-19` reported `0 transcript(s) scanned` and `--day 2026-09-20` reported `no routing declared today`. Neither is a defect: `transcript_dir()` munges the **REPO path**, and `.apollo_routing.json` lives in the main checkout — so from a worktree both resolve to directories that do not exist. Verifying a path-sensitive tool from a worktree measures the worktree. The real reads came from the main checkout, and from `APOLLO_TRANSCRIPT_DIR` pointed at the project dir.

▶ **Why it mattered enough to build on a Sunday:** this is the surface that tells the operator whether work was delegated, and it is the one he used on 2026-09-19 to catch card-shaped work being done inline (*"Are you intentionally running everything in math thread?"*). At that same day's CLOSE it printed *"#610/#669/#652/#299 were declared FABLE work this morning, but no fable agent ran today"* — on a day whose Fable cards had already merged as `7e494bb5` and `5a2d87bf`. **A checkpoint that reports the opposite of the truth trains you to ignore it**, which is worse than not having one.

📐 **Mechanism, stated because the fix is a derivation and not a path:** `transcript_dir()` reads only `~/.claude/projects/<munged-repo>/*.jsonl`, where a DIRECT `Agent` spawn appears as a `tool_use` block. Workflow-spawned agents live in a sibling tree, so the ledger now derives `session_dir = session_path.with_suffix("")` for every session file it already scans and walks `session_dir/subagents/workflows/*/`. Nothing is hard-coded to one session. Double-counting was checked across **224 real saved transcripts** — zero agentId overlap between the two trees — plus a `(wf_dir, agentId)` dedup inside `scan_day`; a day with both kinds sums correctly (4 direct + 18 workflow = 22).

⚖ Reporting and telemetry only — no trading surface, no gate behaviour, and the tool still fails OPEN. Ten mutations run and named. **One drafted test was DROPPED rather than kept** because no mutation of the real code could redden it — the right call, and exactly the kind of assertion that otherwise ships green and meaningless. ⚠ Named as left undone: `_workflow_agent_day` silently skips an agent whose first transcript line carries no usable timestamp (fails open; no transcript on this machine hits it). Suite 8614.


## #261 — the scripts/ root holds nothing throwaway, and the guard proves it (2026-09-20)

BAR: VERIFY-LIVE = the #285 root-hygiene guard reddens on a newly added root-level probe, and `scripts/` root holds nothing that is not imported, referenced by code, or cited by a review.

EVIDENCE: **Both halves run by me, not taken from the audit that surfaced it.** ▶ `python3 -m pytest tests/test_scripts_root_hygiene.py -q` → **2 passed** against the live tree. ▶ **The RED half is the one that matters and it was exercised for real:** `touch scripts/_zz_probe_check.py` → the same suite goes **1 failed, 1 passed**, naming the new file; removing it restores green and `git status` is clean. A guard that only ever passes is not evidence, and this one was made to fail on demand. ▶ **The inventory half:** the sweep re-ran the code-reference check across `.py/.yaml/.yml/.sh` over every `KEPT_AT_ROOT` entry — **2 of 92 carry no external code reference, and both are tagged `operator-tool:write`** (`seed_drawdown_breaker.py`, `set_kill_scale_override.py`), a documented category of standing operator control levers rather than throwaway probes. ⚠ **Stated because the DoD's literal wording does not name that exception:** "imported, referenced by code, or cited by a review" does not say "or is an operator tool". It is covered by the guard's own taxonomy and by #261's prior scoping, which re-homed the ops/evals split to #419 Phase 2 — recorded here so it is not re-litigated as a gap. ⚖ Repo hygiene only; no trading surface.

## #665 — the exit-rule boundaries are ONE object and #662's generator reads it (2026-09-20)

BAR: DoD: the boundary list exists as ONE object, #662's generator reads it rather than carrying its own dates, and re-running #662's exit read splits era D by itself with no hand-written date list anywhere in the query.

EVIDENCE: **Run against the LIVE image, not reasoned about.** ▶ `get_setup_era_trades(90)` joined with `rule_eras.exit_era_label(alert_date, signal_type)` inside `apollo-market` returns **era_a 12 · era_b 10 · era_c 6 · era_d 2** — and era_d = 2 matches #662's own hand-count exactly, from the shared object with no date literal in the query. ▶ **The no-hardcoded-dates half:** grepping #662's named scope (`system_review.py`, `ep_replay.py`) for all five `EXIT_SWITCHES` dates returns 7 hits and **every one is a comment or docstring** — prose explaining the fix, not a literal the code branches on. ⚠ **CARRY THIS, it is a live trap for the next reader:** `exit_era_label` called WITHOUT `signal_type` silently returns `era_c` for any post-flip date, so the same query answers era_d **0** instead of 2. Its own docstring warns of it, `system_review.py:2496` passes the argument, and the sweep reproduced the wrong answer first. ⚠ **AND A LIMIT THE DoD's WORDING DOES NOT COVER:** its WOULD-FAIL-IF says "any reader still hardcodes a boundary date" — repo-wide that is NOT met. Several one-off probes and backtests (`scripts/probes/*`, `live_fill_counterfactuals.py`, `scripts/stop_2r_counterfactual.py`) still carry era dates independently. Closed on the DoD as WRITTEN — "#662's generator" — with the wider gap named here rather than quietly inherited. ⚖ Reporting boundary only.

## #630 — a 9:31 fill sized off the real regime, not the floor (2026-09-20)

BAR: a `lane2_decision_record` carrying `lane2_narratives_at_decision`, and no row carrying `active_themes_at_decision`

⚠ **THE GATE CORRECTED MY FIRST DRAFT OF THIS ENTRY AND IT WAS RIGHT.** I quoted the DONE-WHEN (*"one 9:31 fill at full size with no fallback row"*) as the BAR. `close_bar_for` takes the FIRST `VERIFY:` on the line, which is the rename half above — and closing against a later, narrower sentence is precisely the #540 failure the gate was built for. Both halves are evidenced below; the DONE-WHEN is the binding one and is NOT dropped by quoting the bar correctly.

EVIDENCE: **THE BAR ITSELF — the rename half — verified on prod: 3 of 3 `lane2_decision_record` rows since the 09-10 deploy carry `lane2_narratives_at_decision` and ZERO carry `active_themes_at_decision`.** ▶ **AND THE BINDING HALF, the DONE-WHEN, met by fills that had ALREADY happened and that nobody had checked against this line.** ▶ Two live fills since the 09-10 deploy: **DFTX 2026-09-14 09:33 at risk $24.52** and **VICR 2026-09-17 09:31:01 at risk $12.26**. **Zero `sizing_regime_fallback` rows since the deploy** (the only two in the table are 2026-09-08, before it). ▶ 🔑 **THE DISCRIMINATING PART, and it is stronger than "one fill at full size":** the two fills are sized DIFFERENTLY, and each tracks its own prior session's regime. Equity was ~$4,908 and ~$4,906. DFTX = **0.50% of equity**, the Correcting multiplier (0.5× base), with 2026-09-11 Correcting. VICR = **0.25%**, the Crisis multiplier, with 2026-09-16 **Crisis**. **A cache stuck on a fallback constant would have produced the SAME number twice.** Two different, regime-correct sizes across a regime change is a positive observable that a broken cache cannot fake — which is exactly what the verify-condition rule demands and what a "no fallback row appeared" reading alone would not have given. ⚠ **NOT A RE-ASK OF HIS 09-19 RE-DATE.** That "Ok" rested on "Saturday can produce neither a market day nor a fill" — true of that Saturday, but both qualifying fills predate the note and were never checked against the condition. New evidence, not a second bite. ⚖ Read of existing trade records only; nothing placed, cancelled or resized.


## #471 — the veto-alert lane is proven by its own synthetic replay (2026-09-20)

BAR: the fixture replay is green; a SYNTHETIC unassigned cluster demonstrably FIRES the veto alert; and a cluster with no veto is promoted at grace-end.

EVIDENCE: **All three clauses met, and the close gate is what found that — I was about to close this on the wrong bar entirely.** ▶ `python3 -m pytest tests/test_471_ecosystem_discovery_lane.py -q` → **64 passed**. ▶ Clause 2, the SYNTHETIC cluster firing the veto alert: `TestWeeklyPass::test_qualifying_resighting_goes_pending_and_fires_the_veto_alert`. ▶ Clause 3, promotion at grace-end with no veto: `TestGraceSweep::test_sweep_at_grace_end_promotes`, alongside `test_sweep_before_grace_end_does_nothing`, `test_double_sweep_promotes_once` and `test_promote_failure_is_audited_not_raised`.

▶ **NOT TAKEN AS GREEN — MUTATED.** Replacing the veto-page call with `sent = True` (skipping the page entirely) turns **6 of the 64 RED**; restoring it returns 64. ⚠ **My FIRST mutation proved nothing and I nearly banked it:** I short-circuited `_send_html` itself and all 64 still passed, because the tests inject their own sender and assert it was CALLED. Patching the transport under a stubbed test is not a mutation of the thing under test.

⚠ **THIS TASK WAS NEVER EVENT-GATED, and two passes in a row said otherwise.** Today's feasibility sweep classed it NEEDS_EVENT — waiting on a real cluster to survive 14 days — and I carried that forward and drafted a close on the operator's ruling that it *"doesn't need a board spot as long as if things go wrong we'll be alerted"*. The close gate refused it: the BAR I quoted did not appear in the task's own DoD. **The DoD never asked for a real cluster. It asked for a SYNTHETIC one** — which has been demonstrable on demand this whole time. [[check-what-the-system-already-did]]

▶ **HIS CONDITION HOLDS ANYWAY, and the checks are worth keeping since they were run:** promotion pages him first (`_send_html` → `send_telegram_message`) with a tappable `/vetoecosystem <E-CODE>` that soft-retires it; the job is registered through `audit_wrap` (`scheduler.py:7056`) so a failure writes a `failed` row and fires `record_job_failure`; and it is now inside the missed-job recovery population — `eligible_jobs()` returns 66 in the live container with `ecosystem_discovery` among them, so a skipped weekly slot is re-run with the date pinned rather than lost the way 27 of 28 jobs were on 2026-09-18.

📊 **CONTEXT, because I told him the opposite first:** **117 of 124 current themes are assigned across 22 ecosystem buckets**; only **7 are `E-UNASSIGNED`**, and those 7 are the discovery substrate. "No cluster this week" means no NEW bucket is needed — the normal outcome. I had read `mi_themes.parent_theme` (15 of 124) and reported 88% unassigned; the real mapping is its own table, `mi_theme_ecosystems`. He pushed back — *"Right now all themes belong to an ecosystem"* — and he was right. [[derive-the-population-never-hand-list-it]]

🔭 **ONE OPEN MECHANISM QUESTION, recorded so the close does not bury it:** the only candidate ever sighted (3 agriculture themes, 2026-09-13) dissolved on **day 3** when Phase 2 gave a member a `parent_theme` and retired it, dropping the cluster below `MIN_CLUSTER_THEMES`. Phase 2 and Phase 3 compete on the same substrate and Phase 2 is faster — **307 of 472 ever-retired themes (65%) finished retirement within 14 days of first appearing**, so the 14-day sustain bar may rarely complete in the wild. Low stakes (a new bucket is a proposal with a veto). **If it matters later, treat a member's absorption into a parent as CONFIRMATION of the group rather than dissolution** — that removes the race instead of shortening the timer.

⚖ Nothing shipped, deployed or changed by this close.


## #184 — the broker mirror: drift alerts fire, the gap they found was closed, /syncnow works (2026-09-20)

BAR: coverage-drift alerts live + mirror complete + /syncnow works → cutover prerequisite

EVIDENCE: **Three clauses, each checked against prod today rather than read off the line's own history.**

▶ **CLAUSE 1 — coverage-drift alerts live: YES. 144 `coverage_drift*` rows**, and the detector has produced a REAL detection, not just heartbeats: `coverage_drift_detected — D2_untracked_order_high ETON order=ee925e6b (live)` on 2026-08-14. It fires, on the live account, on the class the mirror exists to catch.

▶ **CLAUSE 2 — mirror complete: the gap it found was CLOSED. ETON now has a row in `mi_live_trades`**, so the untracked broker order it flagged on 08-14 was ingested. And **0 real detections in the last 30 days.** ⚠ **That zero is an ABSENCE, so it is only worth something if the detector was looking** — it was: the 15-minute reconcile it is wired into has **424 `order_status_reconciled` rows, latest 2026-09-18**, and the detector itself emitted 3 rows on 09-14. **A broken detector and a clean book produce the same zero; a detector that demonstrably ran, and that caught a real live D2 five weeks ago, does not.**

▶ **CLAUSE 3 — /syncnow works:** resolved 2026-06-24 (the "Unknown command" was a zero-width-character input artifact already fixed 06-04 by `_normalize`); 3 wiring sites confirmed present today.

⚠ **THE ONE HONEST WEAKNESS, stated rather than buried:** all 3 detector rows in the last 30 days are `coverage_drift_check_degraded — broker read failed (paper)`. The degraded-read guard is doing its job — refusing to declare a clean book off a failed read, which is the #137 guard working — but it means part of the recent quiet is *"did not look"* rather than *"looked and found nothing"*. **It is the PAPER account that degraded; the live path kept reconciling.** Worth watching if degraded reads spread to live, and named here so a future reader does not treat the zero as stronger than it is.

⚠ **AND A WORDING GAP FOUND ON THE WAY, which is why this line sat so long:** the line elsewhere describes waiting on a broker/DB **value** mismatch. `broker/coverage_drift.py`'s D1/D2/D3 are all presence/absence checks — untracked position, untracked order, DB-open-no-broker. **There is no detector class for "broker and DB disagree on a value"**, so a verify written against that wording waits on an event the code cannot emit. ▶ **Two value checks DO exist, found by grep rather than assumed:** share **quantity** is compared and auto-corrected to the broker's number at `order_manager.py:7112`, logging `sync_qty_overwrite`; and the R1 stop-**pointer** repair corrects a wrong `stop_order_id`. **The one value nothing compares is the stop PRICE** — recorded here as the open question, not smuggled into this close.

📊 **Accrual context for the increment-3 paths, measured:** R1 has corrected a stop pointer **twice ever, both `paper`, both 2026-07-11 — zero live corrections in the ~10 weeks since `live_r1` went live**. R3i has 2 clean dry-run proposals (08-06, 08-14), R2 has 0 since its false-positive bug was fixed 07-26, and nothing accrued on any path in 37 days. **Those paths belong to increment 3 (guarded auto-correction), which this DoD does not require** — the DoD is alerts + mirror + /syncnow, and increment 3 was always "never the first increment". Closing this does not ship auto-correction and does not need to.

⚖ Nothing shipped, deployed or changed by this close. Read-only verification of an observe-only lane.


## #640 — Rank Flow reads on a phone, and he says so (2026-09-20)

BAR: he can read it on his phone and say what it tells him. Concretely: the *outside* band separates *below the cut with a known rank* from *no rank at all*; labels legible; the ink weighted toward moves rather than stayers. WOULD-FAIL-IF: a ribbon still merges a data gap with a weak rank.

EVIDENCE: **His verdict, 2026-09-20: "640 looks good".** That is the bar — the DoD says readability is HIS call, the same as #561, and he has made it.

▶ **The three concrete clauses, verified in the shipped code rather than asserted:** the outside band renders as **"New / unranked"** (it previously merged two different things under one label); the movers list is **split by direction** via `movers_sections`, which was his one change request after the first phone read; and the chart is a **single hop across two columns** with the ink on movers rather than stayers. Dashboard suite **47 passed** on `test_theme_flow.py`, 145 across the repo.

▶ **THE WOULD-FAIL-IF IS THE INTERESTING HALF and it was settled by measurement, not styling.** The clause says a ribbon must not merge a data gap with a weak rank. **It cannot, because there are no data gaps: all 798 null-rank rows in the grid are stage Fading (424) or Retired (374).** A null rank is the engine's VERDICT, not missing data. ⚠ **I told him the opposite first** — "2 of 20 were data gaps, treat 10% as a floor" — and both of those were stage Retired too. Wrong in kind, not degree, and corrected in `docs/design/rank_flow_readable_sankey.md` before the build.

⚠ **ONE HONEST GAP AGAINST THE DoD's LITERAL WORDING:** it asks him to *"say what it tells him"*, and what he said is *"looks good"* — an approval of the surface, not a reading of its content. Recorded rather than papered over. The clause exists because readability is his to judge and he has judged it; if the view later fails to tell him anything, that is a new finding, not an unmet bar from today.

▶ **Raised, measured and DECLINED the same day, so it is not re-litigated:** extending to 3-4 columns to track a longer period. **A Sankey cannot draw a path across 3+ columns** — rank flow is a many-to-many transition matrix (32 distinct paths against 36 ribbons over 3 columns), while the reference expense chart he had in mind is a tree. Ribbon counts measured: 2 columns/4wk **17** · 3/8wk **36** · 4/12wk **52** · 5/16wk **62**, versus one LONGER hop at 17 → 11 → 9 → 7. His ruling: *"Ok, leave as is for now."*

🔭 **Open and unfiled, recorded in the design doc:** nobody has measured how often a cohort leaves a band and returns within one hop, so net displacement may understate churn.

⚖ Reporting surface only — no strategy, entry, exit, sizing or safeguard touched. Shipped in `portfolio-app2`.

## #673 — the six RS pools now read one universe, and the liquidity floor is dollars not shares (2026-09-21)
BAR: state, in the SSoT, whether the six RS pools are meant to share one universe; then either all six exclude known non-equities or the three that differ carry a written reason.
EVIDENCE: **Both halves of the DoD, plus the live board reading its verify asked for.**
- **SSoT half:** `docs/architecture/theme_engine.md` §"The six RS pools read ONE universe" states the ruling and the commit evidence behind it — the 3/3 split was ACCIDENTAL (`a744d7f6`, a 2026-03-23 evening hotfix on the leaders board only; `get_rs_velocity` 03-16 and `get_rs_turners` 03-18 already existed and were never touched; no commit or doc ever granted them a wider universe).
- **Code half:** all six exclude known non-equities. Gate `tests/test_deal_pinned_not_a_coverage_gap.py::test_every_rs_pool_reads_the_one_universe_or_says_why` reads **6/0**; 21 tests green 2026-09-21.
- **VERIFY ("re-run the AST check … confirm the split is 6/0 … not 3/3-silent"):** re-run today, 6/0, green.
- **The live no-op proof, measured rather than argued:** on the latest score_date (2026-09-18) `mi_stock_scores` holds **2,381 rows and ZERO non-equity rows** (join on `mi_tracked_stocks.quote_type`); the most recent non-equity score row of ANY date is **2026-03-23**. So the new clause removes nothing and the old-vs-new diff is empty by construction — which is exactly what EXPECT predicted.
- **Boards render (2026-09-21):** leaders 30, velocity 30, turners 21, recovery 12 — none empty, which was the stated UNINTENDED watch.
- **The dollar floor's predicted live proof holds: WGS IS on the leaders board.** It trades 497,989 shares × $101.10 = **$50.3M/day** and the old share floor rejected it by 2,011 shares. And **0 of the top-40 by RS sit under the $10M/day floor** — no name disappeared for a liquidity reason, the WOULD-FAIL-IF.
⚠ NOT claimed: the liquidity + small-cap-healthcare split across velocity/turners/recovery is still 3/3 and was deliberately left alone — it is POLICY that would change what the briefing shows, and it is his call. `get_ma_pullbacks` still sits outside the derived pool list. Both were reported to him and neither is part of this DoD.

## #678 — one reader for the mi_job_runs ledger, and the ORDER BY it forces is load-bearing (2026-09-21)
BAR: exactly ONE `FROM mi_job_runs` SELECT across `db.py` + `job_recovery.py` (grep-checkable) and the sweep triple unchanged post-deploy.
EVIDENCE: **Both halves, the second measured against a real pre-change baseline.**
- **One reader:** `grep -c "FROM mi_job_runs"` → `db.py` **1**, `job_recovery.py` **0**. Verified again inside both running containers after the deploy (`apollo-market`, `apollo-execution`).
- **The sweep triple, unchanged:** the first `job_recovery_sweep` after the deploy (2026-09-21 **12:06 ET**) logged `66 eligible job(s), 134 slot(s) examined, 0 gap(s), 0 unrecoverable` — **byte-identical** to the pre-change sweep at 2026-09-21 00:00 ET on the same ledger. That was the pre-registered EXPECT and the WOULD-FAIL-IF was any movement in the triple.
- **The ordering risk was measured BEFORE shipping, not after:** folding the queries made `fetch_ledger` inherit `ORDER BY started_at ASC`, and `classify_slot` returns on the first matching row — so its verdict depends on row order, and its old input had no ORDER BY at all. On the real prod ledger (**90,342 rows**): old and new queries return **identical row sets** (0 only-in-old, 0 only-in-new), and across **17,130 permutation probes the verdict changed ZERO times** — 3,148 differed only in the HH:MM inside a `done` detail, which nothing branches on. Also 0 multi-row slots (same job + `scheduled_for`) in 60 days.
- **Three mutations verified RED:** drop the `ORDER BY`, drop `duration_s`, undo the delegation (`tests/test_678_single_job_runs_reader.py`).
⚠ Recorded because it cost two drafts: the column/ORDER BY test was worthless twice and read GREEN both times under mutation — first asserting over `inspect.getsource()` whole (the docstring explains why those two things matter, so it contains both strings), then subtracting `__doc__` from the source text (`__doc__ in source` is False, so the subtraction silently no-opped). It walks the AST and skips the docstring node now.

## #335 — the theme-axis credit is unplugged from the live composite-authority block, and the rail #331 needs is still there (2026-09-21)
BAR: with zero axes registered, a scan produces byte-identical grades to today with the toggle ON *and* OFF, proven by a test that RED-fails if the composer is reached at all; `compute_theme_axis_credit_live` no longer exists; the toggle and composer still do.
EVIDENCE: **All four clauses read GREEN inside the RUNNING container, checked by me directly rather than taken from the review.**
`docker exec apollo-market python -c "...introspect..."` on 2026-09-21 returned:
- `_COMPOSITE_AXIS_CREDIT_SOURCES` → **`[]` (n=0 axes registered)**
- `hasattr(catalyst_rubric_runtime, "compute_theme_axis_credit_live")` → **False** — the retired function is gone. `grep -rn 'def compute_theme_axis_credit_live' /app/agents /app/shared` → **0 hits in BOTH `apollo-market` and `apollo-execution`**; the only textual survivors are two comments naming it as retired.
- `meta_rubric_compose.resolve_composite_tier` / `compose_final_tier` → **both callable** — the rail #331 depends on is intact, which is the other half of the bar.
- `db.get_composite_authority_enabled` → **callable** — the toggle still exists.
- **The test the DoD names: `tests/test_335_composite_axis_retired.py` → 7 passed.** It spies non-raising on `resolve_composite_tier` and asserts `calls == []` with the toggle **True**, with the toggle **False**, and across all three base-decision shapes a real scan can hand in. Its mutation was shown to discriminate: seeding a fake always-fires +1 axis made toggle-ON compose MODERATE→HIGH while OFF stayed MODERATE, and the assertion failed.
- Images were rebuilt today at 12:02/12:05 ET, so the introspection is of the code now serving, not of the repo.
⚠ **DELIBERATELY NOT RESTING ON THE LINE'S LIVE HALF, which cannot discriminate.** Its EXPECT said "zero tier differences and zero composer errors" — but `mi_safeguard_state` has **0 rows matching `composite%`**, so `get_composite_authority_enabled()` fails closed to False and emitted the identical zero BEFORE the change. A broken build produces the same reading. The DoD is closable only because its real observables are code state and a RED-proofed test. [[a-rule-is-not-live-until-it-has-fired-once]]
⚠ **Its verify-date said "Mon 2026-09-22" and 2026-09-22 is a TUESDAY** — the intended "first market day that can produce the reading" was today. Same UTC-roll class already logged in CLAUDE.md on 2026-09-14; waiting a day bought no additional evidence.

## #661 — the EP money path no longer runs through the nightly pass's batch-driver state machine (2026-09-21)
BAR: `judge_theme_fit` no longer calls `_propose_assignment_batch`; the four kwargs are gone from its signature; and a replay of one nightly assignment run produces the byte-identical proposal list and the same audit events as before.
EVIDENCE: **All three clauses, the first two read out of the RUNNING container and the third from a replay with a working sensitivity control.**
- **Clause 1 + 2, live introspection in `apollo-market`:** `'_propose_assignment_batch(' in inspect.getsource(judge_theme_fit)` → **False**, and its signature is **`['ticker', 'description', 'sector', 'themes', 'rs_composite', 'client']`** — the four batch kwargs (`batch_no`, `n_batches`, `batch_size`, `candidate_pool_size`) are gone.
- **Clause 3, `scripts/probes/_661_assignment_seam_replay.py`, old path vs new on identical inputs:**
```
A nightly 3 batches: consult+propose / direct / truncated   13 events   sha b0b75c27381ca2d5  →  0 differing
B nightly 2 batches: silent stop / advisor budget           18 events   sha c970d53b1c0256ac  →  0 differing
C EP-time fit, 6 cases                                      20 events   sha 1ed586d1a51be099  →  0 differing
TOTAL DIFFERING LINES (A+B+C): 0
```
- 🔑 **AND THE ZERO IS NOT A BLIND INSTRUMENT.** The probe carries a SENSITIVITY control — the same replay with the prompt changed by **one byte** — which produces **8 differing lines and a different sha (`9ae8a3becd7d8df9`)**. Without that, three zeros would be indistinguishable from a comparison that cannot see anything. [[a-rule-is-not-live-until-it-has-fired-once]]
- **The live EXPECT held too, both halves on the first market day:** `ep_theme_fit_llm_proposed` fired **4 times today** (first at 08:35 ET) and `assignment_llm_proposed` landed from tonight's nightly at **17:09 ET**, carrying the full key set `advisor_calls, batch_no, batch_size, candidate_pool_size, candidate_tickers, n_batches, proposals`. **Zero `ep_theme_fit_silent_stop` and zero `FIT_FAILED` rows** — the WOULD-FAIL-IF was a `no verdict (consult)` row, and there are none.
## #671 — deal-pinned names really do leave the themes they sit in, and nothing genuine leaves with them (2026-09-21)
BAR: the strip's OWN audit row, not a surviving 1-member theme. `theme_carryforward_filter_stripped` on a nightly theme run names the deal-pinned ticker it removed and the size it took the theme from and to, AND the over-removal control (*Emerging Medical Device Innovators Breakout*) still reads 3 members, AND the run's total theme count is comparable to the prior run.
EVIDENCE: **Monday 2026-09-21's nightly theme run, read positively — six strips, each naming its ticker.**
```
Defensive Consumer Staples Rotation                     16 → 15   ['UTZ']
Inflammatory Disease & Immunology Biologics             12 → 11   ['APGE']
Life Science Tools & Analytical Instruments             14 → 13   ['TECH']
Management & Business Advisory Consulting Firms          2 →  1   ['CBZ']
Peptide & Hormone Therapies for Metabolic & Endocrine     4 →  3   ['CRNX']
Specialty P&C Insurance Underwriters Rotation Reversal  17 → 16   ['SAFT']
```
- **11 `theme_carryforward_filter_stripped` rows tonight, 6 of them `deal_pinned`.** The named case from the task text is there: **CBZ out of the Consulting theme, 2 → 1.** CBZ's pin confirmed independently against the live function — `get_deal_pinned_tickers(2026-09-21, ['CBZ','HURN','IT','ACN'])` returns **`['CBZ']`** and nothing else, so the strip took the pinned name and left HURN alone.
- **The over-removal control is untouched:** *Emerging Medical Device Innovators Breakout* reads **3 members — ITGR, ATEC, INSP** — on 09-17, 09-18 and 09-21 alike.
- **The engine did not crash:** total themes 132 (09-17) → 124 (09-18) → **120 (09-21)**, a comparable run.
⚠ **THE THEME I NAMED DID NOT SURVIVE, AND THAT IS THE STRIP WORKING, NOT FAILING.** Stripped to one member it falls below the member floor and does not persist — so `mi_themes` on 09-21 holds no Consulting row at 1 member. I had written "a row carrying 1 member `{HURN}`" as the success case and "the theme vanishes entirely" as the FAILURE case; they are the same observation. The audit row is what separates them, and it was there the whole time.
⚠ **TWO CONDITIONS BEFORE THIS ONE COULD NOT BE MET, both defects in the condition rather than the code.** The first named Friday 2026-09-18's run, which predates the Saturday 09-19 ship — unfalsifiable in the wrong direction. The second is the 1-member case above. Recorded because the class recurred three times today (#610, #672, this).
