"""#692 replay — ask the NEW deal question of every M&A-filter decision since 2026-05-15, on prod,
and decide each ticker-day with the LIVE rule (the operator's seven rulings of 2026-10-02).

SELF-CONTAINED by design: the #692 branch is NOT deployed, so this file EMBEDS the branch's new
classifier prompt (RULE 3), both tool schemas, the candidate pre-filter and the live decision rule
verbatim, plus origin/main's OLD grader tool + RULE 3 for the grade-stability pass (tests on the
branch — tests/test_mna_replay_692.py — fail if any copy drifts from the code). It imports only
helpers that already exist in the deployed image (db pool, Polygon / SEC / FMP fetchers, the LLM
client factory, shared.llm_models), always INSIDE functions, never at load time.

RUN (on the box; the script arrives on stdin — no checkout needed):
    # 1. $0 pass: assemble every question, print the priced whole path, NO model call
    docker exec -i apollo-market python - --dry-run < replay_target_question.py \\
        > replay_dry.jsonl 2> replay_dry.log
    # 2. the paid pass (ONE run; capture once, read many)
    docker exec -i apollo-market python - < replay_target_question.py \\
        > replay_results.jsonl 2> replay_run.log

WHAT IT ASKS (the live rule ORs two answers, so the replay asks both):
  * EVERY EP ticker-day: the GRADER question (the new classify_catalyst tool on the fullest stored
    text) AND the HEADLINE scan (Polygon re-fetched with on_or_before = that day, 14-day lookback;
    the 3 newest keyword candidates asked newest first, stopping at the first pin — the same
    verdict as live's concurrent ask). Both answers are kept in the record.
  * Every other ticker-day (flag / 9M / anticipation / acquirer-skip rows): the headline scan
    alone, 21-day lookback, as live.
  * Price-signature days (deal_pin_signature / deal_pin_fresh only): no call — that path is out of
    #692's scope and unchanged (still BLOCK).
  The verdict is `live_verdict` — is_likely_ma's order exactly: grader pins → BLOCK; grade 'mna'
  with blank deal fields → BLOCK (ruling 5); a pinning headline blocks only when the grader found
  no deal or did not answer (ruling 7); an unanswered headline passes (ruling 4).
  Grader text, fullest first: mi_catalyst_tier_shadow.grounded_head (>= 2026-08-24, the corpus
  the live grade read) → a rebuild from EDGAR 8-K/6-K + Benzinga + the shadow row's news_summary
  with its claude_analysis appended (APPROXIMATE — the Perplexity answer is unrecoverable) → that
  shadow text alone → the 200-char audit excerpt ONLY when no shadow row exists. `corpus_source`
  says which.

GRADE-STABILITY PASS (ruling 6): ~30 recent NON-deal rows of mi_catalyst_tier_shadow (grade not
'mna', not an M&A-filter ticker-day, no M&A keyword in the stored text) are re-graded with the OLD
tool + RULE 3 (origin/main fbf181b7, verbatim) and the NEW one; every quality flip is listed.
One sample per arm — a flip can be model noise as well as the prompt (not separable here).

GUARANTEES
  * READ-ONLY on the DB: three SELECTs inside a READ ONLY transaction. No spend-tracker row, no
    audit row (the adapter's rewrite-adoption audit is switched off in-process), no sample capture.
  * Model = shared.llm_models.GROUNDED_GRADE_MODEL resolved at run time (the live grader's id),
    through shared.llm_client.make_async_anthropic, hard cap MAX_CALLS calls.
  * The WHOLE path (grader + headline upper bound + stability) is priced from
    shared.llm_models.pricing_for and printed BEFORE the first call; the run aborts above $6.00
    and stops mid-run if spending would cross it.
  * stdout = one JSON line per record (kind = "ticker_day" | "grade_stability").
    stderr = the estimate, progress and the summary: labelled acceptance, the MUST-SHOW rows for
    HIS labelling, the stability flips.

WHAT THIS DOES NOT ANSWER: whether a released name would have been TRADED; misses the filter never
blocked (the population is its decisions only); stability of the deal answer itself (one call per
question is one sample of a stochastic model). Labels are the operator's; every unlabelled row —
the MUST-SHOW block included — is for HIS sign-off, never a finding.
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

SINCE = date(2026, 5, 15)
SHADOW_SINCE = date(2026, 8, 24)        # #593: the shadow table's stored text starts here
MAX_CALLS = 700                         # ≤ 108 grader + 3 x 151 headline + 60 stability = 621
MAX_COST_USD = 6.00
CLASSIFIER_MAX_TOKENS = 1500   # = output ceiling ep_catalyst_grade
HEADLINE_MAX_TOKENS = 1000     # = output ceiling mna_headline_question
CLASSIFIER_MAX_CHARS = 6000    # the lean grader's corpus window
HEADLINE_MAX_ARTICLES = 3      # = ma_filter._HEADLINE_MAX_ARTICLES
EP_LOOKBACK_DAYS, OTHER_LOOKBACK_DAYS = 14, 21
STABILITY_N = 30
# Estimation: chars per input token, tool-schema tokens, and output tokens per call INCLUDING
# always-on thinking (opus-5-5 measured ~176 on a ~100-token answer; the grade's analysis adds ~150).
EST_CHARS_PER_TOKEN = 3.5
EST_TOOL_TOKENS_CLASSIFIER, EST_TOOL_TOKENS_HEADLINE = 700, 500
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
                    "company-specific catalyst. mna: ONLY when deal_role is shell AND deal_status "
                    "is signed — this listed company is the vehicle of a signed reverse merger. A "
                    "buyout TARGET, signed or proposed, is graded on its own merit; a separate M&A "
                    "filter decides it on price, not the grade."
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



# ── VERBATIM from origin/main fbf181b7 (the pre-#692 grader) — the stability pass's OLD arm ─────
OLD_CATALYST_TOOL = {
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
                    "company-specific catalyst. mna: merger, acquisition, buyout, takeover, "
                    "going-private, tender offer, or any deal where the company is being acquired — "
                    "price is capped at deal value, no momentum trade possible."
                ),
            },
            "analysis": {
                "type": "string",
                "description": "2-3 sentences on the specific catalyst and classification rationale.",
            },
        },
        "required": ["quality", "analysis"],
    },
}

OLD_RULE_3 = """3. If the catalyst is a MERGER, ACQUISITION, BUYOUT, TAKEOVER, TENDER OFFER, GOING-PRIVATE, or any
   deal where the company is being acquired — classify as "mna". This is a hard skip: price is capped
   at deal value, there is no momentum trade. Keywords: "definitive agreement", "to be acquired",
   "tender offer", "going private", "taken private", "strategic transaction", "buyout", "merger agreement"."""

# ── VERBATIM from the #692 branch (agents/market_intelligence/ep_detector.py, RULE 3) ──────────
NEW_RULE_3 = """3. DEAL FIELDS — answer about THIS company only.
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
   Grade "mna" ONLY when deal_role is 'shell' AND deal_status is 'signed' — the listed vehicle of a
   signed reverse merger, the one case where the grade itself carries the verdict. A TARGET of a deal
   — signed or proposed, whatever the consideration — is graded on its own merit under rules 1, 2, 4
   and 5: a separate M&A filter reads its price and decides, not the grade. The same goes for a
   buyer, an all-stock merger, or a deal that involves another company."""


def _grader_prompt(ticker: str, profile: dict, grounded_text: str | None, rule_3: str,
                   max_chars: int = CLASSIFIER_MAX_CHARS) -> str:
    """ep_detector._classify_catalyst_claude's prompt (grounded-text form); only RULE 3 differs
    between origin/main and the #692 branch."""
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


def classifier_prompt(ticker: str, profile: dict, grounded_text: str | None,
                      max_chars: int = CLASSIFIER_MAX_CHARS) -> str:
    """The #692 branch's grader prompt."""
    return _grader_prompt(ticker, profile, grounded_text, NEW_RULE_3, max_chars)


def old_classifier_prompt(ticker: str, profile: dict, grounded_text: str | None,
                          max_chars: int = CLASSIFIER_MAX_CHARS) -> str:
    """origin/main fbf181b7's grader prompt (the stability pass's OLD arm)."""
    return _grader_prompt(ticker, profile, grounded_text, OLD_RULE_3, max_chars)


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



# ── VERBATIM rule (ma_filter.deal_pins_price / deal_answer_from_fields / is_likely_ma) ─────────

def deal_pins_price(role: str | None, status: str | None, consideration: str | None) -> bool:
    """ma_filter.deal_pins_price on the branch."""
    if status != "signed":
        return False
    if role == "target":
        return consideration in PINNING_CONSIDERATIONS
    if role == "shell":
        return SHELL_ROLE_PINS
    return False


def parse_deal(fields) -> tuple[str, str, str] | None:
    """ma_filter.deal_answer_from_fields: (role, status, consideration), or None when any of the
    three is missing / out of vocabulary (= UNANSWERED, never a guess)."""
    if not isinstance(fields, dict):
        return None
    role = str(fields.get("deal_role") or "").strip().lower()
    status = str(fields.get("deal_status") or "").strip().lower()
    cons = str(fields.get("deal_consideration") or "").strip().lower()
    if role not in DEAL_ROLES or status not in DEAL_STATUSES or cons not in DEAL_CONSIDERATIONS:
        return None
    return role, status, cons


def deal_nominates(role: str | None, status: str | None, consideration: str | None) -> bool:
    """ma_filter.deal_nominates on the branch (2026-10-03): a target, signed OR proposed, on
    pinning terms — blocked on the news alone until a price reading can release it."""
    return role == "target" and status in ("signed", "proposed") and consideration in PINNING_CONSIDERATIONS


def headline_acts(role, status, consideration) -> bool:
    """ma_filter._headline_acts: a nomination or a signed shell."""
    return deal_nominates(role, status, consideration) or deal_pins_price(role, status, consideration)


def live_verdict(grade: str | None, grader: tuple[str, str, str] | None,
                 headline: list[tuple[str, str, str] | None]) -> tuple[str, str]:
    """ma_filter.is_likely_ma's decision WITHOUT a price reading (the pre-market / no-reader
    case), in its order — the operator's rulings of 2026-10-02 plus the 2026-10-03 timing ruling
    (a proposed target now blocks on the news until the open window can release it).
    `grade` — the grader's quality (None when the grader was not asked or the call FAILED: live
    reads a failed grade as 'routine', so ruling 5 never fires on it); `grader` — its parsed deal
    answer (None = unanswered); `headline` — the asked articles' parsed answers, newest first
    (None = unanswered). Returns (BLOCK|PASS, why)."""
    if grader is not None and headline_acts(*grader):
        return "BLOCK", "claude_deal_fields"
    if grade == "mna" and grader is None:
        return "BLOCK", "claude_classifier_unanswered"            # ruling 5
    grader_found_deal = grader is not None and grader[0] != "none"
    headline_pins = any(a is not None and headline_acts(*a) for a in headline)
    if headline_pins:
        if grader_found_deal:
            return "PASS", "headline_pin_overruled_by_grader_deal"  # ruling 7
        return "BLOCK", "polygon_headline_model"
    if any(a is None for a in headline) and not grader_found_deal:
        return "PASS", "headline_unanswered"                       # ruling 4
    return "PASS", "no_pin"


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


# Rows HE must see on the sign-off page with the old vs new verdict and the answers — agent-read
# (the reviews' lens 5): signed cash targets that must stay blocked (SYNA), all-stock / tied
# targets released by design (LBRDA / LBRDK), proposal-stage take-privates (NUVL, HZO, RNW, PZZA),
# names whose recall moved from the retired keyword path to the grader (DSGN, PD), and the
# plumbing shapes. NEVER labels — he labels them. Any other day where an answer reads
# target / proposed (a proposal-stage take-private) is added at run time.
MUST_SHOW_TICKERS = frozenset({
    "SYNA", "DV", "UTZ", "CRNX", "FBRX", "NUVL", "DFH", "BANF", "MAIR", "THR", "CECO", "ROKU",
    "DSGN", "QBTS", "LBRDA", "LBRDK", "HZO", "RNW", "PZZA", "PD",
})


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
# The stability sample's candidates (pre-#692 columns only — the deal_* columns do not exist on
# prod until the branch deploys). Filtered further in Python: not an M&A-filter ticker-day, no
# M&A keyword in the stored text, one row per ticker, newest first.
STABILITY_SQL = """
    SELECT scan_date, ticker, grounded_head, grounded_len, claude_analysis,
           live_quality_first, live_quality_last
    FROM mi_catalyst_tier_shadow
    WHERE scan_date >= $1
      AND grounded_head IS NOT NULL AND length(grounded_head) >= 200
      AND COALESCE(live_quality_first, '') <> 'mna' AND COALESCE(live_quality_last, '') <> 'mna'
    ORDER BY scan_date DESC, last_seen_et DESC
    LIMIT 400
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
    """(text, corpus_source). Fullest stored text first; a rebuild is APPROXIMATE. The shadow
    row's news_summary + claude_analysis outrank the 200-char audit excerpt, which is read only
    when no shadow row exists."""
    if shadow and shadow.get("grounded_head"):
        full = (shadow.get("grounded_len") or 0) <= len(shadow["grounded_head"])
        return shadow["grounded_head"], ("stored_grade_corpus" if full else "stored_grade_corpus_first_6000")
    if shadow is not None:
        summary = "\n".join(t for t in (shadow.get("news_summary"), shadow.get("claude_analysis")) if t)
        summary_src = "shadow_summary+analysis"
    else:
        summary = td.get("news_summary") or ""
        summary_src = "audit_excerpt_200_chars"
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
            return text, f"rebuilt_approximate(edgar+benzinga+{summary_src})"
    except Exception as e:
        print(f"  [{td['ticker']}] corpus rebuild failed: {type(e).__name__}: {e}", file=sys.stderr)
    if summary:
        return summary, f"{summary_src}_only"
    return "", "none"


async def headline_candidates(td: dict, lookback: int) -> list[tuple[dict, str, str, str | None]]:
    """Every keyword candidate Polygon held for this ticker-day (on_or_before = that day — exact
    replay of what the scan could see), newest first."""
    from agents.market_intelligence.collector import get_polygon_news
    items = await get_polygon_news(td["ticker"], lookback_days=lookback,
                                   on_or_before=date.fromisoformat(td["date"]), limit=20)
    return candidate_articles(td["ticker"], items or [])


def _article_rec(item: dict, mp: str, kw: str, reasoning: str | None, fired_titles: list) -> dict:
    t = (item.get("title") or "")[:120].strip().lower()
    return {"title": item.get("title"), "published_utc": item.get("published_utc"),
            "publisher": item.get("publisher"), "match_path": mp, "matched_keyword": kw,
            "description": item.get("description"), "reasoning": reasoning,
            "is_the_fired_title": any((f or "")[:120].strip().lower() == t for f in fired_titles)}


def price_signature_only(td: dict) -> bool:
    """Blocked ONLY by the deal-pin price-signature paths (flag detector) — out of #692's scope."""
    blocked_by = set(td["sources"]) - {"veto_516", "acquirer_skip_284"}
    return bool(blocked_by) and all(s.startswith("deal_pin") for s in blocked_by)


def old_decision(td: dict) -> str:
    return "BLOCK" if "mna_filter_fired" in td["events"] else "PASS"


_DEAL_WORDS = re.compile(r"\bacquir|\bacquisition|\bmerg|\btakeover|\bbuyout|\btender offer", re.I)


def select_stability_rows(rows, mna_days) -> list[dict]:
    """~STABILITY_N recent NON-deal grades: not an M&A-filter ticker-day, no M&A keyword or deal
    word in the stored corpus / analysis, not a failed grade; one row per ticker, newest first."""
    out, seen = [], set()
    for r in rows:
        r = dict(r)
        t, d = r["ticker"], str(r["scan_date"])
        if t in seen or (t, d) in mna_days:
            continue
        text = f"{r.get('grounded_head') or ''}\n{r.get('claude_analysis') or ''}"
        if matches_mna_keywords(text) or _DEAL_WORDS.search(text) or "Classification failed" in text:
            continue
        seen.add(t)
        out.append(r)
        if len(out) >= STABILITY_N:
            break
    return out


def _est_cost(prompt: str | None, tool_tokens: int, est_out: int, price: dict) -> float:
    if not prompt:
        return 0.0
    tin = len(prompt) / EST_CHARS_PER_TOKEN + tool_tokens
    return tin / 1e6 * price["input"] + est_out / 1e6 * price["output"]


def _actual_cost(resp, model: str, price: dict) -> float:
    u = getattr(resp, "usage", None)
    tin = getattr(u, "input_tokens", 0) or 0
    tout = getattr(u, "output_tokens", 0) or 0
    try:
        from shared.llm_models import cost_for_call
        return float(cost_for_call(model, tin, tout))
    except Exception:
        return tin / 1e6 * price["input"] + tout / 1e6 * price["output"]


async def ask(client, model: str, price: dict, tool: dict, prompt: str,
              max_tokens: int) -> tuple[dict | None, float, str | None]:
    try:
        from shared import llm_samples
        ctx = llm_samples.capture_disabled()
    except Exception:
        import contextlib
        ctx = contextlib.nullcontext()
    try:
        with ctx:
            resp = await asyncio.wait_for(client.messages.create(
                model=model, max_tokens=max_tokens, tools=[tool],
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


def _fmt(a) -> str:
    return "/".join(a) if a else "unanswered"


def _must_show(rec: dict) -> bool:
    if rec["ticker"] in MUST_SHOW_TICKERS:
        return True
    answers = [rec.get("grader_parsed")] + [h.get("parsed") for h in rec.get("headline_asked", [])]
    return any(a and a[0] == "target" and a[1] == "proposed" for a in answers)


# ── main ───────────────────────────────────────────────────────────────────────────────────────

async def main(dry_run: bool) -> int:
    from agents.market_intelligence.collector import get_fmp_profile, get_ticker_details
    from agents.market_intelligence.db import get_pool
    from shared.llm_models import GROUNDED_GRADE_MODEL, pricing_for
    model = GROUNDED_GRADE_MODEL
    price = pricing_for(model)

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(POP_SQL, datetime(SINCE.year, SINCE.month, SINCE.day,
                                                      tzinfo=timezone.utc))
            days = build_ticker_days(rows)
            tickers = sorted({t for t, _ in days})
            shadow_rows = await conn.fetch(SHADOW_SQL, SHADOW_SINCE, tickers)
            stab_rows = await conn.fetch(STABILITY_SQL, SHADOW_SINCE)
    shadow = {(r["ticker"], str(r["scan_date"])): dict(r) for r in shadow_rows}
    print(f"population: {len(rows)} audit rows -> {len(days)} ticker-days "
          f"({sum(1 for td in days.values() if old_decision(td) == 'BLOCK')} blocked)", file=sys.stderr)

    profiles: dict = {}
    names: dict = {}

    async def _profile(t):
        if t not in profiles:
            profiles[t] = await get_fmp_profile(t) or {}
        return profiles[t]

    async def _name(t):
        if t not in names:
            names[t] = (await get_ticker_details(t) or {}).get("name")
        return names[t]

    # ── phase 1: assemble every question ($0) ──
    plan = []
    for key in sorted(days, key=lambda k: (k[1], k[0])):
        td = days[key]
        ep_day = "ep" in td["detectors"]
        rec = {"kind": "ticker_day", "ticker": td["ticker"], "date": td["date"],
               "detectors": sorted(td["detectors"]), "old_paths": sorted(set(td["sources"])),
               "old_match_paths": sorted(td["match_paths"]), "old_grade": td["catalyst_quality"],
               "old_decision": old_decision(td), "ep_day": ep_day, "label": LABELS.get(key)}
        grader_prompt, headline_qs = None, []
        try:
            if price_signature_only(td):
                rec["arm"] = "price_signature"
            else:
                rec["arm"] = "ep: grader + headline" if ep_day else "headline"
                if ep_day:
                    profile = await _profile(td["ticker"])
                    text, prov = await classifier_corpus(td, shadow.get(key), profile)
                    rec.update(corpus_source=prov, corpus_len=len(text),
                               corpus=text[:CLASSIFIER_MAX_CHARS])
                    if text:
                        grader_prompt = classifier_prompt(td["ticker"], profile, text)
                cands = await headline_candidates(
                    td, EP_LOOKBACK_DAYS if ep_day else OTHER_LOOKBACK_DAYS)
                rec["headline_candidates_n"] = len(cands)
                company = await _name(td["ticker"]) if cands else None
                for item, mp, kw, reasoning in cands[:HEADLINE_MAX_ARTICLES]:
                    headline_qs.append((_article_rec(item, mp, kw, reasoning, td["titles"]),
                                        headline_prompt(td["ticker"], company, item, reasoning)))
                rec["headline_article_cap"] = [
                    (item.get("title") or "")[:200] for item, *_ in cands[HEADLINE_MAX_ARTICLES:]]
                rec["fired_title_among_asked"] = any(a["is_the_fired_title"] for a, _ in headline_qs)
        except Exception as e:
            rec["assembly_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        rec["est_cost_usd_upper"] = round(
            _est_cost(grader_prompt, EST_TOOL_TOKENS_CLASSIFIER, EST_OUT_CLASSIFIER, price)
            + sum(_est_cost(p, EST_TOOL_TOKENS_HEADLINE, EST_OUT_HEADLINE, price)
                  for _, p in headline_qs), 5)
        plan.append((rec, grader_prompt, headline_qs))

    stab_plan = []
    for r in select_stability_rows(stab_rows, set(days)):
        profile = await _profile(r["ticker"])
        rec = {"kind": "grade_stability", "ticker": r["ticker"], "date": str(r["scan_date"]),
               "stored_quality_first": r.get("live_quality_first"),
               "stored_quality_last": r.get("live_quality_last"),
               "corpus_len": len(r["grounded_head"] or "")}
        old_p = old_classifier_prompt(r["ticker"], profile, r["grounded_head"])
        new_p = classifier_prompt(r["ticker"], profile, r["grounded_head"])
        rec["est_cost_usd"] = round(
            _est_cost(old_p, EST_TOOL_TOKENS_CLASSIFIER, EST_OUT_CLASSIFIER, price)
            + _est_cost(new_p, EST_TOOL_TOKENS_CLASSIFIER, EST_OUT_CLASSIFIER, price), 5)
        stab_plan.append((rec, old_p, new_p))

    # ── price the WHOLE path before the first call ──
    n_grader = sum(1 for _, g, _ in plan if g)
    n_head = sum(len(h) for _, _, h in plan)
    n_stab = 2 * len(stab_plan)
    n_calls = n_grader + n_head + n_stab
    est_grader = sum(_est_cost(g, EST_TOOL_TOKENS_CLASSIFIER, EST_OUT_CLASSIFIER, price)
                     for _, g, _ in plan if g)
    est_head = sum(_est_cost(p, EST_TOOL_TOKENS_HEADLINE, EST_OUT_HEADLINE, price)
                   for _, _, h in plan for _, p in h)
    est_stab = sum(r["est_cost_usd"] for r, _, _ in stab_plan)
    est = est_grader + est_head + est_stab
    print(f"model: {model} (shared.llm_models.GROUNDED_GRADE_MODEL, resolved at run time) at "
          f"${price['input']:.2f} in / ${price['output']:.2f} out per MTok (pricing_for)\n"
          f"cost per call = ((prompt_chars / {EST_CHARS_PER_TOKEN} + tool_tokens) x ${price['input']:.2f}"
          f" + est_output_tokens x ${price['output']:.2f}) / 1e6;  tool_tokens grader "
          f"{EST_TOOL_TOKENS_CLASSIFIER} / headline {EST_TOOL_TOKENS_HEADLINE}; est_output (incl. "
          f"thinking) grader {EST_OUT_CLASSIFIER} / headline {EST_OUT_HEADLINE}\n"
          f"planned model calls (UPPER BOUND — the headline scan stops at the first pin): "
          f"{n_calls} = {n_grader} grader + {n_head} headline + {n_stab} stability "
          f"({len(stab_plan)} rows x old/new)  (cap {MAX_CALLS})\n"
          f"ESTIMATED whole path ${est:.2f} = grader ${est_grader:.2f} + headline ${est_head:.2f} "
          f"+ stability ${est_stab:.2f}  (abort above ${MAX_COST_USD:.2f})", file=sys.stderr)
    if n_calls > MAX_CALLS or est > MAX_COST_USD:
        print("ABORT: over the call cap or the cost ceiling — nothing was called.", file=sys.stderr)
        for rec, *_ in plan + stab_plan:
            print(json.dumps({**rec, "new_decision": None, "skipped": "aborted before any call"},
                             default=str))
        return 2

    client = None
    if not dry_run:
        from shared import llm_client
        llm_client._audit_best_effort = lambda *a, **k: None   # read-only: no rewrite-adoption audit row
        client = llm_client.make_async_anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    state = {"spent": 0.0, "calls": 0, "errors": 0, "skipped": 0}

    async def guarded(tool, prompt, max_tok, est_out, tool_tokens):
        if state["calls"] >= MAX_CALLS or \
                state["spent"] + _est_cost(prompt, tool_tokens, est_out, price) > MAX_COST_USD:
            state["skipped"] += 1
            return None, "skipped: cap reached"
        state["calls"] += 1
        raw, cost, err = await ask(client, model, price, tool, prompt, max_tok)
        state["spent"] += cost
        state["errors"] += err is not None
        return raw, err

    # ── phase 2: ask (grader, then the headline scan newest first, stop at the first pin) ──
    for rec, grader_prompt, headline_qs in plan:
        if rec["arm"] == "price_signature":
            rec["new_decision"] = "BLOCK (price-signature path, out of #692 scope - unchanged)"
        elif dry_run:
            rec["new_decision"] = None
        else:
            grade, grader, skipped = None, None, False
            if grader_prompt:
                raw, err = await guarded(CATALYST_TOOL, grader_prompt, CLASSIFIER_MAX_TOKENS,
                                         EST_OUT_CLASSIFIER, EST_TOOL_TOKENS_CLASSIFIER)
                skipped |= bool(err and err.startswith("skipped"))
                # live: no quality → the grade raises → 'routine', and no deal answer is kept
                grade = (raw or {}).get("quality") or None
                grader = parse_deal(raw) if grade else None
                rec.update(grader_answer=raw, grader_parsed=grader, grader_grade=grade,
                           grader_error=err)
            answers, asked = [], []
            for art, prompt in headline_qs:
                raw, err = await guarded(HEADLINE_TOOL, prompt, HEADLINE_MAX_TOKENS,
                                         EST_OUT_HEADLINE, EST_TOOL_TOKENS_HEADLINE)
                skipped |= bool(err and err.startswith("skipped"))
                parsed = parse_deal(raw)
                answers.append(parsed)
                asked.append({**art, "answer": raw, "parsed": parsed, "error": err})
                if parsed is not None and deal_pins_price(*parsed):
                    break
            else:
                answers += [None] * len(rec.get("headline_article_cap") or [])   # live: article_cap
            rec["headline_asked"] = asked
            if skipped:
                rec["new_decision"] = "INCOMPLETE (a call was skipped at the cost / call cap)"
            else:
                rec["new_decision"], rec["new_why"] = live_verdict(grade, grader, answers)
        print(json.dumps(rec, default=str))
        sys.stdout.flush()
        print(f"  {rec['ticker']:6} {rec['date']} {rec['old_decision']:5} -> "
              f"{str(rec.get('new_decision'))[:12]:12} {str(rec.get('new_why') or ''):40} "
              f"{rec.get('label') or ''}", file=sys.stderr)

    for rec, old_p, new_p in stab_plan:
        if not dry_run:
            old_raw, old_err = await guarded(OLD_CATALYST_TOOL, old_p, CLASSIFIER_MAX_TOKENS,
                                             EST_OUT_CLASSIFIER, EST_TOOL_TOKENS_CLASSIFIER)
            new_raw, new_err = await guarded(CATALYST_TOOL, new_p, CLASSIFIER_MAX_TOKENS,
                                             EST_OUT_CLASSIFIER, EST_TOOL_TOKENS_CLASSIFIER)
            rec.update(old_quality=(old_raw or {}).get("quality"),
                       new_quality=(new_raw or {}).get("quality"),
                       new_deal=parse_deal(new_raw), old_analysis=(old_raw or {}).get("analysis"),
                       new_analysis=(new_raw or {}).get("analysis"), old_error=old_err,
                       new_error=new_err)
            rec["flip"] = bool(rec["old_quality"] and rec["new_quality"]
                               and rec["old_quality"] != rec["new_quality"])
        print(json.dumps(rec, default=str))
        sys.stdout.flush()

    # ── summary (stderr) ──
    print(f"\nmodel calls: {state['calls']}; actual spend ${state['spent']:.2f}; call errors "
          f"{state['errors']}; calls skipped at a cap {state['skipped']}", file=sys.stderr)
    if dry_run:
        print("dry run: no model call made.", file=sys.stderr)
        return 0
    from collections import Counter
    moves = Counter((r["old_decision"], str(r.get("new_decision"))[:5]) for r, _, _ in plan)
    print("old -> new verdicts: " + ", ".join(f"{o}->{n}: {c}" for (o, n), c in sorted(moves.items())),
          file=sys.stderr)
    # The DoD's acceptance, on the labelled rows only (every other row is HIS to label).
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

    print("\nMUST-SHOW — for HIS labelling (agent-read, NOT labels): old -> new, the answers, the text",
          file=sys.stderr)
    for rec, *_ in sorted(plan, key=lambda p: (p[0]["ticker"], p[0]["date"])):
        if not _must_show(rec):
            continue
        heads = "; ".join(f"{_fmt(h.get('parsed'))} '{(h.get('title') or '')[:60]}'"
                          for h in rec.get("headline_asked", [])) or "no candidate asked"
        print(f"  {rec['ticker']:6} {rec['date']} {rec['old_decision']} -> {rec.get('new_decision')} "
              f"({rec.get('new_why') or ''}) | grader: {_fmt(rec.get('grader_parsed'))} "
              f"grade {rec.get('grader_grade')} | headline: {heads} | text: "
              f"{rec.get('corpus_source') or '-'}", file=sys.stderr)

    flips = [r for r, _, _ in stab_plan if r.get("flip")]
    print(f"\nGRADE STABILITY (ruling 6): {len(stab_plan)} non-deal rows re-graded old vs new prompt; "
          f"{len(flips)} quality flip(s). One sample per arm — a flip may be model noise as well as "
          f"the prompt.", file=sys.stderr)
    for r in flips:
        print(f"  {r['ticker']:6} {r['date']} {r['old_quality']} -> {r['new_quality']} "
              f"(stored {r['stored_quality_last']}; new deal answer {_fmt(r.get('new_deal'))})",
              file=sys.stderr)
    new_mna = [r for r, _, _ in stab_plan if r.get("new_quality") == "mna"]
    if new_mna:
        print(f"  ⚠ {len(new_mna)} non-deal row(s) graded 'mna' by the NEW prompt: "
              + ", ".join(r["ticker"] for r in new_mna), file=sys.stderr)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="#692 replay (read-only; grader + headline per EP day)")
    ap.add_argument("--dry-run", action="store_true", help="assemble + estimate only, no model call")
    args = ap.parse_args([a for a in sys.argv[1:] if a != "-"])
    sys.exit(asyncio.run(main(args.dry_run)))
