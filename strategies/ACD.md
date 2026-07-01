# The ACD Method — Mark Fisher, *The Logical Trader* (COMPLETE ruleset)

> **Authoritative spec.** Rebuilt 2026 from a full-book read (all 8 chapters + Appendix + Glossary),
> replacing the earlier partial summary. Page citations are BOOK pages. Where Fisher withholds a
> formula (the A/C values) it is flagged loudly. This is the reference for building the FULL ACD bot.
>
> **Key correction to our earlier work:** we implemented only the *micro A-held breakout + pivot filter
> + a naive 3-day trailing stop* — roughly 15% of the method, and the part that fights SPX's mean-reverting
> nature. The real method is a two-layer system (MICRO intraday + MACRO multi-day) with reversal setups,
> a trend/chop filter (the number line), a regime classifier (pivot moving averages), and confluence-based
> sizing. See "What we missed" at the end.

---

## 0. Philosophy (Introduction; Glossary)
- ACD plots objective price points **relative to the opening range**; those points are **references** — "where you get out if you're wrong" — not predictions. *(Ch.1 p.9; Glossary "Points of reference" p.246)*
- **"In trading, time is more important than price."** A level only counts if price *holds* there. *(Ch.1 p.19; Glossary "Time factor" p.248)*
- Two layers: **Micro ACD** (floor/day-trading: A, C, B, D, opening range, daily pivot, pivot first-hour) and **Macro ACD** (multi-day: plus/minus days, number line, change-in-trend, rolling pivots, first-two-weeks, pivot-MA slopes). *(Intro p.1; Glossary "Micro ACD" p.244, "Macro ACD" p.243)*
- **Next! / "maximize size, minimize risk":** seek immediate gratification; if a trade doesn't work fast, get out; size up only when confluence tightens the stop. *(Glossary p.243, p.245)*
- Market must have **liquidity + intraday volatility** to be ACD-tradeable. *(Ch.1 p.34; Glossary p.243, p.249)*

---

# PART A — MICRO ACD (the intraday engine)

## A1. The Opening Range (OR)  *(Ch.1 pp.10–13)*
- The OR = high & low of the **first N minutes** of the session in the instrument's **domicile market**.
- **Duration by instrument (Table A.5, p.222):**
  | Instrument | OR length |
  |---|---|
  | **S&P 500 & Nasdaq futures** | **15 min** |
  | Stocks (general) | 20 min |
  | Most commodity futures | 5 min |
  | FX cash / London Brent | 30 min |
  - *(Our SPX 15-min choice was correct.)*
- Fixed per instrument, used identically every day. Domicile-market rule: use the exchange where the instrument primarily trades (ADRs → foreign open, etc.). *(p.11)*
- **Statistically significant:** the OR marks the day's high or low **~17–23% (~20%)** of the time in volatile markets vs. ~3% random. This is ACD's foundational premise. *(pp.12–13; Glossary "Statistically significant" p.248)*

## A2. The A / B / C / D points  *(Ch.1 pp.13–18; Glossary pp.239–246)*
- **A up** = OR-high + A-value. **A down** = OR-low − A-value. Confirmed only if price **holds at/beyond the level ≥ half the OR duration** (15-min OR → **7.5 min**). *(p.15)*
  - A up held → **long**, stop = OR-low (Point B). A down held → **short**, stop = OR-high (Point D).
- **Only ONE A per day.** Once an A up is confirmed, no A down that day (and vice-versa). Bias is committed. *(p.15)*  *(But a **failed** A does NOT consume the one-A rule — the opposite A is "still in the running." p.19)*
- **Point B** = neutral level after an A up = **bottom of the OR** (Glossary says B = OR bottom for A-up / OR top for A-down; Ch.1 example uses OR-low − 1 tick). It is the **stop for an A trade**. Reaching B → bias neutral, wait. *(p.16; Glossary p.246)*
- **Point C** = the crossover that flips bias to the opposite side, **after** an A. **C up** = OR-high + C-value; **C down** = OR-low − C-value. Same ≥½-OR hold rule. A **C down** can only occur after a confirmed **A up** (and C up only after A down). *(pp.16–17; Glossary p.240)*
  - Enter in C's direction; **stop = Point D** (opposite OR edge + 1 tick). Hitting D → "chopped up enough, done for the day." *(p.17; Glossary "Point D" p.246)*
- **A-values / C-values are PROPRIETARY** (volatility-based; formula withheld). Fisher gives per-instrument numbers in the Appendix. **Stocks: C = A. Commodities: C ≠ A (usually C > A).** *(pp.14,16; Glossary p.240)*

## A3. The A/C values that ARE published (Appendix Table A.5, p.222, Dec 2001)
| Market | OR | A value | C value |
|---|---|---|---|
| **S&P 500** | 15 min | **17.5** | **20.5** |
| Nasdaq | 15 min | 24 | (illegible) |
| Corn | 5 | 1.6 | 1.2 |
| Cocoa | 5 | 10 | 15 |
| Cotton | 5 | 5 | 9 |
| Euro/$ (ED) | 5 | 13 | 4 |
| Unleaded gas | 5 | 115 | 135 |
| Live hogs | 5 | 150 | 220 |
| Platinum | 5 | 100 | 100 |
| British £ (fut) | 5 | 7 | 12 |
- Values are in each market's **ticks**, periodically re-calibrated. (Ch.1's older S&P example used A=2.00/C=1.50 index points — a different snapshot/unit; the reader flagged C<A there as possibly anomalous. The **structural** rule is C usually ≥ A.)
- **For our bot:** port the A/C value as a **% of price or a fraction of ATR** and **backtest-tune** it (Fisher's formula is unavailable). S&P A≈17.5, C≈20.5 in 2001-tick terms → anchor and sweep.

## A4. Failed A / Failed C — the "rubber band" reversals  *(Ch.1 pp.25–29; Glossary pp.241–242)*
- **Failed A:** price reaches A but does NOT hold ≥½-OR (or reverses back into the OR). **Fade it:** failed A-up → **short** (stop just above A-up); failed A-down → **long** (stop just below A-down). Small risk, large reward (Fisher's example: *"made 126 ticks, risked 4"*). *(pp.26–28)*
- **Failed C** = the **"Treacherous Trade"**: price reaches C but doesn't hold; snaps back — often off the pivot range. Fade toward the OR. **No clean stop** — Fisher warns it's risky; "immediate gratification, take profits quickly." *(Glossary p.242; Ch.3 p.75)*
- **Failed A against/within the pivot** is *stronger*: if the pivot stops the A, the failure confirms support/resistance → higher-probability fade with the pivot band as the reference. *(Glossary pp.241–242; Ch.3 p.65)*

---

# PART B — THE PIVOT RANGE (the support/resistance & trend core)

## B1. Daily pivot range formula  *(Ch.2 pp.37–38; Glossary p.241)*
```
Pivot Price  = (High + Low + Close) / 3        # prior day's H/L/C
Second Number= (High + Low) / 2
Differential = | Pivot Price − Second Number |
Pivot Range  = Pivot Price ± Differential       # a BAND
```
*(One glossary line typo'd "second = (H+L+C)/2"; Ch.2's worked examples confirm (H+L)/2.)*

## B2. Roles of the pivot range  *(Ch.2 pp.38–43; Glossary)*
1. **Sentiment/tone:** prior close **above** band → bullish next day; **below** → bearish; **inside** → neutral.
2. **Support/resistance:** band **below** price = support; **above** = resistance. A **clean break through** the band → expect a significant move that way; a **bounce off** it (not penetrating) → fade (rubber-band).
3. **Stop / sizing:** when a signal agrees with the pivot, the stop tightens to the far side of the band → **size up** (see D-sizing).
- **Time stop:** if price sits **inside** the band longer than **3× the OR duration** (e.g., 30 min for a 10-min OR), the pivot is "meaningless for the day" → stand down. *(Ch.3 pp.61–62)*
- **Small pivot** (narrow band after a normal-range day) → expect a **more volatile / larger-range** next day. **Pivot-on-gap:** a gap that never trades back into the band makes the gap level lasting support/resistance. *(Ch.2 pp.44–46; Glossary)*

## B3. Rolling & longer-term pivots  *(Ch.2 pp.47–54)*
- **3-day rolling pivot:** same formula with highest-high / lowest-low / last-close over the trailing 3 days. Used as a **trailing stop** and multi-day bias; recompute daily (drop oldest). Fisher also uses **3–6 day** rolling pivots as exit tools (Ch.6). Never change the window mid-trade.
- **Longer-term pivots** (first-two-weeks, half-year, etc.): identical formula over the period; larger A targets (e.g., 200 ticks) for multi-week horizons. First-two-weeks-of-year and **first trading day of the month** are statistically significant (often the month's high/low). *(pp.46–47, 52–54)*

## B4. Plus / minus days + the 30-day cycle  *(Ch.2 pp.49–51; Glossary pp.244,246)*
- **Plus day:** OR **below** pivot AND close **above** pivot. **Minus day:** OR **above** pivot AND close **below** pivot. Else **zero**.
- **30-trading-day cycle:** if 30 days ago was a (volatile) plus day AND today **opens on the matching side** of the pivot, today has a statistically significant chance of also being a plus day (same for minus). Must line up from the open.

---

# PART C — THE SETUPS (how it's actually traded)

*(Ch.3 "Putting It Together" pp.55–76; Glossary)*

1. **A through the pivot** *(best base setup)* — A up (or down) that also clears the **whole pivot band** in the same direction. Two signals agree → **stop tightens to the opposite side of the band**, so **size up**. *(pp.56–59; Glossary "Point A through the pivot" p.246)*
2. **Failed A against the pivot** — failed A that snaps back at/within the band → fade; stop = far side of band or a time stop. *(p.65)*
3. **Point C through the pivot** *(rare, "once in a blue moon")* — OR entirely on one side of the pivot, market makes A the other way, then reverses **all the way through the OR and the pivot** to make C through the band → high-conviction, **double size**, stop = far side of band. *(pp.65–69)*
4. **Late-day Point C pivot** *(the "Rolls-Royce", highest probability)* — a C-through-pivot late in the session traps those who must liquidate by the close → carry overnight **only if** the close is beyond both the pivot and the C level. *(pp.69–71; Glossary p.243)*
5. **Pivot first-hour high/low** *(trend-day detector)* — if the daily pivot band **engulfs the first-hour high (or low)**, an A forms in the first hour, and price closes the first hour **within ~15% of the extreme** in the trade direction → enter; stop = first-hour extreme; time stop = **2× OR**. *(pp.71–74)*
6. **Treacherous trade / System-failure trade** — fades with **no defined stop** in choppy/failed conditions; take profits fast. *(pp.74–75)*

**Position sizing by confluence ("maximize size, minimize risk")** *(Ch.3 pp.60–61)*: total risk = stop-distance × tick-value × contracts. When the pivot stop replaces the wider B/D stop, the stop shrinks (e.g., 25→10 ticks) → trade **2.5–4× more contracts for the SAME dollar risk**. Stack signals (A + pivot + 30-day cycle) → size up further (e.g., 10 → 20–30 contracts).

---

# PART D — MACRO ACD (the multi-day system we never built)

## D1. The Number Line  *(Ch.4; Glossary "Number line" p.245)*
- Score each day: **+2** (A-up held & close above OR), **−2** (A-down & close below OR), **+4** (C-up & close above), **−4** (C-down & close below); partial/mixed = ±1/±3; else **0**. *(Midterm: good A-down = −2, good C-up = +4.)*
- Keep a **30-trading-day cumulative sum**. When it moves from ~0 to **±9 and holds ≥2 consecutive days** → statistically significant **trend confirmation** (trade that direction, size up, can hold overnight).
- **System-failure fade:** if ±9 triggers but the market doesn't follow through in 2–3 sessions and the line falls back below ±9 → **fade** (the failed macro signal is itself a setup).
- **Chop filter:** while the line hovers in ±4, **avoid trend trades** — this is ACD's answer to choppy markets (which is exactly what killed our momentum version). Change-in-trend calendar (proprietary) flags 2–3 likely reversal days per month.

## D2. The Reversal Trade — *Fisher's best system, 2–3 yrs*  *(Ch.6 pp.139–144; Glossary p.247)*
- **Two consecutive A signals the SAME direction**, then the **next A the OPPOSITE direction beyond the extreme** of the two → trapped traders forced to cover → enter with the reversal. Bigger the gap between the two A's and the opposing A, the better (gap openings amplify it).
- Invalidated by: 3+ consecutive same-direction A's; any A/B/C/D between the two A's; too many neutral days. Manage the exit via normal ACD (C or next opposite A).

## D3. TRT (Trend Reversal Trade) & MAH  *(Ch.6 pp.146–151; Glossary pp.243,249)*
- After a **sustained trend**, a **gap to a new high/low** (stronger after a holiday = **"Mad As Hell"**), then a **hard A against the trend**, then a **failed C** in the trend direction, then price retraces into the OR / prior-day range → **fade** (huge reversals; the 1929 top and 1932 bottom are the examples). Stop = the failed-C level; time stop = 2× OR.

## D4. Pivot Moving Averages (regime classifier)  *(Ch.5; Glossary pp.244–246)*
- MAs of the **daily pivot** (not close), periods **14 / 30 / 50**. **Judge the SLOPE, not crossovers.**
  - All three up → **bullish**; all down → **bearish**; flat & parallel → **neutral** (stand aside); diverging → **confused** (chop).
- Strategies: **MAS** (trade in the slope direction on an A signal), **MAF** (fake-out: in a trend, price dips to but not through the 30-day PMA then re-crosses the 14-day → re-enter), **MAD** (divergence: in confused/neutral PMAs with a point of reference + island reversal → fade the extreme). "Kindergarten trader": slopes up→long, down→short, flat/confused→flat.

## D5. Exit tools  *(Ch.6)*
- **Momentum:** today's close vs. close **8 days ago**; a sign flip = exit even if price hasn't moved against you. *(pp.137–139)*
- **Rolling pivot (3–6 day)** catching up to price = momentum lost → exit. *(pp.133–137)*
- **Sushi Roll:** 5 rolling bars (days, or 5×10-min) — when the latest 5 take out the prior 5's high & low and **close** beyond the prior 5's extreme → reversal warning. **Outside Reversal Week** = the weekly version (Enron, 1929/1932 examples). *(pp.152–160; Glossary p.248)*

---

## E. Honest gaps & how we handle them
1. **A/C-value formula is proprietary** — port as % of price / ATR fraction, anchor at the Appendix numbers (S&P A≈17.5, C≈20.5 in 2001 ticks; ≈0.15–0.20% of price), **backtest-tune**, judge on cross-regime robustness.
2. **Some Appendix values illegible** in the scan (natural gas A, several C's) — we don't need them (SPX-focused, and we tune anyway).
3. **Number-line partial scores (±1/±3)** are edge cases — implement core ±2/±4/0 first.
4. **Instrument matters:** Fisher's world is **futures/commodities that TREND** (energies, metals, bonds). The trend/breakout setups (A-held, reversal-trade, TRT, number-line) are built for trending instruments; **SPX index mean-reverts** (we proved it). Building the FULL method lets us test it on the right instruments (energy/commodity ETFs, individual momentum stocks, futures) — not just SPX.

## F. What we MISSED (the case for the full build)
Our shelved v1 = **only** A-held breakout + pivot *filter* + a naive 3-day trailing stop. The full method adds, all UNbuilt:
- **Failed-A / Failed-C rubber-band reversals** (mean-reversion — fits SPX!).
- **A/C through the pivot; late-day C pivot** (the highest-probability setups).
- **The Reversal Trade** (Fisher's best) and **TRT/MAH**.
- **The number line** (trend confirm + **chop filter** — would have vetoed the losing choppy trades).
- **Pivot moving averages** (regime classifier: only trend-trade when PMAs agree).
- **Confluence sizing, momentum/rolling-pivot/sushi exits.**
- **Instrument flexibility** (the method is designed for trending futures/commodities, not the mean-reverting SPX index).

→ Next: design the **complete, instrument-agnostic ACD engine + options overlay** from this spec.
