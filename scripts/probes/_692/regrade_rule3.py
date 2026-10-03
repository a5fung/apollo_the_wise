"""#692 ruling 2 regrade (PAID, read-only, ~$1) — RULE 3 re-tied: the 'mna' grade is reserved for a
signed reverse-merger SHELL; a buyout TARGET is graded on its own merit and the M&A filter alone
decides it on price (operator 2026-10-03, "Go with rec"). This re-grades the SAME rows under the
10-02 branch prompt (OLD) and the re-tied prompt (NEW) and lists every quality flip:
  * the 30 non-deal GRADE-STABILITY rows of the 10-02 replay (expected: ~0 flips — the change
    must not move an ordinary grade);
  * every EP-day row the 10-03 rule NOMINATES (18: the price decides these; expected: the
    signed targets PD / DSGN / ACVA / UTZ / DV / SYNA / CRNX / ATKR / RAMP move from 'mna' to a
    merit grade; the proposals keep their merit grade; nothing becomes 'mna' except a shell).

SELF-CONTAINED by design (the branch is NOT deployed): this file EMBEDS both prompts + tool schemas
verbatim (tests/test_mna_regrade_rule3_692.py fails if the NEW copy drifts from the code, and
pins the OLD copy by hash to the 10-02 branch) and the row lists; it imports only helpers that
already exist in the deployed image (db pool, FMP profile, SEC / Benzinga fetchers, the LLM client
factory, shared.llm_models), always INSIDE functions, never at load time.

RUN (on the box; the script arrives on stdin — no checkout needed; output = JSON lines on stdout):
    # 1. $0: assemble every prompt, print the priced whole path, NO model call
    docker exec -i apollo-market python - --dry-run < scripts/probes/_692/regrade_rule3.py \\
        > regrade_rule3_dry.jsonl 2> regrade_rule3_dry.log
    # 2. the paid pass (ONE run; capture once, read many)
    docker exec -i apollo-market python - < scripts/probes/_692/regrade_rule3.py \\
        > regrade_rule3.jsonl 2> regrade_rule3.log

GUARANTEES
  * READ-ONLY on the DB: SELECTs inside a READ ONLY transaction. No spend-tracker row, no audit
    row (the adapter's rewrite-adoption audit is switched off in-process), no sample capture.
  * Model = shared.llm_models.GROUNDED_GRADE_MODEL resolved at run time (the live grader's id),
    through shared.llm_client.make_async_anthropic; hard cap MAX_CALLS calls.
  * PRICED WHOLE-PATH from shared.llm_models.pricing_for BEFORE the first call, printed to stderr
    with the formula; aborts above MAX_COST_USD ($3.00) and stops mid-run if spending would cross it.
  * Corpus per row, fullest first (the 10-02 replay's order): mi_catalyst_tier_shadow.grounded_head
    → an APPROXIMATE rebuild (EDGAR 8-K/6-K + Benzinga + the shadow row's summary + analysis) →
    the shadow text alone → the 200-char audit excerpt only when no shadow row exists.
    `corpus_source` says which. The same text goes to BOTH prompts, so a flip is the prompt (or
    model noise — one sample per arm; not separable here).
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

MAX_COST_USD = 3.00
MAX_CALLS = 120                        # 2 x (18 + 30) = 96 planned
CLASSIFIER_MAX_TOKENS = 1500           # = output ceiling ep_catalyst_grade
CLASSIFIER_MAX_CHARS = 6000            # the lean grader's corpus window
EST_CHARS_PER_TOKEN = 3.5
EST_TOOL_TOKENS_CLASSIFIER = 700
EST_OUT_CLASSIFIER = 600               # incl. thinking
SHADOW_SINCE = date(2026, 8, 24)       # the shadow table's stored text starts here
AUDIT_SINCE = date(2026, 5, 15)

# EP-day rows the 2026-10-03 rule NOMINATES (scripts/probes/_692/replay_pin_2026-10-03.jsonl —
# the news says target, signed or proposed, on pinning terms; the price decided them).
ROWS_NOMINATED: tuple[tuple[str, str], ...] = (
    ("PZZA", "2026-05-15"), ("DSGN", "2026-05-18"), ("RAMP", "2026-05-18"), ("IMAX", "2026-05-22"),
    ("PD", "2026-05-29"), ("MGM", "2026-06-01"), ("NUVL", "2026-06-09"), ("IRDM", "2026-06-29"),
    ("CRNX", "2026-07-07"), ("PYPL", "2026-07-15"), ("UTZ", "2026-07-21"), ("ATKR", "2026-08-03"),
    ("DV", "2026-08-07"), ("HZO", "2026-08-10"), ("RNW", "2026-08-11"), ("ACVA", "2026-09-11"),
    ("WAY", "2026-09-15"), ("SYNA", "2026-10-02"),
)
# The 10-02 replay's grade-stability sample (kind = grade_stability in replay_2026-10-02.jsonl):
# 30 recent NON-deal grades, one per ticker.
ROWS_STABILITY: tuple[tuple[str, str], ...] = (
    ("VECO", "2026-10-02"), ("IMOS", "2026-10-02"), ("MXL", "2026-10-02"), ("IBRX", "2026-10-02"),
    ("ABTC", "2026-10-02"), ("FWDI", "2026-10-02"), ("CTSH", "2026-10-01"), ("CNXC", "2026-10-01"),
    ("EFOR", "2026-10-01"), ("EFXT", "2026-10-01"), ("ACN", "2026-10-01"), ("GLOB", "2026-10-01"),
    ("SNPS", "2026-10-01"), ("EPAM", "2026-10-01"), ("INFY", "2026-10-01"), ("GLUE", "2026-10-01"),
    ("OLMA", "2026-10-01"), ("SYRE", "2026-09-30"), ("FVR", "2026-09-30"), ("CELC", "2026-09-30"),
    ("SGMT", "2026-09-30"), ("SPXC", "2026-09-30"), ("FEIM", "2026-09-30"), ("AXTI", "2026-09-29"),
    ("CCL", "2026-09-29"), ("ITG", "2026-09-29"), ("KMX", "2026-09-29"), ("CBOE", "2026-09-29"),
    ("FCEL", "2026-09-29"), ("PKOH", "2026-09-28"),
)

# ── the shared deal fields (ma_filter.DEAL_FIELD_PROPERTIES, verbatim; unchanged by ruling 2) ──
DEAL_FIELD_PROPERTIES = {
    "deal_role": {
        "type": "string",
        "enum": ["target", "buyer", "shell", "none"],
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
        "enum": ["signed", "proposed", "speculation", "completed", "none"],
        "description": (
            "signed: definitive/merger agreement signed or tender offer commenced. "
            "proposed: unsolicited or non-binding proposal, letter of intent, bid received, in "
            "talks, exploring a sale. speculation: rumour, 'potential target' list, 'could "
            "pursue', denial. completed: deal closed. none: no deal."),
    },
    "deal_consideration": {
        "type": "string",
        "enum": ["cash", "stock", "mixed", "unknown", "none"],
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


def _tool(quality_desc: str) -> dict:
    return {
        "name": "classify_catalyst",
        "description": "Classify the quality of a stock EP catalyst and provide analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "quality": {
                    "type": "string",
                    "enum": ["game_changer", "strong", "routine", "mna"],
                    "description": quality_desc,
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


# ── OLD = the 10-02 branch (commit f666f9e9), verbatim; hash-pinned by the test ──────────────
OLD_CATALYST_TOOL = _tool(
    "game_changer: massive earnings beat + guidance raise, FDA approval, transformative contract. "
    "strong: solid beat + guidance raise, analyst upgrade cluster, major partnership. routine: "
    "in-line results, no company-specific catalyst. mna: ONLY when deal_status is signed AND "
    "either deal_role is shell, or deal_role is target and deal_consideration is cash, mixed or "
    "unknown — this company's price is fixed by a signed deal, no momentum trade. Any other deal "
    "is graded on its own merit.")

_RULE_3_HEAD = """3. DEAL FIELDS — answer about THIS company only.
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
"""

OLD_RULE_3 = _RULE_3_HEAD + """   Grade "mna" ONLY when deal_status is 'signed' AND either deal_role is 'shell', or deal_role is
   'target' and deal_consideration is 'cash', 'mixed' or 'unknown' — that is the one case where the
   price is fixed by the deal and there is no momentum trade. In every other case (this company is the
   buyer, the deal is proposed or rumoured, the merger is all-stock, the deal involves another company)
   grade the catalyst on its own merit under rules 1, 2, 4 and 5."""

# ── NEW = the re-tied RULE 3 (agents/market_intelligence/ep_detector.py on the branch), verbatim ─
NEW_CATALYST_TOOL = _tool(
    "game_changer: massive earnings beat + guidance raise, FDA approval, transformative contract. "
    "strong: solid beat + guidance raise, analyst upgrade cluster, major partnership. routine: "
    "in-line results, no company-specific catalyst. mna: ONLY when deal_role is shell AND "
    "deal_status is signed — this listed company is the vehicle of a signed reverse merger. A "
    "buyout TARGET, signed or proposed, is graded on its own merit; a separate M&A filter decides "
    "it on price, not the grade.")

NEW_RULE_3 = _RULE_3_HEAD + """   Grade "mna" ONLY when deal_role is 'shell' AND deal_status is 'signed' — the listed vehicle of a
   signed reverse merger, the one case where the grade itself carries the verdict. A TARGET of a deal
   — signed or proposed, whatever the consideration — is graded on its own merit under rules 1, 2, 4
   and 5: a separate M&A filter reads its price and decides, not the grade. The same goes for a
   buyer, an all-stock merger, or a deal that involves another company."""


def _grader_prompt(ticker: str, profile: dict, grounded_text: str | None, rule_3: str,
                   max_chars: int = CLASSIFIER_MAX_CHARS) -> str:
    """ep_detector._classify_catalyst_claude's prompt (grounded-text form); only RULE 3 differs."""
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
{rule_3}
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


def old_prompt(ticker, profile, text):
    return _grader_prompt(ticker, profile, text, OLD_RULE_3)


def new_prompt(ticker, profile, text):
    return _grader_prompt(ticker, profile, text, NEW_RULE_3)


def parse_deal(fields) -> tuple[str, str, str] | None:
    if not isinstance(fields, dict):
        return None
    role = str(fields.get("deal_role") or "").strip().lower()
    status = str(fields.get("deal_status") or "").strip().lower()
    cons = str(fields.get("deal_consideration") or "").strip().lower()
    if role not in ("target", "buyer", "shell", "none") or \
            status not in ("signed", "proposed", "speculation", "completed", "none") or \
            cons not in ("cash", "stock", "mixed", "unknown", "none"):
        return None
    return role, status, cons


# ── the corpus (the 10-02 replay's order; copied so this file stands alone) ───────────────────
SHADOW_SQL = """
    SELECT scan_date, ticker, grounded_head, grounded_len, claude_analysis, news_summary,
           live_quality_first, live_quality_last
    FROM mi_catalyst_tier_shadow
    WHERE ticker = ANY($1::text[]) AND scan_date = ANY($2::date[])
"""
AUDIT_SQL = """
    SELECT (created_at AT TIME ZONE 'America/New_York')::date AS et_day, summary, detail::text AS detail
    FROM mi_audit_log
    WHERE event_type = 'mna_filter_fired' AND created_at >= $1
      AND split_part(summary, ' via', 1) = ANY($2::text[])
    ORDER BY created_at
"""


def parse_detail(raw: str | None) -> dict:
    if not raw:
        return {}
    for loader in (json.loads, ast.literal_eval):
        try:
            d = loader(raw)
            return d if isinstance(d, dict) else {}
        except Exception:
            continue
    return {}


async def _benzinga(ticker: str, day: date) -> list[dict]:
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


async def corpus_for(ticker: str, day_iso: str, shadow: dict | None, excerpt: str,
                     profile: dict) -> tuple[str, str]:
    """(text, corpus_source) — fullest stored text first; a rebuild is APPROXIMATE."""
    if shadow and shadow.get("grounded_head"):
        full = (shadow.get("grounded_len") or 0) <= len(shadow["grounded_head"])
        return shadow["grounded_head"], ("stored_grade_corpus" if full else "stored_grade_corpus_first_6000")
    if shadow is not None:
        summary = "\n".join(t for t in (shadow.get("news_summary"), shadow.get("claude_analysis")) if t)
        summary_src = "shadow_summary+analysis"
    else:
        summary, summary_src = excerpt or "", "audit_excerpt_200_chars"
    try:
        from agents.market_intelligence.collector import get_sec_recent_filings, is_primary_subject_news
        from agents.market_intelligence.ep_detector import build_grounded_text, nearest_today_filing
        day = date.fromisoformat(day_iso)
        filings = await get_sec_recent_filings(
            ticker, forms=("8-K", "6-K"), lookback_days=400, max_filings=30, want_text=True)
        sec = nearest_today_filing(filings, day)
        benz = [n for n in await _benzinga(ticker, day)
                if is_primary_subject_news(n, ticker, profile.get("companyName", ""))][:3]
        text = build_grounded_text(sec, benz, summary or None)
        if text and (sec or benz):
            return text, f"rebuilt_approximate(edgar+benzinga+{summary_src})"
    except Exception as e:
        print(f"  [{ticker}] corpus rebuild failed: {type(e).__name__}: {e}", file=sys.stderr)
    if summary:
        return summary, f"{summary_src}_only"
    return "", "none"


# ── pricing + the call ────────────────────────────────────────────────────────────────────────

def est_cost(prompt: str | None, price: dict) -> float:
    """cost per call = ((prompt_chars / 3.5 + 700 tool tokens) x $in + 600 est. output tokens x $out) / 1e6"""
    if not prompt:
        return 0.0
    tin = len(prompt) / EST_CHARS_PER_TOKEN + EST_TOOL_TOKENS_CLASSIFIER
    return tin / 1e6 * price["input"] + EST_OUT_CLASSIFIER / 1e6 * price["output"]


def _actual_cost(resp, model: str, price: dict) -> float:
    u = getattr(resp, "usage", None)
    tin = getattr(u, "input_tokens", 0) or 0
    tout = getattr(u, "output_tokens", 0) or 0
    try:
        from shared.llm_models import cost_for_call
        return float(cost_for_call(model, tin, tout))
    except Exception:
        return tin / 1e6 * price["input"] + tout / 1e6 * price["output"]


async def ask(client, model: str, price: dict, tool: dict, prompt: str) -> tuple[dict | None, float, str | None]:
    try:
        from shared import llm_samples
        ctx = llm_samples.capture_disabled()
    except Exception:
        import contextlib
        ctx = contextlib.nullcontext()
    try:
        with ctx:
            resp = await asyncio.wait_for(client.messages.create(
                model=model, max_tokens=CLASSIFIER_MAX_TOKENS, tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=[{"role": "user", "content": prompt}]), timeout=120)
    except Exception as e:
        return None, 0.0, f"{type(e).__name__}: {str(e)[:200]}"
    cost = _actual_cost(resp, model, price)
    if getattr(resp, "stop_reason", None) == "max_tokens":
        return None, cost, "truncated"
    block = next((b for b in (resp.content or []) if getattr(b, "type", None) == "tool_use"), None)
    if block is None:
        return None, cost, f"no tool_use (stop_reason={getattr(resp, 'stop_reason', None)})"
    return dict(block.input), cost, None


# ── main ───────────────────────────────────────────────────────────────────────────────────────

async def main(dry_run: bool) -> int:
    from agents.market_intelligence.collector import get_fmp_profile
    from agents.market_intelligence.db import get_pool
    from shared.llm_models import GROUNDED_GRADE_MODEL, pricing_for
    model = GROUNDED_GRADE_MODEL
    price = pricing_for(model)

    keys = [("nominated", t, d) for t, d in ROWS_NOMINATED] + [("stability", t, d) for t, d in ROWS_STABILITY]
    tickers = sorted({t for _, t, _ in keys})
    dates = sorted({date.fromisoformat(d) for _, _, d in keys})
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            shadow_rows = await conn.fetch(SHADOW_SQL, tickers, dates)
            audit_rows = await conn.fetch(
                AUDIT_SQL, datetime(AUDIT_SINCE.year, AUDIT_SINCE.month, AUDIT_SINCE.day, tzinfo=timezone.utc),
                tickers)
    shadow = {(r["ticker"], str(r["scan_date"])): dict(r) for r in shadow_rows}
    excerpts: dict[tuple[str, str], str] = {}
    for r in audit_rows:
        t = (r["summary"] or "").split(" via", 1)[0].strip()
        key = (t, str(r["et_day"]))
        if key not in excerpts:
            excerpts[key] = str(parse_detail(r["detail"]).get("news_summary") or "")

    profiles: dict = {}

    async def _profile(t):
        if t not in profiles:
            profiles[t] = await get_fmp_profile(t) or {}
        return profiles[t]

    # ── phase 1: assemble every prompt ($0) ──
    plan = []
    for arm, t, d in keys:
        profile = await _profile(t)
        sh = shadow.get((t, d))
        rec = {"kind": "regrade", "arm": arm, "ticker": t, "date": d,
               "stored_quality_first": (sh or {}).get("live_quality_first"),
               "stored_quality_last": (sh or {}).get("live_quality_last")}
        try:
            text, prov = await corpus_for(t, d, sh, excerpts.get((t, d), ""), profile)
        except Exception as e:
            text, prov = "", f"error:{type(e).__name__}"
        rec.update(corpus_source=prov, corpus_len=len(text))
        o = old_prompt(t, profile, text) if text else None
        n = new_prompt(t, profile, text) if text else None
        rec["est_cost_usd"] = round(est_cost(o, price) + est_cost(n, price), 5)
        plan.append((rec, o, n))

    n_calls = sum(2 for _, o, _ in plan if o)
    est = sum(r["est_cost_usd"] for r, _, _ in plan)
    print(f"model: {model} (shared.llm_models.GROUNDED_GRADE_MODEL, resolved at run time) at "
          f"${price['input']:.2f} in / ${price['output']:.2f} out per MTok (pricing_for)\n"
          f"cost per call = ((prompt_chars / {EST_CHARS_PER_TOKEN} + {EST_TOOL_TOKENS_CLASSIFIER} tool tokens) "
          f"x ${price['input']:.2f} + {EST_OUT_CLASSIFIER} est. output tokens incl. thinking x "
          f"${price['output']:.2f}) / 1e6\n"
          f"planned model calls: {n_calls} = 2 (OLD + NEW prompt) x {n_calls // 2} rows with text "
          f"({sum(1 for r, o, _ in plan if o and r['arm'] == 'nominated')} nominated + "
          f"{sum(1 for r, o, _ in plan if o and r['arm'] == 'stability')} stability; "
          f"{sum(1 for _, o, _ in plan if not o)} row(s) with no text, skipped)  (cap {MAX_CALLS})\n"
          f"ESTIMATED whole path ${est:.2f}  (abort above ${MAX_COST_USD:.2f})", file=sys.stderr)
    if n_calls > MAX_CALLS or est > MAX_COST_USD:
        print("ABORT: over the call cap or the cost ceiling — nothing was called.", file=sys.stderr)
        for rec, *_ in plan:
            print(json.dumps({**rec, "skipped": "aborted before any call"}, default=str))
        return 2

    client = None
    if not dry_run:
        from shared import llm_client
        llm_client._audit_best_effort = lambda *a, **k: None   # read-only: no rewrite-adoption audit row
        client = llm_client.make_async_anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    state = {"spent": 0.0, "calls": 0, "errors": 0, "skipped": 0}

    async def guarded(tool, prompt):
        if state["calls"] >= MAX_CALLS or state["spent"] + est_cost(prompt, price) > MAX_COST_USD:
            state["skipped"] += 1
            return None, "skipped: cap reached"
        state["calls"] += 1
        raw, cost, err = await ask(client, model, price, tool, prompt)
        state["spent"] += cost
        state["errors"] += err is not None
        return raw, err

    # ── phase 2: ask both prompts on the same text ──
    for rec, o, n in plan:
        if dry_run or not o:
            rec["old_quality"] = rec["new_quality"] = None
        else:
            old_raw, old_err = await guarded(OLD_CATALYST_TOOL, o)
            new_raw, new_err = await guarded(NEW_CATALYST_TOOL, n)
            rec.update(old_quality=(old_raw or {}).get("quality"), old_deal=parse_deal(old_raw),
                       new_quality=(new_raw or {}).get("quality"), new_deal=parse_deal(new_raw),
                       old_analysis=((old_raw or {}).get("analysis") or "")[:300],
                       new_analysis=((new_raw or {}).get("analysis") or "")[:300],
                       old_error=old_err, new_error=new_err)
            rec["flip"] = bool(rec["old_quality"] and rec["new_quality"] and rec["old_quality"] != rec["new_quality"])
        print(json.dumps(rec, default=str))
        sys.stdout.flush()

    print(f"\nmodel calls: {state['calls']}; actual spend ${state['spent']:.2f}; call errors "
          f"{state['errors']}; calls skipped at a cap {state['skipped']}", file=sys.stderr)
    if dry_run:
        print("dry run: no model call made.", file=sys.stderr)
        return 0
    for arm in ("nominated", "stability"):
        rows = [r for r, *_ in plan if r["arm"] == arm and r.get("old_quality")]
        flips = [r for r in rows if r.get("flip")]
        print(f"\n{arm.upper()}: {len(rows)} rows re-graded OLD (10-02 RULE 3) vs NEW (shell-only 'mna'); "
              f"{len(flips)} flip(s). One sample per arm — a flip may be model noise as well as the prompt.",
              file=sys.stderr)
        for r in rows:
            mark = "  <-- FLIP" if r.get("flip") else ""
            print(f"  {r['ticker']:6} {r['date']} {str(r.get('old_quality')):12} -> {str(r.get('new_quality')):12} "
                  f"old deal {'/'.join(r.get('old_deal') or ()) or '-':24} new deal "
                  f"{'/'.join(r.get('new_deal') or ()) or '-':24} ({r['corpus_source']}){mark}", file=sys.stderr)
    bad = [r for r, *_ in plan if r.get("new_quality") == "mna"
           and not ((r.get("new_deal") or ("", ""))[0] == "shell" and (r.get("new_deal") or ("", ""))[1] == "signed")]
    if bad:
        print(f"\n⚠ {len(bad)} row(s) graded 'mna' by the NEW prompt WITHOUT a signed-shell answer (the rule "
              f"not holding): " + ", ".join(f"{r['ticker']} {r['date']}" for r in bad), file=sys.stderr)
    else:
        print("\nNEW prompt graded 'mna' only with a signed-shell answer (or never): the rule holds on this sample.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="#692 ruling 2 regrade (read-only; OLD vs NEW RULE 3)")
    ap.add_argument("--dry-run", action="store_true", help="assemble + estimate only, no model call")
    args = ap.parse_args([a for a in sys.argv[1:] if a != "-"])
    sys.exit(asyncio.run(main(args.dry_run)))
