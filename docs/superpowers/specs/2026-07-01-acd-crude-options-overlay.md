# Spec — ACD on Crude Oil (CL), Phase 2: the options overlay

**Date:** 2026-07-01
**Status:** approved (design), pending spec review
**Sub-project:** phase 2 of the crude-oil ACD bot — express the phase-1 SAME-DAY signal edge as real options with real fills and costs.

## 1. Purpose

Phase 1 proved the full ACD **signal** has a strong, cost-robust directional edge on crude, best in the **same-day** hold (+1043% on risk, 64% win, risk-adj +31.73, PF 2.19, 79/Deploy, breakouts finally positive). But phase 1 traded the *underlying future*. This phase answers the deployable question:

> **Does the same-day edge survive being expressed as OPTIONS, with real bid/ask fills and transaction costs?**

This is the exact bar the SPX fade edge (④b→V5) had to clear. A positive underlying signal does NOT guarantee a positive options result after premium, spread, and theta — that is what this phase measures.

Non-goal: live trading; parameter optimization of the signal (phase-1 params stay a-priori); the multi-day breakout-trend edge (a possible later phase). Graded by `backtest-expert`, honestly caveated.

## 2. What we test

The identical phase-1 **same-day** signals (ALL families — fades + breakouts + first-hour + macro that are same-day horizon), each expressed as a **directional debit spread**, entered at the signal's intraday time and exited the SAME day.

- **Structure = directional debit spread** (defined risk): **bull call spread** for a long signal (long ATM call, short ATM+width call), **bear put spread** for a short signal (long ATM put, short ATM−width put). Width ≈ **$2** (a few strikes; tunable).
- **Deliberate change from `acd_options` policy:** the old policy maps breakouts→*credit* spreads (a no-movement bet). A same-day breakout is a *directional continuation* bet, so both fades AND breakouts get **debit** spreads here. Uniform debit treatment → reuse `acd_fade_pricing.py` wholesale.
- **Expiry = nearest crude option expiry ≥ signal date** (weeklies included → shortest DTE → most directional bang per premium). Crude options are days-to-weeks out (NOT 0DTE), so one-day theta is small; we capture the intraday directional move and **close the spread at the same-day close** (we do NOT hold to expiry).
- **Two exits, reported side by side** (like ④b): (a) **hold-to-same-day-close** (`close_value` at the last bar); (b) **active target/stop ±50%** (`exit_target_stop` walking the intraday cost-to-close series). ④b found the active exit cut 0DTE drawdown ~5× — let the data decide for crude.

## 3. Data — Databento crude options (CME `GLBX.MDP3`, parent `LO`)

Confirmed live:
- **Options exist + are cheap.** `LO` = American options on WTI; ~24.5k contracts/day, each carrying `instrument_class` (C/P), `strike_price`, `expiration`, `underlying` (the CL future) in the **`definition`** schema. Resolve legs by symbol.
- **Fills = `bbo-1m` (real NBBO).** Per-minute top-of-book `bid_px_00`/`ask_px_00` (dense, ~1337 rows/day). This is the honest fill source (buy at ask, sell at bid) that `acd_fade_pricing` expects. **NOT `ohlcv-1m`** (that's last-trade only, no bid/ask → optimistic).
- **Cost:** `bbo-1m` = **$0.0018 / option-contract-day**; targeted pull of ~2,554 signals × 2 legs ≈ **~$9**, inside the remaining free credit. Pull only the legs each signal needs (the ④b pattern), never the whole chain.
- **Pull by symbol:** `get_range(dataset="GLBX.MDP3", symbols=[raw_symbol], stype_in="raw_symbol", schema="bbo-1m", start=D, end=D+1)`; UTC `ts_event` index → convert to ET like the futures loader.

## 4. Architecture — reuse the seam

**Signals (reuse phase 1):** `backtest_acd_cl.build_cl_history` gives the `DayEntry` history; then a **small phase-2 collector** (new, in the driver) iterates it, runs `macro_context` + `apply_macro`, and keeps the FULL `Setup` for each filtered micro setup — crucially including **`entry_time`**, which `diag_full_signal.collect_signals` drops (it returns only date/direction/entry_price/name/conviction). We need `entry_time` to price the intraday option entry. This matches phase-1's headline set (all filtered micro setups, exited same-day); we do NOT edit the shared `collect_signals`.

**Pricing (reuse ④b):** `acd_fade_pricing.spread_entry` (net debit = long.ask − short.bid at first bar ≥ entry_time), `close_value` (long.bid − short.ask at the close bar), `exit_target_stop` (active exit on the intraday cost-to-close series). P&L per contract = `(exit_value − debit) * 1000` (CL option point = $1000); return = P&L / (debit·1000); `max_loss = debit·1000`.

### New components (isolated — new files only; phase-1 + V5 untouched)

**1. `bot/load_cl_options_databento.py`** — crude-options loader:
- `resolve_legs(date, direction, entry_price, width) -> (long_sym, short_sym, expiry, kind)` — pull/cache the day's `LO` **definition**, pick the nearest expiry ≥ date, snap ATM to the nearest listed strike to `entry_price`, pick short = ATM ± width in the signal direction, return the two `raw_symbol`s (+ kind = bull_call/bear_put).
- `pull_leg(symbol, date) -> path` and `leg_bars(symbol, date) -> [(HH:MM, bid, ask), ...]` — pull/cache one leg's `bbo-1m` for one ET day; offline reader (maps `bid_px_00`/`ask_px_00`, ET-windowed). Same cache/skip discipline as `load_cl_databento`.

**2. `bot/pull_cl_options.py`** — resumable background pull (the ④b `pull_fade_data` analogue): for each same-day signal, `resolve_legs` → `pull_leg` both legs. `~5,100` leg-days, cache-skips done ones, logs progress, cost-checked (`metadata.get_cost`) before running. After one run, the backtest is fully offline.

**3. `bot/backtest_cl_options.py`** — the phase-2 driver (offline on cache):
- Build same-day signals; for each, `resolve_legs` → read cached leg bars → `spread_entry` (debit at entry_time) → both exits (`close_value` @ close; `exit_target_stop` ±50%). Drop degenerate positions (zero/inverted/missing debit or bars) with a counter.
- **Report** per exit-style: n, win rate, total-on-risk, maxDD, risk-adj (total/|maxDD|), Sharpe, **per family** (BREAKOUT vs FADES), **per year**, and a **slippage sweep** (extra ¢/leg haircut on entry+exit) — mirroring `backtest_acd_full.report` / `backtest_acd_cl.report_pnl`.
- **Grade** via `backtest-expert` → `results/backtest_cl_options_eval_2026-07-01.md`.

### Reuses (no new copies)
`build_cl_history` (`backtest_acd_cl`), `collect_signals` (`diag_full_signal`), `BREAKOUT`/`FADES` (`acd_macro`), `spread_entry`/`close_value`/`exit_target_stop` (`acd_fade_pricing`), `nearest` (`orb_rules`), `max_drawdown` (`backtest`), the loader/ET/cache patterns from `load_cl_databento`, and the stats/slippage/report shape from `backtest_acd_cl`.

## 5. Data flow (one signal)

```
same-day Setup (date, entry_time, entry_price=underlying, direction)
  -> resolve_legs: nearest LO expiry >= date; long=nearest listed strike to entry_price;
                   short = long ± width (dir);  kind = bull_call | bear_put
  -> cached bbo-1m bars for each leg (ET-windowed)  [pull once, offline after]
  -> debit = spread_entry(long_bars, short_bars, entry_time)     [long.ask - short.bid @ entry minute]
  -> exit A: close_value(structure, long_close_row, short_close_row)   [long.bid - short.ask @ close]
     exit B: exit_target_stop(debit, cost_to_close_series, close_val, 0.5, 0.5)
  -> pnl = (exit_value - debit)*1000 ;  ret = pnl / (debit*1000)
```

## 6. Honesty caveats (logged in the eval)

- **Fills use real NBBO** (`bbo-1m`), buy-at-ask/sell-at-bid; the slippage sweep stress-tests worse fills. This is the honest bar; last-trade prices were deliberately rejected.
- **Sparse/illiquid option minutes:** crude options can be thin intraday. `spread_entry` uses the first bar ≥ entry_time; drop signals with no fillable bar (counted). A high drop rate is itself a finding (the edge isn't tradeable where options don't quote).
- **Same-day close ≠ literal settlement:** we sell the spread at the last quoted bar of the ET session, not an official settle. Reasonable for a same-day directional exit; noted.
- **Nearest-expiry DTE varies** (days to ~weeks); one-day theta is small but nonzero and IS captured (real bid/ask over the day).
- **Signal params a-priori** (phase-1 CL spec, untuned) — carried over; no re-optimization here, so no new overfitting surface beyond the structure/width/exit choices (report robustness across them, don't curve-fit one cell).
- **Underlying signal edge was strong; options may erode it** — that erosion is exactly what this measures. A weaker or negative options result is a real, publishable finding, not a failure to hide.

## 7. Success criteria

- Loader resolves legs + pulls/caches `bbo-1m` within the free credit; offline thereafter; self-tests green.
- The driver produces honest per-family/per-year metrics + slippage sweep for BOTH exit styles, on the same-day signals.
- A `backtest-expert` grade with the same rigor lens as every prior slice.
- A clear verdict: **does the crude same-day edge survive as options-with-costs, and which exit (hold-to-close vs active) monetizes it best — or is it a rigorously-tested negative.** Either is a real result and sets up (or bounds) live paper trading.

## 8. Testing

- Each new module: inline `__main__` assert self-tests (house style; no pytest) on MOCK bars/definitions BEFORE any real pull: `resolve_legs` picks nearest expiry + correct strikes + kind; `leg_bars` ET-windows and maps bid/ask; the driver prices one mock signal end-to-end (debit > 0, both exits sane).
- Validate at the data seam: skip zero/inverted/missing debits, no-bar-at-entry, `entry_price<=0`; count drops (like `backtest_acd_full`'s `dropped`).
- Opus whole-branch review before merge (has caught a real bug every sub-project).

## 9. Out of scope (follow-ups)

- The **multi-day breakout-trend** overlay (longer-dated options, EOD marking; cheaper IVolatility daily futures-options) — a separate phase.
- Signal/structure parameter tuning + walk-forward (the standing project debt).
- Live paper trading on Schwab/TOS.
- Volatility/IV-aware structure selection (straddles on high-conviction days, etc.).
