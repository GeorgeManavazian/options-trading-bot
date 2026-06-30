# ORB Bot — Design Spec

**Date:** 2026-06-30
**Status:** Approved for planning (pending user review of this doc)
**Author:** Session 3 brainstorm (continuity: see `STATUS.md`)

## 1. What we're building

**Bot #2: an Opening Range Breakout (ORB) backtester** for SPX 0DTE credit spreads.

This is the second strategy in the project (bot #1 = the 1DTE iron condor, already built and
backtested — it lost money in 2024, a useful honest result). ORB is a **directional momentum +
premium-selling** strategy: watch the first hour of trading to define a price range, and when price
**breaks out** of that range, sell a credit spread **in the direction of the breakout**, betting the
move continues.

Strategy background lives in `strategies/ORB.md`. Source: Option Alpha "Behind The Scenes: ORB".

### Goal for this build
Same honest arc as the condor: **build the rules engine + a historical backtester** to test whether
ORB actually has edge on real data. **No live/paper trading yet.** Win rate, equity curve, and max
drawdown are the deliverables — measured, not assumed.

### Scope decisions (locked in during brainstorm)
- **Exit styles: build BOTH and compare** — Kirk's "let it expire" baseline AND the other OA trader's
  "50% profit target / 130% stop". This directly tests Kirk's "nothing beat the baseline" claim on our
  own data.
- **Data source: IVolatility Builder (the $79 trial we already have).** Its intraday endpoint provides
  real 1-minute option data — no new vendor, no modeled prices needed.
- **v1 = the bare baseline** (every breakout taken, no filters). Filters added later, one at a time.

## 2. The data reality (the crux)

ORB is **intraday** — unlike the condor, which used only end-of-day data. We need minute-level data to
build the opening range, detect the breakout, and price the spread at entry/exit.

**What IVolatility Builder gives us (verified in `research/Rest API Documentation.pdf`):**

- `/equities/intraday/single-equity-option-rawiv` — for one option contract on one date, returns
  **1-minute bars** (also 5/15/30-min via `minuteType`) with **real NBBO bid/ask, IV, OI, and greeks.**
  Params: `symbol`, `date`, `expDate`, `strike`, `optType` (CALL/PUT), `minuteType` (MINUTE_1, ...).
- `/equities/intraday/single-equity-optionsymbol-rawiv` — same, but keyed by full `optionSymbol`.
- This endpoint is included in the Builder plan ("+ + +" in the access table, p.7).

**Consequences:**
- We get **real intraday bid/ask** — so we do NOT need to model option prices with Black-Scholes.
  `greeks.py` is kept only as a fallback for missing minutes / sanity checks.
- Both exit styles are fully supported: let-it-expire needs only the entry-minute price; the
  target/stop version needs the full 1-min series. Same endpoint serves both.

**Two wrinkles (verify on first live pull, like we did for the condor's column names):**
1. **No dedicated intraday *underlying-index* endpoint.** `/equities/stock-market-data` is end-of-day
   only. Solution: the option's 1-min bars carry the **underlying spot** on every minute (required to
   compute IV/greeks), so we read the 9:30–10:30 opening range off a near-ATM option's bars. Confirm
   the exact spot column on the first call; sanity-check it against the EOD close.
2. **Per-contract calls.** Each leg/day is a separate request. One ORB trade ≈ 2–3 small calls/day →
   a year (~252 days) ≈ ~13 min at the 1-req/sec throttle. **Every pull is cached to `data_cache/`**
   (same pattern as the condor) so re-runs are instant and offline.

## 3. Architecture

New `bot/orb_*` files; reuse the condor's plumbing. Each unit is small and single-purpose, and mirrors
the condor so the engine keeps its "all 3 strategies plug in" shape.

| File | Role | Notes |
|---|---|---|
| `bot/load_ivol_intraday.py` | **Data layer** — the only new file that talks to IVolatility | Given a date: returns the underlying 1-min path, and on request a chosen leg's 1-min price series. Caches to `data_cache/`. |
| `bot/orb_rules.py` | **The brain** (ORB analog of `condor_rules.build_orb`) | Pure logic, no fetching. Intraday path → opening range → breakout (time + direction) → pick the spread. The "seam": eats live/historical/fake data alike. |
| `bot/orb_exits.py` | **The two exit styles** as swappable functions | `exit_expire(...)` and `exit_target_stop(...)`. Each takes the entry + legs' intraday series → returns trade P&L. |
| `bot/backtest_orb.py` | **The day-by-day loop** (ORB analog of `backtest_chains.py`) | Outputs win rate, equity curve, max drawdown. Reuses `config.py` + `sizing.py` unchanged. |
| `bot/greeks.py` | Reused as-is | Fallback pricing / sanity check only. |
| `bot/config.py`, `bot/sizing.py` | Reused as-is | ORB plugs into the same position-sizing layer. |

## 4. Per-day data flow

The loop in `backtest_orb.py` runs this once per trading day:

1. **Get the morning underlying path.** Pull the 1-min series for a single near-ATM 0DTE option that
   day; read the underlying **spot** off each minute bar (9:30 onward). *(1 cached call.)*
2. **Build the opening range.** From 9:30–10:30 bars: `range_high = max(spot)`, `range_low = min(spot)`.
3. **Watch for a breakout (10:30 → noon cutoff).** First minute spot closes **above range_high** →
   bullish; **below range_low** → bearish. Record breakout **time** + **direction**. Neither by the
   noon cutoff → **no trade** (recorded as a flat day — counts in honest stats).
4. **Pick the spread (`orb_rules.build_orb`).**
   - Bullish → **put credit spread**; bearish → **call credit spread**.
   - **Short strike** = just outside the range on the safe side (range boundary ± a small buffer),
     snapped to a real listed strike.
   - **Long strike** = short strike ± fixed width ($10 or $15 — a `config` knob).
   - Listed strikes come from the **EOD chain we already pull/cache** (`stock-opts-by-param`).
5. **Get the two legs' real prices.** Pull each leg's 1-min series from breakout minute → close.
   *(2 cached calls.)* **Entry credit** = (short bid − long ask) at the breakout minute.
6. **Settle, both ways** (`orb_exits.py`) — see §5.
7. **Record** the day: entry time, direction, credit, max risk (= width − credit), P&L per exit style,
   win/loss → append to equity curve.

## 5. Exit logic (Step 6 detail)

Both work off the same two-leg 1-min series from Step 5:

- **`exit_expire` (Kirk's baseline):** P&L is purely the payoff at the **0DTE close**. Settles on the
  safe side of the short strike → keep full credit (max win); past the long strike → full max loss;
  in between → partial. Needs only the credit + the closing price.
- **`exit_target_stop` (active):** walk the 1-min series from entry. Each minute, spread value =
  (short bid − long ask). Unrealized profit ≥ **50%** of credit → close (win). Unrealized loss ≥
  **130%** of credit → close (loss). Neither by close → settle at expiry like the baseline. **First**
  trigger wins.

Same day, same data, two P&L numbers → apples-to-apples test of "nothing beat the baseline".

## 6. Filters — added later, one at a time (NOT in v1)

v1 takes every breakout. Filters are added afterward as **toggles in `config.py`**, measured one at a
time (Kirk's discipline lesson — avoid curve-fitting a pile at once):

- **Range width ≥ 0.2%** — skip boring/too-tight mornings.
- **R/R floor ~5–10%** — don't take a wide spread for a tiny credit.
- **ADX ≥ 15** — trend-strength gate, computed from the morning bars. (ADX 20 over-filtered in Kirk's tests.)
- **FOMC handling** — skip Fed days on the put side; Kirk found trading *through* FOMC on the call side
  helped. Implemented as a date list.

## 7. Honest caveats (stated up front)

1. **Fills are optimistic.** We use NBBO touch/mid; real fills suffer slippage — worst on the fast
   reversal days that are ORB's core enemy.
2. **One spot source.** Reading the underlying off an option's bars is fine but sanity-checked against
   the EOD close on day one.
3. **The unfilterable risk is real.** News-driven reversals (e.g. the government-shutdown whipsaws in
   the source videos) can't be backtested away. Defense = **sizing + diversification** — exactly why
   this is bot #2, complementing the condor, not replacing it.

## 8. Testing (TDD)

- `orb_rules` — tested on **hand-built fake intraday days**: a clean bullish breakout, a clean bearish
  one, a no-breakout chop day, a whipsaw. Assert correct direction/strikes, or correct sit-out.
- `orb_exits` — tested on a **synthetic price series** with known target/stop trigger points. Assert
  exact P&L for both styles.
- **Small real run** (1–2 weeks of cached SPX days) end-to-end before any multi-month backtest — same
  way we de-risked the condor.

## 9. Out of scope (YAGNI for this build)

- Live/paper trading and Schwab integration.
- Real-time (today's) data — backtest only.
- The condor's wheel/ORB live orchestration ("all 3 live" is a fall stretch goal).
- More than the four filters listed — only if v1 results justify investigating them.

## 10. Open items to confirm during implementation

- Exact **spot column name** in the intraday option response (verify on first live call).
- Exact **timestamp/field names** in the 1-min bars → drives the `COLUMN_MAP` in `load_ivol_intraday.py`.
- The noon **cutoff time** and the opening-range window are config knobs; defaults 12:00 ET cutoff,
  9:30–10:30 ET range.
- Whether to trade **SPX vs XSP** for the $10k account (sizing) — handled by the existing `config`
  profile, same as the condor; default to building/validating on SPX data, size into XSP live.

---

*Note: this project is not yet a git repo (`STATUS.md`), so this spec is saved but not committed.*
