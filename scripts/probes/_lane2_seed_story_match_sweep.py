"""#167 Lane-2 — seed-story vs ACTIVE-theme matcher: the calibration sweep that
said NO (2026-09-08, read-only, $0, no LLM).

Operator-approved rule under test: "before parking a name as a lane-2 seed, test
its story against the ACTIVE themes; if it matches one, join it instead of
seeding." A mechanical matcher (IDF-weighted distinctive-token overlap between the
seed's stored story and each active theme's name + thesis) is swept over the
labelled forward-era seeds:

  MUST FIRE      seeds that later joined a theme which ALREADY EXISTED on the seed
                 night and did NOT already hold the ticker
  MUST NOT FIRE  seeds that never joined any theme

Verdict on the 25 seeds of 2026-08-10 -> 09-03: NOT calibratable — see
docs/architecture/theme_engine.md change log 2026-09-08. Re-run this when the
labelled set has grown (the lane2_seed_birth_calibration review in
data_gated_reviews.yaml is the natural trigger); a rule that cannot separate the
labelled cases must not go live on a detection path.

The FOUR pulls (read-only; `\\pset format unaligned`, `\\pset fieldsep '\\t'`,
`\\pset tuples_only on`), run as
  ssh apollo@87.99.134.162 'docker exec -i apollo-postgres psql -U apollo -d apollo -f -' < q.sql > out.tsv

  seeds.tsv  SELECT run_date, name, tickers, thesis FROM mi_theme_candidates_shadow
             WHERE source='narrative_seed' ORDER BY run_date, name;
  narr.tsv   SELECT run_date, name, tickers, thesis FROM mi_theme_candidates_shadow
             WHERE source='narrative_cogap' ORDER BY name, run_date;
  live.tsv   SELECT theme_date, name, stage, tickers,
                    regexp_replace(coalesce(description,''), E'[\\\\n\\\\r\\\\t]+', ' ', 'g'), source
             FROM mi_themes WHERE theme_date >= '<first seed date - 8 days>' ORDER BY theme_date, name;
  born.tsv   SELECT name, min(theme_date), max(theme_date), count(*) FROM mi_themes
             GROUP BY name ORDER BY min(theme_date);

Usage: python scripts/probes/_lane2_seed_story_match_sweep.py [--dir /tmp]
"""
from __future__ import annotations

import argparse
import math
import re
from collections import Counter
from datetime import date, timedelta

_STOP = set("""a an the and or of to in on for with by at from as is are was were be been being this that
these those it its their his her they them we our you your ahead plus also into over under after before
during than then via per amid new q1 q2 q3 q4 fy fy25 fy26 fy27 h1 h2 today monday tuesday wednesday
thursday friday week yoy""".split())


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _arr(s: str) -> list[str]:
    return [t for t in s.strip("{}").split(",") if t]


def _rows(path: str, ncols: int, date_col: int = 0) -> list[list[str]]:
    """psql unaligned TSV -> rows; skips the `\\pset` echo lines by requiring a date in `date_col`."""
    out = []
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= ncols and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p[date_col] or ""):
            out.append(p)
    return out


def load(d: str):
    seeds = [dict(sd=_d(p[0]), ticker=_arr(p[2])[0], story=p[3]) for p in _rows(f"{d}/seeds.tsv", 4)]
    narr = [dict(td=_d(p[0]), name=p[1], tickers=_arr(p[2]), desc=p[3]) for p in _rows(f"{d}/narr.tsv", 4)]
    live = [dict(td=_d(p[0]), name=p[1], stage=p[2], tickers=_arr(p[3]), desc=p[4])
            for p in _rows(f"{d}/live.tsv", 5)]
    born = {p[0]: _d(p[1]) for p in _rows(f"{d}/born.tsv", 4, date_col=1)}
    return seeds, narr, live, born


def tokens(s: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", s.lower()):
        if w in _STOP or len(w) < 2:
            continue
        for suf in ("ings", "ing", "ies", "es", "s"):  # light stem
            if len(w) > 4 and w.endswith(suf):
                w = w[: -len(suf)] + ("y" if suf == "ies" else "")
                break
        out.append(w)
    return out


def live_roster(live, asof: date, days: int = 7, include_same_day: bool = True):
    """get_active_themes semantics: latest row per name within `days`, drop Retired."""
    lo = asof - timedelta(days=days)
    latest: dict[str, dict] = {}
    for r in live:
        if r["td"] < lo or r["td"] > asof or (r["td"] == asof and not include_same_day):
            continue
        if r["name"] not in latest or r["td"] > latest[r["name"]]["td"]:
            latest[r["name"]] = r
    return [r for r in latest.values() if r["stage"] != "Retired"]


def lane2_roster(narr, asof: date, trading_days: int = 10):
    """get_lane2_active_narratives semantics: latest row per name, prior sessions only,
    LANE2_WINDOW_TRADING_DAYS back (weekday approximation — holidays ignored)."""
    n, cur = 0, asof
    while n < trading_days:
        cur -= timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    latest: dict[str, dict] = {}
    for r in narr:
        if cur <= r["td"] < asof and (r["name"] not in latest or r["td"] > latest[r["name"]]["td"]):
            latest[r["name"]] = r
    return list(latest.values())


def label(seeds, live, born):
    """Per seed: first LATER live theme holding the ticker, whether that theme pre-dated the
    seed, and whether the ticker was ALREADY on the seed-night board (the membership fact
    the original read missed)."""
    out = {}
    for s in seeds:
        tk, sd = s["ticker"], s["sd"]
        same = [r["name"] for r in live if r["td"] == sd and tk in r["tickers"] and r["stage"] != "Retired"]
        later = sorted((r for r in live if r["td"] > sd and tk in r["tickers"] and r["stage"] != "Retired"),
                       key=lambda r: r["td"])
        first = later[0] if later else None
        pre = bool(first and born.get(first["name"], first["td"]) < sd)
        in_roster = bool(first and first["name"] in {r["name"] for r in live_roster(live, sd)})
        out[tk] = dict(first=first and first["name"], lag=first and (first["td"] - sd).days,
                       born=first and born.get(first["name"]), pre_existing=pre,
                       in_roster=in_roster, already_member=same)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/tmp")
    a = ap.parse_args()
    seeds, narr, live, born = load(a.dir)
    lab = label(seeds, live, born)

    print("== LABELS (first later live theme holding the ticker; born; already on the seed-night board)")
    for s in seeds:
        L = lab[s["ticker"]]
        print(f"{s['sd']} {s['ticker']:5s} joined={str(L['first'])[:48]:48s} lag={L['lag']} born={L['born']} "
              f"pre_existing={L['pre_existing']} already_member={L['already_member']}")
    never = {t for t, L in lab.items() if L["first"] is None}
    positives = {t for t, L in lab.items() if L["pre_existing"] and L["in_roster"] and not L["already_member"]}
    print(f"\nnever joined: {len(never)} {sorted(never)}")
    print(f"already on the board when parked (same theme_date): "
          f"{sorted(t for t, L in lab.items() if L['already_member'])}")
    print("  ⚠ same theme_date is NOT 'before the lane-2 decision': the board row can land AFTER it "
          "(NESR 08-10 +2.5 min, LPTH 08-14 +62 ms). Compare mi_themes.created_at with the "
          "lane2_decision_record created_at before counting a name as already-held; on the "
          "2026-09-08 read only HOOD, OMER, MRNA were on the board first.")
    print(f"MUST-FIRE (pre-existing theme, not yet a member): {sorted(positives)}")

    # IDF background = latest description per live theme name
    latest: dict[str, dict] = {}
    for r in live:
        if r["name"] not in latest or r["td"] > latest[r["name"]]["td"]:
            latest[r["name"]] = r
    docs = [set(tokens(r["name"] + " " + r["desc"])) for r in latest.values()]
    n_docs, df = len(docs), Counter(t for d_ in docs for t in d_)

    def idf(t):
        return math.log((n_docs + 1) / (df.get(t, 0) + 1))

    def score(story, theme, min_idf):
        st = {t for t in tokens(story) if idf(t) >= min_idf}
        th = {t for t in tokens(theme["name"] + " " + theme["desc"]) if idf(t) >= min_idf}
        shared = st & th
        return (sum(idf(t) for t in shared) / sum(idf(t) for t in st) if st else 0.0), shared

    def sweep(roster_fn, title, must_fire):
        print(f"\n#### roster = {title}   must-fire = {sorted(must_fire)}")
        for mi in (0.0, 1.5, 2.5, 3.5):
            for thr in (0.15, 0.25, 0.35, 0.50):
                fired = {}
                for s in seeds:
                    hits = [(sc, th["name"], sorted(sh)) for th in roster_fn(s["sd"])
                            for sc, sh in [score(s["story"], th, mi)] if sc >= thr and sh]
                    if hits:
                        fired[s["ticker"]] = max(hits)
                tp = [t for t in fired if t in must_fire]
                fp = [t for t in fired if t in never]
                print(f"min_idf={mi:.1f} thr={thr:.2f}  fires={len(fired):2d}/25  must-fire caught={len(tp)}/{len(must_fire)}"
                      f"  never-joined fired={len(fp)}/{len(never)}  missed={sorted(must_fire - set(fired))}")
                if thr == 0.15 and mi == 0.0:
                    for t, (sc, nm, sh) in sorted(fired.items(), key=lambda kv: -kv[1][0]):
                        tag = "TP" if t in must_fire else ("FP" if t in never else "joiner")
                        print(f"      {tag:6s} {t:5s} {sc:.2f} -> {nm[:52]} | shared={sh}")

    sweep(lambda sd: live_roster(live, sd), "LIVE mi_themes board (same-day rows included)", positives)
    l2_pos = {s["ticker"] for s in seeds
              if any(r["td"] > s["sd"] and s["ticker"] in r["tickers"]
                     and r["name"] in {x["name"] for x in lane2_roster(narr, s["sd"])} for r in narr)}
    sweep(lambda sd: lane2_roster(narr, sd), "LANE-2 narratives (the `active` param of _lane2_registry_clean)", l2_pos)

    print("\n== Can a threshold rescue the must-fire cases? (target theme's score and rank on its board)")
    for s in seeds:
        L = lab[s["ticker"]]
        if not (L["pre_existing"] and L["in_roster"]):
            continue
        ros = live_roster(live, s["sd"])
        tgt = next((r for r in ros if r["name"] == L["first"]), None)
        if tgt is None:
            continue
        for mi in (0.0, 2.5):
            sc, sh = score(s["story"], tgt, mi)
            allsc = sorted((score(s["story"], r, mi)[0] for r in ros), reverse=True)
            print(f"{s['ticker']} min_idf={mi}: target={sc:.2f} shared={sorted(sh)} rank={allsc.index(sc) + 1}/{len(ros)} best={allsc[0]:.2f}")

    print("\n== Sector-is-not-a-theme check: never-joined biotech seeds vs biotech-worded board themes")
    for s in seeds:
        if s["ticker"] not in never:
            continue
        ros = live_roster(live, s["sd"])
        bio = [r for r in ros if re.search(r"oncolog|biotech|pharma|therap|clinical|phase", (r["name"] + " " + r["desc"]).lower())]
        if not re.search(r"phase|trial|drug|readout|oncolog", s["story"].lower()):
            continue
        best = sorted(((score(s["story"], r, 0.0)[0], r["name"], sorted(score(s["story"], r, 0.0)[1])) for r in bio), reverse=True)[:1]
        print(f"{s['ticker']:5s} ({len(bio)} biotech-worded themes) best={[(f'{b[0]:.2f}', b[1][:40], b[2]) for b in best]}")


if __name__ == "__main__":
    main()
