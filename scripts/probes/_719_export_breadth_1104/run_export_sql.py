"""#719 one-off: run scripts/export_breadth_snapshot.sql on a REAL (embedded) Postgres against SYNTHETIC tables,
then recompute every number in plain Python from the same rows and compare.

No production data and no server. Run with a venv holding `pixeltable-pgserver` and `psycopg2-binary`
(python3.13 -m venv v && v/bin/pip install pixeltable-pgserver psycopg2-binary):

    python run_export_sql.py               # correctness: fixture + independent Python recompute (prints PASS/FAIL)
    python run_export_sql.py --scale       # timing: ~11,000 tickers x ~1,260 sessions (~13.9M rows), prod-sized

The Python recompute is written from the RULES (docs/architecture/market_breadth_snapshot.md), not from the SQL, so an
off-by-one in a session index (the 20 / 60 / 150 / 252 offsets) shows up as a mismatch, which no regex test can see.

Fixture (every number invented; seeded):
  calendar  weekdays 2025-06-02 .. 2026-11-03, minus 3 holidays (no rows at all); 2026-07-02 carries only ~2,000 rows
            (a partial ingest: NOT a session, its bars must be ignored); 2026-11-04 carries 2,900 rows (a partial
            trailing ingest: as_of must stay 2026-11-03).
  3,050 CS random-walk tickers (R0000..) with drifts that spread them across all four stages
  NEWHI / NEWLO        a clean new 52-week high / low on as_of
  NULLLO               would be a new low, but its as_of low_price is NULL       -> never a new low (ineligible)
  ZEROLO               would be a new low, but its as_of low_price is 0          -> never a new low (ineligible)
  ZEROHIST             declining, three zero lows in the prior 252 (excluded from the min) -> still a new low
  SHORTH               only 200 bars                                             -> unstaged, ineligible
  GAPPY                one missing bar inside the last 210 sessions, 12 in the prior 252 -> unstaged, ineligible
  NOPRIOR              no bar on the previous session                            -> adv/dec no_prior
  UNCH                 as_of close == previous close                             -> unchanged
  PENNY                close 0.90 on as_of                                       -> outside the universe (a theme member)
  ETF1                 security_type ETF                                         -> outside the universe (a theme member)
  NOTYPE               no mi_security_types row                                  -> outside the universe
  IPO26                first bar 2026-03-02                                      -> drops out of YTD only
  S2UP / S4DN / S3TOP / S1BASE  hand-built stage 2 / 4 / 3 (flat after an advance) / 1 (flat after a decline)
  themes   'Alpha' (members incl. PENNY, ETF1, IPO26, a duplicate, a ticker with no bars at all),
           'Beta' (newest row Retired, an older non-Retired row inside the window -> excluded, NOT resurrected),
           'Gamma' (newest row 9 days before as_of -> excluded),
           'Delta' (a row dated 2026-11-04, after as_of -> included with THAT membership),
           'Epsilon' (no members), 'Zeta' (an e_code in mi_theme_ecosystems)
  groups   (#722) 'Alpha' and 'Zeta' share ecosystem E-AISEMI and share R0001 -> the group counts R0001 ONCE;
           'Delta' -> E99 (a code not in the YAML: prints its code); 'Epsilon' (no members) -> E-CYBR (a group with
           zero members, null returns); 'Eta' has NO mi_theme_ecosystems row (e_code null) and 'Theta' -> E-UNASSIGNED,
           sharing R0009: both file under E-UNASSIGNED, printed 'Other', R0009 once. Names are re-derived here from
           theme_ecosystems.yaml, not read from the SQL's VALUES list.
  scores   2026-10-28..11-03: 2,400 rows a day; 2026-11-04: ONE stray row -> score_date must be 2026-11-03.
  empty    mi_security_types deleted (inside a rolled-back transaction) -> no session -> ZERO rows, never an all-null file.
  removal  each hand-made ticker deleted in turn (rolled back): the counts must move by exactly its expected cells.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import math
import pathlib
import random
import sys
import tempfile
import time

import psycopg2
import pixeltable_pgserver as pgserver
import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
SQL = (REPO / "scripts" / "export_breadth_snapshot.sql").read_text()

DDL = """
CREATE TABLE mi_daily_closes (trade_date DATE NOT NULL, ticker TEXT NOT NULL, close FLOAT NOT NULL, volume BIGINT,
  open_price FLOAT, high_price FLOAT, low_price FLOAT, PRIMARY KEY (trade_date, ticker));
CREATE TABLE mi_security_types (ticker TEXT PRIMARY KEY, security_type TEXT NOT NULL, exchange TEXT DEFAULT '',
  updated_at TIMESTAMPTZ DEFAULT NOW(), name TEXT);
CREATE TABLE mi_themes (id SERIAL PRIMARY KEY, theme_date DATE NOT NULL, name TEXT NOT NULL, stage TEXT NOT NULL,
  score FLOAT, description TEXT, tickers TEXT[], rs_avg FLOAT, parent_theme TEXT, days_active INT NOT NULL DEFAULT 0,
  consecutive_accelerating INT NOT NULL DEFAULT 0, pct_above_20sma REAL, source TEXT NOT NULL DEFAULT 'live',
  created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE mi_theme_ecosystems (theme_name TEXT PRIMARY KEY, e_code TEXT NOT NULL, method TEXT,
  assigned_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE mi_stock_scores (ticker TEXT NOT NULL, score_date DATE NOT NULL, rs_composite FLOAT, rs_rank INT,
  sector TEXT, close FLOAT, sma_50 FLOAT, PRIMARY KEY (ticker, score_date));
"""
INDEXES = "CREATE INDEX idx_daily_closes_ticker ON mi_daily_closes(ticker); " \
          "CREATE INDEX idx_daily_closes_ticker_date ON mi_daily_closes(ticker, trade_date);"

AS_OF = dt.date(2026, 11, 3)
HOLIDAYS = {dt.date(2025, 7, 4), dt.date(2025, 11, 27), dt.date(2025, 12, 25)}
PARTIAL_MID = dt.date(2026, 7, 2)
PARTIAL_TAIL = dt.date(2026, 11, 4)


def weekdays(a: dt.date, b: dt.date) -> list[dt.date]:
    out, d = [], a
    while d <= b:
        if d.weekday() < 5 and d not in HOLIDAYS:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def build_fixture():
    rnd = random.Random(719)
    days = weekdays(dt.date(2025, 6, 2), AS_OF)
    rows: list[tuple] = []          # (date, ticker, close, high, low)
    types: dict[str, str] = {}

    def bar(d, t, c, hi=None, lo=None, spread=0.01):
        rows.append((d, t, c, c * (1 + spread) if hi is None else hi, c * (1 - spread) if lo is None else lo))

    # 3,050 random walks. Drift spread across names so every stage is populated.
    for i in range(3050):
        t = f"R{i:04d}"
        types[t] = "ADRC" if i % 17 == 0 else "CS"
        price = rnd.uniform(0.5, 120)
        drift = rnd.uniform(-0.004, 0.004)
        for d in days:
            price *= math.exp(drift + rnd.gauss(0, 0.02))
            if d == PARTIAL_MID and i >= 2000:
                continue                          # partial day: only 2,000 rows
            bar(d, t, round(price, 4), spread=abs(rnd.gauss(0.01, 0.005)))
    for i in range(2900):                         # the partial trailing day: 2,900 rows
        bar(PARTIAL_TAIL, f"R{i:04d}", 50.0)

    def path(t, kind, closes, typ="CS"):
        types[t] = typ
        for d, c in zip(days, closes):
            bar(d, t, c)

    n = len(days)
    path("NEWHI", "", [10 + 0.05 * k for k in range(n)])
    path("NEWLO", "", [100 - 0.2 * k for k in range(n)])
    types["NULLLO"] = types["ZEROLO"] = types["ZEROHIST"] = "CS"
    for k, d in enumerate(days):
        c = 100 - 0.2 * k
        bar(d, "NULLLO", c, lo=None if d != AS_OF else None)
        if d == AS_OF:
            rows[-1] = (d, "NULLLO", c, c * 1.01, None)
        bar(d, "ZEROLO", c, lo=0.0 if d == AS_OF else None)
        bar(d, "ZEROHIST", c, lo=0.0 if k in (n - 30, n - 60, n - 90) else None)
    path("SHORTH", "", [20 + 0.01 * k for k in range(200)] , )
    # SHORTH's 200 bars must END at as_of: re-place them.
    rows[:] = [r for r in rows if r[1] != "SHORTH"]
    for k, d in enumerate(days[-200:]):
        bar(d, "SHORTH", 20 + 0.01 * k)
    types["GAPPY"] = "CS"
    gap_dates = {days[-50]} | {days[-100 - 2 * j] for j in range(11)}
    for k, d in enumerate(days):
        if d not in gap_dates:
            bar(d, "GAPPY", 30 + 0.03 * k)
    types["NOPRIOR"] = "CS"
    for k, d in enumerate(days):
        if d != days[-2]:
            bar(d, "NOPRIOR", 40 + 0.01 * k)
    types["UNCH"] = "CS"
    for k, d in enumerate(days):
        bar(d, "UNCH", 25.0 if k >= n - 2 else 20 + 0.01 * k)
    path("PENNY", "", [0.90 + 0.0 * k for k in range(n)])
    path("ETF1", "", [300 + 0.1 * k for k in range(n)], typ="ETF")
    for k, d in enumerate(days):
        bar(d, "NOTYPE", 15 + 0.01 * k)
    types["IPO26"] = "CS"
    for k, d in enumerate([d for d in days if d >= dt.date(2026, 3, 2)]):
        bar(d, "IPO26", 10 + 0.1 * k)
    # Stage hand cases (n ~ 370 sessions; the last 210 decide the stage).
    path("S2UP", "", [50 * (1.003 ** k) for k in range(n)])
    path("S4DN", "", [50 * (0.997 ** k) for k in range(n)])
    path("S3TOP", "", [20 + 0.2 * min(k, n - 200) for k in range(n)])    # advance, then flat for 200 sessions
    path("S1BASE", "", [80 - 0.2 * min(k, n - 200) for k in range(n)])   # decline, then flat for 200 sessions
    for t in ("NEWHI", "NEWLO", "S2UP", "S4DN", "S3TOP", "S1BASE", "PENNY"):
        types.setdefault(t, "CS")
    return days, rows, types


THEMES = [
    # (theme_date, name, stage, tickers)
    (dt.date(2026, 11, 2), "Alpha", "Accelerating", ["R0001", "R0002", "PENNY", "ETF1", "IPO26", "R0002", "NOBARS"]),
    (dt.date(2026, 11, 3), "Alpha", "Accelerating", ["R0001", "R0002", "PENNY", "ETF1", "IPO26", "R0002", "NOBARS"]),
    (dt.date(2026, 10, 30), "Beta", "Mainstream", ["R0003", "R0004"]),
    (dt.date(2026, 11, 3), "Beta", "Retired", []),
    (dt.date(2026, 10, 25), "Gamma", "Fading", ["R0005"]),
    (dt.date(2026, 11, 1), "Delta", "Nascent", ["R0006"]),
    (dt.date(2026, 11, 4), "Delta", "Nascent", ["R0007", "R0008", "NEWHI"]),
    (dt.date(2026, 11, 3), "Epsilon", "Nascent", []),
    (dt.date(2026, 11, 3), "Zeta", "Mainstream", ["S2UP", "S4DN", "R0001"]),
    (dt.date(2026, 11, 3), "Eta", "Nascent", ["R0001", "R0009"]),
    (dt.date(2026, 11, 3), "Theta", "Nascent", ["R0009", "R0010"]),
]
# theme name -> e_code in mi_theme_ecosystems ('Eta' has no row on purpose: e_code null).
ECO_OF = {"Alpha": "E-AISEMI", "Zeta": "E-AISEMI", "Delta": "E99", "Epsilon": "E-CYBR", "Theta": "E-UNASSIGNED"}
YAML_NAMES = {e["e_code"]: e["name"] for e in
              yaml.safe_load((REPO / "theme_ecosystems.yaml").read_text())["ecosystems"]}


def load(cur, rows, types, *, copy_rows=True):
    cur.execute(DDL)
    if copy_rows:
        buf = io.StringIO()
        for d, t, c, h, lo in rows:
            buf.write(f"{d}\t{t}\t{c}\t{'\\N' if h is None else h}\t{'\\N' if lo is None else lo}\n")
        buf.seek(0)
        cur.copy_from(buf, "mi_daily_closes", columns=("trade_date", "ticker", "close", "high_price", "low_price"))
    cur.execute(INDEXES)
    for t, typ in types.items():
        cur.execute("INSERT INTO mi_security_types (ticker, security_type) VALUES (%s, %s)", (t, typ))
    for td, name, stage, tickers in THEMES:
        cur.execute("INSERT INTO mi_themes (theme_date, name, stage, tickers) VALUES (%s,%s,%s,%s)",
                    (td, name, stage, tickers))
    for theme, code in ECO_OF.items():
        cur.execute("INSERT INTO mi_theme_ecosystems (theme_name, e_code) VALUES (%s, %s)", (theme, code))
    scored = sorted(types)[:2400]
    for back in range(7):
        sd = AS_OF - dt.timedelta(days=back)
        cur.executemany("INSERT INTO mi_stock_scores (ticker, score_date, rs_rank) VALUES (%s,%s,%s)",
                        [(t, sd, i + 1 + back) for i, t in enumerate(scored)])
    cur.execute("INSERT INTO mi_stock_scores (ticker, score_date, rs_rank) VALUES ('NEWHI', %s, 1)", (PARTIAL_TAIL,))
    cur.execute("ANALYZE")
    return {t: i + 1 for i, t in enumerate(scored)}


# ---------------------------------------------------------------- independent recompute, from the written rules
def recompute(rows, types, ranks):
    by_date: dict[dt.date, int] = {}
    for d, t, *_ in rows:
        if types.get(t) in ("CS", "ADRC"):
            by_date[d] = by_date.get(d, 0) + 1
    sessions = sorted([d for d, n in by_date.items() if n >= 3000], reverse=True)
    as_of, prev = sessions[0], sessions[1]
    sess_idx = {d: i for i, d in enumerate(sessions)}
    pye = max(d for d in sessions if d.year < as_of.year)
    bars: dict[str, dict[int, tuple]] = {}
    for d, t, c, h, lo in rows:
        if d in sess_idx and c > 0:
            bars.setdefault(t, {})[sess_idx[d]] = (c, h, lo)
    universe = sorted(t for t, b in bars.items() if types.get(t) in ("CS", "ADRC") and 0 in b and b[0][0] >= 1.0)

    def ok(x):
        return x is not None and x > 0

    def stage_of(t):
        b = bars.get(t, {})
        # 2026-11-04 relaxation (SSoT): a bar on at least 203 of the 210 sessions 0-209, each SMA over the bars present.
        if 0 not in b or sum(i in b for i in range(210)) < 203:
            return None
        def sma(end):
            vals = [b[i][0] for i in range(end, end + 150) if i in b]
            return sum(vals) / len(vals)
        now, s20, s60 = sma(0), sma(20), sma(60)
        slope, c0 = now / s20 - 1, b[0][0]
        if slope > 0.01:
            return 2 if c0 >= now else 3
        if slope < -0.01:
            return 4 if c0 <= now else 1
        return 3 if now > s60 else 1

    hl = {"eligible_n": 0, "new_highs": 0, "new_lows": 0}
    ad = {"advances": 0, "declines": 0, "unchanged": 0, "no_prior": 0}
    stg = {"1": 0, "2": 0, "3": 0, "4": 0, "unstaged": 0}
    for t in universe:
        b = bars[t]
        prior = [b[i] for i in range(1, 253) if i in b and ok(b[i][1]) and ok(b[i][2])]
        if ok(b[0][1]) and ok(b[0][2]) and len(prior) >= 245:
            hl["eligible_n"] += 1
            hl["new_highs"] += b[0][1] >= max(p[1] for p in prior)
            hl["new_lows"] += b[0][2] <= min(p[2] for p in prior)
        if 1 not in b:
            ad["no_prior"] += 1
        else:
            k = "advances" if b[0][0] > b[1][0] else "declines" if b[0][0] < b[1][0] else "unchanged"
            ad[k] += 1
        s = stage_of(t)
        stg["unstaged" if s is None else str(s)] += 1

    latest: dict[str, tuple] = {}
    for i, (td, name, stage, tickers) in enumerate(THEMES):
        if td >= as_of - dt.timedelta(days=7) and (name not in latest or (td, i) > latest[name][:2]):
            latest[name] = (td, i, stage, tickers)
    active = sorted(n for n, v in latest.items() if v[2] != "Retired")
    themes = []
    member_of: dict[str, list[int]] = {}
    pye_i = sess_idx[pye]

    def close_at(t, i):
        return bars.get(t, {}).get(i, (None,))[0]

    def ytd_base(t):
        b = bars.get(t, {})
        cands = [i for i in b if i >= pye_i]
        return b[min(cands)][0] if cands else None

    for idx, name in enumerate(active):
        td, _, stage, tickers = latest[name]
        mem = sorted(set(tickers))
        for m in mem:
            member_of.setdefault(m, []).append(idx)
        th = {"idx": idx, "name": name, "stage": stage, "e_code": ECO_OF.get(name),
              "theme_date": str(td), "n_members": len(mem), "members": mem}
        for key, base in (("1d", lambda t: close_at(t, 1)), ("5d", lambda t: close_at(t, 5)),
                          ("21d", lambda t: close_at(t, 21)), ("ytd", ytd_base)):
            vals = [(close_at(m, 0) / base(m) - 1) * 100 for m in mem
                    if close_at(m, 0) is not None and base(m) is not None]
            th[f"ret_{key}"] = round(sum(vals) / len(vals), 2) if vals else None
            th[f"n_{key}"] = len(vals)
        themes.append(th)
    # #722 — ecosystem groups, from the written rules: file each theme under its e_code (none -> E-UNASSIGNED), pool the
    # UNIQUE members, return them on the same bases.
    groups: dict[str, dict] = {}
    for th in themes:
        g = groups.setdefault(th["e_code"] or "E-UNASSIGNED", {"theme_idx": [], "members": set()})
        g["theme_idx"].append(th["idx"])
        g["members"] |= set(th["members"])
    ecosystems = []
    for code in sorted(groups):
        g = groups[code]
        eco = {"code": code,
               "name": "Other" if code == "E-UNASSIGNED" else YAML_NAMES.get(code, code),
               "theme_idx": sorted(g["theme_idx"]), "n_members": len(g["members"])}
        for key, base in (("1d", lambda t: close_at(t, 1)), ("5d", lambda t: close_at(t, 5)),
                          ("21d", lambda t: close_at(t, 21)), ("ytd", ytd_base)):
            vals = [(close_at(m, 0) / base(m) - 1) * 100 for m in sorted(g["members"])
                    if close_at(m, 0) is not None and base(m) is not None]
            eco[f"ret_{key}"] = round(sum(vals) / len(vals), 2) if vals else None
            eco[f"n_{key}"] = len(vals)
            eco[f"up_{key}"] = sum(1 for v in vals if v > 0)
        ecosystems.append(eco)
    stocks = {t: [stage_of(t), ranks.get(t), sorted(member_of.get(t, []))]
              for t in sorted(set(universe) | set(member_of))}
    return {"as_of": str(as_of), "prev_session": str(prev), "prior_year_end": str(pye),
            "universe": {"n": len(universe)}, "highs_lows": hl, "adv_dec": ad, "stages": stg,
            "themes": themes, "ecosystems": ecosystems, "stocks": stocks}


def compare(got, want) -> list[str]:
    bad = []
    for k in ("as_of", "prev_session", "prior_year_end", "universe", "highs_lows", "adv_dec", "stages"):
        if got[k] != want[k]:
            bad.append(f"{k}: sql={got[k]} python={want[k]}")
    if len(got["themes"]) != len(want["themes"]):
        bad.append(f"themes: sql {len(got['themes'])} python {len(want['themes'])}")
    for g, w in zip(got["themes"], want["themes"]):
        for k, v in w.items():
            gv = g.get(k)
            if isinstance(v, float) and gv is not None and abs(float(gv) - v) <= 0.011:
                continue
            if gv != v:
                bad.append(f"theme {w['name']}.{k}: sql={gv} python={v}")
    if len(got["ecosystems"]) != len(want["ecosystems"]):
        bad.append(f"ecosystems: sql {len(got['ecosystems'])} python {len(want['ecosystems'])}")
    for g, w in zip(got["ecosystems"], want["ecosystems"]):
        for k, v in w.items():
            gv = g.get(k)
            if isinstance(v, float) and gv is not None and abs(float(gv) - v) <= 0.011:
                continue
            if gv != v:
                bad.append(f"ecosystem {w['code']}.{k}: sql={gv} python={v}")
        if set(g) != set(w):
            bad.append(f"ecosystem {w['code']} keys: sql {sorted(g)} python {sorted(w)}")
    if set(got["stocks"]) != set(want["stocks"]):
        bad.append(f"stocks keys differ: sql-only {sorted(set(got['stocks']) - set(want['stocks']))[:5]} "
                   f"python-only {sorted(set(want['stocks']) - set(got['stocks']))[:5]}")
    for t, w in want["stocks"].items():
        if t in got["stocks"] and got["stocks"][t] != w:
            bad.append(f"stock {t}: sql={got['stocks'][t]} python={w}")
    return bad


def run_correctness():
    days, rows, types = build_fixture()
    srv = pgserver.get_server(pathlib.Path(tempfile.mkdtemp()) / "pg")
    conn = psycopg2.connect(srv.get_uri())
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SHOW server_version")
    print("postgres", cur.fetchone()[0], "| fixture rows", len(rows), "| sessions in fixture",
          len([d for d in days if d != PARTIAL_MID]))
    ranks = load(cur, rows, types)
    cur.execute("BEGIN READ ONLY")
    t0 = time.time()
    cur.execute(SQL.strip().rstrip(";"))
    raw = cur.fetchone()[0]
    cur.execute("ROLLBACK")
    took = time.time() - t0
    text = json.dumps(raw)
    got = json.loads(text)
    want = recompute(rows, types, ranks)
    print(f"export ran in {took:.2f}s inside a READ ONLY transaction | {len(text):,} bytes")
    for k in ("version", "generated_at", "as_of", "prev_session", "prior_year_end", "score_date", "theme_membership",
              "universe", "highs_lows", "adv_dec", "stages"):
        print(f"  {k}: {got[k]}")
    print("  stages sum to universe:", sum(got["stages"].values()) == got["universe"]["n"])
    for th in got["themes"]:
        print("  theme", {k: th[k] for k in th if k != "members"}, "members", th["members"])
    for eco in got["ecosystems"]:
        print("  ecosystem", eco)
    for t in ("NEWHI", "NEWLO", "NULLLO", "ZEROLO", "ZEROHIST", "SHORTH", "GAPPY", "NOPRIOR", "UNCH", "PENNY", "ETF1",
              "IPO26", "S2UP", "S4DN", "S3TOP", "S1BASE", "NOBARS", "NOTYPE", "R0001"):
        print(f"  stock {t}: {got['stocks'].get(t, '(absent)')}")
    print("  definitions keys:", sorted(got["definitions"]))
    bad = compare(got, want)
    # The hand cases, stated directly (not via the recompute) so a shared misreading cannot hide.
    s = got["stocks"]
    hand = {
        "as_of skips the 2,900-row trailing day": got["as_of"] == "2026-11-03",
        "score_date skips the one-row stray day": got["score_date"] == "2026-11-03",
        "Beta not resurrected from its older row": all(t["name"] != "Beta" for t in got["themes"]),
        "Gamma (9 days old) excluded": all(t["name"] != "Gamma" for t in got["themes"]),
        "Delta carries its post-as_of membership": next(t for t in got["themes"] if t["name"] == "Delta")["members"]
                                                   == ["NEWHI", "R0007", "R0008"],
        "Alpha dedups R0002, keeps NOBARS as a member": next(
            t for t in got["themes"] if t["name"] == "Alpha")["n_members"] == 6,
        "Epsilon (no members) has null returns": next(
            t for t in got["themes"] if t["name"] == "Epsilon")["ret_1d"] is None,
        "Zeta carries its e_code": next(t for t in got["themes"] if t["name"] == "Zeta")["e_code"] == "E-AISEMI",
        "Eta (no mapping row) keeps a null e_code in themes[]": next(
            t for t in got["themes"] if t["name"] == "Eta")["e_code"] is None,
        "S2UP stage 2": s["S2UP"][0] == 2, "S4DN stage 4": s["S4DN"][0] == 4,
        "S3TOP stage 3": s["S3TOP"][0] == 3, "S1BASE stage 1": s["S1BASE"][0] == 1,
        "SHORTH unstaged": s["SHORTH"][0] is None, "GAPPY unstaged": s["GAPPY"][0] is None,
        "PENNY / ETF1 in stocks (members) but not the universe": "PENNY" in s and "ETF1" in s,
        "NOTYPE absent (not CS/ADRC, not a member)": "NOTYPE" not in s,
        "NOBARS present with stage null": s.get("NOBARS", [0])[0] is None,
    }
    # Removal deltas: drop ONE hand-made ticker, re-run the export, and read how the counts move. This checks each
    # high/low/adv-dec/stage case through the SQL's own aggregates (the stocks map carries no high/low flag).
    def counts_without(ticker):
        cur.execute("BEGIN")
        cur.execute("DELETE FROM mi_daily_closes WHERE ticker = %s", (ticker,))
        cur.execute(SQL.strip().rstrip(";"))
        out = cur.fetchone()[0]
        cur.execute("ROLLBACK")
        flat = {**out["highs_lows"], **out["adv_dec"], **{f"stage_{k}": v for k, v in out["stages"].items()}}
        base = {**got["highs_lows"], **got["adv_dec"], **{f"stage_{k}": v for k, v in got["stages"].items()}}
        return {k: flat[k] - base[k] for k in base if flat[k] != base[k]}

    expect_delta = {
        "NEWHI": {"eligible_n": -1, "new_highs": -1, "advances": -1, "stage_2": -1},
        "NEWLO": {"eligible_n": -1, "new_lows": -1, "declines": -1, "stage_4": -1},
        "NULLLO": {"declines": -1, "stage_4": -1},          # ineligible: its as_of low is NULL, never a new low
        "ZEROLO": {"declines": -1, "stage_4": -1},          # ineligible: its as_of low is 0, never a new low
        "ZEROHIST": {"eligible_n": -1, "new_lows": -1, "declines": -1, "stage_4": -1},  # zero lows excluded from min
        "GAPPY": {"advances": -1, "stage_unstaged": -1},    # 240 usable prior bars < 245; a gap inside 210
        "SHORTH": {"advances": -1, "stage_unstaged": -1},
        # NOPRIOR rises steadily and misses ONE prior bar (251 >= 245 usable): eligible, and a new high. Its 209 of 210
        # bars clear the 203 floor (relaxed 2026-11-04 from 'all 210'), so it is STAGED (a flat-ish rising line: 3).
        "NOPRIOR": {"eligible_n": -1, "new_highs": -1, "no_prior": -1, "stage_3": -1},
        # UNCH's as_of high TIES the previous session's high: "at or above" counts it as a new high.
        "UNCH": {"eligible_n": -1, "new_highs": -1, "unchanged": -1, "stage_3": -1},
    }
    # No session at all (security types gone -> no date reaches 3,000) must return ZERO rows, never an all-null object.
    cur.execute("BEGIN")
    cur.execute("DELETE FROM mi_security_types")
    cur.execute(SQL.strip().rstrip(";"))
    hand["no session -> the export returns zero rows"] = cur.fetchall() == []
    cur.execute("ROLLBACK")
    for t, exp in expect_delta.items():
        d = counts_without(t)
        hand[f"removing {t} moves exactly {exp}"] = d == exp
        if d != exp:
            print(f"    {t}: got delta {d}")
    # #722 — the group rules, stated directly (not via the recompute) so a shared misreading cannot hide.
    eco = {e["code"]: e for e in got["ecosystems"]}
    names = {t["name"]: t for t in got["themes"]}
    ai = eco.get("E-AISEMI", {})
    hand.update({
        "ecosystems: one entry per e_code present among the themes (+ E-UNASSIGNED for the unmapped one)":
            sorted(eco) == ["E-AISEMI", "E-CYBR", "E-UNASSIGNED", "E99"],
        "E-AISEMI counts R0001 ONCE (Alpha 6 + Zeta 3 members overlap on R0001 -> 8, not 9)":
            ai.get("n_members") == 8 and names["Alpha"]["n_members"] + names["Zeta"]["n_members"] == 9,
        "E-AISEMI lists both its themes by index": ai.get("theme_idx") == sorted(
            [names["Alpha"]["idx"], names["Zeta"]["idx"]]),
        "E-UNASSIGNED collects the unmapped theme AND the explicit one, R0009 once, printed 'Other'":
            eco["E-UNASSIGNED"]["n_members"] == 3 and eco["E-UNASSIGNED"]["name"] == "Other"
            and eco["E-UNASSIGNED"]["theme_idx"] == sorted([names["Eta"]["idx"], names["Theta"]["idx"]]),
        "a curated code prints its YAML name": ai.get("name") == "AI silicon & semiconductors",
        "an unknown code prints itself": eco["E99"]["name"] == "E99",
        "a group whose only theme has no members: zero members, null returns, still listed":
            eco["E-CYBR"]["n_members"] == 0 and eco["E-CYBR"]["ret_1d"] is None and eco["E-CYBR"]["n_1d"] == 0
            and eco["E-CYBR"]["up_1d"] == 0,
        "up_ never exceeds n_ and n_ never exceeds n_members": all(
            e[f"up_{w}"] <= e[f"n_{w}"] <= e["n_members"] for e in got["ecosystems"] for w in ("1d", "5d", "21d", "ytd")),
        "a theme's own numbers are untouched by the grouping (Alpha still has 6 members)":
            names["Alpha"]["n_members"] == 6,
    })
    for k, v in hand.items():
        print(f"  {'ok ' if v else 'BAD'} {k}")
        if not v:
            bad.append(k)
    print("\nRESULT:", "PASS — SQL matches the independent recompute on every field" if not bad
          else "FAIL\n  " + "\n  ".join(bad))
    return not bad


def run_scale():
    """Prod-shaped timing: ~11,000 tickers over ~5 years of weekdays, ~13.9M rows, both indexes, ANALYZEd."""
    srv = pgserver.get_server(pathlib.Path(tempfile.mkdtemp()) / "pg")
    conn = psycopg2.connect(srv.get_uri())
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(DDL)
    t0 = time.time()
    cur.execute("""
      INSERT INTO mi_daily_closes (trade_date, ticker, close, high_price, low_price)
      SELECT d::date, 'T' || lpad(g::text, 5, '0'), c, c * 1.01, c * 0.99
        FROM generate_series(DATE '2021-11-08', DATE '2026-11-03', interval '1 day') d,
             generate_series(1, 11000) g,
             LATERAL (SELECT 5 + (g % 200) + 20 * sin((extract(doy FROM d) + g) / 30.0) AS c) x
       WHERE extract(isodow FROM d) < 6
    """)
    cur.execute(INDEXES)
    cur.execute("""INSERT INTO mi_security_types (ticker, security_type)
                   SELECT 'T' || lpad(g::text, 5, '0'), CASE WHEN g % 10 = 0 THEN 'ETF' ELSE 'CS' END
                     FROM generate_series(1, 11000) g""")
    cur.execute("""INSERT INTO mi_themes (theme_date, name, stage, tickers)
                   SELECT DATE '2026-11-03', 'Theme ' || g, 'Accelerating',
                          ARRAY(SELECT 'T' || lpad((g * 37 + j)::text, 5, '0') FROM generate_series(1, 12) j)
                     FROM generate_series(1, 150) g""")
    cur.execute("""INSERT INTO mi_theme_ecosystems (theme_name, e_code)
                   SELECT 'Theme ' || g, (ARRAY['E-CYBR','E-AISEMI','E-BIO','E-ENER','E-UNASSIGNED'])[1 + g % 5]
                     FROM generate_series(1, 150) g""")
    cur.execute("""INSERT INTO mi_stock_scores (ticker, score_date, rs_rank)
                   SELECT 'T' || lpad(g::text, 5, '0'), DATE '2026-11-03' - b, g
                     FROM generate_series(1, 2400) g, generate_series(0, 9) b""")
    cur.execute("ANALYZE")
    cur.execute("SELECT count(*) FROM mi_daily_closes")
    n = cur.fetchone()[0]
    print(f"loaded {n:,} rows in {time.time() - t0:.0f}s")
    for attempt in (1, 2):
        t1 = time.time()
        cur.execute(SQL.strip().rstrip(";"))
        out = json.dumps(cur.fetchone()[0])
        print(f"run {attempt}: {time.time() - t1:.1f}s | {len(out):,} bytes")
    cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + SQL.strip().rstrip(";"))
    plan = "\n".join(r[0] for r in cur.fetchall())
    (pathlib.Path(__file__).parent / "scale_plan.txt").write_text(plan)
    print(plan.splitlines()[-2], "|", plan.splitlines()[-1])


if __name__ == "__main__":
    if "--scale" in sys.argv:
        run_scale()
    else:
        sys.exit(0 if run_correctness() else 1)
