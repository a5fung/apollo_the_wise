# #533 — Within-day ranking: when several EP alerts fire in one morning, are we taking the right ones?

**Date:** 2026-08-30 · **Read-only analysis, $0, nothing flipped** · Data + scripts: `/Users/alvinfung/.claude/jobs/6b173ac9/tmp/533wd_*`

## The decision it serves

Operator 2026-08-05: *"does it capture the main goal of selecting best EPs in a given day when there's many?"* — and 2026-08-11, on SE: *"the ranking within same day EP is important and this may be a good data point."* The entry path today has **no ranking at all**: `live_tracker.process_new_alerts_live` selects with `DISTINCT ON (ticker) … ORDER BY ticker, ep_score DESC`, so across tickers the surviving order is **alphabetical**. This document measures whether any followable ranking would have taken better names, morning by morning, than that accident.

## Method / population

- **Population:** `mi_ep_alerts` rows with `score_tier='HIGH'` and `source='live'` (193 rows) — the rows that existed on each morning. The 150 `historical_scan` rows (backfilled 2026-06-11, different scorer) are **excluded**: they were not on any live board. Deduped per ticker-day by max `ep_score`, mirroring the entry path's `DISTINCT ON`.
- **ORB eligibility:** only alerts detected before 9:45 ET compete for slots (the submission cutoff). 49 of 190 ticker-days were detected later and are excluded — validated against `mi_live_trades`: **0 of the 49 ever produced a non-skip trade row**, and prod's own `window:out_of_orb` skips (AMRC, TSAT on 08-04) match the cutoff exactly.
- **Window:** alert days 2026-05-11 → 2026-08-28. Usable board rows n=141 across 63 alert days.
- **Outcome (primary):** the name's move **from the day-0 open** — buyable after the open, so the gap itself earns no credit. `ret5` = 5th-session close ÷ day-0 open − 1 (from `mi_daily_closes`); `mfe5` = max high over day 0–5 ÷ open; `ret_d0` = day-0 close ÷ open. NOT `mi_ep_missed_outcomes` (60% corrupt, repaired 08-29) and not `baseline_close`-anchored `mi_ep_scan_outcomes` (those credit the gap).
- **Features, all known by 09:31 from the prior evening:** `ep_score` (alert time), prior-day `rs_composite`/`rs_rank`/SMAs/`adv_20` from `mi_stock_scores` (point-in-time join: latest `score_date` strictly before `alert_date`; **0 of 141 names lacked an RS row**), theme stage reconstructed from `mi_themes` snapshots ≤ day−1 (the briefing's exact bonus map).
- **Spot-verified by hand:** SE 08-11 ret5 −9.1% recomputed from raw bars; the 08-11 four-name board reproduces the operator's worked case exactly (scores, RS ranks, above-MA flags).

## How many days had a real choice

| board size (distinct HIGH tickers, ORB-eligible) | days |
|---|---|
| ≥2 alerts | n=35 |
| **≥3 alerts (the decision days used below)** | **n=16 (15 with settled 5-day outcomes)** |
| ≥6 alerts (cap binds even from an empty book) | n=6 |
| days where the 5-slot cap actually blocked an entry | n=3 (05-14, 08-04, 08-07) |

**The real n is ~15 mornings, not 141 alerts.** All 15 settled decision days predate the 08-22 score rework — zero multi-alert days have settled since, so the `ep_score` read below describes the OLD score.

## The numbers — each ranking on the same 15 mornings

Per day: rank the board, take the top 2 (the realistic free-slot count), compare to the rest of that same day. Never pooled across days. `pickPct` = where the ranking's chosen pair lands among ALL possible pairs that morning (0.50 = picking blind).

**Primary metric, ret5 (5-day move from day-0 open), n=15 days:**

| ranking (all followable at 09:31) | median within-day rank corr. | median top2−rest edge | days edge>0 | pickPct | day's best name in top 2 | sum of top-2 means |
|---|---|---|---|---|---|---|
| **ALPHA — the incumbent** | −0.05 | +1.6% | 8/15 | 0.48 | 8/15 | **−22.9%** |
| ep_score alone | −0.05 | +1.6% | 8/15 | 0.50 | 7/15 | −5.3% |
| composite (briefing sort) | +0.14 | +3.1% | 10/15 | 0.62 | 8/15 | +30.8% |
| **RS (prior-day RS composite, highest first)** | **+0.22** | **+8.4%** | **10/15** | **0.63** | **9/15** | **+55.1%** |
| strength (above-MA count, then RS rank) | +0.29 | +6.4% | 8/15 | 0.56 | 8/15 | +30.7% |
| ADV$ (20-day dollar volume) | +0.20 | +6.7% | 10/15 | 0.61 | 9/15 | +27.7% |
| gap% (biggest gap first) | −0.01 | +2.8% | 8/15 | 0.52 | 8/15 | −19.3% |

- **The incumbent and the score are both coin flips.** Alphabetical picks sit at the 48th percentile of that morning's possible pairs; ep_score at the 50th. The thing the entry path sorts on does not rank the day.
- **RS is the best single axis**, and it is the one the operator pointed at on 08-11. Direction holds on all three outcome measures (mfe5: composite 0.66 / RS 0.61 / ALPHA 0.55 pickPct, n=16; ret_d0: composite 0.66 / RS 0.62 / ALPHA 0.54, n=16). With one free slot (top-1, n=15): RS +11.4% median edge, ADV$ +10.7%, ALPHA −4.0%.
- **The briefing composite is directionally right but diluted by construction:** its RS bonus caps at 10 points against a 40–115 score scale, and its theme bonus fired on only 19 of 141 names. Its gain over raw ep_score IS the RS term.
- **On the 6 big-board mornings (≥6 alerts — the mornings this task is about):** RS mean top-2 edge **+9.8%/day**; alphabetical **−6.4%/day**.
- **Worked case generalised:** on 08-11 RS puts SE first (RIOT/FRMI/BW last three) — and on 08-04, RS's top 2 were LIFE (+22.4%, RS 98) and ZBRA (+16.0%, RS 92) while the live path gave slots to BTDR (−32.0%, RS 24) and cap-blocked ZBRA.

## Both directions (P14) — what each ranking's top-2 would have MISSED

Day-best names with ≥+10% ret5 left outside the top 2, n=15 days:

| ranking | missed day-bests (n) | which |
|---|---|---|
| ALPHA (incumbent) | 4 | STUB 05-14 +11%, VOYG 08-04 +26%, U 08-06 +27%, TEAM 08-07 +12% |
| ep_score | 6 | BW 05-11, AMBQ 05-12 +34%, STUB, ARM 07-30, VOYG, U |
| RS | 4 | STUB 05-14, ARM 07-30 +11%, FET 07-31 +21%, VOYG 08-04 +26% |

RS misses no more than the incumbent misses today, and its misses share one shape: a weak-RS name that ran anyway (VOYG, RS rank 1969, +26% — **no ranking tested put it in the top 2**). Ranking reorders the board; it cannot manufacture recall. Note these are slot-competition misses, not alert misses — every name was still alerted and briefed.

## Adversarial checks

- **Best day removed:** RS median edge +8.4% → **+8.1%** (mean +8.2% → +7.1%). It does not collapse. ep_score DOES collapse (+1.6% → +0.3%); strength drops to +1.3%.
- **The hypothesis-source day removed:** the RS ranking was proposed from the 08-11 shape, which is in-sample. Excluding 08-11 entirely: RS median edge **+11.8%**, 9/14 days positive. The result does not depend on the day that inspired it.
- **How much is fitting?** Five challenger rankings were tried on 15 mornings; RS's 10/15 positive days is one-sided p≈0.15 — **not statistically conclusive on its own**. What it has instead: consistency across three outcome metrics, survival of both leave-outs, and an incumbent with literally zero evidence in its favor. The claim this supports is "alphabetical is indefensible and RS is the best-evidenced replacement," not "RS is proven."
- **SE was killed by the gap floor, not by ordering.** `setup:gap_below_floor` at submission. A ranking fix alone would NOT have entered SE on 08-11; the floor half was addressed separately (#559, real-time gap authoritative, live 08-27). Both are needed.
- **One big-day dependence in the sums:** the sum-of-top-2 gap (RS +55% vs ALPHA −23%) is spread across days (RS per-day edges: 10 positive, largest +23.7%), not one day — per-day list is in `533wd_verify.py` output.

## What this does not answer

- **Whether the ranked name would have FILLED.** Outcomes are the name's move from the open, not realized R under our ORB entry/stops — on 08-04, RS's #1 pick LIFE never broke its ORB high in the window and the order cancelled unfilled. Ranking chooses which orders to place; entry tactics decide fills. (Realized live trades cannot score a ranking at all: the closed cohort is 0-winners, no variance.)
- **Whether the NEW (post-08-22, liquidity-led) ep_score ranks better within-day** — zero settled multi-alert days exist since the rework. The RS result is unaffected (its input didn't change), but the "ep_score is a coin flip" row describes the old score.
- **Whether RS ordering helps on 1–2 alert days** (no choice exists) or predicts absolute returns (within-day rank only, by design).
- **Tail conversion:** +8%/day of top-2 edge is selection quality, not proof any picked name reaches 4R.
- **~15 mornings is a small n.** The honest error bars include zero for every challenger; they do not include anything positive for alphabetical.

## Recommendation (evidence only)

Replace the accidental alphabetical order in `process_new_alerts_live` with a deliberate one: **order the day's HIGH alerts by prior-day `rs_composite` descending (ep_score as tiebreak)** — one ORDER BY change, every input already in the query's reach, followable at 09:31, and the best-evidenced axis on 15 mornings. A close second worth considering jointly: let the existing composite do it, with the RS term uncapped so it can actually move a 40–115-scale score. Keep collecting: ~10 more multi-alert mornings roughly doubles the decision-day n.

## ⚖ THE LINE

What the entry path selects is entry discipline — **the operator's sole authority**. This analysis flipped nothing, shipped nothing, and changed no live behavior; any ORDER BY change to the entry path requires his sign-off (and CHANGE_PROCESS if framed as a criterion change).
