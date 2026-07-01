# Spec — ④b: Intraday/Overnight Fade Backtest

**Date:** 2026-07-01
**Status:** approved (design), pending spec review
**Sub-project:** the ACD refine sprint, lever (a) — backtest the intraday FADES.

## 1. Purpose

The full ACD bot's checkpoint (`bot/diag_full_signal.py`) showed the strongest
directional edge lives in the **mean-reversion FADES** (`failed_a`,
`failed_a_pivot`, `failed_c`) — 164 signals over the 3-yr window, +0.265%
same-day at **63% positive** (highest hit rate of any horizon) and +0.325% at
+1d (57%). But the fades were never turned into an options P&L. The multiday
macro slice was (④, `backtest_acd_full.py`) and cleared a real, cost-robust bar.

This sub-project (④b) answers: **does the fade edge survive being expressed as
options, with transaction costs — the same honest bar the multiday slice
cleared?** And secondarily: **which horizon × structure monetizes the
mean-reversion best?**

Non-goal: deploying anything. This is a rigor/measurement slice, graded by
`backtest-expert`, honestly caveated.

## 2. What we test — the 2×2 grid

The identical 164 fade signals, expressed four ways:

|              | Debit spread                                   | Long option |
|--------------|------------------------------------------------|-------------|
| **0DTE**     | enter at fade time → hold to same-day close    | "           |
| **Overnight**| enter at fade time → hold to next-day close    | "           |

- **0DTE** captures the same-day edge (63% hit). Expiry = the fade's own trade date.
- **Overnight** captures the +1d edge (+0.33%). Expiry = the **next trading day**
  (from the sorted `daily_hlc` calendar); "~1 DTE". Held to that expiry.
- **Debit spread**: long ATM, short `width` further OUT in the signal direction
  (bull call spread for a long fade, bear put for a short fade). Defined risk =
  net debit; reward capped at the width — appropriate for a bounded snap-back.
- **Long option**: single ATM option in the signal direction (call if long, put
  if short). Risk = premium; uncapped reward — captures a bigger reversion.
  Shares the ATM leg's contract with the debit spread (no extra pull).

### Faithfulness to the checkpoint
The checkpoint measured the edge as the direction-adjusted **underlying** move
from the fade's **intraday** entry level. So both horizons **enter at the fade's
intraday entry time** (not at EOD). Overnight exits at the next-day close =
exactly how the checkpoint's +1d was measured.

## 3. Architecture — reuse the existing seam

The fade signals already exist: `build_history()` (`diag_full_signal.py`) →
`apply_macro(day.day_result.setups, ctx)` → filter to the `FADES` set
(`acd_options.FADES = {"failed_a","failed_a_pivot","failed_c"}`). Each `Setup`
carries `name, direction, entry_time (HH:MM), entry_price (underlying level),
conviction`. What's missing is the intraday pricing/marking + the driver.

### Components

**1. `bot/acd_fade_pricing.py`** — pure pricing/exit for *debit* structures
(offline `__main__` self-tests on mock bars; no network):
- `spread_entry(long_bars, short_bars, entry_time) -> (debit, entry_t)` — net
  debit at the first fillable bar with `time >= entry_time`:
  `long.ask - short.bid`. For the long-option case (no short leg) → single-leg
  `ask`. Raises if no bar at/after entry_time.
- `expire_value(structure, settle) -> float` — intrinsic per share at expiry:
  - bull call spread: `clamp(settle - long_strike, 0, width)`
  - bear put spread:  `clamp(long_strike - settle, 0, width)`
  - long call: `max(settle - strike, 0)`
  - long put:  `max(strike - settle, 0)`
- `exit_target_stop(structure, debit, close_series, settle, target, stop)` — the
  debit sibling of `orb_exits.exit_target_stop`, walking the 0DTE minute
  cost-to-close series (`long.bid - short.ask`); first bar to hit
  `profit >= target*debit` or `loss >= stop*debit` ends it, else fall back to
  `expire_value` at the close. Used ONLY for the 0DTE exit-comparison.

P&L for one contract = `(exit_value - debit) * 100`; return = P&L / max_loss,
where `max_loss = debit * 100` (both structures are debit-paid → risk = debit).

**2. `bot/pull_fade_data.py`** — resumable background pull. For each of the 164
fades, pull the leg contracts' **intraday 1-min bars** via
`load_ivol_intraday.fetch_option_minutes`:
- 0DTE: ATM (long/long-option) + width-OTM (short), expDate = fade date.
- Overnight: ATM + width-OTM, expDate = next trading day.
~4 contracts × 164 ≈ **650 pulls ≈ 12 min** at the 1.1s/req cap. Cache-skips
already-pulled contracts (like `pull_acd_data.py`). Logs progress to
`results/fade_pull.log`. After this runs once, the backtest is fully offline.

**3. `bot/backtest_acd_fades.py`** — the ④b driver (offline on cache):
- Build the fade signal list (as above).
- For each fade × each of the 4 grid cells: snap strikes off `entry_price` on
  the $5 grid (ATM long via `orb_rules.nearest`; short = ATM ± width in the
  signal direction), read cached leg bars, compute entry debit, settle via
  `expire_value` at the horizon's underlying close (from `daily_hlc`).
- P&L, return-on-risk; drop degenerate positions (zero/inverted debit, missing
  bars) with a counter (like `backtest_acd_full`'s `dropped`).
- **Report** per cell: n, win rate, total-on-risk, maxDD, risk-adj (total/|maxDD|),
  Sharpe, **slippage sweep** (0/5/10/20¢ per leg, haircut entry+exit) — mirroring
  `backtest_acd_full.report` / `_with_slip` / `_stats`.
- **0DTE exit comparison:** hold-to-close vs `exit_target_stop` (re-tests the
  recurring "hold-to-horizon beats tight stops" lesson).

**4. Grade** the results via the `backtest-expert` skill; write the eval to
`results/backtest_fades_eval_*.md`.

### Reuses (no new copies of)
`build_history` (`diag_full_signal`), `apply_macro`/`macro_context`
(`acd_macro`), `FADES` (`acd_options`), `nearest` (`orb_rules`),
`fetch_option_minutes`/`normalize_minutes` (`load_ivol_intraday`),
`daily_hlc` (`run_acd_signal`), `max_drawdown` (`backtest`), and the
`_with_slip`/`_stats`/report shape from `backtest_acd_full`.

## 4. Data flow (one fade, one grid cell)

```
fade Setup (date, entry_time, entry_price=underlying level, direction)
  -> long_strike = nearest($5 grid, entry_price)                 [ATM]
     short_strike = long_strike ± width   (+ for long call spread, − for bear put)
  -> exp_date = fade_date (0DTE) | next trading day (overnight)
  -> cached intraday bars for each leg (symbol, fade_date, exp_date, strike, type)
  -> debit = spread_entry(long_bars, short_bars, entry_time)     [real NBBO @ entry minute]
  -> settle_px = daily_hlc[exp_date] close                       [cached underlying]
  -> exit_value = expire_value(structure, settle_px)
  -> pnl = (exit_value − debit)*100 ;  ret = pnl / (debit*100)
```

## 5. Honesty caveats (logged in the eval, not hidden)

- **Settle-at-intrinsic** assumes hold-to-settlement — ignores pin risk / early
  assignment. Same assumption ORB's `exit_expire` used (which graded
  cost-robust). SPX daily options are PM-settled at the close → intrinsic vs the
  cached SPX close is correct.
- **Entry fills** use the real NBBO bid/ask at the entry minute; the slippage
  sweep stress-tests worse fills both ways.
- **Still SPX-only, ~3 yrs.** The overfitting / data-length flags from the
  multiday grade carry over — do NOT over-claim. The fade *policy* (structures,
  widths, target/stop) adds tunable params; report robustness across the grid
  and years, not a single curve-fit cell.
- Underlying edge ≠ option P&L is exactly what this slice measures; a positive
  checkpoint does not guarantee a positive options result.

## 6. Success criteria

- All 4 grid cells produce honest per-cell metrics + a slippage sweep, offline
  on cache, self-tests green.
- A `backtest-expert` grade with the same rigor lens as the multiday slice.
- A clear, honest verdict: does the fade edge survive as options-with-costs, and
  which horizon×structure (if any) is the best expression — or is it a
  rigorously-tested negative. Either outcome is a real result.

## 7. Testing

- Each new module: inline `__main__` assert self-tests on mock minute bars
  (house style; no pytest) BEFORE any real pull — `spread_entry` picks the right
  bar and nets the debit; `expire_value` intrinsic correct for all 4 structures
  (incl. clamps); `exit_target_stop` honors target/stop/expiry fallback.
- The driver validates at the data seam: skip NaN/zero/inverted debits, missing
  bars, `entry_price<=0`; count drops.
- Opus whole-branch review before merge.

## 8. Out of scope (possible follow-ups)

- Active multi-day management of overnight positions (needs next-day intraday
  quotes) — overnight = hold-to-expiry only here.
- 2+ DTE / longer overnight holds beyond the next trading day.
- Running the instrument-agnostic engine on a trending market (lever d).
- Walk-forward / out-of-sample across more years (lever c) — needs a data pull.
