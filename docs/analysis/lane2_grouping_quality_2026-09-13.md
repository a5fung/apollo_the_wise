# Lane-2 narrative grouping quality — the review, run 2026-09-13

Run on his instruction after the entry's own pull-forward trigger was found to have fired
(Lane-2 proposals now overlap EP-traded names 47 of 59 = 80%).

## Method and population

**Population:** the **64 distinct live run-days** with a `narrative_theme_discovery_ran` audit row
since **2026-06-07**. The 90 earlier runs are hindsight backfill crammed into two days (06-04 ×67,
06-06 ×23) and the registry entry says they must NEVER be pooled — they are excluded.

**Day classes**, taken from each run's own summary:

| class | meaning | days |
|---|---|---|
| A | `0 qualifying` — nothing reached the model | 15 |
| B | `-> 0 join + 0 new` — candidates seen and declined | 8 |
| C | proposed something | 30 |
| D | other shapes | 11 |

**GENUINE MISS** = ≥2 of that day's EP alert tickers (`mi_ep_alerts`) later landed in the SAME theme
in `mi_themes`, any lane, any date after. That is the engine itself saying later that the group was
real. **CORRECTLY DECLINED** = they never did. **The model's own opinion is used nowhere in this
classification**, as the entry requires.

## Result

| day class | days | genuine miss | correctly declined | no pair to find | miss rate |
|---|---|---|---|---|---|
| A nothing qualified | 15 | 0 | 0 | **15** | – |
| B seen and declined | 8 | **2** | 3 | 3 | 40% (2 of 5 judgeable, n=5) |
| C proposed | 30 | **6** | 23 | 1 | 21% (6 of 29 judgeable, n=29) |
| D other | 11 | 0 | 1 | 10 | 0% |

**All 15 class-A days had fewer than two EP alerts.** There was nothing to find — those are not
failures and must not be counted as such.

## The number that decides it: how much EARLIER would Lane-2 have been?

A miss that another lane names the next day costs **one day**, not a theme.

| day | class | lag | members | the theme that later appeared |
|---|---|---|---|---|
| 2026-06-15 | C | **51d** | HYMC, AUGO | Precious Metals Miners Rotation |
| 2026-07-30 | C | **13d** | EME, PWR | AI-Driven Power & Grid Infrastructure Boom |
| 2026-07-31 | C | **12d** | BLZE, FLNC, MPWR | AI data center infrastructure buildout |
| 2026-08-04 | C | 1d | BTDR, AMRC, BLZE | AI Data Center Infrastructure Buildout |
| 2026-08-12 | C | 1d | CRWV, WYFI, BE, EROC | AI data center infrastructure buildout |
| 2026-08-13 | B | 1d | CRMD, KURA, OMER | Rare disease/specialty pharma earnings beats |
| 2026-08-27 | B | 1d | OKTA, CRWD | Network Security & Zero-Trust Edge |
| 2026-09-03 | C | 1d | AGX, SNOW | AI data-center power buildout |

**Median lag 1 day (n=8 misses). 5 of 8 were caught by another lane within a day.** The whole value sits in the
other three: **51, 13 and 12 days.**

## The ruling this feeds — leave / widen / retire

⛔ **CORRECTION, 2026-09-13, after he caught it: my first recommendation ("leave", on the grounds
that widening buys ~2 days) was arithmetically wrong and the conclusion did not follow from this
table.** His words: *"your data doesn't agree with your conclusion, e.g. 51 days for miners, how is
that buying 2 days."* He is right.

**The error:** I defined "widen" as *act on the days it declined* and so computed the benefit over
class B only — 2 misses × 1 day = 2 days. But **six of the eight misses are class C**: days Lane-2
ran, proposed something, and missed a DIFFERENT real group. Widening breadth — how many groups it
considers and proposes per day — targets exactly those.

**The prize, recomputed over all 8 misses:**

| class | misses | days of earliness available | lags |
|---|---|---|---|
| B — declined that day | 2 | **2 days** | 1, 1 |
| C — proposed something else | 6 | **79 days** | 51, 13, 12, 1, 1, 1 |
| **total** | **8** | **81 days** | |

**So the upside is 81 days across three months, 76 of it in three catches — not 2 days.** My figure
described one narrow reading of "widen" and I then used it to rule out the whole option.

**RETIRE remains wrong** — 12-to-51-day catches are the rare-event payoff the entry says this lane
exists for.

**LEAVE is no longer supported by this table.** An 81-day prize is worth answering properly.

**The honest recommendation is now: INSTRUMENT, THEN DECIDE.** The run audit rows carry an **empty
`detail`**, so what Lane-2 actually considered each day is not recorded. Without that, *"would a
wider Lane-2 have caught HYMC/AUGO on 06-15?"* is unanswerable — and it is the only question that
matters here. Log the per-day candidate inputs, re-run this review after ~20 run-days, and the
widen/leave call is then made on evidence instead of on a guess about breadth.

## What this does NOT answer

- **Whether a wider Lane-2 would have caught the three long-lag cases.** They are class-C: Lane-2
  ran, proposed something else, and did not name that group. Whether a more permissive setting
  would have surfaced HYMC/AUGO on 06-15 is not decidable from these rows — it needs the per-day
  candidate inputs, which the audit rows do not carry (`detail` is empty on every run row).
- **Whether "the engine later built a theme" means Lane-2 COULD have seen it.** It is a proxy for
  the group being real, not proof the tickers were in Lane-2's input that day.
- **Anything about trade outcomes.** Not used, by his standing ruling.
- **The 30 class-C days' proposals themselves** — this measures what was MISSED, not whether what
  was proposed was any good.

Cost: **$0**. Read-only.


---

# THE CALL — 2026-09-13, after he pushed back on "instrument and wait"

> *"it's already delayed, I need to know why you recommend keep waiting, if that even makes sense
> or we just keep deferring to not make a call"*

He was right. The data answered it; no instrumentation was needed. Both of my earlier
recommendations are withdrawn.

## 1. What "widening" concretely means — and why it is dead

The only knob is `_lane2_qualifies` (`theme_engine.py:626`):
**`ep_score >= 50` AND (`catalyst` OR `claude_analysis`)**. Widening = lowering that floor.

**Checked all 21 tickers across all 8 missed groups: every one QUALIFIED. Zero were excluded.**
Scores ran 50 to 96; every one had both a catalyst and an analysis.

**So widening the pool changes nothing.** Lane-2 already saw every name it missed. The floor is
innocent and the question is closed — with evidence, today, not after 20 more run-days.

## 2. The goal it serves

His goal 2, stated 2026-09-13: *source new themes from the gap-ups* — an early mover can be the
start of a theme that later lifts the group. Lane-2 exists for the cross-sector/policy stories that
price correlation structurally cannot see.

## 3. What Lane-2 actually gives us

| | |
|---|---|
| proposals since 2026-06-07 | **43** over 64 run-days |
| map to a theme the board later held | **12** |
| never became anything | **31** |
| **proposed BEFORE the board had it** | **3 — by 14d, 13d and 1d** |

The two that matter: **AI-Driven Power & Grid Infrastructure Boom, proposed 07-30, board named it
08-12 — 13 days later.** **Semiconductor test recovery, proposed 07-31, board named it 08-14 — 14
days later.** Lane-2 named them correctly and first.

## The verdict

**LEAVE THE LANE AS IT IS. Do not widen, do not retire. The defect is downstream of it.**

Lane-2's 07-30 candidate sat **13 days** before the board held that theme, and it was in
`narrative_cogap` — a source that is already on the auto-promote allowlist. **Its output was right,
and slow to land.**

**That is the same finding as the main theme work today** — the engine holds a group a median 26
sessions before naming it. Lane-2 is not a separate problem; it is more evidence for step 2
(timing), on a lane whose detection is already working.

## What this does NOT answer

- **Why the 07-30 candidate took 13 days** to become a live theme despite sitting in an
  auto-promote source. That is the promotion path, not the detection lane, and it is the thing
  worth chasing next.
- **Whether the 31 proposals that never became themes were wrong.** They may be noise, or groups
  the board still has not found. Not tested here.
- **The model/prompt question.** All 21 names qualified, so what made it group some and not others
  is a prompt-quality question this review does not open.
