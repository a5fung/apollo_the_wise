"""#577 ADVERSARIAL VERIFY (2026-09-21) — re-run the 50-75% extension band under the
STOP GEOMETRY THAT IS ACTUALLY LIVE.  READ-ONLY.  THE LINE holds: measures only.

WHY. The reviewed read replayed the band with `stop = the 9:30 bar's LOW`.  That is
era_b geometry, retired 2026-08-16.  Primary sources, three:
  * agents/market_intelligence/broker/order_manager.py:617  (and the same line inside
    the RUNNING apollo-market image):   stop_loss_price = 2 * orb_low - orb_high
  * rule_eras.exit_rules_as_of -> stop_mode 'entry_minus_2r' for any d >= 2026-08-16
  * CLAUDE.md: "stop `entry - 2R`, R = entry - ORB low - NOT the ORB low"

FRAMES (the two R's, which is where this is easy to get wrong):
  stop distance / dollar-risk denominator  = orb_high - stop = 2*(orb_high - orb_low)
  target + breakeven trigger frame         = entry - orb_low   (ORB R; live
      order_manager.profit_target_r_per_share for _ORB_R_FRAME_SIGNAL_TYPES)
  The live comment is explicit that the +NR target does NOT move with the stop.

ARMS (rule_eras):
  era_b  stop = orb_low,                 partial 1/3 @ +2 ORB-R, be at partial   <- what was reviewed
  era_c  stop = 2*orb_low - orb_high,    partial 1/3 @ +2 ORB-R, be at partial
  era_d  stop = 2*orb_low - orb_high,    partial 1/3 @ +8 ORB-R, be arms +3 ORB-R  <- LIVE TODAY
  era_d_nolad  stop = 2*orb_low - orb_high, hard stop only
Realized R is reported in that arm's OWN risk denominator (= dollar risk), so the
arms are comparable at equal dollar risk, which is how the live sizer places them.
"""
from __future__ import annotations
import subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent.parent))
import _468_moderate_realized_r as M   # noqa: E402  fill walk + bar loaders, reused verbatim

HOST = "apollo@87.99.134.162"
HORIZON = 20

BAND_SQL = (
  "SELECT ticker, alert_date, "
  "(substring(skip_reason from 'already up ([0-9.]+)%'))::numeric AS ext, "
  "round(ret_5d::numeric,4), round(max_high_5d::numeric,4) "
  "FROM mi_ep_missed_outcomes "
  "WHERE skip_category='extension_gate' AND setup_at_open IS TRUE AND ret_5d IS NOT NULL "
  "AND (substring(skip_reason from 'already up ([0-9.]+)%'))::numeric >= 50 "
  "AND (substring(skip_reason from 'already up ([0-9.]+)%'))::numeric < 75 "
  "ORDER BY alert_date")


def pull(sql):
    s = " ".join(sql.split()); assert s.upper().startswith("SELECT")
    r = subprocess.run(["ssh","-o","ConnectTimeout=25",HOST,
        f"docker exec -i apollo-postgres psql -U apollo -d apollo -tAX -c \"{s}\""],
        capture_output=True, text=True, timeout=180)
    if r.returncode: raise RuntimeError(r.stderr[:400])
    return [l.split("|") for l in r.stdout.splitlines() if l.strip()]


def load_bars():
    M.DAILY, M.MINUTE = HERE/"_ext_daily.tsv", HERE/"_ext_minute.tsv"
    daily, minute = M.load_daily(), M.load_minute()
    from datetime import datetime, timedelta, timezone
    for ln in (HERE/"_577b_extra_bars.tsv").read_text().splitlines():
        p = ln.split("\t")
        if len(p) < 8 or p[0].startswith("#"): continue
        if p[0] == "D":
            daily[p[1]].append({"date":p[2],"o":float(p[3]),"h":float(p[4]),
                                "l":float(p[5]),"c":float(p[6]),"v":float(p[7])})
        elif p[0] == "M":
            t = int(p[2]); et = datetime.fromtimestamp(t/1000, timezone.utc) - timedelta(hours=4)
            minute[(p[1], et.date().isoformat())].append(
                {"t":t,"o":float(p[3]),"h":float(p[4]),"l":float(p[5]),"c":float(p[6]),"v":float(p[7])})
    for tk in daily:
        seen, keep = set(), []
        for b in sorted(daily[tk], key=lambda x: x["date"]):
            if b["date"] in seen: continue
            seen.add(b["date"]); keep.append(b)
        daily[tk] = keep
    return daily, minute


def fill_walk(rth, atr14):
    """Live fill only: first 9:30-9:35 bar -> validate -> stop-limit buy, 10:00 cancel.
    Mirrors _468.reconstruct's entry half; we do NOT use its r/stop (it simulates vs orb_low)."""
    cands = [b for b in rth if M.RTH_OPEN <= b["m"] < M.ORB_FETCH_END]
    if not cands: return {"outcome":"no_orb_bar"}
    orb = cands[0]; hi, lo = orb["h"], orb["l"]
    ok, why = M.validate_orb_entry(hi, lo, atr14)
    if not ok: return {"outcome": why.split(":")[1], "hi":hi, "lo":lo}
    limit = M.stop_limit_buy_price(hi)
    scan_from = max(M.SUBMIT_MIN, orb["m"]+1)
    fill_px = fill_m = None; armed = False
    for b in rth:
        if b["m"] < scan_from: continue
        if b["m"] >= M.FILL_END: break
        if armed:
            if b["l"] <= limit: fill_px, fill_m = limit, b["m"]; break
            continue
        if b["h"] >= hi:
            if b["o"] <= hi: fill_px, fill_m = hi, b["m"]
            elif b["o"] <= limit: fill_px, fill_m = b["o"], b["m"]
            else: armed = True; continue
            break
    if fill_px is None: return {"outcome":"no_fill", "hi":hi, "lo":lo}
    return {"outcome":"filled", "entry":fill_px, "fill_m":fill_m, "hi":hi, "lo":lo}


def sma(c, n): return sum(c[-n:])/n if len(c) >= n else None


def sim(hi, lo, entry, day0, fwd, prior, *, stop_mode, partial_r, be_arm_r,
        be_at_partial=True, trail=True, frac=1/3):
    """Returns realized R in the arm's own dollar-risk denominator, or None if unplaceable."""
    stop0 = lo if stop_mode == "orb_low" else 2*lo - hi
    if stop0 <= 0 or stop0 >= entry: return None      # live reject (2R stop <= $0)
    denom = hi - stop0                                 # live sizer's risk_per_share
    rframe = entry - lo                                # ORB R: target/breakeven frame
    if rframe <= 0 or denom <= 0: return None
    held, banked, stop, done = 1.0, 0.0, stop0, False
    tgt_p = entry + partial_r*rframe if partial_r else None
    tgt_be = entry + be_arm_r*rframe if be_arm_r else None
    for b in day0:
        if b["l"] <= stop: return banked + held*(stop-entry)/denom
        if tgt_be and b["h"] >= tgt_be: stop = max(stop, entry)
        if not done and tgt_p and b["h"] >= tgt_p:
            banked += frac*(tgt_p-entry)/denom; held -= frac; done = True
            if be_at_partial: stop = max(stop, entry)
    closes = list(prior) + ([day0[-1]["c"]] if day0 else [])
    for d in fwd[:HORIZON]:
        eff = stop
        if trail:
            s10, s20 = sma(closes,10), sma(closes,20)
            line = max([x for x in (s10,s20) if x is not None], default=None)
            if line is not None and line > eff: eff = line
        if d["l"] <= stop: return banked + held*(stop-entry)/denom
        if tgt_be and d["h"] >= tgt_be: stop = max(stop, entry)
        if not done and tgt_p and d["h"] >= tgt_p:
            banked += frac*(tgt_p-entry)/denom; held -= frac; done = True
            if be_at_partial: stop = max(stop, entry)
        if trail and d["c"] < eff: return banked + held*(d["c"]-entry)/denom
        closes.append(d["c"])
    last = fwd[:HORIZON][-1]["c"] if fwd[:HORIZON] else entry
    return banked + held*(last-entry)/denom


ARMS = {
 "era_b  ORB-low stop, 1/3@+2R, be@partial   <-REVIEWED": dict(stop_mode="orb_low", partial_r=2.0, be_arm_r=None),
 "era_c  2R stop,      1/3@+2R, be@partial":              dict(stop_mode="entry_minus_2r", partial_r=2.0, be_arm_r=None),
 "era_d  2R stop,      1/3@+8R, be ARMS@+3R  <-LIVE":     dict(stop_mode="entry_minus_2r", partial_r=8.0, be_arm_r=3.0),
 "era_d  2R stop,      no ladder (hard stop only)":       dict(stop_mode="entry_minus_2r", partial_r=None, be_arm_r=None, trail=False),
 "era_b  ORB-low stop, no ladder (hard stop only)":       dict(stop_mode="orb_low", partial_r=None, be_arm_r=None, trail=False),
}


def run(pairs, label, daily, minute, detail=False):
    res = {k: [] for k in ARMS}; filled = 0; skips = {}; rows = []
    for tk, ad in pairs:
        db = daily.get(tk, []); i = M.idx_of_date(db, ad); raw = minute.get((tk, ad), [])
        if i is None or not raw: skips[f"{tk} {ad}"] = "no_bars"; continue
        rth = M.de.polygon_to_rth_minutes(raw, ad)
        if not rth: skips[f"{tk} {ad}"] = "no_rth"; continue
        rec = fill_walk(rth, M.atr14_prior_close(db, i))
        if rec["outcome"] != "filled": skips[f"{tk} {ad}"] = rec["outcome"]; continue
        filled += 1
        day0 = [b for b in rth if b["m"] >= rec["fill_m"]]
        prior = [b["c"] for b in db[:i]]; fwd = db[i+1:]
        r = {"tk":tk,"ad":ad}
        for k, kw in ARMS.items():
            v = sim(rec["hi"], rec["lo"], rec["entry"], day0, fwd, prior, **kw)
            if v is not None: res[k].append(v); r[k] = v
        rows.append(r)
    print(f"\n### {label}  — candidates {len(pairs)}, filled {filled}")
    if skips: print("   not filled:", ", ".join(f"{k}={v}" for k, v in sorted(skips.items())))
    for k in ARMS:
        v = sorted(res[k]); n = len(v)
        if not n: continue
        print(f"   {k:52} n={n} mean {sum(v)/n:+.2f}R median {M._median(v):+.2f}R "
              f"best {v[-1]:+.2f}R SUM {sum(v):+.1f}R winners {sum(1 for x in v if x>0)}/{n}")
    if detail:
        ks = list(ARMS)
        print(f"\n   {'ticker':7}{'date':12}" + "".join(f"{k.split()[0]+k.split()[1][:6]:>14}" for k in ks))
        for r in rows:
            print(f"   {r['tk']:7}{r['ad']:12}" + "".join(
                (f"{r[k]:+14.2f}" if k in r else f"{'-':>14}") for k in ks))
    return rows


def main():
    band = [(p[0], p[1]) for p in pull(BAND_SQL)]
    print("="*112)
    print("#577 VERIFY — 50-75%% EXTENSION BAND under LIVE vs REVIEWED stop geometry (read-only)")
    print("="*112)
    print(f"band population re-derived from prod: n={len(band)}")
    daily, minute = load_bars()
    run(band, "50-75 BAND (prod-derived, setup_at_open TRUE, scoreable)", daily, minute, detail=True)

    # the >=75% still-skipped tail, same cache the reviewed read used
    ext, so = {}, {}
    for ln in open(HERE/"_577b_mo_ext.psv"):
        p = ln.rstrip("\n").split("|")
        if len(p) < 4 or not p[0] or not p[2]: continue
        ext[(p[0],p[1])] = float(p[2]); so[(p[0],p[1])] = (p[3] == "t")
    M.COHORT = HERE/"_ext_cohort.tsv"
    rows = M.load_cohort()
    p75 = [(r["ticker"], r["alert_date"]) for r in rows if ext.get((r["ticker"],r["alert_date"]), -1) >= 75]
    run(p75, ">=75%% still-skipped, 08-16 cache, ALL", daily, minute)
    run([k for k in p75 if so.get(k)], ">=75%% still-skipped, real setups at the open only", daily, minute)


if __name__ == "__main__":
    main()
