# #490 — the delayed-screen capture question, re-cut on COMPLETE forward windows (2026-09-15)

**Answer first: the delayed universe screen surfaced ZERO tail winners we missed, over 36 trading
days, on windows that are now complete rather than censored — but n=33 is too thin to call the feed
costless, and it never touched the failure mode that actually cost him a trade.**

This re-runs `490_delayed_screen_cost_2026-08-18.md` under its own pre-registered closing rule, now
that the forward windows have matured. MEASURE-ONLY, $0, read-only. Nothing here proposes a flip:
admission is entry discipline = THE LINE.

## Population — §0, declared before the first measuring query

| | |
|---|---|
| **Cohort** | `ep_rt_universe_catch` shadow events, **2026-07-27 → 2026-08-18** — real-time ≥10% gap crossers the ~15-min-delayed universe screen did NOT hold as candidates at that tick |
| **Size** | 261 raw events → **252 settled ticker-days** (30 alerted the same day anyway, **222 never alerted**) |
| **The measured set** | never-alerted **AND** still ≥10% at the actual open **AND** passing the replayed mechanical gates = **33 names** |
| **Statistic** | `tailx` = (max high over sessions d+1..d+20 − close(d)) / close(d) / ADR% — a tail winner is **≥8×ADR**, the programme's own bar |
| **Comparison sets** | the 30 alerted crossers, and all 103 live alerts over the same dates, through the **same machinery on the same dates** |

**ERA CHECK — this question is single-era, and that is why it can be answered tonight.**
`tailx` is a price-only measure: it asks what the stock DID, never how we would have exited it. So
the 2026-09-06 exit flip (#545, +2R partial → +8R, price-armed breakeven) cannot contaminate it.
The admission side is single-era too: `MIN_GAP_PCT` moved 10.0 → 9.0 on **2026-08-19**, entirely
AFTER the cohort closes on 08-18. Both boundaries checked against `rule_eras.py`, not assumed.

**WHAT CHANGED SINCE 08-18 — the censoring, and only the censoring.** Four of the five captured
TSVs are fixed by the cohort window and were reused untouched. Only the daily-bar leg was
re-captured from prod (15,646 → 27,940 rows, now running to 2026-09-15). On 08-18 **no** name had a
full 20-session forward window and every share was explicitly a floor. Now **fwd_n median = 20** and
only 1 of 33 is still short. The floors have become final numbers.

## THE RESULT

| set | n | ≥8×ADR | median tailx | P90 |
|---|---|---|---|---|
| **never-alerted, held the open, passed the gates** | **33** | **0 (0.0%)** | 1.47× | 4.32× |
| never-alerted, held the open, pre-gates | 52 | 1 (1.9%) | 1.49× | 5.00× |
| never-alerted, faded at the open but crossed intraday | 138 | 5 (3.6%) | 1.96× | 6.27× |
| the alerted crossers | 30 | 2 (6.7%) | 2.03× | 6.55× |
| **all live alerts, same dates** | **103** | **3 (2.9%)** | 1.91× | 5.31× |

**Prize, in the programme's own terms:** 0 additional tail winners per month from the delayed
screen's blind spot, against the alerted book's **1.8/month**.

**33 is an UPPER bound on the would-have-alerted set** — the LLM catalyst grade, the RVOL pace gates
and the top-20 rank cap were not replayed ($0 limit). Zero out of an upper bound is zero out of every
subset, so the bound makes this conclusion stronger, not weaker.

## ⚠ THE LIMIT ON WHAT THIS CAN CLAIM — stated because a zero is not a proof

At the alerted population's own rate of 2.9%, **33 names are EXPECTED to yield about 1 tail winner**.
Observing 0 has probability 0.38 under that base rate alone — `Fisher(0/33 vs 3/103) p = 1.00`.

- ✅ **Supported: the capture argument has no evidence FOR it.** After 36 trading days and matured
  windows, nothing the delayed screen hid has turned into a tail winner.
- ⛔ **NOT supported: "the delayed feed costs us nothing."** This cohort cannot distinguish zero from
  the normal rate. Separating them at p<0.05 needs **~102 gate-passing survivors**; they accrue at
  ~33 per 36 trading days, so that is roughly **3.5 more months**.
- Anyone citing "0 tail winners" as proof the feed is costless is citing a number this study does not
  contain. [[check-what-the-system-already-did]]

## What this does not answer — 🔴 starting with the population that actually cost him a trade

**TWST 2026-08-19 is not in this study and must not be judged by it.** TWST *alerted*; it alerted
fifteen minutes late, because `ep_rt_floor_flip_up` read 10.69% at 09:30:04 while the delayed feed
still read 9.34%, and only the delayed number is authoritative. Admission fired 09:45:11 — eleven
seconds past the ORB window. This study measures **NEVER-ALERTED** names. Different population,
different failure mode; #559 already records that the 08-18 read must not be cited against it, and
that still holds with complete windows.

Two more things this does not reach:
- **The faded-but-crossed class (138 names, 5 tail winners)** is the floor-timing fork, not a feed
  question — `ep_rt_entry_gap_recheck` removes sub-10%-at-entry names under the current rule whatever
  feed supplies the number. Its 3.6% is statistically indistinguishable from our own book's 2.9%
  (`p = 1.00`), so it is not a hidden seam either.
- **ANIK 2026-07-29 reached 10.3×ADR** and was excluded by my replayed gates on ADV$ ($0.86M < $1M)
  and market cap ($288M < $500M). One name, two operator-signed floors, noted not argued.
- **The ops / latency case for a cutover is untouched and ungated** — fill quality, slippage, feed
  cost. It was never part of the capture argument and the operator can raise it at any time.

## Reproducing

`python3 scripts/probes/_490_delayed_cost_funnel.py` — deterministic on the captured TSVs.
⚠ `scripts/probes/_490cost_daily.tsv` was **re-captured 2026-09-15**; the 08-18 doc's censored
numbers can no longer be reproduced from the repo, which is the intended trade (the capture is
strictly a superset of the old one, extended forward).
