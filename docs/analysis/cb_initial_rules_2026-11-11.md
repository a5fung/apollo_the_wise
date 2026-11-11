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

---
# RESULT (scored once; `scripts/probes/_717_qm_confidence_1111/10_initial_rules.out`, `11_ready_sheet_1110.out`)
**FAIL on (i) the list half and on (iii). Nothing is wired; no gate changed; paper stays OFF.**

| Bar | Result | Verdict |
|---|---|---|
| (i) the 84 bought on E by the trigger port (n = 84) | 84 of 84, same buy point as the rating | pass |
| (i) the 84 listed at D by the loosened gates (n = 84) | **80 of 84** (79 counting FCEL) | **fail** — PLTR (the named history exception) + BNGO 2019-12-30, INO 2020-01-21, HEXO 2020-08-13 under the $5M dollar-volume floor (20-session median $1.5M, $3.6M, $4.4M); FCEL 2020-02-10 is scored as kept only because its night has no raw close — its raw buy point is $1.95, under the $2 floor |
| (ii) Medium listed (n = 65 dated / 51 widened) | 65 / 42 (today 65 / 34 by this scorer, which leaves the strength rank out on unranked nights; with it, 32 of 51 the night before the break) | reported |
| (ii) Medium ready the night before / bought by the High trigger | 53 / 31 ready; 0 bought (a Medium buy is by definition short of the High trigger) | reported |
| (iii) his 28 no / not-yet LISTED (n = 28) | 28 of 28 | reported |
| (iii) his 28 READY to trigger (n = 28) | **11 of 28** at the X the 84 force (3.0); 1 / 6 / 9 at X = 1.0 / 1.5 / 2.0 | **fail** (bar 0) |
| (iv) his 13 good / ok listed / ready (n = 13) | 13 listed; 6 ready (2 / 5 / 6 at X = 1.0 / 1.5 / 2.0) | listed pass |
| (v) 2026-11-10, ready of the 190 listed (n = 190) | 48 at X = 3.0 (23 / 33 / 41 at 1.0 / 1.5 / 2.0) | reported |

- **(iii) has two readings.** At the definition as given (within ONE day's range of the close) it is 1 of 28 (AMLX) —
  but only 47 of the 84 are ready at that distance. At the 3.0 the pre-registered escalation forced, it is 11 of 28.
  The trigger itself bought 84 of 84 with no distance condition. Whether "ready" is a gate or only a description is
  his / the main loop's call; either way the bar of 0 is missed.
- **"84 of 84 bought" is port parity:** the High tier IS the trigger, so it shows the port matches the rating, not
  that the trigger is selective.
- **X had to go to 3.0:** the buy point sits a median 0.87 daily ranges above the prior close for the 84, but 37 are
  further than 1.0, 5 further than 1.5, and CCJ 2021-10-12 is 2.5 away. At X = 1.0 only 47 of the 84 are ready.
- **The charts that break (iii):** PAY 11-06 and PLSE 11-10, VEEV 11-10 (not-yet); RSKD 11-06, CVLT 11-05, MANE 11-05,
  ABCL 11-09, DOCS, CTSH, AMLX, APPN 11-10 (no). AMLX is ready even at X = 1.0 (range high 31.22, 0.2 away).
- **Why:** "a range of 10+ sessions that holds its gains, with its high near the close" is true of 11 of his 28
  rejected charts and 6 of his 13 good ones — the night-before reading does not tell his no from his good. Everything
  that made the 84 High is in the bar of the break day itself (takes the level out, closes above it, on volume),
  which no list-night chart has yet. The rating was built to recognise a breakout AFTER it happened.
- **The 50-day alternative** (3% under instead of dropped) lists 78 of 84 — NVAX 2021-04-13 and LCID 2022-01-10 go too.
- **The $5M floor** was not in the pre-registration; three High buys fail it. It is a tradability rule, so it is
  named here and not loosened.
- **Sheet:** `scripts/probes/_717_qm_confidence_1111/ready_sheet_1110.png` — the 12 highest-ranked ready names on
  11-10. Eight of the twelve are charts he has already graded: 2 ok (CVLT, EVH), 6 no / not-yet (DOCS, VEEV, AMLX,
  PLSE, CTSH, APPN); MANE is the 11-05 `no` ticker a few sessions later. New to him: OABI, AVAH, KOD.
- Tests: `pytest tests -q -x -k "breakout or consolidation"` — 759 passed, 1 xfailed. No production code was touched, so
  this confirms only that nothing changed.

## Not verified
- The loosened list's size on 11-10 or any night (the file holds only today's listed names).
- Whether the intraday entry would have fired on the 84 break days.
- `rs` and the $2 floor on the 6 unranked High nights (BNGO, INO, FCEL, HEXO, PLTR, SLV).

---
# WIRED on the branch (2026-11-11, on his "buy his setups period"; PENDING HIS SIGN-OFF BEFORE PAPER)
His grades stopped being a bar, so the rule set was wired (commit `c41436db` + the follow-up). Owner: the 2026-11-11
change-log entry of `docs/setups/consolidation_breakout.md`. Two things found while wiring that this document did not
show:
- **Head to head on all 757 buys (n = 757; `13_head_to_head.out`):** listed / fired — the 11-02 rules 455 / 209, the
  wired set 319 / 94; big winners fired 21 -> 11 (n = 26). The wired set buys 78 of the 84 High and none of the 116
  Medium. "84 of 84" above was true by construction and hid this.
- **FCEL 2020-02-10** fails the $2 floor (raw close $1.72): 79 listable, 5 floor losses (not 80 and 4).
