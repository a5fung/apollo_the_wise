## CARD #210 — one Sonnet build: the TradingView shadow gets a time frame, a proven story matcher, a corpus for every graded candidate, every alert as a candidate, and a 10:10 ET slot

**Model:** Sonnet. **Deploy scope:** `bash scripts/deploy.sh market-agent` (every file below is market-agent; nothing in `broker/`). **Window:** weekend (unrestricted) — target Sat/Sun 2026-10-10/11 PT so the first 10:10 ET run is Mon 2026-10-12. **Spend:** $0 at build and run time (no model calls anywhere in this card).

🛑 **THE LINE.** Everything here is telemetry. The new table and the new shadow columns are read by NO grading, admission, scoring, entry, sizing or safeguard path; the one write added to the scan (Part 3) is a fail-open INSERT beside an existing audit INSERT and changes no grade. No threshold, no strategy, no money is touched. If any step below seems to require touching a grade or a trade path, STOP — the card is wrong, not the rule.

**No design decisions remain.** Every rule is stated once, in code, in `scripts/probes/_wk1010_210/tv_story_matcher.py`, and proven against `fixture_cases.json` by `run_fixture_proof.py` (50 assertions, 0 failures, `run_fixture_proof.out`). The card PORTS; it does not tune. Anything that looks like a judgment call goes back through the fixture (add a case, re-run the proof, THEN change code) — never into the port as a quiet tweak.

### Files

| File | Change |
|---|---|
| `agents/market_intelligence/tv_news_shadow.py` | Part 1 frame in `build_shadow_row`; Part 2 matcher functions + constants pasted VERBATIM from `tv_story_matcher.py` (names kept); module docstring: slot 10:10 ET, the two-list rule, the period-start reach test |
| `agents/market_intelligence/db.py` | Part 3 DDL `mi_ep_grade_corpus` + `write_grade_corpus` + `get_grade_corpus`; Part 4 `get_tv_shadow_population` (replaces `get_no_catalyst_alert_population`); shadow `ALTER TABLE … ADD COLUMN IF NOT EXISTS` ×11; `_TV_NEWS_SHADOW_COLS` / `_TV_NEWS_SHADOW_JSONB_LIST_COLS` extended |
| `agents/market_intelligence/ep_detector.py` | Part 3 writer call beside the `ep_catalyst_provenance` audit call (~5047–5060) |
| `agents/market_intelligence/scheduler.py` | `tv_news_shadow` CronTrigger 20:45 → **10:10 ET** mon-fri + the comment block above it + `_tv_news_shadow_job` docstring |
| `tests/test_210_tv_news_shadow.py` | +11 tests (below, every one failing on today's code); 2 existing tests rewritten (named below); the other 44 unchanged |
| `tests/test_tv_news_shadow_null_semantics.py` | the three NULL/[]/list tests parametrised over BOTH list columns |
| `tests/fixtures/tv_shadow_210_cases_2026-10-10.json` | `cp scripts/probes/_wk1010_210/fixture_cases.json` — byte-identical, never edited by hand |
| `docs/analysis/210_tv_miss_read_2026-10-10.md` | nothing — the analysis stays; the card is its §10 |

### Part 1 — the comparison frame (`tv_news_shadow.build_shadow_row`)

Port `build_frame` from `tv_story_matcher.py` into `build_shadow_row`, keeping every existing column. New inputs: `corpus["captured_at"]` (TIMESTAMPTZ, from Part 3's reader) and `corpus["company_name"]` (TEXT or None).

- **Period start** = 16:00:00 ET on the prior NYSE TRADING day: `prior_trading_day_holiday_aware(alert_date)` (ported; steps back one day at a time until `trading_calendar.get_market_status(d).is_trading_day`). ⚠ NOT `shared.dates.last_trading_day` — it is weekend-only (its own docstring says so): for ERO 2026-09-08 it returns Labor Day 09-07. One calendar call per candidate; it logs one INFO line, acceptable.
- **Same-day items** = `is_same_day_item(published_et, alert_date, prior_trading_day)` (existing function, unchanged) — ET date == alert_date, or prior trading day ≥ 16:00 ET.
- **Three buckets over same-day items** (INT columns): `tv_items_before_grade` = `published <= captured_at` · `tv_items_in_repoll_window` = `captured_at < published <= 10:00:00 ET on alert_date` (`_TV_ACTIONABLE_CUTOFF_ET = time(10, 0)`: the scan's last tick and the 10:00 ET unfilled-cancel) · `tv_items_after_cutoff` = later. With the job at 10:10 ET the third bucket holds at most the 10:00–10:10 items — informational only.
- **Reach** `tv_coverage_reaches_period_start` = `oldest item of the WHOLE window <= period_start`. ⚠ NOT `oldest <= captured_at`: that leaves 16:00-ET-to-oldest unseen and would record `[]` over it (a 06:59 oldest vs a 07:01 capture reads "reaches"; ACN's 09:31 oldest vs 07:10 capture would too). `tv_unseen_minutes_at_period_start` = 0 when reaching, else `ceil((oldest − period_start) / 60s)` (ACN 1052, MSTR 38, PENG 7 on the captured rows). Keep `tv_coverage_reaches_alert_date` as is for continuity.
- **Two lists, one rule.** `tv_items_unmatched_seen` (JSONB) = the `none` and `class` items of the first two buckets, each `{"title","provider","published","bucket","class","match"}` — written whenever a diff is possible (`corpus` present and `captured_at` present), whatever the reach. `tv_items_we_missed` (JSONB, the DoD column) = that same list when `tv_coverage_reaches_period_start` is True, else **NULL** ("cannot tell"). An empty `tv_items_we_missed` is an honest zero; one may never appear on a non-reaching window (that is the 2026-09-08 false zero returning).
- `tv_match_summary` (JSONB) = `{"before_grade": {verdict: n}, "repoll_window": {…}, "after_cutoff": {…}}` over every bucketed item; its counts sum to the three buckets (asserted).
- `corpus is None` → every new column NULL (as today). `corpus` present but `captured_at` None cannot happen through Part 3's reader (both sources carry a timestamp); treat it as `corpus is None` for the diff columns and log a warning.

### Part 2 — the story matcher (port `tv_story_matcher.py` verbatim)

Functions and constants to paste with their names: `STOPWORDS`, `CLASS_WORDS`, `GENERIC_WORDS`, `CATALYST_CLASS_PATTERNS`, `CATALYST_CLASSES`, `COMMENTARY_STRONG_RE`, `COMMENTARY_WEAK_RE`, `PREVIEW_RE`, `_ANALYST_VERBS`, `_CAP`, `_FIRM_HEAD_RE`, `_FIRM_TAIL_RE`, `_USD_RE`, `_PCT_RE`, `_FY_RE`, `_UNIT`, `catalyst_classes`, `is_commentary`, `is_preview`, `primary_class`, `holds_a_catalyst`, `company_tokens`, `_num`, `numeric_anchors`, `alpha_anchors`, `analyst_firm`, `period_start`, `prior_weekday`, `prior_trading_day_holiday_aware`, `match_tv_item`, `build_frame`. `normalize_title` and `is_same_day_item` already exist in the module — do not duplicate them.

`match_tv_item(tv_title, our_items, *, alert_date, prior_trading_day, company) -> (verdict, matched_title | None)`, verdicts in this order:

| verdict | rule (anchor-first — WHAT is shared decides, never HOW MUCH) | fixture that pins it |
|---|---|---|
| `title` | `normalize_title` equality (today's rule, kept first) | BFLY filler item |
| `story` | same NON-earnings catalyst class on both sides **and** a shared anchor; for `analyst` the anchor must be the FIRM (`analyst_firm`: capitalised run before an analyst verb, else after by/at/from); two items both carrying $ figures that share none are not the same story | PENG Cumming ×3 → our CFO wire; Needham ×2 → our Needham; Stifel (Dow Jones tail template) → our Stifel; Needham $85 vs Stifel $85 → NOT story |
| `event` | an earnings-class item on a day we hold an earnings RESULTS item (not a preview: `is_preview`) — one company reports once a day | PENG "Q4 Earnings Call Highlights" → our transcript; ACN Reuters results summary → our Q4 wire (control) |
| `move` | commentary-only title (no catalyst class) on a day we hold any non-preview catalyst item | PENG "Why Is PENG Stock Rising…" |
| `class` | same class among our same-day items, but no anchor proves the same story (second analyst, second contract, results vs our preview) | Rosenblatt vs Stifel; ACN_PREVIEW Reuters results vs our preview |
| `none` | nothing above | BFLY Business Wire release; ACN TradingView consensus PT |

`our_items = [{title, published (ET-aware or None)}]` from Polygon + Alpaca + FMP; an undated FMP item counts as same-day (it came from the grade-time fetch). `company` = `company_tokens(company_name, ticker, our_titles)`: the stored `company_name` when the grade-corpus row has one, else the frequency fallback (a token in ≥3 of our titles, ≥2 when we hold <6). ⚠ The fallback over-includes (ACN: `micron`, `watch`; PENG: `beat`, `eps`) — that only REMOVES anchors, so it can only make matching stricter; it is what metrics-only rows get.

Fixture: copy `fixture_cases.json` unchanged. Every title and time is a real capture except the two BFLY TradingView times (labelled `published_is_synthetic`) and the one re-dated item in `ACN_PREVIEW` (labelled). `expected` holds the exact numbers the tests assert.

### Part 3 — a corpus row for EVERY graded candidate (new table `mi_ep_grade_corpus`)

DDL (db.py, beside the `mi_tv_news_shadow` DDL, line ~793 idiom):
```sql
CREATE TABLE IF NOT EXISTS mi_ep_grade_corpus (
    ticker          TEXT NOT NULL,
    alert_date      DATE NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,   -- when the grade read this corpus (= the provenance row's time)
    company_name    TEXT,                   -- profile.get("companyName") — Part 2's company tokens
    alpaca_json     JSONB,                  -- alpaca_news verbatim (<= 20 items, 7-day)
    fmp_json        JSONB,                  -- fmp_news verbatim
    perplexity_text TEXT,
    sec_title       TEXT,                   -- form + filed + items ONLY, never the body
    raw_grade       TEXT,                   -- catalyst_quality at this point: the RAW LLM grade
    PRIMARY KEY (ticker, alert_date)
);
```
- **Writer** `db.write_grade_corpus(ticker, alert_date, captured_at, company_name, alpaca_json, fmp_json, perplexity_text, sec_title, raw_grade)` → `INSERT … ON CONFLICT (ticker, alert_date) DO NOTHING` — the FIRST grade's corpus is the one the grade saw. Called in `ep_detector.py` in the uncached grade branch, in its own `try/except Exception → logger.warning`, immediately after the `log_audit_event("ep_catalyst_provenance", …)` call (~5047–5060); `captured_at = datetime.now(_ET)` at that point. Inputs already in scope from the gather at ~4945: `alpaca_news`, `fmp_news`, `perplexity_answer`, `sec_filing` (`f"{form} filed {filed}, items {items}"` or None), `profile.get("companyName")`, `catalyst_quality` (raw). **No new fetch. Polygon is NOT in that gather** (it is fetched only inside `extract_earnings_metrics`), so a grade-corpus row has no Polygon side.
- ⚠ **It fires once per GRADED CANDIDATE, not per alert**: 28–49 graded ticker-days a week since 09-01 (q1_read.out Q9: 28, 34, 34, 37, 39, 49) against 3–10 alerts a week — ~40 small rows a week, one INSERT each, the same class as the audit INSERT beside it. No toggle: a write that cannot change a grade needs no kill switch beyond its try/except.
- ⚠ Do NOT write corpus-only rows into `mi_ep_catalyst_metrics`: `lookup_cached_metrics` reads that table as "extraction ran".
- **Reader** `db.get_grade_corpus(ticker, alert_date) -> dict | None` replaces `get_catalyst_metrics_raw_corpus` in `snapshot_ticker`. Returns `{raw_polygon_news_json, raw_alpaca_news_json, raw_fmp_news_json, raw_perplexity_text, captured_at, company_name, polygon_available, source}`: read BOTH rows; `source='grade_corpus'` when that row exists (its `captured_at` is the grade time — `mi_ep_catalyst_metrics.extracted_at` lags it: ACN extracted 07:10:15 for a 07:00:20 grade), taking `raw_polygon_news_json` from the metrics row when present (`polygon_available=True`) else None (`our_polygon_count` stays NULL, never 0); `source='metrics'` with `captured_at=extracted_at` when only the metrics row exists (today's 5 rows); None when neither exists. Shadow stores `our_corpus_source TEXT`.

### Part 4 — the population (`db.get_tv_shadow_population(since_date, today)` replaces `get_no_catalyst_alert_population`)

- Every `mi_ep_alerts` ticker-day in `[since, today]` not yet in `mi_tv_news_shadow`. **Drop the raw-grade predicate** — the DoD says "share of alerts", and this is telemetry (decided, not an operator question).
- Carry per row: `catalyst_quality` = RAW grade from the `ep_catalyst_provenance` row (None when absent — keep the row, do not drop it), `has_direct_source`, `source_class_count` (as today); NEW `acting_grade` = `mi_ep_alerts.catalyst_quality`; NEW `acting_rule` = `mi_catalyst_tier_shadow.rule_last` via `LEFT JOIN … ON t.ticker = a.ticker AND t.scan_date = a.alert_date` (None when absent). Shadow stores them as `our_acting_grade TEXT`, `our_acting_rule TEXT`.
- **The "no-catalyst days" cut uses the RAW grade**: `catalyst_quality = 'routine' OR NOT our_has_direct_source` — on 6 of the 10 captured rows (CIFR, MSTR, ITUB, NU, PBR, AAOI) the acting `strong` is the lattice's `routine_promoted_demotion_corrective`, a demotion-corrective promotion, not a company catalyst (q3_lattice.out). The acting grade is carried so a second cut is one WHERE clause away.
- `_TV_MAX_FETCHES_PER_RUN = 20` already covers the busiest week seen (10 alerts, w/c 10-05); `_TV_LOOKBACK_DAYS = 3` unchanged.

### Part 5 — the slot: 10:10 ET mon-fri (was 20:45)

Change `CronTrigger(hour=20, minute=45, …)` → `CronTrigger(hour=10, minute=10, day_of_week="mon-fri", timezone="America/New_York")` on `id="tv_news_shadow"`; keep `misfire_grace_time=1800`. Rewrite the scheduler comment and `_tv_news_shadow_job`'s docstring (they cite 20:45 and the EOD recorders); the module docstring's "never runs 07:00–10:00 ET or 09:31–09:44 ET" stays TRUE and stays.

Why 10:10, from the captures: (a) the doc's own trigger is met — 3 of 10 windows at 20:45 do not reach the period start (MSTR 38 unseen minutes, PENG 7, ACN 1052 — the three most heavily covered names); (b) the rolling window is ~25 items, and at 20:45 ACN's had spent 23 of 25 slots on items published after 10:10 ET, PENG's 6 of 25 — at 10:10 those slots hold earlier items instead; (c) 10:10 is the earliest slot after which the before-grade and re-poll buckets are complete: the scan's last tick is 10:00, the latest grade seen is 09:55 (ERO 09:55:22, KARD 09:55:14), and the worst grade→metrics-row lag seen is 10 min (ACN 07:00:20 → 07:10:15), so 10:10 sees the last tick's rows; (d) no job is registered at 10:10 (10:00: `ep_scan_stop`, `rt_miss_digest`, `orb_window_cleanup`, `shadow_orb_entry`; 10:05: `ep_scan_watchdog`), and it is clear of the 12:00–13:00 ET deploy window. What is given up: `tv_items_after_cutoff` shrinks to the 10:00–10:10 items, so "what the day's coverage became" is no longer read — it was never the question. What the captures cannot show: whether a mega-cap's window reaches 16:00 the prior day even at 10:10 — `tv_unseen_minutes_at_period_start` measures exactly that on the first rows.

### Shadow columns (`ALTER TABLE mi_tv_news_shadow ADD COLUMN IF NOT EXISTS`, db.py:450 idiom)

`our_captured_at TIMESTAMPTZ`, `our_corpus_source TEXT`, `our_acting_grade TEXT`, `our_acting_rule TEXT`, `tv_coverage_reaches_period_start BOOLEAN`, `tv_unseen_minutes_at_period_start INT`, `tv_items_before_grade INT`, `tv_items_in_repoll_window INT`, `tv_items_after_cutoff INT`, `tv_match_summary JSONB`, `tv_items_unmatched_seen JSONB`. Add all eleven to `_TV_NEWS_SHADOW_COLS`; add `tv_items_unmatched_seen` to `_TV_NEWS_SHADOW_JSONB_LIST_COLS` so the existing ⚠ PRESERVE NULL branch (db.py ~18602) covers BOTH lists. ⚠ Do NOT put `tv_match_summary` in `_TV_NEWS_SHADOW_JSONB_DICT_COLS` — that branch coerces None → `{}`, which would store "not computed" as "computed, empty" (the 09-08 class again); add a `_TV_NEWS_SHADOW_JSONB_NULLABLE_DICT_COLS = frozenset({"tv_match_summary"})` handled as `_jsonb_param(v) if v is not None else None`, and include it in `_jsonb_value_list`'s jsonb column sets. `catalyst_quality` keeps the raw grade (continuity with the 10 existing rows).

### Tests — `tests/test_210_tv_news_shadow.py` (new, all FAIL on today's code: `fails_on_today.out`)

Each loads `tests/fixtures/tv_shadow_210_cases_2026-10-10.json`, builds `our_items` from `our_corpus` (ISO → ET-aware; FMP `null` → None), `company = company_tokens(None, ticker, our_titles)`, and runs `build_shadow_row` with a fake payload `{"items": case["tv_items"]}` and a corpus dict carrying `captured_at` — exactly what `run_fixture_proof.py` does with `build_frame`.

1. `test_match_tv_item_is_importable_with_its_constants` — imports every name in the Part 2 list (ImportError today).
2. `test_acn_rolled_window_is_null_with_buckets` — ACN: 0 / 1 / 24; reach False; unseen 1052; `tv_items_we_missed is None`; `tv_items_unmatched_seen == []`; `tv_match_summary["repoll_window"] == {"event": 1}` (KeyError today).
3. `test_acn_results_summary_is_the_event_we_held` — `match_tv_item(Reuters summary, [our Q4 EPS wire])[0] == "event"` (the control for test 6).
4. `test_peng_every_seen_item_is_a_story_we_held` — PENG: 17 / 1 / 7; reach False; unseen 7; `tv_items_we_missed is None`; `tv_items_unmatched_seen == []`; every verdict in the first two buckets ∈ {title, story, event, move} (18 items); the four `must_match_as_held` pairs.
5. `test_same_target_different_firm_is_class_not_story` — Rosenblatt $100 vs Stifel $85 → `class`; Needham $85 vs Stifel $85 → `class`.
6. `test_preview_on_our_side_does_not_absorb_the_results` — ACN_PREVIEW: `tv_items_unmatched_seen` = [Reuters summary] with `match == "class"`; `tv_items_we_missed is None`; `match_tv_item(Reuters summary, [the re-dated preview])[0] == "class"`.
7. `test_bfly_unmatched_item_survives_in_the_repoll_bucket` — BFLY: 0 / 1 / 1; reach True; unseen 0; `tv_items_we_missed` = [Business Wire release] with `bucket == "repoll_window"`, `match == "none"`, `class == "other"`; the Stocktwits piece absent from both lists; the filler matched `title`.
8. `test_period_start_is_the_prior_nyse_trading_day` — `prior_trading_day_holiday_aware(date(2026, 9, 8)) == (date(2026, 9, 4), "nyse_calendar")`; `period_start(…)` == 2026-09-04 16:00 ET. (Today's `last_trading_day` gives 09-07.)
9. `test_grade_corpus_write_is_fail_open` — `write_grade_corpus` with a `get_pool` that raises → returns without raising, `logger.warning` called (monkeypatched).
10. `test_population_is_every_alert_with_both_grades` — mocked `conn.fetch` rows: 3 alerts, 2 with a provenance row, 1 with a lattice row → 3 rows returned; `catalyst_quality` None on the one without provenance; `acting_grade` from the alert on all 3; `acting_rule` only on the one with a lattice row; no row dropped for being `strong`.
11. `test_shadow_job_is_registered_at_1010_et` — read the `tv_news_shadow` job's trigger from the scheduler source (regex on the `id="tv_news_shadow"` block): hour 10, minute 10.

Existing tests that CHANGE (2, named): `test_our_corpus_available_flags_the_item_we_never_held` (its window's oldest item is 08:05 on the alert date → under the corrected rule the DoD column is NULL; rewrite it with a filler item before 16:00 ET the prior day and a `captured_at` of 07:01, asserting the miss in BOTH lists with `match == "none"`), and `test_our_corpus_unavailable_records_same_day_items_without_a_diff` (assert the eleven new columns are None too). The other 44 of today's 46 (`existing_tests_baseline.out`) stay green unchanged; `test_tv_news_shadow_null_semantics.py`'s three tests run over both list columns.

### Pre-registered expectations (write into the #210 PLAN line BEFORE the deploy; baseline = the captures of 2026-10-10)

BASELINE: 10 shadow rows; 3 with a corpus (`tv_items_we_missed` not NULL) in 5 weeks = 0.6 a week; 2.0 candidates a week; 5 of 32 alerts since 09-01 have any corpus; 7 of 10 windows reach the period start at 20:45; `mi_ep_grade_corpus` does not exist.

- **EXPECT** over the first 4 weeks after deploy (~20 alerts at 5.3 a week): `mi_ep_grade_corpus` gains a row for ≥ 95% of graded candidates each morning (28–49 a week per q1_read.out Q9; the writer is fail-open so a few may drop, each with a warning in the log); candidates ≥ 4 a week (every alert); ≥ 80% of rows with TradingView coverage reach the period start at 10:10 (baseline 70% at 20:45 — the slot's positive observable); every row with a corpus carries `our_captured_at`, three bucket counts summing to `tv_items_on_alert_date`, and a `tv_match_summary` whose counts sum to the buckets; readable rows ≥ 3 a week. **UNINTENDED, watched together:** `tv_items_unmatched_seen == []` on EVERY row after 20 rows (the matcher is too loose — BFLY is its only `none` guard); `mi_ep_grade_corpus` write warnings on > 5% of grades (writer broken); any change in the 07:00–10:00 scan's tick duration (one INSERT must not be visible); `tv_coverage_reaches_period_start` false on > 20% of rows at 10:10 (the slot did not help; the unseen-minutes column says by how much).
- **DONE-WHEN:** 20 rows with `tv_items_we_missed` not NULL. Report, with n: strict share (rows with ≥ 1 `match='none'` item in the **before-grade** bucket) and loose share (`none` + `class`), each split by raw grade and by acting grade; the re-poll window separately (that bucket is the #344 class — BFLY's release reached our own Alpaca/Benzinga feed at 08:12 ET per `docs/analysis/missed_ep_bfly_2026-06-18.md`, so it is not "TradingView had what our feeds never carried"); and confirmed unmatched items on rolled windows (`tv_items_we_missed IS NULL AND jsonb_array_length(tv_items_unmatched_seen) > 0`) as a separate line.
- **WOULD-FAIL-IF:** a `[]` in `tv_items_we_missed` on a row with `tv_coverage_reaches_period_start = false` (the false zero back); a corpus row whose buckets do not sum to `tv_items_on_alert_date`; `mi_job_runs` shows `tv_news_shadow` starting at 20:45 after the deploy; `mi_ep_grade_corpus` gains < 20 rows in the first full week; a `tv_items_we_missed` item without a `match` tag.
- **VERIFY-LIVE (Mon 2026-10-12, after 10:15 ET; PT morning):** `mi_job_runs` row for `tv_news_shadow` started 10:10 ET with status success; `mi_ep_grade_corpus` row count for 10-12 equals the day's `ep_catalyst_provenance` ticker-day count (±5%); every 10-12 shadow row with a corpus has the eleven new columns non-NULL except where the rule says NULL; read ONE 10-12 row with TradingView coverage by hand against its `tv_match_summary` and `tv_items_unmatched_seen` and record the check in the PLAN line. Positive observable: the three bucket counts and the summary — a broken writer leaves NULLs, a broken frame leaves sums that do not add up.

### The readout (run at DONE-WHEN; one SELECT, captured once)
```sql
SELECT our_acting_grade, catalyst_quality AS raw_grade,
  count(*) FILTER (WHERE tv_items_we_missed IS NOT NULL) AS readable,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(tv_items_we_missed) i
                   WHERE i->>'bucket'='before_grade' AND i->>'match'='none')) AS strict_before_grade,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(tv_items_we_missed) i
                   WHERE i->>'bucket'='before_grade')) AS loose_before_grade,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(tv_items_we_missed) i
                   WHERE i->>'bucket'='repoll_window' AND i->>'match'='none')) AS strict_repoll,
  count(*) FILTER (WHERE tv_items_we_missed IS NULL AND tv_items_unmatched_seen IS NOT NULL
                   AND jsonb_array_length(tv_items_unmatched_seen) > 0) AS rolled_with_confirmed_unmatched
FROM mi_tv_news_shadow
WHERE tv_status = 'ok' AND our_captured_at IS NOT NULL
GROUP BY 1, 2 ORDER BY 1, 2;
```

### Not in this card
No second fetch, no re-poll of the window, no Stocktwits, no change to `should_repoll_shadow`, no edit to any grade/admission path, no PLAN.md edit by the card (the orchestrator writes the EXPECT block into the #210 line before deploy), no model calls.
