# Spec — V5 Paper Trading (part 1: the offline real-time core)

**Date:** 2026-07-01
**Status:** DRAFT — authored autonomously while the user is away; needs user review.
**Sub-project:** forward-test V5 by paper-trading it — the owed validation before real money.

> **Autonomy note:** the user asked me to "start getting ready to put the bot into TOS"
> while away, hoping not to confirm anything. This spec captures the design we discussed
> (Schwab is live-only, so we build our own paper simulator on live data). It defaults the
> open decisions (§7) and flags them for review. Nothing here has been implemented yet.

## 1. Purpose & the whole picture

V5's honest gap is that it has never traded forward. The next credibility step is to run
it in real time on live market data and record simulated trades — a **paper forward-test**.
Schwab's Trader API is **live-only** (no paper endpoint), so the safe design is to build
**our own paper simulator** fed by Schwab's live data: the bot generates V5 signals in real
time and logs simulated fills and P&L. **It never calls an order endpoint**, so there is
zero risk of an accidental live trade.

The full system is three parts:
- **Part 1 (this spec) — the offline real-time core:** a real-time V5 engine + a paper
  execution/ledger, both testable by *replaying cached historical days minute-by-minute*.
  Needs no Schwab access. **Build this first.**
- **Part 2 — the Schwab live-data client:** OAuth + live SPX quotes / 0DTE chains
  (`schwab-py`). Needs the approved developer key to run. Separate spec.
- **Part 3 — the daily runner:** orchestrates Part 1 on Part 2's live feed during market
  hours. Separate spec.

Part 1 is the bulk of the logic and is fully buildable now, so it's the right first move.

## 2. Scope of Part 1

A real-time V5 engine and paper ledger that consume a **stream of 1-minute bars** (a list
that grows one bar at a time) plus the live option quotes, and produce a paper trade ledger
— identical in logic to what will run live, but driven by a replayed cached day in tests.

## 3. The real-time engine

The backtest engine (`acd_micro.build_day`) processes a whole day's bars at once and has
**no lookahead**. The real-time version reuses it without duplicating the ACD logic:

- Accumulate the day's bars as they arrive: `bars_so_far` grows each minute.
- On each new bar, run the fade-signal path (`build_day` → `apply_macro` → filter to the V5
  fade setups) on `bars_so_far`. Because the engine has no lookahead, the signal it emits at
  bar *t* is exactly the signal the backtest would assign using data through *t*.
- Track which signals have already fired (by setup identity) so a signal is acted on once.
- `RealtimeEngine.on_bar(bar) -> new_signals` is the interface: feed a bar, get any newly
  fired V5 fade signals (with direction, entry level, time).

This makes the live engine **provably equivalent to the backtest**: replaying a cached day
bar-by-bar must reproduce that day's backtest signals (a self-test asserts this).

**Known implementation risk (resolve during the build, gated by the replay test):** the
macro context (`macro_context`) is multi-day, so it's computed once at the open from prior
history. If any part of `apply_macro`'s fade handling depends on *today's* not-yet-complete
OHLC (e.g. a conviction weight), the intraday value could differ from the backtest's
full-day value. The replay-equivalence test will catch this; if it fires, the fix is to
feed `apply_macro` only the prior-day-derived context for fade filtering (fades are kept
regardless of chop/regime, so this should hold, but it must be verified, not assumed).

## 4. The paper executor + ledger

On a new V5 fade signal, the paper executor simulates the V5 trade:
- Build the 0DTE debit spread (V5 structure: long ATM, short ±width, in the fade direction),
  priced at the **current live quotes** (long ask, short bid — the same conservative fills
  the backtest used).
- Track the open position each subsequent bar for the V5 **active exit** (take profit / cut
  loss near ±50% of debit), and settle at the close if neither fires.
- On exit, append a row to the **paper ledger** (`results/spx/paper_ledger.csv`) with the
  same columns as the backtest trade ledger plus a `mode` field (`paper`) and a real
  timestamp — so the paper record is directly comparable to the backtest.

`PaperExecutor` has **no method that submits an order anywhere.** It only reads quotes and
writes to the ledger. This is the hard safety guarantee.

## 5. Data interface (so Part 2 plugs in cleanly)

Part 1 depends only on two small interfaces, which the replay test fills from cache and Part
2 will fill from Schwab:
- `bar_source` — yields `(time, ohlc)` 1-minute bars for the underlying as the day proceeds.
- `quote_source(strike, opt_type)` — returns the current `(bid, ask)` for an option leg.

In tests, both are backed by the cached IVolatility minute data (replayed in order). Live,
both are backed by Schwab. Part 1 never imports Schwab directly.

## 6. Testing (the trust guarantee, again)

- **Replay equivalence:** feed a cached historical day through `RealtimeEngine` bar-by-bar;
  assert the fired V5 signals equal that day's backtest signals (same setups, same entry
  levels). This proves the real-time path matches the validated backtest.
- **Paper-fill equivalence:** run the paper executor over a replayed day using the cached
  quotes; assert the resulting P&L matches `price_cell`'s number for that day's trade (the
  same per-row assertion the trade ledger uses).
- **Safety:** a test/grep confirms `PaperExecutor` contains no order-submission call.
- Inline `__main__` assert self-tests, house style, no pytest.

## 7. Open decisions (defaulted here — please confirm on review)

1. **Which V5:** the tuned config (drop `failed_c`, 0DTE debit spread, active ±50% exit).
   Default: yes, the deployed V5.
2. **Paper sizing:** default **3% of equity, compounding** (your latest choice), starting at
   a configurable notional (default $10k). Easy to change to 1–2% — it's one constant.
3. **Bar granularity:** 1-minute (matches the backtest and Schwab's CHART stream).
4. **Fills:** conservative (long pays ask, short receives bid), matching the backtest.
5. **Session:** US regular hours 09:30–16:00 ET.

## 8. Success criteria

- A `RealtimeEngine` and `PaperExecutor` that, on a replayed cached day, reproduce the
  backtest's V5 signals and P&L, writing a paper ledger.
- No order-submission code path anywhere in the executor.
- Clean seams (`bar_source`, `quote_source`) so Part 2 (Schwab) plugs in without touching
  Part 1.

## 9. Out of scope (later parts / follow-ups)

- The Schwab OAuth + live-data client (Part 2, needs the approved key).
- The market-hours daily runner (Part 3).
- Any real-order submission — permanently out of scope for the paper system.
- Overnight/multi-day positions (V5 is same-day 0DTE).
