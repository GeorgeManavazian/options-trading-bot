# Spec — Fade Drawdown Bake-Off (variant harness)

**Date:** 2026-07-01
**Status:** approved (design), pending spec review
**Sub-project:** ACD refine sprint — harden the ④b fade edge by reducing its drawdown.

## 1. Purpose

The ④b backtest found a real, cost-robust fade edge, but ONLY as **debit spreads**,
and graded 61/100 REFINE with one dominant red flag: **catastrophic drawdown**
(~720–900% of one trade's risk capital). Diagnostic findings that shape this work:

- The drawdown is **~8× one trade's risk** — scary in risk-units, but ~8% of the
  account at disciplined ~1%/trade sizing. It is a *sizing/path* problem, not a blow-up.
- It is **time-concentrated**: the worst 0DTE window is 2026-03-11 → 2026-04-15, and
  2026 is the only losing year (−194% vs +2209% in 2024, +3192% in 2025).
- **`failed_a` is the workhorse** (~57% win, ~80–90% of profit). **`failed_c`** (the
  no-price-stop "treacherous" fade Fisher flags) is low-quality — 40–44% win, and it
  LOSES on the overnight horizon (−203%).

**Goal:** race a curated set of drawdown-reduction *variants* of the debit-spread fade
strategy on one offline backtest and identify which fix (or combination) most improves
**risk-adjusted return and year-by-year robustness** — NOT raw total return.

Non-goal: deploying. This is a measurement slice; a walk-forward comes later (lever c).

## 2. How we judge (the anti-lottery rule)

**Winner = highest risk-adjusted return (total ÷ |maxDD|), cross-checked by year-by-year
consistency and slippage survival.** Raw total is shown but does NOT decide — it is the
metric that crowned the +7844% lottery ticket; picking by biggest number repeats that
mistake. A variant that wins only by dodging the 2026 window will show a one-year-
concentrated year row and is rejected regardless of total.

**Selection-bias honesty:** we test ~8 variants and pick the best, which is mild
overfitting by construction. Mitigants: (a) every variant is *a-priori motivated*, not a
knob sweep; (b) per-year + slippage robustness must hold, not just aggregate DD; (c) the
writeup states the winner still needs an out-of-sample/walk-forward test before trust.

## 3. Scope — the base

The base strategy is the **debit-spread** expression of the fades (the deployable form;
long options are excluded — they're the lottery tickets). Both horizons (0DTE, overnight)
are in play as a switch. All variants are built OFFLINE from the already-cached data via
the existing `collect_fades` / `grid_cells` / `price_cell` (④b), which already computes
both the hold-to-expiry P&L (`pnl0`) and the 0DTE active target/stop P&L (`pnl0_ts`).

## 4. The switches (composable fixes)

Each variant is a config over four independent switches. Each has a reason to work.

1. **Filter (which fades):**
   - `all` — failed_a + failed_a_pivot + failed_c
   - `no_failed_c` — drop the treacherous no-stop fade (a-priori: Fisher flags it; it's
     the weakest sub-type, negative overnight)
   - `failed_a_only` — just the workhorse (~85% of profit)
2. **Exit (when to get out):**
   - `hold` — hold to expiry (uses `pnl0`); works for both horizons
   - `active` — take-profit/cut-loss on the 0DTE minute series (uses `pnl0_ts`); the 5×-DD-
     cut lever. **Only defined for 0DTE** (no next-day intraday data for overnight); for an
     overnight trade, `active` falls back to `hold`.
3. **Sizing (how much to bet — a per-trade weight applied before summing the equity curve):**
   - `flat` — weight 1 each (current behavior)
   - `conviction` — weight ∝ setup conviction (failed_a_pivot conv 2 > conv 1); Fisher confluence
   - `throttle` — anti-martingale: after `k` consecutive losing trades, halve the weight
     until the next win (default k=2, floor 0.5×). Directly de-risks losing streaks.
   - **Normalization:** every sizing rule's weights are rescaled so the variant's **mean
     weight = 1.0**, so variants are compared on *path shape* at equal average exposure —
     not on leverage. (Throttle still helps: it shifts the same average exposure away from
     cold streaks toward the rest.)
4. **Diversify (horizons):**
   - `single` — one horizon (0DTE by default; overnight available)
   - `blend` — take BOTH the 0DTE and overnight trade for each qualifying fade as separate
     positions in one equity curve (two partly-independent streams smooth each other)

## 5. The variant lineup (~8 + reference)

Isolate each switch first, then the combos worth betting on together:

| # | filter | exit | sizing | horizons | why |
|---|---|---|---|---|---|
| V0 | all | hold | flat | 0DTE | reference (current 0DTE debit spread) |
| V0b | all | hold | flat | overnight | reference (current overnight) |
| V1 | no_failed_c | hold | flat | 0DTE | filter effect alone |
| V2 | all | active | flat | 0DTE | exit effect alone (the 5× DD cut) |
| V3 | all | hold | throttle | 0DTE | streak-throttle sizing alone |
| V4 | all | hold | flat | blend | diversification effect alone |
| V5 | no_failed_c | active | flat | 0DTE | cut bad fade + smooth exit |
| V6 | no_failed_c | hold | flat | blend | cut bad fade + diversify |
| V7 | no_failed_c | active | throttle | blend | the "everything" combo |

(Conviction sizing is a weak lever here — only ~17 pivot fades — so it is available as a
switch and reported, but not given its own headline row unless V-series results motivate it.)

## 6. Architecture

One new file, reusing ④b end-to-end. No new data, no network.

- **`bot/backtest_fade_variants.py`** — the bake-off harness:
  - `collect_fade_trades()` — build the richly-tagged debit-spread trade list once:
    for each `(date, setup)` from `collect_fades()`, for each `debit_spread` cell from
    `grid_cells(...)`, call `price_cell(...)` and emit
    `{date, name, conviction, horizon, nlegs, max_loss, pnl_hold (=pnl0), pnl_active (=pnl0_ts or pnl0)}`.
    Drops (None) are counted. Memoized so all variants share it.
  - `Variant(filter, exit, sizing, horizons)` config + `apply_variant(trades, variant)` →
    the ordered, weighted per-trade return series (filter → pick horizon(s) → pick pnl by
    exit → weight by sizing, mean-normalized → sort by date).
  - `weighted_returns(trades_with_weights, slip=0.0)` — per-trade return
    `= (pnl − slip·nlegs·2·100)/max_loss · weight` (same haircut formula as ④b's
    `_with_slip`, but weight-aware, since `_with_slip` can't see per-trade weights).
  - `score(returns)` — reuse `_stats`/`max_drawdown`: n, win%, total, maxDD, risk-adj
    (total/|maxDD|), Sharpe; plus per-year totals and risk-adj recomputed at 10¢ slippage.
  - `report(lineup)` — one scoreboard, one row per variant, **ranked by risk-adj**, with a
    per-year block and the slippage column; prints the anti-lottery + selection-bias notes.
- **Reuses:** `collect_fades`/`grid_cells` (acd_fade_signals), `price_cell` (backtest_acd_fades),
  `daily_hlc` (run_acd_signal), `_stats` (backtest_acd_full), `max_drawdown` (backtest).
  The weighted slippage haircut mirrors `_with_slip`'s formula but is computed locally
  (weight-aware); `_with_slip` itself is not reused.

## 7. Slippage in the weighted world

Per-trade slippage haircut = `slip × nlegs × 2 × 100` dollars (as in ④b), converted to a
return hit `= haircut / max_loss`, then multiplied by the trade's normalized weight before
summing — so the slippage column is consistent with each variant's sizing. Report risk-adj
at 0¢ and 10¢; a variant whose risk-adj collapses at 10¢ is not cost-robust.

## 8. Success criteria

- One offline scoreboard ranking all variants by risk-adjusted return, with per-year and
  10¢-slippage columns, self-tests green.
- A clear, honest verdict: which fix (or combo) best improves risk-adjusted return AND
  year-by-year robustness over the V0/V0b references — or, if none beat the base on the
  steady-kid metric, that honest null result.
- The winner (if any) logged with the explicit caveat that it needs a walk-forward test next.

## 9. Testing

- Inline `__main__` assert self-tests (house style; no pytest) on a small synthetic trade
  list BEFORE relying on the real run: `apply_variant` filters/weights correctly (e.g.,
  `no_failed_c` removes failed_c; `throttle` halves weight after 2 losses then restores;
  mean-normalization gives mean weight 1.0); `active` uses `pnl_active` for 0DTE and falls
  back to `hold` for overnight; `blend` includes both horizons.
- Validate at the seam: skip trades with `max_loss <= 0`; count drops.
- Opus whole-branch review before merge.

## 10. Out of scope (follow-ups)

- Walk-forward / out-of-sample of the winning variant (lever c) — needs more years.
- Blending the fades with the multiday macro edge (portfolio-level diversification).
- The "condor on ACD chop days" idea (separate queued sub-project).
- Account-level dollar sizing / Kelly — this slice compares *path shape* at equal average
  exposure; converting to a dollar sizing policy is a later step.
