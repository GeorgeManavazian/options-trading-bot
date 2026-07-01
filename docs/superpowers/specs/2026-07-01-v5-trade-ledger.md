# Spec — V5 Trade Ledger (auditable trade-by-trade record)

**Date:** 2026-07-01
**Status:** approved (design), pending spec review
**Sub-project:** ACD refine sprint — produce a transparent, auditable record of every
trade the winning V5 fade config took, as evidence/credibility material.

## 1. Purpose

The bake-off crowned V5 (drop `failed_c` + active exit, 0DTE debit spread) with a
strong risk-adjusted result. To make that result *inspectable* — the kind of thing a
skeptic (or a resume reviewer) can audit rather than take on faith — produce a complete,
honest, trade-by-trade ledger: every one of the 119 V5 trades, why it was taken, the
option structure, why it exited, and the P&L — all reconstructed from the same real
cached option prices the backtest used, with each row's P&L asserted equal to the
backtest number.

Non-goal: new strategy work, or claiming live results. This is a transparency/reporting
artifact over the EXISTING V5 backtest.

## 2. Deliverables (all in `results/`)

1. **`v5_trade_ledger.csv`** — the raw ledger, one row per trade (119 rows), all columns
   below. Opens in Excel / Google Sheets.
2. **`v5_trade_ledger.md`** — the human-readable report: honest summary + caveats, a
   clean table, and a one-line narrative for every trade grouped by year. Renders on
   GitHub.

## 3. Columns (per trade)

| column | meaning |
|---|---|
| `#` | trade number (1..119, in date order) |
| `date` | trade date (YYYY-MM-DD) |
| `signal_time` | HH:MM the fade signal fired (setup.entry_time) |
| `direction` | `long` / `short` (the fade direction) |
| `setup` | `failed_a` / `failed_a_pivot` (V5 excludes `failed_c`) |
| `conviction` | 1 or 2 |
| `why_entered` | plain-English reason (see §5) |
| `underlying_at_entry` | SPX level at the signal (setup.entry_price) |
| `structure` | e.g. `bull call spread 4465/4490` / `bear put spread 5150/5125` |
| `option_type` | `call` / `put` |
| `long_strike` | ATM long leg |
| `short_strike` | width-OTM short leg |
| `debit_paid` | net debit per contract ($) = the capital at risk per share |
| `max_loss` | $ risked per contract (= debit × 100) |
| `exit_reason` | `hit +50% target` / `hit -50% stop` / `held to close` |
| `exit_time` | HH:MM of the target/stop bar, or `16:00` if held to close |
| `settle_close` | SPX close on the trade date |
| `pnl_$` | profit/loss per contract ($) |
| `return_on_risk_%` | pnl_$ / max_loss |
| `result` | `WIN` / `LOSS` |

## 4. Data flow (reconstruction — reuses the ④b engine)

For each `(date, setup)` from `collect_fades()` with `setup.name != "failed_c"`, take the
0DTE `debit_spread` cell from `grid_cells(date, setup, calendar)` and:

```
long_bars  = load_cached_minutes(*cell["long_contract"])     # real cached NBBO minutes
short_bars = load_cached_minutes(*cell["short_contract"])
debit, fill_bar = spread_entry(long_bars, short_bars, setup.entry_time)
struct     = cell["structure"]                               # kind/opt_type/long_strike/short_strike/width
settle     = closes[date]                                    # SPX close (daily_hlc)
hold_val   = expire_value(struct, settle)
series     = _value_series(struct, long_bars, short_bars, fill_bar)   # [(time, close_value)]
# walk the series to find the exit reason (the SAME logic price_cell/exit_target_stop use):
exit = "held to close"; exit_time = "16:00"; exit_val = hold_val
for t, v in sorted(series):
    if v - debit >= 0.5 * debit:  exit, exit_time, exit_val = "hit +50% target", t, v; break
    if debit - v >= 0.5 * debit:  exit, exit_time, exit_val = "hit -50% stop",  t, v; break
pnl = round((exit_val - debit) * 100, 2)
```

Trades where `price_cell(...)` returns None (missing bars / no fillable entry / debit ≤ 0 /
bad settle) are skipped exactly as the backtest skips them — the ledger's trade set is
identically the V5 trade set.

**Self-consistency assertion (the trust guarantee):** for every row, the reconstructed
`pnl` MUST equal the backtest's `price_cell(...)["pnl0_ts"]` (the active-exit P&L). The
builder asserts this per trade; any mismatch is a hard failure. (Verified on trade #1:
reconstructed 395.0 == backtest 395.0.)

## 5. The `why_entered` narrative (deterministic, from the setup)

Derived purely from the setup — no discretion:
- **long fade** (bought calls): "SPX broke BELOW the A-trigger (a bearish breakout signal)
  then failed to hold it → faded LONG, betting the failed breakdown snaps back up."
- **short fade** (bought puts): "SPX broke ABOVE the A-trigger (a bullish breakout signal)
  then failed to hold it → faded SHORT, betting the failed breakout reverses down."
- If `setup == failed_a_pivot`, append: " The failed level sat on the prior-day pivot range
  (two signals agreeing → higher conviction)."

## 6. Honesty framing (baked into the .md header)

The report states plainly, up top:
- This is a **backtest on real historical option prices** (IVolatility), not live or
  paper-traded results.
- It is **every** trade the V5 config took over ~3 years (Jul 2023 – Jun 2026) — nothing
  cherry-picked; winners and losers both shown.
- Each row is **auditable**: P&L recomputed from the source prices and asserted equal to
  the backtest.
- The honest next credibility step is **forward / paper trading**; and the V5 config was
  selected as best-of-9, so a walk-forward is still owed.
- Returns are on capital-at-risk; a `$10k @ 1%/trade` account context (from the equity
  chart) = +42% over the span, worst dip −1.1%.

## 7. Architecture

One new file: **`bot/trade_ledger.py`**.
- `build_ledger() -> list[dict]` — the reconstruction above; returns the 119 rows (ordered
  by date), each carrying every §3 field. Asserts per-row P&L == backtest.
- `write_csv(rows, path)` — dump the CSV (stdlib `csv`).
- `write_md(rows, path)` — the summary + caveats + table + per-year one-line narratives.
- `__main__` — build, write both files to `results/`, print summary + a rendered sample
  (first ~12 rows) to stdout.

Reuses: `collect_fades`/`grid_cells` (acd_fade_signals), `price_cell`/`_value_series`
(backtest_acd_fades), `spread_entry`/`expire_value` (acd_fade_pricing),
`load_cached_minutes` (load_ivol_intraday), `daily_hlc` (run_acd_signal). Offline, no
network.

## 8. Success criteria

- `results/v5_trade_ledger.csv` with 119 rows × all §3 columns, openable in a spreadsheet.
- `results/v5_trade_ledger.md` with honest header, table, and 119 one-line narratives.
- Every row's reconstructed P&L equals the backtest's `pnl0_ts` (asserted; build fails
  otherwise) — the ledger provably IS the backtest.
- Row count and total P&L reconcile with the V5 scoreboard (n=119, total +4171% on risk).

## 9. Testing

- Inline `__main__` self-test / assertions (house style; no pytest): the per-row
  P&L-matches-backtest assertion runs for all 119 as part of `build_ledger`; assert the
  aggregate (n == 119, sum of `return_on_risk_%` ≈ 41.71, win count ≈ 82%) reconciles with
  the scoreboard; assert the CSV has 119 data rows and the header matches §3.
- Opus whole-branch review before merge.

## 10. Out of scope

- Walk-forward / forward-testing (the real next credibility step) — separate sub-project.
- Ledgers for the other variants (V0/V2/etc.) — only the chosen V5.
- Any live/paper-trading integration.
