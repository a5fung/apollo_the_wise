"""His grades on breakout v1's nightly list (#717), read on chart sheets shown in chat — his 2026-11-05
ruling ("the scoring we do for pattern is much better when you show me the chart"), not Telegram /bgrade.

Each sheet: names drawn at random from one list night, stratified by list rank; the chart ends on the list
night, the dashed line is the name's level (the highest high of the last 5 sessions). He sees no ticker, rank
or score. Keyed on (ticker, list_date). `grade` normalises his words: good / ok (incl. "okish") / no (incl.
"looks extended") / conditional ("depends how far it breaks out"). His words are kept verbatim.

These are DETECTION labels (is this a real breakout setup?), never a returns verdict.
"""
from dataclasses import dataclass

GRADES_ALLOWED = frozenset({"good", "ok", "no", "conditional"})


@dataclass(frozen=True)
class BreakoutGrade:
    list_date: str
    ticker: str
    sheet_card: str
    list_rank: int
    order_score: float
    level: float
    grade: str
    operator_words: str
    sheet: str


_SHEET_1106 = "scripts/probes/_717_grading_sheet_1107/breakout_sheet_1106.png"   # graded 2026-11-07, 12 of 184

BREAKOUT_LIST_GRADES: list[BreakoutGrade] = [
    BreakoutGrade("2026-11-06", "IAG", "A", 145, 0.326, 18.79, "good", "good", _SHEET_1106),
    BreakoutGrade("2026-11-06", "SIG", "B", 73, 0.568, 129.26, "no", "looks extended", _SHEET_1106),
    BreakoutGrade("2026-11-06", "VFC", "C", 134, 0.367, 21.22, "no", "looks extended", _SHEET_1106),
    BreakoutGrade("2026-11-06", "PAYS", "D", 5, 0.916, 15.88, "good", "good", _SHEET_1106),
    BreakoutGrade("2026-11-06", "APPN", "E", 14, 0.821, 56.38, "ok", "okish", _SHEET_1106),
    BreakoutGrade("2026-11-06", "HAE", "F", 17, 0.815, 132.0, "ok", "okish", _SHEET_1106),
    BreakoutGrade("2026-11-06", "PAY", "G", 30, 0.75, 35.26, "conditional", "depends how far it breaks out", _SHEET_1106),
    BreakoutGrade("2026-11-06", "FNKO", "H", 21, 0.793, 6.76, "ok", "ok", _SHEET_1106),
    BreakoutGrade("2026-11-06", "PAR", "I", 152, 0.299, 21.05, "good", "good", _SHEET_1106),
    BreakoutGrade("2026-11-06", "RSKD", "J", 41, 0.668, 8.98, "good", "good", _SHEET_1106),
    BreakoutGrade("2026-11-06", "PLSE", "K", 11, 0.867, 58.17, "good", "good", _SHEET_1106),
    BreakoutGrade("2026-11-06", "BHC", "L", 174, 0.177, 8.46, "ok", "ok", _SHEET_1106),
]
