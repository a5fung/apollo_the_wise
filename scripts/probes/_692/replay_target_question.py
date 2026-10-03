"""#692 replay — ask the NEW deal question of every M&A-filter decision since 2026-05-15, on prod.

SELF-CONTAINED by design: the #692 branch is NOT deployed, so this file EMBEDS the branch's new
classifier prompt (RULE 3), both tool schemas and the decision rule verbatim (a test on the
branch — tests/test_mna_target_question_692.py — fails if they drift from the code). It imports
only helpers that already exist in the deployed image (db pool, Polygon / SEC / FMP fetchers,
the LLM client factory), never anything new on the branch.

RUN (on the box; the script arrives on stdin — no checkout needed):
    # 1. $0 pass: assemble every corpus, print the cost estimate, NO model call
    docker exec -i apollo-market python - --dry-run < replay_target_question.py \
        > replay_dry.jsonl 2> replay_dry.log
    # 2. the paid pass (ONE run; capture once, read many)
    docker exec -i apollo-market python - < replay_target_question.py \
        > replay_results.jsonl 2> replay_run.log

GUARANTEES
  * READ-ONLY on the DB: two SELECTs inside a READ ONLY transaction. No spend-tracker row, no
    audit row (the adapter's one-off rewrite-adoption audit is switched off in-process), no
    replay-sample capture.
  * At most ONE model call per distinct ticker-day, hard cap 200 calls, on claude-sonnet-5-5
    through shared.llm_client.make_async_anthropic. The whole-path cost is ESTIMATED and printed
    BEFORE the first call; the run aborts above $5.00 (and stops mid-run if actual spend would
    cross it).
  * stdout = one JSON line per ticker-day: ticker, date, detectors, old paths, old decision, the
    arm asked, the text it read (with its provenance), the new answer, the new decision, the
    operator label if any. stderr = the estimate, progress and the summary table.

ONE CALL PER TICKER-DAY MEANS ONE ARM. The arm is the path that BLOCKED in prod (a #516 veto row
means the classifier did NOT block, so a veto + headline-block day asks the headline):
  * claude_classifier / keyword_in_text_* / #516 veto (EP) → the CLASSIFIER prompt on the fullest
    stored text: mi_catalyst_tier_shadow.grounded_head (>= 2026-08-24, #593 — the legacy-built
    corpus; the enriched grade may have read more) → else a rebuild from EDGAR 8-K/6-K + Benzinga
    + the stored 200-char summary (APPROXIMATE — the Perplexity answer is unrecoverable) → else
    the 200-char summary alone.
  * polygon_news / title / #284 acquirer-skip → the HEADLINE question on the article that fired
    (re-fetched from Polygon with on_or_before = that day — exact), else the newest candidate.
  * deal_pin_signature / deal_pin_fresh → no call: price-signature paths are out of #692's scope
    and unchanged (still BLOCK).
  On EP days the arm NOT asked could still change the production verdict (the live rule asks the
  headline question when the grader does not pin): `headline_candidates_n` says how many
  keyword-candidate articles that unasked arm would have seen.

WHAT THIS DOES NOT ANSWER: whether a released name would have been TRADED; misses the filter
never blocked (the population is its decisions only); stability — one call per ticker-day is
one sample of a stochastic model (a 3-run stability pass is a separate, separately-priced ask).
The labels column is the operator's; every unlabelled row is for HIS sign-off, not a finding.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

MODEL = "claude-sonnet-5-5"
SINCE = date(2026, 5, 15)
MAX_CALLS = 200
MAX_COST_USD = 5.00
PRICE_IN_PER_MTOK, PRICE_OUT_PER_MTOK = 2.00, 10.00   # sonnet-5-5 (shared/llm_models.PRICING_PER_MTOK)
CLASSIFIER_MAX_TOKENS = 1500   # = output ceiling ep_catalyst_grade
HEADLINE_MAX_TOKENS = 1000     # = output ceiling mna_headline_question
CLASSIFIER_MAX_CHARS = 6000    # the lean grader's corpus window
# Estimation: chars per input token, and output tokens per call INCLUDING always-on thinking
# (opus-5-5 measured ~176 on a ~100-token answer; the grade's analysis adds ~150).
EST_CHARS_PER_TOKEN = 3.5
EST_OUT_CLASSIFIER, EST_OUT_HEADLINE = 600, 350

# ── VERBATIM from the #692 branch (agents/market_intelligence/ma_filter.py) ───────────────────
DEAL_ROLES = ("target", "buyer", "shell", "none")
DEAL_STATUSES = ("signed", "proposed", "speculation", "completed", "none")
DEAL_CONSIDERATIONS = ("cash", "stock", "mixed", "unknown", "none")
PINNING_CONSIDERATIONS = frozenset({"cash", "mixed", "unknown"})
SHELL_ROLE_PINS = True

MNA_KEYWORDS = (
    "buyout", "takeover", "merger", "bought by",
    "being acquired", "definitive agreement", "tender offer", "going private",
    "taken private", "to go private", "strategic transaction", "merger agreement",
    "to be acquired", "all-cash buyout", "halper sadeh",
    "take-private", "private deal for",
)
LITIGATION_PREFIXES = (
    "brodsky & smith", "halper sadeh", "pomerantz", "johnson fistel", "monteverde",
    "bragar eagel", "robbins llp", "schall law", "rosen law",
)

DEAL_FIELD_PROPERTIES = {
    "deal_role": {
        "type": "string",
        "enum": list(DEAL_ROLES),
        "description": (
            "THIS ticker's part in any deal in the text. target: another company is acquiring "
            "all of, or control of, this company, so its holders are paid out. buyer: this "
            "company is buying a company, an asset or a subsidiary's minority. shell: a private "
            "company merges into this listed company and its holders take control (reverse "
            "merger). none: no one is acquiring all of or control of this company — a minority "
            "stake, a PIPE or private placement, a government or strategic equity investment, "
            "warrants, a buyback, another company's deal, or no deal at all."),
    },
    "deal_status": {
        "type": "string",
        "enum": list(DEAL_STATUSES),
        "description": (
            "signed: definitive/merger agreement signed or tender offer commenced. "
            "proposed: unsolicited or non-binding proposal, letter of intent, bid received, in "
            "talks, exploring a sale. speculation: rumour, 'potential target' list, 'could "
            "pursue', denial. completed: deal closed. none: no deal."),
    },
    "deal_consideration": {
        "type": "string",
        "enum": list(DEAL_CONSIDERATIONS),
        "description": (
            "What the target's holders receive. cash: stated cash price per share or all-cash. "
            "stock: acquirer shares only / fixed exchange ratio / all-stock merger. mixed: cash "
            "plus stock. unknown: deal described, terms not in the text. none: no deal."),
    },
    "deal_counterparty": {
        "type": "string",
        "description": "The other company in the deal, or empty.",
    },
}

HEADLINE_TOOL = {
    "name": "classify_deal_headline",
    "description": "Say whether this ticker's share price is fixed by a signed deal, from one news article.",
    "input_schema": {
        "type": "object",
        "properties": {
            **DEAL_FIELD_PROPERTIES,
            "note": {
                "type": "string",
                "description": "One short sentence: the phrase in the text that decided deal_status.",
            },
        },
        "required": [*DEAL_FIELD_PROPERTIES, "note"],
    },
}

# ── VERBATIM from the #692 branch (agents/market_intelligence/ep_detector.py) ─────────────────
CATALYST_TOOL = {
    "name": "classify_catalyst",
    "description": "Classify the quality of a stock EP catalyst and provide analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "quality": {
                "type": "string",
                "enum": ["game_changer", "strong", "routine", "mna"],
                "description": (
                    "game_changer: massive earnings beat + guidance raise, FDA approval, "
                    "transformative contract. strong: solid beat + guidance raise, analyst "
                    "upgrade cluster, major partnership. routine: in-line results, no "
                    "company-specific catalyst. mna: ONLY when deal_status is signed AND either "
                    "deal_role is shell, or deal_role is target and deal_consideration is cash, "
                    "mixed or unknown — this company's price is fixed by a signed deal, no "
                    "momentum trade. Any other deal is graded on its own merit."
                ),
            },
            **DEAL_FIELD_PROPERTIES,
            "analysis": {
                "type": "string",
                "description": "2-3 sentences on the specific catalyst and classification rationale.",
            },
        },
        "required": ["quality", *DEAL_FIELD_PROPERTIES, "analysis"],
    },
}


def classifier_prompt(ticker: str, profile: dict, grounded_text: str | None,
                      max_chars: int = CLASSIFIER_MAX_CHARS) -> str:
    """ep_detector._classify_catalyst_claude's prompt on the branch (grounded-text form)."""
    news_text = grounded_text[:max_chars] if grounded_text else ""
    company_desc = profile.get("description", "")[:300]
    _mc = profile.get("marketCap")
    try:
        mktcap_str = f"${float(_mc) / 1e9:.1f}B" if float(_mc) >= 1e9 else f"${float(_mc) / 1e6:.0f}M"
    except (TypeError, ValueError):
        mktcap_str = "unknown"

    prompt = f"""You are analyzing a stock gap-up for EP (Episodic Pivot) trading.
This stock is gapping up significantly in pre-market. Your job is to identify the catalyst.

Stock: {ticker}
Company: {profile.get('companyName', '')} — {profile.get('sector', '')}
Market cap: {mktcap_str}
Description: {company_desc}

Recent news (may include earnings announcements, guidance, contracts, upgrades):
{news_text or "No news found."}

IMPORTANT RULES:
1. Look for: earnings releases, guidance raises, FDA decisions, major contracts, analyst upgrades.
2. On GROWTH names, REVENUE growth/acceleration with a guidance raise = game_changer or strong.
   The market does not pay for EPS changes on growth stocks — an EPS beat with flat or missing
   REVENUE is "routine". EPS matters only in TURNAROUNDS (loss→profit inflection), and the
   turnaround must be SUSTAINABLE/structural — a single-quarter EPS anomaly from one-time items
   (asset sale, litigation settlement, tax benefit) is "routine".
3. DEAL FIELDS — answer about THIS company only.
   deal_role: 'target' if another company is acquiring all of, or control of, this company, so its
   holders are paid out; 'buyer' if this company is buying another company, an asset, or the rest of a
   subsidiary; 'shell' if this listed company is the vehicle of a reverse merger (a private company
   merges into it and its holders take control); 'none' if no one is acquiring all of or control of
   this company (a minority stake, a PIPE or private placement, a government or strategic equity
   investment, warrants, a buyback, a peer's deal, sector M&A commentary, an index inclusion, a funding
   or supply agreement are all 'none').
   deal_status: 'signed' only when a definitive or merger agreement has been signed or a tender offer
   has commenced; a proposal, letter of intent, bid received, 'in talks', 'exploring a sale' is
   'proposed'; rumours, analyst 'potential target' lists, 'could pursue', or a denial is 'speculation';
   a closed deal is 'completed'.
   deal_consideration: what the target's holders receive — 'cash' (a stated cash price or all-cash),
   'stock' (acquirer shares only / fixed exchange ratio / all-stock merger), 'mixed', 'unknown' (deal
   described, terms not in the text), or 'none'.
   deal_counterparty: the other company, or empty.
   Grade "mna" ONLY when deal_status is 'signed' AND either deal_role is 'shell', or deal_role is
   'target' and deal_consideration is 'cash', 'mixed' or 'unknown' — that is the one case where the
   price is fixed by the deal and there is no momentum trade. In every other case (this company is the
   buyer, the deal is proposed or rumoured, the merger is all-stock, the deal involves another company)
   grade the catalyst on its own merit under rules 1, 2, 4 and 5.
4. Broad SECTOR-MOMENTUM, SHORT-SQUEEZE, or non-company-specific technical moves with no concrete
   company event = "routine" (a gap-up alone is not a catalyst).
5. MATERIALITY — weigh the catalyst's magnitude RELATIVE to the company (market cap above). A contract,
   deal, or order is game_changer/strong ONLY if its value is SIGNIFICANT vs the company's size (a
   meaningful fraction of market cap / revenue); a small or routine-sized deal for the company's scale
   is "routine" however positively worded.

CRITICAL — VERIFY THE CATALYST IS REAL:
- FRESHNESS: the catalyst must be NEW (dated today/overnight, or freshly disclosed in a filing/
  press wire). An UNDATED event, or one that predates today's gap (an old partnership/contract
  resurfacing in a web summary), is NOT today's catalyst no matter how large — classify what is
  actually fresh, or "routine" with the driver marked unidentified.
- If the news text mentions "earnings" or "quarterly results" but does NOT include specific numbers
  (revenue, EPS, guidance figures), the catalyst is likely FABRICATED. Classify as "routine".
- If the news is vague, generic, or reads like a summary with no specific details (no dates, no
  numbers, no named sources), classify as "routine" — the news source may have hallucinated.
- If none of the news items clearly explain WHY the stock gapped, classify as "routine".
- Penny stocks, biotechs with no revenue, and SPACs frequently gap on low-quality catalysts
  (press releases, conference presentations, speculative articles). Be skeptical — classify as "routine"
  unless the catalyst is concrete and verifiable.
- Do NOT assume earnings occurred just because news mentions "earnings" — look for actual reported
  numbers (EPS beat/miss, revenue figures, guidance).

In your analysis, state the SPECIFIC catalyst clearly. If you cannot identify a concrete, verifiable
catalyst, say so explicitly."""
    return prompt


def headline_prompt(ticker: str, company_name: str | None, item: dict, reasoning: str | None) -> str:
    """ma_filter.build_headline_prompt on the branch."""
    co = f" ({company_name})" if company_name else ""
    return (
        f"Ticker: {ticker}{co}. A news article tagged with this ticker, published "
        f"{item.get('published_utc') or 'unknown'}:\n"
        f"Title: {item.get('title') or ''}\n"
        f"Description: {item.get('description') or '(none)'}\n"
        f"Polygon's note on this ticker in the article: {reasoning or '(none)'}\n"
        "Answer about THIS company only. deal_role: 'target' if another company is acquiring "
        "all of, or control of, this company, so its holders are paid out; 'buyer' if this "
        "company is buying another company or asset; 'shell' if a private company is merging "
        "into this listed company and taking control (a reverse merger); 'none' if the article's "
        "deal involves other companies, is sector commentary, a list of possible targets, a "
        "minority stake, a PIPE or private placement, a government or strategic equity "
        "investment, warrants, a buyback, or no deal at all. deal_status: 'signed' only for a signed "
        "definitive or merger agreement or a commenced tender offer; a proposal, bid, talks or "
        "exploration is 'proposed'; rumours, 'potential targets', 'could be acquired' or a denial "
        "is 'speculation'; a closed deal is 'completed'. deal_consideration: 'cash', 'stock', "
        "'mixed', 'unknown' (deal described, terms not stated) or 'none'. deal_counterparty: the "
        "other company or empty. note: one short sentence naming the phrase in the text that "
        "decided deal_status."
    )


def deal_pins_price(role: str | None, status: str | None, consideration: str | None) -> bool:
    """ma_filter.deal_pins_price on the branch."""
    if status != "signed":
        return False
    if role == "target":
        return consideration in PINNING_CONSIDERATIONS
    if role == "shell":
        return SHELL_ROLE_PINS
    return False


def matches_mna_keywords(text: str | None) -> str | None:
    if not text:
        return None
    low = text.lower()
    return next((kw for kw in MNA_KEYWORDS if kw in low), None)


def candidate_articles(ticker: str, items: list[dict]) -> list[tuple[dict, str, str, str | None]]:
    """ma_filter._candidate_articles on the branch."""
    out = []
    for item in items:
        title = item.get("title") or ""
        if title.strip().lower().startswith(LITIGATION_PREFIXES):
            continue
        insights = item.get("insights") or []
        ti = next((i for i in insights if i.get("ticker") == ticker), None)
        reasoning = (ti or {}).get("sentiment_reasoning") or None
        kw = matches_mna_keywords(title)
        if kw:
            out.append((item, "title", kw, reasoning))
            continue
        body_kw = matches_mna_keywords(item.get("description")) or matches_mna_keywords(reasoning)
        if body_kw and ti is not None:
            out.append((item, "description+insights", body_kw, reasoning))
    out.sort(key=lambda c: c[0].get("published_utc") or "", reverse=True)
    return out


# ── The operator's labels (ground truth); everything else is for his sign-off ─────────────────
LABELS: dict[tuple[str, str], str] = {
    ("ACVA", "2026-09-11"): "operator 2026-10-01: REAL buyout - correctly blocked",
    ("FWDI", "2026-09-18"): "operator 2026-10-01: wrongly blocked",
    ("CHYM", "2026-09-09"): "operator 2026-10-01: wrongly blocked",
    ("JBS", "2026-09-18"): "operator 2026-10-01: wrongly blocked",
    ("GPRK", "2026-09-03"): "operator 2026-10-01: wrongly blocked",
    ("IOVA", "2026-09-29"): "operator 2026-10-01: wrongly blocked",
    ("RGTI", "2026-09-08"): "operator 2026-10-01: wrongly blocked",
    ("VKTX", "2026-09-22"): "operator 2026-10-01: wrongly blocked",
    ("WAY", "2026-09-15"): "operator 2026-10-01: wrongly blocked",
    ("CSR", "2026-09-09"): "operator 2026-10-01: wrongly blocked",
    ("SWKS", "2026-09-15"): "operator 2026-10-01: wrongly blocked",
    ("SUNE", "2026-06-08"): "operator 2026-07-04: TP - correctly blocked",
    ("FRMI", "2026-06-17"): "operator 2026-07-04: FP",
    ("ONDS", "2026-05-28"): "operator 2026-07-04: FP",
    ("MMED", "2026-06-03"): "operator 2026-07-04: FP",
    ("IMAX", "2026-05-22"): "operator-confirmed 2026-07-12: FP",
    ("WEN", "2026-06-26"): "operator 2026-08-08: FP",
    ("WEN", "2026-06-29"): "operator 2026-08-08: FP",
    ("WEN", "2026-07-01"): "operator 2026-08-08: FP",
    ("UMAC", "2026-06-30"): "operator 2026-08-08: FP",
    ("LCID", "2026-07-17"): "operator 2026-08-08: FP",
    ("SOUN", "2026-08-06"): "operator 2026-08-08: FP",
    ("LII", "2026-06-15"): "operator 2026-08-08: FP",
    ("SCZM", "2026-06-15"): "operator 2026-08-08: FP",
    ("CLRO", "2026-07-02"): "operator 2026-08-08: the one correct suppression (TP)",
}
MUST_BLOCK = {k for k, v in LABELS.items() if "TP" in v or "REAL buyout" in v}


# ── population ─────────────────────────────────────────────────────────────────────────────────
POP_SQL = """
    SELECT created_at,
           (created_at AT TIME ZONE 'America/New_York')::date AS et_day,
           event_type, summary, detail::text AS detail
    FROM mi_audit_log
    WHERE event_type IN ('mna_filter_fired', 'mna_keyword_vetoed_by_classifier',
                         'mna_acquirer_title_skipped')
      AND created_at >= $1
    ORDER BY created_at
"""
SHADOW_SQL = """
    SELECT scan_date, ticker, grounded_head, grounded_len, claude_analysis, news_summary,
           live_quality_last
    FROM mi_catalyst_tier_shadow
    WHERE scan_date >= $1 AND ticker = ANY($2::text[])
"""


def parse_detail(raw: str | None) -> dict:
    """Audit detail is JSON (EP / 9m) or a str(dict) cut at 500 chars (flag) — be tolerant."""
    if not raw:
        return {}
    for loader in (json.loads, ast.literal_eval):
        try:
            d = loader(raw)
            if isinstance(d, str):
                d = loader(d)
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    out = {}
    for key in ("ticker", "source", "match_path", "detector", "title", "matched_keyword",
                "catalyst_quality", "published_utc"):
        m = re.search(r"['\"]" + key + r"['\"]\s*:\s*['\"]((?:[^'\"\\]|\\.)*)", raw)
        if m:
            out[key] = m.group(1)
    return out


def build_ticker_days(rows) -> dict[tuple[str, str], dict]:
    days: dict[tuple[str, str], dict] = {}
    for r in rows:
        d = parse_detail(r["detail"])
        ev = r["event_type"]
        summary = r["summary"] or ""
        ticker = (d.get("ticker") or re.split(r"[\s:]", summary, maxsplit=1)[0]).strip().upper()
        if not ticker:
            continue
        day = str(d.get("alert_date") or r["et_day"])[:10]
        td = days.setdefault((ticker, day), {
            "ticker": ticker, "date": day, "events": set(), "sources": [], "detectors": set(),
            "titles": [], "news_summary": None, "catalyst_quality": None, "match_paths": set()})
        td["events"].add(ev)
        if ev == "mna_filter_fired":
            src = d.get("source") or "unknown"
            td["sources"].append(src)
            if d.get("detector"):
                td["detectors"].add(d["detector"])
            if d.get("match_path"):
                td["match_paths"].add(d["match_path"])
        elif ev == "mna_keyword_vetoed_by_classifier":
            td["sources"].append("veto_516")
            td["detectors"].add("ep")
        elif ev == "mna_acquirer_title_skipped":
            td["sources"].append("acquirer_skip_284")
            m = re.search(r"not fired: '(.*)'\s*$", summary)
            if m:
                td["titles"].append(m.group(1))
        if d.get("title"):
            td["titles"].append(d["title"])
        if d.get("news_summary") and not td["news_summary"]:
            td["news_summary"] = d["news_summary"]
        if d.get("catalyst_quality") and not td["catalyst_quality"]:
            td["catalyst_quality"] = d["catalyst_quality"]
    return days


def choose_arm(td: dict) -> str:
    """The arm = the path that BLOCKED (is_likely_ma's order: classifier, keyword, headline).
    A #516 veto row means the classifier path did NOT block, so on a day with a veto AND a
    headline block (RGTI 09-08) the headline is what gets asked."""
    srcs = set(td["sources"])
    blocked_by = srcs - {"veto_516", "acquirer_skip_284"}
    if blocked_by and all(s.startswith("deal_pin") for s in blocked_by):
        return "price_signature"
    if any(s == "claude_classifier" or s.startswith("keyword_in_text") for s in blocked_by):
        return "classifier"
    if "polygon_news" in blocked_by:
        return "headline"
    if "veto_516" in srcs:
        return "classifier"
    if "acquirer_skip_284" in srcs or td["titles"]:
        return "headline"
    return "classifier" if "ep" in td["detectors"] else "none"


def old_decision(td: dict) -> str:
    if "mna_filter_fired" in td["events"]:
        return "BLOCK"
    return "PASS"


# ── corpus assembly ($0) ───────────────────────────────────────────────────────────────────────

async def _benzinga(ticker: str, day: date) -> list[dict]:
    """Primary-subject Benzinga items up to `day` via Alpaca News (as scripts/_344 does)."""
    try:
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest
        key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY", "")
        sec = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY", "")
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - timedelta(days=10)
        end = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)
        req = NewsRequest(symbols=ticker, start=start, end=end, limit=30, include_content=True)
        resp = await asyncio.get_running_loop().run_in_executor(
            None, lambda: NewsClient(api_key=key, secret_key=sec).get_news(req))
        items = (resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()).get("news", [])
        return [{"title": n.get("headline", "") or "", "headline": n.get("headline", "") or "",
                 "summary": n.get("summary", "") or "", "content": n.get("content", "") or "",
                 "symbols": list(n.get("symbols", []) or []),
                 "created_at": str(n.get("created_at", ""))} for n in items]
    except Exception as e:
        print(f"  [{ticker}] benzinga rebuild skipped: {type(e).__name__}: {e}", file=sys.stderr)
        return []


async def classifier_corpus(td: dict, shadow: dict | None, profile: dict) -> tuple[str, str]:
    """(text, provenance). Fullest stored text first; a rebuild is APPROXIMATE."""
    if shadow and shadow.get("grounded_head"):
        full = (shadow.get("grounded_len") or 0) <= len(shadow["grounded_head"])
        return shadow["grounded_head"], ("stored_grade_corpus" if full else "stored_grade_corpus_first_6000")
    summary = td.get("news_summary") or (shadow or {}).get("news_summary") or ""
    try:
        from agents.market_intelligence.collector import (
            get_sec_recent_filings, is_primary_subject_news)
        from agents.market_intelligence.ep_detector import build_grounded_text, nearest_today_filing
        day = date.fromisoformat(td["date"])
        filings = await get_sec_recent_filings(
            td["ticker"], forms=("8-K", "6-K"), lookback_days=400, max_filings=30, want_text=True)
        sec = nearest_today_filing(filings, day)
        benz = [n for n in await _benzinga(td["ticker"], day)
                if is_primary_subject_news(n, td["ticker"], profile.get("companyName", ""))][:3]
        text = build_grounded_text(sec, benz, summary or None)
        if text and (sec or benz):
            return text, "rebuilt_approximate(edgar+benzinga+stored_summary)"
    except Exception as e:
        print(f"  [{td['ticker']}] corpus rebuild failed: {type(e).__name__}: {e}", file=sys.stderr)
    if summary:
        return summary, "stored_summary_only_200_chars"
    return "", "none"


async def headline_article(td: dict) -> tuple[dict | None, str | None, str | None, int]:
    """(item, match_path, reasoning, candidates_n) — the article that fired, else the newest
    candidate. Polygon re-fetch with on_or_before = that day (exact replay of what was seen)."""
    from agents.market_intelligence.collector import get_polygon_news
    lookback = 14 if td["detectors"] <= {"ep"} and td["detectors"] else 21
    items = await get_polygon_news(td["ticker"], lookback_days=lookback,
                                   on_or_before=date.fromisoformat(td["date"]), limit=20)
    cands = candidate_articles(td["ticker"], items or [])
    if not cands:
        return None, None, None, 0
    for want in td["titles"]:
        w = (want or "")[:120].strip().lower()
        for item, mp, _kw, reasoning in cands:
            if w and (item.get("title") or "")[:120].strip().lower() == w:
                return item, mp, reasoning, len(cands)
    item, mp, _kw, reasoning = cands[0]
    return item, mp, reasoning, len(cands)


# ── model ──────────────────────────────────────────────────────────────────────────────────────

def _est_cost(prompt: str, est_out: int) -> float:
    tin = len(prompt) / EST_CHARS_PER_TOKEN + 400   # + tool schema
    return tin / 1e6 * PRICE_IN_PER_MTOK + est_out / 1e6 * PRICE_OUT_PER_MTOK


def _actual_cost(resp) -> float:
    u = getattr(resp, "usage", None)
    tin = getattr(u, "input_tokens", 0) or 0
    tout = getattr(u, "output_tokens", 0) or 0
    try:
        from shared.llm_models import cost_for_call
        return float(cost_for_call(MODEL, tin, tout))
    except Exception:
        return tin / 1e6 * PRICE_IN_PER_MTOK + tout / 1e6 * PRICE_OUT_PER_MTOK


async def ask(client, tool: dict, prompt: str, max_tokens: int) -> tuple[dict | None, float, str | None]:
    try:
        from shared import llm_samples
        ctx = llm_samples.capture_disabled()
    except Exception:
        import contextlib
        ctx = contextlib.nullcontext()
    try:
        with ctx:
            resp = await asyncio.wait_for(client.messages.create(
                model=MODEL, max_tokens=max_tokens, tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=[{"role": "user", "content": prompt}]), timeout=120)
    except Exception as e:
        return None, 0.0, f"{type(e).__name__}: {str(e)[:200]}"
    cost = _actual_cost(resp)
    if getattr(resp, "stop_reason", None) == "max_tokens":
        return None, cost, "truncated"
    block = next((b for b in (resp.content or []) if getattr(b, "type", None) == "tool_use"), None)
    if block is None:
        return None, cost, f"no tool_use (stop_reason={getattr(resp, 'stop_reason', None)})"
    return dict(block.input), cost, None


# ── main ───────────────────────────────────────────────────────────────────────────────────────

async def main(dry_run: bool) -> int:
    from agents.market_intelligence.collector import get_fmp_profile, get_ticker_details
    from agents.market_intelligence.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(POP_SQL, datetime(SINCE.year, SINCE.month, SINCE.day,
                                                      tzinfo=timezone.utc))
            days = build_ticker_days(rows)
            tickers = sorted({t for t, _ in days})
            shadow_rows = await conn.fetch(SHADOW_SQL, date(2026, 8, 24), tickers)
    shadow = {(r["ticker"], str(r["scan_date"])): dict(r) for r in shadow_rows}
    print(f"population: {len(rows)} audit rows -> {len(days)} ticker-days "
          f"({sum(1 for td in days.values() if old_decision(td) == 'BLOCK')} blocked)", file=sys.stderr)

    # phase 1 — assemble every question ($0)
    plan = []
    for key in sorted(days, key=lambda k: (k[1], k[0])):
        td = days[key]
        arm = choose_arm(td)
        rec = {"ticker": td["ticker"], "date": td["date"], "detectors": sorted(td["detectors"]),
               "old_paths": sorted(set(td["sources"])), "old_match_paths": sorted(td["match_paths"]),
               "old_grade": td["catalyst_quality"], "old_decision": old_decision(td), "arm": arm,
               "label": LABELS.get(key)}
        prompt, tool, max_tok, est_out = None, None, 0, 0
        try:
            if arm == "classifier":
                profile = await get_fmp_profile(td["ticker"]) or {}
                text, prov = await classifier_corpus(td, shadow.get(key), profile)
                rec.update(corpus_source=prov, corpus_len=len(text), corpus=text[:CLASSIFIER_MAX_CHARS])
                if text:
                    prompt, tool, max_tok, est_out = (classifier_prompt(td["ticker"], profile, text),
                                                      CATALYST_TOOL, CLASSIFIER_MAX_TOKENS,
                                                      EST_OUT_CLASSIFIER)
                if "ep" in td["detectors"]:   # the unasked arm, for the reader ($0)
                    _i, _mp, _r, n = await headline_article(td)
                    rec["headline_candidates_n"] = n
            elif arm == "headline":
                item, mp, reasoning, n = await headline_article(td)
                rec["headline_candidates_n"] = n
                if item is not None:
                    details = await get_ticker_details(td["ticker"]) or {}
                    rec.update(corpus_source="polygon_article_refetched", article={
                        "title": item.get("title"), "published_utc": item.get("published_utc"),
                        "publisher": item.get("publisher"), "match_path": mp,
                        "description": item.get("description"), "reasoning": reasoning,
                        "matched_fired_title": any(
                            (t or "")[:120].strip().lower() == (item.get("title") or "")[:120].strip().lower()
                            for t in td["titles"])})
                    prompt, tool, max_tok, est_out = (
                        headline_prompt(td["ticker"], details.get("name"), item, reasoning),
                        HEADLINE_TOOL, HEADLINE_MAX_TOKENS, EST_OUT_HEADLINE)
                else:
                    rec["corpus_source"] = "none (no keyword-candidate article re-fetched)"
        except Exception as e:
            rec["assembly_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        rec["est_cost_usd"] = round(_est_cost(prompt, est_out), 5) if prompt else 0.0
        plan.append((rec, prompt, tool, max_tok))

    n_calls = sum(1 for _, p, _, _ in plan if p)
    est = sum(r["est_cost_usd"] for r, _, _, _ in plan)
    print(f"planned model calls: {n_calls} (cap {MAX_CALLS}) on {MODEL}; "
          f"ESTIMATED cost ${est:.2f} (abort above ${MAX_COST_USD:.2f})", file=sys.stderr)
    if n_calls > MAX_CALLS or est > MAX_COST_USD:
        print("ABORT: over the call cap or the cost ceiling — nothing was called.", file=sys.stderr)
        for rec, *_ in plan:
            print(json.dumps({**rec, "new_answer": None, "new_decision": None,
                              "skipped": "aborted before any call"}, default=str))
        return 2

    client = None
    if not dry_run:
        from shared import llm_client
        llm_client._audit_best_effort = lambda *a, **k: None   # read-only: no rewrite-adoption audit row
        client = llm_client.make_async_anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    spent, calls = 0.0, 0
    for rec, prompt, tool, max_tok in plan:
        ans, err = None, None
        if prompt and not dry_run:
            if calls >= MAX_CALLS or spent + rec["est_cost_usd"] > MAX_COST_USD:
                err = "skipped: cap reached"
            else:
                calls += 1
                ans, cost, err = await ask(client, tool, prompt, max_tok)
                spent += cost
                rec["call_cost_usd"] = round(cost, 5)
        if rec["arm"] == "price_signature":
            new = "BLOCK (price-signature path, out of #692 scope - unchanged)"
        elif ans is not None:
            role, status, cons = (ans.get("deal_role"), ans.get("deal_status"),
                                  ans.get("deal_consideration"))
            valid = role in DEAL_ROLES and status in DEAL_STATUSES and cons in DEAL_CONSIDERATIONS
            new = ("BLOCK" if deal_pins_price(role, status, cons) else "PASS") if valid \
                else "UNANSWERED (out-of-vocabulary answer)"
        elif dry_run:
            new = None
        elif prompt is None:
            new = "PASS (nothing to ask)"
        else:
            new = f"UNANSWERED ({err})"
        rec.update(new_answer=ans, new_decision=new, error=err)
        print(json.dumps(rec, default=str))
        sys.stdout.flush()
        print(f"  {rec['ticker']:6} {rec['date']} {rec['old_decision']:5} -> {str(new)[:40]:40} "
              f"{rec['arm']:10} {rec.get('label') or ''}", file=sys.stderr)

    print(f"\nmodel calls: {calls}; actual spend ${spent:.2f}", file=sys.stderr)
    # The DoD's acceptance, on the labelled rows only (every other row is HIS to label):
    # every labelled real target still BLOCKs, every labelled false positive PASSes.
    ok = bad = 0
    for rec, *_ in plan:
        key = (rec["ticker"], rec["date"])
        if key not in LABELS or not rec.get("new_decision"):
            continue
        want = "BLOCK" if key in MUST_BLOCK else "PASS"
        hit = str(rec["new_decision"]).startswith(want)
        ok += hit
        bad += not hit
        if not hit:
            print(f"  LABEL MISS {key[0]} {key[1]}: want {want}, got {rec['new_decision']} "
                  f"({LABELS[key]})", file=sys.stderr)
    print(f"labelled acceptance: {ok} of {ok + bad} as labelled", file=sys.stderr)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="#692 replay (read-only; one call per ticker-day)")
    ap.add_argument("--dry-run", action="store_true", help="assemble + estimate only, no model call")
    args = ap.parse_args([a for a in sys.argv[1:] if a != "-"])
    sys.exit(asyncio.run(main(args.dry_run)))
