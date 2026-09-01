# Delayed-entry watch lane, replayed OFFLINE over every EP we actually caught (May–Aug)

**Date:** 2026-09-01 · **Read-only replay** — no prod writes, no thresholds, no strategy changed.
**Acting-rules source:** `live_rules_2026-09-01.txt` (captured 06:27 PDT, 0 drift findings).
**Supersedes** the funnel numbers in `562_delayed_entry_trigger_2026-09-01.md` (wrong population —
gappers, not caught EPs) for every outcome question. Probe + captured data:
`scripts/probes/_562_backfill_replay.py` + `_562bf_*.tsv` (+ `_562bf_report.txt`, the full tables).

---

## The decision this serves

The live watch lane, re-seeded to the operator's 2026-09-01 population ruling (*"any real EPs our
system caught… delayed entry is only a trading entry/exit tactic, not a EP finding system"*), holds
~6 members and gives its first honest forward read ~2026-09-23. This replay answers the same
question **today** from stored bars: which of the four recorded rungs (if any) deserves the
selection-layer design effort, and what the missing piece actually is. Nothing here flips anything.

**What would change the answer:** a rung with positive expectancy per fire and a real ≥4R tail on
the caught-EP population would graduate toward a proposal; a rung that fires on everything and
bleeds at the stop says the missing piece is selection/management, not rung definitions.

## Method / population

- **Population:** live-source `mi_ep_alerts` (`COALESCE(source,'live')='live'`), ALL tiers, one
  campaign per ticker×alert_date: **n=267** (May 74 · Jun 53 · Jul 41 · Aug 99). Not
  outcome-conditioned — every EP the system caught, winners and corpses alike. This is the first
  delayed-entry expectancy read on a non-outcome-conditioned caught-EP population.
- **Instrument:** the lane's OWN pure functions imported from
  `agents/market_intelligence/delayed_entry_shadow.py` (pattern v2) — `session_needs_minutes`,
  `evaluate_session_minute/daily`, `evaluate_session_620`, `compute_settlement`, `to_rth_5min`,
  the rung constants. Nothing re-implemented. Settlement = the lane's two arms: **M-none** (hard
  stop, else 20th-session close) and **M-trail** (same stop + exit on close below MAX(SMA10,20),
  live `exit_logic` semantics). **All R is HARVESTED R, never MFE.**
- **Bars:** `mi_daily_closes` (cohort tickers, 2026-02-15..08-31) + `mi_intraday_bars` 1-min for
  the 3,907 (ticker, session) pairs the walk could need (93.7% present). Captured once via
  read-only SELECTs; replay run entirely from the files.
- **THE ABSTAIN RULE held with full force:** a minute-resolution decision with missing minute bars
  abstains (daily facts fold, no minute-grade fire) — never a daily fallback, never a fabricated
  fill. Result: **8 abstained sessions of 4,745 walked (0.2%)**, 0 fires unsettleable offline,
  0 campaigns unenrollable. Abstention is a non-issue on this population.
- **Maturity split (the de-biasing cut this data forces):** a fire is **MATURE** when 20 post-fire
  sessions existed by 08-31 — its settlement could have gone either way. An immature fire can only
  have settled as a **stop** (a time exit needs 20 sessions), so immature settled rows are losers
  BY CONSTRUCTION. Every expectancy number below is **mature fires only** (n=374 of 602);
  the 228 immature fires (195 already stopped, 33 open — the open rows are the candidate winners)
  are reported as counts, never pooled. **This makes August's expectancy unreadable until ~late
  September** — exactly the live lane's own caveat, inherited honestly.
- **Not replayed:** the lane's bounded re-entry shapes (`same_pattern` / `new_high_break`) — first
  attempts only. Every number understates what a re-entry policy would add (see the ran-hard
  table: 5 monsters whose first fires ALL stopped before the run).
- Era stamped per campaign by alert month. Dead strategies touch nothing here.
- Verification: ALAB's +21.65R (fire, stop, 20-session walk) and QBTS's −1.00R/+9.60R arm split
  reproduced by hand from raw bars before this document was written.

## The numbers

**Recall first (P1): the family fires on 257 of 267 caught EPs (96%), and on 13 of 13 that ran
hard (≥8×ADR20 over the EP close).** Nothing real escapes the rungs. The 10 never-fired campaigns
were flat corpses (max forward high −7.5%..+2.2%) — except NWL 07-31, which faded so hard on EP
day that its close sat near the low and it then ran +18.6% inside the untouchable gap between its
EP close and its far-away EP high: the one structural hole, n=1.

**Then expectancy — and every rung is paying for that recall (mature fires, first attempts):**

| rung | fired (of 267) | med fire session | med stop | M-none mean / med (n) | M-trail mean / med (n) | ≥4R fires (none/trail) |
|---|---|---|---|---|---|---|
| ep_low_reclaim | 203 (76%) | 2 | 2.1% | **−0.39 / −1.00** (130) | −0.25 / −1.00 (130) | 6 / 3 |
| ep_close_reclaim | 144 (54%) | 1 | 2.8% | **−0.44 / −1.00** (86) | **−0.06 / −1.00** (86) | 2 / 8 |
| ep_high_break | 48 (18%) | 1 | 10.8% | **−0.41 / −1.00** (32) | −0.12 / −0.39 (32) | 2 / 0 |
| ep_close_620_prox | 207 (78%) | 2 | 2.1% | **−0.35 / −1.00** (126) | −0.19 / −1.00 (126) | 8 / 5 |
| **family (every fire)** | 257 (96%) | 1–2 | — | **−0.39 / −1.00** (374) | **−0.18 / −1.00** (374) | 18 / 16 |

Plain words: the rungs fire on almost every caught EP within a session or two at a 2–3% stop, and
the **median fire is a full stop-out in every rung, every month, both exit styles**. Taking every
first fire loses 147R (M-none) or 66R (M-trail) over three readable months.

- **The break-even arithmetic (THE GOAL):** M-none wins 10% of fires at mean **+4.74R** per winner;
  at that win rate the winner must average **8.5R**. M-trail wins 24% at mean +2.16R vs **2.9R**
  needed — closer, still short. No rung, no month, no tier/grade cut closes either gap.
- **The tail exists and is catchable:** 18 mature fires harvested ≥4R (M-none), 12 of them in May
  alone — ALAB +21.7R, STUB +11.4R, TE +10.7R (each verified against bars). The two arms
  disagree on WHICH tail: M-none banks the trend-and-hold names; M-trail banks 5 razor-stop
  (0.7–1.8%) spikes M-none round-trips to −1R (QBTS +9.6R vs −1.0R). Neither arm's tail out-earns
  the bleed of taking everything.
- **What each rung misses (P14):** on the 13 ran-hard campaigns, every one fired ≥1 rung, but
  **5 of 13 (NRIX, ALOY, EFOR, HLIT, AKTS) had EVERY first fire stop out before the run** — the
  move happened after the stop-out, which is the re-entry lens this replay does not cover. Best
  settled harvest on the other 7: TE +10.7R, FET +7.1R, ABVX +6.8R, VPG +6.2R, ARM +4.5R,
  HQ +2.1R, BLZE +0.4R (M-none; BLZE's trail arm took +6.0R).
- **Era split — the result does NOT rest on one month being good; it rests on one month being
  less bad.** M-none mean per fire: **May −0.10 (n=180) · Jun −0.56 (n=113) · Jul −0.80 (n=81) ·
  Aug unreadable** (187 settled Aug fires are all stops by construction; 31 open). May's
  near-water-line read is carried by ALAB/STUB/TE, three campaigns from one hot week (05-12..05-20)
  supplying +73R across six fires. Fire rates and stop widths are stable across all four months — the
  MECHANISM (fire everywhere, die at the stop) holds in every era; only the tail supply varied.
- **Adversarial cuts:** drop the best campaign (ALAB, +33.9R settled) → family M-none −0.49
  (n=372). Drop the best month (May) → −0.66 (n=194), ≥4R count 18→6. The NEGATIVE result is
  robust to both cuts; a positive reading of any subset is not.
- **Descriptive selection cuts (selection owns win rate; these are evidence for the fork, not a
  ranking of tactics):** HIGH-tier fires M-none −0.25 (n=251) vs MODERATE −0.66 (n=109); catalyst
  strong/game_changer −0.36 (n=302) vs weaker −0.51 (n=72). Direction says selection helps;
  magnitude says **no ex-ante cut recorded on the alert row turns any rung positive.**

## What this says (and the fork)

The live lane's 09-01 mechanism finding transfers to the caught-EP population **with expectancy
now attached**: the rungs are recall instruments, not selection instruments — they find
essentially every real EP's turn AND every corpse's, and the stop kills the median fire
everywhere. A rung with a decent fire rate and a real tail still loses money taken wholesale.
**The binding constraint is unchanged: a missing SELECTION rule (P13) — plus the re-entry layer,
which is where 5 of the 13 monsters' first-fire losses would have to be recovered.**

Fork for the operator (evidence only, his call):
- **(a)** Let the forward lane accrue to its ~09-23 read before any design commitment (this replay
  predicts what it will find: high fire rates, −1R medians, a thin tail).
- **(b)** Point the next design card at SELECTION + RE-ENTRY over these 602 recorded fires (the
  ex-ante vector is on every row), not at rung definitions — the rungs themselves are adequate.
- **(c)** Treat M-trail's razor-stop tail (5 fires ≥4R that M-none loses) as the one
  management-layer signal worth a follow-up measurement.

## What this does not answer

- **August, at all.** 99 campaigns, 218 fires; every settled row a stop by construction. Readable
  ~late September as windows close.
- **Re-entry economics** — not replayed; the 5 stopped-then-ran monsters put an upper bound on
  what first attempts alone can ever capture, and the campaign study's +12.9R strength-proof
  re-entry finding is untested on this population.
- **Whether any selection rule separates the 18 tail fires from the 356 others ex ante** — the
  tier/grade cuts above are the only stamps available on these rows; the P13 residual is unpriced.
- **The behavioural "near"** — rung 4 here is the ±0.5×ADR placeholder band; a null result
  falsifies the band only (its 8 tail fires are the best per-rung count regardless).
- **Same-day re-entry** — out of the lane's scope by construction, so out of this replay's.
- **Whether May's tail supply was regime or luck** — three campaigns in one week decide it; no
  test on this data can.

## ⚖ THE LINE

Entry/exit discipline, stops, selection rules, sizing and any threshold are the operator's sole
authority. This replay changed nothing: prod access was read-only SELECTs captured once; the
probe and its data live in `scripts/probes/`; the live lane was not touched.

---
*Population: 267 live-source `mi_ep_alerts` rows 2026-05-01..08-31. Instrument: the lane's own
pure functions, pattern v2, settle_v2 semantics. Full tables: `scripts/probes/_562bf_report.txt`.
Related: PLAN #562/#327; `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER` (needs its row
for this doc — ledger edit deliberately left to the main session; this card was scoped to
`scripts/probes/` + `docs/analysis/` only).*
