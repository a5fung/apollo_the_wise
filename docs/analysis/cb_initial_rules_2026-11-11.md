# #717 — the initial breakout rule set, built on the high-confidence Qullamaggie buys (2026-11-11)

His ruling 2026-11-11 on the 21 missed high-confidence buys: *"these are qullamaggie buys, they all look good"* —
Qullamaggie's buys are ground truth; a rule that drops one is the defect. So W, DOCU, SQM (his earlier "no" on
Qullamaggie buys) no longer count against a rule.

**This section is committed BEFORE anything is scored.** Nothing is wired until the score is in; paper stays OFF.

## Method and population
- **The 84 High-tier buys** (n = 84: 53 dated, 31 widened; `scripts/probes/_717_qm_confidence_1111/ratings.tsv`,
  method `docs/analysis/cb_qm_buy_confidence_2026-11-11.md`), each scored at the night D before its rated break day E.
- **Medium tier** (n = 116: 65 dated, 51 widened) — recall reported, no bar.
- **His list grades** (n = 41 name-nights, `tests/fixtures/breakout_list_grades.py` + `_bars.psv.gz`): 28 to reject
  (23 `no` + 5 `conditional`), 13 good / ok. Each chart ends on its list night. All 41 were on the list that night.
- **List night 2026-11-10** (n = 190 names, `scripts/probes/_717_shape_gates_1111/10_sheet_latest_list.out`) — the
  names the CURRENT gates listed, with their bars to that night.
- Not opened: `features_eraB.parquet`, any 2025-26 research store. Strength rank for widened nights: era-A file only.

## The rule set
**(a) The list (night D) — today's gates, loosened just enough to keep the 84:**
| Gate | Today | Initial rule | Why (from the 84, already printed in `03_high_vs_list.out`) |
|---|---|---|---|
| prior move | >= 32.1% | **>= 20%** | lowest High buy 21% (PBR); plateau 20% -> dropped is flat |
| close vs the 50-day | at or above | **DROPPED** | NVAX 2021-04-13 sits 21% under, LCID 10%, HEXO 7%; "3% under" keeps 6 of the 9 it blocks — reported as the alternative, not the rule |
| close vs the 21-day EMA | >= -0.6335 daily ranges | **>= -0.9** | NVAX -0.85 |
| base depth | 1.51 - 8.98 daily ranges | **1.51 - 11** | HEXO 10.8 |
| strength rank >= 35, $2 / $5M, daily range >= 2.1%, 86 sessions of history | - | unchanged | see the exceptions |
**(b) The buy trigger — the High-tier range break:**
- At night D, a **range**: walk back from D (at most 126 sessions); each high above every later high is a level; its
  range starts at the earliest session, among those it stands above, whose high came within one average daily range
  (mean high - low of the 20 sessions ending D) of the level. It qualifies when it is **10+ sessions long** counting
  to E, and **holds its gains** (level - the range's low is no more than half of level - the lowest low of the 60
  sessions before the range).
- **Buy point = the range high.** On E: the high takes it out, the close is above it, and volume is above the
  20-session average ending D. The lowest qualifying level that does so is the buy.
- **Ready to trigger (a list-night reading):** a qualifying range whose high is no more than X average daily ranges
  above the close of D. X = 1.0. If any of the 84 is not ready at 1.0, X becomes the smallest of 1.5 / 2 / 3 that
  keeps all that can be kept — chosen on the 84 ONLY, before the 28 are looked at; the count at each X is printed.

## Exceptions stated in advance (so 84 of 84 is read honestly)
- **PLTR 2021-01-22** has under 86 sessions of history. That is the data guard the pole measure needs, not a setup
  rule; it stays, and PLTR is counted as the one known miss unless he rules the guard down.
- **Unranked widened nights** (BNGO, INO, FCEL, HEXO, SLV at least): the fixtures hold no strength rank and no raw
  close for them, so `rs` and the $2 floor cannot be measured there. They are scored on every other gate and
  listed by name; "kept" for them means "kept by every gate that can be measured".

## Bars
1. **(i) The 84:** every one listed at D by the initial list rules (subject to the two exceptions above, named) AND
   bought on E by the trigger computed from bars <= D by the port — 84 of 84 bought.
2. **(ii) Medium:** listed and bought counts reported.
3. **(iii) His 28 no / not-yet:** how many are LISTED (reported) and how many are READY TO TRIGGER at the list night.
   **Bar: 0 of 28 ready.**
4. **(iv) His 13 good / ok:** listed (bar: 13 of 13) and ready (reported — a good chart need not be ready that night).
5. **(v) 2026-11-10:** of the 190 listed names, how many are ready. The LOOSENED list's size that night cannot be
   measured from this file (it holds only names today's gates listed) — reported as unverified.
- If (i) and (iii) pass: wire it on the branch with tests; paper stays OFF; merge / deploy is his sign-off.
- If not: nothing is enforced, and the charts that break it are named.

## What this does not answer
- Whether the trigger makes money — no bar after E is read.
- The loosened list's nightly size over the whole market.
- Whether the intraday entry (5-minute opening range, volume pace) fires on these days — the score uses daily bars.
- Medium and Low buys: the rule set is crafted on High only ("then expand as needed").
