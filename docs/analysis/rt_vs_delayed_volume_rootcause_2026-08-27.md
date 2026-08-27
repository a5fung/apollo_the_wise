# Why the two volume readings disagree — root cause

**Scope:** `ep_rt_volume_shadow` / `ep_rt_rvol_gate_flip`, the `vol_delayed` vs `vol_rt_*` pair.
**Status:** root cause established. READ-ONLY analysis — no rule, threshold, toggle or code changed.
**Evidence on disk:** `scripts/probes/_490rt_shadow_rows.psv` (678 rows, pre-captured),
`scripts/probes/_490rt_vol_truth.tsv` + `_490rt_vol_truth_replay.py` (independent minute tape, $0).

---

## The mechanism, in one paragraph

**The two numbers are not two readings of the same quantity at the same instant, so neither
"disagrees" with the other — they measure different windows, read at times ~16 minutes apart.**
`vol_delayed` is `c["today_volume"]`, a *single day-cumulative share count* taken from the Polygon
full-market snapshot (`day.v or min.av`), which our Polygon **Starter** subscription publishes about
**16 minutes behind the tape** — a delay the codebase already pins by name
(`ep_delayed_residual.py:40`, `LAG_MIN = 16  # measured Polygon Starter feed delay`) — and which the
detector then assigns **wholesale to whichever RVOL anchor happens to be active**
(`ep_detector.py:3313-3316`: before the open the whole day-cumulative becomes the *pre-market*
bucket; after the open the same whole day-cumulative becomes the *session* bucket).
`vol_rt_pm` / `vol_rt_session` are a live Alpaca SIP minute-bar sum split into two *genuine*
buckets — 04:00–09:29 and 09:30–now — fetched a few seconds after the same scan tick. So the pair
is "(everything Polygon counted, as of T−16 min)" against "(one correctly-bounded bucket, as of T)".
In early pre-market almost nothing trades in 16 minutes, so the staleness costs nothing and a small
**fixed head-start** that Polygon carries and our 04:00-anchored Alpaca sum does not (a few hundred
to ~1,500 shares) makes the delayed number look *higher*; once the tape ramps — and violently at the
open — 16 minutes of volume dwarfs that head-start and the ordering **reverses**. The frozen repeats
are the same effect seen twice over: the real-time number repeats when there genuinely were no
trades in the interval, and the delayed number repeats when the 16-minute-old slice it is showing
happens to be a quiet stretch. **The real finding: the shadow telemetry has been comparing unlike
things, and the same mis-pairing is live in the RVOL gate** — 79 of the 187 usable session rows are
recorded gate flips, essentially all in one direction (delayed rejects, real time passes).

---

## What each number actually is — code trace

| | delayed (`vol_delayed`) | real time (`vol_rt_pm` / `vol_rt_session`) |
|---|---|---|
| Source | Polygon full-market snapshot, `get_snapshot_all()` (`collector.py:213`) | Alpaca SIP minute bars, `get_alpaca_minute_cum_volumes()` (`collector.py:337`) |
| Field | `snap["day"]["v"] or snap["min"]["av"]` (`ep_detector.py:2064`) | sum of minute-bar volumes from `now_et.replace(hour=4, minute=0)` |
| Window | ONE day-cumulative number — no bucket split at all | TWO real buckets: 04:00–09:29 and 09:30–now |
| Freshness | **~16 min stale** (Polygon Starter) | live at fetch time |
| Fetched at | scan start, `ep_detector.py:2866-2874` | after Pass-0/1/2, `ep_detector.py:3266` |

The delayed number is then forced into an anchor it was never bucketed for:

```python
# ep_detector.py:3313-3316
if _minutes_since_open is None:
    premkt_vol, session_vol = c["today_volume"], 0
else:
    premkt_vol, session_vol = 0, c["today_volume"]
```

The two-fetch gap inside one scan is **not** a material contributor: across 273 scan ticks the first
audit row lands a median of **6 seconds** after the tick (p90 19 s). The ~16-minute vendor delay is
the whole of the timing term.

---

## Q1 — what window does the delayed number cover?

**A day-cumulative window, ending ~16 minutes in the past, and it is fed to whichever anchor is
active regardless of what that anchor means.**

- It is never a pre-market-only or session-only figure by construction. `day.v or min.av` is one
  running total; the in-code comment (`ep_detector.py:2063`) says as much: *"day.v for regular
  session, min.av for accumulated (includes pre-mkt)"*.
- Because of the 16-minute delay, at every scan tick from **09:30 to ~09:45** the snapshot still
  reflects a pre-market clock time, so the value taken is `min.av` — Polygon's day-accumulated
  volume, which by the quoted comment *includes pre-market* — and at those ticks it consists of
  little or nothing but pre-market shares. That **pre-market share count is then divided by the
  *session* baseline.** **222 of the 342 session-anchor rows sit at ticks 09:30–09:44** — i.e. two
  thirds of the session telemetry is pre-market volume over a session denominator.
- Worked example, PSIX 2026-08-07, tick 09:30: delayed 22,132 against a session baseline of
  ~10,284 → `rvol_delayed` 2.152. The 22,132 is pre-market shares as of roughly 09:14. The ratio is
  arithmetically fine and physically meaningless.
- Worked example, CAI 2026-08-06, ticks 09:35 and 09:40: delayed 26,551 both times — pre-market
  accumulated as of ~09:19 and ~09:24 — then jumps to 152,977 at the 09:45 tick, the first reading
  to carry any session shares at all. 152,977 decomposes almost exactly as pre-market (35,232 per
  Alpaca) plus part of the 291,734-share 09:30 opening minute, i.e. the tape as of ~09:30:30 read at
  09:45 — an implied lag of ~14.5 minutes. That decomposition is itself the evidence that the field
  being read across this whole window is `min.av` (pre-market inclusive) rather than `day.v`: a
  session-only `day.v` could not contain the 35,232 pre-market shares.

**Undetermined (does not change the answer):** whether the residual head-start comes from trades
before 04:00 that Polygon's day-accumulator counts, or from trade-condition inclusion differences
between the two vendors' aggregation. See "Open item" below.

---

## Q2 — why do consecutive ticks repeat identical numbers?

Three distinct causes, and the operator's three examples are one of each. **It is not caching in our
code** — `_polygon_get` has no cache, `get_snapshot_all()` and the Alpaca bars call are both issued
fresh every tick, and `_audit_dedupe_check` only suppresses *rows*, never reuses values.

1. **BOTH feeds repeat → genuinely no trades.** CAI 2026-08-06, ticks 07:00 and 07:20: delayed
   7,103 and rt 6,396 at both. The delayed pair says nothing traded between ~06:47 and ~07:07; the
   rt pair says nothing traded between ~07:03 and ~07:20. Thin pre-market name, dead 30 minutes.
   Consistent, not contradictory.
2. **Only rt repeats → genuinely no trades in *its* window, while delayed is still walking an
   earlier, busier slice.** ATRO 2026-08-12: rt is 402 at both 07:30 and 07:50 (nothing traded
   04:00→07:50 beyond 402 shares), while delayed grows 1,097 → 1,479 because it is showing
   07:14 → 07:34, and ATRO *did* trade in that slice. **The two numbers are reading different
   20-minute windows of the same tape.** No freeze, no lag anomaly.
3. **Only the delayed number repeats → its 16-minute-old window happened to be quiet.** CAI's
   26,551 at both 09:35 and 09:40, while rt session went 449,075 → 634,505. Pre-market
   09:19→09:24 was quiet; the actual market was not.

**The real-time session bucket never repeats: 0 consecutive-pair repeats across the whole capture.**
**48 of the 53 `vol_rt_pm` repeats are the trivially correct case** — 45 pairs where both ticks are
at or after 09:30 and 3 straddling it, i.e. pre-market volume that cannot change once the session
starts. Only **5** are a genuine pre-09:30 no-trade interval (case 1 above). The
operator's "CAI both feeds identical at 09:35/09:40" reads the `vol_rt_pm` column; the acting
column there is `vol_rt_session`, which grew 449,075 → 634,505 → 1,110,765.

---

## Q3 — why does the ordering reverse?

**Because the two error terms move in opposite directions and cross.**

- *Staleness* pushes delayed **down** by exactly the volume traded in the last ~16 minutes. That
  term is near zero at 07:00 and enormous at 09:45.
- A *fixed additive residual* pushes delayed **up** by a constant few hundred to ~1,500 shares that
  does not grow with the day.

Early, the residual wins; late, the staleness wins. Two independent proofs that the residual is
real (neither depends on knowing the lag length):

- **Monotonicity.** Cumulative volume only increases, so a pure delay can *only* make the delayed
  number ≤ the real-time number. Yet delayed exceeds real time on **36% of 07:00-hour pre-market
  rows** (n=215). A positive additive term is therefore required — this is an existence proof.
- **A hard bound with no interpolation.** ATRO 2026-08-12: Alpaca read 402 shares at 07:50, so
  Alpaca's count at 07:34 was ≤ 402. Polygon's reading *as of* ~07:34 was 1,479.
  **Polygon − Alpaca ≥ 1,077 shares at the same instant.**

Magnitude estimate (weaker, caveat named): re-aligning each delayed reading against the real-time
reading from ~16 minutes earlier (25 usable pairs, partners accepted at 12–20 min spacing) gives a
median ratio of **1.115** and — the load-bearing part — **never once below 1.0 (0 of 25)**, versus
64% below 1.0 when the two are compared at the same clock time. The 1.115 itself is confounded by
the ±4-minute partner tolerance and should be read as "roughly 10%", not a measurement.

The crossover in the raw data, per tick hour, pre-market anchor:

| tick | n | median delayed / real time | share where delayed > real time |
|---|---|---|---|
| 07:00–07:59 | 215 | 0.946 | 36% |
| 08:00–08:59 | 77 | 0.906 | 26% |
| 09:00–09:29 | 43 | 0.957 | 33% |
| 09:30+ (session) | — | see below | collapses; real time dominates |

PSIX 2026-08-07 walked end to end (delayed reading is as-of ≈ tick − 16 min):

| tick | delayed | real time @ tick | delayed − real time |
|---|---|---|---|
| 07:00 | 3,875 | 2,383 | +1,492 |
| 08:50 | 13,832 | 12,608 | +1,224 |
| 09:10 | 15,027 | 19,517 | −4,490 |
| 09:30 | 22,132 | 26,098 | −3,966 |

The positive column is the fixed residual (~1,200–1,500 shares, flat while volume grew 10×); the
negative column is 16 minutes of a ramping tape.

---

## Q4 — which number is correct?

**In the regular session, the real-time number, decisively — verified against an independent tape.**
Yahoo minute bars for CAI 2026-08-06 (captured to `scripts/probes/_490rt_vol_truth.tsv`):

| tick | delayed | real time (session) | independent tape, cumulative from 09:30 |
|---|---|---|---|
| 09:35 | 26,551 | 449,075 | 491,040 (through the 09:34 bar) |
| 09:40 | 26,551 | 634,505 | 675,075 (through 09:39) |
| 09:45 | 152,977 | 1,110,765 | 1,152,726 (through 09:44) |

The real-time reading matches the independent tape within a few percent — the gap is the one bar
still open when Alpaca was called. The delayed reading is **17× low at 09:35 and 7× low at 09:45**,
and is not a *session* number at all at the first two ticks.

**In pre-market, "correct" is not established for either — but the real-time number is the
*window-consistent* one, which is what the gate actually needs.** The independent tape returns zero
volume on every pre-market bar for these symbols, so it cannot arbitrate pre-market shares. What is
established:

- The RVOL denominator in `mi_minute_volume_curves` is built from Polygon minute bars filtered to
  `m >= PM_START_MIN` (`minute_volume.py`, `PM_START_MIN = 240` = 04:00) — i.e. the baseline is
  **04:00-anchored**. The real-time numerator uses the same 04:00 anchor; the delayed numerator does
  not (it is one un-split day total, 16 minutes stale).
- ⚠ Caveat worth carrying: the real-time path puts an **Alpaca numerator over a Polygon
  denominator**. If the residual turns out to be a proportional trade-condition class, that is a
  systematic RVOL bias *against* the real-time path at all volume levels. If it is a fixed pre-04:00
  chunk, the baseline's own 04:00 filter already removes it and there is no bias. This is exactly
  why the open item below matters.

---

## What this means for the shadow telemetry and for the live gate

**The comparison as built is not apples-to-apples, so `would_rvol_gate_flip` is not measuring what
its name says.** It is measuring "correctly-bucketed live volume vs a 16-minute-stale day total",
and the flips are mostly the delayed feed being stale rather than the real-time feed being better
at anything.

Recorded flips (the code's own flag, which already applies the `baseline_n >= 10` condition):

- **Session anchor, 187 rows with a *measured* real-time session bucket → 79 flips (42%).**
  77 of those 79 are one-directional: **delayed fails the 1.0× session gate while real time
  passes.** Examples: NEOG 2026-07-30 09:40 — delayed 956 shares (0.03×) vs real-time session
  138,213 (3.58×); INIO 2026-07-30 09:45 — delayed 24,262 (0.09×) vs 611,381 (2.28×);
  FTNT 2026-07-30 09:35 — 144,462 (0.74×) vs 839,381 (4.28×).
  *The 187 deliberately excludes the closed 09:30 zero class — this does not re-open it.*
- **Pre-market anchor, 336 rows → 15 flips (4.5%)**, split 10 / 5 by direction. Pre-market is where
  the two numbers nearly agree, because 16 minutes of a dead tape costs almost nothing.

**The same mis-pairing is live**, not shadow: `compute_rvol_at_time` receives the identical
`c["today_volume"]` in the acting path. A name whose real session pace is 3–4× normal can be
rejected with `session_rvol_too_low` on a stale pre-market share count. **This is a statement of
mechanism, not a proposed change — entry/admission discipline is the operator's call (THE LINE).**

---

## Open item — the one thing not settled, and the exact read that settles it

**What the fixed additive residual IS.** Two candidates: (a) trades before 04:00 that Polygon's
day-accumulator counts and our `start = 04:00` Alpaca sum slices off; (b) trade-condition inclusion
differences between the vendors' aggregation. The evidence leans (a) — the residual is roughly flat
while volume grows 10–60× (WLDN 2026-08-07: ~350 → ~500 → ~780 shares while real-time volume went
100 → 4,564) — but that is a lean, not a proof, and a small proportional component may coexist.

**Settled by one read-only call:** Polygon minute aggregates for **ATRO 2026-08-12** covering
20:00 on 2026-08-11 through 08:00 on 2026-08-12, summed either side of 04:00 ET. If the pre-04:00
side holds ≳1,077 shares, it is (a) and closed. Same call for PSIX 2026-08-07 confirms.

**Why it was not run here:** no Polygon or Alpaca credentials exist on this machine (`.env` is
absent; only `.env.example` is present), the keys live on the prod host, and `ssh` to the prod host
is blocked by the sandbox classifier in this session. Every local capture that could have
substituted (`_490b_intraday_bars.tsv`, `_508e_winner_bars_out.csv`) is regular-session-only
(09:30–16:00); `_srbt_bars.psv.gz` is daily bars.

**It does not block the answer above.** The mechanism — 16-minute vendor lag, plus one day-cumulative
number forced into whichever anchor is active, plus a fixed additive head-start — is established, and
the "comparing unlike things" finding stands on its own. It *does* block a clean recommendation on
`ep_rt_volume_authoritative`, because the residual's class decides whether the real-time path carries
a systematic RVOL bias.

---

## Method and provenance

- **No prod query, no paid call, no code change.** The 678 shadow rows were read from the existing
  capture. The only new fetch is Yahoo minute bars (free, keyless), captured once by
  `scripts/probes/_490rt_vol_truth_replay.py` to `scripts/probes/_490rt_vol_truth.tsv`.
- The Polygon Starter delay is not inferred here — it is already measured and pinned in-tree:
  `ep_delayed_residual.py:40` (`LAG_MIN = 16`), `broker/order_manager.py:7224`,
  `broker/alpaca_client.py:913`, `docs/design/306_intraday_path_recorder_2026-07-25.md:31`,
  `scheduler.py:5656`. This analysis independently reproduces it (the CAI 09:45 decomposition implies
  ~14.5 min; the lag-aligned pairing is consistent with 12–20 min).
- Sanity check on the telemetry itself: `rvol_delayed / rvol_rt` equals `vol_delayed / vol_rt` on
  520 of 521 rows where both are positive, confirming both readings are divided by the *same*
  baseline — the divergence is entirely in the numerators.
- Test suite untouched and re-run: `python -m pytest tests/ -q` → **6456 passed, 7 skipped** at HEAD
  `033173db`. The task brief expected 6443/7, which was the count at `adf55733`; 91 commits touching
  49 test files have landed since. `git status` shows **zero modified tracked files** from this work —
  the only new files are `docs/analysis/rt_vs_delayed_volume_rootcause_2026-08-27.md`,
  `scripts/probes/_490rt_vol_truth_replay.py` and `scripts/probes/_490rt_vol_truth.tsv`. Nothing
  committed, nothing deployed, `PLAN.md` untouched.
