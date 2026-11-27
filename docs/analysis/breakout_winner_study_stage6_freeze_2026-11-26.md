# Breakout big-winner study — stage 6 FREEZE (2026-11-26; operator OK "go with rec" on the main form, no pause)

Frozen BEFORE any check-period (2021-2024) outcome is read. Prereg `3eb2b9b0…` + A1 `4a7beda1…` + A2 `0a6cc417…` + A3 `a0c11a36…`.

## The family, m = 6 (Holm, one-sided, frozen directions)
1. f01 daily range — HIGH
2. f09 6-month move — HIGH
3. f04 strength rank, best — HIGH
4. f02 price — LOW
5. the §5.6 combination of 1-4 (equal-weight mean of signed within-month percentile ranks)
6. gallery read #1, gr1 "V into the breakout" (below) — NOT-V rate ÷ V rate (V has FEWER big winners)

The ruling slot and the gallery-read slots CLOSE here. Anything ruled after the check run is description, outside the family.

## Method and population
Seed-1124 kept events: discovery 5,330 (2017–2020, outcomes seen), check 6,266 (era A 2,910 2021–2022Q1, era B 3,356 2022–2024). gr1 flags 577 of the check events (9.2%), 0 NULL.

## Pinned files (sha256)
```
ff342a19c08ad7d707c32aff4e956e9087cb14271987d3e21e68082303c035a2  gr1.py
c290946c49eeb8cba771d36ca2f8abc1c247471966434afcc1eff0b5b874b619  common6.py
9c4d25188c9e938ae1e453e58f0e5746b9612515e3dd9819fdc2b686d881a851  gr1_components.tsv.gz
7a290dfe4a2c06b4ede71514bd462ac6fa814ef5bb39d212b17879dedd12ac9f  s6a_build.py
```

## His words (2026-11-26, after the first pairs of winner gallery A)
"when buying breakout from a v-shaped rally, it's prone to failure, the reason maybe the sharp rally (after sharp drop) already used up
the momentum, and it's time for the stock to consolidate if it were to move up again ... there's still some that worked, but mostly it
didn't". Direction HE states: V into the breakout -> FEWER big winners.

## Plain words
The stock made its lowest low of the last four months within the last three months, after falling at least five of its daily ranges
in under five weeks; it has already rallied back at least half of that fall by the buy level; and it only got back to the level in
the last two weeks — it has not rested there.

## Exact form (code: `gr1.py::v_parts` + `flag`; bars <= D only; open(E) NOT used)
Inputs: the name's adjusted daily bars with calendar index <= ci(D); `level(D)` and `ADR20(D)` (a fraction) as the live `v1_gates`
returns them from those same cut bars. Window W = the 85 calendar sessions D-84 .. D (the list's own guaranteed history, `DEEP`).
- T = the LATEST session in W whose low equals the lowest low of W.  `trough_age` = D - T.
- H1 = the highest high of the 25 sessions T-25 .. T-1.
- `drop_adr`  = (H1 - low(T)) / H1 / ADR20(D)
- `recover`   = (level(D) - low(T)) / (H1 - low(T))
- A = the first session after T whose high >= level(D) x (1 - 1.0 x ADR20(D));  `at_level` = D - A  (0 when no session qualifies)
**gr1 = 1 (V into the breakout) when ALL of:**
1. `trough_age` <= 59            (the low of the last 85 sessions was made in the last 60)
2. `drop_adr`  >= 5.0            (a sharp drop: five daily ranges or more, from a high at most 25 sessions before the low)
3. `recover`   >= 0.5            (a sharp rally: the buy level takes back at least half of the drop, within 60 sessions)
4. `at_level`  <= 9              (no consolidation: under 10 sessions since price first got back to within one daily range of the level)
**gr1 = 0 otherwise.** NULL (stage 1f's calendar rules on W): history | coverage (any missing session in W) | adjustment flag in W |
guard break in W | bad price | no ADR / no level.
Two groups; statistic = the Mantel-Haenszel ratio by (era, month) of prereg 5.1, stated in his direction: **rate of NOT-V ÷ rate of V**
(over 1.0 = V has fewer big winners).

## Where each threshold comes from (his words, the charts' shape, the list's own constants — never an outcome)
- 85 / 60 sessions: W is the list's own deepest look-back (no new history rule, no NULLs); the Vs on the sheets he saw (pairs 1-2) have
  their low 16-56 sessions before the break (read off the charts by pixel, then measured: the face check in `6b_coverage.txt`).
- 25 sessions for the drop leg: "sharp drop" = about a month or less; 60 + 25 = 85 fits W exactly.
- 5 daily ranges: ADR-relative, as base depth is (the list's band is 1.5-11 ranges); 5 ranges in under five weeks is a drop no trader
  calls a pullback. NOT a percent: a percent threshold would mostly re-measure daily range (f01, carried, high third wins).
- half of the drop taken back: the plain meaning of a V. First written as two-thirds; at the face check three charts that are Vs to the
  eye read 0.65-0.67 (two from failure sheets, one from a winner sheet), so it was set to one-half. Moved on SHAPE, before the outcome join;
  the chart ids carry their sheet, so the roles of those 48 charts were visible to me — said here, and the discovery numbers print "seen".
- under 10 sessions at the level: the list's own minimum base is 10 sessions (`BASE_MIN`); fewer than that at the level is "no base".
  One daily range under the level = "at the level" (the same unit as B4).

## Alternatives considered
- **ALT-1 "V, pause allowed" = conditions 1-3 only (no condition 4).** The same V, but a stock that got back to the level and then chopped
  there for two to eight weeks still counts. Rejected as the main form because he says the V's problem is that the stock has NOT yet
  consolidated — a V followed by three weeks or more at the level has started to — but it is THE fork for his OK: on a 250-session chart a
  three-week pause is small and he may well have been counting those as Vs. It flags about 2.4x as many events (coverage printed), so it
  is also the better-powered form. Its discovery numbers are NOT printed (one definition's outcomes seen, not two).
- **ALT-2 reuse existing columns** (20-session run-up f08 high, or base depth f13 deep, or sessions since the 52-week low f22 small).
  Rejected: none has a drop leg — f08 high is any fast rally, f13 deep is any deep base — so none is "a sharp rally AFTER a sharp drop";
  f22 is NULL for 25 months of era B. (f08 and f13 were also already read on discovery, in the direction opposite to his.)
- **ALT-3 one numeric (rally speed = daily ranges gained from the low to the level ÷ sessions since the low).** Rejected: it has no
  consolidation term and no natural cut; "V or not" is how he said it.

## What this does not answer
- Every event already has a pole top 10-45 sessions back and a pullback of 1.5+ ranges (the list's gates), so a V here is mostly "the
  base IS the V" — the low sits inside the list's base. A V whose rally topped 10+ sessions ago within one range of the level is NOT flagged.
- ADR20(D) is measured on the rally leg, where ranges are wide: the 5-range bar is harder to meet right after a crash than in calm tape.
- `recover` and `at_level` use the level, so the flag is tied to how far close(D) is from the level (B4): the B4-third split prints at check.
- Rare by construction (coverage printed): small group, weak power — the smallest detectable ratio prints beside it.

## Added after the runs (2026-11-26; the definition and thresholds above were NOT changed)
- **What the author could see when the form was kept (wider than the recover note above):** 48 gallery charts (pairs 1-2) were opened to learn the
  shape, and their ids carry the sheet (winner / failure). The components of those 48 were printed BEFORE the eye list was written to a file, and
  the face-check table (`6b_coverage.txt`) shows the main form flagging 7 failure-sheet charts and 1 winner-sheet chart, ALT-1 11 and 5. The main
  form (condition 4 = 9, in `gr1.py` from its first write) was kept with that table on screen. No outcome FILE was open, but this is not blind:
  the discovery numbers are "seen" for that reason too.
- **Threshold grid viewed before the join (coverage only):** 18 combinations, `6b_pre_join_grid.txt`.
- **The flag leans to low-daily-range names** (12.4% / 10.7% / 7.7% flagged across the daily-range thirds) and high daily range is the study's
  strongest carried reading, so part of any ratio is that reading's echo: the discovery ratio is 1.43 by month and 1.29 by month x daily-range third.
- **11 of the 1,192 flagged events have their low within the last 4 sessions** (70 within 9): there the level was set before the low, so "rally
  into the level" is one or two days old. Left as is; a limit, not patched.
