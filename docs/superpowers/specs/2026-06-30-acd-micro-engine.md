# ACD Full Bot — Sub-project ①: The Micro Engine (Design Spec)

**Date:** 2026-06-30
**Status:** Approved (design) — pending implementation plan
**Rules source of truth:** `strategies/ACD.md` (complete, page-cited from Fisher's *The Logical Trader*)
**Part of:** the FULL ACD bot. Build order: **① Micro Engine (this)** → ② Macro Engine → checkpoint (validate signal edge) → ③ Options Overlay → ④ Backtest/Eval.

---

## Purpose

Implement the **complete intraday reference-point system** of Fisher's ACD, faithfully and
instrument-agnostically. The engine consumes one day's intraday price path plus the prior day's
H/L/C, and emits a structured, faithful record of *what ACD saw that day* — the levels, the events
that actually occurred, and the qualified trade setups. It does **not** place trades, filter by macro
context, size positions, or touch options — those are later sub-projects. It is the foundation
everything else reads.

## Success criteria

- Given a day's bars + prior H/L/C + an `InstrumentSpec`, produce a `DayResult` containing the OR,
  the pivot band, the ordered list of ACD **events**, and the list of qualified **setups**.
- Every micro setup in `ACD.md` Part A/C is implemented with its exact entry/stop/direction rules.
- Fully instrument-agnostic: all instrument specifics live in `InstrumentSpec`; SPX is just one spec.
- Fully offline-testable: one synthetic intraday path per setup, inline `__main__` asserts.

## Non-goals (explicitly deferred to later sub-projects)

- The number-line **scoring** and all macro filters/regimes (② Macro Engine) — but the Micro Engine
  emits the raw `events` the number line will score.
- Position sizing, options expression, backtesting, real data loading.
- The rarer/ill-defined setups may be flagged but are still implemented where a clean rule exists.

---

## Architecture — the four-stage pipeline

```
 intraday bars [(time,"HH:MM", price)] + prior-day (H,L,C) + InstrumentSpec
        │
  Stage 1  LEVELS        → or_high, or_low; A_up, A_down, C_up, C_down; B, D; pivot_band   (pure math)
        │
  Stage 2  EVENTS        → walk bars chronologically, detect (in sequence):
        │                   A_up/A_down (held ≥ hold_time; one A per day),
        │                   failed_A_up/failed_A_down (touched, not held, reversed),
        │                   B reached (bias→neutral),
        │                   C_up/C_down (held; only after the opposite-consuming A),
        │                   failed_C_up/failed_C_down, D reached
        │
  Stage 3  PIVOT CONTEXT → OR vs pivot (above/below/inside); each A/C "through the pivot"?
        │
  Stage 4  SETUPS        → qualify events+pivot into trades with direction/entry/stop/conviction/horizon
        ▼
   DayResult
```

## Data structures

```python
@dataclass
class InstrumentSpec:
    symbol: str
    or_minutes: int = 15               # opening-range length (SPX/Nasdaq=15; stocks=20; commodities=5)
    a_pct: float = 0.0018              # A-value as fraction of price (Fisher's formula is proprietary → tune)
    c_pct: float = 0.0021              # C-value as fraction of price (stocks: c_pct == a_pct)
    hold_fraction: float = 0.5         # signal must hold >= hold_fraction * or_minutes
    cutoff: str = "12:00"              # latest A entry
    tick: float = 0.01                 # min price increment (for B/D = 1 tick beyond OR)
    session_open: str = "09:30"
    session_close: str = "16:00"

@dataclass
class ACDEvent:
    type: str        # A_up|A_down|C_up|C_down|failed_A_up|failed_A_down|failed_C_up|failed_C_down|B|D
    time: str        # "HH:MM"
    price: float
    held: bool       # did it satisfy the hold-time rule (False for failed_* / B / D)

@dataclass
class Setup:
    name: str        # a_held|a_through_pivot|c|c_through_pivot|late_day_c|failed_a|failed_a_pivot|failed_c|first_hour
    direction: str   # long|short
    entry_time: str
    entry_price: float
    stop: float
    conviction: int  # 1..3 (by confluence; see Conviction)
    horizon: str     # intraday|overnight
    refs: dict       # named reference levels used (a, c, b, d, pivot_low, pivot_high, or_high, or_low)

@dataclass
class DayResult:
    date: str
    or_high: float
    or_low: float
    pivot_band: tuple           # (low, high)
    events: list                # [ACDEvent]
    setups: list                # [Setup]
```

---

## Stage 1 — Levels (pure math; `ACD.md` A1–A3, B1)

- Opening range over `[session_open, session_open + or_minutes]` → `or_high`, `or_low`.
- `a = mid * a_pct` where `mid = (or_high + or_low)/2`; `c = mid * c_pct`. (For stocks `c_pct == a_pct`.)
- `A_up = or_high + a`, `A_down = or_low − a`, `C_up = or_high + c`, `C_down = or_low − c`.
- `B = or_low` (stop for A-up; neutral level) and `or_high` (for A-down) — Glossary p.246. `D = opposite OR edge + 1 tick` (stop for C).
- `pivot_band` from prior `(H,L,C)`: `pivot=(H+L+C)/3`, `second=(H+L)/2`, `diff=|pivot−second|`, band `=(pivot−diff, pivot+diff)`. (Reuse `acd_rules.pivot_range`.)
- `hold_bars_minutes = hold_fraction * or_minutes` (15-min OR → 7.5 min).

## Stage 2 — Events (stateful walk; `ACD.md` A2, A4)

Walk bars chronologically after the OR window, ≤ `cutoff` for the A:
- **A_up / A_down:** first price to reach `A_up` (or `A_down`) that **holds ≥ hold_time** beyond the level (reuse the verified hold-clock from `acd_rules.detect_a`, incl. the entry-bar-still-beyond guard). Emit `ACDEvent(A_up, held=True)`. **One A per day** — once emitted, the opposite A cannot be emitted.
- **failed_A_up / failed_A_down:** price reaches the A level but does **not** hold (snaps back inside/through) → emit `failed_A_*` (held=False). A failed A does **not** consume the one-A rule; the opposite A remains eligible.
- **B:** after an A, price returns to the opposite OR edge → emit `B` (bias neutral).
- **C_up / C_down:** only **after** the consuming A (C_down only after A_up; C_up only after A_down); price reaches `C_*` and holds ≥ hold_time → emit `C_*` (held=True).
- **failed_C_*:** C level reached but not held → emit `failed_C_*`.
- **D:** after a C, price hits the opposite extreme +1 tick → emit `D` ("done for the day").

## Stage 3 — Pivot context (`ACD.md` B2, C)

- `or_vs_pivot`: OR entirely above / below / straddling the pivot band.
- For each A/C event, `through_pivot = True` if the level and the move clear the **entire** pivot band in that direction.

## Stage 4 — Setups (`ACD.md` Part C; Glossary)

Qualify events + pivot context into `Setup`s (a day may yield several):

| Setup | Trigger | Direction | Entry | Stop | Conviction | Horizon |
|---|---|---|---|---|---|---|
| **a_held** | A held | dir of A | at confirm | opposite OR edge (B/D) | 1 | intraday |
| **a_through_pivot** | A held **and** through pivot | dir of A | at confirm | far side of pivot band | 2 | intraday |
| **c** | C held (after opposite A) | dir of C | at confirm | Point D | 1 | intraday |
| **c_through_pivot** | C held **and** through pivot | dir of C | at confirm | far side of pivot band | 3 | intraday |
| **late_day_c** | c_through_pivot in last portion of session | dir of C | at confirm | far side of pivot band | 3 | overnight *(only if close beyond both pivot and C)* |
| **failed_a** | failed_A | **opposite** of the A | at A level | just beyond A level | 1 | intraday |
| **failed_a_pivot** | failed_A at/within pivot band | opposite of A | at A level | far side of pivot band | 2 | intraday |
| **failed_c** *(treacherous)* | failed_C | toward OR | at C level | **none** → time-stop only | 1 | intraday |
| **first_hour** | pivot band engulfs first-hour high/low, A in first hour, close within 15% of extreme in trade dir | dir of A | first-hour close | first-hour extreme | 2 | intraday |

Time-stop attached to every setup: exit if not working within `2×`–`3× or_minutes` (per `ACD.md` B2/C).

## Conviction model (`ACD.md` C — "maximize size, minimize risk")

`conviction` counts confluence at signal time: base 1 (A or C alone); +1 if **through the pivot**
(tighter stop); +1 if it is a C-through-pivot / late-day C (Fisher's highest-probability). Capped at 3.
Macro confluence (number line, PMAs) adds further in sub-project ② — not here.

## Instrument-agnostic config

`InstrumentSpec` holds everything instrument-specific. Ship `SPX = InstrumentSpec(symbol="SPX",
or_minutes=15, a_pct=0.0018, c_pct=0.0021, cutoff="12:00")` as the default. A/C as **% of price**
(tunable; Fisher's formula is proprietary — anchor at his S&P numbers, sweep later in ④). Any future
instrument is just a new spec — no engine change.

## Testing

Inline `if __name__ == "__main__"` (house convention). **One synthetic intraday path per setup**, each a
hand-built list of `(time, price)` bars + prior H/L/C + a test `InstrumentSpec`, asserting the engine
emits exactly the expected `events` and `setups`. Cases: a_held, a_through_pivot, c, c_through_pivot,
late_day_c, failed_a (rubber band), failed_a_pivot, failed_c, first_hour, and a no-signal chop day.
All offline; no data needed.

## Interfaces produced (consumed by later sub-projects)

- `build_day(bars, prior_hlc, spec) -> DayResult` — the engine entry point.
- `DayResult.events` → the ② Macro number-line scorer.
- `DayResult.setups` → the ② Macro filter/sizer, then ③ Options overlay.

## Honest flags

- **A/C values** are our reconstruction (% of price), anchored at Fisher's Appendix numbers and to be
  **backtest-tuned** in ④; his exact volatility formula is proprietary (`ACD.md` A2/E).
- **failed_c (treacherous)** and any system-failure fades have **no clean stop** in the book — implement
  with a mandatory **time-stop** and flag conviction 1.
- The engine reuses `acd_rules.py` primitives (opening range, hold-clock, pivot formula) but supersedes
  its partial `build_acd_signal`; `acd_rules.py` is left intact for the shelved momentum experiments.
