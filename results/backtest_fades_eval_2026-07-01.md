# ④b Fade Backtest — Evaluation (2026-07-01)

**Strategy:** the 164 ACD FADE signals (failed_a / failed_a_pivot / failed_c —
mean-reversion), expressed as options across a 2×2 grid: {0DTE, overnight ~1-DTE}
× {debit spread, long option}. Enter at the fade's intraday time (real NBBO
minute bars); settle at each option's expiry via the cached underlying close.
Data pull: 652/652 leg-contracts, 0 failures. Backtest: 652 trades, 4 dropped.

## Headline (read the distribution, not the totals)

| cell | n | win | median trade | total on risk | top-5 share | maxDD | @20¢/leg |
|---|---|---|---|---|---|---|---|
| 0DTE / debit_spread | 162 | 51% | **+5.2%** | +5180% | 44% | 796% | +3392% |
| overnight / debit_spread | 164 | 51% | **+25.1%** | +2606% | 40% | 882% | +1319% |
| 0DTE / long_option | 162 | 45% | **−25.3%** | +7844% | 47% | 897% | +7182% |
| overnight / long_option | 164 | 45% | **−44.1%** | +6913% | 49% | 718% | +6614% |

**The big totals are a fat-tail mirage.** The long-option cells post the largest
totals (+6913–7844%) but the MEDIAN long-option trade LOSES (−25% to −44%), and
~half the entire return comes from the top 5 trades (best single trade +1393%).
That is a lottery-ticket payoff — buy cheap near-expiry options, most expire near
worthless, a handful explode. Not repeatable, not deployable.

**The debit spreads are the real, defensible result.** Positive MEDIAN trade
(+5% 0DTE, +25% overnight), 51% win, avg win > avg loss, far less
tail-concentrated, and they SURVIVE the slippage sweep through 20¢/leg. This is
a genuine, cost-robust fade edge — the project's second (after the multiday
sushi slice).

## backtest-expert grade

All four cells: **61/100 → REFINE** (a notch above the multiday slice's 55/100).
Two HIGH red flags, shared by every cell:
- 🚩 **Catastrophic drawdown** ~720–900% of one trade's risk capital → the path
  is savage; only viable at ~1% of account per trade (same lesson as the
  multiday slice's 743%).
- 🚩 **Only 3 years** (< the 5-yr minimum) — data-length / regime flag.

**Grader blind spot (important):** the score is computed from summary stats
(win rate, avg win, avg loss), which do NOT capture the median-loses /
top-5-carry tail concentration. So the grader rates the long-option lottery
cells the same 61 as the healthy debit spreads. The distribution — not the
grade — is what disqualifies the long options.

## Honest caveats (carry-over + new)

- **Return-on-risk inflates on small denominators.** "Total on risk" sums
  per-trade P&L ÷ (small) debit; it is NOT an account return. Size tiny.
- **Settle-at-intrinsic** assumes hold-to-settlement, entry filled at the quoted
  NBBO at that minute — optimistic; the slippage sweep stress-tests worse fills
  (debit spreads hold up; long options barely move because their return is
  tail-driven, not spread-driven).
- **`_with_slip` charges an exit fill on hold-to-expiry** (SPX cash-settles with
  no closing trade) → OVERSTATES cost / understates edge. Conservative/safe.
- **Still SPX-only, ~3 yrs, tunable params** (fade width, ATM snap, horizon,
  structure) — overfitting/data-length flags from the multiday grade carry over.

## Exit comparison (0DTE, hold vs active target/stop)

- hold-to-close: 48% win, +13024%, maxDD **1638%**
- target/stop (50%/50%): 72% win, +8217%, maxDD **323%**

Nuance vs the multiday "hold-to-horizon beats tight stops" lesson: for the 0DTE
fades, an active target/stop CUT drawdown ~5× and lifted the win rate to 72% at
the cost of total return. Because 0DTE tails cut both ways, banking gains early
smooths the path here — the opposite of the multiday case. Worth a proper test.

## Verdict

**A real, cost-robust fade edge exists — but only in the DEFINED-RISK DEBIT
SPREAD form.** The long-option expression is an un-deployable jackpot machine
(median trade loses). Best single cell = **overnight/debit_spread** (highest
median +25%, least tail-dependent) or **0DTE/debit_spread** (highest total,
survives 20¢). REFINE, not deploy: tame the ~800% drawdown (sizing caps),
extend beyond 3 yrs (walk-forward), and test the 0DTE active-exit nuance.
