# Block 5 (2026-09-26) — P0 + P1

$0, read-only prod extract + offline replay. Raw CSVs are gitignored (regenerate with
`extract_p0.sh`); only scripts + the small JSON summaries are committed.

## Regenerate

```bash
./extract_p0.sh          # prod pull via ssh+psql, ~2M-4M CSVs, gitignored
python3 p0_completeness.py   # -> p0_summary.json
python3 p1_probe.py          # -> p1_summary.json (needs trigger.csv, daily_closes.csv,
                              #    intraday_day0_raw.csv from extract_p0.sh)
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

## Files

- `extract_p0.sh` — the one prod extract (gitignored CSV outputs).
- `p0_completeness.py` -> `p0_summary.json` — bar-completeness / abstain-rate / day-0
  minute-hole read + the pass-bar verdict.
- `p1_probe.py` -> `p1_summary.json` — the settlement-replay probe + the pass-bar
  verdict + the full mismatch/abstain detail with split-ratio annotation.
