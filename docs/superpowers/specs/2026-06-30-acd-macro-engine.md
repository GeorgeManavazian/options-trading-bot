# ACD Full Bot — Sub-project ②: The Macro Engine (Design Spec)

**Date:** 2026-06-30
**Status:** Approved (design) — pending implementation plan
**Rules source of truth:** `strategies/ACD.md` Part D (+ B4). **Consumes:** `bot/acd_micro.py` output.
**Build order:** ① Micro (done) → **② Macro (this)** → CHECKPOINT (validate signal edge) → ③ Options → ④ Backtest.

---

## Purpose

Implement Fisher's **macro** layer: the multi-day context that (A) **filters and sizes** the micro
setups — above all the **number-line chop filter** and the pivot-MA regime, the pieces our failed
momentum version lacked — and (B) provides its own multi-day **macro setups** (Reversal Trade, TRT/MAH,
sushi/outside-reversal). It consumes a chronological history of days (each = daily OHLC + the Micro
Engine's `DayResult`) and, for each day, produces a `MacroContext` plus the filtered/sized setup list.

## Success criteria
- `macro_context(i, history) -> MacroContext` for day `i`: the day's number-line score, the 30-day
  cumulative + trend state, the PMA regime, momentum sign, plus/minus classification, and any macro setups.
- `apply_macro(micro_setups, ctx) -> [Setup]`: drop setups that fight the regime/number-line (chop
  filter); boost conviction on macro confluence.
- Instrument-agnostic (reuses `InstrumentSpec`; no instrument specifics here). Offline-testable on
  synthetic day sequences.

## Non-goals (later sub-projects)
- Options expression (③), backtesting/costs (④), real data loading. Position *sizing in contracts* is
  ④'s `sizing.py`; here "size" = the conviction multiplier only.

---

## Inputs & data structures

```python
@dataclass
class DayEntry:
    date: str
    ohlc: tuple                 # (High, Low, Close) of the day  (Open optional, unused for now)
    day_result: DayResult       # from acd_micro.build_day  (has or_high/or_low/pivot_band/events/setups)

@dataclass
class MacroContext:
    date: str
    score: int                  # today's number-line value: +4/+2/0/-2/-4
    cum: int                    # 30-day cumulative number-line sum
    trend_state: str            # trend_up | trend_down | chop | neutral | system_failure
    regime: str                 # bullish | bearish | neutral | confused  (pivot-MA slopes)
    momentum: int               # +1 / 0 / -1  (close vs close 8 days ago)
    plus_minus: int             # +1 plus day / -1 minus day / 0
    macro_setups: list          # [Setup] with name in {reversal_trade, trt, sushi}
```
`history` = chronological `list[DayEntry]`; `i` = index of the day being contextualized (uses days ≤ i only — no lookahead).

---

## Part A — context & filters

### A1. Daily score (`ACD.md` D1; Ch.6 p.161)
`score_day(entry) -> int`, from the day's `DayResult.events` + close (`entry.ohlc[2]`) vs the OR:
- `+4` if a **C_up** held and close > or_high; `-4` if **C_down** held and close < or_low.
- else `+2` if an **A_up** held and close > or_high; `-2` if **A_down** held and close < or_low.
- else `0`. (Partial ±1/±3 cases deferred — flag.)

### A2. Number line (`ACD.md` D1; Glossary "Number line")
- `cum` = sum of the last **30** daily scores (≤ day i).
- `trend_state`: `trend_up` if `cum >= +9` and it was `>= +9` yesterday too (two consecutive days);
  `trend_down` symmetric at `-9`; `chop` if `abs(cum) < 4`; `system_failure` if a `±9` trend fired in
  the last ~3 days but `cum` has since fallen back below `±9` without price following through; else `neutral`.

### A3. Plus/minus day (`ACD.md` B4)
`plus_minus(entry) -> +1|-1|0`: `+1` if OR **below** pivot band AND close **above** it; `-1` if OR
**above** pivot band AND close **below** it; else `0`.

### A4. Pivot moving averages (`ACD.md` D4; Ch.5)
- Daily pivot per day = `(H+L+C)/3`. Compute rolling means over **14 / 30 / 50** days.
- Slope of each = sign(MA[i] − MA[i−1]) (or over a short window). Regime:
  all three up → `bullish`; all down → `bearish`; all ~flat/parallel → `neutral`; mixed → `confused`.

### A5. Momentum (`ACD.md` D5)
`momentum` = sign(close[i] − close[i−8]) → +1/0/-1.

### A6. The integrator — `apply_macro(setups, ctx)`
For each micro `Setup`:
- **Chop filter:** if `ctx.trend_state == "chop"` OR `ctx.regime == "confused"`, DROP trend/breakout
  setups (`a_held`, `a_through_pivot`, `c`, `c_through_pivot`, `late_day_c`, `first_hour`). **Keep the
  mean-reversion fades** (`failed_a`, `failed_a_pivot`, `failed_c`) — chop is where fades belong.
- **Regime gate:** in a clear trend (`trend_up`/`bullish`), drop setups whose `direction` fights it
  (and vice-versa for down). Neutral regime → keep, base conviction.
- **Confluence sizing:** `conviction += 1` for each of {trend_state agrees, regime agrees, momentum
  agrees, plus/minus agrees}, capped at 5. (Fisher: "maximize size when signals stack.")
Return the surviving, re-convicted setups.

---

## Part B — macro setups (over the daily sequence)

### B1. Reversal Trade (`ACD.md` D2; Ch.6 pp.139–144) — Fisher's best
Two consecutive same-direction **held A's** (two A_up or two A_down; only neutral/no-A days between,
≤ ~3), then the **next held A the opposite direction** beyond the extreme of the two (opposite A_down
below the lower A_up; opposite A_up above the higher A_down). Emit `Setup("reversal_trade", dir=opposite,
...)`. Invalidated by 3+ same-direction A's or any intervening A/C. Bigger the gap → higher conviction.

### B2. TRT / MAH (`ACD.md` D3; Glossary p.249)
After a sustained trend (proxy: `cum` strongly one-sided over the window), a **gap** to a new high/low
in the trend direction, a **held A against** the trend that day, and a **failed C** in the trend
direction → emit `Setup("trt", dir=against-trend, ...)`, stop = the failed-C level. (MAH = the same
after a holiday gap — flag as a `refs` note; holiday calendar deferred.)

### B3. Sushi Roll / Outside Reversal Week (`ACD.md` D5; Glossary p.248)
Over daily OHLC, compare the latest **5** days to the prior **5**: if the latest 5 take out both the
prior-5 high and low AND **close** beyond the prior-5 extreme → `Setup("sushi", dir=reversal, ...)`.
Bearish: latest-5 high > prior-5 high, latest-5 low < prior-5 low, last close < prior-5 low.

---

## Testing
Inline `__main__`. Build synthetic `history` sequences and assert: number line reaching +9 over days →
`trend_up`; a chop sequence → `chop` and `apply_macro` drops breakouts but keeps fades; each PMA regime
(construct pivot series with the right slopes); momentum flip; a reversal-trade sequence (two A_up then a
lower A_down); a bearish sushi roll; plus/minus classification. All offline (fabricated `DayEntry`s).

## Interfaces produced (for the checkpoint + ③)
- `macro_context(i, history) -> MacroContext`
- `apply_macro(micro_setups, ctx) -> [Setup]`
- Together with ①, these give the **full daily signal** (filtered, sized setups + macro setups) that the
  CHECKPOINT validates for edge before we build options.

## Honest flags
- Partial number-line scores (±1/±3), the MAH holiday calendar, and the exact chop/slope thresholds are
  **tunable/deferred** — implement the core (±2/±4, |cum|<4 chop, 3-way slope regime) first, sweep in ④.
- `system_failure` detection is heuristic; refine against real data in ④.
- Build in two commits: **(A) context+filters** (needed for the checkpoint) then **(B) macro setups**.
