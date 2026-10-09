"""#505 closeness scorers — PRE-BUILD copy for the phase-1 replay (rule fixed before any result was seen).
If built, the engine's copies (theme_engine.parent_industry_overlap / parent_word_similarity) are the
ones of record and the replay uses them."""
import re

STOP_WORDS = frozenset("""
a an and are as at be been being but by can could did do does for from had has have he her his how i if in
into is it its itself may might more most much no nor not of off on once only or other our out over own same
she should so some such than that the their them then there these they this those through to too under until
up very was we were what when where which while who whom why will with would you your also just about across
after again against all any because before below between both down during each few further here many new
one two three us via vs per amid around still yet ever even well
""".split())
# Words that appear across theme names/descriptions regardless of subject — they say nothing about closeness.
THEME_COMMON = frozenset("""
stock stocks company companies theme themes group groups sector sectors name names play plays basket baskets
catalyst catalysts shared share driven drive driving rally rallies rallying move moves moving trade trading
investor investors broad broader broadly market markets demand expectation expectations appear appears seem
seems single clear common recent recently strong stronger higher rise rising gain gains boost boosted lift
lifted renewed optimism headline headlines news report reports result results quarter quarterly outlook
analyst analysts rating ratings target targets price prices tailwind momentum rotation rebound recovery
upgrade upgrades sentiment continued continue spending fresh specific
""".split())


def _stem(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 5 and tok.endswith("ing"):
        return tok[:-3]
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def closeness_tokens(theme: dict) -> set[str]:
    text = f"{theme.get('name') or ''} {theme.get('description') or ''}".lower()
    out = set()
    for tok in re.split(r"[^a-z0-9]+", text):
        if len(tok) < 3 or tok.isdigit() or tok in STOP_WORDS or tok in THEME_COMMON:
            continue
        s = _stem(tok)
        if s in STOP_WORDS or s in THEME_COMMON:
            continue
        out.add(s)
    return out


def parent_word_similarity(child: dict, parent: dict) -> float:
    a, b = closeness_tokens(child), closeness_tokens(parent)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def parent_industry_overlap(child: dict, parent: dict, industry_by_ticker: dict) -> float:
    c_ind = [industry_by_ticker.get(tk) for tk in (child.get("tickers") or [])]
    c_ind = [i for i in c_ind if i]
    if not c_ind:
        return 0.0
    p_ind = {industry_by_ticker.get(tk) for tk in (parent.get("tickers") or [])} - {None, ""}
    return sum(1 for i in c_ind if i in p_ind) / len(c_ind)
