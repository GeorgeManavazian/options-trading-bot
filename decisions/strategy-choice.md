# Strategy selection scorecard

Goal: compare candidate strategies and pick the one to automate. We score each on the things that matter for THIS project (small account, beginner coder, resume, runnable live).

## Scoring dimensions (1 = bad fit, 5 = great fit)
- **Capital fit** — works with a small account?
- **Codeability** — easy to express as precise rules a bot can follow?
- **Edge honesty** — plausible real edge vs. likely fool's gold?
- **Risk profile** — how survivable are the bad days?
- **User comfort** — does the user understand it and feel okay running it live?

## Candidates
| Strategy | Capital fit | Codeability | Edge honesty | Risk | Comfort | Notes |
|----------|:----------:|:-----------:|:------------:|:----:|:-------:|-------|
| Wheel (CSP → CC) | 2 | 4 | 4 | 3 | 5 | User's current manual strategy. Baseline to beat. Capital-heavy (locks full collateral); assignment risk; but user understands & trusts it. |
| 1DTE SPX Iron Condor | 4 | 5 | 2 | 3 | 2 | Neutral (bet market stays still). Cash-settled, tiny fixed risk, very codeable. BUT thin edge (~$20/trade pre-slippage), 27% win rate, brutal drawdowns. See `strategies/1DTE.md`. |
| ORB (Opening Range Breakout) | 4 | 3 | 3 | 3 | 4 | Directional momentum + premium selling on SPX 0DTE. High win rate (~86-90%), defined risk, no assignment, emotionally easier. BUT needs real-time intraday data/logic (harder to build), whipsaw/reversal risk. See `strategies/ORB.md`. |

> Fill in scores as we review each transcript. The winner becomes the bot's strategy.

## Decision
_Not yet made._
