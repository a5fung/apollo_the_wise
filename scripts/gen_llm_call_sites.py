"""Generate shared/llm_call_sites.py — the call-site key -> model ROLE map (#690).

The replay that guards a new model release (agents/market_intelligence/model_resolution.py)
needs to know which ROLE each captured request belongs to, so a sample recorded at
`agents.market_intelligence.theme_engine:_rename_theme_to_fit_cluster` is replayed when the
sonnet tier moves and not when opus does. The runtime only sees a stack frame
(shared/llm_samples.call_site_key); this script derives the same key STATICALLY from the source,
together with the role its `model=` argument names:

  * every `<x>.messages.create(...)` Call node in agents/ shared/ core/ channels/ (Call nodes
    only — a docstring mentioning messages.create is not a call site; shared/llm_client.py is
    the transport itself and is excluded);
  * the model argument resolved through simple aliases (`_MODEL = X_MODEL`,
    `from shared.llm_models import X as _MODEL`, `effective_model("X")`, `**kwargs` built by
    `dict(model=...)`) and through a parameter's DEFAULT;
  * a call inside a pass-through wrapper (shared/llm_samples.PASSTHROUGH_*) is attributed to the
    wrapper's CALLERS — keyword or positional — recursively, exactly as the stack walk skips it;
  * a raw tier constant (HAIKU, OPUS_PIN …) or a literal id is UNTRACKED: it follows no role, so
    no tier move ever replays it.

FAILS LOUDLY (exit 1) on a model argument it cannot resolve or on one key resolving to two roles —
a silent guess would record samples under the wrong role, which is the failure this file exists
to prevent.

Run:  python3 scripts/gen_llm_call_sites.py          (rewrites shared/llm_call_sites.py)
      python3 scripts/gen_llm_call_sites.py --check  (exit 1 if the committed map is stale)
Gate: tests/test_llm_call_sites.py regenerates the map and compares it to the committed one.
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SCANNED = ("agents", "shared", "core", "channels")
EXCLUDED_FILES = frozenset({"shared/llm_client.py"})
# Synthetic re-sends, not call sites: the pre-adoption replay sends CAPTURED requests to a
# candidate model with capture disabled (its model is the candidate, never a role).
EXCLUDED_FUNCTIONS = frozenset({("agents.market_intelligence.model_resolution", "_replay_once")})
OUT_PATH = REPO / "shared" / "llm_call_sites.py"
_ROLES_MODULE = "shared.llm_models"
_MAX_DEPTH = 12

FuncNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]


class GenError(RuntimeError):
    pass


@dataclass
class Module:
    name: str
    rel: str
    tree: ast.Module
    assigns: dict[str, list[ast.expr]] = field(default_factory=dict)
    imports: dict[str, tuple[str, str]] = field(default_factory=dict)   # local -> (module, name)
    module_aliases: dict[str, str] = field(default_factory=dict)        # local -> module
    parents: dict[int, ast.AST] = field(default_factory=dict)


@dataclass(frozen=True)
class Role:
    role: str


@dataclass(frozen=True)
class Param:
    """The value is function `func`'s parameter `name` — bound by whoever calls `func`."""
    module: str
    func_lineno: int
    name: str


Result = Union[Role, Param]


def _module_name(rel: str) -> str:
    parts = rel[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _collect_imports(body: list[ast.stmt], module_name: str) -> tuple[dict, dict]:
    imports: dict[str, tuple[str, str]] = {}
    aliases: dict[str, str] = {}
    for node in body:
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                imports[a.asname or a.name] = (node.module, a.name)
        elif isinstance(node, ast.ImportFrom) and node.level:
            base = module_name.split(".")[: -node.level]
            mod = ".".join(base + ([node.module] if node.module else []))
            for a in node.names:
                imports[a.asname or a.name] = (mod, a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                aliases[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
    return imports, aliases


def load_modules(repo: Path = REPO) -> dict[str, Module]:
    mods: dict[str, Module] = {}
    for pkg in SCANNED:
        for path in sorted((repo / pkg).rglob("*.py")):
            rel = path.relative_to(repo).as_posix()
            if rel in EXCLUDED_FILES or "/backtester/" in rel:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover
                continue
            name = _module_name(rel)
            m = Module(name=name, rel=rel, tree=tree)
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            m.assigns.setdefault(t.id, []).append(node.value)
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
                    m.assigns.setdefault(node.target.id, []).append(node.value)
            m.imports, m.module_aliases = _collect_imports(tree.body, name)
            for parent in ast.walk(tree):
                for child in ast.iter_child_nodes(parent):
                    m.parents[id(child)] = parent
            mods[name] = m
    return mods


def _scope_chain(mod: Module, node: ast.AST) -> list[FuncNode]:
    """Enclosing functions, innermost first."""
    chain = []
    cur = mod.parents.get(id(node))
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            chain.append(cur)
        cur = mod.parents.get(id(cur))
    return chain


def _own_statements(func: FuncNode):
    """Nodes in `func`'s body that are not inside a nested function/class."""
    stack = list(func.body)
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                stack.append(child)


def _params(func: FuncNode) -> list[ast.arg]:
    a = func.args
    return list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)


def _param_default(func: FuncNode, name: str) -> Optional[ast.expr]:
    a = func.args
    positional = list(a.posonlyargs) + list(a.args)
    offset = len(positional) - len(a.defaults)
    for i, p in enumerate(positional):
        if p.arg == name and i >= offset:
            return a.defaults[i - offset]
    for p, d in zip(a.kwonlyargs, a.kw_defaults):
        if p.arg == name:
            return d
    return None


class Resolver:
    def __init__(self, mods: dict[str, Module], role_names: frozenset[str]):
        self.mods = mods
        self.role_names = role_names
        self._funcs: dict[tuple[str, int], FuncNode] = {}
        for m in mods.values():
            for node in ast.walk(m.tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self._funcs[(m.name, node.lineno)] = node

    # ── value resolution ────────────────────────────────────────────────────
    def _from_import(self, module: str, name: str, depth: int) -> Result:
        if module == _ROLES_MODULE:
            return Role(name if name in self.role_names else "UNTRACKED")
        target = self.mods.get(module)
        if target is None:
            raise GenError(f"cannot follow import of {name!r} from {module!r}")
        return self._module_name_value(target, name, depth + 1)

    def _module_name_value(self, mod: Module, name: str, depth: int) -> Result:
        if name in mod.assigns:
            return self._one_of([self.resolve(v, mod, [], depth + 1) for v in mod.assigns[name]],
                                f"{mod.rel}: {name}")
        if name in mod.imports:
            return self._from_import(*mod.imports[name], depth)
        raise GenError(f"{mod.rel}: cannot resolve module-level name {name!r}")

    @staticmethod
    def _one_of(results: list[Result], where: str) -> Result:
        uniq = set(results)
        if len(uniq) != 1:
            raise GenError(f"{where}: assigned several different models {sorted(map(str, uniq))}")
        return results[0]

    def resolve(self, expr: ast.expr, mod: Module, chain: list[FuncNode], depth: int = 0) -> Result:
        if depth > _MAX_DEPTH:
            raise GenError(f"{mod.rel}:{getattr(expr, 'lineno', '?')}: alias chain too deep")
        if isinstance(expr, ast.Constant):
            return Role("UNTRACKED")        # a literal id (# model-ok) follows no role
        if isinstance(expr, ast.Call):
            fn = expr.func
            fname = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
            if fname == "effective_model" and expr.args and isinstance(expr.args[0], ast.Constant):
                name = str(expr.args[0].value)
                return Role(name if name in self.role_names else "UNTRACKED")
            raise GenError(f"{mod.rel}:{expr.lineno}: model is a call this generator cannot follow")
        if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
            base = expr.value.id
            target = mod.module_aliases.get(base) or (
                ".".join(mod.imports[base]) if base in mod.imports else None)
            if target == _ROLES_MODULE:
                return self._from_import(_ROLES_MODULE, expr.attr, depth)
            raise GenError(f"{mod.rel}:{expr.lineno}: model attribute {ast.unparse(expr)!r} not followed")
        if isinstance(expr, ast.Name):
            name = expr.id
            for i, func in enumerate(chain):
                values = [n.value for n in _own_statements(func)
                          if isinstance(n, ast.Assign) and any(
                              isinstance(t, ast.Name) and t.id == name for t in n.targets)]
                if values:
                    return self._one_of([self.resolve(v, mod, chain[i:], depth + 1) for v in values],
                                        f"{mod.rel}:{func.name}: {name}")
                local_imports, _ = _collect_imports(
                    [n for n in _own_statements(func) if isinstance(n, (ast.ImportFrom, ast.Import))],
                    mod.name)
                if name in local_imports:
                    return self._from_import(*local_imports[name], depth)
                if any(p.arg == name for p in _params(func)):
                    return Param(mod.name, func.lineno, name)
            return self._module_name_value(mod, name, depth)
        raise GenError(f"{mod.rel}:{getattr(expr, 'lineno', '?')}: unsupported model expression "
                       f"{ast.unparse(expr)!r}")

    def finalize(self, res: Result, depth: int = 0) -> str:
        """A role name for `res`; a parameter resolves to its DEFAULT (the static attribution —
        what the call uses when its caller does not pass one)."""
        if isinstance(res, Role):
            return res.role
        func = self._funcs[(res.module, res.func_lineno)]
        mod = self.mods[res.module]
        default = _param_default(func, res.name)
        if default is None:
            raise GenError(f"{mod.rel}:{func.name}: model parameter {res.name!r} has no default and "
                           f"its function is not a pass-through wrapper — cannot attribute a role")
        chain = _scope_chain(mod, func)
        return self.finalize(self.resolve(default, mod, chain, depth + 1), depth + 1)

    # ── model argument of one create() call ─────────────────────────────────
    def model_of_create(self, call: ast.Call, mod: Module, chain: list[FuncNode]) -> Result:
        for kw in call.keywords:
            if kw.arg == "model":
                return self.resolve(kw.value, mod, chain)
        for kw in call.keywords:
            if kw.arg is None and isinstance(kw.value, ast.Name):
                built = self._kwargs_model(kw.value.id, mod, chain)
                if built is not None:
                    return built
        raise GenError(f"{mod.rel}:{call.lineno}: messages.create without a resolvable model=")

    def _kwargs_model(self, name: str, mod: Module, chain: list[FuncNode]) -> Optional[Result]:
        for i, func in enumerate(chain):
            for n in _own_statements(func):
                if not (isinstance(n, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == name for t in n.targets)):
                    continue
                v = n.value
                if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "dict":
                    for kw in v.keywords:
                        if kw.arg == "model":
                            return self.resolve(kw.value, mod, chain[i:])
                if isinstance(v, ast.Dict):
                    for k, val in zip(v.keys, v.values):
                        if isinstance(k, ast.Constant) and k.value == "model":
                            return self.resolve(val, mod, chain[i:])
        return None


def _is_create_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create" and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "messages")


def _passthrough_outer(mod: Module, chain: list[FuncNode], pt_modules, pt_functions) -> Optional[FuncNode]:
    """The pass-through function whose CALLERS own this site, or None when the innermost frame
    is itself a call site. A nested helper inside a pass-through module (judge_transport's `_call`)
    is called by its encloser, so the outermost enclosing function is the one to follow."""
    if not chain:
        return None
    if mod.name in pt_modules:
        return chain[-1]
    for func in chain:
        if (mod.name, func.name) in pt_functions:
            return func
        break  # only the innermost frame can be the wrapper; an outer one is a normal caller
    return None


def _callers_of(resolver: Resolver, target_mod: Module, func: FuncNode):
    """(module, Call node) for every call of `func` by name — same-module calls, calls through a
    `from <its module> import <name>`, and `<module alias>.<name>(...)`."""
    for m in resolver.mods.values():
        # every `from <its module> import <name> [as x]` anywhere in the file, function-local
        # imports included (judge_divergence imports grade_holistic inside _run)
        all_imports, _ = _collect_imports(
            [n for n in ast.walk(m.tree) if isinstance(n, ast.ImportFrom)], m.name)
        imported_as = {local for local, (src, name) in all_imports.items()
                       if src == target_mod.name and name == func.name}
        mod_aliases = {local for local, src in m.module_aliases.items() if src == target_mod.name}
        mod_aliases |= {local for local, (src, name) in all_imports.items()
                        if f"{src}.{name}" == target_mod.name}
        if m.name == target_mod.name:
            imported_as.add(func.name)
        if not imported_as and not mod_aliases:
            continue
        for node in ast.walk(m.tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Name):
                hit = f.id in imported_as
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                hit = f.attr == func.name and f.value.id in mod_aliases
            else:
                hit = False
            if hit:
                yield m, node


def _bind_param(call: ast.Call, func: FuncNode, pname: str) -> Optional[ast.expr]:
    for kw in call.keywords:
        if kw.arg == pname:
            return kw.value
    positional = [p.arg for p in list(func.args.posonlyargs) + list(func.args.args)]
    if pname in positional:
        idx = positional.index(pname)
        if idx < len(call.args) and not any(isinstance(a, ast.Starred) for a in call.args[: idx + 1]):
            return call.args[idx]
    return None


def build_map(repo: Path = REPO) -> dict[str, str]:
    """{call-site key: ROLE or "UNTRACKED"} for every production messages.create."""
    from shared.llm_models import RESOLVED_ROLES
    from shared.llm_samples import PASSTHROUGH_FUNCTIONS, PASSTHROUGH_MODULES

    mods = load_modules(repo)
    resolver = Resolver(mods, frozenset(RESOLVED_ROLES))
    found: dict[str, set[str]] = {}

    def attribute(mod: Module, chain: list[FuncNode], res: Result, depth: int) -> None:
        if depth > _MAX_DEPTH:
            raise GenError(f"{mod.rel}: wrapper chain too deep")
        if not chain:
            raise GenError(f"{mod.rel}: messages.create at module level has no call-site frame")
        wrapper = _passthrough_outer(mod, chain, PASSTHROUGH_MODULES, PASSTHROUGH_FUNCTIONS)
        if wrapper is None:
            key = f"{mod.name}:{chain[0].name}"
            found.setdefault(key, set()).add(resolver.finalize(res))
            return
        callers = list(_callers_of(resolver, mod, wrapper))
        if not callers:
            raise GenError(f"{mod.rel}:{wrapper.name}: pass-through wrapper has no caller in "
                           f"{'/'.join(SCANNED)}")
        for cmod, call in callers:
            cchain = _scope_chain(cmod, call)
            bound: Result = res
            if isinstance(res, Param) and res.module == mod.name and res.func_lineno == wrapper.lineno:
                arg = _bind_param(call, wrapper, res.name)
                if arg is None:
                    default = _param_default(wrapper, res.name)
                    if default is None:
                        raise GenError(f"{cmod.rel}:{call.lineno}: calls {wrapper.name} without "
                                       f"{res.name!r} and it has no default")
                    bound = resolver.resolve(default, mod, _scope_chain(mod, wrapper))
                else:
                    bound = resolver.resolve(arg, cmod, cchain)
            attribute(cmod, cchain, bound, depth + 1)

    for mod in mods.values():
        for node in ast.walk(mod.tree):
            if _is_create_call(node):
                chain = _scope_chain(mod, node)
                if chain and (mod.name, chain[0].name) in EXCLUDED_FUNCTIONS:
                    continue
                attribute(mod, chain, resolver.model_of_create(node, mod, chain), 0)

    clashes = {k: v for k, v in found.items() if len(v) > 1}
    if clashes:
        raise GenError("one call-site key resolves to several roles (the stack walk cannot tell "
                       f"them apart — add a pass-through or split the function): {clashes}")
    return {k: next(iter(v)) for k, v in sorted(found.items())}


_HEADER = '''"""GENERATED by scripts/gen_llm_call_sites.py — do not edit by hand (#690).

Call-site key (`module:function`, the first frame outside shared/llm_client and the pass-through
wrappers — shared/llm_samples.call_site_key) -> the model ROLE that call's `model=` argument names,
or "UNTRACKED" for a raw tier pin / literal id that follows no role. The pre-adoption replay
(agents/market_intelligence/model_resolution.py) uses it to decide which captured requests a tier
move must replay. Regenerate after adding or moving a messages.create:

    python3 scripts/gen_llm_call_sites.py

tests/test_llm_call_sites.py fails when this file is stale.
"""

CALL_SITES: dict[str, str] = {
'''


def render(mapping: dict[str, str]) -> str:
    lines = [_HEADER]
    for key, role in sorted(mapping.items()):
        lines.append(f"    {key!r}: {role!r},\n")
    lines.append("}\n")
    return "".join(lines)


def main(argv: list[str]) -> int:
    try:
        mapping = build_map()
    except GenError as e:
        print(f"gen_llm_call_sites: {e}", file=sys.stderr)
        return 1
    text = render(mapping)
    if "--check" in argv:
        current = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else ""
        if current != text:
            print("gen_llm_call_sites: shared/llm_call_sites.py is stale — run "
                  "python3 scripts/gen_llm_call_sites.py", file=sys.stderr)
            return 1
        print(f"gen_llm_call_sites: {len(mapping)} call sites, map is current")
        return 0
    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"gen_llm_call_sites: wrote {len(mapping)} call sites to {OUT_PATH.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
