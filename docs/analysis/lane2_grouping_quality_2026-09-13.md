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

**RETIRE is wrong on this evidence.** Three catches at 12–51 days early is precisely the rare-event
payoff the lane was built for, and the entry says so itself: *"Lane-2 is a RARE-EVENT detector by
design... low output is EXPECTED and a low proposal count is not evidence of failure."*

**WIDEN is aimed at the wrong thing if aimed at the decline days.** Both class-B misses cost one day
each — widening the model's willingness to propose buys **two days across three months**. The 15
class-A days cannot be helped at all: they had no pair.

**LEAVE is what the evidence supports**, with one caveat below.

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
