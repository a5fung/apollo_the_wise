# HTF — High Tight Flag (Family-A Setup 2)

**Phase**: Shadow (telemetry-only — NO order fires from the detector; `/flags`→`/htf` board + #94
intraday break + EOD digest are observational). Promotion path: the breakout-entry shadow → paper → live.
**Origin (SOURCED)**: O'Neil (*How to Make Money in Stocks*), Minervini (*Trade Like a Stock Market
Wizard*), Qullamaggie — operator-sourced + shared, `docs/methodology/operator_shared_notes.md` (HTF block,
2026-06-22). **Provenance rule (ADR 0013 §2 / #358): every gate below cites that source; no unsourced number.**
**Code**: `agents/market_intelligence/flag_detector.py` — `compute_flag_metrics`. Daily 17:25 ET scan +
the #94 intraday break scan.

> **Why this exists (the n=1 story):** the prior criteria (`runup ≥ 50% / 60d`, `proximity ≤ 20%` off the
> pivot close, + the #80 runup-scaling) were built on **n=1** — a single-case pick (first commit
> 2026-05-01), never validated. That is the exact reason Family-A was split into the *sourced* setups: the
> generic runup→coil detection moved to **Anticipation** (the coil-finder), freeing this detector to become
> the *specific* HTF — the `90%` flagpole is the "high tight" trait that distinguishes a monster-runup flag
> from a generic coil. The swap REPLACES an unsourced n=1 number with the literature (operator-confirmed
> 2026-06-27: no N≥10 P&L backtest — the old 50/60 was the n=1; the gate is spec-correctness + a `/flags`
> eyeball + the sourced sign-off, on an alert-only/no-money detector).

## Detection criteria (sourced — `compute_flag_metrics`)

The 5-stage state machine (`unqualified → WATCH → TIGHTENING → COILED → TRIGGERED`/`INVALIDATED`), the
hysteresis (a downgrade held ONE night, then the reading stands — held night after night until #697 item 5,
2026-10-11, made the code match this and `flag_continuation.md`), and the volatility-relative tightness gates (range/vol
contraction, fresh-tightening, RMV) are UNCHANGED (operator: "I like how it shows which stage a stock is at"). Only the runup + flag-depth + trend
criteria were swapped/added.

| Gate | Sourced value | Source | Code |
|---|---|---|---|
| **Flagpole magnitude** | `pivot_high / 40d_low ≥ 1.9×` (≥90% in ~8wk) | spec `C≥1.9×C₄₀` / `High₄₀≥1.9×Low₄₀` | `_RUNUP_MIN_RATIO=1.90`, `_RUNUP_LOOKBACK_DAYS=40` |
| **Flag depth** | `base_low ≥ 0.75×pivot_high` (≤25% pullback, on the ABSOLUTE low) | spec `Close≥0.75×High₄₀`, tightened to the low | `_FLAG_DEPTH_MIN=0.75` |
| **Trend** | `close ≥ sma_50` AND MAs stacked `10≥20≥50` (Stage-2 uptrend) | spec "above the 10/20/50 MAs" | `_SMA50_WINDOW` + the trend block |
| **Stage-2 (long-term)** | `close ≥ 200d MA` AND `pivot_high ≥ 75% of the 52w high` (near highs, not a crash-recovery) | spec "Stage-2 uptrend (Minervini)" | `_SMA200_WINDOW`, `_STAGE2_NEAR_HIGH_MIN`; needs `_HISTORY_DAYS=260` (TRADING rows since 2026-09-05 — see change log) |
| **Flagpole data-artifact** | reject a >50% single-day close jump with `vol < 2× window avg` | Gemini 6/27 (split / bad-tick backstop) | runup-window guard |
| **Flagpole volume** | ≥1 day in the 40d window at `vol ≥ 2× window avg` | spec "undeniable institutional demand"; Gemini 6/27 | `spike_days ≥ 1` |
| **Liquidity** | ADV > 500k shares, ADR > 4% | spec | ✅ ENCODED 6/28 in `compute_flag_metrics` (per-ticker — so EVERY universe path is gated, not just the organic SQL one; VERIFY found the $5M dollar-vol floor didn't cover it). Tunable named constants: `_HTF_MIN_ADV_SHARES=500_000` (firm liquidity floor) + `_HTF_MIN_ADR_PCT=0.04` (STARTING value — 4% is NOT canonical, sources 3-6%; DATA-GATED tune `htf_adr_threshold_tune` once the breakout-shadow accrues N≥10 settled winners). Impact: dropped 1 of 2 current candidates (under-liquid). |
| **Tightness / vol dry-up** | volatility-relative range/vol contraction + RMV | ADR 0013 (signed) | UNCHANGED |
| **Breakout entry** | close > flag-high on ≥150% ADV (buy-stop-limit) | spec | `_BREAKOUT_VOL_RATIO=1.50` (Phase-3 shadow) |
| **TRIGGERED licence** (the EOD state, not the buy) | a breakout reads TRIGGERED only when LICENSED: COILED today, or a COILED / TIGHTENING / TRIGGERED **stored** label in the last 5 calendar days (held labels count). The breakout leg itself (close over the base's highest close on ≥ 1.5× the base's recent volume) is unchanged | operator ruling 2026-10-11 (#146); evidence `docs/analysis/146_detection_page_2026-10-11.md` | `_TRIGGER_LICENCE`, `trigger_licence` — dropping its last two entries is the one-line revert |
| **Catalyst-backed** | — | spec | OUT OF SCOPE — separate catalyst axis (#189/#201), not flag geometry |

### Reasoned deviations from the literal spec (documented per the provenance rule)
- **Flagpole anchor (✅ VERIFIED 6/28 — the detector form IS the primary definition, not a deviation):**
  the detector measures the runup at the **pivot** (the pole top) — `pivot_high / min(low, 40d ending at
  pivot) ≥ 1.9`. This IS the primary O'Neil/Minervini definition: the pole is the run-up measured AT its
  peak. Verify 6/28 (20 prod names) confirmed a today-anchored trailing-40d form (`high(40d)/low(40d)` from
  scan_date) DIVERGES — it qualifies ~3/10 fewer post-pole bases, because today's window has walked off the
  early-runup low and measures from INSIDE the flag, not the pole. Operator-confirmed 6/28: HTF is a
  well-defined setup — use the PRIMARY definition, do NOT invent our own; the today-anchored form was a
  non-primary interpretation, REJECTED. (memory `feedback_established_setup_use_primary_definition`)
  **Since 2026-09-04 (#592) the pole top only walks forward over a FORMED flag once price has CLOSED
  above it** (`_flag_resolved_by`): a wick over the top that closes back inside the flag is not a new
  pole top, so the 40-session window no longer slides into the flag. A pole still extending (fewer
  than `_BASE_AGE_MIN_WATCH` bars since the pivot) walks as before. Change-log entry below.
- **Flag depth on the absolute low (not the close):** the spec writes `Close≥0.75×High₄₀`; we tighten to
  `min(low)≥0.75×High₄₀`. O'Neil/Minervini reject a deep intraday shakeout that rallies to a tight close
  (the spring uncoiled). Operator-endorsed (Gemini 6/27); confirm via the eyeball. **Since 2026-09-19
  (#610) BOTH readings are RECORDED per candidate-day** — `depth_on_low` (this gate's quantity) and
  `depth_on_close` (the spec literal), alongside `sma20_margin` and `ma_stack_margin`, on
  `mi_flag_candidates` — so the 2026-09-18 ruling ("observe several, act on one") accrues live data.
  The gate still acts on the low; the columns are read by nothing. Change-log entry 2026-09-19.
- **`#80` runup-scaling removed (CHANGE_PROCESS #3 — why it was WRONG, not just superseded):** #80 relaxed
  the proximity band to ~35% for high-runup names. That is correct for a GENERIC flag (deeper bases are
  still valid setups) but WRONG for HTF, where ≤25% tightness is DEFINITIONAL — the "tight" in
  high-tight-flag. The generic-flag recall #80 served is now Anticipation's job; HTF is the tight subset.
- **The 10-day is not a close-above floor:** a flag routinely tests the 10/20 MA on a support pullback
  (it's the stop/trail reference, not a veto). The trend gate vetoes on the 50-day + the MA stack instead.

## Management (Phase 4, shadow)
Scale 33–50% into strength 3–5 days post-breakout → move the remainder to breakeven → trail the runner on
the 10/20-day **EMA** (exit only on a daily close below). Stop = the tightest-day low / 10–20 EMA, hard
max-loss 5–8%. Sizing risk 0.5–1% of equity. Target = the flagpole height added to the breakout.

## M&A suppression on the named stages (`flag_scan`, not `compute_flag_metrics`)

Backfilled into this SSoT 2026-07-24 (#502) — these layers had lived only in `flag_detector.py`. They
run AFTER scoring, on `TIGHTENING`/`COILED`/`TRIGGERED` rows (`_MNA_SCREENED_STAGES`; TIGHTENING added
2026-10-04, #598 — WATCH is digest-silent and is NOT screened). A hit rewrites the persisted row to
`stage='unqualified'` with `reason='mna_filter:<source>'` — kept, not deleted, so the filter's hit rate
stays auditable.

**Why the board needs this at all:** once price is pinned at an announced deal value it stops moving.
Range collapses to bid–ask noise and volume bleeds out — which is *mechanically identical to a coil*.
The tightness that scores a deal-pinned name COILED **is** the pin. Geometry alone cannot tell them apart.

| Layer | Test | Catches |
|---|---|---|
| 1 — news | `ma_filter.is_likely_ma(check_polygon=True, polygon_lookback_days=21)` | deals Polygon has a headline for |
| 2 — mature pin | median (H−L)/C over last **10** sessions < **0.5%** AND ≥**5** sub-0.5% sessions | pins ≥ ~3-4 weeks old (~session 13+) |
| 3 — fresh pin (#502) | 5-session band ≤ **2.5%** AND ≥**5×** volume spike (max vol last 10 / mean vol sessions 11–40) | pins days old, through session 10 |
| 3b — sticky carry (#502 refinement, 2026-08-06) | today's band still ≤ **2.5%** AND layer 3's own conjunction fired as-of 1–**5** sessions ago (re-runs the shipped `_evaluate_fresh_pin` on the trailing window; no new persistent state) | bridges the measured session-11–12 hole below |

⚠ **Layers 2 and 3 were documented as "complementary by deal age" — that was FALSE, and is
corrected here (2026-08-06, #502).** Measured against production: layer 3's own-data conjunction
stops firing on session 11 (the announcement's volume event ages out of its 10-session window);
layer 2 doesn't reach a qualifying 10-session median until ~session 13. Sessions 11–12 are a real,
measured hole where a still-pinned deal reads as a plain coil and leaks onto the actionable board —
this is exactly what happened to ATAI on 2026-07-30/07-31 (see change log below). Layer 3b closes
that hole by carrying layer 3's own last-verified verdict forward, released the moment today's own
band stops looking pinned. All layers fail OPEN — a missing signature never suppresses.

## Surfacing — the 17:25 ET digest and its stage-transition push (#598)

**One message a day, built by `flag_detector.send_flag_digest` / `build_flag_digest`, sent as Telegram HTML.**
Suppressed entirely on a day with no TRIGGERED, no COILED and no new transition. Sections, in order:

1. **`NEW TODAY`** — every ticker that moved **up into TIGHTENING or COILED on this scan** (#598), one line
   each: `ticker — STAGE · run-up +N% · pivot $P · range R×, volume V× · base Nd`. `pivot` is
   `pivot_high_price` (the pole top); `range` / `volume` are `range_contraction_ratio` /
   `vol_contraction_ratio` (the base's last 5 days against its first 5 — 1.00 is no tightening; the stage bars
   are `_RANGE_CONTRACTION_MAX=0.75` / `_VOL_CONTRACTION_MAX=0.70`, quoted live in the message footer). A
   fresh-tightening entry adds `last 2 bars tight`. **A base of 5 sessions or fewer (`_SHORT_BASE_MAX`)
   prints neither ratio** — the detector's last-5 and first-5 windows are the same bars there, so both are
   exactly 1.00 by construction (pinned against the real detector in `tests/test_htf_criteria.py`). It prints
   the last-2-bars measure instead (`fresh_2bar_tr_pct ÷ atr14_pct`, tight under `_FRESH_TIGHT_RATIO_MAX=0.60`):
   `last 2 bars tight (0.53× usual range)` (fresh path fired: range under the bar AND volume dry) /
   `last 2 bars 0.55× usual range (tight on range, volume not dry)` (under the bar, did not fire) /
   `last 2 bars 0.63× usual range` (over the bar) / `tightness n/a` when it cannot be computed (base under 4
   days, no ATR). The same rule applies to the `COILED — still coiled` roster and to the `/flags` board and
   `/flags TICKER` history. The one-sentence legend for the measure is printed wherever a short-base row is
   rendered: after the `NEW TODAY` footer, or — when the short-base name is already coiled and so only in the
   standing roster — on its own line under that roster (never twice). Display only — no stage, threshold or
   detection reads it (wk1010, 2026-10-10). The footer says in so many words that it is **a watch
   list, not a trade signal — no buy point or stop is set** (a stage is a state, not a setup; CLAUDE.md).
2. `TRIGGERED`, 3. `COILED — still coiled` (names already coiled, not the ones listed in `NEW TODAY`),
   4. a one-line `N dropped out` count (#479).

**The transition rule** (`stage_transitions`, pure): *push when rank(previous stored stage) < rank(today's)*
and today is TIGHTENING or COILED; rank 0 = no row in the last 5 days / `unqualified` / WATCH / INVALIDATED,
TIGHTENING = 1, COILED = 2, TRIGGERED = 3. So: WATCH / unqualified / INVALIDATED / absent → TIGHTENING pushes;
TIGHTENING → COILED pushes; **staying** in a stage is silent; a relapse (COILED → TIGHTENING) is silent;
leaving and re-entering pushes again. `previous` is `db.get_yesterday_flag_stages` (the same map the scan's
hysteresis reads), `today` is the scan's post-M&A `by_stage`. Nothing here changes a stage, a threshold, an
entry or a trade path — it reads what the scan already decided.

**Dedupe + record.** One `flag_stage_transition` audit row per transition pushed, summary
`<TICKER> entered <STAGE> <scan_date>` (detail JSON: previous stage, run-up, pivot, range, volume, base age,
`telegram`). The key carries the SCAN date — not the date the row was written — so a #672 recovery re-run of
the same scan on a later calendar day still dedupes. Only a **delivered** row dedupes; a push whose Telegram
failed is written as `… (not delivered)` and goes out again on the next run of that scan. The lookup fails
open (a repeat beats a silent drop). A broken transition step writes `flag_stage_transition_error` (named by the
nightly `%error%` sweep) and the rest of the digest still goes out.

**Why folded into the digest, not a message of its own (decided 2026-10-04).** The digest already reaches the
operator from the same run, and the old `NEW TIGHTENING` roll-call it replaces WAS the transition surface —
bare tickers, no numbers, so nothing to chart from (CDNA, TIGHTENING on 2026-08-18, a day before the trader
bought it). A second message a minute apart would be noise. What changed: that block now carries the fields,
also catches re-entry from `unqualified` / INVALIDATED (the old test was `previous in (None, WATCH)`), and the
COILED roster no longer re-lists a name on the day it is announced. The old `COILED — actionable setup` header
is now `COILED — still coiled` (it called a state a setup). `agent.py`'s `/flags` header was the same wording and is now `COILED — tightest bases, watch only` (2026-10-04); the Friday watchlist section label `Flag Setups` became `Flag Bases … (watch only)`.

**Deploy scope: `flag_detector.py` is NOT on `scripts/exec_loaded_modules.txt` → `deploy.sh market-agent`
only.** The dedupe query is inline for that reason (`db.py` is execution-loaded); the event names are local
constants, not `audit_events.py` (also execution-loaded). `channels/telegram.py` is untouched — no new
command. Tests: `tests/test_598_flag_stage_transition_push.py`.

**Send record — one `flag_digest_sent` audit row per digest SEND (#697 item 1b, 2026-10-11).** Before this a
send left no trace: only a stage *transition* wrote a row, so "did we tell him about X" was unanswerable from
prod. Summary `flag digest <scan_date> (sent|not delivered)`; detail JSON `{scan_date, telegram, new_today,
triggered, coiled, coiled_not_shown, dropped_out}` — the tickers each section LISTED, taken from the same
`digest_sections()` the message is built from (so the record cannot drift from the text), with the standing
COILED names the 8-name roster did not print named in `coiled_not_shown`. Written after the send, outside the
transition step (a broken transition step cannot lose it), delivered or not. **A quiet day sends nothing and
writes nothing** — a missing row is "no digest that night", or (rarely) a digest sent whose audit WRITE failed: that is
only a logged warning (`db.log_audit_event` never raises, so no `_error` row can follow it), and the missing row is the
signal. `flag_digest_sent_error` names a different failure — the record could not be BUILT (the detail JSON), pinned by
`test_a_record_build_failure_is_named_by_the_error_event...`. Neither breaks the scan. NOT a dedupe key: a #672
recovery re-run of the same scan sends a second message and writes a second row. Query: `SELECT created_at, summary FROM mi_audit_log
WHERE event_type='flag_digest_sent' AND detail LIKE '%"CDNA"%'`.

**Friday watchlist — the "Flag Bases — TRIGGERED / COILED / TIGHTENING (watch only)" section (#697 item 1a/1c, 2026-10-11; TRIGGERED added by the #146 review, same day).**
`friday_watchlist._fetch_flag` reads the latest `mi_flag_candidates` scan (within 7 days) and prints up to 3
TRIGGERED + 5 COILED + 3 TIGHTENING (M&A-screened names are `unqualified`, so absent). **TRIGGERED is listed because #146 would otherwise
take names OFF this list on the night they break out:** the section used to be `stage IN ('COILED','TIGHTENING')`, and a name the shipped rule leaves at
TIGHTENING now reads TRIGGERED, so it dropped off on exactly the night it mattered — the review's replay of this branch's code over the page's 444 sessions (288 tickers, threaded like the page; not re-run in the fix commit) found 25 Friday ticker-days leave the pool
that way, 8 of them in 2026, two on the live board (CDNA 2026-07-31, CHPT 2026-09-18). Each TRIGGERED row reads `TRIGGERED · from TIGHTENING · base 12d ·
run-up +130% · close $36.19 over the base's highest close $34.42` (the path in the same words as the digest, `flag_detector.triggered_from_label`); a row HELD
over from yesterday says `TRIGGERED · held over from yesterday (today reads TIGHTENING)`. They list first within the section (the FLAG tier's own priority, so the stored `int(priority)` stays 2 and never reads as the EP HIGH tier, and an
EP-sourced name keeps its EP primary); the 25-ticker cap can now be bound by up to 11 flag names instead of 8. Display only: no order / entry / sizing / safeguard path reads it. **It has NO strategy gate.** It used
to return `[]` when `should_run("flag_continuation")` was false; that retired strategy row went
`deprecated / enabled=false` on 2026-08-02 and the section rendered EMPTY from then on (the last stored Friday
list carrying a FLAG name is the week ending 2026-07-31 — prod `mi_weekly_watchlists`). The detector has no
strategy row of its own (`run_flag_scan`'s own gate was removed the same week), so a watch surface of the
detector must not read one. The tightness text is `flag_detector.board_tightness(r, compact=True)` — `r0.45
v0.80` on a base of 6 sessions or more, the last-2-bars measure on 5 or fewer — never the raw `r1.00` (which is 1.00
by construction on a short base; KOD, base 5d, Friday 2026-10-09: stored 1.000 / 1.000, real reading 0.63). Its
SELECT therefore also pulls `fresh_tight_fires`, `fresh_2bar_tr_pct`, `atr14_pct`. Priority is unchanged
(`FLAG` ranks 2nd, behind EP HIGH): when the 25-ticker cap binds, up to 8 flag names displace the lowest-priority
ambient rows, as they did before 08-02. Tests: `tests/test_697_htf_reach_repairs.py`.

**Which path licensed a TRIGGERED read (#146, 2026-10-11).** Every TRIGGERED line says it, in the same words everywhere
(`flag_detector.triggered_from_label`): `from COILED` / `from TIGHTENING` / `re-trigger` (after an earlier TRIGGERED). The 17:25
digest's TRIGGERED row reads `• TICKER — from TIGHTENING · base 12d · run-up +130% · volume 2.48× · close $36.19 over the base's highest close $34.42`, and its
header carries the day's split (`TRIGGERED (3) 1 from COILED · 2 from TIGHTENING`, `triggered_bucket_summary`); `/flags` shows the
same row and header; `/flags TICKER` appends `· from TIGHTENING` to the TRIGGERED day; `/watch` (the Tight-Range Watchlist) writes `(base 12d · from TIGHTENING)` and the same split in the
TRIGGERED group header; `/setup TICKER` writes `TRIGGERED · from TIGHTENING — base …` and keeps the path through the run-collapsing (`TRIGGERED (from TIGHTENING)`);
the Friday watchlist lists TRIGGERED names with the path (above). A HELD TRIGGERED row (yesterday's TRIGGERED kept over a
lower raw read) and any legacy row carry no path — nothing licensed them today — so the header split counts them as `N held` and its parts always add up to the number
beside it (`TRIGGERED (3) 1 from COILED · 1 from TIGHTENING · 1 held`).

**The close level in the TRIGGERED line.** The gate tests the close against the base's highest CLOSE (`base_high_close`), which is not the stored `base_high` (its highest
HIGH). The line used to print `close $X above $base_high` — false on about a third of reads (52 of the 143 reads under #146 close at or under `base_high`, 16 of the 42 shipped
ones; HTFL 2026-10-05 closed 52.21 against a base high of 52.22). It now names the level the gate used, parsed from the row's own `reason` (`close_52.21>base_high_close_51.90`):
`close $52.21 over the base's highest close $51.90` (`flag_detector.triggered_close_phrase`; a row with no readable reason prints `close $52.21 · base high $52.22` with no
comparative). The parser is pinned against the detector's real output in `tests/test_146_unpark_triggered_licence.py`. Display only: nothing gates on the label or the line.

## Bucket the TRIGGERED reads (#146, 2026-10-11) — how to split performance by the path that licensed the breakout

His reason for the stamp: *"so that we can track performance from each and if we get too many breakouts we can discern where they come from."*

**The stamp.** `mi_flag_candidates.triggered_from`, written on a **raw** TRIGGERED read only (`stage = 'TRIGGERED' AND held_from_stage IS NULL`):
`'coiled'` (COILED today, or a COILED label in the 5 calendar days before — the shipped path), `'tightening'` (a TIGHTENING label and no COILED),
`'retrigger'` (only an earlier TRIGGERED label). Precedence coiled > tightening > retrigger (`flag_detector.trigger_licence`, pure). NULL on
every other row, **including a held TRIGGERED row** — filter `held_from_stage IS NULL` or the holds pollute the counts (the detection page excluded
them for the same reason). Every raw TRIGGERED row written before the change was licensed by the shipped path, so the schema step labels them
`'coiled'` once, when it adds the column; **from then on a raw TRIGGERED row with a NULL stamp is a defect, not history.**

**Two different facts — they must not contradict, and they are not the same.** `parent_stage` on `mi_flag_breaks` / `mi_htf_breakout_shadow` = the stage of
the flag's LAST stored row when the intraday break fired (copied from `mi_flag_candidates.stage` at the parent scan date). `triggered_from` = the strongest
licence ANYWHERE in the 5-day window before the EOD read. So a parent of COILED can only be `'coiled'`; a parent of TIGHTENING is `'coiled'` (a COILED a few
days back) or `'tightening'`, never `'retrigger'`; a TRIGGERED parent may be any bucket (pinned over every possible window in
`tests/test_146_unpark_triggered_licence.py`). **Measured on prod 2026-10-11** (`scripts/probes/_146_unpark/q4_agree.out`, all 27 shadow rows): `parent_stage`
equals the stage of the candidate row it points at on 27 of 27; the 3 breaks whose same-evening EOD read was a raw TRIGGERED (CHYM 08-19, XHLD 09-09, IOVA 09-14)
all had a COILED parent; the other 24 had no TRIGGERED EOD read under the shipped rule (20 TIGHTENING parents, 3 TRIGGERED parents whose EOD row was a hold or absent,
1 COILED). The two populations differ — an EOD TRIGGERED read need not have an intraday break and an intraday break need not close TRIGGERED — so join on the
break date (below), never assume they line up.

**Era rule for Q0 and Q2: `scan_date >= DATE '2026-06-27'` (the sourced HTF rebuild, change log 2026-06-27).** Stored raw TRIGGERED rows from before it were read by
the RETIRED 50%/60-session pole rule (25 of the 30 rows on the day-one prod read: 05-06 → 06-19); the detection page excludes that era for the same reason, so a
per-path comparison that mixes eras compares two different detectors. The backfill still stamps them `'coiled'` (that WAS the only licence), the SELECTs below leave them out.

**Q0 — how many raw reads came from each path** (`mi_flag_candidates` alone):
```sql
SELECT triggered_from AS bucket, count(*) AS reads, min(scan_date) AS first_seen, max(scan_date) AS last_seen
FROM mi_flag_candidates
WHERE stage = 'TRIGGERED' AND held_from_stage IS NULL AND scan_date >= DATE '2026-06-27'
GROUP BY triggered_from ORDER BY 1;
```
**Q1 — the ONE SELECT that splits the recorded breakout performance (shadow R) by path.** Joins each intraday break to the SAME evening's EOD row on the
break date; a break whose EOD read was not a raw TRIGGERED lands in its own bucket, with its `parent_stage` beside it:
```sql
SELECT COALESCE(c.triggered_from, 'no EOD TRIGGERED read') AS bucket, s.parent_stage,
       count(*) AS breaks,
       count(*) FILTER (WHERE s.outcome IS NOT NULL) AS settled,
       count(*) FILTER (WHERE s.outcome = 'capture') AS capture,
       count(*) FILTER (WHERE s.outcome = 'stop') AS stop,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY s.realized_r) FILTER (WHERE s.outcome IS NOT NULL) AS med_realized_r
FROM mi_htf_breakout_shadow s
LEFT JOIN mi_flag_candidates c ON c.ticker = s.ticker AND c.scan_date = s.break_date
                              AND c.stage = 'TRIGGERED' AND c.held_from_stage IS NULL
GROUP BY 1, 2 ORDER BY 1, 2;
```
**Q2 — did each path's breakouts hold** (the detection-page measure: a close under the base LOW within the next 10 sessions; raw bars, so a split inside
the 10 sessions corrupts a row — check an outlier before trusting a small n):
```sql
SELECT c.triggered_from AS bucket, count(*) AS reads,
       count(*) FILTER (WHERE f.n = 10) AS settled_10_sessions,
       count(*) FILTER (WHERE f.n = 10 AND f.min_close < c.base_low) AS closed_under_base_low_within_10
FROM mi_flag_candidates c
CROSS JOIN LATERAL (SELECT count(*) AS n, min(x.close) AS min_close
                    FROM (SELECT d.close FROM mi_daily_closes d
                          WHERE d.ticker = c.ticker AND d.trade_date > c.scan_date
                          ORDER BY d.trade_date LIMIT 10) x) f
WHERE c.stage = 'TRIGGERED' AND c.held_from_stage IS NULL AND c.scan_date >= DATE '2026-06-27'
GROUP BY c.triggered_from ORDER BY 1;
```
**Day-one baseline** (dry-run on prod 2026-10-11 with the column simulated as the backfill will write it — `scripts/probes/_146_unpark/q8_ssot_selects_dryrun.out` runs Q0–Q2 exactly as written above, era rule included; `q9_era_split_dryrun.out` splits the 30 stored raw reads by rule era):
the stored table holds **30 raw TRIGGERED reads, 25 of them from the retired pre-06-27 rule (05-06 → 06-19) and 5 from the sourced rule (06-30 → 09-14)**; the backfill labels all 30 `coiled`, Q0 and Q2 read the 5.
Q0 5 raw reads, all `coiled`, 2026-06-30 → 09-14. Q1 `coiled`/COILED parent 3 breaks (3 settled, 2 capture, median +3.0R); `no EOD TRIGGERED read`: TIGHTENING parent 20
(10 settled, 0 capture, median −0.69R), TRIGGERED parent 3 (2 settled, median −1.0R), COILED parent 1 (none settled). Q2 `coiled` 5 reads, 1 of 5 closed under the base low within 10
sessions (the retired era alone: 3 of 25; the page, over 444 sessions: 6 of 42, 14%). **Counts, not findings** — n is far too small to rank the paths; the buckets exist so the comparison can be read when it is.

## The post-breakout state — what a row says after the flag it was in breaks out (#697 item 4, 2026-10-16)

**The gap (htf_scope G3).** When a name CLOSES above the pole top of a formed flag, the next scan re-anchors the pivot on the breakout bar (`_find_pivot_high` + `_flag_resolved_by`), the base window restarts at zero, and the row reads a bare `base_age_0_below_3` — the board forgets the flag (CDNA 08-26, MRNA 09-23; 11 pushable ticker-days in 60). Two nullable columns on `mi_flag_candidates` now say which flag it broke out of and how long ago. **Telemetry: no stage, gate, threshold, hysteresis, M&A screen, universe path or order path reads them** (`flag_detector._post_breakout_state`, `post_breakout_label`; tests `tests/test_697_item4_post_breakout.py`).

| Column | Meaning |
|---|---|
| `post_breakout_from` (DATE) | the date of the OLD pivot / pole-high bar the name broke out of |
| `days_since_breakout` (INT) | trading sessions from the breakout bar to this scan; `1` = the first row after the breakout bar |

**The definition is a chart fact, not a stage test** — MRNA, the operator's top-rated example, was `unqualified` (flag depth on the low) on every night of its flag and still broke out of it on 2026-09-22, and the stamp must follow it:
- **the flag** = a pole top that is a pole by the detector's own runup gate (high ÷ lowest low of the 40 sessions ending at it ≥ `_RUNUP_MIN_RATIO`, measured exactly as the gate measures it) with at least `_BASE_AGE_MIN_WATCH` (3) sessions of base under it when the breakout bar printed — fewer is a pole still extending (`_flag_resolved_by`'s own line), not a flag;
- **the breakout bar** = the first bar from that point, strictly before today, that CLOSED above the pole top's high (a wick that closes back inside is not one — #592);
- **the re-anchor** = the pivot the finder chose today is a LATER bar than yesterday's carried pivot, and that old top is still inside the 25-session lookback. An old top that AGED OUT of the lookback is not a breakout (HNGE 08-18);
- **the count** is re-derived from the bars every night (`today − breakout bar`), so a skipped scan cannot drift it; the carried item is only the DATE (`db.get_flag_post_breakout_carry`, the ticker's last stored stamp within `_PIVOT_CARRY_DAYS`). A newer breakout replaces it (CDNA: 08-25 still cites the 07-16 flag, 08-26 cites the 08-03 flag). A carried claim the bars no longer support lapses to NULL;
- **the horizon** = `_PIVOT_LOOKBACK_DAYS` (25) sessions after the breakout bar; both columns go NULL together on day 26. The stamp only SHOWS while the ticker is still scanned: the universe carry (path (e), #697 item 2) holds a TIGHTENING-or-better name 25 sessions from its last such stored row, not from the breakout bar, so a pushable name keeps its rows for roughly that long and no longer; a name that never reached a pushable stage (MRNA) is scanned only while the organic universe holds it. A stamp that outlives a name's scanning is simply never written.

**Not set** on the breakout day's own row (the old flag is still the flag that day), on a row that returned before the pivot anchor (liquidity floor, no pivot), on rows written before 2026-10-16 (no backfill — NULL there means "not recorded", not "no breakout"), or on a name that never broke out of a flag (GH, HPE, NCI, SHAZ, ATAI: every replayed row NULL). `_demote_unqualified` leaves it alone: a chart fact survives an M&A demotion.

**Read it.** `/flags TICKER` appends it to those rows in plain words: `2026-09-23  unqualified  age —  tightness n/a · broke out of the 08-19 flag 1 session ago` (the count is sessions AFTER the breakout bar, so the first row after it says `1 session ago`; it never says "day 1", which reads as the breakout day itself; the breakout date is not stored, so the wording names only the flag's date; `flag_detector.post_breakout_label` is the one place it is built). One SELECT for "which names carry the stamp on the latest scan", i.e. broke out within the last 25 sessions and are still scanned (a name no longer scanned has no row on the latest scan and is not listed):
```sql
SELECT ticker, scan_date, stage, post_breakout_from, days_since_breakout
FROM mi_flag_candidates
WHERE scan_date = (SELECT max(scan_date) FROM mi_flag_candidates) AND post_breakout_from IS NOT NULL
ORDER BY days_since_breakout, ticker;
```
**Limits, stated.** (a) The count runs from the FIRST formed close above the old top. A name that poked above it, fell back inside the flag and only later printed the decisive new high reads the later count on the re-anchor row (PBF 2026-09-03: 13 sessions ago; REPL: 7; 5 of the 71 stamp episodes in the 62-name replay began on day 3 or later, 58 on day 1). **The stamp can then contradict the board's own history:** in the replay (`scripts/probes/_697_item4/replay_equiv.py`, the prod capture's PBF bars) PBF closed above its 07-30 top on 08-17 and 08-18, then fell back inside it and the board kept reading it as that flag (COILED 08-19 and 08-20, TIGHTENING or INVALIDATED on the sessions after) until the decisive high of 09-02 re-anchored the pivot; the 09-03 row then says it broke out of the 07-30 flag 13 sessions ago, while the last unbroken run of closes above the top began 09-01 (which would read 2). Not changed: that count has no stable anchor on the nights after the re-anchor (price that dips back under the old top and closes over it again would restart it) without storing the re-anchor date, the third column rejected below, and it would change the definition `verify_live.sql` re-derives independently. (b) A flag whose pole fails the runup gate is never stamped, whatever the name did — consistent with "the detector never recognised a pole". (c) A stamp says a name broke out of a flag; it is a STATE on a board, not a setup (CLAUDE.md SETUP vs FAMILY) and carries no buy point or stop.

## Known limitations / open questions (CHANGE_PROCESS rule 7 — the canonical surface)

Measured 2026-09-04 from raw bars over the stored candidate history (27,446 pairs, 06-29 → 09-04;
`docs/analysis/htf_pole_window_grid_2026-09-04.md`, harness `scripts/probes/_592_610_htf_grid_replay.py`).
Nothing below was changed; each is the operator's ruling and stays here until ruled.

1. **The pole definition vs the trader's HNGE label (#592, #610 — one fork, not two).** The sourced
   pole is 90%+ within **40 sessions**, measured at the pole top (signed 6/27–6/28). HNGE — a
   trader-labelled HTF the operator brought in — has a **10-week pole** (05-04 $45.01 → 07-13
   $91.50, +103% / 49 sessions); the spec's own scanner forms reject it on the trader's date
   (`C/C40` 1.14, `High40/Low40` 1.30 vs 1.90). Admitting HNGE-class poles means the 60-session
   window (board 10 → 19 names/day, +2 breakouts of which one −23%) or the full retired 1.50/60
   pair (board → 42/day, HNGE TRIGGERs on his date, the added breakouts' 20-day returns all negative
   on n=4). CDNA, the must-not-miss, needs neither. **Rec: keep the sourced 40-session pole; treat
   HNGE as outside the setup, not as a detector miss.** His call.
2. **The flag horizon.** `_BASE_AGE_MAX=25` / `_PIVOT_LOOKBACK_DAYS=25` encode the spec's 3–5-week
   flag. SNOW (+25% next 20 sessions) and TWLO (+21%) were dropped at week 5; HNGE's flag on the
   trader's date was in week 6. Widening it is a criteria change; not measured as a variant.
3. **`_HTF_MIN_ADR_PCT=0.04` — measured, immaterial under the sourced runup.** 4.0% → 3.0% admits
   **+3 tickers and 0 breakouts** in two months; the 7,560 ADR rejects (#610) almost all fail the
   90% pole anyway. It only matters if (1) loosens (+9 names/day at 1.50/60). The data-gated
   `htf_adr_threshold_tune` review stays as the eventual data-fit; nothing to decide today.
4. **The board's own outcomes are negative on median** (first-WATCH 20-day return −6.1%, 62% of
   admits down, against a flat tape) with 3 TRIGGERED events in two months. Context for #397, not
   a criterion question; recorded so the money gate is not built on an assumed edge.
5. `close_below_base_low_close` INVALIDATED re-arms as the base's lowest close creeps down, so a
   name can flip INVALIDATED → TIGHTENING (CDNA 07-22→07-29, then 07-30). Cosmetic; unfixed.
6. **Labelled corpus is N=11, pinned BY KIND** (`label_kind`, #697 item 6, 2026-10-11) — **htf** ×3 (CDNA — caught;
   HNGE-August and MRNA — declared known misses at `runup_` / `flag_low_`), **consolidation** ×2 (GH, HNGE-June — his
   06-27 family positives, NOT HTF labels; both stopped by the 90% pole floor on replay: 79% / 67%), **pointer** ×1
   (HPE 06-02, recorded and never scored), **negative** ×5 (NCI, ATAI, OUST, SHAZ, REPL). Every member a VERBATIM
   operator label, never an inference — `tests/fixtures/htf_labelled.py`, replayed every suite run through the
   shipped detector by `tests/test_htf_labelled_corpus.py::check_member`; the new kinds must quote his words and the
   quote is checked verbatim against the cited doc. The contract: an htf / consolidation member reaches TIGHTENING-or-
   better inside the 5 scan sessions before its date OR declares the gate that stops it (`known_miss_gate`) — and a
   declared miss the detector later catches FAILS, so a closed miss cannot stay on the books; a pointer / negative is
   never asserted as a hit (a negative the raw function scores actionable on an asserted date — ATAI — names the
   layer that closes it, `closed_by`; ATAI is not the only negative the raw function scores actionable — REPL
   replays TIGHTENING 09-01 / COILED 09-02, before his 09-04 sign-off, on dates the fixture does not assert; see
   `docs/analysis/htf_scope_2026-10-10.md` §2d). Only the `htf` kind enters a hit rate. The pre-trade window is
   anchored to the NYSE calendar — exactly the 5 sessions before the label — so a member whose label falls after
   the last bar in `htf_labelled_bars.psv` FAILS with "append bars through <date>" instead of being judged on an
   older window. `tests/test_697_corpus_label_kinds.py` proves the checker fails on deliberately wrong members, on
   a stale window and on a loosened pole floor. Every further trader-shared HTF is a one-line fixture addition
   plus its bars through the session before its label.
7. **The shipped breakout bet has no replayed edge (#610, 2026-09-10 —
   `docs/analysis/610_htf_replay_2026-09-10.md`, harness `scripts/probes/_610_htf_replay.py`).**
   The live chain (detector → next-session break → `prepare_htf_breakout_order` →
   `_htf_settle_from_bars`) replayed from raw bars 2021-09 → 2026-09 under the code at HEAD:
   **148 takeable first-breakouts settled, 25 captures (17%, breakeven 25%), mean +0.05R, median
   −1R; −0.09R once the 8 entries that opened above the order's limit are removed.** 2023: 0 of 20.
   The #396 management readout on the same entries is +0.74R mean / −0.16R median, 85% of it from
   five trades. #397's N≥10 exists offline; the edge it was meant to confirm does not, for the
   fixed +3R/−1R bet. Nothing changed; the fork is the operator's.

8. **THE TRADER-LABEL FORK IS NOT ONE FORK — $MRNA blocks on FLAG DEPTH, not the pole (added
   2026-09-17).** Item 1 above frames the whole trader-vs-spec question around the pole window,
   because HNGE was the only labelled example that reached it. **A second operator-shared HTF now
   says that framing is too narrow.** Leif Soreide called $MRNA a High Tight Flag on 2026-09-17
   (chart 09-16, before the move); transcript in `docs/methodology/operator_shared_notes.md
   § 2026-09-17`, member in `tests/fixtures/htf_labelled.py`.
   **`mi_flag_candidates` has MRNA on all 23 scan days 08-17 → 09-16 and rejects every one.** The
   pole is never reached: `runup_pct` = **2.4 (240%)** against the 90% floor. The block is **flag
   depth, the identical reason for 15 consecutive sessions (08-25 → 09-15):
   `flag_low_128.61_below_75%_of_pole_176.66`** — a **27.2%** retracement against our **25%**
   ceiling.
   🛑 **CORRECTED 2026-09-18 BY THE MEASUREMENT — I WROTE TWO THINGS HERE THAT ARE FALSE, and
   both were inferences from the trader's own words rather than from our bars.** Replay:
   `docs/analysis/610_htf_depth_and_sma20_margin_2026-09-18.md`.
   ❌ **"Mostly one stretch day", so a one-bar allowance is the difference.** IT IS NOT. **FOUR
   bars breach the floor** (08-20 low 128.61 = 72.8% of the pole, 08-21 132.42 = 75.0%, 08-24
   130.00 = 73.6%, 09-10 130.38 = 73.8%), and the **second**-lowest low is still **73.6%** — so
   dropping the single worst bar leaves MRNA rejected. A one-bar allowance could never have
   reached it. Measured over 88 scan days it admits 25 episodes whose outcomes are
   indistinguishable from the baseline's own, **1 extra breakout, 0 corpus flips.**
   ❌ **"Invalidated by five cents, retired one day early on a rounding error."** The 0.03% SMA20
   breach is real but was **not** what stood between MRNA and the board: on 09-16 the **MA stack
   was already broken by 1.30%** (sma10 143.78 < sma20 145.67), and on 09-17 — his breakout day —
   it still fails by **0.24%** (sma10 144.51 < sma20 144.86) under **all ten** variants tested.
   With an SMA20 margin applied, that same day simply reads `ma_stack_not_stage2`. Margins of
   0.1/0.25/0.5/1.0% keep 4/8/15/37 of 617 kills and add **0 breakouts at every margin**.
   ✅ **WHAT THE 26.2%-VS-27.2% GAP ACTUALLY IS — a DENOMINATOR, and this is the real finding.**
   His 26.2% is `128.61 / 174.38`, the pole-day **CLOSE**. Ours is `128.61 / 176.66`, the pole-day
   **HIGH**. Same low, different reference. And our gate reads the flag's extreme **LOW**, while
   the sourced spec's literal words are **`Close ≥ 0.75 × High`** — on which MRNA **passes at
   75.5%** (lowest close 133.32). **That is the mechanism, and it is neither of the two knobs I
   scoped.** [[prove-two-numbers-measure-the-same-thing]]
   ⚖ **SO THE OPEN QUESTION IS A METHODOLOGY REVERSAL, NOT A TUNE:** reading depth on the LOW is
   our **signed 2026-06-27 deviation** from the spec's literal close. Reverting it is a reversal
   of a signed decision → CHANGE_PROCESS rule 3 (say why the prior reasoning was *wrong*, not
   merely incomplete). Measured cost both ways: the spec-literal read puts MRNA COILED 08-28 →
   09-15, **but also admits OUST — which the operator labelled NOT-HTF** — and its 41 broad
   admits fall **harder** (57% down a month later vs 51%; MAE −24% vs −14%) with a slightly fatter
   tail (29% vs 21%).
   **So HNGE argues the pole window; MRNA does not reach that argument and does not reach mine
   either — it turns on how depth is measured. Tuning from HNGE alone tunes the wrong knob, and
   tuning from my first reading of MRNA would have tuned a knob that changes nothing.**
   ⛔ **NOTHING CHANGED.** Flag depth, the 75%-of-pole floor, the SMA20 stop and the MA stack are
   all admission criteria = the operator's sole authority. **Both knobs #610 asked for measure
   NULL and are NOT recommended.** What remains is his ruling on the fork below.

**#598 additions (2026-10-04) — surfaced, not decided:**
- ~~**A deal-pinned name at TIGHTENING can still push once.**~~ **CLOSED 2026-10-04 (#598, operator ok 2026-10-03):**
  the M&A screen (news nominates via `is_likely_ma`, the day-window own-day range <= 2.0% decides) and the Layer-2/3/3b
  price backstop now run on TIGHTENING as well as COILED/TRIGGERED, so a screened TIGHTENING name is `unqualified`
  with `mna_filter:<source>`, never on `/flags`, never in NEW TODAY.
- **INVALIDATED ↔ TIGHTENING flapping re-pushes each time.** Item 5 above (the base-low creep) means a name can
  bounce out and back; the rule pushes every genuine re-entry, as asked. If live data shows the same ticker
  pushing on consecutive days, the lever is a re-entry cool-off (a policy, not a bug fix) — measure first.

**#146 — TRIGGERED from TIGHTENING without COILED (parked by him 2026-07-12 behind the faithful harness; detection page 2026-10-11, #697 item 3; UNPARKED on his ruling 2026-10-11 and shipped — see the change log):**
`docs/analysis/146_detection_page_2026-10-11.md` — the shipped `compute_flag_metrics` replayed over raw bars for 444
sessions (2025-01-02 → 2026-10-09, 2,397 tickers, four arms differing in the one `recent_stages` conjunct). ESTABLISHED:
the shipped rule registered 42 TRIGGERED reads; letting a breakout register from a TIGHTENING-or-better label without
COILED turns them into 143 — +101 reads on 82 flags and 72 names the shipped rule never registered — and the added
breakouts closed back under the base low within 10 sessions as rarely as the shipped ones (14% of 99 vs 14% of 42). The
"above the base high at +10 sessions" check (55% vs 57%) separates nothing: breakouts with no tightening label hold 53%
(n = 351), so the evidence is "no harm seen", not "proven as good". Breakouts from WATCH fail under the base low 24%
(n = 351), 21% with base age matched (n = 157; the WATCH set's bases are younger, 6 vs 12): a lean, not a significant
gap. "From TIGHTENING" read on stored labels (held count) vs raw reads differs on 3 names (CDNA 08-25 among them, by a
held night on the 5-day window's edge); CDNA 07-31 registers under either, 09-17 under none (0.83× volume).
"TIGHTENING-or-better" includes re-triggers off an earlier TRIGGERED label (5 of the 101), and the replayed licence reads
the 5 days before the breakout, not the breakout day's own tightness (the shipped licence's same-day half; 24 of the 355
from-WATCH breakouts, an independent count). Detection only, no R; he parked it 07-12 behind the faithful harness, and
the harness then set the reopen condition (0031 structural stops) — a returns question the page cannot meet. **He ruled
on 2026-10-11 (verbatim in the change log) and the rule shipped on that branch.** Still open after it: (a) the breakout day's OWN
tightness is not a licence (page §9: 24 of the 355 from-WATCH breakouts read TIGHTENING the same day) — that half of #146 was not
asked for and is not added; (b) the page's population is wider than the live board (about 1 extra breakout per 4–5 sessions across
all 2,397 names, 5 of the 10 extras in the 60-session scope window on the live board); (c) (closed by the review, same day) the Friday watchlist now lists TRIGGERED names with their path.

## Change log
- **2026-10-18 — #704: the HTF breakout-shadow settler reads the splits ingest's recorded verdict (`db.stored_price_scale`) instead of "any `mi_splits` row after the break day is unbookable". SHADOW TELEMETRY ONLY: no detection criterion, stage, threshold, entry or exit rule moved; `prepare_htf_breakout_order` is untouched; no money path.**
  **Trigger**: the 10-17 /simplify altitude review — three consumers answered "did this split move the stored bars?" three ways; this one counted EVERY row, phantoms included, while the Consolidation Breakout entry step and the parabolic-short shadow ignored a phantom. His "Aligned, let's do these tmr" 10-17.
  **What** (`scheduler._htf_breakout_settle_job` GUARD 1, `db.get_split_dates_after`): the guard asks `stored_price_scale(ticker, break_date, today)` — the product of the factors the ingest restated the bars by over the window (break_date, today]. `1.0` (no split, or only splits the ingest recorded as PHANTOM, which wrote no bar because there was no split) → settle as usual. A `skipped_no_data` split is NOT a phantom: the ingest wrote no bar, but that is also what a FAILED Polygon fetch of a real split records, so it reads at the table ratio and voids as before #704. `None` (a split executed and the 17:00 pull has not handled it) → the row WAITS for the next run: marking it unbookable would be permanent and wrong if the ingest then records a phantom - but not for ever: 30 days after the split executed (`scheduler.HTF_SPLIT_UNRESOLVED_DAYS`) it is marked `unbookable` with reason `split_unresolved_<from>:<to>_on_<date>_<n>d_unapplied`, and the job's log line counts the rows still waiting. Anything else → `unbookable`, as before, with the same `split_{from}:{to}_on_{date}_between_break_and_settle` reason (the first split that moved a bar). Back-fill: an outcome-NULL row that is applied reads as a real split at the table's ratio, i.e. exactly the old behaviour for every row written before the column.
  **Two named behaviour changes**: (1) a recorded phantom no longer voids a row for good; (2) the window now has an UPPER bound (today) — the old unbounded `execution_date > break_date` also voided on an ANNOUNCED split that had not executed, which has changed no stored price.
  **Evidence**: tests in `tests/test_667_unbookable_htf_fills.py` — a real forward and a real reverse split (recorded) and a legacy forward row all still void with the bars never fetched; a phantom settles; an unapplied split defers (neither marked nor settled); an announced future split changes nothing; a phantom beside a real split names the real one. The reading itself: `tests/test_stored_price_scale.py`, and against a real Postgres `tests/test_cb_shadow_pg.py`.
  **Reversion-flag**: NEW; not a detection-criterion change (CHANGE_PROCESS "When NOT to log" — logged because the settler's bookable/unbookable line moved). **Removing it**: restore the one-line `get_split_dates_after` guard; the columns stay.
  **Status**: built on a worktree branch, not deployed. EXPECT / DONE-WHEN / WOULD-FAIL-IF: CHANGELOG 2026-10-18 (#704).
- **2026-10-16 — #697 item 4 (htf_scope G3): the board remembers a flag the night it breaks out — `post_breakout_from` + `days_since_breakout` on `mi_flag_candidates`. RULE UNCHANGED, TELEMETRY ONLY: no stage, threshold, window, floor, admission, hysteresis, TRIGGERED licence or universe-carry rule moved; the flag strategy stays disabled; no order / entry / sizing / safeguard path reads either column (THE LINE holds). Detection only.**
  Branch `worktree-wf_529414ed-ea0-1` (on `main` at `f06371f4`), not yet deployed. Rule + owner: "The post-breakout state" above; code `flag_detector._post_breakout_state` / `_flag_breakout_idx` / `post_breakout_label`, `db.get_flag_post_breakout_carry`, the two columns in `db.initialize_schema` + `insert_flag_candidate`; display `agent._handle_flag_query` (`/flags TICKER`). Mirror: `flag_continuation.md` change log.
  **Trigger**: `docs/analysis/htf_scope_2026-10-10.md` G3 / §6 item 4 — the night after a pushable name closes above its pole the pivot re-anchors and the row reads `base_age_0`; 11 ticker-days in 60 (CDNA 07-31 and 08-25, CHPT 09-18, EFOR 10-01, HELP 08-04, IOVA 09-16, PBF 09-02, QMCO 09-23, REPL 09-02, TJGC 09-11, XHLD 09-09) plus MRNA 09-23, his top-rated example, which was never pushable at all.
  **What**: (1) `compute_flag_metrics` takes `prior_post_breakout` (the ticker's last stored stamp) and, right after the pivot anchor and before the `base_age_N_below_3` return, sets the two keys from `_post_breakout_state` — wrapped so a bar it cannot read leaves both NULL and never costs the ticker its row. (2) `run_flag_scan` reads the carry in the same `asyncio.gather` as the other state (`get_flag_post_breakout_carry`, fails open to `{}`). (3) Two nullable columns, `ADD COLUMN IF NOT EXISTS`, no backfill. (4) `/flags TICKER` words it. **Not changed**: every field of every other row — proven below.
  **Evidence** (n stated; nothing here is a threshold, so no backtest gate applies — the evidence is that nothing else moved and that the stamp is right): (a) **NO STAGE RULE MOVED** — the SHIPPED `compute_flag_metrics` replayed over every committed bar set (the 10 labelled-corpus tickers and the 62-ticker prod capture `scripts/probes/_697/q6_extra_bars.out`, state threaded the way `run_flag_scan` threads it, 7,586 ticker-days 2026-05-04 → 10-09) on `main` BEFORE and on this branch AFTER, every field except the two new keys dumped: **byte-identical, 7,586 of 7,586 rows** (`scripts/probes/_697_item4/replay_equiv.py`, result in `equiv_result.out`); in-suite the same property is `test_switching_the_stamp_off_changes_nothing_else_…` (886 corpus rows incl. MRNA's extension, stamp on vs off), plus the 347 existing #697 / #146 / #610 / #598 / #354 / #592 / htf tests green before and after (the one edit: test_610's INSERT parameter-count pin, 41 → 43) and the full suite green (11,133 passed before, 11,160 after = +27 new tests, 10 skipped both). (b) **The stamp is right** — `scripts/probes/_697_item4/verify_live.sql`, an INDEPENDENT re-derivation of the stamp from bars in SQL, run in DuckDB over the 6,346 pivot-anchored replay rows (every replay session after the first; 748 + 5,651 reach the pivot in all): agrees with the detector on all of them (5,080 NULL, 1,266 stamped) and flags each of four deliberate corruptions under the right verdict (`dryrun_verify_sql.py`). (c) **The G3 population**: 9 of the 11 ticker-days replay (IOVA and QMCO have no bars in any committed capture) — each one's next row is the stored `base_age_0` row and now carries the stamp, on day 1 for CDNA ×2, CHPT, EFOR, HELP, XHLD, day 2 for TJGC, day 7 for REPL, day 13 for PBF (the delayed re-anchors, limit (a) in the section). (d) **MRNA** (his top rating): 09-22 close $182.56 over the 08-19 pole top's high $176.66 (prod stored the 09-23 row as `base_age_0_below_3`, pivot 09-22 $187.20 — the replay reproduces it); 09-23 → 10-09 are 13 rows, all `post_breakout_from = 2026-08-19`, `days_since_breakout` 1 … 13, stage `unqualified` → `WATCH` → `INVALIDATED` → `WATCH` (the stamp ignores stage, by design). CDNA 08-26 reads `broke out of the 08-03 flag 1 session ago`; its 08-20 → 08-25 rows still cite the 07-16 flag (the 07-31 breakout). (e) **Negative controls**: GH, HPE, NCI, SHAZ, ATAI — every replayed row NULL; HNGE 08-18 (the 07-13 top aged out of the lookback) NULL; HNGE June stamps day 1 on 06-16 and lapses to NULL on day 26 (07-23). (f) Rate: the 62-name capture, 111 sessions, 71 stamp episodes on 36 names (58 first-stamped on day 1, 8 on day 2, 5 later).
  **Anticipated effect**: no change to any stage, alert, digest, Friday list or `/flags` board; `/flags TICKER` rows in the 25 sessions after a breakout out of a pole-grade flag gain `· broke out of the MM-DD flag N sessions ago`; ~0.6 new stamp episodes a night on flag-heavy names (see EXPECT for the live rate).
  **Reversion-flag**: NEW (no prior change to this logic); not a detection-criterion change (CHANGE_PROCESS "When NOT to log" — logged here because the operator asked for it). **Removing it**: make `_post_breakout_state` return `(None, None)` — one line, every other field unchanged (tested); the columns stay, NULL.
  **Rejected variants**: gating the stamp on a pushable stored stage (MRNA was never pushable — it would not be stamped); incrementing yesterday's count (a skipped scan drifts it; re-deriving from bars cannot); counting from the re-anchor scan instead of the breakout bar (needs the re-anchor date stored — a third column); folding the date into `get_yesterday_flag_pivots` (changes a tuple `test_592` pins, and a transient NULL on the one row it reads would lose the stamp for good — the separate reader takes the latest row that HAS one and the bars re-validate it); clearing the stamp on an M&A demotion (it is a chart fact).
  **Status**: shipped on the branch, awaiting deploy and field validation.
  **Review fixes (same day, branch `worktree-wf_529414ed-ea0-1`; display, docs and a sweep registration — no detector rule moved)**: (1) the nightly dead-column sweep (17:30 ET, `health_checks.run_dead_column_sweep`) would have sent a false 'DEAD COLUMNS' page for `mi_flag_candidates.days_since_breakout` (an INT, NULL on every row until the first breakout) after two scans with no stamp — 41 of 110 back-to-back two-scan windows in the 62-name capture replay (`replay_equiv.py`) had no new stamp, so about one first deploy in three — and the sweep announces a column once ever, so the false page would have spent the one real alarm; the column is now registered in `_DEAD_COL_EVENT_GATED` (the #695 `mark_r` pattern, event = `post_breakout_from IS NOT NULL`), listed in EXPECT (v) and WOULD-FAIL-IF; `post_breakout_from` is a DATE and was never swept; (2) `/flags TICKER` says `broke out of the 08-19 flag 1 session ago` — "day 1" read one session early; (3) the horizon bullet no longer says path (e) keeps rows for as long as the stamp does, and the "which names carry the stamp" SELECT now reads the latest scan (the 40-calendar-day filter returned a lapsed stamp and a breakout up to about 75 calendar days old); (4) limit (a) states what the board itself read in between (PBF) and why the count is not changed; (5) scope item 4 said "when a PUSHABLE name closes above its pole" — the build stamps any pole that passes the 90% runup gate whatever the stage (MRNA was never pushable; rejected variants below), telemetry only. Deploy scope unchanged (`health_checks.py` is market-agent only). Tests: `tests/test_697_item4_post_breakout.py` § 7–9.
  **EXPECT** (BASELINE: neither column exists; ~540 rows a scan; WATCH ~5 / TIGHTENING ~1 / COILED ~0 a scan, `htf_scope` §3. Read from the first scan after deploy `d0`: `psql "$DATABASE_URL" -v d0=<date> -v since=2025-08-01 -f scripts/probes/_697_item4/verify_live.sql`): (i) statement 1: the scan writes its usual ~540 rows and statement 3 prints 0 (both columns set together, 1–25, from-date before the scan); (ii) statement 2: zero `VIOLATION_*` rows AND, once any ticker re-anchors off a formed flag's pole top, `ok_stamped` ≥ 1 — the stored pair equals the SQL's independent re-derivation in both directions; (iii) rate: ~1–6 day-1 rows a scan, alarm above 25 in one scan (an over-firing flood) — a quiet scan with none is normal (replay: ~0.6 episodes a night on 62 flag-heavy names; the 11 pushable G3 ticker-days alone are ~0.2 a night), so zero in one scan proves nothing; (iv) the carry: a ticker stamped on one scan is stamped on the next (same from-date, days +1) until day 25 — statement 2's `carry` claims; (v) UNINTENDED, all display or cost: the stage mix of the first nights is unchanged (no path to move it); the digest, Friday list and `/flags` board are unchanged; `get_flag_candidates_window` rows (`SELECT *`) carry two more keys; one more indexed read per scan; `/flags TICKER` lines are longer on stamped rows only; the 17:30 ET dead-column sweep's `N event-gated` log count is one higher (`mi_flag_candidates.days_since_breakout`, registered in `health_checks._DEAD_COL_EVENT_GATED`) until the first stamp is written, and it raises no page and writes no audit row on a night with no stamp on the table.
  **WOULD-FAIL-IF** (positive; each prints from `verify_live.sql`): statement 2 prints `VIOLATION_missing_stamp` (the bars show a breakout re-anchor the detector did not stamp — the event or carry path is dead), `VIOLATION_unsupported_stamp` (a stamp with no breakout behind it — over-firing) or `VIOLATION_wrong_value` (wrong from-date or count); statement 3 prints ≥ 1; statement 1 shows a scan with ~0 rows or the 17:25 log shows `flag_scan: <ticker> failed` for many names (the INSERT names columns the table lacks — the deploy-order failure, the one risk that can cost the board a night); a stamped ticker with no stamp on its next scan while its `days_since_breakout` was under 25; **a `dead_column_suspect` or `dead_column_detected` row in `mi_audit_log` whose summary starts `mi_flag_candidates.days_since_breakout`** (`SELECT created_at, event_type, summary FROM mi_audit_log WHERE event_type IN ('dead_column_suspect','dead_column_detected') AND summary LIKE 'mi_flag_candidates.days_since_breakout%'`): the bare key means the exemption is missing from the running image, `@event_live` means a row carries `post_breakout_from` while `days_since_breakout` is still NULL on every row — the writer set one column and not the other.
  **DONE-WHEN**: three scans pass statements 1 and 3 with zero violations in statement 2 AND at least one `ok_stamped` row with `days_since_breakout = 1` has been seen (a first re-anchor off a formed flag). If none appears in 10 scan sessions that is inconclusive, not a pass — extend to 20 (at ~0.2 a night the chance of none in 20 is ~2%, then look at the wiring); stop watching once it has passed. The offline replay and SQL cross-check already cover correctness; the live scans cover wiring, schema and rate.
  **Deploy scope**: `agents/market_intelligence/db.py` and `agent.py` are on `scripts/exec_loaded_modules.txt`, `flag_detector.py` is market-agent only → `bash scripts/deploy.sh execution` and `bash scripts/deploy.sh market-agent` (each scope builds and recreates its own service, so either order works; weekend, unrestricted, or 12:00–13:00 / 21:15–22:15 ET), both BEFORE the 17:25 ET scan so the columns exist when the first stamped INSERT runs (the schema step is idempotent and runs on whichever container boots first). Saturday/Sunday 10-17/18 → `d0` = Monday 2026-10-19.
- **2026-10-15 — #697 item 6: MRNA's corpus entry now records his two entry days, the THIRD blocking gate and his TOP rating — TEST FIXTURE ONLY, no detector, threshold or surfacing change.**
  From his 10-15 note (`operator_shared_notes.md` § "2026-10-15 — MRNA: the post-EP consolidation and his two entries"). `tests/fixtures/htf_labelled.py` gains
  four optional, default-empty fields — `trader_entries` (09-16 anticipation buy on the tight inside day; 09-17 ORB breakout entry: two SETUPS in the post-EP
  consolidation family, each with its own name, his words checked verbatim), `gates_recorded` (the board's reading per day: 09-15 `flag_low_`, 09-16 SMA20 kill,
  **09-17 `ma_stack_not_stage2_144.5/144.9/96.6`**, 09-18 `ma_stack_not_stage2_145.0/145.9/98.2`), `rating` / `rating_quote` (`top`: "a really good setup per my
  estimation"). The days the bars reach are REPLAYED (the replay reproduces 09-17 exactly), so a detector change that moves a gate fails the suite; 09-18 is a prod
  row (bars end 09-17) pinned as text. Pins + bite cases: `tests/test_697_corpus_label_kinds.py` § 2b. The member stays `htf` / declared `flag_low_` miss; the rating is a
  lean about the label, not a score input or filter. No criterion reopened — three gates on three days (depth, a 5-cent SMA20 kill, MA-stack order) is a recorded
  verdict, and the admit-or-not fork stays the operator's.
- **2026-10-11 — #146 UNPARKED: a breakout reads TRIGGERED from a TIGHTENING-or-better label without first reaching COILED, and every raw TRIGGERED row now says which
  path licensed it (`triggered_from`: `coiled` / `tightening` / `retrigger`). DETECTION only — no threshold, window, floor or volume leg moved; the flag strategy
  stays disabled and HTF trading stays parked behind EP (#397); no order / entry / sizing / safeguard path reads a stage or the stamp (THE LINE holds).**
  Branch `wk1011/146-unpark` (on `main` at `7694efff`), not yet deployed. Rule + owner: this file ("TRIGGERED licence" row, "Bucket the TRIGGERED reads");
  code `flag_detector._TRIGGER_LICENCE` / `trigger_licence`; stamp `db.insert_flag_candidate`. Mirror: `flag_continuation.md` (stage progression + change log).
  **Trigger**: #146 (filed 2026-05-28: *"direct TIGHTENING→TRIGGERED on close > base_high_close + vol should be allowed"*, needing an N≥10 cohort); the 07-12 sitting
  parked it (*"B2 0026-D2: PARKED"*, behind the faithful harness); the detection page (`docs/analysis/146_detection_page_2026-10-11.md`, #697 item 3) supplied the cohort
  (n = 101) and put the decision to him as D1.
  **His sign-off (verbatim, 2026-10-11)**: *"The reason I want to add it is so that we can track performance from each and if we get too many breakouts we can discern
  where they come from. This is not important right now. If and when we move this to paper trade or real trade this will become useful. Now you can proceed to end
  park."* — the reason is the SEPARATION of the paths (hence the stamp), not a claim that the new path pays.
  **What**: (1) `compute_flag_metrics` reads TRIGGERED when `breakout_now` and `trigger_licence(coiled_today, recent_stages)` is not None — the licence is COILED today
  or ANY of COILED / TIGHTENING / TRIGGERED among the stored labels of the last 5 calendar days (`_COILED_LOOKBACK_DAYS`, `db.get_recent_flag_stages`), held labels counting.
  That is exactly arm B of the page. Membership in the window, not "yesterday": 9 of the page's 101 extras had a TIGHTENING 2–4 sessions back followed by WATCH / INVALIDATED days.
  (2) The bucket: `coiled` (COILED today or a COILED label in the window — the shipped path), else `tightening`, else `retrigger`; written to the NEW column
  `mi_flag_candidates.triggered_from` on a raw TRIGGERED read only (NULL on a hold — nothing licensed it today — and on a row the M&A / deal-pin layer demotes to
  `unqualified`). Schema: declared in CREATE TABLE and an idempotent ALTER; one guarded step adds the column on an existing table AND labels the already-stored raw
  TRIGGERED rows `coiled` (all licensed by the shipped path), exactly once. (3) Display: the 17:25 digest, `/flags`, `/flags TICKER`, `/watch`, `/setup TICKER` and the Friday watchlist name the path ("Surfacing" and the Friday section above).
  (4) Tracking: "Bucket the TRIGGERED reads" above — three SELECTs and how `parent_stage` relates. **Not changed**: the 1.5× volume leg, the close-over-the-base's-highest-close
  leg, pole / depth / floors, the hysteresis, the universe, the intraday scans. **Changed beyond the rule, display only (review, same day)**: the Friday watchlist now also LISTS TRIGGERED names (see its section) —
  without that, #146 took breaking-out names off the list on the night they broke out.
  **Evidence** (n stated; "no harm seen", NOT "proven good" — the page's own wording): over 444 sessions the rule turns 42 TRIGGERED reads into 143 — +101 reads on 82 flags
  and 72 names the shipped rule never registered; the added breakouts closed under the base low within 10 sessions as rarely as the shipped ones (14% of 99 vs 14% of 42);
  the "held at +10" column separates nothing (55% vs 57%; breakouts with no tightening label at all hold 53%, n = 351). Breakouts from WATCH fail under the base low 21% (n = 157,
  base-age-matched) — a lean, not a gap. THIS CHANGE, replayed on prod's own stored rows (`scripts/probes/_146_unpark/replay_stored_146.py`, the REAL `compute_flag_metrics`
  run twice on identical inputs threaded from the stored labels): the shipped-rule run reproduces prod's stored stage + raw read on **4,465 of 4,465** rows (scan dates
  09-29 → 10-09); a positive control on the 4 names that carry every stored raw TRIGGERED read since 08-14 (CHYM, WDAY, XHLD, IOVA) reproduces **4 of 4** (the 15 rows that differ
  are the pre-10-11 re-arming hold, 14, and the pre-09-08 anchor, 1 — both older code, neither the licence); the new licence adds exactly **2** raw TRIGGERED reads in the 9 sessions —
  **EFOR 2026-10-01** (2.48× volume, stored window TIGHTENING ×3) and **HTFL 2026-10-05** (1.96×, stored window TIGHTENING, INVALIDATED, TIGHTENING), both bucket `tightening`, the same two
  the page found in that window from raw bars — and changes no other field of any row (0 unexpected differences). Both gains are also intraday breaks already in the shadow with a TIGHTENING parent
  (`q4_agree.out`: EFOR 10-01 id 23, HTFL 10-05 id 25), so Q1 would have moved those two rows from `no EOD TRIGGERED read / TIGHTENING` to `tightening / TIGHTENING` — the two tables describing the same events. Day-one SELECT dry-runs on prod with the column simulated: `q8_ssot_selects_dryrun.out` (Q0–Q2 exactly as written in this file) and `verify_live_dryrun.out` (all 30 stored raw reads judged `ok`, 27 of 27 shadow parents match).
  **Anticipated effect**: stored baseline = 4 raw TRIGGERED reads in the last 60 scan dates (`q2_baseline.out`: CHYM 08-19, WDAY 08-28, XHLD 09-09, IOVA 09-14). The page's 60-session
  window (07-17 → 10-09) reads 14 instead of 4 on its wider population; on the live board 5 of the 10 extras would have registered (CDNA 07-31 and 08-25, CHPT 09-18, EFOR 10-01, HTFL 10-05
  — page §3), i.e. roughly one extra raw read per 12 sessions live, up to the page's whole-population rate of one per 4–5. The 17:25 digest therefore carries a TRIGGERED section on
  more nights; each line says which path.
  **Reversion-flag**: NEW — the first change to this logic; it ENDS the 07-12 park, it does not reverse a shipped change. Why the park no longer binds: it rested on R (the
  incumbent gate read +0.78R and the harness that would justify a change was 4/21-faithful) and the harness's own reopen condition was stop geometry (0031) — questions about RETURNS.
  His ruling gives a different reason (separate the paths so returns can be read per path later) and the stamp is what makes that read possible. **To revert: set
  `_TRIGGER_LICENCE = (("COILED", "coiled"),)` in `flag_detector.py` — one line, restores the shipped rule bit for bit (tested), keeps the stamp, and the same-day COILED half is
  never behind it. Already-stored `tightening` / `retrigger` rows stay and keep their labels.**
  **Review fixes (same day, branch `wk1011/146-unpark-fix`; display + checks only — `_TRIGGER_LICENCE`, every threshold and the stamp are untouched)**: (1) BLOCKING — the Friday watchlist now lists TRIGGERED names (they were
  leaving the list the night they broke out; "Friday watchlist" section above); (2) the TRIGGERED line no longer says `close $X above $base_high` — it names the base's highest close, the level the gate tests ("The close level"
  above); (3) `verify_live.sql` statement 4 is now a bucket-vs-parent check over both tracking tables, plus `verify_deploy.sh` for the running image — the old statement 4 could not read differently on a broken gate;
  (4) the day-one baseline is split by rule era (5 post-rebuild reads, 25 retired-rule); (5) `/watch`, `/setup TICKER` and the header's `N held` carry the path / the holds.
  **Status**: shipped on the branch, awaiting deploy and field validation.
  **Known limitations**: (a) the breakout day's OWN tightness is not a licence — page §9, the same-day TIGHTENING half (24 of the 355 from-WATCH breakouts) is NOT added; (b) it reads
  STORED labels, so a name absent from the universe on the days before its breakout has an emptier window live than on the page (HELP 08-04: on the board, no stored TIGHTENING-or-better row
  in the prior 5 days); (c) stored labels before 10-11 are the old re-arming-hold kind — the licence window reads what was stored; (d) the page's population is wider than the board (about 1 extra
  per 4–5 sessions across all names; roughly 1 per 12 on the live board); (e) NOTHING here measures returns — a TRIGGERED label is a state on a board, not a setup (CLAUDE.md SETUP vs FAMILY);
  (f) the Friday watchlist lists at most 3 TRIGGERED names (a night with more drops the rest), and it reads the LATEST scan only — a Monday-to-Thursday breakout that is no longer TRIGGERED
  by Friday's scan is not on that Friday's list (it never was; the digest and `/flags` carry it on the night).
  **EXPECT** (baseline above; read from the first scan after deploy, `d0`; `scripts/probes/_146_unpark/verify_live.sql -v d0=<date>`): (i) **every** raw TRIGGERED row from `d0` carries a non-NULL
  `triggered_from` and no hold, no `INVALIDATED` and no `unqualified` row does (statement 1) — checkable on the very first TRIGGERED night through ANY path; (ii) within the first 20 scan
  sessions at least one `tightening` or `retrigger` row appears, and statement 2 (each raw read judged against its OWN stored 5-day window) prints `ok` for it — expected 2 to 5 at the
  rates above (zero has a chance of about 19% at the live-board rate of one per 12 and about 1% at the whole-population rate of one per 4.4 — hence the stop rule below); (iii) the shipped path is not suppressed — the replay's 4-of-4 positive control
  is the proof offline; live, a `coiled` row arrives at its own ~4-per-60 pace, so its absence in 20 sessions proves nothing either way; (iv) UNINTENDED, all display or telemetry: (a) more
  stored TRIGGERED rows keep a name in the universe carry for 25 sessions (#697 item 2) and in the intraday watchlist (`TIGHTENING / COILED / TRIGGERED` parents), so a few shadow rows move from
  parent TIGHTENING to parent TRIGGERED in the `/flags` footer split; (b) the 17:25 digest is sent on more nights (a TRIGGERED section alone un-suppresses it); (c) the BREAKOUT CONVERGENCE tag on EP
  alerts (`db.check_sugar_baby_convergence`, display + audit row) reads a stored TRIGGERED row within 5 days — more `breakout` tags; (d) the deprecated `flag_continuation` outcome adapter counts more
  `closed` rows (no R, strategy disabled); (e) the monthly #92 graduation evidence's TRIGGERED cohort is now a mix of paths — split it by `triggered_from` before reading it;
  (f) **the Friday watchlist**: a TIGHTENING name that breaks out on a Friday now stays listed, as `TRIGGERED · from TIGHTENING` (CDNA 07-31 class) instead of leaving the list — `mi_weekly_watchlists` stores the chip
  (`reason_chip`), so that Friday's board shows the name with `sources ? 'FLAG'` and a chip containing `[TRIGGERED · from …`; the one SELECT is `scripts/probes/_146_unpark/verify_friday.sql` (a Friday whose latest scan
  holds no TRIGGERED name is inconclusive, not a pass — the proof is a TRIGGERED candidate row on the board whose chip says so, and a board name that IS TRIGGERED on the list's scan date without that chip prints VIOLATION). **Baseline** (`verify_friday_dryrun.out`, prod, the nine Fridays 06-05 → 07-31 that carried a flag section): **0 TRIGGERED names on any board,
  while the Friday scan itself held 1, 2 and 1 TRIGGERED names on 06-05, 06-19 and 07-03** — the old query could not list them; CDNA 07-31 sat on the board as a held TIGHTENING. The flag section can now hold up to 11 names (3 + 5 + 3) and displace more of the lowest-priority ambient RS rows when the 25-ticker cap binds;
  (g) **#354 failure telemetry starts on the new-path flags**: `failed_at` / `low_after_breakout` / `undercut_after_breakout` are anchored on `breakout_close` (`db.get_flag_failure_carry`), so a flag that
  reads TRIGGERED through a TIGHTENING label now begins accumulating them — telemetry only, nothing gates on it; (h) `/watch`, `/setup TICKER` and the digest/`/flags` header carry the path and the `N held` count.
  **WOULD-FAIL-IF** (positive; every one prints from `verify_live.sql`): statement 2 prints any `VIOLATION` — a raw TRIGGERED read with a NULL stamp; a `tightening` row with a COILED label in its own
  window (precedence wrong) or with no TIGHTENING label (the gate widened to WATCH / INVALIDATED); a `retrigger` row with a COILED or TIGHTENING label in its window or none TRIGGERED; a stamped hold; a stamp on a
  non-TRIGGERED row; or statement 4 / 4b prints a `VIOLATION` — in `mi_flag_breaks` or `mi_htf_breakout_shadow`, a COILED parent whose break-date raw TRIGGERED row is stamped anything but `coiled`, a TIGHTENING
  parent stamped `retrigger`, or a `parent_stage` that no longer equals the candidate row it points at (that last one is a triage item, not a reason to revert: it is the intraday scan's copy drifting, which #146 never touches); **or `verify_friday.sql` F1 prints a `VIOLATION`** (a name TRIGGERED on the Friday list's scan date whose board chip does not say `TRIGGERED`, names the wrong path, or hides a hold); **or `verify_deploy.sh` prints FAIL** (the running image does not carry `_TRIGGER_LICENCE` with 3 entries — a stale image writes the
  old rule's unstamped rows and every SQL check then reads as a quiet day). A zero-row day is NOT a pass (statement 1 can be empty) — the proof is a row judged `ok` against its own window. **The checks were shown to be able to fail**:
  the same SQL on prod with the stamp deliberately wrong (`retrigger` on every raw TRIGGERED row) prints 30 statement-2 and 16 statement-4 `VIOLATION`s (`verify_live_dryrun_wrongstamp.out`), and `verify_deploy.sh` FAILs on the pre-change code
  (`verify_deploy_selftest_stale.out`) and PASSes on this branch (`verify_deploy_selftest.out`). Statement 4's n is small (a break needs a raw TRIGGERED EOD read the same evening: 15 of 178 `mi_flag_breaks` rows and 3 of 27 shadow rows on the day-one read). Statement 2 CANNOT discriminate a `coiled` row whose window holds no COILED label (it prints `ok (COILED the same day)` whatever the stamp): for the shipped path the proof is the offline replay's 4-of-4 control plus the code path, and the live check bites on the `tightening` / `retrigger` rows.
  **DONE-WHEN**: (i) the first raw TRIGGERED row after `d0` is stamped and `ok`, AND (ii) the first non-`coiled` row is `ok` with its window cited in the close note, AND (iii) `verify_deploy.sh` PASSed right after the deploy AND statement 4b reads `violations = 0` with `judged_ok >= 1` summed over the two tables (a check that judges nothing is a blank, not a pass; the day-one
  read judged 18 breaks in about 100 scan sessions, so a handful are expected in 20), AND (iv) the first Friday after the deploy whose latest scan holds a TRIGGERED name shows it on the board with `verify_friday.sql` F1 reading `ok`
  (a Friday with none is inconclusive; baseline: 3 of the 9 flagged Fridays 06-05 → 07-31 had a TRIGGERED name in their scan). If no `tightening` / `retrigger` row exists by scan session 20 (**2026-11-06** if `d0` = 2026-10-12), tell the operator the rule was never exercised by live data —
  do not close on silence; the same applies to (iii) if no break has had a same-evening raw TRIGGERED read by then, and to (iv) if no Friday through 2026-11-06 had a TRIGGERED name in its scan.
  **Deploy scope** (derive: `scripts/exec_loaded_modules.txt` lines 10 and 46): `db.py` and `agent.py` are execution-loaded, `flag_detector.py` is market-agent only. The flag scan is INTELLIGENCE-owned
  (`flag_continuation_scan`), so `bash scripts/deploy.sh market-agent` carries the behaviour and `bash scripts/deploy.sh execution` is drift hygiene so the running execution container's `db.py` / `agent.py`
  match the repo — **sequentially: market-agent first, execution after it has booted** (the new column and its one-time label are added by whichever container runs `initialize_schema` first;
  guarded, idempotent, and if two ever boot together the loser's whole block rolls back on `duplicate_column`, so the label is still written exactly once). No orchestrator change (the Friday job is INTELLIGENCE-owned, `friday_watchlist` — market-agent). Weekends are unrestricted. Read the delta
  first (a deploy ships the BRANCH): diff the running image against `origin/main` before deploying. **Right after the market-agent deploy and BEFORE `verify_live.sql`: `bash scripts/probes/_146_unpark/verify_deploy.sh`**
  (`docker exec apollo-market python -c 'from agents.market_intelligence import flag_detector as f; print(len(f._TRIGGER_LICENCE))'` must print 3; the script asserts the whole tuple and exits 1 on a stale image).
- **2026-10-11 — #697 item 6: corpus mechanics — TEST FIXTURE ONLY, no detector, threshold or surfacing change.**
  `tests/fixtures/htf_labelled.py` gains `label_kind` (htf / consolidation / pointer / negative) and the suite asserts by
  kind (known limitation 6). Added GH 06-27 and HNGE 06-27 as CONSOLIDATION members and HPE 06-02 as a POINTER, from his own
  words in `operator_shared_notes.md`, bars pulled from `mi_daily_closes` 2026-10-11. First replay of the June examples
  through the shipped detector (the scope doc had them by inspection): GH `runup_79%` every session 06-03 → 06-24; HNGE-June
  `runup_67%` 06-23 → 06-25 (WATCH at 92% on an earlier pivot 06-11 → 06-15); HPE `base_age_0` on the gap day. Both June
  examples are stopped by the sourced 90% pole floor (Detection criteria above) — a recorded verdict, no criterion reopened.
  Review fix, same day: the pre-trade window is now anchored to the NYSE calendar (a label past the last bar fails with
  "append bars through <date>" rather than being judged on an older window) — still test-only.
- **2026-10-11 — #697 item 5: the hysteresis holds a downgrade ONE night, as documented — a hold is never followed by a
  hold. A BUG FIX (the code held it night after night); no threshold, window, floor or stage rule moved, the flag strategy
  stays disabled, and no order / entry / sizing / safeguard path reads a stage. The per-night reading of WATCH / TIGHTENING /
  COILED is history-free and unchanged; TRIGGERED's "COILED in the last 5 days" reads the STORED labels, so a held COILED
  now licenses a breakout for one night instead of indefinitely (UNINTENDED (d)).** Branch
  `wk1011/697-item-5` (on `wk1011/697-items-1-2-fix`), not yet deployed. Rule + owner: `flag_continuation.md` "Hysteresis";
  code `flag_detector.stage_after_hold` + `db.get_yesterday_flag_state`.
  **What**: `compute_flag_metrics` gains `yesterday_was_held`; a downgrade against yesterday's STORED stage is held only
  when yesterday's stored row was NOT itself a hold (`held_from_stage IS NULL`); the next night the detector's own reading
  stands. `run_flag_scan` reads the flag from the same row as `yesterday_stage` (`db.get_yesterday_flag_state`: ONE statement
  returns the stage map and the hold set, so both come from the same row of the same snapshot; a failed read raises — an
  empty set would hold every downgrade again, silently) and logs `holds_carried=N` on the
  `flag_scan <date>: scoring …` line. **Rejected variant**: compare against yesterday's RAW read — it re-holds a second-step
  downgrade (held COILED from a raw TIGHTENING, raw WATCH today → held at TIGHTENING), i.e. a hold following a hold.
  **Trigger**: `docs/analysis/htf_scope_2026-10-10.md` G4 / §6 item 5 — `flag_continuation.md` and the `compute_flag_metrics`
  docstring say "held one day", this file says the stage machine is unchanged, and `yesterday_stage` was the STORED (already
  held) stage, so the hold re-armed every night until INVALIDATED or a pivot reset (CHYM read TRIGGERED 7 scan days on raw
  TIGHTENING / WATCH / COILED; WDAY held TRIGGERED 3 days at −12.8% under its pivot). **Evidence** (prod read-only,
  `scripts/probes/_697/`: `item5_q1_hold_rows.sql/.out` = 92 names × 70 scan dates, one pull; `item5_q3_shadow_parents.sql/.out`
  = every stored shadow row of the five intraday tables since 07-01 with its parent row, one pull; `item5_replay_hold.py/.out`; test
  `tests/test_697_one_day_hold.py` pins these numbers): each stored row's RAW reading is recoverable (`held_from_stage` when
  held, else `stage`), so the chain is re-threaded per name through the SHIPPED `stage_after_hold`. **Validity**: the OLD rule
  re-threaded from raw readings reproduces prod's stored stage + hold on **2707 of 2707 rows**, and its probe counts equal the
  live SQL probe's (`verify_hold_live_baseline_2026-10-09.out`: 43 / 24 / 0 / 20). **Effect over the 60 scan dates to 10-09**:
  held rows **44 → 21** (COILED 21 → 10, TRIGGERED 12 → 3, TIGHTENING 11 → 8); **24 rows change** — exactly the holds that
  followed a hold (55% of holds were followed by another; 17 of 60 nights have ≥ 1 change, max 3, median 0); stage rows
  TRIGGERED 16 → 7 (= the 4 real reads + 3 first-night holds: CHYM 08-20, WDAY 08-31, IOVA 09-15), COILED 40 → 32, TIGHTENING
  102 → 113, WATCH 310 → 316. **The 4 real (un-held) TRIGGERED reads — CHYM 08-19, WDAY 08-28, IOVA 09-14, XHLD 09-09 — are
  unchanged**: each is licensed by an UN-HELD COILED in its 5-day window, and an un-held COILED is a raw reading no re-threading
  can remove (TRIGGERED needs `coiled_today or was_coiled_recent`; the nearest un-held COILED sits 2 / 4 / 5 / 1 calendar days
  before CHYM / WDAY / IOVA / XHLD — IOVA is on the edge of the 5-day window, 09-09 → 09-14). That check is on the STORED reads
  only: a breakout that only the bars would show cannot be replayed from rows (UNINTENDED (d)). Not modelled: the universe carry (items 1+2) keys on stored
  stages, so a name that leaves WATCH-or-better a day or two sooner is carried a few sessions less — second order. **Anticipated
  effect**: a lower reading shows after ONE night instead of persisting; `/flags` and the digest's "COILED — still coiled" show
  what the detector read, not a label held for days. **WDAY (item 2's replay)**: with item 5 WDAY leaves TRIGGERED on 09-01 (held
  08-31 only), so a carried 09-03 / 09-04 row reads WATCH — the "held-TRIGGERED with no fresh breakout" print item 2 warned
  about shrinks from 12 name-nights to 3 (one per hold, by design). **Reversion-flag**: REFINEMENT of the 2026-05-01
  hysteresis — restores its documented rule, not a new one.
  **EXPECT** (baseline = `verify_hold_live.sql -v d0=2026-07-17` on prod before deploy: after_hold 43, violators 24,
  fingerprint 0, first_holds 20, over 60 scan dates), read from the first scan after deploy: (i) **every night**, the
  container log line `flag_scan <date>: scoring N candidates | holds_carried=K` shows K equal to the number of tickers whose
  latest prior row (≤ 5 days) has `held_from_stage` NOT NULL — `verify_hold_live.sql`'s second statement, column
  `expected_holds_carried`, which is NOT `after_hold` (that counts only tickers that got a row that night); read BEFORE the
  scan, it gives **K = 1 for 10-12** (`verify_hold_live_pre_deploy_for_2026-10-12.out`: KOD, held COILED on 10-09). (i) shows
  **the hold reader is running** and nothing more — a call site that dropped `yesterday_was_held` would still log the same K;
  (ii) and (iii) are what show the fix ACTS. (ii) **violators = 0** on every scan date ≥ deploy (a hold row whose yesterday row was a hold; the
  old code wrote 24 in 60 dates); (iii) **fingerprint ≥ 1** within the first 20 scan sessions (10-12 → 11-06): a row whose
  yesterday was a hold, whose stage FELL, and which is NOT itself a hold — the row the old code would have held again; the
  replay predicts 11 in 60 dates (98% of 20-session windows hold ≥ 1; only 63% of 10-session windows and 48% of 5-session
  ones, so a quiet fortnight proves nothing); KOD on 10-12 is the live candidate for the first one IF it reads below COILED
  (a candidate, not an expectation); `first_holds` keeps appearing (21 in 60) — the one-night hold still works.
  **UNINTENDED to watch** (all measured on the replay): (a) a few more `NEW TODAY` pushes — a name that relapsed after a held
  label and re-enters now pushes again (≈ +3 in 60 nights: 08-19, 08-26, 09-09; approximate, built from the replayed stages,
  not the delivered-key dedupe); (b) **all five intraday scans** (break `run_intraday_flag_break_scan`, support test, undercut &
  rally, MA pullback, low-vol rest — plus `get_flag_watchlist`, the bare `/watch` roster) take their watchlist from the latest
  stored TIGHTENING / COILED / TRIGGERED rows, so each loses names whose label was a hold. Of the 169 stored shadow rows since
  07-01 whose parent row is in the window (`item5_q3_shadow_parents.out`): 142 unchanged, 21 keep their place with a lower parent
  stage (e.g. CHYM 08-28 TRIGGERED → COILED, IOVA 09-14 COILED → TIGHTENING), **5 would not have been written** — 2 breaks:
  CDNA 08-25 (parent 08-24 held TIGHTENING on a raw WATCH) and WDAY 09-03 (parent 09-02 held TRIGGERED on a raw WATCH); 3 in the
  other four tables: support test ABVX 07-20 (parent 07-17), MA pullback CDNA 08-25 (parent 08-24) and MA pullback WDAY 09-02
  (parent 09-01); one more row (low-vol rest ATAI 07-24) has a stored parent that differs from what the scan saw, and is
  excluded as not a hold-rule effect. Shadow rows only (`mi_flag_breaks` → `mi_htf_breakout_shadow`, #397 evidence; no order;
  the flag strategy stays disabled, THE LINE holds). Also, the deprecated `flag_continuation` outcome adapter
  (`strategies/adapters.py` ~300) counts every stored TRIGGERED row as a `closed` outcome: 16 → 7 in the window (a count with
  no R attached, on a strategy that stays disabled); (c) `BREAKOUT
  CONVERGENCE` tags on EP alerts read the stage within 5 calendar days (`db.py` ~7180): fewer `breakout`-class tags from a held
  TRIGGERED label — display + audit row only; (d) **TRIGGERED licenses itself on STORED labels** (`flag_detector.py`
  ~1291: `coiled_today or "COILED" in recent_stages[-5:]`, `db.get_recent_flag_stages`, 5 calendar days), so the per-night
  reading of TRIGGERED is NOT history-free: before, a name that read COILED once and relapsed kept a held COILED label
  indefinitely, so a breakout any number of days later read TRIGGERED; now the label lasts one extra night, and a breakout more
  than ~5 calendar days after the last real COILED (with no `coiled_today`) no longer reads TRIGGERED. That is the documented
  5-day window, not a new rule, and it touches the same TIGHTENING → TRIGGERED question as #146 (the rule itself is untouched).
  **Measured: 0 of the 4 real TRIGGERED reads in the 60 days move** (each has an un-held COILED 1–5 days back; IOVA's sits on
  the edge), but a stored-row replay cannot see a breakout only the bars would show. **Hand-off to #697 item 3 (#146 page)**:
  (1) CDNA 08-24 is a raw WATCH, so under the documented hold CDNA's 08-25 breakout is NOT "from TIGHTENING" at all; (2) the
  #146 baseline ("TRIGGERED reads under today's rule") is item 5's rule, with the licence of (d); (3) any replay that feeds a
  stored or replayed stage back as `yesterday_stage` without `yesterday_was_held` re-creates the OLD behaviour. As of
  2026-10-11 (derive: `grep -rn yesterday_stage scripts tests`): `_146_faithful_harness.py` now threads it (via
  `db.get_yesterday_flag_state`; ⚠ it also predates the required `carry_days` argument of `get_yesterday_flag_pivots`, so it
  does not run as-is); `tests/test_htf_labelled_corpus.py` threads it; NOT threaded and chain-feeding (their committed
  outputs are the OLD-rule numbers; thread `prev["held_from_stage"] is not None` before re-using them for anything about
  today's rule): `_592_610_htf_grid_replay.py`, `_610_htf_replay.py`, `_610_htf_depth_sma20_replay.py`, `_668_analyze.py`,
  `replay_flag_fresh_tighten.py`, `backfill_flag_xndu.py` (each feeds its OWN output back), and
  `_610_four_reading_observer_replay.py` (`replay_stored_threading` feeds the STORED yesterday row: correct as an old-rule
  comparator against stored rows, wrong as a replay of today's code); unaffected (a hard-coded single-night
  `yesterday_stage`, no chain): `_146_triggered_gate_backtest.py`,
  `_697/replay_extras.py`, `_697/replay_extras_held.py`. Production has one call site (`run_flag_scan`'s `_score`), pinned by
  `test_run_flag_scan_holds_exactly_one_night_end_to_end` (it fails if the kwarg is dropped); no AST sweep of future call
  sites was added — it would be a source-pin test and the checked-in pin baseline only goes down.
  **WOULD-FAIL-IF** (positive; `scripts/probes/_697/verify_hold_live.sql -v d0=<first scan date after deploy>`): (a) **violators
  > 0** on any scan date ≥ deploy — the broken code writes ~0.4 a night, so one is a FAIL; (b) `holds_carried` missing from the
  log line, or 0 on a night whose prior rows include a hold — the hold reader is not running; (c) fingerprint still 0 after 20
  sessions — read as "the rule was never exercised by live data", NOT a pass. **DONE-WHEN**: (i) the logged `holds_carried`
  equals `expected_holds_carried` on each of the first 3 scan sessions after deploy (the hold reader is running), AND (ii)
  violators = 0 on every scan date from deploy, AND (iii) the first fingerprint row is seen (the proof the fix acts). If there
  is no fingerprint row by 2026-11-06 (20 sessions), the reader is running and violators are 0 but the rule was never exercised
  by live data — tell the operator that instead of closing on silence. **Deploy scope**: same as item 2 — `db.py` is on
  `scripts/exec_loaded_modules.txt` (line 46); `deploy.sh market-agent` carries the behaviour (`flag_continuation_scan` is
  INTELLIGENCE-owned), `deploy.sh execution` is drift hygiene so the running execution container's `db.py` matches the repo.
  Weekends are unrestricted. This branch contains items 1+2, so it ships them with it.
  Tests: `tests/test_697_one_day_hold.py` (25). Item 5 itself: the original 22 all failed on the item-1+2 branch
  (`scripts/probes/_697/red_item5_on_base.txt`). Review fixes (one read for stage + hold, licence margins, five-table shadow
  effect): 5 fail and 6 error on the item-5 head (`scripts/probes/_697/red_item5_fix_on_item5.txt`, which includes the two
  `test_598_*` files that now patch `get_yesterday_flag_state`). Mutation check on the call site: delete
  `yesterday_was_held=` from `run_flag_scan`'s call and 2 tests fail (the end-to-end one and the one-statement one).
- **2026-10-11 — #697 item 2: the flag board's universe CARRY now keeps a name while its base can still be alive —
  WATCH and stored-TRIGGERED names are carried, and "5 days" means 5 scan sessions, not 5 calendar days; a name that
  reached TIGHTENING-or-better stays scored for 25 sessions. No admission criterion, stage threshold, pole window,
  depth, ADR/ADV floor or trade path moved: it decides only which already-vetted names the scan SCORES.** Branch
  `wk1011/697-items-1-2`, not yet deployed. Rule + owner: `flag_continuation.md` "Universe / eligibility"; code
  `db.flag_carry_sources` + `get_flag_universe` path (e).
  **What**: stored WATCH / TIGHTENING / COILED / TRIGGERED in the last 5 scan sessions → tag `flag_stage_carryforward`;
  else stored TIGHTENING / COILED / TRIGGERED in the last 25 sessions (`_PIVOT_LOOKBACK_DAYS`) → tag
  `flag_pivot_window_carryforward` (exclusive of the first). A scan *session* = a scan date with bars in
  `mi_daily_closes` (drops the 09-07 Labor Day partial scan: 87 names, 0 bars). `INVALIDATED` / `unqualified` rows never
  carry; `FLAG_STAGE_CARRYFORWARD_ENABLED=false` still turns the whole path off. **A carried name must also have a bar on
  the SCAN date** (review fix, same day) — the organic path already requires it (`INNER JOIN mi_daily_closes d ...
  d.trade_date = $1`); without it `_score` rates a name on FROZEN history: FBRX (last bar 08-26, deal closed) was carried on
  12 scans 08-27 → 09-14 (`q8_carried_no_bar.out`; every other night is clean), a frozen WATCH-or-better read re-arms its own
  carry (with the G4 hold, indefinitely), and a market-holiday scan (06-19, 07-03, 09-07: 0 bars each) would re-score ~26-30
  carried names on the prior day's bars instead of ~4. A halted name simply resumes the day its bar returns (the windows
  count scan sessions, not that name's missing bars). Admission still moves no threshold, window or floor — it only stops
  the scan scoring a name that has nothing to score. **Trigger**: htf_scope G1 — 19 of 304
  WATCH rows (18 names) in 60 days had no row the next scan day; the old query skipped stored TRIGGERED (WDAY, held
  TRIGGERED to 09-02, then NO row 09-03 → 09-16 — `q2_sessions.out` — so its 09-08 close under the base low never stamped
  `failed_at`: `q7_failed_at.out` — `failed_at` is non-null on 0 rows in the whole table, and the breakout anchor that
  arms it exists on 2 rows of 1 ticker) and counted 5 CALENDAR days. **Evidence** (all prod
  read-only, `scripts/probes/_697/`): (1) *admit replay on stored rows* (`q1_admit_replay.sql/.out`, summary
  `summarize_q1.out`): in the clean era (nights 08-04 → 10-09, n = 48, where the 25-session lookback sits wholly inside the
  06-27 rule) the new rule adds a **median 10 names a night** to a ~540-name scan (range 6–19, ~2%): ≈8 from the 25-session
  memory, ≈1–2 WATCH, 0.5 TIGHTENING/COILED, <0.1 TRIGGERED (6 name-nights in 60 sessions: CHYM, WDAY). The 07-16 → 07-31
  nights show 40–125 only because the 25-session window reaches back into the retired pre-06-27 rule's rows — excluded. First
  order: stored rows are the OLD run's, so an added name that reads WATCH-or-better would extend its own window (bounded by
  the extras' own WATCH-or-better count, below). (2) *what the shipped detector says about the added names*
  (`replay_extras.py/.out`; bars + stored rows in `q6_extra_bars.out`): validated first — the offline call reproduces the
  stored un-held stage on **1538 of 1590 pairs (96.7%)**; then of the **493 added name-nights**, 42.2% read INVALIDATED and
  53.3% unqualified (runup, ADR, ADV the commonest reasons), **4.1% WATCH (20), 0.4% TIGHTENING (2: BWIN 08-26, 08-28), 0
  COILED, 0 TRIGGERED**; extras reading WATCH-or-better: median 0 a night, max 3. Approximation stated: no stored prior pivot
  and no hysteresis for a name that had no row — **so this replay could not see a HOLD**; the same 6 stored-TRIGGERED extras
  re-run with the hysteresis ON are in `replay_extras_held.py/.out` (2 of the 6 name-nights are held-TRIGGERED, see
  UNINTENDED). (3) *the shipped query vs the independent replay* (`emit_carry_sql.py` captures
  the query text from the real function; `q5_carry_prod.out`, `summarize_q5.out`): identical carried-name counts on all 7
  session dates compared (09-03 / 09-04 / 09-08 / 09-09 / 09-14 / 09-16 / 10-09 = 30 / 33 / 32 / 29 / 28 / 25 / 27 — the
  independent replay's count minus the names with no bar that night, `q8_carried_no_bar.out`: FBRX on 09-03, 09-04, 09-08,
  09-09 and 09-14) and 0 on the 09-07 holiday; 15 ms (was 7.4 ms before the bar-on-date guard, which adds one primary-key lookup per
  candidate row). 10-12 can no longer be pre-run (no bars yet); its prediction stays the replay's 26 candidates / 10 on the
  long tag, and no name has been carried without a bar since 09-14.
  **Anticipated effect**: the scan scores ~10 more names a night (almost all of which write INVALIDATED / unqualified rows —
  the telemetry #654 needs); a WATCH name that dips out of the organic set keeps getting rows; a TRIGGERED name keeps getting
  rows until its base ages out. **Reversion-flag**: REFINEMENT of the 2026-05-19 path (e). **EXPECT** (baseline: the old
  carry admitted a median 4 names a night; 6% of WATCH rows had no next-scan row; `failed_at` never stamped): from the first
  scan after deploy (Mon 10-12 17:25 ET, read Tue 10-13), every query below = `scripts/probes/_697/verify_carry_live.sql`
  (`-v d=<scan date>`): (i) `mi_flag_candidates` rows for that scan date whose `universe_sources` hold
  **`flag_pivot_window_carryforward`** — the tag only the NEW code writes: **≥ 1, expected ~10** (replay 6-20 a night, 10
  predicted for 10-12; the old code wrote 0 such rows ever). The older `flag_stage_carryforward` tag does NOT tell new from
  old: the old code already wrote carry-only rows with it (0-4 a night, on 36 of 48 nights, 08-04 → 10-09), so it is not
  the pass criterion. Rows kept ONLY by a carry (a carry tag and none of `rs_top200`, `rs_1m_80`, `momentum_25pct`,
  `magna53_failed_r3`, `ninem_universe_watch`) are the **ballooning alarm: above 30** (replay 7-19 a night, the old code
  never above 4); (ii) a stored WATCH-or-better name from the last 5 sessions has a row on that date — the violator set
  (`b_violator`) is empty; one empty night is NOT proof (the old code's set was empty on 8 of 48 nights), so it counts
  only together with (i); (iii) a few carry-only rows with stage INVALIDATED. **UNINTENDED to watch**: the digest header's "tickers scanned" up ~10 and its
  "📉 N dropped out" count up ~4 a night (carried names that read INVALIDATED are now counted — they used to vanish silently);
  the `/htf` INVALIDATED roster and the deprecated `flag_continuation` outcome-adapter's `no_entry` rows grow the same ~4;
  a `NEW TODAY` push can now name a ticker with no organic tag (a leader that dipped out of the RS set and re-tightened — 1
  name in 48 nights on the replay; read it against the chart, it is the carry doing its job); ⚠ G4 INTERACTION —
  the hysteresis stores a HELD label, so a held stage re-arms this carry each night until INVALIDATED or a pivot reset, and a
  carried held-TRIGGERED name WILL sit in the digest's TRIGGERED section with no fresh breakout: **expected on the first
  name of this shape until item 5 ships — do not report it as a defect.** The replay with the hysteresis ON
  (`replay_extras_held.py/.out`) lists WDAY in that section on 09-03 and 09-04, 9.0% and 13.9% under its pivot (raw read
  WATCH, held as TRIGGERED): 2 name-nights of the 6 stored-TRIGGERED extras (CHYM 09-01 reads unqualified; WDAY 09-08/09/10 go
  INVALIDATED = the #654 stamp). The same held label also feeds `check_sugar_baby_convergence` (`db.py` ~7180: a COILED /
  TIGHTENING / TRIGGERED row within 5 CALENDAR days), which can put a `BREAKOUT CONVERGENCE` tag on an EP alert
  (`briefing.py` ~3330) — a display tag plus an audit row, read by no order, entry, sizing or safeguard path (THE LINE
  holds). Item 5, the one-day hold, removes the re-arm [**2026-10-11 update: item 5 is the entry above — a held label now lasts one
  night, so the "expected until item 5 ships" caveat above ends the day item 5 deploys; with it on, WDAY's 09-03 / 09-04 carried
  rows read WATCH**]. **WOULD-FAIL-IF** (positive; `verify_carry_live.sql`): on a scan date after deploy, (a) NO row holds
  `flag_pivot_window_carryforward` (the new carry is not running — the old code never wrote that tag; the replay predicts ~10;
  an alternative bar is carry-only rows ≥ 5, since the old code's max is 4 and the replay's min is 7); (b) the **violator
  set** is non-empty — a ticker with a stored WATCH / TIGHTENING / COILED / TRIGGERED row in the previous 5 scan sessions and
  NO row on the date (the probe drops a name with no bar on the date or < 60 bars; also excuse a logged `flag_scan: <T>
  failed`, a container-log line). **An empty violator set on one night is not proof**: the old code's was empty on 8 of 48
  nights, and on 3 of them (08-12, 09-28, 10-02) it also met the old carry-only test — the broken system passed (a), (b) and
  (c) together — so (b) counts only with (a). (c) more than 30 carry-only rows (ballooning). A night with an empty violator
  set but no `flag_pivot_window_carryforward` row is a FAIL for (a), not a pass; a night where nothing was due to carry is not
  expected (26 carried names predicted for 10-12). The probe was run once on prod for 10-09, the last night of the old
  code, and reads as the broken system should: `a_long_tag_rows` 0 and 6 violators — ABCL, CAI, FWDI, SDGR, TEM, XNCR
  (`verify_carry_live_2026-10-09.out`; it matches the independent replay's 6). **DONE-WHEN**: the first 3 scan sessions after deploy (10-12 → 10-14) each satisfy (a)–(c), and any
  `NEW TODAY` push on a ticker without an organic tag has been read against its chart. #654's first real `failed_at` stamp
  stays event-gated under #654 (it needs a TRIGGERED name to close back under its base — WDAY was the first in 60 days) and
  does not gate this item. **Deploy scope**: `db.py` IS on `scripts/exec_loaded_modules.txt` (line 46) — NOT the single
  market-agent deploy the 10-10 scope assumed. `deploy.sh market-agent` carries the behaviour (`flag_continuation_scan` is
  INTELLIGENCE-owned: the execution container never runs `get_flag_universe`); `deploy.sh execution` is drift hygiene so the
  running execution container's `db.py` matches the repo. Tests: `tests/test_697_universe_carry.py` (27 of 28 fail on
  origin/main — the 28th pins the unchanged kill switch; the bar-on-the-scan-date guard has its own red,
  `scripts/probes/_697/red_nobar_on_branch_head.txt`).
- **2026-10-11 — #697 item 1: the Friday "Flag Bases" section renders again, a digest send now leaves a record, and the
  Friday chip stops printing `r1.00` on a short base. A REACH / display change: no stage, threshold, pole window, depth,
  ADR/ADV floor, order, entry, sizing or safeguard path moved.** Branch `wk1011/697-items-1-2`, not yet deployed.
  **What**: (a) `friday_watchlist._fetch_flag` no longer calls `should_run("flag_continuation")` (the detector has no
  strategy row; mirrors `run_flag_scan`'s 08-02 change) — the section had been `[]` since 08-02; (b) one `flag_digest_sent`
  audit row per digest send (tickers per section, delivered or not); (c) the Friday chip prints
  `flag_detector.board_tightness` instead of the raw range ratio. **Trigger**: `docs/analysis/htf_scope_2026-10-10.md`
  §4/G7 + the #598 review's carried note; operator "Htf" 2026-10-11 pulled it from 10-17/18. **Evidence**: prod, read-only
  (`scripts/probes/_697/q3_friday_flag.out`): `mi_strategies.flag_continuation` = `deprecated / enabled=false`; the last
  stored Friday list with a FLAG name is the week ending 2026-07-31 (none in the 10 lists since, 08-07 → 10-09); Friday
  2026-10-09's only board name, KOD (COILED, base 5d), is stored 1.000 / 1.000 with a last-2-bars reading of 0.63.
  A detection-criterion change this is NOT (CHANGE_PROCESS does not apply): no value any stage reads was touched.
  **Anticipated effect**: a non-empty "Flag Bases" section on every Friday whose latest scan holds COILED / TIGHTENING
  names; a `flag_digest_sent` row for every digest message. **Reversion-flag**: none (restores the pre-08-02 section; adds a
  record). **EXPECT** (baseline: section empty every Friday since 08-07; digest sends unrecorded): Friday 10-16 18:00 ET —
  IF the latest scan on or before 10-16 holds ≥1 COILED / TIGHTENING name, `mi_weekly_watchlists` week ending 10-16 has ≥1
  row whose `sources` contains `FLAG` and the message carries the section (FLAG ranks 2nd, behind ≤5 EP HIGH, so the 25-name
  cap cannot cut it); a name of base ≤5 shows `last 2 bars …`, never `r1.00`. Every night a digest message goes out, one
  `flag_digest_sent` row for that scan date whose `new_today` / `triggered` / `coiled` tickers equal the tickers the
  message names. **UNINTENDED to watch**: up to 8 flag names displace the lowest-priority ambient (RS / parabolic) rows
  when the cap binds, as before 08-02; the Friday message is up to 8 lines longer. **WOULD-FAIL-IF** (positive): a scan
  date whose stored board holds ≥1 COILED or TRIGGERED row (so the digest cannot have been suppressed) has NO
  `flag_digest_sent` row; or a Friday whose latest scan holds a COILED / TIGHTENING name has no `FLAG`-sourced row in
  `mi_weekly_watchlists` for that week (`scripts/probes/_697/verify_friday_flag.sql` — `sources` is JSONB, so the test is
  `sources ? 'FLAG'`, never `sources LIKE`; its run over 07-01 → 10-09 is the baseline: FLAG rows on the Fridays through
  07-31 and none on the 10 since, although 9 of those 10 boards held COILED / TIGHTENING names —
  `verify_friday_flag.out`). A quiet night (no COILED, TRIGGERED or new transition) or an empty Friday board
  is **inconclusive**, not a pass. **DONE-WHEN**: one non-quiet digest night AND one Friday with a non-empty board have
  each been read against the above (if the 10-16 board is empty, the next Friday with a non-empty board closes it).
  **Deploy scope**: `flag_detector.py` and `friday_watchlist.py` are NOT on `scripts/exec_loaded_modules.txt` →
  `deploy.sh market-agent` only. Tests: `tests/test_697_htf_reach_repairs.py` (15 of 19 fail on origin/main).
- **2026-10-04 — #598 follow-up: the M&A / deal-pin screen now covers TIGHTENING, and the stage board stops calling
  a state a setup. Closes the known limit above. No stage rule, threshold or trade path moved.**
  **What**: `flag_scan` screened only COILED + TRIGGERED, so a buyout-pinned name (price welded to the offer) read as a
  perfect TIGHTENING base and reached `/flags` and the 17:25 NEW TODAY block. The SAME screen — `is_likely_ma`
  (`check_polygon`, 21-day lookback, day-window pin reader) and the Layer-2/3/3b price backstop, both unchanged — now runs
  on `_MNA_SCREENED_STAGES = (TIGHTENING, COILED, TRIGGERED)`; a hit downgrades to `unqualified`,
  `reason='mna_filter:<source>'`, plus the usual `mna_filter_fired` row (detector `flag`, original stage). Wording only:
  `/flags` header `COILED — actionable setup` -> `COILED — tightest bases, watch only`; Friday watchlist label
  `Flag Setups` -> `Flag Bases … (watch only)`; `/htf` menu entry `Higher-timeframe setups` -> `Higher-timeframe flag bases (watch only)`.
  **Trigger**: operator ok 2026-10-03 (same news-nominates / own-day-range-decides rule the coil board got 10-03).
  **Evidence**: extends the signed 502/692 screens (news nominates, own-day range decides) to one more stage; pinned by
  `tests/test_598_flag_tightening_screen.py`. ⚠ **Not every layer was measured on TIGHTENING**: the news screen and the
  0.5% median-range backstop are unchanged rules, but the fresh-pin check (5-session band <= 2.5% plus a >= 5x volume spike
  within 10 sessions) and its 5-session carry-over now also reach TIGHTENING, and their "no overlap with real bases"
  evidence (`docs/analysis/htf_deal_pin_fresh_2026-07-24.md:72`) covers only the 405 COILED/TRIGGERED rows. A young
  TIGHTENING base right after an EP-gap pole is the shape that could meet the volume half; that case was never measured.
  **Cost**: the model call fires only on keyword-hit headlines (<=3 articles a ticker, memoized per ET day) on the
  existing `shared` budget pool (300 of the 400/day calls; the EP scan keeps its 100 reserve); the deal-pin layer is
  price-only. The screen runs every night on every TIGHTENING name still held and the memo resets each ET day, so the
  lookups grow with names held x days held x keyword-hit articles; the repo records no per-scan count of held TIGHTENING
  names (the only figure is 11 names ENTERING TIGHTENING in 30 days, which counts entries, not holdings).
  **Anticipated effect**: a pinned name that would have been announced at TIGHTENING no longer is; ordinary TIGHTENING
  names (daily range well above 2%) are unchanged. **Reversion-flag**: REFINEMENT of #502/#692 (extends population).
  **EXPECT** (against the baseline: pinned TIGHTENING names reached `/flags` and NEW TODAY): `mna_filter_fired` rows with
  `detector='flag'` and original stage TIGHTENING appear for genuinely deal-pinned names (news shows a deal AND own-day
  range <= 2.0%); the TIGHTENING count on `/flags` falls only by those. **UNINTENDED to watch**: `reason` =
  `mna_filter:deal_pin_fresh` or `mna_filter:deal_pin_sticky` on a TIGHTENING name whose news shows NO deal (a real
  young base wrongly dropped). **WOULD-FAIL-IF**: any such row whose headlines show no deal, or `/flags` TIGHTENING count
  dropping with no matching `mna_filter_fired` rows. **DONE-WHEN**: every TIGHTENING `mna_filter_fired` row in the first
  10 market days after deploy has been read against its headlines (or none fired and the count is unchanged). A $0 replay
  of past TIGHTENING `mi_flag_candidates` rows through the fresh-pin check is the pre-deploy way to measure it.
  **Status**: branch `598-flag-tightening-screen`, not yet deployed. **Two-step deploy**: `agent.py` is on
  `scripts/exec_loaded_modules.txt`, so `deploy.sh market-agent` alone leaves the `/flags` header stale in the execution
  container; `channels/telegram.py` (the `/htf` menu label) is orchestrator-owned. Run `deploy.sh both`, then
  `deploy.sh execution`.
- **2026-10-04 — #598: the 17:25 ET digest now opens with `NEW TODAY` — every ticker that moved up into
  TIGHTENING or COILED, with run-up, pivot and base tightness. A surfacing change: no stage, threshold,
  entry or trade path moved. Built on branch `598-flag-stage-push`; NOT yet deployed.**
  **Trigger**: operator 2026-08-25 — CDNA was TIGHTENING from 2026-08-18, the day before an experienced trader
  bought it, and nothing usable reached him (`docs/analysis/htf_surfacing_gap_2026-08-25.md`). The digest's
  `NEW TIGHTENING` block listed bare tickers; COILED names were re-listed every day.
  **Evidence**: single-case trigger (CDNA) plus the 30-day volume the PLAN line quotes — 36 names reached WATCH,
  11 TIGHTENING, 6 COILED, 1 TRIGGERED. No threshold depends on it, so no backtest applies; the rule is pinned
  by `tests/test_598_flag_stage_transition_push.py` (41 tests, 12 mutants all caught — see the commit).
  **Anticipated effect**: a `NEW TODAY` block on roughly one scan day in two or three (entries into TIGHTENING /
  COILED); the digest's own send/suppress days are unchanged except that a day whose only news is a name
  re-entering from `unqualified` / INVALIDATED now sends (the old test missed those). One
  `flag_stage_transition` audit row per name announced.
  **Reversion-flag**: REFINEMENT of the 2026-05-01 digest (the `NEW TIGHTENING` roll-call); the
  `previous in (None, WATCH)` test is widened to rank-based entry, and the `actionable setup` COILED header
  is dropped (CLAUDE.md SETUP vs FAMILY).
  **Status**: shipped to a branch, awaiting deploy and field validation.
- **2026-09-27 — #592 follow-through: a name that leaves the scan for over 5 days keeps its pole top.
  Enforces the signed 09-04 rule (a wick over an unresolved flag never becomes the top); no threshold moved.**
  **What**: `db.get_yesterday_flag_pivots` carries the last anchored top for `flag_detector._PIVOT_CARRY_DAYS` =
  40 calendar days, derived from the 25-session pivot lookback (was 5, sized for a weekend); `_find_pivot_high` still ignores a carried top outside its
  25-session lookback. **Why**: verified live on prod — among flags with a formed flag whose top moved up,
  moves on a wick with no close above the old top fell from 135 of 885 (07-01..09-03) to 8 of 146
  (09-05..09-25), and 7 of the 8 (MRVL, ORCL, SMR, ASAN, LITE, NMAX, VERA) were names back after 6+ days out
  of the scan, re-anchored fresh with no carried top. The 8th, ARQT 09-21, is the existing volume rule (a
  retest within 2% of the top on higher volume takes the anchor) — not this defect, unchanged.
  **Impact, replayed in the running image on the 278 rows 09-05..09-25 with a 6–40-day gap**: 257 identical
  tops, 21 differ (~1.4 a day) — 12 where the fresh anchor had taken a higher wick, 9 where the stable anchor
  holds a top the volume rule would have swapped for a lower bar in the 2% band; both are what a name scanned
  every day already gets. **Reversion flag**: none. Tests: `tests/test_592_flag_pivot_carry.py`.
- **2026-09-19 — #610 THE FOUR-READING OBSERVER IS BUILT. Telemetry only — THE LIVE GATE IS
  UNCHANGED (flag LOW ÷ pole high ≥ 75%). Built in a card, NOT yet deployed; the deploy is TWO
  steps (`db.py` is execution-loaded: `deploy.sh market-agent`, then `execution`).** Implements
  the 2026-09-18 ruling below ("observe several readings, keep acting on one").
  **What**: `compute_flag_metrics` records four new keys per candidate-day, persisted as four
  columns on `mi_flag_candidates` (idempotent `ALTER … ADD COLUMN IF NOT EXISTS`; CREATE TABLE in
  parity; carried through the upsert so a re-scan refreshes them):
  `depth_on_low` = the flag's lowest LOW ÷ pole high (the LIVE reading, = `1 − flag_depth_pct`;
  the gate fires below 0.75) · `depth_on_close` = the flag's lowest CLOSE ÷ pole high (the spec's
  literal `Close ≥ 0.75×High`) · `sma20_margin` = `(close − sma_20) / sma_20` · `ma_stack_margin`
  = the TIGHTER of the two stack legs, `min((sma_10 − sma_20)/sma_20, (sma_20 − sma_50)/sma_50)`.
  **⚠ The two margins are SIGNED — negative = that gate fires, by that fraction — so on the live
  verify MRNA reads −0.03% / −0.24%, not the unsigned 0.03 / 0.24 the PLAN line quotes.**
  **Where**: the depth pair is set where `flag_depth_pct` is (every row that reaches the base
  window, including the ones the runup / trend / depth checks then reject); the SMA pair right
  after the SMAs are computed and BEFORE the INVALIDATED returns (every row past the runup gate
  and the flagpole guards). NULL before that point; `ma_stack_margin` is NULL whenever the gate
  itself cannot evaluate (an SMA missing) — each column mirrors its gate exactly. Read by nothing.
  **Verification, pre-deploy**: (1) `tests/test_610_htf_four_reading_observer.py` — MRNA on the
  real fixture bars (the 09-17 bar appended from prod): **72.8% / 75.5% / −0.035% on 09-16 /
  −0.24% on 09-17** (the hand figure "0.03" came from the reason string's 2-dp SMA; exact is
  0.051/145.671), with the acting stage/reason on both days byte-equal to the stored prod rows;
  gate agreement on every replayed corpus row; NULL-until-inputs; the upsert carries all four —
  seven mutations RED-proven, listed in the file's docstring. (2)
  `scripts/probes/_610_four_reading_observer_replay.py` over every stored candidate-day
  2026-08-17 → 09-17 (12,657 pairs / 1,796 tickers, prod bars, $0): **OLD function vs NEW, 0
  diffs on stage / reason / score / held_from_stage** — the WOULD-FAIL-IF, met; NEW vs the STORED
  rows **99.75% identical (12,625 / 12,657)** with stored-row state threading and **100% on all
  4,282 rows from 09-07 onward** — every one of the 32 mismatches sits on or before 09-04 and is
  the #592 anchor fix (committed 09-04 `2d343421`, AFTER that day's 17:25 ET scan, and live by
  09-08 per the 2026-09-05 entry below — the deploy timestamp itself was not read; the stored
  `base_age_0_below_3` rows are what the pre-fix pivot walk wrote, where HEAD holds the older
  pivot and reads `runup_…`) or a bar the vendor revised since the scan (IESC's volume), i.e.
  the rule era, not the observer. Readings populated: depth pair 4,157 rows, SMA pair 646.
  **EXPECT (live, from the first 17:25 ET scan after deploy)**: every row that reaches the base
  window carries the depth pair and every row past the runup gate carries the SMA pair (≈ a third
  and ≈ 5% of the day's rows, on the replay's proportions); the day's stage/reason distribution
  is unchanged against the prior week; a `flag_low_` reject reads `depth_on_low < 0.75`.
  **DONE-WHEN**: one full scan day writes all four. Reversion-flag: NEW (adds columns, changes no
  criterion). Nothing about THE LINE moved; the fork stays his.
- **2026-09-18 — OPERATOR RULING on the depth fork: DO NOT PICK ONE YET — OBSERVE SEVERAL.
  NOTHING CHANGED IN THE DETECTOR.** Per #610's DoD ("his ruling recorded in docs/setups/htf.md").
  **The fork put to him** (F1): measure flag depth on the flag's **LOW** ÷ pole **HIGH** (ours, the
  signed 2026-06-27 deviation) or on the **CLOSE** ÷ pole high (the source's literal
  `Close ≥ 0.75 × High`). My recommendation was to keep the low.
  **His ruling, verbatim:** *"i dont really see OUST, but i'd lean on letting MRNA. In any case, we
  should be able to observe multiple parameters since we're just collecting data and refining the
  setup, we still need to nail down entry/exit, so hard to make a final call right now."*
  **Three things he settled, and one he deliberately did not:**
  1. **OUST is NOT an HTF** — and this time it is a CHART READ, not the 2026-09-04 removal-list
     sign-off. The `tests/fixtures/htf_labelled.py` negative label is now directly supported.
  2. **He leans toward ADMITTING MRNA.** A LEAN, recorded as a lean — not a criteria change.
  3. **He REFUSED the binary, and gave the reason: entry and exit are not nailed down.** A depth
     rule cannot be chosen on outcome evidence while the entry and exit that produce the outcomes
     are still moving — the same reasoning as [[check-the-rule-era-before-comparing-to-actual]].
     ⚠ **OUST is the case in point: under the shipped rules its breakout is REJECTED outright
     (`stop_distance_gt_8pct`, every stop candidate 11-28% away against an 8% cap), and if the cap
     is overridden it is +3R or −1R depending on WHICH DAY'S sma10 is read.** A selection rule
     cannot be judged against an exit that unstable.
  4. **NOT settled, and not to be inferred:** which reading finally ships. That waits on entry/exit.
  **WHAT THIS MEANS MECHANICALLY — record several readings per candidate-day, keep acting on one.**
  The LIVE admission gate is UNCHANGED (flag low ÷ pole high ≥ 75%). Alongside it the detector is to
  RECORD, per candidate-day, the margins for each reading under discussion — depth on the low, depth
  on the close, the SMA20 invalidation margin and the MA-stack margin — so that when entry/exit
  settle, the choice is made on accumulated LIVE data instead of a one-off replay. **Observation is
  not admission: nothing a shadow column records can change what the board admits.**
  **The two knobs #610 originally asked for are dead and stay dead** — a one-bar depth allowance
  cannot reach MRNA (four bars breach; second-lowest low 73.6%) and an SMA20 margin adds zero
  breakouts at every size. Both measured: `docs/analysis/610_htf_depth_and_sma20_margin_2026-09-18.md`.
- **2026-09-16 — OPERATOR RULING on the detection fork. NOTHING CHANGED IN THE DETECTOR; this
  records a decision and closes out a question, per #610's own DoD ("his ruling recorded in
  docs/setups/htf.md").**
  **The fork**: after the 2026-09-10 replay, three options — (A) park #397's money-graduation
  thread, (B) fix the two `mi_htf_breakout_shadow` recorder defects and re-measure, (C) go at the
  detector. **He took A + C.**
  **(A) #397 is PARKED**, status `blocked`, re-opening on EP profitability rather than on a date.
  HTF is a DETECTION problem and is not traded, so a capture / realized-R number cannot decide
  anything about it — a point he has now made twice.
  **(C) is NARROWER THAN IT WAS WRITTEN, and the correction matters more than the ruling.** The
  Sunday page offered C as *"the ADR/ADV floors cut breakouts 91%"*. That premise had already been
  retracted twice inside #610 before the page existed:
  - **2026-08-31** — the floors cut the scanned input roughly IN HALF (228 passed vs 230 ADR + 86
    ADV killed on 08-31), never 91%.
  - **2026-09-04** — the 12-variant raw-bar replay put the collapse on the signed 2026-06-27 runup
    swap (`_RUNUP_MIN_RATIO` 1.50→1.90, `_RUNUP_LOOKBACK_DAYS` 60→40) working AS DESIGNED: its kill
    rate went 46% → 78-85%. Under the sourced runup, ADR is nearly moot — 4%→3% admits **+3 tickers
    and 0 breakouts** over two months.
  - **2026-09-10** — the proposal to lower the ADR floor was withdrawn the same hour, on his
    question *"why lower, what's the purpose of the range floor"*: names that PASS run ≥+20% in ten
    sessions at **4.91%**, the 3.0-4.0 band at **2.38%**, below 3.0 at **0.27%**. The rate rises
    monotonically with ADR, so **the floor sorts on exactly the property HTF monetises.**
  **So `_HTF_MIN_ADR_PCT` = 4% and `_HTF_MIN_ADV_SHARES` = 500,000 STAY, and they are no longer an
  open question** — they were measured against the ADMITTED population and they earn their keep. A
  large exclusion count is what a working filter looks like.
  **What is left of C**: `_RUNUP_MIN_RATIO` 1.90 over 40 days is the SOURCED spec (*"C≥1.9×C₄₀"*),
  not our invention. The remaining question is whether our READING of the source matches how its
  author actually screens — **#592's question**, and #610's 2026-09-04 note had already reached it
  (*"#592 and #610 collapse into one ruling"*). ⚖ **Methodology, not tuning: it is answered against
  the author's own labelled examples, never by loosening a sourced number because we want more rows.**
  **(B) NOT taken, and the consequence is recorded rather than dropped**: the two defects in
  `mi_htf_breakout_shadow` stay unfixed — (1) `_htf_settle_from_bars` credits a stop-limit fill at
  `base_high` without checking the break day's LOW, so a gap-above-entry day books a fill that could
  not have happened (CDNA 2026-07-31: entry 40.47, day low 40.67); (2) the shadow stores raw prices
  while `mi_daily_closes` is split-adjusted, so any join across a split is nonsense (CRWD
  2026-07-01, 1 of 16 rows). **Anything that later reads this table for OUTCOMES must fix both
  first.** They were not worth fixing for a sanity check on a thread now parked.
  **Files**: no code changed. `docs/analysis/610_397_htf_fork_for_sunday.md` carries the corrected
  fork; `docs/analysis/610_htf_replay_2026-09-10.md` carries the scope banner (what the replay
  measured is OUR ENCODING plus ONE exit bet, not the HTF pattern).

- **2026-09-05 — #356 follow-up: `get_recent_daily_history` now counts TRADING rows, not a
  calendar span; `flagpole_ratio`/`flag_depth_pct` persisted on `mi_flag_candidates`. Bug fix +
  telemetry, no criterion changed.**
  **Trigger**: #356's own to-do list (recorded 2026-08-26) named both as unbuilt: the two columns
  were absent (not merely NULL) from `mi_flag_candidates`, and `get_recent_daily_history` filtered
  `trade_date >= end - days` — a CALENDAR span, so the actual row count silently drifted with how
  many weekends/holidays fell inside that span on any given scan_date (the exact defect the
  2026-07-24 entry below papered over by inflating `_HISTORY_DAYS` to 380 calendar days).
  **Fix**: `get_recent_daily_history` now orders the ticker's own rows by `trade_date DESC LIMIT
  days` (a plain per-ticker top-N — no PARTITION needed, unlike the multi-ticker ROW_NUMBER pattern
  used for ADV-20 elsewhere in this file) — so "N rows" and "N trading days" are the same thing (no
  separate holiday calendar needed; `mi_daily_closes` only ever has a row for a day the market was
  open). `_HISTORY_DAYS` recalibrated **380 calendar → 260 trading** — the same target the 2026-07-24
  entry already named as its intent ("380 ≈ 260 trading rows"), now exact every day instead of
  fluctuating with the holiday count inside that specific calendar window.
  `flagpole_ratio` (`pivot_high / runup_low`, = `1 + runup_pct`) and `flag_depth_pct`
  (`1 - base_low/pivot_high`, the same quantity the flag-depth gate compares) are now computed
  in `compute_flag_metrics` from values it already derives and persisted as their own columns —
  telemetry only, read nowhere by the state machine.
  **Anticipated effect — MEASURED, not guessed**: `parabolic_detector.py` (the other production
  caller, `_HISTORY_DAYS=120`) is unaffected — every lookback there (`_sma`, `_compute_base_low`,
  `_roc`) slices relative to `today_idx`, never the total row count, so the extra rows it now
  receives (≈120 vs. the old ≈82 actual trading rows from 120 calendar days) are unused headroom,
  not a new admission path. For THIS detector, `hi_52w` (the Stage-2 near-52w-high gate) is the one
  place that consumes the ENTIRE returned row list rather than a fixed offset from today, so it is
  the only place row-count exactness matters. Measured the real NYSE trading calendar
  (`exchange_calendars`, 898 end-dates 2023-2026, scratchpad-only): the OLD 380-calendar-day window
  actually returned **258-263 trading rows** (mean 261.7, median 262) — never as low as the "~260"
  the old comment claimed as its target. NEW is fixed at exactly **260**, i.e. at the low end of that
  range. Direction: fewer rows ⇒ `hi_52w` can only be ≤ the old value in 897 of 898 dates (one rare
  date had OLD=258 < NEW=260, the opposite direction) ⇒ `pivot_high < 0.75×hi_52w` fires *less* often
  ⇒ **the fix is weakly MORE PERMISSIVE at this one gate, essentially never stricter** — nothing that
  qualified before gets newly rejected by it. Replayed the full 7-member labelled corpus
  (`tests/test_htf_labelled_corpus.py` fixture bars) old-window-vs-new-window, ticker-by-ticker,
  scan-date-by-scan-date — 405 (ticker, scan_date) pairs total, not just the corpus's own pass/fail
  assertions (which only check a handful of `assert_dates`). Of those, **116 pairs actually got a
  different window** (the other 289 truncated to the same fixture-data start under both old and new,
  so they're identical by construction, not evidence); the difference on those 116 was always 1-3
  rows (old − new). **All 116 produced identical stage AND reason.** Not a live-production replay (no
  DB access at fix time) — this is the best available check short of one.
  **Operator's call**: commit at 260 (the documented target, and the direction is provably
  permissive-or-neutral), or move to 262 (the measured median of the old behavior, closer to
  reproducing it exactly) if exact behavioral continuity matters more than hitting the stated target.
  **Reversion-flag**: NEW (first fix of this specific bug; not a reversal of a signed threshold).
  **Status**: ✅ **DEPLOYED AND LIVE AT 262 — read off the running `apollo-market` image
  2026-09-08** (`flag_detector.py:32`, matching the repo). The old line said *"shipped in this
  session, tree left dirty — not deployed"*, which was true on 2026-09-05 and stale by the next
  deploy; `live_rules.py --drift-only` caught it at CLOSE on 09-08.
  **The 260-vs-262 fork above is CLOSED at 262 — the exact-behavioural-continuity option**, i.e.
  the measured median of the old window rather than the stated 260 target. Recording the basis
  rather than re-asking: the entry's own replay showed the direction is permissive-or-neutral at
  this gate under EITHER value (all 116 differing pairs produced identical stage and reason), HTF
  is not live-trading (its money gate #397 is still blocked), so neither number can move a trade
  today. **If the operator prefers 260 — the documented target — it is a one-line change**; this is
  recorded as a settled default, not as a ruling he gave. Known
  inconsistency left OUT OF SCOPE (belongs to #592, not this line): `scripts/probes/
  _592_610_htf_grid_replay.py:153` still does `d - timedelta(days=fd._HISTORY_DAYS)` — a calendar-
  span slice — so it will silently stop mirroring live once `_HISTORY_DAYS` means trading rows;
  whoever next runs that probe needs to fix its slicing first. Tests: `test_schema_alter_create_parity.py`,
  `audit_column_writes.py check` (confirmed `mi_flag_candidates` is out of that gate's scope —
  it only covers `mi_live_trades`), full suite.

- **2026-09-04 — Pivot anchor: a wick over the pole top is no longer a new pole top (#592).
  Measurement fix, no criterion or constant changed.**
  **Trigger**: #592 (operator's HNGE call, 2026-08-24). Its two named causes did NOT hold up (the
  40-session window is the sourced criterion and rejects HNGE's 10-week pole by the spec's own
  scanner; the volume rule KEPT the higher-runup pivot — the 77%→41% drop was the 25-session pivot
  lookback expiring). The replay built to test them found the real anchor defect instead.
  **Root cause**: the stable-anchor walk (`_find_pivot_high`, #41) fired on ANY high beating the
  prior top by `max(1%, 0.25×ATR)`. A wick that never CLOSED above the top became the pole top, the
  40-session pole window slid INTO the flag, and a qualified pole re-read as a stub. Measured
  06-29 → 09-04: 9 names walked from a ≥90% actionable row to a `runup_` reject within 7 days; 2
  were the 5-week flag limit (SNOW, TWLO — by design); of the 7 walks, **2 were pure wicks that
  never closed above the top (QLYS 94%→88%, CHYM 110%→71%)** and 5 had closed above it (DELL, MAN,
  PGEN, RBRK, INTA — those still walk under the fix, correctly). None of the 9 ever re-qualified;
  QLYS then ran +31%. The full before/after diff (below) finds 6 more names the 7-day heuristic
  missed (BFLY, MBX, NIQ, OKTA, REPL, TRAX) — 8 names kept in total.
  **Fix** (`_flag_resolved_by`): a decisive high over a FORMED flag (≥ `_BASE_AGE_MIN_WATCH` bars)
  walks the pivot only if some bar since the flag formed CLOSED above the pole top. A pole still
  extending walks as before. A close test with NO volume term, deliberately: the first cut reused
  the TRIGGERED gate's volume test and, replayed, held the anchor BELOW price for weeks on real pole
  continuations at 1.3–1.5× volume (NEO +40%, RNG +16% above a stale pivot; 2,175 rows changed) —
  an invalid geometry. The close-only form is the geometry; volume is the entry's business.
  **Evidence**: replay of the SHIPPED function over the same 27,446 pairs (`docs/analysis/
  htf_pole_window_grid_2026-09-04.md` §2). Baseline reproduces prod at 99.58% before the fix, every
  mismatch accounted for; after the fix 350 rows / 110 tickers differ (305 are rejected→rejected
  bookkeeping), **+26 actionable rows on 8 names** (QLYS +24% and TRAX +18% over the next 20
  sessions; OKTA −5%, MBX −14%, BFLY −16%, REPL 0%; NIQ/CHYM truncated), **−5 rows on 3 names**
  (OUST, SHAZ on 06-29 — an older held pivot makes their flag deeper than 25%; REPL ×2). From
  08-03, once the seed chain has aged out: +6 rows / 3 names, −2 / 1. CDNA (must-not-miss) and HNGE
  unchanged. Board 10.4 → 10.8 actionable rows/day.
  **Anticipated effect**: ~1 name per week (8 names over the 10-week window) stays on the board
  that used to be silently ejected mid-flag; base_age keeps counting through the wick so those
  names still age out at 25. No effect
  on the runup, depth, trend, Stage-2, liquidity or tightness gates.
  **Reversion-flag**: REFINEMENT of the #41 stable-anchor rule (same intent — do not let the pivot
  walk on noise; this closes the wick case that rule's `max(1%, 0.25×ATR)` floor let through). Not
  a reversal of any signed criterion. The 6/28 "flagpole anchor = pivot-anchored" ruling is intact.
  **Status**: shipped, awaiting field validation — verify = a name whose flag pokes a marginal new
  high keeps its pivot/runup on the next `mi_flag_candidates` row (the QLYS shape), and no
  `no_pivot_in_lookback`/base_age regressions in the nightly HTF digest. Shadow-only detector; no
  order path touched. Tests: `test_wick_over_pole_top_does_not_walk_pivot`,
  `test_close_above_pole_top_still_walks_pivot`, `test_close_above_pole_top_then_later_wick_still_walks`,
  `test_pole_still_extending_walks_as_before` (`tests/test_htf_criteria.py`);
  `tests/test_htf_labelled_corpus.py` (HNGE, CDNA replayed through the shipped detector).

- **2026-08-06 — Layer 3b added: STICKY carry bridges the layer-2/layer-3 hand-off hole (#502
  refinement). OPERATOR-SIGNED.**
  **Trigger**: the 2026-07-24 layer-3 change log (below) documented layers 2 and 3 as "complementary
  by deal age." That claim was never verified against production and turned out to be false — a real
  setup (ATAI) leaked through a measured 2-3 session hole between the two layers.
  **Root cause**, session-by-session against the real ATAI cash-buyout (announced 2026-07-16,
  165.6M shares that day vs ~16.6M baseline; price welded $7.15-7.22 since):

  | session after announcement | Layer 3 (fresh) | Layer 2 (mature) median | outcome |
  |---|---|---|---|
  | 07-23 … 07-29 | FIRES (spike 18.3-18.7x) | 0.70-1.73% — no | suppressed correctly |
  | **07-30** | **STOPS** — the 07-16 spike falls out of the 10-session window on session 11 | 0.696% — no | **COILED, leaked** |
  | **07-31** | no | 0.627% — no | **COILED, leaked** |
  | 08-03 | no | 0.523% — no, misses by 0.023pp | (no candidate row) |
  | 08-04 onward | no | 0.453%, 6 sub-0.5 days — WOULD fire | masked by an unrelated ADR gate |

  Precisely: `_FRESH_PIN_VOL_EVENT_DAYS = 10` means the announcement's volume ages out of layer 3's
  own event window on session 11 — and worse, that same volume then falls INTO layer 3's baseline
  window (sessions 11-40), inflating the ADV denominator and dragging the spike ratio down further.
  Layer 2's 10-session median needs until ~session 13 to fall under 0.5%. Sessions 11-12 (calendar
  07-30/07-31) are a genuine hole, not a documentation gap — confirmed live: `mi_flag_candidates`
  shows `mna_filter:deal_pin_fresh` on ATAI 07-23→07-29, then bare **COILED** (no `mna_filter:*`
  reason, i.e. unsuppressed) on 07-30 and 07-31, then `adr_3.0pct_below_4pct` — a DIFFERENT,
  unrelated liquidity gate — from 08-04 onward. **Layer 2 is untested in the field here, not
  proven**: its 08-04 median (0.453%, 6 sub-0.5 days) would have qualified, but the row was already
  marked unqualified by the ADR gate before layer 2 ever got a chance to evaluate it — so this
  incident does not confirm layer 2 would have closed the hole on its own eventually; it confirms
  only that something else happened to mask the symptom from session 13 on.
  **The fix** (mechanism, not a threshold move — none of `_FRESH_PIN_BAND_MAX`,
  `_FRESH_PIN_VOL_SPIKE_MIN`, `_FRESH_PIN_VOL_EVENT_DAYS`, or layer 2's `_DEAL_PIN_RANGE_THRESHOLD`
  moved): `_evaluate_fresh_pin` now re-runs itself (the shipped function, not a parallel evaluator —
  the #416 lesson) on the trailing window for 1..`_FRESH_PIN_STICKY_SESSIONS` (=5) sessions back
  whenever today's own conjunction doesn't fire but today's band still reads ≤ `_FRESH_PIN_BAND_MAX`.
  A hit is carried forward and labelled `sticky_from_session=i`; recursion is guarded to exactly one
  level (a carried lookup never itself tries to carry). The release condition — today's own band
  widening past the max — is the design's whole safety property: no new persistent state exists, so
  there is nothing to leave stale when a deal breaks or price starts moving again. Audited under a
  distinct source string, `deal_pin_sticky`, kept separate from `deal_pin_fresh` so the carry's hit
  rate stays independently reviewable.
  **Evidence**: extended the 2026-07-24 replay's SAME 405-row/89-ticker corpus (2026-05-04 → 07-24,
  frozen — `scripts/probes/_502_bars.tsv`, unchanged) with a NEW extension pull covering 2026-07-25 →
  08-06 (`scripts/probes/_502_bars_ext_20260806.tsv`) — this is NOT the identical corpus the original
  evidence used; it is that corpus plus everything actionable since, confirmed via direct query that
  no COILED/TRIGGERED row for ANY ticker exists in 07-25→08-06 other than ATAI's two leak sessions
  (`mi_flag_candidates` grouped by scan_date/stage, 07-20→08-06). Run against the SHIPPED
  `_evaluate_fresh_pin` (`scripts/probes/_502_fresh_pin_replay.py`):
  - **ATAI 07-30 and 07-31 are now suppressed** — band 0.84% both days (still reads as welded),
    carried from 1 and 2 sessions back respectively. This is the regression the fix targets, closed.
  - **HUM is still preserved** — all 5 HUM rows in the base window remain `is_fresh_pin=False`; every
    HUM band (3.07-10.64%) sits above `_FRESH_PIN_BAND_MAX`, so the release condition exits before
    any carry is attempted. The designated canary is untouched.
  - **The original 11 rows are unchanged** — same 11 rows (ATAI ×2, CCRN ×2, KALV ×4, PAYO ×3), all
    still firing on their OWN data (`sticky_from_session=0`), byte-identical to pre-refinement
    behaviour; the sticky path never engages for rows whose own conjunction already fires.
  - **Net new production-behaviour change: exactly 2 rows** — ATAI 07-30 and 07-31, both hand-checked
    above. One additional row (AVNS, 2026-05-04) picked up a `sticky_from_session=5` fresh-pin flag
    it didn't have before, but AVNS was ALREADY suppressed by the mature rule (`is_pin=True`) both
    before and after this change, and the mature label always wins when both fire — so AVNS's
    production outcome and reason string (`deal_pin_signature`) are unaffected either way. Hand-
    checked, zero behavioural impact, noted for completeness rather than shipped as a "new"
    suppression.
  This is the narrow bridge it was meant to be, not a widened surface: 2 rows change outcome, both
  are the diagnosed leak, and the false-positive population (HUM, the 393 preserved rows) is intact.
  **Known approximation, measured not just asserted**: the carried lookup reuses the caller's already-
  fetched `_PIN_HISTORY_DAYS`-row window, so a carry at offset `i` sees a baseline `i` bars shorter
  than that session's own historical evaluation would have had — the as-of verdict approximates the
  historical day's own verdict rather than replaying it byte-for-byte. A shorter baseline can only
  ever RAISE the computed spike ratio, so in principle a carry could fire where the true historical
  day would not have. This replay measured that risk directly instead of leaving it theoretical: 0 of
  407 rows flipped in that direction (AVNS's fresh-flag changed under the shortened baseline but was
  independently mature-suppressed regardless, so it produced no behaviour change).
  **Anticipated effect**: closes the ATAI-class leak going forward — a fresh pin that ages past
  session 10 while still genuinely welded stays suppressed through session ~15 (5-session bridge with
  margin over the measured 2-3 session hole) instead of surfacing as an actionable COILED/TRIGGERED
  row on the digest.
  **Reversion-flag**: REFINEMENT of the 2026-07-24 layer-3 change directly below — same intent
  (suppress a still-pinned M&A target that geometry alone cannot distinguish from a coil), closing a
  hand-off gap that change's own evidence didn't test for. Not a reversal: every row layer 3 already
  caught keeps firing exactly as before (own-data, `sticky_from_session=0`); the carry only ever adds
  coverage in the specific band-still-holds-but-event-window-elapsed shape.
  **Status**: shipped, awaiting field validation — verify = ATAI (or any future fresh-pin case)
  absent as COILED/TRIGGERED from the rendered nightly HTF digest through the point its own mature-pin
  median would take over. Scope is flag-only (HTF is shadow, no order fires); unchanged from the
  2026-07-24 entry's scope carve-out.
  Tests: `tests/test_flag_fresh_deal_pin_502.py` (bridge, release, bound, fail-open, no-recursion,
  mutation-check — 7 new cases). Replay: `scripts/probes/_502_fresh_pin_replay.py --pull-ext` (base
  window `--pull` is now frozen and should NOT be re-run — see the script's own docstring for why).

- **2026-07-24 — Layer 3 added: FRESH deal-pin suppression (#502). OPERATOR-SIGNED.**
  **Trigger**: operator, 2026-07-24 — the nightly HTF digest surfaced `ATAI` as the single 🌀 COILED
  actionable setup; ATAI is a buyout. Root cause: a cash-deal pin is indistinguishable from a coil on
  geometry, and *both* existing layers structurally cannot reach a FRESH pin. Layer 1 found nothing —
  Polygon returned 2 ATAI articles in 21 days, neither carrying an M&A keyword (the #416 guards are NOT
  implicated; nothing ever matched, so nothing vetoed). Layer 2 needs a 10-session median under 0.5%,
  which a 6-session-old deal cannot reach — ATAI's median was 1.735% with 1 sub-0.5% day.
  **Evidence**: 405-row replay of every historical COILED/TRIGGERED row using the SHIPPED
  `_evaluate_fresh_pin` (not a lookalike sim — the #416 lesson), window 2026-05-04 → 07-24, 89 tickers.
  11 rows / 4 tickers suppressed (ATAI ×2, CCRN ×2, KALV ×4, PAYO ×3); **393 preserved**, including
  `HUM` — the nearest non-pin by band (3.07%) — which went on to **+25.7%** over the next 20 sessions.
  The two populations do not overlap: every fresh pin ≥ 12.6× spike, every non-pin ≤ 2.9×. Band ∈
  {2.0, 2.5, 3.0} crossed with spike ∈ {5×, 10×} all select the same 11 rows, so neither threshold is
  load-bearing. Prior measured behaviour: layer 2 had fired **5 times in its lifetime** and caught KALV
  ~29 days *after* KALV's first 4-session COILED leak; ATAI/CCRN/PAYO leaked and were never caught.
  ⚠ **Single-regime limitation** — that window is one regime. Per the #454 finding that the kill/scale
  envelope was silently bull-conditional, this calibration carries the same caveat and is due a re-cut
  at the quarterly band review.
  **Also tested and NOT shipped**: reusing the EP Claude-classifier `catalyst_quality='mna'` verdict.
  It is not in `mi_ep_alerts` (the filter suppresses before the alert row is written) and the audit-log
  store is 1-true/1-junk on N=2 — `ACLS` was graded `mna` while its own summary read "No recent news or
  catalysts found", then ran $164 → $191. The guards cannot discriminate (`matches_mna_keywords`
  returns `None` for ATAI too). Filed under #416; N=2 is below the bar to ship it *or* to close it.
  **Anticipated effect**: ~11 actionable rows suppressed per ~3 months (of 405). ATAI leaves the board.
  Layer 2's own hit rate is unchanged — layer 3 is purely additive; where both fire, the mature label
  wins (3 KALV rows). New audit source string `deal_pin_fresh` alongside `deal_pin_signature`.
  **Reversion-flag**: REFINEMENT of the 2026-05-11 deal-pin-signature change. Same intent — catch
  zero-news M&A targets by price signature; the prior statistic is correct for mature pins and simply
  has no reach on fresh ones. Not a reversal: nothing layer 2 catches is given up.
  **Status**: shipped, awaiting field validation — verify = ATAI absent as COILED from the rendered
  nightly HTF digest. Scope is flag-only (HTF is shadow, no order fires); extending the conjunction to
  EP/9M would change detection on money paths and was deliberately excluded.
  Full evidence: `docs/analysis/htf_deal_pin_fresh_2026-07-24.md`; replay:
  `scripts/probes/_502_fresh_pin_replay.py`.

- **2026-07-24 — FL-5 reconcile: doc synced to code (missing change-log entry added).** `_HISTORY_DAYS`
  is **380**, not 260 — the 6/27 entries below say "90→260" but the code moved a third time, same day,
  in a follow-up commit (`1f2f7a8`) that was never logged here: `get_recent_daily_history` filters by
  CALENDAR days, not row count, so `_HISTORY_DAYS=260` calendar only yielded ~178 TRADING rows (< 200) —
  `sma_200` silently came back `None` and the 200MA Stage-2 gate (added earlier that same day, see
  below) never actually fired; the near-high gate alone was carrying NCI's rejection. Bumped 260→380
  calendar (~261 trading rows via the ~0.685 trading/calendar-day ratio) so the 200MA check fires for
  real — reverified live: AGL 3.68× above / XMTR 1.59× / NCI 0.66× BELOW (now caught by BOTH the 200MA
  and near-high gates). Advisor-caught 6/27, same day as the Stage-2 gate ship below. No code change in
  this reconcile — doc-only correction + backfilled change-log entry.

- **2026-07-19 — Doc cross-ref only: ADR 0026 D1 / card C4 (flag_continuation retirement).**
  **Trigger**: `#354`/ADR 0026 card C4 rewrote `flag_continuation.md` to document its retirement as a
  standalone strategy and absorption as the Confirm(b) entry; added a pointer here for discoverability.
  **Evidence**: N/A — no detection-criterion, gate, or code change in this file; pure cross-reference.
  **Anticipated effect**: none in production. **Reversion-flag**: NEW (doc-only addition, nothing
  reversed). **Status**: shipped 2026-07-19.

- **2026-07-18 — ADV liquidity floor: MEAN → MEDIAN (bugfix, #402(2)).**
  **Trigger**: #402 /simplify code review found `compute_flag_metrics`'s liquidity gate computed ADV as
  `sum(volume)/len` (mean) while every other ADV computation in this codebase — `db.get_adv_from_daily_closes`
  (the cited SSoT, `PERCENTILE_CONT(0.5)`), `rs_engine`, `ep_detector`, and this SAME file's own #94
  intraday-break-scan query (which already comments "matching db.get_adv_from_daily_closes SSoT — median
  is spike-immune") — uses median. **Evidence**: internal consistency, not a new threshold — the
  `_HTF_MIN_ADV_SHARES=500_000` floor value is unchanged; only the aggregation method computing the
  statistic compared against it was wrong. **Anticipated effect**: stricter for spike-influenced tickers —
  a ticker whose trailing-20d volume includes one large block-trade/climax day could previously clear the
  floor on an inflated mean; the median now reflects steady-state liquidity, so those borderline names may
  newly reject (`adv_Xk_below_500k_shares`). No effect on tickers without a volume spike in the window.
  **Reversion-flag**: NEW (bugfix — first correction of this specific bug, not a reversal of a signed
  threshold call). **Status**: shipped, awaiting field validation. No N≥10 P&L backtest — this detector is
  shadow/telemetry-only (no money); see the 6/27 entry below for the same carve-out. Test:
  `test_adv_floor_uses_median_not_mean_spike_robust` (`tests/test_htf_criteria.py`).

- **2026-06-27 — Sourced HTF rebuild (replaces the n=1 50/60).** Flagpole 50%/60d → 90%/40d; flag depth
  off-pivot-close-20%-(scaled-to-35%) → absolute-low ≤25% flat; ADDED the 10/20/50 Stage-2 trend filter,
  the flagpole data-artifact guard + pole-volume confirmation. #80 runup-scaling removed (reason above).
  Reversion-flag: REFINEMENT (an unsourced n=1 → the sourced literature; not a reversal of a signed call).
  Gate: spec-correctness (tests/`test_htf_criteria.py`) + `/flags` eyeball + operator sign-off (sourcing).
  NO N≥10 P&L backtest (the alert-only detector touches no money; the money breakout-entry validates
  separately shadow→paper→live). Refs #356, `docs/roadmap/family_a_setups_split_2026-06-22.md`.

- **2026-06-27 (eyeball catch) — Stage-2 long-term gate added (operator: "NCI is not valid").** The
  10/20/50 alone PASSES a sharp crash-recovery (the short MAs catch up fast): NCI spiked $110 → crashed
  $4 → bounced to $11 (−90% from its high, BELOW the 200d) and read as a "221% flagpole" that was a
  dead-cat bounce. Added the spec's "Stage-2 uptrend" long-term gate — `close ≥ 200d MA` AND
  `pivot_high ≥ 75% of the 52w high` — and extended `_HISTORY_DAYS` 90→260 (a 200MA/52w-high needs ~250d;
  **superseded same-day, 260→380 — see the 2026-07-24 entry above, `_HISTORY_DAYS` is 380 in code**).
  Confirmed on the live eyeball: AGL (100% of 52w high, 4.32× 200MA) + XMTR (95%, 1.70×) KEPT; NCI (10%,
  0.81×) REJECTED. Test: `test_crash_recovery_rejected_stage2`.

> Supersedes the criteria section of `docs/setups/flag_continuation.md` (the generic-flag definition).
> See also `docs/decisions/0026-consolidation-family-unification.md` §D1 (card C4, 2026-07-19): the
> Family-A 3-way split — **HTF is the *setup*** (this file, unchanged); **Confirm is the *entry*** (the
> consolidation family's base-high breakout, `anticipation.py::confirm_signal_at`, SHADOW-only, documented
> in `flag_continuation.md`); Anticipation is the third (in-coil) entry. No criteria here changed.
