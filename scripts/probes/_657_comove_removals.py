"""#657 — should the tape decide REMOVALS too? Stage 2 of 2: the offline replay (2026-09-25, $0).

Judges every current theme membership with the LIVE membership test — `theme_engine._comove_verdict`
on a `ComoveContext` built with `market_adjusted_correlation`'s own primitives (the functions
`_load_comove_context` calls) — and reports what a removal rule at `ASSIGN_COMOVE_BAR` would do:
the eviction list, what happened to each name OUT OF SAMPLE (co-movement, not returns), theme
tightness before/after against a matched random-removal control, and the overlap with the strips
the engine already runs. Not a lookalike: the same function the engine runs at assignment.

Reads the seven CSVs `_657_pull.sh` wrote. Writes <dir>/results.md, <dir>/*.psv, <dir>/summary.json.

    bash scripts/probes/_657_pull.sh scripts/probes/_657_out
    python scripts/probes/_657_comove_removals.py scripts/probes/_657_out

Method (declared in docs/analysis/657_comove_removals_2026-09-25.md BEFORE this ran): two shapes of
"job 2 on the tape" (A = as built, singleton-sector members only; B = every member below the bar);
two out-of-sample windows, both derived from the SPY session index (W1 = after the 09-11 board,
9 returns; W2 = the first close of session_index(SPY, 2026-09-25, 30) = 2026-08-12, 30 returns);
tightness = mean leave-one-out co-movement (the 09-13 doc's metric — no engine metric exists);
control = the same number of random removals, 300 draws, seed 20260925. NO LOOKAHEAD: every
in-sample verdict uses sessions strictly before its context date, against the board as it stood.
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
from agents.market_intelligence import market_adjusted_correlation as mac  # noqa: E402
from agents.market_intelligence import theme_engine as te  # noqa: E402
from agents.market_intelligence import ep_theme_belonging as etb  # noqa: E402

D = (sys.argv[1] if len(sys.argv) > 1 else "scripts/probes/_657_out").rstrip("/") + "/"
BAR = te.ASSIGN_COMOVE_BAR
LOOKBACK = mac.BELONGING_LOOKBACK_SESSIONS
PAYING = set(etb.THEME_BONUS_STAGES)
PRUNE_MIN = te.PRUNE_MIN_TICKERS
TODAY_CTX = date(2026, 9, 25)          # context date -> sessions strictly before = through 09-24
BOARD_TODAY = date(2026, 9, 24)
W1_BOARD = date(2026, 9, 11)           # the 09-13 backtest's board
W2_RETURNS = 30                        # the engine's own minimum overlap
N_DRAWS = 300
RNG = np.random.default_rng(20260925)
BACKTEST_DOC = "docs/analysis/assignment_comove_backtest_2026-09-13.md"


def d(s: str) -> date:
    return date.fromisoformat(s)


def f2(x) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def pct(a: int, b: int) -> str:
    return f"{a} of {b} ({100 * a / b:.0f}%)" if b else f"{a} of 0"


# ── load ──────────────────────────────────────────────────────────────────────────────────────
closes: dict[str, dict[date, float]] = defaultdict(dict)
for r in csv.DictReader(open(D + "closes.csv")):
    closes[r["ticker"].upper()][d(r["trade_date"])] = float(r["close"])
SPY = closes[mac.MARKET_TICKER]

board: dict[date, dict[str, dict]] = defaultdict(dict)   # theme_date -> name -> row
for r in csv.DictReader(open(D + "themes.csv")):
    tk = [t.strip().strip('"').upper() for t in r["tickers"].strip("{}").split(",") if t.strip()]
    board[d(r["theme_date"])][r["name"]] = {"stage": r["stage"], "tickers": tk}
ALL_DATES = sorted(board)

sector_of: dict[str, str] = {}
for r in csv.DictReader(open(D + "sectors.csv")):
    if r["src"] == "scores" or r["ticker"] not in sector_of:   # scores wins; overrides fill gaps
        sector_of[r["ticker"].upper()] = r["sector"]

events = list(csv.DictReader(open(D + "events.csv")))
try:   # the merge-machinery events (absorption / birth-gate joins / successor pointers), pulled 2026-09-25
    events += list(csv.DictReader(open(D + "events_extra.csv")))
except FileNotFoundError:
    pass
for e in events:
    e["run_date"] = d(e["run_date"])

bypassed_pairs: set[tuple[str, str]] = set()
for r in csv.DictReader(open(D + "cooldowns.csv")):
    if r["bypassed"] in ("t", "true", "True"):
        bypassed_pairs.add((r["ticker"].upper(), r["theme_name"]))

renames: list[tuple[str, str]] = [(r["old_name"], r["new_name"]) for r in csv.DictReader(open(D + "renames.csv"))]
for e in events:
    if e["event_type"] == "theme_renamed_for_continuity":
        for m in re.finditer(r"'(.+?)' → '(.+?)' \(canonical", e["detail"]):
            renames.append((m.group(1), m.group(2)))
    elif e["event_type"] == "theme_renamed_on_mass_flag":
        m = re.match(r"'(.+?)' renamed to '(.+?)' —", e["summary"])
        if m:
            renames.append((m.group(1), m.group(2)))

# theme identity = union-find over rename lineage
_parent: dict[str, str] = {}


def find(n: str) -> str:
    _parent.setdefault(n, n)
    while _parent[n] != n:
        _parent[n] = _parent[_parent[n]]
        n = _parent[n]
    return n


def union(a: str, b: str) -> None:
    ra, rb = find(a), find(b)
    if ra != rb:
        _parent[ra] = rb


for a, b in renames:
    union(a, b)
for dd in board:
    for n in board[dd]:
        find(n)


def aliases(name: str) -> set[str]:
    root = find(name)
    return {n for n in _parent if find(n) == root}


# ── boards ──────────────────────────────────────────────────────────────────────────────────
def active_board(asof: date, days: int = 7) -> dict[str, dict]:
    """The 7-day mirror of get_active_themes: latest row per name in (asof-7, asof], Retired dropped."""
    out: dict[str, dict] = {}
    for dd in ALL_DATES:
        if dd > asof or dd <= asof - timedelta(days=days):
            continue
        for name, row in board[dd].items():
            out[name] = {**row, "date": dd}
    return {n: r for n, r in out.items() if r["stage"] != "Retired"}


def identity_rows(name: str) -> dict[date, set[str]]:
    """Every board date on which this theme identity (any alias) had a row -> the union of tickers."""
    out: dict[date, set[str]] = defaultdict(set)
    for al in aliases(name):
        for dd in ALL_DATES:
            row = board[dd].get(al)
            if row is not None:
                out[dd].update(row["tickers"])
    return out


# ── contexts via the LIVE builders ──────────────────────────────────────────────────────────
_ctx_cache: dict[date, te.ComoveContext | None] = {}


def ctx_for(before: date) -> te.ComoveContext | None:
    if before in _ctx_cache:
        return _ctx_cache[before]
    cs = mac.session_index(SPY, before, LOOKBACK)
    if len(cs) < 2:
        _ctx_cache[before] = None
        return None
    mkt = mac.log_returns(SPY, cs)
    ex = mac.excess_returns(closes, cs, mkt)
    _ctx_cache[before] = te.ComoveContext(before_date=before, excess=ex, n_sessions=len(cs) - 1, n_rows=0)
    return _ctx_cache[before]


def oos_excess(base_close: date, n_returns: int) -> tuple[dict[str, np.ndarray], list[date]]:
    """Excess returns over the n_returns SPY sessions strictly AFTER base_close (same maths)."""
    after = sorted(dd for dd in SPY if dd > base_close)[:n_returns]
    sessions = [base_close] + after
    mkt = mac.log_returns(SPY, sessions)
    return mac.excess_returns(closes, sessions, mkt), after


def loo_corr(t: str, members: list[str], excess: dict[str, np.ndarray], min_overlap: int):
    """Leave-one-out co-movement of t with the rest, on an arbitrary excess-return set (the OOS
    windows) — `mac.build_baskets` + `mac.correlate` with a declared overlap override."""
    vec = excess.get(t)
    if vec is None:
        return None, 0, 0
    others = [m for m in members if m != t]
    baskets = mac.build_baskets([{"name": "_pair", "stage": "_pair", "tickers": others}], excess,
                                stages=("_pair",), min_overlap=min_overlap)
    if not baskets:
        return None, 0, 0
    return mac.correlate(vec, baskets[0], exclude=t, min_overlap=min_overlap)


def tightness_live(members: list[str], ctx: te.ComoveContext):
    vals = []
    for m in members:
        cv = te._comove_verdict(m, members, ctx)
        if cv is not None and cv.corr is not None:
            vals.append(cv.corr)
    return (float(np.mean(vals)) if len(vals) >= 3 else None), len(vals)


def tightness_oos(members: list[str], excess: dict[str, np.ndarray], min_overlap: int):
    vals = []
    for m in members:
        c, _, _ = loo_corr(m, members, excess, min_overlap)
        if c is not None:
            vals.append(c)
    return (float(np.mean(vals)) if len(vals) >= 3 else None), len(vals)


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 5:
        return None
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    return float(np.corrcoef(rx, ry)[0, 1])


# ── singleton-sector logic, mirrored from _apply_carryforward_deterministic_filter ─────────
def singleton_sector_members(tickers: list[str]) -> set[str]:
    if len(tickers) < 3:
        return set()
    sec = {t: sector_of.get(t) or "Unknown" for t in tickers}
    known = [s for s in sec.values() if s != "Unknown"]
    if not known:
        return set()
    counts = Counter(known)
    singles = {s for s, n in counts.items() if n == 1 and len(counts) > 1}
    return {t for t in tickers if sec[t] in singles}


# ── join path / LLM / operator provenance ──────────────────────────────────────────────────
assign_by_date: dict[date, set[tuple[str, str]]] = defaultdict(set)
discovered_by_date: dict[date, dict[str, set[str]]] = defaultdict(dict)
split_by_date: dict[date, dict[str, set[str]]] = defaultdict(dict)
promoted_by_date: dict[date, dict[str, set[str]]] = defaultdict(dict)
shadow_by_date: dict[date, set[str]] = defaultdict(set)
merged_by_date: dict[date, list[tuple[str, str]]] = defaultdict(list)     # (child, parent)
revalidated_out: set[tuple[date, str, str]] = set()
operator_tickers: dict[str, set[str]] = defaultdict(set)                  # identity root -> tickers
for e in events:
    et, rd = e["event_type"], e["run_date"]
    if et == "assignment_llm_proposed":
        try:
            det = json.loads(e["detail"])
        except Exception:
            continue
        for p in det.get("proposals", []):
            assign_by_date[rd].add(((p.get("ticker") or "").upper(), te._strip_stage_label(p.get("theme") or "")))
    elif et == "theme_discovered":
        m = re.match(r"New theme: (.+?) \(\d+ stocks?\)", e["summary"])
        mt = re.search(r"Tickers: (.+)", e["detail"])
        if m and mt:
            discovered_by_date[rd][m.group(1)] = {t.strip().upper() for t in mt.group(1).split(",")}
    elif et == "theme_split":
        m = re.match(r"Split: '(.+?)' from '", e["summary"])
        mt = re.search(r"Tickers: (\[.*?\])", e["detail"])
        if m and mt:
            split_by_date[rd][m.group(1)] = {t.upper() for t in ast.literal_eval(mt.group(1))}
    elif et == "theme_operator_promoted":
        mf = re.search(r"final='(.+?)' tickers=(\[.*?\])", e["detail"])
        if mf:
            tks = {t.upper() for t in ast.literal_eval(mf.group(2))}
            promoted_by_date[rd][mf.group(1)] = tks
            operator_tickers[find(mf.group(1))].update(tks)
    elif et == "shadow_themes_promoted":
        m = re.search(r"promoted=(\[.*?\])", e["detail"])
        if m:
            try:
                shadow_by_date[rd].update(ast.literal_eval(m.group(1)))
            except Exception:
                pass
    elif et == "theme_thesis_merged":
        m = re.search(r"'(.+?)' merged into '(.+?)'", e["summary"])
        mn = re.search(r"merged_name='(.+?)'", e["detail"])
        if m:
            merged_by_date[rd].append((m.group(1), m.group(2), "thesis_merge"))
            if mn and mn.group(1) != m.group(2):
                union(m.group(2), mn.group(1))      # the merged product continues under merged_name
    elif et == "theme_pass1_5_absorption":
        m = re.search(r"Pass1\.5: '(.+?)' -> '(.+?)'", e["summary"])
        if m:
            merged_by_date[rd].append((m.group(1), m.group(2), "pass1_5_absorption"))
    elif et == "theme_merge_parent_child":
        m = re.search(r"'(.+?)' → sub-theme of '(.+?)'", e["summary"])
        if m:
            merged_by_date[rd].append((m.group(1), m.group(2), "sub_theme_merge"))
    elif et == "theme_auto_retired":
        for m in re.finditer(r"'(.+?)' -> parent='(.+?)'", e["detail"]):
            if m.group(2) != "(unknown)":
                merged_by_date[rd].append((m.group(1), m.group(2), "merge_pass_successor"))
    elif et == "theme_birth_gate":
        try:
            for o in json.loads(e["detail"]):
                if o.get("outcome") == "join" and o.get("join_target") and o.get("name") != o.get("join_target"):
                    merged_by_date[rd].append((o["name"], o["join_target"], "birth_gate_join"))
        except Exception:
            pass
    elif et == "ticker_revalidated_out":
        m = re.match(r"(\S+) removed from '(.+?)' by validation", e["summary"])
        if m:
            revalidated_out.add((rd, m.group(1).upper(), m.group(2)))


def join_trace(t: str, name: str, asof: date) -> dict:
    """Walk the identity's rows back from `asof` while t is present; the earliest such row is the
    join date. Then name the event that put it there."""
    rows = identity_rows(name)
    dates = sorted(dd for dd in rows if dd <= asof)
    join = None
    for dd in reversed(dates):
        if t in rows[dd]:
            join = dd
        else:
            break
    if join is None:
        return {"join": None, "path": "unknown", "validated_at_join": False, "rescores_survived": 0}
    al = aliases(name)
    path = "unknown"
    for dd in (join, join - timedelta(days=1), join + timedelta(days=1)):
        if any(nm in al and t in tks for nm, tks in promoted_by_date.get(dd, {}).items()):
            path = "operator_promoted"; break
        if any((t, nm) in assign_by_date.get(dd, set()) for nm in al):
            path = "assignment_llm"; break
        if any(nm in al and t in tks for nm, tks in discovered_by_date.get(dd, {}).items()):
            path = "discovery_llm"; break
        if any(nm in al and t in tks for nm, tks in split_by_date.get(dd, {}).items()):
            path = "split_llm"; break
        # the merge machinery: an edge source -> target on the join date whose target is this theme
        # and whose source held the ticker on its most recent prior row (within 8 days)
        hit = None
        for child, parent, mech in merged_by_date.get(dd, []):
            if parent not in al:
                continue
            src_rows = identity_rows(child)
            prior = [x for x in src_rows if dd - timedelta(days=8) <= x < dd or x == dd]
            if prior and t in src_rows[max(prior)]:
                hit = mech
                break
        if hit:
            path = f"merge:{hit}"; break
        if al & shadow_by_date.get(dd, set()):
            path = "shadow_promoted"; break
    if path == "unknown":
        # unlogged merge: the ticker sat in ANOTHER theme the session before and that theme is Retired
        # by the join date + 1 (dropped in a merge pass with no successor row we can read)
        prev_dates = [x for x in ALL_DATES if x < join]
        if prev_dates:
            pd = prev_dates[-1]
            for nm, row in board[pd].items():
                if nm in al or t not in row["tickers"] or row["stage"] == "Retired":
                    continue
                later = [x for x in ALL_DATES if join <= x <= join + timedelta(days=1) and nm in board[x]]
                if later and board[later[-1]][nm]["stage"] == "Retired":
                    path = "merge:unlogged"
                    break
    if path == "unknown" and join == ALL_DATES[0]:
        path = "before_log_window"
    # Mon/Wed/Fri rescore validation dates survived: run dates strictly after join, theme row with >= 2 members
    surv = sum(1 for dd in dates if dd > join and dd.weekday() in (0, 2, 4) and len(rows[dd]) >= 2)
    return {"join": join, "path": path,
            "validated_at_join": path in ("assignment_llm", "discovery_llm", "split_llm"),
            "rescores_survived": surv}


def operator_placed(t: str, name: str) -> bool:
    if t in operator_tickers.get(find(name), set()):
        return True
    return any((t, al) in bypassed_pairs for al in aliases(name))


# ── the 09-13 backtest's 95 (parsed from the committed doc, not hand-listed) ───────────────
backtest95: list[tuple[str, str, float]] = []
try:
    txt = open(BACKTEST_DOC).read()
    sec = txt.split("### Newly rejected, sector-admitted pairs")[1].split("## 3.")[0]
    for line in sec.splitlines():
        m = re.match(r"\| (\d{4}-\d\d-\d\d) \| (\S+) \| (.+?) \| (-?\d\.\d\d) \| \d+ \| \d+ \| (yes|no) \|", line)
        if m:
            backtest95.append((m.group(2).upper(), m.group(3).strip(), float(m.group(4))))
except Exception:
    pass


def in_backtest95(t: str, name: str) -> bool:
    al = aliases(name)
    return any(bt == t and any(a.startswith(bn[:40]) for a in al) for bt, bn, _ in backtest95)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# POPULATION 1 — today's board, single pass, live judge
# ═══════════════════════════════════════════════════════════════════════════════════════════
today = active_board(BOARD_TODAY)
ctx_today = ctx_for(TODAY_CTX)
assert ctx_today is not None
memberships: list[dict] = []
for name, row in today.items():
    members = row["tickers"]
    singles = singleton_sector_members(members)
    for t in members:
        cv = te._comove_verdict(t, members, ctx_today)
        memberships.append({
            "ticker": t, "theme": name, "stage": row["stage"], "members_n": len(members),
            "corr": cv.corr if cv else None, "overlap": cv.overlap if cv else 0,
            "basket_n": cv.basket_n if cv else 0,
            "verdict": ("admit" if cv.admit else "reject") if (cv and cv.admit is not None) else f"unjudgeable:{cv.reason if cv else 'no_ctx'}",
            "sector": sector_of.get(t) or "Unknown", "singleton_sector": t in singles,
            "paying": row["stage"] in PAYING,
        })
judgeable = [m for m in memberships if m["verdict"] in ("admit", "reject")]
evictions = [m for m in judgeable if m["verdict"] == "reject"]
unjudg = Counter(m["verdict"] for m in memberships if m["verdict"] not in ("admit", "reject"))
themes_unjudgeable = {m["theme"] for m in memberships if m["verdict"].startswith("unjudgeable")}
themes_fully_unjudgeable = {n for n in today if all(m["verdict"].startswith("unjudgeable") for m in memberships if m["theme"] == n)}

for m in evictions:
    jt = join_trace(m["ticker"], m["theme"], BOARD_TODAY)
    m.update(jt)
    m["llm_passed"] = jt["validated_at_join"] or jt["rescores_survived"] > 0
    m["operator"] = operator_placed(m["ticker"], m["theme"])
    m["in_backtest95"] = in_backtest95(m["ticker"], m["theme"])

ev_by_theme: dict[str, list[dict]] = defaultdict(list)
for m in evictions:
    ev_by_theme[m["theme"]].append(m)
starved_under3 = [n for n, evs in ev_by_theme.items() if len(today[n]["tickers"]) - len(evs) < 3]
starved_under_prune = [n for n, evs in ev_by_theme.items() if len(today[n]["tickers"]) - len(evs) < PRUNE_MIN]

# Shape A — as built: singleton-sector members re-judged by the tape
shape_a = [m for m in memberships if m["singleton_sector"]]
shape_a_kept = [m for m in shape_a if m["verdict"] == "admit"]
shape_a_stripped = [m for m in shape_a if m["verdict"] == "reject"]
shape_a_unj = [m for m in shape_a if m["verdict"].startswith("unjudgeable")]

# bridge to the 09-13 "95": which of those pairs are memberships today, and what they read now
bridge = []
for bt, bn, bc in backtest95:
    hit = [m for m in memberships if m["ticker"] == bt and any(a.startswith(bn[:40]) for a in aliases(m["theme"]))]
    bridge.append({"ticker": bt, "theme": bn, "corr_0913": bc, "member_today": bool(hit),
                   "corr_today": hit[0]["corr"] if hit else None, "verdict_today": hit[0]["verdict"] if hit else "not a member"})
bridge_members = [b for b in bridge if b["member_today"]]
bridge_pairs = {(b["ticker"], b["theme"]) for b in bridge}
bridge_member_pairs = {(b["ticker"], b["theme"]) for b in bridge_members}

# in-sample tightness on today's board (a floor, by construction) with the matched random control
tight_today = []
for n, evs in sorted(ev_by_theme.items()):
    members = today[n]["tickers"]
    ev_t = [m["ticker"] for m in evs]
    after = [t for t in members if t not in ev_t]
    tb, nb = tightness_live(members, ctx_today)
    ta, na = tightness_live(after, ctx_today)
    pool = [m["ticker"] for m in judgeable if m["theme"] == n]
    ctrl = []
    if len(pool) > len(ev_t) and tb is not None:
        for _ in range(N_DRAWS):
            drop = set(RNG.choice(pool, size=len(ev_t), replace=False).tolist())
            tc, _ = tightness_live([t for t in members if t not in drop], ctx_today)
            if tc is not None:
                ctrl.append(tc)
    tight_today.append({"theme": n, "stage": today[n]["stage"], "evict": ev_t, "members_n": len(members),
                        "before": tb, "after": ta, "ctrl_mean": float(np.mean(ctrl)) if ctrl else None,
                        "ctrl_ge_real": sum(1 for v in ctrl if ta is not None and v >= ta) if ctrl else None,
                        "ctrl_n": len(ctrl)})

# ═══════════════════════════════════════════════════════════════════════════════════════════
# OUT OF SAMPLE — W1 (the 09-11 board, 9 returns) and W2 (the 08-12 board, 30 returns)
# ═══════════════════════════════════════════════════════════════════════════════════════════
w2_sessions = mac.session_index(SPY, TODAY_CTX, W2_RETURNS)
W2_BOARD = w2_sessions[0]


def oos_study(board_date: date, n_returns: int | None) -> dict:
    bd = active_board(board_date)
    ctx = ctx_for(board_date + timedelta(days=1))
    if n_returns is None:
        n_returns = len([dd for dd in SPY if dd > board_date])
    ex_oos, oos_dates = oos_excess(board_date, n_returns)
    n_ret = len(oos_dates)
    rows = []
    for name, row in bd.items():
        members = row["tickers"]
        for t in members:
            cv = te._comove_verdict(t, members, ctx)
            if cv is None or cv.admit is None:
                continue
            c_oos, ov, used = loo_corr(t, members, ex_oos, n_ret)
            rows.append({"ticker": t, "theme": name, "stage": row["stage"], "members_n": len(members),
                         "corr_in": cv.corr, "verdict_in": "reject" if not cv.admit else "admit",
                         "corr_oos": None if c_oos is None else round(c_oos, 4), "oos_overlap": ov,
                         "sector": sector_of.get(t) or "Unknown",
                         "paying": row["stage"] in PAYING})
    ev = [r for r in rows if r["verdict_in"] == "reject"]
    kp = [r for r in rows if r["verdict_in"] == "admit"]
    ev_j = [r for r in ev if r["corr_oos"] is not None]
    kp_j = [r for r in kp if r["corr_oos"] is not None]
    both = [r for r in rows if r["corr_oos"] is not None]
    rho = spearman([r["corr_in"] for r in both], [r["corr_oos"] for r in both])
    # price-path context (NOT a verdict): median excess log return of evicted names vs their basket over the window
    def _cum(t):
        v = ex_oos.get(t)
        return None if v is None or not np.isfinite(v).all() else float(np.sum(v))
    ev_ret = [x for x in (_cum(r["ticker"]) for r in ev_j) if x is not None]
    basket_ret = []
    for r in ev_j:
        others = [m for m in bd[r["theme"]]["tickers"] if m != r["ticker"]]
        vals = [x for x in (_cum(m) for m in others) if x is not None]
        if vals:
            basket_ret.append(float(np.mean(vals)))
    # OOS tightness: evictions chosen in-sample, tightness change read on the OOS sessions, vs random removal on OOS
    by_theme: dict[str, list[dict]] = defaultdict(list)
    for r in ev:
        by_theme[r["theme"]].append(r)
    tight = []
    for n, evs in sorted(by_theme.items()):
        members = bd[n]["tickers"]
        ev_t = [r["ticker"] for r in evs]
        after = [t for t in members if t not in ev_t]
        tb, _ = tightness_oos(members, ex_oos, n_ret)
        ta, _ = tightness_oos(after, ex_oos, n_ret)
        tb_in, _ = tightness_live(members, ctx)
        ta_in, _ = tightness_live(after, ctx)
        pool = [r["ticker"] for r in rows if r["theme"] == n]
        ctrl = []
        if len(pool) > len(ev_t) and tb is not None and ta is not None:
            for _ in range(N_DRAWS):
                drop = set(RNG.choice(pool, size=len(ev_t), replace=False).tolist())
                tc, _ = tightness_oos([t for t in members if t not in drop], ex_oos, n_ret)
                if tc is not None:
                    ctrl.append(tc)
        tight.append({"theme": n, "stage": bd[n]["stage"], "evict": ev_t, "members_n": len(members),
                      "before_in": tb_in, "after_in": ta_in, "before": tb, "after": ta,
                      "ctrl_mean": float(np.mean(ctrl)) if ctrl else None,
                      "ctrl_ge_real": sum(1 for v in ctrl if v >= ta) if ctrl else None, "ctrl_n": len(ctrl)})
    return {"board_date": board_date, "ctx_date": board_date + timedelta(days=1), "themes_n": len(bd),
            "memberships_n": sum(len(r["tickers"]) for r in bd.values()), "judgeable_n": len(rows),
            "oos_dates": oos_dates, "n_ret": n_ret, "rows": rows, "ev": ev, "kp": kp, "ev_j": ev_j, "kp_j": kp_j,
            "rho": rho, "ev_ret": ev_ret, "basket_ret": basket_ret, "tight": tight}


W1 = oos_study(W1_BOARD, None)
W2 = oos_study(W2_BOARD, W2_RETURNS)

# ═══════════════════════════════════════════════════════════════════════════════════════════
# WHAT THE SYSTEM ALREADY DOES — the churn the split ruling creates
# ═══════════════════════════════════════════════════════════════════════════════════════════
admitted_over: list[dict] = []
strips: list[dict] = []
for e in events:
    if e["event_type"] == "assignment_comove_admitted_over_sector":
        try:
            det = json.loads(e["detail"])
        except Exception:
            continue
        admitted_over.append({"date": e["run_date"], "ticker": det["ticker"].upper(),
                              "theme": te._strip_stage_label(det["theme"]), "corr": det.get("corr")})
    elif e["event_type"] == "theme_carryforward_filter_stripped":
        m_th = re.search(r"theme=(.*)\n", e["detail"])
        m_so = re.search(r"sector_outlier=(\[.*?\])", e["detail"])
        if m_th and m_so:
            strips.append({"date": e["run_date"], "theme": m_th.group(1).strip(),
                           "tickers": {t.upper() for t in ast.literal_eval(m_so.group(1))}})
churn = []
for a in admitted_over:
    al = aliases(a["theme"])
    hit = [s for s in strips if s["theme"] in al and a["ticker"] in s["tickers"]
           and a["date"] < s["date"] <= a["date"] + timedelta(days=7)]
    churn.append({**a, "stripped_by_label": bool(hit), "days": (hit[0]["date"] - a["date"]).days if hit else None,
                  "readmissions": sum(1 for b in admitted_over if b["ticker"] == a["ticker"] and aliases(b["theme"]) & al)})
churn_pairs = {(c["ticker"], find(c["theme"])) for c in churn}
churn_pairs_stripped = {(c["ticker"], find(c["theme"])) for c in churn if c["stripped_by_label"]}
churn_pairs_bounced = {(c["ticker"], find(c["theme"])) for c in churn if c["readmissions"] >= 2}

# HOOD — the operator's "partially correct" case, made concrete (descriptive)
hood_rows = []
for name, row in today.items():
    nm = name.lower()
    is_member = "HOOD" in row["tickers"]
    if is_member or any(k in nm for k in ("bitcoin", "crypto", "digital asset", "digital-asset", "stablecoin")):
        cv = te._comove_verdict("HOOD", row["tickers"], ctx_today)
        hood_rows.append({"theme": name, "stage": row["stage"], "member": is_member,
                          "corr": cv.corr if cv else None, "verdict": cv.reason if cv else "no_ctx"})

# ═══════════════════════════════════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════════════════════════════════
L: list[str] = []
P = L.append
n_mem = len(memberships)
P(f"# #657 — co-movement as a REMOVAL rule: results ({BOARD_TODAY} board, judged on the {LOOKBACK} sessions to {ctx_today.before_date - timedelta(days=1)})")
P("")
P("## 1. Population — today's board")
P("")
P("| population | n |")
P("|---|---|")
P(f"| themes on the {BOARD_TODAY} board (7-day mirror of get_active_themes, Retired dropped) | {len(today)} |")
P(f"| memberships (ticker, theme) | {n_mem} |")
P(f"| … judgeable by the tape (≥3 basket members with history, ≥30 overlapping sessions) | {len(judgeable)} ({100*len(judgeable)/n_mem:.0f}% of {n_mem}) |")
P(f"| … NOT judgeable → the sector test keeps deciding (fail-safe) | {n_mem - len(judgeable)} {dict(unjudg)} |")
P(f"| themes the rule cannot touch at all (every member unjudgeable — a 3-member theme leaves a 2-name basket after leave-one-out) | {len(themes_fully_unjudgeable)} of {len(today)} (every theme with an unjudgeable member: {len(themes_unjudgeable)}) |")
P(f"| **Shape B evictions: judgeable memberships below {BAR}** | **{len(evictions)} of {len(judgeable)} ({100*len(evictions)/max(len(judgeable),1):.0f}%)** |")
P(f"| themes with ≥1 eviction | {len(ev_by_theme)} of {len(today)} |")
P(f"| themes an eviction pass would leave under 3 members | {len(starved_under3)} of {len(ev_by_theme)} changed themes |")
P(f"| themes it would leave under PRUNE_MIN_TICKERS={PRUNE_MIN} (retired next pass) | {len(starved_under_prune)} of {len(ev_by_theme)} |")
P(f"| evictions inside a PAYING theme (Accelerating/Mainstream — a LISTED member gets the EP +10 regardless of co-movement) | {sum(1 for m in evictions if m['paying'])} of {len(evictions)} ({len({m['ticker'] for m in evictions if m['paying']})} distinct stocks) |")
P("")
P("### Provenance of the evictions (each n is of the eviction list)")
P("")
paths = Counter(m["path"] for m in evictions)
P("| join path (first audit event naming the pair, rename lineage followed) | n |")
P("|---|---|")
for k, v in paths.most_common():
    P(f"| {k} | {v} of {len(evictions)} |")
merged_in = [m for m in evictions if m["path"].startswith("merge:")]
P("")
P("| how the pair got onto the board | n |")
P("|---|---|")
P(f"| an LLM judged THIS pair at join (assignment proposal + immediate validation, discovery/split + birth validation) | {sum(1 for m in evictions if m['validated_at_join'])} of {len(evictions)} |")
P(f"| the MERGE MACHINERY moved it in (thesis merge / Pass 1.5 absorption / sub-theme merge / merge-pass successor / birth-gate join) — no LLM judged the pair at join | {len(merged_in)} of {len(evictions)} |")
P(f"| a Lane-2 shadow cohort was promoted whole | {sum(1 for m in evictions if m['path'] == 'shadow_promoted')} of {len(evictions)} |")
P(f"| untraceable | {sum(1 for m in evictions if m['path'] in ('unknown', 'before_log_window'))} of {len(evictions)} |")
llm_passed = [m for m in evictions if m["llm_passed"]]
P("")
P("| membership-LLM / operator flags | n |")
P("|---|---|")
P(f"| passed the membership LLM at least once (validated at join, or survived ≥1 Mon/Wed/Fri rescore) | {len(llm_passed)} of {len(evictions)} ({100*len(llm_passed)/max(len(evictions),1):.0f}%) |")
P(f"| … validated at join (assignment / discovery / split path) | {sum(1 for m in evictions if m['validated_at_join'])} of {len(evictions)} |")
P(f"| … survived ≥1 Mon/Wed/Fri rescore after joining | {sum(1 for m in evictions if m['rescores_survived'] > 0)} of {len(evictions)} |")
P(f"| … survived ≥3 rescores | {sum(1 for m in evictions if m['rescores_survived'] >= 3)} of {len(evictions)} |")
P(f"| operator placed or confirmed (operator-promoted theme ticker, or bypassed cooldown) | {sum(1 for m in evictions if m['operator'])} of {len(evictions)} |")
P(f"| one of the 09-13 backtest's 95 assignment-night pairs | {sum(1 for m in evictions if m['in_backtest95'])} of {len(evictions)} |")
P(f"| median days on the board (join → {BOARD_TODAY}) | {int(np.median([(BOARD_TODAY - m['join']).days for m in evictions if m['join']]))} |")
P("")
P("### What the strips the engine ALREADY runs would do with the same names")
P("")
P("| overlap check | n |")
P("|---|---|")
P(f"| evictions that are SINGLETON-sector members (the carry-forward label strip removes these tomorrow anyway) | {sum(1 for m in evictions if m['singleton_sector'])} of {len(evictions)} |")
P(f"| evictions with an Unknown sector (the label never touches them) | {sum(1 for m in evictions if m['sector'] == 'Unknown')} of {len(evictions)} |")
P(f"| evictions the label leaves alone (same-sector, known) — reachable ONLY by Shape B | {sum(1 for m in evictions if not m['singleton_sector'] and m['sector'] != 'Unknown')} of {len(evictions)} |")
P("")
P("### Shape A — as built (`comove_ctx` passed to the two strip sites): singleton-sector members only")
P("")
P("| singleton-sector members on today's board | n |")
P("|---|---|")
P(f"| singleton-sector members (what the label strips tonight without the context) | {len(shape_a)} of {n_mem} memberships |")
P(f"| … the tape would KEEP (≥ {BAR}) | {len(shape_a_kept)} of {len(shape_a)} |")
P(f"| … the tape would STRIP (< {BAR}) — the label strips these too | {len(shape_a_stripped)} of {len(shape_a)} |")
P(f"| … unjudgeable → stripped by the label as before | {len(shape_a_unj)} of {len(shape_a)} |")
if shape_a:
    P("")
    P("| stock | theme | stage | sector | reading | tape says |")
    P("|---|---|---|---|---|---|")
    for m in sorted(shape_a, key=lambda m: -(m["corr"] if m["corr"] is not None else -9)):
        P(f"| {m['ticker']} | {m['theme'][:55]} | {m['stage']} | {m['sector']} | {f2(m['corr'])} | {m['verdict']} |")
P("")
P("### The churn the split ruling creates (job 1 admits on the tape, job 2 strips on the label)")
P("")
P("| since 2026-09-13 | n |")
P("|---|---|")
P(f"| pairs the tape admitted OVER the sector label (`assignment_comove_admitted_over_sector`) | {len(churn_pairs)} distinct pairs ({len(churn)} events) |")
P(f"| … stripped again by the label as `sector_outlier` within 7 days | {len(churn_pairs_stripped)} of {len(churn_pairs)} |")
P(f"| … re-admitted over the label ≥2 times (the loop) | {len(churn_pairs_bounced)} of {len(churn_pairs)} |")
if churn:
    P("")
    P("| night | stock | theme | admitted at | stripped by label after (days) | times admitted |")
    P("|---|---|---|---|---|---|")
    for c in sorted(churn, key=lambda c: (c["ticker"], c["date"])):
        P(f"| {c['date']} | {c['ticker']} | {c['theme'][:50]} | {f2(c['corr'])} | {c['days'] if c['stripped_by_label'] else '—'} | {c['readmissions']} |")
P("")
P("## 2. The eviction list (Shape B, today's board)")
P("")
P(f"Every judgeable membership below {BAR}. LLM = passed the membership LLM at least once; op = operator placed/confirmed; "
  "single = singleton-sector (the label strips it anyway); pay = paying-stage theme; bt95 = in the 09-13 backtest's 95.")
P("")
P("| stock | theme | stage | reading | basket | sector | joined | path | rescores | LLM | op | single | pay | bt95 |")
P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for m in sorted(evictions, key=lambda m: (m["theme"], m["corr"])):
    P(f"| {m['ticker']} | {m['theme'][:48]} | {m['stage'][:5]} | {m['corr']:.2f} | {m['basket_n']} | {m['sector'][:14]} | "
      f"{m['join'] or '?'} | {m['path']} | {m['rescores_survived']} | {'y' if m['llm_passed'] else 'n'} | {'y' if m['operator'] else '—'} | "
      f"{'y' if m['singleton_sector'] else '—'} | {'y' if m['paying'] else '—'} | {'y' if m['in_backtest95'] else '—'} |")
P("")
P("### Bridge to the 09-13 backtest's \"95 of 504\"")
P("")
P(f"- Those 95 were ASSIGNMENT-NIGHT pairs judged against the PRIOR night's basket. Parsed from the committed doc: {len(backtest95)} rows = {len(bridge_pairs)} distinct pairs; "
  f"**{len(bridge_member_pairs)} of {len(bridge_pairs)} distinct pairs are memberships on today's board** ({len(bridge_members)} rows; the rest left the board or the theme retired); "
  f"of those {len(bridge_member_pairs)} pairs, {len({(b['ticker'], b['theme']) for b in bridge_members if b['verdict_today']=='reject'})} still read below {BAR} today, "
  f"{len({(b['ticker'], b['theme']) for b in bridge_members if b['verdict_today']=='admit'})} now read above it, "
  f"{len({(b['ticker'], b['theme']) for b in bridge_members if b['verdict_today'].startswith('unjudgeable')})} unjudgeable today (the table lists rows, so HOOD and TRAX appear twice).")
P("")
P("| stock | theme (09-13 doc) | 09-13 reading | today |")
P("|---|---|---|---|")
for b in sorted(bridge_members, key=lambda b: (b["verdict_today"], b["ticker"])):
    P(f"| {b['ticker']} | {b['theme'][:50]} | {b['corr_0913']:.2f} | {f2(b['corr_today'])} {b['verdict_today']} |")
P("")
P("### HOOD — the \"partially correct\" case, today's readings (descriptive; 0.35 is a per-pair bar, not best-of-many)")
P("")
P("| theme | stage | HOOD is a member | reading | tape |")
P("|---|---|---|---|---|")
for h in sorted(hood_rows, key=lambda h: -(h["corr"] if h["corr"] is not None else -9)):
    P(f"| {h['theme'][:60]} | {h['stage']} | {'yes' if h['member'] else 'no'} | {f2(h['corr'])} | {h['verdict']} |")
if not hood_rows:
    P("| (HOOD is not on today's board and no crypto-named theme exists) | | | | |")
P("")
P("## 3. What happened afterwards — OUT OF SAMPLE co-movement (not returns)")
P("")
for tag, W in (("W1 — the 09-13 backtest's board", W1), ("W2 — engine-grade window", W2)):
    n_ev, n_kp = len(W["ev"]), len(W["kp"])
    ev_j, kp_j = W["ev_j"], W["kp_j"]
    P(f"### {tag}: board {W['board_date']} ({W['themes_n']} themes, {W['memberships_n']} memberships, {W['judgeable_n']} judgeable), "
      f"in-sample = {LOOKBACK} sessions to {W['board_date']}, out-of-sample = {W['n_ret']} returns {W['oos_dates'][0]} … {W['oos_dates'][-1]}")
    P("")
    P("| group (in-sample verdict) | n | OOS judgeable | mean OOS co-movement | median | share < 0.35 OOS | share ≥ 0.35 OOS |")
    P("|---|---|---|---|---|---|---|")
    for gname, g_all, g_j in (("would be EVICTED (in-sample < 0.35)", W["ev"], ev_j), ("KEPT (in-sample ≥ 0.35)", W["kp"], kp_j)):
        vals = [r["corr_oos"] for r in g_j]
        below = sum(1 for v in vals if v < BAR)
        P(f"| {gname} | {len(g_all)} | {len(g_j)} | {f2(np.mean(vals)) if vals else 'n/a'} | {f2(np.median(vals)) if vals else 'n/a'} | "
          f"{pct(below, len(g_j))} | {pct(len(g_j) - below, len(g_j))} |")
    P("")
    both_n = len(ev_j) + len(kp_j)
    P(f"- Spearman rank correlation between the in-sample and out-of-sample readings over all {both_n} judgeable memberships: "
      f"**{f2(W['rho'])}**.")
    se = (1 - 0.3 ** 2) / np.sqrt(max(W["n_ret"] - 2, 1))
    P(f"- Noise floor: with {W['n_ret']} returns the standard error of a Pearson r near 0.3 is ≈ {se:.2f}"
      + (" — no per-name verdict is readable in this window; only the group contrast is." if W["n_ret"] < 30 else " — a per-name direction is readable, with n."))
    if W["ev_ret"]:
        P(f"- Price path, CONTEXT ONLY (not a verdict): median market-adjusted return over the window, evicted names "
          f"{100*float(np.median(W['ev_ret'])):+.1f}% (n={len(W['ev_ret'])}) vs their theme baskets {100*float(np.median(W['basket_ret'])):+.1f}% (n={len(W['basket_ret'])}).")
    P("")
    if W["n_ret"] >= 30:
        stayed = [r for r in ev_j if r["corr_oos"] < BAR]
        rose = [r for r in ev_j if r["corr_oos"] >= BAR]
        P(f"**Per name (readable at {W['n_ret']} returns): {len(stayed)} of {len(ev_j)} would-be-evicted names kept failing to move with their theme "
          f"(the tape was right); {len(rose)} of {len(ev_j)} started moving with it (the tape was early or wrong).**")
        P("")
        P("| stock | theme | stage | in-sample | OOS ({} returns) | direction |".format(W["n_ret"]))
        P("|---|---|---|---|---|---|")
        for r in sorted(ev_j, key=lambda r: -r["corr_oos"]):
            P(f"| {r['ticker']} | {r['theme'][:50]} | {r['stage'][:5]} | {r['corr_in']:.2f} | {r['corr_oos']:.2f} | "
              f"{'rose above the bar' if r['corr_oos'] >= BAR else 'still below'} |")
        P("")
        # mirror: kept names that fell below the bar OOS (the false-keep side of the same coin)
        fell = [r for r in kp_j if r["corr_oos"] < BAR]
        P(f"- Mirror, the kept side: {pct(len(fell), len(kp_j))} in-sample-kept memberships read below {BAR} out of sample.")
        P("")
P("## 4. Tightness before / after, with the matched random-removal control")
P("")
P("Tightness = mean leave-one-out co-movement of each member with the rest (no engine metric exists; the 09-13 doc's). "
  f"Control = remove the SAME NUMBER of members at random from the theme's judgeable members, {N_DRAWS} draws, seed 20260925. "
  "'control ≥ real' = draws whose after-tightness is at least the tape's.")
P("")
P("### 4a. In-sample on today's board — a FLOOR by construction (removing the lowest-scoring members raises the mean of what is left)")
P("")
P("| theme | stage | evicted | members | before | after | control mean | control ≥ real (of draws) |")
P("|---|---|---|---|---|---|---|---|")
for t in tight_today:
    P(f"| {t['theme'][:48]} | {t['stage'][:5]} | {', '.join(t['evict'])} | {t['members_n']} | {f2(t['before'])} | {f2(t['after'])} | "
      f"{f2(t['ctrl_mean'])} | {t['ctrl_ge_real'] if t['ctrl_ge_real'] is not None else 'n/a'}/{t['ctrl_n']} |")
ok = [t for t in tight_today if t["before"] is not None and t["after"] is not None]
if ok:
    P("")
    P(f"- Across the {len(ok)} measurable changed themes: mean tightness **{np.mean([t['before'] for t in ok]):.2f} → {np.mean([t['after'] for t in ok]):.2f}**; "
      f"random removal of the same count lands at **{np.mean([t['ctrl_mean'] for t in ok if t['ctrl_mean'] is not None]):.2f}** (n={sum(1 for t in ok if t['ctrl_mean'] is not None)}).")
P("")
for tag, W in (("W1", W1), ("W2", W2)):
    P(f"### 4b. OUT OF SAMPLE — evictions chosen on the in-sample window, tightness change read on the {W['n_ret']} OOS returns ({tag}, board {W['board_date']}) — this is the reading that counts")
    P("")
    P("| theme | stage | evicted | members | in-sample before → after | OOS before | OOS after | OOS control mean | control ≥ real (of draws) |")
    P("|---|---|---|---|---|---|---|---|---|")
    for t in W["tight"]:
        P(f"| {t['theme'][:44]} | {t['stage'][:5]} | {', '.join(t['evict'])[:40]} | {t['members_n']} | {f2(t['before_in'])} → {f2(t['after_in'])} | "
          f"{f2(t['before'])} | {f2(t['after'])} | {f2(t['ctrl_mean'])} | {t['ctrl_ge_real'] if t['ctrl_ge_real'] is not None else 'n/a'}/{t['ctrl_n']} |")
    okw = [t for t in W["tight"] if t["before"] is not None and t["after"] is not None and t["ctrl_mean"] is not None]
    if okw:
        tighter = sum(1 for t in okw if t["after"] > t["before"])
        beats = sum(1 for t in okw if t["after"] > t["ctrl_mean"])
        sig = sum(1 for t in okw if t["ctrl_ge_real"] is not None and t["ctrl_n"] and t["ctrl_ge_real"] / t["ctrl_n"] <= 0.05)
        P("")
        P(f"- {tag}: across the {len(okw)} measurable changed themes, OOS tightness {np.mean([t['before'] for t in okw]):.2f} → {np.mean([t['after'] for t in okw]):.2f} "
          f"(tighter in {tighter} of {len(okw)}); random removal of the same count lands at {np.mean([t['ctrl_mean'] for t in okw]):.2f}; "
          f"the tape's eviction beats the random control's mean in {beats} of {len(okw)} themes, and beats ≥95% of draws in {sig} of {len(okw)}.")
    P("")

out = "\n".join(L)
open(D + "results.md", "w").write(out)


def psv(name: str, rows: list[dict], fields: list[str]) -> None:
    with open(D + name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="|", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (", ".join(v) if isinstance(v, list) else v) for k, v in r.items()})


psv("evictions_today.psv", sorted(evictions, key=lambda m: (m["theme"], m["corr"])),
    ["ticker", "theme", "stage", "corr", "overlap", "basket_n", "members_n", "sector", "singleton_sector", "paying",
     "join", "path", "validated_at_join", "rescores_survived", "llm_passed", "operator", "in_backtest95"])
psv("memberships_today.psv", memberships, ["ticker", "theme", "stage", "corr", "overlap", "basket_n", "members_n", "verdict", "sector", "singleton_sector", "paying"])
psv("shape_a_today.psv", shape_a, ["ticker", "theme", "stage", "sector", "corr", "verdict"])
psv("churn_since_0913.psv", churn, ["date", "ticker", "theme", "corr", "stripped_by_label", "days", "readmissions"])
psv("oos_w1.psv", W1["rows"], ["ticker", "theme", "stage", "members_n", "corr_in", "verdict_in", "corr_oos", "oos_overlap", "sector", "paying"])
psv("oos_w2.psv", W2["rows"], ["ticker", "theme", "stage", "members_n", "corr_in", "verdict_in", "corr_oos", "oos_overlap", "sector", "paying"])
psv("tightness_today.psv", tight_today, ["theme", "stage", "evict", "members_n", "before", "after", "ctrl_mean", "ctrl_ge_real", "ctrl_n"])
psv("tightness_oos_w1.psv", W1["tight"], ["theme", "stage", "evict", "members_n", "before_in", "after_in", "before", "after", "ctrl_mean", "ctrl_ge_real", "ctrl_n"])
psv("tightness_oos_w2.psv", W2["tight"], ["theme", "stage", "evict", "members_n", "before_in", "after_in", "before", "after", "ctrl_mean", "ctrl_ge_real", "ctrl_n"])
psv("bridge_0913_95.psv", bridge, ["ticker", "theme", "corr_0913", "member_today", "corr_today", "verdict_today"])
psv("hood_today.psv", hood_rows, ["theme", "stage", "member", "corr", "verdict"])

w2_ev_j = W2["ev_j"]
summary = {
    "board_date": str(BOARD_TODAY), "themes_n": len(today), "memberships_n": n_mem,
    "population_n": len(judgeable), "evictions_n": len(evictions),
    "evicted_llm_passed_n": len(llm_passed),
    "evicted_operator_n": sum(1 for m in evictions if m["operator"]),
    "evicted_paying_n": sum(1 for m in evictions if m["paying"]),
    "overlap_with_existing_filters_n": sum(1 for m in evictions if m["singleton_sector"]),
    "shape_a_singletons_n": len(shape_a), "shape_a_kept_n": len(shape_a_kept), "shape_a_stripped_n": len(shape_a_stripped),
    "themes_changed_n": len(ev_by_theme), "themes_under3_after_n": len(starved_under3),
    "churn_pairs_n": len(churn_pairs), "churn_pairs_stripped_n": len(churn_pairs_stripped),
    "w2_board": str(W2_BOARD), "w2_evicted_n": len(W2["ev"]), "w2_evicted_oos_judgeable_n": len(w2_ev_j),
    "after_still_not_comoving_n": sum(1 for r in w2_ev_j if r["corr_oos"] < BAR),
    "after_now_comoving_n": sum(1 for r in w2_ev_j if r["corr_oos"] >= BAR),
    "w2_kept_oos_below_bar_n": sum(1 for r in W2["kp_j"] if r["corr_oos"] < BAR), "w2_kept_oos_judgeable_n": len(W2["kp_j"]),
    "w2_rho": W2["rho"], "w1_rho": W1["rho"],
    "w1_evicted_oos_judgeable_n": len(W1["ev_j"]), "w1_evicted_oos_below_n": sum(1 for r in W1["ev_j"] if r["corr_oos"] < BAR),
    "w1_kept_oos_judgeable_n": len(W1["kp_j"]), "w1_kept_oos_below_n": sum(1 for r in W1["kp_j"] if r["corr_oos"] < BAR),
    "bridge_95_parsed_n": len(backtest95), "bridge_95_members_today_n": len(bridge_members),
}
json.dump(summary, open(D + "summary.json", "w"), indent=1, default=str)
print(out)
print("\nSUMMARY", json.dumps(summary, default=str))
