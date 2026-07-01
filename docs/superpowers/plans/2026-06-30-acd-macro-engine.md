# ACD Macro Engine — Implementation Plan

> REQUIRED SUB-SKILL: subagent-driven-development / executing-plans. Checkbox steps.

**Goal:** `bot/acd_macro.py` — the multi-day macro layer that filters+sizes the Micro Engine's setups and adds its own macro setups, per spec `docs/superpowers/specs/2026-06-30-acd-macro-engine.md` and `strategies/ACD.md` Part D.

**Architecture:** Pure functions over a chronological `list[DayEntry]` (daily OHLC + `acd_micro.DayResult`), producing a `MacroContext` per day + `apply_macro(setups, ctx)`. No lookahead (uses days ≤ i). Reuses `acd_micro.Setup`. Inline `__main__` tests. Built in two commits: **(A) context+filters**, then **(B) macro setups**.

## Global Constraints
- Flat `bot/` module, run `.venv/bin/python bot/acd_macro.py`, inline asserts (no pytest).
- Number line: score +4/-4 (C held & close beyond OR), +2/-2 (A held & close beyond OR), else 0. 30-day cum; ±9 (2 days) = trend; |cum|<4 = chop.
- Chop filter: in chop/confused, DROP breakout setups, KEEP fades (failed_*). Regime gate: drop direction-fighting setups in a clear trend. Confluence: +1 conviction per agreeing macro signal, cap 5.
- Pivot MAs 14/30/50 of daily pivot (H+L+C)/3, regime by slope. Momentum = sign(close[i]-close[i-8]).
- Reversal Trade: two same-dir held A's (≤3 neutral days between, no intervening A/C), then opposite held A beyond the pair's extreme. Sushi: latest-5 take out prior-5 high&low and close beyond the prior-5 extreme.

---

### Task A: context + filters (one commit)
**Create `bot/acd_macro.py`.** `DayEntry`, `MacroContext`; `score_day`, `_cum`, `number_line_state`, `plus_minus`, `daily_pivot`, `pivot_ma_regime`, `momentum`, `macro_context(i, history)` (context only, macro_setups=[]), `apply_macro(setups, ctx)`. Inline tests: number line → trend_up over a +ve sequence; chop sequence → chop and apply_macro drops breakouts / keeps fades; each PMA regime; momentum flip; plus/minus. Commit `feat(acd-macro): context + filters (number line, chop filter, PMAs, momentum, sizing)`.

### Task B: macro setups (one commit)
**Modify `bot/acd_macro.py`.** `reversal_trade(i, history)`, `trt(i, history)`, `sushi(i, history)`; wire into `macro_context.macro_setups`. Inline tests: a two-A_up-then-lower-A_down sequence → reversal_trade short; a bearish sushi roll (latest-5 engulf + close below prior-5 low) → sushi. Commit `feat(acd-macro): macro setups (reversal trade, TRT, sushi)`.

## Self-Review
Covers spec Part A (score/number-line/plus-minus/PMAs/momentum/integrator = Task A) and Part B (reversal/TRT/sushi = Task B). No placeholders — exact rules fixed in ACD.md/spec; authored + unit-tested at build time.
