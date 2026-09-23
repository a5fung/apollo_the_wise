# RMV Recalibration — Implementation Write-up for External Review (2026-06-27)

We replaced our **RMV (Relative Measured Volatility)** tightness indicator from a min-max
normalization to a ratio-to-baseline form, after the min-max version produced false
"maximum contraction" readings on post-runup stocks. We'd like a second opinion —
**the design choices we're least confident about are listed first.**

---

## Context — what RMV is for

Momentum/VCP trading (Qullamaggie / Pradeep Bonde methodology). RMV is a **0–100
contraction index, low = tight/coiled**, used to find Volatility Contraction Patterns:
a stock that ran up, then consolidates *tightly* (the coiled "spring"), before a
breakout. We use it as recorded telemetry and, as of this change, as the gate on a
**SHADOW** consolidation-entry signal (internal #327 — records a would-be entry, has
**zero execution authority**, not live-traded).

The indicator originates from DeepVue/TraderLion; the author describes it as comparing
"the volatility of the recent trading range against a historical lookback (default 15
bars)," with `<30` = getting tight, `<15` = very tight, `<5 or 0` = maximum contraction.

---

## The bug we fixed

**Old form — min-max normalization** over a 5-bar lookback:

```
RMV = (ATR_today − ATR_min) / (ATR_max − ATR_min) × 100
```

A single wide *runup* bar owns `ATR_max`, so any mildly quiet follow-through day gets
crushed to ~0 ("max coil"). It was flagging the **exhaust of the preceding move**, not
a real base. Empirical evidence: a 303-candidate labeling worksheet where the entire
`rmv≈0` block charted as garbage — volatile or trending, no base whatsoever.

---

## The new implementation (ratio-to-baseline, author-confirmed)

```
NTR   = gap-aware Wilder True Range ÷ close × 100      # price-level neutral
ratio = mean(NTR over last 3 bars) / mean(NTR over last 15 bars)
RMV   = clamp( (ratio − FLOOR) / (CEILING − FLOOR) × 100,  0, 100 )   # FLOOR=0.4, CEILING=1.5
```

- The 15-bar baseline is a **rolling** lookback and *intentionally* spans the prior
  runup — the runup's wide bars elevate the *average* baseline, so the recent 3-bar
  window must be **legitimately, sustainedly quiet** (not one lucky inside day) before
  the ratio drops toward the floor.
- Returns **`None` (never 0)** on insufficient history (`today_idx < 15`), a non-positive
  close, or a zero baseline (halted/frozen feed) — because 0 is a *real* max-coil signal,
  so a dead feed must not be allowed to mint a phantom one.

**Gate change:** the #327 shadow entry gate moved from `rmv_5d ≤ 40` to `rmv_15d ≤ 30`.
The new ratio form only reads "contracted" against the long baseline — the 5-bar window
overlaps the recent run and reads ~50 for a genuine coil. `30` = the author's "`<30` =
getting tight", **provisional** — our operator's hand-labeling pass calibrates the final
value. Both `rmv_5d` and `rmv_15d` are still recorded as telemetry.

---

## Design choices we're LEAST sure about — feedback wanted here

1. **FLOOR = 0.4 / CEILING = 1.5, linear map.** These are the author's suggested
   defaults (recent vol at 40% of baseline → RMV 0; 150% → RMV 100). Is a *linear* map
   between them right for daily equity bars, or should it be nonlinear to give more
   resolution in the `<15` "tight" region where entries actually live?

2. **Relative, not absolute.** This measures contraction *relative to the stock's own
   15-bar baseline*. A stock that's been uniformly quiet for 15 bars (low absolute
   range, but no prior expansion to contract *from*) scores **~55, not ~0**. That's
   correct for "consolidation *after a runup*" — but it means RMV is **not** an
   absolute-narrowness measure. Is relative-only the right semantic for VCP detection,
   or should there be an absolute-tightness floor alongside it?

3. **The recent-halt edge (verified real).** A 2–3 day trading halt (zero range, zero
   volume) sitting *inside* an otherwise-live 15-bar baseline drives `recent→0` →
   `RMV→0` — a phantom "max coil" on dead data. Our zero-baseline guard catches a
   *fully* dead window but not this partial case (the gate's range and volume checks
   also pass on a halt, so all three shadow gates fire). We're weighing a
   "recent-window-not-dead" floor (require nonzero volume **and** nonzero range in the
   recent window). **How would you separate a halt from a genuine coil without
   rejecting real coils?** (Both have small range; the distinguisher we have is volume —
   a coil rests on *reduced-but-nonzero* volume, a halt on ~0.)

4. **Threshold 30 vs the author's `<10`.** The author's *screener* surfaces coiled
   setups at `RMV < 10`, the on-chart trigger at `<8`, prime entry at `<5`. Our gate
   sits at `30` — deliberately loose so the calibration worksheet over-captures and the
   operator's labels can pull the cutoff *down* to where the real edge is. Is `30` too
   loose even as a starting point, or is over-capturing-for-labeling the right bias?

---

## Other open questions

- **NTR input.** We use gap-aware Wilder True Range (incorporates the prior close, so
  overnight gaps count) ÷ close. Right volatility primitive for equities, vs ATR or
  high-low range?
- **Windows: recent = 3, baseline = 15.** The author describes "2–4 day" tight areas.
  Is a 3-bar recent window the right choice, or should it be 2 or 4?
- **Anything structurally wrong** with the ratio-to-baseline approach for VCP/coil
  detection that we've missed?

---

*Internal context: this is a shadow (non-traded) signal; RMV otherwise serves as
recorded telemetry. The threshold and floor/ceiling are explicitly provisional and will
be calibrated from a manual labeling pass of the live candidate universe.*
