# Long-Weekend Sprint — 2026-07-03 (Fri, market closed) → 07-05 (Sun)

**Set 2026-06-30 (operator).** Two goals: **(1) key progress across projects** · **(2) reduce open tasks (net-down).**
Aggressive by design — 3 market-closed days + parallel agents. **THE LINE holds:** everything here is
shadow / advisory / no-money OR a careful gated change; **no live grade-flip, no un-exercised trade-state
change on this weekend's authority.**

**HEADLINE (operator priority 6/30): push the EP launch project to near-closure.**

---

## Track 1 — EP launch project push (the two launch-named projects, ~13 tasks → target ~7–8)

**Close (the doable):**
- **#303** — run the DR-restore rehearsal (markets closed = the safe window) → close.
- **#364** — remove the dead staged-proposal buttons (never worked; Phase-2 auto-enters). ⚠ OPERATOR-CALL (confirm remove).
- **#261** — finish the scripts ops/evals reorg (careful — touches deploy.sh) → close.

**Unblock + advance (conditions now appear met — CONFIRM first):**
- **#299** — was "blocked on funding"; funding settled at the 6/28 arm → unblock + build the P2 tape-features.
- **#301** — was "deferred to post-cutover"; the cutover happened → start the ensemble-divergence SHADOW.

**Hardening — CAREFUL (trade-state-adjacent; advisor + a paper-Alpaca exercise, NOT auto-grind):**
- **#184** (trade-state mirror increments) · **#225** (demotion residuals) · **#183** (ORB classifier). Advance;
  close #225 if the residuals resolve clean. The closed-market window is ideal, but these get the careful path.

**Builds (advance):** #398 (theme-lookup dashboard half) · #255 (judge precedent-retrieval).

**Can't force:** #150 (sell-retry — closes only on the next share-reservation event) · #316 (PDT/4210 — gated on
Alpaca's external rollout; check status, re-gate or relax).

**⚠ OPERATOR-CALL to settle at kickoff — #305 (the launch task itself):** currently "stays open until the first
real FILL." The arm-mechanic IS verified-live (AVAV 6/30). Option A: close on "launch executed + entry-path
verified-live" + spin the first-fill into a standalone watch. Option B: hold until a fill lands. **Operator's
decision — real-money launch task, not the agent's.**

## Track 2 — North Star (Judge & catalyst): go deep, not just a spec
- **#328 theme-axis = DESIGN *and* build the shadow scoring** (a live shadow eval, not a doc) + kick off the
  catalyst-sourcing backbone (**#210/#211**, direct primary sources). Safe — all shadow/advisory; the live grade
  flip stays gated (CHANGE_PROCESS + N≥10 + sign-off — never on this weekend's authority).

## Track 3 — Grade-path debt (Operational safety): clear it on the closed-market window
- **#405** (EP catalyst-cache re-grade refactor) + **#406** (alpaca alert label) — deploy 7/3 + verify. #405 gated
  on the "filtered-ticker-never-enters" test (advisor-designed).

## Track 4 — Aggressive burndown sweep (target ~15–20 net-down, 108 → ~90)
- Systematic, not cherry-picked. Fan out parallel agents (a burndown WORKFLOW — one agent per task → verify →
  close or re-date with a reason) over: the deploy-gated (**#342** eval-CSVs, **#279** /simplify dedup), the
  verify-live tail, the dedups, the /simplify cleanups (**#404, #407**), + the 2 VIX follow-ups (regime.py:485
  stale comment · the offline backtester historical_scan.py:208 I:VIX call).
- Batch ALL the deploy-gated closes onto the 7/3 window (one safe deploy pass).

## Track 5 — Apollo v1.1 fast-follow: open the lane
- Start the post-launch v1.1 program (spec PART I, apollo-v1.1-v2.0.md).

## Track 6 — Triage the 23 overdue data-gated reviews (the single biggest burndown lever)
The data-gated review board has **23 ready/overdue reviews** (surfaced 6/30). Each: run it → CLOSE (evidence
resolves it) OR convert to ONE gated #-task — both shrink the open/overdue surface. Route via `/datareviews`.

**⭐ Flagged by the 2026-07-01 monthly backward-check sweep — DO THESE WITH THE OPERATOR** (evidence attached;
all already tracked → no new tasks). The sweep is re-runnable for full detail:
`docker exec apollo-market python -m agents.market_intelligence.quarterly_review`. Decision-relevant signals:
1. **M&A filter over-suppression** → `mna_filter_accuracy_review` + **#410** (buyout-pin guard). The filter
   SUPPRESSED **SUNE → +216%** (also FRMI +25%, ONDS +23%, MMED +23% on the material-miss list; n=48 suppressed).
   Operator FP/TP call — hard-gate #3/#4 bars the agent from classifying. (78% of `mna_filter_fired` events
   matched on the "unknown" path — a data-quality angle for `mna_filter_direction_blindness`.)
2. **Judge demoting winners** → the **#335/#329 grade-quality cluster** (~7/3) + the monthly judge review. 5
   unjustified demotes: **HQ HIGH→MODERATE then +152%**, JBIO MOD→none +20.8%, XE +13.5%, AEHR HIGH→MOD +7.5%,
   AUGO +7.3%. Root-cause candidate = **direct-source blindness: 79% of assessable rows had a DIRECT source the
   judge was shown 'no' for** (the #329→#335 fix). Verdict = operator `/why`-labeling of the demotes + top promotes.
3. **#92 flag-EOD graduation = STRUCTURAL NO-GO** → `flag_detector_post_breakout_label`. The sweep's own verdict:
   EOD "TRIGGERED" is a post-hoc measurement, not an entry (the move already played out). **Candidate CLOSE** —
   evidence resolves it (consistent with HTF Phase-3 riding the #94 intraday break, not the EOD scan).

**Band datapoints to carry into the methodology reviews (context, not fire-now):** #77 Pradeep — the +40%+
"extended" band UNDERperforms (-0.70%, 31% win) while +20-40% leads (+7.40%, 51%) → supports the extension-block
direction · #53 gap/ATR — 2-3x best (43% win), <1.5x worst (29%, -5.2%) → `gap_atr_3_5x_band` · #78 decliner —
shallow (-5/-10%) + STRONG catalyst bounces +6.6%/55%, deep (-20%+) craters -17% · #54 9M stop/ATR — 66 cand /
8 entered / 12 stop_too_wide (RMV #54, data-ready) · #55 revenue-pin HELD (data re-confirms 0.01) · news-quality
no-drift · #122 & #197 accruing (N<10).
- **FIRST-UP:** `alpaca_stop_trigger_reliability` — a paper stop silently failed despite a SIP-confirmed
  cross (real-money-safety; MITIGATED by the never-naked backstop [sync_positions remediates ≤15 min] so NOT
  fire-now — but investigate the root cause). NB: registry severity is **P2** (operator-ratified 6/03 — these
  are entry-side fill-rate events, not exit-side stop failures; this doc said "P0" until the 7/2 review caught it).
- **Cutover gates (overlap Track 1):** `drawdown_breaker_promotion` (GATE 1 of live cutover, 22≥14) ·
  `paper_r_expectancy_validation` (GATE 3, 23≥10) · `unified_allocator_phase_1b` (#44 promotion, 21≥15).
- **Detection / methodology (overlap North Star + Family A):** flag_proximity_band_calibration ·
  flag_ma_pin_filter · flag_proximity_bypass_hysteresis · flag_detector_post_breakout_label ·
  ep_cooldown_resetup_admission · rel_volume_large_cap_floor · theme_engine_narrative_blindness · fishhook_v3 ·
  p74_alpha_capture_stage2 · gap_atr_3_5x_band · nbis_rubric_calibration · mna_filter_direction_blindness ·
  gate5h_value_invariant · silent_failure_taxonomy · adv_probe_retirement · extraction_pipeline_smoke ·
  breadth_cluster_view · perplexity_sanitizer · trade_stream_stop_placement.

---

## Sequencing
- **7/3 (Fri, market closed):** batch ALL deploys on the one safe window — #405 + #406 + #342 + #279 +
  the monthly-sweep 08:00→18:00 ET cron move (committed 7/1) + any launch-project close needing a deploy.
  Deploy + verify once (incl. confirming the `monthly_backward_check_sweep` job registers at 18:00 ET).
- **7/4–7/5:** the North-Star #328 build (deep-focus) + the launch-project push + the burndown workflow +
  the v1.1 kickoff.

## Targets
EP launch project 13 → ~7–8 · North Star shadow LIVE · grade-path debt cleared · count down ~15–20 · v1.1 opened.

## Safety (THE LINE)
All shadow/advisory/no-money OR careful-gated. Live grade-flips + trade-state changes stay gated
(CHANGE_PROCESS + sign-off + paper-Alpaca exercise). Two operator-calls open: **#305** close-criterion ·
**#364** remove-buttons.
