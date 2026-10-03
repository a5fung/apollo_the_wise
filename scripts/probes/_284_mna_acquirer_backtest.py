"""#692 regression harness for the M&A filter — every operator-labelled block as a named case.

RESHAPED 2026-10-02 (#692). Was: the #284 title-direction regex backtest (`title_implies_acquirer`,
deleted with the regex layer). Now: (ticker, date, the inputs the OLD filter saw, the deal
answer(s) the NEW question is expected to return, the expected verdict) → runs the decision
deterministically at $0 through the real `ma_filter.is_likely_ma`, with Polygon and the model
replaced by the fixtures below.

GROUND TRUTH vs EXPECTATION — read before trusting a row:
  * `label` — the operator's own ruling where `ground_truth=True` (2026-07-04, 2026-07-12,
    2026-08-08, 2026-10-01 — docs/analysis/mna_filter_operator_labels_2026-10-01.md and the
    2026-08-08 entry in docs/setups/magna53_ep.md). Rows with `ground_truth=False` are
    AGENT-READ plumbing cases for his sign-off list, never findings (CHANGE_PROCESS #3/#4).
  * `grader` / `headline` — the answers the model is EXPECTED to give (the design's reading of
    the stored source text). They are NOT recorded model output: the paid replay
    (scripts/probes/_692/replay_target_question.py) produces the real answers, and any row
    whose real answer differs is the replay's finding, not this file's.
  So a green run proves the RULE and the plumbing on these inputs; whether the model answers
  as expected is the replay's question.

ARMS
  python scripts/probes/_284_mna_acquirer_backtest.py
      → the NEW logic over every case; exit 1 on any operator-labelled miss.
  python scripts/probes/_284_mna_acquirer_backtest.py --old-module <path/to/old/ma_filter.py>
      → ALSO runs the OLD `is_likely_ma` (e.g. `git show origin/main:agents/market_intelligence/
        ma_filter.py > /tmp/ma_filter_old.py`) on the same old-path inputs, so each case shows
        the old verdict next to the new one. That is the "fails on today's code, passes on the
        fix" check — the old module is loaded from a file, never kept in the repo.

ASCII-only output (cp1252 console safety). $0 — no network, no DB, no model.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from contextlib import ExitStack
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NamedTuple, Optional
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_ET = ZoneInfo("America/New_York")
# Any instant outside the 9:30-9:45 ORB window — the question is skipped inside it.
_OUTSIDE_ORB = datetime(2026, 10, 2, 8, 0, tzinfo=_ET)


class Ans(NamedTuple):
    role: str
    status: str
    consideration: str
    counterparty: str = ""


class Case(NamedTuple):
    ticker: str
    day: str
    label: str
    ground_truth: bool
    old_path: str                      # classifier | keyword | headline (what fired in prod)
    expected: str                      # BLOCK | PASS
    catalyst_quality: Optional[str] = None   # the OLD grade (None = never graded, e.g. 9m)
    catalyst_texts: tuple = ()               # the OLD text the keyword path scanned
    grader: Optional[Ans] = None             # the NEW grader deal fields (None = no grader)
    articles: tuple = ()                     # Polygon items the headline path sees
    headline: tuple = ()                     # ((title, Ans), ...) expected headline answers
    company: Optional[str] = None
    # 2026-10-03 — the RECORDED price reading at the detector's decision window (the exported
    # bars, scripts/probes/_692/pin/): ("open5m", range % of the 09:30 open over 09:30-09:34) on
    # EP days, ("day", own-day range % of close) for the evening detectors. None = this caller
    # carries no price (the 10-02 verdict applies); pin_pending=True = the window was not readable.
    pin: Optional[tuple] = None
    pin_pending: bool = False
    # his ruling 3 (2026-10-03): the EP scan's gap at decision time arms the price-only arm
    # (gap >= 20% AND open window <= 0.5% blocks regardless of the news). None = not the EP path.
    gap_pct: Optional[float] = None


def _item(title: str, *, description: str = "", ticker: str = "", reasoning: Optional[str] = None,
          published: str = "2026-09-01T12:00:00Z", others: tuple = ()) -> dict:
    insights = [{"ticker": t, "sentiment_reasoning": r} for t, r in others]
    if reasoning is not None:
        insights.insert(0, {"ticker": ticker, "sentiment_reasoning": reasoning})
    return {"title": title, "description": description, "insights": insights,
            "published_utc": published, "publisher": "fixture"}


_NONE = Ans("none", "none", "none")

# ── The 2026-10-01 sitting: ten wrongly blocked, ACVA correct ─────────────────────────────────
_IOVA_VKTX_TITLE = "4 Biotech Stocks to Watch as Potential Takeover Targets"
_RGTI_TITLE = ("Rigetti Signs Definitive Agreement for $100M with U.S. Government to Accelerate "
               "R&D for Superconducting Quantum Computing")
_CLRO_TITLE = ("Vivani Announces Entry into Merger Agreement Between Wholly Owned Subsidiary "
               "Cortigent, Inc. and Nasdaq-listed ClearOne, Inc.")
_SUNE_TITLE = "Clean Energy Stocks Are Trending — Here's Why"
_FRMI_TITLE = "Why Is Fermi (FRMI) Stock Moving Today?"
_ONDS_TITLE = "Ondas Bets Big On AI Battlefield Software With Omnisys Buyout"
_WEN_TITLE = "The Crowd Is Selling Wendy's Stock. Here's Why It's a Buy Instead."
_LCID_TITLE = ("Stock Market Today, July 16: Lucid Group Surges on CEO's Denial of Bankruptcy "
               "and Take-Private Rumors")
_CECO_THR_TITLE = ("CECO Environmental and Thermon Group Holdings Announce Election Deadline for "
                   "Thermon Stockholders to Elect Form of Merger Consideration")
_ROKU_TITLE = ("Deal Dispatch: Yum! Brands Sells Pizza Hut, Fox Corp. Buys Roku For $22 Billion, "
               "Salesforce Acquires Fin")
_QBTS_TITLE = ("Stock Market Today, May 11: IonQ Rises as SkyWater Vote Advances Semiconductor "
               "Manufacturing Deal")

CASES: tuple[Case, ...] = (
    Case("ACVA", "2026-09-11", "operator 2026-10-01: real buyout (Copart, all-cash ~$1.9B) - correctly blocked",
         True, "classifier", "BLOCK", "mna",
         ("[SEC 8-K filed 2026-09-10, items 1.01,7.01,9.01] ACVA gapped up because Copart announced an "
          "agreement to acquire ACV Auctions in an all-cash deal valued at approximately $1.9 billion.",),
         grader=Ans("target", "signed", "cash", "Copart"), pin=("open5m", 0.2869), gap_pct=44.81),
    # ── his 2026-10-03 sign-off on the replay: three releases, two keeps (the price decides) ──
    Case("PD", "2026-05-29", "operator 2026-10-03: 'is not a buyout, release' - signed take-private read, no buyer named; "
         "the open ranged 5.36% (13% on the day)",
         True, "keyword", "PASS", "mna",
         ("The news says a private equity buyer agreed to acquire PagerDuty and take it private at a premium.",),
         grader=Ans("target", "signed", "unknown"), pin=("open5m", 5.3591), gap_pct=25.40),
    Case("DSGN", "2026-05-18", "operator 2026-10-03: 'is not a buyout, release' - 'agreed to acquire' with no buyer "
         "named; the open ranged 6.60% (65% on the day)",
         True, "keyword", "PASS", "routine",
         ("DSGN gapped up on news that a larger biopharma company agreed to acquire Design Therapeutics at a "
          "substantial premium; a takeover.",),
         grader=Ans("target", "signed", "unknown"), pin=("open5m", 6.599), gap_pct=9.67),
    Case("THR", "2026-05-22", "operator 2026-10-03: 'is not a buyout, release' - CECO merger, holders elect "
         "cash/stock/mix; the day ranged 2.39% (flag scan: day window)",
         True, "headline", "PASS",
         articles=(_item(_CECO_THR_TITLE, published="2026-05-21T12:00:00Z"),),
         headline=((_CECO_THR_TITLE, Ans("target", "signed", "mixed", "CECO Environmental")),),
         company="Thermon Group Holdings, Inc.", pin=("day", 2.3893)),
    Case("HZO", "2026-08-10", "operator 2026-10-03: 'is a real buyout, keep blocked' - final-round bidding (Blackstone, "
         "Donerail, Centerbridge), a PROPOSAL; the open ranged 0.15% (0.50% on the day)",
         True, "classifier", "BLOCK", "routine",
         ("HZO is gapping up on reports that Blackstone, Donerail and Centerbridge are in the final round of "
          "bidding for MarineMax.",),
         grader=Ans("target", "proposed", "unknown", "Blackstone, Donerail, Centerbridge"), pin=("open5m", 0.1542),
         gap_pct=45.42),
    Case("RNW", "2026-08-11", "operator 2026-10-03: 'is a real buyout, keep blocked' - the controlling holders' "
         "take-private PROPOSAL reaffirmed; the open ranged 0.74% (1.5% on the day)",
         True, "classifier", "BLOCK", "routine",
         ("RNW gapped up on a 6-K disclosing a confirmatory letter from CPPIB and founder-CEO Sumant Sinha "
          "reaffirming their take-private proposal.",),
         grader=Ans("target", "proposed", "unknown", "CPPIB and Sumant Sinha"), pin=("open5m", 0.7396),
         gap_pct=10.28),
    # ── his ruling 4 (2026-10-03, "Go with rec"): the two approved 10-02 rows the price reverses ──
    Case("NUVL", "2026-06-09", "operator 2026-10-03 ruling 4: NUVL 06-09 now BLOCKED - GSK takeover bid at a premium "
         "(PROPOSED; the 10-02 rule released it); gap +39%, the open ranged 0.11%, 0.67% on the day",
         True, "classifier", "BLOCK", "routine",
         ("NUVL gapped up on a reported takeover bid from GSK at a substantial premium.",),
         grader=Ans("target", "proposed", "unknown", "GSK"), pin=("open5m", 0.114), gap_pct=38.80),
    Case("IRDM", "2026-06-29", "operator 2026-10-03 ruling 4: IRDM 06-29 now RELEASED - a Viasat article said 'Rocket "
         "Lab announced an $8 billion acquisition of Iridium' (headline target/signed/unknown; the 10-02 rule blocked "
         "it); gap +19%, the open ranged 3.28%, 7.1% on the day - the price says free",
         True, "headline", "PASS", "routine",
         ("The only news attributes the gap-up to SpaceX-related sector momentum.",),
         grader=_NONE,
         articles=(_item("Why Viasat Stock Went to the Moon Today", ticker="IRDM",
                         description="Rocket Lab announced an $8 billion acquisition of Iridium Communications; "
                                     "a merger wave in satellite names.",
                         reasoning="Rocket Lab announced an $8 billion acquisition of Iridium Communications.",
                         published="2026-06-29T12:00:00Z"),),
         headline=(("Why Viasat Stock Went to the Moon Today",
                    Ans("target", "signed", "unknown", "Rocket Lab")),),
         company="Iridium Communications Inc.", pin=("open5m", 3.2847), gap_pct=18.92),
    # ── his ruling 3 (2026-10-03, "Go with rec"): THE PRICE-ONLY ARM — seven real buyouts the news
    # called 'none' (the replayed grader read a 200-char excerpt): gap >= 20% AND open window <= 0.5%
    # blocks regardless of the news. Recorded readings: scripts/probes/_692/pin_backtest_measures.json ──
    Case("TMHC", "2026-06-01", "operator 2026-10-03 ruling 3 (price-only arm): real buyout, news read 'Berkshire stake'; "
         "gap +22%, open window 0.25%, 0.43% on the day",
         True, "classifier", "BLOCK", "routine",
         ("TMHC gapped up on news that Berkshire Hathaway disclosed a large new stake in homebuilders.",),
         grader=_NONE, pin=("open5m", 0.2515), gap_pct=22.35),
    Case("APGE", "2026-06-22", "operator 2026-10-03 ruling 3 (price-only arm): real buyout, news read 'no discrete "
         "headline'; gap +47%, open window 0.41%, 0.41% on the day",
         True, "classifier", "BLOCK", "routine",
         ("APGE's latest gap up does not appear tied to a single discrete news headline.",),
         grader=_NONE, pin=("open5m", 0.4148), gap_pct=46.71),
    Case("SAFT", "2026-07-24", "operator 2026-10-03 ruling 3 (price-only arm): real buyout, news read 'sector move'; "
         "gap +41%, open window 0.37%, 0.53% on the day",
         True, "classifier", "BLOCK", "routine",
         ("[SEC 8-K filed 2026-07-23, items 7.01,9.01] SAFT appears to have gapped up mainly on a sector/name-specific move.",),
         grader=_NONE, pin=("open5m", 0.3689), gap_pct=41.23),
    Case("FBRX", "2026-07-27", "operator 2026-10-03 ruling 3 (price-only arm): real buyout (the flag scan caught it by "
         "headline on 08-10..12), news read 'bullish Street initiation'; gap +39%, open window 0.08%, 0.29% on the day",
         True, "classifier", "BLOCK", "routine",
         ("[SEC 8-K filed 2026-07-27, items 1.01,7.01,9.01] The recent gap up in FBRX is being driven primarily by "
          "bullish Street initiation and strong clinical data.",),
         grader=_NONE, pin=("open5m", 0.0785), gap_pct=39.49),
    Case("VREX", "2026-08-10", "operator 2026-10-03 ruling 3 (price-only arm): real buyout, news read 'pre-earnings "
         "positioning'; gap +48%, open window 0.11%, 0.68% on the day",
         True, "classifier", "BLOCK", "routine",
         ("VREX looks like it gapped up mainly because traders are positioning ahead of its third-quarter earnings release.",),
         grader=_NONE, pin=("open5m", 0.1088), gap_pct=48.19),
    Case("ARX", "2026-08-13", "operator 2026-10-03 ruling 3 (price-only arm): real buyout, news read 'pre-earnings "
         "positioning'; gap +44%, open window 0.46%, 0.87% on the day",
         True, "classifier", "BLOCK", "routine",
         ("ARX appears to be Accelerant Holdings; the most likely reason for the gap up is pre-earnings positioning.",),
         grader=_NONE, pin=("open5m", 0.4592), gap_pct=44.09),
    Case("WEAV", "2026-08-18", "operator 2026-10-03 ruling 3 (price-only arm): real buyout, news read 'earnings beat'; "
         "gap +32%, open window 0.48%, 0.48% on the day",
         True, "classifier", "BLOCK", "routine",
         ("[SEC 8-K filed 2026-08-18, items 8.01,9.01] WEAV appears to be moving on a company-specific earnings beat.",),
         grader=_NONE, pin=("open5m", 0.4795), gap_pct=31.83),
    Case("ATAI", "2026-07-16", "agent-read: the closest FREE >= 20% gapper to the price-only line - gap +32%, open "
         "window 0.99% (2.8% on the day); the arm must let it through (ATAI was pinned by a deal only from 07-24)",
         False, "classifier", "PASS", "routine",
         ("ATAI's recent gap up has been driven by a cluster of bullish catalysts around its psychedelic pipeline.",),
         grader=Ans("none", "speculation", "none"), pin=("open5m", 0.9901), gap_pct=31.81),
    Case("FWDI", "2026-09-18", "operator 2026-10-01: wrongly blocked - FWDI is the BIDDER for SkyAI",
         True, "classifier", "PASS", "mna",
         ("[SEC 8-K filed 2026-09-15, items 7.01,9.01] FWDI's latest identifiable catalyst is its renewed, "
          "sweetened proposal to acquire SkyAI, a Solana-treasury company.",),
         grader=Ans("buyer", "proposed", "unknown", "SkyAI")),
    Case("CHYM", "2026-09-09", "operator 2026-10-01: wrongly blocked - Chime buys Stride Bank $590M",
         True, "classifier", "PASS", "mna",
         ("[SEC 8-K filed 2026-09-08, items 1.01,7.01,9.01] CHYM gapped up on the announcement that Chime "
          "Financial agreed to acquire its longtime banking partner, Stride Bank, for $590 million in cash.",),
         grader=Ans("buyer", "signed", "cash", "Stride Bank")),
    Case("JBS", "2026-09-18", "operator 2026-10-01: wrongly blocked - JBS proposes to buy out Pilgrim's minority",
         True, "classifier", "PASS", "mna",
         ("[SEC 8-K filed 2026-09-15, items 8.01,9.01] JBS N.V. appears to be gapping up primarily on renewed "
          "attention to its proposed acquisition of the remaining publicly traded shares of Pilgrim's Pride.",),
         grader=Ans("buyer", "proposed", "unknown", "Pilgrim's Pride")),
    Case("GPRK", "2026-09-03", "operator 2026-10-01: wrongly blocked - Venezuela Bare Block entry, no deal",
         True, "classifier", "PASS", "mna",
         ("GPRK gapped up primarily on GeoPark's announcement of a major strategic entry into Venezuela "
          "through the Bare Block, a producing heavy-oil asset in the Orinoco Heavy Oil Belt.",),
         grader=_NONE),
    Case("WAY", "2026-09-15", "operator 2026-10-01: wrongly blocked - exploring strategic alternatives incl. a sale",
         True, "classifier", "PASS", "mna",
         ("WAY is gapping up on Reuters reporting that Waystar is exploring strategic alternatives, "
          "including a potential sale that could take the company private.",),
         grader=Ans("target", "proposed", "unknown"), pin=("open5m", 5.7021)),
    Case("CSR", "2026-09-09", "operator 2026-10-01: wrongly blocked - $8.1B ALL-STOCK merger with Independence Realty",
         True, "classifier", "PASS", "mna",
         ("[SEC 8-K filed 2026-09-09, items 1.01,7.01,9.01] CSR is gapping up because Centerspace announced "
          "an $8.1 billion all-stock merger with Independence Realty Trust (NYSE: IRT).",),
         grader=Ans("target", "signed", "stock", "Independence Realty Trust")),
    Case("SWKS", "2026-09-15", "operator 2026-10-01: wrongly blocked - proposed $22B merger with Qorvo (Skyworks the acquirer)",
         True, "classifier", "PASS", "mna",
         ("SWKS gapped up primarily on renewed optimism around its proposed $22 billion merger with Qorvo.",),
         grader=Ans("buyer", "signed", "stock", "Qorvo")),
    Case("IOVA", "2026-09-29", "operator 2026-10-01: wrongly blocked - raised revenue outlook; 'potential takeover targets' headline",
         True, "headline", "PASS", "strong",
         ("[SEC 8-K filed 2026-09-29, items 8.01,9.01] IOVA's latest reported gap-up catalyst is Iovance's "
          "raised 2026 revenue outlook, announced September 29.",),
         grader=_NONE,
         articles=(_item(_IOVA_VKTX_TITLE, published="2026-09-28T14:00:00Z"),),
         headline=((_IOVA_VKTX_TITLE, Ans("target", "speculation", "none")),),
         company="Iovance Biotherapeutics, Inc."),
    Case("VKTX", "2026-09-22", "operator 2026-10-01: wrongly blocked - Novo 'could pursue acquisitions' speculation "
         "(a free +23% gapper: the price-only arm reads 3.38% and lets it through)",
         True, "headline", "PASS", "strong",
         ("[SEC 8-K filed 2026-09-22, items 8.01,9.01] VKTX's latest move higher was driven primarily by "
          "renewed obesity-drug M&A speculation after Novo Nordisk said it could pursue larger acquisitions.",),
         grader=Ans("target", "speculation", "none"),
         articles=(_item(_IOVA_VKTX_TITLE, published="2026-09-21T14:00:00Z"),),
         headline=((_IOVA_VKTX_TITLE, Ans("target", "speculation", "none")),),
         company="Viking Therapeutics, Inc.", pin=("open5m", 3.3784), gap_pct=22.88),
    Case("RGTI", "2026-09-08", "operator 2026-10-01: wrongly blocked - $100M Commerce Dept FUNDING agreement",
         True, "headline", "PASS", "strong",
         ("[SEC 8-K filed 2026-09-08, items 1.01,3.02,7.01,8.01,9.01] RGTI gapped up primarily because Rigetti "
          "announced a binding $100 million funding agreement with the U.S. Department of Commerce.",),
         grader=_NONE,
         articles=(_item(_RGTI_TITLE, published="2026-09-08T12:30:00Z"),),
         headline=((_RGTI_TITLE, _NONE),),
         company="Rigetti Computing, Inc."),
    # ── the two true-positive rulings that must stay blocked (operator decision 1: shell) ──
    Case("SUNE", "2026-06-08", "operator 2026-07-04: TP - definitive reverse merger with Suniva",
         True, "headline", "BLOCK",
         articles=(_item(_SUNE_TITLE, ticker="SUNE",
                         description="Solar names rallied; one small cap exploded on a reverse merger.",
                         reasoning="Exploded 150% to $2.83 on announcement of definitive reverse merger "
                                   "with Suniva, the largest U.S. merchant solar cell manufacturer.",
                         published="2026-06-08T16:13:28Z"),),
         headline=((_SUNE_TITLE, Ans("shell", "signed", "stock", "Suniva")),),
         company="SUNation Energy, Inc."),
    Case("CLRO", "2026-07-02", "operator 2026-08-08: the ONE correct suppression - Cortigent merges into ClearOne",
         True, "headline", "BLOCK",
         articles=(_item(_CLRO_TITLE, published="2026-07-02T12:00:00Z"),),
         headline=((_CLRO_TITLE, Ans("shell", "signed", "stock", "Vivani / Cortigent")),),
         company="ClearOne, Inc."),
    # ── the 2026-07-04 / 07-12 / 08-08 false positives ──
    Case("MMED", "2026-06-03", "operator 2026-07-04: FP - 'not a single dramatic takeover' (negated keyword)",
         True, "keyword", "PASS", "routine",
         ("MMED's latest gap-up catalyst appears to be company-specific execution news around MiniMed's "
          "diabetes device rollout, not a single dramatic takeover or earnings shock.",),
         grader=_NONE),
    Case("FRMI", "2026-06-17", "operator 2026-07-04: FP - proxy campaign seeking strategic alternatives",
         True, "headline", "PASS",
         articles=(_item(_FRMI_TITLE, ticker="FRMI",
                         description="An activist pushes for a merger or sale of the company.",
                         reasoning="Stock gained 22.6% on proxy campaign announcement seeking strategic "
                                   "alternatives and board changes, including a potential merger.",
                         published="2026-06-11T06:54:45Z"),),
         headline=((_FRMI_TITLE, Ans("target", "proposed", "none")),),
         company="Fermi America"),
    Case("ONDS", "2026-05-28", "operator 2026-07-04: FP - Ondas is the BUYER of Omnisys; real earnings gap",
         True, "headline", "PASS", "strong",
         ("ONDS gapped up mainly on a Q1 2026 earnings blowout and a stronger forward outlook.",),
         grader=Ans("buyer", "completed", "none", "Omnisys"),
         articles=(_item(_ONDS_TITLE, published="2026-05-27T13:00:00Z"),),
         headline=((_ONDS_TITLE, Ans("buyer", "completed", "none", "Omnisys")),),
         company="Ondas Holdings, Inc."),
    Case("IMAX", "2026-05-22", "operator 2026-07-12: FP - 'exploring a sale', takeout speculation",
         True, "keyword", "PASS", "routine",
         ("IMAX gapped up on news that the company may be exploring a sale, which triggered a strong "
          "takeout/speculation bid in the stock, a potential buyout.",),
         grader=Ans("target", "proposed", "unknown"), pin=("open5m", 2.648)),
    Case("WEN", "2026-06-26", "operator 2026-08-08: FP - takeover speculation",
         True, "headline", "PASS",
         articles=(_item(_WEN_TITLE, ticker="WEN",
                         description="Some investors think a takeover could unlock value.",
                         reasoning="Despite current operational challenges, potential takeover interest "
                                   "could support the shares.",
                         published="2026-06-26T11:12:00Z"),),
         headline=((_WEN_TITLE, Ans("target", "speculation", "none")),),
         company="The Wendy's Company", pin=("day", 13.2051)),
    Case("UMAC", "2026-06-30", "operator 2026-08-08: FP - Russell 2000 inclusion; keyword 'definitive agreement'",
         True, "keyword", "PASS", "routine",
         ("UMAC gapped up on a mix of a fresh index inclusion and a broader drone-sector tailwind; it also "
          "signed a definitive agreement with a supplier.",),
         grader=_NONE),
    Case("LCID", "2026-07-17", "operator 2026-08-08: FP - CEO DENIAL of take-private rumours",
         True, "headline", "PASS",
         articles=(_item(_LCID_TITLE, published="2026-07-16T20:00:00Z"),),
         headline=((_LCID_TITLE, Ans("target", "speculation", "none")),),
         company="Lucid Group, Inc."),
    Case("SOUN", "2026-08-06", "operator 2026-08-08: FP - blowout Q2 print; keyword 'merger'",
         True, "keyword", "PASS", "routine",
         ("[SEC 8-K filed 2026-08-05, items 2.02,9.01] SOUN's gap-up is driven by a blowout Q2 earnings print; "
          "a merger was mentioned elsewhere.",),
         grader=_NONE),
    Case("LII", "2026-06-15", "operator 2026-08-08: FP - HVAC operating momentum; keyword 'takeover'",
         True, "keyword", "PASS", "routine",
         ("LII gapped up on operating momentum and broader HVAC strength; no takeover news.",),
         grader=_NONE),
    Case("SCZM", "2026-06-15", "operator 2026-08-08: FP - broad market commentary; keyword 'merger'",
         True, "keyword", "PASS", "routine",
         ("I don't see a specific catalyst for SCZM; the only material is broad market commentary about a "
          "merger elsewhere.",),
         grader=_NONE),
    # ── AGENT-READ plumbing cases (his to label; never findings) ──
    Case("CECO", "2026-05-22", "agent-read: CECO is the BUYER on the same title as THR",
         False, "headline", "PASS",
         articles=(_item(_CECO_THR_TITLE, published="2026-05-21T12:00:00Z"),),
         headline=((_CECO_THR_TITLE, Ans("buyer", "signed", "mixed", "Thermon")),),
         company="CECO Environmental Corp.", pin=("day", 2.4208)),
    Case("ROKU", "2026-06-24", "agent-read: 'Fox Corp. Buys Roku For $22 Billion' (the #284 regex read ROKU as acquirer); "
         "his 10-03 approval kept it blocked - the day ranged 1.84% (day window)",
         False, "headline", "BLOCK",
         articles=(_item(_ROKU_TITLE, ticker="ROKU",
                         description="This week's deals include a strategic transaction for Roku.",
                         reasoning="Being acquired by Fox at $160 per share in cash.",
                         published="2026-06-18T18:05:05Z"),),
         headline=((_ROKU_TITLE, Ans("target", "signed", "cash", "Fox Corp.")),),
         company="Roku, Inc.", pin=("day", 1.8355)),
    Case("QBTS", "2026-05-21", "agent-read: IonQ/SkyWater roundup bleed - QBTS not in insights, never asked",
         False, "headline", "PASS",
         articles=(_item(_QBTS_TITLE, description="IonQ's merger vote with SkyWater advanced.",
                         others=(("IONQ", "IonQ's merger with SkyWater advanced."),),
                         published="2026-05-11T20:00:00Z"),),
         company="D-Wave Quantum Inc.", pin=("open5m", 5.4688)),
    # MGM stays agent-read (his 10-03 approval of the released list stands; the price agrees, by 0.24pp)
    Case("MGM", "2026-06-01", "agent-read: People Inc.'s non-binding $48.30 cash proposal (headline; the grader found no "
         "deal); the open ranged 1.24% (6.5% on the day) - the price says free, by 0.24pp",
         False, "headline", "PASS", "routine",
         ("MGM gapped up on Nevada gaming data and analyst target hikes.",),
         grader=_NONE,
         articles=(_item("Barry Diller's People Makes Move To Take Casino Giant MGM Private", ticker="MGM",
                         description="People Inc. proposed acquiring MGM's remaining shares for $48.30 per share "
                                     "in cash, a non-binding take-private offer.",
                         reasoning="Received a non-binding take-private offer at $48.30 per share.",
                         published="2026-06-01T11:00:00Z"),),
         headline=(("Barry Diller's People Makes Move To Take Casino Giant MGM Private",
                    Ans("target", "proposed", "cash", "People Inc.")),),
         company="MGM Resorts International", pin=("open5m", 1.2381), gap_pct=10.97),
    Case("KALV", "2026-05-25", "agent-read: shareholder-litigation notice - skipped by prefix, never asked",
         False, "headline", "PASS",
         articles=(_item("BRODSKY & SMITH SHAREHOLDER UPDATE: Notifying Investors of the Following "
                         "Investigations: KalVista Pharmaceuticals, Inc. (Nasdaq - KALV)",
                         description="Investigation into the merger announced last quarter.",
                         ticker="KALV", reasoning="Investigation following merger announcement.",
                         published="2026-05-25T12:00:00Z"),),
         company="KalVista Pharmaceuticals, Inc."),
)

CASES_BY_TICKER: dict[str, Case] = {c.ticker: c for c in CASES}


# ── fakes ──────────────────────────────────────────────────────────────────────────────────────

class FakeModel:
    """Answers the headline question from a case's (title -> Ans) fixtures and counts calls.
    An article with no fixture is an UNPLANNED question — recorded, answered with an error."""

    def __init__(self, ticker: str, answers: dict[str, Ans]):
        self.ticker = ticker
        self.answers = answers
        self.calls: list[str] = []
        self.unplanned: list[str] = []
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kw: Any):
        prompt = kw["messages"][0]["content"]
        title = next((ln[len("Title: "):] for ln in prompt.splitlines() if ln.startswith("Title: ")), "")
        self.calls.append(title)
        ans = self.answers.get(title)
        if ans is None:
            self.unplanned.append(title)
            raise RuntimeError(f"unplanned headline question for {self.ticker}: {title!r}")
        block = SimpleNamespace(type="tool_use", name="classify_deal_headline", input={
            "deal_role": ans.role, "deal_status": ans.status,
            "deal_consideration": ans.consideration, "deal_counterparty": ans.counterparty,
            "note": "fixture answer"})
        return SimpleNamespace(content=[block], stop_reason="tool_use",
                               usage=SimpleNamespace(input_tokens=0, output_tokens=0))


class Outcome(NamedTuple):
    blocked: bool
    meta: Optional[dict]
    calls: list
    unplanned: list
    audits: list


def pin_reader_for(case: Case):
    """The case's RECORDED price reading as the `pin_reader` the detector would pass: None when
    the case carries no price (the 10-02 verdict), an unreadable reading when `pin_pending`."""
    from agents.market_intelligence import ma_filter as mf
    if case.pin is None and not case.pin_pending:
        return None
    window = (case.pin or ("open5m", None))[0]
    thr = mf.OPEN_WINDOW_PIN_MAX_PCT if window == "open5m" else mf.DAY_WINDOW_PIN_MAX_PCT

    async def _reader():
        if case.pin_pending:
            return mf.PinReading(window, None, thr, 0, False, "pre_market", case.day)
        return mf.PinReading(window, float(case.pin[1]), thr, 5 if window == "open5m" else 1,
                             True, "", case.day)
    return _reader


async def run_new(case: Case, *, unanswered_blocks: bool = False, now_et: datetime = _OUTSIDE_ORB,
                  skip_in_orb: bool = False, budget_pool: str = "shared",
                  pin_reader=None, use_case_pin: bool = True) -> Outcome:
    """The NEW `is_likely_ma` on this case, with Polygon + the model replaced by fixtures and the
    price reading replaced by the case's RECORDED reading (`pin_reader_for`; pass `pin_reader`
    to override, `use_case_pin=False` for no reader at all).
    `skip_in_orb` / `budget_pool` are what the EP scan passes (`ep_detector._post_grade_filters`)."""
    from agents.market_intelligence import ma_filter as mf
    model = FakeModel(case.ticker, dict(case.headline))
    audits: list = []

    async def _capture(event_type, ticker, summary, detail):
        audits.append((event_type, summary, detail))

    grader = (mf.DealAnswer(*case.grader) if case.grader is not None else None)
    if pin_reader is None and use_case_pin:
        pin_reader = pin_reader_for(case)
    mf.reset_headline_day()
    mf._COMPANY_NAME_MEMO.clear()
    with ExitStack() as st:
        st.enter_context(patch("agents.market_intelligence.collector.get_polygon_news",
                               new=AsyncMock(return_value=[dict(a) for a in case.articles])))
        st.enter_context(patch("agents.market_intelligence.collector.get_ticker_details",
                               new=AsyncMock(return_value={"name": case.company} if case.company else {})))
        st.enter_context(patch.object(mf, "_get_headline_client", return_value=model))
        st.enter_context(patch.object(mf, "_audit_once", new=_capture))
        st.enter_context(patch.object(mf, "_unanswered_blocks",
                                      new=AsyncMock(return_value=unanswered_blocks)))
        st.enter_context(patch("agents.market_intelligence.spend_tracker.log_anthropic_call_safe",
                               new=AsyncMock(return_value=None)))

        async def _raw_audit(event_type, summary, detail=None):
            audits.append((event_type, summary, detail))
        st.enter_context(patch("agents.market_intelligence.db.log_audit_event", new=_raw_audit))
        blocked, meta = await mf.is_likely_ma(
            case.ticker, deal_answer=grader, check_polygon=True,
            on_or_before=date.fromisoformat(case.day),
            catalyst_quality=case.catalyst_quality,
            catalyst_texts=list(case.catalyst_texts) or None,
            now_et=now_et, skip_in_orb=skip_in_orb, budget_pool=budget_pool,
            pin_reader=pin_reader, gap_pct=case.gap_pct)
    return Outcome(blocked, meta, model.calls, model.unplanned, audits)


def load_old_module(path: str):
    """Load an OLD ma_filter.py (e.g. origin/main's, exported with `git show`) as a module."""
    spec = importlib.util.spec_from_file_location("ma_filter_old_692", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def run_old(case: Case, old_mod) -> tuple[bool, Optional[dict]]:
    """The OLD `is_likely_ma` on the same old-path inputs (no deal answer — it had none)."""
    with ExitStack() as st:
        st.enter_context(patch("agents.market_intelligence.collector.get_polygon_news",
                               new=AsyncMock(return_value=[dict(a) for a in case.articles])))
        st.enter_context(patch("agents.market_intelligence.collector.get_ticker_details",
                               new=AsyncMock(return_value={"name": case.company} if case.company else {})))
        st.enter_context(patch("agents.market_intelligence.db.get_pool",
                               new=AsyncMock(side_effect=RuntimeError("no DB in the harness"))))
        st.enter_context(patch("agents.market_intelligence.db.log_audit_event",
                               new=AsyncMock(return_value=None)))
        if hasattr(old_mod, "_COMPANY_NAME_MEMO"):
            old_mod._COMPANY_NAME_MEMO.clear()
        return await old_mod.is_likely_ma(
            case.ticker, catalyst_quality=case.catalyst_quality,
            catalyst_texts=list(case.catalyst_texts) or None, check_polygon=True,
            on_or_before=date.fromisoformat(case.day))


def _verdict(blocked: bool) -> str:
    return "BLOCK" if blocked else "PASS"


async def _main(old_path: Optional[str]) -> int:
    old_mod = load_old_module(old_path) if old_path else None
    fails = 0
    flips = 0
    print(f"#692 M&A filter regression harness (N={len(CASES)}; "
          f"{sum(c.ground_truth for c in CASES)} operator-labelled, "
          f"{sum(not c.ground_truth for c in CASES)} agent-read)\n")
    hdr = f"  {'ticker':6} {'date':10} {'truth':5} {'expect':6} {'new':6}"
    if old_mod:
        hdr += f" {'old':6} {'flip':4}"
    print(hdr + "  source / calls")
    for c in CASES:
        out = await run_new(c)
        new = _verdict(out.blocked)
        ok = new == c.expected and not out.unplanned
        line = (f"  {c.ticker:6} {c.day:10} {'OP' if c.ground_truth else 'agent':5} "
                f"{c.expected:6} {new:6}")
        if old_mod:
            ob, _ = await run_old(c, old_mod)
            old = _verdict(ob)
            flip = old != new
            flips += flip
            line += f" {old:6} {'YES' if flip else '':4}"
        src = (out.meta or {}).get("source", "-")
        line += f"  {src} / {len(out.calls)} call(s)"
        if c.pin is not None:
            line += f" / {c.pin[0]} {c.pin[1]:.2f}%"
        if c.gap_pct is not None:
            line += f" / gap {c.gap_pct:.1f}%"
        if (out.meta or {}).get("pin"):
            line += f" -> {'PINNED' if out.meta['pin'].get('pinned') else 'free'}"
        elif out.blocked is False and any(a[0] == "mna_filter_released" and "pin_free" in
                                          (a[2] or {}).get("old_reasons", []) for a in out.audits):
            line += " -> free (released on price)"
        if not ok:
            line += "   <-- " + ("UNPLANNED QUESTION" if out.unplanned else "MISS")
            if c.ground_truth:
                fails += 1
        print(line)
    print(f"\n  operator-labelled misses: {fails}")
    if old_mod:
        print(f"  verdicts that differ from the OLD module: {flips}")
    return 1 if fails else 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-module", help="path to an OLD ma_filter.py to compare against")
    args = ap.parse_args()
    sys.exit(asyncio.run(_main(args.old_module)))
