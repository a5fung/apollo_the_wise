"""Single-source M&A / buyout filter — ONE question, answered, not inferred (#692, 2026-10-02).

Used by every detector that emits actionable trade ideas (EP, flag, 9M sugar-baby, the low-cap
shadow lane, the consolidation anticipation shadow) to reject names whose price is structurally
capped by an announced deal.

THE QUESTION. Is THIS ticker the TARGET of a SIGNED deal that fixes its price? Three facts answer
it — the ticker's ROLE in any deal (target / buyer / shell / none), the deal's STATUS (signed /
proposed / speculation / completed / none) and what the target's holders receive (CONSIDERATION:
cash / stock / mixed / unknown / none). A model answers the facts; the verdict is derived HERE in
code (`deal_pins_price`, pure), so the rule that blocks is one readable function, not a prompt.

WHY (the three rounds this replaces). 2026-07-04: 3 of 4 blocks wrong → #416 guards A/B/C.
2026-08-08: 7 of 8 wrong → #516 guard D. 2026-10-01: 10 of 11 wrong (only ACVA a real buyout) —
FWDI was the BIDDER, CHYM / JBS / SWKS buyers, GPRK / RGTI / IOVA no deal at all, VKTX / WAY
speculation and exploration, CSR an all-stock merger. Each round added a phrase-matching guard
and the error rate did not fall, because the words were never the signal: "definitive agreement"
blocked RGTI's $100M government FUNDING agreement; "takeover" blocked IOVA on a "potential
takeover targets" list; the #284 title regex read ROKU (a target headline) as the acquirer.
Ground truth: docs/analysis/mna_filter_operator_labels_2026-10-01.md.

TWO ANSWERING PATHS, same question, same `DealAnswer`, same verdict:
  1. The EP catalyst grader's own deal fields (ep_detector `_CATALYST_TOOL` — passed in by the
     caller as `deal_answer`). The grader reads the full grounded corpus (SEC 8-K body, Benzinga
     wires, web synthesis), so on the EP path this is the primary answer.
  2. The Polygon headline question (`ask_deal_question`): a cheap $0 keyword pre-filter picks
     candidate articles (`_MNA_KEYWORDS` — its job now is ONLY to choose what gets asked), and
     a small forced-tool call answers the same three facts from that article. Every detector
     gets it through `is_likely_ma(check_polygon=True)`.
The deal-pin PRICE-signature paths (flag_detector: deal_pin_signature / deal_pin_fresh / sticky)
are price evidence of a pinned tape, live outside this module and are untouched.

OPERATOR RULINGS (#692, 2026-10-02 22:20 PDT — "ok" to all seven; each is a named knob here):
  1. `_SHELL_ROLE_PINS` — a signed reverse-merger SHELL blocks (keeps his SUNE 07-04 and CLRO
     08-08 rulings; without it CLRO reads target/signed/stock = CSR, which he ruled wrong).
  2./3. `_PINNING_CONSIDERATIONS` — a signed target paid in cash, cash+stock, or on terms the
     text does not state blocks; an all-stock merger does not fix the price (CSR).
  4. The headline question UNANSWERED (API error, truncation, daily cap, the 9:30-9:45 ORB window
     on the EP scan, the 3-article cap) → PASS + an `mna_headline_unanswered` audit row. Runtime
     toggle `mna_headline_unanswered_blocks`, default OFF = his ruling. Before #692 a keyword
     headline blocked on its own; that changed on his word.
  5. Grade 'mna' with the grader's deal fields blank / out of vocabulary / missing → BLOCK, as
     before #692 (source `claude_classifier_unanswered`).
  6. The 'mna' GRADE means only a signed price-fixing deal (ep_detector RULE 3); every other deal
     is graded on its merit.
  7. A headline overrides the grader ONLY when the grader found no deal (role 'none') or did not
     answer. When the grader answered a deal that does not pin (buyer, proposed, speculation,
     all-stock...), a pinning headline cannot re-block — it is logged as a conflict and passes.
NOT RULED (kept as built, listed for him): grade 'mna' while the grader's own answered fields do
not pin → the fields decide (pass) + an `mna_grade_without_pin` row.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Iterable, NamedTuple, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# ── Candidate pre-filter + shadow comparator (NOT a blocking rule since #692) ─────────────────
# This list no longer decides anything. It (a) picks which Polygon articles get the headline
# question ($0, so a quiet name costs nothing) and (b) powers the `mna_filter_released`
# comparator ("the OLD rule would have blocked here; the answer said no") — without (b) the
# change has no positive observable. Bare "acquire"/"acquisition" stay OUT (removed 2026-05-13
# for direction-blindness); widening the list is a separate, one-variable-at-a-time question
# filed in docs/setups/magna53_ep.md "Known limitations".
_MNA_KEYWORDS: tuple[str, ...] = (
    "buyout", "takeover", "merger", "bought by",
    "being acquired", "definitive agreement", "tender offer", "going private",
    "taken private", "to go private", "strategic transaction", "merger agreement",
    "to be acquired", "all-cash buyout", "halper sadeh",  # shareholder-investigation firm; always follows M&A
    "take-private", "private deal for",
)

# Shareholder-investigation firms — their press releases list multiple tickers (class-action
# notices on already-announced deals, NOT new M&A events). Title-prefix match → never a
# candidate, never asked (Task #90, KALV via BRODSKY & SMITH SHAREHOLDER UPDATE).
_SHAREHOLDER_LITIGATION_PREFIXES: tuple[str, ...] = (
    "brodsky & smith",
    "halper sadeh",
    "pomerantz",
    "johnson fistel",
    "monteverde",
    "bragar eagel",
    "robbins llp",
    "schall law",
    "rosen law",
)


def matches_mna_keywords(text: Optional[str]) -> Optional[str]:
    """Return the first M&A keyword found in `text` (lowercased), else None."""
    if not text:
        return None
    low = text.lower()
    for kw in _MNA_KEYWORDS:
        if kw in low:
            return kw
    return None


def matches_mna_in_any(texts: Iterable[Optional[str]]) -> Optional[tuple[str, int]]:
    """Scan multiple text blobs; return (keyword, index_of_first_hit) or None."""
    for i, t in enumerate(texts):
        kw = matches_mna_keywords(t)
        if kw:
            return kw, i
    return None


def is_shareholder_litigation_notice(title: Optional[str]) -> bool:
    """Title starts with a known shareholder-litigation firm name → True."""
    if not title:
        return False
    low = title.strip().lower()
    return any(low.startswith(prefix) for prefix in _SHAREHOLDER_LITIGATION_PREFIXES)


# ── The answer shape + the decision rule ───────────────────────────────────────────────────────
DEAL_ROLES: tuple[str, ...] = ("target", "buyer", "shell", "none")
DEAL_STATUSES: tuple[str, ...] = ("signed", "proposed", "speculation", "completed", "none")
DEAL_CONSIDERATIONS: tuple[str, ...] = ("cash", "stock", "mixed", "unknown", "none")

#: Operator decisions 2 + 3 (#692): a SIGNED TARGET is pinned when its holders receive a stated
#: cash value (cash / mixed) or the terms are not in the text (unknown — a signed acquisition of
#: a public target is cash in the large majority of cases). An all-stock merger floats with the
#: acquirer's shares and does not fix the price — CSR 2026-09-09, ruled wrongly blocked.
_PINNING_CONSIDERATIONS: frozenset[str] = frozenset({"cash", "mixed", "unknown"})

#: Operator decision 1 (#692): a signed reverse-merger SHELL blocks. Exists ONLY to honour his two
#: true-positive rulings — SUNE 2026-06-08 ("definitive reverse merger with Suniva") and CLRO
#: 2026-07-02 (Vivani's subsidiary Cortigent merging into Nasdaq-listed ClearOne). Without it CLRO
#: reads target / signed / stock — indistinguishable from CSR — so no target-only rule can honour
#: both rulings. Not part of his recorded direction ("target / buyer / none"): his call.
_SHELL_ROLE_PINS: bool = True


class DealAnswer(NamedTuple):
    """One answer to the question, from either path. `source_text` carries the model's one-line
    note (headline path) — what in the text decided the status — for the audit trail."""
    role: str
    status: str
    consideration: str
    counterparty: str = ""
    source_text: str = ""


def deal_pins_price(a: Optional[DealAnswer]) -> bool:
    """THE decision rule (pure). True → the filter blocks. None (unanswered) → False."""
    if a is None or a.status != "signed":
        return False
    if a.role == "target":
        return a.consideration in _PINNING_CONSIDERATIONS
    if a.role == "shell":
        return _SHELL_ROLE_PINS
    return False


def deal_answer_from_fields(fields: Any, *, note_key: str = "") -> Optional[DealAnswer]:
    """Parse a tool's `input` dict into a DealAnswer. None when any of the three enums is missing
    or outside its vocabulary — an out-of-vocabulary answer is UNANSWERED, never a guess."""
    if not isinstance(fields, dict):
        return None
    role = str(fields.get("deal_role") or "").strip().lower()
    status = str(fields.get("deal_status") or "").strip().lower()
    consideration = str(fields.get("deal_consideration") or "").strip().lower()
    if role not in DEAL_ROLES or status not in DEAL_STATUSES or consideration not in DEAL_CONSIDERATIONS:
        return None
    note = str(fields.get(note_key) or "")[:300] if note_key else ""
    return DealAnswer(role, status, consideration,
                      str(fields.get("deal_counterparty") or "")[:120], note)


def deal_fields(a: Optional[DealAnswer]) -> dict:
    """The answer as audit-telemetry keys (empty dict for an unanswered None)."""
    if a is None:
        return {}
    out = {"role": a.role, "status": a.status, "consideration": a.consideration,
           "counterparty": a.counterparty}
    if a.source_text:
        out["note"] = a.source_text
    return out


# ── The shared field definitions (ONE wording for both tools) ─────────────────────────────────
# ep_detector._CATALYST_TOOL spreads these between `quality` and `analysis`; the headline tool
# below uses them with a short `note` last. Verdict fields come before any free-text field.
DEAL_FIELD_PROPERTIES: dict[str, dict] = {
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
DEAL_FIELD_NAMES: tuple[str, ...] = tuple(DEAL_FIELD_PROPERTIES)

_HEADLINE_TOOL_NAME = "classify_deal_headline"
_HEADLINE_TOOL: dict = {
    "name": _HEADLINE_TOOL_NAME,
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
        "required": [*DEAL_FIELD_NAMES, "note"],
    },
}


def build_headline_prompt(ticker: str, company_name: Optional[str], item: dict,
                          reasoning: Optional[str]) -> str:
    """The headline question's user message (one article, this ticker only)."""
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


# ── The headline question: memo + daily budget + EP-only ORB-window skip ──────────────────────
#: Process-level daily budget on headline-question model calls, ALL callers together. The EP tick
#: re-runs the filters every 5 min for a filter-killed name (#405), so the per-article memo below
#: is what keeps one headline to one call per day; the budget bounds the worst case (~$4/day at
#: ~$0.01 a call on sonnet-5-5 — typical days spend a few cents). Raised 40 → 400 by the #692
#: fix round: 40 was never measured, and a spent budget means every later question that day
#: goes unanswered (= pass, ruling 4).
_HEADLINE_QUESTION_CALLS_CAP = 400
#: Of that budget, this many calls are RESERVED for the EP scan (the money path): every other
#: caller (flag scan, low-cap lane, anticipation, 9M) stops at CAP - RESERVE, so a shadow lane
#: can never spend the EP path's questions.
_HEADLINE_EP_RESERVE = 100
_HEADLINE_BUDGET_POOLS: tuple[str, ...] = ("ep", "shared")
#: A failing article is retried at most this many times per ET day, then left unanswered —
#: otherwise one persistently failing article could spend the whole daily budget.
_HEADLINE_MAX_ATTEMPTS_PER_ARTICLE = 2
#: Wall-clock bound on one question AND on one ticker's whole scan (the ≤3 articles are asked
#: concurrently under one deadline) — the call sits on the EP scan path.
_HEADLINE_TIMEOUT_S = 20.0
#: Candidate articles asked per ticker per check (newest first). Older candidates are recorded
#: as UNANSWERED (why='article_cap') — never dropped without a trace.
_HEADLINE_MAX_ARTICLES = 3

# (ticker, article key, ET day) -> answer; attempts per key; the day's call counter + which
# budget pools already wrote their cap-hit audit row today.
_HEADLINE_MEMO: dict[tuple[str, str, str], DealAnswer] = {}
_HEADLINE_ATTEMPTS: dict[tuple[str, str, str], int] = {}
_HEADLINE_DAY: dict[str, Any] = {"day": None, "calls": 0, "cap_logged": set()}

# Cross-call memo of filing-ticker company names (immutable). None is a cached "no name".
_COMPANY_NAME_MEMO: dict[str, Optional[str]] = {}

_headline_client = None


def _get_headline_client():
    global _headline_client
    if _headline_client is None:
        import os
        from shared.llm_client import make_async_anthropic
        _headline_client = make_async_anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _headline_client


def reset_headline_day() -> None:
    """Forget today's memo, attempts, call count and cap-hit flags (day rollover; tests)."""
    _HEADLINE_MEMO.clear()
    _HEADLINE_ATTEMPTS.clear()
    _HEADLINE_DAY["day"] = None
    _HEADLINE_DAY["calls"] = 0
    _HEADLINE_DAY["cap_logged"] = set()


def _roll_headline_day(day: date) -> None:
    if _HEADLINE_DAY["day"] != day:
        reset_headline_day()
        _HEADLINE_DAY["day"] = day


def _budget_cap(pool: str) -> int:
    """The day's call ceiling for a budget pool: the EP scan may spend the whole budget; every
    other caller stops short of the EP reserve."""
    if pool == "ep":
        return _HEADLINE_QUESTION_CALLS_CAP
    return _HEADLINE_QUESTION_CALLS_CAP - _HEADLINE_EP_RESERVE


async def _log_cap_hit(pool: str, day: date) -> None:
    """One `mna_headline_cap_hit` audit row per budget pool per ET day — no Telegram (the
    questions it leaves unanswered pass under ruling 4 and are audited row by row). Never raises."""
    if pool in _HEADLINE_DAY["cap_logged"]:
        return
    _HEADLINE_DAY["cap_logged"].add(pool)   # set BEFORE the await: concurrent asks log once
    try:
        if not await _first_today("mna_headline_cap_hit", f"{pool}: %"):
            return
        from agents.market_intelligence.db import log_audit_event
        await log_audit_event(
            "mna_headline_cap_hit",
            f"{pool}: M&A headline-question budget spent ({_HEADLINE_DAY['calls']} calls, "
            f"{pool} ceiling {_budget_cap(pool)}) — later questions today go unanswered and pass",
            json.dumps({"pool": pool, "calls": _HEADLINE_DAY["calls"], "ceiling": _budget_cap(pool),
                        "et_day": day.isoformat()}))
    except Exception as e:  # loud-ok: telemetry must never change the filter verdict
        logger.warning(f"mna_headline_cap_hit audit failed: {e}")


def _article_key(item: dict) -> str:
    title = (item.get("title") or "").encode("utf-8", "ignore")
    return f"{item.get('published_utc') or ''}|{hashlib.sha1(title).hexdigest()[:12]}"


def _in_orb_window(now_et: datetime) -> bool:
    """The 9:30-9:45 ET ORB-submission window — ONE definition, ep_detector._in_orb_cutoff.
    Imported lazily: ep_detector imports this module at its top."""
    try:
        from agents.market_intelligence.ep_detector import _in_orb_cutoff
        return bool(_in_orb_cutoff(now_et))
    except Exception:  # loud-ok: a missing helper must not block the filter; logged
        logger.warning("ma_filter: ORB-window helper unavailable — treating as outside the window")
        return False


def _call_would_touch_orb(now_et: datetime) -> bool:
    """A call started now is IN the window when it starts inside it OR its timeout would carry it
    past 9:30 ET (a call started at 9:29:50 must not delay the 9:30/9:31 scans)."""
    return _in_orb_window(now_et) or _in_orb_window(now_et + timedelta(seconds=_HEADLINE_TIMEOUT_S))


async def ask_deal_question(
    ticker: str,
    item: dict,
    *,
    company_name: Optional[str] = None,
    reasoning: Optional[str] = None,
    now_et: Optional[datetime] = None,
    skip_in_orb: bool = False,
    budget_pool: str = "shared",
) -> tuple[Optional[DealAnswer], str]:
    """Ask the deal question about ONE article. Returns (answer, how):
    how ∈ {"answered", "memo"} with an answer, or an UNANSWERED reason with None —
    "orb_window" (only when `skip_in_orb`), "daily_cap", "gave_up", "error:<Exc>", "truncated",
    "no_tool_use", "invalid". Never raises.
    `skip_in_orb` — set ONLY by the EP scan (`ep_detector._post_grade_filters`): no new call
    inside 9:30-9:45 ET or one whose timeout would cross 9:30. Every other caller is asked.
    `budget_pool` — "ep" (the EP scan; may spend the whole daily budget) or "shared" (everyone
    else; stops short of the EP reserve)."""
    now = now_et or datetime.now(_ET)
    day = now.date()
    _roll_headline_day(day)
    key = (ticker, _article_key(item), day.isoformat())
    if key in _HEADLINE_MEMO:
        return _HEADLINE_MEMO[key], "memo"
    if _HEADLINE_ATTEMPTS.get(key, 0) >= _HEADLINE_MAX_ATTEMPTS_PER_ARTICLE:
        return None, "gave_up"
    if skip_in_orb and _call_would_touch_orb(now):
        return None, "orb_window"
    pool = budget_pool if budget_pool in _HEADLINE_BUDGET_POOLS else "shared"
    if _HEADLINE_DAY["calls"] >= _budget_cap(pool):
        await _log_cap_hit(pool, day)
        return None, "daily_cap"
    _HEADLINE_DAY["calls"] += 1
    _HEADLINE_ATTEMPTS[key] = _HEADLINE_ATTEMPTS.get(key, 0) + 1

    from shared.llm_models import GROUNDED_GRADE_MODEL
    from shared.llm_response import is_truncated
    from shared.output_ceilings import max_tokens_for
    try:
        response = await asyncio.wait_for(
            _get_headline_client().messages.create(
                model=GROUNDED_GRADE_MODEL,  # the grader's own tier (Haiku confabulated on raw headlines, #190)
                max_tokens=max_tokens_for("mna_headline_question"),
                tools=[_HEADLINE_TOOL],
                tool_choice={"type": "tool", "name": _HEADLINE_TOOL_NAME},
                messages=[{"role": "user", "content": build_headline_prompt(
                    ticker, company_name, item, reasoning)}],
            ),
            timeout=_HEADLINE_TIMEOUT_S,
        )
    except Exception as e:  # loud-ok: UNANSWERED is a first-class outcome, audited by the caller
        logger.warning(f"{ticker}: M&A headline question failed — {type(e).__name__}: {e}")
        return None, f"error:{type(e).__name__}"
    try:
        from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
        await log_anthropic_call_safe(model=GROUNDED_GRADE_MODEL, caller="mna_headline_question",
                                      response=response)
    except Exception as e:  # loud-ok: spend logging must never change the answer
        logger.warning(f"{ticker}: headline-question spend log failed: {e}")
    if is_truncated(response):
        return None, "truncated"
    block = next((b for b in (getattr(response, "content", None) or [])
                  if getattr(b, "type", None) == "tool_use"), None)
    if block is None:
        return None, "no_tool_use"
    answer = deal_answer_from_fields(getattr(block, "input", None), note_key="note")
    if answer is None:
        return None, "invalid"
    _HEADLINE_MEMO[key] = answer
    return answer, "answered"


class HeadlineScan(NamedTuple):
    """What the headline path found for one ticker: the first pinning hit (or None), every
    candidate that was answered without a pin, and every candidate left unanswered."""
    hit: Optional[dict]
    released: list
    unanswered: list
    candidates_n: int


def _candidate_articles(
    ticker: str, items: list[dict], insights_missing: Optional[list] = None,
) -> list[tuple[dict, str, str, Optional[str]]]:
    """$0 candidate selection: (item, match_path, keyword, this ticker's insight reasoning).
    A title keyword → 'title'; a description / insight-reasoning keyword → 'description+insights'
    ONLY when this ticker is in the article's `insights` (the #88 multi-ticker bleed guard — a
    roundup that only insights another company is never asked about). Litigation notices skip.
    `insights_missing`, when given, collects the titles skipped because Polygon had not graded
    the article at all (the #88 false-negative telemetry `_b88_mna_filter_path_b_fp_rate` counts)."""
    out = []
    for item in items:
        title = item.get("title") or ""
        if is_shareholder_litigation_notice(title):
            continue
        insights = item.get("insights") or []
        ticker_insight = next((i for i in insights if i.get("ticker") == ticker), None)
        reasoning = (ticker_insight or {}).get("sentiment_reasoning") or None
        title_kw = matches_mna_keywords(title)
        if title_kw:
            out.append((item, "title", title_kw, reasoning))
            continue
        body_kw = matches_mna_keywords(item.get("description")) or matches_mna_keywords(reasoning)
        if body_kw and ticker_insight is not None:
            out.append((item, "description+insights", body_kw, reasoning))
        elif body_kw and not insights and insights_missing is not None:
            insights_missing.append(title)
    out.sort(key=lambda c: c[0].get("published_utc") or "", reverse=True)
    return out


async def _company_name(ticker: str) -> Optional[str]:
    if ticker not in _COMPANY_NAME_MEMO:
        try:
            from agents.market_intelligence.collector import get_ticker_details
            details = await get_ticker_details(ticker)
            _COMPANY_NAME_MEMO[ticker] = (details or {}).get("name") or None
        except Exception as e:  # loud-ok: the question still runs on the ticker alone
            logger.debug(f"{ticker}: company-name lookup failed: {e}")
            return None
    return _COMPANY_NAME_MEMO[ticker]


async def headline_deal_scan(
    ticker: str,
    *,
    lookback_days: int = 14,
    on_or_before: Optional[date] = None,
    now_et: Optional[datetime] = None,
    skip_in_orb: bool = False,
    budget_pool: str = "shared",
) -> HeadlineScan:
    """Fetch recent Polygon news, pick keyword candidates ($0), and ask the deal question on the
    `_HEADLINE_MAX_ARTICLES` newest of them CONCURRENTLY under one overall deadline. The hit is
    the newest candidate whose answer pins. Candidates past the cap, and asks still running at
    the deadline, are recorded UNANSWERED (why='article_cap' / 'deadline') — never dropped."""
    from agents.market_intelligence.collector import get_polygon_news

    items = await get_polygon_news(
        ticker, lookback_days=lookback_days, on_or_before=on_or_before, limit=20)
    missing: list = []
    candidates = _candidate_articles(ticker, items or [], insights_missing=missing)
    for title in missing:   # unchanged #88 telemetry (one row per skipped article, as before)
        try:
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event(
                "polygon_news_insights_missing",
                f"{ticker} skipped Path B — no insights field on '{title[:120]}'")
        except Exception as e:  # loud-ok: telemetry must never change the verdict
            logger.debug(f"{ticker}: insights-missing audit failed: {e}")
    released: list = []
    unanswered: list = []
    if not candidates:
        return HeadlineScan(None, released, unanswered, 0)
    company = await _company_name(ticker)

    def _meta(item: dict, match_path: str, kw: str) -> dict:
        return {
            "match_path": match_path,
            "matched_keyword": kw,
            "title": (item.get("title") or "")[:200],
            "published_utc": item.get("published_utc", ""),
            "publisher": item.get("publisher", ""),
        }

    asked = candidates[:_HEADLINE_MAX_ARTICLES]
    tasks = [asyncio.ensure_future(ask_deal_question(
        ticker, item, company_name=company, reasoning=reasoning, now_et=now_et,
        skip_in_orb=skip_in_orb, budget_pool=budget_pool)) for item, _mp, _kw, reasoning in asked]
    done, pending = await asyncio.wait(tasks, timeout=_HEADLINE_TIMEOUT_S)
    for t in pending:
        t.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    hit = None
    for task, (item, match_path, kw, _reasoning) in zip(tasks, asked):
        meta = _meta(item, match_path, kw)
        if task not in done or task.cancelled() or task.exception() is not None:
            unanswered.append({**meta, "why": "deadline"})
            continue
        answer, how = task.result()
        if answer is None:
            unanswered.append({**meta, "why": how})
        elif deal_pins_price(answer):
            if hit is None:   # newest pinning candidate (asked newest first)
                hit = {"source": "polygon_headline_model", "ticker": ticker, **meta,
                       **deal_fields(answer)}
        else:
            released.append({**meta, **deal_fields(answer)})
    for item, match_path, kw, _reasoning in candidates[_HEADLINE_MAX_ARTICLES:]:
        unanswered.append({**_meta(item, match_path, kw), "why": "article_cap"})
    return HeadlineScan(hit, released, unanswered, len(candidates))


async def polygon_news_has_mna_headline(
    ticker: str,
    *,
    lookback_days: int = 14,
    on_or_before: Optional[date] = None,
) -> Optional[dict]:
    """The first Polygon article whose deal answer pins this ticker's price, or None."""
    scan = await headline_deal_scan(ticker, lookback_days=lookback_days, on_or_before=on_or_before)
    return scan.hit


# ── Audit dedup (one row per ticker per ET day per event) ──────────────────────────────────────

async def _first_today(event_type: str, summary_like: str) -> bool:
    """True if no `event_type` row whose summary matches `summary_like` exists today (ET).
    Fail-open: a DB error returns True (over-log rather than drop)."""
    try:
        from agents.market_intelligence.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            prior = await conn.fetchrow("""
                SELECT 1 FROM mi_audit_log
                WHERE event_type = $1
                  AND summary LIKE $2
                  AND (created_at AT TIME ZONE 'America/New_York')::date
                      = (NOW() AT TIME ZONE 'America/New_York')::date
                LIMIT 1
            """, event_type, summary_like)
        return prior is None
    except Exception as e:
        logger.debug(f"{event_type} audit dedup check failed (non-critical): {e}")
        return True


async def should_log_mna_filter_fired(ticker: str, detector_tag: str) -> bool:
    """Trading-day dedup for `mna_filter_fired` per (ticker, detector) — #89 (2026-05-23): the
    detectors call is_likely_ma every scan tick, so without it the audit inflates 5-20x.
    Summary contract: every call site writes `{ticker} via <source> ({detector_tag})`."""
    return await _first_today("mna_filter_fired", f"{ticker} via%({detector_tag})%")


async def should_log_mna_released(ticker: str) -> bool:
    """Trading-day dedup for `mna_filter_released` (summary starts with `{ticker}: `)."""
    return await _first_today("mna_filter_released", f"{ticker}: %")


async def _audit_once(event_type: str, ticker: str, summary: str, detail: dict) -> None:
    """Write one dedup'd audit row (`{ticker}: ...` summaries). Never raises."""
    try:
        if not await _first_today(event_type, f"{ticker}: %"):
            return
        from agents.market_intelligence.db import log_audit_event
        await log_audit_event(event_type, f"{ticker}: {summary}"[:300],
                              json.dumps({"ticker": ticker, **detail}, default=str)[:4000])
    except Exception as e:  # loud-ok: telemetry must never change the filter verdict
        logger.warning(f"{ticker}: {event_type} audit failed: {e}")


async def _unanswered_blocks() -> bool:
    """Operator ruling 4 (2026-10-02, RULED) — an unanswered headline question PASSES (+ an
    `mna_headline_unanswered` row). The toggle stays so the ruling is one flip to reverse;
    its default OFF IS the ruling. Literal name + env so scripts/live_rules.py discovers it."""
    try:
        from agents.market_intelligence.db import get_runtime_toggle
        return bool(await get_runtime_toggle("mna_headline_unanswered_blocks",
                                             "MNA_HEADLINE_UNANSWERED_BLOCKS", default=False))
    except Exception as e:  # loud-ok: fail direction = the ruled default (pass), logged
        logger.warning(f"mna_headline_unanswered_blocks read failed → default OFF: {e}")
        return False


def _answer_str(a: Optional[DealAnswer]) -> str:
    return f"{a.role}/{a.status}/{a.consideration}" if a is not None else "no grader answer"


# ── The single entry point every detector calls ───────────────────────────────────────────────

async def is_likely_ma(
    ticker: str,
    *,
    deal_answer: Optional[DealAnswer] = None,
    check_polygon: bool = True,
    polygon_lookback_days: int = 14,
    on_or_before: Optional[date] = None,
    catalyst_quality: Optional[str] = None,
    catalyst_texts: Optional[list[Optional[str]]] = None,
    now_et: Optional[datetime] = None,
    skip_in_orb: bool = False,
    budget_pool: str = "shared",
) -> tuple[bool, Optional[dict]]:
    """Is THIS ticker's price fixed by a signed deal? Returns (block, telemetry).

    1. `deal_answer` (the EP grader's deal fields) pins → block, source `claude_deal_fields`.
    2. Ruling 5: the grader graded 'mna' but its deal fields are missing / out of vocabulary
       (`deal_answer is None`) → block, as before #692, source `claude_classifier_unanswered`.
    3. The headline question (`check_polygon=True`, ≤3 newest keyword candidates). Ruling 7: a
       pinning headline blocks ONLY when the grader found no deal (role 'none') or did not
       answer (None — a failed grade, or a non-EP caller). When the grader answered a deal that
       does not pin, a pinning headline is logged as a conflict and PASSES. Ruling 4: candidates
       left UNANSWERED pass (+ an audit row) unless `mna_headline_unanswered_blocks` is ON.
    `catalyst_texts` decide NOTHING: with `catalyst_quality` they feed the `mna_filter_released`
    comparator (the names the pre-#692 rule would have blocked, plus every grader-answered deal
    that does not pin — the under-fire surface of the monthly review).
    `skip_in_orb` / `budget_pool` — set ONLY by the EP scan (see `ask_deal_question`).
    """
    if deal_answer is not None and deal_pins_price(deal_answer):
        return True, {
            "source": "claude_deal_fields",
            "match_path": "claude_deal_fields",
            "ticker": ticker,
            **deal_fields(deal_answer),
        }
    if catalyst_quality == "mna":
        if deal_answer is None:
            # Ruling 5: the grade said 'mna' and the deal fields are blank — block as before.
            return True, {
                "source": "claude_classifier_unanswered",
                "match_path": "claude_classifier_unanswered",
                "ticker": ticker,
                "catalyst_quality": catalyst_quality,
            }
        # NOT RULED (kept as built): 'mna' graded while the grader's OWN answered fields do not
        # pin. The fields decide; this row makes the mismatch countable (EXPECT ~0/week).
        await _audit_once(
            "mna_grade_without_pin", ticker,
            f"graded 'mna' but its deal fields do not pin — {_answer_str(deal_answer)}",
            {"grader": deal_fields(deal_answer)})

    # Ruling 7: did the grader find a deal (any role but 'none')? Then a headline cannot re-block.
    grader_found_deal = deal_answer is not None and deal_answer.role != "none"
    scan = HeadlineScan(None, [], [], 0)
    if check_polygon:
        scan = await headline_deal_scan(
            ticker, lookback_days=polygon_lookback_days, on_or_before=on_or_before, now_et=now_et,
            skip_in_orb=skip_in_orb, budget_pool=budget_pool)
        if scan.hit:
            if grader_found_deal:
                await _audit_once(
                    "mna_deal_answers_conflict", ticker,
                    f"grader read {_answer_str(deal_answer)}, headline pinned "
                    f"({scan.hit.get('role')}/{scan.hit.get('status')}) — passed (ruling 7: "
                    "the grader's deal answer governs)",
                    {"grader": deal_fields(deal_answer), "headline": scan.hit, "blocked": False})
            else:
                if deal_answer is not None:
                    await _audit_once(
                        "mna_deal_answers_conflict", ticker,
                        f"grader read {_answer_str(deal_answer)}, headline pinned "
                        f"({scan.hit.get('role')}/{scan.hit.get('status')}) — blocked",
                        {"grader": deal_fields(deal_answer), "headline": scan.hit, "blocked": True})
                return True, scan.hit
        elif scan.unanswered and not grader_found_deal:
            blocks = await _unanswered_blocks()
            await _audit_once(
                "mna_headline_unanswered", ticker,
                f"{len(scan.unanswered)} candidate article(s) unanswered "
                f"({scan.unanswered[0].get('why')}) — {'BLOCKED' if blocks else 'passed'}",
                # `blocked` first and the list bounded: the row is cut at 4000 chars, and the
                # monthly review reads this row's verdict.
                {"blocked": blocks, "unanswered_n": len(scan.unanswered),
                 "unanswered": scan.unanswered[:5]})
            if blocks:
                first = scan.unanswered[0]
                return True, {"source": "polygon_headline_unanswered", "ticker": ticker,
                              **{k: v for k, v in first.items() if k != "why"},
                              "unanswered_why": first.get("why")}

    # Shadow comparator — (a) the pre-#692 rule: the grader said 'mna', a keyword sat in the
    # catalyst text, or a keyword headline was answered; (b) the grader answered a deal that
    # does not pin (role != 'none') — NOT an old-rule block, but every such release is a name
    # the monthly review must be able to see. New rule passed → record why.
    old_rule = []
    if catalyst_quality == "mna":
        old_rule.append("grade_mna")
    kw_hit = matches_mna_in_any(catalyst_texts or [])
    if kw_hit:
        old_rule.append(f"keyword_in_text_{kw_hit[1]}:{kw_hit[0]}")
    if scan.released or scan.hit:
        old_rule.append("headline_keyword")
    old_reasons = list(old_rule)
    if grader_found_deal:
        old_reasons.append("grader_deal_no_pin")
    if old_reasons:
        lead = ("old rule would have blocked (" + ", ".join(old_rule) + ")" if old_rule
                else "released for review (the grader answered a deal that does not pin)")
        await _audit_once(
            "mna_filter_released", ticker,
            f"{lead}; grader read {_answer_str(deal_answer)}"
            + (f"; {len(scan.released)} headline(s) answered no pin" if scan.released else "")
            + ("; a pinning headline was overruled (ruling 7)" if scan.hit else ""),
            {"old_reasons": old_reasons, "old_rule_would_block": bool(old_rule),
             "grader": deal_fields(deal_answer), "headlines": scan.released,
             "overruled_headline": scan.hit, "unanswered_n": len(scan.unanswered)})
    return False, None
