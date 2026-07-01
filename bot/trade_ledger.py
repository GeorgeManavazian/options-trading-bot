# trade_ledger.py — auditable trade-by-trade record of the winning V5 fade config
# (0DTE debit spread, drop failed_c, active +50%/-50% exit). Reconstructs every trade
# from the SAME real cached option prices the ④b backtest used, asserting each row's
# P&L == the backtest. Writes results/v5_trade_ledger.{csv,md}. Offline on cache.
# Spec: docs/superpowers/specs/2026-07-01-v5-trade-ledger.md
# Run:  .venv/bin/python bot/trade_ledger.py
import csv
import os
from collections import defaultdict

from acd_fade_signals import collect_fades, grid_cells
from backtest_acd_fades import price_cell, _value_series
from acd_fade_pricing import spread_entry, expire_value
from load_ivol_intraday import load_cached_minutes
from run_acd_signal import daily_hlc

TARGET, STOP = 0.5, 0.5          # V5 active-exit thresholds (price_cell defaults)

COLUMNS = ["#", "date", "signal_time", "direction", "setup", "conviction", "why_entered",
           "underlying_at_entry", "structure", "option_type", "long_strike", "short_strike",
           "debit_paid", "max_loss", "exit_reason", "exit_time", "settle_close", "pnl_$",
           "return_on_risk_%", "result"]


def _why(setup):
    if setup.direction == "long":
        s = ("SPX broke BELOW the A-trigger (a bearish breakout signal) then failed to hold it "
             "-> faded LONG, betting the failed breakdown snaps back up.")
    else:
        s = ("SPX broke ABOVE the A-trigger (a bullish breakout signal) then failed to hold it "
             "-> faded SHORT, betting the failed breakout reverses down.")
    if setup.name == "failed_a_pivot":
        s += " The failed level sat on the prior-day pivot range (two signals agreeing -> higher conviction)."
    return s


def _exit(struct, long_bars, short_bars, fill_bar, debit, hold_val):
    """Replay the active exit (same logic as price_cell); return (reason, time, value)."""
    for t, v in sorted(_value_series(struct, long_bars, short_bars, fill_bar)):
        if v - debit >= TARGET * debit:
            return "hit +50% target", t, v
        if debit - v >= STOP * debit:
            return "hit -50% stop", t, v
    return "held to close", "16:00", hold_val


def build_ledger():
    """All 119 V5 trades, fully reconstructed; each row's pnl_$ asserted == backtest."""
    closes = {d: v[2] for d, v in daily_hlc().items()}
    cal = sorted(closes)
    rows = []
    for date, s in collect_fades():
        if s.name == "failed_c":                      # V5 filter
            continue
        cell = next((c for c in grid_cells(date, s, cal)
                     if c["horizon"] == "0DTE" and c["structure"]["kind"] == "debit_spread"), None)
        if cell is None:
            continue
        t = price_cell(cell, s, closes)               # the backtest's own number
        if t is None:
            continue
        long_bars = load_cached_minutes(*cell["long_contract"])
        short_bars = load_cached_minutes(*cell["short_contract"])
        debit, fill_bar = spread_entry(long_bars, short_bars, s.entry_time)
        struct = cell["structure"]
        settle = closes[date]
        hold_val = expire_value(struct, settle)
        reason, xtime, xval = _exit(struct, long_bars, short_bars, fill_bar, debit, hold_val)
        pnl = round((xval - debit) * 100, 2)
        assert abs(pnl - t["pnl0_ts"]) < 0.01, (date, pnl, t["pnl0_ts"])   # TRUST GUARANTEE
        typ = struct["opt_type"]
        kind = "bull call spread" if typ == "call" else "bear put spread"
        lk, sk = struct["long_strike"], struct["short_strike"]
        rows.append({
            "#": len(rows) + 1, "date": date, "signal_time": s.entry_time,
            "direction": s.direction, "setup": s.name, "conviction": s.conviction,
            "why_entered": _why(s), "underlying_at_entry": round(s.entry_price, 2),
            "structure": f"{kind} {int(lk)}/{int(sk)}", "option_type": typ,
            "long_strike": lk, "short_strike": sk, "debit_paid": round(debit, 2),
            "max_loss": round(debit * 100, 2), "exit_reason": reason, "exit_time": xtime,
            "settle_close": round(settle, 2), "pnl_$": pnl,
            "return_on_risk_%": round(pnl / (debit * 100) * 100, 1),
            "result": "WIN" if pnl > 0 else "LOSS",
        })
    return rows


if __name__ == "__main__":
    rows = build_ledger()
    assert len(rows) == 119, f"expected 119 V5 trades, got {len(rows)}"
    assert set(COLUMNS) <= set(rows[0]), set(COLUMNS) - set(rows[0])
    tot = sum(r["return_on_risk_%"] for r in rows)
    wins = sum(1 for r in rows if r["result"] == "WIN")
    assert 4100 < tot < 4250, f"total {tot} != ~4171 (scoreboard reconcile)"
    assert 0.78 <= wins / len(rows) <= 0.86, wins / len(rows)
    print(f"OK build_ledger: {len(rows)} trades, +{tot:.0f}% on risk, win {wins/len(rows)*100:.0f}% "
          f"(per-row P&L == backtest, asserted)")
