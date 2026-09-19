# #652 — Rendering check for flipping `send_telegram_message`'s default from Markdown to HTML

**Date:** 2026-09-18 (Friday, PT) · **Status:** finding, evidence half of #652 only — **the default was NOT flipped** and no wrapper was built. · **Refs:** #652, #647, #121. · **Reproduce:** §9.

## The answer

**Flipping the default to HTML-via-`md_to_html` is safe on the 400 side and fixes far more than it touches, with ONE regression that must be patched in `md_to_html` first and TWO design constraints the flip must carry.**

| | count | meaning |
|---|---|---|
| Real bodies checked both ways | **732** | every real message body reachable without spending money (§1) |
| Render today, would 400 under HTML | **0 / 732** | the blocker the task feared does not occur on any real body |
| 400 today, render under HTML | **266 / 732** | messages that today arrive only via the unformatted plain retry |
| Silently corrupted today, correct under HTML | **142 / 732** | v1 ate the underscores out of an identifier and italicised a fragment — no fallback row, nobody knows |
| Identical both ways | **244 / 732** | |
| Differ, HTML worse | **19 / 732** | ALL one thing: a blank first line inside a code block (§5, §7 item 1) |
| Message templates of the flip sites (structure only) | **156 / 173** sites reconstructed; **0** render-today-400-under-HTML; **75** 400 today with an underscore-bearing value |

## 1. Method and population — which rows, over what window

**Population:** (a) `mi_audit_log` rows with `event_type IN ('telegram_markdown_fallback','telegram_send_failed')` over the 60 days ending 2026-09-18 — n = 179 (178 parse verdicts + 1 connect error), captured once by read-only SQL (`_652_capture.sql`); (b) every row of `mi_system_reviews` — n = 21 (2 empty, excluded); (c) the 60 most recent `ep_grade_decision`, 40 most recent `anomaly_detected`, 40 most recent theme-lifecycle rows of `mi_audit_log` and the 25 most recent non-null `mi_ep_alerts.grounded_text` — real dynamic fields, n = 165; (d) every body that crossed `send_telegram_message` while the whole test suite ran once at commit `bfd7deb3` — 278 records, 189 unique bodies, of which 135 come from 53 default-Markdown production sites; (e) the 173 default-Markdown call sites themselves (AST census of `agents/ core/ shared/ scripts/ channels/ main.py`, tests excluded), 156 of which yield a template skeleton. No body was invented; the skeleton group is synthetic in its VALUES only and is reported separately. Era: everything post-#647 (deployed 2026-09-12), i.e. the fallback stripper that keeps identifiers intact is the "today" being compared against.

- **Call sites:** an AST census (`_652_call_site_census.py`), not grep — 125 of the 239 grep hits are multi-line calls whose `parse_mode` sits on another line.
- **Both parsers, locally:** Telegram parses on its servers, has no dry-run, and probing the operator's chat is not acceptable, so both parsers were ported from tdlib's `MessageEntity.cpp` (`_652_tg_parsers.py`). **Credential for the legacy port:** on the 178 real 400s in `mi_audit_log` (Telegram's own error text and byte offset), the byte offset falls inside the stored 300-char head on 59 rows and **the port reproduces it exactly on 59 / 59**. The HTML port has no prod oracle — there were **0 HTML-parser 400s in 60 days** across the 29 explicit-HTML sites — so it rests on tdlib's rules only.
- **The sender's own chunker** (4000 chars, split at a blank line) is applied on both paths BEFORE parsing, on the text the sender would actually chunk (the converted HTML on the proposed path — which is longer).
- **What "today" delivers on a 400:** the real `_strip_markdown_markers` fallback (post-#647). **What HTML delivers on a 400:** the sender's HTML-branch plain fallback.
- **Corpus (all real, one synthetic group named as such):**
  - 178 chunk heads Telegram really 400'd (60 days) — 300 chars each, so their own verdict is Telegram's, not the emulator's;
  - 21 full weekly-review bodies from `mi_system_reviews` (2 are empty rows and are excluded);
  - 165 real dynamic fields the builders embed — 60 judge decisions, 40 L2 anomaly details, 25 grounded texts, 40 theme descriptions — each tested raw, under a `*bold*` header, and (judge prose) in the EP alert's `_{_md_escape(x)}_` shape;
  - **135 unique bodies produced by the REAL builders** for 53 default-Markdown sites, harvested by running the whole test suite once (8,460 tests, 91 s) with a plugin that records every body crossing the send boundary and the production frame that sent it (`_652_harvest_plugin.py`);
  - **156 message templates** reconstructed from the AST of every default-Markdown site, every dynamic slot filled with an underscore-bearing placeholder, an Alpaca-style JSON error, or the acceptance SQL (`_652_site_templates.py`) — structure evidence for the 120 sites the suite never exercises;
  - the acceptance case from the task's WOULD-FAIL-IF, verbatim, in four shapes; and 26 constructed pathological cases from `md_to_html`'s own docstring warning.

## 2. Call-site census (production code; tests/ excluded)

`send_telegram_message` has **205 call sites** in production code (the task's "~205" is exact).

| class | sites | what a default flip does to them |
|---|---|---|
| no `parse_mode` passed — rides the default | **173 / 205** | FLIP: converted + sent as HTML |
| `parse_mode="HTML"` + `md_to_html(...)` at the call (#647's 13 + 3 earlier) | 16 / 205 | untouched — but must NOT be converted twice |
| `parse_mode="HTML"` with a body built by the HTML helpers | 13 / 205 | untouched — same double-conversion rule |
| `parse_mode="Markdown"` written out (`scheduler._backup_health_check_job`, 3 sites) | 3 / 205 | untouched — they opt into legacy explicitly |
| `parse_mode` passed through from a caller / `**kwargs` | 0 / 205 | none exist; there are no wrappers to count callers of |

By file, the flip population is money-path heavy: `order_manager.py` 47, `scheduler.py` 29, `trade_stream.py` 23, `health_checks.py` 19, then 24 files with ≤6 each. Two of the 173 are in `core/confirmations.py` (orchestrator process). Separately, `edit_telegram_message` (`briefing.py:2784`) carries its OWN `parse_mode="Markdown"` default — a send-default flip leaves in-place edits on legacy.

## 3. The acceptance case, verbatim

`SELECT * FROM mi_live_trades WHERE stop_order_id IS NULL`

| shape | today (legacy Markdown) | proposed (HTML via md_to_html) |
|---|---|---|
| bare | **400** on the unpaired `*` → arrives on the plain retry, underscores intact (post-#647 stripper) | first send, intact, no formatting needed |
| inside a ``` fence | first send, intact | first send, intact — block starts with a blank line (§5) |
| inside a `` `code` `` span | first send, intact | first send, intact, identical |
| under a `*bold*` header (the revert-page shape) | **400** → plain retry, bold lost, SQL intact | first send, bold header + SQL intact |

"Intact" today means intact **after a 400 and a second unformatted send**; under HTML it is the first send. The WOULD-FAIL-IF (underscores gone, or no arrival) does not occur on either path today — #647's stripper fix already removed the corruption; what remains today is the 400-then-retry.

## 4. Results by group (every body rendered both ways)

| group | n | identical | differ | 400 today → HTML ok | HTML 400 | identifier loses underscores in what is delivered: today / HTML |
|---|---|---|---|---|---|---|
| **real builder output, default-Markdown sites (the flip population)** | 135 | 101 | 31 | 3 | **0** | 2 / 0 |
| chunk heads Telegram really 400'd | 178 | 11 | 16 | 151 | **0** | 13 / 0 |
| full weekly reviews (19 non-empty) | 19 | 2 | 7 | 10 | **0** | 5 / 0 |
| L2 anomaly detail, raw + under header | 80 | 0 | 50 | 30 | **0** | 50 / 0 |
| judge decision JSON, raw + under header | 120 | 0 | 64 | 56 | **0** | 64 / 0 |
| judge prose in the EP-alert italic shape | 60 | 51 | 5 | 4 | **0** | 0 / 0 |
| grounded text, raw + under header | 50 | 0 | 40 | 10 | **0** | 0 / 0 |
| theme descriptions, raw + under header | 80 | 72 | 8 | 0 | **0** | 0 / 0 |
| bodies a test sent directly (no production sender) | 10 | 7 | 1 | 2 | **0** | 1 / 0 |
| **total, flip-relevant** | **732** | **244** | **222** | **266** | **0** | |
| explicit-HTML sites' bodies (not flipped; double-conversion check) | 44 | — | — | — | — | `md_to_html(body) != body` on **32 / 44** |
| **templates of all default sites (synthetic values)** | 156 | 13 | 68 | 75 | **0** | |

The 178 real-400 heads: 27 parse fine in the first 300 chars because Telegram's failure lies beyond the stored head — 119 of the 178 offsets are past it.

## 5. Every difference, characterised and judged (real bodies; a body can carry several)

| bodies | what differs | HTML is | why |
|---|---|---|---|
| **142** | v1 paired a bare `_`/`*` INSIDE an identifier with one later in the text: underscores eaten (`cooldowns_per_day` → `cooldownsperday`), a bogus italic — often spanning lines — and any `*bold*` or backtick inside it shown literally. HTML shows the text as written. | **better** | this is the "silently corrupted" class — it produces no fallback row |
| **98** | `[…]` in prose (SEC citations, `[L2]`, `[Benzinga 2026-09-11]`): v1 consumes the brackets as a link attempt (a domain-looking text becomes a live link); HTML keeps them literal. | **better** | |
| 33 | a `` `code` `` span or `_italic_` inside `*bold*` (`*Require `rel_volume ≥ 0.5` at alert time*`): v1 cannot nest and shows the inner backticks; HTML nests them. | neutral-to-better | |
| 11 | markup that v1 left literal because it sat inside a bogus span is rendered by HTML. | better | |
| **19** | **the builder writes the fence as ```` ```\n…``` ````; v1 skips that first newline, `md_to_html` keeps it, so the code block starts with a blank line.** 16 of the 156 reconstructed sites write fences this way (`health_checks.py` ×10, `cost_board.py` ×2, `scheduler.py` ×2, `spend_tracker.py`, `crypto/briefing.py`). | **worse — cosmetic, and the only regression found** | fix belongs in `md_to_html`: mirror v1 (drop a language token and ONE newline after the opening fence) |
| 4 + 4 | `**`/`__` pairs and `__________` separator lines from filing text: v1 deletes the characters, HTML shows them. | neutral | both are garbage renderings of a rule line |
| 1 | the HTML text is longer (escapes + tags): one real weekly review (3,593 chars as Markdown, 4,043 as HTML) crosses the 4,000-char split and arrives as two messages. Both halves parse. | neutral, but a **hazard** | the chunker is not tag-aware; a split inside `<pre>`/`<b>` would 400 both halves — none found in 732 bodies |

## 6. The pathological hunt — what the docstring warns about, looked for on purpose

| pattern | constructed case | found in the 732 real bodies | found in the 156 templates |
|---|---|---|---|
| interleaved emphasis `*a _b* c_ d_` | v1 renders (no nesting), HTML **400s** (unmatched end tag) | **0** | **0** |
| a `*bold*` / `_italic_` deliberately spanning a line break | v1 renders it, HTML leaves the markers literal | **0** — every multi-line span in a real body was v1's bogus pairing (§5 row 1), never a deliberate one | 0 |
| fence with a language tag ```` ```sql ```` | v1 treats `sql` as a tag, HTML prints it as the first line | **0** — and **0** language-tagged fences exist in production code (the 4 grep hits are docstrings) | 0 |
| `[text]` without `(url)` | v1 eats the brackets, HTML keeps them | 98 (§5) | 1 |
| nested `*a _b_ c*` | HTML nests, v1 shows `_b_` literally | 33 (§5) | 10 |
| a bare `*` bullet at line start | v1 pairs it with the next `*` (bogus bold across lines) or 400s; HTML shows `*` | 0 | 0 |
| `_md_escape`'d prose inside `_…_` (the pre-#647 EP-alert shape) | v1 **400s** — inside an entity v1 ignores backslash escapes, so the first `\_` closes the italic; HTML consumes the escapes | the IONQ/HOOD alerts of #647 | — |

## 7. What the flip would need (the evidence's conditions, not a plan)

1. **Patch `md_to_html`'s fence handling first** — drop a language token and one newline after the opening fence, as v1 does. That converts the 19 / 732 "worse" bodies into identical ones and closes the only regression. The acceptance case in its fence shape is the regression test.
2. **Convert only when the caller passed no `parse_mode`** (a sentinel default), never when `"HTML"` is passed explicitly — 32 of the 44 bodies from explicit-HTML sites would be mangled by a second `md_to_html` (`<b>` becomes `&lt;b&gt;`). Explicit `"Markdown"` stays the opt-in for legacy.
3. **Chunk safely** — either convert per chunk (chunk the Markdown, then convert each piece) or make the chunker refuse to split inside a tag. Today the converted text is what gets chunked, it is longer, and one real body already crosses the line under HTML.
4. **The HTML-branch plain fallback is already right** (`_to_plain` strips tags and unescapes), so a genuine HTML 400 still lands readable — but it must keep writing `telegram_markdown_fallback` so the first one is seen.
5. **Deploy is two steps** (`both` then `execution`) — broker senders run in `apollo-execution`; and it is a weekend build-slot change, as the task says.
6. **Verify with a positive observable:** a default sender that carries a code block (row-count drift, detector liveness, the nightly audit digest) arrives formatted on its FIRST send with no blank first line in the block, AND `telegram_markdown_fallback` reads zero for default senders. WOULD-FAIL-IF: any fallback row whose `md_body` says "Unsupported start tag" / "Unmatched end tag" / "Can't find end tag", or a message arriving with a literal `<b>`.

## 8. Limits, stated

- **Real output covers 53 / 173 flip sites**; the other 120 (mostly `order_manager.py` 28, `scheduler.py` 24, `trade_stream.py` 12) are covered by template skeletons only — real structure, synthetic values — and 17 sites are built by helpers the reconstruction cannot see into (`briefing.py` ×3, `friday_watchlist.py` ×4, `confirmations.py` ×2, 8 singles).
- The HTML emulator has no production oracle (0 HTML 400s in 60 days) — it follows tdlib's rules; the legacy emulator is validated on 59 / 59 real offsets.
- The 178 real-400 bodies are 300-char heads; their HTML verdict is on the head only.
- Whether Telegram's client trims a leading newline inside `<pre>` was not tested live; the finding assumes it does not, which is the conservative reading.
- Two `mi_system_reviews` rows (sr16, sr17) have an empty summary — excluded; both paths refuse an empty message.

## 9. Reproduce (read-only; nothing here sends a message)

```
python scripts/probes/_652_call_site_census.py --tsv scripts/probes/_652_call_sites.tsv
python scripts/probes/_652_render_check.py --validate           # legacy emulator vs 178 real verdicts
python scripts/probes/_652_render_check.py > scripts/probes/_652_render_report.txt
# re-harvest builder output (91 s):
APOLLO_652_HARVEST=/tmp/652_corpus_tests.jsonl python -m pytest tests -q -p scripts.probes._652_harvest_plugin
# re-capture prod (read-only SQL, capture once): scripts/probes/_652_capture.sql → _652_build_prod_corpus.py
```

Files: `scripts/probes/_652_call_site_census.py`, `_652_tg_parsers.py`, `_652_harvest_plugin.py`, `_652_site_templates.py`, `_652_build_prod_corpus.py`, `_652_render_check.py`, the captured corpora `_652_corpus_prod.jsonl` / `_652_corpus_tests.jsonl`, and the captured report `_652_render_report.txt`.
