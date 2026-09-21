"""#577b — the 50-75% extension band, re-read on 2026-09-21 (READ-ONLY; THE LINE holds).

Gated review `extension_cap_75_recheck`. The band is ENTRY DISCIPLINE: this probe
MEASURES and proposes nothing.

POPULATION, derived (never hand-listed):
  mi_ep_missed_outcomes WHERE skip_category='extension_gate'
    AND extension parsed from skip_reason IN [50,75)          <- the band, which the
        live 50% cap SKIPS and the reverted 75% cap admitted
    AND setup_at_open IS TRUE      (#595 — a real setup at the bell, not a PM fade)
    AND ret_5d IS NOT NULL         (scoreable)

METHOD = the 2026-08-29 read's, so the two are comparable:
  entry = stop-limit buy at the 9:30 bar's HIGH (live two-floor buffer), submission
  9:31 ET, 10:00 ET unfilled-cancel; stop = that bar's LOW, broker stop (intraday
  touch), live past day 0. Arms:
    PLAIN  no partial, hard stop only        <- the 08-29 headline arm (-1.00R x15)
    LIVE   1/3 at +2R + breakeven + SMA trail (the 08-16..09-05 stack)
  MFE-in-R reported alongside realized-R: the 08-29 finding was the GAP between them.

Bars: reuses the _ext_*.tsv caches (2026-08-16 pull) + /tmp/ext_extra.tsv for the
three (ticker,date) the cache predates. No paid re-pull of what we already hold.
"""
from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))

import _468_moderate_realized_r as M      # noqa: E402  (reused verbatim)
import _ext_live_exit_replay as X         # noqa: E402  (arms A/C simulate())

HOST = "apollo@87.99.134.162"
EXTRA = HERE / "_577b_extra_bars.tsv"
COHORT_OUT = HERE / "_577b_cohort.psv"

BAND_SQL = (
    "SELECT ticker, alert_date, "
    "(substring(skip_reason from 'already up (-?[0-9]+)% in prior 5 days'))::numeric AS ext, "
    "round(ret_5d::numeric,4), round(max_high_5d::numeric,4), "
    "last_refreshed_at::date "
    "FROM mi_ep_missed_outcomes "
    "WHERE skip_category = 'extension_gate' AND setup_at_open IS TRUE "
    "AND ret_5d IS NOT NULL "
    "AND (substring(skip_reason from 'already up (-?[0-9]+)% in prior 5 days'))::numeric >= 50 "
    "AND (substring(skip_reason from 'already up (-?[0-9]+)% in prior 5 days'))::numeric < 75 "
    "ORDER BY alert_date"
)


def pull_band() -> list[dict]:
    s = " ".join(BAND_SQL.split())
    assert s.upper().startswith("SELECT")
    remote = f"docker exec -i apollo-postgres psql -U apollo -d apollo -tAX -c \"{s}\""
    out = subprocess.run(["ssh", "-o", "ConnectTimeout=25", HOST, remote],
                         capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[:400])
    COHORT_OUT.write_text(out.stdout, encoding="utf-8")
    rows = []
    for ln in out.stdout.splitlines():
        p = ln.split("|")
        if len(p) < 6 or not p[0]:
            continue
        rows.append({"ticker": p[0], "alert_date": p[1], "ext": float(p[2]),
                     "ret_5d": float(p[3]), "mfe_5d": float(p[4]), "refreshed": p[5]})
    return rows


def load_bars():
    M.DAILY, M.MINUTE = HERE / "_ext_daily.tsv", HERE / "_ext_minute.tsv"
    daily, minute = M.load_daily(), M.load_minute()
    from datetime import datetime, timedelta, timezone
    for ln in EXTRA.read_text(encoding="utf-8").splitlines():
        p = ln.split("\t")
        if len(p) < 8 or p[0].startswith("#"):
            continue
        if p[0] == "D":
            daily[p[1]].append({"date": p[2], "o": float(p[3]), "h": float(p[4]),
                                "l": float(p[5]), "c": float(p[6]), "v": float(p[7])})
        elif p[0] == "M":
            tms = int(p[2])
            et = datetime.fromtimestamp(tms / 1000, timezone.utc) - timedelta(hours=4)
            minute[(p[1], et.date().isoformat())].append(
                {"t": tms, "o": float(p[3]), "h": float(p[4]), "l": float(p[5]),
                 "c": float(p[6]), "v": float(p[7])})
    for tk in daily:                       # dedupe + resort after the merge
        seen, keep = set(), []
        for b in sorted(daily[tk], key=lambda x: x["date"]):
            if b["date"] in seen:
                continue
            seen.add(b["date"])
            keep.append(b)
        daily[tk] = keep
    return daily, minute


def mfe_r(entry, stop, day0_after_fill, fwd, n_days):
    """Best price touched, in R, over day 0 (minute) + n_days forward daily bars."""
    risk = entry - stop
    if risk <= 0:
        return None
    hi = max([b["h"] for b in day0_after_fill] or [entry])
    for d in fwd[:n_days]:
        hi = max(hi, d["h"])
    return (hi - entry) / risk


def replay(band, daily, minute, fill_end_m):
    """Walk the band through the live bracket with the 10:00 ET unfilled-cancel set
    to fill_end_m. 600 = the LIVE rule; a later value is the sensitivity arm."""
    saved = M.FILL_END
    M.FILL_END = fill_end_m
    rows, skipped = [], {}
    try:
        for r in band:
            tk, ad = r["ticker"], r["alert_date"]
            db = daily.get(tk, [])
            i = M.idx_of_date(db, ad)
            raw = minute.get((tk, ad), [])
            if i is None or not raw:
                skipped[f"{tk} {ad}"] = "no_bars"; continue
            rth = M.de.polygon_to_rth_minutes(raw, ad)
            if not rth:
                skipped[f"{tk} {ad}"] = "no_rth"; continue
            rec = M.reconstruct(rth, M.SUBMIT_MIN, M.atr14_prior_close(db, i), db[i:])
            orbs = [b for b in rth if 570 <= b["m"] < 575]
            orb = orbs[0] if orbs else None
            fwd = db[i + 1:]
            # MFE measured from the ORB HIGH regardless of whether we filled — the
            # "what the name did" column, which is what the 08-23 review's +58% was.
            mfe_ah = None
            if orb and orb["h"] > orb["l"]:
                after_all = [b for b in rth if b["m"] >= 571]
                mfe_ah = mfe_r(orb["h"], orb["l"], after_all, fwd, 5)
            if rec.get("outcome") != "filled":
                skipped[f"{tk} {ad}"] = str(rec.get("outcome"))
                rows.append({**r, "filled": False, "outcome": rec.get("outcome"),
                             "plain": None, "live": None, "mfe5": None,
                             "mfe_at_orb_high_5d": mfe_ah, "fwd_days": len(fwd)})
                continue
            fm = rec["fill_minute"]
            after = [b for b in rth if b["m"] >= fm]
            prior = [b["c"] for b in db[:i]]
            rows.append({**r, "filled": True, "outcome": "filled",
                         "entry": rec["entry"], "stop": rec["stop"], "fill_m": fm,
                         "fwd_days": len(fwd),
                         "plain": X.simulate(rec["entry"], rec["stop"], after, fwd, prior,
                                             use_partial=False, use_trail=False),
                         "live": X.simulate(rec["entry"], rec["stop"], after, fwd, prior,
                                            use_partial=True, use_trail=True),
                         "mfe5": mfe_r(rec["entry"], rec["stop"], after, fwd, 5),
                         "mfe20": mfe_r(rec["entry"], rec["stop"], after, fwd, 20),
                         "mfe_at_orb_high_5d": mfe_ah})
    finally:
        M.FILL_END = saved
    return rows, skipped


def main():
    band = pull_band()
    daily, minute = load_bars()
    live_rows, live_skip = replay(band, daily, minute, 600)      # LIVE: 10:00 ET cancel
    late_rows, _ = replay(band, daily, minute, 930)              # sensitivity: 15:30 cutoff

    print("=" * 100)
    print("#577b - 50-75% EXTENSION BAND, LIVE BRACKET REPLAY (read-only, 2026-09-21)")
    print("=" * 100)
    print(f"band population derived from prod: n={len(band)}")
    f = [r for r in live_rows if r["filled"]]
    print(f"filled under the LIVE bracket (stop-buy at 9:30 high, 10:00 ET unfilled-cancel): {len(f)}/{len(band)}")
    for k, v in sorted(live_skip.items()):
        print(f"   not filled: {k:18} {v}")
    print("")
    hdr = (f"{'ticker':7}{'date':12}{'ext%':>5}{'filled':>7}{'PLAIN R':>9}{'LIVE R':>9}"
           f"{'MFE5 R':>8}{'MFE@ORBhi5d':>12}{'ret5d':>8}{'peak5d':>8}{'fwdD':>6}")
    print(hdr)
    for r in sorted(live_rows, key=lambda x: x["alert_date"]):
        fm = lambda v, w=9, s2="+.2f": (format(v, s2).rjust(w) if v is not None else "-".rjust(w))
        print(f"{r['ticker']:7}{r['alert_date']:12}{r['ext']:>5.0f}"
              f"{('Y' if r['filled'] else 'n'):>7}{fm(r['plain'])}{fm(r['live'])}"
              f"{fm(r['mfe5'],8)}{fm(r['mfe_at_orb_high_5d'],12)}"
              f"{r['ret_5d']*100:>7.0f}%{r['mfe_5d']*100:>7.0f}%{r['fwd_days']:>6}")
    print("")
    for key, label in (("plain", "PLAIN  no partial, hard stop only  (the 08-29 headline arm)"),
                       ("live", "LIVE   1/3 at +2R, breakeven, SMA trail")):
        v = sorted(x[key] for x in f)
        n = len(v)
        print(label)
        print(f"   n={n}  mean {sum(v)/n:+.2f}R  median {M._median(v):+.2f}R  best {v[-1]:+.2f}R  SUM {sum(v):+.1f}R")
        print(f"   winners(>0R) {sum(1 for x in v if x > 0)}/{n}   full stop-outs(<=-0.99R) {sum(1 for x in v if x <= -0.99)}/{n}")
    print("")
    lf = [r for r in late_rows if r["filled"]]
    lv = sorted(x["plain"] for x in lf)
    print(f"SENSITIVITY - fills allowed to 15:30 ET instead of the live 10:00 cancel: "
          f"{len(lf)}/{len(band)} fill, mean {sum(lv)/len(lv):+.2f}R, "
          f"winners {sum(1 for x in lv if x > 0)}/{len(lv)}")
    print("")
    ah = [r["mfe_at_orb_high_5d"] for r in live_rows if r["mfe_at_orb_high_5d"] is not None]
    print(f"WHAT THE NAMES DID (MFE from the 9:30 high, in R, 5 sessions, fill or not): n={len(ah)}")
    print(f"   median {M._median(ah):+.2f}R   >=2R {sum(1 for x in ah if x >= 2)}/{len(ah)}   "
          f">=5R {sum(1 for x in ah if x >= 5)}/{len(ah)}   max {max(ah):+.2f}R")
    print("   ^ MFE is the best price touched, not money kept.")


if __name__ == "__main__":
    main()
