"""#672 — which daily jobs can be re-run with the date PINNED, and which of them SEND. Derived by AST.

WHY. The recovery sweep (agents/market_intelligence/job_recovery.py) re-runs a missed daily job with
`shared.dates.et_today()` pinned to the day it was due. That reaches every job that derives its
market date from `et_today()` / `last_trading_day()`. It does NOT reach a job that derives a
calendar date from the wall clock itself — `datetime.now(_ET).date()`, `now_et.weekday()`,
`date.today()` — such a job, re-run on Saturday for Friday, records SATURDAY (or, for a weekend
guard, silently no-ops and records a "success" that did nothing). The 09-19 probe hand-checked 14
jobs for this. The sweep's population is 60+ and derived, so the check must be too.

WHAT IT DOES. Parses `scheduler.py`'s `add_job(...)` calls → (job id, function name, cron fields);
keeps the ones the sweep would consider (single fixed hour+minute, not execution-owned); then walks
each job function's TRANSITIVE call graph across `agents/market_intelligence/**` (calls by bare
name, `module.func`, and `from x import y` — function-local imports included) and reports:

  DATE-FROM-CLOCK  a `.date()` / `.weekday()` / `.isoweekday()` / `.strftime(` / `.toordinal()`
                   applied to `datetime.now(...)`, `datetime.utcnow()`, `date.today()`, or a local
                   name assigned from one of those in the same function. Timestamps (`created_at =
                   datetime.now(_ET)`) are NOT flagged — only a calendar-date derivation is.
  SENDS            the closure reaches a Telegram sender (any function whose body posts to
                   api.telegram.org, plus the two shared wrappers) — the P3 classification.

ESCAPE: `# recovery-clock-ok: <reason ≥ 12 chars>` on the flagged line, for a wall-clock date that
is genuinely about NOW (a "how late is it" guard, a log line) rather than the data's date.

Heuristic by construction (dynamic dispatch, methods on objects and getattr are invisible). False
negatives are the risk; the runtime refusal guard in job_recovery.py is the other half.

Run: python3 scripts/check_job_date_sources.py [--json]
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MI = REPO / "agents" / "market_intelligence"
SCHEDULER = MI / "scheduler.py"
ESCAPE_RE = re.compile(r"#\s*recovery-clock-ok:\s*(.{12,})")
CLOCK_CALLS = {("datetime", "now"), ("datetime", "utcnow"), ("date", "today"), ("_dt", "now")}
DATE_DERIVATIONS = {"date", "weekday", "isoweekday", "strftime", "toordinal", "isocalendar"}
SENDER_NAMES = {"send_telegram_message", "notify_owner", "send_telegram_photo", "notify_job_failure",
                "_send_with_keyboard", "send_photo", "send_message"}
TELEGRAM_HOST = "api.telegram.org"


# ── module index ──────────────────────────────────────────────────────────────────────────

class Module:
    def __init__(self, path: Path):
        self.path = path
        self.name = ".".join(path.relative_to(REPO).with_suffix("").parts)
        self.src = path.read_text(encoding="utf-8", errors="replace")
        self.tree = ast.parse(self.src)
        self.lines = self.src.splitlines()
        self.funcs: dict[str, ast.AST] = {}
        self.imports: dict[str, str] = {}          # local alias → "module" or "module.func"
        for n in self.tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.funcs[n.name] = n
            elif isinstance(n, ast.ClassDef):
                for m in n.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.funcs[f"{n.name}.{m.name}"] = m
        self._collect_imports(self.tree, self.imports)
        self.sends_directly = TELEGRAM_HOST in self.src

    @staticmethod
    def _collect_imports(node, into: dict) -> None:
        for n in ast.walk(node):
            if isinstance(n, ast.Import):
                for a in n.names:
                    into[a.asname or a.name.split(".")[0]] = a.name
            elif isinstance(n, ast.ImportFrom) and n.module:
                for a in n.names:
                    into[a.asname or a.name] = f"{n.module}.{a.name}"


def load_modules() -> dict[str, Module]:
    mods = {}
    for p in MI.rglob("*.py"):
        if "backtester" in p.parts or p.name.startswith("_"):
            continue
        try:
            m = Module(p)
        except SyntaxError:
            continue
        mods[m.name] = m
    for extra in (REPO / "core" / "notifications.py", REPO / "core" / "job_audit.py", REPO / "shared" / "dates.py"):
        m = Module(extra)
        mods[m.name] = m
    return mods


# ── scheduler registrations ───────────────────────────────────────────────────────────────

def registrations(sched: Module) -> list[dict]:
    """Every `_scheduler.add_job(audit_wrap(fn, "id"...) | fn, CronTrigger(...), id="...")`."""
    out = []
    for n in ast.walk(sched.tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "add_job"):
            continue
        fn_name, jid, cron, paused = None, None, {}, False
        first = n.args[0] if n.args else None
        if isinstance(first, ast.Call) and getattr(first.func, "id", "") == "audit_wrap" and first.args:
            fn_name = getattr(first.args[0], "id", None)
        elif isinstance(first, ast.Name):
            fn_name = first.id
        for kw in n.keywords:
            if kw.arg == "id" and isinstance(kw.value, ast.Constant):
                jid = kw.value.value
            if kw.arg == "next_run_time" and isinstance(kw.value, ast.Constant) and kw.value.value is None:
                paused = True
        trig = n.args[1] if len(n.args) > 1 else next((k.value for k in n.keywords if k.arg == "trigger"), None)
        if isinstance(trig, ast.Call) and getattr(trig.func, "id", "") == "CronTrigger":
            for kw in trig.keywords:
                if isinstance(kw.value, ast.Constant):
                    cron[kw.arg] = kw.value.value
        if jid is None and isinstance(first, ast.Call) and len(first.args) > 1 and isinstance(first.args[1], ast.Constant):
            jid = first.args[1].value
        out.append({"job_id": jid, "func": fn_name, "cron": cron, "paused": paused, "line": n.lineno})
    return out


def is_daily(cron: dict) -> bool:
    h, m = cron.get("hour"), cron.get("minute")
    return isinstance(h, int) and isinstance(m, int) and "second" not in cron


def is_in_session(cron: dict) -> bool:
    """The runtime rule mirrored: a slot inside 09:30–16:00 ET is never re-run (job_recovery.
    slot_is_in_session), so its wall-clock reads cannot mislabel a re-run."""
    h, m = cron.get("hour"), cron.get("minute")
    return isinstance(h, int) and isinstance(m, int) and (9, 30) <= (h, m) < (16, 0)


# ── call graph ────────────────────────────────────────────────────────────────────────────

def _resolve(mods: dict[str, Module], mod: Module, node: ast.AST, local_imports: dict) -> tuple[Module, str] | None:
    """A call target → (module, function name) when it is a repo function we can see."""
    imports = {**mod.imports, **local_imports}
    if isinstance(node, ast.Name):
        if node.id in mod.funcs:
            return mod, node.id
        tgt = imports.get(node.id)
        if tgt and "." in tgt:
            mname, fname = tgt.rsplit(".", 1)
            m = mods.get(mname)
            if m and fname in m.funcs:
                return m, fname
    elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        tgt = imports.get(node.value.id)
        if tgt:
            m = mods.get(tgt) or mods.get(tgt.rsplit(".", 1)[0])
            if m and node.attr in m.funcs:
                return m, node.attr
    return None


def _local_imports(fn: ast.AST) -> dict:
    out: dict = {}
    Module._collect_imports(fn, out)
    return out


def closure(mods: dict[str, Module], start: tuple[Module, str]) -> list[tuple[Module, str]]:
    seen, stack, order = set(), [start], []
    while stack:
        mod, fname = stack.pop()
        if (mod.name, fname) in seen:
            continue
        seen.add((mod.name, fname))
        fn = mod.funcs.get(fname)
        if fn is None:
            continue
        order.append((mod, fname))
        li = _local_imports(fn)
        for n in ast.walk(fn):
            if isinstance(n, ast.Call):
                r = _resolve(mods, mod, n.func, li)
                if r:
                    stack.append(r)
    return order


# ── the two detectors ─────────────────────────────────────────────────────────────────────

def _is_clock_call(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
        return (node.func.value.id, node.func.attr) in CLOCK_CALLS
    return False


def date_from_clock(mod: Module, fname: str) -> list[dict]:
    """Lines in `fname` where a calendar date is derived from the wall clock."""
    if mod.name == "shared.dates" and fname in ("et_today", "operator_today"):
        return []          # et_today IS the pin's live-clock fallback; operator_today is the operator's clock
    fn = mod.funcs[fname]
    clock_names: set[str] = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and _is_clock_call(n.value):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    clock_names.add(t.id)
    hits = []
    for n in ast.walk(fn):
        recv = None
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in DATE_DERIVATIONS:
            recv = n.func.value
        elif isinstance(n, ast.Attribute) and n.attr in ("weekday",) and not isinstance(getattr(n, "ctx", None), ast.Store):
            recv = n.value
        if recv is None:
            continue
        if _is_clock_call(recv) or (isinstance(recv, ast.Name) and recv.id in clock_names) \
                or (isinstance(recv, ast.Call) and isinstance(recv.func, ast.Attribute)
                    and isinstance(recv.func.value, ast.Name) and recv.func.value.id == "date" and recv.func.attr == "today"):
            line = mod.lines[n.lineno - 1] if n.lineno - 1 < len(mod.lines) else ""
            esc = ESCAPE_RE.search(line)
            hits.append({"module": mod.name, "func": fname, "line": n.lineno, "text": line.strip()[:110],
                         "escaped": bool(esc), "reason": esc.group(1).strip() if esc else None})
    return hits


def sends(mod: Module, fname: str) -> bool:
    fn = mod.funcs[fname]
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
            if name in SENDER_NAMES:
                return True
    return False


# ── report ────────────────────────────────────────────────────────────────────────────────

def analyse() -> dict:
    mods = load_modules()
    sched = mods["agents.market_intelligence.scheduler"]
    exec_owned = set()
    for n in ast.walk(sched.tree):
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "EXECUTION_OWNED_JOB_IDS" for t in n.targets):
            for c in ast.walk(n.value):
                if isinstance(c, ast.Constant) and isinstance(c.value, str):
                    exec_owned.add(c.value)
    report = {"jobs": [], "unescaped": 0}
    for reg in registrations(sched):
        jid, fn = reg["job_id"], reg["func"]
        if not jid or not fn or jid in exec_owned or reg["paused"] or not is_daily(reg["cron"]) \
                or is_in_session(reg["cron"]):
            continue
        if fn not in sched.funcs:
            report["jobs"].append({"job_id": jid, "func": fn, "status": "function not found in scheduler.py"})
            continue
        chain = closure(mods, (sched, fn))
        hits, sender_paths = [], []
        for mod, f in chain:
            hits.extend(date_from_clock(mod, f))
            if sends(mod, f) or (mod.sends_directly and f in SENDER_NAMES):
                sender_paths.append(f"{mod.name.rsplit('.', 1)[-1]}.{f}")
        report["jobs"].append({"job_id": jid, "func": fn, "reach": len(chain),
                               "date_from_clock": hits, "sends": sorted(set(sender_paths))})
        report["unescaped"] += sum(1 for h in hits if not h["escaped"])
    return report


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    rep = analyse()
    if "--json" in argv:
        print(json.dumps(rep, indent=1))
        return 0
    print(f"{len(rep['jobs'])} daily intelligence jobs examined (paused + execution-owned excluded)\n")
    print("DATE-FROM-CLOCK (a pinned re-run would record the wrong day here):")
    n = 0
    for j in rep["jobs"]:
        for h in j.get("date_from_clock", []):
            n += 1
            tag = "ok  " if h["escaped"] else "FLAG"
            print(f"  {tag} {j['job_id']:32s} {h['module'].rsplit('.', 1)[-1]}.{h['func']}:{h['line']}  {h['text']}")
    if not n:
        print("  none")
    print("\nSENDS (a re-run's Telegram is HELD by default — these are the jobs that would produce one):")
    for j in rep["jobs"]:
        if j.get("sends"):
            print(f"  {j['job_id']:32s} via {', '.join(j['sends'])}")
    silent = [j["job_id"] for j in rep["jobs"] if not j.get("sends") and "status" not in j]
    print(f"\nSILENT (no sender reachable): {len(silent)} — {', '.join(sorted(silent))}")
    print(f"\nunescaped date-from-clock derivations: {rep['unescaped']}")
    return 1 if rep["unescaped"] else 0


if __name__ == "__main__":
    sys.exit(main())
