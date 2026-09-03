# #545 — Entry/Exit Tactics Program, v2: the inventory, the grid, the harness map, the sequenced plan (2026-09-02)

**Status: DESIGN ONLY — no code changed, no threshold moved, nothing flipped, nothing deployed.**
**Supersedes** `docs/design/545_entry_exit_program_2026-08-07.md` (v1). v1's inventory is cited by
section below and not re-derived; this document carries what changed in the 26 days since, the
consolidated grid, the harness reconciliation, and the plan the operator sequences.

⚖ **THE LINE.** Every variant here is entry / exit / stop / sizing discipline = strategy = the
operator's SOLE authority. This produces EVIDENCE and a RANKED RECOMMENDATION and flips nothing.
Every live change is CHANGE_PROCESS + the #151 harness + operator sign-off. Nothing below says
"we have decided". Where a fork exists it is stated as his.

**The operator's framing (the yardstick for everything below), verbatim:**
- 2026-08-07: *"EP stocks is a winning cohort overall (not high win rate, but major winners can be
  found here) however, entry/exit tactics is the big challenge… I want to run multiple variations
  of all the parameters including some more novel approaches like re-enter next day, which is
  similar to delayed EP, or even next few days when some delayed setup hits."*
- 2026-09-01: *"we are not building a prediction engine here, we are building a trading system
  that can be risk managed, we find entries and exits where we can manage risk properly and where
  we have positive expected returns."*
- The thesis: **a low-win-rate / fat-right-tail population is one you HARVEST, not one you filter
  harder** — the leverage is in WHEN you enter and HOW you hold, not in tightening what qualifies.

**Acting-rules source:** `python scripts/live_rules.py --drift-only`, run 2026-09-02 12:18 PDT —
**0 drift findings**, prod reachable at server checkout `20b6ff70`. Live today: ORB 1-min stop-limit
entry · stop `entry − 2R` at half size (08-16) · +2R partial (1/3) via resting limit with breakeven
at the broker (08-10) · seeded SMA10/20 close-below trail · same-day re-entry OFF (R3) · giveback
peak-lock OFF by operator ruling (08-11).
**Harness validity:** `python scripts/ep_replay.py validate` run 2026-09-02 → **PASS** (stop formula
44/44 · entry decision 33/33 · exit class 29/30 · realized R within 0.25R on 25/30 — all floors met).

---

## 0. The decision this serves, and what would change it

1. **Decision:** which entry/exit variants are worth the operator's next sequencing decision, in
   what order, at what cost — and which are already answered so nobody re-runs them.
2. **What would change it:** a cell that is positive at n ≥ 30, holds with May excluded, and is
   produced by a harness that reproduces real fills, moves to a CHANGE_PROCESS candidate; a cell
   that fails those three stays "one-cohort read" no matter how large its number.
3. **Population:** §2 — every number below names its rows and window; no number is pooled across
   the 08-01 / 08-16 exit-rule boundaries.
4. **What would make this document wrong:** (a) a stored number quoted from a document whose
   population was since corrected — §8 lists the ones this card found; (b) an MFE column read as a
   return; (c) a re-entry figure whose "winner" is a session HIGH, not a close (every post-stop
   figure in §3.5 is); (d) a regime split quoted from memory — §2 re-derives it from the 09-01
   capture and labels the join.

---

## 1. What changed between v1 (08-07) and v2 (09-02) — the delta in one table

| v1 said | what happened since | consequence for the grid |
|---|---|---|
| "next-day / N-day re-entry: NEVER-RUN, the biggest open cell" | **Run 08-07 (n=15) and 08-09 (full 17)** — 13 same-day/next-day variants incl. the 5-min-range-clear, base-then-turn proxies and the 620 family (`scripts/probes/_545_reentry_sweep_output.txt`). Then the whole day-2+ family was rebuilt as the delayed-entry lane and replayed over **267 caught EPs / 602 fires** (09-01) | the cell is no longer open; it is a one-cohort read on live stop-outs (THC-carried) and a load-bearing recall result on 267 EPs (§3.5) |
| stop basis "REFUTED, every widening" | **Operator signed `entry − 2R` at half size 08-16** (LIVE; 43 matched reconstructed trades: −6.0R → +11.4R at equal dollar risk); on the day-2+ rungs the 09-01 stop grid found **one shape: the working stop is volatility-proportional (0.75–1.25×ADR), not structural** | the day-1 refutations were of the ORB-low FRAME (target moved with the stop). With the target pinned (08-16), the ADR-floor question is open again on day 1 — §4 Axis 2 |
| "+2R partial: cost side unpriced (no live winners)" | **First live winners 08-24:** PLTR — the rule cost **$19.57 = 0.57R = 15% of the trade** as designed; ETON banked +2R off 21 cents of headroom. `ep_backtest` run 1 (n=194, today's rules): **82 of 106 partial-takers round-trip to breakeven at exactly +0.33R** | the harvest leak is now measured twice: the breakeven scratch (n=194) and the partial toll (n=1 live) |
| "giveback peak-lock BUILT-DARK, awaiting fork" | **Operator RULED IT OUT 08-11: *"no, we let winners run"*** | closed by ruling — never re-propose on a reached-vs-kept table |
| "regime: ZERO bull live trades" | stale the day it was written (3 Bull on 08-07). **08-22 stamped split n=22: Bull 7 / Choppy 7 / Correcting 7 / Crisis 1.** 09-01 capture (date-join): 14 of 26 closed live in Bull | the confound moved from paper-vs-live to **ERA**: every Bull close ran the post-08-05 stack, every non-Bull close (bar SOLS 08-28) ran the bare ORB-low stop — §4 Axis 6 |
| "reuse the three probes, do not mint a fourth" | **Ten replay lineages now exist** (§5); the strongest, `scripts/ep_replay.py`, was built 09-01 with live code paths, era matching and a self-gating validity check; one campaign walker lives OUTSIDE the repo | §5 assigns one owner per cell and lists retirements *after absorption* |
| "selection finds movers at the calibrated rate" | **Pre-registered selection test 09-01: NULL** — 49 cuts on 11 fire-time features, 569 fires, 18 tails, zero pass | nothing knowable at fire time picks the tail; the leverage is risk management (stop, attempts, harvest) — the operator's 09-01 reframe |
| the retry idea — not in v1 | logged 09-01: *"we keep a very tight stop… but we take more tries… up to 3 times"* | a first-class axis (§4 Axis 5), the P1 answerable-now cell (§7 Phase 1) |
| the missed-EP read — not in v1 | HTFL 08-14 (HIGH, score 96, skipped `stop_too_wide`, +29% by 09-01); only ONE of five skip buckets ever read; **#595 found 66% of `mi_ep_missed_outcomes` rows never gapped at the open** and added `setup_at_open` | its own phase (§7 Phase 2), because it decides WHICH names enter the tactics grid |

---

## 2. Method / population — read before any number

**Population:** every figure is from one of the rows/windows below, captured once and read from
file. **No new prod query was run for this document** beyond `live_rules.py`'s own read-only toggle
check (the one read-only `psql` capture attempted 2026-09-02 was blocked by the session's
permission classifier; §7 Phase 2 needs it and says so).

| label | rows | window | source | caveat that travels with it |
|---|---|---|---|---|
| **LIVE** | 26 closed real-money `mi_live_trades` (magna53, first attempts) | alerts 07-06 → 08-28 | `scripts/ep_replay_data/_pull2_out.txt` (09-01 capture) | **era-split, never pooled:** A (<08-01, ORB-low stop, no executable partial) n=12 · B (08-01→08-15, ORB-low stop + partial) n=10 · C (≥08-16, `entry−2R` half size + partial) n=4 |
| **LIVE regime split** | same 26 | same | **ENTRY-STAMPED `mi_live_trades.regime`** (Phase 4, 09-02): Bull 10 · Choppy 8 · Correcting 7 · Crisis 1 — the stamp is the PRIOR session's regime row (`live_tracker.py:522` reads `regime_date <= today` at 09:31; the nightly writes today's row at 17:00 ET), i.e. what was knowable at entry; the date-join is the entry day's own close (look-ahead) and disagrees on 8 of 26 (Bull 14 by join). Four stamps inferred from that rule (22 of 22 known reproduced): ABCL/AMLX/SOLS Bull, CRWD Choppy — confirm via `_545p4_bull_capture.sql` Q1 | **Bull ⊂ eras B+C (7+3), non-Bull ⊂ era A (15) + CRWD (C)** — any Bull-vs-non-Bull contrast is an exit-STACK contrast; the era-matched cell is 3 vs 1 |
| **PAPER** | 24–34 closed paper magna53 | 04-17 → 07-02 | `_306`/`_508` probe caches | the only cohort with multi-day winners; Bull era AND pre-06-05 entry mechanics — never pooled with live |
| **44 replayable real trades** | live + paper fills, first attempts | 04-17 → 08-31 | `ep_replay.py validate` | the calibration set for the day-1 harness; 14 abstain (11 no entry-window minutes, 3 fill-bar straddles) |
| **270 alert campaigns** | every live-source `mi_ep_alerts` row | 05-11 → 08-31 | `ep_replay.py replay --ruleset era_c` → `campaigns_era_c.tsv` | settled 100 · no_entry 37 · abstain 46 · **open_at_horizon 87 — the settled mean is CENSORED (the open rows are the candidate winners); quote the harness, never this mean as expectancy** |
| **267 caught EPs / 602 fires** | live-source `mi_ep_alerts` × the four delayed-entry rungs | May 74 · Jun 53 · Jul 41 · Aug 99 | `scripts/probes/_562bf_*`, `_562grid_*` | **mature fires only** (20 post-fire sessions by 08-31) → **August is unreadable until ~late September**; May is the era the operator ruled stale, so every cell is shown pooled AND ex-May |
| **194 filled today's-rules trades** | raw-derived population (4,453 ticker-days) under the 08-29 rule manifest, Run U (catalyst-generous) | 04-13 → 08-28 | `docs/analysis/ep_backtest_run1_2026-08-29.md`, `runner_rule_sweep_2026-08-29.md` | over-admits (no catalyst/judge/RVOL reconstruction); winners cluster in two theme runs; no CI excludes zero on any runner rule |
| **15 / 17 live stop-outs** | the July–early-August live losers | 07-06 → 08-07 | `_stop_floor_*`, `_545_reentry_sweep_output.txt`, `_545_rerun_full17.py` | every "winner" a re-entry could hold is a **session HIGH** (QBTS +8.88R, HUT +8.32R), not a close; THC's +12.43R sits on a 0.67% stop |
| **missed cohort** | 55 real EPs that got past us on day 1 (43 evaluable) | Mar → Aug | `delayed_entry_campaign_policies_327_2026-08-30.md` | **outcome-conditioned label** — every number inflated by construction; direction only |
| **`mi_ep_missed_outcomes`** | ~4,000 skipped-name rows | Feb → | #595 doc | **66% of rows never gapped at the open**; read `setup_at_open = true` only; `max_high_*` columns are MFE (positive by construction) |

**Load-bearing rule used in every table:** a result is **LOAD-BEARING** only if it is (a) n ≥ 30,
(b) holds with May excluded or spans two eras/regimes, and (c) comes from a harness that reproduces
real fills or from a rule that is live. Anything else is **ONE-COHORT** (a real read that must not
be generalised) or **REFUTED** (stated n) or **RULED** (operator decision, not evidence).

**Measurement traps that already burned this program (each appears as a caveat below):**
- `mi_ep_scan_outcomes.fwd_5d_pct` and `mi_ep_missed_outcomes.max_high_*` are maximum favourable
  excursion — positive by construction; never a harvestable return.
- `mi_ep_scan_log.gap_pct` is recomputed per tick — a day-max is an intraday peak, not the open.
- R must be each variant's OWN R, then normalised to equal DOLLAR risk before rules with different
  stop distances are compared (the 08-16 §2b correction halved a headline).
- Recorded peaks are floors under ~10 minutes of hold (`highest_price_seen` polls).
- Same-day stop-outs: a bar low can predate the fill second — the replay convention (fill bar must
  CLOSE at/below the stop) is what reconciles MANE and HUT.

---

## 3. THE INVENTORY — every variant tried, with cohort, n, what it showed, and whether it bears weight

Status vocabulary (v1's): **LIVE** · **SHIPPED** · **REFUTED** · **BUILT-DARK** · **RULED** ·
**EVIDENCE-ONLY** · **NEVER-RUN**. The last column applies §2's rule.

### 3.1 Day-1 entry timing

| # | variant | cohort · n | what it showed | status | load-bearing? |
|---|---|---|---|---|---|
| 1 | **ORB 1-min breakout** (stop-limit at the first-minute high, 9:31–9:44) | LIVE · 26 closed | 5 wins of 26; **0 of 26 ever realized ≥4R**; era A 0 of 12 (−9.65R) · era B 3 of 10 (+1.92R) · era C 2 of 4 (−0.17R). 17 of the first 22 died on the entry day | LIVE | the baseline; no cell is judged except against it |
| 2 | ORB 5-min (entry AND stop from the 5-min range) | #268 sim year n=300 vs 399 (06-12); 5-min shadow lane n=38 closed (09-01); 22 same-ticker-day pairs vs live | sim: +0.15R vs +0.95R baseline; lane +0.02R mean / −0.70 median, 16 of 22 pairs worse than live, **era-C pairs 0 of 3 better**; the "20 of 21 losers rose" finding was an MFE artifact — honestly 2 of 19 losers offered ≥4R | REFUTED as an entry+stop pair (three reads) | REFUTED (n=38 + 22 pairs; era C n=3 too thin) |
| 3 | ORB 5-min entry with an INDEPENDENT stop | none | never tested (v1 §B noted the refutation does not cover it) | NEVER-RUN | ◻ |
| 4 | Skip-wide-open (`stop_too_wide`: ORB range > 1.5×ATR) | #268 (06-18); 9 rejected MAGNA53 names, 5 settled (08-17); 55 sessions, 3 filled alerts ≥1.5× (08-15) | rejected names land within noise of what we trade; **HTFL** rejected 08-14 at 1.75× ran +27% by day 5, +29% by 09-01 | LIVE gate; EVIDENCE thin | ONE-COHORT (n=5 settled); the tail case is n=1 |
| 5 | Wait-for-established-intraday-low entry (buy the HOD after a 30-min unbroken low) | #572 · 30 live day-0 sessions (08-18) | no entry on 19 of 30 days; on the 11 traded, worse than the baseline by −1.17 ADR/pair median; a fade-day DETECTOR, not an entry | EVIDENCE-ONLY | ONE-COHORT (era A/B) |
| 6 | Anticipation (pre-breakout coil close) — Family A | `mi_consolidation_entry_shadow` n=150 | −0.217R, 36.7% win → NO-GO 07-12; the stop was ~6× tighter than confirm's and the median trade still reached +2.44R — an exit-side failure | REFUTED for graduation | different setup; carried for the mechanism |
| 7 | Price-aware limit fallback (#500) · ask-aware trigger (#541) | live since 07-23 · 08-07 | 14 entries after 08-07, zero venue rejections (by 08-13) | SHIPPED | mechanics, not tactics |
| 8 | **Gap-over open entry on the EP-day high** (the VPG/ARM class) | none | the stop grid's high-break winners GAP OVER the level, so every bar-anchored stop kills them; "buy the gap-over open" is a different entry definition that has never been written as a setup | NEVER-RUN | ◻ — new cell from the 09-01 grid |

### 3.2 Day-1 stop basis

| # | variant | cohort · n | what it showed | status | load-bearing? |
|---|---|---|---|---|---|
| 9 | ORB low (the retired stop) | live 10 (07-25) · 14 (08-06) · 21 (08-22) | width vs the stock's own 20-day range is essentially random: 0.15–1.19×, **median 0.42 — under half a normal day** (18 of 21 under one day); the four biggest movers sat in the tight half | RETIRED 08-16 | LOAD-BEARING (three cohorts agree) — about a rule no longer live |
| 10 | **`entry − 2R` at half size, +2R target pinned to the ORB frame** | 43 matched reconstructed Apr–May (0c-pre) · live era C n=4 | reconstructed: −6.0R → **+11.4R at equal dollar risk, median −1.00 → +0.33**; live era C: AMLX +1.29 · CRWD +0.38 · MRVL −0.87 · SOLS −0.98 = −0.17R | **LIVE (08-16)** | direction LOAD-BEARING (n=43, one regime, reconstructed); live n=4 grades nothing yet |
| 11 | ORB-multiple widening 1.25×/1.5×/2.0× | 12 live + sim n=147 (08-03) | every live loser still lost at every width; sim totals top-5-carried, median delta 0.00 | REFUTED | REFUTED (one era) |
| 12 | ADR volatility FLOOR k=0.5/0.75/1.0 with the +2R target moving with the stop | 14 live, minute-bar forward replay (08-06 §E) | survival on day 0 was DELAY: k=0.75 −9.00R vs −7.33R no floor; floor alone −14.00R at every k, 0 winners. **Mechanism: the wider R-unit raised the +2R target above the actual peak** (MANE 121.98 → 132.32 vs a 129.80 high) | REFUTED as run | REFUTED (n=14, non-bull) — **but the mechanism it died of was removed by the 08-16 target pin**, so the question is OPEN again in the pinned frame (§4 Axis 2) |
| 13 | ATR-0.5× · ATR-1.0× · prior-day-low stops, same entries | #572 · 30 live day-0 sessions (08-18) | ATR-0.5× the lone ADR-positive delta (+3.45 ADR sum, +0.10 median) but more shake-outs; prior-day-low = the R-unit mirage (best median R −0.31, worst dollar loss −23.70 ADR) | EVIDENCE-ONLY | ONE-COHORT |
| 14 | Closing-basis stops (hold through every intraday breach) | 75 reconstructed HIGH (08-16); 43 matched at 60 days | stop-outs 69% → 47%, ≥5R 1.3% → 5.3%, max +20.78R, **but −13R vs live on total and unbounded intraday risk** (MANE −19.6R excursion); at 60 days +36.8R vs −6.0R crude, **+16.8R at equal risk** | EVIDENCE-ONLY | ONE-COHORT (Apr–May, daily grain past day 0, no out-of-sample) |
| 15 | Prior-day low as the day-1 stop (9M geometry) | 12 live (08-03) | a different trade: ~20% stop, 5× winner shrink; 6 of 12 stopped within 5 days anyway | REFUTED | REFUTED |
| 16 | **Stop for a RE-ENTRY leg** (prior-day low · 5-min low · session low-so-far · basing low · 620 basing low) | the 08-07 sweep's per-variant stops (n=15) | low-so-far / basing-low stops fed 9–13 second full stops out of 13–15 fires on every base-then-turn and 620 variant | EVIDENCE-ONLY | ONE-COHORT; the day-2+ grid says the same thing with n=602: **bar-anchored stops are dominated on every rung** |

### 3.3 Profit-take / harvest

| # | variant | cohort · n | what it showed | status | load-bearing? |
|---|---|---|---|---|---|
| 17 | **+2R partial (1/3) → breakeven** | 14 live (08-06) · PLTR + ETON, the first live winners (08-24) · n=194 today's-rules replay (08-29) | 14 live: −13.15R → −7.33R, every "winner" a +0.67R bank. **PLTR: the rule cost $19.57 = 0.57R = 15% of a +3.69R trade** (as designed; $9.40 as it actually fired a day late). **n=194: 106 fire the partial, 82 of them round-trip to breakeven at exactly +0.33R** | **LIVE** | LIVE; the breakeven scratch is the largest measured harvest leak (n=194, no CI; one live winner) |
| 18 | Partial vs full exit at +2R | 15 old-era live losers · PLTR | full exit beats partial by +4.20R on the losers; **partial beats full by +1.13R on PLTR; ~3.7 PLTR-shaped winners flips the ranking** | EVIDENCE-ONLY | undecided by construction (winner rate) |
| 19 | Arming breakeven at +1R vs +2R | 2 paper runners (08-08) | +1R arm destroys GOOGL's +8.18R entirely (0.00); +2R keeps +3.35R | mechanism | n=2 — a reason never to lower the trigger, not a level |
| 20 | Exit-ALL at +2R / +3R / 1 ADR | paper runners; PLTR | BW +10.16R → +2.00; PLTR exit-all-2R costs 46% of the trade | REFUTED by THE GOAL | recorded so it is never adopted on a mean-R argument |
| 21 | Trigger UNIT (R vs ADR vs fixed-%) | 12 live + 43 records (08-01) · 9 live + 31 paper (07-25) | entry-to-stop spans 0.15–1.17 ADR (7.7×), so "+2R" is 0.31 days on MANE and 2.35 on NVCR; fixed-% mis-scales 3× across a 2.6–9.7% ADR universe; ADR-multiple the only basis positive on BOTH cohorts without one catastrophe dodge (1×ADR live −0.23 vs +2R −0.46) | EVIDENCE-ONLY | ONE-COHORT; blocked on live runners (peak ≥1.5 ADR count) |
| 22 | Giveback peak-lock (arm +6% / floor 60%) | 28 paper (07-08); shadow 0 rows | +$8,075 lock-attributable offline; **operator ruled it OUT 08-11 — "we let winners run"** | **RULED OUT** | closed by ruling |
| 23 | Day-3/5 time partial (the 03-27 rule) | 12 live (08-01) | 1 of 12 reached day 3; 0 fired; day-5 unconditional removed by the operator 08-01 | superseded | inert on live holds |
| 24 | Seeded SMA10/20 trail (stock's own closes, 08-08 fix) | paper n=33 · live n=3 · 116 extension cohort · n=194 | paper +0.64 → +1.27R (8 better / 2 worse); trail cost ≈0 on 116 (+0.3R, cut zero names by >0.5R); `live_trail_be` ≈ breakeven control on n=194 (+0.131 vs +0.142) | LIVE | direction consistent: costs ~nothing, banks ~nothing measurable yet |
| 25 | Second partial higher up (5R/8R/10R/15R × fraction) | none | operator variant 08-08, self-gated *"once we have runners"*; live cohort has never held past +3.69R | NEVER-RUN | ◻ gated on runners |
| 26 | Structural-level take (prior high / 20d / 52wk) · sell-into-day-2-gap | 10 live · 41 trades | zero fires for geometric reasons · fires 6 of 41, banks near local tops when it does | REFUTED as primary / complement | follows from the setup's definition |
| 27 | Character-conditioned time exit (biotech runs days) | — | operator-deferred 08-01 *"later not now"* | DEFERRED | — |
| 28 | Management arms on delayed (day-2+) entries: M-none · M-trail · M-live · M-noBE | missed cohort 23 entries (08-30) · 267 caught EPs (09-01) | missed cohort: **no-management +162.3R vs the live shape +52.1R** (trail −72R, partial −37R, BE ~0) — on an outcome-conditioned label, and #270 found the opposite sign on its cohort. On the 267 caught EPs the trail BEATS hold-only on every rung (family −0.39 → −0.18 incumbent; −0.12 → +0.05 at 0.75×ADR) — there it is loss-truncation, not exit alpha | EVIDENCE-ONLY | **DIRECTION ONLY — the sign flips with the population (P8)** |

### 3.4 Hold / runner rules after the partial

| # | variant | cohort · n | what it showed | status | load-bearing? |
|---|---|---|---|---|---|
| 29 | Runner rules after the +2R partial: hard-stop-stays · t3/t5/t10/t20 · sma10/20 · atr1/atr2 · gb25/gb50 vs breakeven (control) | n=194, today's rules (08-29) | every looser rule beats the control on MEAN (best t20 +0.36 vs +0.14) by flipping the MEDIAN trade +0.33 → −0.33 and win rate 55% → 25–44%; the 82 breakeven round-trips are worth +12R to +51R under every alternative; **no rule's 95% CI excludes zero; the edge lives in April and July** | EVIDENCE-ONLY | DIRECTION consistent (11 of 13 rules); magnitude and ranking unsettled |
| 30 | Breakeven delayed 1/3/5 days · breakeven on a closing basis | 116 extension names (wrong cohort) · 75 HIGH (08-16) | on the HIGH cohort the mild forms are noise (ceiling stays +6.19R, cost 2–6R) | EVIDENCE-ONLY | ONE-COHORT, reconstructed |
| 31 | 20-session time exit on delayed rungs (M-none) · 40-session mark (ep_backtest) | 602 fires · 194 | a horizon choice inherited from engines, never chosen; the 08-16 read found catch rate rising monotonically to a 20-day wait window and not turning over | EVIDENCE-ONLY | horizon is an unpriced axis |

### 3.5 Re-entry and attempts — same-day, next-day, N-day, campaign

| # | variant | cohort · n | what it showed | status | load-bearing? |
|---|---|---|---|---|---|
| 32 | Same-day 1-min re-entry (pre-R3) | 6–7 re-entries, 60d to 05-17 | 0 wins, avg −6.0%; killed 05-17 (R3); `R3_DAY1_REENTRY_ENABLED` unset in prod, 0 attempt-2 rows since | REFUTED / config-off | REFUTED (n=7, stale era) |
| 33 | **Same-day 5-min-range-clear re-entry** (`orb_5m_reentry_hybrid_replay`) | 15 (08-07) · **full 17 (08-09)** | fired 9 of 17; 1 real hold (**THC +12.43R on a 0.67% stop**), 2 partial-then-scratch, **6 second full stops** (CRCL/FIGS/HUT/QBTS/WKC/WULF); net +7.76R, **ex-THC −4.67R**; fired on two of the four biggest forward movers and paid a second stop on both | EVIDENCE-ONLY — **RAN; the YAML entry still says `pending`** | ONE-COHORT, one-trade-carried |
| 34 | Next-day-open unconditional re-entry (stop = prior-day low / first-5-min low) | 14 (08-07) | NDO-pdl fired 11/14: net +0.92R with **6 second stops (−6R paid)**, −2.02R without the best name; NDO-o5l +8.50R = THC +11.83R unsettled, −3.33R without it | EVIDENCE-ONLY | ONE-COHORT, THC-carried |
| 35 | Base-then-turn proxies (2/3 higher lows · 2/3 higher closes · 20/30/45-min base ≤0.25×ADR then break) | 15 (08-07) | HL/HC: −6.4R to −10.9R, 9–11 second stops on 11–13 fires; BASE20 +5.53R (THC) → −2.57R without it; none held QBTS or HUT beyond a +0.67R bank | EVIDENCE-ONLY | ONE-COHORT; every proxy is a modelling choice, none is the operator |
| 36 | 620 MACD-cross re-entry (6/20 · 8/24 · 12/26) | 15 (08-07) · 44 stopped episodes (08-22) · 267 EPs (09-01) | fired 15/15 and paid 12–13 second stops (−8.0R to −9.7R); 620 near the EP close on 44 episodes +0.21R but **closed-only −3.74R** (SMCI settled +4.19R; TEAM settles 09-08); the 620-prox rung on 267 EPs −0.35R (n=126) incumbent, +0.12R trail at 0.75×ADR and **not independent of the low-reclaim rung** (shares 109 campaigns) | EVIDENCE-ONLY | consistent direction across three reads: **620 alone is noise; 620 at a pivot ≈ break-even** |
| 37 | **Same-day attempts 1 / 2 / 3 / 4** (identical trigger, stop, exit; each attempt a fresh 1R) | 75 reconstructed HIGH, Apr–May (08-16) | 2 attempts −9.1R vs 1 attempt −23.4R, **catches the +20.26R name 1 attempt missed**; 3 and 4 strictly worse (more cuts, no new catch); worst case bounded −2R/−3R/−4R per name; ~13 retries fired; **without the single best name 1 and 2 attempts are identical** | EVIDENCE-ONLY | ONE-COHORT — and the parked 32-cell grid found EVERY ≥5R outcome in the early half of that cohort; **per-NAME accounting was done here** (sum incl. every attempt, worst case per name) |
| 38 | Campaign policies: same-trigger ×1 (R1) · unlimited (R2) · re-enter only on EP-high strength (R3) · abandon after 2 | missed cohort, 43 evaluable / 23 entered (08-30) | R1 +4.2R net on 8 re-entries · R2 +0.6R on 10 (cost doubles, no added win) · **R3 +12.9R on 10 at −2.5R failed-attempt cost**; re-entry does not rescue recall | EVIDENCE-ONLY | DIRECTION ONLY (outcome-conditioned label) |
| 39 | Shadow-lane bounded re-entry rows (`same_pattern` / `new_high_break`, ×1 each, day-2+ only) | live lane since 08-30 | recording; the PLAN line counts ~693 attempt rows as of 09-01 (not re-verified today); first honest read ~09-23 | forward capture | ACCRUING |
| 40 | Next-day / N-day re-entry on HIGH alerts (reclaim EP low · EP close · prior-day high · 10-MA; wait 3/5/10/20 days) | 99 HIGH names, daily bars, Apr–May (08-16 v1/v2) | every shape positive after a 0.5×ADR stop floor (best +110–122R); **catch of the 40 ≥5R names rises with the wait: 18% at 3 days → 28% at 20 — and still misses 72%**; pre-floor R totals were tight-stop artifacts | EVIDENCE-ONLY | superseded by #41–42 (minute bars, 267 EPs, the lane's own functions) |
| 41 | **The four delayed-entry rungs on 267 caught EPs** (EP-low reclaim · EP-close reclaim · EP-high break · 620 near EP close), incumbent stops | 602 first-attempt fires; mature: 130 / 86 / 32 / 126 (09-01) | **recall solved: fires on 96% of caught EPs and 13 of 13 that ran ≥8×ADR**; **every rung mean-negative, median fire a full stop** (−0.39 / −0.44 / −0.41 / −0.35R); 18 of ~570 fires ever ≥4R; the whole raw tail is May | EVIDENCE-ONLY | LOAD-BEARING for recall (n=267, 4 months); the expectancy read is of the INCUMBENT stops only |
| 42 | **Stop basis on the rungs: 13 bases × 4 rungs** | same 602 fires (09-01) | one shape everywhere: **the working stop is volatility-proportional (0.75–1.25×ADR), not structural**; `ep_low_reclaim` × entry−0.75..1.0×ADR × trail: **+0.17–0.25R/fire pooled (n=130), +0.16–0.19 ex-May (n=70), positive May+Jun+Jul, kills 0 fires**; family-wide −0.18 → +0.05R trail; bar-low / LOD / EP-close / EP-low bases dominated or winner-killing on every rung; the high-break's +53R is two May gap-overs (0 of 17 ex-May) | EVIDENCE-ONLY; **#616 records the band forward (built 09-02, deploy pending)** | LOAD-BEARING for the SHAPE (monotone band, 4 rungs × 3 months); the magnitude (+0.19R ex-May) is a candidate for the forward out-of-sample read, not an edge |
| 43 | **Selection at fire time** (11 pre-registered features, 49 cuts) | 569 settled fires, 18 tails (09-01) | **zero cuts pass** (≥8% tail rate at n≥30, ex-May, both arms); the one cut over 8% collapses to 4.5% ex-May; features barely move a 3.2% base | NULL | LOAD-BEARING NULL (pre-registered) |
| 44 | Which day-1 group to re-enter (simulated: stopped-out · never-triggered · survived) | 157 EPs that met our entry criteria, day-1 trade simulated (09-01) | **111 of 157 (71%) unfilled for OUR reasons** (window-late 38 · unfilled 34 · outage 8 · breaker 7 · cap 5 · size 5); stopped-out group's delayed fires −0.45R (n=91) with 4 of 7 tail fires ex-May; never-triggered −0.79R (n=15, 0 tail); sim agrees with real day-1 trades 33 of 34 | EVIDENCE-ONLY | ONE read; day-1 group is at most a ranking signal |

### 3.6 Missed EPs — the population that never entered any grid

| # | variant | cohort · n | what it showed | status | load-bearing? |
|---|---|---|---|---|---|
| 45 | `stop_too_wide` bucket read | 9 MAGNA53 rejects, 5 settled (08-17) | within noise of what we trade; HTFL the tail case (+29%) | EVIDENCE-ONLY | ONE-COHORT (n=5); **the only bucket ever read** |
| 46 | The unread buckets (PLAN 09-01, `real setup` = gapped at the open per #595) | outside_top20 791 rows / 213 real / **18 ran ≥20%** · score_below_50 329 / 176 / **14** · session_rvol_low 321 / 140 / **15** · mcap_low 223 / 100 / **14** · stop_too_wide 8 / 8 / 1 | never judged on the tail; `ret_5d` under-counts HTFL's run (+27% at day 5, +29% by day 13) | NEVER-RUN | ◻ — §7 Phase 2 |
| 47 | Extension filter vs the fat tail | 159 extended names / 70 sessions (08-16) | median 20-day return −38% AND 17.6% doubled; 28 of the 142 hundred-percent movers in the dataset | EVIDENCE-ONLY | **MFE-based** (20-day max high) — a population description, not a harvestable return; needs the day-1 bracket replay |

### 3.7 Headline tally

- **~47 distinct variants** measured (plus the 34-candidate exit grid and the 13-policy campaign
  set), across ten non-interchangeable populations.
- **Variants that have ever ACTED on real money: three** — the +2R partial (08-01/08-05), the
  `entry − 2R` half-size stop (08-16), the seeded SMA trail (08-08). Everything else is replay,
  shadow, or dark.
- **LOAD-BEARING results by §2's rule: four, plus one pre-registered NULL** — the retired ORB-low
  stop was inside one day's noise (three cohorts); the four delayed rungs have 96% recall on 267
  EPs; their incumbent stops lose on every rung; the volatility-proportional stop band improves
  every rung from either direction; and (the null — settlement-based, not fill-validated, but
  pre-registered) nothing knowable at fire time separates the tail. **Everything else is a
  one-cohort read.**
- **Live winners ≥4R in the program's history: zero** (26 closed live trades). The +4R-average-winner
  requirement of THE GOAL has never once been met on real money.

---

## 4. THE PARAMETER GRID

✅ answered (cohort noted) · ⚠ partial / confounded / one-cohort · ⛔ refuted · 🔒 operator-ruled ·
◻ open. **Unless marked, every ✅/⛔ is a non-bull-or-era-confounded answer (Axis 6).**

### Axis 1 — entry timing

| cell | status | who owns the next read (§5) |
|---|---|---|
| ORB 1-min at the open (LIVE) | ✅ baseline; era C n=4 | `ep_replay.py` |
| ORB 5-min entry + 5-min stop | ⛔ three reads (n=300 sim · n=38 lane · 22 pairs) | lane accrues; no work |
| ORB 5-min entry + independent stop | ◻ | `ep_replay.py` after the stop-mode extension |
| next-day open re-entry after a day-1 stop-out | ⚠ one cohort n=14, THC-carried, 6 of 11 fires paid a second stop | `ep_replay.py` after the attempt-2 leg |
| same-day re-entry, 1-min | ⛔ n=7 (R3) | — |
| same-day re-entry, 5-min-range-clear | ⚠ n=17, ex-THC −4.67R; **close the YAML entry** | — |
| base-then-turn / 620 re-entry, same session | ⚠ n=15: 9–13 second stops per variant | — |
| EP-low reclaim · EP-close reclaim · EP-high break · 620 near EP close (day 2+) | ✅ recall (n=267); expectancy break-even at best under the ADR band | `_562_backfill_replay.py` lineage + the live lane |
| gap-over open entry on the EP-day high | ◻ never written as a setup | `_562` lineage (new rung definition — the operator names it first) |
| wait-for-established-low | ⚠ n=30, negative; a fade detector | — |
| anticipation coil | ⛔ n=150 shadow | — |

### Axis 2 — stop basis

| cell | status | owner |
|---|---|---|
| ORB low | ✅ retired: median 0.42 of one day's range (n=21) | — |
| `entry − 2R` half size, target pinned (LIVE) | ⚠ n=43 reconstructed one regime; live n=4 | `ep_replay.py` (era C accrues) |
| ORB multiples · prior-day low on day 1 | ⛔ | — |
| **ADR-anchored day-1 stop with the target PINNED** (k = 0.5 / 0.75 / 1.0 / 1.25) | ◻ — the 08-06 refutation was of the moving-target frame; **the pinned frame has never been swept on day 1** | `ep_replay.py` after `stop_mode` gains `adr_k` |
| ADR-anchored stop on the delayed rungs | ✅ shape (n=602); ⚠ magnitude (+0.19R ex-May) → forward read via #616 | `_562` lineage · #616 review |
| structure stops on the rungs (bar low · LOD · EP close · EP low · prior low) | ⛔ dominated or winner-killing on every rung (n=602) | — |
| closing-basis stops | ⚠ n=75 reconstructed; unbounded intraday risk | `ep_replay.py` if the operator wants it priced on real bars |
| stop for a re-entry leg | ⚠ every bar-anchored basis fed 9–13 second stops (n=15) | the retry test (Axis 5) |
| **joint stop × profit-target sweep** | ◻ mandatory for ANY stop candidate (the R-unit coupling) | `ep_replay.py` |
| **`stop_too_wide` → size DOWN instead of skip** (same dollar risk, smaller position) | ◻ — the operator's structural hypothesis (09-01) | `ep_replay.py` with `validate_orb_entry` relaxed |

### Axis 3 — profit-take

| cell | status |
|---|---|
| none (ride to trail/time) | ⚠ direction only — sign flips with population (§3.3 #28) |
| +2R · 1/3 · breakeven (LIVE) | ✅ live; toll priced once (PLTR 15%); 82 of 106 scratch to +0.33R (n=194) |
| ADR-multiple trigger | ⚠ one cohort, blocked on runners |
| fixed-% · exit-all | ⛔ |
| second partial at 5R / 8R / 10R / 15R × fraction | ◻ gated on runners (operator's own gate) |
| structural / day-2 gap | ⚠ complement only |
| giveback peak-lock | 🔒 ruled out 08-11 |

### Axis 4 — hold / runner rules after the partial

| cell | status |
|---|---|
| breakeven (LIVE) | ✅ control on n=194 |
| hard stop stays · t3 / t5 / t10 / t20 · sma10 / sma20 · atr1 / atr2 · gb25 / gb50 | ⚠ direction (11 of 13 beat the control on mean; none at 95%); cost = median +0.33 → −0.33, win 55% → 25–44% |
| seeded SMA10/20 trail (LIVE) | ✅ ≈ control (n=194); ≈0 cost on 116 |
| horizon (20 vs 40 vs 60 sessions) | ◻ unpriced axis inherited from engines |
| character-keyed time exit | 🔒 deferred by operator |

### Axis 5 — ATTEMPTS (new; first-class — the operator's retry idea)

His trade-off, verbatim: *"with tight stop losses, to get positioned often requires multiple tries…
we keep a very tight stop, like what you've listed, but we take more tries… if we get shaken out by
intraday volatility we just retry let's say up to 3 times."*

| cell | status |
|---|---|
| 1 attempt (LIVE) | ✅ baseline |
| 2 attempts, same day, same trigger | ⚠ n=75 reconstructed: catches the one +20R name, worst −2R/name, identical to 1 attempt without that name |
| 3–4 attempts, same day | ⚠ strictly worse on the same cohort (more cuts, no new catch) |
| same-trigger ×1 / unlimited / strength-proof ×1 (campaign level) | ⚠ direction on the missed cohort: strength-proof +12.9R at −2.5R cost; unlimited doubles cost for nothing |
| **stop width × max attempts (1 / 2 / 3 / unlimited-in-window) on the delayed rungs, per NAME** | ◻ **THE RETRY TEST — never run.** Every prior attempts read varied attempts at ONE stop width; his idea couples a TIGHT stop to MORE tries, and the 09-01 grid says tight stops lose per attempt — so the cell is genuinely open, and only per-campaign accounting can answer it |
| the lane's bounded re-entry rows (day-2+, ×1 per shape) | ACCRUING; first read ~09-23 |

**The unit rule for this axis (stated now so the result cannot flatter):** with risk-based sizing
every attempt risks the same DOLLARS, so a 3-attempt campaign at a tight stop risks up to **3R of
dollars** against a 1-attempt campaign's 1R. Report per name: total R at equal dollar risk per
attempt · attempts actually fired · campaigns that spend every stop and never get positioned ·
campaigns netting ≥4R (one +6R after two −1R stops is +4R and a WIN) · **worst cumulative drawdown
on one name**. A per-trade average hides the retries and is not an output of this cell.

### Axis 6 — regime (cross-cutting)

| cell | status as of 2026-09-02 |
|---|---|
| non-bull, live, old stack (era A) | ✅ n=12, 0 winners — the whole "0-for-14" record lives here |
| bull, live (entry-stamped) | ✅ **n=10, RUN 09-02** (`docs/analysis/exit_tune_bull_regime_read_2026-09-02.md`): **−1.95R, 3 winners (ABCL +2.68R, AMLX +1.26R, ETON +0.52R via the #566 defect), 7 of 10 died on the entry day** — vs non-Bull n=16 −9.33R, 10 of 16 day-0. **Confounded with ERA on every realized number**: Bull = era B×7 + C×3, non-Bull = era A×15 + CRWD; the 3-vs-1 era-C cell decides nothing. Date-join sensitivity: Bull 14 → −0.17R, 5 winners (moves PLTR and CRWD in, SOLS out) |
| what transfers to Bull | ✅ **the STOP conclusions**: day-0 death rate unchanged (6 of 7 under the ORB-low stop), ORB-low stop median 0.42 ADR in Bull too (7 of 7 under one day's range) — tape-independent |
| what does NOT transfer cleanly | ⚠ **partial / breakeven-trail / floor**: the partial priced on the 5 real firings is a wash (+0.42R net; cost 0.10–0.34R on each runner, +0.73R on FIGS's collapse); the TRAIL carried ABCL/AMLX/PLTR (exits at trailed stops 10.65/34.45/170.39); the BREAKEVEN arm ended ETON at ~0R on a day it closed +6.6 % (one case). The 08-06 floor refutation is **neither confirmed nor re-opened**: a 0.75×ADR floor rescues ONE Bull ORB-low trade on day 0 (TEAM, which then ran +16.8 % in 10 sessions — the whole +4.29R gap over the no-floor row is that trade; ABCL/ETON survive day 0 with no floor), a 1.0×ADR floor also rescues FRMI, which hits the wider stop on session 2 (the 08-06 delay mechanism repeating). n=1–2, widened-R units, daily-grain forward walk; the same method reproduces −14.00R/0 wins on the non-Bull 14. The signed 2R stop (era C) is the live test |
| runners in Bull (operator 08-01 hypothesis) | ⚠ direction now WITH it: the three ≥4-ADR runs in the live record (ABCL 4.75, AMLX 5.52, PLTR 4.62) were all entered on Bull days (2 of 3 by stamp); the one non-Bull-stamped trade ≥ 4 ADR of 16 is PLTR, itself a Bull day by join — but multi-week holds exist only under the trail stack, so even peaks are era-confounded. n=3; the 08-17 read (n=6/7) pointed the other way |
| `exit_tune_bull_regime_read` | **RUN 09-02 at n=10, re-gated**: threshold 8 → 20 stamped-Bull AND ≥5 non-Bull era-C closes (`LEAST(bull, 4×nonbull_eraC) ≥ 20`) — a bigger Bull count alone cannot break the confound. The 34-candidate grid was NOT re-run (the 08-17/08-22 engine snapshots lived in session scratchpads and are gone); `scripts/probes/_545p4_bull_capture.sql` re-creates the engine's 4-TSV shape for the next run |
| non-bull, live, era C | ⚠ n=1 — **CRWD 08-27 (+0.40R), not SOLS**: SOLS is stamped Bull (08-27's row) and joins Choppy; CRWD is stamped Choppy (08-26's row) and joins Bull. **The cell that breaks the era confound**; accrues by trading, readable at ~5 |
| bull, no-broker control (5-min shadow lane) | ⚠ n=38 lane, 12 winners, all on daily-bar reconstructions; real-time-accrued rows −0.99R median |

### Axis 7 — sizing (named, out of scope, interacts)

Risk-based sizing (`shares = risk_dollars / stop_distance`) is what makes Axis 5's unit a dollar
unit, what halved the position on 08-16, and what the "size down, not skip" cell tests. Sizing
itself is untouched and operator-owned (#571 owns it).

---

## 5. THE HARNESSES — reconciled: ten lineages, one owner per cell, retirements after absorption

**Four overlapping tools is itself a finding — and the count is ten.** Each lineage was minted
because the previous one could not answer the next question; nobody retired the last one. The
rule from here: **a cell has ONE owner; a new question extends the owner; a harness retires only
after its unique capability is absorbed.**

| # | harness | replays what | fidelity evidence | unique capability | verdict |
|---|---|---|---|---|---|
| 1 | **`scripts/ep_replay.py`** (repo, reusable) | day-1 campaigns over stored minute + daily bars under an EXPLICIT rule-set; `ruleset_as_of(date)` era-matches; abstains rather than fabricates | **validate PASS 09-02**: stop 44/44 · entry 33/33 · exit class 29/30 · R 25/30; replay abstain 17% vs 30% ceiling; calls LIVE `validate_orb_entry`, `stop_limit_buy_price`, `profit_target_r_per_share`, `apply_daily_exit_step`, `_score_ep` | live code paths + era matching + a self-gating validity check; replays ALL 270 alerts (skipped ones included) | **OWNER of every day-1 cell.** Gaps to close before it can own the whole day-1 grid: `stop_mode` has only `orb_low` / `entry_minus_2r`; no runner-rule axis; no attempt-2 leg (6 re-entry trades excluded); 87 of 270 era-C campaigns `open_at_horizon` (censoring — state it on every read) |
| 2 | `scripts/probes/_bt_replay.py` + `_runner_sweep.py` | today's bracket over a raw-derived 4,453 ticker-day population; `runner_rule` axis | 295-row reproduction gate vs run 1; self-tests + mutation tests; no `exit_logic` ladder | the runner-rule axis (13 rules) and the raw-derived population | **fold `runner_rule` into `ep_replay`'s RuleSet, then RETIRE**; its n=194 findings are carried in §3.4 |
| 3 | **`scripts/probes/_562_backfill_replay.py`** + `_562_stop_grid_probe.py` + `_562_theoretical_day1_probe.py` | the four delayed rungs over 267 caught EPs, using the live lane's OWN pure functions (`compute_settlement`, rung evaluators) | 602/602 fires reproduced before any variation; incumbent settlements 0-drift; day-1 sim 33 of 34 vs real trades; ABVX hand-walked | the day-2+ family, both exit arms, 13 stop bases, the theoretical day-1 population | **OWNER of every day-2+ cell and of the retry test** (needs an offline campaign loop that re-drives the lane's re-entry logic — the lane's `_replay_same_pattern_*` / `replay_level_break` are DB-bound, so the loop must prove it reproduces the lane's recorded re-entry rows before quoting) |
| 4 | `scripts/probes/_508_exit_rule_replay.py` | 34 candidate exit rules against RECORDED live/paper trades (`mi_sell_discipline_records`) | twice-verified fill contract; regime cells entry-stamped | the recurring reviews' engine (`exit_tune_cohort_review`, `exit_tune_bull_regime_read`) | **OWNER of the n-milestone and bull-regime reviews** (recorded trades only — it cannot re-admit or re-enter) |
| 5 | `scripts/probes/_stop_floor_forward_replay.py` + `_545_reentry_sweep.py` + `_545_rerun_full17.py` | minute-bar forward walk of live stop-outs; a SECOND leg after the stop-out | k=0 reconciles to reality within 0.07R/trade (n=14) | the only walker that has ever carried a same-day re-entry leg on real stop-outs | **RETIRE after `ep_replay` gains an attempt-2 leg**; findings carried in §3.5 |
| 6 | `scripts/probes/_306_intraday_partial_sim.py` | partial-trigger basis sweep, 9 live + 31 paper | same contract as #4 | none left — #4 supersedes it | **RETIRE** (findings in §3.3 #21) |
| 7 | the 08-16 family: `_468_moderate_realized_r.py` · `_ext_live_exit_replay.py` · `_ext_cohort_replay.py` · `_545_grid.py` · `_reentry_vs_nostop.py` · `_delayed_reentry.py`/`_v2.py` | reconstructed HIGH-alert trades, daily grain past day 0, Apr–May only | no validity gate; the parked grid found every ≥5R outcome in its first half | the attempts 1–4 read and the wait-window read | **RETIRE**; findings carried (§3.2 #14, §3.5 #37, #40). Any re-ask runs on #1 or #3 |
| 8 | `scripts/probes/geometry_sweep_572.py` + `bracket_geometry_read_482.py` | sim-vs-sim geometry on 30 live day-0 sessions; the 5-min lane read | calibration: sim +11.94R rosier than live on identical trades | ATR/structure day-1 stops, the established-low entry | **RETIRE after #1 gains `adr_k` stop modes**; the 5-min lane itself keeps accruing |
| 9 | `~/.claude/jobs/6b173ac9/tmp/327s3_campaign.py` (+ its Stage-2 walker) | 13 campaign policies per NAME on the missed cohort | equality assertion vs Stage 2; NOT validated against real fills | per-name campaign accounting (entry + stop + management + re-entry + abandon) | **NOT IN THE REPO.** No phase may depend on it. Its 13-policy vocabulary is inherited by the retry test on #3 |
| 10 | `scripts/_306_harvest_sweep.py` · `scripts/_270_*` · `scripts/_327_replay.py` | the giveback sweep · the #270 state machine · the 9M consolidation replay | — | history | giveback RULED OUT; #270 rebuilt as the live lane; **keep as history, no new runs** |

**The forward instruments (not replayers, and not retirable):** the live delayed-entry lane
(`delayed_entry_shadow.py` → `mi_delayed_entry_watch` / `mi_delayed_entry_trigger`, with #616's
ADR-stop variant columns pending deploy), the 5-min ORB shadow lane (`mi_orb_shadow_trades`), the
sell-discipline recorder (`mi_sell_discipline_records`), and the path recorder (`mi_intraday_bars`,
now 5-year retention and a minute path for every alert ticker-day since #567).

**Retirement is sequenced, not immediate:** #2, #5, #8 each hold one capability #1 lacks. The
order is: extend #1 (stop modes · runner rule · attempt-2 leg), re-run `validate` (must stay PASS),
reproduce one headline from each retiring harness on #1, then retire.

---

## 6. ANSWERABLE NOW vs NEEDS CAPTURE — per cell, with the harness and the cost

**$0 path first.** Every "NOW" row runs on captured files already in the repo. The ONLY priced
dollar item anywhere in this program is `ep_backtest` Stage 1b (re-grading catalysts to collapse
the L/U expectancy band): **≈ $40, ceiling $60** (`docs/design/ep_backtest_spec_2026-08-29.md` §7)
— it is NOT part of this card and needs the operator's sign-off on that one number before the
first dollar.

| cell | answerable NOW? | harness · data | cost (agent) | what it cannot see |
|---|---|---|---|---|
| **The retry test** (stop width × attempts 1/2/3/unlimited, per name, on `ep_low_reclaim` first, then all four rungs) | **YES** | #3 extended with an offline campaign loop · `_562bf_*` + `_562sp_extra_minutes.tsv` (already captured); the loop's reproduction of the lane's recorded re-entry rows is checked once Phase 2's capture pulls them — not a prerequisite to run | ~1 session, $0 | August (immature until ~late Sept); same-day re-entry (the lane is day-2+ by ruling); spread/venue refusals |
| **The missed-EP tail read across all five buckets** | **YES, after one read-only capture** (blocked this session; the orchestrator runs it in seconds) | `mi_ep_missed_outcomes` with `setup_at_open = true`, tail share at 20 days per bucket, `ret_20d` not `max_high_20d` | ~½ session, $0 | scan-level buckets (outside_top20, score_below_50, rvol, mcap) have no ORB bars unless the name was an alert — the day-1 bracket on them needs a Polygon refetch ($0 marginal, subscribed) |
| the day-1 bracket on skipped HIGH alerts (what would the live bracket have done on names we skipped for OUR reasons) | **YES** | #1 — `campaigns_era_c.tsv` already walks all 270 alerts; join to `mi_live_trades.skip_reason` | ~½ session, $0 | the 87 open-at-horizon rows censor the mean; report settled + open marks separately |
| `stop_too_wide` → size down instead of skip | YES, small build | #1 with `validate_orb_entry` relaxed for those rows + the sizing formula at the wider stop | ~½ session, $0 | n is tiny (the bucket holds 8 rows all-time per the 09-01 count; 9 MAGNA53 rejects 05-05 → 08-14 per the 08-17 read) — a mechanism read, not a statistic |
| ADR-anchored day-1 stop with the target pinned (k sweep) × runner rule (joint) | YES, after extending #1 | #1 `RuleSet` + `stop_mode = adr_k` + `runner_rule`; era-matched; validate must stay PASS | ~1 session build + ~½ session sweep, $0 | slippage / auction fills; the same-bar stop-vs-target ambiguity abstains |
| the bull-regime read (`exit_tune_bull_regime_read`) | **RUN 09-02 (Phase 4)** on the 09-01 capture — methods (a)(c0)(c)(d)(e) + the partial priced on real fills; the #4 grid itself needs the fresh snapshot `_545p4_bull_capture.sql` produces | done offline, $0; grid re-run ~½ session after capture | it compares exit STACKS as much as tapes (era confound) — said on every row of Axis 6 |
| the n-milestone review (`exit_tune_cohort_review`, threshold 20 era-C closes) | NOT YET — era C has 4 closed | #4 | — | accrues by trading (~5 real closes/month) |
| ORB 5-min entry + independent stop | YES after extending #1 (entry-range mode) | #1 | ~½ session | the 5-min lane's `stop_too_wide` self-censoring does not apply to a replay |
| gap-over open entry on the EP-day high | NO — needs a setup definition from the operator (buy point + stop) first | #3 once defined | — | — |
| second partial higher up | NO — needs runners; the live book has one +3.69R close | #1 / #4 when runners exist | — | — |
| the forward out-of-sample read of the 0.75–1.0×ADR band | NEEDS CAPTURE — #616 built 09-02, **deploy pending** (verify 09-03); gate `delayed_entry_adr_stop_variant_616` at 30 trail-settled `ep_low_reclaim` fires | the live lane | — | ~6+ weeks of accrual |
| the lane's bounded re-entry rows | NEEDS ACCRUAL — first honest read ~09-23 (30 settled triggers) | the live lane | — | day-2+ only by ruling |
| the operator's own discretionary fills (TEAM-class) | NEEDS CAPTURE — TEAM 08-07 fill ($144.39, stop low-so-far) is recorded; its outcome is not yet written down in the repo (settles ~09-08 per the ledger) | manual | — | one fill is a fixture, not evidence |
| NBBO ask at submission | NEEDS CAPTURE (build) — nothing stores the ask; every entry-timing replay assumes fills the venue may refuse (#541 class) | capture-only build, operator scope | — | — |
| non-bull era-C live closes (the cell that breaks the regime/era confound) | NEEDS ACCRUAL — n=1 | trading | — | — |

---

## 7. THE PHASED, RANKED EXECUTION PLAN — for the operator to sequence

Each phase: the question · the harness · the cost to run · **the cost of the variant itself, in R,
stated beside its benefit** · the pass bar written before the run. Nothing here is a decision.

### Phase 0 — already running, nothing to do (cost 0)
- Live era C accrues (~5 closes/month); the recorder scores 34 candidate exits on every close.
- The delayed-entry lane records four rungs + bounded re-entries; **#616's ADR-stop variant
  columns are built and awaiting the deploy** (verify 09-03) — the band's forward test starts the
  night it deploys.
- Accrual clocks: `delayed_entry_shadow_first_read` (30 settled, ~09-23) ·
  `delayed_entry_adr_stop_variant_616` (30 trail-settled low-reclaim fires) · TEAM settles ~09-08 ·
  tier-3 labels ~mid-October · August fires readable ~late September.
- **Action: none** — except that `orb_5m_reentry_hybrid_replay` in `data_gated_reviews.yaml` should
  be marked run (08-09) so it stops counting as pending.

### Phase 1 — THE RETRY TEST (P1; $0; ~1 session; this weekend)
- **Question:** on the same 267 EPs, does a TIGHT stop with up to 3 tries beat ONE try at the
  0.75–1.0×ADR stop — measured per NAME at equal dollar risk per attempt?
- **Harness:** #3 (`_562_backfill_replay.py`) + an offline campaign loop re-driving the lane's
  re-entry logic (same_pattern / new_high_break / same-trigger re-arm). Its fidelity check —
  reproducing the lane's recorded re-entry rows — needs those rows pulled (Phase 2's capture);
  until then the loop is validated the way the grid was: the 602/602 first-attempt reproduction
  plus hand-walked campaigns from raw bars.
- **Grid:** stop ∈ {0.25, 0.50, 0.75, 1.00}×ADR · attempts ∈ {1, 2, 3, unlimited in the 20-session
  window} · exit ∈ {M-none, M-trail} · rung `ep_low_reclaim` first, then the other three.
- **Cost of the variant, in R:** worst case **−N R per name** (N attempts × 1R of dollars); the
  same-day read on 75 reconstructed trades saw retries fire on ~17% of names and 3–4 attempts add
  cuts without catches; the missed-cohort read saw unlimited re-entry double the failed-attempt cost
  (−7.5R vs −4.0R) for +0.6R net. Expect a 3-attempt column to carry a visibly worse worst-case
  drawdown than the 1-attempt column — that number is the deliverable, not a footnote.
- **Pre-registered outputs:** per-name total R · attempts fired · campaigns that spend every stop
  and never position · ≥4R campaigns · worst cumulative drawdown on one name · pooled AND ex-May ·
  drop-best-campaign. **August unreadable.**
- **Pass bar:** a (stop × attempts) cell beats the 1-attempt 0.75×ADR cell on total R ex-May at n≥30
  campaigns AND does not worsen the worst-name drawdown by more than the extra attempts' nominal
  risk. A cell that only wins pooled (May) is the same collapse every delayed-entry result showed.
- **What would kill it:** if 2–3 tight attempts merely reproduce one wider attempt's outcome at a
  worse drawdown, the retry idea is priced and closed — a legitimate end state.

### Phase 2 — THE MISSED-EP TAIL READ, own phase (P2; $0 + one read-only capture; ~½–1 session)
- **Why its own phase, not a grid cell:** it decides WHICH population enters the tactics grid — a
  selection question upstream of every tactic — and #595 only made it readable on 08-29
  (`setup_at_open`). The operator's "size down, not skip" hypothesis for `stop_too_wide` IS a grid
  cell (Axis 2) and runs on #1 inside this phase.
- **Question:** for each of the five skip buckets, restricted to names that actually gapped at the
  open, what share reached ≥4R-equivalent (≥20% at 20 days as the daily-grain proxy) — the TAIL,
  never the mean — and for the alert-level buckets, what would the live day-1 bracket have realized?
- **Harness:** the capture (`mi_ep_missed_outcomes`, `setup_at_open = true`, `ret_20d`) + #1 for
  the skipped HIGH alerts (already walked in `campaigns_era_c.tsv`).
- **Cost of the variant, in R:** admitting a bucket = its base rate of −1R losers per tail winner;
  at a 17–20% win rate the tail must average ≥4R — the read reports the ratio per bucket so the
  operator can see the cost side.
- **Pass bar:** a bucket whose tail share is ≥ the traded cohort's (26 live: 0 of 26 ≥4R; the n=194
  replay: 24 of 194 held a runner past the partial, median +1.98R) is a candidate for a P14 both-directions read; anything below is closed.
- **Traps carried:** `ret_5d` under-counts HTFL-class runs; `max_high_*` is MFE; scan-level buckets
  have no ORB bars → daily grain only, stated.

### Phase 3 — extend the day-1 owner, then the joint stop × target × runner sweep (P3; $0; ~1½ sessions)
- **Build:** `ep_replay.RuleSet` gains `stop_mode = adr_k` (k ∈ 0.5/0.75/1.0/1.25, target pinned to
  the ORB frame as live), `runner_rule` (the 13 rules from #2), and an attempt-2 leg (the same-day
  5-min-clear and next-day-open signals from #5). Re-run `validate` — **must stay PASS**; reproduce
  one headline from each of #2, #5, #8 on #1; then retire those three.
- **Question:** in the pinned-target frame, does an ADR-anchored day-1 stop repeat the day-2+ band
  finding — and what does each runner rule cost/give on the same era-matched campaigns?
- **Cost of the variants, in R:** a wider stop pays fewer R for the same move (on the rungs, ≥4R
  fires fell 30 → 7 from 0.75×ADR to 2.0×ADR); every runner rule that beat breakeven on n=194 did
  so by turning the median partial-taker from +0.33R into −0.33R and win rate 55% → 25–44%.
- **Pass bar:** era-matched, settled AND open-at-horizon reported separately, n≥30 per cell, holds
  ex-May, joint with the target — a stop that wins only because its R-unit grew is the 08-06
  mechanism and fails.

### Phase 4 — the review whose predicate is met, run inside this frame (P4; $0; ~½ session) — ✅ RUN 2026-09-02
- `exit_tune_bull_regime_read` — predicate 10 vs threshold 8 (verified in prod 09-02); methods (a)–(e)
  run on the entry-stamped Bull live closes against the era-A non-bull baseline, offline on the 09-01
  capture: `docs/analysis/exit_tune_bull_regime_read_2026-09-02.md`, findings in Axis 6. Verdict: the
  STOP conclusions transfer; the partial/trail/floor conclusions are era-confounded (Bull = B+C,
  non-Bull = A) and n cannot separate them; caveat re-worded; trigger re-keyed to Bull ≥ 20 AND
  non-Bull era-C ≥ 5. Remaining: the #4 grid on a fresh snapshot (`_545p4_bull_capture.sql`).
- `exit_tune_cohort_review` fires at 20 era-C closes (4 today) — no action.

### Phase 5 — accrual reads, on their own clocks (cost 0)
- ~09-23: first honest read of the lane (30 settled triggers) + the re-entry rows (Axis 5 forward).
- After #616 deploys + ~30 trail-settled low-reclaim fires: the band out of sample — the one test
  that separates a durable +0.19R/fire from a well-dressed survivor.
- Late September: August's 228 immature fires mature — the first non-May, non-stale expectancy read.

### Phase 6 — operator forks, only after a phase puts a number on the table (each = CHANGE_PROCESS + sign-off; nothing pre-decided)
| candidate that could emerge | from | cost shape the operator would weigh |
|---|---|---|
| a NAMED delayed setup: buy = the EP-low reclaim close, stop = entry − 0.75..1.0×ADR, trail exit | Phase 5 (#616 out-of-sample) | a new order-emission site; interacts with the 5-slot cap and daily-loss limit; day-2+ only |
| a retry rule (N attempts at a stated stop) | Phase 1 | up to −N R per name; the daily-loss safeguard attributes by close day |
| a size-down-not-skip rule for wide ORBs | Phase 2 | same dollar risk, smaller position; tiny n |
| an ADR-anchored day-1 stop in the pinned frame | Phase 3 | a stop level cannot ship dark — deploy is the flip; joint with the target |
| a runner rule other than breakeven | Phase 3 + era-C accrual | median trade +0.33R → −0.33R; a different book psychologically |
| the $40 catalyst re-grade (Stage 1b) | only if the operator wants the L/U band collapsed | ≈$40, ceiling $60, one run, cached forever |

**Sequencing rationale in one line:** Phase 1 is the only cell where a genuinely new answer exists
at $0 on data already captured; Phase 2 decides the population every later phase runs on; Phase 3
consolidates the harnesses while answering the day-1 half of the stop question; Phases 4–5 are
clocks; Phase 6 spends operator attention only where a number already exists.

---

## 8. What this card found to be WRONG or STALE in the brief and in prior statements

| claim | what the record shows |
|---|---|
| "the 5-min ORB re-entry replay (`orb_5m_reentry_hybrid_replay`) — never run" | **It ran**: 08-07 on n=15 (13 variants) and 08-09 on the full 17 (`_545_rerun_full17.py`). Fired 9 of 17, ex-THC −4.67R. The `data_gated_reviews.yaml` entry still says `status: pending` — the review ran and never closed |
| "all 14 closed live trades were taken in Correcting/Choppy/Crisis and ZERO in Bull" | true on 08-06, stale since 08-07 (3 Bull); 09-02 stamped n=26: **Bull 10** (14 by date-join). **The confound is ERA, not regime** — Phase 4 ran on it 09-02; the caveat is re-worded in Axis 6, the YAML and `ep_profitability_program.md` (PLAN #545's line still carries the old wording) |
| "compute R over `COALESCE(risk_dollars_actual, risk_dollars)`" (the 09-02 brief) | `risk_dollars` is the PRE-CAP budget (db.py:898); on the three notional-capped rows a full stop-out reads NET −0.32R / TEAM −0.50R / FTNT −0.55R. `risk_dollars_actual` = `shares × (orb_high − hard_stop)` (verified on both rows that carry it) and reconstructs for all 26. Exit reads use the recorder's realized per-share basis: best PLTR **+3.42R**, worst BW −1.09R, cohort −11.27R |
| "the stamp and the date-join disagree on 7 of 26" (the 09-02 brief) | **8** — FTNT (07-30, Crisis → Correcting) is the eighth. The mechanism is a one-session lag, not a revision: the stamp is the prior session's row, the join is the entry day's own close |
| "non-bull, live, era C — n=1 (SOLS 08-28)" (this doc, v2 first cut) | **CRWD**, not SOLS: SOLS is stamped Bull (08-27's row → joins Choppy), CRWD is stamped Choppy (08-26's row → joins Bull). Corrected in Axis 6 |
| "his retry idea… not yet tested" | same-day attempts 1–4 were swept 08-16 (n=75 reconstructed, per-name accounting, worst case bounded) and campaign policies R1/R2/R3 08-30 (missed cohort). **Untested = tight stop × attempts on the delayed rungs, per campaign, at equal dollar risk** — which is the cell Phase 1 runs |
| "reuse the three probes; a fourth now exists" | **ten** replay lineages exist (§5); one (the campaign walker) is outside the repo |
| "the giveback peak-lock (#306, built dark)" — implied open | **ruled OUT by the operator 08-11**; not an open cell |
| "the stop-floor — tested and REFUTED 08-06" | refuted in the frame where the +2R target moved with the stop; **that mechanism was removed on 08-16** (target pinned), so the pinned-frame question is open on day 1 — while on the day-2+ rungs the ADR band is the one thing that worked |
| `python scripts/check_analysis_doc.py <path>` | `main()` ignores its argument and checks only STAGED `docs/analysis/*.md`; this document was checked by calling `check(path)` directly (returns no problems) — and it lives in `docs/design/`, which the pre-commit gate does not scan |
| "we record every skipped-but-real setup" (`mi_ep_missed_outcomes`) | 66% of the table's rows never gapped at the open (#595); "real setup" now means `setup_at_open = true`, and the bucket counts quoted on the PLAN line (e.g. outside_top20 791 / 213 real / 18 ran ≥20%) already use that split |
| the shadow ORB control "0 winners in every month including two Bull months" (v1) | at n=38 the 5-min lane has 12 winners — all on daily-bar reconstructions; its real-time-accrued rows are −0.99R median. The v1 sentence is stale, the conclusion (geometry is not the lever) survived four reads |

---

## 9. What this does not answer

- **Any cell's expectancy under today's full stack** — era C has 4 closed live trades and 87 of 270
  era-C replay campaigns are still open at the horizon; the winners are, by construction, the rows
  not yet settled.
- **Whether the 0.75–1.0×ADR band survives out of sample** — ~104 cells per arm were scanned; the
  strongest cell is +0.19R/fire ex-May at n=70. Only #616's forward accrual (or a pre-May backfill)
  separates structure from survivorship.
- **Same-day re-entry on the delayed rungs** — the lane is day-2+ by the 08-30 ruling, so every
  lane re-entry figure understates same-day re-entry; the same-day reads that exist (n=15/17/75)
  are one-cohort and THC-carried.
- **The bull cell on its own terms** — every Bull close ran a different exit stack from every
  non-Bull close; the read exists (Phase 4) but cannot separate tape from stack until non-Bull era-C
  closes accrue (n=1).
- **Portfolio interaction** — slot competition, the 2% daily-loss limit attributing a re-entered
  name's two stops to one day, breakers. Every replay prices campaigns independently.
- **Fill reality** — spread (the #541 ask class), LULD halts, slippage beyond the modelled cent,
  our own impact. Every minute-bar replay assumes a fill the venue may refuse.
- **The operator's own tactic** — "looking at the low forming, turn back up" is not a rule; every
  proxy swept is a modelling choice, and a proxy underperforming him is expected, not a refutation.
- **Whether the EP COHORT is a winning cohort on OUR data** — 0 of 26 live trades ≥4R; the tail
  exists in the alert population and in the delayed rungs' MFE (25 of 130 low-reclaim fires TOUCH
  ≥4R at 0.75×ADR; 13 keep it on hold-only, 6 on the trail) — the harvest layer still gives back
  about half of what entry + stop finds. The thesis is not contradicted; it is not yet demonstrated
  on real fills.

---

## 10. ⚖ THE LINE

Nothing here changes a stop, a target, a trigger, sizing, a safeguard, a lane, or any live table.
No prod query was run beyond `live_rules.py`'s read-only toggle check (the one attempted capture
was blocked and is listed as Phase 2's first step). The retry test, the missed-EP read, the harness extension and the bull read are read-only
analysis; any resulting change is CHANGE_PROCESS + the #151 harness + operator sign-off, and the
one dollar item in this program (≈$40 Stage 1b) is the operator's stop-point, not this card's.

---
*Population statement (Gate 6): every figure names its rows and window in §2 and in its table row.
Sources: `scripts/ep_replay_data/` (09-01 capture: `mi_live_trades` closed magna53 rows,
`mi_ep_alerts` live-source, `mi_market_regime`, `mi_daily_closes`; `campaigns_era_c.tsv`,
`validate_trades.tsv`) · `scripts/probes/_562bf_*`, `_562grid_*`, `_562sp_*`, `_545_*` ·
`docs/analysis/` as cited per row · `docs/setups/exit_discipline.md`, `magna53_ep.md`,
`delayed_ep_reentry.md` (the CONTEXT LEDGER) · `data_gated_reviews.yaml` · v1
`docs/design/545_entry_exit_program_2026-08-07.md`. Related: PLAN #545 · #616 · #482 · #327 · #562 ·
#508 · #306 · #503 · #541 · #595.*
