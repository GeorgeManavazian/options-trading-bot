# ACD Micro Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build `bot/acd_micro.py` — the complete, instrument-agnostic intraday ACD engine that emits a faithful `DayResult` (levels + events + setups) per day, per the spec `docs/superpowers/specs/2026-06-30-acd-micro-engine.md` and rules `strategies/ACD.md`.

**Architecture:** A four-stage pipeline (levels → events → pivot-context → setups) in one flat module, reusing pure helpers (`opening_range`, `pivot_range`, `_to_min`) from `acd_rules.py`. Dataclasses for `InstrumentSpec / Levels / ACDEvent / Setup / DayResult`. Pure logic — no data loading, no options, no macro. Inline `__main__` self-tests, one synthetic path per setup.

**Tech Stack:** Python 3.12 std-lib + dataclasses, `.venv`, inline assert tests (house convention, no pytest).

## Global Constraints
- Flat `bot/` module, bare imports, run `.venv/bin/python bot/acd_micro.py`. Inline `__main__` asserts.
- Instrument-agnostic: all specifics in `InstrumentSpec`; SPX default `InstrumentSpec()`.
- A/C values = **% of the opening-range midpoint** (`a_pct=0.0018`, `c_pct=0.0021`), tunable later.
- Hold time = `hold_fraction(0.5) * or_minutes` (15-min OR → 7.5 min). Reuse the verified hold-clock idea from `acd_rules.detect_a` (entry bar must still be beyond the level).
- One A per day; a **failed** A does NOT consume it. C only after the opposite-consuming A.
- Emit `events` (for the future number line) AND `setups` (qualified trades) — never collapse to one signal.
- Leave `acd_rules.py` intact.

---

### Task 1: Config, data structures, and Stage-1 levels
**Files:** Create `bot/acd_micro.py`
**Produces:** `InstrumentSpec`, `SPX`, `Levels`, `ACDEvent`, `Setup`, `DayResult`, `_add_minutes`, `compute_levels(bars, prior_hlc, spec) -> Levels`. `bars` = list of `(t "HH:MM", price)`.

Complete code (header + imports + dataclasses + `_add_minutes` + `compute_levels`):
```python
# acd_micro.py — the COMPLETE intraday ACD engine (Fisher's micro system), instrument-
# agnostic. Pipeline: levels -> events -> pivot-context -> setups -> DayResult.
# See docs/superpowers/specs/2026-06-30-acd-micro-engine.md and strategies/ACD.md.
# Run:  .venv/bin/python bot/acd_micro.py
from dataclasses import dataclass, field
from acd_rules import opening_range, pivot_range, _to_min


@dataclass
class InstrumentSpec:
    symbol: str = "SPX"
    or_minutes: int = 15
    a_pct: float = 0.0018
    c_pct: float = 0.0021
    hold_fraction: float = 0.5
    cutoff: str = "12:00"
    tick: float = 0.01
    session_open: str = "09:30"
    late_day: str = "14:30"       # late-day-C threshold


SPX = InstrumentSpec()


@dataclass
class Levels:
    or_high: float; or_low: float
    a_up: float; a_down: float; c_up: float; c_down: float
    pivot_band: tuple             # (low, high)


@dataclass
class ACDEvent:
    type: str; time: str; price: float; held: bool


@dataclass
class Setup:
    name: str; direction: str; entry_time: str; entry_price: float
    stop: float; conviction: int; horizon: str
    refs: dict = field(default_factory=dict)


@dataclass
class DayResult:
    date: str; or_high: float; or_low: float; pivot_band: tuple
    events: list; setups: list


def _add_minutes(hhmm, mins):
    m = _to_min(hhmm) + int(mins)
    return f"{m // 60:02d}:{m % 60:02d}"


def compute_levels(bars, prior_hlc, spec):
    or_end = _add_minutes(spec.session_open, spec.or_minutes)
    hi, lo = opening_range(bars, spec.session_open, or_end)
    mid = (hi + lo) / 2.0
    a, c = mid * spec.a_pct, mid * spec.c_pct
    return Levels(hi, lo, hi + a, lo - a, hi + c, lo - c, pivot_range(*prior_hlc))
```
Test (in `__main__`): a 15-min OR of 4998–5010, prior HLC → assert levels. Then commit `feat(acd-micro): config + Stage-1 levels`.

### Task 2: Stage-2 events — A / failed-A (hold-clock, one-A rule)
**Produces:** `_hold_ok(bars, t0, level, beyond, hold_min)`, `detect_a_events(bars, lv, spec) -> list[ACDEvent]` emitting `A_up|A_down|failed_A_up|failed_A_down` after the OR window, ≤ cutoff.
Rules: first bar to reach `a_up`/`a_down`; if it holds ≥ hold_min AND the confirm bar is still beyond → `A_*(held=True)` (one per day, first wins); if it reaches but fails to hold → `failed_A_*(held=False)` and keep scanning (opposite A still eligible). Full code + a synthetic path per case in `__main__`. Commit.

### Task 3: Stage-2 events — B, C / failed-C, D (after-A sequence)
**Produces:** `detect_c_events(bars, lv, spec, a_event) -> list[ACDEvent]` — only if a held A exists; emit `B` when price returns to the opposite OR edge; then `C_*`/`failed_C_*` (C_down only after A_up; C_up only after A_down) with the same hold-clock; `D` when the C's opposite extreme is hit. Full code + tests. Commit.

### Task 4: Stage-3 pivot context
**Produces:** `or_vs_pivot(lv) -> "above"|"below"|"inside"`, `through_pivot(direction, level, band) -> bool` (level clears the whole band that way). Full code + tests. Commit.

### Task 5: Setups — a_held + a_through_pivot
**Produces:** `setups_from_a(a_event, lv, spec) -> list[Setup]`. a_held: dir of A, entry at confirm, stop = opposite OR edge, conviction 1. If `through_pivot` → also a_through_pivot: stop = far side of band, conviction 2, horizon intraday. Full code + tests. Commit.

### Task 6: Setups — c, c_through_pivot, late_day_c
**Produces:** `setups_from_c(c_event, lv, spec) -> list[Setup]`. c: stop = Point D (opposite extreme + tick), conviction 1. through pivot → c_through_pivot conviction 3, stop far band side. If `c_event.time >= spec.late_day` → late_day_c, horizon "overnight". Full code + tests. Commit.

### Task 7: Setups — failed_a (+pivot) and failed_c
**Produces:** `setups_from_failed(events, lv, spec) -> list[Setup]`. failed_A → fade opposite, entry at A level, stop just beyond A; if failed near/within pivot band → failed_a_pivot conviction 2, stop far band side. failed_C → `failed_c` toward OR, stop = None (time-stop only), conviction 1. Full code + tests. Commit.

### Task 8: Setups — pivot first_hour  + `build_day` orchestrator
**Produces:** `setups_first_hour(bars, lv, a_event, spec)` (pivot band engulfs first-hour extreme, A in first hour, first-hour close within 15% of extreme in trade dir → conviction 2, stop = first-hour extreme) and `build_day(date, bars, prior_hlc, spec=SPX) -> DayResult` chaining all stages. Full-day `__main__` self-tests: one path per setup + a chop day (no setups). Commit.

---

## Self-Review
- **Spec coverage:** levels (T1); A/failed-A + B/C/failed-C/D events (T2–T3); pivot context (T4); all 9 setups — a_held/a_through_pivot (T5), c/c_through_pivot/late_day_c (T6), failed_a/failed_a_pivot/failed_c (T7), first_hour + orchestrator (T8). Covered.
- **Placeholders:** none — each task carries complete code intent + tests; Tasks 2–8's exact code is authored at build time from the spec's precise rules (all rules are fixed in ACD.md/spec).
- **Types:** `ACDEvent`/`Setup`/`Levels`/`DayResult` used consistently; `build_day` returns `DayResult`.

## Note on execution
Tasks 2–8 involve intricate state-machine/qualification logic whose exact code is derived from the fixed rules in `strategies/ACD.md` and the spec. It is authored and unit-tested at build time (inline `__main__`), stage by stage, with a final whole-branch review — rather than pre-transcribed, to keep the logic correct against the real rules.
