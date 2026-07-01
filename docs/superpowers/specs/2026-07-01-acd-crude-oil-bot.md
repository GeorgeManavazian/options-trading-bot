# Spec — ACD on Crude Oil (CL): the trending-instrument test

**Date:** 2026-07-01
**Status:** approved (design), pending spec review
**Sub-project:** the ACD refine sprint, lever (d) — run the full, instrument-agnostic
ACD bot on a **trending** market (crude oil futures), isolated from the SPX/V5 work.

## 1. Purpose

Every ACD result so far is on **SPX**, which *mean-reverts* — so the fades/reversals
worked and the **breakout half stayed flat** (checkpoint: breakouts ~0 edge on SPX).
The whole thesis (from the user's contact who trades ACD for a living, and from
Fisher's own firm) is that ACD's edge lives in instruments that **TREND** —
commodities, energy, futures. This sub-project runs the **full ACD engine we already
built** (all 9 micro setups + the macro number-line/regime/reversal layer) on **crude
oil (CL)** and asks the payoff question:

> **Does the full ACD signal have a real directional edge on a trending instrument —
> and does the breakout half finally light up where SPX suppressed it?**

**Phase 1 (this spec) = signal only.** Trade the **future itself** (long/short), no
options. This is the cheap, honest checkpoint — the crude analogue of
`diag_full_signal.py`. **Only if the signal shows an edge do we spend on phase-2
options** (a separate later spec).

Non-goals: deploying anything; the options overlay; live trading. This is a
measurement slice, graded by `backtest-expert`, honestly caveated.

## 2. Hard constraint — isolation from V5

The user's explicit requirement: crude-market tweaks must **never** be able to break
the working SPX/V5 bot.

- The signal engine (`acd_micro.py`, `acd_macro.py`) is already **instrument-agnostic**
  via `InstrumentSpec`. We **reuse it unchanged** — we do NOT edit shared engine files.
- **All crude-specific code lives in new files** (a CL `InstrumentSpec` instance, a
  Databento loader, a CL backtest driver). Creating `CL = InstrumentSpec(symbol="CL",
  ...)` in a new module does not modify `acd_micro`.
- **If** crude ever needs an actual *rule* change (not just a parameter), we **fork
  that function into a CL-only copy** rather than editing the shared engine. Shared
  code only changes if the change is provably instrument-agnostic and re-verified
  against the SPX self-tests.
- V5's files (`backtest_fade_variants.py`, `trade_ledger.py`, its config) are **never
  touched**.

## 3. Data layer — Databento (CME `GLBX.MDP3`)

Confirmed live with our key (free metadata/cost calls):
- **CL 1-minute OHLCV** available **2010-06-06 → present** (16 years).
- Continuous front-month symbology `CL.c.0`, `stype_in="continuous"` works.
- **Cost:** ~$10 (1-min) + ~$0.03 (daily) for 2018→2026; full 16 yrs ≈ $20 — all
  inside the **$125 free signup credit → $0 out of pocket**. **Decision: pull the full
  ~16-year history** (turns the recurring "only 3 years" grader flag into a strength).

**`bot/load_cl_databento.py`** — pull + cache, offline thereafter (same pattern as
`load_ivolai.py` / `load_ivol_intraday.py`):
- `pull_cl_minutes(start, end)` → `ohlcv-1m` for `CL.c.0`; `pull_cl_daily(start, end)`
  → `ohlcv-1d`. Cache to `data_cache/CL_1m_<start>_<end>.csv` and
  `data_cache/CL_1d.csv`; skip re-pull if cached (zero API/credit on re-runs).
- **Timezone:** Databento stamps bars in **UTC nanoseconds at bar-open**. Convert to
  **America/New_York** (DST-aware) so `session_open` is real ET. Group bars by the ET
  calendar date = the trading day.
- **Shape to the engine's contract:** `daily_bars(date) -> [(("HH:MM"), price), ...]`
  in ET (what `acd_micro.analyze_day` consumes — a per-day list of (time, price)); and
  `daily_ohlc(date) -> (o,h,l,c)` (what `acd_macro`'s `DayEntry` consumes). Provide a
  `load_cl_history()` that yields the ordered `DayEntry` stream the macro layer needs.
- **RTH window:** feed the micro engine bars from `session_open` (09:00 ET) through a
  configurable close (default 16:00 ET); the opening range, A-hold, `cutoff`, and
  `late_day` are all evaluated in ET.
- Validate at the seam: drop days with no bars / gaps across the OR window (reuse the
  sparse-bar guard lesson); assert bars are sorted and within the session.

**Continuous-contract note:** use the **ratio-adjusted** continuous series (preserves %
moves across roll dates). ACD's A/C values are `% of the OR midpoint` and pivots come
from the *same* series' daily H/L/C, so everything is internally consistent on the
adjusted series. Roll days may leave minor artifacts — acceptable for a phase-1 signal
check; noted as a caveat.

## 4. The CL `InstrumentSpec`

A new instance in a new file (`bot/acd_cl.py` or similar), NOT an edit to `acd_micro`:

```
CL = InstrumentSpec(
    symbol="CL",
    session_open="09:00",   # crude RTH open, ET (confirmed decision; configurable)
    or_minutes=15,          # start at Fisher's 15-min; may tune
    a_pct=?, c_pct=?,       # % of OR midpoint — TUNE for crude's vol (SPX=0.18%/0.21%)
    hold_fraction=0.5,
    cutoff="12:00",         # latest A entry (ET) — may widen for crude
    tick=0.01,              # CL min tick = $0.01
    late_day="14:30",       # C-through-pivot at/after -> overnight carry
)
```

- **A/C tuning:** Fisher withholds the exact formula; we anchor at % of price and
  **backtest-sweep** a small, structurally-honest set (e.g. A ∈ {0.15%, 0.25%, 0.4%},
  C proportional), judged by **cross-year robustness**, NOT a single curve-fit value
  (the overfitting discipline from every prior sub-project). Crude is more volatile
  than SPX, so expect larger values.
- Everything else stays the engine default until the backtest says otherwise.

## 5. Phase-1 backtest — `bot/backtest_acd_cl.py`

The crude analogue of `diag_full_signal.py` + a simple underlying P&L (no options):

1. **Build history:** for each trading day, `acd_micro.analyze_day(daily_bars(date),
   CL) -> DayResult`; wrap into `DayEntry(date, ohlc, DayResult)`; run the macro layer
   (`macro_context` + `apply_macro`) to get filtered, confluence-sized signals — the
   *full* method, exactly as on SPX.
2. **Trade the future:** each qualified signal enters at its `entry_price` (the
   intraday level the engine emitted) in its `direction`. Phase-1 exit rule =
   **hold-to-horizon** (the recurring, hard-won lesson that hold beats too-tight
   stops), with the entry-day **B stop** kept as the disaster brake. Report a small
   horizon set (same-day close, +1d, +5d) so we can see where the edge concentrates —
   mirroring the checkpoint.
3. **P&L:** per contract, `pnl = (exit − entry) * direction * point_value`
   (CL point = $1000/contract); also report **return as % of entry** (account-agnostic,
   like every prior result). Slippage-aware: sweep 0 / 1 / 2 / 5 ticks per side.
4. **Report, split by signal family** — the decisive cut:
   - **Breakouts** (`a_held`, `a_through_pivot`, `c`, `c_through_pivot`, `first_hour`,
     late-day C) — *do these finally work on a trending market?*
   - **Fades / reversals** (`failed_a`, `failed_a_pivot`, `failed_c`, macro
     reversal/sushi) — do they still work, or does trending kill the mean-reversion?
   - Per family and overall: n, win rate, avg move, total-on-risk, maxDD, risk-adj
     (total/|maxDD|), Sharpe, **per-year** breakdown, slippage sweep. Reuse the
     `_stats` / `_with_slip` / report shape from `backtest_acd_full`.
5. **Grade** via the `backtest-expert` skill → `results/backtest_cl_eval_2026-07-01.md`.

**Reuses (no new copies of):** `analyze_day`/`InstrumentSpec` (`acd_micro`),
`macro_context`/`apply_macro`/`DayEntry` (`acd_macro`), `max_drawdown` (`backtest`),
and the stats/slippage/report helpers from `backtest_acd_full`. New code is only the
Databento loader, the CL spec, and the driver.

## 6. Honesty caveats (logged in the eval, not hidden)

- **Signal ≠ tradeable options P&L.** Phase 1 measures the *underlying* edge only; a
  positive result licenses phase-2 options, it does not prove a deployable options
  strategy (the SPX arc taught exactly this).
- **Continuous back-adjustment** can leave small roll-date artifacts; ratio-adjusted
  minimizes % distortion but is not the literal tradable price on any single day.
- **A/C tuning adds parameters.** Judge on cross-year robustness; a value that only
  works in one regime is curve-fit, not an edge. 16 years / multiple crude regimes
  (2014-16 crash, 2020 negative-price shock, 2022 spike) is the robustness test.
- **2020 negative crude** is a real data event — the loader/backtest must not choke on
  negative prices; flag any day around 2020-04-20 explicitly.
- **Point value / contract size** is CL-specific ($1000/pt); % return is the
  cross-instrument-comparable metric.

## 7. Success criteria

- Loader pulls + caches CL 1-min and daily history within the free credit; offline
  thereafter; self-tests green.
- The full ACD engine runs end-to-end on CL and produces honest per-family, per-year
  metrics with a slippage sweep.
- A `backtest-expert` grade with the same rigor lens used on every prior slice.
- A clear, honest verdict: **does the full ACD method (and specifically its breakout
  half) have a directional edge on trending crude** — a green light for phase-2
  options, or a rigorously-tested negative. Either outcome is a real result and
  vindicates (or bounds) the instrument-agnostic thesis.

## 8. Testing

- Each new module: inline `__main__` assert self-tests (house style; no pytest)
  **before** any real pull. Loader: UTC→ET conversion (incl. a DST boundary),
  day-grouping, and shape correctness on mock bars. CL spec: sane values. Driver:
  runs on a tiny mock history and produces the report structure.
- The driver validates at the data seam: skip no-bar / gapped-OR days, handle negative
  prices, count drops (like `backtest_acd_full`'s `dropped`).
- Opus whole-branch review before merge (has caught a real bug every prior sub-project).

## 9. Out of scope (follow-ups)

- **Phase 2:** the options overlay on crude (futures options) — separate spec; data
  from IVolatility's daily futures options (possibly within the free download
  allowance) or Databento futures options.
- Additional trending instruments (gold, nat gas, grains) — same engine, new specs.
- Walk-forward / formal out-of-sample of the A/C tuning (the standing V5 debt applies
  here too if a tuned config is chosen).
- Intraday exit management / active stops beyond the entry-day B stop.
