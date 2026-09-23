#!/usr/bin/env python3
"""#333 measurement task (this session) — Finnhub /calendar/earnings probe across the
live alert population (trailing 90 days, ~176 tickers from mi_ep_alerts).

READ-ONLY, $0, stdlib-only (no pip installs on the host). Reads FINNHUB_API_KEY by
hand-parsing the .env file at ENV_PATH below (no python-dotenv dependency on the
host). NEVER prints or writes the key: every exception is stringified through
_redact() before it touches stdout or the output file, and the key is held in a
single local variable that is never included in any dict written to disk.

Output: ONE JSON file (OUT_PATH) containing only non-secret Finnhub response fields
(symbol/date/quarter/year/epsEstimate/epsActual/revenueEstimate/revenueActual) per
ticker, plus a small error map. Capture once, read many (CLAUDE.md cost-efficiency
rule) — this script is meant to run exactly once.

Delete this file and its output from the server after the local copy is pulled down
(scp) — it is a throwaway probe, never committed, never left running.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

ENV_PATH = "/home/apollo/apollo_the_wise/.env"
OUT_PATH = "/tmp/_333cov_finnhub_out.json"
BASE = "https://finnhub.io/api/v1/calendar/earnings"  # v2 redirects (302 -> "/") and yields
                                                        # an empty body; v1 is the real path
                                                        # (matches analyst_estimates_recorder.
                                                        # FINNHUB_BASE) — caught via a raw curl
                                                        # probe after the first run 176/176 errored
PACE_SECONDS = 1.1          # well under the ~60 calls/min budget the task set
CALENDAR_WINDOW_DAYS = 200  # ~2 quarters ahead, matches the recorder's own window

TICKERS = ["ABCL", "ABSI", "ACAD", "ACHR", "ACMR", "AEHR", "AEIS", "AEVA", "AGX", "AKTS", "AMLX", "AMRC", "APPS", "ARGX", "ARM", "ARWR", "ATRO", "AUGO", "AVAV", "BE", "BLSH", "BLZE", "BRUN", "BTDR", "BULL", "BW", "CAI", "CAT", "CBRL", "CBRS", "CGEM", "CHRN", "CHTR", "CLF", "CLSK", "COHU", "CORT", "CORZ", "CRCL", "CRMD", "CRSR", "CRWD", "CRWV", "DCTH", "DFTX", "DG", "DOCN", "DOCS", "ECG", "EFOR", "ELVN", "EME", "EROC", "ETON", "FCEL", "FET", "FIGS", "FLNC", "FRMI", "FROG", "FTK", "FTNT", "GLBE", "GRND", "HAS", "HGTY", "HLIT", "HOOD", "HQ", "HRB", "HTFL", "HUT", "HYMC", "IDCC", "IDR", "INOD", "INSM", "INSP", "IREN", "JBIO", "JBL", "KC", "KMT", "KODK", "KTOS", "KURA", "KYMR", "LFST", "LIFE", "LIND", "LPTH", "LRCX", "LZB", "MANE", "MLTX", "MMYT", "MPWR", "MRNA", "MRVL", "MRX", "MTW", "MU", "NAVN", "NBIS", "NESR", "NET", "NMAX", "NNE", "NRIX", "NVCR", "NWL", "OKTA", "OMER", "ONTO", "OUST", "PENG", "PLTR", "PRAA", "PRG", "PRGO", "PSIX", "PUBM", "PWR", "QBTS", "QDEL", "QNST", "QURE", "RARE", "RDDT", "RDW", "RIOT", "ROCK", "RPD", "RXT", "SCSC", "SE", "SEDG", "SG", "SHAZ", "SIMO", "SITM", "SLN", "SMCI", "SNOW", "SNX", "SOLS", "SOUN", "STDN", "SWBI", "SYRE", "TASK", "TATT", "TEAM", "TEM", "TER", "TEVA", "TH", "THC", "TRUP", "TSAT", "TSEM", "TWLO", "TWST", "U", "UUUU", "VEEV", "VERA", "VOYG", "WDFC", "WEN", "WKC", "WLDN", "WULF", "WYFI", "XE", "ZBRA"]  # full 90-day live-source alert population (176 tickers)


def _read_key(path: str) -> str:
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("FINNHUB_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _redact(text: str, key: str) -> str:
    return text.replace(key, "***REDACTED***") if key else text


def main() -> None:
    api_key = _read_key(ENV_PATH)
    if not api_key:
        print("NO_KEY")
        return

    today = date.today()
    to = today + timedelta(days=CALENDAR_WINDOW_DAYS)
    data: dict = {}
    errors: dict = {}

    for i, ticker in enumerate(TICKERS):
        params = {
            "token": api_key,
            "symbol": ticker,
            "from": today.isoformat(),
            "to": to.isoformat(),
        }
        url = f"{BASE}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            cal = payload.get("earningsCalendar") if isinstance(payload, dict) else None
            data[ticker] = cal if isinstance(cal, list) else []
        except Exception as e:  # noqa: BLE001 — probe script, every failure just gets counted
            errors[ticker] = _redact(f"{type(e).__name__}: {e}", api_key)
        if (i + 1) % 20 == 0:
            print(f"...{i + 1}/{len(TICKERS)}")
        time.sleep(PACE_SECONDS)

    with open(OUT_PATH, "w") as f:
        json.dump({"data": data, "errors": errors}, f)
    print(f"DONE {len(data)} tickers, {len(errors)} errors -> {OUT_PATH}")


if __name__ == "__main__":
    main()
