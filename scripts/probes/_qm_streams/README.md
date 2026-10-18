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

Known limits: captions mis-hear tickers (MDGL is heard "mdgs"; many are lost) and ~half of the 2022 videos have no
auto-caption track at all; watch nights start 2022-03-28 so earlier talks are flagged `pre_watch_era` (C0 not assessable,
not "no base"); videos before 2021-08 have no bars (`no_bars`, text kept). Tickers that are also very common words
(AI, ON, ALL, NOW...) survive only with CAPS + a chart word. Company-name matching uses current names only.
