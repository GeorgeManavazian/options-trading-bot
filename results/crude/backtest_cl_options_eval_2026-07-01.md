# Eval — ACD Crude Oil, Phase 2: same-day options overlay

**Date:** 2026-07-01
**Branch:** `acd-crude-options` (worktree)
**What:** the phase-1 same-day crude signals expressed as directional debit spreads on real Databento NBBO (`bbo-1m`), 16 years, both exits. Raw: `results/backtest_cl_options_raw_2026-07-01.txt`; grade: `results/backtest_eval_2026-07-01_194809.*`. (Exit proceeds floored at 0 — see caveats — so per-trade loss caps at −100%, economically correct for a debit spread.)

---

## Verdict: NEGATIVE — the edge does NOT survive as same-day options. Do not deploy.

The full ACD signal has a strong, cost-robust edge on the crude **underlying** (phase 1: same-day +1043% on risk, 64% win, 79/Deploy). Expressed as **same-day debit spreads**, it **loses money** — decisively, both exits, catastrophically with realistic slippage.

| Metric (hold-to-close, the better exit) | Value |
|---|---|
| Trades | 1,962 (of 2,556 signals; **594 = 23% unpriceable**, illiquid options) |
| Win rate | **35%** (was 64% on the underlying) |
| Avg win / avg loss | +28.5% / −16.8% |
| **Profit factor** | **0.91** (< 1 → loses) |
| Expectancy | **−0.98% per trade** |
| Total on risk | **−1,906%** (active exit: −2,774%) |
| Max drawdown | 2,897% of per-trade risk |
| Slippage 1¢/leg | far worse (edge is nowhere near cost) |

By family (hold-to-close, 0 slip): **breakouts PF 0.76 (−2,428%)** — the worst, despite a real signal edge; **fades PF 1.05 (+522%)** — marginally above water at zero cost only, and dies with any slippage.

## Why it fails (this is exactly the phase-1 caveat, confirmed)
The signal predicts a **small** same-day move (~0.4% on the underlying). A debit spread costs premium + a **wide crude-option bid/ask spread**; entering at the ask and exiting at the bid, that spread cost is large relative to the small intraday move. So a correct directional call frequently still loses after costs — win rate collapses 64% → 35%. The 23% drop rate is itself a finding: crude options are too thin intraday to fill a chunk of the signals at all.

## On the grade (honest note)
`backtest-expert` scored **60/100 "Refine"** — but that number is **inflated by the rigor dimensions** (Sample 20/20 for n=1,962, Robustness 20/20 for 16 years, Execution 20/20 for real NBBO + slippage tested). The dimensions that matter here scored **0/20 (Expectancy) and 0/20 (Risk Management)**, and it raised **two 🔴 red flags: negative expectancy and catastrophic drawdown**. The honest reading of that output is **ABANDON this expression**, not "refine" — the grader rewards a well-run test even when the strategy loses.

## What this means (the value of a "no")
- **Signal edge ≠ options edge — proven, not just warned about.** The same-day horizon is the *worst* case for options: the move is too small to clear the premium + spread.
- **The signal itself is still real and strong** (phase 1). The deployable vehicle is **not** same-day options.

## Recommended next steps
1. **Trade the underlying, not options.** The signal's +1043% lives on the crude *future*. On a small account the clean vehicle is a **micro WTI future (MCL, 1/10 of CL)** — directional, no premium/spread drag, no theta. This is the most promising deployable path and worth a dedicated backtest (futures P&L + realistic futures commission/slippage, which phase 1 already showed survives).
2. **Multi-day breakout-trend overlay (deferred "phase 2b").** Breakouts *trend* on crude (phase 1: edge grows to +5 days). A longer-dated option held several days lets a **bigger** move cover the option cost — the one options angle that might work. Cheaper daily futures-options data (IVolatility) suffices.
3. **Do NOT** pursue same-day crude debit spreads further.

## Honesty caveats
- Fills are **real NBBO** (`bbo-1m`), buy-ask/sell-bid; the slippage sweep only makes it worse — so this is not a pessimistic-assumptions artifact, it's the honest picture.
- Signal params are a-priori (phase-1 CL spec, untuned); tuning the *signal* wouldn't fix a structure that pays more in spread than the move is worth.
- Same-day exit = last quoted ET bar, not an official settle (reasonable for a same-day exit).
- **Exit proceeds floored at 0** (a debit spread's worst case is letting it expire, value ≥ 0; you'd never sell for a negative amount on a crossed close). This caps per-trade loss at −100%, which is economically correct; it made the total slightly *less* bad (−2,234% → −1,906%) and does not change the verdict. Caught by the whole-branch review.
- Opus whole-branch review **confirmed the negative is real, not a pricing bug** — reproduced the numbers from cache and verified entry/exit/direction/drop logic.
- This is a rigorously-tested **negative** — as publishable as phase-1's positive. It's what keeps the project honest.
