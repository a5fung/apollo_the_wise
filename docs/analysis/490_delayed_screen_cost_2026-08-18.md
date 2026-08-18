# #490 — Is the delayed universe screen costing us real EPs? (2026-08-18, MEASURE-ONLY)

**One sentence:** No — on the honest denominator (crossers that still held ≥10% at the actual
open and pass our mechanical gates) the delayed screen's shadow watchdog has surfaced **zero
additional ≥8×ADR tail winners in 16 trading days (floor, windows incomplete)** while the alerted
population produced 2 over the same dates; the real tail winners among the crossers sit in the
**premarket-fade / built-after-the-open class that the 10%-at-entry floor excludes regardless of
data feed** — a floor-timing question (operator fork, a5680b5), not a delayed-data one.

⚖ **THE LINE:** the universe screen and the gap floor are entry discipline. This doc measures;
it proposes no threshold and flips no toggle. Advancing the #490 cutover ladder is the
operator's decision alone.
🔴 **Provisional per the GOAL-section rule (2026-08-18):** measured on the population the
current selector + floors produce; any material selection change re-opens this read.
**Right-censoring is severe: EVERY forward window is incomplete (median 8 of 20 sessions).
All ≥8×ADR shares below are FLOORS. Re-run after 2026-09-15**, when the last cohort day
(08-17) completes its 20-session window. Probe: `scripts/probes/_490_delayed_cost_funnel.py`
on the one-time 2026-08-18 capture (`scripts/probes/_490cost_*.tsv`,
`_490_funnel_capture.sql`) — $0, read-only, deterministic.

## Mechanism, verified on prod 2026-08-18

- `EP_RT_UNIVERSE_ENABLED=true`, `EP_RT_PASS2_ENABLED=true` (container env) — the Pass-0
  overlay and shadow watchdog ARE running (this corrects the working assumption that
  `EP_RT_PASS2_ENABLED` was unset; the substance stands unchanged:)
- `ep_rt_universe_authoritative` absent from `mi_safeguard_state` → default **off** →
  every Pass-0 catch is SHADOW-only, never admitted.
- `ep_rt_gap_down_authoritative`=on + `ep_rt_entry_gap_recheck`=on (both 08-02) → real-time
  data can only REMOVE candidates, never ADD them. Confirmed as described.
- `ep_rt_sustain_enabled`=on since 08-02 → catches after that date already passed the 3-bar
  sustain rule (they are levels, not single prints).

## The funnel (settled cohort: 2026-07-27 → 2026-08-17, 16 trading days = 0.76 months)

**261 raw `ep_rt_universe_catch` events → 246 settled ticker-days** (9 dupes deduped, 6 events
from 2026-08-18 excluded — no settled session yet; the FLXS example was one of these).
30 were alerted the same day anyway; **216 never alerted**; 68 had no delayed reading at the
tick. Mean rt_gap 14.0% vs mean delayed_gap 2.1%. Ticks span 07:00–09:55 ET, median 09:31.

**Stage 1 — did the gap hold to the actual open?** (open vs prev close, `mi_daily_closes`;
the open print is the proxy — minute bars are not persisted for never-alerted names)

| never-alerted crossers | n |
|---|---|
| held ≥10% at the open | **49 (23%)** |
| faded <10% at open but crossed 10% intraday later | 137 (63%) |
| never saw 10% again | 30 (14%) |

77% of the "misses" are premarket prints or in-session builds the 10%-at-the-open floor never
qualifies — e.g. JLHL 07-27 (rt 12.7% premarket) opened **+1.3%**. Split by tick: premarket
catches held 36/84; in-session (≥09:30) catches held only 13/132 — those are mostly names that
BUILT to 10% after opening below it. For context our own 30 alerted crossers held only 15/30.

**Stage 2 — the other mechanical gates** (replayed as-of the day: D-1 floors pre-cleared by
universe membership; extension ≥+50%/10cal-d; ADV$ median ≥$1M; ATR14 ≤15%; mcap ≥$500M from
`mi_market_caps` + a one-time yfinance fill): **49 → 32 survivors** (17 hit mcap, 7 ADV$,
3 extension, 3 ATR). NOT replayed at $0 — PM/session RVOL pace, the LLM catalyst grade +
score≥50 cut, the top-20 gap-rank cap — so **32 is an upper bound** on would-have-alerted.

**The scan log then removes the premise for most of them: 44 of the 49 held names appeared in
the delayed scan log later that same day** and were rejected on the merits — dominant reasons
`score < 50 (catalyst=routine)`, `pm/session_rvol_too_low`, top-20 cap, cooldown, M&A. The
delay changed WHEN the screen saw them, not WHETHER. The **pure delayed-invisibility class —
held at the open yet never in the scan log at all — is 5 names in 3 weeks**: COHU 07-30
(tailx-so-far 4.8, the only material one), CON, ZD (both ~1–2×ADR), OEC and SRZN (both fail
the $500M mcap gate anyway).

**Stage 3 — what they did** (the program's statistic: tailx = 20-session-forward max high vs
EP-day close in own-ADR units, identical to `_552_missed_why_cohort.sql`; every row censored,
so shares are floors; all sets share dates + censoring, so the comparison is fair):

| cohort (same window, same censoring) | n | ≥8×ADR so far | P90 | median | fwd med |
|---|---|---|---|---|---|
| **never-alerted, held open, passed gates** | **32** | **0 (0.0%)** | 4.2× | 1.2× | 8/20 |
| never-alerted, held open, pre-gates | 48 | 1 (2.1%) — ANIK, fails ADV$+mcap | 4.8× | 1.1× | 8/20 |
| never-alerted, faded-but-crossed | 132 | 3 (2.3%) — ALOY, BCAR, AMRC | 5.3× | 1.6× | 9/20 |
| alerted crossers | 28 | 2 (7.1%) | 5.9× | 1.7× | 8/20 |
| ALL live alerts 07-27..08-17 | 100 | 2 (2.0%) — BLZE, FET | 3.7× | 1.4× | 7/20 |

The would-have-alerted survivors are **no better than the alerted population on every tail
statistic** — and every ≥8×ADR winner the crosser pool has produced so far lives OUTSIDE the
honest denominator: ANIK (held, but our size/liquidity gates exclude it — the known 08-16
anti-selectivity, not a data-latency loss), ALOY/BCAR/AMRC (faded at the open — BCAR opened
**−2.5%** and still did 14.7×ADR), QMCO/INVX (opened 9.2%/3.0% — never crossers at the open).

## The prize, in the programme's terms (target: ~1 converted tail winner/month, ≈4 total)

- **Additional ≥8×ADR opportunities from flipping the universe screen to real time:
  0 per month measured so far** (0 winners / 0.76 months), vs 2.6/month already produced by
  the alerted population over the same window.
- Ceiling not yet closed: three survivors sit at 4.8–6.2×ADR with 8 sessions still to run
  (PLPC 6.2×, PGY 5.4×, COHU 4.8× — each 12/20). Even if all three converted, most would have
  been rejected by the unreplayed catalyst/RVOL gates; only COHU is in the invisibility class.
- **Censoring: 32/32 survivors (and 100/100 alerted rows) lack a full 20-session window** —
  none excluded, all flagged; the 09-15 re-read settles them.

## What remains untested

1. The catalyst grade + RVOL + top-20 gates were not replayed ($0 limit) — the true
   would-have-alerted set is ≤32, likely far smaller (44/49 were graded and failed).
2. The open print is a proxy for the 09:31–09:45 floor reads — minute bars are not persisted
   for never-alerted names (the same gap a5680b5 flagged).
3. The 137-name faded-but-crossed class (3 winners so far, incl. the ARGX-shaped fades) is
   the **floor-timing fork** (re-check later / sustained-cross), already surfaced to the
   operator on 08-16 — a delayed-vs-real-time flip does not reach it, because
   `ep_rt_entry_gap_recheck` removes sub-10%-at-entry names under the current rule regardless
   of feed.
4. Conversion (would a COHU-class alert have been entered and exited well) — selection-only
   read here.

## Appendix — probe output

Full stdout: run `python3 scripts/probes/_490_delayed_cost_funnel.py` (deterministic on the
captured TSVs). Survivor-level detail (all 32 names with tailx-so-far) is printed by the probe.
