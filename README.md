# Options Wheel Bot

A project to automate an options **wheel strategy** (cash-secured puts → covered calls) into a trading bot — built as a hands-on learning project and resume piece, with a real, honest track record as the goal rather than hype.

## Goals
1. **Learn** options strategies deeply enough to automate one.
2. **Build** a bot that faithfully executes a chosen strategy: data → rules → backtest → paper trade → live (small).
3. **Prove it honestly** — real (even small) live results plus a validated backtester. Rigor over headline returns.

## Status
**Phase 1: researching strategies to choose the best one to automate.** See `STATUS.md` for the live state.

## Project map
| Path | What's in it |
|------|--------------|
| `STATUS.md` | Home base — where we left off, next step, session log |
| `CLAUDE.md` | Instructions a fresh AI session reads first |
| `strategies/` | Plain-English explainer per strategy studied |
| `research/` | Raw transcripts and notes (Option Alpha videos, etc.) |
| `decisions/` | Strategy-selection scorecard |
| `bot/` | Code (added once a strategy is chosen) |

## The build roadmap
1. Coding environment set up
2. Pull live stock + option data (free tools)
3. Rules engine (encode the strategy)
4. Backtester (replay history honestly)
5. Paper trade (Schwab API, simulation)
6. Go live, small (real, honest track record)

## Tech (planned)
Python · free market data (e.g. yfinance) early · Schwab Trader API for live/paper trading later.
