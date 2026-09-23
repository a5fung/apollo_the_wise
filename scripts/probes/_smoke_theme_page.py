"""Render smoke of Apollo Themes (native-theme version): imports + both views
render without exception + grid keeps drill links. (Can't test the light/dark
flip here — that's Streamlit's native theme, not settable in AppTest.)"""
import sys
APP = r"C:\Users\lasto\Documents\portfolio-app2"
sys.path.insert(0, APP)
import app_theme, theme_palette, theme_grid, theme_detail  # noqa: F401,E401
print("IMPORTS OK · is_dark default:", app_theme.is_dark())
from streamlit.testing.v1 import AppTest
PAGE = APP + r"\pages\Apollo_Themes.py"


def run(view):
    at = AppTest.from_file(PAGE, default_timeout=60)
    at.session_state["view"] = view
    at.run()
    if at.exception:
        print(f"[{view}] EXC:", [(e.type, e.message) for e in at.exception])
        return None
    md = " ".join(m.value for m in at.markdown)
    print(f"[{view}] OK · dataframes={len(at.dataframe)} · drill={'?drill=' in md} · errors={[e.value for e in at.error]}")
    return md


g = run("Grid")
d = run("Detail")
ok = g is not None and d is not None and "?drill=" in (g or "")
print("RENDER SMOKE:", "PASS" if ok else "FAIL")
