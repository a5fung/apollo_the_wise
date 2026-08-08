"""Single-source M&A / buyout / take-private filter.

Used by every detector that emits actionable trade ideas (EP, flag, 9M, etc.)
to reject names whose momentum is structurally capped by an announced deal —
price is pinned at the deal value, no further gain available.

Two layers:

1. **Catalyst keyword scan** — `matches_mna_keywords(text)` walks `_MNA_KEYWORDS`
   over any text source. Drives Claude/Perplexity catalyst summaries on EP, and
   raw Polygon news titles on flag/9M (which don't run an LLM catalyst pass).

2. **Polygon news backstop** — when Perplexity hedges ("no specific news") and
   Claude grades `routine`, the keyword scan has no text to match. AVNS 5/4
   surfaced this gap: Polygon had the 4/14 "Avanos To Go Private" headline the
   whole time. Fetching Polygon titles directly closes the coverage gap.

Future Layer 3 (filed as data-gated review `flag_ma_pin_filter`): deal-pin
price signature — median daily (H-L)/close < ~0.3% across 7+ of 10 sessions.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# Keep this list as the single canonical source — every detector reads from here.
#
# Target-direction only: every keyword below should imply the ticker is the
# TARGET of a deal, not the acquirer. Bare "acquire" / "acquisition" were
# removed 2026-05-13 after NBIS (acquired Eigen AI for $643M; NBIS = buyer)
# was wrongly filtered. 90d backtest: 13 acquirer-side FPs vs 2 real targets
# already covered by Claude `catalyst_quality='mna'` (EBAY) or `"take-private"`
# (WEN). See ma_filter.py change log + magna53_ep.md 2026-05-13.
_MNA_KEYWORDS: tuple[str, ...] = (
    "buyout", "takeover", "merger", "bought by",
    "being acquired", "definitive agreement", "tender offer", "going private",
    "taken private", "to go private", "strategic transaction", "merger agreement",
    "to be acquired", "all-cash buyout", "halper sadeh",  # shareholder-investigation firm; always follows M&A
    "take-private", "private deal for",
)

# Shareholder-investigation firms — their press releases list multiple tickers
# (often class-action notices on already-announced deals, NOT new M&A events).
# Title-prefix match → reject regardless of M&A keyword. Caught 2026-05-25
# Task #90 audit (KALV via BRODSKY & SMITH SHAREHOLDER UPDATE).
_SHAREHOLDER_LITIGATION_PREFIXES: tuple[str, ...] = (
    "brodsky & smith",
    "halper sadeh",       # already in _MNA_KEYWORDS but also gets prefix reject
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


# ── #416 binding-context guards (operator-signed 7/12, rulings-pack R6) ────────────────────────
# The filter SUPPRESSES a candidate only when an M&A signal is a BINDING deal that pins THIS ticker
# as the TARGET. The three ratified false-positives were three ways that failed, one per fire-path:
#   Guard A (keyword_in_text): a NEGATED/SPECULATIVE keyword ("not a takeover", "takeout speculation")
#   Guard B (polygon Path B): EXPLORATION/agitation ("proxy campaign seeking strategic alternatives")
#   Guard C (claude_classifier): ACQUIRER-side / completed-deal ("Mistral acquisition closing")
# Each is a per-path veto that falls through to the other independent paths — a real deal still fires.
# The shared escape is a BINDING-deal marker (SUNE's "definitive reverse merger" keeps firing).
# Full evidence + N-gate sim: docs/analysis/416_mna_fp_amendment_2026-07-12.md.
_MNA_NEGATOR = re.compile(
    r"\b(not|no|never|without|rather than|unlike|denies|denied|isn't|wasn't|aren't|weren't)\b", re.I)
_MNA_SPECULATION = re.compile(
    r"\b(speculation|speculative|rumou?r|reportedly|potential(?:ly)?|exploring|explore|"
    r"talks|considering|could|takeout)\b", re.I)
_MNA_EXPLORATION = re.compile(
    r"\b(strategic alternatives?|proxy campaign|activist|exploring options|seeking strategic|"
    r"strategic review)\b", re.I)
_MNA_BINDING = re.compile(
    r"\b(definitive|agreed to|agreement to acquire|to be acquired|tender offer|going private|"
    r"completed (?:the )?acquisition|merger agreement|will acquire|has acquired|acquired by)\b", re.I)
_MNA_ACQUIRER_SIDE = re.compile(
    r"\b(acquisition clos\w*|completed (?:the |its )?acquisition|acquired \w+ for|prime.contract)\b", re.I)
_MNA_TARGET_SIDE = re.compile(
    r"\b(to be acquired|acquired by|takeover target|being acquired|going private)\b", re.I)


def mna_context_is_binding(text: Optional[str]) -> bool:
    """The shared escape: a binding-deal marker present → a real price-pin, not exploration/speculation.
    (SUNE's 'definitive reverse merger' → True → keeps firing; FRMI's 'strategic alternatives' → False.)"""
    return bool(text and _MNA_BINDING.search(text))


def keyword_context_is_nonbinding(text: Optional[str], kw: Optional[str]) -> bool:
    """Guard A: the matched keyword sits in a NEGATED (within ~25 chars before) or SPECULATIVE
    (±60-char window) context, with NO binding-deal escape anywhere in the text. MMED: 'not a single
    dramatic takeover' → True (veto). IMAX/WEN/IMVT: 'takeout speculation' → True (veto)."""
    if not text or not kw:
        return False
    if mna_context_is_binding(text):
        return False
    low = text.lower()
    i = low.find(kw.lower())
    if i < 0:
        return False
    pre = low[max(0, i - 25):i]
    win = low[max(0, i - 60):i + 60]
    return bool(_MNA_NEGATOR.search(pre) or _MNA_SPECULATION.search(win))


def reasoning_is_exploration_only(reasoning: Optional[str]) -> bool:
    """Guard B: polygon Path B reasoning is exploration/agitation with no binding-deal escape.
    FRMI: 'proxy campaign seeking strategic alternatives' → True (veto)."""
    return bool(reasoning and _MNA_EXPLORATION.search(reasoning)
                and not mna_context_is_binding(reasoning))


def text_implies_acquirer_or_completed(texts: Iterable[Optional[str]]) -> bool:
    """Guard C: the classifier's catalyst text frames THIS ticker as the ACQUIRER or a COMPLETED deal
    (ONDS: 'Mistral acquisition closing' — bullish growth, not a target price-pin). Suppressed when
    the text also reads target-side ('to be acquired', 'acquired by') — then it IS a pinned target."""
    blob = " ".join(t for t in texts if t) if texts else ""
    if not blob or not _MNA_ACQUIRER_SIDE.search(blob):
        return False
    return not _MNA_TARGET_SIDE.search(blob)


def is_shareholder_litigation_notice(title: Optional[str]) -> bool:
    """Title starts with a known shareholder-litigation firm name → True.

    These firms publish multi-ticker investigation notices on
    *already-announced* deals; their press releases are informational, not
    indicative of an active fade-risk M&A event for any tagged ticker.
    """
    if not title:
        return False
    low = title.strip().lower()
    return any(low.startswith(prefix) for prefix in _SHAREHOLDER_LITIGATION_PREFIXES)


# Direction-detection patterns for ticker's per-article role.
# Operate on Polygon's per-ticker `sentiment_reasoning` (richer than title
# alone — it's the AI's contextualized take on this specific ticker's role
# in the article). All matches case-insensitive substring.
_TARGET_DIRECTION_PATTERNS: tuple[str, ...] = (
    "to be acquired",
    "being acquired",
    "acquired by",
    "stockholders to receive",
    "shareholders to receive",
    "merger consideration",
    "go-private",
    "going private",
    "taken private",
    "premium to ",
    "tender offer for ",
    "agreed to sell",
    "to be sold to",
    "sold to ",
    "buyout offer",
    "all-cash offer",
)

_ACQUIRER_DIRECTION_PATTERNS: tuple[str, ...] = (
    " to acquire ",
    " acquires ",
    " acquiring ",
    "announces acquisition",
    "announced acquisition",
    "announces the acquisition",
    "completes acquisition",
    "completed acquisition",
    "agreed to acquire",
    "agreement to acquire",
    " to purchase ",
    "announces purchase",
    "to buy ",
    " buys ",
    "announces the purchase",
)


def classify_direction(reasoning: Optional[str]) -> str:
    """Classify ticker's deal direction from per-ticker reasoning text.

    Returns one of: "target" / "acquirer" / "ambiguous".

    Target patterns checked BEFORE acquirer because " to acquire " can appear
    in target-side reasoning (e.g. "X agreed to be acquired by Y" — ticker X
    is target despite "acquire" in the sentence).
    """
    if not reasoning:
        return "ambiguous"
    low = reasoning.lower()
    for p in _TARGET_DIRECTION_PATTERNS:
        if p in low:
            return "target"
    for p in _ACQUIRER_DIRECTION_PATTERNS:
        if p in low:
            return "acquirer"
    return "ambiguous"


def _ticker_is_acquirer(item: dict, ticker: str, reasoning: Optional[str] = None) -> bool:
    """Return True if Polygon insights identify this ticker as the deal buyer.

    Used by both title-match (Path A) and description-match (Path B) acceptance
    to suppress acquirer-side fires (CECO-class). Missing insights → return
    False (conservative: preserve title-match acceptance when no signal).

    `reasoning` may be passed by callers that already extracted it; else
    looked up here from the per-ticker insight entry.
    """
    if reasoning is None:
        insights = item.get("insights") or []
        ticker_insight = next(
            (i for i in insights if i.get("ticker") == ticker),
            None,
        )
        if ticker_insight is None:
            return False
        reasoning = ticker_insight.get("sentiment_reasoning") or ""
    return classify_direction(reasoning) == "acquirer"


# Acquirer-direction on the TITLE (Path A) — #284, 2026-06-14.
# The 2026-05-13 fix removed bare "acquire"/"acquisition" keywords but left
# buyout/merger/definitive-agreement direction-blind on TITLES, and
# `_ticker_is_acquirer` only inspects per-ticker REASONING. So acquirer-side
# title matches with absent/ambiguous reasoning leak through (ONDS 5/28
# "...With Omnisys Buyout" = Ondas is the BUYER, graded strong on a real
# earnings gap, suppressed; MYRG "...to Acquire Valley Electric").
_ACQUIRER_OBJECT_NOUNS: tuple[str, ...] = ("buyout", "acquisition", "takeover")
# Tokens that can immediately precede an acquirer-noun but are NOT a company
# entity, so "<word> Buyout" must NOT be read as "<entity> Buyout" (acquirer
# object form). Two kinds: deal adjectives ("Cash/Management Buyout") and
# Title-Case headline verbs/preps ("Acme Receives Buyout Offer" — 'Receives'
# is capitalized in Title Case but is a verb, not the bought entity).
_GENERIC_ACQ_PRECEDERS: frozenset[str] = frozenset({
    # deal adjectives / generic nouns
    "cash", "stock", "management", "leveraged", "pending", "proposed",
    "potential", "all", "the", "a", "an", "its", "their", "company",
    "majority", "minority", "strategic", "private", "secondary", "partial",
    # Title-Case headline verbs / prepositions that precede the noun
    "receives", "received", "announces", "announced", "completes", "completed",
    "enters", "entered", "agrees", "agreed", "rejects", "rejected", "accepts",
    "accepted", "confirms", "confirmed", "explores", "explored", "considers",
    "considered", "eyes", "weighs", "plans", "planned", "approves", "approved",
    "finalizes", "finalized", "seeks", "secures", "secured", "launches",
    "launched", "nears", "faces", "after", "amid", "following", "in", "for",
    "of", "on", "via", "through", "with", "and", "to", "from",
})


# Corporate suffixes stripped from the filing company name before anchoring, so
# "MYR Group Inc." anchors on "myr" not the generic "group/inc". (Drift sibling:
# collector._GENERIC_NAME_TOKENS does the same strip for is_primary_subject_news;
# keep roughly in sync — consolidation deferred to avoid a circular import.)
_CORP_SUFFIXES: frozenset[str] = frozenset({
    "group", "inc", "incorporated", "corp", "corporation", "co", "company",
    "holdings", "holding", "ltd", "limited", "plc", "llc", "lp", "sa", "nv",
    "ag", "se", "the", "and", "of",
})

# Object-form acquirer pattern, precompiled once. Scoped (?i:) on the NOUN only —
# the entity must be Capitalized (a global re.IGNORECASE would make [A-Z] match
# lowercase and defeat the entity signal); the noun matches any case.
_OBJECT_FORM_RE = re.compile(
    r"\b([A-Z][A-Za-z][A-Za-z.&-]*)\s+(?i:buyout|acquisition|takeover)\b"
)

# Cross-call memo of filing-ticker company names (immutable; #284). Avoids a
# get_ticker_details Polygon round-trip on every scan tick for a persistent
# acquirer-side headline. None is a cached "no name" (won't retry).
_COMPANY_NAME_MEMO: dict[str, Optional[str]] = {}


def title_implies_acquirer(
    title: Optional[str],
    filing_company_name: Optional[str] = None,
) -> bool:
    """True when the article TITLE indicates the FILING ticker is the deal
    ACQUIRER (buyer), not the target — so the M&A pin filter should NOT fire
    (an acquirer's momentum is not price-capped). #284.

    A headline is NOT per-ticker, so direction is anchored on the filing
    company's POSITION relative to the deal verb/noun — otherwise 'BigCo to
    Acquire Acme' (filed under target Acme) would read as acquirer. Without the
    company name we cannot anchor, so we return False (conservative — fire).

    Safety is NOT uniform across the two signals (corrected 6/14 after /simplify):
      - VERB form IS asymmetric-safe: the target-guard runs first and the
        acquirer verb must FOLLOW the filing co, so a target never converts to
        a pass.
      - OBJECT form is a BENIGN-FAILURE heuristic, NOT bulletproof: a Title-Case
        headline verb/adjective before the noun ('Acme Mulls Buyout', 'Acme
        Spurns Sweetened Buyout') can be misread as a bought entity and mis-pass
        a noun-form target. `_GENERIC_ACQ_PRECEDERS` narrows but cannot close
        this (no NER/name-map available). Failure is benign — a mis-passed
        target is price-capped (small/quick loss, paper) — and every pass emits
        `mna_acquirer_title_skipped`, surfaced for operator FP review by
        `scripts/mna_filter_accuracy_review.py` (the monitored backstop).

    Both signals require the filing co to appear BEFORE them:
      1. Verb form — an acquirer verb after the filing co ('MYR Group ... to
         Acquire Valley').
      2. Object form — an acquirer-noun preceded by a Capitalized non-filing
         entity, after the filing co ('Ondas ... Omnisys Buyout' -> buys Omnisys).
    """
    if not title or not filing_company_name:
        return False
    filing_tokens = {
        t.lower() for t in re.split(r"[^A-Za-z]+", filing_company_name)
        if len(t) > 1 and t.lower() not in _CORP_SUFFIXES
    }
    if not filing_tokens:
        return False
    low = title.lower()
    positions = [p for t in filing_tokens if (p := low.find(t)) >= 0]
    if not positions:
        return False  # filing company not named in the title -> can't anchor
    co_pos = min(positions)

    # TARGET guard FIRST — any target-side phrase means the filing side is (or
    # may be) the one being acquired; stay conservative and let it fire.
    if classify_direction(low) == "target":
        return False

    # 1. Acquirer VERB after the filing company (filing co is the subject).
    for ap in _ACQUIRER_DIRECTION_PATTERNS:
        if low.find(ap) > co_pos:
            return True

    # 2. Acquirer OBJECT form: "<OtherEntity> <noun>" after the filing company.
    #    _OBJECT_FORM_RE enforces the Capitalized entity (scoped flags, not a
    #    global IGNORECASE), so no separate isupper() guard is needed.
    for m in _OBJECT_FORM_RE.finditer(title):
        if m.start() <= co_pos:
            continue  # entity-noun must follow the filing company
        entity_low = m.group(1).lower()
        if entity_low in filing_tokens or entity_low in _GENERIC_ACQ_PRECEDERS:
            continue
        return True
    return False


def matches_mna_in_any(texts: Iterable[Optional[str]]) -> Optional[tuple[str, int]]:
    """Scan multiple text blobs; return (keyword, index_of_first_hit) or None.

    `index_of_first_hit` lets the caller report which source matched (Claude
    analysis vs Perplexity summary vs Polygon title #3, etc.) for telemetry.
    """
    for i, t in enumerate(texts):
        kw = matches_mna_keywords(t)
        if kw:
            return kw, i
    return None


async def should_log_mna_filter_fired(ticker: str, detector_tag: str) -> bool:
    """Return True if `mna_filter_fired` audit should fire for (ticker,
    detector_tag) today. False if an audit row for this combination already
    exists in mi_audit_log for the current trading day (ET).

    Per #89 ship 2026-05-23: without this dedup, M&A filter audit events
    inflate 5-20x per converging ticker because detectors call is_likely_ma
    every scan tick (every 5 min over 3-hour scan window). 2026-05-22 L2
    anomaly fired with mna_filter_fired at 210 events vs 10 median (21x
    normal) — investigation showed 4 tickers (INFQ/RGTI/QBTS/EL) accounted
    for 201 of 210 fires. Same shape as the catalyst-downgrade dedup (1h)
    and the sugar_baby_convergence_alert dedup (#85, also trading-day).

    Summary contract: every mna_filter_fired call site MUST write a summary
    matching `{ticker} via%({detector_tag})%` so this LIKE-based dedup
    works. Standardized 2026-05-23 across all 5 detector sites
    (9m_intraday, 9m_sugar_baby, ep, flag, flag deal_pin).

    Fail-open: any DB error returns True (caller proceeds to log). Better
    to over-log than silently drop a filter decision audit.
    """
    try:
        from agents.market_intelligence.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            prior = await conn.fetchrow("""
                SELECT 1 FROM mi_audit_log
                WHERE event_type = 'mna_filter_fired'
                  AND summary LIKE $1
                  AND (created_at AT TIME ZONE 'America/New_York')::date
                      = (NOW() AT TIME ZONE 'America/New_York')::date
                LIMIT 1
            """, f"{ticker} via%({detector_tag})%")
        return prior is None
    except Exception as e:
        logger.debug(f"mna_filter audit dedup check failed (non-critical): {e}")
        return True  # fail-open: log if dedup check fails


async def should_log_mna_acquirer_skipped(ticker: str) -> bool:
    """Trading-day dedup for `mna_acquirer_title_skipped` (#284) — sibling of
    `should_log_mna_filter_fired`. polygon_news_has_mna_headline runs per scan
    tick, so without this a persistent acquirer-side headline re-logs 5-20x/day
    (the same inflation #89 fixed for mna_filter_fired). The skip summary starts
    with `{ticker} ` so a LIKE-prefix match dedups per ticker per ET day.
    Fail-open: any DB error returns True (better to over-log than drop)."""
    try:
        from agents.market_intelligence.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            prior = await conn.fetchrow("""
                SELECT 1 FROM mi_audit_log
                WHERE event_type = 'mna_acquirer_title_skipped'
                  AND summary LIKE $1
                  AND (created_at AT TIME ZONE 'America/New_York')::date
                      = (NOW() AT TIME ZONE 'America/New_York')::date
                LIMIT 1
            """, f"{ticker} %")
        return prior is None
    except Exception as e:
        logger.debug(f"mna_acquirer_skip audit dedup check failed (non-critical): {e}")
        return True  # fail-open


_POSSESSIVE_RE = re.compile(r"\b([A-Z][a-zA-Z]+)['’]s\b")
# Abbreviation-safe split: requires 2+ lowercase/digit chars before the
# terminator and a capital letter following, so "U.S. acquisition" / "a.m."
# / "Dr. Smith" don't split mid-abbreviation. Mirrors briefing.py's pattern.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[a-z0-9][a-z0-9][.!?])\s+(?=[A-Z])")


def reasoning_other_entity_owns_deal(
    reasoning: str,
    mna_keyword: str,
    filing_ticker: str,
    insight_tickers: Iterable[str],
) -> bool:
    """Sister-ticker possessive proximity check (#119 Part B, 2026-05-27).

    Return True when the M&A keyword appears in a sentence preceded by a
    `[Sister]'s ` possessive — where `Sister` (case-insensitive prose
    form) matches a different ticker symbol in the article's
    `insight_tickers` list.

    Narrow by design: catches the QBTS/RGTI 5/11 class where Polygon's
    sentiment_reasoning attributes the M&A activity to a tagged sibling
    (`"...driven by IonQ's acquisition..."` for QBTS, IONQ in insights).
    Does NOT attempt to recognize possessive prose forms of arbitrary
    company names (we have no name→ticker map; "Hewlett-Packard's deal"
    for an HPQ-tagged article won't fire). For those, upstream
    layers (direction check, catalyst_quality classifier) remain
    responsible.

    Implementation notes:
    - Sentence-bounded look-back (split on `. ` etc.), not arbitrary
      char window — keeps semantics interpretable.
    - Sister-ticker set strips the `.WS` warrant suffix
      (`IONQ.WS` → also matches the bare `IONQ` prose form).
    - Only `[A-Z][a-zA-Z]+'s` shapes — single capitalized prose token.
      Multi-word company names (Estée Lauder) aren't handled, but those
      would only fire if the company's first word matched a sister
      ticker, which is the bug class we ALREADY catch.
    """
    if not reasoning or not mna_keyword:
        return False
    filing_upper = filing_ticker.upper()
    sisters: set[str] = set()
    for t in insight_tickers:
        if not t:
            continue
        u = t.upper()
        if u == filing_upper:
            continue
        sisters.add(u)
        if "." in u:
            sisters.add(u.split(".", 1)[0])
    if not sisters:
        return False

    kw_low = mna_keyword.lower()
    for sentence in _SENTENCE_SPLIT_RE.split(reasoning):
        slow = sentence.lower()
        idx = slow.find(kw_low)
        if idx < 0:
            continue
        before = sentence[:idx]
        for m in _POSSESSIVE_RE.finditer(before):
            if m.group(1).upper() in sisters:
                return True
    return False


async def polygon_news_has_mna_headline(
    ticker: str,
    *,
    lookback_days: int = 14,
    on_or_before: Optional[date] = None,
) -> Optional[dict]:
    """Fetch recent Polygon news and scan for M&A keywords with the
    multi-ticker-tag-bleed discriminator (#88 fix, 2026-05-23).

    Two-path acceptance:

      Path A (title match) — M&A keyword in article TITLE. High specificity:
      title is the article's primary topic; if M&A keyword appears there
      it's almost certainly about *one* of the tagged tickers' M&A activity.
      We accept and let the broader filter graph + downstream
      direction-blindness fixes (#90) handle acquirer-side leaks.

      Path B (description-only match) — M&A keyword in description but NOT
      in title. The article may be tagged with multiple tickers; require:
        (i)  filtering ticker present in article's `insights` array
             (Polygon's per-ticker AI tagging — proxy for "article is
             relevant to this ticker, not just multi-tagged"), AND
        (ii) that ticker's `sentiment_reasoning` text itself contains an
             M&A keyword (proxy for "Polygon's AI thinks this ticker's
             move is M&A-related").

    If `insights` field is missing entirely (Polygon hasn't AI-graded the
    article — rare for recent ≤21d window where Polygon Insights has
    near-100% coverage), Path B SKIPS the article entirely (conservative;
    avoids resurrecting the QBTS-class bug for un-graded articles). Emits
    `polygon_news_insights_missing` audit event for future false-negative
    quantification.

    Loop semantics: when Path B rejects an article (description-only match
    but ticker not in insights or reasoning lacks M&A kw), continue to next
    article. Don't terminate on first rejection.

    Returns the first qualifying headline dict or None.

    Pre-ship backward verification (#88, 2026-05-23): 9 of 9 classified
    historical cases (2 TP + 7 FP from 90d audit) behave as expected
    under this logic. Replay script: scripts/_replay_88_mna_filter_fix.py
    """
    from agents.market_intelligence.collector import get_polygon_news, get_ticker_details

    items = await get_polygon_news(
        ticker, lookback_days=lookback_days, on_or_before=on_or_before, limit=20
    )

    # #284: resolve the filing ticker's company name only when a TITLE M&A
    # keyword hits (rare), memoized cross-call in _COMPANY_NAME_MEMO so a
    # persistent acquirer-side headline doesn't re-fetch the immutable name on
    # every scan tick.
    async def _filing_company_name() -> Optional[str]:
        if ticker not in _COMPANY_NAME_MEMO:
            details = await get_ticker_details(ticker)
            _COMPANY_NAME_MEMO[ticker] = (details or {}).get("name") or None
        return _COMPANY_NAME_MEMO[ticker]

    for item in items:
        title = item.get("title", "")
        description = item.get("description", "")

        # Shareholder-investigation notices reference prior deals, not new
        # fade-risk events.
        if is_shareholder_litigation_notice(title):
            continue

        title_kw = matches_mna_keywords(title)
        if title_kw:
            if _ticker_is_acquirer(item, ticker):
                continue
            # #284: acquirer-direction on the TITLE itself. `_ticker_is_acquirer`
            # only inspects per-ticker REASONING, so acquirer-side titles with
            # absent/ambiguous reasoning leaked (ONDS "...Omnisys Buyout",
            # MYRG "...to Acquire Valley"). Anchoring needs the company name.
            if title_implies_acquirer(title, await _filing_company_name()):
                if await should_log_mna_acquirer_skipped(ticker):
                    try:
                        from agents.market_intelligence.db import log_audit_event
                        from agents.market_intelligence.audit_events import (
                            MNA_ACQUIRER_TITLE_SKIPPED,
                        )
                        await log_audit_event(
                            MNA_ACQUIRER_TITLE_SKIPPED,
                            f"{ticker} title '{title_kw}' read ACQUIRER-side, not fired: "
                            f"'{title[:120]}'",
                        )
                    except Exception:
                        pass
                continue
            return {
                "ticker": ticker,
                "matched_keyword": title_kw,
                "match_path": "title",
                "title": title[:200],
                "published_utc": item.get("published_utc", ""),
                "publisher": item.get("publisher", ""),
            }

        desc_kw = matches_mna_keywords(description)
        if not desc_kw:
            continue  # neither title nor description matched — try next article

        # Path B: description match — verify ticker is article subject
        insights = item.get("insights") or []
        if not insights:
            # Polygon hasn't AI-graded this article. Skip Path B (conservative
            # missing-insights handling per advisor 2026-05-23). Emit audit so
            # we can quantify the false-negative risk over time. Use lazy import
            # to avoid circularity (ma_filter is imported by detectors that
            # also import db).
            try:
                from agents.market_intelligence.db import log_audit_event
                await log_audit_event(
                    "polygon_news_insights_missing",
                    f"{ticker} skipped Path B — no insights field on '{title[:120]}'",
                )
            except Exception:
                pass
            continue

        # Ticker must be in article's insights list (filtering ticker is a
        # subject of Polygon's AI tagging, not just a multi-tag bleed).
        ticker_insight = next(
            (i for i in insights if i.get("ticker") == ticker),
            None,
        )
        if ticker_insight is None:
            continue  # ticker tagged on article but not insighted — QBTS class

        # Ticker's per-ticker sentiment_reasoning must contain an M&A keyword
        # (Polygon's AI thinks THIS ticker's move is M&A-related).
        reasoning = ticker_insight.get("sentiment_reasoning") or ""
        reasoning_kw = matches_mna_keywords(reasoning)
        if not reasoning_kw:
            continue  # ticker insighted but not for M&A reason — MNST/ONDS/INFQ class

        # Part B proximity check (#119): if the M&A keyword is sentence-
        # preceded by a sister-ticker possessive (e.g. "IonQ's acquisition"
        # in QBTS reasoning), the M&A activity is attributed to another
        # tagged entity, not this ticker. Reject.
        insight_ticker_list = [i.get("ticker") for i in insights if i.get("ticker")]
        if reasoning_other_entity_owns_deal(
            reasoning, reasoning_kw, ticker, insight_ticker_list,
        ):
            continue

        if _ticker_is_acquirer(item, ticker, reasoning=reasoning):
            continue

        # Guard B (#416 R6): exploration/agitation reasoning ("proxy campaign seeking strategic
        # alternatives" — FRMI) is a pre-deal bullish catalyst, not a binding price-pin. Veto unless
        # a binding-deal marker escapes it. Next article still gets a chance (loop continues).
        if reasoning_is_exploration_only(reasoning):
            continue

        return {
            "ticker": ticker,
            "matched_keyword": desc_kw,
            "match_path": "description+insights",
            "title": title[:200],
            "published_utc": item.get("published_utc", ""),
            "publisher": item.get("publisher", ""),
            "insight_reasoning": reasoning[:200],
            "insight_reasoning_kw": reasoning_kw,
        }
    return None


async def is_likely_ma(
    ticker: str,
    *,
    catalyst_quality: Optional[str] = None,
    catalyst_texts: Optional[list[Optional[str]]] = None,
    check_polygon: bool = True,
    polygon_lookback_days: int = 14,
    on_or_before: Optional[date] = None,
) -> tuple[bool, Optional[dict]]:
    """Single-call M&A check used by all detectors.

    Sources, in order of cost (cheap → expensive):
      1. `catalyst_quality == 'mna'` (Claude classifier verdict; EP only)
      2. Keyword scan over `catalyst_texts` (Claude analysis, news_summary, …)
      3. Polygon news headlines (`check_polygon=True`)

    Returns (is_mna, telemetry_dict). The telemetry dict identifies which
    source fired so audit events can distinguish "Claude flagged it" from
    "we caught it via Polygon despite Perplexity hedging".
    """
    if catalyst_quality == "mna":
        # Guard C (#416 R6): the classifier called it M&A, but if the catalyst text frames THIS
        # ticker as the acquirer / a completed deal (ONDS 'Mistral acquisition closing'), that's a
        # bullish growth catalyst, not a target price-pin — veto this path, fall through to the
        # independent keyword/polygon paths (a real target-side deal still fires there).
        if not text_implies_acquirer_or_completed(catalyst_texts or []):
            return True, {
                "source": "claude_classifier",
                "ticker": ticker,
                "catalyst_quality": catalyst_quality,
            }

    # ── #516 GUARD D — a keyword match may NOT overrule a CONTRARY classification ──────────
    # OPERATOR-SIGNED 2026-08-08 after ruling 8 suppressions: 7 were false positives.
    #
    # All four of the keyword-path misfires he ruled — LII, SCZM, SOUN, UMAC — had ALREADY been
    # classified by our own grader as something OTHER than M&A (`routine`), and were suppressed
    # anyway because a word like "merger" or "takeover" appeared somewhere in the text. SOUN is
    # the clearest: its own stored summary says the move was "driven primarily by a blowout Q2
    # earnings print", and the filter killed it on the word "merger".
    #
    # So: when we have ALREADY FORMED A VIEW and that view is not M&A, a bare keyword match is
    # not allowed to override it. This is strictly narrower than "require the classifier to
    # concur", and that distinction is load-bearing:
    #
    #   ⚠ CLRO — the ONE correct suppression in the ruled set — has NO classification at all
    #     (killed at the 9m_intraday detector before grading ran). Requiring concurrence would
    #     have RELEASED it. This guard cannot touch it: no verdict → no veto → unchanged.
    #
    # Measured over 73 fires in 60 days: 28 where the classifier agrees stay suppressed, 27 with
    # no classification are unaffected, 18 are released. Of the released, the 4 he ruled are all
    # confirmed false positives.
    #
    # ⚠ It deliberately does NOT gate the polygon_news path below. That path fires on headlines
    # for tickers that were never graded (WEN ×5, LCID ×2, FRMI all have no classification), so
    # gating it here would do nothing — and it is a SEPARATE problem the operator has parked.
    _classifier_disagrees = bool(catalyst_quality) and catalyst_quality != "mna"

    if catalyst_texts and not _classifier_disagrees:
        hit = matches_mna_in_any(catalyst_texts)
        if hit:
            kw, idx = hit
            # Guard A (#416 R6): a negated/speculative keyword with no binding escape is not a real
            # deal (MMED 'not a takeover'; IMAX 'takeout speculation') — veto, fall through to polygon.
            if not keyword_context_is_nonbinding(catalyst_texts[idx], kw):
                return True, {
                    "source": f"keyword_in_text_{idx}",
                    "ticker": ticker,
                    "matched_keyword": kw,
                }

    # Telemetry for the guard above: record ONLY when it actually changed the outcome — i.e. a
    # keyword WOULD have matched and the contrary classification vetoed it. Silent otherwise,
    # so the row count is a direct measure of the rule's effect and not background noise.
    if _classifier_disagrees and catalyst_texts:
        _would_have = matches_mna_in_any(catalyst_texts)
        if _would_have and not keyword_context_is_nonbinding(
                catalyst_texts[_would_have[1]], _would_have[0]):
            try:
                from agents.market_intelligence.db import log_audit_event
                await log_audit_event(
                    "mna_keyword_vetoed_by_classifier",
                    f"{ticker}: kept — classifier said '{catalyst_quality}', "
                    f"keyword '{_would_have[0]}' did not override it (#516)",
                    json.dumps({"ticker": ticker, "catalyst_quality": catalyst_quality,
                                "matched_keyword": _would_have[0]}),
                )
            except Exception as e:  # loud-ok: telemetry must never change the filter verdict
                logger.warning(f"{ticker}: #516 veto telemetry failed: {e}")

    if check_polygon:
        polygon_hit = await polygon_news_has_mna_headline(
            ticker,
            lookback_days=polygon_lookback_days,
            on_or_before=on_or_before,
        )
        if polygon_hit:
            return True, {
                "source": "polygon_news",
                **polygon_hit,
            }

    return False, None
