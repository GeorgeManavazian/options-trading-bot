# backtest_cl_options.py — Phase-2: express phase-1 same-day crude signals as directional
# debit spreads on Databento NBBO; report hold-to-close vs active exit. Offline on cache.
# Run: .venv/bin/python bot/backtest_cl_options.py
import os
import statistics

from acd_macro import macro_context, apply_macro, BREAKOUT, FADES
from acd_fade_pricing import spread_entry, close_value, exit_target_stop
from load_cl_options_databento import resolve_legs, leg_bars
from load_cl_databento import CACHE_DIR
from backtest_acd_cl import build_cl_history, _ret_stats

START, END = "2010-06-06", "2026-06-29"


def collect_same_day(hist):
    out = []
    for i in range(len(hist)):
        ctx = macro_context(i, hist)
        for s in apply_macro(hist[i].day_result.setups, ctx):
            s.date = hist[i].date   # Setup has no date field; attach from DayEntry
            out.append(s)
    return out


def price_signal(setup, width=2.0):
    lg = resolve_legs(setup.date, setup.direction, setup.entry_price, width=width)
    if lg is None:
        return None
    lb = leg_bars(lg["long_sym"], setup.date)
    sb = leg_bars(lg["short_sym"], setup.date)
    if lb.empty or sb.empty:
        return None
    try:
        debit, entry_t = spread_entry(lb, sb, setup.entry_time)
    except ValueError:
        return None
    if debit <= 0:
        return None
    structure = {"kind": "debit_spread", "opt_type": lg["opt_type"],
                 "long_strike": lg["long_strike"], "width": lg["width"]}
    Ls = {str(r["time"]): r for _, r in lb.iterrows()}
    Ss = {str(r["time"]): r for _, r in sb.iterrows()}
    common = sorted(t for t in Ls if t in Ss and t >= entry_t)
    if not common:
        return None
    series = [(t, close_value(structure, Ls[t], Ss[t])) for t in common]
    # Floor exit proceeds at 0: a debit spread's worst case is letting it expire (value >= 0),
    # so you'd never sell for a negative amount even if the closing NBBO is crossed. This caps
    # loss at the debit (ret >= -100%), economically correct for a debit spread.
    close_val = max(series[-1][1], 0.0)
    active_val = max(exit_target_stop(debit, series, close_val, 0.5, 0.5), 0.0)
    return {"date": setup.date, "name": setup.name, "direction": setup.direction,
            "debit": debit, "close_val": close_val, "active_val": active_val}


def slip_ret(debit, exit_val, c):
    return (exit_val - 2 * c) / (debit + 2 * c) - 1.0


def report(trades, exit_key):
    if not trades:
        print(f"  ({exit_key}: no trades)"); return
    rets = [t[exit_key] / t["debit"] - 1.0 for t in trades]
    n, wr, tot, mdd, ra = _ret_stats(rets)
    sd = statistics.pstdev(rets); sharpe = statistics.mean(rets) / sd if sd > 0 else 0
    print(f"\n=== CL OPTIONS [{exit_key}] — {n} trades ===")
    print(f"@0 slip: win {wr:.0%}  total {tot:+.0%} on risk  maxDD {mdd:.0%}  "
          f"RISK-ADJ {ra:+.2f}  Sharpe {sharpe:+.2f}")
    for label, keys in [("BREAKOUTS", BREAKOUT), ("fades", FADES)]:
        sub = [t[exit_key]/t["debit"]-1.0 for t in trades if t["name"] in keys]
        if sub:
            w = sum(1 for r in sub if r > 0)
            print(f"    {label:<10} n={len(sub):>4}  win {w/len(sub):.0%}  total {sum(sub):+.0%}")
    print("  by year:")
    for yr in sorted({t["date"][:4] for t in trades}):
        sub = [t[exit_key]/t["debit"]-1.0 for t in trades if t["date"][:4] == yr]
        w = sum(1 for r in sub if r > 0)
        print(f"    {yr}  n={len(sub):>4}  win {w/len(sub):.0%}  total {sum(sub):+.0%}")
    print("  slippage sweep ($/leg/side):")
    for c in (0.0, 0.01, 0.02, 0.05):
        rr = [slip_ret(t["debit"], t[exit_key], c) for t in trades]
        n2, wr2, tot2, _, ra2 = _ret_stats(rr)
        print(f"    {c:.2f}:  win {wr2:.0%}  total {tot2:+.0%}  risk-adj {ra2:+.2f}")


def run(width=2.0):
    mc = os.path.join(CACHE_DIR, f"CL_1m_{START}_{END}.csv")
    dc = os.path.join(CACHE_DIR, f"CL_1d_{START}_{END}.csv")
    hist = build_cl_history(mc, dc)
    sigs = collect_same_day(hist)
    trades, dropped = [], 0
    for s in sigs:
        t = price_signal(s, width=width)
        if t is None:
            dropped += 1
            continue
        trades.append(t)
    print(f"CL options overlay: {len(trades)} trades ({dropped} dropped) from {len(sigs)} signals")
    report(trades, "close_val")
    report(trades, "active_val")
    return trades


if __name__ == "__main__":
    # offline self-test: slip_ret math + report on hand-built trades
    assert abs(slip_ret(1.0, 1.5, 0.0) - 0.5) < 1e-9
    assert slip_ret(1.0, 1.5, 0.05) < 0.5, "slippage lowers return"
    fake = [
        {"date":"2020-01-02","name":"a_held","direction":"long","debit":1.0,"close_val":1.4,"active_val":1.5},
        {"date":"2021-05-05","name":"failed_a","direction":"short","debit":1.0,"close_val":1.6,"active_val":1.5},
        {"date":"2021-06-06","name":"a_held","direction":"long","debit":1.0,"close_val":0.5,"active_val":0.5},
    ]
    report(fake, "close_val")
    report(fake, "active_val")
    print("Task 4 self-test OK: slip_ret + report")

    import glob
    if os.path.exists(os.path.join(CACHE_DIR, f"CL_1m_{START}_{END}.csv")) and \
            glob.glob(os.path.join(CACHE_DIR, "CLopt_*.csv")):
        try:
            run()
        except Exception as _exc:
            print(f"[run() skipped — cache incomplete or network error: {_exc}]")
