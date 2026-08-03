# Stop-width replay — would a wider EP stop have produced a better result? (2026-08-03)

**Verdict in one line: the stops ARE tight (0.6–0.85× ATR, 4 of 5 stop-outs inside the first
30 minutes) and widening them does buy a higher win rate — but every net-R gain in every sweep
is carried by ≤5 outlier trades, the median trade is unchanged or worse, and on the 12 real live
trades every loser eventually died under every width tested. The sample cannot support a
stop-geometry change; the measurable leverage sits in exit/harvest timing (#508 territory),
not stop width.**

> **THE LINE — this document is EVIDENCE, not a change.** Nothing here authorises touching the
> stop, sizing, entry, or any safeguard. Any stop-geometry change is a detection/criteria change
> requiring the operator's sign-off, the discipline in `docs/setups/CHANGE_PROCESS.md`, and a
> backtest with N≥10 read together with this doc's limits. No live behaviour was modified in
> producing it (read-only replay of prod data).

Script: `scripts/stop_width_replay.py` (reads cached prod pulls `scripts/_stopw_*.tsv`,
gitignored; re-pull queries in the script header). Question raised from live EP losses through
2026-08-01; prior kill test found only ~1 in 4 losers ever traded back above entry the same
session.

---

## 1. What was replayed

Current geometry: entry = stop-limit buy at ORB high (9:30 ET 1-min bar), stop = ORB low,
submission window 9:31–9:44 ET.

**Risk held constant.** Every variant is scored in R-multiples of its own stop distance
(risk budget / distance = shares). A full stop-out is −1R under every variant; a winner's R
shrinks mechanically as the stop widens (same price move, bigger denominator). This is the
frame that stops "wider is better" from collapsing into "more size is better".

**Two cohorts, never merged:**

| Cohort | What it is | N | Evidence weight |
|---|---|---|---|
| A | Real closed trades with full entry-day minute bars, replayed from the actual fill time/price | **21** (12 live + 9 paper, all magna53) | What actually happened; tiny N |
| B | Distinct HIGH alerts replayed as simulated ORB entries (fill at ORB high, no slippage) | **162** (of 327 alert-days) | Bigger N; simulated, weaker as live evidence |

Cohort accounting (why not "35 trades / 300 alerts"):
- 46 closed trades → 21 replayable. 13 of the "35 with bars" have only the single 9:30 ORB bar
  stored (capture gap, late-May–June paper era) — unreplayable; 1 more (CRMD) has entry below
  ORB low (broken geometry row); rest have no bars.
- 327 distinct HIGH alert-days → 74 no minute bars, 42 partial capture (missing the 9:30 bar or
  the close), 49 never triggered the ORB buy in 9:31–9:44 (no trade under ANY variant — no bias).
  Replayed 162; **135 of them are May 2026** — one market era. No-bars exclusions look similar on
  gap% (median 15.0 vs 15.9) with mildly higher ep_score (72 vs 64) — mild, stated, not corrected.
- 33 of the 162 overlap a closed real trade (kept; cohort B is a mechanics simulation).

**Variants** (stop below entry; D0 = entry − ORB low = current distance):
`orb_1.25x/1.5x/2.0x` = entry − k·D0 · `atr_0.5/0.75/1.0` = entry − m·ATR14 (cohort A: the
recorded live atr_14; cohort B: mean of last 14 Wilder TRs strictly before the alert day — what
the 9:31 live path can see) · `pdl` = prior day's low (the 9M geometry).

**Two settle horizons, both reported** (no profit-taking rule in either — stated limit):
- **Day-0**: stop touch (minute-bar low) or exit at the 16:00 close.
- **Day-5**: day-0 survivors walk daily bars 5 forward days; overnight gap through the stop
  fills at the OPEN, not the stop (the honest #327-class loss); else day-5 close.

**Split-adjustment guard** (found during validation, worth recording): `mi_intraday_bars` is
as-traded at capture time; `mi_daily_closes` is retroactively split-adjusted. DLLL 2026-05-22
trades at $88 in minute bars, $13 in the daily series (8:1), also SNEX (3:2), MVLL (3:1).
Every daily-derived quantity (prior-day low, ATR, the day-1..5 walk) is rescaled to entry-day
minute units per ticker; without this, DLLL showed a fictitious −43.7R "gap-through".

---

## 2. The operator's suspicion, measured

- Current stop distance / ATR14: **median 0.60×** (cohort B), **0.84×** (cohort A). The stop
  does sit at roughly half-to-0.8 of a typical day's range. Median distance ≈ 3–4% of entry.
- Baseline day-0 stop-outs fire early: **81%** within 30 min of open (cohort B, 85/105);
  **78%** live (7/9).

The premise is confirmed. The question is whether widening pays. It does not, robustly:

---

## 3. Cohort A — the 12 real live trades (plus 9 paper)

Replayed baseline vs actuals first (uniform mechanics; live exits included partials, moved
stops, manual/next-open closes — so replay ≠ actual on some rows):

```
                     actual   replay-base      orb_2.0x
 live trade          R        d0      d5       d0      d5
 WULF   07-06        -0.70   -1.00   -1.00    -1.00   -1.00
 WDFC   07-10        -0.80   -1.00   -1.00    -1.00   -1.00
 CRCL   07-10        -0.81   -1.00   -1.00    -1.00   -1.00
 TSEM   07-14        -1.05   -1.00   -1.00    -1.00   -1.00
 MANE   07-15        -0.11   -1.00   -1.00    +1.76   -1.00   (rescued d0, dead day 1)
 HUT    07-20        -0.98   -1.00   -1.00    -1.00   -1.00
 SMCI   07-22        -0.68   +1.10   -1.00    +0.55   -1.00   (d0 winner, gave it back)
 NVCR   07-23        -1.07   +0.73   -1.00    +0.37   -1.00   (d0 winner, dead day 1)
 THC    07-24        -0.81   -1.00   -1.00    -0.53   +0.81   (the ONE d5 rescue)
 WKC    07-24        -1.18   -1.00   -1.00    -1.00   -1.00
 QBTS   07-27        -0.92   +3.17   -1.00    +1.58   -1.00   (+3.2R at d0 close, dead day 1)
 FTNT   07-30        -0.55   -1.00   -1.00    -1.00   -1.00
```

Sweep (paired vs baseline on the same trades; dTotR = variant total R − baseline total R):

```
 LIVE n=12        day-0 settle                 day-5 settle
 variant     stopped rescued  totR   dTotR    stopped rescued  totR   dTotR
 orb_1.0x       9       -     -4.0    —         12       -    -12.0    —
 orb_1.25x      8       1     -1.2   +2.8       12       0    -12.0   +0.0
 orb_1.5x       8       1     -2.3   +1.7       12       0    -12.0   +0.0
 orb_2.0x       7       2     -3.3   +0.7       11       1    -10.2   +1.8
 atr_1.0        7       3     -5.8   -1.8       11       1    -11.0   +1.0
 pdl            0       9     -1.8   +2.2        6       6     -7.6   +4.4
```

**Reading — the live losers were not noise-outs:**
- At the day-5 horizon **every live trade ends −1R under the current stop AND under 1.25×/1.5×**;
  2.0× rescues exactly one (THC, +0.81R). Ten to eleven of twelve names went down and stayed
  down. Widening buys the same −1R, later.
- Even prior-day-low — a stop 17% below entry, 5.6× wider — still loses −7.6R on 12 trades,
  and 6 of its 12 stop out anyway within 5 days.
- The day-0 numbers show the REAL pattern: three baseline trades (SMCI +1.1R, NVCR +0.7R,
  QBTS +3.2R) were GREEN at the day-0 close and all three were dead by the next morning. The
  giveback is an exit/harvest failure, not a stop-width failure — no width fixes it.
- Paper (n=9): day-0 mildly positive for 1.25–1.5× (+0.6/+0.8R), day-5 negative for every
  variant (−0.9 to −4.8R). Same shape.

---

## 4. Cohort B — 162 simulated HIGH-alert entries

Headline slice = **executable geometry** (baseline stop distance ≥ 1% of entry, n=147). The 15
sub-1% rows are micro-ORB lottery tickets (CCUP 0.56%, ETHD 0.51%…) where constant-risk sizing
implies notional >100× the risk budget, inside microcap bid-ask noise, on names the live
pipeline's mcap/ADV filters would mostly refuse — their R numbers are arithmetic, not trading.
(Unsliced tables in the script output; same conclusions, more extreme concentration: the top-5
day-0 winners are 99% of the whole cohort's +110R total.)

```
 EXEC n=147            day-0 settle                          day-5 settle
 variant    win%  stopped resc rescEndR  dTotR  dTotEx5    stopped resc  dTotR  dTotEx5
 orb_1.0x    32%    95      -      -      —       —          121     -     —       —
 orb_1.25x   41%    78     17   +0.47   +28.6    -6.5        112     9   +35.5   -16.6
 orb_1.5x    43%    72     23   +0.39   +20.2   -14.2        102    19   +31.0   -18.5
 orb_2.0x    47%    59     36   +0.27   +12.5   -14.7         90    31   +12.6   -25.7
 atr_1.0     45%    66     31   +0.53    +7.3   -13.9        111    12   -14.8   -47.2
 pdl         53%     3     92   -0.13    -5.6   -15.5         30    91    -2.6   -17.4
 (dTotEx5 = paired delta after dropping that variant's 5 best per-trade deltas
  rescEndR = median end-R of the rescued trades, in the variant's own R units)
```

**Reading — the gain is real only in the tail:**
- Win rate genuinely rises with width (32% → 47%): the rescues are real trades that really
  came back. **But the marginal rescue is small** — median end-R of rescued trades falls from
  +0.47 (1.25×) to +0.27 (2.0×) — while **every surviving winner shrinks** by exactly the width
  factor (0.80 / 0.67 / 0.50).
- **Every positive dTotR flips negative when the 5 best deltas are removed.** Per-trade, the
  variant loses to the baseline about twice as often as it wins (e.g. 1.25× day-0: 24 up / 52
  down) — many small winner-shrink losses paid for a few big rescue wins. Symmetric-trimmed
  deltas (drop 5 best AND 5 worst) are ±small single digits over n=147 — noise.
- Median per-trade delta is 0.00 for every ORB multiple (the modal outcome is stopped-both-ways,
  a −1R tie).
- **ATR-anchored stops are the worst way to widen**: they hand the most width to exactly the
  wrong trades. The biggest winners have tight ORBs (CCUP: ORB distance 0.56% vs 1-ATR distance
  12.9% — a 23× winner-R haircut), while 0.5-ATR is actually TIGHTER than the ORB stop on the
  median trade (2.8% vs 3.9%). All ATR rows are ex-top-5 negative at both horizons; atr_0.75 was
  also checked (in script output) — same shape.
- **Prior-day-low** is a different trade, not a wider stop: ~20% distance, 5× winner shrink,
  win rate 53%, expectancy ≈ flat-to-negative, and 30 of 147 still stop within 5 days. It beats
  the baseline on most individual trades (turning −1R full losses into ~−0.4R partial losses at
  the day-5 close) but never in total.
- Thin stops + overnight holds are the real tail risk in the other direction: ETHD (0.51%
  distance, excluded from the exec slice) closed day-0 at +16.8R and gapped to **−13.5R** the
  next open — R is bounded by the stop only intraday. On the executable slice this tail is
  modest (one case below −1.5R), but #327 measured gap-through as 64% of loss on the
  consolidation shadow; a wider stop shrinks gap-through R by construction (same dollar gap,
  bigger denominator) — the one structural argument FOR width, and it is visible only off-slice.

---

## 5. Both arms, so the trade-off is decidable

For every width, the two arms at day-0 on the executable slice (day-5 in §4 table):

| Width | Arm 1: losers rescued | Arm 2: cost paid |
|---|---|---|
| 1.25× | 17 of 95 baseline stop-outs survive; median end +0.47R; 9 of 17 still dead by day-5 | 52 trades do worse; every common survivor's R × 0.80 |
| 1.5× | 23 rescued, median +0.39R; 19 dead by day-5... | R × 0.67 |
| 2.0× | 36 rescued, median +0.27R | R × 0.50 — half of every winner |
| pdl | 92 rescued, median −0.13R (still losses, just smaller) | R × 0.21 |

And the cohort-A version of "what happened to the rescued ones in the end": of the 4 real-trade
day-0 rescues at 2.0× (MANE +1.76R, MRAM +0.71R, KLAR +0.36R, THC −0.53R), **MANE and MRAM were
stopped anyway by day 1/5 for the full −1R, later and slower**; THC finished +0.81R and KLAR
scratched (+0.01R). A rescue that dies later is the same loss with more time in it.

---

## 6. Fidelity limits (read before citing any number)

1. **Minute-bar lows, not ticks.** A stop counts as filled on a bar-low touch — conservative
   against the wider-stop case (wide stops get stopped as often as the data allows).
2. **Intraday day-0 + daily-bar day-1..5.** The extension fills overnight gap-through at the
   open, not the stop. Intrabar sequence on daily bars is unknowable; with no profit target in
   the replay the only ambiguity is stop-vs-close, resolved stop-first (pessimistic).
3. **No harvest rule in any arm.** Live now runs the +2R trigger (#508) and partials; both
   settle worlds bracket reality (bank-everything-at-day-0-close vs hold-5-days-stop-only).
   The day-0 vs day-5 flip in cohort B's baseline total (+16R → −3R exec slice) is the measured
   cost of not harvesting — it dwarfs every stop-width delta in the table.
4. **Sim entries fill at ORB high with zero slippage** (live fills averaged slightly worse).
   Real trades replay from actual fills.
5. **Replays structurally flatter wider stops**: no widened-stop world changes anyone's later
   entries/exits, halts, or borrow; and survivorship of the capture pipeline decides cohort B.
6. **Era concentration**: 83% of cohort B is May 2026. The live cohort is July 2026. Neither
   spans a regime cycle.
7. Counterfactual sizing at constant risk means wider stops = smaller notional; position-cap and
   PDT interactions were not modelled (they bind against the CURRENT tighter stops, so this
   flatters nothing).

---

## 7. Recommendation

- **Do not change the stop.** The evidence does not clear the bar for any width tested:
  every aggregate gain is ≤5-outlier-carried, the median trade is indifferent (−1R either way)
  or worse (winner shrink), and the only real-money sample (12 trades) shows losers that die
  under every geometry up to 5.6× wider. If the current stop were costing us real trades that
  work, the 162-entry simulated cohort is large enough that it would show up ex-outliers. It
  does not.
- **The measured leverage is harvest timing, not stop width**: three of the twelve live trades
  were +0.7R to +3.2R at the day-0 close and all died by the next morning; cohort B's baseline
  swings +19R between the bank-at-close world and the hold-5-days world (exec slice). That is
  exit-discipline territory — already the operator's stated priority (#508) — and argues for
  replaying THIS sweep under the actual #508 exit rules before ever revisiting stop width.
- **If width is ever revisited**: ORB-proportional (≈1.25×) is the only variant positive at both
  horizons before trimming, and ATR-anchored widening should be ruled out (it taxes exactly the
  best setups). But 1.25× is not currently defensible either — its entire gain is tail-carried
  (ex-top-5: −6.5R / −16.6R).
- **Any change requires**: operator sign-off + `docs/setups/CHANGE_PROCESS.md` + backtest N≥10
  — this doc is an input to that process, not a substitute for it.

**What would change this conclusion:**
1. ~40–60 additional live/full-bar real trades whose day-5 rescued-share materially exceeds
   the ~8% (1/12 at 2.0×) seen here.
2. A harvest-aware re-run (wider stop + #508 +2R banking + partials) showing the day-0 rescues
   (MANE/QBTS class: +1.6R to +3.2R intraday) get BANKED instead of given back — the one
   interaction this replay cannot see and the most plausible path by which width could pay.
3. Tick-level evidence that bar-low-touch materially over-stops the BASELINE (would make the
   current stop look worse than it is).
4. A regime split showing the May-era cohort B masked a different answer in the current tape.

---

*Data: `mi_live_trades` (46 closed), `mi_ep_alerts` (327 distinct HIGH days), `mi_intraday_bars`
(121,604 RTH 1-min bars), `mi_daily_closes` (through 2026-07-31), pulled 2026-08-03. Full sweep
tables incl. unsliced cohort B, atr_0.5/0.75, per-trade rescue rosters and all exclusion ladders:
`python scripts/stop_width_replay.py`. Units verified empirically per column (gap_pct is percent
in `mi_ep_alerts`; all prices dollars; atr_14 dollars).*
