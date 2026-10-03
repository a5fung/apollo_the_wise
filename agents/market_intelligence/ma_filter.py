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
  6. The 'mna' GRADE — re-tied 2026-10-03 (his ruling 2, "Go with rec", supersedes the letter of
     this ruling): graded ONLY for a signed reverse-merger SHELL (ep_detector RULE 3, the judge's
     rule 6); a buyout TARGET, signed or proposed, is graded on its own merit and this filter alone
     decides it on price. Before: 'mna' for any signed price-fixing deal, which left a price-
     released target (PD, DSGN) with a 0-point grade that could not reach HIGH.
  7. A headline overrides the grader ONLY when the grader found no deal (role 'none') or did not
     answer. When the grader answered a deal that does not pin (buyer, proposed, speculation,
     all-stock...), a pinning headline cannot re-block — it is logged as a conflict and passes.
NOT RULED (kept as built, listed for him): grade 'mna' while the grader's own answered fields do
not pin → the fields decide (pass) + an `mna_grade_without_pin` row.

THE PRICE DECIDES (operator 2026-10-03, on the replay sign-off — "I'm more concerned about the keep
pile, in those cases can't we reuse our pinned price check? It's clearly pinned to a buyout
price"; he released DSGN 05-18 / THR 05-22 / PD 05-29 and kept HZO 08-10 / RNW 08-11 blocked):
  * The news answer NOMINATES (`deal_nominates`): this ticker is the TARGET of a deal, signed OR
    proposed, on terms that could fix its price. The PRICE decides (`pin_verdict`): blocked only
    when the stock's range over the decision window is at or under the window's pin ceiling —
    the EP path reads the first five regular-session minutes (09:30-09:34 ET, <= 1.0% of the
    open) at the first tick after 09:35; the evening / multi-day detectors read the scan date's
    own daily bar (<= 2.0% of the close). A nominated name whose price is FREE passes, with an
    `mna_filter_released` row naming both readings (`pin_free`).
  * Three reading states, by design: a caller that passes NO reader (9M) gets the 10-02 verdict
    (`deal_pins_price` — a signed target blocks, a proposal passes); a reader whose window is not
    readable yet (pre-market, the window still open, a failed fetch, too few bars) HOLDS the name
    — blocked for this tick with an `mna_pin_pending` row and NO `mna_filter_fired` row, so the
    next tick re-reads; a readable window decides.
  * A reverse-merger SHELL keeps blocking on the news alone (ruling 1 + his SUNE / CLRO rulings +
    the 10-03 approvals): a shell is re-rated, not pinned — SUNE ranged 124% and CLRO 100% on
    their days, so any price check would release both.
  Evidence + thresholds: docs/setups/magna53_ep.md change log 2026-10-03; backtest
  scripts/probes/_692/pin_backtest.py ($0, the exported bars).

THE PRICE-ONLY ARM (operator 2026-10-03 ruling 3, "Go with rec"): on an EP gap day, a gap of
  PRICE_ONLY_GAP_MIN_PCT (20%) or more whose open window trades within PRICE_ONLY_PIN_MAX_PCT
  (0.5%) blocks REGARDLESS of the news — source `open_window_price_pin`. Why: seven real buyouts
  (TMHC, APGE, SAFT, FBRX 07-27, VREX, ARX, WEAV: +22..48% gaps, 0.1-0.9% day ranges) were graded
  'none' from a 200-char excerpt and released; the price alone catches 7 of 7 with 0 of the 47
  proven-free gappers. Same decision-time hold as the news arm: a >= 20% gapper is HELD until its
  open window is readable (09:35) — the EP caller passes `gap_pct`; no other caller does.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Awaitable, Callable, Iterable, NamedTuple, Optional
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
    """The NEWS-ONLY rule (pure; his 2026-10-02 rulings 1-3). True → blocks WITHOUT a price
    reading: a signed target on pinning terms, or a signed reverse-merger shell. Since 2026-10-03
    a TARGET's news verdict is only the fallback for a caller that carries no price (`pin_verdict`
    with reading None); a shell still blocks on this alone. None (unanswered) → False."""
    if a is None or a.status != "signed":
        return False
    if a.role == "target":
        return a.consideration in _PINNING_CONSIDERATIONS
    if a.role == "shell":
        return _SHELL_ROLE_PINS
    return False


# ── THE PRICE DECIDES (operator 2026-10-03) ──────────────────────────────────────────────────
#: The EP path's reading — the OPEN WINDOW: the first `OPEN_WINDOW_MINUTES` regular-session
#: minute bars (09:30-09:34 ET), range = (max high − min low) / the earliest bar's open, in %.
#: Readable once the window has ELAPSED (>= 09:35 ET) with >= `OPEN_WINDOW_MIN_BARS` bars present
#: (the 09:34 bar may not be published at the 09:35 tick; on the labelled rows a 4-bar reading
#: never crosses the ceiling where the 5-bar one does not). Backtest (scripts/probes/_692/
#: pin_backtest.py, 2026-10-03): every operator-labelled pinned name reads <= 0.74% (RNW), every
#: labelled free one >= 2.65% (IMAX) — PD 5.36%, DSGN 6.60%; with his approved rows the corridor
#: narrows to 0.74% ↔ 1.24% (MGM), and 0 of 47 proven-free gappers (own-day range >= 3%, gap
#: >= 7%) read under 1.0%. The ORB bar alone (09:30 minute) was rejected: 6 of those 47 read
#: under 1.0% and its labelled corridor is 0.59% ↔ 1.39% (PD).
OPEN_WINDOW_MINUTES: int = 5
OPEN_WINDOW_MIN_BARS: int = 4
OPEN_WINDOW_PIN_MAX_PCT: float = 1.0
#: The evening / multi-day detectors' reading — the DAY WINDOW: the scan date's own daily bar,
#: range = (high − low) / close in % (flag_detector._evaluate_deal_pin's convention; the bar is
#: in mi_daily_closes from 17:00 ET, the flag scan runs 17:25). Labelled corridor: pinned
#: <= 1.84% (ROKU, his approved block) ↔ free >= 2.39% (THR, released on his word) — thin; said so.
DAY_WINDOW_PIN_MAX_PCT: float = 2.0
#: THE PRICE-ONLY ARM (his ruling 3, 2026-10-03) — EP path only: a gap of at least this many
#: percent whose open window (the same 09:30-09:34 reading) is at or under this ceiling blocks
#: regardless of the news. Backtest on the 105 EP rows with an open window: 13 hits = the seven
#: news-missed buyouts + six already blocked by news (RAMP, NUVL, CRNX, ATKR, HZO, ACVA); the
#: closest free >= 20% gappers read 0.57% (UTZ, itself a news block) and 0.99% (ATAI 07-16).
PRICE_ONLY_GAP_MIN_PCT: float = 20.0
PRICE_ONLY_PIN_MAX_PCT: float = 0.5


class PinReading(NamedTuple):
    """One price reading over a decision window. `readable=False` carries `why` (pre_market /
    window_open / bars:<n> / no_own_day_bar / fetch_error:<Exc> / reader_error:<Exc>)."""
    window: str                      # "open5m" | "day"
    range_pct: Optional[float]
    threshold_pct: float
    bars_n: int = 0
    readable: bool = False
    why: str = ""
    as_of: str = ""

    @property
    def pinned(self) -> bool:
        return bool(self.readable and self.range_pct is not None
                    and self.range_pct <= self.threshold_pct)

    def as_dict(self) -> dict:
        return {"window": self.window, "range_pct": self.range_pct,
                "threshold_pct": self.threshold_pct, "bars_n": self.bars_n,
                "readable": self.readable, "why": self.why, "as_of": self.as_of,
                "pinned": self.pinned}


def deal_nominates(a: Optional[DealAnswer]) -> bool:
    """The NEWS half of the 2026-10-03 rule (pure): this ticker is the TARGET of a deal, signed
    OR proposed, on terms that could fix its price (cash / cash+stock / unstated). The price then
    decides. Not a nomination: a buyer, a shell (news-only — see `deal_pins_price`), speculation,
    a denial, a closed deal, an all-stock merger (CSR), 'none'."""
    if a is None:
        return False
    return (a.role == "target" and a.status in ("signed", "proposed")
            and a.consideration in _PINNING_CONSIDERATIONS)


def pin_verdict(a: Optional[DealAnswer], reading: Optional[PinReading]) -> tuple[Optional[bool], str]:
    """THE decision (pure) for one answer and one price reading → (block, why), where block is
    True / False / None (None = HOLD: nominated, but the window cannot be read yet).
      shell + signed                      → (True,  'shell_signed')      news alone (ruling 1)
      not nominated                       → (False, 'not_nominated')
      nominated, no reading (no reader)   → (deal_pins_price, 'no_price_reading')  the 10-02 rule
      nominated, reading not readable     → (None,  'pin_pending')
      nominated, pinned                   → (True,  'pinned')
      nominated, free                     → (False, 'pin_free')
    """
    if a is not None and a.role == "shell":
        return (True, "shell_signed") if deal_pins_price(a) else (False, "not_nominated")
    if not deal_nominates(a):
        return False, "not_nominated"
    if reading is None:
        return deal_pins_price(a), "no_price_reading"
    if not reading.readable:
        return None, "pin_pending"
    return (True, "pinned") if reading.pinned else (False, "pin_free")


def price_only_pin_verdict(gap_pct: Optional[float],
                           reading: Optional[PinReading]) -> tuple[Optional[bool], str]:
    """THE PRICE-ONLY ARM (pure; his ruling 3) → (block, why), block ∈ True / False / None (HOLD).
      gap below the arm (or unknown)        → (False, 'gap_below_arm')
      no reading (a caller with no reader)  → (False, 'no_price_reading')
      window not readable                   → (None,  'pin_pending')
      open window <= PRICE_ONLY_PIN_MAX_PCT → (True,  'price_only_pinned')
      else                                  → (False, 'price_only_free')
    """
    if gap_pct is None or gap_pct < PRICE_ONLY_GAP_MIN_PCT:
        return False, "gap_below_arm"
    if reading is None:
        return False, "no_price_reading"
    if not reading.readable:
        return None, "pin_pending"
    if reading.range_pct is not None and reading.range_pct <= PRICE_ONLY_PIN_MAX_PCT:
        return True, "price_only_pinned"
    return False, "price_only_free"


def _headline_acts(a: Optional[DealAnswer]) -> bool:
    """A headline answer the filter must ACT on: a nomination (the price decides) or a news-only
    pin (a signed shell)."""
    return deal_nominates(a) or deal_pins_price(a)


def open_window_pin_from_bars(bars: Iterable[dict], day: date, *, as_of: str = "") -> PinReading:
    """Pure: the open-window reading from minute bars (dicts with an aware `ts` datetime and
    open/high/low). Keeps the bars whose ET minute falls in [09:30, 09:30 + OPEN_WINDOW_MINUTES)
    on `day`; fewer than OPEN_WINDOW_MIN_BARS of them → not readable (`bars:<n>`)."""
    start = datetime.combine(day, time(9, 30), tzinfo=_ET)
    end = start + timedelta(minutes=OPEN_WINDOW_MINUTES)
    inside = []
    for b in bars or []:
        ts = b.get("ts")
        if ts is None or getattr(ts, "tzinfo", None) is None:
            continue
        et = ts.astimezone(_ET)
        if start <= et < end:
            inside.append((et, b))
    n = len(inside)
    thr = OPEN_WINDOW_PIN_MAX_PCT
    if n < OPEN_WINDOW_MIN_BARS:
        return PinReading("open5m", None, thr, n, False, f"bars:{n}", as_of)
    inside.sort(key=lambda p: p[0])
    try:
        o = float(inside[0][1]["open"])
        hi = max(float(b["high"]) for _t, b in inside)
        lo = min(float(b["low"]) for _t, b in inside)
    except (KeyError, TypeError, ValueError):
        return PinReading("open5m", None, thr, n, False, "bad_bar", as_of)
    if o <= 0 or hi < lo:
        return PinReading("open5m", None, thr, n, False, "bad_bar", as_of)
    return PinReading("open5m", round((hi - lo) / o * 100.0, 4), thr, n, True, "", as_of)


def day_window_pin(rows: Iterable[dict], scan_date: date) -> PinReading:
    """Pure: the day-window reading from daily rows — mi_daily_closes shape (trade_date /
    high_price / low_price / close) or the anticipation bar shape (date / h / l / c). The scan
    date's own bar missing → not readable (`no_own_day_bar`)."""
    want = scan_date.isoformat()
    thr = DAY_WINDOW_PIN_MAX_PCT
    own = None
    for r in rows or []:
        d = r.get("trade_date", r.get("date"))
        if d is not None and str(d)[:10] == want:
            own = r
            break
    if own is None:
        return PinReading("day", None, thr, 0, False, "no_own_day_bar", want)
    try:
        h = float(own["high_price"] if "high_price" in own else own["h"])
        l = float(own["low_price"] if "low_price" in own else own["l"])
        c = float(own["close"] if "close" in own else own["c"])
    except (KeyError, TypeError, ValueError):
        return PinReading("day", None, thr, 1, False, "bad_bar", want)
    if c <= 0 or h < l:
        return PinReading("day", None, thr, 1, False, "bad_bar", want)
    return PinReading("day", round((h - l) / c * 100.0, 4), thr, 1, True, "", want)


# (ticker, ET day) -> a READABLE open-window reading; a fixed window reads the same at every
# later tick, so one successful read serves the day. Cleared with the headline memo.
_PIN_MEMO: dict[tuple[str, str], PinReading] = {}


async def read_open_window_pin(ticker: str, day: date, now_et: Optional[datetime] = None) -> PinReading:
    """The EP path's reader (and the low-cap lane's): the open window of `day`, read from the
    same Alpaca minute bars + feed (ALPACA_DATA_FEED) the ORB entry reads its 09:30 bar from.
    Before 09:35 ET it is not readable (pre_market / window_open) — the name is HELD and the next
    tick asks again. Never raises."""
    now = now_et or datetime.now(_ET)
    key = (ticker, day.isoformat())
    if key in _PIN_MEMO:
        return _PIN_MEMO[key]
    start = datetime.combine(day, time(9, 30), tzinfo=_ET)
    end = start + timedelta(minutes=OPEN_WINDOW_MINUTES)
    thr = OPEN_WINDOW_PIN_MAX_PCT
    stamp = now.isoformat(timespec="seconds")
    if now < start:
        return PinReading("open5m", None, thr, 0, False, "pre_market", stamp)
    if now < end:
        return PinReading("open5m", None, thr, 0, False, "window_open", stamp)
    try:
        from agents.market_intelligence.collector import get_alpaca_minute_bars_window
        bars = (await get_alpaca_minute_bars_window([ticker], start, end)).get(ticker) or []
    except Exception as e:  # loud-ok: an unreadable window HOLDS the name (audited), never passes it
        logger.warning(f"{ticker}: open-window pin fetch failed — {type(e).__name__}: {e}")
        return PinReading("open5m", None, thr, 0, False, f"fetch_error:{type(e).__name__}", stamp)
    reading = open_window_pin_from_bars(bars, day, as_of=stamp)
    if reading.readable:
        _PIN_MEMO[key] = reading
    return reading


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
    """Forget today's memo, attempts, call count, cap-hit flags and pin readings (day rollover; tests)."""
    _HEADLINE_MEMO.clear()
    _HEADLINE_ATTEMPTS.clear()
    _PIN_MEMO.clear()
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
    the newest candidate whose answer the filter must ACT on — a nomination (target, signed or
    proposed, pinning terms: the price decides) or a signed shell (news alone). Candidates past
    the cap, and asks still running at the deadline, are recorded UNANSWERED (why='article_cap'
    / 'deadline') — never dropped."""
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
        elif _headline_acts(answer):
            if hit is None:   # newest acting candidate (asked newest first)
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
    """The first Polygon article whose deal answer the filter must act on (a nomination or a
    signed shell), or None."""
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
    pin_reader: Optional[Callable[[], Awaitable[Optional[PinReading]]]] = None,
    gap_pct: Optional[float] = None,
) -> tuple[bool, Optional[dict]]:
    """Is THIS ticker's price fixed by a deal? Returns (block, telemetry).

    `gap_pct` (EP scan only) arms THE PRICE-ONLY ARM (his ruling 3, 2026-10-03): a gap >=
    PRICE_ONLY_GAP_MIN_PCT whose open window reads <= PRICE_ONLY_PIN_MAX_PCT blocks regardless of
    the news (source `open_window_price_pin`); unreadable → HOLD like the news arm. Runs after
    the news paths, only when they did not block.

    1. `deal_answer` (the EP grader's deal fields) NOMINATES (target, signed or proposed, on
       pinning terms) → the PRICE decides via `pin_reader` (2026-10-03): pinned → block, source
       `claude_deal_fields` + the reading under `pin`; free → pass + an `mna_filter_released` row
       (`pin_free`); window not readable yet → HOLD (block for this tick, `pending: True`, an
       `mna_pin_pending` row — callers write NO `mna_filter_fired` row for a hold). A signed
       shell blocks on the news alone. No `pin_reader` → the 10-02 verdict (`deal_pins_price`).
    2. Ruling 5: the grader graded 'mna' but its deal fields are missing / out of vocabulary
       (`deal_answer is None`) → block, as before #692, source `claude_classifier_unanswered`.
    3. The headline question (`check_polygon=True`, ≤3 newest keyword candidates), the same
       verdict on its acting answer. Ruling 7: a headline acts ONLY when the grader found no deal
       (role 'none') or did not answer (None — a failed grade, or a non-EP caller). When the
       grader answered a deal that does not act, an acting headline is logged as a conflict and
       PASSES. Ruling 4: candidates left UNANSWERED pass (+ an audit row) unless
       `mna_headline_unanswered_blocks` is ON.
    `catalyst_texts` decide NOTHING: with `catalyst_quality` they feed the `mna_filter_released`
    comparator (the names the pre-#692 rule would have blocked, plus every grader-answered deal
    that does not pin — the under-fire surface of the monthly review).
    `skip_in_orb` / `budget_pool` — set ONLY by the EP scan (see `ask_deal_question`).
    """
    reading_box: dict = {}

    async def _reading() -> Optional[PinReading]:
        """Read the price ONCE per call, only when an answer nominates."""
        if "r" not in reading_box:
            r: Optional[PinReading] = None
            if pin_reader is not None:
                try:
                    r = await pin_reader()
                except Exception as e:  # loud-ok: an unreadable price HOLDS, never releases
                    logger.warning(f"{ticker}: pin reader failed — {type(e).__name__}: {e}")
                    r = PinReading("?", None, 0.0, 0, False, f"reader_error:{type(e).__name__}")
            reading_box["r"] = r
        return reading_box["r"]

    async def _decide(answer: DealAnswer, meta: dict) -> Optional[tuple[bool, dict]]:
        """The verdict on an ACTING answer: (True, meta) to block / hold, None when the price
        releases it (recorded for the comparator)."""
        reading = await _reading() if deal_nominates(answer) else None
        verdict, why = pin_verdict(answer, reading)
        pin = reading.as_dict() if reading is not None else {}
        if verdict is None:
            await _audit_once(
                "mna_pin_pending", ticker,
                f"deal-nominated ({_answer_str(answer)} via {meta.get('source')}) — the price "
                f"cannot be read yet ({reading.why}); held this tick",
                {"answer": deal_fields(answer), "source": meta.get("source"), "pin": pin})
            return True, {**meta, "pending": True, "why": why, "pin": pin}
        if verdict:
            return True, {**meta, "why": why, **({"pin": pin} if pin else {})}
        reading_box["released"] = {"answer": deal_fields(answer), "why": why,
                                   "source": meta.get("source"), "pin": pin}
        return None

    if deal_answer is not None and _headline_acts(deal_answer):
        res = await _decide(deal_answer, {
            "source": "claude_deal_fields",
            "match_path": "claude_deal_fields",
            "ticker": ticker,
            **deal_fields(deal_answer),
        })
        if res is not None:
            return res
    if catalyst_quality == "mna":
        if deal_answer is None:
            # Ruling 5: the grade said 'mna' and the deal fields are blank — block as before.
            return True, {
                "source": "claude_classifier_unanswered",
                "match_path": "claude_classifier_unanswered",
                "ticker": ticker,
                "catalyst_quality": catalyst_quality,
            }
        # 'mna' graded while the grader's OWN answered fields are not a signed SHELL. Since his
        # 2026-10-03 ruling 2 the grade is reserved for a signed reverse-merger shell — a buyout
        # TARGET is graded on merit and the filter decides it on price — so a target graded 'mna'
        # is the prompt rule NOT holding. The fields decide the verdict; this row counts the
        # mismatch (EXPECT ~0/week; > 3/week = the prompt rule is not holding).
        if not (deal_answer.role == "shell" and deal_answer.status == "signed"):
            await _audit_once(
                "mna_grade_without_pin", ticker,
                f"graded 'mna' but its deal fields are not a signed shell — {_answer_str(deal_answer)}",
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
                    f"grader read {_answer_str(deal_answer)}, headline nominated "
                    f"({scan.hit.get('role')}/{scan.hit.get('status')}) — passed (ruling 7: "
                    "the grader's deal answer governs)",
                    {"grader": deal_fields(deal_answer), "headline": scan.hit, "blocked": False})
            else:
                hit_answer = DealAnswer(
                    str(scan.hit.get("role") or ""), str(scan.hit.get("status") or ""),
                    str(scan.hit.get("consideration") or ""),
                    str(scan.hit.get("counterparty") or ""), str(scan.hit.get("note") or ""))
                res = await _decide(hit_answer, scan.hit)
                if res is not None:
                    if deal_answer is not None:
                        await _audit_once(
                            "mna_deal_answers_conflict", ticker,
                            f"grader read {_answer_str(deal_answer)}, headline nominated "
                            f"({scan.hit.get('role')}/{scan.hit.get('status')}) — "
                            f"{'held' if res[1].get('pending') else 'blocked'}",
                            {"grader": deal_fields(deal_answer), "headline": scan.hit, "blocked": True})
                    return res
        # Ruling 4 — the unanswered candidates. A separate `if` (not `elif`) since 2026-10-03:
        # a nominating hit the PRICE released must not swallow the unanswered row for the other
        # candidates in the same scan.
        if scan.unanswered and not grader_found_deal:
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

    # ── THE PRICE-ONLY ARM (his ruling 3, 2026-10-03): the news did not block; a >= 20% gapper
    # whose open window is pinned blocks on the price alone. Reads the same window (memoized
    # within this call); an unreadable window HOLDS, as the news arm does.
    if gap_pct is not None and gap_pct >= PRICE_ONLY_GAP_MIN_PCT and pin_reader is not None:
        reading = await _reading()
        verdict, why = price_only_pin_verdict(gap_pct, reading)
        arm_pin = reading._replace(threshold_pct=PRICE_ONLY_PIN_MAX_PCT).as_dict() if reading else {}
        arm_meta = {"source": "open_window_price_pin", "match_path": "open_window_price_pin",
                    "ticker": ticker, "gap_pct": round(float(gap_pct), 2), "why": why, "pin": arm_pin}
        if verdict is None:
            await _audit_once(
                "mna_pin_pending", ticker,
                f"gap {gap_pct:.1f}% >= {PRICE_ONLY_GAP_MIN_PCT:.0f}% (price-only arm) — the "
                f"price cannot be read yet ({reading.why}); held this tick",
                {"answer": deal_fields(deal_answer), "source": "open_window_price_pin",
                 "gap_pct": round(float(gap_pct), 2), "pin": arm_pin})
            return True, {**arm_meta, "pending": True}
        if verdict:
            return True, arm_meta

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
    pin_release = reading_box.get("released")
    if pin_release:
        # 2026-10-03: a nominated name the PRICE released — the row names both readings.
        old_reasons.append("pin_free")
    if old_reasons:
        lead = ("old rule would have blocked (" + ", ".join(old_rule) + ")" if old_rule
                else "released for review (the grader answered a deal that does not pin)")
        if pin_release:
            pr = pin_release["pin"]
            lead = (f"deal-nominated ({pin_release['answer'].get('role')}/"
                    f"{pin_release['answer'].get('status')} via {pin_release['source']}) but the "
                    f"price is FREE — {pr.get('window')} range {pr.get('range_pct')}% > "
                    f"{pr.get('threshold_pct')}% ceiling; " + lead)
        await _audit_once(
            "mna_filter_released", ticker,
            f"{lead}; grader read {_answer_str(deal_answer)}"
            + (f"; {len(scan.released)} headline(s) answered no pin" if scan.released else "")
            + ("; a nominating headline was overruled (ruling 7)"
               if scan.hit and grader_found_deal else ""),
            {"old_reasons": old_reasons, "old_rule_would_block": bool(old_rule),
             "grader": deal_fields(deal_answer), "headlines": scan.released,
             "overruled_headline": scan.hit if grader_found_deal else None,
             "unanswered_n": len(scan.unanswered),
             **({"pin_release": pin_release} if pin_release else {})})
    return False, None
