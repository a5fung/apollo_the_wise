# Theme engine — full-lifecycle diagnosis (2026-09-13)

**Method**: six parallel readers over birth / growth / shrink / death / thesis / ground-truth, each
reading code AND querying prod; every finding then adversarially verified by an independent agent
instructed to refute it. 31 agents, 14 findings survived. Population: `mi_themes`,
`mi_theme_birth_candidates`, `mi_theme_candidates_shadow`, `mi_audit_log`; windows stated per number.

**Denominators for every percentage in this document** (state them with the number, always):

| population | n |
|---|---|
| live themes on the board, single-industry check | n = 127 |
| theme lineages born, last 120 days | n = 495 (271 Lane-1 `live`, 224 `shadow_promoted`) |
| theme lineages born, last 90 days (growth/lifespan) | n = 469 |
| shadow candidate rows, last 120 days | n = 547 (445 of them `shadow_v2`) |
| birth-gate verdicts recorded over the 45-day observe window | n = 168 (86 join, 53 await, 26 birth, 3 held) |
| operator theme labels available as a cross-check | n = 90 (71 yes / 18 no / 1 unsure), plus 44 on 09-13 |
| placement (assignment) opportunities measured | n = 23 nights |

**Two headline claims were re-verified by hand afterwards and both reproduce** — see
`## Operator-facing verification` below.

## The diagnosis

Two root causes, plus one change that went live today and first acts on Monday. Every number below is from **before** today's switch.

**Cause 1 — a real story that spans more than one industry cannot become a theme. Discovery does not go looking for one, and two rules pull it apart if it forms.**
- Two separate mechanisms hold a theme to a single industry: the placing step refuses 1 proposal in 5 as a "sector outlier", and a nightly strip pulls lone-industry members out of any theme with 3 or more members. **118 of our 127 live themes carry exactly one industry label.** Payments, bitcoin miners turning into data centres, the chip supply chain — none of those can accumulate members even when that is literally the theme's name.
- Discovery is the only thing that invents themes and it looks only at the **top 40 stocks** (in practice the top ~2% by strength), while the step that places stocks into existing themes reaches 600. That gap was left in deliberately in August and never revisited.
- The consequence, and the deciding test: 87% of placement chances end in nothing, and of the names offered night after night that eventually did get a theme, **54 of 55 joined a theme invented later — only 1 joined a theme already on the board.** They were waiting for a theme to exist, not for a filter to relent.
- It is not the entry bar. Over 23 nights, roughly 1 chance in 5,000 was missed. Widening the strength bar reaches nobody new.
- The refusals never settle. One stock was refused into the same theme on **16 separate nights**; the original fix had two halves, a code filter and a prompt rule telling the model about it, and **the prompt half is missing from the code**, so the model is filtered against a rule it cannot see. Three utilities (Spire, Xcel, AEP) were then locked out of *all* theme assignment because they kept being mis-filed into oil themes and correctly removed.

**Cause 2 — nothing carries a theme's story, and we have no test of whether a name is right.**
- The theme NAME is the only durable identity and the only thing on his screen; the one story field is a weekly news blurb (we literally ask "what news catalyst is driving these tickers higher this week"), rewritten three times a week. Hand-read 12 of those rewrites: **zero** changed the theme's organising idea.
- That blurb is **never shown on any theme surface he uses** — and about a third of the board on a typical day, over half on 11 Sept (63 of 118), shows as a struck-through name with no strength and no members at all.
- Since 4 August that same weekly news blurb is what decides who stays in the theme, and the check runs *before* the refresh, so members are judged against a bulletin two days stale.
- His own case is the shape: the shadow lane proposed "Bitcoin miners pivoting to AI data centers" on **20 July**, the day he raised it; the live board did not carry that name until **three weeks later**. The engine kept producing the right identity and kept throwing it away.
- We cannot score any of it. The groups are **not random** — a theme's founders move together 0.16 to 0.28 more than size-, volatility- and industry-matched non-theme groups, on the 42% of themes with 3 or more founders — but that says nothing about whether they are the **right** groups or carry the **right** names.

**Live today, first acts Monday — and it is two changes, not one.**
- **What it holds:** the wait rule now holds roughly half of newly discovered themes for at least one extra night; the strength floor holds 3%.
- **The evidence that authorised it is circular.** "These held candidates were one-day corpses" is the definition of that bucket restated — a maximally costly version of the rule reads identically. On the measure the design doc named 48 days earlier, **46 of the 49 held themes lived two days or more and 19 reached the doc's own "long-lived" bar of 14 days**; the claimed benefit of ~53 junk themes removed is really about 6.
- **What it retires:** the same switch drops shadow_v2 from the promotion list. That source wrote 82% of all shadow candidate rows, and its lane produced **55% of every genuine new theme** we have had. Its selectors were moved into discovery; nobody has verified those cohorts actually arrive that way.
- Whether the one-night hold is a delay or a permanent loss cannot be known from anything we hold today. **Monday's 5pm run is the first night either half acts.**

## What to fix, in order

| Fix | What it buys | Mine or his |
|---|---|---|
| 1. Rule on today's switch as a whole — the one-night hold **and** the retirement of our largest theme source — before Monday 5pm | Step 2. It either costs us a night on every new theme for a benefit ~9x smaller than claimed, or it does not; nothing we have can tell us, and Monday is the first night it bites. | **His** — detection criterion. I will not pre-decide it. |
| 2. Decide how discovery finds candidates beyond the top 40, and whether a dying theme's members can be re-homed | Step 1, the biggest lever: it is the only thing that creates homes for the strong names sitting homeless today. | **His.** He has already ruled once that a raw strength band is not the answer, so the option to price is a different selector, not a lower bar. |
| 3. Rule whether a theme may span more than one industry — starting with the 16 stock-and-theme pairs we refuse night after night | Step 1. Cross-industry stories are the ones he actually trades, and today two rules guarantee they never form. | **His** — and whether any given refusal was right is his judgement, not mine. |
| 4. Restore the prompt half of the sector fix he already signed | Step 1, free: the model stops proposing into a rule it cannot see, which is why the same refusals repeat forever. | **Mine** — but it waits on Row 3; if he allows cross-industry themes, restoring it is the wrong direction. |
| 5. Fix the theme board he actually looks at | Step 1: show the theme's story, show a fading theme's strength and members, and fix the "mainstream" label that counts rows in the last seven calendar days instead of age — it blocked all but 3 of ~75 expected promotions across four long weekends. | **Mine.** One flag: that label also gates the live EP score boost, so the fix changes which themes carry it. |
| 6. Give a theme a durable thesis, separate from the weekly news line | Step 1: today there is no field a theme's real story can live in, and the news blurb is quietly deciding membership. | Building the field is **mine**; pointing the membership check at it is **his**. |
| 7. Build the missing name-correctness test, and repair two broken instruments | Step 1 measurement: the judge's "we found it first" result flips to "we already had it" when read correctly, and it repeats our own candidate names back about a quarter of the time. | **Mine** — I need roughly 20 quick yes/no calls from him on names, nothing more. |

## Still unknown

- Whether the one-night hold is a delay or a permanent loss — only Monday's first real run answers it.
- Whether the roughly 1-in-5 sector refusals were actually right. That is a judgement on names, and it is his.
- Whether our theme NAMES are right. No test exists; this is the biggest measurement hole we have.
- How many real themes we are missing right now. The only labels are 31 rows from a 10-day window 4.5 months old, chosen by what went up — the axis he ruled out for judging themes.
- Which merge step ate a correct utilities theme three times in one week. The code branch that does it writes no record; one audit line settles it, and that is mine.

## The one thing to do next

Rule on today's switch before Monday's 5pm run — both halves of it, the night it holds every new theme and the retirement of the source that produced more than half of them — because the reading that authorised it proves nothing in either direction and Monday is the first night it acts.

---

## Operator-facing verification (run by hand, not by the workflow)

**1. The wait-arm evidence that authorised today's flip was circular — CONFIRMED WRONG.**
I reported *"all 53 `await_second_sighting` candidates were single sightings that never recurred —
one-day corpses."* That is the bucket's own definition restated: under `observe` the theme was born
anyway, so the candidate never re-presented as a candidate. Measuring what those 53 cohorts actually
DID (ticker-overlap match into `mi_themes` from `first_seen` onward):

| | |
|---|---|
| cohort never became a live theme | 0 |
| lived exactly 1 day (a real one-day corpse) | **5** |
| lived 2+ days | **48** |
| lived 14+ days (the design doc's own "long-lived" bar) | **20** |

Longest: 31 days (Cloud Contact Center & CCaaS), 29 (Digital Insurance Distribution), 29
(Commercial/Office & Home Furniture), 28 (Private Equity & Alternative Asset Management), 27
(Industrial Process Equipment & Automation).
**The wait arm would have delayed every one of those by a night**, and killed any that did not
re-present. The "~53 fewer one-day themes per 45 days" I put in the change-log is really about **5**.

**2. The same flip cuts the input to the lane that produced ~45% of themes — CONFIRMED.**
Last 120 days: `shadow_v2` wrote **445 of ~547** shadow candidate rows (81%). The promote lane it
feeds produced **224 of 495** themes born (45%), of which **120 lived 5+ days** and 35 lived 14+.
At gate mode `on`, `shadow_v2` leaves `resolve_auto_promote_sources` and its nightly pass is skipped;
its a/a2 selectors were ported into Lane-1 discovery first. **That port has never run** — the engine
is market-days-only and last ran Fri 2026-09-11 under `observe`.

**Both halves first act Monday 2026-09-14 ~17:00 ET.** Reversion is one command, instant, no
redeploy: `set_theme_birth_gate_mode('observe')`. ⚖ **OPERATOR-ONLY** — a detection criterion under
THE LINE; never self-authorised.

**What held up from my earlier reporting**: the join arm is de-duplication by design, and 64 of its
86 observe-era verdicts (74%) were overlap 1.00 — the cohort genuinely already on the board. That
part of the flip does what I said it does.

## What this does NOT answer

- Whether the one-night hold is a delay or a permanent loss. No gated night has ever run.
- Whether the ~1-in-5 sector refusals were correct. That is a judgement on names, and it is his.
- Whether our theme NAMES are right. No test exists — the largest measurement hole we have.
- How many real themes we are missing now. The only labels are 31 rows from a 10-day window 4.5
  months old, selected on forward return — the axis he explicitly ruled out for judging themes.
- Which merge step ate a correct utilities theme three times in one week (the branch writes no
  audit row).


---

## ⚠ Correction 2026-09-13 (post-build): the dedup arm's value was overstated ~2x

I reported *"64 of 86 join verdicts were overlap 1.00 — the cohort genuinely already on the board
under another name."* The overlap figure is right; the **"under another name"** half is not.

| of the 86 observe-era `join` verdicts | n |
|---|---|
| joined a **different** theme (the real dedup case) | **47** |
| joined **ITSELF** — same theme name | **39** |
| at overlap 1.00 | 64 |
| …of those, self-joins | **34** |
| **real exact duplicates under another name** | **30** |

**Cause**: the promote lane's observe carve-out re-evaluates cohorts it promoted itself, and
`get_active_themes()` still holds that theme the next night — so it draws `join` against its own
name at overlap 1.00. 30 of the 39 self-joins come from `promote:shadow_v2`.

**This does not change the recommendation**, and the shipped code already handles it: `dedup_only`
acts on **first crossings only**, so a maintenance re-promotion is never cancelled (pinned in
`tests/test_theme_birth_gate.py`). The corrected value of the arm is **~47 genuine joins in 45 days,
about one a day**, not 64.

Flagged by the build agent, verified by direct query before reporting.
