# #715 — flip-up entries replayed under today's rules vs three alternatives (2026-10-31, $0)

**REC (pre-registered rule): (b) — refuse a flip-up whose 09:30 open is below the floor price. Its whole effect is 4 removed trades (3 losers, 1 small winner), and it turns on CEG's open sitting 0.2% below the floor — admit CEG and the rule says keep today's rule. Decision is his (THE LINE).**

- Population: the 51 flip-ups that became HIGH since 2026-08-02, replayed from stored minute + daily bars under TODAY's entry mechanics and the CURRENT depth exit (the #482 recorder's own walker), 20-session decision horizon.
- All four calibration checks passed before any outcome was read; one fill (CRWD) reproduces only with the stored live price (§5).
- Script `s2_replay.py` → `s2_replay.txt`; per-row `s2_rows.tsv`.

## 1. What the 51 are (stated before any outcome)

| split | count (of 51) |
|---|---|
| admission era: real-time gap NOT yet authoritative (through 08-27) / authoritative (from 09-03) | 32 / 19 |
| floor on the day: 10% (before 08-20) / 9% | 26 / 25 |
| the REGN shape — ORB high BELOW the floor price / ORB high at or above it | 22 / 29 |
| 09:30 bar open at or above the floor price / below it | 24 / 27 |
| first minute a bar's high reached the floor price: the 09:30 bar / 09:31–09:44 / never in regular hours (pre-market only) | 29 / 16 / 6 |
| inside the ORB window (order could go in before 09:45) / detected too late | 34 / 17 |
| stored fate today: filled / chase-cap refused / gap re-check refused / out of window / stop too wide / blocked by cap or breaker / no bar / broker rejected / unfilled cancel / no trade row | 10 / 3 / 10 / 17 / 1 / 3 / 3 / 1 / 2 / 1 |
| REGN-shape rows that were also inside the window (the rows an anchor change can touch) | 15 |
| minute-bar coverage: have the 09:30 bar / have all 30 bars 09:30–10:00 | 51 / 45 (6 short by 1–4 bars) |

## 2. The table (budget-R = profit per share ÷ the planned risk per share, so every option is at equal dollars; 20 sessions)

| option | entries (of 51) | same outcome as today (of 51) | settled / horizon / pending / abstain | win share | big winners ≥ +3R (settled \| marked) | tail R Σ(R−3)⁺ | sum R (settled) | worst loss | names added / dropped vs today | ≥ +3R at 40 sessions |
|---|---|---|---|---|---|---|---|---|---|---|
| **today** (09:30 bar anchor) | 16 | — | 16 / 0 / 0 / 0 | 4 of 16 (25%) | 0 \| 0 | 0.00 | **−6.09** (n=16) | −1.44 (HOOD) | — | 0 of 16 |
| **(a)** anchor on the bar that crossed the floor | 20 | 45 | 20 / 0 / 0 / 0 | 6 of 20 (30%) | 2 (FTK +3.49, U +3.88) \| 0 | +1.37 | **−0.33** (n=20) | −1.43 (IONQ) | adds FTK, U, IONQ, SPCX; re-anchors HOOD, PENG; drops none | 2 of 20 |
| **(b)** 09:30 open must be at/above the floor | 12 | 47 | 12 / 0 / 0 / 0 | 3 of 12 (25%) | 0 \| 0 | 0.00 | **−3.12** (n=12) | −1.10 (INSM) | drops HOOD −1.44, PENG −1.26, CEG −1.08, CLS +0.80 (sum −2.98, n=4); adds none | 0 of 12 |
| **(c)** chase cap measured from the floor | 17 | 50 | 16 / 0 / 1 / 0 | 4 of 16 (25%) | 0 \| 0 | 0.00 | **−6.09** (n=16) | −1.44 (HOOD) | adds REGN (filled 10-30 at $925.38, still open — a full stop-out would cost −2.06 R) | 0 of 16 |
| (c′) same, sized on the floor risk | 17 | 50 | 16 / 0 / 1 / 0 | 4 of 16 (25%) | 0 \| 0 | 0.00 | −5.81 (n=16) | −1.28 (HOOD) | sensitivity row; REGN's full stop-out would cost −1.44 R | 0 of 16 |

- Every entry settled inside 20 sessions except REGN under (c) (filled Friday, no forward session yet); nothing is marked — the horizon is complete for 16 of today's 16.
- Harness-independent check (best high within 20 sessions, before the stop): today reached +3R first on 3 of 16, stopped first on 11; (a) 5 of 20 / 13; (b) 3 of 12 / 8; (c) 3 of 17 / 11.

**The two cohorts disagree on (a), so the post-08-27 cohort decides (§6):**

| cohort | today sum R | (a) sum R | (b) sum R | (c) sum R |
|---|---|---|---|---|
| real-time gap authoritative (from 09-03, n=19; today enters 6) | −3.98 (n=6) | −5.58 (n=8) — adds IONQ −1.43, SPCX −1.00 | −1.00 (n=2) | −3.98 (n=6, REGN pending) |
| before authority (through 08-27, n=32; today enters 10) | −2.12 (n=10) | +5.25 (n=12) — adds FTK +3.49, U +3.88 | −2.12 (n=10, unchanged) | −2.12 (n=10, unchanged) |

## 3. The rec (pre-registered §6 rule, applied as written)

**REC: (b) — only enter a flip-up whose 09:30 open is at or above the floor price; every other mechanic unchanged.**

- (b) clears all five tests: enters 12 (≥ 10), all settled; the 4 names it removes sum to −2.98 R with no big winner; tail unchanged; sum −3.12 vs the bar −4.09 (today −6.09 + 2.0); worst −1.10.
- (a) clears on the 51 (−0.33 vs −6.09, 2 big winners) but its gain is two pre-authority names (FTK, U) and it loses in the post-08-27 cohort (−5.58 vs −3.98): pre +7.37 / post −1.61, the post cohort decides → out.
- (c) and (c′) fail the sum test — REGN is their only change and it is one open trade (filled 10-30).
- Fragility: CEG's open is 0.20% below (b)'s line (291.11 vs 291.71, official daily open also 291.11). Admit it and (b) enters 13 with sum −4.19 vs the bar −4.09 → fails → the rule would say keep today's rule. The next-closest of today's entries sit +0.99% (CRWD) and +1.06% (MRVL) above the line.
- A change still needs his sign-off + CHANGE_PROCESS (N ≥ 10; (b) has 12).

## 4. Rows whose verdict depends on the minute proxy (no live quote stored)

- CEG 10-06 under (b): the admission line, not the proxy — 0.20% below the floor on both the 09:30 bar and the official open (above).
- CRWD 08-27: live went in by the limit path at $213.31; the replay's proxy (the 09:30 close, exactly on the ORB high) takes the stop-limit path and fills $211.47 — 0.86% off, outside the 0.5% bar; with the stored live price the replay reproduces $213.80 (0.23%). Its R is 0.00 either way (breakeven stop).
- EROC 08-12: live refused it under the old ORB-low stop (1.83×); today's 2R stop admits the same $13.50 limit (1.41×). The replay fills it at $13.23 by stop-limit (the proxy sat below the ORB high; the live ask did not) — its +1.56 R is on a fill ~2% below what the ask path would give.
- IONQ under (a): admitted at 1.43× of the crossing-bar risk on the proxy, 1.22× on the stored price — admitted either way; it lost −1.43 R the same day.
- REGN under (c): admitted at 1.44× of the floor-based risk on the proxy, 1.48× on the stored price (cap 1.5×) — admitted either way; outcome pending.
- Replay enters 5 names the live system stopped for non-setup reasons (ZBRA, KTOS, TATT blocked by cap/breaker; INSM venue-rejected; CRMD no bar) and gap-rechecks out 3 (FTK, CGEM, RARE) — all stay in every option's population by the "real EPs regardless of safeguards" rule.

## 5. Calibration (all passed before the option table was read)

- Population: 51 rows, 51 with the 09:30 bar, 19,103 minute bars complete, last settled session 2026-10-30.
- Stored 09:30 bar = the live ORB read on 32 of 32 ticker-days that reached the fetch.
- ATR14 replica = the stored value on 16 of 16 trade rows (ATRO's "1.5× ATR $5.29" reproduced).
- Today's rule reproduced the stored setup/window fate on 42 of 43 rows exactly (all 9 other fills within 0.5%: BTDR, ABCL, MRVL, HOOD, SEI, DFTX, CEG, PENG, CLS); CRWD only with the stored live price (§4). REGN refuses at 2.06× planned (plan: must refuse ≥ 1.5×).
- Proxy for the live price at submit: the pre-registered rule flipped to the sensitivity proxy (close of the alert-minute bar) — median error 0.318% vs 0.476% for the submit-minute open on the 7 registered rows (0.097% vs 0.643% on all 20 rows with a stored price).
- Depth-exit walk = the recorder's own live_replay row on CLS (the one depth-era fill): +0.857 own-R, trail exit, session 2 — exact.
- Added AFTER the outcomes marker (stated for honesty): the implementation of §6's cohort clause on the rec line (the clause itself is pre-registered; its effect was to drop (a) from "also cleared") and a guard that (b)'s rule 2 is not evaluable while a dropped name is pending (no effect this run — all 4 settled). Neither changed the rec: (b) wins the (b) < (c) < (a) tie-break regardless. The CEG sensitivity in §3 is post-hoc too.

## 6. What the data cannot answer

- (b)'s verdict turns on CEG's open being 0.20% below the floor; one tick the other way and the rule says keep today's rule.
- The true live price at submit: only a minute proxy exists; CRWD's and EROC's fills and any cap verdict within ~0.2% of the limit move on a tick (none of the 51 sat inside that band).
- Limit-fallback fills are assumed at the limit; the ask-aware path and partial fills are not modelled (EROC's live path was the ask).
- The walk reproduces the recorder's MODEL of the depth exit (check 2 exact on CLS), not the live trade: CLS actually stopped at $265.635 on 10-30 (−0.29 own-R) where the model books a +0.86 trail sale. With the live figure (b)'s dropped sum is about −4.1 R instead of −2.98 — more negative, direction unchanged.
- The 16:00 closing bar is not in the capture (day-0 walks end 15:59).
- Six names (CGEM, RARE, DG, AGX, SRRK, INIO) only crossed the floor pre-market — (a) has no anchor for them.
- (b)'s whole effect is 4 removed trades (HOOD, PENG, CEG, CLS), all from the post-08-27 cohort; (a)'s whole gain is 2 pre-authority names (FTK, U) that today's gap re-check refuses.
- REGN under (c) is one open trade (filled 10-30); (c)'s verdict cannot change until it settles.
- Whether a name would still have graded HIGH under a different anchor, size/account effects, and the admission era (10%→9% floor 08-19, authority 08-27) — the replay applies today's entry + exit mechanics to names admitted under their day's rules; the era split is shown, not pooled.
