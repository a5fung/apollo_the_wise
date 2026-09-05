"""Earnings-catalyst structured-metrics extractor (2026-05-19).

The LLM catalyst classifier returns single-bucket labels (`strong`,
`game_changer`) based on overall narrative. This module extracts the
STRUCTURED NUMBERS from the news corpus — Q revenue YoY, EPS YoY, guidance,
subscription growth, beat-vs-estimate — so downstream gates can read fresh
ground-truth numbers (instead of stale yfinance fundamentals which lag the
catalyst by 24-72 hours).

Multi-source ingestion: Polygon news + Perplexity synthesis + FMP news +
Claude analysis text. Single Sonnet call extracts to a fixed JSON schema
with per-field source attribution + confidence rating + disagreement flags.

Used by `ep_detector.py` post-catalyst-classification on `is_earnings_day=True`
+ catalyst_quality in ('strong', 'game_changer'). Persists to
`mi_ep_catalyst_metrics`. Subsequent gate logic reads
`q_revenue_yoy_pct` to make the auto-downgrade decision.

Failure handling: on extraction error or low confidence, persists what we
have + flags extraction_quality='low'. Caller decides fallback behavior
(typically: fail-loud → default downgrade with Telegram surface, operator
can re-evaluate via /why).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Any

import httpx

from agents.market_intelligence.collector import (
    get_polygon_news, get_fmp_news, search_news_perplexity, get_alpaca_news,
)
from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)

from shared.llm_models import METRICS_EXTRACTION_MODEL as _EXTRACTION_MODEL
from shared.output_ceilings import max_tokens_for
from shared.llm_response import content_block_types, first_text, is_truncated

# ── STRUCTURAL OUTPUT LOCK (2026-08-10, /simplify altitude review after #542/#543) ─────────
# This caller broke twice on the sonnet-5 move because NOTHING structurally constrained the
# response: output grew >=2.7x and pierced the old ceiling (#542), and a thinking block
# arrived first and broke the positional read (#543/#544). Defect class: output unbounded
# because nothing locks the response shape. Two locks were evaluated:
#
#   (a) FORCED TOOL CALL via judge_transport.invoke_forced_tool — the strong form.
#       REJECTED here, for reasons specific to THIS call site:
#       * invoke_forced_tool takes an SDK AsyncAnthropic client; this caller is raw httpx.
#         Migrating the transport drags the incident-hardened #273 credit-exhaustion path
#         (llm_health classifies httpx.HTTPStatusError from raise_for_status) into a
#         different exception taxonomy, plus SDK client lifecycle — a large change on the
#         EP grading path for a defect the weak lock already covers.
#       * The extraction schema (10 fields, nested null-OR-object unions) lives IN the
#         prompt as prose. A forced tool needs it AGAIN as input_schema: either two copies
#         that drift, or a prompt restructure — and restructuring what the model is asked
#         to produce is a grading-surface change this transport fix must not make (THE LINE).
#   (b) system= JSON-API LOCK — the weak form, mirroring theme_engine.py theme_validation.
#       CHOSEN. Measured sufficient for the defect class: theme_validation carries this
#       exact lock and its output held ~1.0x across the 4-6 -> 5 model change (max completed
#       293 -> 272; see shared/output_ceilings.py), while this caller — freeform, no lock —
#       grew >=2.7x on the same change. One added request field; reader, cost logging, and
#       error handling stay byte-identical. A smaller correct change beats a large risky
#       one on this path.
#
# Byte-identical to the theme_validation lock so the two stay one pattern:
_SYSTEM_LOCK = "You are a JSON API. Respond with valid JSON only. No prose, no markdown, no explanation."

_EXTRACTION_PROMPT = """You will extract structured earnings metrics from news articles about {ticker}.

Today's date: {today}.

Articles (multi-source corpus):
=== Polygon news ===
{polygon_news}

=== Alpaca News (Benzinga-sourced) ===
{alpaca_news}

=== FMP news ===
{fmp_news}

=== Perplexity synthesis ===
{perplexity_text}

=== Internal Claude analysis ===
{claude_analysis}
========================

Extract earnings metrics from the article corpus. Return ONLY a JSON object with this exact schema (use null when a number is not stated, use empty array [] when sources cannot be cited):

{{
  "fiscal_period": "<the fiscal quarter these results are FOR, exactly as the release labels it, e.g. 'Q2 FY2026' or 'Q3 2026' or 'fiscal Q1 2027'; null if the corpus does not state the period>",
  "q_revenue_usd": null OR {{"value": <number>, "yoy_pct": <number>, "beat_vs_est_pct": <number or null>, "sources": ["polygon", "fmp", ...], "confidence": "low" | "medium" | "high"}},
  "fy_revenue_usd": null OR {{"value": <number>, "yoy_pct": <number>, "sources": [...], "confidence": "..."}},
  "q_eps": null OR {{"value": <number>, "yoy_pct": <number or null>, "beat_vs_est_pct": <number or null>, "sources": [...], "confidence": "..."}},
  "subscription_revenue_yoy_pct": null OR {{"value": <number>, "sources": [...], "confidence": "..."}},
  "q_margins": null OR {{"gross_margin": <number 0-1 or null>, "op_margin": <number 0-1 or null>, "net_margin": <number 0-1 or null>, "sources": [...], "confidence": "..."}},
  "guidance_fy_revenue_usd": null OR {{"low": <number>, "high": <number>, "midpoint_yoy_pct": <number or null>, "sources": [...], "confidence": "..."}},
  "guidance_change": null OR {{"direction": "raised" | "lowered" | "reaffirmed" | "initiated", "raise_pct_vs_consensus": <number or null>, "sources": [...], "confidence": "..."}},
  "disagreement_flags": ["<plain text describing any source disagreement>"],
  "extraction_quality": "low" | "medium" | "high",
  "reasoning_brief": "<one sentence: what evidence supports the primary q_revenue_yoy_pct claim>"
}}

EXTRACTION RULES:
- "fiscal_period": the fiscal quarter the just-reported results cover, exactly as the release labels it (e.g. "Q2 FY2026", "Q3 2026", "fiscal Q1 2027"). It is the period the q_revenue/q_eps numbers are FOR — used downstream to align the prior-year comparable when YoY isn't stated. null if no period is stated in the corpus.
- "yoy_pct" should be the explicit YoY growth percentage stated in articles (e.g., "revenue rose 11%" → 11.0). If raw quarter numbers are stated but YoY % is not stated, you MAY compute it (new - old) / old * 100 — but mark confidence "medium" unless multiple articles corroborate.
- "value" fields are absolute dollars (USD). e.g., $82.9M → 82900000.
- "beat_vs_est_pct": revenue or EPS beat vs analyst consensus estimate (e.g., "EPS of $0.63 beat estimate of $0.50" → +26.0). Negative if missed. Look for "beat estimate", "vs consensus", "vs analysts expected", "above/below estimate".
- "subscription_revenue_yoy_pct" is the SEGMENT-LEVEL subscription growth (e.g., "subscription revenue grew 30%"). This is different from total q_revenue YoY — extract both if both are stated. Methodology gates on q_revenue total, not subscription.
- "q_margins": gross/op/net margins for the just-reported quarter, as DECIMAL fractions 0-1 (e.g. "gross margin of 62.5%" → 0.625). Articles often state margins explicitly OR you can compute from raw numbers (gross profit / revenue, operating income / revenue, net income / revenue). If only one or two are stated, leave the others null.
- "q_eps.yoy_pct": EPS YoY growth. If articles state "EPS up X%" use that. If raw EPS numbers are given for current and prior-year quarter, you MAY compute. Mark confidence accordingly.
- "guidance_change": direction is "raised" (above current consensus), "lowered" (below), "reaffirmed" (same), "initiated" (first guidance). raise_pct_vs_consensus is the percentage above/below current Street consensus. Look for: "raises guidance", "lifts forecast", "increases outlook", "cuts guidance", "lowered FY view", "reaffirms outlook".
- "sources": use short publisher names like "polygon", "fmp", "reuters", "dowjones", "perplexity", "claude". An article passed through Polygon mentioning a Reuters quote → source = "polygon" (the channel we got it through).
- "confidence":
  * "high" = 2+ corroborating sources OR cited by a primary authority (Reuters, Dow Jones, BusinessWire, PR Newswire)
  * "medium" = 1 source OR computed-from-raw-numbers
  * "low" = extracted by inference from narrative without explicit number
- "extraction_quality":
  * "high" = q_revenue_usd.yoy_pct is present with confidence high AND at least one of (q_eps with yoy_pct, q_margins, guidance_change)
  * "medium" = q_revenue_usd is present (any confidence)
  * "low" = q_revenue_usd is null
- "disagreement_flags": when sources cite different numbers for the same field, add a plain-text flag describing the disagreement.
- "reasoning_brief": one sentence on which article + numbers support the q_revenue_usd claim. Operator visibility — keep concise.

IMPORTANT — push hard for completeness. Earnings press releases ALWAYS contain: q-revenue, q-eps, beat-vs-estimate, guidance direction. If a field is null, that's a strong signal the corpus is sparse OR you missed it on a re-read. Re-scan before returning null.

OUTPUT: just the JSON, no preamble, no markdown fences.
"""


def _truncate(text: str | None, max_chars: int = 4000) -> str:
    if not text:
        return ""
    return text[:max_chars]


def _format_polygon_news(news: list[dict]) -> str:
    if not news:
        return "(no polygon news)"
    lines = []
    for n in news[:10]:
        title = n.get("title", "")
        pub = n.get("publisher", "")
        desc = n.get("description", "")[:300]
        lines.append(f"- [{pub}] {title}: {desc}")
    return "\n".join(lines)


def _format_fmp_news(news: list[dict]) -> str:
    if not news:
        return "(no fmp news)"
    lines = []
    for n in news[:5]:
        title = n.get("title", "")
        text = n.get("text", "")[:300]
        lines.append(f"- {title}: {text}")
    return "\n".join(lines)


def _format_alpaca_news(news: list[dict]) -> str:
    if not news:
        return "(no alpaca news)"
    lines = []
    for n in news[:10]:
        title = n.get("title", "")
        src = n.get("source", "")
        summary = (n.get("summary", "") or n.get("content", ""))[:400]
        created = n.get("created_at", "")[:10]  # YYYY-MM-DD
        lines.append(f"- [{src} {created}] {title}: {summary}")
    return "\n".join(lines)


async def _call_claude_extraction(prompt: str) -> dict[str, Any] | None:
    """Single Sonnet call returning the structured JSON."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("catalyst_metrics_extractor: no ANTHROPIC_API_KEY")
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": _EXTRACTION_MODEL,
                    # 2026-08-07: was 2000 and it became BINDING the moment this role
                    # tracked to Sonnet 5. Measured in api_usage: on sonnet-4-6 this call
                    # ran 489-561 output tokens (max ever 720) — nowhere near the cap. On
                    # sonnet-5 it runs 1431-1544 avg and hit EXACTLY 2000 on 3 calls, i.e.
                    # truncated mid-JSON -> parse fails -> `extraction_call_failed`.
                    # Extraction failures: ZERO on every day before 08-06, 8 on 08-06 (the
                    # day the role moved), 14 of 14 on 08-07. Raised well clear of the new
                    # model's natural length rather than to a number that merely fits
                    # today's worst case — the whole failure was a ceiling sized for the
                    # previous model's verbosity. See PLAN #542. The number now
                    # lives in shared/output_ceilings.py with its evidence.
                    "max_tokens": max_tokens_for("catalyst_metrics_extractor"),
                    # Output-shape lock — see _SYSTEM_LOCK block above for the (a)/(b)
                    # decision. TRANSPORT ONLY: the user prompt (rubric, fields,
                    # thresholds) is untouched; this constrains FORM, not judgment.
                    "system": _SYSTEM_LOCK,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            r.raise_for_status()
            data = r.json()
            # #377 cost meter — raw-HTTP path: `data` is the response JSON dict, which the
            # tracker's shared readers handle directly (no more SimpleNamespace wrap — that
            # wrap existed only to survive the old getattr-based usage reader, #543).
            # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
            from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
            await log_anthropic_call_safe(
                model=_EXTRACTION_MODEL, caller="catalyst_metrics_extractor",
                response=data,
            )
            # TRUNCATION IS A FAILURE, said out loud (2026-08-10, #543 discipline).
            # Before this guard, a max_tokens cut surfaced only as a mid-JSON parse
            # error ("Expecting ',' delimiter") — and a cut landing exactly after a
            # closing brace would PARSE and grade on a cut answer, the same trap the
            # judge transport measured (AMRC/RDW promoted to HIGH on truncated
            # verdicts). Same predicate as judge_transport, same outcome as a parse
            # failure: return None -> the caller's retry/fail-low path runs. The
            # spend tracker above already fired the LIVE operator alarm + audit row
            # off this response's stop_reason; this guard is the local behavior.
            if is_truncated(data):
                logger.warning(
                    "catalyst_metrics_extractor: response TRUNCATED at "
                    f"max_tokens={max_tokens_for('catalyst_metrics_extractor')} — "
                    "discarding rather than grading on a cut answer (#543)"
                )
                return None
            # ⚠ 2026-08-07 ROOT CAUSE OF THE 08-06/08-07 EXTRACTION OUTAGE.
            # This read `data["content"][0]["text"]` — it assumed the FIRST content
            # block is the answer. That held for sonnet-4-6 and stopped holding the
            # moment this role tracked to sonnet-5, which returns a THINKING block
            # first. `[0]` is then `{"type": "thinking", ...}` with no "text" key, so
            # every call died on `KeyError: 'text'` (logged as the generic "extraction
            # call failed") and the caller graded 14 earnings names as weak on an
            # exception. Take the first block that IS text, rather than assuming
            # position — the shape is a list precisely because it can hold more than
            # one kind of block.
            # ONE canonical reader (#544, shared/llm_response.py) — this hand-rolled loop was
            # the original fix and is now the ninth-plus caller of the same rule. Keeping a
            # local copy is how `extract_stop_leg_id` nearly got four divergent versions.
            content = first_text(data).strip()
            if not content:
                # Be explicit rather than falling into a confusing JSON error: name the
                # block types we got, so the NEXT response-shape change is diagnosable
                # from one log line instead of a morning of forensics.
                logger.warning(
                    "catalyst_metrics_extractor: no text block in response "
                    f"(block types: {content_block_types(data)})"
                )
                return None

            # Strip optional code fences
            if content.startswith("```"):
                lines = content.split("\n")
                # remove ```json or ``` opener, and trailing ```
                content = "\n".join(
                    l for l in lines
                    if not (l.startswith("```"))
                )
            return json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning(f"catalyst_metrics_extractor: JSON parse failed: {e}")
        return None
    except Exception as e:
        # #376: a 401/402 from the Anthropic REST endpoint (raise_for_status →
        # httpx.HTTPStatusError) is credit exhaustion — alert it (deduped).
        from agents.market_intelligence.llm_health import maybe_alert_credit_exhausted
        await maybe_alert_credit_exhausted("catalyst metrics extractor", e)
        logger.warning(f"catalyst_metrics_extractor: extraction call failed: {e}")
        return None


async def extract_earnings_metrics(
    ticker: str,
    today: date,
    *,
    claude_analysis: str | None = None,
    perplexity_text: str | None = None,
    fmp_news: list[dict] | None = None,
    news_on_or_before: date | None = None,
) -> dict[str, Any]:
    """Multi-source earnings-metrics extraction.

    Fetches Polygon news AND Alpaca News on-demand, both windowed to
    `news_on_or_before` for historical re-extraction. FMP + Perplexity
    + Claude analysis are passed by caller since ep_detector already
    has them.

    `news_on_or_before` constrains the Polygon + Alpaca News window for
    historical re-extraction (fixture re-validation, backtests).
    Default None = today. FMP also supports date filtering on plans
    that include the news endpoint.

    Perplexity has no time-travel; historical callers should pass
    perplexity_text=None. Alpaca News (Benzinga-sourced, historical)
    substantially compensates for the missing Perplexity synthesis in
    backtests.

    Returns the extraction dict (per schema in _EXTRACTION_PROMPT). If
    extraction completely fails, returns a minimal dict with
    extraction_quality='low' so callers can apply fail-closed logic
    uniformly.
    """
    polygon_news = await get_polygon_news(
        ticker, lookback_days=7, limit=15, on_or_before=news_on_or_before,
    )
    alpaca_news = await get_alpaca_news(
        ticker, lookback_days=7, limit=15, to_date=news_on_or_before,
    )

    # Wider Perplexity query if first call returned sparse — try a second
    # query with a more specific catalyst-focused phrasing.
    async def _retry_perplexity_more_specific() -> str:
        return await search_news_perplexity(
            f"{ticker} Q4 earnings results — actual revenue, EPS, YoY growth percentages, "
            f"guidance, analyst estimate beat. Quote specific dollar amounts.",
            recency="week",
        )

    base_prompt = _EXTRACTION_PROMPT.format(
        ticker=ticker,
        today=today.isoformat(),
        polygon_news=_truncate(_format_polygon_news(polygon_news), 4000),
        alpaca_news=_truncate(_format_alpaca_news(alpaca_news), 4000),
        fmp_news=_truncate(_format_fmp_news(fmp_news or []), 3000),
        perplexity_text=_truncate(perplexity_text, 3000),
        claude_analysis=_truncate(claude_analysis, 2000),
    )

    extracted = await _call_claude_extraction(base_prompt)

    # Retry on extraction failure OR low quality (per advisor 2026-05-19):
    # extraction variance from Perplexity can leave us with sparse data on
    # one call but rich data on another. Single retry with a more specific
    # Perplexity query + explicit "re-scan for numbers" instruction.
    needs_retry = (
        extracted is None
        or extracted.get("extraction_quality") == "low"
        or (extracted.get("q_revenue_usd") is None)
    )
    if needs_retry:
        try:
            retry_perplexity = await _retry_perplexity_more_specific()
            if retry_perplexity:
                retry_prompt = _EXTRACTION_PROMPT.format(
                    ticker=ticker,
                    today=today.isoformat(),
                    polygon_news=_truncate(_format_polygon_news(polygon_news), 4000),
                    alpaca_news=_truncate(_format_alpaca_news(alpaca_news), 4000),
                    fmp_news=_truncate(_format_fmp_news(fmp_news or []), 3000),
                    perplexity_text=_truncate(retry_perplexity, 3000),
                    claude_analysis=_truncate(claude_analysis, 2000),
                ) + "\n\nNOTE: Earlier extraction returned low quality. Re-scan carefully for explicit dollar amounts, YoY %, and beat-vs-estimate numbers. Press releases ALWAYS contain these — if missing from your prior attempt, look again."
                retry_extracted = await _call_claude_extraction(retry_prompt)
                if retry_extracted is not None:
                    # Keep whichever attempt has more populated fields
                    def _populated_count(d):
                        if not d:
                            return 0
                        return sum(1 for k in ("q_revenue_usd", "q_eps", "q_margins",
                                               "guidance_change", "guidance_fy_revenue_usd",
                                               "subscription_revenue_yoy_pct")
                                   if d.get(k))
                    if _populated_count(retry_extracted) > _populated_count(extracted):
                        logger.info(f"{ticker}: retry extraction higher quality, using retry")
                        extracted = retry_extracted
        except Exception as e:
            logger.warning(f"{ticker}: extraction retry failed: {e}")

    if extracted is None:
        return {
            "extraction_quality": "low",
            "extraction_error": "extraction_call_failed",
            "_polygon_news_count": len(polygon_news),
            "_alpaca_news_count": len(alpaca_news),
            "_raw_polygon_news": polygon_news,
            "_raw_alpaca_news": alpaca_news,
            "_raw_fmp_news": fmp_news or [],
            "_raw_perplexity_text": perplexity_text,
            "_raw_claude_analysis": claude_analysis,
        }

    # Tag corpus shape + raw inputs for audit traceability + future B6 backtests
    extracted["_polygon_news_count"] = len(polygon_news)
    extracted["_alpaca_news_count"] = len(alpaca_news)
    extracted["_fmp_news_count"] = len(fmp_news or [])
    extracted["_extracted_at"] = datetime.now(timezone.utc).isoformat()
    # Carry-forward raw corpus snapshot (consumed by persist_catalyst_metrics).
    # These are stripped before _truncate'd display surfaces so they don't
    # bloat /why output; they're written to dedicated columns for replay.
    extracted["_raw_polygon_news"] = polygon_news
    extracted["_raw_alpaca_news"] = alpaca_news
    extracted["_raw_fmp_news"] = fmp_news or []
    extracted["_raw_perplexity_text"] = perplexity_text
    extracted["_raw_claude_analysis"] = claude_analysis
    return extracted


def get_q_revenue_yoy_pct(extracted: dict[str, Any]) -> float | None:
    """Pull the gate-able field out of the extraction dict.

    Returns the percentage value (e.g., 11.6 for +11.6%) or None if missing.
    """
    qr = extracted.get("q_revenue_usd")
    if not isinstance(qr, dict):
        return None
    val = qr.get("yoy_pct")
    if isinstance(val, (int, float)):
        return float(val)
    return None


async def persist_catalyst_metrics(
    ticker: str,
    alert_date: date,
    extracted: dict[str, Any],
) -> None:
    """Idempotent UPSERT to mi_ep_catalyst_metrics.

    Denormalizes q_revenue_yoy_pct + extraction_quality for cheap gate
    queries; raw_json carries the full extraction for `/why TICKER`.
    Per-source raw corpus columns (polygon/alpaca/fmp news + perplexity
    + claude_analysis) enable replay for future B6 backtests against
    methodology changes — see docs/setups/catalyst_rubric.md.
    """
    q_rev_yoy = get_q_revenue_yoy_pct(extracted)
    eq = extracted.get("extraction_quality", "low")

    # Pop raw corpus from extracted dict before persisting raw_json to
    # avoid duplication (raw corpus has its own columns).
    raw_polygon = extracted.pop("_raw_polygon_news", None)
    raw_alpaca = extracted.pop("_raw_alpaca_news", None)
    raw_fmp = extracted.pop("_raw_fmp_news", None)
    raw_perplexity = extracted.pop("_raw_perplexity_text", None)
    raw_claude = extracted.pop("_raw_claude_analysis", None)

    # asyncpg has a JSONB codec registered at pool init (db.py:90) — passing
    # Python dict/list directly stores correctly typed JSONB (queryable with
    # jsonb_array_length, ->, ->>, etc). Passing json.dumps() would
    # double-encode (codec re-serializes the string). The existing raw_json
    # column has this latent issue; lookup_cached_metrics defensively
    # json.loads on read. New columns use direct-pass for correct typing.
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_ep_catalyst_metrics
                (ticker, alert_date, q_revenue_yoy_pct, extraction_quality,
                 raw_json, raw_polygon_news_json, raw_alpaca_news_json,
                 raw_fmp_news_json, raw_perplexity_text,
                 raw_claude_analysis_text, extracted_at)
            VALUES ($1, $2, $3, $4, $5,
                    $6, $7, $8, $9, $10, NOW())
            ON CONFLICT (ticker, alert_date) DO UPDATE SET
                q_revenue_yoy_pct = EXCLUDED.q_revenue_yoy_pct,
                extraction_quality = EXCLUDED.extraction_quality,
                raw_json = EXCLUDED.raw_json,
                raw_polygon_news_json = EXCLUDED.raw_polygon_news_json,
                raw_alpaca_news_json = EXCLUDED.raw_alpaca_news_json,
                raw_fmp_news_json = EXCLUDED.raw_fmp_news_json,
                raw_perplexity_text = EXCLUDED.raw_perplexity_text,
                raw_claude_analysis_text = EXCLUDED.raw_claude_analysis_text,
                extracted_at = EXCLUDED.extracted_at
        """, ticker, alert_date, q_rev_yoy, eq,
            extracted,
            raw_polygon,
            raw_alpaca,
            raw_fmp,
            raw_perplexity,
            raw_claude,
        )


# #321 write-back (2026-09-04, NSSC 8/24 bug). The live prior-year YoY recovery in ep_detector
# computes a real number once, then every later 5-min tick re-derived "missing" from this table's
# raw_json (which never carried it) — inside the 9:30-9:45 ORB window, where the fetch is off by
# design, that re-derivation DOWNGRADED a name recovered two hours earlier. The recovered number
# now lands in its OWN column, read back by lookup_cached_metrics under `_yoy_recovered`:
#   * NOT raw_json — that stays "what the extractor said" (replay tooling reads it as the LLM
#     output), and the extraction UPSERT's DO UPDATE lists only its own columns, so a later
#     re-extraction cannot clobber a recovery.
#   * NOT q_revenue_yoy_pct / raw_json.q_revenue_usd.yoy_pct — if get_q_revenue_yoy_pct started
#     returning the recovered number on later ticks, the 6-axis rubric would score and its
#     composite gate could downgrade a name the recovery tick kept: a DIFFERENT gate acting than
#     the one that decided. Behaviour must be identical except that the right number survives,
#     so the carrier is read by the recovery block only (every other reader of the
#     denormalised q_revenue_yoy_pct column is unchanged).
# Module constant, not an inline string: scripts/preflight_db_updates.py prepares the REAL
# statement at deploy (its list's rule — a copy can go green about SQL that no longer executes).
YOY_RECOVERY_WRITEBACK_SQL = """
    UPDATE mi_ep_catalyst_metrics
       SET yoy_recovered_json = $3::jsonb
     WHERE ticker = $1 AND alert_date = $2
"""


async def persist_yoy_recovery(ticker: str, alert_date: date, rec: dict[str, Any]) -> bool:
    """Write the #321 recovery result beside the extraction row so every later tick today —
    ORB window included — reads the answer instead of re-deriving "missing". Returns True on a
    row updated; False (loud, never raises) when the row is absent or the write fails, in which
    case the calling tick still applies the number it holds and the next tick re-fetches."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # The pool's JSONB codec (db.py get_pool) serialises the dict itself — passing a
            # pre-dumped string would double-encode to a JSONB string scalar (the raw_json
            # latent issue that persist_catalyst_metrics' comment regrets). Pass the dict.
            status = await conn.execute(YOY_RECOVERY_WRITEBACK_SQL, ticker, alert_date, rec)
        if not str(status).endswith(" 1"):
            logger.warning(f"{ticker}: YoY recovery write-back matched no metrics row for {alert_date} "
                           f"({status}) — the next tick will re-derive")
            return False
        return True
    except Exception as e:  # loud-ok: logged; a failed write-back degrades to the pre-fix re-fetch, never to a wrong grade
        logger.warning(f"{ticker}: YoY recovery write-back failed: {e}")
        return False


def _coerce_recovery(val: Any) -> dict[str, Any] | None:
    """The column round-trips through asyncpg's JSONB codec (dict) or, defensively, a JSON string."""
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except ValueError:
            return None
    if isinstance(val, dict) and isinstance(val.get("yoy_pct"), (int, float)):
        return val
    return None


async def lookup_cached_metrics(ticker: str, alert_date: date) -> dict[str, Any] | None:
    """Read prior extraction for this ticker+date. Returns None if missing.

    Carries the #321 write-back (if any) under `_yoy_recovered` — an annotation key in the
    `_polygon_news_count` idiom, never part of the extraction itself."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT q_revenue_yoy_pct, extraction_quality, raw_json, yoy_recovered_json
            FROM mi_ep_catalyst_metrics
            WHERE ticker = $1 AND alert_date = $2
        """, ticker, alert_date)
    if not row:
        return None
    raw = row["raw_json"]
    if isinstance(raw, str):
        raw = json.loads(raw)
    # #543 DoD: NEVER serve a transport failure as a cached result. A row whose
    # raw_json carries `extraction_error` holds no extracted data — it exists only
    # because ep_detector persists whatever extract_earnings_metrics returns,
    # including the extraction_call_failed placeholder. Serving it as cache
    # converted one transient API failure into a PERMANENT skip for that
    # (ticker, alert_date): every later tick saw "cached" and never re-tried.
    # Returning None makes callers re-extract; a later success UPSERTs over the
    # failure row. The row itself still lands (persist is unchanged) so the raw
    # corpus columns keep their forensic/replay value — it is a forensic row now,
    # not a cached result. Guarding here (the read) rather than at persist also
    # heals failure rows already in prod.
    if isinstance(raw, dict) and raw.get("extraction_error"):
        return None
    if isinstance(raw, dict):
        # asyncpg Record: a column absent from the SELECT (older test doubles) raises KeyError.
        try:
            rec = _coerce_recovery(row["yoy_recovered_json"])
        except (KeyError, IndexError):
            rec = None
        if rec is not None:
            raw["_yoy_recovered"] = rec
    return raw or None
