#!/usr/bin/env python3
"""#314 replay — STEP 0's pulls (plan §Security type, identity and CIK; §One cap rule; §Reads 3-5; §Distribution artifacts). Runs ON THE
PRODUCTION SERVER by the main loop after review (the Polygon key lives only there; secrets from the env, never printed). Written and
tested OFFLINE through an injectable transport; `--dry-run` makes NO network call and says what `--run` would request.

THREE PHASES (R6 in ps_population), each its own invocation, each resumable (a record already in the output is not re-fetched):
  --reference    Polygon /v3/reference/tickers, market=stocks, limit=1000, TWICE (active=true, active=false), `next_url` followed to
                 the end -> polygon_reference.jsonl.gz (every record + `_pull` + `_pulled_at`). Needs POLYGON_API_KEY. No input file.
  --edgar        for every CIK in candidate_ciks.txt (written by `ps_replay.py --step0 derive`; the two distribution controls' owning
                 CIKs included): data.sec.gov/submissions/CIK##########.json (+ every older file it lists under filings.files) ->
                 edgar_submissions.jsonl.gz, and data.sec.gov/api/xbrl/companyfacts/CIK##########.json -> xbrl_facts.jsonl.gz with the
                 FACT_TAGS only (the whole response is not kept: a large filer's companyfacts is 10+ MB). The SEC asks <= 10 requests a
                 second and a descriptive User-Agent (collector._SEC_UA, as the nightly recorders use). Needs no key.
  --instances    for every (cik, accn, primaryDocument) in filings_wanted.tsv (written by `--step0 climax`): the filing index
                 (www.sec.gov/Archives/edgar/data/<cik>/<accn>/index.json) then the XBRL INSTANCE named there (`*_htm.xml` for inline
                 XBRL, else the dated `<prefix>-<yyyymmdd>.xml`) -> xbrl_instances.jsonl.gz: the contexts (period, dimension members)
                 and the facts of INSTANCE_TAGS with their context, the instance's sha256 and size, `--keep-raw` stores the bytes (R30).
  --news         for every (ticker, d0, kind, gte, lte) in news_wanted.tsv (written by `--step0 climax`; two rows per climax — read 3's
                 three-session window and row (a)'s [D0 - 30d, D0]): Polygon /v2/reference/news, ticker=, published_utc.gte / .lte as
                 full timestamps, limit=1000, order=desc, sort=published_utc, `next_url` followed for at most K = 3 pages; a 3rd page
                 that still carries a next_url = `truncated` -> polygon_news.jsonl.gz (status, pages, truncated, the items' title,
                 description, published_utc, publisher, tickers, insights). Needs POLYGON_API_KEY.
  --alpaca-ca    for every (ticker, gap_date) in suspects_wanted.tsv (written by `--step0 climax`): data.alpaca.markets/v1/corporate-
                 actions?symbols=&start=gap-7d&end=gap+3d&limit=1000 -> alpaca_corporate_actions.jsonl.gz. Needs the paper keys.

READINGS (continued; the main loop decides):
  R30 `xbrl_instances.jsonl.gz` holds the PARSED instance (every context's period and dimension members; every fact of the plan's
      warrant / convertible / cover tags with its context, unit and decimals; the warrant title text tag's presence) plus the raw
      instance's sha256 and byte size — the facts the plan reads "WITH its context" — rather than the raw XML (1-10 MB each; the raw
      bytes are kept under `--keep-raw` as a sibling `xbrl_instances_raw/` folder, never in the jsonl).
  R31 EDGAR's older filing files (`filings.files[]`, present for filers with over ~1,000 filings) are fetched and concatenated behind
      `recent`, so a 2016 D0 of a heavy filer still finds its periodic report.
  R32 Retries: 3 attempts with back-off on 429 / 5xx / a transport error; a final 4xx is the ANSWER and is recorded as the status
      (a 404 CIK is `no_submissions` downstream, never retried into a guess).
  R56 (a plan deviation, flagged for the main loop) Read 3 says "the runner calls `collector._polygon_get` DIRECTLY and records the
      HTTP status". `_polygon_get` cannot record a status — it RAISES on a non-200 after `llm_health.maybe_alert_api_failure`, the
      #380 loud-failure guard that pages Telegram on a sustained failure — and it takes a path + params, so `next_url` (a full URL
      with a cursor) is not followed. A research pull of thousands of windows on the production server must not page the operator
      on a 5xx, so the news stage uses this module's transport: the same endpoint and parameters, the status recorded per pull,
      every failure / non-200 = unknown downstream (the plan's intent: never `get_polygon_news`'s silent []). Switching to the
      collector call is a small change if he rules it.
  R64 (review 10-28) A record is final only on 200, a 4xx about the data (404 / 410 / 400 ...) or the instance stage's own 595-597;
      429 / 408 / 401 / 403 / 5xx / 598 / 599 are transient and re-requested on resume (the first build kept every failure as the
      answer, so one outage made permanent unknowns). SEC's 403 is its rate-limit answer: retried with a 60 / 120 / 180 s back-off,
      then the pull STOPS (resume later) rather than record 403s CIK after CIK. Each older submissions file's status is recorded; a
      failed one marks the CIK `older_files_failed` with `coverage_from` = the recent block's first filing date (downstream every
      lookup that needs a filing before that date reads unknown, never "none"); the CIK is re-requested on resume only while an
      older file's status is transient (a 404 / 410 is SEC's answer: the record is done and stays holed). `PULL COMPLETE` is printed only when every wanted record has a final answer; else `PULL INCOMPLETE`,
      the keys listed, exit 4. The reference pull is a whole rewrite: a stale `.partial` from a failed attempt is removed first
      (R63; appending to it doubled every record).
  R57 `--out` points the pulls at the server's copy of the STEP 0 folder (the inputs candidate_ciks.txt / *_wanted.tsv are copied
      there from apollo_data/ps314/ and the outputs copied back); the default is the local folder.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import ps_common as X  # noqa: E402

POLYGON = "https://api.polygon.io"
SEC_SUB = "https://data.sec.gov/submissions/"
SEC_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data/"
ALPACA_CA = "https://data.alpaca.markets/v1/corporate-actions"
POLYGON_DELAY, SEC_DELAY, ALPACA_DELAY = 0.2, 0.15, 0.25        # seconds between requests (SEC: under 10 a second)
FACT_TAGS = ("dei:EntityCommonStockSharesOutstanding", "us-gaap:NetIncomeLoss")
INSTANCE_TAGS = ("us-gaap:ClassOfWarrantOrRightNumberOfSecuritiesCalledByWarrantsOrRights", "us-gaap:ClassOfWarrantOrRightOutstanding",
                 "us-gaap:ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1", "us-gaap:DebtInstrumentConvertibleNumberOfEquityInstruments",
                 "us-gaap:DebtInstrumentConvertibleConversionPrice1", "us-gaap:ConvertibleNotesPayable", "us-gaap:ConvertibleDebt",
                 "us-gaap:ConvertibleNotesPayableCurrent", "us-gaap:ConvertibleDebtCurrent", "us-gaap:ConvertibleDebtNoncurrent",
                 "us-gaap:ConvertibleNotesPayableNoncurrent", "dei:EntityCommonStockSharesOutstanding", "dei:DocumentPeriodEndDate")
INSTANCE_TEXT_TAGS = ("us-gaap:ClassOfWarrantOrRightTitleOfSecurityWarrantsOrRightsOutstanding",)
STAGES = ("reference", "edgar", "instances", "news", "alpaca_ca")


class PullStop(Exception):
    pass


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the transport (R32) — the ONLY place a socket is opened; the tests inject a fake
# ═════════════════════════════════════════════════════════════════════════════════════════════
class Transport:
    def __init__(self, delay: float = 0.0, log=None):
        self.delay, self.log, self.n = delay, log, 0
        self._last = 0.0

    def _wait(self):
        now = time.monotonic()
        if now - self._last < self.delay:
            time.sleep(self.delay - (now - self._last))
        self._last = time.monotonic()

    def get(self, url: str, headers: dict = None, timeout: int = 60) -> tuple:
        """-> (status, bytes | None). 3 attempts on 429 / 5xx / transport errors; a final 4xx is returned as the answer."""
        last = None
        for k in range(3):
            self._wait()
            self.n += 1
            try:
                req = urllib.request.Request(url, headers=headers or {})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = r.read()
                    if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                        data = gzip.decompress(data)
                    return (r.status, data)
            except urllib.error.HTTPError as e:
                last = e.code
                if e.code == 429 or e.code >= 500:
                    time.sleep(5 * (k + 1))
                    continue
                if e.code == 403 and "sec.gov" in url:          # SEC's rate-limit answer (R64): a long back-off, never the answer
                    time.sleep(60 * (k + 1))
                    continue
                return (e.code, None)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = f"error:{type(e).__name__}"
                time.sleep(5 * (k + 1))
                continue
        return (last if isinstance(last, int) else 599, None)

    def get_json(self, url: str, headers: dict = None, timeout: int = 60) -> tuple:
        st, data = self.get(url, headers, timeout)
        if data is None:
            return (st, None)
        try:
            return (st, json.loads(data.decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            return (598, None)


class FakeTransport:
    """The tests' transport: `routes` = {url substring or exact url: (status, payload bytes | obj)}; counts every call."""

    def __init__(self, routes: dict, delay: float = 0.0):
        self.routes, self.n, self.urls = routes, 0, []

    def get(self, url: str, headers: dict = None, timeout: int = 60) -> tuple:
        self.n += 1
        self.urls.append(url)
        if url in self.routes:
            st, payload = self.routes[url]
        else:
            hit = [k for k in self.routes if k in url]
            if not hit:
                return (404, None)
            st, payload = self.routes[max(hit, key=len)]
        if payload is None:
            return (st, None)
        if isinstance(payload, (bytes, bytearray)):
            return (st, bytes(payload))
        return (st, json.dumps(payload).encode("utf-8"))

    def get_json(self, url: str, headers: dict = None, timeout: int = 60) -> tuple:
        st, data = self.get(url, headers, timeout)
        if data is None:
            return (st, None)
        try:
            return (st, json.loads(data.decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            return (598, None)


class NoNetwork:
    """The dry run's transport: any call is a defect."""

    def get(self, *_a, **_k):
        raise PullStop("--dry-run made a network call")

    get_json = get


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the output files: one JSON per line, gzip, resumable
# ═════════════════════════════════════════════════════════════════════════════════════════════
TRANSIENT_4XX = (401, 403, 408, 429)       # a key / rate-limit / timeout answer: about the request, never about the data (R64)
FINAL_SYNTHETIC = (595, 596, 597)          # the instance stage's own answers: unparseable instance / none named / empty index


def is_final(status) -> bool:
    """R64: a record is the ANSWER (never re-requested) only on 200, a 4xx about the data (404 / 410 / 400 ...), or the instance stage's
    own 595-597; 429 / 408 / 401 / 403 / 5xx / 598 (bad JSON) / 599 (transport error) are transient: re-requested on resume."""
    if status == 200 or status in FINAL_SYNTHETIC:
        return True
    return isinstance(status, int) and 400 <= status < 500 and status not in TRANSIENT_4XX


def rec_done(r: dict) -> bool:
    """Done = a final status AND every older submissions file a final answer. A HOLED record (an older file != 200, `older_files_failed`)
    whose older files all answered finally (a 404 / 410: SEC lists a file it no longer serves) is done — re-requesting it would never
    change it and would hold PULL COMPLETE and the climax gate shut forever; it still reads unknown before its `coverage_from`."""
    return is_final(r.get("status")) and all(is_final(o.get("status")) for o in (r.get("older_files") or []))


def sec_rate_limited(st, url: str) -> None:
    """R64: a 403 from SEC that survived the transport's 60 / 120 / 180 s back-off is a sustained block — stop (resume later), never
    record it CIK after CIK."""
    if st == 403:
        raise PullStop(f"SEC is rate-limiting (403 after the back-off) on {url}: wait 10 minutes, then re-run the same command to resume")


def latest_records(path: str, key_fn) -> dict:
    """{key: the LAST record written for it} (a resume appends; the loaders keep the last one too)."""
    out = {}
    if not os.path.exists(path):
        return out
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for ln in fh:
                if ln.strip():
                    try:
                        r = json.loads(ln)
                        out[key_fn(r)] = r
                    except (ValueError, KeyError):
                        continue
    except (EOFError, OSError, zlib.error) as ex:     # a pull killed without closing its gzip member
        raise PullStop(f"{path} is cut short ({type(ex).__name__}): a resume would append behind a broken member — move it aside and "
                       f"re-run, or rewrite it from its readable records first")
    return out


def existing_keys(path: str, key_fn, done=rec_done) -> set:
    """The keys whose LAST record is a final answer (R64): a transient failure is re-requested on resume, never kept as the answer."""
    return {k for k, r in latest_records(path, key_fn).items() if done(r)}


def not_done(path: str, key_fn, wanted, done=rec_done) -> list:
    """The wanted keys with no final record in `path` (absent, or transient on its last attempt) — the coverage test (R64)."""
    have = existing_keys(path, key_fn, done)
    return [k for k in wanted if k not in have]


STAGE_OF = {"edgar_submissions": "edgar", "xbrl_facts": "edgar", "xbrl_instances": "instances", "polygon_news": "news", "alpaca_ca": "alpaca-ca"}
KEYS = {"edgar_submissions": lambda r: r["cik"], "xbrl_facts": lambda r: r["cik"], "xbrl_instances": lambda r: (r["cik"], r["accn"]),
        "polygon_news": lambda r: (r["ticker"], r["d0"], r["kind"]), "alpaca_ca": lambda r: (r["ticker"], r["gap_date"])}


class Writer:
    def __init__(self, path: str, mode: str = "at"):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self.fh = gzip.open(path, mode, encoding="utf-8")
        self.n = 0

    def write(self, rec: dict) -> None:
        self.fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
        self.n += 1
        if self.n % 50 == 0:
            self.fh.flush()

    def close(self) -> None:
        self.fh.close()


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def sec_headers() -> dict:
    """collector._SEC_UA at --run (the app's own SEC User-Agent); the dry run never imports the collector."""
    try:
        from agents.market_intelligence.collector import _SEC_UA
        return dict(_SEC_UA)
    except Exception:
        return {"User-Agent": os.environ.get("SEC_USER_AGENT", "Apollo Research"), "Accept-Encoding": "gzip, deflate"}


def polygon_key() -> str:
    k = os.environ.get("POLYGON_API_KEY", "")
    if not k:
        raise PullStop("POLYGON_API_KEY is not set (this stage runs on the production server)")
    return k


def alpaca_headers() -> dict:
    a, b = os.environ.get("ALPACA_PAPER_API_KEY", ""), os.environ.get("ALPACA_PAPER_SECRET_KEY", "")
    if not a or not b:
        raise PullStop("ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET_KEY are not set")
    return {"APCA-API-KEY-ID": a, "APCA-API-SECRET-KEY": b}


def with_key(url: str, key: str) -> str:
    return url + ("&" if "?" in url else "?") + "apiKey=" + key


# ═════════════════════════════════════════════════════════════════════════════════════════════
# --reference
# ═════════════════════════════════════════════════════════════════════════════════════════════
def reference_plan(P: X.Paths) -> dict:
    return {"endpoint": f"{POLYGON}/v3/reference/tickers?market=stocks&active=<true|false>&limit=1000 (+ next_url pages)",
            "requests": "one page per 1,000 records, both pulls: about 12 pages active (~11-12k active stock records); the delisted count is "
                        "not measured on this machine (the 10-23 refetch pulled active=false on the server and logged no count) — tens of pages",
            "run_time": "minutes at a 0.2 s courtesy delay", "output": P.polygon_reference, "key": "POLYGON_API_KEY"}


def pull_reference(P: X.Paths, tr, say=print) -> dict:
    key = polygon_key()
    out = P.polygon_reference
    if os.path.exists(out):
        raise PullStop(f"{out} exists — the reference pull is made once (delete it by hand to redo)")
    if os.path.exists(out + ".partial"):                 # R63: a failed earlier attempt; this pull is a whole rewrite, never a resume
        os.remove(out + ".partial")
        say(f"- reference: removed a stale {os.path.basename(out)}.partial from a failed earlier attempt")
    w = Writer(out + ".partial", mode="wt")
    stats = {"active": 0, "delisted": 0, "pages": 0}
    try:
        for active in ("true", "false"):
            url = with_key(f"{POLYGON}/v3/reference/tickers?" + urllib.parse.urlencode({"market": "stocks", "active": active, "limit": 1000}), key)
            while url:
                st, obj = tr.get_json(url)
                stats["pages"] += 1
                if st != 200 or obj is None:
                    raise PullStop(f"reference pull: page {stats['pages']} returned {st}")
                for r in obj.get("results") or []:
                    r["_pull"] = "active" if active == "true" else "delisted"
                    r["_pulled_at"] = now_iso()
                    w.write(r)
                    stats["active" if active == "true" else "delisted"] += 1
                nxt = obj.get("next_url")
                url = with_key(nxt, key) if nxt else None
    finally:
        w.close()
    os.replace(out + ".partial", out)
    say(f"- reference: {stats['active']:,} active + {stats['delisted']:,} delisted records over {stats['pages']} pages -> {out}")
    return stats


# ═════════════════════════════════════════════════════════════════════════════════════════════
# --edgar (submissions + companyfacts)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def read_ciks(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return sorted({ln.strip().zfill(10) for ln in fh if ln.strip() and not ln.startswith("#")})


def edgar_plan(P: X.Paths) -> dict:
    ciks = read_ciks(P.candidate_ciks)
    n = len(ciks)
    return {"endpoint": f"{SEC_SUB}CIK##########.json (+ filings.files[]) and {SEC_FACTS}CIK##########.json",
            "ciks": n, "requests": f"about {int(n * 2.3):,} ({n:,} CIKs x (1 submissions + ~0.3 older files + 1 companyfacts))" if n else
            "n CIKs x ~2.3 (candidate_ciks.txt is not written yet: run `ps_replay.py --step0 derive` first)",
            "run_time": f"about {n * 2.3 * SEC_DELAY / 60:.0f} minutes at {SEC_DELAY} s a request" if n else "n x 2.3 x 0.15 s",
            "outputs": [P.edgar_submissions, P.xbrl_facts], "key": "none (SEC User-Agent from collector._SEC_UA / SEC_USER_AGENT)"}


def _filings_from(block: dict) -> list:
    n = len(block.get("form") or [])
    cols = ("form", "filingDate", "reportDate", "acceptanceDateTime", "accessionNumber", "primaryDocument", "items", "isXBRL")
    out = []
    for i in range(n):
        out.append({c: (block.get(c) or [None] * n)[i] for c in cols})
    return out


def pull_edgar(P: X.Paths, tr, say=print, ciks: list = None) -> dict:
    hdr = sec_headers()
    ciks = ciks if ciks is not None else read_ciks(P.candidate_ciks)
    if not ciks:
        raise PullStop(f"{P.candidate_ciks} is missing or empty — run `ps_replay.py --step0 derive` first")
    done_sub = existing_keys(P.edgar_submissions, KEYS["edgar_submissions"])
    done_fac = existing_keys(P.xbrl_facts, KEYS["xbrl_facts"])
    ws, wf = Writer(P.edgar_submissions), Writer(P.xbrl_facts)
    stats = {"ciks": len(ciks), "submissions_ok": 0, "submissions_fail": 0, "facts_ok": 0, "facts_fail": 0, "older_files": 0, "skipped": 0}
    try:
        for i, cik in enumerate(ciks):
            if cik in done_sub and cik in done_fac:
                stats["skipped"] += 1
                continue
            if cik not in done_sub:
                st, obj = tr.get_json(f"{SEC_SUB}CIK{cik}.json", headers=hdr)
                sec_rate_limited(st, f"{SEC_SUB}CIK{cik}.json")
                rec = {"cik": cik, "status": st, "pulled_at": now_iso()}
                if st == 200 and obj:
                    fl = _filings_from((obj.get("filings") or {}).get("recent") or {})
                    recent_dates = [f["filingDate"] for f in fl if f.get("filingDate")]
                    older = (obj.get("filings") or {}).get("files") or []
                    ostat = []
                    for f in older:
                        name = f.get("name")
                        if not name:
                            continue
                        st2, o2 = tr.get_json(f"{SEC_SUB}{name}", headers=hdr)
                        sec_rate_limited(st2, f"{SEC_SUB}{name}")
                        stats["older_files"] += 1
                        ostat.append({"name": name, "status": st2 if (st2 != 200 or o2) else 597})
                        if st2 == 200 and o2:
                            fl += _filings_from(o2)
                    failed = [o for o in ostat if o["status"] != 200]
                    rec.update({"name": obj.get("name"), "formerNames": obj.get("formerNames"), "tickers": obj.get("tickers"), "sic": obj.get("sic"),
                                "fiscalYearEnd": obj.get("fiscalYearEnd"), "filings": fl, "files_fetched": len(older), "older_files": ostat,
                                # R64: a failed older file leaves a hole before the recent block -> filings before it read unknown, never none
                                "older_files_failed": bool(failed), "coverage_from": min(recent_dates) if recent_dates else ""})
                    if failed:
                        stats["older_files_failed"] = stats.get("older_files_failed", 0) + 1
                    stats["submissions_ok"] += 1
                else:
                    stats["submissions_fail"] += 1
                ws.write(rec)
            if cik not in done_fac:
                st, obj = tr.get_json(f"{SEC_FACTS}CIK{cik}.json", headers=hdr, timeout=120)
                sec_rate_limited(st, f"{SEC_FACTS}CIK{cik}.json")
                rec = {"cik": cik, "status": st, "pulled_at": now_iso()}
                if st == 200 and obj:
                    facts = {}
                    allf = obj.get("facts") or {}
                    for tag in FACT_TAGS:
                        ns, local = tag.split(":")
                        entry = (allf.get(ns) or {}).get(local)
                        if not entry:
                            continue
                        rows = []
                        for unit, lst in (entry.get("units") or {}).items():
                            for e in lst:
                                rows.append({"unit": unit, "accn": e.get("accn"), "end": e.get("end"), "start": e.get("start"), "filed": e.get("filed"),
                                             "form": e.get("form"), "fp": e.get("fp"), "fy": e.get("fy"), "frame": e.get("frame"), "val": e.get("val")})
                        facts[tag] = rows
                    rec.update({"entityName": obj.get("entityName"), "facts": facts})
                    stats["facts_ok"] += 1
                else:
                    stats["facts_fail"] += 1
                wf.write(rec)
            if (i + 1) % 100 == 0:
                say(f"  edgar {i + 1:,} / {len(ciks):,}")
    finally:
        ws.close(); wf.close()
    left = sorted(set(not_done(P.edgar_submissions, KEYS["edgar_submissions"], ciks)) | set(not_done(P.xbrl_facts, KEYS["xbrl_facts"], ciks)))
    stats["transient"], stats["transient_keys"] = len(left), left[:20]
    say(f"- edgar: {stats}")
    return stats


# ═════════════════════════════════════════════════════════════════════════════════════════════
# --instances
# ═════════════════════════════════════════════════════════════════════════════════════════════
def read_filings_wanted(path: str) -> list:
    if not os.path.exists(path):
        return []
    rows = X.read_tsv(path)
    seen, out = set(), []
    for r in rows:
        k = (r["cik"].zfill(10), r["accn"])
        if k in seen:
            continue
        seen.add(k)
        out.append({"cik": k[0], "accn": r["accn"], "primaryDocument": r.get("primaryDocument", ""), "form": r.get("form", ""),
                    "filingDate": r.get("filingDate", "")})
    return out


def instances_plan(P: X.Paths) -> dict:
    n = len(read_filings_wanted(P.filings_wanted))
    return {"endpoint": f"{SEC_ARCHIVES}<cik>/<accn>/index.json then the instance named there", "filings": n,
            "requests": f"{2 * n:,} ({n:,} filings x (index + instance))" if n else "2 x distinct filings (filings_wanted.tsv is not written yet: run `--step0 climax` first)",
            "run_time": f"about {2 * n * SEC_DELAY / 60:.0f} minutes plus download time (1-10 MB each)" if n else "2 x n x 0.15 s + downloads",
            "output": P.xbrl_instances, "key": "none (SEC User-Agent)"}


_NS_PREFIX = {"fasb.org/us-gaap": "us-gaap", "xbrl.sec.gov/dei": "dei", "xbrl.org/2003/instance": "xbrli", "xbrl.org/2006/xbrldi": "xbrldi"}


def ns_prefix(tag: str) -> tuple:
    """'{http://fasb.org/us-gaap/2023}Foo' -> ('us-gaap', 'Foo'); an unknown namespace -> ('', 'Foo')."""
    if tag.startswith("{"):
        uri, local = tag[1:].split("}", 1)
        for k, v in _NS_PREFIX.items():
            if k in uri:
                return (v, local)
        return ("", local)
    return ("", tag)


def parse_instance(data: bytes) -> dict:
    """R30: the contexts and the facts of INSTANCE_TAGS from an XBRL instance document."""
    contexts, facts, text_present = {}, [], set()
    period_end = None
    root = ET.fromstring(data)
    for el in root.iter():
        p, local = ns_prefix(el.tag)
        if p == "xbrli" and local == "context":
            cid = el.get("id")
            c = {"instant": None, "start": None, "end": None, "dims": []}
            for sub in el.iter():
                sp, sl = ns_prefix(sub.tag)
                if sp == "xbrli" and sl == "instant":
                    c["instant"] = (sub.text or "").strip()
                elif sp == "xbrli" and sl == "startDate":
                    c["start"] = (sub.text or "").strip()
                elif sp == "xbrli" and sl == "endDate":
                    c["end"] = (sub.text or "").strip()
                elif sp == "xbrldi" and sl == "explicitMember":
                    c["dims"].append([sub.get("dimension") or "", (sub.text or "").strip()])
            c["dims"].sort()
            contexts[cid] = c
            continue
        if el.get("contextRef") is None:
            continue
        full = f"{p}:{local}" if p else local
        if full in INSTANCE_TEXT_TAGS:
            text_present.add(full)
        if full in INSTANCE_TAGS:
            val = (el.text or "").strip()
            facts.append({"tag": full, "context": el.get("contextRef"), "value": val, "unit": el.get("unitRef"), "decimals": el.get("decimals")})
            if full == "dei:DocumentPeriodEndDate" and val and period_end is None:
                period_end = val
    return {"period_end": period_end, "contexts": contexts, "facts": facts, "text_tags_present": sorted(text_present)}


def pick_instance(index: dict, primary: str) -> "str | None":
    """The instance document's file name from the filing index: `*_htm.xml`, else the dated `<prefix>-<yyyymmdd>.xml` (never the
    _cal / _def / _lab / _pre linkbases or FilingSummary.xml)."""
    items = ((index.get("directory") or {}).get("item") or [])
    names = [it.get("name") or "" for it in items]
    htm = [n for n in names if n.endswith("_htm.xml")]
    if htm:
        return htm[0]
    dated = [n for n in names if re.fullmatch(r"[a-z0-9]+-\d{8}\.xml", n, flags=re.I)]
    if dated:
        return dated[0]
    other = [n for n in names if n.endswith(".xml") and not re.search(r"_(cal|def|lab|pre|ref)\.xml$", n) and n != "FilingSummary.xml"]
    return other[0] if other else None


def pull_instances(P: X.Paths, tr, say=print, keep_raw: bool = False) -> dict:
    hdr = sec_headers()
    wanted = read_filings_wanted(P.filings_wanted)
    if not wanted:
        raise PullStop(f"{P.filings_wanted} is missing or empty — run `ps_replay.py --step0 climax` first")
    done = existing_keys(P.xbrl_instances, KEYS["xbrl_instances"])
    w = Writer(P.xbrl_instances)
    stats = {"filings": len(wanted), "ok": 0, "no_index": 0, "no_instance": 0, "fetch_fail": 0, "parse_fail": 0, "skipped": 0}
    raw_dir = os.path.join(os.path.dirname(P.xbrl_instances), "xbrl_instances_raw")
    try:
        for i, f in enumerate(wanted):
            key = (f["cik"], f["accn"])
            if key in done:
                stats["skipped"] += 1
                continue
            nodash = f["accn"].replace("-", "")
            base = f"{SEC_ARCHIVES}{int(f['cik'])}/{nodash}/"
            rec = {"cik": f["cik"], "accn": f["accn"], "status": None, "instance_url": "", "instance_name": "", "sha256": "", "bytes": 0,
                   "period_end": None, "contexts": {}, "facts": [], "text_tags_present": [], "pulled_at": now_iso()}
            st, idx = tr.get_json(base + "index.json", headers=hdr)
            sec_rate_limited(st, base + "index.json")
            if st != 200 or not idx:
                rec["status"] = st if st != 200 else 597
                stats["no_index"] += 1
                w.write(rec)
                continue
            name = pick_instance(idx, f.get("primaryDocument", ""))
            if not name:
                rec["status"] = 596
                stats["no_instance"] += 1
                w.write(rec)
                continue
            st, data = tr.get(base + name, headers=hdr, timeout=180)
            sec_rate_limited(st, base + name)
            rec["instance_url"], rec["instance_name"] = base + name, name
            if st != 200 or data is None:
                rec["status"] = st
                stats["fetch_fail"] += 1
                w.write(rec)
                continue
            rec["sha256"], rec["bytes"] = hashlib.sha256(data).hexdigest(), len(data)
            try:
                rec.update(parse_instance(data))
                rec["status"] = 200
                stats["ok"] += 1
            except ET.ParseError:
                rec["status"] = 595
                stats["parse_fail"] += 1
            if keep_raw:
                os.makedirs(raw_dir, exist_ok=True)
                with open(os.path.join(raw_dir, f"{f['cik']}_{nodash}_{name}"), "wb") as fh:
                    fh.write(data)
            w.write(rec)
            if (i + 1) % 100 == 0:
                say(f"  instances {i + 1:,} / {len(wanted):,}")
    finally:
        w.close()
    left = not_done(P.xbrl_instances, KEYS["xbrl_instances"], [(f["cik"], f["accn"]) for f in wanted])
    stats["transient"], stats["transient_keys"] = len(left), left[:20]
    say(f"- instances: {stats}")
    return stats


# ═════════════════════════════════════════════════════════════════════════════════════════════
# --news
# ═════════════════════════════════════════════════════════════════════════════════════════════
def read_news_wanted(path: str) -> list:
    return X.read_tsv(path) if os.path.exists(path) else []


def news_plan(P: X.Paths) -> dict:
    n = len(read_news_wanted(P.news_wanted))
    return {"endpoint": f"{POLYGON}/v2/reference/news?ticker=&published_utc.gte=&published_utc.lte=&limit=1000&order=desc&sort=published_utc (<= {X.NEWS_PAGES_K} pages)",
            "pulls": n, "requests": f"{n:,} to {X.NEWS_PAGES_K * n:,} ({n:,} pulls x 1-{X.NEWS_PAGES_K} pages; most windows fit one page)" if n else
            "2 pulls per climax x 1-3 pages (news_wanted.tsv is not written yet: run `--step0 climax` first)",
            "run_time": f"about {n * 1.1 * POLYGON_DELAY / 60:.0f} minutes" if n else "n x 1.1 x 0.2 s", "output": P.polygon_news, "key": "POLYGON_API_KEY"}


def pull_news(P: X.Paths, tr, say=print) -> dict:
    key = polygon_key()
    wanted = read_news_wanted(P.news_wanted)
    if not wanted:
        raise PullStop(f"{P.news_wanted} is missing or empty — run `ps_replay.py --step0 climax` first")
    done = existing_keys(P.polygon_news, KEYS["polygon_news"])
    w = Writer(P.polygon_news)
    stats = {"pulls": len(wanted), "ok": 0, "fail": 0, "truncated": 0, "skipped": 0, "pages": 0}
    keep = ("title", "description", "published_utc", "tickers", "insights")
    try:
        for i, r in enumerate(wanted):
            k = (r["ticker"], r["d0"], r["kind"])
            if k in done:
                stats["skipped"] += 1
                continue
            url = with_key(f"{POLYGON}/v2/reference/news?" + urllib.parse.urlencode({"ticker": r["ticker"], "published_utc.gte": r["gte"], "published_utc.lte": r["lte"],
                                                                                   "limit": X.NEWS_PAGE_LIMIT, "order": "desc", "sort": "published_utc"}), key)
            rec = {"ticker": r["ticker"], "d0": r["d0"], "kind": r["kind"], "gte": r["gte"], "lte": r["lte"], "status": None, "pages": 0, "truncated": False,
                   "items": [], "pulled_at": now_iso()}
            while url and rec["pages"] < X.NEWS_PAGES_K:
                st, obj = tr.get_json(url)
                rec["pages"] += 1
                stats["pages"] += 1
                rec["status"] = st
                if st != 200 or obj is None:
                    break
                for it in obj.get("results") or []:
                    item = {c: it.get(c) for c in keep}
                    item["publisher"] = (it.get("publisher") or {}).get("name", "")
                    rec["items"].append(item)
                nxt = obj.get("next_url")
                url = with_key(nxt, key) if nxt else None
                if url and rec["pages"] >= X.NEWS_PAGES_K:
                    rec["truncated"] = True
            if rec["status"] == 200:
                stats["ok"] += 1
            else:
                stats["fail"] += 1
            if rec["truncated"]:
                stats["truncated"] += 1
            w.write(rec)
            if (i + 1) % 200 == 0:
                say(f"  news {i + 1:,} / {len(wanted):,}")
    finally:
        w.close()
    left = not_done(P.polygon_news, KEYS["polygon_news"], [(r["ticker"], r["d0"], r["kind"]) for r in wanted])
    stats["transient"], stats["transient_keys"] = len(left), left[:20]
    say(f"- news: {stats}")
    return stats


# ═════════════════════════════════════════════════════════════════════════════════════════════
# --alpaca-ca
# ═════════════════════════════════════════════════════════════════════════════════════════════
def read_suspects_wanted(path: str) -> list:
    return X.read_tsv(path) if os.path.exists(path) else []


def alpaca_plan(P: X.Paths) -> dict:
    n = len(read_suspects_wanted(P.suspects_wanted))
    return {"endpoint": f"{ALPACA_CA}?symbols=&start=gap-7d&end=gap+3d&limit=1000", "suspects": n,
            "requests": f"{n:,}" if n else "one per distinct (ticker, gap date) suspect (suspects_wanted.tsv is not written yet: run `--step0 climax` first)",
            "run_time": f"about {n * ALPACA_DELAY / 60:.0f} minutes" if n else "n x 0.25 s", "output": P.alpaca_ca, "key": "ALPACA_PAPER_API_KEY / SECRET"}


def pull_alpaca_ca(P: X.Paths, tr, say=print) -> dict:
    hdr = alpaca_headers()
    wanted = read_suspects_wanted(P.suspects_wanted)
    if not wanted:
        raise PullStop(f"{P.suspects_wanted} is missing or empty — run `ps_replay.py --step0 climax` first")
    done = existing_keys(P.alpaca_ca, KEYS["alpaca_ca"])
    w = Writer(P.alpaca_ca)
    stats = {"suspects": len(wanted), "ok": 0, "fail": 0, "skipped": 0}
    try:
        for r in wanted:
            k = (r["ticker"], r["gap_date"])
            if k in done:
                stats["skipped"] += 1
                continue
            g = date.fromisoformat(r["gap_date"])
            start, end = (g - timedelta(days=7)).isoformat(), (g + timedelta(days=3)).isoformat()
            url = f"{ALPACA_CA}?" + urllib.parse.urlencode({"symbols": r["ticker"], "start": start, "end": end, "limit": 1000})
            st, obj = tr.get_json(url, headers=hdr)
            rec = {"ticker": r["ticker"], "gap_date": r["gap_date"], "start": start, "end": end, "status": st,
                   "actions": (obj or {}).get("corporate_actions") if st == 200 else None, "pulled_at": now_iso()}
            stats["ok" if st == 200 else "fail"] += 1
            w.write(rec)
    finally:
        w.close()
    left = not_done(P.alpaca_ca, KEYS["alpaca_ca"], [(r["ticker"], r["gap_date"]) for r in wanted])
    stats["transient"], stats["transient_keys"] = len(left), left[:20]
    say(f"- alpaca corporate actions: {stats}")
    return stats


# ═════════════════════════════════════════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════════════════════════════════════════
PLANS = {"reference": reference_plan, "edgar": edgar_plan, "instances": instances_plan, "news": news_plan, "alpaca_ca": alpaca_plan}
PULLS = {"reference": pull_reference, "edgar": pull_edgar, "instances": pull_instances, "news": pull_news, "alpaca_ca": pull_alpaca_ca}


def main(argv=None, transport=None, paths: X.Paths = None, say=print) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    for s in STAGES:
        g.add_argument("--" + s.replace("_", "-"), dest="stage", action="store_const", const=s)
    m = ap.add_mutually_exclusive_group(required=True)
    m.add_argument("--dry-run", action="store_true")
    m.add_argument("--run", action="store_true")
    ap.add_argument("--keep-raw", action="store_true", help="--instances: also keep the raw instance bytes beside the jsonl (R30)")
    ap.add_argument("--out", default="", help="the folder holding the STEP 0 files (candidate_ciks.txt, *_wanted.tsv) and the pulls "
                                              "(R57: the server's copy of apollo_data/ps314/; default the local one)")
    a = ap.parse_args(argv)
    P = paths or (X.Paths(out=a.out) if a.out else X.LOCAL)
    plan = PLANS[a.stage](P)
    say(f"## ps_pull --{a.stage.replace('_', '-')} {'DRY RUN' if a.dry_run else 'RUN'} ({now_iso()})")
    for k, v in plan.items():
        say(f"- {k}: {v}")
    if a.dry_run:
        tr = NoNetwork()
        say("- network: none (dry run); the run needs the key named above in the environment")
        say("DRY RUN COMPLETE")
        return 0
    tr = transport or Transport(delay={"reference": POLYGON_DELAY, "news": POLYGON_DELAY, "alpaca_ca": ALPACA_DELAY}.get(a.stage, SEC_DELAY))
    try:
        if a.stage == "instances":
            st = PULLS[a.stage](P, tr, say=say, keep_raw=a.keep_raw)
        else:
            st = PULLS[a.stage](P, tr, say=say)
    except PullStop as e:
        say(f"PULL STOPPED: {e}")
        return 3
    if (st or {}).get("transient"):
        say(f"PULL INCOMPLETE: {a.stage}: {st['transient']:,} wanted records have no final answer (transient status or a failed older "
            f"file; re-run the same command to retry them): {st['transient_keys']}")
        return 4
    say(f"PULL COMPLETE: {a.stage} ({getattr(tr, 'n', '?')} requests)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
