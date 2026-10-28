#!/usr/bin/env python3
"""#314 replay — the STEP 0 phases (derive / climax / features), the detector subprocess per population, the walk subprocess per
population, and the walk stage (rule (c), the bars, the reads, the beside rows, G8, the re-derivation). Called by ps_replay.py, whose
gates run first. Nothing here opens the network; every pull is read from the file ps_pull.py wrote.

READINGS (continued; the main loop decides):
  R51 The cap is computed for EVERY night of a company whose CIK was pulled (the pull covers the companies with at least one
      necessary-condition night, R7); a company outside the pull is cap `not_pulled` -> the detector's unknown (mid) branch. So the
      per-gate funnel is exact for every pulled company and, for the others, read at the mid tier — and none of those nights can be a
      climax at ANY tier (R7), so the climax list does not depend on it. Counted per source. This holds only for a COMPLETE pull:
      the climax gate refuses unless every candidate CIK has a final submissions AND companyfacts record (R66).
  R52 The GME 2021-01 and NVDA 2024-03 printed goldens run in the P1 process (the untouched module) on every session of the month
      at the night's own point-in-time cap, whatever population the night falls in (the population is printed beside).
  R53 Read 1's beside ("exit at the close of D0 + 3, his count from the top day") is a fifth replay of the same episode with
      time_stop = 4 - k, k = the entry's session offset from D0 (an entry on D0+3 exits at that close).
  R54 Read 2's ratio beside: pauses / run length <= 0.20 vs > 0.20 (one down close per five sessions or fewer = straighter).
  R67 (review 10-28; a PLAN GAP — the main loop rules) Read 3 and row (a) query Polygon news by `ticker`, but era A keys every series
      by TODAY's symbol (META holds Facebook's 2016-22 bars) and Polygon tags an item with the symbol in use when it was published, so a
      renamed company's pre-rename news would read `absent` / `clear`, not unknown. The climax phase finds the symbol in use at D0
      (`PP.FormerSymbols`: a delisted record of the same security under another symbol, smallest delisted_utc >= D0) and writes it
      beside each news_wanted row (`d0_symbol`, `symbol_status` series / renamed / ambiguous); the features phase reads a renamed or
      ambiguous row's read 3 and row (a) as UNKNOWN (`renamed_symbol`). The pull still queries the series symbol. The fork for the main
      loop: query the D0 symbol (the #88 rule then names it) vs keep them unknown. A rename Polygon carries no record of stays a silent
      `absent` — stated, not caught.
  R69 (main-loop ruling 2026-10-28, round 5 of the plan) R67's fork: a RENAMED row's news is pulled under its D0 symbol (`ps_pull.pull_news`
      writes `query_symbol` on the record; read 3 and row (a) match items tagged with it); an AMBIGUOUS row keeps the series symbol and reads
      unknown (`renamed_symbol`).
  R55 The pooled verdict is per population over both eras; per-era rows beside with their n. Read 3's present share is printed by the
      D0 calendar year.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import ps_common as X  # noqa: E402
import ps_population as PP  # noqa: E402
import ps_features as FT  # noqa: E402
import ps_walk as W  # noqa: E402
import ps_goldens as GD  # noqa: E402

GuardStop = X.GuardStop
STAGE = "ps314_"
POPS = ("P1", "P2", "P2small")
CLIMAX_COLS = ("ticker", "d0", "era", "calendar_file", "calendar_sha256", "population", "company_key", "key_source", "tier", "cap", "cap_source",
               "cap_reason", "cap_filing_accn", "owner_type", "owner_cik", "owner_cfigi", "owner_sfigi", "owner_delisted", "owner_name", "owner_path",
               "type", "type_source", "gone", "refetch_sourced", "earnings", "reachable", "open_at_seal", "jump_unevidenced", "pre_hole",
               "alias_outside_span", "pre_break", "no_active_record", "base_date", "base_low", "anchor", "open", "high", "low", "close", "raw_close",
               "factor_d0", "dollar_volume", "prior_move", "days_up_streak", "score", "stop_price", "atr_14", "ohlcv_sha", "void_adjustment_event",
               "adj_event_date", "distribution_suspect", "suspect_gap_date", "suspect_gap", "duplicate_company_night", "duplicate_of")


def _R():
    import ps_replay as R
    return R


def expectations(say, rows: list) -> None:
    """The plan's expectations (each can miss; a miss changes no rule): printed at the TOP of the printout, every MISS first."""
    rows = sorted(rows, key=lambda r: (r[1] is not False, r[1] is None))
    block = ["", "## Expectations (fixed in the plan; a miss is reported first and changes no rule)"]
    for text, held, detail in rows:
        block.append(f"  [{'MISS' if held is False else 'held' if held else 'n/a'}] {text}: {detail}")
    k = next((i for i, ln in enumerate(say.lines) if ln.startswith("- modules: ")), 2) + 1
    say.lines[k:k] = block
    for ln in block:
        print(ln, flush=True)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# STEP 0 driver
# ═════════════════════════════════════════════════════════════════════════════════════════════
def step0(P: X.Paths, phase: str, say) -> int:
    R = _R()
    R.header(say, f"STEP 0 — {phase} (derive and count the populations; walk nothing)", P)
    problems = R.gate_step0(P, phase)
    if problems:
        say("STEP 0 REFUSED:")
        for q in problems:
            say("  - " + q)
        say.write(P.refused)
        return 2
    os.makedirs(P.out, exist_ok=True)
    try:
        say("\n## The synthetic positive controls (a mismatch refuses)")
        import tempfile
        bad = GD.detector_golden_check(say) + GD.walk_goldens(tempfile.mkdtemp(prefix="ps314_goldens_"), say)
        if bad:
            raise GuardStop("a synthetic golden failed: " + "; ".join(bad))
        outs = {"derive": derive, "climax": climax, "features": features}[phase](P, say)
    except GuardStop as ex:
        say(f"\nSTEP 0 {phase.upper()} STOPPED: {ex}")
        say.write(P.refused)
        return 3
    say(f"\nSTEP 0 {phase.upper()} COMPLETE")
    say.write(P.step0_printout(phase))
    for k in outs:
        X.ledger_append(P.ledger, f"{STAGE}step0_{phase}:{k}", getattr(P, k))
    for k in R.PHASE_PULLS[phase]:                          # R66: the pull files this phase read, so a later append or swap is caught
        X.ledger_append(P.ledger, f"{STAGE}step0_{phase}:input:{k}", getattr(P, k))
    X.ledger_append(P.ledger, f"{STAGE}step0_{phase}:printout", P.step0_printout(phase))
    if phase == "derive":
        X.ledger_append(P.ledger, f"{STAGE}step0_derive:dry_run", P.dry)
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# shared context builders
# ═════════════════════════════════════════════════════════════════════════════════════════════
def reference(P: X.Paths) -> tuple:
    ref = PP.load_reference(P.polygon_reference)
    return ref, PP.active_key_set(ref), PP.company_counts(ref)


def breaks_from_file(P: X.Paths, era: str) -> list:
    return [r for r in X.read_tsv(P.breaks_applied) if r["era"] == era]


def build_ctx(P: X.Paths, e, ref: dict, cc: dict, active_keys: set, breaks: "list | None" = None, name_mismatch: set = frozenset()) -> PP.Ctx:
    if e.name == "A":
        guard = PP.load_guard(P.guard_A)
        refetch = {t: PP.refetch_record_as_ref(r) for t, r in PP.load_refetch_records(P.refetch_records).items()}
        refetched, minus_pre = PP.refetch_set(P, e)
        if minus_pre is not None and refetched != minus_pre:
            raise GuardStop(f"the refetch set ({len(refetched)}) differs from v2 minus cb702_pre ({len(minus_pre)})")
        ao = PP.alias_outside_span(PP.load_dedupe(P.dedupe_A), e)
        if sum(v["inside"] for v in ao.values()):
            raise GuardStop("a dedupe_applied.tsv dropped symbol has a bar inside its dropped span: the file is not the deduped one")
        types, _ = PP.load_type_table(P.types_A)
        sic = PP.load_sic_types(P.sic_A)
    else:
        guard = PP.load_guard(P.guard_B)
        refetch, refetched, ao = {}, set(), {}
        types, _ = PP.load_type_table(P.types_B)
        sic = PP.load_sic_types(P.sic_B)
    cls = PP.classify_breaks(e, guard, cc)
    if breaks is None:
        breaks = cls
    else:
        strip = lambda rows: sorted((r["symbol"], r["date"], r["kind"], r["evidence"], r["applied"]) for r in rows)
        if strip(breaks) != strip(cls):
            raise GuardStop(f"era {e.name}: the pinned breaks_applied.tsv differs from the evidence rule on the pinned guard + pull")
    return PP.Ctx(ref=ref, refetch=refetch, refetched=refetched, breaks=breaks, company_count=cc, alias_outside=ao, types=types, sic=sic,
                  active_keys=active_keys, name_mismatch=set(name_mismatch))


def cal_file_of(P: X.Paths, era: str) -> str:
    return P.sessions_A if era == "A" else P.calendar_B


# ═════════════════════════════════════════════════════════════════════════════════════════════
# derive
# ═════════════════════════════════════════════════════════════════════════════════════════════
def derive(P: X.Paths, say) -> list:
    ref, active_keys, cc = reference(P)
    na = sum(1 for v in ref.values() for r in v if r.get("_pull") == "active")
    nd = sum(1 for v in ref.values() for r in v if r.get("_pull") == "delisted")
    say(f"\n## The reference pull: {na:,} active + {nd:,} delisted records over {len(ref):,} symbols; active company keys {len(active_keys):,}")
    if not na or not nd:
        raise GuardStop(f"the reference pull must hold both pulls (active {na:,}, delisted {nd:,})")
    dups = PP.reference_duplicates(ref)
    say(f"- exact duplicate reference records (R63; a refusal if any): {sum(dups.values()):,} on {len(dups):,} symbols"
        + (": " + ", ".join(f"{t} x{n + 1}" for t, n in sorted(dups.items())[:30]) if dups else ""))
    if dups:
        raise GuardStop(f"the reference pull holds {sum(dups.values()):,} exact duplicate records (a retried pull appended to its partial file?)")
    all_breaks, owners, ciks = [], [], set()
    for era in ("A", "B"):
        e = PP.load_era(P, era)
        say(f"\n## Era {era}: {e.info['rows']:,} rows, {e.info['symbols']:,} symbols, {e.info['sessions']} sessions")
        if era == "B":
            nyse = X.nyse_sessions(X.B_FIRST, X.CUT_B)
            if nyse != e.cal:
                raise GuardStop("era B: SPY's sessions differ from the NYSE calendar")
            with open(P.calendar_B + ".partial", "w") as fh:
                fh.write("\n".join(e.cal) + "\n")
            os.replace(P.calendar_B + ".partial", P.calendar_B)
            say(f"- calendar_B.txt written: {len(e.cal)} sessions = the NYSE calendar ({X.sha(P.calendar_B)[:16]})")
        ctx = build_ctx(P, e, ref, cc, active_keys)
        all_breaks += [{"era": era, **r} for r in ctx.breaks]
        nt = PP.night_table(e, ctx)
        PP.assert_alias_owners(nt)
        bad = [nt.recs[o] for o in np.unique(nt.owner[nt.owner >= 0]) if PP.owner_has_placeholder(nt.recs[o])]
        if bad:
            raise GuardStop(f"era {era}: {len(bad)} owners still carry the 2022-06-30 placeholder after the re-resolution")
        _print_breaks(say, era, ctx)
        say(f"\n### era {era} funnel (STEP 0 derive; the cap and the detector gates come at the climax phase)")
        for k, v in PP.funnel_step0(e, nt).items():
            say(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
        pops = PP.populations(e, nt)
        sup = PP.superset_mask(e) & (pops["P1"] | pops["P2"] | pops["P2unk"])
        sup_ciks = {(nt.recs[o].get("_cik") or "") for o in np.unique(nt.owner[sup & (nt.owner >= 0)])} - {""}
        ciks |= sup_ciks
        say(f"- necessary-condition nights (R7: a climax at SOME tier is possible): {int(sup.sum()):,}; their owners' CIKs: {len(sup_ciks):,}")
        if era == "A":
            for s, d in X.CONTROLS["distribution"]:
                i = e.bar_index(s, d)
                r = nt.rec_of(i) if i >= 0 else None
                ck = (r or {}).get("_cik") or ""
                say(f"- distribution control {s} {d}: owner {PP.PATHS[int(nt.path[i])] if i >= 0 else 'no bar'} CIK {ck or 'NONE'} (added to the EDGAR pull)")
                if ck:
                    ciks.add(ck)
            _print_era_A_owner_checks(say, e, nt, ctx)
        else:
            for s, d in X.CONTROLS["earlier_issuer_B"]:
                ok, lines = earlier_issuer_control(e, nt, ref.get(s, []), s, d)
                for ln in lines:
                    say(ln)
                if not ok:
                    raise GuardStop(f"the earlier-issuer control {s} {d} is not caught by the earlier-issuer rule: " + lines[-1].strip())
        owners += _owner_rows(e, nt, era)
        for pn in ("P1", "P2", "P2unk"):
            sk = len({nt.keys[k] for k in np.unique(nt.key[pops[pn]]) if nt.keys[k].startswith("sym:")})
            say(f"- {pn} symbol-keyed companies (no CIK, no FIGI): {sk:,} (each may be one company counted twice)")
        empty = sorted({nt.recs[o].get("ticker", "") for o in np.unique(nt.owner[nt.owner >= 0])
                        if not (nt.recs[o].get("_cik") or nt.recs[o].get("composite_figi") or nt.recs[o].get("share_class_figi"))})
        say(f"- owners left empty-keyed (type / CIK / gone unknown): {len(empty)}: {', '.join(empty[:200])}")
        fd = PP.funnel_dry(e)
        for k in [k for k in fd if k.startswith("adjusted-pass") or k.startswith("raw-pass")]:
            say(f"- {k}: {fd[k]:,}")
        for k, v in sorted(nt.info.items()):
            say(f"- {k}: {v}")
        del e, nt
    X.write_tsv(P.breaks_applied, ["era", "symbol", "date", "kind", "evidence", "applied"], all_breaks)
    X.write_tsv(P.owners, ["era", "symbol", "first", "last", "rows", "path", "ticker_of_record", "type", "cik", "composite_figi", "share_class_figi",
                           "delisted", "name", "gone"], owners)
    with open(P.candidate_ciks + ".partial", "w") as fh:
        fh.write("# the owning CIKs of every necessary-condition night (R7) + the distribution controls' owners\n")
        fh.write("\n".join(sorted(ciks)) + "\n")
    os.replace(P.candidate_ciks + ".partial", P.candidate_ciks)
    say(f"\n- candidate_ciks.txt: {len(ciks):,} CIKs (the EDGAR pull's input)")
    return ["calendar_B", "breaks_applied", "owners", "candidate_ciks"]


def _print_breaks(say, era, ctx) -> None:
    syms = sorted({r["symbol"] for r in ctx.breaks})
    kinds = Counter()
    for s in syms:
        n = ctx.company_count.get(s) if ctx.company_count is not None else None
        kinds["no_record" if not n else "multi_company" if n >= 2 else "one_company"] += 1
    ev = Counter((r["kind"], r["applied"]) for r in ctx.breaks)
    say(f"- era {era} break symbols: {len(syms):,} — one-company {kinds['one_company']:,}, multi-company {kinds['multi_company']:,}, "
        f"no-record {kinds['no_record']:,}; breaks applied / not: " + ", ".join(f"{k}:{a} {v}" for (k, a), v in sorted(ev.items())))


def _print_era_A_owner_checks(say, e, nt, ctx) -> None:
    gme = e.tid.get("GME")
    if gme is not None:
        a, b = e.rows_of(gme)
        rows = [r for r in ctx.breaks if r["symbol"] == "GME"]
        say(f"- GME: company keys among its records {ctx.company_count.get('GME')}; breaks {[(r['date'], r['applied'], r['evidence']) for r in rows]}; "
            f"Jan-2021 nights {'INSIDE (typed by its own record)' if not (nt.flags[a:b] & (PP.F_ID_GUARD | PP.F_PRE_BREAK)).any() else 'outside: an applied break'}")
    # type agreement with the v2 table (expected 100% refetched, >= 99% original)
    agree = Counter()
    lst = []
    for t, s in enumerate(e.tickers):
        a, b = e.rows_of(t)
        o = int(nt.owner[b - 1]) if b > a else -1
        if o < 0 or s not in ctx.types:
            continue
        rt = nt.recs[o].get("type") or ""
        grp = "refetched" if s in ctx.refetched else "original"
        ok = rt == ctx.types[s]
        agree[(grp, ok)] += 1
        if not ok:
            lst.append(f"{s}:{rt or '-'}!={ctx.types[s]}")
    for grp in ("refetched", "original"):
        n = agree[(grp, True)] + agree[(grp, False)]
        say(f"- era A type agreement, owner record vs the v2 table, {grp}: {agree[(grp, True)]:,} of {n:,} ({X.pct(agree[(grp, True)], n)})")
    if lst:
        say("  disagreements: " + ", ".join(lst[:200]) + (f" ... (+{len(lst) - 200})" if len(lst) > 200 else ""))
    ao = sorted(ctx.alias_outside)
    for s in ao:
        t = e.tid[s]
        a, b = e.rows_of(t)
        own = Counter(PP.PATHS[int(p)] for p in nt.path[a:b])
        recs = Counter((nt.rec_of(k) or {}).get("name", "unknown") for k in range(a, b))
        say(f"- alias_outside_span {s}: {b - a} rows; owner paths {dict(own)}; owners {dict(recs)}")


def earlier_issuer_control(e, nt, recs: list, s: str, d: str) -> tuple:
    """R58 (revised 10-28): the INBX / DOC control -> (passes, printed lines). The records and the night's owner path are printed. If the
    control night is owned by the ACTIVE (new) record, the earlier-issuer FLAG must be set on it. If Polygon dated the old record on or
    after the switch (its delisted_utc commonly lags the last bar by 1-2 sessions), the old record owns the night by the date rule and the
    rule does not apply there: the night must then be excluded (history or identity), AND the flag must be set on the first ACTIVE-owned
    session after the old record's delisted_utc (the first night the rule governs) — so the rule is tested either way, never vacuously."""
    lines = [f"- earlier-issuer control {s} {d}: records " + "; ".join(
        f"{r.get('_pull')} {r.get('name', '')!r} cik {r.get('_cik') or '-'} delisted {r.get('_delisted') or '-'} key {PP.rec_key(r, s)}"
        for r in recs)]
    i = e.bar_index(s, d)
    if i < 0:
        return False, lines + ["  bar ABSENT on the control night"]
    fl = int(nt.flags[i])
    rec = nt.rec_of(i)
    lines.append(f"  night {d}: owner path {PP.PATHS[int(nt.path[i])]}, owner {(rec or {}).get('name', 'unknown')!r}; earlier-issuer flag "
                 f"{bool(fl & PP.F_ID_EARLIER)}; guard {bool(fl & PP.F_ID_GUARD)}; 120 consecutive sessions {bool(e.contig[i])}")
    if rec is None:
        return False, lines + ["  the control night has no owner (a tie or no record): the control cannot be evaluated"]
    if PP.is_active_record(rec):
        if fl & PP.F_ID_EARLIER:
            return True, lines + ["  active-owned and flagged: the rule catches the control night"]
        return False, lines + ["  active-owned and NOT flagged"]
    excluded = (not bool(e.contig[i])) or bool(fl & (PP.F_ID_EARLIER | PP.F_ID_GUARD))
    if not excluded:
        return False, lines + ["  owned by the old record (date lag) and NOT excluded by history or identity"]
    t = e.tid[s]
    a, b = e.rows_of(t)
    dl = rec.get("_delisted") or ""
    j = next((k for k in range(i, b) if e.cal[e.D.ci[k]] > dl and PP.is_active_record(nt.rec_of(k))), -1)
    if j < 0:
        return False, lines + [f"  owned by the old record (delisted {dl}); no active-owned session after it to test the rule on"]
    fj = int(nt.flags[j])
    dj = e.cal[e.D.ci[j]]
    lines.append(f"  owned by the old record (delisted {dl}, the date rule) and excluded; first active-owned session {dj}: earlier-issuer "
                 f"flag {bool(fj & PP.F_ID_EARLIER)}")
    if fj & PP.F_ID_EARLIER:
        return True, lines + [f"  the rule catches the first night it governs ({dj})"]
    return False, lines + [f"  the first active-owned session {dj} is NOT flagged"]


def _owner_rows(e, nt, era) -> list:
    out = []
    for t, s in enumerate(e.tickers):
        a, b = e.rows_of(t)
        for k0, k1, oi, pc in PP._runs(nt.owner[a:b], nt.path[a:b]):
            r = nt.recs[oi] if oi >= 0 else {}
            out.append({"era": era, "symbol": s, "first": e.cal[e.D.ci[a + k0]], "last": e.cal[e.D.ci[a + k1 - 1]], "rows": k1 - k0,
                        "path": PP.PATHS[pc], "ticker_of_record": r.get("ticker", ""), "type": r.get("type", ""), "cik": r.get("_cik", ""),
                        "composite_figi": r.get("composite_figi", ""), "share_class_figi": r.get("share_class_figi", ""),
                        "delisted": r.get("_delisted", "") if r else "", "name": r.get("name", ""),
                        "gone": {PP.G_NO: "no", PP.G_YES: "yes"}.get(int(nt.gone[a + k0]), "unknown")})
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the cap per night (climax phase) and the name cross-check
# ═════════════════════════════════════════════════════════════════════════════════════════════
class EraBasis(FT.Basis):
    """S(end, D0) straight off an era's arrays (no per-ticker date lists: 12M strings would not fit) — era A from raw / adjusted on
    the name's last bar <= d, era B from the split list (the parent class)."""

    def __init__(self, e):
        super().__init__(e.name, splits=e.splits)
        self.e = e
        self.cal_ord = np.array([X.ord_of(d) for d in e.cal], dtype=np.int64)

    def _last_le(self, ticker: str, d: str) -> tuple:
        t = self.e.tid.get(ticker)
        if t is None:
            return (None, -1)
        a, b = self.e.rows_of(t)
        ords = self.cal_ord[self.e.D.ci[a:b]]
        return (a, int(np.searchsorted(ords, X.ord_of(d), side="right")) - 1)

    def factor_A(self, ticker: str, d: str):
        a, i = self._last_le(ticker, d)
        if a is None or i < 0:
            return None
        return X.num(self.e.fac[a + i])

    def steps_A(self, ticker: str, lo: str, hi: str) -> "bool | None":
        a, i = self._last_le(ticker, lo)
        _a, j = self._last_le(ticker, hi)
        if a is None or i < 0 or j < 0:
            return None
        return FT._any_step(np.asarray(self.e.fac[a + i: a + j + 1], dtype=float))


class Caps:
    """Per CIK: the filing index and the cover facts by accession (R40); one `cap_for` per night."""

    def __init__(self, subs: dict, facts: dict):
        self.subs, self.facts = subs, facts
        self._idx = {}

    def index(self, cik: str) -> "FT.FilingIndex":
        if cik not in self._idx:
            self._idx[cik] = FT.FilingIndex(self.subs.get(cik))
        return self._idx[cik]

    def cap(self, ticker: str, d0: str, cik: str, basis, raw_close: float) -> dict:
        if not cik:
            return {"cap": None, "cap_source": "unknown", "cap_reason": "no_cik", "filing_accn": "", "shares_d0": None, "fact_end": ""}
        if cik not in self.subs:
            return {"cap": None, "cap_source": "not_pulled", "cap_reason": "not_pulled (R51)", "filing_accn": "", "shares_d0": None, "fact_end": ""}
        return FT.cap_for(ticker, d0, cik, self.subs.get(cik), self.facts.get(cik), basis, raw_close, index=self.index(cik))


def name_mismatches(ref: dict, refetch_recs: dict, subs: dict) -> tuple:
    """R14 / R59: the record ids whose name disagrees with SEC's for their CIK after the printed normalisation — the submissions `name`
    or any of its `formerNames` (the same filer's own history: a delisted record carries the name at its delisting) -> (ids, listing)."""
    ids, lst = set(), []
    allrecs = [r for v in ref.values() for r in v] + list(refetch_recs.values())
    for r in allrecs:
        ck = r.get("_cik") or ""
        sub = subs.get(ck)
        if not ck or not sub or sub.get("status") != 200 or not sub.get("name") or not r.get("name"):
            continue
        a = FT.name_normal(r["name"])
        names = {FT.name_normal(sub["name"])} | {FT.name_normal(x.get("name", "")) for x in (sub.get("formerNames") or []) if isinstance(x, dict)}
        if a not in names:
            ids.add(PP.id_of(r))
            lst.append(f"{r.get('ticker')}: {r['name']!r} vs SEC {sub['name']!r}")
    return ids, lst


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the detector subprocess (one per population; the constant asserted / patched here only)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def detect_pop(P: X.Paths, pop: str) -> int:
    t0 = time.time()
    bad = child_refusal(P, "--detect", pop)
    if bad:
        print(f"[detect {pop}] REFUSED:\n  - " + "\n  - ".join(bad), flush=True)
        return 2
    if pop == "P1":
        const = PP.assert_dollar_vol_const("P1")
    else:
        PP.patch_p2_constant()
        const = PP.assert_dollar_vol_const("P2")
    print(f"[detect {pop}] parabolic_detector._MIN_DOLLAR_VOL_TODAY = {const:,}", flush=True)
    ref, active_keys, cc = reference(P)
    subs = FT.load_submissions(P.edgar_submissions)
    facts = FT.load_facts(P.xbrl_facts)
    refetch_recs = {t: PP.refetch_record_as_ref(r) for t, r in PP.load_refetch_records(P.refetch_records).items()}
    mm, mm_list = name_mismatches(ref, refetch_recs, subs)
    caps = Caps(subs, facts)
    out_rows, summary = [], {"pop": pop, "constant": const, "name_mismatch": mm_list, "eras": {}}
    flag_parts = {}
    for era in ("A", "B"):
        e = PP.load_era(P, era)
        ctx = build_ctx(P, e, ref, cc, active_keys, breaks=breaks_from_file(P, era), name_mismatch=mm)
        nt = PP.night_table(e, ctx)
        PP.assert_alias_owners(nt)
        pops = PP.populations(e, nt)
        mask = pops["P1"] if pop == "P1" else pops["P2"]
        rows, es = _detect_era(P, e, nt, ctx, mask, pop, caps)
        out_rows += rows
        summary["eras"][era] = es
        if pop == "P1":
            summary["eras"][era]["printed_goldens"] = _printed_goldens(e, nt, caps, era)
            fl = PP.distribution_flags(e)
            fl.insert(0, "era", era)
            flag_parts[era] = fl
        print(f"[detect {pop}] era {era}: {es['scored']:,} nights scored, {len(rows):,} climaxes ({time.time() - t0:.0f}s)", flush=True)
        del e, nt
    X.write_tsv(P.o(f"climax_part_{pop}.tsv"), list(CLIMAX_COLS), out_rows)
    if pop == "P1":
        import pandas as pd
        pd.concat([flag_parts["A"], flag_parts["B"]]).to_csv(P.o("distribution_flags_part.tsv"), sep="\t", index=False)
    with open(P.o(f"detect_{pop}.json"), "w") as fh:
        json.dump(summary, fh, default=str)
    print(f"[detect {pop}] DETECT COMPLETE ({time.time() - t0:.0f}s)", flush=True)
    return 0


def _key_source(k: str) -> str:
    return {"cik": "cik", "cfigi": "composite_figi", "sfigi": "share_class_figi", "sym": "symbol"}[k.split(":", 1)[0]]


def _detect_era(P, e, nt, ctx, mask, pop, caps) -> tuple:
    """Every night of `mask` through the pinned detector (the funnel per gate); the climax candidates removed by identity / history
    counted (R46); the climax rows."""
    pdm = PP.detector_module()
    from agents.market_intelligence import parabolic_short_shadow as psh
    basis = EraBasis(e)
    cal_file = cal_file_of(P, e.name)
    cal_sha = X.sha(cal_file)
    funnel = Counter()
    by_year = Counter()
    cap_src = Counter()
    tier_ct = Counter()
    removed = Counter()
    rows = []
    # the band nights that failed identity / history (counted as removed climax candidates, never listed)
    adm_band = (e.sym_ok[e.row_tid] & e.detect & ((nt.flags & (PP.F_TYPE_EXCLUDED | PP.F_SUFFIX_EXCLUDED)) == 0)
                & (e.p1 if pop == "P1" else (e.band & ~e.p1)))
    typed_ok = np.ones(len(e.D.c), bool) if pop == "P1" else ((nt.tcode == PP.T_CS) | (nt.tcode == PP.T_ADRC))
    removed_mask = adm_band & typed_ok & ~mask
    want = mask | removed_mask
    scored = 0
    sentinel = (pop == "P2small")
    for t in np.unique(e.row_tid[want]):
        t = int(t)
        a, b = e.rows_of(t)
        idx = np.flatnonzero(want[a:b])
        if not len(idx):
            continue
        s = e.tickers[t]
        dicts = PP.ticker_dicts(e, t)
        for j in idx:
            j = int(j)
            i = a + j
            if j < X.HISTORY - 1:
                continue
            d0 = e.cal[e.D.ci[i]]
            rec = nt.rec_of(i)
            cik = (rec or {}).get("_cik") or ""
            if sentinel:
                capd = {"cap": 1, "cap_source": "sentinel_small_tier", "cap_reason": "", "filing_accn": ""}
            else:
                capd = caps.cap(s, d0, cik, basis, X.num(e.raw[i]))
            cap = capd["cap"]
            hist = dicts[j - X.HISTORY + 1: j + 1]
            if hist[-1]["trade_date"].isoformat() != d0:
                raise GuardStop(f"rows[-1].trade_date != D0 for ({s}, {d0})")
            res = pdm.compute_parabolic_metrics(hist, market_cap=(int(cap) if cap is not None else None), is_earnings_today=None)
            if not mask[i]:
                if res.get("stage") == "climax":
                    fl = int(nt.flags[i])
                    why = ("history (not 120 consecutive sessions)" if not e.contig[i] else
                           "identity_break: applied guard break" if fl & PP.F_ID_GUARD else
                           "identity_break: earlier-issuer rule" if fl & PP.F_ID_EARLIER else "other")
                    removed[why] += 1
                continue
            if not e.contig[i]:
                raise GuardStop(f"a scored night without 120 consecutive sessions ({s}, {d0})")
            scored += 1
            gate = PP.gate_of(res)
            funnel[gate] += 1
            cap_src[capd["cap_source"]] += 1
            tier_ct[res.get("cap_tier")] += 1
            if res.get("stage") != "climax":
                continue
            by_year[d0[:4]] += 1
            fl = int(nt.flags[i])
            bdate, blow = pdm._compute_base_low(hist, len(hist) - 1)
            anchor = _is_anchor(hist, pdm)
            geo = psh.arm_geometry(hist, len(hist) - 1)
            reach = (geo["stop_price"] - geo["climax_low"]) / geo["climax_low"] < 0.25 if geo["climax_low"] > 0 else False
            key = nt.key_of(i)
            ohlcv = np.concatenate([e.D.o[i - X.HISTORY + 1:i + 1], e.D.h[i - X.HISTORY + 1:i + 1], e.D.l[i - X.HISTORY + 1:i + 1],
                                    e.D.c[i - X.HISTORY + 1:i + 1], e.D.v[i - X.HISTORY + 1:i + 1]])
            rows.append({
                "ticker": s, "d0": d0, "era": e.name, "calendar_file": cal_file, "calendar_sha256": cal_sha, "population": pop,
                "company_key": key, "key_source": _key_source(key), "tier": res.get("cap_tier"), "cap": cap if not sentinel else "",
                "cap_source": capd["cap_source"], "cap_reason": capd.get("cap_reason", ""), "cap_filing_accn": capd.get("filing_accn", ""),
                "owner_type": (rec or {}).get("type", ""), "owner_cik": cik, "owner_cfigi": (rec or {}).get("composite_figi", ""),
                "owner_sfigi": (rec or {}).get("share_class_figi", ""),
                "owner_delisted": ((rec or {}).get("_delisted") or ("active" if rec else "")), "owner_name": (rec or {}).get("name", ""),
                "owner_path": PP.PATHS[int(nt.path[i])], "type": {PP.T_CS: "CS", PP.T_ADRC: "ADRC"}.get(int(nt.tcode[i]), ""),
                "type_source": PP.TSRC[int(nt.tsrc[i])], "gone": {PP.G_NO: "no", PP.G_YES: "yes"}.get(int(nt.gone[i]), "unknown"),
                "refetch_sourced": int(bool(fl & PP.F_REFETCHED)), "earnings": "unknown", "reachable": int(bool(reach)),
                "open_at_seal": int(e.D.ci[i] > e.last_d0), "jump_unevidenced": int(bool(fl & PP.F_JUMP_UNEV)),
                "pre_hole": int(bool(fl & PP.F_PRE_HOLE)), "alias_outside_span": int(bool(fl & PP.F_ALIAS_OUTSIDE)),
                "pre_break": int(bool(fl & PP.F_PRE_BREAK)), "no_active_record": int(bool(fl & PP.F_NO_ACTIVE)),
                "base_date": bdate.isoformat() if bdate else "", "base_low": blow, "anchor": int(anchor),
                "open": X.num(e.D.o[i]), "high": X.num(e.D.h[i]), "low": X.num(e.D.l[i]), "close": X.num(e.D.c[i]), "raw_close": X.num(e.raw[i]),
                "factor_d0": X.num(e.fac[i]), "dollar_volume": X.num(e.dv[i]), "prior_move": res.get("prior_move_pct"),
                "days_up_streak": res.get("days_up_streak"), "score": res.get("score"), "stop_price": geo["stop_price"], "atr_14": geo["atr_14"],
                "ohlcv_sha": hashlib.sha256(ohlcv.tobytes()).hexdigest()[:32],
                "void_adjustment_event": 0, "adj_event_date": "", "distribution_suspect": 0, "suspect_gap_date": "", "suspect_gap": "",
                "duplicate_company_night": 0, "duplicate_of": ""})
    return rows, {"scored": scored, "funnel": dict(funnel), "by_year": dict(by_year), "cap_source": dict(cap_src), "tier": dict(tier_ct),
                  "removed_candidates": dict(removed)}


def _is_anchor(hist: list, pdm) -> bool:
    """The base is the 60-sessions-ago anchor: no close <= SMA20 in [today - 60, today] (detector.py:140-157)."""
    ti = len(hist) - 1
    for i in range(ti, max(0, ti - pdm._BASE_LOOKBACK_DAYS) - 1, -1):
        s = pdm._sma(hist, i, pdm._SMA20_DAYS)
        if s is not None and float(hist[i]["close"]) <= s:
            return False
    return True


def _printed_goldens(e, nt, caps, era) -> list:
    """R52: GME 2021-01 (era A) / NVDA 2024-03 (era B), every session of the month, stage + gate values at the point-in-time cap."""
    pdm = PP.detector_module()
    sym, month = X.CONTROLS["gme"] if era == "A" else X.CONTROLS["nvda"]
    t = e.tid.get(sym)
    out = []
    if t is None:
        return [f"{sym}: no bars in era {era}"]
    a, b = e.rows_of(t)
    dicts = PP.ticker_dicts(e, t)
    basis = EraBasis(e)
    for j in range(b - a):
        d0 = e.cal[e.D.ci[a + j]]
        if not d0.startswith(month) or j < X.HISTORY - 1:
            continue
        i = a + j
        rec = nt.rec_of(i)
        capd = caps.cap(sym, d0, (rec or {}).get("_cik") or "", basis, X.num(e.raw[i]))
        res = pdm.compute_parabolic_metrics(dicts[j - X.HISTORY + 1: j + 1], market_cap=(int(capd["cap"]) if capd["cap"] else None))
        out.append(f"{sym} {d0}: stage {res.get('stage')} ({PP.gate_of(res)}), tier {res.get('cap_tier')} (cap {capd['cap_source']}), prior move "
                   f"{res.get('prior_move_pct')}, ext50 {res.get('ext_vs_sma50')}, streak {res.get('days_up_streak')}, score {res.get('score')}, "
                   f"gapped {res.get('gapped_today')}, climax vol {res.get('climax_volume_flag')}, contiguous {bool(e.contig[i])}, "
                   f"identity flags {int(nt.flags[i])}, population P1 {bool(e.p1[i])}")
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# climax (the parent)
# ═════════════════════════════════════════════════════════════════════════════════════════════
CLAIM_ENV = "PS314_CLAIM"


def claim_path(P: X.Paths, flag: str, pop: str) -> str:
    return P.o(f".claim_{flag.strip('-')}_{pop}")


def run_sub(P: X.Paths, flag: str, pop: str, log: str) -> None:
    """R62: the parent writes a ONE-SHOT claim (a random token under P.out) and passes the token in the child's environment; the child
    refuses without it and deletes it, so --detect / --walk-pop cannot run except as the subprocess of a gated parent."""
    import secrets
    import ps_replay as R
    tok = secrets.token_hex(16)
    os.makedirs(P.out, exist_ok=True)
    with open(claim_path(P, flag, pop), "w") as fh:
        fh.write(tok)
    cmd = [sys.executable, os.path.join(HERE, "ps_replay.py"), flag, pop, "--paths-json", R.paths_to_json(P)]
    try:
        with open(log, "w") as fh:
            rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, env={**os.environ, CLAIM_ENV: tok}).returncode
    finally:
        if os.path.exists(claim_path(P, flag, pop)):
            os.remove(claim_path(P, flag, pop))
    if rc != 0:
        tail = open(log).read()[-2000:]
        raise GuardStop(f"the {flag} {pop} subprocess exited {rc}:\n{tail}")


def child_refusal(P: X.Paths, flag: str, pop: str) -> list:
    """R62: the child's own refusal — the parent's one-shot claim (verified and consumed), then the parent's gate re-run."""
    cp = claim_path(P, flag, pop)
    tok = os.environ.get(CLAIM_ENV, "")
    have = open(cp).read().strip() if os.path.exists(cp) else ""
    if os.path.exists(cp):
        os.remove(cp)                                          # one shot, whatever the outcome
    if not tok or not have or tok != have:
        return [f"{flag} {pop} was not launched by a gated parent (no matching one-shot claim at {cp}): it runs only as the "
                f"subprocess of --step0 climax / --walk"]
    R = _R()
    if flag == "--detect":
        return R.gate_step0(P, "climax", child=True)
    probs = R.gate_walk(P, child=True)
    part = P.o(f"episodes_part_{pop}.tsv")
    if os.path.exists(part):
        probs.append(f"{part} exists: a population is walked once (the operator removes it by hand)")
    return probs


def climax(P: X.Paths, say) -> list:
    import pandas as pd
    for pop in POPS:
        say(f"- detector pass {pop} (its own process) ...")
        run_sub(P, "--detect", pop, P.o(f"detect_{pop}.log"))
    summ = {pop: json.load(open(P.o(f"detect_{pop}.json"))) for pop in POPS}
    for pop in POPS:
        want = X.P1_DOLLAR_VOL_CONST if pop == "P1" else X.P2_DOLLAR_VOL_CONST
        if summ[pop]["constant"] != want:
            raise GuardStop(f"the {pop} process ran with _MIN_DOLLAR_VOL_TODAY = {summ[pop]['constant']}, expected {want}")
        say(f"- {pop} process: _MIN_DOLLAR_VOL_TODAY = {summ[pop]['constant']:,} (asserted in the process)")
    rows = []
    for pop in POPS:
        rows += X.read_tsv(P.o(f"climax_part_{pop}.tsv"))
    flags = pd.read_csv(P.o("distribution_flags_part.tsv"), sep="\t", dtype=str, keep_default_na=False)
    flags.to_csv(P.distribution_flags + ".partial", sep="\t", index=False)
    os.replace(P.distribution_flags + ".partial", P.distribution_flags)
    _mark_voids(P, rows, flags, say)
    _dedupe(rows, say)
    X.write_tsv(P.climax_list, list(CLIMAX_COLS), rows)
    sus = [r for r in rows if r["distribution_suspect"] == "1"]
    X.write_tsv(P.distribution_suspects, ["ticker", "d0", "era", "population", "gap_date", "gap", "prior_close", "n_new_listings", "new_listings"],
                [{"ticker": r["ticker"], "d0": r["d0"], "era": r["era"], "population": r["population"], "gap_date": r["suspect_gap_date"],
                  "gap": r["suspect_gap"], **_flag_hint(flags, r)} for r in sus])
    _print_climax(P, rows, summ, flags, say)
    _write_wanted(P, rows, flags, say, PP.FormerSymbols(PP.load_reference(P.polygon_reference)))
    expectations(say, _climax_expectations(rows, summ))
    return ["climax_list", "distribution_flags", "distribution_suspects", "filings_wanted", "news_wanted", "suspects_wanted"]


def _flag_hint(flags, r) -> dict:
    m = flags[(flags["ticker"] == r["ticker"]) & (flags["gap_date"] == r["suspect_gap_date"]) & (flags["era"] == r["era"])]
    if not len(m):
        return {"prior_close": "", "n_new_listings": "", "new_listings": ""}
    q = m.iloc[0]
    return {"prior_close": q["prior_close"], "n_new_listings": q["n_new_listings"], "new_listings": q["new_listings"]}


def _sessions_after(cal: list, d0: str, n: int) -> list:
    import bisect
    i = bisect.bisect_left(cal, d0)
    return cal[i + 1: i + 1 + n]


def _cal(P: X.Paths, era: str) -> list:
    with open(cal_file_of(P, era)) as fh:
        return [ln.strip() for ln in fh if ln.strip()]


def _mark_voids(P, rows, flags, say) -> None:
    """R47: a listed adjustment event inside the 120-row window (after its first bar) or on D0+1..D0+7 -> void_adjustment_event; a
    flagged gap on D0+1..D0+7 -> distribution_suspect."""
    import bisect
    adj = {"A": PP.load_adj_events(P.flags_A, X.A_LAST), "B": PP.load_adj_events(P.flags_B, X.CUT_B)}
    adj_by = {era: defaultdict(list) for era in adj}
    for era, lst in adj.items():
        for t, d in lst:
            adj_by[era][t].append(d)
    fl_by = defaultdict(list)
    for r in flags.itertuples():
        fl_by[(r.era, r.ticker)].append((r.gap_date, r.gap))
    cals = {era: _cal(P, era) for era in ("A", "B")}
    for r in rows:
        cal = cals[r["era"]]
        i = bisect.bisect_left(cal, r["d0"])
        if i >= len(cal) or cal[i] != r["d0"]:
            raise GuardStop(f"a climax row's D0 {r['d0']} is not on its era's calendar ({r['era']})")
        w_first = cal[i - X.HISTORY + 1]
        after = cal[i + 1: i + 1 + X.WALK_AFTER]
        hit = [d for d in adj_by[r["era"]].get(r["ticker"], []) if (w_first < d <= r["d0"]) or (d in after)]
        if hit:
            r["void_adjustment_event"], r["adj_event_date"] = "1", min(hit)
        sus = sorted((d, g) for d, g in fl_by.get((r["era"], r["ticker"]), []) if d in after)
        if sus:
            r["distribution_suspect"], r["suspect_gap_date"], r["suspect_gap"] = "1", sus[0][0], sus[0][1]
    say(f"- void_adjustment_event climax rows: {sum(1 for r in rows if r['void_adjustment_event'] == '1'):,}; distribution suspects: "
        f"{sum(1 for r in rows if r['distribution_suspect'] == '1'):,}")


def _dedupe(rows, say) -> None:
    """One climax row per (company, D0) within a population and era: same key on one D0, or byte-identical 120-row OHLCV under any
    keys -> keep ONE (the alias map's kept symbol — no dropped symbol's row survives inside its span, asserted — else the higher D0
    dollar volume, else the alphabetically first); the others `duplicate_company_night`."""
    groups = defaultdict(list)
    for k, r in enumerate(rows):
        groups[("key", r["population"], r["era"], r["d0"], r["company_key"])].append(k)
        groups[("bytes", r["population"], r["era"], r["d0"], r["ohlcv_sha"])].append(k)
    parent = list(range(len(rows)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for ks in groups.values():
        for k in ks[1:]:
            ra, rb = find(ks[0]), find(k)
            if ra != rb:
                parent[rb] = ra
    clusters = defaultdict(list)
    for k in range(len(rows)):
        clusters[find(k)].append(k)
    n = 0
    lst = []
    for ks in clusters.values():
        if len(ks) < 2:
            continue
        keep = sorted(ks, key=lambda k: (-float(rows[k]["dollar_volume"]), rows[k]["ticker"]))[0]
        for k in ks:
            if k != keep:
                rows[k]["duplicate_company_night"], rows[k]["duplicate_of"] = "1", rows[keep]["ticker"]
                n += 1
                lst.append(f"{rows[k]['population']} {rows[k]['d0']} {rows[k]['ticker']} -> {rows[keep]['ticker']}")
    say(f"- duplicate_company_night: {n} climax rows (kept one per company and D0)" + (": " + "; ".join(lst[:50]) if lst else ""))


def _print_climax(P, rows, summ, flags, say) -> None:
    live = [r for r in rows if r["duplicate_company_night"] != "1"]
    for pop in POPS:
        for era in ("A", "B"):
            es = summ[pop]["eras"][era]
            say(f"\n### {pop} era {era}: the detector funnel (gates in the plan's order; {es['scored']:,} nights scored)")
            for g in PP.GATE_ORDER:
                if g in es["funnel"]:
                    say(f"  stopped at / reached {g}: {es['funnel'][g]:,}")
            say(f"  climax candidates REMOVED before the detector (scored as live would, counted only): {es['removed_candidates']}")
            say(f"  cap source: {es['cap_source']}; tier: {es['tier']}")
            say(f"  climaxes per calendar year: {dict(sorted(es['by_year'].items()))}")
            for line in es.get("printed_goldens", []) or []:
                say("  " + line)
    if summ["P1"]["name_mismatch"]:
        say(f"\n- owner records unknown by the name cross-check (R14): {len(summ['P1']['name_mismatch'])}: "
            + "; ".join(summ["P1"]["name_mismatch"][:100]))
    say("\n## Climax companies: the survivorship floor (refusing on a zero)")
    for pop in ("P1", "P2"):
        for era in ("A", "B"):
            sub = [r for r in live if r["population"] == pop and r["era"] == era]
            comps = defaultdict(set)
            for r in sub:
                comps[r["company_key"]].add(r["gone"])
            gone = sum(1 for v in comps.values() if v == {"yes"})
            unk = sum(1 for v in comps.values() if "unknown" in v)
            inwin = sum(1 for r in {r["company_key"]: r for r in sub if r["gone"] == "yes"}.values()
                        if r["owner_delisted"] not in ("", "active") and r["owner_delisted"] <= (X.A_LAST if era == "A" else X.CUT_B))
            say(f"- {pop} era {era}: {len(comps):,} climax companies; gone {gone:,} ({X.pct(gone, len(comps))}); gone inside the era's window "
                f"{inwin:,}; gone unknown {unk:,}")
            if era == "A":
                refc = len({r["company_key"] for r in sub if r["refetch_sourced"] == "1"})
                say(f"  era A refetch-sourced climax companies: {refc:,} ({X.pct(refc, len(comps))})")
                if pop == "P2":
                    both = [r for r in live if r["era"] == "A" and r["population"] in ("P1", "P2")]
                    if both and not any(r["refetch_sourced"] == "1" for r in both):
                        raise GuardStop("era A's refetch-sourced share of the climax companies is zero (the gone companies did not arrive)")
                bad = [r for r in sub if r["gone"] == "yes" and r["refetch_sourced"] != "1"
                       and r["owner_path"] not in ("no active record -> latest delisted", "alias_date_rule")]
                if bad:
                    raise GuardStop("a gone era-A climax company that is not refetch-sourced came by another owner path: "
                                    + ", ".join(f"{r['ticker']} {r['d0']} {r['owner_path']}" for r in bad[:10]))
                listing = sorted({(r["ticker"], r["owner_path"]) for r in sub if r["gone"] == "yes" and r["refetch_sourced"] != "1"})
                say(f"  gone, not refetch-sourced (the subset test, each with its path): {listing}")
            if pop == "P2" and len(comps) and gone == 0:
                raise GuardStop(f"the gone share of P2 climax companies is zero in era {era}")
    say("\n## Climax rows by population and era")
    for pop in POPS:
        for era in ("A", "B"):
            sub = [r for r in live if r["population"] == pop and r["era"] == era]
            n = len(sub)
            say(f"- {pop} era {era}: {n:,} climax rows ({sum(1 for r in sub if r['open_at_seal'] == '1')} open at the seal); reachable 3R proxy "
                f"{X.pct(sum(1 for r in sub if r['reachable'] == '1'), n)}; void_adjustment_event {sum(1 for r in sub if r['void_adjustment_event'] == '1')}; "
                f"suspects {sum(1 for r in sub if r['distribution_suspect'] == '1')}; jump_unevidenced {sum(1 for r in sub if r['jump_unevidenced'] == '1')}; "
                f"pre_hole {sum(1 for r in sub if r['pre_hole'] == '1')}; alias_outside_span {sum(1 for r in sub if r['alias_outside_span'] == '1')}; "
                f"type sources {dict(Counter(r['type_source'] for r in sub))}; key sources {dict(Counter(r['key_source'] for r in sub))}; "
                f"typed CS {X.pct(sum(1 for r in sub if r['type'] == 'CS'), n)}")
            caps = [float(r["cap"]) for r in sub if r["cap"] not in ("", None)]
            if pop == "P2":
                say(f"  P2's point-in-time cap where known: {len(caps):,} of {n:,}; under $250M: {X.pct(sum(1 for c in caps if c < 250e6), len(caps))}")
    keys = set(zip(flags["ticker"], flags["gap_date"]))
    for s, d in X.CONTROLS["distribution"]:
        if (s, d) not in keys:
            raise GuardStop(f"the flagger does not list {s} {d} (a rule that cannot see the two known spin-offs is refused)")
    say("- the flagger over the raw bars lists OPLN 2019-06-28 and ZWS 2021-10-05 (checked; the evidence class comes at the features phase)")


def _climax_expectations(rows, summ) -> list:
    live = [r for r in rows if r["duplicate_company_night"] != "1"]
    n = lambda **kw: [r for r in live if all(r[k] == v for k, v in kw.items())]
    out = []
    n1, n2 = len(n(population="P1")), len(n(population="P2"))
    out.append(("P2 yields more climax nights than P1", n2 > n1, f"P2 {n2:,} vs P1 {n1:,}"))
    p2 = n(population="P2")
    cs = sum(1 for r in p2 if r["type"] == "CS")
    out.append(("at least 80% of P2's climax rows typed CS", (cs >= 0.8 * len(p2)) if p2 else None, f"{cs} of {len(p2)}"))
    p1 = n(population="P1")
    rc = sum(1 for r in p1 if r["reachable"] == "1")
    out.append(("the reachable-3R proxy share is under 50% in P1", (rc < 0.5 * len(p1)) if p1 else None, f"{rc} of {len(p1)}"))
    for era, floor in (("A", 0.25), ("B", 0.15)):
        sub = n(population="P2", era=era)
        comps = defaultdict(set)
        for r in sub:
            comps[r["company_key"]].add(r["gone"])
        g = sum(1 for v in comps.values() if v == {"yes"})
        out.append((f"the gone share of P2 climax companies is >= {int(floor * 100)}% in era {era}", (g >= floor * len(comps)) if comps else None,
                    f"{g} of {len(comps)}"))
    ya = Counter(r["d0"][:4] for r in live if r["era"] == "A" and r["population"] in ("P1", "P2"))
    yb = Counter(r["d0"][:4] for r in live if r["era"] == "B" and r["population"] in ("P1", "P2"))
    mb = (sum(yb.values()) / len(yb)) if yb else 0
    ok = all(0.5 * mb <= v <= 2 * mb for v in ya.values()) if (ya and mb) else None
    out.append(("era A's climax count per calendar year is within 2x of era B's per-year mean", ok, f"A {dict(sorted(ya.items()))}, B mean {mb:.1f}"))
    tot = len(rows)
    for col, cap in (("duplicate_company_night", 0.01), ("alias_outside_span", 0.01), ("void_adjustment_event", 0.02)):
        c = sum(1 for r in rows if r[col] == "1")
        out.append((f"{col} is under {cap:.0%} of climax rows", (c < cap * tot) if tot else None, f"{c} of {tot}"))
    return out


def _write_wanted(P, rows, flags, say, former=None) -> None:
    subs = FT.load_submissions(P.edgar_submissions)
    cals = {era: _cal(P, era) for era in ("A", "B")}
    fw, nw, sw = [], [], set()
    sym_status = Counter()
    for r in rows:
        if r["duplicate_company_night"] == "1":
            continue
        d0s, sst = r["ticker"], "series"
        if r["era"] == "A" and former is not None and r["population"] in ("P1", "P2"):              # R67 (a plan gap: the main loop rules)
            d0s, sst = former.at(r["ticker"], r["d0"], r["owner_cik"], r["owner_cfigi"], r["owner_sfigi"], r["owner_type"])
        if r["population"] in ("P1", "P2"):
            sym_status[(r["era"], sst)] += 1
        if r["population"] in ("P1", "P2") and r["owner_cik"]:
            f = FT.FilingIndex(subs.get(r["owner_cik"])).latest_before(r["d0"]) if r["owner_cik"] in subs else None
            if f and FT.lookup_covered(subs.get(r["owner_cik"]), f):
                fw.append({"cik": r["owner_cik"], "accn": f.get("accessionNumber", ""), "primaryDocument": f.get("primaryDocument", ""),
                           "form": f.get("form", ""), "filingDate": f.get("filingDate", "")})
        if r["population"] in ("P1", "P2"):
            w3 = FT.news_window_read3(cals[r["era"]], r["base_date"] or None) if r["anchor"] != "1" else None
            if w3:
                X.seal_date(w3[1][:10], "news window")
                nw.append({"ticker": r["ticker"], "d0": r["d0"], "kind": "read3", "gte": w3[0], "lte": w3[1], "d0_symbol": d0s, "symbol_status": sst})
            gte, lte = FT.news_window_mna(r["d0"])
            nw.append({"ticker": r["ticker"], "d0": r["d0"], "kind": "mna", "gte": gte, "lte": lte, "d0_symbol": d0s, "symbol_status": sst})
        if r["distribution_suspect"] == "1":
            sw.add((r["ticker"], r["suspect_gap_date"]))
    for s, d in X.CONTROLS["distribution"]:
        sw.add((s, d))
    X.write_tsv(P.filings_wanted, ["cik", "accn", "primaryDocument", "form", "filingDate"], sorted({tuple(x.values()): x for x in fw}.values(),
                                                                                                     key=lambda x: (x["cik"], x["accn"])))
    X.write_tsv(P.news_wanted, ["ticker", "d0", "kind", "gte", "lte", "d0_symbol", "symbol_status"], nw)
    X.write_tsv(P.suspects_wanted, ["ticker", "gap_date"], [{"ticker": t, "gap_date": d} for t, d in sorted(sw)])
    say(f"- filings_wanted.tsv {len(fw):,} rows; news_wanted.tsv {len(nw):,} pulls; suspects_wanted.tsv {len(sw):,} (ticker, gap date)")
    say(f"- R67: P1 / P2 climax rows by the symbol in use at D0 (era A keys by today's symbol; Polygon news by the symbol at publication): "
        f"{dict(sorted(sym_status.items()))}; a `renamed` row's news is pulled under its D0 symbol (R69, the main loop's ruling 10-28); an "
        f"`ambiguous` row reads news unknown (`renamed_symbol`)")
    ren = sorted({(r["ticker"], r["d0_symbol"]) for r in nw if r["symbol_status"] == "renamed"})
    if ren:
        say("  renamed (series -> D0 symbol): " + ", ".join(f"{a}->{b}" for a, b in ren[:100]))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# features
# ═════════════════════════════════════════════════════════════════════════════════════════════
FEATURE_COLS = ("ticker", "d0", "era", "population", "pause_count", "run_length", "anchor", "pause_ratio",
                "news3_group", "news3_item_date", "news3_status", "news3_pages", "news3_truncated", "news3_reason",
                "mna_flag", "mna_item_date", "mna_keyword", "mna_reason", "mna_status", "mna_pages", "mna_truncated",
                "swing_group", "swing_filed", "swing_group_any", "swing_reason",
                "dilution_bucket", "dilution_ratio", "dilution_ratio_itm", "tranche_count", "dilution_accn", "dilution_filed", "dilution_reason",
                "warrant_text_present", "earnings_flag", "earnings_acceptance", "earnings_after", "earnings_reason", "sec_name", "record_name")


def features(P: X.Paths, say) -> list:
    rows = [r for r in X.read_tsv(P.climax_list) if r["duplicate_company_night"] != "1"]
    subs = FT.load_submissions(P.edgar_submissions)
    facts = FT.load_facts(P.xbrl_facts)
    inst = FT.load_instances(P.xbrl_instances)
    news = FT.load_news(P.polygon_news)
    ca = FT.load_alpaca_ca(P.alpaca_ca)
    suspects = X.read_tsv(P.distribution_suspects)
    renamed = {(w["ticker"], w["d0"]) for w in X.read_tsv(P.news_wanted) if w.get("symbol_status") == "ambiguous"}   # R69: renamed rows are pulled under the D0 symbol
    out, classes = [], []
    caps = Caps(subs, facts)
    for era in ("A", "B"):
        e = PP.load_era(P, era)
        basis = EraBasis(e)
        cal = e.cal
        for r in [q for q in rows if q["era"] == era]:
            out.append(_features_row(r, e, basis, caps, subs, facts, inst, news, cal, renamed))
        for sp in [q for q in suspects if q["era"] == era]:
            classes.append(_class_row(sp["ticker"], sp["gap_date"], era, [q for q in rows if q["ticker"] == sp["ticker"] and q["d0"] == sp["d0"]],
                                      subs, ca, cal, e, sp))
        if era == "A":
            for s, d in X.CONTROLS["distribution"]:
                i = e.bar_index(s, d)
                cik = _owner_cik_on(P, era, s)
                c = FT.distribution_class(s, d, cal, subs.get(cik), ca.get((s, d)))
                say(f"- distribution control {s} {d}: class {c['class']} ({c['evidence']}; owner CIK {cik or 'NONE'})")
                if c["class"] != "distribution":
                    raise GuardStop(f"the evidence rule does not class {s} {d} `distribution` (refused; a fix is a new registration)")
        del e
    X.write_tsv(P.features, list(FEATURE_COLS), out)
    X.write_tsv(P.distribution_class, ["ticker", "d0", "era", "population", "gap_date", "class", "evidence"], classes)
    _print_features(out, classes, say)
    expectations(say, _features_expectations(out, classes))
    return ["features", "distribution_class"]


def _owner_cik_on(P, era, symbol) -> str:
    for r in X.read_tsv(P.owners):
        if r["era"] == era and r["symbol"] == symbol and r["cik"]:
            return r["cik"]
    return ""


def _features_row(r, e, basis, caps, subs, facts, inst, news, cal, renamed=None) -> dict:
    t = e.tid[r["ticker"]]
    a, b = e.rows_of(t)
    i = e.bar_index(r["ticker"], r["d0"])
    j = i - a
    dicts = PP.ticker_dicts(e, t)
    hist = dicts[j - X.HISTORY + 1: j + 1]
    bd = date.fromisoformat(r["base_date"]) if r["base_date"] else None
    pc = FT.pause_count(hist, bd, len(hist) - 1)
    o = {"ticker": r["ticker"], "d0": r["d0"], "era": r["era"], "population": r["population"], "anchor": r["anchor"], **pc}
    o["pause_ratio"] = (pc["pause_count"] / pc["run_length"]) if pc.get("run_length") else None
    if r["population"] == "P2small":
        return o
    cik = r["owner_cik"]
    sub = subs.get(cik) if cik else None
    fac = facts.get(cik) if cik else None
    p3 = news.get((r["ticker"], r["d0"], "read3"))
    n3 = FT.news_present(_in_window(p3), (p3 or {}).get("query_symbol") or r["ticker"]) if r["anchor"] != "1" else {
        "news_group": "unknown", "news_status": "", "news_pages": 0, "news_truncated": 0, "news_item_date": "", "news_reason": "anchor_base"}
    mp = _in_window(news.get((r["ticker"], r["d0"], "mna")))
    mf = FT.mna_flag(mp, (mp or {}).get("query_symbol") or r["ticker"])                # R69: items are tagged with the symbol queried
    mf["mna_reason"] = ""
    if renamed and (r["ticker"], r["d0"]) in renamed:              # R67 / R69: an AMBIGUOUS D0 symbol reads unknown
        n3 = dict(n3, news_group="unknown", news_item_date="", news_reason="renamed_symbol")
        mf = dict(mf, mna_flag="unknown", mna_item_date="", mna_keyword="", mna_reason="renamed_symbol")
    o.update({"news3_" + k[5:]: v for k, v in n3.items()})
    o.update(mf)
    o["mna_status"], o["mna_pages"], o["mna_truncated"] = (mp or {}).get("status", ""), (mp or {}).get("pages", 0), int(bool((mp or {}).get("truncated")))
    o.update(FT.swing_feature(fac, cik, r["d0"], r["base_date"] or None))
    capd = caps.cap(r["ticker"], r["d0"], cik, basis, float(r["raw_close"]))
    base_low_raw = float(r["base_low"]) * float(r["factor_d0"]) if r["base_low"] not in ("", None) else None    # R18
    o.update(FT.dilution_feature(r["ticker"], r["d0"], cik, sub, fac, inst, basis, float(r["raw_close"]), base_low_raw, capd))
    walk_s = _sessions_after(cal, r["d0"], X.WALK_AFTER)
    ek = FT.eight_k_feature(sub, cik, r["d0"], cal, walk_s)
    for d in walk_s + [r["d0"]]:
        X.seal_date(d, "8-K window")
    o.update({"earnings_flag": ek["earnings_flag"], "earnings_acceptance": ek["earnings_acceptance"],
              "earnings_after": "|".join(ek["earnings_after"]), "earnings_reason": ek["earnings_reason"]})
    o["sec_name"], o["record_name"] = (sub or {}).get("name", ""), r["owner_name"]
    return o


def _in_window(pull: "dict | None") -> "dict | None":
    """A feature never reads an item dated outside its own window (the WOULD-FAIL-IF 'a feature dated after its cut-off'): items whose
    published_utc falls outside [gte, lte] are dropped (a vendor quirk; counted in `_outside`), then asserted."""
    if not pull or pull.get("status") != 200:
        return pull
    lo, hi = pull.get("gte") or "", pull.get("lte") or ""
    norm = lambda t: (t or "").replace("+00:00", "Z")
    keep = [it for it in (pull.get("items") or []) if lo <= norm(it.get("published_utc")) <= hi]
    out = dict(pull, items=keep, _outside=len(pull.get("items") or []) - len(keep))
    if any(norm(it.get("published_utc")) > hi for it in keep):
        raise GuardStop("a news item dated after its window reached a feature")
    return out


def _class_row(ticker, gap_date, era, climax_rows, subs, ca, cal, e, sp) -> dict:
    cik = climax_rows[0]["owner_cik"] if climax_rows else ""
    c = FT.distribution_class(ticker, gap_date, cal, subs.get(cik) if cik else None, ca.get((ticker, gap_date)))
    return {"ticker": ticker, "d0": sp["d0"], "era": era, "population": sp["population"], "gap_date": gap_date, "class": c["class"],
            "evidence": c["evidence"]}


def _features_expectations(out, classes) -> list:
    res = []
    for pop in ("P1", "P2"):
        sub = [r for r in out if r["population"] == pop]
        ge = sum(1 for r in sub if r.get("dilution_bucket") == "ge20")
        lt = sum(1 for r in sub if r.get("dilution_bucket") == "lt20")
        res.append((f"{pop}: the read-5 known buckets are under 30 each (CAN'T TELL expected)", (ge < 30 and lt < 30) if sub else None,
                    f">= 20% {ge}, < 20% {lt}"))
        tr = sum(1 for r in sub if str(r.get("news3_truncated")) == "1") + sum(1 for r in sub if str(r.get("mna_truncated")) == "1")
        res.append((f"{pop}: truncated news pulls are under 1% of pulls", (tr < 0.01 * 2 * len(sub)) if sub else None, f"{tr} of {2 * len(sub)}"))
        yrs = defaultdict(Counter)
        for r in sub:
            yrs[r["d0"][:4]][r.get("news3_group")] += 1
        sh = [(y, c["present"] / (c["present"] + c["absent"])) for y, c in sorted(yrs.items()) if c["present"] + c["absent"]]
        rises = (sh[-1][1] > sh[0][1]) if len(sh) >= 2 else None
        res.append((f"{pop}: the share 'present' in read 3 rises across 2016 -> 2024", rises, ", ".join(f"{y} {v:.0%}" for y, v in sh)))
    d = sum(1 for c in classes if c["class"] == "distribution")
    res.append(("under 10% of the distribution suspects are classed `distribution`", (d < 0.1 * len(classes)) if classes else None,
                f"{d} of {len(classes)}"))
    return res


def _print_features(out, classes, say) -> None:
    for pop in ("P1", "P2"):
        sub = [r for r in out if r["population"] == pop]
        say(f"\n### {pop}: the reads' groups before any walk (N per group; unknown reasons)")
        say(f"- read 2 pause count <= 2 / >= 3 / unknown: {sum(1 for r in sub if r['pause_count'] is not None and r['pause_count'] <= 2)} / "
            f"{sum(1 for r in sub if r['pause_count'] is not None and r['pause_count'] >= 3)} / {sum(1 for r in sub if r['pause_count'] is None)}; "
            f"anchor bases {sum(1 for r in sub if str(r['anchor']) == '1')}")
        for col, nm in (("news3_group", "read 3 news"), ("swing_group", "read 4 swing (primary)"), ("swing_group_any", "read 4 swing (beside)"),
                        ("dilution_bucket", "read 5 dilution"), ("mna_flag", "row (a) M&A keyword"), ("earnings_flag", "8-K item 2.02")):
            say(f"- {nm}: {dict(Counter(r.get(col) for r in sub))}")
        for col in ("news3_reason", "mna_reason", "swing_reason", "dilution_reason", "earnings_reason"):
            say(f"  {col}: {dict(Counter(r.get(col) for r in sub if r.get(col)))}")
        tr = sum(1 for r in sub if str(r.get("news3_truncated")) == "1") + sum(1 for r in sub if str(r.get("mna_truncated")) == "1")
        say(f"- truncated news pulls: {tr} of {2 * len(sub)} ({X.pct(tr, 2 * len(sub))}; expectation: under 1%)")
        yrs = defaultdict(Counter)
        for r in sub:
            yrs[r["d0"][:4]][r.get("news3_group")] += 1
        say("- read 3 share present by D0 year: " + ", ".join(f"{y} {X.pct(c['present'], c['present'] + c['absent'])}" for y, c in sorted(yrs.items())))
        known = [r for r in sub if r.get("dilution_bucket") in ("ge20", "lt20")]
        say(f"- read 5 coverage: names with a CIK {sum(1 for r in sub if r.get('dilution_reason') != 'no_cik')}, parsed with a ratio {len(known)}, "
            f"tranches paired {sum(int(r.get('tranche_count') or 0) for r in known)}; ratio-0 names with the warrant text tag "
            f"{sum(1 for r in known if r.get('dilution_ratio') == 0 and str(r.get('warrant_text_present')) == '1')} (the tranche parser's bound)")
    cc = Counter(c["class"] for c in classes)
    say(f"\n- distribution suspects classed: {dict(cc)} (expectation: under 10% `distribution`)")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the walk subprocess (one per population)
# ═════════════════════════════════════════════════════════════════════════════════════════════
EP_EXTRA = ("ticker", "d0", "era", "calendar_file", "population", "company_key", "gone", "refetch_sourced", "cap", "tier", "jump_unevidenced",
            "void_adjustment_event", "distribution_suspect", "distribution_class", "open_at_seal", "pre_hole", "alias_outside_span", "pre_break")


def walk_pop(P: X.Paths, pop: str) -> int:
    t0 = time.time()
    bad = child_refusal(P, "--walk-pop", pop)
    if bad:
        print(f"[walk {pop}] REFUSED:\n  - " + "\n  - ".join(bad), flush=True)
        return 2
    if pop == "P1":
        const = PP.assert_dollar_vol_const("P1")
    else:
        PP.patch_p2_constant()
        const = PP.assert_dollar_vol_const("P2")
    print(f"[walk {pop}] _MIN_DOLLAR_VOL_TODAY = {const:,}", flush=True)
    pdm = PP.detector_module()
    rows = [r for r in X.read_tsv(P.climax_list) if r["population"] == pop and r["duplicate_company_night"] != "1"]
    feats = {(r["ticker"], r["d0"], r["population"]): r for r in X.read_tsv(P.features)}
    cls = {(r["ticker"], r["d0"], r["population"]): r["class"] for r in X.read_tsv(P.distribution_class)}
    out = []
    for era in ("A", "B"):
        e = PP.load_era(P, era)
        era_last = e.cal[-1]
        brk = {}
        for r in breaks_from_file(P, era):
            if r["applied"] == "yes" and r["kind"] == "jump":
                brk.setdefault(r["symbol"], []).append(r["date"])
        by_t = defaultdict(list)
        for r in rows:
            if r["era"] == era:
                by_t[r["ticker"]].append(r)
        for s, rs in by_t.items():
            t = e.tid[s]
            a, b = e.rows_of(t)
            dicts = PP.ticker_dicts(e, t)
            ci_arr = e.D.ci[a:b]
            raw = e.raw[a:b]
            for r in sorted(rs, key=lambda q: q["d0"]):
                if r["calendar_file"] != cal_file_of(P, era) or r["calendar_sha256"] != X.sha(r["calendar_file"]):
                    raise GuardStop(f"a climax row carries another calendar than its era's ({s} {r['d0']} era {era})")
                i = e.bar_index(s, r["d0"])
                j = i - a
                hist = dicts[j - X.HISTORY + 1: j + 1]
                cap = None if r["cap"] in ("", None) else int(float(r["cap"]))
                res = pdm.compute_parabolic_metrics(hist, market_cap=(1 if pop == "P2small" else cap), is_earnings_today=None)
                if res.get("stage") != "climax":
                    raise GuardStop(f"the walk's climax set differs from the pinned climax_list.tsv: ({s}, {r['d0']}, {pop}) reads {res.get('stage')}")
                base = {k: r.get(k, "") for k in EP_EXTRA}
                base["distribution_class"] = cls.get((s, r["d0"], pop), "")
                if r["open_at_seal"] == "1":
                    out.append({**base, "r5_status": "open_at_seal", "decision": ""})
                    continue
                cut = r.get("owner_delisted") if era == "B" and r.get("owner_delisted") not in ("", "active") else None
                f = feats.get((s, r["d0"], pop), {})
                ea = frozenset(date.fromisoformat(d) for d in (f.get("earnings_after") or "").split("|") if d)
                ep = W.walk_one(dicts, ci_arr, j, r["d0"], e.cal, era_last, cut, raw, ea)
                ep.update(_d3_variant(dicts, j, ep))
                fwd_dates = e.cal[e.D.ci[i] + 1: e.D.ci[i] + 1 + X.WALK_AFTER]
                ep["jump_in_walk"] = int(any(d in fwd_dates for d in brk.get(s, [])))
                _walk_asserts(ep, r, e.cal)
                for k in ("news3_group", "swing_group", "swing_group_any", "dilution_bucket", "dilution_ratio", "dilution_ratio_itm", "mna_flag",
                          "earnings_flag", "pause_count", "run_length", "pause_ratio", "anchor"):
                    ep[k] = f.get(k, "")
                out.append({**base, **ep, "decision": ""})
        print(f"[walk {pop}] era {era}: {sum(1 for o in out if o['era'] == era):,} episodes walked ({time.time() - t0:.0f}s)", flush=True)
        del e
    cols = sorted({k for o in out for k in o})
    X.write_tsv(P.o(f"episodes_part_{pop}.tsv"), cols, out)
    print(f"[walk {pop}] WALK COMPLETE", flush=True)
    return 0


def _d3_variant(dicts, j, ep) -> dict:
    """R53: exit at the close of D0 + 3 (time_stop = 4 - k, k = the entry's offset from D0)."""
    from agents.market_intelligence import parabolic_short_shadow as psh
    if not ep.get("r5_entry_date"):
        return {"d3_status": ep.get("r5_status"), "d3_r": None}
    hist_fwd = dicts[j - X.HISTORY + 1: j + 1 + X.WALK_AFTER]
    ci = X.HISTORY - 1
    k = next(q for q in range(1, len(hist_fwd) - ci) if hist_fwd[ci + q]["trade_date"].isoformat() == ep["r5_entry_date"])
    r = psh.replay_episode(hist_fwd[: ci + 1 + min(X.WALK_AFTER, ep["forward_bars"])], ci, stop_price=ep["stop_price"],
                           armed_on=hist_fwd[ci]["trade_date"], time_stop=max(1, 4 - k))
    o = r.get("outcome") or {}
    return {"d3_status": o.get("status") or r["state"], "d3_r": o.get("realized_r") if o.get("status") == "settled" else None}


def _walk_asserts(ep, r, cal) -> None:
    import bisect
    d0 = r["d0"]
    for lab, maxoff in (("r5", 4), ("r3", 2)):
        if ep.get(f"{lab}_status") == "settled":
            en, ex = ep[f"{lab}_entry_date"], ep[f"{lab}_exit_date"]
            if en <= d0:
                raise GuardStop(f"a settled episode whose entry {en} <= D0 {d0}")
            if bisect.bisect_left(cal, ex) - bisect.bisect_left(cal, en) > maxoff:
                raise GuardStop(f"a settled episode ({lab}) whose exit {ex} is more than {maxoff} sessions after its entry {en}")
            X.seal_date(ex, "walk exit")
    if ep.get("r5_entry_date") and ep.get("r3_entry_date") and ep["r5_entry_date"] != ep["r3_entry_date"]:
        raise GuardStop(f"a read-1 pair whose two walks differ in entry ({r['ticker']} {d0})")
    if ep.get("last_walked_date"):
        X.seal_date(ep["last_walked_date"], "walk")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the walk stage (the parent)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def walk(P: X.Paths, say) -> int:
    R = _R()
    R.header(say, "WALK (the one run)", P)
    problems = R.gate_walk(P)
    if problems:
        say("WALK REFUSED:")
        for q in problems:
            say("  - " + q)
        say.write(P.refused)
        return 2
    try:
        import tempfile
        bad = GD.detector_golden_check(say) + GD.walk_goldens(tempfile.mkdtemp(prefix="ps314_goldens_"), say)
        if bad:
            raise GuardStop("a golden failed: " + "; ".join(bad))
        open(P.episodes + ".partial", "w").close()          # claims the run (a second run refuses on it)
        for pop in POPS:
            say(f"- walking {pop} (its own process) ...")
            run_sub(P, "--walk-pop", pop, P.o(f"walk_{pop}.log"))
        eps = []
        for pop in POPS:
            eps += X.read_tsv(P.o(f"episodes_part_{pop}.tsv"))
        eps = [_typed(e) for e in eps]
        decide_all(eps)
        cols = sorted({k for e in eps for k in e})
        X.write_tsv(P.episodes + ".partial", cols, eps)
        os.replace(P.episodes + ".partial", P.episodes)
        res = W.results(eps, say)
        expectations(say, _walk_expectations(eps, res))
        for era in ("A", "B"):
            g8(P, eps, era, say)
        mine = os.path.join(P.out, "ps_replay_numbers.json")
        with open(mine, "w") as fh:
            json.dump(res["numbers"], fh, sort_keys=True)
        theirs = os.path.join(P.out, "ps_rederive_numbers.json")
        rc = subprocess.run([sys.executable, os.path.join(HERE, "ps_rederive.py"), P.episodes, theirs]).returncode
        if rc != 0:
            raise GuardStop(f"ps_rederive.py exited {rc}")
        diff = compare_numbers(json.load(open(mine)), json.load(open(theirs)))
        if diff:
            raise GuardStop("VERDICT MISMATCH against the independent re-derivation: " + "; ".join(diff[:20]))
        say("VERDICT MATCH (ps_rederive.py, pandas only, from episodes.tsv alone)")
    except GuardStop as ex:
        say(f"\nWALK STOPPED: {ex}")
        say.write(P.refused)
        return 3
    say("WALK COMPLETE")
    say.write(P.result)
    X.ledger_append(P.ledger, STAGE + "walk:episodes", P.episodes)
    X.ledger_append(P.ledger, STAGE + "walk:result", P.result)
    return 0


NUMERIC = ("r5_r", "r3_r", "d3_r", "e5_r", "e3_r", "r5_pnl_adr", "r5_r_slip1", "r5_r_slip2", "r5_pnl_adr_slip1", "r5_pnl_adr_slip2",
           "r5_r_last_close", "r5_r_haircut", "r5_pnl_adr_last_close", "r5_pnl_adr_haircut", "e5_pnl_adr", "cap", "pause_count", "run_length",
           "pause_ratio", "dilution_ratio", "dilution_ratio_itm")


def _typed(e: dict) -> dict:
    out = dict(e)
    for k in NUMERIC:
        if k in out:
            out[k] = None if out[k] in ("", None, "None", "nan") else float(out[k])
    return out


def in_n(e: dict, label: str = "r5", decision: str = "decision") -> bool:
    """n = settled, admitted by rule (c), not voided (adjustment event; a `distribution`-classed suspect)."""
    return (e.get(decision) == "admitted" and e.get(f"{label}_status") == "settled" and str(e.get("void_adjustment_event")) != "1"
            and e.get("distribution_class") != "distribution")


def decide_all(eps: list) -> None:
    """Rule (c) per population for the primary and for every beside row that drops climaxes (R49)."""
    for pop in POPS:
        sub = [e for e in eps if e["population"] == pop]
        W.apply_open_rule(sub, "company_key", "r5", "decision")
        _assert_one_open(sub)
        if pop == "P2small":
            continue                                   # R29: base numbers only
        jr = [e for e in sub if str(e.get("jump_unevidenced")) != "1"]
        W.apply_open_rule(jr, "company_key", "r5", "decision_jump_removed")
        if pop == "P1":
            fl = [e for e in sub if e.get("cap") is not None and e["cap"] >= 250_000_000]
            W.apply_open_rule(fl, "company_key", "r5", "decision_cap_floor")
        mn = [e for e in sub if e.get("mna_flag") != "flagged"]
        W.apply_open_rule(mn, "company_key", "r5", "decision_mna")
        ek = [e for e in sub if e.get("earnings_flag") == "none"]
        W.apply_open_rule(ek, "company_key", "e5", "decision_8k")


def _assert_one_open(sub: list) -> None:
    """WOULD-FAIL-IF: a name with two open episodes on one night — the admitted episodes of one company key never overlap."""
    by = defaultdict(list)
    for e in sub:
        if e.get("decision") == "admitted":
            by[e["company_key"]].append((e["d0"], W.closes_on(e) or "9999-12-31"))
    for k, iv in by.items():
        iv.sort()
        for (a0, a1), (b0, _b1) in zip(iv, iv[1:]):
            if b0 < a1:
                raise GuardStop(f"two open episodes on one company key {k}: {a0}..{a1} and {b0}")


def compare_numbers(a: dict, b: dict, tol: float = 1e-9) -> list:
    out = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            if not ((np.isnan(x) and np.isnan(y)) or abs(x - y) <= tol * max(1.0, abs(x))):
                out.append(f"{k}: {x} vs {y}")
        elif x != y:
            out.append(f"{k}: {x!r} vs {y!r}")
    return out


def _walk_expectations(eps, res) -> list:
    out = []
    nums = res["numbers"]
    g, s_ = nums.get("base:P2:pooled:mean_r"), None
    gy, gn = nums.get("gone_yes:P2:mean_r"), nums.get("gone_no:P2:mean_r")
    out.append(("the gone companies carry a HIGHER settled mean R than the survivors in P2",
                (gy > gn) if (gy is not None and gn is not None and not np.isnan(gy) and not np.isnan(gn)) else None, f"gone {gy}, survivors {gn}"))
    for pop in ("P1", "P2"):
        armed = [e for e in eps if e["population"] == pop and e.get("decision") == "admitted" and e.get("r5_status") != "open_at_seal"]
        ended = [e for e in armed if e.get("r5_status") == "ended_mid_walk"]
        out.append((f"{pop}: ended_mid_walk is under 5% of armed episodes", (len(ended) < 0.05 * len(armed)) if armed else None,
                    f"{len(ended)} of {len(armed)}"))
        if pop == "P2":
            c = Counter(e.get("r5_ended_class") for e in ended)
            out.append(("P2: the ended_mid_walk collapse group outnumbers its pinned group", (c["collapse"] > c["pinned"]) if ended else None, dict(c)))
    return out


def g8(P: X.Paths, eps: list, era: str, say) -> None:
    """R50: the data standard's G8 on the settled list (trade_impact.py --kind r1); a non-zero after-cutoff / past-last-bar count refuses."""
    rows = [e for e in eps if e["era"] == era and e.get("r5_status") == "settled"]
    if not rows:
        say(f"- G8 era {era}: no settled episode")
        return
    path = P.o(f"g8_trades_{era}.tsv")
    with open(path, "w") as fh:
        fh.write("cell\tattempt\tticker\tentry_date\texit_j\trealized_r\n")
        for e in rows:
            fh.write(f"PS314\t0\t{e['ticker']}\t{e['r5_entry_date']}\t{int(float(e['r5_sessions_held'])) - 1}\t{e['r5_r']}\n")
    flags = P.flags_A if era == "A" else P.flags_B
    export = P.export_A if era == "A" else P.export_B
    cut = X.A_LAST if era == "A" else X.CUT_B
    cmd = [sys.executable, os.path.join(X.REPO, "scripts", "backtest_data_audit", "trade_impact.py"), "--flags", flags, "--export", export,
           "--trades", path, "--label", f"PS314-{era}", "--cutoff", cut, "--kind", "r1", "--cell", "PS314"]
    txt = subprocess.run(cmd, capture_output=True, text=True).stdout
    with open(P.o(f"g8_{era}.txt"), "w") as fh:
        fh.write(txt)
    after = _int_after(txt, "trades entered after the cutoff")
    past = _int_after(txt, "trades whose hold runs past the last bar kept")
    say(f"- G8 era {era}: entered after the cutoff {after}; holds past the last kept bar {past} ({os.path.basename(P.o(f'g8_{era}.txt'))})")
    if after != 0 or past != 0:
        raise GuardStop(f"G8 era {era}: {after} entered after the cutoff, {past} holds past the last kept bar")


def _int_after(txt: str, label: str) -> "int | None":
    for ln in txt.splitlines():
        if label in ln:
            try:
                return int(ln.rsplit(":", 1)[1].strip().split()[0])
            except (ValueError, IndexError):
                return None
    return None
