# _qm_streams — #702 P4b free label mining ($0: no model call, no paid data)

Goal: labelled "base" examples (ticker + date + what he said) from Qullamaggie's stream captions and Kyna Kosling's stream
notes, matched to our Consolidation Breakout watch rows. Operator ruling 2026-10-18: free steps only; the frame-reading
vision step is HELD. Data lives OUTSIDE the repo: `/Users/alvinfung/apollo_data/cb702/qm_streams/` (results: `summary.txt`).

Run order (venv with yt-dlp + certifi; set `SSL_CERT_FILE=$(python -c "import certifi;print(certifi.where())")`):

1. `fetch_transcripts.py --videos qm_videos.txt --out OUT --yt-dlp <venv>/bin/yt-dlp` — auto-caption track only
   (`en-orig`, falls back to `en`), upload date from the same call. >= 8 s between videos, exponential back-off on HTTP 429,
   resumable (`OUT/fetch_log.tsv`; ids marked ok / nocaps are skipped). No cookies: age-gated videos are logged as failures.
2. `crawl_kyna.py --out OUT` — index + every linked `/p/` post of tradingresourcehub.substack.com, >= 3.5 s apart, robots.txt
   read with our own honest user agent (not a browser string, not one of the AI-crawler names the site disallows), stops at a
   paywall. Raw HTML kept in `OUT/kyna_raw/`.
3. `extract_hits.py` — VTT -> words (`qmlib.parse_vtt` de-duplicates YouTube's rolling captions), spoken tickers validated
   against the tickers with bars within +-60 days of the upload date, collision tiers (A spoken ticker / B English-word or
   2-letter ticker needs a chart word / C very common stream word needs CAPS + chart word / N company name from the free Nasdaq
   Trader symbol files), 45 s clustering into moments, keyword flags. -> `stream_moments_raw.tsv`, `video_status.tsv`.
4. `parse_kyna.py` — post HTML -> per (post, ticker) rows with context, flags, image URLs + alt text (URLs only).
5. `match_bars.py` — watch row in the <= 28 calendar days (about 20 sessions) up to the talk date, character features of
   the last matching night, breakout-candidate existence + first entry date (no trade outcome read), base state on the talk
   day. -> `stream_moments.tsv`, `kyna_notes.tsv`, `labelled_candidates.tsv`.
6. `summarize.py` — `summary.txt` incl. the frame count and price of the HELD vision step (pricing table lookup only).

Known limits (first pass): captions mis-hear tickers (MDGL is heard "mdgs"; many are lost) and ~half of the 2022 videos have no
auto-caption track at all; watch nights start 2022-03-28 so earlier talks are flagged `pre_watch_era` (C0 not assessable,
not "no base"). Tickers that are also very common words (AI, ON, ALL, NOW...) survive only with CAPS + a chart word.
The two limits the extension below removes: "videos before 2021-08 have no bars" (Alpaca bars now cover 2016-01 .. 2022-06) and
"company-name matching uses current names only" (a hand-reviewed allowlist now adds dictionary-word names and two historical ones).

## Extension: 2016-2022 on free Alpaca daily bars (#702 P4b, 2026-10-18)

Bars were fetched by the main loop (`alpaca_all_2016_2022/{raw,split}/b*.csv.gz`, every symbol Alpaca lists, active AND inactive);
everything here is local and $0. Outputs go to `QM_DIR/ext_2016_2022/` (`summary_ext.txt` first). The first-pass scripts above are
unchanged except `match_bars.match_one`, which gained two optional arguments (defaults reproduce the old behaviour).

1. `ext_bars.py EXT` - load raw + split bars, drop forward-filled zero-volume rows (Alpaca keeps printing a dormant symbol's last close),
   identity guard per symbol (hole > 30 sessions, > 70% move without a volume event, overlap vs Polygon), data-derived rename map
   (SQ -> XYZ). A "break" excludes the NIGHTS whose 130 bars straddle it, not the whole symbol.
2. `extract_hits_ext.py --out QM_DIR --ext EXT --videos qm_videos.txt` - the first-pass extractor plus: the hand-reviewed allowlist of
   company names (`ALLOW_UNI` / `ALLOW_BI`, review record `ALIAS_REVIEW`), validation against Alpaca symbols with bars within +-60 days,
   and three precision rules (year/month words within +-10 s, "tight" next to "stop", "cruise line"). `--legacy` switches every
   addition off and reproduces `extract_hits.py` exactly (checked: 19,235 moments, 0 differing cells).
3. `ext_c0.py` (library) + `ext_match.py` - `cb.explain_watch` on Alpaca split bars for talks before 2022-03-28 (the runner's per-night
   loop, per-bar raw factor = raw close / split close), eligibility reported apart from "no base", first breakout of the base;
   talks from 2022-03-28 still use the production watch rows. -> `stream_moments_ext.tsv`, `labelled_candidates_ext.tsv`.
4. `ext_parity.py` - Alpaca-bar C0 vs the production watch table on 2022-05-02..06-30 (96% of passing nights shared, 99.9% same pole).
5. `summarize_ext.py` - `summary_ext.txt`: counts by era, eligibility, identity guard, precision (hand-read evidence in
   `hand_read_ext.tsv`, `hand_read_names.tsv`), recall table, top 40, the HELD vision step priced from `pricing_for()`.

Known limits (extension): Alpaca's asset list omits many delisted names (ABMD, TWTR, ATVI...), so a spoken ticker with no Alpaca series
cannot be matched before 2022-03-28. A reused symbol whose old issuer left before 2021-09-27 is only seen by the hole / jump tests.
`match_bars.load_watch` now keys watch rows by the runner's drift-robust chain id (`cb.chain_bases`), the same key candidates.tsv uses;
before the 2026-10-18 fix a base whose pole drifted one session read "no breakout" (first pass: 22 -> 40 of 46 labelled now find theirs).

## Step 5 - label join: which level did he draw? (#702 P4b, 2026-10-18)

`p4b_label_join.py` ($0, local files only) joins the 93 hand-drawn lines on 60 labelled bases (`vision/p4b_label_lines.tsv`, used as given)
to the C0 candidate levels on the last watch night <= the screen date: his line is converted from screen-date price scale to the bar scale
(divide by r(screen) = raw / split close), projected to the next session in session-index terms, and compared with `pivot_k5/k10/full/tl`
(from `cb.explain_watch`) plus three settled-high variants over the same window as `pivot_full` (highest close, highest body top,
second-highest high). Ties between coincident levels are kept as a set (`match_set_*pct`), never resolved by chance. Outputs in
`vision/p4b_labels/`: `labels_p4b.tsv` (one row per base), `lines_p4b.tsv` (every line), `summary_p4b_labels.txt`, `spot/*.png`.
No classes and no rule here - step 6 fits the character -> level rule from these rows. Docstring = the full definitions.
