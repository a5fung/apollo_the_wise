#!/usr/bin/env python3
"""Price and corporate-action integrity audit for a daily-bar export (ticker,date,open,high,low,close,volume; no header).

Built 2026-10-23 for #705 after OPLN (a spin-off, read as a -34R loss) showed the exports carry artifacts no one had classified.
READ-ONLY on the export. No network. Rows dated after --cutoff (default 2024-12-31, the sealed-table boundary) are DROPPED WHILE
STREAMING and never inspected; going past the cutoff needs --allow-sealed and is not for any outcome-adjacent use.

Usage
  python price_integrity_check.py --export /path/daily_closes_all.csv.gz --label A --out-dir OUT \\
      [--splits cb702_splits.psv] [--raw-close daily_raw_close.csv.gz] [--sectype small_pulls.psv] [--compare OTHER_EXPORT --compare-label B] [--selftest]

Checks (each prints counts WITH n; flagged rows go to OUT/<label>_flags.tsv, counts to OUT/<label>_summary.tsv)
  ohlc            high < max(open, close), low > min(open, close), high < low, non-positive prices, NaN
  level           split-adjusted price levels no trade could ever print (history rescaled by later reverse splits)
  gap             one-session moves >= 25% either way (open gap OR close-to-close), classed: known adjustment event /
                  open-only-reverted / reverted next session / reverted within 5 / persistent / no next bar
  adj_event       every KNOWN adjustment event (listed splits via --splits, or steps in raw/adjusted via --raw-close): is the
                  adjusted series continuous across it? A discontinuity = a factor applied with no matching raw move (spin-off /
                  distribution booked as a split) or a split not applied
  splitlike       ratios within 5% of 2,3,4,5,10,20 or their reciprocals with NO known event within one bar; volume-confirmed
                  when median volume re-levels by ~1/ratio and stays there (a real crash decays; a split does not)
  spinoff         persistent down moves >= 25% with a volume spike (CANDIDATES only - an earnings crash also qualifies); a
                  new listing within -2..+1 sessions whose first open is within 25% of the parent's dollar drop is a child match
  calendar        per-ticker missing sessions against the calendar ticker (SPY); partial-session breadth
  volume          zero volume (flat fill vs price change vs adjusted-volume underflow at huge price levels)
  wick            high or low print >= 1.5x away from open/close
  test_symbol     exchange test tickers (ZVZZT, ZTEST, NTEST ...)
  duplicate       distinct tickers whose bars are byte-identical (renames / de-SPACs carried under two symbols)
  compare         with --compare: overlap-window close ratio per ticker (adjustment-epoch and identity differences)

Positive controls (--controls, default OPLN:2019-06-28,ZWS:2021-10-05,BEP:2020-07-30): each must be flagged as a spin-off candidate
or a factor-without-move event, or the run exits 3. A control with no prior bar in this export is reported NOT_TESTABLE.
"""
import argparse
import os
import re
import sys
import time

import numpy as np
import pandas as pd

SEALED_FROM = "2025-01-01"
GAP = 0.25
LIQ_DV = 10e6
TARGETS = np.array([2, 3, 4, 5, 10, 20, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10, 1 / 20], dtype=float)
TEST_RE = re.compile(r"^(Z[A-Z]ZZ[TC]|ZVZZC|ZBZX|ZTEST|ZTST|ZIEXT|ZXYZ\.?A?|[ACMNPQ]TEST)$")
STUDY_RE = re.compile(r"^[A-Z]{1,5}$")
COLS = ["t", "d", "o", "h", "l", "c", "v"]


def log(msg):
    print(msg, flush=True)


def load_export(path, cutoff, allow_sealed):
    if cutoff >= SEALED_FROM and not allow_sealed:
        sys.exit(f"refusing cutoff {cutoff}: bars from {SEALED_FROM} are sealed (pass --allow-sealed only for non-outcome use)")
    parts, dropped = [], 0
    # keep_default_na=False: the ticker "NA" (Nano Labs) otherwise parses as NaN and silently vanishes from every groupby.
    for ch in pd.read_csv(path, header=None, names=COLS, dtype={"t": str, "d": str}, keep_default_na=False,
                          na_values=[""], chunksize=2_000_000):
        keep = ch.d <= cutoff
        dropped += int((~keep).sum())
        parts.append(ch[keep])
    df = pd.concat(parts, ignore_index=True)
    return df, dropped


def prior_median(arr, start_of, rows, k=20, minn=10):
    """Median of the k bars BEFORE each row, inside the same ticker; NaN if fewer than minn."""
    out = np.full(len(rows), np.nan)
    for j, i in enumerate(rows):
        lo = max(start_of[i], i - k)
        if i - lo >= minn:
            out[j] = np.median(arr[lo:i])
    return out


class Audit:
    def __init__(self, df, label, cal_ticker, args):
        self.label, self.args = label, args
        self.summary, self.flags = [], []
        df = df.sort_values(["t", "d"], kind="mergesort").reset_index(drop=True)
        cal = np.sort(df.loc[df.t == cal_ticker, "d"].unique())
        self.cal_source = cal_ticker
        if len(cal) == 0:
            cnt = df.groupby("d").t.size()
            cal = np.sort(cnt[cnt >= 0.5 * cnt.max()].index.to_numpy())
            self.cal_source = "breadth>=50%"
        self.cal = cal
        self.df = df
        n = len(df)
        self.n = n
        self.t = df.t.to_numpy(); self.d = df.d.to_numpy()
        self.o, self.h, self.l, self.c = (df[k].to_numpy(float) for k in "ohlc")
        self.v = df.v.to_numpy(float)
        pos = np.searchsorted(cal, self.d)
        pos_c = np.minimum(pos, len(cal) - 1)
        self.on_cal = cal[pos_c] == self.d
        self.idx = pos_c.astype(np.int64)
        tc = pd.factorize(df.t)[0]
        self.tc = tc
        first = np.r_[True, tc[1:] != tc[:-1]]
        last = np.r_[tc[1:] != tc[:-1], True]
        self.first, self.last = first, last
        self.start_of = np.maximum.accumulate(np.where(first, np.arange(n), 0))
        self.pc = np.r_[np.nan, self.c[:-1]]; self.pc[first] = np.nan
        self.pv = np.r_[np.nan, self.v[:-1]]; self.pv[first] = np.nan
        pidx = np.r_[-1, self.idx[:-1]].astype(float); pidx[first] = np.nan
        self.gapn = self.idx - pidx
        self.c1 = np.r_[self.c[1:], np.nan]; self.c1[last] = np.nan
        self.c5 = self._ahead(self.c, 5)
        with np.errstate(divide="ignore", invalid="ignore"):
            self.go = self.o / self.pc - 1
            self.rc = self.c / self.pc - 1
        self.dup_tickers = set()
        self.sectype = {}
        self.known = np.zeros(n, bool)          # within one bar of a known adjustment event
        self.known_src = np.array([""] * n, dtype=object)
        self.adj_events = pd.DataFrame()
        self.raw_f = None

    def _ahead(self, arr, k):
        out = np.full(self.n, np.nan)
        out[: self.n - k] = arr[k:]
        ok = np.zeros(self.n, bool)
        ok[: self.n - k] = self.tc[k:] == self.tc[: self.n - k]
        out[~ok] = np.nan
        return out

    # ---------- helpers ----------
    def S(self, check, metric, value):
        self.summary.append((check, metric, value))
        log(f"  [{check}] {metric}: {value}")

    def liquid_at(self, rows):
        dv = prior_median(self.c * self.v, self.start_of, rows)
        ok = np.array([bool(STUDY_RE.match(self.t[i])) and self.sectype.get(self.t[i], "") in ("CS", "ADRC", "") for i in rows]) & (dv >= LIQ_DV)
        return dv, ok

    def add_flags(self, check, klass, rows, extra=None, dv=None, liq=None):
        rows = np.asarray(rows, int)
        if len(rows) == 0:
            return
        if dv is None:
            dv, liq = self.liquid_at(rows)
        with np.errstate(divide="ignore", invalid="ignore"):
            v20 = prior_median(self.v, self.start_of, rows)
            vr = self.v[rows] / v20
        f = pd.DataFrame({
            "check": check, "klass": klass, "ticker": self.t[rows], "date": self.d[rows], "liquid": liq.astype(int),
            "gapn": self.gapn[rows], "prev_close": self.pc[rows], "open": self.o[rows], "close": self.c[rows],
            "go": self.go[rows], "rc": self.rc[rows], "c1_over_pc": self.c1[rows] / self.pc[rows],
            "c5_over_pc": self.c5[rows] / self.pc[rows], "v_ratio_20": vr, "dv20_prior": dv,
            "extra": extra if extra is not None else ""})
        self.flags.append(f)

    # ---------- known adjustment events ----------
    def load_known(self, splits_path, raw_path):
        ev = []
        if splits_path:
            sp = pd.read_csv(splits_path, sep="|", header=None, names=["t", "ex", "fr", "to"], keep_default_na=False,
                             dtype={"t": str, "ex": str})
            sp["fr"] = pd.to_numeric(sp.fr, errors="coerce"); sp["to"] = pd.to_numeric(sp.to, errors="coerce")
            n_all = len(sp)
            sp = sp[(sp.ex <= self.args.cutoff) & (sp.ex >= self.cal[0]) & (sp.fr > 0) & (sp.to > 0)]
            self.S("adj_event", f"listed splits in file / inside the export window (<= {self.args.cutoff})", f"{n_all} / {len(sp)}")
            sp = sp.drop_duplicates(["t", "ex"])
            ts = pd.Series(np.arange(self.n)).groupby(self.t).agg(["min", "max"])
            for r in sp.itertuples():
                if r.t not in ts.index:
                    continue
                lo, hi = int(ts.at[r.t, "min"]), int(ts.at[r.t, "max"])
                exi = np.searchsorted(self.cal, r.ex)
                ix = self.idx[lo:hi + 1]
                p = lo + int(np.searchsorted(ix, exi))
                if p > hi or self.idx[p] - exi > 1 or p == lo:
                    continue
                ev.append((p, "psv", r.to / r.fr, np.nan, np.nan))
        if raw_path:
            raw = pd.read_csv(raw_path, header=None, names=["t", "d", "raw"], dtype={"t": str, "d": str}, keep_default_na=False)
            raw = raw[raw.d <= self.args.cutoff]
            m = pd.DataFrame({"t": self.t, "d": self.d}).merge(raw, on=["t", "d"], how="left")
            rawc = m.raw.to_numpy(float)
            self.S("adj_event", "rows with a raw close / total rows", f"{int(np.isfinite(rawc).sum())} / {self.n}")
            f = rawc / self.c
            self.raw_f = f
            pf = np.r_[np.nan, f[:-1]]; pf[self.first] = np.nan
            step = pf / f
            rraw = rawc / np.r_[np.nan, rawc[:-1]]
            for p in np.where(np.abs(step - 1) > 0.02)[0]:
                ev.append((int(p), "raw_step", float(step[p]), float(rraw[p]), float(step[p])))
        if not ev:
            return
        e = pd.DataFrame(ev, columns=["row", "src", "fac", "rraw", "step"])
        e["ticker"] = self.t[e.row]; e["date"] = self.d[e.row]
        e["rc"] = self.rc[e.row]; e["gapn"] = self.gapn[e.row]
        self.adj_events = e
        for r in e.itertuples():
            lo = r.row - 1 if (r.row > 0 and self.tc[r.row - 1] == self.tc[r.row]) else r.row
            hi = r.row + 1 if (r.row + 1 < self.n and self.tc[r.row + 1] == self.tc[r.row]) else r.row
            self.known[lo:hi + 1] = True
            self.known_src[r.row] = r.src

    # ---------- checks ----------
    def check_ohlc(self):
        log("== ohlc")
        o, h, l, c = self.o, self.h, self.l, self.c
        mx, mn = np.maximum(o, c), np.minimum(o, c)
        bad_h = h < mx; bad_l = l > mn; hl = h < l
        nonpos = (o <= 0) | (h <= 0) | (l <= 0) | (c <= 0)
        nan = ~(np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c) & np.isfinite(self.v))
        self.S("ohlc", "rows (n)", self.n)
        self.S("ohlc", "high < max(open, close)", int(bad_h.sum()))
        self.S("ohlc", "low > min(open, close)", int(bad_l.sum()))
        self.S("ohlc", "high < low", int(hl.sum()))
        self.S("ohlc", "non-positive price rows / distinct tickers", f"{int(nonpos.sum())} / {len(set(self.t[nonpos]))}")
        self.S("ohlc", "NaN in o/h/l/c/v", int(nan.sum()))
        self.S("ohlc", "duplicate (ticker, date) rows", int(pd.Series(self.t).add("|").add(pd.Series(self.d)).duplicated().sum()))
        self.S("ohlc", "rows off the calendar ticker's sessions", int((~self.on_cal).sum()))
        if bad_h.sum() + bad_l.sum() + hl.sum() == 0:
            self.S("ohlc", "NOTE", "zero violations in a whole export is unusual for vendor bars (cause unverified, possibly clamped upstream); "
                                   "this check cannot see a bad high or low that still covers open and close (see wick)")
        for name, m in (("ohlc_inconsistent", bad_h | bad_l | hl), ("nonpositive_price", nonpos)):
            rows = np.where(m)[0]
            if len(rows):
                dv, liq = self.liquid_at(rows)
                self.add_flags("ohlc", name, rows, dv=dv, liq=liq)

    def check_level(self):
        log("== level (split-adjusted price levels)")
        c = self.c
        for thr in (1e3, 1e5, 1e9):
            m = c >= thr
            self.S("level", f"close >= ${thr:g}: rows / tickers", f"{int(m.sum())} / {len(set(self.t[m]))}")
        m = c < 0.01
        self.S("level", "close < $0.01: rows / tickers", f"{int(m.sum())} / {len(set(self.t[m]))}")
        q = np.nanquantile(c, [0.5, 0.99, 0.999, 1.0])
        self.S("level", "close quantiles p50 / p99 / p99.9 / max", " / ".join(f"{x:.4g}" for x in q))
        mx = pd.Series(c).groupby(self.t).max()
        self.S("level", "tickers whose max adjusted close >= $1000 (n of all)", f"{int((mx >= 1000).sum())} of {len(mx)}")
        self.S("level", "NOTE", "adjusted levels are not tradable prices: any absolute-price rule (close >= $5, price band) needs the RAW close; "
                                "percent signals are unaffected")

    def check_gap(self):
        log("== gap (one-session moves >= 25%)")
        ev_mask = ((np.abs(self.go) >= GAP) | (np.abs(self.rc) >= GAP)) & np.isfinite(self.pc)
        rows = np.where(ev_mask)[0]
        dv, liq = self.liquid_at(rows)
        pc = self.pc[rows]; c1 = self.c1[rows]; c5 = self.c5[rows]
        rc, go = self.rc[rows], self.go[rows]
        rev1 = np.abs(c1 / pc - 1) < 0.10
        rev5 = np.abs(c5 / pc - 1) < 0.10
        same_day = (np.abs(rc) < 0.10) & (np.abs(go) >= GAP)
        no_next = ~np.isfinite(c1)
        klass = np.full(len(rows), "persistent", dtype=object)
        klass[rev5] = "reverted_within_5"
        klass[rev1] = "reverted_next_session"
        klass[same_day] = "open_gap_reverted_same_day"
        klass[no_next & ~same_day] = "no_next_bar"
        klass[self.known[rows]] = "known_adjustment_event"
        stale = self.pv[rows] == 0
        multi = self.gapn[rows] > 1
        self.gap_rows, self.gap_klass, self.gap_liq, self.gap_dv = rows, klass, liq, dv
        self.S("gap", "events (open gap or close-to-close >= 25%) all / liquid", f"{len(rows)} / {int(liq.sum())}")
        self.S("gap", "  open-gap >= 25% / close-to-close >= 25% / down(cc<=-25%) / up(cc>=+25%)",
               f"{int((np.abs(go) >= GAP).sum())} / {int((np.abs(rc) >= GAP).sum())} / {int((rc <= -GAP).sum())} / {int((rc >= GAP).sum())}")
        for k in ["known_adjustment_event", "open_gap_reverted_same_day", "reverted_next_session", "reverted_within_5", "persistent", "no_next_bar"]:
            m = klass == k
            self.S("gap", f"  class {k}: all / liquid", f"{int(m.sum())} / {int((m & liq).sum())}")
        self.S("gap", "  events whose prior bar is a zero-volume fill (stale base): all / liquid", f"{int(stale.sum())} / {int((stale & liq).sum())}")
        self.S("gap", "  events spanning >1 session (prior bar missing days): all / liquid", f"{int(multi.sum())} / {int((multi & liq).sum())}")
        v20g = prior_median(self.v, self.start_of, rows)
        vrg = self.v[rows] / v20g
        for k in ("reverted_next_session", "reverted_within_5"):
            m = (klass == k) & (vrg < 2) & (np.abs(rc) >= GAP)
            self.S("gap", f"  class {k} AND no volume event (volume < 2x its 20-session median; strongest bad-print suspects): all / liquid", f"{int(m.sum())} / {int((m & liq).sum())}")
        extra = np.where(stale, "stale_prior_bar", "")
        extra = np.where(multi, np.char.add(extra.astype(str), "|multi_session"), extra)
        self.add_flags("gap", klass, rows, extra=extra, dv=dv, liq=liq)

    def check_adj_events(self):
        log("== adj_event (is the adjusted series continuous across every known adjustment?)")
        e = self.adj_events
        if e.empty:
            self.S("adj_event", "events", "none (pass --splits and/or --raw-close)")
            return
        e = e.copy()
        e["rr"] = 1 + e.rc            # close/prior close
        e["cont"] = (e.rc).abs() < 0.35
        rows = e.row.to_numpy()
        dv, liq = self.liquid_at(rows)
        e["liq"] = liq
        for src, g in e.groupby("src"):
            mat = g if src == "raw_step" else g[(g.fac - 1).abs() > 0.2]
            self.S("adj_event", f"[{src}] material events / liquid", f"{len(mat)} / {int(mat.liq.sum())}")
            self.S("adj_event", f"[{src}]   adjusted close continuous (|close/prior close - 1| < 35%): all / liquid", f"{int(mat.cont.sum())} / {int((mat.cont & mat.liq).sum())}")
            bad = mat[~mat.cont]
            self.S("adj_event", f"[{src}]   DISCONTINUOUS: all / liquid", f"{len(bad)} / {int(bad.liq.sum())}")
            if src == "psv" and len(bad):
                up = bad[np.abs(np.log(bad.rr / bad.fac)) < np.log(1.35)]
                dn = bad[np.abs(np.log(bad.rr * bad.fac)) < np.log(1.35)]
                self.S("adj_event", "[psv]   of those, jump equals to/fr (the listed factor): ", len(up))
                self.S("adj_event", "[psv]   of those, jump equals fr/to (the inverse): ", len(dn))
                self.S("adj_event", "[psv]   of those, neither (post-reverse-split dump or other): ", len(bad) - len(up) - len(dn))
            if src == "raw_step" and len(bad):
                self.S("adj_event", "[raw_step]   discontinuous with raw price moving < 50% (a factor booked on a non-split move)",
                       int((np.abs(bad.rraw - 1) < 0.5).sum()))
        bad = e[~e.cont & ((e.src == "raw_step") | ((e.fac - 1).abs() > 0.2))]
        if len(bad):
            sel = bad.row.to_numpy()
            ex = np.array([f"{r.src}|fac={r.fac:.4g}|rraw={r.rraw:.3g}" for r in bad.itertuples()])
            d2, l2 = self.liquid_at(sel)
            self.add_flags("adj_event", "discontinuous_across_known_adjustment", sel, extra=ex, dv=d2, liq=l2)
        self.bad_adj_rows = set(bad.row.to_numpy().tolist()) if len(bad) else set()

    def check_splitlike(self):
        log("== splitlike (split-sized close ratios with no known event)")
        with np.errstate(divide="ignore", invalid="ignore"):
            lr = np.log(1 + self.rc)
        ok = np.isfinite(lr) & (self.gapn == 1)
        hit = np.zeros(self.n, bool)
        ok_i = np.where(ok)[0]
        d = np.abs(lr[ok_i][:, None] - np.log(TARGETS)[None, :]).min(axis=1)
        hit[ok_i[d < 0.05]] = True
        hit &= ~self.known
        stale = self.pv == 0
        rows = np.where(hit & ~stale)[0]
        dv, liq = self.liquid_at(rows)
        conf = np.zeros(len(rows), bool)
        for j, i in enumerate(rows):
            lo, hi = self.start_of[i], i
            if hi - lo < 5 or i + 10 > self.n or self.tc[min(i + 9, self.n - 1)] != self.tc[i]:
                continue
            b = np.median(self.v[hi - 5:hi]); a1 = np.median(self.v[i:i + 5]); a2 = np.median(self.v[i + 5:i + 10])
            if b <= 0 or a1 <= 0 or a2 <= 0:
                continue
            want = 1.0 / (1 + self.rc[i])
            conf[j] = abs(np.log(a1 / b / want)) < np.log(1.5) and abs(np.log(a2 / b / want)) < np.log(1.5)
        self.S("splitlike", "close ratios within 5% of 2,3,4,5,10,20 or reciprocals, no known event within one bar, prior bar not a zero-volume fill: all / liquid",
               f"{len(rows)} / {int(liq.sum())}")
        self.S("splitlike", "  of those volume-confirmed (volume re-levels by ~1/ratio for 10 sessions): all / liquid", f"{int(conf.sum())} / {int((conf & liq).sum())}")
        self.S("splitlike", "  distinct tickers (all)", len(set(self.t[rows])))
        klass = np.where(conf, "volume_confirmed_relevel", "unconfirmed")
        self.add_flags("splitlike", klass, rows, dv=dv, liq=liq)

    def check_spinoff(self, controls):
        log("== spinoff (candidates; an earnings crash also qualifies)")
        rows = self.gap_rows
        rc, c5, pc = self.rc[rows], self.c5[rows], self.pc[rows]
        with np.errstate(invalid="ignore", divide="ignore"):
            persistent = (c5 / pc - 1) <= 0.5 * rc
        v20 = prior_median(self.v, self.start_of, rows)
        with np.errstate(invalid="ignore", divide="ignore"):
            vr = self.v[rows] / v20
        cand = (rc <= -GAP) & persistent & (vr >= 2) & (self.gapn[rows] == 1) & (self.gap_klass != "known_adjustment_event")
        bad_adj = getattr(self, "bad_adj_rows", set())
        sel = rows[cand]
        c_o = self.c[sel] / self.o[sel] - 1
        c5c = self.c5[sel] / self.c[sel] - 1
        mech = (np.abs(c_o) < 0.08) & (np.abs(np.nan_to_num(c5c, nan=9.0)) < 0.15)   # a mechanical (not discovered) price: flat intraday, flat after
        # child match: a new listing in -2..+1 sessions whose first open is within 25% of the parent's dollar drop; placebo = same test 20 sessions earlier
        firsts = np.where(self.first)[0]
        fidx = self.idx[firsts]
        order = np.argsort(fidx); firsts, fidx = firsts[order], fidx[order]
        scale = self.raw_f if self.raw_f is not None else np.ones(self.n)

        def child_of(i, shift):
            lo, hi = np.searchsorted(fidx, self.idx[i] - 2 + shift), np.searchsorted(fidx, self.idx[i] + 1 + shift, side="right")
            drop = (self.pc[i] - self.o[i]) * scale[i]
            m = []
            if drop > 0:
                for k in firsts[lo:hi]:
                    if self.tc[k] != self.tc[i] and self.idx[k] > 0 and abs(self.o[k] * scale[k] / drop - 1) <= 0.25:
                        m.append(self.t[k])
            return m
        child = [child_of(i, 0) for i in sel]
        placebo = [bool(child_of(i, -20)) for i in sel]
        has_child = np.array([bool(x) for x in child], bool)
        liq = self.gap_liq[cand]; dv = self.gap_dv[cand]
        self.S("spinoff", "persistent >=25% close-to-close drops (<50% recovered by +5 sessions), volume >= 2x the 20-session median, one-session gap: all / liquid",
               f"{len(sel)} / {int(liq.sum())}")
        self.S("spinoff", "  MECHANICAL subset (|close/open-1| < 8% and |close(+5)/close-1| < 15%): all / liquid", f"{int(mech.sum())} / {int((mech & liq).sum())}")
        self.S("spinoff", "  child-listing match rate, real window vs placebo window 20 sessions earlier (n=%d)" % len(sel),
               f"{has_child.mean() if len(sel) else float('nan'):.3f} vs {np.mean(placebo) if len(sel) else float('nan'):.3f}  -> a match is {'NOT ' if (len(sel) and has_child.mean() < 1.3 * np.mean(placebo)) else ''}discriminating")
        # how does the mechanical test treat events the vendor itself booked as an adjustment but left discontinuous (down moves)?
        ae = self.adj_events
        if len(ae):
            bd = ae[(ae.rc <= -GAP) & ((ae.src == "raw_step") | ((ae.fac - 1).abs() > 0.2))].row.to_numpy()
            if len(bd):
                co = self.c[bd] / self.o[bd] - 1
                c5 = np.nan_to_num(self.c5[bd] / self.c[bd] - 1, nan=9.0)
                m2 = (np.abs(co) < 0.08) & (np.abs(c5) < 0.15)
                self.S("spinoff", "  vendor-booked adjustment events with a >=25% down move: n / pass the mechanical test", f"{len(bd)} / {int(m2.sum())}  (vs {mech.mean():.3f} of all candidates)")
        klass = np.where(mech, "candidate_mechanical", "candidate_other")
        extra = np.array([("child=" + "|".join(x)) if x else "" for x in child], dtype=object)
        self.add_flags("spinoff", klass, sel, extra=extra, dv=dv, liq=liq)
        self.spin_rows = set(sel.tolist()) | bad_adj
        self.mech_rows = set(sel[mech].tolist())
        self.bad_adj_rows = bad_adj
        # positive controls
        failed = []
        log("  positive controls:")
        for ctl in controls:
            tk, dt = ctl.split(":")
            m = np.where((self.t == tk) & (self.d == dt))[0]
            if len(m) == 0:
                st = "NOT_IN_EXPORT_RANGE" if dt < self.cal[0] or dt > self.cal[-1] else "NO_BAR_THAT_DAY"
            else:
                i = m[0]
                if self.first[i]:
                    st = "NOT_TESTABLE_no_prior_bar (the ticker starts that day: a rename/listing seam, not a gap)"
                elif i in self.spin_rows:
                    st = f"FLAGGED as {'MECHANICAL candidate' if i in self.mech_rows else ('vendor-booked factor with a broken series' if i in self.bad_adj_rows else 'candidate (non-mechanical)')} (rc={self.rc[i]:+.3f}, go={self.go[i]:+.3f})"
                else:
                    st = f"NOT_FLAGGED (rc={self.rc[i]:+.3f}, c5/pc={self.c5[i] / self.pc[i]:.3f}, known={bool(self.known[i])})"
                    failed.append(ctl)
            self.S("spinoff", f"control {ctl}", st)
        self.failed_controls = failed

    def check_calendar(self):
        log("== calendar (missing sessions against the calendar ticker)")
        g = pd.DataFrame({"tc": self.tc, "idx": self.idx}).groupby("tc").idx.agg(["min", "max", "size"])
        span = g["max"] - g["min"] + 1
        miss = span - g["size"]
        self.S("calendar", f"calendar sessions ({self.cal_source}) / first / last", f"{len(self.cal)} / {self.cal[0]} / {self.cal[-1]}")
        self.S("calendar", "tickers / with >=1 interior missing session", f"{len(g)} / {int((miss > 0).sum())}")
        self.S("calendar", "interior missing sessions / expected sessions in ticker spans", f"{int(miss.sum())} / {int(span.sum())}")
        self.S("calendar", "tickers starting after the first session (listing or ticker-start seam)", int((g["min"] > 0).sum()))
        self.S("calendar", "tickers ending before the last session (delisted, renamed, or the export dropped them)", int((g["max"] < len(self.cal) - 1).sum()))
        h = self.gapn[(self.gapn >= 2)]
        for lo, hi, nm in ((2, 2, "1 missing"), (3, 3, "2 missing"), (4, 6, "3-5 missing"), (7, 21, "6-20 missing"), (22, 10**6, ">20 missing")):
            self.S("calendar", f"holes with {nm}", int(((h >= lo) & (h <= hi)).sum()))
        hole_rows = np.where(self.gapn >= 2)[0]
        dv, liq = self.liquid_at(hole_rows)
        self.hole_rows, self.hole_liq = hole_rows, liq
        self.S("calendar", "holes (>=1 missing session) all / liquid-at-the-time", f"{len(hole_rows)} / {int(liq.sum())}")
        big = self.gapn[hole_rows] >= 6
        self.S("calendar", "holes of >=5 missing sessions all / liquid-at-the-time", f"{int(big.sum())} / {int((big & liq).sum())}")
        self.add_flags("calendar", "hole_ge5_sessions", hole_rows[big], extra=np.array([f"missing={int(x) - 1}" for x in self.gapn[hole_rows][big]]),
                       dv=dv[big], liq=liq[big])
        cnt = pd.Series(self.idx).value_counts().sort_index()
        roll = cnt.rolling(21, center=True, min_periods=5).median()
        low = cnt[cnt < 0.9 * roll]
        self.S("calendar", "sessions with <90% of the local (21-session) median ticker count", f"{len(low)} of {len(cnt)}"
               + (f" e.g. {self.cal[low.index[0]]}={int(low.iloc[0])} vs {int(roll.loc[low.index[0]])}" if len(low) else ""))
        self.S("calendar", "tickers per session min / median / max", f"{int(cnt.min())} / {int(cnt.median())} / {int(cnt.max())}")

    def check_volume(self):
        log("== volume")
        v0 = self.v == 0
        chg = v0 & (self.c != self.pc) & np.isfinite(self.pc)
        flat = (self.o == self.h) & (self.h == self.l) & (self.l == self.c)
        self.S("volume", "zero-volume rows / distinct tickers", f"{int(v0.sum())} / {len(set(self.t[v0]))}")
        self.S("volume", "  flat fill (o=h=l=c) / non-flat", f"{int((v0 & flat).sum())} / {int((v0 & ~flat).sum())}")
        self.S("volume", "  zero volume AND close != prior close: rows", int(chg.sum()))
        self.S("volume", "  zero volume with close >= $100 (adjusted-volume underflow at a huge price level)", int((v0 & (self.c >= 100)).sum()))
        self.S("volume", "  zero volume, non-flat, close < $100 (a printed range with no volume)", int((v0 & ~flat & (self.c < 100)).sum()))
        self.S("volume", "rows with volume < 0 / NaN", f"{int((self.v < 0).sum())} / {int(np.isnan(self.v).sum())}")
        rows = np.where(v0 & ~flat)[0]
        if len(rows):
            kl = np.where(self.c[rows] >= 100, "zero_volume_underflow", "zero_volume_nonflat")
            dv, liq = self.liquid_at(rows)
            self.add_flags("volume", kl, rows, dv=dv, liq=liq)

    def check_wick(self):
        log("== wick (bad high/low ticks)")
        with np.errstate(divide="ignore", invalid="ignore"):
            up = self.h / np.maximum(self.o, self.c)
            dn = np.minimum(self.o, self.c) / self.l
        for thr in (1.25, 1.5, 2.0):
            self.S("wick", f"high >= {thr}x max(o,c) or low <= min(o,c)/{thr}: rows", int(((up >= thr) | (dn >= thr)).sum()))
        rows = np.where(((up >= 1.5) | (dn >= 1.5)) & (self.v > 0))[0]
        if len(rows):
            dv, liq = self.liquid_at(rows)
            self.S("wick", "  >=1.5x with volume > 0: rows / liquid", f"{len(rows)} / {int(liq.sum())}")
            self.add_flags("wick", "wick_ge_1.5x", rows, dv=dv, liq=liq)

    def check_test_symbols(self):
        log("== test symbols")
        tk = sorted(x for x in pd.unique(self.t) if TEST_RE.match(x))
        n = int(np.isin(self.t, tk).sum()) if tk else 0
        self.S("test_symbol", "tickers / rows", f"{len(tk)} / {n}  {tk}")
        for x in tk:
            r = np.where(self.t == x)[0]
            self.add_flags("test_symbol", "exchange_test_ticker", r[:1], extra=np.array([f"rows={len(r)}"]), dv=np.array([np.nan]), liq=np.array([False]))

    def check_duplicates(self):
        log("== duplicate series (byte-identical bars under two symbols)")
        m = self.v >= 1000
        key = pd.util.hash_array(self.o.view(np.int64)) ^ (pd.util.hash_array(self.h.view(np.int64)) * np.uint64(3)) \
            ^ (pd.util.hash_array(self.l.view(np.int64)) * np.uint64(5)) ^ (pd.util.hash_array(self.c.view(np.int64)) * np.uint64(7)) \
            ^ (pd.util.hash_array(self.v.view(np.int64)) * np.uint64(11))
        df = pd.DataFrame({"i": np.where(m)[0], "idx": self.idx[m], "key": key[m]})
        dup = df[df.duplicated(["idx", "key"], keep=False)]
        self.S("duplicate", "rows (volume >= 1000) sharing an identical (date, o, h, l, c, v) with another ticker", len(dup))
        if len(dup) == 0:
            return
        grp = dup.groupby(["idx", "key"]).i.apply(list)
        pairs = {}
        for lst in grp:
            ts = sorted({self.t[i] for i in lst})
            for a in range(len(ts)):
                for b in range(a + 1, len(ts)):
                    pairs[(ts[a], ts[b])] = pairs.get((ts[a], ts[b]), 0) + 1
        p = pd.DataFrame([(a, b, n) for (a, b), n in pairs.items()], columns=["a", "b", "days"])
        real = p[p.days >= 10]
        self.S("duplicate", "ticker pairs with >=10 identical days / pairs with any", f"{len(real)} / {len(p)}")
        self.dup_tickers = set(real.a) | set(real.b)
        self.S("duplicate", "  distinct tickers inside those pairs", len(set(real.a) | set(real.b)))
        self.S("duplicate", "  examples", "; ".join(f"{r.a}={r.b}({r.days}d)" for r in real.sort_values("days", ascending=False).head(12).itertuples()))
        f = pd.DataFrame({"check": "duplicate", "klass": "identical_series_pair", "ticker": real.a.to_numpy(), "date": "", "liquid": "",
                          "extra": [f"other={r.b}|days={r.days}" for r in real.itertuples()]})
        self.flags.append(f)


    def check_exposure(self):
        """How much of the LIQUID population (20-session median dollar volume >= $10M, ticker ^[A-Z]{1,5}$) each defect touches."""
        log("== exposure (share of liquid ticker-days)")
        dvs = (pd.Series(self.c * self.v).groupby(self.tc).transform(lambda x: x.rolling(20, min_periods=10).median().shift(1))).to_numpy()
        study_t = {x: bool(STUDY_RE.match(x)) and self.sectype.get(x, "") in ("CS", "ADRC", "") for x in pd.unique(self.t)}
        stu = np.array([study_t[x] for x in self.t])
        liq = (dvs >= LIQ_DV) & stu
        tot = int(liq.sum())
        ends = np.where(self.last)[0]
        end_of = ends[np.searchsorted(ends, np.arange(self.n))]
        self.S("exposure", "liquid ticker-days (denominator) / distinct liquid tickers", f"{tot:,} / {len(set(self.t[liq])):,}")

        def shadow(rows, W):
            m = np.zeros(self.n, bool)
            for i in rows:
                m[i:min(i + W, end_of[i] + 1)] = True
            return m
        def rep(name, m):
            self.S("exposure", f"{name}", f"{int((m & liq).sum()):,} liquid ticker-days = {100 * (m & liq).sum() / max(tot, 1):.3f}%")
        hr = self.hole_rows[self.hole_liq]
        rep("within 130 sessions after an interior missing-session hole on a liquid name (a 130-CONSECUTIVE-session history rule drops these)", shadow(hr, 130))
        ba = np.array(sorted(getattr(self, "bad_adj_rows", set())), dtype=np.int64)
        if len(ba):
            rep("within 126 sessions after an adjustment event whose adjusted series is discontinuous (return windows spanning it are wrong)", shadow(ba, 126))
        mr = np.array(sorted(getattr(self, "mech_rows", set())), dtype=np.int64)
        if len(mr):
            rep("within 126 sessions after a MECHANICAL spin-off candidate", shadow(mr, 126))
        if self.dup_tickers:
            rep("rows of a ticker inside an identical-series pair (the same company counted twice)", np.isin(self.t, list(self.dup_tickers)))
        rep("adjusted close >= $1000 (raw-price rules cannot be applied to this price)", self.c >= 1000)
        br = self.gap_rows[np.isin(self.gap_klass, ["reverted_next_session", "reverted_within_5"]) & self.gap_liq]
        if len(br):
            rep("within 60 sessions after a reverted (bad-print suspect) one-session move >= 25%", shadow(br, 60))

    def check_compare(self, other_df, other_label):
        log(f"== compare with {other_label}")
        lo, hi = max(self.d.min(), other_df.d.min()), min(self.d.max(), other_df.d.max())
        a = pd.DataFrame({"t": self.t, "d": self.d, "ca": self.c, "va": self.v})
        a = a[(a.d >= lo) & (a.d <= hi)]
        b = other_df[(other_df.d >= lo) & (other_df.d <= hi)][["t", "d", "c", "v"]].rename(columns={"c": "cb", "v": "vb"})
        m = a.merge(b, on=["t", "d"], how="outer", indicator=True)
        both = m[m._merge == "both"].copy()
        self.S("compare", f"overlap window / sessions", f"{lo} .. {hi} / {m.d.nunique()}")
        self.S("compare", f"(ticker,date) rows in both / only {self.label} / only {other_label}",
               f"{len(both)} / {int((m._merge == 'left_only').sum())} / {int((m._merge == 'right_only').sum())}")
        self.S("compare", "tickers in both / only here / only there", f"{both.t.nunique()} / {m[m._merge == 'left_only'].t.nunique()} / {m[m._merge == 'right_only'].t.nunique()}")
        bt = set(both.t)
        mm = m[m.t.isin(bt)]
        ob, oa = mm[mm._merge == "right_only"], mm[mm._merge == "left_only"]
        self.S("compare", "for tickers present in both: bars only here / only there", f"{len(oa)} ({oa.t.nunique()} tickers) / {len(ob)} ({ob.t.nunique()} tickers)")
        self.S("compare", "  of the 'only there' bars, share with zero volume (a no-trade fill the other export omits)", f"{(ob.vb == 0).mean() if len(ob) else float('nan'):.3f} (n={len(ob)})")
        both["r"] = both.ca / both.cb
        self.S("compare", "rows with close ratio within 0.1% / 1%", f"{(abs(both.r - 1) < 1e-3).mean():.4f} / {(abs(both.r - 1) < 1e-2).mean():.4f}  (n={len(both)})")
        g = both.groupby("t").r.agg(["median", "min", "max"])
        off = g[(g["median"] - 1).abs() > 0.01].copy()
        off["drift"] = off["max"] / off["min"]
        cum = {}
        if self.args.splits:
            sp = pd.read_csv(self.args.splits, sep="|", header=None, names=["t", "ex", "fr", "to"], keep_default_na=False, dtype={"t": str, "ex": str})
            sp["fr"] = pd.to_numeric(sp.fr, errors="coerce"); sp["to"] = pd.to_numeric(sp.to, errors="coerce")
            sp = sp[(sp.fr > 0) & (sp.to > 0) & (sp.ex > hi) & (sp.ex <= self.args.cutoff)]
            cum = sp.assign(f=sp.fr / sp.to).groupby("t").f.prod().to_dict()
        def explained(t, med):
            c = cum.get(t)
            return c is not None and (abs(np.log(med / c)) < 0.05 or abs(np.log(med * c)) < 0.05)
        off["expl"] = [explained(t, r["median"]) for t, r in off.iterrows()]
        off["klass"] = np.where(off.expl, "explained_by_listed_later_splits", np.where(off.drift > 1.02, "ratio_drifts_in_window_identity_or_event", "constant_ratio_unexplained"))
        self.S("compare", "tickers whose median close ratio is off by >1% (adjustment-epoch or identity difference)", f"{len(off)} of {len(g)}")
        for k, n in off.klass.value_counts().items():
            self.S("compare", f"  {k}", n)
        self.S("compare", "  NOTE", "the epoch explanation uses listed splits dated after the overlap and <= cutoff only; constant unexplained ratios are usually splits after the cutoff (not tested here)")
        self.flags.append(pd.DataFrame({"check": "compare", "klass": off.klass.to_numpy(), "ticker": off.index, "date": "", "liquid": "",
                                        "extra": [f"median_ratio={r['median']:.6g}|drift={r.drift:.3g}" for _, r in off.iterrows()]}))

    def write(self, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        fl = pd.concat(self.flags, ignore_index=True) if self.flags else pd.DataFrame()
        fl.to_csv(f"{out_dir}/{self.label}_flags.tsv", sep="\t", index=False, float_format="%.6g")
        pd.DataFrame(self.summary, columns=["check", "metric", "value"]).to_csv(f"{out_dir}/{self.label}_summary.tsv", sep="\t", index=False)
        log(f"wrote {out_dir}/{self.label}_flags.tsv ({len(fl)} rows) and {self.label}_summary.tsv ({len(self.summary)} lines)")


def run(args):
    t0 = time.time()
    np.seterr(divide="ignore", invalid="ignore")
    df, dropped = load_export(args.export, args.cutoff, args.allow_sealed)
    log(f"[{args.label}] {args.export}: {len(df):,} rows kept (<= {args.cutoff}), {dropped:,} later rows dropped unread, "
        f"{df.t.nunique():,} tickers, {df.d.min()}..{df.d.max()}  ({time.time() - t0:.0f}s)")
    a = Audit(df, args.label, args.calendar_ticker, args)
    if args.sectype:
        for ln in open(args.sectype):
            f = ln.rstrip("\n").split("|")
            if len(f) >= 3 and f[0] == "sectype":
                a.sectype[f[1]] = f[2]
        log(f"  sectype table: {len(a.sectype):,} tickers; 'liquid' now also requires type CS / ADRC / unknown (the study's rule)")
    a.check_ohlc(); a.check_level()
    a.load_known(args.splits, args.raw_close)
    a.check_gap(); a.check_adj_events(); a.check_splitlike()
    a.check_spinoff([x for x in args.controls.split(",") if x])
    a.check_calendar(); a.check_volume(); a.check_wick(); a.check_test_symbols(); a.check_duplicates(); a.check_exposure()
    if args.compare:
        o, _ = load_export(args.compare, args.cutoff, args.allow_sealed)
        a.check_compare(o, args.compare_label)
    a.write(args.out_dir)
    log(f"done in {time.time() - t0:.0f}s")
    if a.failed_controls:
        log(f"POSITIVE CONTROL(S) NOT FLAGGED: {a.failed_controls}")
        return 3
    return 0


def selftest():
    """Synthetic export with one injected defect per check; each must be caught."""
    import tempfile, gzip
    rng = np.random.default_rng(1)
    cal = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2020-01-01", periods=120)]
    rows = []
    def series(t, p0=50.0, vol=1e6, drop=()):
        p = p0
        for k, d in enumerate(cal):
            if k in drop: continue
            p *= 1 + rng.normal(0, 0.01)
            rows.append([t, d, p, p * 1.01, p * 0.99, p, vol])
    for t in ["SPY", "GOOD"]: series(t)
    series("HOLE", drop=range(40, 50))
    series("ZTEST")
    series("DUPA"); rows.extend([[("DUPB"), r[1], r[2], r[3], r[4], r[5], r[6]] for r in rows if r[0] == "DUPA"])
    df = pd.DataFrame(rows, columns=COLS)
    def bump(t, k, f, persist=True, vol_f=1.0):
        m = (df.t == t) & (df.d == cal[k])
        if not m.any(): return
        for col in "ohlc": df.loc[m, col] *= f
        if persist:
            m2 = (df.t == t) & (df.d > cal[k])
            for col in "ohlc": df.loc[m2, col] *= f
            df.loc[m2, "v"] *= vol_f
    bump("GOOD", 30, 1.4, persist=False)                      # bad print: spike that reverts
    bump("GOOD", 60, 0.5, persist=True, vol_f=2.0)            # unlisted 2:1 split
    bump("GOOD", 90, 0.4, persist=True)                       # persistent crash
    df.loc[(df.t == "GOOD") & (df.d == cal[10]), "h"] = 1.0   # high below open/close
    p = tempfile.mkdtemp()
    f = f"{p}/x.csv.gz"
    with gzip.open(f, "wt") as fh: df.to_csv(fh, header=False, index=False)
    ns = argparse.Namespace(export=f, label="T", out_dir=p, cutoff="2024-12-31", allow_sealed=False, splits=None, raw_close=None,
                            compare=None, compare_label="", calendar_ticker="SPY", controls="", sectype=None)
    assert run(ns) == 0
    fl = pd.read_csv(f"{p}/T_flags.tsv", sep="\t")
    def has(check, klass, ticker): return ((fl.check == check) & (fl.klass == klass) & (fl.ticker == ticker)).any()
    assert has("ohlc", "ohlc_inconsistent", "GOOD")
    assert has("gap", "reverted_next_session", "GOOD"), fl[fl.check == "gap"]
    assert has("gap", "persistent", "GOOD")
    assert has("splitlike", "volume_confirmed_relevel", "GOOD"), fl[fl.check == "splitlike"]
    assert has("calendar", "hole_ge5_sessions", "HOLE")
    assert has("test_symbol", "exchange_test_ticker", "ZTEST")
    assert has("duplicate", "identical_series_pair", "DUPA")
    print("SELFTEST OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export"); ap.add_argument("--label", default="X"); ap.add_argument("--out-dir", default="price_audit_out")
    ap.add_argument("--cutoff", default="2024-12-31"); ap.add_argument("--allow-sealed", action="store_true")
    ap.add_argument("--splits", help="pipe file ticker|ex_date|from|to (cb702_splits.psv)")
    ap.add_argument("--raw-close", help="ticker,date,raw_close csv.gz (unadjusted) to derive the adjustment steps")
    ap.add_argument("--sectype", help="small_pulls.psv (sectype|TICKER|TYPE|MIC); makes 'liquid' = the study universe (CS/ADRC/unknown)")
    ap.add_argument("--compare"); ap.add_argument("--compare-label", default="OTHER")
    ap.add_argument("--calendar-ticker", default="SPY")
    ap.add_argument("--controls", default="OPLN:2019-06-28,ZWS:2021-10-05,BEP:2020-07-30")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest(); return 0
    if not args.export:
        ap.error("--export is required")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
