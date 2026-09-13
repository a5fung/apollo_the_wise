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

---

# Why Lane-2 suggestions don't reach the board — answered

## How Lane-2 works, in one pass

Nightly, inside the theme-engine run (~17:00–18:00 ET, market days):

1. **Take today's qualifying EP alerts** — `ep_score >= 50` AND (`catalyst` OR `claude_analysis`)
   (`_lane2_qualifies`, `theme_engine.py:626`).
2. **Read its own memory** — the ACTIVE narratives it is already tracking, plus one-name "seeds",
   both windowed to the last `LANE2_WINDOW_TRADING_DAYS` sessions, prior days only.
3. **One Sonnet call** over today's evidence text plus that roster. The evidence is the SEC-8K
   grounded body where available, else `claude_analysis`, else the Perplexity catalyst.
4. **It emits three things**: JOIN (add today's name to a story it already tracks), NEW (a fresh
   multi-name story), SEED (a one-name story to watch for a partner later).

**The point of the memory** is cross-day assembly: WULF on 07-06 and CLSK on 07-14 become one
cohort without re-reading old documents nightly. **The point of the lane** is stories that bind
non-co-moving names — policy, cross-sector — which Lane 1 structurally cannot see because it needs
price correlation.

Writes land in `mi_theme_candidates_shadow`: multi-name as `narrative_cogap` (auto-promotable),
one-name as `narrative_seed` (walled off — a 1-member row can never promote).

## Why they don't land: the 3-member bar

The nightly auto-promote takes cohorts with **`len(tickers) >= _PROMOTE_MIN_MEMBERS`**, and
`_PROMOTE_MIN_MEMBERS = 3` (`theme_engine.py:2274`).

**Lane-2's `narrative_cogap` output since 2026-06-07, by size:**

| members | candidates | can promote? |
|---|---|---|
| **2** | **8** | **NO — below the bar** |
| 3 | 4 | yes |
| 4 | 2 | yes |
| 5 | 1 | yes |
| 8 | 1 | yes |

**Exactly half — 8 of 16 — name a two-stock story and are structurally unpromotable.**

## The 13-day case, explained exactly

```
2026-07-30   AI-Driven Power & Grid Infrastructure Boom   2 members: EME, PWR      -> below the bar
2026-08-12   same narrative                               4 members: EME, PWR, EROC, BE -> promoted
```

**The 13 days were Lane-2 waiting for a third and fourth member to show up.** Nothing was stuck or
forgotten — the cohort was two names, the bar is three, and it promoted the day it crossed. The
lane was right on 07-30 and the board could not act on it.

## The inconsistency worth his eye

`_PROMOTE_MIN_MEMBERS = 3` but `PRUNE_MIN_TICKERS = 2` — **a theme may LIVE at two members but may
not be BORN at two.** Twenty live themes currently sit at 2, having arrived by other paths. So the
board already holds two-member themes; it just refuses to create them.

**The fork, and it is his:** lower the birth bar to 2 and Lane-2's eight stalled candidates become
eligible — at the cost of admitting more two-stock groups, which is the same churn the birth gate
(flipped ON today) exists to control. The gate's join arm would now fold many of them into existing
themes rather than minting new ones, which did not used to be true. ⚖ Detection criterion —
CHANGE_PROCESS, backtest, his sign-off.

## What this does NOT answer

- **Whether two-name stories are worth promoting.** 8 of 16 is the supply; nobody has checked how
  many of those eight later proved real.
- **Whether the bar should be 2, or 2-with-conditions** (e.g. 2 plus a second sighting, which is
  what the birth gate's wait arm already does).
- **The 31 proposals that never became themes** — size is one reason, quality may be another.


---

# ⛔ A CONTRADICTION HE CAUGHT — and today's statement was the wrong one

> *"Yesterday you told me EP alerts themes are just text and don't source themes, now you say it does"*

**He is right, and the error is in TODAY's work, not yesterday's.**

Today I wrote *"Goal 2 had no lane until yesterday"* and *"nothing routes a gap into theme
creation."* **Both false.** `narrative_cogap` — Lane 2 — has been writing theme candidates from EP
alerts since **2026-06-25**, nearly three months, and it sits on the auto-promote allowlist.

What was true yesterday is narrower: **#651 is about the JUDGE's free-text theme mention inside its
grading rationale**, which was parsed by nothing and routed nowhere. That specific signal was just
text. **I then over-generalised it into "EP alerts don't source themes", which erases a lane that
has been running all along.**

Lane 2 IS the gap-ups-to-themes lane. #651 is a second, different signal on the same alerts.

---

# Impact of allowing two-stock themes

## (a) Supply — it is not a Lane-2 change, it is a board-wide one

Candidates from auto-promotable sources since 2026-06-07, by member count:

| | at the bar today (≥3) | dropping to ≥2 adds |
|---|---|---|
| **total eligible** | **225** | **+258 → 483 (+115%)** |

⚠ **And the change is overwhelmingly NOT about Lane 2.** Of the 258 newly-eligible two-member
candidates, **250 are `shadow_v2`** (the correlation lane) and only **8 are Lane-2's**. Framing this
as "frees Lane-2's eight stalled stories" understates the blast radius by ~30×. **It would roughly
double theme births, from Lane 1.**

## (b) Do small-born themes actually behave worse? Measured, and NO — the opposite

Every theme lineage on record, by its size on its birth day, against whether it ever reached
Accelerating or Mainstream:

| born with | themes | ever matured | rate |
|---|---|---|---|
| **2 or fewer** | 142 | 85 | **60%** |
| 3–4 | 247 | 74 | **30%** |
| 5+ | 163 | 66 | **40%** |

**Themes born small mature at twice the rate of mid-sized ones.** The 3-member bar exists to keep
noise out, and on this measure the names it keeps out are the ones that do best.

⚠ **Uncontrolled, and I am not going to dress it up.** This compares raw cohorts with no control
for era, sector, market regime or how the lineage is name-matched across renames. It is strong
enough to say *the bar is not obviously protecting quality*; it is not strong enough on its own to
move a detection threshold.

## What this does NOT answer

- **Whether doubling births is survivable.** The birth gate (flipped ON today) would fold many of
  the 250 into existing themes via its join arm rather than minting them — but that interaction has
  never been measured, and it is the whole question.
- **Why small-born themes mature more.** Could be real (a tight pair is a truer signal) or an
  artifact of how lineages are matched. Untested.
- **Whether Lane-2's eight specifically are any good** — they are 3% of the change and should not
  drive it.

---

# ⚠️ RECOMMENDATION — REWRITTEN 2026-09-13 EVENING. The first version was wrong.

**Superseded:** *"Do not move the bar this week. Decide it on Friday 2026-09-18, on a rule."*
**Now:** **lower the promote floor to 2 while the birth gate is `on`.** His call — a detection
criterion, so CHANGE_PROCESS + backtest + sign-off.

An advisor review of the recommendation caught that **every number under it was measured against a
rule the flip had already replaced four hours earlier.** The corrections, in order of how much they
moved the answer.

## Correction 1 — the "+258 candidates, board doubles" figure is dead

The impact script imported the STATIC `db.AUTO_PROMOTE_THEME_SOURCES`. The engine reads
`db.resolve_auto_promote_sources()`, which at gate mode `on` returns the set **minus `shadow_v2`**
(`db.py:9157`). Confirmed live in `apollo-market`:

```
gate mode        : on
static frozenset : ['narrative_cogap', 'rs_slope_synthesis', 'shadow_v2']
RESOLVED (live)  : ['narrative_cogap', 'rs_slope_synthesis']
```

`shadow_v2` is not merely de-allowlisted — its whole pass is retired at `on`, and its a/a2
selectors were **ported into Lane-1 discovery** first (`theme_engine.py:7428`), which births at
`NEW_THEME_MIN_STOCKS = 2`. So those cohorts were never going to hit the promote floor at all; they
already flow through a **2-member** floor, into the same gate.

**Re-measured on the live allowlist, over the engine's real 3-day promote window, 35 nights:**

| | cohort-nights eligible | per night |
|---|---|---|
| bar = 3 (today) | 65 | 1.9 |
| bar = 2 | 84 | 2.4 |
| **delta** | **+19 (+29%)** | **+0.5** |

| source | extra admitted at bar=2 | already eligible at bar=3 |
|---|---|---|
| `narrative_cogap` (Lane 2) | **19** | 21 |
| `rs_slope_synthesis` | **0** | 44 |

**The bar is now a Lane-2-only bar.** `rs_slope_synthesis` never produces a 2-member cohort. The
decision affects one lane and about half a cohort a night — not 258 candidates, not a doubled board.

## Correction 2 — the Friday rule could not have produced a reading

It proposed measuring *"the gated join rate on new 2-member candidates, Mon–Fri."* But
`theme_engine.py:2447` filters on the member count **before** the gate loop runs:

```python
cohorts = [c for c in cands if len(c.get("tickers") or []) >= _PROMOTE_MIN_MEMBERS]
```

At bar 3, **zero** 2-member cohorts reach a gate verdict — this week, last week, or ever. The rule
would have returned an empty numerator every night and I would have read a structural zero as
evidence. The 51% join figure it leaned on came from Lane-1 births and ≥3-member promotes: a
different population entirely.

⚠ **This is the week's recurring defect class again** — a check that cannot fire reads exactly like
one that passes. It is the third instance in seven days.

## Correction 3 — the 60% maturity figure cannot speak to this decision

Split by source, the ≤2-member band is **entirely** Lane-1 (`source='live'`). Not one
`shadow_promoted` theme was ever born at ≤2 — the bar makes that impossible by construction.

| source | born 1–2 | born 3–4 | born 5+ |
|---|---|---|---|
| `live` (Lane-1 discovery) | **48%** (68/142) | 34% (30/88) | 36% (35/98) |
| `shadow_promoted` | **— none exist —** | 21% (33/159) | 14% (9/65) |

So the number says nothing about how a 2-member promote would mature. **Withdrawn from the
decision.** What survives is weaker and points the same way: in the one lane that *does* allow
2-member births, they mature **better** than larger ones (48% vs 34%/36%). Still uncontrolled —
"Mainstream" is age-gated, so it is partly a survival measure.

## What actually decides it — the bar is a permanent filter, not a delay

Every `narrative_cogap` cohort first seen at exactly 2 members, last 120 days:

| first seen | cohort | outcome |
|---|---|---|
| 2026-06-25 | AI memory and infrastructure demand surge — MU, SNX | never reached 3, never a theme |
| 2026-07-20 | **Bitcoin miners pivoting to AI data centers — HUT, IREN** | never reached 3, never a theme |
| 2026-07-30 | AI-Driven Power & Grid Infrastructure Boom — EME, PWR | reached 3 in **13 days** |
| 2026-07-31 | Semiconductor test recovery AI-driven demand — COHU, MPWR | never reached 3, never a theme |
| 2026-08-04 | Semiconductor Equipment Cycle Recovery — AEIS, ZBRA | never reached 3, never a theme |
| 2026-08-19 | AI-driven biotech/R&D acceleration — TWST, TEM | never reached 3, never a theme |
| 2026-09-03 | AI data-center power buildout — AGX, SNOW | reached 3 in **1 day** |
| 2026-09-08 | Bradykinin-mediated angioedema oral therapies — PHVS, ROIV | never reached 3, never a theme |

**6 of 8 never cross.** The bar does not delay them, it deletes them. Only 2 of 8 ever became live
themes, and one of those waited 13 days.

## The evidence that these are not noise — a second, independent system named the same pairs

The #651 judge reads EP alert text and names the group it sees. It has no access to Lane 2's
cohorts, no shared code path, no shared input. Its recurring groups against the blocked list:

| Lane 2, blocked by the bar | #651 judge, independently |
|---|---|
| COHU + MPWR, **2026-07-31** | `ai-data-center-semiconductor` — **COHU + MPWR, 2026-07-31** |
| HUT + IREN, **2026-07-20** | `ai-data-center-infrastructure` — first seen **2026-07-20**, includes **HUT** |
| AEIS + ZBRA, 2026-08-04 | `ai-data-center-power` — first seen **2026-08-04**, includes **AEIS** |
| AGX + SNOW, 2026-09-03 | `ai-data-center-power` evidence names **AGX/SNOW/ALAB**, 09-08 |

The first row is an **exact match**: same two tickers, same day, two mechanisms that share nothing.
That is the strongest available answer to "are 2-member co-gap cohorts noise?" — twice, a separate
system looking at different data named the identical group on the identical day.

**And the second row is his own thesis.** Lane 2 named *"Bitcoin miners pivoting to AI data
centers"* on **2026-07-20**. He ruled the same thing — miners *"converting into AI infra plays"* —
on **2026-08-04**, fifteen days later (#491 M2, SSoT `theme_engine.md`). The bar deleted the
engine's version. IREN now sits in the live *Emerging Bitcoin & AI Cloud Compute Miners* theme that
is tonight's flagged unruled join.

## The recommendation

**Make the promote floor mode-dependent, exactly as the allowlist already is:** 2 while the birth
gate is `on`, 3 when it is `observe` or `off`.

- **Why mode-dependent and not a flat 2:** reverting the gate puts `shadow_v2` back in the
  allowlist. A flat 2 would then admit its ~250-candidate stream at a 2-member floor with no gate
  adjudicating it. Tying the floor to the mode makes the change auto-revert with the gate, and it
  reuses the `resolve_auto_promote_sources` idiom rather than adding a source-specific special case.
- **Why 2 is the consistent number:** post-flip, Lane-1 discovery already births live themes at 2
  members, through the same gate. Two floors for the same act — 2 for Lane-1, 3 for promote — had a
  reason before today: promote was *"THE previously-ungated bypass"* (`theme_engine.py:2498`). The
  flip closed that bypass. The asymmetry outlived its justification by four hours.
- **What protects quality now:** the gate, which promote cohorts did not clear before today. Its
  arms are `join` (fold into an existing theme), `await_second_sighting` (the one-day-corpse
  filter — all 53 observe-era holds were single sightings that never recurred), `held_floor` and
  `held_no_rs`. A 2-member cohort admitted at bar=2 is adjudicated, not waved through.
- **Blast radius:** ~0.5 extra cohort-nights per night, one lane, every one of them gated.

**The backtest CHANGE_PROCESS requires:** replay the promote path over the last N nights with the
floor at 2 and the gate on, and read the join/birth/hold split. That is the evidence for sign-off,
and it is the same work the dead Friday rule was going to wait five days to approximate badly.

## What this still does NOT answer

- **Whether the 6 blocked cohorts would have matured.** They never existed as themes, so there is
  no outcome to read. The judge correspondence says they were real groups; it does not say they
  were durable ones.
- **Whether the gate's join arm handles 2-member cohorts well.** It has never seen one. The backtest
  is what answers this, and it must report the join/birth split, not a total.
- **Whether naming these earlier would have changed a trade.** Out of scope by his own sequencing —
  step 3 is parked until steps 1 and 2 are settled (#655).
- **The 48% Lane-1 small-birth maturity edge.** Uncontrolled for era, sector and regime, and
  "Mainstream" is age-gated. Directional only; it is not load-bearing above.
