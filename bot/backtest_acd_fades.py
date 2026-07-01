# backtest_acd_fades.py — (4b) backtest the ACD FADES as options across the 2x2
# grid ({0DTE, overnight} x {debit_spread, long_option}). Enter at the fade's
# intraday time (real NBBO bars); settle at each option's expiry via the cached
# underlying close. Reports per cell + a slippage sweep + a 0DTE hold-vs-stop
# comparison. Offline on cache. Run: .venv/bin/python bot/backtest_acd_fades.py
from collections import Counter

from acd_fade_signals import collect_fades, grid_cells
from acd_fade_pricing import spread_entry, expire_value, close_value, exit_target_stop
from load_ivol_intraday import load_cached_minutes
from run_acd_signal import daily_hlc
from backtest_acd_full import _with_slip, _stats


def _value_series(structure, long_bars, short_bars, entry_t):
    """[(time, close_value)] from entry_t onward (0DTE active-exit walk)."""
    Lb = {str(r["time"]): r for _, r in long_bars.iterrows()}
    Sb = {str(r["time"]): r for _, r in short_bars.iterrows()} if short_bars is not None else None
    out = []
    for t in sorted(Lb):
        if t < entry_t:
            continue
        if Sb is not None and t not in Sb:
            continue
        out.append((t, close_value(structure, Lb[t], None if Sb is None else Sb[t])))
    return out


def price_cell(cell, setup, closes, target=0.5, stop=0.5):
    """One grid cell -> a trade dict, or None if un-markable/degenerate."""
    long_bars = load_cached_minutes(*cell["long_contract"])
    if long_bars is None or long_bars.empty:
        return None
    short_c = cell["short_contract"]
    short_bars = load_cached_minutes(*short_c) if short_c else None
    if short_c and (short_bars is None or short_bars.empty):
        return None
    try:
        debit, entry_t = spread_entry(long_bars, short_bars, setup.entry_time)
    except ValueError:
        return None
    if debit <= 0:                                 # inverted/degenerate -> skip
        return None
    settle_px = closes.get(cell["settle_date"])
    if settle_px is None or settle_px <= 0:
        return None
    struct = cell["structure"]
    hold_val = expire_value(struct, settle_px)     # hold-to-expiry
    nlegs = 1 if short_c is None else 2
    trade = {"date": cell["long_contract"][1], "horizon": cell["horizon"],
             "kind": struct["kind"], "nlegs": nlegs, "debit": debit,
             "max_loss": debit * 100,
             "pnl0": round((hold_val - debit) * 100, 2)}
    if cell["horizon"] == "0DTE":                  # active target/stop comparison
        vs = _value_series(struct, long_bars, short_bars, entry_t)
        ts_val = exit_target_stop(debit, vs, hold_val, target, stop)
        trade["pnl0_ts"] = round((ts_val - debit) * 100, 2)
    return trade


def run_fades():
    closes = {d: v[2] for d, v in daily_hlc().items()}
    calendar = sorted(closes)
    fades = collect_fades()
    trades, dropped = [], 0
    for date, setup in fades:
        for cell in grid_cells(date, setup, calendar):
            t = price_cell(cell, setup, closes)
            if t is None:
                dropped += 1
            else:
                trades.append(t)
    return trades, dropped


def _cell_line(rows, label):
    n, wr, total, mdd, ra = _stats([r["ret_pct"] for r in rows])
    print(f"  {label:<26} n={n:>3}  win {wr:.0%}  total {total:+.0%} on risk  "
          f"maxDD {mdd:.0%}  risk-adj {ra:+.2f}")


def report(trades):
    print(f"\n=== FADE backtest — {len(trades)} trades ===")
    print("by cell:", dict(Counter((t['horizon'], t['kind']) for t in trades)))
    base = _with_slip(trades, 0.0)                 # adds ret_pct = pnl/max_loss
    print("\n@0 slippage, hold-to-expiry, by grid cell:")
    for horizon in ("0DTE", "overnight"):
        for kind in ("debit_spread", "long_option"):
            rows = [t for t in base if t["horizon"] == horizon and t["kind"] == kind]
            if rows:
                _cell_line(rows, f"{horizon}/{kind}")

    print("\nslippage sweep (per cell, does the edge survive costs?):")
    for horizon in ("0DTE", "overnight"):
        for kind in ("debit_spread", "long_option"):
            sub = [t for t in trades if t["horizon"] == horizon and t["kind"] == kind]
            if not sub:
                continue
            line = f"  {horizon}/{kind:<13}"
            for slip in (0.0, 0.05, 0.10, 0.20):
                rets = [r["ret_pct"] for r in _with_slip(sub, slip)]
                _, wr2, tot2, _, _ = _stats(rets)
                line += f"  {int(slip*100)}c:{tot2:+.0%}/{wr2:.0%}"
            print(line)

    ov = [t for t in base if t["horizon"] == "0DTE" and "pnl0_ts" in t]
    if ov:
        print("\n0DTE exit comparison (the recurring hold-vs-tight-stop lesson):")
        hold = [t["ret_pct"] for t in ov]
        ts = [t["pnl0_ts"] / t["max_loss"] for t in ov]
        _, wr_h, tot_h, mdd_h, _ = _stats(hold)
        _, wr_t, tot_t, mdd_t, _ = _stats(ts)
        print(f"  hold-to-close : win {wr_h:.0%}  total {tot_h:+.0%}  maxDD {mdd_h:.0%}")
        print(f"  target/stop   : win {wr_t:.0%}  total {tot_t:+.0%}  maxDD {mdd_t:.0%}")


if __name__ == "__main__":
    # --- pure price_cell self-test on monkeypatched cached bars (offline) ---
    import pandas as pd
    import load_ivol_intraday as lv
    from acd_micro import Setup

    def fake_cache(sym, date, exp, strike, typ):
        # long 5000 call ~ deep; short 5025 call ~ cheaper -> debit ~12; settle 5040
        px = {5000.0: (30, 32), 5025.0: (18, 20)}.get(float(strike))
        if px is None:
            return None
        bid, ask = px
        return pd.DataFrame({"time": ["10:00", "16:00"], "bid": [bid, bid],
                             "ask": [ask, ask]})
    lv.load_cached_minutes = fake_cache            # monkeypatch (backtest imported the name)
    globals()["load_cached_minutes"] = fake_cache

    setup = Setup("failed_a", "long", "10:00", 5003.0, None, 1, "intraday", {})
    ds_cell = {"horizon": "0DTE",
               "structure": {"kind": "debit_spread", "opt_type": "call",
                             "long_strike": 5000.0, "short_strike": 5025.0, "width": 25.0},
               "long_contract": ("SPX", "2024-06-03", "2024-06-03", 5000.0, "call"),
               "short_contract": ("SPX", "2024-06-03", "2024-06-03", 5025.0, "call"),
               "settle_date": "2024-06-03"}
    tr = price_cell(ds_cell, setup, {"2024-06-03": 5040.0})
    # debit = 32 - 18 = 14; expire_value(bull call, 5040) = min(40,25) = 25; pnl=(25-14)*100
    assert tr is not None and abs(tr["debit"] - 14.0) < 1e-9 and tr["pnl0"] == 1100.0, tr
    assert tr["nlegs"] == 2 and "pnl0_ts" in tr, tr
    print(f"OK price_cell (debit 14, pnl {tr['pnl0']})")

    lo_cell = {"horizon": "0DTE",
               "structure": {"kind": "long_option", "opt_type": "call", "long_strike": 5000.0},
               "long_contract": ("SPX", "2024-06-03", "2024-06-03", 5000.0, "call"),
               "short_contract": None, "settle_date": "2024-06-03"}
    tr2 = price_cell(lo_cell, setup, {"2024-06-03": 5040.0})
    # debit = ask 32; expire_value = 40; pnl = (40-32)*100 = 800
    assert tr2["debit"] == 32.0 and tr2["pnl0"] == 800.0 and tr2["nlegs"] == 1, tr2
    print(f"OK price_cell long option (debit 32, pnl {tr2['pnl0']})")

    print("Restore + attempt full run (needs the real cache)...")
    import importlib
    importlib.reload(lv)
    from load_ivol_intraday import load_cached_minutes as _real
    globals()["load_cached_minutes"] = _real
    trades, dropped = run_fades()
    print(f"full run: {len(trades)} trades, {dropped} dropped")
    if trades:
        report(trades)
    else:
        print("(no cached fade bars yet — run bot/pull_fade_data.py first)")
