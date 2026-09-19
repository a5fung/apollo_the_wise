"""Shortlist pre-score HISTORICAL REPLAY (2026-08-22) — gap-top-20 vs prescore-top-20.

Re-ranks every logged scan day (mi_ep_scan_log capture, last-seen state per
name per day) plus the reconstructed 2026-04-08 open board under BOTH shortlist
keys — gap-descending (the pre-2026-08-22 order) and the three-term pre-score —
using the LIVE arithmetic imported from `ep_rubric` (`shortlist_prescore` /
`shortlist_sort_key` / `SHORTLIST_SIZE`), never a reimplementation. Reports:
which names each key adds/drops, how the labelled real-EP fixture members fare,
and forward-outcome distributions (5-day max-high / close vs the day-0 open,
from daily bars) for the added and dropped sets.

Inputs (CAPTURED ONCE, 2026-08-22 — scripts/probes/_prescore_replay_capture.sql;
never re-run to re-read):
    scripts/probes/_prescore_replay_boards.psv        q1 scan-log boards
    scripts/probes/_prescore_replay_themes.psv        q2 Accelerating/Mainstream sets
    scripts/probes/_prescore_replay_outcomes.psv      q3 forward outcomes (bars)
    scripts/probes/_prescore_replay_board0408.psv     q4 04-08 open-board reconstruction
    scripts/probes/_prescore_replay_outcomes0408.psv  q5 04-08 forward outcomes
    scripts/probes/_prescore_replay_advfill.psv       q6 bars-based ADV for the 13
        April days (04-13..04-30) whose scan-log rows predate the adv column —
        without it the pre-score degenerates to a flat-composite ticker-order
        lottery on exactly those days (found on the first run of this script)

Method notes (stated in the output + the analysis doc):
  - Board = the day's scan-log names minus `filter:universe_*` visibility rows
    (never candidates). Both keys rank the SAME set, so the comparison is fair
    even where the era's gap floor differed.
  - Day-level approximation: the live cap acts per 5-min tick; last-seen state
    is the settled day picture (house `get_ep_scan_log` idiom) and has the best
    ADV coverage (the top-50-by-gap got backfilled historically).
  - Theme membership per day = the latest mi_themes snapshot <= scan_date
    within 7 days (mirrors live `get_active_themes(stale_after_days=7)`).
  - ADV$ counts only real 20-day bases (rs_universe / polygon_20d); 'pending'
    rows rescale, exactly like the live pre-score.
Output: full text to stdout (captured to
scripts/probes/_prescore_replay_out.txt, read many).

$0 — reads local capture files only. Read-only. No LLM calls.
"""
from __future__ import annotations

import pathlib
import sys
from collections import defaultdict
from datetime import date, timedelta
from statistics import median

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from agents.market_intelligence.ep_rubric import (  # noqa: E402
    SHORTLIST_SIZE, shortlist_prescore, shortlist_sort_key)
from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS  # noqa: E402

_PROBES = _REPO / "scripts" / "probes"
# bars_20d = the q6/q4 reconstruction basis (mean volume over the prior <=20
# bars) — a real 20-day basis, flagged separately in the day lines.
_REAL_ADV = ("rs_universe", "polygon_20d", "bars_20d")


def _f(x: str) -> "float | None":
    try:
        return float(x) if x != "" else None
    except ValueError:
        return None


def _load_advfill() -> dict[tuple[date, str], float]:
    fill: dict[tuple[date, str], float] = {}
    for line in (_PROBES / "_prescore_replay_advfill.psv").read_text().splitlines():
        p = line.split("|")
        if len(p) == 3 and p[2] != "":
            fill[(date.fromisoformat(p[0]), p[1])] = float(p[2])
    return fill


def _load_boards() -> dict[date, list[dict]]:
    advfill = _load_advfill()
    boards: dict[date, list[dict]] = defaultdict(list)
    for line in (_PROBES / "_prescore_replay_boards.psv").read_text().splitlines():
        p = line.split("|")
        if len(p) < 11:
            continue
        reason = p[8]
        if reason.startswith("filter:universe_"):
            continue  # #570 visibility rows — never candidates
        day = date.fromisoformat(p[0])
        adv, adv_source = _f(p[4]), p[5]
        if adv is None and (day, p[1]) in advfill:
            adv, adv_source = advfill[(day, p[1])], "bars_20d"
        boards[day].append({
            "ticker": p[1], "gap_pct": _f(p[2]), "prev_close": _f(p[3]),
            "adv": adv, "adv_source": adv_source,
            "rank_by_gap_logged": _f(p[6]), "reason": reason,
            "ep_score": _f(p[9]), "tier": p[10],
        })
    return boards


def _load_themes() -> dict[date, set[str]]:
    by_day: dict[date, set[str]] = defaultdict(set)
    for line in (_PROBES / "_prescore_replay_themes.psv").read_text().splitlines():
        p = line.split("|")
        if len(p) < 4:
            continue
        by_day[date.fromisoformat(p[0])].update(p[3].split())
    return dict(by_day)


def theme_set_for(day: date, themes: dict[date, set[str]]) -> "tuple[set[str], date | None]":
    """Latest snapshot <= day within 7 days — the live stale_after_days=7 read."""
    for back in range(0, 8):
        d = day - timedelta(days=back)
        if d in themes:
            return themes[d], d
    return set(), None


def _load_outcomes(name: str) -> dict[tuple, dict]:
    out: dict[tuple, dict] = {}
    for line in (_PROBES / name).read_text().splitlines():
        p = line.split("|")
        if len(p) == 6:      # q3: scan_date|ticker|open|close|maxhigh5|close5
            key = (date.fromisoformat(p[0]), p[1])
            out[key] = {"open_d0": _f(p[2]), "close_d0": _f(p[3]),
                        "max_high_5d": _f(p[4]), "close_5d": _f(p[5])}
        elif len(p) == 5:    # q5: ticker|open|close|maxhigh5|close5
            key = (date(2026, 4, 8), p[0])
            out[key] = {"open_d0": _f(p[1]), "close_d0": _f(p[2]),
                        "max_high_5d": _f(p[3]), "close_5d": _f(p[4])}
    return out


def rank_board(rows: list[dict], theme_set: set[str]) -> tuple[dict, dict]:
    """Both orderings on the SAME rows. Gap order: gap desc, ticker asc for a
    deterministic tie order (live is stable-by-snapshot-iteration, which is not
    reconstructible — ties at the gap boundary are noted, not resolved)."""
    gap_sorted = sorted(rows, key=lambda r: (-(r["gap_pct"] or 0.0), r["ticker"]))
    rank_gap = {r["ticker"]: i + 1 for i, r in enumerate(gap_sorted)}
    scored = []
    for r in rows:
        advd = (r["adv"] * r["prev_close"]
                if r["adv"] and r["prev_close"] and r["adv_source"] in _REAL_ADV
                else None)
        pre = shortlist_prescore(adv_dollar=advd, gap_pct=r["gap_pct"],
                                 in_active_theme=r["ticker"] in theme_set)
        scored.append((shortlist_sort_key(r["ticker"], pre["composite"], advd),
                       r["ticker"]))
    scored.sort()
    rank_pre = {t: i + 1 for i, (_, t) in enumerate(scored)}
    return rank_gap, rank_pre


def _ret(o: "dict | None", key: str) -> "float | None":
    if not o or not o.get("open_d0") or o.get(key) is None:
        return None
    return (o[key] / o["open_d0"] - 1.0) * 100


def _dist(label: str, rets: list[float]) -> str:
    if not rets:
        return f"    {label}: n=0"
    rets.sort()
    return (f"    {label}: n={len(rets)} median={median(rets):+.1f}% "
            f">=+10%: {sum(1 for r in rets if r >= 10)} "
            f">=+20%: {sum(1 for r in rets if r >= 20)} "
            f">=+50%: {sum(1 for r in rets if r >= 50)} "
            f"max={rets[-1]:+.1f}%")


def main() -> None:
    boards = _load_boards()
    themes = _load_themes()
    outcomes = _load_outcomes("_prescore_replay_outcomes.psv")
    outcomes.update(_load_outcomes("_prescore_replay_outcomes0408.psv"))

    # Reconstructed 04-08 open board enters as one more day (its own ADV basis:
    # 20-bar mean volume — real, so adv_source marked rs_universe-equivalent).
    d0408 = date(2026, 4, 8)
    rows0408 = []
    for line in (_PROBES / "_prescore_replay_board0408.psv").read_text().splitlines():
        p = line.split("|")
        if len(p) < 5:
            continue
        rows0408.append({
            "ticker": p[0], "prev_close": _f(p[1]), "gap_pct": _f(p[3]),
            "adv": _f(p[4]), "adv_source": "bars_20d",
            "rank_by_gap_logged": None, "reason": "(reconstructed 04-08 board)",
            "ep_score": None, "tier": ""})
    boards[d0408] = rows0408

    fixture = {(m.ticker, date.fromisoformat(m.alert_date)) for m in MUST_NOT_MISS}
    fixture_days = {d for _, d in fixture}

    days = sorted(boards)
    churn_days = 0
    added_all: list[tuple[date, str]] = []
    dropped_all: list[tuple[date, str]] = []
    live_basis_days: set[date] = set()
    print(f"REPLAY — {len(days)} boards ({days[0]} .. {days[-1]}), "
          f"SHORTLIST_SIZE={SHORTLIST_SIZE}")
    print("basis per day: LIVE = the scan log's own adv (2026-05-01 onward, "
          "100% coverage) · ADVFILL = bars-based q6 backfill (04-13..04-30) · "
          "RECON = the reconstructed 04-08 open board")
    print("=" * 78)
    for day in days:
        rows = boards[day]
        srcs = {r["adv_source"] for r in rows if r["adv"] is not None}
        basis = ("RECON" if day == d0408
                 else "ADVFILL" if "bars_20d" in srcs else "LIVE")
        if basis == "LIVE":
            live_basis_days.add(day)
        tset, tday = theme_set_for(day, themes)
        rank_gap, rank_pre = rank_board(rows, tset)
        top_gap = {t for t, r in rank_gap.items() if r <= SHORTLIST_SIZE}
        top_pre = {t for t, r in rank_pre.items() if r <= SHORTLIST_SIZE}
        added = sorted(top_pre - top_gap)
        dropped = sorted(top_gap - top_pre)
        if added or dropped:
            churn_days += 1
            added_all += [(day, t) for t in added]
            dropped_all += [(day, t) for t in dropped]
        line = (f"{day} [{basis:7s}] board={len(rows):3d} theme_snap={tday} "
                f"in_theme_on_board={sum(1 for r in rows if r['ticker'] in tset):2d} "
                f"added={len(added):2d} dropped={len(dropped):2d}")
        if added or dropped:
            line += f"  +{','.join(added) or '-'}  -{','.join(dropped) or '-'}"
        print(line)
        for tk, fd in sorted(fixture):
            if fd == day and tk in rank_gap:
                print(f"    [labelled EP] {tk}: gap_rank={rank_gap[tk]} "
                      f"prescore_rank={rank_pre[tk]} "
                      f"gap_top20={'Y' if tk in top_gap else 'n'} "
                      f"prescore_top20={'Y' if tk in top_pre else 'n'} "
                      f"in_theme={'Y' if tk in tset else 'n'}")

    print("=" * 78)
    print(f"days with any top-{SHORTLIST_SIZE} difference: {churn_days} of {len(days)}")
    print(f"total added (prescore-only) name-days: {len(added_all)}; "
          f"dropped (gap-only): {len(dropped_all)}")

    for key, label in (("max_high_5d", "fwd 5d MAX-HIGH vs d0 open"),
                       ("close_5d", "fwd 5d close vs d0 open")):
        print(f"\nOutcome distribution — {label}:")
        print(_dist("ADDED by prescore ", [
            r for r in (_ret(outcomes.get((d, t)), key) for d, t in added_all)
            if r is not None]))
        print(_dist("DROPPED by prescore", [
            r for r in (_ret(outcomes.get((d, t)), key) for d, t in dropped_all)
            if r is not None]))
        print("  LIVE-basis days only (scan log's own ADV, 2026-05-01 onward):")
        print(_dist("ADDED by prescore ", [
            r for r in (_ret(outcomes.get((d, t)), key)
                        for d, t in added_all if d in live_basis_days)
            if r is not None]))
        print(_dist("DROPPED by prescore", [
            r for r in (_ret(outcomes.get((d, t)), key)
                        for d, t in dropped_all if d in live_basis_days)
            if r is not None]))

    # fixture members whose day has no board at all
    print("\nLabelled fixture members with NO board coverage in this replay "
          "(pre-scan-log day other than 04-08, or name absent from that day's log):")
    for tk, fd in sorted(fixture, key=lambda x: (x[1], x[0])):
        rows = boards.get(fd)
        if not rows or tk not in {r["ticker"] for r in rows}:
            print(f"    {tk} {fd}"
                  + ("  (day has a board; name not on it)" if rows else "  (no board)"))

    # theme coverage on the day that matters most
    tset, tday = theme_set_for(d0408, themes)
    print(f"\n04-08 theme reconstruction: snapshot={tday}, "
          f"{len(tset)} tickers in Accelerating/Mainstream themes; "
          f"{sum(1 for r in rows0408 if r['ticker'] in tset)} of them on the board")


if __name__ == "__main__":
    main()
