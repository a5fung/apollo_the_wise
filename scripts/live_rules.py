"""live_rules.py — what rules are acting RIGHT NOW, from ground truth, never from prose.

WHY THIS EXISTS (operator-directed, 2026-08-23 — three failures in one day, same shape):
  1. `docs/setups/magna53_ep.md` said "Built, NOT yet deployed" for a WEEK after the 2R stop
     was live in production.
  2. `docs/setups/safeguards.md` said regime sizing was "flag OFF by default" for FOUR WEEKS
     after `REGIME_SIZING_ENABLED=true` was set in both containers.
  3. The +2R partial was reported as "fires only on days 3-5" because ONE of the two partial
     code paths was read (`live_tracker.run_partial_exits`) and the other — the one that acts —
     was not (`order_manager.scan_profit_triggers`, live since 2026-08-01).
  Every one is the same defect: the acting rule is knowable from code and prod state, and prose
  was asserted instead. Prose rots; this generated view cannot.

SOURCES, in priority order (an env var OVERRIDES a code default; a DB toggle row OVERRIDES both):
  (a) code constants, AST-parsed from the rule modules (never hand-copied values);
  (b) runtime toggles in `mi_safeguard_state` (read-only SELECT over SSH);
  (c) env in the RUNNING containers, read var-by-var (NEVER a full `env` dump — secrets);
  (d) `scripts/gate_provenance_registry.py` — the existing enumerated gate registry, reused.

DESIGN RULES:
  - Generated, never hand-maintained. Every printed VALUE is derived (AST / prod / registry /
    doc parse). The prose meaning strings here are presentation only; if the constant or code
    fingerprint they describe disappears, the row reports ABSENT loudly instead of lying.
  - Prod reads are READ-ONLY (printenv + SELECT + git log + cat). If the server is unreachable
    the tool still works from code alone and LABELS prod-derived rows unknown — never guesses.
  - $0. No paid calls.
  - Plain words: every number carries its meaning.

CLI:
  python scripts/live_rules.py                # full view (ENTRY / EXIT / SIZING / DRIFT / REPLACED)
  python scripts/live_rules.py --drift-only   # terse session-open check: DRIFT section only
  python scripts/live_rules.py --no-prod      # skip the SSH read (offline mode)
  python scripts/live_rules.py --selftest     # replay the two doc-borne 2026-08-23 failures
                                              # from real git history (the third failure —
                                              # partial-path misread — is pinned by
                                              # tests/test_live_rules.py, synthetic fixtures)

HONEST LIMITS (do not oversell):
  - The stale-claim scan (drift rule 1) is lexical: a deployment claim written in words the
    phrase list doesn't contain will not be caught. Claims that name NO checkable flag are
    surfaced as UNVERIFIED rather than resolved — they are exactly the lines that rot.
  - Drift rule 2 only covers toggles MENTIONED in docs/setups/*.md; toggles whose SSoT lives
    elsewhere (theme/judge ADRs) are out of scope here.
  - A doc that is semantically wrong while lexically consistent is not caught (same limit as
    scripts/check_gate_provenance.py, stated there).
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SSH_HOST = os.environ.get("APOLLO_SSH_HOST", "apollo@87.99.134.162")
SSH_CONNECT_TIMEOUT_S = 6
SSH_TOTAL_TIMEOUT_S = 45
PROD_CONTAINERS = ("apollo-market", "apollo-execution")
PROD_REPO_DIR = "/home/apollo/apollo_the_wise"

# Never read (or even request) env vars whose NAME suggests a secret.
_SECRET_TOKENS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASSWD", "DSN", "CREDENTIAL")

# The modules whose module-level constants ARE the rule surface.
# order_manager.py holds the stop formula, the 20% cap and scan_profit_triggers (the +2R
# partial) — the module whose rules were misread on 2026-08-23; flag_detector.py holds the
# continuation-flag rule constants. Listed LAST deliberately: on a name collision the first
# module wins (constants.py stays authoritative for shared names).
RULE_MODULES = (
    "agents/market_intelligence/constants.py",
    "agents/market_intelligence/ep_detector.py",
    "agents/market_intelligence/ep_rubric.py",
    "agents/market_intelligence/ninem_detector.py",
    "agents/market_intelligence/broker/entry_pipeline.py",
    "agents/market_intelligence/broker/order_manager.py",
    "agents/market_intelligence/flag_detector.py",
)

SETUP_DOCS_GLOB = "docs/setups/*.md"
# docs/architecture/* are owners too (docs/SSoT.md registers them as such) and were never
# scanned — which is why lane2_grouping_v2 could run ON in paper with the theme-engine SSoT
# silent about it. Same treatment as setup docs: both drift rules apply.
ARCH_DOCS_GLOB = "docs/architecture/*.md"

# 2026-08-29 — ALSO scan analysis + design documents. Operator: "how many times we need to fix
# this, 100x more times???" The drift checker had only ever read docs/setups/, so a FINDING built
# on a rule we had deleted passed unnoticed: the #327 Stage-1 analysis attributed 22 of 55 missed
# EPs to a top-20-BY-GAP shortlist cap that was replaced on 2026-08-22. The doc was wrong the
# moment it was written and nothing caught it. Findings are what decisions get made from, so they
# need the same check the setup docs get — the constant-mismatch rule (_DOC_VALUE_RE) applies
# unchanged, and a stale number in a conclusion is worse than a stale number in a reference.
FINDING_DOCS_GLOBS = ("docs/analysis/*.md", "docs/design/*.md")

# The pre-correction revision of the two docs that carried the 2026-08-23 stale claims —
# used ONLY by --selftest to replay the historical text through the live drift rules.
# (763b1ee4 = "Two safety docs described rules that had not been true for weeks"; its parent
# still carries both stale claims.)
_SELFTEST_FIX_COMMIT = "763b1ee4"


# ───────────────────────────── code constants (source a) ─────────────────────────────

@dataclass
class ConstFact:
    """One module-level constant: either a plain literal or an env-var-driven value."""
    name: str
    module: str
    kind: str                 # "literal" | "env"
    value: object = None      # literal value, or the CODE DEFAULT for env kind
    env_var: str | None = None
    cast: str | None = None   # "bool" | "float" | "int" | "str" (env kind only)
    lineno: int = 0


def _env_call_parts(node: ast.AST) -> tuple[str, ast.AST | None] | None:
    """If `node` is os.environ.get("VAR", default) / os.getenv("VAR", default), return
    (var_name, default_node)."""
    if not isinstance(node, ast.Call):
        return None
    f = node.func
    is_env_get = (
        isinstance(f, ast.Attribute) and f.attr == "get"
        and isinstance(f.value, ast.Attribute) and f.value.attr == "environ"
    )
    is_getenv = isinstance(f, ast.Attribute) and f.attr == "getenv"
    if not (is_env_get or is_getenv):
        return None
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return None
    default = node.args[1] if len(node.args) > 1 else None
    return str(node.args[0].value), default


def _classify_value(node: ast.AST) -> dict | None:
    """Classify a module-level assignment's value expression into a ConstFact payload."""
    # Plain literal (numbers, strings, dicts, tuples, None, frozenset of literals…)
    try:
        return {"kind": "literal", "value": ast.literal_eval(node)}
    except (ValueError, SyntaxError):
        pass

    # bool env:  os.environ.get("V", "false").lower() == "true"
    if isinstance(node, ast.Compare) and len(node.comparators) == 1:
        left = node.left
        if isinstance(left, ast.Call) and isinstance(left.func, ast.Attribute) and left.func.attr == "lower":
            parts = _env_call_parts(left.func.value)
            if parts and isinstance(node.comparators[0], ast.Constant):
                var, default = parts
                default_s = default.value if isinstance(default, ast.Constant) else "false"
                return {"kind": "env", "env_var": var, "cast": "bool",
                        "value": str(default_s).lower() == "true"}

    # cast env:  float(os.environ.get("V", d)) / int(...)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("float", "int"):
        parts = _env_call_parts(node.args[0]) if node.args else None
        if parts:
            var, default = parts
            payload = {"kind": "env", "env_var": var, "cast": node.func.id, "value": None}
            if isinstance(default, ast.Name):
                # default refers to another module constant (e.g. _MIN_GAP_PCT_DEFAULT) —
                # resolved after the whole module is parsed (see parse_module_constants).
                payload["default_ref"] = default.id
            else:
                try:
                    dval = ast.literal_eval(default) if default is not None else None
                    payload["value"] = {"float": float, "int": int}[node.func.id](dval) if dval is not None else None
                except (ValueError, TypeError, SyntaxError):
                    pass
            return payload

    # plain string env:  os.environ.get("V", "combined").lower()  /  os.environ.get("V", "x")
    inner = node
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("lower", "rstrip", "strip"):
        inner = node.func.value
    parts = _env_call_parts(inner)
    if parts:
        var, default = parts
        try:
            dval = ast.literal_eval(default) if default is not None else None
        except (ValueError, SyntaxError):
            dval = None
        return {"kind": "env", "env_var": var, "cast": "str", "value": dval}
    return None


def parse_module_constants(text: str, module: str) -> dict[str, ConstFact]:
    """AST-parse ONE module's top-level constants (literal + env-driven). Narrow on purpose —
    function bodies and computed values are out of scope (same discipline as
    check_gate_provenance._ModuleIndex)."""
    facts: dict[str, ConstFact] = {}
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return facts
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value_node = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            name, value_node = node.target.id, node.value
        else:
            continue
        payload = _classify_value(value_node)
        if payload is not None:
            ref = payload.pop("default_ref", None)
            fact = ConstFact(name=name, module=module, lineno=node.lineno, **payload)
            if ref is not None:
                ref_fact = facts.get(ref)
                if ref_fact is not None and ref_fact.kind == "literal":
                    fact.value = ref_fact.value
            facts[name] = fact
    return facts


def collect_code_facts(repo: Path = REPO, modules: tuple[str, ...] = RULE_MODULES) -> dict[str, ConstFact]:
    """All rule-module constants keyed by name. On a name collision the FIRST module wins
    (constants.py is listed first deliberately — it is the shared-constants module)."""
    out: dict[str, ConstFact] = {}
    for rel in modules:
        p = repo / rel
        if not p.exists():
            continue
        for name, fact in parse_module_constants(p.read_text(), rel).items():
            out.setdefault(name, fact)
    return out


# ───────────────────────────── runtime toggles (source b) ─────────────────────────────

@dataclass
class ToggleFact:
    name: str
    style: str                # "runtime" (get_runtime_toggle: DB>env>default) | "state" (get_safeguard_state per mode)
    env_var: str | None = None
    default: bool = True
    where: str = ""           # file:line of first sighting


_RT_TOGGLE_RE = re.compile(
    r'get_runtime_toggle\(\s*["\']([a-z0-9_]+)["\']\s*,\s*["\']([A-Z0-9_]+)["\']'
    r'(?:\s*,\s*default\s*=\s*(True|False))?', re.S)
_SG_TOGGLE_RE = re.compile(r'get_safeguard_state\(\s*["\']([a-z0-9_]+)["\']')

# One walk+read of agents/market_intelligence/**/*.py per repo per process —
# discover_runtime_toggles and scan_live_comments both consume it (each used to walk
# and read the whole tree separately).
_AGENT_SRC_CACHE: dict[Path, list[tuple[str, str]]] = {}


def _agent_sources(repo: Path = REPO) -> list[tuple[str, str]]:
    """[(rel_path, text)] for every non-__pycache__ .py under agents/market_intelligence."""
    cached = _AGENT_SRC_CACHE.get(repo)
    if cached is not None:
        return cached
    out: list[tuple[str, str]] = []
    root = repo / "agents" / "market_intelligence"
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        out.append((str(p.relative_to(repo)), p.read_text()))
    _AGENT_SRC_CACHE[repo] = out
    return out


def discover_runtime_toggles(repo: Path = REPO) -> dict[str, ToggleFact]:
    """Scan agents/market_intelligence for every runtime-toggle registration. Generated,
    not hand-listed: a new toggle in code appears here on the next run."""
    out: dict[str, ToggleFact] = {}
    for rel, text in _agent_sources(repo):
        for m in _RT_TOGGLE_RE.finditer(text):
            name, env_var, default = m.group(1), m.group(2), m.group(3)
            line = text.count("\n", 0, m.start()) + 1
            if name not in out:
                out[name] = ToggleFact(name=name, style="runtime", env_var=env_var,
                                       default=(default != "False"), where=f"{rel}:{line}")
        for m in _SG_TOGGLE_RE.finditer(text):
            name = m.group(1)
            line = text.count("\n", 0, m.start()) + 1
            if name not in out:
                out[name] = ToggleFact(name=name, style="state", default=False,
                                       where=f"{rel}:{line}")
    return out


# ───────────────────────────── prod state (sources b + c) ─────────────────────────────

@dataclass
class ProdState:
    reachable: bool = False
    error: str = ""
    env: dict[str, dict[str, str | None]] = field(default_factory=dict)   # container -> var -> value|None(unset)
    toggles: list[dict] = field(default_factory=list)                      # mi_safeguard_state rows
    strategies: list[dict] = field(default_factory=list)                   # mi_strategies rows
    deployed_commit: str = ""
    deployed_constants: dict[str, ConstFact] = field(default_factory=dict)  # parsed server-checkout constants.py

    def toggle_row(self, name: str, mode: str | None = None) -> dict | None:
        for r in self.toggles:
            if r["safeguard"] == name and (mode is None or r["account_mode"] == mode):
                return r
        return None


def _prod_script(env_vars: list[str]) -> str:
    """One read-only server-side script: targeted printenv (never a full env dump — that
    would capture secrets), two SELECTs, the deployed commit, and the server checkout's
    constants.py for deployed-code cross-check.

    ONE `docker exec` per container — the per-var loop runs INSIDE the container's shell
    (was one exec per var: 2 containers x ~39 vars = 78 sequential execs, ~5s of every
    session open). Still var-by-var `printenv "$v"` against the caller's already
    secret-filtered list — the never-dump-full-env property is unchanged."""
    vars_str = " ".join(env_vars)
    q_toggles = ("SELECT safeguard, account_mode, state, last_transition_at "
                 "FROM mi_safeguard_state ORDER BY safeguard, account_mode")
    q_strats = ("SELECT strategy_id, phase, enabled, live_real_enabled, position_size_multiplier "
                "FROM mi_strategies ORDER BY strategy_id")
    return f"""
VARS="{vars_str}"
for c in {' '.join(PROD_CONTAINERS)}; do
  echo "===ENV:$c==="
  docker exec "$c" sh -c 'for v in '"$VARS"'; do
    val=$(printenv "$v" 2>/dev/null) && echo "$v=$val" || echo "$v(unset)"
  done'
done
echo "===TOGGLES==="
docker exec apollo-postgres psql -U apollo -d apollo -t -A -F"|" -c "{q_toggles}" 2>&1
echo "===STRATEGIES==="
docker exec apollo-postgres psql -U apollo -d apollo -t -A -F"|" -c "{q_strats}" 2>&1
echo "===DEPLOYED_COMMIT==="
git -C {PROD_REPO_DIR} log -1 --format="%H %cI %s" 2>&1
echo "===CONSTANTS_PY==="
cat {PROD_REPO_DIR}/agents/market_intelligence/constants.py 2>&1
"""


def collect_prod(env_vars: list[str], runner=None) -> ProdState:
    """Read prod state over SSH, read-only. `runner` is injectable for tests. Degrades to
    ProdState(reachable=False, error=...) on ANY failure — the caller labels rows unknown."""
    safe_vars = sorted(v for v in set(env_vars)
                       if v and not any(tok in v.upper() for tok in _SECRET_TOKENS))
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_S}",
           SSH_HOST, _prod_script(safe_vars)]
    try:
        if runner is None:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=SSH_TOTAL_TIMEOUT_S)
            if proc.returncode != 0:
                return ProdState(error=f"ssh exited {proc.returncode}: {proc.stderr.strip()[:200]}")
            raw = proc.stdout
        else:
            raw = runner(cmd)
    except Exception as e:  # loud-ok: unreachable prod must degrade, never crash the tool
        return ProdState(error=f"{type(e).__name__}: {e}")
    return parse_prod_capture(raw)


def parse_prod_capture(raw: str) -> ProdState:
    """Parse the delimited capture. Pure — unit-testable without SSH."""
    st = ProdState(reachable=True)
    section, container = None, None
    const_lines: list[str] = []
    for line in raw.splitlines():
        m = re.match(r"^===([A-Z_]+)(?::([a-z0-9-]+))?===$", line)
        if m:
            section, container = m.group(1), m.group(2)
            if section == "ENV" and container:
                st.env[container] = {}
            continue
        if section == "ENV" and container:
            if line.endswith("(unset)"):
                st.env[container][line[:-len("(unset)")]] = None
            elif "=" in line:
                k, _, v = line.partition("=")
                st.env[container][k] = v
        elif section == "TOGGLES" and line.count("|") >= 3:
            sg, mode, state, ts = line.split("|", 3)
            st.toggles.append({"safeguard": sg, "account_mode": mode, "state": state,
                               "last_transition_at": ts})
        elif section == "STRATEGIES" and line.count("|") >= 4:
            sid, phase, enabled, live_real, mult = line.split("|", 4)
            st.strategies.append({"strategy_id": sid, "phase": phase,
                                  "enabled": enabled == "t", "live_real_enabled": live_real == "t",
                                  "position_size_multiplier": mult})
        elif section == "DEPLOYED_COMMIT" and line.strip():
            st.deployed_commit = line.strip()
        elif section == "CONSTANTS_PY":
            const_lines.append(line)
    if const_lines:
        st.deployed_constants = parse_module_constants(
            "\n".join(const_lines), "agents/market_intelligence/constants.py (deployed checkout)")
    return st


# ───────────────────────────── acting-value resolution ─────────────────────────────

@dataclass
class Resolved:
    value: object
    source: str          # plain words: where this value comes from
    known: bool = True   # False = prod-dependent and prod unreachable


class Resolver:
    """Answers 'what value is ACTING right now' for a constant, env var, or toggle —
    env overrides code default; a DB toggle row overrides both (get_runtime_toggle contract)."""

    def __init__(self, code: dict[str, ConstFact], toggles: dict[str, ToggleFact], prod: ProdState):
        self.code, self.toggles, self.prod = code, toggles, prod

    # env var -> Resolved (uses the code default from `fact` when prod lacks it)
    def env(self, var: str, code_default: object = None) -> Resolved:
        if self.prod.reachable:
            vals = {c: env.get(var) for c, env in self.prod.env.items() if var in env}
            set_vals = {c: v for c, v in vals.items() if v is not None}
            if set_vals:
                uniq = set(set_vals.values())
                if len(uniq) == 1:
                    return Resolved(next(iter(uniq)), f"prod env ({', '.join(sorted(set_vals))})")
                return Resolved(dict(set_vals), "prod env ⚠ CONTAINERS DISAGREE")
            return Resolved(code_default, "code default (env unset in prod)")
        return Resolved(code_default, "code default — prod UNREACHABLE, running value unknown",
                        known=False)

    def const(self, name: str) -> Resolved | None:
        fact = self.code.get(name)
        if fact is None:
            return None
        if fact.kind == "literal":
            dep = self.prod.deployed_constants.get(name) if self.prod.reachable else None
            if dep is not None and dep.kind == "literal" and dep.value != fact.value:
                return Resolved(dep.value,
                                f"DEPLOYED code ({dep.value!r}) ⚠ local code differs ({fact.value!r})")
            src = "code constant" + ("" if dep is not None or not self.prod.reachable
                                     else " (local; not re-checked on server)")
            return Resolved(fact.value, f"{src} {fact.module}:{fact.lineno}")
        r = self.env(fact.env_var, fact.value)
        if fact.cast == "bool" and isinstance(r.value, str):
            r = Resolved(r.value.lower() == "true", r.source, r.known)
        elif fact.cast in ("float", "int") and isinstance(r.value, str):
            try:
                r = Resolved({"float": float, "int": int}[fact.cast](r.value), r.source, r.known)
            except ValueError:
                pass
        return r

    def toggle(self, name: str) -> list[tuple[str, Resolved]]:
        """[(account_mode, Resolved(state))]. 'runtime'-style resolves DB > env > default;
        'state'-style is per-mode DB rows with fail-closed 'off' when absent."""
        t = self.toggles.get(name)
        rows = [r for r in self.prod.toggles if r["safeguard"] == name] if self.prod.reachable else []
        out: list[tuple[str, Resolved]] = []
        for r in rows:
            out.append((r["account_mode"],
                        Resolved(r["state"],
                                 f"mi_safeguard_state (set {r['last_transition_at'][:10] or 'date unrecorded'})")))
        if out:
            return out
        if t and t.style == "runtime":
            if t.env_var and self.prod.reachable:
                e = self.env(t.env_var, "true" if t.default else "false")
                return [("global", Resolved("on" if str(e.value).lower() == "true" else "off",
                                            f"{e.source} (no DB row)"))]
            return [("global", Resolved("on" if t.default else "off",
                                        "code default — prod UNREACHABLE, DB row + env unknown",
                                        known=self.prod.reachable))]
        if not self.prod.reachable:
            return [("?", Resolved("unknown", "prod UNREACHABLE — DB toggle row unknown", known=False))]
        return [("(no row)", Resolved("off", "no mi_safeguard_state row (fail-closed default)"))]

    def toggle_is_on(self, name: str) -> bool | None:
        """True/False when decidable, None when unknown. 'observe'/'live_r1' count as acting."""
        states = self.toggle(name)
        if any(not r.known for _, r in states):
            return None
        return any(str(r.value).lower() in ("on", "observe", "live_r1", "active") for _, r in states)


# ───────────────────────────── docs model ─────────────────────────────

_DATE_HEADING_RE = re.compile(r"^(#{2,3})\s+(\d{4}-\d{2}-\d{2})\s*[—-]?\s*(.*)$")
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")


def _relpath(p: Path) -> str:
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return p.name


@dataclass
class DocFile:
    path: Path
    lines: list[str]
    fence_mask: list[bool]          # True = inside a fenced code block
    historical_mask: list[bool]     # True = change-log region or a dated section (candidate history)
    line_date: list[str | None]     # governing dated-heading date per line (None outside dated regions)
    changelog_entries: list[tuple[str, str, int]]  # (date, title, lineno)
    # True = a FINDING doc (docs/analysis/**), which legitimately states "not deployed as of
    # <date>" as history rather than a live claim — `scan_stale_claims` skips those. Declared
    # here (not stapled on after construction) so the distinction is visible to a reader and to
    # the type system, not just to whichever code path happens to set the attribute.
    skip_stale_claims: bool = False


def load_doc(path: Path) -> DocFile:
    lines = path.read_text().splitlines()
    fence_mask, in_fence = [], False
    for ln in lines:
        if ln.strip().startswith("```"):
            in_fence = not in_fence
            fence_mask.append(True)
        else:
            fence_mask.append(in_fence)

    historical = [False] * len(lines)
    i = 0
    while i < len(lines):
        m = _HEADING_RE.match(lines[i])
        if m and not fence_mask[i]:
            level, title = len(m.group(1)), m.group(2)
            dm = _DATE_HEADING_RE.match(lines[i])
            is_changelog = re.search(r"change\s*log", title, re.I) is not None
            if dm or is_changelog:
                j = i + 1
                while j < len(lines):
                    m2 = _HEADING_RE.match(lines[j])
                    if m2 and not fence_mask[j] and len(m2.group(1)) <= level:
                        break
                    j += 1
                for k in range(i, j):
                    historical[k] = True
                i = j
                continue
        i += 1

    # Per-line governing date: the dated heading whose region a line sits under (mirrors the
    # mask walk's nesting rules). Feeds the superseded check — a masked claim is history only
    # when a LATER dated entry re-states its subject.
    line_date: list[str | None] = [None] * len(lines)
    cur_date: str | None = None
    cur_level = 0
    for i, ln in enumerate(lines):
        m = _HEADING_RE.match(ln)
        if m and not fence_mask[i]:
            dm = _DATE_HEADING_RE.match(ln)
            if dm:
                cur_date, cur_level = dm.group(2), len(m.group(1))
            elif cur_date is not None and len(m.group(1)) <= cur_level:
                cur_date = None
        line_date[i] = cur_date

    # Change-log entries are collected over the WHOLE file (dated headings nest INSIDE the
    # change-log region, which the region walk above deliberately skips over).
    entries: list[tuple[str, str, int]] = []
    for i, ln in enumerate(lines):
        dm = _DATE_HEADING_RE.match(ln)
        if dm and not fence_mask[i]:
            entries.append((dm.group(2), dm.group(3).strip() or "(untitled)", i + 1))
    return DocFile(path=path, lines=lines, fence_mask=fence_mask,
                   historical_mask=historical, line_date=line_date, changelog_entries=entries)


def load_setup_docs(repo: Path = REPO) -> list[DocFile]:
    """Setup SSoTs plus the findings built on them.

    A finding is not a reference document, but it IS what decisions are made from, so a constant
    quoted in a conclusion has to match the acting value exactly as one quoted in an SSoT does.
    Retracted documents are skipped: they are kept deliberately as the record of a failure, and
    re-flagging their numbers forever would train everyone to ignore this check.
    """
    paths = [p for p in sorted(repo.glob(SETUP_DOCS_GLOB)) if p.name not in ("README.md",)]
    paths += sorted(repo.glob(ARCH_DOCS_GLOB))
    docs = [load_doc(p) for p in paths]
    for g in FINDING_DOCS_GLOBS:
        for p in sorted(repo.glob(g)):
            d = load_doc(p)
            head = "\n".join(getattr(d, "text", "").split("\n")[:12]).upper()
            # A retracted document is kept deliberately as the record of a failure. Re-flagging
            # its numbers forever trains everyone to ignore this check.
            if "RETRACTED" in head or "DO NOT CITE" in head:
                continue
            # ⚠ FINDINGS GET THE VALUE-MISMATCH RULE ONLY, never the deployment-status rule.
            # A finding legitimately says "not deployed as of 2026-07-20" — that is HISTORY, and
            # flagging it is noise. Measured when this scan was added: 13 stale-claim hits, all
            # of them dated statements that were true when written, against 8 real value
            # mismatches. A checker that cries wolf gets switched off, which is worse than not
            # having it. The mismatch rule is the one that matters: a CONSTANT quoted in a
            # conclusion must still be the acting value, or the conclusion is about a system
            # that no longer exists.
            d.skip_stale_claims = True
            docs.append(d)
    return docs


# ───────────────────────────── DRIFT detection ─────────────────────────────

@dataclass
class DriftRow:
    rule: str        # which drift rule fired
    severity: str    # DRIFT | UNVERIFIED | UNKNOWN | INFO
    where: str       # doc-or-code file:line
    claim: str       # what the prose says
    actual: str      # what code/prod says
    words: str       # plain-words takeaway


# Claims that assert something is NOT acting. Two tiers:
_STRONG_DEPLOY_RE = re.compile(
    r"not\s+(?:yet\s+)?deployed|NOT\s+SHIPPED|awaiting\s+deploy|until\s+the\s+next[^.\n]{0,40}deploy"
    r"|still\s+places\s+the", re.I)
_FLAG_OFF_RE = re.compile(
    r"flag\s+OFF|default\s+OFF|default-off|OFF\s+by\s+default|shipp?e?d?s?\s+dark|built\s+OFF"
    r"|shipped\s+OFF|shadow[- ]only|no\s+live\s+caller", re.I)
# NOT stale claims: (a) descriptions of the revert path ("Flag OFF restores…", "OFF → old
# behaviour"); (b) lines that themselves assert the LIVE state (✅ / "Confirmed in production" —
# often while quoting the old stale wording, e.g. the corrected 2026-08-23 lines); (c) recorded
# DECISIONS not to ship ("not shipped — operator forks, decided", "tested and NOT shipped") —
# a permanent ruling is not a pending status and would otherwise fire forever.
_REVERT_DESC_RE = re.compile(
    r"revert|restore|when\s+off|if\s+off|OFF\s*[→=:]|OFF\s*\("
    r"|OFF\s+(?:presents|keeps|preserves|leaves|yields|means|falls\s+back)", re.I)
_DECIDED_NO_SHIP_RE = re.compile(
    r"\b(?:decided|ruled\s+out|not\s+worth|tested\s+and\s+not\s+shipped)\b", re.I)
_LIVE_ASSERT_RE = re.compile(r"✅|Confirmed in production|\bLIVE\b\s*\.")
# The docs' own convention for naming a section's governing flag: "**Flag**: `NAME`".
_SECTION_FLAG_RE = re.compile(r"\*\*Flag\*\*:\s*`([A-Za-z_][A-Za-z0-9_]+)`")

_IDENT_RE = re.compile(r"\b([A-Z][A-Z0-9_]{3,})\b")
_TOGGLE_IDENT_RE = re.compile(r"[`'\"(]([a-z][a-z0-9_]{3,})[`'\")]")

# Evidence that a doc mention records the ON/live state (drift rule 2). Deliberately does NOT
# include a bare "on" — conditional instructions ("requires X already on") must not count.
_ON_EVIDENCE_RE = re.compile(
    r"flipped|went\s+live|now\s+on\b|is\s+on\b|turned\s+on|\bLIVE\b|ON\s+since|→\s*on|->\s*on"
    r"|=\s*\*{0,2}on\b")


def _paragraph_bounds(lines: list[str], idx: int) -> tuple[int, int]:
    lo = idx
    while lo > 0 and lines[lo - 1].strip():
        lo -= 1
    hi = idx
    while hi < len(lines) - 1 and lines[hi + 1].strip():
        hi += 1
    return lo, hi


def _section_bounds(doc: DocFile, idx: int) -> tuple[int, int]:
    lo = idx
    while lo > 0 and not (_HEADING_RE.match(doc.lines[lo]) and not doc.fence_mask[lo]):
        lo -= 1
    hi = idx + 1
    while hi < len(doc.lines) and not (_HEADING_RE.match(doc.lines[hi]) and not doc.fence_mask[hi]):
        hi += 1
    return lo, hi - 1


def _identifier_states(text: str, res: Resolver) -> list[tuple[str, bool | None, str]]:
    """(identifier, acting_on|None(unknown), evidence) for every checkable FLAG-LIKE identifier
    in text. Numeric constants are deliberately NOT on/off signals (RISK_PCT=0.01 is not 'ON');
    only env-driven values, toggles, bool constants, and None-able constants qualify."""
    out = []
    for name in dict.fromkeys(_IDENT_RE.findall(text)):
        fact = res.code.get(name)
        if fact is None:
            continue
        if fact.kind == "env":
            r = res.env(fact.env_var, fact.value)
            v = str(r.value).lower() if r.value is not None else ""
            if not r.known:
                out.append((name, None, r.source))
            else:
                on = v not in ("", "false", "0", "none", "off", "shadow")
                out.append((name, on, f"{fact.env_var}={r.value!r} [{r.source}]"))
        elif fact.kind == "literal" and (fact.value is None or isinstance(fact.value, bool)):
            out.append((name, bool(fact.value), f"{name} = {fact.value!r} in {fact.module}"))
    for tname in dict.fromkeys(_TOGGLE_IDENT_RE.findall(text)):
        if tname in res.toggles:
            on = res.toggle_is_on(tname)
            states = ", ".join(f"{m}:{r.value}" for m, r in res.toggle(tname))
            out.append((tname, on, f"toggle `{tname}` → {states}"))
    return out


def _superseded_later(doc: DocFile, idx: int, names: list[str]) -> bool:
    """True when a LATER dated entry in the same doc mentions any of `names` — the masked
    claim at `idx` is then genuinely historical (a later entry re-addressed its subject).
    Strictly later DATE, so sibling same-day entries never supersede each other; fenced
    mentions count (a later entry quoting the identifier is re-stating the subject)."""
    claim_date = doc.line_date[idx]
    if claim_date is None:
        return False  # undatable masked region — supersession unprovable
    for j, d in enumerate(doc.line_date):
        if d is not None and d > claim_date and any(nm in doc.lines[j] for nm in names):
            return True
    return False


def scan_stale_claims(doc: DocFile, res: Resolver) -> list[DriftRow]:
    """Drift rule 1 — a doc claim 'not yet deployed / flag OFF / shadow only' for something
    that IS acting.

    Historical regions (change log, dated sections) are NOT blanket-exempt (that exemption hid
    76% of the status-shaped corpus and re-created the exact 2026-08-23 failure inside the tool
    built to prevent it): a masked status claim is historical ONLY IF a LATER dated entry in
    the same doc mentions the same subject (the identifiers the claim names). The most recent
    statement about a subject is a CURRENT claim wherever it sits, and is scanned like prose.
    A masked STRONG (deployment-status) line naming NO resolvable identifier is reported
    UNVERIFIED (historical, unsuperseded) — never dropped silently. The weaker flag-OFF tier
    with no identifier stays silent in masked regions exactly as it does in unmasked prose
    (measured 2026-08-23: 16 such lines, 15 genuine narrative/history — reporting them is
    flood, and the one real rot-shape among them is caught by the strong tier instead).
    Dated-entry heading lines themselves are exempt: a title is self-dated history ('what
    happened that day'), not a status claim."""
    rows: list[DriftRow] = []
    # Findings (docs/analysis, docs/design) opt out of this rule — see load_setup_docs.
    # They legitimately carry dated "not deployed" statements, which are history, not drift.
    if getattr(doc, "skip_stale_claims", False):
        return rows
    rel = _relpath(doc.path)
    for i, line in enumerate(doc.lines):
        if doc.fence_mask[i]:
            continue
        masked = doc.historical_mask[i]
        if masked and _HEADING_RE.match(line):
            continue
        strong = _STRONG_DEPLOY_RE.search(line)
        flagoff = _FLAG_OFF_RE.search(line)
        if not (strong or flagoff):
            continue
        plo0, phi0 = _paragraph_bounds(doc.lines, i)
        para0 = "\n".join(doc.lines[plo0:phi0 + 1])
        if _LIVE_ASSERT_RE.search(para0) or _ON_EVIDENCE_RE.search(para0):
            continue  # the paragraph asserts LIVE / records the flip ("shipped OFF, then flipped")
                      # — often while quoting the old stale wording
        if not strong and _REVERT_DESC_RE.search(line):
            continue  # a description of the revert path, not a status claim
        if _DECIDED_NO_SHIP_RE.search(line):
            continue  # a recorded decision NOT to ship — a permanent ruling, not a pending status
        plo, phi = _paragraph_bounds(doc.lines, i)
        para = "\n".join(doc.lines[plo:phi + 1])
        ids = _identifier_states(para, res)
        if not ids:
            # Fall back to the section's DECLARED flag ("**Flag**: `NAME`") — but only when the
            # claim is actually about a flag/phase/deploy state, so an unrelated in-section
            # remark can't be pinned on the section's flag.
            slo, shi = _section_bounds(doc, i)
            section_text = "\n".join(doc.lines[slo:shi + 1])
            if strong or re.search(r"flag|phase|deploy", line, re.I):
                fm = _SECTION_FLAG_RE.search(section_text)
                if fm:
                    ids = _identifier_states(f"{fm.group(1)} `{fm.group(1)}`", res)
        claim = line.strip()[:160]
        if masked:
            subjects = [name for name, _, _ in ids]
            if subjects and _superseded_later(doc, i, subjects):
                continue  # a later dated entry re-states this subject — genuinely historical
            if not subjects:
                if strong:
                    rows.append(DriftRow(
                        rule="stale-claim", severity="UNVERIFIED", where=f"{rel}:{i + 1}",
                        claim=claim,
                        actual="historical entry, unsuperseded — no later dated entry re-states "
                               "this subject, and no checkable flag is named",
                        words="A status claim in a dated entry that is still the doc's most recent "
                              "word on its subject, and nothing can verify it — the exact shape "
                              "that rotted on 2026-08-23. Re-check by hand; tie it to a flag or "
                              "add a superseding entry."))
                continue
            # else: the most recent statement about this subject — scan exactly like prose.
        on_ids = [x for x in ids if x[1] is True]
        unknown_ids = [x for x in ids if x[1] is None]
        if on_ids:
            ident, _, ev = on_ids[0]
            rows.append(DriftRow(
                rule="stale-claim", severity="DRIFT", where=f"{rel}:{i + 1}",
                claim=claim, actual=ev,
                words=f"The doc says this is off/not deployed, but `{ident}` IS acting right now."))
        elif unknown_ids and (strong or flagoff):
            ident, _, ev = unknown_ids[0]
            rows.append(DriftRow(
                rule="stale-claim", severity="UNKNOWN", where=f"{rel}:{i + 1}",
                claim=claim, actual=ev,
                words=f"Claim depends on `{ident}` whose prod value is unknown (prod unreachable) — verify by hand."))
        elif strong:
            rows.append(DriftRow(
                rule="stale-claim", severity="UNVERIFIED", where=f"{rel}:{i + 1}",
                claim=claim, actual="no checkable flag named near the claim",
                words="A deployment-status assertion nothing can verify — exactly the kind of line "
                      "that rotted on 2026-08-23. Re-check it by hand and tie it to a flag or date."))
    return rows


def scan_unrecorded_flips(docs: list[DocFile], res: Resolver) -> list[DriftRow]:
    """Drift rule 2 — a runtime toggle that prod says is ON while every setup-doc mention still
    reads OFF/dark (i.e. the flip was never recorded in the SSoT). Missing the env/DB row does
    NOT mean off — this is exactly how PROFIT_TRIGGER_R was misread."""
    rows: list[DriftRow] = []
    if not res.prod.reachable:
        return rows
    on_rows = [r for r in res.prod.toggles if str(r["state"]).lower() == "on"]
    for row in on_rows:
        name = row["safeguard"]
        mentions: list[tuple[DocFile, int]] = []
        for doc in docs:
            for i, line in enumerate(doc.lines):
                if name in line and not doc.fence_mask[i]:
                    mentions.append((doc, i))
        if not mentions:
            continue  # SSoT for this toggle lives elsewhere — out of scope (see module docstring)
        has_on_evidence = any(_ON_EVIDENCE_RE.search(doc.lines[i]) for doc, i in mentions)
        says_off = any(_FLAG_OFF_RE.search(doc.lines[i]) for doc, i in mentions)
        if has_on_evidence or not says_off:
            continue
        first = mentions[0]
        when = row["last_transition_at"][:16] or "date unrecorded"
        rows.append(DriftRow(
            rule="unrecorded-flip", severity="DRIFT",
            where=f"{_relpath(first[0].path)}:{first[1] + 1}",
            claim=f"every doc mention of `{name}` still says OFF/dark",
            actual=f"mi_safeguard_state: {name}[{row['account_mode']}] = on (since {when})",
            words=f"`{name}` was flipped ON in prod but the setup docs never recorded it — "
                  f"the docs still read as if it were dark."))
    return rows


_DOC_VALUE_RE = re.compile(r"\b([A-Z][A-Z0-9_]{3,})`?\s*=\s*(-?\d[\d_]*(?:\.\d+)?)\b")


def scan_value_mismatches(docs: list[DocFile], res: Resolver) -> list[DriftRow]:
    """Drift rule 3a — a doc naming a NUMERIC value different from the acting constant.
    Historical regions are exempt ONLY when a later dated entry mentions the same constant
    (an old value legitimately quoted in superseded history); the most recent dated entry
    naming a constant is a current claim and is checked like prose (same superseded rule as
    scan_stale_claims — the blanket mask hid current claims). Dated-entry headings exempt."""
    rows: list[DriftRow] = []
    for doc in docs:
        rel = _relpath(doc.path)
        for i, line in enumerate(doc.lines):
            if doc.fence_mask[i]:
                continue
            if doc.historical_mask[i] and _HEADING_RE.match(line):
                continue
            for m in _DOC_VALUE_RE.finditer(line):
                name, sval = m.group(1), m.group(2)
                r = res.const(name)
                if r is None or not r.known or not isinstance(r.value, (int, float)) or isinstance(r.value, bool):
                    continue
                if doc.historical_mask[i] and _superseded_later(doc, i, [name]):
                    continue  # an old value quoted in genuinely superseded history
                # RECONCILED-HISTORY notation ("NAME=75.0 ⚠now 50.0"): a finding is a dated
                # record of what was decided ON a value, so rewriting its number would falsify
                # the record. Annotating it does not. When the annotation matches the acting
                # value the line is reconciled — the reader sees both what it decided on and
                # what is live — and it stops being drift. When the acting value moves again,
                # the annotation goes stale and this fires once more, which is the point:
                # reconciliation is a claim about NOW, and it has to keep earning that.
                # Allow the closing punctuation of whatever markup wraps the value —
                # `NAME = 6.0` ⚠now 5.0, **NAME=6.0** ⚠now 5.0 — to sit between the two.
                ann = re.match(r"[`*_)\]]*\s*⚠\s*now\s+(-?\d[\d_]*(?:\.\d+)?)",
                               line[m.end():])
                if ann:
                    try:
                        if float(ann.group(1).replace("_", "")) == float(r.value):
                            continue
                    except ValueError:
                        pass
                # Transition notation ("NAME = 60 → 10"): the doc's claimed CURRENT value is
                # the one AFTER the arrow — check that, not the recorded old value.
                arrow = re.match(r"\s*(?:→|->)\s*(-?\d[\d_]*(?:\.\d+)?)", line[m.end():])
                if arrow:
                    sval = arrow.group(1)
                try:
                    doc_val = float(sval.replace("_", ""))
                except ValueError:
                    continue
                if abs(doc_val - float(r.value)) > 1e-9:
                    rows.append(DriftRow(
                        rule="value-mismatch", severity="DRIFT", where=f"{rel}:{i + 1}",
                        claim=f"{name}={sval}", actual=f"{name} = {r.value} [{r.source}]",
                        words=f"The doc quotes {name} as {sval} but the acting value is {r.value}."))
    return rows


def scan_registry_drift() -> list[DriftRow]:
    """Drift rule 3b — reuse scripts/check_gate_provenance.py over the existing 26-gate registry
    (never a second registry): registry-vs-code value drift + citations that no longer resolve."""
    rows: list[DriftRow] = []
    try:
        sys.path.insert(0, str(REPO))
        from scripts.check_gate_provenance import evaluate_entry
        from scripts.gate_provenance_registry import GATE_REGISTRY
    except Exception as e:  # loud-ok: registry import failure is itself worth a row
        return [DriftRow(rule="gate-registry", severity="UNKNOWN", where="scripts/gate_provenance_registry.py",
                         claim="registry unavailable", actual=str(e)[:120],
                         words="Could not reuse the gate registry — run scripts/check_gate_provenance.py by hand.")]
    for entry in GATE_REGISTRY:
        for problem in evaluate_entry(entry, REPO):
            kind = problem.get("kind", "?")
            if kind == "UNCITED":
                continue  # tracked by check_gate_provenance's own ratchet baseline
            rows.append(DriftRow(
                rule="gate-registry", severity="DRIFT", where=entry["file"],
                claim=f"{entry['id']} registered as {entry.get('value')!r}",
                actual=f"{kind}: {problem.get('msg', '')[:140]}",
                words=f"The gate registry and the live code/doc disagree about {entry['id']} — "
                      f"same-commit update rule was missed."))
    return rows


_LIVE_COMMENT_RE = re.compile(r"#[^\n]*\bLIVE\b\s+(?:since\s+)?(\d{4}-\d{2}-\d{2})")


def scan_live_comments(docs: list[DocFile], repo: Path = REPO,
                       changelog_dates: set[str] | None = None) -> list[DriftRow]:
    """Drift rule 4 — a `# LIVE <date>` code comment with NO change-log entry dated that day in
    any setup SSoT: the code claims a rule went live and the SSoT never recorded it."""
    if changelog_dates is None:
        changelog_dates = {d for doc in docs for d, _, _ in doc.changelog_entries}
    rows: list[DriftRow] = []
    for rel, text in _agent_sources(repo):
        for m in _LIVE_COMMENT_RE.finditer(text):
            date = m.group(1)
            if date in changelog_dates:
                continue
            line = text.count("\n", 0, m.start()) + 1
            rows.append(DriftRow(
                rule="live-comment-no-changelog", severity="DRIFT", where=f"{rel}:{line}",
                claim=f"code comment says LIVE {date}",
                actual=f"no `### {date}` change-log entry in any docs/setups/*.md",
                words=f"Code marks a rule live on {date} but no setup SSoT change log records that day — "
                      f"the change was never written down where rules are looked up."))
    return rows


def detect_drift(docs: list[DocFile], res: Resolver) -> list[DriftRow]:
    rows: list[DriftRow] = []
    for doc in docs:
        rows += scan_stale_claims(doc, res)
    rows += scan_unrecorded_flips(docs, res)
    rows += scan_value_mismatches(docs, res)
    rows += scan_registry_drift()
    rows += scan_live_comments(docs)
    return rows


# ───────────────────────────── code fingerprints ─────────────────────────────

def code_fingerprint(rel: str, pattern: str, repo: Path = REPO) -> str | None:
    """'file:line' when `pattern` (regex) is present in the file, else None. Used for rules that
    are code SHAPE rather than a constant — if the shape disappears, the row says ABSENT loudly
    instead of asserting a rule that no longer exists."""
    p = repo / rel
    if not p.exists():
        return None
    m = re.search(pattern, p.read_text())
    if not m:
        return None
    return f"{rel}:{p.read_text().count(chr(10), 0, m.start()) + 1}"


# ───────────────────────────── report sections ─────────────────────────────

def _fmt(r: Resolved | None, unit: str = "") -> str:
    if r is None:
        return "⚠ ABSENT from code — this row's rule no longer exists; remove or re-derive it"
    val = r.value
    if isinstance(val, float) and val == int(val):
        val = int(val)
    if isinstance(val, int) and not isinstance(val, bool) and abs(val) >= 10_000:
        val = f"{val:,}"
    flag = "" if r.known else "  ⚠ UNKNOWN"
    return f"{val}{unit}  [{r.source}]{flag}"


def _toggle_line(res: Resolver, name: str) -> str:
    states = res.toggle(name)
    return "; ".join(f"{mode}={r.value} [{r.source}]" for mode, r in states)


def build_entry_section(res: Resolver) -> list[str]:
    L: list[str] = []
    strat = {s["strategy_id"]: s for s in res.prod.strategies}
    if res.prod.reachable and "magna53" in strat:
        s = strat["magna53"]
        money = "REAL money" if s["live_real_enabled"] else "staged (no real orders)"
        L.append(f"MAGNA53 EP — strategy phase '{s['phase']}', {money} [mi_strategies]")
    else:
        L.append("MAGNA53 EP — strategy phase unknown (prod unreachable; mi_strategies not read)")
    L.append(f"  gap floor: a stock must gap {_fmt(res.const('MIN_GAP_PCT'), '%')} over yesterday's close to be a candidate")
    L.append(f"  universe floors: prior close ≥ ${res.const('MIN_PREV_CLOSE').value if res.const('MIN_PREV_CLOSE') else '⚠ABSENT'}, "
             f"prior-day volume ≥ {_fmt(res.const('MIN_PREV_DAY_VOLUME'), ' shares')}")
    L.append(f"  pre-market shares floor: {_fmt(res.const('MIN_PREMARKET_SHARES'), ' shares')} "
             f"(carve-outs: 5× pre-market volume anomaly, or gap ≥10% with a strong-or-better catalyst)")
    L.append(f"  extension cap: skip if already up {_fmt(res.const('MAX_EXTENSION_PCT'), '%')} off the lowest close of the last ~5 days")
    L.append(f"  re-alert cooldown: {_fmt(res.const('EP_COOLDOWN_DAYS'), ' days')} (bypassed by gap ≥15% on a fresh earnings day)")
    L.append(f"  grading shortlist: only the top {_fmt(res.const('SHORTLIST_SIZE'))} per tick get graded; "
             f"ranked by the liquidity-led pre-score — toggle `ep_shortlist_prescore`: {_toggle_line(res, 'ep_shortlist_prescore')}")
    sep_bar, raw_bar = res.const("SEPARATION_BAR"), res.const("SEPARATION_BAR_RAW")
    L.append(f"  alert bar: score ≥ {_fmt(sep_bar)} on the presented scale (= raw {_fmt(raw_bar)}) fires a HIGH alert — "
             f"toggle `ep_score_separation`: {_toggle_line(res, 'ep_score_separation')}")
    L.append(f"  catalyst grade correction (lattice) — toggle `catalyst_tier_lattice`: {_toggle_line(res, 'catalyst_tier_lattice')} "
             f"(when on, every filter and the score read the corrected grade)")
    L.append(f"  earnings revenue gate: earnings catalysts downgraded unless revenue grew "
             f"{_fmt(res.const('EARNINGS_REVENUE_GATE_MIN_YOY'), '%')} year-over-year "
             f"(enabled: {_fmt(res.const('EARNINGS_REVENUE_GATE_ENABLED'))})")
    L.append(f"  real-time price overlay: hybrid pass-2 {_fmt(res.const('EP_RT_PASS2_ENABLED'))}, "
             f"full-universe overlay {_fmt(res.const('EP_RT_UNIVERSE_ENABLED'))}")
    L.append(f"    gap authority (real-time price DECIDES): `ep_rt_gap_authoritative`: {_toggle_line(res, 'ep_rt_gap_authoritative')}; "
             f"remove-only half `ep_rt_gap_down_authoritative`: {_toggle_line(res, 'ep_rt_gap_down_authoritative')}")
    L.append(f"    sustain rule (level must hold {_fmt(res.const('EP_RT_SUSTAIN_BARS'), ' minutes')}): "
             f"`ep_rt_sustain_enabled`: {_toggle_line(res, 'ep_rt_sustain_enabled')}")
    L.append(f"  at submission: gap re-checked on live price — `ep_rt_entry_gap_recheck`: {_toggle_line(res, 'ep_rt_entry_gap_recheck')}; "
             f"ask-aware trigger — `entry_ask_aware`: {_toggle_line(res, 'entry_ask_aware')}")
    fg = code_fingerprint("agents/market_intelligence/broker/live_tracker.py", r"fade_midpoint_ratio=None")
    L.append(f"  fade guard: MAGNA53 HIGH skips it (ratio None{' — ' + fg if fg else ' — ⚠ fingerprint ABSENT, re-check'}); "
             f"other strategies use ratio {_fmt(res.const('FADE_MIDPOINT_RATIO'))}")
    L.append("")
    L.append("9M EP (alert stream; the 9M Day-2 ENTRY was deleted 2026-08-02 — phase: "
             + (strat.get("9m_day2", {}).get("phase", "unknown") if res.prod.reachable else "unknown") + ")")
    L.append(f"  price ≥ ${res.const('_MIN_PRICE').value if res.const('_MIN_PRICE') else '⚠ABSENT'}, "
             f"dollar volume ≥ {_fmt(res.const('_MIN_DOLLAR_VOL_ACTUAL'))} traded (confirmed) / "
             f"{_fmt(res.const('_MIN_DOLLAR_VOL_ANTICIPATION'))} (anticipation)")
    L.append(f"  direction: gap ≥ {_fmt(res.const('_MIN_GAP_PCT'), '%')} OR intraday gain ≥ {_fmt(res.const('_MIN_INTRADAY_GAIN_PCT'), '%')}; "
             f"volume anomaly ≥ {_fmt(res.const('_ADV_ANOMALY_MULTIPLIER'), '× 20-day average')}")
    return L


def build_exit_section(res: Resolver) -> list[str]:
    L: list[str] = []
    stop_fp = code_fingerprint("agents/market_intelligence/broker/order_manager.py",
                               r"stop_loss_price = 2 \* orb_low - orb_high")
    if stop_fp:
        L.append(f"initial stop (MAGNA53): entry − 2R where R = entry − ORB low (placed at 2·ORB_low − ORB_high), "
                 f"at half size — dollar risk unchanged [{stop_fp}; operator-signed 2026-08-16]")
    else:
        L.append("initial stop (MAGNA53): ⚠ the 2R-stop code fingerprint is ABSENT — the stop rule has "
                 "changed; read order_manager.prepare_orb_order before saying anything about stops")

    ptr = res.const("PROFIT_TRIGGER_R")
    frame_fp = code_fingerprint("agents/market_intelligence/broker/order_manager.py",
                                r'_ORB_R_FRAME_SIGNAL_TYPES = frozenset\(\{"magna53"\}\)')
    standdown_fp = code_fingerprint("agents/market_intelligence/broker/live_tracker.py",
                                    r"skip_partial_decision=bool\(PROFIT_TRIGGER_R\)")
    trigger_on = ptr is not None and ptr.value not in (None, 0)
    L.append("")
    L.append("partial profit — TWO code paths exist; exactly ONE acts (misreading this is the "
             "2026-08-23 failure this tool exists to prevent):")
    act1 = "ACTING" if trigger_on else ("OFF (constant unset)" if ptr and ptr.known else "⚠ UNKNOWN")
    L.append(f"  1. INTRADAY [{act1}] — order_manager.scan_profit_triggers, every 5 minutes 9:30–16:00 ET:")
    L.append(f"     sells 1/3 the first time the in-hold minute HIGH reaches entry + {_fmt(ptr)} × R, "
             f"then moves the stop to breakeven.")
    if frame_fp:
        L.append(f"     R here = entry − ORB low for MAGNA53 (NOT the placed 2R stop distance — that would "
                 f"silently make the target +4R) [{frame_fp}]")
    else:
        L.append("     ⚠ the ORB-R target-frame fingerprint is ABSENT — re-read profit_target_r_per_share")
    act2 = "STANDING DOWN — never fires while the intraday trigger is on" if trigger_on else "ACTING (intraday trigger off)"
    L.append(f"  2. DAY 3-5 TIME GATE [{act2}] — live_tracker.run_partial_exits at 3:45 PM ET:")
    L.append("     day 3-4 sell 1/3 if the close is above entry; day 5+ sell 1/3 regardless.")
    if standdown_fp:
        L.append(f"     the stand-down is mechanical: skip_partial_decision=bool(PROFIT_TRIGGER_R) [{standdown_fp}] "
                 f"— setting PROFIT_TRIGGER_R=None restores this path with no code change.")
    else:
        L.append("     ⚠ the stand-down fingerprint is ABSENT — the two paths may BOTH be able to fire; "
                 "check live_tracker.run_partial_exits immediately.")

    L.append("")
    L.append("order shape of the partial (runtime toggles, per account mode):")
    L.append(f"  resting GTC limit AT the target instead of a market sell — `profit_take_resting_limit`: "
             f"{_toggle_line(res, 'profit_take_resting_limit')}")
    L.append(f"  freed 1/3 protected by an OCO (limit at target + stop at breakeven) — `profit_take_oco`: "
             f"{_toggle_line(res, 'profit_take_oco')}")
    L.append(f"  breakeven applied at the BROKER in real time — `breakeven_at_broker`: "
             f"{_toggle_line(res, 'breakeven_at_broker')}")
    L.append(f"  bracket-leg-safe stop handling (lets the partial execute on bracket orders) — "
             f"`partial_exit_leg_safe`: {_toggle_line(res, 'partial_exit_leg_safe')}")
    L.append("")
    L.append("trail: max(stock's 10-day, 20-day SMA) once enough closes exist; close below it exits "
             "(seeded from the stock's own closes since the 2026-08-08 fix)")
    L.append("stop moves are RAISE-ONLY, enforced against the live broker stop in update_stop (2026-08-10)")
    L.append("giveback floor: RULED OUT by the operator 2026-08-11 — winners run; no peak-lock floor")
    return L


def build_sizing_section(res: Resolver) -> list[str]:
    L: list[str] = []
    L.append(f"risk per trade: {_fmt(res.const('RISK_PCT'))} of equity (1.0 = 100%); "
             f"position cap {_fmt(res.const('MAX_POSITION_PCT'))} of equity per name")
    rs = res.const("REGIME_SIZING_ENABLED")
    L.append(f"regime-keyed sizing: {_fmt(rs)} — when true, risk % is scaled by market regime "
             f"and the old VIX/QQQ halving is replaced")
    mult = res.const("REGIME_RISK_MULTIPLIER")
    if mult and isinstance(mult.value, dict):
        pairs = ", ".join(f"{k} {v}×" for k, v in mult.value.items())
        L.append(f"  multipliers: {pairs}; unknown/stale regime floors to "
                 f"{_fmt(res.const('REGIME_SIZING_FALLBACK_MULTIPLIER'), '×')} and alerts loudly")
    L.append(f"max open positions: {_fmt(res.const('MAX_CONCURRENT_LIVE_POSITIONS'))}; "
             f"daily realized-loss stop: {_fmt(res.const('DAILY_LOSS_LIMIT_PCT'))} of equity")
    L.append(f"circuit breaker (KEPT, operator-ruled 2026-07-31): {_fmt(res.const('CIRCUIT_BREAKER_CONSEC_LOSSES'))} "
             f"straight losses pauses entries for {_fmt(res.const('CIRCUIT_BREAKER_COOLDOWN_DAYS'), ' day(s)')}")
    dbp = res.const("DRAWDOWN_BREAKER_PHASE")
    L.append(f"drawdown breaker: phase {_fmt(dbp)} — tiers WATCH {_fmt(res.const('DRAWDOWN_WATCH_TRIP_PCT'))} (warn) / "
             f"REDUCE {_fmt(res.const('DRAWDOWN_REDUCE_TRIP_PCT'))} (half size) / "
             f"BLOCK {_fmt(res.const('DRAWDOWN_BLOCK_TRIP_PCT'))} (no entries)")
    if res.prod.reachable:
        dd = [f"{r['account_mode']}={r['state']}" for r in res.prod.toggles if r["safeguard"] == "drawdown_breaker"]
        if dd:
            L.append(f"  current drawdown state: {', '.join(dd)} [mi_safeguard_state]")
        halt = res.prod.toggle_row("manual_trading_halt", "live")
        L.append(f"operator halt (/pause): {'ON — real-money entries blocked' if halt and halt['state'] == 'on' else 'off — trading allowed'} "
                 f"[mi_safeguard_state]")
        ksb = res.prod.toggle_row("kill_scale_band", "live")
        if ksb:
            L.append(f"kill/scale band: {ksb['state']} [mi_safeguard_state]")
    else:
        L.append("  current drawdown state / operator halt: unknown (prod unreachable)")
    L.append(f"master kill switch: LIVE_TRADING_ENABLED {_fmt(res.const('LIVE_TRADING_ENABLED'))} (boot-read)")
    if res.prod.reachable and res.prod.strategies:
        rows = ", ".join(f"{s['strategy_id']}={s['phase']}{'+real$' if s['live_real_enabled'] else ''}"
                         for s in res.prod.strategies)
        L.append(f"strategy phases [mi_strategies]: {rows}")
    return L


def build_replaced_section(docs: list[DocFile]) -> list[str]:
    """Every dated change-log entry across the setup SSoTs, newest first — the replacement
    history that stops a superseded rule being quoted as current."""
    L: list[str] = []
    supersede_re = re.compile(r"REVERSAL|REVERS|REPLACE|SUPERSED|CANCELL|RETIR|DELETED|REMOVED|→", re.I)
    for doc in docs:
        if not doc.changelog_entries:
            continue
        L.append(f"{doc.path.relative_to(REPO)}:")
        for date, title, lineno in sorted(doc.changelog_entries, key=lambda e: e[0], reverse=True):
            tag = "  ⇄" if supersede_re.search(title) else "   "
            L.append(f"{tag} {date}  {title[:110]}")
        L.append("")
    return L


# ───────────────────────────── main report ─────────────────────────────

def build_report(res: Resolver, docs: list[DocFile], drift: list[DriftRow],
                 drift_only: bool = False) -> str:
    out: list[str] = []
    now = datetime.now().astimezone()
    if res.prod.reachable:
        commit = res.prod.deployed_commit.split(" ")[0][:8] if res.prod.deployed_commit else "?"
        prod_line = f"prod: reachable (server checkout {commit})"
    else:
        prod_line = f"prod: UNREACHABLE ({res.prod.error[:90]}) — prod-derived rows are labelled unknown, not guessed"
    out.append("APOLLO LIVE RULES — generated from code + prod state, never from hand-written prose")
    out.append(f"generated {now:%Y-%m-%d %H:%M %Z} · {prod_line}")
    out.append("")

    sev_order = {"DRIFT": 0, "UNKNOWN": 1, "UNVERIFIED": 2, "INFO": 3}
    drift_sorted = sorted(drift, key=lambda r: (sev_order.get(r.severity, 9), r.where))
    out.append(f"== ⚠ DRIFT — where the prose contradicts code or prod ({len(drift_sorted)} finding(s)) ==")
    if not drift_sorted:
        out.append("  none found — every checked claim matches the acting state")
    for r in drift_sorted:
        out.append(f"  [{r.severity}] {r.where}  ({r.rule})")
        out.append(f"      doc says : {r.claim}")
        out.append(f"      actual   : {r.actual}")
        out.append(f"      → {r.words}")
    if drift_only:
        return "\n".join(out)

    out.append("")
    out.append("== ENTRY — what gets admitted and alerted ==")
    out += ["  " + l for l in build_entry_section(res)]
    out.append("")
    out.append("== EXIT — every path that reduces or closes a position ==")
    out += ["  " + l for l in build_exit_section(res)]
    out.append("")
    out.append("== SIZING + SAFEGUARDS ==")
    out += ["  " + l for l in build_sizing_section(res)]
    out.append("")
    out.append("== REPLACED — the rule-change history, newest first (⇄ = supersession/reversal) ==")
    out += ["  " + l for l in build_replaced_section(docs)]
    return "\n".join(out)


# ───────────────────────────── selftest ─────────────────────────────

def _git_show(rev_path: str) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(REPO), "show", rev_path],
                              capture_output=True, text=True, timeout=15)
        return proc.stdout if proc.returncode == 0 else None
    except Exception:
        return None


def run_selftest(res: Resolver) -> int:
    """Replay the two DOC-BORNE 2026-08-23 failures through the live drift rules, against the
    real pre-fix text from git history (which pytest fixtures can't carry). PASS = the rule
    catches the historical text; FAIL = a regression in the detector.

    The third failure (the partial-path misread) and the LIVE-comment rule are pinned by
    tests/test_live_rules.py (test_exit_section_names_both_partial_paths_and_the_acting_one,
    test_live_comment_without_changelog_entry_is_reported) — not duplicated here."""
    import tempfile
    results: list[tuple[str, str, str]] = []

    def _doc_from_text(text: str, name: str) -> DocFile:
        with tempfile.NamedTemporaryFile("w", suffix=f"-{name}.md", delete=False) as f:
            f.write(text)
            tmp = Path(f.name)
        try:
            return load_doc(tmp)
        finally:
            tmp.unlink()

    # Case 1 — magna53_ep.md's week-stale "Built, NOT yet deployed" (the 2R stop WAS live).
    text = _git_show(f"{_SELFTEST_FIX_COMMIT}^:docs/setups/magna53_ep.md")
    if text is None:
        results.append(("case 1 (stale 'NOT yet deployed', magna53)", "SKIP",
                        f"git history for {_SELFTEST_FIX_COMMIT} unavailable"))
    else:
        rows = scan_stale_claims(_doc_from_text(text, "magna53"), res)
        hits = [r for r in rows if "NOT yet deployed" in r.claim or "not yet deployed" in r.claim.lower()]
        results.append(("case 1 (stale 'NOT yet deployed', magna53)",
                        "PASS" if hits else "FAIL",
                        hits[0].claim[:100] if hits else "the stale line was NOT flagged"))

    # Case 2 — safeguards.md's four-week-stale "flag OFF by default" while REGIME_SIZING_ENABLED=true.
    text = _git_show(f"{_SELFTEST_FIX_COMMIT}^:docs/setups/safeguards.md")
    if text is None:
        results.append(("case 2 (stale 'flag OFF', regime sizing)", "SKIP",
                        f"git history for {_SELFTEST_FIX_COMMIT} unavailable"))
    else:
        case_res = res
        note = ""
        if not res.prod.reachable:
            sim = ProdState(reachable=True)
            sim.env = {c: {"REGIME_SIZING_ENABLED": "true"} for c in PROD_CONTAINERS}
            case_res = Resolver(res.code, res.toggles, sim)
            note = " (prod unreachable — env simulated ON, labelled)"
        rows = scan_stale_claims(_doc_from_text(text, "safeguards"), case_res)
        hits = [r for r in rows if "REGIME_SIZING_ENABLED" in r.actual and r.severity == "DRIFT"]
        results.append(("case 2 (stale 'flag OFF', regime sizing)" + note,
                        "PASS" if hits else "FAIL",
                        hits[0].actual[:100] if hits else "the stale flag claim was NOT resolved against prod env"))

    print("SELFTEST — replaying the two doc-borne 2026-08-23 failures through the live drift rules")
    print("(the partial-path misread + LIVE-comment rules are pinned by tests/test_live_rules.py)")
    failed = False
    for name, verdict, detail in results:
        print(f"  [{verdict}] {name}")
        print(f"         {detail}")
        failed = failed or verdict == "FAIL"
    return 1 if failed else 0


# ───────────────────────────── CLI ─────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="What rules are acting RIGHT NOW — from ground truth.")
    ap.add_argument("--drift-only", action="store_true", help="terse mode: DRIFT section only")
    ap.add_argument("--no-prod", action="store_true", help="skip the read-only SSH prod read")
    ap.add_argument("--selftest", action="store_true",
                    help="replay the two doc-borne 2026-08-23 failures from git history "
                         "(the rest of the coverage lives in tests/test_live_rules.py)")
    args = ap.parse_args(argv)

    code = collect_code_facts()
    toggles = discover_runtime_toggles()
    env_vars = [f.env_var for f in code.values() if f.kind == "env"] + \
               [t.env_var for t in toggles.values() if t.env_var]
    prod = ProdState(error="skipped (--no-prod)") if args.no_prod else collect_prod(env_vars)
    res = Resolver(code, toggles, prod)
    docs = load_setup_docs()

    if args.selftest:
        return run_selftest(res)

    drift = detect_drift(docs, res)
    print(build_report(res, docs, drift, drift_only=args.drift_only))
    return 0


if __name__ == "__main__":
    sys.exit(main())
