# How do we tell whether an EP belongs to a theme? (2026-09-13)

> **Operator:** *"Judge already suggests a theme, what we need to figure out is how to check and
> verify if this EP truly belongs to a theme. Stock already in list is the obvious way, peers may be
> one, other methods we use to determine theme membership are also fair, at the end of the day, even
> without stock directly in list, we need to figure out if it belongs to a theme."*

**Method**: four membership signals measured at alert time — the judge's own naming, peers, the
membership machinery we already run, and the combination — each adversarially verified by a separate
agent instructed to refute it. 8 agents. Population `mi_ep_alerts` with a score, last 120 days,
**n = 346**.

⚠ **THE `combined` ANGLE WAS REFUTED and one agent errored.** Its union and ceiling figures are NOT
carried into the headline below; the ceiling quoted here is my own recount, run independently
afterwards. Its per-signal findings are unaffected.

## My independent recount of the ceiling — run after the workflow, and it is the whole story

| as of the alert day, was this ticker in a theme? | n of 346 | |
|---|---|---|
| the live `in_active_theme` flag — **what actually pays the +10 today** | **22** | 6% |
| Accelerating/Mainstream within 7 days (recomputed) | 31 | 9% |
| **ANY stage within 7 days** | **72** | 21% |
| **ANY stage, ANY time before the alert** | **108** | 31% |
| **in NO theme within 7 days** | **274** | **79%** |
| **in NO theme EVER** | **238** | **69%** |

**Between 69% and 79% of EP alerts have no theme to belong to.** No membership signal — his, mine or
anyone's — can match a stock to a group that does not exist. That is the ceiling on this entire
idea, and it is the answer to his question.

⚠ The workflow's own widening figure (22 → 54) does not reproduce against mine (22 → 72 → 108); the
difference is how "wider" is defined. **Do not quote a single widening number** — the honest
statement is a range, and every version says the same thing: today's rule pays a small fraction of
what the engine already knows.

## The answer

- **For the alerts his objection is actually about — EPs the engine has not grouped yet — nothing we own can say "this belongs to a theme" at 9:31.** On the alert day, 292 of 346 alerts (84%, last 120 days) sit in no theme at any stage, so there is no group for any signal to match them to. The lateness is a theme-coverage problem (his steps 1 and 2), not a scoring-signal problem.
- **Rank 1 — the same list, read wider (zero build):** dropping the 7-day recency floor and accepting any stage takes the list from 22 of 346 alerts (6%) to 54 (16%), +32 alerts, using the same snapshot read at the same moment; it is also the sharpest separator measured — stocks it flags are recognised in a theme later 90% of the time vs 51% for those it does not.
- **Rank 2 — the judge's own naming of the group (+39 on top, union 93 of 346, 27%):** where the extraction has read the prose (144 alerts), the judge names a group on 59 (41%) vs the list's 14 (10%), and those alerts are recognised in a theme within 30 days 80% of the time vs 49% for alerts the same reader found nothing in — but 34 of its 47 hits were stocks **already** in a theme, and on the 77 genuinely-late alerts its edge is 4 of 21 vs 6 of 56, i.e. nothing.
- **Rank 3 — peers, rejected as a membership signal:** shared-industry peers reach the most alerts (177 of 346, 51%) and are the least informative — they fire on 61% of EP alerts vs ~50% of ordinary non-alerting stocks (1.2x), invert at a stricter peer count, name the theme the engine later chose 3 times in 35, and in August fire at 0.96x an ordinary stock. It tells you the neighbourhood is hot, not that the stock belongs to a group.
- **Correlation peers, stored correlation clusters, Lane-2 cohort membership and the axis shadow add nothing usable:** clusters fire on 3 of 346 and the engine deletes a cluster precisely when its members share a theme; Lane-2 ticker membership fires on 2; the axis shadow can only fire where the list already found a theme.

## What is already built

- **The judge already overwrites the alert's tier on 181 of 346 alerts (52%) while holding the theme flag and the cohort names** — a theme read is acting on his alerts today, just not through the +10. He likely does not know this.
- **The judge names the group before the alert leaves** — it runs inside the scan; only our structured capture of that naming is a next-evening batch job (18:20 ET). The lateness in this signal is our plumbing, not the judge's information.
- **The +10 cannot be reached by any judge output without resequencing the scan:** the bonus is computed in `_score_ep`, and the judge runs afterwards and is *fed* the score.
- **The wider list read is free today** — same nightly snapshot, same lookup, no new code and no new latency (94% of theme rows are written 17:00–17:59 ET the night before, verified from write timestamps).
- **The nightly extraction of the judge's group names is finished, not growing:** 100% of eligible alerts from 2026-07-01 are done, 0% before, and that start date is hard-coded.

## The ceiling

- **292 of 346 alerts (84%) are in no theme at any stage on the day they fire.** That is the real constraint on this whole idea.
- **230 of 346 (66%) are reached by no signal I would trust** — every signal except peers, combined, reaches 116 of 346 (34%).
- **134 of 346 (39%) are reached by nothing at all**, peers included.
- **It is improving fast: over the last 30 days of the window (60 alerts) the live +10 reaches 15% not 6%, the wider list reaches 32%, and 68% are unthemed rather than 84%** — the engine roughly quadrupled its theme coverage inside the measurement window.
- **But that recent reach is mostly peers, and peers is exactly where it stops working** (2.00x separation in May, 0.96x in August) — coverage grew, the broadest signal did not.

## Recommendation

- **HIS — does a theme the engine has functionally retired still count as membership?** Dropping the 7-day floor buys +32 alerts (22→54 of 346) and 57% of the 49 floor-only alerts rejoin a live theme within 30 days. *Rec: yes, but as a smaller partial boost than a live theme, via CHANGE_PROCESS + backtest + sign-off — I have not touched it.*
- **HIS — should the judge's group name reach the score at all?** It needs the scan resequenced, and the cheap version (a group field on the judge's tool) changes the judge's prompt, which is grade-affecting. *Rec: not yet — its edge is on stocks already grouped, so it would mostly pay the boost to names the wider list already catches.*
- **HIS — the one that attacks the 84%: feed the EP into theme DISCOVERY** (his own #368 framing, "not seeing a theme does not mean no theme exists") rather than reading membership off it. *Rec: this is where the return is; a membership signal cannot reach a theme that does not exist.*
- **NO FORK on peers** — I am not recommending it at any threshold or weight.
- **MINE, $0, read-only:** the two measurements in "Still unknown" below. No paid runs, nothing deployed, nothing changed by this work.

## Still unknown

- **Whether any signal is right in HIS terms.** Every precision number here uses "the engine eventually put it in a theme" as the answer key — which is the very lateness he is complaining about. *The one measurement: re-seed his `themeless_winner` rows (31 labelled cases where he says a theme existed and we missed it, all currently outside the window) over the current 346 and check what each signal said on them. Mine, this week.*
- **Whether a peer signal built on the alert MORNING behaves differently.** Every peer definition tested looks back 20–60 days, structurally the wrong window for an event that happened at 9:31. *The one measurement: intraday co-movement from `mi_intraday_bars` on the alert morning itself. Mine.*
- **How much of the judge's naming is our own engine read back to us** — a quarter to a half of the groups it names match Lane-2 cohort names that were placed in its own prompt (25% word-for-word vs 2% against an unrelated day's cohorts). It survived the test that removes those, but its marginal reach is partly self-referential.
- **Whether the judge works outside AI:** 88% of the groups it names are AI-flavoured, and the same AI-data-centre story appears under five different labels — only 7 named alerts fall outside AI, too few to test.
- **Era caveat on every pooled number:** the rate at which any stock later joins a theme runs 4% in May to 80% in September. The judge's edge holds within a single month (1.77x); the peers edge does not.

---

## The short version

1. **The lookup is not the problem — coverage is.** 69-79% of EP alerts have no theme at any stage.
2. **The cheapest real gain needs no new signal**: today's rule pays 22 of 346 while the same
   nightly snapshot already knows about a theme for 72-108 of them. The narrowing is the 7-day
   recency floor plus the Accelerating/Mainstream stage filter, not a missing data source.
3. **Peers were measured and rejected** — they fire on 61% of EP alerts against ~50% of ordinary
   non-alerting stocks, and in August at 0.96x. That is noise, not membership.
4. **The judge's edge is on stocks already grouped**, so it would mostly pay names the wider lookup
   already reaches.
5. **The lever is discovery, not the lookup.** A membership test cannot reach a theme that was never
   born — which is step 1 and step 2 of his own sequence, where this work already sits.

## What this does NOT answer

- **Whether any signal is right in HIS terms.** Every precision number here uses "the engine
  eventually put it in a theme" as the answer key — which IS the lateness he is complaining about.
  The fix: re-score his 31 labelled `themeless_winner` rows, where he says a theme existed and we
  missed it, against each signal. Mine, this week, $0.
- **Whether a peer signal built on the alert MORNING behaves differently.** Every definition tested
  looks back 20-60 sessions, structurally the wrong window for an event at 9:31.
- **How much of the judge's naming is our own engine read back to it** — a quarter to a half of its
  group names match Lane-2 cohorts placed in its own prompt.
- **Anything about trade outcomes.** Step 3 stays parked.
