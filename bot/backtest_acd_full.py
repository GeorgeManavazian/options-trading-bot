# backtest_acd_full.py — ④ backtest the FULL ACD bot end-to-end (①micro + ②macro + ③options)
# on real cached option data. Scope of THIS driver: the MULTIDAY macro signals (reversal_trade /
# sushi), expressed via acd_options into ~30-DTE structures, marked day-by-day on the cached dated
# chains (dte10-50 big pull), exited via the 3-day pivot trailing stop / expiry (reusing the tested
# backtest_acd.simulate_hold). Reports risk-adjusted return per setup + a slippage sweep.
#
# (Intraday fades @ 0DTE = the next slice ④b — needs 0DTE-spread intraday pricing; deferred.)
# Offline on cache. Run:  .venv/bin/python bot/backtest_acd_full.py
import statistics
from collections import Counter
from itertools import accumulate

from diag_full_signal import build_history
from acd_macro import macro_context, apply_macro
from acd_options import express, horizon_of, DEFAULT_POLICY
from load_acd_dated import dated_chain_df, pick_entry_chain
from backtest_acd import simulate_hold, _safe_mark, _degenerate
from backtest import max_drawdown

SYM = "SPX"
_CHAINS = {}


def _chain(sym, date):
    key = (sym, date)
    if key not in _CHAINS:
        _CHAINS[key] = dated_chain_df(sym, date)     # memoize the large CSV reads
    return _CHAINS[key]


def _hold_fixed(pos, entry_date, days, hold_days, mark_fn, expiration):
    """Horizon-matched exit: mark at entry_date + hold_days (walk back to the last markable day)."""
    i = days.index(entry_date)
    exit_i = min(i + hold_days, len(days) - 1)
    for j in range(exit_i, i, -1):
        m = mark_fn(days[j], expiration, pos["legs"])
        if m is not None:
            return round((m - pos["entry_cost"]) * 100, 2), days[j]
    return None, None


def run_full_backtest(hist, target_dte=30, hold_days=None):
    """hold_days=None -> 3-day pivot trailing stop (simulate_hold); int -> fixed-horizon hold."""
    hlc = {e.date: e.ohlc for e in hist}
    days = sorted(hlc)
    trades, dropped = [], 0
    for i, day in enumerate(hist):
        ctx = macro_context(i, hist)
        sigs = apply_macro(day.day_result.setups, ctx) + ctx.macro_setups
        D = day.date
        for setup in sigs:
            if horizon_of(setup) != "multiday":
                continue                              # this driver = multiday macro slice
            try:
                puts, calls, spot, exp = pick_entry_chain(_chain(SYM, D), target_dte)
                pos = express(setup, puts, calls, spot, exp, DEFAULT_POLICY)
            except Exception:
                dropped += 1
                continue
            max_loss = max(0.0, pos["max_loss"])
            if max_loss <= 0 or _degenerate(pos):
                dropped += 1
                continue
            mark_fn = lambda d, e, legs: _safe_mark(_chain, SYM, d, e, legs)
            if hold_days is None:
                pnl, xd, reason = simulate_hold(setup.direction, pos, exp, D, days, hlc,
                                                mark_fn, stop_B=setup.stop)
            else:
                pnl, xd = _hold_fixed(pos, D, days, hold_days, mark_fn, exp)
                reason = "hold"
            if pnl is None:
                dropped += 1
                continue
            trades.append({"date": D, "setup": setup.name, "direction": setup.direction,
                           "conviction": setup.conviction, "wrapper": pos["wrapper"],
                           "nlegs": len(pos["legs"]), "max_loss": max_loss,
                           "pnl0": round(pnl, 2), "exit_date": xd, "reason": reason})
    return trades, dropped


def _with_slip(trades, slip):
    """Post-hoc slippage haircut: slip $/leg on entry+exit fills."""
    out = []
    for t in trades:
        pnl = t["pnl0"] - slip * t["nlegs"] * 2 * 100
        out.append({**t, "pnl": pnl, "ret_pct": pnl / t["max_loss"]})
    return out


def _stats(rets):
    n = len(rets)
    wins = sum(1 for r in rets if r > 0)
    total = sum(rets)
    mdd = max_drawdown(list(accumulate(rets)))
    ra = total / abs(mdd) if mdd else (float("inf") if total > 0 else float("-inf") if total < 0 else 0)
    return n, wins / n, total, mdd, ra


def report(trades):
    print(f"\n=== FULL ACD multiday backtest — {len(trades)} trades ===")
    print("by setup:", dict(Counter(t["setup"] for t in trades)))
    t0 = _with_slip(trades, 0.0)
    n, wr, total, mdd, ra = _stats([t["ret_pct"] for t in t0])
    sd = statistics.pstdev([t["ret_pct"] for t in t0])
    sharpe = statistics.mean([t["ret_pct"] for t in t0]) / sd if sd > 0 else 0
    print(f"\n@0 slippage:  win {wr:.0%}   total {total:+.0%} on risk   maxDD {mdd:.0%}   "
          f"RISK-ADJ {ra:+.2f}   Sharpe {sharpe:+.2f}")
    for name in sorted(set(t["setup"] for t in t0)):
        sub = [t["ret_pct"] for t in t0 if t["setup"] == name]
        w = sum(1 for r in sub if r > 0)
        print(f"    {name:<15} n={len(sub):>3}   win {w/len(sub):.0%}   total {sum(sub):+.0%} on risk")
    print("\nslippage sweep (does the edge survive costs?):")
    for slip in (0.0, 0.05, 0.10, 0.20):
        rets = [t["ret_pct"] for t in _with_slip(trades, slip)]
        n2, wr2, tot2, _, ra2 = _stats(rets)
        print(f"  {int(slip*100):>2}c/leg:  win {wr2:.0%}   total {tot2:+.0%} on risk   risk-adj {ra2:+.2f}")


def _quick(trades):
    t = _with_slip(trades, 0.0)
    n, wr, total, mdd, ra = _stats([x["ret_pct"] for x in t])
    rev = [x["ret_pct"] for x in t if x["setup"] == "reversal_trade"]
    return (f"n={n} win {wr:.0%} total {total:+.0%} maxDD {mdd:.0%} risk-adj {ra:+.2f}"
            f"  | reversal: win {sum(1 for r in rev if r>0)/max(len(rev),1):.0%} total {sum(rev):+.0%}")


if __name__ == "__main__":
    print("Building full-engine signal history (cached, ~1 min)...", flush=True)
    hist = build_history()

    print("\n=== EXIT COMPARISON (multiday macro signals) ===", flush=True)
    for label, hd in [("3-day pivot trailing stop", None), ("fixed hold 5 days", 5),
                      ("fixed hold 10 days", 10)]:
        trades, dropped = run_full_backtest(hist, hold_days=hd)
        print(f"  {label:<26}: {_quick(trades)}", flush=True)

    print("\n=== FULL REPORT: horizon-matched hold (5 days) ===", flush=True)
    trades, dropped = run_full_backtest(hist, hold_days=5)
    print(f"trades {len(trades)} (dropped {dropped})")
    if trades:
        report(trades)
