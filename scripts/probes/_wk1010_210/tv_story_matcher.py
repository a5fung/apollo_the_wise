"""#210 2026-10-10 (review fix) — REFERENCE IMPLEMENTATION of the TradingView story matcher and
the comparison frame the build card ports into agents/market_intelligence/tv_news_shadow.py.

Pure stdlib, no DB, no network. Every rule here is stated once, in code, and PROVEN against
fixture_cases.json by run_fixture_proof.py (its pass/fail table is pasted into
docs/analysis/210_tv_miss_read_2026-10-10.md). The Sonnet card copies these functions and
constants VERBATIM (names included) and copies the fixture to tests/fixtures/ unchanged; it
makes no matching decision of its own — anything it wants to change goes back through the
fixture first.

WHY ANCHOR-FIRST, NOT JACCARD. The 2026-10-10 review showed no Jaccard threshold satisfies
the fixture: "Q4 Earnings Call Highlights" vs our transcript MUST match and scores 0.33-0.43
with no shared anchor, while Rosenblatt-$100 vs Stifel-$85 must NOT match and scores 0.40.
So a story match is decided by WHAT is shared, not HOW MUCH:
  title   — identical after normalisation (today's rule, kept first)
  story   — the same catalyst CLASS on both sides plus a shared ANCHOR; for analyst notes
            the anchor must be the FIRM (targets collide: Needham and Stifel both said $85)
  event   — an earnings-class item on a day we hold an earnings RESULTS item (one company
            reports once per day; a PREVIEW on our side does not count — correction 6)
  move    — a commentary-only piece ("why is X rising") on a day we hold any catalyst item
  class   — same class present among our same-day items, but no anchor proves the same
            story (a second analyst, a second contract, results vs our preview)
  none    — nothing above

TWO STORED LISTS, ONE RULE (correction 2 + the 2026-09-08 NULL rule together):
  tv_items_unmatched_seen — the `none` AND `class` items among the same-day items the window
            DID show us in the before-grade and re-poll buckets, each tagged `match` and
            `bucket`. Written whenever a diff is possible (corpus + captured_at), whatever
            the window's reach — a miss we saw is a miss even if the window rolled.
  tv_items_we_missed      — the DoD column. Equal to tv_items_unmatched_seen when the window
            reaches the START of the same-day period (oldest item <= 16:00 ET on the prior
            trading day); otherwise NULL = "cannot tell". An empty list here is an honest
            zero; an empty list may never appear on a rolled window.
The DoD readout reports "none" (strict) and "none + class" (loose) separately, each on the
before-grade bucket, with the re-poll bucket reported on its own (correction 8).

PROVEN BY run_fixture_proof.py against fixture_cases.json; its table is in the doc §7.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, time as dt_time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

# ── frame constants ────────────────────────────────────────────────────────────────
_TV_SAME_DAY_PRIOR_CLOSE_HOUR = 16          # unchanged from tv_news_shadow.py
_TV_ACTIONABLE_CUTOFF_ET = dt_time(10, 0)   # the scan's last tick + the 10:00 ET unfilled-cancel

# ── normalisation (identical to tv_news_shadow.normalize_title) ────────────────────
_TITLE_NORMALIZE_RE = re.compile(r"[^a-z0-9\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    t = title.lower()
    t = _TITLE_NORMALIZE_RE.sub(" ", t)
    return _WHITESPACE_RE.sub(" ", t).strip()


# ── vocabularies (closed lists; the card may EXTEND, never remove) ─────────────────
STOPWORDS = frozenset("""
the a an of to in on for and is at by as with its it from this that are be or vs after before
into over up down out here there what why how who when which more than their his her our your
has have had will can does do did not no but also about amid says said say stock stocks share
shares inc corp ltd plc co nyse nasdaq update updated correction summary today tonight
monday tuesday wednesday thursday friday saturday sunday week month year years ago per via
""".split())

# Words that name a CLASS or a rating/target vocabulary — never an anchor.
CLASS_WORDS = frozenset("""
q1 q2 q3 q4 1q 2q 3q 4q quarter quarterly fiscal earnings eps revenue revenues sales results
result guidance outlook profit profits beat beats miss misses estimate estimates transcript
gaap non-gaap nongaap call highlights
price target targets pt maintains maintain maintained reiterates reiterate reiterated upgrades
upgrade upgraded downgrades downgrade downgraded initiates initiate initiated rating ratings
overweight underweight outperform underperform buy sell hold neutral raised raises raise lowers
lower lowered cut cuts keeps keep rates rated boosts boost hikes hike lifts lift trims trim
sees see starts start resumes resume reinstates reinstate assumes assume
appoints appoint appointed appointment names name named hires hire hired resigns resign
resigned resignation steps step stepped retires retire retiring retirement departure succeeds
succeed succeeded cfo ceo coo cto chief officer president chairman director effective immediately
acquires acquire acquired acquiring acquisition merger merge buyout takeover definitive
partnership partners partner collaborates collaborate collaboration agreement contract awarded
award selected signs sign teams team
offering priced private placement convertible notes due at-the-market warrants warrant dilution
dilutive shelf direct
fda approval approves approved clearance 510(k) phase trial topline pdufa breakthrough
lawsuit class action investigation settles settle settled settlement probe subpoena
launch launches launched unveils unveil unveiled introduces introduce introduced debuts debut
scheduled set report reports reported reporting ahead preview expect expected watch deck
volatility primer
market talk trades trade trading higher jumps jump jumped surges surge surged soars soar
soared rally rallies rallied pops pop climbs climb rising rises rise falls fall slips slip
drops drop plunges plunge best worst day 52-week high low premarket pre-market overnight
midday skyrocket skyrockets sympathy gaps gap gapped gapping movers mover moving focus
happening need know explain
""".split())

# Generic headline words that carry no story identity — never an anchor.
GENERIC_WORDS = frozenset("""
strong strongly record records growth demand business businesses company companies group
global market markets investors investor analysts analyst wall street report reports new
news big major key top first latest update higher lower after ahead following amid upbeat
surging signals faster future shape taking stake stakes deal deals client clients spending
costs cost shares stock stocks inc corp plc ltd
""".split())

# Catalyst classes, in PRIMARY-class precedence order (first hit wins for `class` storage).
CATALYST_CLASS_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("earnings", re.compile(
        r"\bq[1-4]\b|\b[1-4]q\b|\bquarter\b|\bfy ?\d{2,4}\b|\bfiscal\b|\bearnings\b|\beps\b|"
        r"\brevenues?\b|\bsales\b|\bresults\b|\bguidance\b|\boutlook\b|\bprofits?\b|\bbeats?\b|"
        r"\bmiss(es)?\b|\bestimates?\b|\btranscript\b|\bnon-gaap\b|\bgaap\b", re.I)),
    ("analyst", re.compile(
        r"\bprice targets?\b|\bpt\b|\bmaintains?\b|\bmaintained\b|\breiterates?\b|\breiterated\b|"
        r"\bupgrades?\b|\bupgraded\b|\bdowngrades?\b|\bdowngraded\b|\binitiates?\b|\binitiated\b|"
        r"\brating\b|\boverweight\b|\bunderweight\b|\boutperform\b|\bunderperform\b", re.I)),
    ("exec_change", re.compile(
        r"\bappoint(s|ed|ment)?\b|\bnames?\b.{0,40}\b(cfo|ceo|coo|cto|chief|president|chairman|"
        r"director)\b|\bhires?\b|\bhired\b|\bresign(s|ed|ation)?\b|\bsteps? down\b|\bstepped down\b|"
        r"\bretir(es|ing|ement)\b|\bdeparture\b|\bsucceed(s|ed)?\b|\bnew (cfo|ceo|coo|cto)\b|"
        r"\bas (cfo|ceo|coo|cto)\b|\bchief [a-z]+ officer\b|\beffective immediately\b", re.I)),
    ("mna", re.compile(
        r"\bacquir(es?|ed|ing)\b|\bacquisition\b|\bmerger\b|\bmerge\b|\bbuyout\b|\btakeover\b|"
        r"\bto buy\b|\bdefinitive agreement\b|\bbid for\b", re.I)),
    ("deal", re.compile(
        r"\bpartnership\b|\bpartners? with\b|\bcollaborat(es?|ion)\b|\bagreement\b|\bcontract\b|"
        r"\bawarded?\b|\bselected by\b|\bsigns?\b|\bteams? up\b", re.I)),
    ("financing", re.compile(
        r"\boffering\b|\bpriced\b|\bprivate placement\b|\bconvertible\b|\bnotes due\b|"
        r"\bat-the-market\b|\bwarrants?\b|\bdilut(ion|ive)\b|\bshelf\b", re.I)),
    ("regulatory", re.compile(
        r"\bfda\b|\bapprov(al|es|ed)\b|\bclearance\b|\b510\(k\)|\bphase [1-3]\b|\btrial\b|"
        r"\btopline\b|\bpdufa\b|\bbreakthrough\b", re.I)),
    ("legal", re.compile(
        r"\blawsuit\b|\bclass action\b|\binvestigation\b|\bsettle(s|d|ment)?\b|\bprobe\b|"
        r"\bsubpoena\b", re.I)),
    ("product", re.compile(
        r"\blaunch(es|ed)?\b|\bunveils?\b|\bunveiled\b|\bintroduces?\b|\bintroduced\b|\bdebuts?\b",
        re.I)),
)
CATALYST_CLASSES = frozenset(c for c, _ in CATALYST_CLASS_PATTERNS)

# STRONG commentary markers = a FORMAT (a roundup, a "why" explainer, a Market Talk blurb).
# They win over any catalyst keyword in the same title ("CEO Says Focus on Big Deals — Market
# Talk" is commentary, not a deal). WEAK markers (jumps, surges, premarket) make a title
# commentary only when it carries no catalyst class ("jumps premarket following strong Q4
# beat" stays earnings).
COMMENTARY_STRONG_RE = re.compile(
    r"market talk|here is why|here's why|what's going on|what you need to know|need to know|"
    r"stock market today|stocks to watch|\bmovers?\b|moving (premarket|pre-market|higher|lower|in)|"
    r"and more stocks|stocks that explain|what's happening|\bin focus\b|\bbig stocks\b", re.I)
COMMENTARY_WEAK_RE = re.compile(
    r"\bwhy\b|trades? up|trading (higher|lower)|\bjumps?\b|\bjumped\b|\bsurges?\b|\bsurged\b|"
    r"\bsoars?\b|\bsoared\b|\brall(y|ies|ied)\b|\bpops?\b|\bclimbs?\b|\brising\b|\brises?\b|"
    r"\bfalls?\b|\bslips?\b|\bdrops?\b|\bplunges?\b|\bbest day\b|\bworst day\b|52-week|"
    r"(month|year) high|(month|year) low|\bpremarket\b|\bpre-market\b|\bovernight\b|\bmidday\b|"
    r"\bskyrockets?\b|\bsympathy\b|\bgap(s|ped|ping)? (up|down)\b", re.I)
# An earnings PREVIEW is not a results item: it cannot anchor an `event` match and is not
# "a reason for the move" (correction 6: actual results vs our preview must stay visible).
PREVIEW_RE = re.compile(
    r"\bscheduled\b|\bset to report\b|\bahead of\b|\bpreview\b|\bwhat to expect\b|\bto watch\b|"
    r"\bto report\b|\bexpected to report\b|\bearnings week\b|\bearnings volatility\b|"
    r"\bwill report\b|\bon deck\b|\breports? (on|after|before|this|next)\b|\bshould know\b|"
    r"\bearnings (preview|watch)\b|\bprimer\b", re.I)

# Analyst-firm extraction: the capitalised run BEFORE an analyst verb at the start of the
# title, or AFTER "by/at/from" at its end. Company/class/stop words are stripped from the
# candidate; an empty remainder means "no firm here" (so "Penguin Solutions Price Target
# Raised ... by Stifel" yields Stifel from the tail, not the company from the head).
_ANALYST_VERBS = (r"maintains?|maintained|reiterates?|reiterated|upgrades?|upgraded|downgrades?|"
                  r"downgraded|initiates?|initiated|raises?|raised|lowers?|lowered|cuts?|keeps?|"
                  r"rates?|rated|boosts?|hikes?|lifts?|trims?|sees?|starts?|resumes?|reinstates?|"
                  r"assumes?")
_CAP = r"[A-Z][\w&.'’-]*"
_FIRM_HEAD_RE = re.compile(
    rf"^\s*(?P<firm>{_CAP}(?:\s+(?:(?:of|&|and|de)\s+)?{_CAP}){{0,3}})\s+(?i:{_ANALYST_VERBS})\b")
_FIRM_TAIL_RE = re.compile(
    rf"\b(?:by|at|from)\s+(?P<firm>{_CAP}(?:\s+(?:(?:of|&|and)\s+)?{_CAP}){{0,3}})\s*[.)]?\s*$")

# Numeric anchors: dollar amounts (with unit), percentages, fiscal years. Bare numbers and
# calendar years are deliberately NOT anchors (they are everywhere).
_USD_RE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k|m|b|t|million|billion|trillion|thousand)?\b", re.I)
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?%")
_FY_RE = re.compile(r"\bfy\s?(\d{2}|\d{4})\b|\bfiscal (\d{4})\b", re.I)
_UNIT = {"million": "m", "billion": "b", "trillion": "t", "thousand": "k"}


# ── classification ─────────────────────────────────────────────────────────────────

def catalyst_classes(title: str) -> set[str]:
    """Catalyst classes a title carries (possibly several). A STRONG commentary marker
    empties the set — the title is a format, not a catalyst."""
    if COMMENTARY_STRONG_RE.search(title):
        return set()
    return {c for c, rx in CATALYST_CLASS_PATTERNS if rx.search(title)}


def is_commentary(title: str) -> bool:
    if COMMENTARY_STRONG_RE.search(title):
        return True
    return bool(COMMENTARY_WEAK_RE.search(title)) and not catalyst_classes(title)


def is_preview(title: str) -> bool:
    return "earnings" in catalyst_classes(title) and bool(PREVIEW_RE.search(title))


def primary_class(title: str) -> str:
    """ONE label for storage on a `none`/`class` item: the first catalyst class in precedence
    order, else `commentary`, else `other`."""
    cats = catalyst_classes(title)
    for c, _ in CATALYST_CLASS_PATTERNS:
        if c in cats:
            return c
    return "commentary" if is_commentary(title) else "other"


def holds_a_catalyst(title: str) -> bool:
    """Our item is 'a reason for the move' when it carries a catalyst class and is not
    merely an earnings preview."""
    cats = catalyst_classes(title)
    if not cats:
        return False
    return not (cats == {"earnings"} and is_preview(title))


# ── anchors ────────────────────────────────────────────────────────────────────────

def company_tokens(company_name: Optional[str], ticker: str, our_titles: list[str]) -> set[str]:
    """Tokens that name the company — never anchors. From the stored company name when the
    grade-corpus row carries one (Part 3 stores profile['companyName']); otherwise the
    frequency fallback: a token present in >= 3 of our titles (>= 2 when we hold fewer than
    6). The fallback is what the metrics-only rows (ACN/PENG/ERO) get."""
    toks = {ticker.lower()}
    if company_name:
        toks |= {t for t in normalize_title(company_name).split() if t not in STOPWORDS}
        return toks
    n = len(our_titles)
    thr = 3 if n >= 6 else 2
    counts: dict[str, int] = {}
    for t in our_titles:
        for w in set(normalize_title(t).split()):
            if w.isalpha() and len(w) >= 3 and w not in STOPWORDS:
                counts[w] = counts.get(w, 0) + 1
    toks |= {w for w, c in counts.items() if c >= thr}
    return toks


def _num(s: str) -> str:
    try:
        return format(Decimal(s.replace(",", "")).normalize(), "f")
    except InvalidOperation:
        return s


def numeric_anchors(title: str) -> set[str]:
    out: set[str] = set()
    for m in _USD_RE.finditer(title):
        unit = (m.group(2) or "").lower()
        out.add(f"usd:{_num(m.group(1))}{_UNIT.get(unit, unit)}")
    for m in _PCT_RE.finditer(title):
        out.add(f"pct:{_num(m.group(1))}")
    for m in _FY_RE.finditer(title):
        y = m.group(1) or m.group(2)
        out.add(f"fy:{('20' + y) if len(y) == 2 else y}")
    return out


def alpha_anchors(title: str, company: set[str]) -> set[str]:
    return {w for w in normalize_title(title).split()
            if w.isalpha() and len(w) >= 4
            and w not in STOPWORDS and w not in CLASS_WORDS and w not in GENERIC_WORDS
            and w not in company}


def analyst_firm(title: str, company: set[str]) -> Optional[str]:
    for rx in (_FIRM_HEAD_RE, _FIRM_TAIL_RE):
        m = rx.search(title)
        if not m:
            continue
        toks = [w for w in normalize_title(m.group("firm")).split()
                if w not in STOPWORDS and w not in CLASS_WORDS and w not in GENERIC_WORDS
                and w not in company]
        if toks:
            return " ".join(toks)
    return None


# ── same-day frame ─────────────────────────────────────────────────────────────────

def is_same_day_item(item_et: datetime, alert_date: date, prior_trading_day: date) -> bool:
    d = item_et.date()
    if d == alert_date:
        return True
    return d == prior_trading_day and item_et.time() >= dt_time(_TV_SAME_DAY_PRIOR_CLOSE_HOUR, 0)


def period_start(alert_date: date, prior_trading_day: date) -> datetime:
    """The first instant of the alert's news day: 16:00:00 ET on the prior TRADING day
    (the same-day rule's own boundary, _TV_SAME_DAY_PRIOR_CLOSE_HOUR). The frame's
    window-reach test is `oldest item <= period_start`, never `oldest <= captured_at`:
    the latter leaves the stretch between 16:00 and the oldest item unseen and reads an
    empty list over it (ACN: oldest 09:31 vs capture 07:10 would have read "reaches")."""
    return datetime.combine(prior_trading_day, dt_time(_TV_SAME_DAY_PRIOR_CLOSE_HOUR, 0), tzinfo=_ET)


def prior_weekday(d: date) -> date:
    """Weekend-only step back — what `shared.dates.last_trading_day(d - 1 day)` does today.
    HOLIDAY-BLIND: for ERO 2026-09-08 (the Tuesday after Labor Day) it returns Monday
    09-07, so the period would start 16:00 on a day the market was shut. Kept only as
    the fallback when exchange_calendars is unavailable; production uses the function
    below."""
    p = d - timedelta(days=1)
    while p.weekday() >= 5:
        p -= timedelta(days=1)
    return p


def prior_trading_day_holiday_aware(d: date) -> tuple[date, str]:
    """(prior NYSE trading day strictly before d, which calendar decided it). Steps back
    one calendar day at a time until `trading_calendar.get_market_status(x).is_trading_day`
    (exchange_calendars XNYS: weekends + NYSE holidays; it logs one INFO line per call,
    which at one call per candidate is fine). Falls back to the weekend-only rule,
    saying so, when the calendar cannot be imported — the card ports the first branch."""
    try:
        from agents.market_intelligence.trading_calendar import get_market_status
    except Exception:
        return prior_weekday(d), "weekday_fallback"
    p = d - timedelta(days=1)
    for _ in range(10):  # never more than a long weekend + holiday away
        if get_market_status(p).is_trading_day:
            return p, "nyse_calendar"
        p -= timedelta(days=1)
    return prior_weekday(d), "weekday_fallback"


# ── the matcher ────────────────────────────────────────────────────────────────────

def match_tv_item(tv_title: str, our_items: list[dict], *, alert_date: date,
                  prior_trading_day: date, company: set[str]) -> tuple[str, Optional[str]]:
    """(verdict, the title of ours it matched or None). `our_items` = [{title, published}]
    where `published` is an ET-aware datetime or None (undated FMP items count as same-day:
    they came from the grade-time fetch)."""
    tv_norm = normalize_title(tv_title)
    for o in our_items:
        if normalize_title(o["title"]) == tv_norm:
            return "title", o["title"]

    tv_cats = catalyst_classes(tv_title)
    tv_alpha = alpha_anchors(tv_title, company)
    tv_num = numeric_anchors(tv_title)
    tv_usd = {a for a in tv_num if a.startswith("usd:")}
    tv_firm = analyst_firm(tv_title, company) if "analyst" in tv_cats else None

    # story — same catalyst class + a shared anchor; analyst notes need the FIRM; two items
    # that both carry dollar figures and share none are not the same story.
    best: tuple[int, str] | None = None
    for o in our_items:
        shared_cls = (tv_cats & catalyst_classes(o["title"])) - {"earnings"}
        if not shared_cls:
            continue
        o_alpha = alpha_anchors(o["title"], company)
        o_num = numeric_anchors(o["title"])
        shared_alpha, shared_num = tv_alpha & o_alpha, tv_num & o_num
        if "analyst" in shared_cls:
            ok = tv_firm is not None and tv_firm == analyst_firm(o["title"], company)
        else:
            ok = bool(shared_alpha or shared_num)
        o_usd = {a for a in o_num if a.startswith("usd:")}
        if ok and tv_usd and o_usd and not (tv_usd & o_usd):
            ok = False
        if ok:
            score = len(shared_alpha) + len(shared_num) + (1 if "analyst" in shared_cls else 0)
            if best is None or score > best[0]:
                best = (score, o["title"])
    if best:
        return "story", best[1]

    same_day = [o for o in our_items
                if o.get("published") is None
                or is_same_day_item(o["published"], alert_date, prior_trading_day)]

    # event — one company, one results event per day; a preview on our side does not count.
    if "earnings" in tv_cats:
        for o in same_day:
            if "earnings" in catalyst_classes(o["title"]) and not is_preview(o["title"]):
                return "event", o["title"]

    # move — commentary on a day we held a reason for the move.
    if not tv_cats and is_commentary(tv_title):
        for o in same_day:
            if holds_a_catalyst(o["title"]):
                return "move", o["title"]

    # class — same class held today, but nothing proves the same story.
    for o in same_day:
        if tv_cats & catalyst_classes(o["title"]):
            return "class", o["title"]

    return "none", None


# ── the row frame (what build_shadow_row computes from these pieces) ───────────────

def build_frame(*, alert_date: date, prior_trading_day: date, captured_at: Optional[datetime],
                our_items: Optional[list[dict]], tv_items: list[dict], company: set[str]) -> dict:
    """tv_items = [{title, provider, published(unix s)}] — the whole returned window.
    our_items = None when no corpus exists. Returns the new columns of the shadow row.
    Column semantics: module docstring, "TWO STORED LISTS, ONE RULE"."""
    ps = period_start(alert_date, prior_trading_day)
    cutoff = datetime.combine(alert_date, _TV_ACTIONABLE_CUTOFF_ET, tzinfo=_ET)
    out: dict[str, Any] = {
        "our_captured_at": captured_at,
        "tv_coverage_reaches_period_start": None, "tv_unseen_minutes_at_period_start": None,
        "tv_items_before_grade": None, "tv_items_in_repoll_window": None,
        "tv_items_after_cutoff": None, "tv_match_summary": None,
        "tv_items_unmatched_seen": None, "tv_items_we_missed": None,
    }
    if tv_items:
        oldest = datetime.fromtimestamp(min(it["published"] for it in tv_items), tz=_ET)
        out["tv_coverage_reaches_period_start"] = oldest <= ps
        out["tv_unseen_minutes_at_period_start"] = (
            0 if oldest <= ps else math.ceil((oldest - ps).total_seconds() / 60))
    else:
        out["tv_coverage_reaches_period_start"] = False

    def bucket(it: dict) -> Optional[str]:
        t = datetime.fromtimestamp(it["published"], tz=_ET)
        if not is_same_day_item(t, alert_date, prior_trading_day):
            return None
        if captured_at is not None and t <= captured_at:
            return "before_grade"
        if t <= cutoff:
            return "repoll_window" if captured_at is not None else None
        return "after_cutoff"

    if captured_at is not None:
        counts = {"before_grade": 0, "repoll_window": 0, "after_cutoff": 0}
        for it in tv_items:
            b = bucket(it)
            if b:
                counts[b] += 1
        out["tv_items_before_grade"] = counts["before_grade"]
        out["tv_items_in_repoll_window"] = counts["repoll_window"]
        out["tv_items_after_cutoff"] = counts["after_cutoff"]

    if our_items is None or captured_at is None:
        return out  # cannot bucket or cannot diff: every diff column stays NULL

    summary = {b: {} for b in ("before_grade", "repoll_window", "after_cutoff")}
    unmatched_seen: list[dict] = []
    verdicts: dict[str, tuple[str, str, Optional[str]]] = {}
    for it in tv_items:
        b = bucket(it)
        if not b:
            continue
        v, matched = match_tv_item(it["title"], our_items, alert_date=alert_date,
                                   prior_trading_day=prior_trading_day, company=company)
        verdicts[it["title"]] = (b, v, matched)
        summary[b][v] = summary[b].get(v, 0) + 1
        if v in ("none", "class") and b in ("before_grade", "repoll_window"):
            unmatched_seen.append({"title": it["title"], "provider": it["provider"],
                                   "published": it["published"], "bucket": b,
                                   "class": primary_class(it["title"]), "match": v})
    out["tv_match_summary"] = summary
    out["_verdicts"] = verdicts  # proof-only; not a column
    out["tv_items_unmatched_seen"] = unmatched_seen
    # The DoD column: a list ONLY when the window reaches the period start. A rolled window
    # keeps NULL here even when unmatched_seen is non-empty — the reader takes confirmed
    # misses on rolled windows from tv_items_unmatched_seen, reported separately.
    out["tv_items_we_missed"] = (unmatched_seen if out["tv_coverage_reaches_period_start"]
                                 else None)
    return out
