# ACD Full Bot — Sub-project ③: The Options Overlay (Design Spec)

**Date:** 2026-07-01
**Status:** Approved (design) — pending plan
**Consumes:** micro/macro `Setup`s (from ①②) + an option chain. **Reuses:** `bot/acd_wrappers.py`.
**Build order:** ①✅ → ②✅ → CHECKPOINT✅ (edge confirmed: fades + high-conviction + macro reversals) → **③ (this)** → ④ Backtest.

## Purpose
Map each edge-bearing ACD `Setup` (`direction, conviction, horizon, setup-name`) to an option
**Position** via a **pluggable Policy** — the layer that expresses the strategy as options
(the "options improve risk/return over stock" thesis). It does not pull chains or compute P&L (④).

## Success criteria
- `express(setup, puts, calls, spot, expiration, policy) -> Position` reusing `acd_wrappers.build_*`.
- The Policy chooses structure + DTE-target by signal type/conviction/horizon; swappable so ④ can sweep.
- `size_position(...)` scales contracts with conviction (Fisher's "maximize size on confluence").
- Instrument-agnostic; offline-testable on a mock chain.

## Non-goals
- Chain pulling, expiration selection from `dte_target`, daily marking, P&L, costs → all ④.

## Structures (reused from `acd_wrappers.py`)
`build_long_option`, `build_debit_spread(width=)`, `build_credit_spread(short_otm=, width=)` — each
returns the uniform `{wrapper, direction, expiration, legs, entry_cost, max_loss, width}`.

## The Policy (default = what the checkpoint said has edge)
```
FADES     = {failed_a, failed_a_pivot, failed_c}            # our strongest edge (mean-reversion)
MACRO     = {reversal_trade, trt, sushi}                    # multi-day edge
BREAKOUTS = everything else (a_held, a_through_pivot, c, c_through_pivot, late_day_c, first_hour)
```
| Signal class | structure | DTE target |
|---|---|---|
| FADE | `debit_spread` (near-ATM, defined risk) | horizon: intraday→0, overnight→2 |
| MACRO, conviction ≥ 3 | `long_option` (leverage the multi-day move) | 30 |
| MACRO, conviction < 3 | `debit_spread` | 30 |
| BREAKOUT (weak on SPX) | `credit_spread` (harvest theta, don't bet direction) | horizon: intraday→0, overnight→2 |

- `horizon_of(setup)` = "multiday" if setup name in MACRO else `setup.horizon`.
- Policy fields: `dte_intraday=0, dte_overnight=2, dte_multiday=30, fade_structure, breakout_structure,
  macro_high_structure, macro_low_structure, high_conv=3, debit_width=25, credit_short_otm=10, credit_width=25`.

## Sizing
`size_position(max_loss, account, risk_pct, conviction, max_conviction=5)` → reuse `sizing.position_size`
with the risk fraction scaled `risk_pct * (0.4 + 0.6 * conviction/max_conviction)` (40%–100% of the cap
by conviction). Tunable.

## Output
The wrapper `Position` dict + metadata: `setup`, `conviction`, `horizon`, `dte_target`.

## Testing (inline `__main__`, mock chain)
Assert: a fade → `debit_spread` intraday dte 0; a high-conviction `reversal_trade` → `long_option`
multiday dte 30; a low-conviction `sushi` → `debit_spread`; an `a_held` breakout → `credit_spread`;
`size_position` gives more contracts at conviction 5 than at 1.

## Honest flags
- The default structure/DTE map is a **principled starting policy, tunable/sweepable in ④** — not claimed optimal.
- Weak breakouts on SPX are expressed as premium (credit spread); on a trending instrument the policy
  would likely make them directional. That's a policy sweep, not an engine change.
