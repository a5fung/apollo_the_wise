"""#210 2026-10-10 (review fix) — PROOF that the reference matcher + frame in tv_story_matcher.py
satisfy every expectation in fixture_cases.json. Run from this directory:

    python3 run_fixture_proof.py > run_fixture_proof.out

Prints (1) every same-day item the window showed, per case, with its bucket, verdict and the
title of ours it matched — so a reader can check each verdict against the hand table in the
doc — and (2) a PASS/FAIL table, one row per assertion, exit 1 on any FAIL. $0, no network,
no DB. The Sonnet card ports these assertions 1:1 into tests/test_210_tv_news_shadow.py.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import tv_story_matcher as m  # noqa: E402

ET = ZoneInfo("America/New_York")
HELD = {"title", "story", "event", "move"}   # every verdict meaning "a story we held"

results: list[tuple[str, str, bool, str]] = []   # (case, check, ok, detail)


def check(case: str, name: str, ok: bool, detail: str = "") -> None:
    results.append((case, name, bool(ok), detail))


def iso_to_et(s) -> datetime | None:
    if s is None:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(ET)


def load_case(c: dict) -> dict:
    our_items = []
    our_titles = []
    for src in ("polygon", "alpaca", "fmp"):
        for it in c["our_corpus"][src]:
            our_items.append({"title": it["title"], "published": iso_to_et(it.get("published")),
                              "src": src})
            our_titles.append(it["title"])
    alert_date = date.fromisoformat(c["alert_date"])
    prior, how = m.prior_trading_day_holiday_aware(alert_date)
    return {
        "alert_date": alert_date, "prior": prior, "prior_how": how,
        "captured_at": datetime.fromisoformat(c["our_captured_at"]),
        "our_items": our_items,
        "company": m.company_tokens(None, c["ticker"], our_titles),
        "tv_items": c["tv_items"],
    }


def fmt_et(unix: int) -> str:
    return datetime.fromtimestamp(unix, tz=ET).strftime("%m-%d %H:%M")


def run_case(name: str, c: dict, exp: dict) -> None:
    L = load_case(c)
    frame = m.build_frame(alert_date=L["alert_date"], prior_trading_day=L["prior"],
                          captured_at=L["captured_at"], our_items=L["our_items"],
                          tv_items=L["tv_items"], company=L["company"])
    print("=" * 110)
    print(f"{name}  alert_date={L['alert_date']}  prior_trading_day={L['prior']} ({L['prior_how']})  "
          f"captured_at={L['captured_at']:%m-%d %H:%M:%S} ET  ours={len(L['our_items'])}  "
          f"tv_window={len(L['tv_items'])}  company_tokens={sorted(L['company'])}")
    print(f"  reach_period_start={frame['tv_coverage_reaches_period_start']}  "
          f"unseen_min={frame['tv_unseen_minutes_at_period_start']}  "
          f"buckets before/repoll/after={frame['tv_items_before_grade']}/"
          f"{frame['tv_items_in_repoll_window']}/{frame['tv_items_after_cutoff']}")
    print(f"  tv_match_summary={json.dumps(frame['tv_match_summary'])}")
    print(f"  tv_items_unmatched_seen={[(i['title'][:50], i['match'], i['bucket']) for i in frame['tv_items_unmatched_seen']]}")
    print(f"  tv_items_we_missed={'NULL' if frame['tv_items_we_missed'] is None else [i['title'][:50] for i in frame['tv_items_we_missed']]}")
    print("  -- every same-day item the window showed (bucket | verdict | TV title -> ours):")
    for it in sorted(L["tv_items"], key=lambda x: x["published"]):
        v = frame["_verdicts"].get(it["title"])
        if not v:
            continue
        b, verdict, matched = v
        print(f"     {fmt_et(it['published'])} {b:13} {verdict:6} | {it['title'][:62]:62} -> "
              f"{(matched or '-')[:55]}")

    # frame columns
    for col in ("tv_items_before_grade", "tv_items_in_repoll_window", "tv_items_after_cutoff",
                "tv_coverage_reaches_period_start", "tv_unseen_minutes_at_period_start"):
        if col in exp:
            check(name, col, frame[col] == exp[col], f"got {frame[col]} expected {exp[col]}")
    if "tv_items_we_missed" in exp:
        got = frame["tv_items_we_missed"]
        want = exp["tv_items_we_missed"]
        ok = (got is None and want is None) or (got is not None and want is not None and
                                                [i["title"] for i in got] == [i["title"] for i in want])
        check(name, "tv_items_we_missed", ok,
              f"got {'NULL' if got is None else len(got)} expected {'NULL' if want is None else len(want)}")
    if "tv_items_unmatched_seen" in exp:
        got = [i["title"] for i in frame["tv_items_unmatched_seen"]]
        check(name, "tv_items_unmatched_seen", got == [i.get("title", i) if isinstance(i, dict) else i
                                                        for i in exp["tv_items_unmatched_seen"]],
              f"got {got}")
    if "tv_items_unmatched_seen_titles" in exp:
        got = [i["title"] for i in frame["tv_items_unmatched_seen"]]
        check(name, "tv_items_unmatched_seen_titles", got == exp["tv_items_unmatched_seen_titles"],
              f"got {got}")
        if frame["tv_items_unmatched_seen"]:
            check(name, "tv_items_unmatched_seen_match",
                  all(i["match"] == exp["tv_items_unmatched_seen_match"]
                      for i in frame["tv_items_unmatched_seen"]),
                  f"got {[i['match'] for i in frame['tv_items_unmatched_seen']]}")
    if "tv_items_we_missed_titles" in exp:
        got = frame["tv_items_we_missed"]
        check(name, "tv_items_we_missed_titles",
              got is not None and [i["title"] for i in got] == exp["tv_items_we_missed_titles"],
              f"got {'NULL' if got is None else [i['title'][:40] for i in got]}")
        if got:
            check(name, "tv_items_we_missed_bucket", all(i["bucket"] == exp["tv_items_we_missed_bucket"] for i in got),
                  f"got {[i['bucket'] for i in got]}")
            check(name, "tv_items_we_missed_match", all(i["match"] == exp["tv_items_we_missed_match"] for i in got),
                  f"got {[i['match'] for i in got]}")
    if exp.get("seen_verdicts_all_held"):
        seen = [(t, v) for t, v in frame["_verdicts"].items() if v[0] in ("before_grade", "repoll_window")]
        bad = [(t[:50], v[1]) for t, v in seen if v[1] not in HELD]
        check(name, f"all {len(seen)} seen items read as held", not bad, f"not held: {bad}")
    # the summary must account for every bucketed item
    tot = sum(sum(d.values()) for d in frame["tv_match_summary"].values())
    nb = frame["tv_items_before_grade"] + frame["tv_items_in_repoll_window"] + frame["tv_items_after_cutoff"]
    check(name, "tv_match_summary sums to the three buckets", tot == nb, f"{tot} vs {nb}")

    # pair assertions (direct match_tv_item calls against ONE item of ours)
    def pair(tv_title: str, our_title: str) -> str:
        ours = next((o for o in L["our_items"] if o["title"] == our_title), None)
        if ours is None:
            return "OUR-TITLE-NOT-IN-CORPUS"
        return m.match_tv_item(tv_title, [ours], alert_date=L["alert_date"],
                               prior_trading_day=L["prior"], company=L["company"])[0]
    for tv_t, our_t in exp.get("must_match_as_held", []):
        v = pair(tv_t, our_t)
        check(name, f"held: {tv_t[:48]}", v in HELD, f"verdict={v}")
    for tv_t, our_t in exp.get("must_match_as_class_not_story", []):
        v = pair(tv_t, our_t)
        check(name, f"class-not-story: {tv_t[:40]}", v == "class", f"verdict={v}")
    if "control_must_match_as_event" in exp:
        tv_t, our_t = exp["control_must_match_as_event"]
        v = pair(tv_t, our_t)
        check(name, f"control event: {tv_t[:40]}", v == "event", f"verdict={v}")
    if "must_match_as_class_not_event" in exp:
        tv_t, our_t = exp["must_match_as_class_not_event"]
        v = pair(tv_t, our_t)
        check(name, f"preview is class: {tv_t[:40]}", v == "class", f"verdict={v}")


def main() -> int:
    d = json.load(open(os.path.join(HERE, "fixture_cases.json"), encoding="utf-8"))
    for name, c in d["cases"].items():
        run_case(name, c, d["expected"][name])

    # Rules the fixture pins beyond whole-case runs: Benzinga template firm extraction and the
    # same-$-target-different-firm collision (Needham $85 vs Stifel $85 must NOT cross-match).
    comp = {"penguin", "solutions", "peng"}
    check("RULES", "firm from Benzinga head template",
          m.analyst_firm("Rosenblatt Maintains Buy on Penguin Solutions, Raises Price Target to $100", comp) == "rosenblatt",
          str(m.analyst_firm("Rosenblatt Maintains Buy on Penguin Solutions, Raises Price Target to $100", comp)))
    check("RULES", "firm from Dow Jones tail template",
          m.analyst_firm("Penguin Solutions Price Target Raised to $85.00/Share From $75.00 by Stifel", comp) == "stifel",
          str(m.analyst_firm("Penguin Solutions Price Target Raised to $85.00/Share From $75.00 by Stifel", comp)))
    check("RULES", "firm from TradingView analyst-feed template",
          m.analyst_firm("Needham maintains Buy rating on Penguin Solutions, $85 price target", comp) == "needham",
          str(m.analyst_firm("Needham maintains Buy rating on Penguin Solutions, $85 price target", comp)))
    v = m.match_tv_item("Needham maintains Buy rating on Penguin Solutions, $85 price target",
                        [{"title": "Stifel Maintains Buy on Penguin Solutions, Raises Price Target to $85",
                          "published": datetime(2026, 10, 7, 9, 25, tzinfo=ET)}],
                        alert_date=date(2026, 10, 7), prior_trading_day=date(2026, 10, 6), company=comp)[0]
    check("RULES", "same $85 target, different firm -> class not story", v == "class", f"verdict={v}")
    check("RULES", "preview detection", m.is_preview("ACN Set to Report Q4 Earnings: Here's What Investors Should Know")
          and m.is_preview("Earnings Scheduled For October 6, 2026")
          and not m.is_preview("Accenture Q4 EPS $3.29 Beats $3.18 Estimate, Sales $18.700B Beat $18.030B Estimate"))
    check("RULES", "Market Talk is commentary even with a deal word",
          m.is_commentary("Accenture CEO Says Focus on Big Deals, AI Drove Strong Bookings — Market Talk")
          and not m.catalyst_classes("Accenture CEO Says Focus on Big Deals, AI Drove Strong Bookings — Market Talk"))
    check("RULES", "numeric anchors normalise $85.00 == $85",
          m.numeric_anchors("Price Target Raised to $85.00") == m.numeric_anchors("Raises Price Target to $85"))

    print("=" * 110)
    print(f"{'case':12} {'check':62} result  detail")
    fails = 0
    for case, name, ok, detail in results:
        fails += (not ok)
        print(f"{case:12} {name[:62]:62} {'PASS' if ok else 'FAIL':6}  {'' if ok else detail[:80]}")
    print("=" * 110)
    print(f"{len(results) - fails} PASS, {fails} FAIL out of {len(results)} assertions "
          f"over {len(d['cases'])} cases")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
