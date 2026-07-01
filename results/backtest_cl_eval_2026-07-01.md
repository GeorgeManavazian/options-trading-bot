# Eval — ACD on Crude Oil (CL), Phase 1 (signal only)

**Date:** 2026-07-01
**Branch:** `acd-crude-oil-bot`
**Engine:** the full, unmodified ACD signal engine (`acd_micro` + `acd_macro`), run on crude via a new `InstrumentSpec` (`acd_cl.CL`) + Databento loader (`load_cl_databento`) + driver (`backtest_acd_cl`).
**Data:** Databento CME `GLBX.MDP3`, `CL.c.0` continuous front-month, **1-min + daily, 2010-06-07 → 2026-06-26** (3,969 trading days). Raw output: `results/backtest_cl_raw_2026-07-01.txt`; grade JSON/MD: `results/backtest_eval_2026-07-01_153524.*`.

---

## Headline verdict

**The full ACD method has a real, cost-robust directional edge on crude — and, decisively, the BREAKOUT half (dead on SPX) works here and TRENDS.** This is the first time the breakout third of the strategy has shown profitability anywhere, and it validates the instrument-agnostic thesis (and Fisher's original design intent: ACD is for trending markets).

- `backtest-expert` grade: **79/100 = DEPLOY, ZERO red flags** — the project's best (every SPX slice was 55–61 and tripped the >50%-drawdown flag). Dimensions: Sample 20/20, Robustness 20/20, Execution 20/20, Expectancy 9/20, Risk-Mgmt 10/20.
- Best config = **same-day hold** (enter at the signal's intraday level, exit same-day close): **+1044% on risk, 64% win, risk-adj +31.78, PF 2.19**, positive in **16 of 17 calendar years** (only partial-2026 negative), survives slippage to **5 ticks/side** (+635%).

## The breakout result (the reason we did this)

| Family | n | win | avg win | avg loss | PF | same-day total | +5d total |
|---|---|---|---|---|---|---|---|
| **Breakouts** | 1110 | 54.8% | 1.07% | 0.95% | **1.37** | **+176%** | **+444%** |
| Fades | 1442 | 70.7% | 1.24% | 0.95% | **3.18** | +869% | +774% |

- **Breakouts on SPX were ≈flat (no edge).** On crude they are **positive (PF 1.37)** and — unlike the fades — their edge **GROWS with horizon** (+0.16% same-day → +0.40% at +5d): textbook trend-continuation. This is the qualitative signature ACD predicts on a trending instrument.
- **Fades still work** (PF 3.18) and mean-revert (best same-day, decays with horizon) — consistent with the SPX fade edge. Crude has BOTH a trend engine (breakouts) and a mean-reversion engine (fades), and the full method captures both.
- **Macro (reversal/trt/sushi)** are weak here (same-day 22% positive; build to +0.19%/53% at +5d) — the weakest family on crude; not a phase-2 priority.

## Per-year robustness (same-day hold, % on risk)

Positive every year 2010–2025 (range +23% to +164%); only **2026 (−17%, partial year + Databento-flagged missing Feb days)** is negative. Spans the 2014–16 oil crash, the 2020 negative-price shock, and the 2022 spike — no single regime carries it. This is why Robustness scored 20/20 and no red flag fired.

## Cost robustness

Slippage sweep (same-day): 0t +1044% / 1t +963% / 2t +881% / **5t +635%** (risk-adj +31.78 → +16.40). Edge survives realistic futures friction with room to spare (5 ticks = $50/contract round-trip on a ~$76 underlying).

---

## Honesty caveats (do NOT over-claim)

1. **Signal ≠ options P&L.** Phase 1 trades the *underlying future* and measures the directional edge only. This is a green light for phase 2 (the crude options overlay), NOT a deployable options strategy. The SPX arc taught exactly this: a positive underlying signal does not guarantee a positive options result after structure + theta.
2. **Params were A-PRIORI, not tuned.** `a_pct=0.25% / c_pct=0.30%` were set by scaling the SPX anchors up for crude's higher vol — NO optimization/sweep was run on crude. This is a genuine strength (the 79/Deploy is not curve-fit), but it also means the numbers are un-optimized; a tuning sweep is a future option (and would then owe a walk-forward, like the standing V5 debt).
3. **Metric convention.** "% on risk" sums per-trade directional returns (not compounded), identical to every prior SPX slice — so risk-adj (total/|maxDD|) is the comparable figure, not the raw total.
4. **Raw continuous contract.** `CL.c.0` is raw front-month (Databento does not back-adjust); the loader detects and **skips contract-roll days** (instrument_id change) so a roll gap can't fabricate a signal. Minor residual artifacts possible.
5. **2026 is partial + degraded.** Data runs to 2026-06-26 and Databento flagged several 2026-Feb days as missing; discount the −17% 2026 figure accordingly.
6. **Hold horizon matters.** Same-day gives the best risk-adjusted return (+31.78); longer holds raise total but grow drawdown faster (+1d +10.13, +5d +6.48) because the fades mean-revert intraday. Breakouts alone would favor a longer hold (they trend); a family-specific hold is a phase-2 refinement.
7. **Grader scope.** `backtest-expert` scores summary stats; "Deploy" here means "the signal decisively cleared the rigor bar," not "trade real money now." Phase 2 (options), a tuned+walk-forward pass, and paper trading are still owed before any capital.

## Recommendation

**GO to phase 2: build the crude options overlay.** The signal is the strongest and most robust the project has produced, the breakout half is finally alive, and the edge is cost-robust across 16 years and multiple regimes. Phase-2 data (daily futures options) is available from IVolatility's Data Download (possibly within the free allowance) or Databento. Keep the same honesty bar: signal edge ≠ options edge until backtested with structure + costs.
