# 1DTE SPX Iron Condor (Option Alpha / Kirk)

Source: Option Alpha "Behind the Scenes: New 1DTE Options Trading Strategy" — 4-part YouTube series. Transcript in `research/Option Alpha Strategies/1DTE Strategy/`.

> Note: numbers below are approximate and evolved across the 4 videos. Treat them as "the shape," not gospel.

## What it is, in one sentence
Every afternoon, sell a tight, defined-risk **iron condor on SPX** that expires the **next day**, collect the overnight premium, and let it expire — no babysitting.

## The building blocks (so it's not jargon)
- **Iron condor** = sell a put spread *below* the market AND a call spread *above* it at the same time. You win if the market stays in the middle "box." It's a **bet on the market staying calm**, not on direction.
- **SPX** = options on the S&P 500 index itself. Three reasons he uses it:
  - **Cash-settled** — you can never be "assigned" actual shares. The trade just settles to cash. (Big deal vs. the wheel.)
  - **No early assignment** — European-style, so nothing happens before expiration.
  - **Tax treatment** — index options get favorable 1256 tax treatment (60% long-term). Minor, but a real edge.
- **1DTE** = "1 day to expiration." Enter today, it expires tomorrow.

## The exact rules he landed on
| Piece | Rule |
|---|---|
| Instrument | SPX iron condor |
| Short strikes | ~$5 below and ~$5 above where SPX is trading (nearly at-the-money) |
| Wing width | $5 wide on each spread → **max loss capped at $500 − credit** per contract |
| Entry time | ~**3:30 PM** (late afternoon) |
| Hold | Overnight, **let it expire next day** (deliberately NOT same-day, to dodge the PDT rule — good for small accounts) |
| Exit | **None** — hold to expiration. (He tested profit-taking; it made results *worse*.) |
| Filters | Skip days with a big opening move (>1.5%), skip big overnight **gaps**, require **RSI 20–80**, skip **FOMC** days |
| Realism | Backtests include **slippage** in AND out |

## How it actually performed (honest version)
From the backtest (~384 trades over ~3 years, 1 contract):
- **Win rate ≈ 27–29%** — it *loses more often than it wins.*
- **Average win ≈ $307, average loss ≈ $87** — but wins are ~3.5× bigger than losses.
- Net expectancy ≈ **+$20 per trade** (0.27 × $307 − 0.73 × $87). Small but positive.
- **Long, ugly drawdowns** ("dark nights") — one stretch went from ~$6,000 down and took *March to June* just to recover. Live, he hit a **24-trade losing streak.**

Why the weird shape: the box is so tight (≈at-the-money) that the market usually pokes out of it → frequent small losses. But the credit collected is large vs. the $5 width, so the occasional "market sat still" day pays big. Net: a slim edge that only shows up over *hundreds* of trades.

## Honest assessment for OUR project
**Pros**
- **No assignment risk** (cash-settled) — removes the wheel's scariest moment.
- **Tiny, fixed risk per trade** ($500 max minus credit) — genuinely small-account-friendly and PDT-safe.
- **Extremely codeable** — fixed time, fixed strikes, mechanical filters, no discretion. Ideal for a bot.
- **Lots of data** — hundreds of trades to backtest honestly.

**Cons / red flags**
- **Thin edge.** ~$20/trade before *real-world* execution friction. SPX condors have wide bid/ask spreads; real slippage could eat most of the edge.
- **Brutal psychology.** A 27% win rate and 24-trade losing streaks will destroy a human trader's discipline. (He argues this is *exactly why you automate it* — the bot doesn't panic.)
- **Tail risk.** "Max loss $500" assumes you can always close/settle cleanly. A violent overnight gap is the nightmare scenario for short premium.
- **SPX is capital-heavier than it looks** for a truly tiny account, though the $5-wide defined risk keeps it bounded.

## The REAL gold: his backtesting *method*
More valuable to us than the strategy is *how he searches*. We'll steal this for our own backtester:
1. **Start with a dumb baseline** ("just hold to expiration") and only add complexity if it beats the baseline.
2. **Change ONE variable at a time** — isolate what actually helps. Never test 52 things vs. 52 things.
3. **Always include slippage** in and out — stress-test, don't flatter yourself.
4. **Require 2 consecutive hits** for a profit target so a one-tick mispricing doesn't fake a fill.
5. **Most ideas fail, and that's the point** — discarding bad ideas *is* the work.
6. **Validate out-of-sample** — he compared live trades to the backtest and they matched, which built real confidence.
7. **Document every test** so you can retrace your reasoning.

This discipline is the antidote to the "backtests lie" problem. We will build our backtester to enforce these rules.
