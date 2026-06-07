# Live-cutover readiness scorecard — 2026-06-07 (T-15 to the 6/22 decision)

Grounded, read-only assessment of the four `live_cutover_decision` gates + the hard
P0 blockers. Each marked against **prod evidence** (queried 2026-06-07). Re-run the
queries in this doc to refresh. Markets-closed snapshot; nothing here mutates state.

**Headline:** The infra/safety gates are largely green, but **Gate 3 (paper
R-expectancy) is RED on the literal predicate** — the entire GO case rests on the
#223 SIP-replay reinterpretation. That reinterpretation (hardened by #224) + the
**#151 partial-exit P0** are the two load-bearing items for 6/22. Nothing else is a
surprise blocker.

---

## Gate scorecard

| Gate | Predicate | Prod evidence (6/07) | Verdict |
|---|---|---|---|
| **1 — Drawdown breaker armed** | ACTIVE before cutover | `mi_safeguard_state`: paper state=**REDUCE**, dd −7.7%, **enforcing 0.5×** since 6/3 (#174) | ✅ **GREEN** — armed + verified enforcing |
| **2 — Partial-then-trail verified** | ≥1 paper partial_taken closed, no naked-window | **N=3** partial-then-trail closed paper trades since 5/10 (threshold 1) | 🟡 **GREEN (predicate)** — but reliability still hardening under #151 (see below) |
| **3 — Paper R-expectancy** | ≥10 closed paper, +R | **N=15** (≥10 ✓) BUT **portfolio −0.18R / avg −0.20R / win 33% / −$2,424**. magna53 −0.13R (n=11, 27% win); 9m_day2 −0.33R (n=4, 50%) | 🔴 **RED on raw paper** · 🟡 GO-supportive only via #223 SIP reinterpretation |
| **4 — Dual-account ready** | infra shipped + activatable | Code shipped (#66); all 7 strategies `phase∈{paper,shadow}`, `live_real_enabled=false`, `ENABLE_LIVE_MODE` dormant | 🟡 **READY-dormant** — infra done; activation IS the cutover action |

## Hard P0 blockers (from the 5/27 IBM cascade + RDW)

| # | Item | State | Verdict |
|---|---|---|---|
| #142 | RDW stuck `pending_new` watchdog | completed | ✅ closed |
| **#151** | **Partial-exit hardening** (architectural split + G6 + breaker) | **in_progress**, N=7-clean target **6/15** | 🔴 **HARD BLOCKER** — partial path still being hardened; FPS 6/04-6/05 fragility is fresh evidence |
| #184 | Trade-state broker-SoT mirror (ADR 0008) | in_progress — inc-1 fence shipped 6/6; #225 residuals | 🟡 partial — write-side fence live, 3 residuals open |
| #183 | ORB cancellation classifier (IEX/SIP mislabel) | in_progress | 🟡 feeds Gate-3 accuracy |

---

## The crux: Gate 3 is the whole game

The literal R-expectancy gate is **negative** (−0.18R portfolio, 33% win, both
strategies red). The GO case rests **entirely** on the #223 finding that the paper
negative is an **IEX execution-feed artifact** (paper fills off IEX, misses the
clean fast breakouts; SIP-reconstructed same-exit cross-check = synth-CANCELLED
+1.27R vs synth-FILLED −1.00R → **+2.27R selection delta**, GO-supportive for
reduced size). See `docs/analysis/sip_replay_gate3_2026-06-06.md`.

**Implication:** going live 6/22 means betting real money on a *reinterpretation* of
negative paper results, not on positive paper results. That is defensible (the IEX
mechanism is real and confirmed) but **thin** — it is the single highest-leverage
thing to harden before the decision. → **#224 SIP-replay robustness checks** was the
top cutover-prep item.

**#224 hardening done (2026-06-07)** — see `sip_replay_gate3_2026-06-06.md` §"#224
robustness hardening". Two checks, folded into the durable script's default output (re-run
monthly): (1) **trim curve** — standalone synth-CANCELLED +1.27R survives dropping the top
3 names (+0.097R) and crosses 0 at the 4th → **real but concentrated**; (2) **winner fill-
realism** — 6/6 edge-carrying names are convincing SIP fills (0.60–2.61% penetration through
the limit), zero grazes. Net: the GO *direction* holds (selection is real, winners are
genuine fills); the *sizing* read sharpens to **START-SMALL, not full-size** — the standalone
edge leans on ~3–4 winners of 14. Operator owns the GO/size call. Bootstrap-CI demoted
(false precision at N=14 bimodal); recent-window redundant (cohort already within 90d).
**Scope: this hardening is `magna53`-only.** 9m_day2 is also Gate-3 RED (N=4, −0.33R) and is
NOT covered by this SIP evidence — if 9m_day2 is in the 6/22 flip it needs its own cohort
(too thin today). The magna53-only verdict must not be read as clearing both strategies.

## What to attack in the 15 days (priority order)

1. ~~**#224 — harden the Gate-3 SIP verdict**~~ ✅ **DONE 2026-06-07** (trim curve + winner
   fill-realism; verdict sharpened to START-SMALL). Now the load-bearing item is closing the
   *reliability* gates below — the *edge* question is as resolved as the proxy allows.
2. **#151 — close the partial-exit P0** (hard blocker; 6/15 target). The FPS 6/04-6/05 fragility is live evidence it's not done.
3. **#184/#225 — finish the trade-state mirror residuals** (3 demotion-fence residuals).
4. **Gate 4 activation runbook** — the flip itself (ENABLE_LIVE_MODE + magna53→phase=live, reduced size). Infra is ready; needs the operator go-procedure written.

## What is NOT a blocker (verified green / handled)
Drawdown breaker (Gate 1, enforcing) · dual-account infra (Gate 4 code) · PDT
retired (#181) · DR layer · RDW watchdog (#142) · the 8-gate deploy gauntlet.

---
*Re-run: the four predicate queries live in `data_gated_reviews.yaml`
(`drawdown_breaker_promotion` / `ftre_partial_trail_verification` /
`paper_r_expectancy_validation` / `dual_account_architecture_ready`). Refresh this
doc weekly until 6/22.*
