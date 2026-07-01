# Options Trading Bot: The ACD Method

An options trading bot that automates Mark Fisher's ACD method and backtests it honestly on three years of real SPX option prices. Built as a learning and resume project. The goal is a track record you can audit, not a headline return.

The guiding rule for the whole project: find strategies that break the least, not strategies that look best on paper. Several ideas were tested and shelved when the data said so. One survived.

## The strategy

The bot trades **Mark Fisher's ACD method** from *The Logical Trader*.

Every morning the market spends its first stretch of time carving out a high and a low. Call that the opening range. Fisher draws a trigger level a set distance beyond it, and adds one rule that filters out most fakeouts: price has to *hold* past the trigger for a while before it counts. Time confirms the move, not just price.

On top of the intraday signals, a multi-day layer scores recent days to judge whether the market is trending or chopping, and stands aside when it is chopping.

Testing the full method on the S&P 500 surfaced a clear result: the S&P does not follow breakouts, it fades them. So the edge is not in trading the breakout. It is in trading the **failed** breakout. When price pokes past the trigger, fails to hold, and snaps back, the bot fades that failure. That is a mean-reversion bet, and it fits how the S&P actually behaves.

The winning configuration, called **V5**:

- **Signal:** a failed A-trigger breakout (the "rubber band" fade)
- **Filter:** skip `failed_c`, the reversal Fisher himself flags as treacherous
- **Structure:** a same-day (0DTE) debit spread in the fade's direction, defined risk
- **Exit:** take profit or cut the loss intraday near 50%, rather than holding to the close

## Results (V5, backtest)

Three years, July 2023 to June 2026, 119 trades on real IVolatility option prices.

| Metric | V5 | Baseline (no filter, hold to close) |
|---|---|---|
| Risk-adjusted return (return ÷ worst drawdown) | **+37.9** | +6.5 |
| Win rate | **82%** | 51% |
| Worst drawdown (in units of one trade's risk) | **110%** | 796% |
| Positive years | **all 4 (incl. 2026)** | 2 of 4 |
| Survives 10¢/contract slippage | **yes** | yes |

What that looks like as a real account: **$10,000 compounding at 3% of equity per trade grows to about $34,374 (+244%) over the backtest, with a worst backtest dip of 3.3%.** Money made in every year, including 2026, the year the unfiltered version lost. Note that 3% is an aggressive size for an edge that has not traded live yet: the backtest dip is a lucky-ordering artifact, and a realistic worst case under stress testing is closer to 10%.

Two findings mattered more than the numbers:

1. **The active exit did the heavy lifting.** Banking the bounce intraday, instead of holding a fast-decaying option to the bell, is what cut the drawdown by about seven times.
2. **The simplest good combination won.** A "kitchen sink" variant with every switch turned on scored *worse* than the clean two-lever V5. Piling on knobs made it worse, which is the opposite of what overfitting a backtest usually tempts you to do.

A rigor grader scored V5 at 56/100, "refine, not deploy," flagging the drawdown and the three-year sample. Both flags are honest and both are addressed below.

## How it is built

The bot is a pipeline. Real prices go in one end, a graded verdict comes out the other.

| Stage | File | Job |
|---|---|---|
| Intraday engine | `bot/acd_micro.py` | Reads one day, finds the A/B/C/D levels and all nine ACD setups |
| Multi-day engine | `bot/acd_macro.py` | Judges the regime (trend vs chop), filters and sizes the signals |
| Options overlay | `bot/acd_options.py` | Turns a signal into an actual option position |
| Backtest | `bot/backtest_acd_fades.py`, `bot/backtest_fade_variants.py` | Prices every trade on cached real chains, adds costs, scores it |

Data comes from IVolatility (end-of-day chains and one-minute intraday bars), cached locally so every experiment runs offline. The strategy rules live in `strategies/ACD.md`, cited page by page from the book.

## See the evidence yourself

- **[`results/v5_trade_ledger.md`](results/v5_trade_ledger.md)**: every one of the 119 trades, why it was entered, the strikes, why it exited, and the profit or loss. Nothing filtered.
- **[`results/v5_trade_ledger.csv`](results/v5_trade_ledger.csv)**: the same ledger as a spreadsheet you can slice yourself.
- **[`results/v5_equity_curve.png`](results/v5_equity_curve.png)**: the account curve and the drawdown underneath it.
- **[`results/backtest_fade_bakeoff_eval_2026-07-01.md`](results/backtest_fade_bakeoff_eval_2026-07-01.md)**: the nine-variant bake-off and how V5 won.

Every P&L in the ledger is recomputed from the source prices and checked against the backtest by an assertion in the code. The ledger *is* the backtest, not a nicer retelling of it.

## Honest limits

Read these before trusting anything here.

- **This is a backtest, not live or paper-traded results.** Real historical prices, real signals, but the strategy has not risked a dollar forward.
- **V5 was picked as the best of nine variants.** That is mild overfitting by construction. The owed next step is a walk-forward test on data the strategy never saw during tuning.
- **Three years, one instrument (SPX).** A short sample across a limited set of market conditions.
- Returns quoted "on risk" are per-trade returns on the capital at risk, not account returns. Position sizing is what translates them into the account figures above.

## Running it

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install pandas matplotlib ivolatility

# Reproduce the winning bake-off and the trade ledger (offline, uses cached data):
.venv/bin/python bot/backtest_fade_variants.py
.venv/bin/python bot/trade_ledger.py

# Pulling fresh data needs an IVolatility key:
export IVOL_API_KEY="your-key"
```

## Project map

| Path | What's in it |
|---|---|
| `STATUS.md` | Where the work stands and what comes next |
| `strategies/` | Plain-English explainer per strategy studied (`ACD.md` is the live one) |
| `bot/` | The engine, the options overlay, the backtests, the reports |
| `results/` | Backtest evals, the trade ledger, the equity chart |
| `docs/superpowers/` | The spec and plan behind each piece of work |

## Where it is headed

The next step is the walk-forward test that validates V5 on unseen data. After that: run the same engine on a trending market (where the breakout half of ACD should work, unlike the mean-reverting S&P), and test an older idea, running an iron condor only on the days the engine flags as chop.
