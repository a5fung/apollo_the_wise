# Pricing the last real-time switch — the grading-cost objection was wrong by 10×

**Date:** 2026-08-27 (PT) · **Task:** #559 · **Switch:** `ep_rt_gap_authoritative` (no row = OFF)
**Status:** priced. The flip is entry discipline = THE LINE, so this is a recommendation.

---

## What the switch does

A candidate must be up ≥9% from the prior close (`MIN_GAP_PCT`) to survive. That percentage
needs a current price, and there are two: Polygon (~15 min behind) and Alpaca live.

- **Today:** for a name already on the morning candidate list, Polygon's price sets the
  deciding percentage. Live can only *remove* it (`ep_rt_gap_down_authoritative`, on since
  08-01).
- **With the switch on:** the live price sets it, in both directions.

Everything else real-time is already authoritative — `ep_rt_universe_authoritative` since
2026-08-25, `ep_rt_volume_authoritative` since 2026-08-27, the down-half and entry re-check
since 08-02. This is the last one.

---

## The recorded objection, and why it does not survive

The 2026-08-01 change log priced the up-half at **+25.0 candidates per day** and held it on
that basis: grading runs only on admitted candidates, the LLM call is 27s median / 150s worst,
and detection must finish before the 09:45 ORB cutoff.

**That number counted `ep_rt_floor_flip_up` EVENTS.** It did not dedupe a ticker firing on
several 5-minute ticks, did not drop the ones firing after 09:45 (too late to trade), and did
not check whether the name was already in the funnel via another path.

Doing all three, over the 40 days to 2026-08-27 (`ep_rt_floor_flip_up` joined to
`mi_ep_alerts` and `mi_ep_scan_log`), in-window only:

| what the flip-up actually was | ticker-days | per day |
|---|---|---|
| already evaluated, died downstream anyway | 301 | 10.8 |
| alerted anyway (delayed caught up in time) | 49 | 1.8 |
| **never evaluated — the true new admits** | **70** | **2.5** |

**The new grading load is 2.5 names per day, not 25.** Nine in ten flip-ups are names the
system already looked at; for those the switch changes *when* they are seen, not *whether*.

2026-08-26 is the shape of it — four in-window flip-ups, one genuinely new:

| ticker | rt vs delayed | what actually happened |
|---|---|---|
| **TH** | 10.06% vs 5.75% | no scan-log row, no outcome row — **never seen at all** |
| NIPG | 9.91% vs 5.51% | evaluated at 10.79%, died on ADV |
| ANF | 9.64% vs 8.82% | evaluated at 28.19%, died on score |
| SMMT | 9.21% vs 7.41% | evaluated at 9.02%, died on score |

---

## What the 2.5 per day are worth

Scored from `mi_daily_closes` — 68 of 70 have a day-0 bar, 61 have a full five sessions.

- **Hold to day 5: −0.9% average, 28 up / 33 down.** As a buy-and-hold pool, a coin flip
  tilted slightly negative.
- **26 of 61 (43%) traded ≥10% above the day-0 close at some point within five days**, average
  best move +9.9%.

Top of the set: BRUN +26.0% · ENTG +21.8% · CECO +19.6% · TTMI +18.0% · BCRX +16.8% ·
PI +16.6% · RXO +15.2% · AMKR +12.2%.

⚠ **What this does not measure.** The baseline is the day-0 CLOSE, not our actual entry (a
stop-buy at the ORB high around 09:31) and there is no stop in it. So these are not R numbers
and must not be read as such — they say the pool contains real movers, not what we would have
made. They also do not pass the rest of the funnel: these 70 were never graded, so an unknown
share would have died at the catalyst, score, ADV or extension gates anyway. **The honest
reading is an upper bound on what the switch could add, not a forecast.**

---

## Recommendation

**Flip it.** The stated reason for holding it was cost, that cost is 2.5 graded names a day
rather than 25, and there is no data-quality argument for deciding a 9% cutoff with a price
we know is 15 minutes stale — the same feed is already authoritative for removing a name,
admitting a name, and for volume.

Two things to watch after the flip, both already instrumented:

1. **Latency against the 09:45 cutoff** — `ep_rt_admit` and the scan-tick timings. 2.5 extra
   candidates at 27s median is well inside budget, but it is the number that would invalidate
   this if it moves.
2. **Whether the extra 2.5 dilute the 5 entry slots.** They compete for the same slots on a
   ranker that is not validated out-of-sample — the P9 concern the operator raised on 08-19,
   which this analysis does not answer.

⚖ Admission is entry discipline = **THE LINE**. This document produces a number and a
recommendation; the flip is the operator's.
