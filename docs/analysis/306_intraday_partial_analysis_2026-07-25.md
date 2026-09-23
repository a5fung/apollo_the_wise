# #306 — Intraday partial-profit + breakeven stop: what the operator's rule would have done

**Date:** 2026-07-25 (PT) · **Status:** EVIDENCE + reading for operator ruling — changes NOTHING live. Per CHANGE_PROCESS rule 3 the parameter reads below are **my reading; the ruling is the operator's.** No trigger level is declared "correct."
**Rule under test (operator's words):** when a position is up to some level INTRADAY — a percent gain, or a gap-up / a level above a point in the stock's history — sell ~1/3, move the stop on the rest to breakeven.
**Scope-add (operator, mid-card):** the trigger BASIS is the central question — fast/gappy names likely need more aggressive profit-taking than slow large caps; a single fixed level across the universe is probably wrong by construction. Bases compared: fixed-% vs R-multiple vs ADR-multiple, plus character segmentation.
**Parent:** #306 (exit tune) · #503 (0-for-9 forensic). Routes to those tasks only — no new tasks proposed.

## 0. Data + method (all offline, re-runnable)

- **Cohorts:** the 9 closed live trades (7/06–7/24, −8.37R deployed-risk basis; the headline −7.50R is the budget basis — same #503 §4 distinction) + SMCI (open) + the 32 closed-with-fill paper trades 4/17–7/02 (CRMD excluded from R aggregates: inverted stop, risk/share ≤ 0).
- **Intraday paths reconstructed from Polygon 1-minute bars** (`mi_intraday_bars` does not cover the trade days), fetched read-only through the apollo-market container using the same endpoint `collector.get_minute_bars` calls, cached at `scripts/probes/_306_bars_raw.tsv` (+ `_306_trades_live.tsv`, `_306_trades_paper.tsv`, `_306_caps.tsv`). Probe: **`scripts/probes/_306_intraday_partial_sim.py`** (pure offline replay of the caches).
- **Sim contract (conservative):** RTH bars only; trigger scan starts at the first bar ≥ `filled_at` (fill-bar spike can't self-trigger) and ends before the actual exit minute (no post-exit rebound triggers — this matters: HUT hit +3.4% AFTER its stop-out and is correctly NOT credited); partial fills AT the trigger (limit assumption, no slippage credit); BE stop fills at entry, or at the bar OPEN when price gaps through (MANE d2 confirms realism: the counterfactual BE fill = 119.04 = the real gap-open fill). Same-bar trigger+BE ambiguity resolved pessimistically and counted (≤2 cases, only at the 2%/0.5R levels). Real exit legs before/after the counterfactual events replay at correct scale; multi-attempt rows (paper TEAM) replay the final attempt only, in deltas, so merged prior-attempt P&L cancels.
- **ADR20** = mean (high−low)/close over the 20 sessions ENDING THE DAY BEFORE the fill — flag_detector's sourced-range convention (`_HTF_MIN_ADR_PCT` companion), shifted pre-entry so the gap day doesn't inflate the denominator. Market cap = Polygon reference, as-of-fetch (tiering only).

**Corrections to #503 found (verify-against-primary):** `highest_price_seen` is blind on sub-10-minute holds (seeded at fill, 5-min polls). Minute paths show **CRCL's MFE was +3.12% / +1.62R** (peak 72.855 at 9:37, BEFORE the 9:40:34 stop-out — the forensic's "MFE 0.00, post-stop pop to 72.86" is wrong: the pop was pre-stop) and **WDFC's was +0.71% / +0.23R** (not 0.00). WULF's true MFE is $25.15, $0.14 above the stored 25.01. The forensic's MFE zeros stand only for TSEM and (bounded by a 51-s hold) HUT. Net effect: the exit-side case is *stronger* than #503 stated — 3 of 9 closed (4 of 10 with SMCI) saw ≥ +1.6R intraday.

## 1. The intraday paths (fill → exit, minute-level)

```
tkr   fill ET      hold      MFE%  MFE_R min→peak peakday  shape
WULF  07-06 09:33   0.4h    2.15   0.65     15      1     dipped under entry 9:34, rallied +2.2%, stopped 9:57
CRCL  07-10 09:31   0.2h    3.12   1.62      6      1     straight up 6 min, then −4% collapse in 3 min to stop
WDFC  07-10 09:31   0.2h    0.71   0.23      1      1     1-min pop, then straight down
TSEM  07-14 09:32   0.2h    0.00   0.00      –      –     never above fill (fill = day's top tick)
MANE  07-15 09:33  24.0h    8.76   7.92    201      1     +7.3% by 9:46, peak 12:54, held gains to close, d2 GAP-DOWN open 119.04
HUT   07-20 09:31  51s      ~0     ~0       –      –     stopped in 51 s (re-crossed trigger later — post-exit, not creditable)
SMCI  07-22 09:33  open    10.57   3.21   1625      2     chop d1 (BE-touch 9:36), ran d2 to 32.585, faded d3 to BE 10:40
NVCR  07-23 09:32  30.1h   12.01   2.00   1438      2     dipped under entry 9:33 d1, recovered, d2 gap +3.5% to 21.45 by 9:31, bled ALL DAY to stop
THC   07-24 09:31   3.2h    2.13   0.64     40      1     +2.1% in 40 min, faded to stop 12:43
WKC   07-24 09:33   2.5h    2.59   0.90     31      1     +2.6% in 31 min, faded to stop 12:02
```

Two path families: **(a) fast pop-and-fade** — 6 of 9 peaked within 40 minutes of fill and died the same day; **(b) day-1 runner reclaimed on day 2** (MANE, NVCR, and open SMCI). Both families put their peak where only an INTRADAY mechanism can see it — no daily close ever ratified these peaks (best closes +3.65%/+4.39%/+5.87%), which is the closes-based `giveback_floor` arm-gap already documented in #503 §3.

## 2. The sweep — sell 1/3 at L, stop to breakeven

Net cohort R (deployed-risk basis), live closed 9, actual −8.37R. `bene/cost` = Σ positive / Σ negative per-trade deltas:

```
basis  level trig_n BEscr    netR      ΔR   bene   cost  triggered per-trade Δ
pct       2%      6     5   -1.57   +6.80  +6.80   0.00  WULF+1.20 CRCL+1.35 MANE+0.68 NVCR+1.11 THC+1.21 WKC+1.26
pct       3%      3     2   -4.70   +3.67  +3.67   0.00  CRCL+1.53 MANE+0.98 NVCR+1.17
pct       5%      2     1   -5.51   +2.86  +2.86   0.00  MANE+1.58 NVCR+1.28
pct       8%      2     1   -4.44   +3.93  +3.93   0.00  MANE+2.49 NVCR+1.44
pct      10%      1     1   -6.82   +1.55  +1.55   0.00  NVCR+1.55
pct      15%      0     0   -8.37   +0.00      —      —
R       0.5R      6     5   -2.26   +6.11  +6.11   0.00  WULF CRCL MANE NVCR THC WKC (~+1.2 each)
R       1.0R      3     2   -5.29   +3.08  +3.08   0.00  CRCL+1.34 MANE+0.41 NVCR+1.33
R       1.5R      3     2   -4.79   +3.58  +3.58   0.00  CRCL+1.51 MANE+0.58 NVCR+1.50
R       2.0R      2     1   -5.96   +2.41  +2.41   0.00  MANE+0.74 NVCR+1.67
R       3.0R      1     0   -7.30   +1.08  +1.08   0.00  MANE+1.08
adr     0.5A      4     3   -3.71   +4.67  +4.67   0.00  MANE+1.17 NVCR+1.14 THC+1.18 WKC+1.18
adr     1.0A      2     1   -4.83   +3.54  +3.54   0.00  MANE+2.26 NVCR+1.28
adr     1.5A      1     1   -6.93   +1.44  +1.44   0.00  NVCR+1.44
adr     2.0A      1     1   -6.81   +1.56  +1.56   0.00  NVCR+1.56
```

Read this table with both hands:

1. **Direction is unambiguous: any intraday profit-protection beats the current nothing on this cohort** — every basis, every level that triggers at all, is +1.1R to +6.8R better, and `cost = 0` everywhere.
2. **`cost = 0` is structural, not evidence.** A 0-for-9 cohort cannot price the rule's downside — every trade died at −1R, so any early sell can only help. The cost lives in the winner cohort (§3).
3. **The spectacular low rows are top-tick curve-fit.** The +2% / 0.5R rows (Δ ≈ +6.8/+6.1) work because four trades peaked at +2.13–3.12% — a +2% trigger "sold" within ~1% of the absolute top of dead-cat bounces. That coincidence will not generalize; on the paper cohort the same levels scratch 12 of 15 triggers and cost the winners the most (§3).
4. **Fragility at the edges:** NVCR's +2R capture triggers by $0.0006 (peak 21.4506 vs trigger 21.45) — the 2R row's second-best status flips off with a 3-cent path change. Do not read level rankings at n=2 triggers.
5. **SMCI (open, the live instance):** actual = still open, 7/24 close +0.65R unrealized, stop still −1R. EVERY variant banks +0.30R…+1.00R and BE-scratches the rest on 7/24 10:40 — i.e. the rule converts an open −1R-risk position into a locked +0.3…+1.0R. (The Day-3/5 partial machinery reaches SMCI Monday 7/27 — this is #503's "live instance" clock still running.)

## 3. The cost side — what the rule does to real winners (paper cohort)

Paper closed n=31 (risk-valid), actual −17.71R. The 10 winners sum to **+12.23R actual**; winners held 4–24 days. Rule replayed on their minute paths:

```
level      winners triggered   BE-scratched mid-hold      winner-cohort Δ
pct 3%         10 / 10          6  (S-day: 1,1,2,2,3,8)       −2.46R  (−20%)
pct 5%          9 / 10          4                             −0.65R
pct 8%          8 / 10          4                             +0.31R
pct 10%         8 / 10          4                             +1.43R
R   1R         10 / 10          6                             −4.53R *  (−1.25R excl. degenerate-stop KURA/GOOGL)
R   2R          8 / 10          3                             +0.12R *  (+0.20R excl.)
adr 1A         10 / 10          4                             +1.27R
adr 2A          8 / 10          3                             +3.84R
```
\* KURA (risk 0.8% of entry) and GOOGL (0.8%) carry pre-current stop conventions — an R-trigger there fires on noise (GOOGL 1R = +0.8%, triggered day 1, scratched day 1 of a 17-day +3.8R run: Δ −3.48R alone). Live stops (ORB low / prior-day low) run 1.1–6.0%, so these two say little about live R-basis behavior; excluded variants shown.

The operator's stated worry — **"a breakeven stop on day 1 of a 16-day run is a real risk" — is confirmed, quantified:** at +3%, all 10 winners trigger (8 on day 1) and **6 of 10 are BE-scratched on days 1–8 of holds that actually paid up to +3.8R.** Worst cases: CRSR triggered AND scratched day 1, missing its +12.9% day-2 gap (−1.57R); RCAT scratched day 2 of an 8-day +1.24R run (−1.04R); BW was never scratched but the early 1/3 partial dragged a +3.83R winner to +2.86R (−0.97R). That is the second cost component: even scratch-free, selling 1/3 of an eventual big winner at +3% costs ~⅓ × (final − trigger).

Two honest complications:

- **The scratch is not always a cost.** Half the scratched winners' REAL exits also surrendered most of their MFE (QURE actual +0.49R vs cf +0.34…+0.68R; KURA actual +0.13R vs cf +1.28R — the scratch beat reality). The current ladder is itself leaky, so "scratched winner" ≠ "lost winner" in this system as it stands.
- **One trade dominates the loser-side benefit.** SYRE (−4.57R overnight gap-through-stop) is dodged by any low/mid trigger (Δ +4.6…+4.9R) — that single dodge exceeds the entire net paper improvement at pct-3% (+3.71R) and R-1R (+5.36R excl. degenerates). Remove SYRE and pct-3% goes NEGATIVE. **The ADR-basis mid levels are the only variants whose paper benefit does NOT depend on the SYRE dodge** (SYRE never reaches 1×ADR; the full-paper adr-1A +2.11R and adr-2A +5.89R are SYRE-free) — they win by triggering high enough to skip noise scratches while still catching runners.

**Net-net across both cohorts** (live 9 + paper 31, actual −26.08R): every basis's best level improves the total by +3 to +9R, and the overall frontier peaks at levels that differ by basis (pct: 2% then 10%; R: 1R; adr: 2A). At this n, the frontier's SHAPE (u-curve: low levels rescue dead cohorts, high levels protect winners) is a solid finding; its ARGMAX is not.

## 4. The central fork — trigger basis, and does R already solve character? (scope-add)

Character spread of the live cohort (the operator's premise, confirmed): ADR20 runs **2.6%–9.7%** across the 10 names. A fixed +8% trigger is therefore 0.9×ADR on WULF but 3.1×ADR on WKC — the same number is an easy day for one stock and a career day for another. **Fixed-% is wrong by construction on this universe**, exactly as the operator suspected.

**Does R-basis already fix it?** Partially at best — and this cohort measures it directly. Stop distance (entry − hard_stop, the R denominator) as a fraction of ADR20:

```
tkr    ADR20  risk%  risk/ADR      tkr    ADR20  risk%  risk/ADR
WULF    8.5%   3.3%    0.39        HUT     9.7%   2.0%    0.20
CRCL    7.2%   1.9%    0.27        NVCR    5.1%   6.0%    1.19
WDFC    2.8%   3.1%    1.12        THC     3.5%   3.3%    0.95
TSEM    6.8%   2.8%    0.41        WKC     2.6%   2.9%    1.11
MANE    7.3%   1.1%    0.15        SMCI    6.0%   3.3%    0.55
```

The ORB low is one 30-minute morning range, not the stock's personality: risk/ADR spans **0.15×–1.19×** (8×). Concretely, +2R on MANE = a +2.2% move on a 7.3%-ADR stock (hair-trigger), while +2R on NVCR = +12% on a 5.1%-ADR stock (needs the run of its life — and cleared the trigger by half a cent). **R-basis inherits the day's stop geometry, not the stock's character; it does NOT dissolve the operator's problem, so the "simple answer" (use R and skip segmentation) is not supported.** Its real virtue is different: it speaks the account's risk language and is already wired everywhere.

**ADR-multiple** is the fullest normalization, the machinery is trivial (the ADR convention already exists in `flag_detector`), and it is the only basis whose paper-side benefit survives removing SYRE (§3). On the live side 1×ADR captures both real runners near their peaks (MANE trigger +7.3%, Δ +2.26R; NVCR +5.1%, Δ +1.28R) using ONE parameter across a 2.6–9.7% ADR spread — which is precisely what the operator's per-character intuition asks a trigger to do without needing named segments.

**On reusing `character_profile()` (scope-add item 3):** checked before proposing anything — it profiles a different axis. It computes MA-respect personality (home MA among SMA10/EMA21/SMA20/SMA50, pullback undercut depth p80, episode durations) for TRAIL placement, consumed by pivot_stop_shadow. It contains no run-rate/velocity notion. The fast/slow axis the operator means IS ADR%, and that convention already exists (`flag_detector._HTF_MIN_ADR_PCT` companion math). **Recommendation of frame, not parameter: key the trigger off ADR20; no new taxonomy needed; `character_profile` stays a trail-side tool.**

**Segmentation by character (cap / ADR tier / gap):** the full per-trade table is in the probe output. Every cell is n ≤ 4 except gap≥10% (n=8): per-segment level choices are **unsupported at this n — stated per cell in the probe, not smoothed over.** What the segmentation DOES show even at n=9: the two trades a fixed +5% trigger catches are both mid-cap; all three ADR<4% names peaked under +2.7% (their scale is different, as predicted); and ADR-normalized MFE clusters tighter (0.25–2.4 ADR units) than %-MFE (0.7–12%) or R-MFE (0.2–7.9R) among trades that moved at all. The frame is right; populating it needs on the order of ≥20 *triggered* trades per tier — months of live cadence, or pooling future paper flow. Until then a continuous normalization (ADR-multiple) gives the segmentation's benefit without estimating per-cell parameters.

## 5. The structural variant — "gap up, or above a point in history"

**Pre-entry structure produced ZERO partials on this cohort, and the reason is geometric, not statistical.** For each live trade, where the nearest structural levels sat relative to entry: prior-day high — BELOW entry for 10 of 10 (gap-day entries clear it by construction); pre-entry 20-day high — below entry for 4, and +10% to +26% above for the other 6; 52-week high — below entry for 3 (NVCR/WKC/WDFC broke out through it AT entry), +2.3% above for THC (peak +2.13% — missed by 0.16%), and +10 to +272% above for the rest. Nothing was ever reached: **net R unchanged at −8.37.** An EP entry either already stands above nearby structure or sits far below the prior high — there is rarely a usable level in the +3–10% band where profit-taking lives. n=9, but this follows from the setup's definition (gap + ORB breakout), so I'd expect it to hold.

**Gap-up-open variant** (day ≥2 opens ≥G% above prior close, above entry → sell 1/3 at the open): fires on 6 of 41 trades at G=2% (live: NVCR d2 +3.5% open — banking +1.33R at what proved to be within pennies of its best price of the day; paper: CRSR d2 +12.9% → +6.22R level, FTRE +1.54R, FPS +1.22R, PURR +0.56R, IBM +0.44R). When it fires it banks near local tops (mean level ≈ +2R), but it fires on ~15% of trades and cannot be the primary mechanism — MANE, the cohort's biggest MFE, gapped DOWN on day 2 and gets no protection. **Read: structural triggers are a plausible COMPLEMENT (sell-into-day-2-gap), not a substitute for a level trigger; at n=6 fires, underdetermined beyond that.**

## 6. What is underdetermined (plainly)

1. **The trigger level within any basis.** Live rankings ride on 1–3 triggering trades (NVCR's 2R capture margin: half a cent); live and paper cohorts prefer OPPOSITE ends of the level range (u-shaped frontier, §3). No level is separable from noise at n=9+31.
2. **Whether 1/3 is the right fraction, and whether BE is the right stop destination** — not swept; single-variant rule as the operator stated it. (A stop at trigger−1×ADR instead of BE would change the scratch numbers materially; untested.)
3. **Per-segment levels** — every character cell is n ≤ 4.
4. **The winner-cost estimate's external validity** — the 10 paper winners span Apr–Jul across different regimes and old stop conventions; 2 of 10 have degenerate stops; FPS's exits are only partially recorded (28 of 163 shares — consistently on both sides of the comparison, but it under-weights one winner).
5. **Regime interaction** — this rule was tested on a Choppy/Correcting live cohort; in the Bull calibration (winners 13% ≥ +3R) low triggers + BE would tax exactly the trades that fund the yearly expectancy. Nothing here measures that.

What is NOT underdetermined: (a) zero profit-protection on days 1–2 measurably threw away +1.6 to +3.9R on this one 3-week live cohort (MANE+NVCR+CRCL at any mid-level trigger, before counting SMCI); (b) the peaks live intraday, not at closes — a close-armed mechanism structurally cannot see them; (c) fixed-% triggers are mis-scaled across this universe's 2.6–9.7% ADR spread; (d) R-triggers inherit ORB geometry (0.15–1.2× ADR), not character.

## 7. Build-gap note (feasibility, not a design)

Most plumbing exists; the gap is the ACT layer, not price access:

- **Price path:** `highest_price_seen` is already maintained intraday — websocket seed at fill (`trade_stream.py` ~804) + `track_open_position_extremes` 5-min Polygon polls (`order_manager.py` ~3730). A trigger evaluator can piggyback the same 5-min cadence (worst case one poll late ≈ the conservative side of this sim); sub-minute latency would need the quote stream, which is NOT currently consumed for open-position monitoring.
- **Partial-sell path:** exists but is day-gated — `live_tracker.run_partial_exits` (live_tracker.py:691) via the 15:45 ET `partial_exit_scan` (#361). It already solved the hard part (replace the resting stop FIRST so qty_available frees, then sell — the ~0.2 s settle). Generalizing it to fire at an arbitrary intraday time is the main new code.
- **Stop-to-BE:** `update_stop()` is the authorized stop writer (trade-state-ownership doc); `breakeven_active` and `partial_taken` columns already exist on `mi_live_trades` (the Day-3/5 ladder uses them). A BE floor composes with the existing `effective_stop = max(...)` exactly like the dormant `giveback_floor` hook (exit_logic.py:78) — same wiring point, same one-more-max()-input pattern.
- **Genuinely missing:** (1) the intraday trigger evaluator on open positions (compute trigger price per basis at fill, compare on each extremes-poll tick); (2) the intraday-partial submit path (generalize run_partial_exits' stop-replace-then-sell out of its 15:45 window, with idempotency against re-fires); (3) safeguards review — an intraday sell is a new order-emission site and must carry the mode-bound client-order-ID + account-mode invariants (dual_account SSoT) and a `docs/setups/` change via CHANGE_PROCESS with operator sign-off. **This touches live trade state — THE LINE: nothing here moves without the operator's explicit ruling.**
- Relation to the existing #306 fork: the operator's rule and the dormant giveback hook need the SAME new intraday plumbing; they differ only in the ACTION (sell-1/3+BE vs raise-floor). This cohort's evidence (peaks invisible to closes) bears on that arm-basis fork identically.

## 8. Bottom line (my reading — operator rules)

The mechanism direction is supported by everything measured here: intraday peaks existed, died unprotected, and any version of the operator's rule recovers +1 to +4R of the −8.37R live cohort while costing the paper winner cohort −4.5R (low R triggers) to +3.8R (high ADR-scaled triggers). The basis question has a clear structural answer — **ADR-multiple is the right frame** (fixed-% mis-scales 3× across the universe; R-multiple inherits one morning's range, 0.15–1.2× ADR) — and ADR mid-levels (~1–2×ADR20) are the only variants that look good on BOTH cohorts without leaning on a single catastrophe dodge. The trigger LEVEL itself, the 1/3 fraction, and per-segment tuning are underdetermined at n=9(+31) and I decline to pick them; if the operator wants a next evidentiary step, the cheapest is running this exact replay as a SHADOW (log-only) on live positions — it needs only the evaluator, no order path, no strategy change — and lets the level frontier populate itself on real cohort flow.

**Probe:** `scripts/probes/_306_intraday_partial_sim.py` (offline; caches in `scripts/probes/_306_*.tsv`). Full tables in probe stdout.
