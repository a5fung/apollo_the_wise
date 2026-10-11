# #700 — the Sunday weekly review: cut the noise, keep what informs (design + build spec)

**DESIGN ONLY (read-only, 2026-10-11).** Telemetry / reporting change — no strategy, sizing,
safeguard, grade or trade-state path is touched (THE LINE). Every metric stays computed and stored
in `mi_system_reviews` exactly as today; only what the Telegram message renders changes.

**The answer:** the 10-11 fold (12,257 chars, 38 identical "quiet" fragments, three "anomalies" that
were all false alarms) renders under this spec at **~5,450 chars steady state (45%) / ~5,800 on the
first run (48%) by hand; the built renderer measures 6,315 chars with last week's row to compare (51%)
and 6,968 with none (57%)** - the review-fix round (§10) put the L2 bullet back in front of him with every surface still named on the head's one "Also checked" line, and nothing
dropped from the data. Hand render: §8 and `scripts/probes/_700_review_noise/preview_1011_by_hand.md`.

His ask (2026-10-11): *"given the sunday review wrote so much text and none of it is actionable, is
there room to improve it and reduce noise?"* His rule, verbatim: *"even if something doesnt need me,
if it's informative it can still include so don't need to remove everthing but remove noise as much
as possible."* Baseline (what he received, section by section, with what was true when checked):
`scripts/probes/_700_review_noise/baseline_2026-10-11.md`.

Evidence captured ONCE, read-only (`ssh apollo@… psql`): `q1_reviews.out` (the stored 10-11 / 10-04 /
09-27 rows — summary + metrics), `q2_sizes.out` (fold-size history), `q3_render_inputs.out` (the
inputs of the sections computed at render time: live cohort, setup rows, 2nd-opinion counts, MTD
spend, last week's gap keys); `check_settle_rule.py` runs §4's rule over both weeks' stored bullets.
All under `scripts/probes/_700_review_noise/`.

---

## 1. The four rules the renderer applies (from his definitions)

| rule | meaning in code |
|---|---|
| **INFORMATIVE → keep, compact** | a result WITH its conclusion, a number that changed materially vs last week or crossed a bar, a first-ever event, a new section's readout (#486, #313), a live-money P&L fact. Rendered in plain words, max lines per section fixed below. |
| **UNCHANGED → one phrase, not a block** | a status block whose decision inputs equal last week's (crypto verdict, band, promotion rows, winner capture) prints ONLY on the head's "Also checked" line under *unchanged since last week:*. The block itself goes to the stored full text. |
| **REPEATED → one line** | audit-error rows collapse to one line per event type (count · disposition · first–last time · "none since Nd" · the common cause). Live rows still print individually (they are in the head anyway). |
| **UNVERIFIED → never a finding** | the narrative's "anomalies to verify" are checked by the job against the record it already holds; what the record settles is said so in one line, what it cannot settle is MY work: a head count under *Needs me* and the bullets under a *To verify (mine)* heading, never under a finding heading. |

Boilerplate (legends, era keys, ⓘ caveats, "telemetry only" footers, explainer lines, the calibration
card, the cost-envelope block the head already summarises) leaves the message. Pointers stay where a
reader needs one ("full table: full text").

**Nothing is deleted from the data.** `metrics` is stored as today (including `audit_errors.dispositioned`
and `report.suppressed`, uncollapsed). The full, uncompacted rendering is ALSO stored
(`report.full_md`) so "full detail stays reachable" = the stored row, printed by the preview probe
(`--full`). No new Telegram command (three-places rule; out of scope — see §11).

---

## 2. What changes in `system_review.py` — the shape

```
run_weekly_review
  prior = get_latest_system_review(window_days, on_or_before=window_start)   # §6 — NOT "latest"
  summary = _synthesize(metrics, prior)            # prompt UNCHANGED; prior_block strips metrics["report"]
  head, fold, report = _assemble_report(metrics, summary, window_start, today, prior=prior)
  metrics["report"] = report       # + snapshot, full_md, head_md, fold_md, changes (§6)
  insert_system_review(...)        # as today
  send(render_review_html(head, fold))  # as today
```

`_assemble_report` keeps its order and its per-section try/except. Each section now yields up to
three things: its FULL text (always → `full`), its MESSAGE text (→ `fold`, possibly empty), and an
"Also checked" phrase (as today, plus a `changed` flag so unchanged phrases group at the end). A new
pure helper decides change (§6); a new pure helper splits the LLM narrative into blocks (§4); a new
pure helper collapses error rows (§5). `compose_report` gains `full_sections` and `changes` and
returns `full_md` in meta; its head/fold logic is otherwise untouched (`Needs me (N)` still counts
LINES — the anomaly item is ONE line, §4).

---

## 3. Section by section — the decisions

Order = today's fold order. "Max" = lines in the message. `full_md` always gets today's full text.

| # | section (renderer) | decision | rule / exact message rendering |
|---|---|---|---|
| 0 | header | KEEP | as today. |
| 0 | Needs you / Needs me / Also checked | KEEP structure | *Also checked* stays ONE line ≤ 420 chars: changed/always phrases first, then `unchanged since last week: bands HOLD · winner capture 19% · …`. Phrases are what each section returns today; a section suppressed as unchanged contributes its phrase to the *unchanged* group instead of a block. |
| 1 | 📅 Reviews ready (`_format_pending_reviews_section`) | KEEP | already one line per item, leads the fold, head counts it under Needs me. No change. |
| 2 | 🔴 Silent failures (`_format_silent_failures_section`) | COMPACT (dedupe, §5) | header `⚪ *Errors logged (7d)* — 40 rows, 0 open` (🔴 only when open > 0). ONE line per type, max 5 types (top5 as today): `• <type> ×<count> — <disposition>: <first–last when>, none since (<N>d) · <cause stem>`. Live rows: one line each, as today. |
| 3 | 📈 Strategy promotion (`_format_promotion_section`) | CHANGE-ONLY per row | header always `📈 *Strategy promotion* — none ready` + ` · changed since last week:` when any row prints. A row prints when it is NEW on the ladder, or its `eligible` / `current_phase` / `next_phase` flipped, or its first blocking reason's text changed **ignoring digits** (`re.sub(r"\d+", "", reason)`), or it became eligible (head, as today). Unchanged rows → full_md only; phrase `promotions: 0 ready, 5 accruing, 1 held by ruling` as today. Prior source: `prior.metrics.strategy_promotions.checks`. |
| 4 | LLM narrative — ✅ Working | KEEP | verbatim, as today (prompt caps it at 3 bullets). |
| 4 | LLM — ⚠️ Anomalies to verify | VERIFY → head count + *To verify (mine)* block (§4) | head: `• <k> observations from this week's narrative to verify Monday, <s> more already settled by the record — ⚠️ block below` (one Needs-me line; omitted when k = 0 and then only the settled line prints in the fold). Fold: `⚠️ *To verify (mine, Monday)* — observations from the narrative, not findings` + the k unsettled bullets verbatim + one line per settled bullet: `• settled by the record: <type> ×<n> — every row <disposition> since <when> (errors above)`. When EVERY bullet settles there is no 'To verify' heading, so the block opens with `⚠️ *Narrative warnings — all settled by the record*` (§10). |
| 4 | LLM — 🔁 Last week | KEEP | verbatim (one sentence). |
| 4 | LLM — 📉 Drift | CUT the LLM's; re-render from `metrics.anomalies.l3_drifts` | `📉 *Drift — band moves this week*` then ONE line per metric key (latest transition first in list order): `• <key in words>: band <from>→<to> — <current> vs a typical <p50> (<n> moves this week)`; `recent_change_hint` appends ` — may be intentional (<hint>)`. Key words: `cooldowns_per_day` → "cooldowns per day", `theme_count_active` → "active theme count", else `key.replace("_", " ")`. Omitted when count = 0. |
| 4 | LLM — 📄 Docs drift | CUT the LLM's; one line from `metrics.drift_check` | `📄 Docs: <n> dated claim(s) nothing can verify — <where> (mine to re-check)`; lists up to 3 `where`, then `+N more`. Omitted when `unverified_n` = 0. |
| 4 | LLM — any other header | KEEP verbatim | fail-open: an unrecognised block is appended to the fold unchanged (never dropped). |
| 5 | 🧪 Setup review (`_setup_performance_review`) | CHANGE-ONLY (event key) + COMPACT | prints when a trade CLOSED this week OR an ask exists (asks still go to the head). "Closed" is any of: a loser or post-mortem in the window, a partial-taken winner closed in the window (`mfe_capture.window_closes`), or the live closed-trade count (`snapshot.live_closed_n`, all-time) differing from last week's - the first two are keyed on the ALERT date and miss a trade alerted earlier and held across the boundary (§10). No stored count to compare -> print (header without the 'a trade closed' claim). Message keeps: header (+ ` — a trade closed this week` only when a close is established), the row line, its bits line, the `⚠ peaks unreadable` line. CUT from message: `_Runs win or lose…_`, every "(… — not enough to ask …)" / "(n<10 — monitoring only…)" parenthetical, the `EXIT_ERA_KEY` legend, and the `eras: era_a n=..` line (bare era letters mean nothing without the legend; the replay `rule eras:` sentence says it in words). ⚠ never key on a windowed `n` - the 90-day window slides every week. |
| 6 | 🎚️ Kill/scale bands (`_band_section`) | CHANGE-ONLY | prints when `band` ≠ prior, or `override_active` ≠ prior, or `n_trades ≥ _SAMPLE_FLOOR` flipped, or a band other than HOLD (head, as today). Prior source: `prior.metrics.report.snapshot.band` (absent → print). Phrase `bands: HOLD` → *unchanged* group when suppressed. Block text unchanged when it prints. |
| 7 | 📉 Early-window drift (`_early_window_drift_review`) | CUT once the floor is reached | its own purpose is pre-floor visibility; at `n ≥ _SAMPLE_FLOOR` (20) the bands own the number → full_md only. Below the floor: as today. |
| 7 | 🔁 Replay-regression (`run_replay_regression` lines) | CHANGE-ONLY (event key) + COMPACT | prints when a trade closed this week (same key as #5; the run is hoisted ahead of #5 because its fingerprint `n` is half of that key, the text still lands here). Message keeps the header, the `live (n=…)` line and the `rule eras:` line; CUT the `calibration (…)` line and the `ⓘ` caveat (full_md). The `suppressed` record and the audit snapshot write are untouched. |
| 8 | ❌ Losers post-mortem (`_format_loser_section`) | KEEP + COMPACT | header + one line per loser (max 10 as today) with flags in WORDS: `the 5-min ORB would have blocked it (<orb5_skip_reason after "setup:stop_too_wide: ">)` / `5-min ORB stop would sit at $X` / `stopped in Nm` / `second attempt, compound loss` / `filled $X past the stop` / `earnings backstop fired` / `catalyst grade vs prose mismatch`. CUT: the 2-line 5m explainer, the legend line, the aggregate line when `n_losers < 5` (at ≥ 5 keep it, `_agg` percentages as today). |
| 8 | 🎯 MFE capture (`_format_mfe_capture_section`) | CHANGE-ONLY | prints when `(n, capture_pct, len(era_split.current))` ≠ prior's or `window_closes` non-empty. Prior source: `prior.metrics.mfe_capture`. Phrase `winner capture 19%` → *unchanged* group when suppressed. |
| 8 | ⚖️ Holistic judge (`_format_judge_section`) | COMPACT to 1 line, KEEP | `⚖️ *Holistic judge:* graded <judged> of <total> alerts — <promotes> up, <demotes> down, <holds> held · <total-judged> fell back to our score · fire axes seen on <fire_seen>, none on <no_fire>`. CUT the code block and the "Per-delta review" pointer. n = 0 → as today. |
| 9 | 🚨 Should've-entered gaps (`format_gaps_section_for_weekly`) | CHANGE-ONLY rows (new only) + COMPACT | header `🚨 *Should've-entered gaps (30d)* — <new> new this week, <carried> carried from last week (full table: full text)`; the table holds NEW rows only (key `TICKER\|YYYY-MM-DD` not in prior's `missed_opportunities.gaps`). 0 new → one header line, no table. CUT the 2-line explainer. The 📡 caps line stays (one line) when `(denom, unsourced)` ≠ prior's; else full_md. |
| 9 | 🔍 Missed Opportunities top winners | COMPACT to 1 line | `🔍 Biggest movers we scored out (7d): T +46% peak (<reason words>) · …` — max 3, peak ≥ 20% only; none → omitted. |
| 9 | 🔍 by-skip-reason table | MOVE (full_md) | counts with no conclusion. |
| 10 | 🪙 Crypto RS (`_format_crypto_section`) | CHANGE-ONLY + COMPACT | prints when `verdict` ≠ `prior.metrics.crypto.verdict` (or ready-to-flip → head, as today): `🪙 *Crypto RS — <LIVE/shadow>*: <verdict words> (last week: <prior verdict words>) · <attempts>/7 ingests, <errors> errors · <universe> coins, <wl> watchlist <marker>` + the pre-arm clause when > 0. 2 lines max. Phrase as today → *unchanged* group when suppressed. |
| 11 | 🔍 Judge 2nd-opinion (`_judge_divergence_section`) | KEEP | one line, n > 0 only, as today. |
| 12 | 🧩 Theme read #486 (`_format_theme_agreement`) | COMPACT, KEEP | header; ONE line per window: `This week (n=6): engine and judge agree on 4 of 6 (67%) — both saw a theme 2 · judge only 1 · engine only 1 · neither 2`; queue line `Judge saw a theme the engine did not — <k> in <basis>, <new> new to this list:` then NEW queue entries only (key `TICKER\|date` vs `prior.metrics.report.snapshot.theme_queue_keys`; absent → all listed with NO novelty claim: `— <k> in <basis> (no earlier review to compare):`), carried ones counted; footer → `_Counts <n> of <graded> judge-graded alerts; definitions and the <excluded> left out: full text._`. ≤ 7 lines + queue. |
| 13 | 💵 Cost envelope MTD (`_spend_envelope`) | CUT from message | the head phrase `spend: $X of $150` already carries it; over-budget → head as today; at ≥ 80% of the budget the phrase also says `(NN%, near the ceiling)` (the block's 🟠 flag moved there). Block → full_md. |
| 14 | 💸 LLM spend vs P&L #313 (`_format_spend_vs_pnl`) | COMPACT, KEEP | 4 lines: header; `LLM spend $X across N calls · top: a $ · b $ · c $` (top 3); `Judge-named callers $X (Y% of spend): <top 3 judge callers>`; one line per book as today. CUT the footer and the `+N other callers` line (full_md). |
| — | 🧭 Source-gap finder | OUT OF SCOPE | a separate 08:45 ET job and message (`source_gap_finder.py`, scheduler ~7478), pasted into the baseline by hand. Not part of `run_weekly_review`. |

---

## 4. The narrative's "anomalies to verify" — what the job settles itself

The LLM prompt is **unchanged** (sonnet-5-5 refuses restructured prompts — memory
`prompts-that-make-a-model-write-its-reasoning-out`; the narrative still emits ✅/⚠️/🔁/📉/📄).
A new pure splitter `split_narrative_blocks(summary) -> list[tuple[str, str]]` cuts the text at
lines starting with `✅`, `⚠️`, `🔁`, `📉`, `📄` (header kind, block text); anything else is kind
`other`. `review["suggestions"]` keeps `_extract_anomalies(summary)` — ALL bullets, as today, so
next week's 🔁 check is unchanged.

`verify_narrative_anomalies(bullets, metrics) -> list[dict]` returns, per bullet,
`{"text", "settled": bool, "why"}`. A bullet is **SETTLED only when all three hold**:

1. it names ≥ 1 audit event type — regex `\b[a-z0-9]+(?:_[a-z0-9]+)*_(?:error|failed)\b` — and EVERY
   named type is in `audit_errors.top_types` with zero rows whose `disposition == "live"`
   (a type not in `top_types` at all → not settled: the record does not hold it);
2. every other backticked identifier in the bullet resolves to one of: a key/path under
   `audit_errors.*`, OR a token that appears in the `summary`/`why`/`detail` text of those
   dispositioned rows (e.g. `prev_close`), OR - from `anomalies.*` - ONLY `silent_audit_error_window`
   (the L1 invariant that fires when an `*_error` row lands in the audit window, so the ledger IS its
   record) and the L1/L2 section names (`l1_invariants`, `l2_anomalies`) while the section holds
   nothing else. Any other L1 invariant or L2 anomaly with count > 0 (a live position with no stop, a
   cooldown spike), a section count with no keys listed, and every L3 drift metric keep the bullet
   MINE (§10: the narrator's prompt tells it to cite the L1/L2 footprint, and an earlier draft that
   let those names resolve could settle a bullet that carried a live-money breach out of the
   message). A backticked
   number, price, dollar amount, percentage or date (after stripping backticks it matches
   `^[-+$\d.,:%/]+$`) is NOT an identifier and is ignored; an identifier that resolves to nothing
   (10-11 bullet 3's `stop_order_id`) blocks settling;
3. it names no ticker from the week's ticker set — every `ticker` value anywhere in `metrics`
   (losers, postmortems, gaps, top winners, cooldowns, churn) — unless that ticker occurs ONLY inside
   a dispositioned row's own summary (KO in the stop-coverage row). Ticker-shaped tokens that are
   not tickers are excluded by a fixed set `{ET, PT, UTC, AM, PM}` AND by position: a token that
   directly follows a `HH:MM` time is a zone, never a ticker (`09:55 ET`; ET is a real ticker that
   can sit in a churn row any week).

Anything else, any parse doubt, any exception → **not settled** (needs-me). **"Settled" means the
named error TYPE is no longer happening - it does not cover an impact claim written in prose** ("...the
EP scan may have missed real candidates that morning" names no identifier a lookup can test); that is
documented here, not detected. **Run, not reasoned**
(`scripts/probes/_700_review_noise/check_settle_rule.py` calls the real `verify_narrative_anomalies`
over the stored rows): 10-11 → bullet 1 names `ep_candidate_parse_error` (0 live rows) but ALSO cites
`l2_anomalies` = 1 (`cooldowns_per_day`), an L2 anomaly the ledger cannot speak to → **not settled**
(the first draft settled it; the review-fix round makes 10-11 read 3 observations, 0 settled); bullet 2
names no type → not settled; bullet 3 names `stop_coverage_repair_failed` (0 live) but CEG is in the
week's ticker set (losers) and `stop_order_id` resolves to nothing → not settled. 10-04 → bullet 1 names
`theme_parent_pass_error`, `theme_synthesis_error`, `assignment_error`, all three present in that
week's `top_types` by exactly those names with 0 live rows, no ticker → settles; bullets 2 and 3
name no type (3 also names TJGC, a top-winner ticker) → not settled. 10-04 settles one bullet; 10-11
settles none, because its only candidate also cites an L2 anomaly. The settle path stays tested on a
constructed bullet (`CLEAN_BULLET`, the 10-11 bullet 1 without its L2 citation).

Rendering: §3 row 4. The settled ones are also appended to `report.suppressed` as
`{"what": "narrative anomaly: <first 60 chars>", "rule": "settled by the record: <why>"}`.

---

## 5. Dedupe for repeated audit-error rows

`collapse_error_rows(rows) -> list[str]` (pure) groups a type's `rows` by `disposition`; for each
non-live group it prints ONE line: `<type> ×<count> — <disposition>: <first when>–<last when>, none
since (<days_ago>d) · <stem>` where `when` is the row's existing `when` (`Wed 10-07 07:00 ET`); when
first and last share the day the second prints as `HH:MM ET` only (`all Wed 10-07 07:00–09:55 ET`
when count > 1); `stem` = the longest common prefix of the group's `summary` fields, cut at the first
digit run that differs, max 110 chars (the parse-error rows differ only in `150`/`139` → stem reads
`… of 13235 snapshot rows dropped … prev_close 0/missing`; the card may instead print the FIRST
row's summary with digit runs replaced by the min–max range — either is accepted, state which).
`recovered`/`closed` groups use their `why` (job + when) as today, one line per group. Live rows:
one line each, unchanged text. `metrics["audit_errors"]` and `report.suppressed` are NOT collapsed.

---

## 6. Change detection — where last week comes from, and the fail direction

**Prior row.** `get_latest_system_review(window_days, on_or_before=None)` in `db.py` gains the
optional kwarg: `AND review_date <= $2` when given. `run_weekly_review` passes
`on_or_before=window_start` (= today − 7). Why not "latest": the on-demand `weekly review`
(agent.py:1319) upserts a row dated that day, so "latest" on a Sunday after a Wednesday run would
compare against Wednesday and hide the week (fail-closed). The SAME `prior` goes to `_synthesize`.

**`_synthesize` strips `prior["metrics"]["report"]` from `prior_block`** — otherwise last week's
rendered text (~15 KB) rides into a prompt that has truncated three times.

**Sources, per field** (missing → PRINT, never hide; a prior fetch that raises → log + print):

| field | this week | last week | change predicate |
|---|---|---|---|
| crypto | `metrics.crypto.verdict` | `prior.metrics.crypto.verdict` | string ≠ |
| MFE | `(n, capture_pct, len(era_split.current))`, `window_closes` | `prior.metrics.mfe_capture` | tuple ≠ or closes non-empty |
| promotions | per `strategy_id`: `(current_phase, next_phase, eligible, re.sub(r"\d+","",reason0))` | `prior.metrics.strategy_promotions.checks` | per row: missing or ≠ |
| gaps | keys `f"{ticker}\|{alert_date}"` | `prior.metrics.missed_opportunities.gaps` | new = cur − prior |
| caps line | `(denom, unsourced)` | `prior.metrics.missed_opportunities.source_gap_summary` | ≠ |
| closed this week | `bool(loser_breakdown.losers) or postmortem_best or postmortem_worst` | — (event key) | true → print setup rows + replay live line |
| band | `{band, override_active, at_floor: n ≥ 20}` | `prior.metrics.report.snapshot.band` | any ≠ |
| theme queue | keys `f"{ticker}\|{alert_date}"` | `prior.metrics.report.snapshot.theme_queue_keys` | new = cur − prior |

**Snapshot** (`report.snapshot`, JSON-safe, string keys, ISO dates): only what raw metrics do not
already hold — `band` and `theme_queue_keys`. Rule stated once: **a snapshot key is never a windowed
count** (30/90-day counts slide every week); use categorical states or event keys.

**Decision log** `report.changes = [{"section", "shown": bool, "why"}]` — one entry per
CHANGE-ONLY section, e.g. `{"section": "bands", "shown": false, "why": "unchanged: HOLD, no override,
at floor"}` / `{"shown": true, "why": "no prior snapshot"}`. The preview probe prints it; the 10-18
verify reads it.

**Stored text:** `report.head_md`, `report.fold_md` (as sent), `report.full_md` (every section's full
text, `\n\n`-joined, code markup intact). `report.suppressed`, `fold_chars`, `head_lines`,
`needs_*` as today.

---

## 7. Constraints the card inherits (verbatim)

- THE LINE: nothing here changes a strategy, size, safeguard, grade, entry or stop; every number is
  computed exactly as today. `compose_report`'s head logic (needs_you / needs_me / one checked line)
  is unchanged except the *unchanged since last week* grouping.
- Telegram: no pipe tables (monospace code blocks only, and the fold strips code markup — as today);
  the existing `render_review_html` + `chunk_html` send path; ONE send.
- No `pytz`, no naive `datetime.now()`, no `date.today()` in `agents/` (`_utcnow()` + `et_today()`
  as today). **No function-local import that shadows a module-level name** (`date`, `datetime`, `re`,
  `json` are module-level in `system_review.py` — use them; `_format_pending_reviews_section`'s
  `as _date` alias is the pattern if a local import is unavoidable).
- Prompt text `_SYSTEM_PROMPT` unchanged. `_extract_anomalies` unchanged.
- `metrics` stored as today plus `report.*` additions; nothing removed or collapsed in storage.
- Deploy: `system_review.py` → `bash scripts/deploy.sh market-agent`; `db.py` is in
  `scripts/exec_loaded_modules.txt`, so the script will ALSO demand `bash scripts/deploy.sh execution`
  — run both (Sunday: windows unrestricted). Verify the running image after
  (`read-the-delta-before-an-execution-deploy`).

---

## 8. The 2026-10-11 message under this spec (by hand, real content)

Source: `scripts/probes/_700_review_noise/preview_1011_by_hand.md` (the file is the artefact; the
head and fold are reproduced here). Lengths from `measure_preview.py`: **head 595 chars / 5 lines
(checked line 330); fold 5,456 chars / 66 lines = 45% of 12,257 (steady state); first run on 10-18
+ the band block once = 5,823 chars = 48%.** The two LLM-verbatim blocks (✅ Working, ⚠️ To verify)
are ~1,500 of those chars; the prompt caps them and they are the informative part.

```
🧠 *Weekly review — Oct 4–11* · regime Choppy
*Needs me (2):*
• 1 data-gated review(s) ripe — I run each and bring you only its result (listed below)
• 2 observations from this week's narrative to verify Monday, 1 more already settled by the record — ⚠️ block below
_Also checked — reviews: 1 ripe (above), 56 still accruing · errors: 40 rows, 0 open · promotions: 0 ready, 5 accruing, 1 held by ruling · crypto: live, gates clean · spend: $13.66 of $150 · themes: 30d n=14, 79% engine-judge agree · 30d LLM $45 vs live P&L $+17 on 6 · unchanged since last week: bands HOLD · winner capture 19%._

▼ (expandable fold)
📅 *Reviews ready* (1) — data-gated thresholds flipped; I run each and bring you only its result:
• *Ranking rule — RUNNING out-of-sample read (converted 2026-08-18 from a single 2026-10-15 gate)* · written 2026-08-16, 2 rule changes since (latest 2026-09-06) — re-check the question against the live rule — RUNNING READ — fires again every session a new out-of-sample alert_date lands, from the first one.

⚪ *Errors logged (7d)* — 40 rows, 0 open
• ep_candidate_parse_error ×38 — quiet: all Wed 10-07 07:00–09:55 ET, none since (4d) · 139–150 of ~13.2k snapshot rows dropped (prev_close 0/missing)
• judge_divergence_check_failed ×1 — quiet: Tue 10-06 09:55 ET, none since (4d) · TLN: 2nd-model call failed/timed out
• stop_coverage_repair_failed ×1 — quiet: Tue 10-06 09:35 ET, none since (4d) · KO: place coverage stop (target 3) failed

📈 *Strategy promotion* — none ready · changed since last week:
• magna53_smallcap: new on the ladder (paper → live) — need 30 closed (have 0)

✅ *Working*
• The CEG loss stayed small and defined. It lost `-$58.95` on about `$58` of actual risk against `$77` planned, roughly -1R. The stop at `281.29` sat about 1.9 ATR away. The postmortem says the setup showed no momentum (day-1 close `299.59` was below the `300.94` entry). That is one trade, so it illustrates the loss cap and says nothing about expectancy.
• The judge layer ran cleanly: `judged` 10 of 10, `fallbacks` 0, `judge_driven` 10 (4 demotes, 0 promotes).
• `audit_errors.open_total` = 0 of 40 total. Every type is dispositioned `quiet`, and the last event was 10-07.

⚠️ *To verify (mine, Monday)* — observations from the narrative, not findings
• `cooldowns.triggered_this_week` = 81 (active 117), versus 38 (active 71) last week. `theme_churn.total_high_churn_pairs` = 20, the same as prior weeks, and this week's top pairs are all Appalachian Natural Gas names at 2 adds / 2 removes. The cause is unknown. It may be a designed mechanism or a known-in-flight task.
• Stop-coverage telemetry: `stop_coverage_repair_failed` count 1 (KO, 10-06, quiet). Separately, the CEG postmortem narrative says the broker-side stop shows `EXPIRED` with a null `stop_order_id`. That comes from the narrative, not from `audit_errors`. It may be designed behaviour, so check it against broker and audit ground truth.
• settled by the record: ep_candidate_parse_error ×38 — every row quiet since Wed 10-07 (errors above)

🔁 *Last week:* The `silent_audit_error_window` invariant persisted at 1, `theme_churn` stayed at 20 pairs, and `cooldowns.triggered_this_week` rose from 38 to 81. The 09-29 theme-pipeline error events did not recur, and the new `audit_errors` types are different ones.

📉 *Drift — band moves this week*
• cooldowns per day: band 1→2 — 20 a day vs a typical 5 (3 moves this week)
• active theme count: band 2→1 — 123 vs a typical 118 (3 moves this week)
📄 Docs: 1 dated claim nothing can verify — docs/setups/magna53_ep.md:675 (mine to re-check)

🧪 *Setup review — entry/stop geometry (90d)* — a trade closed this week
magna53/live n=31 W=9/31 $2.41 · exits: 25/31 stop_hit · peak +1.27R -> real -1.00R · stop/ADR 0.85 · eras: A n=9 · B n=10 · C n=7 · D n=5
   ⚠ 5 peak(s) unreadable (fast exit, recorder blind <10m)

*🔁 Replay-regression* (live R-dist vs #268b calibration):
  live (n=34): exp -0.14R · win 26% · avgW +2.14R · avgL -0.96R · [running maxDD 13.1R · streak 1/14]
  rule eras: under the current rules (since 2026-09-06): 5 trades · older rules: 29 trades — current rules exp +0.85R · older rules exp -0.31R

❌ *Losers post-mortem (1 trade · $-59)*
• `CEG` 2026-10-06 $-59 · the 5-min ORB would have blocked it (range 5.7% > 1.5× ATR)

⚖️ *Holistic judge:* graded 10 of 10 alerts — 0 up, 4 down, 6 held · 0 fell back to our score · fire axes seen on 7, none on 3

🚨 *Should've-entered gaps (30d)* — 2 new this week, 6 carried from last week (full table: full text)
tckr  date   peak    5d   src  reason
EROC  10/06  +14%     —    —   Cooldown
VST   10/06  +11%     —   SRC  Window missed
_📡 Strong-catalyst MODERATE caps (60d, n=14): 2 capped for want of a direct source, 12 had one — a judge call, not a gap._
🔍 Biggest movers we scored out (7d): DNA +46% peak (score below 50) · PICS +35% (score below 50) · SVRN +28% (outside top 20)

🪙 *Crypto RS — LIVE*: gates clean (last week: 1 crypto_ingest_error) · 7/7 ingests, 0 errors · 342 coins, 27 watchlist all resolved · stables in but alts not rotating 4 of the last 7 days

🔍 *Judge 2nd-opinion (#301, claude-sonnet-5-5):* 0/5 disagreed (0%) with the HIGH-tier judge verdict this week

🧩 *Theme read, engine vs judge (#486)*
This week (n=6): engine and judge agree on 4 of 6 (67%) — both saw a theme 2 · judge only 1 · engine only 1 · neither 2
Last 30 days to Oct 11 (n=14): agree on 11 of 14 (79%) — both 4 · judge only 2 · engine only 1 · neither 7
Judge saw a theme the engine did not — 2 in the last 30 days, both new to this list:
• AAOI 10-09 — theme known, excluded (stage Nascent)
• AKAM 09-25 — no theme row at all
_Counts 14 of 22 judge-graded alerts; definitions and the 8 left out: full text._

💸 *LLM spend vs realised P&L (#313) — last 30 days, Sep 12 – Oct 11*
LLM spend $45.33 across 5,623 calls · top: eval_519_option_a $9.22 · perplexity_news_search $8.09 · theme_assignment $7.21
Judge-named callers $2.59 (6% of spend): judge_robustness_eval $0.90 · ep_grade_judge $0.71 · mgmt_judge $0.42
Live book (real money): $+17 over 6 closed trades (3 winners)
```

What left the message and lives only in `full_md`: 38 per-row "quiet" fragments; the 5 unchanged
promotion rows; the HOLD band block (steady state); the early-window drift line (n = 34 ≥ 20); the
calibration card + ⓘ caveat; the MFE block (19%, unchanged, 0 trades under current rules); the
losers' 5m explainer + legend; the judge code block + pointer; 6 carried gap rows + the explainer;
the top-winners table + the by-skip-reason table; the cost-envelope block; the #486 footer and
definitions; the #313 6-caller list + footer; the LLM's own Drift/Docs-drift wording; the setup
review's "not enough to ask" parentheticals + era key.

---

## 9. Build spec (Sonnet card — no design decisions left)

### 9.1 `agents/market_intelligence/db.py`
- `get_latest_system_review(window_days: int = 7, on_or_before: date | None = None)` — adds
  `AND review_date <= $2` when given; return shape unchanged.

### 9.2 `agents/market_intelligence/system_review.py`
New pure helpers (module level, typed, docstring states the fail direction):
- `split_narrative_blocks(summary: str) -> list[tuple[str, str]]` — kinds `working | anomalies |
  last_week | drift | docs_drift | other`; cut at a line whose stripped text starts with the block's
  emoji; `other` for anything before the first header or under an unknown header.
- `verify_narrative_anomalies(bullets: list[str], metrics: dict) -> list[dict]` — §4, exactly.
- `collapse_error_rows(type_entry: dict) -> list[str]` — §5.
- `_prior_value(prior: dict | None, *path) -> tuple[bool, Any]` — `(found, value)`; any
  exception → `(False, None)`.
- `_changed(found: bool, cur, prev) -> tuple[bool, str]` — `(True, "no prior")` when not found;
  `(cur != prev, "…")` otherwise, with the reason text the decision log prints.
- `_render_drift(anomalies: dict) -> str`, `_render_docs_drift(drift_check: dict) -> str`,
  `_render_crypto_change(crypto, prior_verdict) -> str`, `_render_gaps_new(gaps, prior_keys,
  caps, prior_caps) -> str`, `_render_top_movers(top_winners) -> str`, `_loser_flag_words(L) ->
  list[str]`, `_replay_message_lines(lines) -> list[str]` (keeps header + `live (` + `rule eras:`).
Changed signatures:
- `_assemble_report(metrics, summary, window_start, today, prior: dict | None = None)`.
- `compose_report(header, needs_you, needs_me, checked, fold_sections, suppressed, *,
  full_sections: list[str] | None = None, unchanged: list[str] | None = None, changes: list[dict]
  | None = None)` — `unchanged` phrases render as `unchanged since last week: a · b` at the END of
  the checked line; meta gains `full_md`, `head_md`, `fold_md`, `changes`.
- `_band_section(today) -> (block, band, action, snap)` where `snap = {"band", "override_active",
  "at_floor"}`.
- **Naming rule (decided, not the card's choice): every EXISTING renderer keeps its name, its
  signature and its FULL output** — `_format_silent_failures_section`, `_format_promotion_section`,
  `_format_loser_section`, `_format_judge_section`, `_format_mfe_capture_section`,
  `_format_theme_agreement`, `_format_spend_vs_pnl`, `_format_crypto_section`,
  `missed_outcomes.format_gaps_section_for_weekly` / `format_missed_section_for_weekly` and the
  replay `render_section` lines are what `full_md` stores. The COMPACT text comes from NEW
  siblings named `_<section>_message(...)` (e.g. `_silent_failures_message(ae)`,
  `_promotion_message(sp, prior_checks)`, `_theme_agreement_message(weekly, trailing, today=,
  prior_queue_keys=)`, `_spend_vs_pnl_message(agg, window_start=, today=)`,
  `_crypto_message(crypto, prior_verdict)`, `_gaps_message(gaps, caps, prior_keys, prior_caps)`),
  and `_assemble_report` calls BOTH per section (full → `full`, message → `fold`). Consequence:
  **no existing assertion in `tests/test_weekly_review_report_layout.py` is deleted or loosened**
  — the #486 footer/queue wording, the #313 caller list, the `"4 row(s), 1 open"` header and the
  promotion wording all still hold on the full renderers. The ONE existing-test edit is the
  3→4-tuple unpack of `_band_section` in
  `test_early_window_drift_and_band_lines_carry_the_era_clause` (add `, _snap`). The whole-assembly
  tests (`test_a_quiet_week_says_so_and_names_what_was_checked`, the #486/#313 fold-only tests)
  assert on `fold` substrings that the compact message still carries (`📈 *Strategy promotion* —
  none ready`, `*🎚️ Kill/scale bands*` + `rule eras:` — printed because `_assemble` passes no
  prior, `Theme read, engine vs judge (#486)`, `LLM spend vs realised P&L (#313)`); if a substring
  is not in the compact form, carry it in the compact form rather than editing the test.
- `_synthesize(metrics, prior)` — `prior_block` built from `{k: v for k, v in prior["metrics"].items()
  if k != "report"}`.
- `run_weekly_review` — `prior = await get_latest_system_review(window_days,
  on_or_before=window_start)`; passes `prior` to both consumers; `metrics["report"] = report`.
`missed_outcomes.py`: `format_gaps_section_for_weekly(gaps, source_gap_summary, *, prior_keys=None,
prior_caps=None)` and `format_missed_section_for_weekly(missed, *, prior=None)` return the message
form; the current full form stays under `*_full` names (the `/missed` command is untouched).

### 9.3 Tests — `tests/test_weekly_review_noise_700.py` (each RED on today's code; the mutation that
reddens it goes in the docstring, as the existing layout tests do). Reuse `_assemble`/`_inputs`/
`_meta` from `tests/test_weekly_review_report_layout.py` (import them; do not copy). The existing
suite (`tests/test_weekly_review_report_layout.py`, `tests/test_weekly_review_html_send.py`,
`tests/test_setup_performance_review.py`) stays green with the single named edit in §9.2.
1. `test_prior_review_is_the_row_at_or_before_window_start` — mock pool; SQL contains
   `review_date <= $2`; args `(7, window_start)`. RED: kwarg does not exist.
2. `test_synthesize_prompt_strips_last_weeks_rendered_text` — prior with `report.full_md =
   "X"*5000`; capture `messages.create` kwargs via a fake client from `make_async_anthropic`
   monkeypatch; `"X"*5000 not in messages[0].content`. RED.
3. `test_repeated_error_rows_collapse_to_one_line_per_type` — 38 quiet rows 07:00–09:55 ET +
   one quiet row of another type → fold has exactly one `ep_candidate_parse_error ×38` line
   containing `07:00–09:55` and `none since`; `metrics["audit_errors"]["dispositioned"]` still has
   38 entries; `report.suppressed` still carries them. RED.
4. `test_unchanged_band_and_winner_capture_leave_the_fold_and_join_the_checked_line` — prior row
   with equal `mfe_capture` and `report.snapshot.band` → fold lacks `Kill/scale band` and `MFE
   capture`; checked line ends with `unchanged since last week: bands HOLD · winner capture 19%`;
   `report.changes` has both with `shown: false`; with `prior=None` both blocks print and
   `changes[*].why == "no prior"`. RED.
5. `test_a_changed_crypto_verdict_prints_with_last_weeks_reading` — prior verdict `⚠️ not ready: 1
   crypto_ingest_error events in last 7d` → fold has `last week: 1 crypto_ingest_error`; equal →
   absent, phrase in the unchanged group. RED.
6. `test_promotion_rows_print_only_when_new_or_changed` — the 10-11 checks + 10-04 prior →
   exactly one row (`magna53_smallcap … new on the ladder`); `shadow_orb_5m` (-0.07 → -0.06, 43 →
   45) absent from the fold, present in `full_md`. RED.
7. `test_narrative_anomalies_settled_by_the_record_become_a_count_and_say_why` — the three stored
   10-11 bullets verbatim + the 10-11 `audit_errors` (zero live) + losers CEG → needs_me has ONE
   line `3 observations …` (as built: bullet 1 cites an L2 anomaly, §4/§10); fold has `⚠️ *To verify (mine`
   with all three; the positive control is `CLEAN_BULLET` → `2 observations … 1 more already settled`
   and a `settled by the record: ep_candidate_parse_error ×38` line; `review["suggestions"]` still has
   all 3. RED.
8. `test_a_bullet_naming_a_live_error_or_a_traded_ticker_is_never_settled` — the direction guard:
   bullet 3 (quiet type + CEG) not settled; a bullet naming a type with one live row not settled;
   a bullet naming a type absent from `top_types` not settled; (§10) an L1 breach beside a quiet type,
   a bare `l1_invariants` count, an L2 key and an L3 key are never settled. GREEN today by vacuity; RED against
   `settled = True`. Keep it beside 7.
9. `test_drift_and_docs_drift_are_rerendered_in_plain_words_from_metrics` — the 10-11
   `anomalies.l3_drifts` (6 transitions, 2 keys) + the LLM's own `📉 *Drift:*` lines → fold has
   exactly 2 drift lines, `20 a day vs a typical 5 (3 moves this week)`, none of the LLM's `1→2 (20.0
   vs p50 5.0)` text; docs line `1 dated claim nothing can verify — docs/setups/magna53_ep.md:675`. RED.
10. `test_an_unrecognised_narrative_block_is_kept_verbatim` — `🧿 *New thing*\n• x` lands in the
    fold. GREEN today by construction (the whole summary folds); RED against a splitter that drops
    `other`. Keep it.
11. `test_boilerplate_leaves_the_message_but_stays_in_the_full_text` — fold_md lacks `Legend:`,
    `era key —`, `ⓘ`, `Per-delta review`, `Cost envelope (MTD)`, `Telemetry only`, `_Runs win or
    lose`, `not enough to ask`; `report.full_md` contains each. RED.
12. `test_early_window_drift_is_silent_once_the_band_floor_is_reached` — n = 34 → message "" and
    `changes` says `at floor: bands own it`; n = 6 → prints as today. RED.
13. `test_gaps_print_new_rows_only_and_count_the_carried` — 10-11 gaps vs 10-04 gaps → table has
    EROC and VST only; header `2 new this week, 6 carried from last week`; 0 new → header only. RED.
14. `test_replay_and_setup_rows_print_only_when_a_trade_closed_this_week` — losers empty +
    postmortems None + a stored `live_closed_n` equal to now → neither in fold, both in full_md; losers
    [CEG] → both print; stored 33 vs now 34 (a held trade closed) → both print; a partial-taken winner
    in `window_closes` → both print; no stored count or an unreadable replay → both print without the
    'a trade closed' claim; replay message lacks `calibration (` and `ⓘ`; no `eras: era_` in the fold. RED.
15. `test_judge_rollup_is_one_line_and_losers_flags_are_words` — `⚖️ *Holistic judge:* graded 10 of
    10 alerts — 0 up, 4 down, 6 held`; loser line contains `the 5-min ORB would have blocked it
    (range 5.7% > 1.5x ATR)` and no `⛔`/`Legend`. RED.
16. `test_theme_and_spend_sections_are_compact` — #486 ≤ 7 lines + queue, footer is the one-line
    pointer, no prior → every name lists with `(no earlier review to compare)` and no novelty claim,
    an empty stored queue → `both new to this list`, a stored queue → only new keys list;
    #313 is 4 lines with the top-3 inline and no footer. RED.
17. `test_report_meta_persists_snapshot_full_and_sent_text` — the insert payload has
    `report.snapshot == {"band": {...}, "theme_queue_keys": [...], "live_closed_n": 34}`, `full_md`, `head_md`,
    `fold_md`, `changes`; `suppressed` as before. RED.
18. `test_the_1011_fixture_renders_under_the_budget` — fixture
    `tests/fixtures/weekly_review_1011.json` (the stored 10-11 row trimmed to the keys the renderer
    reads + the 10-04 row's `crypto`, `mfe_capture`, `strategy_promotions.checks`,
    `missed_opportunities.gaps/source_gap_summary`; built by a script in
    `scripts/probes/_700_review_noise/`, committed): `len(fold_md) <= 6500` with the prior,
    `<= 7500` without; `head_lines <= 6`; every phrase of today's checked line present; `needs_me
    == 2`. RED (today: 12,257).

### 9.4 Preview probe — `scripts/probes/review_preview.py`
Renders a stored week's review through the REAL `run_weekly_review` without sending and without
writing. Runs where the DB is reachable, i.e. inside the market-agent container after deploy:
`docker exec -i apollo-market python scripts/probes/review_preview.py --date 2026-10-11 --out /tmp/700`.
- `from scripts.probes._muzzle import muzzle_telegram; muzzle_telegram()` FIRST (the derived
  guard — never a hand-listed sender), plus `sr.send_telegram_message` captured.
- `sr.insert_system_review` → capture only (raise if `--strict`); `db.log_audit_event` → capture
  (the replay snapshot + crypto error writes); the real pool is wrapped so `execute`/`executemany`
  raise unless the SQL starts with `SELECT`/`WITH` (the `_662` probe's `_FakeConn` pattern, around
  the real connection).
- `collector.et_today = lambda: date`; `sr._utcnow = lambda: datetime(date, 12:00 UTC)`.
- `sr._gather_and_aggregate` → the stored row's `metrics` with `alert_date` strings restored to
  `date` (the `_662` probe's `_fix_dates`); `sr._synthesize` → the stored `summary` (the LLM is NOT
  re-run — $0); `get_latest_system_review` → the real accessor with `on_or_before=window_start`, or
  `--prior YYYY-MM-DD`.
- Render-time sections (bands, setup rows, replay, 2nd-opinion, themes, spend) run LIVE read-only
  as of now; the stats file states `live_sections_as_of`.
- Writes `head.md`, `fold.md`, `full.md`, `message.html`, `stats.json` (`head_lines`, `fold_chars`,
  `html_chars`, `chunks`, `needs_you/needs_me`, `report.changes`, `audit_writes_captured`,
  `sends_refused`) and prints the stats line. `--full` also prints `full.md`.
- Optional `--offline scripts/probes/_700_review_noise/q1_reviews.out`: no DB; render-time
  sections print their fail-open `unavailable:` lines under a banner — a laptop smoke test only.
Acceptance for the card: `--date 2026-10-11` after deploy → `fold_chars` within the §8 lengths
± 15%, `sends_refused == 0` AND `sent == 1` captured, `audit_writes_captured >= 1`
(replay snapshot) and `mi_system_reviews` unchanged (`SELECT created_at` before/after).

### 9.5 Pre-registration for the PLAN line (status → `deployed`, ETA = Sun 2026-10-18)
- **EXPECT (10-18, first run with a prior row that has raw metrics but no snapshot):** head ≤ 6
  lines; *Also checked* names reviews / errors / promotions / crypto / spend / themes / 30d LLM
  (+ bands, winner capture in the unchanged group or as blocks); fold ≤ 7,500 chars (baseline
  12,257; 7,883 the week before) — the band block and the #486 queue print once; no `quiet: it
  has not recurred` fragment appears more than once per error type; the narrative's ⚠️ bullets
  appear only under `To verify (mine` with a head count; the 10-18 row carries
  `report.snapshot/full_md/fold_md/changes` (the snapshot now also holds `live_closed_n`);
  `suggestions` shape unchanged. On THAT first run the prior row has no `live_closed_n`, so the setup
  review and replay-regression print once (without the 'a trade closed' claim) and the #486 queue lists
  every name with `(no earlier review to compare)`, exactly like the band block; from 10-25 they print
  only when the live closed-trade count moves.
- **DONE-WHEN:** the 10-18 message matches EXPECT AND the 10-25 message shows the steady state
  (unchanged bands/winner capture absent from the fold, present on the checked line; fold ≤ 6,500).
- **WOULD-FAIL-IF:** a section whose inputs changed is missing (worked example: crypto's verdict
  flipped 10-04 → 10-11 and must print on such a week), or an error type with a `live` row is not in
  the head, or the fold is unchanged in length/shape, or `report.changes` is absent from the row.

### 9.6 Out of scope (named, not forgotten)
- A `/review full` Telegram command to fetch `full_md` — three-places rule, orchestrator scope;
  file as its own line only if he asks after seeing 10-18.
- The source-gap finder's own message (08:45 ET job) — a separate noise pass if he wants one.
- Any change to `_SYSTEM_PROMPT`, the LLM model or ceilings.

---

## 10. Review-fix round (2026-10-11, branch `wk1011/700-build-fix`)

Seven findings from the build review, all applied (none contradicts his rule: informative stays, noise
goes, and an unverified claim is never printed as a finding).

| finding | change | result on the real 10-11 content |
|---|---|---|
| BLOCKING: an L1/L2 name settled a bullet | `_settleable_anomaly_names`: only `silent_audit_error_window` (+ the section names while the section holds nothing else) may resolve from `anomalies.*`; other L1/L2 keys with count > 0, a section count with no keys, and L3 metrics keep the bullet mine. Outcome (b) of the review, implemented as written. | Bullet 1 ALSO cites the L2 `cooldowns_per_day`, so it is mine too: 3 observations, 0 settled (the review expected 10-11 unchanged under (b); it is not). Fold 6,315 chars, still under the 6,500 budget. |
| BLOCKING: "a trade closed" ignored held trades | the key is now any of: loser / post-mortem in the window, a partial-taken winner closed in the window, or `snapshot.live_closed_n` differing from last week's. Replay-regression runs ahead of the setup review so its fingerprint `n` is known. No stored count → print. | the held KOD (11d) / PENG (2d) closing next week brings back the setup review and the live expectancy / win rate. |
| minor: first-run theme novelty | no prior → `— N in the last 30 days (no earlier review to compare):`, no 'new to this list' claim. | |
| minor: bare era letters | the `eras: era_a n=..` line leaves the message (full text keeps it). | |
| minor: headerless settled lines | all-settled block opens with `⚠️ *Narrative warnings — all settled by the record*`. | |
| minor: lost 🟠 spend flag | `(NN%, near the ceiling)` on the checked phrase at ≥ 80%. | |
| minor: probe pool guard | `_patch_name_bound_pools` patches every loaded module whose `get_pool` is the original (cost_board, missed_outcomes), derived from `sys.modules`. | still a backstop, not a proof: a connection obtained some other way is not covered. |

Mutation sweep: M1..M24, every one killed (M16-M24 are this round's).
