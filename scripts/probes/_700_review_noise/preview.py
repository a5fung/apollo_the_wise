"""#700 - render a stored week's weekly review under the CURRENT renderer. No send, no write.

It drives the REAL `run_weekly_review` over a stored `mi_system_reviews` row: the stored `metrics` stand
in for the aggregators and the stored `summary` for the LLM (neither is re-run - $0). Everything that
could leave the process is captured instead of performed, and a captured action is COUNTED, so
"nothing was sent, nothing was written" is a number in `stats.json`, not a claim:

  * Telegram: `scripts/probes/_muzzle.muzzle_telegram()` runs FIRST (any request to api.telegram.org is
    refused at the HTTP layer, whoever builds it), and `sr.send_telegram_message` is replaced by a
    capture. `sends_refused` counts what reached the wire anyway (expected 0); `sent` counts what the
    review tried to send through its own sender (expected 1 - the one message).
  * `mi_system_reviews`: `sr.insert_system_review` is replaced by a capture (raises with --strict).
    The replay-regression snapshot (`log_audit_event`) is captured too. In DB mode the pool is also
    wrapped so any statement that is not a plain SELECT/WITH read raises. The wrapper reaches modules
    that bound `get_pool` by name at import (cost_board, missed_outcomes) too - found from
    `sys.modules`, not hand-listed - but it cannot reach a connection obtained some other way, so it is
    a backstop: the review's own queries are SELECT-only and every write it makes is captured above.

Three modes:
  --date YYYY-MM-DD   DB mode. Run INSIDE the market-agent container (the DB is reachable there):
        docker exec -i apollo-market python scripts/probes/_700_review_noise/preview.py \\
            --date 2026-10-11 --out /tmp/700
      The stored row for that date is read; "last week" is the real accessor with
      `on_or_before=window_start` (or `--prior YYYY-MM-DD` to pin it). The render-time sections
      (bands, setup rows, replay, 2nd-opinion, themes, spend) run LIVE read-only as of now, which
      `stats.json` states as `live_sections_as_of` - a past week's bands are not reproduced.
  --offline PATH      no DB: rows come from a local capture (q1_reviews.out) and the render-time
      sections print their fail-open `unavailable:` lines. A laptop smoke test of the plumbing.
  --fixture           no DB: the stored 10-11 row with its render-time inputs rebuilt from the one-time
      capture (tests/fixtures/weekly_review_1011.json) through the real `_assemble_report`. Nothing
      is "sent" in this mode (no send path is exercised), so `sent` is null.

Writes head.md, fold.md, full.md, message.html, stats.json to --out and prints the stats line.
`--full` also prints full.md - the uncompacted text that is stored as `report.full_md`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

_WRITE_WORDS = re.compile(r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|TRUNCATE|CREATE|GRANT|REVOKE|COPY)\b", re.IGNORECASE)


class ReadOnlyViolation(RuntimeError):
    """A statement that is not a plain read reached the guarded pool."""


def _guard(sql: str) -> None:
    s = " ".join(str(sql).split())
    if not s.upper().startswith(("SELECT", "WITH")) or _WRITE_WORDS.search(s):
        raise ReadOnlyViolation(f"preview probe is read-only; refused: {s[:120]}")


class _ReadOnlyConn:
    def __init__(self, conn):
        self._conn = conn

    async def _checked(self, name, sql, *args, **kwargs):
        _guard(sql)
        return await getattr(self._conn, name)(sql, *args, **kwargs)

    async def execute(self, sql, *a, **k):
        return await self._checked("execute", sql, *a, **k)

    async def executemany(self, sql, *a, **k):
        return await self._checked("executemany", sql, *a, **k)

    async def fetch(self, sql, *a, **k):
        return await self._checked("fetch", sql, *a, **k)

    async def fetchrow(self, sql, *a, **k):
        return await self._checked("fetchrow", sql, *a, **k)

    async def fetchval(self, sql, *a, **k):
        return await self._checked("fetchval", sql, *a, **k)

    def __getattr__(self, name):
        return getattr(self._conn, name)


class _Acquire:
    def __init__(self, cm):
        self._cm = cm

    async def __aenter__(self):
        return _ReadOnlyConn(await self._cm.__aenter__())

    async def __aexit__(self, *exc):
        return await self._cm.__aexit__(*exc)


class ReadOnlyPool:
    """Wraps an asyncpg pool: every connection it hands out refuses a non-read statement."""

    def __init__(self, pool):
        self._pool = pool

    def acquire(self, *a, **k):
        return _Acquire(self._pool.acquire(*a, **k))

    def __getattr__(self, name):
        return getattr(self._pool, name)


# -- stored rows -------------------------------------------------------------------------------

def rows_from_capture(path: Path) -> list[dict]:
    """The stored rows of a one-time capture file (one JSON object per line, e.g. q1_reviews.out)."""
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines()
            if l.strip().startswith("{")]


def _patch_name_bound_pools(stack: ExitStack, original, replacement) -> list[str]:
    """Patch `get_pool` in every ALREADY-LOADED module that did `from agents.market_intelligence.db import
    get_pool` (cost_board and missed_outcomes do, at module level) - patching `db.get_pool` alone leaves
    those modules holding the real, unguarded function. Derived from `sys.modules`, never a hand list: a
    module is patched when its `get_pool` IS `original`. A module first imported AFTER this runs, inside
    the same ExitStack, binds the already-patched `db.get_pool`. Returns the module names it patched."""
    patched = []
    for name, mod in list(sys.modules.items()):
        if mod is None or not name.startswith(("agents.", "shared.", "core.", "broker.", "channels.")):
            continue
        if getattr(mod, "get_pool", None) is original:
            stack.enter_context(patch.object(mod, "get_pool", replacement))
            patched.append(name)
    return patched


def newest_at_or_before(rows: list[dict], d: date) -> dict | None:
    ok = [r for r in rows if date.fromisoformat(str(r["review_date"])) <= d]
    return max(ok, key=lambda r: r["review_date"]) if ok else None


async def read_stored_row(d: date, window_days: int = 7) -> dict | None:
    """DB mode: one stored review row through the read-only pool (a SELECT)."""
    import agents.market_intelligence.db as dbmod
    pool = ReadOnlyPool(await dbmod.get_pool())
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT review_date, window_days, regime, summary, metrics, suggestions "
            "FROM mi_system_reviews WHERE review_date = $1 AND window_days = $2", d, window_days)
    if not row:
        return None
    out = dict(row)
    out["review_date"] = out["review_date"].isoformat()
    for k in ("metrics", "suggestions"):
        if isinstance(out.get(k), str):
            out[k] = json.loads(out[k])
    return out


# -- the preview ---------------------------------------------------------------------------------

async def run_preview(stored: dict, *, today: date, prior_fn=None, strict: bool = False,
                      read_only_pool: bool = False, no_database: bool = False) -> dict:
    """Run the REAL `run_weekly_review` over `stored` with every outbound edge captured.

    `prior_fn(window_days, on_or_before)` stands in for `get_latest_system_review`; None leaves the REAL
    accessor in place (DB mode). `read_only_pool` wraps `db.get_pool` so a non-read statement raises;
    `no_database` makes `db.get_pool` raise (offline mode: render-time sections fail open).
    Returns the captures and the rendered pieces."""
    import agents.market_intelligence.collector as collector
    import agents.market_intelligence.db as dbmod
    import agents.market_intelligence.system_review as sr
    from scripts.probes._700_review_noise.harness_1011 import restore_dates

    sent: list = []
    inserted: list = []
    audit: list = []
    metrics = restore_dates(stored["metrics"])

    async def capture_send(text, **kwargs):
        sent.append((text, kwargs))
        return True

    async def capture_insert(review):
        if strict:
            raise AssertionError("--strict: the preview tried to write mi_system_reviews")
        inserted.append(review)
        return True

    async def capture_audit(*args, **kwargs):
        audit.append(args)

    with ExitStack() as stack:
        for target, name, value in (
            (sr, "send_telegram_message", capture_send),
            (sr, "insert_system_review", capture_insert),
            (dbmod, "log_audit_event", capture_audit),
            (sr, "_gather_and_aggregate", AsyncMock(return_value=metrics)),
            (sr, "_synthesize", AsyncMock(return_value=stored["summary"])),
            (sr, "_utcnow", lambda: datetime(today.year, today.month, today.day, 12, 0, tzinfo=timezone.utc)),
            (collector, "et_today", lambda: today),
        ):
            stack.enter_context(patch.object(target, name, value))
        if prior_fn is not None:
            stack.enter_context(patch.object(sr, "get_latest_system_review", prior_fn))
        real_get_pool = dbmod.get_pool
        if no_database:
            async def no_pool():
                raise RuntimeError("offline: no database")
            stack.enter_context(patch.object(dbmod, "get_pool", no_pool))
            _patch_name_bound_pools(stack, real_get_pool, no_pool)
        elif read_only_pool:
            async def ro_pool():
                return ReadOnlyPool(await real_get_pool())
            stack.enter_context(patch.object(dbmod, "get_pool", ro_pool))
            _patch_name_bound_pools(stack, real_get_pool, ro_pool)
        review = await sr.run_weekly_review(7)
    report = review["metrics"]["report"]
    return {"review": review, "report": report, "sent": sent, "inserted": inserted, "audit": audit}


def _stats(mode: str, out: dict | None, meta: dict, *, today: date, refused: int,
           html: str, prior_row: dict | None) -> dict:
    from shared.telegram_format import chunk_html
    return {
        "mode": mode, "review_date": today.isoformat(),
        "prior_review_date": (prior_row or {}).get("review_date"),
        "live_sections_as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "head_lines": meta["head_lines"], "fold_chars": meta["fold_chars"],
        "full_chars": len(meta["full_md"]), "html_chars": len(html), "chunks": len(chunk_html(html)),
        "needs_you": meta["needs_you"], "needs_me": meta["needs_me"],
        "changes": meta["changes"],
        "sent": None if out is None else len(out["sent"]),
        "inserts_captured": None if out is None else len(out["inserted"]),
        "audit_writes_captured": None if out is None else len(out["audit"]),
        "sends_refused": refused,
    }


def _write(out_dir: Path, meta: dict, html: str, stats: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "head.md").write_text(meta["head_md"] + "\n", encoding="utf-8")
    (out_dir / "fold.md").write_text(meta["fold_md"] + "\n", encoding="utf-8")
    (out_dir / "full.md").write_text(meta["full_md"] + "\n", encoding="utf-8")
    (out_dir / "message.html").write_text(html + "\n", encoding="utf-8")
    (out_dir / "stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False, default=str) + "\n",
                                        encoding="utf-8")


def main(argv=None) -> dict:
    from scripts.probes._muzzle import muzzle_telegram
    captured = muzzle_telegram([])                       # FIRST: nothing below may reach the Bot API
    refused_before = len(captured)

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", help="review date, YYYY-MM-DD (DB mode and --offline)")
    ap.add_argument("--prior", help="pin 'last week' to the stored row with this date (DB mode)")
    ap.add_argument("--offline", metavar="CAPTURE", help="no database: rows from a local capture file")
    ap.add_argument("--fixture", action="store_true", help="no database: the 10-11 fixture, all sections")
    ap.add_argument("--no-prior", action="store_true", help="--fixture: render with no earlier review")
    ap.add_argument("--out", default=str(Path("/tmp") / "700"))
    ap.add_argument("--full", action="store_true", help="also print full.md")
    ap.add_argument("--strict", action="store_true", help="raise if the review tries to write its row")
    args = ap.parse_args(argv)
    out_dir = Path(args.out)

    if args.fixture:
        from scripts.probes._700_review_noise import harness_1011 as h
        head, fold, meta = h.render_1011(h.NO_PRIOR if args.no_prior else h.FIXTURE_PRIOR)
        import agents.market_intelligence.system_review as sr
        html = sr.render_review_html(head, fold)
        stats = _stats("fixture", None, meta, today=h.TODAY, refused=len(captured) - refused_before,
                       html=html, prior_row=None if args.no_prior else h.load_fixture()["prior"])
        print("FIXTURE: the stored 2026-10-11 row, render-time inputs rebuilt from the one-time capture; "
              "nothing is sent or written in this mode.")
    elif args.offline:
        if not args.date:
            ap.error("--offline needs --date")
        today = date.fromisoformat(args.date)
        rows = rows_from_capture(Path(args.offline))
        stored = next((r for r in rows if r["review_date"] == args.date), None)
        if stored is None:
            ap.error(f"no row dated {args.date} in {args.offline}")

        async def prior_fn(window_days=7, on_or_before=None):
            return newest_at_or_before([r for r in rows if r["review_date"] != args.date],
                                       on_or_before or today)
        out = asyncio.run(run_preview(stored, today=today, prior_fn=prior_fn, strict=args.strict,
                                      no_database=True))
        meta = out["report"]
        html = out["sent"][0][0] if out["sent"] else ""
        stats = _stats("offline", out, meta, today=today, refused=len(captured) - refused_before,
                       html=html, prior_row=newest_at_or_before(
                           [r for r in rows if r["review_date"] != args.date], today - timedelta(days=7)))
        print("OFFLINE: no database - the render-time sections (bands, setup rows, replay, 2nd-opinion, "
              "themes, spend) print their fail-open `unavailable:` lines. A smoke test of the plumbing, "
              "not a render of the week.")
    else:
        if not args.date:
            ap.error("give --date (DB mode), --offline CAPTURE --date, or --fixture")
        today = date.fromisoformat(args.date)

        async def go():
            stored = await read_stored_row(today)
            if stored is None:
                raise SystemExit(f"no stored review dated {args.date}")
            prior_fn = None
            prior_row = None
            if args.prior:
                prior_row = await read_stored_row(date.fromisoformat(args.prior))

                async def prior_fn(window_days=7, on_or_before=None):   # noqa: F811
                    return prior_row
            return await run_preview(stored, today=today, prior_fn=prior_fn, strict=args.strict,
                                     read_only_pool=True), prior_row
        out, prior_row = asyncio.run(go())
        meta = out["report"]
        html = out["sent"][0][0] if out["sent"] else ""
        stats = _stats("db", out, meta, today=today, refused=len(captured) - refused_before,
                       html=html, prior_row=prior_row)

    _write(out_dir, meta, html, stats)
    print(json.dumps({k: v for k, v in stats.items() if k != "changes"}, ensure_ascii=False))
    if args.full:
        print((out_dir / "full.md").read_text(encoding="utf-8"))
    return stats


if __name__ == "__main__":
    main()
