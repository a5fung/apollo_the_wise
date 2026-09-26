#!/usr/bin/env python3
"""Re-homing defect (fixed 2026-09-25) — DERIVE every current theme membership that arrived through
the Pass-2 sector-cap absorb (the SR/ATO path), with the co-movement reading the FIXED code would
have read at the branch. Read-only, $0: prod logs + prod rosters captured once, the LIVE
`theme_engine._comove_verdict` replayed offline over the captured closes.

THE PATH. `_merge_overlapping_themes` Pass 2 caps each keyword group (`_SECTOR_KEYWORD_GROUPS` —
"gas"/"crude"/"oil"/... = oil_gas, cap 2) and, until 2026-09-25, unioned every capped theme's whole
roster into the group's top theme: `top_theme["tickers"] = list(existing | extra)`. No ticker
overlap, no verdict, no validator, no audit row — the only trace is the INFO line
    Theme merge (sector cap): 'S' → 'G' (sector group 'g', N tickers absorbed)
where N = len(S's roster at Pass 2), NOT the delta. Pass 1 (overlap merge, protect strip) and Pass
1.5 (small-theme absorption) mutate rosters between the `[theme merge input]` snapshot and Pass 2,
so this script REPLAYS those logged operations per merge call to reconstruct the rosters at the
branch, then
    arrived(D) = S_p2 − G_p2 − board[D−1][G]
and a membership is CURRENT when the ticker sits in G's roster (following renames) on EVERY board
date from D through the board date — a gap means a later path re-admitted it (not this defect).

READING. `_comove_verdict(ticker, G_p2, ctx(before_date = D))` — the pair as the fixed code would
have judged it that night: against the target's PRE-absorb members, sessions strictly before the
run date. (Reading it against TODAY's roster is circular once the absorbed names are the majority of
the basket — 11 of 18 in the 09-25 tanker theme.) `corr_today` (vs today's roster, before today)
is reported beside it for the operator's frame; the verdict column is the at-branch one.

CALIBRATION (fails loudly): SR / ATO against the 09-24 tanker board roster with before_date
2026-09-25 must reproduce the readings in docs/analysis/657_comove_removals_2026-09-25.md
(0.105 / 0.2665) — same maths, same closes, same window.

COVERAGE (checked, not assumed — the first draft of this script claimed the logs began 09-10 off a
truncated `ls | head`; they do not). The prod file logs (market-agent.log, .1 … .10) run from
2026-04-15 and carry 470 `Theme merge (sector cap)` lines. The `[theme merge input]` snapshot this
replay rests on was first logged 2026-04-30, so a cap absorb from 04-15 … 04-29 (the ~250 lines of
the theme engine's first fortnight) CANNOT be reconstructed and is reported as "not replayable";
every absorb from 2026-04-30 on is derived. The board history (mi_themes) is pulled from 2026-04-01
so continuity can be checked from any replayable arrival to today. The closes pull starts 2026-04-01,
so an at-branch reading for an arrival before ~late June has fewer than 30 sessions and reads
"unjudgeable:thin_basket" here — it only matters if such an arrival is still current (none is).

INPUTS (captured 2026-09-25 evening PT, after the 09-25 run):
  rehome_merge_trace.log         prod file logs, the merge-machinery lines, ALL rotations (grep below)
  rehome_themes_since_0401.psv   mi_themes rows since 2026-04-01 (theme_date|name|stage|parent|source|tickers)
  rehome_renames_since_0401.psv  mi_theme_renames since 2026-04-01 (the #214 mass-flag renames)
  rehome_rename_events_since_0401.psv  theme_renamed_for_continuity / theme_renamed_on_mass_flag audit rows
  closes.csv                     the #657 pull (scripts/probes/_657_pull.sh) — gitignored; re-pull it.

  ssh apollo@87.99.134.162 "cd /home/apollo/apollo_the_wise/logs && grep -h 'theme merge input\\|Theme merge (sector cap)\\|Theme merge (overlap)\\|Theme merge (small-theme\\|Theme protect: stripped\\|Theme cap: removed\\|dropped: only' market-agent.log.10 market-agent.log.9 market-agent.log.8 market-agent.log.7 market-agent.log.6 market-agent.log.5 market-agent.log.4 market-agent.log.3 market-agent.log.2 market-agent.log.1 market-agent.log" > scripts/probes/_657_out/rehome_merge_trace.log
  ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -At -F '|' -c \\"SELECT theme_date, name, stage, coalesce(parent_theme,''), source, array_to_string(tickers, ',') FROM mi_themes WHERE theme_date >= '2026-04-01' ORDER BY theme_date, name\\"" > scripts/probes/_657_out/rehome_themes_since_0401.psv
  ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -At -F '|' -c \\"SELECT theme_date, mechanism, old_name, new_name FROM mi_theme_renames WHERE theme_date >= '2026-04-01' ORDER BY theme_date, id\\"" > scripts/probes/_657_out/rehome_renames_since_0401.psv
  ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -At -F '|' -c \\"SELECT (created_at AT TIME ZONE 'America/New_York')::date, event_type, replace(replace(summary, E'\\\\\\\\n', ' '), '|', '/'), replace(replace(detail, E'\\\\\\\\n', ' // '), '|', '/') FROM mi_audit_log WHERE created_at >= '2026-04-01' AND event_type IN ('theme_renamed_for_continuity','theme_renamed_on_mass_flag') ORDER BY id\\"" > scripts/probes/_657_out/rehome_rename_events_since_0401.psv

Usage: python scripts/probes/_rehome_sector_cap.py [--board 2026-09-25] [--out scripts/probes/_657_out]
Writes <out>/rehome_sector_cap_<board>.psv (every arrival, current or not) and prints the
markdown the doc section carries.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agents.market_intelligence import market_adjusted_correlation as mac  # noqa: E402
from agents.market_intelligence import theme_engine as te  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--board", default="2026-09-25")
ap.add_argument("--out", default="scripts/probes/_657_out")
ap.add_argument("--closes", default=None, help="closes.csv (default <out>/closes.csv)")
args = ap.parse_args()
OUT = ROOT / args.out
BOARD = date.fromisoformat(args.board)
CLOSES = Path(args.closes) if args.closes else OUT / "closes.csv"
BAR = te.ASSIGN_COMOVE_BAR

# ── prod rosters + renames ───────────────────────────────────────────────────────────────────
board: dict[date, dict[str, set[str]]] = defaultdict(dict)
stage_of: dict[tuple[date, str], str] = {}
for line in (OUT / "rehome_themes_since_0401.psv").read_text().splitlines():
    if not line.strip():
        continue
    d, name, stage, _parent, _source, tickers = line.split("|", 5)
    dd = date.fromisoformat(d)
    stage_of[(dd, name)] = stage
    if stage == "Retired":
        continue
    board[dd][name] = {t for t in tickers.split(",") if t}
BOARD_DATES = sorted(board)
assert BOARD in board, f"no rows for board {BOARD} — pull the rosters after the run"

renames: list[tuple[date, str, str]] = []
for line in (OUT / "rehome_renames_since_0401.psv").read_text().splitlines():
    if line.strip():
        d, _mech, old, new = line.split("|", 3)
        renames.append((date.fromisoformat(d), old, new))
# the #214 continuity renames and the mass-flag renames as audit rows (same parsing as the #657 probe)
_R_CONT = re.compile(r"'(.+?)' → '(.+?)' \(canonical")
_R_MASS = re.compile(r"^'(.+?)' renamed to '(.+?)' —")
for line in (OUT / "rehome_rename_events_since_0401.psv").read_text().splitlines():
    if not line.strip():
        continue
    d, et, summary, detail = line.split("|", 3)
    if et == "theme_renamed_for_continuity":
        for m in _R_CONT.finditer(detail):
            renames.append((date.fromisoformat(d), m.group(1), m.group(2)))
    elif (m := _R_MASS.match(summary)):
        renames.append((date.fromisoformat(d), m.group(1), m.group(2)))


def name_on(name: str, d: date) -> str:
    """The theme's name on board date d, following every rename dated <= d."""
    for rd, old, new in sorted(renames):
        if rd <= d and name == old:
            name = new
    return name


def prev_board_date(d: date) -> date | None:
    earlier = [x for x in BOARD_DATES if x < d]
    return earlier[-1] if earlier else None


# ── closes → the live context, per run date ──────────────────────────────────────────────────
closes: dict[str, dict[date, float]] = defaultdict(dict)
with open(CLOSES) as fh:
    for r in csv.DictReader(fh):
        closes[r["ticker"].upper()][date.fromisoformat(r["trade_date"])] = float(r["close"])
SPY = closes[mac.MARKET_TICKER]
_ctx: dict[date, te.ComoveContext] = {}


def ctx_for(before: date) -> te.ComoveContext:
    if before not in _ctx:
        cs = mac.session_index(SPY, before, mac.BELONGING_LOOKBACK_SESSIONS)
        assert len(cs) >= 2, f"no SPY sessions before {before}"
        mkt = mac.log_returns(SPY, cs)
        _ctx[before] = te.ComoveContext(before_date=before, excess=mac.excess_returns(closes, cs, mkt),
                                        n_sessions=len(cs) - 1, n_rows=0)
    return _ctx[before]


def read(ticker: str, members: list[str], before: date) -> tuple[float | None, int, int, str]:
    cv = te._comove_verdict(ticker, members, ctx_for(before))
    if cv is None:
        return None, 0, 0, "unjudgeable:no_context"
    if cv.admit is None:
        return None, cv.overlap, cv.basket_n, f"unjudgeable:{cv.reason}"
    return cv.corr, cv.overlap, cv.basket_n, ("admit" if cv.admit else "reject")


# ── calibration against the #657 readings the operator saw ──────────────────────────────────
_cal_board = date(2026, 9, 24)
_cal_theme = "Crude & Product Tanker Shipping"
_cal_members = sorted(board[_cal_board][_cal_theme])
cal = {t: read(t, _cal_members, date(2026, 9, 25))[0] for t in ("SR", "ATO")}
assert abs(cal["SR"] - 0.105) < 1e-4 and abs(cal["ATO"] - 0.2665) < 1e-4, \
    f"calibration failed — expected SR 0.105 / ATO 0.2665, got {cal}"
print(f"calibration: SR {cal['SR']} / ATO {cal['ATO']} against the {_cal_board} tanker roster "
      f"({len(_cal_members)} members, sessions before 2026-09-25) — matches #657 ✓")

# ── replay the merge calls from the prod trace ──────────────────────────────────────────────
LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) \[[^\]]+\] \w+: (.*)$")
R_INPUT = re.compile(r"^\[theme merge input\] (.*)$")
R_OVERLAP = re.compile(r"^Theme merge \(overlap\): '(.+?)' → '(.+?)' \(")
# two wordings: pre-2026-05 "from new cluster 'X' to preserve existing 'Y'", since "from 'X' to preserve 'Y'"
R_STRIP = re.compile(r"^Theme protect: stripped \[(.*?)\] from (?:new cluster )?'(.+?)' to preserve (?:existing )?'(.+?)'")
R_SMALL = re.compile(r"^Theme merge \(small-theme absorption\): '(.+?)' → '(.+?)' \(")
R_CAP = re.compile(r"^Theme merge \(sector cap\): '(.+?)' → '(.+?)' \(sector group '(\w+)', (\d+) tickers absorbed\)")

absorbs: list[dict] = []
not_replayable: list[tuple[date, str, str, int]] = []   # cap lines before the first snapshot of a call
rosters: dict[str, set[str]] = {}
call_ts = None
first_snapshot: date | None = None
for raw in (OUT / "rehome_merge_trace.log").read_text().splitlines():
    m = LINE.match(raw)
    if not m:
        continue
    d, t, msg = date.fromisoformat(m.group(1)), m.group(2), m.group(3)
    if (mi := R_INPUT.match(msg)):
        rosters = {x["name"]: set(x["tickers"]) for x in json.loads(mi.group(1))}
        call_ts = f"{d} {t}Z"
        first_snapshot = first_snapshot or d
        continue
    if first_snapshot is None:
        if (mc := R_CAP.match(msg)):
            not_replayable.append((d, mc.group(1), mc.group(2), int(mc.group(4))))
        continue
    if (mo := R_OVERLAP.match(msg)):
        src, dst = mo.group(1), mo.group(2)
        rosters.setdefault(dst, set()).update(rosters.pop(src, set()))
    elif (ms := R_STRIP.match(msg)):
        stripped = {s.strip().strip("'\"") for s in ms.group(1).split(",") if s.strip()}
        rosters.setdefault(ms.group(2), set()).difference_update(stripped)
    elif (ma := R_SMALL.match(msg)):
        src, dst = ma.group(1), ma.group(2)
        rosters.setdefault(dst, set()).update(rosters.pop(src, set()))
    elif (mc := R_CAP.match(msg)):
        src, dst, group, n = mc.group(1), mc.group(2), mc.group(3), int(mc.group(4))
        s_p2 = set(rosters.get(src, set()))
        g_p2 = set(rosters.get(dst, set()))
        assert len(s_p2) == n, f"{d} '{src}': replayed roster {len(s_p2)} != logged {n} — the replay is wrong"
        absorbs.append({"date": d, "call": call_ts, "source": src, "target": dst, "group": group,
                        "source_p2": sorted(s_p2), "target_p2": sorted(g_p2)})
        rosters.setdefault(dst, set()).update(s_p2)
        rosters.pop(src, None)

print(f"trace: {len(absorbs)} sector-cap absorb(s) replayed ({sum(len(a['source_p2']) for a in absorbs)} "
      f"member-moves) over {sorted({a['date'] for a in absorbs})[0]} … {sorted({a['date'] for a in absorbs})[-1]}; "
      f"{len(not_replayable)} cap line(s) from {min(x[0] for x in not_replayable) if not_replayable else '-'} … "
      f"{max(x[0] for x in not_replayable) if not_replayable else '-'} predate the first roster snapshot "
      f"({first_snapshot}) and cannot be replayed ({sum(x[3] for x in not_replayable)} logged member-moves)")

# ── arrivals, continuity, readings ──────────────────────────────────────────────────────────
rows: list[dict] = []
for a in absorbs:
    d = a["date"]
    g_p2 = set(a["target_p2"])
    prev = prev_board_date(d)
    prior = board[prev].get(a["target"], set()) | board[prev].get(name_on(a["target"], prev), set()) if prev else set()
    arrived = [t for t in a["source_p2"] if t not in g_p2 and t not in prior]
    for t in arrived:
        # continuity: in the target's roster (renamed as needed) on every board date D … BOARD
        path_ok, gap_on = True, None
        for bd in [x for x in BOARD_DATES if d <= x <= BOARD]:
            if t not in board[bd].get(name_on(a["target"], bd), set()):
                path_ok, gap_on = False, bd
                break
        corr_b, ov_b, bn_b, verdict_b = read(t, a["target_p2"], d)
        tgt_today = name_on(a["target"], BOARD)
        today_members = sorted(board[BOARD].get(tgt_today, set()))
        corr_t, _, _, verdict_t = read(t, today_members, BOARD) if today_members else (None, 0, 0, "n/a")
        rows.append({
            "date": d.isoformat(), "ticker": t, "source": a["source"], "target": a["target"],
            "target_today": tgt_today, "group": a["group"],
            "target_members_at_branch": len(a["target_p2"]),
            "corr_at_branch": "" if corr_b is None else f"{corr_b:.4f}", "overlap": ov_b, "basket_n": bn_b,
            "verdict_at_branch": verdict_b,
            "corr_today": "" if corr_t is None else f"{corr_t:.4f}", "verdict_today": verdict_t,
            "current": "yes" if path_ok else f"no (gone {gap_on})",
        })

fields = ["date", "ticker", "source", "target", "target_today", "group", "target_members_at_branch",
          "corr_at_branch", "overlap", "basket_n", "verdict_at_branch", "corr_today", "verdict_today", "current"]
out_path = OUT / f"rehome_sector_cap_{BOARD}.psv"
with open(out_path, "w") as fh:
    fh.write("|".join(fields) + "\n")
    for r in rows:
        fh.write("|".join(str(r[f]) for f in fields) + "\n")

current = [r for r in rows if r["current"] == "yes"]
rej = [r for r in current if r["verdict_at_branch"] == "reject"]
adm = [r for r in current if r["verdict_at_branch"] == "admit"]
unj = [r for r in current if r["verdict_at_branch"].startswith("unjudgeable")]
print(f"arrivals: {len(rows)} member-moves derived; {len(current)} CURRENT on the {BOARD} board "
      f"(continuous since arrival): the fixed code rejects {len(rej)} on the tape, admits {len(adm)}, "
      f"and sends {len(unj)} to the validator (tape cannot judge)")
print(f"written: {out_path.relative_to(ROOT)}")
print()
print("| arrived | ticker | from | into (today's name) | co-movement at the branch | fixed code | today vs today's roster |")
print("|---|---|---|---|---|---|---|")
for r in sorted(current, key=lambda r: (r["target_today"], r["date"], r["ticker"])):
    into = r["target"] if r["target"] == r["target_today"] else f"{r['target']} → {r['target_today']}"
    rd = r["corr_at_branch"] or r["verdict_at_branch"].split(":", 1)[1]
    fixed = {"reject": "REJECT (not moved)", "admit": "admit"}.get(r["verdict_at_branch"], "validator decides")
    print(f"| {r['date']} | {r['ticker']} | {r['source']} | {into} | {rd} (basket {r['basket_n']}) | {fixed} | {r['corr_today'] or r['verdict_today']} |")
gone = [r for r in rows if r["current"] != "yes"]
print()
print(f"not current (arrived by this path, since left — {len(gone)}): "
      + ", ".join(f"{r['ticker']}→{r['target']} ({r['date']}, {r['current']})" for r in sorted(gone, key=lambda r: (r['date'], r['ticker']))))
