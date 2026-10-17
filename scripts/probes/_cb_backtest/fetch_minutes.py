#!/usr/bin/env python3
"""#702 P2a stage 4 — fetch Alpaca SIP 1-minute bars (Adjustment.SPLIT, regular hours) for a
(ticker|date) list. READ-ONLY market data: it writes files, never a table. P3 runs it in the prod
container (which holds the Alpaca data keys); it is NOT run by the build card.

  python fetch_minutes.py --list minute_fetch_list.tsv [--out /tmp/cb702_minutes] [--min-tier 0]
                          [--per-request 50] [--sleep 0.25] [--limit-dates N] [--dry-run]

Input   one `ticker|date` per line (extra `|`-columns ignored; `tier` column honoured by --min-tier; a header
        line is skipped). The runner's DATA/out/minute_fetch_list.tsv is tab-separated: pass it through
        `tr '\\t' '|'` or just use it as is - both separators are accepted.
Output  <out>/<date>.psv.gz   `ticker|minute_since_0930|o|h|l|c|v`, minute 0..389 (09:30..15:59 ET).
        Each SYMBOL's rows are appended as its own gzip member, compressed in memory and written with one
        `write()` (valid multi-member gzip; `gzip.open` / `zcat` read it as one stream). A kill mid-write can
        still leave a truncated last member, so `fetch_date` first runs `repair_gz` on the date file: it keeps
        every complete member and drops the truncated tail - nothing in _done is ever lost, because a
        symbol's done-line is written only AFTER its member. A crash between a member and its done-line
        re-fetches that symbol on resume - READERS KEEP THE LAST BLOCK PER (date, ticker).
        <out>/_done.psv       `date|ticker|n_bars|status` (status ok | empty) - the resume log: a pair listed
                              here is never fetched again. `empty` = Alpaca returned no regular-hours bar.
        <out>/_failed.psv     `date|ticker|error` - pairs that errored; NOT in _done, so a re-run retries them.
        <out>/fetch.log       progress + errors (never the keys).

Time handling: every window is built with zoneinfo America/New_York (09:30 .. 16:00 exclusive) and every
returned timestamp is converted back to ET before the minute offset is taken - DST-proof, no pytz, no naive
datetimes. 50 symbols per request grouped by date (pattern: scripts/probes/_623_fetch_bars.py); one bad
symbol never stops the run (a failed chunk falls back to one request per symbol); a rate-limit answer backs
off and retries. Credentials: ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET_KEY, else ALPACA_API_KEY /
ALPACA_SECRET_KEY (as agents/market_intelligence/collector.py does); never printed.
"""
from __future__ import annotations

import argparse
import gzip
import os
import sys
import time as _time
import zlib
from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
OPEN_MINUTE = 9 * 60 + 30            # 09:30 ET in minutes since midnight
LAST_MINUTE = 389                    # 15:59 ET
DONE_NAME, FAILED_NAME, LOG_NAME = "_done.psv", "_failed.psv", "fetch.log"


# ── pure helpers (unit-tested) ──────────────────────────────────────────────────────────────
def parse_list(path: Path, min_tier: int = 0) -> dict:
    """{date: sorted unique tickers}. Accepts `|` or tab separators; the third column, when present and an
    integer, is the tier (rows below `min_tier` are dropped). Lines whose second field is not an ISO date
    (a header) are skipped."""
    out: dict = defaultdict(set)
    for line in Path(path).read_text().splitlines():
        f = line.replace("\t", "|").strip().split("|")
        if len(f) < 2 or not f[0]:
            continue
        try:
            d = date.fromisoformat(f[1])
        except ValueError:
            continue
        if len(f) >= 3 and f[2].strip().lstrip("-").isdigit() and int(f[2]) < min_tier:
            continue
        out[d].add(f[0].strip())
    return {d: sorted(t) for d, t in sorted(out.items())}


def minute_since_open(ts: datetime):
    """Minutes since 09:30 ET for a tz-aware timestamp; None outside regular hours (09:30..15:59)."""
    if ts.tzinfo is None:
        raise ValueError("naive timestamp - Alpaca bars are tz-aware; refusing to guess a zone")
    e = ts.astimezone(_ET)
    m = e.hour * 60 + e.minute - OPEN_MINUTE
    return m if 0 <= m <= LAST_MINUTE else None


def window(d: date) -> tuple:
    """(start, end) for the regular session of `d`, tz-aware ET; end = 16:00 exclusive."""
    return (datetime.combine(d, time(9, 30), tzinfo=_ET), datetime.combine(d, time(16, 0), tzinfo=_ET))


def format_rows(sym: str, bars) -> list:
    """`ticker|minute|o|h|l|c|v` lines for the regular-hours bars of one symbol (ascending minute)."""
    rows = []
    for b in bars:
        m = minute_since_open(b.timestamp)
        if m is not None:
            rows.append(f"{sym}|{m}|{b.open}|{b.high}|{b.low}|{b.close}|{b.volume}")
    return rows


def load_done(out_dir: Path) -> set:
    """{(date, ticker)} already fetched, from the resume log."""
    p = Path(out_dir) / DONE_NAME
    done = set()
    if p.exists():
        for line in p.read_text().splitlines():
            f = line.split("|")
            if len(f) >= 2:
                try:
                    done.add((date.fromisoformat(f[0]), f[1]))
                except ValueError:
                    pass
    return done


def chunks(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def _append(path: Path, text: str) -> None:
    with open(path, "a") as fh:
        fh.write(text)
        fh.flush()


def _append_gz(path: Path, lines: list) -> None:
    """Append `lines` as ONE new gzip member, compressed in memory and written with a single write()."""
    if lines:
        blob = gzip.compress(("\n".join(lines) + "\n").encode(), mtime=0)
        with open(path, "ab") as fh:
            fh.write(blob)
            fh.flush()


def _members_end(raw: bytes) -> int:
    """End offset of the last COMPLETE gzip member in `raw` (0 if none). Streams each member through zlib in
    64 KB slices so a many-member file costs O(size), not O(size x members). A truncated member, a CRC
    mismatch, or trailing garbage all stop the scan at the last good boundary."""
    n, pos = len(raw), 0
    while pos < n:
        d = zlib.decompressobj(wbits=31)                       # 31 = gzip wrapper (header + CRC trailer checked)
        q = pos
        try:
            while q < n and not d.eof:
                chunk = raw[q:q + 65536]
                d.decompress(chunk)
                q += len(chunk)
        except zlib.error:
            return pos
        if not d.eof:                                          # ran out of bytes inside a member: truncated
            return pos
        pos = q - len(d.unused_data)
    return pos


def repair_gz(path: Path) -> int:
    """Make `path` a clean multi-member gzip: keep every complete leading member, drop a truncated or corrupt
    tail (what a kill during `_append_gz` leaves behind - a reader would stop at it, and every later member
    appended on resume would be unreadable). Returns the bytes dropped (0 = clean or absent). The rewrite goes
    to a temp file and is renamed over the original, so the repair itself cannot lose the good members."""
    path = Path(path)
    if not path.exists():
        return 0
    raw = path.read_bytes()
    good = _members_end(raw)
    dropped = len(raw) - good
    if dropped:
        tmp = path.with_name(path.name + ".repair.tmp")
        tmp.write_bytes(raw[:good])
        os.replace(tmp, path)
    return dropped


# ── Alpaca (imported lazily: the helpers above need no alpaca-py) ────────────────────────────
def _client():
    from alpaca.data.historical import StockHistoricalDataClient
    key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY")
    sec = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
    if not key or not sec:
        raise SystemExit("no Alpaca credentials in env (ALPACA_PAPER_API_KEY/_SECRET_KEY or ALPACA_API_KEY/_SECRET_KEY)")
    return StockHistoricalDataClient(key, sec)


def _request(symbols: list, d: date):
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    start, end = window(d)
    return StockBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Minute, start=start, end=end,
                            feed=DataFeed.SIP, adjustment=Adjustment.SPLIT, limit=None)


def _get(client, symbols: list, d: date, log, tries: int = 4):
    """Bars for `symbols` on `d`, or None after `tries` failures. Rate-limit answers back off harder."""
    for k in range(tries):
        try:
            return client.get_stock_bars(_request(symbols, d)).data
        except Exception as e:                                       # noqa: BLE001 - one bad chunk never stops the run
            msg = f"{type(e).__name__}: {str(e)[:160]}"
            limited = "429" in msg or "rate" in msg.lower() or "too many" in msg.lower()
            log(f"  ! {d} {len(symbols)} syms try {k + 1}/{tries}: {msg}")
            _time.sleep((10.0 if limited else 2.0) * (k + 1))
    return None


def fetch_date(client, d: date, tickers: list, out_dir: Path, per_request: int, sleep_s: float, log) -> tuple:
    """Fetch every ticker of one date; returns (n_ok, n_empty, n_failed)."""
    ok = empty = failed = 0
    path = out_dir / f"{d.isoformat()}.psv.gz"
    dropped = repair_gz(path)                       # a kill mid-append leaves a truncated member; cut it off first
    if dropped:
        log(f"  ! {d}: dropped {dropped:,} bytes of a truncated gzip tail (their pairs have no done-line; re-fetched)")

    def settle(sym, bars):
        nonlocal ok, empty
        rows = format_rows(sym, bars or [])
        _append_gz(path, rows)
        _append(out_dir / DONE_NAME, f"{d.isoformat()}|{sym}|{len(rows)}|{'ok' if rows else 'empty'}\n")
        ok, empty = ok + (1 if rows else 0), empty + (0 if rows else 1)

    for chunk in chunks(tickers, per_request):
        data = _get(client, chunk, d, log)
        _time.sleep(sleep_s)
        if data is not None:
            for sym in chunk:
                settle(sym, data.get(sym))
            continue
        for sym in chunk:                                            # the chunk failed: isolate the bad symbol
            one = _get(client, [sym], d, log, tries=2)
            _time.sleep(sleep_s)
            if one is None:
                failed += 1
                _append(out_dir / FAILED_NAME, f"{d.isoformat()}|{sym}|request failed\n")
                log(f"  ! {d} {sym}: gave up")
            else:
                settle(sym, one.get(sym))
    return ok, empty, failed


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--list", required=True, help="ticker|date list (the runner's minute_fetch_list.tsv)")
    ap.add_argument("--out", default="/tmp/cb702_minutes")
    ap.add_argument("--min-tier", type=int, default=0, help="drop list rows whose tier column is below this")
    ap.add_argument("--per-request", type=int, default=50)
    ap.add_argument("--sleep", type=float, default=0.25, help="seconds between requests")
    ap.add_argument("--limit-dates", type=int, default=0, help="only the first N pending dates (smoke test)")
    ap.add_argument("--dry-run", action="store_true", help="parse + count what would be fetched; no network")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    todo_all = parse_list(Path(args.list), args.min_tier)
    done = load_done(out)
    todo = {d: [t for t in ts if (d, t) not in done] for d, ts in todo_all.items()}
    todo = {d: ts for d, ts in todo.items() if ts}
    if args.limit_dates:
        todo = dict(list(todo.items())[:args.limit_dates])
    n_pairs = sum(len(v) for v in todo.values())
    reqs = sum(-(-len(v) // args.per_request) for v in todo.values())
    msg = (f"list: {sum(len(v) for v in todo_all.values()):,} pairs over {len(todo_all):,} dates; already done "
           f"{len(done):,}; to fetch {n_pairs:,} pairs over {len(todo):,} dates (~{reqs:,} requests)")

    def log(m: str) -> None:
        print(m, file=sys.stderr, flush=True)
        _append(out / LOG_NAME, f"{datetime.now(_ET):%Y-%m-%d %H:%M:%S} {m}\n")

    log(msg)
    if args.dry_run:
        return
    client = _client()
    tot = [0, 0, 0]
    for k, (d, ts) in enumerate(todo.items(), 1):
        ok, empty, failed = fetch_date(client, d, ts, out, args.per_request, args.sleep, log)
        tot = [tot[0] + ok, tot[1] + empty, tot[2] + failed]
        log(f"{d} [{k}/{len(todo)}] {len(ts)} syms: ok {ok} empty {empty} failed {failed}  (cum ok {tot[0]:,} empty {tot[1]:,} failed {tot[2]:,})")
    log(f"done: ok {tot[0]:,} empty {tot[1]:,} failed {tot[2]:,}")


if __name__ == "__main__":
    main()
