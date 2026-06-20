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

**The HARD #344 catalyst gate is now operator-RESOLVED (2026-06-19): "shadow plus Monday flip
is good."** The operator labeled BFLY a real EP / `routine` WRONG, then accepted that the
corpus-completeness fix shipping as a **premarket shadow now + the live flip after the shadow
validates (#347)** SATISFIES the gate — the live flip need not have landed before GO. **PRECISE
TIMELINE (operator CONFIRMED 6/19 "that's fine"):** #347 needs ~2 shadow days (Mon 6/22 + Tue
6/23) → the flip lands **Wed 6/24 earliest**, gated on CHANGE_PROCESS + sign-off. So if GO is
Monday, **real money trades Mon–Wed on the PRE-fix grade — BFLY-class names won't fire live
until the flip** — operator accepts this. This remains **conditional on Monday's shadow verify
(#346) being clean** (a bad shadow read is a NO-GO trigger).

**#349 (DR rehearsal): operator decided NOT to gate GO on it** — the split-topology rehearsal
runs in the next couple of days (operator-triggered), separately from the 6/22 GO.

So the remaining GO/NO-GO inputs are **Monday's mechanical verifies + your START-SMALL sizing**
(§5/§6), not open catalyst/DR questions.

---

## 1. Gate composite

| Gate | State | Evidence |
|---|---|---|
| **P0 — orb_entry_stuck_pending_new** | ✅ CLEARED | Closed 5/28 (APScheduler 10:00 misfire + watchdog); 0 post-fix recurrences. Predicate floored at the fix date so it can't false-block the cutover (#291). |
| **P0 — alpaca_stop_trigger_reliability** | ✅ NOT A BLOCKER | Downgraded P0→P2 6/03; mechanism = #182 paper-IEX entry-side miss; re-escalate only on an exit-side activation failure (none observed). |
| **GATE 2 — partial-trail race** | ✅ VERIFIED + RATIFIED | RCAT 6/01 root-caused = the fix working (transient APIError → correct abort, broker stayed covered, 0 naked exposure). Operator RATIFIED green 6/19 (#291). |
| **GATE 3 — paper R expectancy** | ✅ GO-SUPPORTIVE (reduced-size) | **Load-bearing fact, from PRIMARY output `sip_replay_r_cohort.py` re-run 6/19 (read-only, no LLM):** the selection delta. IEX adversely selects — a clean breakout runs away from the stop-limit, never fills on IEX's thin book → lands in the *cancelled* set; a weak breakout pulls back, fills, then dies → lands in the *filled* set. Re-scored under one identical floor-proxy exit: **synth-FILLED −1.00R** vs **synth-CANCELLED +1.183R** (N=15, totR +17.74, win 6/15) = **+2.18R selection delta**; gap_through=0 (100% reachable), 6/6 winners convincing fills. **Concentration (re-run):** drop-top-1 +0.748, drop-top-2 +0.417, drop-top-3 **+0.087**, drop-top-4 **−0.291 (crosses 0)** → edge survives drop-3 but barely → **START-SMALL**. **$-baseline (re-run):** raw paper-IEX ≈ **−$9,475**. — *Carried from #291 (not this re-run, distinct cohorts):* raw paper-IEX **closed-trade** cohort N=21 = −5.64R/33%; SIP **REAL-only** cohort N=23, E[R] −0.45. The 21-vs-23 gap is unreconciled here (likely 2 real-placed-but-IEX-cancelled orders the SIP-real set retains but the closed-trade count drops — NOT verified); they are NOT the same set repriced. (memory `project_gate3_sip_selection_finding`, `paper_iex_vs_live_sip_gate_adjustment`.) |
| **gate5 — adel deliverables** | ✅ COMPLETE | All code shipped+verified (naked-position remediation, stuck-fill watchdog, schema-type regression gate, Gate 5 G deploy gate). Operator SIGNED the gate5-F IBM 5/27 post-mortem 6/19 (#291). |
| **#344 — catalyst correctness** | ✅ OPERATOR-RESOLVED 6/19 (conditional on Mon verify) | **Operator call 2026-06-19: "shadow plus Monday flip is good"** — shadow-now + the live flip (#347) SATISFIES the HARD catalyst gate; the live flip need not have landed pre-GO. ⚠ Precise timeline: the flip is **Wed 6/24 earliest** (~2 shadow days Mon+Tue → CHANGE_PROCESS + sign-off), so Mon–Wed real money runs the pre-fix grade (BFLY-class names don't fire live until the flip). Background: cache-staleness was replay-cleared as non-blocking; the operator then labeled BFLY a real EP / `routine` WRONG, re-pointing the gate onto catalyst-CORRECTNESS; the corpus-completeness fix shipped as a premarket shadow (`ep_grade_enrich_shadow`), live grade byte-identical until the flip. **Still conditional on Monday's clean shadow verify (#346)** — a bad shadow read flips this back to a NO-GO trigger — and does NOT waive the #347 CHANGE_PROCESS + sign-off on the flip itself. Doc `late_source_replay_344_2026-06-19.md`. |
| **#345 — global real-money PAUSE (panic button)** | ✅ DONE + VERIFIED-LIVE 6/19 | `/pause`/`/resume` (fail-SAFE, highest-priority gate + a 2nd gate at the submit chokepoint + resting-order cancel). Cross-service verified live 6/19; full real-money exercise only possible once ENABLE_LIVE_MODE=true at go-live. |
| **#275 — kill/scale bands** | ✅ SHIPPED 6/19 | Evaluator (12 boundary tests prove silence through the healthy year) + daily 16:13 transition alert + weekly digest + override. Verifies-live as trades accrue post-launch. |
| **#349 — DR restore (split topology)** | 🟢 NOT GATING GO (operator 6/19) · rehearsal next couple days | Found 6/19: restore.sh brought up no execution + aborted on the creds-preflight. Fixed (execution-first → both) + operator-signed. **Operator decided NOT to gate the 6/22 GO on the rehearsal** — it runs in the next couple of days (operator-triggered), separately. Fix is verified-from-code; the live split-topology drill is the remaining confirmation. |

**Implementation verification (code-verified 6/19, #303 readiness audit — claims above traced to source, not prose):**
the safeguard implementations the GO relies on are present in the code that fires on a real entry —
- Panic button: highest-priority gate in `_check_safeguards` (`live_tracker.py:105`, before any other guard) + 2nd gate at the submit chokepoint (`order_manager.py:186`); both fail-SAFE (unreadable→block, distinct `infra:halt_state_unreadable`).
- Day-1 equity guards all in `_check_safeguards`: `LIVE_TRADING_ENABLED` master kill (`live_tracker.py:92`), daily-loss (`:191`), 5-loss circuit breaker (`:220`), tiered drawdown breaker (`:240`, multiplier→0 blocks).
- Creds boot-block incl. the 2026-05-13 outage class: `phase=live` under `ENABLE_LIVE_MODE=false` → BOOT BLOCKED (`agent.py:7037+`).
- Kill/scale band job registered 16:13 ET mon-fri, `INTELLIGENCE_OWNED`, enforced by the unclassified-job boot guard (`scheduler.py:185,4434`).
- #349 DR fix in place: `restore.sh:383` runs `deploy.sh execution` **then** `deploy.sh both`.
- Monday verify scripts all present (`_344_shadow_verify.py`, `evaluate_kill_scale_bands.py`, `set_kill_scale_override.py`).

No new gaps surfaced; the audit re-confirmed the gate composite is code-backed (the same audit class that caught #349).

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

1. **#344 — RESOLVED by you (shadow + Monday flip), no longer open.** BFLY-class names won't fire live until the Mon/Tue flip (#347), which you accepted. The only live residual: Monday's shadow verify (#346) must read clean — if it doesn't, this reverts to a NO-GO trigger.
2. **#349 — you decided NOT to gate GO on the rehearsal** (running it in the next couple days). The residual you accepted: a host failure in week 1 before the rehearsal would exercise a recovery path verified-from-code but not yet drilled end-to-end.
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

NO-GO under the signed rules is **launch-complete**, not failure. With #344 and #349 resolved
by the operator (6/19), the remaining triggers to NOT go live 6/22: **Monday's #346 shadow
verify reads dirty** (shadow rows didn't write / re-poll thrash / scan wall-time regressed —
this was the explicit condition on the #344 resolution); any other gate flips red on Monday's
verify (#275 16:13 job fires; #325 theme run); or the START-SMALL sizing isn't set. NO-GO →
keep paper, re-evaluate at the next review trigger; nothing is lost.

---

### Monday 6/22 checklist (the only things that must happen live)
- [ ] `_344_shadow_verify.py` — shadow rows wrote premarket, re-poll fired once, scan wall-time unchanged (#346)
- [ ] #275 16:13 band job fires clean + Sunday digest rendered the band section
- [ ] #325 theme run (~17:00 ET) — first valid test of the discovery fix (read `new_raw_llm`)
- [ ] GO/NO-GO decision (#305) — with this pack in hand
- [ ] If GO: the staged config+deploy in §5, panic button confirmed, START-SMALL size set
