"""Block 5 / P7 — WHY the delayed-entry lane loses: the diagnosis. $0, read-only, offline.

PRE-REGISTRATION OF RECORD (committed before any Q1-Q4 number is computed; nothing below
changes after). The operator, 2026-09-26: "We should have a good cohort already, unsure
collecting more will change, we need to understand what the issue is." Block 5 and its two
follow-ups (`327_exit_determination_2026-09-26.md`, `327_leaders_ep_management_2026-09-26.md`)
proved no stop x target x exit, no leader filter and no EP-style management pays on ~3,400
fires. This probe does not test another rule. It asks four descriptive questions of the same
fires and ranks what it finds by how much of the loss each explains.

──────────────────────────────────────────────────────────────────────────────────────────
POPULATION AND ITS FIRST CUT — established during ORIENTATION, before this registration,
and therefore DECLARED here rather than discovered later.
──────────────────────────────────────────────────────────────────────────────────────────
Population = every fire in the Block 5 extract with >= 10 sessions elapsed by 2026-09-25
(P2's `sessions_elapsed` >= 10 from `p2_fire_walks.csv`; n = 3,398), never settlement status.

The fired campaigns are classified by what OUR OWN EP SCREEN did on the gap day:
  EP-ALERT  the (ticker, ep_date) is a row of `mi_ep_alerts` with COALESCE(source,'live')='live'
            — the seed query's own LIVE_SOURCE_SQL — at any tier (HIGH / MODERATE / 'none').
  NOT-EP    everything else, split by the furthest stage the scan log shows for that
            (ticker, gap day): universe_floor (prev close < $5 MIN_PREV_CLOSE, or prior-day
            volume < 50,000 MIN_PREV_DAY_VOLUME) · gap_floor · rvol / pre-market volume ·
            quality_filter · extension · cooldown · scored-below-the-bar · post-grade filter
            (routine catalyst, M&A) · no scan row. `reject_stage` where stamped, else the
            `filter_reason` prefix (the older rows carry no stage column).
Seen before registration and disclosed: 22 of 941 fired campaigns are alerts (100 fires, 51
with >= 10 sessions elapsed); 855 campaigns (3,460 fires, 92%) were rejected at the universe
floor, 783 of them for a prior close under $5; the six 08-24..08-31 alerts (CHRN, CRWD, DG,
OKTA, SOLS, VEEV) reproduce the seed query's docstring ("1,269 campaigns, SIX were EP alerts").
Also seen: 1,457 of the 3,075 settled stops in the population fell on the fire session itself.
No other Q1-Q4 number was computed before this file was committed. EVERY table below carries
the two cohorts side by side (EP-ALERT n is small and is reported as small, never pooled away).

──────────────────────────────────────────────────────────────────────────────────────────
THE OUTCOME MEASURE — the lane's own arm, on the sessions-elapsed population
──────────────────────────────────────────────────────────────────────────────────────────
R10 = the incumbent stop + the lane's trail arm (a close below max(SMA10, SMA20)) read at
session 10: -1.00R on a stop (house convention; P3 measured gap-charging at 0.03R on this
cell and it is NOT applied here), the exit close's R on a trail exit, else the session-10
close marked to market. R10_none (no exit) beside it. Sources, in this order:
  (1) production's recorded settlement (`outcome`, `stop_hit_date`, `r_trail_s10`,
      `r_none_s10`, `mfe_r`, `mae_r`) for settled rows — production walked them with the real
      minute bars at settle time; these ARE the lane's own arm;
  (2) the 259 rows still open at the extract (outcome NULL, >= 10 sessions elapsed): the
      probe walks the same arm from the daily table with the real `sma_trail_line` (closes
      before the fire from `daily_closes(_warmup).csv`, day 0 per P2's `day0_bars_for_fire`
      — real post-fire 5-min bars, else the cached day-0 excursion, else the daily fold for a
      level fire); a row whose day 0 cannot be ordered ABSTAINS and is counted, never scored;
  (3) `outcome='unscoreable'` rows (degenerate geometry) are counted, never scored.
Every fire-time price is rescaled to the daily table's scale by P2's `scale_factor` (the
post-fire split rows); entry_price is reported UNSCALED for the price buckets (the price he
would have paid).
ANCHORS, printed before any table is read:
  (a) the probe's own walk on settled rows with a resolvable day 0 must reproduce
      `stop_hit_date` and `r_trail_s10` (match rate; the P1/P2 number is ~99.8%);
  (b) the R10 mean on the ids P3 walked for its incumbent trail cell (`p3_events.csv`,
      convention=recorded, stop=incumbent, target=none) is printed beside P3's verified
      -0.29R (n = 1,320); a difference over 0.02R is stated before any other number is read.

──────────────────────────────────────────────────────────────────────────────────────────
Q1 — HOW TRADES FAIL (the path). Per pattern, both cohorts.
──────────────────────────────────────────────────────────────────────────────────────────
Path classes at session 10, declared:
  STOP-D0     stopped on the fire session. At daily grade the order of "went green" vs
              "hit the stop" is UNKNOWN; where a post-fire minute source exists (real
              `mi_intraday_bars`, else the row's cached `day0_post_high`) the class is split
              into green-first / straight-down; otherwise "order unknown". Never folded into
              NEVER-GREEN.
  NEVER-GREEN stopped at session >= 1 with NO high above the entry strictly before the stop
              session. Day-0 credit: a level (daily-grade) fire's fire-day high counts (price
              passed the level on the way there — the `reached_4r` rule); a minute fire's
              post-fire bars count where a source exists; its day-0 DAILY high is never
              credited.
  GREEN-THEN-STOPPED  stopped at session >= 1 with a high above the entry before the stop
              session; sub-bucketed by the peak strictly before the stop session:
              (0, 1R] · (1R, 2R] · (2R, 3R] · > 3R.
  OPEN-AT-S10 not stopped by session 10: trail-exited (R at the exit close) or still marked
              at the session-10 close; split positive / negative.
Sessions to stop: 0 · 1 · 2 · 3-5 · 6-10 · not by s10. Peak before the stop reported TWICE:
strict (strictly before the stop session, from daily highs) and recorded `mfe_r` (the stop
session's own high folds in — the same-session ordering caveat, stated wherever it is used).
Loss contribution = the summed R10 of each class over the total summed R10 (a negative
number), per pattern and pooled, both cohorts.

──────────────────────────────────────────────────────────────────────────────────────────
Q2 — THE ENTRY MOMENT: fire vs the matched same-window non-fire control (P2's method).
──────────────────────────────────────────────────────────────────────────────────────────
Rows = P2's own walks (`p2_fire_walks.csv`, `p2_control_walks.csv`): +2xADR$ before -1xADR$
at s10, PESSIMISTIC bound. The control of a pattern = every non-fire session (any-pattern
`is_fire_session` False) of the campaigns where that pattern fired, entered at that session's
close (P2's `matched_controls`). PRIMARY like-for-like read = the fire entered at the fire
session's CLOSE (`close_pess_s10`) against the control's close entry — same convention on
both sides, so the level-priced head start P2 found cannot leak in; the recorded entry
(`pess_s10`) is reported beside it. Pre-entry features, on the daily table's scale, in ADR$
(P2's campaign ADR$), t = the entry session, identical for fires and controls:
  drift3         (close[t-1] - close[t-4]) / ADR         the prior three sessions' net move
  drift1         (close[t-1] - close[t-2]) / ADR
  bounce         (entry - min low over [t-3, t]) / ADR   the rise off the recent low into the
                                                          entry, the entry session's own low
                                                          included (the dead-cat measure)
  intraday       (entry - open[t]) / ADR                 the entry session's own move to the
                                                          entry (close - open for a control)
  overhead       (max high over [EP day, t-1] - entry) / ADR   distance UP to the campaign's
                                                          running high (overhead supply);
                                                          negative = above every prior high
  dist_gap_high  (EP-day high - entry) / ADR
  pos_ep_close   (entry - EP-day close) / ADR
  pos_ep_low     (entry - EP-day low) / ADR
  prior_reclaims the number of sessions in (EP day, t) that already reclaimed the pattern's
                 own level (EP low for ep_low_reclaim; EP close for ep_close_reclaim and
                 ep_close_620_prox: a session with low <= level < close); for ep_high_break
                 the number of prior sessions whose high reached the EP-day high. Fires also
                 carry `reentry_shape` (first vs a re-entry shape).
  session_idx    sessions since the EP day.
Strata = terciles of each feature cut on the pattern's CONTROL distribution (declared, not
tuned); the 2-D stratum = bounce tercile x overhead tercile. Decomposition per pattern:
  gap = fire rate - control rate
      = [fire rate - control rate REWEIGHTED to the fires' stratum shares]   (within-stratum:
                                                   fires do worse at the same kind of moment)
      + [reweighted control rate - raw control rate]                        (composition:
                                                   fires sit at worse kinds of moment)
reported per feature and for the 2-D stratum with n per stratum; a stratum under 20 rows on
either side is pooled into its neighbour and said so. "Buying into overhead supply / a
dead-cat bounce" is answered by the sign and size of the composition term for `bounce` and
`overhead`, and by the fire-vs-control rate inside each tercile.

──────────────────────────────────────────────────────────────────────────────────────────
Q3 — WHICH STOCKS. Pre-entry buckets, declared now; per bucket n · mean R10 · stopped-by-s10
rate · kept >= 3R (R10 >= 3) · runner rate. Both cohorts.
──────────────────────────────────────────────────────────────────────────────────────────
  cohort            EP-ALERT vs NOT-EP, the latter by rejection stage
  price at the fire unscaled entry_price: < $1 · $1-5 · $5-20 · > $20
  EP tier at the gap  alert HIGH · alert MODERATE (incl. tier 'none' alerts) · scored below
                    the bar · rejected before scoring
  ep_score          terciles among scored fires (scan log max ep_score that day; alert score
                    where alerted)
  catalyst grade    scan-log `catalyst_quality`, else `llm_catalyst_quality`, among graded
  gap size          terciles of the watch table's `gap_pct`, cut on the fire population
  sessions since EP 1 · 2 · 3-5 · 6-10 · 11+
  run-up into the EP  the screen's own formula from daily bars: (prev close - MIN close over
                    [ep_date - 10 calendar days, ep_date)) / MIN close x 100 (ep_detector's
                    extension check); < 10% · 10-25% · 25-50% · >= 50% (the screen's cap)
  active theme      scan-log `in_active_theme` (alert row first); unknown reported as unknown
  market, fire day  SPY close-to-close on the fire date: up / down; the SPY 5-session return
                    sign beside it
  dollar volume     terciles of EP-day $ volume (watch `ep_dollar_volume`) and of fire-day
                    $ volume (day_volume x day_close), both
Runner labels: PRIMARY = P6's campaign definition (EP date <= 09-04, the highest high within
15 sessions of the EP >= +50% over the EP-day close — the definition behind the "9% of fires"
fact he holds; fires in later campaigns are outside the label's population and shown as such;
declared now: 0 of the 120 runner campaigns are alerts, so tier / score AUCs against this
label are degenerate by construction, not a null). SECONDARY = fire-anchored: the highest high
in sessions 1..10 after the fire >= +50% over the scaled entry — fully observed for the whole
population, and the one that says "this fire was in a stock that then ran".
AUC = Mann-Whitney with ties at 1/2, Hanley-McNeil 95% CI, n_pos / n_neg, of every numeric
pre-entry trait (price, gap %, ep_score, sessions since EP, run-up, EP-day and fire-day $
volume, adr20_pct, stop_width_pct, SPY return, and Q2's drift3 / bounce / overhead /
pos_ep_close / prior_reclaims) against each runner label, on the whole population and within
NOT-EP; a trait dark on more than half the rows is reported as DARK, not as a null.

──────────────────────────────────────────────────────────────────────────────────────────
Q4 — THE LINK TO THE EP ITSELF. Per fired campaign, from daily bars.
──────────────────────────────────────────────────────────────────────────────────────────
Sessions 1-3 after the EP day against the EP close and EP low:
  HELD    every close of sessions 1-3 >= the EP-day close
  FADED   a close below the EP close, none below the EP low
  FAILED  a close below the EP-day low within sessions 1-3
plus depth = (EP close - min low over sessions 1-3) / ADR and the day-1 close move in ADR.
TAUTOLOGY DECLARED: ep_low_reclaim fires only after an undercut of the EP low and the two
close-reclaim patterns only after a dip under the EP close, so "did the EP fail" is partly the
trigger's own precondition. The read is therefore HOW HARD and HOW EARLY, the fire's own
position at entry (entry < EP low · EP low <= entry < EP close · EP close <= entry <= EP
high · above the EP high), the share of re-entry shapes, and the same sessions-1-3 read on
runner vs non-runner campaigns (do the stocks that ran hold the EP close?).

──────────────────────────────────────────────────────────────────────────────────────────
RANKING THE CAUSES BY LOSS — method before numbers.
──────────────────────────────────────────────────────────────────────────────────────────
A mechanism's share = the summed R10 of the fires it labels over the total summed R10, within
the cohort. Overlapping labels (a same-session stop that is also a re-entry into a FAILED EP,
etc.) are shown in a JOINT table and never summed across causes. The population fact (which
cohort a fire is in) is the FRAME of the write-up, not a mechanism: a stock being rejected by
the screen does not make its fire lose.

THE LINE: nothing here picks a stop, target, exit, selection rule or population; no toggle,
table, deploy or PLAN.md line. Outputs: p7_summary.json (every table, committed),
p7_rows.csv / p7_q2_rows.csv (per-row features and labels, gitignored, regenerable).
Inputs: the P0/P3 pulls + extract_p7.sh (index_daily.csv, ep_scan_log.csv, ep_alerts.csv) +
p2_fire_walks.csv / p2_control_walks.csv + p3_events.csv + p6_summary.json.
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

LAST_SESSION = date(2026, 9, 25)
PRIMARY_K = 10
PATTERNS = ("ep_low_reclaim", "ep_close_reclaim", "ep_high_break", "ep_close_620_prox")


def main():
    print("P7 pre-registration committed; the computation is the next commit. "
          "Nothing in the docstring above changes after this point.")


if __name__ == "__main__":
    main()
