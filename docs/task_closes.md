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
