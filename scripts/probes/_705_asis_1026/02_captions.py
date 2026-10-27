#!/usr/bin/env python3
"""#705 as-is read, STEP 6a, MACHINE PASS: his own trade statements in the stream captions, the market-wide ticker search, the reader sheets and
the agreement score (docs/analysis/cb_asis_reconstruction_prereg_2026-10-26.md §4.1 steps 1-3 and 6, §10, §13). RULE-FREE BY CONSTRUCTION: no
rule, setup name, pattern label or rule-library level enters; nothing is imported from the four rule folders.

THE OPERATOR'S PRINCIPLE (2026-10-26): "stop trying to pigeon hole his trades ... reverse eng his trades as they are, not as we want them to
be and fit into our rules." His note the same day: "from my understanding he doesn't buy premarket" (regular-session buys only; this module
reads captions and never a price).

WHAT IT DOES
  streams      the inventory's loader (495 caption files, 485 unique streams after its duplicate-upload drop) with the stream date corrected from
               the title of a 'Late upload' video; a late upload that is the same stream as another (same corrected date and length) is dropped.
  statements   the inventory's regex and clustering, WIDENED by two kinds the inventory lacks (`shorted`, `covered`); the original nine-kind
               extraction is re-run first and every inventory number is a CLAIM on it; the widened counts stand beside it.
  search set   per stream date, every symbol the lexicon carries whose bar-file span covers the date (either export), the panel symbols whose
               alias target is live that date (FB -> META), and the funds / notes / delisted names we hold no bars for (`NO_BARS_SYMBOLS`).
               NOT limited to the names on his screen (review F3): the holdings windows play no part in the search or the alias list.
  aliases      a caption word within +-30 s of a trade statement that is no English word, is 1 or 2 edits from a live symbol and has ONE nearest
               live symbol is an alias; the stretch it was heard in is listed. Accepted on caption evidence only, never because the stock was on
               his screen and never from the bars.
  hand-read    a (non-account) statement with a search-set symbol or alias within +-30 s of it; the price tier = a price-shaped number within 12
               words of the statement. A seeded sample (rng_for) of 200 statements with NO symbol within +-30 s is drawn for the blind reader.
  sheets       the T1 (price) batch FIRST as its own sheet, then the rest in batches, each row carrying +-30 s of caption text and the label
               columns of captions.md; the readers see captions ONLY: no holdings window, no bar, no price of ours, no machine ticker hint (F13).
  join         symbol + day only, never the action and never a price: the NEAREST window of EITHER side whose span contains the day or lies
               within one session of it. In this stage the only day is the stream date, so the joins printed here are PROVISIONAL.
  agreement    reader 1 vs the blind reader 2: >= 80% on the joint label (ticker, action, day class), >= 85% on the price number where both
               read one; the disagreements listed. (Step 6b, the checks, is 03_check.py and is not here.)

STAGES  --dry-run    loads the captions, the lexicon, the dictionary and the windows; prints the claims, counts by kind and year, the alias list,
                     the hand-read set and tier sizes against the inventory's yield, the filter's recall on the inventory's 120 hand-read rows,
                     the provisional joins and the sheet sizes -> 02_captions_dryrun.txt, ending 'DRY RUN COMPLETE' after a RESULT line
                     '<n> claims, <k> OK, <j> MISMATCH'. Writes no sheet.
        --sheets     GATED (R59). Writes the reader sheets, machine_statements.tsv, sheet_manifest.tsv, aliases.tsv and joins.tsv under
                     apollo_data/cb702/qm_streams/asis_1026/ (sheets/ for the sheets only) -> 02_captions.txt + step6a_* ledger rows.
                     Refuses to overwrite a sheet that already carries a label.
        --print-pins every pin step 6a rests on -> 02_captions_pins.txt (for pasting below the doc's freeze marker).
        --agreement  scores two filled sheets: --r1 FILE [FILE ...] --r2 FILE [--nosymbol FILE] -> 02_agreement.txt.

READINGS where the plan is silent, ambiguous or contradicts itself (numbered on from 01_points.py's R1-R39 (R59-R61 are review fixes); the main loop decides):
  R40 [the alias rule contradicts its own examples] The plan's rule is "a caption word ... that is no English word"; its examples (cash, gosh,
      tweaks, tricks, twigs) ARE English words. The rule is applied as written (stricter): an English word is never an alias. The 1-edit
      candidates the English test excluded are printed beside it (a readout, not acted on) with the plan's examples looked up one by one.
  R41 [what "no English word" means; the classes] A word is English when it is in /usr/share/dict/{web2,web2a,connectives} (their sha256
      printed), or is one of those words plus -s / -es / -ed / -d / -ing / -er / -est / -ly (the 1934 dictionary has no inflected forms and no
      'has', 'is', 'was'; the connectives list carries the function words), or is a spoken filler (`FILLERS`: uh, gonna, okay ...). The word
      lists are a parameter of every function (tests pass fixtures; CI has no /usr/share). A word is CLASSED, never silently dropped: 'common'
      (a connective, a filler, or a dictionary word said in at least half of the streams - play, best, good: ordinary speech, never a ticker
      mention), 'dict' (any other dictionary word: RIOT, BOIL, SPY, ZOOM, CODX's 'codex'), 'other' (no dictionary word). An EXACT symbol hit is
      'strong' (not a dictionary word) or 'weak' (a dictionary-word symbol, 'weak_near' when within 12 words of the statement). The first draft
      used the 1,000 most frequent tokens as 'common' and it swallowed riot, codex and shop (rank 636-855; document frequency 15-28%): the
      line is DOCUMENT frequency, 50%, the one place a number was moved (before any sheet was drawn, shown in the dry run).
  R42 [alias targets] An alias must (a) start with the same letter as its symbol, (b) be at least 3 letters, (c) be 1 edit away when it has 3-5
      letters and 1-2 edits when it has 6 or more (adjacent swaps count 1), (d) point to ONE live symbol at the minimum distance, or, on a
      tie, to the ONE tied candidate that is not a dictionary word and was heard at least 3 times as a literal caption token (caption
      evidence only: 'tqq' is 1 edit from TQQQ, THQ, TMQ, TRQ, TSQ; TQQQ is said 52 times, so it wins; 'twix' -> TVIX over TWIN the same way),
      else the word is `ambiguous` (listed with its candidates; class 'amb', stratum S3), (e) not itself be a symbol of the lexicon on any
      date (a delisted symbol said aloud is not re-aimed at a live neighbour), and the target is never a 'common' word. A two-letter garble
      (the plan's 'tq' for TQQQ) is therefore not recovered. WITHOUT the evidence tie-break nothing of the plan's examples resolves (the live
      set is 8,000-12,000 symbols, dense at 4 letters): the tie-break is mine and it is caption-only, but the plan did not write it.
  R43 [company names] Spoken company names are NOT turned into tickers (no name table: "from the captions alone"). The top non-dictionary words
      within +-30 s of a statement that match no live symbol are printed (shopify, draftkings, bitcoin, livongo ...): the size of that blind spot,
      which the 200-statement blind sample measures. The dictionary-word company names (codex, kodak, billy, space ...) that R40 keeps out of
      the alias list are printed beside.
  R44 [no-bars table; review F7, stricter] `NO_BARS_SYMBOLS` = GBTC, ETHE, FNGU, TVIX, the plan's four funds and notes, always in the search set,
      printed. The first build also carried TCAC, VTIQ, FSR, NXTD (the delisted names data.md §3.2 lists FOR HIS WINDOWS); those four are OUT
      now: they came from his panel, so a held no-bars name was searchable and an unheld one was not (the review found 33 hand-read statements
      in the set only through those names). The 200-statement blind sample measures what this leaves out. 'NO' is not added. DISCLOSED EXCEPTION:
      GSX / SBE still enter through the rename table of asis_common (`extend_alias_renames`, built for his panel symbols; 72 S1 hits for GSX
      alone) because that table is step 5's pinned code; a held renamed name is searchable and an unheld one is not.
  R45 [kinds] `shorted` and `covered` sit right after `stopped` in the naming priority (so "bought it back" names as covered; "stopped out of my
      short" stays stopped). Excluded by the patterns: covered call(s), short term, short squeeze, short interest, "short on ...", the noun "a short".
      The engine is a PARAMETERISED COPY of the inventory's find_matches / cluster (the originals read module globals and raise on a kind not in
      their priority list); a test shows the copy, given the inventory's patterns, returns the inventory's statements exactly.
  R46 [the claims are on the original extraction] 9,474 / 7,607 and the per-kind table are claims on the ORIGINAL nine-kind engine; the widened
      counts and the statements that MERGED (a new match bridged two old ones, or moved a cluster start so its tail split off) stand beside it.
      Old and widened statements are matched by word-span OVERLAP, never by an exact first-word index.
  R47 ['account' statements] The 'account' kind (my account, year to date, up/down N this year) is counted and printed but is not put in the hand-
      read set or the blind pool: those are account-level statements, already extracted by hand (133 in account_statements.tsv, section 4.3).
  R48 [stream dates] Claims stay on the inventory's frame (UPLOAD year). The stream date is the upload date, except a 'Late upload' title:
      month + day from the title, the nearest such date on or before the upload (Dec 31 stream, uploaded 2021-01-05 -> 2020-12-31); the title's
      weekday is checked against it and a mismatch printed. 'This is yesterdays video' (2020-10-06) is CORRECTED to the previous weekday of its
      upload (2020-10-05; review F11, stricter: left at its upload date it sat one session late for the readers' day labels and the day-offset
      histogram), noted `yesterdays_video`, and is not counted among the 8 late uploads.
      Two videos with the same corrected date and length, one a late upload, are one stream (ytWg3aGNc10 repeats DNSJux1yiOI under another
      title): the later upload is dropped, printed; claims are made before this drop.
  R49 [the price tier] A statement is a price candidate when its neighbourhood (12 words before the first and after the last matched word, the
      inventory's snippet window) holds: a '$' number, a decimal, "and a half / quarter", "at <number>" (not a clock time), "in the <490s /
      forties>", or a number followed by dollars / bucks / cents. A candidate is a reading aid for the sheet order, not a label.
  R50 [sheets] The label columns are captions.md's plus `side`, `shares`, `dollar_result`, `price_kind` (fill / level) and the widened action
      list. The machine's ticker or alias hit is NOT on the sheet: the reader resolves the ticker from the words alone (03 can then measure
      reader-vs-machine ticker agreement). Review F10: sheet names and row ids are NEUTRAL (reader1_rest_b01.., B0001..); the stratum of a
      batch lives in `sheet_manifest.tsv` and `machine_statements.tsv` (outside sheets/), never on the page or in a file name. Draws use rng_for with a named key and a sorted pool (guard 7), never random.Random.
  R51 [tiers] T2 / T3 are the readers' day labels; the machine tiers are 'price candidate' and 'rest'. The T2 / T3 sizes printed are a PROJECTION
      of the inventory's yield on the hand-read set, labelled so.
  R52 [the join] On the panel symbol (`sym`, what he would say) only; the rename table of asis_common is not applied to his words. The join
      function takes (symbol, day) and nothing else: a test calls it with a sale and a purchase, with and without a price, and gets the same
      window; the function body names neither (a source-text pin, reviewed).
  R53 [the window] The +-30 s of caption context is measured from the first matched word to the last matched word of the statement (the
      inventory's `context_text`), for the sheet AND for the symbol filter, so the reader sees exactly the stretch the filter used.
  R54 [spelled letters] Letters said one at a time ("t s l a") are not joined into a symbol. Single-letter and numeric-only tokens are not symbol
      mentions.
  R55 [the plan's filter, in strata; review F6] The plan's filter is "a search-set symbol or alias within +-30 s": taken literally with the
      dictionary-word symbols it is the hand-read set S1-S4 below, which admits ~85% of all non-account in-span statements (it barely filters:
      ~890 ordinary-word symbols count as mentions), whose size (about 7,200) is 3x the plan's 1,500-2,500. Its recall on the inventory's
      usable rows rests on 1-3 rows per cell: the dry run prints the counts with 95% Wilson ranges, and the ranges of S1-S3 and S1-S4
      overlap, so no cut is shown to be "under 10% dropped" at this sample size (the full cut's anydate figure is also 4.7% once the one
      `account` row, dropped by every cut by design, is set aside). So the strata are kept on the page and in the sheet names, so the main loop
      can stop reading at a stratum: S1 = a strong symbol or a resolved garble; S2 = a dictionary-word symbol within 12 words of the statement;
      S3 = a garble with tied candidates (one word, 'tesla', is 376 of them); S4 = a dictionary-word symbol 13+ words away. The price-candidate
      sheet (T1) is cut from the WHOLE set, which is what puts it in the plan's 300-600 band; the rest are batched by stratum.
  R56 [the join's symbols] The provisional join reads the precise symbols only (S1 + S2 classes: strong, alias, weak_near); a tied garble's
      candidates and the far dictionary-word symbols are not joined.
  R57 [agreement] The joint label is (ticker, action, day class): a ticker only when the reader marked it identified, 'unidentified' otherwise on
      both sides; a row that is not his own trade is ONE label whatever the reason (advice / plan / viewer / other); rows either reader left
      unlabelled are set aside and listed, never scored. The price number agrees when the two numbers are equal to the cent (42.5 = 42.50)
      among rows where both stated a price; garbled flags are printed, not scored. The blind sample's estimate is the share of its labelled rows
      that are his own trade EVENT (buy, add, sell, stopped, shorted, covered), with a Wilson range.
  R58 [what the dry run does not write] No sheet, no ledger row and no pin: the main loop pins `02_captions.py`, the dictionary files and the
      dry-run printout below the freeze marker (`--print-pins` lists them all, 02_captions_pins.txt). The printout prints the input shas it was
      made from. `machine_statements.tsv` (the symbol hits and the stratum) and `sheet_manifest.tsv` are written to the output folder, NOT to
      sheets/, so a reader card pointed at sheets/ cannot see a machine hint.
  R59 [the sheets gate; review F1] `--sheets` REFUSES (exit 3, 02_captions.refused.txt) like 01_points `--run` (R34): the step-6a dry run
      complete with 0 MISMATCH; its `- modules:` line equal to the code on disk (that line now carries 01_points.py: load_windows executes its
      read_frames / read_windows, so an edit there changes the joins); every pin (step 5's inputs and modules, this module, the inventory's
      inputs, the word lists, the dry-run printout, the doc body) below the freeze marker; the ledger verifying; no sheet or side file present.
      After writing, the dry run, the run printout and the four side files get `step6a_*` ledger rows (the sheets themselves do not: the readers
      label them; the manifest records their shas at the draw).
  R60 [ties and `none` in the join; review F2, F3] A tied join (`ambiguous`) writes BLANK eid and side and lists the tied windows in `tied`
      (a sort handed every tie to 'buy'; 480 of the first build's 623 ties were ONE position's buy and sale on the same session, so a sale said
      on a day-trade day would have scored as a miss on R5). A `none` carries a reason: `inside_hold` (the day lies between a position's first
      and last window: a trade said mid-hold, which the panel cannot show as a window, is HELD, not invisible), `other_date` (held, another
      date), `not_on_panel` (never on his panel: includes false aliases). 03 counts the invisible trades from the last two only.
  R61 [the price bar; review F8] No row where both readers read a price is NOT a pass: the report says the bar is not testable and the exit
      code is 1. A count under 10 is noted, not a bar (the plan sets no minimum).

No network, no model client, no DB, no subagent. Nothing is opened at import.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import hashlib
import importlib.util
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date as _date, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_module(name: str, path: str):
    if name in sys.modules and getattr(sys.modules[name], "__file__", "") == path:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load_module("asis_common", os.path.join(HERE, "asis_common.py"))
INV = _load_module("captions_inventory", os.path.join(HERE, "inventory", "captions_inventory.py"))   # imports the standard library only

# ---- paths / constants ----------------------------------------------------------------------------------------------------------------
P_DRY = os.path.join(HERE, "02_captions_dryrun.txt")
P_RUN = os.path.join(HERE, "02_captions.txt")
P_AGREE = os.path.join(HERE, "02_agreement.txt")
P_PINS = os.path.join(HERE, "02_captions_pins.txt")
P_REFUSED = os.path.join(HERE, "02_captions.refused.txt")   # a refused --sheets writes here, never P_RUN
SHEETS_DIR = os.path.join(C.OUT_DIR, "sheets")
OUT_FILES = {k: os.path.join(C.OUT_DIR, f"{k}.tsv") for k in ("aliases", "joins", "machine_statements", "sheet_manifest")}
DICT_FILES = ("/usr/share/dict/web2", "/usr/share/dict/web2a", "/usr/share/dict/connectives")      # R41
SPAN = ("2020-01-01", "2022-06-30")                      # the primary span (the stream date), as 01_points
FRAME_YEARS = INV.FRAME_YEARS                            # the inventory's claim frame (UPLOAD year)
CONTEXT_S = 30.0                                         # +- seconds of caption context (the inventory's)
NEIGHBOUR_WORDS = 12                                     # the inventory's snippet window, the price tier's reach (R49)
COMMON_DF = 0.50                                         # R41: a dictionary word said in half of the streams is ordinary speech, never a ticker mention
ATTEST_MIN = 3                                           # R42: a tied alias target heard this often as a literal caption token is "attested"
STRATA = (("S1", ("strong", "alias")), ("S2", ("weak_near",)), ("S3", ("amb",)), ("S4", ("weak",)))     # R55: the hit classes, strongest first
FILTER_CLASSES = tuple(c for _, cl in STRATA for c in cl)  # the plan's literal filter: ANY search-set symbol or alias within +-30 s
JOIN_CLASSES = ("strong", "alias", "weak_near")          # the provisional join reads the precise symbols only
NO_BARS_SYMBOLS = ("GBTC", "ETHE", "FNGU", "TVIX")      # R44 (the plan's four funds and notes only; review F7)
FILLERS = frozenset("uh um uhm hmm mhm mm mmm okay ok gonna gotta wanna kinda sorta nah yeah yep yup nope alright whatever lemme gimme dunno "
                    "cuz cause".split())
BATCH_ROWS = 500
READER2_PRICE, READER2_REST, NOSYMBOL_N = 100, 50, 200
AGREE_JOINT_BAR, AGREE_PRICE_BAR = 0.80, 0.85
SMALL_PRICE_N = 10                                       # review F8: a printed note only (the plan sets no minimum), never a bar

# the original kinds, in the inventory's order, and the two widened ones (R45)
OLD_PRIORITY = tuple(INV.KIND_PRIORITY)
WIDE_PRIORITY = ("stopped", "covered", "shorted", "sold_part", "sold", "added", "bought", "buy_now", "profit", "cost_stop", "account")
SHORT_PATTERNS = {
    "shorted": [
        r"\b(?:i|we|i've|ive|i'd)\s+(?:\w+\s+){0,2}?shorted\b",
        r"\bshorted\s+(?:it|this|that|them|these|some|more|a|the|here|at|in|on|before|after|back|\d)\b",
        r"\bi'?m\s+(?:\w+\s+)?short\b(?!\s+(?:term|squeeze|interest|on|of|sale|seller|sellers|selling|volume))",
        r"\bwent\s+short\b",
        r"\bshort\s+it\b",
    ],
    "covered": [
        r"\b(?:i|we|i've|ive)\s+(?:\w+\s+){0,2}?covered\b(?!\s+calls?)",
        r"\bcovered\s+(?:it|my|the|all|some|half|here|at|part|\d)\b",
        r"\bi'?m\s+out\s+of\s+(?:my|the|this|that)\s+short\b",
        r"\bbought\s+(?:it\s+|them\s+)?back\b",
    ],
}
WIDE_PATTERNS = {**INV.PATTERNS, **SHORT_PATTERNS}
OLD_COMPILED = {k: [re.compile(p) for p in v] for k, v in INV.PATTERNS.items()}
WIDE_COMPILED = {k: [re.compile(p) for p in v] for k, v in WIDE_PATTERNS.items()}

# the price tier (R49) and the other machine flags (reading aids for the sheet order and the tier sizes; never labels)
_NUMW = INV.NUMW
PRICE_RES = [re.compile(p) for p in (
    r"\$\s?\d",
    r"\b\d+\.\d+\b",
    r"\band\s+a\s+(?:half|quarter)\b|\bthree\s+quarters\b",
    r"\bat\s+(?:\$?\d[\d.,]*|(?:%s))\b(?!\s*(?:am|pm|o'clock|minutes?|mins?|seconds?|percent|%%|shares|k\b))" % _NUMW,
    r"\bin\s+the\s+(?:\d{2,4}s|twenties|thirties|forties|fifties|sixties|seventies|eighties|nineties|hundreds)\b",
    r"\b(?:\d+(?:\.\d+)?|(?:%s)(?:[\s-]+(?:%s))*)\s+(?:dollars|bucks|cents)\b" % (_NUMW, _NUMW),
)]
SHARES_RE = re.compile(r"\b(?:%s)\s*(?:thousand\s+|k\s+|hundred\s+)?shares?\b" % INV.NUM)
RESULT_RE = re.compile(r"\b(?:lost|made|gained|lose|losing|profit|loss|up|down)\b(?:\s+\w+){0,4}?\s+(?:\$?\d[\d.,]*|(?:%s))\s*(?:k|m|thousand|million|grand)\b" % _NUMW)
DAY_RE = re.compile(r"\b(?:today|yesterday|this\s+morning|pre\s*market|at\s+the\s+open|last\s+night|monday|tuesday|wednesday|thursday|friday|"
                    r"last\s+week|days?\s+ago|a\s+week\s+ago|earlier\s+(?:today|this))\b")

MONTHS = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
          "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11,
          "november": 11, "dec": 12, "december": 12}
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# the inventory's measured facts (captions.md / data.md): the dry run's claims
CLAIMS_TABLE = {"stopped": 1829, "sold_part": 221, "sold": 1165, "added": 433, "bought": 1977, "buy_now": 462, "profit": 29, "cost_stop": 901,
                "account": 590}

# the hand-labelled sample's columns (captions.md) and the sheet layout (R50)
SHEET_DATA_COLS = ["sid", "stmt_id", "video", "stream_date", "upload_date", "t_hms", "kind", "kinds_in_cluster", "matched", "snippet",
                   "price_candidate", "context"]
SHEET_LABEL_COLS = ["ticker_ident", "ticker", "ticker_inferred", "his_trade", "action", "side", "date_pinnable", "price_stated", "price_value",
                    "price_garbled", "price_kind", "shares", "dollar_result", "note"]
SHEET_COLS = SHEET_DATA_COLS + SHEET_LABEL_COLS
SHEET_BANNED_STEMS = ("eid", "window", "bracket", "panel", "range", "join", "alias", "hint", "hits", "symbol", "sym_", "position", "bar_", "raw")
ACTIONS = ("buy", "add", "sell_part", "sell_all", "sell_unspec", "stopped", "shorted", "covered", "holding", "stop_level", "result", "none")
DAY_CLASSES = ("stream_day", "stated_earlier", "implied_recent", "approx_earlier", "unstated")


class GuardStop(C.GuardStop):
    pass


class Say:
    def __init__(self):
        self.lines = []

    def __call__(self, msg: str = "") -> None:
        print(msg, flush=True)
        self.lines.append(msg)

    def write(self, path: str) -> None:
        with open(path + ".partial", "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.lines) + "\n")
        os.replace(path + ".partial", path)


def pct(a, b) -> str:
    return f"{100.0 * a / b:.1f}%" if b else "n/a"


def table(say, hdr: list, rows: list) -> None:
    w = [max(len(str(x)) for x in col) for col in zip(hdr, *rows)] if rows else [len(h) for h in hdr]
    say("  " + "  ".join(str(h).ljust(w[k]) for k, h in enumerate(hdr)))
    for r in rows:
        say("  " + "  ".join(str(x).ljust(w[k]) for k, x in enumerate(r)))


class Claims:
    """The dry run's checks against the inventory: every one printed; the RESULT line counts OK / MISMATCH (never tuned)."""

    def __init__(self, say):
        self.say, self.rows = say, []

    def __call__(self, label: str, expected, got) -> None:
        ok = expected == got
        self.rows.append((label, expected, got, ok))
        self.say(f"  [{'OK' if ok else 'MISMATCH'}] {label}: expected {expected}, got {got}")

    def result(self) -> str:
        n, k = len(self.rows), sum(1 for r in self.rows if r[3])
        return f"RESULT: {n} claims, {k} OK, {n - k} MISMATCH"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# words: what counts as an English word (R41)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_wordlists(paths=DICT_FILES) -> tuple:
    """-> (dictionary words, connectives, {path: sha16}); every list lower-cased, alphabetic words only. A missing file is an error."""
    words, conn, shas = set(), set(), {}
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as fh:
            ws = {ln.strip().lower() for ln in fh if ln.strip()}
        ws = {w for w in ws if w.isalpha()}
        (conn if p.endswith("connectives") else words).update(ws)
        shas[p] = C.sha(p)[:16]
    return frozenset(words), frozenset(conn), shas


class Words:
    """`klass(w)`: 'common' (never a ticker mention), 'dict' (a dictionary word rarer than the top tokens), 'other' (no English word)."""

    def __init__(self, dictionary, connectives=(), common=(), fillers=FILLERS):
        self.dictionary, self.connectives, self.common, self.fillers = frozenset(dictionary), frozenset(connectives), frozenset(common), frozenset(fillers)
        self._cache = {}

    def is_dictionary(self, w: str) -> bool:
        if not w.isalpha():
            return False
        if w in self.dictionary or w in self.connectives:
            return True
        d = self.dictionary
        for suf in ("s", "es", "ed", "d", "ing", "er", "est", "ly"):
            if w.endswith(suf) and len(w) - len(suf) >= 2:
                st = w[:-len(suf)]
                if st in d:
                    return True
                if suf == "ing" and (st + "e") in d:
                    return True
                if suf in ("ed", "ing", "er", "est") and len(st) >= 3 and st[-1] == st[-2] and st[:-1] in d:
                    return True
        if w.endswith("ies") and (w[:-3] + "y") in d:
            return True
        return False

    def klass(self, w: str) -> str:
        k = self._cache.get(w)
        if k is None:
            if not w.isalpha():
                k = "other"
            elif w in self.fillers or w in self.connectives:
                k = "common"
            elif self.is_dictionary(w):
                k = "common" if w in self.common else "dict"
            else:
                k = "other"
            self._cache[w] = k
        return k


# ═════════════════════════════════════════════════════════════════════════════════════════════
# streams: the inventory's loader + the stream date (R48)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def finish_video(v) -> None:
    """The tail of `Video.load` for a video whose `toks` / `times` were set directly (the inventory's, line for line)."""
    v.starts, parts, pos = [], [], 0
    for n in v.toks:
        v.starts.append(pos)
        parts.append(n)
        pos += len(n) + 1
    v.text = " ".join(parts)


def iso(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"


def title_stream_date(title: str, upload_iso: str) -> tuple:
    """-> (stream date ISO, note). 'Late upload' titles carry the earlier stream date (month + day, the nearest such date on or before the
    upload); every other title keeps the upload date. The note is '' / 'weekday_mismatch:<name>' / 'no_date_in_title'."""
    t = title.lower()
    if re.search(r"yesterday'?s\s+video", t) and "late upload" not in t:       # R48 (review F11): the previous weekday of the upload
        d = _date.fromisoformat(upload_iso) - timedelta(days=1)
        while d.weekday() > 4:
            d -= timedelta(days=1)
        return d.isoformat(), "yesterdays_video"
    if "late upload" not in t:
        return upload_iso, ""
    m = re.search(r"\b(%s)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b" % "|".join(sorted(MONTHS, key=len, reverse=True)), t)
    if not m:
        return upload_iso, "no_date_in_title"
    up = _date.fromisoformat(upload_iso)
    try:
        d = _date(up.year, MONTHS[m.group(1)], int(m.group(2)))
    except ValueError:
        return upload_iso, "no_date_in_title"
    if d > up:
        d = _date(up.year - 1, d.month, d.day)
    note = ""
    for k, name in enumerate(WEEKDAYS):
        if name in t and d.weekday() != k:
            note = f"weekday_mismatch:{name}"
    return d.isoformat(), note


@dataclass
class Stream:
    v: object
    upload: str
    stream_date: str
    late: bool
    note: str = ""


def make_streams(vids: list) -> tuple:
    """-> (streams, dropped): the corrected stream date per video; a late upload repeating another stream (same corrected date and length) is
    dropped, the later upload (R48)."""
    streams = []
    for v in vids:
        up = iso(v.date)
        sd, note = title_stream_date(v.title, up)
        C.seal_date(sd, "stream date")
        streams.append(Stream(v, up, sd, "late upload" in v.title.lower(), note))
    seen, keep, dropped = {}, [], []
    for s in sorted(streams, key=lambda s: (s.upload, s.v.id)):
        key = (s.stream_date, s.v.seconds)
        if key in seen and (s.late or seen[key].late):
            dropped.append((s, seen[key]))
            continue
        seen.setdefault(key, s)
        keep.append(s)
    return keep, dropped


# ═════════════════════════════════════════════════════════════════════════════════════════════
# statements: a parameterised copy of the inventory's find_matches / cluster (R45)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def find_matches_with(v, compiled: dict, priority: tuple) -> list:
    """-> [(kind, w_start, w_end, matched_text)] with same-kind repeats collapsed (the inventory's, over the given patterns)."""
    out = []
    for kind, pats in compiled.items():
        raw = []
        for p in pats:
            for m in p.finditer(v.text):
                raw.append((v.widx(m.start()), v.widx(max(m.end() - 1, m.start())), m.group(0)))
        raw.sort()
        last_end = -10 ** 9
        for ws, we, txt in raw:
            if ws - last_end < INV.SAME_KIND_GAP:
                last_end = max(last_end, we)
                continue
            out.append((kind, ws, we, txt))
            last_end = we
    out.sort(key=lambda x: (x[1], priority.index(x[0])))
    return out


def cluster_with(v, matches: list, priority: tuple) -> list:
    """Merge nearby matches (any kind) into one statement named by its highest-priority kind (the inventory's, over the given priority)."""
    stmts, cur = [], None
    for kind, ws, we, txt in matches:
        if cur and ws - cur["end"] <= INV.CLUSTER_GAP and ws - cur["start"] <= INV.CLUSTER_MAX:
            cur["end"] = max(cur["end"], we)
            cur["kinds"].add(kind)
            cur["texts"].append(txt)
        else:
            cur = {"start": ws, "end": we, "kinds": {kind}, "texts": [txt]}
            stmts.append(cur)
    res = []
    for s in stmts:
        kind = min(s["kinds"], key=priority.index)
        res.append({
            "video": v.id, "date": v.date, "title": v.title,
            "t": v.times[s["start"]], "w0": s["start"], "w1": s["end"],
            "kind": kind, "kinds_in_cluster": "+".join(sorted(s["kinds"], key=priority.index)),
            "matched": " | ".join(s["texts"])[:160],
            "snippet": " ".join(v.toks[max(0, s["start"] - 12): s["end"] + 13]),
        })
    return res


def old_statements(v) -> list:
    return cluster_with(v, find_matches_with(v, OLD_COMPILED, OLD_PRIORITY), OLD_PRIORITY)


def wide_statements(v) -> list:
    return cluster_with(v, find_matches_with(v, WIDE_COMPILED, WIDE_PRIORITY), WIDE_PRIORITY)


def overlaps(a: dict, b: dict) -> bool:
    return a["video"] == b["video"] and a["w0"] <= b["w1"] and b["w0"] <= a["w1"]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the search set and the aliases (R41, R42, R44)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def skey(sym: str) -> str:
    return re.sub(r"[^a-z0-9]", "", sym.lower())


def osa(a: str, b: str, limit: int) -> int:
    """Optimal-string-alignment distance (an adjacent swap counts 1), or limit + 1 once it must exceed `limit`."""
    la, lb = len(a), len(b)
    if abs(la - lb) > limit:
        return limit + 1
    prev2, prev = None, list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        best = cur[0]
        for j in range(1, lb + 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if a[i - 1] == b[j - 1] else 1))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                v = min(v, prev2[j - 2] + 1)
            cur[j] = v
            best = min(best, v)
        if best > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[lb]


def deletes(s: str, k: int) -> set:
    out, level = {s}, {s}
    for _ in range(k):
        nxt = set()
        for x in level:
            for i in range(len(x)):
                nxt.add(x[:i] + x[i + 1:])
        out |= nxt
        level = nxt
    return out


def alias_limit(n: int) -> int:
    """R42: the edits a garble of n letters may be from its symbol."""
    return 0 if n < 3 else (1 if n <= 5 else 2)


def live_on(span, d: str) -> bool:
    a0, a1, b0, b1 = span
    return (a0 != "" and a0 <= d <= a1) or (b0 != "" and b0 <= d <= b1)


class SymbolIndex:
    """key (lower-cased alphanumerics of a symbol) -> its entries; `live_map(date)` = {key: (symbols, class)} of the keys that can be mentioned
    that date: the lexicon symbols whose span covers it, the panel symbols whose alias target is live, the no-bars names (always)."""

    def __init__(self, lex: dict, alias: dict, words: Words, no_bars=NO_BARS_SYMBOLS):
        self.lex, self.alias, self.words = lex, alias, words
        self.entries = collections.defaultdict(list)       # key -> [(symbol, span|None, target|None)]
        for sym, span in lex.items():
            k = skey(sym)
            if k:
                self.entries[k].append((sym, span, None))
        for sym in no_bars:
            self.entries[skey(sym)].append((sym, None, None))
        for panel, target in alias.items():
            if target in lex:
                self.entries[skey(panel)].append((panel, None, target))
        self.known = frozenset(self.entries)
        self._live = {}

    def klass(self, key: str) -> str:
        return self.words.klass(key)

    def live_map(self, d: str) -> dict:
        m = self._live.get(d)
        if m is None:
            C.seal_date(d, "search set")
            m = {}
            for k, ents in self.entries.items():
                if len(k) < 2 or k.isdigit():
                    continue
                syms = []
                for sym, span, target in ents:
                    if span is None and target is None:
                        ok = True
                    elif target is not None:
                        ok = live_on(self.lex[target], d)
                    else:
                        ok = live_on(span, d)
                    if ok and sym not in syms:
                        syms.append(sym)
                if not syms:
                    continue
                cls = self.klass(k)
                if cls == "common":
                    continue
                m[k] = (tuple(syms), "weak" if cls == "dict" else "strong")
            self._live[d] = m
        return m


class AliasResolver:
    """A caption word that is no English word, near a trade statement -> the ONE nearest live symbol within R42's edits, or 'ambiguous'."""

    def __init__(self, index: SymbolIndex, counts=None):
        self.index = index
        self.counts = counts if counts is not None else collections.Counter()
        self.targets = [k for k in index.known if len(k) >= 3 and k.isalpha() and index.klass(k) != "common"]
        self.del_idx = collections.defaultdict(list)
        for k in self.targets:
            for dk in deletes(k, 2):
                self.del_idx[dk].append(k)
        self._cand = {}
        self._res = {}

    def candidates(self, word: str, limit: int = None, same_first: bool = True) -> list:
        """[(key, distance)] sorted, over all dates."""
        lim = alias_limit(len(word)) if limit is None else limit
        ck = (word, lim, same_first)
        got = self._cand.get(ck)
        if got is None:
            got = []
            if lim:
                keys = set()
                for dk in deletes(word, lim):
                    keys.update(self.del_idx.get(dk, ()))
                for k in keys:
                    if k == word or (same_first and k[0] != word[0]):
                        continue
                    dist = osa(word, k, lim)
                    if dist <= lim:
                        got.append((k, dist))
                got.sort(key=lambda x: (x[1], x[0]))
            self._cand[ck] = got
        return got

    def resolve(self, word: str, d: str) -> tuple:
        """-> (status 'alias' | 'ambiguous' | 'none', symbol, distance, tied keys)."""
        ck = (word, d)
        got = self._res.get(ck)
        if got is None:
            if word in self.index.known:
                got = ("none", None, None, ())
            else:
                live = self.index.live_map(d)
                cand = [(k, dist) for k, dist in self.candidates(word) if k in live]
                if not cand:
                    got = ("none", None, None, ())
                else:
                    dmin = min(dist for _, dist in cand)
                    best = [k for k, dist in cand if dist == dmin]
                    attested = [k for k in best if live[k][1] == "strong" and self.counts[k] >= ATTEST_MIN]
                    if len(best) == 1 and len(live[best[0]][0]) == 1:
                        got = ("alias", live[best[0]][0][0], dmin, ())
                    elif len(attested) == 1 and len(live[attested[0]][0]) == 1:
                        got = ("alias", live[attested[0]][0][0], dmin, ())
                    else:
                        got = ("ambiguous", None, dmin, tuple(sorted(s for k in best for s in live[k][0])))
            self._res[ck] = got
        return got


# ═════════════════════════════════════════════════════════════════════════════════════════════
# per-stream annotation: hits within +-30 s, the flags, the tier
# ═════════════════════════════════════════════════════════════════════════════════════════════
def window_of(v, s: dict, pre: float = CONTEXT_S, post: float = CONTEXT_S) -> tuple:
    """R53: the token range [lo, hi) of the +-30 s of caption context around a statement."""
    return (bisect.bisect_left(v.times, s["t"] - pre), bisect.bisect_right(v.times, v.times[s["w1"]] + post))


def neighbourhood(v, s: dict) -> str:
    return " ".join(v.toks[max(0, s["w0"] - NEIGHBOUR_WORDS): s["w1"] + NEIGHBOUR_WORDS + 1])


def flags_of(text: str) -> dict:
    return {"price_candidate": any(r.search(text) for r in PRICE_RES), "day_words": bool(DAY_RE.search(text))}


@dataclass
class AliasLog:
    n: int = 0
    seen: set = field(default_factory=set)
    evidence: list = field(default_factory=list)


def annotate_stream(stream: Stream, stmts: list, index: SymbolIndex, resolver: AliasResolver, alias_log: dict, ambiguous_log: dict,
                    unmatched: collections.Counter, excluded_1edit: collections.Counter) -> None:
    """Adds to each statement dict: hits (list of (token, symbol, class, distance)), the flags. Aliases are only looked up for the words in the
    +-30 s of some statement. The logs collect the evidence (R42) and the readouts (R40, R43)."""
    v, sd = stream.v, stream.stream_date
    live = index.live_map(sd)
    exact = [(i, tk) for i, tk in enumerate(v.toks) if tk in live]
    exact_pos = [i for i, _ in exact]
    seen_alias = {}
    for s in stmts:
        lo, hi = window_of(v, s)
        hits = []
        j = bisect.bisect_left(exact_pos, lo)
        while j < len(exact) and exact[j][0] < hi:
            tk = exact[j][1]
            syms, cls = live[tk]
            if cls == "weak" and s["w0"] - NEIGHBOUR_WORDS <= exact[j][0] <= s["w1"] + NEIGHBOUR_WORDS:
                cls = "weak_near"
            for sym in syms:
                hits.append((tk, sym, cls, 0))
            j += 1
        for i in range(lo, hi):
            tk = v.toks[i]
            if tk in live or tk in index.known or len(tk) < 3 or not tk.isalpha() or index.words.klass(tk) != "other":
                continue
            r = seen_alias.get(tk) or resolver.resolve(tk, sd)
            seen_alias[tk] = r
            status, sym, dist, tied = r
            if status == "alias":
                hits.append((tk, sym, "alias", dist))
                log = alias_log.setdefault((tk, sym), AliasLog())
                if (v.id, i) not in log.seen:
                    log.n += 1
                    log.seen.add((v.id, i))
                    if len(log.evidence) < 3:
                        log.evidence.append(f"{v.id}@{INV.hms(v.times[i])}: " + " ".join(v.toks[max(0, i - 8): i + 9]))
            elif status == "ambiguous":
                ambiguous_log.setdefault(tk, set()).update(tied)
                hits.append((tk, ";".join(tied), "amb", dist))
            else:
                unmatched[tk] += 1
        s["hits"] = hits
        s["stream_date"] = sd
        s.update(flags_of(neighbourhood(v, s)))
        wide_txt = " ".join(v.toks[lo:hi])                     # the share count and the dollar result may sit anywhere in the +-30 s (T1b)
        s["shares"], s["dollar_result"] = bool(SHARES_RE.search(wide_txt)), bool(RESULT_RE.search(wide_txt))


def in_filter(s: dict, classes=FILTER_CLASSES) -> bool:
    return s["kind"] != "account" and any(h[2] in classes for h in s["hits"])


def stratum_of(s: dict) -> str:
    """R55: the strongest hit class of a statement: S1 strong / resolved garble, S2 dictionary-word symbol within 12 words, S3 garble with tied
    candidates, S4 dictionary-word symbol 13+ words away; '' when it has no hit."""
    have = {h[2] for h in s["hits"]}
    for name, cl in STRATA:
        if have & set(cl):
            return name
    return ""


def hit_symbols(s: dict, classes=JOIN_CLASSES) -> list:
    out = []
    for h in s["hits"]:
        if h[2] in classes:
            for sym in h[1].split(";"):
                if sym not in out:
                    out.append(sym)
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the join: symbol + day only (R52)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def index_windows(windows: list) -> dict:
    """{panel symbol: [(eid, side, lo, hi)]} over every window (a name with several positions keeps them all)."""
    out = collections.defaultdict(list)
    for w in windows:
        out[w[2]].append((w[0], w[1], w[3], w[4]))
    return out


def join_position(symbol: str, day: str, by_sym: dict, S) -> dict:
    """The NEAREST window of either side whose span contains `day` or lies within one session of it. A tie at the nearest distance is
    `ambiguous`; no window within a session is `none`. The statement's action and price are not arguments and are not read."""
    di = S.le(day)
    cands = []
    for eid, side, lo, hi in by_sym.get(symbol, ()):
        a, b = sorted((S.ge(lo), S.le(hi)))
        dist = 0 if a <= di <= b else (a - di if di < a else di - b)
        if dist <= 1:
            cands.append((dist, eid, side))
    if not cands:
        return {"status": "none", "eid": "", "side": "", "dist": "", "n": 0}
    cands.sort()
    best = [c for c in cands if c[0] == cands[0][0]]
    tied = ";".join(f"{e}:{sd}" for _, e, sd in best)
    if len(best) > 1:           # review F2: a tie names NO eid and NO side (sorting would always hand the tie to 'buy'); `tied` lists them
        return {"status": "ambiguous", "eid": "", "side": "", "dist": best[0][0], "n": len(cands), "tied": tied}
    return {"status": "unique", "eid": best[0][1], "side": best[0][2], "dist": best[0][0], "n": len(cands), "tied": tied}


def tie_is_one_position(j: dict) -> bool:
    """An `ambiguous` join whose tied windows all belong to ONE position (its buy and its sale on the same session: a day-trade day)."""
    return j["status"] == "ambiguous" and len({t.split(":")[0] for t in j["tied"].split(";")}) == 1


def index_holds(windows: list) -> dict:
    """{panel symbol: [(eid, first window's end, last window's start)]}: the stretch BETWEEN a position's first and last window (its hold), for
    every position with at least two windows. An open position with a buy window only has no hold here (stricter: nothing is called held)."""
    by = collections.defaultdict(list)
    for w in windows:
        by[(w[2], w[0])].append((w[3], w[4]))
    out = collections.defaultdict(list)
    for (sym, eid), ws in by.items():
        if len(ws) >= 2:
            ws = sorted(ws)
            out[sym].append((eid, ws[0][1], ws[-1][0]))
    return out


NONE_REASONS = ("inside_hold", "other_date", "not_on_panel")      # nearest-to-a-window first


def none_reason(symbol: str, day: str, by_sym: dict, holds: dict, S) -> str:
    """Why a `none` join found nothing (review F3): the day lies BETWEEN a position's first and last window (`inside_hold`: a trade said
    mid-hold, which the panel cannot show as a window, is not an invisible trade), the symbol is held on another date (`other_date`), or the
    symbol was never on his panel (`not_on_panel`)."""
    if symbol not in by_sym:
        return "not_on_panel"
    di = S.le(day)
    for _eid, end, start in holds.get(symbol, ()):
        if S.le(end) < di < S.ge(start):
            return "inside_hold"
    return "other_date"


def best_join(syms: list, day: str, by_sym: dict, holds: dict, S) -> dict:
    """The best-joined symbol of a statement (unique, then ambiguous, then none); a `none` carries its reason (the one nearest a window)."""
    rank = {"unique": 0, "ambiguous": 1, "none": 2}
    best = None
    for sym in syms:
        j = join_position(sym, day, by_sym, S)
        if j["status"] == "none":
            j["reason"] = none_reason(sym, day, by_sym, holds, S)
        else:
            j["reason"] = ""
        j["symbol"] = sym
        if best is None or (rank[j["status"]], NONE_REASONS.index(j["reason"]) if j["reason"] else 0) < (rank[best["status"]], NONE_REASONS.index(best["reason"]) if best["reason"] else 0):
            best = j
    return best


def load_windows(tally: collections.Counter = None) -> tuple:
    """-> (windows [(eid, side, sym, lo, hi)], Sessions): the step-5 windows (01_points' reader), not ranges.tsv, which only exists after the
    re-run; no bar, no minute and no export is opened."""
    P = _load_module("asis_points_for_captions", os.path.join(HERE, "01_points.py"))
    tally = tally if tally is not None else collections.Counter()
    S = C.sealed_sessions()
    frames = P.read_frames(C.FILES["snapshots"])
    buys, sales, _ = P.read_windows(frames, S, tally)
    return [(w.eid, w.side, w.sym, w.lo, w.hi) for w in buys + sales], S


# ═════════════════════════════════════════════════════════════════════════════════════════════
# sheets (R50): captions only
# ═════════════════════════════════════════════════════════════════════════════════════════════
def assert_sheet_columns(cols: list) -> None:
    """F13: the sheet carries no window, bar, price or machine hint of ours. Raises GuardStop on a column outside the layout or one whose name
    carries a banned stem (the label columns `price_*` are the reader's own readings of the words)."""
    for c in cols:
        if c not in SHEET_COLS:
            raise GuardStop(f"sheet column {c!r} is outside the layout")
    for c in SHEET_DATA_COLS:
        if c in cols and any(b in c for b in SHEET_BANNED_STEMS):
            raise GuardStop(f"sheet data column {c!r} carries a banned stem")


def sheet_row(sid: str, s: dict, v) -> dict:
    ctx = INV.context_text(v, s["t"], s["w0"], s["w1"]).replace("\n", " ")
    row = {"sid": sid, "stmt_id": s["stmt_id"], "video": s["video"], "stream_date": s["stream_date"], "upload_date": iso(s["date"]),
           "t_hms": INV.hms(s["t"]), "kind": s["kind"], "kinds_in_cluster": s["kinds_in_cluster"], "matched": s["matched"], "snippet": s["snippet"],
           "price_candidate": "Y" if s["price_candidate"] else "N", "context": ctx}
    row.update({c: "" for c in SHEET_LABEL_COLS})
    return row


def draw(pool: list, n: int, key: str) -> list:
    """n items of `pool` (sorted by stmt_id first) through rng_for(key); all of them when the pool is smaller."""
    pool = sorted(pool, key=lambda s: s["stmt_id"])
    if len(pool) <= n:
        return pool
    idx = sorted(C.rng_for(key).choice(len(pool), size=n, replace=False).tolist())
    return [pool[i] for i in idx]


def build_sheet_plan(handread: list, blind_pool: list, videos: dict) -> dict:
    """-> {sheet name: [row dicts]}. T1 (the price candidates of the whole set) first and alone; the rest by stratum (S1 .. S4) in batches of
    BATCH_ROWS in stream order (a batch never straddles two strata; the manifest says which stratum a batch is, the sheet does not); reader 2: 100 price candidates + 50 others, and the blind
    sample of 200, in a seeded shuffled order with their own ids."""
    order = lambda s: (s["stream_date"], s["video"], s["w0"])
    t1 = sorted([s for s in handread if s["price_candidate"]], key=order)
    rest = [s for s in handread if not s["price_candidate"]]
    plan = {"reader1_t1_price": [sheet_row(f"A{k + 1:04d}", s, videos[s["video"]]) for k, s in enumerate(t1)]}
    nth = nbatch = 0                                         # review F10: NEUTRAL sheet names and ids; the stratum lives in the manifest, not on the page
    for name, _ in STRATA:
        grp = sorted([s for s in rest if stratum_of(s) == name], key=order)
        for b in range(0, len(grp), BATCH_ROWS):             # a batch never straddles two strata
            rows_ = [sheet_row(f"B{nth + k + 1:04d}", s, videos[s["video"]]) for k, s in enumerate(grp[b:b + BATCH_ROWS])]
            nth += len(rows_)
            nbatch += 1
            plan[f"reader1_rest_b{nbatch:02d}"] = rows_
    pick = draw(t1, READER2_PRICE, "asis_6a_reader2_price") + draw(sorted(rest, key=order), READER2_REST, "asis_6a_reader2_rest")
    perm = C.rng_for("asis_6a_reader2_order").permutation(len(pick)).tolist()
    plan["reader2_150"] = [sheet_row(f"R{k + 1:03d}", pick[i], videos[pick[i]["video"]]) for k, i in enumerate(perm)]
    blind = draw(blind_pool, NOSYMBOL_N, "asis_6a_nosymbol_200")
    perm = C.rng_for("asis_6a_nosymbol_order").permutation(len(blind)).tolist()
    plan["reader2_nosymbol_200"] = [sheet_row(f"N{k + 1:03d}", blind[i], videos[blind[i]["video"]]) for k, i in enumerate(perm)]
    return plan


def sheet_manifest(plan: dict, strata_of: dict) -> list:
    """One row per sheet: its rows, tokens and how many of its statements fall in each stratum (`strata_of`: stmt_id -> 'S1'..'S4' or '').
    Kept OFF the reader folder (R50 / review F10): the main loop reads it to stop at a stratum; the readers never see it."""
    out = []
    for name, rows in plan.items():
        cnt = collections.Counter(strata_of.get(r["stmt_id"], "") or "blind" for r in rows)
        out.append({"sheet": name, "rows": len(rows), "tokens": est_tokens(rows),
                    "strata": " ".join(f"{k}:{cnt[k]}" for k in ("S1", "S2", "S3", "S4", "blind") if cnt[k])})
    return out


def tsv_text(rows: list, cols: list) -> str:
    out = ["\t".join(cols)]
    for r in rows:
        out.append("\t".join(str(r.get(c, "")).replace("\t", " ").replace("\n", " ") for c in cols))
    return "\n".join(out) + "\n"


def write_sheet(path: str, rows: list, cols: list = SHEET_COLS) -> None:
    """Writes one sheet atomically; refuses to overwrite a file that already carries a label (the inventory's `draw` rule)."""
    assert_sheet_columns(cols)
    path = C.checked(path)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            old = list(csv.DictReader(fh, delimiter="\t"))
        if any(r.get(c, "").strip() for r in old for c in SHEET_LABEL_COLS):
            raise GuardStop(f"{path} already carries labels; refusing to overwrite (delete it by hand to redraw)")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".partial", "w", encoding="utf-8") as fh:
        fh.write(tsv_text(rows, cols))
    os.replace(path + ".partial", path)


def est_tokens(rows: list) -> int:
    return sum((len(r["context"]) + len(r["snippet"]) + 40 * len(SHEET_LABEL_COLS)) // 4 for r in rows)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the agreement score (§4.1 step 5)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def norm_ticker(x: str) -> str:
    m = re.match(r"[A-Za-z0-9.\-]+", (x or "").strip().lstrip("$"))
    return m.group(0).upper() if m else ""


def parse_price(x: str) -> "float | None":
    m = re.search(r"\d+(?:[.,]\d+)?", (x or "").replace(",", ""))
    return float(m.group(0)) if m else None


def labelled(r: dict) -> bool:
    """A row is read when ticker_ident and his_trade are filled; the action and the day class are required only when it IS his own trade (a
    reader who marks a row 'advice' need not fill them, and such a row must not be set aside)."""
    if not all((r.get(c) or "").strip() for c in ("ticker_ident", "his_trade")):
        return False
    return (r["his_trade"].strip().lower() != "y") or all((r.get(c) or "").strip() for c in ("action", "date_pinnable"))


def joint_label(r: dict) -> tuple:
    """(ticker, action, day class). A row that is not his own trade is one label whatever the reason (advice / plan / viewer / other)."""
    if (r.get("his_trade") or "").strip().lower() != "y":
        return ("-", "not_own", "-")
    ident = (r.get("ticker_ident") or "").strip().lower()
    tick = norm_ticker(r.get("ticker", "")) if ident == "y" else "unidentified"
    return (tick or "unidentified", (r.get("action") or "").strip().lower(), (r.get("date_pinnable") or "").strip().lower())


def price_of(r: dict) -> "float | None":
    if (r.get("price_stated") or "").strip().upper() != "Y":
        return None
    return parse_price(r.get("price_value", ""))


def score_agreement(rows1: list, rows2: list) -> dict:
    """Reader 1 vs reader 2 on the rows both labelled (matched on stmt_id). -> counts, rates, the disagreement list."""
    by1 = {r["stmt_id"]: r for r in rows1}
    pairs = [(by1[r["stmt_id"]], r) for r in rows2 if r["stmt_id"] in by1]
    missing = [r["stmt_id"] for r in rows2 if r["stmt_id"] not in by1]
    unl = [a["stmt_id"] for a, b in pairs if not (labelled(a) and labelled(b))]
    pairs = [(a, b) for a, b in pairs if labelled(a) and labelled(b)]
    n = len(pairs)
    joint = [(a, b) for a, b in pairs if joint_label(a) == joint_label(b)]
    marg = {"his_trade": sum((a["his_trade"].strip().lower() == b["his_trade"].strip().lower()) for a, b in pairs)}
    own = [(a, b) for a, b in pairs if joint_label(a)[1] != "not_own" and joint_label(b)[1] != "not_own"]
    marg["ticker"] = sum(joint_label(a)[0] == joint_label(b)[0] for a, b in own)
    marg["action"] = sum(joint_label(a)[1] == joint_label(b)[1] for a, b in own)
    marg["day"] = sum(joint_label(a)[2] == joint_label(b)[2] for a, b in own)
    both_price = [(price_of(a), price_of(b)) for a, b in pairs if price_of(a) is not None and price_of(b) is not None]
    price_ok = sum(abs(x - y) < 0.005 for x, y in both_price)
    dis = [(a["stmt_id"], a.get("sid", ""), joint_label(a), joint_label(b)) for a, b in pairs if joint_label(a) != joint_label(b)]
    return {"n": n, "joint_ok": len(joint), "joint_rate": len(joint) / n if n else float("nan"), "own_n": len(own), "marginal": marg,
            "price_n": len(both_price), "price_ok": price_ok, "price_rate": price_ok / len(both_price) if both_price else float("nan"),
            "disagreements": dis, "not_in_reader1": missing, "unlabelled": unl,
            "joint_pass": bool(n) and len(joint) / n >= AGREE_JOINT_BAR,
            "price_testable": bool(both_price),       # review F8: no row where both read a price is NOT a pass
            "price_pass": bool(both_price) and price_ok / len(both_price) >= AGREE_PRICE_BAR}


def read_sheet(path: str) -> list:
    with open(C.checked(path), encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def blind_spot(rows: list) -> dict:
    """The blind sample (reader 2 only): the share of the no-symbol statements that are his own trade event, with a Wilson range."""
    ev = {"buy", "add", "sell_part", "sell_all", "sell_unspec", "stopped", "shorted", "covered"}
    rows = [r for r in rows if labelled(r)]
    k = sum(1 for r in rows if (r["his_trade"].strip().lower() == "y") and r["action"].strip().lower() in ev)
    lo, hi = INV.wilson(k, len(rows))
    return {"n": len(rows), "own_event": k, "share": k / len(rows) if rows else float("nan"), "lo": lo, "hi": hi,
            "own_unidentified": sum(1 for r in rows if joint_label(r)[1] in ev and joint_label(r)[0] == "unidentified")}


def agreement_report(say, res: dict, blind: "dict | None") -> None:
    say(f"- rows both readers labelled: {res['n']}; not in reader 1's sheets: {len(res['not_in_reader1'])}; unlabelled by either: {len(res['unlabelled'])}")
    say(f"- joint label (ticker, action, day class): {res['joint_ok']} / {res['n']} = {100 * res['joint_rate']:.1f}% (bar >= {100 * AGREE_JOINT_BAR:.0f}%) "
        f"-> {'PASS' if res['joint_pass'] else 'BELOW THE BAR'}")
    m = res["marginal"]
    say(f"- parts: his-own-trade {m['his_trade']} / {res['n']}; among rows both call his own ({res['own_n']}): ticker {m['ticker']}, action {m['action']}, "
        f"day class {m['day']}")
    say(f"- price number where both read one: {res['price_ok']} / {res['price_n']}" +
        (f" = {100 * res['price_rate']:.1f}% (bar >= {100 * AGREE_PRICE_BAR:.0f}%) -> {'PASS' if res['price_pass'] else 'BELOW THE BAR'}" if res["price_n"] else
         " (no row where both read a price: the bar is not testable)"))
    if blind is not None:
        say(f"- blind sample (reader 2 only): {blind['own_event']} of {blind['n']} no-symbol statements are his own trade event = {100 * blind['share']:.1f}% "
            f"(95% range {100 * blind['lo']:.1f}%-{100 * blind['hi']:.1f}%); of them the ticker unidentified: {blind['own_unidentified']}")
    if res["disagreements"]:
        say(f"- disagreements ({len(res['disagreements'])}):")
        for sid, s1, a, b in res["disagreements"]:
            say(f"    {sid} {s1}: reader 1 {a} | reader 2 {b}")
    if res["price_n"] and res["price_n"] < SMALL_PRICE_N:
        say(f"- NOTE: the price bar rests on only {res['price_n']} row(s) where both readers read a price")
    if res["joint_pass"] and res["price_pass"]:
        say("AGREEMENT PASS")
    elif res["joint_pass"] and not res["price_testable"]:
        say("JOINT LABEL PASSES BUT THE PRICE BAR IS NOT TESTABLE (no row where both readers read a price): this is NOT an agreement pass; "
            "read a price-candidate sample before step 6b")
    else:
        say("AGREEMENT BELOW THE BAR: the wording of the sheet is fixed and BOTH readers re-read a fresh 150 (once, disclosed); a second failure stops step 6a")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the machine pass
# ═════════════════════════════════════════════════════════════════════════════════════════════
def corpus_common(vids: list, df_min: float = COMMON_DF) -> frozenset:
    """R41: the tokens said in at least `df_min` of the streams (document frequency; a frequent NAME such as riot or codex is bursty and stays
    out, ordinary speech such as play or best is not)."""
    df = collections.Counter()
    for v in vids:
        df.update(set(v.toks))
    return frozenset(w for w, n in df.items() if n >= df_min * len(vids))


def corpus_counts(vids: list) -> collections.Counter:
    cnt = collections.Counter()
    for v in vids:
        cnt.update(v.toks)
    return cnt


def in_span(sd: str) -> bool:
    return SPAN[0] <= sd <= SPAN[1]


def machine_pass(streams: list, index: SymbolIndex, resolver: AliasResolver) -> dict:
    """Wide statements for every stream, annotated; the alias logs. The hand-read set = primary-span, non-account, FILTER_CLASSES hit."""
    alias_log, ambiguous_log, unmatched, excl = {}, {}, collections.Counter(), collections.Counter()
    allst = []
    for st in streams:
        sts = wide_statements(st.v)
        for s in sts:
            s["stmt_id"] = f"{s['video']}:{s['w0']}"
        if in_span(st.stream_date):
            near = [s for s in sts if s["kind"] != "account"]
            annotate_stream(st, near, index, resolver, alias_log, ambiguous_log, unmatched, excl)
        for s in sts:
            s.setdefault("hits", [])
            s.setdefault("stream_date", st.stream_date)
            s.setdefault("price_candidate", False)
            s.setdefault("shares", False)
            s.setdefault("dollar_result", False)
            s.setdefault("day_words", False)
        allst.extend(sts)
    prim = [s for s in allst if in_span(s["stream_date"])]
    handread = [s for s in prim if in_filter(s)]
    pool = [s for s in prim if s["kind"] != "account" and not in_filter(s)]
    return {"all": allst, "primary": prim, "handread": handread, "blind_pool": pool, "alias_log": alias_log, "ambiguous_log": ambiguous_log,
            "unmatched": unmatched}


def english_excluded_readout(streams: list, wide: list, index: SymbolIndex, resolver: AliasResolver) -> tuple:
    """R40: the dictionary words near statements that the English test kept out of the alias list although they were 1 edit from exactly one
    live (non-common) symbol with the same first letter. -> (Counter of (word, symbol), the plan's examples looked up)."""
    by_vid = {st.v.id: st for st in streams}
    cnt = collections.Counter()
    for s in wide:
        if s["kind"] == "account" or not in_span(s["stream_date"]):
            continue
        st = by_vid[s["video"]]
        lo, hi = window_of(st.v, s)
        live = index.live_map(st.stream_date)
        for i in range(lo, hi):
            tk = st.v.toks[i]
            if len(tk) < 3 or tk in live or tk in index.known or index.words.klass(tk) != "dict":
                continue
            cand = [(k, d) for k, d in resolver.candidates(tk, limit=1) if k in live]
            if len(cand) == 1 and len(live[cand[0][0]][0]) == 1:
                cnt[(tk, live[cand[0][0]][0][0])] += 1
    return cnt


def examples_lookup(index: SymbolIndex, resolver: AliasResolver, d: str = "2020-06-15") -> list:
    """The plan's own garbles looked up one by one against the search set of a mid-2020 stream: (word, class, resolution)."""
    out = []
    for w in ("twix", "tweaks", "tricks", "twigs", "gosh", "cash", "tqq", "tq", "tvix", "gush", "tqqq"):
        r = resolver.resolve(w, d) if index.words.klass(w) == "other" else ("english", None, None, ())
        out.append((w, index.words.klass(w), r[0], r[1] or "", r[3]))
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the dry run
# ═════════════════════════════════════════════════════════════════════════════════════════════
MODULE_FILES = ("asis_common.py", "01_points.py", "02_captions.py", "forbidden_identifiers.txt", os.path.join("inventory", "captions_inventory.py"))


def module_shas_line() -> str:
    """01_points.py is IN it (review F1): load_windows executes its read_frames / read_windows, so an edit to it changes the joins."""
    return " ".join(f"{n} {C.sha(os.path.join(HERE, n))[:16]}" for n in MODULE_FILES)


def dry_modules_line(path: str = None) -> "str | None":
    path = path or P_DRY
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            if ln.startswith("- modules: "):
                return ln[len("- modules: "):].strip()
    return None


def dry_mismatches(path: str = None) -> "int | None":
    """The MISMATCH count of the dry run's RESULT line (None when absent or unreadable); a mismatching dry run also ends COMPLETE."""
    path = path or P_DRY
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            if ln.startswith("RESULT:"):
                try:
                    return int(ln.split("MISMATCH")[0].strip().split()[-1])
                except (ValueError, IndexError):
                    return None
    return None


def pins_6a(doc: str = None) -> dict:
    """Every pin step 6a rests on: step 5's inputs and modules (C.pins, without its outputs), this module, the inventory's inputs, the word
    lists, and this stage's dry-run printout."""
    p = C.pins(doc, include_outputs=False)
    p["02_captions.py"] = C.sha(os.path.join(HERE, "02_captions.py"))
    p["captions_inventory.py"] = C.sha(os.path.join(HERE, "inventory", "captions_inventory.py"))
    for name, path in (("video_status", INV.STATUS), ("caption_sample", INV.SAMPLE_TSV), ("account_statements", INV.ACCOUNT_TSV)):
        p[name] = C.sha(path) if os.path.exists(path) else "ABSENT"
    for path in DICT_FILES:
        p["dict_" + os.path.basename(path)] = C.sha(path) if os.path.exists(path) else "ABSENT"
    p["dryrun6a_printout"] = C.sha(P_DRY) if os.path.exists(P_DRY) else "ABSENT"
    return p


def sheets_outputs() -> list:
    """Every file --sheets writes or may leave behind: the sheets in the reader folder, the four side files, the printout."""
    out = []
    if os.path.isdir(SHEETS_DIR):
        out += [os.path.join(SHEETS_DIR, n) for n in sorted(os.listdir(SHEETS_DIR))]
    out += [p for p in OUT_FILES.values() if os.path.exists(p)]
    return out + ([P_RUN] if os.path.exists(P_RUN) else [])


def sheets_gate(doc: str = None) -> list:
    """Review F1 (the reader sheets are the irreversible step-6a output, so --sheets refuses like 01_points --run, R34): the dry run complete
    with 0 MISMATCH and made by the modules on disk; every pin below the doc's freeze marker; the ledger verifying; no sheet or side file
    present. -> the reasons it is refused (empty = go)."""
    problems = []
    if not C.dry_run_complete(P_DRY):
        problems.append("the step-6a dry run has not completed (02_captions_dryrun.txt)")
    else:
        mm = dry_mismatches()
        if mm is None:
            problems.append("the dry run's RESULT line is missing or unreadable")
        elif mm > 0:
            problems.append(f"the dry run ended with {mm} MISMATCH")
        ml = dry_modules_line()
        if ml != module_shas_line():
            problems.append("the dry run was made by other code than the modules on disk (or carries no module line): rerun --dry-run first"
                            + (f" (dry run: {ml})" if ml else ""))
    miss = C.freeze_missing(doc or C.DOC, pins_6a(doc))
    if miss:
        problems.append("pins not below the doc's freeze marker (freeze first, --print-pins, paste): " + ", ".join(miss))
    bad = C.ledger_verify() if os.path.exists(C.LEDGER) else []
    if bad:
        problems.append("ledger: " + "; ".join(bad))
    present = sheets_outputs()
    if present:
        problems.append("outputs exist: " + ", ".join(present))
    return problems


def run_machine(say) -> dict:
    """Loads and runs the whole machine pass; prints the inputs. -> the state dict the dry run and --sheets share."""
    t0 = time.time()
    rows, ok, vids, dups = INV.load_videos()
    for r in ok:
        C.seal_date(iso(r["upload_date"]), "caption file")
    say(f"- captions: {len(ok)} caption files, {len(vids)} unique streams, {len(dups)} duplicate uploads dropped ({time.time() - t0:.0f}s)")
    dictionary, conn, shas = load_wordlists()
    words = Words(dictionary, conn, corpus_common(vids), FILLERS)
    say("- dictionary: " + ", ".join(f"{os.path.basename(p)} {h}" for p, h in shas.items()) + f"; {len(dictionary):,} words + {len(conn)} connectives; "
        f"{len(FILLERS)} fillers; a dictionary word said in {100 * COMMON_DF:.0f}% of the streams is 'common' (R41): {len(words.common):,} tokens")
    counts = corpus_counts(vids)
    lex = C.load_lexicon()
    tally = collections.Counter()
    alias = C.extend_alias_renames(C.load_alias(lex, tally), lex, tally)
    say(f"- lexicon {len(lex):,} symbols; alias map {len(alias):,} (signature {tally['alias_signature']}, dedupe {tally['alias_dedupe']}, "
        f"rename table {tally['alias_rename_table']})")
    index = SymbolIndex(lex, alias, words)
    resolver = AliasResolver(index, counts)
    streams, dropped = make_streams(vids)
    st = {"rows": rows, "ok": ok, "vids": vids, "dups": dups, "words": words, "lex": lex, "alias": alias, "index": index, "resolver": resolver,
          "streams": streams, "dropped_streams": dropped, "dict_shas": shas, "t0": t0}
    t1 = time.time()
    st.update(machine_pass(streams, index, resolver))
    say(f"- machine pass: {len(st['all']):,} widened statements over {len(streams)} streams ({time.time() - t1:.0f}s)")
    return st


def sample_rescore(say, claims: Claims, st: dict) -> None:
    """The inventory's 120 hand-read rows through the widened search and the filter (§4.1 steps 1 and 3)."""
    rows = read_sheet(INV.SAMPLE_TSV)
    vmap = {s.v.id: s for s in st["streams"]}
    vids_all = {v.id: v for v in st["vids"]}
    old_by_vid = {}
    for v in st["vids"]:
        if any(r["video"] == v.id for r in rows):
            old_by_vid[v.id] = old_statements(v)
    wide_by_vid = collections.defaultdict(list)
    for s in st["all"]:
        wide_by_vid[s["video"]].append(s)
    found = overlapped = renamed = newkind = 0
    variants = {"S1: strong + resolved garble": STRATA[0][1], "S1+S2: + dictionary-word symbol within 12 words": STRATA[0][1] + STRATA[1][1],
                "S1-S3: + garble with tied candidates": STRATA[0][1] + STRATA[1][1] + STRATA[2][1],
                "S1-S4: + dictionary-word symbol anywhere in 30 s (the plan's literal filter)": FILTER_CLASSES}
    passes = {k: collections.Counter() for k in variants}
    right = collections.Counter()
    usable = collections.Counter()
    na_usable = collections.Counter()                    # review F6: the same counts WITHOUT the 'account' rows (R47 puts those out of the set by design)
    na_pass = {k: collections.Counter() for k in variants}
    acct_rows = collections.Counter()
    for r in rows:
        olds = [o for o in old_by_vid.get(r["video"], []) if INV.hms(o["t"]) == r["t_hms"]]
        if not olds:
            continue
        found += 1
        o = olds[0]
        ws = [w for w in wide_by_vid[r["video"]] if overlaps(o, w)]
        if not ws:
            continue
        overlapped += 1
        w = ws[0]
        renamed += w["kind"] != o["kind"]
        newkind += bool({"shorted", "covered"} & set(w["kinds_in_cluster"].split("+")))
        is_acct = all(x["kind"] == "account" for x in ws)
        for col in ("usable_strict", "usable_anydate", "usable_loose"):
            if r[col] == "Y":
                usable[col] += 1
                if is_acct:
                    acct_rows[col] += 1
                else:
                    na_usable[col] += 1
                for name, cl in variants.items():
                    if any(in_filter(x, cl) for x in ws):
                        passes[name][col] += 1
                        if not is_acct:
                            na_pass[name][col] += 1
                tick = norm_ticker(r["ticker"]) if r["ticker_ident"] == "Y" else ""
                if tick and any(tick in [sy for h in x["hits"] if h[2] in FILTER_CLASSES for sy in h[1].split(";")] for x in ws):
                    right[col] += 1
    claims("inventory hand-read rows (caption_sample.tsv)", 120, len(rows))
    claims("... each found in the original-engine statements", 120, found)
    claims("... each overlapped by a widened statement (none lost)", 120, overlapped)
    say(f"  widened engine on those rows: {renamed} renamed by the new kinds, {newkind} now carry a shorted / covered match")
    say("  the hand-read filter on the inventory's usable rows (the share it DROPS is the recall loss; the plan expected under 10%):")
    table(say, ["filter variant", f"usable_strict ({usable['usable_strict']})", "dropped", f"usable_anydate ({usable['usable_anydate']})", "dropped",
                f"usable_loose ({usable['usable_loose']})", "dropped"],
          [[name] + sum(([passes[name][col], pct(usable[col] - passes[name][col], usable[col])] for col in ("usable_strict", "usable_anydate", "usable_loose")), [])
           for name in variants] +
          [["... the S1-S4 filter, with the LABELLED ticker among its hits"] + sum(([right[col], pct(usable[col] - right[col], usable[col])] for col in ("usable_strict", "usable_anydate", "usable_loose")), [])])
    say(f"  review F6: the table above counts the inventory's 'account' rows ({acct_rows['usable_strict']} strict, {acct_rows['usable_anydate']} anydate, "
        f"{acct_rows['usable_loose']} loose), which R47 keeps out of the set by design, so EVERY cut drops them. Without them, with the 95% Wilson range "
        "of the share dropped (a handful of rows decides each cell; ranges that overlap are not different):")
    rows_ = []
    for name in variants:
        cells = []
        for col in ("usable_strict", "usable_anydate", "usable_loose"):
            n, k = na_usable[col], na_usable[col] - na_pass[name][col]
            lo, hi = INV.wilson(k, n)
            cells += [f"{k}/{n}", f"{100 * k / n:.1f}% ({100 * lo:.1f}-{100 * hi:.1f})" if n else "n/a"]
        rows_.append([name] + cells)
    table(say, ["filter variant (no account rows)", "strict dropped", "share (95% range)", "anydate dropped", "share (95% range)", "loose dropped",
                "share (95% range)"], rows_)
    say("  (the rows the filter cannot see: the ticker is a company name said whole - shopify, peloton -, an inferred referent ('that thing'), "
        "a garble beyond the edit limit, or a delisted name; those are what the 200-statement blind sample measures)")


def dry_report(say, claims: Claims, st: dict, windows_info: tuple) -> None:
    streams, allst, vids = st["streams"], st["all"], st["vids"]
    # ---- the original engine: the claims ---------------------------------------------------------------------------------------------
    say("\n## 1. The original nine-kind extraction: the inventory's numbers are claims on it (R46)")
    old = []
    for v in vids:
        old.extend(old_statements(v))
        # parity with the inventory's own functions on the same video (a belt: the copy and the original agree)
    inv_total = sum(len(INV.cluster(v, INV.find_matches(v))) for v in vids)
    claims("caption files", 495, len(st["ok"]))
    claims("unique streams", 485, len(vids))
    claims("duplicate uploads dropped", 10, len(st["dups"]))
    claims("statements, all years (the copied engine)", 9474, len(old))
    claims("... the copied engine equals the inventory's own functions", inv_total, len(old))
    frame = [s for s in old if s["date"][:4] in FRAME_YEARS]
    claims("statements in 2020-22 (upload year)", 7607, len(frame))
    by = collections.Counter(s["kind"] for s in frame)
    for k in OLD_PRIORITY:
        claims(f"... {k}", CLAIMS_TABLE[k], by[k])
    claims("'Late upload' videos among the caption files", 8, sum("late upload" in r["title"].lower() for r in st["ok"]))
    claims("lexicon symbols", 22744, len(st["lex"]))
    claims("account statements listed by the inventory", 133, len(INV.load_account_rows()))
    # ---- the widened engine ----------------------------------------------------------------------------------------------------------
    say("\n## 2. The widened extraction (+ shorted, covered) beside it")
    wide_all = []
    for v in vids:
        wide_all.extend(wide_statements(v))
    wide_frame = [s for s in wide_all if s["date"][:4] in FRAME_YEARS]
    ob = collections.defaultdict(list)
    for s in old:
        ob[s["video"]].append(s)
    wb = collections.defaultdict(list)
    for s in wide_all:
        wb[s["video"]].append(s)
    lost = merged = 0
    for vid, olds in ob.items():
        for o in olds:
            if not any(overlaps(o, w) for w in wb[vid]):
                lost += 1
    for vid, ws in wb.items():
        for w in ws:
            if sum(overlaps(o, w) for o in ob[vid]) >= 2:
                merged += 1
    gained = [s for s in wide_all if not any(overlaps(o, s) for o in ob[s["video"]])]
    claims("original statements with NO overlapping widened statement (lost)", 0, lost)
    say(f"- widened statements, all years {len(wide_all):,} (original {len(old):,}); 2020-22 upload years {len(wide_frame):,} (original {len(frame):,})")
    say(f"- GAINED (no original statement overlaps them): {len(gained)}; widened statements that MERGED two or more original ones: {merged}")
    gk = collections.Counter((s["date"][:4], s["kind"]) for s in gained)
    yrs = sorted({s["date"][:4] for s in gained})
    table(say, ["gained, by kind"] + yrs + ["total"], [[k] + [gk[(y, k)] for y in yrs] + [sum(gk[(y, k)] for y in yrs)] for k in ("shorted", "covered")])
    nm = collections.Counter(k for s in wide_all for k in s["kinds_in_cluster"].split("+") if k in ("shorted", "covered"))
    say(f"- shorted / covered matches inside ANY statement (gained or merged into an old one): shorted {nm['shorted']}, covered {nm['covered']}")
    for s in gained[:8]:
        say(f"    e.g. {s['date']} {s['video']}@{INV.hms(s['t'])} [{s['kind']}] {s['snippet'][:130]}")
    sample_rescore(say, claims, st)
    # ---- stream dates ----------------------------------------------------------------------------------------------------------------
    say("\n## 3. Stream dates (R48)")
    late = [s for s in streams if s.late]
    for s in sorted(late, key=lambda s: s.upload):
        say(f"- {s.v.id} upload {s.upload} -> stream {s.stream_date} ({s.v.title!r}){'  NOTE ' + s.note if s.note else ''}")
    for s, kept in st["dropped_streams"]:
        say(f"- DROPPED {s.v.id} (upload {s.upload}, {s.v.title!r}): the same stream as {kept.v.id} (stream {kept.stream_date}, {s.v.seconds}s)")
    yv = [s for s in streams if re.search(r"yesterday'?s\s+video", s.v.title.lower())]
    for s in yv:
        say(f"- CORRECTED (R48, review F11): {s.v.id} upload {s.upload} -> stream {s.stream_date} ({s.v.title!r}: the previous weekday of the upload)")
    claims("'Late upload' streams among the 485 (8 files less the 2 duplicate uploads the inventory dropped)", 6, len(late) + sum(1 for s, _ in st["dropped_streams"] if s.late))
    claims("... every late upload's title date resolves", 0, sum(1 for s in late if s.note == "no_date_in_title"))
    prim_streams = [s for s in streams if in_span(s.stream_date)]
    say(f"- streams in the primary span {SPAN[0]}..{SPAN[1]} (stream date): {len(prim_streams)} of {len(streams)}")
    # ---- the search set --------------------------------------------------------------------------------------------------------------
    say("\n## 4. The search set (R41, R44)")
    idx = st["index"]
    sizes = sorted(len(idx.live_map(s.stream_date)) for s in prim_streams)
    cls = collections.Counter(c for s in prim_streams[:1] for _, c in idx.live_map(s.stream_date).values())
    say(f"- symbols per stream date (strong + weak keys): min {sizes[0]:,}, median {sizes[len(sizes) // 2]:,}, max {sizes[-1]:,}; example date "
        f"{prim_streams[0].stream_date}: {dict(cls)}")
    say("- NO_BARS_SYMBOLS (always in the set, R44): " + ", ".join(NO_BARS_SYMBOLS))
    say(f"- 'common' tokens (never a mention): {len(idx.words.common):,} dictionary words said in {100 * COMMON_DF:.0f}% of the streams + "
        f"{len(idx.words.connectives)} connectives + {len(FILLERS)} fillers")
    # ---- hits and the hand-read set --------------------------------------------------------------------------------------------------
    say("\n## 5. The hand-read set (§4.1 step 3)")
    prim = st["primary"]
    non_acc = [s for s in prim if s["kind"] != "account"]
    handread, pool = st["handread"], st["blind_pool"]
    cnt_cls = collections.Counter()
    for s in non_acc:
        for c in {h[2] for h in s["hits"]}:
            cnt_cls[c] += 1
    say(f"- primary-span statements: {len(prim):,} ({len(prim) - len(non_acc)} 'account', not put in the set: R47); non-account {len(non_acc):,}")
    say("- statements with at least one hit of class: " + ", ".join(f"{c} {cnt_cls[c]:,}" for c in ("strong", "alias", "weak_near", "weak", "amb")) +
        "  (strong = not a dictionary word; alias = resolved garble; weak_near = a dictionary-word symbol within 12 words; weak = the same, farther "
        "than 12 words but inside 30 s; amb = a garble with tied candidates)")
    sizes_, cum = [], ()
    for name, cl in STRATA:
        cum += cl
        sel = [s for s in non_acc if in_filter(s, cum)]
        own = [s for s in handread if stratum_of(s) == name]
        sizes_.append([name, "+".join(cl), f"{len(own):,}", f"{sum(1 for s in own if s['price_candidate']):,}", f"{len(sel):,}", f"{sum(1 for s in sel if s['price_candidate']):,}"])
    table(say, ["stratum", "hit classes", "statements (strongest hit here)", "of them price candidates", "cumulative", "cumulative price candidates"], sizes_)
    say(f"- HAND-READ SET (the plan's literal filter, strata S1-S4): {len(handread):,} statements vs the plan's expected 1,500-2,500 "
        f"({'inside' if 1500 <= len(handread) <= 2500 else 'OUTSIDE'} the band); stratum S1 alone {sum(1 for s in handread if stratum_of(s) == 'S1'):,}. "
        f"For scale: the plan's own arithmetic is 43% of the inventory's 7,607 = ~3,270 ticker + action statements, and the widened kinds add "
        f"{sum(1 for s in handread if s['kind'] in ('shorted', 'covered')):,} here")
    say(f"- review F6: the plan's literal filter admits {len(handread):,} of the {len(non_acc):,} non-account in-span statements = {pct(len(handread), len(non_acc))}; "
        f"the blind pool (no symbol of any class) is the other {len(pool):,}. Taken literally the filter barely filters: dictionary-word symbols "
        f"(plug, eyes, ads, apt, stay, save, free, huge ...) count as mentions. The strata are the only cut that separates them; where to stop is his ruling")
    tw = [s for s in handread if any(h[0] == "tesla" and h[2] == "amb" for h in s["hits"]) and stratum_of(s) == "S3"]
    say(f"- the single word 'tesla' (TSLA or TELA, tied) is the ONLY reason {len(tw):,} statements sit in stratum S3; a one-line ruling (tesla = TSLA) would move "
        f"them to S1, but a name table is not 'from the captions alone' (R43), so it is the main loop's call")
    say(f"- blind pool (no symbol of ANY class within +-30 s): {len(pool):,}; the sample drawn from it: {min(NOSYMBOL_N, len(pool))}")
    by_year = collections.Counter(s["stream_date"][:4] for s in handread)
    kinds = collections.Counter(s["kind"] for s in handread)
    say("- hand-read set by stream year: " + ", ".join(f"{y} {n:,}" for y, n in sorted(by_year.items())) + "; by kind: " +
        ", ".join(f"{k} {kinds[k]}" for k in WIDE_PRIORITY if kinds[k]))
    only_alias = sum(1 for s in handread if stratum_of(s) == "S1" and not any(h[2] == "strong" for h in s["hits"]))
    say(f"- of stratum S1, reached ONLY through a resolved garble: {only_alias:,}")
    for nm_, cl in STRATA:
        tok = collections.Counter(h[0] for s in handread if stratum_of(s) == nm_ for h in {(h[0], h[1], h[2]): h for h in s["hits"]}.values() if h[2] in cl)
        say(f"- the 25 most frequent hit tokens of stratum {nm_} (a noise audit: jargon that is also a symbol shows here): " + ", ".join(f"{w} {n}" for w, n in tok.most_common(25)))
    # ---- aliases ---------------------------------------------------------------------------------------------------------------------
    say("\n## 6. The alias list (R40, R42, R43)")
    al, am = st["alias_log"], st["ambiguous_log"]
    say(f"- accepted aliases (a word -> ONE live symbol, heard within +-30 s of a statement): {len(al):,} word-symbol pairs, "
        f"{sum(l.n for l in al.values()):,} hearings; ambiguous words (tied candidates, not used): {len(am):,}")
    say("- review F9: the alias list is UNVERIFIED and its top is noisy (a company or sector word one edit from a ticker: crypto > CRTO, nasdaq > NDAQ, "
        "pfizer > PFIE where Pfizer is PFE, cciv > CCI where CCIV is not in the lexicon). S1 is a stratum of strong hit classes, NOT a precision tier; the "
        "readers resolve every ticker from the words and 03 joins on THEIR tickers only")
    top_al = sorted(al.items(), key=lambda kv: -kv[1].n)[:25]
    table(say, ["word", "symbol", "heard", "evidence (first)"], [[w, s, l.n, l.evidence[0][:110]] for (w, s), l in top_al])
    ex = examples_lookup(idx, st["resolver"])
    say("- the plan's own examples against a mid-2020 search set: " + "; ".join(f"{w}: {k}" + (f" -> {r} {sy}" if r not in ("english",) else "") for w, k, r, sy, _t in ex))
    exc = english_excluded_readout(streams, allst, idx, st["resolver"])
    say(f"- READOUT (not acted on): {len(exc):,} dictionary-word / symbol pairs 1 edit apart that the English test kept OUT of the alias list; the 25 most heard: " +
        ", ".join(f"{w}>{s} {n}" for (w, s), n in exc.most_common(25)))
    um = st["unmatched"]
    say(f"- READOUT (R43): the 40 most heard non-dictionary words near statements that match NO live symbol within the edits: " +
        ", ".join(f"{w} {n}" for w, n in um.most_common(40)))
    # ---- tiers -----------------------------------------------------------------------------------------------------------------------
    say("\n## 7. Tiers (R49, R51)")
    t1 = [s for s in handread if s["price_candidate"]]
    t1b = [s for s in handread if s["shares"] and s["dollar_result"]]
    t2 = [s for s in handread if not s["price_candidate"] and s["day_words"]]
    t3 = [s for s in handread if not s["price_candidate"] and not s["day_words"]]
    say(f"- price candidates (T1 sheet): {len(t1):,} vs the plan's 300-600 ({'inside' if 300 <= len(t1) <= 600 else 'OUTSIDE'}); the plan's expected T1 AFTER the "
        f"readers' labels is 100-250 (about 20% of the ~1,070 dated statements carry a price, roughly half clean)")
    say(f"- shares + dollar result anywhere in the +-30 s (T1b candidates): {len(t1b):,} vs the plan's 50-150 after labels")
    say(f"- machine day-word split of the rest (a PROJECTION of T2 / T3; the readers' day labels decide): day word present {len(t2):,}, absent {len(t3):,}; "
        f"the inventory's yield projected on the set: usable-now 14% = {int(0.14 * len(handread)):,}, ticker + action any day 43% = {int(0.43 * len(handread)):,}")
    # ---- joins -----------------------------------------------------------------------------------------------------------------------
    say("\n## 8. The symbol-and-day join, PROVISIONAL (R52): the day is the stream date, the only day known before the readers")
    windows, S = windows_info
    by_sym = index_windows(windows)
    holds = index_holds(windows)
    res = collections.Counter()
    yr = collections.Counter()
    reasons = collections.Counter()
    tie_one = tie_sides = 0
    no_symbol = 0
    for s in handread:
        syms = hit_symbols(s)
        if not syms:
            no_symbol += 1
            continue
        best = best_join(syms, s["stream_date"], by_sym, holds, S)
        res[best["status"]] += 1
        yr[(s["stream_date"][:4], best["status"])] += 1
        if best["status"] == "none":
            reasons[best["reason"]] += 1
        elif best["status"] == "ambiguous":
            tie_one += tie_is_one_position(best)
            tie_sides += sum(1 for t in best["tied"].split(";") if t.endswith(":buy"))
    say(f"- windows {len(windows):,} ({sum(1 for w in windows if w[1] == 'buy'):,} buy, {sum(1 for w in windows if w[1] == 'sale'):,} sale) over "
        f"{len(by_sym):,} panel symbols")
    say(f"- hand-read statements joined (best symbol of each): unique {res['unique']:,}, ambiguous {res['ambiguous']:,}, no position within a session "
        f"{res['none']:,}; {no_symbol:,} more carry only a tied-garble or far dictionary-word hit (S3 / S4) and have no join symbol (R56)")
    say(f"- the {res['none']:,} 'none' split (review F3): the symbol is held but the stream date lies BETWEEN that position's first and last window "
        f"(inside a hold: a trade said mid-hold, not an invisible trade) {reasons['inside_hold']:,}; held on another date {reasons['other_date']:,}; "
        f"never on his panel {reasons['not_on_panel']:,} (this last includes false aliases such as crypto, nasdaq, pfizer). Only the last two are even a "
        f"candidate for 'invisible'; 03 treats a stated day inside a hold as HELD, not none")
    say(f"- the {res['ambiguous']:,} 'ambiguous' ties (review F2): {tie_one:,} are ONE position's buy window and sale window on the same session; their "
        f"eid and side are left BLANK on the join (a sort would hand every tie to 'buy' and make each sale said on a day-trade day look like a miss); "
        f"`tied` lists them")
    table(say, ["stream year", "unique", "ambiguous", "none"], [[y, yr[(y, 'unique')], yr[(y, 'ambiguous')], yr[(y, 'none')]] for y in sorted({k[0] for k in yr})])
    say("- own-trade statements whose ticker the readers could not identify: not measurable before the readers (the blind sample reports it)")
    # ---- sheets ----------------------------------------------------------------------------------------------------------------------
    say("\n## 9. Sheet sizes (nothing written by the dry run)")
    vmap = {s.v.id: s.v for s in streams}
    plan = build_sheet_plan(handread, pool, vmap)
    strata_of = {x["stmt_id"]: stratum_of(x) for x in handread}
    man = sheet_manifest(plan, strata_of)
    table(say, ["sheet", "rows", "approx tokens (4 chars each, context + labels)", "strata of its statements (manifest only; NOT on the sheet, review F10)"],
          [[m["sheet"], m["rows"], f"{m['tokens']:,}", m["strata"]] for m in man])
    rows_ = [[m["sheet"], m["rows"], m["tokens"]] for m in man]
    r1 = sum(n for nm_, n, _ in rows_ if nm_.startswith("reader1"))
    t_r1 = sum(t for nm_, _, t in rows_ if nm_.startswith("reader1"))
    menu, cum = [], est_tokens(plan["reader1_t1_price"])
    menu.append(["T1 price batch (price candidates of the whole set)", len(plan["reader1_t1_price"]), f"{cum:,}", f"{cum:,}"])
    for nm_, _ in STRATA:
        mm = [m for m in man if m["sheet"].startswith("reader1_rest_") and m["strata"].startswith(nm_ + ":")]
        tok = sum(m["tokens"] for m in mm)
        cum += tok
        menu.append([f"rest, stratum {nm_}", sum(m["rows"] for m in mm), f"{tok:,}", f"{cum:,}"])
    say("- the reading menu (the main loop stops at a line; the sheets are in this order):")
    table(say, ["block", "rows", "tokens", "cumulative tokens"], menu)
    say(f"- reader 1: {r1:,} rows, about {t_r1:,} tokens of sheet (the plan priced ~700k for 1,500-2,500 statements); the T1 sheet alone "
        f"{len(plan['reader1_t1_price']):,} rows, about {est_tokens(plan['reader1_t1_price']):,} tokens; reader 2: 150 + {len(plan['reader2_nosymbol_200'])} blind rows, "
        f"about {est_tokens(plan['reader2_150']) + est_tokens(plan['reader2_nosymbol_200']):,} tokens")
    for name, rs in plan.items():
        assert_sheet_columns(list(rs[0].keys())) if rs else None
    say("- every sheet's columns checked: captions-only layout, no window / bar / price / machine-hint column")
    lens = [len(r["context"].split()) for rs in plan.values() for r in rs]
    say(f"- context length (words): median {int(np.median(lens))}, max {max(lens)}")


def inputs_line(st: dict) -> str:
    return ("- input pins (sha256, first 16): " +
            ", ".join(f"{n} {C.sha(p)[:16]}" for n, p in (("video_status", INV.STATUS), ("caption_sample", INV.SAMPLE_TSV), ("account_statements", INV.ACCOUNT_TSV),
                                                      ("lexicon", C.FILES["lexicon"]), ("calendar_cache", C.FILES["calendar_cache"]),
                                                      ("snapshots", C.FILES["snapshots"]), ("entries", C.FILES["entries"]), ("exits", C.FILES["exits"]))) +
            f", subs_list {C.subs_list_sha()[:16]}, dictionary " + ", ".join(f"{os.path.basename(p)} {h}" for p, h in st["dict_shas"].items()))


def write_tsv(rows: list, cols: list, path: str) -> None:
    path = C.checked(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".partial", "w", encoding="utf-8") as fh:
        fh.write(tsv_text(rows, cols))
    os.replace(path + ".partial", path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--sheets", action="store_true")
    g.add_argument("--agreement", action="store_true")
    g.add_argument("--print-pins", action="store_true")
    ap.add_argument("--r1", nargs="+", help="--agreement: reader 1's filled sheet(s)")
    ap.add_argument("--r2", help="--agreement: reader 2's filled 150-row sheet")
    ap.add_argument("--nosymbol", help="--agreement: reader 2's filled blind sample (optional)")
    a = ap.parse_args(argv)
    if a.print_pins:
        lines = [f"{k}\t{v}" for k, v in pins_6a().items()]
        print("\n".join(lines))
        with open(P_PINS, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"(written to {P_PINS})")
        return 0
    say = Say()
    stage = "DRY RUN" if a.dry_run else ("SHEETS" if a.sheets else "AGREEMENT")
    say(f"# #705 as-is STEP 6a (machine pass) — {stage} ({time.strftime('%Y-%m-%d %H:%M')})")
    say("Guards: no network, no production server, no paid call, nothing after 2024-12-31, the seven outcome folders never opened, nothing "
        "imported from the rule folders. No rule, setup name or pattern label enters; the readers see captions only.")
    if a.agreement:
        if not a.r1 or not a.r2:
            say("--agreement needs --r1 FILE [FILE ...] and --r2 FILE")
            return 2
        r1 = [r for p in a.r1 for r in read_sheet(p)]
        res = score_agreement(r1, read_sheet(a.r2))
        agreement_report(say, res, blind_spot(read_sheet(a.nosymbol)) if a.nosymbol else None)
        say.write(P_AGREE)
        return 0 if res["joint_pass"] and res["price_pass"] else 1
    refused_to = P_DRY if a.dry_run else P_REFUSED
    hits = C.scan_identifiers([os.path.join(HERE, n) for n in ("asis_common.py", "01_points.py", "02_captions.py")])
    if hits:
        say("IDENTIFIER SCAN FAILED: " + "; ".join(f"{os.path.basename(p)}:{ln} {t}" for p, ln, t in hits))
        say.write(refused_to)
        return 2
    say("- identifier scan: clean (the step-5/6 modules hold none of the excluded names)")
    loaded = C.rule_modules_loaded()
    if loaded:
        say("RULE MODULE LOADED (guard 3): " + ", ".join(loaded))
        say.write(refused_to)
        return 2
    say("- import belt: no rule module in sys.modules")
    say("- modules: " + module_shas_line())
    if a.sheets:
        problems = sheets_gate()
        if problems:
            for pr in problems:
                say("REFUSED: " + pr)
            say.write(P_REFUSED)
            return 3
        say("- sheets gates: the dry run completed with 0 MISMATCH by these modules; every pin (inputs, modules, doc body, the dry-run printout) is below "
            "the doc's freeze marker; the ledger verifies; no sheet or side file exists")
    say("\n## Inputs")
    st = run_machine(say)
    say(inputs_line(st))
    windows_info = load_windows()
    say(f"- windows: {len(windows_info[0]):,} step-5 windows read from snapshots / entries / exits (no bar, minute or export opened)")
    if a.dry_run:
        claims = Claims(say)
        dry_report(say, claims, st, windows_info)
        say("")
        say(claims.result())
        say("DRY RUN COMPLETE")
        say.write(P_DRY)
        return 0
    # ---- --sheets ---------------------------------------------------------------------------------------------------------------------
    vmap = {s.v.id: s.v for s in st["streams"]}
    plan = build_sheet_plan(st["handread"], st["blind_pool"], vmap)
    for name, rs in plan.items():
        write_sheet(os.path.join(SHEETS_DIR, f"{name}.tsv"), rs)
    where = {r["stmt_id"]: (name, r["sid"]) for name, rs in plan.items() for r in rs if name.startswith("reader1")}
    strata_of = {x["stmt_id"]: stratum_of(x) for x in st["handread"]}
    mcols = ["stmt_id", "video", "stream_date", "t_hms", "kind", "kinds_in_cluster", "price_candidate", "shares", "dollar_result", "day_words",
             "symbols", "hits", "in_hand_read_set", "stratum", "reader1_sheet", "reader1_sid"]
    mrows = [{"stmt_id": s["stmt_id"], "video": s["video"], "stream_date": s["stream_date"], "t_hms": INV.hms(s["t"]), "kind": s["kind"],
              "kinds_in_cluster": s["kinds_in_cluster"], "price_candidate": s["price_candidate"], "shares": s["shares"],
              "dollar_result": s["dollar_result"], "day_words": s["day_words"], "symbols": ",".join(hit_symbols(s)),
              "hits": ";".join(f"{h[0]}>{h[1]}:{h[2]}:{h[3]}" for h in s["hits"]), "in_hand_read_set": in_filter(s),
              "stratum": strata_of.get(s["stmt_id"], ""), "reader1_sheet": where.get(s["stmt_id"], ("", ""))[0],
              "reader1_sid": where.get(s["stmt_id"], ("", ""))[1]} for s in st["primary"]]
    write_tsv(mrows, mcols, OUT_FILES["machine_statements"])
    man = sheet_manifest(plan, strata_of)
    for m in man:
        m["sha256"] = C.sha(os.path.join(SHEETS_DIR, m["sheet"] + ".tsv"))
    write_tsv(man, ["sheet", "rows", "tokens", "strata", "sha256"], OUT_FILES["sheet_manifest"])
    acols = ["word", "symbol", "status", "heard", "evidence_1", "evidence_2", "evidence_3"]
    arows = [{"word": w, "symbol": sy, "status": "alias", "heard": l.n, **{f"evidence_{k + 1}": e for k, e in enumerate(l.evidence)}}
             for (w, sy), l in sorted(st["alias_log"].items())]
    arows += [{"word": w, "symbol": ";".join(sorted(t)), "status": "ambiguous", "heard": "", "evidence_1": "", "evidence_2": "", "evidence_3": ""}
              for w, t in sorted(st["ambiguous_log"].items())]
    write_tsv(arows, acols, OUT_FILES["aliases"])
    windows, S = windows_info
    by_sym = index_windows(windows)
    holds = index_holds(windows)
    jrows = []
    for s in st["handread"]:
        for sym in hit_symbols(s):
            j = join_position(sym, s["stream_date"], by_sym, S)
            j["reason"] = none_reason(sym, s["stream_date"], by_sym, holds, S) if j["status"] == "none" else ""
            jrows.append({"stmt_id": s["stmt_id"], "symbol": sym, "day": s["stream_date"], "day_is": "stream_date_provisional", **j})
    write_tsv(jrows, ["stmt_id", "symbol", "day", "day_is", "status", "reason", "eid", "side", "dist", "n", "tied"], OUT_FILES["joins"])
    say("\n## Outputs")
    for name in plan:
        p = os.path.join(SHEETS_DIR, f"{name}.tsv")
        say(f"- {name}: {len(plan[name])} rows, ~{est_tokens(plan[name]):,} tokens ({C.sha(p)[:16]})")
    for p in OUT_FILES.values():
        say(f"- {os.path.basename(p)}: {C.sha(p)[:16]}")
    say("SHEETS COMPLETE")
    say.write(P_RUN)
    for stage_, path in (("step6a_dry_run", P_DRY), ("step6a_sheets", P_RUN)) + tuple((f"step6a_{k}", p) for k, p in OUT_FILES.items()):
        C.ledger_append(stage_, path)          # the dry run this was frozen on, the run, and the side files (NOT the sheets: the readers label those; the manifest holds their shas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
