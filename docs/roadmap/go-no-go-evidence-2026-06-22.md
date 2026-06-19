# 6/22 GO/NO-GO — evidence pack (#304)

**Purpose:** one place to make the real-money MAGNA53 go-live decision (#305) with every
gate, the economics, and the signed rules in view. **This pack SURFACES the evidence; it
does not make the call.** Under the signed rules, **NO-GO is a complete, valid outcome** —
the launch DoD is "decided on evidence," not "went live."

Assembled 2026-06-19 (pre-launch). Sources cited inline; the umbrella SoT is
`docs/roadmap/launch-2026-06-22.md`, the gate triage is #291, the economics are #268 Phase B.

---

## Bottom line (evidence state, not a decision)

**The mechanical gates (P0s, GATE 2, gate5, #345 panic button) are cleared/verified; the
economics gate (GATE 3) is GO-supportive at START-SMALL size.** The edge is real but
**selection-concentrated** (drop the top 3 winners and the SIP cohort barely clears 0; it
crosses below at drop-4) → the evidence supports **reduced-size GO**, not full size.

**The one gate this pack does NOT and CANNOT resolve is the operator's HARD #344 catalyst
gate.** On 6/19 the operator labeled BFLY a real EP and called the `routine` grade WRONG —
that re-pointed the gate from "build the cache fix" onto catalyst-CORRECTNESS. The
corpus-completeness fix shipped 6/19 as a **premarket shadow**; the live grade is unchanged
until the Monday/Tuesday flip (#347, gated on shadow net-correctness + CHANGE_PROCESS +
operator sign-off). **The open operator question for GO: does shadow-now + a Monday/Tuesday
flip satisfy your HARD catalyst gate, or do you require the live grade flip to have landed
before GO?** Per the HARD-gate rule (CLAUDE.md), only the operator can call that gate
satisfied — this pack will not.

One more item is *applied-but-unconfirmed* and should be weighed: the #349 DR fix (applied,
not yet rehearsed on the split topology).

---

## 1. Gate composite

| Gate | State | Evidence |
|---|---|---|
| **P0 — orb_entry_stuck_pending_new** | ✅ CLEARED | Closed 5/28 (APScheduler 10:00 misfire + watchdog); 0 post-fix recurrences. Predicate floored at the fix date so it can't false-block the cutover (#291). |
| **P0 — alpaca_stop_trigger_reliability** | ✅ NOT A BLOCKER | Downgraded P0→P2 6/03; mechanism = #182 paper-IEX entry-side miss; re-escalate only on an exit-side activation failure (none observed). |
| **GATE 2 — partial-trail race** | ✅ VERIFIED + RATIFIED | RCAT 6/01 root-caused = the fix working (transient APIError → correct abort, broker stayed covered, 0 naked exposure). Operator RATIFIED green 6/19 (#291). |
| **GATE 3 — paper R expectancy** | ✅ GO-SUPPORTIVE (reduced-size) | **Load-bearing fact, from PRIMARY output `sip_replay_r_cohort.py` re-run 6/19 (read-only, no LLM):** the selection delta. IEX adversely selects — a clean breakout runs away from the stop-limit, never fills on IEX's thin book → lands in the *cancelled* set; a weak breakout pulls back, fills, then dies → lands in the *filled* set. Re-scored under one identical floor-proxy exit: **synth-FILLED −1.00R** vs **synth-CANCELLED +1.183R** (N=15, totR +17.74, win 6/15) = **+2.18R selection delta**; gap_through=0 (100% reachable), 6/6 winners convincing fills. **Concentration (re-run):** drop-top-1 +0.748, drop-top-2 +0.417, drop-top-3 **+0.087**, drop-top-4 **−0.291 (crosses 0)** → edge survives drop-3 but barely → **START-SMALL**. **$-baseline (re-run):** raw paper-IEX ≈ **−$9,475**. — *Carried from #291 (not this re-run, distinct cohorts):* raw paper-IEX **closed-trade** cohort N=21 = −5.64R/33%; SIP **REAL-only** cohort N=23, E[R] −0.45. The 21-vs-23 gap is unreconciled here (likely 2 real-placed-but-IEX-cancelled orders the SIP-real set retains but the closed-trade count drops — NOT verified); they are NOT the same set repriced. (memory `project_gate3_sip_selection_finding`, `paper_iex_vs_live_sip_gate_adjustment`.) |
| **gate5 — adel deliverables** | ✅ COMPLETE | All code shipped+verified (naked-position remediation, stuck-fill watchdog, schema-type regression gate, Gate 5 G deploy gate). Operator SIGNED the gate5-F IBM 5/27 post-mortem 6/19 (#291). |
| **#344 — catalyst correctness** | 🔴 HARD GATE — operator's open call | **Operator-owned, not agent-resolvable.** Cache-staleness itself is replay-cleared as non-blocking (funnel 21 web-only grades → 2 in-window sources → 0 re-graded higher → 0 new fires; doc `late_source_replay_344_2026-06-19.md`). BUT on 6/19 the operator labeled **BFLY a real EP and `routine` WRONG** — re-pointing the gate onto catalyst-CORRECTNESS. The corpus-completeness fix shipped 6/19 as a **premarket shadow** (`ep_grade_enrich_shadow`); **the live grade is byte-identical to before until the flip** (#346 Mon verify → #347 flip, gated on shadow net-correctness + CHANGE_PROCESS + operator sign-off). **OPEN OPERATOR QUESTION for GO: is the gate satisfied by shadow-now + the Monday/Tuesday flip, or did you require the live grade flip to have landed before GO?** The agent will not classify this gate satisfied (HARD-gate rule). |
| **#345 — global real-money PAUSE (panic button)** | ✅ DONE + VERIFIED-LIVE 6/19 | `/pause`/`/resume` (fail-SAFE, highest-priority gate + a 2nd gate at the submit chokepoint + resting-order cancel). Cross-service verified live 6/19; full real-money exercise only possible once ENABLE_LIVE_MODE=true at go-live. |
| **#275 — kill/scale bands** | ✅ SHIPPED 6/19 | Evaluator (12 boundary tests prove silence through the healthy year) + daily 16:13 transition alert + weekly digest + override. Verifies-live as trades accrue post-launch. |
| **#349 — DR restore (split topology)** | 🟡 FIX APPLIED · rehearsal pending | Found 6/19: restore.sh brought up no execution + aborted on the creds-preflight. Fixed (execution-first → both) + operator-signed. **Not yet rehearsed on the split topology** — the pre-split 5/25 drill doesn't cover it. Live rehearsal is operator-triggered. |

---

## 2. Economics — the envelope the GO is sized within (#268 Phase B)

12-month selection replay, judge-HIGH cohort (n=399, 2025-06-09→2026-05-04;
`docs/analysis/selection_replay_268_phaseB.md`):

- expectancy **+0.95R/trade**, win rate **30%**
- max R-drawdown **−24.1R**, worst losing streak **15**
- trailing-20 expectancy: p5 **−0.63R**, min **−1.03R**, **25% of windows negative**
- monthly expectancy −0.64R → +2.71R (**4 of 12 months negative**)
- 62% full −1R stops; the edge lives in the **13% of trades ≥ +3R**

**Read:** a *healthy* year of this strategy contains a 15-loss streak, a −24R drawdown, and
whole quarters of negative trailing-20 windows. The kill/scale bands are set OUTSIDE that
envelope so they never fire on normal variance. Sizing must survive that drawdown.

---

## 3. Signed criteria (#268b — operator-signed 2026-06-12, `safeguards.md`)

Pre-committed kill/scale bands (decision triggers, not mechanical blocks):

- **SCALE UP**: ≥40 trades AND trailing-40 ≥ +0.5R AND equity > start → raise risk one notch (operator-confirm).
- **REDUCE**: trailing-20 ≤ −0.70R OR streak ≥ 16 → halve risk.
- **KILL → paper**: trailing-20 ≤ −1.05R OR cumulative ≤ −30R OR drawdown BLOCK (−12% equity).
- **Floor**: no expectancy/streak band before 20 closed trades; equity guards (2% daily-loss, tiered drawdown breaker) bind from day 1.

**START-SMALL**: GATE 3 says the edge is real but concentrated → cutover at **reduced size**
(0.25% risk/trade likely), `position_size_multiplier` + `max_concurrent_positions` available
to dial it (#65). At 0.25%, the R-bands bind before the equity bands (strategy health leads).

---

## 4. Residual risks — open at the moment of GO (weigh explicitly)

1. **#344 is your HARD gate, and the flip is Monday/Tuesday, not now.** The live grade is unchanged until the flip, so the question is whether GO can ride on the shadow + a deferred flip. You labeled BFLY a real EP and called `routine` wrong — BFLY-class names will NOT fire live until the shadow validates + you sign off (#347). **This is the call only you can make: does shadow-now + the Monday/Tuesday flip satisfy the gate, or did you require the live flip pre-GO?**
2. **#349 DR fix is applied but unrehearsed** on the split topology. A host failure in week 1 would exercise an un-drilled recovery path (the fix is verified-from-code, but not end-to-end). Your call whether to gate GO on the rehearsal.
3. **SIP vs IEX is a reconstruction, not live SIP.** The +2.18R selection delta is decision-grade *direction*, not a pinned live E[R]; paper fills are still IEX-priced. First live fills are the real confirmation.
4. **Edge concentration.** Drop-top-3 survives, crosses 0 at drop-4 → START-SMALL is doing real work; full size is not yet earned.

---

## 5. What GO means mechanically (it is NOT a switch)

Current state confirmed 6/19: `magna53 phase=paper · live_real_enabled=f · multiplier 1.0 ·
cap NULL · ENABLE_LIVE_MODE=false` (the live Alpaca account is not yet wired). So go-live is a
**deliberate staged config + deploy**, not a toggle the GO decision throws:

1. Wire `ALPACA_LIVE_API_KEY/SECRET` + set `ENABLE_LIVE_MODE=true` (boot-blocks if creds missing).
2. `magna53` → `phase=live`, `live_real_enabled=true`, `position_size_multiplier` to the START-SMALL value, `max_concurrent_positions` cap.
3. Deploy (`deploy.sh both` + `deploy.sh execution`) + preflight green + `verify_dual_account_clients`.
4. Confirm `/pause` is live (the panic button) before the first ORB window.

**Reversion:** `/pause` (instant, runtime) · `LIVE_TRADING_ENABLED=false` (boot kill switch) ·
`phase=paper` (per-strategy).

---

## 6. NO-GO path

NO-GO under the signed rules is **launch-complete**, not failure. Triggers to NOT go live
6/22: **the operator rules the HARD #344 catalyst gate unsatisfied by shadow-now + a deferred
flip** (the headline open call); any gate flips red on Monday's verify (#346 #344 shadow wrote
/ re-poll clean; #275 16:13 job fires; scan wall-time unchanged); the operator isn't satisfied
with the residual risks above; or the START-SMALL sizing isn't set. NO-GO → keep paper,
re-evaluate at the next review trigger; nothing is lost.

---

### Monday 6/22 checklist (the only things that must happen live)
- [ ] `_344_shadow_verify.py` — shadow rows wrote premarket, re-poll fired once, scan wall-time unchanged (#346)
- [ ] #275 16:13 band job fires clean + Sunday digest rendered the band section
- [ ] #325 theme run (~17:00 ET) — first valid test of the discovery fix (read `new_raw_llm`)
- [ ] GO/NO-GO decision (#305) — with this pack in hand
- [ ] If GO: the staged config+deploy in §5, panic button confirmed, START-SMALL size set
