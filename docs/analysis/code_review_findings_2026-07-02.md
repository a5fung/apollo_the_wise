# Comprehensive code review — 8226c3f..HEAD (6/12 → 7/1), findings

**Run 2026-07-02.** Range: 539 commits, 351 files, +92k/−1.3k (Python core 265 files, +33k).
Method after the full fan-out hit the session limit: recovered the completed finder's 15 candidates
from the workflow journal (already paid for), verified them inline, + ONE scoped agent for the
money-path correctness gap (broker/ diff — results appended below when it lands).
Umbrella task: **#412** (fix batch rides the 7/3 sprint deploy window).

## Fixed same-day (committed 7/2, deploy 7/3)
| # | Where | What |
|---|---|---|
| F1 | agent.py:4716 | `/regime` printed the grouped-why description TWICE (the section formatter embeds it since 6/24; the handler still appended it). Dropped the append. |
| F2 | flag_detector.py:1622 | HTF breakout shadow recorder wrapped the whole per-tick loop in one try — one bad break silently dropped shadow rows for every later break that tick (#370 class; this dataset gates the future paper decision). Now per-break try. |
| F3 | agent.py:4932 | Dead re-dedup loop over `get_shadow_theme_candidates` (query is already `DISTINCT ON (name)`), with a wrong ordering comment. Removed. |

## Filed → #412 (verify at fix time; line numbers are 7/2)
| # | Where | Finding | Priority |
|---|---|---|---|
| F4 | scheduler.py:3212 | Prod job `_run_chart_axis_shadow` imports from `scripts/_judge_replay_common` — breaks when #261 (sprint) reorganizes scripts/; the #343 shadow would silently stop accruing (theme-shadow-0-rows class). Re-home the 3 helpers under `agents/market_intelligence/` (same move judge_review.py made). **Must land with/before #261.** | HIGH |
| F5 | ep_detector.py:1662 | #344 re-poll precheck fetches FULL news bodies (`include_content=True`) every premarket tick per routine ticker just to count primary-subject items. Light call for the count; bodies only on trigger (once/day). | MED |
| F6 | ep_detector.py:~1656+~1801 | Enrichment shadow + re-poll shadow are two ~70-line near-copies (same SEC fetch → corpus → classify pipeline, duplicated premarket-window expr). Extract `_build_enriched_corpus` before the next #344 iteration diverges them. | MED |
| F7 | theme_engine.py:1468 | `promote_candidate_by_name` (operator /promotetheme) duplicates `promote_shadow_themes`' guarded INSERT…ON CONFLICT verbatim — two hand-synced copies writing live `mi_themes`. Shared `_upsert_promoted_theme`. | MED |
| F8 | live_tracker.py:629 | Finder claimed the 3:45 partial job duplicates the 4:45 scaffold → **verified DELIBERATE + documented** (decision fn is shared SSoT; write ownership explicit per BW 5/14 protocol). Optional `_load_exit_state` helper only. | LOW |
| F9 | spend_tracker.py | #377 cost meter pasted as `try/except: pass` at ~16 call sites — a tracker failure silences ALL spend telemetry (the exact May-2026 outage class it was built to fix). One `log_anthropic_call_safe` wrapper that WARNs. | MED |
| F10 | execution_client.py:113 | `_http_call` builds a fresh `httpx.AsyncClient` (new pool + TLS handshake) per facade call incl. `trigger_orb_entry` on the ORB window. Module-level shared client. **Trade transport → careful path** (staging exercise, not a hot fix). | MED |
| F11 | flag_detector.py:77 | `_htf_settle_from_bars` re-implements `anticipation.entry_bet_outcome`'s capture/stop/abstain semantics — lockstep-divergence risk makes Family-A vs HTF capture% incomparable. Generalize the tested primitive (entry-price override + include-entry-bar flag). | MED |
| F12 | db.py:6686 | `_dd` ISO→date coercion redefined in 4 functions + 1 inline copy in live_tracker (the LZB 6/13 class was one missed site). One module-level `_coerce_date`. | LOW |
| F13 | channels/telegram.py:1586 | 6+ copies of the AgentRequest→POST /task→reply boilerplate; the copies already diverge — `/themes <arg>` lacks the plain-text retry on Markdown-400 that `/ideas` has (underscore-heavy theme name → hard error). One `_post_market_task` helper. | MED |
| F14 | order_manager.py:1729 | `execute_partial_exit` copies 5 vars into `_*_out` relay names after the advisory-lock block — pure renaming layer in the most safety-critical function; a future in-lock edit that misses the relay line creates a real mismatch. Use the original names. **Trade-state → #151 discipline** (paper exercise before relying on cron). | MED |
| F15 | flag_detector.py:174 | `_FLAG_DEPTH_MIN` (the load-bearing ≤25% HTF depth gate) is stranded mid-file glued to a SHADOW-only helper, ~120 lines from its sibling gate constants. Move to the constants block. | LOW |

## Money-path correctness pass (broker/ diff, single agent)
*(appended when the pass completes)*
