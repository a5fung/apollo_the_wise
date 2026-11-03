"""#706 one-off: run scripts/export_trades_snapshot.sql on a REAL (embedded) Postgres against SYNTHETIC tables.

No production data and no server: three minimal tables are built here, the export SELECT is executed as written,
and the rows it returns are printed. Run with a venv holding `pixeltable-pgserver` and `psycopg2-binary`
(python3.13: pip install pixeltable-pgserver psycopg2-binary):

    python run_export_sql.py <new.sql> [<old.sql>]       # with a second file, prints the column-by-column diff

Fixture (ET date = today's New York date; every number invented):
  LONGA   open long, hard_stop below the entry, 3 shares with 1 sold (double-encoded exits string);
          closes: yesterday 23.0, TODAY 24.0 and a row dated 5 days AHEAD at 99.0 (must be ignored)
  SHORTB  open short (hard_stop above the entry), newest close two days ago
  NOSIDE  open, no hard_stop and no orb_low            -> side NULL
  FLATC   open, hard_stop == entry                     -> side NULL
  NOPX    open long, no stored close at all            -> price / market value NULL
  CLOSEDD closed row                                   -> no price / market value, equity still present
  PAPERP  paper-account open row                       -> excluded
  equity: live 4,900 (3 days ago), live 5,000 (yesterday), paper 99,999 (today) -> the live yesterday row.
"""
import datetime as dt
import json
import pathlib
import sys
import tempfile

import psycopg2
import pixeltable_pgserver as pgserver

COLS = ("ticker", "status", "side", "current_price", "current_price_date", "market_value", "account_equity",
        "account_equity_date")


def run(sql_path: str) -> tuple[dt.date, list[dict]]:
    srv = pgserver.get_server(pathlib.Path(tempfile.mkdtemp()) / "pg")
    conn = psycopg2.connect(srv.get_uri())
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE mi_live_trades (
      id serial primary key, ticker text, signal_type text, alert_date date, filled_at timestamptz,
      closed_at timestamptz, status text, entry_price numeric, stop_price numeric, hard_stop float8, orb_low float8,
      entry_shares float8, total_pnl numeric, regime text, gap_pct numeric, catalyst_quality text, ep_score numeric,
      account_mode text, lowest_price_seen numeric, highest_price_seen numeric, exits jsonb DEFAULT '[]');
    CREATE TABLE mi_daily_closes (ticker text, trade_date date, close numeric);
    CREATE TABLE mi_account_equity_snapshots (id serial primary key, snapshot_date date, account_mode text,
      equity numeric, created_at timestamptz default now());
    """)
    cur.execute("SELECT (now() AT TIME ZONE 'America/New_York')::date")
    et = cur.fetchone()[0]

    def day(n: int) -> dt.date:
        return et + dt.timedelta(days=n)

    def trade(t, status, entry, stop, hard, orb, shares, exits="'[]'", mode="live", pnl=0):
        cur.execute(
            f"""INSERT INTO mi_live_trades (ticker, signal_type, alert_date, filled_at, status, entry_price,
                stop_price, hard_stop, orb_low, entry_shares, total_pnl, account_mode, exits)
                VALUES (%s,'magna53',%s,'2026-01-01T15:00:00Z',%s,%s,%s,%s,%s,%s,%s,%s,{exits})""",
            (t, day(-3), status, entry, stop, hard, orb, shares, pnl, mode))

    trade("LONGA", "filled", 20, 21, 18, 19, 3, exits="""to_jsonb('[{"price":22,"shares":1}]'::text)""")
    trade("SHORTB", "filled", 40, 44, 44, None, 100)
    trade("NOSIDE", "filled", 10, 9, None, None, 5)
    trade("FLATC", "filled", 10, 10, 10, None, 5)
    trade("NOPX", "filled", 15, 14, 13, None, 7)
    trade("CLOSEDD", "closed", 20, 18, 18, 19, 4, pnl=8)
    trade("PAPERP", "filled", 30, 28, 28, None, 2, mode="paper")
    for tk, off, close in [("LONGA", -1, 23.0), ("LONGA", 0, 24.0), ("LONGA", 5, 99.0), ("SHORTB", -4, 41.0),
                           ("SHORTB", -2, 38.0), ("NOSIDE", 0, 9.5), ("FLATC", 0, 10.5), ("CLOSEDD", 0, 25.0)]:
        cur.execute("INSERT INTO mi_daily_closes VALUES (%s,%s,%s)", (tk, day(off), close))
    cur.execute(
        "INSERT INTO mi_account_equity_snapshots (snapshot_date, account_mode, equity, created_at) VALUES "
        "(%s,'live',4900,now()-interval '2 days'), (%s,'live',5000,now()-interval '1 day'), (%s,'paper',99999,now())",
        (day(-3), day(-1), day(0)))

    cur.execute(pathlib.Path(sql_path).read_text().strip().rstrip(";"))
    return et, cur.fetchone()[0]


if __name__ == "__main__":
    et, rows = run(sys.argv[1])
    print(f"ET date {et} | {len(rows)} rows (the paper row is excluded)")
    for r in rows:
        print({k: r.get(k) for k in COLS})
    if len(sys.argv) > 2:
        _, old = run(sys.argv[2])
        print("\nnew-only keys:", sorted(set(rows[0]) - set(old[0])), "| dropped keys:", sorted(set(old[0]) - set(rows[0])))
        for o, n in zip(old, rows):
            diff = {k: (o[k], n[k]) for k in o if o[k] != n[k]}
            print(o["ticker"], diff or "identical on every pre-existing column")
