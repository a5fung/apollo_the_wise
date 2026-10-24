# Review — #491 U2 (the shadow promotion re-adding a moved stock to the theme it left)

Reviewed 2026-10-24 (Sat). Worktree base 13ddc88b, uncommitted diff (theme_engine.py, theme_engine.md, conftest + 6 test files, new tests/test_491_u2_promotion_cooldown.py). Prod reads were read-only (`SET default_transaction_read_only = on`), remote files /tmp/r491_1..5.sql.

## VERDICT: SHIP — after two prose fixes (no code change needed)

## Checks

| # | check | result | evidence |
|---|---|---|---|
| 0 | no money path | PASS | `promote_shadow_themes` has one caller, scheduler.py:737-740 (nightly step 5d). Nothing under agents/market_intelligence/broker/ imports theme_engine (grep empty). `_hard_guard_refusal` / `_membership_path` / `_strip_guarded_promotion_members` are referenced only inside theme_engine.py. Execution loads theme_engine.py (exec_loaded_modules.txt:67) only through `ep_theme_belonging.py:115` (lazy `judge_theme_fit`), which this diff does not touch. |
| 1 | same cooldown reader as the assignment funnel | PASS | theme_engine.py:70 imports `db.get_cooldown_set` (db.py:15898 → `_get_validation_pair_set`, `NOT bypassed AND cooldown_until > NOW()`). Funnel reads it at :5050 / :11019 and tests `(ticker, theme_name) in cooldown_set` at :5288. Promote reads the same function at :2619 and tests the same tuple at :6154. Exclusions: same `get_all_theme_exclusions` (:2620 vs :10774) and same `_get_excluded_tickers_for_theme` (:2549 vs funnel :5193). Nit: the funnel's :5288 and the carryforward strip :5879 still inline the tuple test, so the "ONE definition" docstring at :6149 holds for the three move/promote paths only — accurate as worded. |
| 2 | exact-name key on PROD | PASS | All four bounce rows carry the source name byte for byte (r491_2 §C, r491_3 §D). `shadow_promoted` row name = move `from` = cooldown `theme_name`: `exact_eq=t`, `md5_eq=t`, same length, for MKSI (10-07, cooldown 932), PAYX (10-16, 1026), YUM (10-16, 1028), CXM (10-21, 1073). The shadow candidate names were ALREADY the source names before canonicalization (r491_3 §E), so canonicalization was not even the mechanism. No other key is needed. The one row the wall will not touch, MKSI 10-09 in "Semiconductor Equipment Subsystem & Fluid Delivery Suppliers" {ICHR,MKSI,UCTT}, is a different cohort and not a return to the source. |
| 3 | hold a cohort left under 3 vs promote the remainder | PASS | Holding is the only choice consistent with standing rulings: `_PROMOTE_MIN_MEMBERS` stays 3 (ruled 2026-09-13, theme_engine.md:237; lowering to 2 withdrawn, :412), and the manual-tap exemption was ruled "leave it" 2026-09-14. Promoting the 2-member remainder would recreate the thin home that the rehome pass plus rule B just retired. All four real cases are exactly this shape (3 → 2). Hold at :2639-2654, alarm subtraction at :2826. |
| 4 | a failed read stops the promote, never fails open | PASS (with a caveat) | The reads at :2619-2620 are not wrapped. A raise goes to scheduler.py:743-751, which writes `shadow_promotion_failed`, and the nightly pull continues. Mutation M6 (cooldown read wrapped with an empty-set fallback) turns `test_a_failed_guard_read_stops_the_run…` red. Caveat 1: it does NOT page. `_failed` does not match the 24h invariant (`audit_invariants.py:218`, `%_error`) or the post-nightly 2h page (market_agent_reference.md:297, `*_error`). Only the weekly digest picks it up (`system_review.py:2250`, `%_failed%`). This was true before the change. Cost of a missed night: themes do not refresh for one night, and the 7-day recency cap means nothing ages out. Caveat 2: no test makes the EXCLUSION read raise (only the cooldown one). |
| 5 | the six edited existing tests still assert the same things | PASS | The diff in each file adds only the `stub_promotion_guards(monkeypatch)` line, plus one import-line change in three of them. No assertion was removed or loosened. The stub defaults to an empty cooldown set and empty exclusions, which is exactly the old behaviour (conftest.py:166-177). The three other promote callers need no stub: test_theme_small_fading_retire reuses test_theme_birth_gate's `_wire_promote` (stubbed); test_judge_theme_gap returns early before the reads; test_651 is a source-text pin. |
| 6 | tests | PASS | Theme and promote files (10 files): 208 passed. Full `python3 -m pytest tests/ -q` in the worktree: **12431 passed, 41 skipped, exit 0** (3m35s). Mutations run on a scratch copy: all 8 turn a named test red (no strip call / strip before canonicalization / no floor hold / alarm not subtracted / no cooldown arm / no exclusion arm / fail-open read / reads moved before the early return). |
| 7 | deploy scope | **FIX the framing in the task, not the SSoT** | For U2 alone: theme_engine.py → NEED_MARKET plus NEED_EXEC (exec_loaded_modules.txt:67), docs → NEED_MARKET, tests → nothing. But the server runs **0d78e80c**, and the pull to origin/main also carries **`shared/llm_models.py`** (521a06ea "Opus fallback pin → claude-opus-5-5" + 1bd2e615) and scripts/preflight_judge_eval_gate.py. A `shared/*` file hits deploy.sh's `*)` arm, which sets NEED_ORCH=1. So **`deploy.sh market-agent` would abort with exit 11**. The correct order is **`deploy.sh both` then `deploy.sh execution`**, which is what the SSoT says (theme_engine.md:1024). That deploy also ships the Opus fallback-pin change, and the operator should know it rides along. `both` builds two images on the box that froze on 10-22: poll the box during the build. A weekend deploy has no window restriction. |
| 8 | EXPECT / DONE-WHEN / WOULD-FAIL-IF / VERIFY-LIVE | drafted below | Baseline replay (r491_4): the new wall replayed over the 15 baseline nights. |

## Fixes, most severe first

1. **Deploy scope (report / caller):** use `deploy.sh both` → `deploy.sh execution`, NOT `market-agent` → `execution` (exit 11 on the `shared/llm_models.py` delta). Say that the Opus fallback-pin change (521a06ea, 1bd2e615) ships in the same deploy. Poll the box during the two-image build.
2. **theme_engine.md:1017, U3 refute column, cannot be observed as written:** it says "a `shadow_promotion_failed` row whose detail names `get_cooldown_set` / `get_all_theme_exclusions`". But scheduler.py:750 writes `detail=f"{type(e).__name__}: {e}"`, which never names the reader. Replace it with: "any `shadow_promotion_failed` row after deploy → read the apollo-market log for that night's traceback."
3. (optional, minor) Add the exclusion-read twin of `test_a_failed_guard_read_stops_the_run…` (set `_ex.side_effect`). M6 only covers the cooldown read.
4. (optional) theme_engine.md U1 row: add the replay reference, "the replay touches about 3% of rows (5 of 157)", so the 25% ceiling has a baseline next to it.

## Out of scope (not a blocker, not filed)
- The promote path also never reads the GLOBAL ban (`db.get_globally_banned_tickers`). NAVN sat in the shadow_promoted row "AI-Enabled Travel, Expense & Vehicle Data Software" on 10-21 and 10-23 while removed from 3 themes in 30 days (r491_5). It is a different wall of the same kind. The caller decides whether to act.

## Baseline the EXPECT rests on (prod, r491_4, read-only)
- 15 nights (10-05..10-23), 157 `shadow_promoted` rows. With the U2 wall replayed over them, **5 rows touched (~3%)**:
  - **4 held** (under 3 after the strip), the four bounces: MKSI 10-07, YUM 10-16, CXM 10-21, and PAYX 10-16. PAYX is inferred: the 10-19 retro-sweep overwrote its cooldown row 1026, so the table hides its 10-16 state.
  - **1 trimmed and still promoted:** CNR out of 'Coal Mining Producers' (10-09), on a validation cooldown, kept at 3 members.
- 0 exact-name exclusion hits (the fuzzy arm cannot be replayed in SQL).
- Active cooldowns now: 150, of which 21 are `rehome:`.

## Drafted PLAN block (for the #491 line, U2 sub-item)

`#491 U2 (the shadow promotion re-adding a moved stock to the theme it left) — status deployed, ETA = deploy night + 10 trading days.`

- **EXPECT** (baseline: 10-05..10-23, 4 of 32 moves were back in their source theme the next night; the replay touches 5 of 157 promoted rows, 4 held + 1 trimmed):
  - **(+)** `promote_member_skipped` rows appear at about one distinct (ticker, theme) pair every 3 nights. Most are `path=cooldown`, and `held_below_floor=true` on the rehome cases.
  - **(+)** 0 moved stocks inside a `shadow_promoted` row named exactly their `from` theme within 14 days of the move.
  - **(−) unintended:** a night's trims plus holds stay at or under 10% of that night's promoted rows (replay: about 3%).
  - **(−) unintended:** a `shadow_themes_promoted` row is written every nightly run.
  - **(−) unintended:** no `shadow_promotion_failed` row.
  - **(−) unintended:** no `shadow_promotion_silent_failure` for a held cohort.
  - **(−) unintended:** no 2-member `shadow_promoted` row.
- **DONE-WHEN:** all three hold:
  - the first `promote_member_skipped` `path=cooldown` row whose (ticker, theme) equals a `theme_member_rehomed` (ticker, from);
  - 10 trading days after deploy with 0 bounces;
  - the trim/hold share recorded once against the 3% replay.
- **WOULD-FAIL-IF:**
  - a `theme_member_rehomed` ticker appears in a `shadow_promoted` row named exactly its `from` theme within 14 days. This is what the unfixed code did 4 times in 15 nights.
  - OR 10 nights that carry moves end with 0 skip rows while the `shadow_themes_promoted` detail `promoted=` lists a `from` name.
  - OR any `shadow_promotion_failed` row after deploy. Read the apollo-market log for that night's traceback; the row's detail does not name the reader.
- **VERIFY-LIVE =**
  - bounce (expect 0 rows):
    ```sql
    SELECT m.detail::jsonb->>'ticker' tk, m.detail::jsonb->>'from' frm, t.theme_date
    FROM mi_audit_log m JOIN mi_themes t ON t.source='shadow_promoted'
     AND t.name = m.detail::jsonb->>'from' AND (m.detail::jsonb->>'ticker') = ANY(t.tickers)
     AND t.theme_date >  (m.created_at AT TIME ZONE 'America/New_York')::date
     AND t.theme_date <= (m.created_at AT TIME ZONE 'America/New_York')::date + 14
    WHERE m.event_type='theme_member_rehomed' AND m.created_at >= '<deploy>';
    ```
  - wall fires (expect ≥ 1, counted as distinct pairs because a held cohort repeats across the 3-day shadow window):
    ```sql
    SELECT detail::jsonb->>'path' path, count(DISTINCT (detail::jsonb->>'ticker', detail::jsonb->>'theme')) pairs,
           count(*) FILTER (WHERE (detail::jsonb->>'held_below_floor')::bool) held_rows
    FROM mi_audit_log WHERE event_type='promote_member_skipped' AND created_at >= '<deploy>' GROUP BY 1;
    ```
