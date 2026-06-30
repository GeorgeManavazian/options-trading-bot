# Opening Range Breakout (ORB) — Option Alpha

Source: Option Alpha "Behind The Scenes: Opening Range Breakout (ORB)" — multi-part series (Kirk + another OA trader). Transcript in `research/Option Alpha Strategies/ORB Strategy/`.

> Numbers are approximate and evolved across the videos. Treat as "the shape."

## What it is, in one sentence
Watch the first hour of the trading day to define a price "range," and when the market **breaks out** of that range, sell a credit spread **in the direction of the breakout**, betting the move continues. (Directional momentum + premium selling.)

## The core idea: the "opening range"
- The **opening range** = the **high and low of the first 60 minutes** of trading (9:30–10:30 AM ET).
- A **breakout** = price pushing **above that high** (bullish) or **below that low** (bearish).
- The bet: once the market breaks out of its morning range, it tends to **keep going** that way (trend/momentum), or at least not snap all the way back.

This is fundamentally different from the iron condor:
- **Iron condor (1DTE)** = *neutral.* Bet the market stays STILL. Sell both sides.
- **ORB** = *directional.* Bet the market KEEPS MOVING the way it broke. Sell ONE side.

## How they trade it with options (on SPX, 0DTE, cash-settled)
| Breakout direction | What you sell | The bet |
|---|---|---|
| Price breaks **above** the range (bullish) | **Short put spread** (PCS) | Market keeps going up / doesn't fall back below |
| Price breaks **below** the range (bearish) | **Short call spread** (CCS) | Market keeps going down / doesn't rally back |

- **Strikes:** short strike placed **outside the opening range** (further out-of-the-money = safer). Spreads **$15 wide** (Kirk) or **$10 wide** (the other trader).
- **Expiration:** same day (**0DTE**) on **SPX** → cash-settled, no assignment.
- **Entry window:** the breakout has to happen by about **noon** (gives ~1.5 hrs after the range is set).

## The filters Kirk layered on (one at a time)
- **Range width ≥ 0.2%** — ignore boring, too-tight mornings.
- **Risk/reward floor (~5–10%)** — don't take a $15-wide spread for a tiny credit. (Avoid "$1,400 of risk to make $30" trades.)
- **ADX ≥ 15** — a trend-strength gauge; only trade when there's real directional momentum. (ADX 15 helped; ADX 20 over-filtered and hurt.)
- **FOMC handling (a great find):** he *skips* Fed days on the put side, but discovered **trading *through* FOMC on the call side actually improved results** — those days were "juiced up" with premium.
- **Exits:** Kirk **lets it expire** (profit targets and stop-losses all underperformed in his tests). The other OA trader uses a **50% profit target + 130% stop** — a more active, hands-on version.

## How it performed (honest version)
- **High win rate ≈ 86–90%** (on the short-put/bullish side after the ADX filter). This is the opposite of the condor's 27% — ORB wins *often*.
- Avg premium collected ≈ **$188**, avg P&L ≈ **$69** per trade (short put spread).
- The losses come from **fast reversals** — the market breaks out, you sell into it, then it whips back the other way (often on news).
- **The unfixable risk:** during the videos there was a government-shutdown period with violent reversals. Kirk's takeaway: *some reversal days you simply can't backtest or filter away* ("black swan"). The defense is **position sizing + running multiple uncorrelated strategies**, not a cleverer filter.

## Honest assessment for OUR project
**Pros**
- **No assignment** (SPX cash-settled), **defined risk** (capped at spread width).
- **High win rate** — emotionally MUCH easier to run than the 27% condor.
- **Very codeable**, but more moving parts than the condor (needs intraday data to compute the opening range + detect the breakout in real time).
- Kirk chose it specifically to **complement** lower-win-rate 0DTE strategies — a lesson in combining strategies.

**Cons / red flags**
- **Needs live intraday data + real-time logic** (track the 60-min range, watch for a breakout, fire within a window). Harder to build than a fixed-time condor.
- **Reversal/whipsaw risk** is the core enemy; news-driven reversals are unfilterable.
- **0DTE + active exits (stops/targets) = same-day trades** → could trip the PDT rule on a small account. Holding to expiration (Kirk's way) avoids this; the other trader's stop/target version does not.
- Credit per trade is modest vs. the width risk — execution quality (slippage) matters a lot.

## Meta-lessons worth keeping
1. **"Nothing beat the baseline."** Kirk tested 35–50 variations and the *original simple version won.* He refused to keep curve-fitting just to force an improvement. Huge discipline lesson: more tweaking ≠ better.
2. **Black swans are a sizing problem, not a filter problem.** You can't backtest your way out of news reversals — you survive them with small size and diversification.
3. **THE thesis of our whole project, in their words:** the second trader said building the bot forced her to articulate decisions she normally makes "in 2 seconds instinctively," and that *slowing down to define every micro-decision made her a better trader.* That is exactly why we're doing this. ([[project-goal]])
4. **Bot ≠ your manual trading unless you're precise.** Her bot lost on a day her real money won — purely because the bot's profit target was 55¢ and she'd manually taken 50¢. Tiny rule mismatches = different outcomes.
