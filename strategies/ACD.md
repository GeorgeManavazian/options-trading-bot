# The ACD Method — Mark Fisher

Source: Mark B. Fisher, *The Logical Trader: Applying a Method to the Madness* (Wiley, 2002). Full scanned book in `research/The_Logical_Trader_Applying_A_Method_To_The_Madness.pdf`. Rules below were extracted chapter-by-chapter (Ch. 1–3, Appendix, Glossary) with page citations — see the session log in `STATUS.md`.

> Everything here is **what the book actually says**, not generic internet ACD. Where Fisher hides something (the A-value formula), it's flagged loudly.

## What it is, in one sentence
Use the **high–low of the first 15 minutes** as the day's reference range; when price pushes a set distance beyond that range **and holds there for half the range's duration**, trade in that direction — with built-in stops at the range edge and a separate "pivot range" (from yesterday) as a trend filter.

## How it relates to what we've already built
ACD is the **smarter cousin of our ORB bot.** Both are built on the *opening range*. The difference is what they do with it:

| | ORB (the bot we have) | ACD (this strategy) |
|---|---|---|
| Opening range | First **60 min** | First **15 min** (S&P) |
| Trigger | Price simply breaks the range | Price moves a **set distance** past it (the "A value") **and holds for half the range time** |
| Fakeout defense | A filter bolted on later (ADX, range width) | **Built into the trigger** — a quick poke-and-snap-back doesn't count |
| Reversals | None | The **"C"** level + the **"failed-A rubber band"** trade |
| Stops | Spread width | **B / D** levels at the range edges + the pivot range |
| Trend filter | (none in v1) | The **pivot range** from yesterday's H/L/C |

👉 The time-hold requirement is the headline. Remember our ORB whipsaw on 6/04 (−70% on a breakout that immediately reversed)? ACD's "must *stay* beyond the level" rule is engineered to reject exactly those head-fakes.

---

## The four building blocks

### 1. The opening range
- The **high and low of the first 15 minutes** of the session (9:30–9:45 ET for the S&P). *(Fisher: stocks use 20 min; commodities 5–30 min by trader preference. The S&P value comes from his Appendix table — see below.)*
- Why 15 min and not any random 15-min window? Fisher's claim: the opening range marks the day's high or low **~20% of the time** — far more than the ~1-in-16 random-walk odds. It's the "statistically significant" part of the day. *(Ch. 1, p. 12)*

### 2. The "A" — the breakout trigger (with a clock)
- **A up** = opening-range high **+ the A value**. **A down** = opening-range low **− the A value**.
- It only counts if price **holds at that level for at least half the opening-range duration** (so ~7.5 min for a 15-min range). A touch that snaps right back is **not** an A. *(Fisher: "In trading, time is more important than price.")*
- **A up held → go long. A down held → go short.**
- **Only ONE A per day.** Once an A up is set, there can be no A down that day (and vice versa). The day's directional bias is committed. *(Ch. 1, p. 15)*

### 3. The "C" — the second-chance / reversal trigger
- If the A fails and price reverses back *through* the opening range, the **C** level (further out than A) is the next entry, in the **opposite** direction.
- A **C down** can only happen after a confirmed **A up** (and a **C up** only after an **A down**). It's the "the breakout was a trap, now fade it" trade. *(Glossary, p. 240)*
- Same time rule: must hold for half the opening-range duration.

### 4. B and D — the built-in stops
- **B** = the **far edge of the opening range** → your stop on an A trade. (Long via A up? Stop = bottom of the range. At B your bias is "neutral — wait.") *(Ch. 1, pp. 15–16)*
- **D** = the stop on a C trade (1 tick beyond the opposite range edge). **Hit D and you're done with that market for the day** — "chopped up enough." *(Glossary, p. 246)*

### 5. The pivot range — yesterday's trend filter
Computed from **yesterday's** High/Low/Close:
```
Pivot Price   = (High + Low + Close) / 3
Second Number = (High + Low) / 2
Differential  = | Pivot Price − Second Number |
Pivot Range   = Pivot Price ± Differential        # a BAND, not a single line
```
- Price **above** the band = bullish bias; **below** = bearish; **inside** = neutral (wait). *(Ch. 2, p. 39)*
- The band also acts as **support/resistance**, and as a **tighter stop** (see below).
- A **3-day rolling** version (highest high / lowest low / last close over 3 days, same formula) is used as a **trailing stop** for multi-day holds. *(Ch. 2, p. 47)*

---

## The best trade: "A through the pivot"
The highest-conviction setup is when **two signals agree**: an A breakout that punches **through the pivot range in the same direction.**
- A up **+ price above/through the pivot** → strong long. Stop tightens from B (far range edge) up to just **below the pivot band** — same dollar risk, but you can size bigger. *(Ch. 3, pp. 57–60)*
- This is Fisher's whole "**maximize size, minimize risk**" idea: when signals stack, the stop gets tighter, so you put on more contracts for the *same* risk.

**Time-stop:** if price just sits inside the pivot range longer than **3× the opening-range duration** (~45 min), the pivot is "meaningless for the day" → exit, move on. *(Ch. 3, pp. 61–62)*

## The spicy one: the "failed-A rubber band"
When price reaches the A level but **fails to hold** and snaps back — especially near the pivot range — you **fade it** (short a failed A up / buy a failed A down). Tiny risk (stop = the A level itself), large potential reward. Fisher's worked example: *"you made 126 ticks and risked 4."* *(Ch. 1, pp. 27–28)* This is a reversal trade ORB doesn't have, and it's some of the best reward:risk in the book.

---

## Fisher's actual S&P 500 numbers (Appendix, Table A.5, p. 222)
| | Value (2001) | As % of price (S&P ≈ 1,135 then) |
|---|---|---|
| Opening range | **15 minutes** (9:30–9:45 ET) | — |
| **A value** | **2 points** | **≈ 0.18%** |
| **C value** | **1.5 points** | **≈ 0.13%** |

> ⚠️ **These are 2001 values.** Two literal points on today's SPX (~5,400) is a rounding error. We port them as a **% of price**: A ≈ 0.18%, C ≈ 0.13% → on SPX 5,400 that's roughly **A ≈ 9–10 pts, C ≈ 7 pts**. Treat these as **starting anchors to backtest around**, not gospel — they're also pre-decimalization and may not be apples-to-apples with today's ES.

---

## ⚠️ The big honest gap for automation
**Fisher deliberately does NOT publish how the A and C values are calculated.** He says only that they're *"based on proprietary research... volatility measurements,"* and lists static per-instrument numbers (the table above) without a formula. There is **no "A = X% of ATR" rule anywhere in the book.**

**What this means for our bot:** we cannot port his formula because he doesn't give one. We have to **engineer our own volatility-based A value** and tune it by backtest. The clean plan:
1. Start from his anchor: **A ≈ 0.18% of price, C ≈ 0.13%** (or equivalently a fraction of recent ATR / average daily range).
2. Backtest a sweep of that fraction (like we swept delta/wings on the condor) to see what actually works on SPX in our 3-year data window — judged on **cross-regime robustness, not curve-fit.**

This is a feature, not a bug: it's exactly the kind of honest, measurable engineering this project is for.

---

## Honest assessment for OUR project
**Pros**
- The **time-hold trigger directly attacks ORB's #1 enemy** (whipsaw fakeouts). Natural A/B comparison: same opening-range family, but does "wait for it to stick" actually beat "trade the raw break"?
- **Defined reference points everywhere** (B, D, pivot) → clean, mechanical stops, easy to code honestly.
- Reuses our engine: data loaders, intraday path-from-options, backtest reporting, sizing layer.
- The **pivot range** is a cheap, powerful trend filter we could even retrofit onto ORB later.

**Cons / red flags**
- **More intraday logic than ORB:** we must track a sub-bar clock ("has price held above A for 7.5 min?"), not just "did it cross." More state to get right.
- **The proprietary A-value gap** means a chunk of the "edge" is ours to rediscover by backtest — no guarantee our tuned value reproduces Fisher's results.
- It's a **discretionary system with many setups** (A, C, failed-A, late-day C, first-hour pivot...). For a v1 bot we must pick the **one core mechanical setup** (likely: A-through-pivot, hold-time enforced) and ignore the rest, or it becomes unbuildable.
- ACD is a **directional futures/stock** system. Like ORB, we'd express it on SPX via options — wrapper **TBD after this writeup** (credit spread vs. long option). *[open decision]*

## Open build decisions (to settle before coding)
1. **Options wrapper** — credit spread (ORB-style, reuse everything) vs. buy directional options. *Deferred by user until the strategy is clear; now it is — revisit next.*
2. **A/C value derivation** — fixed % of price (≈0.18% / 0.13%) vs. fraction-of-ATR; then a sweep to tune. *This is the heart of the build.*
3. **Which setup(s) for v1** — recommend starting with the single **"A (held) through the pivot"** long/short, stop at the pivot band, time-stop at 3× the range. Add failed-A and C trades only if v1 shows promise.
4. **Entry window** — by when must the A form (ORB used ~noon)? TBD.

## Meta-lessons worth keeping
1. **Time > price.** Fisher's core edge over a naive breakout is *patience* — make the move prove itself. If our backtest confirms this beats raw ORB, that's a genuine, transferable insight.
2. **When a vendor hides the formula, the honest move is to rebuild it measurably** — not to pretend we know it. Our A-value sweep is that, out loud.
3. **Don't build all of ACD.** The book has a dozen setups; a good bot does *one* of them well. Same discipline as Kirk's "nothing beat the baseline." ([[project-goal]])
