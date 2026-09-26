# #327 — what the issue is: the delayed-entry lane's diagnosis

**2026-09-26 (Saturday build slot, after Block 5, its addendum and the leaders / management read).**
Operator, 2026-09-26: *"We should have a good cohort already, unsure collecting more will change, we need to
understand what the issue is."* This document does not test another rule. It asks four descriptive questions
of the same ~3,400 fires — how the trades fail, what the entry moment looks like against a random session of
the same stock, which stocks these are, and how the EP itself behaved before the fire — and ranks what it
finds by how much of the loss each explains. THE ISSUE, the ranked causes and the implication are written
AFTER the Method section below was committed (`p7_diagnosis.py`'s docstring is the pre-registration of
record); nothing in the Method changed after that commit.

> **THE ISSUE (one sentence):** _pending — written after the probe runs._

## The decision it serves

His standing frame (2026-09-26): *"any EP related trades are low winrate by default, what we want is always to
catch big winners while limiting losses"* — and the question of the day: *"we need to understand what the issue
is."* The decision is what to do with the delayed-entry lane after three nulls: keep collecting, change what it
watches, change how it enters, or stop. **What would change it:** if the loss is concentrated in a path or a
moment the trigger itself creates (a same-session stop, a bounce into overhead supply), the issue is the trigger;
if it is concentrated in a kind of stock the lane admits, the issue is selection; if the fires lose about as
much as a random session of the same stocks, the lane is structurally a bad-moment buyer and nothing downstream
fixes it. **What would make this analysis wrong:** a population error (the one that voided the 09-01 numbers) —
which is why the first cut is what our own screen did on the gap day — or reading a day-0 stop as "never went
green" when the order inside that session is unknown, which the Q1 classes keep apart by construction.

## Method and population

**Committed before any Q1–Q4 number was computed.** The probe is `scripts/probes/_327_block5/p7_diagnosis.py`;
its docstring is the registration of record and this section mirrors it. Inputs are the Block 5 extract
(`extract_p0.sh`, `extract_p3.sh`) plus three new read-only pulls (`extract_p7.sh`: SPY / QQQ / IWM daily bars,
the EP scan log 2026-08-20 → 09-25, and `mi_ep_alerts` since July), P2's fire and control walks, P3's per-row
events and P6's runner list. $0 throughout; no toggle, table, deploy or PLAN.md line.

**Population.** Every fire in the extract with **≥ 10 sessions elapsed by 2026-09-25** (P2's `sessions_elapsed`;
n = 3,398), never settlement status.

**Its first cut — established during orientation, before this registration, and therefore declared here rather
than discovered later.** Each fired campaign is classified by what **our own EP screen did on the gap day**:
**EP-ALERT** = the (ticker, EP date) is a live-source row of `mi_ep_alerts` at any tier (the seed query's own
`LIVE_SOURCE_SQL`); **NOT-EP** = everything else, split by the furthest stage the scan log shows for that ticker-day
(universe floor — a prior close under the $5 `MIN_PREV_CLOSE` or prior-day volume under 50,000 shares — gap floor,
RVOL / pre-market volume, quality filter, extension, cooldown, scored below the bar, post-grade filter, no scan row;
`reject_stage` where stamped, else the `filter_reason` prefix). Seen before registration and disclosed: **22 of 941
fired campaigns are alerts (100 fires; 51 with ≥ 10 sessions elapsed); 855 campaigns — 3,460 fires, 92% — were
rejected at the universe floor, 783 of them for a prior close under $5**; the six 08-24 → 08-31 alerts (CHRN, CRWD,
DG, OKTA, SOLS, VEEV) reproduce the seed query's own docstring ("1,269 campaigns, SIX were EP alerts"); and 1,457
of the 3,075 settled stops in the population fell on the fire session itself. No other Q1–Q4 number was computed
before the registration commit. **Every table carries the two cohorts side by side**; the EP-ALERT cohort is small
and is reported as small, never pooled away.

**The outcome measure — the lane's own arm on the sessions-elapsed population.** `R10` = the incumbent stop plus
the lane's trail arm (a close below max(SMA10, SMA20)) read at session 10: −1.00R on a stop (house convention; P3
measured gap-charging at 0.03R on this cell and it is not applied), the exit close's R on a trail exit, else the
session-10 close marked to market; `R10_none` (no exit) beside it. Sources, in order: (1) production's recorded
settlement (`outcome`, `stop_hit_date`, `r_trail_s10`, `r_none_s10`, `mfe_r`) for settled rows — production walked
them with real minute bars at settle time, and they ARE the lane's own arm; (2) the 259 rows still open at the
extract are walked by the probe from the daily table with the real `sma_trail_line` (day 0 per P2's
`day0_bars_for_fire`; a day 0 that cannot be ordered abstains and is counted); (3) `unscoreable` rows are counted,
never scored. Fire-time prices are rescaled to the daily table's scale by P2's `scale_factor`; `entry_price` is
reported unscaled for the price buckets. **Anchors, printed before any table is read:** (a) the probe's walk on
settled rows with a resolvable day 0 must reproduce `stop_hit_date` and `r_trail_s10` (the P1/P2 number is
~99.8%); (b) the R10 mean on the ids P3 walked for its incumbent trail cell is printed beside P3's verified −0.29R
(n = 1,320) — a difference over 0.02R is stated before any other number is read.

**Q1 — how trades fail (the path), per pattern, both cohorts.** Path classes at session 10: **STOP-D0** (stopped
on the fire session; the order of "went green" vs "hit the stop" is unknown at daily grade — split green-first /
straight-down only where a post-fire minute source exists, otherwise "order unknown", never folded into
never-green); **NEVER-GREEN** (stopped at session ≥ 1 with no high above the entry strictly before the stop
session; a level fire's fire-day high counts, a minute fire's day-0 daily high never does — the `reached_4r`
rule); **GREEN-THEN-STOPPED** (a high above the entry before the stop session; sub-bucketed by that peak:
0–1R, 1–2R, 2–3R, > 3R); **OPEN-AT-S10** (trail-exited or marked; positive / negative). Sessions to stop:
0 · 1 · 2 · 3–5 · 6–10 · not by s10. The peak before the stop is reported twice: strict (before the stop
session) and recorded `mfe_r` (the stop session's own high folds in — the same-session caveat). Loss
contribution = the summed R10 of each class over the total summed R10.

**Q2 — the entry moment, fire vs P2's matched same-window non-fire control.** Rows are P2's own walks
(+2×ADR$ before −1×ADR$ at s10, pessimistic). Primary like-for-like read = the fire entered at the fire
session's **close** against the control's close entry (same convention on both sides, so the level-priced head
start P2 found cannot leak in); the recorded entry beside it. Pre-entry features in ADR$, identical for fires
and controls, t = the entry session: `drift3` (close[t−1] − close[t−4]), `drift1`, `bounce` (entry − min low over
[t−3, t] — the rise off the recent low into the entry, the dead-cat measure), `intraday` (entry − open[t]),
`overhead` (max high over [EP day, t−1] − entry — distance up to the campaign's running high; negative = above
every prior high), `dist_gap_high`, `pos_ep_close`, `pos_ep_low`, `prior_reclaims` (sessions in (EP day, t)
that already reclaimed the pattern's own level; for `ep_high_break`, prior sessions whose high reached the EP
high), `session_idx`; fires also carry `reentry_shape`. Strata = terciles cut on the pattern's **control**
distribution; the 2-D stratum = bounce tercile × overhead tercile. Decomposition: gap = [fire rate − control
reweighted to the fires' stratum shares] (within-stratum) + [reweighted control − raw control] (composition);
a stratum under 20 rows on either side is pooled into its neighbour and said so.

**Q3 — which stocks.** Per bucket: n · mean R10 · stopped-by-s10 rate · kept ≥ 3R · runner rate; both cohorts.
Buckets declared: cohort (and NOT-EP by rejection stage) · price at the fire (< $1, $1–5, $5–20, > $20) · EP
tier at the gap (alert HIGH · alert MODERATE incl. tier-'none' alerts · scored below the bar · rejected before
scoring) · `ep_score` terciles among scored · catalyst grade among graded (`catalyst_quality`, else
`llm_catalyst_quality`) · gap-size terciles (watch `gap_pct`) · sessions since EP (1 · 2 · 3–5 · 6–10 · 11+) ·
run-up into the EP by the screen's own formula ((prev close − MIN close over [EP − 10 calendar days, EP)) /
MIN close; < 10%, 10–25%, 25–50%, ≥ 50%) · active theme (scan-log flag; unknown reported as unknown) · market
on the fire day (SPY close-to-close up / down; the 5-session sign beside) · dollar-volume terciles (EP-day and
fire-day). **Runner labels:** primary = P6's campaign definition (EP date ≤ 09-04; highest high within 15
sessions ≥ +50% over the EP-day close — the definition behind the "9% of fires" fact; declared now: 0 of the
120 runner campaigns are alerts, so tier / score AUCs against it are degenerate by construction); secondary =
fire-anchored (highest high in sessions 1–10 after the fire ≥ +50% over the scaled entry; fully observed).
**AUC** = Mann-Whitney with ties at ½, Hanley-McNeil 95% CI, n_pos / n_neg, for every numeric pre-entry trait
against each label, on the whole population and within NOT-EP; a trait dark on more than half the rows is
reported as dark, not as a null.

**Q4 — the link to the EP itself.** Per fired campaign from daily bars, sessions 1–3 after the EP day:
**HELD** (every close ≥ the EP close), **FADED** (a close below the EP close, none below the EP low), **FAILED**
(a close below the EP low); depth = (EP close − min low over sessions 1–3) / ADR; the day-1 close move.
**Tautology declared:** `ep_low_reclaim` fires only after an undercut of the EP low and the two close-reclaim
patterns only after a dip under the EP close, so "did the EP fail" is partly the trigger's own precondition;
the read is how hard and how early, the fire's own position at entry (below the EP low · between EP low and
close · between EP close and high · above the EP high), the share of re-entry shapes, and the same
sessions-1–3 read on runner vs non-runner campaigns.

**Ranking the causes by loss.** A mechanism's share = the summed R10 of the fires it labels over the total
summed R10, within the cohort; overlapping labels are shown jointly and never summed across causes. The
population fact is the frame of the write-up, not a mechanism — a stock being rejected by the screen does not
make its fire lose.

⚖ **THE LINE.** Nothing here picks a stop, target, exit, selection rule or population; nothing is deployed.

## THE CAUSES, ranked by how much of the loss each explains

_pending — written after the probe runs._

## What this does not answer

Declared with the Method (the run may add to this list, never shorten it):

- **One month, one regime.** Fires 2026-08-25 → 09-11 at ten sessions; nothing here says what these patterns do
  in a different tape.
- **The EP-ALERT cohort is 22 campaigns and 51 fires at ten sessions.** It is the lane's intended population and
  it is too small to judge on its own; its tables are read as "what these 51 did", never as a rate.
- **Half the stops are same-session stops whose order is unknown at daily grade** (1,457 of 3,075 settled stops
  fell on the fire session, seen before registration). Where no post-fire minute source exists the class says
  "order unknown"; it is never resolved by assumption.
- **The primary runner label is a campaign label** (the stock ran +50% from its EP close within 15 sessions,
  P6's definition); a fire can sit after the run. The fire-anchored label is beside it for that reason, and it
  is capped at ten sessions so the whole population is observed.
- **Most pre-entry traits from the EP screen are dark for rejected names** (`ep_score`, catalyst grade, theme
  membership are computed only for names that reach grading). A dark trait is reported as dark, not as a null.
- **The peak-before-stop reading rests on daily highs**; a same-session ordering caveat is stated wherever
  `mfe_r` (which folds in the stop session's high) is used.
- **Nothing here re-prices the EP alert itself, tests a new rule, or picks one.**

## What it implies — for his ruling

_pending._

## Files

- `scripts/probes/_327_block5/p7_diagnosis.py` — the probe; its docstring is the pre-registration of record.
- `scripts/probes/_327_block5/extract_p7.sh` — the three supplementary read-only pulls (gitignored CSVs;
  `ep_scan_log.pulled_at` records the pull time).
- `p7_summary.json` (every table) — committed after the run; `p7_rows.csv` / `p7_q2_rows.csv` gitignored.
