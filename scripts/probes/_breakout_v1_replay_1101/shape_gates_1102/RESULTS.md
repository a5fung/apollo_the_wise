# Breakout v1 — three shape gates from his MTW read: RESULTS (2026-11-02)

**Verdict: none of the four candidates passes the bar fixed in DEFINITIONS.md. Nothing to ship as tested.**
The closest is G1 (riding the average): it reads his MTW reason, keeps 10 of his 12, and improves the paper book in
both eras — but the trades it removes were NOT worse than the ones it keeps, and the same share removed at random
improves the book about as much. So the book gain is from having fewer names, not better ones.

Definitions (fixed before any outcome): DEFINITIONS.md. Code: gates_patch.py (the backtest imports it). Inputs: the
frozen replay (out/list_eraA/B, out/trades), sealed stores; MTW from `_mtw_1102/mtw_bars.csv` to 10-30 only.
Every candidate sits on top of the 4.26% daily-range floor (live since 11-02). MTW is ALREADY off the list under that
floor (its daily range was 4.06%); these gates are about its shape.

## The gates in one line each

- **G1 riding**: last 10 sessions, every close at/above the 10-day (or the 20-day), no low more than 0.5 of a day's
  range under it.
- **G2 rising lows**: three 5-session blocks (last 15 sessions), each block's lowest low higher than the one before.
- **G3 no failed attempt**: if the last 5 sessions traded above the base's earlier ceiling and the stock closed back
  under it, skip.

## Pass / fail against the bar

| Candidate | (a) MTW fails | (b) his 12 kept (need 10) | (c1) paper book vs floor-only, 2017-21 / 2022-24 (need >= -0.139 / -0.340) | (c2) removed trades worse than kept | (c3) >= 100 trades per era | Verdict |
|---|---|---|---|---|---|---|
| G1 riding | PASS | **10** PASS | -0.085 / -0.172 PASS | FAIL (removed -0.098 vs kept -0.123) | 818 / 444 PASS | FAIL (c2) |
| G2 rising lows | PASS | **7** FAIL | -0.090 / -0.263 PASS | PASS, barely (-0.120 vs -0.111) | 847 / 469 PASS | FAIL (b) |
| G3 no failed attempt | PASS | **11** PASS | -0.090 / **-0.346** FAIL | FAIL (-0.055 vs -0.122) | 986 / 537 PASS | FAIL (c1, c2) |
| All three | PASS | **6** FAIL | -0.129 / -0.228 PASS | FAIL (-0.094 vs -0.137) | 763 / 408 PASS | FAIL (b, c2) |

R = the trade's result in units of its risk, at 2 cents a share. Baseline reproduced exactly (5-slot 983 trades at
-0.139 and 556 at -0.340; guard-only 4,029 at -0.092; the floor's removed 919 at -0.464).

## The paper book (5 slots, 2 cents) beside the floor-only baseline

| Book | 2017-21 trades / avg R / 3R+ share | 2022-24 trades / avg R / 3R+ share |
|---|---|---|
| Floor only (BASELINE) | 983 / -0.139 / 4.7% | 556 / -0.340 / 4.1% |
| G1 riding | 818 / -0.085 / 5.3% | 444 / -0.172 / 5.6% |
| G2 rising lows | 847 / -0.090 / 4.8% | 469 / -0.263 / 4.9% |
| G3 no failed attempt | 986 / -0.090 / 4.9% | 537 / -0.346 / 3.7% |
| All three | 763 / -0.129 / 5.2% | 408 / -0.228 / 4.7% |

## Removed vs kept, every list name-day (no slot limit, 2 cents, from the floor-kept set)

List rows (all 61,071, before the floor) passing: G1 61%, G2 64%, G3 78%, all three 36%.

| Gate | Orders removed | Kept: trades / avg R / win / 3R+ / 10R+ | Removed: trades / avg R / win / 3R+ / 10R+ |
|---|---|---|---|
| G1 riding | 5,160 (35%) | 3,332 / -0.123 / 34.5% / 5.3% / 37 | 1,902 / -0.098 / 34.2% / 4.5% / 27 |
| G2 rising lows | 4,823 (33%) | 3,442 / -0.111 / 34.8% / 5.0% / 41 | 1,792 / -0.120 / 33.5% / 4.9% / 23 |
| G3 no failed attempt | 2,201 (15%) | 4,596 / -0.122 / 33.4% / 4.9% / 59 | 638 / -0.055 / 41.5% / 5.5% / 5 |
| All three | 8,086 (55%) | 2,380 / -0.137 / 33.4% / 5.1% / 28 | 2,854 / -0.094 / 35.1% / 4.9% / 36 |

Per era (shape_gates_effect.txt): in 2017-21 every gate's removed trades did BETTER than its kept ones; in 2022-24
G2 and G3 removed worse trades, G1 about equal.

## After-the-fact check (not part of the bar): is the book gain more than thinning?

Same share of orders removed at random, 200 draws, 5-slot book. Share of random draws at least as good as the gate:
G1 46% (2017-21) / 14% (2022-24); G2 50% / 62%; G3 33% / 92%; all three 70% / 46%. No gate beats random thinning
clearly in either era. Random thinning alone moves the 2017-21 book from -0.139 to about -0.09 — an observation for
the main loop, outside this card: the 5-slot cap seems to admit worse names first when the list is crowded (a property of
the book, not of any gate). No action from this card.

## Label checks

- **MTW 10-30 (his "not a breakout")**: fails ALL three new gates. G1: one close under the 10-day and four lows more
  than half a day's range under it (20-day: three closes under). G2: block lows 21.28 / 21.05 / 21.99 — the middle
  block undercut. G3: 10-29 traded $23.875 over the $23.114 base ceiling, 10-30 closed $23.03 (8 cents under; thin).
  Parity: the live list row's pole (10-06), base low (21.05), level (23.875) and surf run (10) reproduced exactly.
- **ZCSH (his positive example)**: not in either store (a 2026 fund) — not checked.
- **His 12 good setups v1 already catches** (labels.txt):

| Setup (D) | G1 | G2 | G3 | Why it fails |
|---|---|---|---|---|
| CELH-1 (2020-06-22) | pass | pass | FAIL | closed 3.38 under a 3.403 ceiling after a 3.50 push |
| CELH-3 (2020-08-04) | pass | FAIL | pass | middle block low 4.400 vs 4.403 — a one-cent undercut |
| CODX-1 (2020-04-15) | FAIL | FAIL | pass | closes under both averages; middle block undercut |
| LVGO-4 (2020-07-02) | pass | pass | pass | |
| OPK-2 (2020-07-16) | pass | pass | pass | |
| OSTK-2 (2020-06-22) | pass | FAIL | pass | middle block undercut (18.84 vs 19.42) |
| SRNE-2 (2020-07-30) | pass | pass | pass | |
| PRTS (2020-07-07) | pass | FAIL | pass | middle block undercut (81.9 vs 84.0) |
| ARCT (2020-07-10) | pass | pass | pass | |
| HL (2020-08-03) | pass | pass | pass | |
| IBIO-1 (2020-07-14) | pass | pass | pass | |
| PENN-2 (2020-06-22) | FAIL | FAIL | pass | closes under both averages; middle block undercut |

Kept: G1 10, G2 7, G3 11, all three 6.

What it says: G2 as written throws out his own good setups — all 5 it loses made a lower low in the MIDDLE of the
base and then recovered (a shakeout under the lows), which a strict "each block higher" reading cannot tell apart from
MTW's October. G3 catches MTW only by 8 cents.

## A correction disclosed

DEFINITIONS.md quoted the floor-only "all trades -0.092R (4,029)" as the c2 reference; that figure is the same-ticker-guard
book, not every name-day. c2 is judged like for like (removed vs kept, both every name-day, no guard), which is how the
floor's own "removed 919 at -0.464" was measured. The bar's direction is unchanged; under the guard book G1's kept set is
-0.100 vs the floor-only -0.092 (also no better).

## Action (the operator's call — THE LINE: paper rules are his)

- Rec: hold to the bar — nothing ships from this card; the 4.26% floor already keeps MTW off.
- If he wants a detection-only change regardless of returns, G1 is the only one that reads his MTW reason and keeps 10
  of his 12 (no measured return gain on the replay).
- G2 / G3 need a rework before any use (G2 loses his own shakeout bases; G3 is an 8-cent call on MTW and its removed
  trades were better). Not re-tuned here — any new constant would be fitted after seeing outcomes.
