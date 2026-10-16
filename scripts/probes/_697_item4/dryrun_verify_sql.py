"""#697 item 4 - prove `verify_live.sql` can tell a working stamp from a broken one BEFORE it is pointed at prod.

Loads the replayed rows (the REAL detector, `replay_equiv.replay`) and the bars into DuckDB under the production table
names, runs the exact text of verify_live.sql statement 2 (psql variables substituted), and checks:
  1. the SQL's independent re-derivation agrees with the detector on EVERY replayed row (0 violations), with a
     positive count of stamped rows agreeing (the POSITIVE evidence the live check needs);
  2. it BITES: deliberately corrupted copies of the table - a stamp deleted, a stamp invented, a day count off by one,
     a carried stamp swapped for another pole - are each flagged under the matching VIOLATION_* verdict.
DuckDB is a stand-in for Postgres (both run this text: DISTINCT ON, FILTER, date - integer). Run from the repo root:
  PYTHONPATH=. python scripts/probes/_697_item4/dryrun_verify_sql.py
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import duckdb

import replay_equiv as R   # same directory

SQL = (Path(__file__).parent / "verify_live.sql").read_text()


def statement(n: int) -> str:
    """The n-th (1-based) statement of verify_live.sql, comments stripped, psql variables substituted."""
    body = "\n".join(re.sub(r"--.*$", "", ln) for ln in SQL.splitlines())   # whole-line and trailing comments
    stmts = [s.strip() for s in body.split(";") if s.strip()]
    return stmts[n - 1].replace(":'d0'", "'2026-05-05'").replace(":'since'", "'2025-07-01'")


def load(con, replays, bars):
    con.execute("""CREATE TABLE mi_flag_candidates (ticker TEXT, scan_date DATE, stage TEXT, pivot_high_date DATE,
                   pivot_high_price DOUBLE, post_breakout_from DATE, days_since_breakout INT)""")
    con.execute("""CREATE TABLE mi_daily_closes (ticker TEXT, trade_date DATE, open_price DOUBLE, high_price DOUBLE,
                   low_price DOUBLE, close DOUBLE, volume DOUBLE)""")
    con.executemany("INSERT INTO mi_flag_candidates VALUES (?,?,?,?,?,?,?)",
                    [(t, d, m["stage"], m["pivot_high_date"], m["pivot_high_price"], m["post_breakout_from"],
                      m["days_since_breakout"]) for t, res in replays.items() for d, m in res.items()])
    con.executemany("INSERT INTO mi_daily_closes VALUES (?,?,?,?,?,?,?)",
                    [(t, b["trade_date"], b["open_price"], b["high_price"], b["low_price"], b["close"], b["volume"])
                     for t, bs in bars.items() for b in bs])


def run(con, n=2):
    return {v: (rows, tick) for v, rows, _, _, tick in con.execute(statement(n)).fetchall()}


def main():
    corpus = R.load_corpus()
    cap_bars, _ = R.load_capture()
    total_ok = total_stamped = 0
    for name, bars in (("corpus", corpus), ("capture", cap_bars)):
        replays = {t: R.replay(t, b) for t, b in bars.items()}
        con = duckdb.connect()
        load(con, replays, bars)
        got = run(con)
        n_rows = sum(len(r) for r in replays.values())
        print(f"[{name}] {n_rows} replayed rows ({sum(1 for r in replays.values() for m in r.values() if m['pivot_high_date'])} reach the pivot) -> {got}")
        assert not [v for v in got if v.startswith("VIOLATION")], f"{name}: the SQL and the detector disagree: {got}"
        total_ok += got.get("ok_null", (0,))[0]
        total_stamped += got.get("ok_stamped", (0,))[0]

        # ── it must BITE (capture population only; every tamper is applied to a fresh copy) ──
        if name != "capture":
            continue
        base_rows = con.execute("SELECT ticker, scan_date, post_breakout_from, days_since_breakout FROM mi_flag_candidates "
                                "WHERE post_breakout_from IS NOT NULL ORDER BY ticker, scan_date").fetchall()
        assert base_rows
        t0, d0_, f0, n0 = base_rows[len(base_rows) // 2]
        nulls = con.execute("SELECT ticker, scan_date FROM mi_flag_candidates WHERE post_breakout_from IS NULL "
                            "AND pivot_high_date IS NOT NULL AND scan_date > '2026-06-15' ORDER BY ticker, scan_date").fetchall()
        tn, dn = nulls[len(nulls) // 2]
        other_from = next(f for _, _, f, _ in base_rows if f != f0)
        tampers = {
            "a stamp deleted": (f"UPDATE mi_flag_candidates SET post_breakout_from=NULL, days_since_breakout=NULL "
                                f"WHERE ticker='{t0}' AND scan_date='{d0_}'", "VIOLATION_missing_stamp"),
            "a stamp invented on a row with no breakout": (f"UPDATE mi_flag_candidates SET post_breakout_from='{f0}', "
                                                           f"days_since_breakout=3 WHERE ticker='{tn}' AND scan_date='{dn}'",
                                                           "VIOLATION_unsupported_stamp"),
            "a day count off by one": (f"UPDATE mi_flag_candidates SET days_since_breakout={n0 + 1} "
                                       f"WHERE ticker='{t0}' AND scan_date='{d0_}'", "VIOLATION_wrong_value"),
            "a stamp citing another pole": (f"UPDATE mi_flag_candidates SET post_breakout_from='{other_from}' "
                                            f"WHERE ticker='{t0}' AND scan_date='{d0_}'", "VIOLATION_wrong_value"),
        }
        for label, (upd, want) in tampers.items():
            con.execute("BEGIN")
            con.execute(upd)
            hit = run(con)
            con.execute("ROLLBACK")
            assert want in hit, f"{label}: expected {want}, got {hit}"
            print(f"  bites: {label:45} -> {want} {hit[want]}")
        # statement 3 (shape) is clean on the real rows and fires on a broken one
        assert con.execute(statement(3)).fetchone()[0] == 0
        con.execute("BEGIN")
        con.execute(f"UPDATE mi_flag_candidates SET days_since_breakout=26 WHERE ticker='{t0}' AND scan_date='{d0_}'")
        assert con.execute(statement(3)).fetchone()[0] == 1
        con.execute("ROLLBACK")
        print("  statement 3 (shape): 0 on real rows, 1 on days=26")
    print(f"AGREE on every replayed row: ok_null={total_ok}, ok_stamped={total_stamped}, VIOLATION=0")
    assert total_stamped > 100


if __name__ == "__main__":
    main()
