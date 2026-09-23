"""Assignment-gate co-movement backtest — stage 2 of 2: the REPLAY (2026-09-13, $0, offline).

Replays every (stock, theme) pair the assignment LLM proposed over the last 60 trading days
through the LIVE membership test — `theme_engine._comove_verdict` on a `ComoveContext` built with
`ep_theme_belonging`'s own functions — and compares the verdict with what the sector-identity test
actually did that night (the audit trail: `assignment_llm_proposed` = every proposal,
`assignment_skipped_sector_outlier` = every sector rejection). Not a lookalike: the same function
the engine will run.

Reads the five CSVs `_assign_comove_pull.sh` wrote. Writes <dir>/results.md and prints it.

    bash scripts/probes/_assign_comove_pull.sh /tmp/acm
    python scripts/probes/_assign_comove_backtest.py /tmp/acm

NO LOOKAHEAD: each pair is judged on the sessions strictly before ITS run date, against the
theme's members as they stood on the PRIOR night's board (the engine writes tonight's row after
assignment, so the prior row is what assignment saw, minus that night's carryforward strip).
"""
from __future__ import annotations

import ast
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, ".")
from agents.market_intelligence import ep_theme_belonging as etb  # noqa: E402
from agents.market_intelligence import theme_engine as te  # noqa: E402

D = sys.argv[1].rstrip("/") + "/"
BAR = te.ASSIGN_COMOVE_BAR
LOOKBACK = etb.BELONGING_LOOKBACK_SESSIONS
WINDOW_SESSIONS = 60
PAYING = set(etb.THEME_BONUS_STAGES)
RNG = np.random.default_rng(20260913)
N_CONTROL_DRAWS = 300


def d(s: str) -> date:
    return date.fromisoformat(s)


# ── load ──────────────────────────────────────────────────────────────────────────────────────
closes: dict[str, dict[date, float]] = defaultdict(dict)
for r in csv.DictReader(open(D + "closes.csv")):
    closes[r["ticker"]][d(r["trade_date"])] = float(r["close"])

themes_rows = list(csv.DictReader(open(D + "themes.csv")))
board: dict[date, dict[str, dict]] = defaultdict(dict)   # theme_date -> name -> row
for r in themes_rows:
    tk = [t.strip().strip('"') for t in r["tickers"].strip("{}").split(",") if t.strip()]
    board[d(r["theme_date"])][r["name"]] = {"stage": r["stage"], "tickers": [t.upper() for t in tk]}

sector_of: dict[str, str] = {}
for r in csv.DictReader(open(D + "sectors.csv")):
    # scores row wins (the engine's stocks_by_ticker comes from mi_stock_scores); overrides fill gaps
    if r["src"] == "scores" or r["ticker"] not in sector_of:
        sector_of[r["ticker"]] = r["sector"]

controls_by_sector: dict[str, list[str]] = defaultdict(list)
for r in csv.DictReader(open(D + "controls.csv")):
    controls_by_sector[r["sector"]].append(r["ticker"])

events = list(csv.DictReader(open(D + "events.csv")))

# ── the replay window: the last 60 SPY sessions ending on the last run date ─────────────────
run_dates_all = sorted({d(r["run_date"]) for r in events})
last_run = run_dates_all[-1]
spy_sessions = sorted(dd for dd in closes["SPY"] if dd <= last_run)
window_start = spy_sessions[-WINDOW_SESSIONS]
run_dates = [x for x in run_dates_all if x >= window_start]


def prior_board(run_date: date) -> dict[str, dict]:
    """The board assignment saw on `run_date`: latest row per name with theme_date < run_date
    within 8 days, Retired dropped — the mirror of get_active_themes(stale_after_days=7) at 17:00."""
    out: dict[str, dict] = {}
    for dd in sorted(board):
        if dd >= run_date or dd < run_date - timedelta(days=8):
            continue
        for name, row in board[dd].items():
            out[name] = row  # later dates overwrite
    return {n: r for n, r in out.items() if r["stage"] != "Retired"}


# ── contexts, one per run date, via the LIVE builders ───────────────────────────────────────
_ctx_cache: dict[date, te.ComoveContext | None] = {}


def ctx_for(before: date) -> te.ComoveContext | None:
    if before in _ctx_cache:
        return _ctx_cache[before]
    cs = etb.session_index(closes["SPY"], before, LOOKBACK)
    if len(cs) < 2:
        _ctx_cache[before] = None
        return None
    mkt = etb.log_returns(closes["SPY"], cs)
    ex = etb.excess_returns(closes, cs, mkt)
    _ctx_cache[before] = te.ComoveContext(before_date=before, excess=ex, n_sessions=len(cs) - 1,
                                          n_rows=0)
    return _ctx_cache[before]


# ── the proposal population ─────────────────────────────────────────────────────────────────
proposals: list[dict] = []        # one per (run_date, ticker, theme)
sector_rejected: set[tuple[date, str, str]] = set()
other_skips: Counter = Counter()
for r in events:
    rd = d(r["run_date"])
    if rd < window_start:
        continue
    et = r["event_type"]
    if et == "assignment_llm_proposed":
        det = json.loads(r["detail"])
        for p in det.get("proposals", []):
            proposals.append({"run_date": rd, "ticker": (p.get("ticker") or "").upper(),
                              "theme": te._strip_stage_label(p.get("theme") or "")})
    elif et == "assignment_skipped_sector_outlier":
        det = json.loads(r["detail"])
        sector_rejected.add((rd, det["ticker"].upper(), te._strip_stage_label(det["theme"])))
    elif et.startswith("assignment_skipped") or et in ("cooldown_blocked_assignment",
                                                      "assignment_theme_not_found"):
        other_skips[et] += 1

# dedupe (a proposal echoed twice in one night is one decision)
seen = set()
uniq = []
for p in proposals:
    k = (p["run_date"], p["ticker"], p["theme"])
    if k not in seen:
        seen.add(k)
        uniq.append(p)
proposals = uniq

# ── what assignment SAW each night: the prior row, minus that night's carryforward strip, plus
#    the pairs admitted EARLIER in the same run (the apply-loop appends to theme["tickers"] as it
#    goes, so a later proposal to the same theme sees the earlier admit — IREN on 09-08 was judged
#    against CIFR/CORZ/BTDR because BTDR's proposal came first) ──────────────────────────────────
stripped_tonight: dict[tuple[date, str], set[str]] = defaultdict(set)
for r in events:
    if r["event_type"] != "theme_carryforward_filter_stripped":
        continue
    det = r["detail"]
    m_th = re.search(r"theme=(.*)\n", det)
    if not m_th:
        continue
    for m in re.finditer(r"(?:banned|cooldown|sector_outlier)=(\[.*?\])", det):
        stripped_tonight[(d(r["run_date"]), m_th.group(1).strip())].update(
            t.upper() for t in ast.literal_eval(m.group(1)))

# ── judge every pair with the LIVE function, the way the NEW engine would run the night ──────
#    basket = prior row − that night's carryforward strip (sector-era, as recorded) + the pairs the
#    NEW rule admitted earlier in the run. Pass 1 in proposal order; pairs thin for want of members
#    are deferred to pass 2, ordered sector-admit first (the engine's own rule), where a still-thin
#    pair takes the sector test — its recorded historical verdict.
rows: list[dict] = []
by_night: dict[date, list[dict]] = defaultdict(list)
for p in proposals:
    by_night[p["run_date"]].append(p)


def _judge(p: dict, members: list[str] | None, ctx) -> dict:
    rd, tk, th = p["run_date"], p["ticker"], p["theme"]
    sector_says = "reject" if (rd, tk, th) in sector_rejected else "admit"
    cv = te._comove_verdict(tk, members, ctx) if members is not None else None
    if members is None:
        new = "no_prior_row"
    elif cv is None or cv.admit is None:
        new = f"unjudgeable:{cv.reason if cv else 'no_ctx'}"
    else:
        new = "admit" if cv.admit else "reject"
    return {"run_date": rd, "ticker": tk, "theme": th, "sector": sector_says, "new": new,
            "corr": cv.corr if cv else None, "overlap": cv.overlap if cv else 0,
            "basket_n": cv.basket_n if cv else 0, "members_n": len(members or []),
            "stage": None, "on_board_tonight": tk in (board.get(rd, {}).get(th, {}).get("tickers") or []),
            "stock_sector": sector_of.get(tk, "Unknown"), "pass": 1}


for rd in sorted(by_night):
    pb = prior_board(rd)
    ctx = ctx_for(rd)
    new_members: dict[str, list[str] | None] = {}
    deferred: list[dict] = []
    for p in by_night[rd]:
        th = p["theme"]
        if th not in new_members:
            new_members[th] = ([m for m in pb[th]["tickers"] if m not in stripped_tonight.get((rd, th), set())]
                               if th in pb else None)
        r = _judge(p, new_members[th], ctx)
        r["stage"] = pb.get(th, {}).get("stage")
        if r["new"] == "unjudgeable:thin_basket":
            deferred.append((p, r))
            continue
        # a pair the tape cannot judge takes the sector verdict — its recorded one
        landed = r["new"] == "admit" or (r["new"] not in ("admit", "reject") and r["sector"] == "admit")
        if landed and new_members[th] is not None and p["ticker"] not in new_members[th]:
            new_members[th].append(p["ticker"])
        rows.append(r)
    _rank = {"admit": 0, "reject": 1}
    for p, r1 in sorted(deferred, key=lambda x: _rank[x[1]["sector"]]):
        th = p["theme"]
        r = _judge(p, new_members[th], ctx)
        r["stage"] = r1["stage"]
        r["pass"] = 2
        landed = r["new"] == "admit" or (r["new"] not in ("admit", "reject") and r["sector"] == "admit")
        if landed and new_members[th] is not None and p["ticker"] not in new_members[th]:
            new_members[th].append(p["ticker"])
        rows.append(r)

judged = [r for r in rows if r["new"] in ("admit", "reject")]
conf = Counter((r["sector"], r["new"]) for r in rows)
unjudg = Counter(r["new"] for r in rows if r["new"] not in ("admit", "reject"))

# ── the board on the last run date, and what returns ───────────────────────────────────────
final_board = {n: r for n, r in board[last_run].items() if r["stage"] != "Retired"}
final_active = prior_board(last_run + timedelta(days=1))  # 7-day-active mirror incl. last_run
ctx_final = ctx_for(last_run + timedelta(days=1))          # sessions <= last_run


def tightness(members: list[str], ctx: te.ComoveContext) -> float | None:
    """Mean leave-one-out co-movement of each member with the rest (only members the tape can
    judge); None when fewer than 3 members have history."""
    vals = []
    for m in members:
        cv = te._comove_verdict(m, members, ctx)
        if cv is not None and cv.corr is not None:
            vals.append(cv.corr)
    return float(np.mean(vals)) if len(vals) >= 3 else None


# expected returning set (the analysis's "26"): sector-rejected pairs in the window whose theme is
# live on the final board and whose ticker is not a member there
returning_candidates: dict[tuple[str, str], list[date]] = defaultdict(list)
for (rd, tk, th) in sector_rejected:
    if th in final_active and tk not in final_active[th]["tickers"]:
        returning_candidates[(tk, th)].append(rd)

returning: list[dict] = []
for (tk, th), dates in sorted(returning_candidates.items()):
    members = final_active[th]["tickers"]
    cv = te._comove_verdict(tk, members, ctx_final)
    verdict = ("admit" if cv.admit else "reject") if (cv and cv.admit is not None) else \
        f"unjudgeable:{cv.reason if cv else 'no_ctx'}"
    returning.append({"ticker": tk, "theme": th, "stage": final_active[th]["stage"],
                      "members_n": len(members), "corr": cv.corr if cv else None,
                      "verdict": verdict, "nights": len(dates), "last": max(dates)})
returns_admitted = [r for r in returning if r["verdict"] == "admit"]

# would-have-been-rejected members: sector-admitted, new-test-rejected pairs whose ticker sits in
# that theme on the final board
would_reject: dict[str, set[str]] = defaultdict(set)
for r in judged:
    if r["sector"] == "admit" and r["new"] == "reject":
        th = r["theme"]
        if th in final_active and r["ticker"] in final_active[th]["tickers"]:
            would_reject[th].add(r["ticker"])

# sizes + <=5 share, before / after
def size_stats(bd: dict[str, dict]) -> tuple[int, float, int, int]:
    sizes = [len(r["tickers"]) for r in bd.values()]
    n = len(sizes)
    return n, (float(np.mean(sizes)) if n else 0.0), sum(1 for x in sizes if x <= 5), sum(1 for x in sizes if x < 3)


after_add = {n: {**r, "tickers": list(r["tickers"])} for n, r in final_active.items()}
for r in returns_admitted:
    after_add[r["theme"]]["tickers"].append(r["ticker"])
after_both = {n: {**r, "tickers": [t for t in r["tickers"] if t not in would_reject.get(n, set())]}
              for n, r in after_add.items()}

# tightness before/after with the matched control
tight_rows = []
changed = sorted({r["theme"] for r in returns_admitted})
for th in changed:
    before_m = final_active[th]["tickers"]
    adds = [r["ticker"] for r in returns_admitted if r["theme"] == th]
    after_m = before_m + adds
    tb, ta = tightness(before_m, ctx_final), tightness(after_m, ctx_final)
    # control: swap each returning name for a random assignment-eligible name from a sector the
    # theme ALREADY accepts (the analysis's control design), 300 draws
    accepted_sectors = {sector_of.get(m) for m in before_m} - {None, "Unknown"}
    pool = sorted({c for s in accepted_sectors for c in controls_by_sector.get(s, [])
                   if c in ctx_final.excess and c not in after_m})
    ctrl_vals = []
    if pool:
        for _ in range(N_CONTROL_DRAWS):
            draw = list(RNG.choice(pool, size=min(len(adds), len(pool)), replace=False))
            tc = tightness(before_m + draw, ctx_final)
            if tc is not None:
                ctrl_vals.append(tc)
    tight_rows.append({"theme": th, "stage": final_active[th]["stage"], "adds": adds,
                       "before": tb, "after": ta,
                       "ctrl_mean": float(np.mean(ctrl_vals)) if ctrl_vals else None,
                       "ctrl_beats_real": (sum(1 for v in ctrl_vals if ta is not None and v > ta)
                                           if ctrl_vals else None),
                       "ctrl_n": len(ctrl_vals)})

# U1 exposure: boosted stock count before/after
boosted_before = {t for r in final_active.values() if r["stage"] in PAYING for t in r["tickers"]}
boosted_after = {t for r in after_add.values() if r["stage"] in PAYING for t in r["tickers"]}

# ── P2: strips that left a theme under 3 — before vs re-judged ─────────────────────────────
strip_events = []
for r in events:
    if r["event_type"] != "theme_carryforward_filter_stripped":
        continue
    rd = d(r["run_date"])
    if rd < window_start:
        continue
    det = r["detail"]
    m_pre = re.search(r"pre_size=(\d+) post_size=(\d+)", det)
    m_so = re.search(r"sector_outlier=(\[.*?\])", det)
    m_th = re.search(r"theme=(.*)\n", det)
    if not (m_pre and m_so and m_th):
        continue
    pre, post = int(m_pre.group(1)), int(m_pre.group(2))
    stripped = [t.upper() for t in ast.literal_eval(m_so.group(1))]
    th = m_th.group(1).strip()
    pb = prior_board(rd)
    members = pb.get(th, {}).get("tickers") or []
    kept = []
    for t in stripped:
        cv = te._comove_verdict(t, members, ctx_for(rd)) if members else None
        if cv is not None and cv.admit is True:
            kept.append((t, cv.corr))
    n_other = pre - post - len(stripped)   # banned/cooldown strips in the same event
    post_new = post + len(kept)
    strip_events.append({"run_date": rd, "theme": th, "pre": pre, "post": post, "stripped": stripped,
                         "kept": kept, "post_new": post_new, "members_seen": len(members),
                         "n_other": n_other})
under3_before = sum(1 for e in strip_events if e["post"] < 3)
under3_after = sum(1 for e in strip_events if e["post_new"] < 3)

# ── the named checks ────────────────────────────────────────────────────────────────────────
NAMED = {"IREN": "admit", "MSTR": "admit", "CMC": "admit", "GPN": "admit",
         "OTTR": "reject", "ECO": "reject", "SEDG": "reject", "AGX": "reject"}
named_rows = [r for r in rows if r["ticker"] in NAMED and r["sector"] == "reject"]

# ── report ──────────────────────────────────────────────────────────────────────────────────
L: list[str] = []
P = L.append
P(f"# Assignment-gate replay: sector-identity test vs co-movement at {BAR} — {last_run}")
P("")
P(f"Window: the last {WINDOW_SESSIONS} SPY sessions ({window_start} → {last_run}), "
  f"{len(run_dates)} nightly runs with proposals. Every pair judged by the LIVE "
  f"`theme_engine._comove_verdict` (leave-one-out, SPY-subtracted, {LOOKBACK} sessions strictly "
  f"before the run date, basket >= {etb.BELONGING_MIN_BASKET_MEMBERS} members with history, "
  f">= {etb.BELONGING_MIN_OVERLAP_SESSIONS} overlapping sessions).")
P("")
P("## 1. Denominators")
P("")
P("| population | n |")
P("|---|---|")
P(f"| proposals the LLM made (unique stock↔theme pairs per night) | {len(rows)} |")
P(f"| … rejected by the sector-identity test that night | {sum(1 for r in rows if r['sector']=='reject')} |")
P(f"| … admitted by the sector test (no skip event of any kind) | {sum(1 for r in rows if r['sector']=='admit')} |")
P(f"| … of the sector-admitted, on the theme's board that same night (survived validation) | "
  f"{sum(1 for r in rows if r['sector']=='admit' and r['on_board_tonight'])} |")
P(f"| other skip events in the window (exclusion / cooldown / kw / desc / not-found) | {sum(other_skips.values())} {dict(other_skips) if other_skips else ''} |")
P(f"| pairs the tape could judge | {len(judged)} |")
P(f"| pairs it could NOT judge → sector test decides (fail-safe) | {sum(unjudg.values())} {dict(unjudg)} |")
P("")
P("## 2. Sector test vs co-movement test — the confusion table (judgeable pairs)")
P("")
P("| sector test said | co-movement admits | co-movement rejects | total |")
P("|---|---|---|---|")
for sv in ("admit", "reject"):
    a, rj = conf[(sv, "admit")], conf[(sv, "reject")]
    P(f"| {sv} | {a} | {rj} | {a + rj} |")
adm_over = conf[("reject", "admit")]
rej_new = conf[("admit", "reject")]
n_srej = conf[("reject", "admit")] + conf[("reject", "reject")]
n_sadm = conf[("admit", "admit")] + conf[("admit", "reject")]
P("")
P(f"- **Admitted now, sector rejected**: {adm_over} of {n_srej} judgeable sector-rejections "
  f"({100*adm_over/max(n_srej,1):.0f}%).")
P(f"- **Rejected now, sector admitted**: {rej_new} of {n_sadm} judgeable sector-admissions "
  f"({100*rej_new/max(n_sadm,1):.0f}%).")
corr_adm = [r["corr"] for r in judged if r["sector"] == "admit"]
corr_rej = [r["corr"] for r in judged if r["sector"] == "reject"]
P(f"- Mean co-movement of sector-ADMITTED pairs {np.mean(corr_adm):.2f} (n={len(corr_adm)}) vs "
  f"sector-REJECTED pairs {np.mean(corr_rej):.2f} (n={len(corr_rej)}) — the analysis measured 0.65 vs 0.61.")
P("")
P("### Newly rejected, sector-admitted pairs (the bucket he has not seen)")
P("")
P("| night | stock | theme | corr | overlap | basket | on board that night? |")
P("|---|---|---|---|---|---|---|")
for r in sorted(judged, key=lambda r: (r["run_date"], r["ticker"])):
    if r["sector"] == "admit" and r["new"] == "reject":
        P(f"| {r['run_date']} | {r['ticker']} | {r['theme'][:55]} | {r['corr']:.2f} | {r['overlap']} | {r['basket_n']} | {'yes' if r['on_board_tonight'] else 'no'} |")
P("")
P("## 3. IREN — the headline case")
P("")
for r in rows:
    if r["ticker"] == "IREN":
        P(f"- {r['run_date']}: IREN → '{r['theme']}' — sector test **{r['sector']}ed**; "
          f"co-movement **{r['new']}** at corr={r['corr']} over {r['overlap']} sessions against "
          f"{r['basket_n']} members (theme had {r['members_n']} members that night, stage {r['stage']}).")
if not any(r["ticker"] == "IREN" for r in rows):
    P("- IREN was not proposed in the window.")
P("")
P("## 4. The named checks from the analysis (0.35 separates every case measured)")
P("")
P("| stock | expected | night | theme | corr | verdict |")
P("|---|---|---|---|---|---|")
for r in sorted(named_rows, key=lambda r: (r["ticker"], r["run_date"])):
    ok = "✓" if r["new"] == NAMED[r["ticker"]] else ("—" if r["new"] not in ("admit", "reject") else "✗")
    P(f"| {r['ticker']} | {NAMED[r['ticker']]} | {r['run_date']} | {r['theme'][:50]} | {r['corr']} | {r['new']} {ok} |")
missing = sorted(set(NAMED) - {r["ticker"] for r in named_rows})
if missing:
    P(f"\n(not sector-rejected inside the window: {missing})")
P("")
P("## 5. Board effect on the last board (returning names)")
P("")
n_b, mean_b, le5_b, lt3_b = size_stats(final_active)
n_a, mean_a, le5_a, lt3_a = size_stats(after_add)
n_c, mean_c, le5_c, lt3_c = size_stats(after_both)
P(f"- Expected-returning set reconstructed: **{len(returning)}** names blocked on sector during the window "
  f"whose theme is live on {last_run} and who are not members (the analysis expected ~26 under rule-OFF).")
P(f"- Of those, **{len(returns_admitted)} clear {BAR}** and return; "
  f"{sum(1 for r in returning if r['verdict']=='reject')} are below the bar; "
  f"{sum(1 for r in returning if r['verdict'].startswith('unjudgeable'))} unjudgeable (stay out — sector test).")
P("")
P("| board | themes | mean members | ≤5 members | <3 members |")
P("|---|---|---|---|---|")
P(f"| today ({last_run}, 7-day active) | {n_b} | {mean_b:.2f} | {le5_b} ({100*le5_b/max(n_b,1):.0f}%) | {lt3_b} |")
P(f"| + returning names admitted at {BAR} | {n_a} | {mean_a:.2f} | {le5_a} ({100*le5_a/max(n_a,1):.0f}%) | {lt3_a} |")
P(f"| + returning − members the new test would have refused at assignment | {n_c} | {mean_c:.2f} | {le5_c} ({100*le5_c/max(n_c,1):.0f}%) | {lt3_c} |")
P("")
P("### Returning names, one row each")
P("")
P("| stock | theme | stage | members | corr | verdict | nights blocked |")
P("|---|---|---|---|---|---|---|")
for r in sorted(returning, key=lambda r: (r["verdict"], -(r["corr"] or -9))):
    P(f"| {r['ticker']} | {r['theme'][:55]} | {r['stage']} | {r['members_n']} | {r['corr']} | {r['verdict']} | {r['nights']} (last {r['last']}) |")
P("")
P("## 6. Theme tightness before vs after, with the matched random-name control")
P("")
P(f"Tightness = mean leave-one-out co-movement of each member with the rest ({LOOKBACK} sessions to "
  f"{last_run}). Control = the same theme with each returning name replaced by a random "
  f"assignment-eligible stock from a sector the theme already accepts, {N_CONTROL_DRAWS} draws.")
P("")
P("| theme | stage | adds | before | after | control mean | control beats real (of draws) |")
P("|---|---|---|---|---|---|---|")
tighter = looser = 0
for t in tight_rows:
    if t["before"] is not None and t["after"] is not None:
        tighter += t["after"] >= t["before"]
        looser += t["after"] < t["before"]
    fb = f"{t['before']:.2f}" if t["before"] is not None else "n/a"
    fa = f"{t['after']:.2f}" if t["after"] is not None else "n/a"
    fc = f"{t['ctrl_mean']:.2f}" if t["ctrl_mean"] is not None else "n/a"
    fcb = f"{t['ctrl_beats_real']}/{t['ctrl_n']}" if t["ctrl_beats_real"] is not None else "n/a"
    P(f"| {t['theme'][:50]} | {t['stage']} | {', '.join(t['adds'])} | {fb} | {fa} | {fc} | {fcb} |")
b_all = [t["before"] for t in tight_rows if t["before"] is not None and t["after"] is not None]
a_all = [t["after"] for t in tight_rows if t["before"] is not None and t["after"] is not None]
c_all = [t["ctrl_mean"] for t in tight_rows if t["before"] is not None and t["after"] is not None and t["ctrl_mean"] is not None]
P("")
if b_all:
    P(f"- Across the {len(b_all)} changed themes: mean tightness **{np.mean(b_all):.2f} → {np.mean(a_all):.2f}** "
      f"({tighter} tighter, {looser} looser); the random same-sector control lands at "
      f"**{np.mean(c_all):.2f}**." if c_all else f"- mean tightness {np.mean(b_all):.2f} → {np.mean(a_all):.2f}.")
P("")
P("## 7. Money-path exposure (U1) — stocks carrying the +10 theme bonus")
P("")
P(f"- Distinct stocks in Accelerating/Mainstream themes today: **{len(boosted_before)}**; after the returning "
  f"names: **{len(boosted_after)}** (+{len(boosted_after) - len(boosted_before)}). Baseline in the "
  f"pre-registration: 178 → ~183.")
paying_adds = [r for r in returns_admitted if r["stage"] in PAYING]
if paying_adds:
    P("- Returning names that land in a paying theme: " +
      ", ".join(f"{r['ticker']}→'{r['theme'][:40]}' ({r['stage']})" for r in paying_adds))
P("")
P("## 8. Starvation (P2) — nightly strips that left a theme under 3 members")
P("")
P(f"- Sector-outlier strip events in the window: **{len(strip_events)}**; left the theme under 3: "
  f"**{under3_before}** before → **{under3_after}** with the singleton re-judged by the tape "
  f"(kept when it co-moves ≥ {BAR} with the rest, leave-one-out).")
kept_total = sum(len(e["kept"]) for e in strip_events)
strip_total = sum(len(e["stripped"]) for e in strip_events)
P(f"- Singleton-sector members stripped: {strip_total}; the tape would have kept **{kept_total}** of them.")
P("")
P("| night | theme | pre | post | stripped | kept by tape | post (new) |")
P("|---|---|---|---|---|---|---|")
for e in sorted(strip_events, key=lambda e: e["run_date"]):
    P(f"| {e['run_date']} | {e['theme'][:45]} | {e['pre']} | {e['post']} | {', '.join(e['stripped'])} | "
      f"{', '.join(f'{t} ({c:.2f})' for t, c in e['kept']) or '—'} | {e['post_new']} |")
P("")
P("## 9. Against the pre-registration, row by row")
P("")
P("| row | expectation / risk | this replay reads |")
P("|---|---|---|")
P(f"| P1 themes hold more members | avg 4.7 at birth → 6.3 peak; 83 of 119 ≤5 | add-backs alone: mean members {mean_b:.2f} → {mean_a:.2f}, "
  f"≤5 share {100*le5_b/max(n_b,1):.0f}% → {100*le5_a/max(n_a,1):.0f}%; add-backs MINUS the members the tape would have refused at assignment: "
  f"{mean_c:.2f}, {100*le5_c/max(n_c,1):.0f}% — one night on the {last_run} board. **P1 may REFUTE under the symmetric bar**: "
  f"{rej_new} refusals vs {adm_over} admits over the window means the member count is more likely to fall than rise over weeks; "
  f"narrowing the tape to cross-sector pairs only would remove that risk — his call |")
P(f"| P2 fewer themes starved under 3 | 29 of 46 strips left a theme under 3 | {under3_before} of {len(strip_events)} → {under3_after} of {len(strip_events)} in this window |")
iren_rows = [r for r in rows if r["ticker"] == "IREN"]
P(f"| P3 his four concepts formable | IREN blocked from the theme named after it | "
  + ("; ".join(f"IREN {r['new']} at {r['corr']} on {r['run_date']}" for r in iren_rows) or "IREN not proposed in window")
  + " — formation itself needs the live run (the theme is Retired today) |")
P(f"| P4 membership rejections fall | 167 of 824 (20%) rejected on sector | sector rejections {n_srej + unjudg.get('unjudgeable:no_history',0)*0} → "
  f"{conf[('reject','reject')]} of the judgeable ones stay rejected on the tape ({rej_new} sector-admitted pairs newly rejected); "
  f"unjudgeable pairs ({sum(unjudg.values())}) keep the sector verdict |")
P(f"| U1 EP score moves | 178 boosted stocks, 4 bonus-dependent HIGHs / 90d | boosted stocks {len(boosted_before)} → {len(boosted_after)} on this board |")
P(f"| U2 tightness falls | ~1 in 7 readmitted is junk | " +
  (f"mean tightness {np.mean(b_all):.2f} → {np.mean(a_all):.2f} across changed themes; control {np.mean(c_all):.2f}" if b_all and c_all else "no changed theme measurable") +
  f"; {sum(1 for r in returning if r['verdict']=='reject')} of {len(returning)} blocked names are refused by the bar |")
P(f"| U3 volume overshoots ~26 | assignment LLM never told cross-sector is allowed | {len(returns_admitted)} return on this board (of {len(returning)} candidates); "
  f"the prompt has NO sector rule (checked: 'Only assign if the business CLEARLY matches the thesis'), so a drift beyond this needs the live weeks |")
P("| U4 names get vaguer | rename / mass-removal events | not measurable offline — live tripwire |")
P(f"| U5 nothing changes (batching binds) | P1–P4 flat | {adm_over} of {n_srej} sector-rejected pairs flip to admit on the historical nights — the gate WAS binding for those |")
P("")

out = "\n".join(L)
open(D + "results.md", "w").write(out)
# raw per-pair rows for anyone re-reading the evidence
with open(D + "pairs.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(out)
