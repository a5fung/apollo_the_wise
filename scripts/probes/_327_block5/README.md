# Block 5 (2026-09-26) — P0 + P1

$0, read-only prod extract + offline replay. Raw CSVs are gitignored (regenerate with
`extract_p0.sh`); only scripts + the small JSON summaries are committed.

## Regenerate

```bash
./extract_p0.sh          # prod pull via ssh+psql, ~2M-4M CSVs, gitignored
python3 p0_completeness.py   # -> p0_summary.json
python3 p1_probe.py          # -> p1_summary.json (needs trigger.csv, daily_closes.csv,
                              #    intraday_day0_raw.csv from extract_p0.sh)
python3 p2_probe.py          # -> p2_summary.json + p2_fire_walks.csv / p2_control_walks.csv
                              #    (gitignored; per-row checkpoint outcomes for P3/P4)
```

## P0 result — PASS, checkpoint stays s10

Population: 3,767 trigger rows (700 tickers), 3,304 settled. Completeness denominator
is fires whose session *k* has actually occurred by 2026-09-26 (never the fixed
population — a fire fired last week has no session-20 bar to be missing yet, that is
"not happened", not a hole; an earlier cut of this script conflated the two and wrongly
read 35% at s20 before the fix).

| | s10 | s20 |
|---|---|---|
| settled fires | 98.85% | 96.35% |
| clock-eligible (>=20 sessions elapsed, any status) | 97.86% | 95.80% |

Both populations agree closely -> the settled-only read is not a survivorship artifact
here. **s10=98.85% >= 90% and s20=96.35% >= 80% -> PASS, primary checkpoint stays s10**
(the 70-90% move-to-s5 rule never triggers).

Day-0 minute-bar hole (the judges' fix): of 2,437 settled fires whose walk needs
minute resolution (`fire_minute_et` not null and `day_low <= stop_price`), **2,213
(90.8%) have zero 1-min bars in `mi_intraday_bars`** for that ticker/day. 867 settled
fires never need minutes at all (daily-grade fire, or the day low never reached the
stop). This is the number P3 needs before deciding how day-0-needing fires without
minute coverage get walked (fold to a whole-day pseudo-bar, the same convention
`compute_settlement` already uses for daily-grade fires, or exclude them — an
operator/P3 design choice, not decided here).

## P1 result — PASS, and every non-match is explained

Wired to the REAL `compute_settlement` (imported, never re-implemented), fed inputs
assembled to mirror `_assemble_settle_window`'s exact fallback rules. Day-0 minutes,
when needed, come from one of three $0 sources tried in order: (a) `mi_intraday_bars`
already covers the (ticker, fire_date) -> real 5-min bars via the production
`to_rth_5min`, (b) the row's own `day0_resolved`/`day0_post_low/high` cache -> the
production `day0_pseudo_bars`, (c) neither -> the probe abstains (documented, not
attempted, never silently dropped from view).

- **1,283 of 1,297 attempted rows scored** (n >= the 500 floor); 14 abstained
  (`window_open` — ran out of forward calendar without a stop touch, see below).
- **M-none (the pass bar), SCORED reading: outcome exact match 1,281/1,283 = 99.844%;
  realized_r within 0.001R = 99.844%.** Both clear the >=99% bar.
- **STRICT reading** (denominator = all 1,297 rows a day-0 source existed to attempt,
  counting the 14 abstains as non-reproductions): **1,281/1,297 = 98.77% — below 99% on
  its own.** Reported because "reproduce row-for-row" can be read either way; the case
  below is why the scored reading is the one claimed.
- **M-trail (free cross-check): 100.0% on both**, after fixing a probe-only bug (see
  below) — a clean signal that the incumbent walk itself, not just its stop/target
  logic, replays exactly.
- **All 16 non-clean rows (2 scored-mismatch + 14 abstained) carry a clean-integer
  post-fire price-scale jump** (6x-80x, verified per-row against 10 distinct tickers)
  between the trigger row's own contemporaneous `day_high` and today's
  `mi_daily_closes` high for the same date. This is an **inference from price shape**
  (nearest-integer ratio, not a lookup against a corporate-actions source) but a strong
  one on penny stocks: a **stock split between the fire and this extract retroactively
  rescales `mi_daily_closes` while `entry_price`/`stop_price` stay frozen at the
  fire-time scale** — a data-adjustment artifact of replaying against a continuously-
  adjusted table, not a wiring defect in `compute_settlement` or in this probe.
  **Split-adjusted reading: 1,281/1,281 = 100%.** This is the reading claimed for PASS;
  the strict 98.77% would need a corporate-actions source (not available at $0) to
  confirm rather than infer the 16 splits.
- 2,007 settled rows (60.8%) needed day-0 minutes with no offline source available —
  abstained, counted, never dropped silently. This is the same fetch-cost tradeoff P3
  will face at scale; it does not affect the pass-bar verdict (n_scored already clears
  the floor) but bounds how much of the incumbent lane a $0 replay can currently touch.
  **P3 implication:** `day0_pseudo_bars` (the cache-based reconstruction) is only ever
  populated when a #616 ADR variant stays pending past its incumbent settlement — it is
  not a general substitute. For the ~60% of the settled population with no offline
  minute source, a from-scratch daily-grain re-walk has no minute path available either
  and will have to fold day 0 to a whole-day range, which is exactly the pessimistic
  daily-grade convention `compute_settlement` already uses when `fire_minute is None` —
  not a new design decision, just naming that the existing house convention already
  covers this gap.

**Bug found and fixed in the probe itself** (not in production code): the first cut
sorted `closes_before_fire` as `(close, date)` tuples — sorting by PRICE, not
chronologically — which silently corrupted the SMA trail seed. It never touched M-none
(which does not read that list) which is exactly how it surfaced: a trail-only
divergence (89.6%/76.0%) with a clean M-none pointed straight at the seed, per the
advisor's steer, rather than at the walk. Fixed in `p1_probe.py`
(`closes_before_fire = [... for d, v in sorted(daily_for_ticker.items()) ...]`).

## P2 result — PASS on the letter of the bar (one pattern clears), and the pass rests on the recorded entry price

**The question:** does any of the four patterns reach +2×ADR$ before −1×ADR$ more often
than buying the same names on a non-fire session of the same 20-session window? Unit =
EP-anchored ADR$ (the real `compute_ep_adr_dollar`, recomputed on today's adjusted price
scale and matched to the 1,098 stored values on 1,077; every miss is a split-rescaled
name). Population = SESSIONS ELAPSED (>=K after the fire by 2026-09-25), never settlement
status; re-entry shapes pooled into their rung as the 09-22 read did. Control = every
non-fire session of the window for the campaigns where that pattern fired, entered at the
close, same clock, same abstain rule. pess = stop checked first on every bar, opt = target
first. Day 0 mirrors `compute_settlement` (daily-grade fold; minute-grade uses real or
cached post-fire bars, else abstains when the day low reached the stop — 257 rows).

**The walker's own anchor first:** given the incumbent stop and no target, it reproduces
production's `stop_hit_date` / time-exit on **1,295 of 1,297 = 99.85%** of the settled rows
it can walk (the 2 misses are AIXI and NRSN, the same reverse-split rounding rows P1 found).

### s10, the primary checkpoint — fire rate vs matched control, +2ADR before −1ADR

| pattern | n fires | names | control n | pess fire / ctl → gap | opt fire / ctl → gap | drop-best-NAME (pess) | bar |
|---|---:|---:|---:|---|---|---|---|
| ep_low_reclaim | 1,028 | 452 | 4,920 | 13.2% / 15.7% → **−2.5pp** | 15.8% / 17.5% → −1.8pp | PDSB → −3.0pp | no edge |
| ep_close_reclaim | 790 | 384 | 3,940 | 16.2% / 19.0% → **−2.8pp** | 18.6% / 20.5% → −1.9pp | RNXT → −3.3pp | no edge |
| **ep_high_break** | 223 | 119 | 1,222 | 28.7% / 20.3% → **+8.4pp** | 31.8% / 21.7% → +10.2pp | VNRX → +7.1pp | **clears** (≥5pp, n≥150, ≥60 names, survives drop) |
| ep_close_620_prox | 1,099 | 438 | 4,519 | 12.2% / 15.0% → **−2.9pp** | 13.9% / 16.2% → −2.3pp | PDSB → −3.3pp | no edge |

s5 and s20 are in `p2_summary.json` (s20 is thin on the control side — 71–163 sessions —
because only window sessions ≤ 08-27 have 20 sessions elapsed). The kill rule ("all four
within ±2pp on both bounds") does NOT fire: three patterns sit 2.5–2.9pp BELOW control
under pess (outside ±2pp, on the wrong side) and the fourth is +8.4pp. Per the block's
literal rule the verdict is **pass**: at least one pattern shows entry edge.

### What the pass rests on — the recorded entry is not always fillable

`ep_high_break`'s daily-grade fires (and every `new_high_break` re-entry on every rung, via
`replay_level_break`) are resting stop-buys priced AT the level. The lane records the
LEVEL as `entry_price` even when the session OPENED ABOVE it — a stop-buy would have filled
at the open. 44 of the 177 level-priced high-break fires at s10 opened above the level
(median over-shoot 0.63 ADR), and the +2ADR target measured from the level is then only
~1.4 ADR from the real fill. Three reads separate "the pattern picks good sessions" from
"the level entry is a head start", all reported beside the bar and never in place of it:

| read (s10, pess unless stated) | ep_high_break | the other three |
|---|---|---|
| **FILLABLE stop-buy** — entry = max(level, fire-day open) for level-priced fires, unchanged for minute fires | **+2.2pp** (opt +5.8pp); drop-best-NAME PDSB → +1.3pp; would NOT clear 5pp | −3.0 / −3.5 / −3.0pp |
| fire entered at the fire session's CLOSE (same entry as the control) | **−0.3pp** | −0.9 / −2.1 / −1.1pp |
| by resolution, recorded entry | daily-grade +12.5pp (n=175) · minute-grade **−5.8pp** (n=48) | daily −11 to −16pp (level-priced re-entries, pess-folded) · minute −1.8 / −2.5 / −3.2pp |
| tail ladder, recorded entry: +4ADR / +6ADR before −1ADR, fire vs ctl | 14.9 vs 8.3 · 7.7 vs 3.8 | at or below control on every rung |
| tail ladder, FILLABLE entry | **9.1 vs 8.3 · 3.6 vs 3.8** — the 2× tail is gone | unchanged, at or below control |
| paired per-campaign difference (equal weight per campaign) | +14.0pp over 133 campaigns | −4.5 / −3.5 / −4.7pp |
| `first` shape only | +14.3pp (n=124); fillable +8.9pp (n=123) | −1.6 / −2.1 / −3.2pp |

So: **on the recorded entry, `ep_high_break` clears the bar; on a fillable entry it reads
+2.2pp pessimistic / +5.8pp optimistic and its tail is the control's.** The three pullback
patterns are below control on every read. This is the fact P3–P5 and the fork carry: P3
should run the high-break cells under BOTH entry conventions (the recorded level and the
fillable open), and the "lane is instrumented wrong" fork option has a concrete capture
behind it — the trigger row should record the fire-day open (or the actual first-touch
price) beside the level so the next 20 sessions answer this without a probe. ⚖ No stop, no
target and no convention is picked here.

### P4's inputs, per pattern at s10

Straddle-decided fires (s10 outcome differs between bounds): 26 / 19 / 7 / 19 of 1,028 /
790 / 223 / 1,099; straddle-decided control sessions 88 / 60 / 16 / 54. Day-0 abstains
(minute fire, day low reached the 1×ADR stop, no $0 minute source): 132 / 82 / 21 / 23.

## Files

- `extract_p0.sh` — the one prod extract (gitignored CSV outputs).
- `p0_completeness.py` -> `p0_summary.json` — bar-completeness / abstain-rate / day-0
  minute-hole read + the pass-bar verdict.
- `p1_probe.py` -> `p1_summary.json` — the settlement-replay probe + the pass-bar
  verdict + the full mismatch/abstain detail with split-ratio annotation.
- `p2_probe.py` -> `p2_summary.json` (+ gitignored `p2_fire_walks.csv`,
  `p2_control_walks.csv`) — the ADR$ entry-edge grid vs the matched control, both
  bounds, s5/s10/s20, the tail ladder, the fillable-stop-buy read, the walker's anchor.
